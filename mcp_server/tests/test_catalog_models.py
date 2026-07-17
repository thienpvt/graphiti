"""Unit tests for catalog config, allowlists, and request/response models."""

from __future__ import annotations

import math
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig, GraphitiConfig  # noqa: E402
from models.catalog_batch import (  # noqa: E402
    GetCatalogIngestStatusRequest,
    UpsertCatalogBatchRequest,
)
from models.catalog_common import (  # noqa: E402
    CATALOG_EDGE_TYPES,
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
    MAX_EVIDENCE_LENGTH,
    MAX_NESTED_DEPTH,
    MAX_NESTED_NODES,
    MAX_SHORT_STRING_LENGTH,
    PROTECTED_ENTITY_PROPERTIES,
    CatalogErrorCode,
)
from models.catalog_edges import CatalogEdgeItem, UpsertTypedEdgesRequest  # noqa: E402
from models.catalog_entities import (  # noqa: E402
    CatalogEntityItem,
    ResolveEntityRef,
    ResolveTypedEntitiesRequest,
    UpsertTypedEntitiesRequest,
    VerifyEdgeRef,
)
from models.catalog_provenance import (  # noqa: E402
    CatalogProvenanceEdgeTarget,
    CatalogProvenanceEntityTarget,
    CatalogSourceItem,
    UpsertProvenanceRequest,
)
from models.catalog_responses import (  # noqa: E402
    CatalogIngestStatusResponse,
    CatalogItemResult,
    CatalogWriteResponse,
    ResolveTypedEntitiesResponse,
    VerifyCatalogBatchResponse,
)

FIXED_NS = '6ba7b810-9dad-11d1-80b4-00c04fd430c8'


def _entity_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'ORCL.HR.EMPLOYEES',
        'summary': 'Employee master table',
    }
    base.update(overrides)
    return base


def _edge_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'edge_type': 'Contains',
        'edge_key': 'CONTAINS::SCHEMA::HR->TABLE::HR.EMPLOYEES',
        'source_graph_key': 'SCHEMA::HR',
        'source_entity_type': 'Schema',
        'target_graph_key': 'TABLE::HR.EMPLOYEES',
        'target_entity_type': 'Table',
        'fact': 'Schema HR contains table EMPLOYEES',
    }
    base.update(overrides)
    return base


def _entity(**overrides: Any) -> CatalogEntityItem:
    return CatalogEntityItem.model_validate(_entity_kwargs(**overrides))


def _edge(**overrides: Any) -> CatalogEdgeItem:
    return CatalogEdgeItem.model_validate(_edge_kwargs(**overrides))


# ---------------------------------------------------------------------------
# CatalogConfig / CONF-01..05
# ---------------------------------------------------------------------------


def test_catalog_config_enabled_defaults_false():
    cfg = CatalogConfig()
    assert cfg.enabled is False


def test_catalog_config_uuid_namespace_defaults_none():
    cfg = CatalogConfig()
    assert cfg.uuid_namespace is None


def test_catalog_config_no_uuid_factory_in_defaults():
    """CONF-03: namespace must not be auto-generated."""
    cfg = CatalogConfig()
    assert cfg.uuid_namespace is None
    for _ in range(3):
        assert CatalogConfig().uuid_namespace is None


def test_catalog_config_limits_defaults():
    cfg = CatalogConfig()
    assert cfg.max_entities_per_batch == 500
    assert cfg.max_edges_per_batch == 2000
    assert cfg.max_provenance_links_per_batch == 5000


def test_catalog_config_accepts_limits_above_defaults_within_hard_max():
    cfg = CatalogConfig(max_entities_per_batch=501, max_edges_per_batch=2001)
    assert cfg.max_entities_per_batch == 501
    assert cfg.max_edges_per_batch == 2001


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('max_entities_per_batch', HARD_MAX_ENTITIES_PER_BATCH + 1),
        ('max_edges_per_batch', HARD_MAX_EDGES_PER_BATCH + 1),
        ('max_provenance_links_per_batch', 20_001),
    ],
)
def test_catalog_config_rejects_limits_above_hard_max(field: str, value: int):
    with pytest.raises(ValidationError):
        CatalogConfig.model_validate({field: value})


