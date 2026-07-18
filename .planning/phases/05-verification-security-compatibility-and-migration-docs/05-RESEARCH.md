# Phase 5: Verification, Security, Compatibility, and Migration Docs - Research

**Researched:** 2026-07-19
**Domain:** Pre-canary readiness gates — security matrix, compatibility proof, live isolation, offline canary-artifact migration, operator/migration docs, final report (no canary execution)
**Confidence:** HIGH

## Summary

Phase 5 is a **verification-and-documentation phase**, not a product-feature phase. Catalog-v2 prepare/commit, atomic co-commit, manifest-backed verify, split gates, and 28-tool registration are already product-complete through Phase 4 (`ready_for_phase_5=true`, `manifest_verification=true`, `canary_executed=false`). Phase 5 must prove security prohibitions, compatibility, isolation, and migration readiness with truthful pass/fail/skip ledgers, ship two operator docs, offline-regenerate hardened canary artifacts under prepare/commit contracts, and emit a final machine-readable readiness report that always keeps `canary_executed=false`.

Primary implementation work is concentrated in: (1) exhaustive security/log-scrub/prohibition tests (SAFE-03/04/06/07, TEST-10), (2) live Neo4j isolation proofs when available (TEST-11), (3) consolidated gate ledger + REPT-01 report (TEST-12), (4) offline canary builder/runner migration to catalog-v2 prepare/commit without executing the runner (IDEN-13, DOCS-06), (5) operator + migration docs (DOCS-01..05). No new runtime packages. No deploy/push/remote/clear/delete. Never query or mutate `oracle-catalog-v2`. Never run `scripts/run_catalog_canary_batch.py` against live/MCP.

**Primary recommendation:** Clone Phase 4 gate-runner pattern into `catalog_phase5_gate_runner.py` + `05-GATE-RESULTS.json`; extend existing spy/static tests into a full prohibition matrix; offline-migrate canary builder goldens to prepare/commit + catalog-v2 identity without network/DB/LLM; expand README + add one migration guide; run local Ollama E2E on test group only when available.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Stop after truthful Phase 5 readiness. Never enter Phase 6 or execute a real canary. Final report always sets `canary_executed=false`.
- **D-02:** `ready_to_regenerate_canary=true` only when every **available** gate passes, every skip is availability-based (not silent failure), no unexplained internal failures remain, and no blocking review/security/goal gaps remain. Any runnable required failure blocks readiness.
- **D-03:** Unavailable live Neo4j (or other optional infra) → truthful skip with reason. Do not treat skip as pass. Do not require unavailable infrastructure unconditionally.
- **D-04:** No query or mutation of `oracle-catalog-v2`. That group may appear only in offline historical inventory or future-canary metadata (paths, digests, counts, receipts). Development and live DB tests use only `oracle-catalog-tool-test`.
- **D-05:** Preserve two-axis safety: current forbidden-access flags remain false; historical `a67789a` audit truth is retained and never rewritten. Historical ACCEPT_TAB SHA, 10/16/1 receipt, and 38/85 plan remain historical and invalid for hardened catalog-v2.
- **D-06:** No deploy, push, merge, tag, remote-state mutation, `clear_graph`, existing-data deletion, or non-Neo4j catalog portability claim.
- **D-07:** Preserve all 14 legacy MCP tools (names + public contracts) plus the current 14 catalog tools = **28 total**. Roadmap wording about “seven catalog names” protects the original seven names; it is **not** a cap on catalog surface. Prepare/commit is the preferred large-payload path; compatibility tools remain registered.
- **D-08:** Catalog-v2 request contracts may break catalog-v1 payloads **explicitly**; never silently reinterpret, normalize, re-key, or rewrite catalog-v1 as catalog-v2. No automatic in-place identity migration.
- **D-09:** Offline-regenerate hardened catalog-v2 canary artifacts under current identity, hash, evidence, manifest, and prepare+commit contracts. Regeneration is pure offline: no network, DB, MCP transport, LLM, queue, or embedding side effect.
- **D-10:** Harden the future runner (`scripts/run_catalog_canary_batch.py`) for prepare/commit-era contracts as needed, but **do not execute** it (including dry-run against live/MCP). Offline unit tests of builder/runner pure logic remain allowed.
- **D-11:** Historical goldens (pre-hardening ACCEPT_TAB request/catalog SHA, 10/16/1 receipt, 38/85 plan) must not be reused as hardened-v2 authority. New artifacts supersede them offline only; no graph rewrite or data deletion.
- **D-12:** Deterministic catalog paths never invoke prohibited Graphiti tools: `add_memory`, `add_triplet`, `update_entity`, `delete_entity_edge`, `delete_episode`, `clear_graph`, `build_communities` (and never implicit endpoint creation or community creation).
- **D-13:** Deterministic catalog paths never invoke LLM extraction, async queue ingestion, or external embedding/LLM/queue/network on commit (prepare may embed before control-plane persist per SAFE-11 foundation).
- **D-14:** Identity, type, endpoint, provenance, manifest, uniqueness, and hash conflicts fail closed — no silent repair, merge, delete, or rewrite of graph data/constraints.
- **D-15:** Logs/metrics expose only bounded IDs, counts, structured codes, durations, and states. Never payloads, source text, credentials, auth headers, raw plan tokens, embeddings, stack traces, raw Cypher/query text, or unsafe exception bodies that may contain catalog content.
- **D-16:** Tests prove prohibition matrix on deterministic paths (spies/static/contract) and fail-closed conflict behavior.
- **D-17:** Ship **one** operator reference plus an explicit migration/offline-regeneration guide (two docs, not a sprawl). Exact filenames/section layout are Claude discretion; content is not.
- **D-18:** Operator reference covers: full tool inventory (legacy + catalog, 28 total), prepare/commit preferred large-payload path, catalog-v2 system-scoped graph-key grammar, FE/BO single-group guidance, overload handling, entity/edge registries, complete endpoint type map, hash coverage/exclusions, capabilities fields, prepare/commit/discard lifecycle, TTL/payload limits, explicit evidence examples, manifest semantics, read/write gates, every structured error code, rollout config/env vars — **no secrets**.
- **D-19:** Migration guide states: catalog-v1 keys and golden hashes obsolete; no automatic identity migration; canary artifacts must be regenerated under catalog-v2 prepare/commit; old ACCEPT_TAB SHA must not be reused; offline regeneration procedure; historical vs current safety axes.
- **D-20:** Run targeted unit, service, store, MCP, concurrency, live Neo4j, Ruff, and Pyright checks when available. Each final result reports pass/fail/skip truthfully without “fixing” unrelated baseline failures by reclassification.
- **D-21:** Final machine-readable report binds check commands, results, skip reasons, historical/current safety axes, tool/compatibility facts, migration status, known limitations, and risks. Always `canary_executed=false`. Sets `ready_to_regenerate_canary=true` only under D-02.
- **D-22:** Keep current forbidden-access flags false while preserving historical `a67789a` truth (two-axis ledger pattern from Phases 3B/4).
- **D-23:** Run local Ollama E2E before milestone cleanup/final closure when local services are available; scope to local services and `oracle-catalog-tool-test` only — never protected group. Report skip/fail truthfully if unavailable. No cleanup/deletion without explicit human confirmation.

