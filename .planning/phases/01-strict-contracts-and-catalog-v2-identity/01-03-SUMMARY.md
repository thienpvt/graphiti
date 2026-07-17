---
phase: 01-strict-contracts-and-catalog-v2-identity
plan: 03
subsystem: catalog-identity
tags: [catalog-v2, uuid5, identity, IDEN, SAFE-05, TDD]

requires:
  - phase: 01-strict-contracts-and-catalog-v2-identity
    provides: CatalogStrictModel shells; graph-key grammar; IDENTITY_SCHEMA_VERSION constant
provides:
  - Versioned catalog-v2 UUID materials for five existing helpers (signatures stable)
  - Pure unpersisted EvidenceLink / Manifest / PreparedPlan identity helpers
  - FE/BO and Procedure overload non-collision goldens
  - v1 material inequality and ACCEPT_TAB not-as-UUID guards (IDEN-13)
  - SAFE-05 signature non-authority coverage for all eight helpers
  - IDEN-08 exact graph_key echo on service resolve/verify/result paths
affects:
  - 01-04 validation/error conversion
  - Phase 2 write-adjacent evidence/manifest/prepare paths (helpers only; no wiring yet)

tech-stack:
  added: []
  patterns:
    - Material-only UUIDv5 versioning via IDENTITY_SCHEMA_VERSION segment after group_id
    - Pure future-kind helpers without store/service/control-plane wiring
    - Single-constant authority from catalog_common (no duplicate literal in product)

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_identity.py
    - mcp_server/tests/test_catalog_identity.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Insert exact catalog-v2 segment after group_id in all five existing materials; signatures unchanged"
  - "Add three pure future helpers only; no persistence/service/store wiring"
  - "Import single IDENTITY_SCHEMA_VERSION from catalog_common; tests may pin 'catalog-v2' only as expected value"
  - "REFACTOR no-op for 01-03; helpers already minimal"
  - "No dual-version shim; v1 materials never accepted as v2 goldens"

patterns-established:
  - "Pattern: f'{group_id}|{IDENTITY_SCHEMA_VERSION}|{kind}|{key}' UUIDv5 material"
  - "Pattern: future kinds (EvidenceLink/Manifest/PreparedPlan) pure-only until owning phase"
  - "Pattern: service UUID pins recompute via helpers (material break, no fixture rewrite needed)"

requirements-completed: [IDEN-07, IDEN-08, IDEN-10, IDEN-11, IDEN-13, SAFE-05, TEST-03]

coverage:
  - id: D1
    description: Entity/edge/source/batch/mentions UUID materials include catalog-v2 segment
    requirement: IDEN-10
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py::test_catalog_entity_uuid_matches_uuid5
        status: pass
    human_judgment: false
  - id: D2
    description: FE/BO same Oracle body yield different entity UUIDs under one group_id
    requirement: IDEN-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py::test_fe_bo_same_oracle_body_different_entity_uuids
        status: pass
    human_judgment: false
  - id: D3
    description: Procedure overload #a vs #b yield different entity UUIDs
    requirement: TEST-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py::test_procedure_overload_discriminator_yields_different_uuids
        status: pass
    human_judgment: false
  - id: D4
    description: Pure EvidenceLink/Manifest/PreparedPlan helpers with catalog-v2 materials
    requirement: IDEN-11
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py::test_catalog_evidence_link_uuid_matches_uuid5
        status: pass
    human_judgment: false
  - id: D5
    description: SAFE-05 signatures have no caller UUID authority params
    requirement: SAFE-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py::test_identity_functions_do_not_accept_caller_uuid_authority
        status: pass
    human_judgment: false
  - id: D6
    description: v1 material UUID never equals catalog-v2; ACCEPT_TAB digests not UUID goldens
    requirement: IDEN-13
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py::test_v1_material_uuid_never_equals_catalog_v2
        status: pass
    human_judgment: false
  - id: D7
    description: IDEN-08 exact complete graph_key echo on resolve/verify/result service paths
    requirement: IDEN-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py::test_resolve_graph_key_echo_exact_full_system_scoped_key_iden08
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-07-18
status: complete
---

# Phase 1 Plan 03: Versioned Catalog-v2 UUID Materials Summary

**UUIDv5 materials versioned with explicit `catalog-v2` segment; pure future helpers added without persistence.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-07-17T19:29:49Z
- **Completed:** 2026-07-17T19:33:00Z
- **Tasks:** 2 (RED + GREEN; REFACTOR no-op)
- **Files modified:** 3

## Accomplishments

- Versioned five existing identity helpers via `IDENTITY_SCHEMA_VERSION` after `group_id`
- Added pure `catalog_evidence_link_uuid`, `catalog_manifest_uuid`, `catalog_prepared_plan_uuid`
- Proved FE/BO and Procedure overload non-collision; v1 inequality; ACCEPT_TAB not UUID goldens
- SAFE-05 signature coverage for all eight helpers; purity import ban retained
- IDEN-08 exact graph_key echo asserts on resolve/verify/upsert result paths
- Service/store unit suites green without fixture UUID rewrites (helpers recompute)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — versioned identity goldens and FE/BO overload** - `e0b7218` (test)
2. **Task 2: GREEN — version helpers and call-site fixture pins** - `66cf30f` (feat)

