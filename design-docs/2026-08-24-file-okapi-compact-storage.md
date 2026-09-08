# Compact File Okapi Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking.

**Goal:** Replace row-per-term file Okapi persistence with one exact JSONB map per file without changing BM25 ranking.

**Architecture:** Migration 021 losslessly aggregates normalized term rows into JSONB maps and drops the large term table. Indexing writes one document row; retrieval uses GIN key overlap plus `jsonb_each_text` to reconstruct exact term matches before the unchanged BM25 formula.

**Tech Stack:** Python 3.11, SQLAlchemy 2, PostgreSQL 14+, JSONB/GIN, Alembic, pytest.

## Global constraints

- Preserve exact term frequencies, BM25 math, access scope, ordering, provenance, and default-off behavior.
- Migration upgrade and downgrade are lossless.
- Fresh bootstrap creates only compact storage.
- No benchmark, SDK, corpus, or local evidence files are committed.
- Every production change follows red-green TDD.

### Task 1: Compact migration, models, and indexing

**Files:**
- Create `backend/alembic/versions/021_file_okapi_compact.py`
- Modify `backend/synsc/database/connection.py`
- Modify `backend/synsc/database/models.py`
- Modify `backend/synsc/services/indexing_service.py`
- Modify `database/supabase/setup_local.sql`
- Modify schema/indexing tests

- [ ] Add failing migration-contract and round-trip PostgreSQL tests.
- [ ] Add failing indexing tests expecting one JSONB document and no term rows.
- [ ] Implement migration 021 exactly as the design specifies, including lossless downgrade.
- [ ] Replace term model/relationships with `term_frequencies: dict[str, int]`.
- [ ] Simplify indexing to persist one row and remove staged term-row cleanup.
- [ ] Run migration, indexing, atomic reindex, Ruff, and mypy checks.
- [ ] Commit product-only changes.

### Task 2: JSONB-backed exact Okapi search

**Files:**
- Modify `backend/synsc/services/hybrid_retrieval.py`
- Modify unit and real-PostgreSQL hybrid tests

- [ ] Add failing SQL-shape tests for `?|`, GIN-prunable matching documents,
  and `jsonb_each_text`.
- [ ] Extend the real-PostgreSQL fixture to prove exact ranking, language,
  access, and deterministic chunk selection under JSONB.
- [ ] Rewrite only the file-term CTEs; preserve canonical formula,
  pre-limit, provenance metadata, and total order.
- [ ] Run focused unit/PostgreSQL tests, Ruff, and mypy.
- [ ] Commit product-only changes.

### Task 3: Storage and whole-product verification

- [ ] Apply 021 to the isolated test database and prove upgrade/downgrade
  tuple equality.
- [ ] Apply 021 to the interrupted independent development database.
- [ ] Measure compact document-table + GIN size against the old term table
  measurement and record the ratio locally.
- [ ] Run real-PostgreSQL indexing/search suites, full backend pytest, Ruff,
  and mypy.
- [ ] Request whole-change review and fix every Critical/Important finding.
- [ ] Keep the branch local and resume the development reindex only after all
  checks pass.
