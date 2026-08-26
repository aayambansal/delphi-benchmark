from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import unquote, urlparse


def normalize_path(path: str | None, *, repo: str, revision: str) -> str | None:
    """Normalize a provider result to a repository-relative POSIX path."""
    if path is None:
        return None
    normalized = unquote(path.strip().strip("`'\"")).replace("\\", "/")
    if not normalized:
        return None

    parsed = urlparse(normalized)
    if parsed.scheme and parsed.netloc:
        normalized = parsed.path
        github_prefix = f"/{repo}/blob/{revision}/"
        if normalized.startswith(github_prefix):
            normalized = normalized[len(github_prefix) :]
        else:
            marker = "/blob/"
            if marker in normalized:
                normalized = normalized.split(marker, 1)[1].split("/", 1)[-1]

    normalized = normalized.split("#", 1)[0].split("?", 1)[0]
    normalized = normalized.removeprefix("./").lstrip("/")
    repo_prefix = f"{repo}/"
    if normalized.startswith(repo_prefix):
        normalized = normalized[len(repo_prefix) :]
    return normalized or None


@dataclass(frozen=True)
class QueryCase:
    case_id: str
    query: str
    source: str
    revision: str
    gold_paths: tuple[str, ...]
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.gold_paths:
            raise ValueError("positive-track query case requires at least one gold path")


@dataclass(frozen=True)
class DeveloperCase:
    case_id: str
    prompt: str
    library_name: str
    reference_code: str
    gold_identifiers: tuple[str, ...]
    canonical_docs: tuple[dict[str, str], ...]
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.canonical_docs:
            raise ValueError("developer case requires at least one canonical doc")
        if not self.gold_identifiers:
            raise ValueError("developer case requires at least one gold identifier")


@dataclass(frozen=True)
class RetrievedItem:
    path: str | None
    content: str
    score: float | None
    rank: int
    raw_id: str | None


@dataclass(frozen=True)
class SearchObservation:
    engine: str
    case_id: str
    items: tuple[RetrievedItem, ...]
    latency_ms: float
    status: Literal["ok", "no_result", "error", "unsupported"]
    error_type: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ranks = tuple(item.rank for item in self.items)
        if ranks != tuple(range(1, len(self.items) + 1)):
            raise ValueError("result ranks must be contiguous and one-based")
