---
phase: 6
slug: catalog-v2-phase-6-tdd-to-canary-clean-room-closure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-22
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio through locked `uv` environments |
| **Config file** | `pytest.ini`, `pyproject.toml`, `mcp_server/pyproject.toml` |
| **Quick run command** | `uv run --project mcp_server --frozen pytest mcp_server/tests/test_catalog_canary_scripts.py mcp_server/tests/test_catalog_schema_bootstrap.py -q` |
| **Full suite command** | Reproduce the sanitized H7 matrix, then run it again from the exact committed archive |
| **Estimated runtime** | Environment-dependent; record measured duration and zero unexplained skips/warnings |

---

## Sampling Rate

- **After every source task commit:** Run focused archive/canary/bootstrap tests.
- **After every source wave:** Run the complete H7-equivalent offline matrix.
- **Before image build:** Exact archive equality plus complete matrix from that archive must be green.
- **Before canary identity allocation:** Image inspection plus R0–R3 readiness must be green.
- **After canary identity allocation:** No source/test/image change; execute the one committed canary only.
- **Max feedback latency:** Use the smallest relevant focused selector before full-matrix escalation.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | P6-BIND-02..04 | T6-01 | Raw Git objects remain byte authority; no EOL transform | unit | focused archive tests | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | P6-BIND-05, P6-TDD-04 | T6-01 | Exact archive passes frozen matrix | offline regression | H7 matrix in archive root | ✅ evidence recipe | ⬜ pending |
| 06-02-01 | 02 | 2 | P6-IMG-01..05 | T6-02 | Image binds commit/context; excludes secrets and protected config | Docker inspect | build/inspect/hash checks | ❌ W0/operator | ⬜ pending |
| 06-03-01 | 03 | 3 | P6-RT-R0..R1 | T6-03 | Fresh isolated resources; one hidden UUIDv4 authority | live Docker | launcher render/neo4j/status checks | ✅ launcher | ⬜ pending |
| 06-03-02 | 03 | 3 | P6-RT-R2..R3 | T6-04 | Exact one-shot schema and MCP readiness | live Docker/MCP | launcher bootstrap/mcp/inspect + registry/status/capabilities | ✅ launcher/bootstrap | ⬜ pending |
| 06-04-01 | 04 | 4 | P6-CAN-01..06 | T6-05 | One canary; no retry; bounded reconcile | live MCP/Neo4j | committed runner Gates 0–10 | ✅ runner | ⬜ pending |
| 06-04-02 | 04 | 4 | P6-REPT-01, P6-TERM-* | T6-02 | Sanitized truthful terminal report | artifact validation | report schema/hash/secret scan | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Add archive materializer tests proving every regular-file member equals `git cat-file blob` bytes.
- [ ] Cover Git modes, symlink targets, member/path equality, duplicates, collisions, and stable context hashing.
- [ ] Prove the authority path does not use `git archive` or checkout EOL normalization.
- [ ] Add automated image metadata/secret-exclusion assertions where deterministic.
- [ ] Define a sanitized final-report validator or equivalent exact assertions.

Existing H1–H7 tests remain authority for already-closed launcher, materializer, bootstrap, manifest, tool registry, and compatibility behavior.

---

## Manual/Runtime Verifications

| Behavior | Requirement | Why Runtime-Gated | Test Instructions |
|----------|-------------|-------------------|-------------------|
| Source-bound image build/inspect | P6-IMG-01..05 | Requires local Docker daemon | Build only after exact archive matrix; inspect ID/labels/layers; hash sanitized logs |
| Clean-room isolation and Neo4j staging | P6-RT-R0..R1 | Requires Docker resource state | Prove absence, render, materialize once, start Neo4j only, verify mounts/health/MCP absence |
| Schema and MCP readiness | P6-RT-R2..R3 | Requires live clean-room DB/MCP | Execute one bootstrap; start MCP only; verify image ID, 28 tools, status, zero-arg capabilities |
| Final canary Gates 0–10 | P6-CAN-01..06 | Intentionally one irreversible live execution | Freeze authority before IDs; run committed prompt/runner once; preserve stack and ledger |
| Historical-resource preservation | P6-PRES-03, P6-SAFE-01..02 | Requires before/after Docker inventory | Compare sanitized historical inventory; never mutate or clean historical/final resources |

---

## Validation Sign-Off

- [ ] All tasks have automated verification or explicit runtime-gated proof.
- [ ] No three consecutive source tasks lack a focused automated check.
- [ ] Wave 0 covers archive, image, and report gaps before their dependent waves.
- [ ] No watch-mode flags, hidden retries, skipped contracts, or deselection.
- [ ] Exact committed archive passes the full frozen matrix before image construction.
- [ ] Canary freeze recorded before any run/group/control/batch ID allocation.
- [ ] `nyquist_compliant: true` set only after every required proof is mapped and executable.

**Approval:** pending
