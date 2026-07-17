# External Integrations

**Analysis Date:** 2026-07-16

## APIs & External Services

**LLM Providers (pluggable via `mcp_server/src/services/factories.py`):**
- OpenAI - default chat + embeddings
  - SDK: `openai` (AsyncOpenAI), `graphiti_core/llm_client/openai_client.py` (Responses API) and `graphiti_core/llm_client/openai_generic_client.py` (Chat Completions for Ollama/vLLM/LM Studio).
  - Auth env: `OPENAI_API_KEY`, optional `OPENAI_API_URL`, `OPENAI_ORGANIZATION_ID`.
  - Default model: `gpt-5.5` (`mcp_server/src/config/schema.py:160`).
- Azure OpenAI - `graphiti_core/llm_client/azure_openai_client.py`, `graphiti_core/embedder/azure_openai.py`
  - Auth env: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION` (default `2024-10-21`), `AZURE_OPENAI_DEPLOYMENT`, `USE_AZURE_AD` (AD flow stubbed, not yet implemented per `factories.py:194`).
  - Requires base URL normalized to `/openai/v1/` suffix (`factories.py:204-208`).
- Anthropic - `graphiti_core/llm_client/anthropic_client.py`
  - Auth env: `ANTHROPIC_API_KEY`, optional `ANTHROPIC_API_URL` (default `https://api.anthropic.com`), `max_retries=3`.
- Google Gemini - `graphiti_core/llm_client/gemini_client.py`, `graphiti_core/embedder/gemini.py`
  - Auth env: `GOOGLE_API_KEY`, optional `GOOGLE_PROJECT_ID`, `GOOGLE_LOCATION` (default `us-central1`).
- Groq - `graphiti_core/llm_client/groq_client.py`
  - Auth env: `GROQ_API_KEY`, optional `GROQ_API_URL` (default `https://api.groq.com/openai/v1`).
- OpenAI-compatible (Ollama, vLLM, LM Studio) - auto-detected when `api_url` is not an official OpenAI domain (`factories.py:100-114`); routed to `OpenAIGenericClient`.

**Embedding Providers (pluggable via `EmbedderFactory`, `mcp_server/src/services/factories.py:303-433`):**
- OpenAI - `graphiti_core/embedder/openai.py`. Default model `text-embedding-3-small`, dim 1536.
- Azure OpenAI - `graphiti_core/embedder/azure_openai.py`. Same env vars as LLM branch, plus `AZURE_OPENAI_EMBEDDINGS_ENDPOINT`, `AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT`.
- Gemini - `graphiti_core/embedder/gemini.py`. Default model `models/text-embedding-004`, dim 768.
- Voyage AI - `graphiti_core/embedder/voyage.py`. Auth env `VOYAGE_API_KEY`, default model `voyage-3`, dim 1024.
- Ollama (native) - `graphiti_core/embedder/ollama.py`. Config: `OLLAMA_EMBEDDER_API_URL` (default `http://localhost:11434`), `OLLAMA_API_KEY`, `OLLAMA_EMBEDDER_TRUNCATE`, `OLLAMA_EMBEDDER_KEEP_ALIVE`, `OLLAMA_EMBEDDER_TIMEOUT`. Default model `embeddinggemma`, dim 768 (`schema.py:335-342`).

**Cross-Encoder / Reranker Clients (`graphiti_core/cross_encoder/`):**
- OpenAI reranker - `openai_reranker_client.py`
- BGE reranker - `bge_reranker_client.py`
- Gemini reranker - `gemini_reranker_client.py`

**Entity Recognition:**
- GLiNER2 - `graphiti_core/llm_client/gliner2_client.py`. Optional `[gliner2]` extra, Python 3.11+ only.

**Telemetry:**
- PostHog - anonymous usage events. Host `https://us.posthog.com`, public project API key hardcoded in `graphiti_core/telemetry/telemetry.py:18-19`. Disabled under `pytest` or when `GRAPHITI_TELEMETRY_ENABLED=false`. Anonymous ID cached at `~/.cache/graphiti/telemetry_anon_id`.

## Data Storage

