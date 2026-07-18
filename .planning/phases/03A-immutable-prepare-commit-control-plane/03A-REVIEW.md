---
phase: 03A-immutable-prepare-commit-control-plane
reviewed: 2026-07-18T12:00:00Z
depth: deep
files_reviewed: 21
files_reviewed_list:
  - mcp_server/src/graphiti_mcp_server.py
  - mcp_server/src/config/schema.py
  - mcp_server/src/models/catalog_common.py
  - mcp_server/src/models/catalog_prepare.py
  - mcp_server/src/models/catalog_responses.py
  - mcp_server/src/services/catalog_capabilities.py
  - mcp_server/src/services/catalog_identity.py
  - mcp_server/src/services/catalog_prepared_artifact.py
  - mcp_server/src/services/catalog_service.py
  - mcp_server/src/services/catalog_store.py
  - mcp_server/tests/catalog_phase3a_gate_runner.py
  - mcp_server/tests/run_phase3a_gate.py
  - mcp_server/tests/test_catalog_capabilities.py
  - mcp_server/tests/test_catalog_phase3a_gate_runner.py
  - mcp_server/tests/test_catalog_prepare_models.py
  - mcp_server/tests/test_catalog_prepare_neo4j_int.py
  - mcp_server/tests/test_catalog_prepare_service.py
  - mcp_server/tests/test_catalog_prepare_store.py
  - mcp_server/tests/test_catalog_prepared_artifact.py
  - mcp_server/tests/test_catalog_token.py
  - mcp_server/tests/test_graphiti_mcp_server.py
findings:
  critical: 0
  warning: 7
  info: 4
  total: 11
status: issues_found
---

# Phase 03A: Code Review Report

**Reviewed:** 2026-07-18T12:00:00Z
**Depth:** deep
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Deep adversarial review of the immutable prepare/commit control plane (models, identity/token, artifact, store CAS, service orchestration, MCP surface, capabilities, gate/tests). Cross-file focus: token auth, reassembly integrity, capacity serialization, state machine, zero domain write on prepare, zero external call on commit, restart-safe immutability, and 3B seam safety.

No critical product security holes found in the happy-path design (opaque 256-bit token, domain-separated digest, CREATE-once root/chunks, group lock + active count, CAS table forbidding revive, commit stops at `COMMITTING` without embedder/LLM/queue). Seven warnings remain: fail-closed gaps on corrupt digests, weaker plan-schema ensure than domain schema, prepare skipping committed-batch preflight, evidence membership non-coalesce/collision, wrong store default version string, concurrent identity race error mapping, and soft live expiry assertion.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: `plan_token_matches` raises on length-mismatched stored digest

**File:** `mcp_server/src/services/catalog_identity.py:117-125`
**Issue:** `hmac.compare_digest(actual, stored_digest.lower())` raises `ValueError` when `stored_digest` length ≠ 64 (corrupt Neo4j property, partial write, manual edit). Only `plan_token_digest` `ValueError` is caught. Commit/discard then surface generic MCP `ErrorResponse` instead of structured `prepared_plan_not_found`, and bypass the intended fail-closed auth path.

**Failure scenario:** Root exists with `token_digest='abc'`. Caller presents any token. `plan_token_matches` throws; MCP logs `commit_prepared_catalog_batch failed reason=ValueError`.

**Fix:**
```python
def plan_token_matches(token: str, stored_digest: str) -> bool:
    if not isinstance(stored_digest, str) or not stored_digest:
        return False
    try:
        actual = plan_token_digest(token)
        return hmac.compare_digest(actual, stored_digest.lower())
    except (ValueError, TypeError):
        return False
```

### WR-02: `ensure_plan_schema` lacks lock, once-ready flag, and SHOW verification

