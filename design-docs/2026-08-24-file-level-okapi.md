# File-level Okapi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, repository-scoped, default-off `file_okapi` candidate source that supplies true file-level BM25 evidence before Delphi fusion and reranking.

**Architecture:** Index code-aware term frequencies and document lengths per repository file in two new PostgreSQL tables, maintained in the existing atomic indexing transaction. Query those rows with canonical Okapi BM25, map each selected file to a deterministic searchable chunk, then align and fuse the signal through the existing optional file-level branch machinery.

**Tech Stack:** Python 3.11, SQLAlchemy 2, PostgreSQL 16, Alembic raw-SQL migrations, Pydantic settings, pytest, Ruff, mypy.

## Global Constraints

- The feature is named `file_okapi` throughout code, configuration, provenance, and tests.
- Default is disabled; disabled, unscoped, stale-index, empty-query, and zero-hit states are behavioral no-ops.
- Use canonical BM25 with fixed `k1=1.2`, `b=0.75`, weight `0.15`, candidate cap `50`, query-term cap `256`, scope cap `50,000`, and index version `v1`.
- Tokenize the prepared retrieval query and files with one code-aware tokenizer: lowercase, split punctuation/path/snake/camel/acronym boundaries, retain 1–128 character non-numeric terms, prepend each path component once.
- Reject a file above 250,000 retained token occurrences; never silently persist partial term statistics.
- Repository access scope is mandatory and never broadens on failure.
- Preserve deterministic total ordering and existing candidate-source alignment behavior.
- Do not modify benchmark harnesses, SDKs, final datasets, Nia, or Context7.
- Follow TDD: every production behavior must first have a focused failing test.

---

### Task 1: Code-aware file document builder

**Files:**
- Create: `backend/synsc/services/file_okapi.py`
- Create: `backend/tests/test_file_okapi.py`

**Interfaces:**
- Produces: `FILE_OKAPI_INDEX_VERSION: str`, `FILE_OKAPI_K1: float`, `FILE_OKAPI_B: float`, `FILE_OKAPI_QUERY_TERM_CAP: int`, `FILE_OKAPI_DOCUMENT_TOKEN_CAP: int`
- Produces: `FileOkapiDocument(document_length: int, term_frequencies: dict[str, int])`
- Produces: `tokenize_file_okapi(value: str, *, limit: int | None = None) -> list[str]`
- Produces: `build_file_okapi_document(file_path: str, content: str) -> FileOkapiDocument`
- Produces: `bm25_term_score(*, term_frequency: int, document_length: int, document_count: int, document_frequency: int, average_document_length: float, k1: float = FILE_OKAPI_K1, b: float = FILE_OKAPI_B) -> float`

- [ ] **Step 1: Write tokenizer and document-builder failures**

Add focused tests:

```python
def test_tokenizer_splits_snake_camel_acronym_and_path_boundaries():
    assert tokenize_file_okapi("src/HTTPServer/get_user.py") == [
        "src", "http", "server", "get", "user", "py"
    ]


def test_document_prepends_path_terms_once_and_counts_source_terms():
    document = build_file_okapi_document(
        "src/user_service.py",
        "class UserService:\n    user = UserService()\n",
    )
    assert document.term_frequencies["src"] == 1
    assert document.term_frequencies["user"] == 4
    assert document.term_frequencies["service"] == 3
    assert document.document_length == sum(document.term_frequencies.values())


def test_document_rejects_more_than_token_cap(monkeypatch):
    monkeypatch.setattr(file_okapi, "FILE_OKAPI_DOCUMENT_TOKEN_CAP", 3)
    with pytest.raises(ValueError, match="token cap"):
        build_file_okapi_document("a.py", "one two three four")
```

- [ ] **Step 2: Run tests and verify the missing-module failure**

Run: `cd backend && .venv/bin/pytest tests/test_file_okapi.py -q`

Expected: collection fails because `synsc.services.file_okapi` does not exist.

- [ ] **Step 3: Implement the minimal tokenizer and document builder**

Create `file_okapi.py` with compiled acronym/camel/token regexes, stable first-occurrence truncation for query terms, a frozen dataclass, and `Counter`-based frequencies. Path tokens are added once before content tokens. Reject numeric-only/out-of-range terms and over-cap documents.

- [ ] **Step 4: Add and verify the hand-calculated BM25 reference**

