"""Mutation-free catalog capabilities builder (CAPA-01..08).

No Neo4j write, schema ensure, index repair, store, or control-plane side effects.
Truthful readiness probes are read-only: raw Neo4j verify_connectivity,
SHOW CONSTRAINTS inspect, and Ollama GET /api/tags only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import urllib.request
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
from services.catalog_store import CatalogNeo4jStore

logger = logging.getLogger(__name__)

Connectivity = Literal['ok', 'error', 'unknown']
IndexReadiness = Literal['ready', 'unknown', 'n/a']
EmbeddingReady = Literal['ready', 'error', 'unknown']

# Real plan hard ceilings (PLAN-08 / D-29). features.prepare_commit flips true only after
# 03A-06 live immutable proof on final HEAD.
HARD_MAX_PREPARED_PAYLOAD_BYTES = _COMMON_HARD_MAX_PREPARED_PAYLOAD_BYTES
HARD_MAX_ACTIVE_PLANS = HARD_MAX_ACTIVE_PLANS_PER_GROUP
HARD_PLAN_TTL_SECONDS = _COMMON_HARD_PLAN_TTL_SECONDS
# Phase 4 (D-04/D-24): hard page ceiling for diagnostic list tools.
HARD_MAX_PAGE_SIZE = 500

# Bounded read-only probe timeout (pinned).
PROBE_TIMEOUT_SECONDS = 2.0


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


def normalize_ollama_model_name(name: str | None) -> str:
    """Normalize Ollama model name for presence checks (strip + casefold)."""
    if not name:
        return ''
    return str(name).strip().casefold()


def ollama_model_present(configured: str | None, tags_names: list[str]) -> bool:
    """True when configured model is present under documented name normalization.

    Rules:
    - strip whitespace + casefold both sides
    - if configured has tag (`name:tag`), require exact full match
    - if configured has no tag, accept bare name OR `bare:latest`
    """
    cfg = normalize_ollama_model_name(configured)
    if not cfg:
        return False
    normalized_tags = [normalize_ollama_model_name(n) for n in tags_names if n]
    if ':' in cfg:
        return cfg in normalized_tags
    return cfg in normalized_tags or f'{cfg}:latest' in normalized_tags


def build_catalog_capabilities(
    *,
    config: CatalogConfig,
    client: Any | None = None,
    backend: str | None = None,
    package_version: str | None = None,
    connectivity: Connectivity | None = None,
    embedder_provider: str | None = None,
    embedder_model: str | None = None,
    embedder_dimensions: int | None = None,
    neo4j_indexes: IndexReadiness | None = None,
    embeddings_ready: EmbeddingReady | None = None,
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

    if neo4j_indexes is not None:
        indexes: IndexReadiness = neo4j_indexes
    elif backend_name == 'neo4j' or backend_name is None:
        indexes = 'unknown'
    else:
        indexes = 'n/a'

    emb_ready: EmbeddingReady = embeddings_ready if embeddings_ready is not None else 'unknown'
    embeddings: dict[str, Any] = {
        'provider': embedder_provider,
        'model': embedder_model,
        'ready': emb_ready,
    }
    if embedder_dimensions is not None:
        embeddings['dimensions'] = embedder_dimensions

    # client is accepted for future safe read-only probes; pure path never calls it.
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
        neo4j_indexes=indexes,
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


async def _probe_connectivity(client: Any) -> Connectivity:
    """Bounded Neo4j connectivity without exception-text logging wrappers."""
    driver = getattr(client, 'driver', None)
    raw_client = getattr(driver, 'client', None)
    verify = getattr(raw_client, 'verify_connectivity', None)
    if not callable(verify):
        return 'unknown'
    try:
        result = verify()
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            await asyncio.wait_for(result, timeout=PROBE_TIMEOUT_SECONDS)
        return 'ok'
    except Exception as exc:
        logger.warning(
            'catalog capabilities connectivity probe failed reason=%s',
            type(exc).__name__,
        )
        return 'error'


class _RawNeo4jReadExecutor:
    """Minimal adapter that bypasses exception-text logging in Graphiti's wrapper."""

    def __init__(self, driver: Any) -> None:
        self._client = getattr(driver, 'client', None)
        self._database = getattr(driver, '_database', None)

    async def execute_query(self, query: str, **kwargs: Any) -> Any:
        execute = getattr(self._client, 'execute_query', None)
        if not callable(execute):
            raise RuntimeError('raw Neo4j execute_query unavailable')
        params = dict(kwargs.get('params') or {})
        result = execute(query, parameters_=params, database_=self._database)
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            return await result
        return result


