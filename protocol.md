# Delphi context-engine research, round 3

Locked: 2026-08-23 (America/Los_Angeles). Workspace: `new/round3/` (gitignored;
nothing in here is ever committed to the Delphi repository).

## Research questions

- **RQ1 (utility).** Does a context engine actually improve what a coding agent
  does, compared with the agent's own tools (grep, ls, read)? Measured as an
  intervention on the context seed with everything else frozen.
- **RQ2 (ranking quality).** Is Delphi state of the art among directly
  comparable engines on agent-relevant repository retrieval?
- **RQ3 (determinism).** Where does run-to-run variance in context pipelines
  come from (embedding APIs, ANN indexes, LLM rerankers, provider pipelines),
  how large is each source, and what does removing it cost in quality?

## Exposure history (honest accounting)

All 427 ARB v2 cases were scored by the July 2026 round-2 process, and round-2
final results influenced which Delphi configuration shipped. Round 3 therefore:

1. Draws a **fresh split** with salt `delphi-round3-v1` (25% development /
   75% final within each `(release, repo)` stratum; the 50 round-1
   `legacy_exposed` trace2code IDs stay excluded). Round-3 development cases
   may guide product changes; round-3 final cases are queried once after
   freeze.
2. Adds an **external, never-before-touched evaluation** (SWE-bench Verified
   file localization on repositories at held commits) that no prior Delphi
   round has run, for an uncontaminated headline.
3. Reports the exposure history in every artifact that makes a claim.

## Benchmarks

### Track A — static repository retrieval (ARB v2)

427 cases, 25 repos, 271 exact base-commit snapshots; positive workflows
code2test (106), comment2context (80), trace2code (101, 51 eligible),
edit2ripple (58); abstention (82). Queries are the gold-free structured ARB
queries serialized as sorted JSON (`query_text_for_eval`). Engines return up
to 20 repository-relative file paths. Metrics from the official ARB
implementation: MRR, Recall@5/@20, Success@k, BCY@8k, plus latency. Estimands:
sample-weighted, repository-macro, workflow-macro. Paired bootstrap over
repositories, 10,000 resamples, seed 20260823.

Comparators: Delphi (July frozen config, then round-3 candidates), Nia
(documented query mode, same snapshots), BM25, lexical, and the official ARB
released baselines where the release and metric implementation match.

Every reported engine run must cover every sampled `(repo, base_commit)` pair.
The runner aborts before scoring if a source manifest is incomplete; partial
diagnostic runs may not enter tables or claims. This guard was added after a
Nia manifest with 68 indexed rows was found to overlap only 32 of the 68
required development snapshots.

### Track B — determinism and variance

- **Embedding level.** Same text embedded N=20 times per provider
  (OpenAI text-embedding-3-small/large, gemini-embedding-001, local
  sentence-transformers): max pairwise cosine deviation, rate of exact
  bitwise equality.
- **Retrieval level.** Identical query repeated N=10 against each engine:
  exact-list equality rate, Jaccard@10, Kendall tau on shared items;
  Delphi with LLM stages on/off; Nia in query mode; BM25 as the
  deterministic control.
- **System level.** Full round-3-dev metric spread across 3 independent runs
  of the frozen config.
- **Interventions.** temperature=0 + fixed seeds in every Delphi LLM stage,
  deterministic tie-breaks (score desc, path asc), exact vector scan for eval.
  Report the quality delta of full determinism.

### Track C — closed-tool agent utility (RQ1)

ARB's evaluator-mediated protocol: one frozen policy model (single provider,
temperature 0) that can only call `list_dir`, `grep`, `read_file`, `submit`,
with identical prompts, budgets, and tool caps across arms. Arms differ only
in the seed context block: none, grep-pipeline seed, BM25 seed, Delphi seed,
Nia seed, oracle gold seed (ceiling), random-file seed (floor). Metrics: final
file F1, any-gold-acquired, first-gold step, tool calls, tokens observed.
Runs on a stratified round-3-dev subset sized to budget; the same subset for
every arm; paired stats.

### Track D — external untouched evaluation

SWE-bench Verified file-localization subset (stratified sample, size set by
budget): given the issue text, rank files; score against gold patch files.
Delphi and baselines index each instance repository at its base commit.
No development iteration against this track — one shot after freeze.

## Product-change policy (Delphi repo)

Allowed: general retrieval/ranking/determinism improvements, provider
upgrades, bug fixes, regression tests, docs. Every change lands on `master`
via normal commits with tests passing. Forbidden: benchmark IDs, gold paths,
repo-specific rules, benchmark harnesses/SDKs, results, or credentials in the
repository.

## Claim policy

"State of the art" is claimed only for a precisely named track where Delphi
leads every directly comparable engine on the untouched primary metric, or is
statistically tied while leading a predeclared complementary primary metric
(early precision: MRR; utility: BCY@8k), with the full comparator set
reported and the final partition untouched by development. Losses are
reported with the same prominence as wins.

## Deliverables

1. Delphi improvements on `master` (clean, no bench artifacts).
2. Local dashboard (`new/round3/dashboard`) serving every run, per-case
   traces, and comparisons.
3. Blog post (personal voice) on what context engines actually do.
4. ICLR-format paper with the full findings, positive or negative.
