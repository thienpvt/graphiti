---
phase: 05-verification-security-compatibility-and-migration-docs
plan: 04
subsystem: testing
tags: [fastmcp, neo4j, compatibility, isolation, security]
requires:
  - phase: 05-verification-security-compatibility-and-migration-docs
    provides: Phase 5 Wave 0 RED scaffolding and live verification infrastructure
provides:
  - Canonical public contract baseline for all 14 legacy MCP tools
  - Exact independent 14 legacy / 14 catalog / 28 union registration proof
  - Live Neo4j TEST-11 isolation, rollback, search, evidence, and control-label proof
  - Pre-existing-safe elementId-scoped live teardown
  - Run-scoped catalog integration identities
  - requirements: [SAFE-09, SAFE-10, TEST-11]
affects: [mcp-compatibility, catalog-verification, phase-5-audit]
tech-stack:
  added: []
  patterns: [canonical FastMCP schema comparison, runtime query-parameter auditing, elementId-scoped teardown]
key-files:
  created:
    - mcp_server/tests/fixtures/legacy_mcp_contract_baseline.json
  modified:
    - mcp_server/tests/test_legacy_mcp_contract_compatibility.py
    - mcp_server/tests/catalog_neo4j_fixtures.py
    - mcp_server/tests/test_catalog_neo4j_int.py
    - mcp_server/tests/test_catalog_commit_neo4j_int.py
    - mcp_server/tests/test_catalog_prepare_neo4j_int.py
key-decisions:
  - "Canonicalize schemas by removing only non-behavioral title and description metadata."
  - "Prove zero outside-group writes through request propagation and audited query parameters; never query another group."
  - "Use run-scoped identities and elementId differences so live tests preserve all pre-existing test-group records."
patterns-established:
  - "Live safety: query only oracle-catalog-tool-test and delete only elementIds created after the fixture snapshot."
  - "Compatibility: compare signatures, defaults, complete canonical input/output schemas, and fake-backed response references."
