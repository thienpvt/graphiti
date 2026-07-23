"""Stage A/B acceptance: native Ollama clean-room config + no generative LLM on prepare/commit.

P6-OLL-CONF-01 / P6-OLL-EMB-01. Unit only — no network, shell, Docker, or live Ollama.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from graphiti_core.embedder.ollama import OllamaEmbedder  # noqa: E402
from graphiti_core.embedder.openai import OpenAIEmbedder  # noqa: E402

from config.schema import (  # noqa: E402
    CatalogConfig,
    EmbedderConfig,
    EmbedderProvidersConfig,
    OllamaProviderConfig,
)
from models.catalog_common import PLAN_STATE_COMMITTED, PLAN_STATE_PREPARED  # noqa: E402
from models.catalog_entities import CatalogEntityItem  # noqa: E402
from models.catalog_prepare import (  # noqa: E402
    CommitPreparedCatalogBatchRequest,
    PrepareCatalogBatchRequest,
)
from services.catalog_identity import (  # noqa: E402
    CANONICALIZATION_VERSION,
    CATALOG_SCHEMA_VERSION,
    batch_request_sha256,
    catalog_entity_uuid,
    mint_plan_token,
    plan_token_digest,
)
from services.catalog_prepared_artifact import (  # noqa: E402
    PREPARED_ARTIFACT_SERIALIZATION_VERSION,
    artifact_sha256,
    chunk_artifact_bytes,
    serialize_prepared_artifact,
)
from services.catalog_service import CatalogService  # noqa: E402
from services.factories import EmbedderFactory  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / 'mcp_server' / 'config' / 'config-docker-neo4j.catalog-local.example.yaml'
MATERIALIZER_PATH = ROOT / 'scripts' / 'materialize_catalog_local_config.py'
NAMESPACE_TOKEN = '${GRAPHITI_CATALOG_UUID_NAMESPACE}'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'
QWEN_MODEL = 'qwen3-embedding:0.6b'
QWEN_DIM = 1024
OLLAMA_DEFAULT_URL = 'http://host.docker.internal:11434'


def _load_materializer():
    spec = importlib.util.spec_from_file_location('catalog_ollama_materializer', MATERIALIZER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_catalog_local_example_is_native_ollama_qwen3_1024() -> None:
    """P6-OLL-CONF-01: clean-room example is native Ollama qwen3 1024 authority."""
    raw = EXAMPLE.read_text(encoding='utf-8')
    assert raw.count(NAMESPACE_TOKEN) == 1
    assert 'OPENAI_EMBEDDER_API_KEY' not in raw

    doc = yaml.safe_load(raw)
    embedder = doc['embedder']
    assert embedder['provider'] == 'ollama'
    assert (
        embedder['model'] == QWEN_MODEL or embedder['model'] == f'${{EMBEDDER_MODEL:{QWEN_MODEL}}}'
    )
    # Accept bare 1024 or ${EMBEDDER_DIMENSIONS:1024}
    dims = embedder['dimensions']
    if isinstance(dims, int):
        assert dims == QWEN_DIM
    else:
        assert str(dims) in (str(QWEN_DIM), f'${{EMBEDDER_DIMENSIONS:{QWEN_DIM}}}')

    ollama = embedder['providers']['ollama']
    api_url = ollama['api_url']
    assert 'OLLAMA_EMBEDDER_API_URL' in str(api_url)
    assert OLLAMA_DEFAULT_URL in str(api_url)
    # api_key absent or empty expansion only — never required secret
    if 'api_key' in ollama:
        key = ollama['api_key']
        assert key in (None, '', '${OLLAMA_API_KEY:}', '${OLLAMA_API_KEY}')
    truncate = ollama.get('truncate', True)
    assert truncate is True or str(truncate) in (
        'true',
        '${OLLAMA_EMBEDDER_TRUNCATE:true}',
    )
    # Must not be openai embedder authority
    assert embedder['provider'] != 'openai'
    assert 'text-embedding-3-small' not in raw


def test_materializer_preserves_ollama_section_except_namespace(tmp_path: Path) -> None:
    """Materializer replaces only namespace token; Ollama keys stay byte-stable."""
    materializer = _load_materializer()
    source = EXAMPLE
    output = tmp_path / 'catalog-local.yaml'
    namespace = '12345678-1234-5678-9234-567812345678'
    materializer.materialize(source, output, namespace)

    source_text = source.read_text(encoding='utf-8').replace('\r\n', '\n').replace('\r', '\n')
    out_text = output.read_text(encoding='utf-8')
    expected = source_text.replace(NAMESPACE_TOKEN, namespace.lower())
    expected = re.sub(r'\n*\Z', '\n', expected)
    assert out_text == expected
    assert 'provider: "openai"' not in out_text.split('embedder:')[1].split('database:')[0]
    assert 'provider: "ollama"' in out_text or "provider: 'ollama'" in out_text
    assert QWEN_MODEL in out_text
    assert str(QWEN_DIM) in out_text
    assert NAMESPACE_TOKEN not in out_text


def test_materializer_output_has_no_raw_namespace_or_credentials_in_evidence_surface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """T-06-OLL-01: no credential literals; namespace only at token replacement site."""
    materializer = _load_materializer()
    source = EXAMPLE
    output = tmp_path / 'catalog-local.yaml'
    namespace = 'abcdef01-2345-6789-abcd-ef0123456789'
    materializer.materialize(source, output, namespace)

    out = output.read_text(encoding='utf-8')
    # YAML password/api_key keys must be env expansions only (not bare secrets).
    # Anchor to line start so ${OLLAMA_API_KEY:} default forms do not false-positive.
    assert re.search(r'(?im)^\s*(password|api_key):\s*[^$\s{\n]', out) is None
    # Exactly one occurrence of the namespace UUID (the replaced token site)
    assert out.count(namespace.lower()) == 1
    captured = capsys.readouterr()
    assert namespace not in captured.out + captured.err
    assert 'sk-' not in out


def test_factory_ollama_qwen3_creates_native_embedder_not_openai() -> None:
    """P6-OLL-EMB-01: provider=ollama + qwen3/1024 → OllamaEmbedder, not OpenAI."""
    client = EmbedderFactory.create(
        EmbedderConfig(
            provider='ollama',
            model=QWEN_MODEL,
            dimensions=QWEN_DIM,
            providers=EmbedderProvidersConfig(
                ollama=OllamaProviderConfig(
                    api_url=OLLAMA_DEFAULT_URL,
                    truncate=True,
                    timeout=60,
                )
            ),
        )
    )
    assert isinstance(client, OllamaEmbedder)
    assert not isinstance(client, OpenAIEmbedder)
    ollama = client
    assert ollama.config.embedding_model == QWEN_MODEL
    assert ollama.config.embedding_dim == QWEN_DIM
    assert ollama.config.api_key is None
    assert ollama.config.base_url == OLLAMA_DEFAULT_URL
    assert not ollama.config.base_url.rstrip('/').endswith('/v1')
    assert '/v1' not in ollama.config.base_url


def _entity() -> CatalogEntityItem:
    return CatalogEntityItem.model_validate(
        {
            'entity_type': 'Table',
            'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
            'name_raw': 'EMPLOYEES',
            'name_canonical': 'employees',
            'database_qualified_name': 'ORCL.HR.EMPLOYEES',
            'summary': 'Employee master table',
            'attributes': {'owner': 'HR'},
            'source_refs': [{'document_id': 'ddl.sql', 'page': 12, 'raw_text': 'CREATE TABLE'}],
            'confidence': 0.95,
        }
    )


def _enabled_config() -> CatalogConfig:
    return CatalogConfig(
        enabled=True,
        uuid_namespace=str(FIXED_NS),
        max_entities_per_batch=500,
        max_edges_per_batch=2000,
        max_provenance_links_per_batch=5000,
        plan_ttl_seconds=3600,
        max_prepared_payload_bytes=4_194_304,
        max_active_plans_per_group=8,
        prepared_chunk_bytes=131_072,
    )


def _ollama_client(*, dim: int = QWEN_DIM):
    """Client with native Ollama embedder mock returning dim-length vectors; spied LLM."""

    async def _embed(*args, **kwargs):
        _ = args, kwargs
        return [0.01] * dim

    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.create = AsyncMock(side_effect=_embed)
    embedder.create_batch = AsyncMock(side_effect=lambda texts: [[0.01] * dim for _ in texts])

    llm = MagicMock()
    llm.generate = AsyncMock()
    llm._generate = AsyncMock()
    llm.generate_response = AsyncMock()
    llm.chat = AsyncMock()
    llm.create = AsyncMock()

    tx = MagicMock()
    tx.run = AsyncMock(return_value=SimpleNamespace(data=AsyncMock(return_value=[])))

    @asynccontextmanager
    async def _transaction():
        yield tx

    driver = SimpleNamespace(
        provider=SimpleNamespace(value='neo4j'),
        transaction=_transaction,
        execute_query=AsyncMock(return_value=([], None, None)),
    )
    return SimpleNamespace(
        driver=driver,
        embedder=embedder,
        llm_client=llm,
        tx=tx,
    )


def _wire_prepare(service: CatalogService) -> None:
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.resolve_endpoint_typed = AsyncMock(  # type: ignore[method-assign]
        return_value=('missing_endpoint', None)
    )
    service._store.get_batch_status = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.ensure_plan_schema = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.create_prepared_plan_with_chunks = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'plan'}
    )
    service._store.upsert_entity_item = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_edge_item = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_source_episode = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_mentions_link = AsyncMock()  # type: ignore[method-assign]
    service._store.append_edge_episode = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_batch_status = AsyncMock()  # type: ignore[method-assign]
    service._store.claim_batch_status = AsyncMock()  # type: ignore[method-assign]
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()  # type: ignore[method-assign]


def _frozen_artifact(
    *, token: str, request_sha256: str = 'a' * 64, catalog_sha256: str = 'b' * 64
) -> tuple[bytes, str, list[dict[str, Any]], dict[str, Any]]:
    batch_id = 'batch-ollama-zero-llm'
    plan_id = f'{batch_id}|{request_sha256}'
    entity_item = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'ORCL.HR.EMPLOYEES',
        'summary': 'Employee master table',
        'attributes': {'owner': 'HR'},
        'source_refs': [],
        'confidence': 0.95,
    }
    entity_uuid = catalog_entity_uuid(
        FIXED_NS, GROUP, entity_item['entity_type'], entity_item['graph_key']
    )
    body = {
        'artifact_serialization_version': PREPARED_ARTIFACT_SERIALIZATION_VERSION,
        'canonicalization_version': CANONICALIZATION_VERSION,
        'identity_schema_version': 'catalog-v2',
        'catalog_schema_version': CATALOG_SCHEMA_VERSION,
        'group_id': GROUP,
        'batch_id': batch_id,
        'system_key': 'FE',
        'request_sha256': request_sha256,
        'catalog_sha256': catalog_sha256,
        'plan_id': plan_id,
        'membership': {
            'entities': [
                {
                    'uuid': entity_uuid,
                    'entity_type': 'Table',
                    'graph_key': entity_item['graph_key'],
                    'content_sha256': 'e' * 64,
                    'projected_status': 'created',
                    'name_embedding': [0.01] * QWEN_DIM,
                }
            ],
            'edges': [],
            'sources': [],
            'evidence_links': [],
        },
        'request_canonical': {
            'batch_id': batch_id,
            'entities': [entity_item],
            'edges': [],
            'sources': [],
            'evidence_links': [],
        },
        'counts': {
            'entities': 1,
            'edges': 0,
            'sources': 0,
            'evidence_links': 0,
            'created': 1,
            'updated': 0,
            'unchanged': 0,
        },
    }
    artifact_bytes = serialize_prepared_artifact(body)
    art_sha = artifact_sha256(artifact_bytes)
    chunks = chunk_artifact_bytes(artifact_bytes, chunk_size=131_072)
    root_meta = {
        'uuid': 'plan-uuid-ollama-001',
        'group_id': GROUP,
        'batch_id': batch_id,
        'plan_id': plan_id,
        'identity_schema_version': 'catalog-v2',
        'canonicalization_version': CANONICALIZATION_VERSION,
        'artifact_serialization_version': PREPARED_ARTIFACT_SERIALIZATION_VERSION,
        'request_sha256': request_sha256,
        'catalog_sha256': catalog_sha256,
        'artifact_sha256': art_sha,
        'chunk_count': len(chunks),
        'payload_bytes': len(artifact_bytes),
        'entity_count': 1,
        'edge_count': 0,
        'source_count': 0,
        'evidence_link_count': 0,
        'created_count': 1,
        'updated_count': 0,
        'unchanged_count': 0,
        'token_digest': plan_token_digest(token),
    }
    return artifact_bytes, art_sha, chunks, root_meta


def _wire_commit(
    service: CatalogService, *, root: dict[str, Any], chunks: list[dict[str, Any]]
) -> None:
    service._store.load_prepared_plan_by_token_digest = AsyncMock(  # type: ignore[method-assign]
        return_value=root
    )
    service._store.load_prepared_plan_chunks = AsyncMock(  # type: ignore[method-assign]
        return_value=list(chunks)
    )

    async def _default_cas(tx, **kwargs):
        _ = tx
        base = dict(root)
        base['state'] = kwargs.get('to_state')
        base['updated_at'] = kwargs.get('updated_at')
        return base

    service._store.cas_plan_state = AsyncMock(side_effect=_default_cas)  # type: ignore[method-assign]

    def _prep(**kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()  # type: ignore[method-assign]
    service._store.ensure_evidence_manifest_schema = AsyncMock()  # type: ignore[method-assign]
    service._store.ensure_plan_schema = AsyncMock()  # type: ignore[method-assign]
    service._store.create_prepared_plan_with_chunks = AsyncMock()  # type: ignore[method-assign]
    service._store.lock_prepared_plan_for_commit = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': root['uuid'],
            'group_id': root['group_id'],
            'state': 'COMMITTING',
            'locked': True,
        }
    )
    service._store.read_terminal_commit_snapshot = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.terminal_commit_agrees = AsyncMock(return_value=False)  # type: ignore[method-assign]

    async def _claim(tx, *, params):
        _ = tx
        return {
            'uuid': params.get('uuid'),
            'group_id': params.get('group_id'),
            'batch_id': params.get('batch_id'),
            'status': 'writing',
            'request_sha256': params.get('request_sha256'),
        }

    async def _upsert_status(tx, *, params):
        _ = tx
        return {
            'uuid': params.get('uuid'),
            'status': params.get('status') or 'committed',
            'request_sha256': params.get('request_sha256'),
        }

    service._store.claim_batch_status = AsyncMock(side_effect=_claim)  # type: ignore[method-assign]
    service._store.upsert_batch_status = AsyncMock(side_effect=_upsert_status)  # type: ignore[method-assign]
    service._store.upsert_entity_item = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': 'e1',
            'status': 'created',
            'content_sha256': 'e' * 64,
            'error_code': None,
        }
    )
    service._store.upsert_edge_item = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': 'r1',
            'status': 'created',
            'content_sha256': 'e' * 64,
            'error_code': None,
        }
    )
    service._store.upsert_source_episode = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': 's1',
            'status': 'created',
            'source_key': 'SRC',
            'content_sha256': 'e' * 64,
            'error_code': None,
        }
    )
    service._store.upsert_mentions_link = AsyncMock()  # type: ignore[method-assign]
    service._store.append_edge_episode = AsyncMock()  # type: ignore[method-assign]
    service._store.lock_provenance_targets = AsyncMock(return_value=[])  # type: ignore[method-assign]
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.write_evidence_links = AsyncMock(return_value=[])  # type: ignore[method-assign]
    service._store.write_manifest_root_and_chunks = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'manifest-1', 'manifest_sha256': 'a' * 64, 'chunk_count': 1}
    )
    service._store.prepare_entity_params = _prep  # type: ignore[method-assign]
    service._store.prepare_edge_params = _prep  # type: ignore[method-assign]
    service._store.prepare_source_episode_params = _prep  # type: ignore[method-assign]
    service._store.prepare_batch_status_params = _prep  # type: ignore[method-assign]
    service._store.prepare_evidence_link_params = _prep  # type: ignore[method-assign]
    service._store.prepare_manifest_root_params = _prep  # type: ignore[method-assign]
    service._store.prepare_manifest_chunk_params = _prep  # type: ignore[method-assign]


def _assert_llm_untouched(llm: Any) -> None:
    for name in ('generate', '_generate', 'generate_response', 'chat', 'create'):
        method = getattr(llm, name, None)
        if method is not None and hasattr(method, 'assert_not_called'):
            method.assert_not_called()
        if method is not None and hasattr(method, 'assert_not_awaited'):
            method.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_and_commit_paths_invoke_zero_generative_llm_calls() -> None:
    """P6-OLL-EMB-01 / D-14: prepare + commit make zero generative LLM calls under native Ollama."""
    client = _ollama_client(dim=QWEN_DIM)
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    request = PrepareCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id='batch-ollama-zero-llm',
        entities=[_entity()],
        edges=[],
        provenance=None,
        request_sha256=None,
        catalog_sha256='c' * 64,
        atomic=True,
    )

    # Patch generative LLM entrypoints on the concrete client module surface too
    with (
        patch.object(client.llm_client, 'generate', new=AsyncMock()) as gen_spy,
        patch.object(client.llm_client, 'generate_response', new=AsyncMock()) as gen_resp_spy,
        patch.object(client.llm_client, 'chat', new=AsyncMock()) as chat_spy,
    ):
        prepared = await service.prepare_catalog_batch(client=client, request=request)
        assert prepared.error_code is None, prepared.error_message
        cast(AsyncMock, client.embedder.create).assert_awaited()
        gen_spy.assert_not_awaited()
        gen_resp_spy.assert_not_awaited()
        chat_spy.assert_not_awaited()
        _assert_llm_untouched(client.llm_client)

        token = mint_plan_token()
        req_sha = prepared.request_sha256 or batch_request_sha256(request)
        _, art_sha, chunks, meta = _frozen_artifact(
            token=token,
            request_sha256=req_sha,
            catalog_sha256=prepared.catalog_sha256 or 'c' * 64,
        )
        now = datetime.now(timezone.utc)
        root = {
            **meta,
            'state': PLAN_STATE_PREPARED,
            'expires_at': now + timedelta(hours=1),
            'created_at': now - timedelta(minutes=5),
            'updated_at': now - timedelta(minutes=5),
            'committing_started_at': None,
            'artifact_sha256': art_sha,
        }
        _wire_commit(service, root=root, chunks=chunks)
        client.embedder.create.reset_mock()

        committed = await service.commit_prepared_catalog_batch(
            client=client,
            request=CommitPreparedCatalogBatchRequest(
                plan_token=token,
                expected_request_sha256=req_sha,
            ),
        )
        assert committed.error_code is None, committed.error_message
        assert committed.state == PLAN_STATE_COMMITTED
        cast(AsyncMock, client.embedder.create).assert_not_awaited()
        gen_spy.assert_not_awaited()
        gen_resp_spy.assert_not_awaited()
        chat_spy.assert_not_awaited()
        _assert_llm_untouched(client.llm_client)
