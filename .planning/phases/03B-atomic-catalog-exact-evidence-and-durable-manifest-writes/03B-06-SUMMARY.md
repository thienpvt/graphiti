---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 06
subsystem: testing
tags: [neo4j, atomic-commit, manifests, gate, evidence, prepare-commit, isolation, blocked]

requires:
  - phase: 03B-03
    provides: exact evidence link store and non-Entity labels
  - phase: 03B-04
    provides: single-tx atomic co-commit writer
  - phase: 03B-05
    provides: recovery/idempotent commit and same-token concurrency
provides:
  - truthful blocked Phase 3B gate: historical oracle-catalog-v2 read-only probes recorded permanently
  - features.manifests static False while phase blocked; prepare_commit True; manifest_verification False
  - non-live ledger regeneration with ready_for_phase_4=false and oracle_catalog_v2_queried=true
  - current live suite source remediated (no forbidden-group param queries) — history not erased
affects:
  - phase-4-public-manifest-verification
  - catalog-capabilities

tech-stack:
  added: []
  patterns:
    - "historical hard gate: oracle_catalog_v2_queried true cannot be cleared by source remediation"
    - "top-level ledger safety fields copy derived safety only (never constant false)"
    - "static features.manifests=False while phase blocked"
    - "verify_ledger accepts truthful blocked ledger; rejects false-green erasure"

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
  - "Historical a67789a read-only oracle-catalog-v2 probes are permanent; remediation cannot erase phase history"
  - "ready_for_phase_4 remains false; Phase 4 transition not opened"
  - "features.manifests static False under historical block; prepare_commit True; manifest_verification False"
  - "Top-level canary/v2/clear_graph fields mirror derive_safety_ledger only"
  - "Live Neo4j re-runs and merge/primary advance forbidden until coordinator re-opens gate"
  - "Prior green readiness claims (ready_for_phase_4=true, zero historical v2 queries) are unaccepted"

patterns-established:
  - "HISTORICAL_ORACLE_CATALOG_V2_QUERIED constant forces safety ledger truth"
  - "check_manifests_feature_false structural check while blocked"
  - "verify_ledger requires v2 true and ready false under historical gate"

requirements-completed: []

duration: n/a
completed: null
status: blocked
---

# Phase 03B Plan 06: Live Atomic Co-Commit Gate Summary

**BLOCKED / INCOMPLETE.** Historical hard gate: initial live suite (commit `a67789a`) queried `oracle-catalog-v2` read-only for before/after isolation counts. Remediation of current source cannot erase that. `ready_for_phase_4=false`. `features.manifests=False`. No Phase 4 transition.

## Status: blocked

This plan is **not complete**. Do not mark requirements complete. Do not open Phase 4.

## Historical violation (permanent)

| Field | Value |
|-------|-------|
| Event | Initial 03B-06 live suite read-only `MATCH` counts against `oracle-catalog-v2` |
| Commit | `a67789a` (and subsequent false-green remediation path) |
| Disposition | Permanent hard gate: `oracle_catalog_v2_queried=true` in derived safety + top-level ledger |
| Current source | Live suite rewritten (`cc80d8e`+) — no forbidden-group param queries; TrackingDriver spy |
| Effect | `safety_checks_pass=false`; `ready_for_phase_4=false` always under this history |

## Unaccepted prior claims

The following claims from earlier false-green SUMMARY/ledger revisions are **rejected**:

- `ready_for_phase_4=true`
- `oracle_catalog_v2_queried=false` / "zero historical queries"
- `features.manifests=True` after "proof"
- Completed requirements list (PLAN-13..TEST-07) as phase-accepted
- Phase 4 readiness / green gate under `--require-neo4j`

Live 11/11 results after adversarial remediation are **not accepted** as Phase 4 transition evidence because the historical isolation violation remains.

## Current remediated source safety (does not clear history)

- Live suite hardcodes `oracle-catalog-tool-test` only.
- TrackingDriver rejects non-tool-test group params.
- Static ban on forbidden-group Cypher params in current source scan.
- Scoped teardown by created UUID/batch allowlist (no whole-group delete).
- `clear_graph` not called; canary not present in suite source.
- Gate forces `CATALOG_INT_REQUIRED=1` + `CATALOG_CEILING_SMOKE=1` on live argv **when** live is run — **this remediation run does not query Neo4j**.

## Capability flags (truthful blocked)

| Flag | Value | Reason |
|------|-------|--------|
| `prepare_commit` | `True` | Prior plan live proof retained |
| `manifests` | `False` | Historical v2 hard gate blocks flip |
| `manifest_verification` | `False` | Phase 4 public tools not opened |

## Edge resolution rows 21/22

- **21 isolation:** current source does not param-query v2; historical probes permanently set ledger `oracle_catalog_v2_queried=true` and block readiness.
- **22 capability-flip:** `features.manifests` remains static `False`; structural check is `check_manifests_feature_false`; Phase 4 not opened.

## Gate ledger (non-live)

- Regenerated with `require_neo4j=false` (live skipped).
- `ready_for_phase_4=false`
- `oracle_catalog_v2_queried=true` (top-level + `safety.*`)
- `manifests=false`
- `verify_ledger` must pass on this truthful blocked ledger.
- No Neo4j connection during remediation.

## Task Commits (historical; plan not complete)

| Task | Name | Commit | Note |
|------|------|--------|------|
| 1 | Live Neo4j atomic co-commit suite | a67789a | **introduced historical v2 read-only probes** |
| 1b | Dynamic-import IDE pyright safety | 49e2e93 | |
| 2 | Manifests flip + edge + gate (false green) | 3045228 | overclaim |
| R1 | Adversarial harden live suite | cc80d8e | source clean; history remains |
| R2 | Gate safety/ceiling/edge ownership | dabb972 | overclaim readiness |
| R3 | False-green ledger rebinds | c650da9, 30ef824 | unaccepted |
| T1 | Truthful historical block remediation | (this wave) | manifests false; ledger blocked |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Critical correctness] Historical isolation violation is permanent**
- **Found during:** Coordinator hard-gate after false PLAN COMPLETE
- **Issue:** Remediation path claimed `oracle_catalog_v2_queried=false` and `ready_for_phase_4=true` after source cleanup, erasing phase history.
- **Fix:** `HISTORICAL_ORACLE_CATALOG_V2_QUERIED=True`; derive_safety always sets v2 true; top-level mirrors derived; verify_ledger requires v2 true + ready false; manifests static False; SUMMARY blocked.
- **Files modified:** gate runner, capabilities, unit tests, edge resolution, SUMMARY, GATE-RESULTS
- **Commit:** (this wave)

## Known Stubs

None intentional product stubs. Live proofs exist in source but are **unaccepted** for Phase 4.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: historical_group_probe | live suite history a67789a | Past read-only queries to production-adjacent group `oracle-catalog-v2` permanently block phase readiness |

## Self-Check

- FOUND: `mcp_server/src/services/catalog_capabilities.py` (`'manifests': False`)
- FOUND: historical hard gate constants in `catalog_phase3b_gate_runner.py`
- FOUND: SUMMARY `status: blocked`
- FOUND: edge rows 21/22 updated for history + manifests false
- No Neo4j / live re-run in this remediation wave
- Plan **not** marked complete; requirements-completed empty
- No shared STATE.md / ROADMAP.md updates (orchestrator-owned; do not advance)
