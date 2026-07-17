# Roadmap: Deterministic Catalog Ingestion for Graphiti MCP

## Shipped Milestones

- [x] **v1.0 — Deterministic Catalog Ingestion** — Shipped 2026-07-17

| Phase | Plans | Result |
|---|---:|---|
| 1. Typed Catalog Primitives | 8/8 | Verified: 5/5 truths, 55/55 requirements |
| 2. Provenance and Atomic Batch | 6/6 | Verified: 5/5 truths, 31/31 requirements |
| **v1.0 total** | **14/14** | **86/86 requirements; 6/6 integration flows** |

## Delivered Outcomes

- Seven additive deterministic catalog MCP tools; all 14 legacy tools preserved.
- Fixed server-owned types and properties; UUIDv5 identities; canonical SHA-256 audit.
- Embed-before-transaction entity/edge writes with exact typed endpoint enforcement.
- Installed-schema provenance with atomic source compare-and-set and ordered retained target locks.
- Non-`Entity` terminal batch status and one-transaction nested catalog commits.
- Safe retry, conflict, dry-run, rollback, search, community, isolation, and concurrency coverage.
- Final gates: 303 unit, 35 live Neo4j, 338 combined catalog, 86 MCP regression tests.

## Future Work

- FalkorDB or other backend support requires equivalent transaction, provenance, and concurrency semantics.
- Production canary against `oracle-catalog-v2` requires separate approval.
- Full catalog ingestion and Kubernetes deployment require separate approval.
- Graph clearing, existing-data deletion, automatic community creation, and semantic-ingestion changes remain out of scope.

## Archive

- [v1.0 roadmap](milestones/v1.0-ROADMAP.md)
- [v1.0 requirements](milestones/v1.0-REQUIREMENTS.md)
- [v1.0 milestone audit](milestones/v1.0-MILESTONE-AUDIT.md)
- [v1.0 phase artifacts](milestones/v1.0-phases/)

---
*Updated: 2026-07-17 after v1.0 completion*
