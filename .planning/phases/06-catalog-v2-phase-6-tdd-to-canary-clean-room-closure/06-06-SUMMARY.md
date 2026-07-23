---
phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
plan: 06
subsystem: catalog-embedder
tags: [ollama, qwen3-embedding, clean-room-config, materializer, tdd, factory]

requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: reviewed OllamaEmbedder + EmbedderFactory case ollama + materializer
provides:
  - native Ollama clean-room example authority (qwen3-embedding:0.6b / 1024)
  - Stage A config/materializer acceptance suite
  - Stage B factory/dimension/native /api/embed contracts
  - prepare/commit zero generative LLM spy under native Ollama
affects:
  - 06-07 capability/launcher
  - 06-08 preflight/matrix
  - 06-09 bind/image
  - 06-10 R0-R3 prefreeze
  - 06-11 freeze/canary handoff

tech-stack:
  added: []
  patterns:
    - TDD RED then GREEN separate commits for Ollama gap plans
    - clean-room example is sole materialize source; namespace token only
    - provider=ollama must yield OllamaEmbedder (never OpenAIEmbedder /v1)

key-files:
  created:
    - mcp_server/tests/test_catalog_ollama_cleanroom_config.py
  modified:
    - mcp_server/config/config-docker-neo4j.catalog-local.example.yaml
    - mcp_server/tests/test_factories.py
    - tests/embedder/test_ollama.py
    - mcp_server/tests/test_catalog_canary_scripts.py

key-decisions:
  - "Reuse existing OllamaEmbedder/factory; no new provider"
  - "api_key omitted from clean-room ollama block (null by schema default)"
  - "Secret-free scan anchors YAML keys so ${VAR:} empty defaults do not false-positive"

patterns-established:
  - "Stage A example asserts ollama/qwen3/1024 + OLLAMA_EMBEDDER_API_URL host.docker.internal"
  - "Stage B proves /api/embed body dimensions=1024 and mismatch fails before write"
  - "prepare embeds via Ollama only; commit is token-only with LLM spy count 0"

requirements-completed: [P6-OLL-AUTH-01, P6-OLL-CONF-01, P6-OLL-EMB-01]

coverage:
  - id: D1
    description: Clean-room example is native Ollama qwen3-embedding:0.6b dimensions 1024
    requirement: P6-OLL-CONF-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_ollama_cleanroom_config.py::test_catalog_local_example_is_native_ollama_qwen3_1024
        status: pass
    human_judgment: false
  - id: D2
    description: Materializer preserves Ollama section except namespace token
    requirement: P6-OLL-CONF-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_ollama_cleanroom_config.py::test_materializer_preserves_ollama_section_except_namespace
        status: pass
    human_judgment: false
  - id: D3
    description: Factory qwen3/1024 creates OllamaEmbedder not OpenAIEmbedder
    requirement: P6-OLL-EMB-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_factories.py::TestOllamaEmbedderFactory::test_qwen3_1024_creates_native_embedder_not_openai
        status: pass
    human_judgment: false
  - id: D4
    description: /api/embed request body model+dimensions 1024; mismatch fails before write
    requirement: P6-OLL-EMB-01
    verification:
      - kind: unit
        ref: tests/embedder/test_ollama.py::test_ollama_embed_request_body_model_dimensions_1024
        status: pass
      - kind: unit
        ref: tests/embedder/test_ollama.py::test_ollama_dimension_mismatch_fails_before_write
        status: pass
    human_judgment: false
  - id: D5
    description: prepare and commit invoke zero generative LLM calls under native Ollama
    requirement: P6-OLL-EMB-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_ollama_cleanroom_config.py::test_prepare_and_commit_paths_invoke_zero_generative_llm_calls
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-23
status: complete
---

# Phase 06 Plan 06: Native Ollama Clean-Room Config TDD Summary

**TDD-locked native Ollama clean-room example (qwen3-embedding:0.6b/1024) with factory and zero-LLM prepare/commit spies**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-23T09:29:50Z
- **Completed:** 2026-07-23T09:37:49Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Stage A RED then GREEN: clean-room example is provider=ollama, model qwen3-embedding:0.6b, dimensions 1024, OLLAMA_EMBEDDER_API_URL default host.docker.internal:11434, no required embedder API key
- Stage B: EmbedderFactory + OllamaEmbedder prove native `/api/embed` with dimensions=1024 and dimension-mismatch fail-before-write
- Explicit prepare_catalog_batch + commit_prepared_catalog_batch spy: generative LLM call count exactly 0 under native Ollama embedder mock
- Separate RED (`cb1157c`) then GREEN (`1cc58a0`) commits; user-owned `config-docker-neo4j.yaml` never staged

