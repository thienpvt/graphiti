"""Pure graph-key grammar registry. No network, Neo4j, embedder, LLM, queue."""

from __future__ import annotations

import re

from models.catalog_common import ENTITY_TYPE_PREFIXES, MAX_GRAPH_KEY_LENGTH, SYSTEM_KEYS

# Oracle-ish identifier segment (uppercase only; fail-closed, no rewrite/NFC).
_ORACLE_IDENT = r'[A-Z][A-Z0-9_$#]*'
# Procedure/Function overload token after '#'; nonempty, no rewrite.
_OVERLOAD = r'[A-Za-z0-9_$,#()]+'
# SourceArtifact body: bounded path-ish key, no spaces.
_SOURCE_ARTIFACT = r'[A-Za-z0-9._\-/\#]+'


def _body(pattern: str) -> str:
    return pattern


# Body patterns after PREFIX::{SYSTEM}::
_BODY_PATTERNS: dict[str, str] = {
    'System': _body(rf'{_ORACLE_IDENT}'),
    'Database': _body(rf'{_ORACLE_IDENT}'),
    'DictionaryDocument': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'Schema': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'Table': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'View': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'MaterializedView': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'Column': _body(
        rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'
    ),
    'Constraint': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'Index': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'Package': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    # Optional package segment: <DB>.<SCHEMA>.(<PACKAGE>.)?<NAME>#<OVERLOAD>
    'Procedure': _body(
        rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.(?:{_ORACLE_IDENT}\.)?{_ORACLE_IDENT}#{_OVERLOAD}'
    ),
    'Function': _body(
        rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.(?:{_ORACLE_IDENT}\.)?{_ORACLE_IDENT}#{_OVERLOAD}'
    ),
    'Trigger': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'Sequence': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'Synonym': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'DatabaseLink': _body(rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}'),
    'SourceArtifact': _body(_SOURCE_ARTIFACT),
}


def _compile_full(entity_type: str) -> re.Pattern[str]:
    prefix = ENTITY_TYPE_PREFIXES[entity_type]
    # Escape prefix literal; system is closed set FE|BO|COMMON.
    body = _BODY_PATTERNS[entity_type]
    # PREFIX::{SYSTEM}::body — system segment exact uppercase from closed set.
    pattern = (
        rf'^{re.escape(prefix)}'
        rf'(?P<system>FE|BO|COMMON)::'
        rf'{body}$'
    )
    return re.compile(pattern)


_COMPILED: dict[str, re.Pattern[str]] = {
    entity_type: _compile_full(entity_type) for entity_type in ENTITY_TYPE_PREFIXES
}


def validate_entity_graph_key(
    *, entity_type: str, graph_key: str, system_key: str
) -> None:
    """Fullmatch registry; require PREFIX::{system_key}::...; no v1 rewrite."""
    if entity_type not in ENTITY_TYPE_PREFIXES:
        raise ValueError(f'entity_type not allowlisted: {entity_type}')
    if system_key not in SYSTEM_KEYS:
        raise ValueError(f'invalid_system_key: {system_key}')
    if not isinstance(graph_key, str) or not graph_key:
        raise ValueError('graph_key grammar mismatch: empty graph_key')
    if len(graph_key) > MAX_GRAPH_KEY_LENGTH:
        raise ValueError(
            f'graph_key grammar mismatch: exceeds max length ({MAX_GRAPH_KEY_LENGTH})'
        )

    compiled = _COMPILED[entity_type]
    match = compiled.fullmatch(graph_key)
    if match is None:
        raise ValueError(
            f'graph_key grammar mismatch: {entity_type} key does not fullmatch registry'
        )

    key_system = match.group('system')
    if key_system != system_key:
        raise ValueError(
            f'invalid_system_key: graph_key system {key_system} != shell {system_key}'
        )
