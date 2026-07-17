"""Unit tests for deterministic catalog identity and canonical hashing."""

from __future__ import annotations

import inspect
import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_common import CatalogErrorCode, IDENTITY_SCHEMA_VERSION  # noqa: E402
from services import catalog_identity as identity_mod  # noqa: E402
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
# Offline historical ACCEPT_TAB server request SHA-256 (catalog-v1). Never a v2 UUID golden.
ACCEPT_TAB_HISTORICAL_SHA = 'a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a'
ACCEPT_TAB_ARTIFACT_SHA = 'a89e3427a3b1ceec10f36d361fcdbe9e7e30243db4ff51ca59848dfb33968a33'

# Versioned catalog-v2 materials (IDEN-07 / IDEN-10)
V = IDENTITY_SCHEMA_VERSION  # 'catalog-v2'


def test_identity_schema_version_is_catalog_v2():
    assert IDENTITY_SCHEMA_VERSION == 'catalog-v2'
    assert V == 'catalog-v2'


def test_catalog_entity_uuid_matches_uuid5():
    key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    got = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key)
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Table|{key}'))
    assert got == expected


def test_catalog_edge_uuid_matches_uuid5():
    got = catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', 'CONTAINS::S->T')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Contains|CONTAINS::S->T'))
    assert got == expected


def test_entity_uuid_stable_across_calls():
    a = catalog_entity_uuid(FIXED_NS, GROUP, 'Column', 'COLUMN::FE::ORCL.HR.EMPLOYEES.ID')
    b = catalog_entity_uuid(FIXED_NS, GROUP, 'Column', 'COLUMN::FE::ORCL.HR.EMPLOYEES.ID')
    assert a == b


def test_different_entity_type_or_key_yields_different_uuid():
    base = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.A')
    other_type = catalog_entity_uuid(FIXED_NS, GROUP, 'View', 'TABLE::FE::ORCL.A')
    other_key = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.B')
    assert base != other_type
    assert base != other_key


def test_fe_bo_same_oracle_body_different_entity_uuids():
    """IDEN-04 / IDEN-10: FE vs BO system-scoped keys yield distinct UUIDs under one group."""
    fe_key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    bo_key = 'TABLE::BO::ORCL.HR.EMPLOYEES'
    fe = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', fe_key)
    bo = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', bo_key)
    assert fe != bo
    assert fe == str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Table|{fe_key}'))
    assert bo == str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Table|{bo_key}'))


def test_procedure_overload_discriminator_yields_different_uuids():
    """IDEN-06 / IDEN-10: Procedure #a vs #b overloads produce distinct entity UUIDs."""
    a_key = 'PROCEDURE::FE::ORCL.HR.PKG.P#a'
    b_key = 'PROCEDURE::FE::ORCL.HR.PKG.P#b'
    a = catalog_entity_uuid(FIXED_NS, GROUP, 'Procedure', a_key)
    b = catalog_entity_uuid(FIXED_NS, GROUP, 'Procedure', b_key)
    assert a != b
    assert a == str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Procedure|{a_key}'))
    assert b == str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Procedure|{b_key}'))


def test_v1_material_uuid_never_equals_catalog_v2():
    """IDEN-13: unversioned v1 material UUID differs from catalog-v2 for same inputs."""
    key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    v1 = str(uuid.uuid5(FIXED_NS, f'{GROUP}|Table|{key}'))
    v2 = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key)
    assert v1 != v2
    assert v2 == str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Table|{key}'))
    # edge / source / batch / mentions similarly versioned
    assert catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', 'K') != str(
        uuid.uuid5(FIXED_NS, f'{GROUP}|Contains|K')
    )
    assert catalog_source_uuid(FIXED_NS, GROUP, 'SRC::A') != str(
        uuid.uuid5(FIXED_NS, f'{GROUP}|Source|SRC::A')
    )
    assert catalog_batch_uuid(FIXED_NS, GROUP, 'batch-1') != str(
        uuid.uuid5(FIXED_NS, f'{GROUP}|Batch|batch-1')
    )


def test_accept_tab_historical_digests_not_used_as_uuid_goldens():
    """IDEN-13: ACCEPT_TAB historical SHAs are never imported as entity UUID goldens."""
    key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    entity_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key)
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', 'CONTAINS::S->T')
    source_uuid = catalog_source_uuid(FIXED_NS, GROUP, 'DOC::HR.PDF#p12')
    batch_uuid = catalog_batch_uuid(FIXED_NS, GROUP, 'batch-42')
    goldens = {entity_uuid, edge_uuid, source_uuid, batch_uuid}
    assert ACCEPT_TAB_HISTORICAL_SHA not in goldens
    assert ACCEPT_TAB_ARTIFACT_SHA not in goldens
    # digests are 64-char sha256, not UUID form
    assert len(ACCEPT_TAB_HISTORICAL_SHA) == 64
    assert '-' not in ACCEPT_TAB_HISTORICAL_SHA
    assert entity_uuid != ACCEPT_TAB_HISTORICAL_SHA
    assert entity_uuid != ACCEPT_TAB_ARTIFACT_SHA


