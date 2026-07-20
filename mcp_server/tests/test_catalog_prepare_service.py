"""Service tests for prepare/commit/discard control-plane (PLAN-02..12/17..19)."""

from __future__ import annotations

import base64
import json
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_common import (  # noqa: E402
    PLAN_STATE_COMMITTED,
    PLAN_STATE_COMMITTING,
    PLAN_STATE_DISCARDED,
    PLAN_STATE_EXPIRED,
    PLAN_STATE_PREPARED,
    CatalogErrorCode,
)
from models.catalog_edges import CatalogEdgeItem  # noqa: E402
from models.catalog_entities import CatalogEntityItem  # noqa: E402
from models.catalog_prepare import (  # noqa: E402
    CommitPreparedCatalogBatchRequest,
    DiscardPreparedCatalogBatchRequest,
    PrepareCatalogBatchRequest,
)
from services.catalog_identity import (  # noqa: E402
    CANONICALIZATION_VERSION,
    CATALOG_SCHEMA_VERSION,
    batch_request_sha256,
    canonical_sha256,
    catalog_entity_uuid,
    catalog_prepared_plan_uuid,
    entity_canonical_payload,
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
from services.catalog_store import CatalogStoreError  # noqa: E402

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-prepare-001'
PLAN_UUID = 'plan-uuid-fixed-001'
REQUEST_SHA = 'c' * 64
CATALOG_SHA = 'd' * 64


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
    """Prepare-path assertion: no domain writes during prepare receipt construction."""
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_edge_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()
    cast(AsyncMock, service._store.append_edge_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_batch_status).assert_not_awaited()
    cast(AsyncMock, service._store.claim_batch_status).assert_not_awaited()
    cast(AsyncMock, service._store.ensure_uuid_uniqueness_constraints).assert_not_awaited()


def _assert_zero_external(client: Any, queue: Any | None = None) -> None:
    client.embedder.create.assert_not_awaited()
    if getattr(client, 'llm_client', None) is not None:
        gen = getattr(client.llm_client, 'generate', None)
        if gen is not None:
            gen.assert_not_awaited()
    if queue is not None:
        queue.enqueue.assert_not_awaited()


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
        client=client, request=prepare_req, check_batch_status=True
    )
    pre_upsert = await service._prepare_batch_preflight(
        client=client, request=upsert_req, check_batch_status=True
    )
    assert pre_prepare.early_kind is None
    assert pre_upsert.early_kind is None
    assert pre_prepare.server_hash == pre_upsert.server_hash
    assert len(pre_prepare.entity_prepared) == len(pre_upsert.entity_prepared)


# ---------------------------------------------------------------------------
# Commit / discard claim-load seam (PLAN-07/10/11/12/17/18/19)
# ---------------------------------------------------------------------------


def _frozen_artifact(
    *,
    group_id: str = GROUP,
    batch_id: str = BATCH,
    request_sha256: str = REQUEST_SHA,
    catalog_sha256: str = CATALOG_SHA,
    plan_uuid: str = PLAN_UUID,
    entity_count: int = 1,
    edge_count: int = 0,
) -> tuple[bytes, str, list[dict[str, Any]], dict[str, Any]]:
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
        FIXED_NS, group_id, entity_item['entity_type'], entity_item['graph_key']
    )
    body = {
        'artifact_serialization_version': PREPARED_ARTIFACT_SERIALIZATION_VERSION,
        'canonicalization_version': CANONICALIZATION_VERSION,
        'identity_schema_version': 'catalog-v2',
        'catalog_schema_version': CATALOG_SCHEMA_VERSION,
        'group_id': group_id,
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
                    'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                    'content_sha256': 'e' * 64,
                    'projected_status': 'created',
                    'name_embedding': [0.1, 0.2],
                }
            ]
            if entity_count
            else [],
            'edges': [],
            'sources': [],
            'evidence_links': [],
        },
        'request_canonical': {
            'batch_id': batch_id,
            'entities': [entity_item] if entity_count else [],
            'edges': [],
            'sources': [],
            'evidence_links': [],
        },
        'counts': {
            'entities': entity_count,
            'edges': edge_count,
            'sources': 0,
            'evidence_links': 0,
            'created': entity_count,
            'updated': 0,
            'unchanged': 0,
        },
    }
    artifact_bytes = serialize_prepared_artifact(body)
    art_sha = artifact_sha256(artifact_bytes)
    chunks = chunk_artifact_bytes(artifact_bytes, chunk_size=131_072)
    root_meta = {
        'uuid': plan_uuid,
        'group_id': group_id,
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
        'entity_count': entity_count,
        'edge_count': edge_count,
        'source_count': 0,
        'evidence_link_count': 0,
        'created_count': entity_count,
        'updated_count': 0,
        'unchanged_count': 0,
    }
    return artifact_bytes, art_sha, chunks, root_meta


