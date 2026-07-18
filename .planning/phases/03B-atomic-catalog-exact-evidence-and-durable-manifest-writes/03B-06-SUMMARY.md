---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 06
subsystem: testing
tags: [neo4j, atomic-commit, manifests, gate, evidence, prepare-commit, isolation]

requires:
  - phase: 03B-03
    provides: exact evidence link store and non-Entity labels
  - phase: 03B-04
    provides: single-tx atomic co-commit writer
  - phase: 03B-05
    provides: recovery/idempotent commit and same-token concurrency
provides:
  - live Neo4j atomic co-commit suite green under CATALOG_INT_REQUIRED=1 and CATALOG_CEILING_SMOKE=1
  - features.manifests static True after proof (manifest_verification false)
  - Phase 3B fail-closed gate with ready_for_phase_4 under --require-neo4j
  - 24/24 edge probe resolution with ownership/symbol validation
  - isolation without querying oracle-catalog-v2
affects:
  - phase-4-public-manifest-verification
  - catalog-capabilities

tech-stack:
  added: []
  patterns:
    - "static capability flip after live gate proof (no runtime .planning read)"
    - "importlib/getattr live suite for IDE-root pyright safety"
    - "TrackingDriver spy rejects any group_id != oracle-catalog-tool-test"
    - "gate live path forces CATALOG_CEILING_SMOKE=1 for real max=500"
    - "safety ledger derived from live suite source evidence, not constants"
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
  - "never query/mutate oracle-catalog-v2; isolation via TrackingDriver + static source scan"
  - "gate --require-neo4j forces CATALOG_CEILING_SMOKE=1 so live ceiling is configured max 500"
  - "MANI-07 requires committed_unchanged>=1 and durable chunk reassembly with projected_status=unchanged"
  - "terminal CAS fault injects only COMMITTING→COMMITTED after manifest write"

patterns-established:
  - "Live fault inject via monkeypatch store.write_evidence_links mid-tx"
  - "Second live fault: cas_plan_state terminal COMMITTING→COMMITTED only"
  - "Gate check_manifests_feature_true ignores comment-only GATE-RESULTS mentions"
  - "Production search interop via graphiti_core.search + NODE_HYBRID_SEARCH_RRF"
  - "Scoped teardown by created batch_id/plan_uuid/entity_uuid allowlist"

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
    description: Live single-tx co-commit; claim + exactly one success write tx after claim
    requirement: PLAN-13
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_single_tx_co_commit
        status: pass
    human_judgment: false
  - id: D2
    description: Mid-write evidence fault leaves zero partial success artifacts
    requirement: PLAN-14
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_mid_write_fault_zero_partial
        status: pass
    human_judgment: false
  - id: D2b
    description: Post-manifest terminal CAS fault rolls back domain/evidence/manifest; plan stays COMMITTING
    requirement: PLAN-14
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_post_manifest_fault_zero_partial
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
    description: Evidence/manifest control labels exclude Entity; Graphiti search interop holds
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
  - id: D8
    description: MANI-07 unchanged membership reassembly with projected_status and content hash
    requirement: MANI-07
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_unchanged_membership_in_manifest
        status: pass
    human_judgment: false
  - id: D9
    description: Configured ceiling 500 under gate-forced CATALOG_CEILING_SMOKE=1
    requirement: PLAN-13
    verification:
      - kind: integration
        ref: mcp_server/tests/test_catalog_commit_neo4j_int.py#test_live_configured_ceiling_smoke
        status: pass
    human_judgment: false

duration: 180min
completed: 2026-07-18
status: complete
---

# Phase 03B Plan 06: Live Atomic Co-Commit Gate Summary

**Live Neo4j single-tx co-commit proven under hardened isolation; features.manifests static-true; ready_for_phase_4 fail-closed gate green under require-neo4j after adversarial remediation.**

## Performance