## Task Commits

1. **Task 1: RED — Stage A clean-room config + Stage B factory/dimension contracts** - `cb1157c` (test)
2. **Task 2: GREEN — catalog-local.example native Ollama + minimal test-pass fixes** - `1cc58a0` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified

- `mcp_server/tests/test_catalog_ollama_cleanroom_config.py` - Stage A/B + zero-LLM prepare/commit suite
- `mcp_server/config/config-docker-neo4j.catalog-local.example.yaml` - native Ollama clean-room authority
- `mcp_server/tests/test_factories.py` - qwen3 1024 factory contract
- `tests/embedder/test_ollama.py` - /api/embed 1024 body + mismatch tests
- `mcp_server/tests/test_catalog_canary_scripts.py` - secret-free scan anchors YAML keys

## Decisions Made

- Reused existing `OllamaEmbedder` and factory branch; no new embedder class
- Omitted `api_key` from clean-room ollama providers block (schema default null) so secret-free LF scan and local no-key contract both hold
- Tightened secret-free regex to line-anchored YAML keys so `${VAR:}` empty defaults never match as secrets

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Secret-free scan false positive on empty ${VAR:}**
- **Found during:** Task 2 (GREEN)
- **Issue:** Existing canary secret-free check matched `API_KEY:}` inside `${OLLAMA_API_KEY:}` when key present with empty default
- **Fix:** Omitted api_key from example (null by default) and line-anchored secret regex in canary + cleanroom suites
- **Files modified:** `mcp_server/config/config-docker-neo4j.catalog-local.example.yaml`, `mcp_server/tests/test_catalog_canary_scripts.py`, `mcp_server/tests/test_catalog_ollama_cleanroom_config.py`
- **Committed in:** `1cc58a0`

**2. [Rule 3 - Blocking] mcp_server venv used PyPI graphiti-core without ollama module**
- **Found during:** Task 1 (RED)
- **Issue:** Fresh `uv run` in mcp_server installed graphiti-core 0.29.2 from PyPI (no `embedder.ollama`)
- **Fix:** Local editable install of monorepo graphiti-core for the test session (`uv pip install -e ..`); no production package change
- **Files modified:** none (local venv only)
- **Verification:** `uv run --no-sync` imports `graphiti_core.embedder.ollama`

---

**Total deviations:** 2 auto-fixed (Rule 2 x1, Rule 3 x1)
**Impact on plan:** Correctness of secret scan + testability only. No scope creep; no image/runtime/canary.

## Issues Encountered

- mcp_server package env does not automatically bind monorepo graphiti-core Ollama module; local editable install required for factory tests in this worktree
- Root `.venv` lacked pytest until `uv sync --extra dev` (dev-only)

## User Setup Required

None - no external service configuration required for this plan (no runtime/canary).

## Next Phase Readiness

- Ready for 06-07 (capability/launcher) with native Ollama example authority
- Immutable OpenAI-path ledger/report/R receipts untouched; 06-05 not resumed; no 06-05-SUMMARY
- Dirty `mcp_server/config/config-docker-neo4j.yaml` remains user-owned and unstaged

## TDD Gate Compliance

- RED commit present: `cb1157c` `test(06-06): ...`
- GREEN commit present after RED: `1cc58a0` `feat(06-06): ...`
- Intentional Stage A failures observed before GREEN (openai example still present)

## Self-Check: PASSED

- FOUND: `mcp_server/tests/test_catalog_ollama_cleanroom_config.py`
- FOUND: `mcp_server/config/config-docker-neo4j.catalog-local.example.yaml` with `provider: "ollama"` and dimensions 1024
- FOUND: commit `cb1157c`
- FOUND: commit `1cc58a0`
- Protected paths unchanged: no edits to 06-CANARY-LEDGER, 06-FINAL-REPORT, 06-R0..R3, 06-05-SUMMARY, config-docker-neo4j.yaml staged

---
*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Completed: 2026-07-23*
