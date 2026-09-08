"""Restore the canonical git corpora from public GitHub.

Bare clones and materialized snapshots are not archived (they are re-clonable),
so a fresh checkout of this archive must rebuild them before any comparator
can run. Every `(repo, base_commit)` pair referenced by the given sample files
is cloned as a bare repository and the exact commit is verified (fetched by
SHA when the default clone does not contain it).

Usage:
    python -m harness.restore_corpora samples/final/*.jsonl samples/swebench/cases.jsonl \
        corpus/independent/v1/*.jsonl --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.gitcorpus import (  # noqa: E402
    BARE,
    clone_repo,
    fetch_commit,
    has_commit,
    needed_snapshots,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", nargs="+", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    started = time.monotonic()
    pairs = needed_snapshots([p for p in args.samples if p.is_file()])
    repos = sorted({repo for repo, _ in pairs})
    print(json.dumps({"repos": len(repos), "snapshots": len(pairs), "bare_root": str(BARE)}), flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(clone_repo, repos):
            print(json.dumps(result), flush=True)

    missing: list[tuple[str, str]] = []
    fetched = 0
    for repo, sha in pairs:
        if has_commit(repo, sha):
            continue
        if fetch_commit(repo, sha):
            fetched += 1
            print(json.dumps({"repo": repo, "sha": sha, "status": "fetched"}), flush=True)
        else:
            missing.append((repo, sha))
            print(json.dumps({"repo": repo, "sha": sha, "status": "missing"}), flush=True)

    report = {
        "repos": len(repos),
        "snapshots": len(pairs),
        "fetched_by_sha": fetched,
        "missing": [{"repo": r, "sha": s} for r, s in missing],
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }
    print(json.dumps(report), flush=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
