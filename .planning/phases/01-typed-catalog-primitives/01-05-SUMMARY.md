---
phase: 01-typed-catalog-primitives
plan: 05
subsystem: catalog-integration
tags: [catalog, neo4j, mcp, integration, gate-02, gate-03, composite-unique, concurrency, search]
status: complete

requires:
  - 01-02 typed entity upsert store/service
  - 01-03 entity resolve/verify + MCP tools
  - 01-04 typed edge upsert + endpoint resolve
provides:
  - Live Neo4j GATE-02/03 suite under oracle-catalog-tool-test
  - CATALOG_INT_REQUIRED fail-not-skip policy
  - Production composite (uuid, group_id) UNIQUENESS constraints created by product path only
  - Schema ensure only after embed + non-dry-run on entity/edge write paths
  - Edge episodes=[] create-path for stock EntityEdge search interop
  - Identity property create-once (name/graph_key/name_raw/name_canonical)
  - Endpoint resolve prefers expected UUIDv5; rejects non-deterministic typed-only rows
affects:
  - Phase 1 gate report
  - Phase 2 provenance / atomic multi-kind batches

tech-stack:
  added: []
  patterns:
    - FakeEmbedder fixed vectors + real CatalogService + Neo4jDriver.transaction
    - Product CREATE CONSTRAINT IF NOT EXISTS composite (uuid, group_id) for Entity and RELATES_TO
    - Composite MERGE keys match uniqueness: {uuid, group_id}
    - Scoped DETACH DELETE teardown for oracle-catalog-tool-test only
    - Fixture zero DROP — never drops stock Graphiti RANGE indexes or product constraints

key-files:
  created:
    - mcp_server/tests/test_catalog_neo4j_int.py
  modified:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/tests/test_catalog_store_unit.py
    - mcp_server/tests/test_catalog_service.py
    - mcp_server/tests/test_catalog_neo4j_int.py

key-decisions:
  - "Product owns catalog_entity_identity_unique and catalog_relates_to_identity_unique composite UNIQUE — fixtures never manufacture uniqueness"
  - "Composite (uuid, group_id) UNIQUE coexists with stock Graphiti RANGE indexes on uuid; single-property UNIQUE does not"
  - "Schema ensure only after successful embed and non-dry-run, immediately before real write tx; resolve/verify never ensure"
  - "name/graph_key/name_raw/name_canonical are create-once; mismatch → deterministic_uuid_conflict"
  - "Endpoint resolve prefers expected UUIDv5; wrong-only typed row → deterministic_uuid_conflict"
  - "Catalog edges set e.episodes=[] on create so graphiti_core search EntityEdge validation succeeds"
  - "CATALOG_INT_REQUIRED=1 hard-fails when Neo4j missing; never report skip as GATE-02 green"

patterns-established:
  - "Integration fixtures hardcode group_id=oracle-catalog-tool-test; never clear_graph; zero DROP"
  - "RecordingLLM/RecordingQueue spies prove GATE-03 no LLM/queue path"
  - "Search interop via graphiti_core.search + NODE/EDGE_HYBRID_SEARCH_RRF with FakeEmbedder"
  - "Structured schema failures use type(exc).__name__ only — never raw exception text"

requirements-completed:
  - ENTY-12
  - ENTY-13
  - EDGE-12
  - GATE-01
  - GATE-02
  - GATE-03

coverage:
  - id: D1
    description: Live Neo4j happy path six entity types + four structural + two distinct FK edges
    requirement: GATE-02
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_happy_path_six_entities_and_six_edges
        status: pass
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_two_fk_edges_distinct_keys_same_endpoints
        status: pass
    human_judgment: false
  - id: D2
    description: Resolve/verify, create/update/unchanged, conflicts, missing/generic/wrong endpoints
    requirement: ENTY-13
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_resolve_and_verify_found
        status: pass
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_identical_retry_unchanged_preserves_storage
        status: pass
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_missing_endpoint_and_type_and_generic
        status: pass
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_name_raw_canonical_in_hash_identity_stable
        status: pass
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_typed_duplicate_endpoint_does_not_bind_wrong_uuid
        status: pass
    human_judgment: false
  - id: D3
    description: Concurrent identical entity/edge one logical object; atomic entity/edge rollback
    requirement: ENTY-12
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_concurrent_identical_entity_one_node
        status: pass
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_concurrent_identical_edge_one_rel
        status: pass
    human_judgment: false
  - id: D4
    description: GATE-03 no LLM/queue; search interop with FakeEmbedder
    requirement: GATE-03
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_no_llm_or_queue_side_effects
        status: pass
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_search_nodes_and_facts_interop
        status: pass
    human_judgment: false

