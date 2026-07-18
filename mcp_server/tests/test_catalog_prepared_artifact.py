"""Pure prepared-artifact serialize/chunk/reassemble contract (PLAN-04, PLAN-05)."""

from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from services.catalog_identity import (  # noqa: E402
    CANONICALIZATION_VERSION,
    CATALOG_SCHEMA_VERSION,
    catalog_prepared_plan_chunk_uuid,
)
from services.catalog_prepared_artifact import (  # noqa: E402
    DEFAULT_CHUNK_BYTES,
    HARD_CHUNK_BYTES,
    MAX_CHUNKS_PER_PLAN,
    PREPARED_ARTIFACT_SERIALIZATION_VERSION,
    artifact_sha256,
    chunk_artifact_bytes,
    reassemble_artifact_bytes,
    serialize_prepared_artifact,
)

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'


def _membership_fixture() -> dict:
    return {
        'entities': [
            {
                'uuid': 'e1',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': 'a' * 64,
                'projected_status': 'created',
                'name_embedding': [0.1, 0.2, 0.3],
            }
        ],
        'edges': [
            {
                'uuid': 'r1',
                'edge_type': 'ForeignKeyTo',
                'edge_key': 'FK::A->B',
                'source_uuid': 'e1',
                'target_uuid': 'e2',
                'content_sha256': 'b' * 64,
                'projected_status': 'created',
                'fact_embedding': [0.4, 0.5],
            }
        ],
        'sources': [
            {
                'uuid': 's1',
                'source_key': 'SRC::ddl.sql#employees',
                'content_sha256': 'c' * 64,
                'projected_status': 'created',
            }
        ],
        'evidence_links': [
            {
                'uuid': 'l1',
                'link_key': 'SRC::ddl.sql#employees|entity|Table|TABLE::FE::ORCL.HR.EMPLOYEES|...',
                'content_sha256': 'd' * 64,
            }
        ],
    }


def _artifact_body(**overrides) -> dict:
    body = {
        'artifact_serialization_version': PREPARED_ARTIFACT_SERIALIZATION_VERSION,
        'canonicalization_version': CANONICALIZATION_VERSION,
        'identity_schema_version': 'catalog-v2',
        'catalog_schema_version': CATALOG_SCHEMA_VERSION,
        'group_id': GROUP,
        'batch_id': 'batch-prepare-001',
        'system_key': 'FE',
        'request_sha256': '1' * 64,
        'catalog_sha256': '2' * 64,
        'plan_id': 'batch-prepare-001|' + ('1' * 64),
        'membership': _membership_fixture(),
        'request_canonical': {
            'canonicalization_version': CANONICALIZATION_VERSION,
            'batch_id': 'batch-prepare-001',
            'group_id': GROUP,
        },
        'counts': {
            'entities': 1,
            'edges': 1,
            'sources': 1,
            'evidence_links': 1,
            'created': 2,
            'updated': 0,
            'unchanged': 0,
        },
    }
    body.update(overrides)
    return body


def test_serialization_version_constant():
    assert PREPARED_ARTIFACT_SERIALIZATION_VERSION == 'prepared-artifact-v1'
    assert DEFAULT_CHUNK_BYTES == 131_072
    assert HARD_CHUNK_BYTES == 262_144
    assert MAX_CHUNKS_PER_PLAN == 128


def test_serialize_includes_membership_and_embeddings_not_hashes_only():
    raw = serialize_prepared_artifact(_artifact_body())
    assert isinstance(raw, bytes)
    obj = json.loads(raw.decode('utf-8'))
    assert obj['artifact_serialization_version'] == 'prepared-artifact-v1'
    membership = obj['membership']
    assert 'entities' in membership
    assert 'edges' in membership
    assert 'sources' in membership
    assert 'evidence_links' in membership
    assert membership['entities'][0]['name_embedding'] == [0.1, 0.2, 0.3]
    assert membership['edges'][0]['fact_embedding'] == [0.4, 0.5]
    assert 'request_canonical' in obj
    assert 'counts' in obj
    # Not hashes-only: membership content present beyond digests
    assert membership['entities'][0]['graph_key'].startswith('TABLE::')


def test_serialize_canonical_json_rules():
    raw = serialize_prepared_artifact(_artifact_body())
    expected = json.dumps(
        _artifact_body(), sort_keys=True, separators=(',', ':'), ensure_ascii=False
    ).encode('utf-8')
    assert raw == expected


def test_serialize_rejects_embedded_artifact_sha256():
    body = _artifact_body(artifact_sha256='f' * 64)
    with pytest.raises(ValueError, match='artifact_sha256'):
        serialize_prepared_artifact(body)


def test_artifact_sha256_stable_and_external():
    body = _artifact_body()
    raw = serialize_prepared_artifact(body)
    digest = artifact_sha256(raw)
    assert len(digest) == 64
    assert digest == hashlib.sha256(raw).hexdigest()
    assert digest == artifact_sha256(raw)
    # input bytes not mutated
    before = bytes(raw)
    _ = artifact_sha256(raw)
    assert raw == before
    # self-hash field never appears in body
    assert b'artifact_sha256' not in raw


def test_chunk_exact_boundary_produces_n_chunks():
    data = b'x' * (DEFAULT_CHUNK_BYTES * 3)
    chunks = chunk_artifact_bytes(data, chunk_size=DEFAULT_CHUNK_BYTES)
    assert len(chunks) == 3
    for i, ch in enumerate(chunks):
        assert ch['chunk_index'] == i
        assert ch['byte_offset'] == i * DEFAULT_CHUNK_BYTES
        assert ch['byte_length'] == DEFAULT_CHUNK_BYTES
        payload = base64.b64decode(ch['payload_b64'])
        assert len(payload) == DEFAULT_CHUNK_BYTES
        assert ch['chunk_sha256'] == hashlib.sha256(payload).hexdigest()


