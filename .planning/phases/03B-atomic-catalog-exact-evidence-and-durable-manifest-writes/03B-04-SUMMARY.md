---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 04
subsystem: catalog-write
tags: [neo4j, atomic-tx, catalog, evidence, manifest, tdd, prepared-commit]

requires:
  - phase: 03B-02
    provides: prepare/claim control-plane, frozen prepared artifact
  - phase: 03B-03
    provides: evidence/manifest store APIs, terminal_commit_agrees, schema ensure
provides:
  - CatalogWriteProjection + _write_catalog_batch_atomic single success-tx writer
  - upsert_catalog_batch non-dry-run co-writes domain+evidence+manifest+terminals
  - commit_prepared_catalog_batch success path returns COMMITTED with manifest_sha256/batch_uuid
  - Fault-injection suite proving genuine rollback at every persistence boundary
affects:
  - 03B-05 recovery matrix / terminal agreement deep cases
  - Phase 4 verify against committed batch + manifest

tech-stack:
  added: []
  patterns:
    - shared CatalogWriteProjection built before success tx
    - D-04 write order in one Neo4j transaction
    - D-27 failed status only post-rollback separate tx
    - IDE-safe dynamic importlib/getattr in atomic writer tests

key-files:
  created:
    - mcp_server/tests/test_catalog_atomic_writer.py
  modified:
    - mcp_server/src/services/catalog_service.py
    - mcp_server/tests/test_catalog_service.py
    - mcp_server/tests/test_catalog_prepare_service.py

key-decisions:
  - "Single success tx via existing driver.transaction(); claim remains separate PREPARED→COMMITTING"
  - "Prepared projection rebuilds only from frozen artifact membership/embeddings/request_canonical (D-06)"
  - "terminal_commit_agrees short-circuit hook only; deep recovery matrix deferred to 03B-05"
  - "Test schema doubles include evidence/manifest SHOW CONSTRAINTS rows so _ensure_schema fails closed only on real miss"

patterns-established:
  - "Pattern: _write_catalog_batch_atomic(tx, projection) is sole domain+evidence+manifest+terminal writer for upsert and prepared commit"
  - "Pattern: Fake store pending/commit/rollback models genuine Neo4j abort for fault inject"

requirements-completed: [PLAN-13, PLAN-14, MANI-06, EVID-07, EVID-09, EVID-10]

coverage:
  - id: D1
    description: Shared _write_catalog_batch_atomic co-writes entities, edges, sources+links, evidence, manifest, batch committed, optional plan COMMITTED
    requirement: PLAN-13
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_atomic_writer.py::test_shared_writer_used_by_upsert_and_commit_paths
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_atomic_writer.py::test_plan13_write_order_stub
        status: pass
    human_judgment: false
  - id: D2
    description: Fault at each store boundary rolls back; no partial success markers committed
    requirement: PLAN-14
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_atomic_writer.py::test_fault_inject_after_entities_rolls_back
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_atomic_writer.py::test_fault_inject_after_manifest_rolls_back
        status: pass
    human_judgment: false
  - id: D3
    description: Manifest write inside same success tx as domain and plan terminal
    requirement: MANI-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_atomic_writer.py::test_plan13_write_order_stub
        status: pass
    human_judgment: false
  - id: D4
    description: Prepared commit returns COMMITTED with manifest_sha256/batch_uuid; zero external I/O after claim
    requirement: PLAN-13
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py::test_commit_happy_path_prepared_to_committing_zero_domain_external
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_prepare_service.py::test_commit_never_calls_external_clients
        status: pass
    human_judgment: false
  - id: D5
    description: dry_run upsert remains zero-write; no Neo4j success transaction
    requirement: PLAN-14
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_atomic_writer.py::test_dry_run_zero_write
        status: pass
    human_judgment: false

duration: 90min
completed: 2026-07-18
status: complete
---

# Phase 03B Plan 04: Shared Atomic Catalog Writer Summary

