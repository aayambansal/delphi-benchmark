# Delphi Benchmark

**Where Do Context-Engine Gains Come From? A Component-Level Decomposition of Repository Retrieval Under Matched Baselines and Audited Exposure**

Aayam Bansal and Ishaan Gangwani · Synthetic Sciences

[![Paper](https://img.shields.io/badge/Paper-PDF-b31b1b)](paper/context.pdf)
[![Trajectories](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-agent%20trajectories-ffcc4d)](https://huggingface.co/datasets/aayambansall/delphi-benchmark-traces)
[![Delphi](https://img.shields.io/badge/Delphi-context%20engine-111827?logo=github)](https://github.com/synthetic-sciences/delphi)
[![Frozen build](https://img.shields.io/badge/frozen%20build-91d76c1-6b7280)](https://github.com/synthetic-sciences/delphi/commit/91d76c1)
<!-- Once the arXiv identifier is assigned:
[![arXiv](https://img.shields.io/badge/arXiv-XXXX.XXXXX-b31b1b)](https://arxiv.org/abs/XXXX.XXXXX) -->

This repository is the complete evaluation archive behind the paper: the preregistered protocols, every run artifact (including failed and invalidated runs, kept for the audit trail), the harness, the split manifests and case-level exposure ledger, the research journals, and the paper source. The agent trajectories from the executable pilot are published separately on Hugging Face.

## The question

Context engines index a repository and hand a coding agent the files it should read. They report large gains over lexical baselines, but a margin over BM25 does not say whether the engine's design or a learned reranker that would help *any* candidate pool produced it, nor how much of it was selected on the evaluation data. We answer this for one open-source engine, [Delphi](https://github.com/synthetic-sciences/delphi), by

- recording for every evaluation case whether development could have seen it (an **exposure ledger** with three classes);
- building a **ladder of conventional retrievers** from Delphi's own embedding model, with Delphi's rerankers and query expansion attached one rung at a time;
- varying **candidate generation × learned reranking** factorially; and
- **ablating Delphi's candidate branches** one at a time on a fresh, never-scored draw.

## Findings

Measured on three SWE-bench Verified draws that development never saw (62, 98, and 60 instances; sizes fixed before scoring) and one repository-disjoint commit-to-files set.

| | |
|---|---|
| **The advantage is the candidate pool, not the reranker.** | Before any reranking Delphi's candidates lead the full conventional stack by +0.19 MRR and +0.07 Recall@20. The shared rerankers add +0.34 MRR to conventional candidates but +0.19 to Delphi's, so after reranking MRR ties while the recall gap (+0.09) persists. |
| **The pool advantage is chunking, index, and weighting.** | The branch ablation attributes +0.15 MRR to Delphi's chunking and index (same two-branch fusion) and +0.06 to its vector-heavy weighting; the four structural branches add +0.06 jointly, none more than 0.03. |
| **It depends on query style.** | On commit-to-files queries the pattern inverts: Delphi's pool has lower recall than two-branch fusion and the rerankers add nothing to either pool. |
| **Exposure changes the evidence class.** | The ledger reclassifies Delphi's 220-case ARB partition from held-out to validation evidence; confirmatory results rest on 238 cases scored once and never before, with intervals adjusted for three looks. |
| **Matched contracts remove a hosted lead.** | Routing every engine's evidence through one frozen synthesis stage turns an apparent hosted-engine lead on documentation into a four-way tie. Re-indexing a corpus from scratch reproduced Delphi's ordered top-20 on 1 of 18 cases. |
| **No seed effect in the executable pilot.** | 62 instances × 4 seed conditions × 2 repeats with a fixed mini-SWE-agent: a retrieval seed resolves no more verified repairs than a random-file seed, and repeats disagree by more than the effects under study. The pilot audits its own seed and yields a precision target for a decisive study. |

We claim no state of the art; several findings are null or negative for the engine we built, and they are reported with the same prominence as the positive ones.

## Artifacts

| Artifact | Where |
|---|---|
| Paper (camera-ready source and PDF) | [`paper/`](paper/) |
| Agent trajectories: 620 mini-SWE-agent runs with every model call, harness verdicts and per-instance logs, seeded inputs, and a browsable `trajectories.jsonl` index | [Hugging Face dataset](https://huggingface.co/datasets/aayambansall/delphi-benchmark-traces) |
| Per-case results for every system on every set (development, rejected, factorial, branch-ablation, determinism, documentation) | [`results/`](results/) |
| Pilot analyses and harness reports | [`results/pilot/`](results/pilot/) |
| Exposure ledger, split manifests, draw manifests | [`context/EXPOSURE_LEDGER.md`](context/EXPOSURE_LEDGER.md), [`samples/`](samples/), [`samples-ds1000/`](samples-ds1000/) |
| Preregistered protocols | [`protocol.md`](protocol.md) (round 3), [`context/PILOT_PROTOCOL.md`](context/PILOT_PROTOCOL.md) (executable pilot) |
| Research journals: state, decisions, hypotheses, workstreams, artifact inventory | [`context/`](context/) |
| The evaluated engine, frozen at revision `91d76c1` | [synthetic-sciences/delphi](https://github.com/synthetic-sciences/delphi/commit/91d76c1) |

Repository corpora (58 repositories, 425 snapshots) are not redistributed; `harness/restore_corpora.py` re-clones them from public GitHub at the recorded commits. Hosted-engine artifacts are the recorded responses; re-running those arms needs your own credentials. No credentials are stored here.

## Layout

```
paper/            camera-ready paper: context.tex → context.pdf; tables/ and figures/ are generated
results/          every run artifact: per-case details and summaries, paired analyses,
                  factorial and branch-ablation contrasts, determinism repeats, docs arms,
                  hosted-engine accounting; pilot/ holds the pilot analyses and harness reports
harness/          runners, provisioners, analyzers, ledger builder, corpus restorer,
                  paper_tables.py / paper_figures.py, upload_traces_hf.py
harness-r2/       hosted-provider clients and round-2 runners
ds1000_harness/   documentation and generation track (retrieval adapters, synthesis, DS-1000)
samples/          splits and case files (development / final / swebench / docs)
samples-ds1000/   DS-1000 subsets and selection locks
corpus/           independent-corpus sample files and LOCK (bare clones are re-clonable)
determinism/      raw repeat details per engine
external/         official DS-1000 dataset and execution shim
round2-provenance/ round-2 protocol, source and statistics locks, capability audits
stack/            launch scripts and compose files for the frozen Delphi stack and the pilot
context/          research journals (STATE, DECISIONS, HYPOTHESES, workstreams, ledger, inventory)
dashboard/        local run-registry dashboard (reads runstore.db)
runstore.db       run registry (SQLite): every run, including failed and invalidated ones
protocol.md       the preregistered round-3 protocol
```

## Reproducing

Python 3.12+ is enough for the analyses and the paper pipeline (`numpy`, `matplotlib`; `httpx`, `openai`, `tiktoken` for the synthesis and generation arms; `huggingface_hub` for the dataset script). The Delphi stack itself needs PostgreSQL with pgvector; see [`stack/`](stack/).

```bash
# Regenerate every table and figure in the paper from the artifacts in results/
python harness/paper_tables.py
python harness/paper_figures.py

# Build the paper
cd paper && pdflatex context && bibtex context && pdflatex context && pdflatex context

# Rebuild the exposure ledger
python harness/build_exposure_ledger.py

# Re-clone the repository corpora at the recorded commits
python -m harness.restore_corpora samples/final/*.jsonl samples/swebench/cases.jsonl \
    corpus/independent/v1/*.jsonl --workers 4

# Serve the frozen Delphi build (revision 91d76c1) natively, then score with harness/run_arb.py
stack/native-r4-frozen.sh initdb && stack/native-r4-frozen.sh api
```

To re-run the pilot analysis, restore the trajectories from the Hugging Face dataset into `results/pilot/` first (instructions in [`results/pilot/README.md`](results/pilot/README.md)), then run `harness/analyze_pilot.py`. `stack/run_pilot.sh <condition> <step_limit> [workers] [repeat]` reproduces a pilot condition end to end.

Statistical conventions throughout: paired cluster bootstrap with 20,000 resamples and seed 1042 (repository clusters for repository tracks, case clusters otherwise), exact McNemar tests on discordant pairs, and three-look-adjusted intervals for the pooled SWE-bench estimates.

## Citation

```bibtex
@article{bansal2026contextengine,
  title   = {Where Do Context-Engine Gains Come From? A Component-Level Decomposition of
             Repository Retrieval Under Matched Baselines and Audited Exposure},
  author  = {Bansal, Aayam and Gangwani, Ishaan},
  year    = {2026},
  note    = {Preprint. Code and artifacts: https://github.com/aayambansal/delphi-benchmark}
}
```

## License

The trajectories, results, and analyses are released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Content embedded from the public repositories in SWE-bench Verified and the other evaluated corpora keeps its upstream licenses.
