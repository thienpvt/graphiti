---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
reviewed: 2026-07-18T15:40:00Z
reviewed_head: aceffeb80d4420ea50cca753fb61d338698e8e6e
depth: deep
files_reviewed: 19
files_reviewed_list:
  - mcp_server/src/models/catalog_responses.py
  - mcp_server/src/services/catalog_capabilities.py
  - mcp_server/src/services/catalog_identity.py
  - mcp_server/src/services/catalog_manifest.py
  - mcp_server/src/services/catalog_service.py
  - mcp_server/src/services/catalog_store.py
  - mcp_server/tests/catalog_phase3b_gate_runner.py
  - mcp_server/tests/test_catalog_atomic_writer.py
  - mcp_server/tests/test_catalog_capabilities.py
  - mcp_server/tests/test_catalog_commit_neo4j_int.py
  - mcp_server/tests/test_catalog_commit_recovery.py
  - mcp_server/tests/test_catalog_concurrency.py
  - mcp_server/tests/test_catalog_evidence_store.py
  - mcp_server/tests/test_catalog_manifest.py
  - mcp_server/tests/test_catalog_phase3b_gate_runner.py
  - mcp_server/tests/test_catalog_prepare_service.py
  - mcp_server/tests/test_catalog_service.py
  - mcp_server/tests/test_catalog_review_wr_fixes.py
  - mcp_server/tests/test_catalog_store_unit.py
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: clean
---

# Phase 03B: Code Review Report

**Reviewed:** 2026-07-18T15:40:00Z
**Reviewed HEAD:** `aceffeb80d4420ea50cca753fb61d338698e8e6e`
**Depth:** deep
**Files Reviewed:** 19
**Status:** clean

## Summary

Deep re-review of Phase 3B at fix HEAD `aceffeb` (sibling worktree read-only). Prior WR-01..WR-07 and IN-01 are verified fixed in product code and covered by `test_catalog_review_wr_fixes.py` plus prepare/store unit assertions.

Traced prepare → freeze → claim → `_write_catalog_batch_atomic` (entities/edges/sources/evidence/manifest/terminals) → recovery short-circuit → commit exception surfaces. Typed-edge atomic/per-item paths raise `edge_identity_conflict` before status and map `_EdgeEndpointRace` without collapsing to `neo4j_transaction_failed`. Missing/empty embeddings fail closed as `embedding_failed` before domain upsert. No Critical or Warning defects remain under the Phase 3B contracts.

All reviewed files meet quality standards for ship of residual review fixes. Only intentional informational residuals remain.

## Fix verification (prior findings)

| ID | Status | Evidence at `aceffeb` |
|----|--------|------------------------|
| WR-01 | fixed | `coalesced_evidence_count = len(membership_evidence)`; plan/artifact/response use it (`catalog_service.py:6210-6436`); prepare test asserts `== 1` (`test_catalog_prepare_service.py:1337-1340`) |
| WR-02 | fixed | Atomic writer rejects missing/empty embeddings with `embedding_failed` (`catalog_service.py:5390-5452`); no `name_embedding or []` / `fact_embedding or []` in `mcp_server/` |
| WR-03 | fixed | Claim Cypher CAS reclaim only from `writing\|failed` (`catalog_store.py:1420-1452`); consumer fail-closed on unknown status (`catalog_service.py:5307-5317`) |
| WR-04 | fixed | Edge upsert Cypher emits `edge_identity_conflict` + `error_code` (`catalog_store.py:1747-1788`); `_raise_edge_row_error` before status (`catalog_service.py:5474`) |
| WR-05 | fixed | Idempotent manifest root verifies ordered chunk count + `chunk_sha256` (`catalog_store.py:3612-3650`) |
| WR-06 | fixed | Typed edge atomic/per-item call `_raise_edge_row_error`; surface typed code; rollback siblings (`catalog_service.py:2643-2698,2778-2832`); tests `test_wr06_*` |
| WR-07 | fixed | `upsert_catalog_batch` catches `_EdgeEndpointRace` with `exc.code` (`catalog_service.py:5946-5962`); test `test_wr07_*` |
| IN-01 | fixed | `_params_for` / `_edge_params_for` reject empty embeddings (`catalog_service.py:1091-1095,2364-2368`); coalesce assertion no longer tautological |

