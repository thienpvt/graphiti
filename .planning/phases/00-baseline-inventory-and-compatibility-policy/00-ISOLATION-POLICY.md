# Phase 0 Isolation Policy

**Date:** 2026-07-18  
**Authority:** Phase 0 isolation, canary ban, dirty-tree, and remote-safety freeze (D-04, SAFE-01, SAFE-02, SAFE-12, SAFE-13). Policy only — no product code.

## 1. Write / test group (SAFE-01)

- New tests and any permitted development writes use **only** `oracle-catalog-tool-test`.
- Every catalog read and write remains constrained by `group_id`.
- No live-group writes, full ingest, graph clear, or existing-data deletion from Phase 0 tasks.

## 2. Historical canary group (SAFE-01)

- `oracle-catalog-v2` may appear **only** as offline repository inventory text (paths, digests, counts, receipts).
- Never query, mutate, retry, or use `oracle-catalog-v2` as a write target during v1.1 Phase 0–5 work.
- Inventory sources: `catalog/CANARY_V2_SUMMARY.md`, checkpoint, manifest, accept-tab receipts — not live Neo4j.

## 3. Canary ban (SAFE-02)

- Never invoke `scripts/run_catalog_canary_batch.py`, including dry-run.
- Never invoke live canary against any MCP/Neo4j endpoint from Phase 0 plans, docs workflows, or executors.
- Offline unit/workflow tests in `mcp_server/tests/test_catalog_canary_scripts.py` remain allowed (no live runner).
- Checkpoint `attempts` in `catalog/catalog.json.graphiti-canary-v2-state.json` must **not** grow due to Phase 0 work.
- Real canary execution remains Phase 6 under separate approval.

## 4. Dirty-worktree exclude list (SAFE-12)

Do **not** stage unless separately approved:

| Path | Reason |
|------|--------|
| `.planning/config.json` | Local planning config dirt |
| `mcp_server/config/config-docker-neo4j.yaml` | Env-specific deploy config |
| `mcp_server/k8s/graphiti-neo4j.yaml` | Env-specific k8s topology |
| `.codegraph/` | Local index / tool cache |
| untracked bulk `catalog/*` enrichment dumps | Large offline dumps not phase artifacts |
| `mcp_server/sample_catalog.json` | Sample / local fixture dirt |

Known pre-existing dirt must remain preserved and uncommitted by Phase 0.

## 5. Commit allowlist (SAFE-12)

Phase 0 task commits may include **only**:

- Files under `.planning/phases/00-baseline-inventory-and-compatibility-policy/`
- Intentional `.planning/STATE.md` / `.planning/ROADMAP.md` planning updates when the executor is required to update them (this plan 02 executor does **not** update shared tracking — orchestrator owns merge-time tracking)

Any other path is unexpected and fails dirty-tree verification.

## 6. Remote ban (SAFE-13)

No Phase 0 task may:

- `git push`
- merge to protected branches
- deploy
- tag
- clear graph data
- delete existing graph data
- otherwise modify remote state

Local atomic commits of allowlisted phase files only.

## 7. Logging ban

Artifacts and logs record **batch IDs, counts, hashes, failure ids** only.

Never record:

- credentials / tokens / API keys
- complete catalog payloads
- raw documents / complete source text
- full exception dumps that embed catalog content

## 8. Verification commands

Run before/after each Phase 0 commit:

```bash
# Dirty-tree snapshot — fail hard on paths outside allowlist
git status --short

# Assert no canary runner process/history for this phase
# (no shell history / plan step may invoke run_catalog_canary_batch)

# Assert this policy file itself contains the ban strings
rg -n "oracle-catalog-tool-test|run_catalog_canary_batch|SAFE-13|oracle-catalog-v2" \
  .planning/phases/00-baseline-inventory-and-compatibility-policy/00-ISOLATION-POLICY.md
```

Fail-hard allowlist check (unexpected path → exit 1):

```bash
python -c "import re,subprocess,sys; out=subprocess.check_output(['git','status','--short'],text=True,encoding='utf-8',errors='replace'); lines=[ln for ln in out.splitlines() if ln.strip()]; allow=re.compile(r'^(..)\s+(\.planning/phases/00-baseline-inventory-and-compatibility-policy/|\.planning/ROADMAP\.md|\.planning/STATE\.md|\.planning/config\.json|mcp_server/config/config-docker-neo4j\.yaml|mcp_server/k8s/graphiti-neo4j\.yaml|\.codegraph/|catalog/|mcp_server/sample_catalog\.json)'); bad=[ln for ln in lines if not allow.search(ln)]; print('status_lines',len(lines)); print('unexpected',bad); sys.exit(1 if bad else 0)"
```

## 9. Non-goals

- No product contract/identity implementation.
- No canary execution.
- No `oracle-catalog-v2` query/mutation.
- No remote ops.
- No staging of excluded dirty paths.
