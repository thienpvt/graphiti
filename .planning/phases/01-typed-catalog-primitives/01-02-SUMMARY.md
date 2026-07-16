---
phase: 01-typed-catalog-primitives
plan: 02
subsystem: catalog-entity-upsert
tags: [catalog, neo4j, mcp, upsert, embeddings, uuidv5, cypher]

requires:
  - 01-01 catalog models and identity helpers
provides:
  - CatalogNeo4jStore entity MERGE/ON CREATE/ON MATCH Cypher
  - CatalogService.upsert_typed_entities orchestration
  - MCP tool upsert_typed_entities registration
affects:
  - 01-03 resolve/verify and edge upsert
  - Phase 2 provenance/batch orchestration

tech-stack:
  added: []
  patterns:
    - Embed-before-transaction write order
    - Server allowlisted Cypher labels; never SET n = $map
    - Conditional ON MATCH preserves identical-hash properties including batch_id

key-files:
  created:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/tests/test_catalog_store_unit.py
    - mcp_server/tests/test_catalog_service.py
  modified:
    - mcp_server/src/graphiti_mcp_server.py

key-decisions:
  - "ON MATCH uses CASE WHEN content_sha256 equals request hash to leave batch_id/timestamps untouched"
  - "name_embedding from join of graph_key + database_qualified_name + summary via configured embedder"
  - "catalog_service singleton wired at initialize_server; lazy fallback in tool"

patterns-established:
  - "CatalogService gates: enabled → uuid_namespace → Neo4j provider → limits"
  - "Identical hash short-circuits before transaction; dry-run embeds without write"
  - "Atomic failure marks siblings rolled_back with structured neo4j_transaction_failed trigger"

requirements-completed:
  - SAFE-04
  - SAFE-05
  - ENTY-01
  - ENTY-02
  - ENTY-03
  - ENTY-04
  - ENTY-05
  - ENTY-06
  - ENTY-07
  - ENTY-08
  - ENTY-09
  - ENTY-10
  - ENTY-11
  - ENTY-12

coverage:
  - id: D1
    description: Allowlisted entity Cypher builders reject unknown types and avoid full-map SET
    requirement: SAFE-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py
        status: pass
    human_judgment: false
  - id: D2
    description: Embed before transaction; dry-run never writes; batch_id on create/changed update only
    requirement: ENTY-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_entity_embed_before_transaction_order
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_entity_dry_run_embeds_but_never_writes_or_persists_batch_id
        status: pass
    human_judgment: false
  - id: D3
    description: Atomic rollback and feature/backend gates return structured errors without queue/LLM
    requirement: ENTY-10
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_entity_atomic_rollback_on_store_failure
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_entity_no_queue_or_llm_calls
        status: pass
    human_judgment: false

duration: 18min
completed: 2026-07-16
status: complete
---

# Phase 01 Plan 02: Typed Catalog Entity Upsert Summary

**CatalogNeo4jStore entity Cypher and CatalogService.upsert_typed_entities with embed-before-tx, atomic/dry-run semantics, batch_id rules, and registered MCP tool.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-07-16T13:17:00Z
- **Completed:** 2026-07-16T13:35:10Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Safe entity MERGE builders: Entity + allowlisted custom label, parameterized props, nested JSON `source_refs`/`attributes`
- Service orchestration: gates, UUIDv5/hash, coalesce/conflict, embed-before-tx, atomic/per-item/dry-run
- MCP `upsert_typed_entities` registered without queue/LLM; logs batch_id and counts only

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **Task 1: CatalogNeo4jStore entity Cypher and transaction API**
   - `2f5b8e9` test(01-02): add failing tests for CatalogNeo4jStore entity Cypher
   - `7b1fe35` feat(01-02): implement CatalogNeo4jStore entity Cypher builders
2. **Task 2: CatalogService.upsert_typed_entities and MCP tool**
   - `8235a78` test(01-02): add failing tests for CatalogService entity upsert
   - `6a51724` feat(01-02): implement CatalogService entity upsert and MCP tool

## Files Created/Modified

- `mcp_server/src/services/catalog_store.py` — CatalogNeo4jStore, Cypher builders, JSON nested serialization
- `mcp_server/src/services/catalog_service.py` — CatalogService.upsert_typed_entities
- `mcp_server/src/graphiti_mcp_server.py` — tool + catalog_service singleton
- `mcp_server/tests/test_catalog_store_unit.py` — 16 Cypher/safety unit tests
- `mcp_server/tests/test_catalog_service.py` — 17 entity service/tool unit tests

## Decisions Made

- Conditional `CASE WHEN n.content_sha256 = $content_sha256` on ON MATCH so identical payloads leave `batch_id` and timestamps untouched without a separate no-op query branch in Neo4j for writes skipped client-side
- Service skips `upsert_entity_item` entirely on identical hash (no transaction write); dry-run still embeds for readiness
- Embedding text is `graph_key + database_qualified_name + summary` joined with spaces

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pyright attribute access on tuple vs EagerResult**
- **Found during:** Task 2 post-GREEN typecheck
- **Issue:** `result.records` after `isinstance(result, tuple)` branch left pyright believing remaining type was still tuple
- **Fix:** Use `getattr(result, 'records', None)` instead of `hasattr` + attribute access
- **Files modified:** `mcp_server/src/services/catalog_store.py`
- **Committed in:** `6a51724`

**2. [Rule 2 - Missing critical] Atomic failure must attribute error to failing item**
- **Found during:** Task 2 GREEN (atomic rollback test)
- **Issue:** Initial catch always marked first write item as trigger
- **Fix:** Track `current_prep` during loop so trigger index matches the item that raised
- **Files modified:** `mcp_server/src/services/catalog_service.py`
- **Committed in:** `6a51724`

## Threat Flags

None beyond plan register. New MCP tool surface is intentional (additive schema); no auth path change. Mitigations T-01-05..08 applied: allowlisted labels, embed-before-tx, safe logs, server UUIDv5 MERGE only.

## Known Stubs

None. Entity path fully wired under unit mocks. Live Neo4j coverage deferred to integration plan (ENTY-12 concurrency / ENTY-13 search).

## TDD Gate Compliance

- RED commits: `2f5b8e9`, `8235a78`
- GREEN commits after RED: `7b1fe35`, `6a51724`
- Verification: `uv run pytest tests/test_catalog_store_unit.py tests/test_catalog_service.py -q` → 33 passed
- Verification: `uv run pyright` on changed paths → 0 errors

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_store.py`
- FOUND: `mcp_server/src/services/catalog_service.py`
- FOUND: `mcp_server/src/graphiti_mcp_server.py` (`upsert_typed_entities`)
- FOUND: `mcp_server/tests/test_catalog_store_unit.py`
- FOUND: `mcp_server/tests/test_catalog_service.py`
- FOUND commits: `2f5b8e9`, `7b1fe35`, `8235a78`, `6a51724`
