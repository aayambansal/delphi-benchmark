"""Prepare the Track D external eval: SWE-bench Verified file localization.

Downloads the dataset, draws a deterministic stratified subset, extracts
gold files from each instance's patch, and writes a samples jsonl shaped
like ARB cases (repo, base_commit, query, gold files) so the same runners
apply. Also clones the needed repos into the shared bare-corpus store.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from harness.gitcorpus import clone_repo, fetch_commit, has_commit  # noqa: E402

OUT = ROOT / "samples" / "swebench"
N_TOTAL = 60
SALT = "delphi-round3-swebench-v1"

PATCH_FILE_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)


def patch_files(patch: str) -> list[str]:
    files = []
    for match in PATCH_FILE_RE.finditer(patch or ""):
        path = match.group(2)
        if path not in files:
            files.append(path)
    return files


def main() -> None:
    import pyarrow.parquet as pq  # noqa: PLC0415

    url = ("https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/"
           "resolve/main/data/test-00000-of-00001.parquet")
    print("downloading SWE-bench Verified ...", flush=True)
    data = httpx.get(url, follow_redirects=True, timeout=300).content
    table = pq.read_table(io.BytesIO(data))
    rows = table.to_pylist()
    print(f"{len(rows)} instances", flush=True)

    by_repo: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_repo[row["repo"]].append(row)

    # Proportional allocation with at least 1 per repo, deterministic order.
    total = len(rows)
    picked: list[dict] = []
    for repo, repo_rows in sorted(by_repo.items()):
        quota = max(1, round(N_TOTAL * len(repo_rows) / total))
        ordered = sorted(
            repo_rows,
            key=lambda r: hashlib.sha256(f"{SALT}|{r['instance_id']}".encode()).hexdigest(),
        )
        picked.extend(ordered[:quota])
    picked.sort(key=lambda r: str(r["instance_id"]))
    picked = picked[:N_TOTAL + 5]

    OUT.mkdir(parents=True, exist_ok=True)
    kept = []
    for row in picked:
        gold = patch_files(row["patch"])
        if not gold:
            continue
        kept.append({
            "id": row["instance_id"],
            "repo": row["repo"],
            "base_commit": row["base_commit"],
            "task_type": "swebench_localization",
            "query": {"issue": row["problem_statement"][:6000]},
            "gold": {"files": gold},
        })
    with (OUT / "cases.jsonl").open("w") as fh:
        for row in kept:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"kept {len(kept)} cases across {len({r['repo'] for r in kept})} repos", flush=True)

    repos = sorted({r["repo"] for r in kept})
    for repo in repos:
        print(json.dumps(clone_repo(repo)), flush=True)
    missing = 0
    for row in kept:
        if not has_commit(row["repo"], row["base_commit"]):
            ok = fetch_commit(row["repo"], row["base_commit"])
            if not ok:
                missing += 1
                print(f"MISSING {row['repo']}@{row['base_commit']}", flush=True)
    print(json.dumps({"cases": len(kept), "repos": len(repos), "missing_commits": missing}), flush=True)


if __name__ == "__main__":
    main()
