"""Pure graph-key grammar registry. No network, Neo4j, embedder, LLM, queue."""

from __future__ import annotations

import re

from pydantic_core import PydanticCustomError

from models.catalog_common import (
    ENTITY_TYPE_PREFIXES,
    MAX_GRAPH_KEY_LENGTH,
    SYSTEM_KEYS,
    invalid_system_key_validation_error,
)

# Oracle-ish identifier segment (uppercase only; fail-closed, no rewrite/NFC).
_ORACLE_IDENT = r'[A-Z][A-Z0-9_$#]*'
# Procedure/Function overload token after '#'; nonempty, no rewrite.
_OVERLOAD = r'[A-Za-z0-9_$,#()]+'
# SourceArtifact body: bounded path-ish key, no spaces.
_SOURCE_ARTIFACT = r'[A-Za-z0-9._\-/\#]+'

# Body patterns after PREFIX::{SYSTEM}::
_BODY_PATTERNS: dict[str, str] = {
    'System': rf'{_ORACLE_IDENT}',
    'Database': rf'{_ORACLE_IDENT}',
    'DictionaryDocument': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'Schema': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'Table': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'View': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'MaterializedView': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'Column': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'Constraint': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'Index': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'Package': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    # Optional package segment: <DB>.<SCHEMA>.(<PACKAGE>.)?<NAME>#<OVERLOAD>
    'Procedure': (
        rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.(?:{_ORACLE_IDENT}\.)?{_ORACLE_IDENT}#{_OVERLOAD}'
    ),
    'Function': (
        rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.(?:{_ORACLE_IDENT}\.)?{_ORACLE_IDENT}#{_OVERLOAD}'
    ),
    'Trigger': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'Sequence': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'Synonym': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'DatabaseLink': rf'{_ORACLE_IDENT}\.{_ORACLE_IDENT}',
    'SourceArtifact': _SOURCE_ARTIFACT,
}


def _compile_full(entity_type: str) -> re.Pattern[str]:
    prefix = ENTITY_TYPE_PREFIXES[entity_type]
    body = _BODY_PATTERNS[entity_type]
    # PREFIX::{SYSTEM}::body — system segment exact uppercase from closed set.
    pattern = rf'^{re.escape(prefix)}(?P<system>FE|BO|COMMON)::{body}$'
    return re.compile(pattern)


_COMPILED: dict[str, re.Pattern[str]] = {
    entity_type: _compile_full(entity_type) for entity_type in ENTITY_TYPE_PREFIXES
}


def _match_entity_graph_key(entity_type: str, graph_key: str) -> re.Match[str]:
    """Fullmatch key against type grammar; return match with named system group."""
    if entity_type not in ENTITY_TYPE_PREFIXES:
        raise ValueError(f'entity_type not allowlisted: {entity_type}')
    if not isinstance(graph_key, str) or not graph_key:
        raise ValueError('graph_key grammar mismatch: empty graph_key')
    if len(graph_key) > MAX_GRAPH_KEY_LENGTH:
        raise ValueError(f'graph_key grammar mismatch: exceeds max length ({MAX_GRAPH_KEY_LENGTH})')
    match = _COMPILED[entity_type].fullmatch(graph_key)
    if match is None:
        raise ValueError(
            f'graph_key grammar mismatch: {entity_type} key does not fullmatch registry'
        )
    return match


def validate_entity_graph_key(*, entity_type: str, graph_key: str, system_key: str) -> None:
    """Fullmatch registry; require PREFIX::{system_key}::...; no v1 rewrite."""
    if system_key not in SYSTEM_KEYS:
        raise PydanticCustomError('invalid_system_key', 'Invalid system key')
    match = _match_entity_graph_key(entity_type, graph_key)
    key_system = match.group('system')
    if key_system != system_key:
        raise PydanticCustomError('invalid_system_key', 'Invalid system key')


def validate_entity_graph_key_at(
    *,
    entity_type: str,
    graph_key: str,
    system_key: str,
    title: str,
    loc: tuple[str | int, ...],
) -> None:
    try:
        validate_entity_graph_key(
            entity_type=entity_type,
            graph_key=graph_key,
            system_key=system_key,
        )
    except PydanticCustomError as exc:
        if exc.type != 'invalid_system_key':
            raise
        raise invalid_system_key_validation_error(
            title=title,
            loc=loc,
            input_value=graph_key,
        ) from exc
