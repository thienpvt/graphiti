---
phase: 01-typed-catalog-primitives
verified: 2026-07-17T00:35:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "Operator-configured collection limits and strict raw-text validation are enforced (CONF-04, SAFE-03)"
    - "verify_catalog_batch reports edge endpoint mismatches distinctly from edge-type mismatches (VERI-03)"
    - "resolve reports all-row twin anomalies including wrong_type with typed present (RESO-03)"
    - "verify reports wrong_type with typed present; entity elementId physical-row dedup (VERI-02)"
    - "Phase 1 quality gate and report are green and honest (GATE-01, GATE-05)"
  gaps_remaining: []
  regressions: []
---

# Phase 1: Typed Catalog Primitives Verification Report

**Phase Goal:** Operators can configure and use deterministic typed entity/edge primitives that commit exactly one searchable Neo4j object per identity with no LLM, queue, or implicit endpoint mutation
**Verified:** 2026-07-17T00:35:00Z
**Status:** passed
**Re-verification:** Yes — after 01-07/01-08 gap closure

## Goal Achievement

### Observable Truths

| # | Roadmap truth | Status | Evidence |
|---|---|---|---|
| 1 | Operator can enable/disable catalog writes; fixed `GRAPHITI_CATALOG_UUID_NAMESPACE`; batch limits defaults 500/2000/5000 validated; never auto-generates namespace | ✓ VERIFIED | `CatalogConfig` defaults disabled; enabled requires valid namespace; no generation path. Request ceilings use `HARD_MAX_*` (5000/10000); service gates enforce configured `max_*_per_batch` (`catalog_service.py:180-186`, `1667-1672`). Nested raw strings bounded via `validate_nested_json` (`catalog_common.py:33-78`). Independent probe: 501-entity request accepted under HARD_MAX; nested string >8192 rejected. |
| 2 | `upsert_typed_entities` / `upsert_typed_edges`: UUIDv5, 64-char SHA-256, embed-before-tx, atomic rollback, structured errors, no LLM/queue/caller-UUID authority/implicit endpoints | ✓ VERIFIED | Identity helpers + service prepare/embed then `_ensure_schema` then write tx only on non-dry-run paths (`catalog_service.py:435-508`, `1998-2051`). Live suite covers retry/conflict/rollback/concurrency/no-LLM/no-queue. |
| 3 | Read-only `resolve_typed_entities` / `verify_catalog_batch` report missing, generic, duplicate, mistyped, UUID-mismatch, missing-embedding, endpoint issues without writes | ✓ VERIFIED | `_analyze_resolve_item` all-row aggregation (`catalog_service.py:1139-1288`): wrong_type whenever wrong siblings exist; uuid_mismatch/missing_embedding scan all typed rows; primary UUID prefers expected. `_verify_entities` reports wrong_type with typed present (`1517-1518`). `_verify_edges` separates `edge_type_mismatch` vs `endpoint_mismatch` using expected endpoint fields (`1581-1601`). Store returns `elementId(n)` and dedups by physical id (`catalog_store.py:587-665`). Unit+live mixed-twin tests pass. |
| 4 | Existing `search_nodes` / `search_memory_facts` retrieve catalog entities/facts under `oracle-catalog-tool-test` with type filters | ✓ VERIFIED | Live `test_search_nodes_and_memory_facts_interop` passed under `CATALOG_INT_REQUIRED=1`. |
| 5 | Phase 1 quality gate green; short report gates Phase 2 | ✓ VERIFIED | Independent rerun: 196 units, 27 live (0 skip), Ruff format/check, Pyright 0 errors, 86 MCP regressions, 18-tool listing. Report records evidence and keeps Phase 2 pending independent acceptance (now satisfied by this report). |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `mcp_server/src/config/schema.py` | CatalogConfig | ✓ VERIFIED | Limits ge=1 le=HARD_MAX; enabled+namespace gate |
| `mcp_server/src/models/catalog_common.py` | Allowlists, limits, nested validation | ✓ VERIFIED | 15 types, 16 edges, HARD_MAX, `validate_nested_json` |
| `mcp_server/src/models/catalog_entities.py` | Entity/resolve/verify request models | ✓ VERIFIED | HARD_MAX list ceilings; VerifyEdgeRef endpoint expectations |
| `mcp_server/src/models/catalog_edges.py` | Edge request models | ✓ VERIFIED | HARD_MAX; nested attribute validation |
| `mcp_server/src/models/catalog_responses.py` | Structured responses | ✓ VERIFIED | Includes `edge_type_mismatch` section field |
| `mcp_server/src/services/catalog_identity.py` | UUIDv5/SHA-256 | ✓ VERIFIED | Wired into prepare paths |
| `mcp_server/src/services/catalog_store.py` | Neo4j store | ✓ VERIFIED | elementId verify queries; group-scoped Cypher; no client labels |
| `mcp_server/src/services/catalog_service.py` | Orchestration | ✓ VERIFIED | Resolve/verify all-row anomalies; schema ensure write-only |
| `mcp_server/src/graphiti_mcp_server.py` | Four additive tools | ✓ VERIFIED | 18 tools total; 14 existing retained |
| `mcp_server/tests/test_catalog_*.py` | Focused + live coverage | ✓ VERIFIED | 196 unit + 27 live; twin/endpoint regressions present |
| `.planning/phases/01-typed-catalog-primitives/01-PHASE1-REPORT.md` | Gate report | ✓ VERIFIED | Overall PASS with evidence; Phase 2 independently gated |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Four MCP tools | `CatalogService` | Direct await | ✓ WIRED | Tool listing 18/4/14 |
| `CatalogService` | identity helpers | UUID/hash prepare | ✓ WIRED | Configured namespace |
| `CatalogService` | embedder | Await before write tx | ✓ WIRED | Entity/edge embed precede schema/tx |
| `CatalogService` | store/Neo4j | Pre-read, resolve, write | ✓ WIRED | Atomic/per-item live-tested |
| `resolve_typed_entities` | `_analyze_resolve_item` | All-row anomaly aggregate | ✓ WIRED | Mixed-twin unit+live |
| `verify_catalog_batch` | `_verify_entities` / `_verify_edges` | wrong_type + endpoint compare | ✓ WIRED | Typed-present wrong_type; endpoint vs type split |
| Entity verify store | physical rows | `elementId(n)` dedup | ✓ WIRED | Store unit + live |
| Catalog writes | Graphiti search | Entity/RELATES_TO props | ✓ WIRED | Live interop |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| Entity upsert | uuid/hash/embedding | request + namespace + embedder | Neo4j MERGE | ✓ FLOWING |
| Edge upsert | endpoint UUIDs/fact emb | typed endpoint resolve + embedder | RELATES_TO MERGE | ✓ FLOWING |
| Resolve | matches/anomalies | group/key MATCH all rows | aggregated anomalies | ✓ FLOWING |
| Verify entities | rows by graph_key | elementId-preserving MATCH | wrong_type/etc lists | ✓ FLOWING |
| Verify edges | source/target fields | MATCH returns endpoints | endpoint_mismatch when expected set | ✓ FLOWING |
| Search | names/facts | Graphiti hybrid search | live expected hits | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Catalog units | `uv run pytest tests/test_catalog_{models,identity,store_unit,service}.py -q` | `196 passed in 1.51s` | ✓ PASS |
| Live Neo4j required | `CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -q --timeout=120` | `27 passed in 18.06s` | ✓ PASS |
| Focused twin/endpoint | `-k "mixed_twin or wrong_type_with_typed or element_id or endpoint_mismatch or ..."` | `8 passed` | ✓ PASS |
| MCP regressions | `test_update_entity/factories/configuration/core_parity` | `86 passed in 1.31s` | ✓ PASS |
| Ruff format/check | catalog-scoped paths | formatted; all checks passed | ✓ PASS |
| Pyright package paths | catalog-scoped | `0 errors, 0 warnings` | ✓ PASS |
| Tool listing | `mcp.list_tools()` assert | 18/4/14 missing=[] | ✓ PASS |
| CONF-04 probe | construct 501 entities with max=501 config | accepted under HARD_MAX | ✓ PASS |
| SAFE-03 probe | nested string MAX_EVIDENCE_LENGTH+1 | rejected entity+edge | ✓ PASS |

