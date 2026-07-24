---
phase: 05-verification-security-compatibility-and-migration-docs
plan: 03
subsystem: testing
tags: [catalog-v2, canary, offline, prepare-commit, evidence-links, iden-13, docs-06]

requires:
  - phase: 05-01
    provides: phase-5 gate scaffold and offline safety baseline
provides:
  - Hardened offline catalog-v2 canary artifacts under catalog/canary-v2-requests-hardened/
  - Builder mode hardened from sanitized fixture only
  - Runner pure prepare/commit sequence (never live-executed)
  - Offline tests freezing historical digests and rejecting historical authority
affects:
  - 05-04
  - 05-07
  - phase-6 canary regeneration

tech-stack:
  added: []
  patterns:
    - offline_simulation receipts with canary_executed=false
    - historical digests frozen; hardened dir is sole authority
    - prepare_catalog_batch then commit_prepared_catalog_batch pure sequence

key-files:
  created:
    - catalog/canary-v2-requests-hardened/accept-tab.payload.json
    - catalog/canary-v2-requests-hardened/manifest.json
    - catalog/canary-v2-requests-hardened/offline-prepare.receipt.json
    - catalog/canary-v2-requests-hardened/offline-commit.receipt.json
    - catalog/canary-v2-requests-hardened/offline-checkpoint.json
  modified:
    - scripts/build_catalog_canary_requests.py
    - scripts/run_catalog_canary_batch.py
    - mcp_server/tests/test_catalog_canary_scripts.py

key-decisions:
  - "Hardened artifacts use group_id=oracle-catalog-tool-test; oracle-catalog-v2 is future metadata only"
  - "Historical canary-v2-requests/* digests frozen; invalid as hardened authority"
  - "Runner COMMIT_TOOL_SEQUENCE prefers prepare then token-only commit; upsert_catalog_batch prohibited for hardened path"
  - "Cartesian entity_targets/edge_targets converted offline to evidence_links from sanitized fixture"

patterns-established:
  - "build_hardened(fixture, out) emits model-valid prepare-shaped payload + offline receipts/checkpoint"
  - "validate_hardened_artifact / reject_historical_as_hardened pure offline gates"
  - "simulate_prepare_commit_sequence keeps plan_token in-memory only"

requirements-completed: [IDEN-13, DOCS-06]

coverage:
  - id: D1
    description: Offline hardened catalog-v2 payload/manifest/receipts/checkpoint from sanitized fixture
    requirement: IDEN-13
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_hardened_manifest_schema_strict
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_offline_receipt_schema_strict
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_offline_checkpoint_schema_strict
        status: pass
    human_judgment: false
  - id: D2
    description: Historical inventory digests and attempt count preserved; historical not hardened authority
    requirement: IDEN-13
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_historical_inventory_and_digests_preserved
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_historical_bytes_unchanged_and_attempt_count
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_historical_accept_tab_golden_not_hardened_authority
        status: pass
    human_judgment: false
  - id: D3
    description: Pure prepare/commit sequence offline; no canary runner live shell; no external side effects
    requirement: DOCS-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_prepare_catalog_batch_commit_prepared_sequence_preferred
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_offline_canary_no_external_side_effect
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_phase5_gate_never_shells_canary_runner
        status: pass
    human_judgment: false
  - id: D4
    description: No production content/secret leakage in hardened artifacts
    requirement: DOCS-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_canary_scripts.py::test_sanitized_hardened_artifacts_no_production_content
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-07-19
status: complete
---

# Phase 5 Plan 03: Offline Hardened Canary Migration Summary

**Offline-migrated canary builder/runner to catalog-v2 prepare/commit contracts with versioned hardened artifacts; historical goldens frozen and non-authoritative.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-18T00:00:00Z
- **Completed:** 2026-07-19T00:00:00Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Generated `catalog/canary-v2-requests-hardened/` from sanitized FE ACCEPT_* fixture with `identity_schema_version=catalog-v2`, `system_key=FE`, explicit `evidence_links`, and content hashes
- Runner pure path prefers `prepare_catalog_batch` → `commit_prepared_catalog_batch` → post-commit reads; rejects historical Cartesian upsert artifacts as hardened authority
- Frozen historical digests (11 artifacts) and checkpoint `attempts` length=2 unchanged; hardened `canary_attempt_count=0`, `canary_executed=false`
- Full `test_catalog_canary_scripts.py` green (23 offline tests); no runner live execution, no network/DB/MCP

## Task Commits

Each task was committed atomically:

1. **Task 1: Inventory history; build sanitized hardened fixture, manifest, receipts, and checkpoint** - `cb73da8` (feat)
2. **Task 2: Runner pure prepare/commit sequence (never execute live)** - `dcac2b4` (feat)
3. **Follow-up typing guard** - `3917965` (fix)
4. **Project-scoped Pyright hard-gate fix** - `6de5441` (fix)