Add:

```python
def test_bm25_term_score_matches_hand_calculated_reference():
    actual = bm25_term_score(
        term_frequency=3,
        document_length=100,
        document_count=10,
        document_frequency=2,
        average_document_length=80.0,
    )
    expected_idf = math.log(1 + (10 - 2 + 0.5) / (2 + 0.5))
    expected = expected_idf * (3 * 2.2) / (3 + 1.2 * (0.25 + 0.75 * 1.25))
    assert actual == pytest.approx(expected)
```

Run: `cd backend && .venv/bin/pytest tests/test_file_okapi.py -q`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Lint and commit the pure lexical unit**

Run: `cd backend && .venv/bin/ruff check synsc/services/file_okapi.py tests/test_file_okapi.py`

Commit only product code/tests:

```bash
git add backend/synsc/services/file_okapi.py backend/tests/test_file_okapi.py
git commit -m "feat(search): add code-aware Okapi document builder"
```

### Task 2: Persistent schema and atomic indexing

**Files:**
- Create: `backend/alembic/versions/019_file_okapi.py`
- Modify: `backend/synsc/database/connection.py`
- Modify: `backend/synsc/database/models.py`
- Modify: `backend/synsc/services/indexing_service.py`
- Modify: `database/supabase/setup_local.sql`
- Modify: `backend/tests/test_alembic.py`
- Create: `backend/tests/test_file_okapi_indexing.py`
- Modify: `backend/tests/test_atomic_reindex_postgres.py`

**Interfaces:**
- Produces SQLAlchemy models `RepositoryFileLexicalDocument` and `RepositoryFileLexicalTerm`
- Produces repository fields `file_okapi_index_version: str | None` and `file_okapi_documents_count: int`
- Produces `IndexingService._add_file_okapi_rows(session: Session, *, repo_id: str, repository_file: RepositoryFile, file_path: str, content: str, content_hash: str) -> int`

- [ ] **Step 1: Write migration contract failures**

Import `EXPECTED_ALEMBIC_REVISION` from `synsc.database.connection`, then
extend `test_alembic.py` to assert:

```python
def test_file_okapi_migration_is_latest_revision():
    path = PROJECT_ROOT / "alembic" / "versions" / "019_file_okapi.py"
    content = path.read_text()
    assert 'revision: str = "019_file_okapi"' in content
    assert 'down_revision: Union[str, None] = "018_context_sessions"' in content
    assert EXPECTED_ALEMBIC_REVISION == "019_file_okapi"
```

Add assertions that the migration creates both lexical tables, cascading FKs, the `(repo_id, term, file_id)` lookup index, and repository index-version/count columns.

- [ ] **Step 2: Run and verify the migration test fails**

Run: `cd backend && .venv/bin/pytest tests/test_alembic.py -k file_okapi -q`

Expected: failure because migration `019_file_okapi.py` and revision constant do not exist.

- [ ] **Step 3: Add migration, models, and bootstrap parity**

Create an idempotent raw-SQL migration with:

```sql
ALTER TABLE repositories
  ADD COLUMN IF NOT EXISTS file_okapi_index_version VARCHAR(32),
  ADD COLUMN IF NOT EXISTS file_okapi_documents_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS repository_file_lexical_documents (
  file_id VARCHAR(36) PRIMARY KEY REFERENCES repository_files(file_id) ON DELETE CASCADE,
  repo_id VARCHAR(36) NOT NULL REFERENCES repositories(repo_id) ON DELETE CASCADE,
  document_length INTEGER NOT NULL CHECK (document_length > 0),
  content_hash VARCHAR(64) NOT NULL,
  index_version VARCHAR(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS repository_file_lexical_terms (
  file_id VARCHAR(36) NOT NULL REFERENCES repository_files(file_id) ON DELETE CASCADE,
  repo_id VARCHAR(36) NOT NULL REFERENCES repositories(repo_id) ON DELETE CASCADE,
  term VARCHAR(128) NOT NULL,
  term_frequency INTEGER NOT NULL CHECK (term_frequency > 0),
  PRIMARY KEY (file_id, term)
);

CREATE INDEX IF NOT EXISTS idx_file_lexical_terms_scope
ON repository_file_lexical_terms (repo_id, term, file_id);
```

