"""Authoritative batch hash contract (HASH-01..07, TEST-04 pure recipe)."""

from __future__ import annotations

import copy
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_batch import NestedProvenancePayload, UpsertCatalogBatchRequest  # noqa: E402
from models.catalog_common import IDENTITY_SCHEMA_VERSION  # noqa: E402
from models.catalog_edges import CatalogEdgeItem  # noqa: E402
from models.catalog_entities import CatalogEntityItem  # noqa: E402
from models.catalog_evidence import CatalogEvidenceLink  # noqa: E402
from models.catalog_provenance import CatalogSourceItem  # noqa: E402
from services.catalog_identity import (  # noqa: E402
    CANONICALIZATION_VERSION,
    CATALOG_SCHEMA_VERSION,
    batch_request_canonical_payload,
    batch_request_sha256,
    canonical_sha256,
    coalesce_byte_identical_evidence_links,
    evidence_link_key,
)

GROUP = 'oracle-catalog-tool-test'
CATALOG_HASH = 'a' * 64


def _entity(**overrides: Any) -> CatalogEntityItem:
    data: dict[str, Any] = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'HR.EMPLOYEES',
        'summary': 'Employee master',
        'attributes': {},
        'confidence': 1.0,
    }
    data.update(overrides)
    return CatalogEntityItem.model_validate(data)


def _edge(**overrides: Any) -> CatalogEdgeItem:
    data: dict[str, Any] = {
        'edge_type': 'ForeignKeyTo',
        'edge_key': 'FK::HR.EMPLOYEES->HR.DEPARTMENTS',
        'source_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'source_entity_type': 'Table',
        'target_graph_key': 'TABLE::FE::ORCL.HR.DEPARTMENTS',
        'target_entity_type': 'Table',
        'fact': 'employees.dept_id references departments',
        'evidence': None,
        'attributes': {},
        'confidence': 1.0,
    }
    data.update(overrides)
    return CatalogEdgeItem.model_validate(data)


def _source(**overrides: Any) -> CatalogSourceItem:
    data: dict[str, Any] = {
        'source_key': 'SRC::ddl.sql#employees',
        'reference_time': '2026-07-16T12:00:00Z',
        'attributes': {'doc': 'ddl.sql'},
        'metadata': None,
    }
    data.update(overrides)
    return CatalogSourceItem.model_validate(data)


def _link(**overrides: Any) -> CatalogEvidenceLink:
    data: dict[str, Any] = {
        'source_key': 'SRC::ddl.sql#employees',
        'entity_target': {
            'entity_type': 'Table',
            'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        },
        'evidence_kind': 'ddl',
        'extractor_name': 'oracle-ddl-extractor',
        'extractor_version': '1.0.0',
        'excerpt': 'CREATE TABLE employees',
    }
    data.update(overrides)
    return CatalogEvidenceLink.model_validate(data)


def _batch(**overrides: Any) -> UpsertCatalogBatchRequest:
    data: dict[str, Any] = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': GROUP,
        'batch_id': 'hash-batch-001',
        'entities': [_entity()],
        'edges': [],
        'provenance': None,
        'catalog_sha256': CATALOG_HASH,
        'dry_run': False,
    }
    data.update(overrides)
    return UpsertCatalogBatchRequest.model_validate(data)


def test_canonicalization_version_constants():
    assert CANONICALIZATION_VERSION == 'catalog-canonical-v1'
    assert CATALOG_SCHEMA_VERSION == 'catalog-schema-v1'
    assert IDENTITY_SCHEMA_VERSION == 'catalog-v2'


def test_catalog_sha256_required_and_lowercase_hex():
    with pytest.raises(ValidationError):
        UpsertCatalogBatchRequest.model_validate(
            {
                'identity_schema_version': 'catalog-v2',
                'system_key': 'FE',
                'group_id': GROUP,
                'batch_id': 'b1',
                'entities': [_entity().model_dump(mode='json')],
            }
        )
    with pytest.raises(ValidationError):
        UpsertCatalogBatchRequest.model_validate(
            {
                'identity_schema_version': 'catalog-v2',
                'system_key': 'FE',
                'group_id': GROUP,
                'batch_id': 'b1',
                'entities': [_entity().model_dump(mode='json')],
                'catalog_sha256': None,
            }
        )
    with pytest.raises(ValidationError):
        _batch(catalog_sha256='A' * 64)
    with pytest.raises(ValidationError):
        _batch(catalog_sha256='a' * 63)
    with pytest.raises(ValidationError):
        _batch(catalog_sha256='g' * 64)
    ok = _batch(catalog_sha256='b' * 64, dry_run=True)
    assert ok.catalog_sha256 == 'b' * 64
    assert ok.dry_run is True


