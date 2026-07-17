# Milestones

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
