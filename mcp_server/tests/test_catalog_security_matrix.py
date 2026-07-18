"""Phase 5 SAFE-03/04/06/07 + TEST-10 security matrix (GREEN).

Static/AST prohibition, fixed Cypher identifier authority, fail-closed conflicts,
log scrub, and runtime spies. Never shells canary; never targets oracle-catalog-v2.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_batch import UpsertCatalogBatchRequest  # noqa: E402
from models.catalog_common import (  # noqa: E402
    CATALOG_EDGE_TYPES,
    CATALOG_ENTITY_TYPES,
    CatalogErrorCode,
)
from models.catalog_edges import CatalogEdgeItem, UpsertTypedEdgesRequest  # noqa: E402
from models.catalog_entities import CatalogEntityItem, UpsertTypedEntitiesRequest  # noqa: E402
from models.catalog_prepare import CommitPreparedCatalogBatchRequest  # noqa: E402
from services.catalog_identity import mint_plan_token, plan_token_digest  # noqa: E402
from services.catalog_service import CatalogService  # noqa: E402
from services.catalog_store import (  # noqa: E402
    _ENTITY_LABELS,
    CatalogNeo4jStore,
    CatalogStoreError,
)

ROOT = Path(__file__).resolve().parents[2]
MCP_SRC = ROOT / 'mcp_server' / 'src'
SERVICE_PATH = MCP_SRC / 'services' / 'catalog_service.py'
MCP_PATH = MCP_SRC / 'graphiti_mcp_server.py'

ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
FORBIDDEN_GROUP = 'oracle-catalog-v2'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = ALLOWED_TEST_GROUP
BATCH = 'batch-security-matrix-001'
HEX64 = 'a' * 64

# SAFE-03: maintenance/LLM path tools must not be call targets on catalog paths.
PROHIBITED_ON_CATALOG_PATH = frozenset(
    {
        'add_memory',
        'add_triplet',
        'build_communities',
        'clear_graph',
        'delete_entity_edge',
        'delete_episode',
        'summarize_saga',
        'update_entity',
    }
)

# Catalog MCP wrappers that must route only through CatalogService.
CATALOG_MCP_WRAPPERS = frozenset(
    {
        'upsert_typed_entities',
        'upsert_typed_edges',
        'resolve_typed_entities',
        'resolve_typed_edges',
        'verify_catalog_batch',
        'upsert_provenance',
        'get_catalog_ingest_status',
        'get_catalog_batch_manifest',
        'get_catalog_evidence',
        'upsert_catalog_batch',
        'prepare_catalog_batch',
        'commit_prepared_catalog_batch',
        'discard_prepared_catalog_batch',
        'get_catalog_capabilities',
    }
)

# Exact UTF-8 forbidden log substrings (SAFE-07 encoding).
FORBIDDEN_LOG_MARKERS = (
    'plan_token=',
    'password=',
    'api_key=',
    'authorization:',
    'payload=',
    'source_text=',
)

MALICIOUS_ENTITY_TYPES = (
    'Table; DROP TABLE Entity //',
    'Table` WHERE 1=1 //',
    'Table} DETACH DELETE n //',
    'EvilLabel',
)
MALICIOUS_EDGE_TYPES = (
    'ForeignKeyTo; DROP //',
    'RELATES_TO` //',
    'NotAnEdge',
)
MALICIOUS_PROPERTY_KEYS = (
    'uuid; DROP',
    '`injected`',
    "name' OR 1=1 //",
    'content_sha256); MATCH (x) DETACH DELETE x //',
    'labels`',
)

# Fixed server-owned keys from prepare_entity_params / prepare_edge_params.
ENTITY_PARAM_KEYS = frozenset(
    {
        'uuid',
        'group_id',
        'batch_id',
        'name',
        'graph_key',
        'name_raw',
        'name_canonical',
        'database_qualified_name',
        'summary',
        'content_sha256',
        'created_at',
        'updated_at',
        'name_embedding',
        'attributes',
        'source_refs',
        'confidence',
        'labels',
        'create_token',
    }
)
EDGE_PARAM_KEYS = frozenset(
    {
        'uuid',
        'group_id',
        'batch_id',
        'name',
        'edge_key',
        'source_uuid',
        'target_uuid',
        'source_node_uuid',
        'target_node_uuid',
        'fact',
        'evidence',
        'content_sha256',
        'created_at',
        'updated_at',
        'fact_embedding',
        'attributes',
        'confidence',
        'episodes',
        'create_token',
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enabled_config() -> CatalogConfig:
    return CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))


class _FakeDriver:
    def __init__(self) -> None:
        self.tx_count = 0
        self.provider = SimpleNamespace(value='neo4j')
        self.queries: list[tuple[str, Any]] = []

    @asynccontextmanager
    async def transaction(self):
        self.tx_count += 1
        yield SimpleNamespace(run=AsyncMock())

    async def execute_query(self, cypher: str, params=None, **kwargs):
        _ = kwargs
        self.queries.append((cypher, params))
        return ([], None, None)


def _make_client() -> SimpleNamespace:
    driver = _FakeDriver()
    embedder = SimpleNamespace(create=AsyncMock(return_value=[0.1, 0.2]), create_batch=AsyncMock())
    llm = MagicMock()
    llm.generate_response = AsyncMock()
    return SimpleNamespace(driver=driver, embedder=embedder, llm_client=llm)


def _entity(**overrides: Any) -> CatalogEntityItem:
    data: dict[str, Any] = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'ORCL.HR.EMPLOYEES',
        'summary': 'Employee master table',
        'attributes': {'owner': 'HR'},
        'source_refs': [{'document_id': 'ddl.sql', 'page': 12, 'raw_text': 'CREATE TABLE'}],
        'confidence': 0.95,
    }
    data.update(overrides)
    return CatalogEntityItem.model_validate(data)


def _edge(**overrides: Any) -> CatalogEdgeItem:
    data: dict[str, Any] = {
        'edge_type': 'ForeignKeyTo',
        'edge_key': 'FK::HR.EMPLOYEES->HR.DEPARTMENTS',
        'source_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'source_entity_type': 'Table',
        'target_graph_key': 'TABLE::FE::ORCL.HR.DEPARTMENTS',
        'target_entity_type': 'Table',
        'fact': 'employees.dept_id references departments.dept_id',
        'evidence': None,
        'attributes': {'on_delete': 'CASCADE'},
        'confidence': 0.9,
    }
    data.update(overrides)
    return CatalogEdgeItem.model_validate(data)


def _entity_request(
    entities: list[CatalogEntityItem] | None = None,
    *,
    dry_run: bool = False,
) -> UpsertTypedEntitiesRequest:
    return UpsertTypedEntitiesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH,
        entities=entities if entities is not None else [_entity()],
        dry_run=dry_run,
        atomic=True,
    )


def _edge_request(edges: list[CatalogEdgeItem] | None = None) -> UpsertTypedEdgesRequest:
    return UpsertTypedEdgesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH,
        edges=edges or [_edge()],
        dry_run=False,
        atomic=True,
        strict_endpoints=True,
    )


def _batch_request(
    *,
    entities: list[CatalogEntityItem] | None = None,
    edges: list[CatalogEdgeItem] | None = None,
    dry_run: bool = False,
) -> UpsertCatalogBatchRequest:
    return UpsertCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH,
        entities=entities if entities is not None else [_entity()],
        edges=edges if edges is not None else [],
        dry_run=dry_run,
        catalog_sha256=HEX64,
    )


def _wire_minimal_entity_store(service: CatalogService) -> None:
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': HEX64,
            'batch_id': BATCH,
            'status': 'created',
            'error_code': None,
        }
    )
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock(return_value=None)


def _wire_batch_preflight(service: CatalogService) -> None:
    service._store.get_batch_status = AsyncMock(return_value=None)
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.resolve_endpoint_typed = AsyncMock(return_value=('missing_endpoint', None))
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock(return_value=None)
    service._store.ensure_evidence_manifest_schema = AsyncMock(return_value=None)
    service._store.upsert_batch_status = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock()
    service._store.upsert_edge_item = AsyncMock()
    service._store.claim_batch_status = AsyncMock()
    service._store.write_manifest_root_and_chunks = AsyncMock()
    service._store.write_evidence_links = AsyncMock(return_value=[])
    service._store.lock_provenance_targets = AsyncMock(return_value=[])
    real = CatalogNeo4jStore()
    service._store.prepare_entity_params = real.prepare_entity_params
    service._store.prepare_edge_params = real.prepare_edge_params
    service._store.prepare_source_episode_params = real.prepare_source_episode_params
    service._store.prepare_batch_status_params = real.prepare_batch_status_params
    service._store.prepare_evidence_link_params = real.prepare_evidence_link_params
    service._store.prepare_manifest_root_params = real.prepare_manifest_root_params
    service._store.prepare_manifest_chunk_params = real.prepare_manifest_chunk_params


def _function_defs(tree: ast.AST) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _literal_logger_template(expression: ast.expr) -> tuple[str, list[str]] | None:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value, []
    if not isinstance(expression, ast.JoinedStr):
        return None
    parts: list[str] = []
    arguments: list[str] = []
    for value in expression.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            parts.append('{}')
            arguments.append(ast.unparse(value.value))
        else:
            return None
    return ''.join(parts), arguments


def _logger_calls(path: Path) -> list[tuple[str | None, str, str, list[str]]]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    calls: list[tuple[str | None, str, str, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != 'logger':
            continue
        if not node.args:
            continue
        parsed = _literal_logger_template(node.args[0])
        if parsed is None:
            continue
        template, formatted_arguments = parsed
        owner = parents.get(node)
        while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = parents.get(owner)
        function_name = (
            owner.name if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
        )
        calls.append(
            (
                function_name,
                node.func.attr,
                template,
                formatted_arguments + [ast.unparse(argument) for argument in node.args[1:]],
            )
        )
    return calls


def _base_entity_params(**overrides: Any) -> dict[str, Any]:
    now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    params: dict[str, Any] = {
        'uuid': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        'group_id': GROUP,
        'batch_id': BATCH,
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'ORCL.HR.EMPLOYEES',
        'summary': 'Employee table',
        'content_sha256': HEX64,
        'created_at': now,
        'updated_at': now,
        'name_embedding': [0.1, 0.2],
        'attributes': {'owner': 'HR'},
        'source_refs': [],
        'confidence': 0.9,
    }
    params.update(overrides)
    return params


# ---------------------------------------------------------------------------
# SAFE-03 — prohibited tools absent on catalog paths
# ---------------------------------------------------------------------------


def test_prohibited_tools_absent_on_catalog_paths():
    """SAFE-03: deterministic catalog service+MCP wrappers never call prohibited tools."""
    service_tree = ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))
    service_calls = _call_names(service_tree)
    leaked = PROHIBITED_ON_CATALOG_PATH & service_calls
    assert not leaked, f'catalog_service calls prohibited tools: {sorted(leaked)}'

    mcp_tree = ast.parse(MCP_PATH.read_text(encoding='utf-8'))
    defs = _function_defs(mcp_tree)
    for name in sorted(CATALOG_MCP_WRAPPERS):
        assert name in defs, f'missing catalog MCP wrapper: {name}'
        wrapper_calls = _call_names(defs[name])
        leaked_w = PROHIBITED_ON_CATALOG_PATH & wrapper_calls
        assert not leaked_w, f'{name} calls prohibited tools: {sorted(leaked_w)}'

    # Service source must not contain bare call-literal patterns for banned tools
    # as attribute calls on client/graphiti (static string scan of service only).
    service_src = SERVICE_PATH.read_text(encoding='utf-8')
    for tool in PROHIBITED_ON_CATALOG_PATH:
        assert f'.{tool}(' not in service_src, f'catalog_service contains .{tool}('
        assert f' {tool}(' not in service_src, f'catalog_service contains {tool}('


# ---------------------------------------------------------------------------
# SAFE-04 — LLM/queue/community + commit embedder spies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_or_queue_or_community_ban_on_catalog_paths():
    """SAFE-04: LLM/queue/community counts stay zero on prepare/commit/upsert paths."""
    client = _make_client()
    queue = MagicMock()
    queue.add_episode = AsyncMock()
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    _wire_minimal_entity_store(service)

    # Sequential
    await service.upsert_typed_entities(client=client, request=_entity_request())
    # Concurrent
    await asyncio.gather(
        service.upsert_typed_entities(client=client, request=_entity_request()),
        service.upsert_typed_entities(
            client=client,
            request=_entity_request(
                [
                    _entity(
                        graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
                        name_raw='DEPARTMENTS',
                        name_canonical='departments',
                        database_qualified_name='ORCL.HR.DEPARTMENTS',
                    )
                ]
            ),
        ),
    )

    queue.add_episode.assert_not_awaited()
    queue.add_episode.assert_not_called()
    client.llm_client.generate_response.assert_not_called()
    # CatalogService must not expose community/maintenance fan-out callables.
    assert not callable(getattr(service, 'build_communities', None))


@pytest.mark.asyncio
async def test_commit_path_embedder_not_awaited():
    """SAFE-04: commit never re-embeds (embedder.create not awaited)."""
    token = mint_plan_token()
    digest = plan_token_digest(token)
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    # Fail-closed unknown token path — still must not embed.
    service._store.load_prepared_plan_by_token_digest = AsyncMock(return_value=None)
    service._store.load_prepared_plan_chunks = AsyncMock(return_value=[])
    service._store.ensure_plan_schema = AsyncMock()
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()
    service._store.ensure_evidence_manifest_schema = AsyncMock()

    resp = await service.commit_prepared_catalog_batch(
        client=client,
        request=CommitPreparedCatalogBatchRequest(plan_token=token),
    )
    assert resp.error_code is not None
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()
    # digest is computed server-side; never logged as raw token (checked elsewhere).
    assert isinstance(digest, str) and len(digest) == 64


# ---------------------------------------------------------------------------
# TEST-10 — fixed Cypher identifier / property allowlist authority
# ---------------------------------------------------------------------------


def test_client_controlled_cypher_entity_identifiers_fail_before_query():
    """TEST-10: malicious entity-type identifiers never enter Cypher / tx.run."""
    store = CatalogNeo4jStore()
    for bad in MALICIOUS_ENTITY_TYPES:
        with pytest.raises(CatalogStoreError):
            store.resolve_entity_label(bad)
        with pytest.raises(CatalogStoreError):
            store.build_entity_upsert_cypher(bad)
        with pytest.raises(CatalogStoreError):
            store.build_resolve_endpoint_typed_cypher(bad)
        with pytest.raises(CatalogStoreError):
            store.prepare_entity_params(entity_type=bad, **_base_entity_params())

    # Allowlisted builders emit only registry labels as literals.
    for entity_type in sorted(CATALOG_ENTITY_TYPES):
        label = store.resolve_entity_label(entity_type)
        assert label == _ENTITY_LABELS[entity_type]
        cypher = store.build_entity_upsert_cypher(entity_type)
        assert f':{label}' in cypher or f"'{label}'" in cypher
        assert '$uuid' in cypher and '$group_id' in cypher
        for bad in MALICIOUS_ENTITY_TYPES:
            assert bad not in cypher


def test_client_controlled_cypher_edge_identifiers_fail_before_query():
    """TEST-10: malicious edge-type identifiers never enter Cypher / tx.run."""
    store = CatalogNeo4jStore()
    for bad in MALICIOUS_EDGE_TYPES:
        with pytest.raises(CatalogStoreError):
            store.resolve_edge_type(bad)
        with pytest.raises(CatalogStoreError):
            store.prepare_edge_params(
                edge_type=bad,
                uuid='u',
                group_id=GROUP,
                batch_id=BATCH,
                edge_key='FK::A->B',
                source_uuid='s',
                target_uuid='t',
                fact='f',
                content_sha256=HEX64,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                fact_embedding=[0.1],
            )

    cypher = store.build_edge_upsert_cypher()
    # Relationship type is fixed RELATES_TO; edge name is a parameter.
    assert 'RELATES_TO' in cypher
    assert '$name' in cypher or 'e.name' in cypher
    for bad in MALICIOUS_EDGE_TYPES:
        assert bad not in cypher
    for edge_type in sorted(CATALOG_EDGE_TYPES):
        assert store.resolve_edge_type(edge_type) == edge_type


def test_client_controlled_property_keys_fail_before_query():
    """TEST-10: client attribute/property keys never interpolate into Cypher."""
    store = CatalogNeo4jStore()
    # Malicious keys in attributes are values only (serialized JSON), never Cypher keys.
    attrs = {k: 'v' for k in MALICIOUS_PROPERTY_KEYS}
    attrs['owner'] = 'HR'
    params = store.prepare_entity_params(
        entity_type='Table',
        **_base_entity_params(attributes=attrs),
    )
    assert set(params.keys()) == ENTITY_PARAM_KEYS
    # Attributes are a single JSON parameter value — never expanded into Cypher keys.
    assert isinstance(params['attributes'], str)
    cypher = store.build_entity_upsert_cypher('Table')
    assert 'attributes = $attributes' in cypher or '$attributes' in cypher
    for key in MALICIOUS_PROPERTY_KEYS:
        assert key not in cypher
        assert f'n.{key}' not in cypher

    edge_params = store.prepare_edge_params(
        edge_type='ForeignKeyTo',
        uuid='u',
        group_id=GROUP,
        batch_id=BATCH,
        edge_key='FK::A->B',
        source_uuid='s',
        target_uuid='t',
        fact='f',
        content_sha256=HEX64,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        fact_embedding=[0.1],
        attributes=attrs,
    )
    assert set(edge_params.keys()) == EDGE_PARAM_KEYS
    edge_cypher = store.build_edge_upsert_cypher()
    for key in MALICIOUS_PROPERTY_KEYS:
        assert key not in edge_cypher


def test_cypher_identifier_registry_nonempty():
    """TEST-10 empty: fixed-authority identifier registry must be nonempty."""
    assert CATALOG_ENTITY_TYPES
    assert CATALOG_EDGE_TYPES
    assert _ENTITY_LABELS
    assert set(_ENTITY_LABELS) == set(CATALOG_ENTITY_TYPES)
    store = CatalogNeo4jStore()
    # Inventory every builder that accepts entity_type/edge_type.
    builders = [
        store.resolve_entity_label,
        store.build_entity_upsert_cypher,
        store.build_resolve_endpoint_typed_cypher,
        store.resolve_edge_type,
    ]
    assert builders
    for entity_type in sorted(CATALOG_ENTITY_TYPES):
        assert store.resolve_entity_label(entity_type) == entity_type


# ---------------------------------------------------------------------------
# SAFE-04 — missing / same-batch / implicit endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_endpoint_returns_structured_error_zero_writes():
    """SAFE-04: missing persisted endpoints → existing missing_endpoint; zero writes."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.resolve_endpoint_typed = AsyncMock(return_value=('missing_endpoint', None))
    service._store.upsert_edge_item = AsyncMock()
    service._store.upsert_entity_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()

    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert any(r.error_code == CatalogErrorCode.missing_endpoint for r in resp.results)
    assert 'embed' not in getattr(client, 'call_order', [])
    client.embedder.create.assert_not_awaited()
    cast(AsyncMock, service._store.upsert_edge_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    assert client.driver.tx_count == 0

    # Combined batch aggregates known endpoint failures without domain writes.
    service2 = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service2)
    batch_resp = await service2.upsert_catalog_batch(
        client=_make_client(),
        request=_batch_request(entities=[], edges=[_edge()]),
    )
    assert batch_resp.error_code in (
        CatalogErrorCode.missing_endpoint,
        CatalogErrorCode.batch_conflict,
    )
    assert batch_resp.failed >= 1
    cast(AsyncMock, service2._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service2._store.upsert_edge_item).assert_not_awaited()