### Probe Execution

No standalone `scripts/*/tests/probe-*.sh`. Runnable pytest/quality gates above used as probes.

### Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| CONF-01..03, CONF-05 | ✓ SATISFIED | Disabled default; fixed namespace validation; no auto-gen; Neo4j-only gate |
| CONF-04 | ✓ SATISFIED | Defaults 500/2000/5000; config above defaults within HARD_MAX; service enforces configured max |
| SAFE-01..02, SAFE-04..05 | ✓ SATISFIED | group_id isolation; fixed labels/properties; structured codes; bounded logs |
| SAFE-03 | ✓ SATISFIED | Field max lengths + `validate_nested_json` string/key/depth/node/cycle/finite bounds |
| IDEN-01..02, IDEN-05..08 | ✓ SATISFIED | Deterministic UUID/hash, conflict/no-op, no caller UUID authority |
| ENTY-01..13 | ✓ SATISFIED | Tool surface, prefixes, labels, embed-before-tx, atomicity, dry-run, concurrency, search |
| RESO-01..04 | ✓ SATISFIED | Read-only resolve; all-row anomalies including mixed twins; no write/embed |
| EDGE-01..12 | ✓ SATISFIED | Typed endpoints, RELATES_TO, no implicit create, atomicity, search |
| VERI-01..05 | ✓ SATISFIED | Scoped verify; entity twin anomalies; endpoint vs type; provenance optional; read-only |
| GATE-01..05 | ✓ SATISFIED | Units, live isolation suite, no LLM/queue, quality tools, honest report |

