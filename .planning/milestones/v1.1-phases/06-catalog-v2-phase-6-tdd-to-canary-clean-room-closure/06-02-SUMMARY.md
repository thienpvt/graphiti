---
phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
plan: 02
subsystem: canary-terminal-contracts
tags: [tdd, terminal-evidence, auth-sentinel, replay, launcher]
requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: Plan 06-01 exact raw-Git archive authority
provides:
  - Post-ID terminal allowlist with durable FAILED_BEFORE_COMMIT evidence
  - Sanitized embedding_transport_auth classification without CatalogErrorCode expansion
  - Exactly-one prepare/commit replay gate and validated domain counts
  - Source-bound final-canary launcher with exclusive allocation claim and exact invocation binding
  - Sanitized uncommitted phase ledger/final-report mapping
  - No runtime, image, identity, MCP transport, Docker, or live-canary side effects
  - Protected config remained untouched, unstaged, and uncommitted
  - P6-AUTH-01 offline proof: no deployment, Kubernetes, second canary, or historical-group use
  - P6-CAN-01..06 implementation support only; live requirements remain runtime-gated
  - P6-REPT-01 mapping support only; complete §20 report remains Plan 06-05-gated
  - P6-PROV-02/03 live embedding proof/classification remain runtime-gated
  - P6-TERM-01..04 implementation support only; final classification remains runtime-gated
affects: [06-03, 06-04, 06-05, source-binding, final-canary]
tech-stack:
  added: []
  patterns: [sanitized fixed sentinel, create-on-failure terminal evidence, exclusive allocation claim]
key-files:
  created:
    - mcp_server/src/services/catalog_embedding_errors.py
  modified:
    - scripts/run_catalog_canary_batch.py
    - scripts/run_catalog_phase6_final_canary.py
    - tests/script/run_catalog_canary_batch.py
    - tests/script/test_run_catalog_phase6_final_canary.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_service.py
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-VALIDATION.md
key-decisions:
  - "Authentication classification uses provider type/numeric status only; exception text never becomes authority."
  - "Controlled replay is a committed harness gate with zero second commit, not a commit retry."
  - "Final-canary allocation uses one exclusive job-tmp claim; any prior claim rejects a second launch."
  - "Actual launcher argv must equal the approved expanded invocation before identity allocation."
patterns-established:
  - "Post-ID pretransport failure: empty validated ledger, sanitized report, acceptance manifest last."
  - "Phase live outputs contain bounded fields only; raw payload, MCP URL, token, and exception text stay excluded."
requirements-completed: [P6-PRES-01, P6-PRES-02, P6-HARN-19, P6-CONT-01]
requirements-implemented-runtime-pending: [P6-PROV-02, P6-PROV-03, P6-CAN-01, P6-CAN-03, P6-CAN-04, P6-CAN-05, P6-CAN-06, P6-TERM-01, P6-TERM-02, P6-TERM-03, P6-TERM-04, P6-REPT-01]
coverage:
  - id: D1
    description: Post-ID durable terminal evidence and three-class mapping
    requirement: P6-TERM-03
    verification:
      - kind: unit
        ref: tests/script/run_catalog_canary_batch.py
        status: pass
    human_judgment: false
  - id: D2
    description: Contract-safe embedding authentication sentinel
    requirement: P6-PROV-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py
        status: pass
    human_judgment: false
  - id: D3
    description: Final-canary launcher freeze, allocation, argv, terminal, and AUTH-01 contracts
    requirement: P6-CAN-01
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py
        status: pass
    human_judgment: false
duration: 56min
completed: 2026-07-22
status: complete
---

# Phase 6 Plan 02: Terminal/Auth/Replay Contracts Summary

**Post-ID failures now produce durable sanitized evidence, embedding auth stays contract-safe, and the final-canary launcher fails closed around one irreversible allocation.**

## Performance

- **Duration:** 56 min
- **Started:** 2026-07-22T10:27:58Z
- **Completed:** 2026-07-22T11:23:35Z
- **Tasks:** 2
- **Task-owned files:** 15 across RED and GREEN commits

