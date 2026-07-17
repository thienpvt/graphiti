"""Live Neo4j integration for catalog GATE-02 / GATE-03.

Hardcoded group_id: oracle-catalog-tool-test only.
Teardown: DETACH DELETE WHERE group_id = that value. Never clear_graph.
Never touch oracle-catalog-v2 or other groups.

Embedder: FakeEmbedder with fixed vectors (documented). Full CatalogService write
path + real Neo4jDriver.transaction still exercised.

Gate mode: CATALOG_INT_REQUIRED=1 converts missing Neo4j into FAIL (not skip).
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

# Match catalog unit tests: insert mcp_server/src (pyright extraPaths = ["src"]).
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
from models.catalog_provenance import (  # noqa: E402
    CatalogProvenanceEdgeTarget,
    CatalogProvenanceEntityTarget,
    CatalogSourceItem,
)
from services.catalog_identity import (  # noqa: E402
    catalog_batch_uuid,
    catalog_edge_uuid,
    catalog_entity_uuid,
    catalog_source_uuid,
)
from services.catalog_service import CatalogService  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_neo4j,
    pytest.mark.asyncio,
]

GROUP = 'oracle-catalog-tool-test'
FORBIDDEN_GROUP = 'oracle-catalog-v2'
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
EMBED_DIM = 8
BATCH = 'gate02-batch-001'
EDGE_BATCH = 'gate02-edge-batch-001'
ACCEPT_TAB_BATCH = 'accept-tab-batch-001'
ACCEPT_TAB_FIXTURE = Path(__file__).parent / 'fixtures' / 'accept_tab_sanitized.json'


def _catalog_int_required() -> bool:
    return os.environ.get('CATALOG_INT_REQUIRED', '').strip() in ('1', 'true', 'TRUE', 'yes')


def _neo4j_env() -> tuple[str, str, str]:
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:17687')
    user = os.environ.get('NEO4J_USER', 'neo4j')
    password = os.environ.get('NEO4J_PASSWORD', 'catalogtest123')
    return uri, user, password


class FakeEmbedder:
    """Deterministic fixed-vector embedder — no live LLM/embedding provider."""

    call_count = 0

    def __init__(self, dim: int = EMBED_DIM):
        self.dim = dim
        self.create_calls = 0
        self.batch_calls = 0

    async def create(self, input_data: Any = None, **kwargs: Any) -> list[float]:
        # Consume callback args: text length influences only call accounting.
        self.create_calls += 1 + (0 if input_data is None else 0) + len(kwargs)
        FakeEmbedder.call_count += 1
        return [0.01 * ((i % 7) + 1) for i in range(self.dim)]

    async def create_batch(self, inputs: list[Any]) -> list[list[float]]:
        self.batch_calls += 1
        assert isinstance(inputs, list)
        return [await self.create(input_data=item) for item in inputs]


class RecordingLLM:
    """Spy LLM client — catalog path must never call it."""

    def __init__(self) -> None:
        self.generate_response = AsyncMock()
        self.calls = 0

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1 + len(args) + len(kwargs)
        raise AssertionError('LLM must not be called by catalog path')


class RecordingQueue:
    def __init__(self) -> None:
        self.add_episode = AsyncMock()
        self.enqueue = AsyncMock()
        self.add = AsyncMock()


class CommunityLLM:
    """Deterministic test-only summarizer for an explicit community build."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate_response(
        self, *args: Any, response_model: Any = None, **kwargs: Any
    ) -> dict[str, str]:
        _ = args, kwargs
        self.calls += 1
        if getattr(response_model, '__name__', '') == 'SummaryDescription':
            return {'description': 'Synthetic catalog community'}
        return {'summary': 'Synthetic catalog entities'}


def _enabled_config() -> CatalogConfig:
    return CatalogConfig(enabled=True, uuid_namespace=str(FIXED_NS))


def _entity(
    entity_type: str,
    graph_key: str,
    name_raw: str,
    name_canonical: str,
    dqn: str,
    summary: str,
    **extra: Any,
) -> CatalogEntityItem:
    data: dict[str, Any] = {
        'entity_type': entity_type,
        'graph_key': graph_key,
        'name_raw': name_raw,
        'name_canonical': name_canonical,
        'database_qualified_name': dqn,
        'summary': summary,
        'attributes': {'src': 'gate02'},
        'confidence': 0.95,
    }
    data.update(extra)
    return CatalogEntityItem.model_validate(data)


def _six_entities() -> list[CatalogEntityItem]:
    return [
        _entity('Database', 'DATABASE::ORCL', 'ORCL', 'orcl', 'ORCL', 'Oracle database'),
        _entity('Schema', 'SCHEMA::HR', 'HR', 'hr', 'ORCL.HR', 'HR schema'),
        _entity(
            'Table', 'TABLE::HR.EMPLOYEES', 'EMPLOYEES', 'employees', 'HR.EMPLOYEES', 'Employees'
        ),
        _entity('Column', 'COLUMN::HR.EMPLOYEES.ID', 'ID', 'id', 'HR.EMPLOYEES.ID', 'PK column'),
        _entity(
            'Constraint',
            'CONSTRAINT::HR.EMPLOYEES.PK_EMP',
            'PK_EMP',
            'pk_emp',
            'HR.EMPLOYEES.PK_EMP',
            'Primary key',
        ),
        _entity(
            'Index',
            'INDEX::HR.EMPLOYEES.IX_EMP_NAME',
            'IX_EMP_NAME',
            'ix_emp_name',
            'HR.EMPLOYEES.IX_EMP_NAME',
            'Name index',
        ),
    ]


def _extra_table(key: str = 'TABLE::HR.DEPARTMENTS') -> CatalogEntityItem:
    name = key.split('::', 1)[1].split('.')[-1]
    return _entity('Table', key, name, name.lower(), key.split('::', 1)[1], f'Table {name}')


def _doc_entity() -> CatalogEntityItem:
    return _entity(
        'DictionaryDocument',
        'DOC::HR.EMPLOYEES.DOC',
        'EMP_DOC',
        'emp_doc',
        'HR.EMPLOYEES.DOC',
        'Employee documentation',
    )


def _edge(
    edge_type: str,
    edge_key: str,
    source_graph_key: str,
    source_entity_type: str,
    target_graph_key: str,
    target_entity_type: str,
    fact: str,
    **extra: Any,
) -> CatalogEdgeItem:
    data: dict[str, Any] = {
        'edge_type': edge_type,
        'edge_key': edge_key,
        'source_graph_key': source_graph_key,
        'source_entity_type': source_entity_type,
        'target_graph_key': target_graph_key,
        'target_entity_type': target_entity_type,
        'fact': fact,
        'confidence': 0.9,
    }
    data.update(extra)
    return CatalogEdgeItem.model_validate(data)


def _structural_and_fk_edges() -> list[CatalogEdgeItem]:
    return [
        _edge(
            'Contains',
            'CONTAINS::SCHEMA::HR->TABLE::HR.EMPLOYEES',
            'SCHEMA::HR',
            'Schema',
            'TABLE::HR.EMPLOYEES',
            'Table',
            'schema HR contains table EMPLOYEES',
        ),
        _edge(
            'PrimaryKeyOf',
            'PK::CONSTRAINT::HR.EMPLOYEES.PK_EMP->TABLE::HR.EMPLOYEES',
            'CONSTRAINT::HR.EMPLOYEES.PK_EMP',
            'Constraint',
            'TABLE::HR.EMPLOYEES',
            'Table',
            'PK_EMP is primary key of EMPLOYEES',
        ),
        _edge(
            'UniqueKeyOf',
            'UK::CONSTRAINT::HR.EMPLOYEES.PK_EMP->COLUMN::HR.EMPLOYEES.ID',
            'CONSTRAINT::HR.EMPLOYEES.PK_EMP',
            'Constraint',
            'COLUMN::HR.EMPLOYEES.ID',
            'Column',
            'PK_EMP uniquely keys column ID',
        ),
        _edge(
            'DocumentedBy',
            'DOCUMENTED::TABLE::HR.EMPLOYEES->DOC::HR.EMPLOYEES.DOC',
            'TABLE::HR.EMPLOYEES',
            'Table',
            'DOC::HR.EMPLOYEES.DOC',
            'DictionaryDocument',
            'EMPLOYEES documented by EMP_DOC',
        ),
        _edge(
            'ForeignKeyTo',
            'FK::HR.EMPLOYEES.DEPT_ID->HR.DEPARTMENTS.DEPT_ID',
            'TABLE::HR.EMPLOYEES',
            'Table',
            'TABLE::HR.DEPARTMENTS',
            'Table',
            'employees.dept_id references departments.dept_id',
        ),
        _edge(
            'ForeignKeyTo',
            'FK::HR.EMPLOYEES.MGR_ID->HR.DEPARTMENTS.MGR_DEPT',
            'TABLE::HR.EMPLOYEES',
            'Table',
            'TABLE::HR.DEPARTMENTS',
            'Table',
            'employees.mgr_id references departments via alternate FK key',
        ),
    ]


