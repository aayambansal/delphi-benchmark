"""Build seeded SWE-bench Verified datasets for the executable agent pilot.

Each condition writes a local dataset directory (``<out>/<condition>/test.jsonl``)
that ``mini-extra swebench --subset <dir> --split test`` can load. The only
field that differs between conditions is ``problem_statement``: seeded
conditions append a ``<retrieved_context>`` block listing the top files a
recorded retrieval run ranked for the same instance, each with the head of the
file at the instance's base commit. The block is identical in shape across
engines so that any difference in outcome is attributable to which files were
named, not to prompt formatting.

Conditions:
  none        the official problem statement, unchanged
  random      the same block with files drawn at random from the candidate
              set (excluding gold), the ARB-style prompting control
  <run-id>    the block built from ``results/<run-id>-details.jsonl``

The agent keeps its ordinary tools in every condition; the seed is a hint, not
a restriction. Gold files are used only to exclude them from the random arm.

Seed styles (``--seed-style``), added for the round-4 seed-interface check:
  heads       path plus the first ``--head-lines`` lines of the file (pilot default)
  paths       path only, no file content
  chunks      path plus the file's best-matching ARB chunk for the issue text
              under BM25 (a symbol chunk where one exists), capped at
              ``--chunk-lines`` lines; the same total token budget applies
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tiktoken  # noqa: E402

from harness.gitcorpus import BARE, GitCorpus  # noqa: E402

_ENC = tiktoken.get_encoding("cl100k_base")

INTRO = (
    "A code search engine retrieved the following repository files as potentially "
    "relevant to this issue, best match first. Treat them as hints and verify them "
    "with your own tools; the fix may involve other files."
)


def load_verified(cache: Path) -> dict[str, dict]:
    import pyarrow.parquet as pq

    rows = pq.read_table(io.BytesIO(cache.read_bytes())).to_pylist()
    return {str(r["instance_id"]): r for r in rows}


def file_head(corpus: GitCorpus, repo: str, commit: str, path: str, lines: int) -> str:
    text = corpus.file_text(repo, commit, path)
    if not text:
        return ""
    return "\n".join(text.splitlines()[:lines])


def best_chunk(
    chunks_by_path: dict[str, list[dict]],
    path: str,
    query: str,
    *,
    max_lines: int,
) -> tuple[str, int, int] | None:
    """The file's best-matching ARB chunk for the query under BM25.

    Symbol chunks are preferred over the whole-file chunk so that the seed
    carries the query-relevant region rather than the file header. Returns
    (text, start_line, end_line) or None when the file has no chunks.
    """
    from agent_retrieval_bench.baseline import rank_chunks_bm25_with_scores

    chunks = chunks_by_path.get(path) or []
    if not chunks:
        return None
    symbols = [c for c in chunks if c.get("kind") == "symbol"] or chunks
    ranked = rank_chunks_bm25_with_scores(query, symbols)
    _, chunk = ranked[0]
    lines = str(chunk.get("text") or "").splitlines()
    start = int(chunk.get("start_line") or 1)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    return "\n".join(lines), start, start + max(0, len(lines) - 1)


def seed_block(
    corpus: GitCorpus,
    repo: str,
    commit: str,
    paths: list[str],
    *,
    head_lines: int,
    token_budget: int,
    style: str = "heads",
    query: str = "",
    chunks_by_path: dict[str, list[dict]] | None = None,
    chunk_lines: int = 60,
) -> tuple[str, list[str]]:
    parts = [f"<retrieved_context>\n{INTRO}\n"]
    used: list[str] = []
    tokens = len(_ENC.encode(parts[0]))
    for path in paths:
        if style == "paths":
            section = f"\n### {path}\n"
        elif style == "chunks":
            found = best_chunk(chunks_by_path or {}, path, query, max_lines=chunk_lines)
            if found is None:
                head = file_head(corpus, repo, commit, path, head_lines)
                section = f"\n### {path} (lines 1-{min(head_lines, len(head.splitlines()) or 1)})\n{head}\n"
            else:
                text, start, end = found
                section = f"\n### {path} (lines {start}-{end})\n{text}\n"
        else:
            head = file_head(corpus, repo, commit, path, head_lines)
            section = f"\n### {path} (lines 1-{min(head_lines, len(head.splitlines()) or 1)})\n{head}\n"
        cost = len(_ENC.encode(section))
        if tokens + cost > token_budget:
            section = f"\n### {path}\n"
            cost = len(_ENC.encode(section))
            if tokens + cost > token_budget:
                break
        parts.append(section)
        used.append(path)
        tokens += cost
    parts.append("</retrieved_context>\n")
    return "".join(parts), used


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True, help="samples jsonl (repo, base_commit, id, gold)")
    parser.add_argument("--instances", type=Path, required=True, help="file with one instance_id per line")
    parser.add_argument("--condition", required=True, help="none | random | <run-id whose details supply top_files>")
    parser.add_argument("--label", default=None, help="output directory name (default: condition)")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--head-lines", type=int, default=40)
    parser.add_argument("--seed-style", choices=("heads", "paths", "chunks"), default="heads")
    parser.add_argument("--chunk-lines", type=int, default=60)
    parser.add_argument("--token-budget", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=1042)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "pilot" / "datasets")
    parser.add_argument("--verified-cache", type=Path, default=ROOT / "cache" / "swebench_verified.parquet")
    args = parser.parse_args()

    verified = load_verified(args.verified_cache)
    cases = {str(r["id"]): r for r in (json.loads(l) for l in args.cases.open() if l.strip())}
    wanted = [line.strip() for line in args.instances.open() if line.strip()]
    corpus = GitCorpus(bare_root=BARE)

    ranked: dict[str, list[str]] = {}
    if args.condition not in ("none", "random"):
        details = ROOT / "results" / f"{args.condition}-details.jsonl"
        for line in details.open():
            if line.strip():
                row = json.loads(line)
                ranked[str(row["sample_id"])] = list(row.get("top_files") or [])

    label = args.label or args.condition
    out_dir = args.out / label
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    with (out_dir / "test.jsonl").open("w") as fh:
        for iid in wanted:
            base = verified[iid]
            case = cases[iid]
            repo, commit = str(case["repo"]), str(case["base_commit"])
            gold = set((case.get("gold") or {}).get("files") or [])
            statement = str(base["problem_statement"])
            used: list[str] = []
            chunks_by_path: dict[str, list[dict]] = {}
            if args.seed_style == "chunks" and args.condition != "none":
                from harness.run_arb import ChunkCache

                if not hasattr(main, "_chunk_cache"):
                    main._chunk_cache = ChunkCache(corpus, max_snapshots=1)  # type: ignore[attr-defined]
                for chunk in main._chunk_cache.get(repo, commit):  # type: ignore[attr-defined]
                    chunks_by_path.setdefault(str(chunk.get("path")), []).append(chunk)
            seed_kwargs = dict(
                head_lines=args.head_lines,
                token_budget=args.token_budget,
                style=args.seed_style,
                query=statement,
                chunks_by_path=chunks_by_path,
                chunk_lines=args.chunk_lines,
            )
            if args.condition == "random":
                from agent_retrieval_bench.corpus import is_candidate_path

                candidates = [p for p in corpus.list_files(repo, commit) if is_candidate_path(p) and p not in gold]
                rng = random.Random(int(hashlib.sha256(f"{args.seed}|{iid}".encode()).hexdigest(), 16))
                paths = rng.sample(candidates, min(args.k, len(candidates)))
                block, used = seed_block(corpus, repo, commit, paths, **seed_kwargs)
                statement = f"{statement}\n\n{block}"
            elif args.condition != "none":
                paths = ranked.get(iid, [])[: args.k]
                block, used = seed_block(corpus, repo, commit, paths, **seed_kwargs)
                statement = f"{statement}\n\n{block}"
            row = dict(base)
            row["problem_statement"] = statement
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            manifest.append(
                {
                    "instance_id": iid,
                    "condition": label,
                    "seed_style": args.seed_style,
                    "seed_files": used,
                    "seed_hits_gold": sorted(gold & set(used)),
                    "gold_files": sorted(gold),
                    "statement_tokens": len(_ENC.encode(statement)),
                }
            )
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    hits = sum(1 for m in manifest if m["seed_hits_gold"])
    print(json.dumps({"condition": label, "instances": len(manifest), "seed_any_gold": hits, "out": str(out_dir)}))


if __name__ == "__main__":
    main()
