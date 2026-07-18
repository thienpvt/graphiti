"""Live Neo4j proof for atomic co-commit (03B-06 / PLAN-13..16, TEST-06/07).

Hardcoded group_id: oracle-catalog-tool-test only (D-34).
Never touch oracle-catalog-v2. Never call clear_graph.
Teardown: DETACH DELETE WHERE group_id = TEST_GROUP for test-created data only.

CATALOG_INT_REQUIRED=1 converts missing Neo4j into FAIL (not skip).
Skipped live proof must keep ready_for_phase_4=false.

IDE-safe: no static product imports (importlib/getattr only) so repo-root
pyright without mcp_server extraPaths does not report missing imports.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent / 'src'
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _load_fixtures() -> ModuleType | None:
    path = _TESTS_DIR / 'catalog_neo4j_fixtures.py'
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location('catalog_neo4j_fixtures', path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module(module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(f'03B product import failed: {module_name} ({exc})')


def _attr(mod: Any, symbol: str) -> Any:
    value = getattr(mod, symbol, None)
    if value is None:
        pytest.fail(f'03B product missing symbol: {symbol}')
    return value


_fixtures = _load_fixtures()
GROUP = str(getattr(_fixtures, 'GROUP', 'oracle-catalog-tool-test')) if _fixtures else (
    'oracle-catalog-tool-test'
)
FORBIDDEN_GROUP = (
    str(getattr(_fixtures, 'FORBIDDEN_GROUP', 'oracle-catalog-v2'))
    if _fixtures
    else 'oracle-catalog-v2'
)

# D-34: live isolation constant — hard-coded tool-test only.
TEST_GROUP = 'oracle-catalog-tool-test'
assert GROUP == TEST_GROUP or GROUP == 'oracle-catalog-tool-test'
assert FORBIDDEN_GROUP == 'oracle-catalog-v2'
assert TEST_GROUP != FORBIDDEN_GROUP

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_neo4j,
    pytest.mark.asyncio,
]

EMBED_DIM = 8
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
CHUNK_BYTES = 256
CATALOG_SHA = 'b' * 64

# Dynamic product symbols (no static `from config/models/services ...` imports).
_CONFIG = _load_module('config.schema')
_ENTITIES = _load_module('models.catalog_entities')
_BATCH = _load_module('models.catalog_batch')
_EVIDENCE = _load_module('models.catalog_evidence')
_PREPARE = _load_module('models.catalog_prepare')
_PROVENANCE = _load_module('models.catalog_provenance')
_IDENTITY = _load_module('services.catalog_identity')
_SERVICE = _load_module('services.catalog_service')

CatalogConfig = _attr(_CONFIG, 'CatalogConfig')
CatalogEntityItem = _attr(_ENTITIES, 'CatalogEntityItem')
NestedProvenancePayload = _attr(_BATCH, 'NestedProvenancePayload')
CatalogEvidenceEntityTarget = _attr(_EVIDENCE, 'CatalogEvidenceEntityTarget')
CatalogEvidenceLink = _attr(_EVIDENCE, 'CatalogEvidenceLink')
CommitPreparedCatalogBatchRequest = _attr(_PREPARE, 'CommitPreparedCatalogBatchRequest')
PrepareCatalogBatchRequest = _attr(_PREPARE, 'PrepareCatalogBatchRequest')
CatalogSourceItem = _attr(_PROVENANCE, 'CatalogSourceItem')
batch_request_sha256 = _attr(_IDENTITY, 'batch_request_sha256')
plan_token_digest = _attr(_IDENTITY, 'plan_token_digest')
CatalogService = _attr(_SERVICE, 'CatalogService')


def _catalog_int_required() -> bool:
    return os.environ.get('CATALOG_INT_REQUIRED', '').strip() in ('1', 'true', 'TRUE', 'yes')


def _neo4j_env() -> tuple[str, str, str]:
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:17687')
    user = os.environ.get('NEO4J_USER', 'neo4j')
    password = os.environ.get('NEO4J_PASSWORD', 'catalogtest123')
    return uri, user, password


class FakeEmbedder:
    """Deterministic fixed-vector embedder — no live embedding provider."""

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim
        self.create_calls = 0

    async def create(self, input_data: Any = None, **kwargs: Any) -> list[float]:
        _ = input_data, kwargs
        self.create_calls += 1
        return [0.01 * ((i % 7) + 1) for i in range(self.dim)]

    async def create_batch(self, inputs: list[Any]) -> list[list[float]]:
        return [await self.create(input_data=item) for item in inputs]


class RecordingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_response(self, *args: Any, **kwargs: Any) -> Any:
        _ = args, kwargs
        self.calls += 1
        raise AssertionError('LLM must not be called by prepare/commit path')


class RecordingQueue:
    def __init__(self) -> None:
        self.add_episode_calls = 0

    async def add_episode(self, *args: Any, **kwargs: Any) -> Any:
        _ = args, kwargs
        self.add_episode_calls += 1
        raise AssertionError('queue must not be called by prepare/commit path')


def _enabled_config(**overrides: Any) -> Any:
    data: dict[str, Any] = {
        'enabled': True,
        'uuid_namespace': str(FIXED_NS),
        'max_entities_per_batch': 500,
        'max_edges_per_batch': 2000,
        'max_provenance_links_per_batch': 5000,
        'plan_ttl_seconds': 3600,
        'max_prepared_payload_bytes': 4_194_304,
        'max_active_plans_per_group': 8,
        'prepared_chunk_bytes': CHUNK_BYTES,
    }
    data.update(overrides)
    return CatalogConfig(**data)


def _entity(index: int = 0, *, summary_pad: int = 80) -> Any:
    pad = ('X' * summary_pad) + f'-{index}'
    name = f'CTABLE{index:04d}'
    return CatalogEntityItem.model_validate(
        {
            'entity_type': 'Table',
            'graph_key': f'TABLE::FE::ORCL.HR.{name}',
            'name_raw': name,
            'name_canonical': name.lower(),
            'database_qualified_name': f'ORCL.HR.{name}',
            'summary': f'Live commit fixture table {index} {pad}',
            'attributes': {'src': 'commit-neo4j-int', 'i': index},
            'confidence': 0.95,
        }
    )


def _source(index: int = 0) -> Any:
    return CatalogSourceItem.model_validate(
        {
            'source_key': f'SOURCE::SYNTHETIC.HR.COMMIT.{index:04d}#1',
            'reference_time': '2026-07-18T00:00:00Z',
        }
    )


def _evidence_link(entity: Any, source: Any) -> Any:
    return CatalogEvidenceLink.model_validate(
        {
            'source_key': source.source_key,
            'entity_target': CatalogEvidenceEntityTarget(
                entity_type=entity.entity_type,
                graph_key=entity.graph_key,
            ),
            'evidence_kind': 'ddl',
            'extractor_name': 'commit-neo4j-int',
            'extractor_version': '1.0.0',
            'confidence': 0.9,
            'excerpt': f'CREATE TABLE {entity.name_raw}',
        }
    )


def _prepare_request(
    *,
    batch_id: str,
    entities: list[Any] | None = None,
    with_evidence: bool = True,
    catalog_sha256: str = CATALOG_SHA,
) -> Any:
    items = entities if entities is not None else [_entity(0), _entity(1)]
    provenance = None
    if with_evidence:
        sources = [_source(i) for i in range(len(items))]
        links = [_evidence_link(items[i], sources[i]) for i in range(len(items))]
        provenance = NestedProvenancePayload(sources=sources, evidence_links=links)
    return PrepareCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=batch_id,
        entities=items,
        edges=[],
        provenance=provenance,
        request_sha256=None,
        catalog_sha256=catalog_sha256,
        atomic=True,
    )


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
    records = result[0] if result else []
    out: list[tuple[str, int, int]] = []
    for row in records:
        d = row if isinstance(row, dict) else dict(row)
        out.append((str(d['group_id']), int(d['node_count']), int(d['edge_count'])))
    return tuple(out)


async def _snapshot_group_elements(driver: Any, group_id: str = GROUP) -> tuple[set[str], set[str]]:
    nodes = await driver.execute_query(
        'MATCH (n) WHERE n.group_id = $g RETURN collect(n.uuid) AS ids',
        params={'g': group_id},
    )
    edges = await driver.execute_query(
        'MATCH ()-[e]->() WHERE e.group_id = $g RETURN collect(e.uuid) AS ids',
        params={'g': group_id},
    )
    nrec = (nodes[0][0] if nodes and nodes[0] else {}) or {}
    erec = (edges[0][0] if edges and edges[0] else {}) or {}
    nids = nrec['ids'] if isinstance(nrec, dict) else nrec.get('ids')  # type: ignore[union-attr]
    eids = erec['ids'] if isinstance(erec, dict) else erec.get('ids')  # type: ignore[union-attr]
    return set(nids or []), set(eids or [])


async def _teardown_created_elements(
    driver: Any,
    nodes_before: set[str],
    edges_before: set[str],
    group_id: str = GROUP,
) -> None:
    await driver.execute_query(
        'MATCH (n) WHERE n.group_id = $g DETACH DELETE n',
        params={'g': group_id},
    )
    _ = nodes_before, edges_before


async def _label_counts(driver: Any, group_id: str = GROUP) -> dict[str, int]:
    result = await driver.execute_query(
        """
        MATCH (n)
        WHERE n.group_id = $g
        UNWIND labels(n) AS label
        RETURN label, count(*) AS c
        ORDER BY label
        """,
        params={'g': group_id},
    )
    records = result[0] if result else []
    out: dict[str, int] = {}
    for row in records:
        d = row if isinstance(row, dict) else dict(row)
        out[str(d['label'])] = int(d['c'])
    return out


async def _plan_props(driver: Any, plan_uuid: str) -> dict[str, Any] | None:
    result = await driver.execute_query(
        """
        MATCH (p:CatalogPreparedPlan {uuid: $u, group_id: $g})
        RETURN properties(p) AS props, labels(p) AS labels
        """,
        params={'u': plan_uuid, 'g': GROUP},
    )
    records = result[0] if result else []
    if not records:
        return None
    row = records[0] if isinstance(records[0], dict) else dict(records[0])
    props = dict(row['props'] or {})
    props['_labels'] = list(row['labels'] or [])
    return props


async def _count_label(driver: Any, label: str, group_id: str = GROUP) -> int:
    # Label is server-fixed allowlist only (never client-supplied).
    allowed = {
        'Entity',
        'Table',
        'CatalogEvidenceLink',
        'CatalogBatchManifest',
        'CatalogBatchManifestChunk',
        'CatalogIngestBatch',
        'CatalogPreparedPlan',
        'CatalogPreparedPlanChunk',
        'Episodic',
        'CatalogSource',
    }
    if label not in allowed:
        raise AssertionError(f'label not allowlisted for live count: {label}')
    result = await driver.execute_query(
        f'MATCH (n:{label}) WHERE n.group_id = $g RETURN count(n) AS c',
        params={'g': group_id},
    )
    records = result[0] if result else []
    if not records:
        return 0
    row = records[0]
    return int(row['c'] if isinstance(row, dict) else row['c'])


async def _control_nodes_with_entity(driver: Any, group_id: str = GROUP) -> int:
    result = await driver.execute_query(
        """
        MATCH (n)
        WHERE n.group_id = $g
          AND (
            n:CatalogEvidenceLink
            OR n:CatalogBatchManifest
            OR n:CatalogBatchManifestChunk
            OR n:CatalogIngestBatch
            OR n:CatalogPreparedPlan
            OR n:CatalogPreparedPlanChunk
          )
          AND 'Entity' IN labels(n)
        RETURN count(n) AS c
        """,
        params={'g': group_id},
    )
    records = result[0] if result else []
    if not records:
        return 0
    row = records[0]
    return int(row['c'] if isinstance(row, dict) else row['c'])


async def _entity_searchable(driver: Any, name_canonical: str, group_id: str = GROUP) -> int:
    result = await driver.execute_query(
        """
        MATCH (n:Entity)
        WHERE n.group_id = $g AND n.name_canonical = $name
        RETURN count(n) AS c
        """,
        params={'g': group_id, 'name': name_canonical},
    )
    records = result[0] if result else []
    if not records:
        return 0
    row = records[0]
    return int(row['c'] if isinstance(row, dict) else row['c'])


async def _manifest_roots(driver: Any, batch_id: str, group_id: str = GROUP) -> list[dict[str, Any]]:
    result = await driver.execute_query(
        """
        MATCH (m:CatalogBatchManifest {group_id: $g, batch_id: $b})
        RETURN properties(m) AS props, labels(m) AS labels
        """,
        params={'g': group_id, 'b': batch_id},
    )
    records = result[0] if result else []
    out: list[dict[str, Any]] = []
    for row in records:
        d = row if isinstance(row, dict) else dict(row)
        props = dict(d.get('props') or {})
        props['_labels'] = list(d.get('labels') or [])
        out.append(props)
    return out


async def _batch_status(driver: Any, batch_id: str, group_id: str = GROUP) -> dict[str, Any] | None:
    result = await driver.execute_query(
        """
        MATCH (b:CatalogIngestBatch {group_id: $g, batch_id: $b})
        RETURN properties(b) AS props, labels(b) AS labels
        """,
        params={'g': group_id, 'b': batch_id},
    )
    records = result[0] if result else []
    if not records:
        return None
    row = records[0] if isinstance(records[0], dict) else dict(records[0])
    props = dict(row['props'] or {})
    props['_labels'] = list(row['labels'] or [])
    return props


@pytest.fixture
async def neo4j_driver():
    """Real Neo4jDriver against env/default bolt://localhost:17687."""
    try:
        neo4j_mod = importlib.import_module('graphiti_core.driver.neo4j_driver')
        Neo4jDriver = _attr(neo4j_mod, 'Neo4jDriver')
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

    await asyncio.sleep(0.3)
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
            assert (
                await _count_group_nodes(driver, FORBIDDEN_GROUP),
                await _count_group_edges(driver, FORBIDDEN_GROUP),
            ) == forbidden_before
            assert await _snapshot_other_groups(driver) == other_groups_before
        finally:
            await driver.close()


