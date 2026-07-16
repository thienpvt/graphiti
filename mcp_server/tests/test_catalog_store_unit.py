"""Unit tests for CatalogNeo4jStore Cypher builders (no live Neo4j)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_common import ENTITY_TYPE_PREFIXES  # noqa: E402
from services.catalog_store import (  # noqa: E402
    CatalogNeo4jStore,
    CatalogStoreError,
    serialize_nested_json,
)


FIXED_TS = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-001'
UUID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
HASH = 'a' * 64


def _base_params(**overrides):
    params = {
        'uuid': UUID,
        'group_id': GROUP,
        'batch_id': BATCH,
        'graph_key': 'TABLE::HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'HR.EMPLOYEES',
        'summary': 'Employee table',
        'content_sha256': HASH,
        'created_at': FIXED_TS,
        'updated_at': FIXED_TS,
        'name_embedding': [0.1, 0.2, 0.3],
        'attributes': {'owner': 'HR'},
        'source_refs': [{'doc': 'ddl', 'line': 10}],
        'confidence': 0.9,
    }
    params.update(overrides)
    return params


def test_resolve_entity_label_allowlisted():
    store = CatalogNeo4jStore()
    for entity_type in ENTITY_TYPE_PREFIXES:
        label = store.resolve_entity_label(entity_type)
        assert label == entity_type
        assert label in ENTITY_TYPE_PREFIXES


def test_resolve_entity_label_rejects_unknown_type():
    store = CatalogNeo4jStore()
    with pytest.raises(CatalogStoreError) as exc:
        store.resolve_entity_label('Evil; DROP')
    assert 'not allowlisted' in str(exc.value).lower() or 'unknown' in str(exc.value).lower()


def test_build_entity_upsert_cypher_uses_allowlisted_label_literal():
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('Table')
    assert ':Table' in cypher
    assert ':Entity' in cypher
    # Client-controlled raw type must not appear as free-form f-string of unknown value
    assert 'MERGE (n:Entity {uuid: $uuid})' in cypher


def test_build_entity_upsert_cypher_rejects_unknown_before_query_text():
    store = CatalogNeo4jStore()
    with pytest.raises(CatalogStoreError):
        store.build_entity_upsert_cypher('NotAType')


def test_build_entity_upsert_cypher_no_full_map_set():
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('Column')
    # Anti-pattern: stock SET n = $entity_data / SET n = $map
    assert 'SET n = $' not in cypher
    assert 'SET n=$' not in cypher
    assert 'SET n = removeKeyFromMap' not in cypher


def test_build_entity_upsert_cypher_has_on_create_and_on_match():
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('Schema')
    assert 'ON CREATE SET' in cypher
    assert 'ON MATCH SET' in cypher
    assert 'batch_id' in cypher
    assert 'created_at' in cypher
    assert 'updated_at' in cypher
    assert 'content_sha256' in cypher


def test_on_create_and_changed_match_include_batch_id():
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('View')
    # batch_id must appear in property assignment lists
    assert 'n.batch_id = $batch_id' in cypher or 'n.batch_id=$batch_id' in cypher
    # identical-hash path must preserve existing batch_id via CASE or equivalent
    assert 'content_sha256' in cypher
    assert 'CASE' in cypher.upper() or 'WHEN' in cypher.upper()


def test_cypher_parameterizes_values_not_client_identifiers():
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('Index')
    # Property names are server fixed; values are $params
    for prop in (
        'uuid',
        'group_id',
        'name',
        'graph_key',
        'name_raw',
        'name_canonical',
        'database_qualified_name',
        'summary',
        'content_sha256',
        'batch_id',
        'source_refs',
        'name_embedding',
    ):
        assert f'${prop}' in cypher or prop == 'name_embedding'
    # No client string interpolation of property names from request
    assert '${' not in cypher  # no nested client templates


def test_serialize_nested_json_source_refs():
    refs = [{'page': 1, 'span': [2, 3]}, 'plain']
    out = serialize_nested_json(refs)
    assert isinstance(out, str)
    parsed = json.loads(out)
    assert parsed == refs


def test_serialize_nested_json_none():
    assert serialize_nested_json(None) is None


def test_prepare_entity_params_name_equals_graph_key():
    store = CatalogNeo4jStore()
    params = store.prepare_entity_params(
        entity_type='Table',
        **_base_params(),
    )
    assert params['name'] == params['graph_key']
    assert params['labels'] == ['Entity', 'Table']
    assert isinstance(params['source_refs'], str)
    assert isinstance(params.get('attributes'), (str, type(None)))
    # Protected keys never come from client attributes map as top-level overrides
    assert params['uuid'] == UUID
    assert params['group_id'] == GROUP


def test_prepare_entity_params_rejects_unknown_type():
    store = CatalogNeo4jStore()
    with pytest.raises(CatalogStoreError):
        store.prepare_entity_params(entity_type='Injected', **_base_params())


def test_prepare_entity_params_strips_protected_from_attributes():
    """Even if caller bypasses Pydantic, protected keys in attributes are dropped."""
    store = CatalogNeo4jStore()
    params = store.prepare_entity_params(
        entity_type='Table',
        **_base_params(attributes={'owner': 'HR', 'uuid': 'evil', 'created_at': 'x'}),
    )
    # attributes serialized without protected keys
    attrs = json.loads(params['attributes']) if params['attributes'] else {}
    assert 'owner' in attrs
    assert 'uuid' not in attrs
    assert 'created_at' not in attrs
    # identity still server-controlled
    assert params['uuid'] == UUID


def test_build_get_entity_by_uuid_cypher_parameterized():
    store = CatalogNeo4jStore()
    cypher = store.build_get_entity_by_uuid_cypher()
    assert 'MATCH' in cypher
    assert '$uuid' in cypher
    assert '$group_id' in cypher
    assert 'SET n = $' not in cypher


def test_build_get_entity_by_group_name_type_uses_allowlisted_label():
    store = CatalogNeo4jStore()
    cypher = store.build_get_entity_by_group_name_type_cypher('Procedure')
    assert ':Procedure' in cypher or 'Procedure' in cypher
    assert '$group_id' in cypher
    assert '$name' in cypher or '$graph_key' in cypher
    with pytest.raises(CatalogStoreError):
        store.build_get_entity_by_group_name_type_cypher('Nope')


def test_identical_hash_noop_clause_preserves_batch_id():
    """Generated ON MATCH must not blindly overwrite batch_id on identical hash."""
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('Function')
    # The identical path leaves batch_id untouched: CASE WHEN existing hash equals
    assert 'n.content_sha256' in cypher
    # Ensure we do not have unconditional n.batch_id = $batch_id only on MATCH without CASE
    # (ON CREATE may set unconditionally; ON MATCH must be conditional)
    on_match_idx = cypher.index('ON MATCH SET')
    on_match_section = cypher[on_match_idx:]
    assert 'CASE' in on_match_section.upper()


def test_first_from_execute_query_result_uses_tuple_contract():
    """Neo4jDriver.execute_query returns EagerResult = (records, summary, keys)."""
    store = CatalogNeo4jStore()
    parse = store._first_from_execute_query_result

    assert parse(None) is None
    assert parse(([], None, [])) is None
    assert parse(([{'uuid': 'u1', 'group_id': GROUP}], None, ['uuid', 'group_id'])) == {
        'uuid': 'u1',
        'group_id': GROUP,
    }
    # Non-tuple objects (including fake .records attrs) are rejected
    assert parse(SimpleNamespace(records=[{'uuid': 'nope'}])) is None
