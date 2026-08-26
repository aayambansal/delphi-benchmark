from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from ds1000_harness.models import QueryCase, RetrievedItem, SearchObservation


class SearchAdapter(ABC):
    @abstractmethod
    def search(self, case: QueryCase, limit: int) -> SearchObservation:
        """Retrieve bounded context for one case."""


class HTTPAdapter(SearchAdapter):
    engine: str

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=httpx.Timeout(60.0))
        self.max_attempts = max_attempts

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
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

    def _error(
        self,
        case: QueryCase,
        started: float,
        error_type: str,
    ) -> SearchObservation:
        return SearchObservation(
            engine=self.engine,
            case_id=case.case_id,
            items=(),
            latency_ms=(time.perf_counter() - started) * 1000,
            status="error",
            error_type=error_type,
        )


class DelphiHTTPAdapter(HTTPAdapter):
    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }


class DelphiAdapter(DelphiHTTPAdapter):
    engine = "delphi"

    def search(self, case: QueryCase, limit: int) -> SearchObservation:
        started = time.perf_counter()
        repo_id = case.metadata.get("delphi_repo_id")
        if not isinstance(repo_id, str) or not repo_id:
            return self._error(case, started, "missing_delphi_repo_id")
        try:
            response = self._request(
                "POST",
                f"{self.base_url}/v1/search/code",
                headers=self.headers,
                json={
                    "query": case.query,
                    "repo_ids": [repo_id],
                    "top_k": limit,
                },
            )
        except httpx.RequestError as exc:
            return self._error(case, started, type(exc).__name__)
        if response.status_code >= 400:
            return self._error(case, started, f"http_{response.status_code}")
        payload = response.json()
        if not payload.get("success", True):
            return self._error(case, started, "delphi_search_error")

        items = tuple(
            RetrievedItem(
                path=result.get("file_path"),
                content=str(result.get("content") or ""),
                score=(
                    float(result["relevance_score"])
                    if result.get("relevance_score") is not None
                    else None
                ),
                rank=rank,
                raw_id=(
                    str(result["chunk_id"])
                    if result.get("chunk_id") is not None
                    else None
                ),
            )
            for rank, result in enumerate(payload.get("results", ())[:limit], start=1)
        )
        return SearchObservation(
            engine=self.engine,
            case_id=case.case_id,
            items=items,
            latency_ms=(time.perf_counter() - started) * 1000,
            status="ok",
            metadata={"search_time_ms": payload.get("search_time_ms")},
        )


class DelphiDocsAdapter(DelphiHTTPAdapter):
    engine = "delphi"

    def search(self, case: QueryCase, limit: int) -> SearchObservation:
        started = time.perf_counter()
        docs_id = case.metadata.get("delphi_docs_id")
        if not isinstance(docs_id, str) or not docs_id:
            return self._error(case, started, "missing_delphi_docs_id")
        try:
            response = self._request(
                "POST",
                f"{self.base_url}/v1/search",
                headers=self.headers,
                json={
                    "query": case.query,
                    "source_ids": [docs_id],
                    "source_types": ["docs"],
                    "k": limit,
                    "mode": "precise",
                },
            )
        except httpx.RequestError as exc:
            return self._error(case, started, type(exc).__name__)
        if response.status_code >= 400:
            return self._error(case, started, f"http_{response.status_code}")
        payload = response.json()
        if not payload.get("success", True):
            return self._error(case, started, "delphi_search_error")

        items = tuple(
            RetrievedItem(
                path=result.get("path"),
                content=str(result.get("text") or ""),
                score=(
                    float(result["score"])
                    if result.get("score") is not None
                    else None
                ),
                rank=rank,
                raw_id=(
                    str(result["chunk_id"])
                    if result.get("chunk_id") is not None
                    else None
                ),
            )
            for rank, result in enumerate(
                payload.get("results", ())[:limit],
                start=1,
            )
        )
        return SearchObservation(
            engine=self.engine,
            case_id=case.case_id,
            items=items,
            latency_ms=(time.perf_counter() - started) * 1000,
            status="ok",
            metadata={"mode_applied": payload.get("mode_applied")},
        )


