#!/usr/bin/env python3
"""Submit one immutable catalog canary artifact through MCP Streamable HTTP."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MCP_SRC = ROOT / 'mcp_server' / 'src'
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from models.catalog_batch import NestedProvenancePayload, UpsertCatalogBatchRequest  # noqa: E402
from models.catalog_edges import CatalogEdgeItem  # noqa: E402
from models.catalog_entities import CatalogEntityItem  # noqa: E402
from models.catalog_evidence import CatalogEvidenceLink  # noqa: E402
from models.catalog_prepare import (  # noqa: E402
    CommitPreparedCatalogBatchRequest,
    PrepareCatalogBatchRequest,
)
from models.catalog_provenance import (  # noqa: E402
    CatalogProvenanceEdgeTarget,
    CatalogProvenanceEntityTarget,
    CatalogSourceItem,
)
from models.catalog_responses import (  # noqa: E402
    CatalogBatchWriteResponse,
    CatalogIngestStatusResponse,
    ResolveTypedEntitiesResponse,
    VerifyCatalogBatchResponse,
)
from pydantic import ValidationError  # noqa: E402
from services.catalog_identity import canonical_sha256  # noqa: E402
from services.catalog_service import CatalogService  # noqa: E402

TARGET_GROUP_ID = 'oracle-catalog-v2'
CATALOG_SHA256 = '3882cb4bc50064215ead782b0fa0dfbf0098cb344b50184e6c207145377e832f'
DOCUMENT_GRAPH_KEY = 'DOC::docling-14451470779352042667'
MALFORMED_DOCUMENT_ID = 'docling-144514770779352042667'
DEFAULT_CHECKPOINT = ROOT / 'catalog' / 'catalog.json.graphiti-canary-v2-state.json'
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
ARTIFACT_FIELDS = {
    'group_id',
    'batch_id',
    'catalog_sha256',
    'atomic',
    'entities',
    'edges',
    'provenance',
}

# Phase 5 offline hardened path (IDEN-13 / DOCS-06). Historical EXPECTED_BATCHES remain
# inventory only and are invalid as hardened authority (D-05, D-11).
HARDENED_ARTIFACT_FIELDS = {
    'identity_schema_version',
    'system_key',
    'group_id',
    'batch_id',
    'catalog_sha256',
    'atomic',
    'entities',
    'edges',
    'provenance',
}
HARDENED_IDENTITY_SCHEMA_VERSION = 'catalog-v2'
HARDENED_SYSTEM_KEY = 'FE'
HARDENED_GROUP_ID = 'oracle-catalog-tool-test'
FUTURE_TARGET_GROUP_METADATA = 'oracle-catalog-v2'  # metadata only; never transported
HARDENED_ARTIFACT_DIR = ROOT / 'catalog' / 'canary-v2-requests-hardened'
HISTORICAL_ARTIFACT_DIR = ROOT / 'catalog' / 'canary-v2-requests'
HISTORICAL_ACCEPT_TAB_REQUEST_SHA256 = (
    'a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a'
)

# Preferred future execution sequence — never live-invoked in Phase 5 (D-10).
COMMIT_TOOL_SEQUENCE = [
    'prepare_catalog_batch',
    'commit_prepared_catalog_batch',
    'get_catalog_ingest_status',
    'verify_catalog_batch',
    'resolve_typed_entities',
    'get_catalog_batch_manifest',
    'get_catalog_evidence',
    'search_nodes',
    'search_memory_facts',
]
PROHIBITED_LEGACY_TOOLS = {
    'add_memory',
    'add_triplet',
    'build_communities',
    'clear_graph',
    'delete_entity_edge',
    'delete_episode',
    'summarize_saga',
    'update_entity',
    'upsert_provenance',
    'upsert_typed_edges',
    'upsert_typed_entities',
    'upsert_catalog_batch',  # historical direct upsert is not hardened authority
}

EXPECTED_BATCHES: dict[str, dict[str, Any]] = {
    'canary-v2::accept-tab': {
        'filename': 'accept-tab.payload.json',
        'artifact_sha256': 'a89e3427a3b1ceec10f36d361fcdbe9e7e30243db4ff51ca59848dfb33968a33',
        'request_sha256': 'a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a',
        'entity_types': {
            'DictionaryDocument': 1,
            'Schema': 1,
            'Table': 1,
            'Column': 6,
            'Index': 1,
        },
        'edge_types': {'Contains': 9, 'DocumentedBy': 7},
        'provenance': (1, 10, 16),
    },
    'canary-v2::form-cfg': {
        'filename': 'form-cfg.payload.json',
        'artifact_sha256': '5ccc52d84909cf436ade1cffae626e2d667834dc8b96fb4efa73d8f658315b53',
        'request_sha256': '021cbd1a00fd628d15519282588dad58d4fa3f7a768ac914f3a1016ec282897a',
        'entity_types': {
            'DictionaryDocument': 1,
            'Schema': 1,
            'Table': 1,
            'Column': 3,
        },
        'edge_types': {'Contains': 4, 'DocumentedBy': 4},
        'provenance': (1, 6, 8),
    },
    'canary-v2::pre-auth-txn-type': {
        'filename': 'pre-auth-txn-type.payload.json',
        'artifact_sha256': '731cf0db7319ae963f31325b66eace8469424977f6120d4260f398a3524b9750',
        'request_sha256': '28210a6670e13086081dcefd0494e31ed5fca89d0701f247d68e2541c173c68b',
        'entity_types': {
            'DictionaryDocument': 1,
            'Schema': 1,
            'Table': 1,
            'Column': 6,
            'Constraint': 3,
            'Index': 3,
        },
        'edge_types': {'Contains': 27, 'DocumentedBy': 7},
        'provenance': (1, 15, 34),
    },
    'canary-v2::trans-type': {
        'filename': 'trans-type.payload.json',
        'artifact_sha256': 'ee5f73669d5cba175d21967e7502d292009fed67520b6a0d582478730a327944',
        'request_sha256': 'fcf59877c6971e2c0c27a4305197126c490e3b6e37f7cd64d5f8a7324b4ffcce',
        'entity_types': {
            'DictionaryDocument': 1,
            'Schema': 1,
            'Table': 1,
            'Column': 4,
            'Constraint': 2,
        },
        'edge_types': {'Contains': 9, 'DocumentedBy': 5, 'PrimaryKeyOf': 1},
        'provenance': (1, 9, 15),
    },
    'canary-v2::trans-type-class': {
        'filename': 'trans-type-class.payload.json',
        'artifact_sha256': '003ae7f6a5f06811ae6f74fdc7f964c481cfdb4215e2a79e0779aab4affcac60',
        'request_sha256': 'a9cf4cf2fd70a518a19e3ade1894c3acf209f62db9154c4849e42668b27ddd75',
        'entity_types': {
            'DictionaryDocument': 1,
            'Schema': 1,
            'Table': 1,
            'Column': 2,
            'Constraint': 1,
        },
        'edge_types': {'Contains': 5, 'DocumentedBy': 3, 'PrimaryKeyOf': 1},
        'provenance': (1, 6, 9),
    },
    'canary-v2::documented-foreign-keys': {
        'filename': 'documented-foreign-keys.payload.json',
        'artifact_sha256': '6a02bc60ab29b88633e7614d3687c95678375a941e59c8bbcc4e536df13d801e',
        'request_sha256': 'b395ae2cdfa43ee1ceecfba5ff42e38a085d5033a54601539d0d549960be976f',
        'entity_types': {},
        'edge_types': {'ForeignKeyTo': 3},
        'provenance': (1, 0, 3),
    },
}


class RunnerError(RuntimeError):
    """Fail-closed runner error safe to print without transport details."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RunnerError('duplicate_json_key', f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise RunnerError('non_finite_json', f'non-finite JSON number: {value}')


