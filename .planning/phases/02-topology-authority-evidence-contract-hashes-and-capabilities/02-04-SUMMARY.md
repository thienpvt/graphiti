---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
plan: 04
subsystem: catalog-capabilities
tags: [capabilities, catalog-v2, fingerprint, mcp, read-only, CAPA]

requires:
  - phase: 02-01
    provides: endpoint_map_export / EDGE_ENDPOINT_MAP authority
  - phase: 02-02
    provides: explicit evidence schema (features.explicit_evidence_links=true)
  - phase: 02-03
    provides: CANONICALIZATION_VERSION / CATALOG_SCHEMA_VERSION in catalog_identity
provides:
  - namespace_fingerprint one-way domain-separated helper
  - build_catalog_capabilities pure mutation-free builder
  - CatalogCapabilitiesResponse additive response model
  - get_catalog_capabilities MCP tool outside write gate
affects:
  - 02-05 edge-probe resolution / CAPA discharge
  - Phase 3A prepare discovery surface
  - Operators/agents discovering catalog-v2 contracts

tech-stack:
  added: []
  patterns:
    - Pure capabilities builder from single authorities (topology/identity/common/config)
    - One-way namespace fingerprint; never raw namespace or secrets
    - Read-only MCP tool without catalog_upsert.enabled / get_client mutation path

key-files:
  created:
    - mcp_server/src/services/catalog_capabilities.py
    - mcp_server/tests/test_catalog_capabilities.py
  modified:
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/src/graphiti_mcp_server.py

key-decisions:
  - "Fingerprint material b'graphiti.catalog.nsfp.v1|'+namespace.bytes → SHA-256 hex[:16]"
  - "Versions imported from catalog_identity / IDENTITY_SCHEMA_VERSION only — no local version literals"
  - "MCP wrapper never calls get_client; connectivity stays unknown without safe probe"
  - "get_catalog_capabilities not added to CATALOG_TOOL_NAMES (no request body / SAFE-08 rewrite N/A)"
  - "features: prepare_commit/manifests/manifest_verification false; explicit_evidence_links true"
  - "Hard prepared/active-plan/TTL ceilings reported as explicit zero placeholders until later phases"

patterns-established:
  - "Capabilities pure builder accepts client only for future non-mutating probes; Phase 2 never invokes driver"
  - "Registries/endpoint_map/limits generated from ENTITY_TYPE_PREFIXES, CATALOG_EDGE_TYPES, endpoint_map_export, HARD_MAX_*, CatalogConfig"

requirements-completed: [CAPA-01, CAPA-02, CAPA-03, CAPA-04, CAPA-05, CAPA-06, CAPA-07, CAPA-08, CAPA-09]

coverage:
  - id: D1
    description: get_catalog_capabilities works with writes disabled / missing namespace
    requirement: CAPA-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_get_catalog_capabilities_works_when_writes_disabled
        status: pass
    human_judgment: false
  - id: D2
    description: package_version/backend/connectivity without mutation
    requirement: CAPA-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_disabled_writes_missing_namespace
        status: pass
    human_judgment: false
  - id: D3
    description: gates + namespace bool + one-way fingerprint; secrets redacted
    requirement: CAPA-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_redacts_namespace_and_secrets
        status: pass
    human_judgment: false
  - id: D4
    description: identity/canonicalization/catalog schema versions from authorities
    requirement: CAPA-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_versions_from_identity_constants
        status: pass
    human_judgment: false
  - id: D5
    description: entity/edge registries and endpoint_map from single authorities
    requirement: CAPA-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_endpoint_map_from_topology_export
        status: pass
    human_judgment: false
  - id: D6
    description: configured + hard limits including zero prepared/TTL placeholders
    requirement: CAPA-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_limits_configured_and_hard
        status: pass
    human_judgment: false
  - id: D7
    description: embeddings/index readiness unknown without mutation
    requirement: CAPA-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_unknown_readiness_without_client_mutation
        status: pass
    human_judgment: false
  - id: D8
    description: phase-truthful feature flags
    requirement: CAPA-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_features_phase_truthful
        status: pass
    human_judgment: false
  - id: D9
    description: get_status status+message keys preserved
    requirement: CAPA-09
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_get_status_preserves_status_and_message_keys
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-18
status: complete
---

