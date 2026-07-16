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
    CATALOG_ENTITY_IDENTITY_CONSTRAINT,
    CATALOG_RELATES_TO_IDENTITY_CONSTRAINT,
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
    assert 'MERGE (n:Entity {uuid: $uuid, group_id: $group_id})' in cypher


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
    # Create-token status: no ON MATCH marker mutation (zero-mutation unchanged)
    assert 'ON MATCH SET' not in cypher
    assert 'n.group_id = $group_id' in cypher or 'WHERE n.group_id = $group_id' in cypher
    assert 'batch_id' in cypher
    assert 'created_at' in cypher
    assert 'updated_at' in cypher
    assert 'content_sha256' in cypher
    assert '$create_token' in cypher
    assert '_catalog_create_token' in cypher
    assert 'REMOVE n._catalog_create_token' in cypher
    assert 'status' in cypher
    # Vector only on created/updated
    assert "status IN ['created', 'updated']" in cypher or 'status IN' in cypher
    assert 'setNodeVectorProperty' in cypher


def test_on_create_and_changed_match_include_batch_id():
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('View')
    # batch_id must appear in property assignment lists
    assert 'n.batch_id = $batch_id' in cypher or 'n.batch_id=$batch_id' in cypher
    # status derived from create token + pre-update hash
    assert 'content_sha256' in cypher
    assert 'CASE' in cypher.upper() or 'WHEN' in cypher.upper()
    assert '_catalog_create_token' in cypher
    assert 'ON MATCH SET' not in cypher


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
    # Server-generated create token for status classification
    assert isinstance(params.get('create_token'), str)
    assert len(params['create_token']) >= 16


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
    assert 'n.name_raw AS name_raw' in cypher
    assert 'n.name_canonical AS name_canonical' in cypher
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
    """Unchanged path must not SET content props; update path gated by status."""
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('Function')
    assert 'CASE' in cypher.upper()
    # Identity/preservation fields not rewritten after create
    assert 'n.graph_key = CASE' not in cypher
    assert 'n.group_id = CASE' not in cypher
    assert 'n.labels = CASE' not in cypher
    assert 'n.name_raw = CASE' not in cypher
    assert 'n.name_canonical = CASE' not in cypher
    assert "status = 'updated'" in cypher or "status = 'updated'" in cypher.replace(' ', '')
    assert 'REMOVE n._catalog_create_token' in cypher
    assert 'ON MATCH SET' not in cypher


def test_entity_upsert_cypher_scopes_group_and_preserves_identity():
    store = CatalogNeo4jStore()
    cypher = store.build_entity_upsert_cypher('Table')
    # Composite MERGE key matches catalog identity UNIQUE (uuid, group_id).
    assert 'MERGE (n:Entity {uuid: $uuid, group_id: $group_id})' in cypher
    assert '_catalog_create_token' in cypher
    assert 'REMOVE n._catalog_create_token' in cypher
    assert 'n._catalog_create_token AS' not in cypher
    assert 'ON MATCH SET' not in cypher


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
    # MATCH all Entity by group+name; classify_endpoint_rows applies custom label
    assert 'Entity' in cypher
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
    # expected type + extra custom label is wrong_type (exact label contract)
    code, row = store.classify_endpoint_rows(
        [
            {
                'uuid': 'u4',
                'name': 'TABLE::HR.EMPLOYEES',
                'neo4j_labels': ['Entity', 'Table', 'View'],
                'labels': ['Entity', 'Table', 'View'],
            }
        ],
        expected_type='Table',
    )
    assert code == 'endpoint_type_mismatch'
    assert row is not None and row['uuid'] == 'u4'


def test_classify_endpoint_extra_label_not_typed_when_exact_also_present():
    """Duplicates: exact typed preferred; multi-label siblings stay wrong_type."""
    store = CatalogNeo4jStore()
    code, row = store.classify_endpoint_rows(
        [
            {
                'uuid': 'extra',
                'name': 'TABLE::HR.EMPLOYEES',
                'neo4j_labels': ['Entity', 'Table', 'View'],
                'labels': ['Entity', 'Table', 'View'],
            },
            {
                'uuid': 'exact',
                'name': 'TABLE::HR.EMPLOYEES',
                'neo4j_labels': ['Entity', 'Table'],
                'labels': ['Entity', 'Table'],
            },
        ],
        expected_type='Table',
    )
    assert code is None
    assert row is not None and row['uuid'] == 'exact'


