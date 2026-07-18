---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
plan: 02
subsystem: catalog-models
tags: [evidence, provenance, catalog-v2, pydantic, identity, hash]

requires:
  - phase: 01-strict-contracts-and-catalog-v2-identity
    provides: CatalogStrictModel, identity helpers, provenance/batch shell, SHA256 bounds
provides:
  - CatalogEvidenceLink exclusive one-source/one-target schema
  - Pure evidence_link_key / evidence_canonical_payload / coalesce_byte_identical_evidence_links
  - NestedProvenancePayload non-Cartesian sources + evidence_links for catalog-v2 batch
  - Legacy entity_targets/edge_targets rejection without auto-conversion
affects:
  - 02-03 hash recipe / evidence_links counters
  - 02-05 edge-probe resolution
  - Phase 3B evidence persistence

tech-stack:
  added: []
  patterns:
    - Explicit CatalogEvidenceLink XOR targets over Cartesian product
    - Pure identity helpers free of I/O imports
    - mode=before rejection of legacy Cartesian fields

key-files:
  created:
    - mcp_server/src/models/catalog_evidence.py
    - mcp_server/tests/test_catalog_evidence.py
  modified:
    - mcp_server/src/services/catalog_identity.py
    - mcp_server/src/models/catalog_batch.py
    - mcp_server/tests/test_catalog_models.py

key-decisions:
  - "Flat typed CatalogEvidenceLocator; no open dict locator"
  - "link_key excludes excerpt/content_sha256; payload hash includes excerpt"
  - "NestedProvenancePayload replaced Cartesian arrays with evidence_links; UpsertProvenanceRequest left Cartesian (A4)"
  - "coalesce collapses only equal evidence_canonical_payload; stable sort by evidence_link_key"

patterns-established:
  - "EVID-14: mode=before reject entity_targets/edge_targets on batch provenance with no adapter"
  - "Evidence identity: source_key|target_kind|target_type|target_key|kind|extractor|version|rule|locator"

requirements-completed: [EVID-01, EVID-02, EVID-03, EVID-04, EVID-05, EVID-06, EVID-14]

coverage:
  - id: D1
    description: CatalogEvidenceLink XOR targets, six kinds, bounds, finite confidence
    requirement: EVID-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_evidence.py
        status: pass
    human_judgment: false
  - id: D2
    description: Pure evidence identity/hash helpers + byte-identical coalesce
    requirement: EVID-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_evidence.py
        status: pass
    human_judgment: false
  - id: D3
    description: Batch accepts evidence_links; rejects Cartesian multi-target shape
    requirement: EVID-14
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_evidence.py#test_batch_rejects_cartesian_entity_targets
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-07-18
status: complete
---

# Phase 02 Plan 02: Explicit Evidence Contract Summary

**CatalogEvidenceLink schema + pure identity/hash helpers; catalog-v2 batch rejects Cartesian provenance**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-07-18T02:43:26Z
- **Completed:** 2026-07-18T02:46:26Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Froze `CatalogEvidenceLink` with exclusive entity/edge targets, six allowlisted kinds, locator bounds, finite confidence, optional 64-hex `content_sha256`
- Added pure `evidence_link_key`, `evidence_canonical_payload`, `coalesce_byte_identical_evidence_links` in `catalog_identity`
- Migrated batch `NestedProvenancePayload` to `sources` + `evidence_links`; reject legacy Cartesian fields without conversion
- Left standalone `UpsertProvenanceRequest` Cartesian for Phase 3B (A4)

## Task Commits

1. **Task 1: CatalogEvidenceLink models + pure identity helpers** - `c3f8d6f` (feat)
2. **Task 2: Batch non-Cartesian evidence_links + legacy shape reject** - `f3d395f` (feat)
3. **Follow-up: Pyright cast on evidence `_dump`** - `76fe3c7` (fix, superseded)
4. **Follow-up: isinstance narrow on model_dump** - `a86bcef` (fix)

## Files Created/Modified

- `mcp_server/src/models/catalog_evidence.py` - EVIDENCE_KINDS, locator, targets, CatalogEvidenceLink
- `mcp_server/src/services/catalog_identity.py` - link_key, canonical payload, coalesce; runtime `isinstance(raw, dict)` after model_dump
- `mcp_server/src/models/catalog_batch.py` - non-Cartesian NestedProvenancePayload + system_key on evidence entity targets
- `mcp_server/tests/test_catalog_evidence.py` - EVID-01..06/14 unit coverage
- `mcp_server/tests/test_catalog_models.py` - batch provenance fixtures updated to evidence_links

## Decisions Made

- Link key omits excerpt and client `content_sha256` (transport); content hash includes excerpt bytes as submitted
- Coalesce by payload digest equality only; non-identical multiplicity retained; order-stable via link_key sort
- Smallest batch change: replace nested target arrays with `evidence_links`; sources may be empty when links alone provide work
- Prefer runtime `isinstance` narrowing over `cast` for model_dump return (trust-boundary shape check)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pyright return type on evidence `_dump`**
- **Found during:** post-plan diagnostics on `catalog_identity.py`
- **Issue:** `getattr(..., 'model_dump')` callable return typed `object`, not assignable to `dict[str, Any] | None`; intermediate `cast` left unused-import noise for some checkers
- **Fix:** `raw = dump(mode='json'); if not isinstance(raw, dict): raise TypeError(...); return raw` — no cast
- **Files modified:** `mcp_server/src/services/catalog_identity.py`
- **Verification:** `uv run --project mcp_server pyright -p mcp_server` on identity/evidence/batch → 0 errors; ruff clean; 71 evidence+identity tests pass
- **Committed in:** `a86bcef` (supersedes `76fe3c7` cast approach)

## Threat Flags

None new beyond plan threat model (Cartesian reject, safe errors, bounds).

## TDD Gate Compliance

1. RED: `test_catalog_evidence.py` failed collection (missing module)
2. GREEN: models + helpers landed (`c3f8d6f`), then batch migration (`f3d395f`)
3. Type follow-ups: cast (`76fe3c7`) then isinstance narrow (`a86bcef`)
4. Verify: 71 evidence+identity tests pass; scoped pyright 0 errors; ruff clean on identity module

## Self-Check: PASSED

- FOUND: `mcp_server/src/models/catalog_evidence.py`
- FOUND: `mcp_server/src/services/catalog_identity.py` helpers
- FOUND: `mcp_server/src/models/catalog_batch.py` evidence_links
- FOUND: commits `c3f8d6f`, `f3d395f`, `76fe3c7`, `a86bcef`
- FOUND: `02-02-SUMMARY.md`
- STATE.md / ROADMAP.md not modified (orchestrator-owned)
