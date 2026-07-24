---
phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
plan: 08
subsystem: catalog-ollama-preflight
tags: [ollama, preflight, matrix, e2e, qwen3-embedding, ruff, pyright, tdd]

requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: Ollama readiness/launcher freeze authority (06-07)
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: native Ollama clean-room config + factory contracts (06-06)
provides:
  - sanitized local Ollama preflight receipt (daemon/model/1024 embed, no vector)
  - complete 18-check remediation matrix MATRIX_GREEN
  - required real Ollama E2E proof (qwen3-embedding:0.6b / 1024)
  - pyright monorepo extraPaths for local graphiti_core ollama surface
affects:
  - 06-09 bind/image
  - 06-10 R0-R3 prefreeze
  - 06-11 freeze/canary handoff

tech-stack:
  added: []
  patterns:
    - sanitized preflight stores dimension/bools only (no vector/URL/secrets)
    - clean-room example remains Ollama authority; dirty config-docker-neo4j.yaml deferred unstaged
    - matrix receipt enumerates 18 named checks with counts/command ids
    - E2E uses CATALOG_OLLAMA_REQUIRED=1 exact model/dimensions against host Neo4j test group only

key-files:
  created:
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-PREFLIGHT.json
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-MATRIX-RECEIPT.json
  modified:
    - mcp_server/tests/test_catalog_ollama_cleanroom_config.py
    - mcp_server/tests/test_factories.py
    - mcp_server/pyproject.toml

key-decisions:
  - "Protected config-docker-neo4j.yaml left unstaged (default dims 1536 vs qwen3 max 1024); clean-room example is authority"
  - "Preflight authorized one pull of exact qwen3-embedding:0.6b only; native /api/embed dimensions=1024"
  - "E2E used authorized existing host clean-room Neo4j credentials ephemerally; no credential value or endpoint parameter persisted"
  - "Pyright extraPaths adds monorepo root so local graphiti_core.embedder.ollama resolves over PyPI wheel"

patterns-established:
  - "06-OLLAMA-PREFLIGHT.json + 06-OLLAMA-MATRIX-RECEIPT.json are sole new evidence names for this gap"
  - "Matrix classification MATRIX_GREEN requires 18 named checks, skip_count=0, unexplained_skip_count=0"
  - "isinstance narrow then attribute access for OllamaEmbedder.config under basic pyright"

requirements-completed: [P6-OLL-PREFLIGHT-01, P6-OLL-TDD-01]

coverage:
  - id: D1
    description: Sanitized local Ollama preflight proves daemon, exact model, native 1024 embed, credential_used=false
    requirement: P6-OLL-PREFLIGHT-01
    verification:
      - kind: other
        ref: .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-PREFLIGHT.json
        status: pass
    human_judgment: false
  - id: D2
    description: Clean-room example remains native Ollama qwen3/1024; dirty base config unstaged
    requirement: P6-OLL-SAFE-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_ollama_cleanroom_config.py::test_catalog_local_example_is_native_ollama_qwen3_1024
        status: pass
      - kind: other
        ref: git status --short mcp_server/config/config-docker-neo4j.yaml (unstaged/deferred)
        status: pass
    human_judgment: false
  - id: D3
    description: Complete 18-check remediation matrix green with real required Ollama E2E
    requirement: P6-OLL-TDD-01
    verification:
      - kind: other
        ref: .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-MATRIX-RECEIPT.json
        status: pass
      - kind: e2e
        ref: mcp_server/tests/test_catalog_ollama_e2e.py (CATALOG_OLLAMA_REQUIRED=1 model=qwen3-embedding:0.6b dim=1024)
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-07-23
status: complete
---

# Phase 06 Plan 08: Ollama Preflight and Complete Remediation Matrix Summary

**Sanitized host Ollama preflight (qwen3-embedding:0.6b / 1024) plus 18-check MATRIX_GREEN including required real E2E; dirty base config deferred**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-07-23T10:43:41Z
- **Completed:** 2026-07-23T10:57:44Z
- **Tasks:** 2
- **Files modified:** 5 (3 code/config + 2 receipts; SUMMARY separate)

## Accomplishments

- Local Ollama preflight: daemon reachable; exact model present after one authorized pull; native `/api/embed` 1024 finite vector validated in memory only
- Sanitized `06-OLLAMA-PREFLIGHT.json` committed (no vector, secrets, raw namespace, URL, or credentials)
- Complete 18-check remediation matrix `MATRIX_GREEN` with zero unexplained skips/deselections/warnings
- Required real E2E: 5 passed under `CATALOG_OLLAMA_REQUIRED=1`, `CATALOG_OLLAMA_MODEL=qwen3-embedding:0.6b`, `CATALOG_OLLAMA_DIMENSIONS=1024`
- Ruff check/format and Pyright green on Ollama surface after monorepo `extraPaths` + isinstance narrowing
- Protected `mcp_server/config/config-docker-neo4j.yaml` never staged (dims 1536 deferred)

## Task Commits

1. **Task 1: Config safety + sanitized Ollama preflight** - `2d9d098` (test)
2. **Fix-forward: pyright/ruff Ollama surface** - `4bc3b99` (fix)
3. **Task 2: Complete remediation matrix + required Ollama E2E** - `3de07d2` (test)

**Plan metadata:** (pending final docs commit)

_Note: TDD-style fix-forward between RED matrix and GREEN matrix_

## Files Created/Modified

- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-PREFLIGHT.json` - sanitized preflight receipt
- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-MATRIX-RECEIPT.json` - 18-check matrix receipt
- `mcp_server/tests/test_catalog_ollama_cleanroom_config.py` - ruff format/import + pyright OllamaEmbedder narrowing
- `mcp_server/tests/test_factories.py` - pyright OllamaEmbedder narrowing after isinstance
- `mcp_server/pyproject.toml` - pyright `extraPaths` includes monorepo root

