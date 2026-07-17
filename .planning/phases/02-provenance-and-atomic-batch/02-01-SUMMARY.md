---
phase: 02-provenance-and-atomic-batch
plan: 01
subsystem: api
tags: [uuidv5, pydantic, provenance, batch, catalog, identity]

requires:
  - phase: 01-typed-catalog-primitives
    provides: catalog_entity_uuid/catalog_edge_uuid, allowlists, CatalogEntityItem/CatalogEdgeItem, CatalogErrorCode
provides:
  - catalog_source_uuid / catalog_batch_uuid / catalog_mentions_uuid
  - CatalogSourceItem and UpsertProvenanceRequest
  - UpsertCatalogBatchRequest with atomic=true and nested collections
  - GetCatalogIngestStatusRequest and CatalogIngestStatusResponse
affects:
  - 02-02 provenance service
  - 02-03 batch orchestration
  - 02-04 status persistence

tech-stack:
  added: []
  patterns:
    - Server-only UUIDv5 helpers mirrored on entity/edge style
    - Nested batch reuses Phase 1 entity/edge item schemas
    - Literal[True] atomic gate for whole-batch writes
    - Status response omits payload/secret fields

key-files:
  created:
    - mcp_server/src/models/catalog_provenance.py
    - mcp_server/src/models/catalog_batch.py
  modified:
    - mcp_server/src/services/catalog_identity.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/tests/test_catalog_identity.py
    - mcp_server/tests/test_catalog_models.py

key-decisions:
  - "Mentions formula locked as group_id|Mentions|source_uuid|entity_uuid"
  - "UpsertCatalogBatchRequest.atomic is Literal[True]; false rejected at model boundary"
  - "Nested provenance uses NestedProvenancePayload with min one source"
  - "At least one of entities/edges/provenance required for batch"

patterns-established:
  - "Identity helpers: pure uuid5(ns, group|Kind|key...) returning str"
  - "Phase 2 request models reuse Phase 1 validators/allowlists"
  - "Status models: six-literal enum, bounded error_summary, no payloads"

requirements-completed: [IDEN-03, IDEN-04, PROV-02, BATC-01, BATC-02, STAT-02, STAT-03]

coverage:
  - id: D1
    description: catalog_source_uuid / catalog_batch_uuid / catalog_mentions_uuid match UUIDv5 formulas
    requirement: IDEN-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py#test_catalog_source_uuid_matches_uuid5
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py#test_catalog_batch_uuid_matches_uuid5
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py#test_catalog_mentions_uuid_matches_uuid5
        status: pass
    human_judgment: false
  - id: D2
    description: CatalogSourceItem and UpsertProvenanceRequest validate PROV-02 fields
    requirement: PROV-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_catalog_source_item_preserves_exact_reference_time
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_upsert_provenance_request_accepts_valid
        status: pass
    human_judgment: false
  - id: D3
    description: UpsertCatalogBatchRequest rejects atomic=false and empty-all collections
    requirement: BATC-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_upsert_catalog_batch_rejects_atomic_false
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_upsert_catalog_batch_rejects_empty_all_collections
        status: pass
    human_judgment: false
  - id: D4
    description: CatalogIngestStatusResponse exposes six status literals without payload fields
    requirement: STAT-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_catalog_ingest_status_response_six_literals
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_catalog_ingest_status_response_no_payload_or_secret_fields
        status: pass
    human_judgment: false

duration: 17min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 01: Identity and Request Models Summary

**UUIDv5 source/batch/mentions helpers plus Pydantic provenance, atomic batch, and ingest-status models with pure unit coverage**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-17T00:21:03Z
- **Completed:** 2026-07-17T00:38:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added pure `catalog_source_uuid`, `catalog_batch_uuid`, `catalog_mentions_uuid` matching fixed UUIDv5 formulas
- Shipped `CatalogSourceItem` / targets / `UpsertProvenanceRequest` with allowlists, protected keys, hash and nested bounds
- Shipped `UpsertCatalogBatchRequest` reusing entity/edge items, requiring `atomic=true` and non-empty work
- Shipped `GetCatalogIngestStatusRequest` and `CatalogIngestStatusResponse` with six status literals and no payload/secret fields

## Task Commits

Each task was committed atomically:

1. **Task 1: RED/GREEN source, batch, mentions UUIDv5 helpers** - `a20ae39` (feat)
2. **Task 2: RED/GREEN provenance, batch, status Pydantic models** - `e909074` (feat)

**Plan metadata:** (this commit)

_Note: TDD tasks combined RED+GREEN into one commit per task after green verification._

## Files Created/Modified

- `mcp_server/src/services/catalog_identity.py` - source/batch/mentions UUIDv5 helpers
- `mcp_server/src/models/catalog_provenance.py` - source item, targets, upsert provenance request
- `mcp_server/src/models/catalog_batch.py` - nested atomic batch + status request
- `mcp_server/src/models/catalog_responses.py` - ingest status + batch write response shapes
- `mcp_server/tests/test_catalog_identity.py` - identity formula and purity tests
- `mcp_server/tests/test_catalog_models.py` - provenance/batch/status validation tests

## Decisions Made

- Mentions identity locked to `group_id|Mentions|source_uuid|entity_uuid` (A3)
- Batch `atomic` is `Literal[True]` so false is rejected at the model boundary
- Nested provenance requires `sources min_length=1`; batch allows provenance-only work
- Empty entities+edges+provenance rejected; optional provenance list may be null when entities/edges present
- Status response fields omit any full request/payload/secret keys; `error_summary` max 512

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Wave-1 identity and trust-boundary models ready for provenance service and batch orchestration plans
- No I/O, Neo4j, or MCP tool registration in this plan (by design)

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_identity.py` helpers
- FOUND: `mcp_server/src/models/catalog_provenance.py`
- FOUND: `mcp_server/src/models/catalog_batch.py`
- FOUND: `mcp_server/src/models/catalog_responses.py` status types
- FOUND: commit `a20ae39`
- FOUND: commit `e909074`
- TESTS: 106 passed (`test_catalog_identity.py` + `test_catalog_models.py`)

---
*Phase: 02-provenance-and-atomic-batch*
*Completed: 2026-07-17*
