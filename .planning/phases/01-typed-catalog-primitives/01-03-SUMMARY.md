---
phase: 01-typed-catalog-primitives
plan: 03
subsystem: catalog-resolve-verify
tags: [catalog, neo4j, mcp, resolve, verify, read-only, anomalies]

requires:
  - 01-01 catalog models and identity helpers
  - 01-02 catalog entity upsert store/service
provides:
  - CatalogService.resolve_typed_entities read-only path
  - CatalogService.verify_catalog_batch read-only path
  - CatalogNeo4jStore MATCH helpers for resolve/verify/provenance presence
  - MCP tools resolve_typed_entities and verify_catalog_batch
affects:
  - 01-04 typed edge upsert (endpoint diagnostics reuse)
  - Phase 2 provenance writes consuming require_provenance reports

tech-stack:
  added: []
  patterns:
    - Read-only MATCH paths never open write transactions or call embedder
    - Exact group_id (+ batch_id when supplied) scoping; no full-group scan
    - Service owns anomaly aggregation; store owns parameterized MATCH

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/models/catalog_entities.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Resolve MATCH returns all Entity nodes by group_id + name/graph_key; service classifies generic vs typed"
  - "Verify uses exact group_id + batch_id MATCH when batch_id set, unioned with explicit key MATCH"
  - "require_provenance is report-only via MENTIONS presence; missing list only, no writes"

patterns-established:
  - "Shared _read_gate for feature/namespace/backend on resolve and verify"
  - "generic_duplicate = same-group Entity with name=graph_key lacking expected custom label"
  - "ResolveEntityResult carries found/uuid/labels/verified_type/hash/embedding/dups/anomalies"

requirements-completed:
  - RESO-01
  - RESO-02
  - RESO-03
  - RESO-04
  - VERI-01
  - VERI-02
  - VERI-03
  - VERI-04
  - VERI-05

coverage:
  - id: D1
    description: resolve_typed_entities reports found state, UUID, labels, type, hash, embedding, generic/typed dups
    requirement: RESO-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_resolve_found_entity_reports_fields_and_no_side_effects
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_resolve_generic_duplicate_and_typed_duplicate_and_uuid_mismatch
        status: pass
    human_judgment: false
  - id: D2
    description: resolve/verify never embed or open write transactions
    requirement: RESO-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_resolve_never_opens_write_transaction
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_verify_never_embeds_or_writes
        status: pass
    human_judgment: false
  - id: D3
    description: batch-scoped verify MATCH uses exact group_id + batch_id; require_provenance report-only
    requirement: VERI-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_verify_batch_scoped_match_uses_group_and_batch_id
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_verify_require_provenance_report_only_no_write
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-07-16
status: complete
---

# Phase 01 Plan 03: Resolve and Verify Read-Only Paths Summary

**Read-only `resolve_typed_entities` and `verify_catalog_batch` with store MATCH helpers, structured anomaly reports, MCP tools, and zero embed/write side effects.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-16T13:44:16Z
- **Completed:** 2026-07-16T13:49:43Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- `CatalogNeo4jStore` MATCH helpers: resolve by keys, verify by batch_id and/or keys, provenance presence
- `CatalogService.resolve_typed_entities` classifies missing/generic/typed/wrong-type/uuid/embedding anomalies under group_id isolation
- `CatalogService.verify_catalog_batch` aggregates entity/edge expected/found counts and anomaly lists; `require_provenance` report-only
- MCP tools registered additively; schemas present while feature disabled

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **Task 1: RED/GREEN resolve_typed_entities read-only path**
   - `fd33ca7` test(01-03): add failing tests for resolve_typed_entities
   - `e70e8f9` feat(01-03): implement resolve_typed_entities read-only path
2. **Task 2: RED/GREEN verify_catalog_batch read-only path**
   - `ee08e13` test(01-03): add tests for verify_catalog_batch read-only path
   - (implementation shipped in `e70e8f9` with store/service/MCP; verify tests green immediately)
3. **Diagnostic fix**
   - `401dd89` fix(01-03): clear pyright diagnostics on resolve/verify path

## Files Created/Modified

- `mcp_server/src/services/catalog_store.py` — match_entities_for_resolve/verify, match_edges_for_verify, match_provenance_presence
- `mcp_server/src/services/catalog_service.py` — resolve_typed_entities, verify_catalog_batch, shared _read_gate
- `mcp_server/src/models/catalog_entities.py` — VerifyCatalogBatchRequest, VerifyEntityRef, VerifyEdgeRef
- `mcp_server/src/models/catalog_responses.py` — ResolveEntityResult fields, VerifyEntitySection/VerifyEdgeSection
- `mcp_server/src/graphiti_mcp_server.py` — resolve_typed_entities, verify_catalog_batch tools
- `mcp_server/tests/test_catalog_service.py` — 16 resolve/verify unit tests