Mirror table/column definitions in `setup_local.sql`, add SQLAlchemy models, relationships with delete-orphan/cascade semantics, and bump `EXPECTED_ALEMBIC_REVISION`.

- [ ] **Step 4: Write indexing-service failures**

In `test_file_okapi_indexing.py`, use a recording fake session and real `RepositoryFile` to assert `_add_file_okapi_rows` adds one document row and exact term rows, returns `1`, and returns `0` for an over-cap document without partial rows.

Add a full-index test asserting repository version/count fields are set after indexing. Extend the PostgreSQL atomic-reindex test seed to include lexical rows and assert a forced failure restores the previous rows and version.

- [ ] **Step 5: Run and verify indexing tests fail for missing behavior**

Run:

`cd backend && .venv/bin/pytest tests/test_file_okapi_indexing.py tests/test_atomic_reindex_postgres.py -k "file_okapi or failed_full_reindex" -q`

Expected: focused unit failures for missing `_add_file_okapi_rows`; PostgreSQL tests may skip if no DB.

- [ ] **Step 6: Implement transactional index writes**

Call `_add_file_okapi_rows` immediately after each `RepositoryFile` is created in both `_index_files` and `_diff_reindex`. Build rows from the in-memory full content; add the document and term rows to the same SQLAlchemy transaction. Rely on file FK cascade for replacement/deletion. Set repository version to `v1` only after all eligible files are processed, and set the exact document count.

Include `file_okapi_documents_count` in returned indexing stats and repository stats responses. A rejected over-cap file remains searchable by existing branches but does not count as a lexical document; log one structured warning.

- [ ] **Step 7: Run schema/indexing verification**

Run:

```bash
cd backend
.venv/bin/pytest tests/test_alembic.py -k file_okapi -q
.venv/bin/pytest tests/test_file_okapi_indexing.py -q
.venv/bin/pytest tests/test_atomic_reindex_postgres.py -q
.venv/bin/ruff check synsc/database/connection.py synsc/database/models.py synsc/services/indexing_service.py tests/test_file_okapi_indexing.py tests/test_atomic_reindex_postgres.py
```

Expected: unit tests pass; integration tests either pass against PostgreSQL or explicitly skip.

- [ ] **Step 8: Commit persistence changes**

```bash
git add backend/alembic/versions/019_file_okapi.py \
  backend/synsc/database/connection.py \
  backend/synsc/database/models.py \
  backend/synsc/services/indexing_service.py \
  database/supabase/setup_local.sql \
  backend/tests/test_alembic.py \
  backend/tests/test_file_okapi_indexing.py \
  backend/tests/test_atomic_reindex_postgres.py
git commit -m "feat(indexing): persist file-level Okapi statistics"
```

### Task 3: Scoped canonical Okapi search

**Files:**
- Modify: `backend/synsc/services/hybrid_retrieval.py`
- Modify: `backend/tests/test_hybrid_retrieval.py`
- Modify: `backend/tests/test_integration_hybrid_search.py`

**Interfaces:**
- Produces: `FILE_OKAPI_WEIGHT = 0.15`, `FILE_OKAPI_MAX_FILES = 50_000`, `FILE_OKAPI_CANDIDATES = 50`
- Produces: `file_okapi_search(session: Session, query: str, user_id: str, repo_ids: list[str] | None = None, language: str | None = None, top_k: int = FILE_OKAPI_CANDIDATES) -> list[Candidate]`

- [ ] **Step 1: Write SQL and fail-closed behavior tests**

Use the existing recording session pattern to assert:

```python
def test_file_okapi_requires_repository_scope():
    session = RecordingSession([])
    assert file_okapi_search(session, "user service", "u1", repo_ids=None) == []
    assert session.calls == []


def test_file_okapi_sql_uses_canonical_formula_scope_and_total_order():
    candidates = file_okapi_search(
        RecordingSession([scope_count_row, candidate_row]),
        "HTTPServer get_user",
        "u1",
        repo_ids=["repo-1"],
        top_k=7,
    )
    sql = session.calls[-1].sql
    assert "LN(1 +" in sql
    assert "document_frequency" in sql
    assert "average_document_length" in sql
    assert "ur.user_id = :user_id" in sql
    assert "r.is_public = TRUE OR r.indexed_by = :user_id" in sql
    assert "ORDER BY score DESC, rf.file_path" in sql
    assert candidates[0].sources["file_okapi"] > 0
```

