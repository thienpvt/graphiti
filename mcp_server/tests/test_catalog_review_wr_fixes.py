"""Focused unit/service contracts for 03B REVIEW WR-01..WR-05.

No live Neo4j / network. Exercises pure helpers + fake-tx atomic writer paths.
"""

from __future__ import annotations

import importlib
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-wr-fix-01'
HEX64 = 'a' * 64
FIXED_NS = uuid.UUID('12345678-1234-5678-1234-567812345678')
FIXED_TS = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


def _load(name: str) -> Any:
    return importlib.import_module(name)


_COMMON = _load('models.catalog_common')
_SERVICE = _load('services.catalog_service')
_STORE = _load('services.catalog_store')
_CONFIG = _load('config.schema')
_ENTITIES = _load('models.catalog_entities')
_EDGES = _load('models.catalog_edges')

CatalogErrorCode = _COMMON.CatalogErrorCode
CatalogService = _SERVICE.CatalogService
CatalogNeo4jStore = _STORE.CatalogNeo4jStore
CatalogStoreError = _STORE.CatalogStoreError
CatalogWriteProjection = _SERVICE.CatalogWriteProjection
_PreparedEntity = _SERVICE._PreparedEntity
_PreparedEdge = _SERVICE._PreparedEdge
CatalogConfig = _CONFIG.CatalogConfig
CatalogEntityItem = _ENTITIES.CatalogEntityItem
CatalogEdgeItem = _EDGES.CatalogEdgeItem


def _enabled_config() -> Any:
    return CatalogConfig(
        enabled=True,
        uuid_namespace=str(FIXED_NS),
    )


def _entity_item(**overrides: Any) -> Any:
    base = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'ORCL.HR.EMPLOYEES',
        'summary': 'employees',
        'attributes': {},
        'confidence': 1.0,
    }
    base.update(overrides)
    return CatalogEntityItem.model_validate(base)


def _edge_item(**overrides: Any) -> Any:
    base = {
        'edge_type': 'ForeignKeyTo',
        'edge_key': 'FK::HR.EMPLOYEES->HR.DEPARTMENTS',
        'source_entity_type': 'Table',
        'source_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'target_entity_type': 'Table',
        'target_graph_key': 'TABLE::FE::ORCL.HR.DEPARTMENTS',
        'fact': 'employees.dept_id references departments.dept_id',
        'evidence': None,
        'attributes': {},
        'confidence': 1.0,
    }
    base.update(overrides)
    return CatalogEdgeItem.model_validate(base)


def _projection(
    *,
    entity_emb: list[float] | None = None,
    edge_emb: list[float] | None = None,
    entity_status: str = 'created',
    edge_status: str = 'created',
    plan: dict[str, Any] | None = None,
) -> Any:
    ent = _entity_item()
    edge = _edge_item()
    e_uuid = str(uuid.uuid5(FIXED_NS, 'entity'))
    edge_uuid = str(uuid.uuid5(FIXED_NS, 'edge'))
    tgt_uuid = str(uuid.uuid5(FIXED_NS, 'entity-tgt'))
    prep_e = _PreparedEntity(
        index=0,
        item=ent,
        entity_uuid=e_uuid,
        content_sha256=HEX64,
        name_embedding=entity_emb,
        projected_status=entity_status,
    )
    prep_edge = _PreparedEdge(
        index=0,
        item=edge,
        edge_uuid=edge_uuid,
        content_sha256=HEX64,
        source_uuid=e_uuid,
        target_uuid=tgt_uuid,
        fact_embedding=edge_emb,
        projected_status=edge_status,
        batch_result_index=1,
    )
    return CatalogWriteProjection(
        group_id=GROUP,
        batch_id=BATCH,
        batch_uuid=str(uuid.uuid5(FIXED_NS, 'batch')),
        request_sha256=HEX64,
        catalog_sha256=HEX64,
        identity_schema_version='catalog-v2',
        canonicalization_version='catalog-canonical-v1',
        namespace=FIXED_NS,
        request_ts=FIXED_TS,
        entity_prepared=[prep_e],
        edge_prepared=[prep_edge],
        provenance_sources=[],
        request_entity_uuids={(ent.entity_type, ent.graph_key): e_uuid},
        evidence_link_params=[],
        membership={'entities': [], 'edges': [], 'sources': [], 'evidence_links': []},
        entity_count=1,
        edge_count=1,
        provenance_count=0,
        edge_offset=1,
        request_entity_count=1,
        artifact_sha256=HEX64 if plan is not None else None,
        plan=plan,
        request_for_edge_recheck=None,
    )


