---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
plan: 03
subsystem: catalog-hash
tags: [hash, catalog-v2, canonicalization, evidence_links, dry-run, request_sha256]

requires:
  - phase: 02-02
    provides: NestedProvenancePayload evidence_links + pure evidence_canonical_payload/coalesce
  - phase: 02-01
    provides: topology/system_key identity shell
provides:
  - CANONICALIZATION_VERSION / CATALOG_SCHEMA_VERSION constants
  - Pure batch_request_canonical_payload + batch_request_sha256 (HASH-02 full domain + system_key)
  - Required lowercase 64-hex catalog_sha256 on UpsertCatalogBatchRequest
  - CatalogService delegates to pure recipe; no dual hash path
  - CatalogBatchWriteResponse echo of identity/canonicalization/request_sha256/catalog_sha256
  - Batch gate/counters on len(evidence_links); batch write resolves targets from links
affects:
  - 02-04 capabilities / control-plane read surface
  - 02-05 edge-probe resolution
  - Phase 3A prepare/store idempotence

tech-stack:
  added: []
  patterns:
    - Single pure hash authority in catalog_identity; service static methods only delegate
    - Evidence coalesce only for byte-identical links before hash/sort by evidence_link_key
    - Response hash echo on every upsert_catalog_batch path including dry-run and safe failures

key-files:
  created:
    - mcp_server/tests/test_catalog_hash.py
  modified:
    - mcp_server/src/services/catalog_identity.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/models/catalog_batch.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/tests/test_catalog_service.py
    - mcp_server/tests/test_catalog_models.py
    - mcp_server/tests/test_catalog_evidence.py

key-decisions:
  - "One CANONICALIZATION_VERSION='catalog-canonical-v1'; service never reimplements recipe"
  - "catalog_sha256 required on all batch requests including dry-run; separate validators from optional request_sha256"
  - "HASH-02 includes system_key (A2); excludes dry_run, caller request_sha256, timestamps, retries, plan tokens"
  - "Batch provenance counters/write path use evidence_links; standalone upsert_provenance remains Cartesian (A4)"
  - "Hash/version echo on dry-run, content_hash_mismatch, gate failures, and success"

patterns-established:
  - "Pure recipe owns sort/coalesce; CatalogService.batch_request_sha256 is a thin delegate"
  - "CatalogBatchWriteResponse carries authoritative server hashes even when writes are zero"

requirements-completed: [HASH-01, HASH-02, HASH-03, HASH-04, HASH-05, HASH-06, HASH-07, TEST-04]

coverage:
  - id: D1
    description: Required lowercase 64-hex catalog_sha256 including dry-run
    requirement: HASH-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_hash.py#test_catalog_sha256_required_and_lowercase_hex
        status: pass
    human_judgment: false
  - id: D2
    description: Full-domain pure recipe with system_key + versions + sorted collections
    requirement: HASH-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_hash.py#test_recipe_includes_versions_system_key_and_collections
        status: pass
    human_judgment: false
  - id: D3
    description: Excluded transport fields do not change digest
    requirement: HASH-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_hash.py#test_excluded_fields_do_not_change_digest
        status: pass
    human_judgment: false
  - id: D4
    description: Mutation/reorder/multiplicity/coalesce coverage
    requirement: HASH-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_hash.py#test_mutate_included_fields_changes_digest
        status: pass
    human_judgment: false
  - id: D5
    description: Dry-run and mismatch echo authoritative hash fields with zero write
    requirement: HASH-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_hash.py#test_dry_run_echoes_authoritative_hash_fields_zero_write
        status: pass
    human_judgment: false
  - id: D6
    description: Caller request_sha256 audit-only mismatch
    requirement: HASH-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_hash.py#test_caller_request_hash_mismatch_echoes_server_hash
        status: pass
    human_judgment: false
  - id: D7
    description: Service static methods delegate to pure recipe only
    requirement: HASH-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_hash.py#test_service_static_delegates_to_pure_recipe
        status: pass
    human_judgment: false
  - id: D8
    description: Batch gate counts evidence_links not Cartesian product
    requirement: TEST-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_hash.py#test_batch_gate_counts_evidence_links_not_cartesian
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-07-18
status: complete
---

# Phase 02 Plan 03: Authoritative Hash Contract Summary

