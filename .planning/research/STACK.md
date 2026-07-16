# Stack Research

**Domain:** Deterministic catalog-ingestion tools on existing Graphiti MCP + Neo4j
**Researched:** 2026-07-16
**Confidence:** HIGH

## Recommended Stack

Use the **already-installed** MCP server stack. Add no runtime packages for Phase 1–2 catalog upserts. Prefer stdlib + installed Graphiti/Neo4j primitives. Milestone is Neo4j-only for write path; do not claim multi-backend support.

### Core Technologies

| Technology | Version (locked / required) | Purpose | Why Recommended |
|------------|----------------------------|---------|-----------------|
| Python | `>=3.10,<4` (images 3.11/3.12) | Runtime | Entire monorepo is async Python; MCP + Graphiti APIs are `async` |
| `uv` | `0.8.15` in standalone Docker; lockfile-driven | Install / lock | Existing package manager; `mcp_server/uv.lock` is source of truth |
| `mcp` (FastMCP) | **1.27.2** (`>=1.27.2,<2`) | MCP tool surface | Existing server uses `from mcp.server.fastmcp import FastMCP`; register new tools with `@mcp.tool()` only |
| `graphiti-core` | **0.29.2** (`>=0.29.2`, PyPI wheel in lock) | Graph models, embedder, search recipes | Same version as root library; models `EntityNode`/`EntityEdge`/`EpisodicNode`, hybrid search, Neo4j driver |
| `neo4j` (Python driver) | **5.28.1** (req `>=5.26.0`) | Async Bolt driver | Official driver; `Neo4jDriver` wraps `AsyncGraphDatabase`; real `transaction()` |
| Neo4j server | **5.26.0** image (`neo4j:5.26.0` compose); **5.26+** required | Graph DB | Project constraint; vector property procs + MERGE upserts used by Graphiti |
| Pydantic | **2.11.7** (req `>=2.11.5`) | Request/response models | Validation, allowlists, protected fields; matches Graphiti node/edge models |
| `pydantic-settings` | **2.10.1** | Config | Existing `GraphitiConfig` YAML + env merge; extend for catalog UUID namespace |
| `openai` | **2.43.0** (MCP req `>=2.41.0`) | Default embedder transport | Embeddings only for catalog tools — **no LLM calls** |
| `pyyaml` | **6.0.3** | Config load | Existing YAML configs under `mcp_server/config/` |

### Supporting Libraries (already present — reuse)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | (via graphiti-core) | `.env` load | Server boot only; catalog tools read config via `GraphitiConfig` |
| `tenacity` | (via graphiti-core) | Retries in LLM clients | **Do not use** for catalog writes; fail and return structured error |
| `httpx` | **0.28.1** | HTTP in MCP/tests | Integration tests against MCP HTTP transport |
| `typing-extensions` | **4.14.0** | `TypedDict` on <3.12 | Response types (`models/response_types.py` pattern) |
| `starlette` / `uvicorn` | **1.3.1** / **0.34.3** (MCP transitive) | HTTP transport | Existing MCP HTTP path; no FastAPI addition in MCP package |
| `falkordb` | **1.2.0** (optional extra) | Alternate backend | **Out of milestone write path**; leave factory branches untouched |

### Development Tools

| Tool | Locked version | Purpose | Notes |
|------|----------------|---------|-------|
| pytest | **9.0.3** | Unit + Neo4j integration | Markers: `unit`, `integration`, `requires_neo4j`; follow `mcp_server/tests/` |
| pytest-asyncio | **1.4.0** | Async tests | Use existing async fixtures pattern |
| pytest-timeout | **2.4.0** | Hang protection | Integration tests against Neo4j |
| pytest-xdist | (dev group `>=3.8.0`) | Parallel unit only | Avoid parallel Neo4j write tests on shared group |
| ruff | **0.15.18** | Format + lint | line-length 100, single quotes; `make format` / `ruff` |
| pyright | **1.1.408** | Typecheck | `typeCheckingMode = "basic"` for mcp_server |
| faker | **40.23.0** | Synthetic data | Optional; prefer fixed catalog fixtures for determinism |
| psutil | (dev) | Stress tests | Not required for catalog tools |

## Exact APIs to Use (prescriptive)

### MCP registration

- Server: `mcp = FastMCP('Graphiti Agent Memory', instructions=...)` in `mcp_server/src/graphiti_mcp_server.py`
- New tools: same `@mcp.tool()` async functions; return Pydantic/`TypedDict` responses + `ErrorResponse`
- Do **not** introduce a second MCP app or FastAPI router in the MCP package
- Keep tools **synchronous from caller POV**: `await` Neo4j commit before return (unlike `add_memory` → `QueueService`)

