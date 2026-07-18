"""Focused unit/service contracts for 03B REVIEW WR-01..WR-05.

No live Neo4j / network. Exercises pure helpers + fake-tx atomic writer paths.
"""

from __future__ import annotations

import importlib
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

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