@pytest.mark.asyncio
async def test_wr02_missing_entity_embedding_fail_closed():
    service = CatalogService(catalog_config=_enabled_config())
    store = CatalogNeo4jStore()
    service._store = store  # type: ignore[assignment]
    store.claim_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'b', 'status': 'writing', 'request_sha256': HEX64}
    )
    store.get_entity_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.upsert_entity_item = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(CatalogStoreError) as ei:
        await service._write_catalog_batch_atomic(object(), _projection(entity_emb=None))
    assert ei.value.code == 'embedding_failed'
    store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_wr02_empty_entity_embedding_fail_closed():
    service = CatalogService(catalog_config=_enabled_config())
    store = CatalogNeo4jStore()
    service._store = store  # type: ignore[assignment]
    store.claim_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'b', 'status': 'writing', 'request_sha256': HEX64}
    )
    store.get_entity_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.upsert_entity_item = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(CatalogStoreError) as ei:
        await service._write_catalog_batch_atomic(object(), _projection(entity_emb=[]))
    assert ei.value.code == 'embedding_failed'
    store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_wr02_missing_edge_embedding_fail_closed():
    service = CatalogService(catalog_config=_enabled_config())
    store = CatalogNeo4jStore()
    service._store = store  # type: ignore[assignment]
    store.claim_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'b', 'status': 'writing', 'request_sha256': HEX64}
    )
    store.get_entity_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.upsert_entity_item = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'e', 'status': 'created', 'error_code': None}
    )
    store.get_edge_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.upsert_edge_item = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(CatalogStoreError) as ei:
        await service._write_catalog_batch_atomic(
            object(), _projection(entity_emb=[0.1, 0.2], edge_emb=None)
        )
    assert ei.value.code == 'embedding_failed'
    store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_wr03_unknown_claim_status_fail_closed():
    service = CatalogService(catalog_config=_enabled_config())
    store = CatalogNeo4jStore()
    service._store = store  # type: ignore[assignment]
    store.claim_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'b', 'status': 'weird', 'request_sha256': HEX64}
    )
    store.upsert_entity_item = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(CatalogStoreError) as ei:
        await service._write_catalog_batch_atomic(
            object(), _projection(entity_emb=[0.1, 0.2], edge_emb=[0.3, 0.4])
        )
    assert ei.value.code == 'batch_conflict'
    store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_wr03_committed_direct_upsert_short_circuits():
    service = CatalogService(catalog_config=_enabled_config())
    store = CatalogNeo4jStore()
    service._store = store  # type: ignore[assignment]
    store.claim_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'b', 'status': 'committed', 'request_sha256': HEX64}
    )

    with pytest.raises(service._BatchStatusConflict) as ei:
        await service._write_catalog_batch_atomic(
            object(),
            _projection(entity_emb=[0.1], edge_emb=[0.2], plan=None),
        )
    assert ei.value.reason == 'already_committed'


def test_wr04_edge_row_error_raises_before_status():
    service = CatalogService(catalog_config=_enabled_config())
    row = {
        'uuid': 'e1',
        'status': 'error',
        'error_code': CatalogErrorCode.edge_identity_conflict.value,
    }
    with pytest.raises(service._EdgeEndpointRace) as ei:
        service._raise_edge_row_error(row)
    assert ei.value.code == CatalogErrorCode.edge_identity_conflict
    assert service._row_error_code(row) == CatalogErrorCode.edge_identity_conflict


def test_wr01_coalesce_count_authority_in_source():
    # Source-level guard: success-path counts use coalesced_evidence_count.
    src = Path(__file__).resolve().parents[1] / 'src' / 'services' / 'catalog_service.py'
    text = src.read_text(encoding='utf-8')
    assert 'coalesced_evidence_count = len(membership_evidence)' in text
    assert "'evidence_links': coalesced_evidence_count" in text
    assert "'evidence_link_count': coalesced_evidence_count" in text
    assert 'evidence_link_count=coalesced_evidence_count' in text


