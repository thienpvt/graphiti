#!/usr/bin/env python3
"""Unit tests for the direct entity update MCP tool."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphiti_core.driver.driver import GraphProvider
from graphiti_core.errors import NodeNotFoundError
from graphiti_core.nodes import EntityNode

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import graphiti_mcp_server as server  # noqa: E402


@pytest.fixture
def entity() -> EntityNode:
    return EntityNode(
        uuid='entity-1',
        name='Alice',
        name_embedding=[0.1, 0.2],
        group_id='main',
        labels=['Person'],
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        summary='Original summary',
        attributes={'role': 'Engineer', 'team': 'Platform'},
    )


@pytest.fixture
def client() -> SimpleNamespace:
    return SimpleNamespace(
        driver=SimpleNamespace(
            provider=GraphProvider.NEO4J,
            graph_operations_interface=None,
            execute_query=AsyncMock(),
            transaction=MagicMock(),
            entity_node_ops=None,
        ),
        embedder=object(),
    )


@pytest.fixture
def service(client: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(get_client=AsyncMock(return_value=client))


@pytest.fixture
def install_service(monkeypatch: pytest.MonkeyPatch, service: SimpleNamespace):
    monkeypatch.setattr(server, 'graphiti_service', service)
    return service


async def test_update_entity_requires_initialized_service(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server, 'graphiti_service', None)

    result = await server.update_entity('entity-1', summary='Updated')

    assert result == {'error': 'Graphiti service not initialized'}


async def test_update_entity_rejects_empty_patch_before_database_access(install_service):
    result = await server.update_entity('entity-1')

    assert result == {'error': 'At least one entity field must be provided'}
    install_service.get_client.assert_not_awaited()


async def test_update_entity_returns_error_when_entity_is_missing(install_service, client):
    with patch.object(
        server.EntityNode,
        'get_by_uuid',
        AsyncMock(side_effect=NodeNotFoundError('missing')),
    ):
        result = await server.update_entity('missing', summary='Updated')

    assert result == {'error': 'Entity with UUID missing not found'}


async def test_update_entity_replaces_summary_without_regenerating_embedding(
    install_service, client, entity
):
    original_name = entity.name
    original_attributes = entity.attributes.copy()
    original_labels = entity.labels.copy()

    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'generate_name_embedding', AsyncMock()) as generate_embedding,
        patch.object(server.EntityNode, 'save', AsyncMock()) as save,
    ):
        result = await server.update_entity(entity.uuid, summary='Updated summary')

    assert entity.name == original_name
    assert entity.summary == 'Updated summary'
    assert entity.attributes == original_attributes
    assert entity.labels == original_labels
    generate_embedding.assert_not_awaited()
    save.assert_awaited_once_with(client.driver)
    assert result == {
        'uuid': 'entity-1',
        'name': 'Alice',
        'labels': ['Person'],
        'created_at': '2025-01-01T00:00:00+00:00',
        'summary': 'Updated summary',
        'group_id': 'main',
        'attributes': {'role': 'Engineer', 'team': 'Platform'},
    }
    assert 'name_embedding' not in result


async def test_update_entity_loads_missing_embedding_before_non_rename_save(
    install_service, client, entity
):
    entity.name_embedding = None

    operations: list[str] = []
    load_embedding = AsyncMock(side_effect=lambda _driver: operations.append('load'))
    save = AsyncMock(side_effect=lambda _driver: operations.append('save'))

    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'load_name_embedding', load_embedding),
        patch.object(server.EntityNode, 'save', save),
    ):
        await server.update_entity(entity.uuid, summary='Updated')

    load_embedding.assert_awaited_once_with(client.driver)
    assert operations == ['load', 'save']


async def test_update_entity_renames_missing_embedding_without_loading_old_one(
    install_service, client, entity
):
    entity.name_embedding = None

    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'load_name_embedding', AsyncMock()) as load_embedding,
        patch.object(server.EntityNode, 'generate_name_embedding', AsyncMock()) as generate_embedding,
        patch.object(server.EntityNode, 'save', AsyncMock()),
    ):
        await server.update_entity(entity.uuid, name='Alicia')

    load_embedding.assert_not_awaited()
    generate_embedding.assert_awaited_once_with(client.embedder)


async def test_update_entity_clears_summary(install_service, client, entity):
    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'save', AsyncMock()),
    ):
        result = await server.update_entity(entity.uuid, summary='')

    assert entity.summary == ''
    assert result['summary'] == ''


async def test_update_entity_renames_and_regenerates_embedding(install_service, client, entity):
    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'generate_name_embedding', AsyncMock()) as generate_embedding,
        patch.object(server.EntityNode, 'save', AsyncMock()) as save,
    ):
        result = await server.update_entity(entity.uuid, name='  Alicia  ')

    assert entity.name == 'Alicia'
    generate_embedding.assert_awaited_once_with(client.embedder)
    save.assert_awaited_once_with(client.driver)
    assert result['name'] == 'Alicia'


async def test_update_entity_skips_embedding_when_trimmed_name_is_unchanged(
    install_service, client, entity
):
    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'generate_name_embedding', AsyncMock()) as generate_embedding,
        patch.object(server.EntityNode, 'save', AsyncMock()),
    ):
        await server.update_entity(entity.uuid, name=' Alice ')

    generate_embedding.assert_not_awaited()


@pytest.mark.parametrize('name', ['', '   ', '\n\t'])
async def test_update_entity_rejects_blank_name(install_service, client, entity, name):
    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'save', AsyncMock()) as save,
    ):
        result = await server.update_entity(entity.uuid, name=name)

    assert result == {'error': 'Entity name must not be blank'}
    save.assert_not_awaited()


async def test_update_entity_merges_attributes(install_service, client, entity):
    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'save', AsyncMock()),
    ):
        result = await server.update_entity(
            entity.uuid,
            summary='Updated',
            attributes={'role': 'Architect', 'active': True},
        )

    assert entity.attributes == {'role': 'Architect', 'team': 'Platform', 'active': True}
    assert result['attributes'] == entity.attributes


async def test_update_entity_accepts_empty_attribute_merge_with_other_patch(
    install_service, client, entity
):
    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'save', AsyncMock()),
    ):
        await server.update_entity(entity.uuid, summary='Updated', attributes={})

    assert entity.attributes == {'role': 'Engineer', 'team': 'Platform'}


@pytest.mark.parametrize('key', ['uuid', 'group_id', 'name_embedding', 'customEmbedding'])
async def test_update_entity_rejects_protected_attribute_keys(
    install_service, client, entity, key
):
    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'save', AsyncMock()) as save,
    ):
        result = await server.update_entity(entity.uuid, attributes={key: 'unsafe'})

    assert 'reserved or embedding attribute keys' in result['error'].lower()
    assert key in result['error']
    save.assert_not_awaited()


@pytest.mark.parametrize(
    ('labels', 'expected'),
    [
        (['Person', 'Person', 'Organization'], ['Person', 'Organization']),
        (['Entity', 'Person'], ['Person']),
        ([], []),
    ],
)
async def test_update_entity_replaces_labels_atomically(
    install_service, client, entity, labels, expected
):
    original_labels = entity.labels.copy()
    transaction = AsyncMock()
    transaction_context = AsyncMock()
    transaction_context.__aenter__.return_value = transaction
    client.driver.transaction.return_value = transaction_context
    client.driver.entity_node_ops = SimpleNamespace(save=AsyncMock())

    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'save', AsyncMock()) as save,
    ):
        result = await server.update_entity(entity.uuid, labels=labels)

    assert entity.labels == expected
    assert result['labels'] == expected
    transaction.run.assert_awaited_once_with(
        'MATCH (n:Entity {uuid: $uuid}) REMOVE n:$($labels)',
        uuid=entity.uuid,
        labels=original_labels,
    )
    client.driver.entity_node_ops.save.assert_awaited_once_with(
        client.driver, entity, tx=transaction
    )
    save.assert_not_awaited()


async def test_update_entity_replaces_falkordb_labels_in_one_query(
    install_service, client, entity
):
    client.driver.provider = GraphProvider.FALKORDB
    client.driver.execute_query = AsyncMock()

    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'save', AsyncMock()) as save,
    ):
        result = await server.update_entity(entity.uuid, labels=['Organization'])

    assert 'error' not in result
    save.assert_not_awaited()
    client.driver.execute_query.assert_awaited_once()
    await_args = client.driver.execute_query.await_args
    assert await_args is not None
    query = await_args.args[0]
    entity_data = await_args.kwargs['entity_data']
    assert 'REMOVE existing:Person' in query
    assert 'SET n:Organization:Entity' in query
    assert entity_data['uuid'] == entity.uuid
    assert entity_data['name_embedding'] == entity.name_embedding
    assert entity_data['role'] == 'Engineer'


async def test_update_entity_rolls_back_neo4j_label_removal_when_save_fails(
    install_service, client, entity
):
    transaction = AsyncMock()
    transaction_context = AsyncMock()
    transaction_context.__aenter__.return_value = transaction
    client.driver.transaction.return_value = transaction_context
    client.driver.entity_node_ops = SimpleNamespace(
        save=AsyncMock(side_effect=RuntimeError('database unavailable'))
    )

    with patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)):
        result = await server.update_entity(entity.uuid, labels=['Organization'])

    assert result == {'error': 'Error updating entity: database unavailable'}
    transaction_context.__aexit__.assert_awaited_once()
    assert transaction_context.__aexit__.await_args.args[0] is RuntimeError


async def test_update_entity_rejects_invalid_label(install_service, client, entity):
    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'save', AsyncMock()) as save,
    ):
        result = await server.update_entity(entity.uuid, labels=['Person) DETACH DELETE n'])

    assert 'Error updating entity' in result['error']
    save.assert_not_awaited()


@pytest.mark.parametrize('operation', ['embedding_load', 'embedding_generate', 'save'])
async def test_update_entity_returns_operation_errors(
    install_service, client, entity, operation
):
    load_embedding = AsyncMock()
    generate_embedding = AsyncMock()
    save = AsyncMock()
    name = 'Alicia'
    if operation == 'embedding_load':
        entity.name_embedding = None
        load_embedding.side_effect = RuntimeError('embedding unavailable')
        name = None
    elif operation == 'embedding_generate':
        generate_embedding.side_effect = RuntimeError('embedding unavailable')
    else:
        save.side_effect = RuntimeError('database unavailable')

    with (
        patch.object(server.EntityNode, 'get_by_uuid', AsyncMock(return_value=entity)),
        patch.object(server.EntityNode, 'load_name_embedding', load_embedding),
        patch.object(server.EntityNode, 'generate_name_embedding', generate_embedding),
        patch.object(server.EntityNode, 'save', save),
    ):
        result = await server.update_entity(entity.uuid, name=name, summary='Updated')

    assert result['error'].startswith('Error updating entity: ')
    assert 'unavailable' in result['error']
