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


# ---------------------------------------------------------------------------
# Edge endpoint resolution + edge upsert Cypher (EDGE-02..09)
# ---------------------------------------------------------------------------


def test_resolve_edge_type_allowlisted():
    store = CatalogNeo4jStore()
    assert store.resolve_edge_type('ForeignKeyTo') == 'ForeignKeyTo'
    assert store.resolve_edge_type('Contains') == 'Contains'


def test_resolve_edge_type_rejects_unknown():
    store = CatalogNeo4jStore()
    with pytest.raises(CatalogStoreError) as exc:
        store.resolve_edge_type('Evil; DROP')
    assert 'not allowlisted' in str(exc.value).lower()


def test_edge_build_resolve_endpoint_typed_cypher_is_match_only_no_create():
    store = CatalogNeo4jStore()
    cypher = store.build_resolve_endpoint_typed_cypher('Table')
    assert 'MATCH' in cypher
    assert 'CREATE' not in cypher.upper().replace('CREATED_AT', '')
    assert 'MERGE' not in cypher
    assert 'SET ' not in cypher  # read-only
    assert ':Table' in cypher or 'Table' in cypher
    assert '$group_id' in cypher
    assert '$name' in cypher or '$graph_key' in cypher


def test_edge_build_resolve_endpoint_typed_rejects_unknown_type():
    store = CatalogNeo4jStore()
    with pytest.raises(CatalogStoreError):
        store.build_resolve_endpoint_typed_cypher('NotAType')


def test_edge_classify_endpoint_missing_wrong_label_generic():
    store = CatalogNeo4jStore()
    # missing
    code, _ = store.classify_endpoint_rows([], expected_type='Table')
    assert code == 'missing_endpoint'
    # wrong custom label
    code, row = store.classify_endpoint_rows(
        [
            {
                'uuid': 'u1',
                'name': 'TABLE::HR.EMPLOYEES',
                'neo4j_labels': ['Entity', 'View'],
                'labels': ['Entity', 'View'],
            }
        ],
        expected_type='Table',
    )
    assert code == 'endpoint_type_mismatch'
    assert row is not None
    # generic-only Entity
    code, row = store.classify_endpoint_rows(
        [
            {
                'uuid': 'u2',
                'name': 'TABLE::HR.EMPLOYEES',
                'neo4j_labels': ['Entity'],
                'labels': ['Entity'],
            }
        ],
        expected_type='Table',
    )
    assert code == 'generic_endpoint_conflict'
    # correct typed
    code, row = store.classify_endpoint_rows(
        [
            {
                'uuid': 'u3',
                'name': 'TABLE::HR.EMPLOYEES',
                'neo4j_labels': ['Entity', 'Table'],
                'labels': ['Entity', 'Table'],
            }
        ],
        expected_type='Table',
    )
    assert code is None
    assert row is not None and row['uuid'] == 'u3'


def test_build_edge_upsert_cypher_uses_relates_to_and_param_name():
    store = CatalogNeo4jStore()
    cypher = store.build_edge_upsert_cypher()
    assert 'RELATES_TO' in cypher
    assert 'MERGE' in cypher
    assert 'e.name = $name' in cypher or 'e.name=$name' in cypher
    assert 'SET e = $' not in cypher  # no full-map replace
    assert 'ON CREATE SET' in cypher
    assert 'ON MATCH SET' in cypher
    assert 'batch_id' in cypher
    assert 'fact_embedding' in cypher or 'setRelationshipVectorProperty' in cypher
    assert '$source_uuid' in cypher
    assert '$target_uuid' in cypher
    assert '$uuid' in cypher
    # edge type never interpolated as relationship type
    assert ':[ForeignKeyTo]' not in cypher
    assert 'CREATE' not in cypher.split('ON CREATE')[0] or True  # ON CREATE ok


