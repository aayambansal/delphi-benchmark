"""Snapshot-parallel BM25 + lexical evaluation for offload machines.

Groups cases by (repo, base_commit), builds the ARB-style chunk corpus once
per snapshot, ranks with the official ARB bm25 and lexical rankers, scores
with the official metrics, and writes details + summary per engine. Pure
stdlib + git; safe on Windows (spawn) and POSIX.

Usage:
  python -m harness.vm_corpus_eval --split development --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from statistics import fmean, median

ROOT = Path(__file__).resolve().parent.parent
R2 = ROOT.parent / "delphi-evaluation-2026-07-29-round2"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str((R2 / "external" / "arb-src" / "src").resolve()))

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".whl", ".jar", ".class", ".so", ".dylib", ".dll", ".exe", ".bin",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".webm", ".ogg",
    ".pyc", ".wasm", ".onnx", ".pt", ".pack", ".idx", ".parquet", ".npy",
    ".npz", ".h5", ".lock",
}
ENGINES = ("bm25", "lexical")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def eval_snapshot(job: tuple[str, str, list[dict], int, tuple[str, ...]]) -> list[dict]:
    """Worker: evaluate every case of one snapshot for the requested engines."""
    repo, commit, cases, limit, engines = job
    from agent_retrieval_bench.baseline import (
        hard_negative_files,
        query_text_for_eval,
        rank_chunks_bm25_with_scores,
        rank_chunks_with_scores,
        sample_metrics,
        target_gold_files,
    )
    from agent_retrieval_bench.bcy_curve import pack_files
    from agent_retrieval_bench.corpus import chunks_for_file, is_candidate_path

    from harness.gitcorpus import GitCorpus

    corpus = GitCorpus()
    chunks: list[dict] = []
    for path in corpus.list_files(repo, commit):
        if Path(path).suffix.lower() in BINARY_EXT or not is_candidate_path(path):
            continue
        text = corpus.file_text(repo, commit, path)
        if text is None or not text.strip() or len(text) > 1_500_000:
            continue
        chunks.extend(chunks_for_file(repo, commit, path, text))

    rows: list[dict] = []
    for sample in cases:
        gold = target_gold_files(sample)
        query = query_text_for_eval(sample)
        for engine in engines:
            started = time.perf_counter()
            ranker = rank_chunks_bm25_with_scores if engine == "bm25" else rank_chunks_with_scores
            try:
                ranked_chunks = ranker(query, chunks)
                paths: list[str] = []
                for _, chunk in ranked_chunks:
                    p = str(chunk.get("path") or "")
                    if p and p not in paths:
                        paths.append(p)
                    if len(paths) >= limit:
                        break
                status, error = "ok", None
            except Exception as exc:  # noqa: BLE001
                paths, status, error = [], "error", f"{type(exc).__name__}: {exc}"[:300]
            latency_ms = (time.perf_counter() - started) * 1000
            ranked_for_metrics = [
                {"path": p, "text": corpus.file_text(repo, commit, p) or "", "kind": "file"}
                for p in paths
            ]
            metrics = sample_metrics(
                gold, ranked_for_metrics, context_budget=8000,
                hard_negative_files=hard_negative_files(sample),
            )
            packed = pack_files(repo, commit, paths, set(gold), corpus, 8000)
            metrics["BCY@8k"] = float(packed["bcy"])
            if status != "ok":
                metrics = {name: 0.0 for name in metrics}
            rows.append({
                "engine": engine,
                "sample_id": str(sample["id"]),
                "task_type": str(sample.get("task_type") or "unknown"),
                "repo": repo, "base_commit": commit,
                "gold_files": gold, "top_files": paths,
                "status": status, "error": error,
                "latency_ms": latency_ms, "metrics": metrics,
            })
    return rows


def mean_metrics(rows: list[dict]) -> dict[str, float]:
    if not rows:
        return {}
    names = sorted(set.intersection(*(set(r["metrics"]) for r in rows)))
    return {n: fmean(float(r["metrics"][n]) for r in rows) for n in names}


def macro(rows: list[dict], key: str) -> dict[str, float]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    means = [mean_metrics(g) for g in groups.values()]
    if not means:
        return {}
    names = sorted(set.intersection(*(set(m) for m in means)))
    return {n: fmean(m[n] for m in means) for n in names}


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    lats = [r["latency_ms"] for r in ok]
    return {
        "n": len(rows),
        "failures": len(rows) - len(ok),
        "sample_weighted": mean_metrics(rows),
        "repo_macro": macro(rows, "repo"),
        "workflow_macro": macro(rows, "task_type"),
        "by_workflow": {
            wf: {"n": len(g), "metrics": mean_metrics(g)}
            for wf in sorted({r["task_type"] for r in rows})
            for g in [[r for r in rows if r["task_type"] == wf]]
        },
        "latency_ms": {"mean": fmean(lats), "median": median(lats)} if lats else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", required=True, choices=("development", "final"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--engines",
        default="bm25,lexical",
        help="comma-separated subset of bm25,lexical",
    )
    args = parser.parse_args()
    requested = tuple(e.strip() for e in args.engines.split(",") if e.strip())
    unknown = [e for e in requested if e not in ENGINES]
    if unknown:
        raise SystemExit(f"unknown engines {unknown}; allowed {ENGINES}")

    samples = []
    for wf in ("v2_code2test", "v2_comment2context", "v2_trace2code", "v2_edit2ripple"):
        for row in read_jsonl(ROOT / "samples" / args.split / f"{wf}.jsonl"):
            if (row.get("gold") or {}).get("no_gold") is not True:
                samples.append(row)

    by_snapshot: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for sample in samples:
        by_snapshot[(str(sample["repo"]), str(sample["base_commit"]))].append(sample)
    jobs = [(repo, commit, cases, args.limit, requested)
            for (repo, commit), cases in sorted(by_snapshot.items())]
    print(f"{len(samples)} cases across {len(jobs)} snapshots, {args.workers} workers", flush=True)

    all_rows: list[dict] = []
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(eval_snapshot, job): job[:2] for job in jobs}
        for future in as_completed(futures):
            repo, commit = futures[future]
            try:
                rows = future.result()
            except Exception as exc:  # noqa: BLE001
                print(json.dumps({"snapshot": f"{repo}@{commit[:10]}",
                                  "error": f"{type(exc).__name__}: {exc}"[:200]}), flush=True)
                continue
            all_rows.extend(rows)
            done += 1
            print(json.dumps({"done": done, "total": len(jobs),
                              "snapshot": f"{repo}@{commit[:10]}",
                              "rows": len(rows)}), flush=True)

    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    for engine in requested:
        rows = sorted((r for r in all_rows if r["engine"] == engine),
                      key=lambda r: r["sample_id"])
        details = results / f"vm-{engine}-{args.split}-details.jsonl"
        with details.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
        summary = summarize(rows)
        (results / f"vm-{engine}-{args.split}-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"engine": engine, "split": args.split,
                          "MRR": summary["sample_weighted"].get("MRR"),
                          "R@20": summary["sample_weighted"].get("Recall@20")}), flush=True)


if __name__ == "__main__":
    main()