def strict_json_loads(data: bytes) -> Any:
    """Decode strict UTF-8 JSON with duplicate and non-finite rejection."""
    if data.startswith(b'\xef\xbb\xbf'):
        raise RunnerError('utf8_bom', 'JSON must not contain a UTF-8 BOM')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise RunnerError('invalid_utf8', 'JSON is not valid UTF-8') from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_non_finite,
        )
    except RunnerError:
        raise
    except json.JSONDecodeError as exc:
        raise RunnerError(
            'invalid_json', f'invalid JSON at line {exc.lineno}, column {exc.colno}'
        ) from exc


def strict_json_load(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_bytes())
    except OSError as exc:
        raise RunnerError('file_read_failed', f'cannot read {path.name}') from exc


def canonical_artifact_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise RunnerError('non_canonical_json', 'artifact is not canonical JSON data') from exc
    return encoded + b'\n'


def _require_exact_fields(raw: Any, expected: set[str], path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RunnerError('invalid_shape', f'{path} must be an object')
    actual = set(raw)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise RunnerError(
            'field_set_mismatch',
            f'{path} field mismatch; missing={missing}, unknown={unknown}',
        )
    return raw


def _validate_raw_field_sets(raw: dict[str, Any]) -> None:
    _require_exact_fields(raw, ARTIFACT_FIELDS, '$')
    entities = raw.get('entities')
    edges = raw.get('edges')
    provenance = raw.get('provenance')
    if not isinstance(entities, list) or not isinstance(edges, list):
        raise RunnerError('invalid_shape', '$.entities and $.edges must be arrays')
    for index, item in enumerate(entities):
        _require_exact_fields(item, set(CatalogEntityItem.model_fields), f'$.entities[{index}]')
    for index, item in enumerate(edges):
        _require_exact_fields(item, set(CatalogEdgeItem.model_fields), f'$.edges[{index}]')
    _require_exact_fields(provenance, set(NestedProvenancePayload.model_fields), '$.provenance')
    sources = provenance.get('sources')
    entity_targets = provenance.get('entity_targets')
    edge_targets = provenance.get('edge_targets')
    if not all(isinstance(items, list) for items in (sources, entity_targets, edge_targets)):
        raise RunnerError('invalid_shape', 'provenance collections must be arrays')
    for index, item in enumerate(sources):
        _require_exact_fields(
            item, set(CatalogSourceItem.model_fields), f'$.provenance.sources[{index}]'
        )
    for index, item in enumerate(entity_targets):
        _require_exact_fields(
            item,
            set(CatalogProvenanceEntityTarget.model_fields),
            f'$.provenance.entity_targets[{index}]',
        )
    for index, item in enumerate(edge_targets):
        _require_exact_fields(
            item,
            set(CatalogProvenanceEdgeTarget.model_fields),
            f'$.provenance.edge_targets[{index}]',
        )


def _validate_content_hashes(request: UpsertCatalogBatchRequest) -> None:
    for index, item in enumerate(request.entities):
        expected = canonical_sha256(CatalogService.entity_canonical_payload(item))
        if item.content_sha256 != expected:
            raise RunnerError(
                'content_hash_mismatch', f'entity content hash mismatch at index {index}'
            )
    for index, item in enumerate(request.edges):
        expected = canonical_sha256(CatalogService.edge_canonical_payload(item))
        if item.content_sha256 != expected:
            raise RunnerError(
                'content_hash_mismatch', f'edge content hash mismatch at index {index}'
            )
    if request.provenance is None:
        raise RunnerError('missing_provenance', 'artifact provenance is required')
    for index, item in enumerate(request.provenance.sources):
        expected = canonical_sha256(CatalogService.source_canonical_payload(item))
        if item.content_sha256 != expected:
            raise RunnerError(
                'content_hash_mismatch',
                f'provenance source content hash mismatch at index {index}',
            )


def _validate_identities_and_endpoints(request: UpsertCatalogBatchRequest) -> None:
    entity_ids = [(item.entity_type, item.graph_key) for item in request.entities]
    edge_ids = [(item.edge_type, item.edge_key) for item in request.edges]
    if len(entity_ids) != len(set(entity_ids)):
        raise RunnerError(
            'duplicate_entity_identity', 'artifact contains duplicate entity identity'
        )
    if len(edge_ids) != len(set(edge_ids)):
        raise RunnerError('duplicate_edge_identity', 'artifact contains duplicate edge identity')

    local_entities = set(entity_ids)
    approved_entities = set(local_entities)
    external_only = not request.entities and all(
        edge.edge_type == 'ForeignKeyTo' for edge in request.edges
    )
    if external_only:
        for batch in EXPECTED_BATCHES.values():
            if batch['filename'] == 'documented-foreign-keys.payload.json':
                continue
            sibling_path = ROOT / 'catalog' / 'canary-v2-requests' / batch['filename']
            try:
                sibling_bytes = sibling_path.read_bytes()
            except OSError as exc:
                raise RunnerError(
                    'invalid_dependency_artifact', 'dependency artifact is unavailable'
                ) from exc
            if sha256_bytes(sibling_bytes) != batch['artifact_sha256']:
                raise RunnerError(
                    'invalid_dependency_artifact', 'dependency artifact byte hash mismatch'
                )
            sibling_raw = strict_json_loads(sibling_bytes)
            if not isinstance(sibling_raw, dict):
                raise RunnerError('invalid_dependency_artifact', 'dependency artifact is invalid')
            if (
                CatalogService.batch_request_sha256(
                    UpsertCatalogBatchRequest.model_validate(sibling_raw, strict=True)
                )
                != batch['request_sha256']
            ):
                raise RunnerError(
                    'invalid_dependency_artifact', 'dependency artifact hash mismatch'
                )
            approved_entities.update(
                (item['entity_type'], item['graph_key']) for item in sibling_raw['entities']
            )
    for index, edge in enumerate(request.edges):
        endpoints = (
            (edge.source_entity_type, edge.source_graph_key),
            (edge.target_entity_type, edge.target_graph_key),
        )
        if any(endpoint not in approved_entities for endpoint in endpoints):
            raise RunnerError(
                'missing_approved_endpoint', f'edge endpoint missing at index {index}'
            )
        if edge.edge_type == 'DocumentedBy' and (
            edge.target_entity_type != 'DictionaryDocument'
            or edge.target_graph_key != DOCUMENT_GRAPH_KEY
        ):
            raise RunnerError(
                'document_target_mismatch', f'DocumentedBy target mismatch at index {index}'
            )

    assert request.provenance is not None
    provenance_entity_ids = [
        (item.entity_type, item.graph_key) for item in request.provenance.entity_targets
    ]
    provenance_edge_ids = [
        (item.edge_type, item.edge_key) for item in request.provenance.edge_targets
    ]
    if provenance_entity_ids != entity_ids:
        raise RunnerError(
            'provenance_entity_target_mismatch',
            'provenance entity targets must exactly match artifact entities in order',
        )
    if provenance_edge_ids != edge_ids:
        raise RunnerError(
            'provenance_edge_target_mismatch',
            'provenance edge targets must exactly match artifact edges in order',
        )

    source_keys = [item.source_key for item in request.provenance.sources]
    if len(source_keys) != len(set(source_keys)):
        raise RunnerError(
            'duplicate_source_identity', 'artifact contains duplicate provenance source'
        )
    for index, source in enumerate(request.provenance.sources):
        if (source.metadata or {}).get('catalog_sha256') != CATALOG_SHA256:
            raise RunnerError(
                'source_catalog_hash_mismatch',
                f'provenance source catalog hash mismatch at index {index}',
            )
        if (source.attributes or {}).get('batch_id') != request.batch_id:
            raise RunnerError(
                'source_batch_id_mismatch',
                f'provenance source batch mismatch at index {index}',
            )


def _validate_expected_batch(
    request: UpsertCatalogBatchRequest,
    payload_path: Path,
    artifact_sha256: str,
) -> str:
    expected = EXPECTED_BATCHES.get(request.batch_id)
    if expected is None:
        raise RunnerError('unknown_batch', f'unsupported canary batch: {request.batch_id}')
    if payload_path.name != expected['filename']:
        raise RunnerError('payload_filename_mismatch', 'payload filename does not match batch ID')
    if artifact_sha256 != expected['artifact_sha256']:
        raise RunnerError('artifact_hash_mismatch', 'artifact byte hash is not approved')
    if Counter(item.entity_type for item in request.entities) != Counter(expected['entity_types']):
        raise RunnerError('entity_count_mismatch', 'entity type counts do not match approved batch')
    if Counter(item.edge_type for item in request.edges) != Counter(expected['edge_types']):
        raise RunnerError('edge_count_mismatch', 'edge type counts do not match approved batch')
    assert request.provenance is not None
    provenance_counts = (
        len(request.provenance.sources),
        len(request.provenance.entity_targets),
        len(request.provenance.edge_targets),
    )
    if provenance_counts != expected['provenance']:
        raise RunnerError(
            'provenance_count_mismatch', 'provenance counts do not match approved batch'
        )
    server_hash = CatalogService.batch_request_sha256(request)
    if server_hash != expected['request_sha256']:
        raise RunnerError(
            'request_hash_mismatch', 'server request hash does not match approved batch'
        )
    return server_hash


def _reject_unknown_model_fields(raw: Any, model_fields: set[str], path: str) -> dict[str, Any]:
    """Reject unknown keys; allow omitted optional defaults (unlike historical exact-set)."""
    if not isinstance(raw, dict):
        raise RunnerError('invalid_shape', f'{path} must be an object')
    unknown = sorted(set(raw) - model_fields)
    if unknown:
        raise RunnerError('field_set_mismatch', f'{path} unknown fields: {unknown}')
    return raw


def _validate_hardened_raw_field_sets(raw: dict[str, Any]) -> None:
    _require_exact_fields(raw, HARDENED_ARTIFACT_FIELDS, '$')
    entities = raw.get('entities')
    edges = raw.get('edges')
    provenance = raw.get('provenance')
    if not isinstance(entities, list) or not isinstance(edges, list):
        raise RunnerError('invalid_shape', '$.entities and $.edges must be arrays')
    for index, item in enumerate(entities):
        _reject_unknown_model_fields(
            item, set(CatalogEntityItem.model_fields), f'$.entities[{index}]'
        )
    for index, item in enumerate(edges):
        _reject_unknown_model_fields(item, set(CatalogEdgeItem.model_fields), f'$.edges[{index}]')
    _reject_unknown_model_fields(
        provenance, set(NestedProvenancePayload.model_fields), '$.provenance'
    )
    if 'entity_targets' in provenance or 'edge_targets' in provenance:
        raise RunnerError(
            'cartesian_provenance_rejected',
            'Cartesian entity_targets/edge_targets rejected; use evidence_links',
        )
    sources = provenance.get('sources')
    evidence_links = provenance.get('evidence_links')
    if not isinstance(sources, list) or not isinstance(evidence_links, list):
        raise RunnerError('invalid_shape', 'provenance sources/evidence_links must be arrays')
    for index, item in enumerate(sources):
        _reject_unknown_model_fields(
            item, set(CatalogSourceItem.model_fields), f'$.provenance.sources[{index}]'
        )
    for index, item in enumerate(evidence_links):
        _reject_unknown_model_fields(
            item, set(CatalogEvidenceLink.model_fields), f'$.provenance.evidence_links[{index}]'
        )


def reject_historical_as_hardened(raw: dict[str, Any] | Path) -> None:
    """Historical direct-upsert artifacts are not hardened authority (D-05, D-11)."""
    if isinstance(raw, Path):
        data = strict_json_loads(raw.read_bytes())
        if not isinstance(data, dict):
            raise RunnerError('invalid_shape', 'artifact root must be an object')
        raw = data
    historical_markers = []
    if raw.get('identity_schema_version') != HARDENED_IDENTITY_SCHEMA_VERSION:
        historical_markers.append('missing catalog-v2 identity_schema_version')
    if 'system_key' not in raw:
        historical_markers.append('missing system_key')
    provenance = raw.get('provenance') or {}
    if isinstance(provenance, dict) and (
        'entity_targets' in provenance or 'edge_targets' in provenance
    ):
        historical_markers.append('Cartesian provenance')
    if historical_markers:
        raise RunnerError(
            'historical_not_hardened_authority',
            'historical canary artifact is not hardened authority: '
            + '; '.join(historical_markers),
        )


def validate_hardened_artifact(
    payload_path: Path,
    *,
    expected_artifact_sha256: str | None = None,
    expected_request_sha256: str | None = None,
) -> tuple[bytes, dict[str, Any], PrepareCatalogBatchRequest, str, str]:
    """Strict-load and validate one hardened catalog-v2 prepare-shaped payload offline."""
    if expected_artifact_sha256 is not None and not SHA256_RE.fullmatch(expected_artifact_sha256):
        raise RunnerError(
            'invalid_expected_hash', '--expected-artifact-sha256 must be lowercase SHA-256'
        )
    if expected_request_sha256 is not None and not SHA256_RE.fullmatch(expected_request_sha256):
        raise RunnerError(
            'invalid_expected_hash', '--expected-request-sha256 must be lowercase SHA-256'
        )
    try:
        artifact_bytes = payload_path.read_bytes()
    except OSError as exc:
        raise RunnerError('file_read_failed', f'cannot read {payload_path.name}') from exc
    artifact_sha256 = sha256_bytes(artifact_bytes)
    if expected_artifact_sha256 is not None and artifact_sha256 != expected_artifact_sha256:
        raise RunnerError(
            'artifact_hash_mismatch', 'artifact byte hash does not match expected hash'
        )
    raw = strict_json_loads(artifact_bytes)
    if not isinstance(raw, dict):
        raise RunnerError('invalid_shape', 'artifact root must be an object')
    reject_historical_as_hardened(raw)
    if canonical_artifact_bytes(raw) != artifact_bytes:
        raise RunnerError(
            'non_canonical_artifact',
            'artifact bytes must be canonical JSON followed by exactly one LF',
        )
    _validate_hardened_raw_field_sets(raw)
    if raw['identity_schema_version'] != HARDENED_IDENTITY_SCHEMA_VERSION:
        raise RunnerError('identity_schema_mismatch', 'identity_schema_version must be catalog-v2')
    if raw['system_key'] != HARDENED_SYSTEM_KEY:
        raise RunnerError('system_key_mismatch', 'system_key must be FE for sanitized fixture')
    if raw['group_id'] != HARDENED_GROUP_ID:
        raise RunnerError(
            'group_id_mismatch',
            'hardened offline group_id must be oracle-catalog-tool-test',
        )
    if raw['atomic'] is not True:
        raise RunnerError('atomic_required', 'artifact atomic field must be true')
    try:
        prepare_request = PrepareCatalogBatchRequest.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'request_validation_failed', 'artifact fails prepare request validation'
        ) from exc
    # Content hashes via Upsert shape (same domain body + dry_run false)
    upsert = UpsertCatalogBatchRequest.model_validate({**raw, 'dry_run': False}, strict=True)
    _validate_content_hashes(upsert)
    server_hash = CatalogService.batch_request_sha256(upsert)
    if expected_request_sha256 is not None and server_hash != expected_request_sha256:
        raise RunnerError(
            'request_hash_mismatch', 'server request hash does not match expected hash'
        )
    return artifact_bytes, raw, prepare_request, artifact_sha256, server_hash


