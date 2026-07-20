"""Pure catalog-v2 request/fixture constructors for Neo4j integration tests.

No test-framework fixtures, Neo4j drivers, sockets, network clients, or integration modules.
"""

from __future__ import annotations

import importlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

# Allow running without package install: mcp_server/src on path.
_SRC = Path(__file__).resolve().parent.parent / 'src'
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))



def _attr(module_name: str, symbol: str) -> Any:
    value = getattr(importlib.import_module(module_name), symbol, None)
    if value is None:
        raise ImportError(f'{module_name}.{symbol} missing')
    return value


NestedProvenancePayload = _attr('models.catalog_batch', 'NestedProvenancePayload')
UpsertCatalogBatchRequest = _attr('models.catalog_batch', 'UpsertCatalogBatchRequest')
CatalogEdgeItem = _attr('models.catalog_edges', 'CatalogEdgeItem')
UpsertTypedEdgesRequest = _attr('models.catalog_edges', 'UpsertTypedEdgesRequest')
CatalogEntityItem = _attr('models.catalog_entities', 'CatalogEntityItem')
ResolveEntityRef = _attr('models.catalog_entities', 'ResolveEntityRef')
ResolveTypedEntitiesRequest = _attr('models.catalog_entities', 'ResolveTypedEntitiesRequest')
UpsertTypedEntitiesRequest = _attr('models.catalog_entities', 'UpsertTypedEntitiesRequest')
VerifyCatalogBatchRequest = _attr('models.catalog_entities', 'VerifyCatalogBatchRequest')
VerifyEdgeRef = _attr('models.catalog_entities', 'VerifyEdgeRef')
VerifyEntityRef = _attr('models.catalog_entities', 'VerifyEntityRef')
CatalogEvidenceEdgeTarget = _attr('models.catalog_evidence', 'CatalogEvidenceEdgeTarget')
CatalogEvidenceEntityTarget = _attr('models.catalog_evidence', 'CatalogEvidenceEntityTarget')
CatalogEvidenceLink = _attr('models.catalog_evidence', 'CatalogEvidenceLink')
CatalogProvenanceEdgeTarget = _attr(
    'models.catalog_provenance', 'CatalogProvenanceEdgeTarget'
)
CatalogProvenanceEntityTarget = _attr(
    'models.catalog_provenance', 'CatalogProvenanceEntityTarget'
)
CatalogSourceItem = _attr('models.catalog_provenance', 'CatalogSourceItem')
UpsertProvenanceRequest = _attr('models.catalog_provenance', 'UpsertProvenanceRequest')

GROUP = 'oracle-catalog-tool-test'
FORBIDDEN_GROUP = 'oracle-catalog-v2'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
BATCH = 'gate02-batch-001'
EDGE_BATCH = 'gate02-edge-batch-001'
ACCEPT_TAB_BATCH = 'accept-tab-batch-001'
ACCEPT_TAB_FIXTURE = Path(__file__).parent / 'fixtures' / 'accept_tab_sanitized.json'
SYSTEM_KEY = 'FE'
IDENTITY_SCHEMA_VERSION = 'catalog-v2'
_RUN_TOKEN = uuid.uuid4().hex[:10].upper()


