# Native Delphi workstream journal

Date: 2026-08-24 (America/Los_Angeles)

## Scope and guards

- This workstream read the authoritative `STATE.md`, `HYPOTHESES.md`,
  `EXPLORATION.md`, and `DECISIONS.md` before acting. It did not edit them.
- Every corpus command used only
  `corpus/independent/v1/development.jsonl`.
- Neither the independent final split nor the ARB final split was opened,
  provisioned, or scored.
- Docker was not reset or used. The native Homebrew PostgreSQL 14 server was
  used throughout.
- All scored runs required 48/48 cases with `status=ok`, zero technical
  failures, and zero unprovisioned cases.

## Native stack

The isolated database is
`delphi_native_independent_dev_20260824` on `127.0.0.1:5432`.
`pgvector` is installed, Alembic is at `018_context_sessions`, and the HNSW
index `idx_embeddings_vector` exists with `m=16, ef_construction=64`.

Database initialization:

```bash
createdb delphi_native_independent_dev_20260824
psql -X -q -v ON_ERROR_STOP=1 \
  -d delphi_native_independent_dev_20260824 \
  -f database/supabase/setup_local.sql
(
  cd backend
  DATABASE_URL="postgresql://$USER@127.0.0.1:5432/delphi_native_independent_dev_20260824" \
    .venv/bin/alembic upgrade head
)
```

The first verbose `setup_local.sql` invocation returned 255 after producing
large idempotent output. The quiet `ON_ERROR_STOP` rerun and Alembic upgrade
completed successfully.

Long-lived baseline services:

- API PID `24642`, `127.0.0.1:28742`, still running and healthy. This is the
  controlled restart after retrieval-config provenance was added; the original
  PID `6759` exited cleanly.
- Worker PID `6765`, four threads, still running.
- Database: `delphi_native_independent_dev_20260824`.
- Cache:
  `results/native-delphi-stage-cache.sqlite3`.
- Temporary directory: `/tmp/native-delphi-independent-dev`.

The API was launched with the secret environment loaded from
`new/round3/stack/r3-secrets.env` (secret values are intentionally not copied
here) and these experiment controls:

```bash
set -a
source new/round3/stack/r3-secrets.env
set +a
export DATABASE_URL="postgresql://$USER@127.0.0.1:5432/delphi_native_independent_dev_20260824"
export SYNSC_API_HOST=127.0.0.1
export SYNSC_API_PORT=28742
export SYNSC_LOG_FORMAT=json
export SERVER_SECRET=native-delphi-session-secret-local-only
export SYSTEM_PASSWORD=native-delphi-admin
export EMBEDDING_PROVIDER=openai
export OPENAI_EMBEDDING_MODEL=text-embedding-3-small
export SYNSC_RATE_LIMIT_SEARCH=10000/minute
export SYNSC_RATE_LIMIT_INDEX=10000/minute
export SYNSC_ENABLE_RERANKER=true
export SYNSC_USE_CODE_RERANKER=false
export RERANKER_BLEND_ALPHA=0.4
export SYNSC_HYBRID_CANDIDATES=50
export SYNSC_HYBRID_RERANK_K=30
export SYNSC_QUERY_EXPANSION=true
export SYNSC_LISTWISE_RERANK=true
export SYNSC_LISTWISE_RERANK_MODEL=gpt-4o
export SYNSC_LISTWISE_RERANK_K=20
export SYNSC_LLM_SEED=1042
export SYNSC_LLM_CACHE_ENTRIES=2048
export SYNSC_LLM_CACHE_DB="$PWD/new/round3/results/native-delphi-stage-cache.sqlite3"
export SYNSC_HNSW_EF_SEARCH=100
export SYNSC_VECTOR_EXACT_SCAN=true
export SYNSC_FILE_DIVERSE_BM25=false
export SYNSC_TEMP_DIR=/tmp/native-delphi-independent-dev
export PYTHONUNBUFFERED=1
exec backend/.venv/bin/synsc-context-http
```

Worker command:

