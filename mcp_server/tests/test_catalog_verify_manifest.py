"""Manifest-backed verify rewire (VERI-01..06, EVID-13, TEST-08) — Plan 04-04 GREEN.

Durable manifest is sole batch expected authority; live rows are observations only;
never expected=len(live). Keys-only path preserved.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
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
from models.catalog_entities import (  # noqa: E402
    VerifyCatalogBatchRequest,
    VerifyEntityRef,
)
from services.catalog_identity import catalog_edge_uuid, catalog_entity_uuid  # noqa: E402
from services.catalog_manifest import (  # noqa: E402
    build_manifest_body_from_membership,
    serialize_manifest_body,
)
from services.catalog_manifest import (  # noqa: E402
    manifest_sha256 as pure_manifest_sha256,
)
from services.catalog_service import CatalogService  # noqa: E402

GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-verify-manifest-001'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')

ENTITY_A = 'TABLE::FE::ORCL.HR.EMPLOYEES'
ENTITY_B = 'TABLE::FE::ORCL.HR.DEPARTMENTS'
ENTITY_C = 'TABLE::FE::ORCL.HR.JOBS'
EDGE_A = 'FK::EMP->DEPT'
EDGE_B = 'FK::EMP->JOB'
EVID_UUID = 'evidence-uuid-1'
EVID_KEY = 'SRC::ddl.sql#employees|entity|Table|TABLE::FE::ORCL.HR.EMPLOYEES'


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
    }
    defaults.update(cfg_kw)
    return CatalogService(catalog_config=CatalogConfig(**defaults))


def _membership(
    *,
    entities: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    evidence_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if entities is None:
        entities = [
            {
                'uuid': catalog_entity_uuid(FIXED_NS, GROUP, 'Table', ENTITY_A),
                'entity_type': 'Table',
                'graph_key': ENTITY_A,
                'content_sha256': 'a' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': catalog_entity_uuid(FIXED_NS, GROUP, 'Table', ENTITY_B),
                'entity_type': 'Table',
                'graph_key': ENTITY_B,
                'content_sha256': 'b' * 64,
                'projected_status': 'unchanged',
            },
        ]
    if edges is None:
        edges = [
            {
                'uuid': catalog_edge_uuid(FIXED_NS, GROUP, 'ForeignKeyTo', EDGE_A),
                'edge_type': 'ForeignKeyTo',
                'edge_key': EDGE_A,
                'content_sha256': 'd' * 64,
                'projected_status': 'created',
            }
        ]
    if sources is None:
        sources = []
    if evidence_links is None:
        evidence_links = [
            {
                'uuid': EVID_UUID,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ]
    return {
        'entities': entities,
        'edges': edges,
        'sources': sources,
        'evidence_links': evidence_links,
    }


def _build_committed_fixture(
    membership: dict[str, Any] | None = None,
    *,
    corrupt_digest: bool = False,
    drop_chunks: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    membership = membership if membership is not None else _membership()
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


def _status_row(*, status: str = 'committed') -> dict[str, Any]:
    return {
        'uuid': 'batch-uuid-1',
        'group_id': GROUP,
        'batch_id': BATCH,
        'status': status,
        'entity_count': 2,
        'edge_count': 1,
        'provenance_count': 1,
    }


def _wire_store(
    service: CatalogService,
    *,
    status: dict[str, Any] | None = ...,  # type: ignore[assignment]
    root: dict[str, Any] | None = None,
    chunks: list[dict[str, Any]] | None = None,
    entity_rows: list[dict[str, Any]] | None = None,
    edge_rows: list[dict[str, Any]] | None = None,
    evidence_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Stub store read methods; return call log for write/schema spy."""
    calls: list[str] = []

    async def get_status(executor, *, uuid, group_id, tx=None):
        calls.append(f'get_status:{group_id}')
        if status is ...:
            return _status_row()
        return status

    async def read_root(executor, *, group_id, batch_id, tx=None):
        calls.append(f'read_root:{group_id}:{batch_id}')
        return root

    async def load_chunks(executor, *, manifest_uuid, group_id, tx=None):
        calls.append(f'load_chunks:{manifest_uuid}:{group_id}')
        return list(chunks or [])

    async def match_entities(executor, *, group_id, batch_id=None, graph_keys=None, tx=None):
        calls.append(f'match_entities:{group_id}:{batch_id}:{len(graph_keys or [])}')
        return list(entity_rows or [])

    async def match_edges(executor, *, group_id, batch_id=None, edge_keys=None, tx=None):
        calls.append(f'match_edges:{group_id}:{batch_id}:{len(edge_keys or [])}')
        return list(edge_rows or [])

    async def match_evidence(executor, *, group_id, uuids, tx=None):
        calls.append(f'match_evidence:{group_id}:{len(uuids)}')
        return list(evidence_rows or [])

    async def match_evidence_batch(executor, *, group_id, batch_id, tx=None):
        calls.append(f'match_evidence_batch:{group_id}:{batch_id}')
        # Observation scope for extras: same fixture rows by default.
        return list(evidence_rows or [])

    async def match_prov(executor, *, group_id, target_uuids, tx=None):
        calls.append(f'match_prov:{group_id}:{len(target_uuids)}')
        return []

    async def banned(*_a, **_k):
        calls.append('BANNED_WRITE_OR_SCHEMA')
        raise AssertionError('write/schema must not be called on verify')

    service._store.get_batch_status = get_status  # type: ignore[method-assign]
    service._store.read_manifest_root_for_recovery = read_root  # type: ignore[method-assign]
    service._store.load_manifest_chunks_with_payload = load_chunks  # type: ignore[method-assign]
    service._store.match_entities_for_verify = match_entities  # type: ignore[method-assign]
    service._store.match_edges_for_verify = match_edges  # type: ignore[method-assign]
    service._store.match_evidence_links_exact = match_evidence  # type: ignore[method-assign]
    service._store.match_evidence_links_for_batch = match_evidence_batch  # type: ignore[method-assign]
    service._store.match_provenance_presence = match_prov  # type: ignore[method-assign]
    for name in (
        'ensure_evidence_manifest_schema',
        'ensure_catalog_schema',
        'upsert_entity_item',
        'upsert_edge_item',
        'write_evidence_links',
    ):
        if hasattr(service._store, name):
            setattr(service._store, name, banned)
    return calls


