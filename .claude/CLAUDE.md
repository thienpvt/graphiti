<!-- GSD:project-start source:PROJECT.md -->

## Project

**Deterministic Catalog Ingestion for Graphiti MCP**

An extension to the existing Graphiti MCP server that adds synchronous, typed, deterministic, idempotent Neo4j upsert tools for structured database catalogs. It targets PDF catalog, DDL, Oracle dictionary, and SQL parser output where entity and relationship identity must be exact and no LLM extraction or asynchronous ingestion may occur.

The implementation preserves all existing Graphiti and MCP behavior. Work is split into a gated Phase 1 foundation and Phase 2 provenance and atomic batch orchestration.

**Core Value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.

### Constraints

- **Compatibility**: Preserve every existing MCP tool and behavior — this is additive functionality
- **Backend**: Neo4j first, using installed driver semantics and Neo4j 5.26+ behavior — no unsupported portability claim
- **Identity**: Server-derived UUIDv5 only, using a fixed configured namespace — caller UUIDs are never identity authority
- **Configuration**: `GRAPHITI_CATALOG_UUID_NAMESPACE` is immutable deployment configuration — changing it changes every deterministic identity
- **Safety**: Never interpolate unvalidated client labels or property names into Cypher — labels and properties come from fixed server allowlists
- **Transactions**: Writes return only after commit or rollback; atomic batches roll back completely on conflict or write failure
- **Embeddings**: Generate with the configured embedder before opening the Neo4j write transaction — embedding failure cannot produce partial writes
- **Isolation**: Every read and write is constrained by `group_id`; tests use only `oracle-catalog-tool-test`
- **Validation**: Validate complete requests, collection limits, string limits, hashes, prefixes, nested references, confidence range, NaN, infinity, and protected properties
- **Logging**: Log batch IDs and counts only — never credentials, complete catalog payloads, raw documents, or complete source text
- **Data preservation**: Preserve original `created_at`, endpoint UUIDs, labels, and exact `name_raw`/`name_canonical`; add `updated_at`
- **Scale**: Default limits are 500 entities, 2,000 edges, and 5,000 provenance links per batch
- **Workflow**: Phase 2 is blocked until every Phase 1 gate passes and a Phase 1 report is produced
- **Operations**: No deployment, live-group writes, full ingest, graph clearing, or existing-data deletion

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python `>=3.10,<4` - All application code across `graphiti_core/`, `server/`, `mcp_server/`. Pinned to 3.10 minimum by `pyproject.toml`; Docker images use 3.11-slim-bookworm (`mcp_server/docker/Dockerfile.standalone:6`) or 3.12-slim (`Dockerfile:2`).
- YAML - Configuration (`mcp_server/config/*.yaml`), Docker Compose, Kubernetes manifests (`mcp_server/k8s/`).
- Bash - Container entrypoint script (`mcp_server/docker/Dockerfile:72`) and Make targets (`Makefile`).
- Cypher - Graph query language embedded throughout `graphiti_core/driver/` and `graphiti_core/graph_queries.py`.

## Runtime

- CPython 3.10 minimum. Runtime images use Python 3.11 (standalone MCP) or 3.12 (server).
- Async-first: built on `asyncio` (drivers, LLM/embedder clients, FastAPI, MCP server all `async`).
- `uv` (Astral) - single source of truth. Pinned to `0.8.15` in standalone build (`mcp_server/docker/Dockerfile.standalone:5`).
- Lockfiles present: `uv.lock` (root, ~997KB), `server/uv.lock`, `mcp_server/uv.lock`.
- Installed via official installer script in Dockerfiles (`Dockerfile:26-27`, `mcp_server/docker/Dockerfile:19-20`).

## Frameworks

