# Codebase Structure

**Analysis Date:** 2026-07-16

## Directory Layout

```
graphiti/                          # monorepo root (uv + hatchling, package graphiti-core)
├── graphiti_core/                 # core library (published as graphiti-core)
│   ├── __init__.py                # exports Graphiti
│   ├── graphiti.py                # facade class Graphiti (~1800 LOC)
│   ├── graphiti_types.py          # GraphitiClients aggregate
│   ├── nodes.py                   # Node / EntityNode / EpisodicNode / CommunityNode / SagaNode
│   ├── edges.py                   # Edge / EntityEdge / EpisodicEdge / CommunityEdge / ...
│   ├── helpers.py                 # semaphore_gather, group_id / label validation
│   ├── decorators.py              # multi-group-id fanout
│   ├── errors.py                  # GraphitiError hierarchy
│   ├── graph_queries.py           # index / constraint Cypher per provider
│   ├── tracer.py                  # OpenTelemetry Tracer / NoOpTracer
│   ├── driver/                    # GraphDriver ABC + 4 providers
│   │   ├── driver.py              # GraphDriver, GraphDriverSession, GraphProvider enum
│   │   ├── query_executor.py      # QueryExecutor / Transaction ABCs (breaks circular imports)
│   │   ├── neo4j_driver.py
│   │   ├── falkordb_driver.py
│   │   ├── kuzu_driver.py
│   │   ├── neptune_driver.py
│   │   ├── record_parsers.py      # record → model converters
│   │   ├── operations/            # shared ABCs for entity/episode/community/search ops
│   │   ├── neo4j/operations/      # Neo4j-concrete ops
│   │   ├── falkordb/operations/   # FalkorDB-concrete ops
│   │   ├── kuzu/operations/       # Kuzu-concrete ops
│   │   ├── neptune/operations/    # Neptune-concrete ops
│   │   ├── graph_operations/      # legacy GraphOperationsInterface
│   │   └── search_interface/      # legacy SearchInterface
│   ├── llm_client/                # LLMClient ABC + OpenAI/Anthropic/Gemini/Groq/Azure/GLiNER2
│   ├── embedder/                  # EmbedderClient ABC + OpenAI/Azure/Gemini/Voyage/Ollama
│   ├── cross_encoder/             # CrossEncoderClient + OpenAI/BGE/Gemini rerankers
│   ├── search/                    # hybrid search engine + configs + recipes
│   ├── prompts/                   # LLM prompts (extract, dedupe, summarize, eval)
│   ├── utils/                     # bulk, chunking, datetime, text helpers
│   │   ├── maintenance/           # extract / resolve / dedupe / community ops
│   │   └── ontology_utils/        # entity-type validation
│   ├── namespaces/                # graphiti.nodes.* / graphiti.edges.* OO API
│   ├── models/                    # Cypher query fragments for nodes/edges
│   │   ├── nodes/node_db_queries.py
│   │   └── edges/edge_db_queries.py
│   ├── migrations/                # schema migration hooks (placeholder)
│   └── telemetry/                 # Posthog event capture
├── server/                        # FastAPI REST service (separate uv project)
│   ├── graph_service/
│   │   ├── main.py                # FastAPI app entry
│   │   ├── config.py              # pydantic-settings Settings
│   │   ├── zep_graphiti.py        # ZepGraphiti(Graphiti) subclass + FastAPI DI
│   │   ├── routers/
│   │   │   ├── ingest.py          # POST /messages, /add-entity (async queue)
│   │   │   └── retrieve.py        # POST /search, /get-memory; GET /entity-edge, /episodes
│   │   └── dto/                   # request/response Pydantic models
│   └── tests/
├── mcp_server/                    # MCP server (separate uv project)
│   ├── main.py                    # entrypoint
│   ├── pyproject.toml
│   ├── sample_catalog.json        # sample entity catalog
│   ├── config/                    # YAML configs (neo4j / falkordb / docker)
│   ├── docker/                    # Dockerfiles + compose (neo4j, falkordb, standalone)
│   ├── k8s/                       # Kubernetes manifests
│   ├── docs/cursor_rules.md       # agent usage guidelines
│   ├── src/
│   │   ├── graphiti_mcp_server.py # FastMCP tools + GraphitiService
│   │   ├── config/schema.py       # GraphitiConfig (YAML + env)
│   │   ├── models/                # entity_types, edge_types, response_types
│   │   ├── services/
│   │   │   ├── factories.py       # LLMClientFactory / EmbedderFactory / DatabaseDriverFactory
│   │   │   └── queue_service.py   # per-group_id sequential episode queue
│   │   └── utils/                 # formatting, type_config, helpers
│   └── tests/                     # MCP integration / transport / load tests
├── tests/                         # core library tests (pytest)
│   ├── driver/
│   ├── llm_client/
│   ├── embedder/
│   ├── cross_encoder/
│   ├── utils/
│   └── evals/                     # end-to-end evaluation harness
├── examples/                      # demos (not shipped)
│   ├── quickstart/                # neo4j / falkordb / neptune scripts
│   ├── ecommerce/
│   ├── langgraph-agent/
│   ├── azure-openai/
│   ├── opentelemetry/
│   ├── gliner2/
│   ├── podcast/
│   └── wizard_of_oz/
├── .github/                       # CI workflows, issue templates, scripts
├── .planning/                     # GSD planning artifacts (this map lives here)
├── signatures/version1/           # CLA signatures
├── images/                        # README assets
├── pyproject.toml                 # graphiti-core package + tool config (ruff, pyright, hatch)
├── uv.lock
├── Makefile                       # format / lint / test / check
├── conftest.py                    # root pytest fixtures
├── pytest.ini
├── docker-compose.yml             # local Neo4j (+ optional services)
├── docker-compose.test.yml
├── Dockerfile
├── .env.example
├── CLAUDE.md / AGENTS.md          # agent guidance
└── README.md
```

