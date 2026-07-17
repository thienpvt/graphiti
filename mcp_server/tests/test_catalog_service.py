"""Unit tests for CatalogService.upsert_typed_entities (entity path)."""

from __future__ import annotations

import importlib
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_batch import (  # noqa: E402
    GetCatalogIngestStatusRequest,
    NestedProvenancePayload,
    UpsertCatalogBatchRequest,
)
from models.catalog_common import CatalogErrorCode  # noqa: E402
from models.catalog_edges import CatalogEdgeItem, UpsertTypedEdgesRequest  # noqa: E402
from models.catalog_entities import (  # noqa: E402
    CatalogEntityItem,
    ResolveEntityRef,
    ResolveTypedEntitiesRequest,
    UpsertTypedEntitiesRequest,
    VerifyCatalogBatchRequest,
    VerifyEdgeRef,
    VerifyEntityRef,
)
from services.catalog_identity import (  # noqa: E402
    canonical_sha256,
    catalog_batch_uuid,
    catalog_edge_uuid,
    catalog_entity_uuid,
)
from services.catalog_service import CatalogService  # noqa: E402

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-entity-001'
CATALOG_TOOL_NAMES = {
    'upsert_typed_entities',
    'upsert_typed_edges',
    'resolve_typed_entities',
    'verify_catalog_batch',
    'upsert_provenance',
    'get_catalog_ingest_status',
    'upsert_catalog_batch',
}
LEGACY_TOOL_NAMES = {
    'add_memory',
    'search_nodes',
    'search_memory_facts',
    'add_triplet',
    'get_entity_edge',
    'get_episodes',
    'get_episode_entities',
    'update_entity',
    'build_communities',
    'summarize_saga',
    'delete_episode',
    'delete_entity_edge',
    'clear_graph',
    'get_status',
}


def _mcp_server():
    """Lazy import MCP server module (avoids static missing-import diagnostics)."""
    return importlib.import_module('graphiti_mcp_server')


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


def _schema_execute_query(cypher: str, params=None, **kwargs):
    """Async-compatible schema DDL double: SHOW reports constraints present."""
    _ = params, kwargs
    text = (cypher or '').strip().upper()
    if 'SHOW CONSTRAINTS' in text:
        return (
            [
                {
                    'name': 'catalog_entity_identity_unique',
                    'type': 'NODE_PROPERTY_UNIQUENESS',
                    'entityType': 'NODE',
                    'labelsOrTypes': ['Entity'],
                    'properties': ['uuid', 'group_id'],
                },
                {
                    'name': 'catalog_relates_to_identity_unique',
                    'type': 'RELATIONSHIP_PROPERTY_UNIQUENESS',
                    'entityType': 'RELATIONSHIP',
                    'labelsOrTypes': ['RELATES_TO'],
                    'properties': ['uuid', 'group_id'],
                },
            ],
            None,
            None,
        )
    return ([], None, None)


def _make_client(
    *,
    provider: str = 'neo4j',
    embedder: AsyncMock | None = None,
    tx_side_effect=None,
):
    # Mirror GraphProvider.value without importing graphiti_core (editor pyright path).
    provider_enum = SimpleNamespace(value=provider)

    embedder = embedder or AsyncMock(return_value=[0.1, 0.2, 0.3])
    call_order: list[str] = []

    async def _embed(*args, **kwargs):
        _ = args, kwargs
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

    async def _execute_query(cypher: str, params=None, **kwargs):
        return _schema_execute_query(cypher, params=params, **kwargs)

    driver = SimpleNamespace(
        provider=provider_enum,
        transaction=_transaction,
        # Real async callable — product path never special-cases unittest.mock.
        execute_query=_execute_query,
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
async def test_entity_service_enforces_configured_limit_below_hard_max():
    client = _make_client()
    cfg = CatalogConfig(
        enabled=True,
        uuid_namespace=str(FIXED_NS),
        max_entities_per_batch=1,
    )
    service = CatalogService(catalog_config=cfg)
    request = _request([_entity(), _entity(graph_key='TABLE::HR.DEPARTMENTS')])
    resp = await service.upsert_typed_entities(client=client, request=request)
    assert all(r.error_code == CatalogErrorCode.batch_limit_exceeded for r in resp.results)
    assert 'embed' not in client.call_order
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
    service._ensure_schema = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request(dry_run=True))
    assert 'embed' in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_entity_item.assert_not_awaited()
    service._ensure_schema.assert_not_awaited()
    assert resp.dry_run is True
    # dry-run success states still report projected status
    assert resp.results[0].status in ('created', 'updated', 'unchanged')
    assert resp.results[0].uuid is not None


@pytest.mark.asyncio
async def test_entity_create_persists_request_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._ensure_schema = AsyncMock()
    captured: dict = {}

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
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
    service._ensure_schema.assert_awaited()


@pytest.mark.asyncio
async def test_entity_identity_name_raw_conflict_no_write():
    entity = _entity(name_raw='CHANGED')
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-batch',
        'labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'graph_key': entity.graph_key,
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_entity_item = AsyncMock()
    service._ensure_schema = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert any(r.error_code == CatalogErrorCode.deterministic_uuid_conflict for r in resp.results)
    service._store.upsert_entity_item.assert_not_awaited()
    service._ensure_schema.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_identical_hash_unchanged_leaves_batch_id():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
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
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
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

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
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

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
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
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'd' * 64,
        'batch_id': 'old',
        'labels': ['Entity', 'View'],  # wrong custom type
        'neo4j_labels': ['Entity', 'View'],
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

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([e1, e2]))
    assert [r.index for r in resp.results] == [0, 1]
    assert resp.results[0].graph_key == 'TABLE::A.T1'
    assert resp.results[1].graph_key == 'TABLE::A.T2'
    assert resp.results[0].uuid == catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::A.T1')
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
    resp = await service.upsert_typed_entities(client=client, request=_request([e1, e2]))
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
    resp = await service.upsert_typed_entities(client=client, request=_request([e1, e2]))
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
    server = _mcp_server()
    assert hasattr(server, 'upsert_typed_entities')
    assert callable(server.upsert_typed_entities)


# ---------------------------------------------------------------------------
# resolve_typed_entities (read-only)
# ---------------------------------------------------------------------------


def _resolve_request(entities=None, **kwargs):
    if entities is None:
        entities = [
            ResolveEntityRef(entity_type='Table', graph_key='TABLE::HR.EMPLOYEES'),
        ]
    return ResolveTypedEntitiesRequest(group_id=GROUP, entities=entities, **kwargs)


@pytest.mark.asyncio
async def test_resolve_feature_disabled_no_write_no_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    service._store.match_entities_for_resolve = AsyncMock()
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    assert any(
        getattr(r, 'error_code', None) == CatalogErrorCode.feature_disabled for r in resp.results
    )
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()
    service._store.match_entities_for_resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_non_neo4j_backend_unavailable():
    client = _make_client(provider='falkordb')
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock()
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    assert any(
        getattr(r, 'error_code', None) == CatalogErrorCode.backend_unavailable for r in resp.results
    )
    service._store.match_entities_for_resolve.assert_not_awaited()
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_missing_entity_reports_not_found():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(return_value=[])
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is False
    assert 'missing' in r0.anomalies or r0.status == 'missing'
    assert r0.uuid is None or r0.uuid == catalog_entity_uuid(
        FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES'
    )
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_found_entity_reports_fields_and_no_side_effects():
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    resolve_call: dict = {}

    async def _match_resolve(executor=None, **kwargs):
        _ = executor
        resolve_call.clear()
        resolve_call.update(kwargs)
        return [
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]

    service._store.match_entities_for_resolve = AsyncMock(side_effect=_match_resolve)
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert r0.uuid == ent_uuid
    assert r0.labels is not None and 'Table' in (r0.labels or [])
    assert r0.verified_type == 'Table'
    assert r0.content_sha256 == 'a' * 64
    assert r0.has_name_embedding is True
    assert r0.generic_duplicates == []
    assert r0.typed_duplicates == []
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()
    assert 'transaction' not in client.call_order
    # MATCH scoped to group_id + requested keys only (captured via side_effect, not optional mock)
    service._store.match_entities_for_resolve.assert_awaited()
    assert resolve_call.get('group_id') == GROUP
    assert 'TABLE::HR.EMPLOYEES' in (resolve_call.get('graph_keys') or [])