- Pydantic `>=2.11.5` - Data models, config schemas, validation. Foundational to `nodes.py`, `edges.py`, `graphiti_core/models/`, `mcp_server/src/config/schema.py`, `mcp_server/src/models/`.
- `python-dotenv` `>=1.0.1` - `.env` loading in `graphiti_core/driver/driver.py:51`, `mcp_server/src/graphiti_mcp_server.py:17-66`.
- FastAPI `>=0.115.0` - REST API in `server/graph_service/main.py`, routers in `server/graph_service/routers/`.
- Uvicorn `>=0.44.0` - ASGI server. Launch command in `Dockerfile:78`.
- `pydantic-settings` `>=2.4.0` - Typed settings in `server/graph_service/config.py`, `mcp_server/src/config/schema.py:9-13`.
- `mcp` `>=1.27.2,<2` - Model Context Protocol SDK (`mcp.server.fastmcp.FastMCP`) instantiated in `mcp_server/src/graphiti_mcp_server.py:187`. Uses `TransportSecuritySettings` for DNS rebinding protection (`:192-195`).
- pytest `>=8.3.3` - Runner. Config in `pytest.ini`, `pyproject.toml:[tool.pytest.ini_options]`.
- `pytest-asyncio` `>=0.24.0` - `asyncio_mode = auto` (`pytest.ini:5`).
- `pytest-xdist` `>=3.6.1` - Parallel test execution.
- `pytest-timeout` (mcp_server dev group) - Per-test timeouts.
- Ruff `>=0.7.1` - Format + lint. Line length 100, single quotes, isort. Config in `pyproject.toml:[tool.ruff]`.
- Pyright `>=1.1.404` - Type checking. `typeCheckingMode = "basic"` for `graphiti_core`/`mcp_server`, `"standard"` for `server/` (`server/pyproject.toml:74`).
- Hatchling - Build backend (`pyproject.toml:[build-system]`).

## Key Dependencies

- `neo4j` `>=5.26.0` - Official Python driver, used by `graphiti_core/driver/neo4j_driver.py`. Requires Neo4j 5.26+.
- `falkordb` `>=1.1.2,<2.0.0` - FalkorDB client, used by `graphiti_core/driver/falkordb_driver.py`. Optional extra `[falkordb]`.
- `falkordblite` `>=0.5.0` - Embedded test backend (Python 3.12+ only). Pinned `redis<9` for compat (`pyproject.toml:36`).
- `kuzu` `>=0.11.3` - Kuzu embedded graph DB. Marked deprecated in `pyproject.toml:32-33`. Used by `graphiti_core/driver/kuzu_driver.py`.
- `openai` `>=1.91.0` (root), `>=2.41.0` (mcp_server) - OpenAI client. Both Responses API (`graphiti_core/llm_client/openai_client.py`) and Chat Completions (`openai_generic_client.py`).
- `anthropic` `>=0.49.0` (optional `[anthropic]` extra) - `graphiti_core/llm_client/anthropic_client.py`.
- `google-genai` `>=1.62.0` (optional `[google-genai]` extra) - `graphiti_core/llm_client/gemini_client.py`.
- `groq` `>=0.2.0` (optional `[groq]` extra) - `graphiti_core/llm_client/groq_client.py`.
- `voyageai` `>=0.2.3` - Embeddings via `graphiti_core/embedder/voyage.py`.
- `boto3` `>=1.39.16` - AWS SDK for Neptune Auth.
- `langchain-aws` `>=0.2.29` - `NeptuneAnalyticsGraph` / `NeptuneGraph` wrappers (`graphiti_core/driver/neptune_driver.py:23-25`).
- `opensearch-py` `>=3.0.0` - OpenSearch/AOSS for Neptune full-text search (`graphiti_core/driver/neptune_driver.py:25`).
- `httpx` `>=0.28.1` - Async HTTP client used by LLM/embedder integrations.
- `tenacity` `>=9.0.0` - Retry logic in LLM clients.
- `numpy` `>=1.0.0` - Numerical ops on embeddings.
- `posthog` `>=3.0.0` - Anonymous telemetry in `graphiti_core/telemetry/telemetry.py`.
- `pyyaml` `>=6.0.3` - YAML config parsing in MCP server.
- `opentelemetry-api` + `opentelemetry-sdk` `>=1.20.0` (optional `[tracing]` extra) - Distributed tracing. See `OTEL_TRACING.md` and `graphiti_core/tracer.py`.
- `sentence-transformers` `>=3.2.1` - Local embeddings.
- `gliner2` `>=1.2.0` (Python 3.11+) - NER-based entity extraction via `graphiti_core/llm_client/gliner2_client.py`.

