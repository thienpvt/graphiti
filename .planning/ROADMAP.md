# Roadmap: Deterministic Catalog Ingestion for Graphiti MCP

## Overview

Add synchronous, typed, deterministic Neo4j catalog-upsert tools to the existing Graphiti MCP server. Phase 1 ships allowlisted identity/config plus four primitive tools (`upsert_typed_entities`, `upsert_typed_edges`, `resolve_typed_entities`, `verify_catalog_batch`) behind a hard quality gate and short report. Phase 2 is blocked until that gate is green, then ships provenance, restart-safe batch status, atomic `upsert_catalog_batch`, and operator documentation. No deployment, full catalog ingest, live-group mutation, graph clear/delete, `add_memory` changes, or multi-backend claims.

## Phases

**Phase Numbering:**

- Integer phases (1, 2): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Typed Catalog Primitives** - Config, identity, entity/edge upsert, resolve, verify, and Phase 1 quality gate
- [x] **Phase 2: Provenance and Atomic Batch** - Provenance, batch status, atomic catalog batch, docs, final verification (completed 2026-07-17)

## Phase Details

### Phase 1: Typed Catalog Primitives

**Goal**: Operators can configure and use deterministic typed entity/edge primitives that commit exactly one searchable Neo4j object per identity with no LLM, queue, or implicit endpoint mutation
**Depends on**: Nothing (first phase)
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-04, CONF-05, SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05, IDEN-01, IDEN-02, IDEN-05, IDEN-06, IDEN-07, IDEN-08, ENTY-01, ENTY-02, ENTY-03, ENTY-04, ENTY-05, ENTY-06, ENTY-07, ENTY-08, ENTY-09, ENTY-10, ENTY-11, ENTY-12, ENTY-13, RESO-01, RESO-02, RESO-03, RESO-04, EDGE-01, EDGE-02, EDGE-03, EDGE-04, EDGE-05, EDGE-06, EDGE-07, EDGE-08, EDGE-09, EDGE-10, EDGE-11, EDGE-12, VERI-01, VERI-02, VERI-03, VERI-04, VERI-05, GATE-01, GATE-02, GATE-03, GATE-04, GATE-05
**Success Criteria** (what must be TRUE):

  1. Operator can enable or disable catalog writes via config; when enabled, a fixed `GRAPHITI_CATALOG_UUID_NAMESPACE` and batch limits (defaults 500/2000/5000) are validated, and the server never auto-generates the namespace
  2. MCP client can call `upsert_typed_entities` and `upsert_typed_edges` and observe deterministic UUIDv5 identity, 64-char lowercase SHA-256 audit, embed-before-transaction ordering, atomic commit or full rollback, structured item-level errors, and no LLM/queue/caller-UUID authority or implicit endpoint creation
  3. MCP client can call read-only `resolve_typed_entities` and `verify_catalog_batch` and observe missing, generic, duplicate, mistyped, UUID-mismatch, missing-embedding, and endpoint issues without graph writes
  4. Existing `search_nodes` and `search_memory_facts` retrieve catalog entities and facts created only under `oracle-catalog-tool-test` with expected type filters
  5. Phase 1 quality gate is green: focused unit tests, Neo4j integration on `oracle-catalog-tool-test` only, format/lint/changed-code typecheck, MCP tool-schema listing, relevant existing MCP regressions, and a short Phase 1 report that explicitly gates Phase 2

**Plans:** 8/8 plans executed (6 planned + 2 gap-closure)

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — CatalogConfig, allowlisted models, UUIDv5/SHA-256 identity (TDD)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — CatalogNeo4jStore + upsert_typed_entities service/tool (TDD)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — resolve_typed_entities + verify_catalog_batch read-only (TDD)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — upsert_typed_edges with exact endpoints (TDD)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-05-PLAN.md — Neo4j integration GATE-02/03 under oracle-catalog-tool-test (TDD)

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 01-06-PLAN.md — format/lint/typecheck/schema/regressions + Phase 1 report (GATE-04/05)

