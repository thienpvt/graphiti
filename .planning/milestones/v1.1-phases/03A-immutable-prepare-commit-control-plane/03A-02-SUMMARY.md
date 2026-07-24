---
phase: 03A-immutable-prepare-commit-control-plane
plan: 02
subsystem: catalog-control-plane
tags: [prepared-artifact, plan-token, sha256, base64-chunk, hmac, pure-helpers, tdd]

requires:
  - phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
    provides: catalog_identity canonical_sha256 and catalog_prepared_plan_uuid
provides:
  - serialize_prepared_artifact prepared-artifact-v1 UTF-8 JSON bytes
  - artifact_sha256 external to hashed body
  - chunk_artifact_bytes / reassemble_artifact_bytes fail-closed
  - catalog_prepared_plan_chunk_uuid
  - mint_plan_token / plan_token_digest / plan_token_matches
  - plan_binding_fields pure construct
affects:
  - 03A store plan root/chunk persistence
  - 03A prepare/commit service

tech-stack:
  added: []
  patterns:
    - external artifact digest (no self-hash in body)
    - domain-separated token digest with hmac.compare_digest
    - base64 chunk records with per-chunk sha256 + offset/length

key-files:
  created:
    - mcp_server/src/services/catalog_prepared_artifact.py
    - mcp_server/tests/test_catalog_prepared_artifact.py
    - mcp_server/tests/test_catalog_token.py
  modified:
    - mcp_server/src/services/catalog_identity.py

key-decisions:
  - "Token helpers owned by catalog_identity; artifact module never accepts raw tokens"
  - "Empty payload yields one empty chunk (documented)"
  - "Chunk hard ceilings: 262144 bytes, 128 chunks; default 131072"

patterns-established:
  - "Artifact serialize uses same JSON rules as canonical_sha256"
  - "Reassembly sorts by chunk_index and verifies digests/lengths fail-closed"
  - "plan_token_digest domain b'graphiti.catalog.plan_token.v1|'"

requirements-completed: [PLAN-04, PLAN-05, PLAN-06, PLAN-07, PLAN-17]

coverage:
  - id: D1
    description: prepared-artifact-v1 serialize includes membership+embeddings (not hashes-only)
    requirement: PLAN-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepared_artifact.py#test_serialize_includes_membership_and_embeddings_not_hashes_only
        status: pass
    human_judgment: false
  - id: D2
    description: external artifact_sha256 and byte-identical multi-chunk reassembly
    requirement: PLAN-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepared_artifact.py#test_roundtrip_multi_chunk_byte_identical
        status: pass
    human_judgment: false
  - id: D3
    description: corruption/reorder gaps/max chunks fail closed
    requirement: PLAN-05
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepared_artifact.py#test_reassemble_missing_chunk_fails_closed
        status: pass
    human_judgment: false
  - id: D4
    description: secrets mint + domain digest + timing-safe compare
    requirement: PLAN-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_token.py#test_plan_token_matches_true_and_false
        status: pass
    human_judgment: false
  - id: D5
    description: raw token never in artifact serialization; binding fields pure
    requirement: PLAN-17
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_token.py#test_raw_token_never_in_serialized_artifact
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-07-18
status: complete
---

# Phase 03A Plan 02: Pure Artifact And Token Helpers Summary

**prepared-artifact-v1 serialize/chunk/reassemble with external SHA-256 plus secrets-minted plan tokens digested under domain prefix with hmac.compare_digest**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-18T05:57:31Z
- **Completed:** 2026-07-18T06:00:14Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Pure `catalog_prepared_artifact.py`: serialize (canonical JSON), external `artifact_sha256`, base64 chunk/reassemble with hard ceilings
- `catalog_prepared_plan_chunk_uuid` + token mint/digest/match + `plan_binding_fields` on `catalog_identity.py`
- 32 new pure unit tests green; identity regression 28 green (60 total)

## Task Commits

Each task was committed atomically:

1. **Task 1: Prepared artifact serialize/chunk/reassemble** - `de72b86` (feat)
2. **Task 2: Opaque token mint digest timing-safe compare** - `e74fa5e` (test)

**Plan metadata:** (pending docs commit)

_Note: Token helper implementation shipped in Task 1 feat commit; Task 2 added the pure token suite proving PLAN-06/07/17. See Deviations._

## Files Created/Modified

- `mcp_server/src/services/catalog_prepared_artifact.py` - serialize/chunk/reassemble pure authority
- `mcp_server/src/services/catalog_identity.py` - chunk UUID, TOKEN_DIGEST_DOMAIN, mint/digest/match, binding fields
- `mcp_server/tests/test_catalog_prepared_artifact.py` - PLAN-04/05 pure suite
- `mcp_server/tests/test_catalog_token.py` - PLAN-06/07/17 pure suite

## Decisions Made

- Token ownership in `catalog_identity` (domain digests live with identity helpers); artifact module documents no-token policy
- Empty bytes → single empty chunk
- `plan_token_matches` lowercases stored digest for hex case tolerance while still using `hmac.compare_digest`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Token helpers implemented during Task 1**
- **Found during:** Task 1 (GREEN for artifact)
- **Issue:** Plan Task 2 owned mint/digest/match, but `catalog_identity` edits for chunk UUID already open; token helpers are pure and needed for complete module ownership docstring
- **Fix:** Implemented `mint_plan_token` / `plan_token_digest` / `plan_token_matches` / `plan_binding_fields` / `TOKEN_DIGEST_DOMAIN` in Task 1 commit; Task 2 RED→GREEN is test-only against live helpers
- **Files modified:** `mcp_server/src/services/catalog_identity.py`
- **Verification:** `test_catalog_token.py` 11 passed; combined 32 passed
- **Committed in:** `de72b86` (Task 1) + `e74fa5e` (Task 2 tests)

---

**Total deviations:** 1 auto-fixed (Rule 2)
**Impact on plan:** No scope creep; same deliverables; commit boundary slightly earlier for token source

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Store/service plans can import pure artifact + token authority without Neo4j
- Live restart/chunk persistence remains plan 03+/06

## TDD Gate Compliance

1. Task 1: tests + implementation committed together as feat (import failure was RED at collection before module existed; GREEN after)
2. Task 2: test commit after helpers present — behavioral RED was collection/import-level for token suite only after helpers already shipped in Task 1

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_prepared_artifact.py`
- FOUND: `mcp_server/src/services/catalog_identity.py` (chunk uuid + token helpers)
- FOUND: `mcp_server/tests/test_catalog_prepared_artifact.py`
- FOUND: `mcp_server/tests/test_catalog_token.py`
- FOUND: commit `de72b86`
- FOUND: commit `e74fa5e`
- Tests: 32/32 plan suite pass; 60 with identity regression

---
*Phase: 03A-immutable-prepare-commit-control-plane*
*Completed: 2026-07-18*