def test_chunk_size_minus_one_boundary_splits_extra():
    size = 100
    data = b'y' * (size * 2 - 1)
    chunks = chunk_artifact_bytes(data, chunk_size=size)
    assert len(chunks) == 2
    assert chunks[0]['byte_length'] == size
    assert chunks[1]['byte_length'] == size - 1
    assert reassemble_artifact_bytes(chunks) == data


def test_chunk_one_chunk_for_small_payload():
    data = b'hello-prepared-artifact'
    chunks = chunk_artifact_bytes(data, chunk_size=DEFAULT_CHUNK_BYTES)
    assert len(chunks) == 1
    assert chunks[0]['chunk_index'] == 0
    assert reassemble_artifact_bytes(chunks) == data


def test_empty_bytes_single_empty_chunk():
    """Empty payload yields one empty chunk (documented rule)."""
    chunks = chunk_artifact_bytes(b'', chunk_size=64)
    assert len(chunks) == 1
    assert chunks[0]['byte_length'] == 0
    assert chunks[0]['byte_offset'] == 0
    assert reassemble_artifact_bytes(chunks) == b''


def test_roundtrip_multi_chunk_byte_identical():
    body = _artifact_body()
    raw = serialize_prepared_artifact(body)
    digest = artifact_sha256(raw)
    chunks = chunk_artifact_bytes(raw, chunk_size=64)
    assert len(chunks) > 1
    rebuilt = reassemble_artifact_bytes(chunks, expected_sha256=digest, expected_length=len(raw))
    assert rebuilt == raw
    assert artifact_sha256(rebuilt) == digest


def test_reassemble_sorts_by_chunk_index():
    data = b'abcdefghijklmnopqrstuvwxyz' * 10
    chunks = chunk_artifact_bytes(data, chunk_size=17)
    shuffled = list(reversed(chunks))
    assert reassemble_artifact_bytes(shuffled) == data


def test_reassemble_missing_chunk_fails_closed():
    data = b'z' * 50
    chunks = chunk_artifact_bytes(data, chunk_size=20)
    assert len(chunks) >= 2
    bad = chunks[1:]  # drop index 0
    with pytest.raises(ValueError):
        reassemble_artifact_bytes(bad)


def test_reassemble_bad_b64_fails_closed():
    chunks = [
        {
            'chunk_index': 0,
            'byte_offset': 0,
            'byte_length': 4,
            'chunk_sha256': '0' * 64,
            'payload_b64': '!!!not-valid-b64!!!',
        }
    ]
    with pytest.raises(ValueError):
        reassemble_artifact_bytes(chunks)


def test_reassemble_digest_mismatch_fails_closed():
    data = b'payload'
    chunks = chunk_artifact_bytes(data, chunk_size=64)
    with pytest.raises(ValueError, match='artifact_sha256|digest|sha256'):
        reassemble_artifact_bytes(chunks, expected_sha256='0' * 64)


def test_reassemble_length_mismatch_fails_closed():
    data = b'payload'
    chunks = chunk_artifact_bytes(data, chunk_size=64)
    with pytest.raises(ValueError, match='length'):
        reassemble_artifact_bytes(chunks, expected_length=len(data) + 1)


def test_reassemble_chunk_digest_mismatch_fails_closed():
    data = b'abcd' * 8
    chunks = chunk_artifact_bytes(data, chunk_size=8)
    tampered = copy.deepcopy(chunks)
    tampered[0]['chunk_sha256'] = 'e' * 64
    with pytest.raises(ValueError):
        reassemble_artifact_bytes(tampered)


def test_reassemble_truncated_payload_fails_closed():
    data = b'abcd' * 8
    chunks = chunk_artifact_bytes(data, chunk_size=8)
    tampered = copy.deepcopy(chunks)
    # corrupt b64 to shorter decoded payload while keeping declared length
    tampered[0]['payload_b64'] = base64.b64encode(b'xx').decode('ascii')
    with pytest.raises(ValueError):
        reassemble_artifact_bytes(tampered)


def test_max_chunks_hard_limit_fails_closed():
    # 129 chunks of size 1
    data = b'q' * 129
    with pytest.raises(ValueError, match='chunk'):
        chunk_artifact_bytes(data, chunk_size=1)


def test_chunk_size_above_hard_max_fails_closed():
    with pytest.raises(ValueError):
        chunk_artifact_bytes(b'abc', chunk_size=HARD_CHUNK_BYTES + 1)


def test_catalog_prepared_plan_chunk_uuid_deterministic():
    plan_id = 'batch-1|' + ('a' * 64)
    a = catalog_prepared_plan_chunk_uuid(FIXED_NS, GROUP, plan_id, 0)
    b = catalog_prepared_plan_chunk_uuid(FIXED_NS, GROUP, plan_id, 0)
    c = catalog_prepared_plan_chunk_uuid(FIXED_NS, GROUP, plan_id, 1)
    assert a == b
    assert a != c
    expected = str(
        uuid.uuid5(FIXED_NS, f'{GROUP}|catalog-v2|PreparedPlanChunk|{plan_id}|0')
    )
    assert a == expected


def test_serialize_source_has_no_io_or_token_hooks():
    src = inspect.getsource(serialize_prepared_artifact)
    assert 'open(' not in src
    assert 'neo4j' not in src.lower()
    assert 'plan_token' not in src
