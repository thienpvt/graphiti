---
phase: quick
plan: 260723-f4u
subsystem: catalog-phase6-launcher
tags: [final-canary, invocation-schema, allowlist, mcp_url_env]

requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: approved 06-POST-APPROVAL-INVOCATION.json with mcp_url_* metadata
provides:
  - _validate_invocation accepts approved mcp_url_env + mcp_url_hint_local_only
  - unknown top-level fields still fail closed before allocation
  - type-check for non-empty str on optional mcp_url_* when present
affects: [phase6-final-canary-launch]

tech-stack:
  added: []
  patterns:
    - optional approved metadata keys on allowlist with present-implies-nonempty-str

key-files:
  created:
    - .planning/quick/260723-f4u-fix-final-canary-invocation-schema/260723-f4u-PLAN.md
    - .planning/quick/260723-f4u-fix-final-canary-invocation-schema/260723-f4u-SUMMARY.md
  modified:
    - scripts/run_catalog_phase6_final_canary.py
    - tests/script/test_run_catalog_phase6_final_canary.py

key-decisions:
  - "Allowlist only mcp_url_env + mcp_url_hint_local_only; keep them optional for older fixtures"
  - "Present mcp_url_* values must be non-empty str; wrong type fails closed"
  - "No commit; parent owns freeze-HEAD authority before ID allocation"

patterns-established:
  - "Approved post-approval metadata keys join expected_fields without becoming required contract entries"

requirements-completed: [P6-SAFE-01, P6-RT-00, P6-PRES-01]

coverage:
  - id: D1
    description: Approved mcp_url_env and mcp_url_hint_local_only validate through _validate_invocation
    requirement: P6-SAFE-01
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py#test_validate_invocation_accepts_approved_mcp_url_fields
        status: pass
    human_judgment: false
  - id: D2
    description: Unknown top-level invocation fields still fail closed
    requirement: P6-RT-00
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py#test_validate_invocation_rejects_unknown_top_level_field
        status: pass
    human_judgment: false
  - id: D3
    description: Non-string mcp_url_env rejected without allocation path
    requirement: P6-PRES-01
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py#test_validate_invocation_rejects_non_string_mcp_url_env
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-23
status: complete
---

# Phase quick Plan 260723-f4u: Fix final canary invocation schema Summary

**`_validate_invocation` allowlist now accepts approved `mcp_url_env` / `mcp_url_hint_local_only`; unknown keys still fail closed before any identity allocation.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-23T04:00:00Z
- **Completed:** 2026-07-23T04:15:00Z
- **Tasks:** 2/2 (product fix + GSD closeout; STATE intentionally skipped)
- **Files modified:** 2 product + PLAN/SUMMARY under quick slug

## Accomplishments

- Root cause: allowlist omitted approved top-level MCP URL metadata fields present in `06-POST-APPROVAL-INVOCATION.json`.
- Fix: add `mcp_url_env` and `mcp_url_hint_local_only` to `expected_fields`; when present, require non-empty `str`.
- Regression tests: real approved keys accept; unknown field rejects; non-string type rejects.
- Full module green: `14 passed` with `--confcutdir=tests/script`.

## Task Commits

No git commits (parent instruction: do not commit; freeze HEAD authority must update pre-ID).

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED/GREEN allow approved mcp_url_* + fail-closed unknown | uncommitted | scripts/run_catalog_phase6_final_canary.py, tests/script/test_run_catalog_phase6_final_canary.py |
| 2 | GSD closeout SUMMARY only | uncommitted | 260723-f4u-SUMMARY.md (+ PLAN copy) |

## Files Created/Modified

- `scripts/run_catalog_phase6_final_canary.py` — allowlist + optional type check
- `tests/script/test_run_catalog_phase6_final_canary.py` — three new unit tests
- `.planning/quick/260723-f4u-fix-final-canary-invocation-schema/260723-f4u-PLAN.md` — plan copy in primary
- `.planning/quick/260723-f4u-fix-final-canary-invocation-schema/260723-f4u-SUMMARY.md` — this file

## Decisions Made

- Fields optional for absence (existing `_invocation()` fixtures stay valid); type-checked when present.
- No STATE.md update (parent: avoid lifecycle noise).
- No commit.

## Deviations from Plan

### Auto-fixed Issues

None - plan executed as written, with these intentional parent overrides:

- **No commit** (parent override; plan said commit product/docs).
- **STATE.md not updated** (parent override; avoid lifecycle noise).
- Worktree Edit tool blocked primary paths; patches applied in agent worktree then copied to primary.

## Non-claims / Prohibitions honored

- No final canary launcher e2e run
- No identity / namespace allocation
- No builder/runner invocation
- No Compose / MCP transport / provider calls
- No image rebuild / scanner
- No edits to Phase 6 lifecycle artifacts (`06-POST-APPROVAL-INVOCATION.json`, `06-FREEZE-RECEIPT.json`, `06-IMAGE-RECEIPT.json`, etc.)
- No touch/stage of `mcp_server/config/config-docker-neo4j.yaml`
- No allocation claim file written (`phase6-final-canary-allocation.json` not created by this work)

## Test Results

```text
# focused
pytest tests/script/test_run_catalog_phase6_final_canary.py -q -k "invocation or mcp_url or validate" --confcutdir=tests/script
3 passed, 11 deselected

# full module
pytest tests/script/test_run_catalog_phase6_final_canary.py -q --confcutdir=tests/script
14 passed
```

New tests:

- `test_validate_invocation_accepts_approved_mcp_url_fields`
- `test_validate_invocation_rejects_unknown_top_level_field`
- `test_validate_invocation_rejects_non_string_mcp_url_env`

## Known Stubs

None.

## Threat Flags

None beyond plan threat model.

## Self-Check: PASSED

- Product files present in primary with `mcp_url_env` / `mcp_url_hint_local_only` allowlist
- Tests present and green
- PLAN + SUMMARY written under quick slug
- STATE intentionally not updated
- No commit