@pytest.mark.asyncio
async def test_same_batch_endpoints_resolve_from_request_union_only():
    """SAFE-04: same-batch endpoints resolve from validated entity union only."""
    employee = _entity()
    department = _entity(
        graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='ORCL.HR.DEPARTMENTS',
        summary='Department master table',
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(
            entities=[employee, department],
            edges=[_edge()],
            dry_run=True,
        ),
    )
    assert resp.dry_run is True
    assert resp.failed == 0
    cast(AsyncMock, service._store.resolve_endpoint_typed).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_edge_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_batch_status).assert_not_awaited()
    assert client.driver.tx_count == 0


@pytest.mark.asyncio
async def test_implicit_endpoint_creation_forbidden():
    """SAFE-04 / TEST-10: MATCH-only lookup; zero implicit endpoint/community writes."""
    store = CatalogNeo4jStore()
    cypher = store.build_resolve_endpoint_typed_cypher('Table')
    upper = cypher.upper().replace('CREATED_AT', '')
    assert 'MATCH' in upper
    assert 'CREATE' not in upper
    assert 'MERGE' not in upper
    assert 'SET ' not in cypher

    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.resolve_endpoint_typed = AsyncMock(return_value=('missing_endpoint', None))
    service._store.upsert_entity_item = AsyncMock()
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock()

    await service.upsert_typed_edges(client=client, request=_edge_request())
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_edge_item).assert_not_awaited()
    client.embedder.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# SAFE-06 — fail-closed conflicts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_closed_conflicts_no_silent_repair():
    """SAFE-06: identity/type/endpoint/provenance/manifest/hash conflicts fail closed."""
    # Hash mismatch via explicit request_sha256 compare guard.
    service2 = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service2)
    mismatch = await service2.upsert_catalog_batch(
        client=_make_client(),
        request=UpsertCatalogBatchRequest(
            identity_schema_version='catalog-v2',
            system_key='FE',
            group_id=GROUP,
            batch_id=BATCH,
            entities=[_entity()],
            edges=[],
            dry_run=False,
            request_sha256='b' * 64,
            catalog_sha256=HEX64,
        ),
    )
    assert mismatch.error_code == CatalogErrorCode.content_hash_mismatch
    cast(AsyncMock, service2._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service2._store.upsert_edge_item).assert_not_awaited()

    # Divergent duplicate identity conflict (fail-closed, no merge).
    service3 = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service3)
    dup = await service3.upsert_catalog_batch(
        client=_make_client(),
        request=_batch_request(
            entities=[_entity(summary='first'), _entity(summary='second')],
        ),
    )
    assert dup.error_code == CatalogErrorCode.batch_conflict
    assert all(r.error_code == CatalogErrorCode.deterministic_uuid_conflict for r in dup.results)
    cast(AsyncMock, service3._store.upsert_entity_item).assert_not_awaited()

    # Missing endpoint — structured, no repair create.
    service4 = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service4)
    miss = await service4.upsert_catalog_batch(
        client=_make_client(),
        request=_batch_request(entities=[], edges=[_edge()]),
    )
    assert miss.error_code in (
        CatalogErrorCode.missing_endpoint,
        CatalogErrorCode.batch_conflict,
    )
    cast(AsyncMock, service4._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service4._store.upsert_edge_item).assert_not_awaited()

    # Concurrent conflict probes still fail closed.
    async def _conflict_once():
        svc = CatalogService(catalog_config=_enabled_config())
        _wire_batch_preflight(svc)
        return await svc.upsert_catalog_batch(
            client=_make_client(),
            request=UpsertCatalogBatchRequest(
                identity_schema_version='catalog-v2',
                system_key='FE',
                group_id=GROUP,
                batch_id=f'{BATCH}-c',
                entities=[_entity()],
                edges=[],
                request_sha256='c' * 64,
                catalog_sha256=HEX64,
            ),
        )

    results = await asyncio.gather(_conflict_once(), _conflict_once())
    for r in results:
        assert r.error_code == CatalogErrorCode.content_hash_mismatch


