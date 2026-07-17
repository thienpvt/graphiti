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
    VerifyCatalogBatchRequest,
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
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
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
        'edge_key': 'CONTAINS::SCHEMA::FE::ORCL.HR->TABLE::FE::ORCL.HR.EMPLOYEES',
        'source_graph_key': 'SCHEMA::FE::ORCL.HR',
        'source_entity_type': 'Schema',
        'target_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
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


def test_entity_type_prefixes_has_eighteen_types():
    assert len(ENTITY_TYPE_PREFIXES) == 18
    expected = {
        'System': 'SYSTEM::',
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
        'DatabaseLink': 'DBLINK::',
        'SourceArtifact': 'SOURCE::',
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


@pytest.mark.parametrize(
    ('model', 'payload_factory'),
    [
        (
            UpsertTypedEntitiesRequest,
            lambda: {'batch_id': 'batch-1', 'entities': [_entity_kwargs()]},
        ),
        (
            ResolveTypedEntitiesRequest,
            lambda: {
                'entities': [
                    {'entity_type': 'Table', 'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES'}
                ]
            },
        ),
        (VerifyCatalogBatchRequest, lambda: {'batch_id': 'batch-1'}),
        (
            UpsertTypedEdgesRequest,
            lambda: {'batch_id': 'batch-1', 'edges': [_edge_kwargs()]},
        ),
        (
            UpsertProvenanceRequest,
            lambda: {'batch_id': 'batch-1', 'sources': [_source_kwargs()]},
        ),
        (
            UpsertCatalogBatchRequest,
            lambda: {'batch_id': 'batch-1', 'entities': [_entity_kwargs()]},
        ),
        (GetCatalogIngestStatusRequest, lambda: {'batch_id': 'batch-1'}),
    ],
)
def test_phase2_requests_reject_group_id_trailing_newline(model, payload_factory):
    with pytest.raises(ValidationError):
        model.model_validate({'group_id': 'oracle-catalog-tool-test\n', **payload_factory()})


def test_upsert_entities_accepts_valid_request():
    req = UpsertTypedEntitiesRequest.model_validate(
        {
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
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
        _entity(graph_key='SCHEMA::FE::ORCL.HR.EMPLOYEES')
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
    entities = [
        _entity_kwargs(graph_key=f'TABLE::FE::ORCL.HR.T{i}', name_raw=f'T{i}', name_canonical=f't{i}')
        for i in range(501)
    ]
    request = UpsertTypedEntitiesRequest.model_validate(
        {
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'entities': entities,
        }
    )
    assert len(request.entities) == 501


def test_entity_collection_above_hard_max_rejected():
    entities = [
        _entity_kwargs(graph_key=f'TABLE::FE::ORCL.HR.T{i}', name_raw=f'T{i}', name_canonical=f't{i}')
        for i in range(HARD_MAX_ENTITIES_PER_BATCH + 1)
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
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
            'group_id': 'oracle-catalog-tool-test',
            'entities': [
                {'entity_type': 'Table', 'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES'},
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
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
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
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
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
        expected_source_graph_key='SCHEMA::FE::ORCL.HR',
        expected_target_graph_key='TABLE::FE::ORCL.HR.EMPLOYEES',
        expected_source_uuid=FIXED_NS,
        expected_target_uuid=FIXED_NS,
    )
    assert ref.expected_source_graph_key == 'SCHEMA::FE::ORCL.HR'
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
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
    }
    base.update(overrides)
    return base


def _edge_target(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'edge_type': 'Contains',
        'edge_key': 'CONTAINS::SCHEMA::FE::ORCL.HR->TABLE::FE::ORCL.HR.EMPLOYEES',
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
            _entity_target(graph_key='SCHEMA::FE::ORCL.HR.EMPLOYEES')
        )


def test_provenance_edge_target_allowlist():
    CatalogProvenanceEdgeTarget.model_validate(_edge_target())
    with pytest.raises(ValidationError):
        CatalogProvenanceEdgeTarget.model_validate(_edge_target(edge_type='Owns'))


def test_upsert_provenance_request_accepts_valid():
    req = UpsertProvenanceRequest.model_validate(
        {
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
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
        _entity_target(graph_key=f'TABLE::FE::ORCL.HR.T{i}')
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
                'sources': [_source_kwargs(source_key=f'DOC::SRC::{i}') for i in range(201)],
                'entity_targets': [
                    _entity_target(graph_key=f'TABLE::FE::ORCL.HR.T{i}') for i in range(100)
                ],
            }
        )


# ---------------------------------------------------------------------------
# Nested atomic batch (BATC-01 / BATC-02)
# ---------------------------------------------------------------------------


def test_upsert_catalog_batch_accepts_nested_entities():
    req = UpsertCatalogBatchRequest.model_validate(
        {
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
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
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
            'group_id': 'oracle-catalog-tool-test',
            'batch_id': 'batch-1',
            'entities': [
                _entity_kwargs(graph_key='TABLE::FE::ORCL.HR.A', name_raw='A', name_canonical='a'),
                _entity_kwargs(graph_key='TABLE::FE::ORCL.HR.B', name_raw='B', name_canonical='b'),
            ],
        }
    )
    assert [e.graph_key for e in req2.entities] == [
        'TABLE::FE::ORCL.HR.A',
        'TABLE::FE::ORCL.HR.B',
    ]


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
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
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
                    'sources': [_source_kwargs(source_key=f'DOC::SRC::{i}') for i in range(201)],
                    'entity_targets': [
                        _entity_target(graph_key=f'TABLE::FE::ORCL.HR.T{i}') for i in range(100)
                    ],
                },
            }
        )