def _make_root(
    *,
    token: str,
    state: str = PLAN_STATE_PREPARED,
    expires_at: datetime | None = None,
    overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    _, art_sha, chunks, meta = _frozen_artifact()
    now = datetime.now(timezone.utc)
    root: dict[str, Any] = {
        **meta,
        'token_digest': plan_token_digest(token),
        'state': state,
        'expires_at': expires_at if expires_at is not None else now + timedelta(hours=1),
        'created_at': now - timedelta(minutes=5),
        'updated_at': now - timedelta(minutes=5),
        'committing_started_at': now if state == PLAN_STATE_COMMITTING else None,
    }
    if overrides:
        root.update(overrides)
    return root, chunks, art_sha


def _wire_commit(
    service: CatalogService,
    *,
    root: dict[str, Any] | None,
    chunks: list[dict[str, Any]] | None = None,
    cas_side_effect=None,
    cas_return: dict[str, Any] | None = None,
) -> None:
    service._store.load_prepared_plan_by_token_digest = AsyncMock(  # type: ignore[method-assign]
        return_value=root
    )
    service._store.load_prepared_plan_chunks = AsyncMock(  # type: ignore[method-assign]
        return_value=list(chunks or [])
    )

    async def _default_cas(tx, **kwargs):
        _ = tx
        to_state = kwargs.get('to_state')
        if cas_return is not None:
            return cas_return
        base = dict(root or {})
        base['state'] = to_state
        base['updated_at'] = kwargs.get('updated_at')
        if (
            to_state == PLAN_STATE_COMMITTING
            and root
            and root.get('state') == PLAN_STATE_COMMITTING
        ):
            base['reentry'] = True
        if to_state == PLAN_STATE_DISCARDED and root and root.get('state') == PLAN_STATE_DISCARDED:
            base['idempotent'] = True
        return base

    service._store.cas_plan_state = AsyncMock(  # type: ignore[method-assign]
        side_effect=cas_side_effect or _default_cas
    )

    # Schema/prepare spies. Success-path domain writes are stubbed for 03B-04 writer.
    # prepare_*_params: dict-pass-through (no new CatalogNeo4jStore import — root IDE noise).
    def _prep(**kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()  # type: ignore[method-assign]
    service._store.ensure_evidence_manifest_schema = AsyncMock()  # type: ignore[method-assign]
    service._store.ensure_plan_schema = AsyncMock()  # type: ignore[method-assign]
    service._store.create_prepared_plan_with_chunks = AsyncMock()  # type: ignore[method-assign]
    service._store.lock_prepared_plan_for_commit = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': (root or {}).get('uuid') or PLAN_UUID,
            'group_id': (root or {}).get('group_id') or GROUP,
            'state': PLAN_STATE_COMMITTING,
            'locked': True,
        }
    )
    service._store.read_terminal_commit_snapshot = AsyncMock(  # type: ignore[method-assign]
        return_value=None
    )
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


