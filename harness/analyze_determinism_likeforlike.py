"""Like-for-like repeatability across engines with different output contracts.

The headline "98.0% vs 35.6% vs 0.0% byte-identical context" compares the
stability of retrieved text for two engines with the stability of generated
text for a third. This script separates the layers so each engine is judged
on the same quantity:

  retrieved-set exact     the set of retrieved sources is identical across a
                          pair of runs (Delphi/Context7: item identities;
                          the synthesis engine: the set of cited URLs, since
                          its retrieval surface is only observable through
                          citations)
  retrieved-order exact   the ordered list of sources is identical (only
                          meaningful for engines that expose an order)
  retrieved-set Jaccard   mean pairwise Jaccard of the sets above
  context byte-exact      the delivered context text is byte-identical
  hit agreement           the identifier-hit outcome agrees across the pair

Inputs are the raw 10x10 documentation repeats under determinism/<engine>/.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path
from statistics import fmean
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.analyze_docs_determinism import item_identity  # noqa: E402

_URL = re.compile(r"https?://[^\s)\]\"'>]+")

ENGINES = {
    "delphi_compact": ("determinism/delphi/docs-compact-r{n}-details.json", "items"),
    "context7_guided_compact": ("determinism/context7/docs-guided-compact-r{n}-details.json", "items"),
    "context7_oracle_compact": ("determinism/context7/docs-oracle-compact-r{n}-details.json", "items"),
    "nia_full_synthesis": ("determinism/nia/docs-full-r{n}-details.json", "citations"),
}


def _normalize_url(url: str) -> str:
    url = url.rstrip(".,;:")
    url = url.split("#", 1)[0]
    return url.rstrip("/")


def retrieved_sources(row: dict[str, Any], mode: str) -> list[str]:
    if mode == "items":
        return [item_identity(item) for item in row.get("items") or []]
    text = "\n".join(str(item.get("path") or "") for item in row.get("items") or [])
    text += "\n" + str(row.get("context") or "")
    return list(dict.fromkeys(_normalize_url(u) for u in _URL.findall(text)))


def load_runs(pattern: str, runs: int) -> list[dict[str, dict[str, Any]]]:
    out = []
    for n in range(1, runs + 1):
        path = ROOT / pattern.format(n=n)
        if not path.exists():
            continue
        data = json.load(path.open())
        rows = data if isinstance(data, list) else data.get("details") or []
        out.append({str(r.get("case_id")): r for r in rows})
    return out


def analyze(runs: list[dict[str, dict[str, Any]]], mode: str) -> dict[str, Any]:
    set_exact: list[float] = []
    order_exact: list[float] = []
    jaccard: list[float] = []
    byte_exact: list[float] = []
    hit_agree: list[float] = []
    sizes: list[int] = []
    for left, right in combinations(runs, 2):
        for case_id, lrow in left.items():
            rrow = right.get(case_id)
            if rrow is None:
                continue
            ls = retrieved_sources(lrow, mode)
            rs = retrieved_sources(rrow, mode)
            sizes.extend([len(ls), len(rs)])
            lset, rset = set(ls), set(rs)
            set_exact.append(1.0 if lset == rset else 0.0)
            order_exact.append(1.0 if ls == rs else 0.0)
            union = lset | rset
            jaccard.append(len(lset & rset) / len(union) if union else 1.0)
            byte_exact.append(1.0 if (lrow.get("context") or "") == (rrow.get("context") or "") else 0.0)
            hit_agree.append(1.0 if bool(lrow.get("identifier_hit")) == bool(rrow.get("identifier_hit")) else 0.0)
    return {
        "runs": len(runs),
        "paired_case_comparisons": len(set_exact),
        "source_unit": "cited_urls" if mode == "citations" else "retrieved_items",
        "mean_sources_per_run": fmean(sizes) if sizes else None,
        "retrieved_set_exact_rate": fmean(set_exact) if set_exact else None,
        "retrieved_order_exact_rate": fmean(order_exact) if order_exact else None,
        "retrieved_set_jaccard": fmean(jaccard) if jaccard else None,
        "context_byte_exact_rate": fmean(byte_exact) if byte_exact else None,
        "identifier_hit_agreement_rate": fmean(hit_agree) if hit_agree else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "DETERMINISM-docs-like-for-like-v1.json")
    args = parser.parse_args()
    report: dict[str, Any] = {"schema": "determinism_like_for_like_v1", "engines": {}}
    for engine, (pattern, mode) in ENGINES.items():
        runs = load_runs(pattern, args.runs)
        if not runs:
            continue
        report["engines"][engine] = analyze(runs, mode)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for engine, stats in report["engines"].items():
        print(
            f"{engine:26s} set-exact {stats['retrieved_set_exact_rate']:.3f}  "
            f"order-exact {stats['retrieved_order_exact_rate']:.3f}  "
            f"set-Jaccard {stats['retrieved_set_jaccard']:.3f}  "
            f"byte-exact {stats['context_byte_exact_rate']:.3f}  "
            f"hit-agree {stats['identifier_hit_agreement_rate']:.3f}  "
            f"(unit={stats['source_unit']}, n/run={stats['mean_sources_per_run']:.1f})"
        )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
