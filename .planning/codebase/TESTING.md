# Testing Patterns

**Analysis Date:** 2026-07-16

## Test Framework

**Runner:**
- pytest `>=8.3.3` (core), `>=9.0.3` (server)
- Config: `pytest.ini` (root), `tests/evals/pytest.ini`, `mcp_server/pytest.ini`, `mcp_server/tests/pytest.ini`
- Also declared under `[tool.pytest.ini_options]` in `pyproject.toml:73-74` and `server/pyproject.toml:40-44`

**Async support:**
- `pytest-asyncio>=0.24.0`
- `asyncio_mode = auto` (`pytest.ini:5`) — no need for `@pytest.mark.asyncio` strictly, but the codebase still annotates it explicitly on every async test.
- `asyncio_default_fixture_loop_scope = function` (`pytest.ini:4`)

**Parallelism:**
- `pytest-xdist>=3.6.1` installed. Invoke with `pytest -n auto` when desired. Default `make test` does not enable it.

**Assertion Library:**
- Built-in `assert`. `numpy.allclose` for float embedding comparisons (`tests/helpers_test.py:271,286,311`).
- `pytest.raises(Exc, match='...')` for exception contracts (`tests/test_node_label_security.py:14`, `tests/utils/search/test_search_security.py:23`).

**Run Commands:**

```bash
# Core library — unit tests only (no live DB)
make test
# Equivalent:
DISABLE_FALKORDB=1 DISABLE_KUZU=1 DISABLE_NEPTUNE=1 uv run pytest -m "not integration"

# All tests including integration (requires Neo4j at bolt://localhost:7687)
uv run pytest

# Integration only
uv run pytest -m integration
# or by name:
uv run pytest tests/ -k "_int"

# Unit only by name
uv run pytest tests/ -k "not _int"

# Single file / method
uv run pytest tests/test_node_label_security.py
uv run pytest tests/llm_client/test_openai_client.py::test_resolve_reasoning_effort

# Parallel
uv run pytest -n auto -m "not integration"

# Server
cd server && make test   # uv run pytest

# MCP server
cd mcp_server && uv run pytest
# or the custom runner:
python mcp_server/tests/run_tests.py
```

## Test File Organization

**Location:** separate top-level `tests/` tree mirroring `graphiti_core/` package layout. Not co-located with source.

```
tests/
├── conftest.py (root — path setup + re-exports fixtures)
├── helpers_test.py          # shared fixtures + assertion helpers
├── test_*.py                # top-level Graphiti / security / text utils
├── test_*_int.py            # integration tests needing a live DB
├── cross_encoder/
│   ├── test_gemini_reranker_client.py
│   └── test_bge_reranker_client_int.py
├── driver/
│   └── test_falkordb_driver.py
├── embedder/
│   ├── embedder_fixtures.py
│   ├── test_openai.py
│   ├── test_gemini.py
│   ├── test_voyage.py
│   └── test_ollama.py
├── llm_client/
│   ├── test_client.py
│   ├── test_errors.py
│   ├── test_cache.py
│   ├── test_token_tracker.py
│   ├── test_openai_client.py
│   ├── test_openai_generic_client.py
│   ├── test_azure_openai_client.py
│   ├── test_anthropic_client.py
│   ├── test_anthropic_client_int.py
│   └── test_gemini_client.py
├── utils/
│   ├── test_concatenate_episodes.py
│   ├── test_content_chunking.py
│   ├── maintenance/
│   │   ├── test_bulk_utils.py
│   │   ├── test_edge_operations.py
│   │   ├── test_entity_extraction.py
│   │   ├── test_node_operations.py
│   │   └── test_attribute_utils.py
│   └── search/
│       ├── search_utils_test.py
│       ├── test_search_security.py
│       └── test_search_tracing.py
└── evals/                   # end-to-end evaluation scripts (not unit tests)
    ├── eval_e2e_graph_building.py
    ├── eval_cli.py
    ├── utils.py
    └── data/
```

**Server tests:** `server/tests/test_live_falkordb_int.py` only (live e2e).

**MCP server tests:** `mcp_server/tests/` — own suite with own `conftest.py`, `pytest.ini`, and `run_tests.py`. Root collection is blocked by `conftest.py:11` (`collect_ignore_glob = ['mcp_server/*']`).

**Naming:**
- Unit: `test_<module>.py` or `test_<feature>.py`
- Integration: `test_<feature>_int.py` **and** module-level `pytestmark = pytest.mark.integration` (see `tests/test_graphiti_int.py:28`)
- Helpers / fixtures: `helpers_test.py`, `*_fixtures.py`, `*_test.py` (e.g. `search_utils_test.py`)
- Functions: `test_<behavior>` (snake_case, descriptive of the contract)
- Classes: `Test*` grouping related cases (`TestExtractNodesSmallInput` in `test_entity_extraction.py:68`, `TestRateLimitError` in `test_errors.py:24`)

