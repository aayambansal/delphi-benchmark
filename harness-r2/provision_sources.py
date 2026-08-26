from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import httpx


@dataclass(frozen=True)
class ProvisionRecord:
    engine: str
    repo: str
    revision: str
    source_id: str | None
    status: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def positive_source_pairs(paths: Iterable[Path]) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for path in paths:
        for row in read_jsonl(path):
            if (row.get("gold") or {}).get("no_gold") is True:
                continue
            pairs.append((str(row["repo"]), str(row["base_commit"])))
    return tuple(dict.fromkeys(pairs))


def write_manifest(path: Path, records: Iterable[ProvisionRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for record in sorted(records, key=lambda item: (item.repo, item.revision)):
            stream.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    temporary.replace(path)


class DelphiProvisioner:
    engine = "delphi"

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        self.client = httpx.Client(timeout=httpx.Timeout(1_800.0))

    def inventory(self) -> dict[tuple[str, str], str]:
        response = self.client.get(
            f"{self.base_url}/v1/repositories",
            headers=self.headers,
        )
        response.raise_for_status()
        result: dict[tuple[str, str], str] = {}
        for row in response.json().get("repositories") or []:
            repo = f"{row.get('owner')}/{row.get('name')}"
            revision = str(row.get("commit_sha") or row.get("branch") or "")
            source_id = row.get("repo_id")
            if repo and revision and isinstance(source_id, str):
                result[(repo, revision.lower())] = source_id
        return result

    def index(self, repo: str, revision: str) -> ProvisionRecord:
        try:
            response = self.client.post(
                f"{self.base_url}/v1/repositories/index",
                headers=self.headers,
                json={
                    "url": repo,
                    "branch": revision,
                    "quality_mode": "agent",
                    "include_tests": True,
                    "include_docs": True,
                    "include_examples": True,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return ProvisionRecord(
                self.engine, repo, revision, None, "failed", type(exc).__name__
            )
        source_id = payload.get("repo_id")
        returned = str(payload.get("commit_sha") or "")
        if (
            not payload.get("success")
            or not isinstance(source_id, str)
            or returned.lower() != revision.lower()
        ):
            return ProvisionRecord(
                self.engine,
                repo,
                revision,
                source_id if isinstance(source_id, str) else None,
                "failed",
                (
                    "revision_mismatch"
                    if returned and returned.lower() != revision.lower()
                    else str(payload.get("error") or "indexing_failed")
                ),
                payload,
            )
        return ProvisionRecord(
            self.engine, repo, revision, source_id, "indexed", metadata=payload
        )


class NiaProvisioner:
    engine = "nia"
    terminal = {"indexed", "failed", "error", "cancelled"}

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        poll_interval_s: float = 5.0,
        timeout_s: float = 3_600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.client = httpx.Client(timeout=httpx.Timeout(180.0))
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    def inventory(self) -> dict[tuple[str, str], str]:
        result: dict[tuple[str, str], str] = {}
        page = 1
        while True:
            response = self.client.get(
                f"{self.base_url}/sources",
                headers=self.headers,
                params={"page": page, "limit": 100},
            )
            response.raise_for_status()
            payload = response.json()
            for row in payload.get("items") or []:
                metadata = row.get("metadata") or {}
                repo = str(metadata.get("repository") or "")
                revision = str(metadata.get("branch") or "")
                source_id = row.get("id")
                if (
                    row.get("status") == "indexed"
                    and repo
                    and revision
                    and isinstance(source_id, str)
                ):
                    result[(repo, revision.lower())] = source_id
            if not (payload.get("pagination") or {}).get("has_next"):
                break
            page += 1
        return result

    def index(self, repo: str, revision: str) -> ProvisionRecord:
        try:
            response = self.client.post(
                f"{self.base_url}/sources",
                headers=self.headers,
                json={
                    "type": "repository",
                    "repository": repo,
                    "ref": revision,
                    "add_as_global_source": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return ProvisionRecord(
                self.engine, repo, revision, None, "failed", type(exc).__name__
            )
        source_id = payload.get("id") or payload.get("source_id")
        if not isinstance(source_id, str):
            return ProvisionRecord(
                self.engine,
                repo,
                revision,
                None,
                "failed",
                str(payload.get("detail") or payload.get("error") or "missing_id"),
                payload,
            )
        deadline = time.monotonic() + self.timeout_s
        status = str(payload.get("status") or "processing").lower()
        consecutive_poll_errors = 0
        while status not in self.terminal and time.monotonic() < deadline:
            time.sleep(self.poll_interval_s)
            try:
                response = self.client.get(
                    f"{self.base_url}/sources/{source_id}",
                    headers=self.headers,
                )
                response.raise_for_status()
                payload = response.json()
            except httpx.RequestError as exc:
                consecutive_poll_errors += 1
                if consecutive_poll_errors < 4:
                    continue
                return ProvisionRecord(
                    self.engine,
                    repo,
                    revision,
                    source_id,
                    "failed",
                    type(exc).__name__,
                )
            except (httpx.HTTPStatusError, ValueError) as exc:
                return ProvisionRecord(
                    self.engine,
                    repo,
                    revision,
                    source_id,
                    "failed",
                    type(exc).__name__,
                )
            consecutive_poll_errors = 0
            status = str(payload.get("status") or "processing").lower()
        metadata = payload.get("metadata") or {}
        error = metadata.get("error") or payload.get("error") or payload.get("detail")
        return ProvisionRecord(
            self.engine,
            repo,
            revision,
            source_id,
            "indexed" if status == "indexed" else "failed",
            str(error) if error else ("indexing_timeout" if status not in self.terminal else None),
            {**payload, **metadata},
        )


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("delphi", "nia"), required=True)
    parser.add_argument("--samples", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--base-url")
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be positive")

    pairs = positive_source_pairs(args.samples)
    if args.engine == "delphi":
        provisioner: DelphiProvisioner | NiaProvisioner = DelphiProvisioner(
            args.base_url or "http://127.0.0.1:18742",
            required_env("SYSTEM_PASSWORD"),
        )
    else:
        provisioner = NiaProvisioner(
            args.base_url or "https://apigcp.trynia.ai/v2",
            required_env("NIA_API_KEY"),
        )
    inventory = provisioner.inventory()
    records: dict[tuple[str, str], ProvisionRecord] = {}
    for repo, revision in pairs:
        source_id = inventory.get((repo, revision.lower()))
        if source_id:
            records[(repo, revision)] = ProvisionRecord(
                args.engine, repo, revision, source_id, "reused"
            )
    pending = [pair for pair in pairs if pair not in records]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(provisioner.index, repo, revision): (repo, revision)
            for repo, revision in pending
        }
        for future in as_completed(futures):
            record = future.result()
            records[(record.repo, record.revision)] = record
            write_manifest(args.output, records.values())
            print(
                json.dumps(
                    {
                        "engine": record.engine,
                        "repo": record.repo,
                        "revision": record.revision,
                        "source_id": record.source_id,
                        "status": record.status,
                        "error": record.error,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    write_manifest(args.output, records.values())
    failed = sum(record.status == "failed" for record in records.values())
    print(
        json.dumps(
            {
                "engine": args.engine,
                "total": len(records),
                "reused": sum(record.status == "reused" for record in records.values()),
                "indexed": sum(record.status == "indexed" for record in records.values()),
                "failed": failed,
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
