---
phase: 05
slug: verification-security-compatibility-and-migration-docs
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for pre-canary readiness. Every result is pass, fail, or
> availability-based skip. A skip is never a pass.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio through the existing `mcp_server` uv project |
| **Config file** | `mcp_server/pytest.ini` |
| **Quick run command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_security_matrix.py mcp_server/tests/test_catalog_canary_scripts.py mcp_server/tests/test_catalog_phase5_gate_runner.py -q --tb=line -x` |
| **Full suite command** | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py run` |
| **Estimated runtime** | Offline quick loop <15 seconds; full gate depends on available live Neo4j/Ollama checks |

---

## Sampling Rate

- **After every task commit:** Run the smallest named pytest module or structural check covering the changed artifact.
- **After every plan wave:** Run the Phase 5 focused offline suite plus `git diff --check`.
- **Before `/gsd-verify-work`:** Phase 5 gate runner must emit a valid ledger with every check classified pass/fail/skip, `canary_executed=false`, and no current protected-group access.
- **Max offline feedback latency:** 30 seconds.
- **Live checks:** Run only against `oracle-catalog-tool-test` when configured and available. Otherwise record an availability-based skip reason. Never query or mutate `oracle-catalog-v2`.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-W0-01 | 01 | 1 | TEST-10, TEST-12, REPT-01 | T-05-GATE | Gate defaults fail closed; canary and current protected access remain false | unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_phase5_gate_runner.py -q --tb=line` | ❌ W0 | ⬜ pending |
| 05-W0-02 | 01 | 1 | SAFE-03, SAFE-04, SAFE-06, SAFE-07 | T-05-SIDEFX, T-05-LOG | Prohibited tools, LLM, queue, implicit mutations, repair, and unsafe logs are rejected | unit/static/spy | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_security_matrix.py -q --tb=line` | ❌ W0 | ⬜ pending |
| 05-W0-03 | 01 | 1 | IDEN-13, DOCS-06 | T-05-CANARY | Offline regeneration and runner validation make no network/DB/MCP/LLM/queue/embed calls | unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_canary_scripts.py -q --tb=line` | ✅ extend | ⬜ pending |
| 05-W0-04 | 01 | 1 | TEST-11, SAFE-10 | T-05-ISO | Live checks use only `oracle-catalog-tool-test`; unavailable Neo4j is an explicit skip | integration | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_neo4j_int.py mcp_server/tests/test_catalog_commit_neo4j_int.py mcp_server/tests/test_catalog_prepare_neo4j_int.py -q --tb=line` | ✅ extend | ⬜ pending |
| 05-SEC-01 | 02 | 2 | SAFE-03, SAFE-04, SAFE-06, SAFE-07, TEST-10 | T-05-SIDEFX, T-05-LOG | Exhaustive prohibition, fail-closed conflict, and log-scrub matrix passes | unit/static/spy | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_security_matrix.py -q --tb=line` | ❌ W0 | ⬜ pending |
| 05-CAN-01 | 03 | 2 | IDEN-13, DOCS-06 | T-05-CANARY, T-05-MIGRATE | Hardened artifacts are regenerated offline; old goldens are historical only; runner is not executed | unit/offline | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_canary_scripts.py -q --tb=line` | ✅ extend | ⬜ pending |
| 05-COMP-01 | 04 | 2 | SAFE-09, SAFE-10 | T-05-COMPAT, T-05-ISO | Exact registration remains 14 legacy + 14 catalog; all catalog paths remain group scoped and Neo4j-only | contract/unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_gates.py -q --tb=short` | ✅ | ⬜ pending |
| 05-LIVE-01 | 04 | 3 | TEST-11 | T-05-ISO | Rollback, search, exact evidence/manifest, control-label exclusion, and outside-group zero-write proofs pass or skip for unavailable Neo4j | integration | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_neo4j_int.py mcp_server/tests/test_catalog_commit_neo4j_int.py mcp_server/tests/test_catalog_prepare_neo4j_int.py -q --tb=line` | ✅ extend | ⬜ pending |
| 05-DOC-01 | 05 | 3 | DOCS-01, DOCS-02, DOCS-03, DOCS-04 | T-05-DOC | Operator reference covers the exact 28-tool, grammar, topology, hash, lifecycle, evidence, manifest, gate, error, and config contracts without secrets | structural | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py check-docs` | ❌ W0 | ⬜ pending |
| 05-DOC-02 | 05 | 3 | DOCS-05, DOCS-06 | T-05-MIGRATE | Migration guide forbids automatic migration/old SHA reuse and documents offline prepare/commit regeneration without execution | structural/offline | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py check-migration` | ❌ W0 | ⬜ pending |
| 05-OLL-01 | 06 | 4 | TEST-12, D-23 | T-05-ISO | Local Ollama E2E uses local services/test group only and reports pass/fail/availability-skip truthfully | e2e | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_ollama_e2e.py -q --tb=line` | ❌ W0 | ⬜ pending |
| 05-GATE-01 | 06 | 4 | TEST-12, REPT-01 | T-05-GATE | Final ledger binds every check, preserves two-axis safety, sets `canary_executed=false`, and derives readiness fail closed | gate | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py run` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `mcp_server/tests/catalog_phase5_gate_runner.py` — fail-closed TEST-12/REPT-01 ledger cloned from the Phase 4 pattern.
- [ ] `mcp_server/tests/test_catalog_phase5_gate_runner.py` — runner self-tests: readiness formula, pass/fail/skip, two-axis safety, canary false.
- [ ] `mcp_server/tests/test_catalog_security_matrix.py` — SAFE-03/04/06/07 and TEST-10 prohibition/log/conflict matrix.
- [ ] `mcp_server/tests/test_catalog_canary_scripts.py` — RED assertions for hardened offline prepare/commit artifacts and no external side effects.
- [ ] Live TEST-11 gap tests — control labels excluded and zero writes outside `oracle-catalog-tool-test`, using existing integration fixtures.
- [ ] `mcp_server/tests/test_catalog_ollama_e2e.py` — optional local E2E with explicit availability skip; no protected-group or canary path.
- [ ] `05-GATE-RESULTS.json` initial fail-closed ledger: `ready_to_regenerate_canary=false`, `canary_executed=false`.
- [ ] Structural operator/migration doc checks for DOCS-01..06.
- [ ] Framework install: none — use existing uv/pytest/Ruff/Pyright stack.

