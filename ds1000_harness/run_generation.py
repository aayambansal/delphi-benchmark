from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from statistics import fmean
from typing import Any

from ds1000_harness.ds1000_eval import evaluate_completion_isolated
from ds1000_harness.generation import Generator, build_prompt, postprocess_generation
from ds1000_harness.loaders import load_ds1000_cases


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _case_ids(path: Path) -> tuple[str, ...]:
    return tuple(
        str((row.get("metadata") or {})["problem_id"])
        for row in _read_jsonl(path)
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _contexts(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    rows = _read_json(path)
    if not isinstance(rows, list):
        raise ValueError("retrieval details must be a JSON array")
    return {
        str(row["case_id"]): str(row.get("context") or "")
        for row in rows
    }


def _required_key(provider: str) -> str:
    names = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    value = os.environ.get(names[provider])
    if not value:
        raise SystemExit(f"missing required environment variable: {names[provider]}")
    return value


def _summary(
    details: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
    condition: str,
    execution_python: str | None = None,
) -> dict[str, Any]:
    libraries = sorted({str(row["library"]) for row in details})
    per_library = {
        library: {
            "n": len(rows),
            "pass_at_1": fmean(float(row["passed"]) for row in rows),
            "generation_error_rate": fmean(
                float(row["generation_status"] == "error") for row in rows
            ),
        }
        for library in libraries
        for rows in [[row for row in details if row["library"] == library]]
    }
    return {
        "provider": provider,
        "model": model,
        "condition": condition,
        "execution_python": execution_python,
        "n": len(details),
        "pass_at_1": fmean(float(row["passed"]) for row in details),
        "library_macro_pass_at_1": fmean(
            float(row["pass_at_1"]) for row in per_library.values()
        ),
        "generation_error_rate": fmean(
            float(row["generation_status"] == "error") for row in details
        ),
        "mean_generation_latency_ms": fmean(
            float(row["generation_latency_ms"]) for row in details
        ),
        "per_library": per_library,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--provider", choices=("openai", "anthropic", "google"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--contexts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("external/ds1000-official/data/ds1000.jsonl.gz"),
    )
    parser.add_argument(
        "--execution-source",
        type=Path,
        default=Path("external/ds1000-official/execution.py"),
    )
    parser.add_argument(
        "--execution-python",
        type=Path,
        help="Python interpreter containing the official DS-1000 dependencies",
    )
    args = parser.parse_args()
    if args.execution_python is not None and not args.execution_python.is_file():
        raise SystemExit(
            f"DS-1000 execution interpreter not found: {args.execution_python}"
        )
    execution_python = (
        args.execution_python.resolve()
        if args.execution_python is not None
        else Path(sys.executable).resolve()
    )

    cases = load_ds1000_cases(args.samples, _case_ids(args.samples))
    contexts = _contexts(args.contexts)
    if args.contexts is not None:
        missing = [case.case_id for case in cases if case.case_id not in contexts]
        if missing:
            raise SystemExit(f"missing contexts for case IDs: {', '.join(missing)}")

    prior: list[dict[str, Any]] = []
    if args.output.exists():
        value = _read_json(args.output)
        if isinstance(value, list):
            prior = value
    completed = {str(row["case_id"]) for row in prior}
    details = list(prior)

    generator = Generator(
        args.provider,
        args.model,
        _required_key(args.provider),
    )
    for case in cases:
        if case.case_id in completed:
            continue
        context = contexts.get(case.case_id, "")
        generated = generator.generate(build_prompt(case.prompt, context))
        code = postprocess_generation(generated.text)
        if generated.status == "ok":
            passed, execution_error = evaluate_completion_isolated(
                execution_python=execution_python,
                execution_source=args.execution_source,
                dataset_path=args.dataset,
                case_id=case.case_id,
                code=code,
            )
        else:
            passed = False
            execution_error = "generation_error"
        row = {
            "case_id": case.case_id,
            "library": case.library_name,
            "provider": args.provider,
            "model": args.model,
            "condition": args.condition,
            "execution_python": str(execution_python),
            "context_tokens": (
                next(
                    (
                        int(item.get("context_tokens") or 0)
                        for item in (_read_json(args.contexts) if args.contexts else [])
                        if str(item["case_id"]) == case.case_id
                    ),
                    0,
                )
            ),
            "generation_status": generated.status,
            "generation_error_type": generated.error_type,
            "generation_latency_ms": generated.latency_ms,
            "input_tokens": generated.input_tokens,
            "output_tokens": generated.output_tokens,
            "completion": code,
            "passed": passed,
            "execution_error": execution_error,
        }
        details.append(row)
        _write_json(args.output, details)
        print(
            json.dumps(
                {
                    "case_id": case.case_id,
                    "library": case.library_name,
                    "provider": args.provider,
                    "model": args.model,
                    "condition": args.condition,
                    "generation_status": generated.status,
                    "passed": passed,
                    "execution_error": execution_error,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    summary = _summary(
        details,
        provider=args.provider,
        model=args.model,
        condition=args.condition,
        execution_python=str(execution_python),
    )
    _write_json(args.summary, summary)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
