---
phase: 01-strict-contracts-and-catalog-v2-identity
plan: 10
subsystem: catalog-store
tags: [neo4j, merge-lock, deterministic-uuid, catalog-v2, tdd, fixtures]

requires:
  - phase: 01-strict-contracts-and-catalog-v2-identity
    provides: Plan 01-09 CR-02/WR-01 green with readiness false
provides:
  - Lock-authoritative entity conflict arbitration under Neo4j MERGE
  - Exact deterministic_uuid_conflict routing for atomic/per-item/combined entity writes
  - Pure offline catalog-v2 FE Neo4j fixture constructors and construction proof
  - Skipped live concurrent conflicting-name integration definition
affects:
  - 01-11
  - Phase 1 readiness reconsideration

tech-stack:
  added: []
  patterns:
    - source-CAS lock retention applied to entity MERGE (SET n.uuid = n.uuid before CASE)
    - row error_code consumed before status fallback; status=error never reprojected as success
    - pure fixture module with tripwired offline construction tests

key-files:
  created:
    - mcp_server/tests/catalog_neo4j_fixtures.py
    - mcp_server/tests/test_catalog_neo4j_fixtures.py
  modified:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/tests/test_catalog_store_unit.py
    - mcp_server/tests/test_catalog_service.py
    - mcp_server/tests/test_catalog_neo4j_int.py
    - mcp_server/tests/fixtures/accept_tab_sanitized.json

key-decisions:
  - "Entity MERGE self-lock + under-lock immutable/type CASE is mutation authority; pre-read/_recheck remain advisory"
  - "Combined batch catches _EntityInvariantRace separately and returns typed conflict after domain rollback + failed status"
  - "Integration fixtures migrate to pure constructors; live race defined but never collected/run in this plan"

patterns-established:
  - "Order-independent type contract: Entity present, expected custom label present, exactly one non-Entity custom label, n.labels set equals {Entity, expected}"
  - "Offline fixture construction tripwires use scoped pytest fixture, not module-global socket monkeypatch"

requirements-completed: [CONT-01, CONT-04, CONT-07, IDEN-01, IDEN-02, IDEN-04, IDEN-05, IDEN-07, IDEN-10, IDEN-12, SAFE-05, SAFE-08, TEST-01, TEST-03]

coverage:
  - id: D1
    description: Lock-authoritative entity MERGE Cypher with conflict gating before mutable/vector branches
    requirement: IDEN-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py::test_gap_cr01_entity_upsert_cypher_lock_order_and_conflict_gating
        status: pass
    human_judgment: false
  - id: D2
    description: Barrier-driven fake race proves one winner and typed loser conflict on atomic path
    requirement: CONT-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_gap_cr01_atomic_route_race_rolls_back_typed_conflict
        status: pass
    human_judgment: false
  - id: D3
    description: Per-item and combined routes expose exact deterministic_uuid_conflict without neo4j_transaction_failed collapse
    requirement: SAFE-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_gap_cr01_per_item_route_returns_exact_conflict_not_tx_failed
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_gap_cr01_combined_batch_rolls_back_and_returns_typed_conflict
        status: pass
    human_judgment: false
  - id: D4
    description: Catalog-v2 FE fixtures construct fully offline with no network/driver activation
    requirement: TEST-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_neo4j_fixtures.py::test_gap_wr02_constructs_all_fixture_variants_offline
        status: pass
    human_judgment: false
  - id: D5
    description: Live concurrent conflicting-name integration test defined and remains unexecuted
    requirement: TEST-03
    verification:
      - kind: other
        ref: mcp_server/tests/test_catalog_neo4j_int.py::test_concurrent_conflicting_entity_names_only_winner_persists (integration-marked; not collected in plan verify)
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-07-18
status: complete
---

# Phase 01 Plan 10: Locked Entity Conflicts and Catalog-v2 Fixture Migration Summary

**Lock-authoritative entity MERGE returns deterministic_uuid_conflict before mutation; pure FE catalog-v2 fixtures construct offline.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-07-18T00:50:01Z
- **Completed:** 2026-07-18T01:03:34Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Entity upsert Cypher retains the `(uuid, group_id)` lock, arbitrates immutable names and exact type/label set under lock, and gates mutable FOREACH + vector update on non-error status.
- Atomic standalone, per-item standalone, and combined batch consume row `error_code` before status fallback; conflict never collapses to `neo4j_transaction_failed` when typed.
- WR-02 pure fixture module + offline construction suite; `accept_tab_sanitized.json` and integration helpers migrated to FE-scoped catalog-v2 keys; live race definition present but unexecuted.

## Task Commits

Integrated worktree HEAD ancestry (primary base `401d814`):

1. **Task 1: Add failing locked-race, service-routing, and fixture-construction tests** - `fd4c65f` (test RED)
2. **Task 2: Make the locking MERGE authoritative and route conflict results** - `3f3d173` (feat GREEN)
3. **Plan metadata** - `401d814` (docs: complete plan)

_Note: TDD RED preserved as distinct ancestry commit before GREEN. Pre-integration hashes `0bfe925`/`49c58a8`/`4c702cc` are historical only._

## Files Created/Modified