## Accomplishments

- Enforced `PASSED | FAILED_BEFORE_COMMIT | FAILED_AFTER_COMMIT` after confirmed IDs; removed post-ID `BLOCKED` paths.
- Added shared create-on-failure persistence: validated empty ledger, sanitized final report, terminal acceptance manifest written last, zero transport before Gate 0.
- Added fixed `embedding_transport_auth` classification for prepare and search without new error enums or credential-bearing exception text.
- Kept exactly one token-only commit; unsupported replay advertisement fails before commit; commit ambiguity remains read-only reconciliation.
- Added final-canary orchestration: freeze/image binding, job-tmp token expansion, exact argv validation, one exclusive allocation claim, builder once, runner once, strict terminal schema/hash/count checks, AUTH-01, sanitized live output mapping.
- Removed the mocked test ledger side effect; launcher tests never write live evidence into the repository.
- Preserved `mcp_server/config/config-docker-neo4j.yaml` unstaged. No Docker, MCP transport, runtime, identity allocation, image build, canary, deployment, or Kubernetes action occurred.

## Task Commits

1. **Task 1: RED terminal/auth/replay/launcher contracts** — `d2256c8`
2. **Task 2: GREEN production and launcher implementation** — `3199a01`

## Verification

- Phase 6 harness: **57 passed**.
- Catalog regression matrix: **309 passed**.
- Ruff: passed.
- Changed production modules: `py_compile` passed.
- `git diff --check`: no whitespace errors; only Windows LF/CRLF notices.
- Fake repository `06-CANARY-LEDGER.json`: absent.
- Protected config: unstaged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Classified structured prepare errors before strict success-model validation**
- **Issue:** Exact auth sentinel payload first became `invalid_prepare_response`.
- **Fix:** Handle the exact auth pair, then generic structured errors, before success response validation.
- **Verification:** Prepare/auth selectors and complete matrices pass.

**2. [Rule 1 - Bug] Prevented mocked launcher tests from writing live repository evidence**
- **Issue:** A successful mock wrote fake `06-CANARY-LEDGER.json` into the real phase directory.
- **Fix:** Deleted only that fake artifact; redirected phase output writes to test-owned paths/spies; asserted the live path remains absent.
- **Verification:** Launcher suite passes; repository live ledger remains absent.

**3. [Rule 2 - Missing critical safety] Added exclusive pre-builder allocation claim**
- **Issue:** A crash after identity generation but before terminal mapping could allow a second launcher process.
- **Fix:** Exclusively create one job-tmp allocation claim before allocating the run ID; any existing claim fails closed.
- **Verification:** Dedicated exclusive-claim test passes.

**4. [Rule 2 - Missing critical evidence] Added schema-version and phase-report binding**
- **Issue:** Launcher accepted terminal files without exact schema versions and mapped only the JSON ledger.
- **Fix:** Validate runner report/ledger/acceptance schema versions; fill bounded live fields in the committed final-report shell; map sanitized failure evidence after allocation.
- **Verification:** Schema rejection, success mapping, and builder-failure mapping tests pass.

**Total deviations:** 4 auto-fixed correctness/safety gaps. No product schema or public tool contract expansion.

## Remaining Runtime Gates

- Live embedding proof, clean-room readiness, canary counts, terminal classification, and complete Spec §20 report remain intentionally pending Plans 06-03–06-05.
- No requirement dependent on Docker/MCP/live execution is marked complete here.

## Next Phase Readiness

- Plan 06-03 may run the source-complete PREBIND matrix, freeze a candidate, materialize its exact raw-Git archive, and run the frozen matrix.
- Image/runtime/canary work remains prohibited until later sequential gates.

## Self-Check: PASSED

- RED and GREEN commits exist.
- Summary records only task-owned behavior and offline evidence.
- No live identities or final canary artifacts exist.
- Protected user config remains untouched and unstaged.

---
*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Completed: 2026-07-22*
