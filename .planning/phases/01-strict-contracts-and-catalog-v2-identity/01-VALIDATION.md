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
> Statuses below are planning-time pending. Plan 01-05 refreshes them from real pytest/ruff/pyright results only — never invent green; no manual waiver for Phase 2 entry.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `mcp_server/pytest.ini` |
| **Quick run command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py -q --tb=line` |
| **Full suite command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_store_unit.py -q --tb=line` |
| **Estimated runtime** | ~120 seconds quick; ~240 seconds focused gate |

---

## Sampling Rate

- **After each strict-model/grammar task commit:** Run quick models + identity tests.
- **After identity call-site updates:** Run full focused Phase 1 suite.
- **After each wave:** Run focused suite, scoped Ruff, scoped Pyright.
- **Before Phase 2:** `01-PHASE1-GATE.md` must report focused tests, Ruff, and Pyright green; canary/live-group flags false; edge-probe unresolved=0.
- **Max feedback latency:** 240 seconds.

---

## Wave Structure (revised)

| Wave | Plans | depends_on | Notes |
|------|-------|------------|-------|
| 1 | 01-01 | [] | Strict shells |
| 2 | 01-02 | [01-01] | Grammar registry |
| 3 | 01-03 | [01-01, 01-02] | Versioned identity (serial after grammar) |
| 4 | 01-04 | [01-01, 01-02, 01-03] | SAFE-08 + CONT-07 production boundary |
| 5 | 01-05 | [01-04] | Hard gate + VALIDATION refresh + edge-probe assert |

