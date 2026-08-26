# Active hypotheses and ablations

## H1 — quoted evidence should be demoted

Claim: when a structured review or diff query includes an already-open file,
returning that same file consumes context without answering the cross-file
question. Stable demotion after semantic reranking should improve
comment2context.

- General invariant: only structured evidence envelopes trigger demotion; plain
  “explain this file” questions do not.
- Expected movement: comment2context MRR/R@20 up; other workflows unchanged.
- Disconfirmers: any material loss outside comment2context, or no paired gain.
- Test: July versus patched 3-small over the identical 75 development cases,
  plus targeted unit tests.
- Status: the bundled patched run improves comment2context R@20 by 0.153 but
  loses code2test MRR by 0.066 and BCY by 0.130. Because embedding and several
  ranking changes also differ, this neither attributes the gain nor clears the
  outside-workflow disconfirmer; a demotion-only off/on ablation is required.

## H2 — stronger embeddings repair candidate recall

Claim: Gemini embedding-001 retrieves cross-file context that OpenAI
text-embedding-3-small misses before reranking.

- Expected movement: absent-gold@20 down, especially comment2context and
  edit2ripple.
- Disconfirmers: MRR/BCY flat or lower; gains only from rank changes among files
  already retrieved by July.
- Test: full Gemini candidate versus July, with paired per-case and per-workflow
  deltas.
- Status: weakened and rejected as the winner. With all 68 snapshots,
  Gemini raises R@20 from 0.642 to 0.653 and BCY from 0.320 to 0.338, but both
  intervals include zero. MRR falls from 0.337 to 0.284 with a
  repository-bootstrap delta of -0.054 [-0.102, -0.011]. It recovers five
  complete misses and loses four. Gemini contributes different deep
  candidates, but it is not a generally stronger replacement embedding.

## H3 — LLM caching and total ordering restore repeatability

Claim: caching identical HyDE/listwise/query-embedding calls, supplying a fixed
seed, and breaking score ties by stable identifiers raises exact-list
repeatability to at least 95% with negligible quality loss.

- Baseline: exact top-10 list 30.6%, Jaccard 0.760, Kendall tau 0.959.
- Disconfirmers: patched exact-list below 95%, or development MRR loss above
  0.01.
- Test: same eight queries x 10 repeats against patched stack; then three full
  development repeats.
- Status: implementation and unit tests complete. A separate 10-case docs
  Delphi sweep reaches 98.0% exact context and 0.993 item-set Jaccard.
  Context7 quality-guided retrieval reaches only 35.6% exact context; Nia has
  stable normalized citations but 0.0% exact synthesized context. Three
  commit-pinned Delphi repeats reach only 68.9% exact top-10 lists (Jaccard
  0.930), although R@20 is exactly 0.642 each time. The eval stack omitted
  exact vector scan, cache misses were not single-flight, and BM25 ties at the
  candidate cutoff lacked a total order. Single-flight regression tests pass;
  exact scan plus deterministic BM25 reaches 100% exact lists on the original
  8-query x 10-repeat packet. After total-ordering every SQL branch, two cold
  concurrent processes each reach 100% within-process exactness and all 80
  corresponding cross-process lists are identical. A longer full repeat found
  one remaining concurrency path: when the shared expansion timed out, the
  leader received `None` but its waiter retried immediately and succeeded.
  This changed 46/100 candidates. Flight outcomes now share transient `None`
  and exceptions while allowing a later independent retry. The definitive
  rerun gives both exact and HNSW 100% exact lists across two concurrent
  8 x 10 packets and two 75-case repeats. Exact scan satisfies the quality
  guard: MRR rises by 0.004 and R@20 by 0.007 versus the earlier patched run,
  while BCY falls by 0.018 with an interval crossing zero. However, a true API
  restart reproduces only 1/8 exact-scan lists (Jaccard 0.810) and 3/8 HNSW
  lists (Jaccard 0.890), because the cache is process-local. H3 is supported
  only within a live process without persistence. With the optional safe
  SQLite-backed stage cache enabled, the same fill packet remains 8/8 exact
  across two real API restarts (24/24 corresponding pairwise comparisons),
  while mean latency drops from 4.90s on fill to 1.48s and 1.79s on reuse.
  A later cold-key probe found that two live processes could still compute
  different first answers before either persisted its result. The persistent
  cache now uses a renewable per-key SQLite lease: a real two-process probe
  returns the same value to both callers with exactly one computation, and the
  full backend suite passes (1011 passed, 138 environment-dependent skips).
  H3 is now supported for a deployment that preserves its first hosted-stage
  answers. Independent clean installations can still choose different first
  answers, so cache provenance must accompany any reproducibility claim.