def test_catalog_config_enabled_requires_valid_namespace():
    with pytest.raises(ValidationError) as exc:
        CatalogConfig(enabled=True, uuid_namespace=None)
    assert 'uuid_namespace' in str(exc.value).lower() or 'namespace' in str(exc.value).lower()


def test_catalog_config_enabled_rejects_invalid_namespace():
    with pytest.raises(ValidationError):
        CatalogConfig(enabled=True, uuid_namespace='not-a-uuid')


def test_catalog_config_enabled_accepts_valid_namespace():
    cfg = CatalogConfig(enabled=True, uuid_namespace=FIXED_NS)
    assert cfg.enabled is True
    assert cfg.uuid_namespace == FIXED_NS


def test_catalog_config_disabled_allows_missing_namespace():
    cfg = CatalogConfig(enabled=False, uuid_namespace=None)
    assert cfg.enabled is False


def test_catalog_config_docstring_mentions_neo4j_only():
    doc = (CatalogConfig.__doc__ or '').lower()
    assert 'neo4j' in doc


def test_graphiti_config_exposes_catalog_upsert():
    cfg = GraphitiConfig()
    assert hasattr(cfg, 'catalog_upsert')
    assert isinstance(cfg.catalog_upsert, CatalogConfig)
    assert cfg.catalog_upsert.enabled is False


def test_graphiti_catalog_uuid_namespace_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('GRAPHITI_CATALOG_UUID_NAMESPACE', FIXED_NS)
    cfg = CatalogConfig()
    assert cfg.uuid_namespace == FIXED_NS
    g = GraphitiConfig()
    assert g.catalog_upsert.uuid_namespace == FIXED_NS


def test_schema_source_has_no_uuid4_namespace_factory():
    schema_path = Path(__file__).parent.parent / 'src' / 'config' / 'schema.py'
    text = schema_path.read_text(encoding='utf-8')
    assert not re.search(
        r'uuid_namespace\s*[:=].*uuid\.(uuid4|uuid5|uuid1)\(',
        text,
    )
    assert 'default_factory=uuid' not in text


# ---------------------------------------------------------------------------
# Allowlists / CatalogErrorCode
# ---------------------------------------------------------------------------


def test_entity_type_prefixes_has_fifteen_types():
    assert len(ENTITY_TYPE_PREFIXES) == 15
    expected = {
        'Database': 'DATABASE::',
        'DictionaryDocument': 'DOC::',
        'Schema': 'SCHEMA::',
        'Table': 'TABLE::',
        'View': 'VIEW::',
        'MaterializedView': 'MVIEW::',
        'Column': 'COLUMN::',
        'Constraint': 'CONSTRAINT::',
        'Index': 'INDEX::',
        'Package': 'PACKAGE::',
        'Procedure': 'PROCEDURE::',
        'Function': 'FUNCTION::',
        'Trigger': 'TRIGGER::',
        'Sequence': 'SEQUENCE::',
        'Synonym': 'SYNONYM::',
    }
    assert expected == ENTITY_TYPE_PREFIXES


def test_catalog_edge_types_has_sixteen():
    assert len(CATALOG_EDGE_TYPES) == 16
    for name in (
        'Contains',
        'PrimaryKeyOf',
        'UniqueKeyOf',
        'ForeignKeyTo',
        'EnforcedBy',
        'TriggerOn',
        'SynonymFor',
        'DocumentedBy',
        'Calls',
        'ReadsFrom',
        'WritesTo',
        'JoinsWith',
        'ReferencesByCode',
        'DependsOn',
        'DerivedFrom',
        'UsesSequence',
    ):
        assert name in CATALOG_EDGE_TYPES


def test_protected_entity_properties():
    for key in (
        'uuid',
        'group_id',
        'labels',
        'graph_key',
        'name_embedding',
        'created_at',
        'updated_at',
        'content_sha256',
    ):
        assert key in PROTECTED_ENTITY_PROPERTIES


def test_catalog_error_code_includes_required_codes():
    required = {
        'validation_error',
        'feature_disabled',
        'invalid_uuid_namespace',
        'batch_limit_exceeded',
        'content_hash_mismatch',
        'entity_type_conflict',
        'graph_key_prefix_mismatch',
        'deterministic_uuid_conflict',
        'missing_endpoint',
        'endpoint_type_mismatch',
        'generic_endpoint_conflict',
        'edge_identity_conflict',
        'batch_conflict',
        'provenance_target_missing',
        'neo4j_transaction_failed',
        'embedding_failed',
        'internal_error',
    }
    values = {c.value for c in CatalogErrorCode}
    assert required.issubset(values)