**Graph Databases (provider enum in `graphiti_core/driver/driver.py:59-64`):**
- Neo4j (default server backend, `GraphProvider.NEO4J`) - `graphiti_core/driver/neo4j_driver.py`
  - Connection: `NEO4J_URI` (bolt://), `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (default `neo4j`), `USE_PARALLEL_RUNTIME` (Enterprise only).
  - Client: official `neo4j` Python driver. Min version 5.26.
- FalkorDB (default mcp_server backend, `GraphProvider.FALKORDB`) - `graphiti_core/driver/falkordb_driver.py`
  - Connection: `FALKORDB_URI` (default `redis://localhost:6379`), `FALKORDB_PASSWORD`, `FALKORDB_DATABASE` (default `default_db`).
  - Client: `falkordb` package. Host/port parsed from URI in `factories.py:497-499`.
  - Optional embedded test server via `falkordblite` (Python 3.12+).
- Kuzu (`GraphProvider.KUZU`) - `graphiti_core/driver/kuzu_driver.py`. In-process (no server). Upstream deprecated per `pyproject.toml:32-33`.
- AWS Neptune (`GraphProvider.NEPTUNE`) - `graphiti_core/driver/neptune_driver.py`
  - Client: `langchain_aws.graphs.NeptuneAnalyticsGraph` / `NeptuneGraph`.
  - Auth: AWS V4 signer via `boto3` (`neptune_driver.py:23-25`).
  - Requires OpenSearch (AOSS) indices for full-text search; index definitions hardcoded in `neptune_driver.py:62-80`.

**File Storage:**
- Local filesystem only (Docker volumes: `neo4j_data`, `falkordb_data`, `neo4j_logs` in compose files).
- K8s PVCs `neo4j-data` (10Gi) and `neo4j-logs` (1Gi) on storageClass `nfs01` (`mcp_server/k8s/graphiti-neo4j.yaml:280-299`).
- Telemetry cache at `~/.cache/graphiti/telemetry_anon_id` (`telemetry.py:25-26`).

**Caching:**
- LLM response cache: in-memory LRU via `graphiti_core/llm_client/cache.py`.
- FastAPI settings cached via `functools.lru_cache` (`server/graph_service/config.py:25-27`).
- No distributed cache (no Redis/Memcached as app-level cache; FalkorDB itself runs on Redis).

## Authentication & Identity

**Auth Provider:**
- Custom / API-key based. No OAuth, OIDC, or session auth in the codebase.
- LLM provider keys validated non-empty at factory creation (`factories.py:76-97`).
- Azure AD support stubbed: `use_azure_ad` flag parsed in config (`schema.py:102, 174`) but factories still require API key and TODO at `factories.py:194` marks AD flow unimplemented.
- AWS Neptune uses IAM V4 signing via `boto3` credentials chain (`neptune_driver.py:25`).

**MCP Transport Security:**
- DNS rebinding protection enabled via `TransportSecuritySettings(enable_dns_rebinding_protection=True)` (`graphiti_mcp_server.py:192-195`).
- Allowed hosts configurable via `FASTMCP_HTTP_ALLOWED_HOSTS` env (JSON list). Default: localhost, 127.0.0.1, ::1 (`graphiti_mcp_server.py:180-185`). K8s manifest adds the NodePort listener (`mcp_server/k8s/graphiti-neo4j.yaml:431-432`).

**Application-level Auth:**
- None. The K8s NodePort comment at `mcp_server/k8s/graphiti-neo4j.yaml:1-3` explicitly warns: NodePort provides no TLS or app authentication; must be gated by firewall/VPN or replaced with authenticated TLS ingress.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Datadog/Rollbar detected).

**Logs:**
- Python `logging` to stderr. Format `'%(asctime)s - %(name)s - %(levelname)s - %(message)s'` configured in `mcp_server/src/graphiti_mcp_server.py:100-108`.
- Uvicorn access logs demoted to WARNING (`graphiti_mcp_server.py:112`).
- MCP streamable_http_manager logs demoted to WARNING (`graphiti_mcp_server.py:113-115`).
- LLM token usage tracked via `graphiti_core/llm_client/token_tracker.py`.

**Distributed Tracing:**
- Optional OpenTelemetry via `[tracing]` extra. Tracer passed to `Graphiti(tracer=...)`. See `OTEL_TRACING.md` and `graphiti_core/tracer.py`. No-op fallback when no tracer configured.

**Health Checks:**
- FastAPI: `GET /healthcheck` returns `{'status': 'healthy'}` (`server/graph_service/main.py:27-29`).
- MCP: `GET /health` referenced by Docker `HEALTHCHECK` (`mcp_server/docker/Dockerfile.standalone:64-65`).
- Docker Compose healthchecks ping Neo4j HTTP port 7474 (`docker-compose.yml:32-41`).

## CI/CD & Deployment

**Hosting:**
- GitHub Container Registry (GHCR): `ghcr.io/thienpvt/graphiti-mcp` for standalone MCP image.
- Docker Hub: `zepai/knowledge-graph-mcp:standalone` referenced in `mcp_server/docker/docker-compose-neo4j.yml:26`.
- Kubernetes: in-cluster deployment via `mcp_server/k8s/graphiti-neo4j.yaml`.

