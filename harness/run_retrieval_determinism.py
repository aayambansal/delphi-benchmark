"""Track B: retrieval-level determinism.

Fire the identical query N times at an engine and measure list stability:
exact-list equality, Jaccard@10 vs first repeat, Kendall tau on shared items,
plus latency spread. Uses a fixed set of ARB development cases.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R2 = ROOT.parent / "delphi-evaluation-2026-07-29-round2"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str((R2 / "external" / "arb-src" / "src").resolve()))

from agent_retrieval_bench.baseline import query_text_for_eval  # noqa: E402

from harness.gitcorpus import GitCorpus  # noqa: E402
from harness.run_arb import (  # noqa: E402
    CorpusEngine,
    DelphiEngine,
    NiaEngine,
    benchmark_status,
    load_sources,
)
from harness.runstore import RunWriter  # noqa: E402


def kendall_tau(a: list[str], b: list[str]) -> float | None:
    shared = [x for x in a if x in b]
    if len(shared) < 2:
        return None
    pos_b = {x: i for i, x in enumerate(b)}
    concordant = discordant = 0
    for x, y in combinations(shared, 2):
        if (pos_b[x] - pos_b[y]) > 0:
            discordant += 1
        else:
            concordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=("delphi", "nia", "bm25"))
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--n-cases", type=int, default=8)
    parser.add_argument("--sources", type=Path, default=None)
    parser.add_argument("--system", default=None)
    parser.add_argument("--delphi-url", default="http://127.0.0.1:20742")
    parser.add_argument("--delphi-key", default=os.environ.get("SYNSC_API_KEY", ""))
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    corpus = GitCorpus()
    if args.engine == "delphi":
        engine = DelphiEngine(
            load_sources(args.sources),
            base_url=args.delphi_url,
            api_key=args.delphi_key,
        )
    elif args.engine == "nia":
        engine = NiaEngine(load_sources(args.sources))
    else:
        engine = CorpusEngine(corpus, "bm25")

    # fixed, deterministic case pick: first N dev cases by id across workflows
    samples = []
    for wf in ("v2_trace2code", "v2_code2test", "v2_comment2context", "v2_edit2ripple"):
        rows = [json.loads(line) for line in (ROOT / "samples" / "development" / f"{wf}.jsonl").open()]
        rows.sort(key=lambda r: str(r["id"]))
        samples.extend(rows[:2])
    samples = samples[: args.n_cases]

    writer = RunWriter(
        track="B-determinism-retrieval",
        system=args.system or args.engine,
        config={"repeats": args.repeats, "n_cases": len(samples), "notes": args.notes},
        split="determinism",
        notes=args.notes,
    )
    print(f"run_id={writer.run_id}", flush=True)

    per_case = []
    observations = []
    for sample in samples:
        query = query_text_for_eval(sample)
        lists: list[list[str]] = []
        lats: list[float] = []
        for _ in range(args.repeats):
            obs = engine.search(sample, query, limit=20)
            observations.append(obs)
            if obs["status"] != "ok":
                lists.append([])
            else:
                lists.append(list(dict.fromkeys(obs["paths"]))[:10])
            lats.append(obs["latency_ms"])
            time.sleep(0.2)
        ref = lists[0]
        exact = sum(1 for lst in lists[1:] if lst == ref)
        jaccards, taus = [], []
        for lst in lists[1:]:
            union = set(ref) | set(lst)
            jaccards.append(len(set(ref) & set(lst)) / len(union) if union else 1.0)
            tau = kendall_tau(ref, lst)
            if tau is not None:
                taus.append(tau)
        metrics = {
            "exact_list_rate": exact / max(1, len(lists) - 1),
            "jaccard10_mean": sum(jaccards) / len(jaccards) if jaccards else 1.0,
            "kendall_tau_mean": sum(taus) / len(taus) if taus else 1.0,
            "latency_ms_mean": sum(lats) / len(lats),
            "latency_ms_max": max(lats),
        }
        per_case.append(metrics)
        writer.case(case_id=str(sample["id"]), workflow=str(sample.get("task_type")),
                    repo=str(sample["repo"]), revision=str(sample["base_commit"]),
                    ok=all(obs["status"] == "ok" for obs in observations[-args.repeats:]),
                    latency_ms=metrics["latency_ms_mean"], metrics=metrics,
                    ranked=ref, trace={"all_lists": lists})
        print(json.dumps({"case": str(sample["id"]),
                          **{k: round(v, 4) for k, v in metrics.items()}}), flush=True)

    agg = {k: sum(c[k] for c in per_case) / len(per_case) for k in per_case[0]}
    status = benchmark_status(observations, [])
    writer.finish(agg, status=status)
    (ROOT / "results" / f"{writer.run_id}-summary.json").write_text(
        json.dumps({"engine": args.engine, "aggregate": agg}, indent=2) + "\n")
    if status != "done":
        raise SystemExit("determinism run invalid: one or more retrieval calls failed")
    print(json.dumps({"engine": args.engine, **{k: round(v, 4) for k, v in agg.items()}}), flush=True)


if __name__ == "__main__":
    main()
