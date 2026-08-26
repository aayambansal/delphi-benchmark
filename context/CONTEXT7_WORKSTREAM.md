# Context7 documentation-retrieval workstream

Updated: 2026-08-24.

## Scope and audit

Context7 remains restricted to its native documentation surface. No repository
ARB comparison, Delphi product code, paper, blog, or locked final split was
touched.

The audit covered the Context7 adapter, retrieval harness, query compactor,
tests, legacy 40-case runs, all seven current 40-case retrieval artifacts, both
10 x 10 determinism sweeps, and the existing downstream generation summaries.
The relevant completed development results were:

- canonical-name first-result compact: 11/40 identifier hits;
- automatic quality-guided compact: 15/40;
- oracle-ID compact: 15/40;
- quality-guided compact determinism: 10 cases x 10 runs, 35.6% exact context,
  36.2% exact lists, and 0.835 item-set Jaccard;
- oracle compact determinism: 25.3% exact context, 25.8% exact lists, and
  0.806 item-set Jaccard.

Quality-guided full prompts had not been repeated. Existing one-shot
full/compact differences could not separate query-shape effects from Context7's
measured output variance. No additional downstream generation was justified by
the current small, variable pass@1 results.

## Executed ablation

The new ablation isolates query shape while holding library resolution fixed.
The fixed IDs are those selected consistently by the prior 40-case
quality-guided compact run:

- Matplotlib: `/websites/matplotlib_stable`
- NumPy: `/websites/numpy_doc_stable`
- pandas: `/websites/pandas_pydata`
- scikit-learn: `/websites/scikit-learn_stable`
- TensorFlow: `/tensorflow/docs`

The resolver provenance policy was exact normalized title, then descending
benchmark score, trust score, and snippet count. Fixing its selected IDs makes
the only changed retrieval input the query transform:

- full: verbatim development prompt;
- compact: the existing deterministic 2,000-character compactor.

Ten pre-existing development determinism cases were run five times per arm.
Calls were case-blocked and order-balanced: odd repeats used full then compact;
even repeats reversed the order. Both arms used `limit=5`, an 8,000-token
packing ceiling, JSON output, no warmup, and no retries.

Accounting was exact: 100 new outbound hosted HTTP requests, all to
`/api/v2/context`; 50 requests per arm, zero resolver requests, zero retries,
and zero warmups. All 100 observations completed, with no technical failures.
Eleven valid `no_relevant_snippets` responses remained in the denominator.

## Completed metrics

| Metric | Full | Compact |
|---|---:|---:|
| Identifier hits | 19/50 (0.380) | 17/50 (0.340) |
| Per-run hit rates | .40, .40, .30, .40, .40 | .40, .40, .20, .30, .40 |
| Mean context tokens | 957.64 | 1,128.92 |
| Mean context bytes | 3,423.76 | 4,238.38 |
| Mean latency | 2,044.60 ms | 2,037.24 ms |
| Pairwise exact-list rate within arm | 0.280 | 0.220 |
| Pairwise item-set Jaccard within arm | 0.751 | 0.749 |
| Pairwise identifier-hit agreement | 0.960 | 0.900 |
| Valid complete observations | 50/50 | 50/50 |

Full minus compact identifier hit was +0.040, with a case-cluster bootstrap
95% interval of [-0.220, 0.320]. Two cases favored full, two favored compact,
and six tied. Full returned 15.2% fewer context tokens and 19.2% fewer bytes;
latency was effectively unchanged (+0.36%).

Across matched full/compact calls, exact-list equality was only 0.100,
item-set Jaccard was 0.499, and identifier-hit agreement was 0.760. Query shape
therefore changes retrieval materially, but neither transform is a supported
quality winner. Both remain substantially nondeterministic.

The audit also found resolver-identity drift that the existing determinism
summary did not expose. The primary quality-guided compact run selected
`/tensorflow/docs` for the same TensorFlow cases, while all 20 TensorFlow
observations in the later automatic quality-guided determinism sweep selected
`/tensorflow/tensorflow`. Thus historical cross-period compact comparisons mix
resolver-ID and within-library retrieval effects.

## Interpretation and resolver-only follow-up

Do not replace compact with full on this evidence. The +0.040 proxy movement is
small, case-dependent, and compatible with a substantial loss or gain. The
strong result is methodological: query shape must be repeated under fixed
resolution, and aggregate resolver quality does not imply stable library
identity.

The next development audit measured the quality-guided resolver without making
snippet requests. Each canonical package name was supplied as both
`libraryName` and `query` in ten position-balanced rounds. Exact accounting was
50 `/api/v2/libs/search` requests, zero `/context` requests, zero retries, zero
warmups, and zero technical failures.

Selected IDs were exact on all 225 within-package pairs:

- Matplotlib: `/websites/matplotlib_stable` (10/10);
- NumPy: `/websites/numpy_doc_stable` (10/10);
- pandas: `/websites/pandas_pydata` (10/10);
- scikit-learn: `/websites/scikit-learn_stable` (10/10);
- TensorFlow: `/tensorflow/tensorflow` (10/10).

Candidate lists were less stable: aggregate pairwise exactness was 0.556 and
mean set Jaccard was 0.862. Per-package exactness was 1.000, 0.489, 0.200,
0.644, and 0.444 in the order above. The TensorFlow candidate set itself had
Jaccard 1.000 but changed order/score-list form, while the selected ID stayed
fixed.

This establishes short-window selected-ID stability for identity-only queries,
not task-query or cross-period stability. TensorFlow still differs from the
`/tensorflow/docs` ID used by the earlier fixed ablation, so resolve-once
pinning remains part of provenance.

Raw observations and exact accounting are in
`results/context7-accounting-fixed-guided-full-vs-compact.json`. The complete
prior-artifact audit, per-case metrics, clustered interval, and resolver-drift
analysis are in `results/context7-accounting-audit-and-analysis.json`. The
resolver-only raw responses and compact analysis are in
`results/context7-accounting-resolver-stability-raw.json` and
`results/context7-accounting-resolver-stability-analysis.json`.