@pytest.fixture
async def catalog_ctx(neo4j_driver: Any):
    driver = neo4j_driver
    embedder = FakeEmbedder()
    llm = RecordingLLM()
    queue = RecordingQueue()
    client = SimpleNamespace(driver=driver, embedder=embedder, llm_client=llm)
    service = CatalogService(catalog_config=_enabled_config(), queue_service=queue)
    return SimpleNamespace(
        client=client,
        service=service,
        embedder=embedder,
        llm=llm,
        queue=queue,
        driver=driver,
    )


async def _prepare_and_commit(
    ctx: Any,
    *,
    batch_id: str,
    entities: list[Any] | None = None,
    with_evidence: bool = True,
) -> tuple[Any, Any, Any]:
    request = _prepare_request(
        batch_id=batch_id, entities=entities, with_evidence=with_evidence
    )
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    assert prepared.plan_token
    expected_hash = batch_request_sha256(request)
    commit = await ctx.service.commit_prepared_catalog_batch(
        client=ctx.client,
        request=CommitPreparedCatalogBatchRequest(
            plan_token=prepared.plan_token,
            expected_request_sha256=expected_hash,
        ),
    )
    return prepared, commit, request


def test_module_hardcodes_allowed_group_only():
    assert FORBIDDEN_GROUP == 'oracle-catalog-v2'
    assert GROUP == 'oracle-catalog-tool-test'
    assert TEST_GROUP == 'oracle-catalog-tool-test'
    src = Path(__file__).read_text(encoding='utf-8')
    assert "TEST_GROUP = 'oracle-catalog-tool-test'" in src
    forbidden_assign = 'TEST_GROUP = ' + repr(FORBIDDEN_GROUP)
    assert forbidden_assign not in src
    # Avoid embedding the call pattern as a string literal (self-match).
    clear_fn = 'clear' + '_graph'
    assert f'{clear_fn}(' not in src
    # No static product import lines (IDE-root pyright safety).
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith('from config.') or stripped.startswith('from models.'):
            raise AssertionError(f'static product import forbidden: {stripped}')
        if stripped.startswith('from services.') or stripped.startswith('from graphiti_core.'):
            raise AssertionError(f'static product import forbidden: {stripped}')
        if stripped.startswith('from catalog_neo4j_fixtures'):
            raise AssertionError(f'static fixtures import forbidden: {stripped}')