## H4 — file-level structural expansion repairs true misses

Claim: a bounded expansion from high-confidence symbols/files to directly
related tests, imports, callers, or sibling implementations can recover gold
that no chunk-level semantic candidate contains.

- General invariant: expansion derives only from repository structure already
  indexed; no repository names or benchmark labels.
- Expected movement: R@20 up more than MRR; listwise reranking then promotes
  useful expansions.
- Risks: context pollution, popular-file bias, latency.
- Required ablation: expansion off/on with identical embeddings and rerankers;
  report added candidates, gold recovered, and irrelevant files.
- Status: proposal only. Do not implement until r3/r3b reveals remaining misses.

## H4a — reserve bounded file-level lexical candidates

Claim: chunk-level weighted fusion can crowd out a file whose evidence is
distributed across lexical matches. Reserving a small number of distinct
file-level lexical candidates in the rerank/final window recovers true misses
without replacing semantic rank.

- Evidence: BM25 uniquely recovers 7/26 July Delphi full misses; 6/7 are
  comment2context. The official lexical ranker recovers 9/26, including all
  seven BM25 rescues. Delphi uniquely recovers 25 against lexical, so a pure
  lexical ranker is rejected.
- Conservative simulations: two BM25 tail slots change any-gold@20 from 49/75
  to 53/75 and MRR from 0.2852 to 0.2879; three lexical slots also reach 53/75
  and MRR 0.2881. The full Delphi/lexical union is 58/75.
- General invariant: quota is per retrieval branch and distinct file, never per
  workflow, repository, or path.
- Disconfirmers: the current one-per-branch guard already recovers the cases;
  a larger quota lowers MRR/BCY or adds no unique gold; latency grows materially.
- Test: inspect candidate ranks/sources in patched 3-small first, then ablate
  file-diverse lexical branch quota 1 versus 2/3 on development if misses
  remain.
- Status: candidate provenance measured. The patched pool contains gold for
  62/75 cases, but only one gold candidate row is BM25-only. Canonical
  file-level BM25 still rescues three of the thirteen pool misses and lexical
  rescues two. This rejects a larger quota for the existing chunk branch and
  supports testing a distinct file-level lexical candidate source. On the
  patched ranking, reserving ranks 19--20 for whole-file BM25 raises R@20 from
  0.642 to 0.660, but the repository-bootstrap delta is only +0.018
  [-0.026, 0.056] and the intervention recovers two complete misses while
  losing one. On the repository-disjoint 48-case commit-to-files development
  set, the official lexical ranker also beats whole-file BM25 on R@20 by
  +0.090 [0.024, 0.174], recovering six complete misses and losing none
  (McNemar p=0.031). This independent evidence strengthens the case for a
  bounded file-level lexical source, but it still must win as a native Delphi
  ablation before becoming a default. A development-tuned file-level weighted
  RRF of lexical (0.7) and BM25 (0.3) is a stronger MRR/R@5 comparator:
  MRR 0.469 versus lexical 0.462 and R@5 0.551 versus 0.513, with identical
  R@20 0.732. Its BCY is slightly lower (0.433 versus 0.440), and all paired
  quality intervals against lexical include zero, so neither baseline
  dominates the other. Against the complete exact-scan leader,
  canonical lexical retrieves gold for four of Delphi's nineteen complete
  misses. A naive final-list reserve is intentionally conservative: 1 lexical
  slot changes nothing; 3 raises R@20 from 0.649 to 0.669 and complete hits
  from 56 to 57; 8 reaches R@20 0.678 with the same one recovered miss and no
  complete-hit loss, while MRR remains 0.343. Because three additional
  recoverable gold files sit at lexical ranks 10--15, the native ablation
  should enter before reranking/fusion rather than allocate a large final-list
  quota.
