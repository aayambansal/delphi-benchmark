from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable

from harness.provider_clients import DelphiClient, NiaClient


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    temporary.replace(path)


def source_ids(
    path: Path,
) -> dict[tuple[str, str], str | tuple[str, ...]]:
    result: dict[tuple[str, str], str | tuple[str, ...]] = {}
    for row in read_jsonl(path):
        source_id = row.get("source_id")
        if (
            row.get("status") in {"indexed", "reused"}
            and isinstance(source_id, str)
        ):
            shard_ids = (row.get("metadata") or {}).get("source_ids")
            value: str | tuple[str, ...] = source_id
            if (
                isinstance(shard_ids, list)
                and shard_ids
                and all(isinstance(item, str) for item in shard_ids)
            ):
                value = tuple(shard_ids)
            result[(str(row["repo"]), str(row["revision"]).lower())] = value
    return result


def resolve_corpus_manifest(
    path: Path,
    *,
    data_root: Path,
) -> dict[tuple[str, str], Path]:
    result: dict[tuple[str, str], Path] = {}
    for row in read_jsonl(path):
        if row.get("status") not in {None, "ok"}:
            continue
        chunks_value = row.get("chunks_path")
        if not chunks_value:
            continue
        chunks_path = Path(str(chunks_value))
        if not chunks_path.is_absolute():
            chunks_path = data_root / chunks_path
        result[(str(row["repo"]), str(row["base_commit"]))] = chunks_path
    return result


def dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot calculate percentile of empty values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def mean_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {}
    names = sorted(
        set.intersection(
            *(set(row["metrics"]) for row in rows)
        )
    )
    return {
        name: fmean(float(row["metrics"][name]) for row in rows)
        for name in names
    }


def macro_metrics(
    rows: list[dict[str, Any]],
    *,
    key: str,
) -> dict[str, float]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    group_means = [mean_metrics(group) for group in groups.values()]
    if not group_means:
        return {}
    names = sorted(set.intersection(*(set(group) for group in group_means)))
    return {
        name: fmean(group[name] for group in group_means)
        for name in names
    }


