#!/usr/bin/env python3
"""Build immutable deterministic catalog canary v2 request artifacts."""

from __future__ import annotations

# ruff: noqa: E402  # Script bootstraps mcp_server/src before server imports.
import argparse
import contextlib
import hashlib
import json
import os
import re
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
from models.catalog_evidence import CatalogEvidenceLink
from models.catalog_prepare import PrepareCatalogBatchRequest
from models.catalog_provenance import CatalogSourceItem
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

# Phase 5 offline hardened catalog-v2 artifacts (IDEN-13 / DOCS-06). Historical
# canary-v2-requests/ remain read-only and invalid as hardened authority.
HARDENED_ARTIFACT_SCHEMA_VERSION = 'canary-hardened-v1'
HARDENED_IDENTITY_SCHEMA_VERSION = 'catalog-v2'
HARDENED_SYSTEM_KEY = 'FE'
HARDENED_GROUP_ID = 'oracle-catalog-tool-test'  # never live-write oracle-catalog-v2
FUTURE_TARGET_GROUP_METADATA = 'oracle-catalog-v2'  # metadata only; never transported/executed
SANITIZED_FIXTURE_REL = Path('mcp_server') / 'tests' / 'fixtures' / 'accept_tab_sanitized.json'
HARDENED_OUTPUT_REL = Path('catalog') / 'canary-v2-requests-hardened'
HARDENED_PAYLOAD_FIELDS = frozenset(
    {
        'identity_schema_version',
        'system_key',
        'group_id',
        'batch_id',
        'catalog_sha256',
        'atomic',
        'entities',
        'edges',
        'provenance',
    }
)
HARDENED_EXTRACTOR_NAME = 'sanitized-fixture'
HARDENED_EXTRACTOR_VERSION = '1.0.0'
LIVE_ARTIFACT_SCHEMA_VERSION = 'phase6-canary-run-v1'
LIVE_PAYLOAD_NAME = 'accept-tab.payload.json'
LIVE_MANIFEST_NAME = 'run-manifest.json'
MAX_LIVE_ID_LENGTH = 512
LIVE_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')
PROTECTED_GROUP_IDS = frozenset(
    {'oracle-core', 'oracle-catalog-v2', 'oracle-catalog-tool-test', 'main'}
)
APPROVED_FIXTURE_RAW_SHA256 = 'db498f2997803cb09fff15283a523f66aabaf57d54139804484cffa9033de53c'
APPROVED_FIXTURE_LF_SHA256 = '145f38edb7245c448badc7598e2e0733b4c72c16f470909284c6e7d955bae922'
GOLDEN_SHA256 = {
    'accept-tab.payload.json': '9df952774c2ec7f33e110ef8956d7611851ea3e92d68ed108dae5eeedc21359f',
    'manifest.json': 'ba7d5c6c893f59a89ac3533749bfa0e70a4726abcaa7a09c339d754d62706eb9',
    'offline-checkpoint.json': 'f984a4f306f7e39e900f70dc322270c61456b0185d9120f8b50149121377e333',
    'offline-commit.receipt.json': '6fce1543fd5042768f879b978dbd682b460fa05c01cff5bc03bc059fa6397832',
    'offline-prepare.receipt.json': '0452ebd9fe9ee220900061e7af9e7fdc7520bb894e48c81e1406406ec5713111',
}
HISTORICAL_SHA256 = {
    'accept-tab.commit.response.json': (
        '83ac93da85957c5576c745a4db2e64d6e6ee8e99a2ac6c517e17b3f3e1ccc4f4'
    ),
    'accept-tab.dry-run.response.json': (
        '4767473f3ace434ae23bb69687261da8041f430e5ba1908f0ca62cd496fab139'
    ),
    'accept-tab.payload.json': '629decce0f7927d4de542b0cf2b11b12f45872c1d5e4771fd00c900091f3ba48',
    'documented-foreign-keys.payload.json': (
        '2da07e6a9f9a89d5cc6d5352007a3de3401e492ec66175cf480a501fc9741035'
    ),
    'form-cfg.payload.json': '25ca477a8f4180baa00d0b4e60b772b1663552ea3d92decac3d276cdcc2ea11b',
    'manifest.json': '039063d7adfe774564b8a8009af0868f96bb570fc1d74b4236e891d89506763d',
    'pre-auth-txn-type.payload.json': (
        '96150b1e1f10d5b5183f36aecb846f357af6aecd066e7d2d29f84c9872d1bb0b'
    ),
    'trans-type-class.payload.json': (
        '4337527970d5f010ae842a06b47dd3fc2ef46d8594e3336eb9b17a02b34a3e25'
    ),
    'trans-type.payload.json': '97d1b81d4a11434020da0b9bb0c6dd3cb5a099c93ac9ce925c92c5f59e704024',
}
LIVE_MANIFEST_FIELDS = frozenset(
    {
        'artifact_schema_version',
        'profile',
        'run_id',
        'group_id',
        'control_group_id',
        'batch_id',
        'identity_schema_version',
        'system_key',
        'fixture',
        'fixture_sha256',
        'fixture_lf_sha256',
        'catalog_sha256',
        'request_sha256',
        'artifact_sha256',
        'payload',
        'counts',
        'builder',
        'builder_sha256',
        'canary_executed',
    }
)


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