@pytest.mark.asyncio
async def test_resolve_generic_duplicate_and_typed_duplicate_and_uuid_mismatch():
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            # bare generic Entity with name=graph_key, no Table label
            {
                'uuid': 'generic-uuid-1',
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity'],
                'neo4j_labels': ['Entity'],
                'content_sha256': 'b' * 64,
                'has_name_embedding': False,
                'batch_id': None,
            },
            # typed node with wrong uuid
            {
                'uuid': 'wrong-uuid',
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'c' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            },
            # second typed duplicate
            {
                'uuid': expected_uuid,
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'd' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            },
        ]
    )
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert 'generic-uuid-1' in r0.generic_duplicates
    assert len(r0.typed_duplicates) >= 1
    assert any(
        a in r0.anomalies
        for a in (
            'generic_duplicate',
            'typed_duplicate',
            'uuid_mismatch',
            'missing_embedding',
            'wrong_type',
        )
    )
    assert 'uuid_mismatch' in r0.anomalies or any(
        u != expected_uuid for u in ([r0.uuid] if r0.uuid else []) + list(r0.typed_duplicates)
    )
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_wrong_custom_label_and_absent_embedding():
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'View'],
                'neo4j_labels': ['Entity', 'View'],
                'content_sha256': 'e' * 64,
                'has_name_embedding': False,
                'batch_id': BATCH,
            }
        ]
    )
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert 'wrong_type' in r0.anomalies or r0.verified_type != 'Table'
    assert 'missing_embedding' in r0.anomalies or r0.has_name_embedding is False
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_expected_plus_extra_label_is_wrong_type():
    """Entity+Table+View is not typed Table — exact custom label contract."""
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'Table', 'View'],
                'neo4j_labels': ['Entity', 'Table', 'View'],
                'content_sha256': 'f' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]
    )
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert r0.status == 'wrong_type'
    assert 'wrong_type' in r0.anomalies
    assert r0.verified_type == 'View'
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_expected_plus_extra_label_is_wrong_type():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    key = 'TABLE::HR.EMPLOYEES'
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key),
                'graph_key': key,
                'name': key,
                'labels': ['Entity', 'Table', 'View'],
                'neo4j_labels': ['Entity', 'Table', 'View'],
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    req = _verify_request(
        entities=[VerifyEntityRef(entity_type='Table', graph_key=key)],
        edges=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert key in resp.entities.wrong_type
    assert key not in (resp.entities.typed_duplicate or [])


@pytest.mark.asyncio
async def test_resolve_mixed_twin_aggregates_all_row_anomalies():
    """Typed expected + rogue typed + wrong-type sibling: report every anomaly."""
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            {
                'uuid': expected_uuid,
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            },
            {
                'uuid': 'rogue-typed-uuid',
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'b' * 64,
                'has_name_embedding': False,
                'batch_id': BATCH,
            },
            {
                'uuid': 'wrong-type-uuid',
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'View'],
                'neo4j_labels': ['Entity', 'View'],
                'content_sha256': 'c' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            },
        ]
    )
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert r0.status == 'found'
    assert r0.uuid == expected_uuid
    assert 'typed_duplicate' in r0.anomalies
    assert 'uuid_mismatch' in r0.anomalies
    assert 'missing_embedding' in r0.anomalies
    assert 'wrong_type' in r0.anomalies
    assert 'rogue-typed-uuid' in r0.typed_duplicates
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_never_opens_write_transaction():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(return_value=[])
    service._store.upsert_entity_item = AsyncMock()
    service._ensure_schema = AsyncMock()
    await service.resolve_typed_entities(client=client, request=_resolve_request())
    service._store.upsert_entity_item.assert_not_awaited()
    service._ensure_schema.assert_not_awaited()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_mcp_tool_resolve_typed_entities_registered():
    server = _mcp_server()
    assert hasattr(server, 'resolve_typed_entities')
    assert callable(server.resolve_typed_entities)


# ---------------------------------------------------------------------------
# verify_catalog_batch (read-only)
# ---------------------------------------------------------------------------


def _verify_request(**kwargs):
    data = {
        'group_id': GROUP,
        'batch_id': BATCH,
        'entities': [
            VerifyEntityRef(entity_type='Table', graph_key='TABLE::HR.EMPLOYEES'),
        ],
        'edges': [
            VerifyEdgeRef(edge_type='Contains', edge_key='CONTAINS::HR.SCHEMA->HR.EMPLOYEES'),
        ],
        'require_provenance': False,
    }
    data.update(kwargs)
    return VerifyCatalogBatchRequest.model_validate(data)


@pytest.mark.asyncio
async def test_verify_feature_disabled_no_write_no_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    service._store.match_entities_for_verify = AsyncMock()
    service._store.match_edges_for_verify = AsyncMock()
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.feature_disabled
    service._store.match_entities_for_verify.assert_not_awaited()
    service._store.match_edges_for_verify.assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_non_neo4j_backend_unavailable():
    client = _make_client(provider='falkordb')
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock()
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.backend_unavailable
    service._store.match_entities_for_verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_batch_scoped_match_uses_group_and_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    ent_call: dict = {}
    edge_call: dict = {}

    async def _match_entities(executor=None, **kwargs):
        _ = executor
        ent_call.clear()
        ent_call.update(kwargs)
        return []

    async def _match_edges(executor=None, **kwargs):
        _ = executor
        edge_call.clear()
        edge_call.update(kwargs)
        return []

    service._store.match_entities_for_verify = AsyncMock(side_effect=_match_entities)
    service._store.match_edges_for_verify = AsyncMock(side_effect=_match_edges)
    await service.verify_catalog_batch(client=client, request=_verify_request())
    service._store.match_entities_for_verify.assert_awaited()
    service._store.match_edges_for_verify.assert_awaited()
    assert ent_call.get('group_id') == GROUP
    assert ent_call.get('batch_id') == BATCH
    assert edge_call.get('group_id') == GROUP
    assert edge_call.get('batch_id') == BATCH
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_entity_counts_and_anomaly_lists():
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': False,
                'batch_id': BATCH,
            },
            {
                'uuid': 'generic-1',
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity'],
                'neo4j_labels': ['Entity'],
                'content_sha256': 'b' * 64,
                'has_name_embedding': False,
                'batch_id': BATCH,
            },
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    req = _verify_request(
        entities=[
            VerifyEntityRef(entity_type='Table', graph_key='TABLE::HR.EMPLOYEES'),
            VerifyEntityRef(entity_type='View', graph_key='VIEW::HR.V1'),
        ],
        edges=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.entities.expected == 2
    assert resp.entities.found == 1
    assert 'VIEW::HR.V1' in resp.entities.missing
    assert 'TABLE::HR.EMPLOYEES' in resp.entities.generic_duplicate
    assert 'TABLE::HR.EMPLOYEES' in resp.entities.missing_embedding
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_entity_aggregates_anomalies_across_typed_twins():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    key = 'TABLE::HR.EMPLOYEES'
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key)
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': expected_uuid,
                'graph_key': key,
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'has_name_embedding': True,
            },
            {
                'uuid': str(uuid.uuid4()),
                'graph_key': key,
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'has_name_embedding': False,
            },
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(
            batch_id=None,
            entities=[VerifyEntityRef(entity_type='Table', graph_key=key)],
            edges=[],
        ),
    )
    assert resp.entities.found == 1
    assert resp.entities.typed_duplicate == [key]
    assert resp.entities.uuid_mismatch == [key]
    assert resp.entities.missing_embedding == [key]


