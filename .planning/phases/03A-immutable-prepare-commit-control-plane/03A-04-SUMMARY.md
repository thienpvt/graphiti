---
phase: 03A-immutable-prepare-commit-control-plane
plan: 04
subsystem: catalog-control-plane
tags: [prepare-service, shared-preflight, embed-before-tx, plan-token, tdd]

requires:
  - phase: 03A-01
    provides: plan config clamps, PLAN_STATE_*, CatalogErrorCode prepare codes
  - phase: 03A-02
    provides: prepared-artifact-v1 serialize/chunk/sha256, mint_plan_token/plan_token_digest, plan UUID helpers
  - phase: 03A-03
    provides: ensure_plan_schema, create_prepared_plan_with_chunks CREATE-once + capacity CAS
provides:
  - _BatchPreflightOutcome + _prepare_batch_preflight shared by prepare and upsert
  - prepare_catalog_batch control-plane path (preflight → embed-all → plan/chunks only)
  - one-time raw plan_token receipt after committed plan root; digest-only store
  - zero Entity/RELATES_TO/Episodic/evidence/manifest/CatalogIngestBatch mutation on prepare
affects:
  - 03A-05-commit-discard-mcp
  - 03A-06-wire-tools

tech-stack:
  added: []
  patterns:
    - single preflight authority for prepare + upsert (no second hash/topology fork)
    - all embeddings complete before any plan write transaction
    - full membership+embeddings artifact (never hashes-only)
    - raw plan_token once in receipt; never logged; never persisted

key-files:
  created:
    - mcp_server/tests/test_catalog_prepare_service.py
  modified:
    - mcp_server/src/services/catalog_service.py

key-decisions:
  - "Extract shared _prepare_batch_preflight; upsert thinned to call it then dry_run/embed/domain tail"
  - "Prepare skips CatalogIngestBatch status short-circuit (check_batch_status=False)"
  - "plan_id = batch_id|request_sha256 → catalog_prepared_plan_uuid; same identity → prepared_plan_conflict empty token"
  - "Embed only non-unchanged members; payload ceiling enforced before open plan tx"
  - "Store errors map: prepared_plan_conflict, batch_limit_exceeded, embedding_failed"

patterns-established:
  - "Characterization-first extract: dry_run/upsert suite green before and after preflight share"
  - "call_order embed < transaction spy for SAFE-11 embed-before-write"
  - "Domain write spies assert_not_awaited on every prepare path"

requirements-completed: [PLAN-02, PLAN-03, PLAN-04, PLAN-06, PLAN-12, PLAN-20, SAFE-11]

coverage:
  - id: D1
    description: Shared preflight used by prepare and upsert; one identity/hash/projection authority
    requirement: PLAN-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_shared_preflight_used_by_prepare_and_upsert
        status: pass
    human_judgment: false
  - id: D2
    description: Prepare happy path full artifact + receipt; embed before tx; zero domain writes
    requirement: PLAN-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_happy_path_receipt_and_full_artifact
        status: pass
    human_judgment: false
  - id: D3
    description: Embedding failure leaves zero plan schema/create/tx and zero domain
    requirement: SAFE-11
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_embedding_failure_zero_plan_and_domain_writes
        status: pass
    human_judgment: false
  - id: D4
    description: Preflight hash mismatch before embed or plan write
    requirement: PLAN-20
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_preflight_failure_before_embed_or_plan_write
        status: pass
    human_judgment: false
  - id: D5
    description: Same plan identity conflicts; never reissue token
    requirement: PLAN-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_same_identity_conflict_no_second_token
        status: pass
    human_judgment: false
  - id: D6
    description: Capacity and payload ceiling map to batch_limit_exceeded without plan write
    requirement: PLAN-12
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_capacity_exceeded_maps_batch_limit
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_payload_over_max_before_write
        status: pass
    human_judgment: false
  - id: D7
    description: Mixed projection counts; only non-unchanged embeds; order-invariant plan_uuid
    requirement: PLAN-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_mixed_projection_counts
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_order_invariant_request_hash
        status: pass
    human_judgment: false
  - id: D8
    description: Logs omit raw plan_token; receipt returns token once
    requirement: PLAN-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#test_prepare_logs_omit_raw_token
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-07-18
status: complete
---

# Phase 03A Plan 04: Prepare Service Summary

**Shared preflight + prepare_catalog_batch freezes full membership/embeddings into control-plane plan/chunks with one-time token; zero domain mutation.**

## Performance

- **Duration:** ~10 min (post-compaction finish; implementation already green)
- **Started:** 2026-07-18T06:16:06Z
- **Completed:** 2026-07-18T06:26:00Z
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Characterized upsert/dry_run then extracted `_prepare_batch_preflight` as single preflight authority
- Implemented `prepare_catalog_batch`: validate/hash/project → embed non-unchanged → ensure_plan_schema → create plan+chunks only
- Receipt returns raw `plan_token` once; store holds `token_digest` only; logs never include raw token
- 10/10 prepare service tests + 44 focused prepare/upsert regressions green; ruff/pyright clean

## Task Commits

1. **Task 1+2: shared preflight + prepare control-plane path** - `18676da` (feat)
2. **Task 2 tests: prepare service suite** - `f06301a` (test)

**Plan metadata:** (docs commit follows)

_Note: TDD characterization ran against live upsert suite before extract; prepare tests landed with implementation green (RED not re-committed post-compaction)._

## Files Created/Modified

- `mcp_server/src/services/catalog_service.py` - `_BatchPreflightOutcome`, `_prepare_batch_preflight`, `prepare_catalog_batch`; upsert uses shared preflight
- `mcp_server/tests/test_catalog_prepare_service.py` - 10 service spies for embed-before-write, zero domain, conflict/capacity/payload, token hygiene

## Decisions Made

- One preflight helper for prepare and upsert (PLAN-02 / no second authority)
- Prepare does not consult CatalogIngestBatch status (`check_batch_status=False`)
- Full artifact with embeddings (not hashes-only); ceiling checked before plan tx
- Existing plan_uuid → `prepared_plan_conflict` with empty token (no re-mint)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pyright batch_uuid Optional into prepare_batch_status_params**
- **Found during:** Task 2 typecheck
- **Issue:** `batch_uuid: str | None` after early exits still Optional for pyright
- **Fix:** `assert batch_uuid is not None` on write path after early returns
- **Files modified:** `mcp_server/src/services/catalog_service.py`
- **Commit:** `18676da`

**2. [Rule 1 - Bug] AsyncMock / await_args typing in tests**
- **Found during:** Task 2 pyright
- **Issue:** bare AsyncMock attribute access and optional `await_args.kwargs`
- **Fix:** `cast(AsyncMock, ...)` + `assert await_args is not None`
- **Files modified:** `mcp_server/tests/test_catalog_prepare_service.py`
- **Commit:** `f06301a`

## TDD Gate Compliance

- Characterization baseline (upsert dry_run / request_sha256) green before extract and after
- Prepare suite authored against implementation; separate RED commit not retained after worktree apply scripts
- GREEN commits present: `18676da` (feat), `f06301a` (test)

## Known Stubs

None.

## Threat Flags

None new beyond plan threat model (control-plane writes only; token not logged).

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_service.py` (`prepare_catalog_batch`, `_prepare_batch_preflight`)
- FOUND: `mcp_server/tests/test_catalog_prepare_service.py`
- FOUND: commit `18676da`
- FOUND: commit `f06301a`
- VERIFIED: no `_tmp_*` artifacts in worktree
- VERIFIED: 10 prepare + 44 focused regressions pass; ruff all checks; pyright 0 errors
