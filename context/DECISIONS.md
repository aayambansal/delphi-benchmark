# Decisions

## 2026-08-23 — keep benchmark work local

The Vagon path was abandoned after unreliable remote input made execution and
provenance worse, not better. All corpus cloning, indexing, evaluation, and
dashboards run locally. Hosted engines are called from the local harness.

## 2026-08-23 — freeze confirmatory data

Only round-3 development can guide product changes. ARB final and SWE-bench
Track D remain untouched until a single winner/configuration is frozen.

## 2026-08-23 — separate products by supported surface

Delphi and Nia can be compared on commit-pinned repository retrieval. Context7
serves package documentation and cannot honestly be inserted into that table.
It receives a separate documentation-grounded track with equal context and
answer budgets.

## 2026-08-23 — fail closed on source coverage

Hosted comparators must have exact source coverage before scoring. Silent
skipping is forbidden. The old Nia run was cancelled rather than normalized
over its available subset.

The same rule now covers technical request failures. Any non-`ok` case or
unprovisioned case marks the whole ARB run failed and exits nonzero; zero-filled
HTTP errors cannot be reported as retrieval scores.

Track C also requires all predeclared cases. Model/network failures cannot be
dropped from the denominator; an incomplete arm is invalid and must be rerun.

## 2026-08-23 — stop non-terminating Nia repository ingestion

Nia repository comparison remains fail-closed. A unique account namespace
removed identifier collisions, but three snapshot workers stayed in hosted
`syncing` state for over 40 minutes with no backend error; even the smoke source
remained `syncing`. Stop the 68-snapshot fan-out and retain no partial score.
Documentation experiments are independent and continue to be reportable.

## 2026-08-23 — namespace Nia sources by account

Nia daemon identifiers collide across accounts while source reads are
account-scoped. Fresh accounts use a fresh source namespace. A one-file smoke
source must return 200 through the normal source endpoint before bulk upload.

## 2026-08-23 — optimize product behavior, not benchmark rows

Allowed changes must make sense for ordinary users without knowing ARB:
deterministic repeated searches, avoiding already-quoted evidence, stronger
general embeddings, and repository-structural expansion. Repo names, case IDs,
gold paths, and workflow-specific lookup tables are forbidden.

## 2026-08-23 — pause narrative artifacts

Paper and blog drafts are preserved but no longer active work. Results,
exploration, and Delphi improvements take priority until the development
frontier, comparator coverage, and agent intervention are complete.

## 2026-08-23 — serialize the final large local indexes

Parallel hosted queries remain safe, but two simultaneous Delphi API indexers
exceeded Docker's memory budget during large-repository code-graph builds. The
Gemini API was killed with exit 137 after persisting two repositories but before
the clients received responses. Finish and stop the 3-small indexer first, then
restart and reconcile Gemini by repository identity before retrying. Do not
blindly duplicate the persisted repositories.

## 2026-08-23 — isolate DS-1000 execution from model generation

The official evaluator must not inherit whichever Python happens to host an LLM
SDK. Generation and execution now accept separate interpreters, and every result
records the execution interpreter. The official Python 3.10 package versions are
used. On Apple Silicon, the Linux-only `tensorflow-cpu==2.16.1` wheel is
unavailable; install the API-equivalent native `tensorflow==2.16.1` macOS arm64
wheel and record that platform substitution. A known reference solution must
pass before any generated completion is scored.

## 2026-08-24 — lock a repository-disjoint corpus

Create a second localization corpus from first-parent, non-merge commits in
repositories absent from ARB. Queries are cleaned commit messages; gold files
must already exist at the parent commit, contain source code, and never appear
by path or basename in the query. Development and final are split by
repository, selected deterministically, and hashed in `LOCK.json`. Materialize
the final split but do not query, score, or inspect it until the winner and
analysis are frozen.

## 2026-08-24 — reject Gemini as the replacement embedding

Gemini embedding-001 provides complementary deep candidates but is not the
development winner. Against OpenAI 3-small it raises R@20 by 0.011 and BCY by
0.018 with intervals crossing zero, while MRR falls by 0.054 with an interval
excluding zero. Preserve the run for future multi-embedding research; do not
replace the current embedding on this evidence.

## 2026-08-24 — distinguish live-process from restart determinism

