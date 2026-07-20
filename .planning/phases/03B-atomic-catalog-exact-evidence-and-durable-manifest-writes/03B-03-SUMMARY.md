---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 03
subsystem: catalog
tags: [tdd, evidence, manifest, neo4j, create-once, fixed-labels, recovery]

requires:
  - phase: 03B-01
    provides: Wave 0 RED evidence-store scaffold + identity/coalesce helpers
  - phase: 03B-02
    provides: Pure catalog-manifest-v1 body/hash/chunk authority
  - phase: 03A-immutable-prepare-commit-control-plane
    provides: prepared-plan schema/create-once, property-touch lock patterns, CatalogStoreError
provides:
  - CatalogEvidenceLink / CatalogBatchManifest(+Chunk) uniqueness constraints (CREATE-only)
  - write_evidence_link(s) create-once with source/target resolve and provenance_link_conflict
  - write_manifest_root_and_chunks create-once ordered chunks with hash-binding conflict
  - lock_prepared_plan_for_commit + terminal_commit_agrees + read_manifest_root_for_recovery
affects:
  - 03B-04 (atomic writer co-commit of evidence + manifest)
  - 03B-05 (recovery/concurrency using lock + terminal agreement)
  - 03B-06 (live proof + capabilities flip)

tech-stack:
  added: []
  patterns:
    - Fixed control-plane labels only (never Entity/Episodic for evidence/manifest)
    - Create-token MERGE for evidence create-once; CREATE-once for manifest root/chunks
    - Schema ensure outside success transaction with process-local ready flag
    - Property-touch SET uuid=uuid plan lock for commit serialization
    - Terminal agreement requires plan COMMITTED + batch committed + manifest hashes

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/tests/test_catalog_evidence_store.py

key-decisions:
  - "Evidence uses create-token MERGE; divergent content/link/source/target -> provenance_link_conflict"
  - "Manifest uses MATCH-then-CREATE-once; same hashes idempotent; divergent -> batch_conflict"
  - "Target resolve in same tx: Episodic source + Entity/RELATES_TO edge by target_kind"
  - "terminal_commit_agrees is pure read agreement predicate (bool); no mutation"
  - "Tests load product via importlib/getattr (Wave 0 IDE-safe); production keeps static imports"

patterns-established:
  - "evidence_manifest_schema_constraint_statements + ensure_evidence_manifest_schema mirror plan schema"
  - "prepare_*_params allowlist + forbidden embedding/raw-token keys"
  - "Chunks always written in ascending chunk_index order after root create"

requirements-completed:
  - EVID-07
  - EVID-08
  - EVID-09
  - EVID-10
  - EVID-11
  - MANI-01
  - MANI-04
  - MANI-06
  - MANI-07
  - TEST-07

coverage:
  - id: D1
    description: Evidence/manifest uniqueness constraints are fixed-label CREATE IF NOT EXISTS only
    requirement: EVID-10
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py::test_evidence_schema_constraint_statements_fixed_labels"
        status: pass
    human_judgment: false
  - id: D2
    description: Create-once evidence write is idempotent for same content_sha256
    requirement: EVID-07
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py::test_evidence_create_once_same_content"
        status: pass
    human_judgment: false
  - id: D3
    description: Divergent content_sha256 raises provenance_link_conflict
    requirement: EVID-08
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py::test_evidence_divergent_content_raises_provenance_link_conflict"
        status: pass
    human_judgment: false
  - id: D4
    description: Missing source/target fails closed; invalid target_kind rejected
    requirement: EVID-09
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py::test_evidence_missing_target_fails"
        status: pass
    human_judgment: false
  - id: D5
    description: CatalogEvidenceLink never carries Entity/Episodic labels or embeddings
    requirement: EVID-10
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py::test_evidence_no_entity_label"
        status: pass
    human_judgment: false
  - id: D6
    description: Empty evidence list is a valid no-op; single link writes fixed allowlist props
    requirement: EVID-11
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py::test_evidence_empty_list_ok"
        status: pass
    human_judgment: false
  - id: D7
    description: Manifest root+chunks create-once; divergent hash conflicts; same hash idempotent; ordered chunks
    requirement: MANI-04
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py::test_write_manifest_root_and_chunks_create_once"
        status: pass
    human_judgment: false
  - id: D8
    description: Property-touch plan lock + terminal commit agreement + recovery manifest root read
    requirement: MANI-06
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py::test_terminal_commit_agrees_true"
        status: pass
    human_judgment: false
  - id: D9
    description: Fake-tx suite only; group oracle-catalog-tool-test; no live Neo4j
    requirement: TEST-07
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_store.py"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-07-18
status: complete
---

# Phase 03B Plan 03: Exact Evidence + Durable Manifest Store Summary

