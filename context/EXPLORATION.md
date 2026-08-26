# Exploration record

## What has been inspected

- The official ARB v2 query serialization, chunking, file packing, and metrics.
- All 271 required ARB repository snapshots through commit-pinned bare git
  clones; canonical file text comes from `git show`.
- July Delphi per-case failures, file-list lengths, workflow breakdowns, and
  full-miss clusters.
- Delphi query expansion, dense/BM25 fusion, cross-encoder reranking, listwise
  reranking, path boosts, embedding generation, and HNSW retrieval.
- Nia local-folder provisioning, daemon sync, account-scoped source reads,
  manifest coverage, and query citation output.
- OpenAI small/large and Gemini embedding repeats against a fixed gallery.
- Three pinned real questions in Gin, Tokio, and pytest, with Delphi, Nia, and
  grep outputs preserved in `blog/vignette-transcripts.json`.
- SWE-bench Verified localization preparation: 62 issue-to-patch-file cases at
  base commits, not yet queried.
- The existing documentation/DS-1000 assets and Context7 path are under a
  separate active audit.

## What the evidence says

### Static ranking

July Delphi is not a toy: it substantially beats official BM25 on the fresh
development split. It is also not ready for a SOTA claim. Gold is absent from
its top 20 on 34.7% of cases even though it returns 20 unique files every time.
This is a true candidate-recall hole, not output truncation.

The most acute workflow is comment2context: any-gold@20 is 48%, versus 92% for
trace2code. Review envelopes often quote the file already open in the user's
editor. Delphi over-rewards that lexical anchor and fails to cross to the
implementation, configuration, or parallel module that the comment asks about.

Official file-level BM25 recovers 7 of the 26 cases where July Delphi has no
gold in its top 20: six comment2context cases and one edit2ripple case. Delphi
alone recovers 20 cases that BM25 misses, so lexical cannot replace semantic
retrieval. Their union raises any-gold@20 from 49/75 to 56/75. A conservative
simulation that reserves two tail slots for distinct BM25 files raises it to
53/75 while leaving MRR essentially flat (0.2852 to 0.2879). This is evidence
for branch/file diversity, not for switching to BM25.

The official non-BM25 lexical ranker is weaker alone (MRR 0.092, R@20 0.373,
BCY@8k 0.062), but its errors are more useful at the frontier: it recovers nine
of Delphi's 26 full misses, including all seven that BM25 recovers. Delphi plus
lexical therefore reaches 58/75 any-gold@20. Reserving three distinct lexical
tail files reaches 53/75 with MRR 0.2881; one or two slots recover fewer cases.
The result sharpens the product hypothesis from “more BM25” to “bounded
file-diverse lexical candidates,” which must be tested inside Delphi's actual
candidate window rather than post-hoc.

The first patched 3-small Delphi run materially improves deep recall: MRR
0.337, R@20 0.642, and BCY@8k 0.320 versus July's 0.285/0.544/0.313.
Repository-cluster bootstrap supports the R@20 gain (+0.098, 95% CI
[0.041, 0.186]) but not yet MRR or BCY. It recovers ten July misses and loses
four. The gain is uneven: code2test MRR falls by 0.066 and BCY by 0.130, while
comment2context and edit2ripple gain R@20 by 0.153 and 0.190.

Gemini embedding-001 is not a stronger drop-in replacement. Its full run
nudges R@20 to 0.653 and BCY to 0.338, but drops MRR to 0.284; the paired MRR
delta is -0.054 [-0.102, -0.011]. It recovers five complete 3-small misses and
loses four, so the useful conclusion is candidate complementarity, not a
Gemini winner.

The candidate funnel explains the remaining headroom. Gold exists in the
100-file pool for 62/75 cases but survives the final top 20 in only 55/75;
seven cases are reranker losses and thirteen are true candidate-pool misses.
Only one gold candidate is BM25-only inside the current pool, so increasing the
existing branch quota is not supported. A separate canonical file-level BM25
still rescues three pool misses and lexical rescues two, supporting a bounded
file-level candidate source rather than more chunk-level BM25.

The same two-tail-slot simulation on the patched ranking is much less
decisive: R@20 moves from 0.642 to 0.660, but the repository-bootstrap delta
is +0.018 [-0.026, 0.056], with two complete misses recovered and one lost.
That makes a native whole-file branch a measured ablation, not an assumed
improvement.

The locked repository-disjoint commit-to-files development set provides a
second lexical signal. On 48 cleaned commit-message queries, whole-file BM25
scores MRR 0.419/R@20 0.642/BCY 0.390, while the official lexical ranker
scores 0.462/0.732/0.440. Lexical recovers six any-gold@20 cases and loses
none; its repository-bootstrap R@20 delta is +0.090 [0.024, 0.174] and paired
McNemar p=0.031. This does not prove that lexical beats Delphi, which is not
yet provisioned on the independent corpus. It does show that lexical evidence
distributed across a file is robust outside ARB and deserves a native bounded
candidate-source ablation.

