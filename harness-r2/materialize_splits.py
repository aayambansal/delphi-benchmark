from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


POSITIVE_RELEASES = (
    "v2_code2test",
    "v2_comment2context",
    "v2_trace2code",
    "v2_edit2ripple",
)
ABSTENTION_RELEASE = "v2_abstention"
ALL_RELEASES = (*POSITIVE_RELEASES, ABSTENTION_RELEASE)
SEED = "delphi-round2-v1"
PROTOCOL_SHA256 = "54e879fc45db2ea36f10911a8690374604ad9197fcd99e25ba1cd795c5f124bb"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    temporary.replace(path)


def prior_trace_ids(protocol_path: Path) -> set[str]:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    track = protocol["tracks"]["arb_trace2code"]
    return {
        *(str(item) for item in track["development_ids"]),
        *(str(item) for item in track["final_ids"]),
    }


def abstention_stratum(row: dict[str, Any]) -> str:
    reason = str((row.get("gold") or {}).get("reason") or "")
    return "counterfactual" if "counterfactual" in reason else "natural"


def split_key(release_id: str, stratum: str, case_id: str) -> str:
    payload = f"{SEED}|{release_id}|{stratum}|{case_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def split_rows(
    *,
    release_id: str,
    rows: list[dict[str, Any]],
    exposed_trace_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    legacy: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for row in rows:
        case_id = str(row["id"])
        if release_id == "v2_trace2code" and case_id in exposed_trace_ids:
            legacy.append(row)
        else:
            eligible.append(row)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        stratum = (
            abstention_stratum(row)
            if release_id == ABSTENTION_RELEASE
            else str(row["repo"])
        )
        groups[stratum].append(row)

    development: list[dict[str, Any]] = []
    final: list[dict[str, Any]] = []
    for stratum, stratum_rows in sorted(groups.items()):
        ordered = sorted(
            stratum_rows,
            key=lambda row: split_key(release_id, stratum, str(row["id"])),
        )
        development_count = max(1, math.floor(0.25 * len(ordered)))
        development.extend(ordered[:development_count])
        final.extend(ordered[development_count:])

    return {
        "development": sorted(development, key=lambda row: str(row["id"])),
        "final": sorted(final, key=lambda row: str(row["id"])),
        "legacy_exposed": sorted(legacy, key=lambda row: str(row["id"])),
    }


def materialize(
    *,
    data_root: Path,
    prior_protocol: Path,
    output_root: Path,
) -> dict[str, Any]:
    exposed = prior_trace_ids(prior_protocol)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "seed": SEED,
        "protocol_sha256": PROTOCOL_SHA256,
        "prior_protocol_sha256": sha256_file(prior_protocol),
        "split_rule": (
            "Within release/repository (or abstention provenance), order by "
            "SHA256(seed|release|stratum|id); first max(1,floor(0.25*n)) "
            "development, remainder final. Prior trace IDs are legacy-exposed."
        ),
        "releases": {},
    }

    seen_ids: set[str] = set()
    total = 0
    for release_id in ALL_RELEASES:
        samples_path = data_root / "benchmark" / release_id / "samples.jsonl"
        rows = read_jsonl(samples_path)
        splits = split_rows(
            release_id=release_id,
            rows=rows,
            exposed_trace_ids=exposed,
        )
        flattened = [row for split in splits.values() for row in split]
        ids = [str(row["id"]) for row in flattened]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate case IDs within {release_id}")
        overlap = seen_ids.intersection(ids)
        if overlap:
            raise ValueError(f"cross-release duplicate IDs: {sorted(overlap)[:3]}")
        seen_ids.update(ids)
        total += len(rows)

        for split_name, split_rows_value in splits.items():
            write_jsonl(
                output_root / split_name / f"{release_id}.jsonl",
                split_rows_value,
            )
        manifest["releases"][release_id] = {
            "samples_path": str(samples_path),
            "samples_sha256": sha256_file(samples_path),
            "total": len(rows),
            "development_ids": [str(row["id"]) for row in splits["development"]],
            "final_ids": [str(row["id"]) for row in splits["final"]],
            "legacy_exposed_ids": [
                str(row["id"]) for row in splits["legacy_exposed"]
            ],
        }

    if total != 427:
        raise ValueError(f"expected 427 total V2 rows, found {total}")
    if len(manifest["releases"]["v2_trace2code"]["legacy_exposed_ids"]) != 50:
        raise ValueError("expected exactly 50 legacy-exposed trace2code IDs")

    manifest["totals"] = {
        "all": total,
        "development": sum(
            len(value["development_ids"])
            for value in manifest["releases"].values()
        ),
        "final": sum(
            len(value["final_ids"]) for value in manifest["releases"].values()
        ),
        "legacy_exposed": sum(
            len(value["legacy_exposed_ids"])
            for value in manifest["releases"].values()
        ),
    }
    write_json(output_root / "split-manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--prior-protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    manifest = materialize(
        data_root=args.data_root,
        prior_protocol=args.prior_protocol,
        output_root=args.output_root,
    )
    print(json.dumps(manifest["totals"], sort_keys=True))


if __name__ == "__main__":
    main()

