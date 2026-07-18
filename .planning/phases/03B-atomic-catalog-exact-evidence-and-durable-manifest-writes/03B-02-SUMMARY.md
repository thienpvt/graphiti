---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 02
subsystem: catalog
tags: [tdd, manifest, catalog-manifest-v1, pure, commit-response, sha256, chunk]

requires:
  - phase: 03B-01
    provides: Wave 0 RED suite scaffold for test_catalog_manifest.py
  - phase: 03A-immutable-prepare-commit-control-plane
    provides: chunk_artifact_bytes framing, prepare/commit response models, identity helpers
provides:
  - Pure catalog-manifest-v1 body build/serialize/hash/chunk
  - catalog_manifest_chunk_uuid identity helper
  - Additive CommitPreparedCatalogBatchResponse committed fields
affects:
  - 03B-03 (evidence/manifest store)
  - 03B-04 (atomic writer co-commit of manifest)
  - 03B-05 (recovery/concurrency)
  - 03B-06 (live proof + capabilities flip)

tech-stack:
  added: []
  patterns:
    - Pure manifest authority before any Neo4j write
    - Reuse Phase 3A chunk_artifact_bytes; no framing fork
    - Additive response fields default-safe for old constructors
    - Membership sorted by key then uuid; never member batch_id

key-files:
  created:
    - mcp_server/src/services/catalog_manifest.py
  modified:
    - mcp_server/src/services/catalog_identity.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/tests/test_catalog_manifest.py

key-decisions:
  - "Manifest body strips embeddings/source_uuid/target_uuid; compact identities + projected_status only"
  - "chunk_manifest_bytes reuses chunk_artifact_bytes; empty body yields single empty chunk"
  - "Commit response uses committed_created/updated/unchanged (not projected_*) to avoid prepare collision"
  - "artifact_sha256 nullable for direct-upsert path (A3)"

patterns-established:
  - "catalog-manifest-v1 version pin + external manifest_sha256"
  - "ManifestChunk material group_id|catalog-v2|ManifestChunk|batch_id|index"
  - "HARD_CHUNK_BYTES guard local to chunk_manifest_bytes so HARD_CHUNK_BYTES stays used"

requirements-completed:
  - MANI-01
  - MANI-02
  - MANI-03
  - MANI-04
  - MANI-07

coverage:
  - id: D1
    description: Pure catalog-manifest-v1 body is byte-deterministic from frozen membership including unchanged
    requirement: MANI-01
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_manifest.py::test_manifest_canonical_bytes_stable"
        status: pass
    human_judgment: false
  - id: D2
    description: Equal-key members stay separate and sort by uuid; empty/single legal; null rejected
    requirement: MANI-01
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_manifest.py::test_manifest_equal_key_sort_stability"
        status: pass
    human_judgment: false
  - id: D3
    description: Builder never uses member batch_id as membership authority
    requirement: MANI-03
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_manifest.py::test_manifest_builder_ignores_batch_id_for_membership"
        status: pass
    human_judgment: false
  - id: D4
    description: Chunk ceilings reuse Phase 3A defaults; hard+1 fails closed; empty single chunk
    requirement: MANI-04
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_manifest.py::test_manifest_chunk_hard_plus_one_fails"
        status: pass
    human_judgment: false
  - id: D5
    description: Body rejects self-hash and non-finite floats; digest external
    requirement: MANI-07
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_manifest.py::test_manifest_no_self_hash_field"
        status: pass
    human_judgment: false
  - id: D6
    description: Additive commit response fields default-safe; no token/payload/membership/embeddings
    requirement: MANI-07
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_manifest.py::test_commit_response_additive_defaults_safe"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-18
status: complete
---

# Phase 03B Plan 02: Pure Manifest + Additive Commit Response Summary

**Pure catalog-manifest-v1 membership authority (sort/hash/chunk) plus additive commit receipt fields without Neo4j writes.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-18T10:29:16Z
- **Completed:** 2026-07-18T10:41:21Z
- **Tasks:** 2/2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- Implemented pure `catalog_manifest.py` with build/serialize/hash/chunk from frozen membership
- Added `catalog_manifest_chunk_uuid` with D-17 material string
- Extended `CommitPreparedCatalogBatchResponse` additively with `batch_uuid`, `manifest_sha256`, `committed_*` counts
- GREEN suite: 15 manifest tests + Phase 3A prepare-models regression (65 total in verify run)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Pure manifest contract tests** - `ca20a5c` (test)
2. **Task 1 GREEN: Pure manifest body/hash/chunk + chunk UUID** - `0830860` (feat)
3. **Task 2: Additive commit response fields** - `6be79b6` (feat)

