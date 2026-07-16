---
phase: 01-typed-catalog-primitives
plan: 07
subsystem: mcp-catalog-validation
tags: [pydantic, neo4j, validation, verification, tdd]
requires:
  - phase: 01-typed-catalog-primitives
    provides: deterministic typed catalog entity, edge, resolve, and verify primitives
provides:
  - configurable catalog batch limits bounded by transport hard maxima
  - bounded iterative JSON validation before hash/embed/write
  - exact edge endpoint verification separated from edge-type mismatch
  - corrected Phase 1 gate evidence
  - independent verifier handoff with Phase 2 still blocked
  - catalog unit and live Neo4j regression coverage
  - backward-compatible VerifyEdgeRef endpoint expectations
  - refreshed quality and MCP compatibility evidence
  - scoped validation-map updates
  - no Phase 2 product code
  - no unrelated dirty-file changes
  - no credential exposure
  - no graph clear
  - no live-group writes
  - no package changes
  - no new dependencies
  - no unsupported backend claims
  - no caller identity authority
  - no LLM or queue path
  - no report overstatement
  - no skipped Neo4j PASS
  - no deployment changes
  - no ROADMAP/REQUIREMENTS/STATE completion update
affects: [phase-1-verification, phase-2-gate]
tech-stack:
  added: []
  patterns: [transport hard ceiling plus operator runtime limit, iterative bounded JSON validation, all-row expected identity comparison]
key-files:
  created: [.planning/phases/01-typed-catalog-primitives/01-07-SUMMARY.md]
  modified:
    - mcp_server/src/models/catalog_common.py
    - mcp_server/src/config/schema.py
    - mcp_server/src/models/catalog_entities.py
    - mcp_server/src/models/catalog_edges.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/tests/test_catalog_models.py
    - mcp_server/tests/test_catalog_service.py
    - mcp_server/tests/test_catalog_neo4j_int.py
    - .planning/phases/01-typed-catalog-primitives/01-PHASE1-REPORT.md
    - .planning/phases/01-typed-catalog-primitives/01-VALIDATION.md
key-decisions:
  - "Keep operator defaults at 500/2000/5000; cap transport and configuration at 5000/10000/20000."
  - "Only supplied expected endpoint fields participate in endpoint mismatch reporting."
  - "Keep Phase 2 blocked until independent verification accepts corrected executor evidence."
patterns-established:
  - "Collection safety: broad hard Pydantic ceiling, narrower active CatalogConfig enforcement in service."
  - "Verification anomalies: edge_type_mismatch never substitutes for endpoint_mismatch."
requirements-completed: [CONF-04, SAFE-03, VERI-03, GATE-01, GATE-05]
coverage:
  - id: D1
    description: Configured catalog limits above defaults remain constructible within hard safety ceilings.
    requirement: CONF-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py and test_catalog_service.py; 192-unit gate
        status: pass
    human_judgment: false
  - id: D2
    description: Nested values receive iterative bounded JSON validation before service work.
    requirement: SAFE-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py nested validation regressions
        status: pass
    human_judgment: false
  - id: D3
    description: VerifyEdgeRef compares optional expected endpoint identities and reports type mismatch separately.
    requirement: VERI-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py focused verify regressions
        status: pass
      - kind: integration
        ref: mcp_server/tests/test_catalog_neo4j_int.py#test_verify_edge_endpoint_and_type_mismatch_live
        status: pass
    human_judgment: false
  - id: D4
    description: Corrected Phase 1 report records full green gate evidence while preserving the independent verification block.
    requirement: GATE-05
    verification:
      - kind: other
        ref: 192 units; 25 live; 217 combined; Ruff/Pyright; 86 MCP regressions; 18-tool listing
        status: pass
    human_judgment: true
    rationale: Independent verifier must accept executor evidence before phase completion.
duration: 13min
completed: 2026-07-16
status: complete
---

# Phase 1 Plan 7: Independent Gap Closure Summary

**Hard-bounded batches, iterative JSON validation, physical edge verification, and group-isolated provenance with 217 catalog tests green**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-16T16:24:53Z
- **Completed:** 2026-07-16T16:38:14Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments

- Closed CONF-04: transport accepts configured limits above defaults through fixed hard maxima; service retains active configured-limit authority.
- Closed SAFE-03: one iterative validator rejects non-JSON values, non-finite floats, oversized strings, cycles, excess depth, and excess nodes during Pydantic validation.
- Closed VERI-03: optional endpoint expectations compare across every matching Neo4j row; duplicate rogue rows cannot hide UUID/type/endpoint/embedding anomalies.
- Fail closed on provenance read errors with structured `internal_error`; no DB failure becomes absence.
- Re-ran complete catalog, live Neo4j, Ruff, Pyright, 86 MCP regression, and 18-tool compatibility gates.
- Corrected Phase 1 report and validation evidence without updating phase completion tracking.

## Task Commits

1. **Task 1 RED: catalog bound regressions** — `a89fd15`
2. **Task 1 GREEN: configurable safety bounds** — `2d1ed11`
3. **Task 2 RED: edge verification regressions** — `0fad8ce`
4. **Task 2 GREEN: exact edge verification** — `928263b`
5. **Task 3: gate report and validation evidence** — committed with plan metadata

## Verification Results

