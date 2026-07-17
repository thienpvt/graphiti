---
phase: 02-provenance-and-atomic-batch
fixed_at: 2026-07-17T13:18:24+07:00
review_path: .planning/phases/02-provenance-and-atomic-batch/02-REVIEW-FIX-4.md
iteration: 5
base: c5a8b00
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 02: Final Atomic-Lock Review Fix

## Fixed

### BL-05: Nested batch flattened provenance invariant races

**Files modified:** `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_service.py`

**Commit:** `f40426a`

**Applied fix:** `upsert_catalog_batch` now catches `_ProvenanceInvariantRace` before the generic transaction failure handler. The domain path preserves transaction rollback, writes safe failed batch status in a separate transaction, and returns the structured `exc.code` (`batch_conflict` or `deterministic_uuid_conflict`) instead of `neo4j_transaction_failed`. Unit coverage asserts rollback precedes failed-status persistence, exact status summary, structured response code, and no link mutation.

### BL-06: Provenance lock order relied only on Python input order

**Files modified:** `mcp_server/src/services/catalog_store.py`, `mcp_server/tests/test_catalog_store_unit.py`

**Commit:** `140ace9`

**Applied fix:** `lock_provenance_targets` Cypher now executes `ORDER BY target.uuid, target.kind` after `UNWIND` and before the lock-producing `CALL` subquery. The exact unit assertion verifies both the clause and its position before `CALL (target)`.

## Verification

- Focused atomic-lock tests: `8 passed in 0.44s`.
- Full catalog unit suite: `303 passed in 3.22s`.
- Required live Neo4j integration suite: `35 passed in 23.93s`, zero skipped.
- Combined catalog unit/live suite: `338 passed in 25.11s`.
- Existing MCP regressions: `86 passed in 1.36s`.
- Ruff format check: `16 files already formatted`.
- Ruff lint: `All checks passed!`.
- Package-scoped Pyright: `0 errors, 0 warnings, 0 informations`.
- Git whitespace check: clean.

## Safety

All live writes used only `oracle-catalog-tool-test`. Required live and combined suites completed exact fixture cleanup. A post-run read returned empty node and relationship elementId lists for `oracle-catalog-tool-test`. No `clear_graph`, deployment, manifest/config/sample mutation, full ingest, existing-data deletion, registry push, or production-group write occurred.

---

_Fixed: 2026-07-17T13:18:24+07:00_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 5_