def build_prepare_transport_request(raw: dict[str, Any]) -> dict[str, Any]:
    """Prepare tool envelope: full domain body, no dry_run, no plan_token."""
    payload = copy.deepcopy(raw)
    payload.pop('dry_run', None)
    payload.pop('plan_token', None)
    PrepareCatalogBatchRequest.model_validate(payload, strict=True)
    return payload


def build_commit_transport_request(
    plan_token: str, *, expected_request_sha256: str | None = None
) -> dict[str, Any]:
    """Token-only commit envelope (D-20). plan_token stays in-memory for fakes only."""
    body: dict[str, Any] = {'plan_token': plan_token}
    if expected_request_sha256 is not None:
        body['expected_request_sha256'] = expected_request_sha256
    CommitPreparedCatalogBatchRequest.model_validate(body, strict=True)
    return body


def simulate_prepare_commit_sequence(
    raw: dict[str, Any],
    *,
    request_sha256: str,
    plan_token: str = 'offline-plan-token',
) -> list[tuple[str, dict[str, Any]]]:
    """Pure offline expected MCP call sequence for hardened canary (never executed live)."""
    prepare_body = build_prepare_transport_request(raw)
    commit_body = build_commit_transport_request(plan_token, expected_request_sha256=request_sha256)
    group_id = raw['group_id']
    batch_id = raw['batch_id']
    entities = raw['entities']
    edges = raw['edges']
    representative_entity = entities[0]
    representative_edge = edges[0]
    return [
        ('prepare_catalog_batch', {'request': prepare_body}),
        ('commit_prepared_catalog_batch', {'request': commit_body}),
        (
            'get_catalog_ingest_status',
            {'request': {'group_id': group_id, 'batch_id': batch_id}},
        ),
        (
            'verify_catalog_batch',
            {
                'request': {
                    'group_id': group_id,
                    'batch_id': batch_id,
                    'entities': [
                        {'entity_type': item['entity_type'], 'graph_key': item['graph_key']}
                        for item in entities
                    ],
                    'edges': [
                        {
                            'edge_type': item['edge_type'],
                            'edge_key': item['edge_key'],
                            'expected_source_graph_key': item['source_graph_key'],
                            'expected_target_graph_key': item['target_graph_key'],
                            'expected_source_uuid': None,
                            'expected_target_uuid': None,
                        }
                        for item in edges
                    ],
                    'require_provenance': True,
                }
            },
        ),
        (
            'resolve_typed_entities',
            {
                'request': {
                    'group_id': group_id,
                    'entities': [
                        {'entity_type': item['entity_type'], 'graph_key': item['graph_key']}
                        for item in entities
                    ],
                    'graph_keys': None,
                }
            },
        ),
        (
            'get_catalog_batch_manifest',
            {'request': {'group_id': group_id, 'batch_id': batch_id}},
        ),
        (
            'get_catalog_evidence',
            {
                'request': {
                    'group_id': group_id,
                    'entity_type': representative_entity['entity_type'],
                    'graph_key': representative_entity['graph_key'],
                }
            },
        ),
        (
            'search_nodes',
            {
                'query': representative_entity['graph_key'],
                'group_ids': [group_id],
                'max_nodes': 10,
                'entity_types': [representative_entity['entity_type']],
                'center_node_uuid': None,
            },
        ),
        (
            'search_memory_facts',
            {
                'query': representative_edge['fact'],
                'group_ids': [group_id],
                'max_facts': 10,
                'center_node_uuid': None,
                'edge_types': [representative_edge['edge_type']],
                'valid_at_after': None,
                'valid_at_before': None,
                'invalid_at_after': None,
                'invalid_at_before': None,
            },
        ),
    ]