**Wave 7** *(gap closure after independent verify)*

- [x] 01-07-PLAN.md — CONF-04/SAFE-03/VERI-03 bounds, all-row edge verify, isolation

**Wave 8** *(gap closure after 01-07 re-verify)*

- [x] 01-08-PLAN.md — RESO-03/VERI-02 all-row resolve + entity elementId

### Phase 2: Provenance and Atomic Batch

**Goal**: Operators can attach installed-schema provenance, observe restart-safe non-Entity batch status, and commit complete catalog batches atomically with documented operator guidance
**Depends on**: Phase 1 complete quality gate and Phase 1 report
**Requirements**: IDEN-03, IDEN-04, PROV-01, PROV-02, PROV-03, PROV-04, PROV-05, PROV-06, STAT-01, STAT-02, STAT-03, STAT-04, STAT-05, STAT-06, BATC-01, BATC-02, BATC-03, BATC-04, BATC-05, BATC-06, BATC-07, BATC-08, BATC-09, BATC-10, BATC-11, BATC-12, DOCS-01, DOCS-02, DOCS-03, DOCS-04, DOCS-05
**Success Criteria** (what must be TRUE):

  1. MCP client can call `upsert_provenance` against existing entity/edge targets using installed Graphiti Episodic/MENTIONS (or closest compatible representation), with deterministic source UUIDv5 and hash, no `add_episode`/LLM/queue, and `provenance_target_missing` on missing targets with no partial write
  2. MCP client can call `upsert_catalog_batch` and observe full nested validation, same-request endpoint resolution, pre-transaction embeddings, one atomic domain transaction for entities+edges+provenance+committed status, domain rollback plus separate safe failed-status persistence on write failure, dry-run without writes, and `batch_conflict` on committed batch ID reused with different content
  3. MCP client can call `get_catalog_ingest_status` after server reinitialization and receive restart-safe terminal `CatalogIngestBatch` state (`committed`/`failed`) that does not appear in Graphiti entity search or community inputs; `planned`/`validating`/`embedding`/`writing` remain lifecycle response/progress vocabulary, with `writing` transaction-local
  4. Identical committed batch retries leave one logical set of domain objects; ACCEPT_TAB fixture, search interop, and safe `build_communities` execution succeed on `oracle-catalog-tool-test` only without normal upserts invoking communities
  5. Documentation and final verification cover all seven catalog MCP tool schemas, immutable namespace, allowlists, limits, idempotency, atomicity, structured errors, semantic-versus-deterministic guidance, sanitized ACCEPT_TAB and ConfigMap examples, rollout/rollback notes without deploying, exact check results, and canary recommendation only

**Plans**: 6/6 plans executed

- [x] 02-01-PLAN.md
- [x] 02-02-PLAN.md
- [x] 02-03-PLAN.md
- [x] 02-04-PLAN.md
- [x] 02-05-PLAN.md
- [x] 02-06-PLAN.md

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2. Phase 2 must not start until Phase 1 gate and report are complete.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Typed Catalog Primitives | 8/8 | Complete | 2026-07-17 |
| 2. Provenance and Atomic Batch | 6/6 | Complete    | 2026-07-17 |

## Coverage

| Phase | Requirement count | Categories |
|-------|-------------------|------------|
| 1 | 55 | CONF, SAFE, IDEN (entity/edge/audit), ENTY, RESO, EDGE, VERI, GATE |
| 2 | 31 | IDEN (source/batch), PROV, STAT, BATC, DOCS |
| **Total** | **86** | All v1 |

- v1 requirements: 86
- Mapped: 86/86
- Orphans: 0
- Duplicates: 0

## Explicit Non-Goals (this milestone)

- Kubernetes deployment automation
- Full production catalog ingest
- Live-group mutation (`oracle-catalog-v2`)
- `clear_graph` or existing-data deletion
- `add_memory` queue changes
- Multi-backend portability claims
- Automatic community creation on upsert

---
*Roadmap created: 2026-07-16*
