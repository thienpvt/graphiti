---
phase: 03A-immutable-prepare-commit-control-plane
plan: 05
subsystem: catalog-control-plane
tags: [commit, discard, plan-token, cas, mcp-tools, capabilities, tdd]

requires:
  - phase: 03A-03
    provides: plan store load/CAS, token_digest locator, PREPARED/COMMITTING/DISCARDED states
  - phase: 03A-04
    provides: prepare_catalog_batch full frozen artifact + one-time plan_token receipt
provides:
  - commit_prepared_catalog_batch token-only claim/load seam (stop at COMMITTING; zero domain I/O)
  - discard_prepared_catalog_batch token-only PREPARED→DISCARDED (idempotent; no domain deletes)
  - plan_token_matches (hmac.compare_digest) post-load authorization on commit and discard
  - three additive MCP tools + CATALOG_TOOL_NAMES=11
  - real HARD plan ceilings in capabilities; features.prepare_commit still false
affects:
  - 03A-06-wire-tools
  - phase-3B-domain-co-commit

tech-stack:
  added: []
  patterns:
    - digest locator then plan_token_matches authorization (PLAN-07)
    - full reassemble/verify/binding/expected_hash before CAS
    - commit stops at COMMITTING; domain co-commit deferred to 3B
    - capabilities expose real HARD limits while prepare_commit flag stays false until 03A-06

key-files:
  created:
    - mcp_server/tests/test_graphiti_mcp_server.py
  modified:
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/services/catalog_capabilities.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_prepare_service.py
    - mcp_server/tests/test_catalog_capabilities.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Commit path: digest load → plan_token_matches → state/expiry → reassemble → binding/expected_hash → CAS PREPARED→COMMITTING (re-entry allowed)"
  - "Discard maps discarded→prepared_plan_not_found and committed→prepared_plan_already_consumed; no domain deletes"
  - "HARD plan limits re-exported from catalog_common (16MiB / 32 active / 86400s TTL); HARD_MAX_PAGE_SIZE stays 0"
  - "features.prepare_commit remains false through Wave 4 (D-29); flip owned by 03A-06 after live proof"
  - "CATALOG_TOOL_NAMES expanded 8→11 (prior catalog + prepare/commit/discard)"

patterns-established:
  - "Token is locator via plan_token_digest only; authorize with plan_token_matches after load"
  - "Thin MCP wrappers delegate to CatalogService; CatalogSafeFastMCP covers new tool names"
  - "Capability hard ceilings live in catalog_common; capabilities module re-exports for CAPA surface"

requirements-completed: [PLAN-10, PLAN-11, PLAN-12, PLAN-17, PLAN-18, PLAN-19, PLAN-20, PLAN-08]

coverage:
  - id: D1
    description: Token-only commit claim/load to COMMITTING with zero domain/embedder/LLM/queue/HTTP
    requirement: PLAN-10
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py#commit/discard suite
        status: pass
    human_judgment: false
  - id: D2
    description: expected_request_sha256 compare-only; mismatch fails before CAS
    requirement: PLAN-11
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py
        status: pass
    human_judgment: false
  - id: D3
    description: Token binding + plan_token_matches post-load; load miss prepared_plan_not_found
    requirement: PLAN-17
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py
        status: pass
    human_judgment: false
  - id: D4
    description: Terminal states never revive; discarded/committed error codes
    requirement: PLAN-18
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py
        status: pass
    human_judgment: false
  - id: D5
    description: discard PREPARED→DISCARDED idempotent; no domain deletes
    requirement: PLAN-19
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py
        status: pass
    human_judgment: false
  - id: D6
    description: Three additive MCP tools registered; CATALOG_TOOL_NAMES=11
    requirement: PLAN-20
    verification:
      - kind: unit
        ref: mcp_server/tests/test_graphiti_mcp_server.py#test_prepare_commit_discard_tools_registered
        status: pass
    human_judgment: false
  - id: D7
    description: Real HARD plan limits; prepare_commit false; pagination hard=0
    requirement: PLAN-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py#test_build_capabilities_plan_limits_nonzero_prepare_commit_false
        status: pass
    human_judgment: false

duration: ~45min
completed: 2026-07-18
status: complete
---

# Phase 03A Plan 05: Commit/Discard + MCP + Limits Summary

**Token-only commit CAS to COMMITTING and discard to DISCARDED, three additive MCP tools, real HARD plan ceilings — prepare_commit flag still false until 03A-06.**

