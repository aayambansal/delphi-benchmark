from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from statistics import fmean

from ds1000_harness.adapters import DelphiDocsAdapter
from ds1000_harness.developer import identifier_hit, pack_context
from ds1000_harness.loaders import load_ds1000_cases
from ds1000_harness.models import QueryCase, RetrievedItem


_CODE_PREFIXES = (
    ">>>",
    "...",
    "import ",
    "from ",
    "<code>",
    "</code>",
    "begin solution",
    "result =",
)


def compact_docs_query(prompt: str, *, max_chars: int = 2000) -> str:
    problem = re.split(r"\n\s*A:\s*\n", prompt, maxsplit=1)[0]
    lines: list[str] = []
    for raw_line in problem.splitlines():
        line = " ".join(raw_line.strip().split())
        lowered = line.casefold()
        if not line or lowered == "problem:" or lowered.startswith(_CODE_PREFIXES):
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
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:20743")
    parser.add_argument("--exclude-library", action="append", default=[])
    args = parser.parse_args()

    source_map = json.loads(args.source_map.read_text(encoding="utf-8"))["delphi"]
    rows = [
        json.loads(line)
        for line in args.samples.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = tuple(str(row["metadata"]["problem_id"]) for row in rows)
    cases = load_ds1000_cases(args.samples, ids)
    password = os.environ.get("SYSTEM_PASSWORD")
    if not password:
        raise SystemExit("missing SYSTEM_PASSWORD")
    adapter = DelphiDocsAdapter(args.base_url, password)

    details: list[dict[str, object]] = []
    for case in cases:
        if case.library_name in set(args.exclude_library):
            continue
        observations = {}
        for variant, query in (
            ("full", case.prompt),
            ("compact", compact_docs_query(case.prompt)),
        ):
            observation = adapter.search(
                QueryCase(
                    case_id=case.case_id,
                    query=query,
                    source=case.library_name,
                    revision="diagnostic",
                    gold_paths=("documentation",),
                    metadata={"delphi_docs_id": source_map[case.library_name]},
                ),
                10,
            )
            observations[variant] = observation
            context, context_tokens = pack_context(
                observation.items[:5],
                token_budget=8000,
            )
            hit = identifier_hit(context, case.gold_identifiers)
            details.append(
                {
                    "case_id": case.case_id,
                    "library": case.library_name,
                    "variant": variant,
                    "query": query,
                    "query_chars": len(query),
                    "status": observation.status,
                    "identifier_hit": hit,
                    "context_tokens": context_tokens,
                    "paths": [item.path for item in observation.items],
                }
            )
            print(
                json.dumps(
                    {
                        "case_id": case.case_id,
                        "library": case.library_name,
                        "variant": variant,
                        "hit": hit,
                        "query_chars": len(query),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

        fused: dict[str, tuple[RetrievedItem, float]] = {}
        for observation in observations.values():
            for item in observation.items:
                key = item.raw_id or f"{item.path}\0{item.content}"
                existing = fused.get(key)
                score = 1.0 / (60 + item.rank)
                if existing is None:
                    fused[key] = (item, score)
                else:
                    fused[key] = (existing[0], existing[1] + score)
        fused_items = tuple(
            RetrievedItem(
                path=item.path,
                content=item.content,
                score=score,
                rank=rank,
                raw_id=item.raw_id,
            )
            for rank, (item, score) in enumerate(
                sorted(
                    fused.values(),
                    key=lambda value: value[1],
                    reverse=True,
                )[:5],
                start=1,
            )
        )
        context, context_tokens = pack_context(fused_items, token_budget=8000)
        hit = identifier_hit(context, case.gold_identifiers)
        details.append(
            {
                "case_id": case.case_id,
                "library": case.library_name,
                "variant": "fused",
                "query": None,
                "query_chars": None,
                "status": (
                    "ok"
                    if all(
                        observation.status == "ok"
                        for observation in observations.values()
                    )
                    else "error"
                ),
                "identifier_hit": hit,
                "context_tokens": context_tokens,
                "paths": [item.path for item in fused_items],
            }
        )
        print(
            json.dumps(
                {
                    "case_id": case.case_id,
                    "library": case.library_name,
                    "variant": "fused",
                    "hit": hit,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    summary = {
        variant: {
            "n": len(variant_rows),
            "identifier_hit_rate": fmean(
                float(row["identifier_hit"]) for row in variant_rows
            ),
        }
        for variant in ("full", "compact", "fused")
        for variant_rows in [
            [row for row in details if row["variant"] == variant]
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"summary": summary, "details": details}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
