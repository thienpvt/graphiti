---
phase: 02-provenance-and-atomic-batch
fixed_at: 2026-07-17
base: da2e110
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 02: Second-Pass Review Fixes

## Fixed

- BL-01: Deterministic provenance UUID indexing now coalesces identical sources and rejects every divergent occurrence independent of order. Commit `4d70c8f`.
- BL-02: Atomic batch transactions re-read projected unchanged entities and edges, validating identity, type, endpoints, and content hash before committed status. Commit `a510e67`.
- BL-03: Newly created provenance links force source result `updated`; `Episodic.entity_edges` unions requested edge UUIDs without deleting existing links. Commit `1f85bab`.
- BL-04: Unchanged-source MENTIONS and edge-link preflight read failures return structured `internal_error` before schema, embedding, or transaction work. Commit `a06b19a`.
- WR-02: Dry-run batch responses include stable provenance occurrence results and created/updated/unchanged counts, including coalesced duplicates. Included in `4d70c8f`.
- T-02-40: Live integration isolation test no longer writes `oracle-catalog-tool-test-canary`; it performs a read-only missing-target check within the authorized group contract. Commit `3e22f5e`.
- Test diagnostics: Optional mock call access and unused test state corrected. Commit `8ff10ca`.

## Verification

- Focused duplicate/dry-run tests: `6 passed`.
- Focused provenance read-failure tests: `4 passed`.
- Focused unchanged entity/edge race tests: `2 passed`.
- Focused provenance link/status/store tests: `3 passed`.
- Full catalog unit suite: `282 passed in 3.40s`.
- Ruff lint: all changed files passed.
- Ruff format: all changed files formatted.
- Package-scoped Pyright: `0 errors, 0 warnings, 0 informations`.
- Git whitespace check: clean.
- Required local Neo4j integration suite: `34 passed in 23.57s`, zero skipped.
- Combined catalog suite: `316 passed in 25.55s`.
- Existing MCP regressions: `86 passed in 1.48s`.

## Safety

No deployment, live-group writes, full ingest, graph clearing, existing-data deletion, or writes outside `oracle-catalog-tool-test`. Unrelated configuration, manifests, `.codegraph`, `catalog/`, and sample catalog files untouched.