def _commit_client() -> SimpleNamespace:
    client = _make_client()
    client.llm_client = MagicMock()
    client.llm_client.generate = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_commit_happy_path_prepared_to_committing_zero_domain_external():
    token = mint_plan_token()
    root, chunks, art_sha = _make_root(token=token, state=PLAN_STATE_PREPARED)
    client = _commit_client()
    queue = MagicMock()
    queue.enqueue = AsyncMock()
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    _wire_commit(service, root=root, chunks=chunks)

    with patch(
        'services.catalog_service.plan_token_matches',
        wraps=__import__(
            'services.catalog_identity', fromlist=['plan_token_matches']
        ).plan_token_matches,
    ) as match_spy:
        resp = await service.commit_prepared_catalog_batch(
            client=client,
            request=CommitPreparedCatalogBatchRequest(plan_token=token),
        )

    assert resp.error_code is None
    # 03B-04: claim PREPARED→COMMITTING then success writer → COMMITTED
    assert resp.state == PLAN_STATE_COMMITTED
    assert resp.plan_uuid == root['uuid']
    assert resp.request_sha256 == root['request_sha256']
    assert resp.catalog_sha256 == root['catalog_sha256']
    assert resp.artifact_sha256 == art_sha
    assert resp.entity_count == 1
    assert resp.manifest_sha256
    assert resp.batch_uuid
    dumped = resp.model_dump()
    assert 'membership' not in dumped
    assert 'embeddings' not in dumped
    assert 'payload' not in dumped
    assert 'plan_token' not in dumped
    match_spy.assert_called()
    # raw token + stored digest
    called_token, called_digest = match_spy.call_args[0]
    assert called_token == token
    assert called_digest == root['token_digest']
    cas = cast(AsyncMock, service._store.cas_plan_state)
    cas.assert_awaited()
    # First CAS: PREPARED→COMMITTING claim; later CAS: COMMITTING→COMMITTED terminal.
    claim_calls = [
        c
        for c in cas.await_args_list
        if c.kwargs.get('to_state') == PLAN_STATE_COMMITTING
        and c.kwargs.get('expected_from') == PLAN_STATE_PREPARED
    ]
    commit_calls = [
        c
        for c in cas.await_args_list
        if c.kwargs.get('to_state') == PLAN_STATE_COMMITTED
        and c.kwargs.get('expected_from') == PLAN_STATE_COMMITTING
    ]
    assert claim_calls, 'expected PREPARED→COMMITTING claim CAS'
    assert commit_calls, 'expected COMMITTING→COMMITTED terminal CAS'
    assert claim_calls[0].kwargs.get('require_not_expired') is True
    client.embedder.create.assert_not_awaited()
    client.llm_client.generate.assert_not_awaited()
    queue.enqueue.assert_not_awaited()
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_not_awaited()
    # Domain writer is invoked after claim (not zero-domain).
    cast(AsyncMock, service._store.claim_batch_status).assert_awaited()
    cast(AsyncMock, service._store.write_manifest_root_and_chunks).assert_awaited()


