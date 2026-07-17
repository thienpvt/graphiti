---
phase: 00-baseline-inventory-and-compatibility-policy
plan: 01
subsystem: testing
tags: [baseline, inventory, mcp-tools, catalog, canary-offline, ruff, pyright, pytest]

requires: []
provides:
  - Live-grounded 14 legacy + 7 catalog MCP tool inventory with file:line anchors
  - Catalog surface path map (models/services/store/schema/tests/canary)
  - Offline ACCEPT_TAB historical digests and counts
  - Machine-readable pass|fail|skip check ledger for later regression comparison
affects:
  - 00-baseline-inventory-and-compatibility-policy plan 02
  - Phase 1 catalog-v2 contract work

tech-stack:
  added: []
  patterns:
    - Offline historical evidence only (paths/hashes/counts; no live Neo4j)
    - Truthful pass|fail|skip ledger; unavailable checks never marked pass

key-files:
  created:
    - .planning/phases/00-baseline-inventory-and-compatibility-policy/00-BASELINE.md
    - .planning/phases/00-baseline-inventory-and-compatibility-policy/00-baseline-checks.json
  modified: []

key-decisions:
  - "Scoped Pyright to catalog models + catalog services only (research Q2)"
  - "Default-skipped Neo4j int tests; never target oracle-catalog-v2"
  - "Recorded pre-existing canary-script CRLF/hash failures without repair"

patterns-established:
  - "Baseline artifacts cite live @mcp.tool line anchors and offline canary digests only"
  - "Check ledger rows always include name, command, status, exit_code, first_failure_id, notes"

requirements-completed: [BASE-01, BASE-02, BASE-03, BASE-04]

coverage:
  - id: D1
    description: Live inventory of 14 legacy MCP tools and 7 catalog tools with file:line anchors (21 total)
    requirement: BASE-01
    verification:
      - kind: other
        ref: "rg -c @mcp.tool mcp_server/src/graphiti_mcp_server.py == 21; 00-BASELINE.md tool tables"
        status: pass
    human_judgment: false
  - id: D2
    description: Catalog surface map and offline ACCEPT_TAB digests/counts without live Neo4j or canary runner
    requirement: BASE-02
    verification:
      - kind: other
        ref: "00-BASELINE.md ACCEPT_TAB section; canary_executed=false; oracle_catalog_v2_queried=false"
        status: pass
    human_judgment: false
  - id: D3
    description: Truthful pass|fail|skip ledger for catalog pytest/ruff/pyright/neo4j-int
    requirement: BASE-03
    verification:
      - kind: other
        ref: "00-baseline-checks.json status enum validation; catalog suite first_failure_id retained"
        status: pass
    human_judgment: false
  - id: D4
    description: Unavailable or out-of-scope checks recorded as skip; no product repair; safety flags false
    requirement: BASE-04
    verification:
      - kind: other
        ref: "catalog_neo4j_int=skip; ruff/pyright pass; canary_executed=false"
        status: pass
    human_judgment: false

duration: 2min
completed: 2026-07-18
status: complete
---

# Phase 0 Plan 01: Baseline Inventory Summary

**Live 21-tool MCP inventory, offline ACCEPT_TAB digests, and truthful catalog check ledger without canary or Neo4j mutation**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-17T17:36:55Z
- **Completed:** 2026-07-17T17:38:29Z
- **Tasks:** 2
- **Files modified:** 2 created (phase artifacts only)

## Accomplishments

- Inventoried exactly 14 legacy + 7 catalog MCP tools from live `@mcp.tool` registrations
- Mapped catalog models/services/store/schema/tests/canary paths without product edits
- Recorded offline ACCEPT_TAB hashes/counts and disposition (historical only, invalid golden)
- Captured check ledger: catalog suite fail (8 pre-existing), ruff pass, scoped pyright pass, neo4j int skip

## Task Commits

1. **Task 1: Write live inventory and offline ACCEPT_TAB baseline** - `7595cca` (docs)
2. **Task 2: Run targeted checks and record pass fail skip ledger** - `6b416f8` (docs)

**Plan metadata:** (pending final docs commit)

## Files Created/Modified

- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-BASELINE.md` - Tool inventory, surface map, ACCEPT_TAB evidence, check ledger, safety flags
- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-baseline-checks.json` - Machine-readable pass|fail|skip rows + safety flags

## Decisions Made

- Scoped Pyright to catalog modules only; full pyright not required for baseline signal
- Neo4j integration default skip for Phase 0 (no live DB requirement)
- Did not repair Windows CRLF / missing `catalog/catalog.json` canary-script failures (pre-existing baseline noise)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `test_catalog_canary_scripts.py`: 8 pre-existing failures on Windows worktree (CRLF vs LF artifact bytes, missing `catalog/catalog.json`, cascading `artifact_hash_mismatch`). Recorded as fail with first node id; not fixed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- BASE-01..BASE-04 inventory/check baseline ready for plan 02 compatibility/isolation policy
- Later phases can compare against `00-baseline-checks.json` to classify regressions
- Safety flags remain `canary_executed=false`, `oracle_catalog_v2_queried=false`

## Self-Check: PASSED

- FOUND: `00-BASELINE.md`
- FOUND: `00-baseline-checks.json`
- FOUND: commit `7595cca`
- FOUND: commit `6b416f8`
- No product source edited; no STATE.md/ROADMAP.md updates; no remote ops

---
*Phase: 00-baseline-inventory-and-compatibility-policy*
*Completed: 2026-07-18*
