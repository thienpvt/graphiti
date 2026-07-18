"""Service tests for prepare_catalog_batch control-plane path (PLAN-02/03/04/06/20)."""

from __future__ import annotations

import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_common import CatalogErrorCode  # noqa: E402
from models.catalog_edges import CatalogEdgeItem  # noqa: E402
from models.catalog_entities import CatalogEntityItem  # noqa: E402
from models.catalog_prepare import PrepareCatalogBatchRequest  # noqa: E402
from services.catalog_identity import (  # noqa: E402
    batch_request_sha256,
    canonical_sha256,
    catalog_entity_uuid,
    catalog_prepared_plan_uuid,
    entity_canonical_payload,
    plan_token_digest,
)
from services.catalog_service import CatalogService  # noqa: E402
from services.catalog_store import CatalogStoreError  # noqa: E402

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-prepare-001'


def _entity(**overrides: Any) -> CatalogEntityItem:
    data = {
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
    data.update(overrides)
    return CatalogEntityItem.model_validate(data)


def _edge(**overrides: Any) -> CatalogEdgeItem:
    data = {
        'edge_type': 'ForeignKeyTo',
        'edge_key': 'FK::HR.EMPLOYEES->HR.DEPARTMENTS',
        'source_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'source_entity_type': 'Table',
        'target_graph_key': 'TABLE::FE::ORCL.HR.DEPARTMENTS',
        'target_entity_type': 'Table',
        'fact': 'employees.dept_id references departments.dept_id',
        'evidence': None,
        'attributes': {'on_delete': 'CASCADE'},
        'confidence': 0.9,
    }
    data.update(overrides)
    return CatalogEdgeItem.model_validate(data)


def _enabled_config(**overrides: Any) -> CatalogConfig:
    data = {
        'enabled': True,
        'uuid_namespace': str(FIXED_NS),
        'max_entities_per_batch': 500,
        'max_edges_per_batch': 2000,
        'max_provenance_links_per_batch': 5000,
        'plan_ttl_seconds': 3600,
        'max_prepared_payload_bytes': 4_194_304,
        'max_active_plans_per_group': 8,
        'prepared_chunk_bytes': 131_072,
    }
    data.update(overrides)
    return CatalogConfig(**data)


def _make_client(*, embed_side_effect=None):
    call_order: list[str] = []

    async def _embed(*args, **kwargs):
        _ = args, kwargs
        call_order.append('embed')
        if embed_side_effect is not None:
            raise embed_side_effect
        return [0.1, 0.2, 0.3]

    embedder = AsyncMock()
    embedder.create = AsyncMock(side_effect=_embed)

    tx = MagicMock()
    tx.run = AsyncMock(return_value=SimpleNamespace(data=AsyncMock(return_value=[])))

    @asynccontextmanager
    async def _transaction():
        call_order.append('transaction')
        yield tx

    driver = SimpleNamespace(
        provider=SimpleNamespace(value='neo4j'),
        transaction=_transaction,
        execute_query=AsyncMock(return_value=([], None, None)),
    )
    return SimpleNamespace(
        driver=driver,
        embedder=embedder,
        llm_client=MagicMock(),
        call_order=call_order,
        tx=tx,
    )


def _prepare_request(
    *,
    entities: list[CatalogEntityItem] | None = None,
    edges: list[CatalogEdgeItem] | None = None,
    request_sha256: str | None = None,
    catalog_sha256: str = 'a' * 64,
    batch_id: str = BATCH,
) -> PrepareCatalogBatchRequest:
    return PrepareCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=batch_id,
        entities=entities if entities is not None else [_entity()],
        edges=edges if edges is not None else [],
        provenance=None,
        request_sha256=request_sha256,
        catalog_sha256=catalog_sha256,
        atomic=True,
    )


def _wire_prepare(service: CatalogService, *, create_side_effect=None) -> None:
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.resolve_endpoint_typed = AsyncMock(  # type: ignore[method-assign]
        return_value=('missing_endpoint', None)
    )
    service._store.get_batch_status = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.ensure_plan_schema = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.create_prepared_plan_with_chunks = AsyncMock(  # type: ignore[method-assign]
        side_effect=create_side_effect or (lambda *a, **k: {'uuid': 'plan'})
    )
    # Domain write spies — must stay zero on prepare.
    service._store.upsert_entity_item = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_edge_item = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_source_episode = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_mentions_link = AsyncMock()  # type: ignore[method-assign]
    service._store.append_edge_episode = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_batch_status = AsyncMock()  # type: ignore[method-assign]
    service._store.claim_batch_status = AsyncMock()  # type: ignore[method-assign]
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()  # type: ignore[method-assign]