**File:** `mcp_server/src/services/catalog_store.py:1861-1889`
**Issue:** Domain identity ensure uses `asyncio.Lock`, double-checked `_schema_ready`, and post-CREATE `SHOW CONSTRAINTS` shape verification (`:223-389`). Plan schema ensure only loops CREATE IF NOT EXISTS, continues on "already exists", never verifies UNIQUENESS shape on `(uuid,group_id)`, `token_digest`, or chunk index. Without verified uniqueness, CREATE-once and global token uniqueness are best-effort only; concurrent prepares can race past the pre-CREATE existence check (`:2250-2260`) and land on driver errors instead of deterministic `prepared_plan_conflict`.

**Failure scenario:** Constraint create no-ops or wrong shape under restricted role; two concurrent prepares for same `plan_uuid` both pass existence MATCH and race CREATE.

**Fix:** Mirror domain path: lock + once-ready; after CREATE, SHOW and require exact property sets; fail closed with `neo4j_schema_failed` if missing.

### WR-03: Prepare skips committed `CatalogIngestBatch` preflight

**File:** `mcp_server/src/services/catalog_service.py:5133-5137`
**Issue:** `prepare_catalog_batch` calls `_prepare_batch_preflight(..., check_batch_status=False)`. Upsert path refuses re-entry when batch is `committed` with hash match/conflict (`:3816-3841`). Prepare can freeze a new control-plane plan for an already-committed `batch_id` (when no prior plan root exists). Phase 3B domain/status claim then collides with terminal batch status.

**Failure scenario:** `upsert_catalog_batch` commits batch B. Later `prepare_catalog_batch` same B + same body succeeds, returns token. Commit claim → 3B status claim fails or double-writes.

**Fix:** Use `check_batch_status=True` on prepare (or equivalent): `committed`+same hash → structured conflict/no new token; `committed`+different hash → `batch_conflict`.

### WR-04: Evidence membership not coalesced; `link_key` omits excerpt → same UUID, divergent content

**File:** `mcp_server/src/services/catalog_service.py:5275-5286`; `mcp_server/src/services/catalog_identity.py:209-233`
**Issue:** Artifact membership iterates raw `evidence_links` without `coalesce_byte_identical_evidence_links` (used only in `batch_request_canonical_payload`). `evidence_link_key` excludes `excerpt`/transport hash. Two links with same identity material but different excerpts share UUID, different `content_sha256`, both enter membership. 3B evidence apply has no single authoritative row.

**Failure scenario:** Prepare with two evidence rows same source/target/kind/locator, different excerpts → membership list has duplicate `uuid` with conflicting digests; commit reassembly succeeds; domain write ambiguous.

**Fix:** Coalesce byte-identical links; reject same `link_key` with differing `evidence_canonical_payload` at preflight (`provenance_link_conflict` / `deterministic_uuid_conflict`) before serialize.

### WR-05: Store default `canonicalization_version` is wrong sentinel `canon-v1`

**File:** `mcp_server/src/services/catalog_store.py:2114-2116`
**Issue:** `prepare_prepared_plan_params` defaults missing `canonicalization_version` to `'canon-v1'`. Authority is `CANONICALIZATION_VERSION = 'catalog-canonical-v1'`. Service currently passes the correct value; any alternate caller or partial params map persists a version that fails `_verify_frozen_plan_binding` forever (`catalog_service.py:5593-5594`).

**Failure scenario:** Future/internal create omits field → root stores `canon-v1` → every commit binding check returns `prepared_plan_conflict`.

**Fix:**
```python
'canonicalization_version': str(
    fields.get('canonicalization_version') or 'catalog-canonical-v1'
),
```
Prefer importing `CANONICALIZATION_VERSION` (or require explicit field with no wrong default).

### WR-06: Concurrent same-identity prepare maps uniqueness failure to generic Neo4j error

