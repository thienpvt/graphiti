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
  - "CR-01: same-token stale PREPARED expected against live COMMITTING is deterministic re-entry, not prepared_plan_conflict"
  - "CR-02: expected manifest_sha256 always from frozen membership reassembly, never durable snapshot (non-tautological)"
  - "WR-01: claim-time prepared_plan_already_consumed routes to stable terminal receipt"
  - "WR-02: COMMITTING→COMMITTED CAS persists actual outcome counts; first response and replay both read durable authority"

patterns-established:
  - "Pattern: after plan lock + batch claim, snapshot terminals → agree short-circuit OR partial fail-closed OR full idempotent writer"
  - "Pattern: recovery never CAS to PREPARED; COMMITTING ignores TTL for resume"
  - "Pattern: terminal receipt expected digest = pure_manifest_sha256(serialize(build_manifest_body_from_membership(...)))"

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
- GREEN recovery suite (10) + concurrency suite (4); prepare-store CAS + atomic/prepare regressions green (90 total).
- Different-token same-batch arbitration documents reuse of `batch_conflict` / `prepared_plan_conflict` / `prepared_plan_already_consumed` (no new codes).
- Adversarial review gaps closed: CR-01 stale PREPARED→live COMMITTING re-entry; CR-02 frozen expected manifest; WR-01 claim already_consumed→receipt; WR-02 durable outcome counts first==replay.

## Task Commits

1. **Task 1: Stranded COMMITTING recovery + stable replay** - `8094e5c` (feat)
2. **Task 2: Same-token and same-batch concurrency** - `fd33827` (test)
3. **Adversarial fix: CR-01/02 WR-01/02** - `e9c96b5` (fix)

## Files Created/Modified

- `mcp_server/src/services/catalog_service.py` — recovery matrix, partial-terminal, frozen expected manifest, claim→receipt, durable outcome counts
- `mcp_server/src/services/catalog_store.py` — terminal snapshot, stale PREPARED re-entry, outcome-count CAS, plan count fields on snapshot
- `mcp_server/tests/test_catalog_commit_recovery.py` — recovery matrix + CR/WR real-store-semantics tests
- `mcp_server/tests/test_catalog_concurrency.py` — concurrency arbitration
- `mcp_server/tests/test_catalog_prepare_store.py` — CR-01/WR-02 CAS unit proofs
- `mcp_server/tests/test_catalog_atomic_writer.py` — snapshot double for shared writer
- `mcp_server/tests/test_catalog_prepare_service.py` — snapshot stub on commit wire

## Decisions Made

- Prefer existing error registry over new codes for partial terminals and multi-token races.
- Product authority remains Neo4j lock/CAS/uniqueness; test asyncio locks are serialization stand-ins only.
- Internal recovery reads stay non-public (no Phase 4 MCP tools).
- Expected manifest digest authority is frozen membership reassembly (CR-02), never snapshot echo.
- Durable plan `created_count`/`updated_count`/`unchanged_count` written only on COMMITTING→COMMITTED (WR-02).

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

**3. [Rule 1 - Bug] CR-01 stale PREPARED vs live COMMITTING**
- **Found during:** Adversarial review
- **Issue:** `cas_plan_state` only re-entered when `expected_from==COMMITTING`; stale PREPARED expected raised `prepared_plan_conflict`.
- **Fix:** Same-token re-entry when live is COMMITTING and expected is PREPARED or COMMITTING.
- **Files modified:** `catalog_store.py`, `test_catalog_prepare_store.py`
- **Commit:** `e9c96b5`

**4. [Rule 1 - Bug] CR-02 tautological expected manifest**
- **Found during:** Adversarial review
- **Issue:** Receipt used snapshot `manifest_sha256` as expected, so agreement always passed when snapshot present.
- **Fix:** `_expected_manifest_sha_from_frozen` reassembles membership and derives digest; compare durable snapshot to that.
- **Files modified:** `catalog_service.py`, recovery tests
- **Commit:** `e9c96b5`

**5. [Rule 2 - Missing critical functionality] WR-01 claim already_consumed**
- **Found during:** Adversarial review
- **Issue:** Winner COMMITTED before follower claim returned error instead of stable receipt.
- **Fix:** Claim path routes `prepared_plan_already_consumed` to `_commit_terminal_state_receipt`.
- **Files modified:** `catalog_service.py`, recovery tests
- **Commit:** `e9c96b5`

**6. [Rule 2 - Missing critical functionality] WR-02 durable outcome counts**
- **Found during:** Adversarial review
- **Issue:** First response used live write statuses; replay used prepare-projected plan counts — could diverge.
- **Fix:** Persist actual counts on terminal CAS; short-circuit and receipt read durable plan counts.
- **Files modified:** `catalog_service.py`, `catalog_store.py`, recovery/store tests
- **Commit:** `e9c96b5`

## Flagged assumptions (discharged)

- Different-token conflict codes: **reused** `batch_conflict`, `prepared_plan_conflict`, `prepared_plan_already_consumed` — no new registry members.

## Verification

```text
uv run --project mcp_server pytest \
  mcp_server/tests/test_catalog_commit_recovery.py \
  mcp_server/tests/test_catalog_concurrency.py \
  mcp_server/tests/test_catalog_prepare_store.py \
  mcp_server/tests/test_catalog_atomic_writer.py \
  mcp_server/tests/test_catalog_prepare_service.py -q
# 90 passed

ruff check (changed files): clean
ruff format --check: clean
project-config pyright (catalog_service.py, catalog_store.py): 0 errors
```

## Threat Flags

None — recovery reads remain group-scoped internal store methods; no new public endpoints, packages, or auth surfaces.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: product + test files for plan 05
- FOUND: commits `8094e5c`, `fd33827`, `e9c96b5`
- No COMMITTING→PREPARED in `_PLAN_CAS_LEGAL`
- No process-local lock authority in `catalog_service.py`
- CR-01/02 WR-01/02 covered by real-store-semantics unit tests
