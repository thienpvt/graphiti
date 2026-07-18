---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
reviewed: 2026-07-18T00:00:00Z
depth: deep
files_reviewed: 17
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
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 03B: Code Review Report

**Reviewed:** 2026-07-18T00:00:00Z
**Depth:** deep
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Deep adversarial review of Phase 3B atomic catalog exact-evidence + durable-manifest paths. Traced prepare → frozen artifact → claim → `_write_catalog_batch_atomic` (entities/edges/sources/evidence/manifest/terminals) → recovery/short-circuit, plus pure identity/manifest helpers, capabilities, and isolation tests.

Core co-write order, create-once evidence MERGE, manifest CREATE-once + hash conflict, terminal agreement, D-27 failed-status post-rollback, plan CAS legal table (no COMMITTING→PREPARED), token digest + `hmac.compare_digest`, allowlisted Cypher params, and tool-test-only isolation look sound. No critical security injection or terminal dual-commit path proven.

Residual defects are count-authority drift (raw vs coalesced evidence), fail-open empty embeddings on commit projection, batch claim re-entry on non-terminal status, edge write lacking in-Cypher identity `error_code`, and a dead coalesce assertion in tests. Historical `a67789a` v2 probe is documented residual only; current int/gate code bans `oracle-catalog-v2`.

## Narrative Findings (AI reviewer)

### Cross-file call graph (verified)

1. `prepare_catalog_batch` → embed non-unchanged → freeze membership (+embeddings) → plan/chunks CREATE-once.
2. `commit_prepared_catalog_batch` → token digest load → `plan_token_matches` → reassemble artifact → `_verify_frozen_plan_binding` → CAS PREPARED|COMMITTING→COMMITTING → `_build_projection_from_artifact` (zero embedder) → `_write_catalog_batch_atomic`.
3. Atomic writer: lock plan → `claim_batch_status` → terminal agree short-circuit / partial fail-closed → domain upserts → `write_evidence_links` → `write_manifest_root_and_chunks` → batch `committed` → plan COMMITTED + outcome counts.
4. Upsert path reuses same atomic writer with live embed pre-tx.
5. Capabilities pure; `features.manifests=True`, `manifest_verification=False`, `prepare_commit=True`; no `.planning/*` runtime read.

## Warnings

### WR-01: Prepare/plan/receipt `evidence_link_count` uses raw input length; membership/manifest use coalesced

**File:** `mcp_server/src/services/catalog_service.py:6054-6060,6146-6148,6262-6264`
**Issue:** After `coalesce_byte_identical_evidence_links` (line 6008), frozen membership and later manifest body counts use coalesced rows (`catalog_manifest.build_manifest_body_from_membership` counts). Plan root, artifact `counts.evidence_links`, prepare response, and commit receipt still store/echo `len(request.provenance.evidence_links)` (pre-coalesce). `_verify_frozen_plan_binding` only checks root vs artifact counts (both raw), so binding never catches the drift. Clients can see `evidence_link_count=N` while durable `CatalogBatchManifest` has `evidence_link_count<N`. Hash authority correctly coalesces (`catalog_identity.batch_request_canonical_payload`); count surface does not.
**Fix:**
```python
# After building membership_evidence (coalesced+deduped by link_key):
coalesced_evidence_count = len(membership_evidence)
# Use coalesced_evidence_count for artifact counts, plan_params, and PrepareCatalogBatchResponse.
# Keep raw only if explicitly named raw_evidence_link_count (additive).
```

### WR-02: Commit/atomic writer fail-open empty embeddings via `or []`

**File:** `mcp_server/src/services/catalog_service.py:5265,5317` (also projection `name_embedding`/`fact_embedding` at 4852-4866,4877-4909)
**Issue:** For `projected_status != 'unchanged'`, writer passes `prep.name_embedding or []` / `prep.fact_embedding or []` into vector property setters. Prepare freezes embeddings for non-unchanged rows, but artifact projection accepts missing/None embedding and substitutes empty list. Violates project contract that embedding failure must not produce domain writes. Empty vector may abort Neo4j (OK) or persist unsearchable entity/edge (data quality defect) without `embedding_failed`.
**Fix:**
```python
if status != 'unchanged':
    if not prep.name_embedding:  # None or empty
        raise CatalogStoreError(
            'frozen name_embedding missing for non-unchanged entity',
            code='embedding_failed',
        )
    # same for fact_embedding on edges; never `or []` on create/update path
```

### WR-03: `claim_batch_status` ON CREATE only — non-terminal reclaim re-enters full rewrite

**File:** `mcp_server/src/services/catalog_store.py:1420-1435`; consumer `catalog_service.py:5159-5176`
**Issue:** Claim MERGE sets `status='writing'` only ON CREATE. Existing `failed`/`writing` with same `request_sha256` returns prior status and proceeds into full domain+evidence+manifest rewrite. Direct upsert short-circuits only `committed`; plan path uses terminal agreement matrix but still allows resume under `failed`/`writing` without re-stamping claim. Concurrent same-hash writers can both pass claim and race domain MERGEs until one commits terminals.
**Fix:** On MATCH, CAS-style re-claim: only allow proceed when status in (`writing`,`failed`) and hash matches; SET `status='writing', updated_at=$updated_at`. Reject unknown statuses. Optionally serialize with plan lock for upsert path too.

