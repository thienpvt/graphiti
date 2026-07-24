---
phase: 04
slug: manifest-backed-verification-and-read-only-diagnostics
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
validated: 2026-07-19
validated_head: 9b9134e6a2832df6ec22841ee5aedd88767b8cc0
suite_passed: 380
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
| **Full suite command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_verify_manifest.py mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_store_unit.py mcp_server/tests/test_catalog_phase4_gate_runner.py -q --tb=short` |
| **Estimated runtime** | ~6 seconds (observed 5.37s, 380 passed) |

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
| 04-01-01 | 01 | 1 | GATE-*, MANI-05, VERI-*, RESE-*, EVID-*, IDEN-08, TEST-08/09 (scaffolds) | T-04-GATE | Wave 0 RED→GREEN scaffolds + phase4 gate runner | unit collect | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_verify_manifest.py mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py mcp_server/tests/test_catalog_phase4_gate_runner.py --collect-only -q` | ✅ | ✅ green |
| 04-02-01 | 02 | 2 | GATE-01, GATE-02, GATE-03, GATE-04, GATE-05, GATE-06 | T-04-GATE, T-04-ISO | Read/write gates split; reads mutation-free and group-scoped; found=false; capabilities truth | unit/service | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_capabilities.py -q -x` | ✅ | ✅ green |
| 04-03-01 | 03 | 3 | MANI-05, IDEN-08 | T-04-MANI, T-04-BOUND | Manifest bytes fail closed; pages preserve canonical order and bounded projection | unit/service | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_store_unit.py -q -x` | ✅ | ✅ green |
| 04-04-01 | 04 | 4 | VERI-01, VERI-02, VERI-03, VERI-04, VERI-05, VERI-06, EVID-13, TEST-08, IDEN-08 | T-04-AUTH, T-04-DRIFT | Durable manifest sole batch expectation; live rows observations only; EVID-13 uuid authority | unit/service | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_verify_manifest.py -q -x` | ✅ | ✅ green |
| 04-05-01 | 05 | 5 | RESE-01, RESE-02, RESE-03, EVID-12, IDEN-08 | T-04-ISO, T-04-READ, T-04-INFO | Edge + evidence diagnostics exact anomalies; no repair/embed; group-scoped | unit/service | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py -q -x` | ✅ | ✅ green |
| 04-06-01 | 06 | 6 | TEST-09, GATE-02, GATE-03, GATE-04, residual MANI/RESE/EVID/VERI/TEST-08 | T-04-CAP | Three tools registered; 28 total; legacy 14; manifest_verification flip post-proof; gate ledger | contract | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_phase4_gate_runner.py -q -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Edge probe ledger:** all 42 rows in `04-EDGE-PROBE-LEDGER.md` (canonical). Each probe maps to a named automated test; static map at audit time: 42/42 present.

### Edge probe → automated test (audit-proven)

