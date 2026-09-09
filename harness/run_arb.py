"""Round-3 ARB Track A runner: static repository file retrieval.

Engines:
  delphi   -> running local stack (POST /v1/search/code)
  nia      -> hosted Nia (POST /v2/search, local_folder scope)
  bm25     -> BM25Okapi over canonical git corpus (whole files)
  lexical  -> query-term overlap over canonical git corpus
  lexical_bm25 -> weighted file-level reciprocal-rank fusion of both lexical
                  baselines

Metrics come from the official ARB implementation (sample_metrics + pack_files)
with the canonical git corpus as the text source. Every case is streamed into
the runstore so the dashboard shows progress live.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
R2 = ROOT.parent / "delphi-evaluation-2026-07-29-round2"
sys.path.insert(0, str(ROOT))
# The pinned official ARB implementation lives in the archive (see
# harness/restore_corpora.py and external/arb-src); the round-2 tree is the
# historical fallback location.
for _arb_src in (ROOT / "external" / "arb-src" / "src", R2 / "external" / "arb-src" / "src"):
    if _arb_src.is_dir():
        sys.path.insert(0, str(_arb_src.resolve()))
        break
# Delphi's backend supplies the listwise/expansion prompts for matched baselines.
_BACKEND = ROOT.parent / "backend"
if _BACKEND.is_dir():
    sys.path.insert(0, str(_BACKEND.resolve()))

import httpx  # noqa: E402

from harness.gitcorpus import BARE, GitCorpus  # noqa: E402
from harness.runstore import RunWriter  # noqa: E402

from agent_retrieval_bench.baseline import (  # noqa: E402
    hard_negative_files,
    query_has_leakage,
    query_text_for_eval,
    sample_metrics,
    target_gold_files,
)
from agent_retrieval_bench.bcy_curve import pack_files  # noqa: E402

DELPHI_URL = "http://127.0.0.1:20742"
DELPHI_KEY = "delphi-benchmark-admin"
NIA_URL = "https://apigcp.trynia.ai/v2"

BINARY_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".whl",
    ".jar",
    ".class",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".mp4",
    ".webm",
    ".ogg",
    ".pyc",
    ".wasm",
    ".onnx",
    ".pt",
    ".pack",
    ".idx",
    ".parquet",
    ".npy",
    ".npz",
    ".h5",
    ".proto3",
    ".lock",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open() if line.strip()]


def resolve_sample_paths(
    *,
    split: str,
    workflows: str,
    explicit: list[Path] | None,
) -> list[Path]:
    if explicit:
        return explicit
    return [
        ROOT / "samples" / split / f"{workflow}.jsonl"
        for workflow in workflows.split(",")
    ]


def resolve_fetch_limit(
    fetch_limit: int | None,
    *,
    scored_limit: int,
) -> int:
    """Use the API's scored top-k contract unless over-fetch is explicit."""
    resolved = scored_limit if fetch_limit is None else fetch_limit
    if resolved < scored_limit:
        raise ValueError("fetch limit must be at least the scored limit")
    return resolved