## Performance

- **Duration:** ~45 min (includes post-compaction Task 2 finish)
- **Started:** 2026-07-18 (worktree executor)
- **Completed:** 2026-07-18
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- `commit_prepared_catalog_batch`: digest load → `plan_token_matches` → reassemble/verify/binding/expected_hash → CAS PREPARED→COMMITTING; zero domain/embedder/LLM/queue/HTTP
- `discard_prepared_catalog_batch`: token-only PREPARED→DISCARDED; terminal mapping; no domain deletes
- MCP: `prepare_catalog_batch`, `commit_prepared_catalog_batch`, `discard_prepared_catalog_batch` registered; `CATALOG_TOOL_NAMES` = 11
- Capabilities: real HARD payload/active/TTL from `catalog_common`; `features.prepare_commit=false`; page size hard=0
- 50 prepare/capabilities/MCP + 20 catalog tool tests green; ruff/pyright clean

## Task Commits

1. **Task 1: token-only commit/discard claim-load seam** - `f2838c4` (feat)
2. **Task 2: MCP tools + real HARD plan limits** - `782b793` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `mcp_server/src/services/catalog_service.py` - `commit_prepared_catalog_batch`, `discard_prepared_catalog_batch`, store error mapping, binding verify
- `mcp_server/src/services/catalog_capabilities.py` - re-export real HARD plan ceilings; keep prepare_commit false
- `mcp_server/src/graphiti_mcp_server.py` - three thin MCP tools; CATALOG_TOOL_NAMES=11
- `mcp_server/tests/test_catalog_prepare_service.py` - 17 commit/discard matrix tests (+ prepare suite)
- `mcp_server/tests/test_catalog_capabilities.py` - nonzero HARD limits; prepare_commit false
- `mcp_server/tests/test_catalog_service.py` - 11 catalog tools / frozen models / side-effect spies
- `mcp_server/tests/test_graphiti_mcp_server.py` - registration + CATALOG_TOOL_NAMES

## Decisions Made

- Digest is locator only; authorize with `plan_token_matches` / `hmac.compare_digest` after load
- Commit stops at COMMITTING — no Phase 3B domain co-commit body
- expected_request_sha256 is compare-only; omission and correct value both load same frozen plan
- HARD plan limits live in `catalog_common`; capabilities re-exports; page size remains explicit 0
- `features.prepare_commit` stays false until 03A-06 live-proof gate (D-29)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pyright `_make_root` annotated dict but returned tuple**
- **Found during:** Task 1 typecheck
- **Issue:** helper return type mismatched usage in prepare service tests
- **Fix:** annotate `tuple[dict, list, str]`; tighten Optional `.get` / await_args checks
- **Files modified:** `mcp_server/tests/test_catalog_prepare_service.py`
- **Commit:** `f2838c4`

**2. [Rule 3 - Blocking] Ruff isort on capabilities re-exports**
- **Found during:** Task 2 lint
- **Issue:** split `catalog_common` imports needed isort grouping after HARD re-exports
- **Fix:** `ruff check --fix` on `catalog_capabilities.py`
- **Files modified:** `mcp_server/src/services/catalog_capabilities.py`
- **Commit:** `782b793`

## TDD Gate Compliance

- Task 1 commit/discard tests authored with implementation (matrix covers token match, CAS, terminals, external-call spies)
- Task 2 capabilities + MCP registration tests green with implementation
- Separate RED-only commits not retained post-compaction; GREEN feat commits present: `f2838c4`, `782b793`

## Known Stubs

- Commit stops at COMMITTING by design — Phase 3B owns domain co-commit body
- `features.prepare_commit=false` intentional until 03A-06

## Threat Flags

None new. Token still never logged/stored raw; commit path still forbids client replacement payload and external I/O.

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_service.py`
- FOUND: `mcp_server/src/services/catalog_capabilities.py`
- FOUND: `mcp_server/src/graphiti_mcp_server.py`
- FOUND: `mcp_server/tests/test_catalog_prepare_service.py`
- FOUND: `mcp_server/tests/test_catalog_capabilities.py`
- FOUND: `mcp_server/tests/test_graphiti_mcp_server.py`
- FOUND: `mcp_server/tests/test_catalog_service.py`
- FOUND: `f2838c4`
- FOUND: `782b793`
