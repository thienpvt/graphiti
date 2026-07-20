"""CAPA-01..09: mutation-free catalog capabilities + get_status compatibility."""

from __future__ import annotations

import hashlib
import json
import uuid
from types import SimpleNamespace
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
from models.catalog_responses import CatalogCapabilitiesResponse
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


def test_build_capabilities_reads_enabled_follows_config():
    """GATE-01/02: catalog_reads_enabled tracks config.reads_enabled (not hardcoded)."""
    from services.catalog_capabilities import HARD_MAX_PAGE_SIZE, build_catalog_capabilities

    off = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, reads_enabled=False, uuid_namespace=None),
        client=None,
    )
    assert off.catalog_writes_enabled is False
    assert off.catalog_reads_enabled is False
    assert off.features['manifest_verification'] is True
    assert off.limits['hard']['max_page_size'] == HARD_MAX_PAGE_SIZE == 500
    assert off.limits['configured']['max_page_size'] == 100

    on = build_catalog_capabilities(
        config=CatalogConfig(
            enabled=False,
            reads_enabled=True,
            max_page_size=50,
            uuid_namespace=None,
        ),
        client=None,
    )
    assert on.catalog_reads_enabled is True
    assert on.limits['configured']['max_page_size'] == 50
    assert on.limits['hard']['max_page_size'] == 500


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
    from models.catalog_common import (
        DEFAULT_MAX_ACTIVE_PLANS_PER_GROUP,
        DEFAULT_PLAN_TTL_SECONDS,
        DEFAULT_PREPARED_CHUNK_BYTES,
        DEFAULT_PREPARED_PAYLOAD_BYTES,
        HARD_MAX_ACTIVE_PLANS_PER_GROUP,
        HARD_MAX_PREPARED_PAYLOAD_BYTES,
        HARD_PLAN_TTL_SECONDS,
    )
    from services.catalog_capabilities import (
        HARD_MAX_ACTIVE_PLANS,
        build_catalog_capabilities,
    )
    from services.catalog_capabilities import (
        HARD_MAX_PREPARED_PAYLOAD_BYTES as CAP_HARD_PAYLOAD,
    )
    from services.catalog_capabilities import (
        HARD_PLAN_TTL_SECONDS as CAP_HARD_TTL,
    )

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
        'max_prepared_payload_bytes': DEFAULT_PREPARED_PAYLOAD_BYTES,
        'max_active_plans': DEFAULT_MAX_ACTIVE_PLANS_PER_GROUP,
        'plan_ttl_seconds': DEFAULT_PLAN_TTL_SECONDS,
        'prepared_chunk_bytes': DEFAULT_PREPARED_CHUNK_BYTES,
        'max_page_size': 100,
    }
    assert caps.limits['hard'] == {
        'max_entities_per_batch': HARD_MAX_ENTITIES_PER_BATCH,
        'max_edges_per_batch': HARD_MAX_EDGES_PER_BATCH,
        'max_provenance_links_per_batch': HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
        'max_prepared_payload_bytes': HARD_MAX_PREPARED_PAYLOAD_BYTES,
        'max_active_plans': HARD_MAX_ACTIVE_PLANS_PER_GROUP,
        'plan_ttl_seconds': HARD_PLAN_TTL_SECONDS,
        'max_page_size': 500,
    }
    # Module re-exports match catalog_common hard ceilings (non-zero).
    assert CAP_HARD_PAYLOAD == HARD_MAX_PREPARED_PAYLOAD_BYTES == 16_777_216
    assert CAP_HARD_TTL == HARD_PLAN_TTL_SECONDS == 86400
    assert HARD_MAX_ACTIVE_PLANS == HARD_MAX_ACTIVE_PLANS_PER_GROUP == 32
    assert 'max_page_size' in caps.limits['configured']
    assert 'max_page_size' in caps.limits['hard']


def test_build_capabilities_exposes_pagination_limits():
    from services.catalog_capabilities import HARD_MAX_PAGE_SIZE, build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
    )
    # Configured default 100; hard ceiling 500 (D-04 / GATE page authority).
    assert caps.limits['configured']['max_page_size'] == 100
    assert caps.limits['hard']['max_page_size'] == HARD_MAX_PAGE_SIZE == 500