Live Delphi provisioning exposed a separate indexing invariant failure.
Although `chunking.max_tokens` is 2,048, a single generated line cannot be
split by the old line-boundary chunker. Two Rich test fixtures therefore
became 17,851- and 17,165-token chunks, and the OpenAI client silently
truncated them to 8,191 tokens. The chunker now balances an oversized line
across token-bounded chunks while preserving all decoded text and the original
line number. This fix is unit-verified but is not part of the currently
running independent Delphi baseline; measuring it requires a fresh index. A
database-wide audit finds 6,985 chunks above 2,048 tokens, partly because the
AST path deliberately tolerates regions up to 1.5x the configured target, but
only 42 exceed the provider's 8,191-token limit. The line fix targets those
silent provider truncations. Whether to remove the separate 1.5x AST tolerance
is a quality/fragmentation ablation, not part of this safety fix.

### Determinism

Embedding APIs are not the main source of list motion. OpenAI vectors jitter,
but fixed-gallery top-10 membership is stable; Gemini is bitwise stable in the
measured sample. Local MiniLM and MPNet are also bitwise stable across all
20-repeat comparisons, with identical top-10 lists. Full Delphi retrieval was
initially much less stable because approximate vector boundaries, concurrent
cache misses, and an unordered BM25 cutoff changed the candidate pool before
the seeded listwise stage. Total SQL ordering and complete single-flight
outcome sharing now resolve that within one live API process: exact and HNSW
each produce 100% exact lists in two concurrent 8 x 10 packets and two
concurrent 75-case repeats. Exact and HNSW still produce different retrieval
functions—only 2/8 packet lists match, with mean top-10 Jaccard 0.849—and exact
scan is slightly better on development R@20 (0.649 versus 0.629).

That result is not cold-process determinism. Restarting both API containers
clears the in-memory hosted-stage caches. The next exact run reproduces only
1/8 old lists (Jaccard 0.810); HNSW reproduces 3/8 (Jaccard 0.890). Several
top ranks remain stable, but the 95% exact-list claim fails decisively. Fixed
provider seeds are insufficient. A restart-durable cache is therefore a
product requirement if Delphi wants reproducible hosted expansion, listwise,
and embeddings. The current intervention stores only safe typed values
(strings and non-object NumPy arrays) in an optional bounded SQLite LRU;
transient `None` and exceptions remain shared only with same-process waiters
and are never persisted. The first persistent version still allowed two live
processes to compute different successful values for one simultaneous cold
miss. A renewable per-key SQLite lease now coordinates that path: a real
two-process probe returns one shared value with exactly one compute call, while
unrelated cache keys retain separate leases. The integration result closes the
observed restart gap:
after one eight-query fill packet, two successive API restarts reproduce all
8/8 lists exactly on every pairwise comparison. Mean latency also drops from
4.90 seconds on fill to 1.48 and 1.79 seconds after restart. This is durable
“first answer wins” behavior, not proof that separate clean installations
sample the same first hosted answer; the cache is part of result provenance.

### Comparator integrity

Counting manifest rows is insufficient. Coverage must be the set intersection
between required `(repo, commit)` pairs and successful indexed pairs. The first
round-3 Nia score run violated that invariant and was cancelled. The harness now
fails closed.

Even a nominally successful source row is insufficient. During the clean
native rebuild, one Black snapshot returned success with 417 indexed files but
zero chunks in 0.3 seconds. The local-folder endpoint had therefore produced a
catalogued but unsearchable source that the old manifest check would have
accepted. All queued scorers were stopped. Provisioning now requires positive
file and chunk counts, retries one such response with `force_reindex=true`, and
fails closed if the repaired response remains empty. The real retry produced
2,088 chunks for the same 417 files. The completed database contains exactly 48
required repositories, 44,189 files, 145,258 chunks, and 145,258 embeddings,
with no empty repository or embedding-count mismatch. This is a benchmark
validity invariant and a product-health signal, not a quality improvement.

Endpoint identity is also insufficient. Two repeat IDs looked valid until
terminal provenance showed that their listeners had been replaced: one
"exact" run used HNSW-100, and one "file-BM25" run used HNSW-400 with the
branch disabled. Both are quarantined. Search responses now include the
non-secret serving retrieval configuration, and the benchmark runner compares
it with a declared expected subset before accepting a case. Fresh guarded
exact/current and exact/file-BM25 repeats reproduce every one of the 48 metric
rows and top-20 lists. Configuration provenance is part of the result, not an
operator assumption.

