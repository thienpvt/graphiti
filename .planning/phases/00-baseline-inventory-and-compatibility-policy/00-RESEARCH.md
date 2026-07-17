# Phase 0: Baseline, Inventory, and Compatibility Policy - Research

**Researched:** 2026-07-18
**Domain:** Documentation / inventory / isolation policy (no product code change)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Baseline Evidence
- Treat current source and tests as authority for the 14 legacy MCP tools, seven catalog tools, catalog models/services/store/schema, and canary workflow inventory.
- Treat repository receipts, checkpoints, requests, and tests as offline historical evidence only.
- Record the pre-hardening ACCEPT_TAB result without querying Neo4j or retrying the canary.
- Keep inventory reproducible through file/symbol references and exact check commands.

#### Test and Check Reporting
- Run targeted catalog, canary-workflow, compatibility, Ruff, and Pyright checks when locally available.
- Report each check as pass, fail, or skip; never convert unavailable checks into passes.
- Preserve raw failure identity sufficiently to distinguish pre-existing failures from later v1.1 regressions.
- Do not repair unrelated baseline failures in Phase 0.

#### Compatibility Boundary
- Preserve names and public contracts for all 14 legacy MCP tools.
- Preserve all seven existing catalog tool names while documenting that catalog-v2 request identity, provenance, and hash contracts intentionally break catalog-v1 payload compatibility.
- Never silently reinterpret, normalize, migrate, or rewrite catalog-v1 identity as catalog-v2.
- Preserve historical hashes and receipts as invalid-for-v2 evidence rather than reusable golden values.

#### Isolation and Repository Safety
- New tests and any permitted development writes use only `oracle-catalog-tool-test`.
- Never query or mutate `oracle-catalog-v2`; never execute the real canary.
- Preserve unrelated dirty-worktree files; task commits include only intentional phase files.
- Do not push, merge, deploy, tag, clear graph data, or delete existing data.

### Claude's Discretion
- Choose the smallest auditable baseline artifact structure and exact non-destructive check subset consistent with the requirements.

### Deferred Ideas (OUT OF SCOPE)
- Catalog-v2 contract and identity changes begin in Phase 1.
- Real canary execution remains Phase 6 under separate approval.
- Automatic catalog-v1 migration remains out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BASE-01 | Recorded baseline inventory of 14 legacy MCP tools, 7 catalog tools, catalog models/services/store/schema, canary builder/runner/fixtures/receipts/checkpoint/offline tests | Live registration map + file inventory below |
| BASE-02 | Baseline findings grounded in live source/tests and committed canary evidence; historical ACCEPT_TAB dry-run/commit offline only | Offline ACCEPT_TAB evidence table; no Neo4j query |
| BASE-03 | Distinguish pre-existing catalog/canary/compatibility test failures from v1.1 regressions | Targeted pytest command set + raw-failure capture format |
| BASE-04 | Distinguish pre-existing Ruff/Pyright failures; unavailable checks = skip; record catalog-v1 deprecation boundary | Check availability matrix + compatibility policy section |
| SAFE-01 | Dev writes only `oracle-catalog-tool-test`; inventory `oracle-catalog-v2` offline only | Isolation policy; group_id map |
| SAFE-02 | Never execute real catalog canary | Explicit canary-ban in plan/check list |
| SAFE-12 | Unrelated dirty-worktree files unmodified | Dirty-tree inventory; commit allowlist |
| SAFE-13 | No push/merge/deploy/tag/remote state change | Remote-safety policy |
</phase_requirements>

## Summary

Phase 0 is a **read-only baseline + policy** phase. No catalog-v2 contract, identity, store, or canary code changes. Deliverable is a small set of planning artifacts under `.planning/phases/00-baseline-inventory-and-compatibility-policy/` that (1) inventory live MCP/catalog/canary surfaces with file/symbol anchors, (2) record offline ACCEPT_TAB historical evidence, (3) run a non-destructive check subset and report pass/fail/skip with raw failure identity, and (4) freeze isolation + catalog-v1 deprecation policy for later phases.