# ---------------------------------------------------------------------------
# Entity request models
# ---------------------------------------------------------------------------


def test_upsert_entities_requires_group_id():
    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate({'entities': [_entity_kwargs()]})


def test_upsert_entities_rejects_empty_group_id():
    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate(
            {
                'group_id': '',
                'batch_id': 'batch-1',
                'entities': [_entity_kwargs()],
            }
        )


def test_upsert_entities_rejects_invalid_group_id():
    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate(
            {
                'group_id': 'bad group!',
                'batch_id': 'batch-1',
                'entities': [_entity_kwargs()],
            }
        )


def test_upsert_entities_accepts_valid_request():
    req = UpsertTypedEntitiesRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'entities': [_entity_kwargs()],
        }
    )
    assert req.group_id == 'oracle-catalog-tool-test'
    assert req.dry_run is False
    assert req.atomic is True
    assert 'excluded_entity_types' not in UpsertTypedEntitiesRequest.model_fields


def test_entity_item_rejects_unknown_type():
    with pytest.raises(ValidationError):
        _entity(entity_type='Widget')


def test_entity_item_rejects_wrong_prefix():
    with pytest.raises(ValidationError) as exc:
        _entity(graph_key='SCHEMA::HR.EMPLOYEES')
    msg = str(exc.value).lower()
    assert 'prefix' in msg or 'graph_key' in msg


def test_entity_item_rejects_protected_attribute_key():
    with pytest.raises(ValidationError):
        _entity(attributes={'uuid': 'caller-owned'})


def test_entity_item_rejects_non_finite_attribute():
    with pytest.raises(ValidationError):
        _entity(attributes={'score': math.nan})
    with pytest.raises(ValidationError):
        _entity(attributes={'score': math.inf})


def test_entity_item_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        _entity(confidence=1.5)
    with pytest.raises(ValidationError):
        _entity(confidence=-0.1)


def test_entity_item_accepts_boundary_confidence():
    item = _entity(confidence=0.0)
    assert item.confidence == 0.0
    item = _entity(confidence=1.0)
    assert item.confidence == 1.0


def test_entity_item_rejects_empty_strings():
    with pytest.raises(ValidationError):
        _entity(name_raw='')
    with pytest.raises(ValidationError):
        _entity(summary='')


def test_entity_item_rejects_invalid_content_sha256():
    with pytest.raises(ValidationError):
        _entity(content_sha256='deadbeef')
    with pytest.raises(ValidationError):
        _entity(content_sha256='G' * 64)


def test_entity_item_accepts_valid_content_sha256():
    digest = 'a' * 64
    item = _entity(content_sha256=digest)
    assert item.content_sha256 == digest


def test_entity_collection_above_default_constructs_within_hard_max():
    entities = [_entity_kwargs(graph_key=f'TABLE::T{i}') for i in range(501)]
    request = UpsertTypedEntitiesRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'entities': entities,
        }
    )
    assert len(request.entities) == 501


def test_entity_collection_above_hard_max_rejected():
    entities = [
        _entity_kwargs(graph_key=f'TABLE::T{i}') for i in range(HARD_MAX_ENTITIES_PER_BATCH + 1)
    ]
    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'entities': entities,
            }
        )


def test_entity_rejects_oversized_nested_attribute_string():
    with pytest.raises(ValidationError):
        _entity(attributes={'nested': [{'raw': 'x' * 1_000_000}]})


def test_entity_rejects_oversized_nested_source_ref_key_and_value():
    with pytest.raises(ValidationError):
        _entity(source_refs=[{'x' * (MAX_SHORT_STRING_LENGTH + 1): 'value'}])
    with pytest.raises(ValidationError):
        _entity(source_refs=[{'raw': 'x' * (MAX_EVIDENCE_LENGTH + 1)}])


@pytest.mark.parametrize(
    'value',
    [b'raw', {'set'}, object(), 1 + 2j, uuid.UUID(FIXED_NS)],
)
def test_entity_rejects_non_json_nested_values(value: object):
    with pytest.raises(ValidationError):
        _entity(attributes={'value': value})
    with pytest.raises(ValidationError):
        _entity(source_refs=[{'value': value}])


