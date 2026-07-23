"""Tests for Ollama's native embedding client."""

import json

import httpx
import pytest

from graphiti_core.embedder.ollama import (
    DEFAULT_BASE_URL,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    OllamaEmbedder,
    OllamaEmbedderConfig,
)


def embedding(value: float, dimension: int = 3) -> list[float]:
    return [value] * dimension


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_default_config() -> None:
    config = OllamaEmbedderConfig()

    assert config.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert config.embedding_dim == DEFAULT_EMBEDDING_DIM
    assert config.base_url == DEFAULT_BASE_URL
    assert config.api_key is None
    assert config.truncate is True
    assert config.keep_alive is None


@pytest.mark.asyncio
async def test_create_posts_native_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'embeddings': [embedding(0.1)]})

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(
            OllamaEmbedderConfig(
                embedding_model='nomic-embed-text', embedding_dim=3, base_url='http://ollama:11434/'
            ),
            client=client,
        )
        result = await embedder.create('test input')

    assert result == embedding(0.1)
    assert len(requests) == 1
    assert requests[0].url == httpx.URL('http://ollama:11434/api/embed')
    assert json.loads(requests[0].content) == {
        'model': 'nomic-embed-text',
        'input': ['test input'],
        'dimensions': 3,
        'truncate': True,
    }
    assert 'Authorization' not in requests[0].headers


@pytest.mark.asyncio
async def test_create_accepts_list_and_returns_first_embedding() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'embeddings': [embedding(0.1), embedding(0.2)]})

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3), client=client)
        result = await embedder.create(['first', 'second'])

    assert result == embedding(0.1)


@pytest.mark.asyncio
async def test_create_batch_uses_one_request_and_preserves_order() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert json.loads(request.content)['input'] == ['first', 'second', 'third']
        return httpx.Response(
            200,
            json={'embeddings': [embedding(0.1), embedding(0.2), embedding(0.3)]},
        )

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3), client=client)
        result = await embedder.create_batch(['first', 'second', 'third'])

    assert request_count == 1
    assert result == [embedding(0.1), embedding(0.2), embedding(0.3)]


@pytest.mark.asyncio
async def test_empty_batch_skips_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError('empty batch must not make a request')

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3), client=client)
        assert await embedder.create_batch([]) == []
        assert await embedder.create([]) == []


@pytest.mark.asyncio
async def test_optional_fields_and_auth_are_forwarded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers['Authorization'] == 'Bearer secret'
        assert json.loads(request.content) == {
            'model': DEFAULT_EMBEDDING_MODEL,
            'input': ['test'],
            'dimensions': 3,
            'truncate': False,
            'keep_alive': '5m',
        }
        return httpx.Response(200, json={'embeddings': [embedding(0.1)]})

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(
            OllamaEmbedderConfig(
                embedding_dim=3, api_key='secret', truncate=False, keep_alive='5m'
            ),
            client=client,
        )
        await embedder.create('test')


@pytest.mark.parametrize('input_data', [[1, 2], ['valid', 1], (value for value in [1])])
@pytest.mark.asyncio
async def test_rejects_non_text_input(input_data) -> None:
    embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3))

    with pytest.raises(TypeError, match='string or a list of strings'):
        await embedder.create(input_data)


@pytest.mark.asyncio
async def test_http_status_error_is_preserved() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={'error': 'model not found'})

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3), client=client)
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await embedder.create('test')

    assert exc_info.value.response.status_code == 404
    assert exc_info.value.response.json() == {'error': 'model not found'}


@pytest.mark.asyncio
async def test_owned_client_is_reused_and_closed() -> None:
    embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3))
    client = embedder.client

    assert client.is_closed is False
    assert embedder.client is client

    await embedder.close()
    await embedder.close()

    assert client.is_closed is True


@pytest.mark.asyncio
async def test_injected_client_is_not_closed() -> None:
    async with mock_client(
        lambda request: httpx.Response(200, json={'embeddings': [embedding(0.1)]})
    ) as client:
        embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3), client=client)
        await embedder.close()
        assert client.is_closed is False


@pytest.mark.asyncio
async def test_transport_error_is_preserved() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('unreachable', request=request)

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3), client=client)
        with pytest.raises(httpx.ConnectError, match='unreachable'):
            await embedder.create('test')


@pytest.mark.parametrize(
    ('response', 'error'),
    [
        (httpx.Response(200, text='not-json'), 'not valid JSON'),
        (httpx.Response(200, json={}), 'embeddings array'),
        (httpx.Response(200, json={'embeddings': []}), '0 embeddings for 1 inputs'),
        (httpx.Response(200, json={'embeddings': ['invalid']}), 'embedding must be an array'),
        (httpx.Response(200, json={'embeddings': [[0.1, 0.2]]}), 'dimension 2; expected 3'),
        (httpx.Response(200, json={'embeddings': [[0.1, True, 0.3]]}), 'finite numbers'),
        (
            httpx.Response(200, content=b'{"embeddings":[[0.1,Infinity,0.3]]}'),
            'finite numbers',
        ),
    ],
)
@pytest.mark.asyncio
async def test_rejects_malformed_response(response: httpx.Response, error: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(OllamaEmbedderConfig(embedding_dim=3), client=client)
        with pytest.raises(ValueError, match=error):
            await embedder.create('test')


@pytest.mark.asyncio
async def test_ollama_embed_request_body_model_dimensions_1024() -> None:
    """P6-OLL-EMB-01: qwen3-embedding:0.6b posts /api/embed with dimensions=1024."""
    requests: list[httpx.Request] = []
    dim = 1024
    model = 'qwen3-embedding:0.6b'

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'embeddings': [embedding(0.1, dim)]})

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(
            OllamaEmbedderConfig(
                embedding_model=model,
                embedding_dim=dim,
                base_url='http://host.docker.internal:11434',
            ),
            client=client,
        )
        result = await embedder.create('catalog entity name')

    assert len(result) == dim
    assert len(requests) == 1
    assert str(requests[0].url).endswith('/api/embed')
    body = json.loads(requests[0].content)
    assert body['model'] == model
    assert body['dimensions'] == dim
    assert body['input'] == ['catalog entity name']


@pytest.mark.asyncio
async def test_ollama_dimension_mismatch_fails_before_write() -> None:
    """P6-OLL-EMB-01: wrong-length embedding raises before any graph/driver call."""
    driver_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        # Server returns 3-d vector while config expects 1024
        return httpx.Response(200, json={'embeddings': [embedding(0.1, 3)]})

    async with mock_client(handler) as client:
        embedder = OllamaEmbedder(
            OllamaEmbedderConfig(
                embedding_model='qwen3-embedding:0.6b',
                embedding_dim=1024,
                base_url='http://host.docker.internal:11434',
            ),
            client=client,
        )
        with pytest.raises(ValueError, match='dimension 3; expected 1024'):
            await embedder.create('mismatch probe')
            driver_calls.append('would-write')  # unreachable on raise

    assert driver_calls == []
