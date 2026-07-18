---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 05
subsystem: catalog-recovery
tags: [neo4j, recovery, concurrency, cas, terminal-agreement, tdd, prepared-commit]

requires:
  - phase: 03B-04
    provides: shared atomic writer, terminal_commit_agrees short-circuit hook, COMMITTED success path
provides:
  - Recovery decision matrix on commit re-entry (agree / resume / fail-closed)
  - Stable terminal receipts for COMMITTED + agreeing batch/manifest
  - GREEN recovery + concurrency suites under FakeStore CAS/uniqueness
affects:
  - Phase 3B live Neo4j gate
  - Phase 4 verify against committed batch + manifest

tech-stack:
  added: []
  patterns:
    - read_terminal_commit_snapshot then terminal_commit_agrees then partial-terminal fail-closed
    - COMMITTED root stable receipt without domain rewrite
    - concurrency authority via Neo4j locks/CAS/uniqueness stand-ins (not process-local locks)

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/services/catalog_store.py
    - mcp_server/tests/test_catalog_commit_recovery.py
    - mcp_server/tests/test_catalog_concurrency.py
    - mcp_server/tests/test_catalog_atomic_writer.py
    - mcp_server/tests/test_catalog_prepare_service.py

key-decisions:
  - "Partial terminals map to existing codes only: batch_conflict, manifest_mismatch, prepared_plan_conflict"
  - "Different-token same-batch arbitration reuses batch_conflict/prepared_plan_conflict/prepared_plan_already_consumed — no new error codes"
  - "COMMITTED plan roots attempt durable agreement receipt before prepared_plan_already_consumed fallback"
  - "No process-local lock authority in product code; tests use asyncio.Lock only as Neo4j serialization stand-in"

patterns-established:
  - "Pattern: after plan lock + batch claim, snapshot terminals → agree short-circuit OR partial fail-closed OR full idempotent writer"
  - "Pattern: recovery never CAS to PREPARED; COMMITTING ignores TTL for resume"

requirements-completed: [PLAN-14, PLAN-15, PLAN-16, MANI-07, TEST-06]

coverage:
  - id: D1
    description: Terminal agreement returns stable receipt with zero further domain/manifest writes
    requirement: PLAN-15
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_commit_recovery.py::test_terminal_agreement_returns_stable_receipt
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_commit_recovery.py::test_terminal_receipt_idempotent_across_calls
        status: pass
    human_judgment: false
  - id: D2
    description: Partial or contradictory terminal evidence fails closed; plan remains COMMITTING; no PREPARED revival
    requirement: PLAN-14
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_commit_recovery.py::test_partial_terminal_fails_closed
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_commit_recovery.py::test_never_prepared_revival
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_commit_recovery.py::test_no_committing_to_prepared_in_cas_legal
        status: pass
    human_judgment: false
  - id: D3
    description: Stranded COMMITTING without success artifacts resumes full idempotent writer
    requirement: PLAN-14
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_commit_recovery.py::test_committing_resume_full_write
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_commit_recovery.py::test_permanent_conflict_leaves_committing
        status: pass
    human_judgment: false
  - id: D4
    description: Concurrent same-token commits yield one logical committed batch/manifest/entity set
    requirement: PLAN-16
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_concurrency.py::test_same_token_concurrent_one_logical_commit
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_concurrency.py::test_no_duplicate_manifest_under_race
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_concurrency.py::test_no_duplicate_domain_under_race
        status: pass
    human_judgment: false
  - id: D5
    description: Different tokens same batch converge on one manifest or deterministic conflict codes
    requirement: TEST-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_concurrency.py::test_same_batch_different_tokens_converge_or_deterministic_conflict
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-18
status: complete
---

# Phase 03B Plan 05: Recovery Matrix and Concurrency Arbitration Summary