def test_recipe_includes_versions_system_key_and_collections():
    req = _batch(
        edges=[_edge()],
        provenance=NestedProvenancePayload(
            sources=[_source()],
            evidence_links=[_link()],
        ),
    )
    payload = batch_request_canonical_payload(req)
    assert payload['canonicalization_version'] == CANONICALIZATION_VERSION
    assert payload['identity_schema_version'] == 'catalog-v2'
    assert payload['system_key'] == 'FE'
    assert payload['group_id'] == GROUP
    assert payload['batch_id'] == 'hash-batch-001'
    assert payload['catalog_sha256'] == CATALOG_HASH
    assert len(payload['entities']) == 1
    assert len(payload['edges']) == 1
    assert len(payload['sources']) == 1
    assert len(payload['evidence_links']) == 1
    # Transport fields excluded from digest body.
    assert 'dry_run' not in payload
    assert 'request_sha256' not in payload


def test_mutate_included_fields_changes_digest():
    base = _batch(
        edges=[_edge()],
        provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[_link()]),
    )
    base_hash = batch_request_sha256(base)

    mutants: list[UpsertCatalogBatchRequest] = [
        _batch(
            batch_id='hash-batch-002',
            edges=[_edge()],
            provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[_link()]),
        ),
        _batch(
            group_id='oracle-catalog-tool-test2',
            edges=[_edge()],
            provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[_link()]),
        ),
        _batch(
            system_key='BO',
            entities=[_entity(graph_key='TABLE::BO::ORCL.HR.EMPLOYEES')],
            edges=[
                _edge(
                    source_graph_key='TABLE::BO::ORCL.HR.EMPLOYEES',
                    target_graph_key='TABLE::BO::ORCL.HR.DEPARTMENTS',
                )
            ],
            provenance=NestedProvenancePayload(
                sources=[_source()],
                evidence_links=[
                    _link(
                        entity_target={
                            'entity_type': 'Table',
                            'graph_key': 'TABLE::BO::ORCL.HR.EMPLOYEES',
                        }
                    )
                ],
            ),
        ),
        _batch(
            catalog_sha256='c' * 64,
            edges=[_edge()],
            provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[_link()]),
        ),
        _batch(
            entities=[_entity(summary='changed')],
            edges=[_edge()],
            provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[_link()]),
        ),
        _batch(
            edges=[_edge(fact='changed fact')],
            provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[_link()]),
        ),
        _batch(
            edges=[_edge()],
            provenance=NestedProvenancePayload(
                sources=[_source(attributes={'doc': 'other'})],
                evidence_links=[_link()],
            ),
        ),
        _batch(
            edges=[_edge()],
            provenance=NestedProvenancePayload(
                sources=[_source()],
                evidence_links=[_link(excerpt='ALTER TABLE employees')],
            ),
        ),
    ]
    for mutant in mutants:
        assert batch_request_sha256(mutant) != base_hash


def test_excluded_fields_do_not_change_digest():
    base = _batch(request_sha256=None, dry_run=False)
    h1 = batch_request_sha256(base)
    h2 = batch_request_sha256(_batch(request_sha256='f' * 64, dry_run=True))
    assert h1 == h2


def test_reorder_collections_same_digest():
    e1 = _entity(graph_key='TABLE::FE::ORCL.HR.A', name_raw='A', name_canonical='a')
    e2 = _entity(graph_key='TABLE::FE::ORCL.HR.B', name_raw='B', name_canonical='b')
    edge1 = _edge(edge_key='FK::ONE', fact='one')
    edge2 = _edge(edge_key='FK::TWO', fact='two')
    s1 = _source(source_key='SRC::one')
    s2 = _source(source_key='SRC::two')
    l1 = _link(source_key='SRC::one', excerpt='one')
    l2 = _link(
        source_key='SRC::two',
        entity_target={'entity_type': 'Table', 'graph_key': 'TABLE::FE::ORCL.HR.B'},
        excerpt='two',
    )
    a = _batch(
        entities=[e1, e2],
        edges=[edge1, edge2],
        provenance=NestedProvenancePayload(sources=[s1, s2], evidence_links=[l1, l2]),
    )
    b = _batch(
        entities=[e2, e1],
        edges=[edge2, edge1],
        provenance=NestedProvenancePayload(sources=[s2, s1], evidence_links=[l2, l1]),
    )
    assert batch_request_sha256(a) == batch_request_sha256(b)


def test_duplicate_identical_items_retain_multiplicity():
    e = _entity()
    single = _batch(entities=[e])
    double = _batch(entities=[e, e.model_copy(deep=True)])
    assert batch_request_sha256(single) != batch_request_sha256(double)


