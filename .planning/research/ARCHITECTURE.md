# Architecture Research

**Domain:** v1.2 FE/BO Catalog Pilot and Object Context (Graphiti MCP catalog-v2)
**Researched:** 2026-07-24
**Confidence:** HIGH (repo-sourced live modules, `catalog/catalog.json` shape, v1.1 shipped surface)
**Consumer:** roadmapper / phase planner — integration map + minimum build order

## Standard Architecture

### System Overview

v1.1 already ships full deterministic write/read substrate. v1.2 is **additive and thin**:

1. **Offline converter/sampler** turns fixed `catalog/catalog.json` into catalog-v2 prepare payloads (representative FE connected slice + BO structural slice).
2. **Existing prepare → token-only commit** ingests those payloads into a **new isolated group**.
3. **One new read-only MCP tool** returns exact object context (typed object + bounded 1-hop neighbors + evidence locators).
4. **Delta acceptance runner + source-bound image smoke** prove changed v1.2 behavior without repeating v1.1 final canary.

No LLM. No queue. No Docling. No full 1,261-table ingest. No BO invented relationships (catalog has none for MAIN1).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ OFFLINE (host / CI) — never inside FastMCP request path                      │
│  catalog/catalog.json  (authority; 1261 tables, 434 SVFE FKs, 2 docs)         │
│       │                                                                      │
│       ▼                                                                      │
│  scripts/build_catalog_pilot_requests.py   NEW                               │
│    validate JSON → sample FE+BO → map v2 keys → hash via CatalogService      │
│    pure helpers → emit catalog/pilot-v12-requests/*                          │
│       │                                                                      │
│       ▼                                                                      │
│  scripts/run_catalog_pilot_acceptance.py   NEW (delta smoke, not v1.1 canary)│
│    prepare_catalog_batch → commit_prepared_catalog_batch (token only)        │
│    → get_catalog_object_context smoke → write receipts under run dir         │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ MCP / HTTP tool calls only
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ MCP TRANSPORT — mcp_server/src/graphiti_mcp_server.py                        │
│ UNCHANGED: 14 legacy semantic + 14 catalog-v2 tools (prepare/commit/resolve/ │
│   evidence/manifest/capabilities/…)                                          │
│ NEW (1): get_catalog_object_context                                          │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ thin adapter; Pydantic in/out; no Cypher
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ CatalogService  (MODIFY: +get_catalog_object_context only for context path)  │
│   _read_gate → uuid5 identity → store reads → assemble compact DTO           │
│   REUSE: prepare_catalog_batch / commit_prepared_catalog_batch unchanged     │
│   DOES NOT call LLMClient / QueueService / Graphiti.add_episode|add_triplet  │
└───────────┬──────────────────────────────┬───────────────────────────────────┘
            │ (writes: existing)           │ (object context: read-only)
            ▼                              ▼
┌──────────────────────┐   ┌───────────────────────────────────────────────────┐
│ EmbedderClient       │   │ CatalogNeo4jStore                                 │
│ commit path only     │   │ REUSE: get_entity_by_uuid, get_edge_by_uuid,      │
│                      │   │   match_entities_for_resolve, evidence page reads │
│                      │   │ NEW: bounded 1-hop neighbor fetch (group_id +     │
│                      │   │   LIMIT; fixed RELATES_TO; no dynamic labels)     │
└──────────────────────┘   └───────────────────────┬───────────────────────────┘
                                                   ▼
                               Neo4j 5.26+  group_id-partitioned domain + control
```

### Component Responsibilities

| Component | Status | Responsibility |
|-----------|--------|----------------|
| `catalog/catalog.json` | REUSE (read-only authority) | Normalized FE+BO catalog; no Docling regen |
| `scripts/build_catalog_pilot_requests.py` | NEW | Deterministic sample + convert → v2 prepare artifacts |
| Pure mapping helpers (script-local or `scripts/catalog_pilot_convert.py`) | NEW | Table/column/constraint/index/FK → entity/edge/evidence items; FE/BO plane keys |
| `catalog/pilot-v12-requests/` | NEW artifacts | Versioned payloads + manifest digests; not golden v1.1 dirs |
| `scripts/run_catalog_pilot_acceptance.py` | NEW | Isolated-group prepare/commit + object-context smoke + receipts |
| FastMCP `get_catalog_object_context` | NEW | Thin adapter; mirror `get_catalog_evidence` init/gate pattern |
| `models/catalog_object_context.py` | NEW | Strict request/response DTOs (`extra=forbid`) |
| `models/catalog_responses.py` / `catalog_common.py` | MODIFY (minimal) | Shared compact types if needed; neighbor/evidence hard caps |
| `services/catalog_service.py` | MODIFY | `get_catalog_object_context` orchestration only |
| `services/catalog_store.py` | MODIFY | One bounded neighbor read helper |
| `services/catalog_capabilities.py` | MODIFY | Advertise `object_context` + bounds |
| `config/schema.py` CatalogConfig | MODIFY (optional) | Neighbor/evidence default caps |
| Existing prepare/commit/identity/manifest/evidence | UNCHANGED | Ingest path already correct |
| Canary builder / hardened goldens / Phase 6 runner | UNCHANGED | Historical authority; do not overload for pilot |
| QueueService / LLM / `search_nodes` for context | OUT OF PATH | Object context is exact identity, not semantic search |

## Recommended Project Structure

```
catalog/
├── catalog.json                         # REUSE authority (do not rewrite)
├── canary-v2-requests/                  # FROZEN historical — do not write
├── canary-v2-requests-hardened/         # FROZEN v1.1 golden — do not write
└── pilot-v12-requests/                  # NEW pilot artifacts only
    ├── manifest.json
    ├── fe-connected.payload.json
    └── bo-structural.payload.json

scripts/
├── build_catalog_canary_requests.py     # UNCHANGED (patterns to copy)
├── build_catalog_pilot_requests.py      # NEW converter/sampler CLI
├── catalog_pilot_convert.py             # NEW optional pure helpers
├── run_catalog_canary_batch.py          # UNCHANGED — not v1.2 acceptance driver
└── run_catalog_pilot_acceptance.py      # NEW delta acceptance runner

mcp_server/src/
├── graphiti_mcp_server.py               # MODIFY: register get_catalog_object_context
├── config/schema.py                     # MODIFY: optional neighbor/evidence caps
├── models/
│   ├── catalog_object_context.py        # NEW request/response
│   ├── catalog_common.py                # MODIFY: HARD_MAX_OBJECT_CONTEXT_* if needed
│   └── catalog_responses.py             # MODIFY only if sharing compact types
└── services/
    ├── catalog_service.py               # MODIFY: get_catalog_object_context
    ├── catalog_store.py                 # MODIFY: fetch_object_neighbors_bounded
    └── catalog_capabilities.py          # MODIFY: feature + limits echo

mcp_server/tests/
├── test_catalog_object_context.py       # NEW unit
├── test_catalog_pilot_convert.py        # NEW pure converter tests (no Neo4j)
├── test_catalog_object_context_int.py   # NEW live Neo4j; group isolation
└── fixtures/
    └── pilot_fe_bo_slice.json           # NEW tiny synthetic slice for unit tests
```

### Structure Rationale

- **Offline scripts own `catalog.json`:** Server must not open 18MB authority or sample on request path.
- **New artifact directory:** Protects frozen v1.1 hardened/historical canary bytes.
- **One model module for object context:** Avoid bloating large entity/response modules; import `CompactEvidenceLink` if shared.
- **Store gains one read helper only:** Server-owned parameterized Cypher; no second store abstraction.
- **Acceptance runner separate from Phase 6 canary:** Different gates/group policy; not Gates 0–10 replay.

## Architectural Patterns

### Pattern 1: Offline authority → prepare-shaped artifact

**What:** Host script reads frozen JSON, validates, samples, maps to prepare/upsert field set, fills `content_sha256` via existing `CatalogService.*_canonical_payload` + `canonical_sha256`, writes canonical LF JSON + manifest digests.

**When:** catalog.json → graph ingest must stay deterministic and reviewable.

**Trade-offs:** Extra artifact step vs in-server convert. Artifact wins: reviewable digests, no server IO, testable offline.

**Example shape (FE table key):**

```text
entity_type=Table
graph_key=TABLE::FE::ORCL.SVFE_SHB.ACCEPT_TAB
system_key=FE
identity_schema_version=catalog-v2
```

BO uses `::BO::` and `system_key=BO`. Database segment is fixed converter constant (e.g. `ORCL`) — grammar requires `DB.SCHEMA.NAME`; raw catalog only has `schema` + `name`.

### Pattern 2: Thin MCP adapter → CatalogService → CatalogStore

**What:** `@mcp.tool` checks service init, calls one service method, maps exceptions to `ErrorResponse`. Validation/gates/Cypher live below.

**When:** Every catalog tool (existing pattern ~1346–1709 in `graphiti_mcp_server.py`).

**Trade-offs:** None — copy `get_catalog_evidence` read-only init (`require_initialized_client`, no `get_client` bootstrap side effects).

### Pattern 3: Compose exact reads; do not invent search dialect

**What:** Object context = deterministic UUID probe + bounded `RELATES_TO` 1-hop + existing evidence page. Reuse `catalog_entity_uuid`, `_read_gate`, `HARD_MAX_PAGE_SIZE`.

**When:** Agent needs exact object + immediate touches + audit locators.

**Trade-offs:** Weaker than multi-hop impact (out of scope). Stronger than `search_nodes` (exact, typed, no LLM rank).

### Pattern 4: Isolated group + protected-group reject

**What:** Pilot groups reject protected ids (`oracle-catalog-v2`, `oracle-core`, `main`, …). Prefer dedicated `oracle-catalog-v12-pilot-test` for live pilot if parallel CI matters; never touch live canary groups.

**When:** Any write path in tests or acceptance.

## Data Flow

### A. Convert + sample (offline)

```
catalog/catalog.json
  → strict_json (reject BOM/dup keys/non-finite)
  → authority sha256 pin (record in manifest; fail on drift)
  → FE sampler: connected SVFE_SHB slice
       tables + columns + constraints + indexes
       FKs only when BOTH endpoints in sample
       DictionaryDocument FE doc docling-14451470779352042667
       Schema + Contains + DocumentedBy + PrimaryKeyOf + ForeignKeyTo
       system_key=FE; keys PREFIX::FE::ORCL.<SCHEMA>.<...>
  → BO sampler: structurally rich MAIN1 table(s)
       columns/PK/indexes/constraints only
       DictionaryDocument BO doc docling-15867609475948615210
       NO relationship edges (catalog relationships are SVFE→SVFE only)
       system_key=BO; keys PREFIX::BO::ORCL.MAIN1.<...>
  → explicit evidence_links (one source → each entity/edge target); no Cartesian fields
  → content_sha256 via CatalogService canonical payloads
  → PrepareCatalogBatchRequest.model_validate
  → atomic write catalog/pilot-v12-requests/{fe,bo,manifest}
```

**FE connected (minimum):** ≥1 Table, its Columns, ≥1 PK/constraint path, ≥1 `ForeignKeyTo` with both column endpoints in same batch (or ordered two-batch with manifest dependency). Prefer small closed subgraph over historical ACCEPT_TAB 38/85 set.

**BO structural (minimum):** one MAIN1 table with many columns + PK + indexes, child Columns, Contains, DocumentedBy, source_refs page/raw_text preserved. No FK requirement.

### B. Ingest (runtime — existing tools)

```
pilot payload
  → prepare_catalog_batch (immutable plan, no domain write)
  → commit_prepared_catalog_batch (token only; embed then one domain tx)
  → optional: status / verify / manifest
```

### C. Object context (runtime — new tool)

```
GetCatalogObjectContextRequest
  { group_id, entity_type, graph_key, neighbor_limit?, evidence_limit?, offset? }
  → _read_gate(group_id)
  → catalog_entity_uuid(ns, group_id, type, key)
  → store.get_entity_by_uuid  (found_target; no create)
  → store.fetch_object_neighbors_bounded
       MATCH (n:Entity {uuid, group_id})-[r:RELATES_TO]-(m:Entity {group_id})
       WHERE r.group_id = $group_id
       RETURN direction, r, m
       ORDER BY r.edge_key
       LIMIT $neighbor_limit
  → evidence page for entity target (reuse get_catalog_evidence internals)
  → GetCatalogObjectContextResponse
       object | null
       neighbors[]   (bounded; truncated flag)
       evidence[]    (compact; page/raw excerpt only)
       bounds{ neighbor_limit, evidence_limit, neighbors_truncated, evidence_total }
       error_code?   (structured; not exception)
```

**Query bounds (explicit):**

| Bound | Default | Hard max | Notes |
|-------|---------|----------|-------|
| `neighbor_limit` | 50 | 200 | 1-hop only; both directions; stable order |
| `evidence_limit` | config `max_page_size` | `HARD_MAX_PAGE_SIZE` (500) | Same as evidence tool |
| `evidence_offset` | 0 | — | Pagination only; no full dump |
| Response payload | — | omit embeddings, raw source JSON, plan tokens | Compact only |
| Hops | 1 | 1 | Multi-hop / path / impact = later milestone |

### D. Acceptance (offline driver)

```
build artifacts (or verify pinned digests)
  → source-bound image / cleanroom (new run id)
  → isolated group_id (reject protected)
  → one prepare + one token commit per pilot batch (FE then BO if split)
  → get_catalog_object_context on 1 FE table + 1 FE column + 1 BO table
  → assert found, neighbor bound respected, evidence locators when source_refs existed
  → write run-manifest + receipts; non-zero on mismatch
  → DO NOT clear_graph; DO NOT touch oracle-catalog-v2; DO NOT rerun v1.1 Gates 0–10
```

### State Management

- Server stateless between calls aside from driver/embedder clients.
- Prepared plans / manifests / evidence stay on existing control-plane labels.
- Object context introduces **no new control-plane label**.
- Pilot artifacts immutable once pinned (refuse overwrite on digest drift).

### Key Data Flows (summary)

1. **Authority → artifact:** `catalog.json` → sampled v2 payloads + sha256 manifest.
2. **Artifact → graph:** prepare/commit existing path; embeddings only at commit.
3. **Graph → agent context:** exact uuid → bounded neighbors + evidence page.
4. **Acceptance → evidence:** runner receipts prove v1.2 deltas only.

## New vs Modified Files

### New

| Path | Role |
|------|------|
| `scripts/build_catalog_pilot_requests.py` | CLI sampler/converter |
| `scripts/catalog_pilot_convert.py` | Pure mapping (optional split for tests) |
| `scripts/run_catalog_pilot_acceptance.py` | Delta acceptance runner |
| `catalog/pilot-v12-requests/*` | Generated payloads + manifest |
| `mcp_server/src/models/catalog_object_context.py` | Request/response models |
| `mcp_server/tests/test_catalog_object_context.py` | Unit tests |
| `mcp_server/tests/test_catalog_pilot_convert.py` | Converter unit tests |
| `mcp_server/tests/test_catalog_object_context_int.py` | Neo4j integration |
| `mcp_server/tests/fixtures/pilot_fe_bo_slice.json` | Tiny synthetic authority slice |

### Modified (surgical)

| Path | Change |
|------|--------|
| `mcp_server/src/graphiti_mcp_server.py` | Register `get_catalog_object_context` |
| `mcp_server/src/services/catalog_service.py` | Add `get_catalog_object_context` method |
| `mcp_server/src/services/catalog_store.py` | Add bounded neighbor fetch |
| `mcp_server/src/services/catalog_capabilities.py` | Feature flag + limits |
| `mcp_server/src/config/schema.py` | Optional caps on CatalogConfig |
| `mcp_server/src/models/catalog_common.py` | Hard caps / error code if required |

### Explicitly not modified

- Identity grammar / UUIDv5 (`catalog_graph_key.py`, `catalog_identity.py`) — already FE/BO/COMMON.
- Prepare/commit/manifest/evidence write protocols.
- Historical `catalog/canary-v2-requests*`, Phase 6 canary scripts, frozen image digest claims.
- Legacy 14 semantic tools; `add_memory` queue.
- Full-catalog ingest; BO relationship invention; multi-hop tools.

## Dependency-Ordered Build Sequence

Minimum phases for roadmapper (each gateable):

| Order | Work package | Depends on | Exit criteria |
|------:|--------------|------------|---------------|
| **1** | Object-context **models** + hard caps + capabilities stubs | nothing | Pydantic forbid-unknown; reject bad group_id/limits |
| **2** | Store **bounded neighbor** read + unit test (fake driver) | 1 | Parameterized Cypher; `group_id` required; LIMIT; no label injection |
| **3** | Service **`get_catalog_object_context`** + unit tests (mock store) | 1–2 | found/missing; truncation flags; no embedder/write |
| **4** | MCP **tool registration** + tool-list assertion | 3 | Tool visible; thin adapter; read-only init |
| **5** | **Converter/sampler** pure functions + unit tests on tiny fixture | existing models | Model-valid v2 payloads; FE/BO planes; explicit evidence_links; stable hashes |
| **6** | **Build pilot artifacts** from real `catalog.json` + manifest pins | 5 | FE connected + BO structural files; digest pin; refuse overwrite drift |
| **7** | **Integration**: prepare/commit pilot + object_context_int | 4, 6 | Commit ok; context returns neighbors/evidence; no protected-group writes |
| **8** | **Acceptance runner** (delta smoke) | 6–7 | One-command offline→runtime proof; receipts; fail on regression |
| **9** | **Source-bound image** + runtime smoke for new tool | 4, 8 | Image lists new tool; smoke prepare/context; **not** v1.1 final canary replay |

**Parallelism:** 1→4 (context path) parallel with 5→6 (converter/artifacts); join at 7.

**Do not start:** image promotion, live `oracle-catalog-v2` writes, full catalog load, Docling, multi-hop, FE↔BO mapping edges.

## Scaling Considerations

| Scale | Approach |
|-------|----------|
| Pilot slice (tens of entities) | One prepare/commit batch each for FE and BO; under 500/2000 limits |
| Hundreds of neighbors on hot table | Hard neighbor LIMIT + `truncated=true`; page via resolve/evidence |
| Full 1261 tables | Out of scope; converter never defaults to full dump |
| Concurrent acceptance runs | Distinct `group_id` per run_id |

### Scaling Priorities

1. **First bottleneck:** Oversized BO columns explode batch — sampler caps and fails closed over limits.
2. **Second bottleneck:** Hot-node fan-out — hard LIMIT in store query, never unbounded MATCH.

## Anti-Patterns

### Anti-Pattern 1: Converter inside CatalogService / MCP tool

**What people do:** `ingest_catalog_json` tool reading host path or full blob.
**Why wrong:** 18MB IO on server, blows limits, skips reviewable artifacts.
**Instead:** Offline script → small prepare payloads → existing prepare/commit.

### Anti-Pattern 2: Reuse `search_nodes` as object context

**What people do:** Semantic search by name for "context."
**Why wrong:** Non-exact, embedding-dependent, not evidence-addressable.
**Instead:** UUIDv5 + typed resolve + 1-hop RELATES_TO + evidence links.

### Anti-Pattern 3: Extend v1.1 canary runner / hardened golden dir

**What people do:** Flags on `run_catalog_canary_batch.py` or write into `canary-v2-requests-hardened/`.
**Why wrong:** Contaminates frozen authority; invites canary rerun.
**Instead:** New pilot artifact dir + new acceptance script.

### Anti-Pattern 4: v1 graph keys (`TABLE::SVFE_SHB.X`) in pilot payloads

**What people do:** Copy historical builder keys without FE/BO plane.
**Why wrong:** Fail closed under catalog-v2 grammar; dual-identity risk.
**Instead:** Always `PREFIX::{FE|BO|COMMON}::DB.SCHEMA…` with shell `system_key`.

### Anti-Pattern 5: Invent BO relationships or FE↔BO maps

**What people do:** Infer MAIN1 FKs or SVFE↔MAIN1 links.
**Why wrong:** Fabricates graph truth; relationships are SVFE-only.
**Instead:** BO sample structural only.

### Anti-Pattern 6: Unbounded neighbor query

**What people do:** `MATCH (n)-[r]-(m) RETURN *` without LIMIT/order.
**Why wrong:** Memory/timeouts; non-deterministic response.
**Instead:** Parameter LIMIT, stable ORDER BY, `truncated` flag.

### Anti-Pattern 7: Object context writes or schema ensure

**What people do:** Write gate or `ensure_constraints` on read.
**Why wrong:** Mutates under "context" calls.
**Instead:** `_read_gate` only; same posture as `get_catalog_evidence`.

### Anti-Pattern 8: Duplicate abstraction layers

**What people do:** New `ObjectContextService`, second store, parallel identity module.
**Why wrong:** Drift; YAGNI.
**Instead:** One CatalogService method, one store helper, one MCP tool.

## Integration Points

### External Services

| Service | Integration | Notes |
|---------|-------------|-------|
| Neo4j 5.26+ | Existing async driver via GraphitiService client | Object context: reads only |
| Embedder | Commit path only | Object context never embeds |
| Host filesystem | Offline scripts only | Authority + artifact dirs |
| Docker/compose cleanroom | Acceptance + image smoke | Source-bound build; rebuild ≠ old digest |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Script → MCP models/services | `sys.path` import + `CatalogService.*_canonical_payload` | Same as canary builder |
| MCP tool → CatalogService | Direct await | No queue |
| CatalogService → CatalogStore | Driver + params | Server-owned Cypher only |
| Object context → Evidence | Shared helpers | Do not fork evidence schema |
| Pilot runner → tools | MCP/HTTP client | Token never logged |

### Catalog.json facts that drive design

| Fact | Implication |
|------|-------------|
| 2 documents: SVFE PDF + SVBO PDF | FE vs BO plane + two DictionaryDocument entities |
| Schemas `SVFE_SHB` (637) + `MAIN1` (624) | FE sample SVFE_SHB; BO sample MAIN1 |
| 434 relationships, all SVFE→SVFE | FE can be connected; BO cannot use relationship records |
| `source_refs` carry `document_id`, `page`, `raw_text` | Map 1:1 to CatalogSourceRef / evidence excerpts |
| Table id form `SCHEMA.NAME` | Converter supplies fixed DB segment for v2 key body |
| ~18MB file | Never load in MCP request path |

## Confidence Assessment

| Area | Level | Notes |
|------|-------|-------|
| Existing substrate reuse | HIGH | Live tools/service/store/models inspected |
| Converter placement offline | HIGH | Matches canary builder + PROJECT constraints |
| Object-context composition | HIGH | Resolve + evidence exist; neighbors need one store query |
| Sample selection specifics | MEDIUM | Exact FE/BO table ids left to phase design; bounds fixed here |
| Acceptance vs canary split | HIGH | PROJECT forbids repeating v1.1 final canary |
| Config flag names | MEDIUM | Caps may be constants-only if config change unwanted |

## Gaps for Phase-Level Design

- Exact FE table ID set; prefer **one batch** if under limits vs table+FK split.
- Exact BO table id (column-rich MAIN1) and max columns if trimming needed.
- Fixed database token (`ORCL` vs product-specific) — constant in converter + manifest.
- Pilot integration group: `oracle-catalog-tool-test` vs `oracle-catalog-v12-pilot-test`.
- Image/smoke: minimal new launcher vs copy of Phase 6 helpers (prefer minimal; not full canary).

## Sources

- `.planning/PROJECT.md` — v1.2 goal, constraints, out-of-scope
- `mcp_server/src/graphiti_mcp_server.py` — tool surface + adapter pattern
- `mcp_server/src/services/catalog_service.py` — prepare/commit, resolve, evidence
- `mcp_server/src/services/catalog_store.py` — entity/edge/evidence primitives
- `mcp_server/src/models/catalog_graph_key.py` — `PREFIX::{FE|BO|COMMON}::` grammar
- `mcp_server/src/models/catalog_entities.py` / `catalog_responses.py` — DTOs, CompactEvidenceLink
- `scripts/build_catalog_canary_requests.py` — offline convert/hash/manifest patterns
- `mcp_server/tests/fixtures/accept_tab_sanitized.json` — v2 key shape reference
- `catalog/catalog.json` — 1261 tables, schema split, relationship asymmetry, dual documents

---
*Architecture research for: v1.2 FE/BO Catalog Pilot and Object Context*
*Researched: 2026-07-24*
*Confidence: HIGH*
