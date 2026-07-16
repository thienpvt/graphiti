"""Unit tests for catalog config, allowlists, and request/response models."""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig, GraphitiConfig  # noqa: E402
from models.catalog_common import (  # noqa: E402
    CATALOG_EDGE_TYPES,
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    MAX_EVIDENCE_LENGTH,
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
)
from models.catalog_responses import (  # noqa: E402
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
    entities = [_entity_kwargs(graph_key=f'TABLE::T{i}') for i in range(HARD_MAX_ENTITIES_PER_BATCH + 1)]
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


def test_resolve_and_verify_response_models_construct():
    ResolveTypedEntitiesResponse(group_id='g', results=[])
    VerifyCatalogBatchResponse(group_id='g', batch_id='b', results=[])