def test_entity_rejects_nested_cycles_depth_and_total_nodes():
    cycle: list[Any] = []
    cycle.append(cycle)
    with pytest.raises(ValidationError):
        _entity(attributes={'cycle': cycle})

    deep: list[Any] = []
    cursor = deep
    for _ in range(MAX_NESTED_DEPTH + 1):
        child: list[Any] = []
        cursor.append(child)
        cursor = child
    with pytest.raises(ValidationError):
        _entity(source_refs=deep)

    with pytest.raises(ValidationError):
        _entity(attributes={'wide': [None] * MAX_NESTED_NODES})


def test_resolve_typed_entities_requires_group_id():
    with pytest.raises(ValidationError):
        ResolveTypedEntitiesRequest.model_validate({'entities': []})


def test_resolve_accepts_valid():
    req = ResolveTypedEntitiesRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'entities': [
                {'entity_type': 'Table', 'graph_key': 'TABLE::HR.EMPLOYEES'},
            ],
        }
    )
    assert req.group_id == 'oracle-catalog-tool-test'
    assert isinstance(req.entities[0], ResolveEntityRef)


# ---------------------------------------------------------------------------
# Edge request models
# ---------------------------------------------------------------------------


def test_edge_item_rejects_unknown_type():
    with pytest.raises(ValidationError):
        _edge(edge_type='Owns')


def test_edge_enforced_by_requires_evidence():
    with pytest.raises(ValidationError):
        _edge(edge_type='EnforcedBy', evidence=None)
    with pytest.raises(ValidationError):
        _edge(edge_type='EnforcedBy', evidence='')
    item = _edge(
        edge_type='EnforcedBy',
        edge_key='ENFORCEDBY::CONSTRAINT::C1',
        evidence='ALTER TABLE ... CONSTRAINT C1',
    )
    assert item.evidence is not None
    assert item.evidence.startswith('ALTER')


def test_edge_rejects_invalid_endpoint_type():
    with pytest.raises(ValidationError):
        _edge(source_entity_type='Widget')


def test_edge_rejects_empty_fact():
    with pytest.raises(ValidationError):
        _edge(fact='')


def test_upsert_edges_accepts_valid_request():
    req = UpsertTypedEdgesRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'edges': [_edge_kwargs()],
        }
    )
    assert req.strict_endpoints is True
    assert req.atomic is True
    assert 'excluded_entity_types' not in UpsertTypedEdgesRequest.model_fields


def test_edge_collection_above_default_constructs_within_hard_max():
    edges = [_edge_kwargs(edge_key=f'CONTAINS::E{i}') for i in range(2001)]
    request = UpsertTypedEdgesRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'edges': edges,
        }
    )
    assert len(request.edges) == 2001


def test_edge_collection_above_hard_max_rejected():
    edges = [_edge_kwargs(edge_key=f'CONTAINS::E{i}') for i in range(HARD_MAX_EDGES_PER_BATCH + 1)]
    with pytest.raises(ValidationError):
        UpsertTypedEdgesRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'edges': edges,
            }
        )


def test_edge_rejects_oversized_nested_attribute_string():
    with pytest.raises(ValidationError):
        _edge(attributes={'nested': [{'raw': 'x' * 1_000_000}]})


@pytest.mark.parametrize('value', [b'raw', {'set'}, object(), 1 + 2j, uuid.UUID(FIXED_NS)])
def test_edge_rejects_non_json_nested_values(value: object):
    with pytest.raises(ValidationError):
        _edge(attributes={'value': value})


def test_edge_rejects_nested_cycle():
    cycle: dict[str, Any] = {}
    cycle['self'] = cycle
    with pytest.raises(ValidationError):
        _edge(attributes=cycle)


def test_edge_rejects_non_finite_attribute_and_bad_confidence():
    with pytest.raises(ValidationError):
        _edge(attributes={'w': math.inf})
    with pytest.raises(ValidationError):
        _edge(confidence=2.0)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


