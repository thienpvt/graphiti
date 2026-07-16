---
phase: 01
slug: typed-catalog-primitives
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-16
updated: 2026-07-16
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.3 + pytest-asyncio |
| **Config file** | `mcp_server/tests/pytest.ini` |
| **Quick run command** | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py tests/test_catalog_service.py tests/test_catalog_store_unit.py -q` |
| **Full suite command** | `cd mcp_server && uv run pytest tests/test_catalog_*.py -q` |
| **Estimated runtime** | Unit ~3s; Neo4j integration ~14s on local bolt://localhost:17687 |

---

## Sampling Rate

- **After every task commit:** Run the focused catalog unit tests affected by the task.
- **After every plan wave:** Run `cd mcp_server && uv run pytest tests/test_catalog_*.py -q`.
- **Before `/gsd-verify-work`:** Unit and live Neo4j integration suites, Ruff, Pyright, MCP schema listing, and relevant MCP regressions must be green.
- **Max feedback latency:** 60 seconds for unit feedback; integration latency tracked separately.

---

## Per-Task Verification Map

Six plans × two tasks. Waves match plan frontmatter (file-overlap forces 03 before 04).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | CONF-01..05, SAFE-01..03 | T-01-01 | Disabled-by-default config, explicit namespace, bounded allowlists | unit | `cd mcp_server && uv run pytest tests/test_catalog_models.py -q` | ✅ | ✅ green |
| 01-01-02 | 01 | 1 | IDEN-01,02,05..08 | T-01-02 | Server UUIDv5 and canonical lowercase SHA-256 only | unit | `cd mcp_server && uv run pytest tests/test_catalog_identity.py -q` | ✅ | ✅ green |
| 01-02-01 | 02 | 2 | ENTY-01..12, SAFE-02 | T-01-05 | Allowlisted entity Cypher; batch_id on create/changed match | unit | `cd mcp_server && uv run pytest tests/test_catalog_store_unit.py -q` | ✅ | ✅ green |
| 01-02-02 | 02 | 2 | ENTY-01..12, SAFE-04, SAFE-05 | T-01-06, T-01-07, T-01-08 | Embed before transaction; batch_id persistence; dry-run no write | unit | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k entity -q` | ✅ | ✅ green |
| 01-03-01 | 03 | 3 | RESO-01..04 | T-01-09, T-01-10 | Read-only resolve; zero embed/write | unit | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k resolve -q` | ✅ | ✅ green |
| 01-03-02 | 03 | 3 | VERI-01..05 | T-01-09, T-01-10, T-01-11 | Read-only verify; exact group_id + batch_id MATCH | unit | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k verify -q` | ✅ | ✅ green |
| 01-04-01 | 04 | 4 | EDGE-01..11 | T-01-12, T-01-13 | Exact typed endpoints; RELATES_TO; batch_id on create/changed | unit | `cd mcp_server && uv run pytest tests/test_catalog_store_unit.py -k edge -q` | ✅ | ✅ green |
| 01-04-02 | 04 | 4 | EDGE-01..11 | T-01-14, T-01-15 | Embed before tx; no endpoint create; batch_id semantics | unit | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k edge -q` | ✅ | ✅ green |
| 01-05-01 | 05 | 5 | ENTY-13, EDGE-12, GATE-01..02 | T-01-06 | Test-group-only happy path entity/edge graph | integration | `cd mcp_server && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -m 'integration and requires_neo4j' -q` | ✅ | ✅ green |
| 01-05-02 | 05 | 5 | ENTY-12, GATE-03 | T-01-06 | Conflicts, concurrency, rollback, search; no LLM/queue | integration | `cd mcp_server && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -m 'integration and requires_neo4j' -q` | ✅ | ✅ green |
| 01-06-01 | 06 | 6 | GATE-04 | — | Format, lint, typecheck, schema list, MCP regressions | tooling | catalog-scoped ruff/pyright + tool list + MCP unit regressions | ✅ | ✅ green |
| 01-06-02 | 06 | 6 | GATE-05 | — | Phase 1 report PASS only when all gates green; block Phase 2 | tooling/doc | `01-PHASE1-REPORT.md` Overall PASS; Phase 2 allowed | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠ flaky*

---

## Wave 0 Requirements

- [x] `mcp_server/tests/test_catalog_models.py` — configuration, request validation, allowlists, prefixes, limits, protected properties.
- [x] `mcp_server/tests/test_catalog_identity.py` — deterministic UUIDv5, canonical SHA-256, hash mismatch.
- [x] `mcp_server/tests/test_catalog_store_unit.py` — Cypher allowlist, no client-id interpolation, batch_id property lists.
- [x] `mcp_server/tests/test_catalog_service.py` — feature gates, structured errors, no LLM/queue, embed-before-transaction, dry-run, rollback, batch_id create/update/unchanged, resolve/verify.
- [x] `mcp_server/tests/test_catalog_neo4j_int.py` — scoped live Neo4j fixture under `oracle-catalog-tool-test` only.
- [x] Shared deterministic namespace, mock embedder vectors, safe group-scoped Neo4j fixture.
- [x] Existing pytest infrastructure covers execution; no new framework dependency.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions | Status |
|----------|-------------|------------|-------------------|--------|
| Live Neo4j 5.26+ availability and exact integration result | GATE-02 | Requires authorized running Neo4j | Run the integration command; record unskipped pass counts in `01-PHASE1-REPORT.md`. | ✅ 21 passed unskipped |
| Phase 2 remains blocked until all commands pass | GATE-05 | Milestone workflow gate | Confirm report states `PASS` only when every required command passed; otherwise stop before Phase 2. | ✅ Overall PASS recorded |

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Unit feedback latency <60 seconds.
- [x] `nyquist_compliant: true` set after validation audit.

**Approval:** Phase 1 gates green per `01-PHASE1-REPORT.md` (2026-07-16)