### Graphiti client construction (reuse existing)

```python
# Existing path — GraphitiService.initialize()
Graphiti(
    uri=db_config['uri'],
    user=db_config['user'],
    password=db_config['password'],
    llm_client=llm_client,      # may be None; catalog writes must not call it
    embedder=embedder_client,   # required for name/fact embeddings
    max_coroutines=semaphore_limit,
)
await client.build_indices_and_constraints()
```

- Neo4j path uses URI ctor (not `graph_driver=`). Falkor path remains for other deployments; **catalog write code must gate on Neo4j** and return `feature_disabled` / clear error if not Neo4j.
- Factory: `DatabaseDriverFactory.create_config`, `EmbedderFactory.create` — already in `services/factories.py`.

### Models for domain objects

| Model | Module | Key fields for catalog |
|-------|--------|------------------------|
| `EntityNode` | `graphiti_core.nodes` | `uuid`, `name`, `group_id`, `labels`, `created_at`, `name_embedding`, `summary`, `attributes` |
| `EntityEdge` | `graphiti_core.edges` | `uuid`, `name` (edge type), `fact`, `group_id`, `source_node_uuid`, `target_node_uuid`, `fact_embedding`, `episodes`, `valid_at`/`invalid_at`/`expired_at`, `reference_time`, `attributes`, `created_at` |
| `EpisodicNode` | `graphiti_core.nodes` | Provenance (Phase 2): `source=EpisodeType`, `content`, `valid_at`, `entity_edges`, `source_description` |
| `EpisodicEdge` | `graphiti_core.edges` | `MENTIONS` episode→entity; save via installed query |
| `SearchFilters` | `graphiti_core.search.search_filters` | `node_labels`, `edge_types`, date filters, `edge_uuids` |
| `EpisodeType` | `graphiti_core.nodes` | `text` / `json` / `message` / `fact_triple` |

**Identity rule (project):** server UUIDv5 only — never treat caller UUID as authority. Store `graph_key`, `entity_type`/`edge_type`, content hash in **attributes** (or dedicated properties via custom Cypher), not by inventing free-form labels.

**Labels:** always include Graphiti base `Entity` plus allowlisted type label (e.g. `Table`). Never interpolate client-supplied label strings into Cypher; map from fixed allowlist to Cypher fragments.

### Persist / upsert methods

| Method | Behavior | Use for catalog? |
|--------|----------|------------------|
| `EntityNode.save(driver)` / `EntityEdge.save(driver)` | `MERGE` on `uuid`, `SET` properties + labels/embeddings | Prefer for single-object paths **if** attributes/labels/embeddings are complete |
| `add_nodes_and_edges_bulk(driver, [], [], nodes, edges, embedder)` | Session `execute_write` bulk MERGE | OK if you accept Graphiti bulk shape; still runs embedder if embeddings missing |
| `Neo4jDriver.transaction()` → `tx.run(cypher, **params)` | Real commit/rollback (`begin_transaction` / commit / rollback) | **Preferred for atomic batch** and property-preserving upserts |
| `driver.execute_query(cypher, **kwargs)` | Auto-commit query via driver | Reads and non-atomic single ops |
| `client.driver.session()` | Native Neo4j async session | Status checks (`get_status` pattern); bulk write helper uses `session.execute_write` |
| `Graphiti.add_triplet(...)` | Embeddings + **LLM** `resolve_extracted_nodes` / `resolve_extracted_edge` + bulk save | **Forbidden** for catalog — non-deterministic, can create generic endpoints |
| `Graphiti.add_episode(...)` | Full extraction pipeline | **Forbidden** for catalog domain writes |
| `QueueService.add_episode` / `add_memory` | Async queue | **Forbidden** for catalog tools |

Installed Neo4j entity save shape (Graphiti):

```cypher
MERGE (n:Entity {uuid: $entity_data.uuid})
SET n:<AllowlistedLabels>
SET n = $entity_data
WITH n CALL db.create.setNodeVectorProperty(n, "name_embedding", $entity_data.name_embedding)
RETURN n.uuid AS uuid
```

Installed Neo4j edge save shape:

```cypher
MATCH (source:Entity {uuid: $edge_data.source_uuid})
MATCH (target:Entity {uuid: $edge_data.target_uuid})
MERGE (source)-[e:RELATES_TO {uuid: $edge_data.uuid}]->(target)
SET e = $edge_data
WITH e CALL db.create.setRelationshipVectorProperty(e, "fact_embedding", $edge_data.fact_embedding)
RETURN e.uuid AS uuid
```

