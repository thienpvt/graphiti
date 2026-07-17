import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[2] / 'catalog' / 'catalog.json'

duplicate_json_keys: list[str] = []


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            duplicate_json_keys.append(key)
        result[key] = value
    return result


raw = CATALOG.read_bytes()
data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=reject_duplicate_keys, strict=True)
documents = data.get('documents') or []
tables = data.get('tables') or []
relationships = data.get('relationships') or []
document_ids = [document.get('document_id') for document in documents]
document_id_set = set(document_ids)

fatal_errors = []
item_errors = []
warnings = []
quarantined = []

if duplicate_json_keys:
    fatal_errors.append({'kind': 'duplicate_json_keys', 'keys': duplicate_json_keys})
if any(not document_id for document_id in documents):
    fatal_errors.append({'kind': 'missing_document_id'})
for document_id, count in Counter(document_ids).items():
    if count > 1:
        fatal_errors.append({'kind': 'duplicate_document_id', 'id': document_id, 'count': count})

table_ids = [table.get('id') for table in tables]
if any(not table_id for table_id in table_ids):
    fatal_errors.append({'kind': 'missing_table_id'})
for table_id, count in Counter(table_ids).items():
    if count > 1:
        fatal_errors.append({'kind': 'duplicate_table_id', 'id': table_id, 'count': count})


def reference_key(reference):
    return (
        reference.get('document_id'),
        reference.get('page'),
        reference.get('raw_text'),
    )


source_ref_stats = Counter()
source_ref_issues = []


def validate_source_refs(kind, object_id, refs, enclosing_document_id=None):
    if not isinstance(refs, list) or not refs:
        source_ref_issues.append({'kind': kind, 'id': object_id, 'error': 'empty_source_refs'})
        return []
    seen = set()
    normalized = []
    for position, reference in enumerate(refs):
        source_ref_stats['total'] += 1
        if not isinstance(reference, dict):
            source_ref_issues.append(
                {'kind': kind, 'id': object_id, 'error': 'invalid_source_ref', 'position': position}
            )
            continue
        document_id = reference.get('document_id', enclosing_document_id)
        page = reference.get('page')
        raw_text = reference.get('raw_text')
        if (
            document_id not in document_id_set
            or not isinstance(page, int)
            or page < 1
            or not isinstance(raw_text, str)
        ):
            source_ref_issues.append(
                {
                    'kind': kind,
                    'id': object_id,
                    'error': 'invalid_source_ref',
                    'position': position,
                    'document_id': document_id,
                    'page': page,
                    'raw_text_type': type(raw_text).__name__,
                }
            )
            continue
        if raw_text == '':
            source_ref_stats['empty_raw_text'] += 1
        key = reference_key(reference)
        if key in seen:
            source_ref_stats['exact_duplicates'] += 1
            continue
        seen.add(key)
        normalized.append(reference)
    return normalized


for document in documents:
    validate_source_refs(
        'document',
        document.get('document_id'),
        document.get('source_refs'),
        document.get('document_id'),
    )

canonical_tables = {}
tables_by_unqualified_name = defaultdict(list)
table_documents = {}
document_schemas = defaultdict(set)
column_count = 0
columns_with_source_refs = 0
column_document_edges = set()
table_document_edges = set()

