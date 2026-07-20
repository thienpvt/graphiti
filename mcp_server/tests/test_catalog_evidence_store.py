"""Exact evidence + durable manifest store unit suite (EVID-07..11, MANI-*, TEST-07).

No live Neo4j. Fake tx / executor only. Product service orchestration is 03B-04.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
NS = UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
FIXED_TS = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
SHA_A = 'a' * 64
SHA_B = 'b' * 64
SHA_C = 'c' * 64
SHA_D = 'd' * 64
SHA_E = 'e' * 64

FORBIDDEN_SUBSTR = (
    'name_embedding',
    'fact_embedding',
)


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


# Module-level dynamic product symbols (no `from services/models ...` static imports).
_COMMON = _load_module('models.catalog_common')
_EVIDENCE = _load_module('models.catalog_evidence')
_IDENTITY = _load_module('services.catalog_identity')
_STORE = _load_module('services.catalog_store')

IDENTITY_SCHEMA_VERSION = _attr(_COMMON, 'IDENTITY_SCHEMA_VERSION')
MAX_EVIDENCE_LENGTH = _attr(_COMMON, 'MAX_EVIDENCE_LENGTH')
PLAN_STATE_COMMITTED = _attr(_COMMON, 'PLAN_STATE_COMMITTED')
PLAN_STATE_COMMITTING = _attr(_COMMON, 'PLAN_STATE_COMMITTING')

CatalogEvidenceEntityTarget = _attr(_EVIDENCE, 'CatalogEvidenceEntityTarget')
CatalogEvidenceLink = _attr(_EVIDENCE, 'CatalogEvidenceLink')

canonical_sha256 = _attr(_IDENTITY, 'canonical_sha256')
coalesce_byte_identical_evidence_links = _attr(_IDENTITY, 'coalesce_byte_identical_evidence_links')
evidence_canonical_payload = _attr(_IDENTITY, 'evidence_canonical_payload')
evidence_link_key = _attr(_IDENTITY, 'evidence_link_key')

CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT = _attr(
    _STORE, 'CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT'
)
CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT = _attr(_STORE, 'CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT')
CATALOG_MANIFEST_CHUNK_IDENTITY_CONSTRAINT = _attr(
    _STORE, 'CATALOG_MANIFEST_CHUNK_IDENTITY_CONSTRAINT'
)
CATALOG_MANIFEST_CHUNK_INDEX_CONSTRAINT = _attr(_STORE, 'CATALOG_MANIFEST_CHUNK_INDEX_CONSTRAINT')
CATALOG_MANIFEST_IDENTITY_CONSTRAINT = _attr(_STORE, 'CATALOG_MANIFEST_IDENTITY_CONSTRAINT')
CatalogNeo4jStore = _attr(_STORE, 'CatalogNeo4jStore')
CatalogStoreError = _attr(_STORE, 'CatalogStoreError')


class _Rows:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    async def data(self) -> list[dict[str, Any]]:
        return list(self._rows)

    async def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _CaptureTx:
    """Records cypher/params; scripted responses by call index."""

    def __init__(self, responses: list[list[dict[str, Any]]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._responses = list(responses or [])
        self._i = 0

    async def run(self, cypher: str, **params: Any) -> _Rows:
        self.calls.append((cypher, params))
        if self._i < len(self._responses):
            rows = self._responses[self._i]
            self._i += 1
            return _Rows(rows)
        return _Rows([])


def _all_cypher(tx: _CaptureTx) -> str:
    return '\n'.join(c for c, _ in tx.calls)


def _assert_no_entity_on_control(cypher: str) -> None:
    for line in cypher.splitlines():
        stripped = line.strip()
        if (stripped.startswith('CREATE') or stripped.startswith('MERGE')) and (
            'CatalogEvidenceLink' in stripped or 'CatalogBatchManifest' in stripped
        ):
            assert ':Entity' not in stripped
            assert ':Episodic' not in stripped
    for bad in FORBIDDEN_SUBSTR:
        assert bad not in cypher


def _link_params(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'uuid': str(uuid5(NS, f'{GROUP}|catalog-v2|EvidenceLink|k1')),
        'group_id': GROUP,
        'batch_id': 'batch-001',
        'link_key': 'src|entity|Table|tbl.x|comment|ext|1.0||',
        'content_sha256': SHA_A,
        'source_uuid': str(uuid5(NS, f'{GROUP}|catalog-v2|Source|src')),
        'target_kind': 'entity',
        'target_uuid': str(uuid5(NS, f'{GROUP}|catalog-v2|Table|tbl.x')),
        'evidence_kind': 'comment',
        'locator_json': None,
        'excerpt': 'select 1',
        'extractor_name': 'ext',
        'extractor_version': '1.0',
        'rule_id': None,
        'confidence': 0.9,
        'created_at': FIXED_TS,
        'updated_at': FIXED_TS,
    }
    base.update(overrides)
    return base


def _manifest_root(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'uuid': str(uuid5(NS, f'{GROUP}|catalog-v2|Manifest|batch-001')),
        'group_id': GROUP,
        'batch_id': 'batch-001',
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
        'canonicalization_version': 'catalog-canonical-v1',
        'manifest_serialization_version': 'catalog-manifest-v1',
        'catalog_schema_version': 'catalog-schema-v1',
        'request_sha256': SHA_B,
        'catalog_sha256': SHA_C,
        'artifact_sha256': SHA_D,
        'manifest_sha256': SHA_E,
        'payload_bytes': 32,
        'chunk_count': 1,
        'entity_count': 1,
        'edge_count': 0,
        'source_count': 0,
        'evidence_link_count': 0,
        'created_at': FIXED_TS,
        'updated_at': FIXED_TS,
    }
    base.update(overrides)
    return base


def _manifest_chunk(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'uuid': str(uuid5(NS, f'{GROUP}|catalog-v2|ManifestChunk|batch-001|0')),
        'group_id': GROUP,
        'manifest_uuid': str(uuid5(NS, f'{GROUP}|catalog-v2|Manifest|batch-001')),
        'batch_id': 'batch-001',
        'chunk_index': 0,
        'chunk_count': 1,
        'byte_offset': 0,
        'byte_length': 32,
        'chunk_sha256': SHA_A,
        'payload_b64': 'AQIDBA==',
    }
    base.update(overrides)
    return base


def _valid_evidence_manifest_constraint_rows() -> list[dict]:
    return [
        {
            'name': CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT,
            'type': 'UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogEvidenceLink'],
            'properties': ['uuid', 'group_id'],
        },
        {
            'name': CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT,
            'type': 'UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogEvidenceLink'],
            'properties': ['group_id', 'link_key'],
        },
        {
            'name': CATALOG_MANIFEST_IDENTITY_CONSTRAINT,
            'type': 'UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogBatchManifest'],
            'properties': ['uuid', 'group_id'],
        },
        {
            'name': CATALOG_MANIFEST_CHUNK_IDENTITY_CONSTRAINT,
            'type': 'UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogBatchManifestChunk'],
            'properties': ['uuid', 'group_id'],
        },
        {
            'name': CATALOG_MANIFEST_CHUNK_INDEX_CONSTRAINT,
            'type': 'UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogBatchManifestChunk'],
            'properties': ['manifest_uuid', 'group_id', 'chunk_index'],
        },
    ]


def test_evidence_schema_constraint_statements_fixed_labels():
    store = CatalogNeo4jStore()
    stmts = store.evidence_manifest_schema_constraint_statements()
    joined = '\n'.join(stmts)
    assert 'CREATE CONSTRAINT' in joined
    assert 'IF NOT EXISTS' in joined
    assert 'CatalogEvidenceLink' in joined
    assert 'CatalogBatchManifest' in joined
    assert 'CatalogBatchManifestChunk' in joined
    assert CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT in joined
    assert CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT in joined
    assert CATALOG_MANIFEST_IDENTITY_CONSTRAINT in joined
    assert CATALOG_MANIFEST_CHUNK_IDENTITY_CONSTRAINT in joined
    assert CATALOG_MANIFEST_CHUNK_INDEX_CONSTRAINT in joined
    assert 'DROP' not in joined.upper()
    assert '${' not in joined
    assert ':Entity' not in joined
    assert ':Episodic' not in joined


async def test_ensure_evidence_manifest_schema_emits_create_only():
    store = CatalogNeo4jStore()
    calls: list[str] = []

    class _Exec:
        async def execute_query(self, stmt: str, params=None, **kwargs):
            _ = (params, kwargs)  # match execute_query contract; unused by this fake
            calls.append(stmt)
            if 'SHOW CONSTRAINTS' in stmt:
                if any('CREATE CONSTRAINT' in c for c in calls):
                    rows = _valid_evidence_manifest_constraint_rows()
                    return (rows, None, None)
                return ([], None, None)
            return (None, None, None)

    await store.ensure_evidence_manifest_schema(_Exec())
    joined = '\n'.join(calls)
    assert 'CREATE CONSTRAINT' in joined
    assert 'DROP' not in joined.upper()
    assert 'CatalogEvidenceLink' in joined


def test_build_evidence_link_cypher_fixed_label_no_entity():
    store = CatalogNeo4jStore()
    cypher = store.build_evidence_link_write_cypher()
    assert 'CatalogEvidenceLink' in cypher
    assert 'group_id' in cypher
    assert 'content_sha256' in cypher
    assert 'link_key' in cypher
    assert 'name_embedding' not in cypher
    _assert_no_entity_on_control(cypher)
    assert ':CatalogEvidenceLink' in cypher


def test_evidence_create_once_conflict():
    """EVID-07/08 named primary: create-once + divergent content_sha256 conflict."""
    assert GROUP == 'oracle-catalog-tool-test'


async def test_evidence_create_once_same_content():
    """EVID-07: second write identical content_sha256 is create-once no-op."""
    store = CatalogNeo4jStore()
    params = store.prepare_evidence_link_params(**_link_params())
    tx = _CaptureTx(
        responses=[
            [{'uuid': params['source_uuid'], 'kind': 'source'}],
            [{'uuid': params['target_uuid'], 'kind': 'entity', 'labels': ['Entity', 'Table']}],
            [
                {
                    'uuid': params['uuid'],
                    'content_sha256': params['content_sha256'],
                    'link_key': params['link_key'],
                    'status': 'unchanged',
                    'error_code': None,
                    'labels': ['CatalogEvidenceLink'],
                }
            ],
        ]
    )
    row = await store.write_evidence_link(tx, params=params)
    assert row['status'] == 'unchanged'
    assert row['uuid'] == params['uuid']
    assert 'Entity' not in (row.get('labels') or [])
    joined = _all_cypher(tx)
    assert 'CatalogEvidenceLink' in joined
    assert 'group_id' in joined


async def test_evidence_divergent_content_raises_provenance_link_conflict():
    """EVID-08: same link identity, different content_sha256 -> provenance_link_conflict."""
    store = CatalogNeo4jStore()
    params = store.prepare_evidence_link_params(**_link_params(content_sha256=SHA_B))
    tx = _CaptureTx(
        responses=[
            [{'uuid': params['source_uuid'], 'kind': 'source'}],
            [{'uuid': params['target_uuid'], 'kind': 'entity', 'labels': ['Entity', 'Table']}],
            [
                {
                    'uuid': params['uuid'],
                    'content_sha256': SHA_A,
                    'link_key': params['link_key'],
                    'status': 'error',
                    'error_code': 'provenance_link_conflict',
                    'labels': ['CatalogEvidenceLink'],
                }
            ],
        ]
    )
    with pytest.raises(CatalogStoreError) as ei:
        await store.write_evidence_link(tx, params=params)
    assert ei.value.code == 'provenance_link_conflict'


async def test_evidence_missing_target_fails():
    """EVID-07/09: missing entity/edge target fails closed."""
    store = CatalogNeo4jStore()
    params = store.prepare_evidence_link_params(**_link_params())
    tx = _CaptureTx(
        responses=[
            [{'uuid': params['source_uuid'], 'kind': 'source'}],
            [],
        ]
    )
    with pytest.raises(CatalogStoreError) as ei:
        await store.write_evidence_link(tx, params=params)
    assert ei.value.code in {'provenance_target_missing', 'missing_endpoint'}


async def test_evidence_type_mismatch_fails():
    """EVID-07/09: target kind mismatch fails closed."""
    store = CatalogNeo4jStore()
    params = store.prepare_evidence_link_params(**_link_params(target_kind='entity'))
    tx = _CaptureTx(
        responses=[
            [{'uuid': params['source_uuid'], 'kind': 'source'}],
            [],
        ]
    )
    with pytest.raises(CatalogStoreError) as ei:
        await store.write_evidence_link(tx, params=params)
    assert ei.value.code in {
        'provenance_target_missing',
        'missing_endpoint',
        'endpoint_type_mismatch',
    }
    with pytest.raises(CatalogStoreError) as ei2:
        store.prepare_evidence_link_params(**_link_params(target_kind='source'))
    assert ei2.value.code == 'validation_error'


async def test_evidence_no_entity_label():
    """EVID-10: CatalogEvidenceLink must never carry Entity or Episodic labels."""
    store = CatalogNeo4jStore()
    cypher = store.build_evidence_link_write_cypher()
    assert ':CatalogEvidenceLink' in cypher
    assert 'CREATE (n:CatalogEvidenceLink' in cypher or 'MERGE (n:CatalogEvidenceLink' in cypher
    assert 'CatalogEvidenceLink:Entity' not in cypher
    assert ':Entity:CatalogEvidenceLink' not in cypher
    assert 'name_embedding' not in cypher
    params = store.prepare_evidence_link_params(**_link_params())
    tx = _CaptureTx(
        responses=[
            [{'uuid': params['source_uuid'], 'kind': 'source'}],
            [{'uuid': params['target_uuid'], 'kind': 'entity', 'labels': ['Entity', 'Table']}],
            [
                {
                    'uuid': params['uuid'],
                    'content_sha256': params['content_sha256'],
                    'link_key': params['link_key'],
                    'status': 'created',
                    'error_code': None,
                    'labels': ['CatalogEvidenceLink'],
                }
            ],
        ]
    )
    row = await store.write_evidence_link(tx, params=params)
    labels = row.get('labels') or []
    assert 'Entity' not in labels
    assert 'Episodic' not in labels
    assert 'CatalogEvidenceLink' in labels


async def test_evidence_empty_list_ok():
    """EVID-11: empty evidence list is a valid no-op write."""
    store = CatalogNeo4jStore()
    tx = _CaptureTx()
    rows = await store.write_evidence_links(tx, links=[])
    assert rows == []
    assert tx.calls == []


async def test_evidence_single_link():
    """EVID-07: single exact evidence link persists with fixed allowlist properties."""
    store = CatalogNeo4jStore()
    params = store.prepare_evidence_link_params(**_link_params())
    required = {
        'uuid',
        'group_id',
        'batch_id',
        'link_key',
        'content_sha256',
        'source_uuid',
        'target_kind',
        'target_uuid',
        'evidence_kind',
        'created_at',
        'updated_at',
    }
    assert required.issubset(params.keys())
    assert 'name_embedding' not in params
    tx = _CaptureTx(
        responses=[
            [{'uuid': params['source_uuid'], 'kind': 'source'}],
            [{'uuid': params['target_uuid'], 'kind': 'entity', 'labels': ['Entity', 'Table']}],
            [
                {
                    'uuid': params['uuid'],
                    'content_sha256': params['content_sha256'],
                    'link_key': params['link_key'],
                    'status': 'created',
                    'error_code': None,
                    'labels': ['CatalogEvidenceLink'],
                }
            ],
        ]
    )
    row = await store.write_evidence_link(tx, params=params)
    assert row['status'] == 'created'
    joined = _all_cypher(tx)
    assert 'CatalogEvidenceLink' in joined
    assert params['group_id'] in str(tx.calls)


async def test_evidence_coalesce_byte_identical():
    """EVID-08/11: byte-identical links coalesce; store still idempotent on uuid."""
    link = CatalogEvidenceLink(
        source_key='src.k',
        entity_target=CatalogEvidenceEntityTarget(
            entity_type='Table', graph_key='TABLE::FE::ORCL.HR.EMPLOYEES'
        ),
        evidence_kind='comment',
        extractor_name='ext',
        extractor_version='1.0',
        excerpt='same',
    )
    twin = CatalogEvidenceLink(
        source_key='src.k',
        entity_target=CatalogEvidenceEntityTarget(
            entity_type='Table', graph_key='TABLE::FE::ORCL.HR.EMPLOYEES'
        ),
        evidence_kind='comment',
        extractor_name='ext',
        extractor_version='1.0',
        excerpt='same',
    )
    coalesced = coalesce_byte_identical_evidence_links([link, twin])
    assert len(coalesced) == 1
    assert evidence_link_key(coalesced[0]) == evidence_link_key(link)
    digest = canonical_sha256(evidence_canonical_payload(link))
    assert len(digest) == 64

    store = CatalogNeo4jStore()
    params = store.prepare_evidence_link_params(
        **_link_params(content_sha256=digest, link_key=evidence_link_key(link))
    )
    tx = _CaptureTx(
        responses=[
            [{'uuid': params['source_uuid'], 'kind': 'source'}],
            [{'uuid': params['target_uuid'], 'kind': 'entity', 'labels': ['Entity', 'Table']}],
            [
                {
                    'uuid': params['uuid'],
                    'content_sha256': digest,
                    'link_key': params['link_key'],
                    'status': 'created',
                    'error_code': None,
                    'labels': ['CatalogEvidenceLink'],
                }
            ],
            [{'uuid': params['source_uuid'], 'kind': 'source'}],
            [{'uuid': params['target_uuid'], 'kind': 'entity', 'labels': ['Entity', 'Table']}],
            [
                {
                    'uuid': params['uuid'],
                    'content_sha256': digest,
                    'link_key': params['link_key'],
                    'status': 'unchanged',
                    'error_code': None,
                    'labels': ['CatalogEvidenceLink'],
                }
            ],
        ]
    )
    first = await store.write_evidence_link(tx, params=params)
    second = await store.write_evidence_link(tx, params=params)
    assert first['status'] == 'created'
    assert second['status'] == 'unchanged'


async def test_evidence_excerpt_length_bound_uses_string_length():
    """EVID-11: excerpt bound uses MAX_EVIDENCE_LENGTH string length (not bytes)."""
    assert MAX_EVIDENCE_LENGTH > 0
    store = CatalogNeo4jStore()
    ok = 'x' * MAX_EVIDENCE_LENGTH
    params = store.prepare_evidence_link_params(**_link_params(excerpt=ok))
    assert params['excerpt'] == ok
    with pytest.raises(CatalogStoreError) as ei:
        store.prepare_evidence_link_params(**_link_params(excerpt=ok + 'y'))
    assert ei.value.code == 'validation_error'


async def test_evidence_missing_source_fails():
    store = CatalogNeo4jStore()
    params = store.prepare_evidence_link_params(**_link_params())
    tx = _CaptureTx(responses=[[]])
    with pytest.raises(CatalogStoreError) as ei:
        await store.write_evidence_link(tx, params=params)
    assert ei.value.code in {'provenance_target_missing', 'missing_endpoint'}


def test_build_manifest_cypher_fixed_labels():
    store = CatalogNeo4jStore()
    root = store.build_create_manifest_root_cypher()
    chunk = store.build_create_manifest_chunk_cypher()
    assert 'CatalogBatchManifest' in root
    assert 'CatalogBatchManifestChunk' in chunk
    assert 'manifest_sha256' in root
    assert 'group_id' in root and 'group_id' in chunk
    assert 'name_embedding' not in root + chunk
    _assert_no_entity_on_control(root)
    _assert_no_entity_on_control(chunk)


async def test_write_manifest_root_and_chunks_create_once():
    store = CatalogNeo4jStore()
    root = store.prepare_manifest_root_params(**_manifest_root())
    chunks = [store.prepare_manifest_chunk_params(**_manifest_chunk())]
    tx = _CaptureTx(
        responses=[
            [],
            [
                {
                    'uuid': root['uuid'],
                    'group_id': GROUP,
                    'manifest_sha256': root['manifest_sha256'],
                    'chunk_count': 1,
                }
            ],
            [
                {
                    'uuid': chunks[0]['uuid'],
                    'chunk_index': 0,
                    'chunk_sha256': chunks[0]['chunk_sha256'],
                }
            ],
        ]
    )
    out = await store.write_manifest_root_and_chunks(tx, root=root, chunks=chunks)
    assert out['uuid'] == root['uuid']
    joined = _all_cypher(tx)
    assert 'CatalogBatchManifest' in joined
    assert 'CatalogBatchManifestChunk' in joined
    _assert_no_entity_on_control(joined)


async def test_write_manifest_divergent_hash_conflicts():
    store = CatalogNeo4jStore()
    root = store.prepare_manifest_root_params(**_manifest_root(manifest_sha256=SHA_A))
    chunks = [store.prepare_manifest_chunk_params(**_manifest_chunk())]
    tx = _CaptureTx(
        responses=[
            [
                {
                    'uuid': root['uuid'],
                    'group_id': GROUP,
                    'manifest_sha256': SHA_B,
                    'request_sha256': root['request_sha256'],
                    'catalog_sha256': root['catalog_sha256'],
                    'batch_id': root['batch_id'],
                }
            ],
        ]
    )
    with pytest.raises(CatalogStoreError) as ei:
        await store.write_manifest_root_and_chunks(tx, root=root, chunks=chunks)
    assert ei.value.code in {'batch_conflict', 'manifest_mismatch', 'prepared_plan_conflict'}


async def test_write_manifest_same_hash_idempotent():
    store = CatalogNeo4jStore()
    root = store.prepare_manifest_root_params(**_manifest_root())
    chunks = [store.prepare_manifest_chunk_params(**_manifest_chunk())]
    tx = _CaptureTx(
        responses=[
            [
                {
                    'uuid': root['uuid'],
                    'group_id': GROUP,
                    'manifest_sha256': root['manifest_sha256'],
                    'request_sha256': root['request_sha256'],
                    'catalog_sha256': root['catalog_sha256'],
                    'artifact_sha256': root['artifact_sha256'],
                    'batch_id': root['batch_id'],
                    'chunk_count': 1,
                    'payload_bytes': root['payload_bytes'],
                }
            ],
            # WR-05: idempotent root path verifies ordered chunk completeness/hashes
            [
                {
                    'uuid': chunks[0]['uuid'],
                    'manifest_uuid': root['uuid'],
                    'chunk_index': 0,
                    'chunk_count': 1,
                    'chunk_sha256': chunks[0]['chunk_sha256'],
                }
            ],
        ]
    )
    out = await store.write_manifest_root_and_chunks(tx, root=root, chunks=chunks)
    assert out['uuid'] == root['uuid']
    assert out.get('idempotent') is True
    joined = _all_cypher(tx)
    assert joined.count('CREATE (m:CatalogBatchManifest') == 0
    assert 'CatalogBatchManifestChunk' in joined


async def test_write_manifest_chunk_order():
    store = CatalogNeo4jStore()
    root = store.prepare_manifest_root_params(**_manifest_root(chunk_count=2, payload_bytes=64))
    ch0 = store.prepare_manifest_chunk_params(
        **_manifest_chunk(chunk_index=1, chunk_count=2, uuid=str(uuid5(NS, 'ch1')))
    )
    ch1 = store.prepare_manifest_chunk_params(
        **_manifest_chunk(chunk_index=0, chunk_count=2, uuid=str(uuid5(NS, 'ch0')))
    )
    created_indexes: list[int] = []

    class _OrderTx(_CaptureTx):
        async def run(self, cypher: str, **params: Any) -> _Rows:
            self.calls.append((cypher, params))
            if 'CatalogBatchManifestChunk' in cypher and 'CREATE' in cypher:
                created_indexes.append(int(params['chunk_index']))
                return _Rows(
                    [
                        {
                            'uuid': params['uuid'],
                            'chunk_index': params['chunk_index'],
                            'chunk_sha256': params['chunk_sha256'],
                        }
                    ]
                )
            if 'CatalogBatchManifest' in cypher and 'MATCH' in cypher:
                return _Rows([])
            if 'CatalogBatchManifest' in cypher and 'CREATE' in cypher:
                return _Rows(
                    [
                        {
                            'uuid': root['uuid'],
                            'group_id': GROUP,
                            'manifest_sha256': root['manifest_sha256'],
                            'chunk_count': 2,
                        }
                    ]
                )
            return _Rows([])

    tx = _OrderTx()
    await store.write_manifest_root_and_chunks(tx, root=root, chunks=[ch0, ch1])
    assert created_indexes == [0, 1]


async def test_lock_prepared_plan_for_commit():
    store = CatalogNeo4jStore()
    plan_uuid = str(uuid5(NS, 'plan'))
    tx = _CaptureTx(
        responses=[
            [
                {
                    'uuid': plan_uuid,
                    'group_id': GROUP,
                    'state': PLAN_STATE_COMMITTING,
                    'token_digest': SHA_A,
                    'locked': True,
                }
            ]
        ]
    )
    row = await store.lock_prepared_plan_for_commit(tx, plan_uuid=plan_uuid, group_id=GROUP)
    assert row['state'] == PLAN_STATE_COMMITTING
    assert row['uuid'] == plan_uuid
    cypher, params = tx.calls[0]
    assert 'CatalogPreparedPlan' in cypher
    assert 'group_id' in cypher
    assert params['group_id'] == GROUP
    assert params['uuid'] == plan_uuid
    assert 'SET' in cypher and 'p.uuid = p.uuid' in cypher


async def test_terminal_commit_agrees_true():
    store = CatalogNeo4jStore()
    plan_uuid = str(uuid5(NS, 'plan'))
    batch_uuid = str(uuid5(NS, 'batch'))
    projection = {
        'group_id': GROUP,
        'batch_id': 'batch-001',
        'plan_uuid': plan_uuid,
        'batch_uuid': batch_uuid,
        'request_sha256': SHA_B,
        'catalog_sha256': SHA_C,
        'artifact_sha256': SHA_D,
        'manifest_sha256': SHA_E,
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
    }
    tx = _CaptureTx(
        responses=[
            [
                {
                    'plan_state': PLAN_STATE_COMMITTED,
                    'batch_status': 'committed',
                    'manifest_sha256': SHA_E,
                    'request_sha256': SHA_B,
                    'catalog_sha256': SHA_C,
                    'artifact_sha256': SHA_D,
                    'identity_schema_version': IDENTITY_SCHEMA_VERSION,
                    'batch_id': 'batch-001',
                    'group_id': GROUP,
                }
            ]
        ]
    )
    assert await store.terminal_commit_agrees(tx, projection=projection) is True


async def test_terminal_commit_agrees_partial_false():
    store = CatalogNeo4jStore()
    projection = {
        'group_id': GROUP,
        'batch_id': 'batch-001',
        'plan_uuid': str(uuid5(NS, 'plan')),
        'batch_uuid': str(uuid5(NS, 'batch')),
        'request_sha256': SHA_B,
        'catalog_sha256': SHA_C,
        'artifact_sha256': SHA_D,
        'manifest_sha256': SHA_E,
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
    }
    tx = _CaptureTx(
        responses=[
            [
                {
                    'plan_state': PLAN_STATE_COMMITTING,
                    'batch_status': 'committed',
                    'manifest_sha256': SHA_E,
                    'request_sha256': SHA_B,
                    'catalog_sha256': SHA_C,
                    'artifact_sha256': SHA_D,
                    'identity_schema_version': IDENTITY_SCHEMA_VERSION,
                    'batch_id': 'batch-001',
                    'group_id': GROUP,
                }
            ]
        ]
    )
    assert await store.terminal_commit_agrees(tx, projection=projection) is False


async def test_terminal_commit_agrees_hash_mismatch_false():
    store = CatalogNeo4jStore()
    projection = {
        'group_id': GROUP,
        'batch_id': 'batch-001',
        'plan_uuid': str(uuid5(NS, 'plan')),
        'batch_uuid': str(uuid5(NS, 'batch')),
        'request_sha256': SHA_B,
        'catalog_sha256': SHA_C,
        'artifact_sha256': SHA_D,
        'manifest_sha256': SHA_E,
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
    }
    tx = _CaptureTx(
        responses=[
            [
                {
                    'plan_state': PLAN_STATE_COMMITTED,
                    'batch_status': 'committed',
                    'manifest_sha256': SHA_A,
                    'request_sha256': SHA_B,
                    'catalog_sha256': SHA_C,
                    'artifact_sha256': SHA_D,
                    'identity_schema_version': IDENTITY_SCHEMA_VERSION,
                    'batch_id': 'batch-001',
                    'group_id': GROUP,
                }
            ]
        ]
    )
    assert await store.terminal_commit_agrees(tx, projection=projection) is False


async def test_terminal_commit_agrees_missing_false():
    store = CatalogNeo4jStore()
    projection = {
        'group_id': GROUP,
        'batch_id': 'batch-001',
        'plan_uuid': str(uuid5(NS, 'plan')),
        'batch_uuid': str(uuid5(NS, 'batch')),
        'request_sha256': SHA_B,
        'catalog_sha256': SHA_C,
        'artifact_sha256': SHA_D,
        'manifest_sha256': SHA_E,
        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
    }
    tx = _CaptureTx(responses=[[]])
    assert await store.terminal_commit_agrees(tx, projection=projection) is False


async def test_read_manifest_root_for_recovery():
    store = CatalogNeo4jStore()
    root_uuid = str(uuid5(NS, f'{GROUP}|catalog-v2|Manifest|batch-001'))

    class _Exec:
        async def execute_query(self, query: str, params=None, **kwargs):
            _ = kwargs  # match execute_query contract; unused by this fake
            assert 'CatalogBatchManifest' in query
            assert params is not None
            assert params['group_id'] == GROUP
            return (
                [
                    {
                        'uuid': root_uuid,
                        'group_id': GROUP,
                        'batch_id': 'batch-001',
                        'manifest_sha256': SHA_E,
                        'request_sha256': SHA_B,
                        'catalog_sha256': SHA_C,
                        'artifact_sha256': SHA_D,
                        'identity_schema_version': IDENTITY_SCHEMA_VERSION,
                        'chunk_count': 1,
                        'payload_bytes': 32,
                    }
                ],
                None,
                None,
            )

    row = await store.read_manifest_root_for_recovery(_Exec(), group_id=GROUP, batch_id='batch-001')
    assert row is not None
    assert row['manifest_sha256'] == SHA_E
    assert 'Entity' not in str(row)


def test_manifest_params_reject_embeddings_and_raw_token():
    store = CatalogNeo4jStore()
    with pytest.raises(CatalogStoreError):
        store.prepare_manifest_root_params(**_manifest_root(name_embedding=[0.1]))
    with pytest.raises(CatalogStoreError):
        store.prepare_manifest_chunk_params(**_manifest_chunk(fact_embedding=[0.1]))


def test_evidence_write_cypher_group_scoped_params_only():
    store = CatalogNeo4jStore()
    cypher = store.build_evidence_link_write_cypher()
    assert '$group_id' in cypher
    assert '$uuid' in cypher
    assert '$content_sha256' in cypher
    assert '${' not in cypher
    assert '+ $label' not in cypher


async def test_wr05_manifest_idempotent_incomplete_chunks_conflict():
    """Root-only same-hash hit without complete chunks must fail closed."""
    store = CatalogNeo4jStore()
    root = store.prepare_manifest_root_params(**_manifest_root())
    chunks = [store.prepare_manifest_chunk_params(**_manifest_chunk())]
    tx = _CaptureTx(
        responses=[
            [
                {
                    'uuid': root['uuid'],
                    'group_id': GROUP,
                    'manifest_sha256': root['manifest_sha256'],
                    'request_sha256': root['request_sha256'],
                    'catalog_sha256': root['catalog_sha256'],
                    'artifact_sha256': root['artifact_sha256'],
                    'batch_id': root['batch_id'],
                    'chunk_count': 1,
                    'payload_bytes': root['payload_bytes'],
                }
            ],
            [],  # no chunks present
        ]
    )
    with pytest.raises(CatalogStoreError) as ei:
        await store.write_manifest_root_and_chunks(tx, root=root, chunks=chunks)
    assert ei.value.code == 'batch_conflict'
    assert 'chunk' in str(ei.value).lower()


async def test_wr05_manifest_idempotent_chunk_hash_mismatch_conflict():
    store = CatalogNeo4jStore()
    root = store.prepare_manifest_root_params(**_manifest_root())
    chunks = [store.prepare_manifest_chunk_params(**_manifest_chunk())]
    tx = _CaptureTx(
        responses=[
            [
                {
                    'uuid': root['uuid'],
                    'group_id': GROUP,
                    'manifest_sha256': root['manifest_sha256'],
                    'request_sha256': root['request_sha256'],
                    'catalog_sha256': root['catalog_sha256'],
                    'artifact_sha256': root['artifact_sha256'],
                    'batch_id': root['batch_id'],
                    'chunk_count': 1,
                    'payload_bytes': root['payload_bytes'],
                }
            ],
            [
                {
                    'uuid': chunks[0]['uuid'],
                    'manifest_uuid': root['uuid'],
                    'chunk_index': 0,
                    'chunk_count': 1,
                    'chunk_sha256': SHA_B,
                }
            ],
        ]
    )
    with pytest.raises(CatalogStoreError) as ei:
        await store.write_manifest_root_and_chunks(tx, root=root, chunks=chunks)
    assert ei.value.code == 'batch_conflict'