### Claude's Discretion
- Exact operator/migration doc filenames and section layout
- Artifact schema and version suffix for regenerated offline canary artifacts
- Gate ledger schema / check grouping / machine-readable report field layout (must still satisfy REPT-01 axes)
- Minimal helper extraction for offline regeneration and gate runners
- **Never** discretion over: safety isolation, readiness semantics, tool counts (28), historical truth, canary ban, or protected-group ban

### Deferred Ideas (OUT OF SCOPE)
- Phase 6 real canary execution / production or `oracle-catalog-v2` writes — separate explicit approval only after `ready_to_regenerate_canary=true`
- Automatic catalog-v1 → catalog-v2 identity migration, re-keying, or graph rewrite
- Full ~14k catalog ingest
- FalkorDB/Kuzu/Neptune catalog portability claims
- `LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`
- Oracle/SQL/PL/SQL parsing, relationship inference, path/impact tools, delta/retirement, business-transaction entities
- Deployment, push/merge/tag, graph clear/delete without explicit confirmation
- Long-term observability dashboards beyond bounded metrics/logging required here
- Milestone cleanup/deletion — requires explicit human confirmation after Ollama E2E (or truthful skip)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDEN-13 | Historical ACCEPT_TAB hash / 10-16-1 / 38-85 invalid for hardened catalog-v2; offline regenerate without execute or graph rewrite | Builder/runner still pre-hardening; offline migrate goldens + pure tests |
| SAFE-03 | No prohibited Graphiti tools on deterministic catalog paths | Extend `PROHIBITED_LEGACY_TOOLS` + service/MCP spies |
| SAFE-04 | No LLM extraction, async queue, implicit endpoints/communities | Commit path already spies embedder/queue; expand static matrix |
| SAFE-06 | Conflicts fail closed; no silent repair/merge/delete/rewrite | Existing conflict tests + matrix assertion |
| SAFE-07 | Logs: IDs/counts/codes only; no payloads/tokens/credentials/exceptions with content | AST logger scrub + caplog tests exist; exhaust matrix |
| SAFE-09 | 14 legacy + original 7 catalog names preserved; catalog-v2 may break payloads explicitly | Registration already 28; re-prove + docs |
| SAFE-10 | Every read/write `group_id`-isolated; Neo4j 5.26+ only | Store/service isolation + no portability claim |
| TEST-10 | Security tests prove prohibition + log scrub matrix | New/extended `test_catalog_security_matrix` (or expand service/canary tests) |
| TEST-11 | Live Neo4j: rollback, search interop, evidence/manifest, control labels excluded, zero outside test group | `test_catalog_*_neo4j_int.py` + availability-truthful skip |
| TEST-12 | Unit/service/store/MCP/concurrency/live/Ruff/Pyright when available; truthful pass/fail/skip | Phase 5 gate runner superseding Phase 4 pattern |
| DOCS-01 | Operator docs: all tools + prepare/commit preferred path | Expand `mcp_server/README.md` (still “seven tools”) |
| DOCS-02 | Grammar, FE/BO, overloads, registries, endpoint map | Document from models + topology authority |
| DOCS-03 | Hash, capabilities, prepare lifecycle, TTL, evidence, manifest, gates | Document from Phase 2–4 contracts |
| DOCS-04 | Every structured error code + config/env without secrets | `CatalogErrorCode` enum is authority |
| DOCS-05 | Migration: v1 obsolete, no auto migration, regenerate canary offline, old SHA banned | New migration guide |
| DOCS-06 | Builder/runner/fixtures/receipts/checkpoint/tests → hardened prepare/commit offline | Migrate scripts + offline tests only |
| REPT-01 | Final structured report; `canary_executed=false`; `ready_to_regenerate_canary` only if all available gates pass | `05-GATE-RESULTS.json` + implementation report |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Security prohibition matrix (SAFE-03/04/06/07, TEST-10) | API / Backend (tests + service boundary) | — | Deterministic catalog is server-side; spies/static AST over service/MCP wrappers |
| Compatibility 28-tool surface (SAFE-09, TEST-12) | API / Backend (MCP registration) | Docs | Already registered; Phase 5 re-proves + documents |
| Group isolation / Neo4j-only (SAFE-10, TEST-11) | Database / Storage | API / Backend | Every Cypher path group-scoped; live proofs on test group only |
| Offline canary artifact migration (IDEN-13, DOCS-06) | Offline scripts / pure validation | — | No network/DB/MCP/LLM; builder+runner pure logic only |
| Operator + migration docs (DOCS-01..05) | CDN / Static (docs) | — | Two markdown artifacts; no secrets |
| Gate ledger + final report (TEST-12, REPT-01) | Offline gate runner | Planning artifacts | Stdlib JSON ledger; two-axis safety |
| Local Ollama E2E (D-23) | API / Backend (local services) | — | Optional availability-truthful; test group only |

