from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from pathlib import Path
from statistics import fmean
from typing import Any


def _index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed = {str(row["case_id"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("each run must contain unique case IDs")
    return indexed


def _metric_summary(
    baseline: list[float],
    candidate: list[float],
    *,
    clusters: list[str],
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    deltas = [
        right - left
        for left, right in zip(baseline, candidate, strict=True)
    ]
    if len(clusters) != len(deltas):
        raise ValueError("each paired delta must have a bootstrap cluster")
    cluster_ids = sorted(set(clusters))
    clustered_deltas = {
        cluster_id: [
            delta
            for delta, row_cluster in zip(deltas, clusters, strict=True)
            if row_cluster == cluster_id
        ]
        for cluster_id in cluster_ids
    }
    rng = random.Random(seed)
    bootstrap = sorted(
        fmean(
            delta
            for _ in cluster_ids
            for delta in clustered_deltas[
                cluster_ids[rng.randrange(len(cluster_ids))]
            ]
        )
        for _ in range(bootstrap_samples)
    )
    return {
        "baseline_mean": fmean(baseline),
        "candidate_mean": fmean(candidate),
        "mean_delta": fmean(deltas),
        "wins": sum(delta > 0 for delta in deltas),
        "losses": sum(delta < 0 for delta in deltas),
        "ties": sum(delta == 0 for delta in deltas),
        "repo_cluster_bootstrap_95_ci": [
            bootstrap[int(0.025 * (bootstrap_samples - 1))],
            bootstrap[int(0.975 * (bootstrap_samples - 1))],
        ],
    }


def _mcnemar_exact_p(recovered: int, lost: int) -> float:
    discordant = recovered + lost
    if discordant == 0:
        return 1.0
    lower = min(recovered, lost)
    one_sided = sum(
        math.comb(discordant, value)
        for value in range(lower + 1)
    ) / (2**discordant)
    return min(1.0, 2 * one_sided)


def analyze_pair(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    metrics: tuple[str, ...] = ("MRR", "Recall@5", "Recall@20", "BCY@8k"),
    binary_metric: str | None = "Recall@20",
    binary_label: str = "any_gold_at_20",
    bootstrap_samples: int = 100_000,
    seed: int = 20260823,
) -> dict[str, Any]:
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    baseline = _index(baseline_rows)
    candidate = _index(candidate_rows)
    if not baseline or set(baseline) != set(candidate):
        raise ValueError("paired runs must contain the same non-empty case set")
    case_ids = sorted(baseline)
    if any(
        baseline[case_id].get("workflow")
        != candidate[case_id].get("workflow")
        for case_id in case_ids
    ):
        raise ValueError("paired cases must have matching workflows")
    if any(
        not baseline[case_id].get("repo")
        or baseline[case_id].get("repo") != candidate[case_id].get("repo")
        for case_id in case_ids
    ):
        raise ValueError("paired cases must have matching repository clusters")
    clusters = [str(baseline[case_id]["repo"]) for case_id in case_ids]

    metric_results: dict[str, Any] = {}
    for index, metric in enumerate(metrics):
        left = [
            float((baseline[case_id].get("metrics") or {})[metric])
            for case_id in case_ids
        ]
        right = [
            float((candidate[case_id].get("metrics") or {})[metric])
            for case_id in case_ids
        ]
        metric_results[metric] = _metric_summary(
            left,
            right,
            clusters=clusters,
            bootstrap_samples=bootstrap_samples,
            seed=seed + index,
        )

    workflows = sorted(
        {str(baseline[case_id]["workflow"]) for case_id in case_ids}
    )
    by_workflow: dict[str, Any] = {}
    for workflow in workflows:
        workflow_ids = [
            case_id
            for case_id in case_ids
            if str(baseline[case_id]["workflow"]) == workflow
        ]
        by_workflow[workflow] = {}
        for metric in metrics:
            left = [
                float((baseline[case_id].get("metrics") or {})[metric])
                for case_id in workflow_ids
            ]
            right = [
                float((candidate[case_id].get("metrics") or {})[metric])
                for case_id in workflow_ids
            ]
            deltas = [
                candidate_value - baseline_value
                for baseline_value, candidate_value in zip(
                    left,
                    right,
                    strict=True,
                )
            ]
            by_workflow[workflow][metric] = {
                "n": len(workflow_ids),
                "baseline_mean": fmean(left),
                "candidate_mean": fmean(right),
                "mean_delta": fmean(deltas),
                "wins": sum(delta > 0 for delta in deltas),
                "losses": sum(delta < 0 for delta in deltas),
            }

    result = {
        "cases": len(case_ids),
        "metrics": metric_results,
        "by_workflow": by_workflow,
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": seed,
        "bootstrap_unit": "repository",
    }
    if binary_metric is not None:
        baseline_hits = {
            case_id: float(
                (baseline[case_id].get("metrics") or {})[binary_metric]
            )
            > 0
            for case_id in case_ids
        }
        candidate_hits = {
            case_id: float(
                (candidate[case_id].get("metrics") or {})[binary_metric]
            )
            > 0
            for case_id in case_ids
        }
        recovered = sum(
            not baseline_hits[case_id] and candidate_hits[case_id]
            for case_id in case_ids
        )
        lost = sum(
            baseline_hits[case_id] and not candidate_hits[case_id]
            for case_id in case_ids
        )
        result[binary_label] = {
            "metric": binary_metric,
            "baseline_cases": sum(baseline_hits.values()),
            "candidate_cases": sum(candidate_hits.values()),
            "recovered": recovered,
            "lost": lost,
            "both": sum(
                baseline_hits[case_id] and candidate_hits[case_id]
                for case_id in case_ids
            ),
            "neither": sum(
                not baseline_hits[case_id] and not candidate_hits[case_id]
                for case_id in case_ids
            ),
            "mcnemar_exact_p": _mcnemar_exact_p(recovered, lost),
        }
    return result


def _load_run(
    connection: sqlite3.Connection,
    run_id: str,
) -> list[dict[str, Any]]:
    run = connection.execute(
        "select status from runs where run_id = ?",
        (run_id,),
    ).fetchone()
    if run is None:
        raise ValueError(f"unknown run: {run_id}")
    if run[0] != "done":
        raise ValueError(f"run is not valid and complete: {run_id} ({run[0]})")
    rows = connection.execute(
        """
        select case_id, workflow, repo, ok, metrics
        from cases
        where run_id = ?
        order by case_id
        """,
        (run_id,),
    ).fetchall()
    if not rows or any(not row[3] for row in rows):
        raise ValueError(f"run contains failed cases: {run_id}")
    return [
        {
            "case_id": case_id,
            "workflow": workflow,
            "repo": repo,
            "metrics": json.loads(metrics_json),
        }
        for case_id, workflow, repo, _ok, metrics_json in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--metrics",
        default="MRR,Recall@5,Recall@20,BCY@8k",
    )
    parser.add_argument("--binary-metric", default="Recall@20")
    parser.add_argument("--binary-label", default="any_gold_at_20")
    parser.add_argument("--bootstrap-samples", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    try:
        baseline = _load_run(connection, args.baseline)
        candidate = _load_run(connection, args.candidate)
    finally:
        connection.close()
    summary = analyze_pair(
        baseline,
        candidate,
        metrics=tuple(
            metric.strip()
            for metric in args.metrics.split(",")
            if metric.strip()
        ),
        binary_metric=args.binary_metric or None,
        binary_label=args.binary_label,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    summary["baseline_run"] = args.baseline
    summary["candidate_run"] = args.candidate
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
