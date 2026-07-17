<!-- refreshed: 2026-07-16 -->
# Architecture

**Analysis Date:** 2026-07-16

## System Overview

Graphiti is a Python framework for building temporally-aware knowledge graphs over a pluggable graph database backend. The repo ships three deployable surfaces that all share one core library.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                         ENTRY / TRANSPORT LAYER                              │
├────────────────────────┬──────────────────────────┬──────────────────────────┤
│  FastAPI REST Server   │   MCP Server (FastMCP)   │   Examples / Notebooks   │
│  `server/graph_service │   `mcp_server/src/       │   `examples/quickstart/` │
│  /main.py`             │   graphiti_mcp_server.py`│   `examples/ecommerce/`  │
│  Routers:              │   Tools: add_memory,     │   Direct Graphiti() use  │
│  `/messages`,          │   search_nodes,          │                          │
│  `/search`,            │   search_memory_facts,   │                          │
│  `/get-memory`         │   add_triplet, ...       │                          │
└──────────┬─────────────┴────────────┬────────────┴────────────┬──────────────┘
           │                          │                          │
           ▼                          ▼                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LAYER (core API)                             │
│              `graphiti_core/graphiti.py`  ::  class `Graphiti`                │
│  add_episode, add_episode_bulk, search, add_triplet, build_communities,      │
│  summarize_saga, remove_episode, retrieve_episodes                           │
│  Holds GraphitiClients bundle (`graphiti_core/graphiti_types.py`)            │
└──────────┬───────────────────────────────────────────────────────────────────┘
           │
   ┌───────┴────────┬───────────────────┬────────────────────┬────────────────┐
   ▼                ▼                   ▼                    ▼                ▼
┌────────────┐ ┌──────────────┐ ┌───────────────┐ ┌─────────────────┐ ┌──────────────┐
│ LLM Client │ │  Embedder    │ │ Cross-Encoder │ │  Search Engine  │ │ Maintenance  │
│ `llm_client│ │  `embedder/` │ │ `cross_encoder│ │ `search/search.py│ │ `utils/      │
│ /client.py`│ │  client.py   │ │ /client.py`   │ │  search_utils.py│ │  maintenance/│
│ OpenAI,    │ │ OpenAI,      │ │ OpenAI, BGE,  │ │ Hybrid: vector +│ │ extract,     │
│ Anthropic, │ │ Voyage,      │ │ Gemini        │ │ BM25 + BFS +    │ │ dedupe,      │
│ Gemini,    │ │ Gemini,      │ │ rerankers     │ │ RRF + MMR       │ │ resolve      │
│ Groq       │ │ Ollama       │ │               │ │                 │ │              │
└────────────┘ └──────────────┘ └───────────────┘ └─────────────────┘ └──────┬───────┘
                                                                            │
                                                                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                 DRIVER / PERSISTENCE LAYER                                    │