| # | Probe ID | Primary test |
|---|----------|--------------|
| 1 | IDEN-08-unclassified | `test_catalog_manifest_read.py::test_graph_key_complete`, `test_catalog_evidence_read.py::test_full_graph_key_on_target` |
| 2 | EVID-12-adjacency | `test_catalog_evidence_read.py::test_adjacency_multi_link` |
| 3 | EVID-12-empty | `test_catalog_evidence_read.py::test_empty_links` |
| 4 | EVID-12-ordering | `test_catalog_evidence_read.py::test_ordering_stable` |
| 5 | EVID-13-unclassified | `test_catalog_verify_manifest.py::test_exact_evidence` |
| 6 | MANI-05-adjacency | `test_catalog_manifest_read.py::test_adjacency_equal_keys_distinct` |
| 7 | MANI-05-empty | `test_catalog_manifest_read.py::test_empty_categories_legal` |
| 8 | MANI-05-ordering | `test_catalog_manifest_read.py::test_manifest_page_stable_order` |
| 9 | MANI-05-concurrency | `test_catalog_manifest_read.py::test_concurrent_same_params_identical_page` |
| 10 | VERI-01-unclassified | `test_catalog_verify_manifest.py::test_batch_only_uses_manifest` |
| 11 | VERI-02-boundary | `test_catalog_verify_manifest.py::test_expected_not_live_count`, `test_empty_expected_categories` |
| 12 | VERI-02-precision | `test_catalog_verify_manifest.py::test_expected_not_live_count`, `test_never_expected_equals_observed_len` |
| 13 | VERI-03-unclassified | `test_catalog_verify_manifest.py::test_missing_and_extra` |
| 14–18 | VERI-04-* | `test_catalog_verify_manifest.py::test_consistency_checks`, `test_concurrent_verify_stable` |
| 19 | VERI-05-unclassified | `test_catalog_verify_manifest.py::test_missing_manifest_code` |
| 20 | VERI-06-unclassified | `test_catalog_verify_manifest.py::test_explicit_keys_only` |
| 21 | RESE-01-unclassified | `test_catalog_resolve_edges.py::test_resolve_typed_edges_fields` |
| 22 | RESE-02-concurrency | `test_catalog_resolve_edges.py::test_anomalies` |
| 23 | RESE-03-adjacency | `test_catalog_resolve_edges.py::test_group_isolation` |
| 24 | RESE-03-empty | `test_catalog_resolve_edges.py::test_empty_refs` |
| 25 | RESE-03-ordering | `test_catalog_resolve_edges.py::test_ordering_stable` |
| 26 | GATE-01-unclassified | `test_catalog_gates.py::test_reads_enabled_default_true_writes_false` |
| 27 | GATE-02-unclassified | `test_catalog_gates.py::test_capabilities_callable_both_gates_false` |
| 28 | GATE-03-unclassified | `test_catalog_gates.py::test_read_tools_when_writes_disabled` |
| 29 | GATE-04-unclassified | `test_catalog_gates.py::test_reads_no_schema_write_embed` |
| 30 | GATE-05-unclassified | `test_catalog_gates.py::test_missing_status_found_false` |
| 31 | GATE-06-adjacency | `test_catalog_gates.py::test_group_id_isolation_on_reads` |
| 32 | GATE-06-empty | `test_catalog_gates.py::test_empty_group_id_rejected` |
| 33 | GATE-06-ordering | `test_catalog_gates.py::test_isolation_group_id_set_equality` |
| 34 | TEST-08-boundary | `test_catalog_verify_manifest.py::test_unchanged_member_missing_diagnostic` |
| 35 | TEST-08-adjacency | `test_catalog_verify_manifest.py::test_duplicate_key_anomaly_no_repair` |
| 36 | TEST-08-empty | `test_catalog_verify_manifest.py::test_empty_batch_membership_clean` |
| 37 | TEST-08-ordering | `test_catalog_verify_manifest.py::test_missing_extra_lists_deterministic` |
| 38 | TEST-08-precision | `test_catalog_verify_manifest.py::test_count_drift_off_by_one` |
| 39 | TEST-08-concurrency | `test_catalog_verify_manifest.py::test_concurrent_verify_stable` |
| 40–42 | TEST-09-* | `test_catalog_service.py` 14-catalog + 28-tool frozenset registration |

---

## Wave 0 Requirements

