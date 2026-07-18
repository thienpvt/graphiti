---
phase: 04-manifest-backed-verification-and-read-only-diagnostics
plan: 01
subsystem: testing
tags: [tdd, wave0, red, catalog, gate-runner, manifest, verify, phase4]

requires:
  - phase: 03B
    provides: catalog_phase3b_gate_runner pattern (HEAD/spec/content/safety)
provides:
  - Five collectable Phase 4 RED test modules (52 named cases)
  - Fail-closed catalog_phase4_gate_runner with ready_for_phase_5 default false
  - Gate unit suite proving D-30/D-31 fail-closed defaults
affects:
  - 04-02
  - 04-03
  - 04-04
  - 04-05
  - 04-06

tech-stack:
  added: []
  patterns:
    - "Wave 0 RED via pytest.fail + importlib-safe collection"
    - "Phase 4 gate runner port of 3B with ready_for_phase_5 fail-closed"
    - "Bare GROUP assignment ban excluding FORBIDDEN_GROUP constant"

key-files:
  created:
    - mcp_server/tests/test_catalog_gates.py
    - mcp_server/tests/test_catalog_manifest_read.py
    - mcp_server/tests/test_catalog_verify_manifest.py
    - mcp_server/tests/test_catalog_resolve_edges.py
    - mcp_server/tests/test_catalog_evidence_read.py
    - mcp_server/tests/catalog_phase4_gate_runner.py
    - mcp_server/tests/test_catalog_phase4_gate_runner.py
  modified: []

key-decisions:
  - "Wave 0 only: named RED cases; no product GREEN"
  - "ready_for_phase_5 false unless unit/service + registration + safety + manifest_verification"
  - "TEST_GROUP=oracle-catalog-tool-test; preserve a67789a historical pointer only"
  - "features.manifest_verification remains false until plan 06"

patterns-established:
  - "SCAFFOLD_CASES structural checks for required RED function names"
  - "derive_ready_for_phase_5 multi-axis fail-closed readiness"
  - "Safety regex uses lookbehind so FORBIDDEN_GROUP=v2 is allowed"

requirements-completed:
  - GATE-01
  - GATE-02
  - GATE-03
  - GATE-04
  - GATE-05
  - GATE-06
  - MANI-05
  - IDEN-08
  - VERI-01
  - VERI-02
  - VERI-03
  - VERI-04
  - VERI-05
  - VERI-06
  - RESE-01
  - RESE-02
  - RESE-03
  - EVID-12
  - EVID-13
  - TEST-08
  - TEST-09

coverage:
  - id: D1
    description: Five Phase 4 RED suite scaffolds collect 52 named cases
    requirement: GATE-01
    verification:
      - kind: unit
        ref: "uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_verify_manifest.py mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py --collect-only -q"
        status: pass
    human_judgment: false
  - id: D2
    description: Phase 4 gate runner defaults ready_for_phase_5 false without proofs
    requirement: TEST-09
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_phase4_gate_runner.py::test_ready_for_phase_5_false_without_proofs"
        status: pass
    human_judgment: false
  - id: D3
    description: Gate unit suite passes (15) with isolation and a67789a pointer
    verification:
      - kind: unit
        ref: "uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_phase4_gate_runner.py -q"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-18
status: complete
---

# Phase 4 Plan 01: Wave 0 RED Scaffolds Summary

**52 collectable Phase 4 RED cases + fail-closed gate runner (`ready_for_phase_5=false`) with no product GREEN**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-18T18:12:37Z
- **Completed:** 2026-07-18T18:20:07Z
- **Tasks:** 2/2
- **Files modified:** 7 created

## Accomplishments

