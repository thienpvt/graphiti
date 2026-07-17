---
phase: 02-provenance-and-atomic-batch
plan: 02
subsystem: api
tags: [provenance, episodic, mentions, neo4j, catalog, mcp]

requires:
  - phase: 02-provenance-and-atomic-batch
    provides: catalog_source_uuid/catalog_mentions_uuid, UpsertProvenanceRequest
  - phase: 01-typed-catalog-primitives
    provides: CatalogNeo4jStore, CatalogService, MCP catalog tool pattern
provides:
  - build_source_episode_upsert_cypher / upsert_source_episode
  - build_mentions_merge_cypher / upsert_mentions_link
  - build_append_edge_episode_cypher / append_edge_episode
  - CatalogService.upsert_provenance
  - MCP tool upsert_provenance
affects:
  - 02-03 batch orchestration
  - 02-04 status persistence
  - 02-05 live Neo4j provenance integration

tech-stack:
  added: []
  patterns:
    - Episodic MERGE preserve-on-update without Entity label or SET-map wipe
    - APOC-free RELATES_TO.episodes membership dedup append
    - Target preflight fail-closed before any provenance write
    - Sources skip embedder; single domain tx for sources+links

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_store_unit.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Edge content update no longer SETs e.episodes (append-only provenance owns list)"
  - "Source EpisodeType value fixed to json; content is bounded metadata JSON"
  - "Idempotent path pre-reads source hash + MENTIONS + edge episode membership"
  - "Missing/mistyped targets map to provenance_target_missing with atomic rolled_back siblings"

patterns-established:
  - "Store builders: fixed labels only, create-token status, ON CREATE identity"
  - "Service order: gate → hash → resolve targets → dry_run|schema+tx → counts log only"
  - "MCP catalog tools: batch_id/count logging, ErrorResponse without payload dump"

requirements-completed: [PROV-01, PROV-03, PROV-04, PROV-05, PROV-06]

coverage:
  - id: D1
    description: Source episode Cypher is Episodic-only MERGE without Entity/SET-map wipe
    requirement: PROV-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_build_source_episode_upsert_cypher_episodic_no_entity_label
        status: pass
    human_judgment: false
  - id: D2
    description: MENTIONS merge is group-scoped with deterministic uuid; edge episodes append is APOC-free
    requirement: PROV-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_build_mentions_merge_cypher_group_scoped_deterministic_uuid
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_build_append_edge_episode_cypher_apoc_free_dedup
        status: pass
    human_judgment: false
  - id: D3
    description: Missing target returns provenance_target_missing with zero store writes
    requirement: PROV-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_provenance_missing_target_fail_closed_no_writes
        status: pass
    human_judgment: false
  - id: D4
    description: Identical source+links return unchanged; no embed/LLM/queue
    requirement: PROV-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_provenance_idempotent_unchanged_skips_write
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_provenance_happy_path_writes_source_and_mentions_no_embed
        status: pass
    human_judgment: false
  - id: D5
    description: upsert_provenance MCP tool registered
    requirement: PROV-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_mcp_tool_upsert_provenance_registered
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 02: Provenance Store and Service Summary

**Episodic/MENTIONS/episodes provenance writers plus CatalogService.upsert_provenance and MCP registration with fail-closed target preflight**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-17T00:26:25Z
- **Completed:** 2026-07-17T00:34:13Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Store Cypher for Episodic sources (no Entity label), deterministic MENTIONS, APOC-free edge episode append
- Extended provenance presence to cover RELATES_TO.episodes; stopped edge content updates from wiping episodes
- CatalogService.upsert_provenance with gate, target resolve, dry_run, idempotent unchanged, atomic fail-closed
- MCP tool upsert_provenance registered; no add_episode/LLM/queue/embedder on path

## Task Commits

Each task was committed atomically:

1. **Task 1: RED/GREEN store Cypher for Episodic, MENTIONS, edge episodes** - `47eed93` (feat)
2. **Task 2: RED/GREEN CatalogService.upsert_provenance + MCP tool** - `b8135a7` (feat)

**Plan metadata:** (this commit)

_Note: TDD tasks combined RED+GREEN into one commit per task after green verification._

## Files Created/Modified

- `mcp_server/src/services/catalog_store.py` - source/mentions/append builders + helpers; edge update no episodes wipe; presence covers edges
- `mcp_server/src/services/catalog_service.py` - `_PreparedSource`, `upsert_provenance` orchestration
- `mcp_server/src/graphiti_mcp_server.py` - `upsert_provenance` MCP tool
- `mcp_server/tests/test_catalog_store_unit.py` - provenance Cypher/unit helpers
- `mcp_server/tests/test_catalog_service.py` - provenance service + MCP registration tests

## Decisions Made

- Edge content update SET no longer assigns `e.episodes` (create still seeds `[]`)
- Source `source` property fixed to `json`; content is bounded allowlisted metadata JSON
- Idempotency checks source hash and existing MENTIONS/edge membership before skipping writes
- Atomic missing target fans `provenance_target_missing` and sibling `rolled_back` / batch_conflict pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Edge content update wiped episodes**
- **Found during:** Task 1
- **Issue:** Phase 1 `build_edge_upsert_cypher` set `e.episodes = $episodes` on update; `prepare_edge_params` always passed `[]`
- **Fix:** Removed episodes assignment from updated SET block; create path still seeds empty list
- **Files modified:** `mcp_server/src/services/catalog_store.py`, unit assertion updated
- **Commit:** `47eed93`

**2. [Rule 2 - Missing critical functionality] Store reads for idempotency**
- **Found during:** Task 2
- **Issue:** Service needed pre-read of Episodic source and MENTIONS link for PROV-06 unchanged path
- **Fix:** Added `get_source_episode_by_uuid` and `get_mentions_link`; edge get returns `episodes`
- **Files modified:** `mcp_server/src/services/catalog_store.py`
- **Commit:** `b8135a7`

## Issues Encountered

None blocking.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Provenance write path unit-green for batch orchestrator (02-03)
- Live Neo4j provenance integration deferred to 02-05
- Status node CRUD still pending (02-04)

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_store.py` provenance builders
- FOUND: `mcp_server/src/services/catalog_service.py` upsert_provenance
- FOUND: `mcp_server/src/graphiti_mcp_server.py` upsert_provenance tool
- FOUND: commit `47eed93`
- FOUND: commit `b8135a7`
- TESTS: 10 passed (`-k provenance` across store + service); full store unit suite 50 passed
- LINT: scoped Ruff + Pyright clean on touched service/store files

---
*Phase: 02-provenance-and-atomic-batch*
*Completed: 2026-07-17*