async def _count_group_nodes(driver: Any, group_id: str = GROUP) -> int:
    result = await driver.execute_query(
        'MATCH (n) WHERE n.group_id = $g RETURN count(n) AS c',
        params={'g': group_id},
    )
    records = result[0] if result else []
    if not records:
        return 0
    row = records[0]
    return int(row['c'] if isinstance(row, dict) else row['c'])


async def _count_group_edges(driver: Any, group_id: str = GROUP) -> int:
    result = await driver.execute_query(
        'MATCH ()-[e]->() WHERE e.group_id = $g RETURN count(e) AS c',
        params={'g': group_id},
    )
    records = result[0] if result else []
    if not records:
        return 0
    row = records[0]
    return int(row['c'] if isinstance(row, dict) else row['c'])


async def _snapshot_other_groups(driver: Any) -> tuple[tuple[str, int, int], ...]:
    result = await driver.execute_query(
        """
        CALL () {
          MATCH (n)
          WHERE n.group_id IS NOT NULL AND n.group_id <> $g
          RETURN n.group_id AS group_id, count(n) AS node_count, 0 AS edge_count
          UNION ALL
          MATCH ()-[e]->()
          WHERE e.group_id IS NOT NULL AND e.group_id <> $g
          RETURN e.group_id AS group_id, 0 AS node_count, count(e) AS edge_count
        }
        RETURN group_id, sum(node_count) AS node_count, sum(edge_count) AS edge_count
        ORDER BY group_id
        """,
        params={'g': GROUP},
    )
    return tuple(
        (str(row['group_id']), int(row['node_count']), int(row['edge_count']))
        for row in (result[0] if result else [])
    )


async def _count_entity_uuid(driver: Any, ent_uuid: str) -> int:
    result = await driver.execute_query(
        'MATCH (n:Entity {uuid: $u}) WHERE n.group_id = $g RETURN count(n) AS c',
        params={'u': ent_uuid, 'g': GROUP},
    )
    records = result[0] if result else []
    row = records[0]
    return int(row['c'] if isinstance(row, dict) else row['c'])


async def _count_edge_uuid(driver: Any, edge_uuid: str) -> int:
    result = await driver.execute_query(
        'MATCH ()-[e:RELATES_TO {uuid: $u}]->() WHERE e.group_id = $g RETURN count(e) AS c',
        params={'u': edge_uuid, 'g': GROUP},
    )
    records = result[0] if result else []
    row = records[0]
    return int(row['c'] if isinstance(row, dict) else row['c'])


async def _fetch_entity(driver: Any, ent_uuid: str) -> dict[str, Any] | None:
    result = await driver.execute_query(
        """
        MATCH (n:Entity {uuid: $u})
        WHERE n.group_id = $g
        RETURN n.uuid AS uuid,
               n.graph_key AS graph_key,
               n.name AS name,
               n.name_raw AS name_raw,
               n.name_canonical AS name_canonical,
               n.summary AS summary,
               n.content_sha256 AS content_sha256,
               n.batch_id AS batch_id,
               n.created_at AS created_at,
               n.updated_at AS updated_at,
               n._catalog_create_token AS create_token,
               labels(n) AS labels,
               n.name_embedding IS NOT NULL AS has_emb
        """,
        params={'u': ent_uuid, 'g': GROUP},
    )
    records = result[0] if result else []
    if not records:
        return None
    row = records[0]
    return dict(row) if not isinstance(row, dict) else row


async def _seed_generic_entity(driver: Any, name: str) -> str:
    """Create bare Entity (no custom label) for generic_endpoint_conflict tests."""
    u = str(uuid.uuid4())
    await driver.execute_query(
        """
        CREATE (n:Entity {
            uuid: $u,
            group_id: $g,
            name: $name,
            graph_key: $name
        })
        """,
        params={'u': u, 'g': GROUP, 'name': name},
    )
    return u


async def _seed_wrong_type_entity(driver: Any, name: str, label: str = 'View') -> str:
    u = str(uuid.uuid4())
    # Label is server-controlled test fixture constant, not client input.
    cypher = f"""
        CREATE (n:Entity:{label} {{
            uuid: $u,
            group_id: $g,
            name: $name,
            graph_key: $name
        }})
        """
    await driver.execute_query(cypher, params={'u': u, 'g': GROUP, 'name': name})
    return u


async def _snapshot_group_elements(driver: Any, group_id: str = GROUP) -> tuple[set[str], set[str]]:
    nodes = await driver.execute_query(
        'MATCH (n) WHERE n.group_id = $g RETURN elementId(n) AS id',
        params={'g': group_id},
    )
    edges = await driver.execute_query(
        'MATCH ()-[e]->() WHERE e.group_id = $g RETURN elementId(e) AS id',
        params={'g': group_id},
    )
    return (
        {str(row['id']) for row in (nodes[0] if nodes else [])},
        {str(row['id']) for row in (edges[0] if edges else [])},
    )


async def _teardown_created_elements(
    driver: Any,
    before_nodes: set[str],
    before_edges: set[str],
    *,
    group_id: str = GROUP,
) -> None:
    current_nodes, current_edges = await _snapshot_group_elements(driver, group_id)
    created_edges = sorted(current_edges - before_edges)
    created_nodes = sorted(current_nodes - before_nodes)
    if created_edges:
        await driver.execute_query(
            'MATCH ()-[e]->() WHERE e.group_id = $g AND elementId(e) IN $ids DELETE e',
            params={'g': group_id, 'ids': created_edges},
        )
    if created_nodes:
        await driver.execute_query(
            'MATCH (n) WHERE n.group_id = $g AND elementId(n) IN $ids DETACH DELETE n',
            params={'g': group_id, 'ids': created_nodes},
        )


@pytest.fixture
async def neo4j_driver():
    """Real Neo4jDriver against env/default bolt://localhost:17687."""
    try:
        from graphiti_core.driver.neo4j_driver import Neo4jDriver
    except Exception as exc:  # pragma: no cover
        if _catalog_int_required():
            pytest.fail(f'Neo4j driver import failed under CATALOG_INT_REQUIRED=1: {exc}')
        pytest.skip(f'Neo4j driver unavailable: {exc}')

    uri, user, password = _neo4j_env()
    driver = Neo4jDriver(uri=uri, user=user, password=password)
    try:
        await driver.execute_query('RETURN 1 AS ok', params={})
    except Exception as exc:
        await driver.close()
        if _catalog_int_required():
            pytest.fail(f'Neo4j unavailable under CATALOG_INT_REQUIRED=1: {exc}')
        pytest.skip(f'Neo4j unavailable: {exc}')

    # Allow background Graphiti stock index bootstrap if scheduled.
    # Product catalog schema (composite identity UNIQUE) is created by
    # CatalogNeo4jStore.ensure_uuid_uniqueness_constraints on first real write.
    # Fixture issues ZERO DROP statements — safe on shared authorized DBs.
    await asyncio.sleep(0.5)

    group_nodes_before, group_edges_before = await _snapshot_group_elements(driver)
    other_groups_before = await _snapshot_other_groups(driver)
    forbidden_before = (
        await _count_group_nodes(driver, FORBIDDEN_GROUP),
        await _count_group_edges(driver, FORBIDDEN_GROUP),
    )
    try:
        yield driver
    finally:
        try:
            await _teardown_created_elements(driver, group_nodes_before, group_edges_before)
            assert await _snapshot_group_elements(driver) == (
                group_nodes_before,
                group_edges_before,
            )
            assert await _snapshot_other_groups(driver) == other_groups_before
            assert (
                await _count_group_nodes(driver, FORBIDDEN_GROUP),
                await _count_group_edges(driver, FORBIDDEN_GROUP),
            ) == forbidden_before
        finally:
            await driver.close()


@pytest.fixture
async def catalog_client(neo4j_driver: Any):
    driver = neo4j_driver
    assert driver is not None
    embedder = FakeEmbedder()
    llm = RecordingLLM()
    queue = RecordingQueue()
    client = SimpleNamespace(
        driver=driver,
        embedder=embedder,
        llm_client=llm,
    )
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    return SimpleNamespace(
        client=client,
        service=service,
        embedder=embedder,
        llm=llm,
        queue=queue,
        driver=driver,
    )


async def _upsert_entities(ctx, entities: list[CatalogEntityItem], **kw: Any):
    req = UpsertTypedEntitiesRequest(
        group_id=GROUP,
        batch_id=kw.pop('batch_id', BATCH),
        entities=entities,
        dry_run=kw.pop('dry_run', False),
        atomic=kw.pop('atomic', True),
    )
    return await ctx.service.upsert_typed_entities(client=ctx.client, request=req)