def assert_sequence_has_no_prohibited_tools(sequence: list[tuple[str, dict[str, Any]]]) -> None:
    names = [name for name, _ in sequence]
    if names != COMMIT_TOOL_SEQUENCE:
        raise RunnerError(
            'sequence_mismatch',
            f'expected {COMMIT_TOOL_SEQUENCE}, got {names}',
        )
    banned = set(names) & PROHIBITED_LEGACY_TOOLS
    if banned:
        raise RunnerError('prohibited_tool', f'prohibited tools in sequence: {sorted(banned)}')


def validate_artifact(
    payload_path: Path,
    *,
    expected_artifact_sha256: str | None = None,
    expected_request_sha256: str | None = None,
) -> tuple[bytes, dict[str, Any], UpsertCatalogBatchRequest, str, str]:
    """Strict-load and validate one immutable payload before any transport call."""
    if expected_artifact_sha256 is not None and not SHA256_RE.fullmatch(expected_artifact_sha256):
        raise RunnerError(
            'invalid_expected_hash', '--expected-artifact-sha256 must be lowercase SHA-256'
        )
    if expected_request_sha256 is not None and not SHA256_RE.fullmatch(expected_request_sha256):
        raise RunnerError(
            'invalid_expected_hash', '--expected-request-sha256 must be lowercase SHA-256'
        )
    try:
        artifact_bytes = payload_path.read_bytes()
    except OSError as exc:
        raise RunnerError('file_read_failed', f'cannot read {payload_path.name}') from exc
    artifact_sha256 = sha256_bytes(artifact_bytes)
    if expected_artifact_sha256 is not None and artifact_sha256 != expected_artifact_sha256:
        raise RunnerError(
            'artifact_hash_mismatch', 'artifact byte hash does not match expected hash'
        )
    if MALFORMED_DOCUMENT_ID.encode() in artifact_bytes:
        raise RunnerError('malformed_document_id', 'artifact contains malformed document ID')
    raw = strict_json_loads(artifact_bytes)
    if not isinstance(raw, dict):
        raise RunnerError('invalid_shape', 'artifact root must be an object')
    if canonical_artifact_bytes(raw) != artifact_bytes:
        raise RunnerError(
            'non_canonical_artifact',
            'artifact bytes must be canonical JSON followed by exactly one LF',
        )
    _validate_raw_field_sets(raw)
    if raw['group_id'] != TARGET_GROUP_ID:
        raise RunnerError('group_id_mismatch', 'artifact group_id is not approved target group')
    if raw['catalog_sha256'] != CATALOG_SHA256:
        raise RunnerError('catalog_hash_mismatch', 'artifact catalog hash is not approved')
    if raw['atomic'] is not True:
        raise RunnerError('atomic_required', 'artifact atomic field must be true')
    try:
        request = UpsertCatalogBatchRequest.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'request_validation_failed', 'artifact fails catalog request validation'
        ) from exc
    _validate_content_hashes(request)
    _validate_identities_and_endpoints(request)
    server_hash = _validate_expected_batch(request, payload_path, artifact_sha256)
    if expected_request_sha256 is not None and server_hash != expected_request_sha256:
        raise RunnerError(
            'request_hash_mismatch', 'server request hash does not match expected hash'
        )
    return artifact_bytes, raw, request, artifact_sha256, server_hash


