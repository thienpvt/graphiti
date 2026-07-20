---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 01
subsystem: testing
tags: [tdd, wave0, catalog, manifest, evidence, gate-runner, neo4j]

requires:
  - phase: 03A-immutable-prepare-commit-control-plane
    provides: prepare/commit control plane, Phase 3A gate runner pattern, catalog fixtures
provides:
  - Wave 0 RED suite scaffolds for all Phase 3B missing test modules
  - Fail-closed catalog_phase3b_gate_runner with ready_for_phase_4 default false
  - Named collectable cases covering PLAN-13..16, EVID-07..11, MANI-01..07, TEST-06/07
affects:
  - 03B-02 (manifest GREEN)
  - 03B-03 (evidence/manifest store GREEN)
  - 03B-04 (atomic writer GREEN)
  - 03B-05 (recovery/concurrency GREEN)
  - 03B-06 (live proof + gate apply)

tech-stack:
  added: []
  patterns:
    - importlib/getattr for future product symbols (no static missing imports)
    - Phase 3A-style fail-closed HEAD/content/spec/live gate ledger
    - pytest.fail('03B not implemented') RED until GREEN plans

key-files:
  created:
    - mcp_server/tests/test_catalog_manifest.py
    - mcp_server/tests/test_catalog_evidence_store.py
    - mcp_server/tests/test_catalog_atomic_writer.py
    - mcp_server/tests/test_catalog_commit_recovery.py
    - mcp_server/tests/test_catalog_concurrency.py
    - mcp_server/tests/test_catalog_commit_neo4j_int.py
    - mcp_server/tests/catalog_phase3b_gate_runner.py
    - mcp_server/tests/test_catalog_phase3b_gate_runner.py
  modified: []

key-decisions:
  - "Wave 0 only: no product co-commit implementation; all product suites intentionally RED"
  - "ready_for_phase_4 requires local+live+safety+manifests under --require-neo4j; default false without live"
  - "Live isolation hard-codes oracle-catalog-tool-test; FORBIDDEN_GROUP=oracle-catalog-v2 never write target"
  - "Future modules loaded via importlib/getattr to stay pyright-clean before product exists"

patterns-established:
  - "Phase 3B gate runner mirrors 3A (canonical specs, sentinel, content digest, safety ledger)"
  - "Named primary RED cases reserved for later GREEN plans (no silent drop of 24 probe rows)"
  - "Dynamic import for not-yet-existing product modules; fixtures via spec_from_file_location"

requirements-completed:
  - PLAN-13
  - PLAN-14
  - PLAN-15
  - PLAN-16
  - EVID-07
  - EVID-08
  - EVID-09
  - EVID-10
  - EVID-11
  - MANI-01
  - MANI-02
  - MANI-03
  - MANI-04
  - MANI-06
  - MANI-07
  - TEST-06
  - TEST-07

coverage:
  - id: D1
    description: Five pure/store/service/concurrency RED suite scaffolds collect with named Phase 3B cases
    requirement: PLAN-13
    verification:
      - kind: unit
        ref: "pytest --collect-only five unit modules (40 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: Live Neo4j int scaffold hard-codes oracle-catalog-tool-test; truthful skip/RED
    requirement: TEST-07
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_commit_neo4j_int.py --collect-only"
        status: pass
    human_judgment: false
  - id: D3
    description: Gate runner ready_for_phase_4 defaults false without live green
    requirement: TEST-06
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_phase3b_gate_runner.py::test_ready_for_phase_4_false_without_live"
        status: pass
    human_judgment: false
  - id: D4
    description: Scoped Ruff + Pyright clean on all eight Wave 0 files
    verification:
      - kind: other
        ref: "uv run pyright/ruff on created Wave 0 files"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-18
status: complete
---

# Phase 03B Plan 01: Wave 0 RED Scaffolds Summary

**Nyquist Wave 0 RED scaffolds for every missing Phase 3B suite plus fail-closed gate runner; no product co-commit path.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-18T10:13:03Z
- **Completed:** 2026-07-18T10:20:00Z
- **Tasks:** 2/2
- **Files modified:** 8 created (tests/gate only)

## Accomplishments

- Created five pure/store/service/concurrency RED modules with named cases (40 collectable tests)
- Created live Neo4j int scaffold (7 cases) with `TEST_GROUP=oracle-catalog-tool-test` only
- Ported Phase 3A gate structure to `catalog_phase3b_gate_runner.py` with `ready_for_phase_4` fail-closed default
- Gate unit suite (14 tests) proves live skip/safety/manifests block readiness
- Pyright/Ruff clean via importlib dynamic loading (no static missing-module imports)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED pure/store/service suite scaffolds** - `05ed0ca` (test)
2. **Task 2: RED live Neo4j + Phase 3B gate runner scaffolds** - `6b3c623` (test)
3. **Follow-up: pyright-clean Wave 0 scaffolds** - `2931539` (fix)
4. **Follow-up: remaining static diagnostics** - `b3be98e` (fix)

**Plan metadata:** (this SUMMARY commit)

_Note: TDD Wave 0 is RED-only; GREEN implementation is deferred to plans 02–06._

## Files Created/Modified