**Requirement score:** 55/55 Phase 1 IDs satisfied (IDEN-03/04 are provenance — not Phase 1 scope). No orphaned Phase 1 IDs.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| — | — | None blocker | — | Prior fixed-ceiling / mislabeled endpoint / primary-only twin gaps closed |

No unreferenced TBD/FIXME/XXX in catalog product models/services. Product catalog path has no `clear_graph` and no `oracle-catalog-v2` writes. `_ensure_schema` only on real entity/edge write paths (`catalog_service.py:499`, `2051`), not resolve/verify/dry-run.

### Human Verification Required

None. Twin, endpoint, isolation, search, rollback, and concurrency invariants have automated unit and/or live coverage.

### Gaps Summary

None remaining. Prior independent failures (CONF-04, SAFE-03, VERI-03, RESO-03, VERI-02, GATE-01/05 overclaim) are closed in code with focused unit + live regressions. Phase 1 goal is achieved. Orchestrator may mark Phase 1 complete and open Phase 2.

### Re-verification Notes (vs previous 3/5 gaps_found)

| Prior gap | Closure evidence |
|---|---|
| CONF-04 fixed Pydantic 500/2000 ceilings | `max_length=HARD_MAX_*`; service config gate |
| SAFE-03 unbounded nested raw strings | `validate_nested_json` length/depth/nodes |
| VERI-03 endpoint mismatch mislabeled | `VerifyEdgeRef` expected endpoint fields + separate `edge_type_mismatch` |
| RESO-03 primary-only twin anomalies | `_analyze_resolve_item` all-row scan |
| VERI-02 wrong_type suppressed with typed | `_verify_entities` always appends wrong when wrong rows |
| Entity physical-row collapse | `elementId(n)` + element_id dedup |
| GATE-05 false green | Report + this independent pass align |

---

_Verified: 2026-07-17T00:35:00Z_
_Verifier: Claude (gsd-verifier)_
