# Coding Conventions

**Analysis Date:** 2026-07-16

## Repository Layout

Three independently-versioned Python packages, each with its own `pyproject.toml`, `Makefile`, and test suite:

- `graphiti_core/` — core library (`graphiti-core`, version in `pyproject.toml:4`)
- `server/` — FastAPI service (`graph-service`, `server/pyproject.toml`)
- `mcp_server/` — MCP server (`mcp_server/pyproject.toml`)

The root `conftest.py` explicitly excludes `mcp_server/*` from collection (`conftest.py:11`), and `mcp_server/tests/conftest.py` prevents loading the parent conftest. Run the appropriate suite from its own directory.

## Naming Patterns

**Files:**
- `snake_case.py` everywhere. Test files prefixed `test_`; integration tests suffixed `_int.py` (e.g. `tests/test_graphiti_int.py`, `tests/llm_client/test_anthropic_client_int.py`).
- Helper modules shared across tests use the `_test.py` / `_fixtures.py` suffix: `tests/helpers_test.py`, `tests/embedder/embedder_fixtures.py`.
- Private modules are `_`-prefixed only inside packages when meant to be internal (e.g. `graphiti_core/driver/neo4j/operations/`).

**Functions:**
- `snake_case`. Async functions same — no `async_` prefix.
- Public API entrypoints on `Graphiti` are verbs: `add_episode`, `save_entity_node`, `close`, `search`.
- Internal helpers are `_`-prefixed: `_resolve_with_llm`, `_extract_entity_summaries_batch`, `_clean_input`, `_get_cache_key`, `_resolve_reasoning_effort`, `_apply_attribute_extraction_preamble`.
- Factory functions use `get_` prefix: `get_driver`, `get_default_group_id`, `get_entity_node_save_query`.

**Variables:**
- `snake_case` locals, `SCREAMING_SNAKE_CASE` module-level constants.
- Constants cluster at top of module after imports: `graphiti_core/helpers.py:35-55` (`SAFE_CYPHER_IDENTIFIER_PATTERN`, `USE_PARALLEL_RUNTIME`, `SEMAPHORE_LIMIT`, `CHUNK_TOKEN_SIZE`, ...), `graphiti_core/llm_client/client.py:34-35` (`DEFAULT_TEMPERATURE`, `DEFAULT_CACHE_DIR`), `graphiti_core/driver/driver.py:49-56` (`DEFAULT_SIZE`, `ENTITY_INDEX_NAME`, ...).

**Types / Classes:**
- `PascalCase`. Implementations suffixed by role: `OpenAIClient`, `OpenAIEmbedder`, `Neo4jDriver`, `FalkorDriver`, `Neo4jSearchOperations`, `OpenAIRerankerClient`.
- Abstract bases: `LLMClient(ABC)`, `EmbedderClient(ABC)`, `GraphDriver(ABC)`, `CrossEncoderClient(ABC)`, `GraphOperationsInterface`.
- Pydantic models subclass `BaseModel`: result wrappers (`AddEpisodeResults`, `AddTripletResults`), config objects (`EmbedderConfig`, `LLMConfig`, `OpenAIEmbedderConfig`), prompt payload models (`Edge`, `ExtractedEdges`, `EdgeDuplicate`).
- Enums subclass `Enum`: `GraphProvider`, `EpisodeType`.

**Exceptions:**
- All in `graphiti_core/errors.py`, subclass `GraphitiError(Exception)`. Named `*Error`: `EdgeNotFoundError`, `NodeNotFoundError`, `EntityTypeValidationError`, `GroupIdValidationError`, `NodeLabelValidationError`, `SearchRerankerError`.
- Dual-inheritance for ValueError compatibility where Pydantic field validators raise them: `class NodeLabelValidationError(GraphitiError, ValueError)` (`errors.py:86`).
- Constructor stores `.message` and calls `super().__init__(self.message)`.

## Code Style

**Formatting:** Ruff, configured per-package in each `pyproject.toml`.

- Line length: **100** (`pyproject.toml:77`, `server/pyproject.toml:46`).
- Quote style: **single** (`[tool.ruff.format] quote-style = "single"`).
- Indent: spaces.
- Docstrings: formatted as code (`docstring-code-format = true`).
- `ignore = ["E501"]` — line-length lint disabled, formatter owns wrapping.

**Linting:** Ruff with rule set `E, F, UP, B, SIM, I` (`pyproject.toml:79-93`). Banned import: `typing.TypedDict` must be `typing_extensions.TypedDict` (`pyproject.toml:96-98`) — required by Pydantic on Python < 3.12.

**Type checking:** Pyright.
- `graphiti_core`: `typeCheckingMode = "basic"`, `pythonVersion = "3.10"`, `include = ["graphiti_core"]` (`pyproject.toml:105-108`).
- `server`: `typeCheckingMode = "standard"`, `include = ["."]` (`server/pyproject.toml:71-74`).
- `mcp_server`: own config in `mcp_server/pyproject.toml`.