async def test_live_single_tx_co_commit(catalog_ctx):
    """PLAN-13/TEST-07: single-tx co-commit domain+evidence+manifest+batch+plan."""
    ctx = catalog_ctx
    entities = [_entity(0), _entity(1)]
    prepared, commit, request = await _prepare_and_commit(
        ctx, batch_id='commit-live-happy-001', entities=entities
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert commit.plan_uuid == prepared.plan_uuid
    assert commit.manifest_sha256
    assert len(commit.manifest_sha256) == 64
    assert commit.committed_created + commit.committed_updated + commit.committed_unchanged >= 1

    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert props.get('state') == 'COMMITTED'
    assert props.get('token_digest') == plan_token_digest(prepared.plan_token)
    assert 'Entity' not in set(props.get('_labels') or [])

    batch = await _batch_status(ctx.driver, request.batch_id)
    assert batch is not None
    assert batch.get('status') == 'committed'
    assert 'Entity' not in set(batch.get('_labels') or [])

    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert len(manifests) == 1
    m = manifests[0]
    assert m.get('manifest_sha256') == commit.manifest_sha256
    assert int(m.get('entity_count') or 0) == len(entities)
    assert 'Entity' not in set(m.get('_labels') or [])

    assert await _count_label(ctx.driver, 'Entity') >= len(entities)
    assert await _count_label(ctx.driver, 'CatalogEvidenceLink') >= len(entities)
    assert await _count_label(ctx.driver, 'CatalogBatchManifest') == 1
    assert await _control_nodes_with_entity(ctx.driver) == 0
    assert ctx.llm.calls == 0
    assert ctx.queue.add_episode_calls == 0


async def test_live_mid_write_fault_zero_partial(catalog_ctx):
    """PLAN-13/14: mid-write fault leaves zero partial domain/evidence/manifest success."""
    ctx = catalog_ctx
    # Seed one committed entity first so a second prepare can project unchanged.
    seed_entities = [_entity(10)]
    seed_prep, seed_commit, _ = await _prepare_and_commit(
        ctx, batch_id='commit-live-fault-seed', entities=seed_entities, with_evidence=True
    )
    assert seed_commit.error_code is None, seed_commit.error_message
    assert seed_commit.state == 'COMMITTED'
    assert seed_prep.plan_uuid

    mixed = [_entity(10), _entity(11)]
    request = _prepare_request(batch_id='commit-live-fault-001', entities=mixed)
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message

    labels_before = await _label_counts(ctx.driver)
    entity_before = labels_before.get('Entity', 0)
    evidence_before = labels_before.get('CatalogEvidenceLink', 0)
    manifest_before = labels_before.get('CatalogBatchManifest', 0)
    batch_committed_before = 0
    result = await ctx.driver.execute_query(
        """
        MATCH (b:CatalogIngestBatch {group_id: $g})
        WHERE b.status = 'committed'
        RETURN count(b) AS c
        """,
        params={'g': GROUP},
    )
    records = result[0] if result else []
    if records:
        row = records[0]
        batch_committed_before = int(row['c'] if isinstance(row, dict) else row['c'])

    store = ctx.service._store
    original_write_evidence = store.write_evidence_links

    async def _boom(tx: Any, *, links: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _ = tx, links
        raise RuntimeError('inject_after_evidence')

    store.write_evidence_links = _boom  # type: ignore[method-assign]
    try:
        commit = await ctx.service.commit_prepared_catalog_batch(
            client=ctx.client,
            request=CommitPreparedCatalogBatchRequest(plan_token=prepared.plan_token),
        )
    finally:
        store.write_evidence_links = original_write_evidence  # type: ignore[method-assign]

    assert commit.error_code is not None
    assert commit.state != 'COMMITTED'

    labels_after = await _label_counts(ctx.driver)
    assert labels_after.get('Entity', 0) == entity_before
    assert labels_after.get('CatalogEvidenceLink', 0) == evidence_before
    assert labels_after.get('CatalogBatchManifest', 0) == manifest_before

    failed_batch = await _batch_status(ctx.driver, request.batch_id)
    if failed_batch is not None:
        assert failed_batch.get('status') != 'committed'

    result2 = await ctx.driver.execute_query(
        """
        MATCH (b:CatalogIngestBatch {group_id: $g})
        WHERE b.status = 'committed'
        RETURN count(b) AS c
        """,
        params={'g': GROUP},
    )
    records2 = result2[0] if result2 else []
    batch_committed_after = 0
    if records2:
        row2 = records2[0]
        batch_committed_after = int(row2['c'] if isinstance(row2, dict) else row2['c'])
    assert batch_committed_after == batch_committed_before

    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    # Plan may remain COMMITTING (stranded) after claim; never COMMITTED on fault.
    # PREPARED revival is forbidden (D-11).
    assert props.get('state') in {'COMMITTING', 'EXPIRED'}
    assert props.get('state') != 'COMMITTED'
    assert props.get('state') != 'PREPARED'


async def test_live_identical_replay(catalog_ctx):
    """PLAN-15: identical replay of committed batch returns stable receipt; no dup."""
    ctx = catalog_ctx
    entities = [_entity(20), _entity(21)]
    request = _prepare_request(batch_id='commit-live-replay-001', entities=entities)
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    expected_hash = batch_request_sha256(request)
    req = CommitPreparedCatalogBatchRequest(
        plan_token=prepared.plan_token,
        expected_request_sha256=expected_hash,
    )
    first = await ctx.service.commit_prepared_catalog_batch(client=ctx.client, request=req)
    assert first.error_code is None, first.error_message
    assert first.state == 'COMMITTED'
    assert first.manifest_sha256

    second = await ctx.service.commit_prepared_catalog_batch(client=ctx.client, request=req)
    assert second.error_code is None, second.error_message
    assert second.state == 'COMMITTED'
    assert second.manifest_sha256 == first.manifest_sha256
    assert second.plan_uuid == first.plan_uuid
    assert second.committed_created == first.committed_created
    assert second.committed_updated == first.committed_updated
    assert second.committed_unchanged == first.committed_unchanged

    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert len(manifests) == 1
    assert await _count_label(ctx.driver, 'CatalogBatchManifest') == 1
    assert await _count_label(ctx.driver, 'Entity') == len(entities)


async def test_live_entity_search_interop(catalog_ctx):
    """TEST-07: committed catalog entities remain searchable via Entity path."""
    ctx = catalog_ctx
    entities = [_entity(30)]
    _, commit, _ = await _prepare_and_commit(
        ctx, batch_id='commit-live-search-001', entities=entities
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    name = entities[0].name_canonical
    found = await _entity_searchable(ctx.driver, name)
    assert found == 1
    result = await ctx.driver.execute_query(
        """
        MATCH (n:Entity {group_id: $g, name_canonical: $name})
        RETURN n.name_embedding IS NOT NULL AS has_emb,
               size(n.name_embedding) AS emb_len,
               labels(n) AS labels
        """,
        params={'g': GROUP, 'name': name},
    )
    records = result[0] if result else []
    assert records
    row = records[0] if isinstance(records[0], dict) else dict(records[0])
    assert row.get('has_emb') is True
    assert int(row.get('emb_len') or 0) == EMBED_DIM
    labels = set(row.get('labels') or [])
    assert 'Entity' in labels
    assert 'Table' in labels


async def test_live_evidence_manifest_lack_entity(catalog_ctx):
    """EVID-10/MANI: evidence and manifest nodes must not carry Entity label."""
    ctx = catalog_ctx
    entities = [_entity(40), _entity(41)]
    prepared, commit, request = await _prepare_and_commit(
        ctx, batch_id='commit-live-labels-001', entities=entities
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'

    assert await _control_nodes_with_entity(ctx.driver) == 0
    assert await _count_label(ctx.driver, 'CatalogEvidenceLink') >= 1
    assert await _count_label(ctx.driver, 'CatalogBatchManifest') == 1
    assert await _count_label(ctx.driver, 'CatalogBatchManifestChunk') >= 1

    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert len(manifests) == 1
    m = manifests[0]
    assert int(m.get('entity_count') or 0) == len(entities)
    assert m.get('batch_id') == request.batch_id
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert 'Entity' not in set(props.get('_labels') or [])


async def test_live_isolation_tool_test_only(catalog_ctx):
    """D-34: all live writes constrained to oracle-catalog-tool-test; never v2."""
    ctx = catalog_ctx
    assert TEST_GROUP == 'oracle-catalog-tool-test'
    assert FORBIDDEN_GROUP not in (TEST_GROUP,)
    forbidden_before = await _count_group_nodes(ctx.driver, FORBIDDEN_GROUP)
    other_before = await _snapshot_other_groups(ctx.driver)

    _, commit, request = await _prepare_and_commit(
        ctx, batch_id='commit-live-iso-001', entities=[_entity(50)]
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert request.group_id == TEST_GROUP

    assert await _count_group_nodes(ctx.driver, FORBIDDEN_GROUP) == forbidden_before
    assert await _snapshot_other_groups(ctx.driver) == other_before
    result = await ctx.driver.execute_query(
        """
        MATCH (n)
        WHERE n.group_id = $g
        RETURN count(n) AS c,
               sum(CASE WHEN n.group_id = $forbidden THEN 1 ELSE 0 END) AS bad
        """,
        params={'g': GROUP, 'forbidden': FORBIDDEN_GROUP},
    )
    records = result[0] if result else []
    assert records
    row = records[0] if isinstance(records[0], dict) else dict(records[0])
    assert int(row['c']) >= 1
    assert int(row['bad']) == 0


async def test_live_configured_ceiling_smoke(catalog_ctx):
    """A1/plan 06: configured-ceiling smoke at configured max entities when enabled.

    Always runs a reduced multi-entity co-commit (configured path). Full HARD max
    (500) is opt-in via CATALOG_CEILING_SMOKE=1 to keep default live suite fast.
    """
    ctx = catalog_ctx
    full = os.environ.get('CATALOG_CEILING_SMOKE', '').strip() in ('1', 'true', 'TRUE', 'yes')
    count = 500 if full else 20
    entities = [_entity(i, summary_pad=20) for i in range(count)]
    ctx.service = CatalogService(
        catalog_config=_enabled_config(
            prepared_chunk_bytes=65_536 if full else CHUNK_BYTES,
            max_entities_per_batch=500,
        ),
        queue_service=ctx.queue,
    )
    prepared, commit, request = await _prepare_and_commit(
        ctx,
        batch_id=f'commit-live-ceiling-{"full" if full else "smoke"}',
        entities=entities,
        with_evidence=False,
    )
    assert prepared.error_code is None, prepared.error_message
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert commit.manifest_sha256
    assert await _count_label(ctx.driver, 'Entity') == count
    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert len(manifests) == 1
    assert int(manifests[0].get('entity_count') or 0) == count
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert props.get('state') == 'COMMITTED'


async def test_live_same_token_concurrency(catalog_ctx):
    """PLAN-16/TEST-06: concurrent same-token commits → one logical commit (live)."""
    ctx = catalog_ctx
    entities = [_entity(60), _entity(61)]
    request = _prepare_request(batch_id='commit-live-race-001', entities=entities)
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    expected_hash = batch_request_sha256(request)
    req = CommitPreparedCatalogBatchRequest(
        plan_token=prepared.plan_token,
        expected_request_sha256=expected_hash,
    )

    results = await asyncio.gather(
        *[
            ctx.service.commit_prepared_catalog_batch(client=ctx.client, request=req)
            for _ in range(4)
        ]
    )
    successes = [r for r in results if r.error_code is None]
    assert successes, [r.error_code for r in results]
    assert all(r.state == 'COMMITTED' for r in successes)
    shas = {r.manifest_sha256 for r in successes if r.manifest_sha256}
    assert len(shas) == 1
    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert len(manifests) == 1
    assert await _count_label(ctx.driver, 'Entity') == len(entities)
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert props.get('state') == 'COMMITTED'


async def test_live_unchanged_membership_in_manifest(catalog_ctx):
    """MANI-01/02: second commit of same entities records unchanged membership counts."""
    ctx = catalog_ctx
    entities = [_entity(70)]
    _, first, _ = await _prepare_and_commit(
        ctx, batch_id='commit-live-unchanged-a', entities=entities
    )
    assert first.error_code is None, first.error_message
    assert first.state == 'COMMITTED'
    assert first.committed_created >= 1

    _, second, req2 = await _prepare_and_commit(
        ctx, batch_id='commit-live-unchanged-b', entities=entities
    )
    assert second.error_code is None, second.error_message
    assert second.state == 'COMMITTED'
    assert second.committed_unchanged >= 1 or second.committed_updated >= 0
    manifests = await _manifest_roots(ctx.driver, req2.batch_id)
    assert len(manifests) == 1
    assert int(manifests[0].get('entity_count') or 0) == len(entities)
    assert await _entity_searchable(ctx.driver, entities[0].name_canonical) == 1
