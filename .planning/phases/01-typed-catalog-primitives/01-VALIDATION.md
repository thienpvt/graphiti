---
phase: 01
slug: typed-catalog-primitives
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-16
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.3 + pytest-asyncio |
| **Config file** | `mcp_server/tests/pytest.ini` |
| **Quick run command** | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py tests/test_catalog_service.py -q` |
| **Full suite command** | `cd mcp_server && uv run pytest tests/test_catalog_*.py -q` |
| **Estimated runtime** | Unit <60 seconds; Neo4j integration environment-dependent |

---

## Sampling Rate

- **After every task commit:** Run the focused catalog unit tests affected by the task.
- **After every plan wave:** Run `cd mcp_server && uv run pytest tests/test_catalog_*.py -q`.
- **Before `/gsd-verify-work`:** Unit and live Neo4j integration suites, Ruff, Pyright, MCP schema listing, and relevant MCP regressions must be green.
- **Max feedback latency:** 60 seconds for unit feedback; integration latency tracked separately.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | CONF-01..05, SAFE-01..03 | T-01-01 | Disabled-by-default config, explicit namespace, bounded allowlists | unit | `cd mcp_server && uv run pytest tests/test_catalog_models.py -q` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | IDEN-01,02,05..08 | T-01-02 | Server UUIDv5 and canonical lowercase SHA-256 only | unit | `cd mcp_server && uv run pytest tests/test_catalog_identity.py -q` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 2 | ENTY-01..12 | T-01-03 | Embed before transaction; typed atomic entity persistence | unit | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k entity -q` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | RESO-01..04, VERI-01..05 | T-01-04 | Read-only scoped resolution and verification | unit | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k 'resolve or verify' -q` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 3 | EDGE-01..11 | T-01-05 | Exact typed endpoints; no creation; embed before transaction | unit | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k edge -q` | ❌ W0 | ⬜ pending |
| 01-05-01 | 05 | 4 | ENTY-13, EDGE-12, GATE-01..03 | T-01-06 | Test-group-only concurrent, rollback, search behavior | integration | `cd mcp_server && uv run pytest tests/test_catalog_neo4j_int.py -m 'integration and requires_neo4j' -q` | ❌ W0 | ⬜ pending |
| 01-06-01 | 06 | 5 | GATE-04..05 | — | Complete green gate and explicit Phase 2 block/report | tooling/doc | `cd mcp_server && uv run ruff format --check . && uv run ruff check . && uv run pyright` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠ flaky*

---

## Wave 0 Requirements

- [ ] `mcp_server/tests/test_catalog_models.py` — configuration, request validation, allowlists, prefixes, limits, protected properties.
- [ ] `mcp_server/tests/test_catalog_identity.py` — deterministic UUIDv5, canonical SHA-256, hash mismatch.
- [ ] `mcp_server/tests/test_catalog_service.py` — feature gates, structured errors, no LLM/queue, embed-before-transaction, dry-run, rollback.
- [ ] `mcp_server/tests/test_catalog_neo4j_int.py` — scoped live Neo4j fixture under `oracle-catalog-tool-test` only.
- [ ] Shared deterministic namespace, mock embedder vectors, safe group-scoped Neo4j fixture.
- [ ] Existing pytest infrastructure covers execution; no new framework dependency.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Neo4j 5.26+ availability and exact integration result | GATE-02 | Requires authorized running Neo4j | Run the integration command; record unskipped pass counts in `01-PHASE1-REPORT.md`. |
| Phase 2 remains blocked until all commands pass | GATE-05 | Milestone workflow gate | Confirm report states `PASS` only when every required command passed; otherwise stop before Phase 2. |

---

## Validation Sign-Off

- [ ] All tasks have automated verification or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing references.
- [ ] No watch-mode flags.
- [ ] Unit feedback latency <60 seconds.
- [ ] `nyquist_compliant: true` set after validation audit.

**Approval:** pending
