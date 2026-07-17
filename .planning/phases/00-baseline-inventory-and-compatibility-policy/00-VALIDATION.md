---
phase: 0
slug: baseline-inventory-and-compatibility-policy
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-18
---

# Phase 0 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio |
| **Config file** | `mcp_server/tests/pytest.ini` |
| **Quick run command** | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py tests/test_catalog_service.py tests/test_catalog_store_unit.py tests/test_catalog_canary_scripts.py -q --tb=line` |
| **Full suite command** | `cd mcp_server && uv run pytest` |
| **Estimated runtime** | ~120 seconds targeted; full suite variable |

---

## Sampling Rate

- **After every task commit:** Review `git status`; confirm only phase allowlist was committed.
- **Heavy targeted suite (~120s):** only Plan 01 Task 2 baseline capture (catalog unit + offline canary pytest, Ruff, scoped Pyright). Do not re-run the full heavy suite on later tasks unless baseline ledger is being rewritten.
- **After Plan 02 / Wave 2:** lightweight artifact/source checks only (file presence, policy greps, fail-hard dirty-tree allowlist). No unnecessary full pytest re-run.
- **Before `/gsd-verify-work`:** Baseline and policy artifacts must exist; every check must report pass/fail/skip.
- **Max feedback latency:** 180 seconds for targeted checks; heavy suite once for baseline Task 2 only.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 0-01-01 | 01 | 1 | BASE-01, BASE-02 | T-0-04 | Inventory contains paths, counts, hashes only; no payloads | source/doc | Inventory assertions against MCP registrations and offline canary artifacts | ❌ W0 | ⬜ pending |
| 0-01-02 | 01 | 1 | BASE-03, BASE-04 | T-0-05 | Checks retain pass/fail/skip truth | test/tool | Heavy targeted pytest+Ruff+scoped Pyright once (~120s); record only | ✅ tools | ⬜ pending |
| 0-02-01 | 02 | 2 | SAFE-01, SAFE-02 | T-0-01, T-0-02 | No canary or `oracle-catalog-v2` access | source/doc | Assert policy and plans contain no live runner/query step | ❌ W0 | ⬜ pending |
| 0-02-02 | 02 | 2 | SAFE-12, SAFE-13 | T-0-03, T-0-06 | Dirty files and remote state untouched | git | Fail-hard allowlist `git status --short` (no always-success); commit allowlist | ✅ git | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `00-BASELINE.md` — source inventory, offline canary facts, check result ledger.
- [ ] `00-COMPATIBILITY-POLICY.md` — legacy contract freeze and catalog-v1 deprecation boundary.
- [ ] `00-ISOLATION-POLICY.md` — test group, canary ban, dirty-tree and remote-state rules.
- [ ] No new product tests or dependencies required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Historical ACCEPT_TAB evidence was inventoried offline only | BASE-02, SAFE-01, SAFE-02 | Absence of external Neo4j/MCP access is an operational invariant | Confirm command history/plans never invoke runner or access `oracle-catalog-v2`; compare baseline only to repository artifacts. |
| Unrelated working-tree and remote state remain untouched | SAFE-12, SAFE-13 | Requires repository state comparison | Compare pre/post `git status --short`; verify commits list phase files only; verify no push/merge/deploy/tag action. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verification or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing references.
- [ ] No watch-mode flags.
- [ ] Feedback latency < 180 seconds for targeted checks.
- [ ] `nyquist_compliant: true` set after execution evidence exists.

**Approval:** pending