## Configuration

- `.env` files loaded by `python-dotenv` at multiple entry points.
- `.env.example` at repo root lists: `OPENAI_API_KEY`, `NEO4J_URI/PORT/USER/PASSWORD`, `FALKORDB_URI/PORT/USER/PASSWORD`, `USE_PARALLEL_RUNTIME`, `SEMAPHORE_LIMIT`, `GITHUB_SHA`, `MAX_REFLEXION_ITERATIONS`, `ANTHROPIC_API_KEY`.
- MCP server supports YAML config with `${VAR}` / `${VAR:default}` expansion (`mcp_server/src/config/schema.py:23-58`). Config path set via `CONFIG_PATH` env (default `config/config.yaml`).
- pydantic-settings priority order (mcp_server): CLI args > env vars > YAML > defaults (`mcp_server/src/config/schema.py:307`).
- `OPENAI_API_KEY` (or equivalent provider key) - mandatory for LLM + embeddings.
- Database credentials - one of Neo4j (`NEO4J_*`), FalkorDB (`FALKORDB_*`), or Neptune/AOSS.
- `pyproject.toml` - root library (`graphiti-core`).
- `server/pyproject.toml` - FastAPI service (`graph-service`).
- `mcp_server/pyproject.toml` - MCP server (`mcp-server`).
- `Dockerfile` - root server image (Python 3.12, uv, non-root user).
- `mcp_server/docker/Dockerfile` - combined FalkorDB+MCP image (Python 3.11 on FalkorDB base).
- `mcp_server/docker/Dockerfile.standalone` - standalone MCP image connecting to external DB.
- `docker-compose.yml`, `docker-compose.test.yml`, `mcp_server/docker/docker-compose-{neo4j,falkordb}.yml`.
- `mcp_server/k8s/graphiti-neo4j.yaml` - Kubernetes manifest (Neo4j + MCP Deployment, NodePort 30080).
- Ruff: `line-length = 100`, single quotes, isort. Rules: E, F, UP, B, SIM, I (`pyproject.toml:76-94`).
- `typing.TypedDict` banned in favor of `typing_extensions.TypedDict` (`pyproject.toml:96-98`).

## Platform Requirements

- Python 3.10+ (3.11+ for `gliner2`, 3.12+ for `falkordblite`).
- `uv` for env management (`make install` runs `uv sync --extra dev`).
- Neo4j 5.26+ or FalkorDB 1.1.2+ for integration tests.
- `Makefile` targets: `make format`, `make lint`, `make test`, `make check`.
- Unit tests run with `DISABLE_FALKORDB=1 DISABLE_KUZU=1 DISABLE_NEPTUNE=1 pytest -m "not integration"` (`Makefile:29`).
- Docker images published to GHCR: `ghcr.io/thienpvt/graphiti-mcp` (standalone MCP, see `.github/workflows/publish-mcp-image.yml:23`).
- Root server image built from `Dockerfile` (published via `.github/workflows/release-server-container.yml`).
- MCP combined image hosts FalkorDB + MCP in a single container (`mcp_server/docker/Dockerfile`).
- K8s deployment targets an in-cluster Neo4j and exposes MCP via NodePort 30080 (`mcp_server/k8s/graphiti-neo4j.yaml`).
- Python runtime set to `PYTHONUNBUFFERED=1` in all Docker images.

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Repository Layout

- `graphiti_core/` — core library (`graphiti-core`, version in `pyproject.toml:4`)
- `server/` — FastAPI service (`graph-service`, `server/pyproject.toml`)
- `mcp_server/` — MCP server (`mcp_server/pyproject.toml`)

## Naming Patterns

