"""Concurrent same-token / same-batch commit arbitration (PLAN-16, TEST-06, 03B-05)."""

from __future__ import annotations

import asyncio
import importlib
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
        'attributes': {},
        'source_refs': [],
        'confidence': 0.95,
    }


def _frozen(
    *,
    batch_id: str = 'batch-concurrency-001',
    group_id: str = GROUP,
) -> tuple[bytes, str, list[dict[str, Any]], dict[str, Any]]:
    entity_item = _entity_item()
    entity_uuid = catalog_entity_uuid(
        FIXED_NS, group_id, entity_item['entity_type'], entity_item['graph_key']
    )
    request_sha256 = 'c' * 64
    catalog_sha256 = 'd' * 64
    plan_id = 'plan-concurrency-001'
    plan_uuid = 'plan-uuid-concurrency-001'
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
        'entity_count': 1,
        'edge_count': 0,
        'source_count': 0,
        'evidence_link_count': 0,
        'created_count': 1,
        'updated_count': 0,
        'unchanged_count': 0,
    }
    return artifact_bytes, art_sha, chunks, root_meta


class _SerialLock:
    """Asyncio lock simulating Neo4j plan-row serialization (not process-local authority)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self):
        async with self._lock:
            yield


class _RaceGraph:
    """In-memory durable graph with CAS/uniqueness arbitration for concurrency tests."""

    def __init__(self) -> None:
        self.plan_lock = _SerialLock()
        self.plan_state = PLAN_STATE_PREPARED
        self.batch_status: str | None = None
        self.batch_request_sha: str | None = None
        self.manifests: dict[str, dict[str, Any]] = {}  # batch_id -> root
        self.entities: dict[str, dict[str, Any]] = {}  # uuid -> row
        self.domain_write_count = 0
        self.manifest_write_count = 0
        self.entity_write_count = 0
        self.cas_history: list[tuple[str, str]] = []


class _FakeDriver:
    def __init__(self, graph: _RaceGraph) -> None:
        self._graph = graph
        self.provider = SimpleNamespace(value='neo4j')

    @asynccontextmanager
    async def transaction(self):
        # Serialize success-tx body on plan lock (D-08 Neo4j lock stand-in).
        async with self._graph.plan_lock.hold():
            yield SimpleNamespace(run=AsyncMock(), graph=self._graph)

    async def execute_query(self, cypher: str, params=None, **kwargs):
        _ = cypher, params, kwargs
        return ([], None, None)


def _prep(**kwargs: Any) -> dict[str, Any]:
    return dict(kwargs)


def _wire_race_service(
    service: Any,
    *,
    graph: _RaceGraph,
    root: dict[str, Any],
    chunks: list[dict[str, Any]],
    token: str,
) -> None:
    digest = plan_token_digest(token)

    async def _load_root(driver, *, token_digest: str, tx=None):
        _ = driver, tx
        if token_digest != digest:
            return None
        out = dict(root)
        out['state'] = graph.plan_state
        out['token_digest'] = digest
        return out

    async def _load_chunks(driver, *, plan_uuid: str, group_id: str, tx=None):
        _ = driver, plan_uuid, group_id, tx
        return list(chunks)

    async def _cas(tx, **kwargs):
        _ = tx
        expected_from = kwargs.get('expected_from')
        to_state = kwargs.get('to_state')
        graph.cas_history.append((str(expected_from), str(to_state)))
        if to_state == PLAN_STATE_PREPARED:
            raise CatalogStoreError(
                'transition to PREPARED is forbidden',
                code='prepared_plan_conflict',
            )
        if to_state == PLAN_STATE_COMMITTING:
            if graph.plan_state == PLAN_STATE_COMMITTED:
                raise CatalogStoreError(
                    'prepared plan already consumed',
                    code='prepared_plan_already_consumed',
                )
            if graph.plan_state not in {PLAN_STATE_PREPARED, PLAN_STATE_COMMITTING}:
                raise CatalogStoreError(
                    'prepared plan not claimable',
                    code='prepared_plan_conflict',
                )
            if expected_from != graph.plan_state and not (
                graph.plan_state == PLAN_STATE_COMMITTING and expected_from == PLAN_STATE_COMMITTING
            ):
                # Concurrent claim: allow PREPARED or COMMITTING expected.
                if graph.plan_state == PLAN_STATE_COMMITTING:
                    return {
                        'uuid': root['uuid'],
                        'state': PLAN_STATE_COMMITTING,
                        'reentry': True,
                        'token_digest': digest,
                    }
                raise CatalogStoreError(
                    'plan state mismatch',
                    code='prepared_plan_conflict',
                )
            was = graph.plan_state
            graph.plan_state = PLAN_STATE_COMMITTING
            return {
                'uuid': root['uuid'],
                'state': PLAN_STATE_COMMITTING,
                'reentry': was == PLAN_STATE_COMMITTING,
                'token_digest': digest,
            }
        if to_state == PLAN_STATE_COMMITTED:
            if graph.plan_state != PLAN_STATE_COMMITTING:
                raise CatalogStoreError(
                    'only COMMITTING plans may commit',
                    code='prepared_plan_conflict',
                )
            graph.plan_state = PLAN_STATE_COMMITTED
            return {'uuid': root['uuid'], 'state': PLAN_STATE_COMMITTED}
        raise CatalogStoreError('illegal transition', code='prepared_plan_conflict')

    async def _lock(tx, *, plan_uuid: str, group_id: str):
        _ = tx
        return {
            'uuid': plan_uuid,
            'group_id': group_id,
            'state': graph.plan_state,
            'locked': True,
        }

    async def _snapshot(tx, *, group_id: str, batch_id: str, plan_uuid: str, batch_uuid: str):
        _ = tx, plan_uuid, batch_uuid
        manifest = graph.manifests.get(batch_id)
        return {
            'plan_state': graph.plan_state,
            'batch_status': graph.batch_status,
            'manifest_sha256': (manifest or {}).get('manifest_sha256'),
            'request_sha256': (manifest or {}).get('request_sha256') or root['request_sha256'],
            'catalog_sha256': (manifest or {}).get('catalog_sha256') or root['catalog_sha256'],
            'artifact_sha256': (manifest or {}).get('artifact_sha256') or root['artifact_sha256'],
            'identity_schema_version': IDENTITY_SCHEMA_VERSION,
            'batch_id': batch_id,
            'group_id': group_id,
        }

    async def _agrees(tx, *, projection: dict[str, Any]) -> bool:
        snap = await _snapshot(
            tx,
            group_id=str(projection['group_id']),
            batch_id=str(projection['batch_id']),
            plan_uuid=str(projection['plan_uuid']),
            batch_uuid=str(projection['batch_uuid']),
        )
        if snap['plan_state'] != PLAN_STATE_COMMITTED:
            return False
        if snap['batch_status'] != 'committed':
            return False
        if not snap.get('manifest_sha256'):
            return False
        for key in (
            'manifest_sha256',
            'request_sha256',
            'catalog_sha256',
            'identity_schema_version',
        ):
            if str(snap.get(key) or '') != str(projection.get(key) or ''):
                return False
        return str(snap.get('artifact_sha256') or '') == str(
            projection.get('artifact_sha256') or ''
        )

    async def _claim(tx, *, params):
        _ = tx
        req = params.get('request_sha256')
        if graph.batch_status is None:
            graph.batch_status = 'writing'
            graph.batch_request_sha = req
        elif graph.batch_request_sha != req:
            return {
                'uuid': params.get('uuid'),
                'status': graph.batch_status,
                'request_sha256': graph.batch_request_sha,
            }
        return {
            'uuid': params.get('uuid'),
            'group_id': params.get('group_id'),
            'batch_id': params.get('batch_id'),
            'status': graph.batch_status or 'writing',
            'request_sha256': graph.batch_request_sha or req,
        }

    async def _entity(tx, *, entity_type, params):
        _ = tx, entity_type
        graph.domain_write_count += 1
        graph.entity_write_count += 1
        euuid = str(params.get('uuid'))
        if euuid in graph.entities:
            return {
                'uuid': euuid,
                'status': 'unchanged',
                'content_sha256': params.get('content_sha256'),
                'error_code': None,
            }
        graph.entities[euuid] = dict(params)
        return {
            'uuid': euuid,
            'status': 'created',
            'content_sha256': params.get('content_sha256'),
            'error_code': None,
        }

    async def _manifest(tx, *, root: dict[str, Any], chunks: list[dict[str, Any]]):
        _ = tx, chunks
        batch_id = str(root.get('batch_id'))
        existing = graph.manifests.get(batch_id)
        if existing is not None:
            same = existing.get('manifest_sha256') == root.get('manifest_sha256')
            if not same:
                raise CatalogStoreError(
                    'manifest identity already exists with divergent binding',
                    code='batch_conflict',
                )
            return {**existing, 'idempotent': True}
        graph.manifest_write_count += 1
        graph.domain_write_count += 1
        stored = {
            'uuid': root.get('uuid'),
            'batch_id': batch_id,
            'group_id': root.get('group_id'),
            'manifest_sha256': root.get('manifest_sha256'),
            'request_sha256': root.get('request_sha256'),
            'catalog_sha256': root.get('catalog_sha256'),
            'artifact_sha256': root.get('artifact_sha256'),
            'chunk_count': root.get('chunk_count'),
        }
        graph.manifests[batch_id] = stored
        return stored

    async def _status(tx, *, params):
        _ = tx
        status = params.get('status')
        if status == 'committed':
            graph.batch_status = 'committed'
            graph.batch_request_sha = params.get('request_sha256')
        return {
            'uuid': params.get('uuid'),
            'status': status,
            'request_sha256': params.get('request_sha256'),
        }

    service._store.load_prepared_plan_by_token_digest = AsyncMock(side_effect=_load_root)
    service._store.load_prepared_plan_chunks = AsyncMock(side_effect=_load_chunks)
    service._store.cas_plan_state = AsyncMock(side_effect=_cas)
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()
    service._store.ensure_evidence_manifest_schema = AsyncMock()
    service._store.ensure_plan_schema = AsyncMock()
    service._store.create_prepared_plan_with_chunks = AsyncMock()
    service._store.lock_prepared_plan_for_commit = AsyncMock(side_effect=_lock)
    service._store.read_terminal_commit_snapshot = AsyncMock(side_effect=_snapshot)
    service._store.terminal_commit_agrees = AsyncMock(side_effect=_agrees)
    service._store.claim_batch_status = AsyncMock(side_effect=_claim)
    service._store.upsert_batch_status = AsyncMock(side_effect=_status)
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


def _client(graph: _RaceGraph) -> SimpleNamespace:
    return SimpleNamespace(
        driver=_FakeDriver(graph),
        embedder=SimpleNamespace(create=AsyncMock()),
        llm_client=SimpleNamespace(generate=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_same_token_concurrent_one_logical_commit():
    """PLAN-16/TEST-06: concurrent same-token commits → one logical commit."""
    token = mint_plan_token()
    _, art_sha, chunks, meta = _frozen()
    now = datetime.now(timezone.utc)
    root = {
        **meta,
        'token_digest': plan_token_digest(token),
        'state': PLAN_STATE_PREPARED,
        'expires_at': now + timedelta(hours=1),
        'created_at': now - timedelta(minutes=5),
        'updated_at': now - timedelta(minutes=5),
    }
    graph = _RaceGraph()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_race_service(service, graph=graph, root=root, chunks=chunks, token=token)
    client = _client(graph)
    req = CommitPreparedCatalogBatchRequest(plan_token=token)

    results = await asyncio.gather(
        *[service.commit_prepared_catalog_batch(client=client, request=req) for _ in range(5)]
    )

    successes = [r for r in results if r.error_code is None]
    assert successes
    assert all(r.state == PLAN_STATE_COMMITTED for r in successes)
    # One logical plan terminal + one manifest root.
    assert graph.plan_state == PLAN_STATE_COMMITTED
    assert len(graph.manifests) == 1
    # Followers short-circuit; only one first writer creates domain.
    assert graph.entity_write_count == 1
    assert graph.manifest_write_count == 1
    manifests_sha = {m['manifest_sha256'] for m in graph.manifests.values()}
    assert len(manifests_sha) == 1
    _ = art_sha


@pytest.mark.asyncio
async def test_same_batch_different_tokens_converge_or_deterministic_conflict():
    """PLAN-16: different tokens same batch → one manifest or deterministic conflict.

    Error code reuses existing registry: batch_conflict / prepared_plan_conflict.
    """
    token_a = mint_plan_token()
    token_b = mint_plan_token()
    assert token_a != token_b
    _, _, chunks, meta = _frozen(batch_id='batch-shared-001')
    now = datetime.now(timezone.utc)

    # Two distinct plans for same group/batch/request identity (different tokens).
    root_a = {
        **meta,
        'uuid': 'plan-a',
        'token_digest': plan_token_digest(token_a),
        'state': PLAN_STATE_PREPARED,
        'expires_at': now + timedelta(hours=1),
        'created_at': now - timedelta(minutes=5),
        'updated_at': now - timedelta(minutes=5),
    }
    root_b = {
        **meta,
        'uuid': 'plan-b',
        'token_digest': plan_token_digest(token_b),
        'state': PLAN_STATE_PREPARED,
        'expires_at': now + timedelta(hours=1),
        'created_at': now - timedelta(minutes=5),
        'updated_at': now - timedelta(minutes=5),
    }

    graph = _RaceGraph()
    # Separate plan-state map keyed by token digest for multi-token race.
    plan_states = {
        plan_token_digest(token_a): PLAN_STATE_PREPARED,
        plan_token_digest(token_b): PLAN_STATE_PREPARED,
    }
    roots = {
        plan_token_digest(token_a): root_a,
        plan_token_digest(token_b): root_b,
    }

    service = CatalogService(catalog_config=_enabled_config())

    async def _load_root(driver, *, token_digest: str, tx=None):
        _ = driver, tx
        r = roots.get(token_digest)
        if r is None:
            return None
        out = dict(r)
        out['state'] = plan_states[token_digest]
        return out

    async def _load_chunks(driver, *, plan_uuid: str, group_id: str, tx=None):
        _ = driver, plan_uuid, group_id, tx
        return list(chunks)

    async def _cas(tx, **kwargs):
        _ = tx
        digest = kwargs.get('token_digest')
        # cas_plan_state uses token_digest kw — our wire must pass it.
        # Service always passes token_digest from claim path.
        to_state = kwargs.get('to_state')
        expected_from = kwargs.get('expected_from')
        # Find digest from root match if missing (claim path includes it).
        if digest is None:
            raise CatalogStoreError('token_digest required', code='validation_error')
        if to_state == PLAN_STATE_PREPARED:
            raise CatalogStoreError(
                'transition to PREPARED is forbidden',
                code='prepared_plan_conflict',
            )
        cur = plan_states[str(digest)]
        if to_state == PLAN_STATE_COMMITTING:
            if cur == PLAN_STATE_COMMITTED:
                raise CatalogStoreError(
                    'prepared plan already consumed',
                    code='prepared_plan_already_consumed',
                )
            if cur not in {PLAN_STATE_PREPARED, PLAN_STATE_COMMITTING}:
                raise CatalogStoreError('not claimable', code='prepared_plan_conflict')
            if expected_from == PLAN_STATE_COMMITTING and cur == PLAN_STATE_COMMITTING:
                return {'uuid': roots[str(digest)]['uuid'], 'state': cur, 'reentry': True}
            plan_states[str(digest)] = PLAN_STATE_COMMITTING
            return {'uuid': roots[str(digest)]['uuid'], 'state': PLAN_STATE_COMMITTING}
        if to_state == PLAN_STATE_COMMITTED:
            if cur != PLAN_STATE_COMMITTING:
                raise CatalogStoreError('only COMMITTING', code='prepared_plan_conflict')
            plan_states[str(digest)] = PLAN_STATE_COMMITTED
            graph.plan_state = PLAN_STATE_COMMITTED
            return {'uuid': roots[str(digest)]['uuid'], 'state': PLAN_STATE_COMMITTED}
        raise CatalogStoreError('illegal', code='prepared_plan_conflict')

    # Reuse single-token wire then override multi-token load/cas.
    _wire_race_service(service, graph=graph, root=root_a, chunks=chunks, token=token_a)
    service._store.load_prepared_plan_by_token_digest = AsyncMock(side_effect=_load_root)
    service._store.load_prepared_plan_chunks = AsyncMock(side_effect=_load_chunks)
    service._store.cas_plan_state = AsyncMock(side_effect=_cas)

    # lock/snapshot must consult per-plan state via graph.plan_state loosely:
    # after first commit, second token hits create-once manifest with same binding → converge.
    client = _client(graph)

    async def _commit(tok: str):
        return await service.commit_prepared_catalog_batch(
            client=client,
            request=CommitPreparedCatalogBatchRequest(plan_token=tok),
        )

    r_a, r_b = await asyncio.gather(_commit(token_a), _commit(token_b))

    # Never two divergent manifests.
    assert len(graph.manifests) <= 1
    outcomes = [r_a, r_b]
    ok = [r for r in outcomes if r.error_code is None]
    err = [r for r in outcomes if r.error_code is not None]
    # At least one success or both deterministic conflict; never silent dual success with dups.
    if len(ok) == 2:
        assert ok[0].manifest_sha256 == ok[1].manifest_sha256
        assert len(graph.manifests) == 1
    else:
        assert ok or err
        for e in err:
            assert e.error_code in {
                CatalogErrorCode.batch_conflict,
                CatalogErrorCode.prepared_plan_conflict,
                CatalogErrorCode.prepared_plan_already_consumed,
            }


@pytest.mark.asyncio
async def test_no_duplicate_manifest_under_race():
    """PLAN-16/TEST-06: concurrent winners leave exactly one CatalogBatchManifest."""
    token = mint_plan_token()
    _, _, chunks, meta = _frozen(batch_id='batch-race-manifest')
    now = datetime.now(timezone.utc)
    root = {
        **meta,
        'token_digest': plan_token_digest(token),
        'state': PLAN_STATE_PREPARED,
        'expires_at': now + timedelta(hours=1),
        'created_at': now - timedelta(minutes=5),
        'updated_at': now - timedelta(minutes=5),
    }
    graph = _RaceGraph()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_race_service(service, graph=graph, root=root, chunks=chunks, token=token)
    client = _client(graph)
    req = CommitPreparedCatalogBatchRequest(plan_token=token)

    await asyncio.gather(
        *[service.commit_prepared_catalog_batch(client=client, request=req) for _ in range(8)]
    )

    assert len(graph.manifests) == 1
    assert graph.manifest_write_count == 1


@pytest.mark.asyncio
async def test_no_duplicate_domain_under_race():
    """PLAN-16: concurrent same-token races leave no duplicate entity rows."""
    token = mint_plan_token()
    _, _, chunks, meta = _frozen(batch_id='batch-race-entity')
    now = datetime.now(timezone.utc)
    root = {
        **meta,
        'token_digest': plan_token_digest(token),
        'state': PLAN_STATE_PREPARED,
        'expires_at': now + timedelta(hours=1),
        'created_at': now - timedelta(minutes=5),
        'updated_at': now - timedelta(minutes=5),
    }
    graph = _RaceGraph()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_race_service(service, graph=graph, root=root, chunks=chunks, token=token)
    client = _client(graph)
    req = CommitPreparedCatalogBatchRequest(plan_token=token)

    await asyncio.gather(
        *[service.commit_prepared_catalog_batch(client=client, request=req) for _ in range(8)]
    )

    assert len(graph.entities) == 1
    assert graph.entity_write_count == 1
    assert graph.plan_state == PLAN_STATE_COMMITTED