def test_upsert_catalog_batch_optional_hashes():
    digest = 'b' * 64
    req = UpsertCatalogBatchRequest.model_validate(
        {
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
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


# ---------------------------------------------------------------------------
# Catalog-v2 strict contracts (CONT-01..06, CONT-08, IDEN-01/02, TEST-01)
# ---------------------------------------------------------------------------

_PHASE1_ERROR_CODES = (
    'unsupported_identity_schema',
    'invalid_system_key',
    'edge_endpoint_pair_not_allowed',
    'prepared_plan_not_found',
    'prepared_plan_expired',
    'prepared_plan_conflict',
    'prepared_plan_already_consumed',
    'manifest_mismatch',
    'provenance_link_conflict',
)

_PREEXISTING_ERROR_CODES = (
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
    'backend_unavailable',
)


def _v2_shell(**overrides: Any) -> dict[str, Any]:
    """Domain shell fields required by catalog-v2 request contracts."""
    base: dict[str, Any] = {
        'group_id': 'oracle-catalog-tool-test',
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
    }
    base.update(overrides)
    return base


def _loc_paths(exc: ValidationError) -> list[tuple[Any, ...]]:
    return [tuple(err['loc']) for err in exc.errors()]


@pytest.mark.parametrize(
    ('model', 'payload', 'expected_loc_fragment'),
    [
        (
            UpsertTypedEntitiesRequest,
            {
                **_v2_shell(batch_id='batch-1', entities=[_entity_kwargs()]),
                'unknown_shell_field': True,
            },
            ('unknown_shell_field',),
        ),
        (
            UpsertTypedEntitiesRequest,
            {
                **_v2_shell(
                    batch_id='batch-1',
                    entities=[{**_entity_kwargs(), 'typo_nested': 1}],
                ),
            },
            ('entities', 0, 'typo_nested'),
        ),
        (
            UpsertTypedEdgesRequest,
            {
                **_v2_shell(batch_id='batch-1', edges=[_edge_kwargs()]),
                'rogue': 'x',
            },
            ('rogue',),
        ),
        (
            UpsertTypedEdgesRequest,
            {
                **_v2_shell(
                    batch_id='batch-1',
                    edges=[{**_edge_kwargs(), 'extra_edge_field': 'nope'}],
                ),
            },
            ('edges', 0, 'extra_edge_field'),
        ),
        (
            UpsertProvenanceRequest,
            {
                **_v2_shell(batch_id='batch-1', sources=[_source_kwargs()]),
                'unexpected': 1,
            },
            ('unexpected',),
        ),
        (
            UpsertProvenanceRequest,
            {
                **_v2_shell(
                    batch_id='batch-1',
                    sources=[{**_source_kwargs(), 'leak_field': 'secret'}],
                ),
            },
            ('sources', 0, 'leak_field'),
        ),
        (
            UpsertCatalogBatchRequest,
            {
                **_v2_shell(batch_id='batch-1', entities=[_entity_kwargs()]),
                'not_a_field': True,
            },
            ('not_a_field',),
        ),
        (
            UpsertCatalogBatchRequest,
            {
                **_v2_shell(
                    batch_id='batch-1',
                    entities=[],
                    edges=[],
                    provenance={
                        'sources': [_source_kwargs()],
                        'entity_targets': [],
                        'edge_targets': [],
                        'nested_unknown': True,
                    },
                ),
            },
            ('provenance', 'nested_unknown'),
        ),
        (
            ResolveTypedEntitiesRequest,
            {
                **_v2_shell(
                    entities=[
                        {
                            'entity_type': 'Table',
                            'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                        }
                    ],
                ),
                'extra_resolve': 1,
            },
            ('extra_resolve',),
        ),
        (
            VerifyCatalogBatchRequest,
            {
                **_v2_shell(batch_id='batch-1'),
                'verify_extra': False,
            },
            ('verify_extra',),
        ),
        (
            CatalogEntityItem,
            {**_entity_kwargs(), 'sneaky': 1},
            ('sneaky',),
        ),
        (
            CatalogEdgeItem,
            {**_edge_kwargs(), 'sneaky': 1},
            ('sneaky',),
        ),
        (
            CatalogSourceItem,
            {**_source_kwargs(), 'sneaky': 1},
            ('sneaky',),
        ),
        (
            ResolveEntityRef,
            {
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'sneaky': 1,
            },
            ('sneaky',),
        ),
        (
            CatalogProvenanceEntityTarget,
            {**_entity_target(), 'sneaky': 1},
            ('sneaky',),
        ),
        (
            CatalogProvenanceEdgeTarget,
            {**_edge_target(), 'sneaky': 1},
            ('sneaky',),
        ),
    ],
)
def test_catalog_strict_model_rejects_unknown_shell_and_nested_fields(
    model, payload, expected_loc_fragment
):
    with pytest.raises(ValidationError) as exc:
        model.model_validate(payload)
    locs = _loc_paths(exc.value)
    assert any(
        loc[-len(expected_loc_fragment) :] == expected_loc_fragment for loc in locs
    ), f'expected loc fragment {expected_loc_fragment!r} in {locs!r}'


def test_misspelled_optional_fields_rejected():
    with pytest.raises(ValidationError) as exc:
        UpsertTypedEntitiesRequest.model_validate(
            {
                **_v2_shell(batch_id='batch-1', entities=[_entity_kwargs()]),
                'dry_rn': True,  # misspelled dry_run
            }
        )
    locs = _loc_paths(exc.value)
    assert any(loc[-1] == 'dry_rn' for loc in locs)

    with pytest.raises(ValidationError) as exc:
        UpsertTypedEdgesRequest.model_validate(
            {
                **_v2_shell(batch_id='batch-1', edges=[_edge_kwargs()]),
                'strict_endponts': False,  # misspelled strict_endpoints
            }
        )
    locs = _loc_paths(exc.value)
    assert any(loc[-1] == 'strict_endponts' for loc in locs)


def test_strict_endpoints_false_rejected():
    with pytest.raises(ValidationError) as exc:
        UpsertTypedEdgesRequest.model_validate(
            {
                **_v2_shell(batch_id='batch-1', edges=[_edge_kwargs()]),
                'strict_endpoints': False,
            }
        )
    msg = str(exc.value).lower()
    assert 'strict_endpoints' in msg


@pytest.mark.parametrize(
    ('model', 'payload'),
    [
        (
            UpsertTypedEntitiesRequest,
            {**_v2_shell(batch_id='batch-1', entities=[_entity_kwargs()]), 'atomic': False},
        ),
        (
            UpsertTypedEdgesRequest,
            {**_v2_shell(batch_id='batch-1', edges=[_edge_kwargs()]), 'atomic': False},
        ),
        (
            UpsertProvenanceRequest,
            {**_v2_shell(batch_id='batch-1', sources=[_source_kwargs()]), 'atomic': False},
        ),
        (
            UpsertCatalogBatchRequest,
            {**_v2_shell(batch_id='batch-1', entities=[_entity_kwargs()]), 'atomic': False},
        ),
    ],
)
def test_atomic_false_rejected_on_entity_edge_provenance_batch_writes(model, payload):
    with pytest.raises(ValidationError) as exc:
        model.model_validate(payload)
    msg = str(exc.value).lower()
    assert 'atomic' in msg


@pytest.mark.parametrize(
    'model_payload',
    [
        (
            UpsertTypedEntitiesRequest,
            lambda: {'group_id': 'oracle-catalog-tool-test', 'batch_id': 'b', 'entities': [_entity_kwargs()]},
        ),
        (
            ResolveTypedEntitiesRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'entities': [
                    {
                        'entity_type': 'Table',
                        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                    }
                ],
            },
        ),
        (
            VerifyCatalogBatchRequest,
            lambda: {'group_id': 'oracle-catalog-tool-test', 'batch_id': 'b'},
        ),
        (
            UpsertTypedEdgesRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'b',
                'edges': [_edge_kwargs()],
            },
        ),
        (
            UpsertProvenanceRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'b',
                'sources': [_source_kwargs()],
            },
        ),
        (
            UpsertCatalogBatchRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'b',
                'entities': [_entity_kwargs()],
            },
        ),
    ],
)
def test_identity_schema_version_required_and_rejects_non_v2(model_payload):
    model, payload_factory = model_payload
    base = payload_factory()

    with pytest.raises(ValidationError) as exc:
        model.model_validate({**base, 'system_key': 'FE'})
    assert any(
        'identity_schema_version' in (err.get('loc') or ()) for err in exc.value.errors()
    ) or any('identity_schema_version' in str(err.get('loc')) for err in exc.value.errors())

    with pytest.raises(ValidationError) as exc:
        model.model_validate(
            {**base, 'identity_schema_version': 'catalog-v1', 'system_key': 'FE'}
        )
    msg = str(exc.value).lower()
    assert 'identity_schema_version' in msg or 'catalog-v' in msg

    with pytest.raises(ValidationError):
        model.model_validate({**base, 'identity_schema_version': '', 'system_key': 'FE'})

    with pytest.raises(ValidationError):
        model.model_validate({**base, 'identity_schema_version': None, 'system_key': 'FE'})

    ok = model.model_validate(
        {**base, 'identity_schema_version': 'catalog-v2', 'system_key': 'FE'}
    )
    assert ok.identity_schema_version == 'catalog-v2'


