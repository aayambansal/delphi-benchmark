from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable

from ds1000_harness.models import DeveloperCase, QueryCase


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            yield value


def _select_rows(
    path: Path,
    case_ids: tuple[str, ...],
    *,
    id_from_row,
    label: str,
) -> tuple[dict[str, Any], ...]:
    requested = set(case_ids)
    selected: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        case_id = str(id_from_row(row))
        if case_id in requested:
            selected[case_id] = row
    missing = [case_id for case_id in case_ids if case_id not in selected]
    if missing:
        raise ValueError(f"missing {label} case IDs: {', '.join(missing)}")
    return tuple(selected[case_id] for case_id in case_ids)


def materialize_jsonl_subset(
    source: Path,
    destination: Path,
    case_ids: tuple[str, ...],
    *,
    id_from_row: Callable[[dict[str, Any]], object],
    label: str,
) -> None:
    rows = _select_rows(
        source,
        case_ids,
        id_from_row=id_from_row,
        label=label,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            stream.write("\n")


def load_arb_cases(
    path: Path,
    case_ids: tuple[str, ...],
) -> tuple[QueryCase, ...]:
    rows = _select_rows(
        path,
        case_ids,
        id_from_row=lambda row: row.get("id"),
        label="ARB",
    )
    cases: list[QueryCase] = []
    for row in rows:
        gold = row.get("gold") or {}
        query = json.dumps(
            row.get("query") or {},
            ensure_ascii=False,
            sort_keys=True,
        )
        repo = str(row["repo"])
        cases.append(
            QueryCase(
                case_id=str(row["id"]),
                query=query,
                source=repo,
                revision=str(row["base_commit"]),
                gold_paths=tuple(str(path) for path in gold["root_cause_files"]),
                metadata={
                    "repo": repo,
                    "task_type": row.get("task_type"),
                    "query_provenance": row.get("query_provenance"),
                },
            )
        )
    return tuple(cases)


def load_ds1000_cases(
    path: Path,
    case_ids: tuple[str, ...],
) -> tuple[DeveloperCase, ...]:
    rows = _select_rows(
        path,
        case_ids,
        id_from_row=lambda row: (row.get("metadata") or {}).get("problem_id"),
        label="DS-1000",
    )
    cases: list[DeveloperCase] = []
    for row in rows:
        metadata = dict(row.get("metadata") or {})
        case_id = str(metadata["problem_id"])
        raw_docs = row.get("docs") or []
        if not raw_docs:
            raise ValueError(f"DS-1000 case {case_id} has no canonical docs")

        canonical_docs = tuple(
            {
                str(key): str(value)
                for key, value in doc.items()
                if key in {"function", "title", "text"} and value is not None
            }
            for doc in raw_docs
        )
        identifiers = tuple(
            dict.fromkeys(
                str(doc.get("function") or doc.get("title") or "").strip()
                for doc in raw_docs
                if str(doc.get("function") or doc.get("title") or "").strip()
            )
        )
        cases.append(
            DeveloperCase(
                case_id=case_id,
                prompt=str(row.get("prompt") or ""),
                library_name=str(metadata.get("library") or ""),
                reference_code=str(row.get("reference_code") or ""),
                gold_identifiers=identifiers,
                canonical_docs=canonical_docs,
                metadata=metadata,
            )
        )
    return tuple(cases)