## Project Constraints (from CLAUDE.md)

- Additive MCP only — preserve all existing tools/behavior. [VERIFIED: `.claude/CLAUDE.md`]
- Neo4j first, 5.26+; no unsupported multi-backend catalog portability claim. [VERIFIED: CLAUDE.md / project constraints]
- Server-derived UUIDv5 only; `GRAPHITI_CATALOG_UUID_NAMESPACE` immutable deployment config. [VERIFIED: project constraints]
- Never interpolate client labels/property names into Cypher. [VERIFIED: project constraints]
- Writes return only after commit/rollback; embeddings before write tx. [VERIFIED: project constraints]
- Isolation: every read/write constrained by `group_id`; tests only `oracle-catalog-tool-test`. [VERIFIED: project constraints]
- Logging: batch IDs and counts only — never credentials, full payloads, source text. [VERIFIED: project constraints]
- Ops ban: no deployment, live-group writes, full ingest, graph clearing, existing-data deletion. [VERIFIED: project constraints]
- Tooling: `uv`, Ruff (line 100, single quotes), Pyright basic, pytest + pytest-asyncio. [VERIFIED: CLAUDE.md]
- Ruff/Pyright/pytest via `make` / `uv run --project mcp_server`. [VERIFIED: CLAUDE.md]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | ≥8.3.3 (env has 9.x path via uv) | Unit/service/integration runner | Project standard [VERIFIED: mcp_server pyproject / Phase 4 VALIDATION] |
| pytest-asyncio | ≥0.24.0 | Async tests | `asyncio_mode=auto` [VERIFIED: mcp_server/pytest.ini] |
| pydantic | ≥2.11.5 | Catalog contracts / error codes | Existing models authority [VERIFIED: codebase] |
| neo4j | ≥5.26.0 | Live TEST-11 only when available | Official driver; Neo4j-only catalog claim [VERIFIED: pyproject] |
| ruff | ≥0.7.1 | Lint/format gate | Project standard [VERIFIED: pyproject] |
| pyright | ≥1.1.404 | Type gate | Project standard [VERIFIED: pyproject] |
| stdlib (`ast`, `json`, `hashlib`, `subprocess`, `argparse`) | Python 3.10+ | Gate runners + offline canary pure logic | Phase 0–4 gate runners are stdlib-only [VERIFIED: catalog_phase4_gate_runner.py] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unittest.mock / AsyncMock | stdlib | Spy prohibition matrix | Always for SAFE-03/04/TEST-10 |
| uv | 0.11.29 (env) | Project runner | All pytest/ruff/pyright invocations [VERIFIED: env] |
| Ollama (local CLI) | installed (env path present) | Optional local E2E before cleanup | Only if reachable; else truthful skip [VERIFIED: env `ollama` path] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extend Phase 4 gate runner | Brand-new unrelated reporter | Reject — two-axis safety + fail-closed pattern already proven |
| Live canary dry-run for docs | Offline pure validation only | Reject — D-09/D-10 ban network/MCP execution |
| Auto v1→v2 identity rewrite | Explicit offline regeneration | Reject — D-08/D-11 |

**Installation:** None. Phase 5 adds no packages.

**Version verification:** Existing locked deps only. No `package-legitimacy` candidates. [VERIFIED: no new install planned]

## Package Legitimacy Audit

> Phase installs **no** external packages.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — | — | — | — | — | — | N/A |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
[Maintainer / Gate Runner]
        |
        v
+---------------------------+
| Phase 5 Gate Ledger       |
| unit/service/store/MCP    |
| concurrency / live Neo4j  |
| ruff / pyright            |
| security matrix           |
| registration 28           |
| offline canary pure tests |
+------------+--------------+
             |
   +---------+---------+--------------------+
   |                   |                    |
   v                   v                    v
[CatalogService]   [Offline Builder]   [Docs Surface]
 MCP wrappers       scripts/build_*     README + migration
 CatalogStore       scripts/run_*       (no secrets)
 Neo4j (test group  pure validate only
  only if avail)    NO execute
   |
   v
[Final 05-GATE-RESULTS.json + REPT-01 report]
  canary_executed=false
  ready_to_regenerate_canary=?
  historical a67789a axis retained
  current v2 queried/mutated=false
```

### Recommended Project Structure (delta only)

```text
mcp_server/
  README.md                              # expand operator inventory (DOCS-01..04)
  docs/CATALOG_V2_MIGRATION.md           # recommended migration guide path (discretion)
  src/graphiti_mcp_server.py             # re-prove 28 tools (no redesign)
  src/services/catalog_*.py              # spies/targets only unless log scrub gap
  src/models/catalog_common.py           # CatalogErrorCode authority for DOCS-04
  tests/
    catalog_phase5_gate_runner.py        # NEW — extend Phase 4 pattern
    test_catalog_phase5_gate_runner.py   # NEW — self tests
    test_catalog_security_matrix.py      # NEW or expand existing — TEST-10
    test_catalog_canary_scripts.py       # migrate offline pure tests
    test_catalog_*_neo4j_int.py          # TEST-11 when Neo4j available