def _retarget_graph_keys_for_system(payload: dict[str, Any], system_key: str) -> dict[str, Any]:
    """Rewrite nested FE graph keys so shell system_key matches (test helper only)."""

    def rewrite(value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, child in value.items():
                if key in {
                    'graph_key',
                    'source_graph_key',
                    'target_graph_key',
                    'expected_source_graph_key',
                    'expected_target_graph_key',
                } and isinstance(child, str):
                    out[key] = child.replace('::FE::', f'::{system_key}::', 1)
                else:
                    out[key] = rewrite(child)
            return out
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        return value

    return rewrite(payload)


@pytest.mark.parametrize(
    'model_payload',
    [
        (
            UpsertTypedEntitiesRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'b',
                'entities': [_entity_kwargs()],
                'identity_schema_version': 'catalog-v2',
            },
        ),
        (
            ResolveTypedEntitiesRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'entities': [
                    {
                        'entity_type': 'Table',
                        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                    }
                ],
                'identity_schema_version': 'catalog-v2',
            },
        ),
        (
            VerifyCatalogBatchRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'b',
                'identity_schema_version': 'catalog-v2',
            },
        ),
        (
            UpsertTypedEdgesRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'b',
                'edges': [_edge_kwargs()],
                'identity_schema_version': 'catalog-v2',
            },
        ),
        (
            UpsertProvenanceRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'b',
                'sources': [_source_kwargs()],
                'identity_schema_version': 'catalog-v2',
            },
        ),
        (
            UpsertCatalogBatchRequest,
            lambda: {
                'group_id': 'oracle-catalog-tool-test',
                'batch_id': 'b',
                'entities': [_entity_kwargs()],
                'identity_schema_version': 'catalog-v2',
            },
        ),
    ],
)
def test_system_key_required_closed_set(model_payload):
    model, payload_factory = model_payload
    base = payload_factory()

    with pytest.raises(ValidationError) as exc:
        model.model_validate(base)
    assert any('system_key' in str(err.get('loc')) for err in exc.value.errors())

    for bad in ('', None, 'fe', 'COMMONN', 'be', 'frontend'):
        with pytest.raises(ValidationError):
            model.model_validate({**base, 'system_key': bad})

    for good in ('FE', 'BO', 'COMMON'):
        req = model.model_validate(
            _retarget_graph_keys_for_system({**base, 'system_key': good}, good)
        )
        assert req.system_key == good