## Decisions Made

- Store returns raw MATCH rows; service computes expected UUIDv5 and classifies generic vs typed duplicates
- Verify batch scope unions batch_id MATCH with explicit key MATCH under the same group_id (no unrelated group scan)
- Provenance check uses OPTIONAL MENTIONS count; Phase 1 only reports missing_provenance

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Verify request/response shapes incomplete in 01-01**
- **Found during:** Task 1 GREEN / Task 2 design
- **Issue:** Plan required verify by batch_id and/or keys with entity/edge sections; 01-01 had only a thin VerifyCatalogBatchResponse
- **Fix:** Added VerifyCatalogBatchRequest + entity/edge section models; expanded ResolveEntityResult with RESO-02 fields
- **Files modified:** `catalog_entities.py`, `catalog_responses.py`
- **Committed in:** `e70e8f9`

**2. [Rule 1 - Bug] Pyright union type on resolve results**
- **Found during:** Post-GREEN pyright
- **Issue:** `list[ResolveEntityResult | CatalogItemResult]` blocked attribute access in tests/service consumers
- **Fix:** Narrowed to `list[ResolveEntityResult]`; guarded await_args in tests
- **Files modified:** `catalog_responses.py`, `test_catalog_service.py`
- **Committed in:** `401dd89`

**3. [Rule 1 - Bug] Optional mock await_args.kwargs still type-unsafe**
- **Found during:** Pre-merge reopen
- **Issue:** `await_args` is typed optional; accessing `.kwargs` after `assert is not None` still trips reportOptionalMemberAccess in some analyzers
- **Fix:** Capture kwargs via AsyncMock `side_effect` dicts; assert_awaited without reading optional await_args
- **Files modified:** `test_catalog_service.py`
- **Committed in:** `5979d04`

**4. [Rule 1 - Bug] Function-local model/server imports flagged by editor pyright**
- **Found during:** Final diagnostic cleanup
- **Issue:** Repeated `from models.catalog_entities import ...` and `import graphiti_mcp_server` inside tests/helpers
- **Fix:** Top-level model imports; `_mcp_server()` via `importlib.import_module`; drop unused `datetime`/`timezone`/`call`
- **Files modified:** `test_catalog_service.py`
- **Committed in:** final diagnostic cleanup

## Threat Flags

None beyond plan register. Mitigations T-01-09..11 applied: group_id filter always, zero write commits on read paths, only requested keys/batch.

## Known Stubs

None for resolve/verify behavior. Live Neo4j integration deferred to later phase plans. Edge upsert still Phase 01-04.

## TDD Gate Compliance

- RED commit present: `fd33ca7`
- GREEN commit after RED: `e70e8f9`
- Verify tests: `ee08e13` (implementation already present from Task 1 GREEN; tests authored RED-style against public API)
- Diagnostic fix: `401dd89`
- Pre-merge optional-mock fix: capture kwargs via side_effect (no await_args.kwargs)
- Final import cleanup: top-level model symbols; `importlib` for MCP server; no local `from models...` / `import graphiti_mcp_server`
- Verification: `cd mcp_server && uv run pytest tests/test_catalog_service.py -q` → 33 passed
- Verification (root portable): `uv run --project mcp_server pyright --project mcp_server/pyproject.toml mcp_server/src/graphiti_mcp_server.py mcp_server/src/models/catalog_entities.py mcp_server/src/models/catalog_responses.py mcp_server/src/services/catalog_store.py mcp_server/src/services/catalog_service.py mcp_server/tests/test_catalog_service.py` → 0 errors
- Verification (package): `cd mcp_server && uv run pyright src/graphiti_mcp_server.py src/models/catalog_entities.py src/models/catalog_responses.py src/services/catalog_store.py src/services/catalog_service.py tests/test_catalog_service.py` → 0 errors
- Ruff: `uv run ruff check tests/test_catalog_service.py --select F401,F821` → All checks passed

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_store.py` (`match_entities_for_resolve`, `match_entities_for_verify`, `match_edges_for_verify`, `match_provenance_presence`)
- FOUND: `mcp_server/src/services/catalog_service.py` (`resolve_typed_entities`, `verify_catalog_batch`)
- FOUND: `mcp_server/src/graphiti_mcp_server.py` (`resolve_typed_entities`, `verify_catalog_batch`)
- FOUND: `mcp_server/tests/test_catalog_service.py` (resolve + verify cases)
- FOUND commits: `fd33ca7`, `e70e8f9`, `ee08e13`, `401dd89`, `5979d04` (+ final import cleanup)
- STATE.md / ROADMAP.md: not modified (per executor instructions)
- No function-local `from models...` or `import graphiti_mcp_server` remaining