### WR-04: Edge upsert Cypher has no identity `error_code`; atomic path does not raise on edge row errors

**File:** `mcp_server/src/services/catalog_store.py:1685-1760`; `catalog_service.py:5301-5322`
**Issue:** Entity upsert returns `error_code` + `status=error` and service calls `_raise_entity_row_error`. Edge upsert returns only `status` (`created`/`updated`/`unchanged`) with identity set ON CREATE only. Atomic writer relies on `_batch_recheck_edge_in_tx` / `detect_edge_identity_conflict` before write. That recheck is necessary but not symmetric to entity create-once arbitration inside the MERGE; a future caller that skips recheck (or races after recheck outside the same lock strategy) can classify identity drift as content `updated`.
**Fix:** Mirror entity pattern: after MERGE, compare `e.name`/`e.edge_key`/`source_node_uuid`/`target_node_uuid` to params; set `error_code='edge_identity_conflict'` and skip mutable SET/vector. In service, call `_raise_edge_row_error(row)` before `_write_status_from_row`.

### WR-05: Manifest idempotent hit returns without verifying chunk completeness

**File:** `mcp_server/src/services/catalog_store.py:3555-3579`
**Issue:** When root exists and binding hashes match, `write_manifest_root_and_chunks` returns `{idempotent: True}` without confirming `chunk_count` chunks exist or `chunk_sha256` match. Safe under single atomic tx first-write (root+chunks co-committed) and plan recovery short-circuit on full agreement. Residual risk: any out-of-band/partial root-only row (manual repair, future multi-step writer) is treated as durable success and commit can terminal-agree on root hash alone.
**Fix:**
```python
if same:
    # load chunks; require len==chunk_count and ordered sha match; else raise batch_conflict
    return {...}
```

## Info

### IN-01: Coalesce unit assertion is tautological

**File:** `mcp_server/tests/test_catalog_prepare_service.py:1337`
**Issue:** `assert plan['evidence_link_count'] == 2 or plan['evidence_link_count'] == 1 or True` always passes; does not lock raw-vs-coalesced policy (ties to WR-01).
**Fix:** Assert exact expected policy (`== 1` if coalesced authority, or document raw and assert `== 2` plus manifest count `== 1`).

### IN-02: Historical a67789a v2 read probe is residual documentation only

**File:** `mcp_server/tests/catalog_phase3b_gate_runner.py:861+`; `test_catalog_commit_neo4j_int.py:3-4,38-40,131+`
**Issue:** Gate runner records HISTORICAL_V2_COMMIT `a67789a` local test-policy query. Current int tests hard-ban forbidden group in params/cypher and pin `oracle-catalog-tool-test`. No present-day product path issues from this residual.

### IN-03: Capabilities feature flags hard-coded post-flip (intentional)

**File:** `mcp_server/src/services/catalog_capabilities.py:146-155`
**Issue:** `prepare_commit=True`, `manifests=True`, `manifest_verification=False` are static. Mutation-free and no `.planning` read — correct for D-33. Future env/config toggle not present (YAGNI unless multi-env rollback needed).

### IN-04: `_write_status_from_row` can return `'error'` without raising for non-entity paths

**File:** `mcp_server/src/services/catalog_service.py:949-958,5322`
**Issue:** Entity path raises first via `_raise_entity_row_error`. Edge path never emits `error_code` today. If status ever becomes `'error'`, results list would carry error while writer still proceeds to evidence/manifest/terminals. Defensive raise-on-error after every domain write would harden atomic contract.
**Fix:** After each domain write status resolve: `if status == 'error': raise ...` uniformly.

## Security / isolation positives (no finding)

- Evidence/manifest param allowlists; forbidden keys stripped (`prepare_evidence_link_params`, manifest prepares).
- Labels/types server-resolved; no client label interpolation into Cypher.
- Plan token: mint via `secrets.token_urlsafe`, store digest only, `hmac.compare_digest` verify; raw token not in commit response DTO.
- `group_id` on every MATCH/MERGE identity; evidence source/target resolved group-scoped before write.
- Failed batch status only in separate post-rollback tx (D-27); never co-committed with manifest/plan COMMITTED.
- Terminal agreement requires plan COMMITTED + batch committed + manifest/request/catalog/artifact/identity bind; partial terminals fail closed without PREPARED revival.
- Int tests + gate runner enforce `oracle-catalog-tool-test` only; ban `oracle-catalog-v2`.

## Critical Issues

None proven. No CR-tier injection, auth bypass, or durable dual-identity commit path demonstrated under the traced contracts.

---

_Reviewed: 2026-07-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