| Gate | Sanitized result |
|---|---|
| Focused Task 1 | 13 passed |
| Focused Task 2 | 25 passed |
| Catalog units | 192 passed in 1.60s |
| Live Neo4j required | 25 passed in 17.19s; 0 skipped |
| Combined catalog | 217 passed in 18.77s |
| Ruff format | 14 files already formatted |
| Ruff check | All checks passed |
| Pyright | 0 errors, 0 warnings, 0 informations |
| MCP regressions | 86 passed in 1.50s |
| Tool listing | 18 total; 14 existing; 4 catalog; missing none |

Live writes and scoped teardown used only `oracle-catalog-tool-test`. Credentials stayed in the existing environment/session.

## Files Created/Modified

- `mcp_server/src/models/catalog_common.py` — hard maxima and iterative bounded JSON validator.
- `mcp_server/src/config/schema.py` — hard upper bounds on CatalogConfig values.
- `mcp_server/src/models/catalog_entities.py` — hard request ceilings, nested validation, optional expected edge endpoints.
- `mcp_server/src/models/catalog_edges.py` — hard request ceiling and nested validation.
- `mcp_server/src/models/catalog_responses.py` — explicit `edge_type_mismatch` list.
- `mcp_server/src/services/catalog_service.py` — endpoint identity comparison and anomaly aggregation.
- `mcp_server/tests/test_catalog_models.py` — CONF-04/SAFE-03 and VerifyEdgeRef coverage.
- `mcp_server/tests/test_catalog_service.py` — configured service limit and VERI-03 coverage.
- `mcp_server/tests/test_catalog_neo4j_int.py` — live endpoint/type mismatch regression.
- `.planning/phases/01-typed-catalog-primitives/01-PHASE1-REPORT.md` — corrected gate evidence.
- `.planning/phases/01-typed-catalog-primitives/01-VALIDATION.md` — evidence-supported Plan 07 rows.

## Decisions Made

- Defaults remain stable for compatibility. Hard maxima protect transport/config trust boundaries without preventing operator values above defaults.
- Endpoint mismatch requires at least one caller-supplied expected endpoint field. Missing expectations produce no invented mismatch.
- Phase 2 remains blocked pending independent verifier acceptance despite green executor gates.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Hardened nested JSON resource and type validation**
- **Found during:** Independent review after Task 3
- **Issue:** Recursive string-only walking allowed non-JSON values, cycles, and resource exhaustion.
- **Fix:** Added one iterative validator with JSON type, finite-float, string, depth, node, and active-cycle checks.
- **Files modified:** `catalog_common.py`, entity/edge models, model tests
- **Verification:** 192 catalog units; 217 combined catalog tests
- **Committed in:** `4feebfc`

**2. [Rule 1 - Bug] Aggregated every duplicate edge row and failed provenance reads closed**
- **Found during:** Independent review after Task 3
- **Issue:** A selected primary row could hide rogue duplicate anomalies; provenance DB exceptions became missing data.
- **Fix:** Scan all matching rows once per anomaly; return structured `internal_error` on provenance read failure.
- **Files modified:** `catalog_service.py`, service/live tests
- **Verification:** 192 catalog units; 25 live Neo4j tests
- **Committed in:** `4feebfc`

**3. [Rule 1 - Bug] Preserved physical duplicate relationships and enforced provenance/isolation scope**
- **Found during:** Final independent re-review
- **Issue:** Verify store dedup collapsed relationships by UUID; provenance did not constrain both groups; isolation assertions were tautological.
- **Fix:** Return/dedup by `elementId(e)`, scope episode and target groups, snapshot external groups, add scoped canary and AST no-clear check.
- **Files modified:** `catalog_store.py`, store/live tests, validation/report
- **Verification:** 192 units; 25 live Neo4j; 217 combined
- **Committed in:** `427323f`

**4. [Rule 1 - Bug] Aggregated all entity twin anomalies symmetrically**
- **Found during:** Final symmetry review
- **Issue:** Primary-only entity checks hid rogue typed UUID and embedding anomalies.
- **Fix:** Aggregate UUID and missing-embedding anomalies across all typed, wrong, and generic matches.
- **Files modified:** `catalog_service.py`, service/live tests, validation/report
- **Verification:** 192 units; 25 live Neo4j; 217 combined
- **Committed in:** `b069fc7`

**Total deviations:** 4 auto-fixed (1 missing critical, 3 bugs). No scope creep.

## Issues Encountered

- Initial RED tests failed at import/model assertions as expected. GREEN implementation resolved them.
- Live Neo4j available under required mode. No authentication gate or skip occurred.

## Known Stubs

None.

## User Setup Required

None - existing Neo4j environment/session was sufficient.

## Next Phase Readiness

- CONF-04, SAFE-03, VERI-03 executor evidence green.
- GATE-01..GATE-05 executor evidence green.
- Independent verifier must re-evaluate Phase 1 before any tracking completion or Phase 2 work.

## Self-Check: PASSED

- Source/test/report files exist.
- Task/review commits through `db169e8` and `b069fc7` exist.
- No tracked files deleted.
- No ROADMAP, REQUIREMENTS, or STATE completion update made.

---
*Phase: 01-typed-catalog-primitives*
*Completed: 2026-07-16*
