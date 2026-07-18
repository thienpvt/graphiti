"""Shared atomic catalog writer + fault-injection boundaries (PLAN-13/14, 03B-04).

Fake transactions model genuine rollback: pending writes land only on clean exit.
IDE-safe: no static product imports (importlib/getattr only).
"""

from __future__ import annotations

import importlib
import inspect
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-atomic-writer-01'
FIXED_NS = uuid.UUID('12345678-1234-5678-1234-567812345678')
HEX64 = 'a' * 64


def _load_module(module_name: str) -> Any:
    """importlib load; fail closed (Wave 0 / IDE-safe — no static product imports)."""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(f'03B not implemented: {module_name} missing ({exc})')


def _attr(mod: Any, symbol: str) -> Any:
    value = getattr(mod, symbol, None)
    if value is None:
        pytest.fail(f'03B not implemented: missing symbol {symbol}')
    return value


# Module-level dynamic product symbols (no `from config/models/services ...` static imports).
_CONFIG = _load_module('config.schema')
_ENTITIES = _load_module('models.catalog_entities')
_EDGES = _load_module('models.catalog_edges')
_PROVENANCE = _load_module('models.catalog_provenance')
_BATCH = _load_module('models.catalog_batch')
_SERVICE = _load_module('services.catalog_service')

CatalogConfig = _attr(_CONFIG, 'CatalogConfig')
CatalogEntityItem = _attr(_ENTITIES, 'CatalogEntityItem')
CatalogEdgeItem = _attr(_EDGES, 'CatalogEdgeItem')
CatalogSourceItem = _attr(_PROVENANCE, 'CatalogSourceItem')
UpsertCatalogBatchRequest = _attr(_BATCH, 'UpsertCatalogBatchRequest')
CatalogService = _attr(_SERVICE, 'CatalogService')
CatalogWriteProjection = _attr(_SERVICE, 'CatalogWriteProjection')
_PreparedEntity = _attr(_SERVICE, '_PreparedEntity')
_PreparedEdge = _attr(_SERVICE, '_PreparedEdge')
_PreparedSource = _attr(_SERVICE, '_PreparedSource')


def _service_mod() -> Any:
    return _SERVICE


def _now() -> datetime:
    return datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