for table in tables:
    table_id = table.get('id')
    schema = table.get('schema')
    canonical_name = table.get('name_canonical')
    expected_id = f'{schema}.{canonical_name}' if schema and canonical_name else None
    if table_id != expected_id:
        fatal_errors.append(
            {'kind': 'conflicting_table_identifier', 'id': table_id, 'expected': expected_id}
        )
    if table_id:
        canonical_tables[table_id] = table
    tables_by_unqualified_name[canonical_name].append(table)
    table_refs = validate_source_refs('table', table_id, table.get('source_refs'))
    table_doc_ids = sorted({ref['document_id'] for ref in table_refs})
    table_documents[table_id] = table_doc_ids
    if not table_doc_ids:
        item_errors.append({'kind': 'table_without_resolved_document', 'id': table_id})
    for document_id in table_doc_ids:
        document_schemas[document_id].add(schema)
        table_document_edges.add((table_id, document_id))

    names = [column.get('name_canonical') for column in table.get('columns') or []]
    duplicates = [name for name, count in Counter(names).items() if count > 1]
    if duplicates:
        fatal_errors.append(
            {'kind': 'duplicate_columns_within_table', 'table_id': table_id, 'columns': duplicates}
        )
    for column in table.get('columns') or []:
        column_count += 1
        column_name = column.get('name_canonical')
        if not column_name:
            item_errors.append({'kind': 'missing_column_name', 'table_id': table_id})
            continue
        column_id = f'{table_id}.{column_name}'
        column_refs = validate_source_refs('column', column_id, column.get('source_refs'))
        if column_refs:
            columns_with_source_refs += 1
            for document_id in sorted({ref['document_id'] for ref in column_refs}):
                column_document_edges.add((column_id, document_id))

    for primary_key in table.get('primary_keys') or []:
        validate_source_refs(
            'primary_key',
            f'{schema}.{primary_key.get("name_canonical")}',
            primary_key.get('source_refs'),
        )
    for constraint in table.get('constraints') or []:
        validate_source_refs(
            'constraint',
            f'{schema}.{constraint.get("name_canonical")}',
            constraint.get('source_refs'),
        )
    for index in table.get('indexes') or []:
        validate_source_refs(
            'index', f'{schema}.{index.get("name_canonical")}', index.get('source_refs')
        )

for relationship in relationships:
    validate_source_refs('relationship', relationship.get('id'), relationship.get('source_refs'))

if source_ref_issues:
    item_errors.extend(source_ref_issues)
if source_ref_stats['empty_raw_text']:
    warnings.append(
        {
            'kind': 'empty_raw_text_preserved',
            'count': source_ref_stats['empty_raw_text'],
            'scope': 'source_refs',
        }
    )
if source_ref_stats['exact_duplicates']:
    warnings.append(
        {
            'kind': 'exact_duplicate_source_refs_deduplicated',
            'count': source_ref_stats['exact_duplicates'],
        }
    )


def canonical_columns(items):
    return tuple(item.get('name_canonical') for item in (items or []))


constraint_representations = defaultdict(list)
index_representations = defaultdict(list)

for table in tables:
    schema = table['schema']
    table_id = table['id']
    for primary_key in table.get('primary_keys') or []:
        constraint_id = f'{schema}.{primary_key.get("name_canonical")}'
        constraint_representations[constraint_id].append(
            {
                'table_id': table_id,
                'type': 'PRIMARY_KEY',
                'columns': canonical_columns(primary_key.get('columns')),
                'origin': 'primary_keys',
            }
        )
    for constraint in table.get('constraints') or []:
        constraint_type = constraint.get('constraint_type')
        object_id = f'{schema}.{constraint.get("name_canonical")}'
        representation = {
            'table_id': table_id,
            'type': constraint_type,
            'columns': canonical_columns(constraint.get('columns')),
            'origin': 'constraints',
        }
        if constraint_type == 'INDEX':
            index_representations[object_id].append(representation)
        else:
            constraint_representations[object_id].append(representation)
    for index in table.get('indexes') or []:
        index_id = f'{schema}.{index.get("name_canonical")}'
        index_representations[index_id].append(
            {
                'table_id': table_id,
                'type': 'INDEX',
                'columns': canonical_columns(index.get('columns')),
                'origin': 'indexes',
            }
        )


def representation_signature(representation):
    return (
        representation['table_id'],
        representation['type'],
        representation['columns'],
    )


for constraint_id, representations in constraint_representations.items():
    physical = {
        (representation['table_id'], representation['type'], representation['columns'])
        for representation in representations
    }
    types = {representation['type'] for representation in representations}
    if types == {'PRIMARY_KEY'}:
        physical = {
            (representation['table_id'], 'PRIMARY_KEY', representation['columns'])
            for representation in representations
        }
    if len(physical) > 1:
        fatal_errors.append(
            {
                'kind': 'conflicting_constraint_identifier',
                'id': constraint_id,
                'representations': [
                    {
                        **representation,
                        'columns': list(representation['columns']),
                    }
                    for representation in representations
                ],
            }
        )