**Caveat (why custom Cypher may be required):** `EntityNode.save` / bulk flatten `attributes` onto node properties and set labels via string join. For catalog, you must:

1. Preserve `created_at` on update; set `updated_at` (not in base model — store as property/attribute deliberately).
2. Keep exact `name_raw` / `name_canonical` / `graph_key` / `content_sha256` without protected-key collisions (`uuid`, `name`, `group_id`, `name_embedding`, `summary`, `created_at`, `labels` are reserved).
3. Ensure type labels survive `SET n = $entity_data` (labels set separately; do not put free-form labels in client input).
4. Edge type lives in `EntityEdge.name` (string), relationship type remains `RELATES_TO` — matches Graphiti search (`e.name in $edge_types`).

**Transaction API to use for Phase 1–2 writes:**

```python
async with client.driver.transaction() as tx:  # Neo4jDriver.transaction
    await tx.run(FIXED_CYPHER, **params)
# commit on clean exit; rollback on exception
```

Do not open the write transaction until embeddings succeed.

### Embeddings

| API | Usage |
|-----|--------|
| `EmbedderClient.create(input_data=...)` | Single string → `list[float]` |
| `EmbedderClient.create_batch(...)` | Optional batch; default abstract raises — OpenAI embedder may implement; fall back to sequential `create` |
| `EntityNode.generate_name_embedding(embedder)` | Embeds `name` |
| `EntityEdge.generate_embedding(embedder)` | Embeds `fact` |

Config defaults (`schema.py` / Neo4j docker YAML):

- Embedder provider: `openai`
- Model: `text-embedding-3-small`
- Dimensions: `1536` (MCP config); core default `EMBEDDING_DIM` env defaults to `1024` — **use MCP `EmbedderConfig.dimensions` / configured client**, not the bare env default
- Pre-compute embeddings **before** Neo4j write TX; on failure return `embedding_failed` with no partial graph write

Catalog tools must not call `LLMClient` / factories for LLM.

### Search / verify (read path)

| API | Recipe | Use |
|-----|--------|-----|
| `client.search_(query, config=..., group_ids=..., search_filter=..., center_node_uuid=...)` | `NODE_HYBRID_SEARCH_RRF` or `NODE_HYBRID_SEARCH_NODE_DISTANCE` | Interop tests for typed entities via `search_nodes` behavior |
| `client.search(query, group_ids=..., num_results=..., search_filter=..., center_node_uuid=...)` | `EDGE_HYBRID_SEARCH_RRF` / node-distance | Interop for facts; filters on `edge_types` = `EntityEdge.name` |
| `EntityNode.get_by_uuid` / `get_by_uuids` / `get_by_group_ids` | Direct reads | `resolve_typed_entities`, verify |
| `EntityEdge.get_by_uuid` / `get_between_nodes` | Direct reads | Edge conflict / endpoint checks |
| Cypher via `execute_query` with `group_id` predicate | Exact key/uuid lookup | Deterministic verify (preferred over hybrid search for identity checks) |

Hybrid search is for **compatibility**, not identity authority. Verification must use exact UUID / `graph_key` + `group_id` queries.

### Configuration pattern

Extend existing stack — do not invent a second settings system:

| Mechanism | Detail |
|-----------|--------|
| `GraphitiConfig` (`pydantic-settings`) | Priority: CLI init > env > YAML (`CONFIG_PATH`) > defaults |
| YAML | `mcp_server/config/config-docker-neo4j.yaml` pattern; `${VAR}` / `${VAR:default}` |
| Env for Neo4j | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (factory also overrides from env) |
| Required new config | `GRAPHITI_CATALOG_UUID_NAMESPACE` — fixed UUID string, immutable for deployment |
| Recommended new config | Catalog batch limits (defaults: 500 entities, 2000 edges, 5000 provenance), enable flag |
| `group_id` | Existing `graphiti.group_id` / per-call override; tests **only** `oracle-catalog-tool-test` |
| `SEMAPHORE_LIMIT` | Existing concurrency for LLM episodes; catalog tools should not share LLM pressure but may still respect process limits |

Database default in schema is `falkordb`; Neo4j docker config sets `database.provider: neo4j`. Milestone assumes Neo4j runtime.

### Identity / hashing (stdlib only)

