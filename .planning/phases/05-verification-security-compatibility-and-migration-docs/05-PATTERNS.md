# Phase 5: Verification, Security, Compatibility, and Migration Docs - Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 14
**Analogs found:** 14 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp_server/tests/catalog_phase5_gate_runner.py` | utility (gate runner) | batch / transform | `mcp_server/tests/catalog_phase4_gate_runner.py` | exact |
| `mcp_server/tests/test_catalog_phase5_gate_runner.py` | test | request-response | `mcp_server/tests/test_catalog_phase4_gate_runner.py` | exact |
| `mcp_server/tests/test_catalog_security_matrix.py` | test | request-response | `mcp_server/tests/test_catalog_service.py` + `test_catalog_canary_scripts.py` + `test_catalog_commit_recovery.py` | role-match |
| `mcp_server/tests/test_catalog_canary_scripts.py` | test (modify) | transform (offline pure) | self + builder/runner pure load pattern | exact |
| `scripts/build_catalog_canary_requests.py` | utility (modify) | file-I/O / transform | self (offline pure; migrate shape) | exact |
| `scripts/run_catalog_canary_batch.py` | utility (modify; **never execute live**) | transform (pure offline tests only) | self; commit sequence must become prepare/commit | exact |
| `catalog/canary-v2-requests-hardened/` (or versioned suffix) | config/artifact | file-I/O | `catalog/canary-v2-requests/` historical | role-match |
| `mcp_server/README.md` | config/docs (modify) | transform (docs) | self (expand inventory) | exact |
| `mcp_server/docs/CATALOG_V2_MIGRATION.md` | config/docs (new) | transform (docs) | `mcp_server/docs/cursor_rules.md` layout only; content from D-19 | partial |
| `.planning/phases/05-.../05-GATE-RESULTS.json` | config (ledger) | batch | `.planning/phases/04-.../04-GATE-RESULTS.json` | exact |
| `.planning/phases/05-.../05-IMPLEMENTATION-REPORT.md` (and/or `.json`) | config/report | transform | Phase 4 verification/report + roadmap REPT-01 YAML | role-match |
| `mcp_server/tests/test_catalog_*_neo4j_int.py` (gap extend) | test | CRUD / request-response (live) | `test_catalog_neo4j_int.py` + fixtures | exact |
| optional `mcp_server/tests/test_catalog_ollama_e2e.py` (or script) | test | request-response | neo4j int skip policy + local Ollama config docs | role-match |
| product spies only if log scrub gap | service (minimal) | request-response | `catalog_service.py` existing logger style | role-match |

## Pattern Assignments

### `mcp_server/tests/catalog_phase5_gate_runner.py` (utility, batch)

**Analog:** `mcp_server/tests/catalog_phase4_gate_runner.py`

**Constants / two-axis safety** (lines 26–32, 108–118):
```python
SCHEMA_VERSION = 'phase4-gate-results.v1'  # Phase 5 → 'phase5-gate-results.v1'
FORBIDDEN_GROUP = 'oracle-catalog-v2'
ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
HISTORICAL_ORACLE_CATALOG_V2_QUERIED = True
HISTORICAL_V2_COMMIT = 'a67789a'
HISTORICAL_V2_CLASS = 'test_policy'
HISTORICAL_V2_SCOPE = 'local_neo4j_no_corresponding_data'
```

**Focus suite + uv pytest argv** (lines 66–77, 184–199):
```python
FOCUS_TEST_FILES = (
    # Phase 5: security_matrix, canary_scripts, service, capabilities, gates,
    # commit_recovery, concurrency, phase5_gate_runner (+ live optional)
)
def _uv_pytest(files: list[str], extra: list[str] | None = None) -> list[str]:
    argv = [
        'uv', 'run', '--project', 'mcp_server', 'python', '-m', 'pytest',
        '-c', 'mcp_server/pytest.ini', *files,
    ]
    ...