def lf_normalized_bytes(raw: bytes) -> bytes:
    return raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')


def lf_sha256(raw: bytes) -> str:
    return sha256_bytes(lf_normalized_bytes(raw))


def _validate_fixture_authority(fixture_path: Path, *, exact_path: bool) -> bytes:
    approved = (REPO_ROOT / SANITIZED_FIXTURE_REL).resolve()
    if exact_path and fixture_path.resolve() != approved:
        raise ValueError('live fixture path must be the exact approved sanitized fixture path')
    raw = fixture_path.read_bytes()
    if lf_sha256(raw) != APPROVED_FIXTURE_LF_SHA256:
        raise ValueError('sanitized fixture LF-normalized SHA-256 mismatch')
    return raw


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
    if 'entity_targets' in provenance or 'edge_targets' in provenance:
        raise ValueError(
            '$.provenance: Cartesian entity_targets/edge_targets rejected for catalog-v2; '
            'use evidence_links'
        )
    for index, item in enumerate(provenance.get('evidence_links') or []):
        _reject_unknown_fields(
            item,
            CatalogEvidenceLink,
            f'$.provenance.evidence_links[{index}]',
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
        for link in model.provenance.evidence_links:
            if link.entity_target is not None:
                key = (link.entity_target.entity_type, link.entity_target.graph_key)
                if key not in visible_entities:
                    raise ValueError(f'{batch_id}: missing evidence entity target {key}')
            if link.edge_target is not None:
                key = (link.edge_target.edge_type, link.edge_target.edge_key)
                if key not in visible_edges:
                    raise ValueError(f'{batch_id}: missing evidence edge target {key}')

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


def _atomic_replace_set(destinations: dict[Path, bytes]) -> None:
    """Stage and verify every file before replacing; restore on handled failures.

    ponytail: process-crash atomicity is directory-level only; use a generation directory
    plus pointer swap if readers ever consume files concurrently with regeneration.
    """
    staged: dict[Path, Path] = {}
    backups = {path: path.read_bytes() if path.exists() else None for path in destinations}
    replaced: list[Path] = []
    try:
        for path, raw in destinations.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent
            )
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            temporary = Path(temp_name)
            if temporary.read_bytes() != raw:
                raise OSError(f'staged bytes mismatch: {path.name}')
            staged[path] = temporary
        for path, temporary in staged.items():
            os.replace(temporary, path)
            replaced.append(path)
    except BaseException:
        for path in reversed(replaced):
            prior = backups[path]
            if prior is None:
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
            else:
                fd, temp_name = tempfile.mkstemp(
                    prefix=f'.{path.name}.restore.', suffix='.tmp', dir=path.parent
                )
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(prior)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, path)
        raise
    finally:
        for temporary in staged.values():
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()


def verify_historical(output_dir: Path) -> dict[str, Any]:
    """Verify frozen historical bytes without generating or overwriting them."""
    resolved = output_dir.resolve()
    authority = (REPO_ROOT / 'catalog' / 'canary-v2-requests').resolve()
    if resolved != authority:
        raise ValueError('historical mode verifies only the tracked historical directory')
    actual = {
        item.name: sha256_bytes(item.read_bytes()) for item in resolved.iterdir() if item.is_file()
    }
    if actual != HISTORICAL_SHA256:
        raise ValueError('historical artifact inventory or SHA-256 differs from frozen authority')
    manifest = strict_load(resolved / 'manifest.json')
    if not isinstance(manifest, dict):
        raise ValueError('historical manifest root must be an object')
    for batch in manifest.get('batches', []):
        if not isinstance(batch, dict):
            raise ValueError('historical manifest batch is invalid')
        path = (REPO_ROOT / str(batch.get('path'))).resolve()
        if path.parent != authority or not path.is_file():
            raise ValueError('historical manifest path escapes frozen authority')
        if lf_sha256(path.read_bytes()) != batch.get('artifact_sha256'):
            raise ValueError('historical manifest LF-normalized artifact SHA-256 differs')
    return manifest


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