@pytest.mark.asyncio
async def test_commit_plan_token_matches_false_not_found_no_cas():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token)
    # Stored digest does not match supplied token (tampered digest on root).
    root['token_digest'] = '0' * 64
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    with patch(
        'services.catalog_service.plan_token_matches',
        wraps=__import__(
            'services.catalog_identity', fromlist=['plan_token_matches']
        ).plan_token_matches,
    ) as match_spy:
        resp = await service.commit_prepared_catalog_batch(
            client=client,
            request=CommitPreparedCatalogBatchRequest(plan_token=token),
        )

    assert resp.error_code == CatalogErrorCode.prepared_plan_not_found
    assert resp.state == ''
    match_spy.assert_called()
    cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    cast(AsyncMock, service._store.load_prepared_plan_chunks).assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_commit_load_miss_not_found_without_match_success():
    token = mint_plan_token()
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=None, chunks=[])

    with patch(
        'services.catalog_service.plan_token_matches',
        wraps=__import__(
            'services.catalog_identity', fromlist=['plan_token_matches']
        ).plan_token_matches,
    ) as match_spy:
        resp = await service.commit_prepared_catalog_batch(
            client=client,
            request=CommitPreparedCatalogBatchRequest(plan_token=token),
        )

    assert resp.error_code == CatalogErrorCode.prepared_plan_not_found
    cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    # Load miss: match must not authorize (either not called or called only if load exists).
    assert match_spy.call_count == 0
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_commit_reentry_committing_same_token():
    token = mint_plan_token()
    root, chunks, art_sha = _make_root(token=token, state=PLAN_STATE_COMMITTING)
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code is None
    assert resp.state == PLAN_STATE_COMMITTED
    assert resp.artifact_sha256 == art_sha
    cas = cast(AsyncMock, service._store.cas_plan_state)
    cas.assert_awaited()
    reentry_claims = [
        c
        for c in cas.await_args_list
        if c.kwargs.get('expected_from') == PLAN_STATE_COMMITTING
        and c.kwargs.get('to_state') == PLAN_STATE_COMMITTING
    ]
    terminal = [
        c
        for c in cas.await_args_list
        if c.kwargs.get('expected_from') == PLAN_STATE_COMMITTING
        and c.kwargs.get('to_state') == PLAN_STATE_COMMITTED
    ]
    assert reentry_claims, 'expected COMMITTING reentry claim'
    assert terminal, 'expected COMMITTING→COMMITTED terminal'
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_expected_request_sha256_omit_and_correct_identical():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token)
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    resp_omit = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )
    # Reset CAS mock for second call
    _wire_commit(service, root={**root, 'state': PLAN_STATE_PREPARED}, chunks=chunks)
    resp_ok = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(
            plan_token=token,
            expected_request_sha256=root['request_sha256'],
        ),
    )

    assert resp_omit.error_code is None
    assert resp_ok.error_code is None
    assert resp_omit.plan_uuid == resp_ok.plan_uuid
    assert resp_omit.request_sha256 == resp_ok.request_sha256
    assert resp_omit.artifact_sha256 == resp_ok.artifact_sha256
    assert resp_omit.state == resp_ok.state == PLAN_STATE_COMMITTED