async def _probe_neo4j_indexes(client: Any, backend: str | None) -> IndexReadiness:
    """Read-only 14-constraint inspect. Never ensure/CREATE."""
    if backend != 'neo4j':
        if backend is None:
            return 'unknown'
        return 'n/a'

    driver = getattr(client, 'driver', None)
    if driver is None:
        return 'unknown'

    store = CatalogNeo4jStore()
    try:
        readiness = await asyncio.wait_for(
            store.inspect_catalog_v2_schema_readiness(_RawNeo4jReadExecutor(driver)),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        # SHOW attempted and raised, or timed out → unknown (connectivity separate).
        logger.warning(
            'catalog capabilities schema inspect failed reason=%s',
            type(exc).__name__,
        )
        return 'unknown'

    if readiness.get('ready') is True:
        return 'ready'
    return 'unknown'


def _fetch_ollama_tags(url: str) -> tuple[int, Any]:
    """GET Ollama tags without third-party request logging."""
    request = urllib.request.Request(url, method='GET')
    with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
        return response.status, response.read()


async def _probe_ollama_embeddings_ready(
    *,
    provider: str | None,
    model: str | None,
    api_url: str | None,
) -> EmbeddingReady:
    """Ollama readiness via GET /api/tags only. Never /api/embed or embedder.create."""
    if provider != 'ollama':
        return 'unknown'
    if not api_url:
        return 'unknown'

    base = str(api_url).rstrip('/')
    # Never log raw URL (redaction).
    tags_path = '/api/tags'
    try:
        status, raw_payload = await asyncio.wait_for(
            asyncio.to_thread(_fetch_ollama_tags, f'{base}{tags_path}'),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        if status != 200:
            return 'error'
        payload = json.loads(raw_payload)
        models = payload.get('models') if isinstance(payload, dict) else None
        names: list[str] = []
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict) and item.get('name'):
                    names.append(str(item['name']))
                elif isinstance(item, str):
                    names.append(item)
        if ollama_model_present(model, names):
            return 'ready'
        return 'error'
    except Exception as exc:
        logger.warning(
            'catalog capabilities ollama tags probe failed reason=%s',
            type(exc).__name__,
        )
        return 'error'


async def build_catalog_capabilities_async(
    *,
    config: CatalogConfig,
    client: Any | None = None,
    backend: str | None = None,
    package_version: str | None = None,
    embedder_provider: str | None = None,
    embedder_model: str | None = None,
    embedder_dimensions: int | None = None,
    ollama_api_url: str | None = None,
) -> CatalogCapabilitiesResponse:
    """Capabilities with bounded read-only probes overlaid on pure config view.

    Never calls get_client/initialize/build_indices/ensure_*/embedder.create/LLM/queue.
    Schema Cypher allowlist: SHOW CONSTRAINTS body only.
    """
    connectivity: Connectivity = 'unknown'
    indexes: IndexReadiness | None = None
    emb_ready: EmbeddingReady | None = None

    if client is not None and backend == 'neo4j':
        connectivity = await _probe_connectivity(client)
        indexes = await _probe_neo4j_indexes(client, backend)
    elif client is not None and backend is not None and backend != 'neo4j':
        # Non-neo4j: indexes n/a; connectivity remains unknown (no portable probe).
        indexes = 'n/a'
    elif backend is not None and backend != 'neo4j':
        indexes = 'n/a'

    emb_ready = await _probe_ollama_embeddings_ready(
        provider=embedder_provider,
        model=embedder_model,
        api_url=ollama_api_url,
    )

    return build_catalog_capabilities(
        config=config,
        client=client,
        backend=backend,
        package_version=package_version,
        connectivity=connectivity,
        embedder_provider=embedder_provider,
        embedder_model=embedder_model,
        embedder_dimensions=embedder_dimensions,
        neo4j_indexes=indexes,
        embeddings_ready=emb_ready,
    )
