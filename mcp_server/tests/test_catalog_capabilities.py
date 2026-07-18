"""CAPA-01..09: mutation-free catalog capabilities + get_status compatibility."""

from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.schema import CatalogConfig
from models.catalog_common import (
    CATALOG_EDGE_TYPES,
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
    IDENTITY_SCHEMA_VERSION,
)
from models.catalog_topology import endpoint_map_export
from services.catalog_identity import CANONICALIZATION_VERSION, CATALOG_SCHEMA_VERSION

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'


def test_namespace_fingerprint_none_when_missing():
    from services.catalog_capabilities import namespace_fingerprint

    assert namespace_fingerprint(None) is None


def test_namespace_fingerprint_stable_domain_separated_prefix():
    from services.catalog_capabilities import namespace_fingerprint

    fp = namespace_fingerprint(FIXED_NS)
    assert fp is not None
    assert len(fp) == 16
    assert all(c in '0123456789abcdef' for c in fp)
    assert fp == namespace_fingerprint(FIXED_NS)
    material = b'graphiti.catalog.nsfp.v1|' + FIXED_NS.bytes
    assert fp == hashlib.sha256(material).hexdigest()[:16]
    assert fp != str(FIXED_NS)
    assert fp != FIXED_NS.hex
    assert fp != FIXED_NS.bytes.hex()


def test_namespace_fingerprint_changes_with_namespace():
    from services.catalog_capabilities import namespace_fingerprint

    other = uuid.UUID('6ba7b811-9dad-11d1-80b4-00c04fd430c8')
    assert namespace_fingerprint(FIXED_NS) != namespace_fingerprint(other)


def test_build_capabilities_disabled_writes_missing_namespace():
    from services.catalog_capabilities import build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
    )
    assert caps.catalog_writes_enabled is False
    assert caps.catalog_reads_enabled is True
    assert caps.uuid_namespace_configured is False
    assert caps.namespace_fingerprint is None
    assert caps.connectivity == 'unknown'


def test_build_capabilities_versions_from_identity_constants():
    from services.catalog_capabilities import build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
    )
    assert caps.identity_schema_version is IDENTITY_SCHEMA_VERSION
    assert caps.canonicalization_version is CANONICALIZATION_VERSION
    assert caps.catalog_schema_version is CATALOG_SCHEMA_VERSION
    assert caps.canonicalization_version == CANONICALIZATION_VERSION
    assert caps.catalog_schema_version == CATALOG_SCHEMA_VERSION


def test_build_capabilities_endpoint_map_from_topology_export():
    from services.catalog_capabilities import build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
    )
    assert caps.endpoint_map == endpoint_map_export()
    assert set(caps.edge_types) == set(CATALOG_EDGE_TYPES)
    assert set(caps.entity_types) == set(ENTITY_TYPE_PREFIXES.keys())
    assert caps.entity_prefixes == dict(ENTITY_TYPE_PREFIXES)


def test_build_capabilities_limits_configured_and_hard():
    from services.catalog_capabilities import build_catalog_capabilities

    cfg = CatalogConfig(
        enabled=False,
        uuid_namespace=None,
        max_entities_per_batch=100,
        max_edges_per_batch=200,
        max_provenance_links_per_batch=300,
    )
    caps = build_catalog_capabilities(config=cfg, client=None)
    assert caps.limits['configured'] == {
        'max_entities_per_batch': 100,
        'max_edges_per_batch': 200,
        'max_provenance_links_per_batch': 300,
    }
    assert caps.limits['hard'] == {
        'max_entities_per_batch': HARD_MAX_ENTITIES_PER_BATCH,
        'max_edges_per_batch': HARD_MAX_EDGES_PER_BATCH,
        'max_provenance_links_per_batch': HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
        'max_prepared_payload_bytes': 0,
        'max_active_plans': 0,
        'plan_ttl_seconds': 0,
    }


def test_build_capabilities_features_phase_truthful():
    from services.catalog_capabilities import build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
    )
    assert caps.features == {
        'prepare_commit': False,
        'explicit_evidence_links': True,
        'manifests': False,
        'manifest_verification': False,
    }


def test_build_capabilities_redacts_namespace_and_secrets():
    from services.catalog_capabilities import build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS)),
        client=None,
        backend='neo4j',
        package_version='1.0.2',
        embedder_provider='openai',
        embedder_model='text-embedding-3-small',
    )
    dumped = caps.model_dump()
    assert 'uuid_namespace' not in dumped
    assert 'password' not in dumped
    assert 'api_key' not in dumped
    blob = str(dumped).lower()
    assert str(FIXED_NS).lower() not in blob
    assert FIXED_NS.hex.lower() not in blob
    assert 'sk-' not in blob
    assert caps.uuid_namespace_configured is True
    assert caps.namespace_fingerprint is not None
    assert caps.namespace_fingerprint != str(FIXED_NS)
    assert caps.catalog_writes_enabled is True


def test_build_capabilities_unknown_readiness_without_client_mutation():
    from services.catalog_capabilities import build_catalog_capabilities

    driver = MagicMock()
    driver.execute_write = AsyncMock()
    driver.build_indices_and_constraints = AsyncMock()
    client = SimpleNamespace(driver=driver)

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=client,
        backend='neo4j',
        embedder_provider='openai',
    )
    assert caps.embeddings['ready'] == 'unknown'
    assert caps.neo4j_indexes == 'unknown'
    driver.execute_write.assert_not_called()
    driver.build_indices_and_constraints.assert_not_called()


def test_build_capabilities_non_neo4j_indexes_na():
    from services.catalog_capabilities import build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
        backend='falkordb',
    )
    assert caps.neo4j_indexes == 'n/a'
    assert caps.connectivity == 'unknown'


def test_build_capabilities_no_driver_call_when_client_none():
    from services.catalog_capabilities import build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
    )
    assert caps.package_version
    assert caps.backend is None or isinstance(caps.backend, str)