**Python version:** `>=3.10,<4` for core. Use `from __future__ import annotations` to defer forward refs (see `graphiti_core/driver/driver.py:17`). Use `typing_extensions` for anything that needs to run on 3.10 (e.g. `LiteralString`, `Any`).

## Import Organization

Ruff isort (`I`) enforces ordering. Run `make format` (`ruff check --select I --fix` then `ruff format`).

**Observed order** (e.g. `graphiti_core/graphiti.py:17-100`, `graphiti_core/nodes.py:17-49`):

1. Stdlib (`asyncio`, `os`, `re`, `logging`, `datetime`, `abc`, `enum`, `typing`, `uuid`).
2. Third-party (`pydantic`, `neo4j`, `httpx`, `tenacity`, `numpy`, `dotenv`, `typing_extensions`).
3. First-party `graphiti_core.*` (absolute imports — relative `..` imports only used in `llm_client/client.py` for sibling modules).

**Path Aliases:** None. Absolute imports rooted at `graphiti_core.*`.

**TYPE_CHECKING guard:** use for import-cycle-prone type-only imports — pattern at `graphiti_core/driver/driver.py:34-45`.

## Error Handling

**Custom exception hierarchy** rooted at `GraphitiError` (`graphiti_core/errors.py`). Raise these for domain failures (missing node/edge, invalid group_id, invalid node label, entity-type attribute validation).

**Validation at trust boundaries:**
- `group_id` validated by `validate_group_id` (`graphiti_core/helpers.py`) — alphanumeric + dashes + underscores only; raises `GroupIdValidationError`.
- `node_labels` validated by `validate_node_labels` — pattern `^[A-Za-z_][A-Za-z0-9_]*$` (`SAFE_CYPHER_IDENTIFIER_PATTERN`, `helpers.py:35`). Validation runs both in Pydantic field validators AND at the DB-query build boundary (`get_entity_node_save_query`, `get_entity_node_save_bulk_query`, `node_search_filter_query_constructor`, `edge_search_filter_query_constructor`) so a caller that bypasses Pydantic still cannot inject Cypher. See `tests/test_node_label_security.py` and `tests/utils/search/test_search_security.py` for the contract.
- `fulltext_query` rejects invalid group_ids at the query boundary (`search_utils.py`).

**Retry strategy:** `tenacity` on LLM calls only. `_generate_response_with_retry` (`llm_client/client.py:120-141`): `stop_after_attempt(4)`, `wait_random_exponential(multiplier=10, min=5, max=120)`, retry on `is_server_or_retry_error` (5xx httpx, `RateLimitError`, `EmptyResponseError`, `JSONDecodeError`). `reraise=True`. Logged via `after` callback only when `attempt_number > 1`.

**External-call error classes:** `graphiti_core/llm_client/errors.py` — `EmptyResponseError`, `RateLimitError`, `RefusalError`. These trigger retry classification in `is_server_or_retry_error`.

**Logging over raising:** transient failures in providers are logged at `warning`/`error` and retried; persistent failures bubble up after bounded retries.

## Logging

**Framework:** stdlib `logging`. One module-level logger per file: `logger = logging.getLogger(__name__)` (e.g. `graphiti_core/nodes.py:51`, `graphiti_core/llm_client/client.py:59`, `graphiti_core/driver/neo4j_driver.py:57`, `graphiti_core/edges.py`, `graphiti_core/cross_encoder/*`).

**Patterns:**
- f-string interpolation in log calls (`logger.debug(f'Saved edge to Graph: {self.uuid}')`, `logger.warning(f'Retrying {retry_state.fn.__name__}...')`).
- `debug` for successful saves/deletes on graph entities (`edges.py:90,129,160,294,373,592,706,725`).
- `warning` for retried provider errors and partial degradation (`cross_encoder/gemini_reranker_client.py:134,142`, `embedder/gemini.py:157`).
- `error` for unrecoverable provider failures (`cross_encoder/openai_reranker_client.py:122`, `embedder/gemini.py:180`).

## Comments

**When to Comment:**
- "Why" comments for non-obvious workarounds, citing the failure mode. Strong pattern in this codebase — examples:
  - `llm_client/client.py:62-67` — why `EmptyResponseError` is treated as transient.
  - `pyproject.toml:32-36` — why `kuzu` is deprecated, why `redis<9` is pinned.
  - `helpers.py:42-55` — chunking density thresholds with concrete examples.
  - `conftest.py:4-5,10-11` — why sys.path manipulation and `collect_ignore_glob` exist.
- Sentinel versioning for idempotent side effects — `llm_client/client.py:181` (`<<graphiti.attr_extraction.preamble.v1>>`) with instruction to bump suffix when text changes.
- "What" comments are rare; prefer extracting a named helper (`_resolve_with_llm`, `_has_high_entropy`).

