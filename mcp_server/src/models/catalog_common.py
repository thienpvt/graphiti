"""Shared catalog allowlists, limits, and structured error codes."""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, ConfigDict


class StrEnum(str, Enum):
    """str Enum compatible with Python 3.10 (stdlib StrEnum is 3.11+)."""


class CatalogStrictModel(BaseModel):
    """Fail-closed request base: unknown fields rejected at every nesting depth."""

    model_config = ConfigDict(extra='forbid')


# Catalog-v2 identity shell constants (immutable request contract)
IDENTITY_SCHEMA_VERSION = 'catalog-v2'
SYSTEM_KEYS: frozenset[str] = frozenset({'FE', 'BO', 'COMMON'})

# Default batch collection limits (CONF-04)
DEFAULT_MAX_ENTITIES_PER_BATCH = 500
DEFAULT_MAX_EDGES_PER_BATCH = 2000
DEFAULT_MAX_PROVENANCE_LINKS_PER_BATCH = 5000
HARD_MAX_ENTITIES_PER_BATCH = 5000
HARD_MAX_EDGES_PER_BATCH = 10000
HARD_MAX_PROVENANCE_LINKS_PER_BATCH = 20000

# String / raw-text limits (SAFE-03)
MAX_SHORT_STRING_LENGTH = 512
MAX_GRAPH_KEY_LENGTH = 1024
MAX_SUMMARY_LENGTH = 4096
MAX_FACT_LENGTH = 4096
MAX_EVIDENCE_LENGTH = 8192
MAX_ATTRIBUTE_KEYS = 64
MAX_SOURCE_REFS = 32
MAX_NESTED_DEPTH = 32
MAX_NESTED_NODES = 10000


def validate_nested_json(obj: object, path: str = 'value') -> None:
    """Iteratively validate bounded, acyclic JSON-compatible nested data."""
    stack: list[tuple[object, str, int, bool]] = [(obj, path, 0, False)]
    active_containers: set[int] = set()
    visited = 0
    while stack:
        value, current_path, depth, leaving = stack.pop()
        if leaving:
            active_containers.remove(id(value))
            continue
        visited += 1
        if visited > MAX_NESTED_NODES:
            raise ValueError(f'nested value exceeds max nodes ({MAX_NESTED_NODES})')
        if value is None or isinstance(value, (bool, int)):
            continue
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(f'non-finite number at {current_path}')
            continue
        if isinstance(value, str):
            if len(value) > MAX_EVIDENCE_LENGTH:
                raise ValueError(
                    f'string exceeds max length ({MAX_EVIDENCE_LENGTH}) at {current_path}'
                )
            continue
        if not isinstance(value, (dict, list)):
            raise ValueError(f'non-JSON value at {current_path}: {type(value).__name__}')
        if depth >= MAX_NESTED_DEPTH:
            raise ValueError(f'nested value exceeds max depth ({MAX_NESTED_DEPTH})')
        container_id = id(value)
        if container_id in active_containers:
            raise ValueError(f'nested value contains cycle at {current_path}')
        active_containers.add(container_id)
        stack.append((value, current_path, depth, True))
        if isinstance(value, dict):
            for key, child in reversed(list(value.items())):
                if not isinstance(key, str):
                    raise ValueError(f'dict key must be a string at {current_path}')
                if len(key) > MAX_SHORT_STRING_LENGTH:
                    raise ValueError(
                        f'dict key exceeds max length ({MAX_SHORT_STRING_LENGTH}) at {current_path}'
                    )
                stack.append((child, f'{current_path}.{key}', depth + 1, False))
        else:
            for index in range(len(value) - 1, -1, -1):
                stack.append((value[index], f'{current_path}[{index}]', depth + 1, False))


# Fixed entity type → graph_key prefix map (15 types)
ENTITY_TYPE_PREFIXES: dict[str, str] = {
    'Database': 'DATABASE::',
    'DictionaryDocument': 'DOC::',
    'Schema': 'SCHEMA::',
    'Table': 'TABLE::',
    'View': 'VIEW::',
    'MaterializedView': 'MVIEW::',
    'Column': 'COLUMN::',
    'Constraint': 'CONSTRAINT::',
    'Index': 'INDEX::',
    'Package': 'PACKAGE::',
    'Procedure': 'PROCEDURE::',
    'Function': 'FUNCTION::',
    'Trigger': 'TRIGGER::',
    'Sequence': 'SEQUENCE::',
    'Synonym': 'SYNONYM::',
}

CATALOG_ENTITY_TYPES: frozenset[str] = frozenset(ENTITY_TYPE_PREFIXES.keys())

# Fixed edge type allowlist (16 types)
CATALOG_EDGE_TYPES: frozenset[str] = frozenset(
    {
        'Contains',
        'PrimaryKeyOf',
        'UniqueKeyOf',
        'ForeignKeyTo',
        'EnforcedBy',
        'TriggerOn',
        'SynonymFor',
        'DocumentedBy',
        'Calls',
        'ReadsFrom',
        'WritesTo',
        'JoinsWith',
        'ReferencesByCode',
        'DependsOn',
        'DerivedFrom',
        'UsesSequence',
    }
)

# Properties callers may not set via attributes (ENTY-05 / SAFE-03)
PROTECTED_ENTITY_PROPERTIES: frozenset[str] = frozenset(
    {
        'uuid',
        'group_id',
        'labels',
        'graph_key',
        'name_embedding',
        'created_at',
        'updated_at',
        'content_sha256',
    }
)

# SHA-256 lowercase hex pattern
SHA256_HEX_RE = r'^[0-9a-f]{64}$'


class CatalogErrorCode(StrEnum):
    """Documented structured error codes for catalog tools."""

    validation_error = 'validation_error'
    feature_disabled = 'feature_disabled'
    invalid_uuid_namespace = 'invalid_uuid_namespace'
    batch_limit_exceeded = 'batch_limit_exceeded'
    content_hash_mismatch = 'content_hash_mismatch'
    entity_type_conflict = 'entity_type_conflict'
    graph_key_prefix_mismatch = 'graph_key_prefix_mismatch'
    deterministic_uuid_conflict = 'deterministic_uuid_conflict'
    missing_endpoint = 'missing_endpoint'
    endpoint_type_mismatch = 'endpoint_type_mismatch'
    generic_endpoint_conflict = 'generic_endpoint_conflict'
    edge_identity_conflict = 'edge_identity_conflict'
    batch_conflict = 'batch_conflict'
    provenance_target_missing = 'provenance_target_missing'
    neo4j_transaction_failed = 'neo4j_transaction_failed'
    embedding_failed = 'embedding_failed'
    internal_error = 'internal_error'
    backend_unavailable = 'backend_unavailable'
    # Phase 1 CONT-08 (append-only; never remove preexisting members)
    unsupported_identity_schema = 'unsupported_identity_schema'
    invalid_system_key = 'invalid_system_key'
    edge_endpoint_pair_not_allowed = 'edge_endpoint_pair_not_allowed'
    prepared_plan_not_found = 'prepared_plan_not_found'
    prepared_plan_expired = 'prepared_plan_expired'
    prepared_plan_conflict = 'prepared_plan_conflict'
    prepared_plan_already_consumed = 'prepared_plan_already_consumed'
    manifest_mismatch = 'manifest_mismatch'
    provenance_link_conflict = 'provenance_link_conflict'