- Five RED modules cover GATE/MANI/IDEN/VERI/RESE/EVID/TEST scaffolds for plans 02–06
- 52 named cases collect cleanly (`--collect-only`); primary bodies `pytest.fail('04 not implemented: ...')`
- `catalog_phase4_gate_runner.py` ports 3B pattern: HEAD/spec/content digests, two-axis safety, CLI `run`/`check`
- `ready_for_phase_5` and `phase_4_complete` default false; require unit/service + registration + safety + `manifest_verification`
- Historical `a67789a` pointer preserved; never query/mutate `oracle-catalog-v2`; test group `oracle-catalog-tool-test` only
- Gate unit suite: 15 passed (fail-closed readiness, sentinel, ownership 0..41, atomic write, scaffolds)

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wave 0 RED suite scaffolds | `febca35` | 5 test modules |
| 2 | Fail-closed gate runner + unit tests | `e9993a2` | runner + unit suite |

## Files Created

| File | Purpose |
|------|---------|
| `mcp_server/tests/test_catalog_gates.py` | GATE-01..06 RED |
| `mcp_server/tests/test_catalog_manifest_read.py` | MANI-05 / IDEN-08 RED |
| `mcp_server/tests/test_catalog_verify_manifest.py` | VERI-01..06 / EVID-13 / TEST-08 RED |
| `mcp_server/tests/test_catalog_resolve_edges.py` | RESE-01..03 RED |
| `mcp_server/tests/test_catalog_evidence_read.py` | EVID-12 / IDEN-08 RED |
| `mcp_server/tests/catalog_phase4_gate_runner.py` | Phase 4 fail-closed gate |
| `mcp_server/tests/test_catalog_phase4_gate_runner.py` | Gate unit proofs |

## Decisions Made

- No product/GREEN implementation in Wave 0; RED remains observable until 04-02..04-06
- `manifest_verification` stays false until plan 06; gate check enforces
- `registration_pass` / `unit_service_pass` hard-false in Wave 0 `run_gate` so readiness cannot flip early
- TEST-09 registration GREEN deferred; Wave 0 only asserts `CATALOG_TOOL_NAMES` symbol presence

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Safety regex false-positive on `FORBIDDEN_GROUP`**
- **Found during:** Task 2 unit tests
- **Issue:** `\b(GROUP|TEST_GROUP)=` matched `FORBIDDEN_GROUP = 'oracle-catalog-v2'`
- **Fix:** lookbehind `(?<![A-Za-z_])` so bare GROUP only; unit assert uses same ban regex
- **Files modified:** `catalog_phase4_gate_runner.py`, `test_catalog_phase4_gate_runner.py`
- **Commit:** `e9993a2`

## TDD Gate Compliance

- RED gate: Task 1 commit `febca35` (`test(04-01): ...`) — five failing product suites
- GREEN for product suites intentionally deferred to plans 02–06
- Gate-runner self-tests pass in this plan (not pure fail stubs) as required by objective

## Known Stubs

Intentional Wave 0 RED stubs (product GREEN later):

| File | Pattern | Reason |
|------|---------|--------|
| five RED modules | `pytest.fail('04 not implemented: ...')` | Wave 0 Nyquist scaffolds |
| `catalog_phase4_gate_runner.run_gate` | `unit_service_pass=False`, `registration_pass=False` | Fail-closed until 04-06 proofs |

## Verification

```text
# Task 1 collect-only
52 tests collected (gates 10, manifest 9, verify 16, resolve 8, evidence 9)

# Task 2 gate unit
15 passed in 0.20s
```

## Next

- 04-02: split gates / capabilities GREEN (`reads_enabled`, HARD_MAX_PAGE_SIZE)
- 04-03..05: manifest/verify/edge/evidence GREEN against RED cases
- 04-06: registration + flip `manifest_verification` after proofs

## Self-Check: PASSED

- FOUND: `mcp_server/tests/test_catalog_gates.py`
- FOUND: `mcp_server/tests/test_catalog_manifest_read.py`
- FOUND: `mcp_server/tests/test_catalog_verify_manifest.py`
- FOUND: `mcp_server/tests/test_catalog_resolve_edges.py`
- FOUND: `mcp_server/tests/test_catalog_evidence_read.py`
- FOUND: `mcp_server/tests/catalog_phase4_gate_runner.py`
- FOUND: `mcp_server/tests/test_catalog_phase4_gate_runner.py`
- FOUND: commit `febca35`
- FOUND: commit `e9993a2`
