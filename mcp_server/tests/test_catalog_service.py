"""Unit tests for CatalogService.upsert_typed_entities (entity path)."""

from __future__ import annotations

import logging
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_common import CatalogErrorCode  # noqa: E402
from models.catalog_entities import CatalogEntityItem, UpsertTypedEntitiesRequest  # noqa: E402
from services.catalog_identity import canonical_sha256, catalog_entity_uuid  # noqa: E402
from services.catalog_service import CatalogService  # noqa: E402

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-entity-001'


def _entity(**overrides) -> CatalogEntityItem:
    data = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'HR.EMPLOYEES',
        'summary': 'Employee master table',
        'attributes': {'owner': 'HR'},
        'source_refs': [{'doc': 'ddl.sql', 'line': 12}],
        'confidence': 0.95,
    }
    data.update(overrides)
    return CatalogEntityItem.model_validate(data)


def _request(
    entities: list[CatalogEntityItem] | None = None,
    *,
    dry_run: bool = False,
    atomic: bool = True,
    batch_id: str = BATCH,
) -> UpsertTypedEntitiesRequest:
    return UpsertTypedEntitiesRequest(
        group_id=GROUP,
        batch_id=batch_id,
        entities=entities or [_entity()],
        dry_run=dry_run,
        atomic=atomic,
    )


def _enabled_config() -> CatalogConfig:
    return CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))


def _disabled_config() -> CatalogConfig:
    return CatalogConfig(enabled=False, uuid_namespace=None)


def _make_client(
    *,
    provider: str = 'neo4j',
    embedder: AsyncMock | None = None,
    tx_side_effect=None,
    existing: dict | None = None,
):
    from graphiti_core.driver.driver import GraphProvider

    provider_enum = {
        'neo4j': GraphProvider.NEO4J,
        'falkordb': GraphProvider.FALKORDB,
    }.get(provider, GraphProvider.NEO4J)

    embedder = embedder or AsyncMock(return_value=[0.1, 0.2, 0.3])
    call_order: list[str] = []

    async def _embed(*args, **kwargs):
        call_order.append('embed')
        return [0.1, 0.2, 0.3]

    embedder.create = AsyncMock(side_effect=_embed)
    embedder.create_batch = AsyncMock(side_effect=lambda inputs: [[0.1, 0.2]] * len(inputs))

    tx = MagicMock()
    tx.run = AsyncMock(
        return_value=SimpleNamespace(
            data=AsyncMock(
                return_value=[
                    {
                        'uuid': 'u1',
                        'content_sha256': 'h1',
                        'batch_id': BATCH,
                        'status': 'created',
                    }
                ]
            )
        )
    )

    @asynccontextmanager
    async def _transaction():
        call_order.append('transaction')
        if tx_side_effect is not None:
            raise tx_side_effect
        yield tx

    driver = SimpleNamespace(
        provider=provider_enum,
        transaction=_transaction,
        execute_query=AsyncMock(return_value=([], None, None)),
    )

    client = SimpleNamespace(
        driver=driver,
        embedder=embedder,
        llm_client=MagicMock(),
        call_order=call_order,
        tx=tx,
    )
    return client


@pytest.mark.asyncio
async def test_entity_feature_disabled_returns_structured_error_without_write():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert resp.failed >= 1 or any(
        r.error_code == CatalogErrorCode.feature_disabled for r in resp.results
    )
    assert all(r.status in ('error', 'rolled_back') for r in resp.results)
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_entity_invalid_uuid_namespace_when_enabled_without_valid_ns():
    # Construct config that claims enabled but namespace invalid via object mutation
    cfg = CatalogConfig(enabled=False, uuid_namespace=None)
    # Bypass pydantic after construction for gate testing
    object.__setattr__(cfg, 'enabled', True)
    object.__setattr__(cfg, 'uuid_namespace', 'not-a-uuid')
    client = _make_client()
    service = CatalogService(catalog_config=cfg)
    resp = await service.upsert_typed_entities(client=client, request=_request())
    codes = {r.error_code for r in resp.results}
    assert CatalogErrorCode.invalid_uuid_namespace in codes or (
        resp.failed >= 1
        and any(
            r.error_code
            in (CatalogErrorCode.invalid_uuid_namespace, CatalogErrorCode.feature_disabled)
            for r in resp.results
        )
    )
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_entity_non_neo4j_backend_unavailable():
    client = _make_client(provider='falkordb')
    service = CatalogService(catalog_config=_enabled_config())
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert any(r.error_code == CatalogErrorCode.backend_unavailable for r in resp.results)
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_entity_embed_before_transaction_order():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    # No existing node -> create path
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert client.call_order.index('embed') < client.call_order.index('transaction')
    assert resp.created >= 1 or resp.results[0].status in ('created', 'updated', 'unchanged')


@pytest.mark.asyncio
async def test_entity_dry_run_embeds_but_never_writes_or_persists_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(
        client=client, request=_request(dry_run=True)
    )
    assert 'embed' in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_entity_item.assert_not_awaited()
    assert resp.dry_run is True
    # dry-run success states still report projected status
    assert resp.results[0].status in ('created', 'updated', 'unchanged')
    assert resp.results[0].uuid is not None


@pytest.mark.asyncio
async def test_entity_create_persists_request_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    captured: dict = {}

    async def _upsert(tx, *, entity_type, params):
        captured.update(params)
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert captured.get('batch_id') == BATCH
    assert resp.results[0].status == 'created'
    assert resp.created == 1