def test_empty_graph_key_direct_helper_is_deterministic():
    """Empty graph_key still yields deterministic uuid5 of empty segment if called directly."""
    a = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', '')
    b = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', '')
    assert a == b
    assert a == str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Table|'))


def test_identity_functions_do_not_accept_caller_uuid_authority():
    """SAFE-05 / IDEN-05: signatures have no caller UUID identity parameter."""
    helpers = (
        catalog_entity_uuid,
        catalog_edge_uuid,
        catalog_source_uuid,
        catalog_batch_uuid,
        catalog_mentions_uuid,
    )
    # future pure helpers (IDEN-11) — getattr so missing names assert rather than ImportError
    for name in (
        'catalog_evidence_link_uuid',
        'catalog_manifest_uuid',
        'catalog_prepared_plan_uuid',
    ):
        fn = getattr(identity_mod, name, None)
        assert fn is not None, f'missing pure helper {name}'
        helpers = helpers + (fn,)

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
    """IDEN-03: UUIDv5(ns, group_id|catalog-v2|Source|source_key)."""
    got = catalog_source_uuid(FIXED_NS, GROUP, 'DOC::HR.PDF#p12')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Source|DOC::HR.PDF#p12'))
    assert got == expected


def test_catalog_batch_uuid_matches_uuid5():
    """IDEN-04: UUIDv5(ns, group_id|catalog-v2|Batch|batch_id)."""
    got = catalog_batch_uuid(FIXED_NS, GROUP, 'batch-42')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Batch|batch-42'))
    assert got == expected


def test_catalog_mentions_uuid_matches_uuid5():
    """A3: UUIDv5(ns, group_id|catalog-v2|Mentions|source_uuid|entity_uuid)."""
    source_uuid = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::A')
    entity_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    got = catalog_mentions_uuid(FIXED_NS, GROUP, source_uuid, entity_uuid)
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Mentions|{source_uuid}|{entity_uuid}'))
    assert got == expected


def test_catalog_evidence_link_uuid_matches_uuid5():
    """IDEN-11: pure EvidenceLink helper — group_id|catalog-v2|EvidenceLink|link_key."""
    fn = getattr(identity_mod, 'catalog_evidence_link_uuid', None)
    assert fn is not None
    got = fn(FIXED_NS, GROUP, 'EVID::link-1')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|EvidenceLink|EVID::link-1'))
    assert got == expected
    assert got == fn(FIXED_NS, GROUP, 'EVID::link-1')


def test_catalog_manifest_uuid_matches_uuid5():
    """IDEN-11: pure Manifest helper — group_id|catalog-v2|Manifest|batch_id."""
    fn = getattr(identity_mod, 'catalog_manifest_uuid', None)
    assert fn is not None
    got = fn(FIXED_NS, GROUP, 'batch-42')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|Manifest|batch-42'))
    assert got == expected
    assert got == fn(FIXED_NS, GROUP, 'batch-42')


def test_catalog_prepared_plan_uuid_matches_uuid5():
    """IDEN-11: pure PreparedPlan helper — group_id|catalog-v2|PreparedPlan|plan_id."""
    fn = getattr(identity_mod, 'catalog_prepared_plan_uuid', None)
    assert fn is not None
    got = fn(FIXED_NS, GROUP, 'plan-7')
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|{V}|PreparedPlan|plan-7'))
    assert got == expected
    assert got == fn(FIXED_NS, GROUP, 'plan-7')


def test_future_helpers_have_no_persistence_or_store_wiring():
    """IDEN-11: future helpers remain pure — no store/service attributes on module."""
    for bad in ('store', 'neo4j', 'driver', 'service', 'persist', 'write'):
        assert not any(bad in n.lower() for n in dir(identity_mod) if not n.startswith('__'))


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
    e1 = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.A')
    e2 = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.B')
    base = catalog_mentions_uuid(FIXED_NS, GROUP, s1, e1)
    assert base != catalog_mentions_uuid(FIXED_NS, GROUP, s2, e1)
    assert base != catalog_mentions_uuid(FIXED_NS, GROUP, s1, e2)


def test_identity_module_has_no_io_imports():
    forbidden_substrings = (
        'neo4j',
        'embedder',
        'llm',
        'openai',
        'queue',
        'graphiti_core',
        'catalog_store',
        'catalog_service',
    )
    for _name, value in vars(identity_mod).items():
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
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
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