**Neo4j store authorities for create-once CatalogEvidenceLink and CatalogBatchManifest(+Chunk), with plan lock and terminal commit agreement predicates.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-18T10:54:25Z
- **Completed:** 2026-07-18T11:08:19Z
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Added fixed-label evidence/manifest uniqueness constraints and `ensure_evidence_manifest_schema` (CREATE only, process-local ready flag).
- Implemented create-once evidence writes with same-tx Episodic source + Entity/edge target resolve; divergent binding -> `provenance_link_conflict`.
- Implemented durable manifest root+ordered chunks create-once; same hash idempotent; divergent binding -> `batch_conflict`.
- Added `lock_prepared_plan_for_commit`, `terminal_commit_agrees`, and internal `read_manifest_root_for_recovery`.
- Full unit suite green (27 tests); store regressions green; Ruff/Pyright zero on touched files.

## Task Commits

Each task was committed atomically:

1. **Task 1: Exact evidence + durable manifest store suite (RED/GREEN-intent)** - `3db0c8a` (test)
2. **Task 2: Store authorities implementation (GREEN)** - `2c02b08` (feat)
3. **Follow-up: IDE diagnostics / dead allowlist constants** - `7a6dd8d` (fix)

**Plan metadata:** `5a858bd` (docs: complete plan)

_Note: TDD tasks may have multiple commits (test → feat → refactor)_

## Files Created/Modified

- `mcp_server/src/services/catalog_store.py` - Evidence/manifest constraints, schema ensure, write/lock/terminal/recovery APIs
- `mcp_server/tests/test_catalog_evidence_store.py` - Dynamic-import unit suite with fake tx/executor (no live Neo4j)

## Decisions Made

- Evidence write uses create-token MERGE matching domain upsert pattern; control record labels never Entity/Episodic.
- Manifest uses MATCH-existing then CREATE root+chunks (plan-chunk style), not MERGE-on-hash.
- `terminal_commit_agrees` returns bool only; service orchestration remains 03B-04/05.
- Test product symbols loaded via importlib/getattr for IDE-root Pyright; production store keeps static imports per project convention.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Invalid graph_key in coalesce unit fixture**
- **Found during:** Task 1 (test run)
- **Issue:** `CatalogEvidenceEntityTarget(graph_key='tbl.x')` failed Pydantic registry grammar validation.
- **Fix:** Use registry-valid `TABLE::FE::ORCL.HR.EMPLOYEES` (mirrors existing evidence tests).
- **Files modified:** `mcp_server/tests/test_catalog_evidence_store.py`
- **Verification:** full evidence suite 27 passed
- **Committed in:** `3db0c8a` (task 1)

**2. [Rule 2 - Correctness/diagnostics] Dynamic imports + unused fake args**
- **Found during:** Coordinator diagnostic note mid-execution
- **Issue:** Static `from models.*` / `from services.*` unresolved under IDE root; unused `params`/`kwargs` in fake executors.
- **Fix:** Module-level importlib/getattr product load (Wave 0 / Plan 02 pattern); rename unused fake args to `_params`/`_kwargs` (params kept where asserted).
- **Files modified:** `mcp_server/tests/test_catalog_evidence_store.py`
- **Verification:** project-config + root-scoped Pyright 0 errors; Ruff 0
- **Committed in:** `3db0c8a` (task 1)

**3. [Rule 1 - Lint] SIM103 on terminal_commit_agrees artifact compare**
- **Found during:** Task 2 (ruff check)
- **Issue:** Final if/return False/return True pattern.
- **Fix:** Return negated equality directly.
- **Files modified:** `mcp_server/src/services/catalog_store.py`
- **Verification:** ruff check clean; tests still green
- **Committed in:** `2c02b08` (task 2)

**4. [Rule 2 - Diagnostics] Fake kwargs unused + dead plan prop frozensets**
- **Found during:** Coordinator merge pause (IDE diagnostics)
- **Issue:** Pyright flagged unused `_params`/`_kwargs` in test fakes; `_PLAN_ROOT_PROP_KEYS` / `_PLAN_CHUNK_PROP_KEYS` were defined but unused at base and HEAD.
- **Fix:** Consume `params`/`kwargs` via `_ = (...)` in fakes; enforce unknown-key rejection with plan prop allowlists in `prepare_prepared_plan_params` / `prepare_prepared_plan_chunk_params`. Production `models.*` / `services.*` static imports left (project-config + root Pyright 0; baseline convention).
- **Files modified:** `mcp_server/tests/test_catalog_evidence_store.py`, `mcp_server/src/services/catalog_store.py`
- **Verification:** ruff 0; pyright project+root 0; 121 unit tests pass
- **Committed in:** `7a6dd8d`

## TDD Gate Compliance

- RED gate commit present: `3db0c8a` `test(03B-03): ...`
- GREEN gate commit present after RED: `2c02b08` `feat(03B-03): ...`
- REFACTOR: not required (SIM103 fixed inside GREEN commit)

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_store.py` (evidence/manifest methods)
- FOUND: `mcp_server/tests/test_catalog_evidence_store.py`
- FOUND: commit `3db0c8a`
- FOUND: commit `2c02b08`
- FOUND: commit `7a6dd8d`
- Tests: 27 passed; store unit + prepare store regressions 121 passed combined earlier
- Ruff: All checks passed
- Pyright (mcp_server project + root-scoped): 0 errors

## Known Stubs

None.

## Threat Flags

None beyond plan threat model (fixed labels, parameter-bound Cypher, group-scoped MATCH/MERGE, no client-interpolated labels/props).