```

**Safety scan** (lines 311–350, 353–395): `scan_current_source_v2_param_query`, `check_safety_no_probe` — no neo4j driver import in runner; ban `clear_graph(`; preserve a67789a pointer.

**Readiness fail-closed** (lines 771–827):
```python
# canary_executed always False
# derive_ready_for_phase_5 → Phase 5: derive_ready_to_regenerate_canary
# Require: local_gate_pass, unit_service_pass, registration_pass,
# safety canary/clear/current_v2 all false, safety_checks_pass True
# Phase 5 adds: security_matrix pass; docs structural; offline canary pure;
# skip ≠ pass (D-02/D-03)
```

**Atomic ledger write** (lines 234–257): `atomic_write_json` via temp + `os.replace`.

**CLI** (lines 852+, 1028+): `run_gate` → ledger with `canonical_specs`, `content_digest`, `git_head`, `safety`, `canary_executed: false`.

**Copy for Phase 5:**
- Rename readiness field → `ready_to_regenerate_canary` (REPT-01 / D-02).
- Expand `FOCUS_TEST_FILES` / `canonical_specs` per RESEARCH gate table.
- Doc structural checks (section greps) as `check_*` like Phase 4 scaffolds.
- Never shell `scripts/run_catalog_canary_batch.py` live.

---

### `mcp_server/tests/test_catalog_phase5_gate_runner.py` (test)

**Analog:** `mcp_server/tests/test_catalog_phase4_gate_runner.py`

**Imports / path insert** (lines 7–20):
```python
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
import catalog_phase5_gate_runner as gate
```

**Safety fixture helper** (lines 27–39): `_current_clean_safety` with two-axis fields.

**Contracts to re-prove** (lines 42–149 pattern):
- readiness false without proofs
- readiness false on safety violation (`canary_executed`, `clear_graph_called`, `current_source_v2_param_query`)
- historical a67789a constants immutable
- `FORBIDDEN_GROUP` / `ALLOWED_TEST_GROUP` hard-coded
- Wave-0 / default fail-closed ledger

---

### `mcp_server/tests/test_catalog_security_matrix.py` (test, SAFE-03/04/06/07, TEST-10)

**Analogs:**
1. Logger AST scrub — `test_catalog_service.py` lines 88–161
2. Prohibition seed — `test_catalog_canary_scripts.py` lines 54–66
3. Commit no-embed spy — `test_catalog_commit_recovery.py` lines 262–265, 453
4. Registration 28 — `test_catalog_service.py` lines 4583–4604
5. Label security style — `tests/test_node_label_security.py` (repo root)

**AST logger scrub** (`test_catalog_service.py` 88–161):
```python
def _logger_calls(path: Path) -> list[tuple[str | None, str, str, list[str]]]:
    # walk ast.Call where func.value.id == 'logger'
    # parse JoinedStr / Constant templates
...
def test_catalog_logger_templates_omit_group_id():
    # catalog wrappers + catalog_service templates must not embed group_id / payloads
```

**PROHIBITED on deterministic catalog paths** (SAFE-03 product matrix; distinct from canary runner ban of compatibility upsert tools):
```python
# From canary seed — product SAFE-03 set (maintenance/LLM path):
PROHIBITED_ON_CATALOG_PATH = {
    'add_memory', 'add_triplet', 'build_communities', 'clear_graph',
    'delete_entity_edge', 'delete_episode', 'summarize_saga', 'update_entity',
}
# Compatibility catalog tools remain registered (D-07); not preferred large-payload path.
```

**Spy pattern** (`test_catalog_commit_recovery.py`):
```python
embedder = SimpleNamespace(create=AsyncMock())
client = SimpleNamespace(driver=driver, embedder=embedder, llm_client=None)
# after commit:
client.embedder.create.assert_not_awaited()
# extend: queue_service not called; llm_client none/not used
```

**caplog** (`test_catalog_service.py` 164–177, 674+): `_catalog_records`, `_assert_group_id_absent`; forbid payload markers, `plan_token=`, credentials keys, raw Cypher.

**Matrix rows (planner checklist):**
| Axis | Method |
|------|--------|
| SAFE-03 tools | static string/AST scan service+MCP wrappers; no call literals |
| SAFE-04 LLM/queue/community | AsyncMock spies on commit/prepare paths |
| SAFE-06 fail-closed | reuse conflict tests + assert no silent repair |
| SAFE-07 logs | AST templates + caplog forbidden substrings |
| SAFE-09 | 28-tool registration (existing test; matrix re-assert) |
| SAFE-10 | group isolation constants + store unit |

---

### `mcp_server/tests/test_catalog_canary_scripts.py` (test, offline migrate)

**Analog:** self

**Offline load** (lines 24–36):
```python
def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    ...
builder = _load_script(..., ROOT / 'scripts' / 'build_catalog_canary_requests.py')
runner = _load_script(..., RUNNER_PATH)
```

**Pre-hardening sequence to supersede** (lines 46–53):
```python
COMMIT_TOOL_SEQUENCE = [
    'upsert_catalog_batch',  # migrate offline → prepare_catalog_batch + commit_prepared_catalog_batch
    'get_catalog_ingest_status',
    'verify_catalog_batch',
    ...
]
```

**Rules:** pure offline only; fakes for MCP; never open network/Neo4j/embedder; historical ACCEPT_TAB SHA not hardened authority (IDEN-13); new artifact dir/suffix separate from `catalog/canary-v2-requests/`.

---

### `scripts/build_catalog_canary_requests.py` (utility, offline)

**Analog:** self (lines 1–102)

**Current gap (migrate offline):**
```python
GROUP_ID = 'oracle-catalog-v2'  # historical canary target metadata only for future Phase 6;
# Phase 5 offline regen must not execute writes; identity must be catalog-v2
# (identity_schema_version, system_key grammar, evidence_links, hash recipe)
PAYLOAD_FIELDS = frozenset(
    {'group_id', 'batch_id', 'catalog_sha256', 'atomic', 'entities', 'edges', 'provenance'}
)
ACCEPT_TAB_GOLDEN_REQUEST_SHA256 = 'a84e8a7a...'  # historical only — not hardened authority
```

**Imports pattern:** bootstrap `mcp_server/src` on `sys.path`; use `CatalogService` / identity helpers for hash only; no network.

**Phase 5:** emit hardened artifacts under versioned dir; keep historical dir readable; mark old golden historical-only.

---

### `scripts/run_catalog_canary_batch.py` (utility; **do not execute**)

**Analog:** self (lines 1–76)

**Hard constraints:**
- Phase 5 may edit pure-logic path for prepare/commit sequence.
- Offline unit tests import pure functions only.
- Gate runner must **not** invoke live `--mcp-url` / dry-run against MCP.
- `TARGET_GROUP_ID = 'oracle-catalog-v2'` remains future-canary metadata; never live write in Phase 5.
- Checkpoint `attempts` must not grow from Phase 5 work.

---

### Live Neo4j TEST-11 (extend existing)

**Analog:** `mcp_server/tests/test_catalog_neo4j_int.py` + `catalog_neo4j_fixtures.py`

**Isolation** (neo4j int header lines 1–11; fixtures 37–38):
```python
# Hardcoded group_id: oracle-catalog-tool-test only.
# Teardown: DETACH DELETE WHERE group_id = that value. Never clear_graph.
# Never touch oracle-catalog-v2.
# CATALOG_INT_REQUIRED=1 → missing Neo4j = FAIL else pytest.skip
GROUP = 'oracle-catalog-tool-test'
FORBIDDEN_GROUP = 'oracle-catalog-v2'
```

**Also:** `test_catalog_commit_neo4j_int.py`, `test_catalog_prepare_neo4j_int.py` — inventory first; add only missing: control labels excluded, zero writes outside test group, search interop, exact evidence/manifest.

---

### Docs: `mcp_server/README.md` + `mcp_server/docs/CATALOG_V2_MIGRATION.md`

**Analog README:** self (expand; still “seven tools” drift — DOCS-01).

**Operator reference content authority (D-18):**
- 28 tools: `CATALOG_TOOL_NAMES` in `graphiti_mcp_server.py` + `LEGACY_TOOL_NAMES` in tests
- Error codes: `CatalogErrorCode` in `mcp_server/src/models/catalog_common.py`
- prepare/commit preferred large-payload path
- No secrets / no namespace secret values

**Migration guide (D-19):** v1 keys/hashes obsolete; no auto migration; offline regen procedure; old ACCEPT_TAB SHA banned; historical vs current safety axes.

**Structural gate:** Phase 5 runner greps required sections/phrases (clone Phase 4 `_require_defs` / scaffold checks).

---

### `05-GATE-RESULTS.json` + REPT-01 report

**Analog:** `04-GATE-RESULTS.json` + phase4 `run_gate` ledger fields

**Required fields:**
```json
{
  "schema_version": "phase5-gate-results.v1",
  "canary_executed": false,
  "ready_to_regenerate_canary": false,
  "safety": {
    "canary_executed": false,
    "oracle_catalog_v2_queried": false,
    "current_oracle_catalog_v2_queried": false,
    "historical_oracle_catalog_v2_queried": true,
    "historical_v2_commit": "a67789a",
    "historical_v2_class": "test_policy",
    "historical_v2_scope": "local_neo4j_no_corresponding_data",
    "clear_graph_called": false
  }
}
```

**Roadmap REPT-01 axes:** implementation_status, completed_phases, tests passed/failed/skipped, compatibility_breaks, migrations_added, known_limitations, blockers, ready_to_regenerate_canary, canary_executed=false.

---

### Optional Ollama E2E (D-23)

**Analog:** neo4j int availability skip + README “Using Ollama for Local LLM and Embeddings”

**Rules:** probe CLI/daemon; skip with reason if down; `oracle-catalog-tool-test` only; no protected group; no canary runner; no cleanup without human confirm.

## Shared Patterns

### Two-axis safety (REPT-01 / D-05 / D-22)
**Source:** `catalog_phase4_gate_runner.py` 108–118, 771–787; `04-GATE-RESULTS.json`
**Apply to:** Phase 5 gate runner, final report, gate unit tests
- Current flags always false on clean HEAD
- Historical a67789a retained; never rewrite

### Fail-closed readiness (D-02)
**Source:** `derive_ready_for_phase_5` lines 795–827
**Apply to:** `ready_to_regenerate_canary`
- skip ≠ pass
- any runnable required failure blocks
- canary_executed must stay false

### Offline pure canary (D-09 / D-10)
**Source:** `test_catalog_canary_scripts.py` `_load_script` + fakes
**Apply to:** builder/runner hardening + tests
- no network/DB/MCP/LLM/queue/embed side effects in Phase 5

### Isolation
**Source:** `catalog_neo4j_fixtures.py` GROUP/FORBIDDEN; neo4j int header
**Apply to:** all live tests and safety scans
- test group only; never query/mutate `oracle-catalog-v2`

### 28-tool compatibility (SAFE-09 / D-07)
**Source:** `test_catalog_service.py` 4583–4604; `CATALOG_TOOL_NAMES` product frozenset
**Apply to:** docs inventory + gate registration check

### Log scrub (SAFE-07)
**Source:** `test_catalog_service.py` AST + caplog helpers
**Apply to:** security matrix exhaustive extension

### Stdlib gate runner
**Source:** phase4 runner — argparse, subprocess list argv (no shell meta), atomic JSON
**Apply to:** phase5 runner only; no neo4j import

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | All Phase 5 deliverables have strong in-repo analogs; Ollama E2E is optional composition of existing skip + local config patterns |

## Planner bans (do not plan execution of)

- Run `scripts/run_catalog_canary_batch.py` against live/MCP (including dry-run)
- Query/mutate `oracle-catalog-v2`
- Deploy/push/merge/tag/clear_graph/existing-data deletion
- Treat skip as pass
- Reuse ACCEPT_TAB golden as hardened authority
- Product redesign beyond minimal log-scrub gap fix

## Metadata

**Analog search scope:** `mcp_server/tests/`, `mcp_server/src/`, `scripts/`, `catalog/`, `.planning/phases/04-*`, root `tests/*security*`
**Files scanned:** ~25 primary analogs
**Pattern extraction date:** 2026-07-19