def test_source_and_reference_time_preserve_trailing_space():
    source_key = 'DOC::HR.PDF#p12 '
    reference_time = '2024-01-15T10:30:00+00:00 '
    item = CatalogSourceItem.model_validate(
        _source_kwargs(source_key=source_key, reference_time=reference_time)
    )
    assert item.source_key == source_key
    assert item.reference_time == reference_time
    assert item.source_key.endswith(' ')
    assert item.reference_time.endswith(' ')


def test_catalog_error_code_includes_phase1_codes_without_removing_existing():
    values = {c.value for c in CatalogErrorCode}
    names = {c.name for c in CatalogErrorCode}
    for code in _PREEXISTING_ERROR_CODES:
        assert code in values, f'missing preexisting code: {code}'
        assert code in names
    for code in _PHASE1_ERROR_CODES:
        assert code in values, f'missing CONT-08 code: {code}'
        assert code in names
    # No dual-version dead helper: identity version constant is catalog-v2 only.
    from models import catalog_common as common

    assert getattr(common, 'IDENTITY_SCHEMA_VERSION', None) == 'catalog-v2'
    assert 'CatalogStrictModel' in dir(common)
    assert frozenset({'FE', 'BO', 'COMMON'}) == getattr(common, 'SYSTEM_KEYS', frozenset())


