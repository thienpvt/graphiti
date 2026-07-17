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
  - Private _match_entity_graph_key for shell-less standalone item/ref fullmatch
  - ENTITY_TYPE_PREFIXES expanded with System/DatabaseLink/SourceArtifact only
  - Parent shell system_key authority over nested entity/endpoint keys
  - Procedure/Function required nonempty #OVERLOAD; catalog-v1 reject without rewrite
  - IDEN-08 exact graph_key echo on validated model paths
  - No untyped graph_keys or VerifyEdgeRef expected raw graph-key fields
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
    - Remove untyped graph-key convenience fields (extra=forbid)

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
  - "Request shell system_key is sole system authority; standalone items fullmatch only via _match_entity_graph_key"
  - "Procedure/Function require terminal nonempty #OVERLOAD; package optional segment"
  - "No dual-version rewrite helper; catalog-v1 prefix-only keys rejected"
  - "Remove ResolveTypedEntitiesRequest.graph_keys and VerifyEdgeRef expected_*_graph_key (UUID expectations only)"
  - "catalog_service.py stale graph_keys / expected_*_graph_key reads removed with model fields"

patterns-established:
  - "Pattern: validate_entity_graph_key(*, entity_type, graph_key, system_key) pure fullmatch + system equality"
  - "Pattern: _match_entity_graph_key(entity_type, graph_key) for shell-less fullmatch"
  - "Pattern: parent model_validator walks nested entities/endpoints against shell system_key"
  - "Pattern: SourceArtifact SOURCE:: key distinct from provenance source_key"
  - "Pattern: typed ResolveEntityRef only; no untyped graph_keys list"

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
  - id: D8
    description: Untyped graph_keys and VerifyEdgeRef expected raw graph-key fields forbidden
    requirement: IDEN-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_resolve_typed_entities_forbids_raw_graph_keys_field
        status: pass
    human_judgment: false
  - id: D9
    description: Shell system mismatch fails all remaining graph-key input paths
    requirement: IDEN-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py::test_shell_mismatch_entity_upsert_path
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-07-18
status: complete
---

# Phase 1 Plan 02: Catalog-v2 Graph-Key Grammar Registry Summary

**Pure fullmatch registry for 18 entity types with shell-owned FE/BO/COMMON system scope, overload-required Procedure/Function, fail-closed catalog-v1 rejection, and no untyped graph-key bypass fields.**

## Performance

- **Duration:** ~40 min (incl. post-plan IDEN-03/04 bypass correction)
- **Started:** 2026-07-17T19:08:11Z
- **Completed:** 2026-07-18
- **Tasks:** 2/2 + correction
- **Files modified:** 7

## Accomplishments

- TDD RED committed failing 18-type grammar + v1/overload/system-mismatch/IDEN-08 matrix
- GREEN implemented pure `catalog_graph_key.py` and wired model/parent validators
- Post-plan correction closed untyped graph-key bypasses (field removal + path matrix)
- Full `test_catalog_models.py` green (181 passed)
- Ruff clean; scoped Pyright 0 errors on registry, models, and test file
- REFACTOR no-op for original plan; correction simplified validators via `_match_entity_graph_key`

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED — 18-type grammar and v1 rejection matrix | `565a75d` | `mcp_server/tests/test_catalog_models.py` |
| 2 | GREEN — registry module and model hooks | `ac92232` | `catalog_graph_key.py` + model hooks + fixture fix |
| C1 | RED — cover all graph-key input paths | `b1cc868` | `mcp_server/tests/test_catalog_models.py` |
| C2 | GREEN — close untyped graph-key bypasses | `4b8c089` | entities/edges/provenance/graph_key + tests |
| C3 | RED — expose stale graph-key service reads | `a8bcd3e` | `test_catalog_service.py` |
| C4 | GREEN — remove stale graph-key service reads | `fea1377` | `catalog_service.py` + service tests |

## TDD Gate Compliance

1. RED commit present: `test(01-02): add failing grammar and v1 rejection matrix` (`565a75d`) — product source absent
2. GREEN commit present: `feat(01-02): implement catalog-v2 graph-key grammar registry` (`ac92232`)
3. REFACTOR: explicit no-op — GREEN minimal; no further cleanup commit
4. Correction RED: `test(01-02): cover all graph-key input paths` (`b1cc868`)
5. Correction GREEN: `fix(01-02): close untyped graph-key validation bypasses` (`4b8c089`)
6. Service RED: `test(01-02): expose stale graph-key service reads` (`a8bcd3e`)
7. Service GREEN: `fix(01-02): remove stale graph-key service reads`

