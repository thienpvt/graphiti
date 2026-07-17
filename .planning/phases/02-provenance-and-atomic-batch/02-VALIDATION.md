---
phase: 02
slug: provenance-and-atomic-batch
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-17
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `mcp_server/tests/pytest.ini`, `mcp_server/pyproject.toml` |
| **Quick run command** | `cd mcp_server && uv run pytest tests/test_catalog_identity.py tests/test_catalog_models.py tests/test_catalog_store_unit.py tests/test_catalog_service.py -q` |
| **Full suite command** | `cd mcp_server && uv run pytest tests/test_catalog_*.py -q --timeout=120` |
| **Live required command** | `cd mcp_server && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -q --timeout=120` |
| **Estimated runtime** | Quick: <60 seconds; full/live: <180 seconds each |

---

## Sampling Rate

- **After every task commit:** Run the smallest affected `test_catalog_*.py` file; run the quick command after cross-module tasks.
- **After every plan wave:** Run the full suite command.
- **Before phase verification:** Run full suite, live-required suite, scoped Ruff, scoped Pyright, MCP schema listing, and relevant existing MCP regressions.
- **Max feedback latency:** 180 seconds for automated catalog checks.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| W0-IDEN | 02-01 | 0 | IDEN-03, IDEN-04 | T-02-01 | Source and batch IDs are namespace-bound UUIDv5 values | unit | `cd mcp_server && uv run pytest tests/test_catalog_identity.py -k 'source or batch or mentions' -q` | ✅ extend | ✅ green |
| W0-PROV-MODEL | 02-01 | 0 | PROV-01, PROV-02 | T-02-02, T-02-03 | Provenance request rejects unsafe, oversized, malformed, non-finite, or protected input | unit | `cd mcp_server && uv run pytest tests/test_catalog_models.py -k provenance -q` | ✅ extend | ✅ green |
| W0-PROV-STORE | 02-02 | 0 | PROV-03, PROV-04, PROV-05, PROV-06 | T-02-02, T-02-03 | Only fixed Episodic/MENTIONS/episodes shapes are written and every match is group-scoped | unit + integration | `cd mcp_server && uv run pytest tests/test_catalog_store_unit.py -k provenance -q && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -k provenance -q --timeout=120` | ✅ extend | ✅ green |
| W0-STATUS | 02-03 | 0 | STAT-01..STAT-06 | T-02-04 | Status excludes Entity label, raw payloads, secrets, and cross-group reads | unit + integration | `cd mcp_server && uv run pytest tests/test_catalog_store_unit.py tests/test_catalog_service.py -k status -q && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -k status -q --timeout=120` | ✅ extend | ✅ green |
| W0-BATCH-MODEL | 02-04 | 0 | BATC-01, BATC-02, BATC-03, BATC-10 | T-02-10 | Complete nested request validates before side effects and rejects `atomic=false` | unit | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_service.py -k batch -q` | ✅ extend | ✅ green |
| W0-BATCH-TX | 02-04 | 0 | BATC-04..BATC-09 | T-02-11 | Endpoints union correctly; embeddings precede one atomic domain transaction; failure status follows rollback | unit + integration | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k 'batch or transaction or rollback or embedding' -q && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -k 'batch or rollback or retry' -q --timeout=120` | ✅ extend | ✅ green |
| W0-E2E | 02-05 | 0 | BATC-11, BATC-12 | T-02-20 | Sanitized ACCEPT_TAB batch retries safely, searches correctly, survives reinit, and only explicit maintenance builds communities | integration | `cd mcp_server && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -k 'accept_tab or search or communities or reinitialization' -q --timeout=120` | ✅ extend | ✅ green |
| W0-DOCS | 02-06 | 0 | DOCS-01..DOCS-05 | T-02-50, T-02-51, T-02-52 | Seven schemas and operator guidance are complete, sanitized, and non-deploying | smoke | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k 'registers_exactly_seven or registration or mcp_tool' -q` plus report source assertions | ✅ extend | ✅ green |
| W0-ISOLATION | 02-05 | 0 | PROV-05, STAT-06, BATC-08, BATC-11 | T-02-21 | Tests touch only `oracle-catalog-tool-test`; live group remains unchanged | integration | `cd mcp_server && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -q --timeout=120` | ✅ extend | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠ flaky*

---

## Wave 0 Requirements

- [x] Extend `mcp_server/tests/test_catalog_identity.py` with source, batch, and MENTIONS UUID vectors.
- [x] Extend `mcp_server/tests/test_catalog_models.py` with provenance and nested batch trust-boundary tests.
- [x] Extend `mcp_server/tests/test_catalog_store_unit.py` with Episodic, MENTIONS, edge-episode, and non-Entity status Cypher assertions.
- [x] Extend `mcp_server/tests/test_catalog_service.py` with provenance/status/batch orchestration, embedding order, rollback, and seven-tool registration tests.
- [x] Extend `mcp_server/tests/test_catalog_neo4j_int.py` with sanitized ACCEPT_TAB, retry, conflict, rollback, restart, search, isolation, and explicit community execution.
- [x] Assert all seven catalog schemas in the existing `mcp_server/tests/test_catalog_service.py` registration section.
- [x] Use only the sanitized `mcp_server/tests/fixtures/accept_tab_sanitized.json` fixture; do not copy untracked or live catalog payloads blindly.

Existing pytest infrastructure covers execution; no framework installation required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Operator guidance accurately distinguishes semantic and deterministic ingestion | DOCS-01..DOCS-04 | Editorial clarity cannot be proven fully by source assertions | Review `mcp_server/README.md` catalog section against all seven registered tool schemas and sanitized examples |
| Final report records exact observed command results and canary-only recommendation | DOCS-05 | Results must be captured after execution | Compare report command table to terminal output; verify no deployment/live write/full ingest claim |
| Docker image build command is viable | DOCS-05 | Environment-dependent build | Run documented build command locally without push or deploy; record exact result |

---

## Validation Sign-Off

- [x] All planned tasks have automated verification or explicit Wave 0 dependencies.
- [x] No three consecutive implementation tasks lack an automated check.
- [x] Wave 0 covers all missing test references.
- [x] No watch-mode flags.
- [x] Catalog writes never invoke LLM, queue, or automatic communities.
- [x] Every live test is constrained to `group_id == 'oracle-catalog-tool-test'`; the forbidden live group has read-only unchanged evidence.
- [x] Feedback latency remained below 180 seconds per sampled command.
- [x] `nyquist_compliant: true` and `wave_0_complete: true` set only after tests existed and passed.

**Approval:** earned 2026-07-17 — 260 unit, 34 unskipped live, 294 combined, Ruff, Pyright, seven-schema listing, regressions, search, explicit community, isolation, no-LLM/no-queue, and local image build all green. See `02-PHASE2-REPORT.md`.