## Narrative Findings (AI reviewer)

### Cross-file call graph (verified)

1. `prepare_catalog_batch` → embed non-unchanged → freeze membership (+embeddings) with coalesced evidence count authority → plan/chunks CREATE-once.
2. `commit_prepared_catalog_batch` → token digest load → `plan_token_matches` → reassemble artifact → `_verify_frozen_plan_binding` → CAS PREPARED\|COMMITTING→COMMITTING → `_build_projection_from_artifact` (zero embedder) → `_write_catalog_batch_atomic`.
3. Atomic writer: lock plan → `claim_batch_status` → terminal agree short-circuit / partial fail-closed → domain upserts with embedding + identity fail-closed → `write_evidence_links` → `write_manifest_root_and_chunks` (chunk-verified idempotent hit) → batch `committed` → plan COMMITTED + outcome counts.
4. Upsert path reuses same atomic writer with live embed pre-tx; `_EdgeEndpointRace` / `_EntityInvariantRace` mapped to typed codes.
5. Typed edge writers: recheck → upsert → `_raise_edge_row_error` → status; `embedding_failed` and identity races stay typed.
6. Capabilities pure; `features.manifests=True`, `manifest_verification=False`, `prepare_commit=True`; no `.planning/*` runtime read.

### Security / isolation positives (no finding)

- Evidence/manifest param allowlists; forbidden keys stripped.
- Labels/types server-resolved; no client label interpolation into Cypher.
- Plan token: mint via `secrets.token_urlsafe`, store digest only, `hmac.compare_digest` verify; raw token not in commit response DTO.
- `group_id` on every MATCH/MERGE identity; evidence source/target resolved group-scoped before write.
- Failed batch status only in separate post-rollback tx (D-27); never co-committed with manifest/plan COMMITTED.
- Terminal agreement requires plan COMMITTED + batch committed + manifest/request/catalog/artifact/identity bind; partial terminals fail closed without PREPARED revival.
- Int tests + gate runner enforce `oracle-catalog-tool-test` only; ban `oracle-catalog-v2`.
- `_map_store_error_code` preserves `embedding_failed` / `batch_conflict` enums for commit responses.

## Critical Issues

None.

## Warnings

None.

## Info

### IN-01: Capabilities feature flags hard-coded post-flip (intentional)

**File:** `mcp_server/src/services/catalog_capabilities.py:146-155`
**Issue:** `prepare_commit=True`, `manifests=True`, `manifest_verification=False` are static. Mutation-free and no `.planning` read — correct for D-33. Future env/config toggle not present (YAGNI unless multi-env rollback needed).
**Fix:** None required for Phase 3B.

### IN-02: Historical a67789a v2 read probe is residual documentation only

**File:** `mcp_server/tests/catalog_phase3b_gate_runner.py`; `test_catalog_commit_neo4j_int.py`
**Issue:** Gate runner records HISTORICAL_V2_COMMIT `a67789a` local test-policy query. Current int tests hard-ban forbidden group in params/cypher and pin `oracle-catalog-tool-test`. No present-day product path issues from this residual.
**Fix:** None required.

### IN-03: Prepare early-fail helper still echoes raw evidence length

**File:** `mcp_server/src/services/catalog_service.py:6057-6060`
**Issue:** Nested `_fail` used only on pre-coalesce / preflight error paths still sets `evidence_link_count=len(request.provenance.evidence_links)`. Success path, plan root, artifact counts, and commit receipts use `coalesced_evidence_count`. Not durable-authority drift; error responses may show raw input length.
**Fix:** Optional: set early `_fail` count to 0 or pass coalesced when available; cosmetic only.

---

_Reviewed: 2026-07-18T15:40:00Z_
_Reviewed HEAD: aceffeb80d4420ea50cca753fb61d338698e8e6e_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