def response_path_for(payload_path: Path, mode: str) -> Path:
    suffix = '.payload.json'
    base = (
        payload_path.name[: -len(suffix)]
        if payload_path.name.endswith(suffix)
        else payload_path.stem
    )
    return payload_path.with_name(f'{base}.{mode}.response.json')


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'
    ).encode('utf-8')


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb',
            prefix=f'.{path.name}.',
            suffix='.tmp',
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise RunnerError('atomic_write_failed', f'atomic write failed for {path.name}') from exc
    finally:
        if temporary is not None:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: Any) -> str:
    data = _json_bytes(value)
    atomic_write_bytes(path, data)
    return sha256_bytes(data)


def _safe_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _protocol_dump(result: Any) -> dict[str, Any]:
    if hasattr(result, 'model_dump'):
        dumped = result.model_dump(mode='json', by_alias=True, exclude={'meta'})
        if isinstance(dumped, dict):
            dumped.pop('_meta', None)
            return dumped
    content = getattr(result, 'content', None)
    return {
        'content': content if isinstance(content, list) else [],
        'structuredContent': getattr(result, 'structuredContent', None),
        'isError': bool(getattr(result, 'isError', False)),
    }


def _unwrap_structured_result(structured: Any, tool_name: str) -> dict[str, Any]:
    if not isinstance(structured, dict):
        raise RunnerError(
            'missing_structured_content', f'{tool_name} returned no structured content'
        )
    payload = structured.get('result', structured)
    if not isinstance(payload, dict):
        raise RunnerError('invalid_structured_content', f'{tool_name} returned invalid content')
    if 'error' in payload:
        raise RunnerError('graphiti_error_response', f'{tool_name} returned Graphiti ErrorResponse')
    return payload


