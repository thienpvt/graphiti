"""Exhaustive unit matrix for server-owned catalog edge endpoint topology (EDGE-01..09)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_common import (  # noqa: E402
    CATALOG_EDGE_TYPES,
    CATALOG_ENTITY_TYPES,
    CatalogErrorCode,
)
from models.catalog_topology import (  # noqa: E402
    EDGE_ENDPOINT_MAP,
    endpoint_map_export,
    is_edge_endpoint_pair_allowed,
    validate_edge_endpoint_pair,
)

DEFERRED_EDGE_TYPES = frozenset({'LikelyReferencesTo', 'MapsTo', 'SynchronizesTo'})

# Expected pairs locked from 02-RESEARCH Topology Authority (A1/A8 defaults).
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
_JOINS_PAIRS = _product(_JOIN_TYPES, _JOIN_TYPES)
_DEPENDS_PAIRS = _CONTAINS_PAIRS | _CALLS_PAIRS | _READS_PAIRS | _WRITES_PAIRS

EXPECTED_MAP: dict[str, frozenset[tuple[str, str]]] = {
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
        for e in sorted(CATALOG_ENTITY_TYPES)
        for doc in ('DictionaryDocument', 'SourceArtifact')
    ),
    'Calls': _CALLS_PAIRS,
    'ReadsFrom': _READS_PAIRS,
    'WritesTo': _WRITES_PAIRS,
    'JoinsWith': _JOINS_PAIRS,
    'ReferencesByCode': _product(_REF_SOURCES, _REF_TARGETS),
    'DependsOn': _DEPENDS_PAIRS,
    'DerivedFrom': _product(_DERIVED_SOURCES, _DERIVED_TARGETS),
    'UsesSequence': frozenset((s, 'Sequence') for s in _SEQ_SOURCES),
}

# One representative illegal pair per registered edge type (types still allowlisted).
REJECT_SAMPLES: list[tuple[str, str, str]] = [
    ('Contains', 'Table', 'Schema'),
    ('PrimaryKeyOf', 'Table', 'Constraint'),
    ('UniqueKeyOf', 'Column', 'Constraint'),
    ('ForeignKeyTo', 'Column', 'Table'),
    ('EnforcedBy', 'Table', 'Constraint'),
    ('TriggerOn', 'Table', 'Trigger'),
    ('SynonymFor', 'Table', 'Synonym'),
    ('DocumentedBy', 'Table', 'Schema'),
    ('Calls', 'Table', 'Procedure'),
    ('ReadsFrom', 'Table', 'Procedure'),
    ('WritesTo', 'View', 'Table'),
    ('JoinsWith', 'Procedure', 'Table'),
    ('ReferencesByCode', 'Table', 'Procedure'),
    ('DependsOn', 'Column', 'Schema'),
    ('DerivedFrom', 'Table', 'View'),
    ('UsesSequence', 'Table', 'Sequence'),
]


def test_edge_endpoint_map_keys_equal_catalog_edge_types():
    assert set(EDGE_ENDPOINT_MAP.keys()) == set(CATALOG_EDGE_TYPES)
    assert len(EDGE_ENDPOINT_MAP) == 16


def test_deferred_edge_types_not_registered():
    for name in DEFERRED_EDGE_TYPES:
        assert name not in EDGE_ENDPOINT_MAP
        assert name not in CATALOG_EDGE_TYPES


def test_every_pair_member_in_catalog_entity_types():
    for edge_type, pairs in EDGE_ENDPOINT_MAP.items():
        for source, target in pairs:
            assert source in CATALOG_ENTITY_TYPES, f'{edge_type} source {source}'
            assert target in CATALOG_ENTITY_TYPES, f'{edge_type} target {target}'


def test_expected_map_matches_authority():
    assert set(EXPECTED_MAP.keys()) == set(CATALOG_EDGE_TYPES)
    for edge_type, expected in EXPECTED_MAP.items():
        actual = EDGE_ENDPOINT_MAP[edge_type]
        assert actual == expected, f'{edge_type}: missing={expected - actual} extra={actual - expected}'


def _allowed_cases() -> list[tuple[str, str, str]]:
    cases: list[tuple[str, str, str]] = []
    for edge_type, pairs in EXPECTED_MAP.items():
        for source, target in sorted(pairs):
            cases.append((edge_type, source, target))
    return cases


@pytest.mark.parametrize(('edge_type', 'source', 'target'), _allowed_cases())
def test_validate_allows_every_registered_pair(edge_type: str, source: str, target: str):
    validate_edge_endpoint_pair(edge_type, source, target)
    assert is_edge_endpoint_pair_allowed(edge_type, source, target) is True


@pytest.mark.parametrize(('edge_type', 'source', 'target'), REJECT_SAMPLES)
def test_validate_rejects_disallowed_pairs(edge_type: str, source: str, target: str):
    with pytest.raises(ValueError, match=CatalogErrorCode.edge_endpoint_pair_not_allowed.value):
        validate_edge_endpoint_pair(edge_type, source, target)
    assert is_edge_endpoint_pair_allowed(edge_type, source, target) is False


@pytest.mark.parametrize('edge_type', sorted(DEFERRED_EDGE_TYPES))
def test_deferred_and_unknown_edge_types_fail(edge_type: str):
    with pytest.raises(ValueError, match=CatalogErrorCode.edge_endpoint_pair_not_allowed.value):
        validate_edge_endpoint_pair(edge_type, 'Table', 'Table')
    assert is_edge_endpoint_pair_allowed(edge_type, 'Table', 'Table') is False


def test_foreign_key_dual_pairs_and_column_table_reject():
    validate_edge_endpoint_pair('ForeignKeyTo', 'Column', 'Column')
    validate_edge_endpoint_pair('ForeignKeyTo', 'Table', 'Table')
    with pytest.raises(ValueError, match=CatalogErrorCode.edge_endpoint_pair_not_allowed.value):
        validate_edge_endpoint_pair('ForeignKeyTo', 'Column', 'Table')
    with pytest.raises(ValueError, match=CatalogErrorCode.edge_endpoint_pair_not_allowed.value):
        validate_edge_endpoint_pair('ForeignKeyTo', 'Table', 'Column')


def test_trigger_on_requires_trigger_source():
    validate_edge_endpoint_pair('TriggerOn', 'Trigger', 'Table')
    with pytest.raises(ValueError, match=CatalogErrorCode.edge_endpoint_pair_not_allowed.value):
        validate_edge_endpoint_pair('TriggerOn', 'Procedure', 'Table')


def test_synonym_for_requires_synonym_source():
    validate_edge_endpoint_pair('SynonymFor', 'Synonym', 'Table')
    with pytest.raises(ValueError, match=CatalogErrorCode.edge_endpoint_pair_not_allowed.value):
        validate_edge_endpoint_pair('SynonymFor', 'View', 'Table')


def test_documented_by_targets_only_docs():
    for entity in sorted(CATALOG_ENTITY_TYPES):
        validate_edge_endpoint_pair('DocumentedBy', entity, 'DictionaryDocument')
        validate_edge_endpoint_pair('DocumentedBy', entity, 'SourceArtifact')
    with pytest.raises(ValueError, match=CatalogErrorCode.edge_endpoint_pair_not_allowed.value):
        validate_edge_endpoint_pair('DocumentedBy', 'Table', 'Table')


def test_uses_sequence_targets_sequence_only():
    validate_edge_endpoint_pair('UsesSequence', 'Procedure', 'Sequence')
    with pytest.raises(ValueError, match=CatalogErrorCode.edge_endpoint_pair_not_allowed.value):
        validate_edge_endpoint_pair('UsesSequence', 'Procedure', 'Table')


def test_endpoint_map_export_sorted_and_complete():
    exported = endpoint_map_export()
    assert list(exported.keys()) == sorted(CATALOG_EDGE_TYPES)
    for edge_type, pairs in exported.items():
        assert pairs == sorted(pairs)
        as_tuples = {(s, t) for s, t in pairs}
        assert as_tuples == EDGE_ENDPOINT_MAP[edge_type]
        for pair in pairs:
            assert isinstance(pair, list)
            assert len(pair) == 2


def test_is_edge_endpoint_pair_allowed_pure_no_mutation():
    before = {k: frozenset(v) for k, v in EDGE_ENDPOINT_MAP.items()}
    assert is_edge_endpoint_pair_allowed('ForeignKeyTo', 'Table', 'Table') is True
    assert is_edge_endpoint_pair_allowed('ForeignKeyTo', 'Column', 'Table') is False
    after = {k: frozenset(v) for k, v in EDGE_ENDPOINT_MAP.items()}
    assert before == after


def test_allowed_pairs_remain_separate_entries_no_merge():
    # Dual FK pairs must both exist distinctly (no collapse to one entry).
    pairs = EDGE_ENDPOINT_MAP['ForeignKeyTo']
    assert ('Column', 'Column') in pairs
    assert ('Table', 'Table') in pairs
    assert len(pairs) == 2


def test_map_lookup_order_stable_and_reentrant():
    first = endpoint_map_export()
    second = endpoint_map_export()
    assert first == second
    for _ in range(3):
        validate_edge_endpoint_pair('Contains', 'Schema', 'Table')
        assert is_edge_endpoint_pair_allowed('Contains', 'Schema', 'Table') is True
