---
phase: 02-provenance-and-atomic-batch
fixed_at: 2026-07-17
base: 000d278
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 02: Final Review Fixes

## Fixed

- BLOCKER-01: Standalone and nested-batch provenance transactions now re-read source identity/hash plus preflighted MENTIONS and edge-link state before mutation. Source/link drift aborts and rolls back. Updated-source paths receive the same link-state protection. Commit `86d09b5`.
- BLOCKER-02: Catalog request `group_id` validators now use full-string matching, rejecting trailing newlines and other hidden delimiters. Commit `8d3c28e`.
- WARNING-01: Divergent entity/edge duplicate identities quarantine every occurrence, including later repeats such as A/B/A, and exclude the identity from writes. Commit `6dab8bf`.

## Verification

- Focused final-review regressions: `13 passed` before the updated-source extension.
- Provenance transaction-local drift/new-link selection: `10 passed` after the extension.
- Full catalog unit suite: `301 passed in 2.10s`.
- Required local Neo4j integration suite: `34 passed in 24.21s`, zero skipped.
- Combined catalog suite: `335 passed in 24.94s`.
- Existing MCP regressions: `86 passed in 1.33s`.
- Ruff format: 7 files formatted.
- Ruff lint: all checks passed.
- Package-scoped Pyright: `0 errors, 0 warnings, 0 informations`.
- Git whitespace check: clean.

## Safety

All live writes remained restricted to `oracle-catalog-tool-test`. No deployment, production-group write, full ingest, graph clearing, existing-data deletion, registry push, or manifest mutation. Unrelated working-tree changes were untouched.
