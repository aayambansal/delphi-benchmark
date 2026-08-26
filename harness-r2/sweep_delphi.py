"""Fast ARB dev-split sweep against a live Delphi instance.

The full ``run_static_retrieval`` runner also computes BCY and packs corpus
files, which is the right thing for a reportable number and too slow for the
inner loop of tuning. This runner scores ranking metrics only, concurrently,
so a configuration change can be evaluated in a couple of minutes.

Metrics come from the pinned Agent Retrieval Bench source, not a
reimplementation, so sweep numbers are directly comparable to the reportable
ones.

Usage:
    python -m harness.sweep_delphi --label rrf-default
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARB_SRC = ROOT / "external" / "arb-src" / "src"
DEFAULT_SOURCES = (
    ROOT / "artifacts" / "development" / "delphi-openai-local-arb-sources.jsonl"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_samples(split: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((ROOT / "samples" / split).glob("v2_*.jsonl")):
        for row in read_jsonl(path):
            # Abstention cases have no gold and are scored separately.
            if (row.get("gold") or {}).get("no_gold") is True:
                continue
            rows.append(row)
    return rows


def source_index() -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for row in read_jsonl(DEFAULT_SOURCES):
        if row.get("status") in {"indexed", "reused"} and row.get("source_id"):
            index[(row["repo"], str(row["revision"]).lower())] = row["source_id"]
    return index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--split", default="development")
    parser.add_argument("--base-url", default="http://127.0.0.1:20742")
    parser.add_argument("--api-key", default="delphi-benchmark-admin")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--fetch", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "iter")
    args = parser.parse_args()

    sys.path.insert(0, str(DEFAULT_ARB_SRC))
    from agent_retrieval_bench.baseline import (  # noqa: PLC0415
        query_text_for_eval,
        sample_metrics,
        target_gold_files,
    )

    samples = load_samples(args.split)
    sources = source_index()
    client = httpx.Client(timeout=180.0)

    def run_one(sample: dict[str, Any]) -> dict[str, Any] | None:
        source_id = sources.get(
            (sample["repo"], str(sample["base_commit"]).lower())
        )
        if not source_id:
            return None
        gold = target_gold_files(sample)
        if not gold:
            return None
        started = time.perf_counter()
        try:
            response = client.post(
                f"{args.base_url}/v1/search/code",
                headers={"X-API-Key": args.api_key},
                json={
                    "query": query_text_for_eval(sample),
                    "repo_ids": [source_id],
                    "top_k": args.fetch,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - a failed query is a data point
            return {
                "sample_id": sample["id"],
                "task_type": sample["task_type"],
                "error": type(exc).__name__,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        latency_ms = (time.perf_counter() - started) * 1000

        files: list[str] = []
        for row in payload.get("results") or []:
            path = row.get("file_path")
            if path and path not in files:
                files.append(path)
            if len(files) >= args.limit:
                break

        # ARB reads the ``path`` key off each ranked chunk, not ``file_path``.
        ranked_chunks = [{"path": path} for path in files]
        metrics = sample_metrics(gold, ranked_chunks, context_budget=8000)
        return {
            "sample_id": sample["id"],
            "task_type": sample["task_type"],
            "repo": sample["repo"],
            "gold_files": gold,
            "top_files": files,
            "metrics": metrics,
            "latency_ms": latency_ms,
        }

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        details = [row for row in pool.map(run_one, samples) if row]

    ok = [row for row in details if "metrics" in row]
    by_workflow: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ok:
        by_workflow[row["task_type"]].append(row)

    def mean_of(rows: list[dict[str, Any]], key: str) -> float:
        values = [r["metrics"].get(key, 0.0) for r in rows]
        return statistics.fmean(values) if values else 0.0

    keys = ("MRR", "Recall@5", "Recall@20", "Precision@20", "gold_coverage@8k")
    summary: dict[str, Any] = {
        "label": args.label,
        "split": args.split,
        "n": len(ok),
        "errors": len(details) - len(ok),
        "latency_ms": {
            "mean": statistics.fmean([r["latency_ms"] for r in details]),
            "median": statistics.median([r["latency_ms"] for r in details]),
        },
        "by_workflow": {
            name: {"n": len(rows), **{k: mean_of(rows, k) for k in keys}}
            for name, rows in sorted(by_workflow.items())
        },
        "sample_weighted": {k: mean_of(ok, k) for k in keys},
        "workflow_macro": {
            k: statistics.fmean([mean_of(rows, k) for rows in by_workflow.values()])
            for k in keys
        },
    }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{args.label}-details.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in details) + "\n",
        encoding="utf-8",
    )
    (args.out / f"{args.label}-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"\n=== {args.label} ({summary['n']} samples, {summary['errors']} errors) ===")
    header = f"{'workflow':<18}{'n':>4}" + "".join(f"{k:>13}" for k in keys)
    print(header)
    for name, row in summary["by_workflow"].items():
        print(
            f"{name:<18}{row['n']:>4}"
            + "".join(f"{row[k]:>13.3f}" for k in keys)
        )
    for scope in ("sample_weighted", "workflow_macro"):
        print(
            f"{scope:<18}{'':>4}"
            + "".join(f"{summary[scope][k]:>13.3f}" for k in keys)
        )
    print(
        f"latency mean={summary['latency_ms']['mean']:.0f}ms "
        f"median={summary['latency_ms']['median']:.0f}ms"
    )


if __name__ == "__main__":
    main()