def _extract_structured_result(
    result: Any, tool_name: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    protocol = _protocol_dump(result)
    if bool(getattr(result, 'isError', protocol.get('isError', False))):
        raise RunnerError('mcp_tool_error', f'{tool_name} returned MCP error')
    structured = getattr(result, 'structuredContent', protocol.get('structuredContent'))
    return protocol, _unwrap_structured_result(structured, tool_name)


async def call_mcp_tool(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call one MCP tool once and require structured, non-error output."""
    result = await session.call_tool(tool_name, arguments)
    return _extract_structured_result(result, tool_name)


def _validate_batch_response(
    structured: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    mode: str,
) -> CatalogBatchWriteResponse:
    try:
        response = CatalogBatchWriteResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_batch_response', 'upsert response has invalid structure'
        ) from exc
    expected_dry_run = mode == 'dry-run'
    expected_status = 'validating' if expected_dry_run else 'committed'
    if response.group_id != request.group_id or response.batch_id != request.batch_id:
        raise RunnerError('response_identity_mismatch', 'upsert response group or batch mismatch')
    if response.dry_run is not expected_dry_run or response.atomic is not True:
        raise RunnerError('response_mode_mismatch', 'upsert response mode or atomic flag mismatch')
    if response.status != expected_status:
        raise RunnerError(
            'response_status_mismatch', f'upsert response status is not {expected_status}'
        )
    if response.failed != 0 or response.rolled_back != 0:
        raise RunnerError('upsert_failed', 'upsert response reports failed or rolled-back items')
    if response.error_code is not None or response.error_message is not None:
        raise RunnerError('upsert_failed', 'upsert response contains structured error')
    assert request.provenance is not None
    totals = (
        response.entity_created + response.entity_updated + response.entity_unchanged,
        response.edge_created + response.edge_updated + response.edge_unchanged,
        response.provenance_created + response.provenance_updated + response.provenance_unchanged,
    )
    expected_totals = (
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources),
    )
    if totals != expected_totals:
        raise RunnerError('response_count_mismatch', 'upsert response counts do not match artifact')
    if not response.results and mode == 'dry-run':
        raise RunnerError('response_count_mismatch', 'dry-run response omitted item results')
    if (
        not response.results
        and mode == 'commit'
        and any(
            (
                response.entity_created,
                response.entity_updated,
                response.edge_created,
                response.edge_updated,
                response.provenance_created,
                response.provenance_updated,
            )
        )
    ):
        raise RunnerError('response_count_mismatch', 'write response omitted item results')
    if response.results:
        if len(response.results) != sum(expected_totals):
            raise RunnerError(
                'response_count_mismatch', 'upsert item result count does not match artifact'
            )
        if any(item.status not in {'created', 'updated', 'unchanged'} for item in response.results):
            raise RunnerError('upsert_failed', 'upsert item result contains non-success status')
    return response


def require_matching_dry_run_receipt(
    payload_path: Path,
    *,
    artifact_sha256: str,
    artifact_size: int,
    server_request_sha256: str,
    request: UpsertCatalogBatchRequest,
) -> tuple[Path, str]:
    """Require successful receipt for exact current artifact bytes and request hash."""
    receipt_path = response_path_for(payload_path, 'dry-run')
    try:
        receipt_bytes = receipt_path.read_bytes()
    except OSError as exc:
        raise RunnerError(
            'missing_dry_run_receipt', 'matching dry-run receipt is required'
        ) from exc
    receipt = strict_json_loads(receipt_bytes)
    if not isinstance(receipt, dict):
        raise RunnerError('invalid_dry_run_receipt', 'dry-run receipt root must be an object')
    expected_fields = {
        'schema_version',
        'tool',
        'mode',
        'payload_path',
        'artifact_sha256',
        'artifact_size',
        'server_request_sha256',
        'recorded_at',
        'protocol_response',
    }
    _require_exact_fields(receipt, expected_fields, '$receipt')
    if receipt.get('schema_version') != 1 or receipt.get('tool') != 'upsert_catalog_batch':
        raise RunnerError('invalid_dry_run_receipt', 'dry-run receipt schema or tool mismatch')
    if receipt.get('mode') != 'dry-run':
        raise RunnerError('invalid_dry_run_receipt', 'receipt mode is not dry-run')
    if (
        receipt.get('artifact_sha256') != artifact_sha256
        or receipt.get('artifact_size') != artifact_size
    ):
        raise RunnerError(
            'dry_run_artifact_mismatch', 'commit artifact differs from dry-run receipt'
        )
    if receipt.get('server_request_sha256') != server_request_sha256:
        raise RunnerError(
            'dry_run_request_mismatch', 'commit request hash differs from dry-run receipt'
        )
    protocol = receipt.get('protocol_response')
    if not isinstance(protocol, dict) or protocol.get('isError') is True:
        raise RunnerError('invalid_dry_run_receipt', 'dry-run receipt protocol failed')
    structured = protocol.get('structuredContent')
    try:
        payload = _unwrap_structured_result(structured, 'upsert_catalog_batch')
    except RunnerError as exc:
        raise RunnerError(
            'invalid_dry_run_receipt', 'dry-run receipt lacks valid structured response'
        ) from exc
    _validate_batch_response(payload, request, 'dry-run')
    return receipt_path, sha256_bytes(receipt_bytes)


def _validate_status_response(
    structured: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    server_request_sha256: str,
) -> None:
    try:
        response = CatalogIngestStatusResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_status_response', 'status response has invalid structure'
        ) from exc
    assert request.provenance is not None
    if response.group_id != request.group_id or response.batch_id != request.batch_id:
        raise RunnerError('status_identity_mismatch', 'status group or batch mismatch')
    if response.status != 'committed' or response.error_code is not None or response.error_summary:
        raise RunnerError('status_not_committed', 'batch status is not cleanly committed')
    if response.request_sha256 != server_request_sha256:
        raise RunnerError('status_request_hash_mismatch', 'committed status request hash mismatch')
    if response.catalog_sha256 != request.catalog_sha256:
        raise RunnerError('status_catalog_hash_mismatch', 'committed status catalog hash mismatch')
    counts = (response.entity_count, response.edge_count, response.provenance_count)
    expected = (len(request.entities), len(request.edges), len(request.provenance.sources))
    if counts != expected:
        raise RunnerError('status_count_mismatch', 'committed status counts do not match artifact')


def _validate_verify_response(
    structured: dict[str, Any], request: UpsertCatalogBatchRequest
) -> None:
    try:
        response = VerifyCatalogBatchResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_verify_response', 'verify response has invalid structure'
        ) from exc
    if response.group_id != request.group_id or response.batch_id != request.batch_id:
        raise RunnerError('verify_identity_mismatch', 'verify group or batch mismatch')
    if response.error_code is not None or response.error_message is not None:
        raise RunnerError('verify_failed', 'verify response contains structured error')
    if not response.require_provenance:
        raise RunnerError('verify_failed', 'verify response did not require provenance')
    if response.entities.expected != len(request.entities) or response.entities.found != len(
        request.entities
    ):
        raise RunnerError(
            'verify_entity_count_mismatch', 'verify entity counts do not match artifact'
        )
    if response.edges.expected != len(request.edges) or response.edges.found != len(request.edges):
        raise RunnerError('verify_edge_count_mismatch', 'verify edge counts do not match artifact')
    entity_lists = (
        response.entities.missing,
        response.entities.wrong_type,
        response.entities.generic_duplicate,
        response.entities.typed_duplicate,
        response.entities.uuid_mismatch,
        response.entities.missing_embedding,
    )
    edge_lists = (
        response.edges.missing,
        response.edges.duplicate_edge_key,
        response.edges.edge_type_mismatch,
        response.edges.endpoint_mismatch,
        response.edges.uuid_mismatch,
        response.edges.missing_embedding,
    )
    if (
        response.missing
        or response.anomalies
        or response.missing_provenance
        or any(entity_lists)
        or any(edge_lists)
    ):
        raise RunnerError('verify_failed', 'verify response reports missing data or anomalies')


def _validate_resolve_response(
    structured: dict[str, Any], request: UpsertCatalogBatchRequest
) -> None:
    try:
        response = ResolveTypedEntitiesResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_resolve_response', 'resolve response has invalid structure'
        ) from exc
    if response.group_id != request.group_id or len(response.results) != len(request.entities):
        raise RunnerError('resolve_count_mismatch', 'resolve response identity or count mismatch')
    for item, expected in zip(response.results, request.entities, strict=True):
        if (
            item.entity_type != expected.entity_type
            or item.graph_key != expected.graph_key
            or item.status != 'found'
            or not item.found
            or item.verified_type != expected.entity_type
            or item.has_name_embedding is not True
            or item.content_sha256 != expected.content_sha256
            or item.error_code is not None
            or item.error_message is not None
            or item.generic_duplicates
            or item.typed_duplicates
            or item.anomalies
        ):
            raise RunnerError(
                'resolve_failed', 'resolve response contains missing or anomalous entity'
            )


def _validate_node_search(structured: dict[str, Any], graph_key: str) -> None:
    nodes = structured.get('nodes')
    if not isinstance(nodes, list) or not any(
        isinstance(node, dict) and node.get('name') == graph_key for node in nodes
    ):
        raise RunnerError(
            'node_search_failed', 'node retrieval gate did not return expected entity'
        )


def _validate_fact_search(structured: dict[str, Any], edge: CatalogEdgeItem) -> None:
    facts = structured.get('facts')
    if not isinstance(facts, list) or not facts:
        raise RunnerError('fact_search_failed', 'fact retrieval gate returned no facts')
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        attributes = fact.get('attributes') if isinstance(fact.get('attributes'), dict) else {}
        if (
            fact.get('edge_key') == edge.edge_key
            or attributes.get('edge_key') == edge.edge_key
            or (fact.get('name') == edge.edge_type and fact.get('fact') == edge.fact)
        ):
            return
    raise RunnerError('fact_search_failed', 'fact retrieval gate did not return expected edge')


async def run_post_commit_gates(
    session: ClientSession,
    request: UpsertCatalogBatchRequest,
    server_request_sha256: str,
) -> dict[str, Any]:
    """Run status, verify, resolve, node-search, and fact-search gates once."""
    protocols: dict[str, Any] = {}

    protocol, structured = await call_mcp_tool(
        session,
        'get_catalog_ingest_status',
        {'request': {'group_id': request.group_id, 'batch_id': request.batch_id}},
    )
    protocols['get_catalog_ingest_status'] = protocol
    _validate_status_response(structured, request, server_request_sha256)

    verify_request = {
        'group_id': request.group_id,
        'batch_id': request.batch_id,
        'entities': [
            {'entity_type': item.entity_type, 'graph_key': item.graph_key}
            for item in request.entities
        ],
        'edges': [
            {
                'edge_type': item.edge_type,
                'edge_key': item.edge_key,
                'expected_source_graph_key': item.source_graph_key,
                'expected_target_graph_key': item.target_graph_key,
                'expected_source_uuid': None,
                'expected_target_uuid': None,
            }
            for item in request.edges
        ],
        'require_provenance': True,
    }
    protocol, structured = await call_mcp_tool(
        session, 'verify_catalog_batch', {'request': verify_request}
    )
    protocols['verify_catalog_batch'] = protocol
    _validate_verify_response(structured, request)

    resolve_request = {
        'group_id': request.group_id,
        'entities': [
            {'entity_type': item.entity_type, 'graph_key': item.graph_key}
            for item in request.entities
        ],
        'graph_keys': None,
    }
    protocol, structured = await call_mcp_tool(
        session, 'resolve_typed_entities', {'request': resolve_request}
    )
    protocols['resolve_typed_entities'] = protocol
    _validate_resolve_response(structured, request)

    representative_entity = request.entities[0] if request.entities else None
    representative_edge = request.edges[0]
    node_type = (
        representative_entity.entity_type
        if representative_entity is not None
        else representative_edge.source_entity_type
    )
    node_key = (
        representative_entity.graph_key
        if representative_entity is not None
        else representative_edge.source_graph_key
    )
    protocol, structured = await call_mcp_tool(
        session,
        'search_nodes',
        {
            'query': node_key,
            'group_ids': [request.group_id],
            'max_nodes': 10,
            'entity_types': [node_type],
            'center_node_uuid': None,
        },
    )
    protocols['search_nodes'] = protocol
    _validate_node_search(structured, node_key)

    protocol, structured = await call_mcp_tool(
        session,
        'search_memory_facts',
        {
            'query': representative_edge.fact,
            'group_ids': [request.group_id],
            'max_facts': 10,
            'center_node_uuid': None,
            'edge_types': [representative_edge.edge_type],
            'valid_at_after': None,
            'valid_at_before': None,
            'invalid_at_after': None,
            'invalid_at_before': None,
        },
    )
    protocols['search_memory_facts'] = protocol
    _validate_fact_search(structured, representative_edge)
    return protocols


def _response_wrapper(
    *,
    payload_path: Path,
    mode: str,
    artifact_sha256: str,
    artifact_size: int,
    server_request_sha256: str,
    protocol_response: dict[str, Any],
    post_commit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    wrapper: dict[str, Any] = {
        'schema_version': 1,
        'tool': 'upsert_catalog_batch',
        'mode': mode,
        'payload_path': _safe_relative_path(payload_path),
        'artifact_sha256': artifact_sha256,
        'artifact_size': artifact_size,
        'server_request_sha256': server_request_sha256,
        'recorded_at': utc_now(),
        'protocol_response': protocol_response,
    }
    if post_commit is not None:
        wrapper['post_commit'] = post_commit
    return wrapper


def _response_counts(response: CatalogBatchWriteResponse) -> dict[str, int]:
    return {
        'entity_created': response.entity_created,
        'entity_updated': response.entity_updated,
        'entity_unchanged': response.entity_unchanged,
        'edge_created': response.edge_created,
        'edge_updated': response.edge_updated,
        'edge_unchanged': response.edge_unchanged,
        'provenance_created': response.provenance_created,
        'provenance_updated': response.provenance_updated,
        'provenance_unchanged': response.provenance_unchanged,
        'failed': response.failed,
        'rolled_back': response.rolled_back,
    }


def has_verified_commit_attempt(
    checkpoint_path: Path,
    *,
    batch_id: str,
    artifact_sha256: str,
    server_request_sha256: str,
) -> bool:
    """Return whether exact artifact already has verified commit evidence."""
    if not checkpoint_path.exists():
        return False
    checkpoint = strict_json_load(checkpoint_path)
    if not isinstance(checkpoint, dict):
        raise RunnerError('invalid_checkpoint', 'checkpoint root must be an object')
    attempts = checkpoint.get('attempts', [])
    if not isinstance(attempts, list):
        raise RunnerError('invalid_checkpoint', 'checkpoint attempts must be an array')
    return any(
        isinstance(attempt, dict)
        and attempt.get('batch_id') == batch_id
        and attempt.get('mode') == 'commit'
        and attempt.get('status') == 'commit_verified'
        and attempt.get('artifact_sha256') == artifact_sha256
        and attempt.get('server_request_sha256') == server_request_sha256
        for attempt in attempts
    )


def _validate_idempotent_replay(
    response: CatalogBatchWriteResponse,
    request: UpsertCatalogBatchRequest,
) -> None:
    assert request.provenance is not None
    if any(
        (
            response.entity_created,
            response.entity_updated,
            response.edge_created,
            response.edge_updated,
            response.provenance_created,
            response.provenance_updated,
        )
    ):
        raise RunnerError('idempotency_failed', 'verified replay created or updated data')
    unchanged = (
        response.entity_unchanged,
        response.edge_unchanged,
        response.provenance_unchanged,
    )
    expected = (len(request.entities), len(request.edges), len(request.provenance.sources))
    if unchanged != expected:
        raise RunnerError(
            'idempotency_failed', 'verified replay did not report all inputs unchanged'
        )


# ponytail: single-process operator assumption; add file locking for concurrent runners.
def append_checkpoint_attempt(checkpoint_path: Path, attempt: dict[str, Any]) -> None:
    """Append one attempt while preserving every prior checkpoint field and record."""
    checkpoint = strict_json_load(checkpoint_path) if checkpoint_path.exists() else {}
    if not isinstance(checkpoint, dict):
        raise RunnerError('invalid_checkpoint', 'checkpoint root must be an object')
    attempts = checkpoint.get('attempts')
    if attempts is None:
        attempts = []
        checkpoint['attempts'] = attempts
    if not isinstance(attempts, list):
        raise RunnerError('invalid_checkpoint', 'checkpoint attempts must be an array')
    attempts.append(copy.deepcopy(attempt))
    atomic_write_json(checkpoint_path, checkpoint)


def _base_attempt(
    *,
    payload_path: Path,
    mode: str,
    artifact_sha256: str,
    artifact_size: int,
    server_request_sha256: str,
    batch_id: str,
    started_at: str,
) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        'batch_id': batch_id,
        'mode': mode,
        'payload_path': _safe_relative_path(payload_path),
        'artifact_sha256': artifact_sha256,
        'artifact_size': artifact_size,
        'server_request_sha256': server_request_sha256,
        'started_at': started_at,
        'completed_at': None,
        'status': 'started',
        'response_path': None,
        'response_sha256': None,
        'counts': None,
    }
    if batch_id == 'canary-v2::accept-tab':
        attempt.update(
            {
                'retry_from_immutable_artifact': True,
                'previous_failure': {'error_code': 'content_hash_mismatch', 'writes': 0},
            }
        )
    return attempt


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    payload_path = args.payload.resolve()
    artifact_bytes, raw, validated, artifact_sha256, server_request_sha256 = validate_artifact(
        payload_path,
        expected_artifact_sha256=args.expected_artifact_sha256,
        expected_request_sha256=args.expected_request_sha256,
    )
    checkpoint_path = args.checkpoint.resolve()
    idempotent_replay = args.mode == 'commit' and has_verified_commit_attempt(
        checkpoint_path,
        batch_id=validated.batch_id,
        artifact_sha256=artifact_sha256,
        server_request_sha256=server_request_sha256,
    )
    attempt = _base_attempt(
        payload_path=payload_path,
        mode=args.mode,
        artifact_sha256=artifact_sha256,
        artifact_size=len(artifact_bytes),
        server_request_sha256=server_request_sha256,
        batch_id=validated.batch_id,
        started_at=utc_now(),
    )
    attempt['idempotent_replay'] = idempotent_replay
    response_path = response_path_for(payload_path, args.mode)
    attempt['response_path'] = _safe_relative_path(response_path)

    if args.mode == 'commit':
        try:
            try:
                current_bytes = payload_path.read_bytes()
            except OSError as exc:
                raise RunnerError('file_read_failed', f'cannot reread {payload_path.name}') from exc
            if current_bytes != artifact_bytes or sha256_bytes(current_bytes) != artifact_sha256:
                raise RunnerError('artifact_changed', 'artifact bytes changed before commit gate')
            receipt_path, receipt_sha256 = require_matching_dry_run_receipt(
                payload_path,
                artifact_sha256=artifact_sha256,
                artifact_size=len(artifact_bytes),
                server_request_sha256=server_request_sha256,
                request=validated,
            )
        except RunnerError as exc:
            attempt['status'] = 'failed_before_call'
            attempt['error_code'] = exc.code
            attempt['completed_at'] = utc_now()
            append_checkpoint_attempt(checkpoint_path, attempt)
            raise
        attempt['dry_run_receipt_path'] = _safe_relative_path(receipt_path)
        attempt['dry_run_receipt_sha256'] = receipt_sha256

    transport_request = copy.deepcopy(raw)
    transport_request['dry_run'] = args.mode == 'dry-run'
    if args.mode == 'commit':
        transport_request['request_sha256'] = server_request_sha256
    allowed_added = {'dry_run'} if args.mode == 'dry-run' else {'dry_run', 'request_sha256'}
    if set(transport_request) - set(raw) != allowed_added:
        raise RunnerError(
            'transport_field_violation', 'transport request added non-approved fields'
        )

    call_started = False
    result_received = False
    response: CatalogBatchWriteResponse | None = None
    try:
        async with (
            streamable_http_client(args.mcp_url) as (
                read_stream,
                write_stream,
                _get_session_id,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            call_started = True
            result = await session.call_tool('upsert_catalog_batch', {'request': transport_request})
            result_received = True
            protocol_response = _protocol_dump(result)
            wrapper = _response_wrapper(
                payload_path=payload_path,
                mode=args.mode,
                artifact_sha256=artifact_sha256,
                artifact_size=len(artifact_bytes),
                server_request_sha256=server_request_sha256,
                protocol_response=protocol_response,
            )
            attempt['response_sha256'] = atomic_write_json(response_path, wrapper)
            _, structured = _extract_structured_result(result, 'upsert_catalog_batch')
            response = _validate_batch_response(structured, validated, args.mode)
            if idempotent_replay:
                _validate_idempotent_replay(response, validated)

            if args.mode == 'commit':
                post_commit = await run_post_commit_gates(session, validated, server_request_sha256)
                wrapper = _response_wrapper(
                    payload_path=payload_path,
                    mode=args.mode,
                    artifact_sha256=artifact_sha256,
                    artifact_size=len(artifact_bytes),
                    server_request_sha256=server_request_sha256,
                    protocol_response=protocol_response,
                    post_commit=post_commit,
                )
                attempt['response_sha256'] = atomic_write_json(response_path, wrapper)
    except RunnerError as exc:
        attempt['status'] = (
            'committed_verification_failed'
            if response is not None and response.status == 'committed'
            else 'failed'
            if result_received
            else 'uncertain'
            if call_started
            else 'failed_before_call'
        )
        attempt['error_code'] = exc.code
        attempt['completed_at'] = utc_now()
        append_checkpoint_attempt(checkpoint_path, attempt)
        raise
    except Exception as exc:
        attempt['status'] = (
            'committed_verification_failed'
            if response is not None and response.status == 'committed'
            else 'failed'
            if result_received
            else 'uncertain'
            if call_started
            else 'failed_before_call'
        )
        attempt['error_code'] = (
            'post_commit_verification_failed'
            if response is not None and response.status == 'committed'
            else 'response_processing_failed'
            if result_received
            else 'transport_outcome_uncertain'
            if call_started
            else 'transport_setup_failed'
        )
        attempt['error_type'] = type(exc).__name__
        attempt['completed_at'] = utc_now()
        append_checkpoint_attempt(checkpoint_path, attempt)
        if call_started and not result_received:
            raise RunnerError(
                'transport_outcome_uncertain',
                'MCP call outcome is uncertain; inspect status before explicit operator rerun',
            ) from exc
        if result_received:
            raise RunnerError(
                attempt['error_code'],
                'MCP response or post-commit verification failed closed',
            ) from exc
        raise RunnerError(
            'transport_setup_failed', 'MCP transport setup failed before tool call'
        ) from exc

    assert response is not None
    attempt['status'] = 'dry_run_passed' if args.mode == 'dry-run' else 'commit_verified'
    attempt['counts'] = _response_counts(response)
    attempt['completed_at'] = utc_now()
    append_checkpoint_attempt(checkpoint_path, attempt)
    return {
        'ok': True,
        'mode': args.mode,
        'batch_id': validated.batch_id,
        'artifact_sha256': artifact_sha256,
        'server_request_sha256': server_request_sha256,
        'response_path': _safe_relative_path(response_path),
        'response_sha256': attempt['response_sha256'],
        'status': attempt['status'],
        'counts': attempt['counts'],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-url', required=True, help=argparse.SUPPRESS)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--mode', required=True, choices=('dry-run', 'commit'))
    parser.add_argument('--expected-artifact-sha256')
    parser.add_argument('--expected-request-sha256')
    parser.add_argument('--checkpoint', type=Path, default=DEFAULT_CHECKPOINT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        result = asyncio.run(execute(parse_args(argv)))
    except RunnerError as exc:
        failure = {'ok': False, 'error_code': exc.code, 'error': str(exc)}
    except Exception as exc:
        failure = {
            'ok': False,
            'error_code': 'internal_runner_error',
            'error': 'runner failed closed',
            'error_type': type(exc).__name__,
        }
    else:
        print(json.dumps(result, sort_keys=True))
        return 0
    print(json.dumps(failure, sort_keys=True), file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