**Plan metadata:** (this SUMMARY commit)

_Note: TDD RED→GREEN for Task 1; Task 2 model extension with default-safe constructors._

## Files Created/Modified

- `mcp_server/src/services/catalog_manifest.py` — pure catalog-manifest-v1 builder/serializer/hasher/chunker
- `mcp_server/src/services/catalog_identity.py` — `catalog_manifest_chunk_uuid`
- `mcp_server/src/models/catalog_responses.py` — additive commit receipt fields
- `mcp_server/tests/test_catalog_manifest.py` — GREEN pure suite + response defaults

## Decisions Made

- Compact membership rows only: entities/edges/sources keep `projected_status` including `unchanged`; evidence links omit status
- No embeddings, no member `batch_id`, no source/target UUIDs in manifest body
- Reuse `chunk_artifact_bytes` framing; local `chunk_size > HARD_CHUNK_BYTES` guard keeps re-export used
- Response field names `committed_created/updated/unchanged` avoid collision with prepare `projected_*`
- Direct upsert may pass `artifact_sha256=null` (research A3)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Local HARD_CHUNK_BYTES guard in chunk_manifest_bytes**
- **Found during:** Task 1 (ruff F401 on re-exported HARD_CHUNK_BYTES)
- **Issue:** Import-only re-export flagged unused; pure re-export aliases fought isort
- **Fix:** Guard `chunk_size > HARD_CHUNK_BYTES` before delegating to `chunk_artifact_bytes` (same fail-closed contract)
- **Files modified:** `mcp_server/src/services/catalog_manifest.py`
- **Verification:** ruff clean; hard+1 test passes
- **Committed in:** `0830860`

**2. [Rule 2 - Missing critical] Widen runtime-validated param types to object**
- **Found during:** Task 1 (pyright unreachable-code risk on narrow guards)
- **Issue:** `dict[str, Any]` / `bytes` annotations made isinstance guards appear unreachable under strict narrowing
- **Fix:** Annotate trust-boundary params as `object` and validate at runtime (matches prepared-artifact style intent)
- **Files modified:** `mcp_server/src/services/catalog_manifest.py`
- **Verification:** `pyright --project mcp_server/pyproject.toml` 0 errors/warnings
- **Committed in:** `0830860`

---

**Total deviations:** 2 auto-fixed (Rule 2 ×2)
**Impact on plan:** Correctness/tooling only; contracts and bounds preserved. No scope creep.

## Issues Encountered

- Ruff isort repeatedly split multi-name aliased imports; resolved by using public constant names without aliases and using HARD_CHUNK_BYTES in a real guard.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Pure manifest authority ready for store write path (03B-03)
- Commit response fields ready for service wiring (03B-04)
- Later-wave RED scaffolds intentionally still failing (28 cases across evidence/atomic/recovery/concurrency)

## Known Stubs

None in Plan 02 product surface. Later plans still own intentional RED stubs:

| File | Pattern | Reason |
|------|---------|--------|
| `test_catalog_evidence_store.py` | `pytest.fail` | 03B-03 |
| `test_catalog_atomic_writer.py` | `pytest.fail` | 03B-04 |
| `test_catalog_commit_recovery.py` | `pytest.fail` | 03B-05 |
| `test_catalog_concurrency.py` | `pytest.fail` | 03B-05 |
| `test_catalog_commit_neo4j_int.py` | `pytest.fail` after live probe | 03B-06 |

## Threat Flags

None - pure utilities + additive response fields only. No new network endpoints, auth paths, or Neo4j schema.

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_manifest.py`
- FOUND: `mcp_server/src/services/catalog_identity.py` (`catalog_manifest_chunk_uuid`)
- FOUND: `mcp_server/src/models/catalog_responses.py` (additive fields)
- FOUND: `mcp_server/tests/test_catalog_manifest.py`
- FOUND: commit `ca20a5c`
- FOUND: commit `0830860`
- FOUND: commit `6be79b6`
- Verify: manifest suite 15 passed; prepare-models regression included (65 total); ruff/pyright clean on changed files
- Later-wave RED preserved (28 failed intentional)
- No STATE.md / ROADMAP.md modifications (orchestrator-owned)

---
*Phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes*
*Completed: 2026-07-18*
