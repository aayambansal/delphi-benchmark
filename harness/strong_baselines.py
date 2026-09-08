"""Matched strong baselines for the ARB-style static retrieval runner.

The frozen Delphi stack (commit 91d76c1) is a hybrid retriever with a learned
reranking head. A comparison against lexical baselines alone cannot say how
much of its margin comes from the engineering that is specific to Delphi and
how much comes from a conventional dense retriever plus a reranker. This
module adds a ladder of conventional systems, each rung adding exactly one
Delphi component so the differences are attributable:

  dense                 text-embedding-3-small (the embedding model Delphi
                        uses) over the official ARB chunks (file chunk plus
                        symbol chunks), max-pooled to files.
  hybrid                reciprocal-rank fusion (k=60, equal weights, untuned)
                        of the dense file ranking and ARB's BM25 file ranking.
  hybrid_rerank         hybrid top-50 -> top-30 through Delphi's own
                        cross-encoder (cross-encoder/ms-marco-MiniLM-L-6-v2,
                        blend alpha 0.4) -> Delphi's own listwise gpt-4o
                        reranker on the top 20 (seed 1042, Delphi's prompt).
  hybrid_rerank_expand  as hybrid_rerank, with Delphi's hypothetical-document
                        expansion (gpt-4o-mini, Delphi's prompt and gate)
                        feeding the dense query.

What remains between the last rung and frozen Delphi: its exact-symbol,
exact-path, path-affinity, and trigram candidate branches, its own chunker
and index, its tuned fusion weights, and quoted-path demotion.

Prompts and parsers for the listwise and expansion stages are imported from
the Delphi backend so they are identical by construction; the HTTP calls use
the same model names, temperature 0, seed 1042, and token limits as the
backend. Every model output is cached on disk so a rerun repeats exactly.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
EMBEDDING_MAX_TOKENS = 8000
EMBEDDING_BATCH_TOKENS = 200_000
EMBEDDING_BATCH_ITEMS = 512

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_BLEND_ALPHA = 0.4
HYBRID_CANDIDATES = 50
HYBRID_RERANK_K = 30
LISTWISE_MODEL = "gpt-4o"
LISTWISE_K = 20
LISTWISE_EXCERPT_CHARS = 280
LISTWISE_MAX_TOKENS = 300
LISTWISE_TIMEOUT = 20.0
EXPANSION_MODEL = "gpt-4o-mini"
EXPANSION_MAX_TOKENS = 220
EXPANSION_TIMEOUT = 10.0
LLM_SEED = 1042
RRF_K = 60

OPENAI_EMBEDDINGS = "https://api.openai.com/v1/embeddings"
OPENAI_CHAT = "https://api.openai.com/v1/chat/completions"

MODES = ("dense", "hybrid", "hybrid_rerank", "hybrid_rerank_expand")


def _openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for the strong baselines")
    return key


def _sha1(*parts: str) -> str:
    digest = hashlib.sha1()
    for part in parts:
        digest.update(part.encode("utf-8", "surrogatepass"))
        digest.update(b"\x1f")
    return digest.hexdigest()


class SqliteKV:
    """Small thread-safe key/value store for cached model outputs."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=120.0)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v BLOB NOT NULL)")
        self.conn.commit()
        self.lock = threading.Lock()

    def get_many(self, keys: list[str]) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        with self.lock:
            for start in range(0, len(keys), 900):
                batch = keys[start : start + 900]
                marks = ",".join("?" for _ in batch)
                rows = self.conn.execute(f"SELECT k, v FROM kv WHERE k IN ({marks})", batch).fetchall()
                out.update({k: v for k, v in rows})
        return out

    def put_many(self, items: dict[str, bytes]) -> None:
        if not items:
            return
        with self.lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", list(items.items())
            )
            self.conn.commit()

    def get(self, key: str) -> bytes | None:
        return self.get_many([key]).get(key)

    def put(self, key: str, value: bytes) -> None:
        self.put_many({key: value})