## Test Structure

**Suite Organization:**

```python
# Pattern A — free functions with fixtures (most common)
@pytest.mark.asyncio
async def test_create_calls_api_correctly(
    openai_embedder: OpenAIEmbedder,
    mock_openai_client: Any,
    mock_openai_response: MagicMock,
) -> None:
    mock_openai_client.embeddings.create.return_value = mock_openai_response
    result = await openai_embedder.create('Test input')
    mock_openai_client.embeddings.create.assert_called_once()
    _, kwargs = mock_openai_client.embeddings.create.call_args
    assert kwargs['model'] == DEFAULT_EMBEDDING_MODEL
    assert result == mock_openai_response.data[0].embedding[: openai_embedder.config.embedding_dim]


# Pattern B — class grouping for related pure-unit cases
class TestRateLimitError:
    def test_default_message(self):
        error = RateLimitError()
        assert error.message == 'Rate limit exceeded. Please try again later.'

    def test_custom_message(self):
        error = RateLimitError('Custom rate limit message')
        assert error.message == 'Custom rate limit message'


# Pattern C — parametrize for matrix coverage
@pytest.mark.parametrize(
    ('model', 'reasoning', 'expected'),
    [
        ('gpt-5.5', 'auto', 'none'),
        ('gpt-5', 'auto', 'minimal'),
        ('gpt-5.5', 'high', 'high'),
        ('gpt-5.5', None, None),
    ],
)
def test_resolve_reasoning_effort(model, reasoning, expected):
    assert OpenAIClient._resolve_reasoning_effort(model, reasoning) == expected
```

Sources: `tests/embedder/test_openai.py:77-96`, `tests/llm_client/test_errors.py:24-38`, `tests/llm_client/test_openai_client.py:51-71`.

**Patterns:**
- Setup: fixture injection preferred over inline setup. Local factories (`_make_clients()`, `_make_episode()`) for domain objects — see `tests/utils/maintenance/test_bulk_utils.py:14-38`, `test_entity_extraction.py:33-65`, `test_node_operations.py:35-61`.
- Teardown: async fixtures use `try/finally` to close drivers (`helpers_test.py:123-128`). Data is wiped via `clear_data` before yield.
- Assertion: plain `assert`. For floats use `np.allclose`. Domain equality helpers live in `helpers_test.py`: `assert_entity_node_equals`, `assert_entity_edge_equals`, `assert_episodic_node_equals`, `assert_episodic_edge_equals`, `assert_community_node_equals`.

## Markers

Registered in `pytest.ini:2-3`:

```ini
markers =
    integration: marks tests as integration tests
```

Server re-declares the same marker in `server/pyproject.toml:42-44` with a more specific description.

Module-level application:

```python
# tests/test_graphiti_int.py:28
pytestmark = pytest.mark.integration
```

Default `make test` filters them out with `-m "not integration"`.

## Mocking

**Framework:** `unittest.mock` (`Mock`, `MagicMock`, `AsyncMock`, `patch`). No third-party mocking library.

**Patterns:**

```python
# 1. Spec-bound Mock for abstract clients
@pytest.fixture
def mock_llm_client():
    mock_llm = Mock(spec=LLMClient)
    mock_llm.config = Mock()
    mock_llm.model = 'test-model'
    mock_llm.generate_response = Mock(return_value={...})
    return mock_llm

# 2. patch as context manager (sync + async targets)
with (
    patch('graphiti_core.search.search_utils.node_fulltext_search') as mock_fulltext,
    patch('graphiti_core.search.search_utils.node_similarity_search') as mock_sim,
):
    mock_fulltext.return_value = [...]
    results = await hybrid_node_search(...)

# 3. fixture that yields a patched SDK client
@pytest.fixture
def mock_openai_client() -> Generator[Any, Any, None]:
    with patch('openai.AsyncOpenAI') as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.embeddings = MagicMock()
        mock_instance.embeddings.create = AsyncMock()
        yield mock_instance

# 4. monkeypatch for internal helpers (preferred over patch for module attrs)
monkeypatch.setattr(bulk_utils, 'resolve_extracted_nodes', fake_resolve)
monkeypatch.setattr(
    'graphiti_core.utils.maintenance.node_operations._semantic_candidate_search',
    _semantic_candidates([[candidate]]),
)

# 5. GraphitiClients.model_construct to inject test doubles past Pydantic validation
clients = GraphitiClients.model_construct(
    driver=MagicMock(),
    embedder=MagicMock(),
    cross_encoder=MagicMock(),
    llm_client=llm_client,
)

# 6. Hand-rolled Dummy* classes when SDK surface is small
class DummyResponses:
    def __init__(self):
        self.parse_calls: list[dict] = []
    async def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return SimpleNamespace(output_text='{}')
```

