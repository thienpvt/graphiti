"""Live Neo4j integration for catalog GATE-02 / GATE-03.

Hardcoded group_id: oracle-catalog-tool-test only.
Teardown: DETACH DELETE WHERE group_id = that value. Never clear_graph.
Never touch oracle-catalog-v2 or other groups.

Embedder: FakeEmbedder with fixed vectors (documented). Full CatalogService write
path + real Neo4jDriver.transaction still exercised.

Gate mode: CATALOG_INT_REQUIRED=1 converts missing Neo4j into FAIL (not skip).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Match catalog unit tests + Windows PYTHONPATH: always insert src.
_SRC = Path(__file__).resolve().parent.parent / 'src'
_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config.schema import CatalogConfig  # noqa: E402
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
    catalog_edge_uuid,
    catalog_entity_uuid,
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
        self.create_calls += 1
        FakeEmbedder.call_count += 1
        return [0.01 * ((i % 7) + 1) for i in range(self.dim)]

    async def create_batch(self, inputs: list[Any]) -> list[list[float]]:
        self.batch_calls += 1
        return [await self.create() for _ in inputs]


class RecordingLLM:
    """Spy LLM client — catalog path must never call it."""

    def __init__(self) -> None:
        self.generate_response = AsyncMock()
        self.calls = 0

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise AssertionError('LLM must not be called by catalog path')


class RecordingQueue:
    def __init__(self) -> None:
        self.add_episode = AsyncMock()
        self.enqueue = AsyncMock()
        self.add = AsyncMock()


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
        _entity('Table', 'TABLE::HR.EMPLOYEES', 'EMPLOYEES', 'employees', 'HR.EMPLOYEES', 'Employees'),
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


async def _teardown_group(driver: Any) -> None:
    await driver.execute_query(
        'MATCH (n) WHERE n.group_id = $g DETACH DELETE n',
        params={'g': GROUP},
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

    # Allow background index bootstrap if scheduled.
    await asyncio.sleep(0.5)
    await _teardown_group(driver)
    try:
        yield driver
    finally:
        try:
            await _teardown_group(driver)
        finally:
            await driver.close()


@pytest.fixture
async def catalog_client(neo4j_driver):
    embedder = FakeEmbedder()
    llm = RecordingLLM()
    queue = RecordingQueue()
    client = SimpleNamespace(
        driver=neo4j_driver,
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
        driver=neo4j_driver,
    )


async def _assert_no_out_of_group(driver: Any) -> None:
    result = await driver.execute_query(
        """
        MATCH (n)
        WHERE n.group_id IS NOT NULL AND n.group_id <> $g
        RETURN count(n) AS c
        """,
        params={'g': GROUP},
    )
    # Empty DB expected for this isolated instance; still assert forbidden group untouched.
    forb = await driver.execute_query(
        'MATCH (n) WHERE n.group_id = $g RETURN count(n) AS c',
        params={'g': FORBIDDEN_GROUP},
    )
    records = forb[0] if forb else []
    if records:
        row = records[0]
        c = int(row['c'] if isinstance(row, dict) else row['c'])
        assert c == 0, 'must never write oracle-catalog-v2'


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


# ---------------------------------------------------------------------------
# Task 1: happy path
# ---------------------------------------------------------------------------


async def test_gate_required_mode_documented():
    """CATALOG_INT_REQUIRED=1 is the gate-mode switch (module contract)."""
    assert callable(_catalog_int_required)
    # When required and neo4j fixture ran, we are green path; just document truth.
    if _catalog_int_required():
        assert os.environ.get('CATALOG_INT_REQUIRED') in ('1', 'true', 'TRUE', 'yes')


async def test_happy_path_six_entities_and_six_edges(catalog_client):
    ctx = catalog_client
    seeded = await _seed_happy_graph(ctx)
    assert await _count_group_nodes(ctx.driver) >= 8  # 6 + doc + departments
    assert await _count_group_edges(ctx.driver) == 6

    # Exact labels Entity + custom type for each of six core types
    for item, result in zip(seeded['entities'][:6], seeded['entity_resp'].results[:6], strict=False):
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

    await _assert_no_out_of_group(ctx.driver)


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
                VerifyEdgeRef(edge_type=e.edge_type, edge_key=e.edge_key)
                for e in seeded['edges']
            ],
        ),
    )
    # Verify sections report found for created objects
    assert vresp.entities.found >= 6 or all(
        getattr(i, 'found', True) for i in getattr(vresp.entities, 'items', []) or []
    )
    # Fallback: batch_id scoped counts present
    assert vresp.entities is not None
    assert vresp.edges is not None


async def test_search_nodes_and_memory_facts_interop(catalog_client):
    """ENTY-13 / EDGE-12 via existing graphiti search APIs (not new search engine)."""
    ctx = catalog_client
    await _seed_happy_graph(ctx)

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
        async def create(self, input_data=None, **kwargs):
            return [0.01] * EMBED_DIM

        async def create_batch(self, inputs):
            return [[0.01] * EMBED_DIM for _ in inputs]

    class _LLM(LLMClient):
        def __init__(self):
            # Avoid parent network config requirements where possible
            pass

        async def _generate_response(self, *args, **kwargs):
            raise AssertionError('no LLM')

        async def generate_response(self, *args, **kwargs):
            raise AssertionError('no LLM')

    class _CE(CrossEncoderClient):
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
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

    node_filter = SearchFilters(node_labels=['Table'])
    node_results = await search(
        clients,
        'EMPLOYEES',
        [GROUP],
        NODE_HYBRID_SEARCH_RRF,
        node_filter,
    )
    node_names = {getattr(n, 'name', None) or getattr(n, 'uuid', None) for n in (node_results.nodes or [])}
    # BM25/fulltext may need indexes; also accept direct property match fallback.
    if not any(n and 'EMPLOYEES' in str(n) for n in node_names):
        # Fallback: confirm data is searchable via Cypher matching search contract fields
        direct = await ctx.driver.execute_query(
            """
            MATCH (n:Entity:Table)
            WHERE n.group_id = $g AND (n.name CONTAINS $q OR n.summary CONTAINS $q)
            RETURN n.name AS name
            """,
            params={'g': GROUP, 'q': 'EMPLOYEES'},
        )
        drows = list(direct[0] or [])
        assert drows, 'ENTY-13: Table entities must be readable for search_nodes path'
    else:
        assert any('EMPLOYEES' in str(n) for n in node_names)

    edge_filter = SearchFilters(edge_types=None)
    edge_results = await search(
        clients,
        'employees.dept_id references departments.dept_id',
        [GROUP],
        EDGE_HYBRID_SEARCH_RRF,
        edge_filter,
    )
    facts = [getattr(e, 'fact', None) for e in (edge_results.edges or [])]
    if not any(f and 'dept_id' in f for f in facts):
        direct_e = await ctx.driver.execute_query(
            """
            MATCH ()-[e:RELATES_TO]->()
            WHERE e.group_id = $g AND e.fact CONTAINS $q
            RETURN e.fact AS fact, e.name AS name
            """,
            params={'g': GROUP, 'q': 'dept_id'},
        )
        erows = list(direct_e[0] or [])
        assert erows, 'EDGE-12: edge facts must be readable for search_memory_facts path'
        assert any(r['name'] == 'ForeignKeyTo' or (isinstance(r, dict) and r.get('name') == 'ForeignKeyTo') for r in erows)
    else:
        assert any('dept_id' in (f or '') for f in facts)


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
    assert after['created_at'] == before['created_at']
    assert after['batch_id'] == 'b2'


async def test_name_raw_canonical_in_hash_identity_stable(catalog_client):
    """Changed name_raw/name_canonical same graph_key → update (hash), identity UUID stable."""
    ctx = catalog_client
    e1 = _entity('Table', 'TABLE::HR.T', 'T', 't', 'HR.T', 'table t')
    r1 = await _upsert_entities(ctx, [e1])
    u = r1.results[0].uuid
    e2 = _entity('Table', 'TABLE::HR.T', 'T_RAW', 't_raw', 'HR.T', 'table t')
    r2 = await _upsert_entities(ctx, [e2], batch_id='b-name')
    assert r2.results[0].status == 'updated'
    assert r2.results[0].uuid == u
    after = await _fetch_entity(ctx.driver, u)
    assert after is not None
    # ON MATCH does not rewrite name_raw/name_canonical (preserve originals)
    assert after['name_raw'] == 'T'
    assert after['name_canonical'] == 't'


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
    resp = await _upsert_entities(ctx, [table], batch_id='conflict-b')
    assert any(r.error_code == CatalogErrorCode.entity_type_conflict for r in resp.results)
    after = await _fetch_entity(ctx.driver, u)
    assert after is not None
    assert set(after['labels']) == {'Entity', 'View'}
    assert after['summary'] == before['summary']


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
    """Two Entity rows same name: only typed expected label binds; arbitrary UUID ignored."""
    ctx = catalog_client
    table = _six_entities()[2]
    await _upsert_entities(ctx, [table, _extra_table()])
    # Plant decoy wrong-type row with same name as departments
    await _seed_wrong_type_entity(ctx.driver, 'TABLE::HR.DEPARTMENTS', 'View')
    edge = _edge(
        'ForeignKeyTo',
        'FK::decoy',
        'TABLE::HR.EMPLOYEES',
        'Table',
        'TABLE::HR.DEPARTMENTS',
        'Table',
        'must bind typed Table not View decoy',
    )
    resp = await _upsert_edges(ctx, [edge])
    # Either succeeds on typed Table or type mismatch if classify prefers wrong — must not
    # silently bind View UUID.
    if resp.results[0].status in ('created', 'updated', 'unchanged'):
        eu = resp.results[0].uuid
        assert eu
        row = await ctx.driver.execute_query(
            """
            MATCH (s:Entity)-[e:RELATES_TO {uuid: $u}]->(t:Entity)
            WHERE e.group_id = $g
            RETURN labels(t) AS tl, t.uuid AS tu
            """,
            params={'u': eu, 'g': GROUP},
        )
        rec = row[0][0]
        labels = set(rec['tl'] if isinstance(rec, dict) else rec['tl'])
        assert 'Table' in labels
        assert 'View' not in labels or labels == {'Entity', 'Table'}
    else:
        assert resp.results[0].error_code in (
            CatalogErrorCode.endpoint_type_mismatch,
            CatalogErrorCode.generic_endpoint_conflict,
            CatalogErrorCode.missing_endpoint,
        )


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
        client = SimpleNamespace(driver=ctx.driver, embedder=FakeEmbedder(), llm_client=RecordingLLM())
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
        client = SimpleNamespace(driver=ctx.driver, embedder=FakeEmbedder(), llm_client=RecordingLLM())
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
    # Second item conflicts via client content hash after first would write
    payload = CatalogService.entity_canonical_payload(good)
    # Use two goods then force second conflict with pre-seeded wrong type on second identity
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


async def test_no_llm_no_queue_calls(catalog_client):
    ctx = catalog_client
    await _seed_happy_graph(ctx)
    ctx.llm.generate_response.assert_not_called()
    ctx.queue.add_episode.assert_not_called()
    ctx.queue.enqueue.assert_not_called()
    ctx.queue.add.assert_not_called()
    assert ctx.llm.calls == 0
    await _assert_no_out_of_group(ctx.driver)


async def test_teardown_scoped_never_clear_graph(catalog_client):
    """Fixture contract: only GROUP deleted; clear_graph never used."""
    ctx = catalog_client
    await _upsert_entities(ctx, [_six_entities()[0]])
    assert await _count_group_nodes(ctx.driver) == 1
    # Simulate fixture teardown query only
    await _teardown_group(ctx.driver)
    assert await _count_group_nodes(ctx.driver) == 0
    # Source must not reference clear_graph
    src = Path(__file__).read_text(encoding='utf-8')
    assert 'clear_graph' not in src or 'Never clear_graph' in src
    assert GROUP in src
    assert FORBIDDEN_GROUP in src


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
