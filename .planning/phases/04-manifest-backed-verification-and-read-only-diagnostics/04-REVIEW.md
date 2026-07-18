---
phase: 04-manifest-backed-verification-and-read-only-diagnostics
reviewed: 2026-07-19T00:00:00Z
reviewed_head: 92cee52932f1d37154b08911dbc6c2cb81cbe493
depth: deep
files_reviewed: 6
files_reviewed_list:
  - mcp_server/src/services/catalog_service.py
  - mcp_server/src/services/catalog_store.py
  - mcp_server/tests/test_catalog_evidence_read.py
  - mcp_server/tests/test_catalog_manifest_read.py
  - mcp_server/tests/test_catalog_resolve_edges.py
  - mcp_server/tests/test_catalog_verify_manifest.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 4: Code Review Report

**Reviewed:** 2026-07-19T00:00:00Z
**Reviewed HEAD:** `92cee52932f1d37154b08911dbc6c2cb81cbe493`
**Depth:** deep
**Files Reviewed:** 6
**Status:** clean

## Summary

Deep re-review of Phase 4 fail-closed diagnostics after product fix commit `92cee52`. All eight original Critical/Warning findings are fixed. Durable manifest remains sole expected membership authority; live rows stay observations only; batch verify requires `status=committed`; server-derived UUIDv5 mismatch is `manifest_mismatch`; explicit keys stay separate from membership `missing`; edge primary status mirrors dominant anomaly; evidence `found_target` requires exact UUID probe; evidence extras use group+batch observation query. No new Critical or Warning defects.

## Verification

- Targeted new/regression tests + affected modules: 52 passed (pre-commit).
- Phase 4 focused 10-file suite: **380 passed**.
- Gate runner `run` at HEAD `92cee52`: `local_gate_pass=true`, `unit_service_pass=true`, `ready_for_phase_5=true`, `manifest_verification=true`, `canary_executed=false`, `oracle_catalog_v2_queried=false` (current), historical `a67789a` preserved.
- Ruff check/format: clean on changed scope.
- Pyright (mcp_server root) on `catalog_service.py` + `catalog_store.py`: 0 errors.
- No DB/integration, canary, deploy, graph clear, or forbidden-group access during re-review.

## Critical Issues

None remaining.

## Warnings

None remaining.

## Info

None.

## Prior findings disposition

| ID | Title | Status | Evidence |
|----|-------|--------|----------|
| CR-01 | Edge resolve used entity batch limit | **Fixed** | `_read_gate(..., max_items, limit_name)`; `resolve_typed_edges` passes `max_edges_per_batch`; `test_edge_batch_limit_uses_max_edges` |
| CR-02 | Explicit keys conflated with membership missing | **Fixed** | batch+keys absent keys → `anomalies_explicit_*` / `explicit_key_missing`; membership `missing` is manifest-only; verify tests |
| WR-01 | Evidence extras not batch-scoped | **Fixed** | `match_evidence_links_for_batch` (group_id + batch_id); `_verify_evidence_links(..., batch_id=...)` |
| WR-02 | `found_target` from evidence link presence | **Fixed** | `get_entity_by_uuid` / `get_edge_by_uuid` probe; `test_found_target_requires_probe` |
| WR-03 | Manifest UUID not re-derived | **Fixed** | server UUIDv5 recompute; mismatch → `manifest_uuid_mismatch` / `manifest_mismatch` |
| WR-04 | Verify without committed status | **Fixed** | after status row load require `status_val == 'committed'` else validation_error, no manifest/live reads |
| WR-05 | Manifest category counts vs list lengths | **Fixed** | all four category counts must match list lengths fail-closed; `test_counts_list_length_mismatch_fail_closed` |
| WR-06 | Edge resolve status always `found` | **Fixed** | primary status from ordered anomalies (`duplicate_edge_key`, `edge_type_mismatch`, ...); `test_edge_status_mirrors_primary_anomaly` |

## Fix commit

- `92cee52` — `fix(04): deep-review CR/WR fail-closed diagnostics`
- Files: `catalog_service.py`, `catalog_store.py`, four Phase 4 test modules (+609/−76)

## Cross-file notes (no extra findings)

- Durable manifest remains sole expected membership authority; live Neo4j rows are observations only.
- Explicit-key anomalies never promote into section membership `missing`.
- Evidence extras observation is group-scoped `batch_id` query; not membership authority.
- Historical v2 axis (`a67789a`) preserved under `historical_audit`; current axis remains false.
- Existing 28-tool contract and fixed server Cypher parameterization unchanged.

---

_Reviewed: 2026-07-19T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer / deep-review fix)_
_Depth: deep_
_HEAD: 92cee52932f1d37154b08911dbc6c2cb81cbe493_