Concurrent client processes hitting one warm API are not a cold-process test.
The complete single-flight stack is exact across two full concurrent repeats,
but a real API restart reproduces only 1/8 exact-scan lists. Persist supported
hosted-stage outputs in an optional bounded SQLite cache so expansion replies,
listwise replies, and query embeddings survive process restarts. Use safe typed
JSON/base64 serialization only; never pickle. Do not persist `None` or
exceptions, so a later independent request can recover from a transient
provider failure.

## 2026-08-24 — score materialized snapshots without per-file git processes

The canonical content remains commit-pinned, but the benchmark reader now
prefers an already materialized immutable snapshot and falls back to
`git show`. Profiling showed thousands of per-file subprocesses—not missing
blobs—caused multi-minute cases. Direct reads preserve identical file bytes,
cut Svelte snapshot chunk construction to 1.35 seconds, and let both complete
48-case independent baselines replace the quarantined partial attempts.

## 2026-08-24 — retain exact scan and query expansion as the development leader

The complete exact stack reaches MRR 0.342/R@20 0.649 with two identical
75-case repeats. HNSW at `ef_search=100` reaches 0.339/0.629; disabling query
expansion reaches 0.331/0.620. Use exact scan, expansion, complete
single-flight, total ordering, and the persistent stage cache as the current
development configuration. This is not the final freeze: independent Delphi,
a native bounded lexical source, and higher-HNSW-depth ablations remain open.

## 2026-08-24 — prevent provider truncation on oversized single lines

Provider-side truncation is not a valid substitute for chunking: it silently
changes what gets embedded. When one physical line exceeds the configured
target, split its token stream into balanced bounded pieces, preserve all
decoded text, and assign every piece the original line number. Ordinary lines
stay on the existing path. The existing 1.5x tolerance for whole AST regions
is a separate quality policy and is not changed here. Keep this outside the
active independent baseline until a fresh index can isolate its retrieval
effect.

## 2026-08-24 — test file diversity before changing final-list quotas

The exact leader still has four complete misses that canonical lexical can
retrieve, but naive lexical tail slots recover only one unless the final quota
becomes large. Add an opt-in pre-rerank `file_bm25` source that contributes the
best matching chunk from each distinct file. Keep it disabled by default and
ablate weighted-RRF contributions 0.10, 0.15, and 0.20. Do not adopt a
post-hoc final-list reserve or make lexical default until the native branch
meets the preregistered R@20/MRR criterion.

## 2026-08-24 — make file diversity independent of cutoff

File diversity is an ordering guarantee, not merely a way to choose fewer
items. Always place the first ranked chunk from each distinct file before
deferred same-file chunks, even when every candidate fits inside `top_k`, and
restore that order after branch-preservation replacements. Keep all candidates;
only their exposure order changes. Treat `file_bm25` as an explicit lexical
source in the preservation guard so its opt-in ablation actually reaches the
rerank window. Do not adopt the change on unit tests alone: re-run development
and compare quality, unique-file exposure, and latency.

## 2026-08-24 — move development execution off the damaged Docker VM

The partial independent Delphi source map is invalid after Docker's ext4
`/var/lib` remounted read-only during host disk exhaustion. Do not score its
18 successful snapshots beside 30 failed ones, and do not factory-reset Docker
or risk its volumes merely to continue an experiment. Use the already-running
native PostgreSQL 14 server with pgvector and a separate Delphi database for a
clean, complete development index. Preserve the failed artifact as a runtime
diagnostic and keep the independent final split untouched.

## 2026-08-24 — keep retrieval-branch vocabularies synchronized

Every active, weighted retrieval branch must be represented consistently in
fusion, source-diverse selection, and observability. Add the existing
`path_affinity` branch to the rerank-window preservation order and
`hybrid.sources_hit`; a branch that silently vanishes between fusion and
comparative reranking is not a functioning product feature. Require a
fail-first branch-preservation regression and development evidence before
claiming a quality gain.

## 2026-08-24 — treat the native rebuild as current-product evidence

The earlier plan kept the oversized-line fix outside the active independent
baseline to permit a paired index ablation. Docker corruption invalidated that
pre-fix index, so preserving the separation is no longer possible without
building another knowingly unsafe index. Load the repaired chunker for the
clean native rebuild and score it as the current product. Audit the hard-limit
invariant directly, but do not attribute any aggregate quality delta to H9
without a valid paired control.

