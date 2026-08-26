"""Materialize the round-3 dev/final split with a fresh salt.

Within each (release, stratum) group, order case IDs by
SHA256("delphi-round3-v1|release|stratum|id"); the first max(1, floor(0.25*n))
are development, the rest final. The 50 round-1 legacy-exposed trace2code IDs
stay excluded from both partitions.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

SEED = "delphi-round3-v1"
ROOT = Path(__file__).resolve().parent.parent
R2 = ROOT.parent / "delphi-evaluation-2026-07-29-round2"
DATA = R2 / "arb-data"
OUT = ROOT / "samples"

POSITIVE = ("v2_code2test", "v2_comment2context", "v2_trace2code", "v2_edit2ripple")
ABSTENTION = "v2_abstention"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def split_key(release: str, stratum: str, case_id: str) -> str:
    return hashlib.sha256(f"{SEED}|{release}|{stratum}|{case_id}".encode()).hexdigest()


def main() -> None:
    r2_manifest = json.loads((R2 / "samples" / "split-manifest.json").read_text())
    legacy = set(r2_manifest["releases"]["v2_trace2code"]["legacy_exposed_ids"])
    assert len(legacy) == 50, len(legacy)

    manifest: dict = {"seed": SEED, "releases": {}, "legacy_exposed_trace2code": sorted(legacy)}
    totals = {"development": 0, "final": 0, "excluded": 0}
    for release in (*POSITIVE, ABSTENTION):
        rows = read_jsonl(DATA / "benchmark" / release / "samples.jsonl")
        eligible, excluded = [], []
        for row in rows:
            if release == "v2_trace2code" and str(row["id"]) in legacy:
                excluded.append(row)
            else:
                eligible.append(row)
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in eligible:
            if release == ABSTENTION:
                reason = str((row.get("gold") or {}).get("reason") or "")
                stratum = "counterfactual" if "counterfactual" in reason else "natural"
            else:
                stratum = str(row["repo"])
            groups[stratum].append(row)
        dev, final = [], []
        for stratum, srows in sorted(groups.items()):
            ordered = sorted(srows, key=lambda r: split_key(release, stratum, str(r["id"])))
            k = max(1, math.floor(0.25 * len(ordered)))
            dev.extend(ordered[:k])
            final.extend(ordered[k:])
        dev.sort(key=lambda r: str(r["id"]))
        final.sort(key=lambda r: str(r["id"]))
        write_jsonl(OUT / "development" / f"{release}.jsonl", dev)
        write_jsonl(OUT / "final" / f"{release}.jsonl", final)
        manifest["releases"][release] = {
            "total": len(rows),
            "development_ids": [str(r["id"]) for r in dev],
            "final_ids": [str(r["id"]) for r in final],
            "excluded": len(excluded),
        }
        totals["development"] += len(dev)
        totals["final"] += len(final)
        totals["excluded"] += len(excluded)
    manifest["totals"] = totals
    (OUT / "split-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
