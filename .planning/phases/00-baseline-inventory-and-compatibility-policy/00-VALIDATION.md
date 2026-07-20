---
phase: 0
slug: baseline-inventory-and-compatibility-policy
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-18
validated: 2026-07-18
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
| 0-01-01 | 01 | 1 | BASE-01, BASE-02 | T-0-04 | Inventory contains paths, counts, hashes only; no payloads | source/doc | `python` assert `@mcp.tool` count==21 + baseline tool tables; digest/path presence for offline ACCEPT_TAB | ✅ artifacts | ✅ green |
| 0-01-02 | 01 | 1 | BASE-03, BASE-04 | T-0-05 | Checks retain pass/fail/skip truth | test/tool | Heavy targeted pytest+Ruff+scoped Pyright once (~120s); ledger in `00-baseline-checks.json` (fail/skip retained) | ✅ tools + JSON | ✅ green |
| 0-02-01 | 02 | 2 | SAFE-01, SAFE-02 | T-0-01, T-0-02 | No canary or `oracle-catalog-v2` access | source/doc | Policy/plan greps + JSON flags `canary_executed=false`, `oracle_catalog_v2_queried=false` | ✅ policies | ✅ green |
| 0-02-02 | 02 | 2 | SAFE-12, SAFE-13 | T-0-03, T-0-06 | Dirty files and remote state untouched | git | Fail-hard allowlist on `git status --short`; phase commits path-scoped; no push/merge/deploy/tag | ✅ git | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `00-BASELINE.md` — source inventory, offline canary facts, check result ledger.
- [x] `00-COMPATIBILITY-POLICY.md` — legacy contract freeze and catalog-v1 deprecation boundary.
- [x] `00-ISOLATION-POLICY.md` — test group, canary ban, dirty-tree and remote-state rules.
- [x] No new product tests or dependencies required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| *(none)* | — | All Phase 0 requirements have runnable automated evidence: source assertions, JSON ledger validation, policy/plan greps, git allowlist, safety flags, and recorded heavy-suite-once results. True operational absence (no canary invoke / no `oracle-catalog-v2` query) is established by explicit JSON flags + plan bans + phase commit path history without Neo4j/MCP contact. | — |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verification or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency < 180 seconds for targeted checks.
- [x] `nyquist_compliant: true` set after execution evidence exists.

**Approval:** validated 2026-07-18 (Nyquist audit)

---

## Validation Audit 2026-07-18

| Req | Evidence command / artifact | Result | Classification |
|-----|----------------------------|--------|----------------|
| BASE-01 | `@mcp.tool` count == 21; `00-BASELINE.md` 14+7 tables + surface map | pass | automated |
| BASE-02 | Baseline ACCEPT_TAB digests/counts; offline `catalog/` checkpoint/manifest/summary exist; no Neo4j | pass | automated |
| BASE-03 | `00-baseline-checks.json` enum `{pass,fail,skip}`; `catalog_unit_and_offline_canary=fail` + `first_failure_id`; heavy suite once (not re-run this audit) | pass | automated (recorded) |
| BASE-04 | ruff/pyright pass rows; neo4j int `skip`; `00-COMPATIBILITY-POLICY.md` catalog-v1 boundary | pass | automated |
| SAFE-01 | `00-ISOLATION-POLICY.md` tool-test only + v2 offline; JSON `oracle_catalog_v2_queried=false` | pass | automated |
| SAFE-02 | Isolation/plan canary ban; JSON `canary_executed=false`; no runner invoke this audit | pass | automated |
| SAFE-12 | Fail-hard dirty allowlist vs isolation exclude list; phase commit path scope | pass | automated |
| SAFE-13 | Remote ban in isolation policy; phase commits local-only; no push this audit | pass | automated |

**Notes:** Documentation/process-only phase — no product tests invented. Heavy pytest/Ruff/Pyright suite not re-run (intentional heavy-suite-once sampling preserved; ledger remains authority). Pre-existing canary-script `fail` retained as baseline noise. `nyquist_compliant: true`. `wave_0_complete: true`. `ready_for_phase_1=true` unchanged in gate.
