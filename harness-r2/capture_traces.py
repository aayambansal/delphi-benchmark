"""Capture full retrieval traces for publication.

The sweep runner keeps only what it needs to score. The article needs the
rest: the exact query text sent to the engine, every returned file with the
branch that surfaced it, and the raw record — so a reader can expand any
claim down to the evidence rather than taking the number on trust.

Writes a single JSON file shaped for the landing site's trace components.

Usage:
    python -m harness.capture_traces --out ../delphi-sota-worktree/landing/src/lib/traces.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
ARB_SRC = ROOT / "external" / "arb-src" / "src"
SOURCES = ROOT / "artifacts" / "development" / "delphi-openai-local-arb-sources.jsonl"

# One representative case per workflow keeps the article honest: these are
# picked by position in the split, not by how well Delphi happened to do.
CASES_PER_WORKFLOW = 2


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--split", default="development")
    parser.add_argument("--base-url", default="http://127.0.0.1:20742")
    parser.add_argument("--api-key", default="delphi-benchmark-admin")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--per-workflow", type=int, default=CASES_PER_WORKFLOW)
    args = parser.parse_args()

    sys.path.insert(0, str(ARB_SRC))
    from agent_retrieval_bench.baseline import (  # noqa: PLC0415
        query_text_for_eval,
        target_gold_files,
    )

    sources: dict[tuple[str, str], str] = {}
    for row in read_jsonl(SOURCES):
        if row.get("status") in {"indexed", "reused"} and row.get("source_id"):
            sources[(row["repo"], str(row["revision"]).lower())] = row["source_id"]

    selected: list[dict[str, Any]] = []
    for path in sorted((ROOT / "samples" / args.split).glob("v2_*.jsonl")):
        taken = 0
        for sample in read_jsonl(path):
            if (sample.get("gold") or {}).get("no_gold") is True:
                continue
            if not target_gold_files(sample):
                continue
            if (sample["repo"], str(sample["base_commit"]).lower()) not in sources:
                continue
            selected.append(sample)
            taken += 1
            if taken >= args.per_workflow:
                break

    client = httpx.Client(timeout=180.0)
    traces: list[dict[str, Any]] = []

    for sample in selected:
        source_id = sources[(sample["repo"], str(sample["base_commit"]).lower())]
        query = query_text_for_eval(sample)
        started = time.perf_counter()
        response = client.post(
            f"{args.base_url}/v1/search/code",
            headers={"X-API-Key": args.api_key},
            json={"query": query, "repo_ids": [source_id], "top_k": 100},
        )
        response.raise_for_status()
        payload = response.json()
        latency_ms = (time.perf_counter() - started) * 1000

        ranked: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in payload.get("results") or []:
            path_value = row.get("file_path")
            if not path_value or path_value in seen:
                continue
            seen.add(path_value)
            ranked.append(
                {
                    "path": path_value,
                    "score": round(float(row.get("relevance_score") or 0.0), 4),
                    "branches": sorted((row.get("candidate_sources") or {}).keys()),
                }
            )
            if len(ranked) >= args.limit:
                break

        traces.append(
            {
                "sampleId": sample["id"],
                "workflow": sample["task_type"],
                "repo": sample["repo"],
                "baseCommit": sample["base_commit"],
                "query": query,
                "goldFiles": target_gold_files(sample),
                "ranked": ranked,
                "latencyMs": round(latency_ms, 1),
                "raw": {
                    "search_time_ms": payload.get("search_time_ms"),
                    "quality_mode": payload.get("quality_mode"),
                    "hybrid": payload.get("hybrid"),
                    "timing": payload.get("timing"),
                    "warnings": payload.get("warnings"),
                },
            }
        )
        print(f"captured {sample['task_type']:<18} {sample['repo']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(traces, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {len(traces)} traces to {args.out}")


if __name__ == "__main__":
    main()
