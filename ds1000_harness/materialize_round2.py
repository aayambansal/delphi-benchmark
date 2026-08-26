from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def exposed_ids(protocol_path: Path) -> set[str]:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    track = protocol["tracks"]["ds1000_developer_utility"]
    return {
        *(str(value) for value in track["development_ids"]),
        *(str(value) for value in track["final_ids"]),
    }


def eligible_rows(
    rows: Iterable[dict[str, Any]],
    *,
    excluded: set[str],
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("docs")
        and str(row["metadata"]["problem_id"]) not in excluded
    ]


def select_splits(
    rows: Iterable[dict[str, Any]],
    *,
    qualification: dict[str, bool],
    development_per_library: int,
    final_per_library: int,
    seed: str,
) -> dict[str, list[dict[str, Any]]]:
    by_library: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        case_id = str(row["metadata"]["problem_id"])
        if qualification.get(case_id) is True:
            by_library[str(row["metadata"]["library"])].append(row)

    selected = {"development": [], "final": []}
    requested = development_per_library + final_per_library
    for library in sorted(by_library):
        candidates = sorted(
            by_library[library],
            key=lambda row: hashlib.sha256(
                (
                    f"{seed}:{library}:"
                    f"{row['metadata']['problem_id']}"
                ).encode()
            ).hexdigest(),
        )
        if len(candidates) < requested:
            raise ValueError(
                f"{library} has {len(candidates)} qualified cases; "
                f"{requested} required"
            )
        selected["development"].extend(candidates[:development_per_library])
        selected["final"].extend(candidates[development_per_library:requested])

    for split in selected:
        selected[split].sort(key=lambda row: int(row["metadata"]["problem_id"]))
    return selected


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    temporary.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--exclude-protocol", type=Path, required=True)
    parser.add_argument("--pool-output", type=Path, required=True)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--development-output", type=Path)
    parser.add_argument("--final-output", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--development-per-library", type=int, default=8)
    parser.add_argument("--final-per-library", type=int, default=20)
    parser.add_argument(
        "--seed",
        default="delphi-round2-ds1000-2026-07-29",
    )
    args = parser.parse_args()

    excluded = exposed_ids(args.exclude_protocol)
    pool = eligible_rows(read_jsonl(args.canonical), excluded=excluded)
    write_jsonl(args.pool_output, pool)

    manifest: dict[str, Any] = {
        "seed": args.seed,
        "canonical_sha256": sha256(args.canonical),
        "excluded_protocol_sha256": sha256(args.exclude_protocol),
        "excluded_ids": sorted(excluded, key=int),
        "excluded_ids_sha256": hashlib.sha256(
            "\n".join(sorted(excluded, key=int)).encode()
        ).hexdigest(),
        "eligibility": (
            "canonical DS-1000 rows with at least one CodeRAG-Bench "
            "documentation label, excluding all round-one exposed IDs"
        ),
        "eligible_n": len(pool),
        "eligible_by_library": dict(
            sorted(Counter(row["metadata"]["library"] for row in pool).items())
        ),
        "pool_sha256": sha256(args.pool_output),
    }

    if args.qualification is not None:
        if args.development_output is None or args.final_output is None:
            raise SystemExit(
                "--development-output and --final-output are required "
                "with --qualification"
            )
        payload = json.loads(args.qualification.read_text(encoding="utf-8"))
        qualification = {
            str(row["case_id"]): bool(row["reference_passed"])
            for row in payload["details"]
        }
        selected = select_splits(
            pool,
            qualification=qualification,
            development_per_library=args.development_per_library,
            final_per_library=args.final_per_library,
            seed=args.seed,
        )
        write_jsonl(args.development_output, selected["development"])
        write_jsonl(args.final_output, selected["final"])
        manifest["qualification_sha256"] = sha256(args.qualification)
        manifest["qualification_passed_n"] = sum(qualification.values())
        manifest["development_per_library"] = args.development_per_library
        manifest["final_per_library"] = args.final_per_library
        manifest["development_ids"] = [
            str(row["metadata"]["problem_id"])
            for row in selected["development"]
        ]
        manifest["final_ids"] = [
            str(row["metadata"]["problem_id"])
            for row in selected["final"]
        ]
        manifest["development_sha256"] = sha256(args.development_output)
        manifest["final_sha256"] = sha256(args.final_output)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
