from __future__ import annotations

import pytest

from analyze_generation_repeats import analyze_conditions


def _row(case_id: str, passed: bool, completion: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "passed": passed,
        "completion": completion,
    }


def test_analyze_conditions_pairs_repeats_and_bootstraps_cases() -> None:
    baseline = [
        [_row("a", True, "x"), _row("b", False, "z")],
        [_row("a", False, "y"), _row("b", False, "z")],
    ]
    condition = [
        [_row("a", True, "q"), _row("b", True, "r")],
        [_row("a", True, "q"), _row("b", False, "s")],
    ]

    assert analyze_conditions(
        baseline,
        condition,
        bootstrap_samples=100,
        seed=7,
    ) == {
        "repeats": 2,
        "cases": 2,
        "baseline_repeat_pass_rates": [0.5, 0.0],
        "condition_repeat_pass_rates": [1.0, 0.5],
        "repeat_deltas": [0.5, 0.5],
        "baseline_mean_pass_rate": 0.25,
        "condition_mean_pass_rate": 0.75,
        "mean_delta": 0.5,
        "paired_wins": 2,
        "paired_losses": 0,
        "paired_ties": 2,
        "baseline_exact_completion_rate": 0.5,
        "condition_exact_completion_rate": 0.5,
        "baseline_pass_agreement_rate": 0.5,
        "condition_pass_agreement_rate": 0.5,
        "case_cluster_bootstrap_95_ci": [0.5, 0.5],
        "bootstrap_samples": 100,
        "bootstrap_seed": 7,
    }


def test_analyze_conditions_rejects_unpaired_repeats() -> None:
    with pytest.raises(ValueError, match="same number of repeats"):
        analyze_conditions(
            [[_row("a", True, "x")]],
            [
                [_row("a", True, "x")],
                [_row("a", True, "x")],
            ],
        )
