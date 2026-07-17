---
phase: 00-baseline-inventory-and-compatibility-policy
verified: 2026-07-18T12:00:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 0: Baseline, Inventory, and Compatibility Policy Verification Report

**Phase Goal:** Maintainers observe a recorded live-grounded baseline and explicit isolation/compatibility policy before contract or identity code changes.
**Verified:** 2026-07-18T12:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Roadmap success criteria (contract). Plan-level truths map into these five.

| # | Truth | Status | Evidence |
| --- | ------- | ---------- | ------ |
| 1 | Maintainer can review a recorded live-grounded baseline of all 14 legacy MCP tools, all 7 catalog tools, and the cherry-picked canary builder/runner/fixtures/receipts/checkpoint/tests; historical ACCEPT_TAB commit evidence is inventoried offline | ✓ VERIFIED | `00-BASELINE.md` §§1–4: 14 legacy + 7 catalog with live function-line anchors matching current `mcp_server/src/graphiti_mcp_server.py` order; `@mcp.tool` count = 21; catalog surface map paths all exist on disk; offline ACCEPT_TAB digests/counts match checkpoint/manifest/summary artifacts |
| 2 | Pre-existing catalog/canary/Ruff/Pyright failures remain distinguishable from v1.1 regressions; unavailable checks report as skipped | ✓ VERIFIED | `00-baseline-checks.json` + mirrored ledger in `00-BASELINE.md` §5: 4 rows; statuses only `{pass,fail,skip}`; `catalog_unit_and_offline_canary=fail` with first_failure_id retained; `catalog_neo4j_int=skip` (not pass); ruff/pyright pass; fail not repaired |
| 3 | Compatibility policy and catalog-v1 deprecation boundary are recorded before contract changes | ✓ VERIFIED | `00-COMPATIBILITY-POLICY.md`: 14+7 tool freezes, explicit non-silent v1→v2 ban, historical disposition table (ACCEPT_TAB SHAs, 10e/16r/1-source, 38/85, oracle-catalog-v2 offline-only), IDEN-13 golden-import ban |
| 4 | New tests and development writes use only `oracle-catalog-tool-test`; `oracle-catalog-v2` is never queried or mutated; no canary runs | ✓ VERIFIED | `00-ISOLATION-POLICY.md` §§1–3; `00-baseline-checks.json` `canary_executed=false`, `oracle_catalog_v2_queried=false`; gate safety invariants false for canary/v2-query; no phase execution commit invokes product canary runner |
| 5 | Dirty-worktree unrelated files and remote state remain untouched (no push/merge/deploy/tag) | ✓ VERIFIED | `00-ISOLATION-POLICY.md` §§4–6 + `00-PHASE0-GATE.md` §7; Phase 0 execution commits touch only phase-dir (and tracking STATE/ROADMAP on orchestrator commits); `git status --short` allowlist check exit 0 at verify; no product modules under phase dir; no remote-op evidence in phase commits |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Baseline failure disposition

Phase 0 intentionally records pre-existing targeted catalog/canary failures as `fail`.

| Check | Status | Disposition |
| ----- | ------ | ----------- |
| `catalog_unit_and_offline_canary` | fail | Baseline noise (CRLF/LF, missing `catalog/catalog.json`, cascading hash mismatches). first_failure_id preserved. Not repaired. Does **not** block `ready_for_phase_1`. |
| `ruff_catalog_surface` | pass | Recorded truthfully |
| `pyright_catalog_scoped` | pass | Scoped catalog modules only |
| `catalog_neo4j_int` | skip | Default skip; never pass-by-invention; never targets `oracle-catalog-v2` |

`ready_for_phase_1=true` in `00-PHASE0-GATE.md` is consistent with recording/isolation/compatibility deliverables and safety invariants — not with zero product-test failures.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | ----------- | ------ | ------- |
| `00-BASELINE.md` | Live inventory, offline ACCEPT_TAB, check ledger, safety flags | ✓ VERIFIED | Substantive; 14+7 tools; digests; ledger; flags |
| `00-baseline-checks.json` | Machine-readable pass\|fail\|skip ledger + safety flags | ✓ VERIFIED | ≥4 checks; enum valid; canary/v2 flags false |
| `00-COMPATIBILITY-POLICY.md` | Tool freeze + catalog-v1 deprecation boundary | ✓ VERIFIED | Tables + disposition + non-silent migration rules |
| `00-ISOLATION-POLICY.md` | Group isolation, canary ban, dirty-tree, remote ban | ✓ VERIFIED | SAFE-01/02/12/13 covered with verify commands |
| `00-PHASE0-GATE.md` | Phase 1 entry gate with `ready_for_phase_1` | ✓ VERIFIED | Checklist complete; invariants true; coverage map 8/8 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `00-BASELINE.md` tool tables | `graphiti_mcp_server.py` `@mcp.tool` registrations | file:line anchors | ✓ WIRED | Live re-grep: 21 tools; names and function lines match baseline anchors |
| `00-BASELINE.md` ACCEPT_TAB section | `catalog/CANARY_V2_SUMMARY.md`, checkpoint, manifest, accept-tab receipts | offline path + digest citation | ✓ WIRED | Digests present in checkpoint/manifest/summary; receipts exist on disk |
| `00-baseline-checks.json` | mcp_server targeted pytest/ruff/pyright | recorded command + status enum | ✓ WIRED | Commands match plan; statuses enum-valid; MD ledger mirrors JSON |
| `00-COMPATIBILITY-POLICY.md` | SAFE-09 / IDEN-12 / IDEN-13 intent | freeze + deprecation disposition | ✓ WIRED | Explicit freeze, non-silent ban, golden-import ban |
| `00-ISOLATION-POLICY.md` | SAFE-01 / SAFE-02 / SAFE-12 / SAFE-13 | enforceable rules | ✓ WIRED | tool-test only, canary ban, dirty exclude, remote ban |
| `00-PHASE0-GATE.md` | baseline + both policies | checklist + safety flags | ✓ WIRED | All artifacts present; ready_for_phase_1 justified |

