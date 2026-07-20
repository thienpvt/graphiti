---
phase: 04-manifest-backed-verification-and-read-only-diagnostics
plan: 02
subsystem: catalog-gates
tags: [tdd, gates, reads_enabled, capabilities, status, phase4]

requires:
  - phase: 04-01
    provides: Wave 0 RED gate suite + fail-closed phase4 gate runner
provides:
  - CatalogConfig.reads_enabled default True and max_page_size default 100 (le 500)
  - HARD_MAX_PAGE_SIZE=500 with truthful catalog_reads_enabled
  - _read_gate split from write enabled
  - CatalogIngestStatusResponse.found with missing path found=False
  - GREEN GATE-01..06 for existing resolve/status tools
affects:
  - 04-03
  - 04-04
  - 04-05
  - 04-06

tech-stack:
  added: []
  patterns:
    - "Split read/write feature gates (reads_enabled vs enabled)"
    - "Status absence via found=False without validation_error"
    - "Capabilities page authority configured 100 / hard 500"

key-files:
  created: []
  modified:
    - mcp_server/src/config/schema.py
    - mcp_server/src/services/catalog_capabilities.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/tests/test_catalog_gates.py
    - mcp_server/tests/test_catalog_capabilities.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "reads_enabled defaults True; write enabled stays False"
  - "max_page_size default 100 hard 500 (D-04 A1)"
  - "features.manifest_verification remains False until 04-06"
  - "Missing status: found=False error_code=None (GATE-05)"

patterns-established:
  - "_read_gate uses getattr(config, 'reads_enabled', True)"
  - "Status gate failures still set found=False with structured error_code"

requirements-completed:
  - GATE-01
  - GATE-02
  - GATE-03
  - GATE-04
  - GATE-05
  - GATE-06

coverage:
  - id: D1
    description: CatalogConfig.reads_enabled True and enabled False by default; max_page_size 100
    requirement: GATE-01
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_gates.py::test_reads_enabled_default_true_writes_false"
        status: pass
    human_judgment: false
  - id: D2
    description: Capabilities callable with both gates false; hard page 500; manifest_verification false
    requirement: GATE-02
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_gates.py::test_capabilities_callable_both_gates_false"
        status: pass
    human_judgment: false
  - id: D3
    description: resolve/status work with writes off reads on
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_gates.py::test_read_tools_when_writes_disabled"
        status: pass
    human_judgment: false
  - id: D4
    description: Read paths spy zero ensure_*_schema / write / embed / LLM / queue
    requirement: GATE-04
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_gates.py::test_reads_no_schema_write_embed"
        status: pass
    human_judgment: false
  - id: D5
    description: Missing status found=False and error_code None
    requirement: GATE-05
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_gates.py::test_missing_status_found_false"
        status: pass
    human_judgment: false
  - id: D6
    description: group_id isolation, empty rejection, concurrent same-group reads
    requirement: GATE-06
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_gates.py"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-19
status: complete
---

# Phase 4 Plan 02: Split Read/Write Gates Summary

**Independent `reads_enabled` + page ceilings + `found=false` status; GATE-01..06 green on existing tools; `manifest_verification` still false**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-18T18:28:32Z
- **Completed:** 2026-07-19T00:40:00Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- `CatalogConfig.reads_enabled=True` default; write `enabled` remains False; `max_page_size=100` (1..500)
- Capabilities: `HARD_MAX_PAGE_SIZE=500`; `catalog_reads_enabled` follows config; `features.manifest_verification` still False
- `_read_gate` checks `reads_enabled` only (no write coupling)
- Missing ingest status: `found=False`, `error_code=None` (not `validation_error`)
- Full `test_catalog_gates.py` GREEN (10); residual Wave 0 RED suites for plans 03–05 still fail closed (42)

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Config + capabilities page size / read flag | `0ebe238` | schema, capabilities, capabilities tests, gate defaults |
| 2 | Split `_read_gate` + GATE-05 found=false | `8dd68cb` | catalog_service, catalog_responses, gates GREEN, service test fixups |

## Files Created/Modified

| File | Purpose |
|------|---------|
| `mcp_server/src/config/schema.py` | `reads_enabled`, `max_page_size` |
| `mcp_server/src/services/catalog_capabilities.py` | HARD 500; truthful reads flag |
| `mcp_server/src/services/catalog_service.py` | `_read_gate` split; status found |
| `mcp_server/src/models/catalog_responses.py` | `CatalogIngestStatusResponse.found` |
| `mcp_server/tests/test_catalog_gates.py` | GATE-01..06 GREEN |
| `mcp_server/tests/test_catalog_capabilities.py` | page/read flag tests |
| `mcp_server/tests/test_catalog_service.py` | read-disable + missing-status expectations |

## Decisions Made

- Page defaults: configured 100 / hard 500 (D-04 A1)
- Namespace still required only when write `enabled`; identity-bearing reads fail via `_read_gate` on bad/missing namespace
- No new MCP tools; no verification flip

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing service tests assumed write-coupled read gate**
- **Found during:** Task 2
- **Issue:** `test_resolve/verify/status_feature_disabled_*` used `_disabled_config()` (writes off, reads default on) and expected `feature_disabled`
- **Fix:** construct `reads_enabled=False` for those cases; update missing-status assert to `found=False` / `error_code=None`
- **Files modified:** `mcp_server/tests/test_catalog_service.py`
- **Commit:** `8dd68cb`

## TDD Gate Compliance

- RED scaffolds from 04-01 Task 1 already present
- GREEN: Task 1 `0ebe238` (config/capabilities), Task 2 `8dd68cb` (gate/status)
- Residual RED for 04-03..05 intentionally left failing

## Known Stubs

| File | Pattern | Reason |
|------|---------|--------|
| `test_catalog_manifest_read.py` et al. | `pytest.fail('04 not implemented: ...')` | Plans 03–05 product GREEN |
| `features.manifest_verification` | `False` | Flip only in 04-06 after proofs |

## Threat Flags

None new beyond plan threat model (T-04-CAP/GATE/READ/ISO/INFO/BOUND mitigated by this plan's tests).

## Verification

```text
# Task 1
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_gates.py \
  -k "reads_enabled or max_page or capabilities" -q
# 23 passed

# Task 2
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_gates.py -q
# 10 passed

# Residual RED (plans 03–05) still fail closed
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_manifest_read.py \
  mcp_server/tests/test_catalog_verify_manifest.py \
  mcp_server/tests/test_catalog_resolve_edges.py \
  mcp_server/tests/test_catalog_evidence_read.py -q --tb=no
# 42 failed (expected)

# Ruff
uv run --project mcp_server ruff check ...  # All checks passed
```

## Next

- 04-03: manifest read GREEN
- 04-04: verify expected authority + edge resolve
- 04-05: evidence read
- 04-06: registration + `manifest_verification` flip after proofs

## Self-Check: PASSED

- FOUND: `mcp_server/src/config/schema.py` (`reads_enabled`, `max_page_size`)
- FOUND: `mcp_server/src/services/catalog_capabilities.py` (`HARD_MAX_PAGE_SIZE=500`)
- FOUND: `mcp_server/src/services/catalog_service.py` (`reads_enabled` gate, `found=False`)
- FOUND: `mcp_server/src/models/catalog_responses.py` (`found` field)
- FOUND: `mcp_server/tests/test_catalog_gates.py` (10 green)
- FOUND: commit `0ebe238`
- FOUND: commit `8dd68cb`
