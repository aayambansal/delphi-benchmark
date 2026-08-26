"""Index ARB snapshots into a Delphi stack as local-folder sources.

Materializes each (repo, base_commit) working tree from the bare corpus
clones, then POSTs /v1/repositories/index/local against the target stack.
The container sees snapshots under /bench/corpus (read-only mount).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from harness.gitcorpus import (  # noqa: E402
    BARE,
    SNAPSHOTS,
    materialize_snapshot,
    needed_snapshots,
)

CONTAINER_ROOT = Path("/bench/corpus")


def is_valid_indexed_record(row: dict) -> bool:
    """Return whether a manifest row names a searchable completed source."""
    metadata = row.get("metadata")
    if row.get("status") != "indexed" or not isinstance(metadata, dict):
        return False
    files_indexed = metadata.get("files_indexed")
    chunks_created = metadata.get("chunks_created")
    return (
        type(files_indexed) is int
        and files_indexed > 0
        and type(chunks_created) is int
        and chunks_created > 0
    )


def provision_one(
    http: httpx.Client,
    base_url: str,
    api_key: str,
    repo: str,
    commit: str,
    *,
    bare_root: Path = BARE,
    snapshot_root: Path = SNAPSHOTS,
    container_root: Path = CONTAINER_ROOT,
    force_reindex: bool = False,
) -> dict:
    started = time.time()
    try:
        host_path = materialize_snapshot(
            repo,
            commit,
            bare_root=bare_root,
            snapshot_root=snapshot_root,
        )
        relative = host_path.relative_to(snapshot_root)
        container_path = container_root.joinpath(*relative.parts)
        payload = None
        source_id = None
        for repair_attempt in range(2):
            request_body = {
                "path": container_path.as_posix(),
                "name": f"ARB {repo}@{commit[:12]}",
                "quality_mode": "agent",
                "include_tests": True,
                "include_docs": True,
                "include_examples": True,
            }
            if force_reindex or repair_attempt:
                request_body["force_reindex"] = True
            for attempt in range(3):
                resp = http.post(
                    f"{base_url}/v1/repositories/index/local",
                    headers={"X-API-Key": api_key},
                    json=request_body,
                    timeout=3600,
                )
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(15 * (attempt + 1))
                    continue
                break
            resp.raise_for_status()
            payload = resp.json()
            source_id = payload.get("repo_id")
            if not payload.get("success") or not isinstance(source_id, str):
                raise ValueError(str(payload.get("error") or "indexing_failed")[:300])
            chunks_created = payload.get("chunks_created")
            files_indexed = payload.get("files_indexed")
            if (
                isinstance(chunks_created, int)
                and chunks_created > 0
                and isinstance(files_indexed, int)
                and files_indexed > 0
            ):
                break
            if repair_attempt:
                raise ValueError(
                    "indexing_returned_no_searchable_chunks_after_force_reindex"
                )
        assert payload is not None
        assert isinstance(source_id, str)
        return {
            "repo": repo,
            "revision": commit,
            "source_id": source_id,
            "status": "indexed",
            "metadata": {
                "chunks_created": payload.get("chunks_created"),
                "files_indexed": payload.get("files_indexed"),
            },
            "elapsed_s": round(time.time() - started, 1),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "repo": repo,
            "revision": commit,
            "source_id": None,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="development")
    parser.add_argument(
        "--workflows",
        default="v2_code2test,v2_comment2context,v2_trace2code,v2_edit2ripple",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:21742")
    parser.add_argument("--api-key", default="delphi-r3-admin")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--sample-files", type=Path, nargs="+")
    parser.add_argument("--bare-root", type=Path, default=BARE)
    parser.add_argument("--snapshot-root", type=Path, default=SNAPSHOTS)
    parser.add_argument("--container-root", type=Path, default=CONTAINER_ROOT)
    parser.add_argument("--force-reindex", action="store_true")
    args = parser.parse_args()

    sample_paths = args.sample_files or [
        ROOT / "samples" / args.split / f"{wf}.jsonl"
        for wf in args.workflows.split(",")
    ]
    pairs = needed_snapshots(sample_paths)
    done = set()
    if args.manifest.exists():
        for line in args.manifest.open():
            row = json.loads(line)
            if is_valid_indexed_record(row):
                done.add((row["repo"], row["revision"]))
    pending = [(r, c) for r, c in pairs if (r, c) not in done]
    print(
        f"{len(pairs)} snapshots, {len(done)} done, {len(pending)} pending", flush=True
    )

    http = httpx.Client(timeout=httpx.Timeout(3600.0))
    with (
        args.manifest.open("a") as manifest,
        ThreadPoolExecutor(max_workers=args.workers) as pool,
    ):
        futures = {
            pool.submit(
                provision_one,
                http,
                args.base_url,
                args.api_key,
                r,
                c,
                bare_root=args.bare_root,
                snapshot_root=args.snapshot_root,
                container_root=args.container_root,
                force_reindex=args.force_reindex,
            ): (r, c)
            for r, c in pending
        }
        for future in as_completed(futures):
            row = future.result()
            manifest.write(json.dumps(row, sort_keys=True) + "\n")
            manifest.flush()
            print(json.dumps(row), flush=True)
    print("provisioning complete", flush=True)


if __name__ == "__main__":
    main()
