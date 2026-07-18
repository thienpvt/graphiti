---
phase: 02
slug: topology-authority-evidence-contract-hashes-and-capabilities
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-18
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`mcp_server`) |
| **Config file** | `mcp_server/pytest.ini` |
| **Quick run command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_topology.py mcp_server/tests/test_catalog_evidence.py mcp_server/tests/test_catalog_hash.py mcp_server/tests/test_catalog_capabilities.py -q --tb=line` |
| **Full suite command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_topology.py mcp_server/tests/test_catalog_evidence.py mcp_server/tests/test_catalog_hash.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_store_unit.py -q --tb=line` |
| **Estimated runtime** | Quick: <30 seconds; full focused suite: <120 seconds |

---

## Sampling Rate

- **After every task commit:** Run the task-specific test command; run the quick suite once its files exist.
- **After every plan wave:** Run the full focused suite plus scoped Ruff and Pyright.
- **Before `/gsd-verify-work`:** Full focused suite, gate runner, scoped Ruff, and scoped Pyright must be green.
- **Max feedback latency:** 120 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | EDGE-01..09, TEST-02 | T-02-01, T-02-06 | Server map rejects unregistered types/pairs before side effects | unit + service spy | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_topology.py mcp_server/tests/test_catalog_service.py -q --tb=line -k 'endpoint or topology or deferred'` | ✅ | green |
| 02-02-01 | 02 | 1 | EVID-01..06, EVID-14 | T-02-02, T-02-07 | Exclusive explicit links; bounded input; no Cartesian conversion | unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_evidence.py mcp_server/tests/test_catalog_models.py -q --tb=line -k 'evidence or provenance'` | ✅ | green |
| 02-03-01 | 03 | 2 | HASH-01..07, TEST-04 | T-02-03 | Versioned full-domain hash changes for every included field; transport fields stable | unit + service spy | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_hash.py mcp_server/tests/test_catalog_service.py -q --tb=line -k 'hash or dry_run'` | ✅ | green |
| 02-04-01 | 04 | 2 | CAPA-01..09 | T-02-04 | Read-only capabilities redact namespace/secrets and preserve `get_status` | unit + MCP registration | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_graphiti_mcp_server.py -q --tb=line -k 'capabilit or get_status or tool'` | ✅ | green |
| 02-05-01 | 05 | 3 | All Phase 2 | T-02-01..07 | Gate proves no canary/live-group/store/control-plane writes | structural + focused regression | `uv run --project mcp_server python mcp_server/tests/run_phase2_gate.py` | ✅ | green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `mcp_server/tests/test_catalog_topology.py` — exhaustive allowed/rejected topology matrix and pre-side-effect ordering.
- [x] `mcp_server/tests/test_catalog_evidence.py` — explicit evidence-link schema, bounds, identity/hash, Cartesian rejection.
- [x] `mcp_server/tests/test_catalog_hash.py` — field mutation, ordering, exclusions, versioning, catalog-hash sensitivity.
- [x] `mcp_server/tests/test_catalog_capabilities.py` — disabled-write/read-only behavior, redaction, registries, limits, support flags, status compatibility.
- [x] `mcp_server/tests/run_phase2_gate.py` — tracked fail-closed focused gate and safety ledger.

Existing pytest infrastructure covers fixtures, asyncio, and spies; no new framework dependency is needed.

---

## Manual-Only Verifications

All Phase 2 behaviors have automated verification. Live Neo4j is deliberately not probed in this contract-only phase. The gate must record `canary_executed=false`, `oracle_catalog_v2_queried=false`, and `no_new_store_or_control_plane_write_path=true`.

---

## Security Threat Map

| Threat Ref | Threat | Mitigation Evidence |
|------------|--------|---------------------|
| T-02-01 | Illegal endpoint topology becomes searchable truth | Immutable server map; exhaustive matrix; fail-before-side-effect spies |
| T-02-02 | Cartesian evidence inflates or fabricates provenance | One explicit source and one exclusive typed target per link; legacy shape rejected |
| T-02-03 | Hash omissions create false idempotence | Version-tagged full-domain recipe; mutation tests for every included field |
| T-02-04 | Capabilities leak UUID namespace, credentials, or payloads | One-way domain-separated fingerprint; response/log redaction assertions |
| T-02-05 | Capabilities trigger schema/index repair or writes | Pure builder; unknown readiness allowed; zero mutation spies |
| T-02-06 | Client widens edge vocabulary or endpoint map | No client map field; deferred edge types remain unregistered and rejected |
| T-02-07 | Unsafe errors/logs disclose evidence excerpts or source text | Structured safe codes; bounded messages; log-capture tests |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency <120 seconds.
- [x] Focused pytest suite passes.
- [x] Scoped Ruff passes.
- [x] Scoped Pyright passes or baseline-only failures are truthfully isolated.
- [x] Safety ledger records no canary, no `oracle-catalog-v2` access, no new store/control-plane write path.
- [x] `nyquist_compliant: true` set only after evidence exists.

**Approval:** local gate green via 02-GATE-RESULTS.json

## Validation Audit — 2026-07-18 (Nyquist re-audit @ HEAD d78924a)

| Metric | Value |
|--------|-------|
| **HEAD** | `d78924aee44b148f3e789cf129acacdd58e2f183` |
| **status** | `validated` (retained) |
| **nyquist_compliant** | `true` (retained) |
| **wave_0_complete** | `true` (retained) |
| **Requirements audited** | **34/34** (EDGE-01..09, HASH-01..07, CAPA-01..09, EVID-01..06, EVID-14, TEST-02, TEST-04) |
| **Gaps found** | 0 |
| **focused_pytest** | **927 passed** (8 files) |
| **topology/evidence/hash/capabilities** | **396 passed** |
| **runner_self_tests** | **15 passed** |
| **Review-fix regressions** | present (`test_batch_in_tx_already_committed_counts_evidence_links_as_unchanged`, `test_batch_status_provenance_count_includes_evidence_links`, gate-hash echo, sources-cap, pagination) |
| **Safety** | canary=false; oracle-catalog-v2=false; no_new_store_or_control_plane_write_path=true |
| **Ledger** | `02-GATE-RESULTS.json` local_gate_pass=true; re-run unit suites green at audit HEAD |

**Coverage map (requirement → automated surface):**

| Family | Count | Primary tests |
|--------|------:|---------------|
| EDGE-01..09 + TEST-02 | 10 | `test_catalog_topology.py` (exhaustive matrix + deferred types + pre-side-effect) |
| EVID-01..06, EVID-14 | 7 | `test_catalog_evidence.py` (+ models/service non-Cartesian) |
| HASH-01..07 + TEST-04 | 8 | `test_catalog_hash.py` (+ service dry-run / mismatch / gate echo) |
| CAPA-01..09 | 9 | `test_catalog_capabilities.py` (+ MCP registration / get_status) |

No implementation or test-file changes required this audit.