class Embedder:
    """OpenAI embeddings with token-aware batching and a content-hash cache."""

    def __init__(self, model: str = EMBEDDING_MODEL, *, workers: int = 4) -> None:
        import tiktoken

        self.model = model
        self.enc = tiktoken.get_encoding("cl100k_base")
        self.cache = SqliteKV(CACHE_DIR / f"embeddings-{model}.sqlite3")
        self.workers = workers
        self.http = httpx.Client(timeout=httpx.Timeout(120.0))
        self.requests = 0
        self.tokens = 0

    def _truncate(self, text: str) -> list[int]:
        ids = self.enc.encode(text, disallowed_special=())
        return ids[:EMBEDDING_MAX_TOKENS]

    def _post(self, inputs: list[list[int]]) -> list[list[float]]:
        delay = 2.0
        for attempt in range(8):
            try:
                response = self.http.post(
                    OPENAI_EMBEDDINGS,
                    headers={"Authorization": f"Bearer {_openai_key()}"},
                    json={"model": self.model, "input": inputs, "encoding_format": "float"},
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=response.request, response=response)
                response.raise_for_status()
                payload = response.json()
                data = sorted(payload["data"], key=lambda row: row["index"])
                self.requests += 1
                self.tokens += int(payload.get("usage", {}).get("total_tokens", 0))
                return [row["embedding"] for row in data]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                if attempt == 7:
                    raise RuntimeError(f"embedding request failed: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
        raise RuntimeError("unreachable")

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 matrix of unit-normalized embeddings."""
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        keys = [_sha1(self.model, text) for text in texts]
        cached = self.cache.get_many(list(dict.fromkeys(keys)))
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        missing: dict[str, list[int]] = {}
        for index, key in enumerate(keys):
            blob = cached.get(key)
            if blob is not None:
                out[index] = np.frombuffer(blob, dtype=np.float32)
            else:
                missing.setdefault(key, []).append(index)
        if missing:
            unique_keys = list(missing)
            token_lists = {key: self._truncate(texts[missing[key][0]]) for key in unique_keys}
            batches: list[list[str]] = []
            current: list[str] = []
            current_tokens = 0
            for key in unique_keys:
                n_tokens = max(1, len(token_lists[key]))
                if current and (
                    current_tokens + n_tokens > EMBEDDING_BATCH_TOKENS
                    or len(current) >= EMBEDDING_BATCH_ITEMS
                ):
                    batches.append(current)
                    current, current_tokens = [], 0
                current.append(key)
                current_tokens += n_tokens
            if current:
                batches.append(current)

            def run(batch: list[str]) -> dict[str, np.ndarray]:
                vectors = self._post([token_lists[key] or [self.enc.encode(" ")[0]] for key in batch])
                return {key: np.asarray(vec, dtype=np.float32) for key, vec in zip(batch, vectors)}

            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                results = list(pool.map(run, batches))
            fresh: dict[str, bytes] = {}
            for result in results:
                for key, vector in result.items():
                    for index in missing[key]:
                        out[index] = vector
                    fresh[key] = vector.tobytes()
            self.cache.put_many(fresh)
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


class ChatModel:
    """OpenAI chat completions with a persistent exact-prompt cache."""

    def __init__(self) -> None:
        self.cache = SqliteKV(CACHE_DIR / "llm-stages.sqlite3")
        self.http = httpx.Client(timeout=httpx.Timeout(60.0))
        self.calls = 0

    def complete(
        self,
        *,
        rev: str,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        timeout: float,
        seed: int = LLM_SEED,
    ) -> str | None:
        key = _sha1(rev, model, str(seed), system, user)
        cached = self.cache.get(key)
        if cached is not None:
            value = cached.decode("utf-8")
            return value or None
        reply: str | None = None
        delay = 2.0
        for attempt in range(6):
            try:
                response = self.http.post(
                    OPENAI_CHAT,
                    headers={"Authorization": f"Bearer {_openai_key()}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "max_completion_tokens": max_tokens,
                        "temperature": 0.0,
                        "seed": seed,
                    },
                    timeout=timeout,
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=response.request, response=response)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                reply = content.strip() if isinstance(content, str) else None
                self.calls += 1
                break
            except (httpx.HTTPError, KeyError, IndexError, ValueError):
                if attempt == 5:
                    reply = None
                else:
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
        # A failed stage falls back to the incoming order, exactly as in the
        # backend; the failure is cached as empty so repeats stay identical.
        self.cache.put(key, (reply or "").encode("utf-8"))
        return reply


def rrf_fuse(rankings: list[tuple[float, list[str]]], *, k: int = RRF_K) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for weight, ranking in rankings:
        for rank, path in enumerate(ranking, start=1):
            scores[path] = scores.get(path, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class StrongBaselineEngine:
    """Static-retrieval engine implementing one rung of the ladder."""

    def __init__(
        self,
        corpus: Any,
        chunk_cache: Any,
        mode: str,
        *,
        transient_snapshots: bool = True,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
        self.corpus = corpus
        self.chunk_cache = chunk_cache
        self.mode = mode
        self.label = mode
        self.embedder = Embedder()
        self.chat = ChatModel() if mode.startswith("hybrid_rerank") else None
        self.transient_snapshots = transient_snapshots
        self._cross_encoder: Any = None
        self._snapshot_vectors: dict[tuple[str, str], np.ndarray] = {}
        self._current_snapshot: tuple[str, str] | None = None
        self._snapshot_path: Path | None = None
        if mode.startswith("hybrid_rerank"):
            _ = self.cross_encoder  # load before timing any query
        self.stats: dict[str, int] = {
            "expanded": 0,
            "listwise_applied": 0,
            "cross_encoder_applied": 0,
            "embedding_requests": 0,
            "embedding_tokens": 0,
        }

    # ---------------------------------------------------------------- setup
    @property
    def cross_encoder(self) -> Any:
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder

            self._cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
        return self._cross_encoder

    def _enter_snapshot(self, repo: str, commit: str) -> list[dict[str, Any]]:
        from harness.gitcorpus import materialize_snapshot

        key = (repo, commit)
        if self._current_snapshot != key:
            if self.transient_snapshots and self._snapshot_path is not None:
                shutil.rmtree(self._snapshot_path, ignore_errors=True)
            self._snapshot_path = materialize_snapshot(repo, commit, bare_root=self.corpus.bare_root)
            self._snapshot_vectors.pop(self._current_snapshot, None)  # type: ignore[arg-type]
            self._current_snapshot = key
        return self.chunk_cache.get(repo, commit)

    def _vectors(self, key: tuple[str, str], chunks: list[dict[str, Any]]) -> np.ndarray:
        vectors = self._snapshot_vectors.get(key)
        if vectors is None:
            vectors = self.embedder.embed([str(chunk.get("text") or "") for chunk in chunks])
            self._snapshot_vectors[key] = vectors
        return vectors

    # ------------------------------------------------------------- stages
    def _expansion(self, query: str) -> str | None:
        from synsc.services.query_expansion import (
            _PROMPT_REV,
            _SYSTEM_PROMPT,
            looks_like_prose,
            structured_prose_view,
        )

        prose = structured_prose_view(query)
        gate_text = prose if prose is not None else query
        if not looks_like_prose(gate_text):
            return None
        prompt = (prose if prose is not None else query)[:2000]
        assert self.chat is not None
        return self.chat.complete(
            rev=_PROMPT_REV,
            model=EXPANSION_MODEL,
            system=_SYSTEM_PROMPT,
            user=prompt,
            max_tokens=EXPANSION_MAX_TOKENS,
            timeout=EXPANSION_TIMEOUT,
        )

    def _dense_files(
        self, query_text: str, chunks: list[dict[str, Any]], vectors: np.ndarray
    ) -> tuple[list[str], dict[str, str], dict[str, float]]:
        query_vector = self.embedder.embed([query_text])[0]
        scores = vectors @ query_vector
        best_score: dict[str, float] = {}
        best_text: dict[str, str] = {}
        for index in np.argsort(-scores, kind="stable"):
            chunk = chunks[int(index)]
            path = str(chunk.get("path") or "")
            if not path or path in best_score:
                continue
            best_score[path] = float(scores[int(index)])
            best_text[path] = str(chunk.get("text") or "")
        ranked = sorted(best_score, key=lambda p: (-best_score[p], p))
        return ranked, best_text, best_score

    def _bm25_files(self, query: str, chunks: list[dict[str, Any]]) -> list[str]:
        from agent_retrieval_bench.baseline import rank_chunks_bm25_with_scores

        from harness.run_arb import _unique_paths_from_scored

        return _unique_paths_from_scored(rank_chunks_bm25_with_scores(query, chunks))

    def _rerank(self, query: str, fused: list[tuple[str, float]], best_text: dict[str, str]) -> list[str]:
        from synsc.services.listwise_rerank import _PROMPT_REV, _SYSTEM_PROMPT, build_prompt, parse_order

        head = fused[:HYBRID_CANDIDATES]
        top = head[0][1] if head else 1.0
        results = [
            {"file_path": path, "content": best_text.get(path, ""), "similarity": score / top if top else 0.0}
            for path, score in head
        ]
        window = results[:HYBRID_RERANK_K]
        rest = results[HYBRID_RERANK_K:]
        pairs = [(query, row["content"][:4000] or row["file_path"]) for row in window]
        logits = np.asarray(self.cross_encoder.predict(pairs), dtype=np.float64)
        probs = 1.0 / (1.0 + np.exp(-logits))
        for row, prob in zip(window, probs):
            row["similarity"] = RERANKER_BLEND_ALPHA * float(prob) + (1 - RERANKER_BLEND_ALPHA) * float(row["similarity"])
        window.sort(key=lambda row: (-row["similarity"], row["file_path"]))
        self.stats["cross_encoder_applied"] += 1
        results = window + rest

        listwise_head = results[:LISTWISE_K]
        prompt = build_prompt(query, listwise_head, LISTWISE_EXCERPT_CHARS)
        assert self.chat is not None
        reply = self.chat.complete(
            rev=_PROMPT_REV,
            model=LISTWISE_MODEL,
            system=_SYSTEM_PROMPT,
            user=prompt,
            max_tokens=LISTWISE_MAX_TOKENS,
            timeout=LISTWISE_TIMEOUT,
        )
        order = parse_order(reply, len(listwise_head)) if reply else None
        if order is not None:
            listwise_head = [listwise_head[i] for i in order]
            self.stats["listwise_applied"] += 1
        return [row["file_path"] for row in listwise_head + results[LISTWISE_K:]]

    # ------------------------------------------------------------- search
    def search(self, sample: dict[str, Any], query: str, *, limit: int) -> dict[str, Any]:
        repo = str(sample["repo"])
        commit = str(sample["base_commit"])
        started = time.perf_counter()
        meta: dict[str, Any] = {"retrieval_config": self.provenance()}
        try:
            # Index construction (chunking and passage embedding) is amortized
            # setup, as it is for the frozen Delphi stack whose index was built
            # before scoring; latency below covers query-time work only.
            chunks = self._enter_snapshot(repo, commit)
            vectors = self._vectors((repo, commit), chunks)
            meta["index_build_ms"] = (time.perf_counter() - started) * 1000
            meta["chunks"] = len(chunks)
            self.stats["embedding_requests"] = self.embedder.requests
            self.stats["embedding_tokens"] = self.embedder.tokens
            started = time.perf_counter()
            dense_query = query
            if self.mode == "hybrid_rerank_expand":
                expansion = self._expansion(query)
                if expansion:
                    dense_query = f"{query}\n\n{expansion}"
                    self.stats["expanded"] += 1
                meta["query_expanded"] = bool(expansion)
            dense_paths, best_text, _ = self._dense_files(dense_query, chunks, vectors)
            if self.mode == "dense":
                paths = dense_paths[:limit]
            else:
                bm25_paths = self._bm25_files(query, chunks)
                fused = rrf_fuse([(1.0, dense_paths), (1.0, bm25_paths)])
                if self.mode == "hybrid":
                    paths = [path for path, _ in fused[:limit]]
                else:
                    for path, _ in fused[:HYBRID_CANDIDATES]:
                        best_text.setdefault(path, self.corpus.file_text(repo, commit, path) or "")
                    paths = self._rerank(query, fused, best_text)[:limit]
        except Exception as exc:  # noqa: BLE001 - recorded as a technical failure
            return {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "paths": [],
                "latency_ms": (time.perf_counter() - started) * 1000,
                "meta": meta,
            }
        return {
            "status": "ok",
            "paths": paths,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "meta": meta,
        }

    def provenance(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "engine": self.mode,
            "embedding_model": EMBEDDING_MODEL,
            "chunking": "arb-official (file chunk + symbol chunks, max 8000 chars)",
            "file_pooling": "max over chunks",
        }
        if self.mode != "dense":
            config.update({"fusion": "rrf", "rrf_k": RRF_K, "fusion_weights": {"dense": 1.0, "bm25": 1.0}})
        if self.mode.startswith("hybrid_rerank"):
            config.update(
                {
                    "hybrid_candidates": HYBRID_CANDIDATES,
                    "hybrid_rerank_k": HYBRID_RERANK_K,
                    "reranker_model": CROSS_ENCODER_MODEL,
                    "reranker_blend_alpha": RERANKER_BLEND_ALPHA,
                    "listwise_rerank_model": LISTWISE_MODEL,
                    "listwise_rerank_k": LISTWISE_K,
                    "listwise_excerpt_chars": LISTWISE_EXCERPT_CHARS,
                    "llm_seed": LLM_SEED,
                }
            )
        config["query_expansion_enabled"] = self.mode == "hybrid_rerank_expand"
        if self.mode == "hybrid_rerank_expand":
            config["query_expansion_model"] = EXPANSION_MODEL
        return config

    def close(self) -> None:
        if self.transient_snapshots and self._snapshot_path is not None:
            shutil.rmtree(self._snapshot_path, ignore_errors=True)
            self._snapshot_path = None
        self.stats["embedding_requests"] = self.embedder.requests
        self.stats["embedding_tokens"] = self.embedder.tokens
        if self.chat is not None:
            self.stats["chat_calls"] = self.chat.calls
