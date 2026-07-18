---
phase: 03A-immutable-prepare-commit-control-plane
plan: 01
subsystem: api
tags: [pydantic, catalog-prepare, plan-token, config-clamps, tdd]

# Dependency graph
requires:
  - phase: 01-strict-contracts-and-catalog-v2-identity
    provides: CatalogStrictModel, UpsertCatalogBatchRequest, CatalogConfig, prepared_plan_* error codes
provides:
  - PrepareCatalogBatchRequest without dry_run
  - CommitPreparedCatalogBatchRequest token-only (+ optional expected_request_sha256)
  - DiscardPreparedCatalogBatchRequest token-only
  - Prepare/Commit/Discard response receipts without payload/embeddings
  - HARD_*/DEFAULT_* plan ceilings and PLAN_STATE_* constants
  - CatalogConfig plan_ttl/payload/active/chunk Field clamps
affects:
  - 03A-02-canonical-artifact-and-token
  - 03A-03-prepared-plan-store
  - 03A-04-prepare-service
  - 03A-05-commit-discard-mcp

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Prepare = upsert domain body minus dry_run (duplicate fields, no shared base)"
    - "Commit/discard fail-closed token-only via CatalogStrictModel extra=forbid"
    - "HARD_* ceilings + CatalogConfig Field(ge=1, le=HARD_*) clamps"

key-files:
  created:
    - mcp_server/src/models/catalog_prepare.py
    - mcp_server/tests/test_catalog_prepare_models.py
  modified:
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/src/models/catalog_common.py
    - mcp_server/src/config/schema.py

key-decisions:
  - "Duplicated UpsertCatalogBatchRequest domain field set on Prepare rather than shared base to keep zero behavior change on upsert"
  - "expected_request_sha256 remains optional compare-only guard; never plan identity"
  - "catalog_capabilities HARD_* zeros left untouched (plan 05 owns feature flag flip)"

patterns-established:
  - "Token-only commit/discard: field set exactly plan_token (+ optional expected_request_sha256 on commit)"
  - "Receipt models omit payload/membership/embeddings; raw plan_token only on prepare response"

requirements-completed: [PLAN-01, PLAN-08, PLAN-10]

coverage:
  - id: D1
    description: PrepareCatalogBatchRequest accepts full catalog-v2 domain body and rejects dry_run/extra/empty/null shells
    requirement: PLAN-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_prepare_accepts_full_valid_catalog_v2_batch_domain
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_prepare_rejects_dry_run_field
        status: pass
    human_judgment: false
  - id: D2
    description: CommitPreparedCatalogBatchRequest is plan_token + optional expected_request_sha256 only; forbids replacement payload fields
    requirement: PLAN-10
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_commit_field_set_exactly_token_and_optional_hash
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_commit_rejects_replacement_payload_fields
        status: pass
    human_judgment: false
  - id: D3
    description: DiscardPreparedCatalogBatchRequest is token-only with same forbid set
    requirement: PLAN-10
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_discard_field_set_exactly_token
        status: pass
    human_judgment: false
  - id: D4
    description: HARD_* plan ceilings and CatalogConfig clamps reject hard+1, accept exact hard max
    requirement: PLAN-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_hard_plan_ceiling_constants
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_catalog_config_plan_ttl_defaults_and_clamps
        status: pass
    human_judgment: false
  - id: D5
    description: Prepare/Commit/Discard response receipts omit payload/embeddings/membership
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_prepare_response_receipt_fields_no_payload
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_models.py#test_commit_response_receipt_fields_no_membership
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-07-18
status: complete
---

# Phase 03A Plan 01: Immutable Prepare/Commit Control Plane Models Summary

**Strict prepare/commit/discard Pydantic contracts plus research-locked HARD_* plan ceilings with CatalogConfig clamps**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-18T05:57:12Z
- **Completed:** 2026-07-18T06:09:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `PrepareCatalogBatchRequest` mirrors upsert domain body without `dry_run` (PLAN-01, D-14)
- Token-only `CommitPreparedCatalogBatchRequest` / `DiscardPreparedCatalogBatchRequest` forbid replacement payload fields (PLAN-10, D-20, D-11)
- Receipt models return hashes/counts/state only — no payload, embeddings, or membership
- HARD_*/DEFAULT_* TTL/payload/chunk/active ceilings + PLAN_STATE_* constants; CatalogConfig Field clamps (PLAN-08, D-24)
- 50/50 unit tests green in `test_catalog_prepare_models.py`

## Task Commits

Each task was committed atomically:

1. **Task 1: Strict prepare/commit/discard models + receipts** - `206e8f5` (feat)
2. **Task 2: Plan hard ceilings + CatalogConfig clamps** - `99be240` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD RED→GREEN embedded in each task commit (type: tdd plan)._

## Files Created/Modified

- `mcp_server/src/models/catalog_prepare.py` - Prepare/Commit/Discard request models
- `mcp_server/src/models/catalog_responses.py` - Prepare/Commit/Discard receipt models
- `mcp_server/src/models/catalog_common.py` - HARD_*/DEFAULT_* plan ceilings + PLAN_STATE_*
- `mcp_server/src/config/schema.py` - CatalogConfig plan limit Field clamps
- `mcp_server/tests/test_catalog_prepare_models.py` - PLAN-01/08/10 model suite

## Decisions Made

- Duplicated upsert domain fields on Prepare rather than extracting a shared base — keeps zero behavior change on existing upsert path
- Left `catalog_capabilities.py` HARD_* zeros alone; plan 05 owns capabilities feature flag
- `expected_request_sha256` optional; omission and correct value are later service concerns — model only validates 64-hex shape

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Model/config boundary closed for prepare/commit/discard
- Ready for 03A-02 canonical artifact + token helpers
- Store/service/MCP write paths intentionally not present

## TDD Gate Compliance

1. RED: import/collection failure then ceiling ImportError before implementation
2. GREEN: feat commits `206e8f5` (models) and `99be240` (ceilings/config)
3. REFACTOR: not required — no cleanup pass

## Self-Check: PASSED

- FOUND: mcp_server/src/models/catalog_prepare.py
- FOUND: mcp_server/src/models/catalog_responses.py (prepare/commit/discard receipts)
- FOUND: mcp_server/tests/test_catalog_prepare_models.py
- FOUND: 206e8f5, 99be240 in git log
- HARD_MAX_PREPARED_PAYLOAD_BYTES == 16777216 verified by unit test

---
*Phase: 03A-immutable-prepare-commit-control-plane*
*Completed: 2026-07-18*
