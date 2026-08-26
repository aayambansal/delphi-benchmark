"""Track B: embedding-level determinism.

For each provider, embed the same texts N times and measure:
  - bitwise-equality rate across repeats,
  - max pairwise cosine distance across repeats,
  - downstream ranking jitter: top-10 nearest-neighbour sets over a fixed
    candidate matrix when only the query embedding is re-requested.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from harness.gitcorpus import GitCorpus  # noqa: E402
from harness.runstore import RunWriter  # noqa: E402


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class OpenAIEmbedder:
    def __init__(self, model: str) -> None:
        self.model = model
        self.key = os.environ["OPENAI_API_KEY"]
        self.http = httpx.Client(timeout=120)

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.http.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"model": self.model, "input": texts, "encoding_format": "float"},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [row["embedding"] for row in sorted(data, key=lambda r: r["index"])]


class GeminiEmbedder:
    def __init__(self, model: str = "gemini-embedding-001") -> None:
        self.model = model
        self.key = os.environ["GOOGLE_API_KEY"]
        self.http = httpx.Client(timeout=120)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), 50):
            batch = texts[start:start + 50]
            for attempt in range(5):
                resp = self.http.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents",
                    params={"key": self.key},
                    json={"requests": [
                        {"model": f"models/{self.model}",
                         "content": {"parts": [{"text": t[:8000]}]}}
                        for t in batch
                    ]},
                )
                if resp.status_code == 429:
                    time.sleep(10 * (attempt + 1))
                    continue
                resp.raise_for_status()
                break
            out.extend(e["values"] for e in resp.json()["embeddings"])
        return out


class LocalEmbedder:
    """sentence-transformers, loaded in-process (requires backend venv)."""

    def __init__(self, model: str, device: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.st = SentenceTransformer(model, device=device)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.st.encode(texts, batch_size=8)]


def build_texts() -> list[dict]:
    corpus = GitCorpus()
    texts: list[dict] = []
    listing = corpus.list_files("caddyserver/caddy", "ca0ca67fbdb831c026d334dfd77ecc653f321876")
    picked = [p for p in listing if p.endswith(".go")][:8]
    for path in picked:
        body = corpus.file_text("caddyserver/caddy", "ca0ca67fbdb831c026d334dfd77ecc653f321876", path) or ""
        texts.append({"id": f"code:{path}", "text": body[:4000]})
    texts.append({"id": "short", "text": "fix the TLS handshake timeout"})
    texts.append({"id": "prose", "text": "The indexing worker retries transient embedding "
                  "failures with exponential backoff before marking the source as failed."})
    texts.append({"id": "query-json", "text": json.dumps({
        "intent": "find root cause", "failure_excerpt": "panic: nil pointer in reload",
        "command": "go test ./..."}, sort_keys=True)})
    texts.append({"id": "unicode", "text": "def résumé_parser(データ): return 'ok' — emoji test"})
    return texts


def build_candidates(n: int = 200) -> list[str]:
    corpus = GitCorpus()
    commit = "ca0ca67fbdb831c026d334dfd77ecc653f321876"
    out = []
    for path in corpus.list_files("caddyserver/caddy", commit):
        if not path.endswith(".go"):
            continue
        text = corpus.file_text("caddyserver/caddy", commit, path) or ""
        for start in range(0, min(len(text), 12000), 3000):
            out.append(f"{path}\n{text[start:start+2500]}")
            if len(out) >= n:
                return out
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True,
                        choices=("openai-small", "openai-large", "gemini", "local-mpnet", "local-minilm"))
    parser.add_argument("--repeats", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    if args.provider == "openai-small":
        embedder = OpenAIEmbedder("text-embedding-3-small")
    elif args.provider == "openai-large":
        embedder = OpenAIEmbedder("text-embedding-3-large")
    elif args.provider == "gemini":
        embedder = GeminiEmbedder()
    elif args.provider == "local-mpnet":
        embedder = LocalEmbedder("sentence-transformers/all-mpnet-base-v2", args.device)
    else:
        embedder = LocalEmbedder("sentence-transformers/all-MiniLM-L6-v2", args.device)

    texts = build_texts()
    writer = RunWriter(
        track="B-determinism-embedding",
        system=args.provider,
        config={"repeats": args.repeats, "n_texts": len(texts), "device": args.device},
        split="determinism",
    )
    print(f"run_id={writer.run_id}", flush=True)

    # candidate matrix embedded once (for ranking-jitter measurement)
    candidates = build_candidates()
    cand_vecs = embedder.embed(candidates)

    per_text: list[dict] = []
    for item in texts:
        repeats: list[list[float]] = []
        for _ in range(args.repeats):
            repeats.append(embedder.embed([item["text"]])[0])
            time.sleep(0.05)
        exact = 0
        pairs = 0
        max_dist = 0.0
        for a, b in itertools.combinations(range(len(repeats)), 2):
            pairs += 1
            if repeats[a] == repeats[b]:
                exact += 1
            dist = 1.0 - cosine(repeats[a], repeats[b])
            max_dist = max(max_dist, dist)
        # ranking jitter: top-10 by cosine for each repeat
        toplists: list[tuple[int, ...]] = []
        for vec in repeats:
            scored = sorted(range(len(cand_vecs)),
                            key=lambda i: (-cosine(vec, cand_vecs[i]), i))
            toplists.append(tuple(scored[:10]))
        ref = set(toplists[0])
        jaccards = [len(ref & set(t)) / len(ref | set(t)) for t in toplists[1:]]
        identical_lists = sum(1 for t in toplists[1:] if t == toplists[0])
        metrics = {
            "exact_equal_rate": exact / pairs,
            "max_cosine_distance": max_dist,
            "top10_jaccard_mean": (sum(jaccards) / len(jaccards)) if jaccards else 1.0,
            "top10_identical_rate": identical_lists / max(1, len(toplists) - 1),
        }
        per_text.append({"id": item["id"], **metrics})
        writer.case(case_id=item["id"], workflow="embedding", ok=True,
                    metrics=metrics, trace={"n_repeats": args.repeats,
                                            "dim": len(repeats[0])})
        print(json.dumps({"text": item["id"], **{k: round(v, 6) for k, v in metrics.items()}}),
              flush=True)

    agg = {
        "exact_equal_rate": sum(r["exact_equal_rate"] for r in per_text) / len(per_text),
        "max_cosine_distance": max(r["max_cosine_distance"] for r in per_text),
        "top10_jaccard_mean": sum(r["top10_jaccard_mean"] for r in per_text) / len(per_text),
        "top10_identical_rate": sum(r["top10_identical_rate"] for r in per_text) / len(per_text),
        "dim": len(cand_vecs[0]),
    }
    writer.finish(agg)
    (ROOT / "results" / f"{writer.run_id}-summary.json").write_text(
        json.dumps({"provider": args.provider, "aggregate": agg, "per_text": per_text},
                   indent=2, sort_keys=True) + "\n")
    print(json.dumps({"provider": args.provider, **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in agg.items()}}), flush=True)


if __name__ == "__main__":
    main()
