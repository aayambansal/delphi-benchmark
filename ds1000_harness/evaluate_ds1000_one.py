from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ds1000_harness.ds1000_eval import evaluate_completion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-source", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    passed, error = evaluate_completion(
        execution_source=args.execution_source,
        dataset_path=args.dataset,
        case_id=args.case_id,
        code=sys.stdin.read(),
    )
    print(json.dumps({"passed": passed, "error": error}, sort_keys=True))


if __name__ == "__main__":
    main()
