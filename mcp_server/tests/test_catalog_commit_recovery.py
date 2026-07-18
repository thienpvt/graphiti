"""Stranded COMMITTING recovery + terminal agreement (PLAN-14/15, MANI-07, 03B-05)."""

from __future__ import annotations

import importlib
import inspect
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
HEX64 = 'a' * 64


def _load(module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(f'03B not implemented: {module_name} missing ({exc})')


def _attr(mod: Any, symbol: str) -> Any:
    value = getattr(mod, symbol, None)
    if value is None:
        pytest.fail(f'03B not implemented: missing symbol {symbol}')
    return value


_CONFIG = _load('config.schema')
_COMMON = _load('models.catalog_common')
_PREPARE = _load('models.catalog_prepare')
_IDENTITY = _load('services.catalog_identity')
_ARTIFACT = _load('services.catalog_prepared_artifact')
_SERVICE = _load('services.catalog_service')
_STORE = _load('services.catalog_store')

CatalogConfig = _attr(_CONFIG, 'CatalogConfig')
CatalogErrorCode = _attr(_COMMON, 'CatalogErrorCode')
PLAN_STATE_COMMITTED = _attr(_COMMON, 'PLAN_STATE_COMMITTED')
PLAN_STATE_COMMITTING = _attr(_COMMON, 'PLAN_STATE_COMMITTING')
PLAN_STATE_PREPARED = _attr(_COMMON, 'PLAN_STATE_PREPARED')
IDENTITY_SCHEMA_VERSION = _attr(_COMMON, 'IDENTITY_SCHEMA_VERSION')
CommitPreparedCatalogBatchRequest = _attr(_PREPARE, 'CommitPreparedCatalogBatchRequest')
mint_plan_token = _attr(_IDENTITY, 'mint_plan_token')
plan_token_digest = _attr(_IDENTITY, 'plan_token_digest')
catalog_batch_uuid = _attr(_IDENTITY, 'catalog_batch_uuid')
catalog_entity_uuid = _attr(_IDENTITY, 'catalog_entity_uuid')
CANONICALIZATION_VERSION = _attr(_IDENTITY, 'CANONICALIZATION_VERSION')
CATALOG_SCHEMA_VERSION = _attr(_IDENTITY, 'CATALOG_SCHEMA_VERSION')
PREPARED_ARTIFACT_SERIALIZATION_VERSION = _attr(
    _ARTIFACT, 'PREPARED_ARTIFACT_SERIALIZATION_VERSION'
)
serialize_prepared_artifact = _attr(_ARTIFACT, 'serialize_prepared_artifact')
artifact_sha256 = _attr(_ARTIFACT, 'artifact_sha256')
chunk_artifact_bytes = _attr(_ARTIFACT, 'chunk_artifact_bytes')
CatalogService = _attr(_SERVICE, 'CatalogService')
CatalogStoreError = _attr(_STORE, 'CatalogStoreError')
CatalogNeo4jStore = _attr(_STORE, 'CatalogNeo4jStore')
_PLAN_CAS_LEGAL = _attr(_STORE, '_PLAN_CAS_LEGAL')


def _enabled_config() -> Any:
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


def _entity_item() -> dict[str, Any]:
    return {
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


def _frozen_artifact(
    *,
    group_id: str = GROUP,
    batch_id: str = 'batch-recovery-001',
    entity_count: int = 1,
) -> tuple[bytes, str, list[dict[str, Any]], dict[str, Any]]:
    entity_item = _entity_item()
    entity_uuid = catalog_entity_uuid(
        FIXED_NS, group_id, entity_item['entity_type'], entity_item['graph_key']
    )
    request_sha256 = 'c' * 64
    catalog_sha256 = 'd' * 64
    plan_id = 'plan-recovery-001'
    plan_uuid = 'plan-uuid-recovery-001'
    body = {
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
        'canonicalization_version': CANONICALIZATION_VERSION,
        'artifact_serialization_version': PREPARED_ARTIFACT_SERIALIZATION_VERSION,
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
                    'graph_key': entity_item['graph_key'],
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
            'edges': 0,
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
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
        'canonicalization_version': CANONICALIZATION_VERSION,
        'artifact_serialization_version': PREPARED_ARTIFACT_SERIALIZATION_VERSION,
        'request_sha256': request_sha256,
        'catalog_sha256': catalog_sha256,
        'artifact_sha256': art_sha,
        'chunk_count': len(chunks),
        'payload_bytes': len(artifact_bytes),
        'entity_count': entity_count,
        'edge_count': 0,
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
    overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    _, art_sha, chunks, meta = _frozen_artifact()
    now = datetime.now(timezone.utc)
    root: dict[str, Any] = {
        **meta,
        'token_digest': plan_token_digest(token),
        'state': state,
        'expires_at': now + timedelta(hours=1),
        'created_at': now - timedelta(minutes=5),
        'updated_at': now - timedelta(minutes=5),
        'committing_started_at': now if state == PLAN_STATE_COMMITTING else None,
    }
    if overrides:
        root.update(overrides)
    return root, chunks, art_sha


class _FakeDriver:
    def __init__(self) -> None:
        self.tx_count = 0
        self.provider = SimpleNamespace(value='neo4j')

    @asynccontextmanager
    async def transaction(self):
        self.tx_count += 1
        yield SimpleNamespace(run=AsyncMock())

    async def execute_query(self, cypher: str, params=None, **kwargs):
        _ = cypher, params, kwargs
        return ([], None, None)


def _make_client() -> SimpleNamespace:
    driver = _FakeDriver()
    embedder = SimpleNamespace(create=AsyncMock())
    return SimpleNamespace(driver=driver, embedder=embedder, llm_client=None)


def _prep(**kwargs: Any) -> dict[str, Any]:
    return dict(kwargs)


def _wire_recovery_store(
    service: Any,
    *,
    root: dict[str, Any] | None,
    chunks: list[dict[str, Any]] | None = None,
    agree: bool = False,
    snapshot: dict[str, Any] | None = None,
    claim_status: str = 'writing',
    write_boom: Exception | None = None,
) -> dict[str, Any]:
    """Wire store fakes; return mutable counters for recovery assertions."""
    counters: dict[str, Any] = {
        'cas_calls': [],
        'entity_writes': 0,
        'manifest_writes': 0,
        'status_writes': 0,
        'domain_order': [],
    }

    service._store.load_prepared_plan_by_token_digest = AsyncMock(return_value=root)
    service._store.load_prepared_plan_chunks = AsyncMock(return_value=list(chunks or []))

    async def _cas(tx, **kwargs):
        _ = tx
        counters['cas_calls'].append(dict(kwargs))
        to_state = kwargs.get('to_state')
        if to_state == PLAN_STATE_PREPARED:
            raise CatalogStoreError(
                'illegal plan transition COMMITTING->PREPARED',
                code='prepared_plan_conflict',
            )
        base = dict(root or {})
        base['state'] = to_state
        base['updated_at'] = kwargs.get('updated_at')
        if (
            to_state == PLAN_STATE_COMMITTING
            and root
            and root.get('state') == PLAN_STATE_COMMITTING
        ):
            base['reentry'] = True
        return base

    service._store.cas_plan_state = AsyncMock(side_effect=_cas)
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()
    service._store.ensure_evidence_manifest_schema = AsyncMock()
    service._store.ensure_plan_schema = AsyncMock()
    service._store.create_prepared_plan_with_chunks = AsyncMock()
    service._store.lock_prepared_plan_for_commit = AsyncMock(
        return_value={
            'uuid': (root or {}).get('uuid') or 'plan',
            'group_id': (root or {}).get('group_id') or GROUP,
            'state': PLAN_STATE_COMMITTING,
            'locked': True,
        }
    )
    service._store.read_terminal_commit_snapshot = AsyncMock(return_value=snapshot)
    service._store.terminal_commit_agrees = AsyncMock(return_value=agree)

    async def _claim(tx, *, params):
        _ = tx
        counters['domain_order'].append('claim')
        return {
            'uuid': params.get('uuid'),
            'group_id': params.get('group_id'),
            'batch_id': params.get('batch_id'),
            'status': claim_status,
            'request_sha256': params.get('request_sha256'),
        }

    async def _upsert_status(tx, *, params):
        _ = tx
        counters['status_writes'] += 1
        counters['domain_order'].append('status')
        return {
            'uuid': params.get('uuid'),
            'status': params.get('status') or 'committed',
            'request_sha256': params.get('request_sha256'),
        }

    async def _entity(tx, *, entity_type, params):
        _ = tx, entity_type
        if write_boom is not None:
            raise write_boom
        counters['entity_writes'] += 1
        counters['domain_order'].append('entity')
        return {
            'uuid': params.get('uuid'),
            'status': 'created',
            'content_sha256': params.get('content_sha256'),
            'error_code': None,
        }

    async def _manifest(tx, *, root, chunks):
        _ = tx, chunks
        counters['manifest_writes'] += 1
        counters['domain_order'].append('manifest')
        return {
            'uuid': root.get('uuid'),
            'manifest_sha256': root.get('manifest_sha256'),
            'chunk_count': 1,
        }

    service._store.claim_batch_status = AsyncMock(side_effect=_claim)
    service._store.upsert_batch_status = AsyncMock(side_effect=_upsert_status)
    service._store.upsert_entity_item = AsyncMock(side_effect=_entity)
    service._store.upsert_edge_item = AsyncMock(
        return_value={
            'uuid': 'r1',
            'status': 'created',
            'content_sha256': HEX64,
            'error_code': None,
        }
    )
    service._store.upsert_source_episode = AsyncMock(
        return_value={
            'uuid': 's1',
            'status': 'created',
            'source_key': 'SRC',
            'content_sha256': HEX64,
            'error_code': None,
        }
    )
    service._store.upsert_mentions_link = AsyncMock()
    service._store.append_edge_episode = AsyncMock()
    service._store.lock_provenance_targets = AsyncMock(return_value=[])
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.write_evidence_links = AsyncMock(return_value=[])
    service._store.write_manifest_root_and_chunks = AsyncMock(side_effect=_manifest)
    service._store.prepare_entity_params = _prep
    service._store.prepare_edge_params = _prep
    service._store.prepare_source_episode_params = _prep
    service._store.prepare_batch_status_params = _prep
    service._store.prepare_evidence_link_params = _prep
    service._store.prepare_manifest_root_params = _prep
    service._store.prepare_manifest_chunk_params = _prep
    return counters


@pytest.mark.asyncio
async def test_terminal_agreement_returns_stable_receipt():
    """PLAN-15/MANI-07: plan COMMITTED + batch committed + manifest agree → stable receipt."""
    token = mint_plan_token()
    root, chunks, art_sha = _make_root(token=token, state=PLAN_STATE_COMMITTED)
    batch_uuid = catalog_batch_uuid(FIXED_NS, root['group_id'], root['batch_id'])
    manifest_sha = 'f' * 64
    snapshot = {
        'plan_state': PLAN_STATE_COMMITTED,
        'batch_status': 'committed',
        'manifest_sha256': manifest_sha,
        'request_sha256': root['request_sha256'],
        'catalog_sha256': root['catalog_sha256'],
        'artifact_sha256': art_sha,
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
        'batch_id': root['batch_id'],
        'group_id': root['group_id'],
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    counters = _wire_recovery_store(
        service, root=root, chunks=chunks, agree=True, snapshot=snapshot
    )

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code is None
    assert resp.state == PLAN_STATE_COMMITTED
    assert resp.plan_uuid == root['uuid']
    assert resp.batch_uuid == batch_uuid
    assert resp.manifest_sha256 == manifest_sha
    assert resp.committed_created == root['created_count']
    assert counters['entity_writes'] == 0
    assert counters['manifest_writes'] == 0
    # No CAS claim or terminal rewrite on pure terminal agreement.
    assert counters['cas_calls'] == []
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_terminal_fails_closed():
    """PLAN-15: partial terminal evidence fails closed; no repair/silent rewrite."""
    token = mint_plan_token()
    root, chunks, art_sha = _make_root(token=token, state=PLAN_STATE_COMMITTING)
    snapshot = {
        'plan_state': PLAN_STATE_COMMITTING,
        'batch_status': 'committed',
        'manifest_sha256': 'f' * 64,
        'request_sha256': root['request_sha256'],
        'catalog_sha256': root['catalog_sha256'],
        'artifact_sha256': art_sha,
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
        'batch_id': root['batch_id'],
        'group_id': root['group_id'],
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    counters = _wire_recovery_store(
        service, root=root, chunks=chunks, agree=False, snapshot=snapshot
    )

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code == CatalogErrorCode.batch_conflict
    assert resp.state == PLAN_STATE_COMMITTING
    assert counters['entity_writes'] == 0
    assert counters['manifest_writes'] == 0
    # Claim may run (COMMITTING re-entry), but never to PREPARED or COMMITTED success.
    for call in counters['cas_calls']:
        assert call.get('to_state') != PLAN_STATE_PREPARED
        assert not (
            call.get('expected_from') == PLAN_STATE_COMMITTING
            and call.get('to_state') == PLAN_STATE_COMMITTED
        )


@pytest.mark.asyncio
async def test_committing_resume_full_write():
    """PLAN-14/15: stranded COMMITTING with no success artifacts resumes full write."""
    token = mint_plan_token()
    root, chunks, art_sha = _make_root(token=token, state=PLAN_STATE_COMMITTING)
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    counters = _wire_recovery_store(service, root=root, chunks=chunks, agree=False, snapshot=None)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code is None
    assert resp.state == PLAN_STATE_COMMITTED
    assert resp.artifact_sha256 == art_sha
    assert counters['entity_writes'] == 1
    assert counters['manifest_writes'] == 1
    terminal_cas = [
        c
        for c in counters['cas_calls']
        if c.get('to_state') == PLAN_STATE_COMMITTED
        and c.get('expected_from') == PLAN_STATE_COMMITTING
    ]
    assert terminal_cas


@pytest.mark.asyncio
async def test_never_prepared_revival():
    """PLAN-15: COMMITTING must never transition back to PREPARED."""
    assert PLAN_STATE_PREPARED not in _PLAN_CAS_LEGAL.get(PLAN_STATE_COMMITTING, frozenset())
    cas_src = inspect.getsource(CatalogNeo4jStore.cas_plan_state)
    assert 'to_state == PLAN_STATE_PREPARED' in cas_src or 'transition to PREPARED' in cas_src

    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token, state=PLAN_STATE_COMMITTING)
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    counters = _wire_recovery_store(service, root=root, chunks=chunks)

    # Permanent domain conflict leaves COMMITTING; no PREPARED CAS.
    counters_before = len(counters['cas_calls'])
    boom = CatalogStoreError('domain conflict', code='batch_conflict')
    counters2 = _wire_recovery_store(service, root=root, chunks=chunks, write_boom=boom)
    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )
    assert resp.error_code == CatalogErrorCode.batch_conflict
    assert resp.state == PLAN_STATE_COMMITTING
    for call in counters2['cas_calls']:
        assert call.get('to_state') != PLAN_STATE_PREPARED
    _ = counters_before


@pytest.mark.asyncio
async def test_terminal_receipt_idempotent_across_calls():
    """PLAN-15: two successive terminal-agreement reads return equal bounded receipts."""
    token = mint_plan_token()
    root, chunks, art_sha = _make_root(token=token, state=PLAN_STATE_COMMITTED)
    manifest_sha = 'f' * 64
    snapshot = {
        'plan_state': PLAN_STATE_COMMITTED,
        'batch_status': 'committed',
        'manifest_sha256': manifest_sha,
        'request_sha256': root['request_sha256'],
        'catalog_sha256': root['catalog_sha256'],
        'artifact_sha256': art_sha,
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
        'batch_id': root['batch_id'],
        'group_id': root['group_id'],
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    counters = _wire_recovery_store(
        service, root=root, chunks=chunks, agree=True, snapshot=snapshot
    )

    req = CommitPreparedCatalogBatchRequest(plan_token=token)
    r1 = await service.commit_prepared_catalog_batch(client=client, request=req)
    r2 = await service.commit_prepared_catalog_batch(client=client, request=req)

    assert r1.error_code is None and r2.error_code is None
    assert r1.model_dump() == r2.model_dump()
    assert counters['entity_writes'] == 0
    assert counters['manifest_writes'] == 0
    dumped = r1.model_dump()
    assert 'membership' not in dumped
    assert 'plan_token' not in dumped
    assert 'embeddings' not in dumped


@pytest.mark.asyncio
async def test_permanent_conflict_leaves_committing():
    """D-11: permanent domain conflict rolls back; plan remains COMMITTING."""
    token = mint_plan_token()
    root, chunks, _ = _make_root(token=token, state=PLAN_STATE_COMMITTING)
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    boom = CatalogStoreError('invariant race', code='batch_conflict')
    counters = _wire_recovery_store(service, root=root, chunks=chunks, write_boom=boom)

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )

    assert resp.error_code == CatalogErrorCode.batch_conflict
    assert resp.state == PLAN_STATE_COMMITTING
    assert counters['manifest_writes'] == 0
    for call in counters['cas_calls']:
        assert (
            call.get('to_state') != PLAN_STATE_COMMITTED
            or call.get('expected_from') != PLAN_STATE_COMMITTING
            or True
        )
        # No success terminal CAS after boom.
    assert not any(c.get('to_state') == PLAN_STATE_COMMITTED for c in counters['cas_calls'])


def test_no_committing_to_prepared_in_cas_legal():
    """Grep gate: no legal COMMITTING→PREPARED transition."""
    legal = _PLAN_CAS_LEGAL.get(PLAN_STATE_COMMITTING, frozenset())
    assert PLAN_STATE_PREPARED not in legal
    assert PLAN_STATE_COMMITTED in legal
    assert PLAN_STATE_COMMITTING in legal