async def _upsert_edges(ctx, edges: list[CatalogEdgeItem], **kw: Any):
    req = UpsertTypedEdgesRequest(
        group_id=GROUP,
        batch_id=kw.pop('batch_id', EDGE_BATCH),
        edges=edges,
        dry_run=kw.pop('dry_run', False),
        atomic=kw.pop('atomic', True),
        strict_endpoints=kw.pop('strict_endpoints', True),
    )
    return await ctx.service.upsert_typed_edges(client=ctx.client, request=req)


async def _seed_happy_graph(ctx) -> dict[str, Any]:
    """Create six core entities + doc + departments + six edges."""
    entities = _six_entities() + [_doc_entity(), _extra_table()]
    eresp = await _upsert_entities(ctx, entities)
    assert eresp.failed == 0, [r.model_dump() for r in eresp.results if r.status == 'error']
    assert eresp.created == len(entities)
    edges = _structural_and_fk_edges()
    edresp = await _upsert_edges(ctx, edges)
    assert edresp.failed == 0, [r.model_dump() for r in edresp.results if r.status == 'error']
    assert edresp.created == 6
    return {
        'entities': entities,
        'edges': edges,
        'entity_resp': eresp,
        'edge_resp': edresp,
    }


def _accept_tab_request(
    *,
    dry_run: bool = False,
    batch_id: str = ACCEPT_TAB_BATCH,
) -> UpsertCatalogBatchRequest:
    payload = json.loads(ACCEPT_TAB_FIXTURE.read_text(encoding='utf-8'))
    assert payload['batch_id'] == ACCEPT_TAB_BATCH
    return UpsertCatalogBatchRequest(
        group_id=GROUP,
        batch_id=batch_id,
        entities=[CatalogEntityItem.model_validate(item) for item in payload['entities']],
        edges=[CatalogEdgeItem.model_validate(item) for item in payload['edges']],
        provenance=NestedProvenancePayload(
            sources=[
                CatalogSourceItem.model_validate(item) for item in payload['provenance']['sources']
            ],
            entity_targets=[
                CatalogProvenanceEntityTarget.model_validate(item)
                for item in payload['provenance']['entity_targets']
            ],
            edge_targets=[
                CatalogProvenanceEdgeTarget.model_validate(item)
                for item in payload['provenance']['edge_targets']
            ],
        ),
        dry_run=dry_run,
    )


async def _upsert_accept_tab(ctx, *, dry_run: bool = False, batch_id: str = ACCEPT_TAB_BATCH):
    request = _accept_tab_request(dry_run=dry_run, batch_id=batch_id)
    response = await ctx.service.upsert_catalog_batch(client=ctx.client, request=request)
    return request, response


# ---------------------------------------------------------------------------
# Phase 2 Task 1: atomic ACCEPT_TAB batch
# ---------------------------------------------------------------------------


async def test_accept_tab_dry_run_leaves_graph_and_status_untouched(catalog_client):
    ctx = catalog_client
    before = await _snapshot_group_elements(ctx.driver)
    request, response = await _upsert_accept_tab(ctx, dry_run=True)

    assert response.dry_run is True
    assert response.status == 'validating'
    assert response.failed == 0
    assert response.entity_created == len(request.entities)
    assert response.edge_created == len(request.edges)
    assert await _snapshot_group_elements(ctx.driver) == before

    status = await ctx.service.get_catalog_ingest_status(
        client=ctx.client,
        request=GetCatalogIngestStatusRequest(group_id=GROUP, batch_id=ACCEPT_TAB_BATCH),
    )
    assert status.error_code == CatalogErrorCode.validation_error
    assert status.error_summary == 'batch status not found'


async def test_accept_tab_commit_retry_conflict_status_reinitialization_and_verify(catalog_client):
    ctx = catalog_client
    request, committed = await _upsert_accept_tab(ctx)
    assert request.provenance is not None

    assert committed.status == 'committed'
    assert committed.failed == 0
    assert committed.entity_created == len(request.entities)
    assert committed.edge_created == len(request.edges)
    assert committed.provenance_created == len(request.provenance.sources)

    expected_entities = {
        catalog_entity_uuid(FIXED_NS, GROUP, item.entity_type, item.graph_key)
        for item in request.entities
    }
    expected_edges = {
        catalog_edge_uuid(FIXED_NS, GROUP, item.edge_type, item.edge_key) for item in request.edges
    }
    source = request.provenance.sources[0]
    expected_source = catalog_source_uuid(FIXED_NS, GROUP, source.source_key)
    expected_batch = catalog_batch_uuid(FIXED_NS, GROUP, request.batch_id)

    snapshot = await ctx.driver.execute_query(
        """
        MATCH (b:CatalogIngestBatch {uuid: $batch_uuid, group_id: $g})
        OPTIONAL MATCH (ep:Episodic {uuid: $source_uuid, group_id: $g})
        OPTIONAL MATCH (ep)-[m:MENTIONS]->(n:Entity)
        WHERE m.group_id = $g AND n.group_id = $g
        WITH b, ep, collect(DISTINCT n.uuid) AS mentioned
        MATCH (s:Entity)-[e:RELATES_TO]->(t:Entity)
        WHERE e.group_id = $g AND e.uuid IN $edge_uuids
        RETURN labels(b) AS batch_labels, b.status AS status,
               ep.uuid AS source_uuid, labels(ep) AS source_labels,
               mentioned, collect(DISTINCT e.uuid) AS edges,
               collect(DISTINCT e.episodes) AS edge_episodes
        """,
        params={
            'g': GROUP,
            'batch_uuid': expected_batch,
            'source_uuid': expected_source,
            'edge_uuids': sorted(expected_edges),
        },
    )
    row = snapshot[0][0]
    assert row['batch_labels'] == ['CatalogIngestBatch']
    assert row['status'] == 'committed'
    assert row['source_uuid'] == expected_source
    assert set(row['source_labels']) == {'Episodic'}
    assert set(row['mentioned']) == expected_entities
    assert set(row['edges']) == expected_edges
    assert all(episodes == [expected_source] for episodes in row['edge_episodes'])

    physical_before = await _snapshot_group_elements(ctx.driver)
    _, retry = await _upsert_accept_tab(ctx)
    assert retry.status == 'committed'
    assert retry.entity_unchanged == len(request.entities)
    assert retry.edge_unchanged == len(request.edges)
    assert retry.provenance_unchanged == len(request.provenance.sources)
    assert await _snapshot_group_elements(ctx.driver) == physical_before

    conflict_request = request.model_copy(
        update={
            'entities': [
                request.entities[0].model_copy(update={'summary': 'Conflicting synthetic summary'}),
                *request.entities[1:],
            ]
        }
    )
    conflict = await ctx.service.upsert_catalog_batch(client=ctx.client, request=conflict_request)
    assert conflict.error_code == CatalogErrorCode.batch_conflict
    assert conflict.status == 'failed'
    assert await _snapshot_group_elements(ctx.driver) == physical_before

    restarted = CatalogService(catalog_config=_enabled_config(), queue_service=RecordingQueue())
    status = await restarted.get_catalog_ingest_status(
        client=ctx.client,
        request=GetCatalogIngestStatusRequest(group_id=GROUP, batch_id=request.batch_id),
    )
    assert status.status == 'committed'
    assert status.batch_uuid == expected_batch
    assert status.entity_count == len(request.entities)
    assert status.edge_count == len(request.edges)
    assert status.provenance_count == len(request.provenance.sources)

    verified = await restarted.verify_catalog_batch(
        client=ctx.client,
        request=VerifyCatalogBatchRequest(
            group_id=GROUP,
            batch_id=request.batch_id,
            entities=[
                VerifyEntityRef(entity_type=item.entity_type, graph_key=item.graph_key)
                for item in request.entities
            ],
            edges=[
                VerifyEdgeRef(edge_type=item.edge_type, edge_key=item.edge_key)
                for item in request.edges
            ],
            require_provenance=True,
        ),
    )
    assert verified.error_code is None
    assert verified.missing == []
    assert verified.anomalies == []
    assert verified.missing_provenance == []


async def test_accept_tab_concurrent_identical_batch_is_one_logical_set(catalog_client):
    ctx = catalog_client

    async def _once():
        service = CatalogService(catalog_config=_enabled_config(), queue_service=RecordingQueue())
        client = SimpleNamespace(
            driver=ctx.driver, embedder=FakeEmbedder(), llm_client=RecordingLLM()
        )
        return await service.upsert_catalog_batch(client=client, request=_accept_tab_request())

    responses = await asyncio.gather(*[_once() for _ in range(4)])
    assert all(response.status == 'committed' for response in responses)
    request = _accept_tab_request()
    assert request.provenance is not None
    for item in request.entities:
        expected = catalog_entity_uuid(FIXED_NS, GROUP, item.entity_type, item.graph_key)
        assert await _count_entity_uuid(ctx.driver, expected) == 1
    for item in request.edges:
        expected = catalog_edge_uuid(FIXED_NS, GROUP, item.edge_type, item.edge_key)
        assert await _count_edge_uuid(ctx.driver, expected) == 1
    assert await _count_group_nodes(ctx.driver) == len(request.entities) + 2
    assert await _count_group_edges(ctx.driver) == len(request.edges) + len(
        request.provenance.entity_targets
    )


