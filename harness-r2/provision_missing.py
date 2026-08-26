"""Index the (repo, revision) pairs the final split needs but the corpus lacks.

The development split was fully provisioned; the final split reaches the same
repositories at different base commits, and 115 of those were never indexed.
Delphi can clone and index straight from a commit SHA, so this walks the gap
list and appends to the source manifest as each one lands.

Progress is appended incrementally so an interrupted run resumes instead of
restarting, which matters when a single large repository takes ten minutes.

Usage:
    python -m harness.provision_missing --workers 4
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "artifacts" / "development" / "delphi-openai-local-arb-sources.jsonl"
OUTPUT = ROOT / "artifacts" / "final" / "delphi-final-sources.jsonl"

_write_lock = threading.Lock()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def indexed_pairs(paths: list[Path]) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for path in paths:
        for row in read_jsonl(path):
            if row.get("status") in {"indexed", "reused"} and row.get("source_id"):
                found[(row["repo"], str(row["revision"]).lower())] = row["source_id"]
    return found


def needed_pairs(split: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for path in sorted((ROOT / "samples" / split).glob("v2_*.jsonl")):
        for sample in read_jsonl(path):
            if (sample.get("gold") or {}).get("no_gold") is True:
                continue
            pairs.add((sample["repo"], str(sample["base_commit"]).lower()))
    return pairs


def append(record: dict[str, Any]) -> None:
    with _write_lock:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="final")
    parser.add_argument("--base-url", default="http://127.0.0.1:20742")
    parser.add_argument("--api-key", default="delphi-benchmark-admin")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    already = indexed_pairs([SOURCES, OUTPUT])
    todo = sorted(needed_pairs(args.split) - set(already))
    print(f"{len(already)} pairs already indexed, {len(todo)} to go")

    client = httpx.Client(timeout=httpx.Timeout(3_600.0))
    done = 0
    total = len(todo)

    def index_one(pair: tuple[str, str]) -> None:
        nonlocal done
        repo, revision = pair
        started = time.time()
        try:
            response = client.post(
                f"{args.base_url}/v1/repositories/index",
                headers={"X-API-Key": args.api_key, "Content-Type": "application/json"},
                json={
                    "url": repo,
                    "branch": revision,
                    "quality_mode": "agent",
                    "include_tests": True,
                    "include_docs": True,
                    "include_examples": True,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - a failure is a recorded outcome
            append(
                {
                    "repo": repo,
                    "revision": revision,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                }
            )
            done += 1
            print(f"[{done}/{total}] FAILED {repo}@{revision[:12]} {type(exc).__name__}")
            return

        returned = str(payload.get("commit_sha") or "").lower()
        source_id = payload.get("repo_id")
        ok = bool(payload.get("success")) and returned == revision.lower()
        append(
            {
                "repo": repo,
                "revision": revision,
                "source_id": source_id,
                "status": "indexed" if ok else "failed",
                "error": None if ok else f"commit mismatch: got {returned}",
                "metadata": {
                    "files_indexed": payload.get("files_indexed"),
                    "chunks_created": payload.get("chunks_created"),
                    "indexing_time_ms": payload.get("indexing_time_ms"),
                },
            }
        )
        done += 1
        print(
            f"[{done}/{total}] {'ok' if ok else 'MISMATCH'} {repo}@{revision[:12]} "
            f"files={payload.get('files_indexed')} "
            f"chunks={payload.get('chunks_created')} "
            f"{time.time() - started:.0f}s"
        )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(index_one, todo))

    final = indexed_pairs([SOURCES, OUTPUT])
    remaining = needed_pairs(args.split) - set(final)
    print(f"\ndone. indexed={len(final)} still_missing={len(remaining)}")


if __name__ == "__main__":
    main()
