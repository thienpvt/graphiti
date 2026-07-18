---
phase: 04-manifest-backed-verification-and-read-only-diagnostics
plan: 04
subsystem: catalog-verify
tags: [tdd, veri-01, veri-02, veri-03, veri-04, veri-05, veri-06, evid-13, test-08, iden-08, manifest, read-only, phase4]

requires:
  - phase: 04-03
    provides: _load_committed_manifest_body + durable membership reassembly
provides:
  - rewired verify_catalog_batch with durable-manifest expected authority
  - distinct missing vs extras diagnostics for entities/edges/evidence
  - match_evidence_links_exact (group_id + uuid) for EVID-13
  - edge verify RETURN content_sha256 for hash consistency
  - additive VerifyEvidenceSection + extras/manifest_sha256 fields
  - GREEN test_catalog_verify_manifest (VERI-01..06, EVID-13, TEST-08)
affects:
  - 04-05
  - 04-06

tech-stack:
  added: []
  patterns:
    - "Batch expected membership/counts from committed durable manifest only"
    - "Live MATCH rows are observations; never section.expected = len(rows) on batch path"
    - "Evidence identity = group_id + evidence-link uuid; no link_key fallback when uuid present"
    - "Committed invalid/missing manifest → manifest_mismatch; missing status → found=false"
    - "Keys-only authority remains request keys; batch+keys keeps keys diagnostics without inflating batch expected"

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/tests/test_catalog_verify_manifest.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Manifest body is sole batch expected authority; live rows never invent membership"
  - "Q3: committed without valid manifest → CatalogErrorCode.manifest_mismatch; absent status → found=false"
  - "Q1 EVID-13: exact evidence MATCH by group_id+uuid; compare link_key/content_sha256 after load"
  - "Q2: edge verify Cypher RETURNs content_sha256; expected hash from manifest edge member"
  - "require_endpoints fail-closed only for manifest-backed verify or when expected endpoints set"
  - "manifest_verification capability remains false until plan 06"

patterns-established:
  - "_manifest_*_expected builders from durable body → Verify*Ref lists"
  - "_diagnose_entity_matches / _diagnose_edge_matches separate anomaly lists"
  - "_verify_entities/_verify_edges take report_extras; never expected=len(rows)"
  - "match_evidence_links_exact via _read_many only"

requirements-completed:
  - VERI-01
  - VERI-02
  - VERI-03
  - VERI-04
  - VERI-05
  - VERI-06
  - EVID-13
  - TEST-08
  - IDEN-08

coverage:
  - id: D1
    description: Batch-only verify uses durable manifest as sole expected membership authority
    requirement: VERI-01
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py::test_batch_only_uses_manifest"
        status: pass
    human_judgment: false
  - id: D2
    description: Expected counts come from manifest metadata never len(live rows)
    requirement: VERI-02
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py::test_expected_not_live_count"
        status: pass
    human_judgment: false
  - id: D3
    description: Missing members and extras are distinct diagnostics when both true
    requirement: VERI-03
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py::test_missing_and_extra"
        status: pass
    human_judgment: false
  - id: D4
    description: Type/UUID/endpoint/embedding/hash consistency checks always for required members
    requirement: VERI-04
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py::test_consistency_checks"
        status: pass
    human_judgment: false
  - id: D5
    description: Committed batch without valid durable manifest fails closed as manifest_mismatch
    requirement: VERI-05
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py::test_missing_manifest_code"
        status: pass
    human_judgment: false
  - id: D6
    description: Explicit keys-only path never uses manifest as authority
    requirement: VERI-06
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py::test_explicit_keys_only"
        status: pass
    human_judgment: false
  - id: D7
    description: Exact evidence-link MATCH by group_id+uuid with link_key/hash compare
    requirement: EVID-13
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py::test_exact_evidence"
        status: pass
    human_judgment: false
  - id: D8
    description: Shared unchanged members remain expected; twins/endpoint mismatch without repair
    requirement: TEST-08
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py"
        status: pass
    human_judgment: false
  - id: D9
    description: Entity-identifying verify surfaces use complete system-scoped graph keys
    requirement: IDEN-08
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_verify_manifest.py"
        status: pass
    human_judgment: false

duration: 90min
completed: 2026-07-19
status: complete
---

# Phase 04 Plan 04: Manifest-Backed Verify Rewire Summary

**Batch-scoped verify now treats committed durable manifests as sole expected membership/count authority, with distinct missing/extras, exact evidence identity (group_id+uuid), and preserved keys-only mode.**

## Performance