def _scope_accept_fixture(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _scope_accept_fixture(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scope_accept_fixture(item) for item in value]
    if isinstance(value, str):
        return (
            value.replace('ACCEPT_PARENT', f'ACCEPT_PARENT_{_RUN_TOKEN}')
            .replace('ACCEPT_TAB', f'ACCEPT_TAB_{_RUN_TOKEN}')
            .replace('accept_parent', f'accept_parent_{_RUN_TOKEN.lower()}')
            .replace('accept_tab', f'accept_tab_{_RUN_TOKEN.lower()}')
        )
    return value


def build_entity(
    entity_type: str,
    graph_key: str,
    name_raw: str,
    name_canonical: str,
    dqn: str,
    summary: str,
    **extra: Any,
) -> Any:
    data: dict[str, Any] = {
        'entity_type': entity_type,
        'graph_key': graph_key,
        'name_raw': name_raw,
        'name_canonical': name_canonical,
        'database_qualified_name': dqn,
        'summary': summary,
        'attributes': {'src': 'gate02'},
        'confidence': 0.95,
    }
    data.update(extra)
    return CatalogEntityItem.model_validate(data)


def build_six_entities() -> list[Any]:
    return [
        build_entity(
            'Database', 'DATABASE::FE::ORCL', 'ORCL', 'orcl', 'ORCL', 'Oracle database'
        ),
        build_entity(
            'Schema', 'SCHEMA::FE::ORCL.HR', 'HR', 'hr', 'ORCL.HR', 'HR schema'
        ),
        build_entity(
            'Table',
            'TABLE::FE::ORCL.HR.EMPLOYEES',
            'EMPLOYEES',
            'employees',
            'ORCL.HR.EMPLOYEES',
            'Employees',
        ),
        build_entity(
            'Column',
            'COLUMN::FE::ORCL.HR.EMPLOYEES.ID',
            'ID',
            'id',
            'ORCL.HR.EMPLOYEES.ID',
            'PK column',
        ),
        build_entity(
            'Constraint',
            'CONSTRAINT::FE::ORCL.HR.PK_EMP',
            'PK_EMP',
            'pk_emp',
            'ORCL.HR.PK_EMP',
            'Primary key',
        ),
        build_entity(
            'Index',
            'INDEX::FE::ORCL.HR.IX_EMP_NAME',
            'IX_EMP_NAME',
            'ix_emp_name',
            'ORCL.HR.IX_EMP_NAME',
            'Name index',
        ),
    ]


def build_extra_table(
    key: str = 'TABLE::FE::ORCL.HR.DEPARTMENTS',
) -> Any:
    body = key.split('::', 2)[-1]
    name = body.split('.')[-1]
    return build_entity('Table', key, name, name.lower(), body, f'Table {name}')


def build_doc_entity() -> Any:
    return build_entity(
        'DictionaryDocument',
        'DOC::FE::HR.EMPLOYEES',
        'EMP_DOC',
        'emp_doc',
        'HR.EMPLOYEES',
        'Employee documentation',
    )


def build_edge(
    edge_type: str,
    edge_key: str,
    source_graph_key: str,
    source_entity_type: str,
    target_graph_key: str,
    target_entity_type: str,
    fact: str,
    **extra: Any,
) -> Any:
    data: dict[str, Any] = {
        'edge_type': edge_type,
        'edge_key': edge_key,
        'source_graph_key': source_graph_key,
        'source_entity_type': source_entity_type,
        'target_graph_key': target_graph_key,
        'target_entity_type': target_entity_type,
        'fact': fact,
        'confidence': 0.9,
    }
    data.update(extra)
    return CatalogEdgeItem.model_validate(data)


def build_structural_and_fk_edges() -> list[Any]:
    return [
        build_edge(
            'Contains',
            'CONTAINS::SCHEMA::FE::ORCL.HR->TABLE::FE::ORCL.HR.EMPLOYEES',
            'SCHEMA::FE::ORCL.HR',
            'Schema',
            'TABLE::FE::ORCL.HR.EMPLOYEES',
            'Table',
            'schema HR contains table EMPLOYEES',
        ),
        build_edge(
            'PrimaryKeyOf',
            'PK::CONSTRAINT::FE::ORCL.HR.PK_EMP->TABLE::FE::ORCL.HR.EMPLOYEES',
            'CONSTRAINT::FE::ORCL.HR.PK_EMP',
            'Constraint',
            'TABLE::FE::ORCL.HR.EMPLOYEES',
            'Table',
            'PK_EMP is primary key of EMPLOYEES',
        ),
        build_edge(
            'UniqueKeyOf',
            'UK::CONSTRAINT::FE::ORCL.HR.PK_EMP->COLUMN::FE::ORCL.HR.EMPLOYEES.ID',
            'CONSTRAINT::FE::ORCL.HR.PK_EMP',
            'Constraint',
            'COLUMN::FE::ORCL.HR.EMPLOYEES.ID',
            'Column',
            'PK_EMP uniquely keys column ID',
        ),
        build_edge(
            'DocumentedBy',
            'DOCUMENTED::TABLE::FE::ORCL.HR.EMPLOYEES->DOC::FE::HR.EMPLOYEES',
            'TABLE::FE::ORCL.HR.EMPLOYEES',
            'Table',
            'DOC::FE::HR.EMPLOYEES',
            'DictionaryDocument',
            'EMPLOYEES documented by EMP_DOC',
        ),
        build_edge(
            'ForeignKeyTo',
            'FK::ORCL.HR.EMPLOYEES.DEPT_ID->ORCL.HR.DEPARTMENTS.DEPT_ID',
            'TABLE::FE::ORCL.HR.EMPLOYEES',
            'Table',
            'TABLE::FE::ORCL.HR.DEPARTMENTS',
            'Table',
            'employees.dept_id references departments.dept_id',
        ),
        build_edge(
            'ForeignKeyTo',
            'FK::ORCL.HR.EMPLOYEES.MGR_ID->ORCL.HR.DEPARTMENTS.MGR_DEPT',
            'TABLE::FE::ORCL.HR.EMPLOYEES',
            'Table',
            'TABLE::FE::ORCL.HR.DEPARTMENTS',
            'Table',
            'employees.mgr_id references departments via alternate FK key',
        ),
    ]


def build_accept_tab_request(
    *,
    dry_run: bool = False,
    batch_id: str = ACCEPT_TAB_BATCH,
    group_id: str = GROUP,
) -> Any:
    payload = json.loads(ACCEPT_TAB_FIXTURE.read_text(encoding='utf-8'))
    assert payload['batch_id'] == ACCEPT_TAB_BATCH
    assert payload['identity_schema_version'] == IDENTITY_SCHEMA_VERSION
    assert payload['system_key'] == SYSTEM_KEY
    payload = _scope_accept_fixture(payload)
    return UpsertCatalogBatchRequest(
        identity_schema_version=IDENTITY_SCHEMA_VERSION,
        system_key=SYSTEM_KEY,
        group_id=group_id,
        batch_id=batch_id,
        entities=[CatalogEntityItem.model_validate(item) for item in payload['entities']],
        edges=[CatalogEdgeItem.model_validate(item) for item in payload['edges']],
        catalog_sha256='a' * 64,
        provenance=NestedProvenancePayload(
            sources=[
                CatalogSourceItem.model_validate(item)
                for item in payload['provenance']['sources']
            ],
            evidence_links=[
                CatalogEvidenceLink(
                    source_key=payload['provenance']['sources'][0]['source_key'],
                    entity_target=CatalogEvidenceEntityTarget.model_validate(item),
                    evidence_kind='ddl',
                    extractor_name='accept-tab-fixture',
                    extractor_version='1.0.0',
                    confidence=1.0,
                )
                for item in payload['provenance']['entity_targets']
            ]
            + [
                CatalogEvidenceLink(
                    source_key=payload['provenance']['sources'][0]['source_key'],
                    edge_target=CatalogEvidenceEdgeTarget.model_validate(item),
                    evidence_kind='ddl',
                    extractor_name='accept-tab-fixture',
                    extractor_version='1.0.0',
                    confidence=1.0,
                )
                for item in payload['provenance']['edge_targets']
            ],
        ),
        dry_run=dry_run,
    )


def build_upsert_entities_request(
    entities: list[Any],
    *,
    batch_id: str = BATCH,
    dry_run: bool = False,
    group_id: str = GROUP,
) -> Any:
    return UpsertTypedEntitiesRequest(
        identity_schema_version=IDENTITY_SCHEMA_VERSION,
        system_key=SYSTEM_KEY,
        group_id=group_id,
        batch_id=batch_id,
        entities=entities,
        dry_run=dry_run,
        atomic=True,
    )


def build_upsert_edges_request(
    edges: list[Any],
    *,
    batch_id: str = EDGE_BATCH,
    dry_run: bool = False,
    group_id: str = GROUP,
) -> Any:
    return UpsertTypedEdgesRequest(
        identity_schema_version=IDENTITY_SCHEMA_VERSION,
        system_key=SYSTEM_KEY,
        group_id=group_id,
        batch_id=batch_id,
        edges=edges,
        dry_run=dry_run,
        atomic=True,
        strict_endpoints=True,
    )


def build_resolve_entities_request(
    refs: list[Any],
    *,
    group_id: str = GROUP,
) -> Any:
    return ResolveTypedEntitiesRequest(
        identity_schema_version=IDENTITY_SCHEMA_VERSION,
        system_key=SYSTEM_KEY,
        group_id=group_id,
        entities=refs,
    )


def build_verify_batch_request(
    *,
    batch_id: str = BATCH,
    entities: list[Any] | None = None,
    edges: list[Any] | None = None,
    group_id: str = GROUP,
) -> Any:
    return VerifyCatalogBatchRequest(
        identity_schema_version=IDENTITY_SCHEMA_VERSION,
        system_key=SYSTEM_KEY,
        group_id=group_id,
        batch_id=batch_id,
        entities=entities or [],
        edges=edges or [],
    )


def build_provenance_request(
    *,
    sources: list[Any] | None = None,
    entity_targets: list[Any] | None = None,
    edge_targets: list[Any] | None = None,
    batch_id: str = 'prov-batch-001',
    group_id: str = GROUP,
) -> Any:
    return UpsertProvenanceRequest(
        identity_schema_version=IDENTITY_SCHEMA_VERSION,
        system_key=SYSTEM_KEY,
        group_id=group_id,
        batch_id=batch_id,
        sources=sources
        or [
            CatalogSourceItem.model_validate(
                {
                    'source_key': 'SOURCE::SYNTHETIC.HR.EMPLOYEES.DDL#1',
                    'reference_time': '2026-01-01T00:00:00Z',
                }
            )
        ],
        entity_targets=entity_targets
        or [
            CatalogProvenanceEntityTarget.model_validate(
                {
                    'entity_type': 'Table',
                    'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                }
            )
        ],
        edge_targets=edge_targets or [],
        atomic=True,
    )


def build_conflicting_entity_pair() -> tuple[Any, Any]:
    """Same deterministic identity, divergent raw/canonical/mutable payload."""
    winner = build_entity(
        'Table',
        'TABLE::FE::ORCL.HR.RACE',
        'RACE_WIN',
        'race_win',
        'ORCL.HR.RACE',
        'winner summary',
        attributes={'side': 'winner', 'payload': 1},
    )
    loser = build_entity(
        'Table',
        'TABLE::FE::ORCL.HR.RACE',
        'RACE_LOSE',
        'race_lose',
        'ORCL.HR.RACE',
        'loser summary',
        attributes={'side': 'loser', 'payload': 2},
    )
    return winner, loser
