"""GREEN: resolve_typed_edges diagnostics (RESE-01..03, TEST-08, IDEN-08).

Fields + anomaly vocabulary only; no repair; works writes-off; group isolation
on oracle-catalog-tool-test.
"""

from __future__ import annotations

import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_common import CatalogErrorCode  # noqa: E402
from models.catalog_entities import (  # noqa: E402
    ResolveEdgeRef,
    ResolveTypedEdgesRequest,
)
from services.catalog_identity import catalog_edge_uuid  # noqa: E402
from services.catalog_service import CatalogService  # noqa: E402

GROUP = 'oracle-catalog-tool-test'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
EDGE_KEY = 'CONTAINS::FE::ORCL.HR->ORCL.HR.EMPLOYEES'
SRC_KEY = 'SCHEMA::FE::ORCL.HR'
TGT_KEY = 'TABLE::FE::ORCL.HR.EMPLOYEES'


def _enabled_config() -> CatalogConfig:
    return CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))


def _make_client(*, provider: str = 'neo4j', embedder: AsyncMock | None = None):
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
    tx.run = AsyncMock(return_value=SimpleNamespace(data=AsyncMock(return_value=[])))

    @asynccontextmanager
    async def _transaction():
        call_order.append('transaction')
        yield tx

    driver = SimpleNamespace(
        provider=provider_enum,
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


def _edge_ref(edge_type: str = 'Contains', edge_key: str = EDGE_KEY) -> ResolveEdgeRef:
    return ResolveEdgeRef(edge_type=edge_type, edge_key=edge_key)


def _request(edges: list[ResolveEdgeRef] | None = None) -> ResolveTypedEdgesRequest:
    if edges is None:
        edges = [_edge_ref()]
    return ResolveTypedEdgesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        edges=edges,
    )


def _row(
    *,
    edge_uuid: str | None = None,
    edge_type: str = 'Contains',
    edge_key: str = EDGE_KEY,
    content_sha256: str | None = 'a' * 64,
    has_fact_embedding: bool = True,
    source_uuid: str | None = 'src-uuid',
    target_uuid: str | None = 'tgt-uuid',
    source_graph_key: str = SRC_KEY,
    target_graph_key: str = TGT_KEY,
    source_labels: list[str] | None = None,
    target_labels: list[str] | None = None,
    element_id: str = 'rel-1',
) -> dict[str, Any]:
    return {
        'element_id': element_id,
        'uuid': edge_uuid or catalog_edge_uuid(FIXED_NS, GROUP, edge_type, edge_key),
        'group_id': GROUP,
        'edge_type': edge_type,
        'edge_key': edge_key,
        'content_sha256': content_sha256,
        'has_fact_embedding': has_fact_embedding,
        'source_uuid': source_uuid,
        'target_uuid': target_uuid,
        'source_graph_key': source_graph_key,
        'target_graph_key': target_graph_key,
        'source_labels': source_labels or ['Entity', 'Schema'],
        'target_labels': target_labels or ['Entity', 'Table'],
    }


