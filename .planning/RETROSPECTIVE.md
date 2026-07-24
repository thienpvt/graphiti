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

## v1.1 — Catalog-v2 Pre-Canary Hardening

**Shipped:** 2026-07-24
**Scope:** 8 phases, 53/55 plans by terminal-plan contract, 215 requirements

### What Was Built

- Strict catalog-v2 recursive contracts, FE/BO/COMMON identity, topology, hashes, capabilities, prepare/commit, evidence, manifests, diagnostics, compatibility, security, and migration guidance.
- Raw-Git exact source binding, source-bound OCI image, isolated Compose runtime, exact 0/14 → 14/14 schema bootstrap, and exact 28-tool readiness.
- One approved native-Ollama canary passed Gates 0–10 with exact 3/2/1/5 dry-run counts, one prepare, one token-only commit, and no retry.

### What Worked

- Freeze-before-allocation plus immutable image/runtime receipts kept the canary authority explicit.
- Native Ollama removed the external credential dependency while preserving embedding-before-transaction semantics.
- Exact manifests, contiguous ledgers, and group isolation made terminal evidence auditable without exposing secrets.

### What Needed Rework

- The first OpenAI-proxy path failed before commit and required a separate native-Ollama remediation path.
- Evidence-only post-ID commits violated the freeze governance rule; retained as explicit accepted debt rather than concealed or repaired with a rerun.
- Milestone requirement totals required reconciliation after additive Ollama requirements were incorporated.

### Patterns Established

- Never rebuild or rerun to repair a post-ID evidence-boundary defect.
- Treat raw Git object bytes, image digest, generated config fingerprint, runtime project, and canary ledger as one authority chain.
- Preserve terminal and historical runtime resources unless separately authorized for cleanup.

### Key Lessons

- Allocate irreversible IDs only after every source, image, and runtime gate is complete.
- Keep evidence writes pre-boundary, or document the deviation immediately and retain it permanently.
- Separate product readiness from production promotion; a passed isolated canary does not authorize deployment.

### Technical Debt

- `DEV-P6-POST-ID-EVIDENCE-COMMITS` accepted.
- Phase 1 WR-R01/WR-R02 and Phase 2 PR-02-02-RED-COMMIT accepted.
- Production promotion, full catalog ingest, migration, and non-Neo4j portability remain future work.

---