- Native status: an opt-in PostgreSQL `file_bm25` branch now selects the
  highest-scoring totally ordered chunk from each distinct matching file and
  contributes it before weighted RRF. Because fusion is chunk-keyed, the
  file-level score is copied onto the strongest existing candidate chunk from
  that file; otherwise vector and lexical hits on different chunks could not
  agree. It is default-off, covered by SQL/config/alignment regressions, and
  passes a live database probe with ten distinct files.
  All three independent-development weights are complete. Relative to the
  exact current baseline (MRR 0.5951/R@5 0.6076/R@20 0.7292/BCY 0.5278),
  weight 0.15 has the best point estimates at
  0.6018/0.6389/0.7361/0.5139. Its paired deltas are MRR +0.0066
  [-0.0104, 0.0309], R@5 +0.0313 [0.0000, 0.0694], R@20 +0.0069
  [0.0000, 0.0208], and BCY -0.0139 [-0.0625, 0.0208]. It improves one
  already-hit multi-gold case from partial to complete recall but recovers no
  new any-gold case; every weight remains at 38/48 complete hits.
  Weight 0.15 leads canonical lexical and the lexical/BM25 RRF comparator on
  MRR, with repository-bootstrap intervals above zero, but has 38 any-gold
  cases versus their 39 (three lost, two recovered). This supports 0.15 as the
  only file-BM25 weight worth carrying into the primary ARB development
  ablation, not as a default product adoption. The branch changes ordering
  more than coverage and lowers BCY versus the current exact stack. At the
  corrected scored API boundary (`top_k=20`), file-BM25 0.15 is weaker on the
  primary acquisition objective: 38/48 any-gold and R@20 0.729 versus 40/48
  and 0.764 without the branch. It loses both complete cases newly recovered
  by the unmodified stack and recovers none, although its MRR and BCY point
  estimates are higher. H4a is therefore rejected for this file-BM25
  implementation as a default. The remaining lexical complementarity question
  concerns a distinct canonical lexical branch, not a larger BM25 weight.
- Fresh ARB candidate-depth diagnostic: the five whole-file-BM25-only cases
  include all four canonical-lexical-only cases. With Delphi deliberately
  over-fetching 100, gold is absent in three cases and appears only as
  vector-only candidates at ranks 40 and 42 in two; no gold enters the scored
  top 20. Whole-file BM25 ranks gold 3--19 in all five and canonical lexical
  ranks gold 5--15 in four. This supports a file-level candidate-generation
  hypothesis rather than a final-list quota, but does not override the freeze
  or establish that adding the branch would preserve Delphi's 23 unique
  acquisitions. A product-real Okapi design requires explicit approval before
  implementation.
- Product status: the approved branch is implemented locally at `cecc557`.
  It persists exact file-term frequencies and lengths, computes canonical
  repository-scoped BM25 with fixed `k1=1.2` and `b=0.75`, contributes at one
  preregistered weight `0.15`, and remains default-off. Fresh unit, full-suite,
  lint, type, migration, and real-PostgreSQL checks pass. H4a is reopened only
  for the predeclared development gate; implementation correctness is not
  evidence of retrieval gain, and both final partitions remain untouched.

## H5 — a context seed changes frozen-agent behavior

Claim: Delphi seed context improves final File F1 and time-to-first-gold over no
seed and lexical seed under an otherwise identical closed-tool agent.

