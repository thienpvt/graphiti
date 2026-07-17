---
phase: 01-strict-contracts-and-catalog-v2-identity
plan: 01
subsystem: catalog-models
tags: [pydantic, catalog-v2, strict-contracts, CONT, IDEN, TEST-01]

requires:
  - phase: 00-baseline-inventory-and-compatibility-policy
    provides: Compatibility/isolation gates; catalog model baseline
provides:
  - CatalogStrictModel with recursive extra=forbid for all request/nested request models
  - Required identity_schema_version=catalog-v2 and system_key FE|BO|COMMON shells
  - Literal[True] atomic and strict_endpoints write flags
  - CONT-08 CatalogErrorCode append-only registry (+9 members)
  - Table-driven model unit matrix for strict contracts
affects:
  - 01-02 graph-key grammar
  - 01-03 identity UUID material
  - 01-04 validation error conversion
  - later MCP/service request construction

tech-stack:
  added: []
  patterns:
    - CatalogStrictModel inheritance (not parent-field config inheritance)
    - Required Literal shell fields without ownership defaults
    - Append-only CatalogErrorCode members

key-files:
  created: []
  modified:
    - mcp_server/src/models/catalog_common.py
    - mcp_server/src/models/catalog_entities.py
    - mcp_server/src/models/catalog_edges.py
    - mcp_server/src/models/catalog_provenance.py
    - mcp_server/src/models/catalog_batch.py
    - mcp_server/tests/test_catalog_models.py

key-decisions:
  - "Shared CatalogStrictModel base in catalog_common; all request/nested request models inherit it"
  - "Response models remain non-strict BaseModel (shared DTO surface, not request trust boundary)"
  - "GetCatalogIngestStatusRequest is strict but omits version/system_key (status-only, no graph keys)"
  - "No dual-version compatibility helper; catalog-v2 only"
  - "REFACTOR no-op: isort cleanup folded into GREEN; no further structure change"

patterns-established:
  - "Pattern: CatalogStrictModel + required Literal['catalog-v2'] + Literal['FE','BO','COMMON'] on identity-bearing domain shells"
  - "Pattern: write flags as Literal[True]=True; false rejected at validation"
  - "Pattern: CONT-04 hash-bearing fields return original string after strip emptiness check"

requirements-completed: [CONT-01, CONT-02, CONT-03, CONT-04, CONT-05, CONT-06, CONT-08, IDEN-01, IDEN-02, TEST-01]

coverage:
  - id: D1
    description: Recursive extra=forbid on shell and nested catalog request models
    requirement: CONT-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_catalog_strict_model_rejects_unknown_shell_and_nested_fields
        status: pass
    human_judgment: false
  - id: D2
    description: Misspelled optional fields fail forbid path
    requirement: CONT-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_misspelled_optional_fields_rejected
        status: pass
    human_judgment: false
  - id: D3
    description: strict_endpoints false rejected
    requirement: CONT-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_strict_endpoints_false_rejected
        status: pass
    human_judgment: false
  - id: D4
    description: atomic false rejected on entity/edge/provenance/batch writes
    requirement: CONT-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_atomic_false_rejected_on_entity_edge_provenance_batch_writes
        status: pass
    human_judgment: false
  - id: D5
    description: identity_schema_version required and rejects non-v2
    requirement: IDEN-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_identity_schema_version_required_and_rejects_non_v2
        status: pass
    human_judgment: false
  - id: D6
    description: system_key required closed set FE/BO/COMMON
    requirement: IDEN-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_system_key_required_closed_set
        status: pass
    human_judgment: false
  - id: D7
    description: source_key/reference_time preserve trailing space
    requirement: CONT-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_source_and_reference_time_preserve_trailing_space
        status: pass
    human_judgment: false
  - id: D8
    description: CONT-08 nine codes present without removing preexisting
    requirement: CONT-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_catalog_error_code_includes_phase1_codes_without_removing_existing
        status: pass
    human_judgment: false
  - id: D9
    description: Accepted entity list order preserved; duplicate items not merged
    requirement: CONT-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_valid_entity_list_order_preserved
        status: pass
    human_judgment: false
  - id: D10
    description: Focused models suite green as unit gate (TEST-01 partial)
    requirement: TEST-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-07-17
status: complete
---

# Phase 01 Plan 01: Strict Contracts and Catalog-v2 Identity Summary

