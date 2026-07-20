---
phase: 02
plan: WAVE2-LINT-REPAIR
subsystem: catalog-mcp
tags: [ruff, lint, phase-2, topology, evidence]
requires:
  - phase-2-merge-base-c925ed4
provides:
  - ruff-clean-catalog-evidence
  - ruff-clean-catalog-topology-tests
affects:
  - mcp_server/src/models/catalog_evidence.py
  - mcp_server/tests/test_catalog_topology.py
tech-stack:
  added: []
  patterns:
    - Combined nested if into single compound condition (SIM102)
    - Module-top imports with E402 after sys.path insert (I001)
key-files:
  created:
    - .planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-WAVE2-LINT-REPAIR-SUMMARY.md
  modified:
    - mcp_server/src/models/catalog_evidence.py
    - mcp_server/tests/test_catalog_topology.py
decisions:
  - Minimal behavior-preserving Ruff fixes only; no product logic changes
  - STATE/ROADMAP/canary/oracle/store/control-plane/deployment left untouched
metrics:
  duration: ~5m
  completed: 2026-07-18
status: complete
---

# Phase 02 Plan WAVE2-LINT-REPAIR: Ruff SIM102/I001 Summary

Collapsed nested end_line guard and hoisted topology-test imports so Phase 2 merge base `c925ed4` is Ruff-clean on the two reported defects.

## What Shipped

1. **SIM102** — `CatalogEvidenceLocator._end_ge_start` nested `if` collapsed to one compound condition.
2. **I001** — `CatalogEdgeItem` and `ValidationError` moved from mid-file to module-top import block (after `sys.path` insert, with existing E402 pattern).

## Verification

| Check | Result |
|-------|--------|
| `ruff check` on both files | All checks passed |
| `ruff format --check` on both files | 2 files already formatted |
| `pyright` scoped to both files | 0 errors, 0 warnings |
| `pytest tests/test_catalog_topology.py` | 315 passed |

## Commits

- `a09c6f2` — `fix(02): repair Ruff SIM102 and I001 from Phase 2 merge base`

## Base / Worktree

- Branch: `worktree-agent-ab4daf578ebdca96f`
- Expected base: `c925ed4b3b21c286fe3e7143c76fb2c6a5894543`
- Pre-fix HEAD: `c925ed4b3b21c286fe3e7143c76fb2c6a5894543`

## Deviations from Plan

None - plan executed exactly as written.

## Scope Guard

Not modified: STATE.md, ROADMAP.md, canary, oracle-catalog-v2, store/control-plane, deployment, other product files.

## Self-Check: PASSED

- FOUND: `mcp_server/src/models/catalog_evidence.py`
- FOUND: `mcp_server/tests/test_catalog_topology.py`
- FOUND: commit `a09c6f2`