**File:** `mcp_server/src/services/catalog_store.py:2250-2268`; `mcp_server/src/services/catalog_service.py:5440-5478`
**Issue:** Existence check then CREATE is not a single atomic Cypher predicate. Loser of a unique-constraint race raises driver exception → service `except Exception` → `neo4j_transaction_failed`, not `prepared_plan_conflict`. Clients cannot distinguish retryable identity conflict from infra failure.

**Failure scenario:** Two parallel prepares identical `batch_id|request_sha256`; one succeeds; other gets constraint error wrapped as `neo4j_transaction_failed` with empty token.

**Fix:** Catch constraint/client errors on plan/chunk CREATE and map to `prepared_plan_conflict`; or `MERGE`+`ON CREATE` with post-check that existing `artifact_sha256` matches (still no token re-issue).

### WR-07: Live expiry proof allows residual `PREPARED` (gate softness)

**File:** `mcp_server/tests/test_catalog_prepare_neo4j_int.py:599-628`
**Issue:** After TTL sleep + commit, assertion accepts `state in ('EXPIRED', 'PREPARED')`. Documented race hedge weakens the live immutable/expiry proof the gate cites for `prepare_commit=true`. A permanent expiry CAS bug can still pass if the error code is `prepared_plan_expired` while state remains `PREPARED` without a forced second-pass requirement in all cases.

**Failure scenario:** Expiry CAS no-ops; first commit returns expired via wall-clock branch without persisting `EXPIRED`; test still green when state stays `PREPARED` and optional second call also only checks error code.

**Fix:** Require eventual `EXPIRED` (retry loop with bound) or assert `EXPIRED` after the access path that claims to mark expired; fail if still `PREPARED` after N attempts.

## Info

### IN-01: Stranded `COMMITTING` holds active capacity indefinitely

**File:** `mcp_server/src/services/catalog_store.py:1898-1905`, `2034-104`
**Issue:** Active count always includes `COMMITTING` regardless of age. Per D-12/research, no timeout reset to `PREPARED`. Crash after claim fills `max_active_plans_per_group` until ops/3B finalizes. Intentional residual — document runbook; 3B must complete or provide bounded operator recovery that cannot revive terminals.

### IN-02: Discard does not pre-mark expired `PREPARED` as `EXPIRED`

**File:** `mcp_server/src/services/catalog_service.py:5914-5948`
**Issue:** Research CAS table lists discard condition “not expired”; implementation allows `PREPARED→DISCARDED` without expiry check. Capacity-safe (neither state counts as active after discard). Prefer access-path expire-then-conflict for consistency with commit.

### IN-03: Token match unit test is source-string only

**File:** `mcp_server/tests/test_catalog_token.py:95-101`
**Issue:** Asserts `'compare_digest' in src` rather than behavioral length-mismatch / non-hex stored digest cases (would have caught WR-01).

### IN-04: `features.prepare_commit` hardcoded `True` in pure capabilities

**File:** `mcp_server/src/services/catalog_capabilities.py:146-148`
**Issue:** Always true at runtime regardless of Neo4j connectivity. Matches post-gate package authority (D-29), not live readiness. Acceptable if ops treat capabilities as build/contract discovery only.

## Cross-file notes (no separate finding)

- Token mint: `secrets.token_urlsafe(32)`; digest domain `graphiti.catalog.plan_token.v1|`; raw token not in artifact/params/logs — OK.
- Reassembly: ordered indices, offset chain, b64 validate, per-chunk + artifact digests — fail closed — OK.
- Commit path: no embedder/LLM/queue; stops at `COMMITTING` — OK for 3A.
- Prepare write labels: `CatalogPreparedPlan` / `CatalogPreparedPlanChunk` / `CatalogPlanGroupLock` only in create path — OK.
- MCP tools registered; `CATALOG_TOOL_NAMES` includes prepare/commit/discard; SAFE-08 rewrite covers them — OK.
- Artifact body matches research membership shape; full domain fields live under `request_canonical` for 3B rebuild — OK if 3B uses that contract.

---

_Reviewed: 2026-07-18T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
