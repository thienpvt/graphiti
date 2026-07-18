"""Public manifest read + pagination (MANI-05, IDEN-08) — Plan 04-03 GREEN.

Durable category order is authority; fail closed on missing/incomplete/hash-mismatch;
compact projection only. No live batch_id membership synthesis.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_common import CatalogErrorCode  # noqa: E402
from models.catalog_entities import GetCatalogBatchManifestRequest  # noqa: E402
from services.catalog_capabilities import HARD_MAX_PAGE_SIZE  # noqa: E402
from services.catalog_manifest import (  # noqa: E402
    build_manifest_body_from_membership,
    page_members,
    serialize_manifest_body,
)
from services.catalog_manifest import (  # noqa: E402
    manifest_sha256 as pure_manifest_sha256,
)
from services.catalog_service import CatalogService  # noqa: E402

GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-manifest-read-001'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
DEFAULT_MAX_PAGE_SIZE = 100
# HARD_MAX_PAGE_SIZE imported from capabilities (500)


def _neo4j_client() -> SimpleNamespace:
    provider = SimpleNamespace(value='neo4j')
    driver = SimpleNamespace(provider=provider, execute_write=AsyncMock())
    embedder = SimpleNamespace(create=AsyncMock(), create_batch=AsyncMock())
    return SimpleNamespace(driver=driver, embedder=embedder, llm_client=None)


def _service(**cfg_kw: Any) -> CatalogService:
    defaults = {
        'enabled': False,
        'reads_enabled': True,
        'uuid_namespace': str(FIXED_NS),
        'max_page_size': DEFAULT_MAX_PAGE_SIZE,
    }
    defaults.update(cfg_kw)
    return CatalogService(catalog_config=CatalogConfig(**defaults))


def _four_membership() -> dict[str, Any]:
    return {
        'entities': [
            {
                'uuid': 'e1',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.DEPARTMENTS',
                'content_sha256': 'b' * 64,
                'projected_status': 'unchanged',
            },
            {
                'uuid': 'e2',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': 'a' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 'e3',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.JOBS',
                'content_sha256': 'c' * 64,
                'projected_status': 'updated',
            },
        ],
        'edges': [
            {
                'uuid': 'r1',
                'edge_type': 'ForeignKeyTo',
                'edge_key': 'FK::EMP->DEPT',
                'content_sha256': 'd' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 'r2',
                'edge_type': 'ForeignKeyTo',
                'edge_key': 'FK::EMP->JOB',
                'content_sha256': 'e' * 64,
                'projected_status': 'unchanged',
            },
        ],
        'sources': [
            {
                'uuid': 's1',
                'source_key': 'SRC::ddl.sql#employees',
                'content_sha256': 'f' * 64,
                'projected_status': 'created',
            }
        ],
        'evidence_links': [
            {
                'uuid': 'l1',
                'link_key': 'SRC::ddl.sql#employees|entity|Table|TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': '1' * 64,
            }
        ],
    }


def _build_committed_fixture(
    membership: dict[str, Any] | None = None,
    *,
    corrupt_digest: bool = False,
    drop_chunks: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Return (root, chunks_with_payload, body) for a committed durable manifest."""
    membership = membership if membership is not None else _four_membership()
    body = build_manifest_body_from_membership(
        group_id=GROUP,
        batch_id=BATCH,
        request_sha256='r' * 64,
        catalog_sha256='c' * 64,
        membership=membership,
        artifact_sha256='a' * 64,
    )
    raw = serialize_manifest_body(body)
    digest = pure_manifest_sha256(raw)
    # Single chunk for simplicity.
    payload_b64 = base64.b64encode(raw).decode('ascii')
    chunk_sha = hashlib.sha256(raw).hexdigest()
    chunks = [
        {
            'uuid': 'chunk-0',
            'group_id': GROUP,
            'manifest_uuid': 'manifest-uuid-1',
            'chunk_index': 0,
            'chunk_count': 1,
            'byte_offset': 0,
            'byte_length': len(raw),
            'chunk_sha256': chunk_sha,
            'payload_b64': payload_b64,
        }
    ]
    root = {
        'uuid': 'manifest-uuid-1',
        'group_id': GROUP,
        'batch_id': BATCH,
        'manifest_sha256': ('0' * 64) if corrupt_digest else digest,
        'request_sha256': 'r' * 64,
        'catalog_sha256': 'c' * 64,
        'artifact_sha256': 'a' * 64,
        'identity_schema_version': 'catalog-v2',
        'chunk_count': 1,
        'payload_bytes': len(raw),
    }
    if drop_chunks:
        chunks = []
    return root, chunks, body