@pytest.mark.asyncio
async def test_entity_identical_hash_unchanged_leaves_batch_id():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(
        FIXED_NS, GROUP, entity.entity_type, entity.graph_key
    )
    payload = CatalogService.entity_canonical_payload(entity)
    digest = canonical_sha256(payload)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': digest,
        'batch_id': 'prior-batch',
        'labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'unchanged'
    assert resp.unchanged == 1
    # identical: no write of new batch_id
    service._store.upsert_entity_item.assert_not_awaited()
    assert resp.results[0].uuid == ent_uuid
    assert resp.results[0].content_sha256 == digest


@pytest.mark.asyncio
async def test_entity_changed_update_passes_request_batch_id():
    entity = _entity(summary='Changed summary')
    ent_uuid = catalog_entity_uuid(
        FIXED_NS, GROUP, entity.entity_type, entity.graph_key
    )
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-batch',
        'labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    captured: dict = {}

    async def _upsert(tx, *, entity_type, params):
        captured.update(params)
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'updated',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'updated'
    assert captured.get('batch_id') == BATCH


@pytest.mark.asyncio
async def test_entity_atomic_rollback_on_store_failure():
    e1 = _entity(graph_key='TABLE::A.T1', database_qualified_name='A.T1', name_raw='T1')
    e2 = _entity(graph_key='TABLE::A.T2', database_qualified_name='A.T2', name_raw='T2')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type, params):
        if params['graph_key'] == 'TABLE::A.T2':
            raise RuntimeError('neo4j boom')
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(
        client=client, request=_request([e1, e2], atomic=True)
    )
    statuses = [r.status for r in resp.results]
    assert 'error' in statuses
    assert 'rolled_back' in statuses
    assert resp.rolled_back >= 1
    assert resp.failed >= 1
    # trigger error is structured, not raw exception dump as sole message ideally
    err = next(r for r in resp.results if r.status == 'error')
    assert err.error_code in (
        CatalogErrorCode.neo4j_transaction_failed,
        CatalogErrorCode.internal_error,
    )


@pytest.mark.asyncio
async def test_entity_content_hash_mismatch():
    entity = _entity(content_sha256='c' * 64)
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert any(r.error_code == CatalogErrorCode.content_hash_mismatch for r in resp.results)
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_entity_entity_type_conflict_no_mutation():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(
        FIXED_NS, GROUP, entity.entity_type, entity.graph_key
    )
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'd' * 64,
        'batch_id': 'old',
        'labels': ['Entity', 'View'],  # wrong custom type
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert any(r.error_code == CatalogErrorCode.entity_type_conflict for r in resp.results)
    service._store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_no_queue_or_llm_calls():
    client = _make_client()
    queue = MagicMock()
    queue.add_episode = AsyncMock()
    llm = MagicMock()
    llm.generate_response = AsyncMock()
    client.llm_client = llm
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': BATCH,
            'status': 'created',
        }
    )
    await service.upsert_typed_entities(client=client, request=_request())
    queue.add_episode.assert_not_awaited()
    llm.generate_response.assert_not_called()


@pytest.mark.asyncio
async def test_entity_logs_batch_id_and_counts_only(caplog):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': BATCH,
            'status': 'created',
        }
    )
    with caplog.at_level(logging.INFO):
        await service.upsert_typed_entities(client=client, request=_request())
    joined = ' '.join(r.message for r in caplog.records)
    assert BATCH in joined
    # Must not log full summary/payload
    assert 'Employee master table' not in joined
    assert 'ddl.sql' not in joined


@pytest.mark.asyncio
async def test_entity_preserves_input_order_and_deterministic_uuid():
    e1 = _entity(graph_key='TABLE::A.T1', database_qualified_name='A.T1', name_raw='T1')
    e2 = _entity(graph_key='TABLE::A.T2', database_qualified_name='A.T2', name_raw='T2')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type, params):
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(
        client=client, request=_request([e1, e2])
    )
    assert [r.index for r in resp.results] == [0, 1]
    assert resp.results[0].graph_key == 'TABLE::A.T1'
    assert resp.results[1].graph_key == 'TABLE::A.T2'
    assert resp.results[0].uuid == catalog_entity_uuid(
        FIXED_NS, GROUP, 'Table', 'TABLE::A.T1'
    )
    assert resp.results[0].content_sha256 is not None
    assert len(resp.results[0].content_sha256) == 64


@pytest.mark.asyncio
async def test_entity_coalesce_same_identity_same_hash():
    e1 = _entity()
    e2 = _entity()  # identical
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    upsert = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': BATCH,
            'status': 'created',
        }
    )
    service._store.upsert_entity_item = upsert
    resp = await service.upsert_typed_entities(
        client=client, request=_request([e1, e2])
    )
    # One physical write, two results
    assert upsert.await_count == 1
    assert len(resp.results) == 2
    assert resp.results[0].uuid == resp.results[1].uuid


@pytest.mark.asyncio
async def test_entity_same_identity_different_hash_is_conflict():
    e1 = _entity(summary='A')
    e2 = _entity(summary='B')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(
        client=client, request=_request([e1, e2])
    )
    assert any(
        r.error_code
        in (
            CatalogErrorCode.deterministic_uuid_conflict,
            CatalogErrorCode.batch_conflict,
        )
        for r in resp.results
    )
    service._store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_tool_upsert_typed_entities_registered():
    import graphiti_mcp_server as server

    assert hasattr(server, 'upsert_typed_entities')
    assert callable(server.upsert_typed_entities)