scripts/
  build_catalog_canary_requests.py       # offline hardened catalog-v2 prepare-shaped artifacts
  run_catalog_canary_batch.py            # prepare/commit sequence; DO NOT EXECUTE live
catalog/
  canary-v2-requests/                    # historical payloads remain readable
  canary-v2-requests-hardened/           # NEW versioned offline artifacts (discretion)
.planning/phases/05-.../
  05-GATE-RESULTS.json                   # REPT-01 ledger
  05-IMPLEMENTATION-REPORT.md|.json      # human+machine readiness
```

### Pattern 1: Phase Gate Runner (clone Phase 4)

**What:** Stdlib-only runner with focused pytest specs, structural checks, safety two-axis fields, Ruff/Pyright optional availability, fail-closed readiness flag.
**When to use:** Final TEST-12 / REPT-01 ledger.
**Example pattern (from Phase 4):** [VERIFIED: `mcp_server/tests/catalog_phase4_gate_runner.py`]

```python
# Source: mcp_server/tests/catalog_phase4_gate_runner.py
SCHEMA_VERSION = 'phase5-gate-results.v1'  # discretion: version string
FORBIDDEN_GROUP = 'oracle-catalog-v2'
ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
HISTORICAL_ORACLE_CATALOG_V2_QUERIED = True
HISTORICAL_V2_COMMIT = 'a67789a'
# current_* always false; canary_executed always false
```

### Pattern 2: Security prohibition matrix

**What:** Static AST scan of catalog service/MCP wrappers for prohibited call literals + runtime AsyncMock spies on `llm_client`, `queue_service`, embedder (commit), and Graphiti maintenance methods.
**When to use:** SAFE-03/04, TEST-10.
**Seed:** `PROHIBITED_LEGACY_TOOLS` in canary tests already lists banned tools. [VERIFIED: `test_catalog_canary_scripts.py`]

```python
# Source: mcp_server/tests/test_catalog_canary_scripts.py
PROHIBITED_LEGACY_TOOLS = {
    'add_memory', 'add_triplet', 'build_communities', 'clear_graph',
    'delete_entity_edge', 'delete_episode', 'summarize_saga', 'update_entity',
    # note: upsert_provenance/typed_* banned for canary runner path specifically;
    # product compatibility tools remain registered (D-07)
}
```

Phase 5 product matrix must distinguish:
1. **Prohibited on deterministic catalog paths** (SAFE-03): maintenance/LLM/queue tools.
2. **Allowed compatibility catalog tools** that remain registered but are not preferred large-payload path.

### Pattern 3: Offline canary artifact migration

**What:** Builder emits catalog-v2 prepare/commit-compatible payloads (identity_schema_version, system_key, evidence_links, request hash recipe, prepare-shaped plan fields as needed). Runner pure-logic validates prepare→commit tool sequence offline with fakes. Historical goldens retained under historical suffix; new hardened artifacts versioned separately.
**When to use:** IDEN-13, DOCS-06.
**Current gap:** Builder hardcodes `GROUP_ID = 'oracle-catalog-v2'`, pre-hardening request shape without `identity_schema_version` / system-scoped grammar, and runner still calls `upsert_catalog_batch` as commit tool. [VERIFIED: `scripts/build_catalog_canary_requests.py`, `scripts/run_catalog_canary_batch.py`]

### Pattern 4: Availability-truthful live Neo4j

**What:** `pytest.skip` when driver unavailable unless `CATALOG_INT_REQUIRED=1` forces fail. Hardcoded `oracle-catalog-tool-test`. Teardown DETACH DELETE only that group. Never `clear_graph`. Never touch v2. [VERIFIED: `test_catalog_neo4j_int.py` header]

### Anti-Patterns to Avoid

- **Treating skip as pass:** Readiness must separate `skipped` from `passed` (D-02/D-03).
- **Executing canary runner “just to verify”:** Forbidden even dry-run against live/MCP (D-10, Phase 0 isolation policy).
- **Reusing ACCEPT_TAB golden SHA as hardened authority:** Explicitly invalid (D-11, IDEN-13).
- **Silent v1 payload acceptance:** Fail closed with structured codes (D-08).
- **Rewriting historical a67789a axis:** Two-axis only (D-05/D-22).
- **Docs sprawl / secrets in docs:** Exactly two docs; no credentials/namespace secrets (D-17/D-18).
- **Querying protected group for “before/after counts”:** Historical violation only; current ban absolute (D-04).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Gate ledger JSON | Ad-hoc shell scripts | Clone `catalog_phase4_gate_runner.py` | Proven fail-closed + two-axis safety |
| Structured errors | New error taxonomy | `CatalogErrorCode` StrEnum | DOCS-04 authority already complete-ish |
| Identity/hash | New hash recipe | Existing catalog-v2 identity + hash helpers | Phase 1–2 authority |
| Live isolation fixtures | New group scheme | `catalog_neo4j_fixtures.py` + GROUP constant | Hard isolation already wired |
| Log scrub framework | Logging middleware rewrite | AST template scan + caplog assertions already used | Extend, don't replace |
| Canary network client for Phase 5 | Live MCP calls | Offline pure validate + fakes | D-09/D-10 |

**Key insight:** Phase 5 is mostly **proof and packaging** of already-shipped product behavior. Prefer new tests/docs/gate runners over product redesign.

## Runtime State Inventory

> Not a rename/refactor of product identifiers. Offline artifact versioning only.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Historical canary group `oracle-catalog-v2` may exist in local Neo4j from pre-hardening work; test group `oracle-catalog-tool-test` used by int tests | **Never query/mutate v2.** Live tests only touch test group; teardown scoped DELETE |
| Live service config | MCP/Neo4j/Ollama may be running locally | Optional E2E only; no deploy config mutation |
| OS-registered state | Ollama installed at user path | Availability probe only |
| Secrets/env vars | `GRAPHITI_CATALOG_UUID_NAMESPACE`, Neo4j creds, provider keys | Never log/doc secrets; do not change namespace |
| Build artifacts | `catalog/canary-v2-requests/*` historical; checkpoint attempts | Offline regenerate hardened suite with new suffix/dir; do not grow checkpoint via canary execute |

**Nothing found requiring data migration of production graph state** — automatic migration explicitly out of scope.

## Common Pitfalls

### Pitfall 1: “Seven tools” docs drift
**What goes wrong:** README still centers seven catalog tools while code has 14 catalog + 14 legacy. [VERIFIED: README “seven catalog tools”; CATALOG_TOOL_NAMES size 14]
**Why it happens:** Docs lagged Phase 3A/3B/4 registration growth.
**How to avoid:** DOCS-01 inventory table = exact 28 names from frozensets in tests/server.
**Warning signs:** Operator guide omits prepare/commit/manifest/evidence tools.

### Pitfall 2: Canary builder still pre-hardening
**What goes wrong:** Offline regen still emits invalid v1-shaped keys/hashes and direct-upsert sequence.
**Why it happens:** Scripts frozen at pre-hardening ACCEPT_TAB workflow. [VERIFIED: GROUP_ID v2, make_request lacks identity_schema_version]
**How to avoid:** Explicit catalog-v2 fields + prepare/commit preferred sequence in offline artifacts; version suffix so history remains readable.
**Warning signs:** Tests still assert old ACCEPT_TAB golden as current authority.

### Pitfall 3: Skip-as-pass readiness inflation
**What goes wrong:** Missing Neo4j/Ollama counted as green.
**How to avoid:** Ledger fields: `passed` / `failed` / `skipped` + `skip_reason`; readiness formula excludes treating skip as pass (D-02).
**Warning signs:** `ready_to_regenerate_canary=true` with mandatory runnable failures reclassified.

### Pitfall 4: Accidental protected-group touch
**What goes wrong:** Live suite or gate “safety scan” reintroduces v2 query (historical a67789a class).
**How to avoid:** Static source scan forbids v2 as Cypher/param in current product/test paths; only historical inventory strings allowed.
**Warning signs:** `current_oracle_catalog_v2_queried=true`.

### Pitfall 5: Executing runner during “validation”
**What goes wrong:** `run_catalog_canary_batch.py --mcp-url ...` even dry-run.
**How to avoid:** Gate runner must not shell the live runner; offline tests import pure functions only (existing pattern).
**Warning signs:** Checkpoint `attempts` growth; network to MCP.

### Pitfall 6: Log leakage regressions
**What goes wrong:** New log lines include payload, raw plan_token, Cypher, or exception bodies.
**How to avoid:** Extend AST logger template bans + caplog forbidden-substring lists (payload markers, token-looking strings, credentials keys).
**Warning signs:** Caplog contains `plan_token=`, entity summaries, source text.

### Pitfall 7: Commit path external calls
**What goes wrong:** Commit re-embeds or hits queue/LLM.
**How to avoid:** Spies: `embedder.create` not awaited on commit; queue not called; already partially covered in prepare/commit tests — make matrix exhaustive. [VERIFIED: commit recovery / prepare service spies]

## Code Examples

### 28-tool registration contract
```python
# Source: mcp_server/tests/test_catalog_service.py (TEST-09 foundation)
CATALOG_TOOL_NAMES = { ... 14 names including prepare/commit/discard + Phase 4 reads ... }
LEGACY_TOOL_NAMES = {
    'add_memory', 'search_nodes', 'search_memory_facts', 'add_triplet',
    'get_entity_edge', 'get_episodes', 'get_episode_entities', 'update_entity',
    'build_communities', 'summarize_saga', 'delete_episode', 'delete_entity_edge',
    'clear_graph', 'get_status',
}
# assert len(names) == 28 and names == CATALOG_TOOL_NAMES | LEGACY_TOOL_NAMES
```
[VERIFIED: test_catalog_service.py]

### Catalog tool names (product)
```python
# Source: mcp_server/src/graphiti_mcp_server.py
CATALOG_TOOL_NAMES = frozenset({
    'upsert_typed_entities', 'resolve_typed_entities', 'resolve_typed_edges',
    'verify_catalog_batch', 'upsert_typed_edges', 'upsert_provenance',
    'get_catalog_ingest_status', 'get_catalog_batch_manifest', 'get_catalog_evidence',
    'upsert_catalog_batch', 'get_catalog_capabilities',
    'prepare_catalog_batch', 'commit_prepared_catalog_batch', 'discard_prepared_catalog_batch',
})
```
[VERIFIED: graphiti_mcp_server.py]

### Structured error codes (DOCS-04 authority)
```python
# Source: mcp_server/src/models/catalog_common.py — CatalogErrorCode
# validation_error, feature_disabled, invalid_uuid_namespace, batch_limit_exceeded,
# content_hash_mismatch, entity_type_conflict, graph_key_prefix_mismatch,
# deterministic_uuid_conflict, missing_endpoint, endpoint_type_mismatch,
# generic_endpoint_conflict, edge_identity_conflict, batch_conflict,
# provenance_target_missing, neo4j_transaction_failed, embedding_failed,
# internal_error, backend_unavailable, unsupported_identity_schema,
# invalid_system_key, edge_endpoint_pair_not_allowed, prepared_plan_not_found,
# prepared_plan_expired, prepared_plan_conflict, prepared_plan_already_consumed,
# manifest_mismatch, provenance_link_conflict
```
[VERIFIED: catalog_common.py]

### Two-axis safety fields (REPT-01)
```json
{
  "schema_version": "phase5-gate-results.v1",
  "canary_executed": false,
  "ready_to_regenerate_canary": false,
  "safety": {
    "canary_executed": false,
    "oracle_catalog_v2_queried": false,
    "current_oracle_catalog_v2_queried": false,
    "historical_oracle_catalog_v2_queried": true,
    "historical_v2_commit": "a67789a",
    "historical_v2_class": "test_policy",
    "historical_v2_scope": "local_neo4j_no_corresponding_data",
    "clear_graph_called": false
  }
}
```
[VERIFIED: pattern from 04-GATE-RESULTS.json]

### Final report YAML axes (roadmap REPT-01)
```yaml
# Source: .planning/graphiti_mcp_pre_canary_roadmap_en.md §7
implementation_status: complete | partial | blocked
completed_phases: [phase_0, phase_1, phase_2, phase_3a, phase_3b, phase_4, phase_5]
requirements: { total_expected: 138, mapped: 0, implemented: 0, verified: 0 }
tests: { passed: 0, failed: 0, skipped: 0 }
compatibility_breaks: []
migrations_added: []
known_limitations: []
blockers: []
ready_to_regenerate_canary_payload: false  # alias ready_to_regenerate_canary
canary_executed: false
```
[VERIFIED: roadmap_en.md]

### Live Neo4j skip policy
```python
# Source: mcp_server/tests/test_catalog_neo4j_int.py
# Hardcoded group_id: oracle-catalog-tool-test only.
# Gate mode: CATALOG_INT_REQUIRED=1 converts missing Neo4j into FAIL (not skip).
pytest.skip(f'Neo4j unavailable: {exc}')
```
[VERIFIED: test_catalog_neo4j_int.py]

## State of the Art (this repo)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 7 catalog tools docs | 14 catalog + 14 legacy = 28 | Phases 2–4 product | Docs must catch up |
| Direct `upsert_catalog_batch` canary | prepare → commit preferred | Phase 3A/3B | Offline canary migration |
| Cartesian multi-source provenance | Explicit `CatalogEvidenceLink` | Phase 2/3B | Artifacts + docs |
| Single safety flag | Two-axis historical/current | Phase 3B/4 | Phase 5 ledger must retain both |
| Pre-hardening ACCEPT_TAB goldens as authority | Historical only | Phase 0 policy | IDEN-13 offline regen |

**Deprecated/outdated:**
- catalog-v1 keys/hashes as current authority
- README “seven catalog tools” as complete inventory
- Canary runner direct-upsert sequence as hardened path
- Historical ACCEPT_TAB server request SHA as hardened golden

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Recommended migration doc path `mcp_server/docs/CATALOG_V2_MIGRATION.md` (discretion) | Docs | Filename only; content locked by D-19 |
| A2 | Hardened offline artifacts live under versioned dir/suffix (e.g. `canary-v2-requests-hardened/`) | IDEN-13 | Path discretion; must not overwrite historical readability |
| A3 | No product store/service redesign required if security matrix is test-only and logs already scrubbed | Architecture | If log scrub gap found in product code, minimal fix allowed — not redesign |
| A4 | Ollama E2E means local embedder path on test group, not full 14k ingest | D-23 | Scope creep into full ingest if misread |

**If empty verification needed:** Product behavior largely verified in Phases 1–4; Phase 5 owns exhaustive proof packaging.

## Open Questions

1. **Exact hardened artifact directory/version string**
   - What we know: Historical `catalog/canary-v2-requests/` must remain readable; new artifacts supersede offline only.
   - What's unclear: Final dirname/suffix (discretion).
   - Recommendation: `catalog/canary-v2-requests-hardened/` + manifest field `identity_schema_version=catalog-v2` + `artifact_schema_version`.

2. **Whether live TEST-11 expands existing int modules or adds a thin Phase 5 suite**
   - What we know: `test_catalog_neo4j_int.py`, `test_catalog_commit_neo4j_int.py`, `test_catalog_prepare_neo4j_int.py` already cover much of rollback/search/isolation.
   - What's unclear: Gap list vs TEST-11 exact bullets (control labels excluded, zero writes outside group).
   - Recommendation: Inventory existing live tests first; add only missing named proofs; keep availability skip.

3. **Ollama E2E harness location**
   - What we know: Ollama CLI present; retrospective mentions prior E2E; no Phase 5 harness yet.
   - What's unclear: Minimal script vs pytest module.
   - Recommendation: Small optional pytest or script under mcp_server/tests, test group only, skip if Ollama/Neo4j down.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All tests | ✓ | 3.12.10 | — |
| uv | pytest/ruff/pyright | ✓ | 0.11.29 | — |
| pytest (via uv project mcp_server) | TEST-10/11/12 | ✓ (project) | project pin | — |
| Ruff / Pyright | TEST-12 | ✓ via project | project pin | skip with reason if binary missing |
| Neo4j live | TEST-11 | unknown (availability probe at run) | 5.26+ required | Truthful skip unless `CATALOG_INT_REQUIRED=1` |
| Ollama local | D-23 E2E | ✓ CLI path present | local install | Truthful skip if daemon/model unavailable |
| Network / MCP canary endpoint | — | must NOT use | — | Offline pure only |
| Protected group data | — | must NOT use | — | Historical inventory only |

**Missing dependencies with no fallback:** none for offline core Phase 5 work.

**Missing dependencies with fallback:** live Neo4j, Ollama daemon/models — skip with reason; do not invent pass.

## Validation Architecture

> `workflow.nyquist_validation` enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-asyncio) via `uv run --project mcp_server` |
| Config file | `mcp_server/pytest.ini` |
| Quick run command | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_security_matrix.py mcp_server/tests/test_catalog_phase5_gate_runner.py -q --tb=line -x` |
| Full suite command | Phase 5 focused multi-file suite + gate runner `run` (see map) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SAFE-03 | No prohibited Graphiti tools on catalog deterministic paths | unit/static + spy | `pytest ... test_catalog_security_matrix.py -k prohibited -q` | ❌ Wave 0 (extend canary/service seeds) |
| SAFE-04 | No LLM/queue/implicit community on deterministic path | unit/spy | `pytest ... test_catalog_security_matrix.py -k llm_or_queue -q` | ❌ Wave 0 |
| SAFE-06 | Fail-closed conflicts (identity/type/endpoint/provenance/manifest/hash) | unit/service | existing conflict tests + matrix asserts | ✅ partial / extend |
| SAFE-07 | Log scrub: no payload/token/credential/source/exception body | unit/AST/caplog | `pytest ... test_catalog_service.py -k logger -q` + matrix | ✅ partial / extend |
| SAFE-09 | 14 legacy + 14 catalog = 28; original 7 names still registered | contract | `pytest ... test_catalog_service.py::test_mcp_registers_exactly_fourteen_catalog_tools_and_preserves_legacy_tools -q` | ✅ |
| SAFE-10 | group_id isolation; Neo4j-only claim | unit + live | store/service isolation tests; live int | ✅ partial |
| TEST-10 | Full security matrix proof | unit | security matrix module | ❌ Wave 0 |
| TEST-11 | Live rollback, search interop, evidence/manifest, control labels, no outside writes | integration | `pytest ... test_catalog_commit_neo4j_int.py test_catalog_neo4j_int.py test_catalog_prepare_neo4j_int.py -q` (skip if no Neo4j) | ✅ extend gaps |
| TEST-12 | Truthful multi-suite ledger | gate runner | `python mcp_server/tests/catalog_phase5_gate_runner.py run` | ❌ Wave 0 |
| IDEN-13 | Historical goldens invalid; offline hardened regen | offline unit | `pytest ... test_catalog_canary_scripts.py -q` | ✅ migrate |
| DOCS-01..04 | Operator reference completeness | structural/doc gate | gate check greps required sections/names | ❌ Wave 0 doc + check |
| DOCS-05 | Migration guide claims | structural/doc gate | gate check required phrases | ❌ Wave 0 |
| DOCS-06 | Builder/runner offline prepare/commit migration | offline unit | canary script tests | ✅ migrate |
| REPT-01 | Final report schema + canary_executed=false + conditional ready flag | gate runner | phase5 gate + report file | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** focused file(s) for that task (`-q --tb=line -x`)
- **Per wave merge:** Phase 5 focused suite + gate structural checks
- **Phase gate:** `catalog_phase5_gate_runner.py run` green; `canary_executed=false`; readiness only if D-02 satisfied

### Recommended Phase 5 focused suite (planner baseline)

```text
mcp_server/tests/test_catalog_security_matrix.py          # NEW
mcp_server/tests/test_catalog_canary_scripts.py           # migrated
mcp_server/tests/test_catalog_service.py                  # registration + logger
mcp_server/tests/test_catalog_capabilities.py
mcp_server/tests/test_catalog_gates.py
mcp_server/tests/test_catalog_commit_recovery.py          # fail-closed / no embed on commit
mcp_server/tests/test_catalog_concurrency.py
mcp_server/tests/test_catalog_phase5_gate_runner.py       # NEW
# live (optional availability):
mcp_server/tests/test_catalog_neo4j_int.py
mcp_server/tests/test_catalog_commit_neo4j_int.py
mcp_server/tests/test_catalog_prepare_neo4j_int.py
```

Quick offline command:

```bash
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_security_matrix.py \
  mcp_server/tests/test_catalog_canary_scripts.py \
  mcp_server/tests/test_catalog_phase5_gate_runner.py \
  -q --tb=line
```

Full offline-ish focused + registration:

```bash
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_security_matrix.py \
  mcp_server/tests/test_catalog_canary_scripts.py \
  mcp_server/tests/test_catalog_service.py \
  mcp_server/tests/test_catalog_capabilities.py \
  mcp_server/tests/test_catalog_gates.py \
  mcp_server/tests/test_catalog_commit_recovery.py \
  mcp_server/tests/test_catalog_concurrency.py \
  mcp_server/tests/test_catalog_phase5_gate_runner.py \
  -q --tb=short
```

Gate:

```bash
uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py run
```

Ruff / Pyright (catalog surface):

```bash
uv run --project mcp_server ruff check mcp_server/src/services/catalog_service.py mcp_server/src/services/catalog_store.py mcp_server/tests/catalog_phase5_gate_runner.py
uv run --project mcp_server pyright mcp_server/src/services/catalog_service.py mcp_server/src/services/catalog_store.py
```

Live (optional):

```bash
# skip-OK unless CATALOG_INT_REQUIRED=1
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_neo4j_int.py \
  mcp_server/tests/test_catalog_commit_neo4j_int.py \
  mcp_server/tests/test_catalog_prepare_neo4j_int.py \
  -q --tb=line
```

### Wave 0 Gaps

- [ ] `mcp_server/tests/catalog_phase5_gate_runner.py` — TEST-12 / REPT-01 ledger (clone Phase 4)
- [ ] `mcp_server/tests/test_catalog_phase5_gate_runner.py` — runner self-tests
- [ ] `mcp_server/tests/test_catalog_security_matrix.py` — SAFE-03/04/06/07 + TEST-10 exhaustive matrix (or clearly named expansion of existing modules)
- [ ] Offline canary builder/runner prepare/commit migration scaffolds (RED tests first under TDD)
- [ ] Operator doc expansion checklist + migration guide file scaffold
- [ ] `05-GATE-RESULTS.json` fail-closed default (`ready_to_regenerate_canary=false`, `canary_executed=false`)
- [ ] Optional Ollama E2E harness with availability skip
- [ ] LIVE TEST-11 gap inventory vs existing int tests (control-label exclusion, outside-group write zero)

*(Framework install: none — use existing uv project)*

### Gate ledger checks (minimum)

| Check id | Kind | Mandatory | Notes |
|----------|------|-----------|-------|
| runner_self_tests | pytest | yes | phase5 runner unit tests |
| focused_pytest | pytest | yes | offline focused suite |
| security_matrix | pytest | yes | TEST-10 |
| registration_28 | structural/pytest | yes | SAFE-09 |
| safety_no_v2_current | safety scan | yes | current v2 ban |
| historical_axis_preserved | safety | yes | a67789a fields true historically |
| canary_not_executed | safety | yes | always false |
| offline_canary_pure | pytest | yes | canary scripts offline only |
| docs_operator_sections | structural | yes | DOCS-01..04 section greps |
| docs_migration_phrases | structural | yes | DOCS-05 required claims |
| ruff | lint | when available | skip reason if missing |
| pyright | types | when available | skip reason if missing |
| live_neo4j_test11 | integration | no | skip if unavailable |
| ollama_e2e | e2e | no | skip if unavailable |

### Security checks (ASVS-aligned for this phase)

- Input validation already fail-closed at models — re-prove via matrix, do not weaken.
- Log scrub SAFE-07 / SAFE-08 structured errors — exhaustive.
- No client Cypher identifiers — existing allowlists; include in matrix.
- Token: raw plan_token never logged/stored; digest only — include in matrix.
- Isolation: test group only; protected group ban static+runtime.

### Artifact-offline checks

- Builder/runner unit tests never open network sockets / Neo4j / embedder / LLM.
- Checkpoint attempts count does not grow from Phase 5 execution.
- Historical ACCEPT_TAB SHA asserted **not equal** to new hardened goldens (or marked historical-only field).

### Ollama E2E check

- Probe `ollama` CLI + local endpoint; skip with reason if down.
- Use only `oracle-catalog-tool-test`.
- No protected group, no canary runner, no cleanup/delete without human confirm.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no new auth surface) | existing MCP transport security unchanged |
| V3 Session Management | partial (plan_token one-time) | digest compare timing-safe; never log raw token |
| V4 Access Control | yes | `group_id` isolation; feature read/write gates |
| V5 Input Validation | yes | Pydantic CatalogStrictModel + CatalogErrorCode fail-closed |
| V6 Cryptography | yes (tokens/hashes) | SHA-256 digests; UUIDv5 namespace; no hand-rolled crypto |

### Known Threat Patterns for catalog MCP

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher injection via labels/props | Tampering | Server allowlists only; never client interpolation |
| Cross-group read/write | Elevation | Every query parameterized `group_id`; live tests only test group |
| Prompt/LLM side effects on catalog path | Tampering | Deterministic path bans LLM/queue (SAFE-04) |
| Log exfiltration of catalog content | Info disclosure | SAFE-07 scrub + AST/caplog tests |
| Token theft via logs/response replay | Info disclosure / Elevation | Raw token one-time visible; store digest only |
| Silent identity migration | Tampering | Fail closed unsupported_identity_schema / invalid keys |
| Accidental canary / protected writes | Tampering | Hard bans in policy + gate safety fields |
| clear_graph / delete tools from catalog path | Destruction | Prohibition matrix SAFE-03 |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/05-.../05-CONTEXT.md` — locked decisions D-01..D-23
- `.planning/REQUIREMENTS.md` — IDEN-13, SAFE-*, TEST-10..12, DOCS-*, REPT-01
- `.planning/ROADMAP.md` — Phase 5 success criteria + hard gates
- `.planning/graphiti_mcp_pre_canary_roadmap_en.md` § Phase 5 + final report format
- `.planning/phases/04-.../04-VERIFICATION.md` + `04-GATE-RESULTS.json` — dependency proof, ledger shape
- `mcp_server/tests/catalog_phase4_gate_runner.py` — gate pattern
- `mcp_server/src/graphiti_mcp_server.py` — CATALOG_TOOL_NAMES (14)
- `mcp_server/tests/test_catalog_service.py` — 28-tool registration + logger AST scrub
- `mcp_server/tests/test_catalog_canary_scripts.py` — offline canary pure tests + PROHIBITED set
- `scripts/build_catalog_canary_requests.py` / `run_catalog_canary_batch.py` — pre-hardening canary substrate
- `mcp_server/src/models/catalog_common.py` — CatalogErrorCode
- `mcp_server/tests/test_catalog_neo4j_int.py` — live isolation policy
- `.planning/phases/00-.../00-ISOLATION-POLICY.md` — canary/group/remote bans
- `CLAUDE.md` / `.claude/CLAUDE.md` — project constraints

### Secondary (MEDIUM confidence)
- `catalog/CANARY_V2_SUMMARY.md` — historical ACCEPT_TAB inventory (offline)
- `.planning/RETROSPECTIVE.md` — prior Ollama E2E mention

### Tertiary (LOW confidence)
- Exact Ollama model/dim for this environment's E2E (probe at execution; do not hardcode unverified model success)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; repo tooling verified in env
- Architecture: HIGH — product complete through Phase 4; Phase 5 is proof/docs/offline migration
- Pitfalls: HIGH — isolation/canary/docs drift patterns already documented in Phase 0–4

**Research date:** 2026-07-19
**Valid until:** 2026-08-18 (stable contracts; re-check if Phase 4 artifacts move)