- Controls: none, random non-gold, oracle gold.
- Comparators: lexical/grep, BM25, Delphi, Nia.
- Disconfirmers: Delphi no better than no seed or lexical; gains disappear when
  seed tokens are budget-matched; oracle shows no headroom.
- Status: supported on this 40-case development sample. Delphi reaches File F1
  0.234 and final-any-gold 0.475, versus none at 0.046/0.075, BM25 at
  0.093/0.175, and lexical at 0.119/0.250. Repository-cluster File F1 CIs
  exclude zero versus none and BM25; versus lexical, final-hit McNemar p=0.035
  while the File F1 CI narrowly includes zero. Delphi observes roughly 2,500
  seed tokens, so utility and token cost remain coupled. Nia's repository arm
  is externally blocked and cannot enter as a partial run.

## H6 — Context7 helps only on its native surface

Claim: Context7 improves documentation-grounded coding answers when library
resolution is correct, but it is not a valid comparator for commit-pinned
repository retrieval.

- Test: equal-budget documentation cases with no retrieval, Delphi docs, Nia
  docs, and Context7; preserve resolver failures separately from answer
  failures.
- Disconfirmers: no gain over no retrieval, unresolved/incorrect libraries, or
  benchmark leakage through oracle package resolution.
- Status: automatic quality-guided resolution matches oracle identifier hit,
  but three downstream repeats average 0.567 versus 0.575 without retrieval
  (CI includes zero). Nia synthesis averages 0.642 and Delphi 0.592. This
  development result weakens any claim that Context7 helps this frozen model.
  A new fixed-library, equal-request, five-repeat ablation finds full queries
  at 0.38 identifier hit versus compact at 0.34 (delta +0.04, case-cluster CI
  [-0.22, 0.32]); two cases favor each transform. Both remain retrieval-
  nondeterministic (exact-list rates 0.28 and 0.22, item-set Jaccard about
  0.75), and historical resolver output drifted between TensorFlow source IDs.
  No transform wins and no final split has been touched. A resolver-only
  50-request follow-up then holds each package to one canonical identity query:
  selected IDs are pairwise exact at 1.000 for all five packages, but candidate
  lists are exact at only 0.556 with mean set Jaccard 0.862. TensorFlow selects
  `/tensorflow/tensorflow` in 10/10 current calls rather than the earlier
  `/tensorflow/docs` fixed ID. H6 therefore retains resolve-once pinning as an
  evaluation-provenance requirement even though short-window quality selection
  is stable.

## H7 — bounded context synthesis may beat raw snippet volume

Claim: query-aware, citation-preserving compression of a broader Delphi
candidate set can retain API facts while removing context pollution, improving
downstream execution and answer stability.

- Evidence: Nia's synthesized context averages 1,400 tokens and reaches 0.642
  pass@1 across three repeats, versus Delphi `k=5` at 2,647 tokens and 0.592.
  Delphi `k=20` raises retrieval hit by one case but its 7,686-token context
  scores 0.500 in the exploratory downstream run.
- Confounder: Nia raw retrieval is unavailable, so its retrieval and synthesis
  contributions cannot be separated.
- General invariant: synthesis must preserve source citations and exact API
  identifiers, use a hard token budget, expose latency/cost, and never invent
  unsupported code.
- Test: compress Delphi `k=20` to roughly Nia's token budget, then run the same
  frozen generator and compare against Delphi raw `k=5`, raw `k=20`, Nia, and
  no retrieval.
- Disconfirmers: identifier loss, no downstream gain, unstable synthesis, or
  latency/cost that dominates the retrieval benefit.
- Status: first generative pass compresses Delphi `k=20` from 7,686 to 249
  mean tokens, but a faithfulness audit finds six false-to-true identifier
  flips and five true-to-false flips. At least one packet invents a task
  solution despite the evidence-only instruction, so its apparent 0.450 hit
  rate is not a retrieval gain. Its three downstream repeats average 0.558,
  below 0.575 without retrieval. A mechanically extractive selector is 100%
  source-faithful but loses identifier hit (0.300) and averages 0.492 pass@1
  (delta -0.083, CI [-0.208, 0.042]). Current bounded-synthesis designs are
  rejected; neither enters the product.

