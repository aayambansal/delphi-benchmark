from __future__ import annotations

import argparse
import json
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

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


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def related_path_pattern(query: str) -> str | None:
    """Derive a loose sibling-path probe from explicit developer file hints."""
    try:
        payload = json.loads(query)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    paths: list[str] = []

    def collect(key: str, value: Any) -> None:
        normalized_key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                collect(str(nested_key), nested_value)
            return
        if isinstance(value, list):
            for item in value:
                collect(key, item)
            return
        if (
            isinstance(value, str)
            and ("file" in normalized_key or "path" in normalized_key)
            and "/" in value
            and "://" not in value
        ):
            paths.append(value)

    for field, field_value in payload.items():
        collect(str(field), field_value)
    if not paths:
        return None

    stem = Path(paths[0]).name.rsplit(".", 1)[0]
    tokens = re.findall(
        r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+",
        stem.replace("-", "_"),
    )
    useful = [
        token.lower()
        for token in tokens
        if len(token) >= 2 and token.lower() not in {"src", "test", "tests"}
    ]
    if not useful:
        return None
    return "*" + "*".join(useful) + "*"


@contextmanager
def pipeline_variant(name: str) -> Iterator[None]:
    import synsc.services.hybrid_retrieval as hybrid_module
    import synsc.services.reranker as reranker_module
    import synsc.services.search_service as search_module

    original_weights = hybrid_module.DEFAULT_WEIGHTS
    original_metadata = search_module._apply_metadata_scoring
    original_threshold = search_module._apply_dynamic_threshold
    original_mmr = search_module._apply_mmr
    original_reranker = reranker_module.get_reranker

    class IdentityReranker:
        def rerank(
            self,
            query: str,
            results: list[dict[str, Any]],
            *,
            blend_alpha: float,
        ) -> list[dict[str, Any]]:
            del query, blend_alpha
            return results

    try:
        if "no_metadata" in name:
            search_module._apply_metadata_scoring = (
                lambda results, *args, **kwargs: results
            )
        if "no_threshold" in name:
            search_module._apply_dynamic_threshold = (
                lambda results, *args, **kwargs: results
            )
        if "no_rerank" in name:
            reranker_module.get_reranker = lambda: IdentityReranker()
        if "no_mmr" in name:
            search_module._apply_mmr = (
                lambda results, *args, top_k, **kwargs: results[:top_k]
            )
        symbol_weight_match = re.search(r"symbol_weight_(\d+)", name)
        if symbol_weight_match:
            symbol_weight = int(symbol_weight_match.group(1)) / 100
            hybrid_module.DEFAULT_WEIGHTS = {
                **original_weights,
                "symbol": symbol_weight,
            }
        yield
    finally:
        hybrid_module.DEFAULT_WEIGHTS = original_weights
        search_module._apply_metadata_scoring = original_metadata
        search_module._apply_dynamic_threshold = original_threshold
        search_module._apply_mmr = original_mmr
        reranker_module.get_reranker = original_reranker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, action="append", required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--keep-list", type=Path, required=True)
    parser.add_argument("--arb-source", type=Path, required=True)
    parser.add_argument("--per-workflow", type=int, default=2)
    parser.add_argument("--variant", action="append")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.arb_source.resolve()))
    from agent_retrieval_bench.baseline import (
        query_text_for_eval,
        target_gold_files,
    )
    from synsc.database.connection import get_session
    from synsc.services.search_service import SearchService

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

    variants = tuple(args.variant or (
        "baseline",
        "no_metadata",
        "no_threshold",
        "no_rerank",
        "no_metadata_no_threshold",
        "no_rerank_no_threshold",
    ))
    output: list[dict[str, Any]] = []
    for variant in variants:
        with pipeline_variant(variant):
            service = SearchService(user_id=user_id)
            for sample in selected:
                repo = str(sample["repo"])
                revision = str(sample["base_commit"])
                query = query_text_for_eval(sample)
                source_id = ids[(repo, revision.lower())]
                started = time.perf_counter()
                result = service.search_code(
                    query=query,
                    repo_ids=[source_id],
                    file_pattern=(
                        related_path_pattern(query)
                        if "related_path" in variant
                        else None
                    ),
                    top_k=100,
                    quality_mode="agent",
                )
                latency_ms = (time.perf_counter() - started) * 1000
                paths = dedupe(
                    [
                        str(row.get("file_path") or "")
                        for row in result.get("results") or []
                    ]
                )
                gold = target_gold_files(sample)
                ranks = [
                    paths.index(path) + 1
                    for path in gold
                    if path in paths
                ]
                output.append(
                    {
                        "variant": variant,
                        "sample_id": str(sample["id"]),
                        "task_type": str(sample["task_type"]),
                        "repo": repo,
                        "gold_files": gold,
                        "unique_paths": len(paths),
                        "top_files": paths[:20],
                        "mrr": 1.0 / min(ranks) if ranks else 0.0,
                        "recall_at_20": (
                            sum(path in paths[:20] for path in gold) / len(gold)
                            if gold
                            else 0.0
                        ),
                        "latency_ms": latency_ms,
                        "success": bool(result.get("success")),
                        "hybrid": result.get("hybrid"),
                        "timing": result.get("timing"),
                    }
                )
                print(json.dumps(output[-1], sort_keys=True), flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in output) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
