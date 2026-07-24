---
phase: 03A-immutable-prepare-commit-control-plane
plan: 03
subsystem: catalog-control-plane
tags: [prepared-plan-store, cas, capacity-lock, fixed-cypher, tdd]

requires:
  - phase: 03A-01
    provides: PLAN_STATE_* constants, HARD_* plan ceilings, CatalogErrorCode prepared_plan_* codes
  - phase: 03A-02
    provides: chunk payload_b64 shape, token_digest identity (store never accepts raw tokens)
provides:
  - ensure_plan_schema CREATE CONSTRAINT IF NOT EXISTS for plan/chunk/token_digest uniqueness
  - create_prepared_plan_with_chunks CREATE-once under CatalogPlanGroupLock + active capacity
  - load_prepared_plan_by_token_digest / load_prepared_plan_chunks ordered
  - cas_plan_state legal transition matrix with structured CatalogStoreError codes
  - count_active_plans_for_group PREPARED|COMMITTING policy
affects:
  - 03A-04-prepare-service
  - 03A-05-commit-discard-mcp

tech-stack:
  added: []
  patterns:
    - fixed-label control-plane Cypher only (CatalogPreparedPlan/Chunk/PlanGroupLock)
    - CREATE-once immutability; no MERGE-update of artifact bytes
    - same-tx group lock + active count before create
    - CAS table; terminal never revive; no COMMITTING→PREPARED

key-files:
  created:
    - mcp_server/tests/test_catalog_prepare_store.py
  modified:
    - mcp_server/src/services/catalog_store.py

key-decisions:
  - "Existing plan identity always prepared_plan_conflict (no token re-issue)"
  - "Capacity exceed maps to batch_limit_exceeded"
  - "Discard already DISCARDED is idempotent success; COMMITTING/COMMITTED conflict"
  - "COMMITTING re-entry returns reentry flag without SET when already COMMITTING"
  - "require_not_expired claim auto-marks PREPARED→EXPIRED then prepared_plan_expired"

patterns-established:
  - "token_digest param only; raw token keys rejected at prepare_prepared_plan_params"
  - "Legal CAS via _PLAN_CAS_LEGAL; illegal transitions fail closed before Cypher SET"
  - "Active = PREPARED unexpired OR COMMITTING"

requirements-completed: [PLAN-05, PLAN-09, PLAN-11, PLAN-18, PLAN-19]

coverage:
  - id: D1
    description: Fixed labels CatalogPreparedPlan/Chunk/PlanGroupLock only; no Entity/embeddings on plan writes
    requirement: PLAN-09
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_plan_write_queries_label_allowlist_only
        status: pass
    human_judgment: false
  - id: D2
    description: CREATE-once root+chunks; capacity gate; same identity conflict
    requirement: PLAN-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_create_prepared_plan_with_chunks_create_once_and_params
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_create_capacity_rejection_when_active_at_max
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_create_same_identity_different_digest_conflicts
        status: pass
    human_judgment: false
  - id: D3
    description: Load by token_digest + ordered chunks
    requirement: PLAN-11
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_load_prepared_plan_by_token_digest_returns_root
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_load_prepared_plan_chunks_ordered_by_index
        status: pass
    human_judgment: false
  - id: D4
    description: Legal/illegal CAS matrix; no COMMITTING→PREPARED; terminal never revive
    requirement: PLAN-18
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_cas_table_driven_legal_and_illegal_matrix
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_cas_cypher_no_committing_to_prepared_path
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_cas_illegal_terminal_revival
        status: pass
    human_judgment: false
  - id: D5
    description: Discard idempotent/conflicts; expiry CAS; missing/consumed/expired codes
    requirement: PLAN-19
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_discard_idempotent_already_discarded
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_discard_conflict_when_committing_or_committed
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_cas_expiry_only_from_prepared_when_due
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_store.py#test_cas_missing_plan_not_found
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-18
status: complete
---

# Phase 03A Plan 03: Prepared Plan Immutable Store Summary

**Fixed-label prepared-plan store with CREATE-once capacity lock, token_digest load, and legal CAS state machine (no domain Neo4j writes)**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-18T06:05:05Z
- **Completed:** 2026-07-18
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Additive `CatalogNeo4jStore` methods for plan schema, create+chunks, load, capacity count, and CAS
- Unit suite (28 tests) proves fixed labels, CREATE-once, capacity rejection, identity conflict, full CAS matrix
- No live Neo4j, no new dependencies, no domain Entity/RELATES_TO/evidence writes

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1+2 impl | immutable prepared-plan store | 92c3bdb | `mcp_server/src/services/catalog_store.py` |
| 1+2 tests | store unit matrix | fdc0a8d | `mcp_server/tests/test_catalog_prepare_store.py` |

Note: TDD RED tests and GREEN implementation landed as two atomic commits (test file after implementation commit order on disk; both green at suite run).

## Files Created/Modified

- `mcp_server/src/services/catalog_store.py` — plan schema constraints; create/load/capacity/CAS methods; `_PLAN_CAS_LEGAL`
- `mcp_server/tests/test_catalog_prepare_store.py` — mocked-tx unit matrix

## Decisions Made

- Existing plan uuid always conflicts (one-time token; no re-prepare re-issue)
- Capacity full → `batch_limit_exceeded`; identity clash → `prepared_plan_conflict`
- Discard DISCARDED is idempotent; claim expired PREPARED auto-marks EXPIRED when `require_not_expired`

## Deviations from Plan

None - plan executed exactly as written.

## Threat Flags

None new beyond plan threat model mitigations (fixed labels, CREATE-once, group lock capacity, CAS table, token_digest only).

## Known Stubs

None.

## TDD Gate Compliance

- RED: task1 tests failed on missing attributes before implementation
- GREEN: full suite 28 passed after implementation
- REFACTOR: not required

## Verification

```text
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_prepare_store.py -q --tb=line
# 28 passed

uv run --project mcp_server ruff check \
  mcp_server/src/services/catalog_store.py \
  mcp_server/tests/test_catalog_prepare_store.py
# All checks passed

uv run --project mcp_server pyright \
  mcp_server/src/services/catalog_store.py \
  mcp_server/tests/test_catalog_prepare_store.py
# 0 errors
```

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_store.py` methods
- FOUND: `mcp_server/tests/test_catalog_prepare_store.py`
- FOUND: commits `92c3bdb`, `fdc0a8d`