async def test_accept_tab_missing_endpoint_batch_has_no_partial_domain_write(catalog_client):
    ctx = catalog_client
    good = _accept_tab_request()
    missing = good.edges[1].model_copy(
        update={
            'target_graph_key': 'TABLE::APP.MISSING_PARENT',
            'edge_key': 'FK::APP.ACCEPT_TAB.ACCEPT_ID->APP.MISSING_PARENT.ACCEPT_ID',
        }
    )
    request = good.model_copy(
        update={
            'batch_id': 'accept-tab-missing-endpoint',
            'entities': good.entities[:2],
            'edges': [good.edges[0], missing],
            'provenance': None,
        }
    )
    before = await _snapshot_group_elements(ctx.driver)
    response = await ctx.service.upsert_catalog_batch(client=ctx.client, request=request)

    assert response.status == 'failed'
    assert response.error_code == CatalogErrorCode.missing_endpoint
    assert await _snapshot_group_elements(ctx.driver) == before


async def test_accept_tab_real_transaction_failure_rolls_back_and_persists_failed_status(
    catalog_client, monkeypatch
):
    ctx = catalog_client
    request = _accept_tab_request(batch_id='accept-tab-injected-failure')
    original = ctx.service._store.upsert_edge_item
    calls = 0

    async def _fail_first_edge(tx, *, params):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('synthetic injected failure')
        return await original(tx, params=params)

    monkeypatch.setattr(ctx.service._store, 'upsert_edge_item', _fail_first_edge)
    response = await ctx.service.upsert_catalog_batch(client=ctx.client, request=request)

    assert response.status == 'failed'
    assert response.error_code == CatalogErrorCode.neo4j_transaction_failed
    for item in request.entities:
        expected = catalog_entity_uuid(FIXED_NS, GROUP, item.entity_type, item.graph_key)
        assert await _count_entity_uuid(ctx.driver, expected) == 0
    for item in request.edges:
        expected = catalog_edge_uuid(FIXED_NS, GROUP, item.edge_type, item.edge_key)
        assert await _count_edge_uuid(ctx.driver, expected) == 0

    restarted = CatalogService(catalog_config=_enabled_config())
    status = await restarted.get_catalog_ingest_status(
        client=ctx.client,
        request=GetCatalogIngestStatusRequest(group_id=GROUP, batch_id=request.batch_id),
    )
    assert status.status == 'failed'
    assert status.error_summary == 'RuntimeError'


# ---------------------------------------------------------------------------
# Task 1: happy path
# ---------------------------------------------------------------------------


async def test_gate_required_mode_documents_live_driver(neo4j_driver):
    """CATALOG_INT_REQUIRED=1 requires a live Neo4jDriver fixture (fail-not-skip)."""
    assert callable(_catalog_int_required)
    assert _catalog_int_required() is True or _catalog_int_required() is False
    # Fixture yields a real driver; required mode never green without it.
    assert neo4j_driver is not None
    assert hasattr(neo4j_driver, 'execute_query')
    if _catalog_int_required():
        assert os.environ.get('CATALOG_INT_REQUIRED') in ('1', 'true', 'TRUE', 'yes')


async def test_happy_path_six_entities_and_six_edges(catalog_client):
    ctx = catalog_client
    seeded = await _seed_happy_graph(ctx)
    assert await _count_group_nodes(ctx.driver) >= 8  # 6 + doc + departments
    assert await _count_group_edges(ctx.driver) == 6

    # Product schema after first real write: exact composite identity shapes.
    show = await ctx.driver.execute_query(
        """
        SHOW CONSTRAINTS
        YIELD name, type, entityType, labelsOrTypes, properties
        RETURN name, type, entityType, labelsOrTypes, properties
        """,
        params={},
    )
    rows = list(show[0] or [])
    by_name = {str(r['name']): r for r in rows}
    expected_constraints = {
        'catalog_entity_identity_unique': ('NODE', 'Entity'),
        'catalog_relates_to_identity_unique': ('RELATIONSHIP', 'RELATES_TO'),
        'catalog_episodic_identity_unique': ('NODE', 'Episodic'),
        'catalog_mentions_identity_unique': ('RELATIONSHIP', 'MENTIONS'),
        'catalog_batch_identity_unique': ('NODE', 'CatalogIngestBatch'),
    }
    for name, (entity_type, label) in expected_constraints.items():
        constraint = by_name.get(name)
        assert constraint is not None, f'product composite UNIQUE missing: {name}'
        assert (
            'UNIQUENESS' in str(constraint['type']).upper()
            or 'UNIQUE' in str(constraint['type']).upper()
        )
        assert str(constraint['entityType']).upper() == entity_type
        assert label in list(constraint['labelsOrTypes'] or [])
        assert set(constraint['properties'] or []) == {'uuid', 'group_id'}

    # Exact labels Entity + custom type for each of six core types
    for item, result in zip(
        seeded['entities'][:6], seeded['entity_resp'].results[:6], strict=False
    ):
        assert result.status == 'created'
        assert result.uuid
        row = await _fetch_entity(ctx.driver, result.uuid)
        assert row is not None
        labels = set(row['labels'])
        assert labels == {'Entity', item.entity_type}
        assert row['create_token'] is None  # create-token absent after write
        assert row['has_emb'] is True
        assert row['name_raw'] == item.name_raw
        assert row['name_canonical'] == item.name_canonical
        assert row['graph_key'] == item.graph_key
        assert row['name'] == item.graph_key


async def test_resolve_and_verify_found(catalog_client):
    ctx = catalog_client
    seeded = await _seed_happy_graph(ctx)
    refs = [
        ResolveEntityRef(entity_type=e.entity_type, graph_key=e.graph_key)
        for e in seeded['entities'][:6]
    ]
    rresp = await ctx.service.resolve_typed_entities(
        client=ctx.client,
        request=ResolveTypedEntitiesRequest(group_id=GROUP, entities=refs),
    )
    assert all(r.found for r in rresp.results), [r.model_dump() for r in rresp.results]

    vresp = await ctx.service.verify_catalog_batch(
        client=ctx.client,
        request=VerifyCatalogBatchRequest(
            group_id=GROUP,
            batch_id=BATCH,
            entities=[
                VerifyEntityRef(entity_type=e.entity_type, graph_key=e.graph_key)
                for e in seeded['entities'][:6]
            ],
            edges=[
                VerifyEdgeRef(edge_type=e.edge_type, edge_key=e.edge_key) for e in seeded['edges']
            ],
        ),
    )
    assert vresp.entities.expected == 6
    assert vresp.entities.found == 6
    assert vresp.entities.missing == []
    assert vresp.entities.wrong_type == []
    assert vresp.entities.generic_duplicate == []
    assert vresp.entities.typed_duplicate == []
    assert vresp.entities.uuid_mismatch == []
    assert vresp.entities.missing_embedding == []
    assert vresp.edges.expected == len(seeded['edges'])
    assert vresp.edges.found == len(seeded['edges'])
    assert vresp.edges.missing == []
    assert vresp.edges.duplicate_edge_key == []
    assert vresp.edges.edge_type_mismatch == []
    assert vresp.edges.endpoint_mismatch == []
    assert vresp.edges.uuid_mismatch == []
    assert vresp.edges.missing_embedding == []
    assert vresp.missing == []
    assert vresp.anomalies == []


async def test_verify_typed_entity_twin_anomalies_are_not_hidden(catalog_client):
    ctx = catalog_client
    entity = _six_entities()[2]
    response = await _upsert_entities(ctx, [entity])
    expected_uuid = response.results[0].uuid
    assert expected_uuid
    await ctx.driver.execute_query(
        """
        CREATE (n:Entity:Table {
          uuid: $rogue_uuid,
          group_id: $g,
          name: $key,
          graph_key: $key,
          batch_id: $batch_id
        })
        """,
        params={
            'rogue_uuid': str(uuid.uuid4()),
            'g': GROUP,
            'key': entity.graph_key,
            'batch_id': BATCH,
        },
    )
    resp = await ctx.service.verify_catalog_batch(
        client=ctx.client,
        request=VerifyCatalogBatchRequest(
            group_id=GROUP,
            entities=[VerifyEntityRef(entity_type='Table', graph_key=entity.graph_key)],
        ),
    )
    assert resp.entities.found == 1
    assert resp.entities.typed_duplicate == [entity.graph_key]
    assert resp.entities.uuid_mismatch == [entity.graph_key]
    assert resp.entities.missing_embedding == [entity.graph_key]


