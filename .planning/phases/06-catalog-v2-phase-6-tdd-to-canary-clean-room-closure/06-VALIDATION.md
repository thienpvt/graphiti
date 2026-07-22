---
phase: 6
slug: catalog-v2-phase-6-tdd-to-canary-clean-room-closure
status: planned
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-22
updated: 2026-07-22
plans: 5
---

# Phase 6 — Validation Strategy

> Per-phase validation contract. `nyquist_compliant: false` until execution proves every mapped probe. Status values are **planned** or **RED** only until GREEN evidence exists — never mark green at planning time.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio through locked `uv` environments |
| **Config file** | `pytest.ini`, `pyproject.toml`, `mcp_server/pyproject.toml` |
| **Quick run command** | `uv run pytest tests/script/run_catalog_canary_batch.py mcp_server/tests/test_catalog_raw_git_archive.py -q` |
| **Full suite command** | H7-equivalent offline matrix + plan-01 archive + plan-02 classification/auth/replay; frozen matrix from exact archive before image |
| **Estimated runtime** | Environment-dependent; record measured duration; unexplained_skip_count must be 0 |

---

## Sampling Rate

- **After every source task commit:** focused tests for that plan
- **After plan 01–02 source waves:** full H7-equivalent offline matrix before PREBIND freeze
- **Before image build:** exact archive equality + complete frozen matrix from archive
- **Before canary ID allocation:** IMAGE + R0–R3 green; FREEZE receipt uncommitted
- **After canary ID allocation:** no source/test/image change; one canary only
- **Max feedback latency:** smallest focused selector first

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirements | Secure Behavior | Test Type | Automated Command / Proof | File Exists | Status |
|---------|------|------|--------------|-----------------|-----------|---------------------------|-------------|--------|
| 06-01-01 | 01 | 1 | P6-TDD-01..03, P6-BIND-02..04, P6-AUTH-01 | RED archive suite; no git-archive authority; no deploy/K8s/second-canary/historical groups | unit | `uv run --project mcp_server --frozen pytest mcp_server/tests/test_catalog_raw_git_archive.py -q` (8 collected failures; pytest exit exactly 1) | present | GREEN |
| 06-01-02 | 01 | 1 | P6-BASE-01, P6-BIND-02..04, P6-PRES-01/02, P6-CONT-01, P6-AUTH-01 | GREEN plumbing materializer; baseline dcf730…; dirty config unstaged; P6-AUTH-01 criteria recorded | unit | same archive suite: 8 passed; baseline golden exact | present | GREEN |
| 06-02-01 | 02 | 2 | P6-TERM-01..04, P6-REPT-01, P6-CAN-03..06, P6-PROV-02/03, P6-HARN-19, P6-CAN-01..06 | RED: execute_cli pretransport + run_live_canary post-ID never BLOCKED; durable trio; zero streamable_http_client on Gate0 fail; success no result_directory_used; auth sentinel; one-commit replay; sanitized counts 3/2/1/5 + dry_run_zero_write_proven; final-canary importable stub + env/boundary/token fail tests; AUTH-01 kubernetes_applied=false (missing/true fail closed) | unit | `uv run pytest tests/script/run_catalog_canary_batch.py tests/script/test_run_catalog_phase6_final_canary.py mcp_server/tests/test_catalog_prepare_service.py -q -k 'post_id or execute_cli or pretransport or embedding_transport or same_token or replay or counts or dry_run or final_canary or CLAUDE_JOB or argv_expand or leftover or boundary or kubernetes_applied or AUTH_01'` (collects; pytest exit exactly 1; reject 0/2+) | planned | planned/RED |
| 06-02-02 | 02 | 2 | same + P6-PRES-01/02, P6-CONT-01, P6-CAN-01..06 | GREEN early-terminal helper; classifier; prepare/search sentinel; prompt Gate 0/10/Terminal; counts from validated manifest only; final-canary launcher job-tmp env expansion + unit tests GREEN (pre-BIND) | unit | full `tests/script/run_catalog_canary_batch.py` + `tests/script/test_run_catalog_phase6_final_canary.py` + prepare/service/security/review/capabilities GREEN | planned | planned |
| 06-03-01 | 03 | 3 | P6-BASE-01/03, P6-HARN-01..19, P6-TDD-04, P6-PRES-01/02, P6-CONT-01 | Source-complete PREBIND matrix incl. final-canary launcher suite; HARN-01..19 harn_checklist offline/live/deferred; job-tmp workspaces; no unsupported skip | offline matrix | H7-equivalent + archive + plan-02 suite incl. `test_run_catalog_phase6_final_canary.py`; write `06-PREBIND-MATRIX-RECEIPT.json` with `harn_checklist` | planned | planned |
| 06-03-02 | 03 | 3 | P6-BIND-01..06, P6-HARN-01..19, P6-TDD-04 | Freeze HEAD; exact archive bind under `$CLAUDE_JOB_DIR/tmp/phase6-bind-archive-*`; frozen matrix from archive (launcher in candidate); HARN checklist complete for pre-canary offline IDs | offline matrix + bind | `06-BIND-RECEIPT.json` + `06-MATRIX-RECEIPT.json` with `harn_checklist` proving applicable pre-canary HARN | planned | planned |
| 06-04-01 | 04 | 4 | P6-IMG-01..05, P6-BASE-02, P6-RT-00, P6-PRES-01/02 | Gate precheck; OCI labels via `docker build --label` only; **no Dockerfile/source edits**; no Plan 03 re-run; no runtime | Docker inspect strategy | plan-04 task verify; Dockerfile porcelain clean | planned | planned |
| 06-04-02 | 04 | 4 | P6-IMG-01..05 | Filtered archive-derived build under job tmp; deny-list; secret scan via symbol+blob/hash authority (not line range); IMAGE receipt; labels via --label only | Docker build/inspect | `06-IMAGE-RECEIPT.json` | planned | planned |
| 06-05-01 | 05 | 5 | P6-RT-00/R0/R1, P6-HARN-03/04/09..14, P6-SAFE-01, P6-PRES-03 | R0 isolation render + R1 Neo4j; no canary IDs | live Docker | `06-R0-RECEIPT.json` + `06-R1-RECEIPT.json` | planned | planned |
| 06-05-02 | 05 | 5 | P6-RT-R2/R3, P6-PROV-01, P6-HARN-05/06/08/17 | R2 one-shot schema; R3 MCP readiness only | live Docker/MCP | `06-R2-RECEIPT.json` + `06-R3-RECEIPT.json` | planned | planned |
| 06-05-03 | 05 | 5 | P6-CAN-01, P6-PRES-01 | Prefreeze package + `06-POST-APPROVAL-INVOCATION.json` with argv_template tokens `{CLAUDE_JOB_TMP}` (no `$CLAUDE_JOB_DIR` literals) + argv_expansion contract; no SUMMARY; no final FREEZE; no IDs | artifact | `06-PREFREEZE-HANDOFF.md` + `06-FREEZE-INPUTS.json` + `06-POST-APPROVAL-INVOCATION.json` (assert no `$` in argv_template; argv_expansion present) | planned | planned |
| 06-05-04 | 05 | 5 | P6-CAN-01..06, P6-TERM-*, P6-REPT-01, P6-PROV-03, P6-AUTH-01, P6-SAFE-02 | Terminal freeze STOP + checkpoint_contract; top-level FREEZE then expand argv per argv_expansion and run exact validated expanded argv once shell=False; dry-run counts 3/2/1/5; AUTH-01; no gsd-executor resume | live handoff (top-level) | uncommitted FREEZE + expanded launcher invocation + CANARY ledger + FINAL REPORT; incomplete plan is success | planned | planned |

