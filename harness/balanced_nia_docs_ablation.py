"""Bounded, order-balanced Nia documentation query-transform ablation.

This harness is intentionally development-only and refuses to overwrite a raw
artifact that already contains hosted attempts. It schedules exactly one HTTP
attempt for each observation and never retries.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import random
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROUND3 = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
ROUND2 = ROUND3.parent / "delphi-evaluation-2026-07-29-round2"
DEFAULT_RAW_PATH = (
    ROUND3 / "results" / "nia-accounting-balanced-full-compact-raw-20260824.json"
)
DEFAULT_ANALYSIS_PATH = (
    ROUND3
    / "results"
    / "nia-accounting-balanced-full-compact-analysis-20260824.json"
)
SAMPLE_PATH = ROUND3 / "samples" / "docs" / "determinism10.jsonl"
MANIFEST_PATH = ROUND3 / "samples" / "docs" / "determinism10-manifest.json"
SOURCE_MAP_PATH = ROUND2 / "artifacts" / "development" / "docs-source-map.json"
COMPACT_ARTIFACT_PATH = (
    ROUND3 / "results" / "nia-accounting-docs-compact-determinism-20260824.json"
)
FULL_AUDIT_PATH = (
    ROUND3 / "results" / "nia-accounting-docs-full-citation-audit-20260824.json"
)
PRIOR_ANALYSIS_PATH = (
    ROUND3 / "results" / "nia-accounting-docs-full-v-compact-analysis-20260824.json"
)
HISTORICAL_RUNNER_PATH = ROUND2 / "ds1000_harness" / "run_developer_retrieval.py"
FULL_DETAIL_PATHS = tuple(
    ROUND3 / "determinism" / "nia" / f"docs-full-r{repeat}-details.json"
    for repeat in range(1, 11)
)

BASE_URL = "https://apigcp.trynia.ai/v2"
ENDPOINT = "/search"
REQUEST_URL = f"{BASE_URL}{ENDPOINT}"
REPEATS = 5
EXPECTED_CASES = 10
EXPECTED_OBSERVATIONS = 100
CITATION_LIMIT = 5
CONTEXT_BUDGET = 8000
BOOTSTRAP_SEED = 20260824
BOOTSTRAP_SAMPLES = 100_000
REQUEST_CONFIGURATION = {
    "endpoint": "/v2/search",
    "mode": "query",
    "search_mode": "sources",
    "include_sources": True,
    "fast_mode": True,
    "skip_llm": False,
    "bypass_semantic_cache": True,
    "include_follow_ups": False,
    "max_tokens": 8000,
    "context_budget_tokens": 8000,
    "recorded_citation_limit": 5,
    "http_transport_retries": 0,
    "logical_retries": 0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(encoded)


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            values.append(value)
    return values


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_schedule(
    case_ids: Iterable[str],
    *,
    repeats: int = REPEATS,
) -> list[dict[str, Any]]:
    """Alternate AB/BA by case and round with exact aggregate balance."""

    ordered_case_ids = tuple(str(case_id) for case_id in case_ids)
    schedule: list[dict[str, Any]] = []
    observation_index = 0
    pair_index = 0
    for repeat in range(1, repeats + 1):
        for case_position, case_id in enumerate(ordered_case_ids, start=1):
            pair_index += 1
            transforms = (
                ("full", "compact")
                if ((repeat - 1) + (case_position - 1)) % 2 == 0
                else ("compact", "full")
            )
            order = "AB" if transforms == ("full", "compact") else "BA"
            for position, transform in enumerate(transforms, start=1):
                observation_index += 1
                schedule.append(
                    {
                        "observation_index": observation_index,
                        "pair_index": pair_index,
                        "repeat": repeat,
                        "case_position": case_position,
                        "case_id": case_id,
                        "transform": transform,
                        "order": order,
                        "position": position,
                    }
                )
    return schedule


def position_counts(schedule: Iterable[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[tuple[str, int]] = Counter(
        (str(row["transform"]), int(row["position"])) for row in schedule
    )
    order_counts: Counter[str] = Counter(str(row["order"]) for row in schedule)
    return {
        "full": {
            "first": counts[("full", 1)],
            "second": counts[("full", 2)],
        },
        "compact": {
            "first": counts[("compact", 1)],
            "second": counts[("compact", 2)],
        },
        "observation_order_labels": dict(sorted(order_counts.items())),
        "pair_order_counts": {
            order: count // 2 for order, count in sorted(order_counts.items())
        },
    }


def pin_queries(
    cases: Iterable[dict[str, Any]],
    compact_rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Pin full prompts and the exact compact strings in the completed artifact."""

    compact_by_case: dict[str, set[str]] = defaultdict(set)
    supplied_hashes: dict[str, set[str]] = defaultdict(set)
    for row in compact_rows:
        case_id = str(row.get("case_id"))
        query = row.get("query")
        if not isinstance(query, str):
            raise ValueError(f"compact row for case {case_id} has no string query")
        compact_by_case[case_id].add(query)
        supplied_hash = row.get("query_sha256")
        if supplied_hash is not None:
            supplied_hashes[case_id].add(str(supplied_hash))

    pinned: dict[str, dict[str, dict[str, Any]]] = {}
    for case in cases:
        case_id = str(case["case_id"])
        prompt = case.get("prompt")
        if not isinstance(prompt, str):
            raise ValueError(f"case {case_id} has no string prompt")
        compact_values = compact_by_case.get(case_id, set())
        if len(compact_values) != 1:
            raise ValueError(f"inconsistent compact queries for case {case_id}")
        compact_query = next(iter(compact_values))
        compact_hash = sha256_text(compact_query)
        if supplied_hashes.get(case_id) not in (None, set(), {compact_hash}):
            raise ValueError(f"recorded compact query hash mismatch for case {case_id}")
        pinned[case_id] = {
            "full": {
                "query": prompt,
                "sha256": sha256_text(prompt),
                "characters": len(prompt),
                "provenance": "exact sample prompt used by historical full arm",
            },
            "compact": {
                "query": compact_query,
                "sha256": compact_hash,
                "characters": len(compact_query),
                "provenance": "exact recorded compact artifact query string",
            },
        }
    extra = sorted(set(compact_by_case) - set(pinned))
    if extra:
        raise ValueError(f"unexpected compact artifact case IDs: {', '.join(extra)}")
    return pinned