async def test_resolve_mixed_twin_anomalies_are_not_hidden(catalog_client):
    ctx = catalog_client
    entity = _six_entities()[2]
    response = await _upsert_entities(ctx, [entity])
    expected_uuid = response.results[0].uuid
    assert expected_uuid
    await ctx.driver.execute_query(
        """
        CREATE (n:Entity:Table {
          uuid: $rogue_uuid,
          group_id: $g,
          name: $key,
          graph_key: $key,
          batch_id: $batch_id
        })
        CREATE (w:Entity:View {
          uuid: $wrong_uuid,
          group_id: $g,
          name: $key,
          graph_key: $key,
          batch_id: $batch_id
        })
        """,
        params={
            'rogue_uuid': str(uuid.uuid4()),
            'wrong_uuid': str(uuid.uuid4()),
            'g': GROUP,
            'key': entity.graph_key,
            'batch_id': BATCH,
        },
    )
    resp = await ctx.service.resolve_typed_entities(
        client=ctx.client,
        request=ResolveTypedEntitiesRequest(
            group_id=GROUP,
            entities=[ResolveEntityRef(entity_type='Table', graph_key=entity.graph_key)],
        ),
    )
    r0 = resp.results[0]
    assert r0.found is True
    assert r0.status == 'found'
    assert r0.uuid == expected_uuid
    assert 'typed_duplicate' in r0.anomalies
    assert 'uuid_mismatch' in r0.anomalies
    assert 'missing_embedding' in r0.anomalies
    assert 'wrong_type' in r0.anomalies


async def test_verify_wrong_type_sibling_with_typed_present_live(catalog_client):
    ctx = catalog_client
    entity = _six_entities()[2]
    response = await _upsert_entities(ctx, [entity])
    assert response.results[0].uuid
    await ctx.driver.execute_query(
        """
        CREATE (w:Entity:View {
          uuid: $wrong_uuid,
          group_id: $g,
          name: $key,
          graph_key: $key,
          batch_id: $batch_id
        })
        """,
        params={
            'wrong_uuid': str(uuid.uuid4()),
            'g': GROUP,
            'key': entity.graph_key,
            'batch_id': BATCH,
        },
    )
    resp = await ctx.service.verify_catalog_batch(
        client=ctx.client,
        request=VerifyCatalogBatchRequest(
            group_id=GROUP,
            entities=[VerifyEntityRef(entity_type='Table', graph_key=entity.graph_key)],
        ),
    )
    assert resp.entities.found == 1
    assert entity.graph_key in resp.entities.wrong_type


async def test_verify_physical_duplicate_edge_is_preserved_and_reported(catalog_client):
    ctx = catalog_client
    await _upsert_entities(ctx, [_six_entities()[1], _six_entities()[2]])
    edge = _structural_and_fk_edges()[0]
    edge_resp = await _upsert_edges(ctx, [edge], batch_id='verify-duplicate-live')
    assert edge_resp.created == 1
    expected_uuid = edge_resp.results[0].uuid
    assert expected_uuid

    await ctx.driver.execute_query(
        """
        MATCH (s:Entity {group_id: $g, graph_key: $source_key})
        MATCH (t:Entity {group_id: $g, graph_key: $target_key})
        CREATE (s)-[:RELATES_TO {
          uuid: $rogue_uuid,
          group_id: $g,
          edge_key: $edge_key,
          name: '',
          batch_id: $batch_id
        }]->(t)
        """,
        params={
            'g': GROUP,
            'source_key': edge.source_graph_key,
            'target_key': edge.target_graph_key,
            'rogue_uuid': str(uuid.uuid4()),
            'edge_key': edge.edge_key,
            'batch_id': 'verify-duplicate-live',
        },
    )
    resp = await ctx.service.verify_catalog_batch(
        client=ctx.client,
        request=VerifyCatalogBatchRequest(
            group_id=GROUP,
            batch_id='verify-duplicate-live',
            edges=[VerifyEdgeRef(edge_type=edge.edge_type, edge_key=edge.edge_key)],
        ),
    )
    assert resp.edges.found == 1
    assert resp.edges.duplicate_edge_key == [edge.edge_key]
    assert resp.edges.uuid_mismatch == [edge.edge_key]
    assert resp.edges.edge_type_mismatch == [edge.edge_key]
    assert resp.edges.missing_embedding == [edge.edge_key]


async def test_provenance_presence_missing_target_is_group_scoped(catalog_client):
    ctx = catalog_client
    target_uuid = str(uuid.uuid4())

    before = await _snapshot_group_elements(ctx.driver)
    rows = await ctx.service._store.match_provenance_presence(
        ctx.driver, group_id=GROUP, target_uuids=[target_uuid]
    )

    assert rows == [{'uuid': target_uuid, 'has_provenance': False}]
    assert await _snapshot_group_elements(ctx.driver) == before


async def test_verify_edge_endpoint_and_type_mismatch_live(catalog_client):
    ctx = catalog_client
    await _upsert_entities(ctx, [_six_entities()[1], _six_entities()[2]])
    edge = _structural_and_fk_edges()[0]
    edge_resp = await _upsert_edges(ctx, [edge], batch_id='verify-edge-live')
    assert edge_resp.created == 1

    endpoint_resp = await ctx.service.verify_catalog_batch(
        client=ctx.client,
        request=VerifyCatalogBatchRequest(
            group_id=GROUP,
            edges=[
                VerifyEdgeRef(
                    edge_type=edge.edge_type,
                    edge_key=edge.edge_key,
                    expected_source_graph_key='SCHEMA::WRONG',
                )
            ],
        ),
    )
    assert endpoint_resp.edges.endpoint_mismatch == [edge.edge_key]
    assert endpoint_resp.edges.edge_type_mismatch == []

    type_resp = await ctx.service.verify_catalog_batch(
        client=ctx.client,
        request=VerifyCatalogBatchRequest(
            group_id=GROUP,
            edges=[VerifyEdgeRef(edge_type='DependsOn', edge_key=edge.edge_key)],
        ),
    )
    assert type_resp.edges.edge_type_mismatch == [edge.edge_key]
    assert type_resp.edges.endpoint_mismatch == []


async def test_search_nodes_and_memory_facts_interop(catalog_client):
    """BATC-11 via existing graphiti search APIs (not a new search engine)."""
    ctx = catalog_client
    request, committed = await _upsert_accept_tab(ctx)
    assert committed.status == 'committed'

    from graphiti_core.cross_encoder.client import CrossEncoderClient
    from graphiti_core.embedder.client import EmbedderClient
    from graphiti_core.graphiti_types import GraphitiClients
    from graphiti_core.llm_client.client import LLMClient
    from graphiti_core.search.search import search
    from graphiti_core.search.search_config_recipes import (
        EDGE_HYBRID_SEARCH_RRF,
        NODE_HYBRID_SEARCH_RRF,
    )
    from graphiti_core.search.search_filters import SearchFilters
    from graphiti_core.tracer import NoOpTracer

    class _Emb(EmbedderClient):
        async def create(self, input_data: Any = None, **kwargs: Any) -> list[float]:
            assert input_data is None or input_data is not None
            assert isinstance(kwargs, dict)
            return [0.01] * EMBED_DIM

        async def create_batch(self, input_data_list: list[Any] | None = None) -> list[list[float]]:
            items = input_data_list or []
            assert isinstance(items, list)
            return [[0.01] * EMBED_DIM for _ in items]

    class _LLM(LLMClient):
        def __init__(self) -> None:
            # Avoid parent network config requirements where possible
            pass

        async def _generate_response(self, *args: Any, **kwargs: Any) -> Any:
            assert args is not None
            assert isinstance(kwargs, dict)
            raise AssertionError('no LLM')

        async def generate_response(self, *args: Any, **kwargs: Any) -> Any:
            assert args is not None
            assert isinstance(kwargs, dict)
            raise AssertionError('no LLM')

    class _CE(CrossEncoderClient):
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            assert isinstance(query, str)
            assert isinstance(passages, list)
            return [(p, 0.0) for p in passages]

    # Build clients bundle carefully — use model_construct if needed
    try:
        clients = GraphitiClients(
            driver=ctx.driver,
            llm_client=_LLM(),  # type: ignore[arg-type]
            embedder=_Emb(),  # type: ignore[arg-type]
            cross_encoder=_CE(),  # type: ignore[arg-type]
            tracer=NoOpTracer(),
        )
    except Exception:
        clients = GraphitiClients.model_construct(
            driver=ctx.driver,
            llm_client=ctx.llm,
            embedder=ctx.embedder,
            cross_encoder=_CE(),
            tracer=NoOpTracer(),
        )

    node_results = await search(
        clients,
        'ACCEPT_TAB',
        [GROUP],
        NODE_HYBRID_SEARCH_RRF,
        SearchFilters(node_labels=['Table']),
    )
    node_names = {
        getattr(n, 'name', None) or getattr(n, 'uuid', None) for n in (node_results.nodes or [])
    }
    assert any(n and 'ACCEPT_TAB' in str(n) for n in node_names), (
        f'BATC-11: search_nodes path returned no ACCEPT_TAB; got {node_names!r}'
    )

    expected_batch_uuid = catalog_batch_uuid(FIXED_NS, GROUP, request.batch_id)
    assert all(getattr(n, 'uuid', None) != expected_batch_uuid for n in node_results.nodes or [])
    batch_labels = await ctx.driver.execute_query(
        'MATCH (b:CatalogIngestBatch {uuid: $u, group_id: $g}) RETURN labels(b) AS labels',
        params={'u': expected_batch_uuid, 'g': GROUP},
    )
    assert batch_labels[0][0]['labels'] == ['CatalogIngestBatch']

    edge_results = await search(
        clients,
        'ACCEPT_TAB contains ACCEPT_ID',
        [GROUP],
        EDGE_HYBRID_SEARCH_RRF,
        SearchFilters(edge_types=None),
    )
    facts = [getattr(e, 'fact', None) for e in (edge_results.edges or [])]
    assert any(f and 'ACCEPT_ID' in f for f in facts), (
        f'BATC-11: search_memory_facts path returned no ACCEPT_ID fact; got {facts!r}'
    )
    assert request.provenance is not None
    expected_source = catalog_source_uuid(FIXED_NS, GROUP, request.provenance.sources[0].source_key)
    matching_edges = [
        edge
        for edge in edge_results.edges or []
        if getattr(edge, 'uuid', None)
        == catalog_edge_uuid(
            FIXED_NS,
            GROUP,
            request.edges[0].edge_type,
            request.edges[0].edge_key,
        )
    ]
    assert matching_edges
    assert expected_source in matching_edges[0].episodes