**REFACTOR:** no-op — helpers already minimal after ruff format; no separate refactor commit.

**Plan metadata:** (docs commit follows)

_Note: TDD RED → GREEN sequence verified; product source absent from RED commit._

## Files Created/Modified

- `mcp_server/src/services/catalog_identity.py` - catalog-v2 materials + three pure future helpers
- `mcp_server/tests/test_catalog_identity.py` - versioned goldens, FE/BO, overload, IDEN-13, SAFE-05, future helpers
- `mcp_server/tests/test_catalog_service.py` - IDEN-08 exact graph_key echo on resolve/verify/result

## Material Table

| Helper | Signature (unchanged / new) | Material |
|--------|-----------------------------|----------|
| `catalog_entity_uuid` | `(namespace, group_id, entity_type, graph_key) -> str` | `group_id\|catalog-v2\|entity_type\|graph_key` |
| `catalog_edge_uuid` | `(namespace, group_id, edge_type, edge_key) -> str` | `group_id\|catalog-v2\|edge_type\|edge_key` |
| `catalog_source_uuid` | `(namespace, group_id, source_key) -> str` | `group_id\|catalog-v2\|Source\|source_key` |
| `catalog_batch_uuid` | `(namespace, group_id, batch_id) -> str` | `group_id\|catalog-v2\|Batch\|batch_id` |
| `catalog_mentions_uuid` | `(namespace, group_id, source_uuid, entity_uuid) -> str` | `group_id\|catalog-v2\|Mentions\|source_uuid\|entity_uuid` |
| `catalog_evidence_link_uuid` | `(namespace, group_id, link_key) -> str` | `group_id\|catalog-v2\|EvidenceLink\|link_key` |
| `catalog_manifest_uuid` | `(namespace, group_id, batch_id) -> str` | `group_id\|catalog-v2\|Manifest\|batch_id` |
| `catalog_prepared_plan_uuid` | `(namespace, group_id, plan_id) -> str` | `group_id\|catalog-v2\|PreparedPlan\|plan_id` |

`canonical_sha256` algorithm unchanged. Single constant authority: `models.catalog_common.IDENTITY_SCHEMA_VERSION`.

## Goldens / Test Counts

| Suite | Count | Result |
|-------|------:|--------|
| RED focused (`-k uuid or catalog_v2 or graph_key_echo or overload or fe_bo or accept_tab`) | 12 failed / 18 passed | pytest rc=1 (RED gate) |
| GREEN identity | 28 | pass |
| GREEN identity+service+store | 221 | pass |
| Models regression | 181 | pass |
| Combined focused + models | 402 | pass |

## Decisions Made

- Material-only break (signatures stable) to avoid broad service rewrite
- Future helpers pure-only; no Phase 2 premature wiring
- REFACTOR no-op

## Deviations from Plan

None - plan executed exactly as written.

Store unit fixtures needed no UUID pin updates (uses opaque fixture UUID strings, not uuid5 goldens).

## Threat Flags

None new beyond plan threat model mitigations:

| Threat | Mitigation | Status |
|--------|------------|--------|
| T-01-11 Spoofing caller UUID | No caller uuid params; SAFE-05 signature tests | mitigated |
| T-01-12 FE/BO collision | System-scoped keys in material | mitigated |
| T-01-13 silent v1 accept | Always catalog-v2; v1 inequality; no dual helper | mitigated |
| T-01-14 identity logs | Helpers pure, no logging | accepted |

## Safety Flags

- Zero forbidden imports (neo4j/embedder/llm/queue/store/service) in `catalog_identity.py`
- Zero persistence/control-plane wiring for EvidenceLink/Manifest/PreparedPlan
- No canary execution; no `oracle-catalog-v2` access
- Test group only `oracle-catalog-tool-test`
- No dual-version shim; no caller UUID authority

## Verification

```
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_identity.py \
  mcp_server/tests/test_catalog_service.py \
  mcp_server/tests/test_catalog_store_unit.py \
  mcp_server/tests/test_catalog_models.py -q --tb=line
# 402 passed

uv run --project mcp_server ruff check mcp_server/src/services/catalog_identity.py \
  mcp_server/tests/test_catalog_identity.py
# All checks passed

cd mcp_server && uv run pyright src/services/catalog_identity.py \
  tests/test_catalog_identity.py tests/test_catalog_service.py tests/test_catalog_store_unit.py
# 0 errors
```

## TDD Gate Compliance

1. RED: `e0b7218` `test(01-03): add failing versioned identity goldens` — product source absent; pytest rc=1
2. GREEN: `66cf30f` `feat(01-03): version catalog-v2 UUID materials and pure future helpers`
3. REFACTOR: no-op (documented)

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_identity.py`
- FOUND: `mcp_server/tests/test_catalog_identity.py`
- FOUND: `mcp_server/tests/test_catalog_service.py`
- FOUND: `01-03-SUMMARY.md`
- FOUND commits: `e0b7218` (RED), `66cf30f` (GREEN)
- Identity suite: 28 passed
- Combined identity+service+store+models: 402 passed
- Ruff: clean; Pyright (project-scoped): 0 errors
- State guard: total_phases=7, completed_phases=1, total_plans=7, completed_plans=5, percent=14

## Next

Plan 01-04. Phase 1 incomplete. Phase 2 blocked until Phase 1 gate.