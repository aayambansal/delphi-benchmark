from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import httpx

from harness.provider_clients import RetryingHTTPClient
from harness.provision_sources import ProvisionRecord


@dataclass(frozen=True)
class SnapshotRecord:
    repo: str
    revision: str
    path: str
    file_count: int
    content_bytes: int


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or ".." in path.parts:
        raise ValueError(f"unsafe corpus path: {value}")
    return path


def materialize_snapshot(
    *,
    chunks_path: Path,
    output: Path,
    repo: str,
    revision: str,
) -> SnapshotRecord:
    output.mkdir(parents=True, exist_ok=True)
    file_sizes: dict[PurePosixPath, int] = {}
    with chunks_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") != "file" or not row.get("path"):
                continue
            relative = _safe_relative_path(str(row["path"]))
            destination = output.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = str(row.get("text") or "")
            destination.write_text(content, encoding="utf-8")
            file_sizes[relative] = len(content.encode())
    return SnapshotRecord(
        repo=repo,
        revision=revision,
        path=str(output),
        file_count=len(file_sizes),
        content_bytes=sum(file_sizes.values()),
    )


def _file_items(snapshot_path: Path) -> Iterable[dict[str, Any]]:
    for path in sorted(item for item in snapshot_path.rglob("*") if item.is_file()):
        relative = path.relative_to(snapshot_path).as_posix()
        yield {
            "path": relative,
            "content": path.read_text(encoding="utf-8"),
            "change_type": "added",
            "metadata": {},
        }


def _bounded_batches(
    items: Iterable[dict[str, Any]],
    *,
    max_files: int,
    max_bytes: int,
) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    size = 0
    for item in items:
        item_size = len(str(item["path"]).encode()) + len(
            str(item["content"]).encode()
        )
        if item_size > max_bytes:
            raise ValueError(f"file exceeds Nia batch limit: {item['path']}")
        if batch and (len(batch) >= max_files or size + item_size > max_bytes):
            yield batch
            batch = []
            size = 0
        batch.append(item)
        size += item_size
    if batch:
        yield batch