def test_build_capabilities_features_phase_truthful():
    from services.catalog_capabilities import build_catalog_capabilities

    caps = build_catalog_capabilities(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
    )
    # D-29/D-33: prepare_commit true; manifests true post 03B-06 flip; verification false.
    assert caps.features == {
        'prepare_commit': True,
        'explicit_evidence_links': True,
        'manifests': True,
        'manifest_verification': True,
    }
    assert caps.features['prepare_commit'] is True
    assert caps.features['manifests'] is True
    assert caps.features['manifest_verification'] is True
    assert caps.limits['hard']['max_page_size'] == 500


def test_build_capabilities_plan_limits_nonzero_prepare_commit_true():
    """PLAN-08/20 Wave 5: real HARD plan ceilings; prepare_commit true post live proof."""
    from models.catalog_common import (
        HARD_MAX_ACTIVE_PLANS_PER_GROUP,
        HARD_MAX_PREPARED_PAYLOAD_BYTES,
        HARD_PLAN_TTL_SECONDS,
    )
    from services.catalog_capabilities import (
        HARD_MAX_ACTIVE_PLANS,
        build_catalog_capabilities,
    )
    from services.catalog_capabilities import (
        HARD_MAX_PREPARED_PAYLOAD_BYTES as CAP_HARD_PAYLOAD,
    )
    from services.catalog_capabilities import (
        HARD_PLAN_TTL_SECONDS as CAP_HARD_TTL,
    )

    caps = build_catalog_capabilities(
        config=CatalogConfig(
            enabled=True,
            uuid_namespace=str(FIXED_NS),
            plan_ttl_seconds=1800,
            max_prepared_payload_bytes=1_048_576,
            max_active_plans_per_group=4,
            prepared_chunk_bytes=65_536,
        ),
        client=None,
    )
    assert CAP_HARD_PAYLOAD == HARD_MAX_PREPARED_PAYLOAD_BYTES
    assert CAP_HARD_PAYLOAD > 0
    assert HARD_MAX_ACTIVE_PLANS == HARD_MAX_ACTIVE_PLANS_PER_GROUP
    assert CAP_HARD_TTL == HARD_PLAN_TTL_SECONDS
    assert caps.limits['hard']['max_prepared_payload_bytes'] == HARD_MAX_PREPARED_PAYLOAD_BYTES
    assert caps.limits['hard']['max_active_plans'] == HARD_MAX_ACTIVE_PLANS_PER_GROUP
    assert caps.limits['hard']['plan_ttl_seconds'] == HARD_PLAN_TTL_SECONDS
    assert caps.limits['configured']['plan_ttl_seconds'] == 1800
    assert caps.limits['configured']['max_prepared_payload_bytes'] == 1_048_576
    assert caps.limits['configured']['max_active_plans'] == 4
    assert caps.limits['configured']['prepared_chunk_bytes'] == 65_536
    assert caps.features['prepare_commit'] is True
    assert caps.features['manifests'] is True
    assert caps.features['manifest_verification'] is True
    assert caps.limits['hard']['max_page_size'] == 500


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
        client=None,
        get_client=AsyncMock(
            side_effect=AssertionError('capabilities must not require get_client success')
        ),
    )
    monkeypatch.setattr(server, 'graphiti_service', mock_service)

    result = await server.get_catalog_capabilities()
    assert isinstance(result, CatalogCapabilitiesResponse)
    dumped = result.model_dump()
    assert dumped['catalog_writes_enabled'] is False
    assert dumped['uuid_namespace_configured'] is False
    assert dumped['namespace_fingerprint'] is None
    assert dumped['connectivity'] == 'unknown'
    assert dumped['neo4j_indexes'] == 'unknown'
    assert dumped['features']['prepare_commit'] is True
    assert dumped['features']['explicit_evidence_links'] is True
    assert dumped['features']['manifests'] is True
    assert dumped['features']['manifest_verification'] is True
    assert 'uuid_namespace' not in dumped
    mock_service.get_client.assert_not_called()


