---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
fixed_at: 2026-07-18T04:27:41Z
review_path: .planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-REVIEW.md
iteration: 2
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-07-18T04:27:41Z
**Source review:** `.planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-REVIEW.md`
**Iteration:** 2

**Summary:**
- Findings in scope: 2 (residual post-f172453 warnings from deep re-review)
- Fixed: 2
- Skipped: 0

Residual scope (orchestrator instruction, not full REVIEW.md body):
1. In-transaction `already_committed` replay undercounts provenance (sources-only).
2. Batch status `provenance_count` remains sources-only despite evidence links in request domain.

Original REVIEW.md WR-02 preflight path already fixed at HEAD `f172453`; iteration 2 closed remaining write-path / status-path gaps.

## Fixed Issues

### WR-R01: In-tx already_committed replay omits evidence links

**Files modified:** `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_service.py`
**Commit:** `7aee976` (`7aee9762f96dd45fd23bd0e56d3337a5430aa4e5`)
**Applied fix:** Added `_batch_provenance_item_count(request)` (sources + evidence_links). Used it for preflight same-hash replay and in-transaction `already_committed` `provenance_unchanged`. Added `test_batch_in_tx_already_committed_counts_evidence_links_as_unchanged`.

### WR-R02: Batch status provenance_count sources-only

**Files modified:** `mcp_server/src/services/catalog_service.py`, `mcp_server/tests/test_catalog_service.py`
**Commit:** `aa76806` (`aa76806b694352a37005b61cb4edd9f1c443cc8c`)
**Applied fix:** Failed and committed `prepare_batch_status_params(... provenance_count=...)` now use `_batch_provenance_item_count(request)`. Added `test_batch_status_provenance_count_includes_evidence_links` (1 source + 1 link = count 2).

## Verification

- Focused unit tests: 3 passed
  - `test_batch_committed_same_hash_counts_evidence_links_as_unchanged`
  - `test_batch_in_tx_already_committed_counts_evidence_links_as_unchanged`
  - `test_batch_status_provenance_count_includes_evidence_links`
- Ruff check: pass
- Ruff format: pass
- Pyright (`catalog_service.py`): 0 errors
- Not run: Neo4j integration, canary, oracle-catalog-v2, clear_graph, deploy, remote mutation

## Commit hashes

| Finding | Short | Full |
|---------|-------|------|
| WR-R01 | `7aee976` | `7aee9762f96dd45fd23bd0e56d3337a5430aa4e5` |
| WR-R02 | `aa76806` | `aa76806b694352a37005b61cb4edd9f1c443cc8c` |
| Base before fixes | `f172453` | `f172453ec6b66aaace01eecc5f7633ffbc7fbde0` |

---

_Fixed: 2026-07-18T04:27:41Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