- `snake_case.py` everywhere. Test files prefixed `test_`; integration tests suffixed `_int.py` (e.g. `tests/test_graphiti_int.py`, `tests/llm_client/test_anthropic_client_int.py`).
- Helper modules shared across tests use the `_test.py` / `_fixtures.py` suffix: `tests/helpers_test.py`, `tests/embedder/embedder_fixtures.py`.
- Private modules are `_`-prefixed only inside packages when meant to be internal (e.g. `graphiti_core/driver/neo4j/operations/`).
- `snake_case`. Async functions same — no `async_` prefix.
- Public API entrypoints on `Graphiti` are verbs: `add_episode`, `save_entity_node`, `close`, `search`.
- Internal helpers are `_`-prefixed: `_resolve_with_llm`, `_extract_entity_summaries_batch`, `_clean_input`, `_get_cache_key`, `_resolve_reasoning_effort`, `_apply_attribute_extraction_preamble`.
- Factory functions use `get_` prefix: `get_driver`, `get_default_group_id`, `get_entity_node_save_query`.
- `snake_case` locals, `SCREAMING_SNAKE_CASE` module-level constants.
- Constants cluster at top of module after imports: `graphiti_core/helpers.py:35-55` (`SAFE_CYPHER_IDENTIFIER_PATTERN`, `USE_PARALLEL_RUNTIME`, `SEMAPHORE_LIMIT`, `CHUNK_TOKEN_SIZE`, ...), `graphiti_core/llm_client/client.py:34-35` (`DEFAULT_TEMPERATURE`, `DEFAULT_CACHE_DIR`), `graphiti_core/driver/driver.py:49-56` (`DEFAULT_SIZE`, `ENTITY_INDEX_NAME`, ...).
- `PascalCase`. Implementations suffixed by role: `OpenAIClient`, `OpenAIEmbedder`, `Neo4jDriver`, `FalkorDriver`, `Neo4jSearchOperations`, `OpenAIRerankerClient`.
- Abstract bases: `LLMClient(ABC)`, `EmbedderClient(ABC)`, `GraphDriver(ABC)`, `CrossEncoderClient(ABC)`, `GraphOperationsInterface`.
- Pydantic models subclass `BaseModel`: result wrappers (`AddEpisodeResults`, `AddTripletResults`), config objects (`EmbedderConfig`, `LLMConfig`, `OpenAIEmbedderConfig`), prompt payload models (`Edge`, `ExtractedEdges`, `EdgeDuplicate`).
- Enums subclass `Enum`: `GraphProvider`, `EpisodeType`.
- All in `graphiti_core/errors.py`, subclass `GraphitiError(Exception)`. Named `*Error`: `EdgeNotFoundError`, `NodeNotFoundError`, `EntityTypeValidationError`, `GroupIdValidationError`, `NodeLabelValidationError`, `SearchRerankerError`.
- Dual-inheritance for ValueError compatibility where Pydantic field validators raise them: `class NodeLabelValidationError(GraphitiError, ValueError)` (`errors.py:86`).
- Constructor stores `.message` and calls `super().__init__(self.message)`.

## Code Style

- Line length: **100** (`pyproject.toml:77`, `server/pyproject.toml:46`).
- Quote style: **single** (`[tool.ruff.format] quote-style = "single"`).
- Indent: spaces.
- Docstrings: formatted as code (`docstring-code-format = true`).
- `ignore = ["E501"]` — line-length lint disabled, formatter owns wrapping.
- `graphiti_core`: `typeCheckingMode = "basic"`, `pythonVersion = "3.10"`, `include = ["graphiti_core"]` (`pyproject.toml:105-108`).
- `server`: `typeCheckingMode = "standard"`, `include = ["."]` (`server/pyproject.toml:71-74`).
- `mcp_server`: own config in `mcp_server/pyproject.toml`.

## Import Organization

## Error Handling