Add separate tests for stale/missing index version, scope count above 50,000, empty normalized query, language filter, and deterministic best-chunk selection.

- [ ] **Step 2: Run and verify missing search function failures**

Run: `cd backend && .venv/bin/pytest tests/test_hybrid_retrieval.py -k file_okapi -q`

Expected: import or attribute failure because `file_okapi_search` does not exist.

- [ ] **Step 3: Implement the two-query scoped search**

First query validates that every requested accessible repo exists, has version `v1`, and that total lexical documents are at most 50,000. Any mismatch returns `[]`.

Second query uses CTEs for scope documents, scope stats, per-term document frequency, and per-file score:

```sql
SUM(
  LN(1 + (stats.n - term_stats.df + 0.5) / (term_stats.df + 0.5))
  * terms.term_frequency * (:k1 + 1)
  / (
    terms.term_frequency
    + :k1 * (1 - :b + :b * docs.document_length / stats.avgdl)
  )
) AS score
```

Join only explicit `repo_ids` and accessible repositories. Map each file to
the highest `ts_rank_cd` searchable chunk, then order by score descending,
file path, chunk index, repo ID, and chunk ID. Set
`candidate.sources["file_okapi"]`.

- [ ] **Step 4: Add a real-PostgreSQL integration test**

Seed two repositories with lexical documents/terms and chunks. Verify a scoped
query ranks the higher canonical BM25 file first, cannot see an inaccessible
private repository, and produces one chunk per file. Keep the existing
`_postgres_reachable()` skip behavior.

- [ ] **Step 5: Run and commit search behavior**

Run:

```bash
cd backend
.venv/bin/pytest tests/test_hybrid_retrieval.py -k file_okapi -q
.venv/bin/pytest tests/test_integration_hybrid_search.py -k file_okapi -q
.venv/bin/ruff check synsc/services/hybrid_retrieval.py tests/test_hybrid_retrieval.py tests/test_integration_hybrid_search.py
```

Commit:

```bash
git add backend/synsc/services/hybrid_retrieval.py \
  backend/tests/test_hybrid_retrieval.py \
  backend/tests/test_integration_hybrid_search.py
git commit -m "feat(search): add scoped file-level Okapi retrieval"
```

### Task 4: Fusion, configuration, and serving provenance

**Files:**
- Modify: `backend/synsc/config.py`
- Modify: `backend/synsc/services/hybrid_retrieval.py`
- Modify: `backend/synsc/services/search_service.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_hybrid_retrieval.py`
- Modify: `backend/tests/test_search_result_selection.py`

**Interfaces:**
- Produces `SearchConfig.enable_file_okapi: bool`
- Extends `hybrid_retrieve(..., enable_file_okapi: bool = False)`
- Adds `retrieval_config.file_okapi`, `file_okapi_weight`, `file_okapi_candidates`, `file_okapi_index_version`, `file_okapi_k1`, and `file_okapi_b`

- [ ] **Step 1: Write opt-in config failures**

Add:

```python
def test_file_okapi_is_opt_in(monkeypatch):
    monkeypatch.delenv("SYNSC_FILE_OKAPI", raising=False)
    assert SynscConfig.from_env().search.enable_file_okapi is False
    monkeypatch.setenv("SYNSC_FILE_OKAPI", "true")
    assert SynscConfig.from_env().search.enable_file_okapi is True
```

Run: `cd backend && .venv/bin/pytest tests/test_config.py -k file_okapi -q`

Expected: failure because the config field is missing.

- [ ] **Step 2: Implement the config field**

Add `enable_file_okapi: bool = False` to `SearchConfig` and parse
`SYNSC_FILE_OKAPI` with the same accepted truthy strings as the other optional
branches.

- [ ] **Step 3: Write fusion red tests**

Add tests that:

- an enabled branch calls `file_okapi_search`, aligns onto the strongest
  existing chunk from the same file, and sets weight `0.15`;
- a standalone novel file is retained in the rerank window;
- a zero-hit branch does not rescale any existing fused score;
- disabled and unscoped paths do not call the branch.

Run: `cd backend && .venv/bin/pytest tests/test_hybrid_retrieval.py tests/test_search_result_selection.py -k file_okapi -q`