@pytest.mark.asyncio
async def test_commit_expected_request_sha256_mismatch_before_cas():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token)
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(
            plan_token=token,
            expected_request_sha256='f' * 64,
        ),
    )

    assert resp.error_code == CatalogErrorCode.prepared_plan_conflict
    cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_commit_expired_prepared_marks_expired():
    token = mint_plan_token()
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    root, chunks, _ = _make_root(token=token, expires_at=past)

    async def _cas(tx, **kwargs):
        _ = tx
        if kwargs.get('to_state') == PLAN_STATE_EXPIRED:
            return {**root, 'state': PLAN_STATE_EXPIRED}
        raise CatalogStoreError('prepared plan expired', code='prepared_plan_expired')

    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks, cas_side_effect=_cas)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code == CatalogErrorCode.prepared_plan_expired
    # Either explicit EXPIRED CAS or claim with require_not_expired raising expired.
    cas = cast(AsyncMock, service._store.cas_plan_state)
    assert cas.await_count >= 1
    client.embedder.create.assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_commit_discarded_maps_not_found():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token, state=PLAN_STATE_DISCARDED)
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code == CatalogErrorCode.prepared_plan_not_found
    cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_commit_committed_maps_already_consumed():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token, state=PLAN_STATE_COMMITTED)
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code == CatalogErrorCode.prepared_plan_already_consumed
    cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_commit_binding_mismatch_fails_closed_no_cas():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token)
    # Tamper root group_id vs artifact binding.
    root['group_id'] = 'other-group'
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code == CatalogErrorCode.prepared_plan_conflict
    cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_commit_never_calls_external_clients():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token)
    client = _commit_client()
    http = MagicMock()
    http.get = AsyncMock()
    client.http = http
    queue = MagicMock()
    queue.enqueue = AsyncMock()
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    _wire_commit(service, root=root, chunks=chunks)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code is None
    assert resp.state == PLAN_STATE_COMMITTED
    client.embedder.create.assert_not_awaited()
    client.llm_client.generate.assert_not_awaited()
    queue.enqueue.assert_not_awaited()
    http.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_discard_prepared_to_discarded_and_idempotent():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token, state=PLAN_STATE_PREPARED)
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    with patch(
        'services.catalog_service.plan_token_matches',
        wraps=__import__(
            'services.catalog_identity', fromlist=['plan_token_matches']
        ).plan_token_matches,
    ) as match_spy:
        resp1 = await service.discard_prepared_catalog_batch(
            client=client,
            request=DiscardPreparedCatalogBatchRequest(plan_token=token),
        )

    assert resp1.error_code is None
    assert resp1.state == PLAN_STATE_DISCARDED
    assert resp1.plan_uuid == root['uuid']
    match_spy.assert_called()
    assert match_spy.call_args[0][0] == token
    assert match_spy.call_args[0][1] == root['token_digest']
    cas = cast(AsyncMock, service._store.cas_plan_state)
    await_args = cas.await_args
    assert await_args is not None
    assert await_args.kwargs['to_state'] == PLAN_STATE_DISCARDED
    assert await_args.kwargs['expected_from'] == PLAN_STATE_PREPARED

    # Second discard: already DISCARDED → idempotent success.
    discarded_root = {**root, 'state': PLAN_STATE_DISCARDED}
    _wire_commit(service, root=discarded_root, chunks=chunks)
    resp2 = await service.discard_prepared_catalog_batch(
        client=client,
        request=DiscardPreparedCatalogBatchRequest(plan_token=token),
    )
    assert resp2.error_code is None
    assert resp2.state == PLAN_STATE_DISCARDED
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_discard_committing_and_committed_conflict():
    token = mint_plan_token()
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())

    for state in (PLAN_STATE_COMMITTING, PLAN_STATE_COMMITTED):
        root, chunks, _ = _make_root(token=token, state=state)
        _wire_commit(service, root=root, chunks=chunks)
        resp = await service.discard_prepared_catalog_batch(
            client=client,
            request=DiscardPreparedCatalogBatchRequest(plan_token=token),
        )
        assert resp.error_code == CatalogErrorCode.prepared_plan_conflict, state
        cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_discard_match_failure_not_found_no_cas():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token)
    root['token_digest'] = '1' * 64
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    resp = await service.discard_prepared_catalog_batch(
        client=client,
        request=DiscardPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code == CatalogErrorCode.prepared_plan_not_found
    cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_discard_never_calls_domain_delete_apis():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token)
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)
    delete_entity = AsyncMock()
    clear_graph = AsyncMock()
    object.__setattr__(service._store, 'delete_entity', delete_entity)
    object.__setattr__(service._store, 'clear_graph', clear_graph)

    resp = await service.discard_prepared_catalog_batch(
        client=client,
        request=DiscardPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code is None
    delete_entity.assert_not_awaited()
    clear_graph.assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_commit_terminal_expired_state_no_revive():
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token, state=PLAN_STATE_EXPIRED)
    client = _commit_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_commit(service, root=root, chunks=chunks)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code == CatalogErrorCode.prepared_plan_expired
    cast(AsyncMock, service._store.cas_plan_state).assert_not_awaited()
    _assert_zero_domain(service)


def test_commit_discard_helpers_exist_on_service():
    service = CatalogService(catalog_config=_enabled_config())
    assert hasattr(service, 'commit_prepared_catalog_batch')
    assert hasattr(service, 'discard_prepared_catalog_batch')
    assert callable(service.commit_prepared_catalog_batch)
    assert callable(service.discard_prepared_catalog_batch)


