"""Reconstruct the hosted synthesis engine's *retrieved* context from its
recorded responses so it can enter the matched-synthesis comparison.

The engine's `skip_llm` (raw sources) mode returned no sources during the
recorded round, so its raw retrieval was never observable directly. Its
synthesized responses, however, carry the five retrieved source chunks it
grounded on (`sources[*].content` with `metadata.file_path`). Those chunks
are the engine's retrieval evidence for the question. This script packs them
with the same `pack_context` routine and 8,000-token budget used for every
other engine's raw context, producing a details file in the same schema as
the recorded raw-retrieval arms. Routing that context through the frozen
synthesis stage yields a comparison in which the retrieval is the engine's
and the synthesis is ours, matching the other arms.

No hosted requests are made; everything is derived from recorded artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any

from ds1000_harness.developer import identifier_hit, pack_context
from ds1000_harness.models import RetrievedItem

ROOT = Path(__file__).resolve().parent.parent


def source_path(source: dict[str, Any]) -> str:
    metadata = source.get("metadata") or {}
    for key in ("file_path", "sourceURL", "source_url", "url"):
        value = metadata.get(key) or source.get(key)
        if isinstance(value, str) and value:
            return value
    return str(metadata.get("document_name") or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recorded",
        type=Path,
        default=ROOT / "results" / "DOCS-dev-nia-answer-full-details.json",
    )
    parser.add_argument(
        "--retrieval-latency-source",
        type=Path,
        default=ROOT / "results" / "DOCS-dev-nia-raw-full-details.json",
        help="recorded skip_llm run whose latency approximates retrieval-only time",
    )
    parser.add_argument("--budget", type=int, default=8000)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "DOCS-dev-nia-retrieved-k5-details.json",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "results" / "DOCS-dev-nia-retrieved-k5-summary.json",
    )
    args = parser.parse_args()

    recorded = json.loads(args.recorded.read_text(encoding="utf-8"))
    rows = recorded if isinstance(recorded, list) else recorded.get("details") or []
    latency_by_case: dict[str, float] = {}
    if args.retrieval_latency_source.exists():
        raw = json.loads(args.retrieval_latency_source.read_text(encoding="utf-8"))
        raw_rows = raw if isinstance(raw, list) else raw.get("details") or []
        latency_by_case = {
            str(row["case_id"]): float(row.get("latency_ms") or 0.0) for row in raw_rows
        }

    details: list[dict[str, Any]] = []
    for row in rows:
        citations = (row.get("provider_metadata") or {}).get("citations") or []
        items = []
        for rank, source in enumerate(citations[: args.limit], start=1):
            if not isinstance(source, dict):
                continue
            content = str(source.get("content") or source.get("text") or "")
            if not content.strip():
                continue
            path = source_path(source)
            items.append(
                RetrievedItem(path=path, content=content, score=None, rank=rank, raw_id=path or None)
            )
        context, tokens = pack_context(tuple(items), token_budget=args.budget)
        gold = tuple(row.get("gold_identifiers") or ())
        details.append(
            {
                "case_id": str(row["case_id"]),
                "library": row.get("library"),
                "engine": "nia",
                "status": "ok" if items else "error",
                "error_type": None if items else "no_recorded_sources",
                "context": context,
                "context_tokens": tokens,
                "gold_identifiers": list(gold),
                "identifier_hit": identifier_hit(context, gold),
                "items": [
                    {"path": item.path, "rank": item.rank, "raw_id": item.raw_id, "score": None}
                    for item in items
                ],
                "latency_ms": latency_by_case.get(str(row["case_id"]), 0.0),
                "provider_metadata": {
                    "result_mode": "retrieved_sources_reconstructed",
                    "reconstructed_from": str(args.recorded.name),
                    "native_answer_latency_ms": float(row.get("latency_ms") or 0.0),
                    "retrieval_latency_source": str(args.retrieval_latency_source.name),
                    "sources": len(items),
                },
            }
        )

    args.output.write_text(json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    summary = {
        "engine": "nia",
        "result_mode": "retrieved_sources_reconstructed",
        "n": len(details),
        "failure_rate": fmean(float(r["status"] != "ok") for r in details) if details else None,
        "identifier_hit_rate": fmean(float(bool(r["identifier_hit"])) for r in details) if details else None,
        "mean_context_tokens": fmean(r["context_tokens"] for r in details) if details else None,
        "mean_sources": fmean(r["provider_metadata"]["sources"] for r in details) if details else None,
        "context_budget_tokens": args.budget,
        "retrieval_limit": args.limit,
        "per_library": {},
    }
    for library in sorted({str(r.get("library")) for r in details}):
        group = [r for r in details if str(r.get("library")) == library]
        summary["per_library"][library] = {
            "n": len(group),
            "identifier_hit_rate": fmean(float(bool(r["identifier_hit"])) for r in group),
        }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
