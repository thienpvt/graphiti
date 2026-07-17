---
phase: 01-strict-contracts-and-catalog-v2-identity
plan: 02
subsystem: catalog-models
tags: [catalog-v2, graph-key, grammar, IDEN, fullmatch, TDD]

requires:
  - phase: 01-strict-contracts-and-catalog-v2-identity
    provides: CatalogStrictModel shells; required catalog-v2/system_key; CONT-08 codes
provides:
  - Pure catalog_graph_key.validate_entity_graph_key fullmatch registry (18 types)
  - ENTITY_TYPE_PREFIXES expanded with System/DatabaseLink/SourceArtifact only
  - Parent shell system_key authority over nested entity/endpoint keys
  - Procedure/Function required nonempty #OVERLOAD; catalog-v1 reject without rewrite
  - IDEN-08 exact graph_key echo on validated model paths
affects:
  - 01-03 identity UUID material versioning
  - 01-04 validation error conversion / SAFE gates
  - later service/MCP request construction using v2 keys

tech-stack:
  added: []
  patterns:
    - Pure re.fullmatch grammar registry module (no I/O imports)
    - Shell system_key revalidation of nested keys after child construction
    - Fail-closed exact str equality; no NFC/normalize/rewrite helpers

key-files:
  created:
    - mcp_server/src/models/catalog_graph_key.py
  modified:
    - mcp_server/src/models/catalog_common.py
    - mcp_server/src/models/catalog_entities.py
    - mcp_server/src/models/catalog_edges.py
    - mcp_server/src/models/catalog_provenance.py
    - mcp_server/src/models/catalog_batch.py
    - mcp_server/tests/test_catalog_models.py

key-decisions:
  - "Centralize complete fullmatch grammar in pure catalog_graph_key.py; 18 entity types exactly"
  - "Request shell system_key is sole system authority; item validators accept any closed FE|BO|COMMON then parents recheck"
  - "Procedure/Function require terminal nonempty #OVERLOAD; package optional segment"
  - "No dual-version rewrite helper; catalog-v1 prefix-only keys rejected"
  - "REFACTOR no-op: GREEN is minimal; no further structure change"

patterns-established:
  - "Pattern: validate_entity_graph_key(*, entity_type, graph_key, system_key) pure fullmatch + system equality"
  - "Pattern: parent model_validator walks nested entities/endpoints against shell system_key"
  - "Pattern: SourceArtifact SOURCE:: key distinct from provenance source_key"

requirements-completed: [IDEN-03, IDEN-04, IDEN-05, IDEN-06, IDEN-08, IDEN-09, IDEN-12]

coverage:
  - id: D1
    description: 18-type positive graph-key fullmatch under FE
    requirement: IDEN-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_grammar_positive_key_per_entity_type
        status: pass
    human_judgment: false
  - id: D2
    description: catalog-v1 and invalid grammar rejected without rewrite
    requirement: IDEN-12
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_grammar_rejects_catalog_v1_key_without_rewrite
        status: pass
    human_judgment: false
  - id: D3
    description: Procedure/Function require nonempty overload package and standalone
    requirement: IDEN-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_grammar_procedure_function_require_nonempty_overload_package_and_standalone
        status: pass
    human_judgment: false
  - id: D4
    description: Nested system mismatch fails under shell authority
    requirement: IDEN-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_grammar_system_mismatch_rejects_nested_entity_under_shell
        status: pass
    human_judgment: false
  - id: D5
    description: FE/BO same Oracle body remain distinct full keys
    requirement: IDEN-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_grammar_fe_bo_same_body_valid_under_matching_shells_and_unequal
        status: pass
    human_judgment: false
  - id: D6
    description: IDEN-08 exact graph_key echo on entity/edge/resolve/provenance paths
    requirement: IDEN-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_graph_key_echo_exact_equality_iden08_long_multi_segment
        status: pass
    human_judgment: false
  - id: D7
    description: System DatabaseLink SourceArtifact allowlisted only; no business types
    requirement: IDEN-09
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_entity_type_prefixes_has_eighteen_types
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-18
status: complete
---

# Phase 1 Plan 02: Catalog-v2 Graph-Key Grammar Registry Summary