@pytest.mark.asyncio
async def test_prepare_rejects_committed_batch_status():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    req = _prepare_request()
    server_hash = batch_request_sha256(req)
    cast(AsyncMock, service._store.get_batch_status).return_value = {
        'status': 'committed',
        'request_sha256': server_hash,
    }
    resp = await service.prepare_catalog_batch(client=client, request=req)
    assert resp.error_code == CatalogErrorCode.prepared_plan_conflict
    assert resp.plan_token == ''
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_not_awaited()
    _assert_zero_domain(service)

    cast(AsyncMock, service._store.get_batch_status).return_value = {
        'status': 'committed',
        'request_sha256': 'f' * 64,
    }
    resp2 = await service.prepare_catalog_batch(client=client, request=req)
    assert resp2.error_code == CatalogErrorCode.batch_conflict
    assert resp2.plan_token == ''
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_uniqueness_race_exception_maps_conflict():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _race(*_a, **_k):
        raise RuntimeError('ConstraintValidationFailed: Node already exists')

    _wire_prepare(service, create_side_effect=_race)
    resp = await service.prepare_catalog_batch(client=client, request=_prepare_request())
    assert resp.error_code == CatalogErrorCode.prepared_plan_conflict
    assert resp.plan_token == ''
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_evidence_link_key_conflict():
    from models.catalog_batch import NestedProvenancePayload
    from models.catalog_evidence import CatalogEvidenceLink
    from models.catalog_provenance import CatalogSourceItem

    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    entity = _entity()
    source = CatalogSourceItem.model_validate(
        {
            'source_key': 'SRC::ddl.sql',
            'reference_time': '2026-07-18T00:00:00Z',
        }
    )
    base = {
        'source_key': 'SRC::ddl.sql',
        'entity_target': {
            'entity_type': entity.entity_type,
            'graph_key': entity.graph_key,
        },
        'evidence_kind': 'ddl',
        'extractor_name': 'parser',
        'extractor_version': '1.0',
    }
    link_a = CatalogEvidenceLink.model_validate({**base, 'excerpt': 'CREATE TABLE A'})
    link_b = CatalogEvidenceLink.model_validate({**base, 'excerpt': 'CREATE TABLE B'})
    prov = NestedProvenancePayload.model_validate(
        {'sources': [source], 'evidence_links': [link_a, link_b]}
    )
    req = PrepareCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH + '-ev',
        entities=[entity],
        edges=[],
        provenance=prov,
        catalog_sha256='a' * 64,
        atomic=True,
    )
    resp = await service.prepare_catalog_batch(client=client, request=req)
    assert resp.error_code == CatalogErrorCode.provenance_link_conflict
    assert resp.plan_token == ''
    cast(AsyncMock, service._store.create_prepared_plan_with_chunks).assert_not_awaited()
    _assert_zero_domain(service)


@pytest.mark.asyncio
async def test_prepare_evidence_byte_identical_coalesce():
    from models.catalog_batch import NestedProvenancePayload
    from models.catalog_evidence import CatalogEvidenceLink
    from models.catalog_provenance import CatalogSourceItem

    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_prepare(service)
    entity = _entity()
    source = CatalogSourceItem.model_validate(
        {
            'source_key': 'SRC::ddl.sql',
            'reference_time': '2026-07-18T00:00:00Z',
        }
    )
    base = {
        'source_key': 'SRC::ddl.sql',
        'entity_target': {
            'entity_type': entity.entity_type,
            'graph_key': entity.graph_key,
        },
        'evidence_kind': 'ddl',
        'extractor_name': 'parser',
        'extractor_version': '1.0',
        'excerpt': 'CREATE TABLE A',
    }
    link_a = CatalogEvidenceLink.model_validate(base)
    link_dup = CatalogEvidenceLink.model_validate(base)
    prov = NestedProvenancePayload.model_validate(
        {'sources': [source], 'evidence_links': [link_a, link_dup]}
    )
    req = PrepareCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH + '-ev2',
        entities=[entity],
        edges=[],
        provenance=prov,
        catalog_sha256='a' * 64,
        atomic=True,
    )
    resp = await service.prepare_catalog_batch(client=client, request=req)
    assert resp.error_code is None, resp.error_message
    assert resp.plan_token
    await_args = cast(AsyncMock, service._store.create_prepared_plan_with_chunks).await_args
    assert await_args is not None
    plan = await_args.kwargs['plan']
    # membership frozen with single evidence row after coalesce
    chunks = await_args.kwargs['chunks']
    raw = b''.join(
        base64.b64decode(c['payload_b64']) for c in sorted(chunks, key=lambda x: x['chunk_index'])
    )
    body = json.loads(raw.decode('utf-8'))
    assert len(body['membership']['evidence_links']) == 1
    # Coalesced membership is count authority (WR-01).
    assert plan['evidence_link_count'] == 1
    assert body['counts']['evidence_links'] == 1
    assert resp.evidence_link_count == 1
    _assert_zero_domain(service)
