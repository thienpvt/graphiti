---
phase: 00-baseline-inventory-and-compatibility-policy
plan: 02
subsystem: testing
tags: [compatibility, isolation, safety, canary-ban, dirty-tree, phase-gate]

requires:
  - phase: 00-baseline-inventory-and-compatibility-policy
    provides: Live 21-tool inventory, offline ACCEPT_TAB digests, truthful pass|fail|skip ledger
provides:
  - Compatibility freeze for 14 legacy + 7 catalog tool names and catalog-v1 deprecation boundary
  - Isolation policy for oracle-catalog-tool-test, canary ban, dirty-tree allowlist, remote ban
  - Phase 0 gate report with ready_for_phase_1 and safety invariants
affects:
  - Phase 1 strict contracts and catalog-v2 identity
  - All later v1.1 phases consuming isolation/compatibility constraints

tech-stack:
  added: []
  patterns:
    - Policy-only Phase 0 freeze with citable phase-dir artifacts
    - ready_for_phase_1 gated on artifacts + safety invariants + truthful ledger

key-files:
  created:
    - .planning/phases/00-baseline-inventory-and-compatibility-policy/00-COMPATIBILITY-POLICY.md
    - .planning/phases/00-baseline-inventory-and-compatibility-policy/00-ISOLATION-POLICY.md
    - .planning/phases/00-baseline-inventory-and-compatibility-policy/00-PHASE0-GATE.md
  modified: []

key-decisions:
  - "ready_for_phase_1=true despite pre-existing canary-script fail row (Wave 1 baseline noise, not Phase 0 blocker)"
  - "Plan 02 executor does not update shared STATE/ROADMAP (orchestrator owns merge-time tracking)"
  - "Historical ACCEPT_TAB digests remain invalid catalog-v2 goldens (IDEN-13)"

patterns-established:
  - "Compatibility and isolation policies live under phase dir and are cited by later plans"
  - "Gate report copies fail/skip statuses without reclassifying as pass"

requirements-completed: [SAFE-01, SAFE-02, SAFE-12, SAFE-13, BASE-04]

coverage:
  - id: D1
    description: Compatibility freeze preserving 14 legacy + 7 catalog tool names and catalog-v1 deprecation boundary
    requirement: BASE-04
    verification:
      - kind: other
        ref: "00-COMPATIBILITY-POLICY.md tool tables + disposition table; rg catalog-v1|identity_schema"
        status: pass
    human_judgment: false
  - id: D2
    description: Isolation policy requiring oracle-catalog-tool-test and banning canary runner + oracle-catalog-v2 mutation
    requirement: SAFE-01
    verification:
      - kind: other
        ref: "00-ISOLATION-POLICY.md §§1-3; rg oracle-catalog-tool-test|run_catalog_canary_batch"
        status: pass
    human_judgment: false
  - id: D3
    description: Dirty-tree exclude list, commit allowlist, and remote ban (SAFE-12/13)
    requirement: SAFE-12
    verification:
      - kind: other
        ref: "00-ISOLATION-POLICY.md §§4-6; git status allowlist check exit 0"
        status: pass
    human_judgment: false
  - id: D4
    description: Phase 0 gate with safety invariants and ready_for_phase_1 decision for Phase 1 entry
    requirement: SAFE-02
    verification:
      - kind: other
        ref: "00-PHASE0-GATE.md ready_for_phase_1=true; canary_executed=false; truthful fail/skip ledger"
        status: pass
    human_judgment: false

duration: 2min
completed: 2026-07-18
status: complete
---

# Phase 0 Plan 02: Compatibility, Isolation, and Gate Summary

**Compatibility freeze for 14+7 MCP tools, isolation/canary/remote bans, and Phase 0 gate with ready_for_phase_1=true**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-17T17:42:47Z
- **Completed:** 2026-07-17T17:44:45Z
- **Tasks:** 2
- **Files modified:** 3 created (phase artifacts only)

## Accomplishments

- Froze 14 legacy + 7 catalog tool names; documented explicit catalog-v1→v2 break without silent rewrite
- Recorded isolation policy: `oracle-catalog-tool-test` only, canary ban, dirty-tree exclude list, SAFE-13 remote ban
- Emitted Phase 0 gate with artifact checklist, eight-requirement map, truthful pass=2/fail=1/skip=1 ledger
- Set `ready_for_phase_1=true` with all safety invariants false for canary/v2-query/product/dirty/remote risks

## Task Commits

1. **Task 1: Write compatibility and isolation policy documents** - `d05e1ec` (docs)
2. **Task 2: Emit Phase 0 gate report and prove safety invariants** - `5488852` (docs)

**Plan metadata:** (this SUMMARY commit)

## Files Created/Modified

- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-COMPATIBILITY-POLICY.md` - Tool-name freeze, identity authority note, historical disposition table
- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-ISOLATION-POLICY.md` - Group isolation, canary ban, dirty-tree allowlist, remote ban, verification commands
- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-PHASE0-GATE.md` - Single Phase 1 entry gate with `ready_for_phase_1=true`

## Decisions Made

- `ready_for_phase_1=true` even with Wave 1 catalog offline-canary **fail** row — Phase 0 requires truthful recording, not repair
- Shared STATE/ROADMAP not updated by this executor (orchestrator owns post-merge tracking)
- Historical ACCEPT_TAB SHAs remain invalid hardened goldens

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Pre-existing Wave 1 canary-script failures remain baseline noise only.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 may start under `ready_for_phase_1=true`
- Must cite `00-COMPATIBILITY-POLICY.md` and `00-ISOLATION-POLICY.md`
- Compare future checks against `00-baseline-checks.json` fail/skip rows
- Still banned: canary runner, `oracle-catalog-v2` query/mutation, remote ops, unrelated dirty commits

## Gate Outcome

```text
ready_for_phase_1=true
canary_executed=false
oracle_catalog_v2_queried=false
product_contract_or_identity_code_changed=false
unrelated_dirty_files_committed=false
remote_push_merge_deploy_tag=false
check_counts: pass=2 fail=1 skip=1
```

## Self-Check: PASSED

- FOUND: `00-COMPATIBILITY-POLICY.md`
- FOUND: `00-ISOLATION-POLICY.md`
- FOUND: `00-PHASE0-GATE.md`
- FOUND: commit `d05e1ec`
- FOUND: commit `5488852`
- No product source edited; no STATE.md/ROADMAP.md updates; no remote ops

---
*Phase: 00-baseline-inventory-and-compatibility-policy*
*Completed: 2026-07-18*