# ---------------------------------------------------------------------------
# Iteration 2: WR-06 / WR-07 / IN-01
# ---------------------------------------------------------------------------


class _FakeTxDriver:
    """Minimal driver: transaction yields a dummy tx and re-raises on error."""

    def __init__(self) -> None:
        self.tx_count = 0
        self.rolled_back = 0

    @asynccontextmanager
    async def transaction(self):
        self.tx_count += 1
        try:
            yield SimpleNamespace(run=AsyncMock())
        except BaseException:
            self.rolled_back += 1
            raise


def _edge_request(*, atomic: bool = True) -> Any:
    UpsertTypedEdgesRequest = _EDGES.UpsertTypedEdgesRequest
    return UpsertTypedEdgesRequest.model_construct(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH,
        edges=[_edge_item()],
        dry_run=False,
        atomic=atomic,
        strict_endpoints=True,
    )


def _prepared_edge(*, emb: list[float] | None | object = ..., status: str = 'created') -> Any:
    edge = _edge_item()
    e_uuid = str(uuid.uuid5(FIXED_NS, 'entity'))
    tgt_uuid = str(uuid.uuid5(FIXED_NS, 'entity-tgt'))
    edge_uuid = str(uuid.uuid5(FIXED_NS, 'edge'))
    fact_emb: list[float] | None = [0.3, 0.4] if emb is ... else emb  # type: ignore[assignment]
    return _PreparedEdge(
        index=0,
        item=edge,
        edge_uuid=edge_uuid,
        content_sha256=HEX64,
        source_uuid=e_uuid,
        target_uuid=tgt_uuid,
        fact_embedding=fact_emb,
        projected_status=status,
    )


def _client() -> Any:
    return SimpleNamespace(
        driver=_FakeTxDriver(),
        embedder=AsyncMock(create=AsyncMock(return_value=[0.1, 0.2])),
        llm_client=MagicMock(),
    )


@pytest.mark.asyncio
async def test_wr06_typed_edge_atomic_raises_identity_conflict():
    """Under-lock edge row error must raise before status and roll siblings back."""
    service = CatalogService(catalog_config=_enabled_config())
    store = CatalogNeo4jStore()
    service._store = store  # type: ignore[assignment]
    store.upsert_edge_item = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': 'e1',
            'status': 'error',
            'error_code': CatalogErrorCode.edge_identity_conflict.value,
        }
    )
    service._recheck_edge_endpoints_in_tx = AsyncMock(return_value=None)  # type: ignore[method-assign]

    prep = _prepared_edge()
    request = _edge_request(atomic=True)
    client = _client()
    resp = await service._write_edges_atomic(client, request, [prep], {}, FIXED_TS)
    assert resp.failed >= 1
    err = next(r for r in resp.results if r.status == 'error')
    assert err.error_code == CatalogErrorCode.edge_identity_conflict
    assert all(r.status in ('error', 'rolled_back') for r in resp.results)
    assert client.driver.rolled_back == 1


@pytest.mark.asyncio
async def test_wr06_typed_edge_per_item_structured_error_code():
    """Per-item path must surface edge_identity_conflict, not neo4j_transaction_failed."""
    service = CatalogService(catalog_config=_enabled_config())
    store = CatalogNeo4jStore()
    service._store = store  # type: ignore[assignment]
    store.upsert_edge_item = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': 'e1',
            'status': 'error',
            'error_code': CatalogErrorCode.edge_identity_conflict.value,
        }
    )
    service._recheck_edge_endpoints_in_tx = AsyncMock(return_value=None)  # type: ignore[method-assign]

    prep = _prepared_edge()
    request = _edge_request(atomic=False)
    client = _client()
    resp = await service._write_edges_per_item(client, request, [prep], {}, FIXED_TS)
    assert resp.failed == 1
    err = resp.results[0]
    assert err.status == 'error'
    assert err.error_code == CatalogErrorCode.edge_identity_conflict
    assert err.error_code != CatalogErrorCode.neo4j_transaction_failed


