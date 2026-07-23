---
phase: quick
plan: 260723-ita
subsystem: catalog-phase6-launcher
tags: [final-canary, preflight, live-markers, fail-closed]

requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: final-canary launcher + phase final-report shell
provides:
  - pre-allocation final-report LIVE_FIELDS marker validation
  - committed ordered LIVE_FIELDS markers in 06-FINAL-REPORT.md
  - regression coverage for real shell + fail-closed claim gating
affects: [phase6-final-canary-handoff]

tech-stack:
  added: []
  patterns:
    - shared marker validation used by preflight and _final_report_text
    - fail closed before _claim_allocation on bad/missing shell

key-files:
  created:
    - .planning/quick/260723-ita-fix-final-canary-shell-preflight/260723-ita-SUMMARY.md
  modified:
    - scripts/run_catalog_phase6_final_canary.py
    - tests/script/test_run_catalog_phase6_final_canary.py
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md

key-decisions:
  - "Extract shared _validate_final_report_live_markers so preflight and mapping cannot drift"
  - "Call _require_final_report_live_markers after freeze/image checks and before _claim_allocation"
  - "Commit LIVE_FIELDS markers around section 3 classification shell only; keep pending placeholders"

patterns-established:
  - "Read-only shell preflight before any identity allocation claim"
  - "FinalCanaryError message contract: 'final report live field markers are invalid' / 'final report shell is unavailable'"

requirements-completed: [P6-SAFE-01, P6-PRES-01, P6-RT-00]

coverage:
  - id: D1
    description: Shared LIVE_FIELDS marker validation helper
    requirement: P6-SAFE-01
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py::test_final_report_live_markers_valid_text_does_not_raise
        status: pass
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py::test_final_report_live_markers_invalid_raise
        status: pass
    human_judgment: false
  - id: D2
    description: Committed phase final-report shell has ordered LIVE_FIELDS markers
    requirement: P6-PRES-01
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py::test_final_report_shell_live_markers_preflight_valid
        status: pass
    human_judgment: false
  - id: D3
    description: Missing/malformed shell fails before _claim_allocation
    requirement: P6-SAFE-01
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py::test_final_canary_missing_shell_markers_fail_before_claim_allocation
        status: pass
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py::test_final_canary_missing_shell_file_fails_before_claim_allocation
        status: pass
    human_judgment: false
  - id: D4
    description: No runtime/canary/identity/argv/lifecycle work in this fix
    requirement: P6-RT-00
    verification:
      - kind: other
        ref: git status scoped to launcher + tests + final-report shell + quick SUMMARY only
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-23
status: complete
---

# Phase quick Plan 260723-ita: Final canary shell preflight Summary

**Pre-allocation LIVE_FIELDS marker preflight + committed shell markers so final-canary cannot claim IDs then fail mapping.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-23
- **Completed:** 2026-07-23
- **Tasks:** 2/2
- **Files modified:** 4

## Root cause

`run_final_canary` called `_claim_allocation` after freeze/image checks, then later `_map_phase_outputs` → `_final_report_text` required `LIVE_FIELDS_START`/`LIVE_FIELDS_END`. Committed `06-FINAL-REPORT.md` section 3 had no markers, so a successful pre-allocation path would allocate then fail phase-output mapping. Prior rejections happened earlier (argv path representation), so no live claim existed; risk remained for next exact-argv approval.

## Fix

1. **Shared validation** — `_validate_final_report_live_markers(text)` enforces start/end find rules (`start < 0 or end < 0 or end <= start` → `FinalCanaryError('final report live field markers are invalid')`). Used by `_final_report_text` and preflight.
2. **Read-only preflight** — `_require_final_report_live_markers(phase_dir)` reads `phase_dir / '06-FINAL-REPORT.md'`; OSError → `final report shell is unavailable`.
3. **Order** — after freeze/image checks, before `_claim_allocation`, call preflight.
4. **Committed shell** — wrap section 3 classification table with exact `<!-- phase6-final-canary-live:start -->` / `<!-- phase6-final-canary-live:end -->`. Pending placeholders retained; no live values; no canary claim.

## Tests added

- `test_final_report_shell_live_markers_preflight_valid` — real phase shell path validates
- `test_final_report_live_markers_valid_text_does_not_raise`
- `test_final_report_live_markers_invalid_raise` (missing start/end, inverted)
- `test_final_report_live_markers_end_before_start_raises`
- `test_final_canary_missing_shell_markers_fail_before_claim_allocation` — `_claim_allocation` monkeypatched to assert not called
- `test_final_canary_missing_shell_file_fails_before_claim_allocation`

## Verification

```text
python -m pytest tests/script/test_run_catalog_phase6_final_canary.py -q --confcutdir=tests/script --tb=short
# 23 passed

python -m ruff check scripts/run_catalog_phase6_final_canary.py tests/script/test_run_catalog_phase6_final_canary.py
python -m ruff format --check scripts/run_catalog_phase6_final_canary.py tests/script/test_run_catalog_phase6_final_canary.py
# All checks passed / already formatted
```

## Explicit non-claims

- No final canary end-to-end run
- No ID allocation claim on disk outside tmp fixtures
- No argv / exact-invocation relaxation
- No edits to `06-FREEZE-RECEIPT.json`, `06-POST-APPROVAL-INVOCATION.json`, `06-IMAGE-RECEIPT.json`
- No edits to `mcp_server/config/config-docker-neo4j.yaml`
- No edits to `.planning/STATE.md` or `.planning/ROADMAP.md`
- No runtime/Compose/MCP/provider/namespace/image rebuild/cleanup/lifecycle completion
- No commit by this executor (parent verifies and refreezes)

## Deviations from Plan

None — plan executed as written. Commits deferred per parent instruction.

## Task Commits

Commits deferred: parent will verify and refreeze. Working tree changes only:

1. **Task 1: RED/GREEN pre-allocation shell preflight + committed markers** — uncommitted
2. **Task 2: Quick SUMMARY only** — uncommitted

## Files Created/Modified

- `scripts/run_catalog_phase6_final_canary.py` — shared marker validation + pre-allocation preflight
- `tests/script/test_run_catalog_phase6_final_canary.py` — real shell + fail-closed claim tests
- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md` — ordered LIVE_FIELDS markers
- `.planning/quick/260723-ita-fix-final-canary-shell-preflight/260723-ita-SUMMARY.md` — this summary

## Self-Check: PASSED

- FOUND: scripts/run_catalog_phase6_final_canary.py helpers + preflight call site
- FOUND: ordered LIVE_FIELDS markers in 06-FINAL-REPORT.md
- FOUND: new regression tests; full launcher file 23 passed
- FOUND: SUMMARY path
- CONFIRMED: freeze/post-approval/image/STATE/ROADMAP/protected config untouched by this plan