Expected: failures for missing `enable_file_okapi` plumbing and source-diversity registration.

- [ ] **Step 4: Wire branch into hybrid retrieval and selection**

Mirror the existing `file_bm25` branch:

```python
if enable_file_okapi and file_okapi_candidates:
    weights.setdefault("file_okapi", FILE_OKAPI_WEIGHT)
    branches.append(
        _align_file_level_candidates(branches, file_okapi_candidates, "file_okapi")
    )
else:
    weights.pop("file_okapi", None)
```

Add `file_okapi` to timing/source counts, `file_level_sources`, and
incoming-source-aware preservation order. Do not change any behavior when the
branch is disabled.

- [ ] **Step 5: Write and implement provenance red/green**

Extend serving configuration tests to require:

```python
assert config["file_okapi"] is True
assert config["fusion_weights"]["file_okapi"] == 0.15
assert config["file_okapi_candidates"] == 50
assert config["file_okapi_index_version"] == "v1"
assert config["file_okapi_k1"] == 1.2
assert config["file_okapi_b"] == 0.75
```

Disabled or unscoped snapshots must mark `file_okapi=False` and omit its
fusion weight. Wire `SearchService.search_code` to pass the config flag and
emit source hit counts.

- [ ] **Step 6: Run target suite and commit integration**

Run:

```bash
cd backend
.venv/bin/pytest tests/test_config.py tests/test_hybrid_retrieval.py tests/test_search_result_selection.py -q
.venv/bin/ruff check synsc/config.py synsc/services/hybrid_retrieval.py synsc/services/search_service.py tests/test_config.py tests/test_hybrid_retrieval.py tests/test_search_result_selection.py
```

Commit:

```bash
git add backend/synsc/config.py \
  backend/synsc/services/hybrid_retrieval.py \
  backend/synsc/services/search_service.py \
  backend/tests/test_config.py \
  backend/tests/test_hybrid_retrieval.py \
  backend/tests/test_search_result_selection.py
git commit -m "feat(search): integrate the file Okapi candidate source"
```

### Task 5: Product verification and migration smoke

**Files:**
- Modify only if a failing product test exposes a defect in Task 1–4 files.

**Interfaces:**
- Consumes all prior task interfaces.
- Produces a verified product branch; no benchmark artifacts.

- [ ] **Step 1: Apply migration to the local development database**

Run from `backend` with the configured local PostgreSQL:

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

Expected current revision: `019_file_okapi`.

- [ ] **Step 2: Run focused PostgreSQL tests**

```bash
cd backend
.venv/bin/pytest tests/test_atomic_reindex_postgres.py \
  tests/test_integration_hybrid_search.py \
  tests/test_integration_postgres.py -q
```

Expected: all reachable PostgreSQL tests pass; skips state their unavailable
dependency explicitly.

- [ ] **Step 3: Run full backend verification**

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check synsc tests
.venv/bin/mypy synsc
```

Expected: zero test failures, Ruff errors, and mypy errors.

- [ ] **Step 4: Verify disabled baseline contract**

Start the API with `SYNSC_FILE_OKAPI=false`, issue one repository-scoped
search, and assert its `retrieval_config.file_okapi` is false and
`fusion_weights` has no `file_okapi` entry. Do not run any benchmark.

- [ ] **Step 5: Review the complete product diff**

Run:

```bash
git status --short
git diff HEAD~4...HEAD -- backend/synsc backend/tests backend/alembic database
git diff --check HEAD~4...HEAD
```

Confirm no benchmark, SDK, corpus, `new/round3`, secret, local database, or
generated artifact is committed.

### Task 6: Record product state without pushing

**Files:**
- Do not commit local research context, plans, benchmarks, SDKs, run databases,
  corpus snapshots, or generated evidence.

**Interfaces:**
- Produces a clean feature branch with local commits only.

- [ ] **Step 1: Record final product-only status**

Run `git status --short --branch` and `git log -5 --oneline`.

- [ ] **Step 2: Update local durable context**

Record implementation/test facts in the ignored local round-3 context and
Atlas only after verification. Do not claim benchmark improvement; the
development evaluation remains a separate later step.

- [ ] **Step 3: Stop before any push or benchmark**

Leave commits local. Do not push the feature branch, reindex benchmark
corpora, run ARB/independent/final evaluations, or modify any SDK.