**Plan metadata:** (docs commits for SUMMARY)

_Note: TDD RED scaffolds from Wave 0 replaced by GREEN offline assertions in Task 1/2 suite rewrite._

## Files Created/Modified

- `scripts/build_catalog_canary_requests.py` - `build_hardened`, evidence_links conversion, offline receipts/checkpoint
- `scripts/run_catalog_canary_batch.py` - `COMMIT_TOOL_SEQUENCE`, `validate_hardened_artifact`, `simulate_prepare_commit_sequence`
- `mcp_server/tests/test_catalog_canary_scripts.py` - offline inventory/history/schema/sequence/leakage suite
- `catalog/canary-v2-requests-hardened/*` - payload, manifest, prepare/commit receipts, offline checkpoint
- `mcp_server/tests/fixtures/accept_tab_sanitized.json` - unchanged synthetic fixture source (Cartesian converted in builder)

## Decisions Made

- Hardened offline group is `oracle-catalog-tool-test`; `oracle-catalog-v2` metadata only (never transported/executed in Phase 5)
- Historical ACCEPT_TAB request SHA `a84e8a7…` and 10/16/1 / 38/85 remain history only
- `upsert_catalog_batch` remains in historical `execute()` path for inventory but is prohibited for hardened sequence
- No new third-party dependencies

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Hardened field-set allows omitted optional model defaults**
- **Found during:** Task 2 smoke (`source_refs` exact-set mismatch)
- **Issue:** Current entity models include optional fields not present in fixture payloads
- **Fix:** `_reject_unknown_model_fields` rejects unknown keys only
- **Files modified:** `scripts/run_catalog_canary_batch.py`
- **Commit:** `dcac2b4`

**2. [Rule 1 - Bug] Provenance optional typing for pyright**
- **Found during:** Task 2 post-check
- **Issue:** `provenance` from `.get` typed optional before Cartesian check
- **Fix:** explicit `isinstance(provenance, dict)` guard
- **Files modified:** `scripts/run_catalog_canary_batch.py`
- **Commit:** `3917965`

**3. [Rule 1 - Bug] Project-scoped Pyright 8 errors on historical Cartesian fields**
- **Found during:** Hard-gate recheck (`pyright --project mcp_server/pyproject.toml`)
- **Issue:** Historical validators accessed removed `entity_targets`/`edge_targets` on `NestedProvenancePayload`; optional `.get` on un-narrowed provenance/attributes
- **Fix:** Narrow provenance dict; inventory Cartesian shape separately; map `evidence_links` for catalog-v2 counts/targets; narrow fact `attributes` dict
- **Files modified:** `scripts/run_catalog_canary_batch.py`
- **Commit:** `6de5441`

## Threat Flags

None new beyond plan mitigations (T-05-CANARY, T-05-HIST, T-05-ISO). Offline pure path only; no live boundary crossed.

## Known Stubs

None that block plan goals. Historical `execute()` still contains live MCP path for future Phase 6; Phase 5 tests never invoke it and gate forbids shelling the runner.

## TDD Gate Compliance

- RED: Wave 0 scaffolds (`pytest.fail('05 not implemented: …')`) pre-existed; replaced by real assertions
- GREEN: `cb73da8` / `dcac2b4` implement builder + runner + green suite
- Full suite: 23 passed

## Verification

```text
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_canary_scripts.py -q --tb=line
# 23 passed

uv run --project mcp_server pyright --project mcp_server/pyproject.toml \
  scripts/build_catalog_canary_requests.py \
  scripts/run_catalog_canary_batch.py \
  mcp_server/tests/test_catalog_canary_scripts.py
# 0 errors

uv run --project mcp_server ruff check \
  scripts/build_catalog_canary_requests.py \
  scripts/run_catalog_canary_batch.py \
  mcp_server/tests/test_catalog_canary_scripts.py
# All checks passed
```

## Self-Check: PASSED

- FOUND: `catalog/canary-v2-requests-hardened/manifest.json`
- FOUND: `catalog/canary-v2-requests-hardened/offline-prepare.receipt.json`
- FOUND: `catalog/canary-v2-requests-hardened/offline-commit.receipt.json`
- FOUND: `catalog/canary-v2-requests-hardened/offline-checkpoint.json`
- FOUND: commits `cb73da8`, `dcac2b4`, `3917965`, `6de5441`
- Historical checkpoint digest `b367e7f395782d13e72671e1b66d36b24432cb2c1b48c7fa45974d232039ace4` unchanged
- canary_attempt_count hardened = 0; historical attempts length = 2
- Project-scoped Pyright: 0 errors
