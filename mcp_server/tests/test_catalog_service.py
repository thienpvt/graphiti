"""Unit tests for CatalogService.upsert_typed_entities (entity path)."""

from __future__ import annotations

import ast
import asyncio
import importlib
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_batch import (  # noqa: E402
    GetCatalogIngestStatusRequest,
    NestedProvenancePayload,
    UpsertCatalogBatchRequest,
)
from models.catalog_common import CatalogErrorCode  # noqa: E402
from models.catalog_edges import CatalogEdgeItem, UpsertTypedEdgesRequest  # noqa: E402
from models.catalog_entities import (  # noqa: E402
    CatalogEntityItem,
    ResolveEntityRef,
    ResolveTypedEntitiesRequest,
    UpsertTypedEntitiesRequest,
    VerifyCatalogBatchRequest,
    VerifyEdgeRef,
    VerifyEntityRef,
)
from services.catalog_identity import (  # noqa: E402
    canonical_sha256,
    catalog_batch_uuid,
    catalog_edge_uuid,
    catalog_entity_uuid,
)
from services.catalog_service import CatalogService  # noqa: E402

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'
BATCH = 'batch-entity-001'
CATALOG_TOOL_NAMES = {
    'upsert_typed_entities',
    'upsert_typed_edges',
    'resolve_typed_entities',
    'verify_catalog_batch',
    'upsert_provenance',
    'get_catalog_ingest_status',
    'upsert_catalog_batch',
}
LEGACY_TOOL_NAMES = {
    'add_memory',
    'search_nodes',
    'search_memory_facts',
    'add_triplet',
    'get_entity_edge',
    'get_episodes',
    'get_episode_entities',
    'update_entity',
    'build_communities',
    'summarize_saga',
    'delete_episode',
    'delete_entity_edge',
    'clear_graph',
    'get_status',
}


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
    """Return function, logger method, literal template, and argument expressions."""
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


def test_catalog_logger_templates_omit_group_id():
    src = Path(__file__).parent.parent / 'src'
    wrapper_calls = _logger_calls(src / 'graphiti_mcp_server.py')
    service_calls = _logger_calls(src / 'services' / 'catalog_service.py')

    catalog_wrapper_calls = [call for call in wrapper_calls if call[0] in CATALOG_TOOL_NAMES]
    catalog_service_calls = [call for call in service_calls if call[2].startswith('catalog ')]
    catalog_calls = catalog_wrapper_calls + catalog_service_calls

    assert catalog_wrapper_calls
    assert catalog_service_calls
    assert any('Using group_id' in call[2] for call in wrapper_calls)
    assert any('Group ID' in call[2] for call in wrapper_calls)
    assert all('group_id' not in template.lower() for _, _, template, _ in catalog_calls)
    assert all(
        all('group_id' not in argument for argument in arguments)
        for _, _, _, arguments in catalog_calls
    )


def _catalog_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage().startswith('catalog ')]


def _assert_group_id_absent(records: list[logging.LogRecord], group_id: str = GROUP) -> None:
    assert records
    assert all(group_id not in record.getMessage() for record in records)
    assert all(group_id not in record.msg for record in records)
    assert all(
        group_id not in argument
        for record in records
        for argument in (record.args if isinstance(record.args, tuple) else ())
        if isinstance(argument, str)
    )


def _mcp_server():
    """Lazy import MCP server module (avoids static missing-import diagnostics)."""
    return importlib.import_module('graphiti_mcp_server')


def _entity(**overrides) -> CatalogEntityItem:
    data = {
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


def _request(
    entities: list[CatalogEntityItem] | None = None,
    *,
    dry_run: bool = False,
    atomic: Literal[True] = True,
    batch_id: str = BATCH,
) -> UpsertTypedEntitiesRequest:
    return UpsertTypedEntitiesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=batch_id,
        entities=entities or [_entity()],
        dry_run=dry_run,
        atomic=atomic,
    )


def _enabled_config() -> CatalogConfig:
    return CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))


def _disabled_config() -> CatalogConfig:
    return CatalogConfig(enabled=False, uuid_namespace=None)


def _schema_execute_query(cypher: str, params=None, **kwargs):
    """Async-compatible schema DDL double: SHOW reports constraints present."""
    _ = params, kwargs
    text = (cypher or '').strip().upper()
    if 'SHOW CONSTRAINTS' in text:
        return (
            [
                {
                    'name': 'catalog_entity_identity_unique',
                    'type': 'NODE_PROPERTY_UNIQUENESS',
                    'entityType': 'NODE',
                    'labelsOrTypes': ['Entity'],
                    'properties': ['uuid', 'group_id'],
                },
                {
                    'name': 'catalog_relates_to_identity_unique',
                    'type': 'RELATIONSHIP_PROPERTY_UNIQUENESS',
                    'entityType': 'RELATIONSHIP',
                    'labelsOrTypes': ['RELATES_TO'],
                    'properties': ['uuid', 'group_id'],
                },
                {
                    'name': 'catalog_episodic_identity_unique',
                    'type': 'NODE_PROPERTY_UNIQUENESS',
                    'entityType': 'NODE',
                    'labelsOrTypes': ['Episodic'],
                    'properties': ['uuid', 'group_id'],
                },
                {
                    'name': 'catalog_mentions_identity_unique',
                    'type': 'RELATIONSHIP_PROPERTY_UNIQUENESS',
                    'entityType': 'RELATIONSHIP',
                    'labelsOrTypes': ['MENTIONS'],
                    'properties': ['uuid', 'group_id'],
                },
                {
                    'name': 'catalog_batch_identity_unique',
                    'type': 'NODE_PROPERTY_UNIQUENESS',
                    'entityType': 'NODE',
                    'labelsOrTypes': ['CatalogIngestBatch'],
                    'properties': ['uuid', 'group_id'],
                },
            ],
            None,
            None,
        )
    return ([], None, None)


def _make_client(
    *,
    provider: str = 'neo4j',
    embedder: AsyncMock | None = None,
    tx_side_effect=None,
):
    # Mirror GraphProvider.value without importing graphiti_core (editor pyright path).
    provider_enum = SimpleNamespace(value=provider)

    embedder = embedder or AsyncMock(return_value=[0.1, 0.2, 0.3])
    call_order: list[str] = []

    async def _embed(*args, **kwargs):
        _ = args, kwargs
        call_order.append('embed')
        return [0.1, 0.2, 0.3]

    embedder.create = AsyncMock(side_effect=_embed)
    embedder.create_batch = AsyncMock(side_effect=lambda inputs: [[0.1, 0.2]] * len(inputs))

    tx = MagicMock()
    tx.run = AsyncMock(
        return_value=SimpleNamespace(
            data=AsyncMock(
                return_value=[
                    {
                        'uuid': 'u1',
                        'content_sha256': 'h1',
                        'batch_id': BATCH,
                        'status': 'created',
                    }
                ]
            )
        )
    )

    @asynccontextmanager
    async def _transaction():
        call_order.append('transaction')
        if tx_side_effect is not None:
            raise tx_side_effect
        yield tx

    async def _execute_query(cypher: str, params=None, **kwargs):
        return _schema_execute_query(cypher, params=params, **kwargs)

    driver = SimpleNamespace(
        provider=provider_enum,
        transaction=_transaction,
        # Real async callable — product path never special-cases unittest.mock.
        execute_query=_execute_query,
    )

    client = SimpleNamespace(
        driver=driver,
        embedder=embedder,
        llm_client=MagicMock(),
        call_order=call_order,
        tx=tx,
    )
    return client


@pytest.mark.asyncio
async def test_entity_feature_disabled_returns_structured_error_without_write():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert resp.failed >= 1 or any(
        r.error_code == CatalogErrorCode.feature_disabled for r in resp.results
    )
    assert all(r.status in ('error', 'rolled_back') for r in resp.results)
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_entity_invalid_uuid_namespace_when_enabled_without_valid_ns():
    # Construct config that claims enabled but namespace invalid via object mutation
    cfg = CatalogConfig(enabled=False, uuid_namespace=None)
    # Bypass pydantic after construction for gate testing
    object.__setattr__(cfg, 'enabled', True)
    object.__setattr__(cfg, 'uuid_namespace', 'not-a-uuid')
    client = _make_client()
    service = CatalogService(catalog_config=cfg)
    resp = await service.upsert_typed_entities(client=client, request=_request())
    codes = {r.error_code for r in resp.results}
    assert CatalogErrorCode.invalid_uuid_namespace in codes or (
        resp.failed >= 1
        and any(
            r.error_code
            in (CatalogErrorCode.invalid_uuid_namespace, CatalogErrorCode.feature_disabled)
            for r in resp.results
        )
    )
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_entity_non_neo4j_backend_unavailable():
    client = _make_client(provider='falkordb')
    service = CatalogService(catalog_config=_enabled_config())
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert any(r.error_code == CatalogErrorCode.backend_unavailable for r in resp.results)
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_entity_service_enforces_configured_limit_below_hard_max():
    client = _make_client()
    cfg = CatalogConfig(
        enabled=True,
        uuid_namespace=str(FIXED_NS),
        max_entities_per_batch=1,
    )
    service = CatalogService(catalog_config=cfg)
    request = _request([_entity(), _entity(graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS')])
    resp = await service.upsert_typed_entities(client=client, request=request)
    assert all(r.error_code == CatalogErrorCode.batch_limit_exceeded for r in resp.results)
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_entity_embed_before_transaction_order():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    # No existing node -> create path
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert client.call_order.index('embed') < client.call_order.index('transaction')
    assert resp.created >= 1 or resp.results[0].status in ('created', 'updated', 'unchanged')


@pytest.mark.asyncio
async def test_entity_dry_run_embeds_but_never_writes_or_persists_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock()
    service._ensure_schema = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request(dry_run=True))
    assert 'embed' in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_entity_item.assert_not_awaited()
    service._ensure_schema.assert_not_awaited()
    assert resp.dry_run is True
    # dry-run success states still report projected status
    assert resp.results[0].status in ('created', 'updated', 'unchanged')
    assert resp.results[0].uuid is not None


@pytest.mark.asyncio
async def test_entity_create_persists_request_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._ensure_schema = AsyncMock()
    captured: dict = {}

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        captured.update(params)
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert captured.get('batch_id') == BATCH
    assert resp.results[0].status == 'created'
    assert resp.created == 1
    service._ensure_schema.assert_awaited()


@pytest.mark.asyncio
async def test_entity_identity_name_raw_conflict_no_write():
    entity = _entity(name_raw='CHANGED')
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-batch',
        'labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'graph_key': entity.graph_key,
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_entity_item = AsyncMock()
    service._ensure_schema = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert any(r.error_code == CatalogErrorCode.deterministic_uuid_conflict for r in resp.results)
    service._store.upsert_entity_item.assert_not_awaited()
    service._ensure_schema.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_identical_hash_unchanged_leaves_batch_id():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    payload = CatalogService.entity_canonical_payload(entity)
    digest = canonical_sha256(payload)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': digest,
        'batch_id': 'prior-batch',
        'labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'unchanged'
    assert resp.unchanged == 1
    # identical: no write of new batch_id
    service._store.upsert_entity_item.assert_not_awaited()
    assert resp.results[0].uuid == ent_uuid
    assert resp.results[0].content_sha256 == digest


@pytest.mark.asyncio
async def test_entity_changed_update_passes_request_batch_id():
    entity = _entity(summary='Changed summary')
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-batch',
        'labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    captured: dict = {}

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        captured.update(params)
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'updated',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'updated'
    assert captured.get('batch_id') == BATCH


@pytest.mark.asyncio
async def test_entity_atomic_rollback_on_store_failure():
    e1 = _entity(
        graph_key='TABLE::FE::ORCL.A.T1', database_qualified_name='ORCL.A.T1', name_raw='T1'
    )
    e2 = _entity(
        graph_key='TABLE::FE::ORCL.A.T2', database_qualified_name='ORCL.A.T2', name_raw='T2'
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        if params['graph_key'] == 'TABLE::FE::ORCL.A.T2':
            raise RuntimeError('neo4j boom')
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(
        client=client, request=_request([e1, e2], atomic=True)
    )
    statuses = [r.status for r in resp.results]
    assert 'error' in statuses
    assert 'rolled_back' in statuses
    assert resp.rolled_back >= 1
    assert resp.failed >= 1
    # trigger error is structured, not raw exception dump as sole message ideally
    err = next(r for r in resp.results if r.status == 'error')
    assert err.error_code in (
        CatalogErrorCode.neo4j_transaction_failed,
        CatalogErrorCode.internal_error,
    )


@pytest.mark.asyncio
async def test_entity_content_hash_mismatch():
    entity = _entity(content_sha256='c' * 64)
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert any(r.error_code == CatalogErrorCode.content_hash_mismatch for r in resp.results)
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_entity_entity_type_conflict_no_mutation():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'd' * 64,
        'batch_id': 'old',
        'labels': ['Entity', 'View'],  # wrong custom type
        'neo4j_labels': ['Entity', 'View'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert any(r.error_code == CatalogErrorCode.entity_type_conflict for r in resp.results)
    service._store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_no_queue_or_llm_calls():
    client = _make_client()
    queue = MagicMock()
    queue.add_episode = AsyncMock()
    llm = MagicMock()
    llm.generate_response = AsyncMock()
    client.llm_client = llm
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': BATCH,
            'status': 'created',
        }
    )
    await service.upsert_typed_entities(client=client, request=_request())
    queue.add_episode.assert_not_awaited()
    llm.generate_response.assert_not_called()


@pytest.mark.asyncio
async def test_entity_logs_batch_id_and_counts_only(caplog):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': BATCH,
            'status': 'created',
        }
    )
    with caplog.at_level(logging.INFO):
        await service.upsert_typed_entities(client=client, request=_request())
    joined = ' '.join(r.message for r in caplog.records)
    assert BATCH in joined
    # Must not log full summary/payload
    assert 'Employee master table' not in joined
    assert 'ddl.sql' not in joined


@pytest.mark.asyncio
async def test_entity_preserves_input_order_and_deterministic_uuid():
    e1 = _entity(
        graph_key='TABLE::FE::ORCL.A.T1', database_qualified_name='ORCL.A.T1', name_raw='T1'
    )
    e2 = _entity(
        graph_key='TABLE::FE::ORCL.A.T2', database_qualified_name='ORCL.A.T2', name_raw='T2'
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([e1, e2]))
    assert [r.index for r in resp.results] == [0, 1]
    assert resp.results[0].graph_key == 'TABLE::FE::ORCL.A.T1'
    assert resp.results[1].graph_key == 'TABLE::FE::ORCL.A.T2'
    # IDEN-08: write result echoes complete system-scoped keys (exact equality)
    assert resp.results[0].graph_key == e1.graph_key
    assert resp.results[1].graph_key == e2.graph_key
    assert resp.results[0].uuid == catalog_entity_uuid(
        FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.A.T1'
    )
    assert resp.results[0].content_sha256 is not None
    assert len(resp.results[0].content_sha256) == 64


@pytest.mark.asyncio
async def test_entity_result_graph_key_echo_exact_full_system_scoped_key_iden08():
    """IDEN-08: upsert result graph_key equals full submitted system-scoped key (exact ==)."""
    full_key = 'TABLE::FE::ORCL.HR.EMPLOYEES_LONG_NAME'
    entity = _entity(
        graph_key=full_key,
        database_qualified_name='ORCL.HR.EMPLOYEES_LONG_NAME',
        name_raw='EMPLOYEES_LONG_NAME',
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].graph_key == full_key
    assert resp.results[0].graph_key == entity.graph_key
    assert resp.results[0].uuid == catalog_entity_uuid(FIXED_NS, GROUP, 'Table', full_key)


@pytest.mark.asyncio
async def test_entity_coalesce_same_identity_same_hash():
    e1 = _entity()
    e2 = _entity()  # identical
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    upsert = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': BATCH,
            'status': 'created',
        }
    )
    service._store.upsert_entity_item = upsert
    resp = await service.upsert_typed_entities(client=client, request=_request([e1, e2]))
    # One physical write, two results
    assert upsert.await_count == 1
    assert len(resp.results) == 2
    assert resp.results[0].uuid == resp.results[1].uuid


@pytest.mark.asyncio
async def test_entity_same_identity_different_hash_is_conflict():
    e1 = _entity(summary='A')
    e2 = _entity(summary='B')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([e1, e2]))
    assert any(
        r.error_code
        in (
            CatalogErrorCode.deterministic_uuid_conflict,
            CatalogErrorCode.batch_conflict,
        )
        for r in resp.results
    )
    service._store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_divergent_duplicate_marks_later_repeat_conflicted():
    first = _entity(summary='A')
    divergent = _entity(summary='B')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock()

    resp = await service.upsert_typed_entities(
        client=client,
        request=_request([first, divergent, first.model_copy(deep=True)]),
    )

    assert [result.index for result in resp.results] == [0, 1, 2]
    assert all(
        result.error_code == CatalogErrorCode.deterministic_uuid_conflict for result in resp.results
    )
    service._store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_tool_upsert_typed_entities_registered():
    server = _mcp_server()
    assert hasattr(server, 'upsert_typed_entities')
    assert callable(server.upsert_typed_entities)


# ---------------------------------------------------------------------------
# resolve_typed_entities (read-only)
# ---------------------------------------------------------------------------


def _resolve_request(entities=None, **kwargs):
    if entities is None:
        entities = [
            ResolveEntityRef(entity_type='Table', graph_key='TABLE::FE::ORCL.HR.EMPLOYEES'),
        ]
    return ResolveTypedEntitiesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        entities=entities,
        **kwargs,
    )


def test_empty_resolve_rejected_before_service_no_side_effects():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service.resolve_typed_entities = AsyncMock()  # type: ignore[method-assign]

    for entities in ([], None):
        payload: dict[str, Any] = {
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
            'group_id': GROUP,
        }
        if entities is not None:
            payload['entities'] = entities
        with pytest.raises(ValidationError):
            ResolveTypedEntitiesRequest.model_validate(payload)

    service.resolve_typed_entities.assert_not_called()
    client.embedder.create.assert_not_called()
    client.embedder.create_batch.assert_not_called()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_feature_disabled_no_write_no_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    service._store.match_entities_for_resolve = AsyncMock()
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    assert any(
        getattr(r, 'error_code', None) == CatalogErrorCode.feature_disabled for r in resp.results
    )
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()
    service._store.match_entities_for_resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_non_neo4j_backend_unavailable():
    client = _make_client(provider='falkordb')
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock()
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    assert any(
        getattr(r, 'error_code', None) == CatalogErrorCode.backend_unavailable for r in resp.results
    )
    service._store.match_entities_for_resolve.assert_not_awaited()
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_catalog_resolve_logs_omit_group_id_runtime(caplog: pytest.LogCaptureFixture):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(return_value=[])

    with caplog.at_level(logging.INFO):
        await service.resolve_typed_entities(client=client, request=_resolve_request())

    _assert_group_id_absent(_catalog_records(caplog))