| Primitive | Module | Role |
|-----------|--------|------|
| UUIDv5 | `uuid.uuid5(namespace, name)` | Entity: `group_id\|entity_type\|graph_key`; Edge: `group_id\|edge_type\|edge_key`; Source/Batch similar |
| Namespace | `uuid.UUID(GRAPHITI_CATALOG_UUID_NAMESPACE)` | Reject invalid → `invalid_uuid_namespace` |
| SHA-256 | `hashlib.sha256` | Canonical payload audit; exactly 64 lowercase hex; **no MD5** |
| JSON canonicalization | stdlib `json` with sorted keys / project-defined canonical form | Stable hash input |

### Provenance (Phase 2 only — installed schema)

- Prefer `EpisodicNode` + `MENTIONS` (`EpisodicEdge`) + `entity_edges` UUID list on episode — installed Graphiti representation.
- Do **not** call `add_episode` / extraction.
- Status nodes: non-`Entity` label e.g. `CatalogIngestBatch` so hybrid entity search does not pick them up.
- If direct episode→entity-edge link is incomplete in schema, document closest compatible form; do not invent new edge types outside Graphiti’s `MENTIONS` / `RELATES_TO` / saga edges without research flag.

## Installation

No new packages for the feature itself. Work from `mcp_server/`:

```bash
cd mcp_server
uv sync --group dev

# Neo4j for integration (existing compose)
docker compose -f docker/docker-compose-neo4j.yml up -d neo4j

# Unit (no DB)
uv run pytest tests/ -k "not _int and not integration" -q

# Catalog-focused Neo4j tests (to be added); isolate group_id
# uv run pytest tests/test_catalog_*.py -m "requires_neo4j"
```

Root library (if editing shared core — prefer **not** to for this milestone):