```bash
set -a
source new/round3/stack/r3-secrets.env
set +a
export DATABASE_URL="postgresql://$USER@127.0.0.1:5432/delphi_native_independent_dev_20260824"
export SYNSC_LOG_FORMAT=json
export SERVER_SECRET=native-delphi-session-secret-local-only
export SYSTEM_PASSWORD=native-delphi-admin
export EMBEDDING_PROVIDER=openai
export OPENAI_EMBEDDING_MODEL=text-embedding-3-small
export SYNSC_WORKER_THREADS=4
export SYNSC_TEMP_DIR=/tmp/native-delphi-independent-dev
export PYTHONUNBUFFERED=1
exec backend/.venv/bin/synsc-context-worker
```

Final health checks reported API `status=healthy`, deep readiness `ready=true`,
PostgreSQL and pgvector available, the embedding generator loaded, the
reranker ready, and zero embedding-model mismatches.

## Independent development provisioning

Provisioning command:

```bash
cd new/round3
PYTHONPATH=. .venv/bin/python -u harness/provision_delphi_local.py \
  --sample-files corpus/independent/v1/development.jsonl \
  --bare-root corpus/independent/bare \
  --snapshot-root corpus/snapshots \
  --container-root /Users/aayambansal/Desktop/syntheticsciences/delphi/new/round3/corpus/snapshots \
  --base-url http://127.0.0.1:28742 \
  --api-key native-delphi-admin \
  --manifest results/native-delphi-independent-dev-sources.jsonl \
  --workers 1
```

Provisioning took 3,334.889 seconds. Strict postflight:

```json
{
  "required_pairs": 48,
  "manifest_rows": 48,
  "unique_pairs": 48,
  "unique_source_ids": 48,
  "database_source_ids": 48,
  "all_chunks_nonzero": true,
  "all_embedding_counts_match": true
}
```

The database contains 48 repositories, 44,189 stored source files, 145,258
chunks, and 145,258 embeddings and is 1,685 MB. Each manifest source ID exactly
matches one live database repository.

### Provisioning failure and product fix

The first `psf/black@0dae20b2d009` attempt incorrectly reported success with
zero chunks. A skipped final file could bypass the batch flush and strand
earlier valid files. TDD work:

1. Added
   `test_local_index_flushes_valid_files_when_final_input_is_skipped`; it
   failed with `assert 0 >= 1`.
2. Changed `_index_files` to mark empty/oversized/NUL-containing files as
   skipped without bypassing end-of-input flushing, and to flush based on the
   count of valid pending files.
3. The regression now passes, and the snapshot was reindexed to 2,088 chunks.
4. Removed the stale zero-chunk manifest row after confirming its source ID no
   longer existed in PostgreSQL; the canonical manifest is now one-to-one.

No benchmark-specific exception or repository-specific behavior was added.
The provisioning harness now also fails closed: only positive file/chunk
records count as reusable, a zero-chunk success forces one reindex, and a
second zero-chunk response becomes a failed row. The strict index audit is
`results/native-delphi-independent-dev-index-audit-20260824.json`; it records
the canonical manifest hash and all database integrity checks.

## Gold-path searchability preflight

Positive repository-level counts do not prove that every benchmark target is
searchable. During ARB development provisioning, the Playwright index correctly
skipped nine files above the 500 kB PostgreSQL `tsvector` safety cap. Its actual
gold file, `packages/playwright-core/src/tools/dashboard/dashboardApp.ts`, is
not among them, but the observation exposed a protocol gap.

The file API now returns `indexed_chunks` for an authorized file. Before a
Delphi ARB run creates a run record or scores a case, `run_arb.py` requests
every target gold path from its exact source ID, requires a positive chunk
count, and fails closed. Missing paths are written as a deterministic
`delphi_gold_searchability_gaps_v1` artifact. The successful audit result is
also captured in run configuration and summary provenance. Focused TDD and
harness verification pass (13 tests across the new backend regression and ARB
coverage suite), lint is clean, and the full backend suite passes with 1,030
tests plus 138 environment-dependent skips.

## Serving-config-attested exact-scan independent baseline

Run command (repeat changed only the run ID and note):