### RED results

- Selection: `-k 'grammar or overload or system_mismatch or v1_key or catalog_v1 or graph_key_echo'`
- 15 failed, 20 passed, 130 deselected
- pytest exit code 1; root-safe RED gate exit 0

### GREEN results

- Full suite after initial GREEN: `170 passed`
- Full suite after correction: models `181` + focused Phase1 `389 passed`
- Ruff: all checks passed
- Pyright: 0 errors (registry + models + test file)

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

## Post-Plan Correction (IDEN-03/04 bypasses)

### Removals

| Field | Model | Reason |
|-------|-------|--------|
| `graph_keys: list[str] \| None` | `ResolveTypedEntitiesRequest` | Untyped bypass of fullmatch + entity_type |
| `expected_source_graph_key` | `VerifyEdgeRef` | Unvalidated raw string; no entity type |
| `expected_target_graph_key` | `VerifyEdgeRef` | Unvalidated raw string; no entity type |

Kept: `expected_source_uuid` / `expected_target_uuid` only.

### Path matrix (shell system mismatch fails)

| Path | Model entry |
|------|-------------|
| entity upsert | `UpsertTypedEntitiesRequest.entities[].graph_key` |
| edge source | `UpsertTypedEdgesRequest.edges[].source_graph_key` |
| edge target | `UpsertTypedEdgesRequest.edges[].target_graph_key` |
| provenance entity target | `UpsertProvenanceRequest.entity_targets[].graph_key` |
| batch nested entity | `UpsertCatalogBatchRequest.entities[].graph_key` |
| resolve ref | `ResolveTypedEntitiesRequest.entities[].graph_key` |
| verify entity ref | `VerifyCatalogBatchRequest.entities[].graph_key` |

All remaining paths call `_match_entity_graph_key` and/or `validate_entity_graph_key`.

### Service compatibility (same plan)

- Removed `request.graph_keys` branch from `resolve_typed_entities` (empty typed resolve proceeds via read gate/store; no write)
- Removed `expected_source_graph_key` / `expected_target_graph_key` compares in `_verify_edges`; UUID expectations only
- Production `mcp_server/src` has zero matches for the three removed attribute names
- Service fixtures retargeted to catalog-v2 shell/keys; focused suite: models+identity+service+store_unit

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

**3. [Rule 2 - Missing critical] Untyped graph-key validation bypasses**
- **Found during:** Post-plan review (coordinator)
- **Issue:** `ResolveTypedEntitiesRequest.graph_keys` and `VerifyEdgeRef.expected_*_graph_key` accepted arbitrary strings without fullmatch/type
- **Fix:** Field removal + `_match_entity_graph_key` simplification; RED path matrix
- **Files modified:** models + `catalog_service.py` + service fixtures
- **Commits:** `b1cc868`, `4b8c089`, `a8bcd3e`, `fea1377`

Otherwise plan executed as written. No dual-version rewrite helper. No edge topology map. No UUID material versioning changes beyond grammar.

## Threat Flags

None new beyond plan mitigations T-01-06..10 (fullmatch registry, system match, v1 reject, no COMMON default, keys not Cypher labels). Closed untyped-string bypass surface at model boundary.

## Safety Flags

- No canary / `oracle-catalog-v2` access
- Unit tests only; group_id fixtures remain `oracle-catalog-tool-test`
- No network/Neo4j/embedder/LLM/queue imports in `catalog_graph_key.py`
- `_grammar_append_snippet.py` absent

## Self-Check: PASSED

- `mcp_server/src/models/catalog_graph_key.py` FOUND
- `_match_entity_graph_key` + `validate_entity_graph_key` present; `_body` removed
- Removals: `graph_keys`, `expected_source_graph_key`, `expected_target_graph_key` absent from model fields
- Production `mcp_server/src` zero matches for removed attribute names
- Commits FOUND: `565a75d`, `ac92232`, `b1cc868`, `4b8c089`, `a8bcd3e`, `fea1377`
- Suite: models+identity+service+store_unit 389 passed; Ruff pass; Pyright 0
- STATE guards unchanged: total_phases=7, completed_phases=1, total_plans=7, completed_plans=4, percent=14
- No new dependency
- Unrelated working-tree dirt preserved

## Known Stubs

None.

## Self-Check: PASSED

- `mcp_server/src/models/catalog_graph_key.py` FOUND
- Commit `565a75d` FOUND
- Commit `ac92232` FOUND
- `test_catalog_models.py` 170 passed FOUND
