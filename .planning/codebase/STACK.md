# Technology Stack

**Analysis Date:** 2026-07-16

## Languages

**Primary:**
- Python `>=3.10,<4` - All application code across `graphiti_core/`, `server/`, `mcp_server/`. Pinned to 3.10 minimum by `pyproject.toml`; Docker images use 3.11-slim-bookworm (`mcp_server/docker/Dockerfile.standalone:6`) or 3.12-slim (`Dockerfile:2`).

**Secondary:**
- YAML - Configuration (`mcp_server/config/*.yaml`), Docker Compose, Kubernetes manifests (`mcp_server/k8s/`).
- Bash - Container entrypoint script (`mcp_server/docker/Dockerfile:72`) and Make targets (`Makefile`).
- Cypher - Graph query language embedded throughout `graphiti_core/driver/` and `graphiti_core/graph_queries.py`.

## Runtime

**Environment:**
- CPython 3.10 minimum. Runtime images use Python 3.11 (standalone MCP) or 3.12 (server).
- Async-first: built on `asyncio` (drivers, LLM/embedder clients, FastAPI, MCP server all `async`).

**Package Manager:**
- `uv` (Astral) - single source of truth. Pinned to `0.8.15` in standalone build (`mcp_server/docker/Dockerfile.standalone:5`).
- Lockfiles present: `uv.lock` (root, ~997KB), `server/uv.lock`, `mcp_server/uv.lock`.
- Installed via official installer script in Dockerfiles (`Dockerfile:26-27`, `mcp_server/docker/Dockerfile:19-20`).

## Frameworks

**Core:**
- Pydantic `>=2.11.5` - Data models, config schemas, validation. Foundational to `nodes.py`, `edges.py`, `graphiti_core/models/`, `mcp_server/src/config/schema.py`, `mcp_server/src/models/`.
- `python-dotenv` `>=1.0.1` - `.env` loading in `graphiti_core/driver/driver.py:51`, `mcp_server/src/graphiti_mcp_server.py:17-66`.

**API / Server:**
- FastAPI `>=0.115.0` - REST API in `server/graph_service/main.py`, routers in `server/graph_service/routers/`.
- Uvicorn `>=0.44.0` - ASGI server. Launch command in `Dockerfile:78`.
- `pydantic-settings` `>=2.4.0` - Typed settings in `server/graph_service/config.py`, `mcp_server/src/config/schema.py:9-13`.

**MCP:**
- `mcp` `>=1.27.2,<2` - Model Context Protocol SDK (`mcp.server.fastmcp.FastMCP`) instantiated in `mcp_server/src/graphiti_mcp_server.py:187`. Uses `TransportSecuritySettings` for DNS rebinding protection (`:192-195`).

**Testing:**
- pytest `>=8.3.3` - Runner. Config in `pytest.ini`, `pyproject.toml:[tool.pytest.ini_options]`.
- `pytest-asyncio` `>=0.24.0` - `asyncio_mode = auto` (`pytest.ini:5`).
- `pytest-xdist` `>=3.6.1` - Parallel test execution.
- `pytest-timeout` (mcp_server dev group) - Per-test timeouts.

**Build/Dev:**
- Ruff `>=0.7.1` - Format + lint. Line length 100, single quotes, isort. Config in `pyproject.toml:[tool.ruff]`.
- Pyright `>=1.1.404` - Type checking. `typeCheckingMode = "basic"` for `graphiti_core`/`mcp_server`, `"standard"` for `server/` (`server/pyproject.toml:74`).
- Hatchling - Build backend (`pyproject.toml:[build-system]`).

## Key Dependencies

**Critical (graph storage):**
- `neo4j` `>=5.26.0` - Official Python driver, used by `graphiti_core/driver/neo4j_driver.py`. Requires Neo4j 5.26+.
- `falkordb` `>=1.1.2,<2.0.0` - FalkorDB client, used by `graphiti_core/driver/falkordb_driver.py`. Optional extra `[falkordb]`.
- `falkordblite` `>=0.5.0` - Embedded test backend (Python 3.12+ only). Pinned `redis<9` for compat (`pyproject.toml:36`).
- `kuzu` `>=0.11.3` - Kuzu embedded graph DB. Marked deprecated in `pyproject.toml:32-33`. Used by `graphiti_core/driver/kuzu_driver.py`.

**Critical (LLM providers):**
- `openai` `>=1.91.0` (root), `>=2.41.0` (mcp_server) - OpenAI client. Both Responses API (`graphiti_core/llm_client/openai_client.py`) and Chat Completions (`openai_generic_client.py`).
- `anthropic` `>=0.49.0` (optional `[anthropic]` extra) - `graphiti_core/llm_client/anthropic_client.py`.
- `google-genai` `>=1.62.0` (optional `[google-genai]` extra) - `graphiti_core/llm_client/gemini_client.py`.
- `groq` `>=0.2.0` (optional `[groq]` extra) - `graphiti_core/llm_client/groq_client.py`.
- `voyageai` `>=0.2.3` - Embeddings via `graphiti_core/embedder/voyage.py`.