│   ABC:  `graphiti_core/driver/driver.py` :: `GraphDriver`                     │
│   Impl: `neo4j_driver.py`, `falkordb_driver.py`, `kuzu_driver.py`,           │
│         `neptune_driver.py`                                                  │
│   Operations ABCs:  `driver/operations/*.py`                                 │
│   Per-provider ops: `driver/{neo4j,falkordb,kuzu,neptune}/operations/*.py`   │
│   Interface segregations: `driver/graph_operations/graph_operations.py`,     │
│                          `driver/search_interface/search_interface.py`       │
└──────────┬───────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  External: Neo4j 5.26+ | FalkorDB 1.1.2+ | Kuzu | AWS Neptune (+ OpenSearch) │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Graphiti (facade) | Single entry point. Orchestrates episode ingest, search, triplets, communities, sagas | `graphiti_core/graphiti.py` |
| GraphitiClients | Bundle of driver + llm_client + embedder + cross_encoder + tracer | `graphiti_core/graphiti_types.py` |
| NodeNamespace / EdgeNamespace | OO-flavored save/get/delete API on `graphiti.nodes` / `graphiti.edges` | `graphiti_core/namespaces/nodes.py`, `graphiti_core/namespaces/edges.py` |
| Node models | `Node`, `EntityNode`, `EpisodicNode`, `CommunityNode`, `SagaNode` Pydantic models | `graphiti_core/nodes.py` |
| Edge models | `Edge`, `EntityEdge`, `EpisodicEdge`, `CommunityEdge`, `HasEpisodeEdge`, `NextEpisodeEdge` | `graphiti_core/edges.py` |
| EpisodeType enum | `message`, `json`, `text`, `fact_triple` content variants | `graphiti_core/nodes.py:54` |
| LLM client ABC + impls | Structured-output LLM calls with retry, tracing, optional cache | `graphiti_core/llm_client/client.py` |
| Embedder ABC + impls | `create()` / `create_batch()` over a single modality | `graphiti_core/embedder/client.py` |
| Cross-encoder rerankers | Rerank candidate edges/nodes for hybrid search | `graphiti_core/cross_encoder/client.py` |
| Search engine | Config-driven hybrid search (semantic + fulltext + graph + reranking) | `graphiti_core/search/search.py` |
| Search utils | Concrete search primitives (vector, BM25, BFS, RRF, MMR) | `graphiti_core/search/search_utils.py` |
| SearchFilters | Node-label, edge-type, date-range, center-node filtering | `graphiti_core/search/search_filters.py` |
| Search recipes | Pre-built `SearchConfig` combinations | `graphiti_core/search/search_config_recipes.py` |
| Prompts library | Versioned LLM prompts + helpers for extract / dedupe / summarize | `graphiti_core/prompts/` |
| Bulk utils | Bulk episode ingest, batched extract/dedupe/resolve | `graphiti_core/utils/bulk_utils.py` |
| Maintenance ops | Extract → resolve → dedupe → build communities | `graphiti_core/utils/maintenance/` |
| Driver ABC | Provider-agnostic graph operations interface, transactions, index names | `graphiti_core/driver/driver.py` |
| Neo4j driver | `AsyncGraphDatabase`-backed driver, real transactions, schedules index builds | `graphiti_core/driver/neo4j_driver.py` |
| FalkorDB driver | Redis-protocol-backed driver | `graphiti_core/driver/falkordb_driver.py` |
| Kuzu driver | Embedded graph DB driver (deprecated extra) | `graphiti_core/driver/kuzu_driver.py` |
| Neptune driver | AWS Neptune + OpenSearch driver | `graphiti_core/driver/neptune_driver.py` |
| Operations layer | Per-entity-type CRUD ABCs + per-provider concrete impls | `graphiti_core/driver/operations/`, `graphiti_core/driver/{provider}/operations/` |
| GraphQueries (Cypher templates) | Index/constraint DDL + fulltext index definitions per provider | `graphiti_core/graph_queries.py` |
| DB queries (templates) | Parameterized save/return Cypher fragments per provider | `graphiti_core/models/nodes/node_db_queries.py`, `graphiti_core/models/edges/edge_db_queries.py` |
| Tracer | OpenTelemetry span wrapper with no-op fallback | `graphiti_core/tracer.py` |
| Telemetry | Posthog event capture (init events) | `graphiti_core/telemetry/telemetry.py` |
| Errors | Domain exceptions (Edge/Node not found, validation, reranker) | `graphiti_core/errors.py` |
| Helpers | `semaphore_gather`, group-id / label validation, date parsing | `graphiti_core/helpers.py` |
| Decorators | Multi-group-id fanout wrapper | `graphiti_core/decorators.py` |
| MCP server | FastMCP tool surface (`add_memory`, `search_nodes`, `search_memory_facts`, `add_triplet`, `build_communities`, `summarize_saga`, `update_entity`, `delete_*`, `clear_graph`, `get_episode_entities`) | `mcp_server/src/graphiti_mcp_server.py` |
| MCP config schema | YAML + env-driven config for LLM/embedder/DB providers | `mcp_server/src/config/schema.py` |
| MCP factories | Construct LLM/Embedder/Driver from config | `mcp_server/src/services/factories.py` |
| MCP queue service | Per-group_id sequential episode processing queue | `mcp_server/src/services/queue_service.py` |
| MCP type config | Build entity_types / edge_types / edge_type_map from config | `mcp_server/src/utils/type_config.py` |
| FastAPI server | REST endpoints, `ZepGraphiti(Graphiti)` subclass | `server/graph_service/main.py`, `server/graph_service/zep_graphiti.py` |
| Server DTOs | Pydantic request/response models for REST API | `server/graph_service/dto/` |

