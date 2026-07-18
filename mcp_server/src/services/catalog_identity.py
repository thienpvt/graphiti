"""Pure deterministic identity and canonical hash helpers for catalog tools.

No network, Neo4j, embedder, LLM, or queue imports.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from typing import Any

from models.catalog_common import IDENTITY_SCHEMA_VERSION, CatalogErrorCode


def catalog_entity_uuid(
    namespace: uuid.UUID, group_id: str, entity_type: str, graph_key: str
) -> str:
    """Server-derived entity identity: UUIDv5(ns, group_id|catalog-v2|entity_type|graph_key)."""
    return str(
        uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|{entity_type}|{graph_key}')
    )


def catalog_edge_uuid(namespace: uuid.UUID, group_id: str, edge_type: str, edge_key: str) -> str:
    """Server-derived edge identity: UUIDv5(ns, group_id|catalog-v2|edge_type|edge_key)."""
    return str(
        uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|{edge_type}|{edge_key}')
    )


def catalog_source_uuid(namespace: uuid.UUID, group_id: str, source_key: str) -> str:
    """Server-derived source identity: UUIDv5(ns, group_id|catalog-v2|Source|source_key)."""
    return str(uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|Source|{source_key}'))


def catalog_batch_uuid(namespace: uuid.UUID, group_id: str, batch_id: str) -> str:
    """Server-derived batch identity: UUIDv5(ns, group_id|catalog-v2|Batch|batch_id)."""
    return str(uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|Batch|{batch_id}'))


def catalog_mentions_uuid(
    namespace: uuid.UUID, group_id: str, source_uuid: str, entity_uuid: str
) -> str:
    """Server-derived MENTIONS link identity: UUIDv5(ns, group_id|catalog-v2|Mentions|source|entity)."""
    return str(
        uuid.uuid5(
            namespace,
            f'{group_id}|{IDENTITY_SCHEMA_VERSION}|Mentions|{source_uuid}|{entity_uuid}',
        )
    )


def catalog_evidence_link_uuid(namespace: uuid.UUID, group_id: str, link_key: str) -> str:
    """Pure EvidenceLink identity: UUIDv5(ns, group_id|catalog-v2|EvidenceLink|link_key)."""
    return str(
        uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|EvidenceLink|{link_key}')
    )


def catalog_manifest_uuid(namespace: uuid.UUID, group_id: str, batch_id: str) -> str:
    """Pure Manifest identity: UUIDv5(ns, group_id|catalog-v2|Manifest|batch_id)."""
    return str(uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|Manifest|{batch_id}'))


def catalog_prepared_plan_uuid(namespace: uuid.UUID, group_id: str, plan_id: str) -> str:
    """Pure PreparedPlan identity: UUIDv5(ns, group_id|catalog-v2|PreparedPlan|plan_id)."""
    return str(
        uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|PreparedPlan|{plan_id}')
    )


def _reject_non_finite(obj: Any) -> None:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise ValueError('non-finite number')
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_non_finite(v)
    elif isinstance(obj, list):
        for v in obj:
            _reject_non_finite(v)


def canonical_sha256(payload: dict[str, Any]) -> str:
    """Return 64 lowercase hex SHA-256 over canonical JSON.

    Canonical form: sort_keys=True, separators=(',', ':'), ensure_ascii=False.
    Rejects NaN/Inf so hashes remain cross-client stable.
    """
    _reject_non_finite(payload)
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _error_code_text(code: CatalogErrorCode | str) -> str:
    """Normalize CatalogErrorCode or plain string to error-code text."""
    return code if isinstance(code, str) else str(code)


def assert_optional_client_hash(client_hash: str | None, server_hash: str) -> None:
    """Compare optional client content hash to server canonical hash.

    Raises ValueError containing content_hash_mismatch on mismatch.
    """
    if client_hash is None:
        return
    if client_hash.lower() != server_hash.lower():
        code = _error_code_text(CatalogErrorCode.content_hash_mismatch)
        raise ValueError(f'{code}: client hash mismatch')


def _locator_canonical(locator: Any) -> str:
    """Stable pipe-delimited locator material for link_key (empty when absent)."""
    if locator is None:
        return ''
    object_name = getattr(locator, 'object_name', None) or ''
    start_line = getattr(locator, 'start_line', None)
    end_line = getattr(locator, 'end_line', None)
    statement_index = getattr(locator, 'statement_index', None)
    return (
        f'{object_name}|'
        f'{"" if start_line is None else start_line}|'
        f'{"" if end_line is None else end_line}|'
        f'{"" if statement_index is None else statement_index}'
    )


def evidence_link_key(link: Any) -> str:
    """Deterministic identity key for CatalogEvidenceLink (excludes transport hash/excerpt).

    Material:
    source_key|target_kind|target_type|target_key|evidence_kind|
    extractor_name|extractor_version|rule_id|locator_canonical
    """
    entity = getattr(link, 'entity_target', None)
    edge = getattr(link, 'edge_target', None)
    if entity is not None:
        target_kind = 'entity'
        target_type = entity.entity_type
        target_key = entity.graph_key
    elif edge is not None:
        target_kind = 'edge'
        target_type = edge.edge_type
        target_key = edge.edge_key
    else:
        raise ValueError('evidence link requires exactly one target')
    rule_id = getattr(link, 'rule_id', None) or ''
    return (
        f'{link.source_key}|{target_kind}|{target_type}|{target_key}|'
        f'{link.evidence_kind}|{link.extractor_name}|{link.extractor_version}|'
        f'{rule_id}|{_locator_canonical(getattr(link, "locator", None))}'
    )


def evidence_canonical_payload(link: Any) -> dict[str, Any]:
    """Canonical content fields for evidence hashing (includes excerpt bytes).

    Excludes client transport-only content_sha256. Nested targets/locator dumped
    with mode=json for stable structure.
    """
    entity = getattr(link, 'entity_target', None)
    edge = getattr(link, 'edge_target', None)
    locator = getattr(link, 'locator', None)

    def _dump(model: Any) -> dict[str, Any] | None:
        if model is None:
            return None
        dump = getattr(model, 'model_dump', None)
        if callable(dump):
            return dump(mode='json')
        return dict(model)

    return {
        'source_key': link.source_key,
        'entity_target': _dump(entity),
        'edge_target': _dump(edge),
        'evidence_kind': link.evidence_kind,
        'locator': _dump(locator),
        'excerpt': link.excerpt,
        'extractor_name': link.extractor_name,
        'extractor_version': link.extractor_version,
        'rule_id': link.rule_id,
        'confidence': link.confidence,
    }


def coalesce_byte_identical_evidence_links(links: list[Any]) -> list[Any]:
    """Collapse links with equal evidence_canonical_payload; stable sort by link_key.

    Retains multiplicity of non-identical payloads. Pure and reentrant.
    """
    if not links:
        return []
    seen: dict[str, Any] = {}
    for link in links:
        digest = canonical_sha256(evidence_canonical_payload(link))
        if digest not in seen:
            seen[digest] = link
    return sorted(seen.values(), key=evidence_link_key)
