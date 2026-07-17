# Architecture Research

**Domain:** Deterministic catalog-ingestion MCP tools (Graphiti MCP extension)
**Researched:** 2026-07-16
**Confidence:** HIGH

## Standard Architecture

### System Overview

Seven new MCP tools sit **beside** existing semantic tools. They do **not** go through `Graphiti.add_episode` / `QueueService` / LLM extraction. They share the live `GraphitiService` client (driver + embedder + `group_id`) and write Neo4j with server-owned Cypher.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ MCP TRANSPORT (FastMCP)                                                    │
│  mcp_server/src/graphiti_mcp_server.py                                     │
│  EXISTING: add_memory, search_nodes, search_memory_facts, add_triplet, ... │
│  NEW: upsert_typed_entities | resolve_typed_entities | upsert_typed_edges  │
│       verify_catalog_batch | upsert_provenance | upsert_catalog_batch      │
│       get_catalog_ingest_status                                            │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │ sync await (no queue)
                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ MCP BOUNDARY                                                               │
│  models/catalog_*   strict Pydantic request/response + error codes         │
│  services/catalog_service.py   orchestration, feature gate, batch status   │
│  (does NOT call LLMClientFactory / QueueService)                           │
└───────────────┬───────────────────────────────┬────────────────────────────┘
                │                               │
                │ embedder.create_batch         │ Neo4j writes
                ▼                               ▼
┌──────────────────────────┐   ┌─────────────────────────────────────────────┐
│ EmbedderClient           │   │ CatalogNeo4jStore (dedicated persistence)   │
│ graphiti_core/embedder/  │   │ mcp_server/src/services/catalog_store.py    │
│ (pre-tx only)            │   │ uses driver.transaction() + fixed Cypher    │
└──────────────────────────┘   │ reuses: Entity/Episodic labels, RELATES_TO, │
                               │ MENTIONS, name_embedding, fact_embedding    │
                               │ NEW: CatalogIngestBatch (non-Entity)        │
                               └──────────────────┬──────────────────────────┘
                                                  │
                                                  ▼
                               ┌─────────────────────────────────────────────┐
                               │ Neo4j 5.26+  (Neo4jDriver)                  │
                               │ graphiti_core/driver/neo4j_driver.py        │
                               └─────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| FastMCP tool functions | Protocol surface, thin adapters | `@mcp.tool()` in `graphiti_mcp_server.py` (or thin import/register from `catalog_tools.py`) |
| Catalog request models | Allowlists, limits, hash/prefix/UUID validation | New `mcp_server/src/models/catalog_*.py` (Pydantic `BaseModel`, not TypedDict) |
| Catalog response models | Structured success + item-level errors | Extend pattern of `models/response_types.py` with typed error codes |
| `CatalogService` | Feature gate, UUIDv5 identity, SHA-256 audit, embed-then-tx ordering, status nodes | New `mcp_server/src/services/catalog_service.py` |
| `CatalogNeo4jStore` | Parameterized Neo4j Cypher inside real transactions | New `mcp_server/src/services/catalog_store.py` (Neo4j-first; **dedicated persistence required**) |
| `CatalogConfig` | Immutable UUID namespace + batch limits + enable flag | Extend `mcp_server/src/config/schema.py` |
| Existing `GraphitiService` | Provide live `Graphiti` client (`driver`, `embedder`) | Reuse `GraphitiService.client` — do not re-init drivers |
| Existing search tools | Interop only (`search_nodes` / `search_memory_facts`) | Unchanged; catalog entities must be `Entity` + `name_embedding` searchable |
| Existing `QueueService` | Semantic episode queue | **Out of path** for all seven tools |

## Recommended Project Structure