## Directory Purposes

**`graphiti_core/`:**
- Purpose: Publishable Python library (`graphiti-core` on PyPI).
- Contains: Facade, models, drivers, clients, search, prompts, utils.
- Key files: `graphiti.py`, `nodes.py`, `edges.py`, `driver/driver.py`, `search/search.py`.

**`graphiti_core/driver/`:**
- Purpose: Graph DB abstraction. One ABC + four providers; each provider has its own `operations/` package.
- Contains: `GraphDriver` ABC, provider drivers, shared ops ABCs, per-provider ops, legacy interfaces.
- Key files: `driver.py`, `neo4j_driver.py`, `operations/entity_node_ops.py`, `neo4j/operations/entity_node_ops.py`.

**`graphiti_core/llm_client/`:**
- Purpose: LLM provider clients with structured-output + retry + cache.
- Contains: `client.py` (ABC), `openai_client.py`, `openai_generic_client.py`, `anthropic_client.py`, `gemini_client.py`, `groq_client.py`, `azure_openai_client.py`, `gliner2_client.py`, `config.py`, `cache.py`, `token_tracker.py`, `errors.py`.

**`graphiti_core/embedder/`:**
- Purpose: Embedding providers.
- Contains: `client.py` (ABC + `EMBEDDING_DIM`), `openai.py`, `azure_openai.py`, `gemini.py`, `voyage.py`, `ollama.py`.

**`graphiti_core/cross_encoder/`:**
- Purpose: Reranker providers for hybrid search.
- Contains: `client.py` (ABC), `openai_reranker_client.py`, `bge_reranker_client.py`, `gemini_reranker_client.py`.

**`graphiti_core/search/`:**
- Purpose: Hybrid search engine.
- Contains: `search.py` (orchestrator), `search_utils.py` (primitives), `search_config.py` (Pydantic configs), `search_config_recipes.py` (prebuilt configs), `search_filters.py`, `search_helpers.py`.

**`graphiti_core/prompts/`:**
- Purpose: Versioned LLM prompts for extract/dedupe/summarize.
- Contains: `lib.py` (prompt_library), `extract_nodes.py`, `extract_edges.py`, `extract_nodes_and_edges.py`, `dedupe_nodes.py`, `dedupe_edges.py`, `summarize_nodes.py`, `summarize_sagas.py`, `eval.py`, `models.py`, `prompt_helpers.py`, `snippets.py`.

**`graphiti_core/utils/`:**
- Purpose: Cross-cutting helpers and the maintenance pipeline.
- Contains: `bulk_utils.py`, `content_chunking.py`, `datetime_utils.py`, `text_utils.py`, `maintenance/` (node/edge/community/graph_data ops, dedup helpers, attribute utils, combined extraction), `ontology_utils/entity_types_utils.py`.

**`graphiti_core/namespaces/`:**
- Purpose: OO API surface (`graphiti.nodes.entity.save(...)`).
- Contains: `nodes.py` (`NodeNamespace`, `EntityNodeNamespace`, ...), `edges.py`.

**`graphiti_core/models/`:**
- Purpose: Cypher query fragment builders (save/return) shared across providers.
- Contains: `nodes/node_db_queries.py`, `edges/edge_db_queries.py`.

**`server/`:**
- Purpose: Standalone FastAPI REST service wrapping `graphiti_core`.
- Contains: `graph_service/main.py`, routers, DTOs, `ZepGraphiti` subclass, its own pyproject/tests.
- Key files: `graph_service/main.py`, `graph_service/zep_graphiti.py`, `graph_service/routers/ingest.py`, `graph_service/routers/retrieve.py`.