class _RecordingStore:
    """Store double: pending ops commit only when FakeDriver.transaction succeeds."""

    def __init__(self) -> None:
        self.pending: list[tuple[str, dict[str, Any]]] = []
        self.committed: list[tuple[str, dict[str, Any]]] = []
        self.fail_after: str | None = None
        self.order: list[str] = []
        self.agree = False
        self.claim_status = 'open'
        self.claim_hash = HEX64

    def begin(self) -> None:
        self.pending = []

    def commit(self) -> None:
        self.committed.extend(self.pending)
        self.pending = []

    def rollback(self) -> None:
        self.pending = []

    def _rec(self, name: str, payload: dict[str, Any] | None = None) -> None:
        self.order.append(name)
        self.pending.append((name, payload or {}))
        if self.fail_after == name:
            raise RuntimeError(f'inject_after_{name}')

    async def claim_batch_status(self, tx: Any, *, params: dict[str, Any]) -> dict[str, Any]:
        _ = tx
        self._rec('claim', dict(params))
        return {
            'uuid': params.get('uuid'),
            'group_id': params.get('group_id'),
            'batch_id': params.get('batch_id'),
            'status': self.claim_status,
            'request_sha256': self.claim_hash,
        }

    async def get_entity_by_uuid(
        self,
        executor: Any,
        *,
        uuid: str,  # product API kw name
        group_id: str,
        tx: Any = None,
    ) -> dict[str, Any] | None:
        _entity_uuid = uuid
        _ = executor, group_id, tx, _entity_uuid
        return None

    async def upsert_entity_item(
        self, tx: Any, *, entity_type: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        _ = tx, entity_type
        self._rec('entity', dict(params))
        return {
            'uuid': params.get('uuid'),
            'status': 'created',
            'content_sha256': params.get('content_sha256'),
            'error_code': None,
        }

    async def get_edge_by_uuid(
        self,
        executor: Any,
        *,
        uuid: str,  # product API kw name
        group_id: str,
        tx: Any = None,
    ) -> dict[str, Any] | None:
        _edge_uuid = uuid
        _ = executor, group_id, tx, _edge_uuid
        return None

    async def resolve_endpoint_typed(
        self, *args: Any, **kwargs: Any
    ) -> tuple[None, dict[str, Any]]:
        _ = args
        return None, {'uuid': kwargs.get('expected_uuid')}

    async def upsert_edge_item(self, tx: Any, *, params: dict[str, Any]) -> dict[str, Any]:
        _ = tx
        self._rec('edge', dict(params))
        return {
            'uuid': params.get('uuid'),
            'status': 'created',
            'content_sha256': params.get('content_sha256'),
            'error_code': None,
        }

    async def upsert_source_episode(self, tx: Any, *, params: dict[str, Any]) -> dict[str, Any]:
        _ = tx
        self._rec('source', dict(params))
        return {
            'uuid': params.get('uuid'),
            'status': 'created',
            'source_key': params.get('source_key'),
            'content_sha256': params.get('content_sha256'),
            'error_code': None,
        }

    async def lock_provenance_targets(self, tx: Any, **kwargs: Any) -> list[dict[str, Any]]:
        _ = tx, kwargs
        return []

    async def upsert_mentions_link(self, tx: Any, **kwargs: Any) -> dict[str, Any]:
        _ = tx
        self._rec('mentions', dict(kwargs))
        return {'uuid': kwargs.get('mentions_uuid')}

    async def append_edge_episode(self, tx: Any, **kwargs: Any) -> None:
        _ = tx
        self._rec('edge_episode', dict(kwargs))

    async def write_evidence_links(
        self, tx: Any, *, links: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        _ = tx
        self._rec('evidence', {'count': len(links)})
        return [{'uuid': f'e-{i}'} for i in range(len(links))]

    async def write_manifest_root_and_chunks(
        self, tx: Any, *, root: dict[str, Any], chunks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _ = tx
        self._rec('manifest', {'root': root.get('uuid'), 'chunks': len(chunks)})
        return {
            'uuid': root.get('uuid'),
            'manifest_sha256': root.get('manifest_sha256'),
            'chunk_count': len(chunks),
        }

    async def upsert_batch_status(self, tx: Any, *, params: dict[str, Any]) -> dict[str, Any]:
        _ = tx
        self._rec('status', dict(params))
        return {
            'uuid': params.get('uuid'),
            'status': params.get('status'),
            'request_sha256': params.get('request_sha256'),
        }

    async def lock_prepared_plan_for_commit(
        self, tx: Any, *, plan_uuid: str, group_id: str
    ) -> dict[str, Any]:
        _ = tx
        self._rec('lock_plan', {'plan_uuid': plan_uuid, 'group_id': group_id})
        return {
            'uuid': plan_uuid,
            'group_id': group_id,
            'state': 'COMMITTING',
            'locked': True,
        }

    async def terminal_commit_agrees(self, tx: Any, *, projection: dict[str, Any]) -> bool:
        _ = tx, projection
        self.order.append('terminal_agree_check')
        return self.agree

    async def cas_plan_state(self, tx: Any, **kwargs: Any) -> dict[str, Any]:
        _ = tx
        self._rec('cas_plan', dict(kwargs))
        return {'state': kwargs.get('to_state'), 'uuid': 'plan-1'}

    def prepare_entity_params(self, **fields: Any) -> dict[str, Any]:
        return dict(fields)

    def prepare_edge_params(self, **fields: Any) -> dict[str, Any]:
        return dict(fields)

    def prepare_source_episode_params(self, **fields: Any) -> dict[str, Any]:
        return dict(fields)

    def prepare_batch_status_params(self, **fields: Any) -> dict[str, Any]:
        return dict(fields)

    def prepare_evidence_link_params(self, **fields: Any) -> dict[str, Any]:
        return dict(fields)

    def prepare_manifest_root_params(self, **fields: Any) -> dict[str, Any]:
        return dict(fields)

    def prepare_manifest_chunk_params(self, **fields: Any) -> dict[str, Any]:
        return dict(fields)

    def detect_edge_identity_conflict(self, *args: Any, **kwargs: Any) -> bool:
        _ = args, kwargs
        return False


class _FakeDriver:
    def __init__(self, store: _RecordingStore) -> None:
        self._store = store
        self.provider = SimpleNamespace(value='neo4j')
        self.tx_count = 0

    @asynccontextmanager
    async def transaction(self):
        self.tx_count += 1
        self._store.begin()
        try:
            yield SimpleNamespace(run=AsyncMock())
            self._store.commit()
        except BaseException:
            self._store.rollback()
            raise

    async def execute_query(self, cypher: str, params=None, **kwargs):
        _ = cypher, params, kwargs
        return ([], None, None)


def _entity_prep(*, status: str = 'created') -> Any:
    item = CatalogEntityItem.model_validate(
        {
            'entity_type': 'Table',
            'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
            'name_raw': 'EMPLOYEES',
            'name_canonical': 'employees',
            'database_qualified_name': 'ORCL.HR.EMPLOYEES',
            'summary': 'Employee master',
            'attributes': {},
            'confidence': 0.9,
        }
    )
    return _PreparedEntity(
        index=0,
        item=item,
        entity_uuid=str(uuid.uuid5(FIXED_NS, 'ent')),
        content_sha256=HEX64,
        name_embedding=[0.1, 0.2],
        projected_status=status,
    )


def _edge_prep(source_uuid: str, target_uuid: str, *, status: str = 'created') -> Any:
    _ = source_uuid, target_uuid
    item = CatalogEdgeItem.model_validate(
        {
            'edge_type': 'ForeignKeyTo',
            'edge_key': 'FK::HR.EMPLOYEES->HR.DEPARTMENTS',
            'source_entity_type': 'Table',
            'source_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
            'target_entity_type': 'Table',
            'target_graph_key': 'TABLE::FE::ORCL.HR.DEPARTMENTS',
            'fact': 'employees references departments',
            'evidence': None,
            'attributes': {},
            'confidence': 0.9,
        }
    )
    return _PreparedEdge(
        index=0,
        item=item,
        edge_uuid=str(uuid.uuid5(FIXED_NS, 'edge')),
        content_sha256=HEX64,
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        fact_embedding=[0.3, 0.4],
        projected_status=status,
        batch_result_index=1,
    )


def _source_prep(entity_uuid: str, *, status: str = 'created') -> Any:
    item = CatalogSourceItem.model_validate(
        {
            'source_key': 'SRC::FE::ddl.sql',
            'reference_time': '2026-01-01T00:00:00Z',
            'attributes': {},
            'metadata': {},
        }
    )
    return _PreparedSource(
        index=0,
        item=item,
        source_uuid=str(uuid.uuid5(FIXED_NS, 'src')),
        content_sha256=HEX64,
        content_json='{}',
        valid_at=_now(),
        projected_status=status,
        entity_uuids=[entity_uuid],
        edge_uuids=[],
        mentions_uuids=[str(uuid.uuid5(FIXED_NS, 'men'))],
        missing_links=True,
    )


def _projection(*, with_plan: bool = False, with_evidence: bool = True) -> Any:
    ent = _entity_prep()
    edge = _edge_prep(ent.entity_uuid, str(uuid.uuid5(FIXED_NS, 'tgt')))
    src = _source_prep(ent.entity_uuid)
    evidence: list[dict[str, Any]] = []
    if with_evidence:
        evidence = [
            {
                'uuid': str(uuid.uuid5(FIXED_NS, 'ev')),
                'group_id': GROUP,
                'batch_id': BATCH,
                'link_key': 'lk1',
                'content_sha256': HEX64,
                'source_uuid': src.source_uuid,
                'target_kind': 'entity',
                'target_uuid': ent.entity_uuid,
                'evidence_kind': 'ddl',
                'locator_json': None,
                'excerpt': None,
                'extractor_name': 'parser',
                'extractor_version': '1',
                'rule_id': None,
                'confidence': 0.9,
                'created_at': _now(),
                'updated_at': _now(),
            }
        ]
    plan = None
    if with_plan:
        plan = {
            'plan_uuid': str(uuid.uuid5(FIXED_NS, 'plan')),
            'token_digest': 'b' * 64,
        }
    return CatalogWriteProjection(
        group_id=GROUP,
        batch_id=BATCH,
        batch_uuid=str(uuid.uuid5(FIXED_NS, 'batch')),
        request_sha256=HEX64,
        catalog_sha256=HEX64,
        artifact_sha256=HEX64 if with_plan else None,
        identity_schema_version='catalog-v2',
        canonicalization_version='catalog-canonical-v1',
        namespace=FIXED_NS,
        request_ts=_now(),
        entity_prepared=[ent],
        edge_prepared=[edge],
        provenance_sources=[src],
        request_entity_uuids={
            (ent.item.entity_type, ent.item.graph_key): ent.entity_uuid,
        },
        evidence_link_params=evidence,
        entity_count=1,
        edge_count=1,
        provenance_count=2,
        edge_offset=1,
        request_entity_count=1,
        membership={
            'entities': [
                {
                    'uuid': ent.entity_uuid,
                    'entity_type': ent.item.entity_type,
                    'graph_key': ent.item.graph_key,
                    'content_sha256': ent.content_sha256,
                    'projected_status': ent.projected_status,
                }
            ],
            'edges': [
                {
                    'uuid': edge.edge_uuid,
                    'edge_type': edge.item.edge_type,
                    'edge_key': edge.item.edge_key,
                    'content_sha256': edge.content_sha256,
                    'projected_status': edge.projected_status,
                }
            ],
            'sources': [
                {
                    'uuid': src.source_uuid,
                    'source_key': src.item.source_key,
                    'content_sha256': src.content_sha256,
                    'projected_status': src.projected_status,
                }
            ],
            'evidence_links': [
                {
                    'uuid': evidence[0]['uuid'],
                    'link_key': 'lk1',
                    'content_sha256': HEX64,
                }
            ]
            if evidence
            else [],
        },
        plan=plan,
        request_for_edge_recheck=SimpleNamespace(group_id=GROUP, entities=[], edges=[]),
    )


def _service_with_store(store: Any) -> Any:
    return CatalogService(
        catalog_config=CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS)),
        store=store,  # type: ignore[arg-type]
    )


async def _run_writer(
    service: Any, store: _RecordingStore, projection: Any, *, expect_error: bool = False
) -> Any:
    driver = _FakeDriver(store)
    if expect_error:
        with pytest.raises(RuntimeError):
            async with driver.transaction() as tx:
                await service._write_catalog_batch_atomic(tx, projection)
        return None
    async with driver.transaction() as tx:
        return await service._write_catalog_batch_atomic(tx, projection)


def test_shared_writer_used_by_upsert_and_commit_paths():
    """PLAN-13: direct upsert and prepared commit share one atomic writer."""
    assert GROUP == 'oracle-catalog-tool-test'
    mod = _service_mod()
    assert hasattr(mod, 'CatalogWriteProjection')
    assert hasattr(mod.CatalogService, '_write_catalog_batch_atomic')
    upsert_src = inspect.getsource(mod.CatalogService.upsert_catalog_batch)
    commit_src = inspect.getsource(mod.CatalogService.commit_prepared_catalog_batch)
    assert '_write_catalog_batch_atomic' in upsert_src
    assert '_write_catalog_batch_atomic' in commit_src


@pytest.mark.asyncio
async def test_fault_inject_after_entities_rolls_back():
    """PLAN-13/14: fault after entities leaves zero committed success markers."""
    store = _RecordingStore()
    service = _service_with_store(store)
    store.fail_after = 'entity'
    proj = _projection()
    await _run_writer(service, store, proj, expect_error=True)
    assert store.committed == []
    assert store.pending == []
    assert 'entity' in store.order
    assert all(op[0] != 'status' or op[1].get('status') != 'committed' for op in store.committed)
    assert all(op[0] != 'cas_plan' for op in store.committed)


@pytest.mark.asyncio
async def test_fault_inject_after_edges_rolls_back():
    store = _RecordingStore()
    service = _service_with_store(store)
    store.fail_after = 'edge'
    await _run_writer(service, store, _projection(), expect_error=True)
    assert store.committed == []
    assert 'entity' in store.order
    assert 'edge' in store.order


@pytest.mark.asyncio
async def test_fault_inject_after_sources_rolls_back():
    store = _RecordingStore()
    service = _service_with_store(store)
    store.fail_after = 'source'
    await _run_writer(service, store, _projection(), expect_error=True)
    assert store.committed == []
    assert 'source' in store.order


@pytest.mark.asyncio
async def test_fault_inject_after_evidence_rolls_back():
    store = _RecordingStore()
    service = _service_with_store(store)
    store.fail_after = 'evidence'
    await _run_writer(service, store, _projection(), expect_error=True)
    assert store.committed == []
    assert 'evidence' in store.order


@pytest.mark.asyncio
async def test_fault_inject_after_manifest_rolls_back():
    store = _RecordingStore()
    service = _service_with_store(store)
    store.fail_after = 'manifest'
    await _run_writer(service, store, _projection(), expect_error=True)
    assert store.committed == []
    assert 'manifest' in store.order
    assert not any(n == 'status' and d.get('status') == 'committed' for n, d in store.committed)


@pytest.mark.asyncio
async def test_fault_inject_after_status_rolls_back():
    """Fault after batch status still rolls back; no durable committed terminal."""
    store = _RecordingStore()
    service = _service_with_store(store)
    store.fail_after = 'status'
    await _run_writer(service, store, _projection(), expect_error=True)
    assert store.committed == []


@pytest.mark.asyncio
async def test_plan13_write_order_stub():
    """PLAN-13 order: lock/claim → entities → edges → sources → evidence →
    manifest → batch committed → plan COMMITTED (prepared path)."""
    store = _RecordingStore()
    service = _service_with_store(store)
    proj = _projection(with_plan=True)
    outcome = await _run_writer(service, store, proj)
    assert outcome is not None
    assert outcome.get('short_circuit') is False
    order = store.order
    primary = [
        n
        for n in order
        if n
        in {
            'lock_plan',
            'claim',
            'entity',
            'edge',
            'source',
            'evidence',
            'manifest',
            'status',
            'cas_plan',
        }
    ]
    assert primary == [
        'lock_plan',
        'claim',
        'entity',
        'edge',
        'source',
        'evidence',
        'manifest',
        'status',
        'cas_plan',
    ]
    assert any(n == 'status' and d.get('status') == 'committed' for n, d in store.committed)
    assert any(n == 'cas_plan' for n, _ in store.committed)
    assert outcome.get('manifest_sha256')


@pytest.mark.asyncio
async def test_terminal_agree_short_circuits_without_rewrite():
    store = _RecordingStore()
    service = _service_with_store(store)
    store.agree = True
    proj = _projection(with_plan=True)
    outcome = await _run_writer(service, store, proj)
    assert outcome is not None
    assert outcome.get('short_circuit') is True
    assert 'entity' not in store.order
    assert 'manifest' not in store.order
    assert 'cas_plan' not in store.order


@pytest.mark.asyncio
async def test_plan_cas_only_when_projection_plan_present():
    store = _RecordingStore()
    service = _service_with_store(store)
    await _run_writer(service, store, _projection(with_plan=False))
    assert 'lock_plan' not in store.order
    assert 'cas_plan' not in store.order
    assert any(n == 'status' and d.get('status') == 'committed' for n, d in store.committed)


@pytest.mark.asyncio
async def test_dry_run_zero_write():
    """PLAN-14: dry_run path invokes no Neo4j write transaction."""
    store = _RecordingStore()
    service = CatalogService(
        catalog_config=CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS)),
        store=store,  # type: ignore[arg-type]
    )
    driver = _FakeDriver(store)
    client = SimpleNamespace(
        driver=driver,
        embedder=SimpleNamespace(create=AsyncMock(return_value=[0.1, 0.2])),
        llm_client=SimpleNamespace(),
    )
    # Preflight will try real store reads via get_*; stub store methods used in preflight.
    store.get_batch_status = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.get_entity_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.get_entity_by_group_name_type = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.get_edge_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.get_source_episode_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    store.ensure_uuid_uniqueness_constraints = AsyncMock()  # type: ignore[method-assign]
    store.ensure_evidence_manifest_schema = AsyncMock()  # type: ignore[method-assign]

    entity = CatalogEntityItem.model_validate(
        {
            'entity_type': 'Table',
            'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
            'name_raw': 'EMPLOYEES',
            'name_canonical': 'employees',
            'database_qualified_name': 'ORCL.HR.EMPLOYEES',
            'summary': 'Employee master',
            'attributes': {},
            'confidence': 0.9,
        }
    )
    req = UpsertCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH,
        entities=[entity],
        catalog_sha256=HEX64,
        dry_run=True,
        atomic=True,
    )
    resp = await service.upsert_catalog_batch(client=client, request=req)
    assert resp.dry_run is True
    assert resp.status == 'validating'
    assert driver.tx_count == 0
    assert store.committed == []
    assert store.pending == []