```
mcp_server/
├── src/
│   ├── graphiti_mcp_server.py          # register 7 tools; keep existing tools untouched
│   ├── config/
│   │   └── schema.py                   # + CatalogConfig (namespace, limits, enabled)
│   ├── models/
│   │   ├── entity_types.py             # existing semantic extraction types (do not overload)
│   │   ├── response_types.py           # existing TypedDicts
│   │   ├── catalog_entities.py         # allowlisted entity request items
│   │   ├── catalog_edges.py            # allowlisted edge request items
│   │   ├── catalog_provenance.py       # source / link / batch models
│   │   └── catalog_responses.py        # structured results + error codes
│   ├── services/
│   │   ├── factories.py                # reuse EmbedderFactory / DatabaseDriverFactory
│   │   ├── queue_service.py            # DO NOT use for catalog writes
│   │   ├── catalog_service.py          # orchestration (Phase 1 + 2)
│   │   ├── catalog_identity.py         # UUIDv5 + canonical SHA-256 helpers
│   │   └── catalog_store.py            # Neo4j Cypher + transaction boundaries
│   └── utils/
│       └── formatting.py               # optional to_node_result reuse for search interop
└── tests/
    ├── test_catalog_models.py          # unit: validation / allowlists / hashes
    ├── test_catalog_identity.py        # unit: UUIDv5 determinism
    ├── test_catalog_service.py         # unit: embed-before-tx ordering (mocked)
    └── test_catalog_neo4j_int.py       # Neo4j integration, group_id=oracle-catalog-tool-test
```

### Structure Rationale

- **Keep tools in MCP package, not `graphiti_core`:** catalog allowlists and admin semantics are MCP-product concerns; core remains general-purpose.
- **Dedicated `catalog_store.py`:** required. Stock `EntityNode.save` / `get_entity_node_save_query` uses `SET n = $entity_data` and label interpolation that loses `updated_at`/`content_hash` control, drops non-allowlisted property discipline, and is not multi-statement atomic for entity+edge+provenance batches. Neo4j ops accept `tx=` but bulk episode path (`add_nodes_and_edges_bulk`) still embeds *inside* the write session and can create generic endpoints via `add_triplet`.
- **Separate models from semantic `entity_types.py`:** catalog types (Table, Column, …) are identity allowlists, not LLM extraction schemas.
- **Status nodes outside Entity search:** label `CatalogIngestBatch` only (no `:Entity`) so `search_nodes` / fulltext entity indexes ignore them.

## Architectural Patterns

### Pattern 1: Thin MCP tool → service → store

**What:** `@mcp.tool` validates via Pydantic, calls `CatalogService`, returns structured dict. No Cypher in tool body.
**When to use:** All seven tools.
**Trade-offs:** Extra module vs. monolithic `graphiti_mcp_server.py` (already large). Clear test seams.

**Example:**
```python
@mcp.tool()
async def upsert_typed_entities(request: UpsertTypedEntitiesRequest) -> CatalogWriteResponse | ErrorResponse:
    if graphiti_service is None:
        return ErrorResponse(error='Graphiti service not initialized')
    return await catalog_service.upsert_typed_entities(graphiti_service.client, request)
```

### Pattern 2: Embed before open transaction

**What:** Call configured `embedder.create_batch` / name+fact embedding helpers **before** `async with driver.transaction()`. Fail with `embedding_failed` without touching Neo4j.
**When to use:** Every write that stores `name_embedding` or `fact_embedding`.
**Trade-offs:** Embeddings not rolled back with graph (acceptable: pure functions of text). Avoids partial graph writes on embed timeout.

**Ordering (hard):**
1. Full request validation (Pydantic + business rules)
2. Deterministic identity (UUIDv5) + content hash
3. Endpoint existence checks (reads; outside write tx or first statements that only MATCH)
4. **Embeddings**
5. **Single write transaction** (MERGE/SET domain data)
6. Commit → return; exception → rollback → `neo4j_transaction_failed`

### Pattern 3: Server-owned Cypher with fixed labels

**What:** Labels, relationship types, and property keys come only from server allowlists. Parameters carry values. Never interpolate client strings into label positions (beyond validated allowlist members already checked by `validate_node_labels` pattern).
**When to use:** All catalog Cypher.
**Trade-offs:** Less flexible than generic property maps; required for injection safety and schema stability.

### Pattern 4: Deterministic identity (UUIDv5 + SHA-256)