@pytest.mark.asyncio
async def test_get_catalog_capabilities_zero_mutation_spies(monkeypatch):
    server = _mcp_server()
    driver = MagicMock()
    driver.client.verify_connectivity = AsyncMock(return_value=None)
    driver.client.execute_query = AsyncMock(return_value=([], None, None))
    driver.execute_write = AsyncMock()
    driver.build_indices_and_constraints = AsyncMock()
    driver.health_check = AsyncMock(side_effect=AssertionError('health_check forbidden'))
    driver.execute_query = AsyncMock(side_effect=AssertionError('wrapper execute_query forbidden'))
    client = SimpleNamespace(driver=driver)
    cfg = CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))
    mock_service = SimpleNamespace(
        config=SimpleNamespace(
            catalog_upsert=cfg,
            database=SimpleNamespace(provider='neo4j'),
            embedder=SimpleNamespace(provider='openai', model=None, providers=None),
        ),
        client=client,
        get_client=AsyncMock(side_effect=AssertionError('must not call get_client')),
        initialize=AsyncMock(side_effect=AssertionError('must not initialize')),
    )
    monkeypatch.setattr(server, 'graphiti_service', mock_service)

    result = await server.get_catalog_capabilities()
    assert isinstance(result, CatalogCapabilitiesResponse)
    dumped = result.model_dump()
    assert dumped['catalog_writes_enabled'] is True
    assert dumped['namespace_fingerprint'] is not None
    mock_service.get_client.assert_not_called()
    driver.execute_query.assert_not_called()
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


# ---------------------------------------------------------------------------
# Truthful readiness probes (260719-udj)
# ---------------------------------------------------------------------------

_REQUIRED_CONSTRAINTS = (
    ('catalog_entity_identity_unique', 'NODE', 'Entity', {'uuid', 'group_id'}),
    ('catalog_relates_to_identity_unique', 'RELATIONSHIP', 'RELATES_TO', {'uuid', 'group_id'}),
    ('catalog_episodic_identity_unique', 'NODE', 'Episodic', {'uuid', 'group_id'}),
    ('catalog_mentions_identity_unique', 'RELATIONSHIP', 'MENTIONS', {'uuid', 'group_id'}),
    ('catalog_batch_identity_unique', 'NODE', 'CatalogIngestBatch', {'uuid', 'group_id'}),
    ('catalog_prepared_plan_identity_unique', 'NODE', 'CatalogPreparedPlan', {'uuid', 'group_id'}),
    (
        'catalog_prepared_plan_token_digest_unique',
        'NODE',
        'CatalogPreparedPlan',
        {'token_digest'},
    ),
    (
        'catalog_prepared_plan_chunk_identity_unique',
        'NODE',
        'CatalogPreparedPlanChunk',
        {'uuid', 'group_id'},
    ),
    (
        'catalog_prepared_plan_chunk_index_unique',
        'NODE',
        'CatalogPreparedPlanChunk',
        {'plan_uuid', 'group_id', 'chunk_index'},
    ),
    ('catalog_evidence_link_identity_unique', 'NODE', 'CatalogEvidenceLink', {'uuid', 'group_id'}),
    ('catalog_evidence_link_key_unique', 'NODE', 'CatalogEvidenceLink', {'group_id', 'link_key'}),
    (
        'catalog_batch_manifest_identity_unique',
        'NODE',
        'CatalogBatchManifest',
        {'uuid', 'group_id'},
    ),
    (
        'catalog_batch_manifest_chunk_identity_unique',
        'NODE',
        'CatalogBatchManifestChunk',
        {'uuid', 'group_id'},
    ),
    (
        'catalog_batch_manifest_chunk_index_unique',
        'NODE',
        'CatalogBatchManifestChunk',
        {'manifest_uuid', 'group_id', 'chunk_index'},
    ),
)