def test_byte_identical_evidence_links_coalesce_before_hash():
    link = _link()
    twin = link.model_copy(deep=True)
    different = _link(excerpt='different bytes')
    one = _batch(provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[link]))
    two_identical = _batch(
        provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[link, twin])
    )
    two_distinct = _batch(
        provenance=NestedProvenancePayload(sources=[_source()], evidence_links=[link, different])
    )
    assert batch_request_sha256(one) == batch_request_sha256(two_identical)
    assert batch_request_sha256(one) != batch_request_sha256(two_distinct)
    coalesced = coalesce_byte_identical_evidence_links([twin, link, different])
    assert len(coalesced) == 2
    assert [evidence_link_key(x) for x in coalesced] == sorted(
        evidence_link_key(x) for x in coalesced
    )


def test_empty_collections_and_evidence_only_hash_stable():
    emptyish = _batch(
        entities=[],
        edges=[],
        provenance=NestedProvenancePayload(sources=[], evidence_links=[_link()]),
    )
    payload = batch_request_canonical_payload(emptyish)
    assert payload['entities'] == []
    assert payload['edges'] == []
    assert payload['sources'] == []
    assert len(payload['evidence_links']) == 1
    h1 = batch_request_sha256(emptyish)
    h2 = batch_request_sha256(copy.deepcopy(emptyish))
    assert h1 == h2
    assert len(h1) == 64


def test_hash_reentrant_and_idempotent():
    req = _batch(edges=[_edge()], provenance=NestedProvenancePayload(evidence_links=[_link()]))
    first = batch_request_sha256(req)
    second = batch_request_sha256(req)
    assert first == second
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(batch_request_sha256, [req] * 8))
    assert all(r == first for r in results)


def test_service_static_delegates_to_pure_recipe():
    from services.catalog_service import CatalogService

    req = _batch()
    assert CatalogService.batch_request_sha256(req) == batch_request_sha256(req)
    assert CatalogService._batch_canonical_payload(req) == batch_request_canonical_payload(req)
    payload = CatalogService._batch_canonical_payload(req)
    assert 'entity_targets' not in payload
    assert 'edge_targets' not in payload
    assert 'provenance' not in payload
    assert canonical_sha256(payload) == batch_request_sha256(req)


