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
    catalog_edge_uuid,
    catalog_entity_uuid,
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
    ent_params = inspect.signature(catalog_entity_uuid).parameters
    edge_params = inspect.signature(catalog_edge_uuid).parameters
    for name in ('caller_uuid', 'client_uuid', 'uuid', 'entity_uuid', 'edge_uuid'):
        assert name not in ent_params
        assert name not in edge_params


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
