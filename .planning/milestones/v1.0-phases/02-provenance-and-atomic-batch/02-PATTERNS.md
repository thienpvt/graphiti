# Phase 2: Provenance and Atomic Batch - Pattern Map

**Mapped:** 2026-07-17
**Files analyzed:** 16
**Analogs found:** 16 / 16

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp_server/src/models/catalog_provenance.py` | model | request-response | `mcp_server/src/models/catalog_entities.py` | exact |
| `mcp_server/src/models/catalog_batch.py` | model | request-response | `mcp_server/src/models/catalog_edges.py` + nested entity request | role-match |
| `mcp_server/src/models/catalog_common.py` | model/config | transform | same file (codes/limits) | exact |
| `mcp_server/src/models/catalog_responses.py` | model | request-response | same file (`CatalogWriteResponse`) | exact |
| `mcp_server/src/services/catalog_identity.py` | utility | transform | same file (`catalog_entity_uuid`) | exact |
| `mcp_server/src/services/catalog_store.py` | service/store | CRUD + file-I/O (Neo4j) | same file entity/edge MERGE + provenance presence | exact |
| `mcp_server/src/services/catalog_service.py` | service | request-response + batch | same file `upsert_typed_entities` / `_write_atomic` | exact |
| `mcp_server/src/graphiti_mcp_server.py` | route/controller | request-response | same file catalog `@mcp.tool()` block | exact |
| `mcp_server/tests/test_catalog_identity.py` | test | transform | same file | exact |
| `mcp_server/tests/test_catalog_models.py` | test | request-response | same file | exact |
| `mcp_server/tests/test_catalog_store_unit.py` | test | CRUD | same file Cypher builder asserts | exact |
| `mcp_server/tests/test_catalog_service.py` | test | request-response | same file AsyncMock orchestration + MCP registration tests | exact |
| `mcp_server/tests/test_catalog_neo4j_int.py` | test | CRUD/integration | same file `GROUP=oracle-catalog-tool-test` | exact |
| `mcp_server/README.md` | config/docs | — | existing catalog docs section if any; Phase 1 tool docs | partial |
| `.planning/phases/02-.../02-PHASE2-REPORT.md` | config/docs | — | Phase 1 verification report pattern | partial |
| Graphiti Episodic/MENTIONS/episodes (read-only schema contract) | model | — | `graphiti_core/nodes.py`, `edges.py`, `edge_db_queries.py` | exact (compat only) |

## Pattern Assignments

### `mcp_server/src/models/catalog_provenance.py` (model, request-response)

**Analog:** `mcp_server/src/models/catalog_entities.py`

**Imports / structure** (lines 1–24):
```python
from pydantic import BaseModel, Field, field_validator, model_validator
from models.catalog_common import (
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_*,
    MAX_*,
    SHA256_HEX_RE,
    validate_nested_json,
    PROTECTED_ENTITY_PROPERTIES,
)
```

**Item + request pattern** (lines 42–149):
- `CatalogEntityItem` + `UpsertTypedEntitiesRequest` with `group_id`, `batch_id`, collection, `dry_run`, `atomic`.
- Field validators: allowlist, SHA-256 hex, nested JSON, finite confidence, protected keys.
- Group id: ASCII alnum/dash/underscore via local `_validate_group_id`.

**Copy for provenance:**
- `CatalogSourceItem`: `source_key`, bounded metadata/attrs, optional `content_sha256`, exact `reference_time`.
- Entity/edge target refs reusing `entity_type`+`graph_key` / `edge_type`+`edge_key` allowlists.
- `UpsertProvenanceRequest`: `group_id`, `batch_id`, sources/links, `dry_run`, `atomic` (default true; atomic fail-closed).
- Reuse `CatalogErrorCode.provenance_target_missing` (already in common).

---

### `mcp_server/src/models/catalog_batch.py` (model, request-response)

**Analog:** `catalog_entities.UpsertTypedEntitiesRequest` + `catalog_edges.UpsertTypedEdgesRequest`

**Edge request shape** (`catalog_edges.py` 121–129):
```python
class UpsertTypedEdgesRequest(BaseModel):
    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    edges: list[CatalogEdgeItem] = Field(..., min_length=1, max_length=HARD_MAX_EDGES_PER_BATCH)
    dry_run: bool = False
    atomic: bool = True
    strict_endpoints: bool = True