@pytest.mark.asyncio
async def test_verify_entity_wrong_type_with_typed_present_is_reported():
    """Wrong-type sibling must surface even when exact typed rows exist."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    key = 'TABLE::HR.EMPLOYEES'
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key)
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': expected_uuid,
                'graph_key': key,
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'has_name_embedding': True,
            },
            {
                'uuid': str(uuid.uuid4()),
                'graph_key': key,
                'labels': ['Entity', 'View'],
                'neo4j_labels': ['Entity', 'View'],
                'has_name_embedding': True,
            },
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(
            batch_id=None,
            entities=[VerifyEntityRef(entity_type='Table', graph_key=key)],
            edges=[],
        ),
    )
    assert resp.entities.found == 1
    assert key in resp.entities.wrong_type
    assert {'kind': 'wrong_type', 'graph_key': key} in resp.anomalies


@pytest.mark.asyncio
async def test_verify_edge_counts_and_anomaly_lists():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': 'edge-1',
                'edge_key': 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES',
                'edge_type': 'Contains',
                'has_fact_embedding': False,
                'batch_id': BATCH,
            },
            {
                'uuid': 'edge-2',
                'edge_key': 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES',
                'edge_type': 'Contains',
                'has_fact_embedding': True,
                'batch_id': BATCH,
            },
        ]
    )
    req = _verify_request(
        entities=[],
        edges=[
            VerifyEdgeRef(edge_type='Contains', edge_key='CONTAINS::HR.SCHEMA->HR.EMPLOYEES'),
            VerifyEdgeRef(edge_type='DependsOn', edge_key='DEPENDS::MISSING'),
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.edges.expected == 2
    assert resp.edges.found == 1
    assert 'DEPENDS::MISSING' in resp.edges.missing
    assert 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES' in resp.edges.duplicate_edge_key
    assert 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES' in resp.edges.missing_embedding
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_edge_true_endpoint_mismatch_is_distinct_from_type():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', edge_key),
                'edge_key': edge_key,
                'edge_type': 'Contains',
                'source_uuid': str(uuid.uuid4()),
                'target_uuid': str(uuid.uuid4()),
                'source_graph_key': 'SCHEMA::WRONG',
                'target_graph_key': 'TABLE::HR.EMPLOYEES',
                'has_fact_embedding': True,
            }
        ]
    )
    req = _verify_request(
        batch_id=None,
        entities=[],
        edges=[
            VerifyEdgeRef(
                edge_type='Contains',
                edge_key=edge_key,
                expected_source_graph_key='SCHEMA::HR',
            )
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.edges.endpoint_mismatch == [edge_key]
    assert resp.edges.edge_type_mismatch == []
    assert {'kind': 'endpoint_mismatch', 'edge_key': edge_key} in resp.anomalies


@pytest.mark.asyncio
async def test_verify_edge_type_mismatch_never_becomes_endpoint_mismatch():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': 'stored-type-uuid',
                'edge_key': edge_key,
                'edge_type': 'DependsOn',
                'source_graph_key': 'SCHEMA::HR',
                'target_graph_key': 'TABLE::HR.EMPLOYEES',
                'has_fact_embedding': True,
            }
        ]
    )
    req = _verify_request(
        batch_id=None,
        entities=[],
        edges=[VerifyEdgeRef(edge_type='Contains', edge_key=edge_key)],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.edges.edge_type_mismatch == [edge_key]
    assert resp.edges.endpoint_mismatch == []
    assert {'kind': 'edge_type_mismatch', 'edge_key': edge_key} in resp.anomalies


@pytest.mark.asyncio
async def test_verify_edge_aggregates_anomalies_across_all_duplicate_rows_once():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    expected_uuid = catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', edge_key)
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': expected_uuid,
                'edge_key': edge_key,
                'edge_type': 'Contains',
                'source_graph_key': 'SCHEMA::HR',
                'has_fact_embedding': True,
            },
            {
                'uuid': 'rogue',
                'edge_key': edge_key,
                'edge_type': '',
                'source_graph_key': 'SCHEMA::WRONG',
                'has_fact_embedding': False,
            },
        ]
    )
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(
            batch_id=None,
            entities=[],
            edges=[
                VerifyEdgeRef(
                    edge_type='Contains',
                    edge_key=edge_key,
                    expected_source_graph_key='SCHEMA::HR',
                )
            ],
        ),
    )
    assert resp.edges.duplicate_edge_key == [edge_key]
    assert resp.edges.uuid_mismatch == [edge_key]
    assert resp.edges.edge_type_mismatch == [edge_key]
    assert resp.edges.endpoint_mismatch == [edge_key]
    assert resp.edges.missing_embedding == [edge_key]


@pytest.mark.asyncio
async def test_verify_provenance_read_failure_is_internal_error_not_missing():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    service._store.match_provenance_presence = AsyncMock(side_effect=RuntimeError('db down'))
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(require_provenance=True, entities=[], edges=[]),
    )
    assert resp.error_code == CatalogErrorCode.internal_error
    assert resp.error_message == 'verify provenance read failed'
    assert resp.missing_provenance == []


@pytest.mark.asyncio
async def test_verify_require_provenance_report_only_no_write():
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::HR.EMPLOYEES',
                'name': 'TABLE::HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    service._store.match_provenance_presence = AsyncMock(
        return_value=[{'uuid': ent_uuid, 'has_provenance': False}]
    )
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.verify_catalog_batch(
        client=client, request=_verify_request(require_provenance=True, edges=[])
    )
    assert resp.require_provenance is True
    assert ent_uuid in resp.missing_provenance
    service._store.match_provenance_presence.assert_awaited()
    service._store.upsert_entity_item.assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_never_embeds_or_writes():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    service._store.upsert_entity_item = AsyncMock()
    service._ensure_schema = AsyncMock()
    await service.verify_catalog_batch(client=client, request=_verify_request())
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()
    service._store.upsert_entity_item.assert_not_awaited()
    service._ensure_schema.assert_not_awaited()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_mcp_tool_verify_catalog_batch_registered():
    server = _mcp_server()
    assert hasattr(server, 'verify_catalog_batch')
    assert callable(server.verify_catalog_batch)


# ---------------------------------------------------------------------------
# upsert_typed_edges
# ---------------------------------------------------------------------------

EDGE_BATCH = 'batch-edge-001'


def _edge(**overrides) -> CatalogEdgeItem:
    data = {
        'edge_type': 'ForeignKeyTo',
        'edge_key': 'FK::HR.EMPLOYEES->HR.DEPARTMENTS',
        'source_graph_key': 'TABLE::HR.EMPLOYEES',
        'source_entity_type': 'Table',
        'target_graph_key': 'TABLE::HR.DEPARTMENTS',
        'target_entity_type': 'Table',
        'fact': 'employees.dept_id references departments.dept_id',
        'evidence': None,
        'attributes': {'on_delete': 'CASCADE'},
        'confidence': 0.9,
    }
    data.update(overrides)
    return CatalogEdgeItem.model_validate(data)


def _edge_request(
    edges: list[CatalogEdgeItem] | None = None,
    *,
    dry_run: bool = False,
    atomic: bool = True,
    batch_id: str = EDGE_BATCH,
    strict_endpoints: bool = True,
) -> UpsertTypedEdgesRequest:
    return UpsertTypedEdgesRequest(
        group_id=GROUP,
        batch_id=batch_id,
        edges=edges or [_edge()],
        dry_run=dry_run,
        atomic=atomic,
        strict_endpoints=strict_endpoints,
    )


def _typed_endpoint(uuid: str, graph_key: str, entity_type: str = 'Table') -> dict:
    return {
        'uuid': uuid,
        'name': graph_key,
        'graph_key': graph_key,
        'labels': ['Entity', entity_type],
        'neo4j_labels': ['Entity', entity_type],
        'group_id': GROUP,
    }


def _expected_entity_uuid(entity_type: str, graph_key: str) -> str:
    return catalog_entity_uuid(FIXED_NS, GROUP, entity_type, graph_key)


def _wire_ok_endpoints(
    service: CatalogService,
    src_uuid: str | None = None,
    tgt_uuid: str | None = None,
):
    src_uuid = src_uuid or _expected_entity_uuid('Table', 'TABLE::HR.EMPLOYEES')
    tgt_uuid = tgt_uuid or _expected_entity_uuid('Table', 'TABLE::HR.DEPARTMENTS')

    async def _resolve(
        executor,
        *,
        group_id,
        graph_key,
        entity_type,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, tx, expected_uuid, kwargs)
        if graph_key == 'TABLE::HR.EMPLOYEES':
            return None, _typed_endpoint(src_uuid, graph_key)
        if graph_key == 'TABLE::HR.DEPARTMENTS':
            return None, _typed_endpoint(tgt_uuid, graph_key)
        return 'missing_endpoint', None

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    return src_uuid, tgt_uuid


@pytest.mark.asyncio
async def test_edge_feature_disabled_returns_structured_error_without_write():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    service._store.resolve_endpoint_typed = AsyncMock()
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert any(r.error_code == CatalogErrorCode.feature_disabled for r in resp.results)
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order
    service._store.resolve_endpoint_typed.assert_not_awaited()
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_service_enforces_configured_limit_below_hard_max():
    client = _make_client()
    cfg = CatalogConfig(
        enabled=True,
        uuid_namespace=str(FIXED_NS),
        max_edges_per_batch=1,
    )
    service = CatalogService(catalog_config=cfg)
    request = _edge_request([_edge(), _edge(edge_key='FK::SECOND')])
    resp = await service.upsert_typed_edges(client=client, request=request)
    assert all(r.error_code == CatalogErrorCode.batch_limit_exceeded for r in resp.results)
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_edge_missing_endpoint_before_embed_no_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.resolve_endpoint_typed = AsyncMock(return_value=('missing_endpoint', None))
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert any(r.error_code == CatalogErrorCode.missing_endpoint for r in resp.results)
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_source_endpoint_read_failure_is_internal_error_not_missing():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.resolve_endpoint_typed = AsyncMock(side_effect=RuntimeError('db down'))
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert resp.results[0].error_code != CatalogErrorCode.missing_endpoint
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_target_endpoint_read_failure_is_internal_error_not_missing():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _resolve(
        executor,
        *,
        group_id=None,
        graph_key=None,
        entity_type=None,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, tx, expected_uuid, kwargs)
        assert graph_key is not None
        if graph_key == 'TABLE::HR.EMPLOYEES':
            return None, _typed_endpoint(_expected_entity_uuid('Table', graph_key), graph_key)
        raise RuntimeError('db down')

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert 'target' in (resp.results[0].error_message or '')
    assert 'embed' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_endpoint_read_failure_atomic_rolls_back_batch():
    e1 = _edge(edge_key='FK::A.T1->A.T2', fact='fk one')
    e2 = _edge(edge_key='FK::A.T3->A.T4', fact='fk two')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.resolve_endpoint_typed = AsyncMock(side_effect=RuntimeError('db down'))
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_edges(
        client=client, request=_edge_request([e1, e2], atomic=True)
    )
    assert resp.failed >= 1
    assert all(r.status in ('error', 'rolled_back') for r in resp.results)
    assert any(r.error_code == CatalogErrorCode.internal_error for r in resp.results)
    service._store.upsert_edge_item.assert_not_awaited()
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_edge_endpoint_type_mismatch_and_generic_conflict_no_create():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _resolve(
        executor, *, group_id=None, graph_key=None, entity_type=None, tx=None, **kwargs
    ):
        _ = (executor, group_id, entity_type, tx, kwargs)
        assert graph_key is not None
        if graph_key == 'TABLE::HR.EMPLOYEES':
            return 'endpoint_type_mismatch', {
                'uuid': 'wrong',
                'neo4j_labels': ['Entity', 'View'],
            }
        return 'generic_endpoint_conflict', {
            'uuid': 'gen',
            'neo4j_labels': ['Entity'],
        }

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    codes = {r.error_code for r in resp.results}
    assert CatalogErrorCode.endpoint_type_mismatch in codes or (
        CatalogErrorCode.generic_endpoint_conflict in codes
    )
    assert 'embed' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_embed_before_transaction_order():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock(
        return_value={
            'uuid': 'e1',
            'content_sha256': 'a' * 64,
            'batch_id': EDGE_BATCH,
            'status': 'created',
        }
    )
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert client.call_order.index('embed') < client.call_order.index('transaction')
    assert resp.results[0].status in ('created', 'updated', 'unchanged')


@pytest.mark.asyncio
async def test_edge_dry_run_embeds_but_never_writes_or_persists_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request(dry_run=True))
    assert 'embed' in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()
    assert resp.dry_run is True
    assert resp.results[0].status in ('created', 'updated', 'unchanged')
    assert resp.results[0].uuid is not None


@pytest.mark.asyncio
async def test_edge_create_persists_request_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    src, tgt = _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    captured: dict = {}

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        captured.update(params)
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert captured.get('batch_id') == EDGE_BATCH
    assert captured.get('source_uuid') == src
    assert captured.get('target_uuid') == tgt
    assert captured.get('name') == 'ForeignKeyTo'
    assert resp.results[0].status == 'created'
    assert resp.created == 1


@pytest.mark.asyncio
async def test_edge_identical_hash_unchanged_leaves_batch_id():
    edge = _edge()
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
    payload = CatalogService.edge_canonical_payload(edge)
    digest = canonical_sha256(payload)
    src, tgt = (
        _expected_entity_uuid('Table', 'TABLE::HR.EMPLOYEES'),
        _expected_entity_uuid('Table', 'TABLE::HR.DEPARTMENTS'),
    )
    existing = {
        'uuid': edge_uuid,
        'content_sha256': digest,
        'batch_id': 'prior-edge-batch',
        'name': edge.edge_type,
        'edge_key': edge.edge_key,
        'source_uuid': src,
        'target_uuid': tgt,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service, src, tgt)
    service._store.get_edge_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([edge]))
    assert resp.results[0].status == 'unchanged'
    assert resp.unchanged == 1
    service._store.upsert_edge_item.assert_not_awaited()
    assert resp.results[0].uuid == edge_uuid
    assert resp.results[0].content_sha256 == digest


@pytest.mark.asyncio
async def test_edge_changed_update_passes_request_batch_id():
    edge = _edge(fact='changed fact text about fk')
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
    src, tgt = (
        _expected_entity_uuid('Table', 'TABLE::HR.EMPLOYEES'),
        _expected_entity_uuid('Table', 'TABLE::HR.DEPARTMENTS'),
    )
    existing = {
        'uuid': edge_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-edge-batch',
        'name': edge.edge_type,
        'edge_key': edge.edge_key,
        'source_uuid': src,
        'target_uuid': tgt,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service, src, tgt)
    service._store.get_edge_by_uuid = AsyncMock(return_value=existing)
    captured: dict = {}

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        captured.update(params)
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'updated',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([edge]))
    assert resp.results[0].status == 'updated'
    assert captured.get('batch_id') == EDGE_BATCH


@pytest.mark.asyncio
async def test_edge_identity_conflict_no_mutation():
    edge = _edge()
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
    existing = {
        'uuid': edge_uuid,
        'content_sha256': 'c' * 64,
        'batch_id': 'old',
        'name': 'Contains',  # wrong type for same uuid
        'edge_key': edge.edge_key,
        'source_uuid': _expected_entity_uuid('Table', 'TABLE::HR.EMPLOYEES'),
        'target_uuid': _expected_entity_uuid('Table', 'TABLE::HR.DEPARTMENTS'),
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=existing)
    # use real store method for conflict detection
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([edge]))
    assert any(r.error_code == CatalogErrorCode.edge_identity_conflict for r in resp.results)
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_two_foreign_key_same_endpoints_different_keys():
    e1 = _edge(edge_key='FK::HR.EMPLOYEES.DEPT->HR.DEPARTMENTS')
    e2 = _edge(edge_key='FK::HR.EMPLOYEES.MGR_DEPT->HR.DEPARTMENTS', fact='mgr dept fk')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)

    def _upsert_side(tx, *, params):
        _ = tx
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    upsert = AsyncMock(side_effect=_upsert_side)
    service._store.upsert_edge_item = upsert
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([e1, e2]))
    assert upsert.await_count == 2
    assert resp.created == 2
    assert resp.results[0].uuid != resp.results[1].uuid
    assert resp.results[0].edge_key == e1.edge_key
    assert resp.results[1].edge_key == e2.edge_key


@pytest.mark.asyncio
async def test_edge_atomic_rollback_on_store_failure():
    e1 = _edge(edge_key='FK::A.T1->A.T2', fact='fk one')
    e2 = _edge(edge_key='FK::A.T3->A.T4', fact='fk two')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _resolve(
        executor,
        *,
        group_id=None,
        graph_key=None,
        entity_type=None,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, tx, expected_uuid, kwargs)
        assert graph_key is not None
        et = entity_type or 'Table'
        return None, _typed_endpoint(_expected_entity_uuid(et, graph_key), graph_key, et)

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        if params['edge_key'] == 'FK::A.T3->A.T4':
            raise RuntimeError('neo4j boom')
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(
        client=client, request=_edge_request([e1, e2], atomic=True)
    )
    statuses = [r.status for r in resp.results]
    assert 'error' in statuses
    assert 'rolled_back' in statuses
    assert resp.rolled_back >= 1
    err = next(r for r in resp.results if r.status == 'error')
    assert err.error_code in (
        CatalogErrorCode.neo4j_transaction_failed,
        CatalogErrorCode.internal_error,
    )


@pytest.mark.asyncio
async def test_edge_no_queue_or_llm_calls():
    client = _make_client()
    queue = MagicMock()
    queue.add_episode = AsyncMock()
    llm = MagicMock()
    llm.generate_response = AsyncMock()
    client.llm_client = llm
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': EDGE_BATCH,
            'status': 'created',
        }
    )
    await service.upsert_typed_edges(client=client, request=_edge_request())
    queue.add_episode.assert_not_awaited()
    llm.generate_response.assert_not_called()


@pytest.mark.asyncio
async def test_edge_preserves_input_order_and_deterministic_uuid():
    e1 = _edge(edge_key='FK::A.T1->A.T2', fact='one')
    e2 = _edge(edge_key='FK::A.T3->A.T4', fact='two')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _resolve(
        executor,
        *,
        group_id=None,
        graph_key=None,
        entity_type=None,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, tx, expected_uuid, kwargs)
        assert graph_key is not None
        et = entity_type or 'Table'
        return None, _typed_endpoint(_expected_entity_uuid(et, graph_key), graph_key, et)

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([e1, e2]))
    assert [r.index for r in resp.results] == [0, 1]
    assert resp.results[0].edge_key == e1.edge_key
    assert resp.results[1].edge_key == e2.edge_key
    assert resp.results[0].uuid == catalog_edge_uuid(FIXED_NS, GROUP, e1.edge_type, e1.edge_key)
    assert resp.results[0].content_sha256 is not None
    assert len(resp.results[0].content_sha256) == 64


@pytest.mark.asyncio
async def test_edge_empty_upsert_row_fails_not_created():
    """Empty upsert row must not report created (TOCTOU / failed MATCH)."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock(return_value={})
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.neo4j_transaction_failed
    assert resp.created == 0