# Phase 02 Plan 04: Read-Only Catalog Capabilities Summary

**Mutation-free `get_catalog_capabilities` with pure builder, one-way namespace fingerprint, registry/limit export, and preserved `get_status` contract.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-18T03:17:21Z
- **Completed:** 2026-07-18T03:30:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `namespace_fingerprint` domain-separated SHA-256 prefix; `None` when namespace missing
- `build_catalog_capabilities` pure view over topology/identity/common/config authorities
- `CatalogCapabilitiesResponse` additive model; redacts raw namespace/secrets
- MCP `get_catalog_capabilities` registered outside write gate; no schema/index/store writes
- CAPA-01..09 unit coverage green; phase-2 regression subset 418 passed

## Task Commits

1. **Task 1: namespace fingerprint + pure capabilities builder + response model** - `ffd8654` (feat)
2. **Task 2: MCP get_catalog_capabilities registration + get_status compatibility** - `7d5cd51` (feat)
3. **Lint fix (unused import)** - `300ecfe` (style)

## Files Created/Modified

- `mcp_server/src/services/catalog_capabilities.py` - pure fingerprint + builder
- `mcp_server/src/models/catalog_responses.py` - `CatalogCapabilitiesResponse`
- `mcp_server/src/graphiti_mcp_server.py` - MCP tool registration
- `mcp_server/tests/test_catalog_capabilities.py` - CAPA unit + registration tests

## Decisions Made

- Fingerprint algorithm: `sha256(b'graphiti.catalog.nsfp.v1|' + ns.bytes).hexdigest()[:16]`
- Import `CANONICALIZATION_VERSION` / `CATALOG_SCHEMA_VERSION` from `catalog_identity` only
- MCP path uses config only (`client=None`); never `get_client` / `execute_write` / `build_indices`
- Left out of `CATALOG_TOOL_NAMES` (no request ValidationError surface)
- Feature flags truthful to Phase 2: prepare/manifests/manifest_verification false; explicit evidence true
- Prepared-plan hard ceilings reported as documented zeros until later phases

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unused import after Task 2 test additions**
- **Found during:** post-task ruff check
- **Issue:** `typing.Any` unused in `test_catalog_capabilities.py`
- **Fix:** Removed import
- **Files modified:** `mcp_server/tests/test_catalog_capabilities.py`
- **Commit:** `300ecfe`

### Known follow-ups (out of plan ownership)

- `test_catalog_service.py::test_mcp_registers_exactly_seven_catalog_tools_and_preserves_legacy_tools` still asserts total tool count `== 21`. Plan forbade editing that file (owned by 02-01/02-03). Additive tool raises live total to 22; covered by this plan's `test_mcp_registers_capabilities_plus_legacy_and_catalog_tools` (`len(names) >= 22`). Update service registration count in a later owned fix if needed.

## Verification

- `pytest test_catalog_capabilities.py` — 18 passed
- Phase-2 subset (capabilities/topology/evidence/hash/identity) — 418 passed
- Ruff check/format — clean on plan files
- Scoped Pyright — 0 errors on capabilities + responses

## TDD Gate Compliance

1. RED: capabilities tests failed with missing module
2. GREEN: builder/response + MCP registration commits after tests
3. style cleanup commit for unused import

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_capabilities.py`
- FOUND: `mcp_server/src/models/catalog_responses.py` (`CatalogCapabilitiesResponse`)
- FOUND: `mcp_server/src/graphiti_mcp_server.py` (`get_catalog_capabilities`)
- FOUND: `mcp_server/tests/test_catalog_capabilities.py`
- FOUND: commits `ffd8654`, `7d5cd51`, `300ecfe`
