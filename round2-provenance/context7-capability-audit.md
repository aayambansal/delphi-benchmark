# Context7 capability audit

Audited: 2026-07-29 against Context7's public API guide, documentation, and
open MCP server repository.

This describes the exposed product contract, not private backend internals or
benchmark quality.

## Product shape

Context7 is a version-aware documentation retrieval service for coding agents.
Its normal flow is deliberately narrow:

1. resolve a library name and natural-language query to a canonical Context7
   library ID;
2. request bounded documentation context for that library;
3. optionally pin the library ID to a version in prompts or agent rules.

This is materially different from both a repository context engine and a
universal enterprise search platform. Context7 should therefore be compared on
documentation/API-use tasks, not assigned zero on exact-repository retrieval
tasks that its public contract does not claim to support.

## Exposed capabilities

| Capability | Public surface | Relevant behavior |
|---|---|---|
| Library resolution | `GET /api/v2/libs/search` | Maps library name plus query to candidate library IDs |
| Documentation context | `GET /api/v2/context` | Returns query-focused context for one canonical library ID |
| Version selection | Version-qualified library IDs | Lets callers prefer documentation for a named release |
| Output forms | Text or JSON | JSON separates code and information snippets |
| Agent integration | MCP tools and REST API | Supports direct tool use or application-side retrieval |
| Query guidance | Public docs | Recommends specific task-oriented queries rather than broad keywords |
| Caching/rate handling | Public docs | Documents caching and `Retry-After` handling |

## What the comparison can and cannot claim

Valid:

- matched live documentation retrieval for libraries covered by all systems;
- source-resolution success, latency, returned context size, identifier
  contact, and downstream execution under one frozen coding model;
- automatic library resolution as the production path, with an explicitly
  labelled oracle-ID sensitivity analysis.

Invalid:

- repository-snapshot retrieval, code-graph navigation, or blast-radius
  analysis as a Context7 loss;
- claiming knowledge of Context7's private crawler, parser, embedding model,
  reranker, or index freshness beyond the observable API;
- comparing answer prose to a ranked file list.

## Observed evaluation implication

The primary Context7 arm uses automatic library resolution because that is the
public production workflow. A second oracle-resolution arm supplies the
correct canonical library ID to isolate source selection from within-library
retrieval. Both use the same DS-1000 prompts, context budget, and downstream
model as the Nia and Delphi documentation arms.

## Primary sources

- https://context7.com/docs/api-guide
- https://github.com/upstash/context7