@pytest.mark.asyncio
async def test_edge_prefers_db_status_when_present():
    """DB create-token status is authoritative when present."""
    edge = _edge(fact='changed fact text about fk')
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
    src, tgt = (
        _expected_entity_uuid('Table', 'TABLE::HR.EMPLOYEES'),
        _expected_entity_uuid('Table', 'TABLE::HR.DEPARTMENTS'),
    )
    existing = {
        'uuid': edge_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-edge-batch',
        'name': edge.edge_type,
        'edge_key': edge.edge_key,
        'source_uuid': src,
        'target_uuid': tgt,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service, src, tgt)
    service._store.get_edge_by_uuid = AsyncMock(return_value=existing)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'updated',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([edge]))
    assert resp.results[0].status == 'updated'
    assert resp.updated == 1


@pytest.mark.asyncio
async def test_edge_in_tx_endpoint_race_rolls_back():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    call_n = {'n': 0}

    async def _resolve(
        executor,
        *,
        group_id=None,
        graph_key=None,
        entity_type=None,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, expected_uuid, kwargs)
        assert graph_key is not None
        call_n['n'] += 1
        # Pre-tx resolves OK; in-tx (tx is not None) races to missing
        if tx is not None:
            return 'missing_endpoint', None
        et = entity_type or 'Table'
        return None, _typed_endpoint(_expected_entity_uuid(et, graph_key), graph_key, et)

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock(
        return_value={'uuid': 'x', 'content_sha256': 'a' * 64, 'batch_id': EDGE_BATCH}
    )
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.missing_endpoint
    service._store.upsert_edge_item.assert_not_awaited()
    assert call_n['n'] >= 3  # 2 pre-tx + at least 1 in-tx


