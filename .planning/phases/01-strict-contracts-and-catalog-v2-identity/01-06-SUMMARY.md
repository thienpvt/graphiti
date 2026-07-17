---
phase: 01-strict-contracts-and-catalog-v2-identity
plan: 06
subsystem: catalog-contracts
tags: [pydantic, catalog-v2, strict-validation, fastmcp, tdd]

requires:
  - 01-05
provides:
  - Strict typed CatalogSourceRef evidence contract
  - StrictTrue and finite SystemKey request aliases
  - Exact nested invalid_system_key diagnostics
  - Required nonempty typed-entity resolve requests
  - JSON-compatible source references before hashing and storage serialization
affects:
  - 01-07
  - 01-08
  - Phase 2 entry gate

tech-stack:
  added: []
  patterns:
    - Shared Annotated Pydantic aliases validate untrusted scalar types before Literal handling
    - Parent validators raise Pydantic custom errors at exact request-relative child locations
    - Validated nested models are dumped to JSON dictionaries before canonical hashing and persistence

key-files:
  created:
    - .planning/phases/01-strict-contracts-and-catalog-v2-identity/01-06-SUMMARY.md
  modified:
    - .planning/phases/01-strict-contracts-and-catalog-v2-identity/01-VALIDATION.md
    - .planning/phases/01-strict-contracts-and-catalog-v2-identity/01-PHASE1-GATE.md
    - mcp_server/src/models/catalog_common.py
    - mcp_server/src/models/catalog_entities.py
    - mcp_server/src/models/catalog_edges.py
    - mcp_server/src/models/catalog_batch.py
    - mcp_server/src/models/catalog_provenance.py
    - mcp_server/src/models/catalog_graph_key.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/services/catalog_store.py
    - mcp_server/tests/test_catalog_models.py
    - mcp_server/tests/test_catalog_service.py
    - mcp_server/tests/test_catalog_store_unit.py

key-decisions:
  - "Missing system_key remains Pydantic missing and maps to validation_error; only explicit custom invalid_system_key errors receive that structured code"
  - "CatalogSourceRef models are converted with model_dump(mode='json') before canonical hashing and store parameter construction"
  - "Phase 1 readiness remains false until Plans 01-07 and 01-08 re-earn the complete gate"

patterns-established:
  - "Strict scalar alias: BeforeValidator enforces identity/type before Literal validation while WithJsonSchema preserves the public boolean const contract"
  - "Located mismatch: validate_entity_graph_key_at converts scope mismatches into one invalid_system_key error at the exact nested field path"

requirements-completed: [CONT-01, CONT-02, CONT-04, CONT-05, CONT-06, CONT-07, IDEN-01, IDEN-02, IDEN-03, IDEN-04, IDEN-05, SAFE-08, TEST-01, TEST-03]

coverage:
  - id: D1
    description: "Typed source references enforce strict document, page, raw-text, and collection contracts while preserving exact text"
    requirement: CONT-04
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_models.py -k source_ref"
        status: pass
      - kind: unit
        ref: "mcp_server/tests/test_catalog_store_unit.py -k source_ref"
        status: pass
    human_judgment: false
  - id: D2
    description: "Immutable request booleans and finite system keys reject coercion with stable JSON Schema and structured error types"
    requirement: CONT-05
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_models.py -k 'strict_true or system_key'"
        status: pass
    human_judgment: false
  - id: D3
    description: "All nested graph-key scope mismatches report exact request-relative invalid_system_key paths before FastMCP service entry"
    requirement: IDEN-03
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_service.py -k graph_key_mismatch"
        status: pass
    human_judgment: false
  - id: D4
    description: "Resolve requests reject missing or empty entity collections before service, store, embedder, schema, transaction, or status access"
    requirement: CONT-07
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_service.py -k empty_resolve"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-07-18
status: complete
---

# Phase 1 Plan 06: Strict Catalog Contract Gap Closure Summary

**Strict typed source evidence, coercion-proof booleans and system keys, exact nested diagnostics, and nonempty resolve requests at the Pydantic/FastMCP boundary.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-07-18T04:25:13+07:00
- **Completed:** 2026-07-18T05:05:17+07:00
- **Tasks:** 2/2
- **Files modified:** 13

## Accomplishments

- Invalidated stale Nyquist and Phase 2 readiness before all RED/product work.
- Added `CatalogSourceRef` with strict optional `document_id`, strict positive integer `page`, strict bounded `raw_text`, recursive unknown-field rejection, and exact text preservation.
- Added shared `StrictTrue` and `SystemKey` aliases; present invalid keys use `invalid_system_key`, absent keys remain `missing` and structured `validation_error`.
- Preserved exact nested mismatch paths across entity, resolve, verify, edge, provenance, and combined-batch model/FastMCP routes.
- Rejected missing and empty resolve entity collections before service or backend access.
- Converted source-reference models to plain JSON dictionaries before canonical hashing and store serialization.
- Passed 70 focused contract tests and all 446 tests in the three task test files; scoped Ruff, formatting, and MCP-configured Pyright passed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Invalidate stale Nyquist and Phase 2 readiness flags** - `33c4457` (docs)
2. **Task 2 RED: Add failing contract gap coverage** - `56826fa` (test)
3. **Task 2 GREEN: Harden catalog request contracts** - `12945f6` (feat)

