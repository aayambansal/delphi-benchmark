"""Paired analysis for the answer-style synthesis parity experiment.

Compares the delphi_answer_synthesis arm (3 repeats) against the recorded
Nia full retrieval+synthesis pass and the synthesis_no_retrieval control
(3 repeats) on the 40-case documentation development set.

Atlas plan: full-clay-9675 (hypothesis mild-flaw-1796).
"""
from __future__ import annotations

import argparse
import json
from itertools import combinations
from math import comb
from pathlib import Path
from statistics import fmean

import random

ROOT = Path(__file__).resolve().parent.parent


def load_details(path: Path) -> dict[str, dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["case_id"]): row for row in rows}


def per_case_mean(repeat_paths: list[Path]) -> dict[str, float]:
    repeats = [load_details(path) for path in repeat_paths]
    case_ids = set(repeats[0])
    for repeat in repeats[1:]:
        if set(repeat) != case_ids:
            raise SystemExit("repeat case sets differ")
    return {
        case_id: fmean(
            float(bool(repeat[case_id]["identifier_hit"])) for repeat in repeats
        )
        for case_id in case_ids
    }


def cluster_bootstrap_ci(
    deltas_by_cluster: dict[str, list[float]],
    *,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    rng = random.Random(seed)
    clusters = sorted(deltas_by_cluster)
    stats = []
    for _ in range(samples):
        chosen = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        values = [v for name in chosen for v in deltas_by_cluster[name]]
        stats.append(fmean(values))
    stats.sort()
    return (
        stats[int(0.025 * samples)],
        stats[min(int(0.975 * samples), samples - 1)],
    )


def mcnemar_exact_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(0, min(b, c) + 1))
    p = 2.0 * tail / (2.0 ** n)
    return min(1.0, p)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=1042)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "DOCS-dev-answer-synthesis-analysis-v1.json",
    )
    args = parser.parse_args()

    results = ROOT / "results"
    answer_paths = [
        results / f"DOCS-dev-delphi-answer-synth-r{r}-details.json"
        for r in (1, 2, 3)
    ]
    control_paths = [
        results / f"DOCS-dev-control-synth-r{r}-details.json" for r in (1, 2, 3)
    ]
    nia = load_details(results / "DOCS-dev-nia-answer-full-details.json")
    answer = per_case_mean(answer_paths)
    control = per_case_mean(control_paths)
    libraries = {
        case_id: str(row.get("library") or "") for case_id, row in nia.items()
    }
    if set(answer) != set(nia) or set(control) != set(nia):
        raise SystemExit("case sets differ between arms")

    nia_hits = {case_id: float(bool(row["identifier_hit"])) for case_id, row in nia.items()}

    def paired(condition: dict[str, float], baseline: dict[str, float]) -> dict:
        deltas = {c: condition[c] - baseline[c] for c in sorted(baseline)}
        by_case = {c: [d] for c, d in deltas.items()}
        by_library: dict[str, list[float]] = {}
        for case_id, delta in deltas.items():
            by_library.setdefault(libraries[case_id], []).append(delta)
        case_ci = cluster_bootstrap_ci(
            by_case, samples=args.samples, seed=args.seed
        )
        library_ci = cluster_bootstrap_ci(
            by_library, samples=args.samples, seed=args.seed
        )
        wins = sum(1 for d in deltas.values() if d > 0)
        losses = sum(1 for d in deltas.values() if d < 0)
        ties = sum(1 for d in deltas.values() if d == 0)
        return {
            "condition_mean": fmean(condition.values()),
            "baseline_mean": fmean(baseline.values()),
            "mean_delta": fmean(deltas.values()),
            "case_cluster_bootstrap_95_ci": list(case_ci),
            "library_cluster_bootstrap_95_ci": list(library_ci),
            "wins": wins,
            "losses": losses,
            "ties": ties,
        }

    c7_paths = [
        results / f"DOCS-dev-context7-answer-synth-r{r}-details.json"
        for r in (1, 2, 3)
    ]
    context7 = (
        per_case_mean(c7_paths) if all(p.exists() for p in c7_paths) else None
    )
    nia_matched_paths = [
        results / f"DOCS-dev-nia-retrieved-answer-synth-r{r}-details.json"
        for r in (1, 2, 3)
    ]
    nia_matched = (
        per_case_mean(nia_matched_paths)
        if all(p.exists() for p in nia_matched_paths)
        else None
    )
    nia_raw_path = results / "DOCS-dev-nia-retrieved-k5-details.json"
    nia_raw = (
        {c: float(bool(row["identifier_hit"])) for c, row in load_details(nia_raw_path).items()}
        if nia_raw_path.exists()
        else None
    )

    majority = {c: 1.0 if answer[c] >= 2 / 3 else 0.0 for c in answer}
    b = sum(1 for c in majority if majority[c] > nia_hits[c])
    c_count = sum(1 for c in majority if majority[c] < nia_hits[c])

    analysis = {
        "cases": len(nia_hits),
        "repeats": 3,
        "bootstrap_samples": args.samples,
        "bootstrap_seed": args.seed,
        "arms": {
            "delphi_answer_synthesis": {
                "per_repeat_rates": [
                    fmean(
                        float(bool(row["identifier_hit"]))
                        for row in load_details(path).values()
                    )
                    for path in answer_paths
                ],
                "case_mean_rate": fmean(answer.values()),
            },
            "synthesis_no_retrieval": {
                "per_repeat_rates": [
                    fmean(
                        float(bool(row["identifier_hit"]))
                        for row in load_details(path).values()
                    )
                    for path in control_paths
                ],
                "case_mean_rate": fmean(control.values()),
            },
            "nia_full_recorded": {"case_mean_rate": fmean(nia_hits.values())},
            **(
                {
                    "context7_answer_synthesis": {
                        "per_repeat_rates": [
                            fmean(
                                float(bool(row["identifier_hit"]))
                                for row in load_details(path).values()
                            )
                            for path in c7_paths
                        ],
                        "case_mean_rate": fmean(context7.values()),
                    }
                }
                if context7 is not None
                else {}
            ),
        },
        "answer_vs_nia": paired(answer, nia_hits),
        "answer_vs_control": paired(answer, control),
        "control_vs_nia": paired(control, nia_hits),
        **(
            {
                "arms_nia_retrieved_answer_synthesis": {
                    "per_repeat_rates": [
                        fmean(
                            float(bool(row["identifier_hit"]))
                            for row in load_details(path).values()
                        )
                        for path in nia_matched_paths
                    ],
                    "case_mean_rate": fmean(nia_matched.values()),
                    "note": (
                        "the hosted engine's five recorded retrieved source chunks, "
                        "packed under the shared 8,000-token budget and routed through "
                        "the same frozen synthesis stage as every other arm"
                    ),
                },
                "nia_matched_vs_nia_native": paired(nia_matched, nia_hits),
                "nia_matched_vs_control": paired(nia_matched, control),
                "answer_vs_nia_matched": paired(answer, nia_matched),
                **(
                    {"context7_vs_nia_matched": paired(context7, nia_matched)}
                    if context7 is not None
                    else {}
                ),
            }
            if nia_matched is not None
            else {}
        ),
        **(
            {
                "raw_retrieval_identifier_hit": {
                    "nia_retrieved_k5_reconstructed": fmean(nia_raw.values()),
                    "note": "raw (unsynthesized) context hit rates; Delphi compact k=5 0.400 and k=20 0.425 are recorded in DOCS-dev-delphi-compact*-summary.json",
                }
            }
            if nia_raw is not None
            else {}
        ),
        **(
            {
                "context7_vs_nia": paired(context7, nia_hits),
                "context7_vs_control": paired(context7, control),
                "answer_vs_context7": paired(answer, context7),
            }
            if context7 is not None
            else {}
        ),
        "majority_vote_vs_nia_mcnemar": {
            "answer_majority_only": b,
            "nia_only": c_count,
            "exact_p": mcnemar_exact_p(b, c_count),
        },
        "success_criterion": "metrics.identifier_hit_rate >= 0.575",
        "criterion_met": fmean(answer.values()) >= 0.575,
    }
    args.output.write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(analysis, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