def summarize(rows: list[dict[str, Any]], *, provider_label: str) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize empty details")
    successful = [row for row in rows if row["status"] == "ok"]
    scored = rows
    latencies = [float(row["latency_ms"]) for row in successful]
    return {
        "schema_version": 1,
        "provider": provider_label,
        "n": len(rows),
        "failures": len(rows) - len(successful),
        "failure_rate": (len(rows) - len(successful)) / len(rows),
        "sample_weighted": mean_metrics(scored),
        "repo_macro": macro_metrics(scored, key="repo"),
        "workflow_macro": macro_metrics(scored, key="task_type"),
        "success_at": {
            str(k): fmean(
                float(row["metrics"].get(f"Recall@{k}", 0.0) > 0.0)
                for row in scored
            )
            for k in (5, 10, 20)
        },
        "by_workflow": {
            task: {
                "n": len(task_rows),
                "metrics": mean_metrics(task_rows),
                "success_at_5": fmean(
                    float(row["metrics"].get("Recall@5", 0.0) > 0.0)
                    for row in task_rows
                ),
            }
            for task, task_rows in sorted(
                (
                    (task, [row for row in rows if row["task_type"] == task])
                    for task in {str(row["task_type"]) for row in rows}
                ),
                key=lambda item: item[0],
            )
        },
        "latency_ms": (
            {
                "mean": fmean(latencies),
                "median": median(latencies),
                "p95": percentile(latencies, 0.95),
            }
            if latencies
            else {}
        ),
        "mean_unique_paths": fmean(len(row["top_files"]) for row in rows),
    }


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("delphi", "nia"), required=True)
    parser.add_argument("--samples", type=Path, action="append", required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--arb-source", type=Path, required=True)
    parser.add_argument("--corpus-manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--provider-fetch-limit",
        type=int,
        default=100,
        help=(
            "Provider-level chunk/citation fetch depth before deduplicating to "
            "--limit unique files."
        ),
    )
    parser.add_argument("--context-budget", type=int, default=8_000)
    parser.add_argument(
        "--skip-unprovisioned",
        action="store_true",
        help=(
            "Skip samples whose (repo, revision) was never indexed instead of "
            "aborting. The skipped set is written to the summary so the scope "
            "of the reported numbers stays explicit."
        ),
    )
    parser.add_argument("--base-url")
    parser.add_argument("--nia-fast-mode", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--nia-skip-llm", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--nia-source-kind",
        choices=("repository", "local_folder"),
        default="repository",
    )
    parser.add_argument(
        "--nia-reasoning-strategy",
        choices=("vector", "hybrid", "tree"),
        default="vector",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        raise SystemExit("--limit must be between 1 and 100")
    if not args.limit <= args.provider_fetch_limit <= 100:
        raise SystemExit(
            "--provider-fetch-limit must be between --limit and 100"
        )

    sys.path.insert(0, str(args.arb_source.resolve()))
    from agent_retrieval_bench.baseline import (
        hard_negative_files,
        query_has_leakage,
        query_text_for_eval,
        sample_metrics,
        target_gold_files,
    )
    from agent_retrieval_bench.bcy_curve import CorpusFileCache, pack_files

    ids = source_ids(args.sources)
    corpus = CorpusFileCache(
        resolve_corpus_manifest(
            args.corpus_manifest,
            data_root=args.data_root,
        )
    )
    if args.engine == "delphi":
        provider: DelphiClient | NiaClient = DelphiClient(
            args.base_url or "http://127.0.0.1:18742",
            required_env("SYSTEM_PASSWORD"),
        )
    else:
        provider = NiaClient(
            args.base_url or "https://apigcp.trynia.ai/v2",
            required_env("NIA_API_KEY"),
            fast_mode=args.nia_fast_mode,
            reasoning_strategy=args.nia_reasoning_strategy,
            skip_llm=args.nia_skip_llm,
            source_kind=args.nia_source_kind,
        )

    samples = [
        row
        for path in args.samples
        for row in read_jsonl(path)
        if (row.get("gold") or {}).get("no_gold") is not True
    ]
    details: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for sample in samples:
        repo = str(sample["repo"])
        revision = str(sample["base_commit"])
        case_id = str(sample["id"])
        gold = target_gold_files(sample)
        if not gold:
            raise RuntimeError(f"positive sample has no target files: {case_id}")
        query = query_text_for_eval(sample)
        if query_has_leakage(sample, query):
            raise RuntimeError(f"query leakage detected in validated sample: {case_id}")
        source_id = ids.get((repo, revision.lower()))
        if not source_id:
            if args.skip_unprovisioned:
                # Recorded rather than silently dropped: the count of skipped
                # cases is what makes the reported scope auditable.
                skipped.append(
                    {"sample_id": case_id, "repo": repo, "revision": revision}
                )
                continue
            raise RuntimeError(f"missing source for {repo}@{revision}")
        observation = provider.search(
            query=query,
            repo=repo,
            revision=revision,
            source_id=source_id,
            limit=args.provider_fetch_limit,
        )
        ranked_paths = dedupe(observation.paths)[: args.limit]
        ranked_chunks = [
            {
                "path": path,
                "text": corpus.file_text(repo, revision, path) or "",
                "kind": "file",
            }
            for path in ranked_paths
        ]
        metrics = sample_metrics(
            gold,
            ranked_chunks,
            context_budget=args.context_budget,
            hard_negative_files=hard_negative_files(sample),
        )
        packed = pack_files(
            repo,
            revision,
            ranked_paths,
            set(gold),
            corpus,
            args.context_budget,
        )
        metrics["BCY@8k"] = float(packed["bcy"])
        if observation.status != "ok":
            metrics = {name: 0.0 for name in metrics}
        detail = {
            "sample_id": case_id,
            "task_type": str(sample.get("task_type") or "unknown"),
            "repo": repo,
            "base_commit": revision,
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "gold_files": gold,
            "top_files": ranked_paths,
            "scores": observation.scores,
            "status": observation.status,
            "error": observation.error,
            "latency_ms": observation.latency_ms,
            "metrics": metrics,
            "bcy": packed,
            "provider_metadata": observation.metadata,
        }
        details.append(detail)
        print(
            json.dumps(
                {
                    "provider": provider.label,
                    "sample_id": case_id,
                    "status": observation.status,
                    "mrr": metrics["MRR"],
                    "recall_at_20": metrics["Recall@20"],
                    "bcy_at_8k": metrics["BCY@8k"],
                    "paths": len(ranked_paths),
                    "latency_ms": round(observation.latency_ms, 1),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        write_jsonl(args.details, details)
    summary = summarize(details, provider_label=provider.label)
    summary["skipped_unprovisioned"] = len(skipped)
    summary["skipped_samples"] = skipped
    summary.update(
        {
            "limit": args.limit,
            "provider_fetch_limit": args.provider_fetch_limit,
            "context_budget": args.context_budget,
            "details": str(args.details),
            "sample_files": [str(path) for path in args.samples],
            "source_manifest": str(args.sources),
            "corpus_manifest": str(args.corpus_manifest),
        }
    )
    write_json(args.summary, summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
