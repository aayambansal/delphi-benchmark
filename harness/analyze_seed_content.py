"""What the pilot seeds actually contained.

Two questions raised about the executable pilot:

1. The file-head seed carries the first 40 lines of each named file. How often
   did the head include the region the gold patch edits? (If the edit sits at
   line 700, the agent received a path and a header, not the implementation.)
2. The random control excludes gold files, but "non-gold" is not "uninformative".
   What kinds of files did the random block name, and how close were they to
   the gold files?

    python harness/analyze_seed_content.py

Reads the pilot dataset manifests and the SWE-bench Verified gold patches; writes
results/pilot/seed-content-analysis.json.
"""
from __future__ import annotations

import io
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ROOT / "results" / "pilot" / "datasets"
VERIFIED = ROOT / "cache" / "swebench_verified.parquet"

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def gold_hunks(patch: str) -> dict[str, list[tuple[int, int]]]:
    """Old-file line ranges edited by the patch, per file path."""
    out: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in patch.splitlines():
        if line.startswith("--- "):
            target = line[4:].strip()
            current = None if target == "/dev/null" else target[2:] if target.startswith("a/") else target
        elif line.startswith("+++ ") and current is None:
            target = line[4:].strip()
            current = target[2:] if target.startswith("b/") else target
        elif line.startswith("@@") and current is not None:
            m = HUNK.match(line)
            if m:
                start = int(m.group(1))
                length = int(m.group(2) or "1")
                out.setdefault(current, []).append((start, start + max(length, 1) - 1))
    return out


def sections(statement: str) -> dict[str, tuple[int, int] | None]:
    """Seed sections present in a problem statement: path -> (start, end) or None for path-only."""
    out: dict[str, tuple[int, int] | None] = {}
    block = statement.split("<retrieved_context>", 1)[-1]
    for m in re.finditer(r"^### (\S+)(?: \(lines (\d+)-(\d+)\))?$", block, re.M):
        out[m.group(1)] = (int(m.group(2)), int(m.group(3))) if m.group(2) else None
    return out


def load_verified() -> dict[str, dict]:
    import pyarrow.parquet as pq

    rows = pq.read_table(io.BytesIO(VERIFIED.read_bytes())).to_pylist()
    return {str(r["instance_id"]): r for r in rows}


def analyze_heads(label: str, verified: dict[str, dict]) -> dict:
    manifest = json.load((DATASETS / label / "manifest.json").open())
    statements = {json.loads(l)["instance_id"]: json.loads(l)["problem_statement"] for l in (DATASETS / label / "test.jsonl").open() if l.strip()}
    seeded_gold_files = 0
    head_covers_edit = 0
    head_present = 0
    instances_with_gold = 0
    instances_head_covers = 0
    depth: list[int] = []
    for m in manifest:
        iid = m["instance_id"]
        hunks = gold_hunks(str(verified[iid]["patch"]))
        secs = sections(statements[iid])
        gold_seeded = [p for p in m["seed_files"] if p in set(m["gold_files"])]
        if gold_seeded:
            instances_with_gold += 1
        covered_any = False
        for path in gold_seeded:
            seeded_gold_files += 1
            span = secs.get(path)
            ranges = hunks.get(path, [])
            if ranges:
                depth.append(min(s for s, _ in ranges))
            if span is None:
                continue
            head_present += 1
            lo, hi = span
            if any(s <= hi and e >= lo for s, e in ranges):
                head_covers_edit += 1
                covered_any = True
        if covered_any:
            instances_head_covers += 1
    depth_sorted = sorted(depth)
    return {
        "label": label,
        "instances": len(manifest),
        "instances_with_seeded_gold": instances_with_gold,
        "seeded_gold_files": seeded_gold_files,
        "seeded_gold_files_with_content": head_present,
        "seeded_gold_files_whose_content_covers_an_edit": head_covers_edit,
        "instances_where_some_seeded_content_covers_an_edit": instances_head_covers,
        "first_edited_line_in_seeded_gold_files": {
            "median": depth_sorted[len(depth_sorted) // 2] if depth_sorted else None,
            "share_within_40": sum(1 for d in depth_sorted if d <= 40) / len(depth_sorted) if depth_sorted else None,
            "share_beyond_200": sum(1 for d in depth_sorted if d > 200) / len(depth_sorted) if depth_sorted else None,
        },
    }


def analyze_random(label: str) -> dict:
    manifest = json.load((DATASETS / label / "manifest.json").open())
    kinds: Counter = Counter()
    same_dir = same_pkg = total = 0
    instances_same_dir = 0
    for m in manifest:
        gold_dirs = {str(Path(g).parent) for g in m["gold_files"]}
        gold_pkgs = {"/".join(Path(g).parts[:2]) for g in m["gold_files"]}
        hit_dir = False
        for p in m["seed_files"]:
            total += 1
            low = p.lower()
            if "test" in low:
                kinds["test"] += 1
            elif low.endswith((".rst", ".md", ".txt")):
                kinds["docs"] += 1
            elif low.endswith(".py"):
                kinds["python_source"] += 1
            else:
                kinds["other"] += 1
            if str(Path(p).parent) in gold_dirs:
                same_dir += 1
                hit_dir = True
            if "/".join(Path(p).parts[:2]) in gold_pkgs:
                same_pkg += 1
        if hit_dir:
            instances_same_dir += 1
    return {
        "label": label,
        "instances": len(manifest),
        "seed_files": total,
        "kinds": dict(kinds),
        "share_same_directory_as_a_gold_file": same_dir / total if total else None,
        "share_same_top_level_package_as_a_gold_file": same_pkg / total if total else None,
        "instances_with_a_same_directory_file": instances_same_dir,
    }


def main() -> None:
    verified = load_verified()
    out = {
        "schema": "pilot_seed_content_v1",
        "heads": analyze_heads("delphi", verified),
        "chunks": analyze_heads("delphi_chunks", verified) if (DATASETS / "delphi_chunks").exists() else None,
        "conventional_heads": analyze_heads("hybrid_rerank_expand", verified),
        "random": analyze_random("random"),
    }
    path = ROOT / "results" / "pilot" / "seed-content-analysis.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
