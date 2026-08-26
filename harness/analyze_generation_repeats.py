from __future__ import annotations

import argparse
import json
import random
from itertools import combinations
from pathlib import Path
from statistics import fmean
from typing import Any


def _index_run(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed = {str(row["case_id"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("each repeat must contain unique case IDs")
    return indexed


def _repeatability(
    runs: list[dict[str, dict[str, Any]]],
    case_ids: list[str],
) -> tuple[float, float]:
    exact_completion: list[float] = []
    pass_agreement: list[float] = []
    for left, right in combinations(runs, 2):
        for case_id in case_ids:
            exact_completion.append(
                float(
                    str(left[case_id].get("completion") or "")
                    == str(right[case_id].get("completion") or "")
                )
            )
            pass_agreement.append(
                float(
                    bool(left[case_id].get("passed"))
                    == bool(right[case_id].get("passed"))
                )
            )
    return fmean(exact_completion), fmean(pass_agreement)


def analyze_conditions(
    baseline_runs: list[list[dict[str, Any]]],
    condition_runs: list[list[dict[str, Any]]],
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260823,
) -> dict[str, Any]:
    if len(baseline_runs) != len(condition_runs):
        raise ValueError("conditions must contain the same number of repeats")
    if len(baseline_runs) < 2:
        raise ValueError("repeat analysis requires at least two repeats")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")

    baseline = [_index_run(rows) for rows in baseline_runs]
    condition = [_index_run(rows) for rows in condition_runs]
    expected_ids = set(baseline[0])
    if not expected_ids:
        raise ValueError("generation repeats must not be empty")
    if any(set(run) != expected_ids for run in (*baseline, *condition)):
        raise ValueError("all repeats must contain the same case IDs")
    case_ids = sorted(expected_ids)

    baseline_rates = [
        fmean(float(bool(row.get("passed"))) for row in run.values())
        for run in baseline
    ]
    condition_rates = [
        fmean(float(bool(row.get("passed"))) for row in run.values())
        for run in condition
    ]
    repeat_deltas = [
        condition_rate - baseline_rate
        for baseline_rate, condition_rate in zip(
            baseline_rates,
            condition_rates,
            strict=True,
        )
    ]

    paired_deltas = [
        int(bool(condition_run[case_id].get("passed")))
        - int(bool(baseline_run[case_id].get("passed")))
        for baseline_run, condition_run in zip(
            baseline,
            condition,
            strict=True,
        )
        for case_id in case_ids
    ]
    case_deltas = [
        fmean(
            int(bool(condition_run[case_id].get("passed")))
            - int(bool(baseline_run[case_id].get("passed")))
            for baseline_run, condition_run in zip(
                baseline,
                condition,
                strict=True,
            )
        )
        for case_id in case_ids
    ]
    rng = random.Random(seed)
    bootstrap = sorted(
        fmean(
            case_deltas[rng.randrange(len(case_deltas))]
            for _ in case_deltas
        )
        for _ in range(bootstrap_samples)
    )
    lower_index = int(0.025 * (bootstrap_samples - 1))
    upper_index = int(0.975 * (bootstrap_samples - 1))

    baseline_exact, baseline_pass_agreement = _repeatability(
        baseline,
        case_ids,
    )
    condition_exact, condition_pass_agreement = _repeatability(
        condition,
        case_ids,
    )
    return {
        "repeats": len(baseline),
        "cases": len(case_ids),
        "baseline_repeat_pass_rates": baseline_rates,
        "condition_repeat_pass_rates": condition_rates,
        "repeat_deltas": repeat_deltas,
        "baseline_mean_pass_rate": fmean(baseline_rates),
        "condition_mean_pass_rate": fmean(condition_rates),
        "mean_delta": fmean(repeat_deltas),
        "paired_wins": sum(delta > 0 for delta in paired_deltas),
        "paired_losses": sum(delta < 0 for delta in paired_deltas),
        "paired_ties": sum(delta == 0 for delta in paired_deltas),
        "baseline_exact_completion_rate": baseline_exact,
        "condition_exact_completion_rate": condition_exact,
        "baseline_pass_agreement_rate": baseline_pass_agreement,
        "condition_pass_agreement_rate": condition_pass_agreement,
        "case_cluster_bootstrap_95_ci": [
            bootstrap[lower_index],
            bootstrap[upper_index],
        ],
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": seed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, nargs="+", required=True)
    parser.add_argument("--condition", type=Path, nargs="+", required=True)
    parser.add_argument("--baseline-label", default="baseline")
    parser.add_argument("--condition-label", default="condition")
    parser.add_argument("--bootstrap-samples", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    summary = analyze_conditions(
        [load(path) for path in args.baseline],
        [load(path) for path in args.condition],
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    summary.update(
        {
            "baseline_label": args.baseline_label,
            "condition_label": args.condition_label,
            "baseline_files": [str(path) for path in args.baseline],
            "condition_files": [str(path) for path in args.condition],
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