**One Neo4j success transaction co-commits domain+evidence+manifest+terminals for both direct upsert and prepared commit via `_write_catalog_batch_atomic`.**

## Performance

- **Duration:** ~90 min
- **Started:** 2026-07-18T (executor session)
- **Completed:** 2026-07-18
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Extracted `CatalogWriteProjection` + `_write_catalog_batch_atomic` with D-04 order (lock plan → claim → terminal-agree short-circuit → entities → edges → sources+links → evidence → manifest → batch committed → plan COMMITTED).
- Wired `upsert_catalog_batch` non-dry-run and `commit_prepared_catalog_batch` post-claim success path through the shared writer; dry_run stays zero-write.
- GREEN fault-injection suite with genuine pending/commit/rollback fakes at entity/edge/source/evidence/manifest/status boundaries.
- Prepared commit unit path returns `state=COMMITTED` with additive `manifest_sha256` / `batch_uuid` / committed_* counts; no embedder/LLM/queue after claim.

## Task Commits

1. **Task 1: Shared atomic writer + fault injection GREEN** - `6893580` (feat)
2. **Task 2: Wire upsert + prepared commit success path** - `36e9f66` (feat)

**Plan metadata:**  (docs: complete plan)

_Note: TDD RED suite lived in the same task-1 commit with GREEN product extraction (single worktree wave)._

## Files Created/Modified

- `mcp_server/src/services/catalog_service.py` - projection builders, shared writer, upsert/commit wiring, evidence/manifest schema ensure
- `mcp_server/tests/test_catalog_atomic_writer.py` - shared writer + fault inject + dry_run + order + terminal short-circuit (importlib/getattr only)
- `mcp_server/tests/test_catalog_service.py` - schema SHOW rows for evidence/manifest; batch/provenance store stubs for co-write
- `mcp_server/tests/test_catalog_prepare_service.py` - commit expects COMMITTED; writer stubs without new product static imports

## Decisions Made

- Hard stop not required: single success tx retained via existing `driver.transaction()`.
- Claim tx remains separate (D-02); success tx re-locks plan and rechecks batch claim.
- Deep recovery matrix left to plan 05 except `terminal_commit_agrees` short-circuit hook.
- Prepare-path `_assert_zero_domain` retained for prepare-only; commit success tests assert domain writer + zero external clients.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Schema fakes lacked evidence/manifest constraints**
- **Found during:** Task 2 regression (`_ensure_schema` → `ensure_evidence_manifest_schema`)
- **Issue:** Existing `_schema_execute_query` SHOW rows covered identity only; real store fails closed when evidence/manifest constraints absent → mass entity/batch/commit failures.
- **Fix:** Extend SHOW rows; stub `ensure_evidence_manifest_schema` / write helpers on batch and provenance fakes; prepare `_wire_commit` dict-pass-through `prepare_*` without new store import.
- **Files modified:** `test_catalog_service.py`, `test_catalog_prepare_service.py`
- **Committed in:** `36e9f66`

**2. [Rule 1 - Bug] Prepare commit tests still expected COMMITTING-only claim end state**
- **Found during:** Task 2
- **Issue:** Plan 04 extends commit past claim into success writer → COMMITTED; unit expectations lagged.
- **Fix:** Assert COMMITTED + claim and terminal CAS pairs; freeze artifact `request_canonical` entities for projection rebuild.
- **Files modified:** `test_catalog_prepare_service.py`
- **Committed in:** `36e9f66`

**3. [Rule 2 - Hygiene] New product local imports + test static imports**
- **Found during:** Coordinator diagnostic pass
- **Issue:** Local `from models...` inside projection builder; atomic tests static imports; prepare temporarily imported `CatalogNeo4jStore`.
- **Fix:** Module-level `SimpleNamespace` + `CatalogEvidenceLink` in service; atomic tests importlib/getattr only; prepare uses dict `_prep` stubs (no new CatalogNeo4jStore import).
- **Files modified:** `catalog_service.py`, `test_catalog_atomic_writer.py`, `test_catalog_prepare_service.py`
- **Committed in:** `6893580`, `36e9f66`

