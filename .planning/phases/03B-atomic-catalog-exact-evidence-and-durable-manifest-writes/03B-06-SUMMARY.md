---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 06
subsystem: testing
tags: [neo4j, atomic-commit, manifests, gate, evidence, prepare-commit, isolation, re-gate, incomplete]

requires:
  - phase: 03B-03
    provides: exact evidence link store and non-Entity labels
  - phase: 03B-04
    provides: single-tx atomic co-commit writer
  - phase: 03B-05
    provides: recovery/idempotent commit and same-token concurrency
provides:
  - schema-v2 two-axis gate: permanent historical audit vs current execution safety
  - features.manifests static False pre-live; prepare_commit True; manifest_verification False
  - non-live ledger schema v2 with history true, current safety green, ready_for_phase_4 false
  - current live suite source remediated (no forbidden-group param queries) — history not erased
affects:
  - phase-4-public-manifest-verification
  - catalog-capabilities

tech-stack:
  added: []
  patterns:
    - "schema v2 two-axis: Axis A historical audit permanent; Axis B current safety independent"
    - "readiness/CLI gate on current safety only; never on aggregate historical v2 field"
    - "verify_ledger rejects history erasure; allows green current with history true"
    - "static features.manifests=False until post-live flip after coordinator pre-live review"

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
  - "Historical a67789a oracle-catalog-v2 read-only probes remain permanent audit (test_policy; local Neo4j; no corresponding production data)"
  - "Authorized two-axis re-gate: history does not force current safety_checks_pass false"
  - "ready_for_phase_4 still false pre-live (no live re-run; manifests False)"
  - "features.manifests static False until coordinator authorizes live + flip"
  - "Never query/mutate oracle-catalog-v2 again"
  - "Prior permanent hard-block-on-history readiness model superseded; history still cannot be erased"

patterns-established:
  - "SCHEMA_VERSION phase3b-gate-results.v2 with historical_audit object"
  - "derive_ready_for_phase_4 / derive_cli_exit_code gate Axis B only"
  - "check_manifests_feature_false structural check pre-live"

requirements-completed: []

duration: n/a
completed: null
status: incomplete
---

# Phase 03B Plan 06: Live Atomic Co-Commit Gate Summary

**INCOMPLETE / PRE-LIVE.** Authorized two-axis re-gate applied. Historical audit remains true. Current safety axis independent of history. Plan not complete. Phase 4 not opened. No Neo4j in this wave.

## Status: incomplete (pre-live review)

Do not mark requirements complete. Do not open Phase 4. Do not flip `features.manifests` until coordinator pre-live review and accepted live proof.

## Two-axis safety model (schema v2)

| Axis | Fields | Permanence | Gates readiness/CLI? |
|------|--------|------------|----------------------|
| A — Historical audit | `historical_oracle_catalog_v2_queried=true`; aggregate `oracle_catalog_v2_queried=true`; commit `a67789a`; class=`test_policy`; scope=`local_neo4j_no_corresponding_data` | Permanent; erasure rejected by `verify_ledger` | **No** |
| B — Current safety | `safety_no_probe`, canary, `clear_graph`, `current_source_v2_param_query` → `safety_checks_pass` | Current source/live execution only | **Yes** |

History does **not** force Axis B false. Readiness/CLI never gate on aggregate historical field alone.

## Historical violation (permanent audit)

| Field | Value |
|-------|-------|
| Event | Initial 03B-06 live suite read-only `MATCH` counts against `oracle-catalog-v2` |
| Commit | `a67789a` |
| Class | `test_policy` (local test-policy violation; no production/second-schema data) |
| Scope | `local_neo4j_no_corresponding_data` |
| Disposition | Permanent Axis A audit; never query/mutate `oracle-catalog-v2` again |
| Current source | Live suite remediated — no forbidden-group param queries; TrackingDriver spy |

## Unaccepted prior claims

Rejected:

- `ready_for_phase_4=true` under incomplete re-gate / no accepted live
- Erasing `oracle_catalog_v2_queried` / "zero historical queries"
- `features.manifests=True` before post-live coordinator flip
- Permanent hard-block model that forced `safety_checks_pass=false` solely from history (superseded by two-axis; history still permanent audit)
- Completed requirements list as phase-accepted

### Live suite evidence (exact known)

| Claim | Status |
|-------|--------|
| Coordinator pre-remediation run | **10 passed / 1 deselected** (independently known) |
| Later agent-reported 11/11 after adversarial suite rewrite | **agent-reported only; not independently accepted** |
| Use as Phase 4 transition evidence | **not accepted yet** — needs coordinator pre-live review + re-run under two-axis gate |

Do not restate "11/11 results" as accepted proof.

## Current remediated source safety (Axis B)