## 2026-08-24 — compare Delphi against the lexical Pareto frontier

Use both canonical lexical and development-tuned lexical/BM25 weighted RRF as
independent-corpus comparators. The fused ranker is stronger on MRR and R@5;
canonical lexical is stronger on BCY; both tie on R@20. Neither dominates, so
selecting only one would make the conclusion metric-dependent. Keep the 0.7
lexical fusion weight frozen before any final-split evaluation.

## 2026-08-24 — pin Context7 resolution before retrieval ablations

Treat Context7 source resolution and snippet retrieval as separate stochastic
stages. Resolve one quality-guided library ID before paired query-transform
runs, alternate arm order, and count every hosted request. The controlled
full-versus-compact result has no winner and both arms remain nondeterministic;
do not select a transform from its point estimate or compare historical runs
that used different TensorFlow source IDs as if only retrieval changed.

## 2026-08-24 — preserve resolver output as provenance

Short-window quality selection can be stable even when the candidate surface
is not. Across ten balanced canonical-name requests per package, every selected
ID is exact while candidate-list exactness is only 0.556. TensorFlow currently
selects `/tensorflow/tensorflow` in 10/10 requests rather than the
`/tensorflow/docs` ID used by the earlier fixed ablation. Continue to resolve
once and pin the resulting ID before retrieval comparisons; record candidate
motion separately and never infer cross-period resolver stability from one
stable burst.

## 2026-08-24 — coordinate persistent cold misses by cache key

Restart persistence alone is insufficient when two API workers miss the same
hosted-stage key simultaneously: both can sample and return different first
answers before SQLite receives either one. Use a renewable SQLite lease scoped
to `(namespace, cache_key)` so one worker computes each persistable cold value
and the others reuse it. Keep transient `None` and exceptions non-persistent;
durability must not turn a provider outage into a long-lived negative cache.

## 2026-08-24 — choose documentation query shape per provider

Do not apply one compact-query policy to every context engine. Context7's
balanced fixed-library comparison has no transform winner, while Nia's complete
compact repeat block is substantially worse than its historical full block on
identifier hit, context size, latency, and cross-transform citation overlap.
The subsequent fixed-source, order-balanced Nia replication confirms full
queries: full reaches 0.640 identifier hit versus compact at 0.240, and the
paired -0.400 compact-minus-full interval excludes zero. Compact is also longer
and slower. Keep full Nia queries for this track. Query shape remains
provider-specific because Context7 still has no transform winner.

## 2026-08-24 — require searchability, not nominal indexing success

A source is benchmark-ready only when its latest manifest row has positive file
and chunk counts. A successful HTTP response or repository row alone is not
enough. On a zero-chunk success, force one clean reindex; if that also returns
empty, mark the source failed and prohibit scoring. Before a run, validate
exact required-pair coverage and audit every repository for nonzero chunks and
one embedding per chunk. Preserve the original empty response as provenance
rather than deleting evidence that the guard was needed.

## 2026-08-24 — carry file-BM25 0.15 forward without making it default

The independent development sweep selects weight 0.15 among 0.10/0.15/0.20:
it has the strongest MRR and R@5 point estimates and improves one partial
multi-gold result without an R@20 loss. It does not recover a new any-gold
case, lowers BCY versus the exact current stack, and its paired MRR interval
against current crosses zero. Carry only 0.15 into a primary ARB development
ablation. Do not enable the branch by default or touch the final split.

## 2026-08-24 — require response-level serving-configuration provenance

Ports are transport locations, not experiment identities. Two repeat IDs were
mislabelled when another worker replaced their listeners with HNSW processes.
Mark both runs invalid. Every Delphi search response must expose the non-secret
retrieval configuration that produced it, and benchmark runs must declare an
expected subset and fail on the first mismatch. Preserve the invalid traces;
plausible aggregate scores are not evidence that the intended stack served
them.

## 2026-08-24 — report binary acquisition beside fractional Recall@20

Fractional Recall@20 rewards partial recovery of multi-file gold sets, while
Success@20 asks whether a task obtains any gold at all. File-BM25 0.15 has a
slightly higher mean Recall@20 than canonical lexical on independent
development, yet reaches any gold on 38 cases versus lexical's 39, with three
losses and two recoveries. Neither measure replaces the other. Any future
track-level leadership statement must report both and give the acquisition
loss equal prominence.