requirements-completed: [SAFE-09, SAFE-10, TEST-11]
coverage:
  - id: D1
    description: Exact canonical compatibility for 14 legacy tools and exact 28-tool union
    requirement: SAFE-09
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_legacy_mcp_contract_compatibility.py (9 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: Empty, ordering, concurrency, and group-isolation safety contracts
    requirement: SAFE-10
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_gates.py (10 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: Live Neo4j rollback, search interoperability, evidence/manifest, control-label, and exact-group proofs
    requirement: TEST-11
    verification:
      - kind: integration
        ref: "CATALOG_INT_REQUIRED=1 CATALOG_CEILING_SMOKE=1 pytest catalog live modules (62 tests)"
        status: pass
    human_judgment: false
duration: 4h
completed: 2026-07-19
status: complete
---

# Phase 5 Plan 4: MCP Compatibility and Live TEST-11 Summary

**Frozen 14-tool legacy FastMCP contracts plus a fully passing 62-test live Neo4j safety suite using exact-group auditing and test-created-only teardown**

## Performance

- **Duration:** 4h
- **Started:** 2026-07-18
- **Completed:** 2026-07-19
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Froze and verified names, signatures, required/default parameters, canonical input/output schemas, and response references for exactly 14 legacy tools.
- Proved exactly 14 catalog tools, disjoint sets, original-seven preservation, and an exact 28-tool union.
- Added live TEST-11 proofs for control-label exclusion and exact `oracle-catalog-tool-test` propagation across direct, prepare, and commit paths.
- Ran the complete live Neo4j suite: 62 passed, including rollback, search interoperability, evidence/manifest integrity, and configured 500-entity ceiling coverage.
- Removed all other-group and protected-group query probes; teardown deletes only test-created elementIds.

## Task Commits

1. **Task 1: Canonical MCP compatibility contracts** - `18aced7` (test)
2. **Task 2: Live TEST-11 safety proofs** - `c55b2a6` (test)

## Verification

- Focused compatibility/isolation pytest: **PASS — 19 passed**.
- Live Neo4j required suite: **PASS — 62 passed** with `CATALOG_INT_REQUIRED=1 CATALOG_CEILING_SMOKE=1`.
- Ruff, all five changed Python test files: **PASS — All checks passed**.
- Pyright, project config and all five changed Python test files: **PASS — 0 errors, 0 warnings, 0 informations**.
- `git diff --check`: **PASS**.
- Live warnings: pytest unknown-marker warnings and Neo4j Cypher deprecation notifications only; non-failing, pre-existing tooling/query warnings.

## Safety Evidence

- Every test request hard-codes `GROUP = 'oracle-catalog-tool-test'`.
- Runtime commit `TrackingDriver` rejects every query parameter group other than the exact test group.
- No live test queries or mutates `oracle-catalog-v2`; source scans found no other-group query or `<> $g` probe.
- No live test invokes `clear_graph`.
- Direct and prepare fixtures snapshot exact elementIds, then delete only `current - before` within the test group.
- Commit tests maintain explicit run-scoped batch, plan, and entity registries.
- ACCEPT and prepare fixtures add process-unique identity tokens, preventing mutation of pre-existing deterministic records.
- No deployment, canary, push, dependency addition, graph clearing, or broad teardown occurred.

## Files Created/Modified

- `mcp_server/tests/fixtures/legacy_mcp_contract_baseline.json` - canonical contracts for all 14 legacy MCP tools.
- `mcp_server/tests/test_legacy_mcp_contract_compatibility.py` - exact registration, canonical metadata, concurrency, and fail-closed checks.
- `mcp_server/tests/catalog_neo4j_fixtures.py` - catalog-v2 evidence-link fixtures with run-scoped ACCEPT identities.
- `mcp_server/tests/test_catalog_neo4j_int.py` - direct/batch TEST-11 safety and current evidence semantics.
- `mcp_server/tests/test_catalog_commit_neo4j_int.py` - audited commit group propagation and control-label proofs.
- `mcp_server/tests/test_catalog_prepare_neo4j_int.py` - pre-existing-safe prepare teardown and current full-commit semantics.

## Decisions Made

- Canonical schema equality strips only `title` and `description`; all behavior-bearing schema fields remain frozen.
- Outside-group safety is proven without reading other groups: exact request propagation, audited query params, and source scans.
- Missing ingest status follows the current `found=false`, `error_code=None` contract.
- Catalog-v2 provenance totals include source plus explicit evidence-link membership where status/unchanged totals report all provenance objects.
- Prepared commit tests assert current Phase 3B full `COMMITTED` semantics and idempotent replay, replacing obsolete control-plane-only `COMMITTING` expectations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Safety] Removed forbidden and other-group live read probes**
- **Found during:** Task 2
- **Issue:** Existing fixtures queried all non-test groups and the protected group to compare counts.
- **Fix:** Removed those reads; added exact-group query auditing and test-created-only teardown.
- **Files modified:** live Neo4j test modules.
- **Verification:** source scan plus 62 passing required live tests.
- **Committed in:** `c55b2a6`

**2. [Rule 1 - Bug] Updated stale catalog-v2 fixture semantics**
- **Found during:** Task 2 full live run
- **Issue:** ACCEPT fixture used rejected Cartesian provenance fields; tests assumed old missing-status, provenance-count, and prepare-only commit semantics.
- **Fix:** Built explicit evidence links, asserted current response totals, and verified full prepared commit plus replay.
- **Files modified:** catalog fixture, direct and prepare live tests.
- **Verification:** 62 passing required live tests.
- **Committed in:** `c55b2a6`

**3. [Rule 2 - Data preservation] Isolated deterministic live identities**
- **Found during:** Task 2 full live run
- **Issue:** Fixed graph keys and batch IDs could update pre-existing test-group records; global count assertions were contamination-sensitive.
- **Fix:** Added run-scoped identities, UUID-specific assertions, baseline deltas, and elementId-difference teardown.
- **Files modified:** catalog fixture and live test modules.
- **Verification:** complete suite passes while fixture postconditions restore each pre-test snapshot.
- **Committed in:** `c55b2a6`

---

**Total deviations:** 3 auto-fixed (2 safety/correctness, 1 bug)
**Impact on plan:** Required for truthful live execution and the explicit no-existing-data-deletion/no-protected-query constraints; no product behavior or dependencies changed.

## Known Stubs

None.

## Threat Flags

None. Changes are test-only; no endpoint, authentication, file-access, or schema trust boundary added.

## Issues Encountered

- Initial full live execution exposed stale fixed identities and legacy provenance assumptions. Tests were made run-scoped and aligned to current catalog-v2 contracts; no product defect remained.
- Pytest emits unknown integration-marker warnings under `mcp_server/pytest.ini`; Neo4j emits existing Cypher deprecation notifications. Both are non-failing and outside this plan's product scope.

## User Setup Required

None.

## Next Phase Readiness

- SAFE-09, SAFE-10, and TEST-11 have deterministic automated evidence.
- No blocker remains for the remaining Phase 5 verification/documentation plans.

## Self-Check: PASSED

- Created baseline fixture exists.
- Task commits `18aced7` and `c55b2a6` exist.
- Focused, static, and complete required live gates pass.
- Safety scan confirms no protected/other-group query, broad teardown, or graph clearing.

---
*Phase: 05-verification-security-compatibility-and-migration-docs*
*Completed: 2026-07-19*
