# Phase 1: Typed Catalog Primitives - Pattern Map

**Mapped:** 2026-07-16
**Files analyzed:** 16
**Analogs found:** 14 / 16

## File Classification

| New/Modified File | Role | Closest Analog | Match |
|---|---|---|---|
| `mcp_server/src/config/schema.py` | config | nested `GraphitiConfig` models | exact |
| `mcp_server/src/models/catalog_common.py` | model | `models/response_types.py` | role |
| `mcp_server/src/models/catalog_entities.py` | request model | `models/entity_types.py` | role |
| `mcp_server/src/models/catalog_edges.py` | request model | `models/edge_types.py` | role |
| `mcp_server/src/models/catalog_responses.py` | response model | `models/response_types.py` | exact |
| `mcp_server/src/services/catalog_identity.py` | pure utility | stdlib `uuid`/`hashlib`/`json` | new |
| `mcp_server/src/services/catalog_service.py` | orchestration | current MCP tool service guards | role |
| `mcp_server/src/services/catalog_store.py` | Neo4j CRUD | Neo4j operations + `transaction()` | role |
| `mcp_server/src/graphiti_mcp_server.py` | tool route | current `@mcp.tool()` handlers | exact |
| `mcp_server/tests/test_catalog_models.py` | unit test | `test_configuration.py` | role |
| `mcp_server/tests/test_catalog_identity.py` | pure unit test | pytest conventions | new |
| `mcp_server/tests/test_catalog_service.py` | service unit test | `test_update_entity.py` | exact |
| `mcp_server/tests/test_catalog_store_unit.py` | query safety test | core Cypher security tests | role |
| `mcp_server/tests/test_catalog_neo4j_int.py` | integration | MCP integration tests | role |

## Core Pattern

```text
FastMCP tool -> CatalogService -> CatalogNeo4jStore -> Neo4jDriver.transaction()
                         |-> configured EmbedderClient before transaction
```

- Tool adapters stay thin. No queue, LLM, `add_memory`, `add_triplet`, or `excluded_entity_types`.
- Tool schemas remain registered while disabled; service returns `feature_disabled`.
- `CatalogService` owns config/backend gates, identity, hashes, coalescing, embedding order, result order, logging.
- `CatalogNeo4jStore` owns fixed allowlisted Cypher, exact typed reads, commit/rollback.

## Configuration Pattern

Extend `mcp_server/src/config/schema.py` with `CatalogConfig`:

- `enabled: bool = False`
- `uuid_namespace: str | None = None`; never generate a default
- `max_entities_per_batch: int = 500`
- `max_edges_per_batch: int = 2000`
- `max_provenance_links_per_batch: int = 5000`
- `GraphitiConfig.catalog_upsert = Field(default_factory=CatalogConfig)`
- Explicitly map `GRAPHITI_CATALOG_UUID_NAMESPACE` if nested settings do not naturally consume it.
- Missing/invalid namespace allowed only while disabled; enabling requires valid UUID.

## Request and Response Models

Use Pydantic `BaseModel` requests/responses. Enforce:

- Fixed 15 entity types and prefixes; fixed 16 edge types.
- Required non-empty validated `group_id`.
- Collection/string/raw-text limits, finite numbers, confidence `[0,1]`, hashes.
- Protected entity fields: `uuid`, `group_id`, `labels`, `graph_key`, `name_embedding`, `created_at`, `updated_at`, `content_sha256`.
- Structured item errors. Success states: `created`, `updated`, `unchanged`; atomic sibling state: `rolled_back`.
- Input order preserved; deterministic UUID and canonical hash returned.

## Identity Pattern

`catalog_identity.py` uses stdlib only:

- Entity UUID: `uuid.uuid5(namespace, f'{group_id}|{entity_type}|{graph_key}')`.
- Edge UUID: `uuid.uuid5(namespace, f'{group_id}|{edge_type}|{edge_key}')`.
- Canonical SHA-256: reject non-finite values; JSON `sort_keys=True`, compact separators, UTF-8; `hexdigest()`.
- Caller UUID never used as MERGE authority.
- Identical canonical hash returns `unchanged`; no property or timestamp mutation.

## Service Ordering

Hard write order:

1. Feature, namespace, backend gates.
2. Complete request validation and limits.
3. UUIDv5 and canonical SHA-256.
4. Same-request coalescing/conflict detection.
5. Edge endpoint read by exact `group_id + graph_key + entity_type`.
6. Generate all `name_embedding` or `fact_embedding` values.
7. For non-dry-run only, open Neo4j transaction.
8. Commit or rollback before returning.

`atomic=true`: one request transaction. `atomic=false`: one transaction per item. Dry-run still embeds but never writes.

## Neo4j Store Pattern

Avoid stock `SET n = $entity_data` / `SET e = $edge_data`; those replace complete maps.

Entities:

- MERGE deterministic UUID.
- Fixed query per allowlisted label or server-owned label mapping; validate again at query boundary.
- Exactly labels `Entity` + expected custom type; `labels` property matches.
- `name = graph_key`; preserve exact `name_raw`, `name_canonical`; store `database_qualified_name`, summary, batch, hash.
- `ON CREATE` sets `created_at`; changed `ON MATCH` sets mutable fields and `updated_at`; identical hash does nothing.
- Use Neo4j vector property procedure for `name_embedding`.

Edges:

- Resolve both endpoints without CREATE. Missing returns `missing_endpoint`; wrong custom label returns `endpoint_type_mismatch`; generic-only endpoint returns `generic_endpoint_conflict`.
- MERGE `(source)-[e:RELATES_TO {uuid: deterministic_uuid}]->(target)`.
- `e.name = allowlisted edge type`; `e.fact` is searchable; use vector procedure for `fact_embedding`.
- Preserve source/target identity and `created_at`; changed payload advances `updated_at`; identical payload does nothing.

## Search Compatibility

- Node search filters custom Neo4j labels; entity custom label must exist.
- Edge search filter uses `e.name in $edge_types`; catalog relationship `name` must equal edge type.
- Hybrid fact search uses `fact` + `fact_embedding`.

## Test Pattern

- Unit tests use pytest, real Pydantic models, `AsyncMock`, deterministic fake embeddings.
- Assert embedder runs before transaction context entry.
- Assert no queue/LLM calls, dry-run has no transaction, atomic failures mark rollback, safe logs contain IDs/counts only.
- Query-boundary tests bypass Pydantic where useful and verify no client identifiers enter Cypher.
- Integration test group exactly `oracle-catalog-tool-test`; teardown deletes only that group. Never `clear_graph`.
- Cover six typed entities, structural edges, two distinct foreign keys, retry unchanged, conflicts, concurrency, rollback, `search_nodes`, `search_memory_facts`.

## Explicit Non-Copies

| Existing path | Reason |
|---|---|
| `EntityNode.save` / `EntityEdge.save` | complete property-map replacement breaks preservation |
| `add_triplet` | can create generic UUIDv4 endpoints |
| `add_memory` / `QueueService` | asynchronous queue and LLM extraction |
| Node/Edge UUID defaults | UUIDv4, not retry-stable |
| Client-provided Cypher labels/properties | injection and schema drift |

## Dirty Worktree Rule

Never stage or modify unrelated `mcp_server/k8s/graphiti-neo4j.yaml`, `.codegraph/`, or `mcp_server/sample_catalog.json` unless separately approved.