A manual scoped-search probe exposed a separate fail-open boundary. Sending
the plausible but invalid field `repository_ids` was accepted because the
request model ignored extra keys; the intended `repo_ids` filter remained
unset and Delphi searched every repository visible to the account. This did
not affect benchmark runs, which use `repo_ids`, but it can cause cross-project
context leakage and invalid ad hoc experiments. `SearchCodeRequest` now
forbids unknown fields. A fail-first endpoint regression proves the typo no
longer reaches the search service and returns HTTP 422; the focused API/search
suite is 24 passed.

Nia daemon source identifiers are not safely portable across API accounts. The
daemon registry reused an existing `/arb3/...` ID, but source access was scoped
to the account that owned it. A per-account namespace creates a genuinely owned
source and resolves the 404.

Context7's automatic resolver is a material part of product quality. On the
40-case docs development set, full and compact prompts both hit a gold
identifier on 7/40, while oracle library IDs reach 14/40 and 15/40. Automatic
resolution frequently selects `/onnx/sklearn-onnx` or
`/scikit-learn-contrib/sklearn-pandas` for scikit-learn questions, and often
selects `/tensorflow/docs` instead of the Python API source. Its 404 responses
were reproduced serially: the API body says `no_relevant_snippets`, so these
are empty retrievals rather than infrastructure outages. The harness now
records them separately from technical failures.

Part of that resolver gap was measurement-induced: DS-1000 labels the package
`Sklearn`, while Context7 only returns the official project near the top for
the canonical name `scikit-learn`. The corrected automatic arm declares
canonical package names but still lets Context7 choose the source; it improves
identifier hit from 7/40 to 11/40. The original arm is retained as a diagnostic.
Oracle IDs reach 15/40. A deterministic resolver that follows Context7's own
selection guidance—exact normalized title first, then benchmark score, trust,
and snippet count—also reaches 15/40 without oracle IDs, up from 11/40 for the
canonical-name first-result adapter. It selects one source per library and
matches the oracle aggregate despite two paired wins and two paired losses.
This closes the resolver artifact while remaining an honest automatic arm.

Prompt compaction is not a universal optimization. It moves Delphi identifier
hit from 0.300 to 0.400, but moves Nia from 0.575 down to 0.450. Query
transformation must therefore be ablated per engine and reported, not silently
shared as if it were neutral.

Delphi's documentation retrieval shows sharp diminishing returns in result
count. Compact-query identifier hit is 0.400 at both `k=5` and `k=10`; `k=20`
adds only one case (0.425) while raising mean packed context from 2,647 to 7,686
tokens. A downstream `k=5` versus `k=20` generation ablation is running because
retrieval recall alone cannot justify the extra context.

The docs systems are complementary rather than nested. Nia full hits 23/40 and
Delphi compact hits 16/40; they overlap on 13, so Delphi contributes three cases
Nia misses and their union is 26/40. Context7 oracle compact contributes four
cases beyond Nia, taking that pair's union to 27/40. Across Nia, Delphi, and
Context7, 13 cases have no identifier hit at all. This makes a bounded
multi-source ensemble a real hypothesis, but downstream execution must validate
whether the brittle identifier proxy tracks useful context.

Nia's 23/40 number is not raw retrieval. Its live `skip_llm=false` path returns
a synthesized answer plus citations. The documented `skip_llm=true` raw-search
path returned HTTP 200 with `content=null` and an empty `sources` list for every
case in both full and compact 40-case sweeps. Serial probes with fast/deep and
vector/hybrid settings, and with UUID versus display-name selectors, reproduced
the empty response. Therefore Nia is labelled `retrieval+synthesis` in this
track; its identifier hit cannot be treated as the same intervention as raw
Delphi or Context7 snippets. The downstream frozen-model result remains useful
as an end-to-end context-engine comparison.

The completed ten-case x ten-repeat sweep separates Delphi from Context7
sharply. Delphi compact has 98.0% pairwise exact context, 100% hit agreement,
and 0.993 mean item-set Jaccard; all ten runs score 0.300. Context7 oracle
compact has 25.3% exact context, 90.9% hit agreement, and 0.806 item-set
Jaccard; run hit rates range from 0.200 to 0.400. Aggregate equality from two
runs had hidden real item motion.

The automatic quality-guided Context7 resolver narrows but does not remove that
variance: 35.6% exact context, 91.8% hit agreement, and 0.835 item-set Jaccard,
with run hit rates of 0.200--0.300 on the same ten cases. Resolver quality and
retrieval repeatability are separate product properties.