# ---------------------------------------------------------------------------
# Task 2: conflicts, retry, concurrency, rollback, isolation
# ---------------------------------------------------------------------------


async def test_identical_retry_unchanged_preserves_storage(catalog_client):
    ctx = catalog_client
    entity = _six_entities()[2]  # Table
    r1 = await _upsert_entities(ctx, [entity], batch_id='b-create')
    assert r1.results[0].status == 'created'
    u = r1.results[0].uuid
    assert u
    before = await _fetch_entity(ctx.driver, u)
    assert before is not None
    created_at = before['created_at']

    r2 = await _upsert_entities(ctx, [entity], batch_id='b-retry')
    assert r2.results[0].status == 'unchanged'
    assert r2.unchanged == 1
    after = await _fetch_entity(ctx.driver, u)
    assert after is not None
    assert after['batch_id'] == 'b-create'  # unchanged leaves batch_id
    assert after['created_at'] == created_at
    assert after['name_raw'] == entity.name_raw
    assert after['name_canonical'] == entity.name_canonical
    assert after['create_token'] is None


async def test_update_changes_summary_preserves_identity_names(catalog_client):
    ctx = catalog_client
    entity = _six_entities()[2]
    r1 = await _upsert_entities(ctx, [entity], batch_id='b1')
    u = r1.results[0].uuid
    assert u
    before = await _fetch_entity(ctx.driver, u)
    assert before is not None
    before_created_at = before['created_at']
    updated = _entity(
        entity.entity_type,
        entity.graph_key,
        entity.name_raw,
        entity.name_canonical,
        entity.database_qualified_name,
        'Changed employee summary',
    )
    r2 = await _upsert_entities(ctx, [updated], batch_id='b2')
    assert r2.results[0].status == 'updated'
    after = await _fetch_entity(ctx.driver, u)
    assert after is not None
    assert after['summary'] == 'Changed employee summary'
    assert after['name_raw'] == entity.name_raw
    assert after['name_canonical'] == entity.name_canonical
    assert after['graph_key'] == entity.graph_key
    assert after['created_at'] == before_created_at
    assert after['batch_id'] == 'b2'


async def test_name_raw_canonical_in_hash_identity_stable(catalog_client):
    """Changed name_raw/name_canonical same graph_key → deterministic_uuid_conflict; originals preserved."""
    ctx = catalog_client
    e1 = _entity('Table', 'TABLE::HR.T', 'T', 't', 'HR.T', 'table t')
    r1 = await _upsert_entities(ctx, [e1])
    u = r1.results[0].uuid
    assert u
    before = await _fetch_entity(ctx.driver, u)
    assert before is not None
    before_hash = before['content_sha256']
    before_batch = before['batch_id']
    e2 = _entity('Table', 'TABLE::HR.T', 'T_RAW', 't_raw', 'HR.T', 'table t')
    r2 = await _upsert_entities(ctx, [e2], batch_id='b-name')
    assert any(r.error_code == CatalogErrorCode.deterministic_uuid_conflict for r in r2.results)
    after = await _fetch_entity(ctx.driver, u)
    assert after is not None
    # Identity props and content hash/batch never rewritten on conflict
    assert after['name_raw'] == 'T'
    assert after['name_canonical'] == 't'
    assert after['content_sha256'] == before_hash
    assert after['batch_id'] == before_batch


async def test_wrong_graph_key_is_different_identity(catalog_client):
    ctx = catalog_client
    e1 = _entity('Table', 'TABLE::HR.A', 'A', 'a', 'HR.A', 'a')
    e2 = _entity('Table', 'TABLE::HR.B', 'A', 'a', 'HR.A', 'a')  # same names, different key
    r = await _upsert_entities(ctx, [e1, e2])
    assert r.created == 2
    assert r.results[0].uuid != r.results[1].uuid


async def test_content_hash_mismatch_no_write(catalog_client):
    ctx = catalog_client
    entity = _six_entities()[2]
    bad = entity.model_copy(update={'content_sha256': 'a' * 64})
    resp = await _upsert_entities(ctx, [bad])
    assert any(r.error_code == CatalogErrorCode.content_hash_mismatch for r in resp.results)
    assert await _count_group_nodes(ctx.driver) == 0


async def test_entity_type_conflict_leaves_graph_unchanged(catalog_client):
    ctx = catalog_client
    table = _six_entities()[2]
    r1 = await _upsert_entities(ctx, [table])
    u = r1.results[0].uuid
    assert u
    # Same uuid5 identity for Table graph_key cannot become View — different entity_type
    # changes identity. Conflict: plant View label on same uuid via raw write then upsert Table.
    await ctx.driver.execute_query(
        """
        MATCH (n:Entity {uuid: $u})
        WHERE n.group_id = $g
        REMOVE n:Table
        SET n:View
        """,
        params={'u': u, 'g': GROUP},
    )
    before = await _fetch_entity(ctx.driver, u)
    assert before is not None
    before_summary = before['summary']
    resp = await _upsert_entities(ctx, [table], batch_id='conflict-b')
    assert any(r.error_code == CatalogErrorCode.entity_type_conflict for r in resp.results)
    after = await _fetch_entity(ctx.driver, u)
    assert after is not None
    assert set(after['labels']) == {'Entity', 'View'}
    assert after['summary'] == before_summary


async def test_missing_endpoint_and_type_and_generic(catalog_client):
    ctx = catalog_client
    # Only source exists
    src = _six_entities()[2]
    await _upsert_entities(ctx, [src])

    missing = _edge(
        'ForeignKeyTo',
        'FK::missing',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.NOPE',
        'Table',
        'missing target',
    )
    r_miss = await _upsert_edges(ctx, [missing], batch_id='e-miss')
    assert any(r.error_code == CatalogErrorCode.missing_endpoint for r in r_miss.results)
    assert await _count_group_edges(ctx.driver) == 0

    # Wrong type endpoint
    wrong_name = 'TABLE::HR.WRONGTYPE'
    await _seed_wrong_type_entity(ctx.driver, wrong_name, 'View')
    wrong = _edge(
        'ForeignKeyTo',
        'FK::wrongtype',
        'TABLE::HR.EMPLOYEES',
        'Table',
        wrong_name,
        'Table',
        'wrong type target',
    )
    r_wrong = await _upsert_edges(ctx, [wrong], batch_id='e-wrong')
    assert any(r.error_code == CatalogErrorCode.endpoint_type_mismatch for r in r_wrong.results)

    # Generic endpoint
    gen_name = 'TABLE::HR.GENERIC'
    await _seed_generic_entity(ctx.driver, gen_name)
    gen = _edge(
        'ForeignKeyTo',
        'FK::generic',
        'TABLE::HR.EMPLOYEES',
        'Table',
        gen_name,
        'Table',
        'generic target',
    )
    r_gen = await _upsert_edges(ctx, [gen], batch_id='e-gen')
    assert any(r.error_code == CatalogErrorCode.generic_endpoint_conflict for r in r_gen.results)
    assert await _count_group_edges(ctx.driver) == 0