## H8 — deeper HNSW search may retain exact-scan recall at scale

Claim: HNSW `ef_search=100` is too shallow for repository-filtered vector
queries. Raising the dynamic candidate list to 400 should move the fused
candidate pool and final ranking toward exact scan while preserving indexed
retrieval for large deployments.

- Evidence: exact and HNSW-100 are each internally deterministic, but only 2/8
  packet lists match (top-10 Jaccard 0.849). On 75 development cases, exact
  scores MRR 0.342/R@20 0.649 versus HNSW-100 at 0.339/0.629, recovering two
  any-gold@20 cases and losing none.
- General invariant: expose HNSW search depth as configuration; never special
  case a repository, query, or benchmark.
- Test: compare HNSW-100 and HNSW-400 against the persisted exact eight-query
  packet, then run the full development set only if 400 materially closes the
  list/recall gap.
- Disconfirmers: no movement toward exact candidates, R@20 remains below
  HNSW-100, or vector/search latency rises enough to erase the indexed-search
  advantage.
- Independent and fresh cross-corpus evidence: HNSW-100 matches exact on every
  top-20 list across both the 48-case independent development corpus and the
  repaired 75-case ARB development corpus. On fresh ARB, warm mean/median
  latency is 671/468 ms for HNSW versus 670/466 ms for exact.
- Status: weakened and closed as a current intervention. The stale pre-fix ARB
  gap does not reproduce on either validated native corpus, and HNSW-100 shows
  no measured latency advantage, so there is no decision-relevant reason to
  test `ef_search=400`. Keep search depth configurable for genuinely larger
  deployments; do not claim that exact and HNSW are universally equivalent.

## H9 — generated single-line chunks must not reach provider truncation

Claim: splitting an individual line whose token count exceeds
`chunking.max_tokens` prevents provider-side truncation without affecting
ordinary source files.

- Evidence: live indexing stored 17,851- and 17,165-token chunks despite a
  configured 2,048-token maximum; the embedding provider logged truncation to
  8,191. Across the live database, 42 chunks exceed the provider limit. A
  focused regression reproduces the one-line failure.
- Intervention: encode only over-limit lines, divide their token stream into
  balanced pieces no larger than the configured maximum, retain the original
  line number for every piece, and leave normal lines on the existing fast
  path.
- Scope: AST regions between 1.0x and 1.5x the configured target remain whole
  by existing policy. Removing that tolerance is a separate retrieval-quality
  ablation; H9 concerns the one-line path that can exceed the provider limit.
- Disconfirmers: any decoded text is lost, a split piece remains over the hard
  limit, ordinary chunk behavior changes, provider truncation remains after a
  fresh index, or retrieval materially regresses.
- Status: invariant fix and regression pass. The damaged pre-fix Docker index
  is invalid, while the replacement native index necessarily loads the current
  repaired chunker. Retrieval safety can be audited on that clean index, but
  H9's isolated quality effect cannot be estimated as a paired comparison.

## H10 — file-first selection must hold even without truncation

Claim: stable file-first ordering before comparative reranking exposes more
distinct files than chunk-order passthrough whenever the candidate set already
fits inside `top_k`, improving context acquisition without discarding any
candidate.

- Evidence: 19/75 exact development pages contain duplicate-file chunks; the
  worst 100-result page has 72 duplicate slots. The old source-diverse helper
  bypassed file selection when `len(results) <= top_k`, and its final
  original-rank sort could re-interleave duplicates after selection.
- General invariant: return the first ranked chunk from every distinct file
  before deferred same-file chunks, whether or not the call truncates the
  candidate set. Preserve branch coverage inside that file-first constraint.
