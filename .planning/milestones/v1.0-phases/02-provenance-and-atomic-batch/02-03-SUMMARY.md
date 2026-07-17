---
phase: 02-provenance-and-atomic-batch
plan: 03
subsystem: api
tags: [status, CatalogIngestBatch, neo4j, catalog, mcp, restart-safe]

requires:
  - phase: 02-provenance-and-atomic-batch
    provides: catalog_batch_uuid, GetCatalogIngestStatusRequest, CatalogIngestStatusResponse
  - phase: 01-typed-catalog-primitives
    provides: CatalogNeo4jStore, CatalogService, MCP catalog tool pattern
provides:
  - build_batch_status_upsert_cypher / prepare_batch_status_params / upsert_batch_status
  - build_get_batch_status_cypher / get_batch_status
  - CatalogService.get_catalog_ingest_status
  - MCP tool get_catalog_ingest_status
affects:
  - 02-04 atomic batch orchestration (terminal status writers)
  - 02-05/02-06 live Neo4j batch integration

tech-stack:
  added: []
  patterns:
    - Non-Entity CatalogIngestBatch MERGE by uuid+group_id
    - Terminal committed/failed only persisted; six lifecycle literals remain on response model
    - Allowlisted status props; bounded error_summary (512)
    - Read-only MCP status path with reinit-safe store read

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_store_unit.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Status writers accept only terminal committed/failed; intermediate lifecycle literals not persisted"
  - "Missing status returns status=failed + validation_error + error_summary 'batch status not found' (model has no error_message field)"
  - "error_summary max 512 chars, matching CatalogIngestStatusResponse and MAX_SHORT_STRING_LENGTH"

patterns-established:
  - "Status Cypher: CatalogIngestBatch only, no Entity, no SET-map wipe"
  - "get_catalog_ingest_status: gate → catalog_batch_uuid → get_batch_status → map response"

requirements-completed: [STAT-01, STAT-04, STAT-05, STAT-06]

coverage:
  - id: D1
    description: CatalogIngestBatch status Cypher has no Entity label and allowlisted props only
    requirement: STAT-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_build_batch_status_upsert_cypher_no_entity_label
        status: pass
    human_judgment: false
  - id: D2
    description: Status params allowlist; terminal-only; bounded error_summary; no secrets/payloads
    requirement: STAT-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_prepare_batch_status_params_allowlist_and_terminal_only
        status: pass
    human_judgment: false
  - id: D3
    description: get_catalog_ingest_status reads Neo4j via store; reinit new service still returns status
    requirement: STAT-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_status_reinit_new_service_reads_from_store
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_status_found_maps_response_no_payload_fields
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_mcp_tool_get_catalog_ingest_status_registered
        status: pass
    human_judgment: false
  - id: D4
    description: Status node excluded from entity search by omitting Entity label
    requirement: STAT-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_build_batch_status_upsert_cypher_no_entity_label
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_build_get_batch_status_cypher_group_scoped
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 03: Status Store and Read Tool Summary

**Non-Entity CatalogIngestBatch status persistence plus read-only get_catalog_ingest_status MCP tool with unit coverage for shape safety and restart-oriented reads**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-17T00:36:42Z
- **Completed:** 2026-07-17T00:49:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Store Cypher builders/executors for `CatalogIngestBatch` without `Entity` label; allowlisted properties only
- Terminal `committed`/`failed` write gate; bounded sanitized `error_summary` (512)
- `CatalogService.get_catalog_ingest_status` derives batch uuid, reads store, maps response; no writes/embed/LLM/queue
- MCP tool `get_catalog_ingest_status` registered; reinit-style new service still reads store

## Task Commits

Each task was committed atomically:

1. **Task 1: RED CatalogIngestBatch store tests** - `d71dc1c` (test)
2. **Task 1: GREEN status store primitives** - `e1624d4` (feat)
3. **Task 2: RED get_catalog_ingest_status service tests** - `1d1d145` (test)
4. **Task 2: GREEN service + MCP tool** - `c0aa78b` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD tasks have multiple commits (test → feat)_

## Files Created/Modified

- `mcp_server/src/services/catalog_store.py` - batch status MERGE/get/prepare/upsert
- `mcp_server/src/services/catalog_service.py` - `get_catalog_ingest_status`
- `mcp_server/src/graphiti_mcp_server.py` - MCP tool registration
- `mcp_server/tests/test_catalog_store_unit.py` - status Cypher/unit cases
- `mcp_server/tests/test_catalog_service.py` - status service/MCP cases

## Decisions Made

- Persist only terminal statuses at store boundary; response model keeps six lifecycle literals for future batch plan intermediate reporting
- Missing batch uses `error_code=validation_error` and `error_summary='batch status not found'` because `CatalogIngestStatusResponse` has no `error_message` field
- Dry-run status prohibition deferred to batch plan writers (status writers unused on dry_run)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Missing status used non-existent error_message field**
- **Found during:** Task 2 GREEN
- **Issue:** `CatalogIngestStatusResponse` exposes `error_summary` / `error_code` only; tests asserted `error_message`
- **Fix:** Service puts not-found/gated text in `error_summary`; test updated
- **Files modified:** `catalog_service.py`, `test_catalog_service.py`
- **Committed in:** `c0aa78b`

## TDD Gate Compliance

- RED: `d71dc1c`, `1d1d145`
- GREEN: `e1624d4`, `c0aa78b`
- No REFACTOR commit needed

## Known Stubs

None. Status writers ready for batch plan; no intermediate status persistence implemented here (intentional).

## Threat Flags

None beyond plan threat model (T-02-20/21/22 mitigated by allowlist, group_id+uuid MATCH, no Entity).

## Verification

```
cd mcp_server && uv run pytest tests/test_catalog_store_unit.py tests/test_catalog_service.py -k status -q
# 14 passed
uv run ruff check (scoped) — clean
uv run pyright (scoped store/service/mcp) — 0 errors
```

## Self-Check: PASSED
