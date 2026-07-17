---
phase: 01-strict-contracts-and-catalog-v2-identity
plan: 04
subsystem: catalog-validation
tags: [catalog-v2, SAFE-08, CONT-07, FastMCP, structured-errors, TDD]

requires:
  - phase: 01-strict-contracts-and-catalog-v2-identity
    provides: CatalogStrictModel shells; graph-key grammar; versioned identity materials
provides:
  - catalog_validation_error_to_structured pure SAFE-08 adapter (UUID correlation normalize + sanitized field_path)
  - CatalogStructuredError DTO
  - CatalogSafeFastMCP.call_tool wires converter for seven catalog tools only
  - CONT-07 production proof via FastMCP ToolManager/call_tool + typed request annotations on all seven catalog tools
  - No-side-effect spy matrix for invalid version/system/grammar/flags/nested extras
affects:
  - 01-05 Phase 1 gate report
  - later MCP catch/log paths that may surface structured validation errors

tech-stack:
  added: []
  patterns:
    - FastMCP typed request params → fn_metadata.arg_model.model_validate before tool body
    - CatalogSafeFastMCP.call_tool catches catalog ToolError+ValidationError cause → structured JSON ToolError
    - Fresh ToolError raised outside except so client chain has no ValidationError
    - Runtime registration/type-hint/schema inspection plus in-process call_tool spies

key-files:
  created: []
  modified:
    - mcp_server/src/models/catalog_common.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_models.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Converter lives in catalog_common; CatalogSafeFastMCP wires it for seven catalog tools only"
  - "Fresh ToolError(JSON) outside except block; legacy tools and non-validation ToolErrors untouched"
  - "No broad seven-wrapper catch refactor; preserve thin MCP wrappers and existing type(e).__name__ logging"
  - "Production CONT-07 proof uses mcp.call_tool + ToolManager.get_tool annotations, not source-text regex alone"
  - "REFACTOR no-op for 01-04; no dual-version helpers"

patterns-established:
  - "Pattern: catalog_validation_error_to_structured(exc, correlation_id=) → code/message/field_path/retryable/correlation_id"
  - "Pattern: map identity_schema_version → unsupported_identity_schema; system_key → invalid_system_key; else validation_error"
  - "Pattern: CatalogSafeFastMCP rewrites catalog validation ToolError to SAFE-08 JSON; legacy unchanged"
  - "Pattern: FastMCP call_tool rejects invalid nested payloads before tool.fn; body/service/store/embedder spies stay zero"

requirements-completed: [CONT-07, SAFE-08]

coverage:
  - id: D1
    description: SAFE-08 structured validation error shape with safe bounded fields
    requirement: SAFE-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_structured_error_shape_has_safe_fields
        status: pass
    human_judgment: false
  - id: D2
    description: Structured error message non-leaking and length-bounded
    requirement: SAFE-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_structured_error_message_bounded_and_non_leaking
        status: pass
    human_judgment: false
  - id: D3
    description: Seven catalog tools bind typed Pydantic request models at FastMCP registration
    requirement: CONT-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_catalog_tools_bind_typed_pydantic_request_models
        status: pass
    human_judgment: false
  - id: D4
    description: FastMCP call_tool rejects invalid nested payloads before body/service/backends with SAFE-08 structured ToolError
    requirement: CONT-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_fastmcp_call_tool_rejects_invalid_nested_payloads_before_body_no_side_effect
        status: pass
    human_judgment: false
  - id: D5
    description: Invalid identity schema/system/grammar never call service/store/embedder
    requirement: CONT-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_invalid_identity_schema_never_calls_service_store_or_embedder
        status: pass
    human_judgment: false
  - id: D6
    description: Catalog call_tool ToolError is five-field SAFE-08 JSON with UUID correlation_id and no ValidationError chain
    requirement: SAFE-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_fastmcp_catalog_validation_returns_structured_safe_tool_error
        status: pass
    human_judgment: false
  - id: D7
    description: Non-catalog ToolError and legacy tool errors are not rewritten to catalog SAFE-08 shape
    requirement: SAFE-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_fastmcp_unrelated_tool_error_not_rewritten_to_structured
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-07-18
status: complete
---

# Phase 1 Plan 04: Structured Errors and CONT-07 Boundary Summary