def _verify_request(**kwargs: Any) -> VerifyCatalogBatchRequest:
    data: dict[str, Any] = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': GROUP,
        'batch_id': BATCH,
        'entities': [],
        'edges': [],
        'require_provenance': False,
    }
    data.update(kwargs)
    return VerifyCatalogBatchRequest.model_validate(data)


def _entity_row(
    graph_key: str,
    *,
    entity_type: str = 'Table',
    has_emb: bool = True,
    content_sha: str | None = None,
    uuid_val: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        'uuid': uuid_val or catalog_entity_uuid(FIXED_NS, GROUP, entity_type, graph_key),
        'graph_key': graph_key,
        'name': graph_key,
        'labels': labels or ['Entity', entity_type],
        'neo4j_labels': labels or ['Entity', entity_type],
        'content_sha256': content_sha if content_sha is not None else 'a' * 64,
        'has_name_embedding': has_emb,
        'batch_id': BATCH,
        'element_id': f'el-{graph_key}',
    }


def _edge_row(
    edge_key: str,
    *,
    edge_type: str = 'ForeignKeyTo',
    has_emb: bool = True,
    content_sha: str | None = None,
    uuid_val: str | None = None,
    source_uuid: str | None = 'src-uuid',
    target_uuid: str | None = 'tgt-uuid',
) -> dict[str, Any]:
    return {
        'uuid': uuid_val or catalog_edge_uuid(FIXED_NS, GROUP, edge_type, edge_key),
        'edge_key': edge_key,
        'edge_type': edge_type,
        'content_sha256': content_sha if content_sha is not None else 'd' * 64,
        'has_fact_embedding': has_emb,
        'source_uuid': source_uuid,
        'target_uuid': target_uuid,
        'batch_id': BATCH,
        'element_id': f'el-{edge_key}',
    }