- Intervention: route the no-truncation path through the existing stable
  file selector, restore file-first ordering after branch injection, and
  include the opt-in `file_bm25` branch before broad chunk-level BM25 in the
  source-preservation order.
- Disconfirmers: development MRR/R@5/R@20 or BCY materially declines, the
  number of unique files visible to listwise reranking does not increase on
  duplicate-bearing cases, or latency changes materially.
- Status: two fail-first ordering regressions and one `file_bm25` branch
  regression now pass; the 99-test intervention suite is green. A full
  development rerun is required before adoption.

## H11 — every active retrieval branch must reach the rerank window

Claim: source-diverse selection should reserve a bounded slot for the
related-path-affinity branch just as it does for vector, symbol, exact path,
trigram, and lexical branches. Otherwise a branch can be implemented and
weighted in fusion yet silently disappear before comparative reranking.

- Evidence: `path_affinity_search` is an active weighted branch designed to
  retrieve related tests and sibling implementations from paths named in a
  structured coding request, but `_select_source_diverse_results` omitted
  `path_affinity` from its preservation order. A fail-first two-slot
  regression returned two vector-only files and discarded the only
  related-path candidate. In the complete exact-run traces, path affinity
  contributes candidates on 46/75 cases but has no candidate in the top-30
  rerank window on 17 of them. One affected case carries a gold file at rank
  39 solely through path/path-affinity, giving the rerun a concrete possible
  recovery without defining a benchmark-specific rule.
- General invariant: branch coverage and branch observability must enumerate
  the same active branch vocabulary used by fusion.
- Intervention: preserve `path_affinity` immediately after exact path and
  report it in `hybrid.sources_hit`.
- Disconfirmers: no additional path-affinity candidate reaches the rerank
  window on affected development cases, or the reservation displaces stronger
  evidence and materially lowers quality.
- Status: fail-first regression repaired; the full 99-test intervention suite
  and lint pass. Development effect is pending the clean native rerun.

## H12 — compact documentation queries preserve quality more efficiently

Claim: removing setup code and low-value detail from documentation questions
should preserve identifier retrieval while lowering returned context and
latency.

- Test: repeat the same ten predeclared development cases ten times per query
  shape, keep source selection fixed where the provider permits it, count every
  hosted attempt, and compare identifiers, citation identity, tokens, and
  latency.
- Disconfirmers: lower identifier hit, materially different source sets, more
  context, or higher latency.
- Status: rejected for Nia and unsupported for Context7. Nia's complete
  no-retry compact block scores 0.260 mean identifier hit versus 0.600 in the
  historical full block; the case-cluster compact-minus-full delta is -0.340
  [-0.600, -0.090]. It also returns 101 more mean tokens, takes 2.93 seconds
  longer, and has only 0.606 cross-transform citation-set Jaccard. The
  acquisitions were sequential rather than interleaved, so that first result
  was descriptive. A fixed-source, order-balanced 100-request replication then
  confirms the effect: full Nia queries score 0.640 identifier hit versus
  compact 0.240; compact-minus-full is -0.400 with a case-cluster interval
  [-0.640, -0.160]. Compact also adds 100.58 mean tokens [3.12, 192.02] and
  2.620 seconds [1.392, 3.803]. H12 is rejected for Nia under the stronger
  paired design. Context7's fixed-library balanced ablation still has no
  winner (+0.040 full-minus-compact, interval [-0.220, 0.320]). Keep full Nia
  queries and do not universalize query compaction across providers.

## H13 — successful indexing must imply a searchable source

Claim: accepting a source from HTTP status and `success=true` alone can silently
admit an empty index; source validation must require positive files and chunks
before any benchmark case can use it.

- Evidence: one native Black snapshot reported success with 417 files and zero
  chunks. The prior manifest logic marked it complete, even though every query
  against that source would necessarily miss.
- Intervention: require positive `files_indexed` and `chunks_created`, perform
  one forced reindex on an empty successful response, and fail closed if the
  second response remains empty. Re-evaluate old manifest rows with the same
  predicate rather than trusting their status label.