## Pattern Overview

**Overall:** Strategy pattern with dependency injection at the driver / LLM / embedder / cross-encoder boundaries, layered on a single Facade (`Graphiti`).

**Key Characteristics:**
- One Facade class (`Graphiti`) holds a `GraphitiClients` bundle (`driver`/`llm_client`/`embedder`/`cross_encoder`/`tracer`) and forwards every public operation to either a namespace method, a maintenance util, or a search function.
- The driver is an ABC with four concrete providers, each contributing an `operations/` directory whose classes share a common ABC in `driver/operations/`.
- Search is a pure function (`search(...)`) over an immutable-ish `SearchConfig`, composed from primitives in `search_utils.py`. Rerankers are pluggable via the cross-encoder.
- All async, coroutine fan-out is gated by `semaphore_gather` (`graphiti_core/helpers.py`) with `max_coroutines` configurable per instance.
- `group_id` partitions data throughout: every node/edge write and every search call threads it through.

## Layers

**Transport / Entry Layer:**
- Purpose: Accept episodes and serve searches over a protocol.
- Location: `server/graph_service/`, `mcp_server/src/`, `examples/`
- Contains: FastAPI app, FastMCP server, Jupyter notebooks, CLI scripts.
- Depends on: `graphiti_core`.
- Used by: External HTTP / MCP / notebook clients.

**Orchestration Layer:**
- Purpose: Episode → entity extraction → dedupe → resolve → persist → search.
- Location: `graphiti_core/graphiti.py` (1798 lines, the single facade).
- Contains: `class Graphiti`, `AddEpisodeResults`, `AddBulkEpisodeResults`, `AddTripletResults` result models.
- Depends on: `nodes.py`, `edges.py`, `driver/`, `llm_client/`, `embedder/`, `cross_encoder/`, `search/`, `utils/maintenance/`, `utils/bulk_utils.py`, `prompts/`, `namespaces/`.
- Used by: Transport layer, examples, tests.

**Client / Abstraction Layer:**
- Purpose: Provider-swappable LLM, embedding, cross-encoder, and tracing clients.
- Location: `graphiti_core/llm_client/`, `graphiti_core/embedder/`, `graphiti_core/cross_encoder/`, `graphiti_core/telemetry/`, `graphiti_core/tracer.py`.
- Depends on: External SDKs (openai, anthropic, google-genai, groq, voyageai, sentence-transformers, opentelemetry-sdk, posthog).
- Used by: Orchestration layer via `GraphitiClients`.

**Persistence Layer:**
- Purpose: Persist nodes / edges / episodes / communities; execute fulltext + vector search; maintain indices.
- Location: `graphiti_core/driver/` and its provider subpackages.
- Contains: `GraphDriver` ABC, `QueryExecutor` / `Transaction` ABCs, `GraphOperationsInterface`, `SearchInterface`, per-provider operation classes.
- Depends on: External driver SDKs (`neo4j`, `falkordb`, `kuzu`, `langchain-aws`/`opensearch-py`).
- Used by: Orchestration, namespaces, maintenance utils.