# ---------------------------------------------------------------------------
# VERI-01..06 core
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_only_uses_manifest():
    """VERI-01: batch_id path loads committed manifest expected; not len(live)."""
    assert GROUP == 'oracle-catalog-tool-test'
    root, chunks, body = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    # Live has only one of two expected entities + one extra.
    entity_rows = [
        _entity_row(ENTITY_A, content_sha='a' * 64),
        _entity_row(ENTITY_C, content_sha='c' * 64),  # extra
    ]
    edge_rows = [_edge_row(EDGE_A, content_sha='d' * 64)]
    evidence_rows = [
        {
            'uuid': EVID_UUID,
            'group_id': GROUP,
            'link_key': EVID_KEY,
            'content_sha256': '1' * 64,
        }
    ]
    calls = _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=entity_rows,
        edge_rows=edge_rows,
        evidence_rows=evidence_rows,
    )
    # No request keys — batch-only.
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code is None
    assert resp.found is True
    assert resp.manifest_sha256 == root['manifest_sha256']
    # Expected from manifest body counts (2 entities), not len(live)=2 coincidentally
    assert resp.entities.expected == body['counts']['entities']
    assert resp.entities.expected == 2
    assert resp.entities.found == 1
    assert ENTITY_B in resp.entities.missing
    assert ENTITY_C in resp.entities.extras
    assert any(c.startswith('read_root:') for c in calls)
    assert not any(c == 'BANNED_WRITE_OR_SCHEMA' for c in calls)
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_expected_not_live_count():
    """VERI-02 boundary+precision: expected ints from manifest counts; never len(rows)/float."""
    # Empty categories in manifest; live has rows → extras, expected stays 0.
    membership = _membership(entities=[], edges=[], evidence_links=[])
    root, chunks, body = _build_committed_fixture(membership)
    service = _service()
    client = _neo4j_client()
    live = [_entity_row(ENTITY_A), _entity_row(ENTITY_B)]
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=live,
        edge_rows=[],
        evidence_rows=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code is None
    assert resp.entities.expected == 0
    assert isinstance(resp.entities.expected, int)
    assert resp.entities.expected != len(live)
    assert set(resp.entities.extras) == {ENTITY_A, ENTITY_B}
    assert body['counts']['entities'] == 0


@pytest.mark.asyncio
async def test_missing_and_extra():
    """VERI-03: missing list and extras list both populated when both conditions true."""
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    # Missing ENTITY_B; extra ENTITY_C; found ENTITY_A.
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[
            _entity_row(ENTITY_A, content_sha='a' * 64),
            _entity_row(ENTITY_C, content_sha='c' * 64),
        ],
        edge_rows=[],  # EDGE_A missing
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert ENTITY_B in resp.entities.missing
    assert ENTITY_C in resp.entities.extras
    assert EDGE_A in resp.edges.missing
    assert resp.entities.missing and resp.entities.extras
    assert ENTITY_B in resp.missing
    assert ENTITY_C in resp.extras


@pytest.mark.asyncio
async def test_consistency_checks():
    """VERI-04: type/UUID/endpoint/embed/evidence/hash consistency."""
    root, chunks, body = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    bad_uuid = str(uuid.uuid4())
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[
            # wrong type + missing emb
            _entity_row(
                ENTITY_A,
                entity_type='View',
                has_emb=False,
                content_sha='a' * 64,
                labels=['Entity', 'View'],
                uuid_val=bad_uuid,
            ),
            # hash mismatch
            _entity_row(ENTITY_B, content_sha='z' * 64),
        ],
        edge_rows=[
            _edge_row(
                EDGE_A,
                has_emb=False,
                content_sha='x' * 64,
                source_uuid=None,  # endpoint null fails closed
                target_uuid='tgt',
                uuid_val=bad_uuid,
            )
        ],
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': 'WRONG_KEY',
                'content_sha256': '9' * 64,
            }
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code is None
    assert ENTITY_A in resp.entities.wrong_type
    assert ENTITY_A in resp.entities.missing_embedding
    assert ENTITY_B in resp.entities.content_hash_mismatch
    assert EDGE_A in resp.edges.missing_embedding
    assert EDGE_A in resp.edges.endpoint_mismatch
    assert EDGE_A in resp.edges.content_hash_mismatch
    assert EDGE_A in resp.edges.uuid_mismatch
    assert EVID_UUID in resp.evidence.link_key_mismatch
    assert EVID_UUID in resp.evidence.content_hash_mismatch
    # encoding: full system-scoped graph keys
    assert all(k.startswith('TABLE::FE::') for k in resp.entities.wrong_type)
    assert resp.entities.expected == body['counts']['entities']