- `group_id` validated by `validate_group_id` (`graphiti_core/helpers.py`) — alphanumeric + dashes + underscores only; raises `GroupIdValidationError`.
- `node_labels` validated by `validate_node_labels` — pattern `^[A-Za-z_][A-Za-z0-9_]*$` (`SAFE_CYPHER_IDENTIFIER_PATTERN`, `helpers.py:35`). Validation runs both in Pydantic field validators AND at the DB-query build boundary (`get_entity_node_save_query`, `get_entity_node_save_bulk_query`, `node_search_filter_query_constructor`, `edge_search_filter_query_constructor`) so a caller that bypasses Pydantic still cannot inject Cypher. See `tests/test_node_label_security.py` and `tests/utils/search/test_search_security.py` for the contract.
- `fulltext_query` rejects invalid group_ids at the query boundary (`search_utils.py`).

## Logging

- f-string interpolation in log calls (`logger.debug(f'Saved edge to Graph: {self.uuid}')`, `logger.warning(f'Retrying {retry_state.fn.__name__}...')`).
- `debug` for successful saves/deletes on graph entities (`edges.py:90,129,160,294,373,592,706,725`).
- `warning` for retried provider errors and partial degradation (`cross_encoder/gemini_reranker_client.py:134,142`, `embedder/gemini.py:157`).
- `error` for unrecoverable provider failures (`cross_encoder/openai_reranker_client.py:122`, `embedder/gemini.py:180`).

## Comments

- "Why" comments for non-obvious workarounds, citing the failure mode. Strong pattern in this codebase — examples:
- Sentinel versioning for idempotent side effects — `llm_client/client.py:181` (`<<graphiti.attr_extraction.preamble.v1>>`) with instruction to bump suffix when text changes.
- "What" comments are rare; prefer extracting a named helper (`_resolve_with_llm`, `_has_high_entropy`).

## Function Design

## Module Design

- `graphiti_core/llm_client/{client,openai_client,anthropic_client,gemini_client,groq_client}.py`
- `graphiti_core/embedder/{client,openai,voyage,gemini,ollama,...}.py`
- `graphiti_core/driver/{driver,neo4j_driver,falkordb_driver,kuzu_driver,neptune_driver}.py`
- `graphiti_core/cross_encoder/{client,openai_reranker_client,gemini_reranker_client,bge_reranker_client}.py`

## Configuration

- `python-dotenv` auto-loaded at module import (`load_dotenv()` at `helpers.py:33`, `driver.py:51`, `helpers_test.py:31`).
- Feature flags via env vars with defaults: `DISABLE_NEO4J`, `DISABLE_FALKORDB`, `DISABLE_KUZU`, `ENABLE_KUZU`, `DISABLE_NEPTUNE` gate driver registration in `tests/helpers_test.py:34-68`. `SEMAPHORE_LIMIT` (`helpers.py:38`, default 20) caps concurrent async work via `semaphore_gather`. `CHUNK_*` env vars control entity-extraction chunking.
- Secrets (API keys) read from env, never logged, never committed.

## Build / Format / Lint Commands

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

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

- One Facade class (`Graphiti`) holds a `GraphitiClients` bundle (`driver`/`llm_client`/`embedder`/`cross_encoder`/`tracer`) and forwards every public operation to either a namespace method, a maintenance util, or a search function.
- The driver is an ABC with four concrete providers, each contributing an `operations/` directory whose classes share a common ABC in `driver/operations/`.
- Search is a pure function (`search(...)`) over an immutable-ish `SearchConfig`, composed from primitives in `search_utils.py`. Rerankers are pluggable via the cross-encoder.
- All async, coroutine fan-out is gated by `semaphore_gather` (`graphiti_core/helpers.py`) with `max_coroutines` configurable per instance.
- `group_id` partitions data throughout: every node/edge write and every search call threads it through.

## Layers

