---
phase: 01-typed-catalog-primitives
plan: 04
subsystem: catalog-edge-upsert
tags: [catalog, neo4j, mcp, edges, endpoints, relates_to, embeddings, uuidv5]

requires:
  - 01-01 catalog models and identity helpers
  - 01-02 catalog entity upsert store/service patterns
provides:
  - CatalogNeo4jStore resolve_endpoint_typed MATCH-only helpers
  - CatalogNeo4jStore edge RELATES_TO MERGE with conditional batch_id
  - CatalogService.upsert_typed_edges orchestration
  - MCP tool upsert_typed_edges
affects:
  - 01-05 integration search / EDGE-12
  - Phase 2 provenance and atomic multi-kind batches

tech-stack:
  added: []
  patterns:
    - Endpoint resolve before fact_embedding; embed before write transaction
    - Fixed RELATES_TO relationship type; allowlisted edge type in e.name param only
    - Conditional ON MATCH CASE preserves identical-hash batch_id/timestamps

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_store_unit.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Endpoint MATCH returns all Entity by group_id+name; classify_endpoint_rows maps missing/type/generic"
  - "Edge MERGE key is server UUIDv5 only; e.name parameterized allowlisted edge_type"
  - "Identity conflict checked on existing edge type/key/source/target before embed/write"

patterns-established:
  - "resolve both endpoints before any fact_embedding call"
  - "identical edge hash short-circuits before transaction; dry-run embeds without write"
  - "Multiple ForeignKeyTo edges allowed when edge_key (hence UUIDv5) differs"

requirements-completed:
  - EDGE-01
  - EDGE-02
  - EDGE-03
  - EDGE-04
  - EDGE-05
  - EDGE-06
  - EDGE-07
  - EDGE-08
  - EDGE-09
  - EDGE-10
  - EDGE-11

coverage:
  - id: D1
    description: Endpoint MATCH-only resolution returns missing_endpoint / endpoint_type_mismatch / generic_endpoint_conflict without CREATE
    requirement: EDGE-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_edge_classify_endpoint_missing_wrong_label_generic
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_edge_missing_endpoint_before_embed_no_write
        status: pass
    human_judgment: false
  - id: D2
    description: Edge RELATES_TO upsert with parameterized e.name, fact_embedding before tx, batch_id create/changed only
    requirement: EDGE-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_edge_embed_before_transaction_order
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_edge_create_persists_request_batch_id
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_edge_identical_hash_unchanged_leaves_batch_id
        status: pass
    human_judgment: false
  - id: D3
    description: Multi-key ForeignKeyTo, atomic rollback, identity conflict, MCP tool registered
    requirement: EDGE-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_edge_two_foreign_key_same_endpoints_different_keys
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_edge_atomic_rollback_on_store_failure
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_mcp_tool_upsert_typed_edges_registered
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-16
status: complete
---

# Phase 01 Plan 04: Typed Catalog Edge Upsert Summary

**Typed `upsert_typed_edges` with exact endpoint resolution, embed-before-tx RELATES_TO writes, batch_id rules, atomic/dry-run, and structured edge errors — no implicit endpoints.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-16T13:56:57Z
- **Completed:** 2026-07-16T14:09:00Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- `CatalogNeo4jStore`: `resolve_endpoint_typed` MATCH-only + classify; `build_edge_upsert_cypher` RELATES_TO MERGE with conditional batch_id; identity conflict helper
- `CatalogService.upsert_typed_edges`: gate → hash → endpoints → embed → dry-run/write; atomic rollback; multi ForeignKeyTo keys
- MCP tool `upsert_typed_edges` registered additively; entity/resolve/verify paths preserved
- Unit coverage for EDGE-01..11 (EDGE-12 deferred to integration search)

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **Task 1: RED/GREEN endpoint resolution and edge Cypher store**
   - `b62fd32` test(01-04): add failing tests for edge store and endpoint resolution
   - `04074bb` feat(01-04): implement edge store endpoint resolution and RELATES_TO upsert
2. **Task 2: RED/GREEN CatalogService.upsert_typed_edges and MCP tool**
   - `e9138c0` test(01-04): add failing tests for upsert_typed_edges service path
   - `e58a266` feat(01-04): implement upsert_typed_edges service and MCP tool

## Files Created/Modified

- `mcp_server/src/services/catalog_store.py` — resolve_endpoint_typed, edge MERGE/get/params/conflict
- `mcp_server/src/services/catalog_service.py` — upsert_typed_edges full orchestration
- `mcp_server/src/graphiti_mcp_server.py` — upsert_typed_edges MCP tool
- `mcp_server/tests/test_catalog_store_unit.py` — edge Cypher/endpoint unit tests
- `mcp_server/tests/test_catalog_service.py` — edge service unit tests

## Decisions Made

- Endpoint Cypher MATCH is label-agnostic on Entity; classification distinguishes typed vs generic vs wrong label so generic_endpoint_conflict is observable
- Edge relationship type is always RELATES_TO; client edge_type only enters as parameterized `e.name`
- Existing edge identity conflict short-circuits before embedding when type/key/source/target disagree

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

- RED commits present: `b62fd32`, `e9138c0`
- GREEN commits present: `04074bb`, `e58a266`

## Verification

- `uv run pytest tests/test_catalog_store_unit.py tests/test_catalog_service.py tests/test_catalog_models.py tests/test_catalog_identity.py -q` → 131 passed
- Ruff clean on modified catalog files
- Pyright 0 errors (mcp_server package + portable root path)

## Self-Check: PASSED

- FOUND: mcp_server/src/services/catalog_store.py
- FOUND: mcp_server/src/services/catalog_service.py
- FOUND: mcp_server/src/graphiti_mcp_server.py
- FOUND: mcp_server/tests/test_catalog_store_unit.py
- FOUND: mcp_server/tests/test_catalog_service.py
- FOUND: commits b62fd32, 04074bb, e9138c0, e58a266
