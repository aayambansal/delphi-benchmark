"""Answer-style synthesis parity arms for the documentation track.

Nia's recorded documentation numbers score identifier hits on synthesized
answer text (retrieval + synthesis, model knowledge allowed). Delphi's
recorded numbers score raw retrieved context. This runner produces the
matched-output-contract arms predeclared in Atlas plan full-clay-9675:

- mode=answer  : Delphi retrieved context + answer-style synthesis
- mode=control : identical prompt contract with no retrieved context

Both arms reuse the frozen recorded retrieval contexts verbatim; no new
retrieval requests are made.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import fmean
from typing import Any

import tiktoken

from ds1000_harness.developer import identifier_hit
from ds1000_harness.generation import Generator
from ds1000_harness.loaders import load_ds1000_cases

_TOKENIZER = tiktoken.get_encoding("cl100k_base")

_ANSWER_SYSTEM = """You are a documentation-grounded coding assistant.
Answer the coding question directly and concretely.
Name the exact library APIs, functions, methods, and parameters that solve the task, using their precise identifiers.
Ground your answer in the retrieved documentation when it is relevant, and cite the source paths you used.
If the retrieved documentation is missing or unhelpful, still answer from your own knowledge of the library and say the documentation did not cover it.
Do not use Markdown code fences."""

_CONTROL_SYSTEM = """You are a coding assistant.
Answer the coding question directly and concretely.
Name the exact library APIs, functions, methods, and parameters that solve the task, using their precise identifiers.
Answer from your own knowledge of the library.
Do not use Markdown code fences."""


def build_answer_prompt(problem: str, context: str) -> str:
    return (
        "<coding_question>\n"
        f"{problem.strip()}\n"
        "</coding_question>\n\n"
        "<retrieved_documentation>\n"
        f"{context.strip()}\n"
        "</retrieved_documentation>"
    )


def build_control_prompt(problem: str) -> str:
    return (
        "<coding_question>\n"
        f"{problem.strip()}\n"
        "</coding_question>"
    )


def summarize(
    rows: list[dict[str, Any]],
    *,
    engine: str,
    provider: str,
    model: str,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize an empty synthesis run")
    return {
        "engine": engine,
        "provider": provider,
        "model": model,
        "n": len(rows),
        "identifier_hit_rate": fmean(
            float(bool(row.get("identifier_hit"))) for row in rows
        ),
        "technical_failure_rate": fmean(
            float(row.get("status") != "ok") for row in rows
        ),
        "mean_context_tokens": fmean(
            int(row.get("context_tokens") or 0) for row in rows
        ),
        "mean_latency_ms": fmean(
            float(row.get("latency_ms") or 0.0) for row in rows
        ),
    }


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


def _case_ids(path: Path) -> tuple[str, ...]:
    with path.open(encoding="utf-8") as stream:
        return tuple(
            str((json.loads(line).get("metadata") or {})["problem_id"])
            for line in stream
            if line.strip()
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--mode", choices=("answer", "control"), required=True)
    parser.add_argument(
        "--contexts",
        type=Path,
        help="recorded retrieval details JSON; required for mode=answer",
    )
    parser.add_argument("--provider", choices=("openai",), default="openai")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--max-output-tokens", type=int, default=1600)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    if args.mode == "answer" and args.contexts is None:
        raise SystemExit("--contexts is required for mode=answer")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("missing required environment variable: OPENAI_API_KEY")

    context_rows: dict[str, dict[str, Any]] = {}
    source_engine = None
    if args.mode == "answer":
        context_rows = {
            str(row["case_id"]): row for row in _read_json(args.contexts)
        }
        engines = {str(row.get("engine")) for row in context_rows.values()}
        if len(engines) != 1:
            raise SystemExit(f"mixed source engines in contexts: {engines}")
        source_engine = engines.pop()

    cases = load_ds1000_cases(args.samples, _case_ids(args.samples))
    if args.mode == "answer":
        missing = [
            case.case_id for case in cases if case.case_id not in context_rows
        ]
        if missing:
            raise SystemExit(f"missing source contexts: {', '.join(missing)}")

    engine = (
        "delphi_answer_synthesis"
        if args.mode == "answer"
        else "synthesis_no_retrieval"
    )
    details: list[dict[str, Any]] = []
    if args.output.exists():
        prior = _read_json(args.output)
        if isinstance(prior, list):
            details = prior
    completed = {str(row["case_id"]) for row in details}

    generator = Generator(
        args.provider,
        args.model,
        api_key,
        max_output_tokens=args.max_output_tokens,
        system_prompt=_ANSWER_SYSTEM if args.mode == "answer" else _CONTROL_SYSTEM,
    )

    for case in cases:
        if case.case_id in completed:
            continue
        if args.mode == "answer":
            source = context_rows[case.case_id]
            raw_context = str(source.get("context") or "")
            prompt = build_answer_prompt(case.prompt, raw_context)
            source_context_tokens = int(source.get("context_tokens") or 0)
            retrieval_latency_ms = float(source.get("latency_ms") or 0.0)
        else:
            prompt = build_control_prompt(case.prompt)
            source_context_tokens = 0
            retrieval_latency_ms = 0.0
        generated = generator.generate(prompt)
        text = generated.text.strip() if generated.status == "ok" else ""
        row = {
            "case_id": case.case_id,
            "library": case.library_name,
            "engine": engine,
            "status": generated.status,
            "error_type": generated.error_type,
            "context": text,
            "context_tokens": len(_TOKENIZER.encode(text)),
            "source_context_tokens": source_context_tokens,
            "identifier_hit": identifier_hit(text, case.gold_identifiers),
            "gold_identifiers": list(case.gold_identifiers),
            "latency_ms": generated.latency_ms,
            "retrieval_latency_ms": retrieval_latency_ms,
            "provider_metadata": {
                "provider": args.provider,
                "model": args.model,
                "input_tokens": generated.input_tokens,
                "output_tokens": generated.output_tokens,
                "source_engine": source_engine,
                "mode": args.mode,
            },
        }
        details.append(row)
        _write_json(args.output, details)
        print(
            json.dumps(
                {
                    "case_id": case.case_id,
                    "mode": args.mode,
                    "status": row["status"],
                    "identifier_hit": row["identifier_hit"],
                },
                sort_keys=True,
            ),
            flush=True,
        )

    summary = summarize(
        details,
        engine=engine,
        provider=args.provider,
        model=args.model,
    )
    summary["max_output_tokens"] = args.max_output_tokens
    summary["mode"] = args.mode
    if args.mode == "answer":
        summary["source_contexts"] = str(args.contexts)
        summary["source_engine"] = source_engine
    _write_json(args.summary, summary)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