**Stranded COMMITTING resumes or returns stable terminal receipts; races serialize to one logical commit without PREPARED revival or process-local locks.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-18T11:41:19Z
- **Completed:** 2026-07-18T11:50:00Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Implemented RESEARCH §C recovery matrix inside `_write_catalog_batch_atomic` after plan lock + batch claim: terminal agreement short-circuit, partial-terminal fail-closed, else full idempotent writer.
- COMMITTED plan roots now attempt durable agreement receipt (`_commit_terminal_state_receipt`) before already-consumed fallback; identical replays return equal bounded receipts.
- Permanent domain conflicts leave plan `COMMITTING`; `_PLAN_CAS_LEGAL` still forbids `COMMITTING→PREPARED`.
- GREEN recovery suite (7) + concurrency suite (4); regressions in atomic writer / prepare service green.
- Different-token same-batch arbitration documents reuse of `batch_conflict` / `prepared_plan_conflict` / `prepared_plan_already_consumed` (no new codes).

## Task Commits

1. **Task 1: Stranded COMMITTING recovery + stable replay** - `8094e5c` (feat)
2. **Task 2: Same-token and same-batch concurrency** - `fd33827` (test)

## Files Created/Modified

- `mcp_server/src/services/catalog_service.py` — recovery matrix, partial-terminal exception, COMMITTED stable receipt path, `_PartialTerminalConflict`
- `mcp_server/src/services/catalog_store.py` — `read_terminal_commit_snapshot` group-scoped recovery read
- `mcp_server/tests/test_catalog_commit_recovery.py` — GREEN recovery matrix
- `mcp_server/tests/test_catalog_concurrency.py` — GREEN concurrency arbitration
- `mcp_server/tests/test_catalog_atomic_writer.py` — snapshot double for shared writer
- `mcp_server/tests/test_catalog_prepare_service.py` — snapshot stub on commit wire

## Decisions Made

- Prefer existing error registry over new codes for partial terminals and multi-token races.
- Product authority remains Neo4j lock/CAS/uniqueness; test asyncio locks are serialization stand-ins only.
- Internal recovery reads stay non-public (no Phase 4 MCP tools).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] COMMITTED root stable receipt**
- **Found during:** Task 1
- **Issue:** Pre-plan path returned `prepared_plan_already_consumed` for all COMMITTED roots, blocking stable terminal replay receipts required by PLAN-15/D-09/D-23.
- **Fix:** Added `_commit_terminal_state_receipt` to lock + snapshot + agree and return durable receipt without rewrite.
- **Files modified:** `mcp_server/src/services/catalog_service.py`
- **Commit:** `8094e5c`

**2. [Rule 2 - Missing critical functionality] Partial terminal classification**
- **Found during:** Task 1
- **Issue:** `terminal_commit_agrees` false alone could fall into full rewrite on partial terminals (batch committed / manifest present without plan COMMITTED).
- **Fix:** `_raise_if_partial_terminal` fail-closed before domain writes; maps to existing codes.
- **Files modified:** `mcp_server/src/services/catalog_service.py`, `catalog_store.py`
- **Commit:** `8094e5c`

## Flagged assumptions (discharged)

- Different-token conflict codes: **reused** `batch_conflict`, `prepared_plan_conflict`, `prepared_plan_already_consumed` — no new registry members.

## Verification

```text
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_commit_recovery.py \
  mcp_server/tests/test_catalog_concurrency.py \
  mcp_server/tests/test_catalog_atomic_writer.py \
  mcp_server/tests/test_catalog_prepare_service.py -q
# 53 passed

ruff check (changed files): clean
project-config pyright (catalog_service.py, catalog_store.py): 0 errors
IDE-root import diagnostics on config/models/services: baseline vs e55f9d4 (no new import lines)
```

## Threat Flags

None — recovery reads remain group-scoped internal store methods; no new public endpoints, packages, or auth surfaces.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: product + test files for plan 05
- FOUND: commits `8094e5c`, `fd33827`
- No COMMITTING→PREPARED in `_PLAN_CAS_LEGAL`
- No process-local lock authority in `catalog_service.py`
