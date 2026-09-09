# Round-4 workstream: answering the review

Started 2026-09-09 (IST) in response to two external reviews of the round-3
draft. The reviews' priority order was adopted as the work order: (1) exposure
and a defensible primary evaluation, (2) strong matched baselines, (3) a
same-task executable utility study, (4) the documentation-contract
inconsistency and the "parity" overclaim, (5) like-for-like determinism,
(6) inspectable methods and artifacts.

## Infrastructure restored

- Canonical corpora re-cloned from public GitHub with `harness/restore_corpora.py`
  (58 repositories, 365 snapshots; one transient clone failure on `astral-sh/ruff`
  retried successfully). Reports: `results/corpus-restore-2026-09-09*.json`.
- Pinned ARB implementation restored to `external/arb-src` at
  `d04953371d962ec314fb15d642255ed4e9dadd40`; `run_arb.py` resolves it from the
  archive.
- Frozen Delphi stack (`91d76c1`) checked out as a git worktree at
  `stack/freeze-worktree`, its locked environment installed with `uv sync
  --locked`, and served natively by `stack/native-r4-frozen.sh` against the
  isolated database `delphi_r4_swebench_expansion_20260909` (Alembic
  `018_context_sessions`), port 28742, with the round-3 configuration reproduced
  variable for variable.
- Provider keys for this round live in `~/.delphi-r4-secrets.env` (mode 600),
  outside every repository. The Anthropic key supplied on 2026-09-09 returned
  HTTP 401 and was not used; OpenAI and Google keys verified. The Nia key maps
  to the same account as before (395 sources: 389 indexed, 5 syncing, 1 failed).

## Matched baseline ladder (`harness/strong_baselines.py`)