@pytest.mark.asyncio
async def test_entity_empty_upsert_row_fails_not_created():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock(return_value={})
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.neo4j_transaction_failed
    assert resp.created == 0


@pytest.mark.asyncio
async def test_entity_prefers_db_status_when_present():
    entity = _entity(summary='Changed summary')
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-batch',
        'labels': ['Entity', 'Table'],
        'neo4j_labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'updated',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'updated'
    assert resp.updated == 1


@pytest.mark.asyncio
async def test_entity_falls_back_to_projected_when_db_status_absent():
    entity = _entity(summary='Changed summary')
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-batch',
        'labels': ['Entity', 'Table'],
        'neo4j_labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'updated'
    assert resp.updated == 1


@pytest.mark.asyncio
async def test_entity_pre_read_failure_fails_closed_not_create():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(side_effect=RuntimeError('db down'))
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert resp.created == 0
    service._store.upsert_entity_item.assert_not_awaited()
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_edge_pre_read_failure_fails_closed_not_create():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(side_effect=RuntimeError('db down'))
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert resp.created == 0
    service._store.upsert_edge_item.assert_not_awaited()
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_entity_exact_label_rejects_extra_custom_labels():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'd' * 64,
        'batch_id': 'old',
        'labels': ['Entity', 'Table', 'View'],
        'neo4j_labels': ['Entity', 'Table', 'View'],
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
async def test_entity_generic_only_is_type_conflict():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'd' * 64,
        'batch_id': 'old',
        'labels': ['Entity'],
        'neo4j_labels': ['Entity'],
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
async def test_entity_in_tx_label_race_rolls_back():
    entity = _entity()
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    call_n = {'n': 0}

    async def _get(executor=None, *, uuid=None, group_id=None, tx=None):
        _ = (executor, uuid, group_id)
        call_n['n'] += 1
        if tx is None:
            return None  # pre-read: absent
        # in-tx: raced into wrong-type entity
        return {
            'uuid': uuid,
            'labels': ['Entity', 'View'],
            'neo4j_labels': ['Entity', 'View'],
            'group_id': GROUP,
            'content_sha256': 'e' * 64,
        }

    service._store.get_entity_by_uuid = AsyncMock(side_effect=_get)
    service._store.upsert_entity_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': BATCH,
            'status': 'created',
        }
    )
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.entity_type_conflict
    service._store.upsert_entity_item.assert_not_awaited()
    assert call_n['n'] >= 2