An equal-request follow-up isolates query shape from resolution by pinning one
quality-guided library ID per package and alternating full/compact order across
five repeats. Full queries score 0.38 identifier hit versus 0.34 for compact,
but the +0.04 case-cluster interval is [-0.22, 0.32], exactly two cases favor
each transform, and there is no winner. Both arms still move substantially:
exact-list rates are 0.28/0.22 and mean item-set Jaccard is about 0.75. Full
queries unexpectedly return 15% fewer context tokens at essentially identical
latency. The audit also finds historical TensorFlow resolver drift from
`/tensorflow/tensorflow` to `/tensorflow/docs`, so resolve-once pinning is part
of reproducible Context7 evaluation rather than a convenience.

A resolver-only follow-up removes snippet retrieval and task-query variation:
each canonical package name is sent as both `libraryName` and `query` in ten
position-balanced rounds. All 50 `/api/v2/libs/search` calls succeed with no
retries or warmups. The quality-guided selected ID is exact for every package
across all 225 within-package pairs, but the returned candidate lists are exact
on only 55.6% of pairs (mean set Jaccard 0.862). Per-package candidate-list
exactness is 1.000 for Matplotlib, 0.489 for NumPy, 0.200 for pandas, 0.644 for
scikit-learn, and 0.444 for TensorFlow. TensorFlow's current selected ID is
`/tensorflow/tensorflow` in 10/10 requests, while the earlier fixed ablation
used `/tensorflow/docs`. Thus short-window selected-ID stability does not erase
cross-period identity drift; candidate ranking and final quality selection are
separate stability layers, and the resolved ID remains required provenance.

Nia's synthesized answer changes on every paired case comparison: exact context
is 0.0% across ten repeats. Its normalized citation set is nevertheless
perfectly stable (Jaccard 1.000), while identifier-hit agreement is 92.9% and
per-run hit rates range from 0.500 to 0.700. This isolates synthesis variance
from citation retrieval variance: stable sources do not imply stable context.

The attempt-accounted compact-query Nia rerun is also complete at 100/100
observations with no retries or failures. Its citations are internally exact,
but identifier hit falls to 0.260 from the historical full-query repeat mean of
0.600; the case-cluster delta is -0.340 with a 95% bootstrap interval
[-0.600, -0.090]. Compact also returns 101 more mean tokens and takes 2.93
seconds longer. This is not synthesis noise alone: across all 1,000
within-case cross-transform repeat pairs, ordered citation lists match only
20%, top citations 80%, and citation-set Jaccard averages 0.606. Full is the
clear provisional query shape. The acquisitions were not interleaved and the
historical full block did not count retries, so this remains strong descriptive
development evidence rather than a randomized causal estimate.

The matched follow-up resolves that design caveat. It fixes each package to the
same Nia source, alternates full/compact order within 50 case-repeat pairs, and
makes exactly 100 no-retry requests. Full reaches 0.640 identifier hit and
compact 0.240; compact-minus-full is -0.400 with a case-cluster interval
[-0.640, -0.160]. Compact also adds 100.58 mean tokens [3.12, 192.02] and
2.620 seconds [1.392, 3.803]. Citation-set Jaccard remains only 0.606 across
transforms, so compaction changes retrieved evidence rather than merely
shortening the synthesis prompt. Full is now the selected Nia query shape for
this development track, not merely a provisional choice.

The first downstream-generation attempt exposed an executor-validity bug:
model generation ran correctly, but the evaluator inherited the backend Python
environment and marked correct-looking programs as failures because pandas,
Matplotlib, and TensorFlow were absent. Those partial outputs were stopped and
deleted. The harness now accepts an explicit evaluator interpreter; the
official DS-1000 Python 3.10 environment now passes a known reference solution.

Three valid frozen-model repeats remain deliberately inconclusive rather than a
win claim. Mean pass@1 is 0.575 without retrieval, 0.592 with Delphi `k=5`,
0.642 with Nia synthesis, and 0.567 with guided Context7. Nia's +0.067 is the
largest and is positive in every repeat, but its case-cluster bootstrap interval
is [-0.075, 0.200]; Delphi's +0.017 interval is [-0.108, 0.142]. Context7's
mean delta is -0.008. Exact code equality across repeats is only 28.3% without
retrieval, 31.7% with Delphi, 48.3% with Nia synthesis, and 33.3% with
Context7, so generation variance is a first-order part of the result. One
exploratory Delphi `k=20` run falls to 0.500, ten points below its paired
`k=5` run despite one additional identifier hit. More context is not a
monotonic improvement.

An initial Delphi `k=20` generative compressor reaches 249 mean tokens, but it
is not evidence-only in practice. It introduces six identifier hits that were
absent from raw context, loses five existing hits, and in at least one case
writes a novel task solution despite the system instruction. It is therefore
labelled retrieval+synthesis, not compressed retrieval. A source-faithful
variant now asks the model only for excerpt IDs and mechanically copies the
selected source spans; generated prose is never sent downstream. Neither
variant helps execution. Retrieval+synthesis averages 0.558 pass@1 versus
0.575 without retrieval (delta -0.017, CI [-0.142, 0.100]). The faithful
extractive arm averages 0.492 (delta -0.083, CI [-0.208, 0.042]) after losing
identifier coverage. Compression cannot repair missing or poorly selected
evidence merely by deleting tokens.

