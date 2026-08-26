from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate percentile of no values")
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def metric_estimands(
    rows: Iterable[dict[str, Any]],
    metric: str,
) -> dict[str, float]:
    materialized = list(rows)
    if not materialized:
        raise ValueError("cannot estimate metrics from no rows")
    by_repo: dict[str, list[float]] = defaultdict(list)
    by_workflow: dict[str, list[float]] = defaultdict(list)
    values: list[float] = []
    for row in materialized:
        value = float(row["metrics"][metric])
        values.append(value)
        by_repo[str(row["repo"])].append(value)
        by_workflow[str(row["task_type"])].append(value)
    return {
        "sample_weighted": fmean(values),
        "repository_macro": fmean(
            fmean(group) for group in by_repo.values()
        ),
        "workflow_macro": fmean(
            fmean(group) for group in by_workflow.values()
        ),
    }


def validate_paired_arms(
    arms: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    if len(arms) < 2:
        raise ValueError("at least two arms are required")
    indexed = {
        label: {str(row["sample_id"]): row for row in rows}
        for label, rows in arms.items()
    }
    if any(len(rows) != len(indexed[label]) for label, rows in arms.items()):
        raise ValueError("duplicate sample_id in an arm")
    sample_sets = {label: set(rows) for label, rows in indexed.items()}
    first_label = next(iter(arms))
    expected = sample_sets[first_label]
    for label, sample_ids in sample_sets.items():
        if sample_ids != expected:
            raise ValueError(
                f"sample set mismatch for {label}: "
                f"{len(sample_ids)} != {len(expected)}"
            )
    for sample_id in expected:
        identities = {
            (
                str(rows[sample_id]["repo"]),
                str(rows[sample_id]["task_type"]),
            )
            for rows in indexed.values()
        }
        if len(identities) != 1:
            raise ValueError(f"sample identity mismatch: {sample_id}")
    return indexed


def paired_repository_bootstrap(
    arms: dict[str, list[dict[str, Any]]],
    *,
    reference: str,
    metrics: tuple[str, ...],
    resamples: int,
    seed: int,
    confidence_level: float,
) -> dict[str, Any]:
    indexed = validate_paired_arms(arms)
    if reference not in indexed:
        raise ValueError(f"unknown reference arm: {reference}")
    reference_rows = indexed[reference]
    repo_sample_ids: dict[str, list[str]] = defaultdict(list)
    for sample_id, row in reference_rows.items():
        repo_sample_ids[str(row["repo"])].append(sample_id)
    repos = sorted(repo_sample_ids)
    if not repos:
        raise ValueError("no repositories to resample")
    rng = random.Random(seed)
    draws = [
        [rng.choice(repos) for _ in repos]
        for _ in range(resamples)
    ]
    alpha = (1 - confidence_level) / 2

    output: dict[str, Any] = {
        "schema_version": 1,
        "reference": reference,
        "n": len(reference_rows),
        "repositories": len(repos),
        "resamples": resamples,
        "seed": seed,
        "confidence_level": confidence_level,
        "metrics": {},
    }
    for metric in metrics:
        point = {
            label: metric_estimands(rows.values(), metric)
            for label, rows in indexed.items()
        }
        bootstrap_levels: dict[
            str, dict[str, list[float]]
        ] = {
            label: {
                name: []
                for name in (
                    "sample_weighted",
                    "repository_macro",
                    "workflow_macro",
                )
            }
            for label in indexed
        }
        bootstrap_effects: dict[
            str, dict[str, list[float]]
        ] = {
            label: {
                name: []
                for name in (
                    "sample_weighted",
                    "repository_macro",
                    "workflow_macro",
                )
            }
            for label in indexed
            if label != reference
        }
        for sampled_repos in draws:
            sample_ids = [
                sample_id
                for repo in sampled_repos
                for sample_id in repo_sample_ids[repo]
            ]
            estimates = {
                label: metric_estimands(
                    (rows[sample_id] for sample_id in sample_ids),
                    metric,
                )
                for label, rows in indexed.items()
            }
            for label, values in estimates.items():
                for estimand, value in values.items():
                    bootstrap_levels[label][estimand].append(value)
            for label in bootstrap_effects:
                for estimand, value in estimates[label].items():
                    bootstrap_effects[label][estimand].append(
                        value - estimates[reference][estimand]
                    )

        output["metrics"][metric] = {
            "arms": {
                label: {
                    estimand: {
                        "estimate": value,
                        "ci_low": percentile(
                            bootstrap_levels[label][estimand],
                            alpha,
                        ),
                        "ci_high": percentile(
                            bootstrap_levels[label][estimand],
                            1 - alpha,
                        ),
                    }
                    for estimand, value in values.items()
                }
                for label, values in point.items()
            },
            "paired_effects_vs_reference": {
                label: {
                    estimand: {
                        "estimate": (
                            point[label][estimand]
                            - point[reference][estimand]
                        ),
                        "ci_low": percentile(
                            bootstrap_effects[label][estimand],
                            alpha,
                        ),
                        "ci_high": percentile(
                            bootstrap_effects[label][estimand],
                            1 - alpha,
                        ),
                    }
                    for estimand in point[label]
                }
                for label in bootstrap_effects
            },
        }
    return output


def parse_arm(value: str) -> tuple[str, Path]:
    label, separator, raw_path = value.partition("=")
    if not separator or not label or not raw_path:
        raise argparse.ArgumentTypeError("--arm must be LABEL=DETAILS.jsonl")
    return label, Path(raw_path)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", action="append", type=parse_arm, required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    arms = {label: read_jsonl(path) for label, path in args.arm}
    result = paired_repository_bootstrap(
        arms,
        reference=args.reference,
        metrics=tuple(str(value) for value in lock["metrics"]),
        resamples=int(lock["resamples"]),
        seed=int(lock["seed"]),
        confidence_level=float(lock["confidence_level"]),
    )
    result["statistics_lock"] = str(args.lock)
    write_json(args.output, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