- Purpose: Accept episodes and serve searches over a protocol.
- Location: `server/graph_service/`, `mcp_server/src/`, `examples/`
- Contains: FastAPI app, FastMCP server, Jupyter notebooks, CLI scripts.
- Depends on: `graphiti_core`.
- Used by: External HTTP / MCP / notebook clients.
- Purpose: Episode → entity extraction → dedupe → resolve → persist → search.
- Location: `graphiti_core/graphiti.py` (1798 lines, the single facade).
- Contains: `class Graphiti`, `AddEpisodeResults`, `AddBulkEpisodeResults`, `AddTripletResults` result models.
- Depends on: `nodes.py`, `edges.py`, `driver/`, `llm_client/`, `embedder/`, `cross_encoder/`, `search/`, `utils/maintenance/`, `utils/bulk_utils.py`, `prompts/`, `namespaces/`.
- Used by: Transport layer, examples, tests.
- Purpose: Provider-swappable LLM, embedding, cross-encoder, and tracing clients.
- Location: `graphiti_core/llm_client/`, `graphiti_core/embedder/`, `graphiti_core/cross_encoder/`, `graphiti_core/telemetry/`, `graphiti_core/tracer.py`.
- Depends on: External SDKs (openai, anthropic, google-genai, groq, voyageai, sentence-transformers, opentelemetry-sdk, posthog).
- Used by: Orchestration layer via `GraphitiClients`.
- Purpose: Persist nodes / edges / episodes / communities; execute fulltext + vector search; maintain indices.
- Location: `graphiti_core/driver/` and its provider subpackages.
- Contains: `GraphDriver` ABC, `QueryExecutor` / `Transaction` ABCs, `GraphOperationsInterface`, `SearchInterface`, per-provider operation classes.
- Depends on: External driver SDKs (`neo4j`, `falkordb`, `kuzu`, `langchain-aws`/`opensearch-py`).
- Used by: Orchestration, namespaces, maintenance utils.
- Purpose: LLM prompt templates, Pydantic node/edge shapes, DB query fragments.
- Location: `graphiti_core/prompts/`, `graphiti_core/nodes.py`, `graphiti_core/edges.py`, `graphiti_core/models/`.
- Depends on: `pydantic`, `embedder` (for `generate_name_embedding`), `driver` (for `GraphProvider` enum).
- Used by: Orchestration, maintenance utils, search.

## Data Flow

### Primary: Episode Ingest (`add_episode`)

### Primary: Search (`search`)

### Secondary: Direct Triplet Write (`add_triplet`)

- All persistent state lives in the graph DB. The `Graphiti` instance is stateless between calls except for the connected driver and injected clients. Per-episode results are returned as Pydantic models, never cached on the instance.
- Bi-temporal fields on `EntityEdge` (`valid_at`, `invalid_at`, `created_at`) and `EpisodicNode` (`valid_at`, `created_at`) implement the bi-temporal model.

## Key Abstractions

- Purpose: Unify Neo4j / FalkorDB / Kuzu / Neptune behind one interface.
- Examples: `graphiti_core/driver/neo4j_driver.py:60`, `graphiti_core/driver/falkordb_driver.py`, `graphiti_core/driver/kuzu_driver.py`, `graphiti_core/driver/neptune_driver.py`.
- Pattern: ABC in `graphiti_core/driver/driver.py:90` with per-provider concrete classes. Each driver exposes its operations via properties (`entity_node_ops`, `search_ops`, `graph_ops`, ...).
- Purpose: Decouple CRUD logic from both the driver and the model, so each provider can swap query strings independently.
- Examples: `graphiti_core/driver/operations/entity_node_ops.py`, `graphiti_core/driver/neo4j/operations/entity_node_ops.py`, `graphiti_core/driver/falkordb/operations/entity_node_ops.py`.
- Pattern: Abstract base in `driver/operations/<entity>_ops.py`; concrete impl per provider in `driver/<provider>/operations/<entity>_ops.py`. Callers always go through `driver.{entity}_ops`.
- Purpose: Compose search behavior declaratively.
- Examples: `graphiti_core/search/search_config.py`, `graphiti_core/search/search_config_recipes.py`.
- Pattern: Pydantic `SearchConfig` holds nested `NodeSearchConfig`, `EdgeSearchConfig`, `EpisodeSearchConfig`, `CommunitySearchConfig`; each carries search method + reranker enums. Pre-built recipes (`COMBINED_HYBRID_SEARCH_CROSS_ENCODER`, `EDGE_HYBRID_SEARCH_RRF`, etc.) are the default entry points.
- Purpose: Swap providers without touching orchestration code.
- Examples: `graphiti_core/llm_client/client.py:75`, `graphiti_core/embedder/client.py:30`, `graphiti_core/cross_encoder/client.py`.
- Pattern: ABC + concrete implementations. `Graphiti.__init__` accepts any subclass via DI; falls back to OpenAI defaults.
- Purpose: Provide OO API like `graphiti.nodes.entity.save(node)`.
- Examples: `graphiti_core/namespaces/nodes.py`, `graphiti_core/namespaces/edges.py`.
- Pattern: Thin wrapper delegating to the driver's ops properties and the embedder.
- Purpose: Carry the five clients together.
- Examples: `graphiti_core/graphiti_types.py:26`.
- Purpose: Single source of truth for node/edge shape across transport, LLM, and persistence.
- Examples: `graphiti_core/nodes.py:EntityNode`, `graphiti_core/edges.py:EntityEdge`.