**SAFE-08 converter wired through CatalogSafeFastMCP for seven catalog tools; CONT-07 typed-param boundary rejects invalid nested payloads before body/service/store/embedder with structured ToolError only.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-07-17T19:36:24Z
- **Completed:** 2026-07-18
- **Tasks:** 2/2 (+ hard-gate wiring correction)
- **Files modified:** 5 product/test files (+ planning docs)

## Accomplishments

- Added `catalog_validation_error_to_structured` returning exactly `code`, `message`, `field_path`, `retryable`, `correlation_id`
- Mapped identity/system validation locs to `unsupported_identity_schema` / `invalid_system_key`; default `validation_error`; `retryable=False`; message ≤512 and non-leaking
- Hardened converter: server UUID correlation normalize; sanitized bounded field_path; strip FastMCP `request.` wrapper
- Wired `CatalogSafeFastMCP.call_tool` for seven catalog tools only: catch ToolError+ValidationError cause → fresh structured JSON ToolError outside except
- Proved production CONT-07 boundary via FastMCP `ToolManager`/`call_tool` + runtime type-hint/schema inspection for all seven frozen catalog tools
- Spy matrix: invalid schema version, system key, grammar, false immutable flags, unknown nested fields, empty collection — zero service/store/embedder/schema/tx/status/queue/LLM entry
- Legacy/unknown ToolErrors not rewritten

## Task Commits

1. **Task 1: RED — structured error shape, production boundary, no-side-effect spies** - `cc0fa80` (test)
2. **Task 2: GREEN — converter and mandatory production CONT-07 path** - `f16dc0c` (feat)
3. **Hard-gate RED — require structured SAFE-08 ToolError on catalog call_tool** - `c401df0` (test)
4. **Hard-gate GREEN — wire CatalogSafeFastMCP structured ToolError** - `5c2ab3b` (feat)

**REFACTOR:** no-op — converter and tests already minimal; no dual-version helpers.

**Plan metadata:** docs commit after this summary update

## Production CONT-07 / SAFE-08 mechanism

| Item | Value |
|------|-------|
| API path | `CatalogSafeFastMCP.call_tool` → `ToolManager.call_tool` → `Tool.run` → `FuncMetadata.call_fn_with_arg_validation` → `arg_model.model_validate` before `tool.fn` |
| Installed package | `mcp` FastMCP in `mcp_server` venv |
| Registration proof | `mcp._tool_manager.get_tool(name).fn_metadata.arg_model.model_fields['request'].annotation` + `typing.get_type_hints(tool.fn)` + `list_tools()` inputSchema `$ref` |
| Invocation proof | In-process `await server.mcp.call_tool(name, {'request': invalid_payload})` raises fresh `ToolError` with SAFE-08 JSON message; no ValidationError in `__cause__`/`__context__`; body spy empty |
| Converter wiring | `CatalogSafeFastMCP` rewrites only seven catalog tools when ToolError wraps ValidationError; serializes `catalog_validation_error_to_structured`; legacy tools unchanged |

### Seven-tool typed matrix

| Tool | Request model | Typed annotation retained |
|------|---------------|---------------------------|
| upsert_typed_entities | UpsertTypedEntitiesRequest | yes |
| resolve_typed_entities | ResolveTypedEntitiesRequest | yes |
| verify_catalog_batch | VerifyCatalogBatchRequest | yes |
| upsert_typed_edges | UpsertTypedEdgesRequest | yes |
| upsert_provenance | UpsertProvenanceRequest | yes |
| get_catalog_ingest_status | GetCatalogIngestStatusRequest | yes (no identity fields; extra still forbidden) |
| upsert_catalog_batch | UpsertCatalogBatchRequest | yes |

Legacy tools: 14 names preserved via existing registration suite.

### Invalid / side-effect spy matrix

| Case | Boundary | Spies assert_not_called |
|------|----------|-------------------------|
| identity_schema_version catalog-v1/v0 | model_validate + call_tool | body, CatalogService.*, get_client, embedder |
| system_key fe/UNKNOWN | model_validate + call_tool | same |
| v1/malformed/lowercase graph_key | model_validate + call_tool | same |
| atomic/strict_endpoints false | model_validate + call_tool | same |
| unknown shell/nested fields | model_validate + call_tool | same |
| get_catalog_ingest_status extra field | call_tool | same |
| empty entities collection | model_validate | service methods |

## Converter output contract

```text
{
  code: CatalogErrorCode,
  message: str (<=512 Unicode chars, generic),
  field_path: sanitized dotted first loc or None,
  retryable: False,
  correlation_id: UUID string (server-minted when missing/invalid)
}
```

