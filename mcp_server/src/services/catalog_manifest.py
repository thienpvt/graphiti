"""Pure durable-manifest canonicalization, hash, and chunk framing.

No network, graph-driver, embedder, LLM, or queue imports.
Membership authority is frozen compact identities + projected_status only —
never member batch_id, never live graph queries, never embeddings.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from models.catalog_common import (
    HARD_MAX_PREPARED_PAYLOAD_BYTES,
    IDENTITY_SCHEMA_VERSION,
)
from services.catalog_identity import (
    CANONICALIZATION_VERSION,
    CATALOG_SCHEMA_VERSION,
)
from services.catalog_prepared_artifact import (
    DEFAULT_CHUNK_BYTES,
    HARD_CHUNK_BYTES,
    MAX_CHUNKS_PER_PLAN,
    chunk_artifact_bytes,
)

MANIFEST_SERIALIZATION_VERSION = 'catalog-manifest-v1'

# Phase 3A ceilings re-exported for callers/tests (DEFAULT/HARD_CHUNK_BYTES imported).
MAX_CHUNKS_PER_MANIFEST = MAX_CHUNKS_PER_PLAN
HARD_MAX_MANIFEST_PAYLOAD_BYTES = HARD_MAX_PREPARED_PAYLOAD_BYTES

_FORBIDDEN_SELF_HASH_KEYS = frozenset({'manifest_sha256'})

_PROJECTED_STATUS_VALUES = frozenset({'created', 'updated', 'unchanged'})

_MEMBERSHIP_CATEGORIES = (
    (
        'entities',
        'graph_key',
        ('uuid', 'entity_type', 'graph_key', 'content_sha256', 'projected_status'),
    ),
    ('edges', 'edge_key', ('uuid', 'edge_type', 'edge_key', 'content_sha256', 'projected_status')),
    ('sources', 'source_key', ('uuid', 'source_key', 'content_sha256', 'projected_status')),
    ('evidence_links', 'link_key', ('uuid', 'link_key', 'content_sha256')),
)


def _reject_non_finite(obj: object) -> None:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise ValueError('non-finite number')
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_non_finite(v)
    elif isinstance(obj, list):
        for v in obj:
            _reject_non_finite(v)


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{field} must be a non-empty string')
    return value


def _compact_row(row: object, fields: tuple[str, ...], *, require_status: bool) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError('membership row must be a dict')
    out: dict[str, Any] = {}
    for field in fields:
        if field == 'projected_status':
            if not require_status:
                continue
            status = row.get('projected_status')
            if status not in _PROJECTED_STATUS_VALUES:
                raise ValueError(
                    f'projected_status must be one of {sorted(_PROJECTED_STATUS_VALUES)}'
                )
            out[field] = status
            continue
        value = row.get(field)
        out[field] = _require_str(value, field)
    return out


def _sort_key_for(row: dict[str, Any], sort_field: str) -> tuple[str, str]:
    return (str(row[sort_field]), str(row['uuid']))


def _project_category(
    membership: dict[str, Any],
    category: str,
    sort_field: str,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    if category not in membership:
        raise ValueError(f'membership missing required category {category!r}')
    raw = membership[category]
    if raw is None:
        raise ValueError(f'membership category {category!r} must not be null')
    if not isinstance(raw, list):
        raise ValueError(f'membership category {category!r} must be a list')
    require_status = 'projected_status' in fields
    projected = [_compact_row(item, fields, require_status=require_status) for item in raw]
    return sorted(projected, key=lambda r: _sort_key_for(r, sort_field))


def build_manifest_body_from_membership(
    *,
    group_id: object,
    batch_id: object,
    request_sha256: object,
    catalog_sha256: object,
    membership: object,
    artifact_sha256: object = None,
    identity_schema_version: str = IDENTITY_SCHEMA_VERSION,
    canonicalization_version: str = CANONICALIZATION_VERSION,
    catalog_schema_version: str = CATALOG_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Build catalog-manifest-v1 body from frozen compact membership.

    Membership authority is the provided lists only — never member batch_id.
    Embeddings and transport-only fields are stripped. projected_status including
    'unchanged' is preserved (MANI-02).
    """
    if membership is None:
        raise ValueError('membership must not be null')
    if not isinstance(membership, dict):
        raise ValueError('membership must be a dict')

    group_id_s = _require_str(group_id, 'group_id')
    batch_id_s = _require_str(batch_id, 'batch_id')
    request_sha256_s = _require_str(request_sha256, 'request_sha256')
    catalog_sha256_s = _require_str(catalog_sha256, 'catalog_sha256')
    artifact_sha256_s: str | None
    if artifact_sha256 is None:
        artifact_sha256_s = None
    else:
        artifact_sha256_s = _require_str(artifact_sha256, 'artifact_sha256')

    categories: dict[str, list[dict[str, Any]]] = {}
    for name, sort_field, fields in _MEMBERSHIP_CATEGORIES:
        categories[name] = _project_category(membership, name, sort_field, fields)

    body: dict[str, Any] = {
        'manifest_serialization_version': MANIFEST_SERIALIZATION_VERSION,
        'canonicalization_version': canonicalization_version,
        'identity_schema_version': identity_schema_version,
        'catalog_schema_version': catalog_schema_version,
        'group_id': group_id_s,
        'batch_id': batch_id_s,
        'request_sha256': request_sha256_s,
        'catalog_sha256': catalog_sha256_s,
        'artifact_sha256': artifact_sha256_s,
        'counts': {
            'entities': len(categories['entities']),
            'edges': len(categories['edges']),
            'sources': len(categories['sources']),
            'evidence_links': len(categories['evidence_links']),
        },
        'entities': categories['entities'],
        'edges': categories['edges'],
        'sources': categories['sources'],
        'evidence_links': categories['evidence_links'],
    }
    _reject_non_finite(body)
    return body