## Entry Points

- Location: `graphiti_core/__init__.py` exports `Graphiti`.
- Triggers: `from graphiti_core import Graphiti; graphiti = Graphiti(uri=..., user=..., password=...)`.
- Responsibilities: Construct driver, LLM, embedder, cross-encoder; wire tracer; expose `add_episode`, `add_episode_bulk`, `search`, `add_triplet`, `build_communities`, `summarize_saga`, `remove_episode`, `retrieve_episodes`, `close`, `build_indices_and_constraints`.
- Location: `mcp_server/main.py` → `mcp_server/src/graphiti_mcp_server.py:187` (`FastMCP('Graphiti Agent Memory', ...)`).
- Triggers: `uv run python main.py` (stdio/http/sse transport selected by config); also containerized via `mcp_server/docker/`.
- Responsibilities: Register tools (add_memory, search_nodes, search_memory_facts, add_triplet, get_entity_edge, get_episodes, get_episode_entities, update_entity, build_communities, summarize_saga, delete_episode, delete_entity_edge, clear_graph, get_status); own `GraphitiService` wrapper with semaphore and per-group_id `QueueService`.
- Location: `server/graph_service/main.py:20` (`app = FastAPI(lifespan=lifespan)`).
- Triggers: `uvicorn graph_service.main:app --reload` from `server/`.
- Responsibilities: Mount `routers/ingest.py` (`POST /messages`, `POST /add-entity`) and `routers/retrieve.py` (`POST /search`, `POST /get-memory`, `GET /entity-edge/{uuid}`, `GET /episodes/{group_id}`), expose `/healthcheck`. Uses `ZepGraphiti(Graphiti)` subclass per request.
- Location: `examples/quickstart/quickstart_neo4j.py`, `examples/quickstart/quickstart_falkordb.py`, `examples/quickstart/quickstart_neptune.py`, `examples/ecommerce/runner.py`, `examples/langgraph-agent/agent.ipynb`.
- Triggers: Direct script / notebook execution.
- Responsibilities: Demonstrate direct library usage; not deployable services.
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

### Provider-conditionals at call sites

### Module-level singleton config in MCP server

## Error Handling

- `NodeNotFoundError`, `EdgeNotFoundError`, `EdgesNotFoundError`, `GroupsEdgesNotFoundError`, `GroupsNodesNotFoundError` — all carry the UUID / group_id in `.message`.
- `EntityTypeValidationError`, `GroupIdValidationError`, `NodeLabelValidationError` — raised at trust boundaries (input validation in `graphiti_core/helpers.py:validate_group_id`, `validate_node_labels`, `graphiti_core/utils/ontology_utils/entity_types_utils.py`).
- `SearchRerankerError` — raised when cross-encoder reranking fails.
- LLM transient failures retried via `tenacity` (`@retry(stop=stop_after_attempt(4), wait=wait_random_exponential(...))` in `llm_client/client.py:120-130`); `RateLimitError` and 5xx server errors are retried.
- `Neo4jDriver._execute_index_query` (`driver/neo4j_driver.py:191-204`) swallows `EquivalentSchemaRuleAlreadyExists` races.
- `Graphiti._capture_initialization_telemetry` (`graphiti.py:250-269`) swallows telemetry errors silently.

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
