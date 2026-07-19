# Graphiti MCP Server

Graphiti is a framework for building and querying temporally-aware knowledge graphs, specifically tailored for AI agents
operating in dynamic environments. Unlike traditional retrieval-augmented generation (RAG) methods, Graphiti
continuously integrates user interactions, structured and unstructured enterprise data, and external information into a
coherent, queryable graph. The framework supports incremental data updates, efficient retrieval, and precise historical
queries without requiring complete graph recomputation, making it suitable for developing interactive, context-aware AI
applications.

This is an experimental Model Context Protocol (MCP) server implementation for Graphiti. The MCP server exposes
Graphiti's key functionality through the MCP protocol, allowing AI assistants to interact with Graphiti's knowledge
graph capabilities.

## Features

The Graphiti MCP server provides comprehensive knowledge graph capabilities:

- **Episode Management**: Add, retrieve, and delete episodes (text, messages, or JSON data)
- **Entity Management**: Search and manage entity nodes and relationships in the knowledge graph
- **Search Capabilities**: Search for facts (edges) and node summaries using semantic and hybrid search
- **Group Management**: Organize and manage groups of related data with group_id filtering
- **Graph Maintenance**: Clear the graph and rebuild indices
- **Graph Database Support**: Multiple backend options including FalkorDB (default) and Neo4j
- **Multiple LLM Providers**: Support for OpenAI, Anthropic, Gemini, Groq, and Azure OpenAI
- **Multiple Embedding Providers**: Support for OpenAI, Voyage, Sentence Transformers, and Gemini embeddings
- **Rich Entity Types**: Built-in entity types including Preferences, Requirements, Procedures, Locations, Events, Organizations, Documents, and more for structured knowledge extraction
- **HTTP Transport**: Default HTTP transport with MCP endpoint at `/mcp` for broad client compatibility
- **Queue-based Processing**: Asynchronous episode processing with configurable concurrency limits

## Quick Start

### Clone the Graphiti GitHub repo

```bash
git clone https://github.com/getzep/graphiti.git
```

or

```bash
gh repo clone getzep/graphiti
```

### For Claude Desktop and other `stdio` only clients

1. Note the full path to this directory.

```
cd graphiti && pwd
```

