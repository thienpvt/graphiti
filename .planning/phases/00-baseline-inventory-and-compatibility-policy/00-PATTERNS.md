# Phase 0: Baseline, Inventory, and Compatibility Policy - Pattern Map

**Mapped:** 2026-07-18
**Files analyzed:** 4 new planning artifacts (+ optional JSON) — no product code
**Analogs found:** 4 / 4 (docs/report/test/policy patterns)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `00-BASELINE.md` | report / inventory | transform (read-only → evidence ledger) | `catalog/CANARY_V2_SUMMARY.md` + `v1.0-MILESTONE-AUDIT.md` | exact (offline evidence report) |
| `00-COMPATIBILITY-POLICY.md` | config / policy doc | request-response contract freeze | `.claude/CLAUDE.md` Compatibility + REQUIREMENTS SAFE-09/IDEN-12/13 | role-match |
| `00-ISOLATION-POLICY.md` | config / policy doc | isolation / ban list | `.claude/CLAUDE.md` Isolation/Operations + `CONCERNS.md` dirty-tree | exact |
| `00-baseline-checks.json` (optional) | config / check ledger | batch check results | `00-VALIDATION.md` Per-Task map + pytest/ruff exit capture | role-match |

Phase 0 does **not** create or modify: MCP tools, catalog models/services/store, canary scripts, fixtures, Neo4j data, deploy configs.

## Pattern Assignments

### `00-BASELINE.md` (report, transform)

**Analog A — offline canary evidence narrative:** `catalog/CANARY_V2_SUMMARY.md`

**Structure to copy** (summary → scope hashes/counts → immutable workflow paths → execution status numbered list → safety state):

```markdown
# Deterministic catalog canary v2

## Scope
- Target group: `oracle-catalog-v2`
- Catalog SHA-256: `3882cb4bc50064215ead782b0fa0dfbf0098cb344b50184e6c207145377e832f`
- Planned unique entities: 38
- Planned unique edges: 85

## Immutable artifact workflow
- Builder: `scripts/build_catalog_canary_requests.py`
- Runner: `scripts/run_catalog_canary_batch.py`
- Offline tests: `mcp_server/tests/test_catalog_canary_scripts.py`
- ACCEPT_TAB golden server request SHA-256: `a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a`
- ACCEPT_TAB artifact SHA-256: `a89e3427a3b1ceec10f36d361fcdbe9e7e30243db4ff51ca59848dfb33968a33`

## Execution status
1. ACCEPT_TAB dry-run passed ...
2. ACCEPT_TAB commit completed ...
...
## Safety state
- `oracle-catalog-v1` untouched.
- `safe_for_full_ingest`: false until ...
```

**Baseline must restate ACCEPT_TAB as historical only** (IDEN-13): hashes invalid for hardened catalog-v2 goldens; never query `oracle-catalog-v2`.

**Analog B — gated audit table style:** `.planning/milestones/v1.0-MILESTONE-AUDIT.md`

```markdown
| Phase | Goal | Verification | Score |
| 1. ... | ... | PASSED | 5/5 truths |
```

Use same tabular truth/score style for BASE-01..04 check ledger rows.

**Analog C — live MCP tool inventory source:** `mcp_server/src/graphiti_mcp_server.py` (`@mcp.tool` registrations)

Legacy (14) — cite `file:line` from RESEARCH Pattern 1:

| Tool | ~line |
|------|------:|
| `add_memory` | 385 |
| `search_nodes` | 521 |
| `search_memory_facts` | 598 |
| `update_entity` | 678 |
| `delete_entity_edge` | 795 |
| `delete_episode` | 821 |
| `get_entity_edge` | 850 |
| `get_episodes` | 877 |
| `summarize_saga` | 947 |
| `build_communities` | 1000 |
| `add_triplet` | 1054 |
| `get_episode_entities` | 1128 |
| `clear_graph` | 1164 |
| `get_status` | 1207 |

Catalog (7):

| Tool | ~line |
|------|------:|
| `upsert_typed_entities` | 1240 |
| `resolve_typed_entities` | 1269 |
| `verify_catalog_batch` | 1294 |
| `upsert_typed_edges` | 1319 |
| `upsert_provenance` | 1349 |
| `get_catalog_ingest_status` | 1378 |
| `upsert_catalog_batch` | 1407 |

**Inventory command pattern** (RESEARCH / TESTING.md):

```bash
rg -n "@mcp\.tool" -A2 mcp_server/src/graphiti_mcp_server.py
# Total must equal 21 (14+7)
```

**Catalog surface map** (cite only; do not edit):