**Critical (AWS / Neptune):**
- `boto3` `>=1.39.16` - AWS SDK for Neptune Auth.
- `langchain-aws` `>=0.2.29` - `NeptuneAnalyticsGraph` / `NeptuneGraph` wrappers (`graphiti_core/driver/neptune_driver.py:23-25`).
- `opensearch-py` `>=3.0.0` - OpenSearch/AOSS for Neptune full-text search (`graphiti_core/driver/neptune_driver.py:25`).

**Infrastructure:**
- `httpx` `>=0.28.1` - Async HTTP client used by LLM/embedder integrations.
- `tenacity` `>=9.0.0` - Retry logic in LLM clients.
- `numpy` `>=1.0.0` - Numerical ops on embeddings.
- `posthog` `>=3.0.0` - Anonymous telemetry in `graphiti_core/telemetry/telemetry.py`.
- `pyyaml` `>=6.0.3` - YAML config parsing in MCP server.

**Observability:**
- `opentelemetry-api` + `opentelemetry-sdk` `>=1.20.0` (optional `[tracing]` extra) - Distributed tracing. See `OTEL_TRACING.md` and `graphiti_core/tracer.py`.

**Embedders / Rerankers:**
- `sentence-transformers` `>=3.2.1` - Local embeddings.
- `gliner2` `>=1.2.0` (Python 3.11+) - NER-based entity extraction via `graphiti_core/llm_client/gliner2_client.py`.

## Configuration

**Environment:**
- `.env` files loaded by `python-dotenv` at multiple entry points.
- `.env.example` at repo root lists: `OPENAI_API_KEY`, `NEO4J_URI/PORT/USER/PASSWORD`, `FALKORDB_URI/PORT/USER/PASSWORD`, `USE_PARALLEL_RUNTIME`, `SEMAPHORE_LIMIT`, `GITHUB_SHA`, `MAX_REFLEXION_ITERATIONS`, `ANTHROPIC_API_KEY`.
- MCP server supports YAML config with `${VAR}` / `${VAR:default}` expansion (`mcp_server/src/config/schema.py:23-58`). Config path set via `CONFIG_PATH` env (default `config/config.yaml`).
- pydantic-settings priority order (mcp_server): CLI args > env vars > YAML > defaults (`mcp_server/src/config/schema.py:307`).

**Key configs required:**
- `OPENAI_API_KEY` (or equivalent provider key) - mandatory for LLM + embeddings.
- Database credentials - one of Neo4j (`NEO4J_*`), FalkorDB (`FALKORDB_*`), or Neptune/AOSS.

**Build:**
- `pyproject.toml` - root library (`graphiti-core`).
- `server/pyproject.toml` - FastAPI service (`graph-service`).
- `mcp_server/pyproject.toml` - MCP server (`mcp-server`).
- `Dockerfile` - root server image (Python 3.12, uv, non-root user).
- `mcp_server/docker/Dockerfile` - combined FalkorDB+MCP image (Python 3.11 on FalkorDB base).
- `mcp_server/docker/Dockerfile.standalone` - standalone MCP image connecting to external DB.
- `docker-compose.yml`, `docker-compose.test.yml`, `mcp_server/docker/docker-compose-{neo4j,falkordb}.yml`.
- `mcp_server/k8s/graphiti-neo4j.yaml` - Kubernetes manifest (Neo4j + MCP Deployment, NodePort 30080).

**Code style config:**
- Ruff: `line-length = 100`, single quotes, isort. Rules: E, F, UP, B, SIM, I (`pyproject.toml:76-94`).
- `typing.TypedDict` banned in favor of `typing_extensions.TypedDict` (`pyproject.toml:96-98`).

## Platform Requirements

**Development:**
- Python 3.10+ (3.11+ for `gliner2`, 3.12+ for `falkordblite`).
- `uv` for env management (`make install` runs `uv sync --extra dev`).
- Neo4j 5.26+ or FalkorDB 1.1.2+ for integration tests.
- `Makefile` targets: `make format`, `make lint`, `make test`, `make check`.
- Unit tests run with `DISABLE_FALKORDB=1 DISABLE_KUZU=1 DISABLE_NEPTUNE=1 pytest -m "not integration"` (`Makefile:29`).

**Production:**
- Docker images published to GHCR: `ghcr.io/thienpvt/graphiti-mcp` (standalone MCP, see `.github/workflows/publish-mcp-image.yml:23`).
- Root server image built from `Dockerfile` (published via `.github/workflows/release-server-container.yml`).
- MCP combined image hosts FalkorDB + MCP in a single container (`mcp_server/docker/Dockerfile`).
- K8s deployment targets an in-cluster Neo4j and exposes MCP via NodePort 30080 (`mcp_server/k8s/graphiti-neo4j.yaml`).
- Python runtime set to `PYTHONUNBUFFERED=1` in all Docker images.

---

*Stack analysis: 2026-07-16*
