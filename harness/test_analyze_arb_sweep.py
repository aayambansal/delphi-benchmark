from __future__ import annotations

import pytest

from harness.analyze_arb_sweep import parse_comparison, ranking_agreement


def test_ranking_agreement_measures_order_and_set_overlap() -> None:
    result = ranking_agreement(
        {
            "a": ["one", "two"],
            "b": ["three", "four"],
        },
        {
            "a": ["one", "two"],
            "b": ["four", "five"],
        },
        limit=2,
    )

    assert result["exact_top2_rate"] == 0.5
    assert result["mean_top2_set_jaccard"] == pytest.approx((1 + 1 / 3) / 2)


def test_ranking_agreement_requires_paired_cases() -> None:
    with pytest.raises(ValueError, match="same non-empty case set"):
        ranking_agreement({"a": []}, {"b": []})


def test_parse_comparison() -> None:
    assert parse_comparison("candidate=base-run,new-run") == (
        "candidate",
        "base-run",
        "new-run",
    )

    with pytest.raises(Exception, match="comparison must be"):
        parse_comparison("not-valid")
