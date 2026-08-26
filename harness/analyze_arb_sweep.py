from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from statistics import fmean
from typing import Any

from harness.analyze_arb_pair import _load_run, analyze_pair


def ranking_agreement(
    baseline: dict[str, list[str]],
    candidate: dict[str, list[str]],
    *,
    limit: int = 20,
) -> dict[str, float]:
    if not baseline or set(baseline) != set(candidate):
        raise ValueError("ranked runs must contain the same non-empty case set")
    exact = 0
    jaccards: list[float] = []
    for case_id in sorted(baseline):
        left = baseline[case_id][:limit]
        right = candidate[case_id][:limit]
        exact += left == right
        union = set(left) | set(right)
        jaccards.append(len(set(left) & set(right)) / len(union) if union else 1.0)
    return {
        f"exact_top{limit}_rate": exact / len(baseline),
        f"mean_top{limit}_set_jaccard": fmean(jaccards),
    }


def _load_rankings(
    connection: sqlite3.Connection,
    run_id: str,
) -> dict[str, list[str]]:
    rows = connection.execute(
        "select case_id, ranked from cases where run_id = ? order by case_id",
        (run_id,),
    ).fetchall()
    return {
        str(case_id): [str(path) for path in json.loads(ranked_json)]
        for case_id, ranked_json in rows
    }


def parse_comparison(value: str) -> tuple[str, str, str]:
    label, separator, run_ids = value.partition("=")
    baseline, comma, candidate = run_ids.partition(",")
    if not separator or not comma or not label or not baseline or not candidate:
        raise argparse.ArgumentTypeError(
            "comparison must be LABEL=BASELINE_RUN,CANDIDATE_RUN"
        )
    return label, baseline, candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--comparison",
        action="append",
        type=parse_comparison,
        required=True,
    )
    parser.add_argument("--bootstrap-samples", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260824)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    try:
        comparisons: dict[str, Any] = {}
        for index, (label, baseline_run, candidate_run) in enumerate(
            args.comparison
        ):
            baseline_rows = _load_run(connection, baseline_run)
            candidate_rows = _load_run(connection, candidate_run)
            comparison = analyze_pair(
                baseline_rows,
                candidate_rows,
                bootstrap_samples=args.bootstrap_samples,
                seed=args.seed + index * 10,
            )
            comparison["baseline_run"] = baseline_run
            comparison["candidate_run"] = candidate_run
            comparison["repositories"] = len(
                {str(row["repo"]) for row in baseline_rows}
            )
            comparison["ranking_agreement"] = ranking_agreement(
                _load_rankings(connection, baseline_run),
                _load_rankings(connection, candidate_run),
            )
            comparisons[label] = comparison
    finally:
        connection.close()

    output = {
        "schema": "arb_sweep_analysis_v1",
        "comparisons": comparisons,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
