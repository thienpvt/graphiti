---
phase: 02-provenance-and-atomic-batch
reviewed: 2026-07-17T03:12:00Z
depth: deep
files_reviewed: 17
files_reviewed_list:
  - mcp_server/src/models/catalog_provenance.py
  - mcp_server/src/models/catalog_batch.py
  - mcp_server/src/models/catalog_responses.py
  - mcp_server/src/services/catalog_identity.py
  - mcp_server/src/services/catalog_store.py
  - mcp_server/src/services/catalog_service.py
  - mcp_server/src/graphiti_mcp_server.py
  - mcp_server/tests/test_catalog_identity.py
  - mcp_server/tests/test_catalog_models.py
  - mcp_server/tests/test_catalog_store_unit.py
  - mcp_server/tests/test_catalog_service.py
  - mcp_server/tests/test_catalog_neo4j_int.py
  - mcp_server/tests/fixtures/accept_tab_sanitized.json
  - mcp_server/README.md
  - .planning/phases/02-provenance-and-atomic-batch/02-CONTEXT.md
  - .planning/phases/02-provenance-and-atomic-batch/02-RESEARCH.md
  - .planning/REQUIREMENTS.md
findings:
  critical: 6
  warning: 1
  info: 0
  total: 7
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-17T03:12:00Z
**Depth:** deep
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Deep cross-file review found six correctness/security blockers and one response-accuracy warning. Focused catalog tests passed (`260 passed`), but adversarial probes reproduced the issues below.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Caller hash replaces server-authoritative batch hash

**File:** `mcp_server/src/services/catalog_service.py:3431-3433`
**Issue:** `request_sha256` is accepted without comparison to the canonical server hash. A caller can commit content X with arbitrary hash A, then retry changed content Y with hash A; the second request returns unchanged. This violates IDEN-07, BATC-03, BATC-09.
**Fix:** Compare optional `request_sha256` with the canonical server hash and return `content_hash_mismatch` on mismatch. Persist and compare only the server-derived hash.

### CR-02: Batch provenance bypasses complete preflight and dry-run validation

**File:** `mcp_server/src/services/catalog_service.py:3773-3810,3860-3938`
**Issue:** Dry-run returns before provenance sources, reference times, hashes, existing source conflicts, and targets are processed. Real writes process provenance only after embeddings/schema initialization. Missing provenance targets pass dry-run; invalid sources can fail after side effects; target existence/type is not fully preflighted.
**Fix:** Prepare/coalesce sources, validate hashes/times, resolve all entity/edge targets, and read existing source/link state before dry-run, embedding, schema initialization, or transaction opening.

### CR-03: Nested source content hash is ignored

**File:** `mcp_server/src/services/catalog_service.py:3886-3893`
**Issue:** Batch provenance computes a source digest but never compares optional `content_sha256`; a wrong 64-character source hash can commit.
**Fix:** Call `assert_optional_client_hash(source.content_sha256, digest)` during complete preflight and return `content_hash_mismatch` before side effects.

### CR-04: Provenance-link limits count targets, not generated links

**Files:** `mcp_server/src/models/catalog_provenance.py:120-145`, `mcp_server/src/models/catalog_batch.py:34-40`, `mcp_server/src/services/catalog_service.py:2618-2624,3345-3352`
**Issue:** Every source links to every target, but hard/configured limits count only targets. Sources are unbounded. 5,001 sources plus one target passes a 5,000-link limit while generating 5,001 links.
**Fix:** Validate `len(sources) * (len(entity_targets) + len(edge_targets))` at model and service boundaries; bound source count.

### CR-05: Provenance and status identities lack uniqueness constraints

**File:** `mcp_server/src/services/catalog_store.py:37-47,807-822,908-913,1062-1076`
**Issue:** Schema setup constrains only `Entity` and `RELATES_TO`. Concurrent `MERGE` for `Episodic`, `MENTIONS`, and `CatalogIngestBatch` lacks database-enforced uniqueness, undermining deterministic one-object semantics.
**Fix:** Add fixed composite uniqueness constraints for `(uuid, group_id)` on `Episodic`, `MENTIONS`, and `CatalogIngestBatch`; verify exact shapes via `SHOW CONSTRAINTS`.

### CR-06: Batch status has an unchecked concurrency race

**File:** `mcp_server/src/services/catalog_service.py:3434-3479,4092-4106,4116-4132`
**Issue:** Status is read before preflight and not rechecked inside the domain transaction. Concurrent different-content requests can both proceed; unconditional status updates become last-writer-wins. A failed-status transaction can overwrite a committed status.
**Fix:** Transactionally re-read/claim batch status under the uniqueness constraint. Enforce same-hash unchanged and different-hash conflict in the domain transaction. Make failed-status persistence conditional so it never overwrites committed state.

## Warnings

### WR-01: Non-atomic provenance reports rolled-back writes as created

**File:** `mcp_server/src/services/catalog_service.py:3043-3151`
**Issue:** `atomic=false` still writes all sources in one transaction. If a later source fails, Neo4j rolls back all writes while earlier entries remain reported as `created`.
**Fix:** Require `atomic=true`, use one transaction per source for non-atomic mode, or mark every attempted sibling `rolled_back` after failure.

---

_Reviewed: 2026-07-17T03:12:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