### Agent utility

The first four frozen-agent controls behave coherently. No seed reaches File F1
0.0458 and any-gold 0.075. Random seed is worse at 0.0125/0.025, showing that
extra context can actively anchor the agent incorrectly. BM25 seed improves to
0.0925/0.175, roughly doubling File F1 over no seed. Oracle seed reaches
0.8575/0.975, so the task has enormous context headroom and the agent can use
relevant files when given them. These controls establish both a harmful-context
floor and a usable-context ceiling.

The completed lexical and Delphi arms answer most of that intervention
comparison. Lexical reaches File F1 0.119 and final-any-gold 0.250. Delphi
reaches 0.234 and 0.475. Against no seed, Delphi's File F1 delta is +0.188
(repository-cluster CI [0.055, 0.294]); against BM25 it is +0.142
([0.059, 0.208]). Against lexical, Delphi recovers twelve final-hit cases and
loses three (McNemar p=0.035), although its File F1 interval narrowly crosses
zero. Delphi also uses fewer tool calls than no seed because it often submits
from the seed, but observes roughly 2,500 seed tokens versus 390 baseline read
tokens. Utility and context cost must therefore be reported together. Nia's
repository arm remains unavailable because hosted ingestion never completes.

### Product implications

The current highest-confidence product invariant is: evidence already embedded
in a structured review/diff query should not dominate returned context when
alternatives exist. That invariant produced quoted-anchor demotion. It is not
accepted until the full r3b ablation lands.

The next likely gains should target candidate generation and cross-file
structure, not benchmark-specific post-hoc boosts. Stronger embeddings alone may
help, but the Gemini candidate must demonstrate this on the same 75 cases.

The patched pool shows that increasing the existing chunk-level BM25 quota is
the wrong abstraction: only one gold candidate is BM25-only. A separate
file-level lexical source still contributes candidates absent from that pool.
At the same time, seven pool-hit cases lose gold during final reranking.
File-level candidate diversity and rank preservation should be isolated as
separate interventions.

The complete exact leader makes the lexical intervention more precise.
Canonical lexical sees gold for four of exact Delphi's nineteen complete
misses. Simply replacing the final three slots raises R@20 from 0.649 to 0.669
and complete hits from 56 to 57 without moving MRR materially; eight slots
reach R@20 0.678 but still recover only that one complete miss. The other
recoverable gold files sit at lexical ranks 10--15, so a large final quota is
not attractive. The next ablation should contribute distinct file-level
lexical candidates before fusion/reranking, where cross-signal agreement can
promote them.

The independent corpus now has a stronger fused open comparator as well.
File-level weighted RRF (`lexical=0.7`, `BM25=0.3`) reaches MRR 0.469 and R@5
0.551, versus canonical lexical at 0.462/0.513, while preserving lexical's
R@20 of 0.732. It does not dominate: BCY falls from 0.440 to 0.433, and paired
repository-bootstrap intervals against lexical include zero. This is useful
pressure against benchmark theater. Delphi must clear the lexical recall/BCY
frontier and the fused MRR/R@5 frontier, not whichever single baseline makes
it look best.

The clean native Delphi baseline changes that comparison materially. Current
exact Delphi scores MRR 0.595, R@5 0.608, R@20 0.729, and BCY 0.528. It beats
canonical lexical on MRR by +0.133 [0.020, 0.253] and BCY by +0.088
[0.015, 0.165], while R@20 is effectively tied (-0.003
[-0.069, 0.066]). Against lexical/BM25 RRF, BCY improves by +0.095
[0.008, 0.192], while MRR and R@5 intervals cross zero. Delphi therefore
clearly improves early ranking and budgeted context on development, but does
not yet establish deeper-recall leadership.

The native file-BM25 sweep is mostly a ranking intervention, not a coverage
intervention. Weights 0.10/0.15/0.20 all remain at 38/48 any-gold cases. The
0.15 arm is best pointwise: MRR 0.602, R@5 0.639, R@20 0.736, BCY 0.514.
Against current exact Delphi it moves MRR +0.0066 [-0.0104, 0.0309], R@5
+0.0313 [0.0000, 0.0694], R@20 +0.0069 [0.0000, 0.0208], and BCY -0.0139
[-0.0625, 0.0208]. It upgrades one already-hit three-file gRPC case from
partial to full recall and promotes relevant Celery/esbuild files, but recovers
no complete miss. Compared with either lexical baseline it reaches any gold on
38 cases rather than 39 (three losses, two recoveries), even though fractional
R@20 is slightly higher because of multi-gold partial credit. This is why both
Success@20 and Recall@20 must accompany any leadership statement.

