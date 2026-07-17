# Phase 1 Gate Report

**Date:** 2026-07-18  
**Consumer:** Phase 2 entry checklist  
**Authority:** CONT-01..08, IDEN-01..13, SAFE-05, SAFE-08, TEST-01, TEST-03; Wave 5 plan 01-05  
**Rule:** `ready_for_phase_2` is true only when focused pytest, scoped Ruff, scoped Pyright, safety invariants, and edge-probe 53/53 all pass, and no new store/control-plane write path was introduced in Phase 1. Skip is never converted to pass. Phase 0 canary-script baseline fails remain recorded noise, not relabeled pass.

## 1. Artifact checklist

| Artifact | Status | Path |
|----------|--------|------|
| `01-01-SUMMARY.md` | present | `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-01-SUMMARY.md` |
| `01-02-SUMMARY.md` | present | `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-02-SUMMARY.md` |
| `01-03-SUMMARY.md` | present | `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-03-SUMMARY.md` |
| `01-04-SUMMARY.md` | present | `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-04-SUMMARY.md` |
| `01-EDGE-PROBE.json` | present | `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-EDGE-PROBE.json` |
| `01-VALIDATION.md` | present | `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-VALIDATION.md` |
| `01-PHASE1-GATE.md` (this file) | present | `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-PHASE1-GATE.md` |

Missing: none.

## 2. Safety invariants

All must be true for readiness.

| Invariant | Value | Evidence |
|-----------|-------|----------|
| `canary_executed` | false | Plan 01-05 history; no invoke of `scripts/run_catalog_canary_batch.py` or canary runner |
| `oracle_catalog_v2_queried` | false | No Neo4j live probe; no query/mutation of `oracle-catalog-v2` |
| `no_new_store_or_control_plane_write_path` | true | Phase 1 product surface is strict models, graph-key grammar, versioned identity helpers, SAFE-08 converter, CatalogSafeFastMCP validation rewrite only — no prepare/commit control-plane path, no new store write API |
| `unrelated_dirty_files_committed` | false | Commit allowlist = phase planning artifacts + intentional STATE/ROADMAP/REQUIREMENTS |
| `remote_push_merge_deploy_tag` | false | SAFE-13 ban; no remote ops |

## 3. Check ledger (focused Phase 1)

Recorded at gate write. Statuses from real exit codes — fail/skip not reclassified.

| name | status | exit_code | first_failure_id / note |
|------|--------|-----------|-------------------------|
| `focused_pytest` | **pass** | 0 | null — 414 passed in 1.99s |
| `scoped_ruff` | **pass** | 0 | null — All checks passed |
| `scoped_pyright` | **pass** | 0 | null — 0 errors, 0 warnings |
| `catalog_neo4j_int` | **skip** | null | default skip; Neo4j not safely available without live probe; nonblocking |
| `safety_invariants` | **pass** | n/a | canary/live-group flags false; write-path invariant true |
| `edge_probe` | **pass** | n/a | applicable=53 resolved=53 unresolved=0 null_dispositions=0 |

**Commands (repo root):**

1. `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_store_unit.py -q --tb=line` → exit 0, 414 passed
2. `uv run --project mcp_server ruff check mcp_server/src/models mcp_server/src/services/catalog_identity.py mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_store_unit.py` → exit 0
3. `uv run --project mcp_server pyright mcp_server/src/models mcp_server/src/services/catalog_identity.py` → exit 0
4. Neo4j int: skipped by policy (do not probe live DB merely to discover availability)

## 4. Edge-probe coverage

Source: `01-EDGE-PROBE.json` asserted at gate write.

| Metric | Value |
|--------|-------|
| applicable | 53 |
| resolved | 53 |
| unresolved | 0 |
| items | 53 |
| every item status | resolved |
| every item verification | explicit or backstop |
| null_dispositions | 0 |
| no_silent_drop.key_equality | true |
| no_silent_drop.source_count | 53 |
| no_silent_drop.resolved_count | 53 |

## 5. Requirement coverage map (25 Phase 1 IDs)

