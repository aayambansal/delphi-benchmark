from __future__ import annotations

import pytest

from analyze_docs_determinism import analyze_runs, item_identity


def test_analyze_runs_uses_paired_case_level_agreement() -> None:
    runs = [
        [
            {
                "case_id": "a",
                "context": "same",
                "status": "ok",
                "identifier_hit": True,
                "items": [{"raw_id": "chunk-a"}],
            },
            {
                "case_id": "b",
                "context": "first",
                "status": "ok",
                "identifier_hit": False,
                "items": [],
            },
        ],
        [
            {
                "case_id": "a",
                "context": "same",
                "status": "ok",
                "identifier_hit": False,
                "items": [{"raw_id": "chunk-a"}, {"raw_id": "chunk-b"}],
            },
            {
                "case_id": "b",
                "context": "second",
                "status": "error",
                "identifier_hit": False,
                "items": [],
            },
        ],
    ]

    assert analyze_runs(runs) == {
        "runs": 2,
        "cases": 2,
        "paired_case_comparisons": 2,
        "exact_context_rate": 0.5,
        "status_agreement_rate": 0.5,
        "identifier_hit_agreement_rate": 0.5,
        "mean_item_set_jaccard": 0.75,
        "run_identifier_hit_rates": [0.5, 0.0],
        "mean_identifier_hit_rate": 0.25,
        "min_identifier_hit_rate": 0.0,
        "max_identifier_hit_rate": 0.5,
    }


def test_analyze_runs_rejects_mismatched_case_sets() -> None:
    with pytest.raises(ValueError, match="same case IDs"):
        analyze_runs(
            [
                [{"case_id": "a"}],
                [{"case_id": "b"}],
            ]
        )


def test_item_identity_normalizes_nia_serialized_sources() -> None:
    item = {
        "raw_id": str(
            {
                "content": "retrieved text",
                "metadata": {
                    "file_path": "https://docs.example/api.html",
                    "start_line": 10,
                    "end_line": 20,
                    "score": 0.91,
                },
            }
        )
    }

    assert item_identity(item) == (
        "https://docs.example/api.html:10:20"
    )
