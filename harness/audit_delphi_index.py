"""Fail-closed source and embedding audit for a provisioned Delphi corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, create_engine, text

from harness.gitcorpus import needed_snapshots
from harness.provision_delphi_local import is_valid_indexed_record


def _pair(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["repo"]), str(row["revision"]).lower()


def _pair_labels(pairs: set[tuple[str, str]]) -> list[str]:
    return sorted(f"{repo}@{revision}" for repo, revision in pairs)


def build_index_audit(
    required_pairs: set[tuple[str, str]],
    manifest_rows: list[dict[str, Any]],
    database_rows: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Compare the exact required snapshots, manifest, and database state."""
    required = {(repo, revision.lower()) for repo, revision in required_pairs}
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in manifest_rows:
        key = _pair(row)
        if is_valid_indexed_record(row) and isinstance(row.get("source_id"), str):
            latest[key] = row
        else:
            latest.pop(key, None)

    valid_pairs = set(latest)
    missing_pairs = required - valid_pairs
    extra_pairs = valid_pairs - required
    selected_rows = [latest[key] for key in sorted(required & valid_pairs)]
    source_ids = [str(row["source_id"]) for row in selected_rows]
    duplicate_source_ids = sorted(
        source_id
        for source_id, count in Counter(source_ids).items()
        if count > 1
    )
    missing_source_ids = sorted(set(source_ids) - set(database_rows))
    zero_file_source_ids = sorted(
        source_id
        for source_id in source_ids
        if database_rows.get(source_id, {}).get("files", 0) <= 0
    )
    zero_chunk_source_ids = sorted(
        source_id
        for source_id in source_ids
        if database_rows.get(source_id, {}).get("chunks", 0) <= 0
    )
    embedding_mismatches = sorted(
        source_id
        for source_id in source_ids
        if source_id in database_rows
        and database_rows[source_id].get("chunks")
        != database_rows[source_id].get("embeddings")
    )
    selected_database_rows = [
        database_rows[source_id]
        for source_id in source_ids
        if source_id in database_rows
    ]
    canonical_manifest = (
        len(manifest_rows) == len(required) == len(latest)
        and not missing_pairs
        and not extra_pairs
    )
    complete = not any(
        (
            missing_pairs,
            extra_pairs,
            duplicate_source_ids,
            missing_source_ids,
            zero_file_source_ids,
            zero_chunk_source_ids,
            embedding_mismatches,
        )
    ) and canonical_manifest
    return {
        "required_snapshot_pairs": len(required),
        "manifest_rows": len(manifest_rows),
        "valid_snapshot_pairs": len(valid_pairs),
        "canonical_manifest": canonical_manifest,
        "missing_snapshot_pairs": _pair_labels(missing_pairs),
        "extra_snapshot_pairs": _pair_labels(extra_pairs),
        "duplicate_source_ids": duplicate_source_ids,
        "database": {
            "repositories": len(selected_database_rows),
            "files": sum(row["files"] for row in selected_database_rows),
            "chunks": sum(row["chunks"] for row in selected_database_rows),
            "embeddings": sum(row["embeddings"] for row in selected_database_rows),
            "missing_source_ids": missing_source_ids,
            "zero_file_source_ids": zero_file_source_ids,
            "zero_chunk_source_ids": zero_chunk_source_ids,
            "chunk_embedding_mismatch_source_ids": embedding_mismatches,
        },
        "complete": complete,
    }


def fetch_database_rows(
    database_url: str,
    source_ids: list[str],
) -> dict[str, dict[str, int]]:
    if not source_ids:
        return {}
    statement = text(
        """
        SELECT
            r.repo_id,
            (SELECT count(*) FROM repository_files f
             WHERE f.repo_id = r.repo_id) AS files,
            (SELECT count(*) FROM code_chunks c
             WHERE c.repo_id = r.repo_id) AS chunks,
            (SELECT count(*) FROM chunk_embeddings e
             WHERE e.repo_id = r.repo_id) AS embeddings
        FROM repositories r
        WHERE r.repo_id IN :source_ids
        """
    ).bindparams(bindparam("source_ids", expanding=True))
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                statement,
                {"source_ids": source_ids},
            ).mappings()
            return {
                str(row["repo_id"]): {
                    "files": int(row["files"]),
                    "chunks": int(row["chunks"]),
                    "embeddings": int(row["embeddings"]),
                }
                for row in rows
            }
    finally:
        engine.dispose()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sample-files", type=Path, nargs="+", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest_rows = _read_jsonl(args.manifest)
    required_pairs = {
        (repo, revision.lower())
        for repo, revision in needed_snapshots(args.sample_files)
    }
    source_ids = [
        str(row["source_id"])
        for row in manifest_rows
        if isinstance(row.get("source_id"), str)
    ]
    database_rows = fetch_database_rows(args.database_url, source_ids)
    audit = build_index_audit(required_pairs, manifest_rows, database_rows)
    payload = {
        "schema": "native_delphi_index_audit_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus": {
            "sample_files": [str(path) for path in args.sample_files],
            "sample_sha256": {
                str(path): _sha256(path) for path in args.sample_files
            },
            "final_split_inspected": False,
        },
        "manifest": {
            "path": str(args.manifest),
            "sha256": _sha256(args.manifest),
        },
        "audit": audit,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), **audit}, sort_keys=True))
    if not audit["complete"]:
        raise SystemExit("Delphi index audit failed")


if __name__ == "__main__":
    main()
