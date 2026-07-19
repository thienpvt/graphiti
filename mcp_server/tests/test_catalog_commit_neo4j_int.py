"""Live Neo4j proof for atomic co-commit (03B-06 / PLAN-13..16, TEST-06/07).

Hardcoded group_id: oracle-catalog-tool-test only (D-34).
NEVER query or mutate oracle-catalog-v2 (including safety probes).
Never call clear_graph. Teardown only test-created UUIDs/batch_ids.

CATALOG_INT_REQUIRED=1 converts missing Neo4j into FAIL (not skip).
Gate-required live execution sets CATALOG_CEILING_SMOKE=1 → 500 entities.

IDE-safe: no static product imports (importlib/getattr only).
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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

# D-34: allowed live isolation constant only.
TEST_GROUP = 'oracle-catalog-tool-test'
# Named for static scans / ban list — NEVER used as a Cypher param or group_id.
_FORBIDDEN_GROUP_NAME = 'oracle' + '-catalog-v2'
GROUP = TEST_GROUP

EMBED_DIM = 8
FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
CHUNK_BYTES = 256
CATALOG_SHA = 'b' * 64
# Oracle graph_key body segments must match [A-Z][A-Z0-9_$#]* — no hyphens.
_RUN_TOKEN = uuid.uuid4().hex[:10].upper()
RUN_PREFIX = f'C06{_RUN_TOKEN}'


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
# Fixtures GROUP must match TEST_GROUP if present; never assign forbidden as GROUP.
if _fixtures is not None:
    fx_group = str(getattr(_fixtures, 'GROUP', TEST_GROUP))
    assert fx_group == TEST_GROUP, f'fixture GROUP must be {TEST_GROUP}'

_CONFIG = _load_module('config.schema')
_ENTITIES = _load_module('models.catalog_entities')
_BATCH = _load_module('models.catalog_batch')
_EVIDENCE = _load_module('models.catalog_evidence')
_PREPARE = _load_module('models.catalog_prepare')
_PROVENANCE = _load_module('models.catalog_provenance')
_IDENTITY = _load_module('services.catalog_identity')
_SERVICE = _load_module('services.catalog_service')
_MANIFEST = _load_module('services.catalog_manifest')
_PREP_ART = _load_module('services.catalog_prepared_artifact')

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
catalog_entity_uuid = _attr(_IDENTITY, 'catalog_entity_uuid')
CatalogService = _attr(_SERVICE, 'CatalogService')
manifest_sha256 = _attr(_MANIFEST, 'manifest_sha256')
reassemble_artifact_bytes = _attr(_PREP_ART, 'reassemble_artifact_bytes')


def _catalog_int_required() -> bool:
    return os.environ.get('CATALOG_INT_REQUIRED', '').strip() in ('1', 'true', 'TRUE', 'yes')


def _ceiling_required() -> bool:
    return os.environ.get('CATALOG_CEILING_SMOKE', '').strip() in ('1', 'true', 'TRUE', 'yes')


def _neo4j_env() -> tuple[str, str, str]:
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:17687')
    user = os.environ.get('NEO4J_USER', 'neo4j')
    password = os.environ.get('NEO4J_PASSWORD', 'catalogtest123')
    return uri, user, password


def _walk_params_for_group(obj: Any, found: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {'group_id', 'g', 'forbidden'} and isinstance(v, str):
                found.append(v)
            if isinstance(v, str) and v == _FORBIDDEN_GROUP_NAME:
                found.append(v)
            _walk_params_for_group(v, found)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _walk_params_for_group(item, found)


class TrackingDriver:
    """Wrap Neo4jDriver: reject forbidden group params; count success txs; track scope."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.param_groups: list[str] = []
        self.tx_enter_count = 0
        self.tx_commit_count = 0
        self.queries: list[str] = []
        self.rejected = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _audit(self, cypher: str, params: dict[str, Any] | None) -> None:
        self.queries.append(cypher if isinstance(cypher, str) else str(cypher))
        found: list[str] = []
        _walk_params_for_group(params or {}, found)
        for g in found:
            self.param_groups.append(g)
            if g != TEST_GROUP:
                self.rejected = True
                raise AssertionError(
                    f'forbidden group_id in query params: {g!r} (only {TEST_GROUP} allowed)'
                )
        # Never allow forbidden name as literal in Cypher text for this suite.
        if _FORBIDDEN_GROUP_NAME in (cypher if isinstance(cypher, str) else ''):
            self.rejected = True
            raise AssertionError('forbidden group string present in Cypher text')

    async def execute_query(self, cypher_query_: Any, **kwargs: Any) -> Any:
        params = kwargs.get('params')
        if params is None:
            params = {}
        self._audit(cypher_query_, params if isinstance(params, dict) else {})
        return await self._inner.execute_query(cypher_query_, **kwargs)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        """Delegate to inner Neo4j tx; count enter/commit for single-success-tx proof."""
        self.tx_enter_count += 1
        async with self._inner.transaction() as tx:
            yield TrackingTx(tx, self)
        # Reached only when body + inner commit succeeded (rollback re-raises).
        self.tx_commit_count += 1