- `mcp_server/tests/test_catalog_manifest.py` — MANI-01..07 pure manifest RED cases
- `mcp_server/tests/test_catalog_evidence_store.py` — EVID-07..11 evidence store RED cases
- `mcp_server/tests/test_catalog_atomic_writer.py` — PLAN-13/14 shared writer + fault inject RED
- `mcp_server/tests/test_catalog_commit_recovery.py` — PLAN-14/15 terminal agreement / COMMITTING RED
- `mcp_server/tests/test_catalog_concurrency.py` — PLAN-16/TEST-06 same-token race RED
- `mcp_server/tests/test_catalog_commit_neo4j_int.py` — Live atomic co-commit RED/skip skeleton
- `mcp_server/tests/catalog_phase3b_gate_runner.py` — Fail-closed Phase 3B gate runner
- `mcp_server/tests/test_catalog_phase3b_gate_runner.py` — Gate unit proofs (14 pass)

## Decisions Made

- No production code in this plan (plan prohibition + Wave 0 scope)
- `ready_for_phase_4` false unless `require_neo4j` live pass + safety + `features.manifests`
- Future product symbols via `importlib.import_module` / `getattr` (identity-test pattern)
- Fixtures loaded with `importlib.util.spec_from_file_location` for pyright `extraPaths=src`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Pyright-clean dynamic imports**
- **Found during:** Post-Task 2 coordinator diagnostic review
- **Issue:** Static `from services.catalog_manifest import ...` and similar unresolved imports; unused availability flags; safety regex false-positive on `FORBIDDEN_GROUP = '...'`
- **Fix:** importlib/getattr for future modules; fixtures via file-location load; word-boundary on GROUP assign regex; `validate_spec(root)` retained as reserved param
- **Files modified:** all eight Wave 0 files
- **Verification:** scoped pyright 0 errors; ruff clean; 61 collected; 14 gate unit pass; primary RED still fail
- **Committed in:** `2931539`

**2. [Rule 1 - Bug] Dead typed guard + unused symbols**
- **Found during:** Post-fix coordinator diagnostic review
- **Issue:** `validate_spec(spec: dict)` made `isinstance(spec, dict)` unreachable; GROUP/_PRODUCT_SYMBOLS unused in unit scaffolds
- **Fix:** `validate_spec(spec: object)` with payload narrowing; assert GROUP/_PRODUCT_SYMBOLS in primary cases
- **Files modified:** catalog_phase3b_gate_runner.py + five unit scaffolds
- **Verification:** scoped pyright 0 errors/warnings; ruff clean; gate unit 14 pass
- **Committed in:** `b3be98e`

---

**Total deviations:** 2 auto-fixed (Rule 2 + Rule 1)
**Impact on plan:** Correctness/tooling only; RED behavior and fail-closed defaults preserved. No scope creep.

## Issues Encountered

None beyond coordinator-requested pyright cleanup (handled as follow-up fix commits).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 02–06 have collectable RED targets for every 03B-VALIDATION Wave 0 row
- Gate remains `ready_for_phase_4=false` until live atomic proof + manifests flip (plan 06)
- Product co-commit path intentionally absent

## Known Stubs

Intentional Wave 0 RED stubs (by design; GREEN plans own implementation):

| File | Pattern | Reason |
|------|---------|--------|
| `test_catalog_manifest.py` | `pytest.fail('...03B not implemented')` | Product `catalog_manifest` in 03B-02 |
| `test_catalog_evidence_store.py` | `pytest.fail` | Evidence store writes in 03B-03 |
| `test_catalog_atomic_writer.py` | `pytest.fail` | Shared writer in 03B-04 |
| `test_catalog_commit_recovery.py` | `pytest.fail` | Recovery in 03B-05 |
| `test_catalog_concurrency.py` | `pytest.fail` | Concurrency in 03B-05 |
| `test_catalog_commit_neo4j_int.py` | `pytest.fail` after live probe | Live proof in 03B-06 |

These stubs do not prevent Wave 0 goal (collectable named RED + fail-closed gate).

## Threat Flags

None - no new network endpoints, auth paths, or production schema. Gate/safety checks only.

## Self-Check: PASSED

- FOUND: `mcp_server/tests/test_catalog_manifest.py`
- FOUND: `mcp_server/tests/test_catalog_evidence_store.py`
- FOUND: `mcp_server/tests/test_catalog_atomic_writer.py`
- FOUND: `mcp_server/tests/test_catalog_commit_recovery.py`
- FOUND: `mcp_server/tests/test_catalog_concurrency.py`
- FOUND: `mcp_server/tests/test_catalog_commit_neo4j_int.py`
- FOUND: `mcp_server/tests/catalog_phase3b_gate_runner.py`
- FOUND: `mcp_server/tests/test_catalog_phase3b_gate_runner.py`
- FOUND: commit `05ed0ca`
- FOUND: commit `6b3c623`
- FOUND: commit `2931539`
- FOUND: commit `b3be98e`
- Verify: 61 tests collected; gate unit 14 passed; pyright 0 errors/warnings; ruff clean
- No STATE.md / ROADMAP.md modifications (orchestrator-owned)

---
*Phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes*
*Completed: 2026-07-18*
