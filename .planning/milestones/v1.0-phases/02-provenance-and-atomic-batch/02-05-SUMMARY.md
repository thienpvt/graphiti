---
phase: 02-provenance-and-atomic-batch
plan: 05
subsystem: testing
tags: [neo4j, atomic-batch, provenance, search, communities, integration]

requires:
  - phase: 02-provenance-and-atomic-batch
    provides: atomic batch service, provenance, terminal status
provides:
  - Synthetic sanitized ACCEPT_TAB live fixture
  - Required Neo4j readiness and live atomic-batch coverage
  - Restart-safe status, retry/conflict/rollback, search, isolation, and explicit community verification
  - RELATES_TO.episodes update healing without provenance loss
affects:
  - 02-06 operator documentation and final verification

tech-stack:
  added: []
  patterns:
    - Hard-fail Neo4j readiness under CATALOG_INT_REQUIRED=1
    - Exact elementId teardown for only test-created objects
    - Explicit community build remains separate from deterministic catalog upserts

key-files:
  created:
    - mcp_server/tests/fixtures/accept_tab_sanitized.json
  modified:
    - mcp_server/tests/test_catalog_neo4j_int.py
    - mcp_server/tests/test_catalog_store_unit.py
    - mcp_server/src/services/catalog_store.py

key-decisions:
  - "The ACCEPT_TAB fixture is synthetic and sanitized; no live or untracked catalog payload is copied"
  - "Legacy null edge episodes heal to [] on content update; existing provenance episode UUIDs remain unchanged"
  - "Community verification invokes maintenance explicitly with a deterministic test LLM; catalog upsert paths remain LLM-free and never invoke communities"

requirements-completed: [BATC-11, BATC-12]

duration: 45min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 05: Live Neo4j Integration Summary

**Atomic catalog batches, installed-schema provenance, restart-safe status, search interop, isolation, and explicit community compatibility are verified against local Neo4j using only `oracle-catalog-tool-test`.**

## Accomplishments

- Added a synthetic sanitized ACCEPT_TAB table/column/FK/source fixture.
- Verified dry-run, commit, identical retry, conflicting retry, concurrent retry, missing endpoint, real transaction rollback, separate failed status, and status read after service reinitialization.
- Verified `Episodic` source, deterministic `MENTIONS`, `RELATES_TO.episodes`, batch-created node/fact search, and non-Entity `CatalogIngestBatch` exclusion.
- Verified catalog batch uses no LLM or queue and never invokes communities implicitly.
- Ran an explicit test-only community build over batch entities without schema errors.
- Restricted teardown to exact newly-created element IDs; asserted all other groups and `oracle-catalog-v2` unchanged.
- Fixed edge updates to heal legacy null `episodes` while preserving non-empty provenance arrays.

## Task Commits

1. **RED live atomic batch coverage** — `dcdada6`
2. **GREEN edge provenance/null healing** — `eda9b41`
3. **Complete search/community/isolation coverage** — `e73f2c9`

## Verification

- Local container: `graphiti-catalog-neo4j-test`, Bolt `localhost:17687`, ready.
- `CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -q --timeout=120`: **34 passed**.
- Focused Phase 2 live selection: **12 passed, 21 deselected** before final community addition; final full live suite supersedes it.
- `uv run pytest tests/test_catalog_store_unit.py tests/test_catalog_service.py -q`: **153 passed**.
- Scoped Ruff check: **passed**.
- Scoped Ruff format check: **3 files formatted**.
- Scoped Pyright: **0 errors, 0 warnings**.

## Deviations from Plan

### Auto-fixed

- Live search exposed a legacy `RELATES_TO.episodes = null` hydration edge case. Store update Cypher now uses `coalesce(e.episodes, [])`, preserving existing provenance while healing null values.
- Two executor responses failed at the transport layer. Committed work was recovered and completed in the original isolated worktree; no implementation loss.

## Safety

- No deployment, Kubernetes action, full ingest, graph clear, or existing-data deletion.
- No write to `oracle-catalog-v2`.
- No live/untracked payload copied.
- Exact synthetic-object teardown only.

## Self-Check: PASSED

- Fixture present and synthetic.
- Required live suite green.
- Unit regressions green.
- Ruff/Pyright green.
- Worktree clean except pre-existing `.planning/config.json` dirt.