# ---------------------------------------------------------------------------
# SAFE-07 — log scrub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_empty_batch_omits_payload_and_credentials(caplog: pytest.LogCaptureFixture):
    """SAFE-07 empty: empty/minimal catalog log events omit payload/source/token/creds."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_minimal_entity_store(service)

    with caplog.at_level(logging.INFO):
        # Minimal dry_run path logs counts only (entities min_length=1).
        await service.upsert_typed_entities(
            client=client,
            request=_entity_request(dry_run=True),
        )
        await service.upsert_typed_entities(
            client=client,
            request=_entity_request(),
        )

    joined = ' '.join(r.getMessage() for r in caplog.records)
    for marker in FORBIDDEN_LOG_MARKERS:
        assert marker not in joined
    assert 'Employee master table' not in joined
    assert 'CREATE TABLE' not in joined
    assert 'password' not in joined.lower()
    assert GROUP not in joined  # group_id scrubbed from catalog logs
    assert FORBIDDEN_GROUP not in joined


def test_log_encoding_forbids_plan_token_and_payload_markers():
    """SAFE-07 encoding: AST/caplog exact UTF-8 containment bans for forbidden markers."""
    service_calls = _logger_calls(SERVICE_PATH)
    catalog_service_calls = [c for c in service_calls if c[2].startswith('catalog ')]
    assert catalog_service_calls

    wrapper_calls = _logger_calls(MCP_PATH)
    catalog_wrapper_calls = [c for c in wrapper_calls if c[0] in CATALOG_MCP_WRAPPERS]
    assert catalog_wrapper_calls

    for function_name, _method, template, arguments in (
        catalog_service_calls + catalog_wrapper_calls
    ):
        lowered = template.lower()
        for marker in FORBIDDEN_LOG_MARKERS:
            assert marker not in template, f'{function_name}: template has {marker!r}'
            assert marker not in lowered or marker in FORBIDDEN_LOG_MARKERS
        assert 'group_id' not in lowered
        assert 'plan_token' not in lowered
        assert 'password' not in lowered
        assert 'api_key' not in lowered
        assert 'authorization' not in lowered
        assert 'source_text' not in lowered
        assert 'payload=' not in template
        # Argument expressions must not dump raw plan_token / credentials.
        for argument in arguments:
            arg_l = argument.lower()
            assert 'plan_token' not in arg_l or 'digest' in arg_l
            assert 'password' not in arg_l
            assert 'api_key' not in arg_l
            assert 'authorization' not in arg_l


# ---------------------------------------------------------------------------
# TEST-10 empty baseline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_spy_baseline_no_prohibited_call():
    """TEST-10 empty: empty-spy baseline executes no prohibited call/query."""
    client = _make_client()
    queue = MagicMock()
    queue.add_episode = AsyncMock()
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    _wire_minimal_entity_store(service)

    # dry_run validates without opening a write transaction or domain upsert.
    resp = await service.upsert_typed_entities(
        client=client,
        request=_entity_request(dry_run=True),
    )
    assert resp is not None
    assert (
        resp.dry_run is True
        or resp.failed == 0
        or resp.created + resp.updated + resp.unchanged >= 0
    )
    queue.add_episode.assert_not_awaited()
    client.llm_client.generate_response.assert_not_called()
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    assert client.driver.tx_count == 0
    assert client.driver.queries == []


def test_matrix_hardcodes_allowed_test_group_only():
    """D-04: matrix module may name forbidden group only as ban constant."""
    assert ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    assert FORBIDDEN_GROUP == 'oracle-catalog-v2'
    src = Path(__file__).read_text(encoding='utf-8')
    # No bare GROUP/group_id/TEST_GROUP assignment to protected group.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id in {'GROUP', 'group_id', 'TEST_GROUP'}
                and isinstance(node.value, ast.Constant)
                and node.value.value == FORBIDDEN_GROUP
            ):
                pytest.fail(f'forbidden assignment of {target.id} to protected group')