The residual lexical-only cases were not all candidate-generation failures.
Current Delphi already returned `src/value/mod.rs` at rank 21,
`src/blib2to3/pytree.py` at rank 48, and four Poetry gold files at ranks
30/84/93/100 in its 100-file page. The paired API-contract ablation confirms
that the requested boundary matters. Asking Delphi for the scored 20 files
instead of 100 and truncating client-side raises any-gold from 38/48 to 40/48,
with two complete recoveries and no complete loss; fractional R@20 rises from
0.729 to 0.764 [-0.014, 0.097], R@5 from 0.608 to 0.646
[0.000, 0.087], and MRR from 0.595 to 0.597, while BCY moves -0.010. One
three-file Celery case loses one partial hit, so this is not monotonic per
case. A guarded repeat reproduces all metric rows and top-20 lists exactly.

This scored-boundary arm is the development leader. Against canonical lexical
it reaches 40 versus 39 any-gold cases (three recoveries, two losses), R@20
0.764 versus 0.732, and improves MRR by +0.135 [0.029, 0.247] and R@5 by
+0.133 [0.012, 0.274]. The recall and BCY intervals still cross zero, so this
is development selection evidence rather than a final SOTA claim. Enabling
file-BM25 at the same 20-file boundary falls back to 38/48 any-gold and R@20
0.729: it loses both new complete recoveries and gains none, despite stronger
MRR/BCY point estimates. File-BM25 therefore remains an ablation, not the
default. The harness now defaults provider fetch depth to the scored limit;
over-fetching must be explicit and is a different retrieval contract.

A narrower lexical diagnostic identifies a more plausible next branch than
whole-file BM25. Camel/alphanumeric-tokenizing query text and file paths makes
`direct-origin` match `direct_origin.py` and `default types` match
`default_types.rs`. Reserving only the final slot for the top distinct
repository-local IDF path candidate raises independent any-gold from 40/48 to
42/48 with no loss (McNemar p=0.5) and R@20 from 0.764 to 0.789; the
repository-bootstrap delta is +0.025 [0.000, 0.071], while MRR and BCY are
effectively unchanged. The same one- and two-slot simulation does nothing on the 75-case
ARB development set, while three slots add partial recall to two already-hit
cases without changing binary acquisition. This is useful cross-corpus
pressure: path-token normalization is general and cheap, but the apparent
independent gain rests on two repositories and is only a post-hoc tail
simulation. It should be implemented, if selected, as a default-off candidate
branch before reranking and ablated on both development corpora—not adopted as
a hard final-slot rule.

The default-off native branch now exists and reproduces the diagnostic without
gold-aware placement. It scans only explicitly scoped repository paths,
camel/alphanumeric-tokenizes query and path, computes repository-local IDF
overlap, fetches one deterministic chunk from each top file, aligns agreement
onto an existing chunk in that file, and enters weighted RRF at 0.10. The first
native arm exposed a selector subtlety: `types.rs`, path rank one, was already
in the fused pool. Alignment added `path_token` to that existing candidate,
which made the selector believe the branch was covered; rank-two gold
`default_types.rs` remained outside the rerank window. File-level agreement and
novel-file acquisition are distinct signals. The selector now preserves one
standalone file-level candidate even when an aligned multi-source candidate is
already present.

With that correction, native Delphi recovers both diagnostic misses and no
current any-gold case: 42/48 versus 40/48 (McNemar p=0.5). Point estimates move
from MRR/R@5/R@20/BCY 0.597/0.646/0.764/0.517 to
0.629/0.667/0.793/0.528. MRR has three wins and four losses, and fractional
R@20 has three wins and one loss, so the gain is not monotonic. Repository
bootstrap intervals for MRR [-0.018, 0.093], R@5 [-0.021, 0.074], and R@20
[-0.007, 0.079] include zero; BCY improves +0.011 [0.000, 0.028]. A guarded
repeat is exact on all 48 metric rows and top-20 lists. This promotes the branch
from simulation to repeatable independent-development product evidence, but
not to default adoption: ARB development remains the required cross-corpus
gate and its current-product snapshots are still provisioning.

Against canonical lexical, the corrected arm improves MRR by +0.167
[0.070, 0.277] and R@5 by +0.155 [0.039, 0.280]; against the stronger weighted
lexical/BM25 RRF comparator, the gains are +0.160 [0.044, 0.288] and +0.117
[0.006, 0.219]. Recall@20 and BCY intervals still cross zero in both
comparisons. Binary acquisition is 42/48 versus 39/48 for either lexical
comparator, with four recoveries and one loss (McNemar p=0.375). Thus the
independent evidence supports a head-ranking lead and a higher acquisition
point estimate, not a universal recall or BCY claim.