Sources: `tests/test_graphiti_mock.py:72-95`, `tests/utils/search/search_utils_test.py:16-28`, `tests/embedder/test_openai.py:58-65`, `tests/utils/maintenance/test_bulk_utils.py:33-38,73`, `tests/llm_client/test_openai_client.py:11-40`.

**What to Mock:**
- External LLM / embedder / cross-encoder SDKs (`openai.AsyncOpenAI`, provider clients).
- Internal pure-logic boundaries that the unit under test depends on (`resolve_extracted_nodes`, `_semantic_candidate_search`).
- Graph drivers in pure-logic unit tests (use `MagicMock` / `AsyncMock`).

**What NOT to Mock:**
- Pydantic models and domain objects (`EntityNode`, `EntityEdge`, `EpisodicNode`) — construct real ones with `_make_*` factories.
- Validation logic and query builders under security tests — exercise the real path (`tests/test_node_label_security.py`, `tests/utils/search/test_search_security.py`).
- Live drivers in integration tests — use the real `graph_driver` fixture.

## Fixtures and Factories

**Shared fixtures** re-exported from root `conftest.py` via `tests/helpers_test.py`:

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `graph_driver` | function, parametrized over enabled providers | Live `GraphDriver` (Neo4j / FalkorDB / optional Kuzu / Neptune). Clears `group_id` + `group_id_2` data before yield; closes after. |
| `mock_embedder` | function | `Mock(spec=EmbedderClient)` with deterministic per-key embeddings from a module-level `embeddings` dict. |

Provider enablement is env-gated (`helpers_test.py:34-68`):

```
DISABLE_NEO4J unset  → Neo4j included (default bolt://localhost:7687)
DISABLE_FALKORDB unset → FalkorDB included
ENABLE_KUZU set + DISABLE_KUZU unset → Kuzu included (opt-in, deprecated)
DISABLE_NEPTUNE always forced True currently
```

Connection env vars (with defaults): `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USER`, `FALKORDB_PASSWORD`, `KUZU_DB`, `NEPTUNE_HOST`, `NEPTUNE_PORT`, `AOSS_HOST`.

**Local factories** (private helpers inside test modules):

```python
def _make_episode(uuid_suffix: str, group_id: str = 'group') -> EpisodicNode: ...
def _make_clients() -> GraphitiClients: ...   # returns model_construct doubles
def _make_clients() -> tuple[GraphitiClients, AsyncMock]:  # + llm_generate handle
```

**Embedder fixture helpers:** `tests/embedder/embedder_fixtures.py::create_embedding_values(multiplier=0.1, dimension=1536)`.

**Assertion helpers** (`tests/helpers_test.py:248-316`):

```python
await assert_entity_node_equals(graph_driver, retrieved, sample)
await assert_entity_edge_equals(graph_driver, retrieved, sample)
await assert_episodic_node_equals(retrieved, sample)
await assert_episodic_edge_equals(retrieved, sample)
await assert_community_node_equals(graph_driver, retrieved, sample)
await get_node_count(driver, uuids)   # COUNT query helper
await get_edge_count(driver, uuids)
```

These load embeddings from the graph before comparing with `np.allclose`.

**Test group IDs:** module constants `group_id = 'graphiti_test_group'`, `group_id_2 = 'graphiti_test_group_2'` (`helpers_test.py:85-86`). Use these so `clear_data` wipes only test partitions.

## Coverage

**Requirements:** None enforced. No `coverage` / `pytest-cov` dependency in `pyproject.toml`. No coverage gate in CI Makefile targets.

**View Coverage** (if installed ad-hoc):

```bash
uv run pytest --cov=graphiti_core --cov-report=term-missing -m "not integration"
```

## Test Types

**Unit Tests (default):**
- Pure logic, no network, no DB. Mock LLM/embedder/driver.
- Files: `tests/llm_client/test_*.py` (non-`_int`), `tests/embedder/test_*.py`, `tests/utils/**`, `tests/test_text_utils.py`, `tests/test_node_label_security.py`, `tests/test_graphiti_mock.py`, `tests/test_add_triplet.py`.
- Prefer free functions + fixtures; use classes for grouping pure exception/value contracts.

**Integration Tests (marker `integration`, suffix `_int`):**
- Require a live graph backend (`graph_driver` fixture). May skip specific providers:

```python
if graph_driver.provider == GraphProvider.FALKORDB:
    pytest.skip('Skipping as tests fail on Falkordb')
```