## Verification Results

| Check | Result |
|-------|--------|
| Guarded RED focused selection | pass: 70 selected, inner pytest exit 1 from intended missing contracts |
| Focused contract pytest | pass: 70 passed, 376 deselected |
| Full task-file pytest | pass: 446 passed |
| Scoped Ruff | pass: all checks passed |
| Ruff format check | pass: 11 files already formatted |
| MCP-configured Pyright over all task source/tests | pass: 0 errors, 0 warnings |
| Readiness assertions | pass: `nyquist_compliant: false`, unique `ready_for_phase_2=false` |
| Commit order/trailers | pass: docs → RED → GREEN; required co-author trailer present |
| Neo4j integration | skip by policy; no live probe |

## Files Created/Modified

- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-VALIDATION.md` - Nyquist compliance invalidated before gap work.
- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-PHASE1-GATE.md` - Phase 2 readiness blocked pending Plans 01-06 through 01-08.
- `mcp_server/src/models/catalog_common.py` - Shared strict aliases, custom located error construction, structured-error precedence.
- `mcp_server/src/models/catalog_entities.py` - Typed source references, strict shells, nonempty resolve contract, located graph-key validation.
- `mcp_server/src/models/catalog_edges.py` - Strict shell fields and exact source/target mismatch paths.
- `mcp_server/src/models/catalog_batch.py` - Strict shell fields and exact nested entity/edge/provenance paths.
- `mcp_server/src/models/catalog_provenance.py` - Strict shell fields and exact entity-target mismatch paths.
- `mcp_server/src/models/catalog_graph_key.py` - Custom invalid-system error and located validation helper.
- `mcp_server/src/services/catalog_service.py` - Plain JSON source references before hashing and store parameters.
- `mcp_server/src/services/catalog_store.py` - Recursive JSON compatibility conversion before serialization.
- `mcp_server/tests/test_catalog_models.py` - Strict source, boolean, system-key, nested-path, and resolve model matrix.
- `mcp_server/tests/test_catalog_service.py` - FastMCP zero-entry, canonical payload, and resolve boundary proofs.
- `mcp_server/tests/test_catalog_store_unit.py` - Typed source-reference serialization proofs.

## Decisions Made

- Use installed Pydantic `BeforeValidator`, `WithJsonSchema`, `PydanticCustomError`, and `ValidationError.from_exception_data`; no new dependency.
- Keep request-level diagnostics exact by attaching custom errors to nested field locations rather than model-root validators.
- Keep readiness fail-closed despite this plan's green checks; Plans 01-07 and 01-08 remain mandatory.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Root-level Pyright invocation did not load `mcp_server/pyproject.toml` `extraPaths`, yielding only unresolved `config`, `models`, and `services` imports. The same complete task file list passed with the authoritative MCP project configuration and with `mcp_server/src` on `PYTHONPATH`: 0 errors, 0 warnings. All real changed-line diagnostics were fixed before GREEN.
- One worktree sentinel guard initially treated a Windows drive path as relative. No staging occurred; the guard was corrected and rerun before commits.

## Safety

- Tests use only `oracle-catalog-tool-test`.
- No canary, live DB probe, `oracle-catalog-v2` access, deployment, network operation, push, merge, tag, clear, delete, or new dependency.
- No new endpoint, auth path, schema migration, store write API, or control-plane write path.
- Unrelated catalog dumps and primary-checkout dirt remained untouched.

## Known Stubs

None.

## Threat Flags

None - changes harden existing validation and serialization boundaries without introducing a new security-relevant surface.

## Next Phase Readiness

- Plan 01-06 contracts are green and ready for serial Plan 01-07.
- Phase 2 remains blocked: `nyquist_compliant: false` and `ready_for_phase_2=false` until Plans 01-07 and 01-08 complete.
- No Phase 2 work was started.

## Self-Check: PASSED

- Summary and all 13 modified/created plan files exist.
- Commits `33c4457`, `56826fa`, and `12945f6` exist in docs → RED → GREEN order.
- Frontmatter includes `status: complete` and all 14 plan requirement IDs.
- Latest focused pytest, full task regression, Ruff, formatting, Pyright, readiness, and trailer checks passed.

---
*Phase: 01-strict-contracts-and-catalog-v2-identity*
*Completed: 2026-07-18*