def test_classify_endpoint_two_exact_typed_is_duplicate():
    store = CatalogNeo4jStore()
    code, row = store.classify_endpoint_rows(
        [
            {
                'uuid': 'u-a',
                'name': 'TABLE::HR.EMPLOYEES',
                'neo4j_labels': ['Entity', 'Table'],
                'labels': ['Entity', 'Table'],
            },
            {
                'uuid': 'u-b',
                'name': 'TABLE::HR.EMPLOYEES',
                'neo4j_labels': ['Entity', 'Table'],
                'labels': ['Entity', 'Table'],
            },
        ],
        expected_type='Table',
    )
    assert code == 'typed_endpoint_duplicate'
    assert row is None


def test_build_edge_upsert_cypher_uses_relates_to_and_param_name():
    store = CatalogNeo4jStore()
    cypher = store.build_edge_upsert_cypher()
    assert 'RELATES_TO' in cypher
    assert 'MERGE' in cypher
    assert 'e.name = $name' in cypher or 'e.name=$name' in cypher
    assert 'SET e = $' not in cypher  # no full-map replace
    assert 'ON CREATE SET' in cypher
    assert 'ON MATCH SET' not in cypher
    assert 'batch_id' in cypher
    assert 'fact_embedding' in cypher or 'setRelationshipVectorProperty' in cypher
    assert '$source_uuid' in cypher
    assert '$target_uuid' in cypher
    assert '$uuid' in cypher
    # endpoints + edge identity use composite (uuid, group_id) MERGE/MATCH keys
    assert 'MATCH (source:Entity {uuid: $source_uuid, group_id: $group_id})' in cypher
    assert 'MATCH (target:Entity {uuid: $target_uuid, group_id: $group_id})' in cypher
    assert 'MERGE (source)-[e:RELATES_TO {uuid: $uuid, group_id: $group_id}]->(target)' in cypher
    # edge type never interpolated as relationship type
    assert ':[ForeignKeyTo]' not in cypher
    assert '_catalog_create_token' in cypher
    assert 'REMOVE e._catalog_create_token' in cypher
    assert '$create_token' in cypher


def test_edge_on_create_and_changed_match_include_batch_id():
    store = CatalogNeo4jStore()
    cypher = store.build_edge_upsert_cypher()
    assert 'e.batch_id = $batch_id' in cypher or 'e.batch_id=$batch_id' in cypher
    assert '_catalog_create_token' in cypher
    assert 'CASE' in cypher.upper()
    assert 'content_sha256' in cypher
    assert 'ON MATCH SET' not in cypher
    # create + updated paths both set episodes (unchanged FOREACH is empty → zero mutation)
    assert cypher.count('e.episodes = $episodes') == 2
    assert "status = 'updated'" in cypher


def test_edge_identical_hash_noop_preserves_batch_id():
    store = CatalogNeo4jStore()
    cypher = store.build_edge_upsert_cypher()
    assert 'CASE' in cypher.upper()
    # identity/endpoint fields not rewritten on content change
    assert 'e.name = CASE' not in cypher
    assert 'e.edge_key = CASE' not in cypher
    assert 'e.source_node_uuid = CASE' not in cypher
    assert 'e.target_node_uuid = CASE' not in cypher
    assert 'e.group_id = CASE' not in cypher
    assert 'REMOVE e._catalog_create_token' in cypher
    assert 'ON MATCH SET' not in cypher


def test_edge_upsert_cypher_scopes_endpoint_group_id():
    store = CatalogNeo4jStore()
    cypher = store.build_edge_upsert_cypher()
    assert 'MATCH (source:Entity {uuid: $source_uuid, group_id: $group_id})' in cypher
    assert 'MATCH (target:Entity {uuid: $target_uuid, group_id: $group_id})' in cypher
    assert 'MERGE (source)-[e:RELATES_TO {uuid: $uuid, group_id: $group_id}]->(target)' in cypher