class TrackingTx:
    def __init__(self, inner: Any, driver: TrackingDriver) -> None:
        self._inner = inner
        self._driver = driver

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def run(self, query: str, **kwargs: Any) -> Any:
        # Product store uses await tx.run(cypher, **params) — kwargs carry group_id.
        self._driver._audit(query, kwargs)
        return await self._inner.run(query, **kwargs)


class FakeEmbedder:
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


class CreatedRegistry:
    """Track only objects created by this suite for scoped teardown."""

    def __init__(self) -> None:
        self.batch_ids: set[str] = set()
        self.plan_uuids: set[str] = set()
        self.entity_uuids: set[str] = set()
        self.prefixes: set[str] = {RUN_PREFIX}

    def note_batch(self, batch_id: str) -> None:
        self.batch_ids.add(batch_id)

    def note_plan(self, plan_uuid: str | None) -> None:
        if plan_uuid:
            self.plan_uuids.add(str(plan_uuid))

    def note_entities(self, entities: list[Any]) -> None:
        for ent in entities:
            eu = catalog_entity_uuid(FIXED_NS, TEST_GROUP, ent.entity_type, ent.graph_key)
            self.entity_uuids.add(eu)


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


def _entity(index: int = 0, *, summary_pad: int = 80, name_prefix: str = 'CTABLE') -> Any:
    pad = ('X' * summary_pad) + f'-{index}'
    # Table body: DB.SCHEMA.NAME — fold run token into uppercase table name.
    name = f'{name_prefix}{RUN_PREFIX}{index:04d}'
    return CatalogEntityItem.model_validate(
        {
            'entity_type': 'Table',
            'graph_key': f'TABLE::FE::ORCL.HR.{name}',
            'name_raw': name,
            'name_canonical': name.lower(),
            'database_qualified_name': f'ORCL.HR.{name}',
            'summary': f'Live commit fixture table {index} {pad}',
            'attributes': {'src': 'commit-neo4j-int', 'i': index, 'run': RUN_PREFIX},
            'confidence': 0.95,
        }
    )


