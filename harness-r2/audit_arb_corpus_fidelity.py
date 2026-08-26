from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


TRUNCATION_MARKER = re.compile(
    r"(?:^|\n)\.\.\.\[truncated\](?:\d+ bytes)?(?:\n|$)"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def path_values(values: list[Any]) -> list[str]:
    paths: list[str] = []
    for value in values:
        if isinstance(value, str):
            paths.append(value)
        elif isinstance(value, dict) and isinstance(value.get("path"), str):
            paths.append(value["path"])
    return list(dict.fromkeys(paths))


def target_gold_files(sample: dict[str, Any]) -> list[str]:
    gold = sample.get("gold") or {}
    if gold.get("no_gold") is True:
        return []
    explicit = path_values(gold.get("files") or [])
    if explicit:
        return explicit
    if sample.get("task_type") == "code2test":
        return path_values(gold.get("related_tests") or [])
    if sample.get("task_type") == "comment2context":
        context = path_values(
            gold.get("must_context_files")
            or gold.get("context_files")
            or []
        )
        if context:
            return context
    root = path_values(gold.get("root_cause_files") or [])
    return root or path_values(gold.get("related_tests") or [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, action="append", required=True)
    parser.add_argument("--keep-list", type=Path, required=True)
    parser.add_argument("--corpus-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    keep_ids = {
        str(row.get("id") or row.get("sample_id"))
        for row in read_jsonl(args.keep_list)
    }
    samples = [
        row
        for path in args.samples
        for row in read_jsonl(path)
        if str(row["id"]) in keep_ids
    ]
    roots = {
        (str(row["repo"]), str(row["revision"]).lower()): Path(row["path"])
        for row in read_jsonl(args.corpus_manifest)
    }

    output: list[dict[str, Any]] = []
    for sample in samples:
        root = roots[
            (str(sample["repo"]), str(sample["base_commit"]).lower())
        ]
        target_ends: dict[str, int] = {}
        for item in [
            *sample.get("gold_spans", []),
            *sample.get("gold_blocks", []),
        ]:
            path = item.get("path")
            end_line = item.get("end_line")
            if isinstance(path, str) and isinstance(end_line, int):
                target_ends[path] = max(target_ends.get(path, 0), end_line)

        gold_files = target_gold_files(sample)
        file_results: list[dict[str, Any]] = []
        for relative_path in gold_files:
            absolute_path = root / relative_path
            if not absolute_path.is_file():
                file_results.append(
                    {
                        "path": relative_path,
                        "status": "missing",
                        "target_end_line": target_ends.get(relative_path),
                    }
                )
                continue
            content = absolute_path.read_text(encoding="utf-8", errors="replace")
            line_count = len(content.splitlines())
            marker_present = bool(TRUNCATION_MARKER.search(content))
            target_end = target_ends.get(relative_path)
            if marker_present:
                status = "truncated_marker"
            elif target_end is not None and line_count < target_end:
                status = "shorter_than_gold_span"
            else:
                status = "available"
            file_results.append(
                {
                    "path": relative_path,
                    "status": status,
                    "line_count": line_count,
                    "target_end_line": target_end,
                }
            )

        statuses = Counter(row["status"] for row in file_results)
        invalid = any(row["status"] != "available" for row in file_results)
        output.append(
            {
                "sample_id": str(sample["id"]),
                "task_type": str(sample["task_type"]),
                "repo": str(sample["repo"]),
                "invalid": invalid,
                "status_counts": dict(statuses),
                "files": file_results,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in output) + "\n",
        encoding="utf-8",
    )
    summary = {
        "evaluated": len(output),
        "invalid_samples": sum(bool(row["invalid"]) for row in output),
        "valid_samples": sum(not bool(row["invalid"]) for row in output),
        "file_statuses": dict(
            Counter(
                file_result["status"]
                for row in output
                for file_result in row["files"]
            )
        ),
        "invalid_by_task": dict(
            Counter(
                str(row["task_type"])
                for row in output
                if bool(row["invalid"])
            )
        ),
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
