"""Unit tests for deterministic catalog identity and canonical hashing."""

from __future__ import annotations

import inspect
import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_common import CatalogErrorCode  # noqa: E402
from services.catalog_identity import (  # noqa: E402
    assert_optional_client_hash,
    canonical_sha256,
    catalog_batch_uuid,
    catalog_edge_uuid,
    catalog_entity_uuid,
    catalog_mentions_uuid,
    catalog_source_uuid,
)

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'


def test_catalog_entity_uuid_matches_uuid5():
    got = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|Table|TABLE::HR.EMPLOYEES'))
    assert got == expected


def test_catalog_edge_uuid_matches_uuid5():
    got = catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', 'CONTAINS::S->T')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|Contains|CONTAINS::S->T'))
    assert got == expected


def test_entity_uuid_stable_across_calls():
    a = catalog_entity_uuid(FIXED_NS, GROUP, 'Column', 'COLUMN::HR.EMPLOYEES.ID')
    b = catalog_entity_uuid(FIXED_NS, GROUP, 'Column', 'COLUMN::HR.EMPLOYEES.ID')
    assert a == b


def test_different_entity_type_or_key_yields_different_uuid():
    base = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::A')
    other_type = catalog_entity_uuid(FIXED_NS, GROUP, 'View', 'TABLE::A')
    other_key = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::B')
    assert base != other_type
    assert base != other_key


def test_identity_functions_do_not_accept_caller_uuid_authority():
    """IDEN-05: signatures have no caller UUID identity parameter."""
    helpers = (
        catalog_entity_uuid,
        catalog_edge_uuid,
        catalog_source_uuid,
        catalog_batch_uuid,
        catalog_mentions_uuid,
    )
    forbidden = (
        'caller_uuid',
        'client_uuid',
        'uuid',
        'entity_uuid',
        'edge_uuid',
        'source_uuid',
        'batch_uuid',
    )
    for fn in helpers:
        params = inspect.signature(fn).parameters
        for name in forbidden:
            # mentions takes source_uuid/entity_uuid as *derived inputs*, not caller authority
            if fn is catalog_mentions_uuid and name in ('source_uuid', 'entity_uuid'):
                continue
            assert name not in params, f'{fn.__name__} must not accept {name}'


def test_catalog_source_uuid_matches_uuid5():
    """IDEN-03: UUIDv5(ns, group_id|Source|source_key)."""
    got = catalog_source_uuid(FIXED_NS, GROUP, 'DOC::HR.PDF#p12')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|Source|DOC::HR.PDF#p12'))
    assert got == expected


def test_catalog_batch_uuid_matches_uuid5():
    """IDEN-04: UUIDv5(ns, group_id|Batch|batch_id)."""
    got = catalog_batch_uuid(FIXED_NS, GROUP, 'batch-42')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|Batch|batch-42'))
    assert got == expected


def test_catalog_mentions_uuid_matches_uuid5():
    """A3: UUIDv5(ns, group_id|Mentions|source_uuid|entity_uuid)."""
    source_uuid = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::A')
    entity_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::HR.EMPLOYEES')
    got = catalog_mentions_uuid(FIXED_NS, GROUP, source_uuid, entity_uuid)
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|Mentions|{source_uuid}|{entity_uuid}'))
    assert got == expected


def test_source_and_batch_uuid_stable_and_distinct():
    a = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::A')
    b = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::A')
    c = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::B')
    assert a == b
    assert a != c
    ba = catalog_batch_uuid(FIXED_NS, GROUP, 'batch-1')
    bb = catalog_batch_uuid(FIXED_NS, GROUP, 'batch-1')
    bc = catalog_batch_uuid(FIXED_NS, GROUP, 'batch-2')
    assert ba == bb
    assert ba != bc


def test_mentions_uuid_changes_with_either_endpoint():
    s1 = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::1')
    s2 = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::2')
    e1 = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::A')
    e2 = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::B')
    base = catalog_mentions_uuid(FIXED_NS, GROUP, s1, e1)
    assert base != catalog_mentions_uuid(FIXED_NS, GROUP, s2, e1)
    assert base != catalog_mentions_uuid(FIXED_NS, GROUP, s1, e2)


def test_identity_module_has_no_io_imports():
    import services.catalog_identity as mod

    forbidden_substrings = ('neo4j', 'embedder', 'llm', 'openai', 'queue', 'graphiti_core')
    for _name, value in vars(mod).items():
        if inspect.ismodule(value):
            mod_name = getattr(value, '__name__', '')
            lower = mod_name.lower()
            for bad in forbidden_substrings:
                assert bad not in lower, f'unexpected I/O import: {mod_name}'


def test_canonical_sha256_length_and_lowercase():
    digest = canonical_sha256({'b': 1, 'a': 'x'})
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in '0123456789abcdef' for c in digest)


def test_canonical_sha256_key_order_independent():
    h1 = canonical_sha256({'z': 1, 'a': 2, 'm': {'y': 3, 'x': 4}})
    h2 = canonical_sha256({'a': 2, 'm': {'x': 4, 'y': 3}, 'z': 1})
    assert h1 == h2


def test_canonical_sha256_rejects_nan_inf():
    with pytest.raises(ValueError):
        canonical_sha256({'score': math.nan})
    with pytest.raises(ValueError):
        canonical_sha256({'score': math.inf})
    with pytest.raises(ValueError):
        canonical_sha256({'nested': [{'v': -math.inf}]})


def test_same_mutable_payload_same_hash():
    payload = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'summary': 'Employees',
        'attributes': {'rows': 100},
    }
    assert canonical_sha256(payload) == canonical_sha256(dict(payload))


def test_assert_optional_client_hash_none_ok():
    server = canonical_sha256({'k': 'v'})
    assert_optional_client_hash(None, server)  # no raise


def test_assert_optional_client_hash_match_ok():
    server = canonical_sha256({'k': 'v'})
    assert_optional_client_hash(server, server)
    assert_optional_client_hash(server.upper(), server)  # normalize case


def test_assert_optional_client_hash_mismatch():
    server = canonical_sha256({'k': 'v'})
    with pytest.raises(ValueError) as exc:
        assert_optional_client_hash('0' * 64, server)
    assert CatalogErrorCode.content_hash_mismatch.value in str(exc.value)
