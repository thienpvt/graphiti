"""Unit tests for prepared-plan control-plane store (no live Neo4j)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_common import (  # noqa: E402
    HARD_MAX_ACTIVE_PLANS_PER_GROUP,
    PLAN_STATE_COMMITTED,
    PLAN_STATE_COMMITTING,
    PLAN_STATE_DISCARDED,
    PLAN_STATE_EXPIRED,
    PLAN_STATE_PREPARED,
)
from services.catalog_store import (  # noqa: E402
    CATALOG_PREPARED_PLAN_CHUNK_IDENTITY_CONSTRAINT,
    CATALOG_PREPARED_PLAN_CHUNK_INDEX_CONSTRAINT,
    CATALOG_PREPARED_PLAN_IDENTITY_CONSTRAINT,
    CATALOG_PREPARED_PLAN_TOKEN_DIGEST_CONSTRAINT,
    CatalogNeo4jStore,
    CatalogStoreError,
)

GROUP = 'oracle-catalog-tool-test'
PLAN_UUID = '11111111-2222-3333-4444-555555555555'
CHUNK_UUID_0 = 'aaaaaaaa-bbbb-cccc-dddd-000000000000'
CHUNK_UUID_1 = 'aaaaaaaa-bbbb-cccc-dddd-000000000001'
TOKEN_DIGEST = 'a' * 64
ARTIFACT_SHA = 'b' * 64
REQUEST_SHA = 'c' * 64
CATALOG_SHA = 'd' * 64
FIXED_TS = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
EXPIRES = FIXED_TS + timedelta(hours=1)

PLAN_LABELS = frozenset(
    {
        'CatalogPreparedPlan',
        'CatalogPreparedPlanChunk',
        'CatalogPlanGroupLock',
    }
)
FORBIDDEN_LABEL_SUBSTR = (
    ':Entity',
    ':Episodic',
    'CatalogIngestBatch',
    'name_embedding',
    'fact_embedding',
    'RELATES_TO',
)


class _Rows:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    async def data(self) -> list[dict[str, Any]]:
        return list(self._rows)

    async def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _CaptureTx:
    """Records every cypher/params pair; scripted responses by call index."""

    def __init__(self, responses: list[list[dict[str, Any]]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._responses = list(responses or [])
        self._i = 0

    async def run(self, cypher: str, **params: Any) -> _Rows:
        self.calls.append((cypher, params))
        if self._i < len(self._responses):
            rows = self._responses[self._i]
            self._i += 1
            return _Rows(rows)
        return _Rows([])


def _plan_params(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'uuid': PLAN_UUID,
        'group_id': GROUP,
        'batch_id': 'batch-001',
        'plan_id': 'batch-001|' + REQUEST_SHA,
        'token_digest': TOKEN_DIGEST,
        'state': PLAN_STATE_PREPARED,
        'identity_schema_version': 'catalog-v2',
        'canonicalization_version': 'catalog-canonical-v1',
        'artifact_serialization_version': 'prepared-artifact-v1',
        'request_sha256': REQUEST_SHA,
        'catalog_sha256': CATALOG_SHA,
        'artifact_sha256': ARTIFACT_SHA,
        'chunk_count': 1,
        'payload_bytes': 16,
        'entity_count': 1,
        'edge_count': 0,
        'source_count': 0,
        'evidence_link_count': 0,
        'created_count': 1,
        'updated_count': 0,
        'unchanged_count': 0,
        'expires_at': EXPIRES,
        'created_at': FIXED_TS,
        'updated_at': FIXED_TS,
    }
    base.update(overrides)
    return base


def _chunk_params(
    *,
    uuid: str = CHUNK_UUID_0,
    index: int = 0,
    count: int = 1,
    offset: int = 0,
    length: int = 16,
    sha: str | None = None,
    payload_b64: str = 'AQIDBAUGBwgJCgsMDQ4PEA==',
) -> dict[str, Any]:
    return {
        'uuid': uuid,
        'group_id': GROUP,
        'plan_uuid': PLAN_UUID,
        'chunk_index': index,
        'chunk_count': count,
        'byte_offset': offset,
        'byte_length': length,
        'chunk_sha256': sha or ('e' * 64),
        'payload_b64': payload_b64,
    }


def _all_cypher(tx: _CaptureTx) -> str:
    return '\n'.join(c for c, _ in tx.calls)


def _assert_fixed_labels_only(cypher: str) -> None:
    for bad in FORBIDDEN_LABEL_SUBSTR:
        assert bad not in cypher, f'forbidden substring {bad!r} in plan cypher'
    # Allowed control labels may appear; domain Entity label must not as node label.
    assert ':Entity' not in cypher
    assert ':Episodic' not in cypher


# ---------------------------------------------------------------------------
# Task 1: schema + create/load + capacity
# ---------------------------------------------------------------------------


def test_plan_schema_constraint_statements_fixed_labels_and_uniqueness():
    store = CatalogNeo4jStore()
    stmts = store.plan_schema_constraint_statements()
    joined = '\n'.join(stmts)
    assert 'CREATE CONSTRAINT' in joined
    assert 'IF NOT EXISTS' in joined
    assert 'CatalogPreparedPlan' in joined
    assert 'CatalogPreparedPlanChunk' in joined
    assert 'token_digest' in joined
    assert 'uuid' in joined
    assert 'group_id' in joined
    assert 'chunk_index' in joined
    assert 'plan_uuid' in joined
    for bad in FORBIDDEN_LABEL_SUBSTR:
        assert bad not in joined
    assert 'DROP' not in joined.upper()
    # Fixed strings only — no client interpolation markers
    assert '${' not in joined


def _valid_plan_constraint_rows() -> list[dict]:
    return [
        {
            'name': CATALOG_PREPARED_PLAN_IDENTITY_CONSTRAINT,
            'type': 'NODE_PROPERTY_UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogPreparedPlan'],
            'properties': ['uuid', 'group_id'],
        },
        {
            'name': CATALOG_PREPARED_PLAN_TOKEN_DIGEST_CONSTRAINT,
            'type': 'NODE_PROPERTY_UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogPreparedPlan'],
            'properties': ['token_digest'],
        },
        {
            'name': CATALOG_PREPARED_PLAN_CHUNK_IDENTITY_CONSTRAINT,
            'type': 'NODE_PROPERTY_UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogPreparedPlanChunk'],
            'properties': ['uuid', 'group_id'],
        },
        {
            'name': CATALOG_PREPARED_PLAN_CHUNK_INDEX_CONSTRAINT,
            'type': 'NODE_PROPERTY_UNIQUENESS',
            'entityType': 'NODE',
            'labelsOrTypes': ['CatalogPreparedPlanChunk'],
            'properties': ['plan_uuid', 'group_id', 'chunk_index'],
        },
    ]


@pytest.mark.asyncio
async def test_ensure_plan_schema_emits_create_constraint_only():
    store = CatalogNeo4jStore()
    captured: list[str] = []
    created = {'n': 0}

    class _Exec:
        async def execute_query(self, stmt: str, params=None, **kwargs):
            captured.append(stmt)
            if 'SHOW CONSTRAINTS' in stmt:
                if created['n'] < 4:
                    return ([], None, [])
                return (_valid_plan_constraint_rows(), None, [])
            if 'CREATE CONSTRAINT' in stmt:
                created['n'] += 1
            return ([], None, [])

    await store.ensure_plan_schema(_Exec())
    assert captured
    create_stmts = [s for s in captured if 'CREATE CONSTRAINT' in s]
    assert create_stmts
    for stmt in create_stmts:
        assert 'IF NOT EXISTS' in stmt
        assert 'DROP' not in stmt.upper()
        _assert_fixed_labels_only(stmt)


def test_build_create_prepared_plan_cypher_uses_create_not_merge_update():
    store = CatalogNeo4jStore()
    cypher = store.build_create_prepared_plan_cypher()
    assert 'CREATE (plan:CatalogPreparedPlan' in cypher or 'CREATE (p:CatalogPreparedPlan' in cypher
    assert 'MERGE (plan:CatalogPreparedPlan' not in cypher
    assert 'ON MATCH SET' not in cypher
    assert '$token_digest' in cypher
    assert 'token_digest' in cypher
    # raw token must never appear as a property key in Cypher
    assert 'plan_token' not in cypher
    assert 'raw_token' not in cypher
    _assert_fixed_labels_only(cypher)
    # No searchable embedding props on control root
    assert 'name_embedding' not in cypher
    assert 'fact_embedding' not in cypher


def test_build_create_prepared_plan_chunk_cypher_fixed_labels():
    store = CatalogNeo4jStore()
    cypher = store.build_create_prepared_plan_chunk_cypher()
    assert (
        'CREATE (c:CatalogPreparedPlanChunk' in cypher
        or 'CREATE (:CatalogPreparedPlanChunk' in cypher
    )
    assert 'MERGE (c:CatalogPreparedPlanChunk' not in cypher
    assert '$payload_b64' in cypher
    assert '$chunk_index' in cypher
    assert '$plan_uuid' in cypher
    assert '$group_id' in cypher
    _assert_fixed_labels_only(cypher)


def test_build_count_active_plans_cypher_prepared_and_committing_only():
    store = CatalogNeo4jStore()
    cypher = store.build_count_active_plans_cypher()
    assert 'CatalogPreparedPlan' in cypher
    assert 'PREPARED' in cypher
    assert 'COMMITTING' in cypher
    assert '$group_id' in cypher
    assert '$now' in cypher
    _assert_fixed_labels_only(cypher)


def test_build_group_lock_merge_cypher_fixed_label():
    store = CatalogNeo4jStore()
    cypher = store.build_plan_group_lock_cypher()
    assert 'MERGE (lock:CatalogPlanGroupLock {group_id: $group_id})' in cypher or (
        'CatalogPlanGroupLock' in cypher and 'MERGE' in cypher and '$group_id' in cypher
    )
    _assert_fixed_labels_only(cypher)


@pytest.mark.asyncio
async def test_create_prepared_plan_with_chunks_create_once_and_params():
    store = CatalogNeo4jStore()
    # responses: lock, count active=0, existing plan=none, create plan, create chunk
    tx = _CaptureTx(
        responses=[
            [{'locked': True}],
            [{'active': 0}],
            [],  # no existing plan
            [{'uuid': PLAN_UUID, 'state': PLAN_STATE_PREPARED}],
            [{'uuid': CHUNK_UUID_0, 'chunk_index': 0}],
        ]
    )
    plan = _plan_params()
    chunks = [_chunk_params()]
    row = await store.create_prepared_plan_with_chunks(
        tx,
        plan=plan,
        chunks=chunks,
        max_active=HARD_MAX_ACTIVE_PLANS_PER_GROUP,
        now=FIXED_TS,
    )
    assert row['uuid'] == PLAN_UUID
    joined = _all_cypher(tx)
    _assert_fixed_labels_only(joined)
    assert 'CatalogPlanGroupLock' in joined
    assert 'CREATE' in joined
    # token_digest present; raw token keys absent
    all_params = {}
    for _, p in tx.calls:
        all_params.update(p)
    assert all_params.get('token_digest') == TOKEN_DIGEST
    assert 'token' not in all_params or all_params.get('token') is None
    assert 'plan_token' not in all_params
    assert 'raw_token' not in all_params
    # CREATE used for plan/chunk (not MERGE update of artifact)
    create_calls = [c for c, _ in tx.calls if 'CREATE' in c and 'CatalogPreparedPlan' in c]
    assert create_calls
    for c in create_calls:
        assert 'ON MATCH SET' not in c


@pytest.mark.asyncio
async def test_create_capacity_rejection_when_active_at_max():
    store = CatalogNeo4jStore()
    tx = _CaptureTx(
        responses=[
            [{'locked': True}],
            [{'active': 8}],  # at max
        ]
    )
    with pytest.raises(CatalogStoreError) as exc:
        await store.create_prepared_plan_with_chunks(
            tx,
            plan=_plan_params(),
            chunks=[_chunk_params()],
            max_active=8,
            now=FIXED_TS,
        )
    assert exc.value.code in {'batch_limit_exceeded', 'prepared_plan_conflict'}
    # Must not CREATE plan after capacity fail
    joined = _all_cypher(tx)
    assert 'CREATE (plan:CatalogPreparedPlan' not in joined
    assert 'CREATE (p:CatalogPreparedPlan' not in joined


@pytest.mark.asyncio
async def test_create_same_identity_different_digest_conflicts():
    store = CatalogNeo4jStore()
    tx = _CaptureTx(
        responses=[
            [{'locked': True}],
            [{'active': 0}],
            [
                {
                    'uuid': PLAN_UUID,
                    'artifact_sha256': 'f' * 64,  # different
                    'state': PLAN_STATE_PREPARED,
                }
            ],
        ]
    )
    with pytest.raises(CatalogStoreError) as exc:
        await store.create_prepared_plan_with_chunks(
            tx,
            plan=_plan_params(),
            chunks=[_chunk_params()],
            max_active=8,
            now=FIXED_TS,
        )
    assert exc.value.code == 'prepared_plan_conflict'


@pytest.mark.asyncio
async def test_load_prepared_plan_by_token_digest_returns_root():
    store = CatalogNeo4jStore()
    cypher = store.build_load_prepared_plan_by_token_digest_cypher()
    assert 'token_digest' in cypher
    assert 'CatalogPreparedPlan' in cypher
    assert '$token_digest' in cypher
    _assert_fixed_labels_only(cypher)

    class _Exec:
        async def execute_query(self, query: str, params=None, **kwargs):
            assert params is not None
            assert params['token_digest'] == TOKEN_DIGEST
            return (
                [
                    {
                        'uuid': PLAN_UUID,
                        'group_id': GROUP,
                        'token_digest': TOKEN_DIGEST,
                        'state': PLAN_STATE_PREPARED,
                        'artifact_sha256': ARTIFACT_SHA,
                        'chunk_count': 2,
                        'payload_bytes': 32,
                    }
                ],
                None,
                [],
            )

    row = await store.load_prepared_plan_by_token_digest(_Exec(), token_digest=TOKEN_DIGEST)
    assert row is not None
    assert row['uuid'] == PLAN_UUID
    assert row['token_digest'] == TOKEN_DIGEST


@pytest.mark.asyncio
async def test_load_prepared_plan_chunks_ordered_by_index():
    store = CatalogNeo4jStore()
    cypher = store.build_load_prepared_plan_chunks_cypher()
    assert 'CatalogPreparedPlanChunk' in cypher
    assert 'ORDER BY' in cypher
    assert 'chunk_index' in cypher
    assert '$plan_uuid' in cypher
    assert '$group_id' in cypher
    _assert_fixed_labels_only(cypher)

    class _Exec:
        async def execute_query(self, query: str, params=None, **kwargs):
            return (
                [
                    _chunk_params(uuid=CHUNK_UUID_0, index=0, count=2, offset=0, length=8),
                    _chunk_params(
                        uuid=CHUNK_UUID_1,
                        index=1,
                        count=2,
                        offset=8,
                        length=8,
                        payload_b64='CgsMDQ4PEBES',
                    ),
                ],
                None,
                [],
            )

    rows = await store.load_prepared_plan_chunks(_Exec(), plan_uuid=PLAN_UUID, group_id=GROUP)
    assert [r['chunk_index'] for r in rows] == [0, 1]
    assert 'payload_b64' in rows[0]


def test_plan_write_queries_label_allowlist_only():
    store = CatalogNeo4jStore()
    builders = [
        store.build_create_prepared_plan_cypher(),
        store.build_create_prepared_plan_chunk_cypher(),
        store.build_plan_group_lock_cypher(),
        store.build_count_active_plans_cypher(),
        store.build_load_prepared_plan_by_token_digest_cypher(),
        store.build_load_prepared_plan_chunks_cypher(),
        store.build_existing_prepared_plan_cypher(),
    ]
    for cypher in builders:
        _assert_fixed_labels_only(cypher)
        # Only control-plane labels as node labels
        for label in ('Entity', 'Episodic', 'CatalogIngestBatch'):
            assert f':{label}' not in cypher


def test_create_plan_params_reject_raw_token_keys():
    store = CatalogNeo4jStore()
    params = store.prepare_prepared_plan_params(**_plan_params())
    assert 'token_digest' in params
    assert 'plan_token' not in params
    assert 'token' not in params
    assert params['state'] == PLAN_STATE_PREPARED
    assert params['payload_bytes'] == 16


# ---------------------------------------------------------------------------
# Task 2: CAS state matrix, discard, expiry, COMMITTING re-entry
# ---------------------------------------------------------------------------


def _root(
    *,
    state: str = PLAN_STATE_PREPARED,
    expires_at=EXPIRES,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        'uuid': PLAN_UUID,
        'group_id': GROUP,
        'batch_id': 'batch-001',
        'plan_id': 'batch-001|' + REQUEST_SHA,
        'token_digest': TOKEN_DIGEST,
        'state': state,
        'artifact_sha256': ARTIFACT_SHA,
        'request_sha256': REQUEST_SHA,
        'catalog_sha256': CATALOG_SHA,
        'chunk_count': 1,
        'payload_bytes': 16,
        'expires_at': expires_at,
        'created_at': FIXED_TS,
        'updated_at': FIXED_TS,
        'committing_started_at': None,
    }
    row.update(extra)
    return row


class _CasTx:
    """Tx that serves load-by-digest then optional CAS SET responses."""

    def __init__(
        self,
        *,
        current: dict[str, Any] | None,
        cas_row: dict[str, Any] | None = None,
    ) -> None:
        self.current = current
        self.cas_row = cas_row
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, **params: Any) -> _Rows:
        self.calls.append((cypher, params))
        if 'token_digest: $token_digest' in cypher and 'SET p.state' not in cypher:
            return _Rows([self.current] if self.current else [])
        if 'SET p.state' in cypher:
            if self.cas_row is not None:
                return _Rows([self.cas_row])
            if self.current and self.current.get('state') == params.get('expected_from'):
                updated = dict(self.current)
                updated['state'] = params['to_state']
                updated['updated_at'] = params.get('updated_at')
                return _Rows([updated])
            return _Rows([])
        return _Rows([])


def test_cas_cypher_no_committing_to_prepared_path():
    store = CatalogNeo4jStore()
    cypher = store.build_cas_plan_state_cypher()
    assert 'SET p.state = $to_state' in cypher
    assert '$expected_from' in cypher
    assert '$token_digest' in cypher
    assert "to_state = 'PREPARED'" not in cypher
    _assert_fixed_labels_only(cypher)
    import inspect

    src = inspect.getsource(store.cas_plan_state)
    assert 'PREPARED is forbidden' in src or 'to_state == PLAN_STATE_PREPARED' in src
    from services.catalog_store import _PLAN_CAS_LEGAL

    assert PLAN_STATE_PREPARED not in _PLAN_CAS_LEGAL.get(PLAN_STATE_COMMITTING, frozenset())
    for _frm, tos in _PLAN_CAS_LEGAL.items():
        assert PLAN_STATE_PREPARED not in tos


@pytest.mark.asyncio
async def test_cas_legal_prepared_to_discarded():
    store = CatalogNeo4jStore()
    current = _root(state=PLAN_STATE_PREPARED)
    tx = _CasTx(
        current=current,
        cas_row={**current, 'state': PLAN_STATE_DISCARDED, 'updated_at': FIXED_TS},
    )
    row = await store.cas_plan_state(
        tx,
        token_digest=TOKEN_DIGEST,
        expected_from=PLAN_STATE_PREPARED,
        to_state=PLAN_STATE_DISCARDED,
        updated_at=FIXED_TS,
    )
    assert row['state'] == PLAN_STATE_DISCARDED
    assert any('SET p.state' in c for c, _ in tx.calls)


@pytest.mark.asyncio
async def test_cas_legal_prepared_to_committing():
    store = CatalogNeo4jStore()
    current = _root(state=PLAN_STATE_PREPARED)
    tx = _CasTx(
        current=current,
        cas_row={
            **current,
            'state': PLAN_STATE_COMMITTING,
            'committing_started_at': FIXED_TS,
        },
    )
    row = await store.cas_plan_state(
        tx,
        token_digest=TOKEN_DIGEST,
        expected_from=PLAN_STATE_PREPARED,
        to_state=PLAN_STATE_COMMITTING,
        updated_at=FIXED_TS,
        now=FIXED_TS,
        require_not_expired=True,
    )
    assert row['state'] == PLAN_STATE_COMMITTING


@pytest.mark.asyncio
async def test_cas_committing_reentry_same_token():
    store = CatalogNeo4jStore()
    current = _root(state=PLAN_STATE_COMMITTING, committing_started_at=FIXED_TS)
    tx = _CasTx(current=current)
    row = await store.cas_plan_state(
        tx,
        token_digest=TOKEN_DIGEST,
        expected_from=PLAN_STATE_COMMITTING,
        to_state=PLAN_STATE_COMMITTING,
        updated_at=FIXED_TS,
    )
    assert row['state'] == PLAN_STATE_COMMITTING
    assert row.get('reentry') is True
    assert not any('SET p.state' in c for c, _ in tx.calls)


@pytest.mark.asyncio
async def test_cas_stale_prepared_expected_live_committing_reentry():
    """CR-01: same-token claim with stale PREPARED expected against live COMMITTING re-enters."""
    store = CatalogNeo4jStore()
    current = _root(state=PLAN_STATE_COMMITTING, committing_started_at=FIXED_TS)
    tx = _CasTx(current=current)
    row = await store.cas_plan_state(
        tx,
        token_digest=TOKEN_DIGEST,
        expected_from=PLAN_STATE_PREPARED,
        to_state=PLAN_STATE_COMMITTING,
        updated_at=FIXED_TS,
        now=FIXED_TS,
        require_not_expired=True,
    )
    assert row['state'] == PLAN_STATE_COMMITTING
    assert row.get('reentry') is True
    assert not any('SET p.state' in c for c, _ in tx.calls)


@pytest.mark.asyncio
async def test_cas_committed_persists_outcome_counts():
    """WR-02: COMMITTING→COMMITTED CAS may write durable outcome counts."""
    store = CatalogNeo4jStore()
    current = _root(
        state=PLAN_STATE_COMMITTING,
        committing_started_at=FIXED_TS,
        created_count=9,
        updated_count=0,
        unchanged_count=0,
    )
    cas_row = {
        **current,
        'state': PLAN_STATE_COMMITTED,
        'created_count': 1,
        'updated_count': 2,
        'unchanged_count': 3,
    }
    tx = _CasTx(current=current, cas_row=cas_row)
    row = await store.cas_plan_state(
        tx,
        token_digest=TOKEN_DIGEST,
        expected_from=PLAN_STATE_COMMITTING,
        to_state=PLAN_STATE_COMMITTED,
        updated_at=FIXED_TS,
        created_count=1,
        updated_count=2,
        unchanged_count=3,
    )
    assert row['state'] == PLAN_STATE_COMMITTED
    set_calls = [(c, p) for c, p in tx.calls if 'SET p.state' in c]
    assert set_calls
    _, params = set_calls[0]
    assert params.get('apply_outcome_counts') is True
    assert params.get('created_count') == 1
    assert params.get('updated_count') == 2
    assert params.get('unchanged_count') == 3


@pytest.mark.asyncio
async def test_cas_committing_to_committed_reserved():
    store = CatalogNeo4jStore()
    current = _root(state=PLAN_STATE_COMMITTING, committing_started_at=FIXED_TS)
    tx = _CasTx(current=current, cas_row={**current, 'state': PLAN_STATE_COMMITTED})
    row = await store.cas_plan_state(
        tx,
        token_digest=TOKEN_DIGEST,
        expected_from=PLAN_STATE_COMMITTING,
        to_state=PLAN_STATE_COMMITTED,
        updated_at=FIXED_TS,
    )
    assert row['state'] == PLAN_STATE_COMMITTED


@pytest.mark.asyncio
async def test_cas_illegal_any_to_prepared_after_create():
    store = CatalogNeo4jStore()
    for frm in (
        PLAN_STATE_PREPARED,
        PLAN_STATE_COMMITTING,
        PLAN_STATE_COMMITTED,
        PLAN_STATE_DISCARDED,
        PLAN_STATE_EXPIRED,
    ):
        tx = _CasTx(current=_root(state=frm))
        with pytest.raises(CatalogStoreError) as exc:
            await store.cas_plan_state(
                tx,
                token_digest=TOKEN_DIGEST,
                expected_from=frm,
                to_state=PLAN_STATE_PREPARED,
                updated_at=FIXED_TS,
            )
        assert exc.value.code in {'prepared_plan_conflict', 'validation_error'}


@pytest.mark.asyncio
async def test_cas_illegal_terminal_revival():
    store = CatalogNeo4jStore()
    tx = _CasTx(current=_root(state=PLAN_STATE_DISCARDED))
    with pytest.raises(CatalogStoreError) as exc:
        await store.cas_plan_state(
            tx,
            token_digest=TOKEN_DIGEST,
            expected_from=PLAN_STATE_DISCARDED,
            to_state=PLAN_STATE_COMMITTING,
            updated_at=FIXED_TS,
        )
    assert exc.value.code in {'prepared_plan_conflict', 'prepared_plan_not_found'}

    tx2 = _CasTx(current=_root(state=PLAN_STATE_EXPIRED))
    with pytest.raises(CatalogStoreError) as exc2:
        await store.cas_plan_state(
            tx2,
            token_digest=TOKEN_DIGEST,
            expected_from=PLAN_STATE_EXPIRED,
            to_state=PLAN_STATE_COMMITTING,
            updated_at=FIXED_TS,
        )
    assert exc2.value.code in {'prepared_plan_conflict', 'prepared_plan_expired'}

    tx3 = _CasTx(current=_root(state=PLAN_STATE_COMMITTED))
    with pytest.raises(CatalogStoreError) as exc3:
        await store.cas_plan_state(
            tx3,
            token_digest=TOKEN_DIGEST,
            expected_from=PLAN_STATE_COMMITTED,
            to_state=PLAN_STATE_COMMITTING,
            updated_at=FIXED_TS,
        )
    assert exc3.value.code in {
        'prepared_plan_conflict',
        'prepared_plan_already_consumed',
    }


@pytest.mark.asyncio
async def test_discard_idempotent_already_discarded():
    store = CatalogNeo4jStore()
    tx = _CasTx(current=_root(state=PLAN_STATE_DISCARDED))
    row = await store.cas_plan_state(
        tx,
        token_digest=TOKEN_DIGEST,
        expected_from=PLAN_STATE_PREPARED,
        to_state=PLAN_STATE_DISCARDED,
        updated_at=FIXED_TS,
    )
    assert row['state'] == PLAN_STATE_DISCARDED
    assert row.get('idempotent') is True


@pytest.mark.asyncio
async def test_discard_conflict_when_committing_or_committed():
    store = CatalogNeo4jStore()
    for st in (PLAN_STATE_COMMITTING, PLAN_STATE_COMMITTED):
        tx = _CasTx(current=_root(state=st))
        with pytest.raises(CatalogStoreError) as exc:
            await store.cas_plan_state(
                tx,
                token_digest=TOKEN_DIGEST,
                expected_from=PLAN_STATE_PREPARED,
                to_state=PLAN_STATE_DISCARDED,
                updated_at=FIXED_TS,
            )
        assert exc.value.code == 'prepared_plan_conflict'


@pytest.mark.asyncio
async def test_cas_expiry_only_from_prepared_when_due():
    store = CatalogNeo4jStore()
    past = FIXED_TS - timedelta(hours=1)
    current = _root(state=PLAN_STATE_PREPARED, expires_at=past)
    tx = _CasTx(current=current, cas_row={**current, 'state': PLAN_STATE_EXPIRED})
    row = await store.cas_plan_state(
        tx,
        token_digest=TOKEN_DIGEST,
        expected_from=PLAN_STATE_PREPARED,
        to_state=PLAN_STATE_EXPIRED,
        updated_at=FIXED_TS,
        now=FIXED_TS,
    )
    assert row['state'] == PLAN_STATE_EXPIRED

    tx2 = _CasTx(current=_root(state=PLAN_STATE_PREPARED, expires_at=EXPIRES))
    with pytest.raises(CatalogStoreError) as exc:
        await store.cas_plan_state(
            tx2,
            token_digest=TOKEN_DIGEST,
            expected_from=PLAN_STATE_PREPARED,
            to_state=PLAN_STATE_EXPIRED,
            updated_at=FIXED_TS,
            now=FIXED_TS,
        )
    assert exc.value.code == 'prepared_plan_conflict'


@pytest.mark.asyncio
async def test_cas_missing_plan_not_found():
    store = CatalogNeo4jStore()
    tx = _CasTx(current=None)
    with pytest.raises(CatalogStoreError) as exc:
        await store.cas_plan_state(
            tx,
            token_digest=TOKEN_DIGEST,
            expected_from=PLAN_STATE_PREPARED,
            to_state=PLAN_STATE_DISCARDED,
            updated_at=FIXED_TS,
        )
    assert exc.value.code == 'prepared_plan_not_found'


@pytest.mark.asyncio
async def test_cas_consumed_maps_already_consumed():
    store = CatalogNeo4jStore()
    tx = _CasTx(current=_root(state=PLAN_STATE_COMMITTED))
    with pytest.raises(CatalogStoreError) as exc:
        await store.cas_plan_state(
            tx,
            token_digest=TOKEN_DIGEST,
            expected_from=PLAN_STATE_PREPARED,
            to_state=PLAN_STATE_COMMITTING,
            updated_at=FIXED_TS,
        )
    assert exc.value.code == 'prepared_plan_already_consumed'


@pytest.mark.asyncio
async def test_cas_claim_expired_prepared_maps_expired():
    store = CatalogNeo4jStore()
    past = FIXED_TS - timedelta(seconds=1)
    current = _root(state=PLAN_STATE_PREPARED, expires_at=past)
    tx = _CasTx(current=current, cas_row={**current, 'state': PLAN_STATE_EXPIRED})
    with pytest.raises(CatalogStoreError) as exc:
        await store.cas_plan_state(
            tx,
            token_digest=TOKEN_DIGEST,
            expected_from=PLAN_STATE_PREPARED,
            to_state=PLAN_STATE_COMMITTING,
            updated_at=FIXED_TS,
            now=FIXED_TS,
            require_not_expired=True,
        )
    assert exc.value.code == 'prepared_plan_expired'


def test_cas_table_driven_legal_and_illegal_matrix():
    """Static matrix: legal edges present; illegal absent (PLAN-18)."""
    from services.catalog_store import _PLAN_CAS_LEGAL

    legal = {
        (PLAN_STATE_PREPARED, PLAN_STATE_DISCARDED),
        (PLAN_STATE_PREPARED, PLAN_STATE_EXPIRED),
        (PLAN_STATE_PREPARED, PLAN_STATE_COMMITTING),
        (PLAN_STATE_COMMITTING, PLAN_STATE_COMMITTING),
        (PLAN_STATE_COMMITTING, PLAN_STATE_COMMITTED),
    }
    for frm, to in legal:
        assert to in _PLAN_CAS_LEGAL[frm], f'missing legal {frm}->{to}'

    illegal = [
        (PLAN_STATE_COMMITTING, PLAN_STATE_PREPARED),
        (PLAN_STATE_COMMITTED, PLAN_STATE_PREPARED),
        (PLAN_STATE_DISCARDED, PLAN_STATE_COMMITTING),
        (PLAN_STATE_EXPIRED, PLAN_STATE_COMMITTING),
        (PLAN_STATE_COMMITTED, PLAN_STATE_COMMITTING),
        (PLAN_STATE_DISCARDED, PLAN_STATE_PREPARED),
        (PLAN_STATE_EXPIRED, PLAN_STATE_PREPARED),
        (PLAN_STATE_PREPARED, PLAN_STATE_PREPARED),
        (PLAN_STATE_PREPARED, PLAN_STATE_COMMITTED),
    ]
    for frm, to in illegal:
        allowed = _PLAN_CAS_LEGAL.get(frm, frozenset())
        assert to not in allowed, f'illegal edge present {frm}->{to}'


def test_discard_never_detach_delete_domain():
    store = CatalogNeo4jStore()
    cypher = store.build_cas_plan_state_cypher()
    assert 'DETACH DELETE' not in cypher
    assert 'DELETE' not in cypher
    for bad in FORBIDDEN_LABEL_SUBSTR:
        assert bad not in cypher


@pytest.mark.asyncio
async def test_ensure_plan_schema_idempotent_and_verifies_shape():
    store = CatalogNeo4jStore()
    calls: list[str] = []
    created = {'n': 0}

    class _Exec:
        async def execute_query(self, cypher: str, params=None, **kwargs):
            _ = (0 if params is None else 1) + len(kwargs)
            calls.append(cypher.strip())
            if 'SHOW CONSTRAINTS' in cypher:
                if created['n'] < 4:
                    return ([], None, [])
                return (_valid_plan_constraint_rows(), None, [])
            if 'CREATE CONSTRAINT' in cypher:
                created['n'] += 1
            return ([], None, [])

    exec1 = _Exec()
    await store.ensure_plan_schema(exec1)
    assert store._plan_schema_ready is True
    assert sum(1 for c in calls if 'CREATE CONSTRAINT' in c) == 4
    assert sum(1 for c in calls if 'SHOW CONSTRAINTS' in c) >= 2
    assert all('DROP' not in c.upper() for c in calls)
    n_before = len(calls)
    await store.ensure_plan_schema(exec1)
    assert len(calls) == n_before


@pytest.mark.asyncio
async def test_ensure_plan_schema_fails_closed_without_verified_shape():
    store = CatalogNeo4jStore()

    class _Exec:
        async def execute_query(self, cypher: str, params=None, **kwargs):
            _ = params, kwargs
            if 'SHOW CONSTRAINTS' in cypher:
                return (
                    [
                        {
                            'name': CATALOG_PREPARED_PLAN_IDENTITY_CONSTRAINT,
                            'type': 'UNIQUENESS',
                            'entityType': 'NODE',
                            'labelsOrTypes': ['CatalogPreparedPlan'],
                            'properties': ['uuid'],  # missing group_id
                        }
                    ],
                    None,
                    [],
                )
            return ([], None, [])

    with pytest.raises(CatalogStoreError) as ei:
        await store.ensure_plan_schema(_Exec())
    assert ei.value.code == 'neo4j_schema_failed'
    assert store._plan_schema_ready is False


@pytest.mark.asyncio
async def test_create_uniqueness_race_maps_prepared_plan_conflict():
    store = CatalogNeo4jStore()

    class _RaceTx:
        def __init__(self):
            self.n = 0

        async def run(self, cypher: str, **params):
            self.n += 1
            if 'CatalogPlanGroupLock' in cypher:
                return _Rows([{'locked': True}])
            if 'RETURN count(p) AS active' in cypher or 'AS active' in cypher:
                return _Rows([{'active': 0}])
            if 'MATCH (p:CatalogPreparedPlan' in cypher and 'CREATE' not in cypher:
                return _Rows([])
            if (
                'CREATE (plan:CatalogPreparedPlan' in cypher
                or 'CREATE (p:CatalogPreparedPlan' in cypher
            ):
                raise RuntimeError('ConstraintValidationFailed: already exists with label')
            return _Rows([])

    with pytest.raises(CatalogStoreError) as ei:
        await store.create_prepared_plan_with_chunks(
            _RaceTx(),
            plan=_plan_params(),
            chunks=[_chunk_params()],
            max_active=8,
            now=FIXED_TS,
        )
    assert ei.value.code == 'prepared_plan_conflict'


def test_prepare_prepared_plan_params_default_canonicalization_version():
    store = CatalogNeo4jStore()
    params = _plan_params()
    params.pop('canonicalization_version', None)
    out = store.prepare_prepared_plan_params(**params)
    assert out['canonicalization_version'] == 'catalog-canonical-v1'
