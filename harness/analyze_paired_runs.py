"""Paired retrieval-run analysis with repository-cluster bootstrap intervals."""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

METRICS = ("MRR", "Recall@5", "Recall@20", "BCY@8k")


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _mcnemar_exact_p(recovered: int, lost: int) -> float:
    discordant = recovered + lost
    if discordant == 0:
        return 1.0
    smaller = min(recovered, lost)
    lower_tail = sum(
        math.comb(discordant, count) for count in range(smaller + 1)
    ) / (2**discordant)
    return min(1.0, 2.0 * lower_tail)


def _cluster_bootstrap(
    rows: list[tuple[dict[str, Any], dict[str, Any]]],
    metric: str,
    *,
    samples: int,
    seed: int,
) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for baseline, candidate in rows:
        grouped[str(baseline["repo"])].append(
            float(candidate["metrics"][metric])
            - float(baseline["metrics"][metric])
        )
    repositories = sorted(grouped)
    randomizer = random.Random(seed)
    draws: list[float] = []
    for _ in range(samples):
        values: list[float] = []
        for _repo_index in repositories:
            selected = randomizer.choice(repositories)
            values.extend(grouped[selected])
        draws.append(fmean(values))
    return [_quantile(draws, 0.025), _quantile(draws, 0.975)]


def _metric_summary(
    rows: list[tuple[dict[str, Any], dict[str, Any]]],
    metric: str,
) -> dict[str, Any]:
    baseline_values = [float(row[0]["metrics"][metric]) for row in rows]
    candidate_values = [float(row[1]["metrics"][metric]) for row in rows]
    deltas = [
        candidate - baseline
        for baseline, candidate in zip(
            baseline_values,
            candidate_values,
            strict=True,
        )
    ]
    return {
        "baseline_mean": fmean(baseline_values),
        "candidate_mean": fmean(candidate_values),
        "mean_delta": fmean(deltas),
        "wins": sum(delta > 0 for delta in deltas),
        "losses": sum(delta < 0 for delta in deltas),
        "ties": sum(delta == 0 for delta in deltas),
    }


def analyze_pair(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    baseline_run: str,
    candidate_run: str,
    bootstrap_samples: int = 100_000,
    bootstrap_seed: int = 20260824,
) -> dict[str, Any]:
    baseline_by_id = {str(row["sample_id"]): row for row in baseline_rows}
    candidate_by_id = {str(row["sample_id"]): row for row in candidate_rows}
    if set(baseline_by_id) != set(candidate_by_id):
        missing_candidate = sorted(set(baseline_by_id) - set(candidate_by_id))
        missing_baseline = sorted(set(candidate_by_id) - set(baseline_by_id))
        raise ValueError(
            "run case sets differ: "
            f"missing_candidate={missing_candidate[:5]} "
            f"missing_baseline={missing_baseline[:5]}"
        )
    rows = [
        (baseline_by_id[case_id], candidate_by_id[case_id])
        for case_id in sorted(baseline_by_id)
    ]
    metric_summaries = {
        metric: {
            **_metric_summary(rows, metric),
            "repo_cluster_bootstrap_95_ci": _cluster_bootstrap(
                rows,
                metric,
                samples=bootstrap_samples,
                seed=bootstrap_seed,
            ),
        }
        for metric in METRICS
    }
    baseline_acquired = {
        str(baseline["sample_id"])
        for baseline, _candidate in rows
        if float(baseline["metrics"]["Recall@20"]) > 0
    }
    candidate_acquired = {
        str(candidate["sample_id"])
        for _baseline, candidate in rows
        if float(candidate["metrics"]["Recall@20"]) > 0
    }
    recovered = len(candidate_acquired - baseline_acquired)
    lost = len(baseline_acquired - candidate_acquired)
    recovered_case_ids = sorted(candidate_acquired - baseline_acquired)
    lost_case_ids = sorted(baseline_acquired - candidate_acquired)

    exact_rankings = 0
    jaccards: list[float] = []
    for baseline, candidate in rows:
        baseline_top = list(baseline["top_files"])[:20]
        candidate_top = list(candidate["top_files"])[:20]
        exact_rankings += baseline_top == candidate_top
        baseline_set = set(baseline_top)
        candidate_set = set(candidate_top)
        union = baseline_set | candidate_set
        jaccards.append(
            len(baseline_set & candidate_set) / len(union) if union else 1.0
        )

    by_workflow: dict[str, dict[str, Any]] = {}
    workflows = sorted({str(baseline["task_type"]) for baseline, _ in rows})
    for workflow in workflows:
        workflow_rows = [
            pair for pair in rows if str(pair[0]["task_type"]) == workflow
        ]
        by_workflow[workflow] = {
            metric: {
                **_metric_summary(workflow_rows, metric),
                "n": len(workflow_rows),
            }
            for metric in METRICS
        }

    return {
        "baseline_run": baseline_run,
        "candidate_run": candidate_run,
        "cases": len(rows),
        "repositories": len({str(row[0]["repo"]) for row in rows}),
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": bootstrap_seed,
        "bootstrap_unit": "repository",
        "metrics": metric_summaries,
        "any_gold_at_20": {
            "metric": "Recall@20",
            "baseline_cases": len(baseline_acquired),
            "candidate_cases": len(candidate_acquired),
            "both": len(baseline_acquired & candidate_acquired),
            "neither": len(rows) - len(baseline_acquired | candidate_acquired),
            "recovered": recovered,
            "lost": lost,
            "recovered_case_ids": recovered_case_ids,
            "lost_case_ids": lost_case_ids,
            "mcnemar_exact_p": _mcnemar_exact_p(recovered, lost),
        },
        "ranking_agreement": {
            "exact_top20_rate": exact_rankings / len(rows),
            "mean_top20_set_jaccard": fmean(jaccards),
        },
        "by_workflow": by_workflow,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline-run", required=True)
    parser.add_argument("--candidate-run", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=100_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260824)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = analyze_pair(
        _read_jsonl(args.baseline),
        _read_jsonl(args.candidate),
        baseline_run=args.baseline_run,
        candidate_run=args.candidate_run,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
