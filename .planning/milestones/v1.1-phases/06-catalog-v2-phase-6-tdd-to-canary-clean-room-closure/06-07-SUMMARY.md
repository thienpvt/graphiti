---
phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
plan: 07
subsystem: catalog-launcher
tags: [ollama, readiness, freeze-authority, final-canary, waiver, tdd, config-fingerprint, gate1]

requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: native Ollama clean-room config + factory contracts (06-06)
provides:
  - Ollama capability readiness Stage C contracts (tags-only, no-waiver)
  - freeze embedding authority validation (provider/model/dimensions/readiness/null waiver)
  - conditional waiver-free final-canary builder/runner argv for Ollama
  - 06-OLLAMA-* live output names for new operation evidence
  - config_fingerprint (64-hex) required for Ollama freeze; host digests before claim
  - Gate 1 expected vs observed embedding authority all-or-none
  - dimensions threaded through capabilities/MCP; D-17 sanitized ledger fields
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
    - config_fingerprint is sole sanitized config authority (never raw URL/namespace)
    - Gate 1 compares freeze expected authority to observed readiness all-or-none

key-files:
  created: []
  modified:
    - mcp_server/tests/test_catalog_capabilities.py
    - tests/script/test_run_catalog_phase6_final_canary.py
    - tests/script/run_catalog_canary_batch.py
    - scripts/run_catalog_phase6_final_canary.py
    - scripts/run_catalog_canary_batch.py
    - mcp_server/src/services/catalog_capabilities.py
    - mcp_server/src/graphiti_mcp_server.py

key-decisions:
  - "Production capability probe unchanged; existing /api/tags path already satisfied D-12"
  - "Default test freeze remains authorized OpenAI path so legacy suite stays green"
  - "Ollama live outputs use 06-OLLAMA-* names (D-16); never map into old ledger/report"
  - "Ollama freeze requires config_fingerprint; digests compared before identity allocation"
  - "D-17 ledger/report expose provider/model/dimensions/readiness/null waiver + config_fingerprint only"
  - "execute_cli keeps strict attribute access; test fixtures supply expected authority attrs"

patterns-established:
  - "Stage C/D RED then GREEN separate commits for Ollama launcher gap"
  - "_child_waiver_argv(authority) is sole waiver argv constructor"
  - "_validate_observed_embedding_authority fails closed on provider/model/dim/readiness drift"
  - "Gate 1 evaluate_embedding_readiness(expected_*) all-or-none before waiver logic"
  - "main() selects OLLAMA vs legacy invocation by freeze provider"

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

**TDD-locked Ollama readiness (tags-only, no-waiver) plus freeze-bound authority, Gate 1 observed compare, config_fingerprint, and 06-OLLAMA-* live outputs**

## Performance

- **Duration:** ~25 min (initial + authority fix-forward)
- **Started:** 2026-07-23T10:00:07Z
- **Completed:** 2026-07-23
- **Tasks:** 2/2 + fix-forward
- **Files modified:** 8 (code) + plan/summary docs

## Accomplishments

- Stage C RED then GREEN: capability tests lock Ollama `/api/tags` ready/error/url-redaction and fail-closed unknown (no OpenAI waiver); production probe unchanged (already correct)
- Stage D: freeze requires embedding authority fields; Ollama binds provider=ollama, model=qwen3-embedding:0.6b, dimensions=1024, readiness=ready, waiver=null
- Builder/runner argv omit `--allow-unknown-embedding-provider` entirely on Ollama path; OpenAI waiver remains only for authorized OpenAI freezes via `_child_waiver_argv`
- D-16: Ollama operation maps live outputs to `06-OLLAMA-CANARY-LEDGER.json` / `06-OLLAMA-FINAL-REPORT.md`; immutable old ledger/report never targeted by new Ollama runs
- Fix-forward: Ollama freeze requires `config_fingerprint` (64-hex); host Gate 0 digests compared before identity claim; runner argv gets expected authority
- Gate 1: `evaluate_embedding_readiness` all-or-none expected vs observed provider/model/dimensions/readiness
- Dimensions threaded through `catalog_capabilities` + `get_catalog_capabilities` MCP tool
- D-17: ledger/report sanitized fields only (provider/model/dimensions/readiness/null waiver + config_fingerprint)
- `main()` selects `06-OLLAMA-POST-APPROVAL-INVOCATION.json` by freeze provider; Ollama has no legacy final-report fallback
- Separate RED/GREEN commits; no network/runtime/canary/image; no STATE/ROADMAP

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — capability waiver policy + final-canary Ollama freeze/argv** - `bb703f7` (test)
2. **Task 2: GREEN — freeze embedding authority + conditional waiver-free argv** - `8a549b8` (feat)
3. **Fix-forward RED — strict Ollama artifacts and observed authority** - `b6cdf53` (test)
4. **Fix-forward GREEN — bind Ollama config and runtime embedding authority** - `ada9a0c` (fix)

**Plan metadata:** (docs commit follows)

_Note: TDD tasks have separate RED then GREEN commits_

## Files Created/Modified