**Prompts & Models Layer:**
- Purpose: LLM prompt templates, Pydantic node/edge shapes, DB query fragments.
- Location: `graphiti_core/prompts/`, `graphiti_core/nodes.py`, `graphiti_core/edges.py`, `graphiti_core/models/`.
- Depends on: `pydantic`, `embedder` (for `generate_name_embedding`), `driver` (for `GraphProvider` enum).
- Used by: Orchestration, maintenance utils, search.

## Data Flow

### Primary: Episode Ingest (`add_episode`)

1. HTTP/MCP/notebook invokes `Graphiti.add_episode(uuid, group_id, name, episode_body, reference_time, source_description, ...)` (`graphiti_core/graphiti.py:985`).
2. Episode raw content is stored via `EpisodeNode` + episodic edges (`utils/maintenance/edge_operations.py:build_episodic_edges`).
3. Previous episodes are retrieved for context (`utils/maintenance/graph_data_operations.py:retrieve_episodes`).
4. LLM extracts nodes and edges via `utils/maintenance/node_operations.py:extract_nodes` and `edge_operations.py:extract_edges`, using prompts from `graphiti_core/prompts/`.
5. Extracted nodes are resolved/deduped against existing entities (`node_operations.py:resolve_extracted_nodes`, `utils/maintenance/dedup_helpers.py`).
6. Extracted edges are resolved/deduped (`edge_operations.py:resolve_extracted_edge`, `resolve_extracted_edges`).
7. Node/edge embeddings are generated (`nodes.py:create_entity_node_embeddings`, `edges.py:create_entity_edge_embeddings`).
8. Nodes/edges persisted through `driver.{entity_node_ops,entity_edge_ops,...}.save(...)`.
9. Communities optionally rebuilt (`utils/maintenance/community_operations.py`).
10. `AddEpisodeResults` returned (`graphiti_core/graphiti.py:114`).

**Bulk variant** (`add_episode_bulk`, `graphiti.py:1235`) batches many episodes through `utils/bulk_utils.py` (`extract_nodes_and_edges_bulk`, `dedupe_nodes_bulk`, `dedupe_edges_bulk`, `resolve_edge_pointers`, `add_nodes_and_edges_bulk`).

### Primary: Search (`search`)

1. Caller invokes `Graphiti.search(group_ids, query, num_results, search_config=...)` (`graphiti_core/graphiti.py:1532`).
2. Dispatched to `search.search(driver, clients, query, group_ids, config)` (`graphiti_core/search/search.py`).
3. Per-config: vector similarity (`node_similarity_search`, `edge_similarity_search`), BM25 fulltext (`node_fulltext_search`, `edge_fulltext_search`), BFS (`node_bfs_search`, `edge_bfs_search`) — all in `search_utils.py`.
4. Results combined via reciprocal rank fusion (`rrf`) and/or maximal marginal relevance (`maximal_marginal_relevance`).
5. Cross-encoder reranks (`cross_encoder/client.py`) when configured.
6. `SearchResults` (`search/search_config.py`) returned — contains nodes, edges, episodes, communities.

### Secondary: Direct Triplet Write (`add_triplet`)

1. Caller invokes `Graphiti.add_triplet(...)` (`graphiti_core/graphiti.py:1650`).
2. Endpoint nodes resolved by name + group_id; edge created with `valid_at` / `invalid_at` temporal fields.
3. Embeddings generated; save called through driver ops. No LLM extraction.

**State Management:**
- All persistent state lives in the graph DB. The `Graphiti` instance is stateless between calls except for the connected driver and injected clients. Per-episode results are returned as Pydantic models, never cached on the instance.
- Bi-temporal fields on `EntityEdge` (`valid_at`, `invalid_at`, `created_at`) and `EpisodicNode` (`valid_at`, `created_at`) implement the bi-temporal model.

## Key Abstractions