```

**Copy for batch:**
- Nested: entities + edges + provenance collections under one request.
- `atomic: Literal[True]` or validator rejecting `atomic=false` → `validation_error`.
- Limits: config soft max + hard max from `catalog_common` (`DEFAULT_MAX_*`, `HARD_MAX_*` incl. provenance).
- Separate status request: `group_id` + `batch_id` only (get status).

---

### `mcp_server/src/models/catalog_common.py` (extend)

**Analog:** same file

**Already present — do not reinvent:**
- Limits: `DEFAULT_MAX_PROVENANCE_LINKS_PER_BATCH = 5000`, hard max 20000.
- Codes: `batch_conflict`, `provenance_target_missing`, `embedding_failed`, `neo4j_transaction_failed`.
- `validate_nested_json` for bounded metadata.

**Optional add:** batch status literal enum helper if not only on response models; keep codes stable.

---

### `mcp_server/src/models/catalog_responses.py` (extend)

**Analog:** same file lines 11–43, 98–111

```python
ItemStatus = Literal['created', 'updated', 'unchanged', 'rolled_back', 'error']

class CatalogWriteResponse(BaseModel):
    group_id: str
    batch_id: str
    dry_run: bool = False
    atomic: bool = True
    results: list[CatalogItemResult] = Field(default_factory=list)
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    rolled_back: int = 0
```

**Copy for Phase 2:**
- Provenance write response can reuse `CatalogWriteResponse` / `CatalogItemResult`.
- Batch response: counts for entities/edges/provenance + optional lifecycle field; status response: `status`, hashes, counts, bounded `error_summary`, timestamps — no full payload.
- Status enum values: `planned|validating|embedding|writing|committed|failed` (persist terminals only recommended).

---

### `mcp_server/src/services/catalog_identity.py` (utility, transform)

**Analog:** same file lines 17–48

```python
def catalog_entity_uuid(namespace: uuid.UUID, group_id: str, entity_type: str, graph_key: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|{entity_type}|{graph_key}'))

def catalog_edge_uuid(namespace: uuid.UUID, group_id: str, edge_type: str, edge_key: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|{edge_type}|{edge_key}'))

def canonical_sha256(payload: dict[str, Any]) -> str:
    _reject_non_finite(payload)
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()
```

**Add (mirror signature style; no caller UUID authority):**
```python
def catalog_source_uuid(namespace: uuid.UUID, group_id: str, source_key: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|Source|{source_key}'))

def catalog_batch_uuid(namespace: uuid.UUID, group_id: str, batch_id: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|Batch|{batch_id}'))

def catalog_mentions_uuid(
    namespace: uuid.UUID, group_id: str, source_uuid: str, entity_uuid: str
) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|Mentions|{source_uuid}|{entity_uuid}'))
```

Pure module: no Neo4j/embedder/LLM imports.

---

### `mcp_server/src/services/catalog_store.py` (store, CRUD)

**Analog:** same class `CatalogNeo4jStore`

#### Preserve-on-update MERGE (entities) — lines 245–320
```cypher
MERGE (n:Entity {uuid: $uuid, group_id: $group_id})
ON CREATE SET n:TypeLabel, ... identity ..., n._catalog_create_token = $create_token
WITH n, created, same, CASE WHEN created THEN 'created' WHEN same THEN 'unchanged' ELSE 'updated' END AS status
FOREACH (_ IN CASE WHEN status = 'updated' THEN [1] ELSE [] END | SET ...)
REMOVE n._catalog_create_token
```
**Apply to:** `Episodic` sources and `CatalogIngestBatch` (no `Entity` label on either).

#### Edge upsert + episodes wipe hazard — lines 894–1039
- `build_edge_upsert_cypher` SETs `e.episodes = $episodes` on create **and** update.
- `prepare_edge_params` hardcodes `'episodes': []`.
- **Phase 2 rule:** after provenance attaches episodes, never pass bare `[]` on content update; use append-only Cypher or precomputed final list. Prefer write edges then append provenance inside same tx.

#### Provenance presence (entity-only today) — lines 753–776
```cypher
UNWIND $target_uuids AS target_uuid
OPTIONAL MATCH (ep:Episodic)-[:MENTIONS]->(n {uuid: target_uuid})
WHERE ep.group_id = $group_id AND n.group_id = $group_id
RETURN target_uuid AS uuid, mention_count > 0 AS has_provenance
```
**Extend for edges:** `MATCH ()-[e:RELATES_TO {uuid, group_id}]->() WHERE size(coalesce(e.episodes,[])) > 0` (or membership).

#### Endpoint resolve (MATCH only) — lines 853–892
`resolve_endpoint_typed(..., expected_uuid=...)` — never CREATE. Batch unions same-request map **before** this.

#### Stock Graphiti anti-pattern (do not copy for writes)
`get_episode_node_save_query` Neo4j branch: `SET n = {uuid, name, ...}` wipes node (`node_db_queries.py` 61–65).

#### Stock MENTIONS shape (compat reference, prefer catalog preserve-on-create)
`EPISODIC_EDGE_SAVE` (`edge_db_queries.py` 19–27):
```cypher
MATCH (episode:Episodic {uuid: $episode_uuid})
MATCH (node:Entity {uuid: $entity_uuid})
MERGE (episode)-[e:MENTIONS {uuid: $uuid}]->(node)
SET e.group_id = $group_id, e.created_at = $created_at
```
**Catalog variant:** add `group_id` on MATCH for both ends; ON CREATE SET only; deterministic mentions uuid.

#### New store primitives to add (mirror existing method style)
- `build_source_episode_upsert_cypher` / `upsert_source_episode`
- `build_mentions_merge_cypher` / `upsert_mentions_link`
- `build_append_edge_episode_cypher` (APOC-free list concat + dedup)
- `build_batch_status_upsert_cypher` / `get_batch_status` — label **only** `CatalogIngestBatch`
- Extend identity constraints if needed for Episodic/status composite `(uuid, group_id)` — same ensure pattern as entity/relates_to (lines 83–166)

---

### `mcp_server/src/services/catalog_service.py` (service, orchestration)

**Analog:** `upsert_typed_entities` (249–508) + `_write_atomic` (510+)

**Order contract (copy):**
1. gate (feature/namespace/backend/limits)
2. identity + `canonical_sha256` + coalesce / divergent conflict
3. pre-read existing + conflict classification
4. atomic fail-closed before embed if errors
5. embed only non-unchanged (**provenance sources skip embed**)
6. dry_run: no schema, no tx, no status
7. ensure schema
8. `async with client.driver.transaction() as tx:` write all + recheck races
9. log counts/batch_id only

**Atomic write skeleton** (542–551):
```python
async with client.driver.transaction() as tx:
    for prep in to_write:
        inv_err = await self._recheck_entity_in_tx(tx, prep, request)
        if inv_err is not None:
            raise self._EntityInvariantRace(inv_err)
        row = await self._store.upsert_entity_item(tx, entity_type=..., params=...)
```

**Atomic fail response** (918–961): triggers `error`, siblings `rolled_back` + `batch_conflict`.

**New methods (same class, reuse helpers):**
- `upsert_provenance` — target preflight → source hash → MENTIONS/episodes; no `add_episode`/queue/LLM
- `get_catalog_ingest_status` — read by batch uuid + group_id
- `upsert_catalog_batch` — nested validate → coalesce → endpoint **union** (request map + store resolve) → all conflicts → embed all entities/edges → one domain tx (entities, edges, provenance, status=`committed`) → on domain exception: rollback auto, then best-effort **second** tx status=`failed` with bounded summary; embedding failure: **no** status write

**Prepared dataclasses:** extend `_PreparedEntity` / `_PreparedEdge` or add `_PreparedSource` / `_PreparedBatch`.

**Transaction semantics** (`neo4j_driver.py` 152–161):
```python
async with self.client.session(...) as session:
    tx = await session.begin_transaction()
    try:
        yield _Neo4jTransaction(tx)
        await tx.commit()
    except BaseException:
        await tx.rollback()
        raise
```

---

### Graphiti installed-schema contract (read-only)

**EpisodicNode** (`nodes.py` 318–328): `source: EpisodeType`, `source_description`, `content`, `valid_at`, `entity_edges`.
**EpisodeType** (`nodes.py` 74–77): prefer `json` for catalog structured metadata.
**EntityEdge.episodes** (`edges.py` ~267): `list[str]` of episode UUIDs.
**Never call** `EpisodicNode.save` / `add_episode` / queue from catalog path.

---

### `mcp_server/src/graphiti_mcp_server.py` (MCP tools)

**Analog:** lines 1235–1341

```python
@mcp.tool()
async def upsert_typed_entities(request: UpsertTypedEntitiesRequest) -> CatalogWriteResponse | ErrorResponse:
    global graphiti_service, catalog_service
    if graphiti_service is None:
        return ErrorResponse(error='Graphiti service not initialized')
    if catalog_service is None:
        catalog_service = CatalogService(catalog_config=graphiti_service.config.catalog_upsert)
    try:
        client = await graphiti_service.get_client()
        return await catalog_service.upsert_typed_entities(client=client, request=request)
    except Exception as e:
        logger.error('upsert_typed_entities failed batch_id=%s count=%s reason=%s', ..., type(e).__name__)
        return ErrorResponse(error='catalog upsert_typed_entities failed')
```

**Add three tools identically:** `upsert_provenance`, `get_catalog_ingest_status`, `upsert_catalog_batch`.
Log batch_id/counts/type name only — never payloads.
Init path already constructs `catalog_service` (~1485).

---

### Tests

| File | Analog pattern |
|------|----------------|
| `test_catalog_identity.py` | FIXED_NS + GROUP; assert uuid5 formula; no caller uuid params |
| `test_catalog_models.py` | Pydantic ValidationError for allowlist/limits/hash/NaN |
| `test_catalog_store_unit.py` | Cypher string contains fixed labels; no client label interpolation; status cypher must not contain `:Entity` |
| `test_catalog_service.py` | AsyncMock store/embedder; assert call_order embed before transaction; MCP `hasattr(server, tool)` registration (e.g. lines 567–570) |
| `test_catalog_neo4j_int.py` | `GROUP = 'oracle-catalog-tool-test'` only; teardown; canary/live group unchanged; no LLM/queue |

**MCP registration:** extend service tests (no separate `test_catalog_mcp_registration.py` yet) or add thin file asserting 7 catalog tools.

## Shared Patterns

### Identity authority
**Source:** `catalog_identity.py`
**Apply to:** entities, edges, sources, batches, MENTIONS links — server UUIDv5 only.

### Validation / allowlists
**Source:** `catalog_common.py` + entity/edge models
**Apply to:** all new models; fixed labels `Episodic`, `MENTIONS`, `RELATES_TO`, `CatalogIngestBatch` only.

### Embed before transaction
**Source:** `CatalogService.upsert_typed_entities` steps 3–6
**Apply to:** batch entity/edge writes; skip for pure provenance/status.

### Atomic fail-closed
**Source:** early_errors + `_atomic_fail_response`
**Apply to:** provenance (atomic) and batch (always atomic).

### Parameterized Cypher + composite MERGE key
**Source:** `build_entity_upsert_cypher` / `build_edge_upsert_cypher`
**Apply to:** all new writes; `(uuid, group_id)` MERGE.

### Logging safety
**Source:** catalog service `logger.info/error` with batch_id + counts + `type(exc).__name__`
**Apply to:** all new tools/service methods.

### Isolation
**Source:** int tests `GROUP = 'oracle-catalog-tool-test'`
**Apply to:** all live tests; never `oracle-catalog-v2`.

### Communities / LLM
**Source:** Phase 1 gate tests (no queue/embed misuse)
**Apply to:** upsert paths never call `build_communities`, `add_episode`, queue, or LLM.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| _(none blocking)_ | | | Phase 1 stack covers all roles; Episodic/status are store extensions not greenfield |
| Durable intermediate batch status crash recovery | store | event-driven | Product choice: prefer terminal-only persistence; intermediate statuses response/log only unless gated otherwise |

## Anti-Patterns Checklist (planner must encode)

1. No `SET n = $map` episode save.
2. No edge update wiping `episodes` with `[]` after provenance.
3. No `:Entity` on `CatalogIngestBatch`.
4. No routing batch through public tool functions (separate txs).
5. No `atomic=false` on batch.
6. No status write on dry-run or embedding failure.
7. No full source text / credentials in Episodic.content or status props.
8. No `build_communities` inside upsert.

## Metadata

**Analog search scope:** `mcp_server/src/models/catalog_*`, `mcp_server/src/services/catalog_*`, `mcp_server/src/graphiti_mcp_server.py`, `mcp_server/tests/test_catalog_*`, `graphiti_core/{nodes,edges,models,driver/neo4j_driver}.py`
**Files scanned:** ~20 primary
**Pattern extraction date:** 2026-07-17