def _wire_store(
    service: CatalogService,
    *,
    root: dict[str, Any] | None,
    chunks: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Stub store read methods; return call log for write/schema spy."""
    calls: list[str] = []

    async def read_root(executor, *, group_id, batch_id, tx=None):
        calls.append(f'read_root:{group_id}:{batch_id}')
        return root

    async def load_chunks(executor, *, manifest_uuid, group_id, tx=None):
        calls.append(f'load_chunks:{manifest_uuid}:{group_id}')
        return list(chunks or [])

    async def banned(*_a, **_k):
        calls.append('BANNED_WRITE_OR_SCHEMA')
        raise AssertionError('write/schema must not be called on manifest read')

    service._store.read_manifest_root_for_recovery = read_root  # type: ignore[method-assign]
    service._store.load_manifest_chunks_with_payload = load_chunks  # type: ignore[method-assign]
    # Spy common write/schema entry points if present.
    for name in (
        'ensure_evidence_manifest_schema',
        'ensure_catalog_schema',
        'write_entity',
        'write_edge',
        'create_manifest_root',
    ):
        if hasattr(service._store, name):
            setattr(service._store, name, banned)
    return calls


@pytest.mark.asyncio
async def test_manifest_page_stable_order():
    """MANI-05 ordering: page order == Phase 3B canonical category order; stable rereads."""
    assert GROUP == 'oracle-catalog-tool-test'
    root, chunks, body = _build_committed_fixture()
    service = _service()
    _wire_store(service, root=root, chunks=chunks)
    client = _neo4j_client()

    req = GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=10)
    r1 = await service.get_catalog_batch_manifest(client=client, request=req)
    r2 = await service.get_catalog_batch_manifest(client=client, request=req)

    assert r1.found is True
    assert r1.error_code is None
    # Body already sorted by graph_key then uuid.
    expected_keys = [e['graph_key'] for e in body['entities']]
    assert [e.graph_key for e in r1.entities] == expected_keys
    assert [e.graph_key for e in r2.entities] == expected_keys
    assert [e.uuid for e in r1.entities] == [e.uuid for e in r2.entities]
    assert r1.entity_count == len(body['entities'])
    assert r1.edge_count == len(body['edges'])
    assert r1.manifest_sha256 == root['manifest_sha256']
    assert r1.request_sha256 == 'r' * 64
    assert r1.identity_schema_version == 'catalog-v2'


@pytest.mark.asyncio
async def test_empty_categories_legal():
    """MANI-05 empty: empty category membership → empty page total 0; authority still manifest."""
    empty = {'entities': [], 'edges': [], 'sources': [], 'evidence_links': []}
    root, chunks, _body = _build_committed_fixture(empty)
    service = _service()
    _wire_store(service, root=root, chunks=chunks)
    resp = await service.get_catalog_batch_manifest(
        client=_neo4j_client(),
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=10),
    )
    assert resp.found is True
    assert resp.error_code is None
    assert resp.entity_count == 0
    assert resp.edge_count == 0
    assert resp.source_count == 0
    assert resp.evidence_link_count == 0
    assert resp.entities == []
    assert resp.edges == []


@pytest.mark.asyncio
async def test_adjacency_equal_keys_distinct():
    """MANI-05 adjacency: adjacent offset windows no silent overlap/drop."""
    # Two members sharing sort-key prefix path remain distinct rows.
    membership = {
        'entities': [
            {
                'uuid': 'u-aaa',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::SAME',
                'content_sha256': '1' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 'u-bbb',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::SAME',
                'content_sha256': '2' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 'u-ccc',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ZZZ',
                'content_sha256': '3' * 64,
                'projected_status': 'created',
            },
        ],
        'edges': [],
        'sources': [],
        'evidence_links': [],
    }
    root, chunks, body = _build_committed_fixture(membership)
    service = _service()
    _wire_store(service, root=root, chunks=chunks)
    client = _neo4j_client()

    p0 = await service.get_catalog_batch_manifest(
        client=client,
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=1),
    )
    p1 = await service.get_catalog_batch_manifest(
        client=client,
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=1, limit=1),
    )
    p2 = await service.get_catalog_batch_manifest(
        client=client,
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=2, limit=1),
    )
    assert p0.entity_count == 3
    assert len(p0.entities) == 1 and len(p1.entities) == 1 and len(p2.entities) == 1
    uuids = {p0.entities[0].uuid, p1.entities[0].uuid, p2.entities[0].uuid}
    assert uuids == {e['uuid'] for e in body['entities']}
    # Adjacent pages must not overlap.
    assert p0.entities[0].uuid != p1.entities[0].uuid
    assert p1.entities[0].uuid != p2.entities[0].uuid


@pytest.mark.asyncio
async def test_page_size_above_hard_max_fail_closed():
    """MANI-05 boundary: page size above hard max (500) fails closed; default configured 100."""
    assert DEFAULT_MAX_PAGE_SIZE == 100
    assert HARD_MAX_PAGE_SIZE == 500
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    calls = _wire_store(service, root=root, chunks=chunks)
    resp = await service.get_catalog_batch_manifest(
        client=_neo4j_client(),
        request=GetCatalogBatchManifestRequest(
            group_id=GROUP, batch_id=BATCH, offset=0, limit=HARD_MAX_PAGE_SIZE + 1
        ),
    )
    assert resp.found is False
    assert resp.error_code == CatalogErrorCode.validation_error
    assert 'hard max' in (resp.error_message or '').lower()
    # Fail closed before store access.
    assert not any(c.startswith('read_root') for c in calls)


@pytest.mark.asyncio
async def test_missing_incomplete_hash_mismatch_fail_closed():
    """MANI-05 / VERI-05: missing root, incomplete chunks, hash mismatch → fail closed."""
    service = _service()
    client = _neo4j_client()

    # Missing root → found=False, no live synthesis.
    _wire_store(service, root=None, chunks=[])
    missing = await service.get_catalog_batch_manifest(
        client=client,
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=10),
    )
    assert missing.found is False
    assert missing.error_code == CatalogErrorCode.manifest_mismatch
    assert missing.entities == []

    # Incomplete chunks.
    root, _chunks, _ = _build_committed_fixture(drop_chunks=True)
    # root still says chunk_count=1 but chunks empty
    root, full_chunks, _ = _build_committed_fixture()
    _wire_store(service, root=root, chunks=[])
    incomplete = await service.get_catalog_batch_manifest(
        client=client,
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=10),
    )
    assert incomplete.error_code == CatalogErrorCode.manifest_mismatch
    assert incomplete.entities == []

    # Hash mismatch.
    root_bad, chunks_bad, _ = _build_committed_fixture(corrupt_digest=True)
    _wire_store(service, root=root_bad, chunks=chunks_bad)
    mismatch = await service.get_catalog_batch_manifest(
        client=client,
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=10),
    )
    assert mismatch.error_code == CatalogErrorCode.manifest_mismatch
    assert mismatch.entities == []


@pytest.mark.asyncio
async def test_compact_projection_no_embeddings_payload_source():
    """MANI-05: compact projection omits embeddings, payload_b64, and source text."""
    membership = _four_membership()
    # Inject forbidden fields into durable body source material — must be stripped by compact.
    membership['entities'][0]['name_embedding'] = [0.1, 0.2]
    membership['entities'][0]['payload_b64'] = 'SECRET'
    membership['entities'][0]['raw_text'] = 'CREATE TABLE secret'
    membership['entities'][0]['password'] = 'hunter2'
    root, chunks, _ = _build_committed_fixture(membership)
    service = _service()
    _wire_store(service, root=root, chunks=chunks)
    resp = await service.get_catalog_batch_manifest(
        client=_neo4j_client(),
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=50),
    )
    assert resp.found is True
    dumped = resp.model_dump()
    blob = json.dumps(dumped)
    for banned in (
        'name_embedding',
        'fact_embedding',
        'payload_b64',
        'embedding',
        'raw_text',
        'password',
        'CREATE TABLE secret',
        'hunter2',
        'SECRET',
    ):
        assert banned not in blob
    # Only compact fields on members.
    for ent in resp.entities:
        fields = set(ent.model_dump().keys())
        assert fields <= {
            'uuid',
            'entity_type',
            'graph_key',
            'content_sha256',
            'projected_status',
        }


@pytest.mark.asyncio
async def test_graph_key_complete():
    """IDEN-08: every entity-identifying field is full system-scoped graph_key (not name-only)."""
    root, chunks, body = _build_committed_fixture()
    service = _service()
    _wire_store(service, root=root, chunks=chunks)
    resp = await service.get_catalog_batch_manifest(
        client=_neo4j_client(),
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=50),
    )
    assert resp.found is True
    assert resp.entities
    for ent in resp.entities:
        assert '::' in ent.graph_key
        assert ent.graph_key.startswith('TABLE::')
        # Not name-only
        assert '.' in ent.graph_key or ent.graph_key.count('::') >= 2
        assert ent.graph_key in {e['graph_key'] for e in body['entities']}
    for edge in resp.edges:
        assert edge.edge_key
        assert '::' in edge.edge_key or edge.edge_key.startswith('FK')


@pytest.mark.asyncio
async def test_unchanged_shared_entities_remain_members():
    """TEST-08 / MANI-05: unchanged shared entities remain manifest members (not dropped)."""
    root, chunks, body = _build_committed_fixture()
    unchanged = [e for e in body['entities'] if e.get('projected_status') == 'unchanged']
    assert unchanged, 'fixture must include unchanged members'
    service = _service()
    _wire_store(service, root=root, chunks=chunks)
    resp = await service.get_catalog_batch_manifest(
        client=_neo4j_client(),
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=50),
    )
    statuses = {e.graph_key: e.projected_status for e in resp.entities}
    for row in unchanged:
        assert statuses.get(row['graph_key']) == 'unchanged'
    # Edges with unchanged also retained.
    edge_statuses = {e.edge_key: e.projected_status for e in resp.edges}
    assert 'FK::EMP->JOB' in edge_statuses
    assert edge_statuses['FK::EMP->JOB'] == 'unchanged'


@pytest.mark.asyncio
async def test_concurrent_same_params_identical_page():
    """MANI-05 concurrency: concurrent identical page reads return identical contents."""
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    _wire_store(service, root=root, chunks=chunks)
    client = _neo4j_client()
    req = GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH, offset=0, limit=2)

    results = await asyncio.gather(
        service.get_catalog_batch_manifest(client=client, request=req),
        service.get_catalog_batch_manifest(client=client, request=req),
        service.get_catalog_batch_manifest(client=client, request=req),
    )
    dumps = [r.model_dump() for r in results]
    assert dumps[0] == dumps[1] == dumps[2]
    assert results[0].found is True
    assert len(results[0].entities) == 2


def test_page_members_pure_helper():
    """page_members slices durable order only; hard max fail-closed."""
    items = [{'uuid': str(i)} for i in range(5)]
    page, total = page_members(items, offset=1, limit=2)
    assert total == 5
    assert [x['uuid'] for x in page] == ['1', '2']
    with pytest.raises(ValueError):
        page_members(items, offset=-1, limit=1)
    with pytest.raises(ValueError):
        page_members(items, offset=0, limit=0)
    with pytest.raises(ValueError):
        page_members(items, offset=0, limit=HARD_MAX_PAGE_SIZE + 1, hard_max=HARD_MAX_PAGE_SIZE)


@pytest.mark.asyncio
async def test_counts_list_length_mismatch_fail_closed():
    """WR-05: any of four category counts disagreeing list length => manifest_mismatch."""
    service = _service()
    client = _neo4j_client()
    membership = _four_membership()
    body = build_manifest_body_from_membership(
        group_id=GROUP,
        batch_id=BATCH,
        request_sha256='r' * 64,
        catalog_sha256='c' * 64,
        membership=membership,
        artifact_sha256='a' * 64,
    )
    body = dict(body)
    counts = dict(body['counts'])
    counts['entities'] = counts['entities'] + 1
    body['counts'] = counts
    raw = serialize_manifest_body(body)
    digest = pure_manifest_sha256(raw)
    payload_b64 = base64.b64encode(raw).decode('ascii')
    chunk_sha = hashlib.sha256(raw).hexdigest()
    root = {
        'uuid': 'manifest-uuid-counts',
        'group_id': GROUP,
        'batch_id': BATCH,
        'manifest_sha256': digest,
        'request_sha256': 'r' * 64,
        'catalog_sha256': 'c' * 64,
        'artifact_sha256': 'a' * 64,
        'identity_schema_version': 'catalog-v2',
        'chunk_count': 1,
        'payload_bytes': len(raw),
    }
    chunks = [
        {
            'uuid': 'chunk-0',
            'group_id': GROUP,
            'manifest_uuid': root['uuid'],
            'chunk_index': 0,
            'chunk_count': 1,
            'byte_offset': 0,
            'byte_length': len(raw),
            'chunk_sha256': chunk_sha,
            'payload_b64': payload_b64,
        }
    ]

    async def read_root(executor, *, group_id, batch_id, tx=None):
        return root

    async def load_chunks(executor, *, manifest_uuid, group_id, tx=None):
        return list(chunks)

    service._store.read_manifest_root_for_recovery = read_root  # type: ignore[method-assign]
    service._store.load_manifest_chunks_with_payload = load_chunks  # type: ignore[method-assign]
    req = GetCatalogBatchManifestRequest(
        group_id=GROUP,
        batch_id=BATCH,
        offset=0,
        limit=10,
    )
    resp = await service.get_catalog_batch_manifest(client=client, request=req)
    assert resp.error_code == CatalogErrorCode.manifest_mismatch
    assert 'counts' in (resp.error_message or '')