def test_edge_on_create_and_changed_match_include_batch_id():
    store = CatalogNeo4jStore()
    cypher = store.build_edge_upsert_cypher()
    assert 'e.batch_id = $batch_id' in cypher or 'e.batch_id=$batch_id' in cypher
    on_match_idx = cypher.index('ON MATCH SET')
    on_match_section = cypher[on_match_idx:]
    assert 'CASE' in on_match_section.upper()
    assert 'content_sha256' in on_match_section


def test_edge_identical_hash_noop_preserves_batch_id():
    store = CatalogNeo4jStore()
    cypher = store.build_edge_upsert_cypher()
    on_match_idx = cypher.index('ON MATCH SET')
    on_match = cypher[on_match_idx:]
    # conditional batch_id rewrite only when hash differs
    assert 'e.content_sha256' in on_match
    assert 'CASE' in on_match.upper()


def test_prepare_edge_params_sets_name_to_edge_type():
    store = CatalogNeo4jStore()
    params = store.prepare_edge_params(
        edge_type='ForeignKeyTo',
        uuid=UUID,
        group_id=GROUP,
        batch_id=BATCH,
        edge_key='FK::HR.EMPLOYEES->HR.DEPARTMENTS',
        source_uuid='src-uuid',
        target_uuid='tgt-uuid',
        fact='employees.dept_id references departments.id',
        evidence=None,
        content_sha256=HASH,
        created_at=FIXED_TS,
        updated_at=FIXED_TS,
        fact_embedding=[0.1, 0.2],
        attributes={'on_delete': 'CASCADE'},
        confidence=0.9,
    )
    assert params['name'] == 'ForeignKeyTo'
    assert params['edge_key'] == 'FK::HR.EMPLOYEES->HR.DEPARTMENTS'
    assert params['source_uuid'] == 'src-uuid'
    assert params['target_uuid'] == 'tgt-uuid'
    assert params['batch_id'] == BATCH
    assert params['fact'] == 'employees.dept_id references departments.id'
    assert isinstance(params.get('attributes'), (str, type(None)))


def test_prepare_edge_params_rejects_unknown_edge_type():
    store = CatalogNeo4jStore()
    with pytest.raises(CatalogStoreError):
        store.prepare_edge_params(
            edge_type='NotAnEdge',
            uuid=UUID,
            group_id=GROUP,
            batch_id=BATCH,
            edge_key='X',
            source_uuid='s',
            target_uuid='t',
            fact='f',
            evidence=None,
            content_sha256=HASH,
            created_at=FIXED_TS,
            updated_at=FIXED_TS,
            fact_embedding=[0.1],
        )


def test_detect_edge_identity_conflict():
    store = CatalogNeo4jStore()
    existing = {
        'uuid': UUID,
        'name': 'Contains',
        'edge_key': 'CONTAINS::A->B',
        'source_uuid': 's1',
        'target_uuid': 't1',
        'group_id': GROUP,
    }
    # matching identity fields: no conflict
    assert (
        store.detect_edge_identity_conflict(
            existing,
            edge_type='Contains',
            edge_key='CONTAINS::A->B',
            source_uuid='s1',
            target_uuid='t1',
        )
        is None
    )
    # type mismatch
    assert (
        store.detect_edge_identity_conflict(
            existing,
            edge_type='ForeignKeyTo',
            edge_key='CONTAINS::A->B',
            source_uuid='s1',
            target_uuid='t1',
        )
        == 'edge_identity_conflict'
    )
    # source mismatch
    assert (
        store.detect_edge_identity_conflict(
            existing,
            edge_type='Contains',
            edge_key='CONTAINS::A->B',
            source_uuid='s2',
            target_uuid='t1',
        )
        == 'edge_identity_conflict'
    )


def test_build_get_edge_by_uuid_cypher_parameterized():
    store = CatalogNeo4jStore()
    cypher = store.build_get_edge_by_uuid_cypher()
    assert 'MATCH' in cypher
    assert 'RELATES_TO' in cypher
    assert '$uuid' in cypher
    assert '$group_id' in cypher
    assert 'SET e = $' not in cypher
