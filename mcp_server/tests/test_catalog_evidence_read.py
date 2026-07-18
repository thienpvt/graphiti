"""GREEN: get_catalog_evidence pagination (EVID-12, IDEN-08).

Bounded pages, compact default, group isolation on oracle-catalog-tool-test only.
"""

from __future__ import annotations

import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_common import MAX_EVIDENCE_LENGTH, CatalogErrorCode  # noqa: E402
from models.catalog_entities import GetCatalogEvidenceRequest  # noqa: E402
from models.catalog_evidence import (  # noqa: E402
    CatalogEvidenceEdgeTarget,
    CatalogEvidenceEntityTarget,
)
from services.catalog_capabilities import HARD_MAX_PAGE_SIZE  # noqa: E402
from services.catalog_identity import catalog_edge_uuid, catalog_entity_uuid  # noqa: E402
from services.catalog_service import CatalogService  # noqa: E402

GROUP = 'oracle-catalog-tool-test'
DEFAULT_MAX_PAGE_SIZE = 100
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GRAPH_KEY = 'TABLE::FE::ORCL.HR.EMPLOYEES'
EDGE_KEY = 'CONTAINS::FE::ORCL.HR->ORCL.HR.EMPLOYEES'


def _enabled_config(**kwargs) -> CatalogConfig:
    base = {'enabled': True, 'uuid_namespace': str(FIXED_NS), 'max_page_size': 100}
    base.update(kwargs)
    return CatalogConfig(**base)


def _make_client(*, provider: str = 'neo4j'):
    provider_enum = SimpleNamespace(value=provider)
    call_order: list[str] = []
    embedder = AsyncMock(return_value=[0.1, 0.2, 0.3])

    async def _embed(*args, **kwargs):
        _ = args, kwargs
        call_order.append('embed')
        return [0.1, 0.2, 0.3]

    embedder.create = AsyncMock(side_effect=_embed)
    embedder.create_batch = AsyncMock(side_effect=lambda inputs: [[0.1]] * len(inputs))

    @asynccontextmanager
    async def _transaction():
        call_order.append('transaction')
        yield MagicMock()

    driver = SimpleNamespace(
        provider=provider_enum,
        transaction=_transaction,
        execute_query=AsyncMock(return_value=([], None, None)),
    )
    return SimpleNamespace(
        driver=driver,
        embedder=embedder,
        llm_client=MagicMock(),
        call_order=call_order,
    )


def _entity_request(**kwargs) -> GetCatalogEvidenceRequest:
    payload: dict[str, Any] = {
        'group_id': GROUP,
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'entity_target': CatalogEvidenceEntityTarget(entity_type='Table', graph_key=GRAPH_KEY),
    }
    payload.update(kwargs)
    return GetCatalogEvidenceRequest.model_validate(payload)


def _link(i: int, *, excerpt: str | None = 'FULL SOURCE TEXT PAYLOAD') -> dict[str, Any]:
    return {
        'uuid': f'{i:08x}-0000-4000-8000-00000000000{i % 10}',
        'link_key': f'LINK::{i}',
        'content_sha256': f'{i:064x}'[:64],
        'source_uuid': f'src-{i}',
        'target_kind': 'entity',
        'target_uuid': catalog_entity_uuid(FIXED_NS, GROUP, 'Table', GRAPH_KEY),
        'evidence_kind': 'ddl',
        'extractor_name': 'test',
        'extractor_version': '1',
        'rule_id': None,
        'confidence': 0.9,
        'excerpt': excerpt,
    }


@pytest.mark.asyncio
async def test_evidence_page_bounded():
    """EVID-12: get_catalog_evidence returns bounded offset/limit page with total."""
    assert GROUP == 'oracle-catalog-tool-test'
    assert DEFAULT_MAX_PAGE_SIZE == 100
    assert HARD_MAX_PAGE_SIZE == 500
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    rows = [_link(i) for i in range(5)]
    service._store.match_evidence_links_for_target = AsyncMock(return_value=rows)
    resp = await service.get_catalog_evidence(
        client=client, request=_entity_request(offset=1, limit=2)
    )
    assert resp.total == 5
    assert resp.offset == 1
    assert resp.limit == 2
    assert len(resp.links) == 2
    assert resp.links[0].uuid == rows[1]['uuid']
    assert resp.links[1].uuid == rows[2]['uuid']
    assert resp.found_target is True
    assert 'transaction' not in client.call_order
    client.embedder.create.assert_not_awaited()

    # hard max fail-closed
    hard = await service.get_catalog_evidence(
        client=client, request=_entity_request(limit=HARD_MAX_PAGE_SIZE + 1)
    )
    assert hard.error_code == CatalogErrorCode.validation_error
    assert hard.links == []


@pytest.mark.asyncio
async def test_page():
    """EVID-12 alias (research test map): evidence pagination."""
    await test_evidence_page_bounded()


