# Retrospective

## v1.0 — Deterministic Catalog Ingestion for Graphiti MCP

**Shipped:** 2026-07-17
**Scope:** 2 phases, 14 plans, 86 requirements

### What Worked

- Phase 1's hard gate prevented provenance and batch orchestration from building on unverified primitives.
- Fixed allowlists and server-derived identities kept Cypher and graph identity deterministic at every trust boundary.
- Independent verification, deep review, security review, and Nyquist checks found issues ordinary happy-path tests missed.
- Live Neo4j concurrency tests exposed transaction behavior that mocks could not prove.
- Test-group isolation plus exact element-ID cleanup preserved unrelated graph data.
- A real local Ollama E2E validated the configured embedding path before cleanup.

### What Needed Rework

- Match-style group validation accepted a trailing newline; full-string validation should be the default at request boundaries.
- Duplicate handling initially lost later occurrences after divergence; conflict accounting must retain every input occurrence.
- Provenance preflight rereads did not close validation/mutation races; correctness required source compare-and-set plus retained target locks.
- Python-side ordering did not guarantee Neo4j lock order; lock ordering must be explicit in Cypher.
- Nested exception handling initially flattened structured race codes; domain errors need dedicated propagation paths.
- Lifecycle documentation overclaimed persistence until the terminal-only contract was stated consistently.

### Durable Lessons

- Validate and canonicalize the complete request before embeddings or persistent effects.
- Use database-enforced invariants and transaction-local locks for concurrent graph mutation.
- Treat caller hashes as assertions; server canonical hashes remain authoritative.
- Verify physical rows, labels, endpoint identities, and embeddings rather than logical counts alone.
- Keep deterministic structured ingestion separate from semantic LLM ingestion.
- Preserve exact scope fences in tests, reports, and operational documentation.

### Final Evidence

| Gate | Result |
|---|---|
| Phase verification | 2/2 passed; 10/10 truths |
| Requirements | 86/86 |
| Integration flows | 6/6 |
| Catalog unit tests | 303 passed |
| Required live Neo4j tests | 35 passed; zero skipped |
| Combined catalog tests | 338 passed |
| Existing MCP regressions | 86 passed |
| Tool registration | 21 total; 7 catalog; 14 legacy |
| Ruff / Pyright | Clean / 0 errors, 0 warnings |
| Security / review / Nyquist | SECURED / APPROVED / COMPLIANT |
| Local Ollama E2E | Passed with 1024-dimensional embeddings |
| Residual test graph | 0 nodes, 0 relationships |

### Next-Milestone Guardrails

- Require separate approval for production canary, deployment, full ingest, or live-group writes.
- Design backend expansion only after proving equivalent transaction and provenance semantics.
- Keep `clear_graph` and existing-data deletion outside catalog workflows.

---
