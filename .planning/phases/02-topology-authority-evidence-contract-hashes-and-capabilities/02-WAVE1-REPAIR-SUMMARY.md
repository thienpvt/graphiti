---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
plan: wave1-repair
subsystem: catalog-topology
tags: [post-merge-repair, topology, field-path, enforced-by]

requires:
  - phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
    provides: EDGE_ENDPOINT_MAP finite authority + CatalogEdgeItem topology preflight
provides:
  - Exact nested field paths for malformed edge graph keys
  - EnforcedBy evidence test aligned to Constraint→Table pair
affects:
  - Wave 2 / plan 02-03 provenance Cartesian seam work

tech-stack:
  added: []
  patterns:
    - graph-key grammar before topology on CatalogEdgeItem
    - finite-map endpoint fixtures for EnforcedBy success path

key-files:
  created: []
  modified:
    - mcp_server/src/models/catalog_edges.py
    - mcp_server/tests/test_catalog_models.py

key-decisions:
  - "Grammar validation precedes topology so malformed keys never collapse to edges.N"
  - "EnforcedBy success fixture uses Constraint→Table; no map broadening"
  - "Cartesian provenance entity_targets residuals owned by 02-03; left untouched"

requirements-completed: []

duration: 15min
completed: 2026-07-18
status: complete
---

# Phase 02 Wave 1 Repair Summary

**Post-merge topology/path repair: exact edge graph-key locs + EnforcedBy Constraint→Table fixture; no map broadening.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 1 fix commit + summary
- **Files modified:** 2 product/test + 1 summary

## What Was Fixed

### 1. `test_edge_enforced_by_requires_evidence`

- **Symptom:** Success path still used default Schema→Table endpoints; finite `EDGE_ENDPOINT_MAP` rejects that pair for `EnforcedBy`.
- **Fix:** Test fixture retargeted to documented pair `(Constraint, Table)` with valid graph keys. Map unchanged.
- **Files:** `mcp_server/tests/test_catalog_models.py`
- **Commit:** `59977c4`

### 2. Malformed edge graph-key field paths (`edges.0` → `edges.0.source_graph_key`)

- **Symptom:** `CatalogEdgeItem` model validator ran topology before graph-key grammar. Illegal pairs (e.g. Table→Table on `Contains` after source key override) raised bare `ValueError` at `edges.N`, masking exact `source_graph_key` / `target_graph_key` locs.
- **Fix:** Reorder item validator: graph-key grammar (`validate_entity_graph_key_at` with exact loc) then topology. Pair authority preserved.
- **Files:** `mcp_server/src/models/catalog_edges.py`
- **Commit:** `59977c4`

### 3. `invalid_system_key` precedence (topology scope)

- Nested shell-mismatch paths for edges already use request-level `validate_entity_graph_key_at(..., system_key=...)`.
- After grammar-first reorder, item-level topology no longer preempts exact key locs for malformed keys.
- Model-level `test_graph_key_mismatch_has_exact_nested_invalid_system_key_location` and entity WR-01 mismatch tests pass under topology ownership.

## Verification

| Suite | Result |
|-------|--------|
| `test_catalog_models.py` | pass |
| `test_catalog_topology.py` | pass |
| `test_catalog_edge_probe.py` | pass |
| `test_catalog_evidence.py` | pass |
| Ruff check/format (modified) | pass |
| Pyright `catalog_edges.py` | 0 errors |

Focused owned regressions fixed:

- `test_edge_enforced_by_requires_evidence`
- `test_gap_wr01_malformed_graph_key_reports_exact_field_location` (edge source/target cases)
- FastMCP edge path cases for `edges.0.source_graph_key` / `target_graph_key`

## Remaining Failures (owner: 02-03)

All residual failures use Cartesian nested provenance (`entity_targets` / service seam). Not topology/path. Do not re-add Cartesian fields to catalog-v2 batch (EVID-14).

| Test | Failure shape | Owner |
|------|---------------|-------|
| `test_batch_dry_run_rejects_bad_nested_source_hash_before_side_effects` | `NestedProvenancePayload` missing `entity_targets` attr | 02-03 |
| `test_batch_dry_run_resolves_missing_provenance_target_before_side_effects` | NestedProvenancePayload ValidationError | 02-03 |
| `test_batch_dry_run_reports_provenance_projection_counts_and_duplicates` | missing `entity_targets` attr | 02-03 |
| `test_batch_divergent_provenance_duplicate_is_order_independent[*]` | missing `entity_targets` attr | 02-03 |
| `test_batch_unchanged_provenance_link_read_failure_is_structured[*]` | NestedProvenancePayload ValidationError | 02-03 |
| `test_batch_atomic_cas_or_locked_link_drift_aborts_before_link_mutation[*]` | NestedProvenancePayload ValidationError | 02-03 |
| `test_batch_writes_edges_before_provenance_append_in_same_transaction` | NestedProvenancePayload ValidationError | 02-03 |
| `test_fastmcp_graph_key_mismatch...[...provenance.entity_targets.0.graph_key]` | Cartesian path rejected at `provenance` | 02-03 |
| `test_gap_wr01_fastmcp_malformed...[...provenance.entity_targets.0.graph_key...]` | Cartesian path rejected at `provenance` | 02-03 |

Merged focused catalog suite after repair: **14 failed / 791 passed**. All 14 are 02-03 Cartesian/service seam. Zero topology/path/system-precedence failures remain under 02-01 ownership.

## Deviations from Plan

None beyond scoped auto-fix of genuine post-merge regressions listed in the repair brief.

## Known Stubs

None.

## Threat Flags

None. No new endpoints, auth paths, or Cypher surface.

## Safety

- No payload/log leakage introduced.
- No `oracle-catalog-v2` query/mutate.
- No canary/store/control-plane/prepare/deploy.
- STATE.md / ROADMAP.md untouched by design.

## Self-Check: PASSED

- `mcp_server/src/models/catalog_edges.py` FOUND
- `mcp_server/tests/test_catalog_models.py` FOUND
- commit `59977c4` FOUND
- SUMMARY path FOUND