**Docstrings:** Triple-quoted, present on public methods of `Graphiti`, `LLMClient`, and abstract `_generate_response` (`client.py:143-151`). First line capitalized imperative (`graphiti.py:251,273,284,402,...`). Module-level Apache 2.0 license header on every `graphiti_core/*.py` and `tests/*.py` file — do not remove.

## Function Design

**Async-first:** All I/O (driver, LLM, embedder, cross-encoder) is `async def`. Public `Graphiti.*` methods are async. Pure helpers (`parse_db_date`, `lucene_sanitize`, `validate_group_id`) are sync.

**Size:** Tolerates long methods when orchestrating a multi-step pipeline (`Graphiti.add_episode`, `extract_nodes`, `extract_edges`). Prefers extracting `_private` helpers for testable units — see `node_operations.py` (`_collect_candidate_nodes`, `_resolve_with_llm`, `_extract_entity_summaries_batch`) and `dedup_helpers.py` (granular `_shingles`, `_minhash_signature`, `_jaccard_similarity`, `_lsh_bands`).

**Parameters:** Type-hinted. Optional config objects default to `None` and materialize inside the body: `def __init__(self, config: LLMConfig | None = None, ...)` (`client.py:76-78`, `openai.py:40-46`).

**Return Values:** Pydantic `BaseModel` result wrappers for public API (`AddEpisodeResults`, `AddBulkEpisodeResults`, `AddTripletResults` — `graphiti.py:114-140`). Tuples / lists of domain objects (`EntityNode`, `EntityEdge`) for internal flows. `dict[str, Any]` from LLM clients (`_generate_response` returns `dict[str, typing.Any]`).

## Module Design

**Exports:** explicit `__all__` in package `__init__.py` files (e.g. `graphiti_core/embedder/__init__.py`, `graphiti_core/llm_client/__init__.py`). `conftest.py` uses `__all__ = ['graph_driver', 'mock_embedder']`.

**Barrel Files:** `__init__.py` re-exports the public surface of each subpackage so callers do `from graphiti_core.nodes import EntityNode` not `from graphiti_core.nodes.nodes import EntityNode`.

**Dependency injection via `GraphitiClients`:** `graphiti_core/graphiti_types.py:26` defines a Pydantic `GraphitiClients` model bundling `driver`, `embedder`, `cross_encoder`, `llm_client`. Internal utils accept this bundle rather than a `Graphiti` instance, decoupling them from the orchestrator (`tests/utils/maintenance/test_bulk_utils.py:27-38`, `test_entity_extraction.py:33-49`).

**Provider strategy pattern:** each capability (LLM, embedder, cross-encoder, driver) has an abstract base + concrete per-provider classes under a sibling package:
- `graphiti_core/llm_client/{client,openai_client,anthropic_client,gemini_client,groq_client}.py`
- `graphiti_core/embedder/{client,openai,voyage,gemini,ollama,...}.py`
- `graphiti_core/driver/{driver,neo4j_driver,falkordb_driver,kuzu_driver,neptune_driver}.py`
- `graphiti_core/cross_encoder/{client,openai_reranker_client,gemini_reranker_client,bge_reranker_client}.py`

Provider selection happens in `Graphiti.__init__` / factories. Drivers further split per-provider operation classes: `graphiti_core/driver/neo4j/operations/*_ops.py` implementing the interfaces in `graphiti_core/driver/operations/*_ops.py`.

**Tracing hook:** `Tracer` abstraction (`graphiti_core/tracer.py`) with `NoOpTracer` default; injected via `set_tracer` on `LLMClient` (`client.py:94-96`). Optional OpenTelemetry support via `tracing` extra.

## Configuration

**Environment:**
- `python-dotenv` auto-loaded at module import (`load_dotenv()` at `helpers.py:33`, `driver.py:51`, `helpers_test.py:31`).
- Feature flags via env vars with defaults: `DISABLE_NEO4J`, `DISABLE_FALKORDB`, `DISABLE_KUZU`, `ENABLE_KUZU`, `DISABLE_NEPTUNE` gate driver registration in `tests/helpers_test.py:34-68`. `SEMAPHORE_LIMIT` (`helpers.py:38`, default 20) caps concurrent async work via `semaphore_gather`. `CHUNK_*` env vars control entity-extraction chunking.
- Secrets (API keys) read from env, never logged, never committed.

**MCP server config:** YAML-driven Pydantic schema (`mcp_server/src/config/schema.py` `GraphitiConfig`). Nested env-var overrides use double-underscore (e.g. `LLM__PROVIDER=anthropic`, `LLM__MODEL=...`) — see `mcp_server/tests/test_configuration.py:32-34`.

## Build / Format / Lint Commands

Run from the package directory (`./`, `server/`, or `mcp_server/`):

```bash
make format   # ruff isort fix + ruff format
make lint     # ruff check + pyright
make test     # pytest
make check    # all three
```

Core test target: `DISABLE_FALKORDB=1 DISABLE_KUZU=1 DISABLE_NEPTUNE=1 pytest -m "not integration"` (`Makefile:29`).

---

*Convention analysis: 2026-07-16*