---

## Gate Ledger Contract

| Check ID | Required Classification | Readiness Effect |
|----------|-------------------------|------------------|
| `runner_self_tests` | pass/fail | Failure blocks |
| `focused_pytest` | pass/fail | Failure blocks |
| `security_matrix` | pass/fail | Failure blocks |
| `registration_28` | pass/fail | Failure blocks |
| `safety_no_v2_current` | pass/fail | Failure blocks |
| `historical_axis_preserved` | pass/fail | Failure blocks |
| `canary_not_executed` | pass/fail | Failure blocks |
| `offline_canary_pure` | pass/fail | Failure blocks |
| `docs_operator_sections` | pass/fail | Failure blocks |
| `docs_migration_phrases` | pass/fail | Failure blocks |
| `ruff` | pass/fail/availability-skip | Runnable failure blocks; unavailable records skip reason |
| `pyright` | pass/fail/availability-skip | Runnable failure blocks; unavailable records skip reason |
| `live_neo4j_test11` | pass/fail/availability-skip | Runnable failure blocks; unavailable records skip reason |
| `ollama_e2e` | pass/fail/availability-skip | Runnable failure blocks; unavailable records skip reason |

`ready_to_regenerate_canary=true` requires every runnable required check to pass, every skip to have an availability reason, no unexplained internal failure, no blocking review/security/goal gap, `canary_executed=false`, current `oracle-catalog-v2` query/mutation false, and `clear_graph_called=false`.

---

## Manual-Only Verifications

None. Cleanup/deletion is intentionally not performed; it requires a later explicit confirmation. All Phase 5 readiness claims must have automated or artifact evidence.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies.
- [ ] Sampling continuity: no three consecutive tasks without automated verification.
- [ ] Wave 0 covers every missing reference above.
- [ ] No watch-mode flags.
- [ ] Offline feedback latency <30 seconds.
- [ ] Live/Ollama checks report availability-based skip rather than pass when unavailable.
- [ ] `canary_executed=false`; no current `oracle-catalog-v2` access.
- [ ] `nyquist_compliant: true` set only by post-execution validation.

**Approval:** pending
