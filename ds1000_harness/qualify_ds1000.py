from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any

from ds1000_harness.ds1000_eval import evaluate_completion
from ds1000_harness.loaders import load_ds1000_cases


def _rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--execution-source",
        type=Path,
        default=Path("external/ds1000-official/execution.py"),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("external/ds1000-official/data/ds1000.jsonl.gz"),
    )
    args = parser.parse_args()

    raw_rows = _rows(args.samples)
    ids = tuple(str(row["metadata"]["problem_id"]) for row in raw_rows)
    cases = load_ds1000_cases(args.samples, ids)
    details = []
    for case in cases:
        passed, error = evaluate_completion(
            execution_source=args.execution_source,
            dataset_path=args.dataset,
            case_id=case.case_id,
            code=case.reference_code,
        )
        details.append(
            {
                "case_id": case.case_id,
                "library": case.library_name,
                "reference_passed": passed,
                "error_type": error,
            }
        )
        print(json.dumps(details[-1], sort_keys=True), flush=True)

    output = {
        "n": len(details),
        "reference_pass_rate": fmean(
            float(row["reference_passed"]) for row in details
        ),
        "details": details,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "n": output["n"],
                "reference_pass_rate": output["reference_pass_rate"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
