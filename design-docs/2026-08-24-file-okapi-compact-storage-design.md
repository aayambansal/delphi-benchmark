# Compact file Okapi storage

## Problem

The first live development reindex proved the row-per-`(file, term)` schema is
not operationally viable. It used 35 MB for 80,435 term rows across only 294
files. That projects to roughly 5 GB for the 44,189-file independent corpus
and roughly 14 GB for the 116,424-file ARB corpus, while the machine has 13 GB
free.

A direct PostgreSQL measurement over 441 indexed files shows their exact term
maps occupy 2.5 MB as JSONB before indexing, about 5.9 KB per file. The storage
problem is row and B-tree overhead, not the lexical data itself.

## Selected representation

Store one exact JSONB term-frequency map on
`repository_file_lexical_documents`:

- `term_frequencies JSONB NOT NULL`;
- every key is one normalized term;
- every value is its positive integer frequency;
- a check requires a non-empty object;
- a default-operator-class GIN index supports key-overlap lookup.

Drop `repository_file_lexical_terms` after migrating existing rows. Keep
`document_length`, `content_hash`, `index_version`, `file_id`, and `repo_id`.

This preserves exact canonical BM25 statistics while eliminating millions of
small rows. Parallel arrays were considered but rejected because JSONB gives a
single self-describing value, straightforward key lookup, and safer migration.
`tsvector` was rejected because exact retained-token frequency and file-level
document frequency would no longer be available without custom parsing.

## Migration

Add migration `021_file_okapi_compact`, chained after
`020_symbol_parent_index`:

1. Add nullable `term_frequencies JSONB`.
2. Backfill each document with
   `jsonb_object_agg(term, term_frequency ORDER BY term)` from the old term
   table.
3. Reject the migration if any document remains null or empty.
4. Set the column `NOT NULL`.
5. Create `idx_file_lexical_term_keys` using GIN.
6. Drop `repository_file_lexical_terms`.

The downgrade recreates the term table and expands JSONB maps back into exact
rows before dropping the JSONB column. Fresh bootstrap SQL creates only the
compact schema.

## Indexing

`_add_file_okapi_rows` adds one lexical document ORM row whose
`term_frequencies` is the exact deterministic dictionary produced by
`build_file_okapi_document`. Remove term-row ORM construction and staged-term
flush/expunge machinery.

Atomic initial, diff, full, and local force reindex behavior remains
unchanged. File deletion still cascades through the document's `file_id` FK.

## Search

For explicit accessible `repo_ids`:

1. Build `scope_docs` from all version-matched lexical documents. Use it for
   scope-wide `N` and average document length.
2. Build `matching_docs` with
   `term_frequencies ?| CAST(:query_terms AS text[])`, allowing the GIN index
   to prune files with no query-term key.
3. Expand only matching maps with
   `jsonb_each_text(term_frequencies)`.
4. Keep rows whose key is in `:query_terms`; cast each value to integer.
5. Compute document frequency and canonical BM25 from those exact matches.
6. Preserve the existing pre-limit, chunk selection, total ordering, access
   checks, configured/effective provenance, and warning semantics.

No approximation, stemming, benchmark-specific rule, or score change is
allowed.

## Verification gates

- Round-trip migration preserves every `(file_id, term, frequency)` tuple.
- Hand-calculated BM25 rankings match the old normalized schema.
- Multi-repository, language, access, stale-index, zero-overlap, and top-50
  contracts remain green on real PostgreSQL.
- Atomic rollback and local stable-ID reindex tests remain green.
- The 441-file live sample's compact document table plus GIN index must be
  materially smaller than the old term table and index.
- Full backend tests, Ruff, and mypy must pass.
- No development benchmark resumes until the compact migration is applied and
  the interrupted partial reindex is cleaned or replaced.
