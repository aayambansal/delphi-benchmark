"""Track C: does seeding a frozen closed-tool agent with engine context help?

One frozen policy model explores a repository snapshot through list_dir /
grep / read_file and submits the files it believes answer the query. Arms
differ ONLY in the seed context block prepended to the first observation:

  none    -> agent starts cold
  runstore seeds (bm25 / delphi / nia / lexical Track-A runs) -> top-k files
  oracle  -> the gold files themselves (ceiling)
  random  -> deterministic non-gold files (floor)

Uses the official ARB closed-tool sample runner and metrics; the corpus is
the canonical git corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent.parent
R2 = ROOT.parent / "delphi-evaluation-2026-07-29-round2"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str((R2 / "external" / "arb-src" / "src").resolve()))

from agent_retrieval_bench.baseline import (  # noqa: E402
    query_has_leakage,
    query_text_for_eval,
    target_gold_files,
)
from agent_retrieval_bench.closed_tool_eval import (  # noqa: E402
    OpenAIResponsesHTTPClient,
    run_closed_tool_llm_sample,
)
from agent_retrieval_bench.corpus import is_candidate_path  # noqa: E402

from harness.gitcorpus import GitCorpus  # noqa: E402
from harness.runstore import DB_PATH, RunWriter  # noqa: E402

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".whl", ".jar", ".class", ".so", ".dylib", ".dll", ".exe", ".bin",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".webm", ".ogg",
    ".pyc", ".wasm", ".onnx", ".pt", ".pack", ".idx", ".parquet",
}


def load_files(corpus: GitCorpus, repo: str, commit: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in corpus.list_files(repo, commit):
        if Path(path).suffix.lower() in BINARY_EXT or not is_candidate_path(path):
            continue
        text = corpus.file_text(repo, commit, path)
        if text is None or not text.strip() or len(text) > 1_200_000:
            continue
        files[path] = text
    return files


def stratified_cases(per_workflow: int) -> list[dict]:
    out = []
    for wf in ("v2_code2test", "v2_comment2context", "v2_trace2code", "v2_edit2ripple"):
        rows = [json.loads(line) for line in (ROOT / "samples" / "development" / f"{wf}.jsonl").open()]
        rows = [r for r in rows if (r.get("gold") or {}).get("no_gold") is not True]
        rows.sort(key=lambda r: str(r["id"]))
        out.extend(rows[:per_workflow])
    return out


def seeds_from_run(run_id: str, top_k: int) -> dict[str, list[str]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    seeds = {}
    for row in conn.execute("SELECT case_id, ranked FROM cases WHERE run_id=?", (run_id,)):
        seeds[row["case_id"]] = json.loads(row["ranked"])[:top_k]
    conn.close()
    if not seeds:
        raise SystemExit(f"no cases found in runstore for seed run {run_id}")
    return seeds


def random_seeds(sample: dict, files: dict[str, str], top_k: int) -> list[str]:
    gold = set(target_gold_files(sample))
    candidates = sorted(p for p in files if p not in gold)
    picked = sorted(
        candidates,
        key=lambda p: hashlib.sha256(f"r3-random|{sample['id']}|{p}".encode()).hexdigest(),
    )
    return picked[:top_k]


def file_f1(final: list[str], gold: set[str]) -> float:
    if not final or not gold:
        return 0.0
    hits = len(set(final) & gold)
    if hits == 0:
        return 0.0
    precision = hits / len(final)
    recall = hits / len(gold)
    return 2 * precision * recall / (precision + recall)


def agent_run_status(*, expected_cases: int, completed_cases: int) -> str:
    return (
        "done"
        if expected_cases > 0 and completed_cases == expected_cases
        else "failed"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True,
                        help="none | oracle | random | run:<runstore-run-id>")
    parser.add_argument("--system", required=True, help="label, e.g. seed-delphi")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--per-workflow", type=int, default=10)
    parser.add_argument("--seed-top-k", type=int, default=5)
    parser.add_argument("--max-seed-tokens", type=int, default=2500)
    parser.add_argument("--seed-tokens-per-file", type=int, default=700)
    parser.add_argument("--max-tool-calls", type=int, default=12)
    parser.add_argument("--max-read-tokens", type=int, default=8000)
    parser.add_argument("--final-k", type=int, default=3)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    client = OpenAIResponsesHTTPClient(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    corpus = GitCorpus()
    samples = stratified_cases(args.per_workflow)

    run_seeds: dict[str, list[str]] = {}
    if args.arm.startswith("run:"):
        run_seeds = seeds_from_run(args.arm[4:], args.seed_top_k)

    writer = RunWriter(
        track="C-agent-utility",
        system=args.system,
        config={
            "arm": args.arm, "model": args.model,
            "seed_top_k": args.seed_top_k, "max_seed_tokens": args.max_seed_tokens,
            "max_tool_calls": args.max_tool_calls, "final_k": args.final_k,
            "per_workflow": args.per_workflow,
        },
        split="development-strat",
        run_id=args.run_id,
    )
    print(f"run_id={writer.run_id} cases={len(samples)}", flush=True)

    details = []
    for i, sample in enumerate(samples):
        case_id = str(sample["id"])
        repo, commit = str(sample["repo"]), str(sample["base_commit"])
        gold = target_gold_files(sample)
        query = query_text_for_eval(sample)
        if query_has_leakage(sample, query):
            continue
        files = load_files(corpus, repo, commit)

        if args.arm == "none":
            seed_files: list[str] = []
        elif args.arm == "oracle":
            seed_files = list(gold)[: args.seed_top_k]
        elif args.arm == "random":
            seed_files = random_seeds(sample, files, args.seed_top_k)
        else:
            seed_files = run_seeds.get(case_id, [])

        started = time.time()
        try:
            detail = run_closed_tool_llm_sample(
                sample=sample, gold_files=gold, query_text=query, files=files,
                model=args.model, client=client,
                max_tool_calls=args.max_tool_calls,
                max_read_tokens=args.max_read_tokens,
                max_read_tokens_per_file=1200,
                final_k=args.final_k, grep_top_k=12,
                max_model_turns=args.max_tool_calls + 4,
                seed_files=seed_files, seed_label=args.system,
                max_seed_tokens=args.max_seed_tokens if seed_files else 0,
                max_seed_tokens_per_file=args.seed_tokens_per_file,
            )
        except Exception as exc:  # noqa: BLE001
            writer.case(case_id=case_id, workflow=str(sample.get("task_type")),
                        repo=repo, revision=commit, ok=False,
                        metrics={}, gold=gold,
                        trace={"error": f"{type(exc).__name__}: {exc}"[:400]})
            print(json.dumps({"i": i + 1, "case": case_id, "error": str(exc)[:120]}), flush=True)
            continue
        closed = detail.get("closed_tool", {})
        final_files = closed.get("final_files", [])
        metrics = {
            "file_f1": file_f1(final_files, set(gold)),
            "final_any_gold": float(any(p in set(gold) for p in final_files)),
            "any_gold_acquired": float(closed.get("first_gold_step") is not None),
            "first_gold_step": closed.get("first_gold_step"),
            "tool_calls": closed.get("tool_calls"),
            "read_tokens": closed.get("read_tokens"),
            "seed_files_used": len(seed_files),
            "wall_s": round(time.time() - started, 1),
        }
        details.append({"case_id": case_id, "workflow": str(sample.get("task_type")), **metrics})
        raw_trace = (detail.get("closed_tool") or {}).get("trace", [])
        compact_actions = []
        for entry in raw_trace[:120]:
            if entry.get("tool") == "model_action":
                compact_actions.append({"turn": entry.get("model_turn"),
                                        "parsed": entry.get("parsed")})
            else:
                compact_actions.append({k: v for k, v in entry.items()
                                        if k not in ("raw",)})
        writer.case(case_id=case_id, workflow=str(sample.get("task_type")),
                    repo=repo, revision=commit, ok=True,
                    latency_ms=(time.time() - started) * 1000,
                    metrics=metrics, ranked=final_files, gold=gold,
                    trace={"seed_files": seed_files, "actions": compact_actions})
        print(json.dumps({"i": i + 1, "n": len(samples), "case": case_id,
                          "f1": round(metrics["file_f1"], 3),
                          "final_any_gold": metrics["final_any_gold"],
                          "tools": metrics["tool_calls"]}), flush=True)

    ok_rows = details
    first_hits = [r["first_gold_step"] for r in ok_rows if r["first_gold_step"] is not None]
    summary = {
        "n": len(ok_rows),
        "expected_n": len(samples),
        "technical_failures": len(samples) - len(ok_rows),
        "file_f1": mean(r["file_f1"] for r in ok_rows) if ok_rows else None,
        "final_any_gold_rate": mean(r["final_any_gold"] for r in ok_rows) if ok_rows else None,
        "any_gold_acquired_rate": mean(r["any_gold_acquired"] for r in ok_rows) if ok_rows else None,
        "median_first_gold_step": median(first_hits) if first_hits else None,
        "mean_tool_calls": mean(r["tool_calls"] for r in ok_rows) if ok_rows else None,
        "mean_read_tokens": mean(r["read_tokens"] for r in ok_rows) if ok_rows else None,
        "by_workflow": {
            wf: {
                "n": len(rows),
                "file_f1": mean(r["file_f1"] for r in rows),
                "final_any_gold_rate": mean(r["final_any_gold"] for r in rows),
            }
            for wf in sorted({r["workflow"] for r in ok_rows})
            for rows in [[r for r in ok_rows if r["workflow"] == wf]]
        },
    }
    status = agent_run_status(
        expected_cases=len(samples),
        completed_cases=len(ok_rows),
    )
    writer.finish(summary, status=status)
    (ROOT / "results" / f"{writer.run_id}-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    if status != "done":
        raise SystemExit(
            f"agent run invalid: completed {len(ok_rows)}/{len(samples)} cases"
        )
    print(json.dumps({"run_id": writer.run_id, "file_f1": summary["file_f1"],
                      "final_any_gold": summary["final_any_gold_rate"]}), flush=True)


if __name__ == "__main__":
    main()
