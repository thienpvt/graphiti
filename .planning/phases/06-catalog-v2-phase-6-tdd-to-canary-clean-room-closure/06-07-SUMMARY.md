---
phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
plan: 07
subsystem: catalog-launcher
tags: [ollama, readiness, freeze-authority, final-canary, waiver, tdd]

requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: native Ollama clean-room config + factory contracts (06-06)
provides:
  - Ollama capability readiness Stage C contracts (tags-only, no-waiver)
  - freeze embedding authority validation (provider/model/dimensions/readiness/null waiver)
  - conditional waiver-free final-canary builder/runner argv for Ollama
  - 06-OLLAMA-* live output names for new operation evidence
affects:
  - 06-08 preflight/matrix
  - 06-09 bind/image
  - 06-10 R0-R3 prefreeze
  - 06-11 freeze/canary handoff

tech-stack:
  added: []
  patterns:
    - freeze receipt is sole authority for waiver argv construction
    - Ollama path omits --allow-unknown-embedding-provider entirely
    - operation-specific 06-OLLAMA-* outputs isolate new canary from immutable history

key-files:
  created: []
  modified:
    - mcp_server/tests/test_catalog_capabilities.py
    - tests/script/test_run_catalog_phase6_final_canary.py
    - scripts/run_catalog_phase6_final_canary.py

key-decisions:
  - "Production capability probe unchanged; existing /api/tags path already satisfied D-12"
  - "Default test freeze remains authorized OpenAI path so legacy suite stays green"
  - "Ollama live outputs use 06-OLLAMA-* names (D-16); never map into old ledger/report"

patterns-established:
  - "Stage C/D RED then GREEN separate commits for Ollama launcher gap"
  - "_child_waiver_argv(authority) is sole waiver argv constructor"
  - "_validate_observed_embedding_authority fails closed on provider/model/dim/readiness drift"

requirements-completed: [P6-OLL-CAPA-01, P6-OLL-LAUNCH-01]

coverage:
  - id: D1
    description: Ollama tags present yields embeddings.ready=ready; missing/unreachable yield error
    requirement: P6-OLL-CAPA-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py::test_ollama_tags_present_ready
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py::test_ollama_tags_missing_model_error
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py::test_ollama_unreachable_error
        status: pass
    human_judgment: false
  - id: D2
    description: Raw Ollama URL absent from capability output and logs; ollama unknown never gets openai waiver
    requirement: P6-OLL-CAPA-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py::test_ollama_raw_url_absent_from_caps_and_logs
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py::test_ollama_unknown_does_not_get_openai_waiver
        status: pass
    human_judgment: false
  - id: D3
    description: Freeze requires embedding authority; Ollama rejects openai/unknown/non-null waiver/model/dim drift
    requirement: P6-OLL-LAUNCH-01
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py::test_final_canary_ollama_freeze_requires_embedding_authority_fields
        status: pass
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py::test_final_canary_rejects_openai_provider_or_unknown_readiness_on_ollama_freeze
        status: pass
    human_judgment: false
  - id: D4
    description: Ollama final-canary builder/runner argv omit --allow-unknown-embedding-provider; write 06-OLLAMA-* outputs
    requirement: P6-OLL-LAUNCH-01
    verification:
      - kind: unit
        ref: tests/script/test_run_catalog_phase6_final_canary.py::test_final_canary_ollama_path_omits_openai_waiver_argv
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-23
status: complete
---

# Phase 06 Plan 07: Ollama Readiness Waiver and Final-Canary Freeze Authority Summary

**TDD-locked Ollama readiness (tags-only, no-waiver) plus freeze-bound conditional waiver-free final-canary argv and 06-OLLAMA-* live outputs**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-23T10:00:07Z
- **Completed:** 2026-07-23T10:07:33Z
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments

- Stage C RED then GREEN: capability tests lock Ollama `/api/tags` ready/error/url-redaction and fail-closed unknown (no OpenAI waiver); production probe unchanged (already correct)
- Stage D: freeze requires embedding authority fields; Ollama binds provider=ollama, model=qwen3-embedding:0.6b, dimensions=1024, readiness=ready, waiver=null
- Builder/runner argv omit `--allow-unknown-embedding-provider` entirely on Ollama path; OpenAI waiver remains only for authorized OpenAI freezes via `_child_waiver_argv`
- D-16: Ollama operation maps live outputs to `06-OLLAMA-CANARY-LEDGER.json` / `06-OLLAMA-FINAL-REPORT.md`; immutable old ledger/report never targeted by new Ollama runs
- Separate RED (`bb703f7`) then GREEN (`8a549b8`) commits; no network/runtime/canary/image activity; no STATE/ROADMAP edits

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — capability waiver policy + final-canary Ollama freeze/argv** - `bb703f7` (test)
2. **Task 2: GREEN — freeze embedding authority + conditional waiver-free argv** - `8a549b8` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD tasks have separate RED then GREEN commits_