```bash
cd new/round3
PYTHONPATH=. .venv/bin/python -u harness/run_arb.py \
  --engine delphi \
  --sources results/native-delphi-independent-dev-sources.jsonl \
  --sample-files corpus/independent/v1/development.jsonl \
  --bare-root corpus/independent/bare \
  --split development \
  --delphi-url http://127.0.0.1:28742 \
  --delphi-key native-delphi-admin \
  --expected-retrieval-config-json \
    '{"vector_mode":"exact","hnsw_ef_search":100,"embedding_model":"text-embedding-3-small","hybrid_candidates":50,"hybrid_rerank_k":30,"file_diverse_bm25":false,"query_expansion_enabled":true,"listwise_rerank_enabled":true,"listwise_rerank_model":"gpt-4o","listwise_rerank_k":20,"llm_seed":1042}' \
  --run-id native-delphi-independent-exact-attested-r1 \
  --system delphi-native-exact \
  --notes "Fail-closed serving-config-attested independent exact baseline; persisted stage cache; final split untouched."
```

Artifacts:

- `results/native-delphi-independent-exact-attested-r1-{summary.json,details.jsonl}`
- `results/native-delphi-independent-exact-attested-r2-{summary.json,details.jsonl}`

Both runs completed 48/48 cases with zero failures/skips. Their ranked files,
gold files, statuses, and metric dictionaries are identical on every case.
Both were warm-cache measurements: r1 mean/median case latency was
174.3/163.6 ms and r2 was 176.2/157.5 ms.

The earlier non-attested `native-delphi-independent-exact-r1/r2` artifacts are
retained as history but are not the controlled comparison reference: they
predate the final source-selection/provenance changes. The canonical attested
runs were produced after those files stopped changing and all ablation APIs
were then launched from the same working tree.

Full sample-weighted baseline metrics:

```json
{
  "BCY@8k": 0.5277777777777778,
  "F0.5@10": 0.136527539391975,
  "F0.5@20": 0.07948326524460328,
  "F0.5@5": 0.2274295752556622,
  "MRR": 0.5951479076479077,
  "Precision@10": 0.11458333333333333,
  "Precision@20": 0.06570512820512821,
  "Precision@5": 0.19999999999999998,
  "Recall@10": 0.7083333333333334,
  "Recall@20": 0.7291666666666666,
  "Recall@5": 0.607638888888889,
  "context_efficiency@8k": 0.46582073434125265,
  "context_pollution_tokens@8k": 15255.5,
  "coverage_auc@20": 0.6690972222222222,
  "gold_coverage@8k": 0.3489583333333333,
  "gold_token_ratio@8k": 0.46582073434125265,
  "hard_negative_hits@10": 0.0,
  "hard_negative_hits@20": 0.0,
  "hard_negative_hits@5": 0.0,
  "irrelevant_files@10": 8.854166666666666,
  "irrelevant_files@20": 18.4375,
  "irrelevant_files@5": 4.0,
  "redundancy@8k": 0.0
}
```

### Fail-closed serving provenance

The API now returns the non-secret retrieval configuration that determined
each ranking. The harness accepts an expected nested subset through
`--expected-retrieval-config-json`; a missing or mismatched field returns a
fatal `configuration_mismatch` rather than scoring the case. Every canonical
exact, file-BM25, and HNSW trace contains and matches its expected
configuration. This was added as product provenance, not as a benchmark
exception.

## File-diverse BM25 ablation

The three API variants differed from exact baseline only by enabling
`SYNSC_FILE_DIVERSE_BM25=true` and setting
`SYNSC_FUSION_WEIGHTS=file_bm25=<weight>`. Trace validation found at least two
`file_bm25` candidates in every attested case; baseline traces contained none.
The temporary APIs were PID `24991`/port `28745` (0.10), PID `24997`/port
`28744` (0.15), and PID `25005`/port `28746` (0.20); all were stopped after
scoring.

All variants completed 48/48 cases with zero failures/skips:

- Weight 0.10, run `native-delphi-independent-filebm10-attested-r1`: MRR 0.595337,
  R@5 0.631944, R@20 0.736111, BCY@8k 0.513889.
- Weight 0.15, run `native-delphi-independent-filebm15-attested-r1`: MRR 0.601786,
  R@5 0.638889, R@20 0.736111, BCY@8k 0.513889.
