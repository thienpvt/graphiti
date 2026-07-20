---
phase: 03A-immutable-prepare-commit-control-plane
reviewed: 2026-07-18T16:20:00Z
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
  warning: 0
  info: 3
  total: 3
status: clean
prior_findings:
  WR-01: fixed
  WR-02: fixed
  WR-03: fixed
  WR-04: fixed
  WR-05: fixed
  WR-06: fixed
  WR-07: fixed
  WR-R01: fixed
gate:
  evaluated_head: 1fdf545792780795ded88c2a845f767cfef9e254
  current_head: e03e15d101b0b8c253f85b06e3cb6798a8cff746
  head_compatible: true
  head_reason: ledger-only-child
  product_code_at_evaluated_head: true
  prepare_commit_claim: true
  live_neo4j_immutable_proof: pass
  verify_ledger_ok: true
  apply_verified: true
---

# Phase 03A: Code Review Report (re-review after WR-01..WR-07 + WR-R01)

**Reviewed:** 2026-07-18T16:20:00Z
**Depth:** deep
**Files Reviewed:** 12
**Status:** clean

## Summary

Deep re-review after WR-01..WR-07 product fixes and subsequent gate/review docs rebinds. All prior Critical/Warning findings resolved. No new Critical or Warning defects on static review.

Gate authority at primary HEAD `e03e15d` is valid: `evaluated_head=1fdf545`, `_head_compatible` → `ledger-only-child` (HEAD touches only `03A-GATE-RESULTS.json`), `verify_ledger(..., require_neo4j=True)` → `ok=True`, `apply_verified=true`, `prepare_commit=true`, live immutable proof pass. Product WR-01..07 remain fixed since code HEAD `67edbd7` (docs-only after that).

All reviewed files meet quality standards. No Critical or Warning issues remain.

## Prior warning disposition

| ID | Status | Evidence |
|----|--------|----------|
| WR-01 | **fixed** | `plan_token_matches` fail-closed on malformed/corrupt digests (`catalog_identity.py:117-129`); behavioral unit tests. |
| WR-02 | **fixed** | Plan schema lock + once-ready + SHOW CONSTRAINTS exact shape; fail closed `neo4j_schema_failed`. |
| WR-03 | **fixed** | Prepare uses `check_batch_status=True`; committed same → `prepared_plan_conflict`, different → `batch_conflict`. |
| WR-04 | **fixed** | Membership coalesce authority + same-link_key divergent content → `provenance_link_conflict`. |
| WR-05 | **fixed** | Store default `CANONICALIZATION_VERSION` (`catalog-canonical-v1`). |
| WR-06 | **fixed** | Uniqueness CREATE races → `prepared_plan_conflict` (store + service). |
| WR-07 | **fixed** | Live expiry proof requires terminal `EXPIRED` (no PREPARED residual). |
| WR-R01 | **fixed** | Ledger rebound; current HEAD is ledger-only child of evaluated HEAD; `verify_ledger` passes. |

## Narrative Findings (AI reviewer)

No Critical or Warning findings.

## Info

### IN-R01: Uniqueness race classifier remains string-broad

**File:** `mcp_server/src/services/catalog_store.py:2299-2313`
**Issue:** Markers include bare `already exists` and `constraint error`, so non-uniqueness messages (e.g. `Index already exists`) classify as race → `prepared_plan_conflict`. False-positive conflict is safer than infra mis-map. Acceptable residual; tighten to Neo4j codes if ops noise appears.

### IN-R02: Schema ensure failures collapse to `neo4j_transaction_failed` at service

**File:** `mcp_server/src/services/catalog_service.py:5441-5457`
**Issue:** Store raises `CatalogStoreError(code='neo4j_schema_failed')`, but prepare outer catch returns `neo4j_transaction_failed`. Fail-closed write avoidance holds; taxonomy loses schema vs tx distinction.

### IN-R03: Coalesce membership test has vacuous count assert

**File:** `mcp_server/tests/test_catalog_prepare_service.py:1210`
**Issue:** `assert plan['evidence_link_count'] == 2 or plan['evidence_link_count'] == 1 or True` always passes. Membership length assert is real; plan count assert is dead.

## Cross-file notes (no separate finding)

- Token auth: digest locator + post-load `plan_token_matches`; malformed → not_found — OK.
- Plan schema lock mirrors domain identity ensure; process-local once-ready intentional.
- Prepare zero domain/status/evidence writes; commit stops at `COMMITTING` without embedder/LLM/queue — OK for 3A.
- Live expiry: wall-clock → CAS PREPARED→EXPIRED → `prepared_plan_expired`; proof requires persisted EXPIRED.
- Prior Info IN-01..IN-04 remain intentional residuals (stranded COMMITTING capacity, discard expiry path, source-string token test superseded in part, capabilities hardcoded).

## Gate / HEAD truth

| Field | Value |
|-------|-------|
| Product code HEAD for WR-01..07 | `67edbd7` |
| Ledger `evaluated_head` | `1fdf545` |
| Current git HEAD | `e03e15d` |
| HEAD files | `03A-GATE-RESULTS.json` only |
| `_head_compatible` | `ledger-only-child` |
| `verify_ledger` | **ok** |
| `prepare_commit` / live proof | true / pass |
| `apply_verified` | true |

---

_Reviewed: 2026-07-18T16:20:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
_Re-review after: WR-01..WR-07 + WR-R01 gate rebind_