**GraphDriver (strategy):**
- Purpose: Unify Neo4j / FalkorDB / Kuzu / Neptune behind one interface.
- Examples: `graphiti_core/driver/neo4j_driver.py:60`, `graphiti_core/driver/falkordb_driver.py`, `graphiti_core/driver/kuzu_driver.py`, `graphiti_core/driver/neptune_driver.py`.
- Pattern: ABC in `graphiti_core/driver/driver.py:90` with per-provider concrete classes. Each driver exposes its operations via properties (`entity_node_ops`, `search_ops`, `graph_ops`, ...).

**Operations (strategy-per-entity-type):**
- Purpose: Decouple CRUD logic from both the driver and the model, so each provider can swap query strings independently.
- Examples: `graphiti_core/driver/operations/entity_node_ops.py`, `graphiti_core/driver/neo4j/operations/entity_node_ops.py`, `graphiti_core/driver/falkordb/operations/entity_node_ops.py`.
- Pattern: Abstract base in `driver/operations/<entity>_ops.py`; concrete impl per provider in `driver/<provider>/operations/<entity>_ops.py`. Callers always go through `driver.{entity}_ops`.

**SearchConfig (specification):**
- Purpose: Compose search behavior declaratively.
- Examples: `graphiti_core/search/search_config.py`, `graphiti_core/search/search_config_recipes.py`.
- Pattern: Pydantic `SearchConfig` holds nested `NodeSearchConfig`, `EdgeSearchConfig`, `EpisodeSearchConfig`, `CommunitySearchConfig`; each carries search method + reranker enums. Pre-built recipes (`COMBINED_HYBRID_SEARCH_CROSS_ENCODER`, `EDGE_HYBRID_SEARCH_RRF`, etc.) are the default entry points.

**LLMClient / EmbedderClient / CrossEncoderClient (strategy):**
- Purpose: Swap providers without touching orchestration code.
- Examples: `graphiti_core/llm_client/client.py:75`, `graphiti_core/embedder/client.py:30`, `graphiti_core/cross_encoder/client.py`.
- Pattern: ABC + concrete implementations. `Graphiti.__init__` accepts any subclass via DI; falls back to OpenAI defaults.

**NodeNamespace / EdgeNamespace (facade over driver ops):**
- Purpose: Provide OO API like `graphiti.nodes.entity.save(node)`.
- Examples: `graphiti_core/namespaces/nodes.py`, `graphiti_core/namespaces/edges.py`.
- Pattern: Thin wrapper delegating to the driver's ops properties and the embedder.

**GraphitiClients (aggregate):**
- Purpose: Carry the five clients together.
- Examples: `graphiti_core/graphiti_types.py:26`.

**Pydantic models as the DB schema:**
- Purpose: Single source of truth for node/edge shape across transport, LLM, and persistence.
- Examples: `graphiti_core/nodes.py:EntityNode`, `graphiti_core/edges.py:EntityEdge`.

## Entry Points

**Library (primary):**
- Location: `graphiti_core/__init__.py` exports `Graphiti`.
- Triggers: `from graphiti_core import Graphiti; graphiti = Graphiti(uri=..., user=..., password=...)`.
- Responsibilities: Construct driver, LLM, embedder, cross-encoder; wire tracer; expose `add_episode`, `add_episode_bulk`, `search`, `add_triplet`, `build_communities`, `summarize_saga`, `remove_episode`, `retrieve_episodes`, `close`, `build_indices_and_constraints`.

**MCP server:**
- Location: `mcp_server/main.py` → `mcp_server/src/graphiti_mcp_server.py:187` (`FastMCP('Graphiti Agent Memory', ...)`).
- Triggers: `uv run python main.py` (stdio/http/sse transport selected by config); also containerized via `mcp_server/docker/`.
- Responsibilities: Register tools (add_memory, search_nodes, search_memory_facts, add_triplet, get_entity_edge, get_episodes, get_episode_entities, update_entity, build_communities, summarize_saga, delete_episode, delete_entity_edge, clear_graph, get_status); own `GraphitiService` wrapper with semaphore and per-group_id `QueueService`.

