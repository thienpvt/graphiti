---
phase: 01-strict-contracts-and-catalog-v2-identity
plan: 09
subsystem: catalog-contracts
tags: [pydantic, validation, graph-key, provenance, fastmcp, tdd, iso8601]

requires:
  - phase: 01-strict-contracts-and-catalog-v2-identity
    provides: Plan 01-08 historical green gate and catalog request model surface
provides:
  - CR-02 model-boundary ISO-8601 reference_time validation preserving exact source string
  - WR-01 exact malformed graph-key field locations across entity/edge/provenance/batch routes
  - Fixed safe CatalogService timestamp parse fallback without parser/input leakage
  - FastMCP protocol no-leak zero-side-effect regression for CR-02/WR-01
affects:
  - 01-10
  - 01-11
  - Phase 1 readiness reconsideration

tech-stack:
  added: []
  patterns:
    - temporary timestamp normalize for parse only; return original string
    - reusable located graph-key grammar ValidationError helper
    - fixed defensive service parse message separate from content-hash handling

key-files:
  created: []
  modified:
    - .planning/phases/01-strict-contracts-and-catalog-v2-identity/01-VALIDATION.md
    - .planning/phases/01-strict-contracts-and-catalog-v2-identity/01-PHASE1-GATE.md
    - mcp_server/src/models/catalog_graph_key.py
    - mcp_server/src/models/catalog_entities.py
    - mcp_server/src/models/catalog_edges.py
    - mcp_server/src/models/catalog_provenance.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/tests/test_catalog_models.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Keep graphiti_mcp_server.py read-only; prove FastMCP via tests only"
  - "validate_entity_graph_key_at is the single reusable located helper for grammar and shell mismatch"
  - "CR-01 and WR-02 remain delegated to Plan 01-10; readiness stays false"

patterns-established:
  - "Shell-less nested models validate grammar at concrete key fields so parent nesting prepends naturally"
  - "Service defensive timestamp catch uses fixed validation_error message; never str(exc)"

requirements-completed: [CONT-01, CONT-02, CONT-03, CONT-04, CONT-07, CONT-08, IDEN-03, IDEN-04, IDEN-05, SAFE-08, TEST-01, TEST-03]

coverage:
  - id: D1
    description: Stale Phase 1 readiness invalidated before product edits
    requirement: TEST-01
    verification:
      - kind: other
        ref: git show ea5cd93 --name-only; nyquist_compliant=false; ready_for_phase_2=false
        status: pass
    human_judgment: false
  - id: D2
    description: CR-02 reference_time model validation preserves accepted exact strings and rejects malformed at ('reference_time',)
    requirement: CONT-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_gap_cr02_reference_time_accepts_iso_forms_and_preserves_exact_input
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_gap_cr02_malformed_reference_time_fails_at_exact_field_location
        status: pass
    human_judgment: false
  - id: D3
    description: CR-02 FastMCP protocol rejects malformed timestamps with safe structured paths and zero side effects
    requirement: SAFE-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_gap_cr02_fastmcp_malformed_reference_time_no_leak_no_side_effect
        status: pass
    human_judgment: false
  - id: D4
    description: WR-01 exact malformed graph-key locations across upsert/resolve/verify/edge/provenance/batch
    requirement: IDEN-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_gap_wr01_malformed_graph_key_reports_exact_field_location
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_gap_wr01_fastmcp_malformed_graph_key_exact_path_no_side_effect
        status: pass
    human_judgment: false
  - id: D5
    description: Grammar-valid FE key under BO shell remains invalid_system_key at exact field path
    requirement: IDEN-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_gap_wr01_valid_grammar_shell_mismatch_keeps_invalid_system_key
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_gap_wr01_fastmcp_shell_mismatch_keeps_invalid_system_key
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-07-18
status: complete
---

# Phase 1 Plan 09: Provenance Timestamp and Graph-Key Location Hardening Summary

**CR-02 ISO-8601 `reference_time` model validation with exact-string preservation, plus WR-01 exact malformed graph-key field locations, closed via TDD without race/store or MCP-wrapper production edits.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-18T00:42:23Z
- **Completed:** 2026-07-18T00:47:39Z
- **Tasks:** 3/3
- **Files modified:** 9

## Accomplishments

- Invalidated stale Phase 1 readiness (`nyquist_compliant=false`, `ready_for_phase_2=false`) before any product/test edit.
- Closed CR-02: accepted Z/z/offsets/naive/fractional/trailing-space timestamps keep exact submitted bytes; malformed times fail at `reference_time` with fixed safe diagnostics.
- Closed WR-01: malformed grammar reports exact nested field locations; grammar-valid shell mismatch retains typed `invalid_system_key`.
- FastMCP protocol tests prove zero body/service/store/embedder activity and no sentinel/parser/ValidationError leakage.
- CR-01 and WR-02 explicitly left for Plan 01-10; local readiness remains false pending 01-10/01-11 and independent audits.

## Task Commits