def test_valid_entity_list_order_preserved():
    entities = [
        _entity_kwargs(graph_key='TABLE::FE::ORCL.HR.Z', name_raw='Z', name_canonical='z'),
        _entity_kwargs(graph_key='TABLE::FE::ORCL.HR.A', name_raw='A', name_canonical='a'),
        _entity_kwargs(graph_key='TABLE::FE::ORCL.HR.M', name_raw='M', name_canonical='m'),
    ]
    # Two identical nested items remain separate list entries (no merge-on-equality).
    entities_dup = [
        _entity_kwargs(graph_key='TABLE::FE::ORCL.HR.SAME', name_raw='S', name_canonical='s'),
        _entity_kwargs(graph_key='TABLE::FE::ORCL.HR.SAME', name_raw='S', name_canonical='s'),
    ]
    req = UpsertTypedEntitiesRequest.model_validate(
        {
            **_v2_shell(batch_id='batch-order', entities=entities),
        }
    )
    assert [e.graph_key for e in req.entities] == [
        'TABLE::FE::ORCL.HR.Z',
        'TABLE::FE::ORCL.HR.A',
        'TABLE::FE::ORCL.HR.M',
    ]
    req_dup = UpsertTypedEntitiesRequest.model_validate(
        {
            **_v2_shell(batch_id='batch-dup', entities=entities_dup),
        }
    )
    assert len(req_dup.entities) == 2
    assert [e.graph_key for e in req_dup.entities] == [
        'TABLE::FE::ORCL.HR.SAME',
        'TABLE::FE::ORCL.HR.SAME',
    ]


# ---------------------------------------------------------------------------
# Catalog-v2 graph-key grammar (IDEN-03..06,08,09,12)
# ---------------------------------------------------------------------------


_GRAMMAR_POSITIVE_KEYS: list[tuple[str, str]] = [
    ('System', 'SYSTEM::FE::CORE'),
    ('Database', 'DATABASE::FE::ORCL'),
    ('DictionaryDocument', 'DOC::FE::ORCL.HR_DICT'),
    ('Schema', 'SCHEMA::FE::ORCL.HR'),
    ('Table', 'TABLE::FE::ORCL.HR.EMPLOYEES'),
    ('View', 'VIEW::FE::ORCL.HR.EMP_V'),
    ('MaterializedView', 'MVIEW::FE::ORCL.HR.EMP_MV'),
    ('Column', 'COLUMN::FE::ORCL.HR.EMPLOYEES.EMP_ID'),
    ('Constraint', 'CONSTRAINT::FE::ORCL.HR.EMP_PK'),
    ('Index', 'INDEX::FE::ORCL.HR.EMP_IX'),
    ('Package', 'PACKAGE::FE::ORCL.HR.EMP_PKG'),
    ('Procedure', 'PROCEDURE::FE::ORCL.HR.EMP_PKG.HIRE#1'),
    ('Function', 'FUNCTION::FE::ORCL.HR.EMP_PKG.GET_SAL#ARGS(P_ID)'),
    ('Trigger', 'TRIGGER::FE::ORCL.HR.EMP_BI'),
    ('Sequence', 'SEQUENCE::FE::ORCL.HR.EMP_SEQ'),
    ('Synonym', 'SYNONYM::FE::ORCL.HR.EMP_SYN'),
    ('DatabaseLink', 'DBLINK::FE::ORCL.REMOTE_HR'),
    ('SourceArtifact', 'SOURCE::FE::PDF/HR_CATALOG#p12'),
]


