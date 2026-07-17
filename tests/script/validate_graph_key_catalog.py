import hashlib
import json
from collections import defaultdict
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[2] / 'catalog' / 'catalog.json'
data = json.loads(CATALOG.read_text(encoding='utf-8'))


def graph_key(entity_type, database_name):
    prefixes = {
        'DictionaryDocument': 'DOC',
        'Schema': 'SCHEMA',
        'Table': 'TABLE',
        'View': 'VIEW',
        'Column': 'COLUMN',
        'Constraint': 'CONSTRAINT',
        'Index': 'INDEX',
        'Package': 'PACKAGE',
        'Procedure': 'PROCEDURE',
        'Function': 'FUNCTION',
        'Trigger': 'TRIGGER',
    }
    if entity_type == 'DictionaryDocument':
        return f'DOC::{database_name}'
    return f'{prefixes[entity_type]}::{database_name}'


def colnames(items):
    return tuple(item.get('name_canonical') for item in items or [])


entities = []
merge_report = {'primary_key_merges': [], 'index_merges': [], 'unmatched_index_constraints': []}
for document in data['documents']:
    entities.append(
        {
            'entity_type': 'DictionaryDocument',
            'graph_key': graph_key('DictionaryDocument', document['document_id']),
            'database_qualified_name': document['document_id'],
            'origin': 'documents',
        }
    )

for schema in sorted({table['schema'] for table in data['tables']}):
    entities.append(
        {
            'entity_type': 'Schema',
            'graph_key': graph_key('Schema', schema),
            'database_qualified_name': schema,
            'origin': 'tables.schema',
        }
    )

for table in data['tables']:
    table_name = table['id']
    entities.append(
        {
            'entity_type': 'Table',
            'graph_key': graph_key('Table', table_name),
            'database_qualified_name': table_name,
            'origin': 'tables',
        }
    )
    for column in table['columns']:
        database_name = f'{table_name}.{column["name_canonical"]}'
        entities.append(
            {
                'entity_type': 'Column',
                'graph_key': graph_key('Column', database_name),
                'database_qualified_name': database_name,
                'origin': 'columns',
            }
        )

    primary_keys = defaultdict(list)
    for item in table['primary_keys']:
        primary_keys[item['name_canonical']].append(('primary_keys', item))
    for item in table['constraints']:
        if item['constraint_type'] == 'PRIMARY_KEY':
            primary_keys[item['name_canonical']].append(('constraints', item))
    merged_primary_key_names = set()
    for name, representations in primary_keys.items():
        signatures = {colnames(item['columns']) for _, item in representations}
        if len(signatures) == 1:
            merged_primary_key_names.add(name)
            if len(representations) > 1:
                merge_report['primary_key_merges'].append(
                    {'table': table_name, 'name': name, 'representations': len(representations)}
                )
        else:
            for origin, item in representations:
                entities.append(
                    {
                        'entity_type': 'Constraint',
                        'graph_key': graph_key('Constraint', f'{table["schema"]}.{name}'),
                        'database_qualified_name': f'{table["schema"]}.{name}',
                        'origin': origin,
                        'signature': colnames(item['columns']),
                    }
                )
    for name in merged_primary_key_names:
        entities.append(
            {
                'entity_type': 'Constraint',
                'graph_key': graph_key('Constraint', f'{table["schema"]}.{name}'),
                'database_qualified_name': f'{table["schema"]}.{name}',
                'origin': 'merged_primary_key',
            }
        )

    for item in table['constraints']:
        if item['constraint_type'] in {'PRIMARY_KEY', 'INDEX'}:
            continue
        database_name = f'{table["schema"]}.{item["name_canonical"]}'
        entities.append(
            {
                'entity_type': 'Constraint',
                'graph_key': graph_key('Constraint', database_name),
                'database_qualified_name': database_name,
                'origin': 'constraints',
                'constraint_type': item['constraint_type'],
            }
        )

    explicit_indexes = {
        (item['name_canonical'], frozenset(colnames(item['columns']))): item
        for item in table['indexes']
    }
    emitted_indexes = set()
    for item in table['indexes']:
        database_name = f'{table["schema"]}.{item["name_canonical"]}'
        entities.append(
            {
                'entity_type': 'Index',
                'graph_key': graph_key('Index', database_name),
                'database_qualified_name': database_name,
                'origin': 'indexes',
                'explicit_column_order': colnames(item['columns']),
            }
        )
        emitted_indexes.add(item['name_canonical'])
    for item in table['constraints']:
        if item['constraint_type'] != 'INDEX':
            continue
        key = (item['name_canonical'], frozenset(colnames(item['columns'])))
        if key in explicit_indexes:
            merge_report['index_merges'].append(
                {
                    'table': table_name,
                    'name': item['name_canonical'],
                    'explicit_index_order': colnames(explicit_indexes[key]['columns']),
                    'constraint_column_order': colnames(item['columns']),
                }
            )
            continue
        merge_report['unmatched_index_constraints'].append(
            {
                'table': table_name,
                'name': item['name_canonical'],
                'columns': colnames(item['columns']),
            }
        )
        if item['name_canonical'] not in emitted_indexes:
            database_name = f'{table["schema"]}.{item["name_canonical"]}'
            entities.append(
                {
                    'entity_type': 'Index',
                    'graph_key': graph_key('Index', database_name),
                    'database_qualified_name': database_name,
                    'origin': 'unmatched_index_constraint',
                }
            )
            emitted_indexes.add(item['name_canonical'])