A defect-focused review changed the implementation bar without changing this
development result. It exposed three real path-token issues: a configured
zero-hit branch still entered the fusion denominator; unscoped or non-hybrid
responses reported the branch and weight as active; and replacement logic did
not credit sources supplied by an incoming standalone candidate, so it could
retain an aligned result and discard the novel file. The first issue was
generalized to file-BM25 as well: optional file-level weights enter fusion only
when that query produced candidates. Effective provenance now requires hybrid
execution and, for path-token, explicit repository scope. Replacement preserves
all sources represented either elsewhere or by the incoming candidate.

The same pass closed three smaller robustness gaps. Acronym-prefixed camel case
now turns `HTTPServer` into `HTTP` + `Server`; the path scan filters to files
that have chunks; and transfer/Python scoring is bounded by a 50,000-file cap
plus one sentinel row, failing closed on overflow. Tests explicitly cover the
0.10 default, access-control SQL, default-off non-execution, zero-hit score
identity, effective provenance, novel-file replacement, acronym splitting,
searchable-file filtering, and overflow. A second review found no residual
issue in scope. Most importantly, the config-attested post-review run
`I-dev-delphi-native-pathtoken10-reviewed-top20-r4` is exact against the earlier
guarded `r3` run on every metric row and top-20 list. The fixes therefore
remove latent correctness risks without post-hoc changing the selected point.

A separate trace audit shows why file diversity is an ordering invariant, not
only a cutoff policy. Nineteen exact-run pages contain duplicate-file chunks,
and one 100-result page has only 28 distinct files. The source-diverse helper
previously skipped its file-first pass whenever the whole candidate set fit
inside `top_k`; after branch injection, sorting by original rank could also
re-interleave deferred duplicates. The benchmark harness deduplicates file
paths while reading the final page, so this does not automatically translate
to a 72-slot metric loss. The product harm is earlier: comparative reranking
can spend its bounded window comparing multiple chunks from one file instead
of distinct candidate files. The corrected invariant keeps every candidate
but moves first hits from distinct files ahead of same-file leftovers. It also
explicitly preserves the default-off `file_bm25` and `path_token` branches
before broad chunk-level BM25. For file-level sources, an aligned multi-source
candidate no longer consumes the novel-file preservation slot. This is
unit-verified and still requires a full ARB development rerun.

The same audit exposed a second branch-coverage mismatch. Delphi already runs
and weights a `path_affinity` branch for related tests and sibling
implementations, but the source-diverse selector did not reserve that branch a
rerank-window slot and `hybrid.sources_hit` did not count it. In a fail-first
two-slot control, the only related-path result was discarded behind two vector
hits. Retrospective exact-run traces show this is not hypothetical:
path-affinity candidates appear on 46/75 cases, yet 17 have none inside the
top-30 rerank window. One of those carries a gold test file at rank 39 through
path/path-affinity evidence. The selector and observability vocabulary now
include `path_affinity`; the regression and full 99-test intervention suite
pass. This is a general pipeline invariant, but whether that gold candidate
actually reaches the final top 20 remains development evidence to collect
rather than an assumed win.

Native ARB provisioning exposed a narrower coverage caveat beyond the earlier
zero-chunk source bug. The Playwright snapshot
`00dcb5cd511e1e1a1af9dded0b16a975ea7591de` is healthy overall, but the indexer
intentionally skips nine files above its 500 kB PostgreSQL `tsvector` safety
cap: five vendored reading-list bundles and four generated protocol/type
declarations. The benchmark case on that snapshot uses
`packages/playwright-core/src/tools/dashboard/dashboardApp.ts` as gold, so the
observed skips do not structurally zero that case. Still, positive repository
file/chunk counts prove only source-level searchability, not benchmark-gold
searchability. Before scoring the 75 cases, audit every target gold path
against the indexed `repository_files`/`code_chunks` rows and fail closed if
any gold file has no searchable chunk. Do not remove the size guard or ingest
generated bundles merely to improve nominal file coverage.

The completed native gate now closes both validity questions. The canonical
68-row manifest maps exactly to the required development snapshots; direct
database accounting finds 116,424 files, 548,545 chunks, and 548,545
embeddings, with no missing/empty source and no chunk/embedding mismatch. Both
Delphi arms also passed the new source-specific gold-path preflight and
response-level serving-config attestation before scoring. The current exact
stack (`A-dev-delphi-native-current-top20-r1`) scores MRR 0.303374, R@5
0.417778, R@20 0.617778, and BCY@8k 0.300000 on all 75 cases. Its guarded
warm repeat is identical on every metric row and top-20 list.