- Files: `tests/test_graphiti_int.py`, `tests/test_edge_int.py`, `tests/test_node_int.py`, `tests/test_entity_exclusion_int.py`, `tests/llm_client/test_anthropic_client_int.py`, `tests/cross_encoder/test_bge_reranker_client_int.py`, `server/tests/test_live_falkordb_int.py`, `mcp_server/tests/test_live_falkordb_int.py`.
- LLM-provider `_int` tests additionally need the corresponding API key.

**Security / Injection Tests:**
- Dedicated files: `tests/test_node_label_security.py`, `tests/utils/search/test_search_security.py`.
- Contract: both Pydantic validators AND query builders must reject Cypher-injection payloads (`Entity`) WITH n MATCH (x) DETACH DELETE x //`). Use `model_construct` to bypass Pydantic when testing the query-builder boundary.

**Evals:**
- `tests/evals/` — end-to-end graph-building evaluation scripts, not part of the unit/integration gate. Own `pytest.ini`.

**MCP Server Tests:**
- Isolated suite under `mcp_server/tests/`. Covers configuration, factories, transports (stdio/HTTP), stress/load, and live FalkorDB. Custom runner `mcp_server/tests/run_tests.py` with CLI flags (`--mock-llm`, etc.).

## Common Patterns

**Async Testing:**

```python
@pytest.mark.asyncio
async def test_close_releases_driver_and_embedder():
    graphiti = Graphiti.__new__(Graphiti)   # bypass __init__ when only testing one method
    graphiti.driver = Mock(close=AsyncMock())
    graphiti.embedder = Mock(close=AsyncMock())
    await graphiti.close()
    graphiti.driver.close.assert_awaited_once()
    graphiti.embedder.close.assert_awaited_once()
```

Source: `tests/test_graphiti_mock.py:98-107`. Prefer `assert_awaited_once` / `assert_awaited` for `AsyncMock`.

**Error Testing:**

```python
with pytest.raises(ValidationError, match='node_labels must start with a letter or underscore'):
    EntityNode(name='Alice', group_id='group', labels=['Entity`) DETACH DELETE x //'])

with pytest.raises(NodeLabelValidationError, match='node_labels must start with a letter or underscore'):
    get_entity_node_save_query(GraphProvider.NEO4J, 'Entity:Entity`) WITH n ...')

with pytest.raises(TypeError):
    RefusalError()  # type: ignore
```

Always pass `match=` when the message is part of the contract.

**Provider-parametrized integration:**

```python
# helpers_test.py:118
@pytest.fixture(params=drivers)
async def graph_driver(request):
    graph_driver = get_driver(request.param)
    await clear_data(graph_driver, [group_id, group_id_2])
    try:
        yield graph_driver
    finally:
        await graph_driver.close()
```

Any test that takes `graph_driver` as a parameter automatically runs once per enabled backend.

**Bypassing Pydantic for boundary tests:**

```python
# Test that the query builder still rejects bad labels even if Pydantic is skipped
filters = SearchFilters.model_construct(node_labels=['Entity`) DETACH DELETE x //'])
with pytest.raises(NodeLabelValidationError, match='...'):
    node_search_filter_query_constructor(filters, GraphProvider.NEO4J)
```

**Table-driven pure functions:**

```python
test_cases = [
    ('Hello World', 'Hello World'),
    ('Hello\x00World', 'HelloWorld'),
    ('Hello\u200bWorld', 'HelloWorld'),
]
for input_str, expected in test_cases:
    assert client._clean_input(input_str) == expected, f'Failed for input: {repr(input_str)}'
```

Source: `tests/llm_client/test_client.py:32-58`. Prefer `@pytest.mark.parametrize` for new code; the loop form is accepted for dense string-cleaning matrices.

**Direct-run entrypoint** (optional, common in this repo):

```python
if __name__ == '__main__':
    pytest.main(['-xvs', __file__])
```

Present in `tests/helpers_test.py:319-320`, `tests/embedder/test_openai.py:125-126`.

## Writing New Tests — Checklist

1. Place under `tests/` mirroring the source path (`graphiti_core/utils/maintenance/X.py` → `tests/utils/maintenance/test_X.py`).
2. Name unit files `test_*.py`; name integration files `test_*_int.py` and set `pytestmark = pytest.mark.integration`.
3. Prefer fixtures + `_make_*` factories over inline construction.
4. Mock external SDKs and LLM/embedder; construct real domain objects.
5. Use `pytest.raises(..., match=...)` for exception contracts.
6. For security boundaries: test both the Pydantic path and the `model_construct` bypass path.
7. Keep async tests marked `@pytest.mark.asyncio` even though `asyncio_mode = auto`.
8. Do not add tests under `mcp_server/` to the root suite — they have their own collection root.
9. Run `make test` (unit only) before opening a PR; integration requires a local Neo4j.

---

*Testing analysis: 2026-07-16*
