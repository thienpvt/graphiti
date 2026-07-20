---
phase: 03B
slug: atomic-catalog-exact-evidence-and-durable-manifest-writes
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-18
---

# Phase 03B — Validation Strategy

> Per-phase validation contract for atomic co-commit, exact evidence, durable manifest, replay, recovery, and concurrency.

**Plan execution status:** Plans 01–06 executed with green evidence (unit/store/service/live gate). **Nyquist audit complete** — behavioral requirement-to-test audit found no coverage gaps; `status: validated`, `nyquist_compliant: true`.

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

Aligned to six executed plans (03B-01 … 03B-06). Audit inspected behavioral assertions, not filenames or scaffold claims. All 17 Phase 3B requirements map to executable coverage.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03B-01-T1 | 01 | 1 | PLAN-13..16, EVID-07..11, MANI-01..07, TEST-06/07 (scaffold names) | T-03B-01/02/GATE | Wave 0 scaffolds collectable; product GREEN via later plans | unit scaffold | `pytest --collect-only` five unit modules | ✅ | ✅ complete |
| 03B-01-T2 | 01 | 1 | TEST-06/07, D-32/34 | T-03B-GATE/ISO | Gate fail-closed; live group tool-test only | gate/live scaffold | `pytest test_catalog_phase3b_gate_runner.py test_catalog_commit_neo4j_int.py --collect-only` | ✅ | ✅ complete |
| 03B-02-T1 | 02 | 2 | MANI-01/02/03/04/07 | T-03B-04 | Bounded deterministic manifest bytes/chunks; no batch_id membership | unit | `pytest test_catalog_manifest.py` | ✅ | ✅ complete |
| 03B-02-T2 | 02 | 2 | D-28 response | T-03B-INFO | Additive commit fields only; no token/payload/embeddings | unit | `pytest test_catalog_manifest.py test_catalog_prepare_models.py` | ✅ | ✅ complete |
| 03B-03-T1 | 03 | 3 | EVID-07/08/09/10/11, TEST-07 | T-03B-03/05/CY | Fixed non-Entity evidence; create-once; target fail-closed | unit/store | `pytest test_catalog_evidence_store.py -k "evidence or coalesce or conflict or label or target"` | ✅ | ✅ complete |
| 03B-03-T2 | 03 | 3 | MANI-01/04/06/07, D-08/09 | T-03B-04 | Manifest root/chunks create-once; terminal agree; plan lock | unit/store | `pytest test_catalog_evidence_store.py` | ✅ | ✅ complete |
| 03B-04-T1 | 04 | 4 | PLAN-13/14, MANI-06, D-30 | T-03B-01 | Shared writer; every fault boundary rolls back | service | `pytest test_catalog_atomic_writer.py` | ✅ | ✅ complete |
| 03B-04-T2 | 04 | 4 | PLAN-13/14, EVID-09/10, D-06/26 | T-03B-EXT/FAIL | upsert+commit share writer; dry_run zero-write; no external I/O on commit | service | `pytest test_catalog_atomic_writer.py test_catalog_service.py -k "upsert or commit or dry_run or atomic or writer"` | ✅ | ✅ complete |
| 03B-05-T1 | 05 | 5 | PLAN-14/15, MANI-07 | T-03B-REVIVE | COMMITTING resume; terminal agreement; no PREPARED revival | service | `pytest test_catalog_commit_recovery.py` | ✅ | ✅ complete |
| 03B-05-T2 | 05 | 5 | PLAN-16, TEST-06, D-24/25 | T-03B-02/DUP | Concurrent same-token one logical; no dup manifest | concurrency | `pytest test_catalog_concurrency.py test_catalog_commit_recovery.py` | ✅ | ✅ complete |
| 03B-06-T1 | 06 | 6 | PLAN-13..16, EVID-07..11, MANI-01..07 | T-03B-01/ISO | Live single-tx co-commit, rollback, search, isolation | integration | `pytest test_catalog_commit_neo4j_int.py` | ✅ | ✅ complete (live 10/1) |
| 03B-06-T2 | 06 | 6 | TEST-06/07, D-32/33 | T-03B-GATE/CAP | Fail-closed schema-v2 two-axis gate; manifests=True post-flip; history permanent audit; current safety independent; CLI 0 under require-neo4j when ready | gate/unit | `pytest test_catalog_phase3b_gate_runner.py test_catalog_capabilities.py` + final `gate run --require-neo4j` | ✅ | ✅ complete |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All named scaffolds exist and collect under the final suite. `wave_0_complete: true`.

- [x] `mcp_server/tests/test_catalog_manifest.py` — canonical manifest/hash/chunk/bounds (plan 01 scaffold → 02 GREEN).
- [x] `mcp_server/tests/test_catalog_evidence_store.py` — create-once/conflict/target/label (plan 01 → 03).
- [x] `mcp_server/tests/test_catalog_atomic_writer.py` — shared writer and every fault boundary (plan 01 → 04).
- [x] `mcp_server/tests/test_catalog_commit_recovery.py` — terminal agreement and stranded COMMITTING (plan 01 → 05).
- [x] `mcp_server/tests/test_catalog_concurrency.py` — same-token and same-batch races (plan 01 → 05).
- [x] `mcp_server/tests/test_catalog_commit_neo4j_int.py` — live atomicity, rollback, replay, evidence, manifest, search, isolation (plan 01 → 06).
- [x] `mcp_server/tests/test_catalog_phase3b_gate_runner.py` plus `catalog_phase3b_gate_runner.py` — fail-closed HEAD/content/spec/live authority (plan 01 → 06).
- [x] Extend `mcp_server/tests/test_catalog_capabilities.py` and existing service/MCP regressions (plan 06).

---

## Manual-Only Verifications

None. All Phase 3B behavior must be automated. Live Neo4j is mandatory for `ready_for_phase_4=true`; unavailable credentials report skip/fail truthfully and block readiness.

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no three consecutive tasks without automated checks.
- [x] Wave 0 covers every missing test reference (files exist/collect).
- [x] Fault injection covers every persistence boundary.
- [x] Live tests use only `oracle-catalog-tool-test`.
- [x] No canary, `oracle-catalog-v2`, `clear_graph`, deployment, deletion, or remote mutation.
- [x] Full rollback leaves no partial domain/evidence/manifest/committed terminal state.
- [x] Post-execution Nyquist audit maps all 17 requirements to behavioral tests; no gaps found.
- [x] Audit rerun: 129 non-live tests passed at HEAD `1f9a7d75551fe5d1c0260f831102d2a8c5b83e18`; no DB accessed.
- [x] Existing live ledger retained: 10 passed / 1 deselected using only `oracle-catalog-tool-test`; not rerun during audit.
- [x] Historical `a67789a` test-policy event preserved unchanged.

**Plan execution:** complete (01–06 green evidence; final gate ready/complete true).
**Nyquist audit:** compliant — 17/17 requirements behaviorally covered; 0 gaps; no new tests.
**Audit evidence:** local non-live suite 129/129 green; final HEAD-bound live ledger 10/10 selected green; clean REVIEW.md.
**Approval:** validated
