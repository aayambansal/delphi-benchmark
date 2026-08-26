from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _module():
    import balanced_nia_docs_ablation

    return balanced_nia_docs_ablation


def test_schedule_balances_transform_positions_exactly() -> None:
    module = _module()
    case_ids = tuple(str(index) for index in range(10))

    schedule = module.build_schedule(case_ids, repeats=5)

    assert len(schedule) == 100
    assert [row["observation_index"] for row in schedule] == list(range(1, 101))
    assert sum(
        row["transform"] == "full" and row["position"] == 1 for row in schedule
    ) == 25
    assert sum(
        row["transform"] == "full" and row["position"] == 2 for row in schedule
    ) == 25
    assert sum(
        row["transform"] == "compact" and row["position"] == 1 for row in schedule
    ) == 25
    assert sum(
        row["transform"] == "compact" and row["position"] == 2 for row in schedule
    ) == 25
    for pair_index in range(50):
        pair = schedule[pair_index * 2 : pair_index * 2 + 2]
        assert {row["transform"] for row in pair} == {"full", "compact"}
        assert [row["position"] for row in pair] == [1, 2]


def test_request_url_preserves_v2_path() -> None:
    module = _module()

    assert module.REQUEST_URL == "https://apigcp.trynia.ai/v2/search"


def test_pin_queries_uses_recorded_compact_strings_and_exact_full_prompts() -> None:
    module = _module()
    cases = [
        {"case_id": "a", "prompt": "full prompt A"},
        {"case_id": "b", "prompt": "full prompt B"},
    ]
    compact_rows = [
        {"case_id": "a", "query": "compact A"},
        {"case_id": "b", "query": "compact B"},
        {"case_id": "a", "query": "compact A"},
        {"case_id": "b", "query": "compact B"},
    ]

    pinned = module.pin_queries(cases, compact_rows)

    assert pinned["a"]["full"]["query"] == "full prompt A"
    assert pinned["a"]["compact"]["query"] == "compact A"
    assert pinned["a"]["full"]["sha256"] == hashlib.sha256(
        b"full prompt A"
    ).hexdigest()
    assert pinned["a"]["compact"]["sha256"] == hashlib.sha256(
        b"compact A"
    ).hexdigest()


def test_pin_queries_rejects_inconsistent_recorded_compact_strings() -> None:
    module = _module()

    with pytest.raises(ValueError, match="inconsistent compact queries"):
        module.pin_queries(
            [{"case_id": "a", "prompt": "full"}],
            [
                {"case_id": "a", "query": "compact one"},
                {"case_id": "a", "query": "compact two"},
            ],
        )


def test_citation_identity_matches_historical_normalization() -> None:
    module = _module()

    assert (
        module.citation_identity(
            {
                "metadata": {
                    "file_path": "https://docs.example/api",
                    "start_line": 10,
                    "end_line": 20,
                }
            }
        )
        == "https://docs.example/api:10:20"
    )
    assert (
        module.citation_identity(
            {
                "metadata": {
                    "sourceURL": "https://docs.example/fallback",
                }
            }
        )
        == "https://docs.example/fallback::"
    )


def test_analysis_fails_closed_when_any_observation_failed() -> None:
    module = _module()
    raw = {
        "schedule": [
            {"observation_index": 1},
            {"observation_index": 2},
        ],
        "observations": [
            {"observation_index": 1, "status": "ok"},
            {
                "observation_index": 2,
                "status": "error",
                "technical_error": {"type": "http_500"},
            },
        ],
        "request_accounting": {
            "scheduled_observations": 2,
            "http_attempts": 2,
            "successful_observations": 1,
            "technical_failures": 1,
            "retry_count": 0,
        },
        "stop_reason": "completed_with_failures",
        "validity": {"final_split_inspected": False},
    }

    analysis = module.build_analysis(raw, bootstrap_samples=100)

    assert analysis["validity"]["valid"] is False
    assert analysis["validity"]["score_reportable"] is False
    assert analysis["aggregate_metrics"] is None
    assert analysis["technical_errors"] == [
        {
            "observation_index": 2,
            "technical_error": {"type": "http_500"},
        }
    ]


def test_case_cluster_bootstrap_is_seeded_and_case_clustered() -> None:
    module = _module()
    values = {"a": [1.0, 1.0], "b": [-1.0, -1.0]}

    first = module.case_cluster_bootstrap_ci(
        values,
        seed=20260824,
        samples=1000,
    )
    second = module.case_cluster_bootstrap_ci(
        values,
        seed=20260824,
        samples=1000,
    )

    assert first == second
    assert first == [-1.0, 1.0]
