from __future__ import annotations

import argparse
import ast
import json
from itertools import combinations
from pathlib import Path
from statistics import fmean
from typing import Any


def item_identity(item: dict[str, Any]) -> str:
    raw_id = str(item.get("raw_id") or item.get("path") or "")
    if raw_id.startswith("{"):
        try:
            source = ast.literal_eval(raw_id)
        except (SyntaxError, ValueError):
            source = None
        if isinstance(source, dict):
            metadata = source.get("metadata")
            if isinstance(metadata, dict):
                path = (
                    metadata.get("file_path")
                    or metadata.get("sourceURL")
                    or metadata.get("source_url")
                )
                if path:
                    start = metadata.get("start_line", "")
                    end = metadata.get("end_line", "")
                    return f"{path}:{start}:{end}"
    if raw_id:
        return raw_id
    stable = {
        key: value
        for key, value in item.items()
        if key not in {"rank", "score"}
    }
    return json.dumps(stable, sort_keys=True, default=str)


def _run_by_case(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {str(row["case_id"]): row for row in rows}
    if len(result) != len(rows):
        raise ValueError("each run must contain unique case IDs")
    return result


def _item_set(row: dict[str, Any]) -> set[str]:
    items = row.get("items")
    if not isinstance(items, list):
        return set()
    return {
        item_identity(item)
        for item in items
        if isinstance(item, dict)
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def analyze_runs(runs: list[list[dict[str, Any]]]) -> dict[str, Any]:
    if len(runs) < 2:
        raise ValueError("determinism analysis requires at least two runs")
    indexed = [_run_by_case(rows) for rows in runs]
    case_ids = set(indexed[0])
    if not case_ids:
        raise ValueError("determinism runs must not be empty")
    if any(set(run) != case_ids for run in indexed[1:]):
        raise ValueError("all runs must contain the same case IDs")

    exact_context: list[float] = []
    status_agreement: list[float] = []
    hit_agreement: list[float] = []
    item_jaccard: list[float] = []
    for left, right in combinations(indexed, 2):
        for case_id in sorted(case_ids):
            left_row = left[case_id]
            right_row = right[case_id]
            exact_context.append(
                float(str(left_row.get("context") or "") == str(right_row.get("context") or ""))
            )
            status_agreement.append(
                float(left_row.get("status") == right_row.get("status"))
            )
            hit_agreement.append(
                float(
                    bool(left_row.get("identifier_hit"))
                    == bool(right_row.get("identifier_hit"))
                )
            )
            item_jaccard.append(
                _jaccard(_item_set(left_row), _item_set(right_row))
            )

    run_hit_rates = [
        fmean(float(bool(row.get("identifier_hit"))) for row in run.values())
        for run in indexed
    ]
    return {
        "runs": len(indexed),
        "cases": len(case_ids),
        "paired_case_comparisons": len(exact_context),
        "exact_context_rate": fmean(exact_context),
        "status_agreement_rate": fmean(status_agreement),
        "identifier_hit_agreement_rate": fmean(hit_agreement),
        "mean_item_set_jaccard": fmean(item_jaccard),
        "run_identifier_hit_rates": run_hit_rates,
        "mean_identifier_hit_rate": fmean(run_hit_rates),
        "min_identifier_hit_rate": min(run_hit_rates),
        "max_identifier_hit_rate": max(run_hit_rates),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--details", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runs = [json.loads(path.read_text(encoding="utf-8")) for path in args.details]
    summary = analyze_runs(runs)
    summary["details"] = [str(path) for path in args.details]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