## TDD Gate Compliance

- RED behavior expressed in `test_catalog_atomic_writer.py` fault/order/short-circuit cases.
- GREEN product in `catalog_service.py` shared writer + wiring.
- Git: `6893580` feat (writer+tests), `36e9f66` feat (wiring spies). Separate pure `test(...)` RED commit not present (combined wave) — noted for audit.

## Known Stubs

None that block plan goals. Plan 05 owns deep recovery matrix beyond `terminal_commit_agrees` short-circuit.

## Threat Flags

None beyond plan threat model. No new MCP tools, network endpoints, or client Cypher surfaces.

## IDE / Pyright baseline classification

- **Project-config pyright** (`mcp_server/pyproject.toml`, basic, extraPaths=src): **0 errors** on
  `catalog_service.py`, `test_catalog_atomic_writer.py`, `test_catalog_service.py`,
  `test_catalog_prepare_service.py`.
- **Root/IDE-equivalent pyright** (no project extraPaths): **0 errors** on
  `catalog_service.py` + `test_catalog_atomic_writer.py` after dynamic import hygiene.
- **Newly added product imports (Plan 04 only):**
  - `from types import SimpleNamespace` (module-level) — stdlib, clean.
  - `from models.catalog_evidence import CatalogEvidenceLink` — same package style as existing model imports.
  - `from services.catalog_manifest import ...` — same package style as existing service imports.
- **Not Plan 04 new / do not churn:**
  - `test_catalog_service.py` late-block `from models.catalog_evidence import CatalogEvidenceLink` (~2769) — **pre-existing** at base `f1d0775` (shifted line only).
  - `test_catalog_prepare_service.py` local `from models.catalog_batch import UpsertCatalogBatchRequest` (~456) — **pre-existing**.
  - Root-workspace import noise on pre-existing static product imports in service/tests when opened without `extraPaths` — **baseline**, not introduced by this plan.
- **Avoided:** mass conversion of existing static imports; new prepare wiring uses dict pass-through prepare helpers instead of adding `CatalogNeo4jStore` import.

## Verification evidence

```text
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_atomic_writer.py \
  mcp_server/tests/test_catalog_service.py \
  mcp_server/tests/test_catalog_prepare_service.py -q
# 230 passed

uv run --project mcp_server python -m ruff check \
  mcp_server/src/services/catalog_service.py \
  mcp_server/tests/test_catalog_atomic_writer.py \
  mcp_server/tests/test_catalog_service.py \
  mcp_server/tests/test_catalog_prepare_service.py
# All checks passed

uv run --project mcp_server python -m pyright --project mcp_server \
  mcp_server/src/services/catalog_service.py \
  mcp_server/tests/test_catalog_atomic_writer.py \
  mcp_server/tests/test_catalog_service.py \
  mcp_server/tests/test_catalog_prepare_service.py
# 0 errors

uv run --project mcp_server python -m pyright \
  mcp_server/src/services/catalog_service.py \
  mcp_server/tests/test_catalog_atomic_writer.py
# 0 errors
```

## Self-Check: PASSED

- `mcp_server/src/services/catalog_service.py` FOUND
- `mcp_server/tests/test_catalog_atomic_writer.py` FOUND
- commits `6893580`, `36e9f66` FOUND on `worktree-agent-ae186ef0183760375`
- `_write_catalog_batch_atomic` present in upsert + commit sources (grep/tests)
- STATE.md / ROADMAP.md **not** updated (executor constraint)

## Next phase readiness

- 03B-05: recovery deep matrix, terminal agreement edge cases, multi-reentry paths beyond short-circuit hook.
- No canary / oracle-catalog-v2 / clear_graph / deploy performed.