**Fail-closed CatalogStrictModel shells with required catalog-v2/system_key Literals, immutable write flags, CONT-08 codes, and 134 green model unit tests.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-07-17T18:57:10Z
- **Completed:** 2026-07-17T19:00:15Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Introduced shared `CatalogStrictModel` (`extra='forbid'`) and switched every catalog request/nested request model to inherit it.
- Enforced required `identity_schema_version='catalog-v2'` and `system_key` in `FE|BO|COMMON` on all identity-bearing domain request shells.
- Locked `atomic`/`strict_endpoints` to `Literal[True]`; false fails validation.
- Appended nine CONT-08 `CatalogErrorCode` members without removing preexisting codes.
- Table-driven RED→GREEN matrix covers unknown/misspelled fields, flags, version, system_key, byte preservation, order stability.

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — strictness flag version system_key error-code matrix** - `72baa2d` (test)
2. **Task 2: GREEN — CatalogStrictModel shells flags codes** - `6e685e5` (feat)

**Plan metadata:** (pending docs commit)

_Note: REFACTOR gate recorded as no-op; isort cleanup included in GREEN. No dual-version helpers._

## Files Created/Modified

- `mcp_server/src/models/catalog_common.py` - CatalogStrictModel, IDENTITY_SCHEMA_VERSION, SYSTEM_KEYS, CONT-08 codes
- `mcp_server/src/models/catalog_entities.py` - Strict entity shells + version/system_key + Literal atomic
- `mcp_server/src/models/catalog_edges.py` - Strict edge models + Literal atomic/strict_endpoints
- `mcp_server/src/models/catalog_provenance.py` - Strict provenance models + shell Literals
- `mcp_server/src/models/catalog_batch.py` - Strict batch/status requests + shell Literals on batch
- `mcp_server/tests/test_catalog_models.py` - RED matrix + fixture shell updates for positive paths

## Decisions Made

- Response models stay non-strict `BaseModel` (plan allows; request trust boundary only).
- `GetCatalogIngestStatusRequest` strict but without version/system_key (status-only).
- Prefix-only graph-key validators retained until Plan 02.
- No UUID/service/store/canary changes.

## Deviations from Plan

None - plan executed exactly as written.

### Auto-fixed Issues

None.

## TDD Gate Compliance

- RED commit present: `72baa2d test(01-01): add failing strict contract matrix`
- GREEN commit present after RED: `6e685e5 feat(01-01): implement CatalogStrictModel shells and CONT-08 codes`
- REFACTOR: no-op (documented)

## Test Results

| Suite | Result | Notes |
|-------|--------|-------|
| RED focused selection | 34 failed / 14 passed / 48 selected | pytest exit 1 — RED gate OK |
| GREEN full models suite | **134 passed** | `test_catalog_models.py` |
| Ruff scoped | pass | I001 fixed via `--fix` |
| Pyright scoped (6 model files) | 0 errors | mcp_server project |

Safety flags:

- `canary_executed`: false
- `oracle-catalog-v2` access: none
- group_id in tests: `oracle-catalog-tool-test` only
- No store/service/MCP behavior change
- No secret/payload logging introduced

## Threat Coverage

| Threat | Disposition | Mitigation evidence |
|--------|-------------|---------------------|
| T-01-01 Tampering unknown fields | mitigate | CatalogStrictModel recursive forbid + matrix tests |
| T-01-02 Tampering soft flags | mitigate | Literal[True] atomic/strict_endpoints |
| T-01-03 Spoofing system/version | mitigate | Required Literals; no COMMON default |
| T-01-04 Info disclosure | mitigate | No new payload dumps in validators/errors |
| T-01-05 Silent v1 acceptance | mitigate | identity_schema_version required catalog-v2 |
| T-01-SC package installs | accept | No new packages |

## Known Stubs

None.

## Threat Flags

None beyond plan register.

## Issues Encountered

- Coordinator IDE note on undefined `BaseModel`: request modules correctly no longer import `BaseModel`; they inherit `CatalogStrictModel`. Response module retains `BaseModel`. Ruff/Pyright clean.

## Next Phase Readiness

- Plan 01-02 may import `CatalogStrictModel`, `IDENTITY_SCHEMA_VERSION`, `SYSTEM_KEYS`, `ENTITY_TYPE_PREFIXES`.
- Grammar fullmatch, UUID material, structured error converter remain later plans.
- Phase 1 not complete; Phase 2 not ready.

## Self-Check: PASSED

- FOUND: `mcp_server/src/models/catalog_common.py` CatalogStrictModel / IDENTITY_SCHEMA_VERSION / SYSTEM_KEYS / CONT-08
- FOUND: request models inherit CatalogStrictModel
- FOUND: commits `72baa2d`, `6e685e5`
- FOUND: 134 passed models suite; ruff 0; pyright 0
