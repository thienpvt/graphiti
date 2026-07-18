---
phase: 03B
slug: atomic-catalog-exact-evidence-and-durable-manifest-writes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-18
---

# Phase 03B — Validation Strategy

> Per-phase validation contract for atomic co-commit, exact evidence, durable manifest, replay, recovery, and concurrency.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode=auto`) |
| **Config file** | `mcp_server/pytest.ini` |
| **Quick run command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_evidence_store.py mcp_server/tests/test_catalog_atomic_writer.py -q --tb=line` |
| **Full suite command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_*.py -q --tb=line` |
| **Live command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_commit_neo4j_int.py -q --tb=line` |
| **Estimated runtime** | quick <15s; focused <30s; live <60s |

---

## Sampling Rate

- **After every task commit:** Run the narrow new/changed test module plus scoped Ruff.
- **After every plan wave:** Run the Phase 3B focused suite and scoped Pyright.
- **Before goal verification:** Full Phase 3B gate requires live Neo4j proof.
- **Max feedback latency:** 60 seconds for normal unit/store/service feedback; live proof at wave gate.
- No watch-mode flags.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03B-W0-01 | Wave 0 | 0 | MANI-01/02/04/07 | T-03B-04 | Bounded deterministic manifest bytes/chunks | unit | `pytest test_catalog_manifest.py` | ❌ W0 | ⬜ pending |
| 03B-W0-02 | Wave 0 | 0 | EVID-07/08/10/11 | T-03B-03/05 | Fixed non-Entity evidence, target conflicts fail | unit/store | `pytest test_catalog_evidence_store.py` | ❌ W0 | ⬜ pending |
| 03B-W0-03 | Wave 0 | 0 | PLAN-13/14, MANI-06 | T-03B-01 | One success tx; all injected failures roll back | service | `pytest test_catalog_atomic_writer.py` | ❌ W0 | ⬜ pending |
| 03B-W0-04 | Wave 0 | 0 | PLAN-14/15 | T-03B-02 | COMMITTING resumes; no PREPARED revival | service | `pytest test_catalog_commit_recovery.py` | ❌ W0 | ⬜ pending |
| 03B-W0-05 | Wave 0 | 0 | PLAN-16, TEST-06 | T-03B-02 | Concurrent commits produce one logical result | concurrency | `pytest test_catalog_concurrency.py` | ❌ W0 | ⬜ pending |
| 03B-W0-06 | Wave 0 | 0 | PLAN-13..16, EVID-07..11, MANI-01..07 | T-03B-01..08 | Live atomicity/isolation/search/control proof | integration | `pytest test_catalog_commit_neo4j_int.py` | ❌ W0 | ⬜ pending |
| 03B-W0-07 | Wave 0 | 0 | TEST-06/07 | T-03B-GATE | HEAD-bound fail-closed phase gate | gate | `pytest test_catalog_phase3b_gate_runner.py` | ❌ W0 | ⬜ pending |
| 03B-01 | 01 | 1 | MANI-01/02/03/04/07 | T-03B-04 | Manifest includes exact unchanged membership | unit | `pytest test_catalog_manifest.py` | ❌ W0 | ⬜ pending |
| 03B-02 | 02 | 1 | EVID-07/08/09/10/11, TEST-07 | T-03B-03/05 | Exact evidence coalesces; no Cartesian/search pollution | unit/store | `pytest test_catalog_evidence_store.py` | ❌ W0 | ⬜ pending |
| 03B-03 | 03 | 2 | PLAN-13/14, MANI-06 | T-03B-01 | Shared atomic writer co-commits or rolls back | service | `pytest test_catalog_atomic_writer.py` | ❌ W0 | ⬜ pending |
| 03B-04 | 04 | 3 | PLAN-14/15/16, TEST-06 | T-03B-02 | Stable replay/recovery/concurrency | service/concurrency | `pytest test_catalog_commit_recovery.py test_catalog_concurrency.py` | ❌ W0 | ⬜ pending |
| 03B-05 | 05 | 4 | all Phase 3B | T-03B-GATE | Live proof and truthful capabilities/gate | integration/gate | Phase 3B gate runner | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `mcp_server/tests/test_catalog_manifest.py` — canonical manifest/hash/chunk/bounds.
- [ ] `mcp_server/tests/test_catalog_evidence_store.py` — create-once/conflict/target/label behavior.
- [ ] `mcp_server/tests/test_catalog_atomic_writer.py` — shared writer and every fault boundary.
- [ ] `mcp_server/tests/test_catalog_commit_recovery.py` — terminal agreement and stranded `COMMITTING`.
- [ ] `mcp_server/tests/test_catalog_concurrency.py` — same-token and same-batch races.
- [ ] `mcp_server/tests/test_catalog_commit_neo4j_int.py` — live atomicity, rollback, replay, evidence, manifest, search, isolation.
- [ ] `mcp_server/tests/test_catalog_phase3b_gate_runner.py` plus runner — fail-closed HEAD/content/spec/live authority.
- [ ] Extend `mcp_server/tests/test_catalog_capabilities.py` and existing service/MCP regressions.

---

## Manual-Only Verifications

None. All Phase 3B behavior must be automated. Live Neo4j is mandatory for `ready_for_phase_4=true`; unavailable credentials report skip/fail truthfully and block readiness.

---

## Validation Sign-Off

- [ ] All tasks have automated verification or Wave 0 dependencies.
- [ ] Sampling continuity: no three consecutive tasks without automated checks.
- [ ] Wave 0 covers every missing test reference.
- [ ] Fault injection covers every persistence boundary.
- [ ] Live tests use only `oracle-catalog-tool-test`.
- [ ] No canary, `oracle-catalog-v2`, `clear_graph`, deployment, deletion, or remote mutation.
- [ ] Full rollback leaves no partial domain/evidence/manifest/committed terminal state.
- [ ] `nyquist_compliant: true` set only after post-execution audit.

**Approval:** pending
