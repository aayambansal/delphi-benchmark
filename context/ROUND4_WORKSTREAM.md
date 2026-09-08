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

### SWE-bench (C0, 62) and ARB (C2, 220) — running at time of writing

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

## Executable pilot

Preregistered in `context/PILOT_PROTOCOL.md` before any scored run. Pipeline
validated end to end on `psf__requests-1142` (mini-SWE-agent 2.4.6, text-based
actions, `gpt-5.4-mini`, `linux/amd64` emulation; official harness `swebench`
5.0.2 with `SWE-bench/SWE-bench_Verified`; resolved 1/1). Datasets built by
`harness/build_pilot_dataset.py` for `none`, `random`, `delphi` (Delphi's seed
hits gold in 47/62 instances); the `hybrid_rerank_expand` seed waits for that
ladder run. Runner: `stack/run_pilot.sh <condition> <steps>`; outputs under
`results/pilot/`.

## Paper

`paper/context.tex` rewritten around the audited storyline; every table is
generated from artifacts by `harness/paper_tables.py` into `paper/tables/`.
The round-3 source is kept as `paper/context-round3-2026-08-26.tex.bak`.
Pending markers in the text name exactly which runs they wait for.