def _with_content_hashes(
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    hashed_entities: list[dict[str, Any]] = []
    for item in entities:
        model = CatalogEntityItem.model_validate(item)
        payload = dict(item)
        payload['content_sha256'] = canonical_sha256(CatalogService.entity_canonical_payload(model))
        CatalogEntityItem.model_validate(payload)
        hashed_entities.append(payload)
    hashed_edges: list[dict[str, Any]] = []
    for item in edges:
        model = CatalogEdgeItem.model_validate(item)
        payload = dict(item)
        payload['content_sha256'] = canonical_sha256(CatalogService.edge_canonical_payload(model))
        CatalogEdgeItem.model_validate(payload)
        hashed_edges.append(payload)
    hashed_sources: list[dict[str, Any]] = []
    for item in sources:
        model = CatalogSourceItem.model_validate(item)
        payload = dict(item)
        payload['content_sha256'] = canonical_sha256(CatalogService.source_canonical_payload(model))
        CatalogSourceItem.model_validate(payload)
        hashed_sources.append(payload)
    return hashed_entities, hashed_edges, hashed_sources


def _evidence_links_from_cartesian(
    sources: list[dict[str, Any]],
    entity_targets: list[dict[str, Any]],
    edge_targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not sources:
        raise ValueError('sanitized fixture requires at least one provenance source')
    source_key = sources[0]['source_key']
    links: list[dict[str, Any]] = []
    for target in entity_targets:
        links.append(
            {
                'source_key': source_key,
                'entity_target': {
                    'entity_type': target['entity_type'],
                    'graph_key': target['graph_key'],
                },
                'evidence_kind': 'manual',
                'extractor_name': HARDENED_EXTRACTOR_NAME,
                'extractor_version': HARDENED_EXTRACTOR_VERSION,
                'confidence': 1.0,
            }
        )
    for target in edge_targets:
        links.append(
            {
                'source_key': source_key,
                'edge_target': {
                    'edge_type': target['edge_type'],
                    'edge_key': target['edge_key'],
                },
                'evidence_kind': 'manual',
                'extractor_name': HARDENED_EXTRACTOR_NAME,
                'extractor_version': HARDENED_EXTRACTOR_VERSION,
                'confidence': 1.0,
            }
        )
    return links


def _validate_live_id(name: str, value: str) -> str:
    if name in {'group_id', 'control_group_id'} and isinstance(value, str):
        _reject_protected_group(name, value)
    if not isinstance(value, str) or not value or len(value) > MAX_LIVE_ID_LENGTH:
        raise ValueError(f'{name} must be 1..{MAX_LIVE_ID_LENGTH} characters')
    if LIVE_ID_RE.fullmatch(value) is None:
        raise ValueError(f'{name} must use ASCII alphanumeric, dash, or underscore only')
    return value


def _reject_protected_group(name: str, value: str) -> None:
    if value.strip().casefold() in {item.casefold() for item in PROTECTED_GROUP_IDS}:
        raise ValueError(f'{name} is a protected group')


def build_hardened_payload_from_fixture(
    fixture: dict[str, Any],
    *,
    group_id: str = HARDENED_GROUP_ID,
    batch_id: str | None = None,
) -> dict[str, Any]:
    """Build one model-valid catalog-v2 prepare-shaped payload from synthetic fixture only."""
    if fixture.get('identity_schema_version') != HARDENED_IDENTITY_SCHEMA_VERSION:
        raise ValueError('fixture identity_schema_version must be catalog-v2')
    if fixture.get('system_key') != HARDENED_SYSTEM_KEY:
        raise ValueError('fixture system_key must be FE')
    entities = [dict(item) for item in fixture['entities']]
    edges = [dict(item) for item in fixture['edges']]
    provenance = dict(fixture['provenance'])
    sources = [dict(item) for item in provenance.get('sources') or []]
    if provenance.get('evidence_links'):
        evidence_links = [dict(item) for item in provenance['evidence_links']]
    else:
        evidence_links = _evidence_links_from_cartesian(
            sources,
            list(provenance.get('entity_targets') or []),
            list(provenance.get('edge_targets') or []),
        )
    fixture_digest = sha256_bytes(
        json.dumps(fixture, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode(
            'utf-8'
        )
    )
    effective_batch_id = batch_id or fixture['batch_id']
    entities, edges, sources = _with_content_hashes(entities, edges, sources)
    payload = {
        'identity_schema_version': HARDENED_IDENTITY_SCHEMA_VERSION,
        'system_key': HARDENED_SYSTEM_KEY,
        'group_id': group_id,
        'batch_id': effective_batch_id,
        'catalog_sha256': fixture_digest,
        'atomic': True,
        'entities': entities,
        'edges': edges,
        'provenance': {
            'sources': sources,
            'evidence_links': evidence_links,
        },
    }
    if set(payload) != HARDENED_PAYLOAD_FIELDS:
        raise ValueError(f'hardened payload field set mismatch: {sorted(payload)}')
    PrepareCatalogBatchRequest.model_validate(payload)
    UpsertCatalogBatchRequest.model_validate({**payload, 'dry_run': False})
    return payload


def validate_hardened_request(raw: dict[str, Any]) -> tuple[UpsertCatalogBatchRequest, str]:
    if set(raw) != HARDENED_PAYLOAD_FIELDS:
        raise ValueError(
            f'hardened top-level fields must be {sorted(HARDENED_PAYLOAD_FIELDS)}, got {sorted(raw)}'
        )
    if raw.get('identity_schema_version') != HARDENED_IDENTITY_SCHEMA_VERSION:
        raise ValueError('identity_schema_version must be catalog-v2')
    if raw.get('system_key') != HARDENED_SYSTEM_KEY:
        raise ValueError('system_key must be FE for sanitized hardened fixture')
    if raw.get('group_id') != HARDENED_GROUP_ID:
        raise ValueError('hardened offline group_id must be oracle-catalog-tool-test')
    _reject_unknown_fields(raw, UpsertCatalogBatchRequest, '$')
    for index, item in enumerate(raw['entities']):
        _reject_unknown_fields(item, CatalogEntityItem, f'$.entities[{index}]')
    for index, item in enumerate(raw['edges']):
        _reject_unknown_fields(item, CatalogEdgeItem, f'$.edges[{index}]')
    provenance = raw['provenance']
    _reject_unknown_fields(provenance, NestedProvenancePayload, '$.provenance')
    if 'entity_targets' in provenance or 'edge_targets' in provenance:
        raise ValueError('Cartesian provenance rejected; use evidence_links')
    for index, item in enumerate(provenance['sources']):
        _reject_unknown_fields(item, CatalogSourceItem, f'$.provenance.sources[{index}]')
    for index, item in enumerate(provenance['evidence_links']):
        _reject_unknown_fields(item, CatalogEvidenceLink, f'$.provenance.evidence_links[{index}]')
    model = UpsertCatalogBatchRequest.model_validate(raw)
    for item in model.entities:
        digest = canonical_sha256(CatalogService.entity_canonical_payload(item))
        if item.content_sha256 != digest:
            raise ValueError(f'{item.graph_key}: entity content hash mismatch')
    for item in model.edges:
        digest = canonical_sha256(CatalogService.edge_canonical_payload(item))
        if item.content_sha256 != digest:
            raise ValueError(f'{item.edge_key}: edge content hash mismatch')
    assert model.provenance is not None
    for item in model.provenance.sources:
        digest = canonical_sha256(CatalogService.source_canonical_payload(item))
        if item.content_sha256 != digest:
            raise ValueError(f'{item.source_key}: source content hash mismatch')
    return model, CatalogService.batch_request_sha256(model)


def _offline_prepare_receipt(
    *,
    batch_id: str,
    request_sha256: str,
    catalog_sha256: str,
    artifact_sha256: str,
    entity_count: int,
    edge_count: int,
    source_count: int,
    evidence_link_count: int,
) -> dict[str, Any]:
    return {
        'artifact_schema_version': HARDENED_ARTIFACT_SCHEMA_VERSION,
        'execution_mode': 'offline_simulation',
        'canary_executed': False,
        'tool': 'prepare_catalog_batch',
        'batch_id': batch_id,
        'plan_uuid': 'offline-plan-uuid',
        'request_sha256': request_sha256,
        'catalog_sha256': catalog_sha256,
        'artifact_sha256': artifact_sha256,
        'identity_schema_version': HARDENED_IDENTITY_SCHEMA_VERSION,
        'expires_at': '1970-01-01T00:00:00Z',
        'entity_count': entity_count,
        'edge_count': edge_count,
        'source_count': source_count,
        'evidence_link_count': evidence_link_count,
        'projected_created': 0,
        'projected_updated': 0,
        'projected_unchanged': entity_count + edge_count + source_count + evidence_link_count,
        'token_present': False,
        'notes': 'offline simulation only; raw plan_token omitted; not live server success',
    }


def _offline_commit_receipt(
    *,
    batch_id: str,
    request_sha256: str,
    catalog_sha256: str,
    artifact_sha256: str,
    entity_count: int,
    edge_count: int,
    source_count: int,
    evidence_link_count: int,
) -> dict[str, Any]:
    return {
        'artifact_schema_version': HARDENED_ARTIFACT_SCHEMA_VERSION,
        'execution_mode': 'offline_simulation',
        'canary_executed': False,
        'tool': 'commit_prepared_catalog_batch',
        'batch_id': batch_id,
        'plan_uuid': 'offline-plan-uuid',
        'request_sha256': request_sha256,
        'catalog_sha256': catalog_sha256,
        'artifact_sha256': artifact_sha256,
        'state': 'COMMITTED',
        'entity_count': entity_count,
        'edge_count': edge_count,
        'source_count': source_count,
        'evidence_link_count': evidence_link_count,
        'batch_uuid': 'offline-batch-uuid',
        'manifest_sha256': request_sha256,
        'committed_created': 0,
        'committed_updated': 0,
        'committed_unchanged': entity_count + edge_count,
        'token_present': False,
        'notes': 'offline simulation only; no transport body; not live server success',
    }


def _offline_checkpoint() -> dict[str, Any]:
    return {
        'artifact_schema_version': HARDENED_ARTIFACT_SCHEMA_VERSION,
        'execution_mode': 'offline_simulation',
        'canary_executed': False,
        'canary_attempt_count': 0,
        'validation_runs': [],
        'future_target_group_id_metadata': FUTURE_TARGET_GROUP_METADATA,
        'notes': (
            'Hardened offline checkpoint is separate from '
            'catalog/catalog.json.graphiti-canary-v2-state.json'
        ),
    }


def build_hardened(fixture_path: Path, output_dir: Path) -> dict[str, Any]:
    """Emit versioned hardened payload/manifest/receipts/checkpoint offline only."""
    fixture_raw = _validate_fixture_authority(fixture_path, exact_path=False)
    fixture = strict_json_bytes(fixture_raw, str(fixture_path))
    if not isinstance(fixture, dict):
        raise ValueError('sanitized fixture root must be an object')
    payload = build_hardened_payload_from_fixture(fixture)
    model, request_sha256 = validate_hardened_request(payload)
    assert model.provenance is not None
    payload_bytes = canonical_bytes(payload)
    artifact_sha256 = sha256_bytes(payload_bytes)
    file_name = 'accept-tab.payload.json'
    relative_payload = (HARDENED_OUTPUT_REL / file_name).as_posix()
    prepare_receipt = _offline_prepare_receipt(
        batch_id=model.batch_id,
        request_sha256=request_sha256,
        catalog_sha256=model.catalog_sha256,
        artifact_sha256=artifact_sha256,
        entity_count=len(model.entities),
        edge_count=len(model.edges),
        source_count=len(model.provenance.sources),
        evidence_link_count=len(model.provenance.evidence_links),
    )
    commit_receipt = _offline_commit_receipt(
        batch_id=model.batch_id,
        request_sha256=request_sha256,
        catalog_sha256=model.catalog_sha256,
        artifact_sha256=artifact_sha256,
        entity_count=len(model.entities),
        edge_count=len(model.edges),
        source_count=len(model.provenance.sources),
        evidence_link_count=len(model.provenance.evidence_links),
    )
    checkpoint = _offline_checkpoint()
    prepare_bytes = canonical_bytes(prepare_receipt)
    commit_bytes = canonical_bytes(commit_receipt)
    checkpoint_bytes = canonical_bytes(checkpoint)
    inventory = {
        'builder': 'scripts/build_catalog_canary_requests.py',
        'runner': 'scripts/run_catalog_canary_batch.py',
        'sanitized_fixture': SANITIZED_FIXTURE_REL.as_posix(),
        'offline_tests': 'mcp_server/tests/test_catalog_canary_scripts.py',
        'payload': relative_payload,
        'offline_prepare_receipt': (
            HARDENED_OUTPUT_REL / 'offline-prepare.receipt.json'
        ).as_posix(),
        'offline_commit_receipt': (HARDENED_OUTPUT_REL / 'offline-commit.receipt.json').as_posix(),
        'offline_checkpoint': (HARDENED_OUTPUT_REL / 'offline-checkpoint.json').as_posix(),
    }
    digests = {
        'payload': artifact_sha256,
        'offline_prepare_receipt': sha256_bytes(prepare_bytes),
        'offline_commit_receipt': sha256_bytes(commit_bytes),
        'offline_checkpoint': sha256_bytes(checkpoint_bytes),
        'sanitized_fixture': APPROVED_FIXTURE_RAW_SHA256,
    }
    manifest = {
        'artifact_schema_version': HARDENED_ARTIFACT_SCHEMA_VERSION,
        'identity_schema_version': HARDENED_IDENTITY_SCHEMA_VERSION,
        'execution_mode': 'offline_simulation',
        'canary_executed': False,
        'generated_at': _manifest_timestamp(output_dir / 'manifest.json'),
        'system_key': HARDENED_SYSTEM_KEY,
        'group_id': HARDENED_GROUP_ID,
        'future_target_group_id_metadata': FUTURE_TARGET_GROUP_METADATA,
        'preferred_tool_sequence': [
            'prepare_catalog_batch',
            'commit_prepared_catalog_batch',
            'get_catalog_ingest_status',
            'verify_catalog_batch',
            'resolve_typed_entities',
            'get_catalog_batch_manifest',
            'get_catalog_evidence',
            'search_nodes',
            'search_memory_facts',
        ],
        'inventory': inventory,
        'digests': digests,
        'batches': [
            {
                'order': 1,
                'batch_id': model.batch_id,
                'path': relative_payload,
                'artifact_sha256': artifact_sha256,
                'server_request_sha256': request_sha256,
                'counts': {
                    'entities': len(model.entities),
                    'edges': len(model.edges),
                    'provenance_sources': len(model.provenance.sources),
                    'evidence_links': len(model.provenance.evidence_links),
                },
            }
        ],
        'history': {
            'status': 'read_only_not_authority',
            'historical_dir': 'catalog/canary-v2-requests',
            'historical_summary': 'catalog/CANARY_V2_SUMMARY.md',
            'historical_checkpoint': 'catalog/catalog.json.graphiti-canary-v2-state.json',
            'historical_accept_tab_golden_server_request_sha256': ACCEPT_TAB_GOLDEN_REQUEST_SHA256,
            'historical_unique_totals': {'entities': 38, 'edges': 85},
            'historical_accept_tab_receipt_shape': '10/16/1',
            'note': 'Historical ACCEPT_TAB SHA/receipt/plan remain history only (D-05, D-11)',
        },
    }
    manifest_bytes = canonical_bytes(manifest)

    output_dir.mkdir(parents=True, exist_ok=True)
    destinations = {
        output_dir / file_name: payload_bytes,
        output_dir / 'offline-prepare.receipt.json': prepare_bytes,
        output_dir / 'offline-commit.receipt.json': commit_bytes,
        output_dir / 'offline-checkpoint.json': checkpoint_bytes,
        output_dir / 'manifest.json': manifest_bytes,
    }
    if any(not dest.exists() or dest.read_bytes() != raw for dest, raw in destinations.items()):
        _atomic_replace_set(destinations)
    for dest, raw in destinations.items():
        if dest.read_bytes() != raw:
            raise ValueError(f'{dest}: bytes changed after coherent write')
    reopened = strict_json_bytes((output_dir / file_name).read_bytes(), file_name)
    validate_hardened_request(reopened)
    return manifest


def _golden_map(directory: Path) -> dict[str, str]:
    names = {item.name for item in directory.iterdir() if item.is_file()}
    if names != set(GOLDEN_SHA256):
        raise ValueError(f'golden file set mismatch: {sorted(names)}')
    return {name: sha256_bytes((directory / name).read_bytes()) for name in sorted(names)}


def build_golden(fixture_path: Path, output_dir: Path) -> dict[str, Any]:
    """Generate in quarantine, verify five pins, then publish only identical bytes."""
    _validate_fixture_authority(fixture_path, exact_path=False)
    tracked = (REPO_ROOT / HARDENED_OUTPUT_REL).resolve()
    tracked_before = _golden_map(tracked)
    if tracked_before != GOLDEN_SHA256:
        raise ValueError('tracked Phase 5 golden authority differs from reviewed pins')
    tracked_manifest = strict_load(tracked / 'manifest.json')
    if not isinstance(tracked_manifest, dict):
        raise ValueError('golden manifest root must be an object')
    with tempfile.TemporaryDirectory(prefix='graphiti-canary-golden-') as temporary:
        generated = Path(temporary)
        _atomic_write_missing(
            generated / 'manifest.json',
            canonical_bytes({'generated_at': tracked_manifest['generated_at']}),
        )
        manifest = build_hardened(fixture_path, generated)
        generated_map = _golden_map(generated)
        if generated_map != GOLDEN_SHA256:
            raise ValueError('generated Phase 5 golden bytes differ from reviewed pins')
        generated_bytes = {name: (generated / name).read_bytes() for name in GOLDEN_SHA256}
    if _golden_map(tracked) != tracked_before:
        raise ValueError('tracked Phase 5 golden authority changed during generation')
    destination = output_dir.resolve()
    if destination == tracked:
        return manifest
    destination.mkdir(parents=True, exist_ok=True)
    existing = {item.name for item in destination.iterdir() if item.is_file()}
    if existing - set(GOLDEN_SHA256):
        raise FileExistsError('refusing golden output directory containing unexpected files')
    for name, raw in generated_bytes.items():
        _atomic_write_missing(destination / name, raw)
    if _golden_map(destination) != GOLDEN_SHA256:
        raise ValueError('published golden output differs from reviewed pins')
    return manifest


def build_live_canary(
    fixture_path: Path,
    output_dir: Path,
    *,
    run_id: str,
    group_id: str,
    control_group_id: str,
    batch_id: str,
) -> dict[str, Any]:
    """Build one deterministic live-canary request without transport or secret material."""
    identities = {
        name: _validate_live_id(name, value)
        for name, value in {
            'run_id': run_id,
            'group_id': group_id,
            'control_group_id': control_group_id,
            'batch_id': batch_id,
        }.items()
    }
    _reject_protected_group('group_id', identities['group_id'])
    _reject_protected_group('control_group_id', identities['control_group_id'])
    if identities['control_group_id'] == identities['group_id']:
        raise ValueError('control_group_id must differ from group_id')
    expected_group = f'oracle-catalog-v2-canary-{identities["run_id"]}'
    expected_batch = f'accept-tab-catalog-v2-canary-{identities["run_id"]}'
    if identities['group_id'] != expected_group:
        raise ValueError('group_id must equal oracle-catalog-v2-canary-<run_id>')
    if identities['control_group_id'] != f'{expected_group}-empty-control':
        raise ValueError('control_group_id must equal group_id + -empty-control')
    if identities['batch_id'] != expected_batch:
        raise ValueError('batch_id must equal accept-tab-catalog-v2-canary-<run_id>')

    resolved_output = output_dir.resolve()
    hardened = (REPO_ROOT / HARDENED_OUTPUT_REL).resolve()
    historical = (REPO_ROOT / 'catalog' / 'canary-v2-requests').resolve()
    if any(
        resolved_output == root or root in resolved_output.parents
        for root in (hardened, historical)
    ):
        raise ValueError(
            'live output directory must not be a tracked golden or historical directory'
        )

    fixture_raw = _validate_fixture_authority(fixture_path, exact_path=True)
    fixture = strict_json_bytes(fixture_raw, str(fixture_path))
    if not isinstance(fixture, dict):
        raise ValueError('sanitized fixture root must be an object')
    payload = build_hardened_payload_from_fixture(
        fixture,
        group_id=identities['group_id'],
        batch_id=identities['batch_id'],
    )
    model = UpsertCatalogBatchRequest.model_validate({**payload, 'dry_run': True}, strict=True)
    request_sha256 = CatalogService.batch_request_sha256(model)
    payload_bytes = canonical_bytes(payload)
    artifact_sha256 = sha256_bytes(payload_bytes)
    builder_source = Path(__file__).read_bytes()
    builder_sha256 = lf_sha256(builder_source)
    assert model.provenance is not None
    manifest = {
        'artifact_schema_version': LIVE_ARTIFACT_SCHEMA_VERSION,
        'profile': 'live-canary',
        'run_id': identities['run_id'],
        'group_id': identities['group_id'],
        'control_group_id': identities['control_group_id'],
        'batch_id': identities['batch_id'],
        'identity_schema_version': model.identity_schema_version,
        'system_key': model.system_key,
        'fixture': SANITIZED_FIXTURE_REL.as_posix(),
        'fixture_sha256': APPROVED_FIXTURE_RAW_SHA256,
        'fixture_lf_sha256': APPROVED_FIXTURE_LF_SHA256,
        'catalog_sha256': model.catalog_sha256,
        'request_sha256': request_sha256,
        'artifact_sha256': artifact_sha256,
        'payload': LIVE_PAYLOAD_NAME,
        'counts': {
            'entities': len(model.entities),
            'edges': len(model.edges),
            'sources': len(model.provenance.sources),
            'evidence_links': len(model.provenance.evidence_links),
        },
        'builder': 'scripts/build_catalog_canary_requests.py',
        'builder_sha256': builder_sha256,
        'canary_executed': False,
    }
    if set(manifest) != LIVE_MANIFEST_FIELDS:
        raise ValueError('live manifest field set mismatch')
    destinations = {
        resolved_output / LIVE_PAYLOAD_NAME: payload_bytes,
        resolved_output / LIVE_MANIFEST_NAME: canonical_bytes(manifest),
    }
    if resolved_output.exists():
        existing = {path.name for path in resolved_output.iterdir()}
        if existing - {LIVE_PAYLOAD_NAME, LIVE_MANIFEST_NAME}:
            raise FileExistsError('refusing live output directory containing unexpected files')
    resolved_output.mkdir(parents=True, exist_ok=True)
    differing = [
        path for path, raw in destinations.items() if path.exists() and path.read_bytes() != raw
    ]
    if differing:
        raise FileExistsError(
            'refusing to overwrite differing files: ' + ', '.join(str(path) for path in differing)
        )
    if Path(__file__).read_bytes() != builder_source:
        raise ValueError('builder source changed during artifact construction')
    for path, raw in destinations.items():
        _atomic_write_missing(path, raw)
    if Path(__file__).read_bytes() != builder_source:
        raise ValueError('builder source changed during artifact publication')
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('golden', 'live-canary'))
    parser.add_argument('--mode', choices=('historical', 'hardened'))
    parser.add_argument('--catalog', type=Path, default=REPO_ROOT / 'catalog' / 'catalog.json')
    parser.add_argument('--fixture', type=Path, default=REPO_ROOT / SANITIZED_FIXTURE_REL)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--group-id')
    parser.add_argument('--control-group-id')
    parser.add_argument('--batch-id')
    args = parser.parse_args(argv)
    if args.profile is not None and args.mode is not None:
        parser.error('--profile and --mode are mutually exclusive')
    args.mode = args.mode or 'hardened'
    args.profile = args.profile or ('golden' if args.mode == 'hardened' else 'historical')
    if args.profile == 'live-canary':
        missing = [
            name
            for name in ('run_id', 'group_id', 'control_group_id', 'batch_id', 'output_dir')
            if getattr(args, name) is None
        ]
        if missing:
            parser.error(
                'live-canary requires: '
                + ', '.join('--' + name.replace('_', '-') for name in missing)
            )
    return args


def main() -> int:
    args = parse_args()
    if args.profile == 'golden':
        output = args.output_dir or (REPO_ROOT / HARDENED_OUTPUT_REL)
        manifest = build_golden(args.fixture.resolve(), output.resolve())
    elif args.profile == 'historical':
        output = args.output_dir or (REPO_ROOT / 'catalog' / 'canary-v2-requests')
        manifest = verify_historical(output.resolve())
    else:
        manifest = build_live_canary(
            args.fixture.resolve(),
            args.output_dir.resolve(),
            run_id=args.run_id,
            group_id=args.group_id,
            control_group_id=args.control_group_id,
            batch_id=args.batch_id,
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