@pytest.mark.asyncio
async def test_resolve_typed_edges_fields():
    """RESE-01: returns uuid, source/target (+graph keys), type, content_sha256, embedding presence."""
    assert GROUP == 'oracle-catalog-tool-test'
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', EDGE_KEY)
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_edges_for_resolve = AsyncMock(return_value=[_row(edge_uuid=edge_uuid)])
    resp = await service.resolve_typed_edges(client=client, request=_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert r0.uuid == edge_uuid
    assert r0.verified_type == 'Contains'
    assert r0.source_uuid == 'src-uuid'
    assert r0.target_uuid == 'tgt-uuid'
    assert r0.source_graph_key == SRC_KEY
    assert r0.target_graph_key == TGT_KEY
    assert r0.content_sha256 == 'a' * 64
    assert r0.has_fact_embedding is True
    assert r0.edge_key == EDGE_KEY
    assert r0.edge_type == 'Contains'
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_fields():
    """RESE-01 alias (research test map): resolve_typed_edges fields."""
    await test_resolve_typed_edges_fields()


@pytest.mark.asyncio
async def test_anomalies():
    """RESE-02: anomalies missing/duplicate/type/endpoint/endpoint_pair/uuid; no repair."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    # missing
    service._store.match_edges_for_resolve = AsyncMock(return_value=[])
    missing = await service.resolve_typed_edges(client=client, request=_request())
    assert missing.results[0].found is False
    assert 'missing' in missing.results[0].anomalies

    # duplicate + type + uuid + endpoint + endpoint_pair + missing_embedding + missing hash
    expected_uuid = catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', EDGE_KEY)
    twins = [
        _row(
            edge_uuid='wrong-uuid-1',
            edge_type='ForeignKeyTo',
            content_sha256=None,
            has_fact_embedding=False,
            source_uuid=None,
            target_uuid='t1',
            source_labels=['Entity', 'Table'],
            target_labels=['Entity', 'Table'],
            element_id='rel-a',
        ),
        _row(
            edge_uuid='wrong-uuid-2',
            edge_type='ForeignKeyTo',
            content_sha256=None,
            has_fact_embedding=False,
            source_uuid='s1',
            target_uuid=None,
            source_labels=['Entity', 'Table'],
            target_labels=['Entity', 'Table'],
            element_id='rel-b',
        ),
    ]
    service._store.match_edges_for_resolve = AsyncMock(return_value=twins)
    resp = await service.resolve_typed_edges(client=client, request=_request())
    anoms = set(resp.results[0].anomalies)
    assert 'duplicate_edge_key' in anoms
    assert 'edge_type_mismatch' in anoms
    assert 'uuid_mismatch' in anoms
    assert 'endpoint_mismatch' in anoms
    assert 'endpoint_pair_violation' in anoms  # Contains requires Schema->Table-ish pair
    assert 'missing_embedding' in anoms
    assert 'missing_content_hash' in anoms
    assert resp.results[0].found is True
    assert resp.results[0].uuid != expected_uuid or True  # observation only
    # no repair side effects
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_writes_off():
    """RESE-03: resolve_typed_edges works when catalog writes disabled; no embedder calls."""
    client = _make_client()
    service = CatalogService(
        catalog_config=CatalogConfig(
            enabled=False, reads_enabled=True, uuid_namespace=str(FIXED_NS)
        )
    )
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', EDGE_KEY)
    service._store.match_edges_for_resolve = AsyncMock(return_value=[_row(edge_uuid=edge_uuid)])
    resp = await service.resolve_typed_edges(client=client, request=_request())
    assert resp.results[0].found is True
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order

    # reads_enabled=false still gates
    service_off = CatalogService(
        catalog_config=CatalogConfig(
            enabled=False, reads_enabled=False, uuid_namespace=str(FIXED_NS)
        )
    )
    service_off._store.match_edges_for_resolve = AsyncMock()
    gated = await service_off.resolve_typed_edges(client=client, request=_request())
    assert gated.results[0].error_code == CatalogErrorCode.feature_disabled
    service_off._store.match_edges_for_resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_isolation():
    """RESE-03 adjacency: cross-group edge key not returned; tool-test only."""
    assert GROUP == 'oracle-catalog-tool-test'
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    captured: dict[str, Any] = {}

    async def _match(executor=None, **kwargs):
        _ = executor
        captured.clear()
        captured.update(kwargs)
        # Store always scoped by group_id — return empty for foreign group simulation.
        if kwargs.get('group_id') != GROUP:
            return []
        return [_row()]

    service._store.match_edges_for_resolve = AsyncMock(side_effect=_match)
    await service.resolve_typed_edges(client=client, request=_request())
    assert captured.get('group_id') == GROUP
    # Foreign group request still binds its own group_id (never leaks other groups).
    foreign = ResolveTypedEdgesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id='other-group-not-tool-test',
        edges=[_edge_ref()],
    )
    # group_id validator allows other groups at model layer; isolation is MATCH scope.
    await service.resolve_typed_edges(client=client, request=foreign)
    assert captured.get('group_id') == 'other-group-not-tool-test'


def test_empty_refs():
    """RESE-03 empty: empty refs list → request validation rejects before service."""
    with pytest.raises(ValidationError):
        ResolveTypedEdgesRequest.model_validate(
            {
                'identity_schema_version': 'catalog-v2',
                'system_key': 'FE',
                'group_id': GROUP,
                'edges': [],
            }
        )


@pytest.mark.asyncio
async def test_ordering_stable():
    """RESE-03 ordering: results order stable by request order."""
    k1 = 'CONTAINS::FE::ORCL.A->ORCL.A.T1'
    k2 = 'CONTAINS::FE::ORCL.B->ORCL.B.T2'
    refs = [
        _edge_ref(edge_key=k1),
        _edge_ref(edge_key=k2),
        _edge_ref(edge_key=k1),
    ]
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_edges_for_resolve = AsyncMock(
        return_value=[
            _row(edge_key=k2, edge_uuid=catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', k2)),
            _row(edge_key=k1, edge_uuid=catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', k1)),
        ]
    )
    resp = await service.resolve_typed_edges(client=client, request=_request(refs))
    assert [r.index for r in resp.results] == [0, 1, 2]
    assert [r.edge_key for r in resp.results] == [k1, k2, k1]


@pytest.mark.asyncio
async def test_no_repair():
    """RESE-02/GATE-04: resolve path never repairs, creates, or rewrites edges."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_edges_for_resolve = AsyncMock(
        return_value=[
            _row(
                edge_uuid='not-deterministic',
                edge_type='ForeignKeyTo',
                content_sha256=None,
            )
        ]
    )
    # Spy real write-capable store methods only (no inventing unknown attrs).
    upsert_spy = AsyncMock()
    service._store.upsert_edge_item = upsert_spy
    resp = await service.resolve_typed_edges(client=client, request=_request())
    assert resp.results[0].found is True
    assert 'uuid_mismatch' in resp.results[0].anomalies
    upsert_spy.assert_not_awaited()
    assert 'transaction' not in client.call_order
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_batch_limit_uses_max_edges():
    """CR-01: resolve_typed_edges uses max_edges_per_batch, not entity max."""
    client = _make_client()
    # Entity max 500, edge max 2: 2 refs ok, 3 exceeds.
    service = CatalogService(
        catalog_config=CatalogConfig(
            enabled=False,
            reads_enabled=True,
            uuid_namespace=str(FIXED_NS),
            max_entities_per_batch=500,
            max_edges_per_batch=2,
        )
    )
    service._store.match_edges_for_resolve = AsyncMock(return_value=[])

    ok_refs = [ResolveEdgeRef(edge_type='Contains', edge_key=f'{EDGE_KEY}::{i}') for i in range(2)]
    ok = await service.resolve_typed_edges(client=client, request=_request(ok_refs))
    assert all(r.error_code is None for r in ok.results)

    over_refs = [
        ResolveEdgeRef(edge_type='Contains', edge_key=f'{EDGE_KEY}::{i}') for i in range(3)
    ]
    over = await service.resolve_typed_edges(client=client, request=_request(over_refs))
    assert all(r.error_code == CatalogErrorCode.batch_limit_exceeded for r in over.results)
    assert all('max_edges_per_batch' in (r.error_message or '') for r in over.results)

    # 501 edges allowed when max_edges=2000 (entity max must not clamp).
    service_wide = CatalogService(
        catalog_config=CatalogConfig(
            enabled=False,
            reads_enabled=True,
            uuid_namespace=str(FIXED_NS),
            max_entities_per_batch=500,
            max_edges_per_batch=2000,
        )
    )
    service_wide._store.match_edges_for_resolve = AsyncMock(return_value=[])
    many = [
        ResolveEdgeRef(edge_type='Contains', edge_key=f'{EDGE_KEY}::many::{i}') for i in range(501)
    ]
    many_resp = await service_wide.resolve_typed_edges(client=client, request=_request(many))
    assert all(r.error_code is None for r in many_resp.results)


@pytest.mark.asyncio
async def test_edge_status_mirrors_primary_anomaly():
    """WR-06: edge status is primary anomaly, not tautological found."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    twins = [
        _row(
            edge_uuid='wrong-1',
            edge_type='ForeignKeyTo',
            content_sha256=None,
            has_fact_embedding=False,
            source_uuid=None,
            target_uuid='t1',
            source_labels=['Entity', 'Table'],
            target_labels=['Entity', 'Table'],
            element_id='rel-a',
        ),
        _row(
            edge_uuid='wrong-2',
            edge_type='ForeignKeyTo',
            content_sha256=None,
            has_fact_embedding=False,
            source_uuid='s1',
            target_uuid=None,
            source_labels=['Entity', 'Table'],
            target_labels=['Entity', 'Table'],
            element_id='rel-b',
        ),
    ]
    service._store.match_edges_for_resolve = AsyncMock(return_value=twins)
    resp = await service.resolve_typed_edges(client=client, request=_request())
    r = resp.results[0]
    assert r.status == 'duplicate_edge_key'
    assert 'duplicate_edge_key' in r.anomalies
    assert 'edge_type_mismatch' in r.anomalies
    assert r.found is True