*Status legend: planned · planned/RED · GREEN (execution only) · ⚠️ flaky*

---

## Wave 0 / plan-01–02 RED scaffolding

- [x] Archive materializer tests (plan 01 Task 1 RED → Task 2 GREEN; 8 passed)
- [ ] execute_cli pretransport durable FAILED_BEFORE_COMMIT + zero streamable_http_client (plan 02)
- [ ] run_live_canary post-ID never BLOCKED; create-on-failure result_dir ownership
- [ ] Auth sentinel path without CatalogErrorCode expansion
- [ ] One primary commit; committed harness replay (no second commit)
- [ ] Sanitized final-report `counts` {entities,edges,sources,evidence_links} + `dry_run_zero_write_proven`
- [ ] Final-canary launcher RED stub+tests in plan 02 Task 1; GREEN in Task 2 (pre-BIND); env unset/relative/outside-boundary/leftover-token fail closed
- [ ] Plan 04: no Dockerfile/source edits; labels via `--label` only
- [ ] Plan 05: `06-POST-APPROVAL-INVOCATION.json` with `{CLAUDE_JOB_TMP}` + argv_expansion (no `$CLAUDE_JOB_DIR` in argv_template) + Task 4 checkpoint_contract
- [ ] Prompt Gate 0 / Terminal / Gate 10 contracts

Existing H1–H7 tests remain offline authority for already-closed launcher/materializer/bootstrap/registry contracts.

---

## Manual/Runtime Verifications

| Behavior | Requirement | Why Runtime-Gated | Test Instructions |
|----------|-------------|-------------------|-------------------|
| Source-bound image build/inspect | P6-IMG-01..05 | Local Docker | Build only after exact archive matrix; inspect ID/labels; secret scan |
| Clean-room R0–R3 | P6-RT-R0..R3 | Docker resource state | Absence → render → Neo4j → bootstrap 0/14→14/14 → MCP readiness only |
| Final canary Gates 0–10 | P6-CAN-01..06 | One irreversible live execution | Top-level only after freeze approval; exact builder+runner CLI |
| Dry-run counts + zero write | P6-CAN-03 | Live report/ledger | Assert counts entities=3 edges=2 sources=1 evidence_links=5; dry_run_zero_write_proven=true |
| P6-AUTH-01 | P6-AUTH-01 | Live ledger + plan criteria | deployment_applied=false; kubernetes_applied=false (missing/true fails closed; never namespace_applied); second_canary=false; historical_group_ids_used=false; mode = iterative TDD + one final clean-room canary |
| Historical preservation | P6-PRES-03, P6-SAFE-01/02 | Docker inventory | Before/after historical inventory; leave final stack |

---

## Validation Sign-Off

- [ ] All tasks have automated verification or explicit runtime-gated proof
- [ ] No three consecutive source tasks lack a focused automated check
- [ ] Wave 0 / RED scaffolding complete before GREEN dependents
- [ ] No watch-mode, hidden retries, skipped contracts, or deselection
- [ ] Exact committed archive passes frozen matrix before image
- [ ] Canary freeze recorded before any run/group/control/batch ID allocation
- [ ] `nyquist_compliant: true` only after every required proof is mapped **and executed green**

**Approval:** pending (planning only; not green)
