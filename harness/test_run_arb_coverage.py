from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import harness.run_arb as run_arb
from harness.run_arb import (
    DelphiEngine,
    _fuse_ranked_paths,
    benchmark_status,
    load_sources,
    missing_source_pairs,
    observed_retrieval_configs,
    resolve_fetch_limit,
    resolve_sample_paths,
)


def test_missing_source_pairs_normalizes_revisions_and_deduplicates():
    samples = [
        {"repo": "owner/covered", "base_commit": "ABC"},
        {"repo": "owner/missing", "base_commit": "DEF"},
        {"repo": "owner/missing", "base_commit": "DEF"},
    ]
    sources = {("owner/covered", "abc"): "source-id"}

    assert missing_source_pairs(samples, sources) == [("owner/missing", "def")]


def test_delphi_gold_searchability_reports_zero_chunk_gold_file() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert request.url.path == "/v1/files/get"
        assert payload["repo_id"] == "source-id"
        chunks = 2 if payload["file_path"] == "src/ok.py" else 0
        return httpx.Response(
            200,
            json={
                "success": True,
                "file_path": payload["file_path"],
                "indexed_chunks": chunks,
            },
        )

    samples = [
        {
            "id": "case-id",
            "repo": "owner/repo",
            "base_commit": "ABC",
            "gold": {
                "root_cause_files": ["src/ok.py", "src/missing.py"],
                "supporting_files": [],
            },
        }
    ]
    sources = {("owner/repo", "abc"): "source-id"}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    audit = getattr(
        run_arb,
        "delphi_gold_searchability_gaps",
        lambda *_args, **_kwargs: [],
    )
    try:
        gaps = audit(
            samples,
            sources,
            base_url="https://delphi.test",
            api_key="test-key",
            http=client,
        )
    finally:
        client.close()

    assert gaps == [
        {
            "case_id": "case-id",
            "repo": "owner/repo",
            "revision": "abc",
            "path": "src/missing.py",
            "reason": "no_indexed_chunks",
        }
    ]


def test_gold_searchability_preflight_writes_gaps_and_fails(tmp_path) -> None:
    output = tmp_path / "gold-gaps.json"
    gaps = [
        {
            "case_id": "case-id",
            "repo": "owner/repo",
            "revision": "abc",
            "path": "src/missing.py",
            "reason": "no_indexed_chunks",
        }
    ]
    enforce = getattr(
        run_arb,
        "enforce_gold_searchability",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(SystemExit, match="gold searchability preflight failed"):
        enforce(gaps, output=output)

    assert output.read_text() == (
        '{\n'
        '  "gaps": [\n'
        "    {\n"
        '      "case_id": "case-id",\n'
        '      "path": "src/missing.py",\n'
        '      "reason": "no_indexed_chunks",\n'
        '      "repo": "owner/repo",\n'
        '      "revision": "abc"\n'
        "    }\n"
        "  ],\n"
        '  "schema": "delphi_gold_searchability_gaps_v1"\n'
        "}\n"
    )


def test_run_gold_searchability_preflight_accepts_searchable_gold(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "file_path": payload["file_path"],
                "indexed_chunks": 1,
            },
        )

    samples = [
        {
            "id": "case-id",
            "repo": "owner/repo",
            "base_commit": "ABC",
            "gold": {"root_cause_files": ["src/ok.py"]},
        }
    ]
    output = tmp_path / "gold-gaps.json"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    preflight = getattr(
        run_arb,
        "run_gold_searchability_preflight",
        lambda *_args, **_kwargs: False,
    )
    try:
        verified = preflight(
            samples,
            {("owner/repo", "abc"): "source-id"},
            base_url="https://delphi.test",
            api_key="test-key",
            output=output,
            http=client,
        )
    finally:
        client.close()

    assert verified is True
    assert not output.exists()


def test_load_sources_ignores_nominally_indexed_empty_source(tmp_path) -> None:
    manifest = tmp_path / "sources.jsonl"
    manifest.write_text(
        "\n".join(
            [
                (
                    '{"repo":"owner/empty","revision":"ABC","status":"indexed",'
                    '"source_id":"empty","metadata":{"files_indexed":4,'
                    '"chunks_created":0}}'
                ),
                (
                    '{"repo":"owner/valid","revision":"DEF","status":"indexed",'
                    '"source_id":"valid","metadata":{"files_indexed":4,'
                    '"chunks_created":9}}'
                ),
                (
                    '{"repo":"owner/stale","revision":"GHI","status":"indexed",'
                    '"source_id":"old-valid","metadata":{"files_indexed":4,'
                    '"chunks_created":9}}'
                ),
                (
                    '{"repo":"owner/stale","revision":"GHI","status":"indexed",'
                    '"source_id":"empty-replacement","metadata":{"files_indexed":4,'
                    '"chunks_created":0}}'
                ),
            ]
        )
        + "\n"
    )

    assert load_sources(manifest) == {("owner/valid", "def"): "valid"}


