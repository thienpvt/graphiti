---
phase: 04
slug: manifest-backed-verification-and-read-only-diagnostics
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for manifest-backed reads, verification, isolation, and registration.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio |
| **Config file** | `mcp_server/pytest.ini` |
| **Quick run command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_gates.py -q --tb=line -x` |
| **Full suite command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_verify_manifest.py mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_store_unit.py -q --tb=short` |
| **Estimated runtime** | ~30 seconds |

Canonical pytest config is package-root `mcp_server/pytest.ini` (used by Phase 1–3A gate runners and all 04-*-PLAN verify blocks). Do not invent a second config; `mcp_server/tests/pytest.ini` is integration-oriented and is not the Phase 4 unit path.

---

## Sampling Rate

- **After every task commit:** Run the focused test file named by that task.
- **After every plan wave:** Run the full Phase 4 focused suite.
- **Before `/gsd-verify-work`:** Full focused suite, Ruff, Pyright, registration set, and safety checks must be green.
- **Max feedback latency:** 30 seconds for focused checks.

---

## Per-Task Verification Map

Maps to actual plans: **01 Wave 0 tests/gate runner; 02 gates/config/status/capabilities; 03 manifest; 04 verification; 05 edges+evidence; 06 registration/final gate.**

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | GATE-*, MANI-05, VERI-*, RESE-*, EVID-*, IDEN-08, TEST-08/09 (scaffolds) | T-04-GATE | Wave 0 RED tests + phase4 gate runner scaffold; no product GREEN required yet | unit collect | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_verify_manifest.py mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py mcp_server/tests/test_catalog_phase4_gate_runner.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | GATE-01, GATE-02, GATE-03, GATE-04, GATE-05, GATE-06 | T-04-GATE, T-04-ISO | Read/write gates split; reads mutation-free and group-scoped; found=false; capabilities truth (except verification flip) | unit/service | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_capabilities.py -q -x` | ❌ W0 / ✅ extend | ⬜ pending |
| 04-03-01 | 03 | 3 | MANI-05, IDEN-08 | T-04-MANI, T-04-BOUND | Manifest bytes fail closed; pages preserve canonical order and bounded projection | unit/service | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_store_unit.py -q -x` | ❌ W0 / ✅ extend | ⬜ pending |
| 04-04-01 | 04 | 4 | VERI-01, VERI-02, VERI-03, VERI-04, VERI-05, VERI-06, EVID-13, TEST-08, IDEN-08 | T-04-AUTH, T-04-DRIFT | Durable manifest sole batch expectation; live rows observations only; EVID-13 uuid authority | unit/service | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_verify_manifest.py -q -x` | ❌ W0 | ⬜ pending |
| 04-05-01 | 05 | 5 | RESE-01, RESE-02, RESE-03, EVID-12, IDEN-08 | T-04-ISO, T-04-READ, T-04-INFO | Edge + evidence diagnostics exact anomalies; no repair/embed; group-scoped | unit/service | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py -q -x` | ❌ W0 | ⬜ pending |
| 04-06-01 | 06 | 6 | TEST-09, GATE-02, GATE-03, GATE-04, residual MANI/RESE/EVID/VERI/TEST-08 | T-04-CAP | Three tools registered; 28 total; legacy 14; manifest_verification flip post-proof; gate ledger | contract | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_phase4_gate_runner.py -q -x` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Edge probe ledger:** all 42 rows in `04-EDGE-PROBE-LEDGER.md` (canonical).

---

## Wave 0 Requirements

- [ ] `mcp_server/tests/test_catalog_manifest_read.py` — MANI-05, IDEN-08, stable bounded pagination, fail-closed reassembly.
- [ ] `mcp_server/tests/test_catalog_verify_manifest.py` — VERI-01 through VERI-06, EVID-13, TEST-08.
- [ ] `mcp_server/tests/test_catalog_resolve_edges.py` — RESE-01 through RESE-03.
- [ ] `mcp_server/tests/test_catalog_evidence_read.py` — EVID-12, IDEN-08, pagination and isolation.
- [ ] `mcp_server/tests/test_catalog_gates.py` — GATE-01 through GATE-06, zero schema/write/embed calls.
- [ ] Extend `mcp_server/tests/test_catalog_service.py` — exact additive MCP registration and preserved 14-tool legacy set.
- [ ] Extend `mcp_server/tests/test_catalog_capabilities.py` — split gates, positive page limits, final manifest-verification capability.
- [ ] Extend `mcp_server/tests/test_catalog_store_unit.py` — fixed parameterized group-scoped Cypher and manifest chunk payload loading.
- [ ] `mcp_server/tests/catalog_phase4_gate_runner.py` + `test_catalog_phase4_gate_runner.py` — fail-closed ready_for_phase_5 scaffold.

Existing pytest, fixtures, Ruff, and Pyright infrastructure covers this phase; no dependency installation.

---

## Manual-Only Verifications

All Phase 4 behaviors have automated unit/service/contract verification. Optional live Neo4j proof, if later authorized and available, must use only `oracle-catalog-tool-test`; it is not a substitute for deterministic tests and must never access `oracle-catalog-v2`.

---

## Phase Gate Commands

```bash
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_verify_manifest.py mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_store_unit.py mcp_server/tests/test_catalog_phase4_gate_runner.py -q --tb=short
cd mcp_server && uv run ruff check src/services/catalog_*.py src/models/catalog_*.py src/config/schema.py src/graphiti_mcp_server.py tests/test_catalog_manifest_read.py tests/test_catalog_verify_manifest.py tests/test_catalog_resolve_edges.py tests/test_catalog_evidence_read.py tests/test_catalog_gates.py
cd mcp_server && uv run pyright src/services/catalog_*.py src/models/catalog_*.py src/config/schema.py src/graphiti_mcp_server.py
```

Safety assertions: no live DB access by default; no canary, deployment, migration, `clear_graph`, deletion, remote mutation, or `oracle-catalog-v2` access.

---

## Validation Sign-Off

- [ ] All tasks have automated verification or Wave 0 dependencies.
- [ ] Sampling continuity: no three consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing references.
- [ ] No watch-mode flags.
- [ ] Feedback latency under 30 seconds for focused checks.
- [ ] All 21 Phase 4 requirements have behavioral coverage.
- [ ] All 42 edge probes enumerated in `04-EDGE-PROBE-LEDGER.md` with concrete dispositions.
- [ ] `nyquist_compliant: true` set only after post-execution audit.

**Approval:** pending