- [x] `mcp_server/tests/test_catalog_manifest_read.py` — MANI-05, IDEN-08, stable bounded pagination, fail-closed reassembly.
- [x] `mcp_server/tests/test_catalog_verify_manifest.py` — VERI-01 through VERI-06, EVID-13, TEST-08.
- [x] `mcp_server/tests/test_catalog_resolve_edges.py` — RESE-01 through RESE-03.
- [x] `mcp_server/tests/test_catalog_evidence_read.py` — EVID-12, IDEN-08, pagination and isolation.
- [x] `mcp_server/tests/test_catalog_gates.py` — GATE-01 through GATE-06, zero schema/write/embed calls.
- [x] Extend `mcp_server/tests/test_catalog_service.py` — exact additive MCP registration and preserved 14-tool legacy set.
- [x] Extend `mcp_server/tests/test_catalog_capabilities.py` — split gates, positive page limits, final manifest-verification capability.
- [x] Extend `mcp_server/tests/test_catalog_store_unit.py` — fixed parameterized group-scoped Cypher and manifest chunk payload loading.
- [x] `mcp_server/tests/catalog_phase4_gate_runner.py` + `test_catalog_phase4_gate_runner.py` — fail-closed ready_for_phase_5 scaffold.

Existing pytest, fixtures, Ruff, and Pyright infrastructure covers this phase; no dependency installation.

---

## Manual-Only Verifications

All Phase 4 behaviors have automated unit/service/contract verification. Optional live Neo4j proof, if later authorized and available, must use only `oracle-catalog-tool-test`; it is not a substitute for deterministic tests and must never access `oracle-catalog-v2`.

---

## Phase Gate Commands

```bash
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_verify_manifest.py mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_store_unit.py mcp_server/tests/test_catalog_phase4_gate_runner.py -q --tb=short
cd mcp_server && uv run ruff check src/services/catalog_service.py src/services/catalog_store.py src/services/catalog_capabilities.py src/config/schema.py src/graphiti_mcp_server.py tests/test_catalog_manifest_read.py tests/test_catalog_verify_manifest.py tests/test_catalog_resolve_edges.py tests/test_catalog_evidence_read.py tests/test_catalog_gates.py tests/test_catalog_phase4_gate_runner.py
cd mcp_server && uv run pyright src/services/catalog_service.py src/services/catalog_store.py src/services/catalog_capabilities.py
```

Safety assertions: no live DB access by default; no canary, deployment, migration, `clear_graph`, deletion, remote mutation, or `oracle-catalog_v2` access. Historical `a67789a` preserved under gate historical_audit only.

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no three consecutive tasks without automated verification.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency under 30 seconds for focused checks.
- [x] All 21 Phase 4 requirements have behavioral coverage.
- [x] All 42 edge probes enumerated in `04-EDGE-PROBE-LEDGER.md` with concrete dispositions.
- [x] `nyquist_compliant: true` set only after post-execution audit.

**Approval:** validated 2026-07-19 @ HEAD `9b9134e6a2832df6ec22841ee5aedd88767b8cc0`

---

## Validation Audit 2026-07-19

| Metric | Count |
|--------|-------|
| Requirements (Phase 4) | 21 |
| Edge probes | 42 |
| Probes mapped to tests | 42/42 |
| Gaps found | 0 |
| New tests added this audit | 0 |
| Escalated product bugs | 0 |
| Focused 10-file suite | **380 passed** (5.37s) |
| Ruff (phase scope) | clean |
| Pyright (catalog_service/store/capabilities) | 0 errors |
| wave0_files check | pass |
| Product source edited | no |
| STATE/ROADMAP/REQUIREMENTS edited | no |
| Live DB / network / canary / v2 | none |

### Requirement coverage (21)

| Req | Coverage status | Evidence |
|-----|-----------------|----------|
| IDEN-08 | green | graph_key asserts in manifest_read + evidence_read |
| EVID-12 | green | evidence_read adjacency/empty/ordering |
| EVID-13 | green | verify `test_exact_evidence` |
| MANI-05 | green | manifest_read page/order/empty/concurrency |
| VERI-01..06 | green | verify_manifest suite |
| RESE-01..03 | green | resolve_edges suite |
| GATE-01..06 | green | gates suite |
| TEST-08 | green | verify TEST-08_* tests |
| TEST-09 | green | service registration 14+14=28 |

### Verdict

**nyquist_compliant: true.** No test gaps. No product escalation. Docs-only validation update.
