"""Pooled paired analysis across runs that share an engine (e.g. the round-3
SWE-bench set and the round-4 expansion), using the same repository-cluster
bootstrap and McNemar machinery as analyze_arb_pair.py."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.analyze_arb_pair import _load_run, analyze_pair  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "runstore.db")
    parser.add_argument("--baseline", nargs="+", required=True, help="baseline run ids to pool")
    parser.add_argument("--candidate", nargs="+", required=True, help="candidate run ids to pool (same order)")
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=1042)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    try:
        baseline = [row for run in args.baseline for row in _load_run(conn, run)]
        candidate = [row for run in args.candidate for row in _load_run(conn, run)]
    finally:
        conn.close()
    summary = analyze_pair(baseline, candidate, metrics=("MRR", "Recall@5", "Recall@20", "BCY@8k"),
                           binary_metric="Recall@20", binary_label="any_gold_at_20",
                           bootstrap_samples=args.bootstrap_samples, seed=args.seed)
    summary["baseline_run"] = "+".join(args.baseline)
    summary["candidate_run"] = "+".join(args.candidate)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    m = summary["metrics"]; a = summary["any_gold_at_20"]
    def f(k):
        v = m[k]; lo, hi = v["repo_cluster_bootstrap_95_ci"]; return f"{v['mean_delta']:+.3f} [{lo:+.3f},{hi:+.3f}]"
    print(f"n={summary['cases']} MRR {f('MRR')} R@5 {f('Recall@5')} R@20 {f('Recall@20')} BCY {f('BCY@8k')} any-gold {a['candidate_cases']} vs {a['baseline_cases']} p={a['mcnemar_exact_p']:.3g}")


if __name__ == "__main__":
    main()