for index_id, representations in index_representations.items():
    physical = {
        (representation['table_id'], representation['columns'])
        for representation in representations
    }
    if len(physical) > 1:
        fatal_errors.append(
            {
                'kind': 'conflicting_index_identifier',
                'id': index_id,
                'representations': [
                    {
                        **representation,
                        'columns': list(representation['columns']),
                    }
                    for representation in representations
                ],
            }
        )

constraint_objects = {}
for constraint_id, representations in constraint_representations.items():
    first = representations[0]
    constraint_objects[constraint_id] = {
        'id': constraint_id,
        'table_id': first['table_id'],
        'type': first['type'],
        'columns': first['columns'],
        'origins': sorted({representation['origin'] for representation in representations}),
    }

index_objects = {}
for index_id, representations in index_representations.items():
    first = representations[0]
    index_objects[index_id] = {
        'id': index_id,
        'table_id': first['table_id'],
        'columns': first['columns'],
        'origins': sorted({representation['origin'] for representation in representations}),
    }

constraint_column_edges = set()
primary_key_edges = set()
constraint_type_counts = Counter()
for constraint in constraint_objects.values():
    constraint_type_counts[constraint['type']] += 1
    table = canonical_tables.get(constraint['table_id'])
    if not table:
        item_errors.append({'kind': 'constraint_table_missing', 'id': constraint['id']})
        continue
    table_columns = {column['name_canonical'] for column in table.get('columns') or []}
    unresolved = [name for name in constraint['columns'] if name not in table_columns]
    if unresolved:
        item_errors.append(
            {'kind': 'constraint_columns_unresolved', 'id': constraint['id'], 'columns': unresolved}
        )
    for column_name in constraint['columns']:
        if column_name in table_columns:
            constraint_column_edges.add(
                (constraint['id'], f'{constraint["table_id"]}.{column_name}')
            )
    if constraint['type'] == 'PRIMARY_KEY':
        primary_key_edges.add((constraint['id'], constraint['table_id']))

index_column_edges = set()
for index in index_objects.values():
    table = canonical_tables.get(index['table_id'])
    if not table:
        item_errors.append({'kind': 'index_table_missing', 'id': index['id']})
        continue
    table_columns = {column['name_canonical'] for column in table.get('columns') or []}
    unresolved = [name for name in index['columns'] if name not in table_columns]
    if unresolved:
        item_errors.append(
            {'kind': 'index_columns_unresolved', 'id': index['id'], 'columns': unresolved}
        )
    for position, column_name in enumerate(index['columns'], 1):
        if column_name in table_columns:
            index_column_edges.add((index['id'], f'{index["table_id"]}.{column_name}', position))

relationship_ids = [relationship.get('id') for relationship in relationships]
for relationship_id, count in Counter(relationship_ids).items():
    if count > 1:
        fatal_errors.append(
            {'kind': 'duplicate_relationship_id', 'id': relationship_id, 'count': count}
        )