## Files Created/Modified

- `mcp_server/tests/test_catalog_capabilities.py` - Stage C Ollama readiness + no-waiver unit tests
- `tests/script/test_run_catalog_phase6_final_canary.py` - Stage D freeze/argv/output contracts; default freeze is authorized OpenAI
- `scripts/run_catalog_phase6_final_canary.py` - embedding authority validation, conditional waiver argv, 06-OLLAMA-* live output mapping

## Decisions Made

- Capability production code needed no change: existing `_probe_ollama_embeddings_ready` already uses `/api/tags` only and maps present/missing/unreachable correctly
- Legacy suite freezes default to authorized OpenAI so historical path (including openai waiver argv) stays covered; Ollama tests use explicit OLLAMA_FREEZE_AUTHORITY
- Observed-drift helper `_validate_observed_embedding_authority` added for freeze-vs-observed fail-closed checks without expanding the 22-field live-manifest schema

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] D-16 OLLAMA output namespacing**
- **Found during:** Task 1 RED (locked requirements + prior summary seam)
- **Issue:** Launcher mapped all live outputs to immutable `06-CANARY-LEDGER.json` / `06-FINAL-REPORT.md`
- **Fix:** Provider-aware `_live_output_names` writes `06-OLLAMA-*` for Ollama freezes; legacy OpenAI path keeps historical names
- **Files modified:** `scripts/run_catalog_phase6_final_canary.py`, `tests/script/test_run_catalog_phase6_final_canary.py`
- **Verification:** `test_final_canary_ollama_path_omits_openai_waiver_argv` asserts OLLAMA-prefixed writes
- **Committed in:** `8a549b8`

**2. [Rule 1 - Bug] Legacy suite freeze fixture incomplete after authority gate**
- **Found during:** Task 2 GREEN
- **Issue:** Existing tests used freezes without embedding authority fields; `_validate_freeze` began requiring them
- **Fix:** Default `_freeze` fixture binds authorized OpenAI authority; Ollama tests override
- **Files modified:** `tests/script/test_run_catalog_phase6_final_canary.py`
- **Verification:** full launcher suite 27 passed
- **Committed in:** `8a549b8`

---

**Total deviations:** 2 auto-fixed (1 Rule 2, 1 Rule 1)
**Impact on plan:** Required for D-16 and suite correctness. No scope creep; 22-field manifest and 28-tool registry untouched.

## Issues Encountered

None beyond deviation fixes above. RED observed (3 launcher failures for missing freeze fields/hardcoded waiver) before GREEN.

## User Setup Required

None

## Known Stubs

None

## Threat Flags

None new beyond plan threat model mitigations T-06-OLL-04/05 (conditional waiver; no raw URL logs)

## TDD Gate Compliance

- RED commit present: `bb703f7 test(06-07): RED Ollama readiness waiver and final-canary freeze authority`
- GREEN commit present after RED: `8a549b8 feat(06-07): Ollama freeze authority and waiver-free final-canary argv`
- Focused verification: 7 ollama capability tests passed; 27 final-canary launcher tests passed
- `rg` shows waiver flag only inside `_child_waiver_argv` return (conditional), not hard-coded in builder/runner lists

## Next Phase Readiness

- Freeze receipts for native Ollama must include embedding authority fields with null waiver
- Downstream prefreeze/canary plans should emit/consume `06-OLLAMA-*` evidence names
- No shared tracking updates from this executor (orchestrator owns STATE/ROADMAP)

## Self-Check: PASSED

- FOUND: `mcp_server/tests/test_catalog_capabilities.py`
- FOUND: `tests/script/test_run_catalog_phase6_final_canary.py`
- FOUND: `scripts/run_catalog_phase6_final_canary.py`
- FOUND: `bb703f7`
- FOUND: `8a549b8`
- FOUND: `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-07-SUMMARY.md`