Integrated worktree HEAD ancestry (primary base `401d814`):

1. **Task 1: Invalidate stale Phase 1 readiness** - `291b6e1` (docs)
2. **Task 2: Add failing CR-02 and WR-01 contract tests** - `f3843e9` (test RED)
3. **Task 3: Implement safe timestamp validation and exact graph-key locations** - `7f5b156` (feat GREEN)
4. **Follow-up: Drop over-strict space-separator timestamp case** - `02f4c99` (test)
5. **Plan metadata** - `b441307` / final hash note `0f5f692`

_Note: RED commit `f3843e9` preserved independently; not amended into GREEN. Pre-integration hashes `ea5cd93`/`9f5599c`/`72deb07`/`f63a663`/`253e87e` are historical only._

## Files Created/Modified

- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-VALIDATION.md` - readiness false + open-finding invalidation note
- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-PHASE1-GATE.md` - `ready_for_phase_2=false` current authority
- `mcp_server/src/models/catalog_graph_key.py` - located grammar helper via `validate_entity_graph_key_at`
- `mcp_server/src/models/catalog_entities.py` - shell-less entity/resolve/verify graph-key locations
- `mcp_server/src/models/catalog_edges.py` - source/target graph-key locations
- `mcp_server/src/models/catalog_provenance.py` - `reference_time` field validator + entity-target locations
- `mcp_server/src/services/catalog_service.py` - fixed defensive timestamp fallback (standalone + batch)
- `mcp_server/tests/test_catalog_models.py` - CR-02/WR-01 model matrix
- `mcp_server/tests/test_catalog_service.py` - FastMCP protocol no-leak/no-side-effect cases

## Decisions Made

- No production edit to `graphiti_mcp_server.py`; existing `CatalogSafeFastMCP` proven by protocol tests.
- One reusable located helper for grammar failures; parent shell checks keep `invalid_system_key`.
- Python 3.10 `fromisoformat` accepts space-separated ISO forms; dropped that over-strict malformed case after RED without weakening remaining assertions.
- CR-01 race/store and WR-02 Neo4j fixture work remain Plan 01-10 only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Space-separated ISO timestamp accepted by datetime.fromisoformat**
- **Found during:** Task 3 GREEN
- **Issue:** Malformed matrix included `2024-01-15 10:30:00Z`, which Python 3.10 parses successfully after temporary Z-normalization.
- **Fix:** Removed only that over-strict case; retained non-ISO, out-of-range, and sentinel cases.
- **Files modified:** `mcp_server/tests/test_catalog_models.py`
- **Verification:** focused 38 passed; full 430 passed; ruff 0; pyright 0
- **Committed in:** `f63a663`

## Verification Results

| Check | Exit | Result |
|-------|-----:|--------|
| collect-only `-k "gap_cr02 or gap_wr01"` | 0 | 39 then 38 selected after matrix tweak; both selectors present |
| RED wrapper (inner pytest) | 1 inner / 0 outer | historical RED at `9f5599c` |
| focused GREEN `-k "gap_cr02 or gap_wr01"` | 0 | 38 passed |
| full two-file regression | 0 | 430 passed |
| ruff scoped files | 0 | All checks passed |
| pyright MCP-scoped exact files | 0 | 0 errors, 0 warnings |

## TDD Gate Compliance

1. RED commit present: `9f5599c test(01-09): add failing provenance and graph-key validation coverage`
2. GREEN commit present after RED: `72deb07 feat(01-09): harden provenance and graph-key validation`
3. Optional follow-up test commit: `f63a663`

## Safety

- Canary: none
- Live DB / Neo4j probe: none
- `oracle-catalog-v2` query/mutation/reuse: none
- Network/deploy/push/merge/tag/clear/delete/full ingest: none
- Dependency/lockfile/catalog dump edits: none
- `graphiti_mcp_server.py`: unchanged
- Test group only: `oracle-catalog-tool-test`
- Readiness remains false (`nyquist_compliant=false`, `ready_for_phase_2=false`)

## Deferred / Delegated

- **CR-01** concurrent entity-write race → Plan **01-10**
- **WR-02** stale Neo4j integration fixtures → Plan **01-10**
- Local readiness reconsideration → Plan **01-11** only after 01-09 and 01-10 pass
- Independent audits remain mandatory; Phase 2 blocked

## JSON argv outcomes (Plan 01-11 refresh)

| Check | argv summary | Exit |
|-------|--------------|-----:|
| focused CR-02/WR-01 | `pytest ... -k "gap_cr02 or gap_wr01"` | 0 (historical 38 passed) |
| two-file regression | models + service full | 0 (historical 430 passed) |
| ruff / MCP pyright | scoped product+test files | 0 |

## Self-Check: PASSED

- FOUND: production and test files listed above
- FOUND: commits `291b6e1`, `f3843e9`, `7f5b156`, `02f4c99`, `b441307`, `0f5f692`
- FOUND: readiness flags false pending Plan 01-11 apply
