# Active state

Last updated: 2026-09-09 (IST), round 4.

## 2026-09-09: round 4 (review response) — see context/ROUND4_WORKSTREAM.md

- Exposure ledger written; ARB round-3 final reclassified C2. Confirmatory
  sets are C0 only: SWE-bench 62 (+100 expansion, scoring in progress) and
  independent 18.
- Matched conventional ladder complete on all three sets
  (`{I,D,A}-final-{dense,hybrid,hybrid_rerank,hybrid_rerank_expand}-r4-v1`,
  paired analyses `*_delphi_vs_*_r4_v1.json`). Independent: conventional
  stack ahead with intervals excluding zero (R@20 -0.120 [-0.231,-0.019];
  MRR -0.111 [-0.200,-0.034]). SWE-bench: Delphi +0.083 MRR [-0.107,+0.203]
  vs the full rung (tie); the reranking head explains most of the margin over
  lexical systems (hybrid 0.296 -> +rerankers 0.575 -> +expansion 0.597 vs
  Delphi 0.680). ARB (C2): +0.103 MRR [-0.008,+0.189].
- Documentation fully matched: hosted engine's own retrieved sources through
  the frozen stage score 0.583 (raw 0.475); four-arm tie; all engine CIs
  include zero (`DOCS-dev-answer-synthesis-analysis-v3.json`).
- Determinism like for like (`DETERMINISM-docs-like-for-like-v1.json`):
  retrieved-set exact 1.000 (synthesis engine, cited URLs) / 0.980 (Delphi) /
  0.542, 0.496 (documentation engine).
- SWE-bench expansion complete (98 C0 cases after two engine-agnostic rules):
  Delphi 0.700 / 0.745 / 0.820 / 0.685 vs conventional final rung 0.660 / 0.684
  / 0.733 / 0.603; Delphi leads on R@5, R@20, BCY with intervals excluding
  zero, MRR tied. Pooled 160: MRR +0.057 [-0.036, +0.114]; R@5 +0.069
  [+0.015, +0.160]; R@20 +0.084 [+0.013, +0.154]; BCY +0.076 [+0.017, +0.128].
- Executable pilot, two repeats complete (62 instances, step 50): resolved
  25/30/31/23 then 25/27/25/25 (none/random/delphi/conventional). Pooled:
  Delphi - none +0.048 [-0.008, +0.113]; Delphi - random -0.008 [-0.073,
  +0.056]. No seed effect resolved at this size.
- Nia: fresh single-shard smoke with the new key timed out `syncing` at 40
  minutes; arm remains externally blocked.
- Frozen stack instances stopped after scoring; database
  `delphi_r4_swebench_expansion_20260909` retained for audit.
- Paper rewritten (`paper/context.tex`, 12 pages, every table generated from
  artifacts by `harness/paper_tables.py`); no pending markers remain.
- Claim policy: no SOTA claim; no confirmatory claim on ARB; documentation
  "parity" withdrawn.


## 2026-08-25 night: deliverables session (user-directed)

- Fair ordeal completed across all engines. Context7's recorded guided
  contexts through the same frozen synthesis stage score 0.625
  (0.650/0.600/0.625, zero failures). Final matched-contract standings:
  Context7+synth 0.625, Delphi+synth 0.6167, Nia native synthesis 0.575,
  model-alone control 0.4917. Every engine-vs-engine case-cluster CI
  includes zero (Delphi−Nia +0.042 [-0.092,0.183]; C7−Nia +0.050
  [-0.092,0.192]; Delphi−C7 −0.008 [-0.117,0.092]). Retrieval-over-floor:
  C7 +0.133 [0.008,0.258] (excludes zero), Delphi +0.125 [0.000,0.250],
  Nia +0.083. Analysis: DOCS-dev-answer-synthesis-analysis-v2.json. Atlas
  runs even-fire-9717, flat-bone-1314, firm-edge-0219.
- Fair downstream completed: GEN-dev-delphi-synthesis (3 repeats) scores
  pass@1 0.5917 (0.575/0.600/0.600); vs none +0.0167 [-0.125,0.158]; vs
  Nia −0.050 [-0.183,0.075]. All DS-1000 deltas remain unresolved. Atlas
  run slow-drum-5569.