@pytest.mark.asyncio
async def test_missing_manifest_code():
    """VERI-05: missing/incomplete/hash-mismatch → manifest_mismatch; missing status found=false."""
    service = _service()
    client = _neo4j_client()

    # 1) Missing status entirely → found=false, NOT manifest_mismatch.
    _wire_store(service, status=None, root=None, chunks=[])
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.found is False
    assert resp.error_code is None
    assert resp.error_message == 'batch status not found'

    # 2) Status present, missing root → manifest_mismatch.
    _wire_store(service, status=_status_row(), root=None, chunks=[])
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.manifest_mismatch

    # 3) Incomplete chunks → manifest_mismatch.
    root, chunks, _ = _build_committed_fixture(drop_chunks=True)
    _wire_store(service, root=root, chunks=chunks)
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.manifest_mismatch

    # 4) Digest mismatch → manifest_mismatch.
    root, chunks, _ = _build_committed_fixture(corrupt_digest=True)
    _wire_store(service, root=root, chunks=chunks)
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.manifest_mismatch


@pytest.mark.asyncio
async def test_explicit_keys_only():
    """VERI-06: keys-only path never uses manifest load as expected authority."""
    service = _service()
    client = _neo4j_client()
    calls = _wire_store(
        service,
        root=None,
        chunks=None,
        entity_rows=[_entity_row(ENTITY_A, content_sha='a' * 64)],
        edge_rows=[],
    )

    # Force get_status / read_root to raise if called.
    async def boom(*_a, **_k):
        calls.append('MANIFEST_OR_STATUS_CALLED')
        raise AssertionError('keys-only must not load status/manifest as authority')

    service._store.get_batch_status = boom  # type: ignore[method-assign]
    service._store.read_manifest_root_for_recovery = boom  # type: ignore[method-assign]

    req = _verify_request(
        batch_id=None,
        entities=[VerifyEntityRef(entity_type='Table', graph_key=ENTITY_A)],
        edges=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.error_code is None
    assert resp.entities.expected == 1
    assert resp.entities.found == 1
    assert resp.manifest_sha256 is None
    assert not any(c == 'MANIFEST_OR_STATUS_CALLED' for c in calls)
    assert not any(c.startswith('read_root:') for c in calls)


@pytest.mark.asyncio
async def test_batch_and_keys_both_apply():
    """VERI-06: batch_id + explicit keys both apply (keys still diagnosed)."""
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    extra_key = ENTITY_C
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[
            _entity_row(ENTITY_A, content_sha='a' * 64),
            _entity_row(ENTITY_B, content_sha='b' * 64),
            # request key present live
        ],
        edge_rows=[_edge_row(EDGE_A, content_sha='d' * 64)],
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ],
    )
    # Explicit request key not in manifest and not live → separate key diagnostic.
    # Membership missing remains manifest-only (CR-02).
    req = _verify_request(
        entities=[VerifyEntityRef(entity_type='Table', graph_key=extra_key)],
        edges=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.error_code is None
    # Batch expected still from manifest (2 entities)
    assert resp.entities.expected == 2
    assert extra_key not in resp.entities.missing
    assert any(
        a.get('kind') == 'explicit_key_missing' and a.get('graph_key') == extra_key
        for a in resp.anomalies
    )
    assert resp.manifest_sha256 is not None


@pytest.mark.asyncio
async def test_never_expected_equals_observed_len():
    """VERI-01/02: never section.expected = len(observed live rows) on batch path."""
    # Manifest expects 2; live has 5 — expected must stay 2.
    root, chunks, body = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    live = [
        _entity_row(ENTITY_A, content_sha='a' * 64),
        _entity_row(ENTITY_B, content_sha='b' * 64),
        _entity_row(ENTITY_C, content_sha='c' * 64),
        _entity_row('TABLE::FE::ORCL.HR.X1', content_sha='1' * 64),
        _entity_row('TABLE::FE::ORCL.HR.X2', content_sha='2' * 64),
    ]
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=live,
        edge_rows=[_edge_row(EDGE_A, content_sha='d' * 64)],
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.entities.expected == body['counts']['entities']
    assert resp.entities.expected != len(live)
    assert resp.entities.found == 2
    assert len(resp.entities.extras) == 3


@pytest.mark.asyncio
async def test_empty_expected_categories():
    """VERI-02 boundary: empty expected categories legal; live rows become extras."""
    membership = _membership(entities=[], edges=[], evidence_links=[])
    root, chunks, _ = _build_committed_fixture(membership)
    service = _service()
    client = _neo4j_client()
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[_entity_row(ENTITY_A)],
        edge_rows=[_edge_row(EDGE_A)],
        evidence_rows=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code is None
    assert resp.entities.expected == 0
    assert resp.edges.expected == 0
    assert resp.evidence.expected == 0
    assert ENTITY_A in resp.entities.extras
    assert EDGE_A in resp.edges.extras


@pytest.mark.asyncio
async def test_exact_evidence():
    """EVID-13: exact evidence MATCH by group_id + evidence-link uuid from durable manifest."""
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    evidence_calls: list[dict[str, Any]] = []

    async def match_evidence(executor, *, group_id, uuids, tx=None):
        evidence_calls.append({'group_id': group_id, 'uuids': list(uuids)})
        return [
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ]

    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[
            _entity_row(ENTITY_A, content_sha='a' * 64),
            _entity_row(ENTITY_B, content_sha='b' * 64),
        ],
        edge_rows=[_edge_row(EDGE_A, content_sha='d' * 64)],
        evidence_rows=[],
    )
    service._store.match_evidence_links_exact = match_evidence  # type: ignore[method-assign]

    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code is None
    assert resp.evidence.expected == 1
    assert resp.evidence.found == 1
    assert evidence_calls
    assert evidence_calls[0]['group_id'] == GROUP
    assert EVID_UUID in evidence_calls[0]['uuids']
    # Identity is uuid list — not link_key-only.
    assert all(isinstance(u, str) and u for u in evidence_calls[0]['uuids'])

    # Missing evidence uuid → missing diagnostic.
    async def match_empty(executor, *, group_id, uuids, tx=None):
        return []

    service._store.match_evidence_links_exact = match_empty  # type: ignore[method-assign]
    resp2 = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert EVID_UUID in resp2.evidence.missing
    assert resp2.evidence.found == 0


