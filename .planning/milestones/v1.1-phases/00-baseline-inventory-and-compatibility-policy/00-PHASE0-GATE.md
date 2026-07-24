# Phase 0 Gate Report

**Date:** 2026-07-18  
**Consumer:** Phase 1 entry checklist  
**Authority:** SAFE-01, SAFE-02, SAFE-12, SAFE-13, BASE-01..BASE-04; Wave 2 plan 00-02  
**Rule:** `ready_for_phase_1` is true only when all required artifacts exist, safety invariants are true, and the check ledger is present with truthful statuses. Skip is never converted to pass. Pre-existing fail rows are recorded, not repaired.

## 1. Artifact checklist

| Artifact | Status | Path |
|----------|--------|------|
| `00-BASELINE.md` | present | `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-BASELINE.md` |
| `00-baseline-checks.json` (required) | present | `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-baseline-checks.json` |
| `00-COMPATIBILITY-POLICY.md` | present | `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-COMPATIBILITY-POLICY.md` |
| `00-ISOLATION-POLICY.md` | present | `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-ISOLATION-POLICY.md` |
| `00-PHASE0-GATE.md` (this file) | present | `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-PHASE0-GATE.md` |

Missing: none.

## 2. Safety invariants

All must be true for readiness.

| Invariant | Value | Evidence |
|-----------|-------|----------|
| `canary_executed` | false | Wave 1 ledger + this plan history; no invoke of `scripts/run_catalog_canary_batch.py` |
| `oracle_catalog_v2_queried` | false | Wave 1 ledger; offline inventory only |
| `product_contract_or_identity_code_changed` | false | Phase 0 commits touch planning artifacts only under the phase directory |
| `unrelated_dirty_files_committed` | false | Commit allowlist = phase dir (+ intentional STATE/ROADMAP when required; plan 02 does not update shared tracking) |
| `remote_push_merge_deploy_tag` | false | SAFE-13 ban; no remote ops in Phase 0 commits |

## 3. Requirement coverage map

| ID | Coverage artifact / section |
|----|-----------------------------|
| BASE-01 | `00-BASELINE.md` §§1–3 (14 legacy + 7 catalog tools, surface map) |
| BASE-02 | `00-BASELINE.md` §4 (offline ACCEPT_TAB digests/counts) |
| BASE-03 | `00-BASELINE.md` §5 + `00-baseline-checks.json` (pass\|fail\|skip ledger with first_failure_id) |
| BASE-04 | `00-BASELINE.md` §5 (ruff/pyright/skip) + `00-COMPATIBILITY-POLICY.md` (catalog-v1 deprecation boundary) |
| SAFE-01 | `00-ISOLATION-POLICY.md` §§1–2 (`oracle-catalog-tool-test` only; `oracle-catalog-v2` offline only) |
| SAFE-02 | `00-ISOLATION-POLICY.md` §3 (canary ban including dry-run) |
| SAFE-12 | `00-ISOLATION-POLICY.md` §§4–5 (dirty exclude list + commit allowlist) |
| SAFE-13 | `00-ISOLATION-POLICY.md` §6 (remote ban) |

## 4. Check summary (from `00-baseline-checks.json`)

Recorded at `2026-07-17T17:40:00Z`. Statuses copied truthfully — fail and skip are not reclassified as pass.

| name | status | exit_code | first_failure_id |
|------|--------|-----------|------------------|
| `catalog_unit_and_offline_canary` | **fail** | 1 | `tests/test_catalog_canary_scripts.py::test_artifact_set_fields_canonical_bytes_hashes_and_manifest_counts` |
| `ruff_catalog_surface` | **pass** | 0 | null |
| `pyright_catalog_scoped` | **pass** | 0 | null |
| `catalog_neo4j_int` | **skip** | null | null |

**Counts:** pass=2, fail=1, skip=1 (total=4).

Notes (ledger): 8 pre-existing canary-script failures on Windows worktree (CRLF vs LF, missing `catalog/catalog.json`, cascading hash mismatches). Not repaired in Phase 0. Neo4j int default-skipped; never targets `oracle-catalog-v2`.

Wave 1 safety flags from JSON: `canary_executed=false`, `oracle_catalog_v2_queried=false`.

## 5. ready_for_phase_1

```text
ready_for_phase_1=true
```

**Justification:**

1. All five Phase 0 gate artifacts are present (baseline + checks JSON + compatibility policy + isolation policy + this gate).
2. All five safety invariants are true.
3. Check ledger is present with truthful pass/fail/skip statuses (fail/skip retained; not mislabeled pass).
4. No product contract/identity implementation occurred in Phase 0.
5. Pre-existing catalog offline-canary failures are baseline noise for later regression classification — Phase 0 success criteria require recording them, not repairing them.

**Missing list:** empty.

## 6. Explicit non-goals (restated)

- No Phase 1 contract/identity implementation in this phase.
- No canary execution (`run_catalog_canary_batch` banned including dry-run).
- No live-group writes; no `oracle-catalog-v2` query/mutation.
- No remote push/merge/deploy/tag.
- No product source modules under the phase directory.

## 7. Dirty-tree allowlist snapshot (verify)

Known pre-existing dirty / excluded paths (from isolation policy):

- `.planning/config.json`
- `mcp_server/config/config-docker-neo4j.yaml`
- `mcp_server/k8s/graphiti-neo4j.yaml`
- `.codegraph/`
- untracked bulk `catalog/*` enrichment dumps
- `mcp_server/sample_catalog.json`

Intentional Phase 0 paths:

- `.planning/phases/00-baseline-inventory-and-compatibility-policy/**`
- intentional `.planning/STATE.md` / `.planning/ROADMAP.md` when an executor is required to update them (plan 02 does not)

Any other path is unexpected and fails dirty-tree verification.

### Operational verification (recorded at gate write)

| Step | Outcome |
|------|---------|
| `git status --short` against allowlist | pass — no unexpected paths in this worktree at gate write |
| Phase history invoked `run_catalog_canary_batch`? | no — references are ban/inventory only |
| Phase directory product modules? | no — planning docs only |

## 8. Phase 1 entry notes

- Compare future catalog/canary/ruff/pyright results against `00-baseline-checks.json`.
- Treat catalog-v1 keys/hashes/receipts as historical only (`00-COMPATIBILITY-POLICY.md`).
- Tests/dev writes: `oracle-catalog-tool-test` only (`00-ISOLATION-POLICY.md`).
- Do not import pre-hardening goldens as hardened catalog-v2 goldens (IDEN-13 intent).
