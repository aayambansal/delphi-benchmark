from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def source_ids(path: Path) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for row in read_jsonl(path):
        source_id = row.get("source_id")
        if row.get("status") == "indexed" and isinstance(source_id, str):
            result[(str(row["repo"]), str(row["revision"]).lower())] = source_id
    return result


def dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def query_paths(query: str) -> list[str]:
    try:
        payload = json.loads(query)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    paths: list[str] = []

    def collect(key: str, value: Any) -> None:
        normalized = key.lower().replace("-", "_")
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                collect(str(nested_key), nested_value)
            return
        if isinstance(value, list):
            for item in value:
                collect(key, item)
            return
        if not isinstance(value, str):
            return
        if normalized.endswith(
            ("file", "files", "path", "paths", "filename", "filenames")
        ):
            paths.append(value)

    for key, value in payload.items():
        collect(str(key), value)
    return dedupe(paths)


def file_paths(candidates: Iterable[Any]) -> list[str]:
    return dedupe(str(candidate.file_path) for candidate in candidates)


def raw_file_paths(rows: Iterable[dict[str, Any]]) -> list[str]:
    return dedupe(str(row.get("file_path") or "") for row in rows)


def ranks(paths: list[str], gold_files: list[str]) -> dict[str, int | None]:
    return {
        path: paths.index(path) + 1 if path in paths else None
        for path in gold_files
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, action="append", required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--keep-list", type=Path, required=True)
    parser.add_argument("--arb-source", type=Path, required=True)
    parser.add_argument("--per-workflow", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.arb_source.resolve()))
    from agent_retrieval_bench.baseline import (
        query_text_for_eval,
        target_gold_files,
    )
    from synsc.database.connection import get_session
    from synsc.services.hybrid_retrieval import (
        bm25_search,
        exact_path_search,
        exact_symbol_search,
        extract_identifiers,
        fuse_candidates,
        trigram_search,
        vector_to_candidates,
    )
    from synsc.services.search_service import SearchService, _prepare_search_query

    keep_ids = {
        str(row.get("id") or row.get("sample_id"))
        for row in read_jsonl(args.keep_list)
    }
    candidates = [
        row
        for path in args.samples
        for row in read_jsonl(path)
        if str(row["id"]) in keep_ids
    ]
    selected: list[dict[str, Any]] = []
    workflow_counts: dict[str, int] = {}
    for row in candidates:
        workflow = str(row["task_type"])
        if workflow_counts.get(workflow, 0) >= args.per_workflow:
            continue
        selected.append(row)
        workflow_counts[workflow] = workflow_counts.get(workflow, 0) + 1

    ids = source_ids(args.sources)
    first_source_id = ids[
        (str(selected[0]["repo"]), str(selected[0]["base_commit"]).lower())
    ]
    with get_session() as session:
        user_id = str(
            session.execute(
                text(
                    "SELECT indexed_by FROM repositories "
                    "WHERE repo_id = :repo_id"
                ),
                {"repo_id": first_source_id},
            ).scalar_one()
        )

    service = SearchService(user_id=user_id)
    output: list[dict[str, Any]] = []
    for sample in selected:
        repo = str(sample["repo"])
        revision = str(sample["base_commit"])
        source_id = ids[(repo, revision.lower())]
        raw_query = query_text_for_eval(sample)
        prepared = _prepare_search_query(raw_query)
        embedding = service.embedding_generator.generate_single(prepared)
        gold = target_gold_files(sample)
        anchors = query_paths(raw_query)

        with get_session() as session:
            vector_raw = service.vector_store.search(
                query_embedding=embedding,
                user_id=user_id,
                repo_ids=[source_id],
                language=None,
                top_k=300,
            )
            vector = vector_to_candidates(vector_raw)
            bm25 = bm25_search(
                session,
                prepared,
                user_id,
                [source_id],
                top_k=300,
            )
            symbol = exact_symbol_search(
                session,
                prepared,
                user_id,
                [source_id],
                top_k=100,
            )
            trigram = trigram_search(
                session,
                prepared,
                user_id,
                [source_id],
                top_k=100,
            )
            path = [
                candidate
                for anchor in anchors
                for candidate in exact_path_search(
                    session,
                    anchor,
                    user_id,
                    [source_id],
                    top_k=100,
                )
            ]
        fused = fuse_candidates([vector, bm25, symbol, trigram, path])
        branch_paths = {
            "vector": raw_file_paths(vector_raw),
            "bm25": file_paths(bm25),
            "symbol": file_paths(symbol),
            "trigram": file_paths(trigram),
            "explicit_path": file_paths(path),
            "fused": file_paths(fused),
        }
        result = {
            "sample_id": str(sample["id"]),
            "task_type": str(sample["task_type"]),
            "repo": repo,
            "gold_files": gold,
            "anchor_paths": anchors,
            "raw_query_chars": len(raw_query),
            "prepared_query_chars": len(prepared),
            "prepared_query": prepared,
            "identifiers": extract_identifiers(prepared)[:50],
            "branches": {
                name: {
                    "candidate_chunks": len(
                        {
                            "vector": vector,
                            "bm25": bm25,
                            "symbol": symbol,
                            "trigram": trigram,
                            "explicit_path": path,
                            "fused": fused,
                        }[name]
                    ),
                    "unique_files": len(paths),
                    "gold_ranks": ranks(paths, gold),
                    "top_files": paths[:20],
                }
                for name, paths in branch_paths.items()
            },
        }
        output.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in output) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
