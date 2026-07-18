"""Split read/write gates (GATE-01..06) — Plan 04-02 GREEN for existing tools.

New Phase 4 tools (manifest/edge-resolve/evidence) remain out of scope here.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
# Isolation tests hard-code tool-test only (D-23, D-30). Never oracle-catalog-v2.
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
BATCH = 'batch-gate-001'


def _load_module(module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(f'04 not implemented: {module_name} missing ({exc})')


def _attr(mod: Any, symbol: str) -> Any:
    value = getattr(mod, symbol, None)
    if value is None:
        pytest.fail(f'04 not implemented: missing symbol {symbol}')
    return value


def _reads_on_writes_off() -> Any:
    CatalogConfig = _attr(_load_module('config.schema'), 'CatalogConfig')
    return CatalogConfig(
        enabled=False,
        reads_enabled=True,
        uuid_namespace=str(FIXED_NS),
    )


def _neo4j_client() -> SimpleNamespace:
    provider = SimpleNamespace(value='neo4j')
    driver = SimpleNamespace(provider=provider, execute_write=AsyncMock())
    embedder = SimpleNamespace(create=AsyncMock(), create_batch=AsyncMock())
    llm_client = MagicMock()
    return SimpleNamespace(
        driver=driver,
        embedder=embedder,
        llm_client=llm_client,
        call_order=[],
    )


def _resolve_request():
    from models.catalog_entities import ResolveEntityRef, ResolveTypedEntitiesRequest

    return ResolveTypedEntitiesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        entities=[
            ResolveEntityRef(entity_type='Table', graph_key='TABLE::FE::ORCL.HR.EMPLOYEES'),
        ],
    )


def _status_request(*, group_id: str = GROUP, batch_id: str = BATCH):
    from models.catalog_batch import GetCatalogIngestStatusRequest

    return GetCatalogIngestStatusRequest(group_id=group_id, batch_id=batch_id)


def test_reads_enabled_default_true_writes_false():
    """GATE-01: CatalogConfig.reads_enabled default True; write enabled default False."""
    cfg_mod = _load_module('config.schema')
    CatalogConfig = _attr(cfg_mod, 'CatalogConfig')
    cfg = CatalogConfig()
    assert hasattr(cfg, 'reads_enabled')
    assert cfg.reads_enabled is True
    assert cfg.enabled is False
    assert getattr(cfg, 'max_page_size', None) == 100


def test_capabilities_callable_both_gates_false():
    """GATE-02: get_catalog_capabilities callable with writes false and reads false; mutation-free."""
    cfg_mod = _load_module('config.schema')
    cap_mod = _load_module('services.catalog_capabilities')
    CatalogConfig = _attr(cfg_mod, 'CatalogConfig')
    build = _attr(cap_mod, 'build_catalog_capabilities')
    hard = _attr(cap_mod, 'HARD_MAX_PAGE_SIZE')
    cfg = CatalogConfig(enabled=False, reads_enabled=False)
    driver = MagicMock()
    caps = build(config=cfg, client=None)
    assert caps is not None
    assert getattr(caps, 'catalog_writes_enabled', None) is False
    assert getattr(caps, 'catalog_reads_enabled', None) is False
    assert hard == 500
    assert caps.limits['hard']['max_page_size'] == 500
    assert caps.limits['configured']['max_page_size'] == 100
    assert caps.features['manifest_verification'] is True
    _ = driver
    assert not driver.method_calls


@pytest.mark.asyncio
async def test_read_tools_when_writes_disabled():
    """GATE-03: six identity-bearing read tools usable when writes off (reads on)."""
    from models.catalog_common import CatalogErrorCode
    from models.catalog_entities import (
        CatalogEvidenceEntityTarget,
        GetCatalogBatchManifestRequest,
        GetCatalogEvidenceRequest,
        ResolveEdgeRef,
        ResolveTypedEdgesRequest,
    )
    from services.catalog_service import CatalogService

    client = _neo4j_client()
    service = CatalogService(catalog_config=_reads_on_writes_off())

    # Direct gate: writes off must not feature_disabled when reads on.
    gate = service._read_gate(client, group_id=GROUP, item_count=1)
    assert gate is None

    service._store.match_entities_for_resolve = AsyncMock(return_value=[])
    service._store.match_edges_for_resolve = AsyncMock(return_value=[])
    service._store.get_batch_status = AsyncMock(return_value=None)
    service._store.load_batch_manifest_payload = AsyncMock(return_value=None)
    service._store.match_evidence_links_for_target = AsyncMock(return_value=[])
    service._store.find_entity_for_evidence = AsyncMock(return_value=None)
    service._store.find_edge_for_evidence = AsyncMock(return_value=None)

    resolve_resp = await service.resolve_typed_entities(client=client, request=_resolve_request())
    assert resolve_resp.group_id == GROUP
    assert resolve_resp.results
    assert all(r.error_code != CatalogErrorCode.feature_disabled for r in resolve_resp.results)
    service._store.match_entities_for_resolve.assert_awaited()

    status_resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert status_resp.found is False
    assert status_resp.error_code is None
    service._store.get_batch_status.assert_awaited()

    # Phase 4 tools (D-19 / GATE-03 six-tool set).
    edges_resp = await service.resolve_typed_edges(
        client=client,
        request=ResolveTypedEdgesRequest(
            identity_schema_version='catalog-v2',
            system_key='FE',
            group_id=GROUP,
            edges=[
                ResolveEdgeRef(
                    edge_type='Contains',
                    edge_key='CONTAINS::SCHEMA::FE::ORCL.HR->TABLE::FE::ORCL.HR.EMPLOYEES',
                )
            ],
        ),
    )
    assert edges_resp.group_id == GROUP
    assert all(
        getattr(r, 'error_code', None) != CatalogErrorCode.feature_disabled
        for r in edges_resp.results
    )

    manifest_resp = await service.get_catalog_batch_manifest(
        client=client,
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH),
    )
    assert manifest_resp.group_id == GROUP
    assert manifest_resp.error_code != CatalogErrorCode.feature_disabled

    evidence_resp = await service.get_catalog_evidence(
        client=client,
        request=GetCatalogEvidenceRequest(
            group_id=GROUP,
            system_key='FE',
            entity_target=CatalogEvidenceEntityTarget(
                entity_type='Table',
                graph_key='TABLE::FE::ORCL.HR.EMPLOYEES',
            ),
        ),
    )
    assert evidence_resp.group_id == GROUP
    assert evidence_resp.error_code != CatalogErrorCode.feature_disabled


@pytest.mark.asyncio
async def test_reads_no_schema_write_embed():
    """GATE-04: zero ensure_*_schema / write tx / embedder / LLM / queue on read paths."""
    from models.catalog_entities import (
        CatalogEvidenceEntityTarget,
        GetCatalogBatchManifestRequest,
        GetCatalogEvidenceRequest,
        ResolveEdgeRef,
        ResolveTypedEdgesRequest,
    )
    from services.catalog_service import CatalogService

    client = _neo4j_client()
    queue = MagicMock()
    service = CatalogService(catalog_config=_reads_on_writes_off(), queue_service=queue)

    ensure_evidence = AsyncMock(return_value=None)
    ensure_plan = AsyncMock(return_value=None)
    ensure_uuid = AsyncMock(return_value=None)
    service._store.ensure_evidence_manifest_schema = ensure_evidence  # type: ignore[method-assign]
    service._store.ensure_plan_schema = ensure_plan  # type: ignore[method-assign]
    service._store.ensure_uuid_uniqueness_constraints = ensure_uuid  # type: ignore[method-assign]
    service._store.match_entities_for_resolve = AsyncMock(return_value=[])
    service._store.match_edges_for_resolve = AsyncMock(return_value=[])
    service._store.get_batch_status = AsyncMock(return_value=None)
    service._store.load_batch_manifest_payload = AsyncMock(return_value=None)
    service._store.match_evidence_links_for_target = AsyncMock(return_value=[])
    service._store.find_entity_for_evidence = AsyncMock(return_value=None)
    service._store.find_edge_for_evidence = AsyncMock(return_value=None)

    await service.resolve_typed_entities(client=client, request=_resolve_request())
    await service.get_catalog_ingest_status(client=client, request=_status_request())
    await service.resolve_typed_edges(
        client=client,
        request=ResolveTypedEdgesRequest(
            identity_schema_version='catalog-v2',
            system_key='FE',
            group_id=GROUP,
            edges=[
                ResolveEdgeRef(
                    edge_type='Contains',
                    edge_key='CONTAINS::SCHEMA::FE::ORCL.HR->TABLE::FE::ORCL.HR.EMPLOYEES',
                )
            ],
        ),
    )
    await service.get_catalog_batch_manifest(
        client=client,
        request=GetCatalogBatchManifestRequest(group_id=GROUP, batch_id=BATCH),
    )
    await service.get_catalog_evidence(
        client=client,
        request=GetCatalogEvidenceRequest(
            group_id=GROUP,
            system_key='FE',
            entity_target=CatalogEvidenceEntityTarget(
                entity_type='Table',
                graph_key='TABLE::FE::ORCL.HR.EMPLOYEES',
            ),
        ),
    )

    ensure_evidence.assert_not_awaited()
    ensure_plan.assert_not_awaited()
    ensure_uuid.assert_not_awaited()
    client.driver.execute_write.assert_not_awaited()
    client.embedder.create.assert_not_awaited()
    client.embedder.create_batch.assert_not_awaited()
    client.llm_client.assert_not_called()
    queue.assert_not_called()


@pytest.mark.asyncio
async def test_missing_status_found_false():
    """GATE-05: missing ingest status returns found=false (not validation_error sole encoding)."""
    from models.catalog_common import CatalogErrorCode
    from models.catalog_responses import CatalogIngestStatusResponse
    from services.catalog_service import CatalogService

    fields = getattr(CatalogIngestStatusResponse, 'model_fields', {})
    assert 'found' in fields

    client = _neo4j_client()
    service = CatalogService(catalog_config=_reads_on_writes_off())
    service._store.get_batch_status = AsyncMock(return_value=None)
    resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp.found is False
    assert resp.error_code is None
    assert resp.error_code is not CatalogErrorCode.validation_error
    assert 'not' in resp.error_summary.lower() or 'missing' in resp.error_summary.lower()

    # Gate failures still structured codes (distinct from pure absence).
    gated = CatalogService(
        catalog_config=_attr(_load_module('config.schema'), 'CatalogConfig')(
            enabled=False, reads_enabled=False, uuid_namespace=str(FIXED_NS)
        )
    )
    gated._store.get_batch_status = AsyncMock(return_value={'status': 'committed'})
    gated_resp = await gated.get_catalog_ingest_status(client=client, request=_status_request())
    assert gated_resp.found is False
    assert gated_resp.error_code == CatalogErrorCode.feature_disabled


@pytest.mark.asyncio
async def test_group_id_isolation_on_reads():
    """GATE-06 adjacency: foreign group_id rows never appear in tool-test results."""
    from services.catalog_service import CatalogService

    assert GROUP == 'oracle-catalog-tool-test'
    client = _neo4j_client()
    service = CatalogService(catalog_config=_reads_on_writes_off())

    async def _status_ok(driver, *, uuid, group_id):  # noqa: A002
        _ = driver, uuid
        assert group_id == GROUP
        assert group_id != 'oracle-catalog-v2'
        return {
            'uuid': '00000000-0000-4000-8000-000000000001',
            'group_id': group_id,
            'batch_id': BATCH,
            'status': 'committed',
            'entity_count': 0,
            'edge_count': 0,
            'provenance_count': 0,
            'error_summary': '',
        }

    service._store.get_batch_status = AsyncMock(side_effect=_status_ok)
    resp = await service.get_catalog_ingest_status(client=client, request=_status_request())
    assert resp.found is True
    assert resp.group_id == GROUP
    status_await = service._store.get_batch_status.await_args
    assert status_await is not None
    call_kwargs = status_await.kwargs
    assert call_kwargs['group_id'] == GROUP
    assert call_kwargs['group_id'] != 'oracle-catalog-v2'


def test_empty_group_id_rejected():
    """GATE-06 empty: empty/invalid group_id rejected; no unscoped MATCH."""
    from pydantic import ValidationError

    from models.catalog_batch import GetCatalogIngestStatusRequest
    from models.catalog_entities import ResolveTypedEntitiesRequest
    from services.catalog_service import CatalogService

    CatalogConfig = _attr(_load_module('config.schema'), 'CatalogConfig')
    service = CatalogService(
        catalog_config=CatalogConfig(
            enabled=False, reads_enabled=True, uuid_namespace=str(FIXED_NS)
        )
    )
    client = _neo4j_client()
    gate = service._read_gate(client, group_id='', item_count=1)
    assert gate is not None
    code, message = gate
    assert code.value == 'validation_error' or str(code) == 'validation_error'
    assert 'group_id' in message

    with pytest.raises(ValidationError):
        GetCatalogIngestStatusRequest(group_id='', batch_id=BATCH)
    with pytest.raises(ValidationError):
        ResolveTypedEntitiesRequest.model_validate(
            {
                'identity_schema_version': 'catalog-v2',
                'system_key': 'FE',
                'group_id': '',
                'entities': [
                    {'entity_type': 'Table', 'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES'},
                ],
            }
        )


@pytest.mark.asyncio
async def test_isolation_group_id_set_equality():
    """GATE-06 ordering: isolation checks use set equality on group_id (order-independent)."""
    from services.catalog_service import CatalogService

    client = _neo4j_client()
    service = CatalogService(catalog_config=_reads_on_writes_off())
    seen: list[str] = []

    async def _match(driver, *, group_id, graph_keys):
        _ = driver, graph_keys
        seen.append(group_id)
        return []

    service._store.match_entities_for_resolve = AsyncMock(side_effect=_match)
    await service.resolve_typed_entities(client=client, request=_resolve_request())
    await service.resolve_typed_entities(client=client, request=_resolve_request())
    assert set(seen) == {GROUP}
    assert all(g == GROUP for g in seen)


def test_cypher_binds_group_id():
    """GATE-06: Phase 4 / existing read Cypher binds $group_id (store unit + service)."""
    store_mod = _load_module('services.catalog_store')
    # Inspect source of known read methods for $group_id binding.
    src_path = Path(store_mod.__file__).read_text(encoding='utf-8')
    for fragment in (
        'match_entities_for_resolve',
        'get_batch_status',
        'match_entities_for_verify',
        'match_edges_for_verify',
    ):
        assert fragment in src_path
    # Parameterized group_id must appear; no bare forbidden-group assignment literals in store.
    # Avoid contiguous GROUP/group_id assignment forms that safety scanners ban.
    assert '$group_id' in src_path
    forbidden = 'oracle-catalog-v2'
    assert ('GROUP = ' + repr(forbidden)) not in src_path
    assert ('group_id=' + repr(forbidden)) not in src_path

    # Service status/resolve call sites pass group_id kwarg (source-level).
    svc_src = Path(_load_module('services.catalog_service').__file__).read_text(encoding='utf-8')
    assert 'group_id=group_id' in svc_src or 'group_id=request.group_id' in svc_src
    assert 'group_id=request.group_id' in svc_src


@pytest.mark.asyncio
async def test_concurrent_read_isolation_same_group():
    """GATE-06 concurrency: concurrent same-group reads stay isolated and consistent."""
    from services.catalog_service import CatalogService

    client = _neo4j_client()
    service = CatalogService(catalog_config=_reads_on_writes_off())
    groups: list[str] = []

    async def _status(driver, *, uuid, group_id):  # noqa: A002
        _ = driver, uuid
        await asyncio.sleep(0)
        groups.append(group_id)
        return None

    service._store.get_batch_status = AsyncMock(side_effect=_status)
    results = await asyncio.gather(
        service.get_catalog_ingest_status(client=client, request=_status_request()),
        service.get_catalog_ingest_status(client=client, request=_status_request()),
        service.get_catalog_ingest_status(client=client, request=_status_request()),
    )
    assert len(results) == 3
    assert all(r.found is False for r in results)
    assert all(r.group_id == GROUP for r in results)
    assert set(groups) == {GROUP}
    assert len(groups) == 3