No same-wave file overlap.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Expected Files | File Exists | Status |
|---------|------|------|-------------|-----------------|-----------------|-----------|-------------------|----------------|-------------|--------|
| 01-01-T1 | 01-01 | 1 | CONT-01..06, CONT-08, IDEN-01, IDEN-02, TEST-01 | T-01-01..05 | Unknown fields and false immutable flags fail before service dispatch | unit RED | `uv run --project mcp_server python -c "import subprocess, sys; result = subprocess.run([sys.executable, '-m', 'pytest', '-c', 'mcp_server/pytest.ini', 'mcp_server/tests/test_catalog_models.py', '-k', 'strict or extra or misspel or strict_endpoints or atomic or identity_schema or system_key or preserve or trailing or error_code or order_preserv', '-q', '--tb=line']); raise SystemExit(0 if result.returncode == 1 else 1)"` | `mcp_server/tests/test_catalog_models.py` | plan | pending |
| 01-01-T2 | 01-01 | 1 | CONT-01..06, CONT-08, IDEN-01, IDEN-02, TEST-01 | T-01-01..05 | CatalogStrictModel shells + Literal flags + CONT-08 codes | unit GREEN | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py -q --tb=line` | `mcp_server/src/models/catalog_common.py`, `catalog_entities.py`, `catalog_edges.py`, `catalog_provenance.py`, `catalog_batch.py`, `catalog_responses.py`, `tests/test_catalog_models.py` | plan | pending |
| 01-02-T1 | 01-02 | 2 | IDEN-03..06, IDEN-08, IDEN-09, IDEN-12 | T-01-06..10 | Grammar matrix + IDEN-08 echo RED | unit RED | `uv run --project mcp_server python -c "import subprocess, sys; result = subprocess.run([sys.executable, '-m', 'pytest', '-c', 'mcp_server/pytest.ini', 'mcp_server/tests/test_catalog_models.py', '-k', 'grammar or overload or system_mismatch or v1_key or catalog_v1 or graph_key_echo', '-q', '--tb=line']); raise SystemExit(0 if result.returncode == 1 else 1)"` | `mcp_server/tests/test_catalog_models.py` | plan | pending |
| 01-02-T2 | 01-02 | 2 | IDEN-03..06, IDEN-08, IDEN-09, IDEN-12 | T-01-06..10 | Fullmatch registry + v1 reject + exact graph_key | unit GREEN | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py -q --tb=line` | `mcp_server/src/models/catalog_graph_key.py`, `catalog_common.py`, `catalog_entities.py`, `catalog_edges.py`, `catalog_provenance.py`, `catalog_batch.py`, `tests/test_catalog_models.py` | plan | pending |
| 01-03-T1 | 01-03 | 3 | IDEN-07, IDEN-08, IDEN-10, IDEN-11, IDEN-13, SAFE-05, TEST-03 | T-01-11..14 | Versioned goldens + FE/BO/overload + graph_key echo RED | unit RED | `uv run --project mcp_server python -c "import subprocess, sys; result = subprocess.run([sys.executable, '-m', 'pytest', '-c', 'mcp_server/pytest.ini', 'mcp_server/tests/test_catalog_identity.py', 'mcp_server/tests/test_catalog_service.py', '-k', 'uuid or catalog_v2 or graph_key_echo or overload or fe_bo or accept_tab', '-q', '--tb=line']); raise SystemExit(0 if result.returncode == 1 else 1)"` | `mcp_server/tests/test_catalog_identity.py`, `tests/test_catalog_service.py` | plan | pending |
| 01-03-T2 | 01-03 | 3 | IDEN-07, IDEN-08, IDEN-10, IDEN-11, IDEN-13, SAFE-05, TEST-03 | T-01-11..14 | Versioned UUID helpers + pure future kinds + echo | unit GREEN | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_store_unit.py -q --tb=line` | `mcp_server/src/services/catalog_identity.py`, `tests/test_catalog_identity.py`, `tests/test_catalog_service.py`, `tests/test_catalog_store_unit.py` | plan | pending |
| 01-04-T1 | 01-04 | 4 | CONT-07, SAFE-08 | T-01-15..18 | Structured error + FastMCP typed boundary + spies RED | unit RED | `uv run --project mcp_server python -c "import subprocess, sys; result = subprocess.run([sys.executable, '-m', 'pytest', '-c', 'mcp_server/pytest.ini', 'mcp_server/tests/test_catalog_models.py', 'mcp_server/tests/test_catalog_service.py', '-k', 'structured_error or no_side_effect or never_call or typed_pydantic or production_boundary', '-q', '--tb=line']); raise SystemExit(0 if result.returncode == 1 else 1)"` | `mcp_server/tests/test_catalog_models.py`, `tests/test_catalog_service.py` | plan | pending |
| 01-04-T2 | 01-04 | 4 | CONT-07, SAFE-08 | T-01-15..18 | Converter + production FastMCP model_validate boundary | unit GREEN | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_store_unit.py -q --tb=line` | `mcp_server/src/models/catalog_common.py`, `catalog_responses.py`, `graphiti_mcp_server.py`, `tests/test_catalog_models.py`, `tests/test_catalog_service.py` | plan | pending |
| 01-05-T1 | 01-05 | 5 | TEST-01, TEST-03 (gate) | T-01-19..22 | Truthful focused pytest+ruff+pyright gate ledger | gate | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_store_unit.py -q --tb=line` then `uv run --project mcp_server ruff check mcp_server/src/models mcp_server/src/services/catalog_identity.py mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_store_unit.py` then `uv run --project mcp_server pyright mcp_server/src/models mcp_server/src/services/catalog_identity.py` | `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-PHASE1-GATE.md` | plan | pending |
| 01-05-T2 | 01-05 | 5 | all Phase 1 edge probes | T-01-23 | VALIDATION statuses from real results; edge-probe 53/53 | gate assert | `uv run --project mcp_server python -c "import json; from pathlib import Path; d=json.load(open('.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-EDGE-PROBE.json', encoding='utf-8')); c=d['coverage']; assert c['applicable']==53 and c['resolved']==53 and c['unresolved']==0; assert all(i['status']=='resolved' and i['verification'] in ('explicit','backstop') and i.get('resolution') for i in d['items']); assert c['no_silent_drop']['null_dispositions']==0 and c['no_silent_drop']['key_equality'] is True; t=Path('.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-VALIDATION.md').read_text(encoding='utf-8'); keys=['01-01-T1','01-05-T2','wave_0_complete','nyquist_compliant']; missing=[k for k in keys if k not in t]; raise SystemExit(('missing ' + str(missing)) if missing else 0)"` | `01-VALIDATION.md`, `01-EDGE-PROBE.json` | present | pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — Plan 01-05 Task 2 updates from real results only.*

**Map counts:** 10 task rows · plans 01-01..01-05 · waves 1..5 · zero placeholder plan IDs.

---

## Wave 0 Requirements

- [ ] Strict/recursive-extra/misspelling matrix covering every request and nested model. (01-01-T1/T2)
- [ ] Literal `strict_endpoints` and `atomic` rejection tests. (01-01-T1/T2)
- [ ] Raw-byte preservation tests for hash-bearing text. (01-01-T1/T2)
- [ ] Positive/negative grammar table for all 18 entity types. (01-02-T1/T2)
- [ ] FE/BO, package/standalone overload, catalog-v1 rejection, versioned UUID tests. (01-02, 01-03)
- [ ] Safe structured error shape and validation-before-side-effect spies + FastMCP typed boundary. (01-04-T1/T2)
- [ ] Shared fixture helpers migrated to catalog-v2 keys and required shell fields. (01-01..01-03)
- [ ] IDEN-08 exact complete graph_key echo (model + service). (01-02, 01-03)
- [ ] `01-PHASE1-GATE.md` truthful gate ledger. (01-05-T1)
- [ ] Edge-probe 53/53 resolved zero null dispositions. (01-05-T2)
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

## Edge-Probe Coverage (planning disposition)

| Metric | Value |
|--------|-------|
| applicable | 53 |
| resolved | 53 |
| unresolved | 0 |
| explicit | 44 |
| backstop | 9 |
| null dispositions | 0 |
| no_silent_drop key_equality | true |

Plan 01-05 Task 2 re-asserts these counts from `01-EDGE-PROBE.json` after execution.

---

## Validation Sign-Off

- [ ] Every task has automated verification.
- [ ] No 3 consecutive tasks lack focused feedback.
- [ ] Wave 0 covers every missing reference.
- [ ] No watch-mode flags.
- [ ] Feedback latency < 240 seconds.
- [ ] Edge-probe unresolved=0 and null_dispositions=0.
- [ ] `nyquist_compliant: true` set only after all Phase 1 gates pass (Plan 01-05 from real results).
- [ ] `wave_0_complete: true` set only when Wave 0 checklist is actually green.

**Approval:** pending — Plan 01-05 signs off from real gate output only.