Live source already registers **exactly 14 legacy tools** and **exactly 7 catalog tools** on `FastMCP` in `mcp_server/src/graphiti_mcp_server.py`. Catalog domain code is modular under `mcp_server/src/models/catalog_*.py`, `services/catalog_{identity,service,store}.py`. Canary workflow is cherry-picked under `scripts/`, `catalog/canary-v2-requests/`, `catalog/catalog.json.graphiti-canary-v2-state.json`, offline tests in `mcp_server/tests/test_catalog_canary_scripts.py`. ACCEPT_TAB dry-run and commit receipts exist on disk; **do not re-run runner or query Neo4j**.

**Primary recommendation:** Emit three small markdown artifacts (`00-BASELINE.md`, `00-COMPATIBILITY-POLICY.md`, `00-ISOLATION-POLICY.md`) plus optional machine-readable `00-baseline-checks.json`; run only the non-destructive mcp_server catalog/canary/Ruff/Pyright subset; commit only phase artifacts; never touch canary scripts against live MCP or `oracle-catalog-v2`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tool inventory (legacy + catalog) | Docs / planning artifact | MCP registration source | Read-only map of FastMCP registrations; no runtime change |
| Catalog code/schema inventory | Docs / planning artifact | `mcp_server/src/models|services` | File/symbol citations only |
| Canary offline inventory | Docs / planning artifact | `scripts/`, `catalog/`, tests | Historical evidence from git-tracked artifacts |
| Pre-existing failure baseline | Local CLI checks | pytest / ruff / pyright | Capture pass/fail/skip before Phase 1 |
| Isolation / group policy | Docs / planning artifact | Test constants + CLAUDE.md | Policy freezes write target |
| Compatibility / deprecation boundary | Docs / planning artifact | Catalog models + canary hashes | Records intentional v1→v2 break without code change |
| Worktree / remote safety | Git workflow | Agent commit allowlist | SAFE-12/13 operational controls |

## Project Constraints (from CLAUDE.md)

Actionable directives relevant to Phase 0:

- Preserve every existing MCP tool and behavior (additive only in later phases).
- Neo4j first; no multi-backend catalog portability claim.
- Tests/development writes use only `oracle-catalog-tool-test`.
- Never interpolate unvalidated client labels/property names into Cypher (later phases).
- Log batch IDs and counts only — never credentials/payloads/source text.
- No deployment, live-group writes, full ingest, graph clearing, or existing-data deletion.
- MCP package: Ruff line-length 100, single quotes; Pyright `basic`; pytest-asyncio auto.
- Catalog canary must not execute in this milestone (Phase 6 separate).
- Dirty deploy/config files (k8s, docker yaml, sample catalog, `.codegraph/`) are unrelated and must not be committed casually.

## Standard Stack

### Core

| Library / Tool | Version (verified) | Purpose | Why Standard |
|----------------|-------------------|---------|--------------|
| Python | 3.12.10 local (project `>=3.10,<4`) | Runtime | Project pin |
| uv | present (user path) | Env + tool runner | Project single source of truth |
| pytest | 9.0.3 (`mcp_server` dev) | Targeted catalog/canary unit suite | Existing mcp_server runner |
| ruff | 0.15.18 (`uv run` in mcp_server) | Lint/format gate | Project standard |
| pyright | 1.1.408 (`uv run` in mcp_server) | Type gate | Project standard |
| mcp FastMCP | `mcp>=1.27.2,<2` | Tool registration surface | Already installed |
| Pydantic | `>=2.11.5` (core) / via mcp_server deps | Catalog request models | Existing models |