**What:**
- Entity: `uuid5(namespace, f"{group_id}|{entity_type}|{graph_key}")`
- Edge: `uuid5(namespace, f"{group_id}|{edge_type}|{edge_key}")`
- Source: `uuid5(namespace, f"{group_id}|Source|{source_key}")`
- Batch: `uuid5(namespace, f"{group_id}|Batch|{batch_id}")`
- Payload: canonical JSON → SHA-256 hex (64 lowercase); MD5 forbidden
**When to use:** All upserts and verifiers.
**Trade-offs:** Namespace is immutable deployment config (`GRAPHITI_CATALOG_UUID_NAMESPACE`). Caller UUIDs never authority.

### Pattern 5: Provenance via installed episodic schema (Phase 2)

**What:** Reuse `Episodic` nodes + `MENTIONS` edges (`EPISODIC_EDGE_SAVE`) and `EntityEdge.episodes` list when linking facts — **not** `add_episode` / LLM / queue.
**When to use:** `upsert_provenance` and batch orchestration.
**Trade-offs:** If a desired link shape is unsupported, document closest compatible form; do not invent parallel provenance labels.

## Data Flow

### Request Flow — Phase 1 write (`upsert_typed_entities` / `upsert_typed_edges`)

```
MCP client
  → FastMCP tool (sync await)
  → CatalogService.validate (Pydantic + limits + allowlists + hashes)
  → CatalogService.identity (UUIDv5)
  → CatalogStore.read checks (typed endpoints / conflicts)   [read path]
  → EmbedderClient.create_batch                              [outside tx]
  → Neo4jDriver.transaction()
       → MERGE Entity {uuid} SET labels + props + vector
       → or MATCH endpoints + MERGE RELATES_TO {uuid}
  → commit
  → structured response (created/updated/unchanged + item errors)
```

### Request Flow — Phase 1 read (`resolve_typed_entities` / `verify_catalog_batch`)

```
MCP client → tool → CatalogService.validate → CatalogStore MATCH-only queries
  → report missing / generic / duplicate / mistyped / uuid-mismatch / unembedded
  → no writes, no embeddings
```

### Request Flow — Phase 2 batch (`upsert_catalog_batch`)

```
validate entire batch (entities + edges + provenance + limits)
resolve same-request endpoints in memory (graph_key → uuid map)
embed ALL domain texts
open ONE domain write transaction:
  entities → edges → provenance (Episodic + MENTIONS + edge.episodes)
commit domain tx
separately persist CatalogIngestBatch status
  success: status=committed
  failure after domain rollback: status=failed (best-effort second write; never re-open domain data)
return batch result + get_catalog_ingest_status-compatible fields
```

### State Management

- Graph state: Neo4j only. Service process is stateless beyond live `Graphiti` client.
- Batch status: `(:CatalogIngestBatch {uuid, group_id, batch_id, status, ...})` — restart-safe, not searchable as Entity.
- Semantic queue (`QueueService`): unused; `add_memory` remains async and unchanged.

### Key Data Flows

1. **Typed entity upsert:** catalog item → UUIDv5 → name embed → MERGE `:Entity:Table` (etc.) with `group_id`, `name`, `name_raw`, `name_canonical`, `graph_key`, `content_hash`, `created_at` preserved / `updated_at` set.
2. **Typed edge upsert:** require both endpoints exist with expected labels → fact embed → MERGE `(a)-[:RELATES_TO {uuid}]->(b)` with `name` = edge type, `fact`, `fact_embedding`, no implicit endpoint create.
3. **Provenance:** create/merge `Episodic` source records + `MENTIONS` to entities; attach episode uuid onto related `EntityEdge.episodes` when facts are covered.
4. **Search interop:** entities remain `Entity` with `name_embedding` so existing `search_nodes` hybrid path works; status nodes omit `Entity` label.

## Transaction Boundaries