@pytest.mark.asyncio
async def test_wr07_upsert_catalog_batch_edge_endpoint_race_typed_code():
    """Direct upsert_catalog_batch must not collapse _EdgeEndpointRace to neo4j_transaction_failed."""
    service = CatalogService(catalog_config=_enabled_config())
    store = CatalogNeo4jStore()
    service._store = store  # type: ignore[assignment]

    UpsertCatalogBatchRequest = _load('models.catalog_batch').UpsertCatalogBatchRequest
    BatchPreflight = _SERVICE._BatchPreflightOutcome
    edge_prep = _prepared_edge()
    pre = BatchPreflight(
        namespace=FIXED_NS,
        batch_uuid=str(uuid.uuid5(FIXED_NS, 'batch')),
        server_hash=HEX64,
        hash_echo={'request_sha256': HEX64, 'catalog_sha256': HEX64},
        entity_prepared=[],
        edge_prepared=[edge_prep],
        provenance_sources=[],
        edge_offset=0,
        request_entity_uuids={},
        errors=[],
        early_kind=None,
    )
    service._prepare_batch_preflight = AsyncMock(return_value=pre)  # type: ignore[method-assign]
    service._ensure_schema = AsyncMock()  # type: ignore[method-assign]
    service._build_projection_from_upsert = MagicMock(  # type: ignore[method-assign]
        return_value=_projection(entity_emb=[0.1], edge_emb=[0.2])
    )

    async def _boom(*_a: Any, **_k: Any) -> Any:
        raise service._EdgeEndpointRace(CatalogErrorCode.edge_identity_conflict)

    service._write_catalog_batch_atomic = AsyncMock(side_effect=_boom)  # type: ignore[method-assign]
    store.upsert_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'b', 'status': 'failed', 'request_sha256': HEX64}
    )
    store.prepare_batch_status_params = MagicMock(  # type: ignore[method-assign]
        return_value={'uuid': 'b', 'status': 'failed', 'request_sha256': HEX64}
    )

    request = UpsertCatalogBatchRequest.model_construct(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH,
        entities=[],
        edges=[_edge_item()],
        provenance=None,
        request_sha256=HEX64,
        catalog_sha256=HEX64,
        dry_run=False,
        atomic=True,
    )
    client = _client()
    resp = await service.upsert_catalog_batch(client=client, request=request)
    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode.edge_identity_conflict
    assert resp.error_code != CatalogErrorCode.neo4j_transaction_failed
    store.upsert_batch_status.assert_awaited()


def test_in01_params_for_rejects_empty_embedding():
    service = CatalogService(catalog_config=_enabled_config())
    prep = _PreparedEntity(
        index=0,
        item=_entity_item(),
        entity_uuid=str(uuid.uuid5(FIXED_NS, 'entity')),
        content_sha256=HEX64,
        name_embedding=None,
        projected_status='created',
    )
    UpsertTypedEntitiesRequest = _ENTITIES.UpsertTypedEntitiesRequest
    request = UpsertTypedEntitiesRequest.model_construct(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH,
        entities=[_entity_item()],
        dry_run=False,
        atomic=True,
    )
    with pytest.raises(CatalogStoreError) as ei:
        service._params_for(prep, request, FIXED_TS)
    assert ei.value.code == 'embedding_failed'


def test_in01_edge_params_for_rejects_empty_embedding():
    service = CatalogService(catalog_config=_enabled_config())
    prep = _prepared_edge(emb=None)
    request = _edge_request()
    with pytest.raises(CatalogStoreError) as ei:
        service._edge_params_for(prep, request, FIXED_TS)
    assert ei.value.code == 'embedding_failed'


def test_wr06_raise_present_in_typed_edge_writers():
    src = Path(__file__).resolve().parents[1] / 'src' / 'services' / 'catalog_service.py'
    body = src.read_text(encoding='utf-8')
    assert body.count('self._raise_edge_row_error(row)') >= 3
    assert 'catalog upsert_catalog_batch edge_endpoint_race' in body
    assert 'name_embedding missing for non-unchanged entity' in body
    assert 'fact_embedding missing for non-unchanged edge' in body