## 2026-08-24 — make provider top-k equal the scored boundary

Default the benchmark provider fetch depth to the scored file limit. Asking
Delphi for 100 files and truncating in the client changes the backend reranking
and branch-preservation problem: the guarded exact stack recovers two complete
cases at API `top_k=20`, moving any-gold from 38/48 to 40/48 with no complete
loss. Keep over-fetching available only as an explicit ablation and record it
in run configuration.

## 2026-08-24 — select exact/current top-k 20 and retire file-BM25

Use the unmodified exact/current stack at API `top_k=20` as the independent
development leader. It scores MRR 0.597, R@5 0.646, R@20 0.764, BCY 0.517,
and any-gold 40/48; an immediate guarded repeat is exact for every metric row
and ranked list. At the same boundary, file-BM25 0.15 loses both newly
recovered cases and recovers none, falling to 38/48 and R@20 0.729 despite
higher MRR/BCY point estimates. This decision supersedes carrying file-BM25
into another primary ablation. Keep its implementation default-off as
documented negative evidence; do not delete it or tune another weight.

## 2026-08-24 — reject unknown code-search request fields

Repository filters are safety and evaluation boundaries. Pydantic's default
extra-field behavior silently ignored a misspelled `repository_ids` field,
leaving `repo_ids=None` and executing a global search. Configure
`SearchCodeRequest` with `extra="forbid"` so typos return HTTP 422 before the
search service is called. Keep unfiltered search available only when callers
intentionally omit `repo_ids`; do not infer intent from unknown keys.

## 2026-08-24 — carry path-token as a default-off cross-corpus candidate

Implement query/path-token IDF matching as a repository-scoped pre-rerank
branch, not as a hard final-slot benchmark rule. Preserve one standalone novel
file from file-level branches even when alignment already adds their signal to
an existing multi-source candidate. The corrected native independent arm
improves every aggregate point estimate, reaches any-gold 42/48 versus 40/48
with no binary loss, and repeats every top-20 list exactly. Do not enable it by
default yet: MRR/R@5/R@20 intervals include zero and the older ARB simulation
has no binary gain. Carry only the isolated, config-attested branch into the
fresh 75-case ARB development comparison; keep both final splits untouched.

## 2026-08-24 — require path-token no-op semantics before cross-corpus gating

An optional branch must be behaviorally absent when disabled, unscoped, or
empty. Add its fusion weight only when it returns candidates; report it as
active only when hybrid retrieval and required repository scope permit
execution; and let an incoming standalone candidate preserve sources it
replaces. Restrict path ranking to searchable files and fail closed above the
bounded scan cap. Accept the implementation for ARB development only after a
defect-focused re-review and a config-attested independent rerun. The reviewed
`r4` arm matches pre-review `r3` exactly on every metric row and top-20 list,
so retain the same default-off candidate and the same no-final-split rule.

## 2026-08-24 — require gold-path searchability, not only source searchability

Before any ARB run, verify that every case's target gold file has at least one
searchable chunk in the source row for that exact repository revision.
Repository-level positive file/chunk counts do not detect individual files
skipped by size or parser safety guards. Fail closed and preserve a missing-path
artifact if this audit finds any gap. Keep the 500 kB `tsvector` safety guard:
the observed Playwright skips are generated declarations and vendored bundles,
while that case's actual gold file is not skipped.

## 2026-08-24 — keep path-token default-off after the cross-corpus gate

Do not promote the reviewed path-token branch into Delphi's default stack. The
fresh 75-case ARB development comparison passed exact-source, embedding,
gold-path, and serving-configuration gates, then produced a mixed trade:
MRR +0.013610 and R@5 +0.040000, but R@20 -0.006667 and BCY@8k -0.008889.
All repository-cluster intervals include zero, and binary acquisition is
unchanged at 54/75 with two recoveries and two losses (McNemar p=1.0). Both
current and path-token arms reproduce all 75 metric rows and top-20 lists
exactly on guarded warm repeats. Preserve path-token as a tested opt-in and
retain the non-path-token exact stack as the development leader; do not tune a
second path-token weight after seeing these cases.

## 2026-08-24 — close the HNSW-depth ablation and retain exact evaluation

