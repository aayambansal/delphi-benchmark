from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from statistics import fmean
from typing import Any

from ds1000_harness.adapters import (
    Context7Adapter,
    DelphiDocsAdapter,
    NiaDocsAdapter,
)
from ds1000_harness.developer import identifier_hit, pack_context
from ds1000_harness.loaders import load_ds1000_cases
from ds1000_harness.models import QueryCase


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _case_ids(path: Path) -> tuple[str, ...]:
    return tuple(
        str((row.get("metadata") or {})["problem_id"])
        for row in _read_jsonl(path)
    )


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _status_rates(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "technical_failure_rate": fmean(
            float(row["status"] == "error") for row in rows
        ),
        "no_result_rate": fmean(
            float(row["status"] == "no_result") for row in rows
        ),
    }


def _context7_resolver_name(
    library_name: str,
    source_map: dict[str, Any],
) -> str:
    resolver_names = source_map.get("context7_resolver_names")
    if not isinstance(resolver_names, dict):
        return library_name
    canonical = resolver_names.get(library_name)
    return canonical if isinstance(canonical, str) and canonical else library_name


def _compact_docs_query(prompt: str, *, max_chars: int = 2000) -> str:
    problem = re.split(r"\n\s*A:\s*\n", prompt, maxsplit=1)[0]
    code_prefixes = (
        ">>>",
        "...",
        "import ",
        "from ",
        "<code>",
        "</code>",
        "begin solution",
        "result =",
    )
    lines: list[str] = []
    for raw_line in problem.splitlines():
        line = " ".join(raw_line.strip().split())
        lowered = line.casefold()
        if not line or lowered == "problem:" or lowered.startswith(code_prefixes):
            continue
        words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", line)
        if len(words) < 4:
            continue
        punctuation = sum(character in "{}[]()='\":," for character in line)
        if punctuation > max(8, len(line) // 7):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", line):
            continue
        lines.append(line)
    compacted = " ".join(lines)
    return compacted[:max_chars] or prompt[:max_chars]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine",
        choices=("delphi", "nia", "context7"),
        required=True,
    )
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--budget", type=int, default=8000)
    parser.add_argument("--base-url")
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--nia-skip-llm", action="store_true")
    parser.add_argument(
        "--context7-resolver-strategy",
        choices=("first", "quality"),
        default="first",
    )
    parser.add_argument(
        "--query-transform",
        choices=("full", "compact"),
        default="full",
    )
    args = parser.parse_args()

    cases = load_ds1000_cases(args.samples, _case_ids(args.samples))
    source_map = json.loads(args.source_map.read_text(encoding="utf-8"))
    engine_sources = source_map.get(args.engine) or {}
    if args.engine == "delphi":
        adapter = DelphiDocsAdapter(
            args.base_url or "http://127.0.0.1:18742",
            _required_env("SYSTEM_PASSWORD"),
        )
    elif args.engine == "nia":
        adapter = NiaDocsAdapter(
            args.base_url or "https://apigcp.trynia.ai/v2",
            _required_env("NIA_API_KEY"),
            skip_llm=args.nia_skip_llm,
        )
    else:
        adapter = Context7Adapter(
            args.base_url or "https://context7.com/api/v2",
            _required_env("CONTEXT7_API_KEY"),
            resolver_strategy=args.context7_resolver_strategy,
        )

    query_cases: list[QueryCase] = []
    for case in cases:
        metadata: dict[str, object] = {
            "library_name": (
                _context7_resolver_name(case.library_name, source_map)
                if args.engine == "context7"
                else case.library_name
            ),
        }
        source_id = engine_sources.get(case.library_name)
        if args.engine == "delphi" and source_id:
            metadata["delphi_docs_id"] = source_id
        elif args.engine == "nia" and source_id:
            metadata["nia_docs_id"] = source_id
        elif args.engine == "context7" and source_id:
            metadata["context7_library_id"] = source_id
        query_cases.append(
            QueryCase(
                case_id=case.case_id,
                query=(
                    _compact_docs_query(case.prompt)
                    if args.query_transform == "compact"
                    else case.prompt
                ),
                source=case.library_name,
                revision="live-2026-07-29",
                gold_paths=("documentation",),
                metadata=metadata,
            )
        )

    if args.warmup:
        adapter.search(query_cases[0], args.limit)

    details: list[dict[str, Any]] = []
    for case, query_case in zip(cases, query_cases):
        observation = adapter.search(query_case, args.limit)
        context, context_tokens = pack_context(
            observation.items,
            token_budget=args.budget,
        )
        hit = identifier_hit(context, case.gold_identifiers)
        details.append(
            {
                "case_id": case.case_id,
                "library": case.library_name,
                "engine": args.engine,
                "status": observation.status,
                "error_type": observation.error_type,
                "latency_ms": observation.latency_ms,
                "context": context,
                "context_tokens": context_tokens,
                "identifier_hit": hit,
                "gold_identifiers": list(case.gold_identifiers),
                "items": [
                    {
                        "path": item.path,
                        "rank": item.rank,
                        "score": item.score,
                        "raw_id": item.raw_id,
                    }
                    for item in observation.items
                ],
                "provider_metadata": observation.metadata,
            }
        )
        print(
            json.dumps(
                {
                    "engine": args.engine,
                    "case_id": case.case_id,
                    "library": case.library_name,
                    "status": observation.status,
                    "identifier_hit": hit,
                    "context_tokens": context_tokens,
                    "latency_ms": round(observation.latency_ms, 1),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    libraries = sorted({str(row["library"]) for row in details})
    per_library = {
        library: {
            "n": len(rows),
            "identifier_hit_rate": fmean(
                float(row["identifier_hit"]) for row in rows
            ),
            **_status_rates(rows),
        }
        for library in libraries
        for rows in [
            [row for row in details if row["library"] == library]
        ]
    }
    summary = {
        "engine": args.engine,
        "n": len(details),
        "identifier_hit_rate": fmean(
            float(row["identifier_hit"]) for row in details
        ),
        "library_macro_identifier_hit_rate": fmean(
            row["identifier_hit_rate"] for row in per_library.values()
        ),
        **_status_rates(details),
        "mean_latency_ms": fmean(
            float(row["latency_ms"]) for row in details
        ),
        "mean_context_tokens": fmean(
            int(row["context_tokens"]) for row in details
        ),
        "retrieval_limit": args.limit,
        "context_budget_tokens": args.budget,
        "per_library": per_library,
    }
    _write_json(args.output, details)
    _write_json(args.summary, summary)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