async def test_typed_duplicate_endpoint_does_not_bind_wrong_uuid(catalog_client):
    """Typed endpoint bind prefers expected UUIDv5; wrong-only / multi-typed never arbitrary-bind."""
    ctx = catalog_client
    # Source only — target is not product-created.
    await _upsert_entities(ctx, [_six_entities()[2]])
    target_key = 'TABLE::HR.DEPARTMENTS'
    expected_tgt = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', target_key)

    # Case 1: single exact-typed row with non-deterministic uuid → conflict, no edge.
    decoy_uuid = str(uuid.uuid4())
    await ctx.driver.execute_query(
        """
        CREATE (n:Entity:Table {
            uuid: $u,
            group_id: $g,
            name: $name,
            graph_key: $name,
            name_raw: 'DEPARTMENTS',
            name_canonical: 'departments',
            content_sha256: $h
        })
        """,
        params={'u': decoy_uuid, 'g': GROUP, 'name': target_key, 'h': 'c' * 64},
    )
    edge = _edge(
        'ForeignKeyTo',
        'FK::decoy-wrong-only',
        'TABLE::HR.EMPLOYEES',
        'Table',
        target_key,
        'Table',
        'must not bind non-deterministic typed uuid',
    )
    r1 = await _upsert_edges(ctx, [edge], batch_id='e-decoy1')
    assert r1.results[0].status == 'error'
    assert r1.results[0].error_code == CatalogErrorCode.deterministic_uuid_conflict
    assert await _count_group_edges(ctx.driver) == 0

    # Case 2: expected UUIDv5 typed row + corrupt typed twin → bind only expected uuid.
    await _upsert_entities(ctx, [_extra_table()])
    decoy2 = str(uuid.uuid4())
    await ctx.driver.execute_query(
        """
        CREATE (n:Entity:Table {
            uuid: $u,
            group_id: $g,
            name: $name,
            graph_key: $name,
            name_raw: 'DEPARTMENTS',
            name_canonical: 'departments',
            content_sha256: $h
        })
        """,
        params={'u': decoy2, 'g': GROUP, 'name': target_key, 'h': 'd' * 64},
    )
    edge2 = _edge(
        'ForeignKeyTo',
        'FK::decoy-with-expected',
        'TABLE::HR.EMPLOYEES',
        'Table',
        target_key,
        'Table',
        'must bind expected deterministic uuid not twin',
    )
    r2 = await _upsert_edges(ctx, [edge2], batch_id='e-decoy2')
    assert r2.results[0].status == 'created'
    eu = r2.results[0].uuid
    assert eu
    row = await ctx.driver.execute_query(
        """
        MATCH (s:Entity)-[e:RELATES_TO {uuid: $u}]->(t:Entity)
        WHERE e.group_id = $g
        RETURN t.uuid AS tu, labels(t) AS tl
        """,
        params={'u': eu, 'g': GROUP},
    )
    rec = row[0][0]
    assert rec['tu'] == expected_tgt
    assert set(rec['tl']) == {'Entity', 'Table'}


async def test_edge_identity_conflict(catalog_client):
    ctx = catalog_client
    await _upsert_entities(ctx, [_six_entities()[2], _extra_table()])
    e = _edge(
        'ForeignKeyTo',
        'FK::ident',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.DEPARTMENTS',
        'Table',
        'original fact',
    )
    r1 = await _upsert_edges(ctx, [e], batch_id='e1')
    assert r1.results[0].status == 'created'
    eu = r1.results[0].uuid
    # Corrupt identity fields on same uuid
    await ctx.driver.execute_query(
        """
        MATCH ()-[e:RELATES_TO {uuid: $u}]->()
        WHERE e.group_id = $g
        SET e.name = 'Contains', e.edge_key = 'OTHER'
        """,
        params={'u': eu, 'g': GROUP},
    )
    r2 = await _upsert_edges(ctx, [e], batch_id='e2')
    assert any(r.error_code == CatalogErrorCode.edge_identity_conflict for r in r2.results)
    # Original corrupted row still present once (no second edge)
    assert await _count_edge_uuid(ctx.driver, eu) == 1


async def test_concurrent_identical_entity_one_node(catalog_client):
    """ENTY-12: concurrent identical upserts → one logical node."""
    ctx = catalog_client
    entity = _six_entities()[2]
    ent_uuid = catalog_entity_uuid(FIXED_NS, GROUP, entity.entity_type, entity.graph_key)

    async def _once(i: int):
        # Separate service instances, shared driver
        svc = CatalogService(catalog_config=_enabled_config(), queue_service=RecordingQueue())
        client = SimpleNamespace(
            driver=ctx.driver, embedder=FakeEmbedder(), llm_client=RecordingLLM()
        )
        req = UpsertTypedEntitiesRequest(
            group_id=GROUP,
            batch_id=f'conc-e-{i}',
            entities=[entity],
            atomic=True,
        )
        return await svc.upsert_typed_entities(client=client, request=req)

    results = await asyncio.gather(*[_once(i) for i in range(8)])
    statuses = [r.results[0].status for r in results]
    assert all(s in ('created', 'updated', 'unchanged') for s in statuses), statuses
    assert await _count_entity_uuid(ctx.driver, ent_uuid) == 1
    assert await _count_group_nodes(ctx.driver) == 1


async def test_concurrent_identical_edge_one_rel(catalog_client):
    """EDGE-11: concurrent identical edge upserts → one relationship."""
    ctx = catalog_client
    await _upsert_entities(ctx, [_six_entities()[2], _extra_table()])
    edge = _edge(
        'ForeignKeyTo',
        'FK::conc',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.DEPARTMENTS',
        'Table',
        'concurrent fk',
    )
    e_uuid = catalog_edge_uuid(FIXED_NS, GROUP, edge.edge_type, edge.edge_key)

    async def _once(i: int):
        svc = CatalogService(catalog_config=_enabled_config(), queue_service=RecordingQueue())
        client = SimpleNamespace(
            driver=ctx.driver, embedder=FakeEmbedder(), llm_client=RecordingLLM()
        )
        req = UpsertTypedEdgesRequest(
            group_id=GROUP,
            batch_id=f'conc-ed-{i}',
            edges=[edge],
            atomic=True,
        )
        return await svc.upsert_typed_edges(client=client, request=req)

    results = await asyncio.gather(*[_once(i) for i in range(8)])
    statuses = [r.results[0].status for r in results]
    assert all(s in ('created', 'updated', 'unchanged') for s in statuses), statuses
    assert await _count_edge_uuid(ctx.driver, e_uuid) == 1


async def test_atomic_entity_rollback(catalog_client):
    ctx = catalog_client
    good = _entity('Table', 'TABLE::HR.GOOD', 'GOOD', 'good', 'HR.GOOD', 'good table')
    # Canonical payload must be hashable (sanity before atomic conflict path).
    payload = CatalogService.entity_canonical_payload(good)
    assert payload['graph_key'] == good.graph_key
    assert payload['entity_type'] == 'Table'
    # Force second conflict with pre-seeded wrong type on second identity
    bad = _entity('Table', 'TABLE::HR.BAD', 'BAD', 'bad', 'HR.BAD', 'bad table')
    bad_uuid = catalog_entity_uuid(FIXED_NS, GROUP, bad.entity_type, bad.graph_key)
    await ctx.driver.execute_query(
        """
        CREATE (n:Entity:View {
            uuid: $u,
            group_id: $g,
            name: $name,
            graph_key: $name,
            content_sha256: $h
        })
        """,
        params={'u': bad_uuid, 'g': GROUP, 'name': bad.graph_key, 'h': 'f' * 64},
    )
    # Pre-existing wrong type will error; atomic should roll back sibling create
    resp = await _upsert_entities(ctx, [good, bad], atomic=True, batch_id='atomic-rb')
    assert resp.failed >= 1
    assert any(r.status == 'rolled_back' for r in resp.results) or any(
        r.error_code == CatalogErrorCode.entity_type_conflict for r in resp.results
    )
    # good must not remain if atomic and conflict detected before/during write
    good_uuid = catalog_entity_uuid(FIXED_NS, GROUP, good.entity_type, good.graph_key)
    # If conflict was pre-tx, good never written; if mid-tx, rolled back
    assert await _count_entity_uuid(ctx.driver, good_uuid) == 0


async def test_atomic_edge_rollback(catalog_client):
    ctx = catalog_client
    await _upsert_entities(
        ctx,
        [
            _six_entities()[2],
            _extra_table(),
            _extra_table('TABLE::HR.LOCATIONS'),
        ],
    )
    ok = _edge(
        'ForeignKeyTo',
        'FK::ok',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.DEPARTMENTS',
        'Table',
        'ok fk',
    )
    bad = _edge(
        'ForeignKeyTo',
        'FK::bad',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.MISSING',
        'Table',
        'bad fk',
    )
    resp = await _upsert_edges(ctx, [ok, bad], atomic=True, batch_id='atomic-edge-rb')
    assert resp.failed >= 1
    assert any(r.error_code == CatalogErrorCode.missing_endpoint for r in resp.results)
    ok_uuid = catalog_edge_uuid(FIXED_NS, GROUP, ok.edge_type, ok.edge_key)
    assert await _count_edge_uuid(ctx.driver, ok_uuid) == 0


