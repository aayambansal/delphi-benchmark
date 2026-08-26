"""Clone the bare corpus repos needed by the round-3 splits (offload machine).

Reads (repo, base_commit) pairs from round3/samples/{development,final} and
clones/fetches into round3/corpus/bare. Pure stdlib + git.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.gitcorpus import clone_repo, fetch_commit, has_commit  # noqa: E402


def main() -> None:
    pairs: dict[tuple[str, str], None] = {}
    for split in ("development", "final"):
        for wf in ("v2_code2test", "v2_comment2context", "v2_trace2code", "v2_edit2ripple"):
            path = ROOT / "samples" / split / f"{wf}.jsonl"
            for line in path.open(encoding="utf-8"):
                if not line.strip():
                    continue
                row = json.loads(line)
                pairs[(str(row["repo"]), str(row["base_commit"]))] = None
    repos = sorted({repo for repo, _ in pairs})
    print(f"{len(repos)} repos, {len(pairs)} snapshots", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(clone_repo, repos):
            print(json.dumps(result), flush=True)
    missing = 0
    for repo, sha in pairs:
        if not has_commit(repo, sha) and not fetch_commit(repo, sha):
            missing += 1
            print(json.dumps({"repo": repo, "sha": sha, "status": "missing"}), flush=True)
    print(json.dumps({"repos": len(repos), "snapshots": len(pairs), "missing": missing}), flush=True)


if __name__ == "__main__":
    main()