## Decisions Made

- Leave dirty `config-docker-neo4j.yaml` unstaged (cannot path-separate user overlay from default 1536); clean-room example is runtime authority
- Preflight pull only `qwen3-embedding:0.6b`; no other models, no deletes
- E2E used the authorized existing host clean-room Neo4j connection ephemerally; no credential or endpoint parameter persisted
- Temporary matrix runner deleted after receipt write; not committed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pyright EmbedderClient.config attribute access**
- **Found during:** Task 2 (matrix pyright check)
- **Issue:** After `isinstance(client, OllamaEmbedder)`, pyright still typed `client` as `EmbedderClient` without `.config`
- **Fix:** Bind narrowed `ollama = client` after isinstance in factory/cleanroom tests
- **Files modified:** `mcp_server/tests/test_factories.py`, `mcp_server/tests/test_catalog_ollama_cleanroom_config.py`
- **Verification:** pyright 0 errors on Ollama surface
- **Committed in:** `4bc3b99`

**2. [Rule 2 - Missing Critical] Pyright monorepo graphiti_core resolution**
- **Found during:** Task 2
- **Issue:** MCP env/PyPI graphiti-core wheel lacks `embedder.ollama`; pyright `reportMissingImports`
- **Fix:** `extraPaths = ["src", ".."]` in `mcp_server/pyproject.toml`
- **Files modified:** `mcp_server/pyproject.toml`
- **Verification:** pyright resolves local ollama module
- **Committed in:** `4bc3b99`

**3. [Rule 1 - Bug] Ruff import order/format on cleanroom tests**
- **Found during:** Task 2 (ruff check/format)
- **Issue:** isort/format drift in `test_catalog_ollama_cleanroom_config.py`
- **Fix:** `ruff check --fix` + `ruff format`
- **Files modified:** `mcp_server/tests/test_catalog_ollama_cleanroom_config.py`
- **Verification:** ruff check/format --check pass
- **Committed in:** `4bc3b99`

**4. [Rule 3 - Blocking] E2E Neo4j authentication mismatch**
- **Found during:** Task 2 (required E2E)
- **Issue:** Initial local E2E credentials did not match the authorized existing host clean-room Neo4j instance
- **Fix:** Used that instance's authorized credentials ephemerally; persisted neither credentials nor endpoint parameters
- **Files modified:** none permanent (ephemeral runner env only; helper deleted)
- **Verification:** E2E 5 passed
- **Committed in:** N/A (env only); result in `3de07d2` receipt

---

**Total deviations:** 4 auto-fixed (2 bug, 1 missing critical, 1 blocking)
**Impact on plan:** Required for matrix green; no scope creep; no image/canary

## Issues Encountered

- Host Neo4j rate-limited after failed authentication probes; recovered with authorized ephemeral credentials
- PyPI graphiti-core in mcp venv missing ollama module for typecheck — fixed via extraPaths, not package install of unreviewed names

## Auth Gates

None

## Known Stubs

None

## Threat Flags

None beyond plan mitigations (preflight sanitized; single allowlisted pull)

## Matrix Check Counts (truthful)

| # | Check | Status | Counts |
|---|-------|--------|--------|
| 1 | changed_python_compile | pass | files=15 |
| 2 | root_ollama_embedder_tests | pass | 22 passed (1 expected pytest warning) |
| 3 | mcp_factory_tests | pass | 28 passed |
| 4 | cleanroom_config_materializer | pass | 5 passed |
| 5 | catalog_capabilities | pass | 41 passed |
| 6 | final_canary_launcher | pass | 33 passed (1 expected warning) |
| 7 | builder_runner_related | pass | 75 passed (1 expected warning) |
| 8 | schema_bootstrap | pass | 8 passed |
| 9 | phase5_focused_suite | pass | 413 passed |
| 10 | phase6_focused_suite | pass | 187 passed (1 expected warning) |
| 11 | combined_remediation_union | pass | 517 passed (1 expected warning) |
| 12 | golden_contract_hash | pass | 17 passed (intentional -k selection) |
| 13 | exact_22_field_manifest | pass | fields=22 |
| 14 | exact_28_tool_registry | pass | 1 passed (intentional -k selection) |
| 15 | ruff_check | pass | rc=0 |
| 16 | ruff_format_check | pass | rc=0 |
| 17 | pyright_touched_packages | pass | root_rc=0 mcp_rc=0 |
| 18 | required_real_ollama_e2e | pass | 5 passed |

- **skip_count:** 0
- **deselect_count (gate):** 0 (intentional -k on golden/tool_union only; not unexplained)
- **unexplained_skip_count:** 0
- **unexplained_warning_count:** 0 (classified expected pytest warning noise)
- **classification:** MATRIX_GREEN
- **image/runtime/canary:** 0 / 0 / false
- **pull_performed:** true (`qwen3-embedding:0.6b` only)

## User Setup Required

None - local Ollama already used; model pulled during preflight.

## Next Phase Readiness

- Host Ollama + full offline matrix proven for source-bind (06-09)
- No image build or canary IDs from this plan
- Dirty overlay still user-owned; do not stage in 06-09 projection unless path-separated

## Self-Check: PASSED

- FOUND: `06-OLLAMA-PREFLIGHT.json`
- FOUND: `06-OLLAMA-MATRIX-RECEIPT.json`
- FOUND: `06-08-SUMMARY.md`
- FOUND commits: `2d9d098`, `4bc3b99`, `3de07d2`
- Helper `_run_06_08_matrix.py` removed (not committed)
- Protected config unstaged

---
*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Completed: 2026-07-23*