**FastAPI REST server:**
- Location: `server/graph_service/main.py:20` (`app = FastAPI(lifespan=lifespan)`).
- Triggers: `uvicorn graph_service.main:app --reload` from `server/`.
- Responsibilities: Mount `routers/ingest.py` (`POST /messages`, `POST /add-entity`) and `routers/retrieve.py` (`POST /search`, `POST /get-memory`, `GET /entity-edge/{uuid}`, `GET /episodes/{group_id}`), expose `/healthcheck`. Uses `ZepGraphiti(Graphiti)` subclass per request.

**Examples / quickstart:**
- Location: `examples/quickstart/quickstart_neo4j.py`, `examples/quickstart/quickstart_falkordb.py`, `examples/quickstart/quickstart_neptune.py`, `examples/ecommerce/runner.py`, `examples/langgraph-agent/agent.ipynb`.
- Triggers: Direct script / notebook execution.
- Responsibilities: Demonstrate direct library usage; not deployable services.

**Tests:**
- Location: `conftest.py`, `tests/` (driver, llm_client, embedder, cross_encoder, utils, evals).
- Triggers: `make test` / `pytest`.
- Responsibilities: Unit and integration coverage. Integration tests use the `_int` suffix and require live DBs.

## Architectural Constraints

- **Threading:** Single-threaded asyncio event loop. All I/O (LLM, DB, embedder) is `async`. Concurrency is bounded by `semaphore_gather` and the per-instance `max_coroutines` value. No threads or worker pools.
- **Global state:** Minimal at core. Module-level constants in `graphiti_core/driver/driver.py:53-56` read index names from env (`ENTITY_INDEX_NAME`, `EPISODE_INDEX_NAME`, `COMMUNITY_INDEX_NAME`, `ENTITY_EDGE_INDEX_NAME`). `EMBEDDING_DIM` is module-level in `graphiti_core/embedder/client.py:23`. MCP server keeps module-level globals (`graphiti_service`, `queue_service`, `graphiti_client`, `semaphore`, `config`, `mcp`) in `mcp_server/src/graphiti_mcp_server.py`.
- **Circular imports:** Actively avoided. `driver/operations/*` depend only on `QueryExecutor` (not `GraphDriver`) — see comment in `graphiti_core/driver/query_executor.py:33-38`. `GraphOperationsInterface` and `SearchInterface` use `Any` type hints to break cycles (`graphiti_core/driver/graph_operations/graph_operations.py:26`, `graphiti_core/driver/search_interface/search_interface.py:26`). `TYPE_CHECKING` guards in `driver/driver.py:34-46`.
- **Python version:** `>=3.10,<4` (pyproject.toml). Some optional deps gated to `>=3.11` (gliner2) or `>=3.12` (falkordblite).
- **DB provider availability:** Each non-Neo4j driver is an optional import — call sites wrap `from graphiti_core.driver.<x>_driver import ...` in try/except and degrade gracefully.
- **LLM structured output:** Required for extraction. Providers without native structured output (Groq, smaller Anthropic models) may produce schema validation errors. Default provider is OpenAI.
- **Index/constraint bootstrap:** `Neo4jDriver.__init__` schedules `build_indices_and_constraints()` as a background task on the running event loop (`driver/neo4j_driver.py:94-101`).

## Anti-Patterns

### God-class on `Graphiti`

**What happens:** `graphiti_core/graphiti.py` is a 1798-line single class owning episode ingest, bulk ingest, triplet write, search dispatch, community build, saga summarization, episode removal, and index bootstrap.
**Why it's wrong:** High churn area; any feature touches the same file; hard to test in isolation.
**Do this instead:** For new functionality, prefer extending `graphiti_core/utils/maintenance/` or a namespace, and have `Graphiti` delegate. The `nodes`/`edges` namespaces (`graphiti_core/namespaces/`) already model the correct delegation pattern.

