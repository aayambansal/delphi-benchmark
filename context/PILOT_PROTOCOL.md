# Executable agent pilot: does a retrieval seed change verified repair?

Preregistered 2026-09-09 before any pilot run was scored. Written in response
to review feedback that the localization and DS-1000 experiments do not answer
the title question on the same tasks.

## Question

Holding the agent, its tools, its model, and its step budget fixed, does
prepending a retrieval seed (the top files a context engine ranked for the
issue) change the rate of verified repairs on SWE-bench Verified, and does the
answer depend on which engine produced the seed?

## Tasks

The 62 round-3 SWE-bench Verified localization instances
(`samples/swebench/cases.jsonl`; exposure class C0 in
`context/EXPOSURE_LEDGER.md`). These are the instances for which both the
frozen Delphi stack and the matched conventional ladder have recorded one-shot
rankings, so seeds can be built from recorded artifacts without any new
retrieval call.

## Agent

mini-SWE-agent 2.4.6, text-based action format (`swebench_xml.yaml`,
`model.model_class=litellm_textbased`), model `gpt-5.4-mini` through the
OpenAI API, official SWE-bench Verified `x86_64` instance images run under
`linux/amd64` emulation. The agent keeps its ordinary shell tools in every
condition; a seed is a hint appended to the problem statement, never a
restriction. One trajectory per (instance, condition, budget).

## Conditions (identical prompt block; only the named files differ)

| Condition | Seed source |
|---|---|
| `none` | official problem statement, unchanged |
| `random` | 5 candidate files drawn at random (seed 1042, per instance), gold excluded; prompting control |
| `delphi` | top-5 files from `D-final-delphi-generated-source-exact-top20-v1` (frozen stack, recorded 2026-08-25) |
| `hybrid_rerank_expand` | top-5 files from `D-final-hybrid_rerank_expand-r4-v1` (conventional ladder, recorded 2026-09-09) |

Each seeded block lists up to 5 paths with the first 40 lines of each file at
the base commit, capped at 3,000 tokens (`harness/build_pilot_dataset.py`).

## Budgets

Primary: `agent.step_limit=50`, `agent.cost_limit=2.0` USD. Secondary, if
time allows: `agent.step_limit=15` (tight). The seed block's tokens count
against the treatment's cost; abstention is not free and is reported as such.

## Outcome and analysis

Primary outcome: verified repair (`resolved`) from the official SWE-bench
harness (`swebench` 5.0.2, dataset `SWE-bench/SWE-bench_Verified`). Secondary:
API cost in USD, steps, whether the agent opened a gold file, and the
`submitted` rate.

Analysis is paired by instance. For each seeded condition versus `none` and
versus `random`, report the difference in resolved rate with an
instance-cluster bootstrap 95% interval (20,000 resamples, seed 1042) and an
exact McNemar test on discordant pairs. Delphi versus the conventional seed is
reported the same way. Repository-cluster intervals are also reported because
django contributes 28 of 62 instances.

## What counts as a finding

- A seeded condition whose resolved-rate interval versus `none` excludes zero.
- A seeded condition that ties `none` on resolved rate but changes cost or
  steps with an interval excluding zero.
- No interval excluding zero at n=62 is reported as unresolved, not as a
  negative result; the pilot's width is what it is.

## Not claimed from this pilot

Anything about agents other than mini-SWE-agent with `gpt-5.4-mini`, about
budgets other than those run, or about seeds packed differently. The pilot
exists to size the effect for a larger study, and to test whether the
localization margins recorded on these same instances carry to repair.
