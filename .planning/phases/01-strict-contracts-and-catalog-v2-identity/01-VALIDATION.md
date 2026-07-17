---
phase: 1
slug: strict-contracts-and-catalog-v2-identity
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-18
---

# Phase 1 — Validation Strategy

> Strict-contract and identity feedback contract. Phase 2 stays blocked until this strategy is green.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `mcp_server/pytest.ini` |
| **Quick run command** | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py -q --tb=line` |
| **Full suite command** | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py tests/test_catalog_service.py tests/test_catalog_store_unit.py -q --tb=line` |
| **Estimated runtime** | ~120 seconds quick; ~240 seconds focused gate |

---

## Sampling Rate

- **After each strict-model/grammar task commit:** Run quick models + identity tests.
- **After identity call-site updates:** Run full focused Phase 1 suite.
- **After each wave:** Run focused suite, scoped Ruff, scoped Pyright.
- **Before Phase 2:** `01-PHASE1-GATE.md` must report focused tests, Ruff, and Pyright green; canary/live-group flags false.
- **Max feedback latency:** 240 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | TBD | 1 | CONT-01..CONT-06, TEST-01 | T-1-01 | Unknown fields and false immutable flags fail before service dispatch | unit | models strictness matrix | ❌ W0 | ⬜ pending |
| 1-01-02 | TBD | 1 | IDEN-01..IDEN-06, IDEN-09 | T-1-02 | Version/system/full grammar fail closed | unit | grammar positive/negative matrix | ❌ W0 | ⬜ pending |
| 1-02-01 | TBD | 2 | IDEN-07, IDEN-10..IDEN-13, SAFE-05, TEST-03 | T-1-03 | FE/BO and overload identities never collide; caller UUID has no authority | unit | identity golden suite | ⚠ update | ⬜ pending |
| 1-02-02 | TBD | 2 | CONT-07, CONT-08, SAFE-08 | T-1-04 | Invalid requests create zero side effects and bounded structured errors | unit spy | service/MCP boundary spies | ❌ W0 | ⬜ pending |
| 1-03-01 | TBD | 3 | all Phase 1 | T-1-05 | Hard gate reports truthfully; no canary/live-group action | gate | focused pytest + Ruff + Pyright + scope assertions | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Strict/recursive-extra/misspelling matrix covering every request and nested model.
- [ ] Literal `strict_endpoints` and `atomic` rejection tests.
- [ ] Raw-byte preservation tests for hash-bearing text.
- [ ] Positive/negative grammar table for all 18 entity types.
- [ ] FE/BO, package/standalone overload, catalog-v1 rejection, versioned UUID tests.
- [ ] Safe structured error shape and validation-before-side-effect spies.
- [ ] Shared fixture helpers migrated to catalog-v2 keys and required shell fields.
- [ ] `01-PHASE1-GATE.md` or equivalent truthful gate ledger.
- [ ] No new framework or dependency.

---

## Manual-Only Verifications

All Phase 1 behaviors must have automated unit/source/git verification. No manual-only waiver permits Phase 2 entry.

---

## Baseline Comparison

- Phase 0 canary-script failures remain separately recorded; Phase 1 does not repair or relabel them.
- Previously passing focused model/identity/service/store tests may change only for intentional catalog-v2 contract/golden updates and must end green.
- Scoped Ruff and Pyright must remain green.
- No test or command may run the canary or access `oracle-catalog-v2`.

---

## Validation Sign-Off

- [ ] Every task has automated verification.
- [ ] No 3 consecutive tasks lack focused feedback.
- [ ] Wave 0 covers every missing reference.
- [ ] No watch-mode flags.
- [ ] Feedback latency < 240 seconds.
- [ ] `nyquist_compliant: true` set only after all Phase 1 gates pass.

**Approval:** pending