| ID | Coverage evidence |
|----|-------------------|
| CONT-01 | 01-01 SUMMARY + `test_catalog_models.py` CatalogStrictModel base |
| CONT-02 | 01-01 SUMMARY + recursive extra=forbid matrix |
| CONT-03 | 01-01 SUMMARY + misspelled optional field tests |
| CONT-04 | 01-01 SUMMARY + raw-byte / hash-bearing preservation |
| CONT-05 | 01-01 SUMMARY + strict_endpoints Literal True |
| CONT-06 | 01-01 SUMMARY + atomic Literal True |
| CONT-07 | 01-04 SUMMARY + FastMCP call_tool / typed boundary spies |
| CONT-08 | 01-01 SUMMARY + error registry codes in catalog_common |
| IDEN-01 | 01-01 SUMMARY + identity_schema_version=catalog-v2 shell |
| IDEN-02 | 01-01 SUMMARY + required system_key FE\|BO\|COMMON |
| IDEN-03 | 01-02 SUMMARY + invalid_system_key before side effects |
| IDEN-04 | 01-02 SUMMARY + fullmatch graph-key grammar |
| IDEN-05 | 01-02 SUMMARY + 18-type registry |
| IDEN-06 | 01-02 SUMMARY + Procedure/Function #OVERLOAD |
| IDEN-07 | 01-03 SUMMARY + FE/BO UUID separation goldens |
| IDEN-08 | 01-02/01-03 SUMMARY + complete graph_key echo |
| IDEN-09 | 01-02 SUMMARY + System/DatabaseLink/SourceArtifact allowlist |
| IDEN-10 | 01-03 SUMMARY + versioned UUID materials |
| IDEN-11 | 01-03 SUMMARY + IDENTITY_SCHEMA_VERSION in materials |
| IDEN-12 | 01-02 SUMMARY + catalog-v1 key rejection |
| IDEN-13 | 01-03 SUMMARY + pure future helpers only; no pre-hardening golden import |
| SAFE-05 | 01-03 SUMMARY + caller UUID never identity authority |
| SAFE-08 | 01-04 SUMMARY + CatalogSafeFastMCP structured ToolError |
| TEST-01 | focused suite models + service strict/extra/flags matrix (414 green) |
| TEST-03 | focused suite identity FE/BO/overload/version goldens (414 green) |

## 6. Phase 0 baseline noise (not relabeled)

From `00-PHASE0-GATE.md` / `00-baseline-checks.json`:

- `catalog_unit_and_offline_canary` remains **fail** (pre-existing canary-script baseline noise on Windows worktree).
- Phase 1 does not repair or relabel those canary-script failures as pass.
- Phase 1 focused unit gates (models/identity/service/store_unit) are separate and green.

## 7. ready_for_phase_2

Derived only from real outcomes (authoritative machine lines live solely under **Gate Contract**):

- focused pytest, scoped ruff, scoped pyright: pass
- safety invariants: pass
- edge probe: pass (53/53, unresolved 0)
- no new store/control-plane write path: true
- canary executed: false
- oracle-catalog-v2 queried: false
- catalog neo4j int: skip (nonblocking)

Declared readiness: true (see Gate Contract).

## 8. Explicit non-goals

- No canary execution or repair
- No `oracle-catalog-v2` query/mutation
- No live/remote/deploy/push/merge/tag
- No product source edits in plan 01-05
- No manual waiver of Phase 2 entry
- No skip mislabeled pass
- No secret/payload/source-text/credential/token content in this gate

## 9. Dirty-tree allowlist snapshot

Known pre-existing dirty / excluded paths (from isolation policy):

- `.planning/config.json`
- `mcp_server/config/config-docker-neo4j.yaml`
- `mcp_server/k8s/graphiti-neo4j.yaml`
- `.codegraph/`
- untracked bulk `catalog/*` enrichment dumps
- `mcp_server/sample_catalog.json`

Intentional Phase 1 gate paths:

- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/**`
- intentional `.planning/STATE.md` / `.planning/ROADMAP.md` / `.planning/REQUIREMENTS.md`

## Gate Contract

focused_pytest=pass
scoped_ruff=pass
scoped_pyright=pass
catalog_neo4j_int=skip
safety_invariants=pass
edge_probe=pass
ready_for_phase_2=true
canary_executed=false
oracle_catalog_v2_queried=false
no_new_store_or_control_plane_write_path=true
resolved=53
unresolved=0