2. Install the [Graphiti prerequisites](#prerequisites).

3. Configure Claude, Cursor, or other MCP client to use [Graphiti with a `stdio` transport](#integrating-with-mcp-clients). See the client documentation on where to find their MCP configuration files.

### For Cursor and other HTTP-enabled clients

1. Change directory to the `mcp_server` directory

`cd graphiti/mcp_server`

2. Start the combined FalkorDB + MCP server using Docker Compose (recommended)

```bash
docker compose up
```

This starts both FalkorDB and the MCP server in a single container.

**Alternative**: Run with separate containers using Neo4j:
```bash
docker compose -f docker/docker-compose-neo4j.yml up
```

4. Point your MCP client to `http://localhost:8000/mcp`

## Installation

### Prerequisites

1. Docker and Docker Compose (for the default FalkorDB setup)
2. OpenAI API key for LLM operations (or API keys for other supported LLM providers)
3. (Optional) Python 3.10+ if running the MCP server standalone with an external FalkorDB instance

### Setup

1. Clone the repository and navigate to the mcp_server directory
2. Use `uv` to create a virtual environment and install dependencies:

```bash
# Install uv if you don't have it already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a virtual environment and install dependencies in one step
uv sync

# Optional: Install additional providers (anthropic, gemini, groq, voyage, sentence-transformers)
uv sync --extra providers
```

## Configuration

The server can be configured using a `config.yaml` file, environment variables, or command-line arguments (in order of precedence).

### Default Configuration

The MCP server comes with sensible defaults:
- **Transport**: HTTP (accessible at `http://localhost:8000/mcp`)
- **Database**: FalkorDB (combined in single container with MCP server)
- **LLM**: OpenAI with model gpt-5.5
- **Embedder**: OpenAI text-embedding-3-small

### Database Configuration

#### FalkorDB (Default)

FalkorDB is a Redis-based graph database that comes bundled with the MCP server in a single Docker container. This is the default and recommended setup.

```yaml
database:
  provider: "falkordb"  # Default
  providers:
    falkordb:
      uri: "redis://localhost:6379"
      password: ""  # Optional
      database: "default_db"  # Optional
```

#### Neo4j

For production use or when you need a full-featured graph database, Neo4j is recommended:

```yaml
database:
  provider: "neo4j"
  providers:
    neo4j:
      uri: "bolt://localhost:7687"
      username: "neo4j"
      password: "your_password"
      database: "neo4j"  # Optional, defaults to "neo4j"
```

#### FalkorDB

FalkorDB is another graph database option based on Redis:

```yaml
database:
  provider: "falkordb"
  providers:
    falkordb:
      uri: "redis://localhost:6379"
      password: ""  # Optional
      database: "default_db"  # Optional
```

### Configuration File (config.yaml)

The server supports multiple LLM providers (OpenAI, Anthropic, Gemini, Groq) and embedders. Edit `config.yaml` to configure:

```yaml
server:
  transport: "http"  # Default. Options: stdio, http

llm:
  provider: "openai"  # or "anthropic", "gemini", "groq", "azure_openai"
  model: "gpt-5.5"  # Default model

database:
  provider: "falkordb"  # Default. Options: "falkordb", "neo4j"
```

### Using Ollama for Local LLM and Embeddings

Ollama LLM inference uses its OpenAI-compatible `/v1` endpoint. Embeddings use Ollama's native `/api/embed` endpoint directly:

```yaml
llm:
  provider: "openai"
  model: "gpt-oss:120b"  # or your preferred Ollama model
  providers:
    openai:
      api_url: "http://localhost:11434/v1"
      api_key: "ollama"  # placeholder required by the OpenAI-compatible client

embedder:
  provider: "ollama"
  model: "nomic-embed-text"
  dimensions: 768
  providers:
    ollama:
      api_url: "http://localhost:11434"  # host root; client appends /api/embed
      truncate: true
      timeout: 60
```

Local Ollama needs no embedding API key. Ollama Cloud uses `api_url: "https://ollama.com"` and `api_key: ${OLLAMA_API_KEY}`. Keep embedding model and dimensions unchanged for an existing graph; changing either requires rebuilding stored embeddings and vector indexes.

Make sure Ollama is running locally with `ollama serve` and both models are pulled. From Docker, `localhost` means the MCP container; use `http://host.docker.internal:11434` or a reachable Ollama service name. Kubernetes likewise needs a service URL such as `http://ollama:11434`, not pod-local `localhost` unless Ollama runs as a sidecar.

> [!IMPORTANT]
> Graphiti relies on structured (JSON) output for entity/edge extraction and deduplication, and reliability varies on
> small or local models. Prefer the most capable model your hardware can run — very small models frequently emit JSON
> that doesn't match the expected schema, which surfaces as ingestion failures. For background and the
> `structured_output_mode` (`json_schema` vs `json_object`) trade-off, see the core README's
> [Structured output and small models](../README.md#structured-output-and-small-models) section.

### Entity Types

Graphiti MCP Server includes built-in entity types for structured knowledge extraction. These entity types are always enabled and configured via the `entity_types` section in your `config.yaml`:

**Available Entity Types:**

- **Preference**: User preferences, choices, opinions, or selections (prioritized for user-specific information)
- **Requirement**: Specific needs, features, or functionality that must be fulfilled
- **Procedure**: Standard operating procedures and sequential instructions
- **Location**: Physical or virtual places where activities occur
- **Event**: Time-bound activities, occurrences, or experiences
- **Person**: An individual human referenced in the content
- **Organization**: Companies, institutions, groups, or formal entities
- **Document**: Information content in various forms (books, articles, reports, videos, etc.)
- **Topic**: Subject of conversation, interest, or knowledge domain (used as a fallback)
- **Object**: Physical items, tools, devices, or possessions (used as a fallback)

These entity types are defined in `config.yaml` and can be customized by modifying the descriptions:

```yaml
graphiti:
  entity_types:
    - name: "Preference"
      description: "User preferences, choices, opinions, or selections"
    - name: "Requirement"
      description: "Specific needs, features, or functionality"
    # ... additional entity types
```

The MCP server automatically uses these entity types during episode ingestion to extract and structure information from conversations and documents.

> **Upgrade note:** These built-in types are now registered as rich models with typed attributes (e.g. a `description`), so extraction stores those attributes on entities. The shipped default `config.yaml` enables them, so an existing deployment on the default config switches from attribute-free to rich-attribute extraction. To keep the previous behavior, set `graphiti.entity_types` to an empty list (or remove the entries).

### Environment Variables

The `config.yaml` file supports environment variable expansion using `${VAR_NAME}` or `${VAR_NAME:default}` syntax. Key variables:

- `NEO4J_URI`: URI for the Neo4j database (default: `bolt://localhost:7687`)
- `NEO4J_USER`: Neo4j username (default: `neo4j`)
- `NEO4J_PASSWORD`: Neo4j password (default: `demodemo`)
- `OPENAI_API_KEY`: OpenAI API key (required for OpenAI LLM/embedder)
- `ANTHROPIC_API_KEY`: Anthropic API key (for Claude models)
- `GOOGLE_API_KEY`: Google API key (for Gemini models)
- `GROQ_API_KEY`: Groq API key (for Groq models)
- `AZURE_OPENAI_API_KEY`: Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: Azure OpenAI endpoint URL
- `AZURE_OPENAI_DEPLOYMENT`: Azure OpenAI deployment name
- `AZURE_OPENAI_EMBEDDINGS_ENDPOINT`: Optional Azure OpenAI embeddings endpoint URL
- `AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT`: Optional Azure OpenAI embeddings deployment name
- `AZURE_OPENAI_API_VERSION`: Optional Azure OpenAI API version
- `USE_AZURE_AD`: Optional use Azure Managed Identities for authentication
- `EMBEDDER_DIMENSIONS`: Embedding vector width (must match the selected model)
- `OLLAMA_EMBEDDER_API_URL`: Ollama host root for native `/api/embed` (default: `http://localhost:11434`)
- `OLLAMA_API_KEY`: Optional Bearer token for Ollama Cloud
- `OLLAMA_EMBEDDER_TRUNCATE`: Truncate overlong inputs (default: `true`)
- `OLLAMA_EMBEDDER_KEEP_ALIVE`: Optional model keep-alive duration, such as `5m`
- `OLLAMA_EMBEDDER_TIMEOUT`: Request timeout in seconds (default: `60`)
- `SEMAPHORE_LIMIT`: Episode processing concurrency. See [Concurrency and LLM Provider 429 Rate Limit Errors](#concurrency-and-llm-provider-429-rate-limit-errors)

You can set these variables in a `.env` file in the project directory.

## Running the Server

### Default Setup (FalkorDB Combined Container)

To run the Graphiti MCP server with the default FalkorDB setup:

```bash
docker compose up
```

This starts a single container with:
- HTTP transport on `http://localhost:8000/mcp`
- FalkorDB graph database on `localhost:6379`
- FalkorDB web UI on `http://localhost:3000`
- OpenAI LLM with gpt-5.5 model

### Running with Neo4j

#### Option 1: Using Docker Compose

The easiest way to run with Neo4j is using the provided Docker Compose configuration:

```bash
# This starts both Neo4j and the MCP server
docker compose -f docker/docker-compose.neo4j.yaml up
```

#### Option 2: Direct Execution with Existing Neo4j

If you have Neo4j already running:

```bash
# Set environment variables
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"

# Run with Neo4j
uv run main.py --database-provider neo4j
```

Or use the Neo4j configuration file:

```bash
uv run main.py --config config/config-docker-neo4j.yaml
```

### Running with FalkorDB

#### Option 1: Using Docker Compose

```bash
# This starts both FalkorDB (Redis-based) and the MCP server
docker compose -f docker/docker-compose.falkordb.yaml up
```

#### Option 2: Direct Execution with Existing FalkorDB

```bash
# Set environment variables
export FALKORDB_URI="redis://localhost:6379"
export FALKORDB_PASSWORD=""  # If password protected

# Run with FalkorDB
uv run main.py --database-provider falkordb
```

Or use the FalkorDB configuration file:

```bash
uv run main.py --config config/config-docker-falkordb.yaml
```

### Available Command-Line Arguments

- `--config`: Path to YAML configuration file (default: config.yaml)
- `--llm-provider`: LLM provider to use (openai, anthropic, gemini, groq, azure_openai)
- `--embedder-provider`: Embedder provider to use (openai, azure_openai, gemini, voyage, ollama)
- `--embedder-model`: Model name to use with the embedder
- `--embedder-dimensions`: Embedding vector width (must match the selected model)
- `--database-provider`: Database provider to use (falkordb, neo4j) - default: falkordb
- `--model`: Model name to use with the LLM client
- `--temperature`: Temperature setting for the LLM (0.0-2.0)
- `--transport`: Choose the transport method (http or stdio, default: http)
- `--group-id`: Set a namespace for the graph (optional). If not provided, defaults to "main"
- `--destroy-graph`: If set, destroys all Graphiti graphs on startup

### Concurrency and LLM Provider 429 Rate Limit Errors

Graphiti's ingestion pipelines are designed for high concurrency, controlled by the `SEMAPHORE_LIMIT` environment variable. This setting determines how many episodes can be processed simultaneously. Since each episode involves multiple LLM calls (entity extraction, deduplication, summarization), the actual number of concurrent LLM requests will be several times higher.

**Default:** `SEMAPHORE_LIMIT=10` (suitable for OpenAI Tier 3, mid-tier Anthropic)

#### Tuning Guidelines by LLM Provider

**OpenAI:**
- Tier 1 (free): 3 RPM → `SEMAPHORE_LIMIT=1-2`
- Tier 2: 60 RPM → `SEMAPHORE_LIMIT=5-8`
- Tier 3: 500 RPM → `SEMAPHORE_LIMIT=10-15`
- Tier 4: 5,000 RPM → `SEMAPHORE_LIMIT=20-50`

**Anthropic:**
- Default tier: 50 RPM → `SEMAPHORE_LIMIT=5-8`
- High tier: 1,000 RPM → `SEMAPHORE_LIMIT=15-30`

**Azure OpenAI:**
- Consult your quota in Azure Portal and adjust accordingly
- Start conservative and increase gradually

**Ollama (local):**
- Hardware dependent → `SEMAPHORE_LIMIT=1-5`
- Monitor CPU/GPU usage and adjust

#### Symptoms

- **Too high**: 429 rate limit errors, increased API costs from parallel processing
- **Too low**: Slow episode throughput, underutilized API quota

#### Monitoring

- Watch logs for `429` rate limit errors
- Monitor episode processing times in server logs
- Check your LLM provider's dashboard for actual request rates
- Track token usage and costs

Set this in your `.env` file:
```bash
SEMAPHORE_LIMIT=10  # Adjust based on your LLM provider tier
```

### Docker Deployment

The Graphiti MCP server can be deployed using Docker with your choice of database backend. The Dockerfile uses `uv` for package management, ensuring consistent dependency installation.

A pre-built Graphiti MCP container is available at: `zepai/knowledge-graph-mcp`

#### Environment Configuration

Before running Docker Compose, configure your API keys using a `.env` file (recommended):

1. **Create a .env file in the mcp_server directory**:
   ```bash
   cd graphiti/mcp_server
   cp .env.example .env
   ```

2. **Edit the .env file** to set your API keys:
   ```bash
   # Required - at least one LLM provider API key
   OPENAI_API_KEY=your_openai_api_key_here

   # Optional - other LLM providers
   ANTHROPIC_API_KEY=your_anthropic_key
   GOOGLE_API_KEY=your_google_key
   GROQ_API_KEY=your_groq_key

   # Optional - embedder providers
   VOYAGE_API_KEY=your_voyage_key
   OLLAMA_EMBEDDER_API_URL=http://host.docker.internal:11434
   EMBEDDER_DIMENSIONS=768
   ```

**Important**: The `.env` file must be in the `mcp_server/` directory (the parent of the `docker/` subdirectory).

#### Running with Docker Compose

**All commands must be run from the `mcp_server` directory** to ensure the `.env` file is loaded correctly:

```bash
cd graphiti/mcp_server
```

##### Option 1: FalkorDB Combined Container (Default)

Single container with both FalkorDB and MCP server - simplest option:

```bash
docker compose up
```

##### Option 2: Neo4j Database

Separate containers with Neo4j and MCP server:

```bash
docker compose -f docker/docker-compose-neo4j.yml up
```

Default Neo4j credentials:
- Username: `neo4j`
- Password: `demodemo`
- Bolt URI: `bolt://neo4j:7687`
- Browser UI: `http://localhost:7474`

##### Option 3: FalkorDB with Separate Containers

Alternative setup with separate FalkorDB and MCP server containers:

```bash
docker compose -f docker/docker-compose-falkordb.yml up
```

FalkorDB configuration:
- Redis port: `6379`
- Web UI: `http://localhost:3000`
- Connection: `redis://falkordb:6379`

#### Accessing the MCP Server

Once running, the MCP server is available at:
- **HTTP endpoint**: `http://localhost:8000/mcp`
- **Health check**: `http://localhost:8000/health`

#### Running Docker Compose from a Different Directory

If you run Docker Compose from the `docker/` subdirectory instead of `mcp_server/`, you'll need to modify the `.env` file path in the compose file:

```yaml
# Change this line in the docker-compose file:
env_file:
  - path: ../.env    # When running from mcp_server/

# To this:
env_file:
  - path: .env       # When running from mcp_server/docker/
```

However, **running from the `mcp_server/` directory is recommended** to avoid confusion.

## Integrating with MCP Clients

### VS Code / GitHub Copilot

VS Code with GitHub Copilot Chat extension supports MCP servers. Add to your VS Code settings (`.vscode/mcp.json` or global settings):

```json
{
  "mcpServers": {
    "graphiti": {
      "uri": "http://localhost:8000/mcp",
      "transport": {
        "type": "http"
      }
    }
  }
}
```

### Other MCP Clients

To use the Graphiti MCP server with other MCP-compatible clients, configure it to connect to the server:

> [!IMPORTANT]
> You will need the Python package manager, `uv` installed. Please refer to the [`uv` install instructions](https://docs.astral.sh/uv/getting-started/installation/).
>
> Ensure that you set the full path to the `uv` binary and your Graphiti project folder.

```json
{
  "mcpServers": {
    "graphiti-memory": {
      "transport": "stdio",
      "command": "/Users/<user>/.local/bin/uv",
      "args": [
        "run",
        "--isolated",
        "--directory",
        "/Users/<user>>/dev/zep/graphiti/mcp_server",
        "--project",
        ".",
        "main.py",
        "--transport",
        "stdio"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "OPENAI_API_KEY": "sk-XXXXXXXX",
        "MODEL_NAME": "gpt-5.5"
      }
    }
  }
}
```

For HTTP transport (default), you can use this configuration:

```json
{
  "mcpServers": {
    "graphiti-memory": {
      "transport": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

## Available Tools

The Graphiti MCP server exposes **28 total** tools: **14 legacy** semantic-memory tools plus **14 catalog-v2** deterministic tools. Catalog tools are additive; legacy tool names, parameters, and behavior remain frozen.

### Legacy tool inventory (14)

- `add_memory`: Add an episode to the knowledge graph (supports text, JSON, and message formats).
  Supports the bi-temporal `reference_time`, `excluded_entity_types`, `custom_extraction_instructions`,
  `previous_episode_uuids`, `update_communities`, and `saga` / `saga_previous_episode_uuid`.
- `search_nodes`: Search the knowledge graph for relevant entities; supports `entity_types` and `center_node_uuid`.
- `search_memory_facts`: Search for relevant facts (edges); supports `edge_types`, `center_node_uuid`,
  and `valid_at` / `invalid_at` date-range filters.
- `add_triplet`: Add a single fact (source entity -> fact -> target entity) directly, bypassing extraction.
- `get_entity_edge`: Get an entity edge by its UUID.
- `get_episodes`: Get the most recent episodes for a specific group.
- `get_episode_entities`: Trace provenance — the entities and facts created by specific episode UUIDs.
- `update_entity`: Directly repair an existing entity's name, summary, attributes, or labels by UUID.
  Attributes merge with existing values; labels replace existing custom labels. Neo4j label replacement is
  transactional; FalkorDB uses its supported literal-label `REMOVE` syntax. The entity UUID, group,
  creation time, and embedding are not caller-editable; renaming regenerates the embedding automatically.
  This administrative operation does not create episode provenance or temporal history, so prefer
  `add_memory` for normal knowledge corrections.
- `build_communities`: Detect entity communities and produce higher-level community summaries.
- `summarize_saga`: Generate or refresh the running summary of a saga's episodes.
- `delete_episode`: Delete an episode and cascade-delete the entities/facts it solely created.
- `delete_entity_edge`: Delete an entity edge from the knowledge graph.
- `clear_graph`: Clear all data from the knowledge graph for the given group(s).
- `get_status`: Get the status of the Graphiti MCP server and database connection.

Custom entity types and edge (fact) types — including which edge types may connect which entity types —
can be configured under the `graphiti` section of `config/config.yaml`. See the `entity_types`,
`edge_types`, and `edge_type_map` keys there.

### Catalog tool inventory (14)

> [!WARNING]
> Catalog tools are an administrative structured-ingestion surface for trusted PDF-catalog, DDL,
> Oracle-dictionary, and SQL-parser pipelines. They write synchronously and return only after commit,
> rollback, or a structured error. Keep writes disabled unless an operator has approved the source,
> target `group_id`, fixed UUID namespace, allowlists, and batch limits. **Catalog tools support
> Neo4j 5.26+ only**; other backends return `backend_unavailable`. No non-Neo4j portability claim is made.

Stable catalog tool inventory:

1. `upsert_typed_entities` — validate and synchronously upsert allowlisted typed entities. Server derives UUIDv5 identities; embeds searchable text before the write transaction; never accepts caller UUIDs as identity authority.
2. `upsert_typed_edges` — validate and synchronously upsert allowlisted facts between exact typed endpoints. Endpoints must already exist; no implicit create/relabel.
3. `resolve_typed_entities` — read-only. Resolve expected typed entities; report missing, generic, duplicate, mistyped, UUID-mismatch, and missing-embedding conditions without writing or embedding.
4. `resolve_typed_edges` — read-only. Resolve expected typed edges and endpoint pairing conditions without writing.
5. `verify_catalog_batch` — read-only. Verify entity, edge, endpoint, embedding, and optional provenance/manifest expectations by batch ID, explicit keys, or both.
6. `upsert_provenance` — attach deterministic sources to existing targets using installed Graphiti provenance shapes. Missing/mistyped target → `provenance_target_missing` with no partial write.
7. `get_catalog_ingest_status` — read-only. The caller supplies `group_id` + `batch_id`; the server derives the deterministic batch UUID internally and loads restart-safe state from a non-`Entity` `CatalogIngestBatch` node.
8. `get_catalog_batch_manifest` — read-only. Paginated durable membership projection for a committed batch (compact identity + content hashes only; never embeddings, payload, or credentials).
9. `get_catalog_evidence` — read-only. Paginated compact evidence links for one entity or edge target.
10. `upsert_catalog_batch` — validate a complete nested request, resolve same-request and persisted endpoints, create all embeddings before one domain transaction, then commit entities/edges/provenance/status atomically. Requires `atomic=true`. Kept for compatibility; **not** the preferred large-payload path.
11. `get_catalog_capabilities` — read-only. Mutation-free discovery of gates, versions, registries, limits, and feature flags. Never returns the raw UUID namespace (only a one-way `namespace_fingerprint` when configured).
12. `prepare_catalog_batch` — validate full catalog-v2 domain body, embed, store an immutable prepared plan, return one-time `plan_token` + hashes/counts/expiry. Preferred first step for large payloads.
13. `commit_prepared_catalog_batch` — **token-only** commit of a prepared plan (`plan_token` + optional compare-only `expected_request_sha256`). No replacement payload.
14. `discard_prepared_catalog_batch` — **token-only** discard of a prepared plan.

All catalog tools require catalog configuration to be loadable. Write tools additionally require `catalog_upsert.enabled=true` and a valid fixed namespace. Every request is isolated by its validated `group_id`.

## Catalog-v2 Operator Reference

Migration and offline canary regeneration: see [`docs/CATALOG_V2_MIGRATION.md`](docs/CATALOG_V2_MIGRATION.md).

### Preferred large-payload path

For large or agent-driven catalog batches, prefer:

1. `prepare_catalog_batch` with the full catalog-v2 domain body (`identity_schema_version`, `system_key`, `group_id`, `batch_id`, entities/edges/provenance, required `catalog_sha256`, optional client `request_sha256`, `atomic=true` only).
2. `commit_prepared_catalog_batch` with **only** `plan_token` (and optional `expected_request_sha256` compare guard). No entities/edges/sources/evidence/catalog_sha256/group/batch replacement is accepted on commit.
3. On abandon before commit: `discard_prepared_catalog_batch` with `plan_token` only.

Direct tools (`upsert_typed_entities`, `upsert_typed_edges`, `upsert_provenance`, `upsert_catalog_batch`) remain for compatibility and small administrative fixes. Operator policy does not approve them as the hardened canary procedure; regenerated canary work uses the preferred prepare/commit path after separate authorization.

#### Identity schema and system keys

- `identity_schema_version` must be exactly `catalog-v2`. Other values → `unsupported_identity_schema`.
- `system_key` is a closed set: `FE`, `BO`, `COMMON`.
- **FE/BO single-group guidance:** keep FE and BO catalog objects in one group_id. `system_key` and the embedded graph-key system segment keep otherwise-identical Oracle names distinct. Each request/batch has one `system_key`, so ingest FE and BO as separate batches within that same group. `COMMON` is explicit shared ownership, never a fallback for ambiguous ownership. Every entity/edge endpoint `graph_key` must embed the same `system_key` as the request shell.
- Server derives all UUIDv5 identities from the configured namespace + canonical material. Caller UUIDs are never identity authority.
- Canonicalization version: `catalog-canonical-v1`. Catalog schema version: `catalog-schema-v1`.

### Catalog-v2 graph-key grammar and group scope

All entity `graph_key` values fullmatch a server registry. Form:

```text
<PREFIX>::<SYSTEM>::<body>
```

- `<PREFIX>` comes from the entity-type prefix table below (exact, including trailing `::`).
- `<SYSTEM>` is exactly one of `FE`, `BO`, `COMMON` and must equal request `system_key` when the shell supplies one.
- Body segments use uppercase Oracle-ish identifiers `[A-Z][A-Z0-9_$#]*` unless noted. No NFC rewrite, no case folding, fail-closed.
- Max length: 1024 characters.

| Entity type | Prefix | Body pattern (after `PREFIX::{SYSTEM}::`) |
|---|---|---|
| `System` | `SYSTEM::` | `<IDENT>` |
| `Database` | `DATABASE::` | `<IDENT>` |
| `DictionaryDocument` | `DOC::` | `<IDENT>.<IDENT>` |
| `Schema` | `SCHEMA::` | `<IDENT>.<IDENT>` |
| `Table` | `TABLE::` | `<IDENT>.<IDENT>.<IDENT>` |
| `View` | `VIEW::` | `<IDENT>.<IDENT>.<IDENT>` |
| `MaterializedView` | `MVIEW::` | `<IDENT>.<IDENT>.<IDENT>` |
| `Column` | `COLUMN::` | `<IDENT>.<IDENT>.<IDENT>.<IDENT>` |
| `Constraint` | `CONSTRAINT::` | `<IDENT>.<IDENT>.<IDENT>` |
| `Index` | `INDEX::` | `<IDENT>.<IDENT>.<IDENT>` |
| `Package` | `PACKAGE::` | `<IDENT>.<IDENT>.<IDENT>` |
| `Procedure` | `PROCEDURE::` | `<DB>.<SCHEMA>.(<PACKAGE>.)?<NAME>#<OVERLOAD>` |
| `Function` | `FUNCTION::` | `<DB>.<SCHEMA>.(<PACKAGE>.)?<NAME>#<OVERLOAD>` |
| `Trigger` | `TRIGGER::` | `<IDENT>.<IDENT>.<IDENT>` |
| `Sequence` | `SEQUENCE::` | `<IDENT>.<IDENT>.<IDENT>` |
| `Synonym` | `SYNONYM::` | `<IDENT>.<IDENT>.<IDENT>` |
| `DatabaseLink` | `DBLINK::` | `<IDENT>.<IDENT>` |
| `SourceArtifact` | `SOURCE::` | path-ish `[A-Za-z0-9._\-/\#]+` (no spaces) |

Examples:

```text
TABLE::FE::APP.SALES.ORDERS
COLUMN::BO::APP.SALES.ORDERS.ORDER_ID
PROCEDURE::FE::APP.SALES.PKG_ORDERS.PLACE_ORDER#1
FUNCTION::COMMON::APP.UTIL.F_HASH#VARCHAR2
SOURCE::FE::ddl/app/sales/orders.sql
```

#### Overload handling

- `Procedure` and `Function` keys **require** an overload token after `#`.
- Overload token pattern: nonempty `[A-Za-z0-9_$,#()]+` (no rewrite).
- Distinct overload tokens produce distinct graph keys and therefore distinct server UUIDv5 identities.
- Callers must supply the exact overload token from the source catalog/DDL/parser; the server does not invent, normalize, or collapse overloads.

### Entity and edge registries

#### Entity registry (18 types)

`System`, `Database`, `DictionaryDocument`, `Schema`, `Table`, `View`, `MaterializedView`, `Column`, `Constraint`, `Index`, `Package`, `Procedure`, `Function`, `Trigger`, `Sequence`, `Synonym`, `DatabaseLink`, `SourceArtifact`.

Protected entity properties (cannot be supplied via `attributes`): `uuid`, `group_id`, `labels`, `graph_key`, `name_embedding`, `created_at`, `updated_at`, `content_sha256`.

#### Edge registry (16 types)

`Contains`, `PrimaryKeyOf`, `UniqueKeyOf`, `ForeignKeyTo`, `EnforcedBy`, `TriggerOn`, `SynonymFor`, `DocumentedBy`, `Calls`, `ReadsFrom`, `WritesTo`, `JoinsWith`, `ReferencesByCode`, `DependsOn`, `DerivedFrom`, `UsesSequence`.

`EnforcedBy` requires explicit DDL or Oracle-dictionary evidence. Deferred types (`LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`) are intentionally absent.

### Endpoint type map

A single server-owned endpoint map is authoritative. Illegal pairs return `edge_endpoint_pair_not_allowed`. Client-supplied maps are never accepted.

| Edge type | Allowed `(source_entity_type → target_entity_type)` pairs |
|---|---|
| `Contains` | `System→Database`; `Database→Schema`; `Database→DatabaseLink`; `Schema→{Table,View,MaterializedView,Package,Procedure,Function,Trigger,Sequence,Synonym,Index,Constraint,SourceArtifact}`; `Table→Column`; `View→Column`; `MaterializedView→Column`; `Package→Procedure`; `Package→Function`; `DictionaryDocument→SourceArtifact` |
| `PrimaryKeyOf` | `Constraint→Table`; `Constraint→Column` |
| `UniqueKeyOf` | `Constraint→Table`; `Constraint→Column` |
| `ForeignKeyTo` | `Column→Column`; `Table→Table` |
| `EnforcedBy` | `Constraint→Table`; `Constraint→Column` |
| `TriggerOn` | `Trigger→Table`; `Trigger→View`; `Trigger→MaterializedView` |
| `SynonymFor` | `Synonym→{Table,View,MaterializedView,Sequence,Procedure,Function,Package,Synonym}` |
| `DocumentedBy` | every allowlisted entity type → `DictionaryDocument` or `SourceArtifact` |
| `Calls` | `{Procedure,Function,Trigger,Package} → {Procedure,Function,Package}` |
| `ReadsFrom` | `{Procedure,Function,Trigger,Package,View,MaterializedView} → {Table,View,MaterializedView,Column,Synonym}` |
| `WritesTo` | `{Procedure,Function,Trigger,Package} → {Table,Column,View,MaterializedView,Synonym}` |
| `JoinsWith` | `{Table,View,MaterializedView,Column} × same set` |
| `ReferencesByCode` | `{Package,Procedure,Function,Trigger,SourceArtifact} → {Table,View,MaterializedView,Column,Sequence,Synonym,Package,Procedure,Function}` |
| `DependsOn` | union of `Contains` ∪ `Calls` ∪ `ReadsFrom` ∪ `WritesTo` pairs |
| `DerivedFrom` | `{View,MaterializedView,SourceArtifact} → {Table,View,MaterializedView,Column,SourceArtifact}` |
| `UsesSequence` | `{Procedure,Function,Trigger,Package,View,MaterializedView} → Sequence` |

Live authoritative export: `get_catalog_capabilities` → `endpoint_map`.

### Hash contracts

Server is the only hash authority. All digests are 64-character lowercase hex SHA-256.

**Entity `content_sha256` includes:** `entity_type`, `graph_key`, `name_raw`, `name_canonical`, `database_qualified_name`, `summary`, `attributes`, `source_refs`, `confidence`.

**Edge `content_sha256` includes:** `edge_type`, `edge_key`, source/target graph keys and entity types, `fact`, `evidence`, `attributes`, `confidence`.

**Source `content_sha256` includes:** `source_key`, `reference_time`, `attributes`, `metadata`.

**Evidence `link_key` identity excludes** transport-only `content_sha256`, excerpt, and confidence; material is `source_key|target_kind|target_type|target_key|evidence_kind|extractor_name|extractor_version|rule_id|locator_canonical`.

**Evidence content hash includes** excerpt bytes, confidence, and nested targets/locator; excludes client transport-only `content_sha256`.

**Batch `request_sha256` includes (HASH-02):** `canonicalization_version`, `identity_schema_version`, `system_key`, `group_id`, `batch_id`, `catalog_sha256`, sorted entities/edges/sources/evidence_links (evidence post byte-identical coalesce).

**Batch `request_sha256` excludes (HASH-03):** `dry_run`, caller-supplied `request_sha256`, generated timestamps, retry counters, plan tokens, and correlation IDs. Embeddings are outside the canonical request recipe.

If the client supplies `content_sha256` / `request_sha256` / `expected_request_sha256`, mismatch → `content_hash_mismatch` (compare-only; never identity authority).

### Capabilities contract

`get_catalog_capabilities` returns these read-only response fields:

| Field | Meaning |
|---|---|
| `package_version` | MCP server package version |
| `backend` | Graph backend name when known (`neo4j`, etc.) |
| `connectivity` | `ok` \| `error` \| `unknown` |
| `catalog_writes_enabled` | `catalog_upsert.enabled` |
| `catalog_reads_enabled` | `catalog_upsert.reads_enabled` |
| `uuid_namespace_configured` | whether a parseable namespace is configured |
| `namespace_fingerprint` | one-way 16-hex SHA-256 prefix; **never** the raw namespace |
| `identity_schema_version` | `catalog-v2` |
| `canonicalization_version` | `catalog-canonical-v1` |
| `catalog_schema_version` | `catalog-schema-v1` |
| `entity_types` / `entity_prefixes` | sorted registry |
| `edge_types` | sorted registry |
| `endpoint_map` | sorted allowed pairs per edge type |
| `limits.configured` | configured batch, prepared-payload, active-plan, TTL, chunk-size, and page ceilings |
| `limits.hard` | exported hard batch, prepared-payload, active-plan, TTL, and page ceilings; chunk-size/chunk-count hard constants are not exported here |
| `embeddings` | provider/model/ready (ready may be `unknown`) |
| `neo4j_indexes` | `ready` \| `unknown` \| `n/a` |
| `features.prepare_commit` | prepare/commit control plane available |
| `features.explicit_evidence_links` | non-Cartesian evidence links available |
| `features.manifests` | durable manifests co-committed |
| `features.manifest_verification` | manifest-backed verify path available |

Capabilities never probe with writes, never mutate schema/indexes, and never return secrets or the raw UUID namespace.

### Prepare, commit, and discard lifecycle

Plan states: `PREPARED`, `COMMITTING`, `COMMITTED`, `DISCARDED`, `EXPIRED`.

1. **prepare** — full validation + pre-transaction embeddings + immutable plan store → one-time `plan_token`, `plan_uuid`, `request_sha256`, `catalog_sha256`, `artifact_sha256`, `expires_at`, counts/projections. Receipt never includes canonical payload, membership, or embeddings.
2. **commit** — claim token, compare optional `expected_request_sha256`, commit domain objects + status + durable manifest atomically (or roll back). Receipt includes plan/state/hashes/counts/`manifest_sha256`/`batch_uuid`; never returns `plan_token`, membership, payload, or embeddings.
3. **discard** — token-only terminal discard before commit.
4. Matching commit replay may return the stable `COMMITTED` receipt without rewriting domain data; repeated discard is idempotent. Commit after discard returns `prepared_plan_not_found`. Discard while `COMMITTING` or after `COMMITTED` returns `prepared_plan_conflict`. TTL exceeded returns `prepared_plan_expired`; binding/state conflicts return `prepared_plan_conflict`; contradictory or incomplete terminal evidence may return `prepared_plan_already_consumed`.

### Limits and overload handling

| Limit | Default | Hard max |
|---|---:|---:|
| entities per batch | 500 | 5000 |
| edges per batch | 2000 | 10000 |
| provenance links per batch | 5000 | 20000 |
| plan TTL (seconds) | 3600 | 86400 |
| prepared payload bytes | 4_194_304 (4 MiB) | 16_777_216 (16 MiB) |
| prepared chunk bytes | 131_072 | 262_144 |
| chunks per plan | — | 128 |
| active plans per group | 8 | 32 |
| diagnostic page size | 100 | 500 |
| short string | — | 512 |
| graph_key / edge_key | — | 1024 |
| summary / fact | — | 4096 |
| evidence excerpt | — | 8192 |
| attribute keys | — | 64 |
| source refs | — | 32 |
| nested JSON depth / nodes | — | 32 / 10000 |

Configured values may be lower than hard max; requests above the effective limit fail before persistent side effects (`batch_limit_exceeded`).

### Explicit evidence links

Evidence is **non-Cartesian**: each `CatalogEvidenceLink` names exactly one source and exactly one target (entity **or** edge).

Allowed `evidence_kind`: `oracle_dictionary`, `ddl`, `view_sql`, `plsql_source`, `comment`, `manual`.

Entity-target example:

```json
{
  "source_key": "SOURCE::FE::ddl/app/sales/orders.sql",
  "entity_target": {
    "entity_type": "Table",
    "graph_key": "TABLE::FE::APP.SALES.ORDERS"
  },
  "evidence_kind": "ddl",
  "locator": {"object_name": "ORDERS", "start_line": 10, "end_line": 40},
  "excerpt": "CREATE TABLE APP.SALES.ORDERS ( ... )",
  "extractor_name": "ddl-parser",
  "extractor_version": "1.0.0",
  "rule_id": "table-from-create",
  "confidence": 1.0
}
```

Edge-target example:

```json
{
  "source_key": "SOURCE::FE::ddl/app/sales/orders.sql",
  "edge_target": {
    "edge_type": "Contains",
    "edge_key": "CONTAINS::TABLE::FE::APP.SALES.ORDERS->COLUMN::FE::APP.SALES.ORDERS.ORDER_ID"
  },
  "evidence_kind": "ddl",
  "extractor_name": "ddl-parser",
  "extractor_version": "1.0.0",
  "confidence": 1.0
}
```

Read back with `get_catalog_evidence` (paginated compact projection).

### Manifest semantics

- On successful atomic commit, a durable **manifest** is co-committed with compact membership for entities, edges, sources, and evidence links (uuid + type/key + `content_sha256` + optional projected status).
- Manifests never store embeddings, `payload_b64`, source text, or credentials.
- `get_catalog_batch_manifest` returns paginated compact membership plus `request_sha256` / `catalog_sha256` / `artifact_sha256` / `manifest_sha256` and schema/canon versions when found.
- `verify_catalog_batch` can compare live graph state against expected keys and/or committed manifest membership (manifest mismatch → `manifest_mismatch`).

### Read and write gates

| Gate | Config field | Default | Controls |
|---|---|---|---|
| Write gate | `catalog_upsert.enabled` | `false` | prepare/commit and all catalog write tools |
| Read gate | `catalog_upsert.reads_enabled` | `true` | resolve/verify/status/manifest/evidence reads |

Gates are independent: reads do not require writes enabled. `get_catalog_capabilities` remains available regardless of `reads_enabled` because it is a mutation-free config view. Disabled write → `feature_disabled`. Non-Neo4j backend on catalog write path → `backend_unavailable`.

### Catalog error codes

Every structured catalog failure uses one of these codes (do not parse exception text as API contract):

| Code | Typical cause |
|---|---|
| `validation_error` | Request failed strict schema/validation |
| `feature_disabled` | Catalog writes (or required feature) disabled |
| `invalid_uuid_namespace` | Namespace missing/invalid when writes enabled |
| `batch_limit_exceeded` | Entities/edges/links/page/payload above effective limit |
| `content_hash_mismatch` | Client hash does not match server digest |
| `entity_type_conflict` | Same key claimed under conflicting entity types |
| `graph_key_prefix_mismatch` | Prefix does not match entity type (legacy mismatch path) |
| `deterministic_uuid_conflict` | Server UUID collides with different identity material |
| `missing_endpoint` | Edge endpoint entity not present |
| `endpoint_type_mismatch` | Endpoint exists with wrong type |
| `generic_endpoint_conflict` | Generic/untyped endpoint conflicts with typed catalog object |
| `edge_identity_conflict` | Edge identity collision / conflicting fact identity |
| `batch_conflict` | Committed `batch_id` reused with different content |
| `provenance_target_missing` | Provenance target missing or mistyped |
| `neo4j_transaction_failed` | Neo4j transaction aborted |
| `embedding_failed` | Embedder failed before write transaction |
| `internal_error` | Unexpected server failure (bounded message) |
| `backend_unavailable` | Non-Neo4j or backend not usable for catalog |
| `unsupported_identity_schema` | `identity_schema_version` ≠ `catalog-v2` |
| `invalid_system_key` | `system_key` / embedded system segment not in `{FE,BO,COMMON}` or mismatch |
| `edge_endpoint_pair_not_allowed` | Edge type forbids that source/target entity pair |
| `prepared_plan_not_found` | Unknown `plan_token` / plan |
| `prepared_plan_expired` | Plan past TTL |
| `prepared_plan_conflict` | Plan binding/state conflict |
| `prepared_plan_already_consumed` | Contradictory or incomplete terminal plan evidence prevents a stable receipt |
| `manifest_mismatch` | Live/expected membership disagrees with durable manifest |
| `provenance_link_conflict` | Evidence/provenance link identity conflict |

### Rollout configuration

```yaml
# config.yaml or ConfigMap data; credentials do not belong here.
catalog_upsert:
  enabled: false                 # write gate; default off
  reads_enabled: true            # read/diagnostic gate; independent of writes
  uuid_namespace: ${GRAPHITI_CATALOG_UUID_NAMESPACE}
  max_entities_per_batch: 500
  max_edges_per_batch: 2000
  max_provenance_links_per_batch: 5000
  plan_ttl_seconds: 3600
  max_prepared_payload_bytes: 4194304
  max_active_plans_per_group: 8
  prepared_chunk_bytes: 131072
  max_page_size: 100
```

Environment / config keys (names only; never commit secret values):

| Name | Role |
|---|---|
| `GRAPHITI_CATALOG_UUID_NAMESPACE` | Fixed UUIDv5 namespace for all catalog identities (immutable deployment config) |
| `CONFIG_PATH` | Path to YAML config |
| `catalog_upsert.enabled` | Write gate |
| `catalog_upsert.reads_enabled` | Read gate |
| `catalog_upsert.uuid_namespace` | YAML form of the namespace (or via env expansion) |
| `catalog_upsert.max_entities_per_batch` | Configured entity ceiling |
| `catalog_upsert.max_edges_per_batch` | Configured edge ceiling |
| `catalog_upsert.max_provenance_links_per_batch` | Configured provenance/evidence link ceiling |
| `catalog_upsert.plan_ttl_seconds` | Prepared-plan TTL |
| `catalog_upsert.max_prepared_payload_bytes` | Prepared payload ceiling |
| `catalog_upsert.max_active_plans_per_group` | Concurrent plan ceiling per `group_id` |
| `catalog_upsert.prepared_chunk_bytes` | Prepared artifact chunk size |
| `catalog_upsert.max_page_size` | Diagnostic list page ceiling |

`GRAPHITI_CATALOG_UUID_NAMESPACE` must be a fixed valid UUID when writes are enabled. Changing it changes every primary server-derived entity, edge, source, evidence-link, batch, manifest, and plan identity; mention and related control IDs change indirectly because they derive from those UUIDs. Never generate it at startup, rotate it during a retry, accept it from a catalog request, or log/print its value in operator docs.

### Semantic memory versus deterministic catalog ingestion

Use `add_memory` for semantic ingestion of prose, messages, or loosely structured JSON. It queues an asynchronous episode and uses the configured LLM to extract, deduplicate, summarize, and evolve the graph.

Use catalog tools for trusted PDF-catalog, DDL, Oracle-dictionary, or SQL-parser output where identity, type, endpoints, hash, and commit boundaries must be exact. These tools bypass `add_memory`, LLM extraction, and the ingestion queue. Entity and edge embeddings still use the configured embedder before writes so existing search remains interoperable.

### Graphiti and Neo4j provenance limits

A deterministic source is an installed-schema `Episodic` node. Entity provenance uses deterministic `MENTIONS` relationships. Neo4j cannot attach a relationship directly to another relationship without a new schema object, so fact provenance appends source episode UUIDs to the existing `RELATES_TO.episodes` list. Catalog-v2 additionally persists explicit non-`Entity` `CatalogEvidenceLink` control records that target exact entities or edges; these are not relationship-to-relationship provenance edges.

Catalog batch status uses only the `CatalogIngestBatch` label, never `Entity`, so normal entity search and community clustering exclude it. Control-plane prepared-plan and manifest records are likewise non-`Entity`. Normal catalog upserts are community-neutral: they never invoke `build_communities`.

### Catalog safety and backend scope

- Catalog backend claim: **Neo4j 5.26+ only**.
- Do not query or mutate `oracle-catalog-v2` for validation or Phase 5 work.
- Do not treat historical canary files or old ACCEPT_TAB SHA values as identity authority; see migration guide.
- Log batch IDs and counts only — never credentials, complete catalog payloads, raw documents, or complete source text.
- Phase 5 never executes canary. This reference does not authorize deployment, live canary execution, graph clear, or existing-data deletion as catalog rollout steps.

## Working with JSON Data

The Graphiti MCP server can process structured JSON data through the `add_episode` tool with `source="json"`. This
allows you to automatically extract entities and relationships from structured data:

```

add_episode(
name="Customer Profile",
episode_body="{\"company\": {\"name\": \"Acme Technologies\"}, \"products\": [{\"id\": \"P001\", \"name\": \"CloudSync\"}, {\"id\": \"P002\", \"name\": \"DataMiner\"}]}",
source="json",
source_description="CRM data"
)

```

## Integrating with the Cursor IDE

To integrate the Graphiti MCP Server with the Cursor IDE, follow these steps:

1. Run the Graphiti MCP server using the default HTTP transport:

```bash
uv run main.py --group-id <your_group_id>
```

Hint: specify a `group_id` to namespace graph data. If you do not specify a `group_id`, the server will use "main" as the group_id.

or

```bash
docker compose up
```

2. Configure Cursor to connect to the Graphiti MCP server.

```json
{
  "mcpServers": {
    "graphiti-memory": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

3. Add the Graphiti rules to Cursor's User Rules. See [cursor_rules.md](cursor_rules.md) for details.

4. Kick off an agent session in Cursor.

The integration enables AI assistants in Cursor to maintain persistent memory through Graphiti's knowledge graph
capabilities.

## Integrating with Claude Desktop (Docker MCP Server)

The Graphiti MCP Server uses HTTP transport (at endpoint `/mcp`). Claude Desktop does not natively support HTTP transport, so you'll need to use a gateway like `mcp-remote`.

1.  **Run the Graphiti MCP server**:

    ```bash
    docker compose up
    # Or run directly with uv:
    uv run main.py
    ```

2.  **(Optional) Install `mcp-remote` globally**:
    If you prefer to have `mcp-remote` installed globally, or if you encounter issues with `npx` fetching the package, you can install it globally. Otherwise, `npx` (used in the next step) will handle it for you.

    ```bash
    npm install -g mcp-remote
    ```

3.  **Configure Claude Desktop**:
    Open your Claude Desktop configuration file (usually `claude_desktop_config.json`) and add or modify the `mcpServers` section as follows:

    ```json
    {
      "mcpServers": {
        "graphiti-memory": {
          // You can choose a different name if you prefer
          "command": "npx", // Or the full path to mcp-remote if npx is not in your PATH
          "args": [
            "mcp-remote",
            "http://localhost:8000/mcp" // The Graphiti server's HTTP endpoint
          ]
        }
      }
    }
    ```

    If you already have an `mcpServers` entry, add `graphiti-memory` (or your chosen name) as a new key within it.

4.  **Restart Claude Desktop** for the changes to take effect.

## Requirements

- Python 3.10 or higher
- OpenAI API key (for LLM operations and embeddings) or other LLM provider API keys
- MCP-compatible client
- Docker and Docker Compose (for the default FalkorDB combined container)
- (Optional) Neo4j database (version 5.26 or later) if not using the default FalkorDB setup

## Telemetry

The Graphiti MCP server uses the Graphiti core library, which includes anonymous telemetry collection. When you initialize the Graphiti MCP server, anonymous usage statistics are collected to help improve the framework.

### What's Collected

- Anonymous identifier and system information (OS, Python version)
- Graphiti version and configuration choices (LLM provider, database backend, embedder type)
- **No personal data, API keys, or actual graph content is ever collected**

### How to Disable

To disable telemetry in the MCP server, set the environment variable:

```bash
export GRAPHITI_TELEMETRY_ENABLED=false
```

Or add it to your `.env` file:

```
GRAPHITI_TELEMETRY_ENABLED=false
```

For complete details about what's collected and why, see the [Telemetry section in the main Graphiti README](../README.md#telemetry).

## License

This project is licensed under the same license as the parent Graphiti project.