def test_catalog_item_result_states():
    for status in ('created', 'updated', 'unchanged', 'rolled_back'):
        r = CatalogItemResult(
            index=0,
            status=status,  # type: ignore[arg-type]
            uuid=FIXED_NS,
            content_sha256='b' * 64,
        )
        assert r.status == status


def test_catalog_item_result_error():
    r = CatalogItemResult(
        index=1,
        status='error',
        error_code=CatalogErrorCode.content_hash_mismatch,
        error_message='client hash mismatch',
    )
    assert r.error_code == CatalogErrorCode.content_hash_mismatch


def test_write_response_preserves_results():
    resp = CatalogWriteResponse(
        group_id='oracle-catalog-tool-test',
        batch_id='batch-1',
        results=[
            CatalogItemResult(
                index=0,
                status='created',
                uuid=FIXED_NS,
                content_sha256='c' * 64,
            ),
        ],
    )
    assert len(resp.results) == 1


def test_verify_edge_ref_is_backward_compatible_and_accepts_expected_endpoints():
    minimal = VerifyEdgeRef(edge_type='Contains', edge_key='CONTAINS::K')
    assert minimal.expected_source_graph_key is None
    ref = VerifyEdgeRef(
        edge_type='Contains',
        edge_key='CONTAINS::K',
        expected_source_graph_key='SCHEMA::HR',
        expected_target_graph_key='TABLE::HR.EMPLOYEES',
        expected_source_uuid=FIXED_NS,
        expected_target_uuid=FIXED_NS,
    )
    assert ref.expected_source_graph_key == 'SCHEMA::HR'
    uppercase = FIXED_NS.upper()
    assert (
        VerifyEdgeRef(
            edge_type='Contains', edge_key='CONTAINS::K', expected_source_uuid=uppercase
        ).expected_source_uuid
        == FIXED_NS
    )


@pytest.mark.parametrize('field', ['expected_source_uuid', 'expected_target_uuid'])
def test_verify_edge_ref_rejects_invalid_expected_uuid(field: str):
    with pytest.raises(ValidationError):
        VerifyEdgeRef.model_validate(
            {'edge_type': 'Contains', 'edge_key': 'CONTAINS::K', field: 'not-a-uuid'}
        )


def test_resolve_and_verify_response_models_construct():
    ResolveTypedEntitiesResponse(group_id='g', results=[])
    VerifyCatalogBatchResponse(group_id='g', batch_id='b', results=[])


# ---------------------------------------------------------------------------
# Provenance models (PROV-02)
# ---------------------------------------------------------------------------


def _source_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'source_key': 'DOC::HR.PDF#p12',
        'reference_time': '2024-01-15T10:30:00+00:00',
        'attributes': {'page': 12, 'title': 'HR schema'},
    }
    base.update(overrides)
    return base


def _entity_target(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::HR.EMPLOYEES',
    }
    base.update(overrides)
    return base


def _edge_target(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'edge_type': 'Contains',
        'edge_key': 'CONTAINS::SCHEMA::HR->TABLE::HR.EMPLOYEES',
    }
    base.update(overrides)
    return base


def test_catalog_source_item_requires_source_key_and_reference_time():
    with pytest.raises(ValidationError):
        CatalogSourceItem.model_validate({'reference_time': '2024-01-15T10:30:00+00:00'})
    with pytest.raises(ValidationError):
        CatalogSourceItem.model_validate({'source_key': 'DOC::A'})


def test_catalog_source_item_preserves_exact_reference_time():
    raw = '2024-01-15T10:30:00.123456+00:00'
    item = CatalogSourceItem.model_validate(_source_kwargs(reference_time=raw))
    assert item.reference_time == raw


def test_catalog_source_item_rejects_protected_keys_and_bad_hash():
    with pytest.raises(ValidationError):
        CatalogSourceItem.model_validate(_source_kwargs(attributes={'uuid': 'x'}))
    with pytest.raises(ValidationError):
        CatalogSourceItem.model_validate(_source_kwargs(content_sha256='deadbeef'))
    digest = 'a' * 64
    item = CatalogSourceItem.model_validate(_source_kwargs(content_sha256=digest))
    assert item.content_sha256 == digest


def test_catalog_source_item_rejects_non_finite_nested():
    with pytest.raises(ValidationError):
        CatalogSourceItem.model_validate(_source_kwargs(attributes={'score': math.nan}))
    with pytest.raises(ValidationError):
        CatalogSourceItem.model_validate(_source_kwargs(attributes={'score': math.inf}))


