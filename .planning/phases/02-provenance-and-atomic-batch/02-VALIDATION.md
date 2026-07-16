---
phase: 02
slug: provenance-and-atomic-batch
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| W0-IDEN | TBD | 0 | IDEN-03, IDEN-04 | T-02-01 | Source and batch IDs are namespace-bound UUIDv5 values | unit | `cd mcp_server && uv run pytest tests/test_catalog_identity.py -k 'source or batch or mentions' -q` | ✅ extend | ⬜ pending |
| W0-PROV-MODEL | TBD | 0 | PROV-01, PROV-02 | T-02-02, T-02-03 | Provenance request rejects unsafe, oversized, malformed, non-finite, or protected input | unit | `cd mcp_server && uv run pytest tests/test_catalog_models.py -k provenance -q` | ✅ extend | ⬜ pending |
| W0-PROV-STORE | TBD | 0 | PROV-03, PROV-04, PROV-05, PROV-06 | Only fixed Episodic/MENTIONS/episodes shapes are written and every match is group-scoped | unit + integration | `cd mcp_server && uv run pytest tests/test_catalog_store_unit.py -k provenance -q && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -k provenance -q --timeout=120` | ✅ extend | ⬜ pending |
| W0-STATUS | TBD | 0 | STAT-01..STAT-06 | Status excludes Entity label, raw payloads, secrets, and cross-group reads | unit + integration | `cd mcp_server && uv run pytest tests/test_catalog_store_unit.py tests/test_catalog_service.py -k status -q && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -k status -q --timeout=120` | ✅ extend | ⬜ pending |
| W0-BATCH-MODEL | TBD | 0 | BATC-01, BATC-02, BATC-03, BATC-10 | Complete nested request validates before side effects and rejects `atomic=false` | unit | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_service.py -k batch -q` | ✅ extend | ⬜ pending |
| W0-BATCH-TX | TBD | 0 | BATC-04..BATC-09 | Endpoints union correctly; embeddings precede one atomic domain transaction; failure status follows rollback | unit + integration | `cd mcp_server && uv run pytest tests/test_catalog_service.py -k 'batch or transaction or rollback or embedding' -q && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -k 'batch or rollback or retry' -q --timeout=120` | ✅ extend | ⬜ pending |
| W0-E2E | TBD | 0 | BATC-11, BATC-12 | Sanitized ACCEPT_TAB batch retries safely, searches correctly, survives reinit, and only explicit maintenance builds communities | integration | `cd mcp_server && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -k 'accept_tab or search or communities or reinitialization' -q --timeout=120` | ✅ extend | ⬜ pending |
| W0-DOCS | TBD | 0 | DOCS-01..DOCS-05 | Seven schemas and operator guidance are complete, sanitized, and non-deploying | smoke | `cd mcp_server && uv run pytest tests/test_catalog_mcp_registration.py -q` plus report source assertions | ✅ extend | ⬜ pending |
| W0-ISOLATION | TBD | 0 | PROV-05, STAT-06, BATC-08, BATC-11 | Tests touch only `oracle-catalog-tool-test`; live group remains unchanged | integration | `cd mcp_server && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -q --timeout=120` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠ flaky*

---

## Wave 0 Requirements

- [ ] Extend `mcp_server/tests/test_catalog_identity.py` with source, batch, and MENTIONS UUID vectors.
- [ ] Extend `mcp_server/tests/test_catalog_models.py` with provenance and nested batch trust-boundary tests.
- [ ] Extend `mcp_server/tests/test_catalog_store_unit.py` with Episodic, MENTIONS, edge-episode, and non-Entity status Cypher assertions.
- [ ] Extend `mcp_server/tests/test_catalog_service.py` with provenance/status/batch orchestration, embedding order, and rollback tests.
- [ ] Extend `mcp_server/tests/test_catalog_neo4j_int.py` with sanitized ACCEPT_TAB, retry, conflict, rollback, restart, search, isolation, and explicit community execution.
- [ ] Extend `mcp_server/tests/test_catalog_mcp_registration.py` to assert all seven catalog schemas.
- [ ] Add a sanitized fixture only if inline builders become unreadable; never copy untracked or live catalog payloads blindly.

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

- [ ] All planned tasks have automated verification or explicit Wave 0 dependencies.
- [ ] No three consecutive implementation tasks lack an automated check.
- [ ] Wave 0 covers all missing test references.
- [ ] No watch-mode flags.
- [ ] Catalog writes never invoke LLM, queue, or automatic communities.
- [ ] Every live test asserts `group_id == 'oracle-catalog-tool-test'` and checks the forbidden live group remains unchanged.
- [ ] Feedback latency remains below 180 seconds per sampled command.
- [ ] `nyquist_compliant: true` and `wave_0_complete: true` set only after tests exist and pass.

**Approval:** pending
