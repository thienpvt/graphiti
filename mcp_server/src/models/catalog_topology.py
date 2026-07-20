"""Server-owned endpoint-pair authority for catalog edge types.

Pure allowlist — no I/O, no client-supplied map, no store/Cypher.
"""

from __future__ import annotations

from models.catalog_common import CATALOG_ENTITY_TYPES, CatalogErrorCode

_CONTAINS_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ('System', 'Database'),
        ('Database', 'Schema'),
        ('Database', 'DatabaseLink'),
        *{
            ('Schema', t)
            for t in (
                'Table',
                'View',
                'MaterializedView',
                'Package',
                'Procedure',
                'Function',
                'Trigger',
                'Sequence',
                'Synonym',
                'Index',
                'Constraint',
                'SourceArtifact',
            )
        },
        ('Table', 'Column'),
        ('View', 'Column'),
        ('MaterializedView', 'Column'),
        ('Package', 'Procedure'),
        ('Package', 'Function'),
        ('DictionaryDocument', 'SourceArtifact'),
    }
)

_CODE_SOURCES = ('Procedure', 'Function', 'Trigger', 'Package')
_CALL_TARGETS = ('Procedure', 'Function', 'Package')
_READ_SOURCES = (
    'Procedure',
    'Function',
    'Trigger',
    'Package',
    'View',
    'MaterializedView',
)
_READ_TARGETS = ('Table', 'View', 'MaterializedView', 'Column', 'Synonym')
_WRITE_TARGETS = ('Table', 'Column', 'View', 'MaterializedView', 'Synonym')
_JOIN_TYPES = ('Table', 'View', 'MaterializedView', 'Column')
_REF_SOURCES = ('Package', 'Procedure', 'Function', 'Trigger', 'SourceArtifact')
_REF_TARGETS = (
    'Table',
    'View',
    'MaterializedView',
    'Column',
    'Sequence',
    'Synonym',
    'Package',
    'Procedure',
    'Function',
)
_DERIVED_SOURCES = ('View', 'MaterializedView', 'SourceArtifact')
_DERIVED_TARGETS = ('Table', 'View', 'MaterializedView', 'Column', 'SourceArtifact')
_SEQ_SOURCES = (
    'Procedure',
    'Function',
    'Trigger',
    'Package',
    'View',
    'MaterializedView',
)
_SYN_TARGETS = (
    'Table',
    'View',
    'MaterializedView',
    'Sequence',
    'Procedure',
    'Function',
    'Package',
    'Synonym',
)


def _product(
    sources: tuple[str, ...] | list[str], targets: tuple[str, ...] | list[str]
) -> frozenset[tuple[str, str]]:
    return frozenset((s, t) for s in sources for t in targets)


_CALLS_PAIRS = _product(_CODE_SOURCES, _CALL_TARGETS)
_READS_PAIRS = _product(_READ_SOURCES, _READ_TARGETS)
_WRITES_PAIRS = _product(_CODE_SOURCES, _WRITE_TARGETS)
_DEPENDS_PAIRS = _CONTAINS_PAIRS | _CALLS_PAIRS | _READS_PAIRS | _WRITES_PAIRS

# Immutable server authority. Keys must equal CATALOG_EDGE_TYPES exactly.
# Deferred types (LikelyReferencesTo/MapsTo/SynchronizesTo) intentionally absent.
EDGE_ENDPOINT_MAP: dict[str, frozenset[tuple[str, str]]] = {
    'Contains': _CONTAINS_PAIRS,
    'PrimaryKeyOf': frozenset({('Constraint', 'Table'), ('Constraint', 'Column')}),
    'UniqueKeyOf': frozenset({('Constraint', 'Table'), ('Constraint', 'Column')}),
    'ForeignKeyTo': frozenset({('Column', 'Column'), ('Table', 'Table')}),
    'EnforcedBy': frozenset({('Constraint', 'Table'), ('Constraint', 'Column')}),
    'TriggerOn': frozenset(
        {('Trigger', 'Table'), ('Trigger', 'View'), ('Trigger', 'MaterializedView')}
    ),
    'SynonymFor': frozenset({('Synonym', t) for t in _SYN_TARGETS}),
    'DocumentedBy': frozenset(
        (e, doc)
        for e in CATALOG_ENTITY_TYPES
        for doc in ('DictionaryDocument', 'SourceArtifact')
    ),
    'Calls': _CALLS_PAIRS,
    'ReadsFrom': _READS_PAIRS,
    'WritesTo': _WRITES_PAIRS,
    'JoinsWith': _product(_JOIN_TYPES, _JOIN_TYPES),
    'ReferencesByCode': _product(_REF_SOURCES, _REF_TARGETS),
    'DependsOn': _DEPENDS_PAIRS,
    'DerivedFrom': _product(_DERIVED_SOURCES, _DERIVED_TARGETS),
    'UsesSequence': frozenset((s, 'Sequence') for s in _SEQ_SOURCES),
}


def is_edge_endpoint_pair_allowed(
    edge_type: str, source_entity_type: str, target_entity_type: str
) -> bool:
    """Pure boolean map lookup. No mutation."""
    allowed = EDGE_ENDPOINT_MAP.get(edge_type)
    if allowed is None:
        return False
    return (source_entity_type, target_entity_type) in allowed


def validate_edge_endpoint_pair(
    edge_type: str, source_entity_type: str, target_entity_type: str
) -> None:
    """Raise ValueError with edge_endpoint_pair_not_allowed when pair is illegal."""
    if not is_edge_endpoint_pair_allowed(edge_type, source_entity_type, target_entity_type):
        raise ValueError(
            f'{CatalogErrorCode.edge_endpoint_pair_not_allowed}: edge endpoint pair not allowed'
        )


def endpoint_map_export() -> dict[str, list[list[str]]]:
    """Sorted pair lists for capabilities export. Generated only from EDGE_ENDPOINT_MAP."""
    return {
        edge_type: [[s, t] for s, t in sorted(pairs)]
        for edge_type, pairs in sorted(EDGE_ENDPOINT_MAP.items())
    }