```bash
uv sync --extra dev
make format && make lint && make test
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Neo4j 5.26+ + `neo4j` 5.28.1 driver | FalkorDB 1.2.0 | Other deployments only; **not** this milestone’s write path |
| Custom `transaction()` Cypher upserts | `add_triplet` | Never for catalog — LLM + generic endpoints |
| Custom deterministic tools | `add_memory` / queue | Never — async + extraction |
| `EntityNode`/`EntityEdge` + Graphiti labels | Arbitrary Cypher labels/properties from client | Never — injection + search pollution |
| OpenAI embedder (configured) | Voyage / Gemini / Azure embedders | Only if deployment already configures them via `EmbedderFactory`; same `EmbedderClient` interface |
| UUIDv5 + SHA-256 | Caller UUIDs / MD5 | Never — project forbids |
| pytest + Neo4j integration | Live MCP against `oracle-catalog-v2` | Never during implementation |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `Graphiti.add_episode` / `add_memory` / `QueueService` | Async, LLM extraction, non-idempotent for catalogs | Sync catalog upsert tools |
| `Graphiti.add_triplet` | LLM resolve; can create generic `Entity` endpoints | Typed endpoint enforcement + deterministic edge upsert |
| FalkorDB / Kuzu / Neptune write paths | Milestone is Neo4j-only; no portability claim | `Neo4jDriver.transaction` / Neo4j Cypher |
| New ORM / OGM (neomodel, etc.) | Extra dependency; fights Graphiti schema | Installed driver + fixed Cypher |
| New web framework in MCP | Duplicates FastMCP | `@mcp.tool()` only |
| `clear_graph` / bulk delete in tests against shared groups | Data loss risk | Isolated `oracle-catalog-tool-test` only; no live-group mutation |
| Client-supplied DB UUIDs as identity | Breaks idempotency | Server UUIDv5 from namespace + keys |
| MD5 / non-canonical hashing | Audit mismatch | SHA-256 hex64 |
| Interpolating labels/property names from requests into Cypher | Injection / schema drift | Allowlist → fixed query fragments |
| Calling LLM client in catalog tools | Non-determinism, cost, latency | Embedder only |
| Automatic community build on upsert | Side-effecting maintenance | Optional separate `build_communities` interop test only |
| Editing `mcp_server/k8s/graphiti-neo4j.yaml` / unrelated dirty files | Out of scope / preserve worktree | Leave untouched unless approved |

## Stack Patterns by Variant

**If deployment is Neo4j (this milestone):**

- Gate catalog writes: `config.database.provider == 'neo4j'` (case-insensitive).
- Use `client.driver` as `Neo4jDriver` (has `.transaction()` with real commit/rollback).
- Compose image `neo4j:5.26.0`; driver package 5.28.1 against server 5.26+ is the installed combo.

**If deployment is FalkorDB (existing product path, not catalog milestone):**

- Do not implement catalog persistence against Falkor.
- Return explicit disabled/error; keep factory code paths intact.

**If embedder is OpenAI-compatible custom base URL:**

- Still use `EmbedderFactory` / `OpenAIEmbedder`; same `create()` contract.
- Dimensions must match index/config (`1536` default in MCP Neo4j YAML).

**If running unit tests without Neo4j:**

- Mock `EmbedderClient.create` and driver/transaction; pure UUIDv5/hash/validation tests need no DB.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `graphiti-core` 0.29.2 | `neo4j` 5.28.1, Neo4j server 5.26+ | Vector property helpers in save queries |
| `mcp` 1.27.2 | `pydantic` 2.11.x, starlette 1.3.x, uvicorn 0.34.x | FastMCP HTTP + stdio |
| MCP `openai` 2.43.0 | graphiti-core OpenAI clients | Root library allows `openai>=1.91.0`; MCP pins 2.x |
| `pydantic` 2.11.7 | `pydantic-settings` 2.10.1 | Nested config models |
| Python 3.10 | All above | pyright `pythonVersion = "3.10"` |
| pytest 9.x | pytest-asyncio 1.4 | Async tests for MCP tools |

**Lockfile note:** `mcp_server/uv.lock` resolves `graphiti-core` from **PyPI 0.29.2**, not a path editable to this monorepo. Local `graphiti_core/` matches version **0.29.2**. Prefer implementing catalog tools **inside `mcp_server/`** against public 0.29.2 APIs so lockfile and code stay aligned. Only change core if an API gap is proven; then version/path strategy becomes an explicit decision.

## Milestone API Checklist (what to build on)

| Tool | Stack building blocks |
|------|----------------------|
| `upsert_typed_entities` | Pydantic request → UUIDv5 → embedder.create → `Neo4jDriver.transaction` MERGE Entity+labels → structured result |
| `resolve_typed_entities` | Read-only Cypher / `get_by_uuid` + label/embedding checks; no writes |
| `upsert_typed_edges` | Require existing typed endpoints → UUIDv5 → fact embed → MERGE `RELATES_TO` with `name`=edge type |
| `verify_catalog_batch` | Read-only exact checks (+ optional hybrid interop) |
| `upsert_provenance` (P2) | `EpisodicNode`/`EpisodicEdge` save patterns; no `add_episode` |
| `upsert_catalog_batch` (P2) | Validate all → embed all → one domain TX → status node outside Entity |
| `get_catalog_ingest_status` (P2) | Read `CatalogIngestBatch` by UUIDv5 batch id |

## Sources

- `mcp_server/pyproject.toml`, `mcp_server/uv.lock` — locked versions (mcp 1.27.2, graphiti-core 0.29.2, neo4j 5.28.1, pydantic 2.11.7, openai 2.43.0, pytest 9.0.3, …)
- Root `pyproject.toml` — graphiti-core 0.29.2, neo4j `>=5.26.0`, pydantic `>=2.11.5`
- `.planning/PROJECT.md` — milestone requirements, Neo4j-only, identity rules
- `.planning/codebase/STACK.md` — monorepo stack map
- `mcp_server/src/graphiti_mcp_server.py` — FastMCP tools, GraphitiService init, search/triplet patterns
- `mcp_server/src/config/schema.py`, `config/config-docker-neo4j.yaml` — config + Neo4j defaults
- `mcp_server/src/services/factories.py` — LLM/embedder/DB factories
- `graphiti_core/graphiti.py` — `add_triplet` / `search` / `search_` behavior
- `graphiti_core/nodes.py`, `edges.py` — model fields + `save`/`get_by_uuid`
- `graphiti_core/models/nodes/node_db_queries.py`, `models/edges/edge_db_queries.py` — MERGE Cypher
- `graphiti_core/driver/neo4j_driver.py` — `transaction()`, `execute_query`, `session`
- `graphiti_core/utils/bulk_utils.py` — bulk write path
- `graphiti_core/embedder/client.py` — `EmbedderClient.create`
- `graphiti_core/search/search_filters.py` — `SearchFilters`
- `mcp_server/docker/docker-compose-neo4j.yml` — Neo4j **5.26.0** image
- `mcp_server/tests/README.md`, `conftest.py` — test tooling

Confidence: **HIGH** for installed versions and APIs (lockfile + source). **MEDIUM** only for whether `EntityNode.save` alone preserves every catalog attribute without custom Cypher — validate in Phase 1 integration; prefer explicit Neo4j TX queries if any property/label loss appears.

---
*Stack research for: Deterministic catalog ingestion on Graphiti MCP*
*Researched: 2026-07-16*