- **Duration:** ~90 min
- **Started:** 2026-07-18T17:00:00Z
- **Completed:** 2026-07-18T19:05:00Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Rewired `verify_catalog_batch` so `batch_id` loads `_load_committed_manifest_body` and builds expected entity/edge/evidence from the durable body only
- Live MATCH results are observations only — never `section.expected = len(rows)` on the batch path
- Distinct `missing` vs `extras` (and top-level aggregates) for entities, edges, and evidence
- Store `match_evidence_links_exact` (UNWIND uuids, MATCH CatalogEvidenceLink by uuid+group_id, `_read_many` only)
- Edge verify Cypher RETURNs `e.content_sha256`; expected hash from manifest edge member
- Q3: committed + invalid/missing manifest → `manifest_mismatch`; missing status → `found=false`
- Keys-only and batch+keys preserved; additive response fields only (`extras`, `evidence`, `manifest_sha256`)
- 16 GREEN tests in `test_catalog_verify_manifest.py`; 21 existing verify service tests updated/stubbed

## Task Commits

Each task was committed atomically:

1. **Task 1+2: Manifest expected authority rewire + consistency/evidence** - `e8efd2d` (feat)

**Plan metadata:** (pending docs commit)

_Note: TDD RED suite was already present from plan scaffolding; GREEN implementation landed as a single feat commit covering both tasks after full suite green._

## Files Created/Modified

- `mcp_server/src/services/catalog_service.py` - rewired `verify_catalog_batch`, diagnose helpers, evidence verify
- `mcp_server/src/services/catalog_store.py` - edge `content_sha256` RETURN; `match_evidence_links_exact`
- `mcp_server/src/models/catalog_responses.py` - `extras`, `content_hash_mismatch`, `VerifyEvidenceSection`, `manifest_sha256`
- `mcp_server/tests/test_catalog_verify_manifest.py` - 16 GREEN VERI/EVID/TEST cases
- `mcp_server/tests/test_catalog_service.py` - `_stub_batch_manifest_for_verify`; keys-only batch_id=None where needed

## Decisions Made

- Manifest body is sole batch expected authority; live rows never invent membership
- Q3: committed without valid manifest → `CatalogErrorCode.manifest_mismatch`; absent status → `found=false`
- Q1 EVID-13: exact evidence MATCH by `group_id+uuid`; compare `link_key`/`content_sha256` after load
- Q2: edge verify Cypher RETURNs `content_sha256`; expected hash from manifest edge member
- `require_endpoints` fail-closed only for manifest-backed verify or when expected endpoints set (keys-only null endpoints without expected UUIDs do not force endpoint_mismatch)
- `manifest_verification` capability remains false until plan 06

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Keys-only null endpoint check too aggressive**
- **Found during:** Task 2 (GREEN suite / existing `test_verify_edge_type_mismatch_never_becomes_endpoint_mismatch`)
- **Issue:** Always treating null endpoints as endpoint_mismatch broke keys-only type-mismatch-only fixtures
- **Fix:** Gate null-endpoint fail-closed behind `require_endpoints` (batch/manifest path) or when expected source/target UUIDs are set
- **Files modified:** `mcp_server/src/services/catalog_service.py`
- **Verification:** full verify suite green
- **Committed in:** `e8efd2d`

**2. [Rule 2 - Missing critical functionality] Existing service verify tests needed status+manifest stubs**
- **Found during:** Task 1 GREEN after rewire
- **Issue:** Batch-scoped tests still used `batch_id` without committed status/manifest, so rewire returned found=false or mismatch
- **Fix:** Added `_stub_batch_manifest_for_verify`; set `batch_id=None` for pure keys-only cases
- **Files modified:** `mcp_server/tests/test_catalog_service.py`
- **Verification:** 21 verify-related service tests pass
- **Committed in:** `e8efd2d`

**3. [Rule 1 - Bug] Ruff SIM102/SIM114 nested-if in diagnose helpers**
- **Found during:** post-GREEN lint
- **Issue:** Nested `if` for anomaly appends triggered SIM102/SIM114
- **Fix:** Combined conditions; wrong/generic embedding path uses single branch with candidate_rows
- **Files modified:** `mcp_server/src/services/catalog_service.py`
- **Verification:** ruff clean
- **Committed in:** `e8efd2d`

## Verification Results

- `uv run pytest tests/test_catalog_verify_manifest.py tests/test_catalog_service.py -k verify` → **37 passed**
- `uv run ruff check` on modified files → **All checks passed**
- `uv run pyright` on modified sources → **0 errors**

## Known Stubs

None that block plan goals. `manifest_verification` remains false until plan 06 (intentional).

## Threat Flags

None new beyond plan threat model (read-only verify path; group-scoped MATCH; no writes/schema/embed).

## Self-Check: PASSED

- `mcp_server/src/services/catalog_service.py` FOUND
- `mcp_server/src/services/catalog_store.py` FOUND
- `mcp_server/src/models/catalog_responses.py` FOUND
- `mcp_server/tests/test_catalog_verify_manifest.py` FOUND
- `mcp_server/tests/test_catalog_service.py` FOUND
- commit `e8efd2d` FOUND