**CI Pipeline (`.github/workflows/`):**
- `lint.yml` - Ruff lint.
- `typecheck.yml` - Pyright type checking.
- `unit_tests.yml` - Pytest unit tests.
- `server-tests.yml` - Server integration tests.
- `mcp-server-tests.yml` - MCP server tests.
- `codeql.yml` - GitHub CodeQL security scan.
- `claude-code-review.yml`, `claude-code-review-manual.yml`, `claude.yml` - Claude-based review.
- `cla.yml`, `pr-triage.yml` - Contribution hygiene.
- `publish-mcp-image.yml` - Builds and pushes standalone MCP image on `main` pushes; verifies graphiti-core source on PRs via Docker run introspection (`.github/workflows/publish-mcp-image.yml:74-100`).
- `release-graphiti-core.yml` - PyPI release of `graphiti-core`.
- `release-mcp-server.yml` - MCP server release.
- `release-server-container.yml` - Server container release.
- `ai-moderator.yml` - Automated moderation.
- Pinned action SHAs used throughout (e.g. `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5`).

**CD Pipeline:**
- `publish-mcp-image.yml` triggers on pushes to `main` touching `graphiti_core/**`, `mcp_server/**`, `pyproject.toml`. Publishes tags: `sha-<long>`, `standalone`, `<mcp-version>-standalone`.
- Platforms: `linux/amd64` only (`publish-mcp-image.yml:63, 132`).

## Environment Configuration

**Required env vars:**
- `OPENAI_API_KEY` (or other LLM provider key).
- Database: `NEO4J_USER` + `NEO4J_PASSWORD` (Neo4j), or `FALKORDB_PASSWORD` (FalkorDB). Neptune uses AWS credential chain.

**Optional env vars (with defaults):**
- `SEMAPHORE_LIMIT` (10) - Concurrent episode processing cap (`graphiti_mcp_server.py:96`).
- `MAX_REFLEXION_ITERATIONS` - LLM reflection loop bound.
- `MODEL_NAME`, `MAX_TOKENS`, `EMBEDDER_MODEL`, `EMBEDDER_DIMENSIONS` - model overrides.
- `GRAPHITI_GROUP_ID`, `EPISODE_ID_PREFIX`, `USER_ID` - Graphiti app config.
- `USE_PARALLEL_RUNTIME` - Neo4j Enterprise parallel runtime.
- `CONFIG_PATH` - MCP YAML config location (default `config/config.yaml`).
- `FASTMCP_HTTP_ALLOWED_HOSTS` - JSON list of allowed MCP HTTP hosts.
- `GRAPHITI_TELEMETRY_ENABLED` - PostHog telemetry toggle (default `true`).
- `EMBEDDING_DIM` (1024) - Default embedding dimension in `graphiti_core/embedder/client.py:23`.
- `ENTITY_INDEX_NAME` / `EPISODE_INDEX_NAME` / `COMMUNITY_INDEX_NAME` / `ENTITY_EDGE_INDEX_NAME` - Full-text index names (`graphiti_core/driver/driver.py:53-56`).
- `OLLAMA_EMBEDDER_*` - Ollama embedder tuning.

**Secrets location:**
- Local: `.env` (gitignored). Example at `.env.example`.
- K8s: `graphiti-secrets` Secret in `graphiti` namespace, keys `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENAI_API_KEY`, `OPENAI_EMBEDDER_API_KEY`, `OLLAMA_API_KEY` (`mcp_server/k8s/graphiti-neo4j.yaml:332-465`).
- GitHub Actions: `GITHUB_TOKEN` for GHCR auth (`.github/workflows/publish-mcp-image.yml:107-108`).

## Webhooks & Callbacks

**Incoming:**
- FastAPI HTTP endpoints in `server/graph_service/routers/{ingest,retrieve}.py` (REST ingestion + retrieval, not webhooks in the third-party sense).
- MCP tools exposed via HTTP transport at port 8000 (`mcp_server/src/graphiti_mcp_server.py:187-196`). Tools: `add_memory`, `add_triplet`, `search_nodes`, `search_memory_facts`, `summarize_saga`, `build_communities`, `get_episode_entities`, `get_entity_edge`, `get_episodes`, `update_entity`, `delete_episode`, `delete_entity_edge`, `clear_graph` (documented in `GRAPHITI_MCP_INSTRUCTIONS` at `graphiti_mcp_server.py:137-177`).

**Outgoing:**
- None (no outbound webhook delivery; all outbound traffic is LLM/embedding/DB client calls).

---

*Integration audit: 2026-07-16*
