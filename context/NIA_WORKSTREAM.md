# Nia hosted-comparator accounting

Updated: 2026-08-25. Scope: exploration, benchmarking, and comparator
validity only. No locked final split was inspected, no Delphi product code was
changed, and no commit or push was made.

## 2026-08-25 answer-style synthesis parity (documentation, development)

User-directed fair-comparison experiment, predeclared as Atlas hypothesis
`mild-flaw-1796` / plan `full-clay-9675`. Nia's recorded 0.575 scores
identifier hits on synthesized answer text; Delphi's recorded numbers score
raw retrieved context. The new arms match the output contract instead:

- `delphi_answer_synthesis`: recorded Delphi compact `k=20` contexts reused
  verbatim + answer-style gpt-5.4-mini synthesis (model knowledge allowed,
  retrieved paths cited), 40 cases x 3 repeats, zero failures. Case-mean
  identifier hit **0.6167** (repeats 0.600/0.625/0.625).
- `synthesis_no_retrieval`: same contract, no retrieved context. Case-mean
  **0.4917** (0.475/0.475/0.525). This is the parametric-knowledge floor of
  the metric under synthesis contracts.
- Paired vs Nia recorded full pass: delta +0.042, case-cluster bootstrap 95%
  CI [-0.092, +0.183]; 6 wins / 6 losses / 28 ties. Parity-or-better is
  supported; statistical superiority is not claimed.
