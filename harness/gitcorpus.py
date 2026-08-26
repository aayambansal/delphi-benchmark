"""Canonical corpus backed by bare git clones and materialized snapshots.

File contents are read from an immutable materialized snapshot when available
and fall back to `git show <sha>:<path>` against a bare clone. Working trees
can be materialized on demand via `git archive`.
"""
from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BARE = ROOT / "corpus" / "bare"
SNAPSHOTS = ROOT / "corpus" / "snapshots"


def bare_path(repo: str, *, root: Path = BARE) -> Path:
    return root / (repo.replace("/", "__") + ".git")


def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kw)


def clone_repo(repo: str) -> dict:
    dest = bare_path(repo)
    if dest.exists():
        return {"repo": repo, "status": "exists"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = _run([
        "git", "clone", "--bare", f"https://github.com/{repo}.git", str(dest),
    ])
    return {
        "repo": repo,
        "status": "cloned" if proc.returncode == 0 else "error",
        "error": proc.stderr[-400:] if proc.returncode != 0 else None,
    }


def has_commit(repo: str, sha: str) -> bool:
    proc = _run(["git", "-C", str(bare_path(repo)), "cat-file", "-e", f"{sha}^{{commit}}"])
    return proc.returncode == 0


def fetch_commit(repo: str, sha: str) -> bool:
    proc = _run(["git", "-C", str(bare_path(repo)), "fetch", "origin", sha])
    return proc.returncode == 0 and has_commit(repo, sha)


class GitCorpus:
    """ARB CorpusFileCache-compatible snapshot and bare-git reader."""

    def __init__(
        self,
        *,
        bare_root: Path = BARE,
        snapshot_root: Path | None = SNAPSHOTS,
    ) -> None:
        self.bare_root = bare_root
        self.snapshot_root = snapshot_root
        self._text_cache: dict[tuple[str, str, str], str | None] = {}
        self._lock = __import__("threading").Lock()

    def list_files(self, repo: str, commit: str) -> list[str]:
        return _ls_tree(repo, commit, self.bare_root)

    def file_text(self, repo: str, base_commit: str, path: str) -> str | None:
        key = (repo, base_commit, path)
        with self._lock:
            if key in self._text_cache:
                return self._text_cache[key]
        blob: bytes | None = None
        if self.snapshot_root is not None:
            snapshot_file = (
                self.snapshot_root
                / repo.replace("/", "__")
                / base_commit
                / path
            )
            if snapshot_file.is_file():
                blob = snapshot_file.read_bytes()
        if blob is None:
            proc = subprocess.run(
                [
                    "git",
                    "-C",
                    str(bare_path(repo, root=self.bare_root)),
                    "show",
                    f"{base_commit}:{path}",
                ],
                capture_output=True,
            )
            if proc.returncode == 0:
                blob = proc.stdout
        value: str | None = None
        if blob is not None:
            if b"\x00" not in blob[:8192]:
                try:
                    value = blob.decode("utf-8")
                except UnicodeDecodeError:
                    value = None
        with self._lock:
            if len(self._text_cache) > 4096:
                self._text_cache.clear()
            self._text_cache[key] = value
        return value


@lru_cache(maxsize=512)
def _ls_tree(
    repo: str,
    commit: str,
    bare_root: Path = BARE,
) -> list[str]:
    proc = _run(
        [
            "git",
            "-C",
            str(bare_path(repo, root=bare_root)),
            "ls-tree",
            "-r",
            "--name-only",
            commit,
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ls-tree failed for {repo}@{commit}: {proc.stderr[:200]}")
    return [line for line in proc.stdout.splitlines() if line]


def materialize_snapshot(
    repo: str,
    commit: str,
    *,
    bare_root: Path = BARE,
    snapshot_root: Path = SNAPSHOTS,
) -> Path:
    dest = snapshot_root / repo.replace("/", "__") / commit
    if dest.exists() and any(dest.iterdir()):
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.Popen(
        [
            "git",
            "-C",
            str(bare_path(repo, root=bare_root)),
            "archive",
            commit,
        ],
        stdout=subprocess.PIPE,
    )
    extract = subprocess.run(
        ["tar", "-x", "-C", str(dest)], stdin=archive.stdout, capture_output=True
    )
    archive.wait()
    if archive.returncode != 0 or extract.returncode != 0:
        raise RuntimeError(f"archive failed for {repo}@{commit}")
    return dest


def needed_snapshots(sample_paths: list[Path]) -> list[tuple[str, str]]:
    pairs: dict[tuple[str, str], None] = {}
    for path in sample_paths:
        for line in path.open():
            if not line.strip():
                continue
            row = json.loads(line)
            pairs[(str(row["repo"]), str(row["base_commit"]))] = None
    return list(pairs)


if __name__ == "__main__":
    import sys
    from concurrent.futures import ThreadPoolExecutor

    samples = sorted((ROOT.parent / "delphi-evaluation-2026-07-29-round2" / "arb-data" / "benchmark").glob("*/samples.jsonl"))
    pairs = needed_snapshots(samples)
    repos = sorted({repo for repo, _ in pairs})
    print(f"{len(repos)} repos, {len(pairs)} snapshots", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(clone_repo, repos):
            print(json.dumps(result), flush=True)
    missing = []
    for repo, sha in pairs:
        if not has_commit(repo, sha):
            ok = fetch_commit(repo, sha)
            if not ok:
                missing.append((repo, sha))
                print(json.dumps({"repo": repo, "sha": sha, "status": "missing"}), flush=True)
    print(json.dumps({"repos": len(repos), "snapshots": len(pairs), "missing": len(missing)}), flush=True)
    if missing:
        sys.exit(1)