def _assert_zero_domain(service: CatalogService) -> None:
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_edge_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()
    cast(AsyncMock, service._store.append_edge_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_batch_status).assert_not_awaited()
    cast(AsyncMock, service._store.claim_batch_status).assert_not_awaited()
    cast(AsyncMock, service._store.ensure_uuid_uniqueness_constraints).assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_happy_path_receipt_and_full_artifact():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    department = _entity(
        graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    request = _prepare_request(entities=[_entity(), department], edges=[_edge()])
    expected_hash = batch_request_sha256(request)
    expected_plan_id = f'{request.batch_id}|{expected_hash}'
    expected_plan_uuid = catalog_prepared_plan_uuid(FIXED_NS, GROUP, expected_plan_id)

    resp = await service.prepare_catalog_batch(client=client, request=request)

    assert resp.error_code is None
    assert resp.plan_token
    assert len(resp.plan_token) >= 32
    assert resp.plan_uuid == expected_plan_uuid
    assert resp.request_sha256 == expected_hash
    assert resp.catalog_sha256 == request.catalog_sha256
    assert len(resp.artifact_sha256) == 64
    assert resp.entity_count == 2
    assert resp.edge_count == 1
    assert resp.projected_created == 3  # 2 entities + 1 edge
    assert resp.projected_updated == 0
    assert resp.projected_unchanged == 0
    assert 'embed' in client.call_order
    assert client.call_order.index('embed') < client.call_order.index('transaction')
    cast(AsyncMock, service._store.ensure_plan_schema).assert_awaited_once()
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_awaited_once()
    await_args = cast(AsyncMock, service._store.create_prepared_plan_with_chunks).await_args
    assert await_args is not None
    create_kwargs = await_args.kwargs
    plan = create_kwargs['plan']
    chunks = create_kwargs['chunks']
    assert plan['uuid'] == expected_plan_uuid
    assert plan['token_digest'] == plan_token_digest(resp.plan_token)
    assert plan['request_sha256'] == expected_hash
    assert plan['artifact_sha256'] == resp.artifact_sha256
    assert 'plan_token' not in plan
    assert plan['token_digest'] != resp.plan_token
    assert chunks and all('payload_b64' in c for c in chunks)
    dumped = resp.model_dump()
    assert 'membership' not in dumped
    assert 'embeddings' not in dumped
    assert 'payload' not in dumped
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_embedding_failure_zero_plan_and_domain_writes():
    client = _make_client(embed_side_effect=RuntimeError('embed down'))
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)

    resp = await service.prepare_catalog_batch(client=client, request=_prepare_request())

    assert resp.error_code == CatalogErrorCode.embedding_failed
    assert resp.plan_token == ''
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_not_awaited()
    cast(AsyncMock, service._store.ensure_plan_schema).assert_not_awaited()
    assert 'transaction' not in client.call_order
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_preflight_failure_before_embed_or_plan_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)

    resp = await service.prepare_catalog_batch(
        client=client,
        request=_prepare_request(request_sha256='b' * 64),
    )

    assert resp.error_code == CatalogErrorCode.content_hash_mismatch
    client.embedder.create.assert_not_awaited()
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_not_awaited()
    assert 'transaction' not in client.call_order
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_same_identity_conflict_no_second_token():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _conflict(*_a, **_k):
        raise CatalogStoreError(
            'prepared plan identity already exists',
            code='prepared_plan_conflict',
        )

    _wire_prepare(service, create_side_effect=_conflict)
    request = _prepare_request()

    resp = await service.prepare_catalog_batch(client=client, request=request)

    assert resp.error_code == CatalogErrorCode.prepared_plan_conflict
    assert resp.plan_token == ''
    assert resp.plan_uuid  # deterministic identity still reported
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_awaited_once()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_capacity_exceeded_maps_batch_limit():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _cap(*_a, **_k):
        raise CatalogStoreError('active prepared plans at capacity', code='batch_limit_exceeded')

    _wire_prepare(service, create_side_effect=_cap)

    resp = await service.prepare_catalog_batch(client=client, request=_prepare_request())

    assert resp.error_code == CatalogErrorCode.batch_limit_exceeded
    assert resp.plan_token == ''
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_payload_over_max_before_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config(max_prepared_payload_bytes=16))
    _wire_prepare(service)

    resp = await service.prepare_catalog_batch(client=client, request=_prepare_request())

    assert resp.error_code == CatalogErrorCode.batch_limit_exceeded
    assert 'payload' in (resp.error_message or '').lower()
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_not_awaited()
    # Embed may have run; plan write must not.
    assert 'transaction' not in client.call_order
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_mixed_projection_counts():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    existing_entity = _entity()
    eu = catalog_entity_uuid(
        FIXED_NS, GROUP, existing_entity.entity_type, existing_entity.graph_key
    )
    content = canonical_sha256(entity_canonical_payload(existing_entity))
    service._store.get_entity_by_uuid = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda *a, uuid=None, **k: (
            {
                'uuid': eu,
                'content_sha256': content,
                'labels': ['Entity', 'Table'],
                'entity_type': 'Table',
                'graph_key': existing_entity.graph_key,
                'name_raw': existing_entity.name_raw,
                'name_canonical': existing_entity.name_canonical,
            }
            if uuid == eu
            else None
        )
    )
    new_entity = _entity(
        graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    request = _prepare_request(entities=[existing_entity, new_entity], edges=[])

    resp = await service.prepare_catalog_batch(client=client, request=request)

    assert resp.error_code is None
    assert resp.projected_created == 1
    assert resp.projected_unchanged == 1
    assert resp.projected_updated == 0
    # Only the new entity embeds.
    assert client.embedder.create.await_count == 1
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_order_invariant_request_hash():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    a = _entity()
    b = _entity(
        graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    r1 = _prepare_request(entities=[a, b], batch_id='order-1')
    r2 = _prepare_request(entities=[b, a], batch_id='order-1')
    # Same batch_id + different entity order → same request_sha256 (sorted canonical).
    assert batch_request_sha256(r1) == batch_request_sha256(r2)

    resp1 = await service.prepare_catalog_batch(client=client, request=r1)
    # Reset create mock for second call identity conflict expected if same plan
    service._store.create_prepared_plan_with_chunks = AsyncMock(  # type: ignore[method-assign]
        side_effect=CatalogStoreError('exists', code='prepared_plan_conflict')
    )
    resp2 = await service.prepare_catalog_batch(client=client, request=r2)

    assert resp1.plan_uuid == resp2.plan_uuid
    assert resp1.request_sha256 == resp2.request_sha256


@pytest.mark.asyncio
async def test_prepare_logs_omit_raw_token(caplog: pytest.LogCaptureFixture):
    import logging

    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    request = _prepare_request()

    with caplog.at_level(logging.INFO):
        resp = await service.prepare_catalog_batch(client=client, request=request)

    assert resp.plan_token
    joined = ' '.join(r.getMessage() for r in caplog.records)
    assert resp.plan_token not in joined
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_shared_preflight_used_by_prepare_and_upsert():
    """Characterization: both paths share _prepare_batch_preflight authority."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    from models.catalog_batch import UpsertCatalogBatchRequest

    prepare_req = _prepare_request()
    upsert_req = UpsertCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH,
        entities=list(prepare_req.entities),
        edges=[],
        provenance=None,
        dry_run=True,
        catalog_sha256=prepare_req.catalog_sha256,
        atomic=True,
    )
    service._store.get_batch_status = AsyncMock(return_value=None)  # type: ignore[method-assign]

    pre_prepare = await service._prepare_batch_preflight(
        client=client, request=prepare_req, check_batch_status=False
    )
    pre_upsert = await service._prepare_batch_preflight(
        client=client, request=upsert_req, check_batch_status=True
    )
    assert pre_prepare.early_kind is None
    assert pre_upsert.early_kind is None
    assert pre_prepare.server_hash == pre_upsert.server_hash
    assert len(pre_prepare.entity_prepared) == len(pre_upsert.entity_prepared)