| Area | Paths |
|------|-------|
| Models | `mcp_server/src/models/catalog_{common,entities,edges,provenance,batch,responses}.py` |
| Identity | `mcp_server/src/services/catalog_identity.py` |
| Service | `mcp_server/src/services/catalog_service.py` |
| Store | `mcp_server/src/services/catalog_store.py` |
| Config | `mcp_server/src/config/schema.py` (`catalog_upsert`) |
| Tests | `mcp_server/tests/test_catalog_{models,identity,service,store_unit,neo4j_int,canary_scripts}.py` |
| Fixture | `mcp_server/tests/fixtures/accept_tab_sanitized.json` |
| Canary builder | `scripts/build_catalog_canary_requests.py` |
| Canary runner | `scripts/run_catalog_canary_batch.py` — **banned to execute** |
| Checkpoint | `catalog/catalog.json.graphiti-canary-v2-state.json` |
| Manifest | `catalog/canary-v2-requests/manifest.json` |
| Receipts | `catalog/canary-v2-requests/accept-tab.{payload,dry-run.response,commit.response}.json` |
| Archived scripts | `tests/script/{build,run}_catalog_canary_batch.py` |

**Pre-hardening identity material** (document gap only):

```python
# catalog_identity.py — pre-v2; Phase 1 adds identity_schema_version + system_key
str(uuid.uuid5(namespace, f'{group_id}|{entity_type}|{graph_key}'))
```

**Check reporting pattern** (RESEARCH Pattern 3 + `00-VALIDATION.md`):

| Field | Rule |
|-------|------|
| `status` | enum `pass` \| `fail` \| `skip` only |
| tool/DB missing | `skip`, never invent `pass` |
| fail | first node id / rule code (`tests/...::test_x`, `RUF100`) |
| Phase 0 | record only; do not repair product failures |

**Targeted non-destructive commands** (from `00-VALIDATION.md` / RESEARCH):

```bash
cd mcp_server
uv run pytest \
  tests/test_catalog_models.py \
  tests/test_catalog_identity.py \
  tests/test_catalog_service.py \
  tests/test_catalog_store_unit.py \
  tests/test_catalog_canary_scripts.py \
  -q --tb=line
uv run ruff check src/models/catalog_*.py src/services/catalog_*.py tests/test_catalog*.py
uv run pyright src/models src/services/catalog_identity.py src/services/catalog_service.py src/services/catalog_store.py
# Neo4j int only if up; else skip — NEVER oracle-catalog-v2
# uv run pytest tests/test_catalog_neo4j_int.py -q --tb=line
```

**MCP test runner analog:** `.planning/codebase/TESTING.md` — `cd mcp_server && uv run pytest`; package suite separate from root `make test`.

---

### `00-COMPATIBILITY-POLICY.md` (policy, contract freeze)

**Analog:** `.claude/CLAUDE.md` Project Constraints + `.planning/REQUIREMENTS.md` SAFE-09, IDEN-12, IDEN-13

**Compatibility bullets to freeze (copy intent, not product code):**

```text
- Preserve every existing MCP tool and behavior — additive only later
- Preserve 14 legacy tool names and public contracts (SAFE-09)
- Preserve 7 catalog tool names registered
- Catalog-v2 request identity, provenance, hash contracts may break catalog-v1 payloads explicitly
- Never silently reinterpret/normalize/migrate/rewrite catalog-v1 as catalog-v2 (IDEN-12)
- ACCEPT_TAB hashes/receipts/38e-85r plan = historical only; invalid for hardened v2 goldens (IDEN-13)
- Caller UUIDs never identity authority; server UUIDv5 + fixed GRAPHITI_CATALOG_UUID_NAMESPACE
```

**Deprecation disposition table pattern** (mirror REQUIREMENTS IDEN-13 wording):

| Artifact | Disposition |
|----------|-------------|
| `ACCEPT_TAB_GOLDEN` request SHA `a84e8a7a...` | historical evidence; not future golden |
| artifact SHA `a89e3427...` | historical |
| 10e/16r/1-source commit receipt | historical offline only |
| 38/85 plan | historical; builders regenerate later without executing |
| `oracle-catalog-v2` graph state | inventory offline only; never query/mutate in v1.1 |

**Do not** import pre-hardening golden constants into Phase 1+ tests as still-valid goldens.

---

### `00-ISOLATION-POLICY.md` (policy, isolation + repo safety)

**Analog A:** `.claude/CLAUDE.md` Isolation / Operations / Logging

```text
- Tests/dev writes: only `oracle-catalog-tool-test`
- Never live-group writes, full ingest, graph clear, existing-data deletion
- Log batch IDs and counts only — never credentials/payloads/source text
- No deployment from this milestone work
```

**Analog B — dirty-tree concern:** `.planning/codebase/CONCERNS.md` “Dirty working tree / fork-specific deploy config”

```text
Uncommitted mcp_server/k8s/graphiti-neo4j.yaml, sample_catalog.json, .codegraph/
→ exclude from task commits; env-specific topology risk
```