- Disconfirmers: forced reindex remains empty, another required source has no
  files/chunks/embeddings, or the strict manifest does not cover exactly the 48
  required development snapshots.
- Status: supported as a validity invariant. The forced reindex repaired the
  source to 2,088 chunks; four focused tests pass; the strict manifest covers
  48/48 required snapshots; and the database audit finds 145,258 chunks and
  exactly 145,258 embeddings with no empty repository. This does not establish
  a retrieval-quality gain.

## H14 — benchmark identity must include the serving retrieval configuration

Claim: a benchmark that identifies a Delphi deployment only by host/port can
silently score a different retrieval stack after listener reuse; every search
must return non-secret configuration provenance and the scorer must fail on a
predeclared mismatch.

- Evidence: two apparent repeat runs were served after another worker replaced
  their ports. The run labelled exact/current actually used HNSW
  `ef_search=100`, while the run labelled exact/file-BM25=0.15 used HNSW
  `ef_search=400` with file-BM25 disabled. Aggregate metrics happened to look
  plausible, so score inspection alone did not expose the collision.
- Intervention: every code-search response now reports vector mode, HNSW
  depth, embedding model, active branches and fusion weights, reranker/query
  expansion/listwise settings, RRF constant, and seed. The ARB runner accepts
  an expected configuration subset, records the observed snapshot, and stops
  after the first mismatch.
- Disconfirmers: missing or secret-bearing provenance, a mismatched endpoint
  completing as valid, or configuration checks changing ranking behavior.
- Status: supported as an evaluation-validity invariant. The two collided runs
  are marked invalid; focused backend/scorer tests pass; fresh guarded exact
  and file-BM25 repeats reproduce all 48 metric rows and top-20 lists exactly.

## H15 — provider top-k must match the scored retrieval boundary

Claim: asking Delphi for 100 files and truncating to 20 in the client changes
the backend selection problem and can hide candidates that would survive if
reranking and branch preservation operated at the actual scored boundary.

- Test: pair guarded exact/current and exact/file-BM25 runs at API `top_k=100`
  versus `top_k=20`, keeping the final metric limit at 20.
- Disconfirmers: no movement, fewer any-gold cases at 20, or a repeat that
  fails exact ranking reproduction.
- Status: supported on independent development for the current stack. API
  `top_k=20` raises any-gold from 38/48 to 40/48 with two complete recoveries
  and no complete loss; R@20 moves +0.0347 [-0.0139, 0.0972] and R@5
  +0.0382 [0.0000, 0.0868], while BCY moves -0.0104. One multi-gold case
  loses partial recall, so the effect is not monotonic per case. A guarded
  repeat reproduces all 48 metric rows and top-20 lists exactly. The harness
  now defaults provider fetch depth to the scored limit and requires
  over-fetching to be explicit. File-BM25 does not share the gain at 20 and
  remains disabled.

## H16 — normalize query tokens against repository paths

Claim: coding queries often spell a module concept with prose punctuation
(`direct-origin`, `default types`) while repository paths use underscores or
directories. A deterministic candidate source that camel/alphanumeric-tokenizes
both query and path and applies repository-local IDF can recover these files
without another hosted stage.

- Development diagnostic: reserve one rank-20 slot for the highest-scoring
  distinct path-token candidate, with no gold-aware selection. On the
  independent 48-case set this raises any-gold from 40 to 42 with two
  recoveries and no loss (McNemar p=0.5), and R@20 from 0.764 to 0.789
  (delta +0.0250, repository-bootstrap interval [0.0000, 0.0708]). It finds
  `crates/ignore/src/default_types.rs` and
  `src/poetry/packages/direct_origin.py`.
- Cross-corpus pressure: the same one- and two-slot simulations do not move
  the 75-case ARB development result; three slots improve fractional R@20 from
  0.649 to 0.653 on two already-hit cases, with no complete recovery or loss.