The preregistered fresh ARB HNSW-100 arm matches exact on every one of 75
metric rows and top-20 lists, but its warm mean/median latency is 671/468 ms
versus 670/466 ms for exact. Together with exact equality on all 48 independent
development lists, this removes the decision-relevant premise for an
`ef_search=400` arm. Keep exact scan for controlled evaluation and keep HNSW
depth configurable for larger deployments; do not infer universal equivalence
or a production latency advantage from these corpora.

## 2026-08-24 — close retrieval development and freeze exact/current top-20

Freeze the exact-vector, current-product, API-`top_k=20`, non-path-token stack
for confirmatory evaluation. Do not add a true Okapi branch before final.
Whole-file BM25 does acquire five cases Delphi misses, but Delphi acquires 23
that BM25 misses and leads BM25 on all four paired metrics with every
repository-cluster interval above zero. Making Okapi production-real would
require a new persistent file-level index plus another complete reindex;
simulating a gold-observed tail replacement would violate the product and
final-list policies. File-BM25 and path-token already supplied two isolated
lexical interventions without clearing the adoption bar. Product-only commit
`c17c1863faf88d901cceefaf32342cbb6f4d26ed` now captures the clean frozen
implementation and Atlas decision `549a2711-ff7a-4480-bd3f-9d7d4dcfc3f4`
records that code pointer. Final evaluation may proceed exactly once from this
state.

## 2026-08-24 — require explicit approval to reopen for true file-level Okapi

The post-freeze five-case depth diagnostic strengthens the mechanism case for
a product-real file-level lexical source: three BM25-only gold files remain
absent from Delphi's first 100 results and two appear only as vector candidates
at ranks 40 and 42, while whole-file BM25 ranks all five at 3--19. This does
not silently revoke the freeze. Reopening requires an approved design for a
default-off persistent Okapi index, response-level provenance, and a
development gate that recovers lexical misses without losing any of Delphi's
23 BM25-unique acquisitions. A hard tail reserve or harness-only simulation
cannot qualify as the product intervention.

## 2026-08-24 — reopen once for a fixed product-real Okapi gate

Approval was given to reopen development for one implementation, with no
post-outcome tuning. Freeze the candidate at local commit `cecc557`: canonical
BM25 `k1=1.2`, `b=0.75`, file cap 50, query-term cap 256, scope cap 50,000,
RRF weight 0.15, exact vectors, API `top_k=20`, and every other current setting
unchanged. The branch is default-off and unpushed. Require disabled-branch
top-20 equality after reindex, zero any-gold losses on both development
corpora, at least two recovered ARB diagnostic cases, the predeclared
quality/latency bounds, and an exact candidate repeat. Any failure restores the
exact/current freeze; no second configuration may be tried.

## 2026-08-25 — reject File Okapi and freeze the generated-source stack for final

The single approved File-Okapi configuration (weight 0.15, `k1=1.2`, `b=0.75`,
file cap 50) fails its preregistered gates on the fresh isolated development
cohorts. The candidate repeats exactly, loses zero any-gold cases, and gains
Recall@20 +0.018 [0.000, 0.039], but its MRR interval lower bound -0.050 and
BCY lower bound -0.0368 fall below the -0.01 floor, and its median latency
ratio 1.342 exceeds the 1.2 bound. Per the reopening terms, reject the
candidate, run no ARB candidate arm, and tune no second configuration.
Hypothesis `dry-cave-0210` is closed rejected; Atlas run `wide-haze-0900` and
decision `flat-foam-8342` preserve the evidence.

The gate reindex exposed that a locked gold path
(`channelz/grpc_channelz_v1/channelz.pb.go`, 114,500 bytes) was excluded by
the global `*.pb.go` pattern in both the old and new indexes. The agent-mode
generated-source indexing fix committed at `3565123` lifts that exclusion,
and the queued legacy worker now enforces the same 500,000-byte and NUL
guards. The amendment is a general product coverage fix, not a benchmark
exception: generated sources are ordinary retrieval targets, the same
exclusion affected both indexes rather than only the experiment under test,
and the change encodes no benchmark ID, repository, or gold-path rule.

Freeze the confirmatory stack at branch `feature/generated-source-freeze`
commit `91d76c1`, equal to master `c17c186` plus the cherry-picked `3565123`
generated-source fix. All final scoring uses exact vectors, API `top_k=20`,
configuration attestation, and the gold-searchability preflight.
