---
phase: 03B
fixed_at: 2026-07-18T18:45:00Z
review_path: .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-REVIEW.md
iteration: 2
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 03B: Code Review Fix Report

**Fixed at:** 2026-07-18T18:45:00Z
**Source review:** `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-REVIEW.md`
**Iteration:** 2

**Summary:**
- Findings in scope: 7 (WR-01..WR-05 from iteration 1; WR-06, WR-07, IN-01 from iteration 2)
- Fixed: 7
- Skipped: 0

## Fixed Issues

### WR-01: Coalesced evidence count authority

**Files modified:** `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_prepare_service.py`
**Commit:** `9de1790`
**Applied fix:** After membership sort, set `coalesced_evidence_count = len(membership_evidence)` and use it for artifact `counts.evidence_links`, plan_params `evidence_link_count`, and Prepare response `evidence_link_count`.

### WR-02: Fail-closed missing embeddings on non-unchanged writes

**Files modified:** `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_review_wr_fixes.py`
**Commit:** `2df5c5c`
**Applied fix:** Atomic batch path rejects empty/None frozen embeddings with `CatalogStoreError(..., code='embedding_failed')`. Pass `list(prep.*_embedding)` instead of `or []`.

### WR-03: CAS reclaim batch claim; unknown statuses fail closed

**Files modified:** `mcp_server/src/services/catalog_store.py`, `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_store_unit.py`, `mcp_server/tests/test_catalog_atomic_writer.py`
**Commit:** `a04e9fb`
**Applied fix:** Claim Cypher ON MATCH reclaims only same-hash `writing|failed`; committed/unknown returned unchanged. Consumer fail-closed on unknown.

### WR-04: Edge identity error_code + raise before status

**Files modified:** `mcp_server/src/services/catalog_store.py`, `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_store_unit.py`, `mcp_server/tests/test_catalog_review_wr_fixes.py`
**Commit:** `0c92cb4`
**Applied fix:** Edge upsert Cypher under-lock identity CASE → `error_code='edge_identity_conflict'`; `_raise_edge_row_error` on atomic batch path.

### WR-05: Verify manifest chunks on idempotent root hit

**Files modified:** `mcp_server/src/services/catalog_store.py`, `mcp_server/tests/test_catalog_evidence_store.py`, `mcp_server/tests/test_catalog_store_unit.py`
**Commit:** `01b2911`
**Applied fix:** `build_list_manifest_chunks_cypher()`; idempotent root verifies ordered chunks + hashes.

### WR-06: Typed edge writers raise edge row errors before status

**Files modified:** `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_review_wr_fixes.py`
**Commit:** `8bedb81` (product); tests in `aceffeb`
**Applied fix:** `_write_edges_atomic` and `_write_edges_per_item` call `_raise_edge_row_error(row)` immediately after store row, then defensive `status == 'error'` → `_EdgeEndpointRace`. Per-item catches `_EdgeEndpointRace` with structured `error_code` (not `neo4j_transaction_failed`). Atomic path already rolled siblings via existing `_EdgeEndpointRace` handler. Behavioral tests cover both writers.

### WR-07: upsert_catalog_batch catches EdgeEndpointRace with typed code

**Files modified:** `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_review_wr_fixes.py`
**Commit:** `cbed975` (product); tests in `aceffeb`
**Applied fix:** `except self._EdgeEndpointRace` before generic Exception in `upsert_catalog_batch`; `_record_failed_status(exc.code.value)`; return `error_code=exc.code` with message `edge under-lock conflict: {code}`. No collapse to `neo4j_transaction_failed`.

### IN-01: Fail-closed empty embeddings on typed entity/edge params

**Files modified:** `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_review_wr_fixes.py`
**Commit:** `23033c8` (product); tests in `aceffeb`
**Applied fix:** `_params_for` / `_edge_params_for` reject missing/empty embeddings with `CatalogStoreError(..., code='embedding_failed')` and pass `list(prep.*_embedding)`. Typed entity/edge atomic and per-item writers map `CatalogStoreError` embedding_failed to structured `CatalogErrorCode.embedding_failed` responses (no neo4j collapse).

## Verification

- Focused: `test_catalog_review_wr_fixes.py` 13 passed
- Atomic writer: `test_catalog_atomic_writer.py` 12 passed (25 total)
- Ruff check: clean
- Pyright: 0 errors on `catalog_service.py`
- `git diff --check 8fc7ece..HEAD`: clean

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-07-18T18:45:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