**Pure fullmatch registry for 18 entity types with shell-owned FE/BO/COMMON system scope, overload-required Procedure/Function, and fail-closed catalog-v1 rejection without rewrite.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-17T19:08:11Z
- **Completed:** 2026-07-18
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- TDD RED committed failing 18-type grammar + v1/overload/system-mismatch/IDEN-08 matrix
- GREEN implemented pure `catalog_graph_key.py` and wired model/parent validators
- Full `test_catalog_models.py` green (170 passed)
- Ruff clean; scoped Pyright 0 errors on new module, models, and test file
- REFACTOR no-op (no dual-version rewrite helper)

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED — 18-type grammar and v1 rejection matrix | `565a75d` | `mcp_server/tests/test_catalog_models.py` |
| 2 | GREEN — registry module and model hooks | `ac92232` | `catalog_graph_key.py` + model hooks + fixture fix |

## TDD Gate Compliance

1. RED commit present: `test(01-02): add failing grammar and v1 rejection matrix` (`565a75d`) — product source absent
2. GREEN commit present: `feat(01-02): implement catalog-v2 graph-key grammar registry` (`ac92232`)
3. REFACTOR: explicit no-op — GREEN minimal; no further cleanup commit

### RED results

- Selection: `-k 'grammar or overload or system_mismatch or v1_key or catalog_v1 or graph_key_echo'`
- 15 failed, 20 passed, 130 deselected
- pytest exit code 1; root-safe RED gate exit 0

### GREEN results

- Full suite: `170 passed`
- Ruff: all checks passed
- Pyright (`--project mcp_server/pyproject.toml`, includes test file): 0 errors

## Grammar Coverage (18 positive rows)

| entity_type | example key |
|-------------|-------------|
| System | `SYSTEM::FE::CORE` |
| Database | `DATABASE::FE::ORCL` |
| DictionaryDocument | `DOC::FE::ORCL.HR_DICT` |
| Schema | `SCHEMA::FE::ORCL.HR` |
| Table | `TABLE::FE::ORCL.HR.EMPLOYEES` |
| View | `VIEW::FE::ORCL.HR.EMP_V` |
| MaterializedView | `MVIEW::FE::ORCL.HR.EMP_MV` |
| Column | `COLUMN::FE::ORCL.HR.EMPLOYEES.EMP_ID` |
| Constraint | `CONSTRAINT::FE::ORCL.HR.EMP_PK` |
| Index | `INDEX::FE::ORCL.HR.EMP_IX` |
| Package | `PACKAGE::FE::ORCL.HR.EMP_PKG` |
| Procedure | `PROCEDURE::FE::ORCL.HR.EMP_PKG.HIRE#1` |
| Function | `FUNCTION::FE::ORCL.HR.EMP_PKG.GET_SAL#ARGS(P_ID)` |
| Trigger | `TRIGGER::FE::ORCL.HR.EMP_BI` |
| Sequence | `SEQUENCE::FE::ORCL.HR.EMP_SEQ` |
| Synonym | `SYNONYM::FE::ORCL.HR.EMP_SYN` |
| DatabaseLink | `DBLINK::FE::ORCL.REMOTE_HR` |
| SourceArtifact | `SOURCE::FE::PDF/HR_CATALOG#p12` |

Negatives covered: catalog-v1 prefix-only, lowercase/unknown system, wrong segment count, lowercase ident, type/prefix mismatch, missing/empty overload, empty/overlong key, shell system mismatch.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Parametrize decorator attached to helper after insert**
- **Found during:** Task 2 GREEN verification
- **Issue:** `_retarget_graph_keys_for_system` was inserted between `@pytest.mark.parametrize` and `test_system_key_required_closed_set`, causing fixture error
- **Fix:** Move helper above parametrize; keep decorator on test
- **Files modified:** `mcp_server/tests/test_catalog_models.py`
- **Commit:** `ac92232`

**2. [Rule 2 - Missing critical] Parent shell system authority**
- **Found during:** Task 2
- **Issue:** Item-level validators alone cannot see shell `system_key`
- **Fix:** Parent `model_validator` on entity/edge/provenance/batch/verify walks nested keys with shell system
- **Files modified:** entities/edges/provenance/batch
- **Commit:** `ac92232`

Otherwise plan executed as written. No dual-version rewrite helper. No edge topology map. No UUID material changes.

## Threat Flags

None new beyond plan mitigations T-01-06..10 (fullmatch registry, system match, v1 reject, no COMMON default, keys not Cypher labels).

## Safety Flags

- No canary / `oracle-catalog-v2` access
- Unit tests only; group_id fixtures remain `oracle-catalog-tool-test`
- No network/Neo4j/embedder/LLM/queue imports in `catalog_graph_key.py`
- No new dependency
- Unrelated working-tree dirt preserved

## Known Stubs

None.

## Self-Check: PASSED

- `mcp_server/src/models/catalog_graph_key.py` FOUND
- Commit `565a75d` FOUND
- Commit `ac92232` FOUND
- `test_catalog_models.py` 170 passed FOUND