@pytest.mark.asyncio
async def test_resolve_missing_entity_reports_not_found():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(return_value=[])
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is False
    assert 'missing' in r0.anomalies or r0.status == 'missing'
    assert r0.uuid is None or r0.uuid == catalog_entity_uuid(
        FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES'
    )
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_found_entity_reports_fields_and_no_side_effects():
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    resolve_call: dict = {}

    async def _match_resolve(executor=None, **kwargs):
        _ = executor
        resolve_call.clear()
        resolve_call.update(kwargs)
        return [
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]

    service._store.match_entities_for_resolve = AsyncMock(side_effect=_match_resolve)
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert r0.uuid == ent_uuid
    assert r0.labels is not None and 'Table' in (r0.labels or [])
    assert r0.verified_type == 'Table'
    assert r0.content_sha256 == 'a' * 64
    assert r0.has_name_embedding is True
    assert r0.generic_duplicates == []
    assert r0.typed_duplicates == []
    # IDEN-08: exact complete system-scoped graph_key echo (no truncation/reformat)
    assert r0.graph_key == 'TABLE::FE::ORCL.HR.EMPLOYEES'
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()
    assert 'transaction' not in client.call_order
    # MATCH scoped to group_id + requested keys only (captured via side_effect, not optional mock)
    service._store.match_entities_for_resolve.assert_awaited()
    assert resolve_call.get('group_id') == GROUP
    assert 'TABLE::FE::ORCL.HR.EMPLOYEES' in (resolve_call.get('graph_keys') or [])


@pytest.mark.asyncio
async def test_resolve_graph_key_echo_exact_full_system_scoped_key_iden08():
    """IDEN-08: resolve result graph_key equals full submitted system-scoped key (exact ==)."""
    full_key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', full_key)
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': full_key,
                'name': full_key,
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]
    )
    req = _resolve_request(entities=[ResolveEntityRef(entity_type='Table', graph_key=full_key)])
    resp = await service.resolve_typed_entities(client=client, request=req)
    assert len(resp.results) == 1
    assert resp.results[0].graph_key == full_key
    assert resp.results[0].graph_key is full_key or resp.results[0].graph_key == str(full_key)
    # not truncated to body-only or FE-less form
    assert resp.results[0].graph_key != 'TABLE::ORCL.HR.EMPLOYEES'
    assert resp.results[0].graph_key != 'HR.EMPLOYEES'
    assert resp.results[0].uuid == ent_uuid


@pytest.mark.asyncio
async def test_resolve_generic_duplicate_and_typed_duplicate_and_uuid_mismatch():
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            # bare generic Entity with name=graph_key, no Table label
            {
                'uuid': 'generic-uuid-1',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity'],
                'neo4j_labels': ['Entity'],
                'content_sha256': 'b' * 64,
                'has_name_embedding': False,
                'batch_id': None,
            },
            # typed node with wrong uuid
            {
                'uuid': 'wrong-uuid',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'c' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            },
            # second typed duplicate
            {
                'uuid': expected_uuid,
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'd' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            },
        ]
    )
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert 'generic-uuid-1' in r0.generic_duplicates
    assert len(r0.typed_duplicates) >= 1
    assert any(
        a in r0.anomalies
        for a in (
            'generic_duplicate',
            'typed_duplicate',
            'uuid_mismatch',
            'missing_embedding',
            'wrong_type',
        )
    )
    assert 'uuid_mismatch' in r0.anomalies or any(
        u != expected_uuid for u in ([r0.uuid] if r0.uuid else []) + list(r0.typed_duplicates)
    )
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_wrong_custom_label_and_absent_embedding():
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'View'],
                'neo4j_labels': ['Entity', 'View'],
                'content_sha256': 'e' * 64,
                'has_name_embedding': False,
                'batch_id': BATCH,
            }
        ]
    )
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert 'wrong_type' in r0.anomalies or r0.verified_type != 'Table'
    assert 'missing_embedding' in r0.anomalies or r0.has_name_embedding is False
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_expected_plus_extra_label_is_wrong_type():
    """Entity+Table+View is not typed Table — exact custom label contract."""
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'Table', 'View'],
                'neo4j_labels': ['Entity', 'Table', 'View'],
                'content_sha256': 'f' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]
    )
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert r0.status == 'wrong_type'
    assert 'wrong_type' in r0.anomalies
    assert r0.verified_type == 'View'
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_expected_plus_extra_label_is_wrong_type():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key),
                'graph_key': key,
                'name': key,
                'labels': ['Entity', 'Table', 'View'],
                'neo4j_labels': ['Entity', 'Table', 'View'],
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    req = _verify_request(
        entities=[VerifyEntityRef(entity_type='Table', graph_key=key)],
        edges=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert key in resp.entities.wrong_type
    assert key not in (resp.entities.typed_duplicate or [])


@pytest.mark.asyncio
async def test_resolve_mixed_twin_aggregates_all_row_anomalies():
    """Typed expected + rogue typed + wrong-type sibling: report every anomaly."""
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(
        return_value=[
            {
                'uuid': expected_uuid,
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            },
            {
                'uuid': 'rogue-typed-uuid',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'b' * 64,
                'has_name_embedding': False,
                'batch_id': BATCH,
            },
            {
                'uuid': 'wrong-type-uuid',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'View'],
                'neo4j_labels': ['Entity', 'View'],
                'content_sha256': 'c' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            },
        ]
    )
    resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    r0 = resp.results[0]
    assert r0.found is True
    assert r0.status == 'found'
    assert r0.uuid == expected_uuid
    assert 'typed_duplicate' in r0.anomalies
    assert 'uuid_mismatch' in r0.anomalies
    assert 'missing_embedding' in r0.anomalies
    assert 'wrong_type' in r0.anomalies
    assert 'rogue-typed-uuid' in r0.typed_duplicates
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_resolve_never_opens_write_transaction():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_resolve = AsyncMock(return_value=[])
    service._store.upsert_entity_item = AsyncMock()
    service._ensure_schema = AsyncMock()
    await service.resolve_typed_entities(client=client, request=_resolve_request())
    service._store.upsert_entity_item.assert_not_awaited()
    service._ensure_schema.assert_not_awaited()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_mcp_tool_resolve_typed_entities_registered():
    server = _mcp_server()
    assert hasattr(server, 'resolve_typed_entities')
    assert callable(server.resolve_typed_entities)


# ---------------------------------------------------------------------------
# verify_catalog_batch (read-only)
# ---------------------------------------------------------------------------


def _verify_request(**kwargs):
    data = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': GROUP,
        'batch_id': BATCH,
        'entities': [
            VerifyEntityRef(entity_type='Table', graph_key='TABLE::FE::ORCL.HR.EMPLOYEES'),
        ],
        'edges': [
            VerifyEdgeRef(edge_type='Contains', edge_key='CONTAINS::HR.SCHEMA->HR.EMPLOYEES'),
        ],
        'require_provenance': False,
    }
    data.update(kwargs)
    return VerifyCatalogBatchRequest.model_validate(data)


@pytest.mark.asyncio
async def test_verify_feature_disabled_no_write_no_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    service._store.match_entities_for_verify = AsyncMock()
    service._store.match_edges_for_verify = AsyncMock()
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.feature_disabled
    service._store.match_entities_for_verify.assert_not_awaited()
    service._store.match_edges_for_verify.assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_non_neo4j_backend_unavailable():
    client = _make_client(provider='falkordb')
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock()
    resp = await service.verify_catalog_batch(client=client, request=_verify_request())
    assert resp.error_code == CatalogErrorCode.backend_unavailable
    service._store.match_entities_for_verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_batch_scoped_match_uses_group_and_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    ent_call: dict = {}
    edge_call: dict = {}

    async def _match_entities(executor=None, **kwargs):
        _ = executor
        ent_call.clear()
        ent_call.update(kwargs)
        return []

    async def _match_edges(executor=None, **kwargs):
        _ = executor
        edge_call.clear()
        edge_call.update(kwargs)
        return []

    service._store.match_entities_for_verify = AsyncMock(side_effect=_match_entities)
    service._store.match_edges_for_verify = AsyncMock(side_effect=_match_edges)
    await service.verify_catalog_batch(client=client, request=_verify_request())
    service._store.match_entities_for_verify.assert_awaited()
    service._store.match_edges_for_verify.assert_awaited()
    assert ent_call.get('group_id') == GROUP
    assert ent_call.get('batch_id') == BATCH
    assert edge_call.get('group_id') == GROUP
    assert edge_call.get('batch_id') == BATCH
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_entity_counts_and_anomaly_lists():
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': False,
                'batch_id': BATCH,
            },
            {
                'uuid': 'generic-1',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity'],
                'neo4j_labels': ['Entity'],
                'content_sha256': 'b' * 64,
                'has_name_embedding': False,
                'batch_id': BATCH,
            },
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    req = _verify_request(
        entities=[
            VerifyEntityRef(entity_type='Table', graph_key='TABLE::FE::ORCL.HR.EMPLOYEES'),
            VerifyEntityRef(entity_type='View', graph_key='VIEW::FE::ORCL.HR.V1'),
        ],
        edges=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.entities.expected == 2
    assert resp.entities.found == 1
    assert 'VIEW::FE::ORCL.HR.V1' in resp.entities.missing
    assert 'TABLE::FE::ORCL.HR.EMPLOYEES' in resp.entities.generic_duplicate
    assert 'TABLE::FE::ORCL.HR.EMPLOYEES' in resp.entities.missing_embedding
    # IDEN-08: verify anomaly lists carry complete system-scoped keys (exact membership)
    assert any(k == 'TABLE::FE::ORCL.HR.EMPLOYEES' for k in resp.entities.generic_duplicate)
    assert any(k == 'VIEW::FE::ORCL.HR.V1' for k in resp.entities.missing)
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_graph_key_echo_exact_full_system_scoped_key_iden08():
    """IDEN-08: verify missing/anomaly lists echo full submitted system-scoped keys (exact ==)."""
    full_key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    missing_key = 'VIEW::FE::ORCL.HR.V_LONG_NAME'
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    req = _verify_request(
        entities=[
            VerifyEntityRef(entity_type='Table', graph_key=full_key),
            VerifyEntityRef(entity_type='View', graph_key=missing_key),
        ],
        edges=[],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert full_key in resp.entities.missing
    assert missing_key in resp.entities.missing
    # not truncated / reformatted
    assert 'TABLE::ORCL.HR.EMPLOYEES' not in resp.entities.missing
    assert 'HR.EMPLOYEES' not in resp.entities.missing
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_entity_aggregates_anomalies_across_typed_twins():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key)
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': expected_uuid,
                'graph_key': key,
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'has_name_embedding': True,
            },
            {
                'uuid': str(uuid.uuid4()),
                'graph_key': key,
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'has_name_embedding': False,
            },
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(
            batch_id=None,
            entities=[VerifyEntityRef(entity_type='Table', graph_key=key)],
            edges=[],
        ),
    )
    assert resp.entities.found == 1
    assert resp.entities.typed_duplicate == [key]
    assert resp.entities.uuid_mismatch == [key]
    assert resp.entities.missing_embedding == [key]


@pytest.mark.asyncio
async def test_verify_entity_wrong_type_with_typed_present_is_reported():
    """Wrong-type sibling must surface even when exact typed rows exist."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key)
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': expected_uuid,
                'graph_key': key,
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'has_name_embedding': True,
            },
            {
                'uuid': str(uuid.uuid4()),
                'graph_key': key,
                'labels': ['Entity', 'View'],
                'neo4j_labels': ['Entity', 'View'],
                'has_name_embedding': True,
            },
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(
            batch_id=None,
            entities=[VerifyEntityRef(entity_type='Table', graph_key=key)],
            edges=[],
        ),
    )
    assert resp.entities.found == 1
    assert key in resp.entities.wrong_type
    assert {'kind': 'wrong_type', 'graph_key': key} in resp.anomalies


@pytest.mark.asyncio
async def test_verify_edge_counts_and_anomaly_lists():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': 'edge-1',
                'edge_key': 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES',
                'edge_type': 'Contains',
                'has_fact_embedding': False,
                'batch_id': BATCH,
            },
            {
                'uuid': 'edge-2',
                'edge_key': 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES',
                'edge_type': 'Contains',
                'has_fact_embedding': True,
                'batch_id': BATCH,
            },
        ]
    )
    req = _verify_request(
        entities=[],
        edges=[
            VerifyEdgeRef(edge_type='Contains', edge_key='CONTAINS::HR.SCHEMA->HR.EMPLOYEES'),
            VerifyEdgeRef(edge_type='DependsOn', edge_key='DEPENDS::MISSING'),
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.edges.expected == 2
    assert resp.edges.found == 1
    assert 'DEPENDS::MISSING' in resp.edges.missing
    assert 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES' in resp.edges.duplicate_edge_key
    assert 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES' in resp.edges.missing_embedding
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_edge_uuid_only_expectations_no_graph_key_attribute_access():
    """VerifyEdgeRef UUID expectations work; removed raw graph-key attrs absent."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    source_uuid = str(uuid.uuid4())
    target_uuid = str(uuid.uuid4())
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', edge_key),
                'edge_key': edge_key,
                'edge_type': 'Contains',
                'source_uuid': source_uuid,
                'target_uuid': target_uuid,
                'source_graph_key': 'SCHEMA::FE::ORCL.HR',
                'target_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'has_fact_embedding': True,
            }
        ]
    )
    edge_ref = VerifyEdgeRef(
        edge_type='Contains',
        edge_key=edge_key,
        expected_source_uuid=source_uuid,
        expected_target_uuid=target_uuid,
    )
    assert not hasattr(edge_ref, 'expected_source_graph_key')
    assert not hasattr(edge_ref, 'expected_target_graph_key')
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(batch_id=None, entities=[], edges=[edge_ref]),
    )
    assert resp.edges.endpoint_mismatch == []
    assert resp.edges.found == 1
    assert 'transaction' not in client.call_order
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_edge_true_endpoint_mismatch_is_distinct_from_type():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    expected_source_uuid = str(uuid.uuid4())
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', edge_key),
                'edge_key': edge_key,
                'edge_type': 'Contains',
                'source_uuid': str(uuid.uuid4()),
                'target_uuid': str(uuid.uuid4()),
                'source_graph_key': 'SCHEMA::WRONG',
                'target_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'has_fact_embedding': True,
            }
        ]
    )
    req = _verify_request(
        batch_id=None,
        entities=[],
        edges=[
            VerifyEdgeRef(
                edge_type='Contains',
                edge_key=edge_key,
                expected_source_uuid=expected_source_uuid,
            )
        ],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.edges.endpoint_mismatch == [edge_key]
    assert resp.edges.edge_type_mismatch == []
    assert {'kind': 'endpoint_mismatch', 'edge_key': edge_key} in resp.anomalies


@pytest.mark.asyncio
async def test_verify_edge_type_mismatch_never_becomes_endpoint_mismatch():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': 'stored-type-uuid',
                'edge_key': edge_key,
                'edge_type': 'DependsOn',
                'source_graph_key': 'SCHEMA::FE::ORCL.HR',
                'target_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'has_fact_embedding': True,
            }
        ]
    )
    req = _verify_request(
        batch_id=None,
        entities=[],
        edges=[VerifyEdgeRef(edge_type='Contains', edge_key=edge_key)],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert resp.edges.edge_type_mismatch == [edge_key]
    assert resp.edges.endpoint_mismatch == []
    assert {'kind': 'edge_type_mismatch', 'edge_key': edge_key} in resp.anomalies


@pytest.mark.asyncio
async def test_verify_edge_aggregates_anomalies_across_all_duplicate_rows_once():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    expected_uuid = catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', edge_key)
    expected_source_uuid = str(uuid.uuid4())
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': expected_uuid,
                'edge_key': edge_key,
                'edge_type': 'Contains',
                'source_uuid': expected_source_uuid,
                'source_graph_key': 'SCHEMA::FE::ORCL.HR',
                'has_fact_embedding': True,
            },
            {
                'uuid': 'rogue',
                'edge_key': edge_key,
                'edge_type': '',
                'source_uuid': str(uuid.uuid4()),
                'source_graph_key': 'SCHEMA::WRONG',
                'has_fact_embedding': False,
            },
        ]
    )
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(
            batch_id=None,
            entities=[],
            edges=[
                VerifyEdgeRef(
                    edge_type='Contains',
                    edge_key=edge_key,
                    expected_source_uuid=expected_source_uuid,
                )
            ],
        ),
    )
    assert resp.edges.duplicate_edge_key == [edge_key]
    assert resp.edges.uuid_mismatch == [edge_key]
    assert resp.edges.edge_type_mismatch == [edge_key]
    assert resp.edges.endpoint_mismatch == [edge_key]
    assert resp.edges.missing_embedding == [edge_key]


@pytest.mark.asyncio
async def test_verify_provenance_read_failure_is_internal_error_not_missing():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    service._store.match_provenance_presence = AsyncMock(side_effect=RuntimeError('db down'))
    resp = await service.verify_catalog_batch(
        client=client,
        request=_verify_request(require_provenance=True, entities=[], edges=[]),
    )
    assert resp.error_code == CatalogErrorCode.internal_error
    assert resp.error_message == 'verify provenance read failed'
    assert resp.missing_provenance == []


@pytest.mark.asyncio
async def test_verify_require_provenance_report_only_no_write():
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': ent_uuid,
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'name': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'labels': ['Entity', 'Table'],
                'neo4j_labels': ['Entity', 'Table'],
                'content_sha256': 'a' * 64,
                'has_name_embedding': True,
                'batch_id': BATCH,
            }
        ]
    )
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    service._store.match_provenance_presence = AsyncMock(
        return_value=[{'uuid': ent_uuid, 'has_provenance': False}]
    )
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.verify_catalog_batch(
        client=client, request=_verify_request(require_provenance=True, edges=[])
    )
    assert resp.require_provenance is True
    assert ent_uuid in resp.missing_provenance
    service._store.match_provenance_presence.assert_awaited()
    service._store.upsert_entity_item.assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_verify_never_embeds_or_writes():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    service._store.match_edges_for_verify = AsyncMock(return_value=[])
    service._store.upsert_entity_item = AsyncMock()
    service._ensure_schema = AsyncMock()
    await service.verify_catalog_batch(client=client, request=_verify_request())
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()
    service._store.upsert_entity_item.assert_not_awaited()
    service._ensure_schema.assert_not_awaited()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_mcp_tool_verify_catalog_batch_registered():
    server = _mcp_server()
    assert hasattr(server, 'verify_catalog_batch')
    assert callable(server.verify_catalog_batch)