### Provider-conditionals at call sites

**What happens:** Several call sites branch on `GraphProvider` enum value to pick query strings (e.g. `models/nodes/node_db_queries.py:get_entity_node_save_query(GraphProvider.NEO4J, labels)`).
**Why it's wrong:** New provider requires editing many call sites; risk of missing one.
**Do this instead:** Keep provider-specific query strings centralized in `graphiti_core/models/{nodes,edges}/*_db_queries.py` and `graphiti_core/graph_queries.py`, and route through the per-provider operations classes (`driver/<provider>/operations/`).

### Module-level singleton config in MCP server

**What happens:** `mcp_server/src/graphiti_mcp_server.py:134` builds a global `config = GraphitiConfig()` at import time; `graphiti_service`, `queue_service`, `graphiti_client`, `semaphore` are module-level globals assigned during lifespan startup.
**Why it's wrong:** Import-time side effects make testing harder; global mutation during lifespan startup couples startup ordering to module import order.
**Do this instead:** For new MCP tools, accept the `graphiti_service` / `queue_service` as parameters via FastMCP's dependency injection, or read from the single `graphiti_service` global rather than introducing new ones.

## Error Handling

**Strategy:** Raise typed `GraphitiError` subclasses (`graphiti_core/errors.py`); REST/MCP layers translate to HTTP status codes or MCP error responses.

**Patterns:**
- `NodeNotFoundError`, `EdgeNotFoundError`, `EdgesNotFoundError`, `GroupsEdgesNotFoundError`, `GroupsNodesNotFoundError` — all carry the UUID / group_id in `.message`.
- `EntityTypeValidationError`, `GroupIdValidationError`, `NodeLabelValidationError` — raised at trust boundaries (input validation in `graphiti_core/helpers.py:validate_group_id`, `validate_node_labels`, `graphiti_core/utils/ontology_utils/entity_types_utils.py`).
- `SearchRerankerError` — raised when cross-encoder reranking fails.
- LLM transient failures retried via `tenacity` (`@retry(stop=stop_after_attempt(4), wait=wait_random_exponential(...))` in `llm_client/client.py:120-130`); `RateLimitError` and 5xx server errors are retried.
- `Neo4jDriver._execute_index_query` (`driver/neo4j_driver.py:191-204`) swallows `EquivalentSchemaRuleAlreadyExists` races.
- `Graphiti._capture_initialization_telemetry` (`graphiti.py:250-269`) swallows telemetry errors silently.

## Cross-Cutting Concerns

**Logging:** stdlib `logging.getLogger(__name__)` per module; no central config in core. MCP server configures root format/stream in `mcp_server/src/graphiti_mcp_server.py:99-128`. Server module uses `print` for queue status (`server/graph_service/routers/ingest.py:21`) — inconsistent with rest of codebase.

**Validation:** Pydantic v2 for all input/output models; `@field_validator` on node/edge models (e.g. `nodes.py` date parsing). Group-id and node-label validation in `graphiti_core/helpers.py`. Entity-type attribute-name validation in `graphiti_core/utils/ontology_utils/entity_types_utils.py`.

**Authentication:** None in core library. REST server has no auth layer. MCP server uses `TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=...)` (`mcp_server/src/graphiti_mcp_server.py:192-195`). All provider API keys flow through env vars or YAML config into the respective client factories.

**Tracing:** OpenTelemetry via `graphiti_core/tracer.py` — `Tracer` ABC wraps spans; `NoOpTracer` default. Set via `Graphiti(tracer=...)` or env (`OTEL_TRACING.md`). LLM client auto-wraps each generation in a span.

**Telemetry:** Posthog `capture_event('graphiti_initialized', ...)` fired once per `Graphiti()` construction; failures swallowed silently (`graphiti.py:250-269`).

---

*Architecture analysis: 2026-07-16*
