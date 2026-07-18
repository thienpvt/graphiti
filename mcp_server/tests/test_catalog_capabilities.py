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


# ---------------------------------------------------------------------------
# Task 2: MCP registration + get_status compatibility (CAPA-01/09)
# ---------------------------------------------------------------------------


def _mcp_server():
    import importlib

    return importlib.import_module('graphiti_mcp_server')


@pytest.mark.asyncio
async def test_mcp_tool_get_catalog_capabilities_registered():
    server = _mcp_server()
    assert hasattr(server, 'get_catalog_capabilities')
    assert callable(server.get_catalog_capabilities)
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    assert 'get_catalog_capabilities' in names


@pytest.mark.asyncio
async def test_get_catalog_capabilities_works_when_writes_disabled(monkeypatch):
    server = _mcp_server()
    cfg = CatalogConfig(enabled=False, uuid_namespace=None)
    mock_service = SimpleNamespace(
        config=SimpleNamespace(
            catalog_upsert=cfg,
            database=SimpleNamespace(provider='neo4j'),
            embedder=SimpleNamespace(provider='openai', model='text-embedding-3-small'),
        ),
        get_client=AsyncMock(
            side_effect=AssertionError('capabilities must not require get_client success')
        ),
    )
    monkeypatch.setattr(server, 'graphiti_service', mock_service)

    result = await server.get_catalog_capabilities()
    assert not isinstance(result, dict) or 'error' not in result
    dumped = result.model_dump() if hasattr(result, 'model_dump') else dict(result)
    assert dumped['catalog_writes_enabled'] is False
    assert dumped['uuid_namespace_configured'] is False
    assert dumped['namespace_fingerprint'] is None
    assert dumped['features']['prepare_commit'] is False
    assert dumped['features']['explicit_evidence_links'] is True
    assert 'uuid_namespace' not in dumped
    mock_service.get_client.assert_not_called()


@pytest.mark.asyncio
async def test_get_catalog_capabilities_zero_mutation_spies(monkeypatch):
    server = _mcp_server()
    driver = MagicMock()
    driver.execute_write = AsyncMock()
    driver.build_indices_and_constraints = AsyncMock()
    client = SimpleNamespace(driver=driver)
    cfg = CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))
    mock_service = SimpleNamespace(
        config=SimpleNamespace(
            catalog_upsert=cfg,
            database=SimpleNamespace(provider='neo4j'),
            embedder=SimpleNamespace(provider='openai', model=None),
        ),
        get_client=AsyncMock(return_value=client),
    )
    monkeypatch.setattr(server, 'graphiti_service', mock_service)

    result = await server.get_catalog_capabilities()
    dumped = result.model_dump() if hasattr(result, 'model_dump') else dict(result)
    assert dumped['catalog_writes_enabled'] is True
    assert dumped['namespace_fingerprint'] is not None
    # Optional get_client for non-mutating context is allowed; write paths forbidden.
    driver.execute_write.assert_not_called()
    driver.build_indices_and_constraints.assert_not_called()


@pytest.mark.asyncio
async def test_get_status_preserves_status_and_message_keys(monkeypatch):
    server = _mcp_server()
    assert server.StatusResponse.__annotations__.keys() >= {'status', 'message'}
    assert set(server.StatusResponse.__required_keys__) == {'status', 'message'}

    monkeypatch.setattr(server, 'graphiti_service', None)
    resp = await server.get_status()
    assert set(resp.keys()) == {'status', 'message'}
    assert resp['status'] == 'error'
    assert isinstance(resp['message'], str)


@pytest.mark.asyncio
async def test_mcp_registers_capabilities_plus_legacy_and_catalog_tools():
    server = _mcp_server()
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    # Write/read catalog tools preserved; capabilities is additive read tool.
    for required in (
        'upsert_typed_entities',
        'upsert_typed_edges',
        'resolve_typed_entities',
        'verify_catalog_batch',
        'upsert_provenance',
        'get_catalog_ingest_status',
        'upsert_catalog_batch',
        'get_catalog_capabilities',
        'get_status',
        'add_memory',
    ):
        assert required in names
    assert len(names) >= 22


def test_capabilities_source_omits_raw_namespace_logging():
    """Static: capabilities path never logs uuid_namespace material."""
    import ast
    from pathlib import Path

    src = Path(__file__).parent.parent / 'src'
    for rel in (
        'services/catalog_capabilities.py',
        'graphiti_mcp_server.py',
    ):
        tree = ast.parse((src / rel).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != 'logger':
                continue
            # Only inspect get_catalog_capabilities body in server module.
            # Fingerprint builder has no logger; server wrapper must not log namespace.
            text = ast.unparse(node)
            assert 'uuid_namespace' not in text
            assert 'GRAPHITI_CATALOG_UUID_NAMESPACE' not in text