@pytest.mark.asyncio
async def test_read_one_uses_params_kwarg_not_splat():
    """Neo4jDriver.execute_query binds Cypher values only via params=."""
    store = CatalogNeo4jStore()
    calls: list[tuple] = []

    class _Exec:
        async def execute_query(self, cypher, **kwargs):
            calls.append((cypher, kwargs))
            return ([{'uuid': 'u1'}], None, ['uuid'])

    row = await store._read_one(_Exec(), 'RETURN 1', {'group_id': GROUP, 'uuid': 'u1'}, tx=None)
    assert row == {'uuid': 'u1'}
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert 'params' in kwargs
    assert kwargs['params'] == {'group_id': GROUP, 'uuid': 'u1'}
    assert 'group_id' not in kwargs
    assert 'uuid' not in kwargs


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
    assert isinstance(params.get('create_token'), str)
    assert len(params['create_token']) >= 16
    assert params.get('episodes') == []


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


def test_verify_edge_queries_return_physical_identity_and_provenance_is_group_scoped():
    store = CatalogNeo4jStore()
    for cypher in (
        store.build_match_edges_for_verify_by_batch_cypher(),
        store.build_match_edges_for_verify_by_keys_cypher(),
    ):
        assert 'elementId(e) AS element_id' in cypher
    provenance = store.build_match_provenance_presence_cypher()
    assert 'ep.group_id = $group_id' in provenance
    assert 'n.group_id = $group_id' in provenance


@pytest.mark.asyncio
async def test_verify_edge_overlap_dedup_uses_element_id_and_preserves_twins():
    store = CatalogNeo4jStore()

    class _Exec:
        async def execute_query(self, cypher: str, params=None, **kwargs):
            _ = params, kwargs
            rows = [
                {'element_id': 'rel-1', 'uuid': 'same', 'edge_key': 'EDGE::K'},
                {'element_id': 'rel-2', 'uuid': 'same', 'edge_key': 'EDGE::K'},
            ]
            if '$batch_id' in cypher:
                return (rows, None, [])
            return ([rows[0]], None, [])

    rows = await store.match_edges_for_verify(
        _Exec(), group_id=GROUP, batch_id=BATCH, edge_keys=['EDGE::K']
    )
    assert [row['element_id'] for row in rows] == ['rel-1', 'rel-2']


def test_identity_uniqueness_constraint_statements_are_fixed_create_only():
    stmts = CatalogNeo4jStore.identity_uniqueness_constraint_statements()
    assert len(stmts) == 2
    entity_stmt, rel_stmt = stmts
    assert CATALOG_ENTITY_IDENTITY_CONSTRAINT in entity_stmt
    assert CATALOG_RELATES_TO_IDENTITY_CONSTRAINT in rel_stmt
    assert 'CREATE CONSTRAINT' in entity_stmt
    assert 'CREATE CONSTRAINT' in rel_stmt
    assert 'IF NOT EXISTS' in entity_stmt
    assert 'IF NOT EXISTS' in rel_stmt
    assert '(n.uuid, n.group_id)' in entity_stmt
    assert '(e.uuid, e.group_id)' in rel_stmt
    for stmt in stmts:
        assert 'DROP' not in stmt.upper()
        assert 'DELETE' not in stmt.upper()


def _valid_catalog_constraint_rows() -> list[dict]:
    return [
        {
            'name': CATALOG_ENTITY_IDENTITY_CONSTRAINT,
            'type': 'NODE_PROPERTY_UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['Entity'],
            'properties': ['uuid', 'group_id'],
        },
        {
            'name': CATALOG_RELATES_TO_IDENTITY_CONSTRAINT,
            'type': 'RELATIONSHIP_PROPERTY_UNIQUENESS',
            'entityType': 'RELATIONSHIP',
            'labelsOrTypes': ['RELATES_TO'],
            'properties': ['uuid', 'group_id'],
        },
    ]


