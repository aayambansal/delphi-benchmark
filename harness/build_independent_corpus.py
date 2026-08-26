"""Build a repository-disjoint commit-to-files localization corpus.

The query is a commit message and the gold files are files modified by that
commit. Retrieval happens at the first parent, before the gold change exists.
Only already-existing, modified source files are eligible: added files cannot
be retrieved from the base snapshot and are rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".php",
    ".py",
    ".pyi",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}
NOISE_PARTS = {
    ".github",
    "benchmark",
    "benchmarks",
    "dist",
    "docs",
    "examples",
    "fixtures",
    "generated",
    "node_modules",
    "snapshot",
    "snapshots",
    "vendor",
}
LOW_VALUE_SUBJECT = re.compile(
    r"^(?:build|bump|chore|ci|docs?|format|lint|release|style|tests?)"
    r"(?:\([^)]*\))?[!: ]",
    re.IGNORECASE,
)
TRAILER = re.compile(
    r"^(?:change-id|co-authored-by|reviewed-by|signed-off-by):",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommitRecord:
    commit: str
    parent: str
    message: str
    changes: tuple[tuple[str, str], ...]


def _clean_message(message: str) -> str:
    lines = [
        line.rstrip()
        for line in message.replace("\r\n", "\n").splitlines()
        if not TRAILER.match(line.strip())
    ]
    cleaned = "\n".join(lines).strip()
    return cleaned[:4000].strip()


def _is_source_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    parts = {part.lower() for part in normalized.split("/")}
    return (
        bool(normalized)
        and not parts.intersection(NOISE_PARTS)
        and Path(normalized).suffix.lower() in CODE_SUFFIXES
    )


def _contains_path_leakage(message: str, paths: list[str]) -> bool:
    lowered = message.casefold()
    for path in paths:
        normalized = path.replace("\\", "/").casefold()
        basename = normalized.rsplit("/", 1)[-1]
        if normalized in lowered or basename in lowered:
            return True
    return False


def build_sample(repo: str, record: CommitRecord) -> dict[str, Any] | None:
    """Convert one commit into a leak-checked pre-change retrieval sample."""
    message = _clean_message(record.message)
    subject = message.splitlines()[0] if message else ""
    if (
        len(subject) < 24
        or LOW_VALUE_SUBJECT.match(subject)
        or not record.parent
    ):
        return None

    if not 1 <= len(record.changes) <= 5:
        return None
    if any(status != "M" for status, _path in record.changes):
        return None
    paths = [path for _status, path in record.changes]
    if len(set(paths)) != len(paths) or not all(
        _is_source_path(path) for path in paths
    ):
        return None
    if _contains_path_leakage(message, paths):
        return None

    sample_id = hashlib.sha256(
        f"independent-v1\0{repo}\0{record.commit}".encode()
    ).hexdigest()[:24]
    return {
        "id": sample_id,
        "task_type": "commit2files",
        "repo": repo,
        "base_commit": record.parent,
        "query": {"intent": message},
        "gold": {
            "fix_commit": record.commit,
            "root_cause_files": paths,
            "related_tests": [],
            "supporting_files": [],
        },
        "metadata": {
            "source": "first-parent non-merge commit",
            "selection_version": "independent-v1",
        },
    }


def choose_records(
    repo: str,
    records: list[CommitRecord],
    *,
    limit: int,
) -> list[CommitRecord]:
    """Choose a stable, message-distinct subset independent of log order."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    by_message: dict[str, CommitRecord] = {}
    for record in records:
        if build_sample(repo, record) is None:
            continue
        key = _clean_message(record.message).casefold()
        incumbent = by_message.get(key)
        if incumbent is None or record.commit < incumbent.commit:
            by_message[key] = record
    eligible = sorted(
        by_message.values(),
        key=lambda record: (
            hashlib.sha256(
                f"{repo}\0{record.commit}".encode()
            ).hexdigest(),
            record.commit,
        ),
    )
    return eligible[:limit]