- `mcp_server/src/services/catalog_store.py` - lock-authoritative `build_entity_upsert_cypher`
- `mcp_server/src/services/catalog_service.py` - `_row_error_code` / `_raise_entity_row_error` + three-path routing
- `mcp_server/tests/test_catalog_store_unit.py` - gap_cr01 static Cypher order/gating tests
- `mcp_server/tests/test_catalog_service.py` - barrier race + route conflict tests
- `mcp_server/tests/catalog_neo4j_fixtures.py` - pure request/fixture constructors
- `mcp_server/tests/test_catalog_neo4j_fixtures.py` - offline construction tripwires
- `mcp_server/tests/test_catalog_neo4j_int.py` - import pure fixtures; live race definition
- `mcp_server/tests/fixtures/accept_tab_sanitized.json` - FE catalog-v2 acceptance payload

## Decisions Made

- Applied existing source-episode CAS pattern to entities rather than a second storage abstraction.
- Combined batch handles `_EntityInvariantRace` before generic Exception so domain conflict survives rollback and failed-status orchestration.
- Offline tripwires scoped via pytest fixture so they cannot poison sibling unit modules.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Combined batch lacked typed entity race catch**
- **Found during:** Task 2 GREEN
- **Issue:** `_EntityInvariantRace` from under-lock entity conflict fell through to generic `neo4j_transaction_failed`
- **Fix:** Explicit `except self._EntityInvariantRace` before generic handler; record failed status with typed code
- **Files modified:** `mcp_server/src/services/catalog_service.py`
- **Commit:** `49c58a8`

**2. [Rule 1 - Bug] Global socket monkeypatch broke sibling service tests under shared collection**
- **Found during:** Task 1 RED
- **Issue:** Module-level `socket.socket` replacement caused ERROR setup in gap_cr01 service tests
- **Fix:** Scoped `offline_env` pytest fixture with monkeypatch
- **Files modified:** `mcp_server/tests/test_catalog_neo4j_fixtures.py`
- **Commit:** `0bfe925`

**3. [Rule 3 - Blocking] Constraint/Index graph keys used 4-segment bodies invalid for catalog-v2 grammar**
- **Found during:** Task 1 RED construction
- **Issue:** `CONSTRAINT::FE::ORCL.HR.EMPLOYEES.PK_EMP` failed fullmatch (Constraint body is DB.SCHEMA.NAME)
- **Fix:** Use `CONSTRAINT::FE::ORCL.HR.PK_EMP` / `INDEX::FE::ORCL.HR.IX_EMP_NAME`
- **Files modified:** `mcp_server/tests/catalog_neo4j_fixtures.py`, `mcp_server/tests/test_catalog_neo4j_int.py`
- **Commit:** `0bfe925`

## Command Outcomes

| Command | Result |
|---------|--------|
| Collect `gap_cr01 or gap_wr02` | exit 0, 10 selected; int module not collected |
| RED wrapper (inner pytest) | inner exit 1 (assertion failures only) |
| Focused GREEN gap suite | 10 passed |
| Full local regression | 537 passed |
| Ruff (listed files) | exit 0 |
| MCP-scoped Pyright | 0 errors, 0 warnings |

### Query ordering evidence (CR-01)

1. `MERGE (n:Entity {uuid, group_id})`
2. `SET n.uuid = n.uuid` lock retention
3. immutable/type CASE → `error_code='deterministic_uuid_conflict'`
4. `WHEN error_code IS NOT NULL THEN 'error'`
5. `FOREACH` only for `status = 'updated'`
6. vector call only for `status IN ['created','updated']`
7. RETURN includes `error_code` + identity/hash/vector-presence fields

### Three-path service evidence

- Atomic: raises `_EntityInvariantRace` on row conflict → full sibling rollback
- Per-item: maps row `error_code` to exact item/coalesced conflict (not tx failed)
- Combined: typed race after domain tx open → rollback + separate failed status

## TDD Gate Compliance

- RED commit: `fd4c65f` `test(01-10): add failing entity race and fixture coverage`
- GREEN commit: `3f3d173` `feat(01-10): enforce locked entity conflicts and migrate fixtures`
- RED ancestry preserved (not amended)

## JSON argv outcomes (Plan 01-11 refresh)

| Check | argv summary | Exit |
|-------|--------------|-----:|
| focused CR-01/WR-02 | `pytest ... -k "gap_cr01 or gap_wr02"` (no int module) | 0 (10 passed) |
| pure fixtures | `pytest ... test_catalog_neo4j_fixtures.py` | 0 |
| full local regression | unit matrix | 0 (537 passed) |
| ruff / MCP pyright | scoped product+test files | 0 |

## Known Stubs

None.

## Threat Flags

None beyond plan threat model mitigations.

## Issues Encountered

None remaining. Integration module intentionally unexecuted.

## Safety Compliance

- No canary/live Neo4j probe/`oracle-catalog-v2` mutation
- Tests only group `oracle-catalog-tool-test`
- No deploy/push/merge/tag/dependency/lockfile/catalog-dump edits
- Readiness remains false; Phase 2 not started

## Next Phase Readiness

- Plan 01-11 may reconsider local readiness after mandatory checks
- CR-01 and WR-02 closed for unit/static/fake-race/offline construction layers
- Live concurrent race remains deferred integration execution

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_store.py`
- FOUND: `mcp_server/src/services/catalog_service.py`
- FOUND: `mcp_server/tests/catalog_neo4j_fixtures.py`
- FOUND: `mcp_server/tests/test_catalog_neo4j_fixtures.py`
- FOUND: `fd4c65f`
- FOUND: `3f3d173`
- FOUND: `401d814`

