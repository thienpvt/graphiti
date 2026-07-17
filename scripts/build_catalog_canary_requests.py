#!/usr/bin/env python3
"""Build immutable deterministic catalog canary v2 request artifacts."""

from __future__ import annotations

# ruff: noqa: E402  # Script bootstraps mcp_server/src before server imports.
import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_SRC = REPO_ROOT / 'mcp_server' / 'src'
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from models.catalog_batch import NestedProvenancePayload, UpsertCatalogBatchRequest
from models.catalog_edges import CatalogEdgeItem
from models.catalog_entities import CatalogEntityItem
from models.catalog_provenance import (
    CatalogProvenanceEdgeTarget,
    CatalogProvenanceEntityTarget,
    CatalogSourceItem,
)
from services.catalog_identity import canonical_sha256
from services.catalog_service import CatalogService

GROUP_ID = 'oracle-catalog-v2'
DOCUMENT_ID = 'docling-14451470779352042667'
DOCUMENT_KEY = f'DOC::{DOCUMENT_ID}'
MALFORMED_DOCUMENT_ID = 'docling-144514770779352042667'
EXPECTED_CATALOG_SHA256 = '3882cb4bc50064215ead782b0fa0dfbf0098cb344b50184e6c207145377e832f'
ACCEPT_TAB_GOLDEN_REQUEST_SHA256 = (
    'a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a'
)

TABLE_IDS = (
    'SVFE_SHB.ACCEPT_TAB',
    'SVFE_SHB.FORM_CFG',
    'SVFE_SHB.T_PRE_AUTH_TXN_TYPE',
    'SVFE_SHB.T_TRANS_TYPE',
    'SVFE_SHB.T_TRANS_TYPE_CLASS',
)
TABLE_BATCHES = {
    'SVFE_SHB.ACCEPT_TAB': ('canary-v2::accept-tab', 'accept-tab.payload.json'),
    'SVFE_SHB.FORM_CFG': ('canary-v2::form-cfg', 'form-cfg.payload.json'),
    'SVFE_SHB.T_PRE_AUTH_TXN_TYPE': (
        'canary-v2::pre-auth-txn-type',
        'pre-auth-txn-type.payload.json',
    ),
    'SVFE_SHB.T_TRANS_TYPE': ('canary-v2::trans-type', 'trans-type.payload.json'),
    'SVFE_SHB.T_TRANS_TYPE_CLASS': (
        'canary-v2::trans-type-class',
        'trans-type-class.payload.json',
    ),
}
FK_BATCH_ID = 'canary-v2::documented-foreign-keys'
FK_FILE_NAME = 'documented-foreign-keys.payload.json'
SELECTED_FKS = frozenset(
    {
        f'{DOCUMENT_ID}:PRE_AUTH_TXN_C_TRANS_TYPE_FK',
        f'{DOCUMENT_ID}:PRE_AUTH_TXN_TRANS_TYPE_FK',
        f'{DOCUMENT_ID}:TRANS_TYPE_TRANS_TYPE_CLASS_FK',
    }
)
QUARANTINES = frozenset(
    {
        f'{DOCUMENT_ID}:FK_DT_INST_LIMIT_DT_DESC',
        f'{DOCUMENT_ID}:FK_EMV_CARD_SCRIPT_CARD_REFER:2',
        f'{DOCUMENT_ID}:FK_INNER_ATM_EV_ST_TERM_DEF:2',
        f'{DOCUMENT_ID}:FK_MISC_SRV_ATTRIBUTE_MISC_SRV:2',
        f'{DOCUMENT_ID}:FK_SUPV_TRN_CTR_CFG_TRN_TP_CTR',
        f'{DOCUMENT_ID}:FK_TRX_GROUP_TERM_TYPE',
        f'{DOCUMENT_ID}:ISS_BIN_CARD_TEMPLATE_FK:2',
        f'{DOCUMENT_ID}:T_FEE_ALG_FA08_ISO_CURR_FK',
    }
)
EXPECTED_ENTITY_COUNTS = Counter(
    {
        'Column': 21,
        'Constraint': 6,
        'Table': 5,
        'Index': 4,
        'DictionaryDocument': 1,
        'Schema': 1,
    }
)
EXPECTED_EDGE_COUNTS = Counter(
    {'Contains': 54, 'DocumentedBy': 26, 'PrimaryKeyOf': 2, 'ForeignKeyTo': 3}
)
PAYLOAD_FIELDS = frozenset(
    {'group_id', 'batch_id', 'catalog_sha256', 'atomic', 'entities', 'edges', 'provenance'}
)
TRANSIENT_FIELDS = frozenset({'dry_run', 'request_sha256', 'timestamps', 'counters'})


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f'non-finite JSON number: {value}')