- Weight 0.20, run `native-delphi-independent-filebm20-attested-r1`: MRR 0.595569,
  R@5 0.631944, R@20 0.736111, BCY@8k 0.520833.

Against exact, weight 0.15 changes MRR by +0.006638, R@5 by +0.031250,
R@20 by +0.006944, and BCY@8k by -0.013889. A deterministic 20,000-draw
repository-cluster bootstrap over 16 repositories gives 95% intervals:
MRR `[-0.010417, 0.030943]`, R@5 `[0.000000, 0.069444]`, R@20
`[0.000000, 0.020833]`, and BCY@8k `[-0.062500, 0.020833]`.

Weight 0.15 is the development leader for MRR and R@5, but it is not a clean
default: both intervals include zero at the lower bound and BCY moves down.
Keep the branch opt-in and take 0.15 to a frozen downstream development
intervention before adoption.

Every full metric vector, paired delta, interval, and artifact path is in
`results/native-delphi-independent-comparison.json`.

## Scored API-boundary ablation

The original independent runs requested 100 provider results and then scored
the first 20 distinct files. That is not equivalent to asking Delphi to solve
the actual top-20 problem because listwise reranking and source preservation
receive a different boundary. Guarded exact/current and file-BM25 0.15 runs
were therefore repeated with API `top_k=20`.

- Exact/current `I-dev-delphi-native-current-fetch20-r1`: MRR 0.596665,
  R@5 0.645833, R@20 0.763889, BCY@8k 0.517361, any-gold 40/48.
- File-BM25 0.15 `I-dev-delphi-native-filebm15-fetch20-r1`: MRR 0.607176,
  R@5 0.607639, R@20 0.729167, BCY@8k 0.559028, any-gold 38/48.
- Guarded exact repeat `I-dev-delphi-native-current-fetch20-r2`: all 48
  metric rows and top-20 lists exactly match r1.

Relative to exact/current at API `top_k=100`, the scored-boundary run recovers
two complete cases and loses none, raising R@20 by +0.034722
[-0.013889, 0.097222] and R@5 by +0.038194 [0.000000, 0.086806]. One
three-file Celery case loses a partial hit and BCY moves -0.010417, so the
effect is not uniformly positive. Against canonical lexical, the scored-
boundary exact run reaches 40 versus 39 any-gold cases and improves MRR by
+0.134799 [0.028740, 0.247396] and R@5 by +0.133333
[0.011806, 0.274306]; the R@20 and BCY intervals include zero.

File-BM25 at the same boundary loses both newly recovered exact cases and
recovers none. It is retired from the primary development path, though its
default-off implementation and negative evidence remain. The runner now
defaults provider fetch depth to the scored limit; larger pages require an
explicit `--fetch-limit`. Full paired analysis is in
`results/independent_delphi_topk_contract_analysis_v1.json`, and repeat
analysis is in
`results/independent_delphi_topk20_repeat_analysis_v1.json`.

## HNSW ef_search ablation

Temporary APIs used the same database, code, cache, and ranking settings as
baseline, with exact scan disabled:

- HNSW-100: PID `25791`, port `28743`,
  `SYNSC_HNSW_EF_SEARCH=100`.
- HNSW-400: PID `25797`, port `28744`,
  `SYNSC_HNSW_EF_SEARCH=400`.

Both temporary APIs were healthy before scoring and were stopped after the
runs. The long-lived exact API remained on port 28742.

Staged eight-case packet runs:

- `native-delphi-independent-hnsw100-packet-r1`
- `native-delphi-independent-hnsw400-packet-r1`

Both matched exact on all eight ranked lists and metrics. Full runs then
completed 48/48 cases with zero failures/skips:

- `native-delphi-independent-hnsw100-attested-r1`: MRR 0.595148,
  R@5 0.607639, R@20 0.729167, BCY@8k 0.527778; mean latency 185.7 ms.
- `native-delphi-independent-hnsw400-attested-r1`: identical quality and all
  48 ranked lists; mean latency 182.0 ms.