- Native independent result: a default-off branch now ranks explicitly scoped
  repository paths by the diagnostic's token/IDF score, contributes one chunk
  per file before fusion, exposes `path_token` provenance, and attests its
  serving flag and weight. The first arm recovered only `direct_origin.py`.
  Its top path for the remaining miss, `types.rs`, already existed in the
  fused set; alignment attached the file-level signal there and incorrectly
  consumed the branch's preservation slot while rank-two
  `default_types.rs` stayed outside the rerank window.
- The selector now treats an aligned multi-source file as agreement, not as the
  file-level branch's novel-file coverage. It preserves one standalone
  `path_token` candidate. The corrected native arm reaches MRR 0.629, R@5
  0.667, R@20 0.793, BCY 0.528, and any-gold 42/48 versus 0.597, 0.646,
  0.764, 0.517, and 40/48 for current. Both simulated recoveries become native
  recoveries with no any-gold loss (McNemar p=0.5). Repository-bootstrap
  intervals for MRR [-0.0175, 0.0932], R@5 [-0.0208, 0.0736], and R@20
  [-0.0069, 0.0792] include zero; BCY is +0.0111 [0.0000, 0.0278].
- A guarded repeat reproduces all 48 metric rows and top-20 lists exactly.
  Its warm-cache mean/median latency is 152/131 ms versus 146/136 ms for the
  current exact reference; the first corrected run includes hosted-stage cold
  misses and is not an isolated branch-latency estimate.
  Keep the branch default-off and do not adopt a deterministic final-tail
  replacement from the simulation.
- Defect review found and closed zero-hit fusion rescaling, overstated
  unscoped/non-hybrid provenance, incoming-source-blind replacement,
  acronym-boundary tokenization, chunkless-file ranking, and unbounded
  transfer/Python scoring. A second review reports no residual finding. The
  post-review config-attested `r4` arm matches guarded `r3` exactly on all 48
  metric rows and top-20 lists, so these correctness fixes neither create nor
  erase the development gain.
- Disconfirmers: the native branch fails to retain either independent
  recovery, displaces a current any-gold case, lowers MRR/BCY materially, or
  acts only through benchmark-specific path strings.
- Status: rejected for default adoption; retained as an opt-in. On the fresh
  75-case ARB development gate, path-token moves MRR +0.013610 and R@5
  +0.040000 but R@20 -0.006667 and BCY@8k -0.008889. Every
  repository-cluster interval includes zero. It recovers two any-gold cases and
  loses two, leaving acquisition at 54/75 for both arms (McNemar p=1.0).
  Guarded warm repeats reproduce every metric row and top-20 list exactly for
  both stacks. The independent gain therefore does not generalize cleanly
  enough to justify a default change. Final splits remain untouched.

## H17 — every benchmark gold file must be searchable before scoring

Claim: source-level success (`files_indexed > 0`, `chunks_created > 0`) is
necessary but not sufficient for a valid file-retrieval benchmark; every target
gold path must map to at least one indexed chunk in the exact source snapshot.

- Evidence: native Playwright provisioning legitimately skips nine files above
  the 500 kB `tsvector` safety cap while the repository as a whole remains
  searchable. The corresponding development case's gold
  `packages/playwright-core/src/tools/dashboard/dashboardApp.ts` is not among
  those skips, so no defect is established for that case.
- Test: after 68/68 provisioning, join each of the 75 development cases'
  normalized target gold paths to its source-specific repository file and chunk
  rows. Refuse to score on any missing gold path and preserve the missing paths
  as an audit artifact.
- Disconfirmers: the audit reports a missing gold path, a path resolves only in
  another revision, or a file row exists without a searchable chunk.
- Status: supported as a validity invariant. The exact 68-source development
  cohort has 116,424 files, 548,545 chunks, and 548,545 embeddings, with no
  missing, empty, duplicate, or chunk/embedding-mismatched source. Both fresh
  Delphi arms then passed the source-specific gold-path preflight before any
  case was scored. Final splits remain untouched.