@pytest.mark.asyncio
async def test_verify_edge_uuid_mismatch_reported():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': 'wrong-uuid-not-deterministic',
                'edge_key': edge_key,
                'edge_type': 'Contains',
                'has_fact_embedding': True,
                'batch_id': BATCH,
            },
        ]
    )
    req = _verify_request(
        entities=[],
        edges=[VerifyEdgeRef(edge_type='Contains', edge_key=edge_key)],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert edge_key in resp.edges.uuid_mismatch
    assert resp.edges.found == 1


@pytest.mark.asyncio
async def test_mcp_tool_upsert_typed_edges_registered():
    server = _mcp_server()
    assert hasattr(server, 'upsert_typed_edges')
    assert callable(server.upsert_typed_edges)


# ---------------------------------------------------------------------------
# Provenance service (Phase 2 PROV-01, PROV-03..06)
# ---------------------------------------------------------------------------

from models.catalog_provenance import (  # noqa: E402
    CatalogProvenanceEdgeTarget,
    CatalogProvenanceEntityTarget,
    CatalogSourceItem,
    UpsertProvenanceRequest,
)
from services.catalog_identity import catalog_mentions_uuid, catalog_source_uuid  # noqa: E402


def _source(**overrides) -> CatalogSourceItem:
    data = {
        'source_key': 'SRC::ddl.sql#employees',
        'reference_time': '2026-07-16T12:00:00Z',
        'attributes': {'doc': 'ddl.sql'},
        'metadata': None,
    }
    data.update(overrides)
    return CatalogSourceItem.model_validate(data)


def _prov_request(
    sources: list[CatalogSourceItem] | None = None,
    *,
    entity_targets: list[CatalogProvenanceEntityTarget] | None = None,
    edge_targets: list[CatalogProvenanceEdgeTarget] | None = None,
    dry_run: bool = False,
    atomic: bool = True,
    batch_id: str = 'batch-prov-001',
) -> UpsertProvenanceRequest:
    return UpsertProvenanceRequest(
        group_id=GROUP,
        batch_id=batch_id,
        sources=sources or [_source()],
        entity_targets=entity_targets
        or [CatalogProvenanceEntityTarget(entity_type='Table', graph_key='TABLE::HR.EMPLOYEES')],
        edge_targets=edge_targets or [],
        dry_run=dry_run,
        atomic=atomic,
    )


def _wire_provenance_store(service: CatalogService, *, missing_entity: bool = False):
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    src_uuid = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::ddl.sql#employees')

    async def _resolve(executor, *, group_id, graph_key, entity_type, expected_uuid=None, tx=None):
        _ = executor, group_id, entity_type, expected_uuid, tx
        if missing_entity:
            return 'missing_endpoint', None
        return None, {'uuid': ent_uuid, 'name': graph_key, 'neo4j_labels': ['Entity', 'Table']}

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=None)
    service._store.get_mentions_link = AsyncMock(return_value=None)
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock(return_value=None)
    service._store.upsert_source_episode = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': src_uuid, 'content_sha256': 'h', 'status': 'created'}
    )
    service._store.upsert_mentions_link = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'm1', 'status': 'created'}
    )
    service._store.append_edge_episode = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'e1', 'episodes': [src_uuid]}
    )
    service._store.prepare_source_episode_params = CatalogNeo4jStore().prepare_source_episode_params
    return src_uuid, ent_uuid


# late import for prepare helper wiring
from services.catalog_store import CatalogNeo4jStore  # noqa: E402


@pytest.mark.asyncio
async def test_provenance_happy_path_writes_source_and_mentions_no_embed():
    client = _make_client()
    queue = MagicMock()
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    src_uuid, ent_uuid = _wire_provenance_store(service)

    resp = await service.upsert_provenance(client=client, request=_prov_request())
    assert resp.failed == 0
    assert resp.created >= 1 or resp.updated >= 1 or resp.unchanged >= 0
    assert any(r.uuid == src_uuid for r in resp.results)
    cast(AsyncMock, service._store.upsert_source_episode).assert_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_awaited()
    # no embedder / queue / llm on provenance path
    assert 'embed' not in client.call_order
    client.embedder.create.assert_not_awaited()
    queue.assert_not_called()
    # MENTIONS uses deterministic uuid
    mentions_call = cast(AsyncMock, service._store.upsert_mentions_link).await_args
    assert mentions_call is not None
    call_kwargs = mentions_call.kwargs
    expected_men = catalog_mentions_uuid(FIXED_NS, GROUP, src_uuid, ent_uuid)
    assert call_kwargs['mentions_uuid'] == expected_men
    assert call_kwargs['entity_uuid'] == ent_uuid


@pytest.mark.asyncio
async def test_provenance_missing_target_fail_closed_no_writes():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_provenance_store(service, missing_entity=True)

    resp = await service.upsert_provenance(client=client, request=_prov_request())
    assert resp.failed >= 1
    assert any(r.error_code == CatalogErrorCode.provenance_target_missing for r in resp.results)
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()
    cast(AsyncMock, service._store.append_edge_episode).assert_not_awaited()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_provenance_dry_run_no_writes():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_provenance_store(service)

    resp = await service.upsert_provenance(client=client, request=_prov_request(dry_run=True))
    assert resp.dry_run is True
    assert resp.failed == 0
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_provenance_idempotent_unchanged_skips_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    src_uuid, ent_uuid = _wire_provenance_store(service)
    item = _source()
    digest = CatalogService.source_canonical_payload(item)
    sha = canonical_sha256(digest)
    service._store.get_source_episode_by_uuid = AsyncMock(
        return_value={
            'uuid': src_uuid,
            'content_sha256': sha,
            'source_key': item.source_key,
        }
    )
    service._store.get_mentions_link = AsyncMock(
        return_value={'uuid': catalog_mentions_uuid(FIXED_NS, GROUP, src_uuid, ent_uuid)}
    )

    resp = await service.upsert_provenance(client=client, request=_prov_request(sources=[item]))
    assert resp.failed == 0
    assert resp.unchanged >= 1
    assert all(r.status == 'unchanged' for r in resp.results)
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()


@pytest.mark.asyncio
async def test_provenance_feature_disabled_no_write():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    resp = await service.upsert_provenance(client=client, request=_prov_request())
    assert any(r.error_code == CatalogErrorCode.feature_disabled for r in resp.results)
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_mcp_tool_upsert_provenance_registered():
    server = _mcp_server()
    assert hasattr(server, 'upsert_provenance')
    assert callable(server.upsert_provenance)


# ------------------------------------------------------------------
# get_catalog_ingest_status (STAT-05/06)
# ------------------------------------------------------------------


def _status_request(batch_id: str = BATCH) -> GetCatalogIngestStatusRequest:
    return GetCatalogIngestStatusRequest(group_id=GROUP, batch_id=batch_id)


