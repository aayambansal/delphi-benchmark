"""Provision ARB snapshots as Nia local-folder sources (round 3).

For each (repo, base_commit) needed by the requested split, push the snapshot
file-by-file through Nia's daemon sync API and poll until indexed. Existing
sources with the same identifier path are reused. Results are appended to a
manifest jsonl usable by run_arb.py --sources.
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
MAX_BATCH_FILES = 40
MAX_BATCH_BYTES = 600_000
NAMESPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


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
            text = text[:MAX_FILE_BYTES // 2]
        items.append({"path": path, "content": text, "change_type": "added", "metadata": {}})
    return items


def batches(items: list[dict]):
    batch, size = [], 0
    for item in items:
        item_size = len(item["path"].encode()) + len(item["content"].encode("utf-8", "ignore"))
        if batch and (len(batch) >= MAX_BATCH_FILES or size + item_size > MAX_BATCH_BYTES):
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += item_size
    if batch:
        yield batch


def source_identifier(namespace: str, repo: str, commit: str) -> str:
    if NAMESPACE_RE.fullmatch(namespace) is None:
        raise ValueError(f"unsafe Nia source namespace: {namespace!r}")
    return f"/{namespace}/{repo}/{commit}"


def source_status_outcome(status: str) -> str | None:
    normalized = status.strip().lower()
    if normalized in {"indexed", "completed"}:
        return "indexed"
    if normalized in {"failed", "error", "cancelled"}:
        return "failed"
    return None


def provision_one(http: httpx.Client, headers: dict, corpus: GitCorpus,
                  repo: str, commit: str, existing: dict[str, str],
                  namespace: str) -> dict:
    identifier = source_identifier(namespace, repo, commit)
    started = time.time()
    try:
        source_id = existing.get(identifier)
        if source_id is None:
            resp = request(http, "POST", f"{NIA_URL}/daemon/sources", headers=headers,
                           json={"path": identifier, "display_name": f"ARB3 {repo}@{commit[:10]}",
                                 "detected_type": "repository"})
            resp.raise_for_status()
            source_id = resp.json()["local_folder_id"]
        items = snapshot_files(corpus, repo, commit)
        all_batches = list(batches(items))
        for bi, batch in enumerate(all_batches):
            digest = hashlib.sha256(
                f"{repo}:{commit}:{bi}:{','.join(i['path'] for i in batch)}".encode()
            ).hexdigest()
            resp = request(http, "POST", f"{NIA_URL}/daemon/sync", headers=headers,
                           json={"local_folder_id": source_id, "files": batch,
                                 "cursor": {"batch": bi + 1},
                                 "stats": {"files_in_batch": len(batch),
                                           "total_batches": len(all_batches)},
                                 "is_final_batch": bi + 1 == len(all_batches),
                                 "idempotency_key": f"arb3-{digest}",
                                 "connector_type": "repository"})
            resp.raise_for_status()
        deadline = time.time() + 2400
        status = "processing"
        outcome = source_status_outcome(status)
        while outcome is None:
            if time.time() > deadline:
                raise TimeoutError("nia indexing timeout")
            resp = request(http, "GET", f"{NIA_URL}/sources/{source_id}", headers=headers,
                           params={"type": "local_folder"})
            resp.raise_for_status()
            status = str(resp.json().get("status") or "processing").lower()
            outcome = source_status_outcome(status)
            if outcome is None:
                time.sleep(5)
        return {"repo": repo, "revision": commit, "source_id": source_id,
                "status": outcome,
                "files": len(items), "elapsed_s": round(time.time() - started, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"repo": repo, "revision": commit, "source_id": None,
                "status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="development")
    parser.add_argument("--workflows",
                        default="v2_code2test,v2_comment2context,v2_trace2code,v2_edit2ripple")
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "results" / "nia-sources.jsonl")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-snapshots", type=int, default=0)
    parser.add_argument(
        "--namespace",
        default="arb3",
        help="account-specific source path prefix; use a new value across Nia accounts",
    )
    args = parser.parse_args()
    source_identifier(args.namespace, "validation/repo", "validation-commit")

    headers = {"Authorization": f"Bearer {os.environ['NIA_API_KEY']}",
               "Content-Type": "application/json"}
    http = httpx.Client(timeout=httpx.Timeout(90.0, connect=20.0))
    corpus = GitCorpus()

    sample_paths = [ROOT / "samples" / args.split / f"{wf}.jsonl"
                    for wf in args.workflows.split(",")]
    pairs = needed_snapshots(sample_paths)
    done: dict[tuple[str, str], dict] = {}
    if args.manifest.exists():
        for line in args.manifest.open():
            row = json.loads(line)
            if row.get("status") == "indexed":
                done[(row["repo"], row["revision"])] = row
    pending = [(r, c) for r, c in pairs if (r, c) not in done]
    if args.max_snapshots:
        pending = pending[: args.max_snapshots]
    print(f"{len(pairs)} snapshots needed, {len(done)} done, {len(pending)} pending", flush=True)

    resp = request(http, "GET", f"{NIA_URL}/daemon/sources", headers=headers)
    resp.raise_for_status()
    existing = {str(item.get("path")): str(item["local_folder_id"]) for item in resp.json()}

    with args.manifest.open("a") as manifest, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                provision_one, http, headers, corpus, repo, commit, existing, args.namespace
            ): (repo, commit)
                   for repo, commit in pending}
        for future in as_completed(futures):
            row = future.result()
            manifest.write(json.dumps(row, sort_keys=True) + "\n")
            manifest.flush()
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
