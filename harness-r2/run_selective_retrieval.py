from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from statistics import fmean
from typing import Any

from harness.provider_clients import DelphiClient, NiaClient
from harness.run_static_retrieval import (
    dedupe,
    read_jsonl,
    source_ids,
    write_json,
    write_jsonl,
)

_BALANCED_HASH_PREFIX = "delphi-round2-selective-balanced-v1|"


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def balanced_positive_ids(
    positive_rows: list[dict[str, Any]],
    no_gold_count: int,
) -> set[str]:
    if len(positive_rows) < no_gold_count:
        raise ValueError("balanced mixture has fewer positives than no-gold rows")
    ordered = sorted(
        positive_rows,
        key=lambda row: hashlib.sha256(
            (_BALANCED_HASH_PREFIX + str(row["sample_id"])).encode()
        ).hexdigest(),
    )
    return {
        str(row["sample_id"])
        for row in ordered[:no_gold_count]
    }


def summarize_selective(
    positive_rows: list[dict[str, Any]],
    no_gold_rows: list[dict[str, Any]],
    *,
    provider_label: str,
) -> dict[str, Any]:
    if not positive_rows or not no_gold_rows:
        raise ValueError("selective evaluation requires both row classes")
    balanced_ids = balanced_positive_ids(
        positive_rows,
        len(no_gold_rows),
    )

    def summarize_mixture(
        positives: list[dict[str, Any]],
    ) -> dict[str, Any]:
        positive_successes = sum(
            float(row["metrics"].get("Recall@20", 0.0) > 0.0)
            for row in positives
        )
        no_gold_successes = sum(
            float(row["abstained"])
            for row in no_gold_rows
        )
        total = len(positives) + len(no_gold_rows)
        return {
            "n": total,
            "positive_n": len(positives),
            "no_gold_n": len(no_gold_rows),
            "selective_success@20": (
                positive_successes + no_gold_successes
            )
            / total,
            "positive_success@20": positive_successes / len(positives),
            "no_gold_true_abstention_rate": (
                no_gold_successes / len(no_gold_rows)
            ),
        }

    natural_rows = [
        row for row in no_gold_rows if row["no_gold_kind"] == "natural"
    ]
    counterfactual_rows = [
        row
        for row in no_gold_rows
        if row["no_gold_kind"] == "counterfactual"
    ]
    return {
        "schema_version": 1,
        "provider": provider_label,
        "balanced_selection": {
            "hash_prefix": _BALANCED_HASH_PREFIX,
            "positive_ids": sorted(balanced_ids),
        },
        "natural_prevalence": summarize_mixture(positive_rows),
        "balanced": summarize_mixture(
            [
                row
                for row in positive_rows
                if str(row["sample_id"]) in balanced_ids
            ]
        ),
        "natural_no_gold": {
            "n": len(natural_rows),
            "true_abstention_rate": fmean(
                float(row["abstained"]) for row in natural_rows
            ),
        },
        "counterfactual_no_gold": {
            "n": len(counterfactual_rows),
            "true_abstention_rate": fmean(
                float(row["abstained"]) for row in counterfactual_rows
            ),
        },
        "no_gold_failure_rate": fmean(
            float(row["status"] != "ok") for row in no_gold_rows
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("delphi", "nia"), required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--positive-details", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--arb-source", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--provider-fetch-limit", type=int, default=100)
    parser.add_argument("--base-url")
    parser.add_argument(
        "--nia-source-kind",
        choices=("repository", "local_folder"),
        default="repository",
    )
    parser.add_argument(
        "--nia-reasoning-strategy",
        choices=("vector", "hybrid", "tree"),
        default="vector",
    )
    parser.add_argument(
        "--nia-skip-llm",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--nia-fast-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()

    sys.path.insert(0, str(args.arb_source.resolve()))
    from agent_retrieval_bench.baseline import (
        query_has_leakage,
        query_text_for_eval,
    )

    ids = source_ids(args.sources)
    if args.engine == "delphi":
        provider: DelphiClient | NiaClient = DelphiClient(
            args.base_url or "http://127.0.0.1:18742",
            required_env("SYSTEM_PASSWORD"),
        )
    else:
        provider = NiaClient(
            args.base_url or "https://apigcp.trynia.ai/v2",
            required_env("NIA_API_KEY"),
            fast_mode=args.nia_fast_mode,
            reasoning_strategy=args.nia_reasoning_strategy,
            skip_llm=args.nia_skip_llm,
            source_kind=args.nia_source_kind,
        )

    samples = read_jsonl(args.samples)
    if any((row.get("gold") or {}).get("no_gold") is not True for row in samples):
        raise RuntimeError("--samples must contain only no-gold cases")
    details: list[dict[str, Any]] = []
    for sample in samples:
        repo = str(sample["repo"])
        revision = str(sample["base_commit"])
        query = query_text_for_eval(sample)
        if query_has_leakage(sample, query):
            raise RuntimeError(f"query leakage detected: {sample['id']}")
        source_id = ids.get((repo, revision.lower()))
        if not source_id:
            raise RuntimeError(f"missing source for {repo}@{revision}")
        observation = provider.search(
            query=query,
            repo=repo,
            revision=revision,
            source_id=source_id,
            limit=args.provider_fetch_limit,
        )
        paths = dedupe(observation.paths)[: args.limit]
        detail = {
            "sample_id": str(sample["id"]),
            "repo": repo,
            "base_commit": revision,
            "task_type": "abstention",
            "no_gold_kind": (
                "natural"
                if bool((sample.get("metadata") or {}).get("organic"))
                else "counterfactual"
            ),
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "top_files": paths,
            "status": observation.status,
            "error": observation.error,
            "latency_ms": observation.latency_ms,
            "abstained": observation.status == "ok" and not paths,
            "provider_metadata": observation.metadata,
        }
        details.append(detail)
        write_jsonl(args.details, details)
        print(
            json.dumps(
                {
                    "provider": provider.label,
                    "sample_id": detail["sample_id"],
                    "status": detail["status"],
                    "abstained": detail["abstained"],
                    "paths": len(paths),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    positives = read_jsonl(args.positive_details)
    summary = summarize_selective(
        positives,
        details,
        provider_label=provider.label,
    )
    summary.update(
        {
            "positive_details": str(args.positive_details),
            "no_gold_details": str(args.details),
            "source_manifest": str(args.sources),
            "limit": args.limit,
            "provider_fetch_limit": args.provider_fetch_limit,
        }
    )
    write_json(args.summary, summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
