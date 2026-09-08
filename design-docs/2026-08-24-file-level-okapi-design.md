# File-level Okapi candidate branch

## Objective

Add one product-real, default-off file-level lexical candidate source to
Delphi. The branch should recover files whose evidence is distributed across a
whole file and therefore never enters the current chunk-level candidate pool.
It must not encode benchmark cases, reserve final-list slots, or change
behavior while disabled.

The motivating development diagnostic contains five files found by whole-file
BM25 but missed by current Delphi at rank 20. Three remain absent when Delphi
returns 100 results; two appear only as vector candidates at ranks 40 and 42.
Whole-file BM25 ranks all five between 3 and 19. This establishes a
candidate-generation gap, not an adoption result.

## Considered approaches

### Persistent file-level Okapi index — selected

Maintain normalized file-term statistics alongside each indexed repository and
score scoped files with canonical BM25 before Delphi's existing fusion and
reranking stages.

This is the only option that is product-real, deterministic, query-efficient,
and faithful to whole-file BM25. It requires a schema migration and one
development-corpus reindex.

### Query-time aggregation over chunks — rejected

Aggregate existing chunk search rows by file for every query. This avoids a
reindex, but it remains sensitive to chunk boundaries, cannot reproduce true
file-level document frequency and length normalization cheaply, and adds
unbounded query latency.

### Offline sidecar index — rejected for adoption

Build an evaluator-only lexical index. This is useful as a comparator but
cannot support a Delphi product claim because the serving system would not
contain the tested retrieval behavior.

## Storage model

Add two repository-scoped tables:

1. `repository_file_lexical_documents`
   - `file_id` primary key and cascading foreign key to `repository_files`
   - `repo_id`, indexed
   - `document_length`
   - `content_hash`
   - `index_version`
2. `repository_file_lexical_terms`
   - `repo_id`
   - `file_id`
   - `term`
   - `term_frequency`
   - unique key on `(file_id, term)`
   - lookup index on `(repo_id, term, file_id)`

For the normalized terms in a query, document frequency is computed from the
indexed term rows across the explicit `repo_ids` scope. Scope-wide document
count and average document length come from the document table, so scores stay
comparable when a request intentionally includes multiple repositories.

The implementation uses canonical Okapi BM25:

`idf = ln(1 + (N - df + 0.5) / (df + 0.5))`

`score = sum(idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl)))`

Pin `k1=1.2` and `b=0.75`. Do not tune either value on benchmark outcomes.

## Tokenization

Use one versioned, code-aware tokenizer for source files and queries:

- lowercase Unicode text;
- split path separators, punctuation, snake case, camel case, and acronym
  boundaries;
- prepend each path component once, then retain normalized source identifier
  components;
- ignore numeric-only terms and terms outside 1--128 characters;
- consume Delphi's existing prepared retrieval query, deduplicate normalized
  terms in first-occurrence order, keep the first 256 terms, and reject an
  index document above 250,000 retained token occurrences rather than silently
  indexing a partial document;
- contain no repository-, workflow-, or benchmark-specific vocabulary.

Document length is the count of retained token occurrences. Term frequency is
stored exactly for each retained term.

## Index lifecycle

Lexical document and term rows are built as part of repository indexing.
Publish them atomically with repository files and chunks. A failed or cancelled
index operation must leave the previous searchable revision intact.

Reindexing must:

- replace old lexical rows without duplicates;
- delete lexical rows when their repository file is deleted;
- preserve current large-file and parser safety exclusions;
- report indexed lexical document and term counts;
- mark the lexical index version in source metadata.

The branch fails closed when any requested repository lacks a complete matching
index version. It never falls back to an account-wide scan.

## Retrieval flow

Add a source named `file_okapi`:

1. Require hybrid retrieval and explicit `repo_ids`.
2. Normalize at most 256 unique terms from the prepared retrieval query.
3. Score only searchable files in the requested repositories.
4. Return at most 50 files, ordered by score descending and normalized path
   ascending.
5. Map each file to its best searchable chunk with `ts_rank_cd` over the
   existing chunk `content_tsv` and an English plain-text query built from the
   normalized terms. Break ties by chunk index and chunk ID; use the
   deterministic first chunk only when no chunk has lexical overlap.
6. Align file-level agreement onto an existing candidate from the same file;
   otherwise contribute the selected chunk as a standalone candidate.
7. Enter weighted RRF as `file_okapi` with one fixed weight, `0.15`.
8. Preserve one standalone novel-file candidate in the source-diverse rerank
   window, using the existing incoming-source-aware replacement invariant.

The branch is disabled by default. A disabled, unscoped, incomplete, or
zero-hit branch is a behavioral no-op and does not enter the fusion
denominator.

## Configuration and provenance

Add explicit settings for:

- enable flag, default `false`;
- weight, fixed to `0.15` for this experiment;
- candidate cap, fixed to `50`;
- tokenizer/index version;
- `k1` and `b`.

Every code-search response reports whether the branch effectively executed,
its effective weight, candidate count, index version, `k1`, and `b`. The
benchmark runner must fail on the first mismatch with its declared expected
configuration.

## Failure handling

- Missing or stale lexical index: return no branch candidates, emit a warning,
  and report the branch inactive.
- Scope above 50,000 searchable files: fail the branch closed rather than
  score a biased partial set.
- Invalid or empty normalized query: true no-op.
- Failed index transaction: retain the previous complete searchable revision.
- Access-control mismatch: reject before lexical scoring.

No failure mode may broaden repository scope or silently change fusion
weights.

## Test strategy

Develop test-first. Required regressions cover:

- tokenizer punctuation, snake, camel, and acronym boundaries;
- BM25 scores against a small hand-calculated reference corpus;
- deterministic score/path ordering;
- repository scope and private-repository access control;
- atomic initial index, reindex, failure rollback, and deletion;
- skipped and chunkless files;
- disabled, unscoped, stale-index, empty-query, and zero-hit no-op behavior;
- fixed-weight provenance and no fusion rescaling;
- aligned agreement plus standalone novel-file preservation;
- configuration mismatch rejection in the benchmark harness.

Run the focused retrieval/indexing suites, full backend suite, lint, database
integrity audit, source manifest audit, and gold-path searchability audit.

## Development-only evaluation gate

The locked final partitions remain untouched.

1. Reindex the 48-case independent development corpus and the 75-case ARB
   development corpus with lexical documents.
2. With `file_okapi` disabled, rerun current exact Delphi and require exact
   equality with the existing top-20 results. Abort if indexing changes
   baseline behavior.
3. Run one config-attested candidate arm with `file_okapi=true`, weight `0.15`,
   API `top_k=20`, exact vectors, and all other settings unchanged.
4. Repeat the candidate arm and require exact metric rows and top-20 lists.

Adopt only if these common conditions hold on each development corpus:

- zero any-gold losses versus current;
- no negative Recall@20 point change;
- repository-cluster 95% lower bounds for MRR and BCY deltas are at least
  `-0.01`;
- warm median latency increases by no more than 20%;
- all serving configuration, source, chunk, embedding, and gold-path checks
  pass.

ARB has one additional condition: at least two newly acquired cases from the
five-case diagnostic.

If any gate fails, retain exact/current, leave `file_okapi` default-off, record
the negative result, and freeze retrieval development again. Do not tune a
second weight, `k1`, `b`, candidate cap, or quota after seeing outcomes.

## Non-goals

- No final-list lexical reserve.
- No benchmark-specific rules or vocabulary.
- No Nia or Context7 calls.
- No final or confirmatory queries.
- No broad refactor of the existing hybrid pipeline.