class NiaDaemonProvisioner:
    engine = "nia_daemon"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        max_batch_files: int = 100,
        max_batch_bytes: int = 1_500_000,
        poll_interval_s: float = 5.0,
        timeout_s: float = 3_600.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.http = RetryingHTTPClient(
            client=client or httpx.Client(timeout=httpx.Timeout(180.0))
        )
        self.max_batch_files = max_batch_files
        self.max_batch_bytes = max_batch_bytes
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    def index(
        self,
        *,
        repo: str,
        revision: str,
        snapshot_path: Path,
    ) -> ProvisionRecord:
        identifier = f"/arb/{repo}/{revision}"
        try:
            response = self.http.request(
                "GET",
                f"{self.base_url}/daemon/sources",
                headers=self.headers,
            )
            response.raise_for_status()
            source_id = next(
                (
                    str(item["local_folder_id"])
                    for item in response.json()
                    if item.get("path") == identifier
                ),
                None,
            )
            if source_id is None:
                response = self.http.request(
                    "POST",
                    f"{self.base_url}/daemon/sources",
                    headers=self.headers,
                    json={
                        "path": identifier,
                        "display_name": f"ARB {repo}@{revision[:12]}",
                        "detected_type": "repository",
                    },
                )
                response.raise_for_status()
                source_payload = response.json()
                source_id = source_payload["local_folder_id"]
            batches = list(
                _bounded_batches(
                    _file_items(snapshot_path),
                    max_files=self.max_batch_files,
                    max_bytes=self.max_batch_bytes,
                )
            )
            for batch_index, batch in enumerate(batches):
                paths = ",".join(str(item["path"]) for item in batch)
                digest = hashlib.sha256(
                    f"{repo}:{revision}:{batch_index}:{paths}".encode()
                ).hexdigest()
                response = self.http.request(
                    "POST",
                    f"{self.base_url}/daemon/sync",
                    headers=self.headers,
                    json={
                        "local_folder_id": source_id,
                        "files": batch,
                        "cursor": {"batch": batch_index + 1},
                        "stats": {
                            "files_in_batch": len(batch),
                            "total_batches": len(batches),
                        },
                        "is_final_batch": batch_index + 1 == len(batches),
                        "idempotency_key": f"arb-v2-{digest}",
                        "connector_type": "repository",
                    },
                )
                response.raise_for_status()
            deadline = time.monotonic() + self.timeout_s
            payload: dict[str, Any] = {}
            status = "processing"
            while status not in {"indexed", "failed", "error", "cancelled"}:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Nia daemon indexing timed out")
                response = self.http.request(
                    "GET",
                    f"{self.base_url}/sources/{source_id}",
                    headers=self.headers,
                    params={"type": "local_folder"},
                )
                response.raise_for_status()
                payload = response.json()
                status = str(payload.get("status") or "processing").lower()
                if status not in {"indexed", "failed", "error", "cancelled"}:
                    time.sleep(self.poll_interval_s)
        except (httpx.HTTPError, ValueError, KeyError, TimeoutError) as exc:
            return ProvisionRecord(
                self.engine,
                repo,
                revision,
                locals().get("source_id"),
                "failed",
                type(exc).__name__,
            )
        error = (
            (payload.get("metadata") or {}).get("error")
            or payload.get("error")
            or payload.get("detail")
        )
        return ProvisionRecord(
            self.engine,
            repo,
            revision,
            source_id,
            "indexed" if status == "indexed" else "failed",
            str(error) if error else None,
            payload,
        )

    def index_sharded(
        self,
        *,
        repo: str,
        revision: str,
        snapshot_path: Path,
    ) -> ProvisionRecord:
        batches = list(
            _bounded_batches(
                _file_items(snapshot_path),
                max_files=self.max_batch_files,
                max_bytes=self.max_batch_bytes,
            )
        )
        source_ids: list[str] = []
        shard_payloads: list[dict[str, Any]] = []
        try:
            response = self.http.request(
                "GET",
                f"{self.base_url}/daemon/sources",
                headers=self.headers,
            )
            response.raise_for_status()
            inventory = {
                str(item.get("path")): str(item["local_folder_id"])
                for item in response.json()
                if item.get("path") and item.get("local_folder_id")
            }
            for batch_index, batch in enumerate(batches, start=1):
                identifier = (
                    f"/arb-v2-sharded/{repo}/{revision}/"
                    f"shard-{batch_index:04d}-of-{len(batches):04d}"
                )
                source_id = inventory.get(identifier)
                if source_id is None:
                    response = self.http.request(
                        "POST",
                        f"{self.base_url}/daemon/sources",
                        headers=self.headers,
                        json={
                            "path": identifier,
                            "display_name": (
                                f"ARB {repo}@{revision[:12]} "
                                f"[{batch_index}/{len(batches)}]"
                            ),
                            "detected_type": "repository",
                        },
                    )
                    response.raise_for_status()
                    source_id = str(response.json()["local_folder_id"])
                paths = ",".join(str(item["path"]) for item in batch)
                digest = hashlib.sha256(
                    (
                        f"{repo}:{revision}:shard:{batch_index}:"
                        f"{len(batches)}:{paths}"
                    ).encode()
                ).hexdigest()
                response = self.http.request(
                    "POST",
                    f"{self.base_url}/daemon/sync",
                    headers=self.headers,
                    json={
                        "local_folder_id": source_id,
                        "files": batch,
                        "cursor": {
                            "shard": batch_index,
                            "total_shards": len(batches),
                        },
                        "stats": {
                            "files_in_shard": len(batch),
                            "total_shards": len(batches),
                        },
                        "is_final_batch": True,
                        "idempotency_key": f"arb-v2-shard-{digest}",
                        "connector_type": "repository",
                    },
                )
                response.raise_for_status()
                deadline = time.monotonic() + self.timeout_s
                status = "processing"
                payload: dict[str, Any] = {}
                while status not in {
                    "indexed",
                    "failed",
                    "error",
                    "cancelled",
                }:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Nia daemon shard indexing timed out")
                    response = self.http.request(
                        "GET",
                        f"{self.base_url}/sources/{source_id}",
                        headers=self.headers,
                        params={"type": "local_folder"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    status = str(
                        payload.get("status") or "processing"
                    ).lower()
                    if status not in {
                        "indexed",
                        "failed",
                        "error",
                        "cancelled",
                    }:
                        time.sleep(self.poll_interval_s)
                if status != "indexed":
                    raise RuntimeError(f"Nia daemon shard status: {status}")
                source_ids.append(source_id)
                shard_payloads.append(payload)
        except (
            httpx.HTTPError,
            ValueError,
            KeyError,
            RuntimeError,
            TimeoutError,
        ) as exc:
            return ProvisionRecord(
                self.engine,
                repo,
                revision,
                source_ids[0] if source_ids else None,
                "failed",
                type(exc).__name__,
                {
                    "source_ids": source_ids,
                    "shards_indexed": len(source_ids),
                    "shards_total": len(batches),
                },
            )
        return ProvisionRecord(
            self.engine,
            repo,
            revision,
            source_ids[0] if source_ids else None,
            "indexed",
            metadata={
                "source_ids": source_ids,
                "shards_indexed": len(source_ids),
                "shards_total": len(batches),
                "files_submitted": sum(len(batch) for batch in batches),
                "shards": shard_payloads,
            },
        )


class DelphiLocalProvisioner:
    engine = "delphi_local"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        host_root: Path,
        container_root: Path,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        self.host_root = host_root.resolve()
        self.container_root = container_root
        self.http = RetryingHTTPClient(
            client=client or httpx.Client(timeout=httpx.Timeout(1_800.0))
        )

    def index(
        self,
        *,
        repo: str,
        revision: str,
        snapshot_path: Path,
    ) -> ProvisionRecord:
        try:
            relative = snapshot_path.resolve().relative_to(self.host_root)
            container_path = self.container_root.joinpath(*relative.parts)
            response = self.http.request(
                "POST",
                f"{self.base_url}/v1/repositories/index/local",
                headers=self.headers,
                json={
                    "path": container_path.as_posix(),
                    "name": f"ARB {repo}@{revision[:12]}",
                    "quality_mode": "agent",
                    "include_tests": True,
                    "include_docs": True,
                    "include_examples": True,
                },
            )
            response.raise_for_status()
            payload = response.json()
            source_id = payload.get("repo_id")
            if not payload.get("success") or not isinstance(source_id, str):
                raise ValueError(str(payload.get("error") or "indexing_failed"))
        except (httpx.HTTPError, ValueError) as exc:
            return ProvisionRecord(
                self.engine,
                repo,
                revision,
                locals().get("source_id"),
                "failed",
                type(exc).__name__,
                locals().get("payload", {}),
            )
        return ProvisionRecord(
            self.engine,
            repo,
            revision,
            source_id,
            "indexed",
            metadata=payload,
        )
