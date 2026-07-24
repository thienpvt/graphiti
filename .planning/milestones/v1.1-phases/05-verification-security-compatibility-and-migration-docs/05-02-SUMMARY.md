---
phase: 05-verification-security-compatibility-and-migration-docs
plan: 02
subsystem: testing
tags: [security, catalog-v2, SAFE-03, SAFE-04, SAFE-06, SAFE-07, TEST-10, cypher, log-scrub]

requires:
  - phase: 05-verification-security-compatibility-and-migration-docs
    provides: Wave 0 RED scaffolds for security matrix
  - phase: 05-01
    provides: Phase 5 scaffolding and edge-probe ledger
provides:
  - GREEN exhaustive security prohibition matrix (SAFE-03/04/06/07, TEST-10)
  - Fixed-server Cypher identifier and property-allowlist proofs
  - Missing/same-batch endpoint zero-write spies under existing semantics
  - Fail-closed conflict and log-scrub AST/caplog coverage
affects:
  - 05-03
  - 05-07
  - phase5-gate-results

tech-stack:
  added: []
  patterns:
    - AST static scan of catalog_service + catalog MCP wrappers for PROHIBITED_ON_CATALOG_PATH
    - Query-boundary tests for resolve_entity_label/resolve_edge_type/build_*_cypher/prepare_*_params
    - AsyncMock spies proving zero LLM/queue/embed/implicit endpoint writes
    - Logger template AST + caplog exact UTF-8 forbidden-marker bans

key-files:
  created: []
  modified:
    - mcp_server/tests/test_catalog_security_matrix.py
    - mcp_server/tests/test_catalog_store_unit.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "No product edits: matrix greened against existing catalog_service/catalog_store semantics"
  - "Empty-entity list is invalid (min_length=1); empty probes use dry_run minimal path"
  - "Malicious property keys must not false-positive on legitimate Cypher n.uuid literals"

patterns-established:
  - "PROHIBITED_ON_CATALOG_PATH frozenset is the SAFE-03 authority for catalog paths"
  - "prepare_*_params fixed key sets are the sole property-name authority at write boundary"
  - "missing_endpoint and same-request union contracts must match existing service behavior"

requirements-completed: [SAFE-03, SAFE-04, SAFE-06, SAFE-07, TEST-10]

coverage:
  - id: D1
    description: Deterministic catalog paths never call prohibited Graphiti maintenance tools
    requirement: SAFE-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_prohibited_tools_absent_on_catalog_paths
        status: pass
    human_judgment: false
  - id: D2
    description: No LLM extraction, queue ingestion, community fan-out, or commit-time re-embed
    requirement: SAFE-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_llm_or_queue_or_community_ban_on_catalog_paths
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_commit_path_embedder_not_awaited
        status: pass
    human_judgment: false
  - id: D3
    description: Client-controlled labels/property names cannot enter Cypher construction
    requirement: TEST-10
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_client_controlled_cypher_entity_identifiers_fail_before_query
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_phase5_client_entity_type_rejected_before_cypher
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_store_unit.py#test_phase5_client_property_key_rejected_before_cypher
        status: pass
    human_judgment: false
  - id: D4
    description: Missing persisted endpoints fail closed with zero writes; same-batch uses request union only
    requirement: SAFE-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_missing_endpoint_returns_structured_error_zero_writes
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_same_batch_endpoints_resolve_from_request_union_only
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_phase5_same_batch_endpoint_union_no_extra_creation
        status: pass
    human_judgment: false
  - id: D5
    description: Identity/hash/endpoint conflicts fail closed with no silent repair/merge
    requirement: SAFE-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_fail_closed_conflicts_no_silent_repair
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_phase5_fail_closed_conflict_no_silent_merge
        status: pass
    human_judgment: false
  - id: D6
    description: Catalog logs omit payloads, plan tokens, credentials, and group_id
    requirement: SAFE-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_log_empty_batch_omits_payload_and_credentials
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_security_matrix.py#test_log_encoding_forbids_plan_token_and_payload_markers
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-19
status: complete
---