@pytest.mark.asyncio
async def test_dry_run_echoes_authoritative_hash_fields_zero_write():
    from unittest.mock import AsyncMock, MagicMock

    from config.schema import CatalogConfig
    from services.catalog_service import CatalogService

    client = MagicMock()
    client.driver = MagicMock()
    client.driver.provider = MagicMock(value='neo4j')
    client.embedder = MagicMock()
    client.embedder.create = AsyncMock(return_value=[0.1])
    client.call_order = []

    cfg = CatalogConfig(
        enabled=True,
        uuid_namespace='6ba7b810-9dad-11d1-80b4-00c04fd430c8',
        max_entities_per_batch=500,
        max_edges_per_batch=2000,
        max_provenance_links_per_batch=5000,
    )
    service = CatalogService(catalog_config=cfg)
    service._store.get_batch_status = AsyncMock(return_value=None)
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()
    service._store.upsert_batch_status = AsyncMock()
    service._store.upsert_entity_item = AsyncMock()

    req = _batch(dry_run=True)
    expected = batch_request_sha256(req)
    resp = await service.upsert_catalog_batch(client=client, request=req)
    assert resp.dry_run is True
    assert resp.status == 'validating'
    assert resp.identity_schema_version == 'catalog-v2'
    assert resp.canonicalization_version == CANONICALIZATION_VERSION
    assert resp.request_sha256 == expected
    assert resp.catalog_sha256 == req.catalog_sha256
    assert resp.batch_uuid is not None
    client.embedder.create.assert_not_awaited()
    service._store.ensure_uuid_uniqueness_constraints.assert_not_awaited()
    service._store.upsert_batch_status.assert_not_awaited()
    service._store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_caller_request_hash_mismatch_echoes_server_hash():
    from unittest.mock import AsyncMock, MagicMock

    from config.schema import CatalogConfig
    from models.catalog_common import CatalogErrorCode
    from services.catalog_service import CatalogService

    client = MagicMock()
    client.driver = MagicMock()
    client.driver.provider = MagicMock(value='neo4j')
    client.embedder = MagicMock()
    client.embedder.create = AsyncMock()
    client.call_order = []
    cfg = CatalogConfig(
        enabled=True,
        uuid_namespace='6ba7b810-9dad-11d1-80b4-00c04fd430c8',
    )
    service = CatalogService(catalog_config=cfg)
    service._store.get_batch_status = AsyncMock(return_value=None)
    req = _batch(request_sha256='b' * 64)
    expected = batch_request_sha256(req)
    resp = await service.upsert_catalog_batch(client=client, request=req)
    assert resp.error_code == CatalogErrorCode.content_hash_mismatch
    assert resp.request_sha256 == expected
    assert resp.catalog_sha256 == req.catalog_sha256
    assert resp.identity_schema_version == 'catalog-v2'
    assert resp.canonicalization_version == CANONICALIZATION_VERSION
    service._store.get_batch_status.assert_not_awaited()
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case,provider,error_code',
    [
        ('feature_disabled', 'neo4j', 'feature_disabled'),
        ('invalid_uuid_namespace', 'neo4j', 'invalid_uuid_namespace'),
        ('backend_unavailable', 'falkordb', 'backend_unavailable'),
        ('batch_limit_exceeded', 'neo4j', 'batch_limit_exceeded'),
    ],
)
async def test_batch_gate_failure_echoes_request_hash(case, provider, error_code):
    """HASH-05: gate failures still echo authoritative request hash fields."""
    from unittest.mock import AsyncMock, MagicMock

    from config.schema import CatalogConfig
    from models.catalog_common import CatalogErrorCode
    from services.catalog_service import CatalogService

    client = MagicMock()
    client.driver = MagicMock()
    client.driver.provider = MagicMock(value=provider)
    client.embedder = MagicMock()
    client.embedder.create = AsyncMock()
    client.call_order = []

    if case == 'feature_disabled':
        cfg = CatalogConfig(
            enabled=False,
            uuid_namespace='6ba7b810-9dad-11d1-80b4-00c04fd430c8',
        )
    elif case == 'invalid_uuid_namespace':
        # Bypass pydantic: enabled + valid-looking construction then corrupt namespace.
        cfg = CatalogConfig(enabled=False, uuid_namespace=None)
        object.__setattr__(cfg, 'enabled', True)
        object.__setattr__(cfg, 'uuid_namespace', 'not-a-uuid')
    elif case == 'backend_unavailable':
        cfg = CatalogConfig(
            enabled=True,
            uuid_namespace='6ba7b810-9dad-11d1-80b4-00c04fd430c8',
        )
    else:
        cfg = CatalogConfig(
            enabled=True,
            uuid_namespace='6ba7b810-9dad-11d1-80b4-00c04fd430c8',
            max_entities_per_batch=1,
        )

    service = CatalogService(catalog_config=cfg)
    service._store.get_batch_status = AsyncMock(return_value=None)
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()
    service._store.upsert_batch_status = AsyncMock()
    service._store.upsert_entity_item = AsyncMock()

    entities = (
        [_entity(), _entity(graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS')]
        if case == 'batch_limit_exceeded'
        else [_entity()]
    )
    req = _batch(entities=entities)
    expected = batch_request_sha256(req)
    resp = await service.upsert_catalog_batch(client=client, request=req)

    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode(error_code)
    assert resp.request_sha256 == expected
    assert resp.canonicalization_version == CANONICALIZATION_VERSION
    assert resp.identity_schema_version == IDENTITY_SCHEMA_VERSION
    assert resp.catalog_sha256 == req.catalog_sha256
    client.embedder.create.assert_not_awaited()
    service._store.get_batch_status.assert_not_awaited()
    service._store.ensure_uuid_uniqueness_constraints.assert_not_awaited()
    service._store.upsert_batch_status.assert_not_awaited()
    service._store.upsert_entity_item.assert_not_awaited()


def test_batch_gate_counts_evidence_links_not_cartesian():
    from unittest.mock import MagicMock

    from config.schema import CatalogConfig
    from services.catalog_service import CatalogService

    cfg = CatalogConfig(
        enabled=True,
        uuid_namespace='6ba7b810-9dad-11d1-80b4-00c04fd430c8',
        max_provenance_links_per_batch=1,
    )
    service = CatalogService(catalog_config=cfg)
    client = MagicMock()
    client.driver = MagicMock()
    client.driver.provider = MagicMock(value='neo4j')
    # 2 links exceed max 1
    req = _batch(
        entities=[],
        provenance=NestedProvenancePayload(
            sources=[_source()],
            evidence_links=[
                _link(source_key='SRC::a', excerpt='a'),
                _link(source_key='SRC::b', excerpt='b'),
            ],
        ),
    )
    gate = service._batch_gate_error(client, req)
    assert gate is not None
    assert gate[0].value == 'batch_limit_exceeded'