- `mcp_server/tests/test_catalog_capabilities.py` - Stage C Ollama readiness + no-waiver unit tests
- `tests/script/test_run_catalog_phase6_final_canary.py` - Stage D freeze/argv/output + fingerprint/invocation contracts
- `tests/script/run_catalog_canary_batch.py` - Gate 1 expected-authority tests; execute_cli fixtures supply expected_* attrs
- `scripts/run_catalog_phase6_final_canary.py` - fingerprint, Gate 0 digests-before-claim, invocation selection, D-17 fields, terminal authority
- `scripts/run_catalog_canary_batch.py` - expected authority CLI + Gate 1 compare; terminal report fields
- `mcp_server/src/services/catalog_capabilities.py` - embedder_dimensions in capabilities payload
- `mcp_server/src/graphiti_mcp_server.py` - pass embedder_dimensions from config
- `06-10-PLAN.md` / `06-11-PLAN.md` - FREEZE-INPUTS/RECEIPT + launcher OLLAMA invocation notes

## Decisions Made

- Capability production probe needed no change for tags-only readiness; dimensions added for authority surface
- Legacy suite freezes default to authorized OpenAI; Ollama tests use explicit OLLAMA_FREEZE_AUTHORITY incl. config_fingerprint
- Observed-drift helper `_validate_observed_embedding_authority` + runner Gate 1 expected_* all-or-none; 22-field live-manifest schema unchanged
- Production `execute_cli` keeps strict attribute access; test SimpleNamespace fixtures must include expected embedding attrs (all None for legacy)

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

**3. [Rule 1 - Bug] execute_cli SimpleNamespace missing expected_* attrs after Gate 1**
- **Found during:** Fix-forward GREEN verification
- **Issue:** Three live-canary execute_cli fixtures lacked expected embedding attrs; production uses strict access (correct)
- **Fix:** Fixtures supply all four expected_* as None for legacy path; success test asserts handoff kwargs
- **Files modified:** `tests/script/run_catalog_canary_batch.py`
- **Verification:** full runner suite 48 passed
- **Committed in:** `ada9a0c`

**4. [Rule 2 - Missing critical functionality] Authority fix-forward (coordinator gaps)**
- **Found during:** Post-merge coordinator verify
- **Issue:** main() always legacy invocation; Ollama fallback to legacy report; no Gate 1 expected compare; no config_fingerprint; dimensions not threaded; ledger lacked D-17 sanitized fields
- **Fix:** Provider-aware invocation; no Ollama legacy report fallback; expected authority CLI + Gate 1; fingerprint pre-claim; dimensions in capabilities; D-17 ledger fields
- **Files modified:** launcher, runner, capabilities, MCP, tests, 06-10/06-11 plans
- **Verification:** launcher 33 passed; runner 48 passed; capabilities 41 passed
- **Committed in:** RED `b6cdf53`, GREEN `ada9a0c`

---

**Total deviations:** 4 auto-fixed (2 Rule 2, 2 Rule 1)
**Impact on plan:** Required for D-16/D-17 and suite correctness. No scope creep; 22-field manifest and 28-tool registry untouched.

## Issues Encountered

None beyond deviation fixes above. RED observed before each GREEN. Pyright on runner from root reports env-only missing mcp/models imports (mcp_server path); launcher 0 errors; capabilities 0 errors in mcp_server env.

## User Setup Required

None

## Known Stubs

None

## Threat Flags

None new beyond plan threat model mitigations T-06-OLL-04/05 (conditional waiver; no raw URL logs). D-17 keeps config authority as fingerprint only.

## TDD Gate Compliance

- RED: `bb703f7 test(06-07): RED Ollama readiness waiver and final-canary freeze authority`
- GREEN: `8a549b8 feat(06-07): Ollama freeze authority and waiver-free final-canary argv`
- Fix-forward RED: `b6cdf53 test(06-07): RED strict Ollama artifacts and observed authority`
- Fix-forward GREEN: `ada9a0c fix(06-07): bind Ollama config and runtime embedding authority`
- Verification: launcher 33 passed; runner 48 passed; capabilities 41 passed; ruff clean
- Waiver flag only via `_child_waiver_argv` (conditional); never hard-coded on Ollama path

## Next Phase Readiness

- Freeze receipts for native Ollama must include embedding authority + config_fingerprint with null waiver
- Downstream prefreeze/canary plans emit/consume `06-OLLAMA-*` evidence and OLLAMA invocation path
- No shared tracking updates from this executor (orchestrator owns STATE/ROADMAP)

## Self-Check: PASSED

- FOUND: `mcp_server/tests/test_catalog_capabilities.py`
- FOUND: `tests/script/test_run_catalog_phase6_final_canary.py`
- FOUND: `tests/script/run_catalog_canary_batch.py`
- FOUND: `scripts/run_catalog_phase6_final_canary.py`
- FOUND: `scripts/run_catalog_canary_batch.py`
- FOUND: `bb703f7`
- FOUND: `8a549b8`
- FOUND: `b6cdf53`
- FOUND: `ada9a0c`
- FOUND: `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-07-SUMMARY.md`