@pytest.mark.asyncio
async def test_status_found_maps_response_no_payload_fields():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    batch_uuid = catalog_batch_uuid(FIXED_NS, GROUP, BATCH)
    service._store.get_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': batch_uuid,
            'group_id': GROUP,
            'batch_id': BATCH,
            'status': 'committed',
            'request_sha256': 'a' * 64,
            'catalog_sha256': 'b' * 64,
            'entity_count': 2,
            'edge_count': 1,
            'provenance_count': 0,
            'error_summary': '',
            'created_at': '2026-07-17T00:00:00+00:00',
            'updated_at': '2026-07-17T00:01:00+00:00',
            'committed_at': '2026-07-17T00:01:00+00:00',
        }
    )
    resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp.group_id == GROUP
    assert resp.batch_id == BATCH
    assert resp.batch_uuid == batch_uuid
    assert resp.status == 'committed'
    assert resp.entity_count == 2
    assert resp.edge_count == 1
    assert resp.error_summary == ''
    # no payload / secret fields on response model
    dumped = resp.model_dump()
    for banned in ('payload', 'entities', 'edges', 'sources', 'api_key', 'password'):
        assert banned not in dumped
    get_status = cast(AsyncMock, service._store.get_batch_status)
    get_status.assert_awaited_once()
    status_call = get_status.await_args
    assert status_call is not None
    call_kwargs = status_call.kwargs
    assert call_kwargs['uuid'] == batch_uuid
    assert call_kwargs['group_id'] == GROUP
    # read-only: no write tx / embed
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_missing_returns_structured_not_found_no_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_batch_status = AsyncMock(return_value=None)
    resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp.group_id == GROUP
    assert resp.batch_id == BATCH
    assert resp.batch_uuid == catalog_batch_uuid(FIXED_NS, GROUP, BATCH)
    assert resp.error_code is not None
    assert resp.error_code in (
        CatalogErrorCode.validation_error,
        CatalogErrorCode.internal_error,
        CatalogErrorCode.provenance_target_missing,
    ) or resp.error_code.value in (
        'validation_error',
        'internal_error',
        'not_found',
        'batch_not_found',
        'provenance_target_missing',
    )
    # Prefer explicit not-found semantics when available (error_summary, no error_message field)
    assert resp.error_summary
    assert 'not' in resp.error_summary.lower() or 'missing' in resp.error_summary.lower()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order
    # get_batch_status still called (read)
    service._store.get_batch_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_status_reinit_new_service_reads_from_store():
    """Restart simulation: new CatalogService + same store still reads Neo4j state."""
    client = _make_client()
    store = CatalogNeo4jStore()
    batch_uuid = catalog_batch_uuid(FIXED_NS, GROUP, BATCH)
    row = {
        'uuid': batch_uuid,
        'group_id': GROUP,
        'batch_id': BATCH,
        'status': 'failed',
        'request_sha256': None,
        'catalog_sha256': None,
        'entity_count': 0,
        'edge_count': 0,
        'provenance_count': 0,
        'error_summary': 'neo4j transaction failed',
        'created_at': '2026-07-17T00:00:00+00:00',
        'updated_at': '2026-07-17T00:02:00+00:00',
        'committed_at': None,
    }
    store.get_batch_status = AsyncMock(return_value=row)  # type: ignore[method-assign]

    service_a = CatalogService(catalog_config=_enabled_config(), store=store)
    resp_a = await service_a.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp_a.status == 'failed'
    assert resp_a.error_summary == 'neo4j transaction failed'

    # New service instance (reinit) with same store/driver
    service_b = CatalogService(catalog_config=_enabled_config(), store=store)
    resp_b = await service_b.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp_b.status == 'failed'
    assert resp_b.batch_uuid == batch_uuid
    assert resp_b.error_summary == 'neo4j transaction failed'
    assert store.get_batch_status.await_count == 2
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_status_feature_disabled_no_store_read():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    service._store.get_batch_status = AsyncMock(return_value={'status': 'committed'})
    resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp.error_code == CatalogErrorCode.feature_disabled
    service._store.get_batch_status.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_status_no_queue_or_llm():
    client = _make_client()
    queue = MagicMock()
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    batch_uuid = catalog_batch_uuid(FIXED_NS, GROUP, BATCH)
    service._store.get_batch_status = AsyncMock(
        return_value={
            'uuid': batch_uuid,
            'group_id': GROUP,
            'batch_id': BATCH,
            'status': 'committed',
            'entity_count': 0,
            'edge_count': 0,
            'provenance_count': 0,
            'error_summary': '',
        }
    )
    await service.get_catalog_ingest_status(client=client, request=_status_request())
    queue.assert_not_called()
    client.llm_client.assert_not_called()
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_tool_get_catalog_ingest_status_registered():
    server = _mcp_server()
    assert hasattr(server, 'get_catalog_ingest_status')
    assert callable(server.get_catalog_ingest_status)


# ------------------------------------------------------------------
# upsert_catalog_batch preflight (BATC-03..05, BATC-09/10)
# ------------------------------------------------------------------

BATCH_ATOMIC = 'batch-atomic-001'


def _batch_request(
    *,
    entities: list[CatalogEntityItem] | None = None,
    edges: list[CatalogEdgeItem] | None = None,
    provenance: NestedProvenancePayload | None = None,
    dry_run: bool = False,
    request_sha256: str | None = None,
) -> UpsertCatalogBatchRequest:
    return UpsertCatalogBatchRequest(
        group_id=GROUP,
        batch_id=BATCH_ATOMIC,
        entities=entities if entities is not None else [_entity()],
        edges=edges if edges is not None else [],
        provenance=provenance,
        dry_run=dry_run,
        request_sha256=request_sha256,
    )