async def test_batch_no_llm_queue_or_implicit_community_calls(catalog_client):
    ctx = catalog_client
    _, response = await _upsert_accept_tab(ctx)
    assert response.status == 'committed'
    ctx.llm.generate_response.assert_not_called()
    ctx.queue.add_episode.assert_not_called()
    ctx.queue.enqueue.assert_not_called()
    ctx.queue.add.assert_not_called()
    assert ctx.llm.calls == 0
    assert not hasattr(ctx.service, 'build_communities')


async def test_explicit_community_build_accepts_batch_entities(catalog_client):
    ctx = catalog_client
    _, response = await _upsert_accept_tab(ctx)
    assert response.status == 'committed'

    from graphiti_core.utils.maintenance.community_operations import build_communities

    llm = CommunityLLM()
    community_nodes, community_edges = await build_communities(
        ctx.driver,
        llm,  # type: ignore[arg-type]
        [GROUP],
    )
    assert community_nodes
    assert community_edges
    assert llm.calls > 0
    assert all(node.group_id == GROUP for node in community_nodes)
    assert all(edge.group_id == GROUP for edge in community_edges)


async def test_teardown_scoped_and_fixture_never_calls_clear_graph(catalog_client):
    """Fixture contract: deletes exact created elementIds; never clears a group."""
    ctx = catalog_client
    before_nodes, before_edges = await _snapshot_group_elements(ctx.driver)
    await _upsert_entities(ctx, [_six_entities()[0]])
    assert (await _snapshot_group_elements(ctx.driver))[0] > before_nodes
    await _teardown_created_elements(ctx.driver, before_nodes, before_edges)
    assert await _snapshot_group_elements(ctx.driver) == (before_nodes, before_edges)

    tree = ast.parse(Path(__file__).read_text(encoding='utf-8'))
    clear_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id == 'clear_graph'
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == 'clear_graph'
        )
    ]
    assert clear_calls == []
    broad_delete = 'MATCH (n) WHERE n.group_id = $g DETACH ' + 'DELETE n'
    assert broad_delete not in Path(__file__).read_text(encoding='utf-8')
    assert FORBIDDEN_GROUP == 'oracle-catalog-v2'


async def test_two_fk_edges_distinct_keys_same_endpoints(catalog_client):
    """EDGE-08: two ForeignKeyTo same endpoints different edge_key."""
    ctx = catalog_client
    await _upsert_entities(ctx, [_six_entities()[2], _extra_table()])
    e1, e2 = _structural_and_fk_edges()[4], _structural_and_fk_edges()[5]
    resp = await _upsert_edges(ctx, [e1, e2])
    assert resp.created == 2
    u1 = catalog_edge_uuid(FIXED_NS, GROUP, e1.edge_type, e1.edge_key)
    u2 = catalog_edge_uuid(FIXED_NS, GROUP, e2.edge_type, e2.edge_key)
    assert u1 != u2
    assert await _count_edge_uuid(ctx.driver, u1) == 1
    assert await _count_edge_uuid(ctx.driver, u2) == 1


async def test_edge_update_heals_null_episodes_for_search(catalog_client):
    """Updated path sets e.episodes=[] so pre-fix null episodes become searchable."""
    ctx = catalog_client
    await _upsert_entities(ctx, [_six_entities()[2], _extra_table()])
    edge = _edge(
        'ForeignKeyTo',
        'FK::null-episodes-heal',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.DEPARTMENTS',
        'Table',
        'employees.dept_id references departments.dept_id original',
    )
    r1 = await _upsert_edges(ctx, [edge], batch_id='ep-create')
    assert r1.results[0].status == 'created'
    eu = r1.results[0].uuid
    assert eu

    # Plant legacy null episodes on matching deterministic RELATES_TO.
    await ctx.driver.execute_query(
        """
        MATCH ()-[e:RELATES_TO {uuid: $u}]->()
        WHERE e.group_id = $g
        SET e.episodes = null
        """,
        params={'u': eu, 'g': GROUP},
    )
    planted = await ctx.driver.execute_query(
        """
        MATCH ()-[e:RELATES_TO {uuid: $u}]->()
        WHERE e.group_id = $g
        RETURN e.episodes AS episodes
        """,
        params={'u': eu, 'g': GROUP},
    )
    assert planted[0][0]['episodes'] is None

    # Content change forces status=updated (not unchanged zero-mutation).
    updated = _edge(
        'ForeignKeyTo',
        'FK::null-episodes-heal',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.DEPARTMENTS',
        'Table',
        'employees.dept_id references departments.dept_id healed',
    )
    r2 = await _upsert_edges(ctx, [updated], batch_id='ep-update')
    assert r2.results[0].status == 'updated'
    assert r2.results[0].uuid == eu

    stored = await ctx.driver.execute_query(
        """
        MATCH ()-[e:RELATES_TO {uuid: $u}]->()
        WHERE e.group_id = $g
        RETURN e.episodes AS episodes, e.fact AS fact
        """,
        params={'u': eu, 'g': GROUP},
    )
    row = stored[0][0]
    assert row['episodes'] == []
    assert 'healed' in row['fact']

    # Production search path must hydrate without EntityEdge ValidationError.
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    from graphiti_core.embedder.client import EmbedderClient
    from graphiti_core.graphiti_types import GraphitiClients
    from graphiti_core.llm_client.client import LLMClient
    from graphiti_core.search.search import search
    from graphiti_core.search.search_config_recipes import EDGE_HYBRID_SEARCH_RRF
    from graphiti_core.search.search_filters import SearchFilters
    from graphiti_core.tracer import NoOpTracer

    class _Emb(EmbedderClient):
        async def create(self, input_data: Any = None, **kwargs: Any) -> list[float]:
            assert input_data is None or input_data is not None
            assert isinstance(kwargs, dict)
            return [0.01] * EMBED_DIM

        async def create_batch(self, input_data_list: list[Any] | None = None) -> list[list[float]]:
            items = input_data_list or []
            return [[0.01] * EMBED_DIM for _ in items]

    class _LLM(LLMClient):
        def __init__(self) -> None:
            pass

        async def _generate_response(self, *args: Any, **kwargs: Any) -> Any:
            assert args is not None
            assert isinstance(kwargs, dict)
            raise AssertionError('no LLM')

        async def generate_response(self, *args: Any, **kwargs: Any) -> Any:
            assert args is not None
            assert isinstance(kwargs, dict)
            raise AssertionError('no LLM')

    class _CE(CrossEncoderClient):
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            assert isinstance(query, str)
            assert isinstance(passages, list)
            return [(p, 0.0) for p in passages]

    try:
        clients = GraphitiClients(
            driver=ctx.driver,
            llm_client=_LLM(),  # type: ignore[arg-type]
            embedder=_Emb(),  # type: ignore[arg-type]
            cross_encoder=_CE(),  # type: ignore[arg-type]
            tracer=NoOpTracer(),
        )
    except Exception:
        clients = GraphitiClients.model_construct(
            driver=ctx.driver,
            llm_client=ctx.llm,
            embedder=ctx.embedder,
            cross_encoder=_CE(),
            tracer=NoOpTracer(),
        )

    edge_results = await search(
        clients,
        'employees.dept_id references departments.dept_id healed',
        [GROUP],
        EDGE_HYBRID_SEARCH_RRF,
        SearchFilters(edge_types=None),
    )
    facts = [getattr(e, 'fact', None) for e in (edge_results.edges or [])]
    assert any(f and 'healed' in f for f in facts), (
        f'search failed to hydrate healed edge: {facts!r}'
    )
    for e in edge_results.edges or []:
        if getattr(e, 'uuid', None) == eu:
            assert list(getattr(e, 'episodes', None) or []) == []
            break


async def test_edge_update_preserves_existing_provenance_episodes(catalog_client):
    ctx = catalog_client
    await _upsert_entities(ctx, [_six_entities()[2], _extra_table()])
    edge = _edge(
        'ForeignKeyTo',
        'FK::episodes-preserved',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.DEPARTMENTS',
        'Table',
        'original fact',
    )
    created = await _upsert_edges(ctx, [edge], batch_id='episodes-create')
    edge_uuid = created.results[0].uuid
    assert edge_uuid
    source_uuid = str(uuid.uuid4())
    await ctx.driver.execute_query(
        """
        MATCH ()-[e:RELATES_TO {uuid: $u}]->()
        WHERE e.group_id = $g
        SET e.episodes = [$source_uuid]
        """,
        params={'u': edge_uuid, 'g': GROUP, 'source_uuid': source_uuid},
    )

    updated = edge.model_copy(update={'fact': 'updated fact'})
    response = await _upsert_edges(ctx, [updated], batch_id='episodes-update')
    assert response.results[0].status == 'updated'
    stored = await ctx.driver.execute_query(
        """
        MATCH ()-[e:RELATES_TO {uuid: $u}]->()
        WHERE e.group_id = $g
        RETURN e.episodes AS episodes
        """,
        params={'u': edge_uuid, 'g': GROUP},
    )
    assert stored[0][0]['episodes'] == [source_uuid]