def _entity_for_type(entity_type: str, graph_key: str, **overrides: Any) -> dict[str, Any]:
    leaf = graph_key.rsplit('.', 1)[-1].split('#', 1)[0]
    if entity_type == 'SourceArtifact':
        leaf = graph_key.split('::', 2)[-1]
    return _entity_kwargs(
        entity_type=entity_type,
        graph_key=graph_key,
        name_raw=leaf[:64] or 'X',
        name_canonical=(leaf[:64] or 'x').lower(),
        database_qualified_name=graph_key.split('::', 2)[-1][:512],
        **overrides,
    )


@pytest.mark.parametrize(('entity_type', 'graph_key'), _GRAMMAR_POSITIVE_KEYS)
def test_grammar_positive_key_per_entity_type(entity_type: str, graph_key: str):
    item = CatalogEntityItem.model_validate(_entity_for_type(entity_type, graph_key))
    assert item.entity_type == entity_type
    assert item.graph_key == graph_key

    req = UpsertTypedEntitiesRequest.model_validate(
        {
            **_v2_shell(batch_id='grammar-pos', entities=[_entity_for_type(entity_type, graph_key)]),
        }
    )
    assert req.entities[0].graph_key == graph_key
    assert req.system_key == 'FE'


@pytest.mark.parametrize(
    ('entity_type', 'graph_key', 'marker'),
    [
        ('Table', 'TABLE::HR.EMPLOYEES', 'catalog_v1'),
        ('Table', 'TABLE::fe::ORCL.HR.EMPLOYEES', 'lowercase_system'),
        ('Table', 'TABLE::XX::ORCL.HR.EMPLOYEES', 'unknown_system'),
        ('Table', 'TABLE::FE::ORCL.HR', 'wrong_segment_count'),
        ('Table', 'TABLE::FE::orcl.HR.EMPLOYEES', 'lowercase_ident'),
        ('Schema', 'TABLE::FE::ORCL.HR', 'type_prefix_mismatch'),
        ('Procedure', 'PROCEDURE::FE::ORCL.HR.EMP_PKG.HIRE', 'missing_overload'),
        ('Procedure', 'PROCEDURE::FE::ORCL.HR.EMP_PKG.HIRE#', 'empty_overload'),
        ('Function', 'FUNCTION::FE::ORCL.HR.GET_SAL', 'missing_overload'),
        ('Function', 'FUNCTION::FE::ORCL.HR.GET_SAL#', 'empty_overload'),
        ('Table', '', 'empty_graph_key'),
        ('Table', 'TABLE::FE::' + ('A' * 1100), 'overlong_graph_key'),
    ],
)
def test_grammar_negative_rejects_invalid_keys(entity_type: str, graph_key: str, marker: str):
    with pytest.raises(ValidationError) as exc:
        CatalogEntityItem.model_validate(_entity_for_type(entity_type, graph_key))
    msg = str(exc.value).lower()
    assert any(
        token in msg
        for token in (
            'graph_key',
            'prefix',
            'grammar',
            'overload',
            'system',
            'invalid',
            'string_too_long',
            'max_length',
            'at least',
            'ensure this value',
        )
    ), (marker, msg)


def test_grammar_rejects_catalog_v1_key_without_rewrite():
    v1 = 'TABLE::HR.EMPLOYEES'
    with pytest.raises(ValidationError) as exc:
        CatalogEntityItem.model_validate(_entity_for_type('Table', v1))
    msg = str(exc.value).lower()
    assert 'graph_key' in msg or 'grammar' in msg or 'prefix' in msg
    # No dual-version rewrite helper may exist or be used.
    import models.catalog_common as common

    assert not hasattr(common, 'rewrite_v1_graph_key')
    assert not hasattr(common, 'normalize_graph_key')


def test_grammar_system_mismatch_rejects_nested_entity_under_shell():
    with pytest.raises(ValidationError) as exc:
        UpsertTypedEntitiesRequest.model_validate(
            {
                **_v2_shell(
                    system_key='BO',
                    batch_id='mismatch',
                    entities=[_entity_kwargs(graph_key='TABLE::FE::ORCL.HR.EMPLOYEES')],
                ),
            }
        )
    msg = str(exc.value).lower()
    assert 'system' in msg or 'graph_key' in msg or 'invalid_system_key' in msg