Mappings: `identity_schema_version` → `unsupported_identity_schema`; `system_key` → `invalid_system_key`; else `validation_error`. Never copies `input`, `str(exc)`, payload, stack, credentials, tokens. FastMCP `request.` loc prefix stripped; field_path sanitized/bounded.

## Files Created/Modified

- `mcp_server/src/models/catalog_common.py` — converter + UUID/field_path harden
- `mcp_server/src/models/catalog_responses.py` — `CatalogStructuredError`
- `mcp_server/src/graphiti_mcp_server.py` — `CatalogSafeFastMCP` + `CATALOG_TOOL_NAMES`
- `mcp_server/tests/test_catalog_models.py` — SAFE-08 unit tests
- `mcp_server/tests/test_catalog_service.py` — CONT-07 registration + call_tool + spy + structured ToolError tests

## Decisions Made

- Keep converter pure/shared; wire once via `CatalogSafeFastMCP.call_tool` for seven catalog tools only
- Raise fresh `ToolError(JSON)` outside except so client chain has no ValidationError
- Use actual FastMCP in-process invocation (`mcp.call_tool`) as primary production boundary proof; model_validate spies supplemental
- REFACTOR no-op

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Huge-summary leak fixture used valid length**
- **Found during:** Task 2 GREEN
- **Issue:** test used `'x'*2000` but `MAX_SUMMARY_LENGTH` is 4096, so ValidationError never raised
- **Fix:** oversize by `MAX_SUMMARY_LENGTH + 50`
- **Files modified:** `mcp_server/tests/test_catalog_models.py`
- **Committed in:** `f16dc0c`

**2. [Rule 2 - Critical] Converter unused on production FastMCP path**
- **Found during:** hard-gate correction after initial plan complete
- **Issue:** FastMCP `Tool.run` wraps `ValidationError` as `ToolError(str(exc)) from e`, so pure converter never reached client
- **Fix:** `CatalogSafeFastMCP.call_tool` rewrites only seven catalog tools; serializes converter output; fresh ToolError outside except; legacy/non-validation ToolErrors unchanged
- **Files modified:** `mcp_server/src/graphiti_mcp_server.py`, `mcp_server/src/models/catalog_common.py`, `mcp_server/tests/test_catalog_service.py`
- **Committed in:** `c401df0` (RED), `5c2ab3b` (GREEN)

## Verification Results

| Check | Result |
|-------|--------|
| RED pytest exit code 1 | pass (`cc0fa80`, `c401df0`) |
| Four-file suite post hard-gate | 414 passed |
| Ruff | pass on touched files |
| Pyright (mcp_server scoped) | 0 errors on catalog_common/responses/graphiti_mcp_server + tests |
| Canary / oracle-catalog-v2 / live DB | not run |
| New write/control-plane path | none |

## Threat Flags

None new beyond plan mitigations T-01-15..18 (bounded non-leaking converter; validation-before-side-effect spies; clean client exception chain).

## Safety

- Test group only `oracle-catalog-tool-test`
- No canary, live DB, network, deploy, push/merge/tag, graph clear
- No new dependency
- Seven catalog tool names unchanged; 14 legacy tools preserved

## Known Stubs

None.

## TDD Gate Compliance

1. RED: `cc0fa80` `test(01-04): add failing structured error and CONT-07 boundary spies`
2. GREEN: `f16dc0c` `feat(01-04): add structured validation errors and CONT-07 boundary`
3. Hard-gate RED: `c401df0` `test(01-04): require structured SAFE-08 ToolError on catalog call_tool`
4. Hard-gate GREEN: `5c2ab3b` `feat(01-04): wire SAFE-08 structured ToolError for catalog FastMCP tools`
5. REFACTOR: no-op (documented)

## Self-Check: PASSED

- Files present: catalog_common.py, catalog_responses.py, graphiti_mcp_server.py, test_catalog_models.py, test_catalog_service.py, 01-04-SUMMARY.md
- Commits present: cc0fa80 (RED), f16dc0c (GREEN), c401df0 (hard-gate RED), 5c2ab3b (hard-gate GREEN)
- Converter symbol present once; CatalogStructuredError present; CatalogSafeFastMCP present
- Four-file suite 414 passed; Ruff pass; Pyright 0 errors on touched product/test files
