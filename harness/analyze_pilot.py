"""Paired analysis of the executable agent pilot (context/PILOT_PROTOCOL.md).

Inputs per condition label (e.g. ``none-s50``):
  results/pilot/eval/<label>/gpt-5.4-mini.<label>.json   official harness report
  results/pilot/runs/<label>/<instance>/<instance>.traj.json   trajectories
  results/pilot/datasets/<condition>/manifest.json         seed files per instance

Outputs results/pilot/analysis-<budget>.json and a markdown summary. Every
comparison is paired by instance; intervals are cluster bootstraps over
instances and over repositories (20,000 resamples, seed 1042); discordant
pairs get an exact McNemar test.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "results" / "pilot"


def mcnemar_exact_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def cluster_bootstrap_ci(deltas_by_cluster: dict[str, list[float]], *, samples: int, seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    clusters = list(deltas_by_cluster)
    means = []
    for _ in range(samples):
        picked = [deltas_by_cluster[rng.choice(clusters)] for _ in clusters]
        flat = [d for group in picked for d in group]
        means.append(fmean(flat))
    means.sort()
    return means[int(0.025 * samples)], means[int(0.975 * samples) - 1]


def load_condition(label: str, model: str) -> dict[str, dict]:
    report_path = PILOT / "eval" / label / f"{model}.{label}.json"
    report = json.load(report_path.open()) if report_path.exists() else {}
    resolved = set(report.get("resolved_ids", []))
    submitted = set(report.get("submitted_ids", []))
    completed = set(report.get("completed_ids", []))
    rows: dict[str, dict] = {}
    run_dir = PILOT / "runs" / label
    for traj in run_dir.glob("*/*.traj.json"):
        t = json.load(traj.open())
        iid = t.get("instance_id") or traj.stem.replace(".traj", "")
        stats = (t.get("info") or {}).get("model_stats") or {}
        n_steps = sum(1 for m in t.get("messages", []) if m.get("role") == "assistant")
        rows[iid] = {
            "instance_id": iid,
            "resolved": iid in resolved,
            "submitted": iid in submitted or bool((t.get("info") or {}).get("submission")),
            "evaluated": iid in completed,
            "exit_status": (t.get("info") or {}).get("exit_status"),
            "cost_usd": float(stats.get("instance_cost") or 0.0),
            "api_calls": int(stats.get("api_calls") or 0),
            "steps": n_steps,
        }
    return rows


def repo_of(cases: dict[str, dict], iid: str) -> str:
    return str(cases.get(iid, {}).get("repo") or iid.split("__")[0])


def paired(a: dict[str, dict], b: dict[str, dict], key: str, cases: dict[str, dict], *, samples: int, seed: int) -> dict:
    ids = sorted(set(a) & set(b))
    deltas = {i: float(a[i][key]) - float(b[i][key]) for i in ids}
    by_inst = {i: [d] for i, d in deltas.items()}
    by_repo: dict[str, list[float]] = {}
    for i, d in deltas.items():
        by_repo.setdefault(repo_of(cases, i), []).append(d)
    out = {
        "n": len(ids),
        "mean_a": fmean(float(a[i][key]) for i in ids) if ids else None,
        "mean_b": fmean(float(b[i][key]) for i in ids) if ids else None,
        "mean_delta": fmean(deltas.values()) if ids else None,
        "instance_cluster_95_ci": list(cluster_bootstrap_ci(by_inst, samples=samples, seed=seed)) if ids else None,
        "repository_cluster_95_ci": list(cluster_bootstrap_ci(by_repo, samples=samples, seed=seed)) if ids else None,
    }
    if key in ("resolved", "submitted"):
        wins = sum(1 for i in ids if float(a[i][key]) > float(b[i][key]))
        losses = sum(1 for i in ids if float(b[i][key]) > float(a[i][key]))
        out.update({"a_only": wins, "b_only": losses, "mcnemar_exact_p": mcnemar_exact_p(wins, losses)})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", default="s50")
    parser.add_argument("--repeats", default=None, help="comma-separated labels to pool per instance (e.g. s50,s50-r2); overrides --budget")
    parser.add_argument("--conditions", default="none,random,delphi,hybrid_rerank_expand")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--cases", type=Path, default=ROOT / "samples" / "swebench" / "cases.jsonl")
    parser.add_argument("--samples", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=1042)
    parser.add_argument("--pairs", default=None, help="comma-separated a:b pairs to analyse (overrides the default pair set)")
    parser.add_argument("--out-label", default=None, help="output file suffix (default: the budget label)")
    args = parser.parse_args()

    cases = {str(r["id"]): r for r in (json.loads(l) for l in args.cases.open() if l.strip())}
    conds = {}
    labels = args.repeats.split(",") if args.repeats else [args.budget]
    for c in args.conditions.split(","):
        per_label = [load_condition(f"{c}-{lab}", args.model) for lab in labels]
        per_label = [r for r in per_label if r]
        if not per_label:
            continue
        if len(per_label) == 1:
            conds[c] = per_label[0]
            continue
        # pool repeats: per-instance means of resolved/cost/steps over repeats present in every label
        ids = set.intersection(*(set(r) for r in per_label))
        pooled = {}
        for i in ids:
            rows = [r[i] for r in per_label]
            pooled[i] = {
                "instance_id": i,
                "resolved": sum(float(r["resolved"]) for r in rows) / len(rows),
                "submitted": sum(float(r["submitted"]) for r in rows) / len(rows),
                "evaluated": all(r["evaluated"] for r in rows),
                "exit_status": "pooled",
                "cost_usd": sum(r["cost_usd"] for r in rows) / len(rows),
                "api_calls": sum(r["api_calls"] for r in rows) / len(rows),
                "steps": sum(r["steps"] for r in rows) / len(rows),
                "repeats": len(rows),
            }
        conds[c] = pooled
    budget_label = "+".join(labels)
    if not conds:
        sys.exit("no pilot results found")

    common = set.intersection(*(set(r) for r in conds.values()))
    summary = {
        "budget": budget_label,
        "model": args.model,
        "instances_common": len(common),
        "conditions": {},
        "pairs": {},
    }
    for c, rows in conds.items():
        sub = {i: rows[i] for i in common}
        summary["conditions"][c] = {
            "n": len(sub),
            "resolved_rate": fmean(float(r["resolved"]) for r in sub.values()) if sub else None,
            "resolved": sum(float(r["resolved"]) for r in sub.values()),
            "submitted_rate": fmean(float(r["submitted"]) for r in sub.values()) if sub else None,
            "mean_cost_usd": fmean(r["cost_usd"] for r in sub.values()) if sub else None,
            "total_cost_usd": sum(r["cost_usd"] for r in sub.values()),
            "mean_steps": fmean(r["steps"] for r in sub.values()) if sub else None,
            "exit_statuses": {},
        }
        for r in sub.values():
            s = str(r["exit_status"])
            summary["conditions"][c]["exit_statuses"][s] = summary["conditions"][c]["exit_statuses"].get(s, 0) + 1
    if args.pairs:
        wanted = [tuple(p.split(":")) for p in args.pairs.split(",")]
    else:
        order = [c for c in ("delphi", "hybrid_rerank_expand", "random", "none") if c in conds]
        wanted = [(a, b) for a in order for b in order
                  if a != b and (a, b) not in (("none", "random"),)
                  and (b in ("none", "random") or (a == "delphi" and b == "hybrid_rerank_expand"))]
    for a, b in wanted:
        if a not in conds or b not in conds:
            continue
        sa = {i: conds[a][i] for i in common}
        sb = {i: conds[b][i] for i in common}
        summary["pairs"][f"{a}_minus_{b}"] = {
            "resolved": paired(sa, sb, "resolved", cases, samples=args.samples, seed=args.seed),
            "cost_usd": paired(sa, sb, "cost_usd", cases, samples=args.samples, seed=args.seed),
            "steps": paired(sa, sb, "steps", cases, samples=args.samples, seed=args.seed),
        }
    out = PILOT / f"analysis-{(args.out_label or budget_label).replace('+', '_')}.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in summary["conditions"].items()}, indent=1))
    for name, p in summary["pairs"].items():
        r = p["resolved"]
        lo, hi = r["instance_cluster_95_ci"]
        print(f"{name:40s} resolved {r['mean_delta']:+.3f} [{lo:+.3f},{hi:+.3f}] a-only {r['a_only']} b-only {r['b_only']} p={r['mcnemar_exact_p']:.3f}")
    print("wrote", out)


if __name__ == "__main__":
    main()