# ---------------------------------------------------------------------------
# upsert_typed_edges
# ---------------------------------------------------------------------------

EDGE_BATCH = 'batch-edge-001'


def _edge(**overrides) -> CatalogEdgeItem:
    data = {
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


def _edge_request(
    edges: list[CatalogEdgeItem] | None = None,
    *,
    dry_run: bool = False,
    atomic: Literal[True] = True,
    batch_id: str = EDGE_BATCH,
    strict_endpoints: Literal[True] = True,
) -> UpsertTypedEdgesRequest:
    return UpsertTypedEdgesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=batch_id,
        edges=edges or [_edge()],
        dry_run=dry_run,
        atomic=atomic,
        strict_endpoints=strict_endpoints,
    )


def _typed_endpoint(uuid: str, graph_key: str, entity_type: str = 'Table') -> dict:
    return {
        'uuid': uuid,
        'name': graph_key,
        'graph_key': graph_key,
        'labels': ['Entity', entity_type],
        'neo4j_labels': ['Entity', entity_type],
        'group_id': GROUP,
    }


def _expected_entity_uuid(entity_type: str, graph_key: str) -> str:
    return catalog_entity_uuid(FIXED_NS, GROUP, entity_type, graph_key)


def _wire_ok_endpoints(
    service: CatalogService,
    src_uuid: str | None = None,
    tgt_uuid: str | None = None,
):
    src_uuid = src_uuid or _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    tgt_uuid = tgt_uuid or _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.DEPARTMENTS')

    async def _resolve(
        executor,
        *,
        group_id,
        graph_key,
        entity_type,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, tx, expected_uuid, kwargs)
        if graph_key == 'TABLE::FE::ORCL.HR.EMPLOYEES':
            return None, _typed_endpoint(src_uuid, graph_key)
        if graph_key == 'TABLE::FE::ORCL.HR.DEPARTMENTS':
            return None, _typed_endpoint(tgt_uuid, graph_key)
        return 'missing_endpoint', None

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    return src_uuid, tgt_uuid


@pytest.mark.asyncio
async def test_edge_feature_disabled_returns_structured_error_without_write():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    service._store.resolve_endpoint_typed = AsyncMock()
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert any(r.error_code == CatalogErrorCode.feature_disabled for r in resp.results)
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order
    service._store.resolve_endpoint_typed.assert_not_awaited()
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_service_enforces_configured_limit_below_hard_max():
    client = _make_client()
    cfg = CatalogConfig(
        enabled=True,
        uuid_namespace=str(FIXED_NS),
        max_edges_per_batch=1,
    )
    service = CatalogService(catalog_config=cfg)
    request = _edge_request([_edge(), _edge(edge_key='FK::SECOND')])
    resp = await service.upsert_typed_edges(client=client, request=request)
    assert all(r.error_code == CatalogErrorCode.batch_limit_exceeded for r in resp.results)
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_edge_missing_endpoint_before_embed_no_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.resolve_endpoint_typed = AsyncMock(return_value=('missing_endpoint', None))
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert any(r.error_code == CatalogErrorCode.missing_endpoint for r in resp.results)
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_source_endpoint_read_failure_is_internal_error_not_missing():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.resolve_endpoint_typed = AsyncMock(side_effect=RuntimeError('db down'))
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert resp.results[0].error_code != CatalogErrorCode.missing_endpoint
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_target_endpoint_read_failure_is_internal_error_not_missing():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _resolve(
        executor,
        *,
        group_id=None,
        graph_key=None,
        entity_type=None,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, tx, expected_uuid, kwargs)
        assert graph_key is not None
        if graph_key == 'TABLE::FE::ORCL.HR.EMPLOYEES':
            return None, _typed_endpoint(_expected_entity_uuid('Table', graph_key), graph_key)
        raise RuntimeError('db down')

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert 'target' in (resp.results[0].error_message or '')
    assert 'embed' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_endpoint_read_failure_atomic_rolls_back_batch():
    e1 = _edge(edge_key='FK::A.T1->A.T2', fact='fk one')
    e2 = _edge(edge_key='FK::A.T3->A.T4', fact='fk two')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.resolve_endpoint_typed = AsyncMock(side_effect=RuntimeError('db down'))
    service._store.upsert_edge_item = AsyncMock()
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    resp = await service.upsert_typed_edges(
        client=client, request=_edge_request([e1, e2], atomic=True)
    )
    assert resp.failed >= 1
    assert all(r.status in ('error', 'rolled_back') for r in resp.results)
    assert any(r.error_code == CatalogErrorCode.internal_error for r in resp.results)
    service._store.upsert_edge_item.assert_not_awaited()
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_edge_endpoint_type_mismatch_and_generic_conflict_no_create():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _resolve(
        executor, *, group_id=None, graph_key=None, entity_type=None, tx=None, **kwargs
    ):
        _ = (executor, group_id, entity_type, tx, kwargs)
        assert graph_key is not None
        if graph_key == 'TABLE::FE::ORCL.HR.EMPLOYEES':
            return 'endpoint_type_mismatch', {
                'uuid': 'wrong',
                'neo4j_labels': ['Entity', 'View'],
            }
        return 'generic_endpoint_conflict', {
            'uuid': 'gen',
            'neo4j_labels': ['Entity'],
        }

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    codes = {r.error_code for r in resp.results}
    assert CatalogErrorCode.endpoint_type_mismatch in codes or (
        CatalogErrorCode.generic_endpoint_conflict in codes
    )
    assert 'embed' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_embed_before_transaction_order():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock(
        return_value={
            'uuid': 'e1',
            'content_sha256': 'a' * 64,
            'batch_id': EDGE_BATCH,
            'status': 'created',
        }
    )
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert client.call_order.index('embed') < client.call_order.index('transaction')
    assert resp.results[0].status in ('created', 'updated', 'unchanged')


@pytest.mark.asyncio
async def test_edge_dry_run_embeds_but_never_writes_or_persists_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request(dry_run=True))
    assert 'embed' in client.call_order
    assert 'transaction' not in client.call_order
    service._store.upsert_edge_item.assert_not_awaited()
    assert resp.dry_run is True
    assert resp.results[0].status in ('created', 'updated', 'unchanged')
    assert resp.results[0].uuid is not None


@pytest.mark.asyncio
async def test_edge_create_persists_request_batch_id():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    src, tgt = _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    captured: dict = {}

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        captured.update(params)
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert captured.get('batch_id') == EDGE_BATCH
    assert captured.get('source_uuid') == src
    assert captured.get('target_uuid') == tgt
    assert captured.get('name') == 'ForeignKeyTo'
    assert resp.results[0].status == 'created'
    assert resp.created == 1


@pytest.mark.asyncio
async def test_edge_identical_hash_unchanged_leaves_batch_id():
    edge = _edge()
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
    payload = CatalogService.edge_canonical_payload(edge)
    digest = canonical_sha256(payload)
    src, tgt = (
        _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.EMPLOYEES'),
        _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.DEPARTMENTS'),
    )
    existing = {
        'uuid': edge_uuid,
        'content_sha256': digest,
        'batch_id': 'prior-edge-batch',
        'name': edge.edge_type,
        'edge_key': edge.edge_key,
        'source_uuid': src,
        'target_uuid': tgt,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service, src, tgt)
    service._store.get_edge_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([edge]))
    assert resp.results[0].status == 'unchanged'
    assert resp.unchanged == 1
    service._store.upsert_edge_item.assert_not_awaited()
    assert resp.results[0].uuid == edge_uuid
    assert resp.results[0].content_sha256 == digest


@pytest.mark.asyncio
async def test_edge_changed_update_passes_request_batch_id():
    edge = _edge(fact='changed fact text about fk')
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
    src, tgt = (
        _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.EMPLOYEES'),
        _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.DEPARTMENTS'),
    )
    existing = {
        'uuid': edge_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-edge-batch',
        'name': edge.edge_type,
        'edge_key': edge.edge_key,
        'source_uuid': src,
        'target_uuid': tgt,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service, src, tgt)
    service._store.get_edge_by_uuid = AsyncMock(return_value=existing)
    captured: dict = {}

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        captured.update(params)
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'updated',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([edge]))
    assert resp.results[0].status == 'updated'
    assert captured.get('batch_id') == EDGE_BATCH


@pytest.mark.asyncio
async def test_edge_identity_conflict_no_mutation():
    edge = _edge()
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
    existing = {
        'uuid': edge_uuid,
        'content_sha256': 'c' * 64,
        'batch_id': 'old',
        'name': 'Contains',  # wrong type for same uuid
        'edge_key': edge.edge_key,
        'source_uuid': _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.EMPLOYEES'),
        'target_uuid': _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.DEPARTMENTS'),
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=existing)
    # use real store method for conflict detection
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([edge]))
    assert any(r.error_code == CatalogErrorCode.edge_identity_conflict for r in resp.results)
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_divergent_duplicate_marks_later_repeat_conflicted():
    first = _edge(fact='A')
    divergent = _edge(fact='B')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock()

    resp = await service.upsert_typed_edges(
        client=client,
        request=_edge_request([first, divergent, first.model_copy(deep=True)]),
    )

    assert [result.index for result in resp.results] == [0, 1, 2]
    assert all(
        result.error_code == CatalogErrorCode.deterministic_uuid_conflict for result in resp.results
    )
    service._store.upsert_edge_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_two_foreign_key_same_endpoints_different_keys():
    e1 = _edge(edge_key='FK::HR.EMPLOYEES.DEPT->HR.DEPARTMENTS')
    e2 = _edge(edge_key='FK::HR.EMPLOYEES.MGR_DEPT->HR.DEPARTMENTS', fact='mgr dept fk')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)

    def _upsert_side(tx, *, params):
        _ = tx
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    upsert = AsyncMock(side_effect=_upsert_side)
    service._store.upsert_edge_item = upsert
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([e1, e2]))
    assert upsert.await_count == 2
    assert resp.created == 2
    assert resp.results[0].uuid != resp.results[1].uuid
    assert resp.results[0].edge_key == e1.edge_key
    assert resp.results[1].edge_key == e2.edge_key


@pytest.mark.asyncio
async def test_edge_atomic_rollback_on_store_failure():
    e1 = _edge(edge_key='FK::A.T1->A.T2', fact='fk one')
    e2 = _edge(edge_key='FK::A.T3->A.T4', fact='fk two')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _resolve(
        executor,
        *,
        group_id=None,
        graph_key=None,
        entity_type=None,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, tx, expected_uuid, kwargs)
        assert graph_key is not None
        et = entity_type or 'Table'
        return None, _typed_endpoint(_expected_entity_uuid(et, graph_key), graph_key, et)

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        if params['edge_key'] == 'FK::A.T3->A.T4':
            raise RuntimeError('neo4j boom')
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(
        client=client, request=_edge_request([e1, e2], atomic=True)
    )
    statuses = [r.status for r in resp.results]
    assert 'error' in statuses
    assert 'rolled_back' in statuses
    assert resp.rolled_back >= 1
    err = next(r for r in resp.results if r.status == 'error')
    assert err.error_code in (
        CatalogErrorCode.neo4j_transaction_failed,
        CatalogErrorCode.internal_error,
    )


@pytest.mark.asyncio
async def test_edge_no_queue_or_llm_calls():
    client = _make_client()
    queue = MagicMock()
    queue.add_episode = AsyncMock()
    llm = MagicMock()
    llm.generate_response = AsyncMock()
    client.llm_client = llm
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': EDGE_BATCH,
            'status': 'created',
        }
    )
    await service.upsert_typed_edges(client=client, request=_edge_request())
    queue.add_episode.assert_not_awaited()
    llm.generate_response.assert_not_called()


@pytest.mark.asyncio
async def test_edge_preserves_input_order_and_deterministic_uuid():
    e1 = _edge(edge_key='FK::A.T1->A.T2', fact='one')
    e2 = _edge(edge_key='FK::A.T3->A.T4', fact='two')
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())

    async def _resolve(
        executor,
        *,
        group_id=None,
        graph_key=None,
        entity_type=None,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, tx, expected_uuid, kwargs)
        assert graph_key is not None
        et = entity_type or 'Table'
        return None, _typed_endpoint(_expected_entity_uuid(et, graph_key), graph_key, et)

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'created',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([e1, e2]))
    assert [r.index for r in resp.results] == [0, 1]
    assert resp.results[0].edge_key == e1.edge_key
    assert resp.results[1].edge_key == e2.edge_key
    assert resp.results[0].uuid == catalog_edge_uuid(FIXED_NS, GROUP, e1.edge_type, e1.edge_key)
    assert resp.results[0].content_sha256 is not None
    assert len(resp.results[0].content_sha256) == 64


