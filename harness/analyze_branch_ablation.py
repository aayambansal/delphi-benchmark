"""Branch-level ablation of Delphi's candidate generator on the fresh C0 draw.

All runs use the frozen build with both learned rerankers disabled and
expansion on, so that only candidate generation varies. The baseline is the
full six-branch generator with its tuned fusion weights; each ablation sets one
branch's fusion weight to zero (leave-one-out), and one configuration keeps only
the vector and BM25 branches at equal weights, which is the conventional
two-branch fusion inside Delphi's own chunker and index.

    python harness/analyze_branch_ablation.py

Writes results/branch-ablation-r5-v1.json with paired ablation-minus-baseline
differences (repository-cluster bootstrap 95% intervals, 20,000 resamples,
seed 1042).
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
BASELINE = "D3-ablation-delphi-norerank-all-v1"
ABLATIONS = [
    ("no_symbol", "D3-ablation-delphi-norerank-no_symbol-v1", "exact-symbol branch removed"),
    ("no_path", "D3-ablation-delphi-norerank-no_path-v1", "exact-path branch removed"),
    ("no_path_affinity", "D3-ablation-delphi-norerank-no_path_affinity-v1", "path-affinity branch removed"),
    ("no_trigram", "D3-ablation-delphi-norerank-no_trigram-v1", "trigram branch removed"),
    ("no_bm25", "D3-ablation-delphi-norerank-no_bm25-v1", "BM25 branch removed"),
    ("no_vector", "D3-ablation-delphi-norerank-no_vector-v1", "vector branch removed"),
    ("vector_bm25_equal", "D3-ablation-delphi-norerank-vector_bm25_equal-v1", "vector and BM25 only, equal weights (conventional fusion inside Delphi's index)"),
    ("vector_bm25_tuned", "D3-ablation-delphi-norerank-vector_bm25_tuned-v1", "vector and BM25 only, Delphi's relative weights (0.5/0.25)"),
    ("vector_only", "D3-ablation-delphi-norerank-vector_only-v1", "vector branch only"),
]


def rows(run: str) -> list[dict] | None:
    path = RESULTS / f"{run}-details.jsonl"
    if not path.exists():
        return None
    return [json.loads(l) for l in path.open() if l.strip()]


def means(run: str) -> dict | None:
    path = RESULTS / f"{run}-summary.json"
    if not path.exists():
        return None
    s = json.load(path.open())
    return {m: s["sample_weighted"][m] for m in METRICS} | {"n": s["n"]}


def main() -> None:
    base = rows(BASELINE)
    if base is None:
        raise SystemExit(f"baseline run missing: {BASELINE}")
    out = {"schema": "branch_ablation_r5_v1", "baseline": {"run": BASELINE, **means(BASELINE)}, "ablations": {},
           "bootstrap": {"samples": 20000, "seed": 1042, "unit": "repository"}}
    for key, run, desc in ABLATIONS:
        r = rows(run)
        if r is None:
            continue
        pair = analyze_pair(base, r, baseline_run=BASELINE, candidate_run=run, bootstrap_samples=20000, bootstrap_seed=1042)
        out["ablations"][key] = {
            "run": run, "description": desc, **means(run),
            "delta": {m: {"mean_delta": pair["metrics"][m]["mean_delta"], "ci95": pair["metrics"][m]["repo_cluster_bootstrap_95_ci"],
                          "wins": pair["metrics"][m]["wins"], "losses": pair["metrics"][m]["losses"]} for m in METRICS},
            "any_gold_at_20": pair.get("any_gold_at_20"),
        }
    path = RESULTS / "branch-ablation-r5-v1.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    b = out["baseline"]
    print(f"baseline (all branches, no rerankers): MRR {b['MRR']:.3f} R@5 {b['Recall@5']:.3f} R@20 {b['Recall@20']:.3f} BCY {b['BCY@8k']:.3f} n={b['n']}")
    for key, a in out["ablations"].items():
        d = a["delta"]
        print(f"  {key:20s} MRR {a['MRR']:.3f} ({d['MRR']['mean_delta']:+.3f} [{d['MRR']['ci95'][0]:+.3f},{d['MRR']['ci95'][1]:+.3f}])  "
              f"R@20 {a['Recall@20']:.3f} ({d['Recall@20']['mean_delta']:+.3f} [{d['Recall@20']['ci95'][0]:+.3f},{d['Recall@20']['ci95'][1]:+.3f}])")


if __name__ == "__main__":
    main()
