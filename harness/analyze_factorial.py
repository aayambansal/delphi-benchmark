"""Candidate-generator x reranking-head factorial (round 4, declared ablation).

Four cells per set, expansion held constant (on, under Delphi's gate):

    conventional candidates, no learned reranking   hybrid_expand
    conventional candidates + Delphi's rerankers    hybrid_rerank_expand
    Delphi candidates,       no learned reranking   Delphi frozen build, rerankers off
    Delphi candidates        + Delphi's rerankers    Delphi frozen build (confirmatory run)

"Delphi candidates" means every candidate branch (vector, BM25, exact symbol,
exact path, path affinity, trigram), tuned reciprocal-rank fusion, and
quoted-path demotion; the two rerankers are the cross-encoder blend and the
listwise gpt-4o stage. The Delphi cells with rerankers are the confirmatory
runs already reported; the no-reranker cells were scored afterwards on the same
cases and are explanatory, not confirmatory.

    python harness/analyze_factorial.py

Writes results/factorial-r4-v1.json with the four cell means per set and the
paired differences (repository-cluster bootstrap 95% intervals, 20,000
resamples, seed 1042) for the two conditional main effects of each factor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "results"

from harness.analyze_paired_runs import analyze_pair  # noqa: E402

METRICS = ("MRR", "Recall@5", "Recall@20", "BCY@8k")

SETS = {
    "independent": {
        # The independent index was not retained; both Delphi cells of the factorial
        # were served from a re-indexed corpus. The confirmatory run (original
        # index) is kept as its own cell so that the re-indexing shift is visible.
        "label": "Independent commit-to-files (C0, n=18)",
        "conv_norerank": "I-final-hybrid_expand-r4-v1",
        "conv_rerank": "I-final-hybrid_rerank_expand-r4-v1",
        "delphi_norerank": "I-ablation-delphi-norerank-v1",
        "delphi_rerank": "I-factorial-delphi-full-v1",
        "delphi_rerank_confirmatory": "I-final-delphi-generated-source-exact-top20-v1",
    },
    "swebench": {
        "label": "SWE-bench Verified round 3 (C0, n=62)",
        "conv_norerank": "D-final-hybrid_expand-r4-v1",
        "conv_rerank": "D-final-hybrid_rerank_expand-r4-v1",
        "delphi_norerank": None,  # database not retained
        "delphi_rerank": "D-final-delphi-generated-source-exact-top20-v1",
    },
    "expansion": {
        "label": "SWE-bench Verified expansion (C0, n=98)",
        "conv_norerank": "D2-final-hybrid_expand-r4-v1",
        "conv_rerank": "D2-final-hybrid_rerank_expand-r4-v1",
        "delphi_norerank": "D2-ablation-delphi-norerank-v1",
        "delphi_rerank": "D2-final-delphi-generated-source-exact-top20-v1",
    },
    "fresh": {
        "label": "SWE-bench Verified fresh draw (C0, n=60)",
        "conv_norerank": "D3-final-hybrid_expand-r5-v1",
        "conv_rerank": "D3-final-hybrid_rerank_expand-r5-v1",
        "delphi_norerank": "D3-ablation-delphi-norerank-all-v1",
        "delphi_rerank": "D3-final-delphi-generated-source-exact-top20-v1",
    },
    "arb": {
        "label": "ARB round-3 partition (C2, n=220)",
        "conv_norerank": "A-final-hybrid_expand-r4-v1",
        "conv_rerank": "A-final-hybrid_rerank_expand-r4-v1",
        "delphi_norerank": None,  # database not retained
        "delphi_rerank": "A-final-delphi-generated-source-exact-top20-v1",
    },
}

EXISTING_PAIRS = {
    ("independent", "candidate_effect_rerank_confirmatory"): "independent_final_delphi_vs_hybrid_rerank_expand_r4_v1.json",
    ("swebench", "candidate_effect_rerank"): "trackd_final_delphi_vs_hybrid_rerank_expand_r4_v1.json",
    ("expansion", "candidate_effect_rerank"): "swebench_expansion_delphi_vs_hybrid_rerank_expand_r4_v1.json",
    ("fresh", "candidate_effect_rerank"): "swebench_fresh_delphi_vs_hybrid_rerank_expand_r5_v1.json",
    ("arb", "candidate_effect_rerank"): "arb_final_delphi_vs_hybrid_rerank_expand_r4_v1.json",
}

CONTRASTS = [
    ("rerank_effect_conventional", "conv_norerank", "conv_rerank", "rerankers on conventional candidates"),
    ("rerank_effect_delphi", "delphi_norerank", "delphi_rerank", "rerankers on Delphi candidates (same index)"),
    ("candidate_effect_norerank", "conv_norerank", "delphi_norerank", "Delphi vs conventional candidates, no rerankers"),
    ("candidate_effect_rerank", "conv_rerank", "delphi_rerank", "Delphi vs conventional candidates, with rerankers"),
    ("candidate_effect_rerank_confirmatory", "conv_rerank", "delphi_rerank_confirmatory", "Delphi (confirmatory index) vs conventional candidates, with rerankers"),
    ("replication", "delphi_rerank_confirmatory", "delphi_rerank", "Delphi frozen build re-indexed vs confirmatory run"),
]


def rows(run: str | None) -> list[dict] | None:
    if not run:
        return None
    path = RESULTS / f"{run}-details.jsonl"
    if not path.exists():
        return None
    return [json.loads(line) for line in path.open() if line.strip()]


def means(run: str | None) -> dict | None:
    path = RESULTS / f"{run}-summary.json" if run else None
    if not path or not path.exists():
        return None
    s = json.load(path.open())
    out = {m: s["sample_weighted"][m] for m in METRICS}
    out["n"] = s["n"]
    return out


def main() -> None:
    out = {"schema": "factorial_r4_v1", "bootstrap": {"samples": 20000, "seed": 1042, "unit": "repository"}, "sets": {}}
    for key, spec in SETS.items():
        if key == "swebench" and False:
            pass
        entry = {"label": spec["label"], "cells": {}, "contrasts": {}}
        for cell in ("conv_norerank", "conv_rerank", "delphi_norerank", "delphi_rerank", "delphi_rerank_confirmatory"):
            run = spec.get(cell)
            m = means(run)
            if m is not None:
                entry["cells"][cell] = {"run": run, **m}
        for name, base, cand, desc in CONTRASTS:
            b, c = rows(spec.get(base)), rows(spec.get(cand))
            if b is None or c is None:
                continue
            existing = RESULTS / EXISTING_PAIRS.get((key, name), "__none__")
            if existing.exists():
                # Reuse the confirmatory paired analysis so the same number appears everywhere.
                pair = json.load(existing.open())
            else:
                pair = analyze_pair(b, c, baseline_run=spec[base], candidate_run=spec[cand], bootstrap_samples=20000, bootstrap_seed=1042)
            entry["contrasts"][name] = {
                "description": desc,
                "baseline_run": spec[base],
                "candidate_run": spec[cand],
                "metrics": {m: {"mean_delta": pair["metrics"][m]["mean_delta"], "ci95": pair["metrics"][m]["repo_cluster_bootstrap_95_ci"],
                                "wins": pair["metrics"][m]["wins"], "losses": pair["metrics"][m]["losses"]} for m in METRICS if m in pair["metrics"]},
                "any_gold_at_20": pair.get("any_gold_at_20"),
            }
        out["sets"][key] = entry
    path = RESULTS / "factorial-r4-v1.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    for key, entry in out["sets"].items():
        print(f"== {entry['label']}")
        for cell, m in entry["cells"].items():
            print(f"   {cell:28s} MRR {m['MRR']:.3f}  R@5 {m['Recall@5']:.3f}  R@20 {m['Recall@20']:.3f}  BCY {m['BCY@8k']:.3f}  (n={m['n']})")
        for name, c in entry["contrasts"].items():
            mm = c["metrics"]["MRR"]
            rr = c["metrics"]["Recall@20"]
            print(f"   {name:28s} dMRR {mm['mean_delta']:+.3f} [{mm['ci95'][0]:+.3f},{mm['ci95'][1]:+.3f}]  dR@20 {rr['mean_delta']:+.3f} [{rr['ci95'][0]:+.3f},{rr['ci95'][1]:+.3f}]")


if __name__ == "__main__":
    main()
