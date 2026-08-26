from __future__ import annotations

import argparse
import json
import sys
import time
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


def term_weight(term: str) -> float:
    if "." in term:
        return 1.2
    if (
        "_" in term
        or term.isupper()
        or any(character.isupper() for character in term[1:])
    ):
        return 1.0
    return 0.5


def lexical_file_search(
    session: Any,
    *,
    query: str,
    user_id: str,
    repo_id: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    from synsc.services.hybrid_retrieval import _symbol_search_needles

    needles = _symbol_search_needles(query, limit=24)
    if not needles:
        return [], []

    values = ", ".join(
        f"(:term_{index}, :weight_{index})"
        for index in range(len(needles))
    )
    params: dict[str, Any] = {
        "user_id": user_id,
        "repo_id": repo_id,
        "limit": limit,
    }
    for index, needle in enumerate(needles):
        params[f"term_{index}"] = needle
        params[f"weight_{index}"] = term_weight(needle)

    rows = session.execute(
        text(
            f"""
            WITH needles(term, base_weight) AS (
                VALUES {values}
            ),
            accessible AS MATERIALIZED (
                SELECT cc.file_id, cc.content, rf.file_path
                FROM code_chunks cc
                INNER JOIN user_repositories ur
                    ON cc.repo_id = ur.repo_id
                    AND ur.user_id = :user_id
                INNER JOIN repositories r
                    ON cc.repo_id = r.repo_id
                    AND (r.is_public = TRUE OR r.indexed_by = :user_id)
                INNER JOIN repository_files rf ON cc.file_id = rf.file_id
                WHERE cc.repo_id = :repo_id
            ),
            repo_stats AS (
                SELECT count(DISTINCT file_id)::double precision AS file_count
                FROM accessible
            ),
            matches AS (
                SELECT DISTINCT
                    accessible.file_id,
                    accessible.file_path,
                    needles.term,
                    needles.base_weight
                FROM needles
                INNER JOIN accessible
                    ON accessible.content ILIKE '%' || needles.term || '%'
            ),
            document_frequency AS (
                SELECT term, count(DISTINCT file_id)::double precision AS df
                FROM matches
                GROUP BY term
            ),
            file_terms AS (
                SELECT
                    matches.file_id,
                    matches.file_path,
                    matches.term,
                    matches.base_weight
                        * (
                            1.0
                            + ln(
                                (repo_stats.file_count + 1.0)
                                / (document_frequency.df + 1.0)
                            )
                        ) AS term_score
                FROM matches
                INNER JOIN document_frequency USING (term)
                CROSS JOIN repo_stats
            )
            SELECT
                file_id,
                file_path,
                sum(term_score) AS score,
                count(*) AS matched_terms,
                array_agg(term ORDER BY term_score DESC, term) AS terms
            FROM file_terms
            GROUP BY file_id, file_path
            ORDER BY score DESC, matched_terms DESC, file_path
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows], needles


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
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.arb_source.resolve()))
    from agent_retrieval_bench.baseline import (
        query_text_for_eval,
        target_gold_files,
    )
    from synsc.database.connection import get_session
    from synsc.services.search_service import _prepare_search_query

    keep_ids = {
        str(row.get("id") or row.get("sample_id"))
        for row in read_jsonl(args.keep_list)
    }
    samples = [
        row
        for path in args.samples
        for row in read_jsonl(path)
        if str(row["id"]) in keep_ids
    ]
    ids = source_ids(args.sources)
    first_source_id = ids[
        (str(samples[0]["repo"]), str(samples[0]["base_commit"]).lower())
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

    output: list[dict[str, Any]] = []
    for sample in samples:
        source_id = ids[
            (str(sample["repo"]), str(sample["base_commit"]).lower())
        ]
        query = _prepare_search_query(query_text_for_eval(sample))
        started = time.perf_counter()
        with get_session() as session:
            rows, needles = lexical_file_search(
                session,
                query=query,
                user_id=user_id,
                repo_id=source_id,
                limit=args.limit,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        paths = dedupe(str(row["file_path"]) for row in rows)
        gold = target_gold_files(sample)
        gold_ranks = ranks(paths, gold)
        reciprocal_ranks = [
            1.0 / rank
            for rank in gold_ranks.values()
            if isinstance(rank, int) and rank > 0
        ]
        result = {
            "sample_id": str(sample["id"]),
            "task_type": str(sample["task_type"]),
            "repo": str(sample["repo"]),
            "gold_files": gold,
            "gold_ranks": gold_ranks,
            "mrr": max(reciprocal_ranks, default=0.0),
            "recall_at_20": (
                sum(
                    1
                    for rank in gold_ranks.values()
                    if isinstance(rank, int) and rank <= 20
                )
                / len(gold)
                if gold
                else 0.0
            ),
            "latency_ms": latency_ms,
            "needles": needles,
            "top_files": paths[:20],
            "top_file_scores": [
                {
                    "path": str(row["file_path"]),
                    "score": float(row["score"]),
                    "matched_terms": int(row["matched_terms"]),
                    "terms": list(row["terms"]),
                }
                for row in rows[:20]
            ],
        }
        output.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in output) + "\n",
        encoding="utf-8",
    )
    overall_mrr = sum(row["mrr"] for row in output) / len(output)
    overall_recall = sum(row["recall_at_20"] for row in output) / len(output)
    mean_latency = sum(row["latency_ms"] for row in output) / len(output)
    print(
        json.dumps(
            {
                "evaluated": len(output),
                "mrr": overall_mrr,
                "recall_at_20": overall_recall,
                "mean_latency_ms": mean_latency,
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