def _run_git(git_dir: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(git_dir), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _bare_path(root: Path, repo: str) -> Path:
    return root / f"{repo.replace('/', '__')}.git"


def _ensure_clone(root: Path, repo: str) -> Path:
    destination = _bare_path(root, repo)
    if not destination.exists():
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--bare",
                "--filter=blob:none",
                "--single-branch",
                f"https://github.com/{repo}.git",
                str(destination),
            ],
            check=True,
        )
    else:
        _run_git(destination, "fetch", "--prune", "origin")
    return destination


def _log_records(git_dir: Path, *, history_limit: int) -> list[CommitRecord]:
    raw = _run_git(
        git_dir,
        "log",
        "--first-parent",
        "--no-merges",
        f"--max-count={history_limit}",
        "--format=%H%x1f%P%x1f%B%x1e",
        "HEAD",
    )
    records: list[CommitRecord] = []
    for block in raw.split("\x1e"):
        block = block.strip()
        if not block:
            continue
        fields = block.split("\x1f", 2)
        if len(fields) != 3:
            continue
        commit, parents, message = fields
        parent = parents.split()[0] if parents.split() else ""
        if not parent:
            continue
        changed = _run_git(
            git_dir,
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            commit,
        )
        changes: list[tuple[str, str]] = []
        for line in changed.splitlines():
            columns = line.split("\t")
            if len(columns) != 2:
                changes.append((columns[0][:1] if columns else "?", ""))
                continue
            changes.append((columns[0][:1], columns[1]))
        records.append(
            CommitRecord(
                commit=commit,
                parent=parent,
                message=message,
                changes=tuple(changes),
            )
        )
    return records


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    ).encode()


def _write_new(path: Path, payload: bytes, *, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"refusing to replace locked corpus file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--bare-root",
        type=Path,
        default=ROOT / "corpus" / "independent" / "bare",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "corpus" / "independent" / "v1",
    )
    parser.add_argument("--history-limit", type=int, default=250)
    parser.add_argument("--per-repo", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.history_limit <= 0 or args.per_repo <= 0:
        raise SystemExit("history-limit and per-repo must be positive")

    config = json.loads(args.config.read_text(encoding="utf-8"))
    split_repos = {
        split: [str(repo) for repo in config.get(split, [])]
        for split in ("development", "final")
    }
    if not split_repos["development"] or not split_repos["final"]:
        raise SystemExit("config must contain non-empty development and final")
    overlap = set(split_repos["development"]).intersection(split_repos["final"])
    if overlap:
        raise SystemExit(f"repository split overlap: {sorted(overlap)}")

    rows_by_split: dict[str, list[dict[str, Any]]] = {}
    heads: dict[str, str] = {}
    for split, repos in split_repos.items():
        rows: list[dict[str, Any]] = []
        for repo in repos:
            git_dir = _ensure_clone(args.bare_root, repo)
            heads[repo] = _run_git(git_dir, "rev-parse", "HEAD").strip()
            records = _log_records(
                git_dir,
                history_limit=args.history_limit,
            )
            selected = choose_records(repo, records, limit=args.per_repo)
            if len(selected) != args.per_repo:
                raise SystemExit(
                    f"{repo}: only {len(selected)} eligible commits; "
                    f"need {args.per_repo}"
                )
            rows.extend(
                sample
                for record in selected
                if (sample := build_sample(repo, record)) is not None
            )
        rows.sort(key=lambda row: (str(row["repo"]), str(row["id"])))
        rows_by_split[split] = rows

    payloads = {
        split: _jsonl_bytes(rows)
        for split, rows in rows_by_split.items()
    }
    for split, payload in payloads.items():
        _write_new(
            args.output_root / f"{split}.jsonl",
            payload,
            force=args.force,
        )
    lock = {
        "version": str(config.get("version") or "independent-v1"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection": {
            "history_limit": args.history_limit,
            "per_repo": args.per_repo,
            "repository_split": split_repos,
        },
        "repo_heads": heads,
        "files": {
            f"{split}.jsonl": {
                "cases": len(rows_by_split[split]),
                "sha256": hashlib.sha256(payloads[split]).hexdigest(),
            }
            for split in ("development", "final")
        },
    }
    _write_new(
        args.output_root / "LOCK.json",
        _json_bytes(lock),
        force=args.force,
    )
    print(json.dumps(lock, sort_keys=True))


if __name__ == "__main__":
    main()