The reviewed path-token arm is a mixed cross-corpus result rather than a
leader. It scores MRR 0.316984 and R@5 0.457778, but R@20 0.611111 and BCY
0.291111. Paired deltas versus current are respectively +0.013610
[-0.017129, 0.043206], +0.040000 [-0.032609, 0.108333], -0.006667
[-0.056452, 0.032828], and -0.008889 [-0.059829, 0.058140]. It exchanges two
complete recoveries for two complete losses, leaving any-gold at 54/75 for
both arms (McNemar p=1.0). Its repeat is also exact. This is reproducible
movement, but not consistent evidence for enabling the branch.

Current Delphi remains far ahead of the strongest aggregate ARB lexical
comparator, whole-file BM25: MRR +0.159277 [0.059211, 0.242779], R@5 +0.244444
[0.091396, 0.380282], R@20 +0.226667 [0.092040, 0.335470], and BCY +0.195556
[0.054487, 0.312698]. It acquires 23 cases BM25 misses and misses five that
BM25 acquires (McNemar p=0.000912). Those five are informative rather than a
reason to append gold-aware lexical slots: four are review-context cases where
whole-file term evidence reaches a sibling implementation/help file, and one
is a code-to-test case whose named implementation's canonical config test sits
at BM25 rank 19. Any next lexical intervention should therefore be a
predeclared, repository-scoped code-aware Okapi branch before reranking, and
must preserve the 23 Delphi-only acquisitions.

Canonical git lexical is weaker still, but remains a necessary comparator.
Current Delphi improves MRR +0.211842 [0.109410, 0.290055], R@5 +0.268889
[0.135593, 0.373984], R@20 +0.244444 [0.150000, 0.354762], and BCY +0.237778
[0.095588, 0.348659]. It acquires 25 cases lexical misses and loses four
(McNemar p=0.000104). The path-token, comparator, and exact-repeat analyses are
preserved in `results/arb_dev_delphi_path_token_analysis_v1.json`,
`results/arb_dev_delphi_comparator_analysis_v1.json`, and
`results/arb_dev_delphi_repeatability_v1.json`.

A focused post-freeze diagnostic clarifies what the five lexical rescues mean.
The five whole-file-BM25-only cases contain all four canonical-lexical-only
cases; four are comment-to-context and one is code-to-test. Running current
Delphi with a deliberately diagnostic API `top_k=100` does not simply reveal
the gold files just below the scored boundary. Three are absent from all 100
returned candidates. The other two appear only through vector evidence at
ranks 40 and 42. In contrast, whole-file BM25 ranks every gold file between 3
and 19, and canonical lexical ranks four between 5 and 15. The run is
`A-dev-delphi-native-fetch100-lexical-misses-diagnostic-v1`; its aggregate
scores are explicitly non-claim-bearing because over-fetching changes the
backend selection problem.

This shifts the mechanism diagnosis from “reserve more tail slots” to “supply
missing file-level lexical candidates before reranking.” It does not prove an
Okapi branch should ship: current Delphi still has 23 acquisitions BM25 lacks,
and both prior native lexical interventions failed their adoption gates. A
fair final experiment would need a product-real, default-off file-level index,
response-level provenance, and a zero-acquisition-loss gate. Until that design
is explicitly approved, the exact/current freeze stands and neither final
partition may be queried.

The fresh index also resolves the old exact-versus-HNSW ambiguity. A
preregistered HNSW-100 arm, served with response-level configuration
attestation and the same warm hosted-stage cache, reproduces every exact metric
row and top-20 list across all 75 cases. It is not faster: warm mean/median
latency is 671/468 ms versus 670/466 ms for exact. The earlier gap therefore
does not survive the repaired selector/index stack, while the expected indexed
latency advantage is absent at these repository-scoped candidate sizes. The
result closes `ef_search=400` as a development priority without asserting
universal exact/HNSW equivalence. The paired artifact is
`results/arb_dev_delphi_hnsw100_analysis_v1.json`.

## Open questions

- Does quoted-anchor demotion improve comment2context without harming
  code2test, trace2code, or edit2ripple?
- What operational cache-lifetime/export policy makes the now-exact
  restart-durable result reproducible for another installation?
- Can a higher HNSW `ef_search` recover exact-scan quality while retaining
  indexed retrieval at repository scale?
- Can the Delphi seed gain be reproduced with a second model-generation repeat,
  and how should its extra observed-token cost be valued?
- Can Nia repository ingestion ever reach a terminal state on the account?
- Can a true code-aware Okapi branch recover the five ARB cases BM25 uniquely
  acquires without displacing Delphi's 23 unique acquisitions?
- Does unconditional file-first ordering improve the two duplicate-bearing
  listwise heads without moving already-file-diverse queries backward?
- How often does preserving `path_affinity` change the listwise head, and does
  that specifically recover code-to-test and review-to-sibling-file cases?
