# Delphi Benchmark — round-3 evaluation archive

Everything needed to read, audit, and reproduce the round-3 evaluation of the
Delphi context engine: the paper, the interactive research blog, every run
artifact (including failed and invalidated runs, kept for the audit trail),
the harness code, the samples and split manifests, and the context journals
that narrate every decision.

**Frozen product commit for all confirmatory numbers:** `91d76c1`
(branch `feature/generated-source-freeze` in the Delphi repository; content
merged to master via PR #85). Statistical convention throughout: paired
cluster bootstrap, 20,000 resamples, seed 1042 (repository clusters for
repository tracks, case clusters otherwise), plus exact McNemar tests on
any-gold@20 movement.

## Headline results

| Track | Result |
|---|---|
| ARB round-3 final (220 untouched cases) | Delphi MRR 0.332 / R@20 0.648 — beats BM25, lexical, and RRF fusion on all four metrics, all 95% CIs excluding zero |
| SWE-bench Verified localization (62) | MRR 0.680 vs 0.406 best baseline (decisive); R@20 statistical tie |
| Independent commit-to-files final (18) | Leads or ties every comparator; no resolvable loss |
| Documentation, matched output contracts | Delphi+synthesis 0.617 vs hosted synthesis engine 0.575 vs docs engine+synthesis 0.625 — three-way tie above the 0.492 no-retrieval floor |
| Documentation determinism (10×10) | Delphi 98.0% pairwise exact context; hosted engines 35.6% and 0.0% |
| DS-1000 downstream (40×3) | No engine separates from the no-retrieval control; all CIs include zero |

No universal state-of-the-art claim is made: the hosted engine's repository
arm never reached required snapshot coverage (32/68; a minimal 1.5 MB probe
shard never left its ingestion queue across ~3.7 h of polling). The claim
rule requires the complete comparable engine set. See
`context/STATE.md` and the blog's "hosted-arm status" section.

## Layout

```
paper/            ICLR submission source (anonymous; context.tex → context.pdf)
arxiv/            camera-ready preprint source (authors, artifact links; arXiv-ready)
blog/site/        interactive research blog (static, data-driven)
results/          every run artifact: finals, analyses, docs/GEN arms,
                  accounting ledgers, determinism, ingestion probes
context/          research journals: STATE, DECISIONS, per-engine workstreams
harness/          round-3 runners: run_arb, provisioners, analyzers,
                  build_blog_data
harness-r2/       hosted-provider clients and round-2-style runners
ds1000_harness/   documentation + generation harness (retrieval adapters,
                  synthesis runners, DS-1000 evaluation)
samples/          round-3 splits (development / final / swebench / docs)
samples-ds1000/   40-case DS-1000 development subset
corpus/           independent-corpus sample files + LOCK (bare git clones
                  are re-clonable from public GitHub and are not archived)
determinism/      raw 10-run repeat details per engine
external/         official DS-1000 dataset + execution shim
dashboard/        local run-registry dashboard (reads runstore.db)
stack/            docker-compose files for the local scoring stacks
analysis/         one-off analysis artifacts
protocol.md       the preregistered round-3 protocol
runstore.db       run registry (SQLite)
```

The executable-pilot agent trajectories (`results/pilot/`, 620 mini-SWE-agent
runs with harness verdicts) are also published as a Hugging Face dataset:
<https://huggingface.co/datasets/aayambansall/delphi-benchmark-traces>
(`harness/upload_traces_hf.py` builds and uploads it).

## Reading the blog

```bash
cd blog/site && python3 -m http.server 8909
# open http://127.0.0.1:8909/
```

Every number on the page is generated from `results/` by
`harness/build_blog_data.py` (re-run it after adding artifacts). The page
includes per-case trace explorers for all 300 final cases, every synthesized
documentation answer with gold identifiers highlighted, DS-1000 pass
matrices, determinism grids, and the claim/no-claim ledger.

## Building the paper

```bash
cd paper && pdflatex context && bibtex context && pdflatex context && pdflatex context
```

## Reproducing runs

Local engines and analyses need only Python 3.12+ (`httpx`, `openai`,
`tiktoken` for the synthesis/generation arms) and a PostgreSQL with pgvector
for the Delphi stack itself (see `stack/`). Hosted-engine runs additionally
need provider keys via environment variables (`NIA_API_KEY`,
`OPENAI_API_KEY`, ...); no credentials are stored in this repository.
Repository corpora are materialized from public GitHub via
`harness/gitcorpus.py` (bare clones at pinned commits). DS-1000 execution
uses an isolated interpreter (see `ds1000_harness/run_generation.py
--execution-python`).

Provenance note: raw hosted-accounting artifacts pin request/response hashes
and exact attempt counts; invalidated runs are retained and marked in
`context/STATE.md` rather than deleted.