class NiaAdapter(HTTPAdapter):
    engine = "nia"

    def search(self, case: QueryCase, limit: int) -> SearchObservation:
        started = time.perf_counter()
        selector = case.metadata.get("nia_repository_selector")
        if not isinstance(selector, (str, dict)):
            return self._error(case, started, "missing_nia_repository_selector")
        try:
            response = self._request(
                "POST",
                f"{self.base_url}/search",
                headers=self.headers,
                json={
                    "mode": "query",
                    "messages": [{"role": "user", "content": case.query}],
                    "repositories": [selector],
                    "search_mode": "repositories",
                    "include_sources": True,
                    "fast_mode": True,
                    "skip_llm": False,
                    "max_tokens": 8000,
                    "bypass_semantic_cache": True,
                    "include_follow_ups": False,
                },
            )
        except httpx.RequestError as exc:
            return self._error(case, started, type(exc).__name__)
        if response.status_code >= 400:
            return self._error(case, started, f"http_{response.status_code}")
        payload = response.json()
        sources = payload.get("sources") or []
        items: list[RetrievedItem] = []
        for rank, source in enumerate(sources[:limit], start=1):
            if isinstance(source, str):
                path = source
                content = ""
                score = None
                raw_id = source
            else:
                path = source.get("file_path") or source.get("path") or source.get("url")
                content = str(source.get("content") or source.get("text") or "")
                raw_score = source.get("score") or source.get("similarity")
                score = float(raw_score) if raw_score is not None else None
                raw_id = str(source.get("id") or path or "") or None
            items.append(RetrievedItem(path, content, score, rank, raw_id))
        return SearchObservation(
            engine=self.engine,
            case_id=case.case_id,
            items=tuple(items),
            latency_ms=(time.perf_counter() - started) * 1000,
            status="ok",
            metadata={
                "retrieval_log_id": payload.get("retrieval_log_id"),
                "synthesis": payload.get("content"),
            },
        )


class NiaDocsAdapter(HTTPAdapter):
    engine = "nia"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        skip_llm: bool = False,
        client: httpx.Client | None = None,
        max_attempts: int = 3,
    ) -> None:
        super().__init__(
            base_url,
            api_key,
            client=client,
            max_attempts=max_attempts,
        )
        self.skip_llm = skip_llm

    def search(self, case: QueryCase, limit: int) -> SearchObservation:
        started = time.perf_counter()
        docs_id = case.metadata.get("nia_docs_id")
        if not isinstance(docs_id, str) or not docs_id:
            return self._error(case, started, "missing_nia_docs_id")
        try:
            response = self._request(
                "POST",
                f"{self.base_url}/search",
                headers=self.headers,
                json={
                    "mode": "query",
                    "messages": [{"role": "user", "content": case.query}],
                    "data_sources": [docs_id],
                    "search_mode": "sources",
                    "include_sources": True,
                    "fast_mode": True,
                    "skip_llm": self.skip_llm,
                    "max_tokens": 8000,
                    "bypass_semantic_cache": True,
                    "include_follow_ups": False,
                },
            )
        except httpx.RequestError as exc:
            return self._error(case, started, type(exc).__name__)
        if response.status_code >= 400:
            return self._error(case, started, f"http_{response.status_code}")
        payload = response.json()
        content = str(payload.get("content") or "")
        citations = payload.get("sources") or []
        first_path = str(citations[0]) if citations else None
        if self.skip_llm:
            raw_items: list[RetrievedItem] = []
            for rank, source in enumerate(citations[:limit], start=1):
                if isinstance(source, str):
                    path = source
                    source_content = ""
                    score = None
                    raw_id = source
                else:
                    path = (
                        source.get("file_path")
                        or source.get("path")
                        or source.get("url")
                    )
                    source_content = str(
                        source.get("content") or source.get("text") or ""
                    )
                    raw_score = source.get("score") or source.get("similarity")
                    score = (
                        float(raw_score)
                        if raw_score is not None
                        else None
                    )
                    raw_id = str(source.get("id") or path or "") or None
                raw_items.append(
                    RetrievedItem(
                        path=path,
                        content=source_content,
                        score=score,
                        rank=rank,
                        raw_id=raw_id,
                    )
                )
            items = tuple(raw_items)
        else:
            items = (
                (
                    RetrievedItem(
                        path=first_path,
                        content=content,
                        score=None,
                        rank=1,
                        raw_id=first_path,
                    ),
                )
                if content
                else ()
            )
        return SearchObservation(
            engine=self.engine,
            case_id=case.case_id,
            items=items,
            latency_ms=(time.perf_counter() - started) * 1000,
            status="ok",
            metadata={
                "retrieval_log_id": payload.get("retrieval_log_id"),
                "citations": citations[:limit],
                "result_mode": (
                    "raw_sources" if self.skip_llm else "synthesized_answer"
                ),
            },
        )