- Retrieval contribution over the floor: Delphi +0.125 (case CI touching
  zero at [0.000, 0.250]); Nia +0.083 (library CI [-0.192, -0.008] for the
  floor's deficit).
- End-to-end latency: recorded retrieval 3.09 s + synthesis 2.46 s ≈ 5.5 s
  versus Nia's hosted 12.4 s.
- Interpretation: the prior documentation gap (0.575 vs 0.400) was an
  output-contract artifact, not a retrieval deficit. Under matched
  contracts Delphi's own retrieval plus a frozen synthesis stage meets the
  predeclared >=0.575 criterion. Both engines sit close to a ~0.49
  parametric floor, so identifier-hit under synthesis contracts is a weak
  retrieval discriminator; raw-retrieval numbers remain the cleaner signal.
- Artifacts: `results/DOCS-dev-delphi-answer-synth-r{1,2,3}-{details,summary}.json`,
  `results/DOCS-dev-control-synth-r{1,2,3}-{details,summary}.json`,
  `results/DOCS-dev-answer-synthesis-analysis-v1.json`. Atlas runs
  `even-fire-9717`, `flat-bone-1314`. No new Nia request was spent.

## 2026-08-25 repository re-audit: ingestion reopened

The delphi/.env `NIA_API_KEY` credential exposes a different scope than the
2026-08-24 audit key: 394 visible sources, 389 terminally indexed, including
366 under `/arb-v2-sharded/...` covering **32 of the 68** required round-3
development `(repo, base_commit)` pairs. The four permanently-`syncing`
sources are exactly the whole-snapshot pushes of large repositories under
`/arb3/...` (etcd x2, tokio, transformers). Sharded ingestion (one bounded
source per <=100-file / <=1.5 MB batch, polled to terminal individually)
demonstrably terminates on this account.

Per explicit user instruction, ingestion was reopened under Atlas hypothesis
`thin-helm-2134` / plan `wide-root-1378` using
`harness/provision_nia_sharded.py` with the round-2 path scheme
(`/arb-v2-sharded/<repo>/<commit>/shard-NNNN-of-MMMM`), smoke-first
(smallest missing pair: gin-gonic/gin@28e57f58), then a fan-out of the
remaining 36 pairs gated on smoke success. Manifest:
`results/nia-sharded-sources.jsonl`.

Smoke outcome (terminal): the shard (source `eee1e255`, <=1.5 MB, <=100
files) was accepted by `daemon/sources` and `daemon/sync` but never left
`syncing` — the 2,400 s polling deadline (Atlas run `cool-ash-4717`) plus an
18-poll, 3-hour watcher all returned `syncing`
(`WATCH_RESULT=STILL_SYNCING`, ended 2026-08-26T04:28Z; ~3.7 h total from
sync acceptance). Twelve historical gin snapshots on the same account are
`indexed`, including same-shape single shards, so the request pipeline is
correct and the blocker is the provider's ingestion queue. Hypothesis
`thin-helm-2134` is closed **rejected** on its predeclared disconfirmer; the
36-pair fan-out stays gated off and the repository arm returns to
externally-blocked status pending provider-side ingestion recovery. Any
future retry should begin with one smoke shard, not a fan-out. The
`decision:add` recording the reopen returns HTTP 500 from the backend
repeatedly; the decision is carried here, in `STATE.md`, and in Atlas note
`loud-knot-7966` until the endpoint recovers.

## 2026-08-25 night: matched-contract closure

With the Context7 arm complete (0.625 case-mean over 3 repeats), the
matched-output-contract comparison is closed as a three-way engine tie above
the 0.4917 model-alone floor: Delphi−Nia +0.042 [-0.092, 0.183], C7−Nia
+0.050 [-0.092, 0.192], Delphi−C7 −0.008 [-0.117, 0.092]. Nia's native
synthesized pass no longer reads as a documentation-quality lead; it reads
as the most expensive (12.4 s) and least repeatable (0.000 exact-context)
way to reach the same tier. The fair downstream arm
(`GEN-dev-delphi-synthesis`, pass@1 0.5917) keeps all DS-1000 deltas
unresolved in both directions.

## Bounded pass

- New hosted search queries: exactly 100 of 100 allowed.
- Retry policy: none; every logical query made one HTTP attempt.
- Additional hosted reads: one read-only daemon source-inventory call.
- Hosted compact sweep elapsed time: 1,515.2 seconds (25m 15s); the full pass
  remained below 60 minutes.
- All new search calls used Nia query/source mode with `fast_mode=true`,
  `skip_llm=false`, source inclusion, semantic-cache bypass, and an 8,000-token
  response budget. This condition is **retrieval+synthesis**, not raw
  retrieval.

## Repository readiness: valid audit, no valid benchmark

Request mode: read-only repository-readiness audit. Corpus: ARB round-3
development, 75 cases across the four positive workflows, requiring 68 exact
`(repo, base_commit)` pairs from:

- `new/round3/samples/development/v2_code2test.jsonl`
- `new/round3/samples/development/v2_comment2context.jsonl`
- `new/round3/samples/development/v2_trace2code.jsonl`
- `new/round3/samples/development/v2_edit2ripple.jsonl`

The complete required pair list is recorded in
`results/nia-accounting-repository-readiness-20260824.json`.

- Available credential scope: SHA-256 fingerprint prefix `26f620352201`.
- `/arb3-new/` sources visible in that scope: 0.
- Ready required pairs: 0/68.
- Complete cases: 0/75.
- Request errors: 0.
- Audit latency: 1,002.7 ms.
- Synthesis involved: no.
- Audit validity: valid for this credential scope.
- Repository benchmark validity: invalid/not ready; no score was run or
  reported.

The previously observed scope with six nonterminal `/arb3-new/` sources is not
locally addressable with the available credential. This does not erase the
earlier evidence that those sources remained `syncing`; it means their current
state cannot be re-audited from this account.

## Compact-query documentation determinism: valid

Request mode: Nia documentation retrieval+synthesis with compact queries.
Corpus: the predeclared development determinism sample
`new/round3/samples/docs/determinism10.jsonl`, IDs
`538, 635, 339, 482, 277, 51, 887, 850, 680, 670` (two cases per library).

- Complete cases: 10/10 across all 10 repeats.
- Complete observations: 100/100.
- Errors: 0.
- Mean / median / p95 latency: 15.138 / 14.748 / 20.444 seconds.
- Mean packed context: 1,515.83 tokens.
- Exact synthesized-context rate: 0.000.
- All-five-citation ordered exact rate: 1.000.
- All-five-citation set exact rate / mean Jaccard: 1.000 / 1.000.
- Citation top-1 exact rate: 1.000.
- Identifier-hit agreement: 0.889.
- Per-run identifier hit: 0.200--0.300; mean 0.260.
- Synthesis involved: yes.
- Validity: valid and complete; no partial metric is included.

The 10-case quality number is a determinism-subset characterization, not a
replacement for the existing 40-case development estimate.

## Corrected full-query citation accounting

The ten existing full-query repeats were re-analyzed offline using all five
recorded citations per response. All 10 cases and 100 observations were
complete, with no errors.

- Exact synthesized-context rate: 0.000.
- All-five-citation ordered/set exact rate: 0.980.
- All-five-citation mean Jaccard: 0.9933.
- Citation top-1 exact rate: 1.000.
- Identifier-hit agreement: 0.929.
- Mean identifier hit: 0.600 (run range 0.500--0.700).
- Mean hosted latency: 12.205 seconds.
- Mean context: 1,414.44 tokens.
- Synthesis involved: yes.
- Validity: valid.

The earlier `1.000` citation Jaccard came from the synthesized-answer item's
single `raw_id`, which represents only the first citation. The all-five
citation result is therefore `0.9933`, not exactly `1.000`.

## Full versus compact on the same subset

Both conditions are complete (10 cases x 10 repeats each), and the comparison
is valid as a historical sequential-block comparison for this determinism
subset:

- Identifier hit: full 0.600, compact 0.260, delta -0.340.
- Cross-mode citation-set Jaccard: 0.6063.
- Cross-mode citation-set exact rate: 0.200; top-1 exact rate: 0.800.
- Compact mean latency was 1.240x full (+2.933 seconds).
- Compact synthesis was 101.39 mean tokens longer.

Compaction changes the retrieved evidence as well as the synthesis. It is not a
neutral shared query transform and should remain an engine-specific ablation.
The existing 40-case development runs remain the primary aggregate quality
estimates (full 0.575, compact 0.450).

## Balanced full-versus-compact replication: full wins

A later matched run removes the sequential-block caveat by alternating full
and compact requests within each case/repeat pair. It uses the same ten
development cases, five repeats, fixed per-library source IDs, exactly 100
hosted search requests, no warmups, and no retries. All 100 observations
completed without technical failure.

- Identifier hit: full 0.640, compact 0.240.
- Paired compact-minus-full delta: -0.400, case-cluster bootstrap 95% CI
  [-0.640, -0.160].
- Mean packed context: full 1,420.04 tokens, compact 1,520.62; compact adds
  100.58 tokens, CI [3.12, 192.02].
- Mean latency: full 12.423 seconds, compact 15.043; compact adds 2.620
  seconds, CI [1.392, 3.803].
- Cross-transform citation sets match exactly on 20% of paired observations;
  top-1 citations match on 80%; mean citation-set Jaccard is 0.606.
- Exact synthesized context remains 0.000 within both transforms.

This is the decisive development result for Nia query shape: compact prompts
are worse on quality, context volume, and latency under balanced acquisition.
Keep full prompts for Nia. The result remains specific to ten cases, fixed
source IDs, and one hosted-provider period; it does not convert Nia's
retrieval+synthesis output into raw retrieval evidence.

## Exact remaining blocker

Nia repository comparison remains blocked until one owned account exposes all
68 required ARB development `(repo, base_commit)` sources in a terminal indexed
state and account-scoped source reads succeed for every source. The only
currently available credential exposes 0/68 under `/arb3-new/`; the other
known scope previously stalled with six sources still `syncing` and is not
currently addressable. Re-running the same nonterminating ingestion is not a
valid next step. The needed resolution is hosted-side ingestion/account
recovery that can demonstrate complete terminal coverage; until then, no Nia
repository or Track C score is valid.

## Result files

- `new/round3/results/nia-accounting-repository-readiness-20260824.json`
- `new/round3/results/nia-accounting-docs-compact-determinism-20260824.json`
- `new/round3/results/nia-accounting-docs-full-citation-audit-20260824.json`
- `new/round3/results/nia-accounting-docs-query-transform-comparison-20260824.json`
- `new/round3/results/nia-accounting-balanced-full-compact-raw-20260824.json`
- `new/round3/results/nia-accounting-balanced-full-compact-analysis-20260824.json`