| Operation | Transaction scope | Embed timing | Notes |
|-----------|-------------------|--------------|-------|
| `upsert_typed_entities` | One write tx for all entities in request | Before tx | Item-level validation errors may short-circuit pre-tx; post-embed failures roll back all |
| `upsert_typed_edges` | One write tx for all edges | Before tx | Endpoint checks fail closed with `missing_endpoint` / `generic_endpoint_conflict` |
| `resolve_typed_entities` | Read-only (no tx / auto-commit reads) | None | |
| `verify_catalog_batch` | Read-only | None | Optional provenance checks |
| `upsert_provenance` | One write tx | Only if source text needs embedding (prefer episodic content without entity-name re-embed unless required) | No LLM; no queue |
| `upsert_catalog_batch` | **One atomic domain tx** for entities+edges+provenance | All embeddings before domain tx | Status node write **outside** domain tx so failed status can persist after rollback |
| `get_catalog_ingest_status` | Read-only | None | |

**Neo4j primitive:** `Neo4jDriver.transaction()` → `_Neo4jTransaction` (`neo4j_driver.py:151-161, 228-235`). Commit on clean exit; rollback on exception.

**Do not use for catalog domain writes:**
- `QueueService.add_episode` / `add_memory` (async + LLM)
- `Graphiti.add_triplet` (can create generic endpoints; may call LLM resolve)
- `add_nodes_and_edges_bulk` alone (embeds inside write session; not catalog-identity aware)

## Schemas / Index Constraints

### Reused Graphiti baseline (do not break)

| Kind | Neo4j shape | Source |
|------|-------------|--------|
| Entity node | `(:Entity:Label {uuid, name, group_id, name_embedding, summary, created_at, ...attrs})` | `nodes.py` `EntityNode`, `get_entity_node_save_query` |
| Entity edge | `()-[:RELATES_TO {uuid, name, fact, fact_embedding, group_id, episodes, valid_at, invalid_at, created_at, ...}]->()` | `edges.py` `EntityEdge`, `get_entity_edge_save_query` |
| Episode / provenance | `(:Episodic {uuid, name, group_id, source, source_description, content, entity_edges, created_at, valid_at})` | `get_episode_node_save_query` |
| Mention | `(:Episodic)-[:MENTIONS {uuid, group_id, created_at}]->(:Entity)` | `EPISODIC_EDGE_SAVE` |
| Range indexes | uuid / group_id / name / temporal on Entity, Episodic, RELATES_TO, MENTIONS | `graph_queries.get_range_indices` |
| Fulltext | Entity name/summary/group_id; edge name/fact/group_id; episode content/source | `get_fulltext_indices` |

### Catalog-specific properties (server-owned)

On Entity (in addition to Graphiti fields): `graph_key`, `entity_type`, `name_raw`, `name_canonical`, `content_hash`, `updated_at` (preserve original `created_at` on retry).

On RELATES_TO: `edge_key`, `edge_type` (mirror `name`), `content_hash`, `updated_at`, endpoint type metadata as needed — never free-form client property names.

### New label (Phase 2)

```
(:CatalogIngestBatch {
  uuid,              // UUIDv5(group_id|Batch|batch_id)
  group_id,
  batch_id,
  status,            // pending|committed|failed|conflict
  content_hash,
  entity_count, edge_count, provenance_count,
  error_code, error_message,  // safe summaries only
  created_at, updated_at
})
```

Indexes (add in catalog store bootstrap, IF NOT EXISTS):
- `CatalogIngestBatch(uuid)`, `(group_id, batch_id)`, `(group_id, status)`
- Optional uniqueness: composite uniqueness on `(group_id, graph_key)` for entities if Neo4j edition allows; otherwise enforce in application with conflict detection queries (Community often lacks multi-property node key — plan app-level checks).

### Allowlists (identity + Cypher safety)

**Entity types / prefixes:** Database `DATABASE::`, DictionaryDocument `DOC::`, Schema `SCHEMA::`, Table `TABLE::`, View `VIEW::`, MaterializedView `MVIEW::`, Column `COLUMN::`, Constraint `CONSTRAINT::`, Index `INDEX::`, Package `PACKAGE::`, Procedure `PROCEDURE::`, Function `FUNCTION::`, Trigger `TRIGGER::`, Sequence `SEQUENCE::`, Synonym `SYNONYM::`.