HNSW-100 and HNSW-400 are identical on every case. Relative to exact, both
match all 48 complete ranked lists and all metrics, with mean file Jaccard
1.000 at 5, 10, and 20. Increasing `ef_search` to 400 therefore provides no
quality movement; the small latency reversal in this warm run is measurement
noise rather than evidence for a larger default. Keep 100 for HNSW
deployments; exact scan remains the evaluation reference.

## Fresh-index chunk safety audit

The native database was built after the oversized-single-line invariant fix.
The fresh index contains:

```json
{
  "chunks": 145258,
  "max_tokens": 3057,
  "over_provider_limit_8191": 0,
  "over_configured_limit_2048": 609,
  "oversized_single_line_over_2048": 0
}
```

The remaining chunks above 2,048 tokens are permitted multi-line AST regions
under the existing 1.5x tolerance. No chunk reaches the embedding provider
limit and no oversized one-line chunk remains. The damaged pre-fix Docker
index is invalid, so this is a safety audit rather than a paired estimate of
the chunk fix's isolated retrieval effect.

## Default-off path-token branch

The post-hoc path normalization diagnostic was implemented as a real,
repository-scoped candidate branch rather than as a benchmark-side tail edit.
`SYNSC_PATH_TOKEN_SEARCH` defaults to false. When enabled, the branch:

1. requires explicit `repo_ids`, avoiding an account-wide path scan;
2. splits prose and paths on punctuation, separators, camel case, and acronym
   boundaries;
3. ranks paths with repeated-query-term weighting, repository-local IDF, and
   square-root path-length normalization;
4. scans only files with searchable chunks and selects one deterministic first
   chunk per top file;
5. aligns file-level agreement to an existing stronger chunk from that file;
6. enters RRF as `path_token` at default weight 0.10;
7. reports branch counts and response-level serving provenance; and
8. caps each scoped path scan at 50,000 searchable files plus one overflow
   sentinel, failing closed rather than scoring a biased partial scan.

The first native run exposed a distinction between file-level agreement and
novel-file acquisition. For the ripgrep miss, path rank one was `types.rs`,
already present through another branch; alignment added `path_token` there and
the source-diverse selector treated the branch as covered. Gold
`default_types.rs` at path rank two never entered the rerank window. A
fail-first regression now requires one standalone candidate from each
file-level source even when an aligned multi-source candidate is present.

The corrected, config-attested runs are:

- `I-dev-delphi-native-pathtoken10-novel-top20-r2`
- `I-dev-delphi-native-pathtoken10-novel-top20-r3`

Both complete 48/48 with zero failures or skips and are exact on every metric
row and top-20 list. They score MRR 0.628884, R@5 0.667361, R@20 0.793056,
BCY@8k 0.528472, and any-gold 42/48. The current exact reference scores
0.596665/0.645833/0.763889/0.517361 and 40/48. Both diagnostic misses are
recovered with no binary acquisition loss; fractional Recall@20 has three wins
and one loss. Repository-bootstrap intervals for MRR, R@5, and R@20 include
zero. Artifacts:

- `results/independent_delphi_path_token_novel_analysis_v1.json`
- `results/independent_delphi_path_token_repeat_analysis_v1.json`
- the corresponding run summaries and details under `results/`.

Review then exposed latent zero-hit fusion/provenance and multi-source
replacement defects. Optional file-level weights now enter fusion only after
the branch returns candidates; path-token provenance requires both hybrid mode
and explicit repository scope; and replacement credits source coverage supplied
by the incoming standalone candidate. The post-review run
`I-dev-delphi-native-pathtoken10-reviewed-top20-r4` is exact against `r3` on
all 48 metric rows and top-20 lists. Its paired analysis is preserved in
`results/independent_delphi_path_token_reviewed_analysis_v1.json`. A second
defect-focused review found no remaining finding in scope.

This is repeatable independent-development product evidence, not adoption
evidence. The branch stays disabled until it passes the fresh 75-case ARB
development gate. Neither locked final split was touched.

## Verification

Commands and outcomes:

```bash
# Product regression introduced by this workstream
(
  cd backend
  DATABASE_URL="postgresql://$USER@127.0.0.1:5432/delphi_native_independent_dev_20260824" \
    .venv/bin/pytest -q \
    tests/test_atomic_reindex_postgres.py::test_local_index_flushes_valid_files_when_final_input_is_skipped
)
# 1 passed

# Focused retrieval, cache, config, ranking, and chunking suite
cd backend
.venv/bin/pytest -q \
  tests/test_chunker.py tests/test_config.py tests/test_hybrid_retrieval.py \
  tests/test_listwise_rerank.py tests/test_query_expansion.py \
  tests/test_search_determinism.py tests/test_search_result_selection.py \
  tests/test_pgvector_search_config.py
# 102 passed

cd ../new/round3
PYTHONPATH=. ../../backend/.venv/bin/pytest -q \
  harness/test_run_arb_coverage.py
# 9 passed

cd ../..
backend/.venv/bin/ruff check \
  backend/synsc/services/indexing_service.py backend/synsc/core/chunker.py \
  backend/tests/test_atomic_reindex_postgres.py backend/tests/test_chunker.py \
  new/round3/harness/provision_delphi_local.py new/round3/harness/run_arb.py
# All checks passed

# Post-review focused retrieval/config/selection suite
cd backend
.venv/bin/pytest -q \
  tests/test_hybrid_retrieval.py tests/test_search_result_selection.py \
  tests/test_config.py
# 85 passed

# Clean full backend suite
env -u SYNSC_RATE_LIMIT_INDEX -u SYNSC_RATE_LIMIT_SEARCH \
  .venv/bin/pytest -q
# 1029 passed, 138 skipped

# Scorer and paired-analysis regressions
cd ..
PYTHONPATH="new/round3" backend/.venv/bin/pytest -q \
  new/round3/harness/test_run_arb_coverage.py \
  new/round3/harness/test_analyze_arb_sweep.py
# 12 passed
```

Postflight also validated every result JSON/JSONL, all case statuses, source
coverage, manifest/database ID equality, chunk/embedding equality, per-case
serving configuration, file-BM25 branch contribution, and exact repeat
equality. `git diff --check` passes for the complete working tree.

## Fresh native ARB development gate

Provisioning completed for the exact 68 required development snapshots. A new
fail-closed audit binds the required sample hashes, canonical manifest, source
IDs, and database rows in
`results/native-delphi-arb-dev-index-audit-20260824.json`. It verifies 68
repositories, 116,424 files, 548,545 chunks, and 548,545 embeddings with no
missing, empty, duplicate, extra, or chunk/embedding-mismatched source. The
gold-path preflight then passed before both scored arms.

The config-attested current and reviewed path-token runs each completed 75/75
cases without a technical failure or skip:

- Current `A-dev-delphi-native-current-top20-r1`: MRR 0.303374, R@5 0.417778,
  R@20 0.617778, BCY@8k 0.300000, any-gold 54/75.
- Path-token `A-dev-delphi-native-pathtoken10-reviewed-top20-r1`: MRR 0.316984,
  R@5 0.457778, R@20 0.611111, BCY@8k 0.291111, any-gold 54/75.

Path-token's paired changes are +0.013610 MRR, +0.040000 R@5, -0.006667 R@20,
and -0.008889 BCY. All repository-cluster 95% intervals include zero. It has
two complete recoveries and two complete losses (McNemar p=1.0). Guarded
warm-cache repeats of both arms match all 75 metric rows and top-20 lists
exactly, so this is a stable trade rather than run noise. Keep the branch
default-off.

