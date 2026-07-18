---
phase: 03A-immutable-prepare-commit-control-plane
fixed_at: 2026-07-18T07:30:55Z
review_path: .planning/phases/03A-immutable-prepare-commit-control-plane/03A-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 03A: Code Review Fix Report

**Fixed at:** 2026-07-18T07:30:55Z
**Source review:** .planning/phases/03A-immutable-prepare-commit-control-plane/03A-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (WR-01..WR-07)
- Fixed: 7
- Skipped: 0
- Phase 3A gate: local_gate_pass=true, ready_for_phase_3b=true, prepare_commit=true, live_neo4j_immutable_proof=pass
- Final HEAD: 7083317 (ledger rebind after code fixes at 67edbd7)

## Fixed Issues

### WR-01: plan_token_matches raises on length-mismatched stored digest

**Files modified:** mcp_server/src/services/catalog_identity.py, mcp_server/tests/test_catalog_token.py
**Commit:** 565b117
**Applied fix:** Catch ValueError/TypeError around digest + hmac.compare_digest; malformed/corrupt stored digests return False timing-safely. Behavioral unit tests for wrong-length/non-str digests.

### WR-02: ensure_plan_schema lacks lock, once-ready flag, and SHOW verification

**Files modified:** mcp_server/src/services/catalog_store.py, mcp_server/tests/test_catalog_prepare_store.py
**Commit:** 2258923
**Applied fix:** Process-local _plan_schema_lock + _plan_schema_ready; post-CREATE SHOW CONSTRAINTS shape verification for plan/token/chunk uniqueness; fail closed with neo4j_schema_failed. Generalized _constraint_row_matches for property sets. Unit tests for idempotency and fail-closed wrong shape.

### WR-03: Prepare skips committed CatalogIngestBatch preflight

**Files modified:** mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_prepare_service.py
**Commit:** d2d8239
**Applied fix:** prepare_catalog_batch uses check_batch_status=True. committed+same hash -> prepared_plan_conflict (no new token); committed+different hash -> batch_conflict. No domain/status writes. Service tests cover both paths.

### WR-04: Evidence membership not coalesced; link_key omits excerpt

**Files modified:** mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_prepare_service.py
**Commit:** d2d8239
**Applied fix:** Membership path uses existing coalesce_byte_identical_evidence_links authority; rejects same link_key with divergent content as provenance_link_conflict before artifact serialize. Did not invent second hash/identity recipe. Tests for coalesce + conflict.

### WR-05: Store default canonicalization_version is wrong sentinel canon-v1

**Files modified:** mcp_server/src/services/catalog_store.py, mcp_server/tests/test_catalog_prepare_store.py
**Commit:** 2258923
**Applied fix:** Default uses imported CANONICALIZATION_VERSION (catalog-canonical-v1). Unit test asserts missing field defaults correctly.

### WR-06: Concurrent same-identity prepare maps uniqueness failure to generic Neo4j error

**Files modified:** mcp_server/src/services/catalog_store.py, mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_prepare_store.py, mcp_server/tests/test_catalog_prepare_service.py
**Commit:** 2258923 / d2d8239
**Applied fix:** _is_uniqueness_constraint_race maps plan/chunk CREATE uniqueness races to prepared_plan_conflict; unexpected Neo4j failures remain neo4j_transaction_failed. Service Exception path also maps races. Unit/service tests cover race mapping.

### WR-07: Live expiry proof allows residual PREPARED (gate softness)

**Files modified:** mcp_server/tests/test_catalog_prepare_neo4j_int.py
**Commit:** 7c33ac4
**Applied fix:** Bound retry loop requires terminal EXPIRED after access-path expire; PREPARED residual fails the proof.

## Gate / residual

- Extra commit 67edbd7: ruff E401/I001 on new service tests (module-top imports).
- Ledger rebind commit 7083317: docs(03A) rebind Phase 3A gate ledger after WR-01..WR-07 fixes.
- Info findings IN-01..IN-04 out of scope (fix_scope=critical_warning) — not fixed.
- Focused unit tests for fix surface: 75 passed before full gate.
- Full Phase 3A gate --require-neo4j: all mandatory checks pass; apply verified with prepare_commit true.

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-07-18T07:30:55Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