# ---------------------------------------------------------------------------
# TEST-08
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unchanged_member_missing_diagnostic():
    """TEST-08 boundary: shared unchanged member missing from live → missing diagnostic."""
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    # ENTITY_B is projected_status=unchanged in membership; omit from live.
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[_entity_row(ENTITY_A, content_sha='a' * 64)],
        edge_rows=[_edge_row(EDGE_A, content_sha='d' * 64)],
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert ENTITY_B in resp.entities.missing
    assert resp.entities.expected == 2  # unchanged still counted


@pytest.mark.asyncio
async def test_duplicate_key_anomaly_no_repair():
    """TEST-08 adjacency: duplicate_key anomaly without repair/write."""
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    calls = _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[
            _entity_row(ENTITY_A, content_sha='a' * 64),
            _entity_row(ENTITY_B, content_sha='b' * 64),
        ],
        edge_rows=[
            _edge_row(EDGE_A, content_sha='d' * 64, uuid_val='edge-1'),
            _edge_row(EDGE_A, content_sha='d' * 64, uuid_val='edge-2'),  # twin
        ],
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert EDGE_A in resp.edges.duplicate_edge_key
    assert not any(c == 'BANNED_WRITE_OR_SCHEMA' for c in calls)
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_batch_membership_clean():
    """TEST-08 empty: empty batch membership verifies clean when live empty."""
    membership = _membership(entities=[], edges=[], evidence_links=[])
    root, chunks, _ = _build_committed_fixture(membership)
    service = _service()
    client = _neo4j_client()
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[],
        edge_rows=[],
        evidence_rows=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code is None
    assert resp.entities.expected == 0
    assert resp.entities.found == 0
    assert resp.entities.missing == []
    assert resp.entities.extras == []
    assert resp.edges.expected == 0
    assert resp.evidence.expected == 0
    assert resp.missing == []
    assert resp.extras == []


