---
phase: 03A-immutable-prepare-commit-control-plane
reviewed: 2026-07-18T15:10:00Z
depth: deep
files_reviewed: 12
files_reviewed_list:
  - mcp_server/src/services/catalog_identity.py
  - mcp_server/src/services/catalog_store.py
  - mcp_server/src/services/catalog_service.py
  - mcp_server/src/models/catalog_common.py
  - mcp_server/tests/test_catalog_token.py
  - mcp_server/tests/test_catalog_prepare_store.py
  - mcp_server/tests/test_catalog_prepare_service.py
  - mcp_server/tests/test_catalog_prepare_neo4j_int.py
  - mcp_server/tests/catalog_phase3a_gate_runner.py
  - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json
  - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-REVIEW-FIX.md
  - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-PHASE3A-GATE.md
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
prior_findings:
  WR-01: fixed
  WR-02: fixed
  WR-03: fixed
  WR-04: fixed
  WR-05: fixed
  WR-06: fixed
  WR-07: fixed
gate:
  evaluated_head: 67edbd7c94283a7ba65f4ffd23fde751a3064b72
  current_head: 7c5265edebeb4d293e14fdeddd9348cf895320cb
  head_compatible: false
  product_code_at_evaluated_head: true
  prepare_commit_claim: true
  live_neo4j_immutable_proof: pass
---

# Phase 03A: Code Review Report (re-review after WR-01..WR-07)

**Reviewed:** 2026-07-18T15:10:00Z
**Depth:** deep
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Re-review of Phase 03A after WR-01..WR-07 fix commits (`565b117`..`67edbd7`) plus subsequent docs commits (`7083317` gate rebind, `7c5265e` REVIEW-FIX). Product surface for prior warnings is fixed with matching unit coverage. No new Critical product defects found on static review.

One Warning remains: final gate ledger is **not HEAD-compatible** at current HEAD. `evaluated_head=67edbd7` (code fixes). Parent hop `7083317` (ledger-only) would pass `_head_compatible`. Child `7c5265e` adds `03A-REVIEW-FIX.md`, which is outside the allowlist — `verify_ledger` fails closed with `head-mismatch`. Claims `ready_for_phase_3b=true` / `prepare_commit=true` are true for product code at `67edbd7`, but ledger authority is stale at `7c5265e`.

## Prior warning disposition

| ID | Status | Evidence |
|----|--------|----------|
| WR-01 | **fixed** | `plan_token_matches` guards non-str/empty; wraps digest+`compare_digest` in `ValueError`/`TypeError` → `False` (`catalog_identity.py:117-129`). Behavioral tests for wrong-length/None/int digests (`test_catalog_token.py:182-191`). Commit/discard auth path uses matches post-load. |
| WR-02 | **fixed** | `_plan_schema_lock` + `_plan_schema_ready`; double-check; post-CREATE `SHOW CONSTRAINTS` exact prop sets for plan/token/chunk constraints; fail closed `neo4j_schema_failed` (`catalog_store.py:1870-1983`). Tests: idempotent, wrong-shape fail-closed (`test_catalog_prepare_store.py:846-900`). |
| WR-03 | **fixed** | `prepare_catalog_batch` → `check_batch_status=True` (`catalog_service.py:5137`). `committed_same` → `prepared_plan_conflict` (no token); `committed_conflict` → `batch_conflict` (`:5179-5188`, preflight `:3817-3842`). Service tests (`test_catalog_prepare_service.py:1062-1086`). |
| WR-04 | **fixed** | Membership uses `coalesce_byte_identical_evidence_links` then rejects same `link_key` divergent content as `provenance_link_conflict` (`:5287-5315`). Coalesce + conflict tests (`:1105-1210`). |
| WR-05 | **fixed** | Default `CANONICALIZATION_VERSION` import (`catalog_store.py:2208-2210`). Unit default test (`test_catalog_prepare_store.py:934-939`). |
| WR-06 | **fixed** | `_is_uniqueness_constraint_race` on plan/chunk CREATE (`catalog_store.py:2299-2421`); service `except Exception` maps races to `prepared_plan_conflict` (`catalog_service.py:5492-5509`). Store + service race tests. |
| WR-07 | **fixed** | Live expiry proof requires terminal `EXPIRED` with bound retry; residual `PREPARED` fails (`test_catalog_prepare_neo4j_int.py:619-633`). |

## Narrative Findings (AI reviewer)

## Warnings

### WR-R01: Gate ledger HEAD binding invalid after REVIEW-FIX docs commit