def test_grammar_fe_bo_same_body_valid_under_matching_shells_and_unequal():
    body = 'ORCL.HR.EMPLOYEES'
    fe_key = f'TABLE::FE::{body}'
    bo_key = f'TABLE::BO::{body}'
    fe_req = UpsertTypedEntitiesRequest.model_validate(
        {
            **_v2_shell(
                system_key='FE',
                batch_id='fe-body',
                entities=[_entity_kwargs(graph_key=fe_key)],
            ),
        }
    )
    bo_req = UpsertTypedEntitiesRequest.model_validate(
        {
            **_v2_shell(
                system_key='BO',
                batch_id='bo-body',
                entities=[_entity_kwargs(graph_key=bo_key)],
            ),
        }
    )
    assert fe_req.entities[0].graph_key == fe_key
    assert bo_req.entities[0].graph_key == bo_key
    assert fe_req.entities[0].graph_key != bo_req.entities[0].graph_key


def test_grammar_procedure_function_require_nonempty_overload_package_and_standalone():
    package_ok = 'PROCEDURE::FE::ORCL.HR.EMP_PKG.HIRE#OVERLOAD_A'
    standalone_ok = 'FUNCTION::FE::ORCL.HR.GET_SAL#1'
    assert (
        CatalogEntityItem.model_validate(_entity_for_type('Procedure', package_ok)).graph_key
        == package_ok
    )
    assert (
        CatalogEntityItem.model_validate(_entity_for_type('Function', standalone_ok)).graph_key
        == standalone_ok
    )
    with pytest.raises(ValidationError):
        CatalogEntityItem.model_validate(
            _entity_for_type('Procedure', 'PROCEDURE::FE::ORCL.HR.EMP_PKG.HIRE')
        )
    with pytest.raises(ValidationError):
        CatalogEntityItem.model_validate(
            _entity_for_type('Function', 'FUNCTION::FE::ORCL.HR.GET_SAL#')
        )


def test_source_artifact_graph_key_distinct_from_provenance_source_key_concept():
    artifact_key = 'SOURCE::FE::PDF/HR_CATALOG#p12'
    item = CatalogEntityItem.model_validate(_entity_for_type('SourceArtifact', artifact_key))
    assert item.graph_key == artifact_key
    # Provenance source_key remains a free-form identity input, not SourceArtifact grammar.
    source = CatalogSourceItem.model_validate(_source_kwargs(source_key='DOC::HR.PDF#p12'))
    assert source.source_key == 'DOC::HR.PDF#p12'
    assert source.source_key != item.graph_key
    assert not source.source_key.startswith('SOURCE::')


def test_graph_key_echo_exact_equality_iden08_long_multi_segment():
    long_key = (
        'COLUMN::FE::ORCL.HR.EMPLOYEES.'
        'VERY_LONG_COLUMN_NAME_WITH_MANY_SEGMENTS_AND_DETAILS_001'
    )
    submitted = _entity_for_type('Column', long_key)
    item = CatalogEntityItem.model_validate(submitted)
    assert item.graph_key == long_key
    assert item.graph_key == submitted['graph_key']

    edge_source = 'SCHEMA::FE::ORCL.HR'
    edge_target = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    edge = CatalogEdgeItem.model_validate(
        _edge_kwargs(source_graph_key=edge_source, target_graph_key=edge_target)
    )
    assert edge.source_graph_key == edge_source
    assert edge.target_graph_key == edge_target

    req = UpsertTypedEntitiesRequest.model_validate(
        {
            **_v2_shell(batch_id='echo', entities=[submitted]),
        }
    )
    assert req.entities[0].graph_key == long_key

    resolve = ResolveTypedEntitiesRequest.model_validate(
        {
            **_v2_shell(
                entities=[{'entity_type': 'Column', 'graph_key': long_key}],
            ),
        }
    )
    assert resolve.entities[0].graph_key == long_key

    prov = UpsertProvenanceRequest.model_validate(
        {
            **_v2_shell(
                batch_id='prov-echo',
                sources=[_source_kwargs()],
                entity_targets=[{'entity_type': 'Column', 'graph_key': long_key}],
            ),
        }
    )
    assert prov.entity_targets[0].graph_key == long_key