_FORBIDDEN_CYPHER_KEYWORDS = (
    'CREATE',
    'DROP',
    'ALTER',
    'MERGE',
    'SET',
    'DELETE',
    'REMOVE',
    'DETACH',
    'FOREACH',
    'LOAD CSV',
    'CALL DBMS',
    'CALL DB.CREATE',
)


def _constraint_rows(missing: set[str] | None = None) -> list[dict]:
    missing = missing or set()
    rows = []
    for name, etype, label, props in _REQUIRED_CONSTRAINTS:
        if name in missing:
            continue
        rows.append(
            {
                'name': name,
                'type': 'UNIQUENESS',
                'entityType': etype,
                'labelsOrTypes': [label],
                'properties': sorted(props),
            }
        )
    return rows


def test_probe_timeout_seconds_pinned():
    from services.catalog_capabilities import PROBE_TIMEOUT_SECONDS

    assert PROBE_TIMEOUT_SECONDS == 2.0


def test_ollama_model_present_normalization():
    from services.catalog_capabilities import ollama_model_present

    assert ollama_model_present('qwen3-embedding:0.6b', ['qwen3-embedding:0.6b']) is True
    assert ollama_model_present('qwen3-embedding', ['qwen3-embedding:latest']) is True
    assert ollama_model_present('qwen3-embedding', ['qwen3-embedding']) is True
    assert ollama_model_present('Qwen3-Embedding:0.6B', ['qwen3-embedding:0.6b']) is True
    assert ollama_model_present('qwen3-embedding:0.6b', ['qwen3-embedding:latest']) is False
    assert ollama_model_present('missing', ['other']) is False


@pytest.mark.asyncio
async def test_inspect_catalog_v2_schema_readiness_all_present():
    from services.catalog_store import CatalogNeo4jStore

    store = CatalogNeo4jStore()
    assert store._schema_ready is False
    rows = _constraint_rows()
    assert len(rows) == 14
    executor = SimpleNamespace(execute_query=AsyncMock(return_value=(rows, None, None)))
    result = await store.inspect_catalog_v2_schema_readiness(executor)
    assert result == {
        'identity': True,
        'plan': True,
        'evidence_manifest': True,
        'ready': True,
    }
    assert store._schema_ready is False
    assert store._plan_schema_ready is False
    assert store._evidence_manifest_schema_ready is False
    for call in executor.execute_query.await_args_list:
        cypher = call.args[0] if call.args else ''
        upper = cypher.upper()
        assert 'SHOW CONSTRAINTS' in upper
        for kw in _FORBIDDEN_CYPHER_KEYWORDS:
            assert kw not in upper, f'forbidden {kw} in {cypher!r}'


@pytest.mark.asyncio
async def test_inspect_catalog_v2_schema_readiness_missing_one():
    from services.catalog_store import CatalogNeo4jStore

    store = CatalogNeo4jStore()
    rows = _constraint_rows(missing={'catalog_entity_identity_unique'})
    executor = SimpleNamespace(execute_query=AsyncMock(return_value=(rows, None, None)))
    result = await store.inspect_catalog_v2_schema_readiness(executor)
    assert result['identity'] is False
    assert result['ready'] is False


@pytest.mark.asyncio
async def test_build_async_connectivity_ok_raw_driver():
    from services.catalog_capabilities import build_catalog_capabilities_async

    driver = MagicMock()
    driver.client.verify_connectivity = AsyncMock(return_value=None)
    driver.client.execute_query = AsyncMock(return_value=(_constraint_rows(), None, None))
    driver.health_check = AsyncMock(side_effect=AssertionError('health_check forbidden'))
    driver.execute_query = AsyncMock(side_effect=AssertionError('wrapper execute_query forbidden'))
    driver.execute_write = AsyncMock()
    driver.build_indices_and_constraints = AsyncMock()
    client = SimpleNamespace(driver=driver)
    caps = await build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=client,
        backend='neo4j',
        embedder_provider='openai',
        embedder_model='text-embedding-3-small',
    )
    assert caps.connectivity == 'ok'
    assert caps.neo4j_indexes == 'ready'
    assert caps.embeddings['ready'] == 'unknown'
    driver.client.verify_connectivity.assert_awaited_once()
    driver.health_check.assert_not_called()
    driver.execute_write.assert_not_called()
    driver.build_indices_and_constraints.assert_not_called()