@pytest.mark.asyncio
async def test_missing_extra_lists_deterministic():
    """TEST-08 ordering: missing/extra lists deterministic sorted by key."""
    membership = _membership(
        entities=[
            {
                'uuid': catalog_entity_uuid(FIXED_NS, GROUP, 'Table', ENTITY_C),
                'entity_type': 'Table',
                'graph_key': ENTITY_C,
                'content_sha256': 'c' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': catalog_entity_uuid(FIXED_NS, GROUP, 'Table', ENTITY_A),
                'entity_type': 'Table',
                'graph_key': ENTITY_A,
                'content_sha256': 'a' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': catalog_entity_uuid(FIXED_NS, GROUP, 'Table', ENTITY_B),
                'entity_type': 'Table',
                'graph_key': ENTITY_B,
                'content_sha256': 'b' * 64,
                'projected_status': 'created',
            },
        ],
        edges=[],
        evidence_links=[],
    )
    root, chunks, _ = _build_committed_fixture(membership)
    service = _service()
    client = _neo4j_client()
    # None of expected present; three extras with different keys.
    extras = [
        _entity_row('TABLE::FE::ORCL.HR.Z'),
        _entity_row('TABLE::FE::ORCL.HR.M'),
        _entity_row('TABLE::FE::ORCL.HR.A'),
    ]
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=extras,
        edge_rows=[],
        evidence_rows=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.entities.missing == sorted(resp.entities.missing)
    assert resp.entities.extras == sorted(resp.entities.extras)
    assert resp.entities.missing == sorted([ENTITY_A, ENTITY_B, ENTITY_C])


@pytest.mark.asyncio
async def test_count_drift_off_by_one():
    """TEST-08 precision: count drift off-by-one detected."""
    root, chunks, body = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    # One missing of two expected.
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[_entity_row(ENTITY_A, content_sha='a' * 64)],
        edge_rows=[_edge_row(EDGE_A, content_sha='d' * 64)],
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.entities.expected == body['counts']['entities']
    assert resp.entities.found == body['counts']['entities'] - 1
    assert len(resp.entities.missing) == 1


