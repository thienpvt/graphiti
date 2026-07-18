---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 06
subsystem: testing
tags: [neo4j, atomic-commit, manifests, gate, evidence, prepare-commit]

requires:
  - phase: 03B-03
    provides: exact evidence link store and non-Entity labels
  - phase: 03B-04
    provides: single-tx atomic co-commit writer
  - phase: 03B-05
    provides: recovery/idempotent commit and same-token concurrency
provides:
  - live Neo4j atomic co-commit suite green under CATALOG_INT_REQUIRED=1
  - features.manifests static True after proof (manifest_verification false)
  - Phase 3B fail-closed gate with ready_for_phase_4 under --require-neo4j
  - 24/24 edge probe resolution map
affects:
  - phase-4-public-manifest-verification
  - catalog-capabilities

tech-stack:
  added: []
  patterns:
    - "static capability flip after live gate proof (no runtime .planning read)"
    - "importlib/getattr live suite for IDE-root pyright safety"
    - "ledger-only-child HEAD binding for gate results"

key-files:
  created:
    - mcp_server/tests/test_catalog_commit_neo4j_int.py
    - .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-EDGE-PROBE-RESOLUTION.json
    - .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-GATE-RESULTS.json
    - .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-06-SUMMARY.md
  modified:
    - mcp_server/src/services/catalog_capabilities.py
    - mcp_server/tests/catalog_phase3b_gate_runner.py
    - mcp_server/tests/test_catalog_phase3b_gate_runner.py
    - mcp_server/tests/test_catalog_capabilities.py

key-decisions:
  - "features.manifests flipped via static source True only after live+unit proof (D-33)"
  - "manifest_verification remains False for Phase 4"
  - "live suite uses dynamic imports only (Wave 0 IDE pyright pattern)"
  - "configured-ceiling default smoke is 20 entities; full 500 opt-in via CATALOG_CEILING_SMOKE"

patterns-established:
  - "Live fault inject via monkeypatch store.write_evidence_links mid-tx"
  - "Gate check_manifests_feature_true ignores comment-only GATE-RESULTS mentions"

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
    description: Live single-tx co-commit of domain+evidence+manifest+batch+plan COMMITTED
    requirement: PLAN-13
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_single_tx_co_commit
        status: pass
    human_judgment: false
  - id: D2
    description: Mid-write fault leaves zero partial success artifacts
    requirement: PLAN-14
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_mid_write_fault_zero_partial
        status: pass
    human_judgment: false
  - id: D3
    description: Identical replay and same-token concurrency produce one logical batch
    requirement: PLAN-15
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_identical_replay
        status: pass
    human_judgment: false
  - id: D4
    description: Same-token concurrent commits yield one manifest hash
    requirement: PLAN-16
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_same_token_concurrency
        status: pass
    human_judgment: false
  - id: D5
    description: Evidence/manifest control labels exclude Entity; Entity search interop holds
    requirement: TEST-07
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_entity_search_interop
        status: pass
    human_judgment: false
  - id: D6
    description: features.manifests true after gate; verification false; prepare_commit true
    requirement: MANI-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_features_phase_truthful
        status: pass
    human_judgment: false
  - id: D7
    description: Fail-closed Phase 3B gate ready_for_phase_4 under require-neo4j
    requirement: TEST-06
    verification:
      - kind: other
        ref: mcp_server/tests/catalog_phase3b_gate_runner.py --require-neo4j
        status: pass
    human_judgment: false

duration: 90min
completed: 2026-07-18
status: complete
---

# Phase 03B Plan 06: Live Atomic Co-Commit Gate Summary

**Live Neo4j single-tx co-commit proven; features.manifests static-true; ready_for_phase_4 fail-closed gate green under require-neo4j.**

## Performance

- **Duration:** ~90 min
- **Started:** 2026-07-18T00:00:00Z
- **Completed:** 2026-07-18T00:00:00Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Converted live scaffold into 10 genuine Neo4j proofs (happy co-commit, mid-write rollback, replay, concurrency, search interop, non-Entity control labels, isolation, ceiling smoke, unchanged membership).
- Dynamic importlib/getattr live suite for IDE-root pyright safety (Wave 0 pattern).
- Static `features.manifests=True` after proof; `manifest_verification=False`; `prepare_commit=True`.
- Gate runner checks `manifests_feature_true` + `edge_resolution_complete`; 24/24 edge map published.
- Full gate with live Neo4j and fail-closed `ready_for_phase_4=true`.

## Task Commits

| Task | Name | Commit |
|------|------|--------|
| 1 | Live Neo4j atomic co-commit suite | a67789a |
| 1b | Dynamic-import IDE pyright safety | 49e2e93 |
| 2 | Manifests flip + edge resolution + gate checks | 3045228 |

## Live / Gate Proof

- Live suite: `CATALOG_INT_REQUIRED=1` → **10 passed** against `bolt://localhost:17687`, group `oracle-catalog-tool-test` only.
- Focused unit: 103 passed (manifest/evidence/atomic/recovery/concurrency/gate/capabilities).
- Scoped ruff: pass. Scoped project pyright: 0 errors.
- Gate: `--require-neo4j` → `ready_for_phase_4=true` (see 03B-GATE-RESULTS.json).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] clear_graph self-match assertion**
- **Found during:** Task 1
- **Issue:** Assertion string contained `clear_graph(` so the source scan always matched itself.
- **Fix:** Split name construction: `clear_fn = 'clear' + '_graph'`.
- **Files modified:** `mcp_server/tests/test_catalog_commit_neo4j_int.py`
- **Commit:** a67789a

**2. [Rule 2 - Missing critical functionality] IDE-root import safety**
- **Found during:** Task 1 (coordinator)
- **Issue:** Static product imports risk IDE-root missing-import diagnostics on gate PYRIGHT_PATHS.
- **Fix:** importlib/getattr pattern; ban static product/fixture imports in source guard.
- **Files modified:** `mcp_server/tests/test_catalog_commit_neo4j_int.py`
- **Commit:** 49e2e93

**3. [Rule 1 - Bug] manifests feature check false-positive on comments**
- **Found during:** Task 2
- **Issue:** Comment text `GATE-RESULTS` in capabilities tripped the no-ledger-read check.
- **Fix:** Scan non-comment code lines only for forbidden ledger tokens.
- **Files modified:** `mcp_server/tests/catalog_phase3b_gate_runner.py`
- **Commit:** 3045228

## Known Stubs

None.

## Threat Flags

None new — no public Phase 4 tools; control labels remain non-Entity; group isolation preserved.

## Self-Check: PASSED

- FOUND: `mcp_server/tests/test_catalog_commit_neo4j_int.py`
- FOUND: `mcp_server/src/services/catalog_capabilities.py` (`'manifests': True`)
- FOUND: `mcp_server/tests/catalog_phase3b_gate_runner.py`
- FOUND: `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-EDGE-PROBE-RESOLUTION.json`
- FOUND: `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-GATE-RESULTS.json` (`ready_for_phase_4=true`)
- FOUND commits: `a67789a`, `49e2e93`, `3045228`
- Gate verify_ledger: ok (exact HEAD at proof run; docs commit may be ledger-only-child)
- Live: 10/10 pass; focused unit 103 pass; scoped ruff/pyright pass
- Safety: canary=false, v2_queried=false, clear_graph=false
- No shared STATE.md/ROADMAP.md updates (orchestrator-owned)
