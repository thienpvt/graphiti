"""Unit tests for prepare/commit/discard models and plan limit clamps (PLAN-01/08/10)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_prepare import (  # noqa: E402
    CommitPreparedCatalogBatchRequest,
    DiscardPreparedCatalogBatchRequest,
    PrepareCatalogBatchRequest,
)
from models.catalog_responses import (  # noqa: E402
    CommitPreparedCatalogBatchResponse,
    DiscardPreparedCatalogBatchResponse,
    PrepareCatalogBatchResponse,
)

FIXED_SHA = 'a' * 64
GROUP = 'oracle-catalog-tool-test'


def _entity_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'ORCL.HR.EMPLOYEES',
        'summary': 'Employee master table',
    }
    base.update(overrides)
    return base


def _prepare_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': GROUP,
        'batch_id': 'batch-1',
        'catalog_sha256': FIXED_SHA,
        'entities': [_entity_kwargs()],
        'edges': [],
        'atomic': True,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# PLAN-01 — PrepareCatalogBatchRequest
# ---------------------------------------------------------------------------


def test_prepare_accepts_full_valid_catalog_v2_batch_domain():
    req = PrepareCatalogBatchRequest.model_validate(_prepare_body())
    assert req.group_id == GROUP
    assert req.batch_id == 'batch-1'
    assert req.identity_schema_version == 'catalog-v2'
    assert req.system_key == 'FE'
    assert req.catalog_sha256 == FIXED_SHA
    assert len(req.entities) == 1
    assert req.atomic is True
    assert not hasattr(req, 'dry_run')
    assert 'dry_run' not in PrepareCatalogBatchRequest.model_fields


def test_prepare_rejects_dry_run_field():
    with pytest.raises(ValidationError) as exc:
        PrepareCatalogBatchRequest.model_validate(_prepare_body(dry_run=False))
    assert 'dry_run' in str(exc.value)


def test_prepare_rejects_unknown_extra_field():
    with pytest.raises(ValidationError) as exc:
        PrepareCatalogBatchRequest.model_validate(_prepare_body(plan_token='nope'))
    assert 'plan_token' in str(exc.value)


def test_prepare_rejects_unknown_nested_entity_field():
    with pytest.raises(ValidationError) as exc:
        PrepareCatalogBatchRequest.model_validate(
            _prepare_body(entities=[{**_entity_kwargs(), 'typo_nested': 1}])
        )
    assert 'typo_nested' in str(exc.value)


def test_prepare_rejects_empty_all_collections():
    with pytest.raises(ValidationError):
        PrepareCatalogBatchRequest.model_validate(
            _prepare_body(entities=[], edges=[], provenance=None)
        )


def test_prepare_rejects_null_required_shell():
    with pytest.raises(ValidationError):
        PrepareCatalogBatchRequest.model_validate(
            {
                'identity_schema_version': 'catalog-v2',
                'system_key': 'FE',
                'group_id': None,
                'batch_id': 'batch-1',
                'catalog_sha256': FIXED_SHA,
                'entities': [_entity_kwargs()],
            }
        )


def test_prepare_accepts_single_entity_shell():
    req = PrepareCatalogBatchRequest.model_validate(_prepare_body())
    assert len(req.entities) == 1


def test_prepare_accepts_optional_request_sha256():
    req = PrepareCatalogBatchRequest.model_validate(
        _prepare_body(request_sha256=FIXED_SHA)
    )
    assert req.request_sha256 == FIXED_SHA


# ---------------------------------------------------------------------------
# PLAN-10 — CommitPreparedCatalogBatchRequest
# ---------------------------------------------------------------------------


def test_commit_accepts_token_only():
    req = CommitPreparedCatalogBatchRequest.model_validate({'plan_token': 'tok_' + 'x' * 20})
    assert req.plan_token.startswith('tok_')
    assert req.expected_request_sha256 is None


def test_commit_accepts_optional_expected_request_sha256():
    req = CommitPreparedCatalogBatchRequest.model_validate(
        {
            'plan_token': 'tok_' + 'y' * 20,
            'expected_request_sha256': FIXED_SHA,
        }
    )
    assert req.expected_request_sha256 == FIXED_SHA


def test_commit_rejects_empty_plan_token():
    with pytest.raises(ValidationError):
        CommitPreparedCatalogBatchRequest.model_validate({'plan_token': ''})


def test_commit_rejects_plan_token_over_max():
    with pytest.raises(ValidationError):
        CommitPreparedCatalogBatchRequest.model_validate({'plan_token': 't' * 129})


def test_commit_accepts_plan_token_at_max():
    req = CommitPreparedCatalogBatchRequest.model_validate({'plan_token': 't' * 128})
    assert len(req.plan_token) == 128


def test_commit_rejects_malformed_expected_request_sha256():
    with pytest.raises(ValidationError):
        CommitPreparedCatalogBatchRequest.model_validate(
            {
                'plan_token': 'tok_ok_token_value_here',
                'expected_request_sha256': 'not-hex',
            }
        )
    with pytest.raises(ValidationError):
        CommitPreparedCatalogBatchRequest.model_validate(
            {
                'plan_token': 'tok_ok_token_value_here',
                'expected_request_sha256': 'A' * 64,  # uppercase rejected
            }
        )


@pytest.mark.parametrize(
    'forbidden_key',
    [
        'group_id',
        'batch_id',
        'entities',
        'edges',
        'sources',
        'evidence_links',
        'catalog_sha256',
        'atomic',
        'dry_run',
        'provenance',
        'system_key',
        'identity_schema_version',
        'request_sha256',
    ],
)
def test_commit_rejects_replacement_payload_fields(forbidden_key: str):
    payload: dict[str, Any] = {'plan_token': 'tok_ok_token_value_here', forbidden_key: 'x'}
    with pytest.raises(ValidationError) as exc:
        CommitPreparedCatalogBatchRequest.model_validate(payload)
    assert forbidden_key in str(exc.value)


def test_commit_field_set_exactly_token_and_optional_hash():
    fields = set(CommitPreparedCatalogBatchRequest.model_fields)
    assert fields == {'plan_token', 'expected_request_sha256'}


# ---------------------------------------------------------------------------
# PLAN-19 model surface — DiscardPreparedCatalogBatchRequest
# ---------------------------------------------------------------------------


def test_discard_accepts_token_only():
    req = DiscardPreparedCatalogBatchRequest.model_validate(
        {'plan_token': 'tok_discard_token_value'}
    )
    assert req.plan_token == 'tok_discard_token_value'


def test_discard_rejects_empty_plan_token():
    with pytest.raises(ValidationError):
        DiscardPreparedCatalogBatchRequest.model_validate({'plan_token': ''})


def test_discard_rejects_plan_token_over_max():
    with pytest.raises(ValidationError):
        DiscardPreparedCatalogBatchRequest.model_validate({'plan_token': 't' * 129})


@pytest.mark.parametrize(
    'forbidden_key',
    [
        'group_id',
        'batch_id',
        'entities',
        'edges',
        'sources',
        'evidence_links',
        'catalog_sha256',
        'expected_request_sha256',
        'atomic',
        'dry_run',
    ],
)
def test_discard_rejects_extra_fields(forbidden_key: str):
    payload: dict[str, Any] = {'plan_token': 'tok_discard_token_value', forbidden_key: 'x'}
    with pytest.raises(ValidationError) as exc:
        DiscardPreparedCatalogBatchRequest.model_validate(payload)
    assert forbidden_key in str(exc.value)


def test_discard_field_set_exactly_token():
    assert set(DiscardPreparedCatalogBatchRequest.model_fields) == {'plan_token'}


# ---------------------------------------------------------------------------
# Response receipts — shape only (no payload/embeddings)
# ---------------------------------------------------------------------------


def test_prepare_response_receipt_fields_no_payload():
    resp = PrepareCatalogBatchResponse(
        plan_token='tok_once',
        plan_uuid='11111111-1111-1111-1111-111111111111',
        request_sha256=FIXED_SHA,
        catalog_sha256=FIXED_SHA,
        artifact_sha256=FIXED_SHA,
        identity_schema_version='catalog-v2',
        expires_at='2026-07-18T12:00:00+00:00',
        entity_count=1,
        edge_count=0,
        source_count=0,
        evidence_link_count=0,
        projected_created=1,
        projected_updated=0,
        projected_unchanged=0,
    )
    dumped = resp.model_dump()
    assert 'payload' not in dumped
    assert 'embeddings' not in dumped
    assert 'membership' not in dumped
    assert dumped['plan_token'] == 'tok_once'
    assert dumped['entity_count'] == 1


def test_commit_response_receipt_fields_no_membership():
    resp = CommitPreparedCatalogBatchResponse(
        plan_uuid='11111111-1111-1111-1111-111111111111',
        request_sha256=FIXED_SHA,
        catalog_sha256=FIXED_SHA,
        artifact_sha256=FIXED_SHA,
        state='COMMITTING',
        entity_count=1,
        edge_count=0,
        source_count=0,
        evidence_link_count=0,
    )
    dumped = resp.model_dump()
    assert 'membership' not in dumped
    assert 'payload' not in dumped
    assert 'embeddings' not in dumped
    assert 'plan_token' not in dumped
    assert dumped['state'] == 'COMMITTING'


def test_discard_response_state_discarded():
    resp = DiscardPreparedCatalogBatchResponse(
        plan_uuid='11111111-1111-1111-1111-111111111111',
        state='DISCARDED',
    )
    assert resp.state == 'DISCARDED'


# ---------------------------------------------------------------------------
# PLAN-08 — HARD_* ceilings + CatalogConfig clamps
# ---------------------------------------------------------------------------


def test_hard_plan_ceiling_constants():
    from models.catalog_common import (
        DEFAULT_MAX_ACTIVE_PLANS_PER_GROUP,
        DEFAULT_PLAN_TTL_SECONDS,
        DEFAULT_PREPARED_CHUNK_BYTES,
        DEFAULT_PREPARED_PAYLOAD_BYTES,
        HARD_MAX_ACTIVE_PLANS_PER_GROUP,
        HARD_MAX_CHUNKS_PER_PLAN,
        HARD_MAX_PREPARED_PAYLOAD_BYTES,
        HARD_PLAN_TTL_SECONDS,
        HARD_PREPARED_CHUNK_BYTES,
        PLAN_STATE_COMMITTED,
        PLAN_STATE_COMMITTING,
        PLAN_STATE_DISCARDED,
        PLAN_STATE_EXPIRED,
        PLAN_STATE_PREPARED,
    )

    assert HARD_PLAN_TTL_SECONDS == 86400
    assert DEFAULT_PLAN_TTL_SECONDS == 3600
    assert HARD_MAX_PREPARED_PAYLOAD_BYTES == 16_777_216
    assert DEFAULT_PREPARED_PAYLOAD_BYTES == 4_194_304
    assert HARD_PREPARED_CHUNK_BYTES == 262_144
    assert DEFAULT_PREPARED_CHUNK_BYTES == 131_072
    assert HARD_MAX_CHUNKS_PER_PLAN == 128
    assert HARD_MAX_ACTIVE_PLANS_PER_GROUP == 32
    assert DEFAULT_MAX_ACTIVE_PLANS_PER_GROUP == 8
    assert PLAN_STATE_PREPARED == 'PREPARED'
    assert PLAN_STATE_COMMITTING == 'COMMITTING'
    assert PLAN_STATE_COMMITTED == 'COMMITTED'
    assert PLAN_STATE_DISCARDED == 'DISCARDED'
    assert PLAN_STATE_EXPIRED == 'EXPIRED'


def test_catalog_config_plan_ttl_defaults_and_clamps():
    from config.schema import CatalogConfig
    from models.catalog_common import HARD_PLAN_TTL_SECONDS

    cfg = CatalogConfig()
    assert cfg.plan_ttl_seconds == 3600
    cfg_max = CatalogConfig(plan_ttl_seconds=HARD_PLAN_TTL_SECONDS)
    assert cfg_max.plan_ttl_seconds == HARD_PLAN_TTL_SECONDS
    with pytest.raises(ValidationError):
        CatalogConfig(plan_ttl_seconds=HARD_PLAN_TTL_SECONDS + 1)
    with pytest.raises(ValidationError):
        CatalogConfig(plan_ttl_seconds=0)


def test_catalog_config_prepared_payload_clamps():
    from config.schema import CatalogConfig
    from models.catalog_common import HARD_MAX_PREPARED_PAYLOAD_BYTES

    cfg = CatalogConfig()
    assert cfg.max_prepared_payload_bytes == 4_194_304
    cfg_max = CatalogConfig(max_prepared_payload_bytes=HARD_MAX_PREPARED_PAYLOAD_BYTES)
    assert cfg_max.max_prepared_payload_bytes == HARD_MAX_PREPARED_PAYLOAD_BYTES
    with pytest.raises(ValidationError):
        CatalogConfig(max_prepared_payload_bytes=HARD_MAX_PREPARED_PAYLOAD_BYTES + 1)


def test_catalog_config_prepared_chunk_clamps():
    from config.schema import CatalogConfig
    from models.catalog_common import HARD_PREPARED_CHUNK_BYTES

    cfg = CatalogConfig()
    assert cfg.prepared_chunk_bytes == 131_072
    cfg_max = CatalogConfig(prepared_chunk_bytes=HARD_PREPARED_CHUNK_BYTES)
    assert cfg_max.prepared_chunk_bytes == HARD_PREPARED_CHUNK_BYTES
    with pytest.raises(ValidationError):
        CatalogConfig(prepared_chunk_bytes=HARD_PREPARED_CHUNK_BYTES + 1)


def test_catalog_config_active_plans_clamps():
    from config.schema import CatalogConfig
    from models.catalog_common import HARD_MAX_ACTIVE_PLANS_PER_GROUP

    cfg = CatalogConfig()
    assert cfg.max_active_plans_per_group == 8
    cfg_max = CatalogConfig(max_active_plans_per_group=HARD_MAX_ACTIVE_PLANS_PER_GROUP)
    assert cfg_max.max_active_plans_per_group == HARD_MAX_ACTIVE_PLANS_PER_GROUP
    with pytest.raises(ValidationError):
        CatalogConfig(max_active_plans_per_group=HARD_MAX_ACTIVE_PLANS_PER_GROUP + 1)