**File:** `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json` (`evaluated_head`); `mcp_server/tests/catalog_phase3a_gate_runner.py:898-916`
**Issue:** Ledger binds `evaluated_head=67edbd7c94283a7ba65f4ffd23fde751a3064b72` with pass claims (`local_gate_pass`, `ready_for_phase_3b`, `prepare_commit`, live proof). Current HEAD is `7c5265edebeb4d293e14fdeddd9348cf895320cb`.

`_head_compatible` allows only:
1. exact HEAD match, or
2. single parent hop where every file in HEAD ends with allowlisted suffixes (`03A-GATE-RESULTS.json`, `03A-PHASE3A-GATE.md`, `03A-06-SUMMARY.md`, `03A-VALIDATION.md`, `03A-EDGE-PROBE-RESOLUTION.json`).

History:
- `7083317` (parent of current, child of `67edbd7`): only `03A-GATE-RESULTS.json` → would be `ledger-only-child` **pass**.
- `7c5265e` (current): only `03A-REVIEW-FIX.md` → **not allowlisted** → `verify_ledger` returns `evaluated_head invalid: head-mismatch`.

Static invoke at this checkout: `head_compatible=False`. Gate report text still advertises pass. Product code unchanged since `67edbd7` (docs-only delta) — claim is code-true, ledger-false at HEAD.

**Fix:** Either:
1. Re-run Phase 3A gate on current HEAD and rewrite ledger `evaluated_head` + digests, or
2. Extend `_head_compatible` allowlist with `03A-REVIEW.md` / `03A-REVIEW-FIX.md` if review docs are intentionally non-invalidating, or
3. Keep REVIEW-FIX off the branch tip used for readiness (new rebind commit is enough).

Do not treat current HEAD as gate-green without one of the above.

## Info

### IN-R01: Uniqueness race classifier remains string-broad

**File:** `mcp_server/src/services/catalog_store.py:2299-2313`
**Issue:** Markers include bare `already exists` and `constraint error`, so non-uniqueness messages (e.g. `Index already exists`) classify as race → `prepared_plan_conflict`. False-positive conflict is safer than infra mis-map, but clients may retry as identity conflict when the real fault is schema/index. Acceptable residual for WR-06 intent; tighten to Neo4j codes/`ConstraintValidationFailed` if ops noise appears.

### IN-R02: Schema ensure failures collapse to `neo4j_transaction_failed` at service

**File:** `mcp_server/src/services/catalog_service.py:5441-5457`
**Issue:** Store raises `CatalogStoreError(code='neo4j_schema_failed')`, but outer prepare catch is bare `Exception` and always returns `neo4j_transaction_failed`. No `CatalogErrorCode.neo4j_schema_failed`. Fail-closed write avoidance holds; error taxonomy loses schema vs tx distinction.

### IN-R03: Coalesce membership test has vacuous count assert

**File:** `mcp_server/tests/test_catalog_prepare_service.py:1210`
**Issue:** `assert plan['evidence_link_count'] == 2 or plan['evidence_link_count'] == 1 or True` always passes. Membership length assert (`len(...) == 1`) is real; plan count assert is dead. Prefer assert raw request count (`2`) if counts intentionally ignore coalesce.

## Cross-file notes (no separate finding)

- Token auth: digest locator + post-load `plan_token_matches`; malformed digest → not_found, not crash — OK.
- Plan schema lock mirrors domain identity ensure; process-local once-ready is intentional (same as domain). Multi-loop lock reuse only matters if one store instance spans loops before ready — not the MCP process model.
- Prepare still zero domain/status/evidence writes; commit still stops at `COMMITTING` without embedder/LLM/queue — OK for 3A.
- Live expiry product path: wall-clock → CAS PREPARED→EXPIRED → `prepared_plan_expired`; test now requires persisted `EXPIRED`.
- Prior Info residuals IN-01..IN-04 (stranded COMMITTING capacity, discard expiry path, source-string token test, capabilities hardcoded) remain out of fix scope; IN-03 partially superseded by new behavioral digest tests.

## Gate / HEAD truth

| Field | Value |
|-------|-------|
| Product code HEAD for fixes | `67edbd7` |
| Ledger `evaluated_head` | `67edbd7` |
| Current git HEAD | `7c5265e` |
| Docs after code | `7083317` rebind (compatible), `7c5265e` REVIEW-FIX (breaks parent-hop allowlist) |
| `verify_ledger` at current HEAD | **fail** (`head-mismatch`) |
| Product WR-01..07 | fixed at `67edbd7` and unchanged since |
| Live proof claim in ledger | pass (bound to evaluated code HEAD, not re-proven at `7c5265e`) |

---

_Reviewed: 2026-07-18T15:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
_Re-review after: 03A-REVIEW-FIX.md (WR-01..WR-07)_