### Data-Flow Trace (Level 4)

Documentation/policy phase — no dynamic UI/API render path. Offline evidence data-flow:

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| ACCEPT_TAB digests/counts | catalog_sha256, artifact_sha256, server_request_sha256, 10/16/1, 38/85 | checkpoint + manifest + summary | Yes (repo artifacts) | ✓ FLOWING |
| Tool inventory | 14+7 names + lines | live `graphiti_mcp_server.py` | Yes (source) | ✓ FLOWING |
| Check statuses | pass/fail/skip rows | recorded targeted commands | Yes (ledger retains fail/skip) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Live `@mcp.tool` count = 21 and exact name order | `rg -c "@mcp\.tool"` + name extraction | 21; order matches baseline | ✓ PASS |
| Checks JSON schema + safety flags | Python assert on `00-baseline-checks.json` | ok; fail+skip retained; flags false | ✓ PASS |
| Dirty-tree allowlist | `git status --short` + allowlist regex | status_lines 0; unexpected [] | ✓ PASS |
| Offline digests present in checkpoint/manifest | Python membership checks | all expected digests present; unique_totals 38/85 | ✓ PASS |
| Surface paths exist | existence loop over baseline map | all OK | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| N/A | Phase 0 is docs/policy; no `scripts/*/tests/probe-*.sh` declared | skipped | SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| BASE-01 | 00-01 | Recorded baseline inventory: 14 legacy + 7 catalog + surface + canary assets | ✓ SATISFIED | `00-BASELINE.md` §§1–3; live tool count/order; surface paths exist |
| BASE-02 | 00-01 | Live-grounded findings + offline ACCEPT_TAB without Neo4j query | ✓ SATISFIED | Live anchors + offline digests/counts; `oracle_catalog_v2_queried=false` |
| BASE-03 | 00-01 | Distinguish pre-existing catalog/canary failures from v1.1 regressions | ✓ SATISFIED | Fail row + first_failure_id + notes; not repaired |
| BASE-04 | 00-01, 00-02 | Distinguish Ruff/Pyright failures; unavailable=skip; catalog-v1 boundary recorded | ✓ SATISFIED | ruff/pyright pass; neo4j skip; `00-COMPATIBILITY-POLICY.md` deprecation boundary |
| SAFE-01 | 00-02 | Tests/dev writes only `oracle-catalog-tool-test`; v2 offline only | ✓ SATISFIED | Isolation policy §§1–2; gate map; no v2 query flag |
| SAFE-02 | 00-02 | No real canary execution | ✓ SATISFIED | Canary ban; `canary_executed=false`; runner marked banned |
| SAFE-12 | 00-02 | Unrelated dirty worktree files excluded from task commits | ✓ SATISFIED | Exclude list + allowlist; execution commits phase-dir only; allowlist check pass |
| SAFE-13 | 00-02 | No push/merge/deploy/tag/remote mutation | ✓ SATISFIED | Remote ban policy + gate invariant; phase commits local docs only |

No orphaned Phase 0 requirements. SAFE-03..SAFE-11 belong to later phases (not Phase 0).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX in phase execution artifacts | — | — |
| — | — | No skip mislabeled as pass | — | — |
| — | — | No product source edits in Phase 0 execution commits | — | — |
| — | — | No payload/credential dumps in baseline/policy/gate | ℹ️ Info | Isolation policy mentions "exception dumps" only as ban text |

### Safety evidence (Phase 0 prohibitions)

| Prohibition | Status | Evidence |
| ----------- | ------ | -------- |
| No canary execution | ✓ | `canary_executed=false`; runner ban; no execution-commit invoke |
| No `oracle-catalog-v2` query/mutation | ✓ | offline inventory only; `oracle_catalog_v2_queried=false` |
| No payload/source/credential/token dumps | ✓ | hashes/counts/paths/failure ids only |
| No unrelated dirty-file commits | ✓ | execution commits phase-dir only; dirty exclude list recorded |
| No push/merge/deploy/tag | ✓ | SAFE-13 ban; no remote ops in phase execution |
| No baseline skip mislabeled pass | ✓ | neo4j_int=skip; fail retained |
| No product contract/identity implementation | ✓ | phase commits docs only; no `mcp_server/src/**` or product modules in phase execution trees |

### Human Verification Required

None. Phase 0 deliverables are static planning artifacts and offline inventories fully checkable by file/git/content inspection. No visual, real-time, or external-service behaviors remain.

### Gaps Summary

None. Goal achieved: maintainers have a recorded live-grounded baseline, truthful fail/skip ledger (including intentional pre-existing canary-script fail), compatibility freeze, isolation/remote policy, and a gate with `ready_for_phase_1=true` justified without converting fail/skip to pass or implementing catalog-v2 contracts.

---

_Verified: 2026-07-18T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
