"""Mutation-free catalog capabilities builder (CAPA-01..08).

No Neo4j write, schema ensure, index repair, store, or control-plane side effects.
"""

from __future__ import annotations

import hashlib
import uuid
from importlib import metadata
from typing import Any, Literal

from config.schema import CatalogConfig
from models.catalog_common import (
    CATALOG_EDGE_TYPES,
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_ACTIVE_PLANS_PER_GROUP,
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
    IDENTITY_SCHEMA_VERSION,
)
from models.catalog_common import (
    HARD_MAX_PREPARED_PAYLOAD_BYTES as _COMMON_HARD_MAX_PREPARED_PAYLOAD_BYTES,
)
from models.catalog_common import (
    HARD_PLAN_TTL_SECONDS as _COMMON_HARD_PLAN_TTL_SECONDS,
)
from models.catalog_responses import CatalogCapabilitiesResponse
from models.catalog_topology import endpoint_map_export
from services.catalog_identity import CANONICALIZATION_VERSION, CATALOG_SCHEMA_VERSION

Connectivity = Literal['ok', 'error', 'unknown']
IndexReadiness = Literal['ready', 'unknown', 'n/a']

# Real plan hard ceilings (PLAN-08 / D-29). features.prepare_commit flips true only after
# 03A-06 live immutable proof on final HEAD.
HARD_MAX_PREPARED_PAYLOAD_BYTES = _COMMON_HARD_MAX_PREPARED_PAYLOAD_BYTES
HARD_MAX_ACTIVE_PLANS = HARD_MAX_ACTIVE_PLANS_PER_GROUP
HARD_PLAN_TTL_SECONDS = _COMMON_HARD_PLAN_TTL_SECONDS
# Phase 4 (D-04/D-24): hard page ceiling for diagnostic list tools.
HARD_MAX_PAGE_SIZE = 500


def namespace_fingerprint(namespace: uuid.UUID | None) -> str | None:
    """One-way domain-separated SHA-256 prefix; never reverse to raw namespace."""
    if namespace is None:
        return None
    material = b'graphiti.catalog.nsfp.v1|' + namespace.bytes
    return hashlib.sha256(material).hexdigest()[:16]


def _parse_namespace(raw: str | None) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return None


def _package_version() -> str:
    try:
        return metadata.version('mcp-server')
    except metadata.PackageNotFoundError:
        return 'unknown'


def build_catalog_capabilities(
    *,
    config: CatalogConfig,
    client: Any | None = None,
    backend: str | None = None,
    package_version: str | None = None,
    connectivity: Connectivity | None = None,
    embedder_provider: str | None = None,
    embedder_model: str | None = None,
) -> CatalogCapabilitiesResponse:
    """Pure capabilities view. Never mutates DB/schema/indexes/store."""
    parsed_ns = _parse_namespace(config.uuid_namespace)
    ns_configured = parsed_ns is not None
    fp = namespace_fingerprint(parsed_ns)

    # Connectivity / readiness: only report what callers already know. Never probe
    # with writes or schema init. client presence alone is not connectivity proof.
    conn: Connectivity = connectivity if connectivity is not None else 'unknown'
    backend_name = backend
    if client is not None and backend_name is None:
        # Do not call driver methods; only accept explicit backend from caller.
        backend_name = None

    if backend_name == 'neo4j':
        neo4j_indexes: IndexReadiness = 'unknown'
    elif backend_name is None:
        neo4j_indexes = 'unknown'
    else:
        neo4j_indexes = 'n/a'

    embeddings: dict[str, Any] = {
        'provider': embedder_provider,
        'model': embedder_model,
        'ready': 'unknown',
    }

    # client is accepted for future safe read-only probes; Phase 2 never calls it.
    _ = client

    return CatalogCapabilitiesResponse(
        package_version=package_version or _package_version(),
        backend=backend_name,
        connectivity=conn,
        catalog_writes_enabled=bool(config.enabled),
        catalog_reads_enabled=bool(getattr(config, 'reads_enabled', True)),
        uuid_namespace_configured=ns_configured,
        namespace_fingerprint=fp,
        identity_schema_version=IDENTITY_SCHEMA_VERSION,
        canonicalization_version=CANONICALIZATION_VERSION,
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        entity_types=sorted(ENTITY_TYPE_PREFIXES.keys()),
        entity_prefixes=dict(ENTITY_TYPE_PREFIXES),
        edge_types=sorted(CATALOG_EDGE_TYPES),
        endpoint_map=endpoint_map_export(),
        limits={
            'configured': {
                'max_entities_per_batch': config.max_entities_per_batch,
                'max_edges_per_batch': config.max_edges_per_batch,
                'max_provenance_links_per_batch': config.max_provenance_links_per_batch,
                'max_prepared_payload_bytes': config.max_prepared_payload_bytes,
                'max_active_plans': config.max_active_plans_per_group,
                'plan_ttl_seconds': config.plan_ttl_seconds,
                'prepared_chunk_bytes': config.prepared_chunk_bytes,
                'max_page_size': int(getattr(config, 'max_page_size', 100)),
            },
            'hard': {
                'max_entities_per_batch': HARD_MAX_ENTITIES_PER_BATCH,
                'max_edges_per_batch': HARD_MAX_EDGES_PER_BATCH,
                'max_provenance_links_per_batch': HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
                'max_prepared_payload_bytes': HARD_MAX_PREPARED_PAYLOAD_BYTES,
                'max_active_plans': HARD_MAX_ACTIVE_PLANS,
                'plan_ttl_seconds': HARD_PLAN_TTL_SECONDS,
                'max_page_size': HARD_MAX_PAGE_SIZE,
            },
        },
        embeddings=embeddings,
        neo4j_indexes=neo4j_indexes,
        features={
            # D-29 / P22: true only after 03A-06 live immutable proof + re-test green.
            'prepare_commit': True,
            'explicit_evidence_links': True,
            # D-33: True after accepted 03B-06 live preflip + coordinator final flip.
            # Runtime MUST NOT read .planning/* or 03B-GATE-RESULTS to decide this flag.
            'manifests': True,
            # Phase 4 (04-06): true only after registration + focused suite proofs (D-24).
            # Runtime MUST NOT read .planning/* or 04-GATE-RESULTS to decide this flag.
            'manifest_verification': True,
        },
    )