Four conventional systems over the official ARB chunks of the identical
corpora, each adding one Delphi component: `dense` (`text-embedding-3-small`,
max-pooled to files), `hybrid` (RRF k=60, equal untuned weights, of dense and
ARB BM25), `hybrid_rerank` (top 50 -> top 30 through Delphi's
`cross-encoder/ms-marco-MiniLM-L-6-v2` with blend 0.4, then Delphi's `gpt-4o`
listwise rerank over the top 20 at seed 1042 with Delphi's prompt, imported from
the backend), `hybrid_rerank_expand` (adds Delphi's `gpt-4o-mini` HyDE expansion
with Delphi's prompt and gate). All model outputs are cached on disk
(`cache/`), so repeats are exact. Query-time latency excludes index
construction, as it did for Delphi. Runs: `{I,D,A}-final-<engine>-r4-v1`.

### Independent final (C0, 18 cases) — complete

| system | MRR | R@5 | R@20 | BCY | any-gold |
|---|---|---|---|---|---|
| Delphi (frozen) | 0.508 | 0.551 | 0.750 | 0.454 | 15/18 |
| dense | 0.455 | 0.523 | 0.796 | 0.347 | 15/18 |
| hybrid | 0.579 | 0.639 | 0.870 | 0.403 | 16/18 |
| hybrid_rerank | 0.545 | 0.644 | 0.870 | 0.454 | 16/18 |
| hybrid_rerank_expand | 0.619 | 0.662 | 0.852 | 0.546 | 16/18 |

Paired Delphi minus system (repository clusters, 20k resamples, seed 1042):
vs hybrid R@20 -0.120 [-0.231, -0.019]; vs hybrid_rerank_expand MRR -0.111
[-0.200, -0.034]. No Delphi lead over any rung has an interval excluding zero.
Artifacts: `results/independent_final_delphi_vs_<engine>_r4_v1.json`.

### SWE-bench (C0, 62) — complete

| system | MRR | R@5 | R@20 | BCY | any-gold |
|---|---|---|---|---|---|
| Delphi (frozen) | 0.680 | 0.704 | 0.737 | 0.638 | 48/62 |
| dense | 0.254 | 0.324 | 0.591 | 0.210 | 39/62 |
| hybrid | 0.296 | 0.452 | 0.648 | 0.234 | 43/62 |
| hybrid_rerank | 0.575 | 0.598 | 0.616 | 0.533 | 41/62 |
| hybrid_rerank_expand | 0.597 | 0.623 | 0.657 | 0.573 | 44/62 |

Delphi minus hybrid_rerank_expand: MRR +0.083 [-0.107, +0.203]; R@20 +0.080
[-0.105, +0.217]; BCY +0.065 [-0.062, +0.171]; any-gold 48 vs 44 (p=0.42).
Artifacts: `results/trackd_final_delphi_vs_<engine>_r4_v1.json`.

### ARB round-3 partition (C2, 220) — complete, validation evidence only

Delphi 0.332 / 0.476 / 0.648 / 0.296 vs hybrid_rerank_expand 0.229 / 0.389 /
0.595 / 0.220; Delphi minus final rung MRR +0.103 [-0.008, +0.189], BCY +0.076
[-0.019, +0.157], R@5 and R@20 tied, any-gold 163 vs 148 (p=0.08). Workflow
split: Delphi's lead sits in trace2code (MRR 0.579 vs 0.149) and edit2ripple;
code2test and comment2context are equal or favour the conventional rung. An
exploratory traceback/path split of the 62 SWE-bench issues does not reproduce
the pattern. Artifacts: `results/arb_final_delphi_vs_<engine>_r4_v1.json`.

### SWE-bench expansion (C0, 98) — complete

Provisioned 100 snapshots into the frozen stack (three API instances, sharded;
one orphaned django snapshot reconciled from the database into the manifest);
strict audit `results/native-delphi-swebench-r4-expansion-index-audit-v2.json`
complete (100 repositories, 182,415 files, 1,079,743 chunks = embeddings).
Two engine-agnostic rules before scoring: gold must exist at base commit
(one patch-created file removed from astropy__astropy-13398's gold set), and
ARB `query_has_leakage` (excluded django__django-16256 and
scikit-learn__scikit-learn-14710). Sample: `samples/swebench/cases-r4-expansion-v3.jsonl`.

| system | MRR | R@5 | R@20 | BCY | any-gold |
|---|---|---|---|---|---|
| Delphi (frozen, one shot, attested) | 0.700 | 0.745 | 0.820 | 0.685 | 83/98 |
| dense | 0.214 | 0.389 | 0.673 | 0.156 | 69/98 |
| hybrid | 0.306 | 0.509 | 0.651 | 0.223 | 67/98 |
| hybrid_rerank | 0.611 | 0.622 | 0.667 | 0.576 | 69/98 |
| hybrid_rerank_expand | 0.660 | 0.684 | 0.733 | 0.603 | 76/98 |
| lexical | 0.487 | 0.603 | 0.793 | 0.445 | 82/98 |
| lexical+bm25 rrf | 0.383 | 0.521 | 0.789 | 0.350 | 81/98 |
| bm25 | 0.168 | 0.238 | 0.457 | 0.146 | 48/98 |

Delphi minus hybrid_rerank_expand: MRR +0.041 [-0.028, +0.112]; R@5 +0.061
[+0.023, +0.148]; R@20 +0.087 [+0.042, +0.167]; BCY +0.082 [+0.030, +0.152].
Pooled 160 SWE-bench instances (`results/swebench_pooled160_*`): MRR +0.057
[-0.036, +0.114]; R@5 +0.069 [+0.015, +0.160]; R@20 +0.084 [+0.013, +0.154];
BCY +0.076 [+0.017, +0.128]; any-gold 131 vs 120 (p=0.08). Versus the lexical
ranker pooled: MRR +0.237 [+0.174, +0.391], R@20 +0.030 [-0.019, +0.117].

## Documentation contract, fully matched

`ds1000_harness/build_nia_retrieved_contexts.py` reconstructs the hosted
synthesis engine's retrieved evidence from its recorded responses (five source
chunks per case with content and `metadata.file_path`), packs it with the shared
`pack_context` routine under the 8,000-token budget, and writes
`results/DOCS-dev-nia-retrieved-k5-details.json` (raw identifier hit 0.475;
Delphi raw compact k=5 0.400, k=20 0.425). `run_answer_synthesis.py` gained
`--engine-label`; the arm `nia_retrieved_answer_synthesis` ran three repeats
through the same frozen `gpt-5.4-mini` stage: 0.625 / 0.525 / 0.600, case mean
0.583. Analysis v3 (`results/DOCS-dev-answer-synthesis-analysis-v3.json`):
Delphi 0.617, documentation engine 0.625, synthesis engine matched 0.583,
synthesis engine native 0.575, control 0.492; every engine-versus-engine
case-cluster interval includes zero (Delphi - matched Nia +0.033 [-0.092,
+0.158]; matched - native +0.008 [-0.050, +0.075]). "Parity or better" is
withdrawn; the supported sentence is "no statistically resolved difference".

## Determinism, like for like

`harness/analyze_determinism_likeforlike.py` over the 10x10 raws
(`results/DETERMINISM-docs-like-for-like-v1.json`): retrieved-set exact rate
Delphi 0.980, documentation engine 0.542 (guided) / 0.496 (oracle), synthesis
engine 1.000 on its cited-URL set; byte-exact context 0.980 / 0.356 / 0.253 /
0.000; identifier-hit agreement 1.000 / 0.918 / 0.909 / 0.929. The earlier
"0.0%" for the synthesis engine measured generated text, not retrieval.

## Exposure ledger

`harness/build_exposure_ledger.py` -> `results/exposure-ledger-v1.json`,
`context/EXPOSURE_LEDGER.md`. ARB round-3 final is class C2: all 427 cases
were scored in round 2, round-2 held-out aggregates gated shipped components
(round2-provenance/NEGATIVE-RESULTS.md), and July per-workflow rates motivated
quoted-path demotion. Confirmatory claims rest on C0 sets only.

## SWE-bench expansion (C0)

`harness/prep_swebench_expansion.py` drew 100 Verified instances (salt
`delphi-round4-swebench-expansion-v1`) from the 438 never used, excluding
round-3 ids and base commits; 11 repositories, 100 unique snapshots
(`samples/swebench/cases-r4-expansion.jsonl`, manifest alongside). Provisioning
into the frozen stack is in progress
(`results/native-delphi-swebench-r4-expansion-sources-v1.jsonl`); the one-shot
Delphi run, the ladder, and the lexical comparators follow, then paired
analysis.

## Executable pilot — two repeats complete

Repeat 1 (step budget 50, one trajectory per cell, 62 instances):
none 25/62, random 30/62, delphi 31/62, hybrid_rerank_expand 23/62.
Delphi - none +0.097 [+0.016, +0.194] (7/1, p=0.07); Delphi - random +0.016
[-0.065, +0.097]; Delphi - conventional +0.129 [+0.032, +0.242] (10/2,
p=0.04); conventional - random -0.113 [-0.210, -0.032]. Agents used 7-9 steps
and 1.6-2.6 cents per instance; seeds raised cost 30-60%. Four eval reports
initially flagged as infrastructure failures were re-run and confirmed as
genuine unresolved outcomes. `results/pilot/analysis-s50.json`.

Repeat 2: none 25/62, random 27/62, delphi 25/62, hybrid_rerank_expand 25/62
(`results/pilot/analysis-s50-r2.json`). Pooled per-instance means over both
repeats (`results/pilot/analysis-s50_s50-r2.json`): Delphi - none +0.048
[-0.008, +0.113]; Delphi - random -0.008 [-0.073, +0.056]; random - none
+0.056 [-0.016, +0.137]; conventional - random -0.073 [-0.145, -0.008]. No
seed effect is resolved; the two repeats disagree by more than the effects
under study. Total agent spend for all eight condition-repeats: about $11.


Preregistered in `context/PILOT_PROTOCOL.md` before any scored run. Pipeline
validated end to end on `psf__requests-1142` (mini-SWE-agent 2.4.6, text-based
actions, `gpt-5.4-mini`, `linux/amd64` emulation; official harness `swebench`
5.0.2 with `SWE-bench/SWE-bench_Verified`; resolved 1/1). Datasets built by
`harness/build_pilot_dataset.py` for `none`, `random`, `delphi` (Delphi's seed
hits gold in 47/62 instances); the `hybrid_rerank_expand` seed waits for that
ladder run. Runner: `stack/run_pilot.sh <condition> <steps>`; outputs under
`results/pilot/`.

## Nia repository arm

Fresh single-shard smoke with the new credential (same account):
`gin-gonic/gin@28e57f58` shard stayed `syncing` past the 40-minute deadline
(`results/nia-sharded-sources-r4.jsonl`). Still externally blocked.

## Paper

`paper/context.tex` rewritten around the audited storyline; every table is
generated from artifacts by `harness/paper_tables.py` into `paper/tables/`.
The round-3 source is kept as `paper/context-round3-2026-08-26.tex.bak`.
Pending markers in the text name exactly which runs they wait for.

### ICLR-format revision (2026-09-09, later)

`paper/context.tex` restructured for ICLR 2027: main text 9 pages (limit 9 at
submission), statements and references on pages 9-11, appendix A-L on pages
12-26 (26 pages total). Every figure is generated from artifacts by
`harness/paper_figures.py` into `paper/figures/` (12 PDFs: component
attribution, C0 ladder, paired-delta forests (full and compact), exposure
timeline, documentation matched contract, determinism, pilot, ARB workflows,
latency-quality, per-repository SWE-bench, rank histogram). New generated
tables: ARB by workflow, per-repository pooled SWE-bench, latency, exposure
ledger, pilot repeat 2. Main text keeps the pooled SWE-bench table and the
determinism table; the four per-set ladder tables, both documentation tables,
and the pilot tables moved to the appendix. Appendix adds: verbatim prompts
(listwise, expansion, synthesis, control, pilot seed block), the frozen
environment, the ladder implementation, the round chronology, the round-2
measured-and-rejected record, hosted-engine accounting, compute and cost
(233.5M embedded tokens ~ $4.70; 1.44M cached vectors; 1,051 cached LLM
replies; 496 trajectories, $10.97), the artifact release statement (code,
per-case artifacts, all trajectories, ledger; public URL withheld for review,
released once the de-identification pass is complete), and a crosswalk from
the earlier report's claims to their corrected form. Exposure ledger
regenerated: the expansion set is now "confirmatory" (was "pending scoring").
Numbers newly stated in the text were checked against artifacts: pooled rank-1
rates 0.619 / 0.575 / 0.344 and top-20 miss rates 0.181 / 0.250 / 0.200
(Delphi / conventional / lexical); pilot exit statuses (2 LimitsExceeded in
random, repeat 1); File-Okapi gate thresholds (-0.01, -0.01, 1.20); ladder
constants (200k-token batches, 8k truncation, ARB BM25); PostgreSQL 14.