- Product PRs: #85 (deterministic hybrid retrieval + agent-mode
  generated-source indexing + typing fixes) went green on all CI jobs and
  was auto-squash-merged into master at 9d5a559. #86 (file-level Okapi
  branch, default-off, compact JSONB storage, schema 021/022) rebased onto
  the squashed master, full suite green (1102 passed; postgres contracts
  70 passed incl. a planner-stability fix to the GIN pushdown test),
  MERGEABLE pending CI. Local master now tracks origin at 9d5a559; frozen
  provenance branch feature/generated-source-freeze retained at 91d76c1.
- Research blog built at new/round3/blog/site (serve:
  `python3 -m http.server 8909` from that directory; currently running on
  http://127.0.0.1:8909/). All data generated from artifacts by
  harness/build_blog_data.py: final tables with CIs, per-case trace
  explorers for all three finals (220/62/18 cases, per-engine top-20 with
  gold highlighting), the matched-contract docs section with every
  synthesized answer readable and gold identifiers marked, DS-1000 pass
  matrices, 10x10 determinism grids, latency strips, hosted-arm
  transparency timeline, and the claim/no-claim ledger.
- ICLR paper (new/round3/paper/context.tex) fully rewritten with all
  final results, the fair ordeal, determinism resolution, Track C/D, the
  blocked hosted arm, and claim policy; every table value cross-checked
  against artifacts (three transcription errors caught and fixed:
  Track D BM25 row, independent R@5 baselines, one BCY CI). Compiles to
  8 pages, zero errors, zero overfull boxes.
- Nia ingestion probe (terminal): the minimal shard never left `syncing`
  across the 40-minute deadline plus the full 3-hour watcher
  (WATCH_RESULT=STILL_SYNCING, 2026-08-26T04:28Z). Hypothesis
  thin-helm-2134 closed rejected on its predeclared disconfirmer (basis
  run cool-ash-4717). The repository arm is externally blocked again with
  minimal-shard evidence; 32/68 pairs remain indexed from round 2; the
  fan-out never launched. Retry only when a fresh single-shard smoke
  demonstrably reaches terminal state.

## 2026-08-25 evening: fair-comparison workstream (user-directed)

- Answer-style synthesis parity (docs, development; Atlas `mild-flaw-1796`,
  runs `even-fire-9717`/`flat-bone-1314`): Delphi compact k=20 retrieval +
  answer-style gpt-5.4-mini synthesis scores case-mean identifier hit
  0.6167 (repeats 0.600/0.625/0.625, zero failures) vs Nia's recorded
  0.575 under the same output contract. Paired delta +0.042, case-cluster
  CI [-0.092, +0.183]: parity-or-better supported, superiority not claimed.
  No-retrieval control at 0.4917 establishes the parametric floor: the
  prior 0.575-vs-0.400 documentation gap was an output-contract artifact,
  not a retrieval deficit. End-to-end ~5.5 s vs Nia 12.4 s.
- Nia repository arm reopened per user instruction (Atlas `thin-helm-2134`):
  the delphi/.env credential scope exposes 389 terminally indexed sources
  including 32/68 required round-3 development pairs under
  `/arb-v2-sharded/...`. Sharded ingestion of the remaining 36 pairs is in
  flight via `harness/provision_nia_sharded.py` (smoke-first on
  gin-gonic/gin, then gated fan-out). If 68/68 reach terminal indexed
  state, the previously invalid Nia repository comparison becomes runnable
  via `run_arb.py --engine nia` on the 75-case development split.

## Objective

Earn a predeclared Delphi state-of-the-art result rather than writing one into
existence. The active work is exploration, benchmark execution, failure
analysis, and general product iteration. Paper and blog editing are paused until
the experimental picture is stable.

## Non-negotiable guards

- ARB round-3 development may guide changes; round-3 final stays untouched
  until the winner is frozen.
- SWE-bench Track D stays untouched until freeze.
- A hosted-engine run must cover every sampled `(repo, base_commit)` pair.
  Partial runs abort and cannot enter comparisons.
- Context7 is a documentation retriever and is evaluated on a separate
  documentation-grounded track, not inserted into ARB repository tables.
- Product changes must express general retrieval invariants, carry regression
  tests, and survive an ablation. No benchmark-ID, repository, or gold-path
  rules.
- Benchmark data, results, and this context packet remain under gitignored
  `new/round3/`.

## Completed, reportable measurements

- ARB development, July Delphi: MRR 0.285, R@5 0.427, R@20 0.544,
  BCY@8k 0.313 on 75 cases.
- ARB development, patched 3-small Delphi: MRR 0.337, R@5 0.442, R@20
  0.642, BCY@8k 0.320. Versus July, repository-cluster bootstrap deltas are
  MRR +0.052 [-0.012, 0.139], R@20 +0.098 [0.041, 0.186], and BCY +0.007
  [-0.087, 0.120]. It recovers ten July misses and loses four.
- ARB development, complete deterministic exact-scan Delphi: two 75-case
  repeats are bit-for-bit identical at MRR 0.342, R@5 0.476, R@20 0.649,
  BCY@8k 0.302. Against the earlier patched run, deltas are MRR +0.004
  [-0.012, 0.027], R@20 +0.007 [0.000, 0.021], and BCY -0.018
  [-0.050, 0.022]. It recovers one any-gold@20 case and loses none.
- The matched HNSW run is also exactly repeatable within the live process but
  scores MRR 0.339, R@5 0.469, R@20 0.629, BCY 0.309. Exact scan recovers two
  any-gold@20 cases with no losses and changes R@20 by +0.020 [0.000, 0.063].
- Disabling query expansion on the exact stack lowers MRR from 0.342 to 0.331
  and R@20 from 0.649 to 0.620. Expansion recovers three complete misses and
  loses one; it remains enabled.
- ARB development, Gemini embedding candidate: MRR 0.284, R@5 0.476, R@20
  0.653, BCY@8k 0.338. Against patched 3-small, MRR changes by -0.054
  [-0.102, -0.011], while R@20 changes by +0.011 [-0.032, 0.067] and BCY by
  +0.018 [-0.081, 0.113]. Gemini is rejected as the replacement winner.
- Three patched full repeats keep R@20 exactly 0.642 but vary MRR
  0.3299--0.3374 and BCY 0.3067--0.3200. Pairwise exact top-10 lists are
  68.9%, top-10 Jaccard 0.930, and shared-item Kendall tau 0.943. This misses
  the 95% exact-list target.
- Exact vector scan plus single-flight hosted calls initially still diverged;
  paired traces isolated an unordered BM25 cutoff tie and then a timed-out
  expansion whose waiter retried. Total SQL ordering plus complete flight
  outcome sharing now gives exact and HNSW 100% exact lists in two concurrent
  8-query x 10-repeat packets and in two concurrent 75-case repeats. Exact and
  HNSW are not equivalent: only 2/8 packet lists match and mean top-10 Jaccard
  is 0.849.
- A genuine API cold restart exposed the boundary of the in-memory result:
  exact scan reproduced only 1/8 lists (Jaccard 0.810) and HNSW 3/8
  (Jaccard 0.890). Hosted expansion, listwise, and embedding outputs therefore
  still move across process lifetimes. A safe optional SQLite-backed cache for
  strings and NumPy vectors is now wired through all three stages. After one
  fill packet, all 8/8 lists remain exact across two actual API restarts
  (24/24 pairwise corresponding lists). Mean packet latency falls from 4.90s
  on cache fill to 1.48s and 1.79s after restart. This establishes
  restart-durable repeatability from the first persisted answer; it does not
  claim that two unrelated clean installations choose the same first answer.
- ARB development, official BM25 over canonical git: MRR 0.144, R@5 0.173,
  R@20 0.391, BCY@8k 0.104.
- ARB development, official lexical ranker over canonical git: MRR 0.092,
  R@5 0.149, R@20 0.373, BCY@8k 0.062.
- Independent commit-to-files development, 48 locked cases: whole-file BM25
  scores MRR 0.419, R@20 0.642, BCY 0.390; the official lexical ranker scores
  MRR 0.462, R@20 0.732, BCY 0.440. Lexical recovers six any-gold@20 cases and
  loses none (McNemar p=0.031); its paired R@20 delta is +0.090
  [0.024, 0.174].
- A development-tuned file-level RRF (`lexical=0.7`, BM25=0.3) scores MRR
  0.469, R@5 0.551, R@20 0.732, and BCY 0.433 on those same 48 cases. It
  improves the lexical point estimates for MRR/R@5 but lowers BCY; all paired
  quality intervals include zero, so both remain required comparators.
- July Delphi retrieval determinism, 8 queries x 10 repeats: exact top-10 list
  0.306, Jaccard@10 0.760, Kendall tau 0.959.
- Embedding determinism, 12 texts x 20 repeats:
  - OpenAI 3-small: exact vector 0.693, max cosine distance 2.323e-4,
    top-10 identical 1.000.
  - OpenAI 3-large: exact vector 0.806, max cosine distance 5.059e-5,
    top-10 identical 0.987, top-10 set Jaccard 1.000.
  - Gemini embedding-001: bitwise equal 1.000, top-10 identical 1.000.
  - Local MiniLM-L6-v2 and MPNet-base-v2 on CPU: bitwise equal 1.000,
    max cosine distance 0, top-10 identical 1.000.
- Persistent/single-flight caching, retrieval selection, query expansion,
  listwise, SQL ordering, configuration, branch preservation, and chunk-limit
  regressions: the current intervention suite is 99 passed. The latest
  benchmark scorer, paired-analysis, sweep-analysis, and balanced-Nia
  accounting command is 21 passed; PostgreSQL retrieval/reindex integration is
  15 passed against the native database.
- Track C no-seed baseline, 40 paired cases: File F1 0.0458,
  final-any-gold 0.075, and any-gold-acquired 0.075.
- Track C controls on the same 40 cases:
  - random seed: File F1 0.0125, final-any-gold 0.025;
  - BM25 seed: File F1 0.0925, final-any-gold 0.175;
  - oracle seed: File F1 0.8575, final-any-gold 0.975;
  - lexical seed: File F1 0.1192, final-any-gold 0.250;
  - July Delphi seed: File F1 0.2342, final-any-gold 0.475, and
    any-gold-acquired 0.550. Versus no seed, File F1 delta is +0.188
    [0.055, 0.294]; versus BM25 it is +0.142 [0.059, 0.208]. Versus lexical,
    final-any-gold improves by 0.225 with paired McNemar p=0.035, while the
    File F1 interval narrowly includes zero [-0.002, 0.190].
- Documentation retrieval over 40 development cases:
  - Nia synthesized context: identifier hit 0.575 with full prompts and 0.450
    with compact prompts.
  - Delphi: 0.300 with full prompts and 0.400 with compact prompts.
  - Context7: 0.275 with automatic canonical-name resolution and compact
    prompts; 0.375 with an automatic quality-guided resolver and 0.375 with
    oracle IDs.
- Documentation determinism, 10 cases x 10 runs:
  - Delphi compact: exact context 0.980, hit agreement 1.000, mean item-set
    Jaccard 0.993; every run hit 0.300.
  - Context7 oracle compact: exact context 0.253, hit agreement 0.909, mean
    item-set Jaccard 0.806; run hit rates ranged from 0.200 to 0.400.
  - Context7 quality-guided compact: exact context 0.356, hit agreement 0.918,
    mean item-set Jaccard 0.835; run hit rates ranged from 0.200 to 0.300.
  - Nia full retrieval+synthesis: exact context 0.000, hit agreement 0.929,
    normalized citation-set Jaccard 1.000; run hit rates ranged from 0.500 to
    0.700.
- Context7 resolver-only stability, five canonical package identities x 10
  balanced repeats: all 50 `/api/v2/libs/search` requests completed with no
  retries, warmups, snippet calls, or technical failures. Quality-guided
  selected IDs were pairwise exact on all 225 within-package comparisons
  (1.000), while candidate-list exactness was 0.556 and mean set Jaccard was
  0.862. TensorFlow selected `/tensorflow/tensorflow` in all ten current
  identity-only requests, not the `/tensorflow/docs` ID pinned by the earlier
  ablation.
- Valid DS-1000 downstream generation, 40 cases x 3 frozen-model repeats:
  - no retrieval: pass@1 0.575 mean (0.575, 0.550, 0.600);
  - Delphi compact `k=5`: 0.592 (0.600, 0.575, 0.600), delta +0.017,
    case-cluster bootstrap CI [-0.108, 0.142];
  - Nia retrieval+synthesis full: 0.642 (0.625, 0.675, 0.625), delta
    +0.067, CI [-0.075, 0.200];
  - Context7 guided compact: 0.567 (0.600, 0.600, 0.500), delta -0.008,
    CI [-0.142, 0.125].
  One exploratory Delphi `k=20` run scored 0.500. No engine's downstream delta
  is yet distinguishable from zero.
- File-Okapi experiment (Goal 1, closed). Per-file term statistics use compact
  JSONB storage, 26.67x smaller per file. Six review defects were fixed
  test-first at commit `b915d5f` on `feature/file-okapi`. The agent-mode
  generated-source indexing fix was committed at `3565123` after a locked gold
  path (`channelz/grpc_channelz_v1/channelz.pb.go`, 114,500 bytes) was
  excluded by the global `*.pb.go` pattern in both the old and new indexes;
  the queued legacy worker now enforces the same 500,000-byte and NUL guards.
- Fresh isolated cohorts under the new generated-source policy: independent
  48/48 sources with 44,336 files at exact coverage, 151,533 chunks, and
  151,533 embeddings; ARB development 68/68 with 116,546 files at exact
  coverage, 555,340 chunks, and 555,340 embeddings. Disabled-branch controls
  repeat exactly on all 48/48 and 75/75 metric rows and top-20 lists.
- New independent disabled baseline: MRR 0.6577, R@20 0.7819, BCY 0.5806. New
  ARB development disabled baseline: MRR 0.3149, R@20 0.62, BCY 0.2733.
- The File-Okapi candidate (weight 0.15, `k1=1.2`, `b=0.75`, file cap 50)
  repeated exactly and lost zero any-gold cases, with Recall@20 +0.018
  [0.000, 0.039], but failed the preregistered gates: the MRR interval lower
  bound -0.050 and the BCY lower bound -0.0368 are below the -0.01 floor, and
  the median latency ratio 1.342 exceeds the 1.2 bound. The candidate is
  rejected with no ARB candidate arm and no second configuration; hypothesis
  `dry-cave-0210` is closed rejected. Atlas run `wide-haze-0900` and decision
  `flat-foam-8342` record the outcome.
- Final freeze amendment: the confirmatory stack is frozen at branch
  `feature/generated-source-freeze` commit `91d76c1`, equal to master
  `c17c186` plus the cherry-picked `3565123` generated-source fix. All final
  scoring used exact vectors, API `top_k=20`, configuration attestation, and
  the gold-searchability preflight.
- ARB final (Goal 2, complete): 142/142 sources provisioned into
  `delphi_native_arb_final_generated_20260825`; the audit is complete at
  229,836 files, 1,089,836 chunks, and 1,089,836 embeddings with zero
  mismatches; the manifest sha is `c695f37f...`; the database was dropped
  after the artifacts were secured.
- ARB final Delphi, `A-final-delphi-generated-source-exact-top20-v1`: 220/220
  cases with zero failures, MRR 0.3319, R@5 0.4761, R@20 0.6478, BCY@8k
  0.2958. Comparators on the same 220 cases (MRR/R@5/R@20/BCY): BM25
  0.1276/0.1773/0.4246/0.0746; lexical 0.1440/0.2148/0.4777/0.1383;
  `lexical_bm25` RRF 0.1602/0.2038/0.5178/0.1242.
- ARB final paired repository-cluster bootstrap: Delphi versus every
  comparator is positive on all four metrics with all 95% intervals excluding
  zero; versus RRF, MRR +0.1717 [0.0825, 0.2354] and R@20 +0.130
  [0.0243, 0.1995]. Any-gold is 163 versus 113 against BM25 (p=5.0e-9) and
  163 versus 123 against lexical (p=2.4e-6). Artifacts:
  `results/arb_final_delphi_vs_{bm25,lexical,lexical-bm25}_v1.json`.
- Independent final (Goal 3 part 1, complete), 18/18 cases. Delphi
  `I-final-delphi-generated-source-exact-top20-v1`: MRR 0.5083, R@5 0.5509,
  R@20 0.75, BCY 0.4537. Comparators (MRR/R@20/BCY): BM25
  0.3700/0.6759/0.2593; lexical 0.4380/0.7037/0.2593; `lexical_bm25`
  0.4729/0.7593/0.2870. Delphi beats BM25 and lexical on R@20 with intervals
  excluding zero (+0.074 [0.019, 0.139]; +0.046 [0.009, 0.083]) and is
  statistically tied with RRF (R@20 -0.009 [-0.148, 0.083]; MRR +0.035
  [-0.211, 0.259]; any-gold 15 versus 15). Artifacts:
  `results/independent_final_delphi_vs_*_v1.json`.

## Invalidated evidence

- `A-dev-nia` was cancelled after 14 cases. Its old manifest contained 68
  indexed rows but overlapped only 32 of 68 required snapshots, so 39 of 75
  cases would have been skipped.
- Nia identifiers under `/arb3/...` collided across accounts: daemon creation
  returned old-account IDs, while account-scoped source reads returned 404.
  A unique `/arb3-new/...` namespace was tested successfully and is now used.
- Nia's replacement repository provision is externally blocked. Three
  independent sources stayed `syncing` for more than 40 minutes without a
  backend error and timed out; the account inventory still showed all six
  `/arb3-new/` sources as `syncing`, including the smoke source. The 68-snapshot
  fan-out was stopped rather than allowed to consume days. No partial Nia
  repository score is valid.
- Prior DS-1000 95% and prior final-split numbers are exposure context, not
  round-3 evidence.
- `A-dev-delphi-r3b-patched-3small` is invalid: all 75 requests returned HTTP
  401 because the first launch used the wrong local stack key. The dashboard
  row and summary are explicitly marked invalid. The authenticated run is
  `A-dev-delphi-r3b-patched-3small-v2`.
- `C-dev-delphi-jul-frozen` is diagnostic-only: one of 40 model calls timed out
  and the old summarizer excluded it, inflating the denominator. Its 39-case
  values are not reportable. `C-dev-delphi-jul-frozen-r2` is the fail-closed
  replacement.
- The first exact-scan/single-flight validation runs were stopped after 11
  cases when their candidate pools exposed an unordered BM25 score tie. They
  are marked invalid and exist only as root-cause traces; the total-order rerun
  replaces them.
- `I-dev-{bm25,lexical}-v1` are invalid zero-case partial-clone attempts.
  `I-dev-{bm25,lexical}-v2` are invalid 43-case performance diagnostics:
  per-file `git show` subprocesses made large snapshots take minutes. The
  complete v3 runs read immutable materialized snapshots and replace them.

## Running now

- Track D (Goal 3 part 2) is the only open confirmatory work. The 62-case
  SWE-bench corpus contains patch markers in 0/62 queries. Provisioning into
  `delphi_native_swebench_generated_20260825` under frozen commit `91d76c1`
  stood at 51/62 sources with zero failures at the time of writing. The
  remaining steps are preregistered in order: exact file/chunk/embedding
  audit, per-gold-path searchability preflight, one one-shot Delphi run,
  BM25/lexical/`lexical_bm25` comparators, and paired analysis.
- Claim policy: no SOTA claim is made. The Nia repository arm remains invalid
  at 0/68 sources. ARB final shows decisive leadership over all local
  comparators, the independent final shows lead-or-tie, and Track D is
  pending.

## Immediate triggers

1. Complete Track D from frozen commit `91d76c1`: finish provisioning the
   remaining 11 of 62 sources into
   `delphi_native_swebench_generated_20260825`, then run the preregistered
   sequence exactly once and in order — exact file/chunk/embedding audit,
   per-gold-path searchability preflight, the one-shot Delphi run,
   BM25/lexical/`lexical_bm25` comparators, and paired analysis. Fail closed
   on any provisioning, audit, or preflight gap.
2. Keep every remaining confirmatory number on the frozen generated-source
   stack: branch `feature/generated-source-freeze` commit `91d76c1`, exact
   vectors, API `top_k=20`, configuration attestation, and the
   gold-searchability preflight.
3. Treat the File-Okapi rejection as final. The single approved configuration
   failed its preregistered MRR/BCY/latency gates; run no ARB candidate arm
   and tune no second configuration. Hypothesis `dry-cave-0210` stays closed
   rejected.
4. Continue to withhold every SOTA claim until Track D completes and the
   protocol claim rule is satisfied. Report ARB final as decisive leadership
   over all local comparators and the independent final as lead-or-tie; the
   Nia repository arm remains invalid at 0/68 sources. Preserve the secured
   final artifacts; the ARB final database is already dropped.
5. Preserve the completed Track C paired analysis and the closed
   documentation-track selections: make no further Nia documentation calls,
   keep Context7 library IDs pinned, and spend no new hosted requests without
   a separately predeclared, decision-relevant question.