**Versioned pure batch hash recipe with required catalog_sha256, service delegation, evidence_links counters, and full response hash echo (incl. dry-run).**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-18T continuation session
- **Completed:** 2026-07-18
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Pure `batch_request_canonical_payload` / `batch_request_sha256` in `catalog_identity.py` with `CANONICALIZATION_VERSION` / `CATALOG_SCHEMA_VERSION`
- Required lowercase 64-hex `catalog_sha256` on `UpsertCatalogBatchRequest`
- `CatalogService` delegates hash; batch path uses `evidence_links` for gate limits and target resolve; legacy `upsert_provenance` Cartesian preserved
- `CatalogBatchWriteResponse` echoes identity/canonicalization/server `request_sha256`/`catalog_sha256` on dry-run, mismatch, gate, and success
- Focused suite green: 523 tests (hash/service/models/evidence/identity)

## Task Commits

1. **Task 1: versioned pure batch hash recipe + required catalog_sha256** - `4cb23af` (feat)
2. **Task 2: service pure hash path + response echo + evidence_links counters** - `eb40c64` (feat)

**Plan metadata:** (this SUMMARY commit)

## Files Created/Modified

- `mcp_server/src/services/catalog_identity.py` - pure recipe + version constants
- `mcp_server/src/services/catalog_service.py` - delegate hash, evidence_links gate/write, hash echo
- `mcp_server/src/models/catalog_batch.py` - required `catalog_sha256`
- `mcp_server/src/models/catalog_responses.py` - batch response hash/version fields
- `mcp_server/tests/test_catalog_hash.py` - HASH-01..07 / TEST-04 suite
- `mcp_server/tests/test_catalog_service.py` - fixtures + evidence_links migration
- `mcp_server/tests/test_catalog_models.py` - required hash fixtures
- `mcp_server/tests/test_catalog_evidence.py` - `_batch_shell` catalog_sha256 default

## Decisions Made

- Single pure hash authority; service static wrappers only call pure functions
- Coalesce only byte-identical evidence links before hash; sort by `evidence_link_key`
- Echo hashes even when no write occurs (dry-run / content_hash_mismatch / gate)
- Do not reintroduce NestedProvenance Cartesian fields; leave standalone provenance Cartesian

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Post-02-02 seam: service still used entity_targets/edge_targets on batch path**
- **Found during:** Task 2
- **Issue:** NestedProvenancePayload dropped Cartesian arrays; batch service still accessed them (14 baseline failures)
- **Fix:** Resolve targets from `evidence_links` per-source; gate uses `len(evidence_links)`; migrate service fixtures
- **Files modified:** `catalog_service.py`, `test_catalog_service.py`
- **Commit:** `eb40c64`

**2. [Rule 2 - Missing critical] Required catalog_sha256 broke fixtures across models/evidence/service**
- **Found during:** Task 2 verification
- **Issue:** Existing batch payloads omitted new required field
- **Fix:** Inject into `_batch_shell` / `_batch_request` / parametrize payloads; preserve intentional missing-hash negative test
- **Files modified:** test_catalog_models.py, test_catalog_evidence.py, test_catalog_service.py
- **Commit:** `eb40c64`

## TDD Gate Compliance

- RED: `test_catalog_hash.py` mutation/exclusion/coalesce/echo cases landed with Task 1 recipe (`4cb23af`)
- GREEN: service delegation + response echo + evidence_links counters (`eb40c64`)
- No separate refactor commit (format-only churn folded into Task 2)

## Known Stubs

None.

## Threat Flags

None new. No new network endpoints, auth paths, or schema trust-boundary beyond existing catalog batch write surface.

## Verification

```text
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_hash.py \
  mcp_server/tests/test_catalog_service.py \
  mcp_server/tests/test_catalog_models.py \
  mcp_server/tests/test_catalog_evidence.py \
  mcp_server/tests/test_catalog_identity.py -q
# 523 passed
uv run --project mcp_server pyright \
  mcp_server/src/services/catalog_service.py \
  mcp_server/src/services/catalog_identity.py \
  mcp_server/src/models/catalog_batch.py \
  mcp_server/src/models/catalog_responses.py
# 0 errors
```

## Self-Check: PASSED

- `mcp_server/src/services/catalog_identity.py` FOUND
- `mcp_server/src/services/catalog_service.py` FOUND
- `mcp_server/src/models/catalog_batch.py` FOUND
- `mcp_server/src/models/catalog_responses.py` FOUND
- `mcp_server/tests/test_catalog_hash.py` FOUND
- commit `4cb23af` FOUND
- commit `eb40c64` FOUND
- STATE.md / ROADMAP.md intentionally untouched (executor instruction)
