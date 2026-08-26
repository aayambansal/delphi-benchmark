# Nia frontier audit

Updated: 2026-08-24. Scope: Nia benchmark accounting on development data
only. No locked final split was inspected. This audit made no hosted request
and changed no Delphi product, Context7, blog, paper, or split file.

## Outcome

No additional Nia call is justified. The complete order-balanced
full-versus-compact run already selects **full queries**. A further
documentation request would either duplicate that decision or test a different
contract, such as raw-source mode, without removing the repository blocker.

The repository arm remains fail-closed at **0/68 required commit-pinned
sources** in the only available owned account scope. No repository or Track C
score is valid.

## Completeness and accounting

- Repository readiness exactly matches the four development sample files:
  75 cases and 68 unique `(repo, base_commit)` pairs. The artifact records one
  successful `GET https://apigcp.trynia.ai/v2/daemon/sources`, zero search
  calls, zero visible `/arb3-new/` sources, and no partial score.
- Compact determinism contains 10 runs x 10 cases, 100 successful observations,
  100 recorded attempts, zero reported retries, no errors, 100 unique
  retrieval-log IDs, and valid query hashes. Its attempt policy is recorded as
  `NiaDocsAdapter max_attempts=1`, but the artifact does not carry per-row
  attempt fields or a hash of its one-off driver.
- The historical full block contains 10 runs x 10 cases and 100 unique
  successful retrieval-log IDs. Its original attempt count and retry count are
  not recoverable from the rows. The historical adapter default allowed up to
  three attempts, so those files must not be described as exactly one attempt
  per observation. Their output and citation reanalysis remains valid.
- Both historical transform analyses agree numerically. They remain
  descriptive because acquisition was sequential and the full block lacks
  exact attempt accounting.
- The decisive balanced raw artifact contains exactly 100 scheduled and
  dispatched observations, 100 HTTP attempts, 100 HTTP 200 responses, zero
  transport retries, zero logical retries, zero failures, and 100 unique
  retrieval-log IDs. Every schedule row matches its observation.

## Endpoint and citation audit

All documentation searches used the effective endpoint
`POST https://apigcp.trynia.ai/v2/search` in query/source mode with
`fast_mode=true`, `skip_llm=false`, source inclusion, cache bypass, and an
8,000-token budget.

The balanced artifacts record both a base URL ending in `/v2` and an endpoint
field `/v2/search`. The executed URL is correct, but those two strings are not
meant to be concatenated; the endpoint field is the absolute API path.

Citation identity is consistent across compact, historical full, and balanced
data:

- 500 citations checked in each condition family.
- Every response records exactly five citations.
- Every citation resolves through `metadata.file_path` with integer
  `start_line` and `end_line`.
- No path is missing, and no selected path contains a query string, fragment,
  or trailing slash.
- `metadata.file_path` and `metadata.sourceURL` never disagree.
- The balanced raw file has zero stored-versus-recomputed identity mismatches
  and no duplicate identity within an observation.

The normalized identity is therefore
`metadata.file_path:start_line:end_line` for all observed citations. The
documented fallback fields were not exercised.

## Raw and analysis consistency

The balanced analysis was recomputed offline from the raw artifact. After
excluding only top-level creation/update timestamps, it is exactly equal to the
recorded analysis. The raw SHA-256 matches the analysis input pin, all
provenance file hashes match, and copied corpus, source-selector, query,
configuration, schedule, accounting, and stop-reason sections are identical.

## Artifact inventory note

`NIA_WORKSTREAM.md` lists six result files but omits
`new/round3/results/nia-accounting-docs-full-v-compact-analysis-20260824.json`.
The balanced run pins that legacy analysis by SHA-256. It is consistent with
the listed query-transform comparison, so this is an inventory omission rather
than a metric defect.

Machine-readable audit:

- `new/round3/results/nia-accounting-frontier-audit-20260824.json`

## Request ledger for this audit

- Hosted Nia requests: **0**
- Offline balanced-analysis recomputations: **1**
- New benchmark observations: **0**
- Credential check: not performed, because no decision-relevant hosted test
  passed the call-justification gate.

The audited prior records contain one repository inventory read, 100 compact
search attempts, and 100 balanced search attempts. The historical full files
contain 100 successful observations but do not establish an exact HTTP-attempt
count.

## No-more-calls recommendation

Make no further Nia calls now. The only potentially nonredundant documentation
study is a separately predeclared `skip_llm=true` raw-source-mode protocol.
That would answer a different question—raw-retrieval parity—and would not
change the selected full query shape or unblock repository evaluation. Run it
only if the benchmark contract is explicitly changed to require raw-retrieval
parity.

Resume repository work only when one owned Nia scope demonstrably exposes all
68 required `/arb3-new/<repo>/<base_commit>` sources in terminal indexed state
and account-scoped source reads succeed for every source. The previous
six-source scope is not locally addressable and was nonterminal; repeating the
same ingestion is not a valid next step.
