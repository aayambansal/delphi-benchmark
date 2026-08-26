from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol

from harness.provision_sources import (
    ProvisionRecord,
    read_jsonl,
    write_manifest,
)


class LocalProvisioner(Protocol):
    def index(
        self,
        *,
        repo: str,
        revision: str,
        snapshot_path: Path,
    ) -> ProvisionRecord: ...


def provision_manifest(
    *,
    manifest: Path,
    output: Path,
    provisioner: LocalProvisioner,
    workers: int,
) -> list[ProvisionRecord]:
    if workers < 1:
        raise ValueError("workers must be positive")
    rows = read_jsonl(manifest)
    existing_rows = read_jsonl(output) if output.exists() else []
    records: dict[tuple[str, str], ProvisionRecord] = {}
    for row in existing_rows:
        if row.get("status") not in {"indexed", "reused"}:
            continue
        repo = str(row["repo"])
        revision = str(row["revision"])
        source_id = row.get("source_id")
        records[(repo, revision)] = ProvisionRecord(
            engine=str(row.get("engine") or "delphi_local"),
            repo=repo,
            revision=revision,
            source_id=str(source_id) if source_id is not None else None,
            status=str(row["status"]),
            error=str(row["error"]) if row.get("error") else None,
            metadata=(
                row["metadata"]
                if isinstance(row.get("metadata"), dict)
                else {}
            ),
        )

    pending = [
        row
        for row in rows
        if (str(row["repo"]), str(row["revision"])) not in records
    ]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                provisioner.index,
                repo=str(row["repo"]),
                revision=str(row["revision"]),
                snapshot_path=Path(str(row["path"])),
            ): row
            for row in pending
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            row = futures[future]
            repo = str(row["repo"])
            revision = str(row["revision"])
            try:
                record = future.result()
            except Exception as exc:
                record = ProvisionRecord(
                    "delphi_local",
                    repo,
                    revision,
                    None,
                    "failed",
                    type(exc).__name__,
                )
            records[(repo, revision)] = record
            write_manifest(output, records.values())
            print(
                json.dumps(
                    {
                        "completed": completed,
                        "pending_total": len(pending),
                        "repo": repo,
                        "revision": revision,
                        "source_id": record.source_id,
                        "status": record.status,
                        "error": record.error,
                        "files_indexed": record.metadata.get("files_indexed"),
                        "chunks_created": record.metadata.get("chunks_created"),
                        "indexing_time_ms": record.metadata.get(
                            "indexing_time_ms"
                        ),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    write_manifest(output, records.values())
    return sorted(records.values(), key=lambda item: (item.repo, item.revision))


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-root", type=Path, required=True)
    parser.add_argument(
        "--container-root",
        type=Path,
        default=Path("/bench/arb-v2-corpus"),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:20742",
    )
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    from harness.corpus_sources import DelphiLocalProvisioner

    provisioner = DelphiLocalProvisioner(
        args.base_url,
        required_env("SYSTEM_PASSWORD"),
        host_root=args.host_root,
        container_root=args.container_root,
    )
    records = provision_manifest(
        manifest=args.manifest,
        output=args.output,
        provisioner=provisioner,
        workers=args.workers,
    )
    failures = sum(record.status == "failed" for record in records)
    print(
        json.dumps(
            {
                "total": len(records),
                "indexed": sum(
                    record.status in {"indexed", "reused"}
                    for record in records
                ),
                "failed": failures,
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