def serialize_manifest_body(body: object) -> bytes:
    """Serialize catalog-manifest-v1 body to canonical UTF-8 JSON bytes.

    Rules match catalog_prepared_artifact / catalog_identity.canonical_sha256.
    Rejects embedded manifest_sha256 so digest stays external (MANI-07).
    """
    if not isinstance(body, dict):
        raise ValueError('manifest body must be a dict')
    forbidden = _FORBIDDEN_SELF_HASH_KEYS.intersection(body.keys())
    if forbidden:
        raise ValueError(f'manifest body must not embed self-hash field(s): {sorted(forbidden)}')
    version = body.get('manifest_serialization_version')
    if version is not None and version != MANIFEST_SERIALIZATION_VERSION:
        raise ValueError(
            f'unsupported manifest_serialization_version: {version!r}; '
            f'expected {MANIFEST_SERIALIZATION_VERSION!r}'
        )
    _reject_non_finite(body)
    return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode(
        'utf-8'
    )


def manifest_sha256(manifest_bytes: object) -> str:
    """Return 64 lowercase hex SHA-256 over complete canonical manifest bytes."""
    if not isinstance(manifest_bytes, (bytes, bytearray)):
        raise TypeError('manifest_bytes must be bytes')
    return hashlib.sha256(bytes(manifest_bytes)).hexdigest()


def chunk_manifest_bytes(
    manifest_bytes: object,
    *,
    chunk_size: int = DEFAULT_CHUNK_BYTES,
) -> list[dict[str, Any]]:
    """Split manifest bytes via Phase 3A chunk_artifact_bytes framing.

    Empty payload yields a single empty chunk. Enforces HARD_CHUNK_BYTES,
    MAX_CHUNKS_PER_MANIFEST, and HARD_MAX_MANIFEST_PAYLOAD_BYTES fail-closed.
    """
    if not isinstance(manifest_bytes, (bytes, bytearray)):
        raise TypeError('manifest_bytes must be bytes')
    if not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError('chunk_size must be a positive integer')
    if chunk_size > HARD_CHUNK_BYTES:
        raise ValueError(f'chunk_size {chunk_size} exceeds hard max {HARD_CHUNK_BYTES}')
    data = bytes(manifest_bytes)
    if len(data) > HARD_MAX_MANIFEST_PAYLOAD_BYTES:
        raise ValueError(
            f'manifest payload {len(data)} exceeds hard max {HARD_MAX_MANIFEST_PAYLOAD_BYTES}'
        )
    return chunk_artifact_bytes(data, chunk_size=chunk_size)


def chunk_manifest_body(
    body: object,
    *,
    chunk_size: int = DEFAULT_CHUNK_BYTES,
) -> list[dict[str, Any]]:
    """Serialize then chunk a manifest body (convenience)."""
    return chunk_manifest_bytes(serialize_manifest_body(body), chunk_size=chunk_size)