def test_provenance_entity_target_allowlist_and_prefix():
    CatalogProvenanceEntityTarget.model_validate(_entity_target())
    with pytest.raises(ValidationError):
        CatalogProvenanceEntityTarget.model_validate(_entity_target(entity_type='Widget'))
    with pytest.raises(ValidationError):
        CatalogProvenanceEntityTarget.model_validate(
            _entity_target(graph_key='SCHEMA::HR.EMPLOYEES')
        )


def test_provenance_edge_target_allowlist():
    CatalogProvenanceEdgeTarget.model_validate(_edge_target())
    with pytest.raises(ValidationError):
        CatalogProvenanceEdgeTarget.model_validate(_edge_target(edge_type='Owns'))


def test_upsert_provenance_request_accepts_valid():
    req = UpsertProvenanceRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'sources': [_source_kwargs()],
            'entity_targets': [_entity_target()],
            'edge_targets': [_edge_target()],
        }
    )
    assert req.dry_run is False
    assert req.atomic is True
    assert len(req.sources) == 1


def test_upsert_provenance_requires_group_batch_and_sources():
    with pytest.raises(ValidationError):
        UpsertProvenanceRequest.model_validate(
            {
                'batch_id': 'batch-1',
                'sources': [_source_kwargs()],
            }
        )
    with pytest.raises(ValidationError):
        UpsertProvenanceRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'sources': [_source_kwargs()],
            }
        )
    with pytest.raises(ValidationError):
        UpsertProvenanceRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'sources': [],
            }
        )


def test_upsert_provenance_rejects_invalid_group_id():
    with pytest.raises(ValidationError):
        UpsertProvenanceRequest.model_validate(
            {
                'group_id': 'bad group!',
                'batch_id': 'batch-1',
                'sources': [_source_kwargs()],
            }
        )


def test_upsert_provenance_rejects_oversize_links():
    targets = [
        _entity_target(graph_key=f'TABLE::T{i}')
        for i in range(HARD_MAX_PROVENANCE_LINKS_PER_BATCH + 1)
    ]
    with pytest.raises(ValidationError):
        UpsertProvenanceRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'sources': [_source_kwargs()],
                'entity_targets': targets,
            }
        )


def test_upsert_provenance_rejects_generated_link_product_over_hard_max():
    with pytest.raises(ValidationError):
        UpsertProvenanceRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'sources': [
                    _source_kwargs(source_key=f'DOC::SRC::{i}') for i in range(201)
                ],
                'entity_targets': [
                    _entity_target(graph_key=f'TABLE::T{i}') for i in range(100)
                ],
            }
        )


# ---------------------------------------------------------------------------
# Nested atomic batch (BATC-01 / BATC-02)
# ---------------------------------------------------------------------------


def test_upsert_catalog_batch_accepts_nested_entities():
    req = UpsertCatalogBatchRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'entities': [_entity_kwargs()],
            'edges': [],
            'provenance': None,
        }
    )
    assert req.atomic is True
    assert req.dry_run is False
    assert len(req.entities) == 1
    # Nested list order preserved
    req2 = UpsertCatalogBatchRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'entities': [
                _entity_kwargs(graph_key='TABLE::A', name_raw='A', name_canonical='a'),
                _entity_kwargs(graph_key='TABLE::B', name_raw='B', name_canonical='b'),
            ],
        }
    )
    assert [e.graph_key for e in req2.entities] == ['TABLE::A', 'TABLE::B']


def test_upsert_catalog_batch_rejects_atomic_false():
    with pytest.raises(ValidationError) as exc:
        UpsertCatalogBatchRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'entities': [_entity_kwargs()],
                'atomic': False,
            }
        )
    msg = str(exc.value).lower()
    assert 'atomic' in msg or 'validation' in msg


def test_upsert_catalog_batch_rejects_empty_all_collections():
    with pytest.raises(ValidationError):
        UpsertCatalogBatchRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'entities': [],
                'edges': [],
                'provenance': None,
            }
        )


def test_upsert_catalog_batch_accepts_provenance_only():
    req = UpsertCatalogBatchRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'entities': [],
            'edges': [],
            'provenance': {
                'sources': [_source_kwargs()],
                'entity_targets': [_entity_target()],
            },
        }
    )
    assert req.provenance is not None
    assert len(req.provenance.sources) == 1