# Phase 05 Plan 02: Security Matrix GREEN Summary

**Exhaustive SAFE-03/04/06/07 + TEST-10 security matrix greened via static AST, fixed Cypher identifier proofs, endpoint zero-write spies, fail-closed conflicts, and log scrub — no product changes required**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-18T22:34:35Z
- **Completed:** 2026-07-18T22:42:12Z
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments

- GREEN `test_catalog_security_matrix.py` (15/15) covering prohibited tools, LLM/queue/community ban, commit no-embed, Cypher identifier authority, property allowlist, missing/same-batch endpoints, implicit-create ban, fail-closed conflicts, log scrub, empty-spy baseline
- Store unit phase5 proofs for entity/edge identifier rejection, fixed property-key sets, MATCH-only endpoint lookup
- Service phase5 proofs reusing existing missing_endpoint / endpoint_union / fail-closed semantics with zero implicit writes
- Product code untouched — matrix proves existing catalog_service/catalog_store already satisfy SAFE/TEST gates

## Task Commits

Each task was committed atomically:

1. **Task 1+2: Prohibition, fixed Cypher identifiers, no implicit endpoints, fail-closed conflicts, log scrub GREEN** - `b181461` (test)

**Plan metadata:** (docs commit follows)

_Note: TDD Wave 0 RED scaffolds already existed from 05-01; this plan is GREEN-only. Tasks 1 and 2 landed in one atomic test commit because both only green existing scaffolds with no product gap._

## Files Created/Modified

- `mcp_server/tests/test_catalog_security_matrix.py` - Full GREEN SAFE-03/04/06/07 + TEST-10 matrix
- `mcp_server/tests/test_catalog_store_unit.py` - Phase5 store cypher_identifier / property_allowlist / MATCH-only proofs
- `mcp_server/tests/test_catalog_service.py` - Phase5 service endpoint_union / missing_endpoint / fail_closed proofs

## Decisions Made

- No product edits: security matrix greened against current implementation; catalog paths already omit prohibited tools, use fixed registries, and scrub logs
- Empty entity list rejected by Pydantic (`min_length=1`); empty-path probes use dry_run minimal request instead of empty list
- Malicious property-key strings exclude substrings that legitimately appear in server Cypher (`n.uuid`) to avoid false positives

## Deviations from Plan

None - plan executed as written. Tasks 1 and 2 combined into one test commit because both were pure GREEN of RED scaffolds with zero product changes.

## Issues Encountered

- Initial empty-entity request raised ValidationError (entities min_length=1) — switched empty probes to dry_run
- Property-key assert false-positive on legitimate `n.uuid` Cypher — narrowed malicious key set
- Pyright MethodType on AsyncMock spies — cast(AsyncMock, ...) matching existing service tests

## Verification Results

| Command | Result |
|---------|--------|
| Plan Task1 `-k "prohibited or llm_or_queue or community or embed or cypher_identifier or property_allowlist or missing_endpoint or endpoint_union or implicit_endpoint"` (+ phase5/fail_closed/log/empty) | **39 passed** |
| Full `test_catalog_security_matrix.py` | **15 passed** |
| Ruff (changed files) | **0 errors** |
| Pyright (matrix + store unit from mcp_server/) | **0 errors** |

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- SAFE-03/04/06/07 and TEST-10 proven offline with mocks/static checks only
- Ready for 05-03+ (compatibility/live isolation/docs/gates) without canary or v2 access
- No product residual security gap found in this plan

## Self-Check: PASSED

- FOUND: `mcp_server/tests/test_catalog_security_matrix.py`
- FOUND: `mcp_server/tests/test_catalog_store_unit.py` phase5 proofs
- FOUND: `mcp_server/tests/test_catalog_service.py` phase5 proofs
- FOUND: commit `b181461`

---
*Phase: 05-verification-security-compatibility-and-migration-docs*
*Completed: 2026-07-19*
