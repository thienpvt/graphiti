---
phase: 03A-immutable-prepare-commit-control-plane
plan: 06
subsystem: catalog-prepare-gate
tags:
  - prepare-commit
  - neo4j-int
  - phase3a-gate
  - d-29
  - fail-closed
dependency_graph:
  requires:
    - 03A-01
    - 03A-02
    - 03A-03
    - 03A-04
    - 03A-05
  provides:
    - live-immutable-prepare-proof
    - features.prepare_commit=true
    - ready_for_phase_3b
    - 03A-EDGE-PROBE-RESOLUTION 34/34
  affects:
    - Phase 3B unlock
tech-stack:
  added: []
  patterns:
    - fail-closed gate runner (shell=False argv)
    - D-29 flip only after live proof + re-test
    - digest-only plan_token storage
key-files:
  created:
    - mcp_server/tests/test_catalog_prepare_neo4j_int.py
    - mcp_server/tests/catalog_phase3a_gate_runner.py
    - mcp_server/tests/run_phase3a_gate.py
    - mcp_server/tests/test_catalog_phase3a_gate_runner.py
    - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json
    - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-PHASE3A-GATE.md
    - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-EDGE-PROBE-RESOLUTION.json
  modified:
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/services/catalog_capabilities.py
    - mcp_server/tests/test_catalog_capabilities.py
    - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-VALIDATION.md
decisions:
  - "D-29: prepare_commit flipped true only after live 9/9 immutable proof"
  - "ready_for_phase_3b requires local_gate_pass + live proof under --require-neo4j + safety ledger"
  - "Discard CAS always expected_from=PREPARED for idempotent DISCARDED path"
  - "Isolated worktree: STATE.md/ROADMAP.md left to orchestrator"
metrics:
  duration: session-continued
  completed: 2026-07-18
status: complete
---

# Phase 03A Plan 06: Live Immutable Proof + Gate Authority Summary

Live Neo4j multi-chunk prepare proof on `oracle-catalog-tool-test`, D-29 `features.prepare_commit=true` after re-test, fail-closed Phase 3A gate with 34/34 probe resolution and `ready_for_phase_3b=true`.

## What Was Built

### Task 1 — Live Neo4j immutable proof
- `test_catalog_prepare_neo4j_int.py`: 9 integration tests (multi-chunk restart/fresh session, zero domain labels, capacity+discard, commit→COMMITTING, discard idempotent, expiry, digest-only token, group isolation).
- Product fix: discard CAS always `expected_from=PREPARED` so already-DISCARDED is idempotent success.

### Task 2 — D-29 flip + gate + 34/34
- `catalog_capabilities.features.prepare_commit=True` after live green; manifests false; page size 0.
- `catalog_phase3a_gate_runner.py` / `run_phase3a_gate.py` / unit tests: SCHEMA `phase3a-gate-results.v1`, `--require-neo4j`, fail-closed `derive_ready_for_phase_3b`.
- `03A-EDGE-PROBE-RESOLUTION.json`: 34 unique `row_index` 0..33, `no_silent_drop=true`.
- Applied ledger: local+live+safety green; `ready_for_phase_3b=true`; nyquist validated.

## Gate Outcomes (final product HEAD pre-docs)

| Field | Value |
|-------|-------|
| local_gate_pass | true |
| live_neo4j_immutable_proof_pass | true |
| prepare_commit | true |
| ready_for_phase_3b | true |
| canary_executed | false |
| oracle_catalog_v2_queried | false |
| clear_graph_called | false |
| no_domain_write_on_prepare | true |
| no_external_call_on_commit | true |
| probe resolution | 34/34 |

## Commits

| Hash | Message |
|------|---------|
| 5304053 | feat(03A-06): live Neo4j immutable prepare proof + discard CAS fix |
| 88c1e20 | feat(03A-06): D-29 prepare_commit flip + Phase 3A fail-closed gate |
| 8cf7250 | fix(03A-06): match store method names in control_plane check |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Discard idempotency CAS expected_from**
- **Found during:** Task 1 live suite
- **Issue:** Service set `expected_from=DISCARDED` on second discard; store CAS table has no DISCARDED→DISCARDED edge
- **Fix:** Always `expected_from=PLAN_STATE_PREPARED` for discard
- **Files modified:** `mcp_server/src/services/catalog_service.py`
- **Commit:** 5304053

**2. [Rule 2 - Missing critical] validate_spec blocked ruff paths listing live module**
- **Found during:** Task 2 gate unit tests
- **Issue:** Non-live specs rejected any argv ending in integration module; ruff/pyright list it as lint path
- **Fix:** Only enforce pytest collect ban for non-live/non-tool kinds
- **Files modified:** `catalog_phase3a_gate_runner.py`
- **Commit:** 88c1e20

**3. [Rule 1 - Bug] control_plane_present used wrong store method names**
- **Found during:** full gate run
- **Issue:** Checked `create_prepared_plan` / `load_prepared_plan` which do not exist
- **Fix:** Match real symbols `create_prepared_plan_with_chunks`, `load_prepared_plan_by_token_digest`
- **Files modified:** `catalog_phase3a_gate_runner.py`
- **Commit:** 8cf7250

## Safety

- GROUP `oracle-catalog-tool-test` only; never `oracle-catalog-v2` write target
- No canary, no `clear_graph`, no deploy
- STATE.md / ROADMAP.md not modified in this worktree (orchestrator-owned)

## Known Stubs

None.

## Self-Check: PASSED

- All required artifacts present
- Commits 5304053, 88c1e20, 8cf7250 present
- prepare_commit true; manifests false; page size 0
- EDGE-PROBE-RESOLUTION 34/34
- GATE-RESULTS ready_for_phase_3b=true with safety ledger clean