@pytest.mark.asyncio
async def test_edge_empty_upsert_row_fails_not_created():
    """Empty upsert row must not report created (TOCTOU / failed MATCH)."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock(return_value={})
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.neo4j_transaction_failed
    assert resp.created == 0


@pytest.mark.asyncio
async def test_edge_prefers_db_status_when_present():
    """DB create-token status is authoritative when present."""
    edge = _edge(fact='changed fact text about fk')
    edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
    src, tgt = (
        _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.EMPLOYEES'),
        _expected_entity_uuid('Table', 'TABLE::FE::ORCL.HR.DEPARTMENTS'),
    )
    existing = {
        'uuid': edge_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-edge-batch',
        'name': edge.edge_type,
        'edge_key': edge.edge_key,
        'source_uuid': src,
        'target_uuid': tgt,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service, src, tgt)
    service._store.get_edge_by_uuid = AsyncMock(return_value=existing)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'updated',
        }

    service._store.upsert_edge_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_edges(client=client, request=_edge_request([edge]))
    assert resp.results[0].status == 'updated'
    assert resp.updated == 1


@pytest.mark.asyncio
async def test_edge_in_tx_endpoint_race_rolls_back():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    call_n = {'n': 0}

    async def _resolve(
        executor,
        *,
        group_id=None,
        graph_key=None,
        entity_type=None,
        tx=None,
        expected_uuid=None,
        **kwargs,
    ):
        _ = (executor, group_id, entity_type, expected_uuid, kwargs)
        assert graph_key is not None
        call_n['n'] += 1
        # Pre-tx resolves OK; in-tx (tx is not None) races to missing
        if tx is not None:
            return 'missing_endpoint', None
        et = entity_type or 'Table'
        return None, _typed_endpoint(_expected_entity_uuid(et, graph_key), graph_key, et)

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_edge_item = AsyncMock(
        return_value={'uuid': 'x', 'content_sha256': 'a' * 64, 'batch_id': EDGE_BATCH}
    )
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.missing_endpoint
    service._store.upsert_edge_item.assert_not_awaited()
    assert call_n['n'] >= 3  # 2 pre-tx + at least 1 in-tx


@pytest.mark.asyncio
async def test_entity_empty_upsert_row_fails_not_created():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    service._store.upsert_entity_item = AsyncMock(return_value={})
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.neo4j_transaction_failed
    assert resp.created == 0


@pytest.mark.asyncio
async def test_entity_prefers_db_status_when_present():
    entity = _entity(summary='Changed summary')
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-batch',
        'labels': ['Entity', 'Table'],
        'neo4j_labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
            'status': 'updated',
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'updated'
    assert resp.updated == 1


@pytest.mark.asyncio
async def test_entity_falls_back_to_projected_when_db_status_absent():
    entity = _entity(summary='Changed summary')
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'b' * 64,
        'batch_id': 'old-batch',
        'labels': ['Entity', 'Table'],
        'neo4j_labels': ['Entity', 'Table'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)

    async def _upsert(tx, *, entity_type=None, params=None, **kwargs):
        _ = (tx, entity_type, kwargs)
        assert params is not None
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'batch_id': params['batch_id'],
        }

    service._store.upsert_entity_item = AsyncMock(side_effect=_upsert)
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'updated'
    assert resp.updated == 1


@pytest.mark.asyncio
async def test_entity_pre_read_failure_fails_closed_not_create():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(side_effect=RuntimeError('db down'))
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert resp.created == 0
    service._store.upsert_entity_item.assert_not_awaited()
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_edge_pre_read_failure_fails_closed_not_create():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_ok_endpoints(service)
    service._store.get_edge_by_uuid = AsyncMock(side_effect=RuntimeError('db down'))
    service._store.upsert_edge_item = AsyncMock()
    resp = await service.upsert_typed_edges(client=client, request=_edge_request())
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert resp.created == 0
    service._store.upsert_edge_item.assert_not_awaited()
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_entity_exact_label_rejects_extra_custom_labels():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'd' * 64,
        'batch_id': 'old',
        'labels': ['Entity', 'Table', 'View'],
        'neo4j_labels': ['Entity', 'Table', 'View'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert any(r.error_code == CatalogErrorCode.entity_type_conflict for r in resp.results)
    service._store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_generic_only_is_type_conflict():
    entity = _entity()
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)
    existing = {
        'uuid': ent_uuid,
        'content_sha256': 'd' * 64,
        'batch_id': 'old',
        'labels': ['Entity'],
        'neo4j_labels': ['Entity'],
        'name': entity.graph_key,
        'group_id': GROUP,
    }
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_entity_by_uuid = AsyncMock(return_value=existing)
    service._store.upsert_entity_item = AsyncMock()
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert any(r.error_code == CatalogErrorCode.entity_type_conflict for r in resp.results)
    service._store.upsert_entity_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_in_tx_label_race_rolls_back():
    entity = _entity()
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    call_n = {'n': 0}

    async def _get(executor=None, *, uuid=None, group_id=None, tx=None):
        _ = (executor, uuid, group_id)
        call_n['n'] += 1
        if tx is None:
            return None  # pre-read: absent
        # in-tx: raced into wrong-type entity
        return {
            'uuid': uuid,
            'labels': ['Entity', 'View'],
            'neo4j_labels': ['Entity', 'View'],
            'group_id': GROUP,
            'content_sha256': 'e' * 64,
        }

    service._store.get_entity_by_uuid = AsyncMock(side_effect=_get)
    service._store.upsert_entity_item = AsyncMock(
        return_value={
            'uuid': 'x',
            'content_sha256': 'a' * 64,
            'batch_id': BATCH,
            'status': 'created',
        }
    )
    resp = await service.upsert_typed_entities(client=client, request=_request([entity]))
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.entity_type_conflict
    service._store.upsert_entity_item.assert_not_awaited()
    assert call_n['n'] >= 2


@pytest.mark.asyncio
async def test_verify_edge_uuid_mismatch_reported():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_entities_for_verify = AsyncMock(return_value=[])
    edge_key = 'CONTAINS::HR.SCHEMA->HR.EMPLOYEES'
    service._store.match_edges_for_verify = AsyncMock(
        return_value=[
            {
                'uuid': 'wrong-uuid-not-deterministic',
                'edge_key': edge_key,
                'edge_type': 'Contains',
                'has_fact_embedding': True,
                'batch_id': BATCH,
            },
        ]
    )
    req = _verify_request(
        entities=[],
        edges=[VerifyEdgeRef(edge_type='Contains', edge_key=edge_key)],
    )
    resp = await service.verify_catalog_batch(client=client, request=req)
    assert edge_key in resp.edges.uuid_mismatch
    assert resp.edges.found == 1


@pytest.mark.asyncio
async def test_mcp_tool_upsert_typed_edges_registered():
    server = _mcp_server()
    assert hasattr(server, 'upsert_typed_edges')
    assert callable(server.upsert_typed_edges)


# ---------------------------------------------------------------------------
# Provenance service (Phase 2 PROV-01, PROV-03..06)
# ---------------------------------------------------------------------------

from models.catalog_provenance import (  # noqa: E402
    CatalogProvenanceEdgeTarget,
    CatalogProvenanceEntityTarget,
    CatalogSourceItem,
    UpsertProvenanceRequest,
)
from services.catalog_identity import catalog_mentions_uuid, catalog_source_uuid  # noqa: E402


def _source(**overrides) -> CatalogSourceItem:
    data = {
        'source_key': 'SRC::ddl.sql#employees',
        'reference_time': '2026-07-16T12:00:00Z',
        'attributes': {'doc': 'ddl.sql'},
        'metadata': None,
    }
    data.update(overrides)
    return CatalogSourceItem.model_validate(data)


def _prov_request(
    sources: list[CatalogSourceItem] | None = None,
    *,
    entity_targets: list[CatalogProvenanceEntityTarget] | None = None,
    edge_targets: list[CatalogProvenanceEdgeTarget] | None = None,
    dry_run: bool = False,
    atomic: Literal[True] = True,
    batch_id: str = 'batch-prov-001',
) -> UpsertProvenanceRequest:
    return UpsertProvenanceRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=batch_id,
        sources=sources or [_source()],
        entity_targets=entity_targets
        or [
            CatalogProvenanceEntityTarget(
                entity_type='Table', graph_key='TABLE::FE::ORCL.HR.EMPLOYEES'
            )
        ],
        edge_targets=edge_targets or [],
        dry_run=dry_run,
        atomic=atomic,
    )


def _wire_provenance_store(service: CatalogService, *, missing_entity: bool = False):
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', 'TABLE::FE::ORCL.HR.EMPLOYEES')
    src_uuid = catalog_source_uuid(FIXED_NS, GROUP, 'SRC::ddl.sql#employees')

    async def _resolve(executor, *, group_id, graph_key, entity_type, expected_uuid=None, tx=None):
        _ = executor, group_id, entity_type, expected_uuid, tx
        if missing_entity:
            return 'missing_endpoint', None
        return None, {'uuid': ent_uuid, 'name': graph_key, 'neo4j_labels': ['Entity', 'Table']}

    service._store.resolve_endpoint_typed = AsyncMock(side_effect=_resolve)
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=None)
    service._store.get_mentions_link = AsyncMock(return_value=None)

    async def _lock_targets(tx, *, group_id, entity_uuids, edge_uuids):
        _ = tx, group_id
        return [
            *(
                {'uuid': entity_uuid, 'kind': 'entity', 'labels': ['Entity', 'Table']}
                for entity_uuid in entity_uuids
            ),
            *({'uuid': edge_uuid, 'kind': 'edge', 'episodes': []} for edge_uuid in edge_uuids),
        ]

    service._store.lock_provenance_targets = AsyncMock(  # type: ignore[method-assign]
        side_effect=_lock_targets
    )
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock(return_value=None)

    async def _source_upsert(tx, *, params):
        _ = tx
        return {
            'uuid': src_uuid,
            'content_sha256': params['content_sha256'],
            'source_key': params['source_key'],
            'status': 'unchanged' if params['expected_exists'] else 'created',
            'error_code': None,
        }

    service._store.upsert_source_episode = AsyncMock(  # type: ignore[method-assign]
        side_effect=_source_upsert
    )
    service._store.upsert_mentions_link = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'm1', 'status': 'created'}
    )
    service._store.append_edge_episode = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'e1', 'episodes': [src_uuid]}
    )
    service._store.prepare_source_episode_params = CatalogNeo4jStore().prepare_source_episode_params
    return src_uuid, ent_uuid


# late import for prepare helper wiring
from services.catalog_store import CatalogNeo4jStore  # noqa: E402


@pytest.mark.asyncio
async def test_provenance_happy_path_writes_source_and_mentions_no_embed():
    client = _make_client()
    queue = MagicMock()
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    src_uuid, ent_uuid = _wire_provenance_store(service)

    resp = await service.upsert_provenance(client=client, request=_prov_request())
    assert resp.failed == 0
    assert resp.created >= 1 or resp.updated >= 1 or resp.unchanged >= 0
    assert any(r.uuid == src_uuid for r in resp.results)
    cast(AsyncMock, service._store.upsert_source_episode).assert_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_awaited()
    # no embedder / queue / llm on provenance path
    assert 'embed' not in client.call_order
    client.embedder.create.assert_not_awaited()
    queue.assert_not_called()
    # MENTIONS uses deterministic uuid
    mentions_call = cast(AsyncMock, service._store.upsert_mentions_link).await_args
    assert mentions_call is not None
    call_kwargs = mentions_call.kwargs
    expected_men = catalog_mentions_uuid(FIXED_NS, GROUP, src_uuid, ent_uuid)
    assert call_kwargs['mentions_uuid'] == expected_men
    assert call_kwargs['entity_uuid'] == ent_uuid


@pytest.mark.asyncio
async def test_provenance_missing_target_fail_closed_no_writes():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_provenance_store(service, missing_entity=True)

    resp = await service.upsert_provenance(client=client, request=_prov_request())
    assert resp.failed >= 1
    assert any(r.error_code == CatalogErrorCode.provenance_target_missing for r in resp.results)
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()
    cast(AsyncMock, service._store.append_edge_episode).assert_not_awaited()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_provenance_dry_run_no_writes():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_provenance_store(service)

    resp = await service.upsert_provenance(client=client, request=_prov_request(dry_run=True))
    assert resp.dry_run is True
    assert resp.failed == 0
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_provenance_idempotent_unchanged_skips_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    src_uuid, ent_uuid = _wire_provenance_store(service)
    item = _source()
    digest = CatalogService.source_canonical_payload(item)
    sha = canonical_sha256(digest)
    service._store.get_source_episode_by_uuid = AsyncMock(
        return_value={
            'uuid': src_uuid,
            'content_sha256': sha,
            'source_key': item.source_key,
        }
    )
    service._store.get_mentions_link = AsyncMock(
        return_value={'uuid': catalog_mentions_uuid(FIXED_NS, GROUP, src_uuid, ent_uuid)}
    )

    resp = await service.upsert_provenance(client=client, request=_prov_request(sources=[item]))
    assert resp.failed == 0
    assert resp.unchanged >= 1
    assert all(r.status == 'unchanged' for r in resp.results)
    source_write = cast(AsyncMock, service._store.upsert_source_episode)
    source_write.assert_awaited_once()
    source_call = source_write.await_args
    assert source_call is not None
    assert source_call.kwargs['params']['expected_exists'] is True
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()


@pytest.mark.asyncio
async def test_provenance_identical_duplicate_coalesces_with_stable_results():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_provenance_store(service)
    source = _source()

    resp = await service.upsert_provenance(
        client=client,
        request=_prov_request(sources=[source, source.model_copy(deep=True)]),
    )

    assert [(result.index, result.status) for result in resp.results] == [
        (0, 'created'),
        (1, 'created'),
    ]
    assert resp.results[0].uuid == resp.results[1].uuid
    assert cast(AsyncMock, service._store.upsert_source_episode).await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('reverse', [False, True])
async def test_provenance_divergent_duplicate_conflicts_are_order_independent(reverse):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_provenance_store(service)
    sources = [_source(attributes={'version': 1}), _source(attributes={'version': 2})]
    if reverse:
        sources.reverse()

    resp = await service.upsert_provenance(
        client=client,
        request=_prov_request(sources=sources),
    )

    assert [result.index for result in resp.results] == [0, 1]
    assert all(
        result.error_code == CatalogErrorCode.deterministic_uuid_conflict for result in resp.results
    )
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('read_name', ['get_mentions_link', 'get_edge_by_uuid'])
async def test_provenance_unchanged_link_read_failure_is_internal_error(read_name):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    src_uuid, ent_uuid = _wire_provenance_store(service)
    source = _source()
    source_row = {
        'uuid': src_uuid,
        'content_sha256': canonical_sha256(service.source_canonical_payload(source)),
        'source_key': source.source_key,
    }
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=source_row)
    edge_targets = []
    if read_name == 'get_mentions_link':
        service._store.get_mentions_link = AsyncMock(side_effect=TimeoutError('timed out'))
    else:
        edge = _edge()
        edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
        edge_targets = [
            CatalogProvenanceEdgeTarget(edge_type=edge.edge_type, edge_key=edge.edge_key)
        ]
        service._store.get_edge_by_uuid = AsyncMock(
            side_effect=[{'uuid': edge_uuid, 'name': edge.edge_type}, TimeoutError('timed out')]
        )
        service._store.get_mentions_link = AsyncMock(
            return_value={'uuid': catalog_mentions_uuid(FIXED_NS, GROUP, src_uuid, ent_uuid)}
        )

    resp = await service.upsert_provenance(
        client=client,
        request=_prov_request(sources=[source], edge_targets=edge_targets),
    )

    assert resp.results[0].error_code == CatalogErrorCode.internal_error
    assert resp.results[0].error_code != CatalogErrorCode.provenance_target_missing
    assert 'transaction' not in client.call_order
    cast(AsyncMock, service._store.ensure_uuid_uniqueness_constraints).assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('target_kind', ['entity', 'edge'])
async def test_provenance_unchanged_source_new_link_reports_updated(target_kind):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    src_uuid, ent_uuid = _wire_provenance_store(service)
    source = _source()
    service._store.get_source_episode_by_uuid = AsyncMock(
        return_value={
            'uuid': src_uuid,
            'content_sha256': canonical_sha256(service.source_canonical_payload(source)),
            'source_key': source.source_key,
        }
    )
    entity_targets = []
    edge_targets = []
    if target_kind == 'entity':
        service._store.get_mentions_link = AsyncMock(return_value=None)
    else:
        edge = _edge()
        edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
        edge_targets = [
            CatalogProvenanceEdgeTarget(edge_type=edge.edge_type, edge_key=edge.edge_key)
        ]
        service._store.get_edge_by_uuid = AsyncMock(
            return_value={'uuid': edge_uuid, 'name': edge.edge_type, 'episodes': []}
        )
        entity_targets = [
            CatalogProvenanceEntityTarget(
                entity_type='Table', graph_key='TABLE::FE::ORCL.HR.EMPLOYEES'
            )
        ]
        service._store.get_mentions_link = AsyncMock(
            return_value={'uuid': catalog_mentions_uuid(FIXED_NS, GROUP, src_uuid, ent_uuid)}
        )
    service._store.upsert_source_episode = AsyncMock(
        return_value={'uuid': src_uuid, 'status': 'unchanged'}
    )

    resp = await service.upsert_provenance(
        client=client,
        request=_prov_request(
            sources=[source], entity_targets=entity_targets, edge_targets=edge_targets
        ),
    )

    assert resp.results[0].status == 'updated'
    source_call = cast(AsyncMock, service._store.upsert_source_episode).await_args
    assert source_call is not None
    params = source_call.kwargs['params']
    if target_kind == 'edge':
        assert params['entity_edges'] == [edge_uuid]


@pytest.mark.asyncio
@pytest.mark.parametrize('drift', ['source_key', 'content_sha256', 'mentions', 'updated_mentions'])
async def test_provenance_atomic_cas_or_locked_link_drift_aborts_before_link_mutation(drift):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    src_uuid, ent_uuid = _wire_provenance_store(service)
    source = _source(attributes={'version': 2}) if drift == 'updated_mentions' else _source()
    digest = canonical_sha256(service.source_canonical_payload(source))
    stored_digest = (
        canonical_sha256(service.source_canonical_payload(_source(attributes={'version': 1})))
        if drift == 'updated_mentions'
        else digest
    )
    preflight = {
        'uuid': src_uuid,
        'source_key': source.source_key,
        'content_sha256': stored_digest,
    }
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=preflight)
    mention = {'uuid': catalog_mentions_uuid(FIXED_NS, GROUP, src_uuid, ent_uuid)}
    service._store.get_mentions_link = AsyncMock(
        side_effect=[mention, None if drift in {'mentions', 'updated_mentions'} else mention]
    )
    cas_error = (
        CatalogErrorCode.deterministic_uuid_conflict.value
        if drift == 'source_key'
        else CatalogErrorCode.batch_conflict.value
        if drift == 'content_sha256'
        else None
    )
    service._store.upsert_source_episode = AsyncMock(
        return_value={
            'uuid': src_uuid,
            'status': 'error' if cas_error else 'updated',
            'error_code': cas_error,
        }
    )

    resp = await service.upsert_provenance(
        client=client,
        request=_prov_request(sources=[source]),
    )

    assert resp.failed == 1
    assert resp.results[0].error_code in {
        CatalogErrorCode.deterministic_uuid_conflict,
        CatalogErrorCode.batch_conflict,
    }
    source_write = cast(AsyncMock, service._store.upsert_source_episode)
    source_write.assert_awaited_once()
    if cas_error:
        source_call = source_write.await_args
        assert source_call is not None
        params = source_call.kwargs['params']
        assert params['expected_exists'] is True
        assert params['expected_source_key'] == source.source_key
        assert params['expected_content_sha256'] == stored_digest
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()


def test_provenance_request_rejects_non_atomic_false():
    """catalog-v2 locks atomic=True; non-atomic path is not a valid request."""
    from pydantic import ValidationError

    first = _source()
    second = _source(source_key='SRC::ddl.sql#departments')
    with pytest.raises(ValidationError) as exc:
        UpsertProvenanceRequest.model_validate(
            {
                'identity_schema_version': 'catalog-v2',
                'system_key': 'FE',
                'group_id': GROUP,
                'batch_id': 'batch-prov-001',
                'sources': [first.model_dump(), second.model_dump()],
                'entity_targets': [
                    {
                        'entity_type': 'Table',
                        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                    }
                ],
                'atomic': False,
            }
        )
    assert any('atomic' in str(err.get('loc')) for err in exc.value.errors())


@pytest.mark.asyncio
async def test_provenance_feature_disabled_no_write():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    resp = await service.upsert_provenance(client=client, request=_prov_request())
    assert any(r.error_code == CatalogErrorCode.feature_disabled for r in resp.results)
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_mcp_tool_upsert_provenance_registered():
    server = _mcp_server()
    assert hasattr(server, 'upsert_provenance')
    assert callable(server.upsert_provenance)


# ------------------------------------------------------------------
# get_catalog_ingest_status (STAT-05/06)
# ------------------------------------------------------------------


def _status_request(batch_id: str = BATCH) -> GetCatalogIngestStatusRequest:
    return GetCatalogIngestStatusRequest(group_id=GROUP, batch_id=batch_id)


@pytest.mark.asyncio
async def test_status_found_maps_response_no_payload_fields():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    batch_uuid = catalog_batch_uuid(FIXED_NS, GROUP, BATCH)
    service._store.get_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': batch_uuid,
            'group_id': GROUP,
            'batch_id': BATCH,
            'status': 'committed',
            'request_sha256': 'a' * 64,
            'catalog_sha256': 'b' * 64,
            'entity_count': 2,
            'edge_count': 1,
            'provenance_count': 0,
            'error_summary': '',
            'created_at': '2026-07-17T00:00:00+00:00',
            'updated_at': '2026-07-17T00:01:00+00:00',
            'committed_at': '2026-07-17T00:01:00+00:00',
        }
    )
    resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp.group_id == GROUP
    assert resp.batch_id == BATCH
    assert resp.batch_uuid == batch_uuid
    assert resp.status == 'committed'
    assert resp.entity_count == 2
    assert resp.edge_count == 1
    assert resp.error_summary == ''
    # no payload / secret fields on response model
    dumped = resp.model_dump()
    for banned in ('payload', 'entities', 'edges', 'sources', 'api_key', 'password'):
        assert banned not in dumped
    get_status = cast(AsyncMock, service._store.get_batch_status)
    get_status.assert_awaited_once()
    status_call = get_status.await_args
    assert status_call is not None
    call_kwargs = status_call.kwargs
    assert call_kwargs['uuid'] == batch_uuid
    assert call_kwargs['group_id'] == GROUP
    # read-only: no write tx / embed
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_missing_returns_structured_not_found_no_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_batch_status = AsyncMock(return_value=None)
    resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp.group_id == GROUP
    assert resp.batch_id == BATCH
    assert resp.batch_uuid == catalog_batch_uuid(FIXED_NS, GROUP, BATCH)
    assert resp.error_code is not None
    assert resp.error_code in (
        CatalogErrorCode.validation_error,
        CatalogErrorCode.internal_error,
        CatalogErrorCode.provenance_target_missing,
    ) or resp.error_code.value in (
        'validation_error',
        'internal_error',
        'not_found',
        'batch_not_found',
        'provenance_target_missing',
    )
    # Prefer explicit not-found semantics when available (error_summary, no error_message field)
    assert resp.error_summary
    assert 'not' in resp.error_summary.lower() or 'missing' in resp.error_summary.lower()
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order
    # get_batch_status still called (read)
    service._store.get_batch_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_catalog_status_logs_omit_group_id_runtime(caplog: pytest.LogCaptureFixture):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.get_batch_status = AsyncMock(return_value=None)

    with caplog.at_level(logging.INFO):
        await service.get_catalog_ingest_status(client=client, request=_status_request())

    _assert_group_id_absent(_catalog_records(caplog))


@pytest.mark.asyncio
async def test_status_reinit_new_service_reads_from_store():
    """Restart simulation: new CatalogService + same store still reads Neo4j state."""
    client = _make_client()
    store = CatalogNeo4jStore()
    batch_uuid = catalog_batch_uuid(FIXED_NS, GROUP, BATCH)
    row = {
        'uuid': batch_uuid,
        'group_id': GROUP,
        'batch_id': BATCH,
        'status': 'failed',
        'request_sha256': None,
        'catalog_sha256': None,
        'entity_count': 0,
        'edge_count': 0,
        'provenance_count': 0,
        'error_summary': 'neo4j transaction failed',
        'created_at': '2026-07-17T00:00:00+00:00',
        'updated_at': '2026-07-17T00:02:00+00:00',
        'committed_at': None,
    }
    store.get_batch_status = AsyncMock(return_value=row)  # type: ignore[method-assign]

    service_a = CatalogService(catalog_config=_enabled_config(), store=store)
    resp_a = await service_a.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp_a.status == 'failed'
    assert resp_a.error_summary == 'neo4j transaction failed'

    # New service instance (reinit) with same store/driver
    service_b = CatalogService(catalog_config=_enabled_config(), store=store)
    resp_b = await service_b.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp_b.status == 'failed'
    assert resp_b.batch_uuid == batch_uuid
    assert resp_b.error_summary == 'neo4j transaction failed'
    assert store.get_batch_status.await_count == 2
    assert 'transaction' not in client.call_order
    assert 'embed' not in client.call_order


@pytest.mark.asyncio
async def test_status_feature_disabled_no_store_read():
    client = _make_client()
    service = CatalogService(catalog_config=_disabled_config())
    service._store.get_batch_status = AsyncMock(return_value={'status': 'committed'})
    resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp.error_code == CatalogErrorCode.feature_disabled
    service._store.get_batch_status.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_status_no_queue_or_llm():
    client = _make_client()
    queue = MagicMock()
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    batch_uuid = catalog_batch_uuid(FIXED_NS, GROUP, BATCH)
    service._store.get_batch_status = AsyncMock(
        return_value={
            'uuid': batch_uuid,
            'group_id': GROUP,
            'batch_id': BATCH,
            'status': 'committed',
            'entity_count': 0,
            'edge_count': 0,
            'provenance_count': 0,
            'error_summary': '',
        }
    )
    await service.get_catalog_ingest_status(client=client, request=_status_request())
    queue.assert_not_called()
    client.llm_client.assert_not_called()
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_tool_get_catalog_ingest_status_registered():
    server = _mcp_server()
    assert hasattr(server, 'get_catalog_ingest_status')
    assert callable(server.get_catalog_ingest_status)


# ------------------------------------------------------------------
# upsert_catalog_batch preflight (BATC-03..05, BATC-09/10)
# ------------------------------------------------------------------

BATCH_ATOMIC = 'batch-atomic-001'


def _batch_request(
    *,
    entities: list[CatalogEntityItem] | None = None,
    edges: list[CatalogEdgeItem] | None = None,
    provenance: NestedProvenancePayload | None = None,
    dry_run: bool = False,
    request_sha256: str | None = None,
) -> UpsertCatalogBatchRequest:
    return UpsertCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=BATCH_ATOMIC,
        entities=entities if entities is not None else [_entity()],
        edges=edges if edges is not None else [],
        provenance=provenance,
        dry_run=dry_run,
        request_sha256=request_sha256,
    )


def _wire_batch_preflight(service: CatalogService) -> None:
    service._store.get_batch_status = AsyncMock(return_value=None)  # type: ignore[method-assign]

    async def _entity_by_uuid(executor, *, uuid, group_id, tx=None):
        _ = executor, uuid, group_id
        if tx is None:
            return None
        return None

    service._store.get_entity_by_uuid = AsyncMock(  # type: ignore[method-assign]
        side_effect=_entity_by_uuid
    )
    service._store.get_edge_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._store.resolve_endpoint_typed = AsyncMock(  # type: ignore[method-assign]
        return_value=('missing_endpoint', None)
    )
    service._store.ensure_uuid_uniqueness_constraints = AsyncMock(  # type: ignore[method-assign]
        return_value=None
    )
    service._store.claim_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'uuid': 'claim', 'status': 'writing'}
    )
    service._store.upsert_batch_status = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_entity_item = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_edge_item = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_source_episode = AsyncMock()  # type: ignore[method-assign]
    service._store.upsert_mentions_link = AsyncMock()  # type: ignore[method-assign]
    service._store.append_edge_episode = AsyncMock()  # type: ignore[method-assign]
    service._store.lock_provenance_targets = AsyncMock(  # type: ignore[method-assign]
        return_value=[]
    )


@pytest.mark.asyncio
async def test_batch_dry_run_endpoint_union_no_writes_or_status():
    employee = _entity()
    department = _entity(
        graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    request = _batch_request(
        entities=[employee, department],
        edges=[_edge()],
        dry_run=True,
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.dry_run is True
    assert resp.status == 'validating'
    assert resp.failed == 0
    # Both edge endpoints came from the same-request union; no persisted lookup.
    cast(AsyncMock, service._store.resolve_endpoint_typed).assert_not_awaited()
    cast(AsyncMock, service._store.ensure_uuid_uniqueness_constraints).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_batch_status).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_edge_item).assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_rejects_caller_hash_mismatch_before_status_read_or_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(request_sha256='b' * 64),
    )

    assert resp.error_code == CatalogErrorCode.content_hash_mismatch
    cast(AsyncMock, service._store.get_batch_status).assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_committed_different_hash_returns_batch_conflict_before_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    service._store.get_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'status': 'committed', 'request_sha256': 'a' * 64}
    )

    request = _batch_request()
    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.error_code == CatalogErrorCode.batch_conflict
    assert resp.failed >= 1
    assert 'embed' not in client.call_order
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_committed_same_hash_returns_unchanged_short_circuit():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    request = _batch_request()
    expected_hash = CatalogService.batch_request_sha256(request)
    service._store.get_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={'status': 'committed', 'request_sha256': expected_hash}
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.status == 'committed'
    assert resp.error_code is None
    assert resp.entity_unchanged == len(request.entities)
    assert 'embed' not in client.call_order
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_dry_run_rejects_bad_nested_source_hash_before_side_effects():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    provenance = NestedProvenancePayload(
        sources=[_source().model_copy(update={'content_sha256': 'a' * 64})]
    )

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(entities=[], provenance=provenance, dry_run=True),
    )

    assert resp.error_code == CatalogErrorCode.content_hash_mismatch
    client.embedder.create.assert_not_awaited()
    cast(AsyncMock, service._store.ensure_uuid_uniqueness_constraints).assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_dry_run_resolves_missing_provenance_target_before_side_effects():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    provenance = NestedProvenancePayload(
        sources=[_source()],
        entity_targets=[
            CatalogProvenanceEntityTarget(
                entity_type='Table', graph_key='TABLE::FE::ORCL.HR.MISSING'
            )
        ],
    )

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(entities=[], provenance=provenance, dry_run=True),
    )

    assert resp.error_code == CatalogErrorCode.provenance_target_missing
    client.embedder.create.assert_not_awaited()
    cast(AsyncMock, service._store.ensure_uuid_uniqueness_constraints).assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_dry_run_reports_provenance_projection_counts_and_duplicates():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    source = _source()
    provenance = NestedProvenancePayload(sources=[source, source.model_copy(deep=True)])

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(entities=[], provenance=provenance, dry_run=True),
    )

    assert [(result.index, result.status) for result in resp.results] == [
        (0, 'created'),
        (1, 'created'),
    ]
    assert resp.results[0].uuid == resp.results[1].uuid
    assert resp.provenance_created == 2
    assert resp.provenance_updated == 0
    assert resp.provenance_unchanged == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('reverse', [False, True])
async def test_batch_divergent_provenance_duplicate_is_order_independent(reverse):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]
    sources = [_source(attributes={'version': 1}), _source(attributes={'version': 2})]
    if reverse:
        sources.reverse()

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(
            entities=[], provenance=NestedProvenancePayload(sources=sources), dry_run=True
        ),
    )

    assert [result.index for result in resp.results] == [0, 1]
    assert all(
        result.error_code == CatalogErrorCode.deterministic_uuid_conflict for result in resp.results
    )
    cast(AsyncMock, service._store.upsert_source_episode).assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('read_name', ['get_mentions_link', 'get_edge_by_uuid'])
async def test_batch_unchanged_provenance_link_read_failure_is_structured(read_name):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    source = _source()
    src_uuid = catalog_source_uuid(FIXED_NS, GROUP, source.source_key)
    source_row = {
        'uuid': src_uuid,
        'content_sha256': canonical_sha256(service.source_canonical_payload(source)),
        'source_key': source.source_key,
    }
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=source_row)
    employee = _entity()
    provenance_kwargs = {
        'sources': [source],
        'entity_targets': [
            CatalogProvenanceEntityTarget(
                entity_type=employee.entity_type, graph_key=employee.graph_key
            )
        ],
    }
    if read_name == 'get_mentions_link':
        service._store.get_mentions_link = AsyncMock(side_effect=TimeoutError('timed out'))
    else:
        edge = _edge()
        provenance_kwargs['edge_targets'] = [
            CatalogProvenanceEdgeTarget(edge_type=edge.edge_type, edge_key=edge.edge_key)
        ]
        service._store.get_edge_by_uuid = AsyncMock(
            side_effect=[
                None,
                TimeoutError('timed out'),
            ]
        )
        service._store.get_mentions_link = AsyncMock(return_value={'uuid': 'existing-mention'})

    entities = [employee]
    if read_name == 'get_edge_by_uuid':
        entities.append(
            _entity(
                graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
                name_raw='DEPARTMENTS',
                name_canonical='departments',
                database_qualified_name='HR.DEPARTMENTS',
            )
        )
    request = _batch_request(
        entities=entities,
        edges=[_edge()] if read_name == 'get_edge_by_uuid' else [],
        provenance=NestedProvenancePayload(**provenance_kwargs),
    )
    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.error_code == CatalogErrorCode.internal_error
    assert resp.error_code != CatalogErrorCode.provenance_target_missing
    client.embedder.create.assert_not_awaited()
    cast(AsyncMock, service._store.ensure_uuid_uniqueness_constraints).assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_missing_endpoint_preflight_stops_embedding():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    request = _batch_request(
        entities=[],
        edges=[_edge()],
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.error_code in (
        CatalogErrorCode.missing_endpoint,
        CatalogErrorCode.batch_conflict,
    )
    assert resp.failed >= 1
    assert cast(AsyncMock, service._store.resolve_endpoint_typed).await_count >= 1
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_batch_divergent_duplicate_preflight_stops_embedding():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    request = _batch_request(
        entities=[_entity(summary='first'), _entity(summary='second')],
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.error_code == CatalogErrorCode.batch_conflict
    assert resp.failed == 2
    assert all(r.error_code == CatalogErrorCode.deterministic_uuid_conflict for r in resp.results)
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['entity', 'edge'])
async def test_batch_divergent_duplicate_marks_later_repeat_conflicted(kind):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    if kind == 'entity':
        first = _entity(summary='A')
        request = _batch_request(
            entities=[first, _entity(summary='B'), first.model_copy(deep=True)],
        )
    else:
        first = _edge(fact='A')
        request = _batch_request(
            entities=[],
            edges=[first, _edge(fact='B'), first.model_copy(deep=True)],
        )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert [result.index for result in resp.results] == [0, 1, 2]
    assert all(
        result.error_code == CatalogErrorCode.deterministic_uuid_conflict for result in resp.results
    )
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_edge_item).assert_not_awaited()
    client.embedder.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_collects_all_known_conflicts_before_embed():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    service._store.resolve_endpoint_typed = AsyncMock(  # type: ignore[method-assign]
        return_value=('missing_endpoint', None)
    )
    request = _batch_request(
        entities=[_entity(summary='first'), _entity(summary='second')],
        edges=[_edge(edge_key='FK::ONE'), _edge(edge_key='FK::TWO', fact='second fk')],
    )

    resp = await service.upsert_catalog_batch(client=client, request=request)

    assert resp.failed >= 4
    assert {r.error_code for r in resp.results} >= {
        CatalogErrorCode.deterministic_uuid_conflict,
        CatalogErrorCode.missing_endpoint,
    }
    # Both edge items were examined; preflight did not stop at the first conflict.
    assert cast(AsyncMock, service._store.resolve_endpoint_typed).await_count == 4
    client.embedder.create.assert_not_awaited()
    assert 'transaction' not in client.call_order


# ------------------------------------------------------------------
# upsert_catalog_batch atomic write (BATC-06..08)
# ------------------------------------------------------------------


def _install_batch_write_mocks(service: CatalogService, client) -> list[str]:
    events: list[str] = []

    async def _entity_write(tx, *, entity_type, params):
        _ = tx, entity_type
        events.append('entity_write')
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'status': 'created',
        }

    async def _edge_write(tx, *, params):
        _ = tx
        events.append('edge_write')
        return {
            'uuid': params['uuid'],
            'content_sha256': params['content_sha256'],
            'status': 'created',
        }

    async def _status_write(tx, *, params):
        _ = tx
        events.append(f'status_{params["status"]}')
        return {
            'uuid': params['uuid'],
            'status': params['status'],
            'request_sha256': params.get('request_sha256'),
        }

    async def _claim(tx, *, params):
        _ = tx
        events.append('status_claim')
        return {
            'uuid': params['uuid'],
            'status': 'writing',
            'request_sha256': params['request_sha256'],
        }

    service._store.claim_batch_status = AsyncMock(side_effect=_claim)  # type: ignore[method-assign]
    service._store.upsert_entity_item = AsyncMock(side_effect=_entity_write)  # type: ignore[method-assign]
    service._store.upsert_edge_item = AsyncMock(side_effect=_edge_write)  # type: ignore[method-assign]
    service._store.upsert_batch_status = AsyncMock(side_effect=_status_write)  # type: ignore[method-assign]
    original_create = client.embedder.create

    async def _embed(*args, **kwargs):
        events.append('embed')
        return await original_create(*args, **kwargs)

    client.embedder.create = AsyncMock(side_effect=_embed)
    return events


@pytest.mark.asyncio
async def test_batch_embedding_completes_before_single_domain_transaction():
    employee = _entity()
    department = _entity(
        graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(entities=[employee, department], edges=[_edge()]),
    )

    assert resp.status == 'committed'
    assert client.call_order.count('transaction') == 1
    assert events[:3] == ['embed', 'embed', 'embed']
    assert events[3:] == [
        'status_claim',
        'entity_write',
        'entity_write',
        'edge_write',
        'status_committed',
    ]
    cast(AsyncMock, service._store.upsert_batch_status).assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_embedding_failure_opens_no_transaction_or_status():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    client.embedder.create = AsyncMock(side_effect=RuntimeError('embed unavailable'))

    resp = await service.upsert_catalog_batch(client=client, request=_batch_request())

    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode.embedding_failed
    assert 'transaction' not in client.call_order
    cast(AsyncMock, service._store.upsert_batch_status).assert_not_awaited()
    cast(AsyncMock, service._store.upsert_entity_item).assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_transaction_claim_rejects_different_hash_before_domain_write():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)
    service._store.claim_batch_status = AsyncMock(  # type: ignore[method-assign]
        return_value={
            'uuid': 'claim',
            'status': 'writing',
            'request_sha256': 'f' * 64,
        }
    )

    resp = await service.upsert_catalog_batch(client=client, request=_batch_request())

    assert resp.error_code == CatalogErrorCode.batch_conflict
    assert 'entity_write' not in events
    cast(AsyncMock, service._store.upsert_batch_status).assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['entity', 'edge'])
async def test_batch_unchanged_domain_drift_aborts_before_commit_status(kind):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)
    employee = _entity()
    employee_uuid = catalog_entity_uuid(FIXED_NS, GROUP, employee.entity_type, employee.graph_key)
    employee_hash = canonical_sha256(service.entity_canonical_payload(employee))
    entities = [employee]
    edges = []

    if kind == 'entity':

        async def _entity_by_uuid(executor, *, uuid, group_id, tx=None):
            _ = executor, uuid, group_id
            return {
                'uuid': employee_uuid,
                'content_sha256': employee_hash if tx is None else 'f' * 64,
                'labels': ['Entity', 'Table'],
                'name': employee.graph_key,
                'graph_key': employee.graph_key,
                'name_raw': employee.name_raw,
                'name_canonical': employee.name_canonical,
            }

        service._store.get_entity_by_uuid = AsyncMock(side_effect=_entity_by_uuid)
    else:
        department = _entity(
            graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
            name_raw='DEPARTMENTS',
            name_canonical='departments',
            database_qualified_name='HR.DEPARTMENTS',
        )
        entities = [employee, department]
        edge = _edge()
        edges = [edge]
        edge_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)
        edge_hash = canonical_sha256(service.edge_canonical_payload(edge))

        async def _entity_by_uuid(executor, *, uuid, group_id, tx=None):
            _ = executor, group_id, tx
            item = employee if uuid == employee_uuid else department
            return {
                'uuid': uuid,
                'content_sha256': canonical_sha256(service.entity_canonical_payload(item)),
                'labels': ['Entity', item.entity_type],
                'name': item.graph_key,
                'graph_key': item.graph_key,
                'name_raw': item.name_raw,
                'name_canonical': item.name_canonical,
            }

        async def _edge_by_uuid(executor, *, uuid, group_id, tx=None):
            _ = executor, uuid, group_id
            return {
                'uuid': edge_uuid,
                'content_sha256': edge_hash if tx is None else 'f' * 64,
                'name': edge.edge_type,
                'edge_key': edge.edge_key,
                'source_uuid': catalog_entity_uuid(
                    FIXED_NS, GROUP, edge.source_entity_type, edge.source_graph_key
                ),
                'target_uuid': catalog_entity_uuid(
                    FIXED_NS, GROUP, edge.target_entity_type, edge.target_graph_key
                ),
            }

        service._store.get_entity_by_uuid = AsyncMock(side_effect=_entity_by_uuid)
        service._store.get_edge_by_uuid = AsyncMock(side_effect=_edge_by_uuid)

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(entities=entities, edges=edges),
    )

    assert resp.status == 'failed'
    assert resp.error_code in (
        CatalogErrorCode.batch_conflict,
        CatalogErrorCode.neo4j_transaction_failed,
    )
    assert 'status_committed' not in events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('drift', 'expected_code'),
    [
        ('source_key', CatalogErrorCode.deterministic_uuid_conflict),
        ('content_sha256', CatalogErrorCode.batch_conflict),
        ('mentions', CatalogErrorCode.batch_conflict),
        ('updated_mentions', CatalogErrorCode.batch_conflict),
    ],
)
async def test_batch_atomic_cas_or_locked_link_drift_aborts_before_link_mutation(
    drift, expected_code
):
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)

    @asynccontextmanager
    async def _transaction():
        client.call_order.append('transaction')
        try:
            yield client.tx
        except Exception:
            events.append('rollback')
            raise

    client.driver.transaction = _transaction
    source = _source(attributes={'version': 2}) if drift == 'updated_mentions' else _source()
    src_uuid = catalog_source_uuid(FIXED_NS, GROUP, source.source_key)
    digest = canonical_sha256(service.source_canonical_payload(source))
    stored_digest = (
        canonical_sha256(service.source_canonical_payload(_source(attributes={'version': 1})))
        if drift == 'updated_mentions'
        else digest
    )
    preflight = {
        'uuid': src_uuid,
        'source_key': source.source_key,
        'content_sha256': stored_digest,
    }
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=preflight)
    employee = _entity()
    entity_uuid = catalog_entity_uuid(FIXED_NS, GROUP, employee.entity_type, employee.graph_key)
    service._store.lock_provenance_targets = AsyncMock(
        return_value=[{'uuid': entity_uuid, 'kind': 'entity', 'labels': ['Entity', 'Table']}]
    )
    mentions_uuid = catalog_mentions_uuid(FIXED_NS, GROUP, src_uuid, entity_uuid)
    mention = {'uuid': mentions_uuid}
    service._store.get_mentions_link = AsyncMock(
        side_effect=[mention, None if drift in {'mentions', 'updated_mentions'} else mention]
    )
    cas_error = (
        CatalogErrorCode.deterministic_uuid_conflict.value
        if drift == 'source_key'
        else CatalogErrorCode.batch_conflict.value
        if drift == 'content_sha256'
        else None
    )
    service._store.upsert_source_episode = AsyncMock(
        return_value={
            'uuid': src_uuid,
            'status': 'error' if cas_error else 'updated',
            'error_code': cas_error,
        }
    )
    provenance = NestedProvenancePayload(
        sources=[source],
        entity_targets=[
            CatalogProvenanceEntityTarget(
                entity_type=employee.entity_type,
                graph_key=employee.graph_key,
            )
        ],
    )

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(entities=[employee], provenance=provenance),
    )

    assert resp.status == 'failed'
    assert resp.error_code == expected_code
    assert resp.error_message == 'provenance invariant changed in write transaction'
    assert client.call_order.count('transaction') == 2
    assert events.index('rollback') < events.index('status_failed')
    status_call = cast(AsyncMock, service._store.upsert_batch_status).await_args
    assert status_call is not None
    assert status_call.kwargs['params']['status'] == 'failed'
    assert status_call.kwargs['params']['error_summary'] == expected_code.value
    source_write = cast(AsyncMock, service._store.upsert_source_episode)
    source_write.assert_awaited_once()
    if cas_error:
        source_call = source_write.await_args
        assert source_call is not None
        params = source_call.kwargs['params']
        assert params['expected_content_sha256'] == stored_digest
    cast(AsyncMock, service._store.upsert_mentions_link).assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_domain_failure_rolls_back_then_writes_failed_status_separately():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)
    domain_calls = {'count': 0}

    @asynccontextmanager
    async def _transaction():
        domain_calls['count'] += 1
        client.call_order.append('transaction')
        try:
            yield client.tx
        except Exception:
            events.append('rollback')
            raise

    client.driver.transaction = _transaction
    service._store.upsert_entity_item = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError('secret payload must never escape')
    )

    resp = await service.upsert_catalog_batch(client=client, request=_batch_request())

    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode.neo4j_transaction_failed
    assert domain_calls['count'] == 2
    assert events.index('rollback') < events.index('status_failed')
    status_call = cast(AsyncMock, service._store.upsert_batch_status).await_args
    assert status_call is not None
    failed_params = status_call.kwargs['params']
    assert failed_params['status'] == 'failed'
    assert failed_params['error_summary'] == 'RuntimeError'
    assert 'secret payload' not in failed_params['error_summary']


@pytest.mark.asyncio
async def test_batch_failed_status_write_failure_preserves_original_error():
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    _install_batch_write_mocks(service, client)
    service._store.upsert_entity_item = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError('domain failed')
    )
    service._store.upsert_batch_status = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError('status failed')
    )

    resp = await service.upsert_catalog_batch(client=client, request=_batch_request())

    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode.neo4j_transaction_failed
    assert resp.error_message == 'neo4j transaction failed'
    assert client.call_order.count('transaction') == 2


@pytest.mark.asyncio
async def test_batch_writes_edges_before_provenance_append_in_same_transaction():
    employee = _entity()
    department = _entity(
        graph_key='TABLE::FE::ORCL.HR.DEPARTMENTS',
        name_raw='DEPARTMENTS',
        name_canonical='departments',
        database_qualified_name='HR.DEPARTMENTS',
        summary='Department master table',
    )
    provenance = NestedProvenancePayload(
        sources=[_source()],
        edge_targets=[
            CatalogProvenanceEdgeTarget(
                edge_type='ForeignKeyTo',
                edge_key='FK::HR.EMPLOYEES->HR.DEPARTMENTS',
            )
        ],
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    _wire_batch_preflight(service)
    events = _install_batch_write_mocks(service, client)
    service._store.get_source_episode_by_uuid = AsyncMock(return_value=None)  # type: ignore[method-assign]

    async def _source_write(tx, *, params):
        _ = tx, params
        events.append('source_write')
        return {'uuid': params['uuid'], 'status': 'created'}

    async def _append(tx, *, edge_uuid, episode_uuid, group_id):
        _ = tx, group_id
        events.append('provenance_append')
        return {'uuid': edge_uuid, 'episodes': [episode_uuid]}

    service._store.upsert_source_episode = AsyncMock(side_effect=_source_write)  # type: ignore[method-assign]
    service._store.append_edge_episode = AsyncMock(side_effect=_append)  # type: ignore[method-assign]

    resp = await service.upsert_catalog_batch(
        client=client,
        request=_batch_request(
            entities=[employee, department],
            edges=[_edge()],
            provenance=provenance,
        ),
    )

    assert resp.status == 'committed'
    assert events.index('edge_write') < events.index('provenance_append')
    assert client.call_order.count('transaction') == 1


@pytest.mark.asyncio
async def test_mcp_tool_upsert_catalog_batch_registered():
    server = _mcp_server()
    assert hasattr(server, 'upsert_catalog_batch')
    assert callable(server.upsert_catalog_batch)


@pytest.mark.asyncio
async def test_mcp_registers_exactly_seven_catalog_tools_and_preserves_legacy_tools():
    server = _mcp_server()
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    registered_catalog = {name for name in names if name in CATALOG_TOOL_NAMES}

    assert registered_catalog == CATALOG_TOOL_NAMES
    assert LEGACY_TOOL_NAMES.issubset(names)
    assert len(names) == len(CATALOG_TOOL_NAMES | LEGACY_TOOL_NAMES) == 21

    schemas = {tool.name: tool.inputSchema for tool in tools if tool.name in CATALOG_TOOL_NAMES}
    assert schemas.keys() == CATALOG_TOOL_NAMES
    assert all(schema['type'] == 'object' for schema in schemas.values())


# ---------------------------------------------------------------------------
# CONT-07 / SAFE-08 production boundary + no-side-effect spies (01-04)
# ---------------------------------------------------------------------------


_FROZEN_CATALOG_TOOL_REQUEST_MODELS = {
    'upsert_typed_entities': UpsertTypedEntitiesRequest,
    'resolve_typed_entities': ResolveTypedEntitiesRequest,
    'verify_catalog_batch': VerifyCatalogBatchRequest,
    'upsert_typed_edges': UpsertTypedEdgesRequest,
    'upsert_provenance': None,  # filled at runtime
    'get_catalog_ingest_status': GetCatalogIngestStatusRequest,
    'upsert_catalog_batch': UpsertCatalogBatchRequest,
}


def _catalog_request_models():
    from models.catalog_provenance import UpsertProvenanceRequest

    mapping = dict(_FROZEN_CATALOG_TOOL_REQUEST_MODELS)
    mapping['upsert_provenance'] = UpsertProvenanceRequest
    return mapping


def _minimal_entity_dict():
    return {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'ORCL.HR.EMPLOYEES',
        'summary': 'Employee master table',
    }


def _minimal_edge_dict():
    return {
        'edge_type': 'Contains',
        'edge_key': 'CONTAINS::SCHEMA::FE::ORCL.HR->TABLE::FE::ORCL.HR.EMPLOYEES',
        'source_graph_key': 'SCHEMA::FE::ORCL.HR',
        'source_entity_type': 'Schema',
        'target_graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'target_entity_type': 'Table',
        'fact': 'Schema HR contains table EMPLOYEES',
    }


def _minimal_source_dict():
    return {
        'source_key': 'DOC::HR.PDF#p12',
        'reference_time': '2024-01-15T10:30:00+00:00',
    }


def _v2_request_payload(tool_name: str, **overrides):
    """Build a minimal valid nested payload for each frozen catalog tool."""
    base = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': GROUP,
        'batch_id': 'cont07-batch',
    }
    if tool_name == 'upsert_typed_entities':
        payload = {**base, 'entities': [_minimal_entity_dict()]}
    elif tool_name == 'resolve_typed_entities':
        payload = {
            **base,
            'entities': [
                {
                    'entity_type': 'Table',
                    'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                }
            ],
        }
        payload.pop('batch_id', None)
    elif tool_name == 'verify_catalog_batch':
        payload = {
            **base,
            'entities': [
                {
                    'entity_type': 'Table',
                    'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                }
            ],
        }
    elif tool_name == 'upsert_typed_edges':
        payload = {**base, 'edges': [_minimal_edge_dict()]}
    elif tool_name == 'upsert_provenance':
        payload = {**base, 'sources': [_minimal_source_dict()]}
    elif tool_name == 'get_catalog_ingest_status':
        payload = {'group_id': GROUP, 'batch_id': 'cont07-status'}
    elif tool_name == 'upsert_catalog_batch':
        payload = {**base, 'entities': [_minimal_entity_dict()]}
    else:
        raise AssertionError(f'unknown tool {tool_name}')
    payload.update(overrides)
    return payload


def _side_effect_spies(server):
    """Install spies on wrapper body globals and CatalogService methods."""
    store = MagicMock()
    store.upsert_entity_item = AsyncMock()
    store.ensure_schema = AsyncMock()
    embedder = MagicMock()
    embedder.create = AsyncMock(return_value=[0.1, 0.2])
    embedder.create_batch = AsyncMock(return_value=[[0.1]])
    client = MagicMock()
    client.embedder = embedder
    client.driver = MagicMock()
    client.driver.execute_query = AsyncMock()

    catalog_svc = MagicMock()
    for name in (
        'upsert_typed_entities',
        'resolve_typed_entities',
        'verify_catalog_batch',
        'upsert_typed_edges',
        'upsert_provenance',
        'get_catalog_ingest_status',
        'upsert_catalog_batch',
    ):
        setattr(catalog_svc, name, AsyncMock(return_value={'status': 'spy-should-not-run'}))

    graphiti_svc = MagicMock()
    graphiti_svc.get_client = AsyncMock(return_value=client)
    graphiti_svc.config = MagicMock()
    graphiti_svc.config.catalog_upsert = _enabled_config()

    server.graphiti_service = graphiti_svc
    server.catalog_service = catalog_svc
    if hasattr(server, 'queue_service'):
        server.queue_service = MagicMock()
        if hasattr(server.queue_service, 'add_episode'):
            server.queue_service.add_episode = AsyncMock()
    return {
        'catalog_service': catalog_svc,
        'graphiti_service': graphiti_svc,
        'client': client,
        'embedder': embedder,
        'store': store,
    }


def _assert_no_backend_side_effects(spies, body_entered: list):
    assert body_entered == [], f'tool body entered: {body_entered}'
    cs = spies['catalog_service']
    for name in (
        'upsert_typed_entities',
        'resolve_typed_entities',
        'verify_catalog_batch',
        'upsert_typed_edges',
        'upsert_provenance',
        'get_catalog_ingest_status',
        'upsert_catalog_batch',
    ):
        getattr(cs, name).assert_not_called()
    spies['graphiti_service'].get_client.assert_not_called()
    spies['embedder'].create.assert_not_called()
    spies['embedder'].create_batch.assert_not_called()


@pytest.mark.asyncio
async def test_catalog_tools_bind_typed_pydantic_request_models():
    """Production CONT-07: all seven tools bind typed Pydantic request models."""
    import typing

    server = _mcp_server()
    tools = await server.mcp.list_tools()
    by_name = {t.name: t for t in tools}
    models = _catalog_request_models()
    assert set(models) == CATALOG_TOOL_NAMES

    for name, expected_model in models.items():
        assert name in by_name, f'missing registered tool {name}'
        tool = server.mcp._tool_manager.get_tool(name)
        assert tool is not None
        field = tool.fn_metadata.arg_model.model_fields.get('request')
        assert field is not None, f'{name} missing request parameter'
        ann = field.annotation
        origin = typing.get_origin(ann)
        assert origin is None, f'{name} request annotation must not be bare container {ann}'
        assert ann is expected_model, f'{name} bound {ann}, expected {expected_model}'
        hints = typing.get_type_hints(tool.fn)
        assert hints.get('request') is expected_model
        schema = by_name[name].inputSchema
        assert schema.get('type') == 'object'
        props = schema.get('properties') or {}
        assert 'request' in props
        req_schema = props['request']
        assert '$ref' in req_schema or req_schema.get('additionalProperties') is False


@pytest.mark.asyncio
async def test_fastmcp_call_tool_rejects_invalid_nested_payloads_before_body_no_side_effect():
    """Production CONT-07: FastMCP call_tool validates before wrapper/service/backends."""
    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    spies = _side_effect_spies(server)

    cases = [
        (
            'upsert_typed_entities',
            {'identity_schema_version': 'catalog-v1'},
            'identity_schema_version',
        ),
        (
            'upsert_typed_entities',
            {'system_key': 'fe'},
            'system_key',
        ),
        (
            'upsert_typed_entities',
            {
                'entities': [
                    {
                        **_minimal_entity_dict(),
                        'graph_key': 'TABLE::ORCL.HR.EMPLOYEES',
                    }
                ]
            },
            'graph_key',
        ),
        (
            'upsert_typed_entities',
            {'atomic': False},
            'atomic',
        ),
        (
            'upsert_typed_entities',
            {'unknown_shell_field': True},
            'unknown_shell_field',
        ),
        (
            'resolve_typed_entities',
            {'identity_schema_version': 'catalog-v0'},
            'identity_schema_version',
        ),
        (
            'verify_catalog_batch',
            {'system_key': 'UNKNOWN'},
            'system_key',
        ),
        (
            'upsert_typed_edges',
            {'strict_endpoints': False},
            'strict_endpoints',
        ),
        (
            'upsert_provenance',
            {'sources': [{**_minimal_source_dict(), 'extra_bad': 1}]},
            'extra_bad',
        ),
        (
            'get_catalog_ingest_status',
            {'extra_status_field': 'nope'},
            'extra_status_field',
        ),
        (
            'upsert_catalog_batch',
            {'identity_schema_version': 'catalog-v1'},
            'identity_schema_version',
        ),
    ]

    for tool_name, overrides, _hint in cases:
        body_entered: list = []
        tool = server.mcp._tool_manager.get_tool(tool_name)
        original_fn = tool.fn

        async def wrapped_fn(request, _orig=original_fn, _entered=body_entered):
            _entered.append(request)
            return await _orig(request)

        tool.fn = wrapped_fn
        payload = _v2_request_payload(tool_name, **overrides)
        try:
            with pytest.raises(ToolError) as exc:
                await server.mcp.call_tool(tool_name, {'request': payload})
            err = exc.value
            # SAFE-08: structured ToolError, no ValidationError chain leak
            chain = err
            while chain is not None:
                assert not isinstance(chain, ValidationError), f'{tool_name} leaked ValidationError'
                chain = getattr(chain, '__cause__', None) or getattr(chain, '__context__', None)
            raw = str(err)
            assert 'Input should be' not in raw
            assert 'pydantic' not in raw.lower()
            js = raw.find('{')
            assert js >= 0, f'{tool_name}: missing structured JSON: {raw!r}'
            import json

            structured = json.loads(raw[js:])
            assert set(structured.keys()) == {
                'code',
                'message',
                'field_path',
                'retryable',
                'correlation_id',
            }
            assert structured['retryable'] is False
            _assert_no_backend_side_effects(spies, body_entered)
        finally:
            tool.fn = original_fn
            for name in (
                'upsert_typed_entities',
                'resolve_typed_entities',
                'verify_catalog_batch',
                'upsert_typed_edges',
                'upsert_provenance',
                'get_catalog_ingest_status',
                'upsert_catalog_batch',
            ):
                getattr(spies['catalog_service'], name).reset_mock()
            spies['graphiti_service'].get_client.reset_mock()
            spies['embedder'].create.reset_mock()
            spies['embedder'].create_batch.reset_mock()


def test_invalid_identity_schema_never_calls_service_store_or_embedder():
    """CONT-07: invalid identity_schema_version fails at model_validate; zero service entry."""
    service = CatalogService(catalog_config=_enabled_config())
    service._store = MagicMock()
    service._store.upsert_entity_item = AsyncMock()
    service._ensure_schema = AsyncMock()  # type: ignore[method-assign]
    client = MagicMock()
    client.embedder = MagicMock()
    client.embedder.create = AsyncMock()
    client.embedder.create_batch = AsyncMock()

    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate(
            _v2_request_payload(
                'upsert_typed_entities',
                identity_schema_version='catalog-v1',
            )
        )

    service._store.upsert_entity_item.assert_not_called()
    service._ensure_schema.assert_not_called()
    client.embedder.create.assert_not_called()
    client.embedder.create_batch.assert_not_called()


def test_invalid_system_key_never_calls_service():
    """CONT-07: invalid/unknown/lowercase system_key never reaches CatalogService."""
    service = CatalogService(catalog_config=_enabled_config())
    service.upsert_typed_entities = AsyncMock()  # type: ignore[method-assign]
    for bad in ('fe', 'Fe', 'UNKNOWN', '', None):
        with pytest.raises(ValidationError):
            UpsertTypedEntitiesRequest.model_validate(
                _v2_request_payload('upsert_typed_entities', system_key=bad)
            )
    service.upsert_typed_entities.assert_not_called()


def test_invalid_grammar_never_calls_service():
    """CONT-07: malformed/v1 graph keys fail validation before service."""
    service = CatalogService(catalog_config=_enabled_config())
    service.upsert_typed_entities = AsyncMock()  # type: ignore[method-assign]
    bad_keys = (
        'TABLE::ORCL.HR.EMPLOYEES',
        'table::fe::orcl.hr.employees',
        'TABLE::FE::',
        'NOTAPREFIX::FE::ORCL.HR.EMPLOYEES',
    )
    for key in bad_keys:
        with pytest.raises(ValidationError):
            UpsertTypedEntitiesRequest.model_validate(
                _v2_request_payload(
                    'upsert_typed_entities',
                    entities=[{**_minimal_entity_dict(), 'graph_key': key}],
                )
            )
    service.upsert_typed_entities.assert_not_called()


def test_no_side_effect_on_false_immutable_flags_and_unknown_nested_fields():
    """CONT-07 matrix: atomic/strict_endpoints false + unknown nested fields."""
    service = CatalogService(catalog_config=_enabled_config())
    service.upsert_typed_entities = AsyncMock()  # type: ignore[method-assign]
    service.upsert_typed_edges = AsyncMock()  # type: ignore[method-assign]
    service.upsert_catalog_batch = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate(
            _v2_request_payload('upsert_typed_entities', atomic=False)
        )
    with pytest.raises(ValidationError):
        UpsertTypedEdgesRequest.model_validate(
            _v2_request_payload('upsert_typed_edges', strict_endpoints=False)
        )
    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate(
            _v2_request_payload(
                'upsert_typed_entities',
                entities=[{**_minimal_entity_dict(), 'unknown_nested': 1}],
            )
        )
    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate(
            _v2_request_payload('upsert_typed_entities', entities=[])
        )

    service.upsert_typed_entities.assert_not_called()
    service.upsert_typed_edges.assert_not_called()
    service.upsert_catalog_batch.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('function_name', 'request_factory'),
    [
        ('resolve_typed_entities', _resolve_request),
        ('verify_catalog_batch', _verify_request),
        ('get_catalog_ingest_status', _status_request),
    ],
)
async def test_catalog_wrapper_failure_logs_omit_group_id_runtime(
    caplog: pytest.LogCaptureFixture,
    function_name: str,
    request_factory,
):
    server = _mcp_server()
    request = request_factory()
    failing_graphiti = SimpleNamespace(
        config=SimpleNamespace(catalog_upsert=_enabled_config()),
        get_client=AsyncMock(side_effect=RuntimeError('forced wrapper failure')),
    )

    with (
        patch.object(server, 'graphiti_service', failing_graphiti),
        patch.object(server, 'catalog_service', None),
        caplog.at_level(logging.ERROR),
    ):
        await getattr(server, function_name)(request)

    records = [record for record in caplog.records if function_name in record.getMessage()]
    _assert_group_id_absent(records)


@pytest.mark.asyncio
async def test_fastmcp_catalog_validation_returns_structured_safe_tool_error():
    """Production SAFE-08: catalog validation ToolError carries structured JSON only."""
    import json
    import re
    import uuid as uuid_mod

    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    spies = _side_effect_spies(server)
    secret = 'super-secret-token-xyz-DO-NOT-LEAK'
    body_entered: list = []
    tool = server.mcp._tool_manager.get_tool('upsert_typed_entities')
    original_fn = tool.fn

    async def wrapped_fn(request, _orig=original_fn, _entered=body_entered):
        _entered.append(request)
        return await _orig(request)

    tool.fn = wrapped_fn
    payload: dict = _v2_request_payload(
        'upsert_typed_entities',
        identity_schema_version='catalog-v1',
        password=secret,
        authorization=f'Bearer {secret}',
    )
    # also embed secret in a nested field that will be rejected as extra
    payload['entities'] = [{**_minimal_entity_dict(), 'secret_nested': secret}]
    try:
        with pytest.raises(ToolError) as exc:
            await server.mcp.call_tool('upsert_typed_entities', {'request': payload})
        err = exc.value
        # Fresh ToolError: no ValidationError in cause/context chain
        chain = err
        while chain is not None:
            assert not isinstance(chain, ValidationError), f'ValidationError leaked: {chain!r}'
            chain = getattr(chain, '__cause__', None) or getattr(chain, '__context__', None)
        raw = str(err)
        assert secret not in raw
        assert 'password' not in raw.lower() or 'password' not in raw  # no field dump
        assert 'Bearer' not in raw
        assert 'validation error' not in raw.lower() or 'Request validation' in raw
        assert 'pydantic' not in raw.lower()
        assert 'Traceback' not in raw
        assert 'Input should be' not in raw
        # Message is JSON structured error
        # ToolError may wrap as "Error executing..." or pure JSON; accept JSON object parse
        json_start = raw.find('{')
        assert json_start >= 0, f'no JSON in ToolError: {raw!r}'
        structured = json.loads(raw[json_start:])
        assert set(structured.keys()) == {
            'code',
            'message',
            'field_path',
            'retryable',
            'correlation_id',
        }
        assert structured['retryable'] is False
        assert isinstance(structured['message'], str)
        assert 0 < len(structured['message']) <= 512
        assert secret not in structured['message']
        assert 'catalog-v1' not in structured['message']
        # correlation_id is server UUID
        uuid_mod.UUID(structured['correlation_id'])
        # field_path sanitized dotted path or None
        fp = structured['field_path']
        if fp is not None:
            assert isinstance(fp, str)
            assert len(fp) <= 256
            assert re.fullmatch(r'[A-Za-z0-9_.\[\]]+', fp), fp
            assert secret not in fp
        # code is a known catalog error code string/value
        code = structured['code']
        code_val = code.value if hasattr(code, 'value') else str(code)
        assert code_val in {
            'unsupported_identity_schema',
            'invalid_system_key',
            'validation_error',
        }
        _assert_no_backend_side_effects(spies, body_entered)
    finally:
        tool.fn = original_fn


@pytest.mark.asyncio
async def test_fastmcp_unrelated_tool_error_not_rewritten_to_structured():
    """Arbitrary ToolError outside catalog validation must not be rewritten."""
    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    # Use a legacy tool path: force unknown tool → framework ToolError
    with pytest.raises(ToolError) as exc:
        await server.mcp.call_tool('definitely_not_a_real_tool', {'x': 1})
    raw = str(exc.value)
    assert 'Unknown tool' in raw or 'definitely_not_a_real_tool' in raw
    assert 'correlation_id' not in raw
    assert '"code"' not in raw


@pytest.mark.asyncio
async def test_fastmcp_legacy_tool_validation_not_structured_catalog_shape():
    """Legacy tools keep framework errors; no SAFE-08 catalog rewrite."""
    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    # get_status takes no request model; invalid args still ToolError without catalog shape
    # Prefer call_tool with bad args on a typed legacy path if any; else unknown is enough.
    # add_memory typically has many params — force type failure via wrong structure if registered.
    tools = await server.mcp.list_tools()
    legacy = [t for t in tools if t.name == 'get_status']
    assert legacy, 'get_status must remain registered'
    # get_status has empty/no required request; calling with extra junk may be ignored or error.
    # Inject a ToolError from tool body by temporarily replacing fn.
    tool = server.mcp._tool_manager.get_tool('get_status')
    original = tool.fn

    async def boom():
        raise RuntimeError('legacy-body-failure-secret-xyz')

    tool.fn = boom
    try:
        with pytest.raises(ToolError) as exc:
            await server.mcp.call_tool('get_status', {})
        raw = str(exc.value)
        # Must NOT be rewritten into catalog structured JSON
        if '{' in raw:
            import json

            try:
                obj = json.loads(raw[raw.find('{') :])
            except Exception:
                obj = None
            if isinstance(obj, dict):
                assert set(obj.keys()) != {
                    'code',
                    'message',
                    'field_path',
                    'retryable',
                    'correlation_id',
                }
        # legacy error text path remains framework-owned
        assert 'legacy-body-failure-secret-xyz' in raw or 'Error executing tool' in raw
    finally:
        tool.fn = original


@pytest.mark.asyncio
async def test_fastmcp_all_seven_catalog_tools_emit_structured_on_invalid():
    """All seven catalog tools surface SAFE-08 structured ToolError on invalid nested input."""
    import json
    import uuid as uuid_mod

    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    spies = _side_effect_spies(server)
    cases = [
        ('upsert_typed_entities', {'identity_schema_version': 'catalog-v1'}),
        ('resolve_typed_entities', {'identity_schema_version': 'catalog-v0'}),
        ('verify_catalog_batch', {'system_key': 'UNKNOWN'}),
        ('upsert_typed_edges', {'strict_endpoints': False}),
        ('upsert_provenance', {'sources': [{**_minimal_source_dict(), 'extra_bad': 1}]}),
        ('get_catalog_ingest_status', {'extra_status_field': 'nope'}),
        ('upsert_catalog_batch', {'identity_schema_version': 'catalog-v1'}),
    ]
    for tool_name, overrides in cases:
        body_entered: list = []
        tool = server.mcp._tool_manager.get_tool(tool_name)
        original_fn = tool.fn

        async def wrapped_fn(request, _orig=original_fn, _entered=body_entered):
            _entered.append(request)
            return await _orig(request)

        tool.fn = wrapped_fn
        payload = _v2_request_payload(tool_name, **overrides)
        try:
            with pytest.raises(ToolError) as exc:
                await server.mcp.call_tool(tool_name, {'request': payload})
            raw = str(exc.value)
            assert 'Input should be' not in raw
            assert 'pydantic' not in raw.lower()
            js = raw.find('{')
            assert js >= 0, f'{tool_name}: {raw!r}'
            structured = json.loads(raw[js:])
            assert set(structured.keys()) == {
                'code',
                'message',
                'field_path',
                'retryable',
                'correlation_id',
            }
            uuid_mod.UUID(structured['correlation_id'])
            assert structured['retryable'] is False
            assert len(structured['message']) <= 512
            _assert_no_backend_side_effects(spies, body_entered)
        finally:
            tool.fn = original_fn
            for name in (
                'upsert_typed_entities',
                'resolve_typed_entities',
                'verify_catalog_batch',
                'upsert_typed_edges',
                'upsert_provenance',
                'get_catalog_ingest_status',
                'upsert_catalog_batch',
            ):
                getattr(spies['catalog_service'], name).reset_mock()
            spies['graphiti_service'].get_client.reset_mock()
            spies['embedder'].create.reset_mock()
            spies['embedder'].create_batch.reset_mock()


# ---------------------------------------------------------------------------
# Plan 01-06 contract gap coverage
# ---------------------------------------------------------------------------


def test_source_ref_canonical_payload_contains_plain_json_dicts():
    from models import catalog_entities

    source_ref_model = getattr(catalog_entities, 'CatalogSourceRef', None)
    assert source_ref_model is not None, 'CatalogSourceRef missing'
    raw_text = 'DDL  \n'
    item = _entity(
        source_refs=[
            source_ref_model(document_id='ddl.sql', page=12, raw_text=raw_text),
            source_ref_model(page=1, raw_text=''),
        ]
    )

    payload = CatalogService.entity_canonical_payload(item)

    assert payload['source_refs'] == [
        {'document_id': 'ddl.sql', 'page': 12, 'raw_text': raw_text},
        {'document_id': None, 'page': 1, 'raw_text': ''},
    ]
    assert all(isinstance(ref, dict) for ref in payload['source_refs'])
    import json

    assert json.loads(json.dumps(payload))['source_refs'][0]['raw_text'] == raw_text
    assert canonical_sha256(payload) == canonical_sha256(payload)


def _fastmcp_graph_key_mismatch_cases():
    entity_bo = {**_minimal_entity_dict(), 'graph_key': 'TABLE::BO::ORCL.HR.EMPLOYEES'}
    edge_source_bo = {**_minimal_edge_dict(), 'source_graph_key': 'SCHEMA::BO::ORCL.HR'}
    edge_target_bo = {
        **_minimal_edge_dict(),
        'target_graph_key': 'TABLE::BO::ORCL.HR.EMPLOYEES',
    }
    provenance_target_bo = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::BO::ORCL.HR.EMPLOYEES',
    }
    return [
        ('upsert_typed_entities', {'entities': [entity_bo]}, 'entities.0.graph_key'),
        (
            'resolve_typed_entities',
            {
                'entities': [
                    {
                        'entity_type': 'Table',
                        'graph_key': 'TABLE::BO::ORCL.HR.EMPLOYEES',
                    }
                ]
            },
            'entities.0.graph_key',
        ),
        (
            'verify_catalog_batch',
            {'entities': [provenance_target_bo]},
            'entities.0.graph_key',
        ),
        (
            'upsert_typed_edges',
            {'edges': [edge_source_bo]},
            'edges.0.source_graph_key',
        ),
        (
            'upsert_typed_edges',
            {'edges': [edge_target_bo]},
            'edges.0.target_graph_key',
        ),
        (
            'upsert_provenance',
            {'entity_targets': [provenance_target_bo]},
            'entity_targets.0.graph_key',
        ),
        (
            'upsert_catalog_batch',
            {'entities': [entity_bo]},
            'entities.0.graph_key',
        ),
        (
            'upsert_catalog_batch',
            {'entities': [], 'edges': [edge_source_bo]},
            'edges.0.source_graph_key',
        ),
        (
            'upsert_catalog_batch',
            {'entities': [], 'edges': [edge_target_bo]},
            'edges.0.target_graph_key',
        ),
        (
            'upsert_catalog_batch',
            {
                'entities': [],
                'provenance': {
                    'sources': [_minimal_source_dict()],
                    'entity_targets': [provenance_target_bo],
                },
            },
            'provenance.entity_targets.0.graph_key',
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('tool_name', 'overrides', 'expected_path'), _fastmcp_graph_key_mismatch_cases()
)
async def test_fastmcp_graph_key_mismatch_reports_exact_path_before_side_effects(
    tool_name, overrides, expected_path
):
    import json

    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    spies = _side_effect_spies(server)
    body_entered: list = []
    tool = server.mcp._tool_manager.get_tool(tool_name)
    original_fn = tool.fn

    async def wrapped_fn(request, _orig=original_fn, _entered=body_entered):
        _entered.append(request)
        return await _orig(request)

    tool.fn = wrapped_fn
    try:
        with pytest.raises(ToolError) as exc:
            await server.mcp.call_tool(
                tool_name,
                {'request': _v2_request_payload(tool_name, **overrides)},
            )
        raw = str(exc.value)
        structured = json.loads(raw[raw.find('{') :])
        assert structured['code'] == 'invalid_system_key'
        assert structured['field_path'] == expected_path
        _assert_no_backend_side_effects(spies, body_entered)
    finally:
        tool.fn = original_fn


@pytest.mark.asyncio
@pytest.mark.parametrize('entities_override', [[], pytest.param(None, id='missing')])
async def test_fastmcp_empty_resolve_rejected_before_service(entities_override):
    import json

    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    spies = _side_effect_spies(server)
    body_entered: list = []
    tool = server.mcp._tool_manager.get_tool('resolve_typed_entities')
    original_fn = tool.fn

    async def wrapped_fn(request, _orig=original_fn, _entered=body_entered):
        _entered.append(request)
        return await _orig(request)

    tool.fn = wrapped_fn
    payload = _v2_request_payload('resolve_typed_entities')
    if entities_override is None:
        payload.pop('entities')
    else:
        payload['entities'] = entities_override
    try:
        with pytest.raises(ToolError) as exc:
            await server.mcp.call_tool('resolve_typed_entities', {'request': payload})
        raw = str(exc.value)
        structured = json.loads(raw[raw.find('{') :])
        assert structured['code'] == 'validation_error'
        assert structured['field_path'] == 'entities'
        _assert_no_backend_side_effects(spies, body_entered)
    finally:
        tool.fn = original_fn


# ---------------------------------------------------------------------------
# Plan 01-09 gap coverage: CR-02 / WR-01 FastMCP protocol
# ---------------------------------------------------------------------------


def _assert_safe_tool_error_payload(err, *, expected_field_path: str, sentinel: str):
    import json

    from pydantic import ValidationError

    chain = err
    while chain is not None:
        assert not isinstance(chain, ValidationError), 'ValidationError leaked into protocol chain'
        chain = getattr(chain, '__cause__', None) or getattr(chain, '__context__', None)
    raw = str(err)
    assert sentinel not in raw
    assert 'fromisoformat' not in raw.lower()
    assert 'Invalid isoformat' not in raw
    assert 'pydantic' not in raw.lower()
    assert 'Traceback' not in raw
    js = raw.find('{')
    assert js >= 0, f'missing structured JSON: {raw!r}'
    structured = json.loads(raw[js:])
    assert set(structured.keys()) == {
        'code',
        'message',
        'field_path',
        'retryable',
        'correlation_id',
    }
    assert structured['code'] == 'validation_error'
    assert structured['field_path'] == expected_field_path
    assert structured['retryable'] is False
    assert isinstance(structured['correlation_id'], str) and structured['correlation_id']
    assert sentinel not in structured['message']
    assert 'fromisoformat' not in structured['message'].lower()
    return structured


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('tool_name', 'overrides', 'expected_path', 'sentinel'),
    [
        (
            'upsert_provenance',
            {
                'sources': [
                    {
                        **_minimal_source_dict(),
                        'reference_time': 'CR02-TS-SENTINEL-not-iso',
                    }
                ]
            },
            'sources.0.reference_time',
            'CR02-TS-SENTINEL-not-iso',
        ),
        (
            'upsert_catalog_batch',
            {
                'entities': [],
                'provenance': {
                    'sources': [
                        {
                            **_minimal_source_dict(),
                            'reference_time': 'CR02-TS-SENTINEL-batch',
                        }
                    ]
                },
            },
            'provenance.sources.0.reference_time',
            'CR02-TS-SENTINEL-batch',
        ),
    ],
)
async def test_gap_cr02_fastmcp_malformed_reference_time_no_leak_no_side_effect(
    tool_name, overrides, expected_path, sentinel
):
    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    spies = _side_effect_spies(server)
    body_entered: list = []
    tool = server.mcp._tool_manager.get_tool(tool_name)
    original_fn = tool.fn

    async def wrapped_fn(request, _orig=original_fn, _entered=body_entered):
        _entered.append(request)
        return await _orig(request)

    tool.fn = wrapped_fn
    try:
        with pytest.raises(ToolError) as exc:
            await server.mcp.call_tool(
                tool_name,
                {'request': _v2_request_payload(tool_name, **overrides)},
            )
        _assert_safe_tool_error_payload(
            exc.value, expected_field_path=expected_path, sentinel=sentinel
        )
        _assert_no_backend_side_effects(spies, body_entered)
    finally:
        tool.fn = original_fn


def _gap_wr01_fastmcp_malformed_cases():
    bad = 'TABLE::ORCL.HR.EMPLOYEES'
    bad_entity = {**_minimal_entity_dict(), 'graph_key': bad}
    bad_edge_source = {
        **_minimal_edge_dict(),
        'source_graph_key': bad,
        'source_entity_type': 'Table',
    }
    bad_edge_target = {
        **_minimal_edge_dict(),
        'target_graph_key': bad,
        'target_entity_type': 'Table',
    }
    bad_target = {'entity_type': 'Table', 'graph_key': bad}
    return [
        ('upsert_typed_entities', {'entities': [bad_entity]}, 'entities.0.graph_key', bad),
        (
            'resolve_typed_entities',
            {'entities': [{'entity_type': 'Table', 'graph_key': bad}]},
            'entities.0.graph_key',
            bad,
        ),
        (
            'verify_catalog_batch',
            {'entities': [bad_target]},
            'entities.0.graph_key',
            bad,
        ),
        (
            'upsert_typed_edges',
            {'edges': [bad_edge_source]},
            'edges.0.source_graph_key',
            bad,
        ),
        (
            'upsert_typed_edges',
            {'edges': [bad_edge_target]},
            'edges.0.target_graph_key',
            bad,
        ),
        (
            'upsert_provenance',
            {'entity_targets': [bad_target]},
            'entity_targets.0.graph_key',
            bad,
        ),
        (
            'upsert_catalog_batch',
            {'entities': [bad_entity]},
            'entities.0.graph_key',
            bad,
        ),
        (
            'upsert_catalog_batch',
            {'entities': [], 'edges': [bad_edge_source]},
            'edges.0.source_graph_key',
            bad,
        ),
        (
            'upsert_catalog_batch',
            {'entities': [], 'edges': [bad_edge_target]},
            'edges.0.target_graph_key',
            bad,
        ),
        (
            'upsert_catalog_batch',
            {
                'entities': [],
                'provenance': {
                    'sources': [_minimal_source_dict()],
                    'entity_targets': [bad_target],
                },
            },
            'provenance.entity_targets.0.graph_key',
            bad,
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('tool_name', 'overrides', 'expected_path', 'sentinel'),
    _gap_wr01_fastmcp_malformed_cases(),
)
async def test_gap_wr01_fastmcp_malformed_graph_key_exact_path_no_side_effect(
    tool_name, overrides, expected_path, sentinel
):
    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    spies = _side_effect_spies(server)
    body_entered: list = []
    tool = server.mcp._tool_manager.get_tool(tool_name)
    original_fn = tool.fn

    async def wrapped_fn(request, _orig=original_fn, _entered=body_entered):
        _entered.append(request)
        return await _orig(request)

    tool.fn = wrapped_fn
    try:
        with pytest.raises(ToolError) as exc:
            await server.mcp.call_tool(
                tool_name,
                {'request': _v2_request_payload(tool_name, **overrides)},
            )
        structured = _assert_safe_tool_error_payload(
            exc.value, expected_field_path=expected_path, sentinel=sentinel
        )
        assert structured['code'] == 'validation_error'
        _assert_no_backend_side_effects(spies, body_entered)
    finally:
        tool.fn = original_fn


@pytest.mark.asyncio
async def test_gap_wr01_fastmcp_shell_mismatch_keeps_invalid_system_key():
    import json

    from mcp.server.fastmcp.exceptions import ToolError

    server = _mcp_server()
    spies = _side_effect_spies(server)
    body_entered: list = []
    tool = server.mcp._tool_manager.get_tool('upsert_typed_entities')
    original_fn = tool.fn

    async def wrapped_fn(request, _orig=original_fn, _entered=body_entered):
        _entered.append(request)
        return await _orig(request)

    tool.fn = wrapped_fn
    payload = _v2_request_payload(
        'upsert_typed_entities',
        system_key='BO',
        entities=[
            {
                **_minimal_entity_dict(),
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
            }
        ],
    )
    try:
        with pytest.raises(ToolError) as exc:
            await server.mcp.call_tool('upsert_typed_entities', {'request': payload})
        raw = str(exc.value)
        structured = json.loads(raw[raw.find('{') :])
        assert structured['code'] == 'invalid_system_key'
        assert structured['field_path'] == 'entities.0.graph_key'
        assert 'TABLE::FE::ORCL.HR.EMPLOYEES' not in structured['message']
        _assert_no_backend_side_effects(spies, body_entered)
    finally:
        tool.fn = original_fn


# ---------------------------------------------------------------------------
# gap_cr01: barrier-driven entity race across three write routes
# ---------------------------------------------------------------------------


class _RaceEntityStore:
    """Event/barrier-driven fake store for concurrent conflicting-name entity races."""

    def __init__(self, *, loser_name_raw: str | None = None) -> None:
        self.entities: dict[tuple[str, str], dict[str, Any]] = {}
        self.checkpoints: list[str] = []
        self._lock = asyncio.Lock()
        self._pre_reads_done = 0
        self._both_pre_read = asyncio.Event()
        self._loser_at_merge = asyncio.Event()
        self._winner_committed = asyncio.Event()
        self.loser_name_raw = loser_name_raw
        self.upsert_calls = 0
        self.batch_status_writes: list[dict[str, Any]] = []

    async def ensure_uuid_uniqueness_constraints(self, driver: Any) -> None:
        _ = driver
        return None

    async def get_entity_by_uuid(
        self,
        executor: Any,
        *,
        uuid: str,
        group_id: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        _ = executor
        if tx is None:
            row = self.entities.get((uuid, group_id))
            self.checkpoints.append(f'pre_read:{"hit" if row else "miss"}:{uuid[:8]}')
            self._pre_reads_done += 1
            if self._pre_reads_done >= 2:
                self._both_pre_read.set()
            # Concurrent race: both pre-reads observe absence before either commits.
            if self.loser_name_raw is not None:
                await self._both_pre_read.wait()
                return None
            return None if row is None else dict(row)
        row = self.entities.get((uuid, group_id))
        self.checkpoints.append(f'in_tx_recheck:{"hit" if row else "miss"}:{uuid[:8]}')
        return None if row is None else dict(row)

    def prepare_entity_params(self, **kwargs: Any) -> dict[str, Any]:
        from services.catalog_store import CatalogNeo4jStore

        return CatalogNeo4jStore().prepare_entity_params(**kwargs)

    def resolve_entity_label(self, entity_type: str) -> str:
        from services.catalog_store import CatalogNeo4jStore

        return CatalogNeo4jStore().resolve_entity_label(entity_type)

    def _conflict_row(self, existing: dict[str, Any]) -> dict[str, Any]:
        return {
            'uuid': existing['uuid'],
            'status': 'error',
            'error_code': CatalogErrorCode.deterministic_uuid_conflict.value,
            'name': existing['name'],
            'graph_key': existing['graph_key'],
            'name_raw': existing['name_raw'],
            'name_canonical': existing['name_canonical'],
            'labels': existing['labels'],
            'neo4j_labels': existing['neo4j_labels'],
            'content_sha256': existing['content_sha256'],
            'summary': existing['summary'],
            'batch_id': existing['batch_id'],
            'created_at': existing['created_at'],
            'updated_at': existing['updated_at'],
            'has_name_embedding': True,
        }

    def _identity_conflict(self, existing: dict[str, Any], params: dict[str, Any]) -> bool:
        return any(
            existing.get(field) != params.get(field)
            for field in ('name', 'graph_key', 'name_raw', 'name_canonical')
        )

    async def upsert_entity_item(
        self,
        tx: Any,
        *,
        entity_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        _ = tx, entity_type
        self.upsert_calls += 1
        key = (params['uuid'], params['group_id'])
        self.checkpoints.append(f'merge_enter:{params["name_raw"]}')

        # Loser reaches MERGE and blocks until winner commits (real checkpoint order).
        if self.loser_name_raw is not None and params['name_raw'] == self.loser_name_raw:
            self._loser_at_merge.set()
            self.checkpoints.append(f'merge_block:{params["name_raw"]}')
            await self._winner_committed.wait()

        async with self._lock:
            existing = self.entities.get(key)
            if existing is not None:
                if self._identity_conflict(existing, params):
                    self.checkpoints.append(f'merge_conflict:{params["name_raw"]}')
                    return self._conflict_row(existing)
                self.checkpoints.append(f'merge_unchanged:{params["name_raw"]}')
                return {
                    'uuid': existing['uuid'],
                    'status': 'unchanged',
                    'error_code': None,
                    'name': existing['name'],
                    'graph_key': existing['graph_key'],
                    'name_raw': existing['name_raw'],
                    'name_canonical': existing['name_canonical'],
                    'labels': existing['labels'],
                    'neo4j_labels': existing['neo4j_labels'],
                    'content_sha256': existing['content_sha256'],
                    'summary': existing['summary'],
                    'batch_id': existing['batch_id'],
                    'created_at': existing['created_at'],
                    'updated_at': existing['updated_at'],
                    'has_name_embedding': True,
                }

            # Winner may wait until loser is parked at MERGE.
            if (
                self.loser_name_raw is not None
                and params['name_raw'] != self.loser_name_raw
                and not self._winner_committed.is_set()
            ):
                await self._loser_at_merge.wait()

            created = {
                'uuid': params['uuid'],
                'group_id': params['group_id'],
                'name': params['name'],
                'graph_key': params['graph_key'],
                'name_raw': params['name_raw'],
                'name_canonical': params['name_canonical'],
                'labels': params['labels'],
                'neo4j_labels': list(params['labels']),
                'content_sha256': params['content_sha256'],
                'summary': params['summary'],
                'batch_id': params['batch_id'],
                'created_at': params['created_at'],
                'updated_at': params['updated_at'],
                'attributes': params.get('attributes'),
                'has_name_embedding': True,
            }
            self.entities[key] = created
            self.checkpoints.append(f'merge_commit:{params["name_raw"]}')
            self._winner_committed.set()
            return {
                'uuid': created['uuid'],
                'status': 'created',
                'error_code': None,
                'name': created['name'],
                'graph_key': created['graph_key'],
                'name_raw': created['name_raw'],
                'name_canonical': created['name_canonical'],
                'labels': created['labels'],
                'neo4j_labels': created['neo4j_labels'],
                'content_sha256': created['content_sha256'],
                'summary': created['summary'],
                'batch_id': created['batch_id'],
                'created_at': created['created_at'],
                'updated_at': created['updated_at'],
                'has_name_embedding': True,
            }

    def prepare_batch_status_params(self, **kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    async def claim_batch_status(self, tx: Any, *, params: dict[str, Any]) -> dict[str, Any]:
        _ = tx
        return {
            'uuid': params['uuid'],
            'status': 'running',
            'request_sha256': params['request_sha256'],
        }

    async def upsert_batch_status(self, tx: Any, *, params: dict[str, Any]) -> dict[str, Any]:
        _ = tx
        self.batch_status_writes.append(dict(params))
        self.checkpoints.append(f'batch_status:{params.get("status")}')
        return dict(params)

    async def get_batch_status(
        self,
        executor: Any,
        *,
        uuid: str,
        group_id: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        _ = executor, uuid, group_id, tx
        return None

    async def get_edge_by_uuid(self, *args: Any, **kwargs: Any) -> None:
        _ = args, kwargs
        return None

    async def upsert_edge_item(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = args, kwargs
        raise AssertionError('edge write not expected in entity race tests')

    async def upsert_source_episode(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = args, kwargs
        raise AssertionError('source write not expected in entity race tests')


@pytest.mark.asyncio
async def test_gap_cr01_write_status_from_row_error_never_falls_back_to_updated():
    row = {
        'status': 'error',
        'error_code': CatalogErrorCode.deterministic_uuid_conflict.value,
        'uuid': 'u',
    }
    status = CatalogService._write_status_from_row(row, 'created')
    assert status != 'updated'
    assert status != 'created'


@pytest.mark.asyncio
async def test_gap_cr01_atomic_route_race_rolls_back_typed_conflict():
    winner = _entity(
        graph_key='TABLE::FE::ORCL.HR.RACE',
        name_raw='RACE_WIN',
        name_canonical='race_win',
        summary='winner',
        database_qualified_name='ORCL.HR.RACE',
    )
    loser = _entity(
        graph_key='TABLE::FE::ORCL.HR.RACE',
        name_raw='RACE_LOSE',
        name_canonical='race_lose',
        summary='loser',
        database_qualified_name='ORCL.HR.RACE',
    )
    store = _RaceEntityStore(loser_name_raw=loser.name_raw)
    client_a = _make_client()
    client_b = _make_client()
    service_a = CatalogService(catalog_config=_enabled_config())
    service_b = CatalogService(catalog_config=_enabled_config())
    service_a._store = store  # type: ignore[method-assign]
    service_b._store = store  # type: ignore[method-assign]
    service_a._ensure_schema = AsyncMock()  # type: ignore[method-assign]
    service_b._ensure_schema = AsyncMock()  # type: ignore[method-assign]

    req_a = _request([winner], batch_id='race-a')
    req_b = _request([loser], batch_id='race-b')
    task_a = asyncio.create_task(service_a.upsert_typed_entities(client=client_a, request=req_a))
    task_b = asyncio.create_task(service_b.upsert_typed_entities(client=client_b, request=req_b))
    await store._both_pre_read.wait()
    # Loser remains pending at MERGE until winner commits.
    await store._loser_at_merge.wait()
    assert not task_b.done() or not task_a.done()
    results = await asyncio.gather(task_a, task_b)
    statuses = [r.results[0].status for r in results]
    codes = [r.results[0].error_code for r in results]
    success = [s for s in statuses if s in ('created', 'updated', 'unchanged')]
    assert len(success) == 1
    assert any(c == CatalogErrorCode.deterministic_uuid_conflict for c in codes)
    assert all(c != CatalogErrorCode.neo4j_transaction_failed for c in codes if c is not None)
    assert len(store.entities) == 1
    stored = next(iter(store.entities.values()))
    if stored['name_raw'] == winner.name_raw:
        assert stored['name_canonical'] == winner.name_canonical
        assert stored['summary'] == winner.summary
    else:
        assert stored['name_canonical'] == loser.name_canonical
        assert stored['summary'] == loser.summary
    assert any(cp.startswith('merge_commit:') for cp in store.checkpoints)


@pytest.mark.asyncio
async def test_gap_cr01_per_item_route_returns_exact_conflict_not_tx_failed():
    from datetime import datetime, timezone

    from services.catalog_service import _PreparedEntity

    loser = _entity(
        graph_key='TABLE::FE::ORCL.HR.RACE2',
        name_raw='L',
        name_canonical='l',
        summary='loser',
        database_qualified_name='ORCL.HR.RACE2',
    )
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._ensure_schema = AsyncMock()  # type: ignore[method-assign]
    service._store.get_entity_by_uuid = AsyncMock(return_value=None)
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, loser.entity_type, loser.graph_key)
    service._store.upsert_entity_item = AsyncMock(
        return_value={
            'uuid': ent_uuid,
            'status': 'error',
            'error_code': CatalogErrorCode.deterministic_uuid_conflict.value,
            'name': 'TABLE::FE::ORCL.HR.RACE2',
            'graph_key': 'TABLE::FE::ORCL.HR.RACE2',
            'name_raw': 'W',
            'name_canonical': 'w',
            'content_sha256': 'a' * 64,
            'summary': 'winner',
            'has_name_embedding': True,
        }
    )
    prep = _PreparedEntity(
        index=0,
        item=loser,
        entity_uuid=ent_uuid,
        content_sha256=canonical_sha256(service.entity_canonical_payload(loser)),
        projected_status='created',
        name_embedding=[0.1, 0.2, 0.3],
    )
    req = _request([loser], batch_id='l1')
    resp = await service._write_per_item(
        client,
        req,
        [prep],
        {},
        datetime.now(timezone.utc),
    )
    assert resp.results[0].status == 'error'
    assert resp.results[0].error_code == CatalogErrorCode.deterministic_uuid_conflict
    assert resp.results[0].error_code != CatalogErrorCode.neo4j_transaction_failed


@pytest.mark.asyncio
async def test_gap_cr01_combined_batch_rolls_back_and_returns_typed_conflict():
    winner = _entity(
        graph_key='TABLE::FE::ORCL.HR.RACE3',
        name_raw='W',
        name_canonical='w',
        summary='winner',
        database_qualified_name='ORCL.HR.RACE3',
    )
    loser = _entity(
        graph_key='TABLE::FE::ORCL.HR.RACE3',
        name_raw='L',
        name_canonical='l',
        summary='loser',
        database_qualified_name='ORCL.HR.RACE3',
    )
    store = _RaceEntityStore()
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store = store  # type: ignore[method-assign]
    service._ensure_schema = AsyncMock()  # type: ignore[method-assign]

    # Seed winner under lock so batch loser hits MERGE conflict row, not preflight only.
    await service.upsert_typed_entities(client=client, request=_request([winner], batch_id='seed'))
    store.batch_status_writes.clear()
    # Force batch pre-read to treat entity as absent so write path reaches MERGE.
    original_get = store.get_entity_by_uuid

    async def _absent_pre_read(executor, *, uuid, group_id, tx=None):
        if tx is None:
            return None
        return await original_get(executor, uuid=uuid, group_id=group_id, tx=tx)

    store.get_entity_by_uuid = _absent_pre_read  # type: ignore[method-assign]

    batch_req = UpsertCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id='batch-race',
        entities=[loser],
    )
    resp = await service.upsert_catalog_batch(client=client, request=batch_req)
    assert resp.status == 'failed'
    assert resp.error_code == CatalogErrorCode.deterministic_uuid_conflict
    assert resp.error_code != CatalogErrorCode.neo4j_transaction_failed
    assert any(w.get('status') == 'failed' for w in store.batch_status_writes)
    stored = next(iter(store.entities.values()))
    assert stored['name_raw'] == winner.name_raw
    assert stored['summary'] == winner.summary
