"""Pure catalog manifest serialize/hash/chunk contract (MANI-01..07, D-17..D-21, D-29).

Product module `services.catalog_manifest` is the pure authority layer for
catalog-manifest-v1 body bytes. No Neo4j, no store I/O.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import inspect
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
BATCH_ID = 'batch-manifest-001'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
REQUEST_SHA = '1' * 64
CATALOG_SHA = '2' * 64

# Scaffold defaults mirror Phase 3A prepared-artifact ceilings (PATTERNS.md).
DEFAULT_CHUNK_BYTES = 131_072
HARD_CHUNK_BYTES = 262_144
MANIFEST_SERIALIZATION_VERSION = 'catalog-manifest-v1'

_PRODUCT_SYMBOLS = (
    'DEFAULT_CHUNK_BYTES',
    'HARD_CHUNK_BYTES',
    'MANIFEST_SERIALIZATION_VERSION',
    'build_manifest_body_from_membership',
    'chunk_manifest_body',
    'chunk_manifest_bytes',
    'manifest_sha256',
    'serialize_manifest_body',
)


def _product() -> Any:
    """Load services.catalog_manifest; fail closed if missing."""
    try:
        return importlib.import_module('services.catalog_manifest')
    except ImportError as exc:
        pytest.fail(f'03B not implemented: services.catalog_manifest missing ({exc})')


def _require(*names: str) -> Any:
    mod = _product()
    missing = [n for n in names if not hasattr(mod, n)]
    if missing:
        pytest.fail(f'03B not implemented: missing symbols {missing}')
    return mod


def _empty_membership() -> dict[str, Any]:
    return {'entities': [], 'edges': [], 'sources': [], 'evidence_links': []}


def _single_member_membership() -> dict[str, Any]:
    return {
        'entities': [
            {
                'uuid': 'e1',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': 'a' * 64,
                'projected_status': 'created',
                'name_embedding': [0.1, 0.2],  # must be stripped from body
                'batch_id': 'must-not-drive-membership',
            }
        ],
        'edges': [],
        'sources': [],
        'evidence_links': [],
    }


def _four_category_membership() -> dict[str, Any]:
    return {
        'entities': [
            {
                'uuid': 'e1',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': 'a' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 'e2',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.DEPARTMENTS',
                'content_sha256': 'b' * 64,
                'projected_status': 'unchanged',
            },
        ],
        'edges': [
            {
                'uuid': 'r1',
                'edge_type': 'ForeignKeyTo',
                'edge_key': 'FK::EMP->DEPT',
                'source_uuid': 'e1',
                'target_uuid': 'e2',
                'content_sha256': 'c' * 64,
                'projected_status': 'updated',
                'fact_embedding': [9.9],
            }
        ],
        'sources': [
            {
                'uuid': 's1',
                'source_key': 'SRC::ddl.sql#employees',
                'content_sha256': 'd' * 64,
                'projected_status': 'created',
            }
        ],
        'evidence_links': [
            {
                'uuid': 'l1',
                'link_key': 'SRC::ddl.sql#employees|entity|Table|TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': 'e' * 64,
            }
        ],
    }


def _build_kwargs(membership: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body = {
        'group_id': GROUP,
        'batch_id': BATCH_ID,
        'request_sha256': REQUEST_SHA,
        'catalog_sha256': CATALOG_SHA,
        'membership': membership,
        'artifact_sha256': None,
    }
    body.update(overrides)
    return body


def test_manifest_serialization_version_constant():
    """MANI-01: version pin catalog-manifest-v1."""
    assert MANIFEST_SERIALIZATION_VERSION == 'catalog-manifest-v1'
    mod = _require('MANIFEST_SERIALIZATION_VERSION', 'DEFAULT_CHUNK_BYTES', 'HARD_CHUNK_BYTES')
    assert mod.MANIFEST_SERIALIZATION_VERSION == 'catalog-manifest-v1'
    assert mod.DEFAULT_CHUNK_BYTES == 131_072
    assert mod.HARD_CHUNK_BYTES == 262_144
    for name in _PRODUCT_SYMBOLS:
        assert hasattr(mod, name), name


def test_manifest_empty_membership():
    """MANI-01: empty four-category membership is valid and stable."""
    mod = _require('build_manifest_body_from_membership', 'serialize_manifest_body', 'manifest_sha256')
    body = mod.build_manifest_body_from_membership(**_build_kwargs(_empty_membership()))
    assert body['manifest_serialization_version'] == 'catalog-manifest-v1'
    assert body['counts'] == {
        'entities': 0,
        'edges': 0,
        'sources': 0,
        'evidence_links': 0,
    }
    assert body['entities'] == []
    assert body['edges'] == []
    assert body['sources'] == []
    assert body['evidence_links'] == []
    assert body['artifact_sha256'] is None
    raw = mod.serialize_manifest_body(body)
    assert isinstance(raw, bytes)
    digest = mod.manifest_sha256(raw)
    assert len(digest) == 64
    assert digest == hashlib.sha256(raw).hexdigest()
    # null membership rejected
    with pytest.raises((TypeError, ValueError)):
        mod.build_manifest_body_from_membership(**_build_kwargs(None))  # type: ignore[arg-type]
    with pytest.raises((TypeError, ValueError)):
        mod.build_manifest_body_from_membership(
            **_build_kwargs({'entities': None, 'edges': [], 'sources': [], 'evidence_links': []})
        )


def test_manifest_single_member():
    """MANI-01: single entity membership serializes deterministically; embeddings stripped."""
    mod = _require('build_manifest_body_from_membership', 'serialize_manifest_body', 'manifest_sha256')
    body = mod.build_manifest_body_from_membership(**_build_kwargs(_single_member_membership()))
    assert body['counts']['entities'] == 1
    assert len(body['entities']) == 1
    row = body['entities'][0]
    assert row == {
        'uuid': 'e1',
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'content_sha256': 'a' * 64,
        'projected_status': 'created',
    }
    assert 'name_embedding' not in row
    assert 'batch_id' not in row
    raw_a = mod.serialize_manifest_body(body)
    raw_b = mod.serialize_manifest_body(
        mod.build_manifest_body_from_membership(**_build_kwargs(_single_member_membership()))
    )
    assert raw_a == raw_b
    assert mod.manifest_sha256(raw_a) == mod.manifest_sha256(raw_b)


def test_manifest_four_category_membership():
    """MANI-01: entities+edges+sources+evidence_links all participate; unchanged kept."""
    mod = _require('build_manifest_body_from_membership', 'serialize_manifest_body', 'manifest_sha256')
    membership = _four_category_membership()
    body = mod.build_manifest_body_from_membership(**_build_kwargs(membership))
    assert body['counts'] == {
        'entities': 2,
        'edges': 1,
        'sources': 1,
        'evidence_links': 1,
    }
    # sorted by graph_key: DEPARTMENTS before EMPLOYEES
    assert [e['graph_key'] for e in body['entities']] == [
        'TABLE::FE::ORCL.HR.DEPARTMENTS',
        'TABLE::FE::ORCL.HR.EMPLOYEES',
    ]
    assert body['entities'][0]['projected_status'] == 'unchanged'
    assert body['entities'][1]['projected_status'] == 'created'
    assert body['edges'][0]['projected_status'] == 'updated'
    assert 'fact_embedding' not in body['edges'][0]
    assert set(body['edges'][0].keys()) == {
        'uuid',
        'edge_type',
        'edge_key',
        'content_sha256',
        'projected_status',
    }
    assert set(body['sources'][0].keys()) == {
        'uuid',
        'source_key',
        'content_sha256',
        'projected_status',
    }
    assert set(body['evidence_links'][0].keys()) == {
        'uuid',
        'link_key',
        'content_sha256',
    }
    raw = mod.serialize_manifest_body(body)
    # all four categories appear in canonical bytes
    text = raw.decode('utf-8')
    assert 'TABLE::FE::ORCL.HR.EMPLOYEES' in text
    assert 'FK::EMP->DEPT' in text
    assert 'SRC::ddl.sql#employees' in text
    assert 'evidence_links' in text
    digest = mod.manifest_sha256(raw)
    assert len(digest) == 64 and digest == digest.lower()


def test_manifest_canonical_bytes_stable():
    """MANI-01/02: equal membership yields byte-identical canonical serialization."""
    mod = _require('build_manifest_body_from_membership', 'serialize_manifest_body', 'manifest_sha256')
    m = _four_category_membership()
    # reverse entity input order; output must still be key-sorted and identical
    m2 = copy.deepcopy(m)
    m2['entities'] = list(reversed(m2['entities']))
    a = mod.serialize_manifest_body(mod.build_manifest_body_from_membership(**_build_kwargs(m)))
    b = mod.serialize_manifest_body(mod.build_manifest_body_from_membership(**_build_kwargs(m2)))
    assert a == b
    assert mod.manifest_sha256(a) == mod.manifest_sha256(b)
    # golden: sort_keys + compact separators + utf-8
    body = mod.build_manifest_body_from_membership(**_build_kwargs(m))
    expected = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode(
        'utf-8'
    )
    assert a == expected


def test_manifest_equal_key_sort_stability():
    """MANI-02: equal-key members sort stably by uuid; no merge of distinct UUIDs."""
    mod = _require('build_manifest_body_from_membership', 'serialize_manifest_body')
    membership = {
        'entities': [
            {
                'uuid': 'u-z',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::SAME',
                'content_sha256': 'a' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 'u-a',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::SAME',
                'content_sha256': 'b' * 64,
                'projected_status': 'unchanged',
            },
            {
                'uuid': 'u-m',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::SAME',
                'content_sha256': 'c' * 64,
                'projected_status': 'updated',
            },
        ],
        'edges': [],
        'sources': [],
        'evidence_links': [],
    }
    body = mod.build_manifest_body_from_membership(**_build_kwargs(membership))
    uuids = [e['uuid'] for e in body['entities']]
    assert uuids == sorted(uuids)
    assert len(uuids) == 3
    # input reverse order still yields same order
    membership2 = copy.deepcopy(membership)
    membership2['entities'] = list(reversed(membership2['entities']))
    body2 = mod.build_manifest_body_from_membership(**_build_kwargs(membership2))
    assert [e['uuid'] for e in body2['entities']] == uuids
    assert mod.serialize_manifest_body(body) == mod.serialize_manifest_body(body2)


def test_manifest_adjacency_equal_graph_key_ordering():
    """MANI-02: equal graph_key adjacency ordering is deterministic (uuid secondary)."""
    mod = _require('build_manifest_body_from_membership')
    membership = {
        'entities': [
            {
                'uuid': 'bb',
                'entity_type': 'Column',
                'graph_key': 'COLUMN::X',
                'content_sha256': '1' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 'aa',
                'entity_type': 'Column',
                'graph_key': 'COLUMN::X',
                'content_sha256': '2' * 64,
                'projected_status': 'created',
            },
        ],
        'edges': [
            {
                'uuid': 'r-b',
                'edge_type': 'Contains',
                'edge_key': 'EDGE::SAME',
                'content_sha256': '3' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 'r-a',
                'edge_type': 'Contains',
                'edge_key': 'EDGE::SAME',
                'content_sha256': '4' * 64,
                'projected_status': 'created',
            },
        ],
        'sources': [
            {
                'uuid': 's-b',
                'source_key': 'SRC::same',
                'content_sha256': '5' * 64,
                'projected_status': 'created',
            },
            {
                'uuid': 's-a',
                'source_key': 'SRC::same',
                'content_sha256': '6' * 64,
                'projected_status': 'created',
            },
        ],
        'evidence_links': [
            {
                'uuid': 'l-b',
                'link_key': 'LINK::same',
                'content_sha256': '7' * 64,
            },
            {
                'uuid': 'l-a',
                'link_key': 'LINK::same',
                'content_sha256': '8' * 64,
            },
        ],
    }
    body = mod.build_manifest_body_from_membership(**_build_kwargs(membership))
    assert [e['uuid'] for e in body['entities']] == ['aa', 'bb']
    assert [e['uuid'] for e in body['edges']] == ['r-a', 'r-b']
    assert [s['uuid'] for s in body['sources']] == ['s-a', 's-b']
    assert [l['uuid'] for l in body['evidence_links']] == ['l-a', 'l-b']


def test_manifest_chunk_exact_default_boundary():
    """MANI-04: payload exactly DEFAULT_CHUNK_BYTES produces one well-formed chunk."""
    mod = _require('chunk_manifest_bytes', 'DEFAULT_CHUNK_BYTES')
    assert mod.DEFAULT_CHUNK_BYTES == DEFAULT_CHUNK_BYTES
    data = b'x' * DEFAULT_CHUNK_BYTES
    chunks = mod.chunk_manifest_bytes(data, chunk_size=DEFAULT_CHUNK_BYTES)
    assert len(chunks) == 1
    assert chunks[0]['chunk_index'] == 0
    assert chunks[0]['byte_offset'] == 0
    assert chunks[0]['byte_length'] == DEFAULT_CHUNK_BYTES
    assert chunks[0]['chunk_sha256'] == hashlib.sha256(data).hexdigest()
    # multi-chunk contiguous indices
    data3 = b'y' * (DEFAULT_CHUNK_BYTES * 3)
    chunks3 = mod.chunk_manifest_bytes(data3, chunk_size=DEFAULT_CHUNK_BYTES)
    assert [c['chunk_index'] for c in chunks3] == [0, 1, 2]
    # empty body → single empty chunk (prepared-artifact contract)
    empty_chunks = mod.chunk_manifest_bytes(b'', chunk_size=64)
    assert len(empty_chunks) == 1
    assert empty_chunks[0]['byte_length'] == 0


def test_manifest_chunk_hard_plus_one_fails():
    """MANI-04: chunk_size HARD_CHUNK_BYTES+1 fails closed (no silent truncate)."""
    mod = _require('chunk_manifest_bytes', 'HARD_CHUNK_BYTES', 'chunk_manifest_body')
    assert mod.HARD_CHUNK_BYTES == HARD_CHUNK_BYTES
    with pytest.raises(ValueError):
        mod.chunk_manifest_bytes(b'abc', chunk_size=HARD_CHUNK_BYTES + 1)
    # exact hard size ok
    data = b'z' * HARD_CHUNK_BYTES
    chunks = mod.chunk_manifest_bytes(data, chunk_size=HARD_CHUNK_BYTES)
    assert len(chunks) == 1
    assert chunks[0]['byte_length'] == HARD_CHUNK_BYTES
    # body path also rejects oversized chunk_size
    with pytest.raises(ValueError):
        mod.chunk_manifest_body(
            mod.build_manifest_body_from_membership(**_build_kwargs(_empty_membership()))
            if hasattr(mod, 'build_manifest_body_from_membership')
            else {'manifest_serialization_version': 'catalog-manifest-v1'},
            chunk_size=HARD_CHUNK_BYTES + 1,
        )


def test_manifest_no_self_hash_field():
    """MANI-01: canonical body must not embed its own sha256 field."""
    mod = _require(
        'build_manifest_body_from_membership',
        'serialize_manifest_body',
        'manifest_sha256',
    )
    body = mod.build_manifest_body_from_membership(**_build_kwargs(_four_category_membership()))
    assert 'manifest_sha256' not in body
    raw = mod.serialize_manifest_body(body)
    assert b'manifest_sha256' not in raw
    # injecting self-hash is rejected
    bad = dict(body)
    bad['manifest_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='manifest_sha256'):
        mod.serialize_manifest_body(bad)
    # non-finite floats rejected
    bad2 = dict(body)
    bad2['counts'] = dict(body['counts'])
    bad2['nan_probe'] = math.nan
    with pytest.raises(ValueError, match='non-finite'):
        mod.serialize_manifest_body(bad2)


def test_manifest_byte_identical_rehash():
    """MANI-02: rehash of canonical bytes equals stored digest (byte-identical)."""
    mod = _require(
        'build_manifest_body_from_membership',
        'serialize_manifest_body',
        'manifest_sha256',
        'chunk_manifest_body',
    )
    body = mod.build_manifest_body_from_membership(**_build_kwargs(_four_category_membership()))
    raw = mod.serialize_manifest_body(body)
    digest = mod.manifest_sha256(raw)
    assert digest == hashlib.sha256(raw).hexdigest()
    assert digest == mod.manifest_sha256(raw)
    # chunk_manifest_body reuses framing and reassembles to same bytes
    from services.catalog_prepared_artifact import reassemble_artifact_bytes

    chunks = mod.chunk_manifest_body(body, chunk_size=64)
    rebuilt = reassemble_artifact_bytes(chunks, expected_sha256=digest, expected_length=len(raw))
    assert rebuilt == raw


def test_manifest_builder_ignores_batch_id_for_membership():
    """MANI-03: pure builder never consults member batch_id for membership bytes."""
    mod = _require('build_manifest_body_from_membership', 'serialize_manifest_body')
    src = inspect.getsource(mod.build_manifest_body_from_membership)
    # member.batch_id must not be read as authority (scope batch_id param is ok)
    assert 'entity.batch_id' not in src
    assert "['batch_id']" not in src or 'member' not in src
    m1 = _single_member_membership()
    m2 = copy.deepcopy(m1)
    m2['entities'][0]['batch_id'] = 'totally-different-batch'
    a = mod.serialize_manifest_body(mod.build_manifest_body_from_membership(**_build_kwargs(m1)))
    b = mod.serialize_manifest_body(mod.build_manifest_body_from_membership(**_build_kwargs(m2)))
    assert a == b
    # scope batch_id is in body header, not membership rows
    body = mod.build_manifest_body_from_membership(**_build_kwargs(m1, batch_id='scope-batch'))
    assert body['batch_id'] == 'scope-batch'
    assert all('batch_id' not in row for row in body['entities'])


def test_catalog_manifest_chunk_uuid_deterministic():
    """D-17: ManifestChunk material group_id|catalog-v2|ManifestChunk|batch_id|index."""
    from services.catalog_identity import catalog_manifest_chunk_uuid

    a = catalog_manifest_chunk_uuid(FIXED_NS, GROUP, BATCH_ID, 0)
    b = catalog_manifest_chunk_uuid(FIXED_NS, GROUP, BATCH_ID, 0)
    c = catalog_manifest_chunk_uuid(FIXED_NS, GROUP, BATCH_ID, 1)
    assert a == b
    assert a != c
    expected = str(
        uuid.uuid5(FIXED_NS, f'{GROUP}|catalog-v2|ManifestChunk|{BATCH_ID}|0')
    )
    assert a == expected


def test_manifest_module_has_no_io():
    """Pure module: no Neo4j / open / network."""
    mod = _require('serialize_manifest_body')
    src = inspect.getsource(mod)
    assert 'neo4j' not in src.lower()
    assert 'open(' not in src
    assert 'http' not in src.lower()