by_graph_key = defaultdict(list)
by_database_name = defaultdict(list)
for entity in entities:
    by_graph_key[entity['graph_key']].append(entity)
    by_database_name[entity['database_qualified_name']].append(entity)

same_key_same_type = []
same_key_different_type = []
for key, items in by_graph_key.items():
    types = {item['entity_type'] for item in items}
    if len(items) > 1:
        record = {
            'graph_key': key,
            'entity_types': sorted(types),
            'origins': [item['origin'] for item in items],
        }
        if len(types) == 1:
            same_key_same_type.append(record)
        else:
            same_key_different_type.append(record)

valid_namespace_overlap = []
for database_name, items in by_database_name.items():
    types = sorted({item['entity_type'] for item in items})
    if len(types) > 1:
        valid_namespace_overlap.append(
            {
                'database_qualified_name': database_name,
                'entity_types': types,
                'graph_keys': sorted({item['graph_key'] for item in items}),
            }
        )

specific_keys = {
    'index': 'INDEX::SVFE_SHB.T_PRE_AUTH_TXN_TYPE_UK4',
    'constraint': 'CONSTRAINT::SVFE_SHB.T_PRE_AUTH_TXN_TYPE_UK4',
}
specific = {name: by_graph_key.get(key, []) for name, key in specific_keys.items()}

result = {
    'catalog_sha256': hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
    'entity_count_after_merge': len(entities),
    'unique_graph_keys': len(by_graph_key),
    'same_graph_key_same_entity_type': same_key_same_type,
    'same_database_qualified_name_different_entity_types': valid_namespace_overlap,
    'same_graph_key_different_entity_types': same_key_different_type,
    'merge_counts': {
        'primary_key_merges': len(merge_report['primary_key_merges']),
        'index_merges': len(merge_report['index_merges']),
        'unmatched_index_constraints': len(merge_report['unmatched_index_constraints']),
    },
    'unmatched_index_constraints': merge_report['unmatched_index_constraints'],
    'specific_verification': {
        'index_graph_key': specific_keys['index'],
        'index_entities': specific['index'],
        'constraint_graph_key': specific_keys['constraint'],
        'constraint_entities': specific['constraint'],
        'valid_distinct_entities': bool(specific['index'])
        and bool(specific['constraint'])
        and specific_keys['index'] != specific_keys['constraint'],
        'index_constraint_representation_merged_count': sum(
            item['name'] == 'T_PRE_AUTH_TXN_TYPE_UK4'
            and item['table'] == 'SVFE_SHB.T_PRE_AUTH_TXN_TYPE'
            for item in merge_report['index_merges']
        ),
    },
    'fatal_conflicts': same_key_different_type,
}
print(json.dumps(result, ensure_ascii=False, indent=2, default=list))