def _source(index: int = 0) -> Any:
    return CatalogSourceItem.model_validate(
        {
            'source_key': f'SOURCE::SYNTHETIC.HR.COMMIT_{RUN_PREFIX}_{index:04d}#1',
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


async def _count_label(driver: Any, label: str, group_id: str = GROUP) -> int:
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


async def _manifest_roots(
    driver: Any, batch_id: str, group_id: str = GROUP
) -> list[dict[str, Any]]:
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


async def _manifest_chunks(
    driver: Any, manifest_uuid: str, group_id: str = GROUP
) -> list[dict[str, Any]]:
    result = await driver.execute_query(
        """
        MATCH (c:CatalogBatchManifestChunk {group_id: $g, manifest_uuid: $m})
        RETURN c.chunk_index AS chunk_index,
               c.chunk_count AS chunk_count,
               c.byte_offset AS byte_offset,
               c.byte_length AS byte_length,
               c.chunk_sha256 AS chunk_sha256,
               c.payload_b64 AS payload_b64
        ORDER BY c.chunk_index
        """,
        params={'g': group_id, 'm': manifest_uuid},
    )
    records = result[0] if result else []
    out: list[dict[str, Any]] = []
    for row in records:
        d = row if isinstance(row, dict) else dict(row)
        out.append(
            {
                'chunk_index': int(d['chunk_index']),
                'chunk_count': int(d.get('chunk_count') or 0),
                'byte_offset': int(d['byte_offset']),
                'byte_length': int(d['byte_length']),
                'chunk_sha256': str(d['chunk_sha256']),
                'payload_b64': str(d['payload_b64']),
            }
        )
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


async def _teardown_created(driver: Any, reg: CreatedRegistry) -> None:
    """Delete only suite-created nodes by uuid/batch_id allowlist within TEST_GROUP."""
    if reg.batch_ids:
        await driver.execute_query(
            """
            MATCH (n)
            WHERE n.group_id = $g AND n.batch_id IN $bids
            DETACH DELETE n
            """,
            params={'g': GROUP, 'bids': list(reg.batch_ids)},
        )
    if reg.plan_uuids:
        await driver.execute_query(
            """
            MATCH (n)
            WHERE n.group_id = $g AND (
              n.uuid IN $plans OR n.plan_uuid IN $plans OR n.manifest_uuid IN $plans
            )
            DETACH DELETE n
            """,
            params={'g': GROUP, 'plans': list(reg.plan_uuids)},
        )
    if reg.entity_uuids:
        await driver.execute_query(
            """
            MATCH (n)
            WHERE n.group_id = $g AND n.uuid IN $euuids
            DETACH DELETE n
            """,
            params={'g': GROUP, 'euuids': list(reg.entity_uuids)},
        )
    # Chunks/roots keyed by batch_id already deleted; also clean prepared plan chunks
    # that only store plan_uuid.
    if reg.plan_uuids:
        await driver.execute_query(
            """
            MATCH (c:CatalogPreparedPlanChunk)
            WHERE c.group_id = $g AND c.plan_uuid IN $plans
            DETACH DELETE c
            """,
            params={'g': GROUP, 'plans': list(reg.plan_uuids)},
        )


@pytest.fixture
async def neo4j_driver():
    try:
        neo4j_mod = importlib.import_module('graphiti_core.driver.neo4j_driver')
        Neo4jDriver = _attr(neo4j_mod, 'Neo4jDriver')
    except Exception as exc:  # pragma: no cover
        if _catalog_int_required():
            pytest.fail(f'Neo4j driver import failed under CATALOG_INT_REQUIRED=1: {exc}')
        pytest.skip(f'Neo4j driver unavailable: {exc}')

    uri, user, password = _neo4j_env()
    raw = Neo4jDriver(uri=uri, user=user, password=password)
    driver = TrackingDriver(raw)
    try:
        await driver.execute_query('RETURN 1 AS ok', params={})
    except Exception as exc:
        await raw.close()
        if _catalog_int_required():
            pytest.fail(f'Neo4j unavailable under CATALOG_INT_REQUIRED=1: {exc}')
        pytest.skip(f'Neo4j unavailable: {exc}')

    await asyncio.sleep(0.2)
    reg = CreatedRegistry()
    try:
        yield driver, reg
    finally:
        try:
            await _teardown_created(driver, reg)
            # Runtime safety: every captured group param was allowed.
            assert all(g == TEST_GROUP for g in driver.param_groups), driver.param_groups
            assert driver.rejected is False
        finally:
            await raw.close()


@pytest.fixture
async def catalog_ctx(neo4j_driver: Any):
    driver, reg = neo4j_driver
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
        reg=reg,
    )


async def _prepare_and_commit(
    ctx: Any,
    *,
    batch_id: str,
    entities: list[Any] | None = None,
    with_evidence: bool = True,
) -> tuple[Any, Any, Any]:
    items = entities if entities is not None else [_entity(0), _entity(1)]
    ctx.reg.note_batch(batch_id)
    ctx.reg.note_entities(items)
    request = _prepare_request(batch_id=batch_id, entities=items, with_evidence=with_evidence)
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    assert prepared.plan_token
    ctx.reg.note_plan(prepared.plan_uuid)
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
    """Sync safety scan — no asyncio marker on this test."""
    assert GROUP == TEST_GROUP == 'oracle-catalog-tool-test'
    src = Path(__file__).read_text(encoding='utf-8')
    assert "TEST_GROUP = 'oracle-catalog-tool-test'" in src
    # Forbidden group name must never appear as GROUP/group_id/TEST_GROUP assignment.
    assert not any(
        line.strip().startswith(('GROUP =', 'group_id =', 'TEST_GROUP ='))
        and _FORBIDDEN_GROUP_NAME in line
        for line in src.splitlines()
    )
    # Forbidden group must never be passed as a Cypher/query param value.
    # Ban patterns: params={...'oracle-catalog-v2'...} or execute_query(..., forbidden)
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if 'params=' in stripped and _FORBIDDEN_GROUP_NAME in stripped:
            raise AssertionError(f'forbidden group in query params: {stripped}')
        if 'execute_query' in stripped and _FORBIDDEN_GROUP_NAME in stripped:
            raise AssertionError(f'forbidden group in execute_query: {stripped}')
    clear_fn = 'clear' + '_graph'
    assert f'{clear_fn}(' not in src
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith('from config.') or stripped.startswith('from models.'):
            raise AssertionError(f'static product import forbidden: {stripped}')
        if stripped.startswith('from services.') or stripped.startswith('from graphiti_core.'):
            raise AssertionError(f'static product import forbidden: {stripped}')
        if stripped.startswith('from catalog_neo4j_fixtures'):
            raise AssertionError(f'static fixtures import forbidden: {stripped}')


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_single_tx_co_commit(catalog_ctx):
    """PLAN-13/TEST-07: single-tx co-commit; exactly one success write tx after claim."""
    ctx = catalog_ctx
    entities = [_entity(0), _entity(1)]
    items = entities
    ctx.reg.note_batch(f'{RUN_PREFIX}-happy-001')
    ctx.reg.note_entities(items)
    request = _prepare_request(
        batch_id=f'{RUN_PREFIX}-happy-001', entities=items, with_evidence=True
    )
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    assert prepared.plan_token
    ctx.reg.note_plan(prepared.plan_uuid)

    # Instrument only the commit path: claim CAS (1) + success writer (1) = 2.
    tx_enter_before = ctx.driver.tx_enter_count
    tx_commit_before = ctx.driver.tx_commit_count
    expected_hash = batch_request_sha256(request)
    commit = await ctx.service.commit_prepared_catalog_batch(
        client=ctx.client,
        request=CommitPreparedCatalogBatchRequest(
            plan_token=prepared.plan_token,
            expected_request_sha256=expected_hash,
        ),
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert commit.plan_uuid == prepared.plan_uuid
    assert commit.manifest_sha256 and len(commit.manifest_sha256) == 64
    assert commit.committed_created + commit.committed_updated + commit.committed_unchanged >= 1

    enter_delta = ctx.driver.tx_enter_count - tx_enter_before
    commit_delta = ctx.driver.tx_commit_count - tx_commit_before
    # Claim tx + one success write tx; no extra success writers.
    assert enter_delta == 2, f'expected claim+write txs, got enter_delta={enter_delta}'
    assert commit_delta == 2, f'expected 2 commits, got commit_delta={commit_delta}'

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
    assert await _count_label(ctx.driver, 'CatalogBatchManifest') >= 1
    assert await _control_nodes_with_entity(ctx.driver) == 0
    assert ctx.llm.calls == 0
    assert ctx.queue.add_episode_calls == 0
    assert all(g == TEST_GROUP for g in ctx.driver.param_groups)


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_mid_write_fault_zero_partial(catalog_ctx):
    """PLAN-13/14: mid-write fault at evidence leaves zero partial success."""
    ctx = catalog_ctx
    seed_entities = [_entity(10)]
    seed_prep, seed_commit, _ = await _prepare_and_commit(
        ctx, batch_id=f'{RUN_PREFIX}-fault-seed', entities=seed_entities, with_evidence=True
    )
    assert seed_commit.error_code is None, seed_commit.error_message
    assert seed_commit.state == 'COMMITTED'
    assert seed_prep.plan_uuid

    mixed = [_entity(10), _entity(11)]
    request = _prepare_request(batch_id=f'{RUN_PREFIX}-fault-001', entities=mixed)
    ctx.reg.note_batch(request.batch_id)
    ctx.reg.note_entities(mixed)
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    ctx.reg.note_plan(prepared.plan_uuid)

    labels_before = await _label_counts(ctx.driver)
    entity_before = labels_before.get('Entity', 0)
    evidence_before = labels_before.get('CatalogEvidenceLink', 0)
    manifest_before = labels_before.get('CatalogBatchManifest', 0)

    store = ctx.service._store
    original = store.write_evidence_links

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
        store.write_evidence_links = original  # type: ignore[method-assign]

    assert commit.error_code is not None
    assert commit.state != 'COMMITTED'
    labels_after = await _label_counts(ctx.driver)
    assert labels_after.get('Entity', 0) == entity_before
    assert labels_after.get('CatalogEvidenceLink', 0) == evidence_before
    assert labels_after.get('CatalogBatchManifest', 0) == manifest_before
    failed_batch = await _batch_status(ctx.driver, request.batch_id)
    if failed_batch is not None:
        assert failed_batch.get('status') != 'committed'
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert props.get('state') in {'COMMITTING', 'EXPIRED'}
    assert props.get('state') != 'COMMITTED'
    assert props.get('state') != 'PREPARED'


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_post_manifest_fault_zero_partial(catalog_ctx):
    """PLAN-14: fault after manifest write / during terminal CAS → zero partial success."""
    ctx = catalog_ctx
    entities = [_entity(12), _entity(13)]
    request = _prepare_request(batch_id=f'{RUN_PREFIX}-fault-cas', entities=entities)
    ctx.reg.note_batch(request.batch_id)
    ctx.reg.note_entities(entities)
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    ctx.reg.note_plan(prepared.plan_uuid)

    labels_before = await _label_counts(ctx.driver)
    entity_before = labels_before.get('Entity', 0)
    evidence_before = labels_before.get('CatalogEvidenceLink', 0)
    manifest_before = labels_before.get('CatalogBatchManifest', 0)
    batch_committed_before = 0
    result = await ctx.driver.execute_query(
        """
        MATCH (b:CatalogIngestBatch {group_id: $g})
        WHERE b.status = 'committed' AND b.batch_id STARTS WITH $pfx
        RETURN count(b) AS c
        """,
        params={'g': GROUP, 'pfx': RUN_PREFIX},
    )
    records = result[0] if result else []
    if records:
        row = records[0]
        batch_committed_before = int(row['c'] if isinstance(row, dict) else row['c'])

    store = ctx.service._store
    original = store.cas_plan_state

    async def _boom_terminal_cas(tx: Any, **kwargs: Any) -> Any:
        # Fail only terminal COMMITTING→COMMITTED (after manifest), not claim CAS.
        if (
            kwargs.get('expected_from') == 'COMMITTING'
            and kwargs.get('to_state') == 'COMMITTED'
        ):
            raise RuntimeError('inject_during_terminal_cas')
        return await original(tx, **kwargs)

    store.cas_plan_state = _boom_terminal_cas  # type: ignore[method-assign]
    try:
        commit = await ctx.service.commit_prepared_catalog_batch(
            client=ctx.client,
            request=CommitPreparedCatalogBatchRequest(plan_token=prepared.plan_token),
        )
    finally:
        store.cas_plan_state = original  # type: ignore[method-assign]

    assert commit.error_code is not None
    assert commit.state != 'COMMITTED'
    labels_after = await _label_counts(ctx.driver)
    # Full success-tx rollback: entity/evidence/manifest created inside same tx vanish.
    assert labels_after.get('Entity', 0) == entity_before
    assert labels_after.get('CatalogEvidenceLink', 0) == evidence_before
    assert labels_after.get('CatalogBatchManifest', 0) == manifest_before
    result2 = await ctx.driver.execute_query(
        """
        MATCH (b:CatalogIngestBatch {group_id: $g})
        WHERE b.status = 'committed' AND b.batch_id STARTS WITH $pfx
        RETURN count(b) AS c
        """,
        params={'g': GROUP, 'pfx': RUN_PREFIX},
    )
    records2 = result2[0] if result2 else []
    after = 0
    if records2:
        row2 = records2[0]
        after = int(row2['c'] if isinstance(row2, dict) else row2['c'])
    assert after == batch_committed_before
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    # Claim CAS already moved PREPARED→COMMITTING in separate tx; terminal CAS aborted.
    assert props.get('state') == 'COMMITTING'
    assert props.get('state') != 'COMMITTED'
    assert props.get('state') != 'PREPARED'


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_identical_replay(catalog_ctx):
    """PLAN-15: identical replay of committed batch returns stable receipt; no dup."""
    ctx = catalog_ctx
    entities = [_entity(20), _entity(21)]
    request = _prepare_request(batch_id=f'{RUN_PREFIX}-replay-001', entities=entities)
    ctx.reg.note_batch(request.batch_id)
    ctx.reg.note_entities(entities)
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    ctx.reg.note_plan(prepared.plan_uuid)
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
    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert len(manifests) == 1


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_entity_search_interop(catalog_ctx):
    """TEST-07: production graphiti search path returns catalog Entity (not raw Cypher MATCH)."""
    ctx = catalog_ctx
    entities = [_entity(30, name_prefix='SEARCHTAB')]
    _, commit, _ = await _prepare_and_commit(
        ctx, batch_id=f'{RUN_PREFIX}-search-001', entities=entities
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'

    search_mod = importlib.import_module('graphiti_core.search.search')
    search_config_mod = importlib.import_module('graphiti_core.search.search_config')
    filters_mod = importlib.import_module('graphiti_core.search.search_filters')
    types_mod = importlib.import_module('graphiti_core.graphiti_types')
    tracer_mod = importlib.import_module('graphiti_core.tracer')
    ce_mod = importlib.import_module('graphiti_core.cross_encoder.client')
    emb_mod = importlib.import_module('graphiti_core.embedder.client')
    llm_mod = importlib.import_module('graphiti_core.llm_client.client')

    search = _attr(search_mod, 'search')
    NodeSearchConfig = _attr(search_config_mod, 'NodeSearchConfig')
    NodeSearchMethod = _attr(search_config_mod, 'NodeSearchMethod')
    NodeReranker = _attr(search_config_mod, 'NodeReranker')
    SearchConfig = _attr(search_config_mod, 'SearchConfig')
    SearchFilters = _attr(filters_mod, 'SearchFilters')
    GraphitiClients = _attr(types_mod, 'GraphitiClients')
    NoOpTracer = _attr(tracer_mod, 'NoOpTracer')
    CrossEncoderClient = _attr(ce_mod, 'CrossEncoderClient')
    EmbedderClient = _attr(emb_mod, 'EmbedderClient')
    LLMClient = _attr(llm_mod, 'LLMClient')

    class _Emb(EmbedderClient):
        async def create(self, input_data: Any = None, **kwargs: Any) -> list[float]:
            _ = input_data, kwargs
            return [0.01 * ((i % 7) + 1) for i in range(EMBED_DIM)]

        async def create_batch(self, input_data_list: list[Any] | None = None) -> list[list[float]]:
            items = input_data_list or []
            return [await self.create() for _ in items]

    class _LLM(LLMClient):
        def __init__(self) -> None:
            # Bypass provider config; search path must not call LLM.
            self.config = None
            self.model = None
            self.small_model = None
            self.temperature = 0.0
            self.max_tokens = 1
            self.cache_enabled = False
            self.cache_dir = None
            self.tracer = NoOpTracer()
            self.token_tracker = None

        async def _generate_response(self, *args: Any, **kwargs: Any) -> Any:
            _ = args, kwargs
            raise AssertionError('no LLM')

        async def generate_response(self, *args: Any, **kwargs: Any) -> Any:
            _ = args, kwargs
            raise AssertionError('no LLM')

    class _CE(CrossEncoderClient):
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            _ = query
            return [(p, 0.0) for p in passages]

    # TrackingDriver is not a GraphDriver subclass — bypass validation.
    clients = GraphitiClients.model_construct(
        driver=ctx.driver,
        llm_client=_LLM(),
        embedder=_Emb(),
        cross_encoder=_CE(),
        tracer=NoOpTracer(),
    )

    await ctx.driver.execute_query(
        'CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh()', params={}
    )
    name = entities[0].name_raw
    # Catalog Entity.name is the deterministic graph_key; name_raw is preserved separately.
    node_results = await search(
        clients,
        entities[0].graph_key.lower(),
        [GROUP],
        SearchConfig(
            node_config=NodeSearchConfig(
                search_methods=[NodeSearchMethod.bm25],
                reranker=NodeReranker.rrf,
            )
        ),
        SearchFilters(node_labels=['Table']),
    )
    node_names = {
        getattr(n, 'name', None) or getattr(n, 'uuid', None) for n in (node_results.nodes or [])
    }
    assert any(n and name.lower() in str(n).lower() for n in node_names), (
        f'search path returned no {name!r}; got {node_names!r}'
    )
    assert ctx.llm.calls == 0
    assert ctx.queue.add_episode_calls == 0


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_evidence_manifest_lack_entity(catalog_ctx):
    """EVID-10/MANI: evidence and manifest nodes must not carry Entity label."""
    ctx = catalog_ctx
    entities = [_entity(40), _entity(41)]
    prepared, commit, request = await _prepare_and_commit(
        ctx, batch_id=f'{RUN_PREFIX}-labels-001', entities=entities
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert await _control_nodes_with_entity(ctx.driver) == 0
    assert await _count_label(ctx.driver, 'CatalogEvidenceLink') >= 1
    assert await _count_label(ctx.driver, 'CatalogBatchManifest') >= 1
    assert await _count_label(ctx.driver, 'CatalogBatchManifestChunk') >= 1
    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert len(manifests) == 1
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert 'Entity' not in set(props.get('_labels') or [])


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_isolation_tool_test_only(catalog_ctx):
    """D-34: runtime-observed scope is only oracle-catalog-tool-test (no forbidden probe)."""
    ctx = catalog_ctx
    assert TEST_GROUP == 'oracle-catalog-tool-test'
    _, commit, request = await _prepare_and_commit(
        ctx, batch_id=f'{RUN_PREFIX}-iso-001', entities=[_entity(50)]
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert request.group_id == TEST_GROUP
    # All captured param group_ids are allowed.
    assert ctx.driver.param_groups
    assert all(g == TEST_GROUP for g in ctx.driver.param_groups)
    assert ctx.driver.rejected is False
    # No Cypher text contained forbidden group.
    assert all(_FORBIDDEN_GROUP_NAME not in q for q in ctx.driver.queries)


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_configured_ceiling_smoke(catalog_ctx):
    """A1/plan 06: gate-required live must run configured max entities=500.

    CATALOG_CEILING_SMOKE=1 is mandatory under gate --require-neo4j.
    Without the flag this test fails closed when CATALOG_INT_REQUIRED=1.
    """
    ctx = catalog_ctx
    if not _ceiling_required():
        if _catalog_int_required():
            pytest.fail(
                'CATALOG_CEILING_SMOKE=1 required for configured-ceiling live proof '
                '(gate --require-neo4j must set it)'
            )
        pytest.skip('CATALOG_CEILING_SMOKE not set; ceiling proof deferred')

    count = 500
    entities = [_entity(i, summary_pad=12) for i in range(count)]
    ctx.service = CatalogService(
        catalog_config=_enabled_config(
            prepared_chunk_bytes=65_536,
            max_entities_per_batch=500,
        ),
        queue_service=ctx.queue,
    )
    prepared, commit, request = await _prepare_and_commit(
        ctx,
        batch_id=f'{RUN_PREFIX}-ceiling-full',
        entities=entities,
        with_evidence=False,
    )
    assert prepared.error_code is None, prepared.error_message
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert commit.manifest_sha256
    # Entity count for this run's batch membership via manifest.
    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert len(manifests) == 1
    assert int(manifests[0].get('entity_count') or 0) == count
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert props.get('state') == 'COMMITTED'


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_same_token_concurrency(catalog_ctx):
    """PLAN-16/TEST-06: concurrent same-token commits → one logical commit (live)."""
    ctx = catalog_ctx
    entities = [_entity(60), _entity(61)]
    request = _prepare_request(batch_id=f'{RUN_PREFIX}-race-001', entities=entities)
    ctx.reg.note_batch(request.batch_id)
    ctx.reg.note_entities(entities)
    prepared = await ctx.service.prepare_catalog_batch(client=ctx.client, request=request)
    assert prepared.error_code is None, prepared.error_message
    ctx.reg.note_plan(prepared.plan_uuid)
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
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    assert props is not None
    assert props.get('state') == 'COMMITTED'


@pytest.mark.integration
@pytest.mark.requires_neo4j
@pytest.mark.asyncio
async def test_live_unchanged_membership_in_manifest(catalog_ctx):
    """MANI-01/02/07: second commit records projected_status=unchanged with durable reassembly."""
    ctx = catalog_ctx
    entities = [_entity(70)]
    expected_uuid = catalog_entity_uuid(
        FIXED_NS, TEST_GROUP, entities[0].entity_type, entities[0].graph_key
    )
    _, first, _ = await _prepare_and_commit(
        ctx, batch_id=f'{RUN_PREFIX}-unchanged-a', entities=entities
    )
    assert first.error_code is None, first.error_message
    assert first.state == 'COMMITTED'
    assert first.committed_created >= 1

    _, second, req2 = await _prepare_and_commit(
        ctx, batch_id=f'{RUN_PREFIX}-unchanged-b', entities=entities
    )
    assert second.error_code is None, second.error_message
    assert second.state == 'COMMITTED'
    assert second.committed_unchanged >= 1, (
        f'expected committed_unchanged>=1, got created={second.committed_created} '
        f'updated={second.committed_updated} unchanged={second.committed_unchanged}'
    )

    manifests = await _manifest_roots(ctx.driver, req2.batch_id)
    assert len(manifests) == 1
    root = manifests[0]
    assert int(root.get('entity_count') or 0) == len(entities)
    manifest_uuid = str(root.get('uuid') or '')
    assert manifest_uuid
    chunks = await _manifest_chunks(ctx.driver, manifest_uuid)
    assert chunks, 'manifest chunks missing'
    raw = reassemble_artifact_bytes(
        chunks,
        expected_sha256=str(root.get('manifest_sha256') or '') or None,
        expected_length=int(root.get('payload_bytes') or 0) or None,
    )
    body = json.loads(raw.decode('utf-8'))
    assert isinstance(body, dict)
    members = body.get('entities') or body.get('membership', {}).get('entities') or []
    # Body shape: top-level categories from build_manifest_body_from_membership.
    if not members and isinstance(body.get('entities'), list):
        members = body['entities']
    assert isinstance(members, list) and members, f'no entity membership in body keys={list(body)}'
    unchanged_rows = [m for m in members if m.get('projected_status') == 'unchanged']
    assert unchanged_rows, f'no projected_status=unchanged in {members!r}'
    match = next((m for m in unchanged_rows if m.get('uuid') == expected_uuid), None)
    assert match is not None, (
        f'expected uuid {expected_uuid} not in unchanged rows {unchanged_rows}'
    )
    assert match.get('graph_key') == entities[0].graph_key
    assert match.get('content_sha256')
    # Membership authority is compact identity fields — not batch_id.
    assert 'batch_id' not in match
    # Root digest matches reassembly.
    assert manifest_sha256(raw) == root.get('manifest_sha256')

# ---------------------------------------------------------------------------
# Phase 5 Wave 0 RED live gaps (TEST-11) — GREEN in 05-04
# ---------------------------------------------------------------------------


async def test_phase5_commit_zero_writes_outside_test_group(catalog_ctx):
    """TEST-11: runtime-audited commit parameters use only the exact test group."""
    ctx = catalog_ctx
    _, commit, request = await _prepare_and_commit(
        ctx, batch_id=f'{RUN_PREFIX}-phase5-scope', entities=[_entity(80)]
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert request.group_id == GROUP == TEST_GROUP == 'oracle-catalog-tool-test'
    assert ctx.driver.param_groups
    assert set(ctx.driver.param_groups) == {TEST_GROUP}
    assert ctx.driver.rejected is False


async def test_phase5_commit_control_labels_not_in_entity_search(catalog_ctx):
    """TEST-11 empty: post-commit control labels never carry Entity."""
    ctx = catalog_ctx
    prepared, commit, request = await _prepare_and_commit(
        ctx, batch_id=f'{RUN_PREFIX}-phase5-labels', entities=[_entity(81)]
    )
    assert commit.error_code is None, commit.error_message
    assert commit.state == 'COMMITTED'
    assert await _control_nodes_with_entity(ctx.driver) == 0
    props = await _plan_props(ctx.driver, prepared.plan_uuid)
    manifests = await _manifest_roots(ctx.driver, request.batch_id)
    assert props is not None and 'Entity' not in set(props['_labels'])
    assert manifests and all('Entity' not in set(item['_labels']) for item in manifests)