**`mcp_server/`:**
- Purpose: Model Context Protocol server exposing Graphiti as agent tools.
- Contains: FastMCP server, YAML config system, factories, queue service, Docker/K8s packaging, its own test suite.
- Key files: `src/graphiti_mcp_server.py`, `src/services/factories.py`, `src/services/queue_service.py`, `src/config/schema.py`, `src/models/entity_types.py`.

**`tests/`:**
- Purpose: Core library unit + integration tests.
- Contains: Per-subsystem packages mirroring `graphiti_core/`; `evals/` for end-to-end evaluation.
- Naming: unit tests are `test_*.py`; integration tests end with `_int.py` (e.g. `test_graphiti_int.py`).

**`examples/`:**
- Purpose: Runnable demos and notebooks. Not installed as a package.
- Contains: `quickstart/`, `ecommerce/`, `langgraph-agent/`, `azure-openai/`, `opentelemetry/`, `gliner2/`, `podcast/`, `wizard_of_oz/`, `data/`.

**`.planning/`:**
- Purpose: GSD planning artifacts (codebase maps, phase plans). Not runtime code.
- Contains: `codebase/` (this document and siblings).

## Key File Locations

**Entry Points:**
- `graphiti_core/__init__.py`: library public export (`from graphiti_core import Graphiti`)
- `graphiti_core/graphiti.py`: `class Graphiti` facade
- `server/graph_service/main.py`: FastAPI app
- `mcp_server/main.py` → `mcp_server/src/graphiti_mcp_server.py`: MCP server
- `examples/quickstart/quickstart_neo4j.py`: quickstart script

**Configuration:**
- `pyproject.toml`: package metadata, optional extras, ruff, pyright
- `Makefile`: `format`, `lint`, `test`, `check`
- `.env.example`: sample env vars (never commit real secrets)
- `mcp_server/config/config.yaml` (+ docker/provider variants)
- `mcp_server/src/config/schema.py`: config pydantic models
- `server/graph_service/config.py`: REST server settings
- `docker-compose.yml`, `docker-compose.test.yml`
- `mcp_server/docker/docker-compose-neo4j.yml`, `docker-compose-falkordb.yml`
- `mcp_server/k8s/graphiti-neo4j.yaml`

**Core Logic:**
- `graphiti_core/graphiti.py`: orchestration
- `graphiti_core/nodes.py`, `graphiti_core/edges.py`: domain models
- `graphiti_core/driver/driver.py`: driver ABC
- `graphiti_core/driver/operations/`: ops ABCs
- `graphiti_core/driver/{neo4j,falkordb,kuzu,neptune}/operations/`: provider ops
- `graphiti_core/search/search.py`, `search_utils.py`: hybrid search
- `graphiti_core/utils/maintenance/`: extract/resolve/dedupe/community pipeline
- `graphiti_core/utils/bulk_utils.py`: bulk ingest
- `graphiti_core/prompts/`: LLM prompts

**Testing:**
- `conftest.py`: root fixtures
- `tests/`: core library tests
- `server/tests/`: REST server integration
- `mcp_server/tests/`: MCP server unit + integration + stress
- `tests/evals/`: evaluation harness (`eval_e2e_graph_building.py`, `eval_cli.py`)

## Naming Conventions

**Files:**
- Modules: `snake_case.py` (e.g. `neo4j_driver.py`, `entity_node_ops.py`)
- Tests: `test_<module>.py` for unit; `test_<module>_int.py` for integration
- Config: `config-docker-<provider>.yaml`, `docker-compose-<provider>.yml`
- Ops classes: one file per entity-type × provider (`entity_node_ops.py`, `episode_node_ops.py`, `community_edge_ops.py`, `search_ops.py`, `graph_ops.py`, ...)

**Directories:**
- Packages: `snake_case/` matching module names
- Provider-specific ops live under `driver/<provider>/operations/`
- Shared ops ABCs live under `driver/operations/`
- Transport layers (`server/`, `mcp_server/`) are top-level sibling packages, not under `graphiti_core/`

**Classes:**
- ABC suffixes: none fixed; ABCs are named by role (`GraphDriver`, `LLMClient`, `EmbedderClient`, `EntityNodeOperations`)
- Provider impls: `<Provider><Role>` (e.g. `Neo4jEntityNodeOperations`, `FalkorDriver`, `OpenAIClient`, `OpenAIEmbedder`)
- Result models: `AddEpisodeResults`, `AddBulkEpisodeResults`, `AddTripletResults`, `SearchResults`
- Errors: `<Thing>NotFoundError`, `<Thing>ValidationError` under `GraphitiError`

