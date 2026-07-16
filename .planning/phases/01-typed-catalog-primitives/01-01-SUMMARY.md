---
phase: 01-typed-catalog-primitives
plan: 01
subsystem: catalog-models
tags: [pydantic, uuidv5, sha256, catalog, mcp, neo4j, allowlist]

requires: []
provides:
  - CatalogConfig nested under GraphitiConfig.catalog_upsert
  - Allowlisted entity/edge request models and structured responses
  - CatalogErrorCode enum with documented codes
  - Pure UUIDv5 and canonical SHA-256 identity helpers
affects:
  - 01-02 catalog Neo4j store
  - 01-03 catalog service orchestration
  - 01-04 MCP tool registration

tech-stack:
  added: []
  patterns:
    - Fixed server allowlists for 15 entity types and 16 edge types
    - Nested CatalogConfig with env-bound immutable UUID namespace
    - Stdlib-only deterministic identity (uuid5 + sorted JSON SHA-256)

key-files:
  created:
    - mcp_server/src/models/catalog_common.py
    - mcp_server/src/models/catalog_entities.py
    - mcp_server/src/models/catalog_edges.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/src/services/catalog_identity.py
    - mcp_server/tests/test_catalog_models.py
    - mcp_server/tests/test_catalog_identity.py
  modified:
    - mcp_server/src/config/schema.py

key-decisions:
  - "CatalogConfig binds GRAPHITI_CATALOG_UUID_NAMESPACE via model_validator before-mode, no uuid factory"
  - "EnforcedBy requires non-empty evidence at Pydantic model boundary"
  - "Identity helpers return str UUIDs; no caller UUID parameters"

patterns-established:
  - "CatalogConfig.enabled defaults false; valid UUID namespace required only when enabled"
  - "ENTITY_TYPE_PREFIXES + CATALOG_EDGE_TYPES are sole Cypher label/type sources"
  - "canonical_sha256 rejects non-finite floats before JSON dump"

requirements-completed:
  - CONF-01
  - CONF-02
  - CONF-03
  - CONF-04
  - CONF-05
  - SAFE-01
  - SAFE-02
  - SAFE-03
  - IDEN-01
  - IDEN-02
  - IDEN-05
  - IDEN-06
  - IDEN-07
  - IDEN-08

coverage:
  - id: D1
    description: CatalogConfig defaults disabled with no auto-generated UUID namespace and limits 500/2000/5000
    requirement: CONF-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_catalog_config_enabled_defaults_false
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_catalog_config_limits_defaults
        status: pass
    human_judgment: false
  - id: D2
    description: Enabling catalog writes requires a parseable fixed UUID namespace from config/env
    requirement: CONF-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_catalog_config_enabled_requires_valid_namespace
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_graphiti_catalog_uuid_namespace_env
        status: pass
    human_judgment: false
  - id: D3
    description: Allowlisted entity/edge request models reject wrong types, prefixes, protected keys, non-finite values, and bad confidence
    requirement: SAFE-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_entity_item_rejects_wrong_prefix
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_models.py#test_entity_item_rejects_protected_attribute_key
        status: pass
    human_judgment: false
  - id: D4
    description: Deterministic UUIDv5 entity/edge identity and 64-hex canonical SHA-256 with optional client hash audit
    requirement: IDEN-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py#test_catalog_entity_uuid_matches_uuid5
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py#test_canonical_sha256_length_and_lowercase
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_identity.py#test_assert_optional_client_hash_mismatch
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-16
status: complete
---

# Phase 01 Plan 01: Typed Catalog Primitives Summary

**CatalogConfig, allowlisted Pydantic request/response models, structured CatalogErrorCode, and pure UUIDv5/SHA-256 identity helpers with green unit tests.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-16T13:14:21Z
- **Completed:** 2026-07-16T13:26:00Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Nested `CatalogConfig` under `GraphitiConfig.catalog_upsert` with defaults disabled, limits 500/2000/5000, Neo4j-only docs, and env-bound immutable namespace
- Fixed 15 entity type prefixes, 16 edge types, protected properties, and full `CatalogErrorCode` surface
- Pure `catalog_entity_uuid` / `catalog_edge_uuid` / `canonical_sha256` / `assert_optional_client_hash` with 55 unit tests green

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **Task 1: CatalogConfig and allowlisted request models**
   - `bd6290b` test(01-01): add failing tests for catalog config and models
   - `c67e69d` feat(01-01): implement CatalogConfig and allowlisted catalog models
2. **Task 2: Deterministic identity and canonical hash helpers**
   - `ec2d9d6` test(01-01): add failing tests for catalog identity helpers
   - `fb427db` feat(01-01): implement catalog UUIDv5 and canonical SHA-256 helpers

## Files Created/Modified

- `mcp_server/src/config/schema.py` — `CatalogConfig` + `GraphitiConfig.catalog_upsert`
- `mcp_server/src/models/catalog_common.py` — allowlists, limits, `CatalogErrorCode`
- `mcp_server/src/models/catalog_entities.py` — entity request models
- `mcp_server/src/models/catalog_edges.py` — edge request models
- `mcp_server/src/models/catalog_responses.py` — write/resolve/verify responses
- `mcp_server/src/services/catalog_identity.py` — uuid5 + SHA-256 helpers
- `mcp_server/tests/test_catalog_models.py` — config/validation unit tests
- `mcp_server/tests/test_catalog_identity.py` — identity/hash unit tests

## Decisions Made

- Bound `GRAPHITI_CATALOG_UUID_NAMESPACE` in `CatalogConfig` before-validator so both direct and nested construction pick it up without a default UUID factory
- Endpoint graph_key prefixes validated on edge items at model boundary (source/target types)
- `EnforcedBy` requires non-empty `evidence` string in `CatalogEdgeItem`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Forward-ref NameError on CatalogConfig return annotation**
- **Found during:** Task 1 GREEN
- **Issue:** `CatalogConfig` return type on `model_validator` raised `NameError` without postponed annotations
- **Fix:** Added `from __future__ import annotations` to `schema.py`
- **Files modified:** `mcp_server/src/config/schema.py`
- **Committed in:** `c67e69d`

## Threat Flags

None — no new network endpoints, auth paths, or runtime I/O surfaces. Models and pure helpers only.

## Known Stubs

None.

## TDD Gate Compliance

- RED commits present: `bd6290b`, `ec2d9d6`
- GREEN commits present after RED: `c67e69d`, `fb427db`
- Verification: `pytest tests/test_catalog_models.py tests/test_catalog_identity.py` → 55 passed

## Self-Check: PASSED

- FOUND: `mcp_server/src/config/schema.py` (CatalogConfig)
- FOUND: `mcp_server/src/models/catalog_common.py`
- FOUND: `mcp_server/src/models/catalog_entities.py`
- FOUND: `mcp_server/src/models/catalog_edges.py`
- FOUND: `mcp_server/src/models/catalog_responses.py`
- FOUND: `mcp_server/src/services/catalog_identity.py`
- FOUND: `mcp_server/tests/test_catalog_models.py`
- FOUND: `mcp_server/tests/test_catalog_identity.py`
- FOUND commits: `bd6290b`, `c67e69d`, `ec2d9d6`, `fb427db`