class Context7Adapter(HTTPAdapter):
    engine = "context7"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        resolver_strategy: str = "first",
        client: httpx.Client | None = None,
        max_attempts: int = 3,
    ) -> None:
        super().__init__(
            base_url,
            api_key,
            client=client,
            max_attempts=max_attempts,
        )
        if resolver_strategy not in {"first", "quality"}:
            raise ValueError(
                f"unknown Context7 resolver strategy: {resolver_strategy}"
            )
        self.resolver_strategy = resolver_strategy

    def search(self, case: QueryCase, limit: int) -> SearchObservation:
        started = time.perf_counter()
        library_name = case.metadata.get("library_name")
        if not isinstance(library_name, str) or not library_name:
            return self._error(case, started, "missing_library_name")
        library_id = case.metadata.get("context7_library_id")
        if library_id is not None and (
            not isinstance(library_id, str) or not library_id
        ):
            return self._error(case, started, "invalid_context7_library_id")
        try:
            if library_id is None:
                library_response = self._request(
                    "GET",
                    f"{self.base_url}/libs/search",
                    headers=self.headers,
                    params={"libraryName": library_name, "query": case.query},
                )
                if library_response.status_code >= 400:
                    return self._error(
                        case,
                        started,
                        f"http_{library_response.status_code}",
                    )
                libraries = library_response.json().get("results") or []
                if not libraries:
                    return self._error(case, started, "library_not_found")
                if self.resolver_strategy == "quality":
                    normalized_name = re.sub(
                        r"[^a-z0-9]+",
                        "",
                        library_name.casefold(),
                    )

                    def quality_key(library: dict[str, Any]) -> tuple:
                        normalized_title = re.sub(
                            r"[^a-z0-9]+",
                            "",
                            str(library.get("title") or "").casefold(),
                        )
                        return (
                            normalized_title == normalized_name,
                            float(library.get("benchmarkScore") or 0),
                            float(library.get("trustScore") or 0),
                            int(library.get("totalSnippets") or 0),
                        )

                    library_id = max(libraries, key=quality_key)["id"]
                    resolution = "automatic_quality"
                else:
                    library_id = libraries[0]["id"]
                    resolution = "automatic"
            else:
                resolution = "preresolved"
            context_response = self._request(
                "GET",
                f"{self.base_url}/context",
                headers=self.headers,
                params={
                    "libraryId": library_id,
                    "query": case.query,
                    "type": "json",
                },
            )
        except httpx.RequestError as exc:
            return self._error(case, started, type(exc).__name__)
        if context_response.status_code == 404:
            try:
                error_code = context_response.json().get("error")
            except ValueError:
                error_code = None
            if error_code == "no_relevant_snippets":
                return SearchObservation(
                    engine=self.engine,
                    case_id=case.case_id,
                    items=(),
                    latency_ms=(time.perf_counter() - started) * 1000,
                    status="no_result",
                    error_type=error_code,
                    metadata={
                        "library_id": library_id,
                        "resolution": resolution,
                    },
                )
        if context_response.status_code >= 400:
            return self._error(case, started, f"http_{context_response.status_code}")

        payload = context_response.json()
        parsed: list[tuple[str | None, str, str | None]] = []
        for snippet in payload.get("codeSnippets") or []:
            code_blocks = "\n\n".join(
                str(block.get("code") or "")
                for block in snippet.get("codeList") or []
            )
            content = "\n\n".join(
                part
                for part in (
                    str(snippet.get("codeTitle") or ""),
                    str(snippet.get("codeDescription") or ""),
                    code_blocks,
                )
                if part
            )
            raw_id = snippet.get("codeId")
            parsed.append((raw_id, content, raw_id))
        for snippet in payload.get("infoSnippets") or []:
            content = "\n\n".join(
                part
                for part in (
                    str(snippet.get("breadcrumb") or ""),
                    str(snippet.get("content") or ""),
                )
                if part
            )
            raw_id = snippet.get("pageId")
            parsed.append((raw_id, content, raw_id))

        items = tuple(
            RetrievedItem(path, content, None, rank, raw_id)
            for rank, (path, content, raw_id) in enumerate(parsed[:limit], start=1)
        )
        return SearchObservation(
            engine=self.engine,
            case_id=case.case_id,
            items=items,
            latency_ms=(time.perf_counter() - started) * 1000,
            status="ok",
            metadata={
                "library_id": library_id,
                "resolution": resolution,
            },
        )