**Edge types:** Contains, PrimaryKeyOf, UniqueKeyOf, ForeignKeyTo, EnforcedBy, TriggerOn, SynonymFor, DocumentedBy, Calls, ReadsFrom, WritesTo, JoinsWith, ReferencesByCode, DependsOn, DerivedFrom, UsesSequence.

Labels must pass the same safety rules as `validate_node_labels` (`helpers.py` SAFE identifier pattern).

## Existing Analogs (reuse map)

| Need | Existing symbol | Reuse? | Caveat |
|------|-----------------|--------|--------|
| MCP tool registration | `@mcp.tool` in `graphiti_mcp_server.py` | Yes | Keep thin |
| Service + client hold | `GraphitiService` | Yes | Add catalog service sibling; inject same client |
| Config YAML + env | `config/schema.py` `GraphitiConfig` | Yes | Add `CatalogConfig` |
| Embedder wiring | `EmbedderFactory.create` | Yes | Required for searchable upserts |
| Neo4j real tx | `Neo4jDriver.transaction` | Yes | Catalog store must use this |
| Entity save Cypher shape | `get_entity_node_save_query` / `Neo4jEntityNodeOperations.save` | Partial | Pattern only; dedicated store for hash/updated_at/label control |
| Edge save Cypher shape | `get_entity_edge_save_query` | Partial | Same |
| Bulk tx pattern | `add_nodes_and_edges_bulk_tx` | Partial | Ordering wrong for catalog (embed inside); no UUIDv5 |
| Name/fact embeddings | `create_entity_node_embeddings`, `create_entity_edge_embeddings` | Yes | Call **before** catalog tx |
| Provenance read | `get_episode_entities` / `get_nodes_and_edges_by_episode` | Yes (interop) | Writes must populate MENTIONS + episodes list |
| Semantic ingest | `add_memory` + `QueueService` | **No** | Async + LLM |
| Direct fact write | `add_triplet` | **No** as implementation | Creates generic endpoints; non-deterministic resolve |
| Extraction entity types | `models/entity_types.py` ENTITY_TYPES | **No** for catalog allowlist | Different purpose |
| group_id isolation | everywhere | Yes | Tests only `oracle-catalog-tool-test` |
| Label validation | `validate_node_labels` | Yes | Call before any label interpolation |

## Dedicated Persistence Verdict

**Required: yes — Neo4j-specific `CatalogNeo4jStore`.**

Reasons (code evidence):
1. Atomic multi-entity/edge/provenance commit needs one `driver.transaction()` spanning custom statements; stock model `.save()` is single-object `execute_query`.
2. `SET n = $entity_data` full-replace semantics risk wiping or mis-ordering `created_at` / catalog audit fields unless carefully built maps are used under catalog control.
3. Endpoint enforcement (typed, existing-only) is not provided by `add_triplet` / bulk helpers.
4. `CatalogIngestBatch` is outside Graphiti's node model hierarchy.
5. Project decision: Neo4j first; no portability claim. Isolate store interface so a future backend could reimplement — do not pretend FalkorDB works in Phase 1/2.

## Phase 1 / Phase 2 Build Order

Dependency graph:

```
CatalogConfig + feature gate
    → strict Pydantic models (entities, edges, errors, limits)
        → catalog_identity (UUIDv5, SHA-256 canonicalize)
            → CatalogNeo4jStore entity MERGE/read
                → upsert_typed_entities
                → resolve_typed_entities
            → CatalogNeo4jStore edge MERGE/read (needs entity reads)
                → upsert_typed_edges
            → verify_catalog_batch (reads entities+edges [+ optional provenance later])
                ◆ PHASE 1 GATE (unit + Neo4j int + format + types + MCP list + regression)
            → provenance store (Episodic + MENTIONS)
                → upsert_provenance
            → CatalogIngestBatch status nodes
                → get_catalog_ingest_status
            → upsert_catalog_batch (composes all of the above)
                → docs + search interop checks
```

### Phase 1 (foundation — ship first)

