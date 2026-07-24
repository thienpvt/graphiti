---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
plan: wave3-registration-repair
subsystem: mcp-catalog-registration
tags:
  - catalog
  - mcp
  - registration
  - capa
  - compatibility
requires:
  - 02-04 get_catalog_capabilities registration
provides:
  - eight-tool catalog registration contract
  - request-bound seven-tool CONT-07/SAFE-08 split
affects:
  - mcp_server/tests/test_catalog_service.py
tech-stack:
  added: []
  patterns:
    - CATALOG_REQUEST_TOOL_NAMES vs CATALOG_TOOL_NAMES split
key-files:
  created:
    - .planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-WAVE3-REGISTRATION-REPAIR-SUMMARY.md
  modified:
    - mcp_server/tests/test_catalog_service.py
decisions:
  - Registration surface is eight catalog tools after CAPA-01
  - SAFE-08 request-model contract remains seven request-bound tools
  - get_catalog_capabilities is bodyless read tool, not request-bound
metrics:
  duration: ~8m
  completed: 2026-07-18
status: complete
---

# Phase 02 Wave 3: Registration Repair Summary

One-liner: Phase 2 registration contract now expects eight catalog tools including read-only `get_catalog_capabilities`, while preserving fourteen legacy tools.

## Objective

Fix the stale Phase 1 compatibility assertion that catalog MCP registration is exactly seven tools. Phase 2 Plan 04 intentionally registers the eighth tool `get_catalog_capabilities` (CAPA-01), which raised the live total to 22 tools and broke:

`test_mcp_registers_exactly_seven_catalog_tools_and_preserves_legacy_tools`.

## What Changed

### `mcp_server/tests/test_catalog_service.py`

1. Split fixture sets:
   - `CATALOG_REQUEST_TOOL_NAMES` — seven request-bound tools (SAFE-08 / CONT-07)
   - `CATALOG_TOOL_NAMES` — eight tools = request-bound set + `get_catalog_capabilities`
2. Renamed registration test to `test_mcp_registers_exactly_eight_catalog_tools_and_preserves_legacy_tools`
3. Assert:
   - catalog set size == 8
   - request-bound set size == 7
   - legacy set size == 14
   - total registered names == 22
   - `names == CATALOG_TOOL_NAMES | LEGACY_TOOL_NAMES` (no unexpected tools)
4. Request-model binding test now compares against `CATALOG_REQUEST_TOOL_NAMES` only and still asserts capabilities is registered but bodyless

### Product code

None. Live registration already includes `get_catalog_capabilities`; only the stale test contract lagged.

## Requirements

- **CAPA-01**: `get_catalog_capabilities` registered and available without write gate
- **CAPA-09**: `get_status` remains a preserved legacy tool with prior semantics
- Legacy compatibility: all 14 pre-catalog MCP tools still registered

## Verification

| Check | Result |
|-------|--------|
| Registration + capabilities focused tests | 21 passed |
| Full Phase 2 focused suite | 918 passed |
| Ruff check/format on edited test | pass |
| Scoped Pyright on edited test | 2 pre-existing `assert_not_awaited` diagnostics at L2483/L2486 only; no new diagnostics from this change |

Focused suite command:

```bash
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_models.py \
  mcp_server/tests/test_catalog_identity.py \
  mcp_server/tests/test_catalog_service.py \
  mcp_server/tests/test_catalog_topology.py \
  mcp_server/tests/test_catalog_evidence.py \
  mcp_server/tests/test_catalog_hash.py \
  mcp_server/tests/test_catalog_capabilities.py \
  mcp_server/tests/test_catalog_store_unit.py \
  -q --tb=line
```

## Deviations from Plan

None beyond the requested repair scope. Product `CATALOG_TOOL_NAMES` in `graphiti_mcp_server.py` remains the SAFE-08 seven-tool write/request set; read-only capabilities is intentionally outside that rewrite path.

## Known Stubs

None.

## Threat Flags

None — test-only contract repair; no new network, auth, file, or schema surface.

## Out of Scope (honored)

- STATE.md / ROADMAP.md
- canary / oracle-catalog-v2
- store / control-plane / deploy
- product registration code

## Commits

- `685411a` — `fix(02-wave3): expect eight catalog tools including get_catalog_capabilities`

## Self-Check

- FOUND: `mcp_server/tests/test_catalog_service.py`
- FOUND: `test_mcp_registers_exactly_eight_catalog_tools_and_preserves_legacy_tools`
- FOUND: commit `685411a`
- FOUND: base `c7f1f5e76742c5255ccc71d595178c0a0a58b6c7` at agent start
- FOUND: branch `worktree-agent-ade2dfc01ccf5a5f1`

## Self-Check: PASSED