@pytest.mark.asyncio
async def test_build_async_connectivity_error_on_raw_driver_failure(caplog, capsys):
    from services.catalog_capabilities import build_catalog_capabilities_async

    driver = MagicMock()
    driver.client.verify_connectivity = AsyncMock(
        side_effect=RuntimeError('secret-bearing endpoint')
    )
    driver.client.execute_query = AsyncMock(return_value=(_constraint_rows(), None, None))
    driver.health_check = AsyncMock(side_effect=AssertionError('health_check forbidden'))
    driver.execute_query = AsyncMock(side_effect=AssertionError('wrapper execute_query forbidden'))
    client = SimpleNamespace(driver=driver)
    caps = await build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=client,
        backend='neo4j',
        embedder_provider='openai',
    )
    assert caps.connectivity == 'error'
    assert caps.neo4j_indexes == 'ready'
    driver.health_check.assert_not_called()
    captured = capsys.readouterr()
    logs = '\n'.join(record.getMessage() for record in caplog.records)
    assert 'secret-bearing endpoint' not in captured.out + captured.err + logs


@pytest.mark.asyncio
async def test_build_async_schema_unknown_when_missing_or_show_raises(caplog, capsys):
    from services.catalog_capabilities import build_catalog_capabilities_async

    driver = MagicMock()
    driver.client.verify_connectivity = AsyncMock(return_value=None)
    driver.client.execute_query = AsyncMock(
        return_value=(_constraint_rows(missing={'catalog_batch_identity_unique'}), None, None)
    )
    driver.health_check = AsyncMock(side_effect=AssertionError('health_check forbidden'))
    driver.execute_query = AsyncMock(side_effect=AssertionError('wrapper execute_query forbidden'))
    client = SimpleNamespace(driver=driver)
    caps = await build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=client,
        backend='neo4j',
    )
    assert caps.neo4j_indexes == 'unknown'

    driver2 = MagicMock()
    driver2.client.verify_connectivity = AsyncMock(return_value=None)
    driver2.client.execute_query = AsyncMock(
        side_effect=RuntimeError('schema secret-bearing endpoint')
    )
    driver2.health_check = AsyncMock(side_effect=AssertionError('health_check forbidden'))
    driver2.execute_query = AsyncMock(side_effect=AssertionError('wrapper execute_query forbidden'))
    client2 = SimpleNamespace(driver=driver2)
    caps2 = await build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=client2,
        backend='neo4j',
    )
    assert caps2.neo4j_indexes == 'unknown'
    assert caps2.connectivity == 'ok'
    captured = capsys.readouterr()
    logs = '\n'.join(record.getMessage() for record in caplog.records)
    assert 'schema secret-bearing endpoint' not in captured.out + captured.err + logs


@pytest.mark.asyncio
async def test_build_async_non_neo4j_indexes_na():
    from services.catalog_capabilities import build_catalog_capabilities_async

    caps = await build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
        backend='falkordb',
        embedder_provider='openai',
    )
    assert caps.neo4j_indexes == 'n/a'
    assert caps.connectivity == 'unknown'