@pytest.mark.asyncio
async def test_concurrent_verify_stable():
    """TEST-08 concurrency: concurrent verifies same batch_id; no shared mutable expected."""
    root, chunks, body = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[
            _entity_row(ENTITY_A, content_sha='a' * 64),
            _entity_row(ENTITY_B, content_sha='b' * 64),
        ],
        edge_rows=[_edge_row(EDGE_A, content_sha='d' * 64)],
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ],
    )

    async def once():
        return await service.verify_catalog_batch(client=client, request=_verify_request())

    r1, r2 = await asyncio.gather(once(), once())
    assert r1.error_code is None and r2.error_code is None
    assert r1.entities.expected == r2.entities.expected == body['counts']['entities']
    assert r1.entities.found == r2.entities.found
    assert r1.entities.missing == r2.entities.missing
    assert r1.manifest_sha256 == r2.manifest_sha256
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_key_missing_not_in_membership():
    """CR-02: manifest {A,B} + requested C + live A,B => membership missing excludes C."""
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[
            _entity_row(ENTITY_A, content_sha='a' * 64),
            _entity_row(ENTITY_B, content_sha='b' * 64),
        ],
        edge_rows=[_edge_row(EDGE_A, content_sha='d' * 64)],
        evidence_rows=[
            {
                'uuid': EVID_UUID,
                'group_id': GROUP,
                'link_key': EVID_KEY,
                'content_sha256': '1' * 64,
            }
        ],
    )
    req = _verify_request(
        entities=[VerifyEntityRef(entity_type='Table', graph_key=ENTITY_C)],
        edges=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.error_code is None
    assert ENTITY_C not in resp.entities.missing
    assert ENTITY_C not in resp.missing
    assert any(
        a.get('kind') == 'explicit_key_missing' and a.get('graph_key') == ENTITY_C
        for a in resp.anomalies
    )


@pytest.mark.asyncio
async def test_evidence_extras_from_batch_observation():
    """WR-01: extras come from batch-scoped observation, not expected-only scan."""
    root, chunks, _ = _build_committed_fixture()
    service = _service()
    client = _neo4j_client()
    expected_rows = [
        {
            'uuid': EVID_UUID,
            'group_id': GROUP,
            'link_key': EVID_KEY,
            'content_sha256': '1' * 64,
        }
    ]
    extra_uuid = 'evidence-extra-uuid'
    batch_rows = expected_rows + [
        {
            'uuid': extra_uuid,
            'group_id': GROUP,
            'link_key': 'EXTRA::link',
            'content_sha256': '2' * 64,
            'batch_id': BATCH,
        }
    ]
    _wire_store(
        service,
        root=root,
        chunks=chunks,
        entity_rows=[
            _entity_row(ENTITY_A, content_sha='a' * 64),
            _entity_row(ENTITY_B, content_sha='b' * 64),
        ],
        edge_rows=[_edge_row(EDGE_A, content_sha='d' * 64)],
        evidence_rows=expected_rows,
    )

    async def match_batch(executor, *, group_id, batch_id, tx=None):
        assert group_id == GROUP
        assert batch_id == BATCH
        return list(batch_rows)

    service._store.match_evidence_links_for_batch = match_batch  # type: ignore[method-assign]
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code is None
    assert extra_uuid in resp.evidence.extras
    assert any(
        a.get('kind') == 'extra_evidence' and a.get('uuid') == extra_uuid for a in resp.anomalies
    )


@pytest.mark.asyncio
async def test_manifest_uuid_mismatch_fails_closed():
    """WR-03: manifest UUID disagreement fails closed; server UUIDv5 is authority."""
    membership = _membership(
        entities=[
            {
                'uuid': '00000000-0000-4000-8000-000000000099',
                'entity_type': 'Table',
                'graph_key': ENTITY_A,
                'content_sha256': 'a' * 64,
                'projected_status': 'created',
            }
        ],
        edges=[],
        evidence_links=[],
    )
    root, chunks, _ = _build_committed_fixture(membership)
    service = _service()
    client = _neo4j_client()
    _wire_store(service, root=root, chunks=chunks, entity_rows=[], edge_rows=[], evidence_rows=[])
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.manifest_mismatch
    assert 'manifest_uuid_mismatch' in (resp.error_message or '')

    membership_e = _membership(
        entities=[],
        edges=[
            {
                'uuid': '00000000-0000-4000-8000-000000000088',
                'edge_type': 'ForeignKeyTo',
                'edge_key': EDGE_A,
                'content_sha256': 'd' * 64,
                'projected_status': 'created',
            }
        ],
        evidence_links=[],
    )
    root, chunks, _ = _build_committed_fixture(membership_e)
    _wire_store(service, root=root, chunks=chunks, entity_rows=[], edge_rows=[], evidence_rows=[])
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.manifest_mismatch
    assert 'manifest_uuid_mismatch' in (resp.error_message or '')


@pytest.mark.asyncio
async def test_noncommitted_status_fails_closed():
    """WR-04: non-committed batch status fails closed without manifest/live reads."""
    service = _service()
    client = _neo4j_client()
    for status in ('failed', 'writing', 'planned', 'validating', 'embedding'):
        calls = _wire_store(
            service,
            status=_status_row(status=status),
            root={'should': 'not-load'},
            chunks=[{'should': 'not-load'}],
            entity_rows=[_entity_row(ENTITY_A)],
            edge_rows=[],
            evidence_rows=[],
        )
        resp = await service.verify_catalog_batch(client=client, request=_verify_request())
        assert resp.found is False
        assert resp.error_code == CatalogErrorCode.validation_error
        assert 'not committed' in (resp.error_message or '')
        assert not any(c.startswith('read_root:') for c in calls)
        assert not any(c.startswith('match_entities:') for c in calls)