@pytest.mark.asyncio
async def test_ensure_uuid_uniqueness_constraints_idempotent_and_no_drop():
    """Product init issues CREATE IF NOT EXISTS only; second call is no-op."""
    store = CatalogNeo4jStore()
    calls: list[str] = []
    created = {'n': 0}

    class _Exec:
        async def execute_query(self, cypher: str, params=None, **kwargs):
            _ = (0 if params is None else 1) + len(kwargs)
            calls.append(cypher.strip())
            if 'SHOW CONSTRAINTS' in cypher:
                # Empty until both CREATE attempts complete; final SHOW verifies shape.
                if created['n'] < 2:
                    return ([], None, [])
                return (_valid_catalog_constraint_rows(), None, [])
            if 'CREATE CONSTRAINT' in cypher:
                created['n'] += 1
            return ([], None, [])

    exec1 = _Exec()
    await store.ensure_uuid_uniqueness_constraints(exec1)
    assert store._schema_ready is True
    assert any('CREATE CONSTRAINT' in c for c in calls)
    assert all('DROP' not in c.upper() for c in calls)
    create_count = sum(1 for c in calls if 'CREATE CONSTRAINT' in c)
    assert create_count == 2
    # Final SHOW after CREATE must run (fail-closed verification).
    assert sum(1 for c in calls if 'SHOW CONSTRAINTS' in c) >= 2

    # Second call short-circuits (no more executor traffic)
    n_before = len(calls)
    await store.ensure_uuid_uniqueness_constraints(exec1)
    assert len(calls) == n_before


@pytest.mark.asyncio
async def test_ensure_schema_skips_create_when_constraints_present():
    store = CatalogNeo4jStore()
    calls: list[str] = []

    class _Exec:
        async def execute_query(self, cypher: str, params=None, **kwargs):
            _ = params, kwargs
            calls.append(cypher.strip())
            if 'SHOW CONSTRAINTS' in cypher:
                return (_valid_catalog_constraint_rows(), None, [])
            raise AssertionError(f'unexpected query: {cypher[:80]}')

    await store.ensure_uuid_uniqueness_constraints(_Exec())
    assert store._schema_ready is True
    assert all('CREATE CONSTRAINT' not in c for c in calls)
    assert all('DROP' not in c.upper() for c in calls)


@pytest.mark.asyncio
async def test_ensure_schema_rejects_same_name_wrong_shape():
    """Name-only match is not enough — wrong type/props fail closed."""
    store = CatalogNeo4jStore()

    class _Exec:
        async def execute_query(self, cypher: str, params=None, **kwargs):
            _ = params, kwargs
            if 'SHOW CONSTRAINTS' in cypher:
                return (
                    [
                        {
                            'name': CATALOG_ENTITY_IDENTITY_CONSTRAINT,
                            'type': 'RANGE',  # wrong
                            'entityType': 'NODE',
                            'labelsOrTypes': ['Entity'],
                            'properties': ['uuid'],  # missing group_id
                        },
                        {
                            'name': CATALOG_RELATES_TO_IDENTITY_CONSTRAINT,
                            'type': 'RELATIONSHIP_PROPERTY_UNIQUENESS',
                            'entityType': 'RELATIONSHIP',
                            'labelsOrTypes': ['RELATES_TO'],
                            'properties': ['uuid', 'group_id'],
                        },
                    ],
                    None,
                    [],
                )
            # CREATE succeeds but final SHOW still returns wrong shape
            return ([], None, [])

    with pytest.raises(CatalogStoreError) as ei:
        await store.ensure_uuid_uniqueness_constraints(_Exec())
    assert ei.value.code == 'neo4j_schema_failed'
    assert store._schema_ready is False


@pytest.mark.asyncio
async def test_ensure_schema_rejects_already_exists_without_verified_shape():
    """already-exists exceptions must not skip SHOW verification."""
    store = CatalogNeo4jStore()
    creates = {'n': 0}

    class _Boom(Exception):
        pass

    class _Exec:
        async def execute_query(self, cypher: str, params=None, **kwargs):
            _ = params, kwargs
            if 'SHOW CONSTRAINTS' in cypher:
                # Never present with correct shape
                return (
                    [
                        {
                            'name': CATALOG_ENTITY_IDENTITY_CONSTRAINT,
                            'type': 'UNIQUENESS',
                            'entityType': 'NODE',
                            'labelsOrTypes': ['Entity'],
                            'properties': ['uuid'],  # wrong props
                        }
                    ],
                    None,
                    [],
                )
            if 'CREATE CONSTRAINT' in cypher:
                creates['n'] += 1
                raise _Boom('ConstraintAlreadyExists: already exists')
            return ([], None, [])

    with pytest.raises(CatalogStoreError) as ei:
        await store.ensure_uuid_uniqueness_constraints(_Exec())
    assert ei.value.code == 'neo4j_schema_failed'
    assert creates['n'] == 2
    assert store._schema_ready is False