### Supporting

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `git status` / path allowlist | SAFE-12 commit hygiene | Every task commit |
| Offline file SHA (optional `sha256sum` / Python hashlib) | Reconfirm artifact digests match receipts | BASE-02 verification without Neo4j |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Three policy markdown files | One mega `00-BASELINE.md` | Single file is smaller; three files separate inventory vs policy for later phase citation — prefer three short files |
| Live Neo4j ACCEPT_TAB re-verify | Offline receipts only | Live re-verify violates SAFE-01/02; offline is required |
| Full `make check` | Targeted catalog subset | Full suite is noisy for baseline; targeted set isolates catalog pre-existing failures |

**Installation:** none — Phase 0 installs no packages.

**Version verification:** local `uv run` in `mcp_server/` returned ruff 0.15.18, pyright 1.1.408, pytest 9.0.3 on 2026-07-18. [VERIFIED: local uv run]

## Package Legitimacy Audit

No external packages recommended for install in Phase 0.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — | — | — | — | — | — | N/A |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
[Maintainer / Phase-0 executor]
        |
        v
[Read-only inventory]
  |-- graphiti_mcp_server.py  (@mcp.tool registrations)
  |-- models/catalog_*.py
  |-- services/catalog_{identity,service,store}.py
  |-- config/schema.py (catalog_upsert settings)
  |-- scripts/build|run_catalog_canary_*.py
  |-- catalog/canary-v2-requests/* + checkpoint + CANARY_V2_SUMMARY.md
  |-- mcp_server/tests/test_catalog_*.py
        |
        v
[Non-destructive checks]
  |-- pytest catalog unit + canary offline
  |-- ruff check catalog paths
  |-- pyright catalog paths
  |-- skip if tool/DB unavailable (never invent pass)
        |
        v
[Planning artifacts only]
  |-- 00-BASELINE.md (+ optional JSON)
  |-- 00-COMPATIBILITY-POLICY.md
  |-- 00-ISOLATION-POLICY.md
        |
        X  no Neo4j query to oracle-catalog-v2
        X  no run_catalog_canary_batch live
        X  no product code edit
        X  no push/merge/deploy/tag
```

### Recommended Project Structure (phase outputs)

```text
.planning/phases/00-baseline-inventory-and-compatibility-policy/
├── 00-CONTEXT.md                 # already exists
├── 00-RESEARCH.md                # this file
├── 00-BASELINE.md                # inventory + check results (create in execute)
├── 00-COMPATIBILITY-POLICY.md    # catalog-v1 deprecation / tool-name freeze
├── 00-ISOLATION-POLICY.md        # group_id / canary ban / worktree / remote
└── 00-baseline-checks.json       # optional machine-readable pass|fail|skip
```

### Pattern 1: Live-source inventory with line anchors

**What:** Enumerate tools by grepping `@mcp.tool()` then the following `async def` name; cite `file:line`.
**When to use:** BASE-01 tool inventory.
**Example:**

```text
# Legacy (14) — mcp_server/src/graphiti_mcp_server.py
add_memory              :385
search_nodes            :521
search_memory_facts     :598
update_entity           :678
delete_entity_edge      :795
delete_episode          :821
get_entity_edge         :850
get_episodes            :877
summarize_saga          :947
build_communities       :1000
add_triplet             :1054
get_episode_entities    :1128
clear_graph             :1164
get_status              :1207

# Catalog (7)
upsert_typed_entities      :1240
resolve_typed_entities     :1269
verify_catalog_batch       :1294
upsert_typed_edges         :1319
upsert_provenance          :1349
get_catalog_ingest_status  :1378
upsert_catalog_batch       :1407
```

[VERIFIED: codebase grep of graphiti_mcp_server.py]

### Pattern 2: Offline historical evidence only

**What:** Cite committed JSON/MD paths and digests; never open Neo4j session for `oracle-catalog-v2`.
**When to use:** BASE-02 ACCEPT_TAB record.
**Authoritative offline sources:**

| Artifact | Path | Role |
|----------|------|------|
| Summary | `catalog/CANARY_V2_SUMMARY.md` | Human status narrative |
| Checkpoint | `catalog/catalog.json.graphiti-canary-v2-state.json` | Attempts + batch statuses |
| Manifest | `catalog/canary-v2-requests/manifest.json` | Planned 38e/85r + golden hash |
| Dry-run receipt | `catalog/canary-v2-requests/accept-tab.dry-run.response.json` | Dry-run response |
| Commit receipt | `catalog/canary-v2-requests/accept-tab.commit.response.json` | Commit response |
| Payload | `catalog/canary-v2-requests/accept-tab.payload.json` | Immutable request |
| Builder | `scripts/build_catalog_canary_requests.py` | Artifact generator (`GROUP_ID='oracle-catalog-v2'`) |
| Runner | `scripts/run_catalog_canary_batch.py` | Live executor — **do not run** |
| Offline tests | `mcp_server/tests/test_catalog_canary_scripts.py` | Safe offline coverage |
| Sanitized fixture | `mcp_server/tests/fixtures/accept_tab_sanitized.json` | Unit fixture (not live group) |
| Archived scripts | `tests/script/{build,run}_catalog_canary_batch.py` | Historical copies |

### Pattern 3: Truthful pass/fail/skip reporting

**What:** Each check records `{name, command, status: pass|fail|skip, exit_code?, first_failure_id?, notes}`.
**When to use:** BASE-03/04.
**Rules:**
- Tool missing → `skip` (not pass).
- Neo4j live int unavailable → `skip` for `test_catalog_neo4j_int.py`.
- Failures: store first failing node id / rule code (e.g. `tests/test_catalog_models.py::test_x` or `RUF100`).
- Do not fix failures in Phase 0.

### Anti-Patterns to Avoid

- **Re-running canary "to refresh baseline":** violates SAFE-02; receipts already exist.
- **Querying `oracle-catalog-v2` to confirm commit:** violates SAFE-01; use offline receipts.
- **Marking skipped checks as green:** corrupts BASE-03/04 regression detection.
- **Committing dirty k8s/docker/catalog/config files with baseline docs:** violates SAFE-12.
- **Editing catalog models "while documenting":** Phase 1+ only.
- **Treating ACCEPT_TAB golden SHA as future v2 golden:** IDEN-13 / compatibility policy forbids reuse after hardening.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tool list discovery | Manual memory of tool names | `@mcp.tool` grep / line anchors | Registration is source of truth |
| ACCEPT_TAB verification | Custom Neo4j Cypher | Offline JSON receipts + summary | Safe, deterministic, no live group |
| Failure baseline format | Free-form prose only | Structured pass/fail/skip table (+ optional JSON) | Later phases need machine-diffable identity |
| Worktree protection | Hope | Explicit commit `--files` allowlist | Dirty tree contains deploy secrets/topology |
| Canary ban enforcement | Comment only | Plan verification step that asserts runner was not invoked + no new checkpoint attempts | Executable safety |

**Key insight:** Phase 0 value is **frozen evidence**, not new machinery. Prefer markdown + one JSON snapshot over scripts that mutate state.

## Runtime State Inventory

> Not a rename phase, but isolation requires explicit group/runtime awareness.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | Historical ACCEPT_TAB domain write claimed in `oracle-catalog-v2` (offline evidence only). Test group constant `oracle-catalog-tool-test` used in unit tests. | **No migration.** Never query/mutate either live group in Phase 0. |
| Live service config | Dirty `mcp_server/k8s/graphiti-neo4j.yaml`, `mcp_server/config/config-docker-neo4j.yaml` (unrelated). | **Leave untouched** (SAFE-12). |
| OS-registered state | None verified for catalog canary. | None |
| Secrets/env vars | Standard `NEO4J_*`, `OPENAI_API_KEY`, `GRAPHITI_CATALOG_UUID_NAMESPACE` (config). | Do not log values; no key renames. |
| Build artifacts | Untracked `catalog/*` enrichment dumps, `.codegraph/`, `mcp_server/sample_catalog.json` may exist dirty. | Exclude from phase commits. |

**Nothing found requiring data migration:** Phase 0 writes only planning docs.

### Dirty-worktree allowlist (SAFE-12)

Do **not** stage unless separately approved:

- `.planning/config.json` (modified)
- `mcp_server/config/config-docker-neo4j.yaml` (modified)
- `mcp_server/k8s/graphiti-neo4j.yaml` (modified)
- `.codegraph/` (untracked)
- `catalog/` bulk enrichment dumps (untracked except known canary artifacts already committed historically)
- `mcp_server/sample_catalog.json` (untracked)

**Phase 0 commit allowlist:** only files under `.planning/phases/00-baseline-inventory-and-compatibility-policy/` (and STATE/ROADMAP updates if planner requires).

## Common Pitfalls

### Pitfall 1: Counting tools wrong
**What goes wrong:** Inventory reports 13 or 15 legacy tools.
**Why it happens:** Confusing catalog tools with legacy; missing `get_episode_entities` / `summarize_saga`.
**How to avoid:** Count `@mcp.tool` defs; split by line number boundary (catalog starts ~1240).
**Warning signs:** Total ≠ 21 (14+7).

### Pitfall 2: Live canary "just dry-run"
**What goes wrong:** Runner still contacts MCP and may write checkpoint attempts.
**Why it happens:** Dry-run feels safe.
**How to avoid:** Treat entire `scripts/run_catalog_canary_batch.py` as banned in Phase 0; offline tests only.
**Warning signs:** New entries under `catalog/catalog.json.graphiti-canary-v2-state.json` `attempts`.

### Pitfall 3: Converting skip → pass
**What goes wrong:** Later phases cannot detect regressions.
**Why it happens:** Desire for green baseline report.
**How to avoid:** Schema enforces enum `pass|fail|skip`; unavailable = skip.
**Warning signs:** Report says "all green" while Neo4j was down.

### Pitfall 4: Fixing baseline Ruff/Pyright noise
**What goes wrong:** Scope creep into product code; pollutes regression signal.
**Why it happens:** Auto-fix habits.
**How to avoid:** Explicit CONTEXT decision: do not repair unrelated baseline failures.
**Warning signs:** Diff outside `.planning/phases/00-...`.

### Pitfall 5: Reusing ACCEPT_TAB hashes as future goldens
**What goes wrong:** Hardened catalog-v2 identity/hash recipe will not match; false failures or silent acceptance pressure.
**Why it happens:** Convenience of existing digests.
**How to avoid:** Compatibility policy marks hashes historical/invalid-for-hardened-v2 (IDEN-13).
**Warning signs:** Phase 1+ tests import `ACCEPT_TAB_GOLDEN_REQUEST_SHA256` as still-valid golden.

### Pitfall 6: Accidental remote operations
**What goes wrong:** push/tag from worktree automation.
**How to avoid:** SAFE-13 ban in isolation policy; GSD commit local-only.
**Warning signs:** `git push` in plan steps.

## Code Examples

### Enumerate MCP tools (read-only)

```bash
# From repo root — inventory only
rg -n "@mcp\.tool" -A2 mcp_server/src/graphiti_mcp_server.py
```

### Targeted non-destructive check subset [ASSUMED exact flags OK; refine if local paths differ]

```bash
cd mcp_server

# Unit catalog + offline canary (no live canary, no v2 group writes)
uv run pytest \
  tests/test_catalog_models.py \
  tests/test_catalog_identity.py \
  tests/test_catalog_service.py \
  tests/test_catalog_store_unit.py \
  tests/test_catalog_canary_scripts.py \
  -q --tb=line

# Lint / types on catalog surface only
uv run ruff check src/models/catalog_*.py src/services/catalog_*.py tests/test_catalog*.py
uv run pyright src/models src/services/catalog_identity.py src/services/catalog_service.py src/services/catalog_store.py

# Live Neo4j int — run only if Neo4j up; else record skip
# NEVER point at oracle-catalog-v2
# uv run pytest tests/test_catalog_neo4j_int.py -q --tb=line
```

### Offline ACCEPT_TAB facts to record (from repo artifacts)

| Field | Value | Source |
|-------|-------|--------|
| target_group_id | `oracle-catalog-v2` | manifest / CANARY_V2_SUMMARY |
| catalog_sha256 | `3882cb4bc50064215ead782b0fa0dfbf0098cb344b50184e6c207145377e832f` | manifest |
| ACCEPT_TAB batch_id | `canary-v2::accept-tab` | checkpoint / runner EXPECTED_BATCHES |
| artifact_sha256 | `a89e3427a3b1ceec10f36d361fcdbe9e7e30243db4ff51ca59848dfb33968a33` | runner / summary |
| server_request_sha256 | `a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a` | runner / summary / checkpoint |
| dry-run counts | 10 entities created, 16 edges, 1 provenance source, 0 failed | checkpoint attempts[0] |
| planned unique totals | 38 entities, 85 edges | manifest / summary |
| post-commit note | Domain commit claimed; post-commit verification/search gate hit DateTime serialization issue | CANARY_V2_SUMMARY |
| v1.1 disposition | Historical only; invalid as hardened catalog-v2 golden; never query/mutate group | REQUIREMENTS IDEN-13, SAFE-01 |

[VERIFIED: catalog/CANARY_V2_SUMMARY.md, catalog/canary-v2-requests/manifest.json, catalog/catalog.json.graphiti-canary-v2-state.json, scripts/run_catalog_canary_batch.py]

### Catalog surface file map

| Area | Paths |
|------|-------|
| Models | `mcp_server/src/models/catalog_{common,entities,edges,provenance,batch,responses}.py` |
| Identity | `mcp_server/src/services/catalog_identity.py` — UUIDv5 `group_id|entity_type|graph_key` (pre-v2 material; Phase 1 will version) |
| Service | `mcp_server/src/services/catalog_service.py` |
| Store | `mcp_server/src/services/catalog_store.py` |
| Config | `mcp_server/src/config/schema.py` (`catalog_upsert` settings) |
| Tests | `mcp_server/tests/test_catalog_{models,identity,service,store_unit,neo4j_int,canary_scripts}.py` |
| Allowlists | `catalog_common.py`: 15 entity prefixes, 16 edge types, limits, error codes |

Current identity material (pre-hardening) [VERIFIED: catalog_identity.py]:

```python
# group_id|entity_type|graph_key  — catalog-v2 will add identity_schema_version + system_key (Phase 1)
str(uuid.uuid5(namespace, f'{group_id}|{entity_type}|{graph_key}'))
```

Current model gaps vs Phase 1 contracts (document only, do not fix):

- `strict_endpoints` / `atomic` on some requests are plain `bool` defaults, not `Literal[True]` everywhere (`catalog_edges.py` still has `strict_endpoints: bool = True`) [VERIFIED: catalog_edges.py]
- No `identity_schema_version` / `system_key` fields yet (Phase 1)
- Provenance still multi-target Cartesian shape in fixtures (`accept_tab_sanitized.json` entity_targets/edge_targets arrays) [VERIFIED: fixtures]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual nested catalog tool calls | Immutable canary builder + runner + offline tests | 2026-07-17 canary workflow commit `9d53860` | Deterministic artifacts; still pre-hardening identity |
| Catalog-v1 graph keys as production goldens | Explicit deprecation before v2 hardening | v1.1 Phase 0 policy | Hashes/receipts become historical evidence only |
| Live ACCEPT_TAB re-verify for planning | Offline receipts only | Phase 0 constraint | SAFE-01/02 compliance |

**Deprecated/outdated for v1.1 planning:**

- Treating `ACCEPT_TAB_GOLDEN_REQUEST_SHA256` as future regression golden after identity/hash recipe changes.
- Assuming `strict_endpoints=false` or `atomic=false` remain acceptable (Phase 1 forbids).
- Cartesian provenance multi-target arrays (Phase 2 evidence contract replaces).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Three short policy/baseline markdown files is preferred over one mega file | Architecture | Planner may collapse to one file — low risk |
| A2 | Targeted pyright on catalog service modules is sufficient baseline (not whole mcp_server) | Validation | May miss pre-existing errors outside catalog paths — mitigate by noting scope in baseline |
| A3 | `test_catalog_neo4j_int.py` should default to skip unless Neo4j explicitly available | Checks | If always run and fails env, still record as fail/skip honestly |
| A4 | Checkpoint status nuance (dry-run pass + commit verification failure) is the correct historical story, not a clean full success | ACCEPT_TAB evidence | Mis-stating success could mislead Phase 5 report — cite summary verbatim |

## Open Questions

1. **Should baseline JSON be required or optional?**
   - What we know: markdown satisfies human review (BASE-01–04).
   - What's unclear: whether later automation wants machine-readable checks.
   - Recommendation: optional `00-baseline-checks.json`; markdown is mandatory.

2. **Exact pyright include path for baseline**
   - What we know: `[tool.pyright] include = ["src", "tests"]` in mcp_server.
   - What's unclear: full-tree pyright may be slow/noisy.
   - Recommendation: run full `uv run pyright` if cheap; else scoped modules + document scope.

3. **Whether dirty canary artifacts under untracked `catalog/` differ from committed canary-v2-requests**
   - What we know: committed canary artifacts exist; many untracked catalog dumps also present.
   - Recommendation: inventory only committed/known canary paths listed above; ignore enrichment dumps.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | checks | ✓ | 3.12.10 | — |
| uv | run pytest/ruff/pyright | ✓ | present | — |
| pytest (mcp_server) | BASE-03 | ✓ | 9.0.3 | skip catalog tests |
| ruff | BASE-04 | ✓ | 0.15.18 | skip lint check |
| pyright | BASE-04 | ✓ | 1.1.408 | skip type check |
| Neo4j live | optional int test | unknown | — | **skip** `test_catalog_neo4j_int` |
| MCP server live URL | canary runner | must not use | — | **banned** |
| Network push remote | none | N/A | — | **banned** |

**Missing dependencies with no fallback:** none for Phase 0 core (docs + offline checks).

**Missing dependencies with fallback:** Neo4j → skip integration test.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio (mcp_server) |
| Config file | `mcp_server/tests/pytest.ini` |
| Quick run command | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py tests/test_catalog_service.py tests/test_catalog_store_unit.py tests/test_catalog_canary_scripts.py -q --tb=line` |
| Full suite command | `cd mcp_server && uv run pytest` (not required for Phase 0 gate) |
| Lint | `cd mcp_server && uv run ruff check src/models/catalog_*.py src/services/catalog_*.py tests/test_catalog*.py` |
| Types | `cd mcp_server && uv run pyright` (or scoped catalog modules) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| BASE-01 | Inventory lists 14+7 tools and catalog/canary paths | manual/doc assert | Review `00-BASELINE.md` vs `rg @mcp.tool` | ❌ Wave 0 doc |
| BASE-02 | ACCEPT_TAB offline facts recorded | manual/doc assert | Diff baseline table vs `CANARY_V2_SUMMARY.md` + checkpoint | ❌ Wave 0 doc |
| BASE-03 | Catalog/canary test results pass\|fail\|skip with failure ids | automated + record | Quick pytest command above | ✅ tests exist; ❌ baseline record |
| BASE-04 | Ruff/Pyright pass\|fail\|skip; compatibility policy written | automated + doc | ruff + pyright commands; policy file | ❌ Wave 0 doc |
| SAFE-01 | Policy + baseline state no v2 query | manual/policy + grep plan | Assert plan has no `oracle-catalog-v2` query step; tests keep tool-test group | ❌ Wave 0 policy |
| SAFE-02 | Canary not executed | manual/policy | Assert plan has no `run_catalog_canary_batch` invoke; checkpoint attempts unchanged | ❌ Wave 0 policy |
| SAFE-12 | Commit allowlist only phase files | git verify | `git status` / commit `--files` phase dir only | operational |
| SAFE-13 | No remote ops | git verify | Plan contains no push/merge/tag/deploy | operational |

### Sampling Rate

- **Per task commit:** re-read `git status`; ensure only phase allowlist staged
- **Per wave merge:** re-run quick pytest + ruff (record, don't fix)
- **Phase gate:** `00-BASELINE.md` + both policy files present; checks table complete; `canary_executed` effectively false; no v2 mutation

### Wave 0 Gaps

- [ ] `00-BASELINE.md` — inventory + check results (execute phase creates)
- [ ] `00-COMPATIBILITY-POLICY.md` — v1 deprecation / tool-name freeze
- [ ] `00-ISOLATION-POLICY.md` — group_id / canary ban / worktree / remote
- [ ] optional `00-baseline-checks.json` — machine-readable results
- [ ] No new product test files required for Phase 0

*(Existing `test_catalog_*.py` cover product behavior; Phase 0 validates process/docs, not new unit tests.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 0 docs only |
| V3 Session Management | no | — |
| V4 Access Control | yes (data isolation policy) | `group_id` isolation; write target `oracle-catalog-tool-test` only |
| V5 Input Validation | partial | Do not weaken allowlists; no new inputs |
| V6 Cryptography | no new | Historical SHA-256 digests treated as evidence IDs, not secrets |
| V7 Error Handling | yes (reporting) | Failures recorded without payload dumps |
| V9 Communications | yes | No live canary HTTP to MCP for baseline refresh |
| V10 Malicious Code | yes (supply chain) | No new packages; no postinstall risk |
| V14 Configuration | yes | Do not commit dirty deploy configs |

### Known Threat Patterns for this phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Accidental live-group write | Tampering | SAFE-01 ban; offline inventory only |
| Canary execution during baseline | Tampering / DoS | SAFE-02 ban; no runner invoke |
| Committing env-specific k8s/secrets | Information Disclosure | SAFE-12 dirty-tree allowlist |
| Logging full catalog payloads into baseline | Information Disclosure | Cite hashes/paths/counts only |
| Treating skip as pass | Spoofing of quality signal | Explicit skip enum |
| Remote push from agent | Elevation / Integrity | SAFE-13 ban |

## Sources

### Primary (HIGH confidence)

- `mcp_server/src/graphiti_mcp_server.py` — all `@mcp.tool` registrations (lines cited)
- `mcp_server/src/models/catalog_*.py`, `services/catalog_*.py` — catalog surface
- `scripts/build_catalog_canary_requests.py`, `scripts/run_catalog_canary_batch.py` — canary workflow
- `catalog/CANARY_V2_SUMMARY.md`, `catalog/canary-v2-requests/manifest.json`, `catalog/catalog.json.graphiti-canary-v2-state.json` — ACCEPT_TAB offline evidence
- `mcp_server/tests/test_catalog_*.py` — test inventory
- `.planning/REQUIREMENTS.md`, `ROADMAP.md`, `00-CONTEXT.md` — phase constraints
- Local `uv run` tool versions (ruff/pyright/pytest)

### Secondary (MEDIUM confidence)

- `.planning/codebase/{TESTING,CONCERNS,STRUCTURE}.md` — established check patterns and dirty-tree concerns

### Tertiary (LOW confidence)

- Assumed optimal artifact split into three markdown files (A1)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — local tools verified; no new deps
- Architecture: HIGH — live registration and canary paths verified in tree
- Pitfalls: HIGH — derived from explicit SAFE/BASE requirements and observed dirty tree

**Research date:** 2026-07-18
**Valid until:** 2026-08-17 (or until MCP tool registrations / canary artifacts change)
