"""Draw additional SWE-bench Verified localization cases that were never used.

Round 3 scored 62 stratified instances (samples/swebench/cases.jsonl). The
remaining Verified instances were never touched by any development or
confirmatory work, so they can extend the genuinely unexposed primary
evaluation. This draws a further deterministic, repo-proportional sample that
excludes every round-3 instance id and every previously used base commit,
using a new salt so the choice cannot depend on round-3 outcomes.

Output: samples/swebench/cases-r4-expansion.jsonl in the same schema as the
round-3 file, plus a manifest recording the draw.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from harness.prep_swebench import patch_files  # noqa: E402

OUT_DIR = ROOT / "samples" / "swebench"
PARQUET_URL = (
    "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/"
    "resolve/main/data/test-00000-of-00001.parquet"
)


def load_rows(cache: Path) -> list[dict]:
    import pyarrow.parquet as pq

    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        data = httpx.get(PARQUET_URL, follow_redirects=True, timeout=600).content
        cache.write_bytes(data)
    return pq.read_table(io.BytesIO(cache.read_bytes())).to_pylist()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--salt", default="delphi-round4-swebench-expansion-v1")
    parser.add_argument("--existing", type=Path, default=OUT_DIR / "cases.jsonl")
    parser.add_argument("--output", type=Path, default=OUT_DIR / "cases-r4-expansion.jsonl")
    parser.add_argument("--manifest", type=Path, default=OUT_DIR / "cases-r4-expansion-manifest.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "cache" / "swebench_verified.parquet")
    args = parser.parse_args()

    rows = load_rows(args.cache)
    existing = [json.loads(line) for line in args.existing.open() if line.strip()]
    used_ids = {str(r["id"]) for r in existing}
    used_commits = {str(r["base_commit"]) for r in existing}

    eligible = [
        r for r in rows
        if str(r["instance_id"]) not in used_ids
        and str(r["base_commit"]) not in used_commits
        and patch_files(r["patch"])
    ]
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for r in eligible:
        by_repo[r["repo"]].append(r)
    total = len(eligible)
    picked: list[dict] = []
    quotas: dict[str, int] = {}
    for repo, repo_rows in sorted(by_repo.items()):
        quota = max(1, round(args.n * len(repo_rows) / total))
        quotas[repo] = quota
        ordered = sorted(
            repo_rows,
            key=lambda r: hashlib.sha256(f"{args.salt}|{r['instance_id']}".encode()).hexdigest(),
        )
        picked.extend(ordered[:quota])
    # Trim to exactly n by the same hash order so the draw stays deterministic.
    picked.sort(key=lambda r: hashlib.sha256(f"{args.salt}|{r['instance_id']}".encode()).hexdigest())
    picked = picked[: args.n]
    picked.sort(key=lambda r: str(r["instance_id"]))

    cases = [
        {
            "id": r["instance_id"],
            "repo": r["repo"],
            "base_commit": r["base_commit"],
            "task_type": "swebench_localization",
            "query": {"issue": r["problem_statement"][:6000]},
            "gold": {"files": patch_files(r["patch"])},
        }
        for r in picked
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {
        "schema": "swebench_expansion_draw_v1",
        "source": PARQUET_URL,
        "dataset_instances": len(rows),
        "excluded_round3_ids": len(used_ids),
        "excluded_round3_commits": len(used_commits),
        "eligible": total,
        "salt": args.salt,
        "requested": args.n,
        "drawn": len(cases),
        "repo_quotas": quotas,
        "repo_counts": dict(Counter(c["repo"] for c in cases)),
        "unique_snapshots": len({(c["repo"], c["base_commit"]) for c in cases}),
        "instance_ids": [c["id"] for c in cases],
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "instance_ids"}, sort_keys=True))


if __name__ == "__main__":
    main()