def citation_identity(citation: Any) -> str:
    """Historical citation identity used by the completed Nia audits."""

    if isinstance(citation, str):
        return citation.strip()
    if not isinstance(citation, dict):
        return json.dumps(citation, sort_keys=True, default=str)
    metadata = (
        citation.get("metadata")
        if isinstance(citation.get("metadata"), dict)
        else {}
    )
    path = (
        citation.get("file_path")
        or citation.get("path")
        or citation.get("url")
        or metadata.get("file_path")
        or metadata.get("sourceURL")
        or metadata.get("source_url")
        or metadata.get("url")
    )
    start = metadata.get("start_line", citation.get("start_line", ""))
    end = metadata.get("end_line", citation.get("end_line", ""))
    if path:
        return f"{path}:{start}:{end}"
    return json.dumps(citation, sort_keys=True, default=str)


def set_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 1.0


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def distribution(values: Iterable[float]) -> dict[str, float | None]:
    materialized = [float(value) for value in values]
    if not materialized:
        return {
            "mean": None,
            "median": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    return {
        "mean": statistics.fmean(materialized),
        "median": statistics.median(materialized),
        "p95": percentile(materialized, 0.95),
        "min": min(materialized),
        "max": max(materialized),
    }


def case_cluster_bootstrap_ci(
    values_by_case: dict[str, list[float]],
    *,
    seed: int = BOOTSTRAP_SEED,
    samples: int = BOOTSTRAP_SAMPLES,
) -> list[float]:
    """Percentile CI from resampling cases and retaining all repeats per case."""

    if not values_by_case:
        raise ValueError("case-cluster bootstrap requires at least one case")
    if samples < 1:
        raise ValueError("bootstrap samples must be positive")
    case_ids = sorted(values_by_case)
    if any(not values_by_case[case_id] for case_id in case_ids):
        raise ValueError("every bootstrap case cluster must be non-empty")
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        sampled_case_ids = [
            case_ids[generator.randrange(len(case_ids))]
            for _ in range(len(case_ids))
        ]
        sampled_values = [
            float(value)
            for case_id in sampled_case_ids
            for value in values_by_case[case_id]
        ]
        estimates.append(statistics.fmean(sampled_values))
    low = percentile(estimates, 0.025)
    high = percentile(estimates, 0.975)
    assert low is not None and high is not None
    return [low, high]


def _extract_cases(
    sample_rows: list[dict[str, Any]],
    case_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in sample_rows:
        metadata = row.get("metadata") or {}
        case_id = str(metadata.get("problem_id"))
        by_id[case_id] = row
    if set(by_id) != set(case_ids) or len(sample_rows) != len(case_ids):
        raise ValueError("determinism sample must contain exactly the manifest cases")

    cases: list[dict[str, Any]] = []
    for case_id in case_ids:
        row = by_id[case_id]
        metadata = row.get("metadata") or {}
        docs = row.get("docs") or []
        identifiers = tuple(
            dict.fromkeys(
                str(doc.get("function") or doc.get("title") or "").strip()
                for doc in docs
                if str(doc.get("function") or doc.get("title") or "").strip()
            )
        )
        if not identifiers:
            raise ValueError(f"case {case_id} has no gold identifiers")
        cases.append(
            {
                "case_id": case_id,
                "library": str(metadata.get("library") or ""),
                "prompt": str(row.get("prompt") or ""),
                "gold_identifiers": list(identifiers),
            }
        )
    return cases


def _flatten_compact_rows(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    runs = artifact.get("runs")
    if not isinstance(runs, list) or len(runs) != 10:
        raise ValueError("completed compact artifact must contain 10 runs")
    rows: list[dict[str, Any]] = []
    for run in runs:
        run_rows = run.get("rows") if isinstance(run, dict) else None
        if not isinstance(run_rows, list) or len(run_rows) != EXPECTED_CASES:
            raise ValueError("every completed compact run must contain 10 rows")
        rows.extend(run_rows)
    if len(rows) != 100 or any(row.get("status") != "ok" for row in rows):
        raise ValueError("completed compact artifact is incomplete or has failures")
    return rows


def _relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def prepare_inputs() -> dict[str, Any]:
    """Load only the predeclared development files and pin the experiment."""

    required_paths = (
        SAMPLE_PATH,
        MANIFEST_PATH,
        SOURCE_MAP_PATH,
        COMPACT_ARTIFACT_PATH,
        FULL_AUDIT_PATH,
        PRIOR_ANALYSIS_PATH,
        HISTORICAL_RUNNER_PATH,
        *FULL_DETAIL_PATHS,
    )
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise ValueError(f"required input files missing: {', '.join(missing)}")

    manifest = read_json(MANIFEST_PATH)
    if not isinstance(manifest, dict):
        raise ValueError("determinism manifest is not an object")
    case_ids = tuple(str(value) for value in manifest.get("case_ids") or ())
    if len(case_ids) != EXPECTED_CASES or len(set(case_ids)) != EXPECTED_CASES:
        raise ValueError("manifest must contain exactly 10 distinct case IDs")

    cases = _extract_cases(read_jsonl(SAMPLE_PATH), case_ids)
    expected_libraries = Counter(
        {str(key): int(value) for key, value in (manifest.get("libraries") or {}).items()}
    )
    actual_libraries = Counter(str(case["library"]) for case in cases)
    if actual_libraries != expected_libraries:
        raise ValueError("sample library counts do not match manifest")

    source_map = read_json(SOURCE_MAP_PATH)
    nia_sources = source_map.get("nia") if isinstance(source_map, dict) else None
    if not isinstance(nia_sources, dict):
        raise ValueError("development source map has no Nia selector mapping")
    source_selectors: dict[str, str] = {}
    for library in sorted(actual_libraries):
        source_id = nia_sources.get(library)
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(f"missing predeclared Nia source ID for {library}")
        try:
            uuid.UUID(source_id)
        except ValueError as exc:
            raise ValueError(f"invalid Nia source ID for {library}") from exc
        source_selectors[library] = source_id

    compact_artifact = read_json(COMPACT_ARTIFACT_PATH)
    if not isinstance(compact_artifact, dict):
        raise ValueError("compact artifact is not an object")
    compact_rows = _flatten_compact_rows(compact_artifact)
    query_pins = pin_queries(cases, compact_rows)
    compact_counts = Counter(str(row["case_id"]) for row in compact_rows)
    if any(compact_counts[case_id] != 10 for case_id in case_ids):
        raise ValueError("compact artifact must record each case exactly 10 times")

    for detail_path in FULL_DETAIL_PATHS:
        details = read_json(detail_path)
        if not isinstance(details, list) or len(details) != EXPECTED_CASES:
            raise ValueError(f"{detail_path} is not a complete 10-case full run")
        detail_ids = {str(row.get("case_id")) for row in details}
        if detail_ids != set(case_ids) or any(row.get("status") != "ok" for row in details):
            raise ValueError(f"{detail_path} is incomplete or has failures")

    schedule = build_schedule(case_ids, repeats=REPEATS)
    if len(schedule) != EXPECTED_OBSERVATIONS:
        raise AssertionError("balanced schedule is not exactly 100 observations")
    counts = position_counts(schedule)
    if any(
        counts[transform][position] != 25
        for transform in ("full", "compact")
        for position in ("first", "second")
    ):
        raise AssertionError("balanced schedule does not have exact 25/25 positions")

    query_hash_manifest = {
        case_id: {
            transform: query_pins[case_id][transform]["sha256"]
            for transform in ("full", "compact")
        }
        for case_id in case_ids
    }
    provenance_files = (
        SAMPLE_PATH,
        MANIFEST_PATH,
        SOURCE_MAP_PATH,
        COMPACT_ARTIFACT_PATH,
        FULL_AUDIT_PATH,
        PRIOR_ANALYSIS_PATH,
        HISTORICAL_RUNNER_PATH,
        *FULL_DETAIL_PATHS,
    )
    return {
        "manifest": manifest,
        "case_ids": case_ids,
        "cases": cases,
        "cases_by_id": {str(case["case_id"]): case for case in cases},
        "source_selectors": source_selectors,
        "source_selectors_sha256": canonical_json_sha256(source_selectors),
        "query_pins": query_pins,
        "query_hash_manifest_sha256": canonical_json_sha256(query_hash_manifest),
        "schedule": schedule,
        "schedule_sha256": canonical_json_sha256(schedule),
        "position_counts": counts,
        "provenance": {
            "files": [
                {"path": _relative(path), "sha256": sha256_file(path)}
                for path in provenance_files
            ],
            "request_configuration_sha256": canonical_json_sha256(
                REQUEST_CONFIGURATION
            ),
            "source_selectors_sha256": canonical_json_sha256(source_selectors),
            "query_hash_manifest_sha256": canonical_json_sha256(
                query_hash_manifest
            ),
            "schedule_sha256": canonical_json_sha256(schedule),
            "harness": {
                "path": _relative(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
        },
    }


def _technical_errors(observations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "observation_index": row.get("observation_index"),
            "technical_error": row.get("technical_error"),
        }
        for row in observations
        if row.get("status") != "ok"
    ]


def _request_accounting(
    schedule: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> dict[str, int]:
    successful = sum(row.get("status") == "ok" for row in observations)
    failures = len(observations) - successful
    return {
        "scheduled_observations": len(schedule),
        "dispatched_observations": len(observations),
        "outbound_hosted_v2_search_requests": len(observations),
        "http_attempts": len(observations),
        "successful_observations": successful,
        "technical_failures": failures,
        "retry_count": 0,
        "other_hosted_requests": 0,
    }


def _raw_valid(raw: dict[str, Any]) -> bool:
    accounting = raw.get("request_accounting") or {}
    observations = raw.get("observations") or []
    schedule = raw.get("schedule") or []
    return (
        len(schedule) == EXPECTED_OBSERVATIONS
        and len(observations) == EXPECTED_OBSERVATIONS
        and accounting.get("scheduled_observations") == EXPECTED_OBSERVATIONS
        and accounting.get("http_attempts") == EXPECTED_OBSERVATIONS
        and accounting.get("successful_observations") == EXPECTED_OBSERVATIONS
        and accounting.get("technical_failures") == 0
        and accounting.get("retry_count") == 0
        and all(row.get("status") == "ok" for row in observations)
        and raw.get("stop_reason") == "completed"
        and (raw.get("validity") or {}).get("final_split_inspected") is False
    )


def _comparison(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_citations = list(left.get("citation_identities") or [])
    right_citations = list(right.get("citation_identities") or [])
    return {
        "synthesized_context_exact": left.get("synthesized_content")
        == right.get("synthesized_content"),
        "identifier_hit_agreement": bool(left.get("identifier_hit"))
        == bool(right.get("identifier_hit")),
        "synthesis_identifier_hit_agreement": bool(
            left.get("synthesis_identifier_hit")
        )
        == bool(right.get("synthesis_identifier_hit")),
        "citation_ordered_exact": left_citations == right_citations,
        "citation_set_exact": set(left_citations) == set(right_citations),
        "citation_top1_exact": left_citations[:1] == right_citations[:1],
        "citation_set_jaccard": set_jaccard(left_citations, right_citations),
    }


def _rate(rows: Iterable[dict[str, Any]], key: str) -> float:
    materialized = list(rows)
    return statistics.fmean(float(bool(row[key])) for row in materialized)


def _transform_metrics(
    observations: list[dict[str, Any]],
    transform: str,
) -> dict[str, Any]:
    rows = [row for row in observations if row["transform"] == transform]
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[str(row["case_id"])].append(row)

    comparisons: list[dict[str, Any]] = []
    for case_rows in by_case.values():
        ordered = sorted(case_rows, key=lambda row: int(row["repeat"]))
        for left, right in itertools.combinations(ordered, 2):
            comparisons.append(_comparison(left, right))

    return {
        "label": "retrieval+synthesis",
        "observation_count": len(rows),
        "case_count": len(by_case),
        "repeats_per_case": sorted({len(case_rows) for case_rows in by_case.values()}),
        "quality": {
            "identifier_hit_rate": _rate(rows, "identifier_hit"),
            "identifier_hit_label": "packed retrieval+synthesis context",
            "synthesis_identifier_hit_rate": _rate(
                rows, "synthesis_identifier_hit"
            ),
            "synthesis_identifier_hit_label": "provider synthesized content only",
        },
        "determinism": {
            "paired_within_transform_case_repeat_comparisons": len(comparisons),
            "exact_synthesized_context_rate": _rate(
                comparisons, "synthesized_context_exact"
            ),
            "identifier_hit_agreement_rate": _rate(
                comparisons, "identifier_hit_agreement"
            ),
            "synthesis_identifier_hit_agreement_rate": _rate(
                comparisons, "synthesis_identifier_hit_agreement"
            ),
            "citation_ordered_exact_rate": _rate(
                comparisons, "citation_ordered_exact"
            ),
            "citation_set_exact_rate": _rate(comparisons, "citation_set_exact"),
            "citation_top1_exact_rate": _rate(
                comparisons, "citation_top1_exact"
            ),
            "citation_set_mean_jaccard": statistics.fmean(
                float(row["citation_set_jaccard"]) for row in comparisons
            ),
        },
        "context_tokens": distribution(row["context_tokens"] for row in rows),
        "latency_ms": distribution(row["latency_ms"] for row in rows),
        "per_case": [
            {
                "case_id": case_id,
                "library": case_rows[0]["library"],
                "identifier_hit_rate": _rate(case_rows, "identifier_hit"),
                "synthesis_identifier_hit_rate": _rate(
                    case_rows, "synthesis_identifier_hit"
                ),
                "mean_context_tokens": statistics.fmean(
                    float(row["context_tokens"]) for row in case_rows
                ),
                "mean_latency_ms": statistics.fmean(
                    float(row["latency_ms"]) for row in case_rows
                ),
            }
            for case_id, case_rows in sorted(by_case.items())
        ],
    }


def _paired_metrics(
    observations: list[dict[str, Any]],
    *,
    bootstrap_seed: int,
    bootstrap_samples: int,
) -> dict[str, Any]:
    grouped: dict[tuple[int, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in observations:
        grouped[(int(row["repeat"]), str(row["case_id"]))][
            str(row["transform"])
        ] = row

    pair_rows: list[dict[str, Any]] = []
    for (repeat, case_id), transforms in sorted(grouped.items()):
        if set(transforms) != {"full", "compact"}:
            raise ValueError(f"missing paired transform for case {case_id} repeat {repeat}")
        full = transforms["full"]
        compact = transforms["compact"]
        citation = _comparison(full, compact)
        pair_rows.append(
            {
                "repeat": repeat,
                "case_id": case_id,
                "library": full["library"],
                "order": full["order"],
                "identifier_hit": {
                    "full": bool(full["identifier_hit"]),
                    "compact": bool(compact["identifier_hit"]),
                    "compact_minus_full": int(bool(compact["identifier_hit"]))
                    - int(bool(full["identifier_hit"])),
                },
                "synthesis_identifier_hit": {
                    "full": bool(full["synthesis_identifier_hit"]),
                    "compact": bool(compact["synthesis_identifier_hit"]),
                    "compact_minus_full": int(
                        bool(compact["synthesis_identifier_hit"])
                    )
                    - int(bool(full["synthesis_identifier_hit"])),
                },
                "context_tokens": {
                    "full": int(full["context_tokens"]),
                    "compact": int(compact["context_tokens"]),
                    "compact_minus_full": int(compact["context_tokens"])
                    - int(full["context_tokens"]),
                },
                "latency_ms": {
                    "full": float(full["latency_ms"]),
                    "compact": float(compact["latency_ms"]),
                    "compact_minus_full": float(compact["latency_ms"])
                    - float(full["latency_ms"]),
                },
                "cross_transform": citation,
            }
        )

    delta_keys = {
        "identifier_hit": [
            float(row["identifier_hit"]["compact_minus_full"]) for row in pair_rows
        ],
        "synthesis_identifier_hit": [
            float(row["synthesis_identifier_hit"]["compact_minus_full"])
            for row in pair_rows
        ],
        "context_tokens": [
            float(row["context_tokens"]["compact_minus_full"]) for row in pair_rows
        ],
        "latency_ms": [
            float(row["latency_ms"]["compact_minus_full"]) for row in pair_rows
        ],
        "citation_set_jaccard": [
            float(row["cross_transform"]["citation_set_jaccard"])
            for row in pair_rows
        ],
    }
    clustered: dict[str, dict[str, list[float]]] = {}
    for metric in delta_keys:
        clustered[metric] = defaultdict(list)
    for row in pair_rows:
        case_id = str(row["case_id"])
        clustered["identifier_hit"][case_id].append(
            float(row["identifier_hit"]["compact_minus_full"])
        )
        clustered["synthesis_identifier_hit"][case_id].append(
            float(row["synthesis_identifier_hit"]["compact_minus_full"])
        )
        clustered["context_tokens"][case_id].append(
            float(row["context_tokens"]["compact_minus_full"])
        )
        clustered["latency_ms"][case_id].append(
            float(row["latency_ms"]["compact_minus_full"])
        )
        clustered["citation_set_jaccard"][case_id].append(
            float(row["cross_transform"]["citation_set_jaccard"])
        )

    per_case: list[dict[str, Any]] = []
    for case_id in sorted({str(row["case_id"]) for row in pair_rows}):
        case_rows = [row for row in pair_rows if str(row["case_id"]) == case_id]
        per_case.append(
            {
                "case_id": case_id,
                "library": case_rows[0]["library"],
                "paired_repeats": len(case_rows),
                "mean_compact_minus_full_identifier_hit": statistics.fmean(
                    float(row["identifier_hit"]["compact_minus_full"])
                    for row in case_rows
                ),
                "mean_compact_minus_full_synthesis_identifier_hit": statistics.fmean(
                    float(row["synthesis_identifier_hit"]["compact_minus_full"])
                    for row in case_rows
                ),
                "mean_compact_minus_full_context_tokens": statistics.fmean(
                    float(row["context_tokens"]["compact_minus_full"])
                    for row in case_rows
                ),
                "mean_compact_minus_full_latency_ms": statistics.fmean(
                    float(row["latency_ms"]["compact_minus_full"])
                    for row in case_rows
                ),
                "cross_transform_citation_set_mean_jaccard": statistics.fmean(
                    float(row["cross_transform"]["citation_set_jaccard"])
                    for row in case_rows
                ),
            }
        )

    cross = [row["cross_transform"] for row in pair_rows]
    return {
        "delta_direction": "compact_minus_full",
        "paired_case_repeat_count": len(pair_rows),
        "means": {
            metric: statistics.fmean(values) for metric, values in delta_keys.items()
        },
        "case_cluster_bootstrap_95_ci": {
            metric: case_cluster_bootstrap_ci(
                dict(values_by_case),
                seed=bootstrap_seed,
                samples=bootstrap_samples,
            )
            for metric, values_by_case in clustered.items()
        },
        "bootstrap": {
            "unit": "case",
            "case_count": len(clustered["identifier_hit"]),
            "repeats_retained_per_sampled_case": REPEATS,
            "samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "interval": "percentile",
        },
        "cross_transform_citation_overlap": {
            "label": "retrieval citations, matched within case and repeat",
            "comparisons": len(cross),
            "citation_ordered_exact_rate": _rate(
                cross, "citation_ordered_exact"
            ),
            "citation_set_exact_rate": _rate(cross, "citation_set_exact"),
            "citation_top1_exact_rate": _rate(cross, "citation_top1_exact"),
            "citation_set_mean_jaccard": statistics.fmean(
                float(row["citation_set_jaccard"]) for row in cross
            ),
        },
        "cross_transform_exact_synthesized_context_rate": _rate(
            cross, "synthesized_context_exact"
        ),
        "per_case": per_case,
        "paired_case_repeat_deltas": pair_rows,
    }


def build_analysis(
    raw: dict[str, Any],
    *,
    bootstrap_seed: int = BOOTSTRAP_SEED,
    bootstrap_samples: int = BOOTSTRAP_SAMPLES,
) -> dict[str, Any]:
    """Build aggregate metrics only for a complete, all-successful raw run."""

    observations = list(raw.get("observations") or [])
    valid = _raw_valid(raw)
    analysis: dict[str, Any] = {
        "schema": "nia_accounting_balanced_full_compact_analysis_v1",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "corpus": raw.get("corpus"),
        "provenance": raw.get("provenance"),
        "source_selectors": raw.get("source_selectors"),
        "query_pins": raw.get("query_pins"),
        "request_configuration": raw.get("request_configuration"),
        "schedule_design": raw.get("schedule_design"),
        "request_accounting": raw.get("request_accounting"),
        "technical_errors": _technical_errors(observations),
        "stop_reason": raw.get("stop_reason"),
        "metric_definitions": {
            "identifier_hit": (
                "any canonical identifier substring in the packed "
                "retrieval+synthesis context"
            ),
            "synthesis_identifier_hit": (
                "any canonical identifier substring in provider synthesized "
                "content only"
            ),
            "exact_synthesized_context": (
                "byte-for-byte Python string equality of provider content"
            ),
            "citation_identity": (
                "file_path_or_source_url:start_line:end_line over the first "
                "five recorded citations"
            ),
            "citation_metrics": "retrieval labels only",
            "context_tokens": (
                "cl100k_base tokens in historical packed retrieval+synthesis "
                "context, capped at 8000"
            ),
            "latency_ms": "single full retrieval+synthesis HTTP attempt wall time",
        },
        "validity": {
            "valid": valid,
            "score_reportable": valid,
            "partial_scores_reported": False,
            "final_split_inspected": False,
            "reason": (
                "all 100 scheduled observations completed successfully with "
                "exactly one HTTP attempt each"
                if valid
                else "aggregate metrics withheld because the 100-observation "
                "all-success validity gate was not met"
            ),
        },
        "aggregate_metrics": None,
    }
    if not valid:
        return analysis

    analysis["aggregate_metrics"] = {
        "per_transform": {
            transform: _transform_metrics(observations, transform)
            for transform in ("full", "compact")
        },
        "paired": _paired_metrics(
            observations,
            bootstrap_seed=bootstrap_seed,
            bootstrap_samples=bootstrap_samples,
        ),
    }
    return analysis


def _initial_raw(prepared: dict[str, Any], credential_fingerprint: str) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema": "nia_accounting_balanced_full_compact_raw_v1",
        "created_at": now,
        "updated_at": now,
        "corpus": {
            "track": "Nia documentation query-transform ablation",
            "split": "development",
            "sample_file": _relative(SAMPLE_PATH),
            "sample_manifest": _relative(MANIFEST_PATH),
            "case_ids": list(prepared["case_ids"]),
            "case_count": EXPECTED_CASES,
            "repeats": REPEATS,
            "transforms": ["full", "compact"],
            "intended_observations": EXPECTED_OBSERVATIONS,
            "final_split_inspected": False,
        },
        "provenance": prepared["provenance"],
        "credential_scope_fingerprint_sha256_12": credential_fingerprint,
        "source_selectors": {
            "selection": "predeclared per-library Nia documentation source IDs",
            "mapping": prepared["source_selectors"],
            "sha256": prepared["source_selectors_sha256"],
            "hosted_source_mutations": 0,
            "hosted_source_inventory_requests": 0,
        },
        "query_pins": {
            "cases": prepared["query_pins"],
            "hash_manifest_sha256": prepared["query_hash_manifest_sha256"],
            "full_definition": "exact development sample prompt",
            "compact_definition": (
                "exact query strings already recorded in the completed compact "
                "artifact"
            ),
        },
        "request_configuration": {
            **REQUEST_CONFIGURATION,
            "base_url": BASE_URL,
            "one_request_at_a_time": True,
            "retry_policy": "none; one HTTP attempt per scheduled observation",
        },
        "schedule_design": {
            "strategy": (
                "alternate full/compact and compact/full by case and round "
                "parity; sequential dispatch"
            ),
            "position_counts": prepared["position_counts"],
            "schedule_sha256": prepared["schedule_sha256"],
        },
        "schedule": prepared["schedule"],
        "observations": [],
        "technical_errors": [],
        "request_accounting": {
            "scheduled_observations": EXPECTED_OBSERVATIONS,
            "dispatched_observations": 0,
            "outbound_hosted_v2_search_requests": 0,
            "http_attempts": 0,
            "successful_observations": 0,
            "technical_failures": 0,
            "retry_count": 0,
            "other_hosted_requests": 0,
        },
        "validity": {
            "status": "running",
            "valid": False,
            "score_reportable": False,
            "partial_scores_reported": False,
            "final_split_inspected": False,
            "reason": "run in progress; aggregate metrics withheld",
        },
        "stop_reason": "running",
    }


def _safe_error_text(value: object, limit: int = 4000) -> str:
    return str(value).replace(os.environ.get("NIA_API_KEY", ""), "[REDACTED]")[:limit]


def _request_observation(
    client: Any,
    scheduled: dict[str, Any],
    prepared: dict[str, Any],
) -> dict[str, Any]:
    case_id = str(scheduled["case_id"])
    transform = str(scheduled["transform"])
    case = prepared["cases_by_id"][case_id]
    query_pin = prepared["query_pins"][case_id][transform]
    source_id = prepared["source_selectors"][case["library"]]
    request_body = {
        "mode": "query",
        "messages": [{"role": "user", "content": query_pin["query"]}],
        "data_sources": [source_id],
        "search_mode": "sources",
        "include_sources": True,
        "fast_mode": True,
        "skip_llm": False,
        "max_tokens": 8000,
        "bypass_semantic_cache": True,
        "include_follow_ups": False,
    }
    base = {
        **scheduled,
        "library": case["library"],
        "query": query_pin["query"],
        "query_sha256": query_pin["sha256"],
        "source_id": source_id,
        "request_body_sha256": canonical_json_sha256(request_body),
        "request_label": "query/sources/fast/retrieval+synthesis",
        "synthesis_involved": True,
        "http_attempts": 1,
        "retry_count": 0,
    }
    started = time.perf_counter()
    try:
        response = client.post(REQUEST_URL, json=request_body)
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            **base,
            "status": "error",
            "latency_ms": latency_ms,
            "http_status": None,
            "technical_error": {
                "phase": "http_request",
                "type": type(exc).__name__,
                "message": _safe_error_text(exc),
            },
        }

    latency_ms = (time.perf_counter() - started) * 1000
    if response.status_code >= 400:
        return {
            **base,
            "status": "error",
            "latency_ms": latency_ms,
            "http_status": response.status_code,
            "technical_error": {
                "phase": "http_response",
                "type": f"http_{response.status_code}",
                "response_text": _safe_error_text(response.text),
            },
        }
    try:
        payload = response.json()
    except ValueError as exc:
        return {
            **base,
            "status": "error",
            "latency_ms": latency_ms,
            "http_status": response.status_code,
            "technical_error": {
                "phase": "response_decode",
                "type": type(exc).__name__,
                "message": _safe_error_text(exc),
                "response_text": _safe_error_text(response.text),
            },
        }
    if not isinstance(payload, dict):
        return {
            **base,
            "status": "error",
            "latency_ms": latency_ms,
            "http_status": response.status_code,
            "technical_error": {
                "phase": "response_validation",
                "type": "non_object_response",
                "response_type": type(payload).__name__,
            },
        }

    synthesized_content = payload.get("content")
    citations = payload.get("sources")
    if not isinstance(synthesized_content, str) or not synthesized_content.strip():
        return {
            **base,
            "status": "error",
            "latency_ms": latency_ms,
            "http_status": response.status_code,
            "technical_error": {
                "phase": "response_validation",
                "type": "empty_synthesized_content",
                "retrieval_log_id": payload.get("retrieval_log_id"),
            },
        }
    if not isinstance(citations, list) or not citations:
        return {
            **base,
            "status": "error",
            "latency_ms": latency_ms,
            "http_status": response.status_code,
            "technical_error": {
                "phase": "response_validation",
                "type": "empty_or_invalid_citations",
                "retrieval_log_id": payload.get("retrieval_log_id"),
            },
        }

    sys.path.insert(0, str(ROUND2))
    from ds1000_harness.developer import identifier_hit, pack_context
    from ds1000_harness.models import RetrievedItem

    recorded_citations = citations[:CITATION_LIMIT]
    first_path = str(recorded_citations[0])
    historical_item = RetrievedItem(
        path=first_path,
        content=synthesized_content,
        score=None,
        rank=1,
        raw_id=first_path,
    )
    packed_context, context_tokens = pack_context(
        (historical_item,),
        token_budget=CONTEXT_BUDGET,
    )
    return {
        **base,
        "status": "ok",
        "latency_ms": latency_ms,
        "http_status": response.status_code,
        "retrieval_log_id": payload.get("retrieval_log_id"),
        "result_mode": "synthesized_answer",
        "synthesized_content": synthesized_content,
        "packed_retrieval_plus_synthesis_context": packed_context,
        "context_tokens": context_tokens,
        "identifier_hit": identifier_hit(
            packed_context,
            tuple(case["gold_identifiers"]),
        ),
        "synthesis_identifier_hit": identifier_hit(
            synthesized_content,
            tuple(case["gold_identifiers"]),
        ),
        "gold_identifiers": case["gold_identifiers"],
        "provider_source_count": len(citations),
        "recorded_citations": recorded_citations,
        "citation_identities": [
            citation_identity(citation) for citation in recorded_citations
        ],
    }


def run_experiment(
    prepared: dict[str, Any],
    *,
    api_key: str,
    raw_path: Path,
    analysis_path: Path,
    bootstrap_seed: int,
    bootstrap_samples: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if raw_path.exists():
        existing = read_json(raw_path)
        attempts = int((existing.get("request_accounting") or {}).get("http_attempts", 0))
        raise RuntimeError(
            f"refusing to overwrite existing raw artifact with {attempts} attempts: "
            f"{raw_path}"
        )
    if analysis_path.exists():
        raise RuntimeError(f"refusing to overwrite existing analysis: {analysis_path}")

    raw = _initial_raw(prepared, sha256_text(api_key)[:12])
    write_json_atomic(raw_path, raw)

    import httpx

    transport = httpx.HTTPTransport(retries=0)
    fatal_stop: str | None = None
    with httpx.Client(
        base_url=BASE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=httpx.Timeout(60.0, connect=20.0),
        transport=transport,
        follow_redirects=False,
    ) as client:
        for scheduled in prepared["schedule"]:
            observation = _request_observation(client, scheduled, prepared)
            raw["observations"].append(observation)
            if observation["status"] != "ok":
                raw["technical_errors"].append(
                    {
                        "observation_index": observation["observation_index"],
                        "case_id": observation["case_id"],
                        "repeat": observation["repeat"],
                        "transform": observation["transform"],
                        "technical_error": observation["technical_error"],
                    }
                )
                if observation.get("http_status") in {401, 403}:
                    fatal_stop = "authentication_or_authorization_rejected"
            raw["request_accounting"] = _request_accounting(
                prepared["schedule"],
                raw["observations"],
            )
            raw["updated_at"] = utc_now()
            write_json_atomic(raw_path, raw)
            print(
                json.dumps(
                    {
                        "observation_index": observation["observation_index"],
                        "case_id": observation["case_id"],
                        "repeat": observation["repeat"],
                        "transform": observation["transform"],
                        "position": observation["position"],
                        "status": observation["status"],
                        "http_status": observation.get("http_status"),
                        "latency_ms": round(float(observation["latency_ms"]), 1),
                        "attempts": raw["request_accounting"]["http_attempts"],
                        "technical_failures": raw["request_accounting"][
                            "technical_failures"
                        ],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if fatal_stop:
                break

    if fatal_stop:
        raw["stop_reason"] = fatal_stop
    elif len(raw["observations"]) != EXPECTED_OBSERVATIONS:
        raw["stop_reason"] = "incomplete"
    elif raw["request_accounting"]["technical_failures"]:
        raw["stop_reason"] = "completed_with_failures"
    else:
        raw["stop_reason"] = "completed"
    valid = (
        raw["stop_reason"] == "completed"
        and raw["request_accounting"]["http_attempts"] == EXPECTED_OBSERVATIONS
        and raw["request_accounting"]["successful_observations"]
        == EXPECTED_OBSERVATIONS
        and raw["request_accounting"]["technical_failures"] == 0
    )
    raw["validity"] = {
        "status": "valid" if valid else "invalid",
        "valid": valid,
        "score_reportable": valid,
        "partial_scores_reported": False,
        "final_split_inspected": False,
        "reason": (
            "all 100 scheduled observations completed successfully with exactly "
            "one HTTP attempt each"
            if valid
            else "one or more scheduled observations did not finish successfully; "
            "aggregate metrics are withheld"
        ),
    }
    raw["updated_at"] = utc_now()
    write_json_atomic(raw_path, raw)

    analysis = build_analysis(
        raw,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
    )
    analysis["inputs"] = {
        "raw_artifact": {
            "path": _relative(raw_path),
            "sha256": sha256_file(raw_path),
        }
    }
    analysis["updated_at"] = utc_now()
    write_json_atomic(analysis_path, analysis)
    return raw, analysis


def analyze_existing(
    raw_path: Path,
    analysis_path: Path,
    *,
    bootstrap_seed: int,
    bootstrap_samples: int,
) -> dict[str, Any]:
    raw = read_json(raw_path)
    if not isinstance(raw, dict):
        raise ValueError("raw artifact is not an object")
    analysis = build_analysis(
        raw,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
    )
    analysis["inputs"] = {
        "raw_artifact": {
            "path": _relative(raw_path),
            "sha256": sha256_file(raw_path),
        }
    }
    write_json_atomic(analysis_path, analysis)
    return analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan-only", action="store_true")
    action.add_argument("--run", action="store_true")
    action.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--raw-path", type=Path, default=DEFAULT_RAW_PATH)
    parser.add_argument("--analysis-path", type=Path, default=DEFAULT_ANALYSIS_PATH)
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_SAMPLES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.analyze_only:
        analysis = analyze_existing(
            args.raw_path,
            args.analysis_path,
            bootstrap_seed=args.bootstrap_seed,
            bootstrap_samples=args.bootstrap_samples,
        )
        print(
            json.dumps(
                {
                    "analysis": _relative(args.analysis_path),
                    "valid": analysis["validity"]["valid"],
                    "score_reportable": analysis["validity"]["score_reportable"],
                },
                sort_keys=True,
            )
        )
        return

    prepared = prepare_inputs()
    if args.plan_only:
        print(
            json.dumps(
                {
                    "case_ids": list(prepared["case_ids"]),
                    "scheduled_observations": len(prepared["schedule"]),
                    "position_counts": prepared["position_counts"],
                    "schedule_sha256": prepared["schedule_sha256"],
                    "source_selectors_sha256": prepared["source_selectors_sha256"],
                    "query_hash_manifest_sha256": prepared[
                        "query_hash_manifest_sha256"
                    ],
                    "final_split_inspected": False,
                    "hosted_requests": 0,
                },
                sort_keys=True,
            )
        )
        return

    api_key = os.environ.get("NIA_API_KEY")
    if not api_key:
        raise SystemExit(
            "missing NIA_API_KEY; stopped before creating artifacts or making requests"
        )
    raw, analysis = run_experiment(
        prepared,
        api_key=api_key,
        raw_path=args.raw_path,
        analysis_path=args.analysis_path,
        bootstrap_seed=args.bootstrap_seed,
        bootstrap_samples=args.bootstrap_samples,
    )
    print(
        json.dumps(
            {
                "raw": _relative(args.raw_path),
                "analysis": _relative(args.analysis_path),
                "http_attempts": raw["request_accounting"]["http_attempts"],
                "successful_observations": raw["request_accounting"][
                    "successful_observations"
                ],
                "technical_failures": raw["request_accounting"][
                    "technical_failures"
                ],
                "stop_reason": raw["stop_reason"],
                "valid": analysis["validity"]["valid"],
                "score_reportable": analysis["validity"]["score_reportable"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if not analysis["validity"]["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