**Functions / methods:**
- Async everywhere for I/O: `async def add_episode(...)`, `async def search(...)`
- Save/load pair naming on models and ops: `save`, `save_bulk`, `get_by_uuid`, `get_by_uuids`, `get_by_group_ids`, `delete`, `delete_by_uuids`, `delete_by_group_id`
- Factory static methods: `LLMClientFactory.create(config)`, `EmbedderFactory.create(config)`, `DatabaseDriverFactory.create_config(config)`

## Where to Add New Code

**New episode-ingest feature (core behavior change):**
- Primary code: extend `graphiti_core/utils/maintenance/` (e.g. new `*_operations.py`), then wire a thin method on `Graphiti` in `graphiti_core/graphiti.py`
- Prompts: add a module under `graphiti_core/prompts/` and register it in `prompts/lib.py`
- Tests: `tests/test_<feature>.py` (unit) and/or `tests/test_<feature>_int.py` (integration)

**New graph DB provider:**
- Driver: `graphiti_core/driver/<provider>_driver.py` implementing `GraphDriver`
- Ops: `graphiti_core/driver/<provider>/operations/` implementing every ABC in `driver/operations/`
- Register provider enum value in `graphiti_core/driver/driver.py:GraphProvider`
- Cypher fragments: extend `graphiti_core/models/nodes/node_db_queries.py` and `models/edges/edge_db_queries.py` and `graphiti_core/graph_queries.py`
- Optional dep: add extra in `pyproject.toml`
- Tests: `tests/driver/test_<provider>_driver.py`

**New LLM / Embedder / Cross-encoder provider:**
- Implement ABC under the matching package (`llm_client/`, `embedder/`, `cross_encoder/`)
- Export from package `__init__.py`
- Optional dep: add extra in `pyproject.toml`
- MCP factory: add a branch in `mcp_server/src/services/factories.py` and a config model in `mcp_server/src/config/schema.py`
- Tests: `tests/<package>/test_<provider>.py`

**New REST endpoint:**
- Router: `server/graph_service/routers/<domain>.py` (or extend `ingest.py` / `retrieve.py`)
- DTO: `server/graph_service/dto/`
- Wire in `server/graph_service/main.py` via `app.include_router(...)`
- Prefer calling through `ZepGraphiti` (`server/graph_service/zep_graphiti.py`) rather than re-implementing

**New MCP tool:**
- Tool function: add `@mcp.tool()` in `mcp_server/src/graphiti_mcp_server.py` (or extract a service module under `mcp_server/src/services/` if large)
- Response type: `mcp_server/src/models/response_types.py`
- Entity/edge type: `mcp_server/src/models/entity_types.py` / `edge_types.py`
- Config knob: `mcp_server/src/config/schema.py` + YAML under `mcp_server/config/`
- Tests: `mcp_server/tests/test_<feature>.py`

**New utility / helper:**
- Shared pure helpers: `graphiti_core/helpers.py` or a new file under `graphiti_core/utils/`
- Domain maintenance logic: `graphiti_core/utils/maintenance/`
- Date/time: `graphiti_core/utils/datetime_utils.py`
- Text: `graphiti_core/utils/text_utils.py`

**New search strategy / recipe:**
- Primitive: `graphiti_core/search/search_utils.py`
- Config enum + fields: `graphiti_core/search/search_config.py`
- Prebuilt recipe: `graphiti_core/search/search_config_recipes.py`
- Wire into `graphiti_core/search/search.py`

## Special Directories

**`mcp_server/docker/`:**
- Purpose: Container build + compose files for Neo4j, FalkorDB, and standalone images.
- Generated: No (source Dockerfiles).
- Committed: Yes.

**`mcp_server/k8s/`:**
- Purpose: Kubernetes deployment manifests (`graphiti-neo4j.yaml`).
- Generated: No.
- Committed: Yes.

**`.planning/`:**
- Purpose: GSD planning docs (architecture maps, phase plans). Consumed by `/gsd-plan-phase` and `/gsd-execute-phase`.
- Generated: Written by GSD mappers/planners.
- Committed: Yes (repo-relative under primary tree).

**`signatures/`:**
- Purpose: CLA signature archive.
- Generated: No.
- Committed: Yes.

**`images/`:**
- Purpose: README / docs assets.
- Generated: No.
- Committed: Yes.

**`.ruff_cache/`, `__pycache__/`, `.venv/`:**
- Purpose: Tool / runtime caches.
- Generated: Yes.
- Committed: No (gitignored).

**`.claude/worktrees/`:**
- Purpose: Agent-isolated worktrees for concurrent sessions.
- Generated: Yes (by Claude Code harness).
- Committed: No.

---

*Structure analysis: 2026-07-16*