1. **Config:** `CatalogConfig` — `enabled`, `uuid_namespace` (required UUID), limits (500 / 2000 / 5000 defaults), env `GRAPHITI_CATALOG_UUID_NAMESPACE`.
2. **Models:** allowlisted entity/edge request items; protected props; hash/prefix/size/confidence/finite-number validators; structured error codes.
3. **Identity helpers:** UUIDv5 + canonical SHA-256.
4. **Store (entities):** MERGE by uuid; set labels from allowlist; preserve `created_at`; set `updated_at`; store embeddings via `db.create.setNodeVectorProperty` pattern.
5. **Tool:** `upsert_typed_entities` (sync, embed-before-tx).
6. **Tool:** `resolve_typed_entities` (read-only detector).
7. **Store (edges):** MATCH typed endpoints; reject missing/generic; MERGE RELATES_TO.
8. **Tool:** `upsert_typed_edges`.
9. **Tool:** `verify_catalog_batch` (read-only; provenance section optional/no-op until Phase 2).
10. **MCP registration** + unit tests + Neo4j integration (`oracle-catalog-tool-test` only).
11. **Phase 1 report / gate** — blocks Phase 2.

### Phase 2 (provenance + orchestration — only after gate)

1. **Provenance store** using `Episodic` + `MENTIONS` (+ `entity_edges` / edge `episodes` lists as installed).
2. **Tool:** `upsert_provenance`.
3. **Status nodes:** `CatalogIngestBatch` + indexes.
4. **Tool:** `get_catalog_ingest_status`.
5. **Tool:** `upsert_catalog_batch` — full validation, same-request endpoint resolution, pre-tx embeddings, one domain tx, safe failed-status persistence, retry idempotency, `batch_conflict`.
6. Docs: purpose, config, namespace immutability, allowlists, idempotency, atomicity, limits, ACCEPT_TAB examples, semantic-vs-deterministic guidance.
7. Interop: `search_nodes`, `search_memory_facts`, safe `build_communities` on test group only.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Fixtures / canary (sample_catalog) | Single-request upserts; default limits fine |
| ~14k entities / 30k edges (target catalog) | Chunk by batch limits (500 / 2000); sequential batches per `group_id`; rely on UUIDv5 idempotency |
| Concurrent writers same group | Application-level batch_id conflict detection; avoid multi-writer without external lock |
| Multi-backend | Not in scope; keep `CatalogStore` protocol thin for later |

### Scaling Priorities

1. **First bottleneck:** embedding batch latency — batch `create_batch`, fail whole request without partial Neo4j writes.
2. **Second bottleneck:** large single transaction memory — enforce configured limits; never accept full 30k edges in one call.

## Anti-Patterns

### Anti-Pattern 1: Route catalog through `add_memory`

**What people do:** JSON episode + extraction for tables/columns.
**Why it's wrong:** Async queue, LLM nondeterminism, unwanted edges, non-stable UUIDs.
**Do this instead:** Deterministic tools only; leave `add_memory` for semantic memory.

### Anti-Pattern 2: Implement via `add_triplet`

**What people do:** Loop triplets for FK/PK.
**Why it's wrong:** Creates generic endpoints; may LLM-resolve edges; UUID not UUIDv5 catalog identity.
**Do this instead:** `upsert_typed_edges` with pre-existing typed endpoints.

### Anti-Pattern 3: Embed inside the write transaction

**What people do:** Open tx, call embedder, write.
**Why it's wrong:** Embed failures leave aborted/partial transactional state; slow locks.
**Do this instead:** Pattern 2 — embed fully, then tx.

### Anti-Pattern 4: Put status on `:Entity`

**What people do:** Store batch status as entity nodes.
**Why it's wrong:** Pollutes hybrid search and communities.
**Do this instead:** `:CatalogIngestBatch` without `Entity`.

### Anti-Pattern 5: Caller-supplied UUID as identity

**What people do:** Trust client uuid fields.
**Why it's wrong:** Breaks idempotency and namespace integrity.
**Do this instead:** Server UUIDv5 only; reject or ignore caller identity authority.

### Anti-Pattern 6: Interpolate client labels into Cypher

