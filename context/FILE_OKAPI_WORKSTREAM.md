# File-Okapi development experiment

Updated: 2026-08-25. Development-only experiment; neither final partition was
queried.

## Product and storage verification

- Product-real File-Okapi implementation branch: `feature/file-okapi`.
- Reviewed compact/final code: `b915d5f`; generated-source protocol amendment:
  `3565123`.
- Compact schema head: `022_file_okapi_repo_scope_index`.
- Clean 441-file live measurement: 120,675 term entries, 889 KiB JSONB payload,
  and 2,064,384 bytes total table+index storage.
- Per-file storage was 26.67x smaller than the old row schema (96.25% lower).
- Final verification before indexing: 152 focused real-PostgreSQL tests and
  1,098 full-suite tests passed; whole-change review had no Critical/Important
  residual issue.

## Generated-source coverage amendment

Strict gold-path preflight found that both historical and fresh indexes excluded
a required 114.5 KiB protobuf Go source through the global `*.pb.go` pattern.
A benchmark-specific exception was rejected. Agent mode now indexes generated
source under the unchanged extension, 500,000-byte, NUL, parser, chunk,
embedding, and PostgreSQL safety guards. The selected non-Okapi product commit
is `91d76c1` on `feature/generated-source-freeze` (master `c17c186` plus only
the generated-source correction).

Fresh exact path audits:

- Independent development: 48 sources; 44,336 expected and actual files; zero
  missing/extra; 151,533 chunks = embeddings.
- ARB development: 68 sources; 116,546 expected and actual files; zero
  missing/extra; 555,340 chunks = embeddings.

## Fresh disabled controls

Independent controls were exact on all 48 metric rows and top-20 lists:

- MRR 0.657743
- Recall@20 0.781944
- BCY@8k 0.580556

ARB controls were exact on all 75 metric rows and top-20 lists:

- MRR 0.314917
- Recall@20 0.620000
- BCY@8k 0.273333

## Fixed File-Okapi candidate

The single preregistered independent candidate (`weight=0.15`, `k1=1.2`,
`b=0.75`, candidate cap 50, API top-k 20) repeated every metric row and top-20
list exactly:

- MRR 0.660009 (delta +0.002265; repository-bootstrap 95% CI lower -0.050000)
- Recall@20 0.800000 (delta +0.018056; no losses)
- BCY@8k 0.609028 (delta +0.028472; CI lower -0.036806)
- Any-gold acquisitions: 42 baseline, 42 candidate; zero losses/recoveries
- Warm median latency ratio: 1.341862

It failed three preregistered common gates:

1. MRR CI lower bound had to be at least -0.01.
2. BCY CI lower bound had to be at least -0.01.
3. Median latency ratio had to be at most 1.20.

Decision: reject File Okapi, do not run an ARB candidate, do not tune a second
configuration, and retain exact/current retrieval with generated-source
coverage.

## Durable artifacts

- `results/file_okapi_development_gate_v1.json`
- `results/independent_generated_source_fileokapi_paired_v1.json`
- `results/independent_generated_source_fileokapi_repeatability_v1.json`
- `results/independent_generated_source_disabled_repeatability_v1.json`
- `results/arb_generated_source_disabled_repeatability_v1.json`
- `results/native-delphi-independent-okapi-dev-index-audit-v3.json`
- `results/native-delphi-independent-okapi-dev-file-coverage-v3.json`
- `results/native-delphi-arb-okapi-dev-index-audit-v3.json`
- `results/native-delphi-arb-okapi-dev-file-coverage-v3.json`

Atlas:

- Verification run: `69f97913-38e4-4cc5-848f-6ca4eca3b263`
- Protocol amendment: `8f891ee6-5f25-4b4e-a992-628caeec3721`
- Rejected candidate: `d9cede04-f825-4329-840d-37c5eba43b90`
- Rejection decision: `d44ede8c-4e1d-4b7b-a4f7-1df3bb042ddb`
