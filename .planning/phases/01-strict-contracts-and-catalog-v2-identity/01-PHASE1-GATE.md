# Phase 1 Gate Report

**Date:** 2026-07-18
**Consumer:** Plans 01-09 through 01-11 before any Phase 2 transition
**Authority:** Plan 01-08 outcomes retained as historical evidence; current readiness invalidated by open findings
**Policy:** every mandatory real check must return zero; Neo4j integration remains a truthful nonblocking skip without availability probe.

## Readiness Derivation

- **2026-07-18 invalidation:** CR-01, CR-02, WR-01, and WR-02 are open.
- Plan 01-08 failure-propagation and 9/9 mandatory-check outcomes remain historical evidence only, not current authorization.
- Catalog Neo4j integration remains skip — Phase 1 unit policy; availability not probed.
- Current derivation is false. Local readiness may be reconsidered only by Plan 01-11 after Plans 01-09 and 01-10 pass their mandatory checks.
- No Phase 2 work is authorized or started.

## Check Ledger

| Check | Status | Exit | Exact JSON argv / bounded result |
|-------|--------|-----:|----------------------------------|
| `runner_failure_propagation` | **pass** | 1 | `["C:\\Users\\thien\\PyCharmMiscProject\\graphiti\\.claude\\worktrees\\agent-a319dcbc393e31e6a\\mcp_server\\.venv\\Scripts\\python.exe","-c","assert False"]` — expected nonzero; excluded from gate aggregation |
| `focused_pytest` | **pass** | 0 | `["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_identity.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_store_unit.py","mcp_server/tests/test_catalog_edge_probe.py","-q","--tb=line"]` — ============================= 489 passed in 2.24s =============================; pytest_passed=489 |
| `gap_pytest` | **pass** | 0 | `["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_store_unit.py","mcp_server/tests/test_catalog_edge_probe.py","-k","source_ref or strict_true or empty_resolve or invalid_system_key or graph_key_mismatch or catalog_logger or edge_probe","-q","--tb=line"]` — ===================== 62 passed, 399 deselected in 1.20s ======================; pytest_passed=62 |
| `scoped_ruff` | **pass** | 0 | `["uv","run","--project","mcp_server","ruff","check","mcp_server/src/models","mcp_server/src/services/catalog_identity.py","mcp_server/src/services/catalog_service.py","mcp_server/src/services/catalog_store.py","mcp_server/src/graphiti_mcp_server.py","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_identity.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_store_unit.py","mcp_server/tests/test_catalog_edge_probe.py"]` — All checks passed! |
| `scoped_pyright` | **pass** | 0 | `["uv","run","--project","mcp_server","pyright","--project","mcp_server/pyproject.toml","mcp_server/src/models","mcp_server/src/services/catalog_identity.py","mcp_server/src/services/catalog_service.py","mcp_server/src/services/catalog_store.py","mcp_server/src/graphiti_mcp_server.py","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_identity.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_store_unit.py","mcp_server/tests/test_catalog_edge_probe.py"]` — Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest` |
| `validation_rows` | **pass** | 0 | `["json.loads(01-VALIDATION.md rows)","subprocess.run(argv, shell=False)"]` — 17 rows executed; every expected_exit=0; pytest_passed=2039 |
| `security_ledger` | **pass** | 0 | `["in-memory ASVS L1 structural parser","C:\\Users\\thien\\PyCharmMiscProject\\graphiti\\.claude\\worktrees\\agent-a319dcbc393e31e6a\\.planning\\phases\\01-strict-contracts-and-catalog-v2-identity\\01-SECURITY.md"]` — threats_total=41 closed=41 open=0 |
| `edge_probe` | **pass** | 0 | `["[\"uv\", \"run\", \"--project\", \"mcp_server\", \"python\", \"-m\", \"pytest\", \"-c\", \"mcp_server/pytest.ini\", \"mcp_server/tests/test_catalog_edge_probe.py\", \"--collect-only\", \"-qq\"]","[\"uv\", \"run\", \"--project\", \"mcp_server\", \"python\", \"-m\", \"pytest\", \"-c\", \"mcp_server/pytest.ini\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_cont01_model_validate_concurrency\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_cont02_recursive_forbid_concurrency\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_cont07_error_encoding_contract\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_cont07_finite_confidence_precision_contract\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_iden01_validation_ordering\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_iden01_validation_concurrency\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_iden02_system_key_ordering\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_iden04_graph_key_ordering\", \"mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_iden05_overload_ordering\", \"-q\", \"--tb=line\"]"]` — collected=9 exactly_once=9 passed=9; applicable=53 resolved=53 unresolved=0 explicit=53 backstop=0 null=0; pytest_passed=9 |
| `requirements_unique` | **pass** | 0 | `["in-memory structural parser",".planning/REQUIREMENTS.md",".planning/ROADMAP.md"]` — definitions=138 rows=138 mapped=138 duplicates=0 orphans=0; Phase 1=23 Phase 4=21 Phase 5=17 |
| `safety_invariants` | **pass** | 0 | `["[\"git\", \"diff\", \"--name-only\", \"8a55b6e..HEAD\"]","[\"git\", \"diff\", \"--cached\", \"--name-only\"]","[\"git\", \"diff\", \"--name-only\", \"8a55b6e..HEAD\", \"--\", \"mcp_server/src\"]"]` — canary=false; oracle-catalog-v2 access=false; product/store/control-plane diff=0; dependency diff=0; staged unrelated=0 |
| `catalog_neo4j_int` | **skip** | n/a | Phase 1 unit policy; availability not probed |

## Structural Mapping Proof

- Requirement definitions: 138 unique.
- Traceability rows: 138 unique; missing=0; extras=0; duplicates=0.
- ROADMAP canonical phase requirement sets equal traceability sets.
- Counts: Phase 0=8, Phase 1=23, Phase 2=34, Phase 3A=18, Phase 3B=17, Phase 4=21, Phase 5=17.
- IDEN-08 unique owner: Phase 4. Phase 1 graph-key echo is partial foundation evidence.
- IDEN-13 unique owner: Phase 5. Phase 1 v1-material inequality/historical-golden guards are partial foundation evidence.

## Edge-Probe Proof

- Applicable=53; resolved=53; unresolved=0.
- Explicit=53; backstop=0; null dispositions=0; no silent drops.
- Nine named nodes collected exactly once and passed together.

## Security Verdict

- ASVS level: L1.
- Threat rows: 41 unique; closed=41; open=0.
- T-01-14: bounded plan-authorized low residual on pure no-I/O/no-logging identity helpers only.
- T-01-18: closed by AST plus emitted-record tests across `graphiti_mcp_server.py` and `catalog_service.py`.
- T-01-SC: non-applicable; no package installation task ran.
- No human acceptance or approval is claimed.

## Historical Phase 0 Baseline Noise

- Phase 0 canary-script baseline remains recorded as fail; this gate does not relabel it.
- `catalog_neo4j_int` remains skip, never pass, because availability was not probed.

## Safety Invariants

- Canary execution: false.
- `oracle-catalog-v2` query/mutation/reuse: false.
- New product/store/control-plane write path after base `8a55b6e`: none.
- New dependency/lockfile change after base: none.
- Network, deploy, push, merge, tag, clear, delete: none.
- Unrelated staged dirt: none.

## Gate Contract

focused_pytest=pass
gap_pytest=pass
scoped_ruff=pass
scoped_pyright=pass
validation_rows=pass
security_ledger=pass
edge_probe=pass
requirements_unique=pass
safety_invariants=pass
runner_failure_propagation=pass
catalog_neo4j_int=skip
canary_executed=false
oracle_catalog_v2_queried=false
no_new_store_or_control_plane_write_path=true
ready_for_phase_2=false
resolved=53
unresolved=0

## Scope Stop

Plan 01-08's green ledger is superseded as current authorization. Plans 01-09 and 01-10 must close CR-02/WR-01 and CR-01/WR-02 respectively; Plan 01-11 alone may reconsider local readiness. Independent audits remain mandatory, so Phase 2 stays blocked.
