# Nia capability audit

Audited: 2026-07-29 against the public Nia API OpenAPI document
(`Nia AI API` version `1.1.0`) and public Nia documentation.

This document describes exposed capabilities, not benchmark quality. The live
implementation is proprietary and its server revision is opaque.

## Product shape

Nia is not one retriever. Its public surface combines:

1. indexed, source-scoped hybrid retrieval;
2. LLM synthesis over retrieved evidence;
3. repository tree, grep, and source-content inspection;
4. ephemeral filesystem/sandbox operations;
5. autonomous GitHub investigation (Tracer);
6. package-source search without first creating a normal project index;
7. synchronized heterogeneous sources and reusable contexts.

The benchmark must therefore keep raw ranking, context production, and
interactive investigation separate. Treating a synthesized answer as a ranked
file list would be invalid; treating Nia as vector search alone would
understate the product.

## Exposed capabilities

| Capability | Live public surface | Relevant behavior |
|---|---|---|
| Scoped repository search | `POST /v2/search`, mode `query` | Accepts repository selectors; can return raw sources or synthesize an answer |
| Retrieval modes | `reasoning_strategy` | `vector`, tree-guided, or hybrid |
| Raw versus synthesis | `skip_llm`, `fast_mode`, `include_sources` | Raw scored evidence can be isolated from model processing |
| Token budget | `max_tokens` | Server truncates results to a declared response budget |
| Source lifecycle | `/v2/sources` | Repositories can be pinned by branch/ref; sources expose status, sync, tree, grep, and content |
| Repository inspection | `/v2/sources/{id}/tree`, `/grep` | Exact structure and lexical inspection complement semantic search |
| Filesystem namespace | `/v2/fs/{id}/ls`, `/tree`, `/find`, `/grep`, `/read`, `/exec` | Sandbox-style agentic inspection; the command surface is materially broader than static retrieval |
| Symbol expansion | `expand_symbols` in universal search | Extracts functions/classes from hits and searches usages |
| Package source | `/v2/packages/search`, `/grep`, `/read` | Hybrid source search for crates.io, Go proxy, npm, PyPI, and RubyGems packages |
| GitHub Tracer | `/v2/github/tracer` | Autonomous repository research in fast or deep mode |
| Other sources | source type enum | Documentation, papers, Hugging Face datasets, local folders, Slack, Google Drive, and connectors |
| Context memory | `/v2/contexts` and search endpoints | Saved contexts can be created, updated, searched, and reused |
| Scoping | source-scoped search and scoped MCP documentation | Reduces unrelated tool/source exposure for an agent |
| Freshness | source sync and global-source refresh surfaces | Indexed sources can be refreshed rather than treated as immutable uploads |

## Search controls observed in the API contract

The scoped query request accepts repositories, data sources, local folders,
Slack workspaces, source trust filters, and search-mode selection. It exposes:

- `fast_mode` for a low-latency path;
- `skip_llm` for raw results;
- `reasoning_strategy` (`vector`, `tree`, `hybrid`);
- a synthesis-model override;
- cache bypass and cache-similarity threshold;
- a response token budget.

Universal search separately exposes a vector/BM25 blend (`alpha`), source-type
and language boosts, native full-text boosting, and optional symbol expansion.
Because universal search is cross-source rather than exact-repository scoped,
it is not the primary ARB interface.

## Delphi comparison

Delphi already exposes several matching primitives:

- exact-revision repository indexing and immutable source snapshots;
- vector, PostgreSQL full-text, symbol, path, and trigram retrieval;
- cross-encoder reranking and MMR;
- repository tree, regex grep, file reads, and 32-way batch reads;
- symbol lookup, callers, callees, and blast-radius traversal;
- agent-ready context packs with related tests/docs/configs and token packing;
- documentation, papers, datasets, connectors, Atlas graphs, and durable
  context sessions;
- local/self-hosted deployment with inspectable ranking code.

The material product gaps are:

1. **No unified repository-investigation policy.** Delphi exposes strong tools
   but generally leaves query decomposition and iterative inspection to the
   calling agent. Nia packages more of that behavior behind search, sandbox,
   and Tracer surfaces.
2. **No package-registry source search equivalent.** Delphi indexes repositories
   and docs but does not expose zero-setup source lookup across common package
   registries.
3. **Weak abstention contract.** Delphi’s dynamic similarity cutoff can return
   an empty ranking, but the product has no explicit calibrated, explainable
   repository-context abstention response.
4. **Context-pack evidence is not the default search contract.** Delphi’s
   richer pack and graph tools are separate from ordinary code search, which
   makes one-shot clients miss useful structure.
5. **Ranking consistency across workflow types is unproven.** The previous
   trace-only audit showed competitive sample-weighted recall but weaker
   repository-macro early-rank and budgeted yield.
6. **Package/freshness/product integration needs direct measurement.** API
   presence alone does not establish correctness, freshness, latency, or
   downstream developer utility.

## Benchmark implications

Round two uses four distinct evaluations:

- raw source ranking (`skip_llm`/equivalent);
- best 8k context product;
- explicit selective retrieval/abstention;
- a fixed closed-tool developer policy seeded by each engine.

This prevents three common category errors:

- scoring answer prose as if it were a stable ranking;
- awarding unsupported product/task combinations a zero;
- claiming developer utility from retrieval contact without a controlled
  policy or executable/trajectory outcome.