def test_nested_batch_rejects_generated_link_product_over_hard_max():
    with pytest.raises(ValidationError):
        UpsertCatalogBatchRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'entities': [],
                'provenance': {
                    'sources': [
                        _source_kwargs(source_key=f'DOC::SRC::{i}') for i in range(201)
                    ],
                    'entity_targets': [
                        _entity_target(graph_key=f'TABLE::T{i}') for i in range(100)
                    ],
                },
            }
        )


def test_upsert_catalog_batch_optional_hashes():
    digest = 'b' * 64
    req = UpsertCatalogBatchRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'entities': [_entity_kwargs()],
            'request_sha256': digest,
            'catalog_sha256': digest,
        }
    )
    assert req.request_sha256 == digest
    with pytest.raises(ValidationError):
        UpsertCatalogBatchRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'batch-1',
                'entities': [_entity_kwargs()],
                'request_sha256': 'not-hex',
            }
        )


def test_upsert_catalog_batch_requires_group_and_batch():
    with pytest.raises(ValidationError):
        UpsertCatalogBatchRequest.model_validate(
            {
                'batch_id': 'batch-1',
                'entities': [_entity_kwargs()],
            }
        )
    with pytest.raises(ValidationError):
        UpsertCatalogBatchRequest.model_validate(
            {
                'group_id': 'oracle-catalog-tool-test',
                'entities': [_entity_kwargs()],
            }
        )


def test_get_catalog_ingest_status_request_group_and_batch_only():
    req = GetCatalogIngestStatusRequest.model_validate(
        {
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
        }
    )
    assert req.group_id == 'oracle-catalog-tool-test'
    assert req.batch_id == 'batch-1'
    assert set(GetCatalogIngestStatusRequest.model_fields.keys()) == {
        'group_id',
        'batch_id',
    }
    with pytest.raises(ValidationError):
        GetCatalogIngestStatusRequest.model_validate({'group_id': 'g'})


# ---------------------------------------------------------------------------
# Ingest status response (STAT-02 / STAT-03)
# ---------------------------------------------------------------------------


def test_catalog_ingest_status_response_six_literals():
    allowed = {
        'planned',
        'validating',
        'embedding',
        'writing',
        'committed',
        'failed',
    }
    for status in allowed:
        r = CatalogIngestStatusResponse(
            group_id='oracle-catalog-tool-test',
            batch_id='batch-1',
            batch_uuid=FIXED_NS,
            status=status,  # type: ignore[arg-type]
        )
        assert r.status == status
    with pytest.raises(ValidationError):
        CatalogIngestStatusResponse(
            group_id='g',
            batch_id='b',
            batch_uuid=FIXED_NS,
            status='running',  # type: ignore[arg-type]
        )


def test_catalog_ingest_status_response_no_payload_or_secret_fields():
    fields = set(CatalogIngestStatusResponse.model_fields.keys())
    forbidden = {
        'payload',
        'request',
        'entities',
        'edges',
        'provenance',
        'sources',
        'password',
        'secret',
        'api_key',
        'credentials',
        'raw_document',
        'content',
    }
    assert fields.isdisjoint(forbidden)
    r = CatalogIngestStatusResponse(
        group_id='oracle-catalog-tool-test',
        batch_id='batch-1',
        batch_uuid=FIXED_NS,
        status='committed',
        request_sha256='c' * 64,
        catalog_sha256=None,
        entity_count=1,
        edge_count=0,
        provenance_count=0,
        error_summary='',
    )
    assert r.error_summary == ''
    assert r.entity_count == 1


def test_catalog_ingest_status_response_rejects_oversize_error_summary():
    with pytest.raises(ValidationError):
        CatalogIngestStatusResponse(
            group_id='g',
            batch_id='b',
            batch_uuid=FIXED_NS,
            status='failed',
            error_summary='x' * (MAX_SHORT_STRING_LENGTH + 1),
        )


def test_catalog_ingest_status_missing_required_fields():
    with pytest.raises(ValidationError):
        CatalogIngestStatusResponse.model_validate(
            {'group_id': 'g', 'batch_id': 'b', 'status': 'committed'}
        )
