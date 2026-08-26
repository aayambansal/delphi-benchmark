# Context7 remaining-development extension

Updated: 2026-08-24.

## Scope and design

This extension stayed entirely on Context7's native documentation surface. It
used only the 30 documentation development cases not present in the prior
10-case determinism ablation: six cases each for Matplotlib, NumPy, pandas,
scikit-learn, and TensorFlow. No final case, Delphi product code, Nia artifact,
blog, paper, or shared context file was inspected or modified.

The extension used two repeats per arm over all 30 cases. Requests were paired
within case. Each round had 15 full-first and 15 compact-first pairs, and every
case received each arm order once. Both arms used `limit=5`, JSON output, and an
8,000-token packing ceiling. The client used one application attempt,
`HTTPTransport(retries=0)`, disabled redirects, no warmup, and no retry.

Library resolution was not called. IDs were pinned to the exact values used by
the prior ablation so the results can be pooled directly:

- Matplotlib: `/websites/matplotlib_stable`
- NumPy: `/websites/numpy_doc_stable`
- pandas: `/websites/pandas_pydata`
- scikit-learn: `/websites/scikit-learn_stable`
- TensorFlow: `/tensorflow/docs`

TensorFlow intentionally remains pinned to `/tensorflow/docs` for comparability
despite the later resolver-only audit selecting `/tensorflow/tensorflow`.

## Exact accounting and completeness

The run made exactly 120 new hosted requests, all `GET /api/v2/context`: 60
full and 60 compact. There were zero resolver requests, retries, and warmups.
All 120 scheduled observations and all 120 raw HTTP bodies were recorded. The
responses were 113 HTTP 200 and seven valid HTTP 404
`no_relevant_snippets` responses; those seven remained in the denominator.
There were zero technical failures.

Independent verification passed for the 30/10 disjoint partition, development
source hash, complete sequence coverage, equal arm budgets, one request and one
response per row, two repeats per arm, balanced order, deterministic query
hashes, pinned IDs, raw-body hashes and JSON parsing, and absence of
credentials. The raw artifact was created exclusively and is pinned by SHA-256:

- raw:
  `results/context7-accounting-remaining30-full-vs-compact-raw-20260824.json`
  (`dca06f7624ff5a6bbc3dab663158e2ca3df9b15c86d3ae25dd77fed0aa198c25`)
- analysis:
  `results/context7-accounting-remaining30-full-vs-compact-analysis-20260824.json`
  (`f3259e43d68498b129e051c81f76331e3ded292f78b868dfd805a1031dabf26d`)

The raw artifact contains 120 full request/response observations, including
472,497 response-body bytes, request/query hashes, raw response text and
body hashes, parsed items, packed contexts, status, latency, and exact attempt
accounting.

## Extension results

Identifier hit tied exactly:

- full: 22/60 = 0.3667;
- compact: 22/60 = 0.3667;
- full minus compact: 0.0000;
- case-cluster bootstrap 95% interval: `[-0.100, 0.100]`;
- repository-cluster bootstrap 95% interval: `[-0.100, 0.100]`.

The bootstrap retained repeats inside the resampled unit. The case bootstrap
resampled 30 cases; the repository bootstrap resampled the five documentation
libraries and is necessarily coarse. One case favored full, one favored
compact, and 28 tied.

Full returned fewer packed tokens and bytes but was slightly slower:

- mean context tokens: 770.53 full vs 845.45 compact (-8.86%);
- mean context bytes: 3,034.42 full vs 3,277.65 compact (-7.42%);
- mean latency: 2,110.03 ms full vs 2,044.53 ms compact (+3.20%).

Within-arm repeated exact-list rates were 0.467 for full and 0.267 for compact;
mean item-set Jaccard was 0.731 and 0.725. Across matched full/compact calls,
exact-list equality was only 0.0167, mean item-set Jaccard was 0.393, and
identifier-hit agreement was 0.933. Query shape therefore changed the returned
documentation materially even though the quality proxy tied.

## Compatible pooled 40-case result

Pooling this extension with the prior 10-case run gives 220 fixed-ID context
requests over all 40 documentation development cases. Because the first ten
cases have five repeats per arm and the remaining thirty have two, the primary
pooled estimand weights each case equally:

- full case-macro identifier hit: 0.370;
- compact case-macro identifier hit: 0.360;
- full minus compact: +0.010;
- case-cluster bootstrap 95% interval: `[-0.085, 0.110]`;
- repository-cluster bootstrap 95% interval: `[-0.080, 0.100]`.

Three cases favored each arm and 34 tied. The unequal-repeat,
attempt-weighted descriptive rates were 0.3727 full and 0.3545 compact, but
they are not the primary pooled comparison.

## Interpretation

There is no supported winner. The disjoint extension tied, and both clustered
intervals include zero for the extension and the compatible pooled 40-case
analysis. Full prompts again used less packed context, but the latency movement
is small and the identifier-hit evidence is compatible with a loss or gain.
The durable conclusion remains methodological: Context7 comparisons require
pinned library identities, contemporaneous balanced arms, exact hosted-attempt
accounting, and cluster-aware uncertainty.
