from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse

import httpx


@dataclass(frozen=True)
class SearchResult:
    paths: tuple[str, ...]
    latency_ms: float
    status: str
    error: str | None = None
    scores: tuple[float | None, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_path(path: str | None, *, repo: str, revision: str) -> str | None:
    """Normalize a provider citation to a repository-relative POSIX path."""
    if path is None:
        return None
    normalized = unquote(path.strip().strip("`'\"")).replace("\\", "/")
    if not normalized:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme and parsed.netloc:
        normalized = parsed.path
        marker = f"/{repo}/blob/{revision}/"
        if marker in normalized:
            normalized = normalized.split(marker, 1)[1]
        elif "/blob/" in normalized:
            normalized = normalized.split("/blob/", 1)[1].split("/", 1)[-1]
    normalized = normalized.split("#", 1)[0].split("?", 1)[0]
    normalized = normalized.removeprefix("./").lstrip("/")
    repo_prefix = f"{repo}/"
    if normalized.startswith(repo_prefix):
        normalized = normalized[len(repo_prefix) :]
    return normalized or None


class RetryingHTTPClient:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 180.0,
        max_attempts: int = 4,
    ) -> None:
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout_s))
        self.max_attempts = max_attempts

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.RequestError:
                if attempt + 1 == self.max_attempts:
                    raise
                time.sleep(2**attempt)
                continue
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            last_response = response
            if attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 2**attempt)
        assert last_response is not None
        return last_response


class DelphiClient:
    label = "delphi_code_search_agent"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.http = RetryingHTTPClient(client=client)

    def search(
        self,
        *,
        query: str,
        repo: str,
        revision: str,
        source_id: str,
        limit: int,
    ) -> SearchResult:
        started = time.perf_counter()
        try:
            response = self.http.request(
                "POST",
                f"{self.base_url}/v1/search/code",
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={"query": query, "repo_ids": [source_id], "top_k": limit},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResult(
                (),
                (time.perf_counter() - started) * 1000,
                "error",
                type(exc).__name__,
            )
        if not payload.get("success", True):
            return SearchResult(
                (),
                (time.perf_counter() - started) * 1000,
                "error",
                str(payload.get("error") or "delphi_search_error"),
            )
        paths: list[str] = []
        scores: list[float | None] = []
        for row in payload.get("results") or []:
            path = normalize_path(row.get("file_path"), repo=repo, revision=revision)
            if path is None:
                continue
            paths.append(path)
            value = row.get("relevance_score")
            scores.append(float(value) if value is not None else None)
            if len(paths) >= limit:
                break
        return SearchResult(
            tuple(paths),
            (time.perf_counter() - started) * 1000,
            "ok",
            scores=tuple(scores),
            metadata={
                "search_time_ms": payload.get("search_time_ms"),
                "quality_mode": "server_frozen_agent",
            },
        )


class NiaClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        fast_mode: bool,
        reasoning_strategy: str,
        skip_llm: bool,
        source_kind: str = "repository",
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.fast_mode = fast_mode
        self.reasoning_strategy = reasoning_strategy
        self.skip_llm = skip_llm
        if source_kind not in {"repository", "local_folder"}:
            raise ValueError(f"unsupported Nia source kind: {source_kind}")
        self.source_kind = source_kind
        mode = "raw" if skip_llm else "citations"
        speed = "fast" if fast_mode else "deep"
        self.label = f"nia_query_{mode}_{speed}_{reasoning_strategy}"
        self.http = RetryingHTTPClient(client=client)

    def search(
        self,
        *,
        query: str,
        repo: str,
        revision: str,
        source_id: str | tuple[str, ...],
        limit: int,
    ) -> SearchResult:
        started = time.perf_counter()
        try:
            scope = (
                {
                    "local_folders": (
                        list(source_id)
                        if isinstance(source_id, tuple)
                        else [source_id]
                    ),
                    "search_mode": "sources",
                }
                if self.source_kind == "local_folder"
                else {
                    "repositories": [source_id],
                    "search_mode": "repositories",
                }
            )
            response = self.http.request(
                "POST",
                f"{self.base_url}/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "mode": "query",
                    "messages": [{"role": "user", "content": query}],
                    **scope,
                    "include_sources": True,
                    "fast_mode": self.fast_mode,
                    "skip_llm": self.skip_llm,
                    "reasoning_strategy": self.reasoning_strategy,
                    "max_tokens": 8_000,
                    "bypass_semantic_cache": True,
                    "include_follow_ups": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResult(
                (),
                (time.perf_counter() - started) * 1000,
                "error",
                type(exc).__name__,
            )
        paths: list[str] = []
        scores: list[float | None] = []
        for source in payload.get("sources") or []:
            if isinstance(source, str):
                raw_path = source
                score = None
            elif isinstance(source, dict):
                source_metadata = (
                    source.get("metadata")
                    if isinstance(source.get("metadata"), dict)
                    else {}
                )
                raw_path = (
                    source.get("file_path")
                    or source.get("path")
                    or source.get("url")
                    or source_metadata.get("file_path")
                    or source_metadata.get("path")
                    or source_metadata.get("url")
                )
                value = source.get("score")
                if value is None:
                    value = source.get("similarity")
                if value is None:
                    value = source_metadata.get("score")
                if value is None:
                    value = source_metadata.get("similarity")
                score = float(value) if value is not None else None
            else:
                continue
            path = normalize_path(raw_path, repo=repo, revision=revision)
            if path is None:
                continue
            paths.append(path)
            scores.append(score)
            if len(paths) >= limit:
                break
        synthesis = str(payload.get("content") or "")
        return SearchResult(
            tuple(paths),
            (time.perf_counter() - started) * 1000,
            "ok",
            scores=tuple(scores),
            metadata={
                "retrieval_log_id": payload.get("retrieval_log_id"),
                "synthesis_length": len(synthesis),
                "synthesis_sha256": (
                    __import__("hashlib").sha256(synthesis.encode()).hexdigest()
                    if synthesis
                    else None
                ),
                "ranking_semantics": (
                    "raw_score_order" if self.skip_llm else "ordered_citations"
                ),
            },
        )
