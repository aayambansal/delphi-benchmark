"""Blog vignettes: real developer questions, three ways.

Not benchmark queries — the questions a developer actually types. Each runs
against Delphi (July stack), Nia (query mode), and git grep over the same
snapshot, capturing what came back and how long it took. Transcripts feed
the blog post; results also land in the runstore under track "V-vignettes".
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R2 = ROOT.parent / "delphi-evaluation-2026-07-29-round2"
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from harness.gitcorpus import bare_path  # noqa: E402
from harness.runstore import RunWriter  # noqa: E402

VIGNETTES = [
    {
        "id": "gin-html-escape",
        "repo": "gin-gonic/gin",
        "question": "why does my JSON response get HTML-escaped and how do I turn that off?",
        "grep_terms": ["SetEscapeHTML", "escape"],
        "answer_files": ["render/json.go", "context.go"],
    },
    {
        "id": "tokio-joinhandle-drop",
        "repo": "tokio-rs/tokio",
        "question": "what happens when I drop a JoinHandle, does the spawned task keep running?",
        "grep_terms": ["JoinHandle", "detach"],
        "answer_files": ["tokio/src/task/join.rs", "tokio/src/runtime/task/mod.rs"],
    },
    {
        "id": "pytest-assert-rewrite",
        "repo": "pytest-dev/pytest",
        "question": "where is the logic that rewrites assert statements into detailed failure messages?",
        "grep_terms": ["rewrite", "assertion"],
        "answer_files": ["src/_pytest/assertion/rewrite.py"],
    },
]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open() if line.strip()]


def pick_snapshot(repo: str, delphi_sources: list[dict], nia_sources: list[dict]):
    delphi_by_rev = {r["revision"].lower(): r for r in delphi_sources
                     if r["repo"] == repo and r["status"] in ("indexed", "reused")}
    for row in nia_sources:
        if row["repo"] == repo and row.get("status") == "indexed":
            rev = row["revision"].lower()
            if rev in delphi_by_rev:
                return rev, delphi_by_rev[rev], row
    return None, None, None


def delphi_search(question: str, source_id, k: int = 8) -> dict:
    started = time.perf_counter()
    resp = httpx.post(
        "http://127.0.0.1:20742/v1/search/code",
        headers={"X-API-Key": "delphi-benchmark-admin"},
        json={"query": question,
              "repo_ids": [source_id] if isinstance(source_id, str) else list(source_id),
              "top_k": 30},
        timeout=180,
    )
    resp.raise_for_status()
    payload = resp.json()
    files, snippets = [], []
    for row in payload.get("results", []):
        fp = row.get("file_path")
        if fp and fp not in files:
            files.append(fp)
            snippets.append({"path": fp, "lines": f"{row.get('start_line')}-{row.get('end_line')}",
                             "head": (row.get("content") or "")[:250]})
        if len(files) >= k:
            break
    return {"latency_s": round(time.perf_counter() - started, 2), "files": files,
            "snippets": snippets[:5]}


def nia_search(question: str, folder_ids: list[str], k: int = 8) -> dict:
    started = time.perf_counter()
    resp = httpx.post(
        "https://apigcp.trynia.ai/v2/search",
        headers={"Authorization": f"Bearer {os.environ['NIA_API_KEY']}"},
        json={"mode": "query", "messages": [{"role": "user", "content": question}],
              "local_folders": folder_ids, "search_mode": "sources",
              "include_sources": True, "fast_mode": True, "skip_llm": False,
              "reasoning_strategy": "hybrid", "max_tokens": 4000,
              "bypass_semantic_cache": True, "include_follow_ups": False},
        timeout=300,
    )
    resp.raise_for_status()
    payload = resp.json()
    files = []
    for src in payload.get("sources", []):
        raw = src if isinstance(src, str) else (
            src.get("file_path") or src.get("path")
            or (src.get("metadata") or {}).get("file_path") or "")
        raw = str(raw).split("#")[0].lstrip("/")
        for marker in ("/arb/", "/arb3/", "arb-v2-sharded/"):
            if marker in raw:
                raw = raw.split(marker, 1)[1].split("/", 3)[-1]
        if raw and raw not in files:
            files.append(raw)
        if len(files) >= k:
            break
    return {"latency_s": round(time.perf_counter() - started, 2), "files": files,
            "answer_head": str(payload.get("content") or "")[:900]}


def grep_search(question_terms: list[str], repo: str, rev: str, k: int = 8) -> dict:
    started = time.perf_counter()
    counts: dict[str, int] = {}
    for term in question_terms:
        proc = subprocess.run(
            ["git", "-C", str(bare_path(repo)), "grep", "-i", "-c", term, rev],
            capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            try:
                _, path_count = line.split(":", 1)
                path, count = path_count.rsplit(":", 1)
                counts[path] = counts.get(path, 0) + int(count)
            except ValueError:
                continue
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
    return {"latency_s": round(time.perf_counter() - started, 2),
            "files": [p for p, _ in ranked],
            "match_counts": dict(ranked)}


def main() -> None:
    delphi_sources = read_jsonl(R2 / "artifacts" / "final" / "delphi-all-sources.jsonl")
    nia_sources = read_jsonl(ROOT / "results" / "nia-sources.jsonl")
    writer = RunWriter(track="V-vignettes", system="three-way",
                       config={"systems": ["delphi-jul", "nia", "git-grep"]},
                       split="vignettes")
    print(f"run_id={writer.run_id}", flush=True)
    transcript = []
    for vignette in VIGNETTES:
        rev, delphi_row, nia_row = pick_snapshot(vignette["repo"], delphi_sources, nia_sources)
        if rev is None:
            print(json.dumps({"vignette": vignette["id"], "skip": "no shared snapshot"}), flush=True)
            continue
        source_id = delphi_row["source_id"]
        shards = (delphi_row.get("metadata") or {}).get("source_ids")
        if isinstance(shards, list) and shards:
            source_id = shards
        nia_ids = (nia_row.get("metadata") or {}).get("source_ids") or [nia_row["source_id"]]
        entry = {"vignette": vignette["id"], "repo": vignette["repo"], "rev": rev,
                 "question": vignette["question"], "answer_files": vignette["answer_files"]}
        try:
            entry["delphi"] = delphi_search(vignette["question"], source_id)
        except Exception as exc:  # noqa: BLE001
            entry["delphi"] = {"error": str(exc)[:200]}
        try:
            entry["nia"] = nia_search(vignette["question"], list(nia_ids))
        except Exception as exc:  # noqa: BLE001
            entry["nia"] = {"error": str(exc)[:200]}
        entry["grep"] = grep_search(vignette["grep_terms"], vignette["repo"], rev)

        def hit(files: list[str]) -> bool:
            return any(any(ans in f or f in ans for ans in vignette["answer_files"]) for f in files)

        metrics = {
            "delphi_hit": float(hit(entry["delphi"].get("files", []))),
            "nia_hit": float(hit(entry["nia"].get("files", []))),
            "grep_hit": float(hit(entry["grep"].get("files", []))),
            "delphi_latency_s": entry["delphi"].get("latency_s"),
            "nia_latency_s": entry["nia"].get("latency_s"),
            "grep_latency_s": entry["grep"].get("latency_s"),
        }
        writer.case(case_id=vignette["id"], workflow="vignette", repo=vignette["repo"],
                    revision=rev, ok=True, metrics=metrics, trace=entry)
        transcript.append(entry)
        print(json.dumps({k: v for k, v in metrics.items()}), flush=True)
    writer.finish({"n": len(transcript)})
    (ROOT / "blog" / "vignette-transcripts.json").write_text(
        json.dumps(transcript, indent=2, ensure_ascii=False) + "\n")
    print("saved transcripts", flush=True)


if __name__ == "__main__":
    main()