**Analog C — group constants in canary (document ban, do not run):**

- Builder/runner live target: `oracle-catalog-v2` (`scripts/build_catalog_canary_requests.py`, `scripts/run_catalog_canary_batch.py`)
- Offline tests / unit fixtures: `oracle-catalog-tool-test` (`mcp_server/tests/test_catalog_*.py`)

**Isolation policy must state:**

| Rule | Enforcement |
|------|-------------|
| SAFE-01 | Write/test group = `oracle-catalog-tool-test` only; v2 offline inventory only |
| SAFE-02 | Never invoke `scripts/run_catalog_canary_batch.py` (incl. dry-run); checkpoint `attempts` must not grow |
| SAFE-12 | Commit allowlist: only `.planning/phases/00-baseline-inventory-and-compatibility-policy/` (+ STATE/ROADMAP if required) |
| SAFE-13 | No push/merge/deploy/tag/remote |

**Dirty-tree exclude list** (RESEARCH + git status):

- `.planning/config.json`
- `mcp_server/config/config-docker-neo4j.yaml`
- `mcp_server/k8s/graphiti-neo4j.yaml`
- `.codegraph/`
- untracked `catalog/*` enrichment dumps
- `mcp_server/sample_catalog.json`

**Canary-ban verification pattern** (RESEARCH Don't Hand-Roll):

```text
Assert plan/history has no run_catalog_canary_batch invoke
Assert catalog/catalog.json.graphiti-canary-v2-state.json attempts unchanged
Assert no Neo4j session against oracle-catalog-v2
```

---

### `00-baseline-checks.json` (optional ledger)

**Analog:** `00-VALIDATION.md` Per-Task Verification Map + RESEARCH check object schema

```json
{
  "checks": [
    {
      "name": "catalog-unit-offline",
      "command": "cd mcp_server && uv run pytest tests/test_catalog_models.py ... -q --tb=line",
      "status": "pass|fail|skip",
      "exit_code": 0,
      "first_failure_id": null,
      "notes": ""
    }
  ],
  "canary_executed": false,
  "oracle_catalog_v2_queried": false
}
```

## Shared Patterns

### Live-source inventory with line anchors
**Source:** RESEARCH Pattern 1; `graphiti_mcp_server.py` `@mcp.tool`
**Apply to:** `00-BASELINE.md` tool tables
- Grep registration, not memory; total 21 tools.

### Offline historical evidence only
**Source:** `catalog/CANARY_V2_SUMMARY.md`, checkpoint, manifest, accept-tab receipts
**Apply to:** BASE-02 ACCEPT_TAB section
- Paths + digests + counts; no Neo4j; no runner.

### Truthful pass/fail/skip
**Source:** RESEARCH Pattern 3; `00-VALIDATION.md`
**Apply to:** BASE-03/04 ledger and optional JSON
- Unavailable = skip; raw failure identity preserved; no Phase 0 product fixes.

### Group isolation
**Source:** `.claude/CLAUDE.md`; catalog tests; canary scripts constants
**Apply to:** `00-ISOLATION-POLICY.md`
- Dev/test: `oracle-catalog-tool-test`
- Historical canary group: `oracle-catalog-v2` (read artifacts only)

### Commit allowlist / dirty-tree
**Source:** `CONCERNS.md`; RESEARCH dirty-worktree allowlist
**Apply to:** every Phase 0 commit step
- Stage only phase dir files.

### Compatibility freeze without silent migration
**Source:** REQUIREMENTS SAFE-09, IDEN-12/13; CLAUDE Compatibility
**Apply to:** `00-COMPATIBILITY-POLICY.md`
- Names frozen; payload contracts may break explicitly; no v1→v2 rewrite.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | All Phase 0 artifacts map to existing summary/audit/policy/test patterns |

Product-code analogs (for later phases only — **do not implement in Phase 0**):

| Surface | Path |
|---------|------|
| Catalog models | `mcp_server/src/models/catalog_*.py` |
| Identity | `mcp_server/src/services/catalog_identity.py` |
| Service/store | `catalog_service.py`, `catalog_store.py` |
| Config | `mcp_server/src/config/schema.py` |
| Offline canary tests | `mcp_server/tests/test_catalog_canary_scripts.py` |

## Metadata

**Analog search scope:** `.planning/`, `catalog/`, `mcp_server/src/`, `mcp_server/tests/`, `scripts/`, `.claude/CLAUDE.md`, `REQUIREMENTS.md`
**Files scanned:** ~25 key docs/scripts + catalog canary tree
**Pattern extraction date:** 2026-07-18
**Bans preserved:** no canary execution; no `oracle-catalog-v2` query/mutation; no remote ops; no unrelated dirty commits; no product code edits
