"""The three SWE-bench Verified draws as a sequence: per-draw, pooled, and adjusted.

Round 3 scored 62 instances; round 4 drew 98 more and pooled to 160; the
branch-ablation draw added 60. A reader may ask whether pooling after looking is
optional stopping. This script reports, for Delphi against the full conventional
stack (and against the lexical ranker):

  * each draw on its own, with its 95% repository-cluster interval;
  * the pooled estimate over 160 and over all 220 instances, with the 95%
    interval and with a Bonferroni-style interval for k looks (1 - 0.05/k);
  * the sign of the point estimate in every draw.

    python harness/analyze_sequential.py

Writes results/sequential-swebench-r4-v1.json.
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "results"

from harness.analyze_paired_runs import _quantile  # noqa: E402

METRICS = ("MRR", "Recall@5", "Recall@20", "BCY@8k")
DRAWS = [
    ("round3_62", "D-final-delphi-generated-source-exact-top20-v1", "D-final-hybrid_rerank_expand-r4-v1", "D-final-lexical-generated-policy-v1"),
    ("expansion_98", "D2-final-delphi-generated-source-exact-top20-v1", "D2-final-hybrid_rerank_expand-r4-v1", "D2-final-lexical-r4-v1"),
    ("fresh_60", "D3-final-delphi-generated-source-exact-top20-v1", "D3-final-hybrid_rerank_expand-r5-v1", "D3-final-lexical-r5-v1"),
]


def rows(run: str) -> dict[str, dict] | None:
    path = RESULTS / f"{run}-details.jsonl"
    if not path.exists():
        return None
    return {json.loads(l)["sample_id"]: json.loads(l) for l in path.open() if l.strip()}


def paired(delphi: dict, other: dict, metric: str, *, samples: int = 20000, seed: int = 1042, alphas=(0.05,)) -> dict:
    grouped: dict[str, list[float]] = defaultdict(list)
    deltas = []
    for sid, d in delphi.items():
        o = other.get(sid)
        if o is None:
            continue
        delta = float(d["metrics"][metric]) - float(o["metrics"][metric])
        grouped[str(d["repo"])].append(delta)
        deltas.append(delta)
    repos = sorted(grouped)
    rng = random.Random(seed)
    draws = []
    for _ in range(samples):
        vals: list[float] = []
        for _r in repos:
            vals.extend(grouped[rng.choice(repos)])
        draws.append(fmean(vals))
    out = {"n": len(deltas), "clusters": len(repos), "mean_delta": fmean(deltas)}
    for a in alphas:
        lo, hi = _quantile(draws, a / 2), _quantile(draws, 1 - a / 2)
        out[f"ci_{100 * (1 - a):.1f}"] = [lo, hi]
    return out


def main() -> None:
    k = len(DRAWS)
    alphas = (0.05, 0.05 / k)
    out = {"schema": "sequential_swebench_r4_v1", "looks": k, "alphas": list(alphas), "bootstrap": {"samples": 20000, "seed": 1042, "unit": "repository"},
           "comparators": {"full_conventional_stack": {}, "lexical_ranker": {}}}
    pooled = {"delphi": {}, "conv": {}, "lex": {}}
    for name, d_run, c_run, l_run in DRAWS:
        d, c, l = rows(d_run), rows(c_run), rows(l_run)
        if d is None or c is None:
            continue
        out["comparators"]["full_conventional_stack"][name] = {m: paired(d, c, m, alphas=alphas) for m in METRICS}
        if l is not None:
            out["comparators"]["lexical_ranker"][name] = {m: paired(d, l, m, alphas=alphas) for m in METRICS}
        pooled["delphi"].update(d)
        pooled["conv"].update(c)
        if l is not None:
            pooled["lex"].update(l)
        # running pooled estimate after this look
        key = f"pooled_after_{name}"
        out["comparators"]["full_conventional_stack"][key] = {m: paired(pooled["delphi"], pooled["conv"], m, alphas=alphas) for m in METRICS}
        if l is not None:
            out["comparators"]["lexical_ranker"][key] = {m: paired(pooled["delphi"], pooled["lex"], m, alphas=alphas) for m in METRICS}
    for comp, entry in out["comparators"].items():
        signs = {m: [entry[n][m]["mean_delta"] > 0 for n, *_ in DRAWS if n in entry] for m in METRICS}
        entry["sign_agreement"] = {m: {"positive_in_draws": sum(v), "draws": len(v)} for m, v in signs.items()}
    path = RESULTS / "sequential-swebench-r4-v1.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    for comp, entry in out["comparators"].items():
        print(f"== Delphi - {comp}")
        for name, per in entry.items():
            if name == "sign_agreement":
                continue
            cells = []
            for m in METRICS:
                v = per[m]
                ci95 = v["ci_95.0"]
                cia = v[f"ci_{100 * (1 - alphas[1]):.1f}"]
                cells.append(f"{m} {v['mean_delta']:+.3f} [{ci95[0]:+.3f},{ci95[1]:+.3f}] adj[{cia[0]:+.3f},{cia[1]:+.3f}]")
            print(f"  {name:28s} n={per['MRR']['n']:3d}  " + " | ".join(cells))


if __name__ == "__main__":
    main()