@pytest.mark.asyncio
async def test_build_async_ollama_ready_and_missing_and_http_error(monkeypatch, caplog, capsys):
    from services import catalog_capabilities as cap_mod

    current = {'status': 200, 'payload': {'models': [{'name': 'qwen3-embedding:0.6b'}]}}

    def fetch(url: str):
        assert url.endswith('/api/tags')
        assert 'password' not in url
        return current['status'], json.dumps(current['payload']).encode()

    monkeypatch.setattr(cap_mod, '_fetch_ollama_tags', fetch)
    sensitive_url = 'http://sensitive-host:11434'
    caps = await cap_mod.build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
        backend='neo4j',
        embedder_provider='ollama',
        embedder_model='qwen3-embedding:0.6b',
        ollama_api_url=sensitive_url,
    )
    assert caps.embeddings['ready'] == 'ready'
    assert caps.embeddings['provider'] == 'ollama'
    assert caps.embeddings['model'] == 'qwen3-embedding:0.6b'
    blob = str(caps.model_dump()).lower()
    assert '11434' not in blob
    assert 'http://' not in blob
    captured = capsys.readouterr()
    logs = '\n'.join(record.getMessage() for record in caplog.records)
    assert sensitive_url not in captured.out + captured.err + logs

    # missing model → error
    current.update(status=200, payload={'models': [{'name': 'other:latest'}]})
    caps_miss = await cap_mod.build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
        backend='neo4j',
        embedder_provider='ollama',
        embedder_model='qwen3-embedding:0.6b',
        ollama_api_url='http://127.0.0.1:11434',
    )
    assert caps_miss.embeddings['ready'] == 'error'

    # http non-200 → error
    current.update(status=500, payload={})
    caps_err = await cap_mod.build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
        backend='neo4j',
        embedder_provider='ollama',
        embedder_model='qwen3-embedding:0.6b',
        ollama_api_url='http://127.0.0.1:11434',
    )
    assert caps_err.embeddings['ready'] == 'error'


@pytest.mark.asyncio
async def test_build_async_openai_no_http(monkeypatch):
    from services import catalog_capabilities as cap_mod

    called = {'n': 0}

    def fetch(url: str):
        assert url
        called['n'] += 1
        raise AssertionError('openai must not HTTP probe')

    monkeypatch.setattr(cap_mod, '_fetch_ollama_tags', fetch)
    caps = await cap_mod.build_catalog_capabilities_async(
        config=CatalogConfig(enabled=False, uuid_namespace=None),
        client=None,
        backend='neo4j',
        embedder_provider='openai',
        embedder_model='text-embedding-3-small',
        ollama_api_url='http://127.0.0.1:11434',
    )
    assert caps.embeddings['ready'] == 'unknown'
    assert called['n'] == 0


@pytest.mark.asyncio
async def test_build_async_cypher_allowlist_and_forbidden_spies():
    from services.catalog_capabilities import build_catalog_capabilities_async

    captured: list[str] = []

    async def capture_query(cypher, **kwargs):
        assert kwargs == {'parameters_': {}, 'database_': 'neo4j'}
        captured.append(cypher)
        return (_constraint_rows(), None, None)

    driver = SimpleNamespace(
        client=SimpleNamespace(
            verify_connectivity=AsyncMock(return_value=None),
            execute_query=AsyncMock(side_effect=capture_query),
        ),
        _database='neo4j',
        health_check=AsyncMock(side_effect=AssertionError('health_check forbidden')),
        execute_query=AsyncMock(side_effect=AssertionError('wrapper execute_query forbidden')),
        execute_write=AsyncMock(),
        build_indices_and_constraints=AsyncMock(),
    )
    client = SimpleNamespace(
        driver=driver,
        embedder=SimpleNamespace(create=AsyncMock(), create_batch=AsyncMock()),
    )
    store_spies = {
        'ensure_uuid_uniqueness_constraints': AsyncMock(),
        'ensure_plan_schema': AsyncMock(),
        'ensure_evidence_manifest_schema': AsyncMock(),
    }
    # Patch ensure methods on CatalogNeo4jStore instances used by inspect
    from services import catalog_store as store_mod

    orig_init = store_mod.CatalogNeo4jStore.__init__

    def _init(self, *a, **k):
        orig_init(self, *a, **k)
        self.ensure_uuid_uniqueness_constraints = store_spies['ensure_uuid_uniqueness_constraints']
        self.ensure_plan_schema = store_spies['ensure_plan_schema']
        self.ensure_evidence_manifest_schema = store_spies['ensure_evidence_manifest_schema']

    store_mod.CatalogNeo4jStore.__init__ = _init  # type: ignore[method-assign]
    try:
        caps = await build_catalog_capabilities_async(
            config=CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS)),
            client=client,
            backend='neo4j',
            embedder_provider='openai',
        )
    finally:
        store_mod.CatalogNeo4jStore.__init__ = orig_init  # type: ignore[method-assign]

    assert caps.connectivity == 'ok'
    assert caps.neo4j_indexes == 'ready'
    assert captured
    for cypher in captured:
        upper = cypher.upper()
        for kw in _FORBIDDEN_CYPHER_KEYWORDS:
            assert kw not in upper, f'forbidden {kw} in {cypher!r}'
        allow = 'SHOW CONSTRAINTS' in upper and 'YIELD' in upper and 'RETURN' in upper
        assert allow, f'non-allowlisted cypher: {cypher!r}'
    driver.execute_query.assert_not_called()
    driver.execute_write.assert_not_called()
    driver.build_indices_and_constraints.assert_not_called()
    client.embedder.create.assert_not_called()
    client.embedder.create_batch.assert_not_called()
    store_spies['ensure_uuid_uniqueness_constraints'].assert_not_called()
    store_spies['ensure_plan_schema'].assert_not_called()
    store_spies['ensure_evidence_manifest_schema'].assert_not_called()