- Live suite hardcodes `oracle-catalog-tool-test` only.
- TrackingDriver rejects non-tool-test group params.
- Static ban on forbidden-group Cypher params in current source scan.
- Scoped teardown by created UUID/batch allowlist (no whole-group delete).
- `clear_graph` not called; canary not present in suite source.
- Gate forces `CATALOG_INT_REQUIRED=1` + `CATALOG_CEILING_SMOKE=1` on live argv **when** live is run — **this re-gate wave does not query Neo4j**.

## Capability flags (pre-live)

| Flag | Value | Reason |
|------|-------|--------|
| `prepare_commit` | `True` | Prior plan live proof retained |
| `manifests` | `False` | Pre-live; flip only after accepted live + coordinator |
| `manifest_verification` | `False` | Phase 4 public tools not opened |

## Edge resolution rows 21/22

- **21 isolation:** current source does not param-query v2; historical probes permanently set Axis A audit; current safety independent.
- **22 capability-flip:** `features.manifests` remains static `False` pre-live; structural check `check_manifests_feature_false`; Phase 4 not opened.

## Gate ledger

### Non-live preflight (prior)

- `require_neo4j=false`: CLI exit 0 = local preflight only (`pre_live_only=true`); not completion.

### Live preflip (`--require-neo4j`, manifests still False)

Exact run bound to content HEAD before ledger rebind:

| Field | Value |
|-------|-------|
| live suite | **10 passed, 1 deselected, 0 failed** (`-m integration`; sync guard deselected) |
| live wall time (suite alone) | **6.73s** then **6.69s** under gate |
| full gate wall time | **13s** |
| `live_neo4j_atomic_proof` | pass |
| `live_neo4j_atomic_proof_pass` | true |
| `safety_checks_pass` | true |
| `current_source_v2_param_query` | false |
| `canary_executed` / `clear_graph_called` | false / false |
| historical / aggregate `oracle_catalog_v2_queried` | true (Axis A audit only) |
| `manifests` | **false** (sole readiness blocker after live green) |
| `ready_for_phase_4` / `phase_3b_complete` | **false** / **false** |
| `pre_live_only` | false |
| CLI exit under `--require-neo4j` | **1** (expected: ready false while manifests false) |
| `verify_ledger` | ok at evaluated HEAD (exact) |
| TrackingDriver rejects | none observed |
| Neo4j target | local `graphiti-catalog-neo4j-test` bolt `localhost:17687`; group `oracle-catalog-tool-test` only |

Signal names:

- `local_gate_pass` = mandatory non-live command checks only. Not overall success.
- `safety.safety_checks_pass` = current axis only (not forced false by history).
- `oracle_catalog_v2_queried` = aggregate audit (history OR current dirty).
- `ready_for_phase_4` / `phase_3b_complete` = false until live+manifests under require-neo4j.

**Stopped before manifests flip.**

## Task Commits (historical; plan not complete)

| Task | Name | Commit | Note |
|------|------|--------|------|
| 1 | Live Neo4j atomic co-commit suite | a67789a | **introduced historical v2 read-only probes** |
| 1b | Dynamic-import IDE pyright safety | 49e2e93 | |
| 2 | Manifests flip + edge + gate (false green) | 3045228 | overclaim |
| R1 | Adversarial harden live suite | cc80d8e | source clean; history remains |
| R2 | Gate safety/ceiling/edge ownership | dabb972 | overclaim readiness |
| R3 | False-green ledger rebinds | c650da9, 30ef824 | unaccepted |
| T1 | Truthful historical block remediation | 056f960 | permanent hard-block model (superseded) |
| T2 | Authorized two-axis re-gate schema v2 | (this wave) | history audit; current safety independent; pre-live |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Critical correctness] Two-axis re-gate after authorized clarification**
- **Found during:** Coordinator/user authorization after permanent hard-block wave
- **Issue:** Hard-block model treated local test-policy history as permanent readiness fail; user clarified no production data and authorized re-gate separating audit from current safety.
- **Fix:** `SCHEMA_VERSION` v2; permanent historical_audit; `derive_safety_ledger` current-independent; readiness/CLI Axis B only; `verify_ledger` rejects erasure without forcing ready false; unit suite for history/current cases; manifests remain False pre-live.
- **Files modified:** gate runner, unit tests, edge resolution, SUMMARY, PATTERNS, VALIDATION, GATE-RESULTS
- **Commit:** (this wave)

## Known Stubs

None intentional product stubs. Live proofs exist in source but are **unaccepted** for Phase 4 pending coordinator pre-live review.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: historical_group_probe | live suite history a67789a | Past read-only queries to `oracle-catalog-v2` remain permanent audit; never query/mutate again |

## Self-Check

- FOUND: `mcp_server/src/services/catalog_capabilities.py` (`'manifests': False`)
- FOUND: schema v2 two-axis constants/functions in `catalog_phase3b_gate_runner.py`
- FOUND: SUMMARY `status: incomplete`
- FOUND: edge rows 21/22 two-axis wording
- No Neo4j / live re-run in this re-gate wave
- Plan **not** marked complete; requirements-completed empty
- No shared STATE.md / ROADMAP.md updates (orchestrator-owned; do not advance)
