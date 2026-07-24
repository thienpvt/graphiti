# Milestones

## v1.1 — Catalog-v2 Pre-Canary Hardening (Shipped: 2026-07-24)

**Phases completed:** 8 phases, 53/55 plans by contract
**Requirements:** 215/215 satisfied
**Closeout:** Local archive with accepted technical debt; no tag, push, deployment, rebuild, canary rerun, or runtime cleanup

**Key accomplishments:**

- Hardened recursive catalog-v2 contracts, FE/BO/COMMON identity grammar, server-owned edge topology, canonical hashes, and mutation-free capability discovery.
- Added restart-safe immutable prepare/discard/token-only commit with exact evidence links, atomic manifests, deterministic recovery, and manifest-backed diagnostics.
- Preserved exact 14 legacy + 14 catalog MCP tool compatibility while proving Neo4j isolation, security, read/write gates, migration guidance, and Nyquist-compliant coverage.
- Bound raw-Git source to the tested OCI image, staged a fresh isolated Compose authority, and bootstrapped Catalog-v2 schema exactly `0/14 → 14/14`.
- Completed exactly one approved native-Ollama final canary: Gates 0–10 passed; 3/2/1/5 dry run; one prepare; one token-only commit; no retry.
- Retained `DEV-P6-POST-ID-EVIDENCE-COMMITS`, Phase 1 review residuals, and the Phase 2 RED-commit process residual as explicit accepted debt.

**Archives:**

- [Roadmap](milestones/v1.1-ROADMAP.md)
- [Requirements](milestones/v1.1-REQUIREMENTS.md)
- [Milestone audit](milestones/v1.1-MILESTONE-AUDIT.md)
- [Phase artifacts](milestones/v1.1-phases/)

---

## v1.0 — Deterministic Catalog Ingestion for Graphiti MCP (Shipped: 2026-07-17)

**Phases completed:** 2 phases, 14 plans, 26 tasks
**Requirements:** 86/86 satisfied

**Key accomplishments:**

- Added seven additive Neo4j-only catalog MCP tools for typed upsert, resolve, verify, provenance, status, and atomic batch ingestion.
- Enforced server-derived UUIDv5 identity, canonical SHA-256 audit, fixed allowlists, strict bounds, exact typed endpoints, and embeddings before transactions.
- Reused installed `Episodic`/`MENTIONS`/`RELATES_TO.episodes` provenance with atomic source compare-and-set and explicitly ordered retained target locks.
- Added non-`Entity` restart-safe terminal batch status plus all-or-nothing nested writes, write-free dry runs, safe retries, conflicts, and rollback-separated failure status.
- Passed 303 unit tests, 35 required live Neo4j tests, 338 combined catalog tests, 86 MCP regressions, Ruff, Pyright, security, review, and Nyquist gates.
- Completed real local Ollama embedding E2E; left `oracle-catalog-tool-test` clean and `oracle-catalog-v2` unchanged.

**Archives:**

- [Roadmap](milestones/v1.0-ROADMAP.md)
- [Requirements](milestones/v1.0-REQUIREMENTS.md)
- [Milestone audit](milestones/v1.0-MILESTONE-AUDIT.md)
- [Phase artifacts](milestones/v1.0-phases/)

---