@pytest.mark.asyncio
async def test_mcp_service_none_error_no_probes(monkeypatch):
    server = _mcp_server()
    monkeypatch.setattr(server, 'graphiti_service', None)
    result = await server.get_catalog_capabilities()
    # TypedDict ErrorResponse serializes as plain dict.
    if isinstance(result, dict):
        assert result.get('error') == 'Graphiti service not initialized'
    else:
        assert result.error == 'Graphiti service not initialized'


@pytest.mark.asyncio
async def test_mcp_client_none_unknown_no_get_client(monkeypatch):
    server = _mcp_server()
    cfg = CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))
    mock_service = SimpleNamespace(
        config=SimpleNamespace(
            catalog_upsert=cfg,
            database=SimpleNamespace(provider='neo4j'),
            embedder=SimpleNamespace(provider='openai', model='m', providers=None),
        ),
        client=None,
        get_client=AsyncMock(side_effect=AssertionError('get_client forbidden')),
        initialize=AsyncMock(side_effect=AssertionError('initialize forbidden')),
    )
    monkeypatch.setattr(server, 'graphiti_service', mock_service)
    result = await server.get_catalog_capabilities()
    assert isinstance(result, CatalogCapabilitiesResponse)
    assert result.connectivity == 'unknown'
    assert result.neo4j_indexes == 'unknown'
    mock_service.get_client.assert_not_called()
    mock_service.initialize.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_initialized_client_probes_ok(monkeypatch):
    server = _mcp_server()
    driver = MagicMock()
    driver.client.verify_connectivity = AsyncMock(return_value=None)
    driver.client.execute_query = AsyncMock(return_value=(_constraint_rows(), None, None))
    driver.health_check = AsyncMock(side_effect=AssertionError('health_check forbidden'))
    driver.execute_query = AsyncMock(side_effect=AssertionError('wrapper execute_query forbidden'))
    driver.execute_write = AsyncMock()
    driver.build_indices_and_constraints = AsyncMock()
    client = SimpleNamespace(driver=driver)
    cfg = CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))
    mock_service = SimpleNamespace(
        config=SimpleNamespace(
            catalog_upsert=cfg,
            database=SimpleNamespace(provider='neo4j'),
            embedder=SimpleNamespace(provider='openai', model='m', providers=None),
        ),
        client=client,
        get_client=AsyncMock(side_effect=AssertionError('get_client forbidden')),
    )
    monkeypatch.setattr(server, 'graphiti_service', mock_service)
    result = await server.get_catalog_capabilities()
    assert isinstance(result, CatalogCapabilitiesResponse)
    assert result.connectivity == 'ok'
    assert result.neo4j_indexes == 'ready'
    mock_service.get_client.assert_not_called()
    driver.execute_write.assert_not_called()
    dumped = str(result.model_dump()).lower()
    assert str(FIXED_NS).lower() not in dumped
    assert 'password' not in dumped
    assert 'api_key' not in dumped
    assert 'bolt://' not in dumped