**What people do:** `f"MERGE (n:{user_label})"`.
**Why it's wrong:** Injection / schema drift.
**Do this instead:** Allowlist map → fixed label strings; values only as parameters.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Neo4j 5.26+ | `Neo4jDriver` via `GraphitiService.client.driver` | Real transactions; vector property API |
| Embedder provider | `EmbedderFactory` → `client.embedder` | Same config as semantic path; required for search parity |
| LLM providers | None for catalog tools | Feature must work even if LLM init failed |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| FastMCP tools ↔ CatalogService | async Python call | Sync from MCP client POV |
| CatalogService ↔ CatalogNeo4jStore | methods + tx | No Cypher outside store |
| CatalogService ↔ EmbedderClient | `create` / `create_batch` | Pre-tx only |
| CatalogService ↔ Graphiti facade | **avoid** write APIs | Read helpers OK if needed |
| Catalog tools ↔ QueueService | none | |
| Catalog entities ↔ search_nodes | shared Entity index | Must write compatible properties |
| CatalogIngestBatch ↔ search | none | Non-Entity label |

## Error Code Surface (architecture contract)

`validation_error`, `feature_disabled`, `invalid_uuid_namespace`, `batch_limit_exceeded`, `content_hash_mismatch`, `entity_type_conflict`, `graph_key_prefix_mismatch`, `deterministic_uuid_conflict`, `missing_endpoint`, `endpoint_type_mismatch`, `generic_endpoint_conflict`, `edge_identity_conflict`, `batch_conflict`, `provenance_target_missing`, `neo4j_transaction_failed`, `embedding_failed`, `internal_error`.

Return item-level structured errors where possible; never log full payloads/credentials.

## Test Architecture

| Layer | Location | Scope |
|-------|----------|-------|
| Unit models/identity | `mcp_server/tests/test_catalog_*.py` | No DB |
| Service ordering | mocked driver + embedder | Assert embed called before `transaction()` |
| Neo4j integration | `test_catalog_neo4j_int.py` | `group_id=oracle-catalog-tool-test` only |
| Regression | existing MCP tests | Unchanged tools still pass |
| Interop | search_nodes / search_memory_facts after upsert | Same test group |

Forbidden in tests: `clear_graph` on non-test groups; writes to `oracle-catalog-v2`; full catalog load.

## Sources

- `.planning/PROJECT.md` — requirements, allowlists, phase gate, identity rules
- `.planning/codebase/ARCHITECTURE.md` — system layers
- `.planning/codebase/STRUCTURE.md` — package layout
- `mcp_server/src/graphiti_mcp_server.py` — `GraphitiService`, tools, `add_memory` queue, `add_triplet`, `get_episode_entities`
- `mcp_server/src/services/factories.py` — Embedder/DB factories
- `mcp_server/src/services/queue_service.py` — semantic-only queue (bypass)
- `mcp_server/src/config/schema.py` — config extension point
- `graphiti_core/driver/neo4j_driver.py` — `transaction()`, indices bootstrap
- `graphiti_core/driver/query_executor.py` — `Transaction` ABC
- `graphiti_core/driver/neo4j/operations/entity_node_ops.py` — `save(..., tx=)`
- `graphiti_core/models/nodes/node_db_queries.py` — entity/episode MERGE templates
- `graphiti_core/models/edges/edge_db_queries.py` — RELATES_TO / MENTIONS templates
- `graphiti_core/nodes.py` / `edges.py` — `EntityNode`, `EpisodicNode`, `EntityEdge`, embedding helpers
- `graphiti_core/utils/bulk_utils.py` — bulk write/embed ordering analog
- `graphiti_core/graph_queries.py` — index/constraint baseline
- `graphiti_core/helpers.py` — `validate_node_labels`, `validate_group_id`
- `mcp_server/sample_catalog.json` — fixture shape for later canary (not full ingest)

---
*Architecture research for: Deterministic catalog-ingestion MCP tools*
*Researched: 2026-07-16*
*Confidence: HIGH (repo-sourced; Neo4j-first; dedicated store required)*
