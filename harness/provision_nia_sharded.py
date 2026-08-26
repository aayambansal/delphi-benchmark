"""Provision ARB round-3 snapshots as sharded Nia local-folder sources.

The round-2 evaluation demonstrated that whole-snapshot Nia sources stall in
`syncing` for large repositories while sharded sources (one bounded batch per
source, polled to terminal individually) reliably reach `indexed`. This
provisioner applies that strategy to the round-3 corpus under the same
`/arb-v2-sharded/<repo>/<commit>/shard-NNNN-of-MMMM` path scheme so pairs
already indexed by round 2 are reused verbatim.

Atlas plan: wide-root-1378 (hypothesis thin-helm-2134).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from harness.gitcorpus import GitCorpus, needed_snapshots  # noqa: E402

NIA_URL = "https://apigcp.trynia.ai/v2"
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".whl", ".jar", ".class", ".so", ".dylib", ".dll", ".exe", ".bin",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".webm", ".ogg",
    ".pyc", ".wasm", ".onnx", ".pt", ".pack", ".idx", ".parquet", ".npy",
    ".npz", ".h5", ".bmp", ".tiff", ".webp", ".svgz", ".jks", ".keystore",
}
MAX_FILE_BYTES = 900_000
MAX_SHARD_FILES = 100
MAX_SHARD_BYTES = 1_500_000
SHARD_RE = re.compile(r"^shard-(\d{4})-of-(\d{4})$")
TERMINAL_OK = {"indexed", "completed"}
TERMINAL_BAD = {"failed", "error", "cancelled"}


def request(http: httpx.Client, method: str, url: str, **kw) -> httpx.Response:
    for attempt in range(5):
        try:
            resp = http.request(method, url, **kw)
        except httpx.RequestError:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in {429, 500, 502, 503, 504} and attempt < 4:
            retry_after = resp.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after else 2 ** attempt)
            continue
        return resp
    return resp


def snapshot_files(corpus: GitCorpus, repo: str, commit: str) -> list[dict]:
    items = []
    for path in corpus.list_files(repo, commit):
        if Path(path).suffix.lower() in BINARY_EXT:
            continue
        text = corpus.file_text(repo, commit, path)
        if text is None or "\x00" in text[:8192]:
            continue
        if len(text.encode("utf-8", "ignore")) > MAX_FILE_BYTES:
            text = text[: MAX_FILE_BYTES // 2]
        items.append(
            {"path": path, "content": text, "change_type": "added", "metadata": {}}
        )
    return items


def shards(items: list[dict]):
    shard, size = [], 0
    for item in items:
        item_size = len(item["path"].encode()) + len(
            item["content"].encode("utf-8", "ignore")
        )
        if shard and (
            len(shard) >= MAX_SHARD_FILES or size + item_size > MAX_SHARD_BYTES
        ):
            yield shard
            shard, size = [], 0
        shard.append(item)
        size += item_size
    if shard:
        yield shard


def existing_complete_shards(
    inventory: dict[str, dict],
    namespace: str,
    repo: str,
    commit: str,
) -> list[str] | None:
    """Return ordered shard source ids when a complete indexed set exists."""
    prefix = f"/{namespace}/{repo}/{commit}/"
    found: dict[int, tuple[int, str, str]] = {}
    for path, row in inventory.items():
        if not path.startswith(prefix):
            continue
        match = SHARD_RE.match(path[len(prefix):])
        if not match:
            continue
        index, total = int(match.group(1)), int(match.group(2))
        found[index] = (total, str(row["local_folder_id"]), str(row.get("status") or ""))
    if not found:
        return None
    totals = {total for total, _, _ in found.values()}
    if len(totals) != 1:
        return None
    total = totals.pop()
    if sorted(found) != list(range(1, total + 1)):
        return None
    if not all(status.lower() in TERMINAL_OK for _, _, status in found.values()):
        return None
    return [found[index][1] for index in range(1, total + 1)]


def poll_source(
    http: httpx.Client,
    headers: dict,
    source_id: str,
    deadline_s: float,
) -> str:
    deadline = time.monotonic() + deadline_s
    while True:
        resp = request(
            http,
            "GET",
            f"{NIA_URL}/sources/{source_id}",
            headers=headers,
            params={"type": "local_folder"},
        )
        resp.raise_for_status()
        status = str(resp.json().get("status") or "processing").lower()
        if status in TERMINAL_OK:
            return "indexed"
        if status in TERMINAL_BAD:
            return "failed"
        if time.monotonic() >= deadline:
            raise TimeoutError(f"shard {source_id} still {status} at deadline")
        time.sleep(5)


def provision_pair(
    http: httpx.Client,
    headers: dict,
    corpus: GitCorpus,
    inventory: dict[str, dict],
    namespace: str,
    repo: str,
    commit: str,
    poll_deadline_s: float,
) -> dict:
    started = time.time()
    existing = existing_complete_shards(inventory, namespace, repo, commit)
    if existing is not None:
        return {
            "repo": repo,
            "revision": commit,
            "source_ids": existing,
            "shard_count": len(existing),
            "status": "indexed",
            "provenance": "existing",
            "elapsed_s": round(time.time() - started, 1),
        }
    try:
        items = snapshot_files(corpus, repo, commit)
        all_shards = list(shards(items))
        source_ids: list[str] = []
        for shard_index, shard in enumerate(all_shards, start=1):
            identifier = (
                f"/{namespace}/{repo}/{commit}/"
                f"shard-{shard_index:04d}-of-{len(all_shards):04d}"
            )
            source_row = inventory.get(identifier)
            source_id = (
                str(source_row["local_folder_id"]) if source_row else None
            )
            if source_id is None:
                resp = request(
                    http,
                    "POST",
                    f"{NIA_URL}/daemon/sources",
                    headers=headers,
                    json={
                        "path": identifier,
                        "display_name": (
                            f"ARB3 {repo}@{commit[:10]} "
                            f"[{shard_index}/{len(all_shards)}]"
                        ),
                        "detected_type": "repository",
                    },
                )
                resp.raise_for_status()
                source_id = str(resp.json()["local_folder_id"])
            already_indexed = bool(
                source_row
                and str(source_row.get("status") or "").lower() in TERMINAL_OK
            )
            if not already_indexed:
                paths = ",".join(str(item["path"]) for item in shard)
                digest = hashlib.sha256(
                    (
                        f"{repo}:{commit}:shard:{shard_index}:"
                        f"{len(all_shards)}:{paths}"
                    ).encode()
                ).hexdigest()
                resp = request(
                    http,
                    "POST",
                    f"{NIA_URL}/daemon/sync",
                    headers=headers,
                    json={
                        "local_folder_id": source_id,
                        "files": shard,
                        "cursor": {
                            "shard": shard_index,
                            "total_shards": len(all_shards),
                        },
                        "stats": {
                            "files_in_shard": len(shard),
                            "total_shards": len(all_shards),
                        },
                        "is_final_batch": True,
                        "idempotency_key": f"arb3r-shard-{digest}",
                        "connector_type": "repository",
                    },
                )
                resp.raise_for_status()
                outcome = poll_source(http, headers, source_id, poll_deadline_s)
                if outcome != "indexed":
                    raise RuntimeError(
                        f"shard {shard_index}/{len(all_shards)} failed"
                    )
            source_ids.append(source_id)
            print(
                json.dumps(
                    {
                        "repo": repo,
                        "revision": commit,
                        "shard": shard_index,
                        "total_shards": len(all_shards),
                        "status": "indexed",
                    }
                ),
                flush=True,
            )
        return {
            "repo": repo,
            "revision": commit,
            "source_ids": source_ids,
            "shard_count": len(source_ids),
            "files": len(items),
            "content_bytes": sum(
                len(item["content"].encode("utf-8", "ignore")) for item in items
            ),
            "status": "indexed",
            "provenance": "fresh",
            "elapsed_s": round(time.time() - started, 1),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "repo": repo,
            "revision": commit,
            "source_ids": None,
            "status": "failed",
            "provenance": "fresh",
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "elapsed_s": round(time.time() - started, 1),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="development")
    parser.add_argument(
        "--workflows",
        default="v2_code2test,v2_comment2context,v2_trace2code,v2_edit2ripple",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "results" / "nia-sharded-sources.jsonl",
    )
    parser.add_argument("--namespace", default="arb-v2-sharded")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-deadline", type=float, default=2400.0)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="provision only the smallest missing pair, then exit",
    )
    parser.add_argument("--max-pairs", type=int, default=0)
    args = parser.parse_args()

    headers = {
        "Authorization": f"Bearer {os.environ['NIA_API_KEY']}",
        "Content-Type": "application/json",
    }
    http = httpx.Client(timeout=httpx.Timeout(90.0, connect=20.0))
    corpus = GitCorpus()

    sample_paths = [
        ROOT / "samples" / args.split / f"{wf}.jsonl"
        for wf in args.workflows.split(",")
    ]
    pairs = needed_snapshots(sample_paths)

    resp = request(http, "GET", f"{NIA_URL}/daemon/sources", headers=headers)
    resp.raise_for_status()
    inventory = {
        str(item.get("path")): item
        for item in resp.json()
        if item.get("path") and item.get("local_folder_id")
    }

    done: dict[tuple[str, str], dict] = {}
    if args.manifest.exists():
        for line in args.manifest.open():
            row = json.loads(line)
            if row.get("status") == "indexed":
                done[(row["repo"], row["revision"])] = row

    complete_existing = []
    pending = []
    for repo, commit in pairs:
        if (repo, commit) in done:
            continue
        if existing_complete_shards(inventory, args.namespace, repo, commit):
            complete_existing.append((repo, commit))
        else:
            pending.append((repo, commit))

    print(
        f"{len(pairs)} pairs needed | {len(done)} in manifest | "
        f"{len(complete_existing)} complete on account | {len(pending)} to ingest",
        flush=True,
    )

    if args.smoke and pending:
        pending.sort(key=lambda pair: len(corpus.list_files(*pair)))
        pending = pending[:1]
        print(f"smoke pair: {pending[0][0]}@{pending[0][1][:12]}", flush=True)
    elif args.max_pairs:
        pending = pending[: args.max_pairs]

    work = (
        [] if args.smoke else [(repo, commit) for repo, commit in complete_existing]
    ) + pending
    if args.smoke:
        work = pending

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    ready = len(done)
    with args.manifest.open("a") as manifest, ThreadPoolExecutor(
        max_workers=args.workers
    ) as pool:
        futures = {
            pool.submit(
                provision_pair,
                http,
                headers,
                corpus,
                inventory,
                args.namespace,
                repo,
                commit,
                args.poll_deadline,
            ): (repo, commit)
            for repo, commit in work
        }
        for future in as_completed(futures):
            row = future.result()
            manifest.write(json.dumps(row, sort_keys=True) + "\n")
            manifest.flush()
            if row.get("status") == "indexed":
                ready += 1
            print(json.dumps(row), flush=True)

    print(
        json.dumps(
            {
                "ready_pair_count": ready,
                "required_pair_count": len(pairs),
                "smoke": args.smoke,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
