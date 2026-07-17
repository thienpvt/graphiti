---
phase: 02-provenance-and-atomic-batch
fixed_at: 2026-07-17T12:54:10+07:00
review_path: .planning/phases/02-provenance-and-atomic-batch/02-REVIEW-FIX-3.md
iteration: 4
base: 379ffee
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 02: Final Concurrency Blocker Fix

## Fixed

### BL-04: Provenance validation and mutation were not protected by retained locks

**Files modified:** `mcp_server/src/services/catalog_store.py`, `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_store_unit.py`, `mcp_server/tests/test_catalog_service.py`, `mcp_server/tests/test_catalog_neo4j_int.py`

**Commit:** `ef8a4f7`

**Applied fix:** Source writes now use one fixed, group-scoped Neo4j MERGE/self-SET compare-and-set query. It acquires the source write lock before comparing expected existence, `source_key`, and `content_sha256`; mismatches return a structured `error_code` without applying source updates. Entity and RELATES_TO provenance targets are self-SET in deterministic UUID order, retaining write locks while link state is checked and links are written. Standalone and nested batch paths use the same protocol. Source execution is UUID-sorted while response indices remain request-indexed. Newly created sources and same-batch targets remain supported.

## Verification

- Focused store/service tests: `188 passed in 1.84s`.
- Full catalog unit suite: `303 passed in 2.27s`.
- Live Neo4j CAS regression: `1 passed in 1.63s`; concurrent conflicting updates produced exactly one update and one `batch_conflict`.
- Required live Neo4j integration suite: `35 passed in 23.68s`, zero skipped.
- Combined catalog unit/live suite: `338 passed in 25.31s`.
- Existing MCP regressions: `61 passed in 1.22s`.
- Ruff format check: 5 files formatted.
- Ruff lint: all checks passed.
- Package-scoped Pyright: `0 errors, 0 warnings, 0 informations`.
- Git whitespace check: clean.

## Runtime Observation

**Verdict:** PASS

The public catalog service path was driven against live Neo4j at `bolt://localhost:17687`. A source was created, then two separate service instances submitted conflicting content concurrently. Exactly one response reported `updated`; the other reported `batch_conflict`. The stored source hash matched one contender only. Fixture teardown restored the exact pre-run elementId snapshot.

## Safety

All live writes used only `oracle-catalog-tool-test`. Cleanup deleted only elementIds created by each fixture and asserted the exact before/after snapshot plus unchanged other-group counts. No `clear_graph`, deployment, manifest/config/sample mutation, full ingest, existing-data deletion, registry push, or production-group write occurred.

---

_Fixed: 2026-07-17T12:54:10+07:00_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 4_
