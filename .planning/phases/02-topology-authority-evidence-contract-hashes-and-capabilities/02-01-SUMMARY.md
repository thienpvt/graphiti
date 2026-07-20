---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
plan: 01
subsystem: catalog-topology
tags: [topology, edge-endpoint-map, catalog-v2, tdd, fail-closed]

requires:
  - phase: 01-strict-contracts-and-catalog-v2-identity
    provides: CATALOG_EDGE_TYPES, CATALOG_ENTITY_TYPES, CatalogEdgeItem, CatalogService edge/batch paths
provides:
  - EDGE_ENDPOINT_MAP server-owned authority for all 16 edge types
  - validate_edge_endpoint_pair / is_edge_endpoint_pair_allowed / endpoint_map_export
  - CatalogEdgeItem + CatalogService topology preflight before resolve/embed/tx
affects:
  - 02-02 evidence contract
  - 02-04 capabilities export
  - Phase 3A topology hard gate

tech-stack:
  added: []
  patterns:
    - immutable frozenset pair maps as single topology authority
    - model + service defense-in-depth before side effects
    - model_construct spies for service-only preflight coverage

key-files:
  created:
    - mcp_server/src/models/catalog_topology.py
    - mcp_server/tests/test_catalog_topology.py
  modified:
    - mcp_server/src/models/catalog_edges.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "DocumentedBy expanded as explicit (entity, DictionaryDocument|SourceArtifact) pairs for all entity types (A8)"
  - "DependsOn is finite union of structural Contains + Calls/Reads/Writes pairs (no open any→any)"
  - "ForeignKeyTo retains dual Column-Column and Table-Table pairs for fixture compatibility"

patterns-established:
  - "Single EDGE_ENDPOINT_MAP authority; clients cannot supply map"
  - "Topology preflight first in edge identity loop and batch edge loop"
  - "ValueError text carries CatalogErrorCode.edge_endpoint_pair_not_allowed"

requirements-completed: [EDGE-01, EDGE-02, EDGE-03, EDGE-04, EDGE-05, EDGE-06, EDGE-07, EDGE-08, EDGE-09, TEST-02]

coverage:
  - id: D1
    description: Server-owned EDGE_ENDPOINT_MAP with exactly 16 keys matching CATALOG_EDGE_TYPES
    requirement: EDGE-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_topology.py::test_edge_endpoint_map_keys_equal_catalog_edge_types
        status: pass
    human_judgment: false
  - id: D2
    description: Exhaustive allow/reject matrix for all 16 edge types including deferred rejection
    requirement: EDGE-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_topology.py
        status: pass
    human_judgment: false
  - id: D3
    description: ForeignKeyTo dual Column-Column and Table-Table pairs; Column-Table rejected
    requirement: EDGE-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_topology.py::test_foreign_key_dual_pairs_and_column_table_reject
        status: pass
    human_judgment: false
  - id: D4
    description: Model + service preflight rejects illegal topology before resolve/embed/write
    requirement: EDGE-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_edge_topology_disallowed_pair_skips_resolve_embed_write
        status: pass
    human_judgment: false
  - id: D5
    description: Batch and dry-run paths share the same topology authority and fail closed
    requirement: TEST-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_batch_topology_disallowed_edge_skips_resolve_embed_write
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-18
status: complete
---

# Phase 02 Plan 01: Topology Authority Summary

**Immutable server-owned EDGE_ENDPOINT_MAP with model+service preflight so illegal edge topology never reaches resolve/embed/tx.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-18T02:43:03Z
- **Completed:** 2026-07-18T02:48:13Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Delivered `catalog_topology.py` with frozenset pair authority for all 16 catalog edge types
- Exhaustive 311-case unit matrix plus model/service spy coverage (330 focused tests green)
- Wired `validate_edge_endpoint_pair` into `CatalogEdgeItem` and both `upsert_typed_edges` / `upsert_catalog_batch` before any side effect
- Deferred types `LikelyReferencesTo` / `MapsTo` / `SynchronizesTo` remain unregistered

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Topology unit matrix** - `bb5d3c4` (test)
2. **Task 1 GREEN: EDGE_ENDPOINT_MAP authority** - `5145e0d` (feat)
3. **Task 2 RED: Model + service spies** - `5ae6f72` (test)
4. **Task 2 GREEN: Preflight wiring** - `f034318` (feat)

**Plan metadata:** (this commit)

_Note: TDD tasks used RED → GREEN commits; no REFACTOR commit needed._

## Files Created/Modified

- `mcp_server/src/models/catalog_topology.py` - EDGE_ENDPOINT_MAP + validate/export helpers
- `mcp_server/tests/test_catalog_topology.py` - exhaustive allow/reject matrix + model cases
- `mcp_server/src/models/catalog_edges.py` - CatalogEdgeItem topology model_validator
- `mcp_server/src/services/catalog_service.py` - typed-edge and batch topology preflight
- `mcp_server/tests/test_catalog_service.py` - resolve/embed/write spy tests for bad pairs

## Decisions Made

- Locked RESEARCH A1/A8 defaults: finite pair sets for broad families; DocumentedBy fully expanded
- DependsOn = Contains ∪ Calls ∪ ReadsFrom ∪ WritesTo (finite, not any→any)
- Dual ForeignKeyTo pairs retained for live Table-Table fixtures
- Service spies use `model_construct` so service preflight is tested independently of model validation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Temporary GREEN production copy under `/tmp` was clobbered by a prior `git checkout HEAD --` restore of un-wired files; re-applied wiring via explicit patch and committed `f034318`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Topology authority ready for plan 02-02 evidence contract and plan 02-04 capabilities (`endpoint_map_export`)
- Plan 02-02 must not edit `catalog_topology.py` or topology preflight in `catalog_service.py`
- No store/control-plane/canary changes; `oracle-catalog-v2` untouched

## TDD Gate Compliance

1. `test(02-01)` RED commits exist: `bb5d3c4`, `5ae6f72`
2. `feat(02-01)` GREEN commits after RED: `5145e0d`, `f034318`
3. No REFACTOR commit required

## Self-Check: PASSED

- FOUND: `mcp_server/src/models/catalog_topology.py`
- FOUND: `mcp_server/tests/test_catalog_topology.py`
- FOUND: commits `bb5d3c4`, `5145e0d`, `5ae6f72`, `f034318`
- Focused verify: 330 passed

---
*Phase: 02-topology-authority-evidence-contract-hashes-and-capabilities*
*Completed: 2026-07-18*
