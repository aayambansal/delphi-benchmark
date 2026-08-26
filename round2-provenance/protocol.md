# Delphi/Nia context-engine evaluation, round 2

Locked: 2026-07-29 (Asia/Singapore)

This study treats “Stealthy” as Delphi unless the sponsor identifies a
different product. It does not inspect or use SynsciContextBench.

## Objective

Measure and improve Delphi as a general developer context engine, compare it
with Nia and strong open baselines, and permit a state-of-the-art claim only
where untouched evidence supports the exact named scope.

The previous Delphi evaluation is a closed audit. Its engine outputs may be
used to motivate broad research questions but may not be used to tune this
round or score its confirmatory split.

## Primary benchmark

Agent Retrieval Bench V2 at commit
`d04953371d962ec314fb15d642255ed4e9dadd40`:

- `v2_code2test` (106): implementation intent to regression tests;
- `v2_comment2context` (80): review comment to missing context;
- `v2_trace2code` (101): failure trace to root-cause implementation;
- `v2_edit2ripple` (58): anchored edit to affected files;
- `v2_abstention` (82): natural and counterfactual no-gold cases;
- the official balanced and natural-prevalence selective-retrieval mixtures.

All files at the exact base commit are candidates. No task-aware file filter is
allowed.

### Split

The 50 trace-to-code IDs named in the prior protocol are `legacy_exposed` and
are excluded from the new confirmatory split. For every positive
`(release_id, repository)` stratum, sort remaining IDs by
`SHA256("delphi-round2-v1|" + release_id + "|" + repository + "|" + id)`.
The first `max(1, floor(0.25 * stratum_size))` cases are development and the
rest are final. Apply the same rule independently to natural and
counterfactual no-gold strata.

The split manifest must be materialized and hashed before any engine query.
Development outputs may guide general product changes. Final queries are made
once after code, configuration, adapters, policy model, prompts, and budgets
are frozen.

The complete 427-case score may be reported after freeze, but because it
contains development cases it is descriptive. Confirmatory claims use only
the untouched final partition.

## Track A: static positive retrieval

Each engine receives the same gold-free ARB query and exact repository
revision. Each returns up to 20 unique repository-relative files.

Primary metrics:

- MRR;
- Recall@20;
- BCY@8k;
- repository-macro MRR and Recall@20;
- workflow-macro MRR, Recall@20, and BCY@8k.

Secondary metrics:

- Success@1, @5, and @20;
- Precision@20 and F0.5@20;
- failure rate;
- end-to-end latency;
- returned and packed tokens.

Comparators:

- Delphi’s best documented production mode;
- Nia’s best documented repository-query mode;
- official ARB Qwen3-Embedding-4B/8B, RepoMap, lexical, and BM25 results where
  the release and metric implementation match exactly.

Provider-specific agentic synthesis is stored separately and is not silently
converted into a static file ranking.

## Track B: selective retrieval

Evaluate the official balanced and natural-prevalence mixtures. A system
abstains only when its normal production response returns no repository
context or an explicit machine-readable abstention. Do not infer abstention
post hoc from answer prose.

Primary metrics:

- selective success@20;
- positive success@20;
- natural no-gold true-abstention rate;
- counterfactual no-gold true-abstention rate.

Report coverage-risk curves only for engines that expose a stable numeric
confidence. Any threshold is fit on development and frozen before final.

## Track C: controlled developer exploration

Use ARB’s evaluator-mediated closed-tool protocol. A single frozen policy model
can call only `list_dir`, `grep`, `read_file`, and `submit`; it never receives
direct filesystem or shell access. Compare seeds produced by Delphi, Nia,
RepoMap/Qwen where available, random non-gold, oracle gold, and no seed.

The policy, prompt, tool-call limit, observation limit, and model are identical
across arms. Seed context and post-seed observations have separately accounted
token budgets.

Primary metrics:

- final File F1;
- any-gold acquired;
- first-gold tool step;
- post-seed tool calls and observed tokens.

This is an intervention on the context seed, not an end-to-end patch benchmark.

## Track D: downstream developer utility

After the retrieval iteration is frozen, run at least one established
execution-based task suite with one fixed coding policy under:

- no external context;
- Delphi context;
- Nia context;
- oracle context where licenses and harness permit it.

Candidate suites are assessed in this order: official ContextBench used as an
interactive trajectory benchmark, SWE-Explore, and a stratified SWE-bench
Verified localization/repair subset. A suite is included only if its native
scientific question and evaluator can be preserved; unsupported systems are
labelled unsupported rather than assigned zero.

Primary metric is the suite’s official execution or trajectory-success metric.
Also report cost, tokens, latency, and context contacts.

## Product-change policy

Allowed:

- fixes or features that improve normal developer workflows;
- changes reproduced on development cases or independent product tests;
- documented API/MCP behavior with regression tests;
- generic query planning, repository inspection, ranking, context packing,
  calibrated abstention, freshness, and observability improvements.

Forbidden:

- benchmark IDs, gold paths, repository-specific rules, or memorized queries;
- inspecting final engine output before freeze;
- changing the policy, budget, or metric after seeing final results;
- committing benchmark data, outputs, credentials, or reports to Delphi.

Every Delphi product change uses an isolated `codex/` branch, a pull request,
required CI, and a squash merge. Commit and PR messages contain no AI or model
attribution.

## Statistics and claims

Use paired, repository-group-aware bootstrap intervals with 10,000
deterministic resamples. Report sample-, repository-, and workflow-macro
effects. Final API failures remain scored observations unless the protocol
classifies them as infrastructure-invalid before unblinding.

“State of the art” is allowed only for a precisely named track/release where:

1. Delphi leads every directly comparable engine on the untouched primary
   metric or is statistically tied while leading a predeclared complementary
   primary metric;
2. the full compatible comparator set is reported;
3. final cases did not affect code, configuration, prompts, or budgets; and
4. the result is reproducible from the locked sources and frozen commit.

Otherwise, report the strongest bounded conclusion and all material losses.