metrics:
  duration: reopen-production-constraints
  completed: 2026-07-16
  tasks: 1
  files_changed: 5
---

# Phase 01 Plan 05: Live Neo4j GATE-02/03 Summary

Production composite identity uniqueness + live GATE-02 suite under `oracle-catalog-tool-test` with FakeEmbedder, real CatalogService, Neo4jDriver.transaction; fixture never manufactures UNIQUE.

## What Was Built

### Product schema (composite UNIQUE)

- `catalog_entity_identity_unique` FOR (n:Entity) REQUIRE (n.uuid, n.group_id) IS UNIQUE
- `catalog_relates_to_identity_unique` FOR ()-[e:RELATES_TO]-() REQUIRE (e.uuid, e.group_id) IS UNIQUE
- CREATE IF NOT EXISTS only; never DROP INDEX / DROP CONSTRAINT / data repair
- Async once-ready lock; product path never branches on unittest.mock — test doubles supply real async execute_query
- Fail-closed schema verify: after CREATE always SHOW; named constraints must match UNIQUENESS + entityType + label + exact `{uuid, group_id}` props
- Entity/edge MERGE keys: `{uuid, group_id}` (match constraint)

### Schema ensure timing

Exactly two `_ensure_schema` call sites:

1. `upsert_typed_entities` — after embed + dry-run return, before write
2. `upsert_typed_edges` — after embed + dry-run return, before write

`resolve_typed_entities` and `verify_catalog_batch` never ensure or write.

### Identity + endpoints

- Create-once identity props: name/graph_key/name_raw/name_canonical → `deterministic_uuid_conflict`
- Endpoint resolve prefers expected UUIDv5; non-deterministic typed-only → conflict
- Two exact typed same-key: expected UUID wins when present; wrong-only fails closed
- Edge create still sets `e.episodes=[]` for stock search interop

### Live suite (`test_catalog_neo4j_int.py`)

- 20 tests, `CATALOG_INT_REQUIRED=1`
- Fixture: ZERO DROP statements
- Group teardown only (`oracle-catalog-tool-test`)
- Fresh-schema rerun: product creates both composites on first real write

## Verification Results

| Gate | Result |
|------|--------|
| Live int (`CATALOG_INT_REQUIRED=1`) | **20 passed** |
| Unit store+service | **104 passed** |
| Ruff check (touched files) | **All checks passed** |
| Ruff format | **5 files already formatted** |
| Pyright (catalog_service/store) | **0 errors** |
| SHOW CONSTRAINTS (post-run) | both catalog_* composites present; properties `[uuid, group_id]` |
| Group teardown | nodes=0, edges=0 |

## Invalid Prior Approach (corrected)

Original concurrent green path used fixture DROP of stock RANGE + CREATE single-property UNIQUE. That was **not** product-owned, cannot coexist with Graphiti stock indexes on shared DBs, and is **invalid** for GATE-02.

Correct path: product composite UNIQUE + composite MERGE; fixture never DROP; concurrent tests pass under stock Graphiti RANGE + product composites.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Search ValidationError on episodes=None**
- **Found during:** Live search interop
- **Fix:** ON CREATE set `e.episodes=[]`
- **Files:** `catalog_store.py`, unit assert
- **Commit:** `81a9c99` / `6816663`

**2. [Rule 2 - Critical] Fixture-manufactured UNIQUE invalid**
- **Found during:** Gate reopen
- **Issue:** Fixture DROP RANGE + single-prop UNIQUE not production
- **Fix:** Product composite constraints; zero fixture DROP; MERGE composite keys
- **Files:** `catalog_store.py`, `catalog_service.py`, int/unit tests

**3. [Rule 2 - Critical] Schema ensure on resolve/verify and early edge path**
- **Issue:** Read-only paths and pre-embed edge path called ensure
- **Fix:** Ensure only post-embed non-dry-run write paths; unit asserts ensure not awaited on resolve/verify/dry-run

**4. [Rule 2 - Critical] Identity names updatable / endpoint arbitrary bind**
- **Fix:** Identity property conflict; expected UUID endpoint preference; live tests updated

## Known Stubs

None.

## Threat Flags

None beyond plan threat model (parameterized Cypher, allowlisted labels, structured schema errors).

## Self-Check: PASSED

- `mcp_server/tests/test_catalog_neo4j_int.py` FOUND
- Product constraint names FOUND via SHOW after live run
- Live 20/20 FOUND
- Units 102/102 FOUND
- Group residual 0/0 FOUND
