"""Live Neo4j proof for immutable prepared-plan control plane (03A-06 / PLAN-05 hard-stop).

Hardcoded group_id: oracle-catalog-tool-test only.
Teardown: DETACH DELETE WHERE group_id = that value. Never clear_graph.
Never touch oracle-catalog-v2 or other groups.

Embedder: FakeEmbedder with fixed vectors. Full CatalogService prepare/commit/discard
path + real Neo4jDriver.transaction still exercised.

Gate mode: CATALOG_INT_REQUIRED=1 converts missing Neo4j into FAIL (not skip).
Skipped live proof must keep features.prepare_commit=false and ready_for_phase_3b=false.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent / 'src'
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from catalog_neo4j_fixtures import FORBIDDEN_GROUP, GROUP  # noqa: E402

from config.schema import CatalogConfig  # noqa: E402
from models.catalog_common import CatalogErrorCode  # noqa: E402
from models.catalog_entities import CatalogEntityItem  # noqa: E402
from models.catalog_prepare import (  # noqa: E402
    CommitPreparedCatalogBatchRequest,
    DiscardPreparedCatalogBatchRequest,
    PrepareCatalogBatchRequest,
)
from services.catalog_identity import (  # noqa: E402
    batch_request_sha256,
    plan_token_digest,
)
from services.catalog_prepared_artifact import (  # noqa: E402
    artifact_sha256,
    reassemble_artifact_bytes,
)
from services.catalog_service import CatalogService  # noqa: E402
from services.catalog_store import CatalogNeo4jStore  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_neo4j,
    pytest.mark.asyncio,
]

EMBED_DIM = 8
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
# Force multi-chunk path without multi-MiB fixtures (plan-justified max path).
CHUNK_BYTES = 256
CATALOG_SHA = 'a' * 64


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


def _enabled_config(**overrides: Any) -> CatalogConfig:
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


def _entity(index: int = 0, *, summary_pad: int = 400) -> CatalogEntityItem:
    # Pad summary so multi-entity prepare exceeds CHUNK_BYTES and forces multi-chunk.
    pad = ('X' * summary_pad) + f'-{index}'
    name = f'TABLE{index:04d}'
    return CatalogEntityItem.model_validate(
        {
            'entity_type': 'Table',
            'graph_key': f'TABLE::FE::ORCL.HR.{name}',
            'name_raw': name,
            'name_canonical': name.lower(),
            'database_qualified_name': f'ORCL.HR.{name}',
            'summary': f'Live prepare fixture table {index} {pad}',
            'attributes': {'src': 'prepare-neo4j-int', 'i': index},
            'confidence': 0.95,
        }
    )


def _prepare_request(
    *,
    batch_id: str,
    entities: list[CatalogEntityItem] | None = None,
    catalog_sha256: str = CATALOG_SHA,
) -> PrepareCatalogBatchRequest:
    items = entities if entities is not None else [_entity(0), _entity(1), _entity(2)]
    return PrepareCatalogBatchRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        batch_id=batch_id,
        entities=items,
        edges=[],
        provenance=None,
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
    # Always wipe control + any residual nodes for the isolated test group only.
    await driver.execute_query(
        'MATCH (n) WHERE n.group_id = $g DETACH DELETE n',
        params={'g': group_id},
    )
    # Restore nothing from before if prior suite left orphans; only this group.
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


async def _chunk_rows(driver: Any, plan_uuid: str) -> list[dict[str, Any]]:
    result = await driver.execute_query(
        """
        MATCH (c:CatalogPreparedPlanChunk {plan_uuid: $u, group_id: $g})
        RETURN c.chunk_index AS chunk_index,
               c.chunk_count AS chunk_count,
               c.byte_offset AS byte_offset,
               c.byte_length AS byte_length,
               c.chunk_sha256 AS chunk_sha256,
               c.payload_b64 AS payload_b64,
               labels(c) AS labels
        ORDER BY c.chunk_index ASC
        """,
        params={'u': plan_uuid, 'g': GROUP},
    )
    records = result[0] if result else []
    out: list[dict[str, Any]] = []
    for row in records:
        d = row if isinstance(row, dict) else dict(row)
        out.append(dict(d))
    return out


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
            # Isolation: forbidden group untouched; other groups unchanged.
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


def test_module_hardcodes_allowed_group_only():
    assert FORBIDDEN_GROUP == 'oracle-catalog-v2'
    assert GROUP == 'oracle-catalog-tool-test'
    assert GROUP != FORBIDDEN_GROUP
    # Prepare request builder hardcodes the allowed test group only.
    req = _prepare_request(batch_id='prep-group-const-001', entities=[_entity(0)])
    assert req.group_id == GROUP
    assert req.group_id != FORBIDDEN_GROUP


async def test_gate_required_mode_documents_live_driver(neo4j_driver):
    assert neo4j_driver is not None
    assert hasattr(neo4j_driver, 'execute_query')
    assert hasattr(neo4j_driver, 'transaction')


async def test_prepare_multi_chunk_survives_driver_close_and_fresh_session(catalog_ctx):
    """PLAN-05 hard-stop: multi-chunk immutable artifact, commit/close/fresh reassembly."""
    ctx = catalog_ctx
    request = _prepare_request(batch_id='prep-restart-001', entities=[_entity(i) for i in range(6)])
    resp = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert resp.error_code is None, resp.error_message
    assert resp.plan_token
    assert resp.plan_uuid
    assert resp.artifact_sha256
    assert len(resp.artifact_sha256) == 64

    props = await _plan_props(ctx.driver, resp.plan_uuid)
    assert props is not None
    labels = set(props['_labels'])
    assert 'CatalogPreparedPlan' in labels
    assert 'Entity' not in labels
    assert 'Episodic' not in labels
    assert 'CatalogIngestBatch' not in labels
    assert props.get('token_digest') == plan_token_digest(resp.plan_token)
    assert 'plan_token' not in props
    assert 'raw_token' not in props
    assert props.get('artifact_sha256') == resp.artifact_sha256
    chunk_count = int(props.get('chunk_count') or 0)
    assert chunk_count >= 2, f'expected multi-chunk path, got chunk_count={chunk_count}'

    chunks = await _chunk_rows(ctx.driver, resp.plan_uuid)
    assert len(chunks) == chunk_count
    for ch in chunks:
        assert 'Entity' not in set(ch.get('labels') or [])
        assert ch.get('payload_b64') is not None

    # Reassemble on original driver as baseline.
    same_bytes = reassemble_artifact_bytes(
        [
            {
                'chunk_index': int(c['chunk_index']),
                'byte_offset': int(c['byte_offset']),
                'byte_length': int(c['byte_length']),
                'chunk_sha256': str(c['chunk_sha256']),
                'payload_b64': str(c['payload_b64']),
            }
            for c in chunks
        ],
        expected_sha256=resp.artifact_sha256,
        expected_length=int(props.get('payload_bytes') or 0) or None,
    )
    assert artifact_sha256(same_bytes) == resp.artifact_sha256

    # Fresh driver/session (simulates process restart) must reassemble byte-identical.
    # Keep fixture driver open for teardown isolation checks.
    uri, user, password = _neo4j_env()
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    fresh = Neo4jDriver(uri=uri, user=user, password=password)
    try:
        await fresh.execute_query('RETURN 1 AS ok', params={})
        store = CatalogNeo4jStore()
        root = await store.load_prepared_plan_by_token_digest(
            fresh, token_digest=plan_token_digest(resp.plan_token)
        )
        assert root is not None
        assert root.get('artifact_sha256') == resp.artifact_sha256
        assert root.get('token_digest') == plan_token_digest(resp.plan_token)
        loaded_chunks = await store.load_prepared_plan_chunks(
            fresh, plan_uuid=resp.plan_uuid, group_id=GROUP
        )
        fresh_bytes = reassemble_artifact_bytes(
            loaded_chunks,
            expected_sha256=resp.artifact_sha256,
            expected_length=int(root.get('payload_bytes') or 0) or None,
        )
        assert fresh_bytes == same_bytes
        assert artifact_sha256(fresh_bytes) == resp.artifact_sha256
    finally:
        await fresh.close()


async def test_prepare_zero_domain_and_status_contamination(catalog_ctx):
    ctx = catalog_ctx
    before_labels = await _label_counts(ctx.driver)
    request = _prepare_request(batch_id='prep-zero-domain-001')
    resp = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert resp.error_code is None, resp.error_message

    labels = await _label_counts(ctx.driver)
    for forbidden in (
        'Entity',
        'Episodic',
        'CatalogIngestBatch',
        'CatalogSource',
        'Community',
    ):
        assert labels.get(forbidden, 0) == before_labels.get(forbidden, 0) == 0 or labels.get(
            forbidden, 0
        ) == before_labels.get(forbidden, 0)
        assert labels.get(forbidden, 0) == 0
    assert labels.get('CatalogPreparedPlan', 0) >= 1
    assert labels.get('CatalogPreparedPlanChunk', 0) >= 1
    # No RELATES_TO edges for this group from prepare.
    edge_count = await _count_group_edges(ctx.driver, GROUP)
    assert edge_count == 0
    assert ctx.llm.calls == 0
    assert ctx.queue.add_episode_calls == 0


async def test_capacity_serialization_and_discard_frees_slot(catalog_ctx):
    ctx = catalog_ctx
    max_active = 2
    ctx.service = CatalogService(
        catalog_config=_enabled_config(max_active_plans_per_group=max_active),
        queue_service=ctx.queue,
    )
    tokens: list[str] = []
    for i in range(max_active):
        req = _prepare_request(batch_id=f'prep-cap-{i:03d}', entities=[_entity(i)])
        resp = await ctx.service.prepare_catalog_batch(client=ctx.client, request=req)
        assert resp.error_code is None, resp.error_message
        tokens.append(resp.plan_token)

    overflow = await ctx.service.prepare_catalog_batch(
        client=ctx.client,
        request=_prepare_request(batch_id='prep-cap-overflow', entities=[_entity(99)]),
    )
    assert overflow.error_code == CatalogErrorCode.batch_limit_exceeded
    assert overflow.plan_token == ''

    discarded = await ctx.service.discard_prepared_catalog_batch(
        client=ctx.client,
        request=DiscardPreparedCatalogBatchRequest(plan_token=tokens[0]),
    )
    assert discarded.error_code is None, discarded.error_message
    assert discarded.state == 'DISCARDED'

    freed = await ctx.service.prepare_catalog_batch(
        client=ctx.client,
        request=_prepare_request(batch_id='prep-cap-freed', entities=[_entity(100)]),
    )
    assert freed.error_code is None, freed.error_message
    assert freed.plan_token


async def test_commit_claim_committing_without_domain_and_reentry(catalog_ctx):
    ctx = catalog_ctx
    request = _prepare_request(batch_id='prep-commit-001', entities=[_entity(0), _entity(1)])
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    expected_hash = batch_request_sha256(request)
    assert prepared.request_sha256 == expected_hash

    entity_before = (await _label_counts(ctx.driver)).get('Entity', 0)
    commit = await ctx.service.commit_prepared_catalog_batch(
        client=ctx.client,
        request=CommitPreparedCatalogBatchRequest(
            plan_token=prepared.plan_token,
            expected_request_sha256=expected_hash,
        ),
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTING'
    assert commit.plan_uuid == prepared.plan_uuid
    assert commit.artifact_sha256 == prepared.artifact_sha256
    assert (await _label_counts(ctx.driver)).get('Entity', 0) == entity_before

    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert props.get('state') == 'COMMITTING'
    assert props.get('token_digest') == plan_token_digest(prepared.plan_token)

    # COMMITTING re-entry allowed (same token); still no domain write.
    reentry = await ctx.service.commit_prepared_catalog_batch(
        client=ctx.client,
        request=CommitPreparedCatalogBatchRequest(plan_token=prepared.plan_token),
    )
    assert reentry.error_code is None, reentry.error_message
    assert reentry.state == 'COMMITTING'
    assert (await _label_counts(ctx.driver)).get('Entity', 0) == entity_before
    assert ctx.llm.calls == 0
    assert ctx.queue.add_episode_calls == 0


async def test_discard_idempotent_and_terminal_no_revive(catalog_ctx):
    ctx = catalog_ctx
    prepared = await ctx.service.prepare_catalog_batch(
        client=ctx.client,
        request=_prepare_request(batch_id='prep-discard-001', entities=[_entity(0)]),
    )
    assert prepared.error_code is None, prepared.error_message

    d1 = await ctx.service.discard_prepared_catalog_batch(
        client=ctx.client,
        request=DiscardPreparedCatalogBatchRequest(plan_token=prepared.plan_token),
    )
    assert d1.error_code is None, d1.error_message
    assert d1.state == 'DISCARDED'

    d2 = await ctx.service.discard_prepared_catalog_batch(
        client=ctx.client,
        request=DiscardPreparedCatalogBatchRequest(plan_token=prepared.plan_token),
    )
    # Idempotent discard or not-found mapping is acceptable; never revive to PREPARED.
    assert d2.error_code in (None, CatalogErrorCode.prepared_plan_not_found)
    if d2.error_code is None:
        assert d2.state == 'DISCARDED'

    revive = await ctx.service.commit_prepared_catalog_batch(
        client=ctx.client,
        request=CommitPreparedCatalogBatchRequest(plan_token=prepared.plan_token),
    )
    assert revive.error_code == CatalogErrorCode.prepared_plan_not_found
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert props.get('state') == 'DISCARDED'


async def test_expiry_access_path_marks_expired(catalog_ctx):
    ctx = catalog_ctx
    ctx.service = CatalogService(
        catalog_config=_enabled_config(plan_ttl_seconds=1),
        queue_service=ctx.queue,
    )
    prepared = await ctx.service.prepare_catalog_batch(
        client=ctx.client,
        request=_prepare_request(batch_id='prep-expire-001', entities=[_entity(0)]),
    )
    assert prepared.error_code is None, prepared.error_message
    await asyncio.sleep(1.5)
    # Force wall clock past expires_at.
    assert datetime.now(timezone.utc).timestamp() > 0

    expired = await ctx.service.commit_prepared_catalog_batch(
        client=ctx.client,
        request=CommitPreparedCatalogBatchRequest(plan_token=prepared.plan_token),
    )
    assert expired.error_code == CatalogErrorCode.prepared_plan_expired
    # Require terminal EXPIRED (retry-bound). Soft PREPARED allowance is forbidden.
    state = None
    for _ in range(5):
        props = await _plan_props(ctx.driver, prepared.plan_uuid)
        assert props is not None
        state = props.get('state')
        if state == 'EXPIRED':
            break
        again = await ctx.service.commit_prepared_catalog_batch(
            client=ctx.client,
            request=CommitPreparedCatalogBatchRequest(plan_token=prepared.plan_token),
        )
        assert again.error_code == CatalogErrorCode.prepared_plan_expired
        await asyncio.sleep(0.05)
    assert state == 'EXPIRED', f'expected EXPIRED after access-path expire, got {state!r}'


async def test_digest_only_token_storage_on_plan_root(catalog_ctx):
    ctx = catalog_ctx
    prepared = await ctx.service.prepare_catalog_batch(
        client=ctx.client,
        request=_prepare_request(batch_id='prep-digest-001', entities=[_entity(0)]),
    )
    assert prepared.error_code is None, prepared.error_message
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    digest = plan_token_digest(prepared.plan_token)
    assert props.get('token_digest') == digest
    # Raw token must never appear as a stored property value.
    for key, value in props.items():
        if key.startswith('_'):
            continue
        if isinstance(value, str):
            assert value != prepared.plan_token
            assert 'plan_token' not in key