def is_text_candidate(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix not in BINARY_EXT


class ChunkCache:
    """ARB-style chunks (file chunk + symbol chunks) per snapshot, built from
    the canonical git corpus with the official ARB chunker and path filter."""

    def __init__(self, corpus: GitCorpus, max_snapshots: int = 2) -> None:
        self.corpus = corpus
        self.cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.max_snapshots = max_snapshots

    def _disk_path(self, repo: str, commit: str) -> Path:
        return ROOT / "cache" / "chunks" / repo.replace("/", "__") / f"{commit}.jsonl.gz"

    def get(self, repo: str, commit: str) -> list[dict[str, Any]]:
        import gzip

        from agent_retrieval_bench.corpus import chunks_for_file, is_candidate_path

        key = (repo, commit)
        if key in self.cache:
            return self.cache[key]
        disk = self._disk_path(repo, commit)
        chunks: list[dict[str, Any]] = []
        if disk.is_file():
            with gzip.open(disk, "rt", encoding="utf-8") as fh:
                chunks = [json.loads(line) for line in fh if line.strip()]
        else:
            for path in self.corpus.list_files(repo, commit):
                if not is_text_candidate(path) or not is_candidate_path(path):
                    continue
                text = self.corpus.file_text(repo, commit, path)
                if text is None or not text.strip() or len(text) > 1_500_000:
                    continue
                chunks.extend(chunks_for_file(repo, commit, path, text))
            disk.parent.mkdir(parents=True, exist_ok=True)
            tmp = disk.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                for chunk in chunks:
                    fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            tmp.replace(disk)
        if len(self.cache) >= self.max_snapshots:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = chunks
        return chunks


def normalize_path(path: str | None, *, repo: str) -> str | None:
    if not path:
        return None
    p = path.strip().strip("`'\"").replace("\\", "/")
    p = p.split("#", 1)[0].split("?", 1)[0]
    p = p.removeprefix("./").lstrip("/")
    prefix = repo.split("/")[-1] + "/"
    if p.startswith(repo + "/"):
        p = p[len(repo) + 1 :]
    elif p.startswith(prefix) and p not in (prefix,):
        # Nia local folders were uploaded repo-relative; keep as-is unless the
        # provider prefixed the identifier path.
        pass
    for marker in ("/arb/" + repo + "/",):
        if marker in p:
            p = p.split(marker, 1)[1].split("/", 1)[-1]
    return p or None


def retrieval_config_mismatches(
    expected: dict[str, Any],
    observed: Any,
    *,
    prefix: str = "",
) -> list[str]:
    """Compare an expected config subset against serving provenance."""
    if not isinstance(observed, dict):
        return [prefix.rstrip(".") or "retrieval_config"]
    mismatches: list[str] = []
    for key, expected_value in expected.items():
        field = f"{prefix}{key}"
        if key not in observed:
            mismatches.append(field)
            continue
        observed_value = observed[key]
        if isinstance(expected_value, dict):
            mismatches.extend(
                retrieval_config_mismatches(
                    expected_value,
                    observed_value,
                    prefix=f"{field}.",
                )
            )
        elif observed_value != expected_value:
            mismatches.append(field)
    return mismatches


def observed_retrieval_configs(
    details: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return unique serving configurations observed in case responses."""
    unique: dict[str, dict[str, Any]] = {}
    for row in details:
        config = row.get("retrieval_config")
        if not isinstance(config, dict):
            continue
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
        unique.setdefault(canonical, config)
    return [unique[key] for key in sorted(unique)]


class DelphiEngine:
    label = "delphi"

    def __init__(
        self,
        sources: dict[tuple[str, str], Any],
        *,
        base_url: str = DELPHI_URL,
        api_key: str = DELPHI_KEY,
        fetch_limit: int = 100,
        search_type: str = "vector",
        expected_retrieval_config: dict[str, Any] | None = None,
    ) -> None:
        self.sources = sources
        self.http = httpx.Client(timeout=httpx.Timeout(480.0))
        self.base_url = base_url
        self.api_key = api_key
        self.fetch_limit = fetch_limit
        self.search_type = search_type
        self.expected_retrieval_config = expected_retrieval_config

    def search(
        self, sample: dict[str, Any], query: str, *, limit: int
    ) -> dict[str, Any]:
        repo = str(sample["repo"])
        revision = str(sample["base_commit"]).lower()
        source = self.sources.get((repo, revision))
        if source is None:
            return {"status": "unprovisioned", "paths": [], "latency_ms": 0.0}
        started = time.perf_counter()
        try:
            resp = self.http.post(
                f"{self.base_url}/v1/search/code",
                headers={"X-API-Key": self.api_key},
                json={
                    "query": query,
                    "repo_ids": [source] if isinstance(source, str) else list(source),
                    "top_k": self.fetch_limit,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "paths": [],
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        observed_config = payload.get("retrieval_config")
        if self.expected_retrieval_config is not None:
            mismatches = retrieval_config_mismatches(
                self.expected_retrieval_config,
                observed_config,
            )
            if mismatches:
                return {
                    "status": "configuration_mismatch",
                    "fatal": True,
                    "error": (
                        "serving retrieval configuration mismatch: "
                        + ", ".join(sorted(mismatches))
                    ),
                    "paths": [],
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    "meta": {"retrieval_config": observed_config},
                }
        paths = []
        candidates = []
        for row in payload.get("results") or []:
            p = normalize_path(row.get("file_path"), repo=repo)
            if p:
                paths.append(p)
                candidates.append(
                    {
                        "path": p,
                        "chunk_id": row.get("chunk_id"),
                        "relevance_score": row.get("relevance_score"),
                        "candidate_sources": row.get("candidate_sources"),
                    }
                )
        return {
            "status": "ok",
            "paths": paths,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "meta": {
                "search_time_ms": payload.get("search_time_ms"),
                "candidates": candidates,
                "hybrid": payload.get("hybrid"),
                "query_compacted": payload.get("query_compacted"),
                "query_expanded": payload.get("query_expanded"),
                "retrieval_config": observed_config,
                "timing": payload.get("timing"),
                "warnings": payload.get("warnings"),
            },
        }


class NiaEngine:
    label = "nia"

    def __init__(
        self, sources: dict[tuple[str, str], Any], *, fast_mode: bool = True
    ) -> None:
        self.sources = sources
        self.http = httpx.Client(timeout=httpx.Timeout(300.0))
        self.fast_mode = fast_mode
        self.api_key = None
        import os

        self.api_key = os.environ["NIA_API_KEY"]

    def search(
        self, sample: dict[str, Any], query: str, *, limit: int
    ) -> dict[str, Any]:
        repo = str(sample["repo"])
        revision = str(sample["base_commit"]).lower()
        source = self.sources.get((repo, revision))
        if source is None:
            return {"status": "unprovisioned", "paths": [], "latency_ms": 0.0}
        folder_ids = list(source) if isinstance(source, (list, tuple)) else [source]
        started = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            try:
                resp = self.http.post(
                    f"{NIA_URL}/search",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "mode": "query",
                        "messages": [{"role": "user", "content": query}],
                        "local_folders": folder_ids,
                        "search_mode": "sources",
                        "include_sources": True,
                        "fast_mode": self.fast_mode,
                        "skip_llm": False,
                        "reasoning_strategy": "hybrid",
                        "max_tokens": 8000,
                        "bypass_semantic_cache": True,
                        "include_follow_ups": False,
                    },
                )
                if resp.status_code in {429, 500, 502, 503, 504} and attempts < 4:
                    time.sleep(2**attempts)
                    continue
                resp.raise_for_status()
                payload = resp.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                if attempts < 4:
                    time.sleep(2**attempts)
                    continue
                return {
                    "status": "error",
                    "error": f"{type(exc).__name__}"[:300],
                    "paths": [],
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
        paths = []
        for source_row in payload.get("sources") or []:
            raw = None
            if isinstance(source_row, str):
                raw = source_row
            elif isinstance(source_row, dict):
                meta = (
                    source_row.get("metadata")
                    if isinstance(source_row.get("metadata"), dict)
                    else {}
                )
                raw = (
                    source_row.get("file_path")
                    or source_row.get("path")
                    or source_row.get("url")
                    or meta.get("file_path")
                    or meta.get("path")
                    or meta.get("url")
                )
            p = normalize_path(raw, repo=repo)
            if p:
                paths.append(p)
        return {
            "status": "ok",
            "paths": paths,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "meta": {"synthesis_len": len(str(payload.get("content") or ""))},
        }


def _unique_paths_from_scored(
    ranked_chunks: list[tuple[float, dict[str, Any]]],
) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for _, chunk in ranked_chunks:
        path = str(chunk.get("path") or "")
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _fuse_ranked_paths(
    bm25_paths: list[str],
    lexical_paths: list[str],
    *,
    lexical_weight: float,
    rrf_k: int = 60,
) -> list[str]:
    """Fuse two complete file rankings with weighted reciprocal-rank fusion."""
    if not 0.0 <= lexical_weight <= 1.0:
        raise ValueError("lexical_weight must be between 0 and 1")
    if rrf_k < 0:
        raise ValueError("rrf_k must be non-negative")

    scores: dict[str, float] = {}
    for weight, ranking in (
        (1.0 - lexical_weight, bm25_paths),
        (lexical_weight, lexical_paths),
    ):
        if weight == 0.0:
            continue
        for rank, path in enumerate(ranking, start=1):
            scores[path] = scores.get(path, 0.0) + weight / (rrf_k + rank)
    return sorted(scores, key=lambda path: (-scores[path], path))


class CorpusEngine:
    def __init__(
        self,
        corpus: GitCorpus,
        ranker: str,
        *,
        lexical_weight: float = 0.7,
    ) -> None:
        self.chunk_cache = ChunkCache(corpus)
        self.ranker = ranker
        self.label = ranker
        self.lexical_weight = lexical_weight

    def search(
        self, sample: dict[str, Any], query: str, *, limit: int
    ) -> dict[str, Any]:
        from agent_retrieval_bench.baseline import (
            rank_chunks_bm25_with_scores,
            rank_chunks_with_scores,
        )

        repo = str(sample["repo"])
        commit = str(sample["base_commit"])
        started = time.perf_counter()
        try:
            chunks = self.chunk_cache.get(repo, commit)
            if self.ranker == "lexical_bm25":
                bm25_paths = _unique_paths_from_scored(
                    rank_chunks_bm25_with_scores(query, chunks)
                )
                lexical_paths = _unique_paths_from_scored(
                    rank_chunks_with_scores(query, chunks)
                )
                paths = _fuse_ranked_paths(
                    bm25_paths,
                    lexical_paths,
                    lexical_weight=self.lexical_weight,
                )[:limit]
            else:
                fn = (
                    rank_chunks_bm25_with_scores
                    if self.ranker == "bm25"
                    else rank_chunks_with_scores
                )
                paths = _unique_paths_from_scored(fn(query, chunks))[:limit]
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "paths": [],
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        return {
            "status": "ok",
            "paths": paths,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "meta": (
                {"lexical_weight": self.lexical_weight}
                if self.ranker == "lexical_bm25"
                else {}
            ),
        }


def dedupe(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(p for p in paths if p))


def mean_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {}
    names = sorted(set.intersection(*(set(r["metrics"]) for r in rows)))
    return {n: fmean(float(r["metrics"][n]) for r in rows) for n in names}


def macro(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    means = [mean_metrics(g) for g in groups.values()]
    if not means:
        return {}
    names = sorted(set.intersection(*(set(m) for m in means)))
    return {n: fmean(m[n] for m in means) for n in names}


def load_sources(path: Path) -> dict[tuple[str, str], Any]:
    out: dict[tuple[str, str], Any] = {}
    for row in read_jsonl(path):
        key = (str(row["repo"]), str(row["revision"]).lower())
        if row.get("status") not in {"indexed", "reused"}:
            out.pop(key, None)
            continue
        metadata = row.get("metadata") or {}
        invalid_counts = any(
            field in metadata
            and (type(metadata[field]) is not int or metadata[field] <= 0)
            for field in ("files_indexed", "chunks_created")
        )
        if invalid_counts:
            out.pop(key, None)
            continue
        sid = row.get("source_id")
        shards = metadata.get("source_ids")
        value = tuple(shards) if isinstance(shards, list) and shards else sid
        out[key] = value
    return out


def missing_source_pairs(
    samples: list[dict[str, Any]],
    sources: dict[tuple[str, str], Any],
) -> list[tuple[str, str]]:
    required = {
        (str(sample["repo"]), str(sample["base_commit"]).lower()) for sample in samples
    }
    return sorted(required.difference(sources))


def delphi_gold_searchability_gaps(
    samples: list[dict[str, Any]],
    sources: dict[tuple[str, str], Any],
    *,
    base_url: str,
    api_key: str,
    http: httpx.Client | None = None,
) -> list[dict[str, str]]:
    """Return gold paths that lack searchable chunks in their exact source."""
    owned_http = http is None
    client = http or httpx.Client(timeout=httpx.Timeout(120.0))
    gaps: list[dict[str, str]] = []
    try:
        for sample in sorted(samples, key=lambda row: str(row["id"])):
            repo = str(sample["repo"])
            revision = str(sample["base_commit"]).lower()
            source = sources.get((repo, revision))
            if source is None:
                continue
            source_ids = (
                list(source) if isinstance(source, (list, tuple)) else [source]
            )
            for path in sorted(target_gold_files(sample)):
                reason = "file_not_found"
                searchable = False
                for source_id in source_ids:
                    try:
                        response = client.post(
                            f"{base_url}/v1/files/get",
                            headers={"X-API-Key": api_key},
                            json={
                                "repo_id": source_id,
                                "file_path": path,
                                "start_line": 1,
                                "end_line": 1,
                            },
                        )
                        response.raise_for_status()
                        payload = response.json()
                    except (httpx.HTTPError, ValueError):
                        reason = "request_error"
                        continue
                    indexed_chunks = payload.get("indexed_chunks")
                    if (
                        payload.get("success") is True
                        and type(indexed_chunks) is int
                        and indexed_chunks > 0
                    ):
                        searchable = True
                        break
                    if payload.get("success") is True:
                        reason = (
                            "no_indexed_chunks"
                            if indexed_chunks == 0
                            else "missing_chunk_provenance"
                        )
                    else:
                        reason = str(payload.get("error") or "file_not_found")
                if not searchable:
                    gaps.append(
                        {
                            "case_id": str(sample["id"]),
                            "repo": repo,
                            "revision": revision,
                            "path": path,
                            "reason": reason,
                        }
                    )
    finally:
        if owned_http:
            client.close()
    return gaps


def enforce_gold_searchability(
    gaps: list[dict[str, str]],
    *,
    output: Path,
) -> None:
    """Persist any missing gold paths and stop before invalid scoring."""
    if not gaps:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema": "delphi_gold_searchability_gaps_v1",
                "gaps": gaps,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    raise SystemExit(
        f"gold searchability preflight failed: {len(gaps)} target paths missing; "
        f"details written to {output}"
    )


def run_gold_searchability_preflight(
    samples: list[dict[str, Any]],
    sources: dict[tuple[str, str], Any],
    *,
    base_url: str,
    api_key: str,
    output: Path,
    http: httpx.Client | None = None,
) -> bool:
    gaps = delphi_gold_searchability_gaps(
        samples,
        sources,
        base_url=base_url,
        api_key=api_key,
        http=http,
    )
    enforce_gold_searchability(gaps, output=output)
    return True


def benchmark_status(
    details: list[dict[str, Any]],
    skipped: list[str],
) -> str:
    if not details or skipped:
        return "failed"
    return "done" if all(row.get("status") == "ok" for row in details) else "failed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine",
        required=True,
        choices=(
            "delphi",
            "nia",
            "bm25",
            "lexical",
            "lexical_bm25",
            "dense",
            "hybrid",
            "hybrid_expand",
            "hybrid_rerank",
            "hybrid_rerank_expand",
        ),
    )
    parser.add_argument(
        "--split", default="development", choices=("development", "final")
    )
    parser.add_argument(
        "--workflows",
        default="v2_code2test,v2_comment2context,v2_trace2code,v2_edit2ripple",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=None,
        help="jsonl of provisioned sources (delphi/nia)",
    )
    parser.add_argument("--sample-files", type=Path, nargs="+")
    parser.add_argument("--bare-root", type=Path, default=BARE)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--fetch-limit",
        type=int,
        default=None,
        help=(
            "provider top-k; defaults to --limit so backend branch-preservation "
            "and reranking operate at the scored boundary"
        ),
    )
    parser.add_argument("--budget", type=int, default=8000)
    parser.add_argument(
        "--cases", type=Path, default=None, help="optional file of case ids to keep"
    )
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--system", default=None, help="system label override")
    parser.add_argument("--notes", default="")
    parser.add_argument("--delphi-url", default=DELPHI_URL)
    parser.add_argument("--delphi-key", default=DELPHI_KEY)
    parser.add_argument(
        "--expected-retrieval-config-json",
        default=None,
        help=(
            "JSON object that must match a subset of Delphi's serving "
            "retrieval_config; the run stops on the first mismatch"
        ),
    )
    parser.add_argument("--lexical-weight", type=float, default=0.7)
    parser.add_argument(
        "--keep-snapshots",
        action="store_true",
        help="keep materialized snapshots on disk after a strong-baseline run",
    )
    parser.add_argument(
        "--nia-fast-mode", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--allow-partial-sources",
        action="store_true",
        help="score only provisioned snapshots instead of failing coverage preflight",
    )
    parser.add_argument(
        "--gold-audit-output",
        type=Path,
        default=None,
        help="where to persist missing Delphi gold-path searchability records",
    )
    args = parser.parse_args()

    corpus = GitCorpus(bare_root=args.bare_root)
    try:
        fetch_limit = resolve_fetch_limit(
            args.fetch_limit,
            scored_limit=args.limit,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    expected_retrieval_config = None
    if args.expected_retrieval_config_json is not None:
        try:
            expected_retrieval_config = json.loads(
                args.expected_retrieval_config_json
            )
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"invalid --expected-retrieval-config-json: {exc}"
            ) from exc
        if not isinstance(expected_retrieval_config, dict):
            raise SystemExit(
                "--expected-retrieval-config-json must decode to an object"
            )
    source_map: dict[tuple[str, str], Any] | None = None
    if args.engine == "delphi":
        source_map = load_sources(args.sources)
        engine: Any = DelphiEngine(
            source_map,
            base_url=args.delphi_url,
            api_key=args.delphi_key,
            fetch_limit=fetch_limit,
            expected_retrieval_config=expected_retrieval_config,
        )
    elif args.engine == "nia":
        source_map = load_sources(args.sources)
        engine = NiaEngine(source_map, fast_mode=args.nia_fast_mode)
    elif args.engine in ("dense", "hybrid", "hybrid_expand", "hybrid_rerank", "hybrid_rerank_expand"):
        from harness.strong_baselines import StrongBaselineEngine

        engine = StrongBaselineEngine(
            corpus,
            ChunkCache(corpus),
            args.engine,
            transient_snapshots=not args.keep_snapshots,
        )
    else:
        engine = CorpusEngine(
            corpus,
            args.engine,
            lexical_weight=args.lexical_weight,
        )

    keep_ids = None
    if args.cases:
        keep_ids = {line.strip() for line in args.cases.open() if line.strip()}

    samples = []
    sample_paths = resolve_sample_paths(
        split=args.split,
        workflows=args.workflows,
        explicit=args.sample_files,
    )
    for path in sample_paths:
        for row in read_jsonl(path):
            if (row.get("gold") or {}).get("no_gold") is True:
                continue
            if keep_ids and str(row["id"]) not in keep_ids:
                continue
            samples.append(row)
    samples.sort(key=lambda r: (str(r["repo"]), str(r["base_commit"]), str(r["id"])))
    if args.max_cases:
        samples = samples[: args.max_cases]
    gold_searchability_verified: bool | None = None
    if source_map is not None:
        missing = missing_source_pairs(samples, source_map)
        if missing and not args.allow_partial_sources:
            examples = ", ".join(
                f"{repo}@{revision[:10]}" for repo, revision in missing[:5]
            )
            raise SystemExit(
                f"source coverage incomplete: {len(missing)} snapshots missing "
                f"({examples}); pass --allow-partial-sources only for diagnostics"
            )
        if args.engine == "delphi" and not missing:
            audit_output = args.gold_audit_output or (
                ROOT
                / "results"
                / f"{args.run_id or 'delphi-arb'}-gold-searchability-gaps.json"
            )
            gold_searchability_verified = run_gold_searchability_preflight(
                samples,
                source_map,
                base_url=args.delphi_url,
                api_key=args.delphi_key,
                output=audit_output,
                http=engine.http,
            )
        elif args.engine == "delphi":
            gold_searchability_verified = False

    system = args.system or engine.label
    writer = RunWriter(
        track="A-static-retrieval",
        system=system,
        config={
            "engine": args.engine,
            "split": args.split,
            "limit": args.limit,
            "fetch_limit": fetch_limit,
            "budget": args.budget,
            "workflows": args.workflows,
            "nia_fast_mode": args.nia_fast_mode,
            "lexical_weight": args.lexical_weight,
            "sample_files": [str(path) for path in sample_paths],
            "bare_root": str(args.bare_root),
            "expected_retrieval_config": expected_retrieval_config,
            "gold_searchability_verified": gold_searchability_verified,
            "notes": args.notes,
        },
        split=args.split,
        run_id=args.run_id,
        notes=args.notes,
    )
    print(f"run_id={writer.run_id} cases={len(samples)}", flush=True)

    details: list[dict[str, Any]] = []
    skipped: list[str] = []
    for i, sample in enumerate(samples):
        case_id = str(sample["id"])
        repo = str(sample["repo"])
        revision = str(sample["base_commit"])
        gold = target_gold_files(sample)
        query = query_text_for_eval(sample)
        if query_has_leakage(sample, query):
            raise RuntimeError(f"query leakage in {case_id}")
        obs = engine.search(sample, query, limit=args.limit)
        if obs["status"] == "unprovisioned":
            skipped.append(case_id)
            continue
        ranked = dedupe(obs["paths"])[: args.limit]
        ranked_chunks = [
            {
                "path": p,
                "text": corpus.file_text(repo, revision, p) or "",
                "kind": "file",
            }
            for p in ranked
        ]
        metrics = sample_metrics(
            gold,
            ranked_chunks,
            context_budget=args.budget,
            hard_negative_files=hard_negative_files(sample),
        )
        packed = pack_files(repo, revision, ranked, set(gold), corpus, args.budget)
        metrics["BCY@8k"] = float(packed["bcy"])
        if obs["status"] != "ok":
            metrics = {name: 0.0 for name in metrics}
        row = {
            "sample_id": case_id,
            "task_type": str(sample.get("task_type") or "unknown"),
            "repo": repo,
            "base_commit": revision,
            "gold_files": gold,
            "top_files": ranked,
            "status": obs["status"],
            "error": obs.get("error"),
            "latency_ms": obs["latency_ms"],
            "metrics": metrics,
            "retrieval_config": (obs.get("meta") or {}).get("retrieval_config"),
        }
        details.append(row)
        writer.case(
            case_id=case_id,
            workflow=row["task_type"],
            repo=repo,
            revision=revision,
            ok=obs["status"] == "ok",
            latency_ms=obs["latency_ms"],
            metrics=metrics,
            ranked=ranked,
            gold=gold,
            trace={
                "query": query[:4000],
                "provider_meta": obs.get("meta", {}),
                "error": obs.get("error"),
            },
        )
        print(
            json.dumps(
                {
                    "i": i + 1,
                    "n": len(samples),
                    "case": case_id,
                    "status": obs["status"],
                    "MRR": round(metrics.get("MRR", 0), 3),
                    "R@20": round(metrics.get("Recall@20", 0), 3),
                    "lat_ms": round(obs["latency_ms"]),
                }
            ),
            flush=True,
        )
        if obs.get("fatal"):
            break

    ok_rows = [r for r in details if r["status"] == "ok"]
    latencies = [r["latency_ms"] for r in ok_rows]
    retrieval_configs = observed_retrieval_configs(details)
    summary = {
        "n": len(details),
        "failures": len(details) - len(ok_rows),
        "failure_rate": (len(details) - len(ok_rows)) / len(details)
        if details
        else None,
        "skipped_unprovisioned": len(skipped),
        "gold_searchability_verified": gold_searchability_verified,
        "expected_retrieval_config": expected_retrieval_config,
        "observed_retrieval_configs": retrieval_configs,
        "retrieval_configuration_verified": (
            None
            if expected_retrieval_config is None
            else bool(
                retrieval_configs
                and all(
                    not retrieval_config_mismatches(
                        expected_retrieval_config,
                        config,
                    )
                    for config in retrieval_configs
                )
                and len(ok_rows) == len(details)
            )
        ),
        "sample_weighted": mean_metrics(details),
        "repo_macro": macro(details, "repo"),
        "workflow_macro": macro(details, "task_type"),
        "by_workflow": {
            wf: {"n": len(rows), "metrics": mean_metrics(rows)}
            for wf, rows in sorted(
                (
                    (wf, [r for r in details if r["task_type"] == wf])
                    for wf in {r["task_type"] for r in details}
                ),
                key=lambda kv: kv[0],
            )
        },
        "latency_ms": (
            {"mean": fmean(latencies), "median": median(latencies)} if latencies else {}
        ),
    }
    status = benchmark_status(details, skipped)
    if hasattr(engine, "stats"):
        summary["engine_stats"] = dict(engine.stats)
    if hasattr(engine, "close"):
        engine.close()
    writer.finish(summary, status=status)
    out = ROOT / "results" / f"{writer.run_id}-details.jsonl"
    with out.open("w") as fh:
        for row in details:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    (ROOT / "results" / f"{writer.run_id}-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    if status != "done":
        raise SystemExit(
            f"benchmark invalid: {summary['failures']} technical failures, "
            f"{len(skipped)} unprovisioned cases"
        )
    print(
        json.dumps(
            {
                "run_id": writer.run_id,
                "MRR": summary["sample_weighted"].get("MRR"),
                "R@20": summary["sample_weighted"].get("Recall@20"),
                "BCY": summary["sample_weighted"].get("BCY@8k"),
                "skipped": len(skipped),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