- **Duration:** ~180 min (includes adversarial remediation)
- **Started:** 2026-07-18
- **Completed:** 2026-07-18
- **Tasks:** 2/2 (+ remediation wave)
- **Files modified:** 8

## Accomplishments

- 11 live Neo4j proofs: co-commit, mid-write rollback, post-manifest/terminal-CAS rollback, replay, concurrency, Graphiti search interop, non-Entity control labels, isolation spy, ceiling 500, unchanged membership reassembly, static group ban.
- Zero live queries/mutations of `oracle-catalog-v2`; TrackingDriver rejects any non-tool-test group param; safety ledger derived from suite source evidence.
- Gate forces `CATALOG_INT_REQUIRED=1` + `CATALOG_CEILING_SMOKE=1` on live argv; edge 24/24 ownership/symbol/non-placeholder validated; rows 12–13 plan ownership corrected.
- Static `features.manifests=True` after proof; `manifest_verification=False`; `prepare_commit=True`.
- Scoped teardown by created UUID/batch allowlist only (no whole-group DETACH DELETE).

## Task Commits

| Task | Name | Commit |
|------|------|--------|
| 1 | Live Neo4j atomic co-commit suite | a67789a |
| 1b | Dynamic-import IDE pyright safety | 49e2e93 |
| 2 | Manifests flip + edge resolution + gate checks | 3045228 |
| R1 | Adversarial harden live suite | cc80d8e |
| R2 | Gate safety/ceiling/edge ownership | dabb972 |

## Live / Gate Proof

- Live suite: `CATALOG_INT_REQUIRED=1` + `CATALOG_CEILING_SMOKE=1` → **11 passed** against `bolt://localhost:17687`, group `oracle-catalog-tool-test` only.
- Focused unit gate/capabilities: 34 passed; full focused suite under gate: pass.
- Scoped ruff: pass. Scoped project pyright: 0 errors.
- Gate: `--require-neo4j` → `ready_for_phase_4=true` (see 03B-GATE-RESULTS.json).
- Safety: canary=false, oracle_catalog_v2_queried=false, clear_graph_called=false.

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

**4. [Rule 1/2 - Adversarial remediation] Forbidden-group probes and weak proofs**
- **Found during:** Post-completion adversarial review
- **Issue:** Prior suite queried `oracle-catalog-v2` for before/after counts; vacuous MANI-07; Cypher-only search; ceiling optional 20; no post-manifest fault; constant safety ledger; weak edge ownership.
- **Fix:** Full suite rewrite with TrackingDriver, scoped teardown, Graphiti search, terminal CAS fault, strict MANI-07 reassembly, gate-forced ceiling 500, evidence-derived safety, edge ownership/symbol checks, rows 12–13 ownership fix, Oracle graph_key grammar.
- **Files modified:** `mcp_server/tests/test_catalog_commit_neo4j_int.py`, `mcp_server/tests/catalog_phase3b_gate_runner.py`, `03B-EDGE-PROBE-RESOLUTION.json`
- **Commits:** cc80d8e, dabb972

## Known Stubs

None.

## Threat Flags

None new — no public Phase 4 tools; control labels remain non-Entity; group isolation preserved without forbidden-group probes.

## Self-Check: PASSED

- FOUND: `mcp_server/tests/test_catalog_commit_neo4j_int.py`
- FOUND: `mcp_server/src/services/catalog_capabilities.py` (`'manifests': True`)
- FOUND: `mcp_server/tests/catalog_phase3b_gate_runner.py`
- FOUND: `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-EDGE-PROBE-RESOLUTION.json`
- FOUND: `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-GATE-RESULTS.json` (`ready_for_phase_4=true`)
- FOUND commits: `a67789a`, `49e2e93`, `3045228`, `cc80d8e`, `dabb972`
- Live: 11/11 pass with ceiling 500; scoped ruff/pyright 0
- Safety: canary=false, v2_queried=false, clear_graph=false (source-evidence-derived)
- No shared STATE.md/ROADMAP.md updates (orchestrator-owned)