def strict_json_bytes(raw: bytes, source: str) -> Any:
    if raw.startswith(b'\xef\xbb\xbf'):
        raise ValueError(f'{source}: UTF-8 BOM is forbidden')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError(f'{source}: invalid UTF-8') from exc
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def strict_load(path: Path) -> Any:
    return strict_json_bytes(path.read_bytes(), str(path))


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')
        + b'\n'
    )


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_key(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def unique(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = _canonical_key(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def refs(item: dict[str, Any]) -> list[Any]:
    return unique(list(item.get('source_refs') or []))


def pages(item: dict[str, Any]) -> list[int]:
    return sorted(
        {ref['page'] for ref in refs(item) if isinstance(ref, dict) and ref.get('page') is not None}
    )


def summary(item: dict[str, Any], fallback: str) -> str:
    for field in ('description_normalized', 'description_original', 'comment_original'):
        value = item.get(field)
        if value:
            return str(value)
    notes = item.get('notes_original') or []
    return ' '.join(str(note) for note in notes) if notes else fallback


def schema_key(schema: str) -> str:
    return f'SCHEMA::{schema}'


def table_key(table_id: str) -> str:
    return f'TABLE::{table_id}'


def column_key(table_id: str, column: str) -> str:
    return f'COLUMN::{table_id}.{column}'


def constraint_key(schema: str, name: str) -> str:
    return f'CONSTRAINT::{schema}.{name}'


def index_key(schema: str, name: str) -> str:
    return f'INDEX::{schema}.{name}'


def attributes(item: dict[str, Any], **extra: Any) -> dict[str, Any]:
    result = {
        'description_original': item.get('description_original'),
        'description_normalized': item.get('description_normalized'),
        'source_refs': refs(item),
        'normalization_notes': item.get('normalization_notes') or [],
        'warnings': item.get('warnings') or [],
    }
    result.update(extra)
    return result


def make_entity(
    entity_type: str,
    graph_key: str,
    name_raw: str,
    name_canonical: str,
    database_qualified_name: str,
    object_summary: str,
    item: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        'entity_type': entity_type,
        'graph_key': graph_key,
        'name_raw': name_raw,
        'name_canonical': name_canonical,
        'database_qualified_name': database_qualified_name,
        'summary': object_summary,
        'attributes': attributes(item, **extra),
        'source_refs': refs(item),
        'confidence': 1.0,
    }
    model = CatalogEntityItem.model_validate(result)
    result['content_sha256'] = canonical_sha256(CatalogService.entity_canonical_payload(model))
    CatalogEntityItem.model_validate(result)
    return result


def make_edge(
    edge_type: str,
    edge_key: str,
    source_graph_key: str,
    source_entity_type: str,
    target_graph_key: str,
    target_entity_type: str,
    fact: str,
    evidence: str,
    **edge_attributes: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        'edge_type': edge_type,
        'edge_key': edge_key,
        'source_graph_key': source_graph_key,
        'source_entity_type': source_entity_type,
        'target_graph_key': target_graph_key,
        'target_entity_type': target_entity_type,
        'fact': fact,
        'evidence': evidence,
        'attributes': edge_attributes,
        'confidence': 1.0,
    }
    model = CatalogEdgeItem.model_validate(result)
    result['content_sha256'] = canonical_sha256(CatalogService.edge_canonical_payload(model))
    CatalogEdgeItem.model_validate(result)
    return result


def make_source(batch_id: str, source_refs: list[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        'source_key': f'{batch_id}|{EXPECTED_CATALOG_SHA256}',
        'reference_time': '1970-01-01T00:00:00Z',
        'attributes': {
            'document_id': DOCUMENT_ID,
            'source_refs': unique(source_refs),
            'batch_id': batch_id,
        },
        'metadata': {
            'ingest_kind': 'deterministic_catalog_canary_v2',
            'catalog_sha256': EXPECTED_CATALOG_SHA256,
        },
    }
    model = CatalogSourceItem.model_validate(result)
    result['content_sha256'] = canonical_sha256(CatalogService.source_canonical_payload(model))
    CatalogSourceItem.model_validate(result)
    return result


def _column_signature(columns: list[dict[str, Any]]) -> tuple[str | None, ...]:
    return tuple(column.get('name_canonical') for column in columns)


def merge_table_objects(
    table: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schema = table['schema']
    constraints: dict[str, dict[str, Any]] = {}
    constraint_signatures: dict[str, tuple[str, str, tuple[str | None, ...]]] = {}
    indexes: dict[str, dict[str, Any]] = {}
    index_signatures: dict[str, tuple[str, str, tuple[str | None, ...]]] = {}

    for source in list(table['primary_keys']) + list(table['constraints']):
        if source['constraint_type'] == 'INDEX':
            continue
        name = source['name_canonical']
        signature = (schema, source['constraint_type'], _column_signature(source['columns']))
        if name in constraints:
            if constraint_signatures[name] != signature:
                raise ValueError(
                    f'divergent constraint signatures for {schema}.{name}: '
                    f'{constraint_signatures[name]} != {signature}'
                )
            constraints[name]['source_refs'] = unique(refs(constraints[name]) + refs(source))
            continue
        item = dict(source)
        item['source_refs'] = refs(source)
        constraints[name] = item
        constraint_signatures[name] = signature

    for source in table['indexes']:
        name = source['name_canonical']
        signature = (schema, 'INDEX', _column_signature(source['columns']))
        if name in indexes:
            if index_signatures[name] != signature:
                raise ValueError(
                    f'divergent index signatures for {schema}.{name}: '
                    f'{index_signatures[name]} != {signature}'
                )
            indexes[name]['source_refs'] = unique(refs(indexes[name]) + refs(source))
            continue
        item = dict(source)
        item['source_refs'] = refs(source)
        indexes[name] = item
        index_signatures[name] = signature

    for source in table['constraints']:
        if source['constraint_type'] != 'INDEX':
            continue
        name = source['name_canonical']
        signature = (schema, 'INDEX', _column_signature(source['columns']))
        explicit = indexes.get(name)
        if explicit is not None:
            if index_signatures[name] != signature:
                raise ValueError(
                    f'divergent index signatures for {schema}.{name}: '
                    f'{index_signatures[name]} != {signature}'
                )
            explicit['source_refs'] = unique(refs(explicit) + refs(source))
            explicit['merged_index_constraint_source_refs'] = refs(source)
            continue
        indexes[name] = {
            'name_raw': source['name_raw'],
            'name_canonical': name,
            'index_type': None,
            'columns': [
                {
                    'ordinal': position,
                    'name_raw': column.get('name_raw'),
                    'name_canonical': column.get('name_canonical'),
                    'expression': None,
                }
                for position, column in enumerate(source['columns'], 1)
            ],
            'source_refs': refs(source),
            'normalization_notes': source.get('normalization_notes') or [],
            'warnings': source.get('warnings') or [],
        }
        index_signatures[name] = signature

    return list(constraints.values()), list(indexes.values())


def make_request(
    batch_id: str,
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    source_refs: list[Any],
) -> dict[str, Any]:
    return {
        'group_id': GROUP_ID,
        'batch_id': batch_id,
        'catalog_sha256': EXPECTED_CATALOG_SHA256,
        'atomic': True,
        'entities': entities,
        'edges': edges,
        'provenance': {
            'sources': [make_source(batch_id, source_refs)],
            'entity_targets': [
                {'entity_type': item['entity_type'], 'graph_key': item['graph_key']}
                for item in entities
            ],
            'edge_targets': [
                {'edge_type': item['edge_type'], 'edge_key': item['edge_key']} for item in edges
            ],
        },
    }


def build_table_request(
    catalog: dict[str, Any], table: dict[str, Any], document: dict[str, Any]
) -> dict[str, Any]:
    table_id = table['id']
    schema = table['schema']
    batch_id = TABLE_BATCHES[table_id][0]
    constraints, indexes = merge_table_objects(table)
    entities: list[dict[str, Any]] = []

    document_refs = refs(document)
    document_pages = pages(document)
    document_item = {
        'source_refs': [],
        'normalization_notes': [],
        'warnings': [],
    }
    entities.append(
        make_entity(
            'DictionaryDocument',
            DOCUMENT_KEY,
            DOCUMENT_ID,
            DOCUMENT_ID,
            DOCUMENT_ID,
            f'Database dictionary document {document["file_name"]}',
            document_item,
            document_id=DOCUMENT_ID,
            file_name=document['file_name'],
            schema_version=catalog['schema_version'],
            source_page_count=len(document_refs),
            source_page_min=min(document_pages),
            source_page_max=max(document_pages),
        )
    )
    schema_item = {'source_refs': [], 'normalization_notes': [], 'warnings': []}
    entities.append(
        make_entity(
            'Schema',
            schema_key(schema),
            schema,
            schema,
            schema,
            f'Oracle schema {schema}',
            schema_item,
        )
    )
    entities.append(
        make_entity(
            'Table',
            table_key(table_id),
            table['name_raw'],
            table['name_canonical'],
            table_id,
            summary(table, f'Oracle table {table_id}'),
            table,
        )
    )

    for column in table['columns']:
        dqn = f'{table_id}.{column["name_canonical"]}'
        entities.append(
            make_entity(
                'Column',
                column_key(table_id, column['name_canonical']),
                column['name_raw'],
                column['name_canonical'],
                dqn,
                summary(
                    column,
                    f'Column {dqn} with data type '
                    f'{column.get("data_type_raw") or column.get("data_type_base")}',
                ),
                column,
                ordinal=column.get('ordinal'),
                data_type_raw=column.get('data_type_raw'),
                data_type_base=column.get('data_type_base'),
                precision=column.get('precision'),
                scale=column.get('scale'),
                not_null=column.get('not_null'),
                default_value_raw=column.get('default_value_raw'),
                semantic_hints=column.get('semantic_hints') or [],
            )
        )

    for constraint in constraints:
        dqn = f'{schema}.{constraint["name_canonical"]}'
        entities.append(
            make_entity(
                'Constraint',
                constraint_key(schema, constraint['name_canonical']),
                constraint['name_raw'],
                constraint['name_canonical'],
                dqn,
                summary(
                    constraint,
                    f'{constraint["constraint_type"]} constraint {dqn} on table {table_id}',
                ),
                constraint,
                constraint_type=constraint['constraint_type'],
                columns=constraint.get('columns') or [],
            )
        )

    for index in indexes:
        dqn = f'{schema}.{index["name_canonical"]}'
        entities.append(
            make_entity(
                'Index',
                index_key(schema, index['name_canonical']),
                index['name_raw'],
                index['name_canonical'],
                dqn,
                summary(
                    index,
                    f'{index.get("index_type") or "INDEX"} index {dqn} on table {table_id}',
                ),
                index,
                index_type=index.get('index_type'),
                columns=index.get('columns') or [],
                merged_index_constraint_source_refs=(
                    index.get('merged_index_constraint_source_refs') or []
                ),
            )
        )

    result_edges: list[dict[str, Any]] = []
    table_pages = pages(table)
    result_edges.append(
        make_edge(
            'Contains',
            f'contains|{schema_key(schema)}|{table_key(table_id)}',
            schema_key(schema),
            'Schema',
            table_key(table_id),
            'Table',
            f'Schema {schema_key(schema)} contains table {table_key(table_id)}.',
            f'document_id={DOCUMENT_ID}; pages={table_pages}',
            document_id=DOCUMENT_ID,
            pages=table_pages,
            inferred=False,
        )
    )

    for column in table['columns']:
        graph_key = column_key(table_id, column['name_canonical'])
        column_pages = pages(column)
        result_edges.append(
            make_edge(
                'Contains',
                f'contains|{table_key(table_id)}|{graph_key}',
                table_key(table_id),
                'Table',
                graph_key,
                'Column',
                f'Table {table_key(table_id)} contains column {graph_key}.',
                f'document_id={DOCUMENT_ID}; pages={column_pages}',
                document_id=DOCUMENT_ID,
                pages=column_pages,
                ordinal=column.get('ordinal'),
                inferred=False,
            )
        )
        result_edges.append(
            make_edge(
                'DocumentedBy',
                f'documented_by|{graph_key}|{DOCUMENT_KEY}',
                graph_key,
                'Column',
                DOCUMENT_KEY,
                'DictionaryDocument',
                f'Column {graph_key} is documented by {DOCUMENT_KEY}.',
                f'document_id={DOCUMENT_ID}; pages={column_pages}',
                document_id=DOCUMENT_ID,
                pages=column_pages,
                inferred=False,
            )
        )

    real_columns = {column['name_canonical'] for column in table['columns']}
    for constraint in constraints:
        graph_key = constraint_key(schema, constraint['name_canonical'])
        constraint_pages = pages(constraint)
        result_edges.append(
            make_edge(
                'Contains',
                f'contains|{table_key(table_id)}|{graph_key}',
                table_key(table_id),
                'Table',
                graph_key,
                'Constraint',
                f'Table {table_key(table_id)} contains constraint {graph_key}.',
                f'document_id={DOCUMENT_ID}; pages={constraint_pages}',
                document_id=DOCUMENT_ID,
                pages=constraint_pages,
                constraint_type=constraint['constraint_type'],
                inferred=False,
            )
        )
        for position, column in enumerate(constraint['columns'], 1):
            name = column.get('name_canonical')
            if name not in real_columns:
                continue
            target_key = column_key(table_id, name)
            result_edges.append(
                make_edge(
                    'Contains',
                    f'contains|{graph_key}|{target_key}',
                    graph_key,
                    'Constraint',
                    target_key,
                    'Column',
                    f'Constraint {graph_key} contains column {target_key}.',
                    f'document_id={DOCUMENT_ID}; pages={constraint_pages}',
                    document_id=DOCUMENT_ID,
                    pages=constraint_pages,
                    position=column.get('position', position),
                    inferred=False,
                )
            )
        if constraint['constraint_type'] == 'PRIMARY_KEY':
            result_edges.append(
                make_edge(
                    'PrimaryKeyOf',
                    f'primary_key_of|{graph_key}|{table_key(table_id)}',
                    graph_key,
                    'Constraint',
                    table_key(table_id),
                    'Table',
                    f'Constraint {graph_key} is primary key of table {table_key(table_id)}.',
                    f'document_id={DOCUMENT_ID}; pages={constraint_pages}',
                    document_id=DOCUMENT_ID,
                    pages=constraint_pages,
                    inferred=False,
                )
            )

    for index in indexes:
        graph_key = index_key(schema, index['name_canonical'])
        index_pages = pages(index)
        result_edges.append(
            make_edge(
                'Contains',
                f'contains|{table_key(table_id)}|{graph_key}',
                table_key(table_id),
                'Table',
                graph_key,
                'Index',
                f'Table {table_key(table_id)} contains index {graph_key}.',
                f'document_id={DOCUMENT_ID}; pages={index_pages}',
                document_id=DOCUMENT_ID,
                pages=index_pages,
                inferred=False,
            )
        )
        for position, column in enumerate(index['columns'], 1):
            name = column.get('name_canonical')
            if name not in real_columns:
                continue
            target_key = column_key(table_id, name)
            result_edges.append(
                make_edge(
                    'Contains',
                    f'contains|{graph_key}|{target_key}',
                    graph_key,
                    'Index',
                    target_key,
                    'Column',
                    f'Index {graph_key} contains column {target_key}.',
                    f'document_id={DOCUMENT_ID}; pages={index_pages}',
                    document_id=DOCUMENT_ID,
                    pages=index_pages,
                    ordinal=column.get('ordinal', position),
                    expression=column.get('expression'),
                    inferred=False,
                )
            )

    result_edges.append(
        make_edge(
            'DocumentedBy',
            f'documented_by|{table_key(table_id)}|{DOCUMENT_KEY}',
            table_key(table_id),
            'Table',
            DOCUMENT_KEY,
            'DictionaryDocument',
            f'Table {table_key(table_id)} is documented by {DOCUMENT_KEY}.',
            f'document_id={DOCUMENT_ID}; pages={table_pages}',
            document_id=DOCUMENT_ID,
            pages=table_pages,
            inferred=False,
        )
    )

    all_refs = refs(table)
    for column in table['columns']:
        all_refs.extend(refs(column))
    for item in constraints + indexes:
        all_refs.extend(refs(item))
    return make_request(batch_id, entities, result_edges, unique(all_refs))


def build_fk_request(relationships: list[dict[str, Any]]) -> dict[str, Any]:
    result_edges: list[dict[str, Any]] = []
    all_refs: list[Any] = []
    for relationship in relationships:
        source_table = next(
            table_id
            for table_id in TABLE_IDS
            if table_id.endswith('.' + relationship['from_table'])
        )
        target_table = next(
            table_id for table_id in TABLE_IDS if table_id.endswith('.' + relationship['to_table'])
        )
        relationship_pages = pages(relationship)
        description = relationship.get('description_normalized') or relationship.get(
            'description_original'
        )
        for source_column, target_column in zip(
            relationship['from_columns'], relationship['to_columns'], strict=True
        ):
            source_key = column_key(source_table, source_column['name_canonical'])
            target_key = column_key(target_table, target_column['name_canonical'])
            edge_key = f'foreign_key_to|{relationship["id"]}|{source_key}|{target_key}'
            fact = (
                f'Documented relationship {relationship["id"]} '
                f'({relationship["name_canonical"]}) links {source_key} to {target_key}; '
                f'association_raw={relationship["association_raw"]}; '
                f'related_constraint={relationship["related_constraint"]}; '
                f'status=documented; document_id={DOCUMENT_ID}; '
                f'pages={relationship_pages}; description={description}.'
            )
            result_edges.append(
                make_edge(
                    'ForeignKeyTo',
                    edge_key,
                    source_key,
                    'Column',
                    target_key,
                    'Column',
                    fact,
                    f'document_id={DOCUMENT_ID}; pages={relationship_pages}; '
                    f'relationship_id={relationship["id"]}',
                    documented_relationship_id=relationship['id'],
                    relationship_name=relationship['name_canonical'],
                    source_column_graph_key=source_key,
                    target_column_graph_key=target_key,
                    association_raw=relationship['association_raw'],
                    related_constraint=relationship['related_constraint'],
                    status='documented',
                    document_id=DOCUMENT_ID,
                    pages=relationship_pages,
                    description_normalized=relationship.get('description_normalized'),
                    inferred=False,
                )
            )
        all_refs.extend(refs(relationship))
    return make_request(FK_BATCH_ID, [], result_edges, unique(all_refs))


def _reject_unknown_fields(raw: dict[str, Any], model: type[Any], path: str) -> None:
    unknown = set(raw) - set(model.model_fields)
    if unknown:
        raise ValueError(f'{path}: unknown fields: {sorted(unknown)}')


def validate_request(raw: dict[str, Any]) -> tuple[UpsertCatalogBatchRequest, str]:
    if set(raw) != PAYLOAD_FIELDS:
        raise ValueError(
            f'{raw.get("batch_id", "request")}: top-level fields must be '
            f'{sorted(PAYLOAD_FIELDS)}, got {sorted(raw)}'
        )
    forbidden = TRANSIENT_FIELDS & set(raw)
    if forbidden:
        raise ValueError(f'{raw["batch_id"]}: transient fields forbidden: {sorted(forbidden)}')
    _reject_unknown_fields(raw, UpsertCatalogBatchRequest, '$')
    for index, item in enumerate(raw['entities']):
        _reject_unknown_fields(item, CatalogEntityItem, f'$.entities[{index}]')
    for index, item in enumerate(raw['edges']):
        _reject_unknown_fields(item, CatalogEdgeItem, f'$.edges[{index}]')
    provenance = raw['provenance']
    _reject_unknown_fields(provenance, NestedProvenancePayload, '$.provenance')
    for index, item in enumerate(provenance['sources']):
        _reject_unknown_fields(item, CatalogSourceItem, f'$.provenance.sources[{index}]')
    for index, item in enumerate(provenance['entity_targets']):
        _reject_unknown_fields(
            item,
            CatalogProvenanceEntityTarget,
            f'$.provenance.entity_targets[{index}]',
        )
    for index, item in enumerate(provenance['edge_targets']):
        _reject_unknown_fields(
            item,
            CatalogProvenanceEdgeTarget,
            f'$.provenance.edge_targets[{index}]',
        )

    model = UpsertCatalogBatchRequest.model_validate(raw)
    for item in model.entities:
        digest = canonical_sha256(CatalogService.entity_canonical_payload(item))
        if item.content_sha256 != digest:
            raise ValueError(f'{item.graph_key}: entity content hash mismatch')
    for item in model.edges:
        digest = canonical_sha256(CatalogService.edge_canonical_payload(item))
        if item.content_sha256 != digest:
            raise ValueError(f'{item.edge_key}: edge content hash mismatch')
    if model.provenance is None:
        raise ValueError(f'{model.batch_id}: provenance required')
    for item in model.provenance.sources:
        digest = canonical_sha256(CatalogService.source_canonical_payload(item))
        if item.content_sha256 != digest:
            raise ValueError(f'{item.source_key}: source content hash mismatch')
    return model, CatalogService.batch_request_sha256(model)


def validate_batches(
    batches: list[tuple[str, str, dict[str, Any], list[str]]],
) -> tuple[Counter[str], Counter[str], dict[str, str]]:
    available_entities: dict[tuple[str, str], dict[str, Any]] = {}
    available_edges: dict[tuple[str, str], dict[str, Any]] = {}
    unique_entities: dict[tuple[str, str], dict[str, Any]] = {}
    unique_edges: dict[tuple[str, str], dict[str, Any]] = {}
    request_hashes: dict[str, str] = {}

    for batch_id, _file_name, raw, _dependencies in batches:
        model, request_hash = validate_request(raw)
        if model.batch_id != batch_id:
            raise ValueError(f'{batch_id}: payload batch_id mismatch')
        request_hashes[batch_id] = request_hash
        current_entities = {
            (item.entity_type, item.graph_key): raw_item
            for item, raw_item in zip(model.entities, raw['entities'], strict=True)
        }
        visible_entities = {**available_entities, **current_entities}
        for item in model.edges:
            source = (item.source_entity_type, item.source_graph_key)
            target = (item.target_entity_type, item.target_graph_key)
            if source not in visible_entities:
                raise ValueError(f'{item.edge_key}: missing source endpoint {source}')
            if target not in visible_entities:
                raise ValueError(f'{item.edge_key}: missing target endpoint {target}')
            if batch_id == FK_BATCH_ID and (
                source not in available_entities or target not in available_entities
            ):
                raise ValueError(f'{item.edge_key}: FK endpoints must pre-exist')
        current_edges = {
            (item.edge_type, item.edge_key): raw_item
            for item, raw_item in zip(model.edges, raw['edges'], strict=True)
        }
        visible_edges = {**available_edges, **current_edges}
        assert model.provenance is not None
        for target in model.provenance.entity_targets:
            if (target.entity_type, target.graph_key) not in visible_entities:
                raise ValueError(f'{batch_id}: missing provenance entity target {target}')
        for target in model.provenance.edge_targets:
            if (target.edge_type, target.edge_key) not in visible_edges:
                raise ValueError(f'{batch_id}: missing provenance edge target {target}')

        for identity, item in current_entities.items():
            prior = unique_entities.setdefault(identity, item)
            if prior != item:
                raise ValueError(f'{batch_id}: divergent duplicate entity {identity}')
        for identity, item in current_edges.items():
            if identity in unique_edges:
                raise ValueError(f'{batch_id}: duplicate edge {identity}')
            unique_edges[identity] = item
        available_entities.update(current_entities)
        available_edges.update(current_edges)

    entity_counts = Counter(identity[0] for identity in unique_entities)
    edge_counts = Counter(identity[0] for identity in unique_edges)
    if entity_counts != EXPECTED_ENTITY_COUNTS:
        raise ValueError(f'unique entity counts mismatch: {entity_counts}')
    if edge_counts != EXPECTED_EDGE_COUNTS:
        raise ValueError(f'unique edge counts mismatch: {edge_counts}')
    if len(unique_entities) != 38 or len(unique_edges) != 85:
        raise ValueError(
            f'unique totals mismatch: {len(unique_entities)} entities, {len(unique_edges)} edges'
        )
    required_uk4 = {
        ('Index', 'INDEX::SVFE_SHB.T_PRE_AUTH_TXN_TYPE_UK4'),
        ('Constraint', 'CONSTRAINT::SVFE_SHB.T_PRE_AUTH_TXN_TYPE_UK4'),
    }
    if not required_uk4 <= unique_entities.keys():
        raise ValueError('T_PRE_AUTH_TXN_TYPE_UK4 Index and Constraint must remain distinct')
    return entity_counts, edge_counts, request_hashes


def _manifest_timestamp(path: Path) -> str:
    if path.exists():
        existing = strict_load(path)
        if not isinstance(existing, dict) or not isinstance(existing.get('generated_at'), str):
            raise ValueError(f'{path}: existing manifest lacks generated_at')
        return existing['generated_at']
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _atomic_write_missing(path: Path, raw: bytes) -> None:
    if path.exists():
        if path.read_bytes() != raw:
            raise FileExistsError(f'refusing to overwrite differing file: {path}')
        return
    fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise


def build(catalog_path: Path, output_dir: Path) -> dict[str, Any]:
    catalog_raw = catalog_path.read_bytes()
    catalog_sha256 = sha256_bytes(catalog_raw)
    if catalog_sha256 != EXPECTED_CATALOG_SHA256:
        raise ValueError(
            f'catalog SHA mismatch: expected {EXPECTED_CATALOG_SHA256}, got {catalog_sha256}'
        )
    catalog = strict_json_bytes(catalog_raw, str(catalog_path))
    if not isinstance(catalog, dict):
        raise ValueError('catalog root must be an object')

    documents = {document['document_id']: document for document in catalog['documents']}
    tables = {table['id']: table for table in catalog['tables']}
    relationships = {relationship['id']: relationship for relationship in catalog['relationships']}
    if DOCUMENT_ID not in documents:
        raise ValueError(f'missing document: {DOCUMENT_ID}')
    missing_tables = set(TABLE_IDS) - tables.keys()
    if missing_tables:
        raise ValueError(f'missing tables: {sorted(missing_tables)}')
    missing_selected = SELECTED_FKS - relationships.keys()
    if missing_selected:
        raise ValueError(f'missing selected relationships: {sorted(missing_selected)}')
    missing_quarantines = QUARANTINES - relationships.keys()
    if missing_quarantines:
        raise ValueError(f'missing quarantine identities: {sorted(missing_quarantines)}')
    if SELECTED_FKS & QUARANTINES:
        raise ValueError('selected relationships overlap quarantines')

    document = documents[DOCUMENT_ID]
    batches: list[tuple[str, str, dict[str, Any], list[str]]] = []
    for table_id in TABLE_IDS:
        batch_id, file_name = TABLE_BATCHES[table_id]
        batches.append(
            (batch_id, file_name, build_table_request(catalog, tables[table_id], document), [])
        )
    fk_dependencies = [
        TABLE_BATCHES['SVFE_SHB.T_PRE_AUTH_TXN_TYPE'][0],
        TABLE_BATCHES['SVFE_SHB.T_TRANS_TYPE'][0],
        TABLE_BATCHES['SVFE_SHB.T_TRANS_TYPE_CLASS'][0],
    ]
    batches.append(
        (
            FK_BATCH_ID,
            FK_FILE_NAME,
            build_fk_request([relationships[key] for key in sorted(SELECTED_FKS)]),
            fk_dependencies,
        )
    )

    entity_counts, edge_counts, request_hashes = validate_batches(batches)
    accept_hash = request_hashes[TABLE_BATCHES['SVFE_SHB.ACCEPT_TAB'][0]]
    if accept_hash != ACCEPT_TAB_GOLDEN_REQUEST_SHA256:
        raise ValueError(
            'ACCEPT_TAB server request SHA mismatch at $: '
            f'expected {ACCEPT_TAB_GOLDEN_REQUEST_SHA256}, got {accept_hash}'
        )

    payload_bytes = {file_name: canonical_bytes(raw) for _, file_name, raw, _ in batches}
    combined_payload = b''.join(payload_bytes.values())
    if MALFORMED_DOCUMENT_ID.encode() in combined_payload:
        raise ValueError(f'malformed document ID present: {MALFORMED_DOCUMENT_ID}')
    for quarantine in QUARANTINES:
        if quarantine.encode() in combined_payload:
            raise ValueError(f'quarantined relationship present: {quarantine}')

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / 'manifest.json'
    manifest_batches: list[dict[str, Any]] = []
    for position, (batch_id, file_name, raw, dependencies) in enumerate(batches, 1):
        provenance = raw['provenance']
        entity_targets = len(provenance['entity_targets'])
        edge_targets = len(provenance['edge_targets'])
        sources = len(provenance['sources'])
        relative_path = (Path('catalog') / 'canary-v2-requests' / file_name).as_posix()
        manifest_batches.append(
            {
                'order': position,
                'batch_id': batch_id,
                'path': relative_path,
                'dependencies': dependencies,
                'artifact_sha256': sha256_bytes(payload_bytes[file_name]),
                'server_request_sha256': request_hashes[batch_id],
                'counts': {
                    'entities': len(raw['entities']),
                    'edges': len(raw['edges']),
                    'provenance_sources': sources,
                    'provenance_entity_targets': entity_targets,
                    'provenance_edge_targets': edge_targets,
                    'provenance_links': sources * (entity_targets + edge_targets),
                },
            }
        )
    manifest = {
        'generated_at': _manifest_timestamp(manifest_path),
        'catalog_sha256': catalog_sha256,
        'target_group_id': GROUP_ID,
        'accept_tab_golden_server_request_sha256': ACCEPT_TAB_GOLDEN_REQUEST_SHA256,
        'accept_tab_golden_match': True,
        'unique_totals': {'entities': 38, 'edges': 85},
        'entity_counts': dict(sorted(entity_counts.items())),
        'edge_counts': dict(sorted(edge_counts.items())),
        'quarantines': sorted(QUARANTINES),
        'batches': manifest_batches,
    }
    manifest_raw = canonical_bytes(manifest)

    destinations = {
        **{output_dir / file_name: raw for file_name, raw in payload_bytes.items()},
        manifest_path: manifest_raw,
    }
    differing = [
        path for path, raw in destinations.items() if path.exists() and path.read_bytes() != raw
    ]
    if differing:
        raise FileExistsError(
            'refusing to overwrite differing files: ' + ', '.join(str(path) for path in differing)
        )

    for file_name, raw in payload_bytes.items():
        _atomic_write_missing(output_dir / file_name, raw)

    reopened_batches: list[tuple[str, str, dict[str, Any], list[str]]] = []
    for batch_id, file_name, _raw, dependencies in batches:
        path = output_dir / file_name
        disk_raw = path.read_bytes()
        expected_raw = payload_bytes[file_name]
        if disk_raw != expected_raw:
            raise ValueError(f'{path}: bytes changed after write')
        parsed = strict_json_bytes(disk_raw, str(path))
        reopened_batches.append((batch_id, file_name, parsed, dependencies))
        entry = next(item for item in manifest_batches if item['batch_id'] == batch_id)
        if sha256_bytes(disk_raw) != entry['artifact_sha256']:
            raise ValueError(f'{path}: artifact hash mismatch after reopen')
    _, _, reopened_hashes = validate_batches(reopened_batches)
    if reopened_hashes != request_hashes:
        raise ValueError('server request hashes changed after reopen')

    _atomic_write_missing(manifest_path, manifest_raw)
    if strict_json_bytes(manifest_path.read_bytes(), str(manifest_path)) != manifest:
        raise ValueError(f'{manifest_path}: manifest round-trip mismatch')
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--catalog',
        type=Path,
        default=REPO_ROOT / 'catalog' / 'catalog.json',
        help='source catalog.json path',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=REPO_ROOT / 'catalog' / 'canary-v2-requests',
        help='immutable artifact output directory',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build(args.catalog.resolve(), args.output_dir.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