Against whole-file BM25, current Delphi's paired gains are +0.159277 MRR
[0.059211, 0.242779], +0.244444 R@5 [0.091396, 0.380282], +0.226667 R@20
[0.092040, 0.335470], and +0.195556 BCY [0.054487, 0.312698]. Delphi uniquely
acquires 23 cases while BM25 uniquely acquires five (McNemar p=0.000912).
Against canonical git lexical, the corresponding gains are +0.211842 MRR
[0.109410, 0.290055], +0.268889 R@5 [0.135593, 0.373984], +0.244444 R@20
[0.150000, 0.354762], and +0.237778 BCY [0.095588, 0.348659]. Delphi uniquely
acquires 25 cases while lexical uniquely acquires four (McNemar p=0.000104).
Detailed paired artifacts are
`results/native-delphi-arb-dev-path-token-paired-analysis-20260824.json`,
`results/native-delphi-arb-dev-current-repeat-analysis-20260824.json`,
`results/native-delphi-arb-dev-path-token-repeat-analysis-20260824.json`, and
`results/native-delphi-arb-dev-current-vs-bm25-analysis-20260824.json`.
The unified comparator and repeatability artifacts are
`results/arb_dev_delphi_comparator_analysis_v1.json` and
`results/arb_dev_delphi_repeatability_v1.json`.

The five-case union of BM25-only and canonical-lexical-only acquisitions was
then rerun as a non-claim-bearing API-`top_k=100` depth diagnostic. Three gold
files remain absent from all 100 Delphi results; two appear only through vector
evidence at ranks 40 and 42. Whole-file BM25 ranks gold 3--19 in all five, and
canonical lexical ranks gold 5--15 in four. This isolates a file-level
candidate-generation gap rather than a scored-tail quota problem. It supports
designing one true Okapi branch, but not implementing or adopting it without
explicit approval and a zero-acquisition-loss gate. The diagnostic run is
`A-dev-delphi-native-fetch100-lexical-misses-diagnostic-v1`.

That final product experiment is now implemented on local branch
`feature/file-okapi` at `cecc557`. The implementation uses persisted per-file
term frequencies and document lengths, canonical scope-wide BM25
(`k1=1.2`, `b=0.75`), a fixed default-off fusion weight of `0.15`, atomic
initial/diff/full reindex behavior, bounded pre-chunk ranking, and separate
configured/effective provenance. The complete branch received task-level and
whole-branch review; fresh verification passes 1,079 default backend tests,
Ruff, mypy, and 13 focused real-PostgreSQL tests. It has not been pushed,
merged, or benchmarked.

A preregistered HNSW-100 operational arm then matched the exact current stack
on all 75 metric rows and top-20 lists. It did not improve latency: warm
mean/median is 671/468 ms versus 670/466 ms for exact. This closes the stale
pre-fix exact/HNSW gap on the validated native ARB index and removes the need
for an `ef_search=400` arm. The result is preserved in
`results/arb_dev_delphi_hnsw100_analysis_v1.json`.

## Current state and next action

- The current exact, non-path-token stack is restored on the native API at
  port 28843. Exact scan plus the persisted stage cache is the stable
  development reference; request the scored 20-file API boundary.
- Do not enable file-BM25 globally. Its scored-boundary arm loses two complete
  cases versus current exact and recovers none.
- Keep query/path-token default-off. Its independent gain does not generalize
  cleanly across the fresh ARB gate, and tuning another weight now would be
  post-hoc.
- Retrieval development is reopened for exactly one product-real Okapi arm,
  now fixed at commit `cecc557`. Reindex fresh isolated development databases,
  first prove that the disabled branch reproduces current exact, then run the
  single config-attested candidate and repeat it. Reject on any acquisition
  loss or preregistered quality/latency gate failure; do not tune another
  weight, tokenizer, candidate cap, or final-tail rule.
- Product-only commit `c17c1863faf88d901cceefaf32342cbb6f4d26ed`
  captures the clean frozen implementation. Its code pointer is attached to
  Atlas decision `549a2711-ff7a-4480-bd3f-9d7d4dcfc3f4`, and
  `results/delphi-round3-freeze-20260824.json` fixes the serving contract.
- Confirmatory provisioning has begun for the 142 required ARB final
  snapshots. The serial run is protected by a 6 GiB free-disk cutoff; exact
  source, embedding, gold-path, and serving-config audits remain mandatory
  before the one-shot scorer starts.
- Do not raise HNSW `ef_search` above 100 based on this corpus.
- Retain exact scan for controlled evaluation: HNSW-100 is rank-identical but
  has no measured warm-latency advantage on either validated development
  corpus.
- Do not attempt an isolated chunk-quality comparison against the invalid
  Docker index.
- Do not inspect or score final cases outside the frozen runners.