def resolve_table(endpoint, relationship):
    if endpoint in canonical_tables:
        return canonical_tables[endpoint], None
    if not isinstance(endpoint, str) or not endpoint:
        return None, 'missing_endpoint'
    if '.' in endpoint:
        return None, 'unresolved_qualified_endpoint'
    relationship_documents = {
        ref.get('document_id')
        for ref in relationship.get('source_refs') or []
        if isinstance(ref, dict) and ref.get('document_id') in document_id_set
    }
    candidates = [
        table
        for table in tables_by_unqualified_name.get(endpoint, [])
        if relationship_documents.intersection(table_documents.get(table['id'], []))
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, 'unresolved_unqualified_endpoint'
    return None, 'ambiguous_unqualified_endpoint'


foreign_key_edges = []
accepted_fk_relationships = []
related_constraint_missing = []
unknown_cardinality = 0
for relationship in relationships:
    relationship_id = relationship.get('id')
    relationship_type = relationship.get('relationship_type')
    if relationship_type != 'DOCUMENTED_FOREIGN_KEY':
        quarantined.append(
            {
                'id': relationship_id,
                'reason': 'relationship_type_has_no_unambiguous_edge_mapping',
                'relationship_type': relationship_type,
            }
        )
        continue
    from_table, from_error = resolve_table(relationship.get('from_table'), relationship)
    to_table, to_error = resolve_table(relationship.get('to_table'), relationship)
    if from_error or to_error:
        quarantined.append(
            {
                'id': relationship_id,
                'reason': 'unresolved_or_ambiguous_table_endpoint',
                'from_error': from_error,
                'to_error': to_error,
                'from_table': relationship.get('from_table'),
                'to_table': relationship.get('to_table'),
            }
        )
        continue
    from_columns = relationship.get('from_columns')
    to_columns = relationship.get('to_columns')
    if (
        not isinstance(from_columns, list)
        or not isinstance(to_columns, list)
        or not from_columns
        or len(from_columns) != len(to_columns)
    ):
        quarantined.append(
            {
                'id': relationship_id,
                'reason': 'unequal_or_empty_column_endpoint_counts',
                'from_count': len(from_columns or []),
                'to_count': len(to_columns or []),
            }
        )
        continue
    from_names = {column['name_canonical'] for column in from_table.get('columns') or []}
    to_names = {column['name_canonical'] for column in to_table.get('columns') or []}
    unresolved_from = [
        column.get('name_canonical')
        for column in from_columns
        if column.get('name_canonical') not in from_names
    ]
    unresolved_to = [
        column.get('name_canonical')
        for column in to_columns
        if column.get('name_canonical') not in to_names
    ]
    if unresolved_from or unresolved_to:
        quarantined.append(
            {
                'id': relationship_id,
                'reason': 'unresolved_column_endpoint',
                'from_table_id': from_table['id'],
                'to_table_id': to_table['id'],
                'unresolved_from_columns': unresolved_from,
                'unresolved_to_columns': unresolved_to,
            }
        )
        continue
    accepted_fk_relationships.append(relationship_id)
    cardinality = relationship.get('cardinality') or {}
    if cardinality.get('from') is None or cardinality.get('to') is None:
        unknown_cardinality += 1
    related_constraint = relationship.get('related_constraint')
    related_constraint_id = (
        f'{from_table["schema"]}.{related_constraint}' if related_constraint else None
    )
    if related_constraint_id and related_constraint_id not in constraint_objects:
        related_constraint_missing.append(
            {'relationship_id': relationship_id, 'constraint_id': related_constraint_id}
        )
    for from_column, to_column in zip(from_columns, to_columns, strict=True):
        foreign_key_edges.append(
            {
                'relationship_id': relationship_id,
                'source': f'{from_table["id"]}.{from_column["name_canonical"]}',
                'target': f'{to_table["id"]}.{to_column["name_canonical"]}',
            }
        )

if unknown_cardinality:
    warnings.append(
        {
            'kind': 'unknown_cardinality_preserved',
            'count': unknown_cardinality,
            'scope': 'accepted_documented_foreign_keys',
        }
    )
if related_constraint_missing:
    warnings.append(
        {
            'kind': 'related_constraint_not_found_no_node_invented',
            'count': len(related_constraint_missing),
            'items': related_constraint_missing,
        }
    )

normalization_notes = sum(len(table.get('normalization_notes') or []) for table in tables)
normalization_notes += sum(
    len(column.get('normalization_notes') or [])
    for table in tables
    for column in table.get('columns') or []
)
normalization_notes += sum(
    len(relationship.get('normalization_notes') or []) for relationship in relationships
)
catalog_warnings = len(data.get('warnings') or [])
nested_warnings = sum(len(table.get('warnings') or []) for table in tables)
nested_warnings += sum(
    len(column.get('warnings') or []) for table in tables for column in table.get('columns') or []
)
nested_warnings += sum(
    len(constraint.get('warnings') or [])
    for table in tables
    for constraint in table.get('constraints') or []
)
nested_warnings += sum(len(relationship.get('warnings') or []) for relationship in relationships)
if catalog_warnings or nested_warnings:
    warnings.append(
        {
            'kind': 'catalog_supplied_warnings_preserved',
            'top_level': catalog_warnings,
            'nested': nested_warnings,
        }
    )

schema_document_edges = {
    (schema, document_id) for document_id, schemas in document_schemas.items() for schema in schemas
}
schema_table_edges = {(table['schema'], table['id']) for table in tables}
table_column_edges = {
    (table['id'], f'{table["id"]}.{column["name_canonical"]}')
    for table in tables
    for column in table.get('columns') or []
}
table_constraint_edges = {
    (constraint['table_id'], constraint['id']) for constraint in constraint_objects.values()
}
table_index_edges = {(index['table_id'], index['id']) for index in index_objects.values()}

largest_tables = []
for table in tables:
    size = len(
        json.dumps(table, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    )
    largest_tables.append((size, len(table.get('columns') or []), table['id']))
largest_tables.sort(reverse=True)

semantic_calls = len(documents) + len(tables)
triplet_categories = {
    'schema_documented_by_document': len(schema_document_edges),
    'schema_contains_table': len(schema_table_edges),
    'table_contains_column': len(table_column_edges),
    'table_contains_constraint': len(table_constraint_edges),
    'constraint_contains_column': len(constraint_column_edges),
    'primary_key_of': len(primary_key_edges),
    'table_contains_index': len(table_index_edges),
    'index_contains_column': len(index_column_edges),
    'table_documented_by_document': len(table_document_edges),
    'column_documented_by_document': len(column_document_edges),
    'foreign_key_to': len(foreign_key_edges),
}
planned_triplet_calls = sum(triplet_categories.values())

result = {
    'file': {
        'bytes': len(raw),
        'utf8_bom': raw.startswith(b'\xef\xbb\xbf'),
        'sha256': hashlib.sha256(raw).hexdigest(),
        'mechanical_repair_required': False,
    },
    'strict_json': {
        'parsed': True,
        'duplicate_keys': duplicate_json_keys,
        'top_level_keys': list(data),
        'schema_version': data.get('schema_version'),
    },
    'counts': {
        'documents': len(documents),
        'schemas': len({table.get('schema') for table in tables}),
        'tables': len(tables),
        'columns': column_count,
        'constraints_after_merge': len(constraint_objects),
        'constraint_types': dict(sorted(constraint_type_counts.items())),
        'indexes_after_merge': len(index_objects),
        'relationships': len(relationships),
        'accepted_documented_fk_relationships': len(accepted_fk_relationships),
        'accepted_documented_fk_column_pairs': len(foreign_key_edges),
        'quarantined_relationships': len(quarantined),
        'columns_with_source_refs': columns_with_source_refs,
        'normalization_notes': normalization_notes,
    },
    'document_schemas': {key: sorted(value) for key, value in document_schemas.items()},
    'source_refs': dict(source_ref_stats),
    'fatal_errors': fatal_errors,
    'item_errors': item_errors,
    'warnings': warnings,
    'quarantined_relationships': quarantined,
    'largest_table_payloads': [
        {'bytes': size, 'columns': columns, 'table_id': table_id}
        for size, columns, table_id in largest_tables[:10]
    ],
    'planned_writes_if_empty_baseline': {
        'add_memory': semantic_calls,
        'add_triplet': planned_triplet_calls,
        'total': semantic_calls + planned_triplet_calls,
        'triplet_categories': triplet_categories,
    },
    'representative': {
        'document': f'DOC::{documents[0]["document_id"]}' if documents else None,
        'schema': tables[0]['schema'] if tables else None,
        'table': tables[0]['id'] if tables else None,
        'first_column': (
            f'{tables[0]["id"]}.{tables[0]["columns"][0]["name_canonical"]}'
            if tables and tables[0].get('columns')
            else None
        ),
        'first_constraint': next(iter(constraint_objects), None),
        'first_index': next(iter(index_objects), None),
        'first_fk': foreign_key_edges[0] if foreign_key_edges else None,
    },
}
print(json.dumps(result, ensure_ascii=False, indent=2))