def _wire_batch_preflight(service: CatalogService) -> None:
    service._store.get_batch_status = AsyncMock(return_value=None)  # type: ignore[method-assign]

    async def _entity_by_uuid(executor, *, uuid, group_id, tx=None):
        _ = executor, group_id
        if tx is None:
            return None
        return None

    service._store.get_entity_by_uuid = AsyncMock(  # type: ignore[method-assign]
        side_effect=_entity_by_uuid
    )
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.resolve_endpoint_typed = AsyncMock(  # type: ignore[method-assign]
        return_value=('missing_endpoint', None)
    )
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock(  # type: ignore[method-assign]
        return_value=None
    )
    service._store.upsert_batch_status = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_entity_item = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_edge_item = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_source_episode = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_mentions_link = AsyncMock()  # type: ignore[method-assign]
    service._store.append_edge_episode = AsyncMock()  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_batch_dry_run_endpoint_union_no_writes_or_status():
    employee = _entity()
    department = _entity(
        graph_key='TABLE::HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    request = _batch_request(
        entities=[employee, department],
        edges=[_edge()],
        dry_run=True,
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.dry_run is True
    assert resp.status == 'validating'
    assert resp.failed == 0
    # Both edge endpoints came from the same-request union; no persisted lookup.
    cast(AsyncMock, service._store.resolve_endpoint_typed).assert_not_awaited()
    cast(AsyncMock, service._store.ensure_uuid_uniqueness_constraints).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_batch_status).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_edge_item).assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_rejects_caller_hash_mismatch_before_status_read_or_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(request_sha256='b' * 64),
    )

    assert resp.error_code == CatalogErrorCode.content_hash_mismatch
    cast(AsyncMock, service._store.get_batch_status).assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_committed_different_hash_returns_batch_conflict_before_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    service._store.get_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'status': 'committed', 'request_sha256': 'a' * 64}
    )

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(request_sha256='b' * 64),
    )

    assert resp.error_code == CatalogErrorCode.batch_conflict
    assert resp.failed >= 1
    assert 'embed' not in client.call_order
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_committed_same_hash_returns_unchanged_short_circuit():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    request = _batch_request()
    expected_hash = CatalogService.batch_request_sha256(request)
    service._store.get_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'status': 'committed', 'request_sha256': expected_hash}
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.status == 'committed'
    assert resp.error_code is None
    assert resp.entity_unchanged == len(request.entities)
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_missing_endpoint_preflight_stops_embedding():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    request = _batch_request(
        entities=[],
        edges=[_edge()],
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.error_code in (
        CatalogErrorCode.missing_endpoint,
        CatalogErrorCode.batch_conflict,
    )
    assert resp.failed >= 1
    assert cast(AsyncMock, service._store.resolve_endpoint_typed).await_count >= 1
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_divergent_duplicate_preflight_stops_embedding():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    request = _batch_request(
        entities=[_entity(summary='first'), _entity(summary='second')],
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.error_code == CatalogErrorCode.batch_conflict
    assert resp.failed == 2
    assert all(r.error_code == CatalogErrorCode.deterministic_uuid_conflict for r in resp.results)
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_collects_all_known_conflicts_before_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    service._store.resolve_endpoint_typed = AsyncMock(  # type: ignore[method-assign]
        return_value=('missing_endpoint', None)
    )
    request = _batch_request(
        entities=[_entity(summary='first'), _entity(summary='second')],
        edges=[_edge(edge_key='FK::ONE'), _edge(edge_key='FK::TWO', fact='second fk')],
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.failed >= 4
    assert {r.error_code for r in resp.results} >= {
        CatalogErrorCode.deterministic_uuid_conflict,
        CatalogErrorCode.missing_endpoint,
    }
    # Both edge items were examined; preflight did not stop at the first conflict.
    assert cast(AsyncMock, service._store.resolve_endpoint_typed).await_count == 4
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


# ------------------------------------------------------------------
# upsert_catalog_batch atomic write (BATC-06..08)
# ------------------------------------------------------------------


def _install_batch_write_mocks(service: CatalogService, client) -> list[str]:
    events: list[str] = []

    async def _entity_write(tx, *, entity_type, params):
        _ = tx, entity_type
        events.append('entity_write')
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'status': 'created',
        }

    async def _edge_write(tx, *, params):
        _ = tx
        events.append('edge_write')
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'status': 'created',
        }

    async def _status_write(tx, *, params):
        _ = tx
        events.append(f'status_{params["status"]}')
        return {'uuid': params['uuid'], 'status': params['status']}

    service._store.upsert_entity_item = AsyncMock(side_effect=_entity_write)  # type: ignore[method-assign]
    service._store.upsert_edge_item = AsyncMock(side_effect=_edge_write)  # type: ignore[method-assign]
    service._store.upsert_batch_status = AsyncMock(side_effect=_status_write)  # type: ignore[method-assign]
    original_create = client.embedder.create

    async def _embed(*args, **kwargs):
        events.append('embed')
        return await original_create(*args, **kwargs)

    client.embedder.create = AsyncMock(side_effect=_embed)
    return events


@pytest.mark.asyncio
async def test_batch_embedding_completes_before_single_domain_transaction():
    employee = _entity()
    department = _entity(
        graph_key='TABLE::HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(entities=[employee, department], edges=[_edge()]),
    )

    assert resp.status == 'committed'
    assert client.call_order.count('transaction') == 1
    assert events[:3] == ['embed', 'embed', 'embed']
    assert events[3:] == ['entity_write', 'entity_write', 'edge_write', 'status_committed']
    cast(AsyncMock, service._store.upsert_batch_status).assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_embedding_failure_opens_no_transaction_or_status():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    client.embedder.create = AsyncMock(side_effect=RuntimeError('embed unavailable'))

    resp = await service.upsert_catalog_batch(client=client, request=_batch_request())

    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode.embedding_failed
    assert 'transaction' not in client.call_order
    cast(AsyncMock, service._store.upsert_batch_status).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_domain_failure_rolls_back_then_writes_failed_status_separately():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)
    domain_calls = {'count': 0}

    @asynccontextmanager
    async def _transaction():
        domain_calls['count'] += 1
        client.call_order.append('transaction')
        try:
            yield client.tx
        except Exception:
            events.append('rollback')
            raise

    client.driver.transaction = _transaction
    service._store.upsert_entity_item = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError('secret payload must never escape')
    )

    resp = await service.upsert_catalog_batch(client=client, request=_batch_request())

    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode.neo4j_transaction_failed
    assert domain_calls['count'] == 2
    assert events.index('rollback') < events.index('status_failed')
    status_call = cast(AsyncMock, service._store.upsert_batch_status).await_args
    assert status_call is not None
    failed_params = status_call.kwargs['params']
    assert failed_params['status'] == 'failed'
    assert failed_params['error_summary'] == 'RuntimeError'
    assert 'secret payload' not in failed_params['error_summary']


@pytest.mark.asyncio
async def test_batch_failed_status_write_failure_preserves_original_error():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    _install_batch_write_mocks(service, client)
    service._store.upsert_entity_item = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError('domain failed')
    )
    service._store.upsert_batch_status = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError('status failed')
    )

    resp = await service.upsert_catalog_batch(client=client, request=_batch_request())

    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode.neo4j_transaction_failed
    assert resp.error_message == 'neo4j transaction failed'
    assert client.call_order.count('transaction') == 2


@pytest.mark.asyncio
async def test_batch_writes_edges_before_provenance_append_in_same_transaction():
    employee = _entity()
    department = _entity(
        graph_key='TABLE::HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    provenance = NestedProvenancePayload(
        sources=[_source()],
        edge_targets=[
            CatalogProvenanceEdgeTarget(
                edge_type='ForeignKeyTo',
                edge_key='FK::HR.EMPLOYEES->HR.DEPARTMENTS',
            )
        ],
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]

    async def _source_write(tx, *, params):
        _ = tx, params
        events.append('source_write')
        return {'uuid': params['uuid'], 'status': 'created'}

    async def _append(tx, *, edge_uuid, episode_uuid, group_id):
        _ = tx, group_id
        events.append('provenance_append')
        return {'uuid': edge_uuid, 'episodes': [episode_uuid]}

    service._store.upsert_source_episode = AsyncMock(side_effect=_source_write)  # type: ignore[method-assign]
    service._store.append_edge_episode = AsyncMock(side_effect=_append)  # type: ignore[method-assign]

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(
            entities=[employee, department],
            edges=[_edge()],
            provenance=provenance,
        ),
    )

    assert resp.status == 'committed'
    assert events.index('edge_write') < events.index('provenance_append')
    assert client.call_order.count('transaction') == 1


@pytest.mark.asyncio
async def test_mcp_tool_upsert_catalog_batch_registered():
    server = _mcp_server()
    assert hasattr(server, 'upsert_catalog_batch')
    assert callable(server.upsert_catalog_batch)


@pytest.mark.asyncio
async def test_mcp_registers_exactly_seven_catalog_tools_and_preserves_legacy_tools():
    server = _mcp_server()
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    registered_catalog = {name for name in names if name in CATALOG_TOOL_NAMES}

    assert registered_catalog == CATALOG_TOOL_NAMES
    assert LEGACY_TOOL_NAMES.issubset(names)
    assert len(names) == len(CATALOG_TOOL_NAMES | LEGACY_TOOL_NAMES) == 21

    schemas = {tool.name: tool.inputSchema for tool in tools if tool.name in CATALOG_TOOL_NAMES}
    assert schemas.keys() == CATALOG_TOOL_NAMES
    assert all(schema['type'] == 'object' for schema in schemas.values())
