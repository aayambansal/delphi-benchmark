from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--samples", type=Path, action="append", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    valid_ids = {
        str(row["sample_id"])
        for row in read_jsonl(args.audit)
        if row.get("invalid") is False
    }
    candidates = [
        row
        for path in args.samples
        for row in read_jsonl(path)
        if str(row["id"]) in valid_ids
    ]
    candidates.sort(
        key=lambda row: (
            str(row.get("task_type") or ""),
            str(row.get("repo") or ""),
            str(row["id"]),
        )
    )

    selected: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    seen_repos: set[str] = set()
    for row in candidates:
        task = str(row.get("task_type") or "")
        repo = str(row.get("repo") or "")
        if task in seen_tasks or repo in seen_repos:
            continue
        selected.append(row)
        seen_tasks.add(task)
        seen_repos.add(repo)
    for row in candidates:
        if len(selected) >= args.limit:
            break
        repo = str(row.get("repo") or "")
        if repo in seen_repos or row in selected:
            continue
        selected.append(row)
        seen_repos.add(repo)
    for row in candidates:
        if len(selected) >= args.limit:
            break
        if row not in selected:
            selected.append(row)

    if len(selected) != args.limit:
        raise SystemExit(
            f"needed {args.limit} probe cases, found {len(selected)}"
        )
    for row in selected:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