def test_file_level_lexical_bm25_fusion_is_weighted_and_deterministic() -> None:
    bm25 = ["src/a.py", "src/b.py", "src/c.py"]
    lexical = ["src/c.py", "src/b.py", "src/d.py"]

    assert _fuse_ranked_paths(
        bm25,
        lexical,
        lexical_weight=0.7,
    ) == [
        "src/c.py",
        "src/b.py",
        "src/d.py",
        "src/a.py",
    ]
    assert _fuse_ranked_paths(bm25, lexical, lexical_weight=0.0) == bm25
    assert _fuse_ranked_paths(bm25, lexical, lexical_weight=1.0) == lexical


def test_delphi_engine_preserves_candidate_branch_provenance() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "search_time_ms": 12.5,
                "hybrid": {
                    "candidates": 12,
                    "sources_hit": {"vector": 10, "path_affinity": 2},
                },
                "query_compacted": True,
                "query_expanded": False,
                "retrieval_config": {
                    "vector_mode": "exact",
                    "hnsw_ef_search": 100,
                    "file_diverse_bm25": False,
                },
                "timing": {"embedding_ms": 3.0, "db_search_ms": 4.0},
                "warnings": [{"code": "example"}],
                "results": [
                    {
                        "file_path": "src/a.py",
                        "chunk_id": "chunk-a",
                        "relevance_score": 0.81,
                        "candidate_sources": {
                            "vector": 0.9,
                            "bm25": 0.4,
                        },
                    },
                ],
            },
        )

    engine = DelphiEngine(
        {("owner/repo", "abc"): "source-id"},
        base_url="https://delphi.test",
    )
    engine.http.close()
    engine.http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        observation = engine.search(
            {"repo": "owner/repo", "base_commit": "ABC"},
            "find implementation",
            limit=20,
        )
    finally:
        engine.http.close()

    assert observation["paths"] == ["src/a.py"]
    assert observation["meta"] == {
        "search_time_ms": 12.5,
        "hybrid": {
            "candidates": 12,
            "sources_hit": {"vector": 10, "path_affinity": 2},
        },
        "query_compacted": True,
        "query_expanded": False,
        "retrieval_config": {
            "vector_mode": "exact",
            "hnsw_ef_search": 100,
            "file_diverse_bm25": False,
        },
        "timing": {"embedding_ms": 3.0, "db_search_ms": 4.0},
        "warnings": [{"code": "example"}],
        "candidates": [
            {
                "path": "src/a.py",
                "chunk_id": "chunk-a",
                "relevance_score": 0.81,
                "candidate_sources": {
                    "vector": 0.9,
                    "bm25": 0.4,
                },
            },
        ],
    }


def test_delphi_engine_fails_on_serving_configuration_mismatch() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "retrieval_config": {
                    "vector_mode": "hnsw",
                    "hnsw_ef_search": 400,
                    "file_diverse_bm25": False,
                    "fusion_weights": {"file_bm25": 0.15},
                },
                "results": [{"file_path": "src/a.py"}],
            },
        )

    engine = DelphiEngine(
        {("owner/repo", "abc"): "source-id"},
        base_url="https://delphi.test",
        expected_retrieval_config={
            "vector_mode": "exact",
            "file_diverse_bm25": True,
            "fusion_weights": {"file_bm25": 0.15},
        },
    )
    engine.http.close()
    engine.http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        observation = engine.search(
            {"repo": "owner/repo", "base_commit": "ABC"},
            "find implementation",
            limit=20,
        )
    finally:
        engine.http.close()

    assert observation["status"] == "configuration_mismatch"
    assert observation["fatal"] is True
    assert observation["paths"] == []
    assert "file_diverse_bm25" in observation["error"]
    assert "vector_mode" in observation["error"]


def test_benchmark_status_fails_closed_on_technical_errors_or_skips() -> None:
    assert benchmark_status([{"status": "ok"}], []) == "done"
    assert benchmark_status([{"status": "ok"}, {"status": "error"}], []) == ("failed")
    assert benchmark_status([{"status": "ok"}], ["missing-case"]) == "failed"
    assert benchmark_status([], []) == "failed"


def test_explicit_sample_files_override_standard_workflow_paths() -> None:
    explicit = [Path("/corpus/development.jsonl")]

    assert (
        resolve_sample_paths(
            split="development",
            workflows="v2_code2test,v2_trace2code",
            explicit=explicit,
        )
        == explicit
    )


def test_fetch_limit_defaults_to_scored_limit_and_cannot_be_smaller() -> None:
    assert resolve_fetch_limit(None, scored_limit=20) == 20
    assert resolve_fetch_limit(100, scored_limit=20) == 100

    with pytest.raises(ValueError, match="at least the scored limit"):
        resolve_fetch_limit(10, scored_limit=20)


def test_observed_retrieval_configs_are_deduplicated_and_sorted() -> None:
    assert observed_retrieval_configs(
        [
            {"retrieval_config": {"vector_mode": "exact", "llm_seed": 1042}},
            {"retrieval_config": None},
            {"retrieval_config": {"llm_seed": 1042, "vector_mode": "exact"}},
            {"retrieval_config": {"vector_mode": "hnsw", "llm_seed": 1042}},
        ]
    ) == [
        {"llm_seed": 1042, "vector_mode": "exact"},
        {"llm_seed": 1042, "vector_mode": "hnsw"},
    ]