@pytest.mark.asyncio
async def test_compact_default():
    """EVID-12: compact default projection (no full source payload unless requested)."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_evidence_links_for_target = AsyncMock(
        return_value=[_link(1, excerpt='SECRET FULL SOURCE')]
    )
    resp = await service.get_catalog_evidence(client=client, request=_entity_request())
    assert len(resp.links) == 1
    assert resp.links[0].excerpt is None
    assert resp.links[0].link_key == 'LINK::1'
    dumped = resp.model_dump()
    assert 'SECRET FULL SOURCE' not in str(dumped)
    assert 'payload_b64' not in dumped
    assert 'embedding' not in str(dumped).lower()


@pytest.mark.asyncio
async def test_optional_excerpt_length_bound():
    """EVID-12: optional excerpt length is bounded fail-closed."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    huge = 'X' * (MAX_EVIDENCE_LENGTH + 500)
    service._store.match_evidence_links_for_target = AsyncMock(
        return_value=[_link(2, excerpt=huge)]
    )
    resp = await service.get_catalog_evidence(
        client=client, request=_entity_request(include_excerpts=True)
    )
    assert resp.links[0].excerpt is not None
    assert len(resp.links[0].excerpt) <= MAX_EVIDENCE_LENGTH


@pytest.mark.asyncio
async def test_empty_links():
    """EVID-12 empty: zero links → empty page, total 0, still group-scoped."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    captured: dict[str, Any] = {}

    async def _match(executor=None, **kwargs):
        _ = executor
        captured.update(kwargs)
        return []

    service._store.match_evidence_links_for_target = AsyncMock(side_effect=_match)
    resp = await service.get_catalog_evidence(client=client, request=_entity_request())
    assert resp.total == 0
    assert resp.links == []
    assert resp.found_target is True
    assert captured.get('group_id') == GROUP
    assert captured.get('target_kind') == 'entity'


@pytest.mark.asyncio
async def test_adjacency_multi_link():
    """EVID-12 adjacency: multi-link same target returns distinct link rows (no collapse)."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    rows = [_link(1), _link(2), _link(3)]
    service._store.match_evidence_links_for_target = AsyncMock(return_value=rows)
    resp = await service.get_catalog_evidence(client=client, request=_entity_request())
    assert resp.total == 3
    uuids = [lnk.uuid for lnk in resp.links]
    assert len(set(uuids)) == 3


@pytest.mark.asyncio
async def test_ordering_stable():
    """EVID-12 ordering: stable ORDER BY uuid then offset/limit."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    # Store returns already uuid-ordered rows; service preserves that order.
    rows = [_link(i) for i in (1, 2, 3, 4)]
    service._store.match_evidence_links_for_target = AsyncMock(return_value=rows)
    page1 = await service.get_catalog_evidence(
        client=client, request=_entity_request(offset=0, limit=2)
    )
    page2 = await service.get_catalog_evidence(
        client=client, request=_entity_request(offset=2, limit=2)
    )
    assert [x.uuid for x in page1.links] == [rows[0]['uuid'], rows[1]['uuid']]
    assert [x.uuid for x in page2.links] == [rows[2]['uuid'], rows[3]['uuid']]
    # reread same page identical
    page1b = await service.get_catalog_evidence(
        client=client, request=_entity_request(offset=0, limit=2)
    )
    assert [x.uuid for x in page1b.links] == [x.uuid for x in page1.links]


@pytest.mark.asyncio
async def test_group_isolation():
    """EVID-12 / GATE-06: evidence reads constrained to group_id; tool-test only."""
    assert GROUP == 'oracle-catalog-tool-test'
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    captured: dict[str, Any] = {}

    async def _match(executor=None, **kwargs):
        _ = executor
        captured.clear()
        captured.update(kwargs)
        return []

    service._store.match_evidence_links_for_target = AsyncMock(side_effect=_match)
    await service.get_catalog_evidence(client=client, request=_entity_request())
    assert captured['group_id'] == GROUP
    # writes-off still works
    service2 = CatalogService(
        catalog_config=CatalogConfig(
            enabled=False, reads_enabled=True, uuid_namespace=str(FIXED_NS)
        )
    )
    service2._store.match_evidence_links_for_target = AsyncMock(return_value=[])
    resp = await service2.get_catalog_evidence(client=client, request=_entity_request())
    assert resp.error_code is None
    assert 'transaction' not in client.call_order


@pytest.mark.asyncio
async def test_full_graph_key_on_target():
    """IDEN-08: target identity on evidence responses is full system-scoped graph_key."""
    client = _make_client()
    service = CatalogService(catalog_config=_enabled_config())
    service._store.match_evidence_links_for_target = AsyncMock(return_value=[])
    resp = await service.get_catalog_evidence(client=client, request=_entity_request())
    assert resp.target_graph_key == GRAPH_KEY
    assert resp.target_graph_key.startswith('TABLE::FE::')
    expected_uuid = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', GRAPH_KEY)
    assert resp.target_uuid == expected_uuid

    # edge target path
    edge_req = GetCatalogEvidenceRequest(
        group_id=GROUP,
        identity_schema_version='catalog-v2',
        system_key='FE',
        edge_target=CatalogEvidenceEdgeTarget(edge_type='Contains', edge_key=EDGE_KEY),
    )
    service._store.match_evidence_links_for_target = AsyncMock(return_value=[])
    edge_resp = await service.get_catalog_evidence(client=client, request=edge_req)
    assert edge_resp.target_edge_key == EDGE_KEY
    assert edge_resp.target_uuid == catalog_edge_uuid(FIXED_NS, GROUP, 'Contains', EDGE_KEY)
    assert edge_resp.target_kind == 'edge'


def test_request_requires_exactly_one_target():
    with pytest.raises(ValidationError):
        GetCatalogEvidenceRequest.model_validate(
            {
                'group_id': GROUP,
                'system_key': 'FE',
                'identity_schema_version': 'catalog-v2',
            }
        )
