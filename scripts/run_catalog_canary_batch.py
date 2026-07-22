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
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
MCP_SRC = ROOT / 'mcp_server' / 'src'
for import_path in (SCRIPT_DIR, MCP_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from catalog_authority_hashing import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    authority_bytes,
    authority_digest,
    sha256_canonical_text_bytes,
    sha256_raw_bytes,
)
from catalog_canary_manifest_contract import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    EXECUTION_SURFACE_COMPOSE,
    LIVE_MANIFEST_FIELDS,
    SOURCE_DIGEST_ORIGIN_HOST,
    WAIVER_OPENAI,
)
from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from models.catalog_batch import NestedProvenancePayload, UpsertCatalogBatchRequest  # noqa: E402
from models.catalog_edges import CatalogEdgeItem  # noqa: E402
from models.catalog_entities import (  # noqa: E402
    CatalogEntityItem,
    GetCatalogBatchManifestRequest,
    GetCatalogEvidenceRequest,
    ResolveTypedEdgesRequest,
    ResolveTypedEntitiesRequest,
    VerifyCatalogBatchRequest,
)
from models.catalog_evidence import CatalogEvidenceLink  # noqa: E402
from models.catalog_prepare import (  # noqa: E402
    CommitPreparedCatalogBatchRequest,
    PrepareCatalogBatchRequest,
)
from models.catalog_provenance import CatalogSourceItem  # noqa: E402
from models.catalog_responses import (  # noqa: E402
    CatalogBatchWriteResponse,
    CatalogCapabilitiesResponse,
    CatalogIngestStatusResponse,
    CommitPreparedCatalogBatchResponse,
    GetCatalogBatchManifestResponse,
    GetCatalogEvidenceResponse,
    PrepareCatalogBatchResponse,
    ResolveTypedEdgesResponse,
    ResolveTypedEntitiesResponse,
    VerifyCatalogBatchResponse,
)
from pydantic import ValidationError  # noqa: E402
from services import catalog_manifest  # noqa: E402
from services.catalog_identity import (  # noqa: E402
    CANONICALIZATION_VERSION,
    CATALOG_SCHEMA_VERSION,
    canonical_sha256,
    evidence_canonical_payload,
    evidence_link_key,
)
from services.catalog_service import CatalogService  # noqa: E402

HARDENED_ARTIFACT_DIR = ROOT / 'catalog' / 'canary-v2-requests-hardened'
DEFAULT_CHECKPOINT = HARDENED_ARTIFACT_DIR / 'live-checkpoint.json'
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
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
    'upsert_' + 'catalog_batch',
}
LIVE_ARTIFACT_SCHEMA_VERSION = 'phase6-canary-run-v1'
EXPECTED_MCP_TOOLS = frozenset(
    {
        'add_memory',
        'search_nodes',
        'search_memory_facts',
        'update_entity',
        'delete_entity_edge',
        'delete_episode',
        'get_entity_edge',
        'get_episodes',
        'summarize_saga',
        'build_communities',
        'add_triplet',
        'get_episode_entities',
        'clear_graph',
        'get_status',
        'upsert_typed_entities',
        'resolve_typed_entities',
        'verify_catalog_batch',
        'upsert_typed_edges',
        'upsert_provenance',
        'get_catalog_ingest_status',
        'upsert_catalog_batch',
        'prepare_catalog_batch',
        'commit_prepared_catalog_batch',
        'discard_prepared_catalog_batch',
        'get_catalog_batch_manifest',
        'resolve_typed_edges',
        'get_catalog_evidence',
        'get_catalog_capabilities',
    }
)
LIVE_PAYLOAD_NAME = 'accept-tab.payload.json'
LIVE_MANIFEST_NAME = 'run-manifest.json'
PROTECTED_GROUP_IDS = frozenset(
    {'oracle-core', 'oracle-catalog-v2', 'oracle-catalog-tool-test', 'main'}
)
BLOCKED_RUN_ID = '20260719T200946Z-1c7f70b1'
SAFE_NAMESPACE_FINGERPRINT_RE = re.compile(r'^[0-9a-f]{16}$')
SOURCE_HEAD_RE = re.compile(r'^[0-9a-f]{40}$')
REPORT_SCHEMA_VERSION = 'phase6-canary-report-v1'
SOURCE_AUTHORITY_PATHS = (
    'scripts/run_catalog_canary_batch.py',
    'scripts/build_catalog_canary_requests.py',
    'scripts/catalog_authority_hashing.py',
    'scripts/catalog_canary_manifest_contract.py',
    'scripts/run_catalog_canary_launcher.py',
    'scripts/run_catalog_phase6_final_canary.py',
    'scripts/materialize_catalog_local_config.py',
    'scripts/bootstrap_catalog_v2_schema.py',
    'mcp_server/src/services/catalog_schema_bootstrap.py',
    'mcp_server/docker/docker-compose-neo4j.yml',
    'mcp_server/docker/docker-compose-neo4j.catalog-local.override.yml',
    'mcp_server/config/config-docker-neo4j.catalog-local.example.yaml',
    'graphiti_mcp_phase6_canary_agent_prompt_en.md',
    'mcp_server/tests/fixtures/accept_tab_sanitized.json',
    '.planning/phases/05-verification-security-compatibility-and-migration-docs/05-PROOF-PACKAGE.json',
)
APPROVED_FIXTURE_RAW_SHA256 = '145f38edb7245c448badc7598e2e0733b4c72c16f470909284c6e7d955bae922'
APPROVED_FIXTURE_LF_SHA256 = APPROVED_FIXTURE_RAW_SHA256


class LiveStage(IntEnum):
    START = 0
    PREFLIGHT_PASSED = 1
    ISOLATION_PASSED = 2
    ARTIFACT_VALIDATED = 3
    DRY_RUN_PASSED = 4
    PREPARE_PASSED = 5
    COMMIT_CONFIRMED = 6
    MANIFEST_VERIFIED = 7
    SEARCH_ISOLATION_VERIFIED = 8
    REPLAY_VERIFIED_OR_SKIPPED = 9
    FINALIZED = 10


class LiveStageMachine:
    def __init__(self) -> None:
        self.stage = LiveStage.START
        self.ledger: list[str] = []

    def advance(self, expected: LiveStage, target: LiveStage) -> None:
        if self.stage is not expected or target.value != expected.value + 1:
            raise RunnerError('stage_order_violation', 'live stage transition is not monotonic')
        self.stage = target
        self.ledger.append(target.name)

    def require(self, stage: LiveStage) -> None:
        if self.stage is not stage:
            raise RunnerError('stage_prerequisite_missing', f'{stage.name} is required')


class SessionLiveTransport:
    """MCP adapter preserving exact FastMCP envelopes."""

    def __init__(self, session: ClientSession):
        self.session = session
        self.upsert_calls = 0

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self.session.call_tool(name, arguments)

    async def call(self, name: str, request: dict[str, Any]) -> dict[str, Any]:
        if name == 'list_tools':
            listed = await self.session.list_tools()
            tools = list(getattr(listed, 'tools', []) or [])
            return {'count': len(tools), 'names': sorted(str(tool.name) for tool in tools)}
        if name == 'upsert_catalog_batch':
            self.upsert_calls += 1
            if (
                self.upsert_calls != 1
                or request.get('dry_run') is not True
                or type(request['dry_run']) is not bool
            ):
                raise RunnerError(
                    'dry_run_transport_guard',
                    'live upsert is allowed exactly once with boolean true',
                )
        arguments = (
            request
            if name in {'get_status', 'get_catalog_capabilities'}
            else request
            if name in {'search_nodes', 'search_memory_facts'}
            else {'request': request}
        )
        _, structured = await call_mcp_tool(self.session, name, arguments)
        return structured


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
    if not isinstance(provenance, dict):
        raise RunnerError('invalid_shape', '$.provenance must be an object')
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
    if not raw['entities'] or not raw['edges']:
        raise RunnerError(
            'representative_search_required',
            'hardened canary artifact requires at least one entity and one edge',
        )
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


def build_resolve_entities_request(request: UpsertCatalogBatchRequest) -> dict[str, Any]:
    body = {
        'identity_schema_version': request.identity_schema_version,
        'system_key': request.system_key,
        'group_id': request.group_id,
        'entities': [
            {'entity_type': item.entity_type, 'graph_key': item.graph_key}
            for item in request.entities
        ],
    }
    ResolveTypedEntitiesRequest.model_validate(body, strict=True)
    return body


def build_resolve_edges_request(request: UpsertCatalogBatchRequest) -> dict[str, Any]:
    body = {
        'identity_schema_version': request.identity_schema_version,
        'system_key': request.system_key,
        'group_id': request.group_id,
        'edges': [
            {'edge_type': item.edge_type, 'edge_key': item.edge_key} for item in request.edges
        ],
    }
    ResolveTypedEdgesRequest.model_validate(body, strict=True)
    return body


def build_verify_request(
    request: UpsertCatalogBatchRequest,
    entity_uuids: dict[tuple[str, str], str],
) -> dict[str, Any]:
    body = {
        'identity_schema_version': request.identity_schema_version,
        'system_key': request.system_key,
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
                'expected_source_uuid': entity_uuids[
                    (item.source_entity_type, item.source_graph_key)
                ],
                'expected_target_uuid': entity_uuids[
                    (item.target_entity_type, item.target_graph_key)
                ],
            }
            for item in request.edges
        ],
        'require_provenance': True,
    }
    VerifyCatalogBatchRequest.model_validate(body, strict=True)
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
    if not entities or not edges:
        raise RunnerError(
            'representative_search_required',
            'hardened canary artifact requires at least one entity and one edge',
        )
    request = UpsertCatalogBatchRequest.model_validate({**raw, 'dry_run': False}, strict=True)
    representative_entity = entities[0]
    representative_edge = edges[0]
    placeholder_entities = {
        (item.entity_type, item.graph_key): str(
            uuid.uuid5(uuid.NAMESPACE_URL, f'{item.entity_type}|{item.graph_key}')
        )
        for item in request.entities
    }
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
                    **build_verify_request(request, placeholder_entities),
                }
            },
        ),
        (
            'resolve_typed_entities',
            {
                'request': {
                    **build_resolve_entities_request(request),
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
                    'identity_schema_version': raw['identity_schema_version'],
                    'system_key': raw['system_key'],
                    'entity_target': {
                        'entity_type': representative_entity['entity_type'],
                        'graph_key': representative_entity['graph_key'],
                    },
                    'edge_target': None,
                    'offset': 0,
                    'limit': 100,
                    'include_excerpts': False,
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
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.05 * (attempt + 1))
        temporary = None
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            pass
        else:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
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
    if payload.get('error') == 'embedding_transport_auth':
        raise RunnerError('embedding_transport_auth', 'embedding transport authentication failed')
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


def _validate_prepare_response(
    structured: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    server_request_sha256: str,
) -> tuple[PrepareCatalogBatchResponse, str]:
    error_code = structured.get('error_code')
    error_message = structured.get('error_message')
    if error_code == 'embedding_failed' and error_message == 'embedding_transport_auth':
        raise RunnerError('embedding_transport_auth', 'embedding transport authentication failed')
    if error_code is not None or error_message is not None:
        raise RunnerError('prepare_failed', 'prepare response contains structured error')
    try:
        response = PrepareCatalogBatchResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_prepare_response', 'prepare response has invalid structure'
        ) from exc
    if not response.plan_token:
        raise RunnerError('prepare_failed', 'prepare response omitted plan token')
    try:
        uuid.UUID(response.plan_uuid)
    except ValueError as exc:
        raise RunnerError(
            'prepare_binding_mismatch', 'prepare response plan UUID is invalid'
        ) from exc
    if (
        response.request_sha256 != server_request_sha256
        or response.catalog_sha256 != request.catalog_sha256
        or response.identity_schema_version != request.identity_schema_version
        or re.fullmatch(r'[0-9a-f]{64}', response.artifact_sha256) is None
    ):
        raise RunnerError('prepare_binding_mismatch', 'prepare response hash or schema mismatch')
    assert request.provenance is not None
    counts = (
        response.entity_count,
        response.edge_count,
        response.source_count,
        response.evidence_link_count,
    )
    expected = (
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources),
        len(request.provenance.evidence_links),
    )
    if counts != expected:
        raise RunnerError('prepare_count_mismatch', 'prepare response counts do not match artifact')
    return response, response.plan_token


def _validate_commit_response(
    structured: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    server_request_sha256: str,
    *,
    expected_plan_uuid: str,
    expected_artifact_sha256: str,
) -> CommitPreparedCatalogBatchResponse:
    try:
        response = CommitPreparedCatalogBatchResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_commit_response', 'commit response has invalid structure'
        ) from exc
    if response.error_code is not None or response.error_message is not None:
        raise RunnerError('commit_failed', 'commit response contains structured error')
    if response.state != 'COMMITTED':
        raise RunnerError('commit_failed', 'prepared plan is not committed')
    try:
        uuid.UUID(response.plan_uuid)
        uuid.UUID(response.batch_uuid or '')
    except ValueError as exc:
        raise RunnerError('commit_binding_mismatch', 'commit response UUID is invalid') from exc
    if (
        response.plan_uuid != expected_plan_uuid
        or response.request_sha256 != server_request_sha256
        or response.catalog_sha256 != request.catalog_sha256
        or response.artifact_sha256 != expected_artifact_sha256
        or response.manifest_sha256 is None
        or SHA256_RE.fullmatch(response.manifest_sha256) is None
    ):
        raise RunnerError('commit_binding_mismatch', 'commit response binding is incomplete')
    assert request.provenance is not None
    counts = (
        response.entity_count,
        response.edge_count,
        response.source_count,
        response.evidence_link_count,
    )
    expected = (
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources),
        len(request.provenance.evidence_links),
    )
    if counts != expected:
        raise RunnerError('commit_count_mismatch', 'commit response counts do not match artifact')
    committed_total = (
        response.committed_created + response.committed_updated + response.committed_unchanged
    )
    expected_committed_total = (
        len(request.entities) + len(request.edges) + len(request.provenance.sources)
    )
    if committed_total != expected_committed_total:
        raise RunnerError(
            'commit_count_mismatch', 'committed outcome count does not match artifact'
        )
    return response


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
    if (
        response.found is not True
        or response.status != 'committed'
        or response.error_code is not None
        or response.error_summary
    ):
        raise RunnerError('status_not_committed', 'batch status is not cleanly committed')
    if response.request_sha256 != server_request_sha256:
        raise RunnerError('status_request_hash_mismatch', 'committed status request hash mismatch')
    if response.catalog_sha256 != request.catalog_sha256:
        raise RunnerError('status_catalog_hash_mismatch', 'committed status catalog hash mismatch')
    counts = (response.entity_count, response.edge_count, response.provenance_count)
    expected = (
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources) + len(request.provenance.evidence_links),
    )
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
    if (
        response.found is not True
        or response.group_id != request.group_id
        or response.batch_id != request.batch_id
    ):
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
    assert request.provenance is not None
    expected_evidence = len(request.provenance.evidence_links)
    if (
        response.evidence.expected != expected_evidence
        or response.evidence.found != expected_evidence
    ):
        raise RunnerError(
            'verify_evidence_count_mismatch', 'verify evidence counts do not match artifact'
        )
    anomaly_lists = (
        response.missing,
        response.extras,
        response.missing_provenance,
        response.entities.missing,
        response.entities.extras,
        response.entities.wrong_type,
        response.entities.generic_duplicate,
        response.entities.typed_duplicate,
        response.entities.uuid_mismatch,
        response.entities.missing_embedding,
        response.entities.content_hash_mismatch,
        response.edges.missing,
        response.edges.extras,
        response.edges.duplicate_edge_key,
        response.edges.edge_type_mismatch,
        response.edges.endpoint_mismatch,
        response.edges.uuid_mismatch,
        response.edges.missing_embedding,
        response.edges.content_hash_mismatch,
        response.evidence.missing,
        response.evidence.extras,
        response.evidence.link_key_mismatch,
        response.evidence.content_hash_mismatch,
    )
    if response.anomalies or any(anomaly_lists):
        raise RunnerError('verify_failed', 'verify response reports missing data or anomalies')


def _validate_resolve_response(
    structured: dict[str, Any], request: UpsertCatalogBatchRequest
) -> dict[tuple[str, str], str]:
    try:
        response = ResolveTypedEntitiesResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_resolve_response', 'resolve response has invalid structure'
        ) from exc
    if response.group_id != request.group_id or len(response.results) != len(request.entities):
        raise RunnerError('resolve_count_mismatch', 'resolve response identity or count mismatch')
    resolved: dict[tuple[str, str], str] = {}
    for item, expected in zip(response.results, request.entities, strict=True):
        try:
            uuid.UUID(item.uuid or '')
        except ValueError as exc:
            raise RunnerError('resolve_failed', 'resolve response contains invalid UUID') from exc
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
        assert item.uuid is not None
        resolved[(expected.entity_type, expected.graph_key)] = item.uuid
    return resolved


def _validate_node_search(
    structured: dict[str, Any],
    *,
    graph_key: str,
    group_id: str,
    entity_type: str,
    expected_uuid: str,
) -> None:
    nodes = structured.get('nodes')
    if not isinstance(nodes, list) or not any(
        isinstance(node, dict)
        and node.get('uuid') == expected_uuid
        and node.get('name') == graph_key
        and node.get('group_id') == group_id
        and entity_type in (node.get('labels') or [])
        for node in nodes
    ):
        raise RunnerError(
            'node_search_failed', 'node retrieval gate did not return expected entity'
        )


def _validate_fact_search(
    structured: dict[str, Any],
    edge: CatalogEdgeItem,
    *,
    group_id: str,
    expected_uuid: str,
    source_node_uuid: str | None = None,
    target_node_uuid: str | None = None,
) -> None:
    _validate_fact_search_strict(
        structured,
        group_id=group_id,
        expected_uuid=expected_uuid,
        edge_type=edge.edge_type,
        edge_key=edge.edge_key,
        source_node_uuid=source_node_uuid,
        target_node_uuid=target_node_uuid,
    )


def _validate_manifest_inventory(
    manifest: GetCatalogBatchManifestResponse,
    request: UpsertCatalogBatchRequest,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str], dict[str, str]]:
    assert request.provenance is not None
    if manifest.offset != 0:
        raise RunnerError('manifest_failed', 'manifest aggregate must start at offset zero')

    entity_expected = {
        (item.entity_type, item.graph_key): item.content_sha256 for item in request.entities
    }
    edge_expected = {(item.edge_type, item.edge_key): item.content_sha256 for item in request.edges}
    source_expected = {item.source_key: item.content_sha256 for item in request.provenance.sources}
    evidence_expected = {
        evidence_link_key(item): canonical_sha256(evidence_canonical_payload(item))
        for item in request.provenance.evidence_links
    }
    entity_found = {(item.entity_type, item.graph_key): item for item in manifest.entities}
    edge_found = {(item.edge_type, item.edge_key): item for item in manifest.edges}
    source_found = {item.source_key: item for item in manifest.sources}
    evidence_found = {item.link_key: item for item in manifest.evidence_links}
    if (
        len(manifest.entities) != len(entity_found)
        or len(manifest.edges) != len(edge_found)
        or len(manifest.sources) != len(source_found)
        or len(manifest.evidence_links) != len(evidence_found)
        or len(manifest.entities) != manifest.entity_count
        or len(manifest.edges) != manifest.edge_count
        or len(manifest.sources) != manifest.source_count
        or len(manifest.evidence_links) != manifest.evidence_link_count
        or set(entity_found) != set(entity_expected)
        or set(edge_found) != set(edge_expected)
        or set(source_found) != set(source_expected)
        or set(evidence_found) != set(evidence_expected)
    ):
        raise RunnerError('manifest_failed', 'manifest membership identities do not match artifact')
    if any(
        entity_found[key].content_sha256 != digest for key, digest in entity_expected.items()
    ) or any(edge_found[key].content_sha256 != digest for key, digest in edge_expected.items()):
        raise RunnerError('manifest_failed', 'manifest member content hashes do not match artifact')
    if any(source_found[key].content_sha256 != digest for key, digest in source_expected.items()):
        raise RunnerError('manifest_failed', 'manifest source hashes do not match artifact')
    if any(
        evidence_found[key].content_sha256 != digest for key, digest in evidence_expected.items()
    ):
        raise RunnerError('manifest_failed', 'manifest evidence hashes do not match artifact')
    all_members = [
        *manifest.entities,
        *manifest.edges,
        *manifest.sources,
        *manifest.evidence_links,
    ]
    try:
        for member in all_members:
            uuid.UUID(member.uuid)
    except ValueError as exc:
        raise RunnerError('manifest_failed', 'manifest member UUID is invalid') from exc
    return (
        {key: item.uuid for key, item in entity_found.items()},
        {key: item.uuid for key, item in edge_found.items()},
        {key: item.uuid for key, item in evidence_found.items()},
    )


def _validate_evidence_response(
    response: GetCatalogEvidenceResponse,
    request: UpsertCatalogBatchRequest,
    *,
    target_kind: str,
    target_key: str,
    target_uuid: str,
    expected_links: dict[str, str],
) -> None:
    assert request.provenance is not None
    expected_for_target = {
        evidence_link_key(item): canonical_sha256(evidence_canonical_payload(item))
        for item in request.provenance.evidence_links
        if (
            target_kind == 'entity'
            and item.entity_target is not None
            and item.entity_target.graph_key == target_key
        )
        or (
            target_kind == 'edge'
            and item.edge_target is not None
            and item.edge_target.edge_key == target_key
        )
    }
    found = {item.link_key: item for item in response.links}
    if (
        len(response.links) != len(found)
        or len(response.links) != response.total
        or response.found_target is not True
        or response.error_code is not None
        or response.error_message is not None
        or response.group_id != request.group_id
        or response.target_kind != target_kind
        or response.target_uuid != target_uuid
        or (target_kind == 'entity' and response.target_graph_key != target_key)
        or (target_kind == 'edge' and response.target_edge_key != target_key)
        or response.offset != 0
        or response.limit < len(expected_for_target)
        or response.total != len(expected_for_target)
        or set(found) != set(expected_for_target)
    ):
        raise RunnerError('evidence_failed', 'evidence response binding failed')
    for key, digest in expected_for_target.items():
        item = found[key]
        if (
            item.uuid != expected_links.get(key)
            or item.content_sha256 != digest
            or item.target_kind != target_kind
            or item.target_uuid != target_uuid
        ):
            raise RunnerError('evidence_failed', 'evidence link identity does not match manifest')


async def run_post_commit_gates(
    session: Any,
    request: UpsertCatalogBatchRequest,
    server_request_sha256: str,
    *,
    expected_manifest_sha256: str,
    expected_artifact_sha256: str,
) -> dict[str, Any]:
    """Run bounded post-commit read gates once; return token-free summaries."""
    summaries: dict[str, Any] = {}

    _, structured = await call_mcp_tool(
        session,
        'get_catalog_ingest_status',
        {'request': {'group_id': request.group_id, 'batch_id': request.batch_id}},
    )
    _validate_status_response(structured, request, server_request_sha256)
    status = CatalogIngestStatusResponse.model_validate(structured, strict=True)
    summaries['get_catalog_ingest_status'] = {
        'status': 'committed',
        'group_id': status.group_id,
        'batch_id': status.batch_id,
        'request_sha256': status.request_sha256,
        'catalog_sha256': status.catalog_sha256,
        'counts': [status.entity_count, status.edge_count, status.provenance_count],
    }

    # Legacy batch-scoped verification ignores endpoint refs, but strict request models
    # still require valid UUID syntax. Preserve the frozen Phase 5 call order with stable
    # non-authoritative UUIDv5 placeholders; the live path resolves exact endpoints first.
    placeholder_entities = {
        (item.entity_type, item.graph_key): str(
            uuid.uuid5(uuid.NAMESPACE_URL, f'{item.entity_type}|{item.graph_key}')
        )
        for item in request.entities
    }
    verify_request = build_verify_request(request, placeholder_entities)
    _, structured = await call_mcp_tool(
        session, 'verify_catalog_batch', {'request': verify_request}
    )
    _validate_verify_response(structured, request)
    verify = VerifyCatalogBatchResponse.model_validate(structured, strict=True)
    if verify.manifest_sha256 != expected_manifest_sha256:
        raise RunnerError('verify_failed', 'verify manifest hash does not match commit')
    summaries['verify_catalog_batch'] = {
        'manifest_sha256': verify.manifest_sha256,
        'counts': [verify.entities.expected, verify.edges.expected, verify.evidence.expected],
    }

    resolve_request = build_resolve_entities_request(request)
    _, structured = await call_mcp_tool(
        session, 'resolve_typed_entities', {'request': resolve_request}
    )
    resolved_entities = _validate_resolve_response(structured, request)
    summaries['resolve_typed_entities'] = {
        'found': len(request.entities),
        'uuids_sha256': canonical_sha256(
            {
                'entities': [
                    [entity_type, graph_key, entity_uuid]
                    for (entity_type, graph_key), entity_uuid in sorted(resolved_entities.items())
                ]
            }
        ),
    }

    assert request.provenance is not None
    manifest_limit = max(
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources),
        len(request.provenance.evidence_links),
    )
    _, structured = await call_mcp_tool(
        session,
        'get_catalog_batch_manifest',
        {
            'request': {
                'group_id': request.group_id,
                'batch_id': request.batch_id,
                'offset': 0,
                'limit': manifest_limit,
            }
        },
    )
    try:
        manifest = GetCatalogBatchManifestResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_manifest_response', 'manifest response has invalid structure'
        ) from exc
    if (
        not manifest.found
        or manifest.error_code is not None
        or manifest.error_message is not None
        or manifest.group_id != request.group_id
        or manifest.batch_id != request.batch_id
        or manifest.request_sha256 != server_request_sha256
        or manifest.catalog_sha256 != request.catalog_sha256
        or manifest.artifact_sha256 != expected_artifact_sha256
        or manifest.identity_schema_version != request.identity_schema_version
        or manifest.manifest_sha256 != expected_manifest_sha256
    ):
        raise RunnerError('manifest_failed', 'manifest response binding failed')
    assert request.provenance is not None
    manifest_counts = (
        manifest.entity_count,
        manifest.edge_count,
        manifest.source_count,
        manifest.evidence_link_count,
    )
    expected_counts = (
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources),
        len(request.provenance.evidence_links),
    )
    if manifest_counts != expected_counts:
        raise RunnerError('manifest_failed', 'manifest counts do not match artifact')
    manifest_entities, manifest_edges, manifest_evidence = _validate_manifest_inventory(
        manifest, request
    )
    if manifest_entities != resolved_entities:
        raise RunnerError('manifest_failed', 'manifest entity UUIDs differ from typed resolution')
    summaries['get_catalog_batch_manifest'] = {
        'manifest_sha256': manifest.manifest_sha256,
        'artifact_sha256': manifest.artifact_sha256,
        'counts': list(manifest_counts),
        'inventory_sha256': canonical_sha256(
            {
                'entities': sorted(
                    [entity_type, graph_key, entity_uuid]
                    for (entity_type, graph_key), entity_uuid in manifest_entities.items()
                ),
                'edges': sorted(
                    [edge_type, edge_key, edge_uuid]
                    for (edge_type, edge_key), edge_uuid in manifest_edges.items()
                ),
                'evidence_links': sorted(manifest_evidence.items()),
            }
        ),
    }

    representative_entity = request.entities[0]
    representative_edge = request.edges[0]
    evidence_target = (
        {
            'entity_target': {
                'entity_type': representative_entity.entity_type,
                'graph_key': representative_entity.graph_key,
            },
            'edge_target': None,
        }
        if representative_entity is not None
        else {
            'entity_target': None,
            'edge_target': {
                'edge_type': representative_edge.edge_type,
                'edge_key': representative_edge.edge_key,
            },
        }
    )
    _, structured = await call_mcp_tool(
        session,
        'get_catalog_evidence',
        {
            'request': {
                'group_id': request.group_id,
                'identity_schema_version': request.identity_schema_version,
                'system_key': request.system_key,
                **evidence_target,
                'offset': 0,
                'limit': 100,
                'include_excerpts': False,
            }
        },
    )
    try:
        evidence = GetCatalogEvidenceResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_evidence_response', 'evidence response has invalid structure'
        ) from exc
    target_kind = 'entity'
    target_key = representative_entity.graph_key
    target_uuid = manifest_entities[(representative_entity.entity_type, target_key)]
    _validate_evidence_response(
        evidence,
        request,
        target_kind=target_kind,
        target_key=target_key,
        target_uuid=target_uuid,
        expected_links=manifest_evidence,
    )
    summaries['get_catalog_evidence'] = {
        'total': evidence.total,
        'target_uuid': target_uuid,
    }
    node_type = representative_entity.entity_type
    node_key = representative_entity.graph_key
    _, structured = await call_mcp_tool(
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
    _validate_node_search(
        structured,
        graph_key=node_key,
        group_id=request.group_id,
        entity_type=node_type,
        expected_uuid=resolved_entities[(node_type, node_key)],
    )
    summaries['search_nodes'] = {'found': True}

    _, structured = await call_mcp_tool(
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
    expected_edge_uuid = manifest_edges[
        (representative_edge.edge_type, representative_edge.edge_key)
    ]
    _validate_fact_search(
        structured,
        representative_edge,
        group_id=request.group_id,
        expected_uuid=expected_edge_uuid,
        source_node_uuid=manifest_entities[
            (representative_edge.source_entity_type, representative_edge.source_graph_key)
        ],
        target_node_uuid=manifest_entities[
            (representative_edge.target_entity_type, representative_edge.target_graph_key)
        ],
    )
    summaries['search_memory_facts'] = {'found': True, 'uuid': expected_edge_uuid}
    return summaries


def _expected_domain_counts(request: UpsertCatalogBatchRequest) -> dict[str, int]:
    provenance = request.provenance
    return {
        'entities': len(request.entities),
        'edges': len(request.edges),
        'sources': len(provenance.sources if provenance else []),
        'evidence_links': len(provenance.evidence_links if provenance else []),
    }


def _prepare_receipt(response: PrepareCatalogBatchResponse) -> dict[str, Any]:
    return {
        'plan_uuid': response.plan_uuid,
        'request_sha256': response.request_sha256,
        'catalog_sha256': response.catalog_sha256,
        'artifact_sha256': response.artifact_sha256,
        'identity_schema_version': response.identity_schema_version,
        'expires_at': response.expires_at,
        'counts': {
            'entities': response.entity_count,
            'edges': response.edge_count,
            'sources': response.source_count,
            'evidence_links': response.evidence_link_count,
        },
    }


def _commit_receipt(response: CommitPreparedCatalogBatchResponse) -> dict[str, Any]:
    return {
        'plan_uuid': response.plan_uuid,
        'request_sha256': response.request_sha256,
        'catalog_sha256': response.catalog_sha256,
        'artifact_sha256': response.artifact_sha256,
        'state': response.state,
        'batch_uuid': response.batch_uuid,
        'manifest_sha256': response.manifest_sha256,
        'counts': {
            'entities': response.entity_count,
            'edges': response.edge_count,
            'sources': response.source_count,
            'evidence_links': response.evidence_link_count,
        },
        'committed_created': response.committed_created,
        'committed_updated': response.committed_updated,
        'committed_unchanged': response.committed_unchanged,
    }


def _durable_commit_receipt(response: CommitPreparedCatalogBatchResponse) -> dict[str, Any]:
    return {'receipt_source': 'commit_response', **_commit_receipt(response)}


def _hardened_response_wrapper_from_receipts(
    *,
    request: UpsertCatalogBatchRequest,
    payload_path: Path,
    artifact_sha256: str,
    artifact_size: int,
    server_request_sha256: str,
    prepare: dict[str, Any],
    commit: dict[str, Any],
    post_commit: dict[str, Any],
) -> dict[str, Any]:
    return {
        'schema_version': 2,
        'tool_sequence': COMMIT_TOOL_SEQUENCE,
        'mode': 'commit',
        'payload_path': _safe_relative_path(payload_path),
        'group_id': request.group_id,
        'batch_id': request.batch_id,
        'catalog_sha256': request.catalog_sha256,
        'identity_schema_version': request.identity_schema_version,
        'artifact_sha256': artifact_sha256,
        'artifact_size': artifact_size,
        'server_request_sha256': server_request_sha256,
        'recorded_at': utc_now(),
        'prepare': copy.deepcopy(prepare),
        'commit': copy.deepcopy(commit),
        'post_commit': post_commit,
    }


def _hardened_response_wrapper(
    *,
    request: UpsertCatalogBatchRequest,
    payload_path: Path,
    artifact_sha256: str,
    artifact_size: int,
    server_request_sha256: str,
    prepare: PrepareCatalogBatchResponse,
    commit: CommitPreparedCatalogBatchResponse,
    post_commit: dict[str, Any],
) -> dict[str, Any]:
    """Persist bounded receipts only; raw plan_token and protocol bodies stay in memory."""
    return _hardened_response_wrapper_from_receipts(
        request=request,
        payload_path=payload_path,
        artifact_sha256=artifact_sha256,
        artifact_size=artifact_size,
        server_request_sha256=server_request_sha256,
        prepare=_prepare_receipt(prepare),
        commit=_commit_receipt(commit),
        post_commit=post_commit,
    )


def _prepared_response_counts(response: CommitPreparedCatalogBatchResponse) -> dict[str, int]:
    return {
        'committed_created': response.committed_created,
        'committed_updated': response.committed_updated,
        'committed_unchanged': response.committed_unchanged,
        'entities': response.entity_count,
        'edges': response.edge_count,
        'sources': response.source_count,
        'evidence_links': response.evidence_link_count,
    }


def _commit_binding_from_receipt(
    receipt: dict[str, Any],
    *,
    request: UpsertCatalogBatchRequest,
    server_request_sha256: str,
    expected_artifact_sha256: str | None = None,
) -> dict[str, Any]:
    expected_fields = {
        'receipt_source',
        'plan_uuid',
        'request_sha256',
        'catalog_sha256',
        'artifact_sha256',
        'state',
        'batch_uuid',
        'manifest_sha256',
        'counts',
        'committed_created',
        'committed_updated',
        'committed_unchanged',
    }
    counts = receipt.get('counts')
    expected_counts = _expected_domain_counts(request)
    if (
        set(receipt) != expected_fields
        or receipt.get('receipt_source') != 'commit_response'
        or receipt.get('request_sha256') != server_request_sha256
        or receipt.get('catalog_sha256') != request.catalog_sha256
        or receipt.get('state') != 'COMMITTED'
        or counts != expected_counts
        or not isinstance(receipt.get('artifact_sha256'), str)
        or SHA256_RE.fullmatch(receipt['artifact_sha256']) is None
        or not isinstance(receipt.get('manifest_sha256'), str)
        or SHA256_RE.fullmatch(receipt['manifest_sha256']) is None
    ):
        raise RunnerError('invalid_checkpoint', 'commit receipt binding mismatch')
    if (
        expected_artifact_sha256 is not None
        and receipt['artifact_sha256'] != expected_artifact_sha256
    ):
        raise RunnerError('invalid_checkpoint', 'commit receipt artifact mismatch')
    try:
        if receipt.get('receipt_source') == 'commit_response':
            uuid.UUID(str(receipt.get('plan_uuid') or ''))
        uuid.UUID(str(receipt.get('batch_uuid') or ''))
    except ValueError as exc:
        raise RunnerError('invalid_checkpoint', 'commit receipt UUID is invalid') from exc
    raw_outcome_counts = (
        receipt.get('committed_created'),
        receipt.get('committed_updated'),
        receipt.get('committed_unchanged'),
    )
    if any(type(value) is not int or value < 0 for value in raw_outcome_counts):
        raise RunnerError('invalid_checkpoint', 'commit receipt outcome counts mismatch')
    outcome_counts = tuple(
        value
        for value in raw_outcome_counts
        if isinstance(value, int) and not isinstance(value, bool)
    )
    if sum(outcome_counts) != (
        expected_counts['entities'] + expected_counts['edges'] + expected_counts['sources']
    ):
        raise RunnerError('invalid_checkpoint', 'commit receipt outcome counts mismatch')
    return {
        'batch_uuid': receipt['batch_uuid'],
        'request_sha256': server_request_sha256,
        'catalog_sha256': request.catalog_sha256,
        'artifact_sha256': receipt['artifact_sha256'],
        'manifest_sha256': receipt['manifest_sha256'],
        'counts': expected_counts,
    }


def _validate_post_commit_summaries(
    post_commit: dict[str, Any],
    *,
    request: UpsertCatalogBatchRequest,
    server_request_sha256: str,
    manifest_sha256: str,
    expected_artifact_sha256: str | None = None,
) -> None:
    expected_counts = _expected_domain_counts(request)
    expected_provenance_count = expected_counts['sources'] + expected_counts['evidence_links']
    expected = {
        'get_catalog_ingest_status': {
            'status': 'committed',
            'group_id': request.group_id,
            'batch_id': request.batch_id,
            'request_sha256': server_request_sha256,
            'catalog_sha256': request.catalog_sha256,
            'counts': [
                expected_counts['entities'],
                expected_counts['edges'],
                expected_provenance_count,
            ],
        },
        'verify_catalog_batch': {
            'manifest_sha256': manifest_sha256,
            'counts': [
                expected_counts['entities'],
                expected_counts['edges'],
                expected_counts['evidence_links'],
            ],
        },
    }
    if set(post_commit) != set(COMMIT_TOOL_SEQUENCE[2:]):
        raise RunnerError('invalid_checkpoint', 'verified post-commit tool set mismatch')
    for key, value in expected.items():
        if post_commit.get(key) != value:
            raise RunnerError('invalid_checkpoint', 'verified post-commit summary mismatch')
    manifest_summary = post_commit.get('get_catalog_batch_manifest')
    evidence_summary = post_commit.get('get_catalog_evidence')
    if not isinstance(manifest_summary, dict) or (
        expected_artifact_sha256 is not None
        and manifest_summary.get('artifact_sha256') != expected_artifact_sha256
    ):
        raise RunnerError('invalid_checkpoint', 'verified post-commit artifact mismatch')
    resolve_summary = post_commit.get('resolve_typed_entities')
    node_summary = post_commit.get('search_nodes')
    fact_summary = post_commit.get('search_memory_facts')
    if (
        not isinstance(manifest_summary, dict)
        or manifest_summary.get('manifest_sha256') != manifest_sha256
        or manifest_summary.get('counts') != list(expected_counts.values())
        or not isinstance(manifest_summary.get('inventory_sha256'), str)
        or SHA256_RE.fullmatch(manifest_summary['inventory_sha256']) is None
        or not isinstance(resolve_summary, dict)
        or resolve_summary.get('found') != expected_counts['entities']
        or not isinstance(resolve_summary.get('uuids_sha256'), str)
        or SHA256_RE.fullmatch(resolve_summary['uuids_sha256']) is None
        or not isinstance(evidence_summary, dict)
        or evidence_summary.get('total', 0) < 1
        or not isinstance(evidence_summary.get('target_uuid'), str)
        or not isinstance(node_summary, dict)
        or node_summary.get('found') is not True
        or not isinstance(fact_summary, dict)
        or fact_summary.get('found') is not True
        or not isinstance(fact_summary.get('uuid'), str)
    ):
        raise RunnerError('invalid_checkpoint', 'verified post-commit evidence is incomplete')


def _committed_recovery_attempt(
    checkpoint_path: Path,
    *,
    request: UpsertCatalogBatchRequest,
    artifact_sha256: str,
    artifact_size: int,
    server_request_sha256: str,
) -> dict[str, Any] | None:
    if not checkpoint_path.exists():
        return None
    checkpoint = strict_json_load(checkpoint_path)
    if not isinstance(checkpoint, dict):
        raise RunnerError('invalid_checkpoint', 'checkpoint root must be an object')
    attempts = checkpoint.get('attempts', [])
    if not isinstance(attempts, list):
        raise RunnerError('invalid_checkpoint', 'checkpoint attempts must be an array')
    matches = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict)
        and attempt.get('batch_id') == request.batch_id
        and attempt.get('mode') == 'commit'
        and attempt.get('status') in {'commit_received', 'committed_verification_failed'}
        and attempt.get('artifact_sha256') == artifact_sha256
        and attempt.get('artifact_size') == artifact_size
        and attempt.get('server_request_sha256') == server_request_sha256
    ]
    if not matches:
        return None
    attempt = copy.deepcopy(matches[-1])
    prepare = attempt.get('prepare')
    commit = attempt.get('commit')
    if not isinstance(prepare, dict) or not isinstance(commit, dict):
        raise RunnerError('invalid_checkpoint', 'committed recovery receipt is incomplete')
    binding = _commit_binding_from_receipt(
        commit,
        request=request,
        server_request_sha256=server_request_sha256,
    )
    if (
        set(prepare)
        != {
            'plan_uuid',
            'request_sha256',
            'catalog_sha256',
            'artifact_sha256',
            'identity_schema_version',
            'expires_at',
            'counts',
        }
        or prepare.get('plan_uuid') != commit.get('plan_uuid')
        or prepare.get('request_sha256') != server_request_sha256
        or prepare.get('catalog_sha256') != request.catalog_sha256
        or prepare.get('artifact_sha256') != binding['artifact_sha256']
        or prepare.get('identity_schema_version') != request.identity_schema_version
        or prepare.get('counts') != binding['counts']
    ):
        raise RunnerError('invalid_checkpoint', 'committed recovery prepare binding mismatch')
    return attempt


def _requires_remote_reconciliation(
    checkpoint_path: Path,
    *,
    request: UpsertCatalogBatchRequest,
    artifact_sha256: str,
    artifact_size: int,
    server_request_sha256: str,
) -> bool:
    if not checkpoint_path.exists():
        return False
    checkpoint = strict_json_load(checkpoint_path)
    if not isinstance(checkpoint, dict):
        raise RunnerError('invalid_checkpoint', 'checkpoint root must be an object')
    attempts = checkpoint.get('attempts', [])
    if not isinstance(attempts, list):
        raise RunnerError('invalid_checkpoint', 'checkpoint attempts must be an array')
    matches = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict)
        and attempt.get('batch_id') == request.batch_id
        and attempt.get('mode') == 'commit'
        and attempt.get('artifact_sha256') == artifact_sha256
        and attempt.get('artifact_size') == artifact_size
        and attempt.get('server_request_sha256') == server_request_sha256
    ]
    if not matches:
        return False
    statuses = [attempt.get('status') for attempt in matches]
    last_terminal = next(
        (
            status
            for status in reversed(statuses)
            if status in {'commit_verified', 'commit_received', 'failed', 'failed_before_call'}
        ),
        None,
    )
    return statuses[-1] == 'uncertain' or (
        statuses[-1] == 'started' and last_terminal not in {'failed', 'failed_before_call'}
    )


async def _remote_commit_binding(
    session: ClientSession,
    request: UpsertCatalogBatchRequest,
    server_request_sha256: str,
) -> dict[str, Any] | None:
    _, structured = await call_mcp_tool(
        session,
        'get_catalog_ingest_status',
        {'request': {'group_id': request.group_id, 'batch_id': request.batch_id}},
    )
    try:
        status = CatalogIngestStatusResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_status_response', 'status response has invalid structure'
        ) from exc
    if status.group_id != request.group_id or status.batch_id != request.batch_id:
        raise RunnerError('status_identity_mismatch', 'status group or batch mismatch')
    if not status.found:
        if status.error_code is None and status.status == 'failed':
            return None
        raise RunnerError('status_read_failed', 'batch status lookup failed')
    _validate_status_response(structured, request, server_request_sha256)
    assert request.provenance is not None
    manifest_limit = max(
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources),
        len(request.provenance.evidence_links),
    )
    _, structured = await call_mcp_tool(
        session,
        'get_catalog_batch_manifest',
        {
            'request': {
                'group_id': request.group_id,
                'batch_id': request.batch_id,
                'offset': 0,
                'limit': manifest_limit,
            }
        },
    )
    try:
        manifest = GetCatalogBatchManifestResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_manifest_response', 'manifest response has invalid structure'
        ) from exc
    expected_counts = _expected_domain_counts(request)
    if (
        not manifest.found
        or manifest.error_code is not None
        or manifest.error_message is not None
        or manifest.group_id != request.group_id
        or manifest.batch_id != request.batch_id
        or manifest.request_sha256 != server_request_sha256
        or manifest.catalog_sha256 != request.catalog_sha256
        or manifest.identity_schema_version != request.identity_schema_version
        or manifest.entity_count != expected_counts['entities']
        or manifest.edge_count != expected_counts['edges']
        or manifest.source_count != expected_counts['sources']
        or manifest.evidence_link_count != expected_counts['evidence_links']
        or not isinstance(manifest.artifact_sha256, str)
        or SHA256_RE.fullmatch(manifest.artifact_sha256) is None
        or not isinstance(manifest.manifest_sha256, str)
        or SHA256_RE.fullmatch(manifest.manifest_sha256) is None
    ):
        raise RunnerError('manifest_failed', 'committed manifest binding failed')
    return {
        'batch_uuid': status.batch_uuid,
        'request_sha256': server_request_sha256,
        'catalog_sha256': request.catalog_sha256,
        'artifact_sha256': manifest.artifact_sha256,
        'manifest_sha256': manifest.manifest_sha256,
        'counts': expected_counts,
    }


def _verified_commit_result(
    checkpoint_path: Path,
    *,
    request: UpsertCatalogBatchRequest,
    artifact_sha256: str,
    artifact_size: int,
    server_request_sha256: str,
) -> dict[str, Any] | None:
    """Return validated local evidence requiring fresh remote read verification."""
    if not checkpoint_path.exists():
        return None
    checkpoint = strict_json_load(checkpoint_path)
    if not isinstance(checkpoint, dict):
        raise RunnerError('invalid_checkpoint', 'checkpoint root must be an object')
    attempts = checkpoint.get('attempts', [])
    if not isinstance(attempts, list):
        raise RunnerError('invalid_checkpoint', 'checkpoint attempts must be an array')
    matches = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict)
        and attempt.get('batch_id') == request.batch_id
        and attempt.get('mode') == 'commit'
        and attempt.get('status') == 'commit_verified'
        and attempt.get('artifact_sha256') == artifact_sha256
        and attempt.get('artifact_size') == artifact_size
        and attempt.get('server_request_sha256') == server_request_sha256
    ]
    if not matches:
        return None
    attempt = matches[-1]
    rel = attempt.get('response_path')
    expected_response_sha = attempt.get('response_sha256')
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or '..' in Path(rel).parts:
        raise RunnerError('invalid_checkpoint', 'verified response path is invalid')
    root_candidate = (ROOT / rel).resolve()
    checkpoint_candidate = (checkpoint_path.parent / rel).resolve()
    if root_candidate.is_file():
        response_path = root_candidate
        boundary = ROOT.resolve()
    elif checkpoint_candidate.is_file():
        response_path = checkpoint_candidate
        boundary = checkpoint_path.parent.resolve()
    else:
        raise RunnerError('invalid_checkpoint', 'verified response is missing')
    try:
        response_path.relative_to(boundary)
    except ValueError as exc:
        raise RunnerError('invalid_checkpoint', 'verified response path escapes boundary') from exc
    try:
        response_bytes = response_path.read_bytes()
    except OSError as exc:
        raise RunnerError('invalid_checkpoint', 'verified response is unreadable') from exc
    if (
        not isinstance(expected_response_sha, str)
        or sha256_bytes(response_bytes) != expected_response_sha
    ):
        raise RunnerError('invalid_checkpoint', 'verified response digest mismatch')
    wrapper = strict_json_loads(response_bytes)
    if not isinstance(wrapper, dict):
        raise RunnerError('invalid_checkpoint', 'verified response root is invalid')
    expected_counts = _expected_domain_counts(request)
    prepare = wrapper.get('prepare')
    commit = wrapper.get('commit')
    post_commit = wrapper.get('post_commit')
    recorded_counts = attempt.get('counts')
    if (
        set(wrapper)
        != {
            'schema_version',
            'tool_sequence',
            'mode',
            'payload_path',
            'group_id',
            'batch_id',
            'catalog_sha256',
            'identity_schema_version',
            'artifact_sha256',
            'artifact_size',
            'server_request_sha256',
            'recorded_at',
            'prepare',
            'commit',
            'post_commit',
        }
        or wrapper.get('schema_version') != 2
        or wrapper.get('tool_sequence') != COMMIT_TOOL_SEQUENCE
        or wrapper.get('mode') != 'commit'
        or wrapper.get('group_id') != request.group_id
        or wrapper.get('batch_id') != request.batch_id
        or wrapper.get('catalog_sha256') != request.catalog_sha256
        or wrapper.get('identity_schema_version') != request.identity_schema_version
        or wrapper.get('artifact_sha256') != artifact_sha256
        or wrapper.get('artifact_size') != artifact_size
        or wrapper.get('server_request_sha256') != server_request_sha256
        or not isinstance(prepare, dict)
        or not isinstance(commit, dict)
        or not isinstance(post_commit, dict)
        or set(post_commit) != set(COMMIT_TOOL_SEQUENCE[2:])
        or not isinstance(recorded_counts, dict)
    ):
        raise RunnerError('invalid_checkpoint', 'verified response binding mismatch')
    if (
        set(prepare)
        != {
            'plan_uuid',
            'request_sha256',
            'catalog_sha256',
            'artifact_sha256',
            'identity_schema_version',
            'expires_at',
            'counts',
        }
        or prepare.get('request_sha256') != server_request_sha256
        or prepare.get('catalog_sha256') != request.catalog_sha256
        or prepare.get('identity_schema_version') != request.identity_schema_version
        or prepare.get('counts') != expected_counts
        or set(commit)
        != {
            'plan_uuid',
            'request_sha256',
            'catalog_sha256',
            'artifact_sha256',
            'state',
            'batch_uuid',
            'manifest_sha256',
            'counts',
            'committed_created',
            'committed_updated',
            'committed_unchanged',
        }
        or commit.get('plan_uuid') != prepare.get('plan_uuid')
        or commit.get('request_sha256') != server_request_sha256
        or commit.get('catalog_sha256') != request.catalog_sha256
        or commit.get('artifact_sha256') != prepare.get('artifact_sha256')
        or commit.get('state') != 'COMMITTED'
        or commit.get('counts') != expected_counts
        or not isinstance(commit.get('manifest_sha256'), str)
        or SHA256_RE.fullmatch(commit['manifest_sha256']) is None
    ):
        raise RunnerError('invalid_checkpoint', 'verified prepare/commit binding mismatch')
    try:
        if prepare.get('plan_uuid') is not None:
            uuid.UUID(str(prepare['plan_uuid']))
        uuid.UUID(str(commit.get('batch_uuid') or ''))
    except ValueError as exc:
        raise RunnerError('invalid_checkpoint', 'verified response UUID is invalid') from exc
    expected_recorded_counts = {
        'committed_created': commit.get('committed_created'),
        'committed_updated': commit.get('committed_updated'),
        'committed_unchanged': commit.get('committed_unchanged'),
        **expected_counts,
    }
    if recorded_counts != expected_recorded_counts:
        raise RunnerError('invalid_checkpoint', 'verified response counts mismatch')
    _validate_post_commit_summaries(
        post_commit,
        request=request,
        server_request_sha256=server_request_sha256,
        manifest_sha256=str(commit['manifest_sha256']),
        expected_artifact_sha256=str(commit['artifact_sha256']),
    )
    return {
        'ok': True,
        'mode': 'commit',
        'batch_id': request.batch_id,
        'artifact_sha256': artifact_sha256,
        'server_request_sha256': server_request_sha256,
        'response_path': rel,
        'response_sha256': expected_response_sha,
        'status': 'commit_verified',
        'counts': copy.deepcopy(recorded_counts),
        'replayed_from_checkpoint': True,
        '_commit': copy.deepcopy(commit),
        '_post_commit': copy.deepcopy(post_commit),
    }


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
    """Execute the hardened prepare/token-only-commit path.

    ponytail: historical direct-upsert execution is intentionally unsupported; use
    archived historical evidence for history, never as current execution authority.
    """
    if args.mode != 'commit':
        raise RunnerError('hardened_commit_only', 'hardened runner supports commit mode only')
    payload_path = args.payload.resolve()
    checkpoint_path = args.checkpoint.resolve()
    if not bool(getattr(args, 'allow_test_paths', False)):
        hardened_root = HARDENED_ARTIFACT_DIR.resolve()
        try:
            payload_path.relative_to(hardened_root)
            checkpoint_path.relative_to(hardened_root)
        except ValueError as exc:
            raise RunnerError(
                'path_outside_hardened_dir',
                'payload and checkpoint paths must be inside the hardened artifact directory',
            ) from exc
    artifact_bytes, raw, _, artifact_sha256, server_request_sha256 = validate_hardened_artifact(
        payload_path,
        expected_artifact_sha256=args.expected_artifact_sha256,
        expected_request_sha256=args.expected_request_sha256,
    )
    validated = UpsertCatalogBatchRequest.model_validate({**raw, 'dry_run': False}, strict=True)
    prior = _verified_commit_result(
        checkpoint_path,
        request=validated,
        artifact_sha256=artifact_sha256,
        artifact_size=len(artifact_bytes),
        server_request_sha256=server_request_sha256,
    )
    if prior is not None:
        commit = prior.pop('_commit')
        expected_post_commit = prior.pop('_post_commit')
        if not isinstance(commit, dict) or not isinstance(expected_post_commit, dict):
            raise RunnerError('invalid_checkpoint', 'verified commit evidence is invalid')
        manifest_sha256 = commit.get('manifest_sha256')
        prepared_artifact_sha256 = commit.get('artifact_sha256')
        if not isinstance(manifest_sha256, str) or not isinstance(prepared_artifact_sha256, str):
            raise RunnerError('invalid_checkpoint', 'verified commit binding is incomplete')
        async with (
            streamable_http_client(args.mcp_url) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            post_commit = await run_post_commit_gates(
                session,
                validated,
                server_request_sha256,
                expected_manifest_sha256=manifest_sha256,
                expected_artifact_sha256=prepared_artifact_sha256,
            )
        if post_commit != expected_post_commit:
            raise RunnerError('invalid_checkpoint', 'fresh verification differs from checkpoint')
        return prior

    recovery = _committed_recovery_attempt(
        checkpoint_path,
        request=validated,
        artifact_sha256=artifact_sha256,
        artifact_size=len(artifact_bytes),
        server_request_sha256=server_request_sha256,
    )
    response_path = response_path_for(payload_path, 'commit')
    if recovery is not None:
        prepare = recovery['prepare']
        commit = recovery['commit']
        binding = _commit_binding_from_receipt(
            commit,
            request=validated,
            server_request_sha256=server_request_sha256,
            expected_artifact_sha256=str(prepare['artifact_sha256']),
        )
        async with (
            streamable_http_client(args.mcp_url) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            remote = await _remote_commit_binding(session, validated, server_request_sha256)
            if remote != binding:
                raise RunnerError('recovery_binding_mismatch', 'remote commit differs from receipt')
            post_commit = await run_post_commit_gates(
                session,
                validated,
                server_request_sha256,
                expected_manifest_sha256=binding['manifest_sha256'],
                expected_artifact_sha256=binding['artifact_sha256'],
            )
        wrapper = _hardened_response_wrapper_from_receipts(
            request=validated,
            payload_path=payload_path,
            artifact_sha256=artifact_sha256,
            artifact_size=len(artifact_bytes),
            server_request_sha256=server_request_sha256,
            prepare=prepare,
            commit={key: value for key, value in commit.items() if key != 'receipt_source'},
            post_commit=post_commit,
        )
        response_sha256 = atomic_write_json(response_path, wrapper)
        completed = _base_attempt(
            payload_path=payload_path,
            mode='commit',
            artifact_sha256=artifact_sha256,
            artifact_size=len(artifact_bytes),
            server_request_sha256=server_request_sha256,
            batch_id=validated.batch_id,
            started_at=utc_now(),
        )
        completed.update(
            {
                'status': 'commit_verified',
                'response_path': _safe_relative_path(response_path),
                'response_sha256': response_sha256,
                'counts': {
                    'committed_created': commit['committed_created'],
                    'committed_updated': commit['committed_updated'],
                    'committed_unchanged': commit['committed_unchanged'],
                    **binding['counts'],
                },
                'completed_at': utc_now(),
                'recovered_from_committed_receipt': True,
            }
        )
        append_checkpoint_attempt(checkpoint_path, completed)
        return {
            'ok': True,
            'mode': 'commit',
            'batch_id': validated.batch_id,
            'artifact_sha256': artifact_sha256,
            'server_request_sha256': server_request_sha256,
            'response_path': _safe_relative_path(response_path),
            'response_sha256': response_sha256,
            'status': 'commit_verified',
            'counts': completed['counts'],
            'recovered_from_committed_receipt': True,
        }

    if _requires_remote_reconciliation(
        checkpoint_path,
        request=validated,
        artifact_sha256=artifact_sha256,
        artifact_size=len(artifact_bytes),
        server_request_sha256=server_request_sha256,
    ):
        async with (
            streamable_http_client(args.mcp_url) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            remote = await _remote_commit_binding(session, validated, server_request_sha256)
            if remote is None:
                raise RunnerError(
                    'transport_outcome_unknown',
                    'prior commit outcome cannot be safely retried without a durable receipt',
                )
            post_commit = await run_post_commit_gates(
                session,
                validated,
                server_request_sha256,
                expected_manifest_sha256=remote['manifest_sha256'],
                expected_artifact_sha256=remote['artifact_sha256'],
            )
        prepare = {
            'plan_uuid': None,
            'request_sha256': server_request_sha256,
            'catalog_sha256': validated.catalog_sha256,
            'artifact_sha256': remote['artifact_sha256'],
            'identity_schema_version': validated.identity_schema_version,
            'expires_at': None,
            'counts': copy.deepcopy(remote['counts']),
        }
        commit = {
            'plan_uuid': None,
            'request_sha256': server_request_sha256,
            'catalog_sha256': validated.catalog_sha256,
            'artifact_sha256': remote['artifact_sha256'],
            'state': 'COMMITTED',
            'batch_uuid': remote['batch_uuid'],
            'manifest_sha256': remote['manifest_sha256'],
            'counts': copy.deepcopy(remote['counts']),
            'committed_created': 0,
            'committed_updated': 0,
            'committed_unchanged': (
                remote['counts']['entities']
                + remote['counts']['edges']
                + remote['counts']['sources']
            ),
        }
        wrapper = _hardened_response_wrapper_from_receipts(
            request=validated,
            payload_path=payload_path,
            artifact_sha256=artifact_sha256,
            artifact_size=len(artifact_bytes),
            server_request_sha256=server_request_sha256,
            prepare=prepare,
            commit=commit,
            post_commit=post_commit,
        )
        response_sha256 = atomic_write_json(response_path, wrapper)
        completed = _base_attempt(
            payload_path=payload_path,
            mode='commit',
            artifact_sha256=artifact_sha256,
            artifact_size=len(artifact_bytes),
            server_request_sha256=server_request_sha256,
            batch_id=validated.batch_id,
            started_at=utc_now(),
        )
        completed.update(
            {
                'status': 'commit_verified',
                'response_path': _safe_relative_path(response_path),
                'response_sha256': response_sha256,
                'counts': {
                    'committed_created': 0,
                    'committed_updated': 0,
                    'committed_unchanged': commit['committed_unchanged'],
                    **remote['counts'],
                },
                'completed_at': utc_now(),
                'reconciled_from_remote_state': True,
            }
        )
        append_checkpoint_attempt(checkpoint_path, completed)
        return {
            'ok': True,
            'mode': 'commit',
            'batch_id': validated.batch_id,
            'artifact_sha256': artifact_sha256,
            'server_request_sha256': server_request_sha256,
            'response_path': _safe_relative_path(response_path),
            'response_sha256': response_sha256,
            'status': 'commit_verified',
            'counts': completed['counts'],
            'reconciled_from_remote_state': True,
        }

    attempt = _base_attempt(
        payload_path=payload_path,
        mode='commit',
        artifact_sha256=artifact_sha256,
        artifact_size=len(artifact_bytes),
        server_request_sha256=server_request_sha256,
        batch_id=validated.batch_id,
        started_at=utc_now(),
    )
    attempt['response_path'] = _safe_relative_path(response_path)
    append_checkpoint_attempt(checkpoint_path, attempt)
    call_started = False
    commit_started = False
    committed: CommitPreparedCatalogBatchResponse | None = None
    try:
        current_bytes = payload_path.read_bytes()
        if current_bytes != artifact_bytes or sha256_bytes(current_bytes) != artifact_sha256:
            raise RunnerError('artifact_changed', 'artifact bytes changed before prepare')
        prepare_body = build_prepare_transport_request(raw)
        async with (
            streamable_http_client(args.mcp_url) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            call_started = True
            _, structured = await call_mcp_tool(
                session, 'prepare_catalog_batch', {'request': prepare_body}
            )
            prepared, plan_token = _validate_prepare_response(
                structured, validated, server_request_sha256
            )
            commit_body = build_commit_transport_request(
                plan_token, expected_request_sha256=server_request_sha256
            )
            commit_started = True
            _, structured = await call_mcp_tool(
                session, 'commit_prepared_catalog_batch', {'request': commit_body}
            )
            commit_response = _validate_commit_response(
                structured,
                validated,
                server_request_sha256,
                expected_plan_uuid=prepared.plan_uuid,
                expected_artifact_sha256=prepared.artifact_sha256,
            )
            committed = commit_response
            attempt['status'] = 'commit_received'
            attempt['prepare'] = _prepare_receipt(prepared)
            attempt['commit'] = _durable_commit_receipt(committed)
            attempt['counts'] = _prepared_response_counts(committed)
            attempt['completed_at'] = utc_now()
            append_checkpoint_attempt(checkpoint_path, attempt)
            manifest_sha256 = commit_response.manifest_sha256
            assert manifest_sha256 is not None
            post_commit = await run_post_commit_gates(
                session,
                validated,
                server_request_sha256,
                expected_manifest_sha256=manifest_sha256,
                expected_artifact_sha256=prepared.artifact_sha256,
            )
            wrapper = _hardened_response_wrapper(
                request=validated,
                payload_path=payload_path,
                artifact_sha256=artifact_sha256,
                artifact_size=len(artifact_bytes),
                server_request_sha256=server_request_sha256,
                prepare=prepared,
                commit=committed,
                post_commit=post_commit,
            )
            if plan_token in json.dumps(wrapper, ensure_ascii=False):
                raise RunnerError('token_persistence', 'raw plan token reached response wrapper')
            attempt['response_sha256'] = atomic_write_json(response_path, wrapper)
    except BaseException as exc:
        attempt['status'] = (
            'committed_verification_failed'
            if committed is not None and committed.state == 'COMMITTED'
            else 'uncertain'
            if commit_started
            else 'failed'
            if call_started
            else 'failed_before_call'
        )
        attempt['error_code'] = (
            exc.code
            if isinstance(exc, RunnerError)
            else 'post_commit_verification_failed'
            if committed is not None and committed.state == 'COMMITTED'
            else 'transport_outcome_uncertain'
            if commit_started
            else 'response_processing_failed'
            if call_started
            else 'transport_setup_failed'
        )
        attempt['error_type'] = type(exc).__name__
        attempt['completed_at'] = utc_now()
        append_checkpoint_attempt(checkpoint_path, attempt)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(exc, RunnerError):
            raise
        raise RunnerError(attempt['error_code'], 'hardened execution failed closed') from exc

    assert committed is not None
    attempt['status'] = 'commit_verified'
    attempt['counts'] = _prepared_response_counts(committed)
    attempt['completed_at'] = utc_now()
    append_checkpoint_attempt(checkpoint_path, attempt)
    return {
        'ok': True,
        'mode': 'commit',
        'batch_id': validated.batch_id,
        'artifact_sha256': artifact_sha256,
        'server_request_sha256': server_request_sha256,
        'response_path': _safe_relative_path(response_path),
        'response_sha256': attempt['response_sha256'],
        'status': attempt['status'],
        'counts': attempt['counts'],
    }


def _reject_live_group(group_id: str) -> None:
    if group_id.strip().casefold() in {item.casefold() for item in PROTECTED_GROUP_IDS}:
        raise RunnerError('protected_group', 'protected group is forbidden')


def source_authority_map(*, mode: str = 'git', revision: str = 'HEAD') -> dict[str, dict[str, str]]:
    """Exact and canonical text digests from Git blobs or a bound archive tree."""
    result: dict[str, dict[str, str]] = {}
    for relative in SOURCE_AUTHORITY_PATHS:
        try:
            raw = authority_bytes(ROOT, relative, mode=mode, revision=revision)
            result[relative] = authority_digest(raw)
        except ValueError as exc:
            raise RunnerError(
                'source_attestation_missing', 'source authority bytes are unavailable'
            ) from exc
    return result


def attest_local_source(
    *,
    expected_head: str,
    expected_source_map_sha256: str,
    expected_runner_sha256: str,
    authority_mode: str = 'git',
) -> dict[str, Any]:
    if SOURCE_HEAD_RE.fullmatch(expected_head) is None:
        raise RunnerError('source_attestation_invalid', 'expected HEAD must be lowercase Git SHA-1')
    for value in (expected_source_map_sha256, expected_runner_sha256):
        if SHA256_RE.fullmatch(value) is None:
            raise RunnerError(
                'source_attestation_invalid', 'source digest must be lowercase SHA-256'
            )
    if authority_mode not in {'git', 'archive'}:
        raise RunnerError('source_attestation_invalid', 'authority mode must be git or archive')
    head = expected_head
    if authority_mode == 'git':
        try:
            head = subprocess.run(
                ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RunnerError(
                'source_attestation_failed', 'read-only Git attestation failed'
            ) from exc
    source_map = source_authority_map(mode=authority_mode, revision=expected_head)
    if authority_mode == 'git':
        for relative in SOURCE_AUTHORITY_PATHS:
            try:
                worktree = authority_bytes(ROOT, relative, mode='archive')
            except ValueError as exc:
                raise RunnerError(
                    'source_attestation_missing', 'source authority worktree file is unavailable'
                ) from exc
            if sha256_canonical_text_bytes(worktree) != source_map[relative]['lf_sha256']:
                raise RunnerError(
                    'source_attestation_dirty', 'harness authority path differs semantically'
                )
    source_map_sha256 = canonical_sha256({'files': source_map})
    runner_sha256 = source_map['scripts/run_catalog_canary_batch.py']['lf_sha256']
    if (
        head != expected_head
        or source_map_sha256 != expected_source_map_sha256
        or runner_sha256 != expected_runner_sha256
    ):
        raise RunnerError(
            'source_attestation_mismatch', 'reviewed source attestation does not match'
        )
    return {
        'source_head': head,
        'source_map_sha256': source_map_sha256,
        'runner_sha256': runner_sha256,
        'source_files': len(source_map),
    }


class ToolLedger:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(
        self, *, tool: str, stage: str, success: bool, error_code: str | None = None
    ) -> None:
        self.entries.append(
            {
                'ordinal': len(self.entries) + 1,
                'tool': tool,
                'stage': stage,
                'success': success,
                'error_code': error_code,
            }
        )


_LEDGER_ENTRY_KEYS = frozenset({'ordinal', 'tool', 'stage', 'success', 'error_code'})


def validate_tool_ledger(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Fail closed on shape, ordinals, and success/error_code consistency. tool_count stays 28."""
    if not isinstance(entries, list):
        raise RunnerError('tool_ledger_invalid', 'tool ledger entries must be a list')
    n = len(entries)
    seen_ordinals: set[int] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RunnerError('tool_ledger_invalid', 'tool ledger entry must be an object')
        if set(entry.keys()) != _LEDGER_ENTRY_KEYS:
            raise RunnerError(
                'tool_ledger_invalid',
                'tool ledger entry keys must be exactly {ordinal,tool,stage,success,error_code}',
            )
        ordinal = entry.get('ordinal')
        if type(ordinal) is not int:
            raise RunnerError('tool_ledger_invalid', 'tool ledger ordinal must be exact int')
        expected = index + 1
        if ordinal != expected:
            raise RunnerError(
                'tool_ledger_invalid', 'tool ledger ordinals must be unique contiguous 1..N'
            )
        if ordinal in seen_ordinals:
            raise RunnerError('tool_ledger_invalid', 'tool ledger ordinal is duplicated')
        seen_ordinals.add(ordinal)
        if type(entry['success']) is not bool:
            raise RunnerError('tool_ledger_invalid', 'tool ledger success must be bool')
        if not isinstance(entry['tool'], str) or not entry['tool']:
            raise RunnerError('tool_ledger_invalid', 'tool ledger tool must be non-empty string')
        if not isinstance(entry['stage'], str) or not entry['stage']:
            raise RunnerError('tool_ledger_invalid', 'tool ledger stage must be non-empty string')
        error_code = entry['error_code']
        if entry['success'] is True:
            if error_code is not None:
                raise RunnerError(
                    'tool_ledger_invalid', 'successful ledger entry requires error_code None'
                )
        else:
            if not isinstance(error_code, str) or not error_code:
                raise RunnerError(
                    'tool_ledger_invalid',
                    'failed ledger entry requires non-empty string error_code',
                )
    if seen_ordinals != set(range(1, n + 1)):
        raise RunnerError(
            'tool_ledger_invalid', 'tool ledger ordinals must be unique contiguous 1..N'
        )
    return {
        'tool_call_count': n,
        'final_ordinal': n if n else 0,
        'tool_count': 28,
    }


def validate_report_ledger_metadata(report: dict[str, Any], ledger_meta: dict[str, int]) -> None:
    """Reject terminal report metadata that disagrees with validated ledger counts."""
    if not isinstance(report, dict):
        raise RunnerError('tool_ledger_invalid', 'terminal report must be an object')
    if report.get('tool_count') != 28 or report.get('tool_count') != ledger_meta['tool_count']:
        raise RunnerError('tool_ledger_invalid', 'report tool_count must equal registered 28')
    if report.get('tool_call_count') != ledger_meta['tool_call_count']:
        raise RunnerError(
            'tool_ledger_invalid', 'report tool_call_count must match validated ledger'
        )
    if report.get('final_ordinal') != ledger_meta['final_ordinal']:
        raise RunnerError('tool_ledger_invalid', 'report final_ordinal must match validated ledger')


# Host-side execution boundary: exact Docker Compose form, fixed files/services.
COMPOSE_BASE_FILE = 'mcp_server/docker/docker-compose-neo4j.yml'
COMPOSE_OVERRIDE_FILE = 'mcp_server/docker/docker-compose-neo4j.catalog-local.override.yml'
COMPOSE_PROJECT_NAME = 'graphiti-catalog-local'
DEFAULT_MCP_IMAGE = 'thienpvt/mem0:graphiti-mcp'
REQUIRED_COMPOSE_FILES = (COMPOSE_BASE_FILE, COMPOSE_OVERRIDE_FILE)
COMPOSE_GENERATED_CONFIG = 'mcp_server/config/config-docker-neo4j.catalog-local.yaml'
COMPOSE_PROJECT_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')
LOCAL_IMAGE_RE = re.compile(r'^[a-z0-9][a-z0-9_.-]*(?:/[a-z0-9][a-z0-9_.-]*)*:[A-Za-z0-9_.-]+$')
IMAGE_ID_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
PUBLIC_COMPOSE_ACTIONS = ('render', 'neo4j', 'bootstrap', 'mcp', 'status', 'inspect')
HOST_EXECUTION_AUTHORITY_PATHS = (
    COMPOSE_BASE_FILE,
    COMPOSE_OVERRIDE_FILE,
    'mcp_server/src/services/catalog_schema_bootstrap.py',
    COMPOSE_GENERATED_CONFIG,
)


class ComposeOptions:
    def __init__(
        self,
        project: str = COMPOSE_PROJECT_NAME,
        clean_room: bool = False,
        neo4j_http_port: int = 7474,
        neo4j_bolt_port: int = 7687,
        mcp_port: int = 8000,
        image: str = DEFAULT_MCP_IMAGE,
        expected_image_id: str | None = None,
    ) -> None:
        self.project = project
        self.clean_room = clean_room
        self.neo4j_http_port = neo4j_http_port
        self.neo4j_bolt_port = neo4j_bolt_port
        self.mcp_port = mcp_port
        self.image = image
        self.expected_image_id = expected_image_id
        resolve_compose_project(project, clean_room=clean_room)
        _validate_compose_ports(neo4j_http_port, neo4j_bolt_port, mcp_port)
        _validate_image(image, expected_image_id, clean_room=clean_room)


def resolve_compose_project(project: str | None, *, clean_room: bool) -> str:
    if not clean_room and project is None:
        return COMPOSE_PROJECT_NAME
    if not isinstance(project, str) or COMPOSE_PROJECT_RE.fullmatch(project) is None:
        raise RunnerError(
            'execution_boundary_violation', 'project must use Docker Compose project syntax'
        )
    return project


def compose_resource_identities(project: str) -> dict[str, str]:
    validated = resolve_compose_project(project, clean_room=True)
    return {
        'data_volume': f'{validated}_neo4j_data',
        'logs_volume': f'{validated}_neo4j_logs',
        'network': f'{validated}_default',
        'neo4j_container': f'{validated}-neo4j-1',
        'mcp_container': f'{validated}-graphiti-mcp-1',
        'bootstrap_container': f'{validated}-catalog-bootstrap-1',
    }


def _validate_compose_ports(*ports: int) -> None:
    if any(type(port) is not int or not 1 <= port <= 65535 for port in ports):
        raise RunnerError('execution_boundary_violation', 'ports must be integers in 1..65535')
    if len(set(ports)) != len(ports):
        raise RunnerError('execution_boundary_violation', 'selected host ports must be distinct')


def _validate_image(image: str, expected_image_id: str | None, *, clean_room: bool) -> None:
    if not isinstance(image, str) or LOCAL_IMAGE_RE.fullmatch(image) is None:
        raise RunnerError('execution_boundary_violation', 'image must be an explicit local tag')
    if clean_room and (
        not isinstance(expected_image_id, str) or IMAGE_ID_RE.fullmatch(expected_image_id) is None
    ):
        raise RunnerError(
            'execution_boundary_violation', 'clean-room expected image ID must be sha256-prefixed'
        )


def validate_compose_runtime_contract(
    *,
    clean_room: bool,
    project: str | None,
    neo4j_http_port: int,
    neo4j_bolt_port: int,
    mcp_port: int,
    image: str,
    expected_image_id: str | None,
    existing_resources: set[str],
) -> dict[str, Any]:
    selected = resolve_compose_project(project, clean_room=clean_room)
    options = ComposeOptions(
        project=selected,
        clean_room=clean_room,
        neo4j_http_port=neo4j_http_port,
        neo4j_bolt_port=neo4j_bolt_port,
        mcp_port=mcp_port,
        image=image,
        expected_image_id=expected_image_id,
    )
    resources = compose_resource_identities(selected)
    if set(resources.values()) & set(existing_resources):
        raise RunnerError(
            'execution_boundary_violation', 'selected clean-room resource already exists'
        )
    return {
        'project': options.project,
        'clean_room': options.clean_room,
        'resources': resources,
        'volumes_absent': all(
            resources[name] not in existing_resources for name in ('data_volume', 'logs_volume')
        ),
    }


def _compose_prefix(options: ComposeOptions) -> list[str]:
    return [
        'docker',
        'compose',
        '--project-name',
        options.project,
        '-f',
        COMPOSE_BASE_FILE,
        '-f',
        COMPOSE_OVERRIDE_FILE,
    ]


def _compose_suffix(action: str) -> list[str]:
    suffixes = {
        'render': ['config', '--quiet'],
        'neo4j': ['up', '--no-build', '--pull', 'never', '-d', 'neo4j'],
        'bootstrap': [
            '--profile',
            'catalog-bootstrap',
            'run',
            '--no-deps',
            '--no-build',
            '--pull',
            'never',
            '--rm',
            'catalog-bootstrap',
        ],
        'mcp': [
            'up',
            '--no-deps',
            '--no-build',
            '--pull',
            'never',
            '-d',
            'graphiti-mcp',
        ],
        'status': ['ps', '--format', 'json', 'neo4j', 'graphiti-mcp'],
        'inspect': ['images', '--format', 'json', 'neo4j', 'graphiti-mcp'],
    }
    try:
        return suffixes[action]
    except KeyError as exc:
        raise RunnerError(
            'execution_boundary_violation', 'compose action is not allowlisted'
        ) from exc


def compose_argv(action: str, options: ComposeOptions | None = None) -> list[str]:
    selected = options or ComposeOptions()
    return [*_compose_prefix(selected), *_compose_suffix(action)]


def validate_execution_command(
    argv: list[str] | str, options: ComposeOptions | None = None
) -> dict[str, Any]:
    """Accept only fixed staged Compose argv; no string or token passthrough."""
    selected = options or ComposeOptions()
    if isinstance(argv, str) or not isinstance(argv, list) or not argv:
        raise RunnerError('execution_boundary_violation', 'command argv must be a non-empty list')
    if not all(isinstance(token, str) and token for token in argv):
        raise RunnerError('execution_boundary_violation', 'command argv contains invalid tokens')
    matches = [
        action for action in PUBLIC_COMPOSE_ACTIONS if argv == compose_argv(action, selected)
    ]
    if len(matches) != 1:
        raise RunnerError(
            'execution_boundary_violation', 'compose argv is not one fixed staged action'
        )
    return {
        'ok': True,
        'action': matches[0],
        'project': selected.project,
        'files': list(REQUIRED_COMPOSE_FILES),
    }


EXECUTION_DIGEST_METHOD = 'raw-byte-sha256'
TERMINAL_ACCEPTANCE_SCHEMA_VERSION = 'phase6-terminal-artifacts-manifest-v1'


def host_side_execution_authority_digests() -> dict[str, str]:
    """Raw-byte SHA-256 map for fixed host execution authority paths only. Never runs Docker."""
    digests: dict[str, str] = {}
    for relative in HOST_EXECUTION_AUTHORITY_PATHS:
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise RunnerError(
                'execution_boundary_violation', 'execution authority path escapes repository'
            ) from exc
        if not path.is_file():
            raise RunnerError(
                'execution_attestation_missing',
                f'execution authority file missing: {relative}',
            )
        digests[relative] = sha256_raw_bytes(path.read_bytes())
    return digests


def compute_execution_map_sha256(digests: dict[str, str] | None = None) -> str:
    """Canonical SHA-256 over {'files': raw-byte digest map} for host execution authority."""
    files = digests if digests is not None else host_side_execution_authority_digests()
    if tuple(files.keys()) != HOST_EXECUTION_AUTHORITY_PATHS:
        # require exact key order/set when precomputed map is supplied
        if set(files.keys()) != set(HOST_EXECUTION_AUTHORITY_PATHS):
            raise RunnerError(
                'execution_attestation_invalid',
                'execution authority map keys must match fixed host paths',
            )
        ordered = {path: files[path] for path in HOST_EXECUTION_AUTHORITY_PATHS}
        return canonical_sha256({'files': ordered})
    return canonical_sha256({'files': files})


def attest_execution_authority(*, expected_execution_map_sha256: str) -> dict[str, Any]:
    """Host-side Gate 0 execution authority. Fail closed on missing override/base/config."""
    if SHA256_RE.fullmatch(expected_execution_map_sha256) is None:
        raise RunnerError(
            'execution_attestation_invalid',
            'expected execution map digest must be lowercase SHA-256',
        )
    digests = host_side_execution_authority_digests()
    computed = compute_execution_map_sha256(digests)
    if computed != expected_execution_map_sha256:
        raise RunnerError(
            'execution_attestation_mismatch',
            'reviewed execution authority map does not match',
        )
    return {
        'execution_map_sha256': computed,
        'execution_files': len(digests),
        'execution_digest_method': EXECUTION_DIGEST_METHOD,
    }


def attest_host_compose_argv(
    argv: list[str] | str, options: ComposeOptions | None = None
) -> dict[str, Any]:
    """External Compose argv accepted only via exact validator. Never launches Docker."""
    return validate_execution_command(argv, options)


def evaluate_embedding_readiness(
    embeddings: dict[str, Any],
    *,
    allow_unknown_embedding_provider: str | None = None,
) -> dict[str, Any]:
    """Capability embedding policy. Never rewrites readiness.

    Explicit waiver only for provider=openai + readiness=unknown when
    allow_unknown_embedding_provider == 'openai'. Other providers' unknown fail.
    error always fails. ready always passes.
    """
    if not isinstance(embeddings, dict):
        raise RunnerError('capability_preflight_failed', 'embeddings projection is invalid')
    provider = embeddings.get('provider')
    readiness = embeddings.get('ready')
    waiver_requested = allow_unknown_embedding_provider
    if waiver_requested is not None and waiver_requested != 'openai':
        raise RunnerError(
            'capability_preflight_failed',
            'allow_unknown_embedding_provider only accepts exact value openai',
        )
    waiver_applied = False
    if readiness == 'ready':
        status = 'pass'
    elif readiness == 'error':
        raise RunnerError('capability_preflight_failed', 'embedding readiness is error')
    elif readiness == 'unknown':
        if provider == 'openai' and waiver_requested == 'openai':
            status = 'waived'
            waiver_applied = True
        else:
            raise RunnerError(
                'capability_preflight_failed',
                'embedding readiness unknown without exact openai waiver',
            )
    else:
        raise RunnerError('capability_preflight_failed', 'embedding readiness is incomplete')
    return {
        'status': status,
        'provider': provider,
        'readiness': readiness,
        'waiver_applied': waiver_applied,
        'observed_provider': provider,
        'observed_readiness': readiness,
    }


async def _ledger_call(
    transport: Any,
    ledger: ToolLedger,
    stage: str,
    name: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = await transport.call(name, request)
        if not isinstance(result, dict):
            raise RunnerError('invalid_transport_result', f'{name} returned invalid result')
    except BaseException as exc:
        code = exc.code if isinstance(exc, RunnerError) else type(exc).__name__
        ledger.record(tool=name, stage=stage, success=False, error_code=code)
        raise
    ledger.record(tool=name, stage=stage, success=True)
    return result


def validate_live_operator_confirmation(
    manifest: dict[str, Any], *, group_id: str, control_group_id: str, batch_id: str
) -> None:
    supplied = (group_id, control_group_id, batch_id)
    expected = (
        manifest.get('group_id'),
        manifest.get('control_group_id'),
        manifest.get('batch_id'),
    )
    if supplied != expected:
        raise RunnerError(
            'operator_confirmation_mismatch', 'operator confirmation does not match manifest'
        )
    run_id = manifest.get('run_id')
    expected_group = f'oracle-catalog-v2-canary-{run_id}'
    if (
        group_id != expected_group
        or control_group_id != f'{expected_group}-empty-control'
        or batch_id != f'accept-tab-catalog-v2-canary-{run_id}'
    ):
        raise RunnerError('live_identity_mismatch', 'live identity naming relationship is invalid')
    if BLOCKED_RUN_ID in '|'.join(str(value) for value in (*supplied, run_id)):
        raise RunnerError('blocked_run_immutable', 'blocked run identity must never be reused')
    _reject_live_group(group_id)
    _reject_live_group(control_group_id)
    if group_id == control_group_id:
        raise RunnerError('control_group_mismatch', 'control group must differ from canary group')


def preflight_live_manifest(
    manifest_path: Path,
    *,
    confirm_run_id: str,
    confirm_group_id: str,
    confirm_control_group_id: str,
    confirm_batch_id: str,
    allow_unknown_embedding_provider: str | None,
) -> dict[str, Any]:
    """Validate immutable live authority before transport open or local writes."""
    manifest = strict_json_load(manifest_path)
    if not isinstance(manifest, dict):
        raise RunnerError('invalid_live_manifest', 'live manifest must be an object')
    if set(manifest) != LIVE_MANIFEST_FIELDS:
        raise RunnerError('live_manifest_mismatch', 'live manifest field set is invalid')
    if (
        manifest.get('source_digest_origin') != SOURCE_DIGEST_ORIGIN_HOST
        or manifest.get('execution_surface') != EXECUTION_SURFACE_COMPOSE
        or manifest.get('allow_unknown_embedding_provider') not in (None, WAIVER_OPENAI)
    ):
        raise RunnerError('live_manifest_mismatch', 'live manifest semantics are invalid')
    if confirm_run_id != manifest.get('run_id'):
        raise RunnerError(
            'operator_confirmation_mismatch', 'run_id confirmation does not match manifest'
        )
    if manifest['allow_unknown_embedding_provider'] != allow_unknown_embedding_provider:
        raise RunnerError(
            'operator_confirmation_mismatch',
            'embedding waiver does not match immutable manifest',
        )
    validate_live_operator_confirmation(
        manifest,
        group_id=confirm_group_id,
        control_group_id=confirm_control_group_id,
        batch_id=confirm_batch_id,
    )
    return manifest


def _protected_roots(payload_path: Path, manifest_path: Path) -> tuple[Path, ...]:
    roots = [
        HARDENED_ARTIFACT_DIR.resolve(),
        (ROOT / 'catalog' / 'canary-v2-requests').resolve(),
        payload_path.resolve().parent,
        manifest_path.resolve().parent,
    ]
    quick = ROOT / '.planning' / 'quick'
    if quick.exists():
        roots.extend(
            path.resolve()
            for path in quick.rglob('*')
            if path.is_dir() and path.name in {BLOCKED_RUN_ID, '20260719T211404Z-0df5d06d'}
        )
    return tuple(dict.fromkeys(roots))


def validate_result_directory(path: Path, payload_path: Path, manifest_path: Path) -> Path:
    resolved = path.resolve()
    for root in _protected_roots(payload_path, manifest_path):
        if resolved == root or root in resolved.parents:
            raise RunnerError('protected_result_directory', 'result directory is protected')
    if path.exists() and path.is_symlink():
        raise RunnerError('protected_result_directory', 'result directory symlink is forbidden')
    return resolved


def validate_live_artifact(
    payload_path: Path, manifest_path: Path
) -> tuple[bytes, dict[str, Any], dict[str, Any], UpsertCatalogBatchRequest, str, str]:
    payload_resolved = payload_path.resolve()
    manifest_resolved = manifest_path.resolve()
    if payload_resolved.parent != manifest_resolved.parent:
        raise RunnerError(
            'live_directory_mismatch', 'payload and manifest must share one directory'
        )
    for path in (payload_resolved, manifest_resolved):
        if BLOCKED_RUN_ID in path.parts:
            raise RunnerError('blocked_run_immutable', 'blocked run artifact is immutable')
        for root in (
            HARDENED_ARTIFACT_DIR.resolve(),
            (ROOT / 'catalog' / 'canary-v2-requests').resolve(),
        ):
            if path == root or root in path.parents:
                raise RunnerError(
                    'golden_not_live', 'golden or historical artifact is not live authority'
                )
    if payload_path.name != LIVE_PAYLOAD_NAME or manifest_path.name != LIVE_MANIFEST_NAME:
        raise RunnerError('live_filename_mismatch', 'live artifact filenames are invalid')
    directory_files = {item.name for item in payload_resolved.parent.iterdir() if item.is_file()}
    if directory_files != {LIVE_PAYLOAD_NAME, LIVE_MANIFEST_NAME}:
        raise RunnerError('live_file_set_mismatch', 'live artifact directory has unexpected files')
    payload_bytes = payload_resolved.read_bytes()
    manifest_bytes = manifest_resolved.read_bytes()
    payload = strict_json_loads(payload_bytes)
    manifest = strict_json_loads(manifest_bytes)
    if not isinstance(payload, dict) or not isinstance(manifest, dict):
        raise RunnerError('invalid_live_artifact', 'live artifact roots must be objects')
    if set(manifest) != LIVE_MANIFEST_FIELDS:
        raise RunnerError('live_manifest_mismatch', 'live manifest field set is invalid')
    if (
        canonical_artifact_bytes(payload) != payload_bytes
        or canonical_artifact_bytes(manifest) != manifest_bytes
    ):
        raise RunnerError('non_canonical_artifact', 'live artifact bytes must be canonical')
    fixture_path = (ROOT / str(manifest['fixture'])).resolve()
    approved_fixture = (ROOT / 'mcp_server/tests/fixtures/accept_tab_sanitized.json').resolve()
    fixture_raw = approved_fixture.read_bytes()
    authority_mode = 'git' if (ROOT / '.git').exists() else 'archive'
    try:
        committed_fixture_raw = authority_bytes(
            ROOT,
            'mcp_server/tests/fixtures/accept_tab_sanitized.json',
            mode=authority_mode,
        )
        committed_builder_raw = authority_bytes(
            ROOT,
            'scripts/build_catalog_canary_requests.py',
            mode=authority_mode,
        )
    except ValueError as exc:
        raise RunnerError(
            'live_manifest_mismatch', 'bound source authority is unavailable'
        ) from exc
    if (
        fixture_path != approved_fixture
        or manifest['profile'] != 'live-canary'
        or manifest['source_digest_origin'] != SOURCE_DIGEST_ORIGIN_HOST
        or manifest['execution_surface'] != EXECUTION_SURFACE_COMPOSE
        or manifest['allow_unknown_embedding_provider'] not in (None, WAIVER_OPENAI)
        or manifest['artifact_schema_version'] != LIVE_ARTIFACT_SCHEMA_VERSION
        or manifest['payload'] != LIVE_PAYLOAD_NAME
        or manifest['artifact_sha256'] != sha256_bytes(payload_bytes)
        or manifest['builder'] != 'scripts/build_catalog_canary_requests.py'
        or manifest['builder_sha256'] != sha256_canonical_text_bytes(committed_builder_raw)
        or manifest['fixture_sha256'] != APPROVED_FIXTURE_RAW_SHA256
        or manifest['fixture_lf_sha256'] != APPROVED_FIXTURE_LF_SHA256
        or sha256_raw_bytes(committed_fixture_raw) != APPROVED_FIXTURE_RAW_SHA256
        or sha256_canonical_text_bytes(committed_fixture_raw) != APPROVED_FIXTURE_LF_SHA256
        or sha256_canonical_text_bytes(fixture_raw) != APPROVED_FIXTURE_LF_SHA256
        or manifest['canary_executed'] is not False
    ):
        raise RunnerError('live_manifest_mismatch', 'live manifest authority binding is invalid')
    _validate_hardened_raw_field_sets(payload)
    try:
        request = UpsertCatalogBatchRequest.model_validate(
            {**payload, 'dry_run': True}, strict=True
        )
    except ValidationError as exc:
        raise RunnerError('request_validation_failed', 'live payload fails validation') from exc
    _validate_content_hashes(request)
    request_sha = CatalogService.batch_request_sha256(request)
    provenance = request.provenance
    assert provenance is not None
    counts = _expected_domain_counts(request)
    if (
        manifest['group_id'] != request.group_id
        or manifest['batch_id'] != request.batch_id
        or manifest['identity_schema_version'] != request.identity_schema_version
        or manifest['system_key'] != request.system_key
        or manifest['catalog_sha256'] != request.catalog_sha256
        or manifest['request_sha256'] != request_sha
        or manifest['counts'] != counts
    ):
        raise RunnerError('live_manifest_mismatch', 'live payload and manifest differ')
    _reject_live_group(request.group_id)
    return payload_bytes, payload, manifest, request, sha256_bytes(payload_bytes), request_sha


def build_live_dry_run_request(
    payload: dict[str, Any], *, dry_run: object = True
) -> dict[str, Any]:
    if type(dry_run) is not bool or dry_run is not True:
        raise RunnerError('dry_run_required', 'dry_run must be explicit boolean true')
    if 'dry_run' in payload:
        raise RunnerError('dry_run_field_violation', 'domain payload must not include dry_run')
    body = copy.deepcopy(payload)
    body['dry_run'] = True
    try:
        UpsertCatalogBatchRequest.model_validate(body, strict=True)
    except ValidationError as exc:
        raise RunnerError('request_validation_failed', 'dry_run request fails validation') from exc
    return body


def _assert_absent(
    response: dict[str, Any],
    *,
    group_id: str,
    batch_id: str,
    manifest: bool = False,
    expected_batch_uuid: str | None = None,
    expected_limit: int = 100,
) -> str | None:
    if (
        response.get('found') is not False
        or response.get('group_id') != group_id
        or response.get('batch_id') != batch_id
    ):
        raise RunnerError('zero_write_not_proven', 'catalog read did not prove exact absence')
    if manifest:
        if (
            response.get('error_code') != 'manifest_mismatch'
            or response.get('error_message') != 'manifest root not found'
            or response.get('offset') != 0
            or response.get('limit') != expected_limit
            or any(response.get(key) for key in ('entities', 'edges', 'sources', 'evidence_links'))
            or any(
                response.get(key) != 0
                for key in ('entity_count', 'edge_count', 'source_count', 'evidence_link_count')
            )
            or any(
                response.get(key) is not None
                for key in (
                    'request_sha256',
                    'catalog_sha256',
                    'artifact_sha256',
                    'manifest_sha256',
                    'identity_schema_version',
                    'canonicalization_version',
                    'catalog_schema_version',
                )
            )
        ):
            raise RunnerError('zero_write_not_proven', 'manifest absence shape is ambiguous')
        return None
    batch_uuid = response.get('batch_uuid')
    try:
        uuid.UUID(str(batch_uuid))
    except ValueError as exc:
        raise RunnerError('zero_write_not_proven', 'status absence batch UUID is invalid') from exc
    if (
        (expected_batch_uuid is not None and batch_uuid != expected_batch_uuid)
        or response.get('error_code') is not None
        or response.get('status') != 'failed'
        or response.get('error_summary') != 'batch status not found'
        or any(response.get(key) != 0 for key in ('entity_count', 'edge_count', 'provenance_count'))
        or any(
            response.get(key) is not None
            for key in (
                'request_sha256',
                'catalog_sha256',
                'created_at',
                'updated_at',
                'committed_at',
            )
        )
    ):
        raise RunnerError('zero_write_not_proven', 'status absence shape is ambiguous')
    return str(batch_uuid)


def _validate_live_dry_run_response(
    raw: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    request_sha: str,
    *,
    expected_batch_uuid: str,
) -> dict[str, Any]:
    try:
        response = CatalogBatchWriteResponse.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise RunnerError('invalid_dry_run_response', 'dry-run response is invalid') from exc
    provenance = request.provenance
    assert provenance is not None
    expected_results: list[tuple[int, str, str, str]] = []
    for index, item in enumerate(request.entities):
        expected_results.append(
            (index, item.entity_type, item.graph_key, item.content_sha256 or '')
        )
    edge_offset = len(request.entities)
    for index, item in enumerate(request.edges):
        expected_results.append(
            (edge_offset + index, item.edge_type, item.edge_key, item.content_sha256 or '')
        )
    source_offset = edge_offset + len(request.edges)
    for index, item in enumerate(provenance.sources):
        expected_results.append(
            (source_offset + index, '', item.source_key, item.content_sha256 or '')
        )
    if len(response.results) != len(expected_results):
        raise RunnerError('dry_run_binding_mismatch', 'dry-run per-item result count is invalid')
    seen: set[str] = set()
    for result, (index, item_type, key, digest) in zip(
        response.results, expected_results, strict=True
    ):
        identity_key = result.graph_key or result.edge_key or ''
        if (
            result.index != index
            or result.status != 'created'
            or result.uuid is None
            or result.content_sha256 != digest
            or identity_key != key
            or (result.entity_type or result.edge_type or '') != item_type
            or result.error_code is not None
            or result.error_message is not None
        ):
            raise RunnerError('dry_run_binding_mismatch', 'dry-run per-item binding is invalid')
        try:
            uuid.UUID(result.uuid)
        except ValueError as exc:
            raise RunnerError('dry_run_binding_mismatch', 'dry-run item UUID is invalid') from exc
        if result.uuid in seen:
            raise RunnerError('dry_run_binding_mismatch', 'dry-run item UUID is reused')
        seen.add(result.uuid)
    outcome = {
        'created': response.entity_created + response.edge_created + response.provenance_created,
        'updated': response.entity_updated + response.edge_updated + response.provenance_updated,
        'unchanged': response.entity_unchanged
        + response.edge_unchanged
        + response.provenance_unchanged,
    }
    expected_created = len(request.entities) + len(request.edges) + len(provenance.sources)
    if (
        response.group_id != request.group_id
        or response.batch_id != request.batch_id
        or response.batch_uuid != expected_batch_uuid
        or response.dry_run is not True
        or response.atomic is not True
        or response.status != 'validating'
        or response.identity_schema_version != request.identity_schema_version
        or response.canonicalization_version != CANONICALIZATION_VERSION
        or response.request_sha256 != request_sha
        or response.catalog_sha256 != request.catalog_sha256
        or response.error_code is not None
        or response.error_message is not None
        or response.failed != 0
        or response.rolled_back != 0
        or outcome != {'created': expected_created, 'updated': 0, 'unchanged': 0}
    ):
        raise RunnerError('dry_run_binding_mismatch', 'dry-run receipt binding is invalid')
    return {
        'batch_uuid': response.batch_uuid,
        'outcome': outcome,
        'counts': _expected_domain_counts(request),
    }


def _validate_live_prepare_overlap(
    raw: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    request_sha: str,
    dry_run: dict[str, Any],
) -> tuple[PrepareCatalogBatchResponse, str]:
    prepared, token = _validate_prepare_response(raw, request, request_sha)
    outcome = {
        'created': prepared.projected_created,
        'updated': prepared.projected_updated,
        'unchanged': prepared.projected_unchanged,
    }
    if outcome != dry_run['outcome']:
        raise RunnerError('prepare_binding_mismatch', 'prepare C/U/U differs from dry-run')
    return prepared, token


def _validate_committed_status(
    raw: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    request_sha: str,
    *,
    expected_batch_uuid: str,
) -> CatalogIngestStatusResponse:
    _validate_status_response(raw, request, request_sha)
    response = CatalogIngestStatusResponse.model_validate(raw, strict=True)
    if response.batch_uuid != expected_batch_uuid:
        raise RunnerError('batch_uuid_mismatch', 'committed status batch UUID differs')
    return response


def _manifest_page_size(capabilities: CatalogCapabilitiesResponse) -> int:
    configured = (
        capabilities.limits.get('configured') if isinstance(capabilities.limits, dict) else None
    )
    hard = capabilities.limits.get('hard') if isinstance(capabilities.limits, dict) else None
    values = [500]
    for item in (configured, hard):
        if isinstance(item, dict) and type(item.get('max_page_size')) is int:
            values.append(item['max_page_size'])
    size = min(values)
    if size < 1:
        raise RunnerError('capability_preflight_failed', 'advertised page size is invalid')
    return size


async def _fetch_full_manifest(
    call: Any,
    request: UpsertCatalogBatchRequest,
    request_sha: str,
    *,
    page_size: int,
    expected_artifact_sha256: str,
    expected_manifest_sha256: str,
) -> tuple[
    GetCatalogBatchManifestResponse,
    dict[tuple[str, str], str],
    dict[tuple[str, str], str],
    dict[str, str],
    dict[str, str],
]:
    provenance = request.provenance
    assert provenance is not None
    expected_counts = _expected_domain_counts(request)
    aggregate: dict[str, list[Any]] = {
        key: [] for key in ('entities', 'edges', 'sources', 'evidence_links')
    }
    stable: dict[str, Any] | None = None
    maximum = max(expected_counts.values())
    for offset in range(0, maximum, page_size):
        body = {
            'group_id': request.group_id,
            'batch_id': request.batch_id,
            'offset': offset,
            'limit': page_size,
        }
        GetCatalogBatchManifestRequest.model_validate(body, strict=True)
        raw = await call('get_catalog_batch_manifest', body)
        try:
            page = GetCatalogBatchManifestResponse.model_validate(raw, strict=True)
        except ValidationError as exc:
            raise RunnerError('invalid_manifest_response', 'manifest page is invalid') from exc
        page_stable = {
            key: getattr(page, key)
            for key in (
                'group_id',
                'batch_id',
                'found',
                'request_sha256',
                'catalog_sha256',
                'artifact_sha256',
                'manifest_sha256',
                'identity_schema_version',
                'canonicalization_version',
                'catalog_schema_version',
                'entity_count',
                'edge_count',
                'source_count',
                'evidence_link_count',
                'error_code',
                'error_message',
            )
        }
        if stable is None:
            stable = page_stable
        if page_stable != stable or page.offset != offset or page.limit != page_size:
            raise RunnerError('manifest_failed', 'manifest pagination binding changed')
        for category, count_key in (
            ('entities', 'entities'),
            ('edges', 'edges'),
            ('sources', 'sources'),
            ('evidence_links', 'evidence_links'),
        ):
            items = getattr(page, category)
            expected_len = min(page_size, max(expected_counts[count_key] - offset, 0))
            if len(items) != expected_len:
                raise RunnerError('manifest_failed', 'manifest page is premature or overfull')
            aggregate[category].extend(items)
    if stable is None:
        raise RunnerError('manifest_failed', 'manifest has no page')
    if (
        stable['found'] is not True
        or stable['error_code'] is not None
        or stable['error_message'] is not None
        or stable['group_id'] != request.group_id
        or stable['batch_id'] != request.batch_id
        or stable['request_sha256'] != request_sha
        or stable['catalog_sha256'] != request.catalog_sha256
        or stable['artifact_sha256'] != expected_artifact_sha256
        or stable['manifest_sha256'] != expected_manifest_sha256
        or stable['identity_schema_version'] != request.identity_schema_version
        or stable['canonicalization_version'] != CANONICALIZATION_VERSION
        or stable['catalog_schema_version'] != CATALOG_SCHEMA_VERSION
        or [
            stable['entity_count'],
            stable['edge_count'],
            stable['source_count'],
            stable['evidence_link_count'],
        ]
        != list(expected_counts.values())
    ):
        raise RunnerError('manifest_failed', 'manifest stable binding is invalid')
    first = GetCatalogBatchManifestResponse(
        **stable,
        offset=0,
        limit=page_size,
        entities=aggregate['entities'],
        edges=aggregate['edges'],
        sources=aggregate['sources'],
        evidence_links=aggregate['evidence_links'],
    )
    entity_map, edge_map, evidence_map = _validate_manifest_inventory(first, request)
    source_map = {item.source_key: item.uuid for item in first.sources}
    all_uuid = [item.uuid for category in aggregate.values() for item in category]
    if len(all_uuid) != len(set(all_uuid)):
        raise RunnerError('manifest_failed', 'manifest UUID is reused across categories')
    for item in [*first.entities, *first.edges, *first.sources]:
        if item.projected_status != 'created':
            raise RunnerError('manifest_failed', 'fresh manifest member is not projected created')
    membership = {
        key: [item.model_dump(mode='json') for item in value] for key, value in aggregate.items()
    }
    body = catalog_manifest.build_manifest_body_from_membership(
        group_id=request.group_id,
        batch_id=request.batch_id,
        request_sha256=request_sha,
        catalog_sha256=request.catalog_sha256,
        membership=membership,
        artifact_sha256=expected_artifact_sha256,
        identity_schema_version=request.identity_schema_version,
        canonicalization_version=CANONICALIZATION_VERSION,
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
    )
    calculated = catalog_manifest.manifest_sha256(catalog_manifest.serialize_manifest_body(body))
    if calculated != expected_manifest_sha256:
        raise RunnerError('manifest_failed', 'reconstructed manifest SHA-256 differs')
    return first, entity_map, edge_map, source_map, evidence_map


def _validate_resolved_entities(
    raw: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    manifest_entities: dict[tuple[str, str], str],
) -> dict[tuple[str, str], str]:
    resolved = _validate_resolve_response(raw, request)
    response = ResolveTypedEntitiesResponse.model_validate(raw, strict=True)
    if resolved != manifest_entities or [item.index for item in response.results] != list(
        range(len(request.entities))
    ):
        raise RunnerError('resolve_failed', 'typed entity order or manifest UUID differs')
    labels_seen: set[str] = set()
    uuids: list[str] = []
    for result, item in zip(response.results, request.entities, strict=True):
        if (
            result.labels is None
            or result.labels.count(item.entity_type) != 1
            or 'Entity' not in result.labels
        ):
            raise RunnerError('resolve_failed', 'typed entity labels are invalid')
        uuids.append(result.uuid or '')
        labels_seen.add(item.entity_type)
    if len(uuids) != len(set(uuids)):
        raise RunnerError('resolve_failed', 'typed entity UUID is duplicated')
    return resolved


def _validate_resolved_edges(
    raw: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    entity_uuids: dict[tuple[str, str], str],
    manifest_edges: dict[tuple[str, str], str],
) -> None:
    try:
        response = ResolveTypedEdgesResponse.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_resolve_edges_response', 'typed edge response is invalid'
        ) from exc
    if response.group_id != request.group_id or len(response.results) != len(request.edges):
        raise RunnerError('resolve_edges_failed', 'typed edge response count or group mismatch')
    for result, edge in zip(response.results, request.edges, strict=True):
        try:
            uuid.UUID(result.uuid or '')
            uuid.UUID(result.source_uuid or '')
            uuid.UUID(result.target_uuid or '')
        except ValueError as exc:
            raise RunnerError('resolve_edges_failed', 'typed edge UUID is invalid') from exc
        if (
            result.edge_type != edge.edge_type
            or result.edge_key != edge.edge_key
            or result.status != 'found'
            or result.found is not True
            or result.verified_type != edge.edge_type
            or result.source_uuid != entity_uuids[(edge.source_entity_type, edge.source_graph_key)]
            or result.target_uuid != entity_uuids[(edge.target_entity_type, edge.target_graph_key)]
            or result.source_graph_key != edge.source_graph_key
            or result.target_graph_key != edge.target_graph_key
            or result.source_entity_type != edge.source_entity_type
            or result.target_entity_type != edge.target_entity_type
            or result.content_sha256 != edge.content_sha256
            or result.has_fact_embedding is not True
            or result.duplicate_uuids
            or result.anomalies
            or result.error_code is not None
            or result.error_message is not None
        ):
            raise RunnerError('resolve_edges_failed', 'typed edge response binding failed')
    if [item.index for item in response.results] != list(range(len(request.edges))):
        raise RunnerError('resolve_edges_failed', 'typed edge order is invalid')
    uuids = []
    for result, edge in zip(response.results, request.edges, strict=True):
        if result.uuid != manifest_edges[(edge.edge_type, edge.edge_key)]:
            raise RunnerError('resolve_edges_failed', 'typed edge UUID differs from manifest')
        uuids.append(result.uuid or '')
    if len(uuids) != len(set(uuids)):
        raise RunnerError('resolve_edges_failed', 'typed edge UUID is duplicated')


async def _verify_all_evidence(
    call: Any,
    request: UpsertCatalogBatchRequest,
    *,
    page_size: int,
    entity_uuids: dict[tuple[str, str], str],
    edge_uuids: dict[tuple[str, str], str],
    source_uuids: dict[str, str],
    manifest_evidence: dict[str, str],
) -> int:
    provenance = request.provenance
    assert provenance is not None
    found_all: set[str] = set()
    targets = [
        (
            'entity',
            item.entity_type,
            item.graph_key,
            entity_uuids[(item.entity_type, item.graph_key)],
        )
        for item in request.entities
    ] + [
        ('edge', item.edge_type, item.edge_key, edge_uuids[(item.edge_type, item.edge_key)])
        for item in request.edges
    ]
    expected_by_link = {evidence_link_key(item): item for item in provenance.evidence_links}
    for kind, item_type, key, target_uuid in targets:
        expected_keys = {
            evidence_link_key(item)
            for item in provenance.evidence_links
            if (
                kind == 'entity'
                and item.entity_target is not None
                and item.entity_target.entity_type == item_type
                and item.entity_target.graph_key == key
            )
            or (
                kind == 'edge'
                and item.edge_target is not None
                and item.edge_target.edge_type == item_type
                and item.edge_target.edge_key == key
            )
        }
        target_found: set[str] = set()
        total: int | None = None
        offset = 0
        while total is None or offset < total:
            body = {
                'group_id': request.group_id,
                'identity_schema_version': request.identity_schema_version,
                'system_key': request.system_key,
                'entity_target': {'entity_type': item_type, 'graph_key': key}
                if kind == 'entity'
                else None,
                'edge_target': {'edge_type': item_type, 'edge_key': key}
                if kind == 'edge'
                else None,
                'offset': offset,
                'limit': page_size,
                'include_excerpts': False,
            }
            GetCatalogEvidenceRequest.model_validate(body, strict=True)
            raw = await call('get_catalog_evidence', body)
            response = GetCatalogEvidenceResponse.model_validate(raw, strict=True)
            if total is None:
                total = response.total
            assert total is not None
            if (
                response.group_id != request.group_id
                or response.target_kind != kind
                or response.target_uuid != target_uuid
                or response.found_target is not True
                or response.offset != offset
                or response.limit != page_size
                or response.total != total
                or response.error_code is not None
                or response.error_message is not None
                or len(response.links) != min(page_size, max(total - offset, 0))
            ):
                raise RunnerError('evidence_failed', 'evidence page binding is invalid')
            for link in response.links:
                expected = expected_by_link.get(link.link_key)
                if (
                    expected is None
                    or link.uuid != manifest_evidence.get(link.link_key)
                    or link.content_sha256 != canonical_sha256(evidence_canonical_payload(expected))
                    or link.source_uuid != source_uuids.get(expected.source_key)
                    or link.target_kind != kind
                    or link.target_uuid != target_uuid
                    or link.evidence_kind != expected.evidence_kind
                    or link.extractor_name != expected.extractor_name
                    or link.extractor_version != expected.extractor_version
                    or link.rule_id != expected.rule_id
                    or link.confidence != expected.confidence
                    or link.excerpt is not None
                    or link.link_key in target_found
                ):
                    raise RunnerError('evidence_failed', 'evidence link binding is invalid')
                target_found.add(link.link_key)
            offset += page_size
        if target_found != expected_keys:
            raise RunnerError('evidence_failed', 'evidence target membership is incomplete')
        if found_all & target_found:
            raise RunnerError('evidence_failed', 'evidence link appears for multiple targets')
        found_all |= target_found
    if found_all != set(manifest_evidence):
        raise RunnerError('evidence_failed', 'full evidence inventory differs from manifest')
    return len(found_all)


def _validate_node_search_strict(
    raw: dict[str, Any],
    *,
    group_id: str,
    expected_uuid: str,
    entity_type: str,
    graph_key: str,
) -> None:
    nodes = raw.get('nodes')
    if not isinstance(nodes, list) or any(
        not isinstance(row, dict) or row.get('group_id') != group_id for row in nodes
    ):
        raise RunnerError('node_search_failed', 'node search returned foreign or invalid row')
    uuids = [row.get('uuid') for row in nodes]
    if len(uuids) != len(set(uuids)) or uuids.count(expected_uuid) != 1:
        raise RunnerError('node_search_failed', 'node search identity is absent or duplicated')
    typed_identity = [
        row
        for row in nodes
        if row.get('name') == graph_key and entity_type in (row.get('labels') or [])
    ]
    if len(typed_identity) != 1 or typed_identity[0].get('uuid') != expected_uuid:
        raise RunnerError('node_search_failed', 'node search returned a typed identity alias')


def _fact_nested_edge_key(fact: dict[str, Any]) -> Any:
    """Canonical nested identity only. Top-level edge_key is non-authoritative."""
    attributes = fact.get('attributes')
    if not isinstance(attributes, dict):
        raise RunnerError('fact_search_failed', 'fact search attributes must be a dict')
    nested = attributes.get('edge_key')
    top = fact.get('edge_key')
    if top is not None and nested is not None and top != nested:
        raise RunnerError(
            'fact_search_failed', 'fact search top-level edge_key conflicts with nested identity'
        )
    return nested


def _validate_fact_search_strict(
    raw: dict[str, Any],
    *,
    group_id: str,
    expected_uuid: str,
    edge_type: str,
    edge_key: str,
    source_node_uuid: str | None = None,
    target_node_uuid: str | None = None,
) -> None:
    """Gate 9: exact nested attributes.edge_key + UUID/group/type/endpoints once.

    Unrelated same-group extras are allowed. Foreign group, duplicate expected UUID,
    alias/ambiguous identities, missing/non-dict attributes, and top/nested conflicts fail.
    Top-level-only edge_key does not satisfy the canonical nested contract.
    """
    facts = raw.get('facts')
    if isinstance(facts, list) and facts and all(isinstance(row, str) for row in facts):
        raise RunnerError('fact_search_failed', 'fact search lacks structured identity rows')
    if not isinstance(facts, list):
        raise RunnerError('fact_search_failed', 'fact search returned foreign or invalid row')
    for row in facts:
        if not isinstance(row, dict):
            raise RunnerError('fact_search_failed', 'fact search returned foreign or invalid row')
        if row.get('group_id') != group_id:
            raise RunnerError('fact_search_failed', 'fact search returned foreign or invalid row')
        # Force attributes contract on every row so missing/non-dict fail closed.
        _fact_nested_edge_key(row)
    uuids = [row.get('uuid') for row in facts]
    if len(uuids) != len(set(uuids)) or uuids.count(expected_uuid) != 1:
        raise RunnerError('fact_search_failed', 'fact search identity is absent or duplicated')
    matches = []
    for row in facts:
        nested_key = _fact_nested_edge_key(row)
        if nested_key != edge_key or row.get('name') != edge_type:
            continue
        if source_node_uuid is not None and row.get('source_node_uuid') != source_node_uuid:
            continue
        if target_node_uuid is not None and row.get('target_node_uuid') != target_node_uuid:
            continue
        matches.append(row)
    if len(matches) != 1 or matches[0].get('uuid') != expected_uuid:
        raise RunnerError('fact_search_failed', 'fact search returned a typed identity alias')


def _terminal_report(
    *,
    manifest: dict[str, Any],
    classification: str,
    machine: LiveStageMachine,
    gates: dict[str, str],
    attestation: dict[str, Any] | None,
    capability_sha256: str | None,
    artifact_sha256: str | None,
    request_sha256: str | None,
    manifest_sha256: str | None,
    batch_uuid: str | None,
    replay: str,
    error_code: str | None,
    error_type: str | None,
    flags: dict[str, Any],
    plan_token: str | None,
    ledger_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ledger_meta = validate_tool_ledger(list(ledger_entries or []))
    embedding_policy = flags.get('embedding_policy') or {}
    report = {
        'schema_version': REPORT_SCHEMA_VERSION,
        'classification': classification,
        'run_id': manifest.get('run_id'),
        'group_id': manifest.get('group_id'),
        'control_group_id': manifest.get('control_group_id'),
        'batch_id': manifest.get('batch_id'),
        'source_head': (attestation or {}).get('source_head'),
        'source_map_sha256': (attestation or {}).get('source_map_sha256'),
        'runner_sha256': (attestation or {}).get('runner_sha256'),
        'execution_map_sha256': (attestation or {}).get('execution_map_sha256'),
        'execution_files': (attestation or {}).get('execution_files'),
        'execution_digest_method': (attestation or {}).get('execution_digest_method'),
        'runtime_capability_sha256': capability_sha256,
        'namespace_fingerprint': flags.get('namespace_fingerprint'),
        'artifact_sha256': artifact_sha256,
        'catalog_sha256': manifest.get('catalog_sha256'),
        'request_sha256': request_sha256,
        'manifest_sha256': manifest_sha256,
        'batch_uuid': batch_uuid,
        'tool_count': ledger_meta['tool_count'],
        'tool_call_count': ledger_meta['tool_call_count'],
        'final_ordinal': ledger_meta['final_ordinal'],
        'stage': machine.stage.name,
        'stage_ledger': machine.ledger,
        'gates': gates,
        'dry_run_zero_write_proven': flags.get('dry_run_zero_write_proven', False),
        'prepare_functional_embedding_proof': flags.get(
            'prepare_functional_embedding_proof', False
        ),
        'commit_confirmed': flags.get('commit_confirmed', False),
        'manifest_verified': flags.get('manifest_verified', False),
        'entity_resolution_verified': flags.get('entity_resolution_verified', False),
        'edge_resolution_verified': flags.get('edge_resolution_verified', False),
        'evidence_verified': flags.get('evidence_verified', False),
        'search_verified': flags.get('search_verified', False),
        'control_isolation_verified': flags.get('control_isolation_verified', False),
        'embedding_provider': embedding_policy.get('observed_provider'),
        'embedding_readiness': embedding_policy.get('observed_readiness'),
        'waiver_applied': bool(embedding_policy.get('waiver_applied', False)),
        'replay': replay,
        'protected_groups_queried': [],
        'prohibited_tools_called': [],
        'clear_graph_called': False,
        'cleanup_performed': False,
        'secrets_persisted': False,
        'error_code': error_code,
        'error_type': error_type,
        'notes': 'sanitized durable report; prepared-plan process-loss resume is unsupported',
        'canary_executed': flags.get('commit_started', False),
    }
    counts = flags.get('counts')
    if counts is not None:
        expected_count_keys = {'entities', 'edges', 'sources', 'evidence_links'}
        if (
            not isinstance(counts, dict)
            or set(counts) != expected_count_keys
            or any(type(value) is not int or value < 0 for value in counts.values())
        ):
            raise RunnerError('report_counts_invalid', 'terminal report counts are invalid')
        report['counts'] = dict(counts)
    validate_report_ledger_metadata(report, ledger_meta)
    text = json.dumps(report, sort_keys=True)
    if (plan_token and plan_token in text) or 'token_digest' in text:
        raise RunnerError('token_persistence', 'secret token material reached report')
    return report


def _persist_terminal_artifacts(
    result_dir: Path,
    *,
    report: dict[str, Any],
    ledger_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate ledger/report, write tool-ledger then final-report, then acceptance manifest last.

    Failure before the final acceptance manifest leaves terminal artifacts unaccepted.
    """
    ledger_meta = validate_tool_ledger(list(ledger_entries))
    validate_report_ledger_metadata(report, ledger_meta)
    ledger_path = result_dir / 'tool-ledger.json'
    report_path = result_dir / 'final-report.json'
    accept_path = result_dir / 'terminal-artifacts-manifest.json'
    ledger_doc = {'schema_version': 1, 'entries': list(ledger_entries)}
    atomic_write_json(ledger_path, ledger_doc)
    atomic_write_json(report_path, report)
    on_disk_ledger_sha = sha256_bytes(ledger_path.read_bytes())
    on_disk_report_sha = sha256_bytes(report_path.read_bytes())
    acceptance = {
        'schema_version': TERMINAL_ACCEPTANCE_SCHEMA_VERSION,
        'tool_ledger_sha256': on_disk_ledger_sha,
        'final_report_sha256': on_disk_report_sha,
        'tool_call_count': ledger_meta['tool_call_count'],
        'final_ordinal': ledger_meta['final_ordinal'],
        'tool_count': ledger_meta['tool_count'],
    }
    atomic_write_json(accept_path, acceptance)
    return acceptance


def _confirmed_manifest_hint(
    *,
    run_id: str,
    group_id: str,
    control_group_id: str,
    batch_id: str,
) -> dict[str, Any]:
    return {
        'run_id': run_id,
        'group_id': group_id,
        'control_group_id': control_group_id,
        'batch_id': batch_id,
    }


def _persist_pretransport_terminal_failure(
    result_dir: Path,
    *,
    manifest_hint: dict[str, Any],
    exc: BaseException,
    attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a sanitized zero-transport post-ID terminal without fabricated counts."""
    result_dir.mkdir(parents=True, exist_ok=False)
    machine = LiveStageMachine()
    gates = {str(index): 'blocked' for index in range(11)}
    gates['0'] = 'fail'
    report = _terminal_report(
        manifest=manifest_hint,
        classification='FAILED_BEFORE_COMMIT',
        machine=machine,
        gates=gates,
        attestation=attestation,
        capability_sha256=None,
        artifact_sha256=None,
        request_sha256=None,
        manifest_sha256=None,
        batch_uuid=None,
        replay='skipped',
        error_code=exc.code if isinstance(exc, RunnerError) else 'internal_runner_error',
        error_type=type(exc).__name__,
        flags={},
        plan_token=None,
        ledger_entries=[],
    )
    _persist_terminal_artifacts(result_dir, report=report, ledger_entries=[])
    return report


async def run_live_canary(
    transport: Any,
    payload_path: Path,
    manifest_path: Path,
    *,
    confirm_run_id: str,
    confirm_group_id: str,
    confirm_control_group_id: str,
    confirm_batch_id: str,
    source_head: str,
    source_map_sha256: str,
    runner_sha256: str,
    execution_map_sha256: str,
    authority_mode: str = 'git',
    image_fingerprint: str | None = None,
    config_fingerprint: str | None = None,
    output_dir: Path | None = None,
    source_attestor: Any | None = None,
    execution_attestor: Any | None = None,
    checkpoint_path: Path | None = None,
    allow_unknown_embedding_provider: str | None = None,
) -> dict[str, Any]:
    """Execute one non-resumable attempt; every transport body is strict-model-valid."""
    del checkpoint_path
    machine = LiveStageMachine()
    ledger = ToolLedger()
    gates = {str(index): 'blocked' for index in range(11)}
    active_gate = 0
    flags: dict[str, Any] = {}
    attestation = None
    capability_sha = artifact_sha = request_sha = manifest_sha = batch_uuid = None
    replay = 'skipped'
    plan_token: str | None = None
    commit_started = False
    manifest_hint = _confirmed_manifest_hint(
        run_id=confirm_run_id,
        group_id=confirm_group_id,
        control_group_id=confirm_control_group_id,
        batch_id=confirm_batch_id,
    )
    result_dir = (
        validate_result_directory(output_dir, payload_path, manifest_path) if output_dir else None
    )
    if result_dir is not None and result_dir.exists():
        raise RunnerError('result_directory_used', 'result directory must not exist')

    async def call(stage: str, name: str, body: dict[str, Any]) -> dict[str, Any]:
        return await _ledger_call(transport, ledger, stage, name, body)

    async def absence(
        group_id: str,
        batch_id: str,
        *,
        page_size: int,
        expected_uuid: str | None = None,
    ) -> str:
        status_raw = await call(
            'ISOLATION', 'get_catalog_ingest_status', {'group_id': group_id, 'batch_id': batch_id}
        )
        manifest_raw = await call(
            'ISOLATION',
            'get_catalog_batch_manifest',
            {'group_id': group_id, 'batch_id': batch_id, 'offset': 0, 'limit': page_size},
        )
        value = _assert_absent(
            status_raw, group_id=group_id, batch_id=batch_id, expected_batch_uuid=expected_uuid
        )
        _assert_absent(
            manifest_raw,
            group_id=group_id,
            batch_id=batch_id,
            manifest=True,
            expected_limit=page_size,
        )
        assert value is not None
        return value

    try:
        manifest_hint = preflight_live_manifest(
            manifest_path,
            confirm_run_id=confirm_run_id,
            confirm_group_id=confirm_group_id,
            confirm_control_group_id=confirm_control_group_id,
            confirm_batch_id=confirm_batch_id,
            allow_unknown_embedding_provider=allow_unknown_embedding_provider,
        )
        for value in (image_fingerprint, config_fingerprint):
            if value is not None and SHA256_RE.fullmatch(value) is None:
                raise RunnerError('source_attestation_invalid', 'optional fingerprint is invalid')
        attestor = source_attestor or attest_local_source
        attestation = attestor(
            expected_head=source_head,
            expected_source_map_sha256=source_map_sha256,
            expected_runner_sha256=runner_sha256,
            authority_mode=authority_mode,
        )
        if not isinstance(attestation, dict):
            raise RunnerError(
                'source_attestation_failed', 'source attestor returned invalid result'
            )
        exec_attestor = execution_attestor or attest_execution_authority
        execution_attestation = exec_attestor(
            expected_execution_map_sha256=execution_map_sha256,
        )
        if not isinstance(execution_attestation, dict):
            raise RunnerError(
                'execution_attestation_failed', 'execution attestor returned invalid result'
            )
        for key in ('execution_map_sha256', 'execution_files', 'execution_digest_method'):
            if key not in execution_attestation:
                raise RunnerError(
                    'execution_attestation_failed',
                    f'execution attestor missing field {key}',
                )
        attestation = {**attestation, **execution_attestation}
        gates['0'] = 'pass'
        active_gate = 1
        if result_dir is not None:
            result_dir.mkdir(parents=True, exist_ok=False)

        tools = await call('PREFLIGHT', 'list_tools', {})
        names = tools.get('names')
        if (
            tools.get('count') != 28
            or not isinstance(names, list)
            or set(names) != EXPECTED_MCP_TOOLS
        ):
            raise RunnerError('tool_registry_mismatch', 'MCP registry must match exact 28 tools')
        status = await call('PREFLIGHT', 'get_status', {})
        capabilities_raw = await call('PREFLIGHT', 'get_catalog_capabilities', {})
        if not isinstance(capabilities_raw, dict):
            raise RunnerError(
                'capability_preflight_failed', 'capability response must be an object'
            )
        # Hash unmodified raw server response before validation/policy; prove no mutation.
        raw_snapshot = copy.deepcopy(capabilities_raw)
        capability_sha = canonical_sha256(capabilities_raw)
        try:
            capabilities = CatalogCapabilitiesResponse.model_validate(capabilities_raw, strict=True)
        except ValidationError as exc:
            raise RunnerError(
                'capability_preflight_failed', 'capability response is invalid'
            ) from exc
        if capabilities_raw != raw_snapshot:
            raise RunnerError(
                'capability_preflight_failed',
                'raw capability response mutated during preflight',
            )
        if canonical_sha256(capabilities_raw) != capability_sha:
            raise RunnerError(
                'capability_preflight_failed',
                'raw capability SHA changed during preflight',
            )
        if (
            status.get('status') != 'ok'
            or capabilities.backend not in {'neo4j', 'Neo4j'}
            or capabilities.identity_schema_version != HARDENED_IDENTITY_SCHEMA_VERSION
            or capabilities.canonicalization_version != CANONICALIZATION_VERSION
            or capabilities.catalog_schema_version != CATALOG_SCHEMA_VERSION
            or capabilities.connectivity != 'ok'
            or capabilities.catalog_writes_enabled is not True
            or capabilities.catalog_reads_enabled is not True
            or capabilities.uuid_namespace_configured is not True
            or SAFE_NAMESPACE_FINGERPRINT_RE.fullmatch(capabilities.namespace_fingerprint or '')
            is None
            or capabilities.neo4j_indexes != 'ready'
            or any(
                capabilities.features.get(key) is not True
                for key in ('prepare_commit', 'manifests', 'manifest_verification')
            )
        ):
            raise RunnerError(
                'capability_preflight_failed', 'runtime catalog capabilities are incomplete'
            )
        raw_embeddings = dict(capabilities.embeddings or {})
        flags['embedding_policy'] = {
            'observed_provider': raw_embeddings.get('provider'),
            'observed_readiness': raw_embeddings.get('ready'),
            'waiver_applied': False,
        }
        embedding_policy = evaluate_embedding_readiness(
            raw_embeddings,
            allow_unknown_embedding_provider=allow_unknown_embedding_provider,
        )
        if capabilities_raw != raw_snapshot or canonical_sha256(capabilities_raw) != capability_sha:
            raise RunnerError(
                'capability_preflight_failed',
                'raw capability response mutated after policy evaluation',
            )
        flags['embedding_policy'] = embedding_policy
        if capabilities.features.get('same_token_replay') is True:
            raise RunnerError(
                'unsupported_replay_contract', 'advertised replay contract is not harness-validated'
            )
        page_size = _manifest_page_size(capabilities)
        flags['namespace_fingerprint'] = capabilities.namespace_fingerprint
        machine.advance(LiveStage.START, LiveStage.PREFLIGHT_PASSED)
        gates['1'] = 'pass'
        active_gate = 2

        batch_uuid = await absence(confirm_group_id, confirm_batch_id, page_size=page_size)
        control_uuid = await absence(
            confirm_control_group_id, confirm_batch_id, page_size=page_size
        )
        for group in (confirm_group_id, confirm_control_group_id):
            nodes = await call(
                'ISOLATION', 'search_nodes', {'group_ids': [group], 'query': 'phase6-isolation'}
            )
            facts = await call(
                'ISOLATION',
                'search_memory_facts',
                {'group_ids': [group], 'query': 'phase6-isolation'},
            )
            if nodes.get('nodes') or facts.get('facts'):
                raise RunnerError('isolation_failed', 'fresh group is not empty')
        machine.advance(LiveStage.PREFLIGHT_PASSED, LiveStage.ISOLATION_PASSED)
        gates['2'] = 'pass'
        active_gate = 3

        _, payload, manifest, request, artifact_sha, request_sha = validate_live_artifact(
            payload_path, manifest_path
        )
        flags['counts'] = _expected_domain_counts(request)
        validate_live_operator_confirmation(
            manifest,
            group_id=confirm_group_id,
            control_group_id=confirm_control_group_id,
            batch_id=confirm_batch_id,
        )
        machine.advance(LiveStage.ISOLATION_PASSED, LiveStage.ARTIFACT_VALIDATED)
        gates['3'] = 'pass'
        active_gate = 4

        dry_raw = await call('DRY_RUN', 'upsert_catalog_batch', build_live_dry_run_request(payload))
        dry = _validate_live_dry_run_response(
            dry_raw, request, request_sha, expected_batch_uuid=batch_uuid
        )
        after_dry_uuid = await absence(
            request.group_id,
            request.batch_id,
            page_size=page_size,
            expected_uuid=batch_uuid,
        )
        if after_dry_uuid != batch_uuid:
            raise RunnerError('batch_uuid_mismatch', 'post-dry-run batch UUID differs')
        flags['dry_run_zero_write_proven'] = True
        machine.advance(LiveStage.ARTIFACT_VALIDATED, LiveStage.DRY_RUN_PASSED)
        gates['4'] = 'pass'
        active_gate = 5

        prepared_raw = await call(
            'PREPARE', 'prepare_catalog_batch', build_prepare_transport_request(payload)
        )
        prepared, plan_token = _validate_live_prepare_overlap(
            prepared_raw, request, request_sha, dry
        )
        # Validated prepare is functional embedding proof; later isolation failure cannot erase it.
        flags['prepare_functional_embedding_proof'] = True
        after_prepare_uuid = await absence(
            request.group_id,
            request.batch_id,
            page_size=page_size,
            expected_uuid=batch_uuid,
        )
        if after_prepare_uuid != batch_uuid:
            raise RunnerError('batch_uuid_mismatch', 'post-prepare batch UUID differs')
        machine.advance(LiveStage.DRY_RUN_PASSED, LiveStage.PREPARE_PASSED)
        gates['5'] = 'pass'
        active_gate = 6

        commit_body = build_commit_transport_request(
            plan_token, expected_request_sha256=request_sha
        )
        if result_dir is not None:
            atomic_write_json(
                result_dir / 'commit-started.json',
                {
                    'schema_version': 1,
                    'stage': machine.stage.name,
                    'plan_uuid': prepared.plan_uuid,
                    'artifact_sha256': prepared.artifact_sha256,
                    'expires_at': prepared.expires_at,
                    'counts': _expected_domain_counts(request),
                    'request_sha256': request_sha,
                    'catalog_sha256': request.catalog_sha256,
                    'batch_uuid': batch_uuid,
                },
            )
        ambiguity: BaseException | None = None
        try:
            commit_started = True
            flags['commit_started'] = True
            active_gate = 6
            commit_raw = await call('COMMIT', 'commit_prepared_catalog_batch', commit_body)
            committed_response = _validate_commit_response(
                commit_raw,
                request,
                request_sha,
                expected_plan_uuid=prepared.plan_uuid,
                expected_artifact_sha256=prepared.artifact_sha256,
            )
            outcome = {
                'created': committed_response.committed_created,
                'updated': committed_response.committed_updated,
                'unchanged': committed_response.committed_unchanged,
            }
            if outcome != dry['outcome'] or committed_response.batch_uuid != batch_uuid:
                raise RunnerError('commit_binding_mismatch', 'commit C/U/U or batch UUID differs')
            manifest_sha = committed_response.manifest_sha256
        except BaseException as exc:
            ambiguity = exc

        status_raw = await call(
            'RECONCILE' if ambiguity else 'POST_COMMIT',
            'get_catalog_ingest_status',
            {'group_id': request.group_id, 'batch_id': request.batch_id},
        )
        status_response = _validate_committed_status(
            status_raw, request, request_sha, expected_batch_uuid=batch_uuid
        )
        if status_response.batch_uuid != batch_uuid:
            raise RunnerError('batch_uuid_mismatch', 'reconciled status batch UUID differs')

        async def manifest_call(name: str, body: dict[str, Any]) -> dict[str, Any]:
            return await call('RECONCILE' if ambiguity else 'MANIFEST', name, body)

        if manifest_sha is None:
            first_manifest = await manifest_call(
                'get_catalog_batch_manifest',
                {
                    'group_id': request.group_id,
                    'batch_id': request.batch_id,
                    'offset': 0,
                    'limit': page_size,
                },
            )
            candidate = GetCatalogBatchManifestResponse.model_validate(first_manifest, strict=True)
            if candidate.manifest_sha256 is None:
                raise RunnerError(
                    'ambiguous_commit_unresolved', 'committed manifest hash is absent'
                )
            manifest_sha = candidate.manifest_sha256
            # The bounded pass already consumed page zero; use a cache exactly once.
            cached = first_manifest
            original = manifest_call

            async def manifest_call(name: str, body: dict[str, Any]) -> dict[str, Any]:
                nonlocal cached
                if body.get('offset') == 0 and cached is not None:
                    value, cached = cached, None
                    return value
                return await original(name, body)

        (
            durable_manifest,
            manifest_entities,
            manifest_edges,
            manifest_sources,
            manifest_evidence,
        ) = await _fetch_full_manifest(
            manifest_call,
            request,
            request_sha,
            page_size=page_size,
            expected_artifact_sha256=prepared.artifact_sha256,
            expected_manifest_sha256=manifest_sha,
        )
        flags['commit_confirmed'] = True
        machine.advance(LiveStage.PREPARE_PASSED, LiveStage.COMMIT_CONFIRMED)
        gates['6'] = 'pass'
        active_gate = 7
        flags['manifest_verified'] = True
        machine.advance(LiveStage.COMMIT_CONFIRMED, LiveStage.MANIFEST_VERIFIED)
        gates['7'] = 'pass'
        active_gate = 8

        resolved_raw = await call(
            'RESOLVE', 'resolve_typed_entities', build_resolve_entities_request(request)
        )
        resolved_entities = _validate_resolved_entities(resolved_raw, request, manifest_entities)
        flags['entity_resolution_verified'] = True
        edge_raw = await call(
            'RESOLVE', 'resolve_typed_edges', build_resolve_edges_request(request)
        )
        _validate_resolved_edges(edge_raw, request, resolved_entities, manifest_edges)
        flags['edge_resolution_verified'] = True
        verify_raw = await call(
            'VERIFY', 'verify_catalog_batch', build_verify_request(request, resolved_entities)
        )
        _validate_verify_response(verify_raw, request)
        verify = VerifyCatalogBatchResponse.model_validate(verify_raw, strict=True)
        if verify.manifest_sha256 != manifest_sha:
            raise RunnerError('verify_failed', 'verify manifest hash differs')
        evidence_count = await _verify_all_evidence(
            lambda name, body: call('EVIDENCE', name, body),
            request,
            page_size=page_size,
            entity_uuids=manifest_entities,
            edge_uuids=manifest_edges,
            source_uuids=manifest_sources,
            manifest_evidence=manifest_evidence,
        )
        if evidence_count != len(manifest_evidence):
            raise RunnerError('evidence_failed', 'evidence total differs')
        flags['evidence_verified'] = True
        gates['8'] = 'pass'
        active_gate = 9

        for item in request.entities:
            raw = await call(
                'SEARCH',
                'search_nodes',
                {
                    'query': item.graph_key,
                    'group_ids': [request.group_id],
                    'max_nodes': 10,
                    'entity_types': [item.entity_type],
                    'center_node_uuid': None,
                },
            )
            _validate_node_search_strict(
                raw,
                group_id=request.group_id,
                expected_uuid=manifest_entities[(item.entity_type, item.graph_key)],
                entity_type=item.entity_type,
                graph_key=item.graph_key,
            )
        for item in request.edges:
            raw = await call(
                'SEARCH',
                'search_memory_facts',
                {
                    'query': item.fact,
                    'group_ids': [request.group_id],
                    'max_facts': 10,
                    'center_node_uuid': None,
                    'edge_types': [item.edge_type],
                    'valid_at_after': None,
                    'valid_at_before': None,
                    'invalid_at_after': None,
                    'invalid_at_before': None,
                },
            )
            source_uuid = manifest_entities[(item.source_entity_type, item.source_graph_key)]
            target_uuid = manifest_entities[(item.target_entity_type, item.target_graph_key)]
            _validate_fact_search_strict(
                raw,
                group_id=request.group_id,
                expected_uuid=manifest_edges[(item.edge_type, item.edge_key)],
                edge_type=item.edge_type,
                edge_key=item.edge_key,
                source_node_uuid=source_uuid,
                target_node_uuid=target_uuid,
            )
        final_control_uuid = await absence(
            manifest['control_group_id'],
            request.batch_id,
            page_size=page_size,
            expected_uuid=control_uuid,
        )
        if final_control_uuid != control_uuid:
            raise RunnerError('control_isolation_failed', 'final control batch UUID differs')
        nodes = await call(
            'CONTROL',
            'search_nodes',
            {'group_ids': [manifest['control_group_id']], 'query': request.entities[0].graph_key},
        )
        facts = await call(
            'CONTROL',
            'search_memory_facts',
            {'group_ids': [manifest['control_group_id']], 'query': request.edges[0].fact},
        )
        if nodes.get('nodes') or facts.get('facts'):
            raise RunnerError('control_isolation_failed', 'control group is not empty')
        flags['search_verified'] = True
        flags['control_isolation_verified'] = True
        machine.advance(LiveStage.MANIFEST_VERIFIED, LiveStage.SEARCH_ISOLATION_VERIFIED)
        gates['9'] = 'pass'
        active_gate = 10
        gates['10'] = 'pass'
        machine.advance(LiveStage.SEARCH_ISOLATION_VERIFIED, LiveStage.REPLAY_VERIFIED_OR_SKIPPED)
        machine.advance(LiveStage.REPLAY_VERIFIED_OR_SKIPPED, LiveStage.FINALIZED)
        report = _terminal_report(
            manifest=manifest,
            classification='PASSED',
            machine=machine,
            gates=gates,
            attestation=attestation,
            capability_sha256=capability_sha,
            artifact_sha256=artifact_sha,
            request_sha256=request_sha,
            manifest_sha256=manifest_sha,
            batch_uuid=batch_uuid,
            replay=replay,
            error_code=None,
            error_type=None,
            flags=flags,
            plan_token=plan_token,
            ledger_entries=ledger.entries,
        )
        if result_dir is not None:
            _persist_terminal_artifacts(result_dir, report=report, ledger_entries=ledger.entries)
        return report
    except BaseException as exc:
        classification = 'FAILED_AFTER_COMMIT' if commit_started else 'FAILED_BEFORE_COMMIT'
        if result_dir is not None and not result_dir.exists():
            _persist_pretransport_terminal_failure(
                result_dir,
                manifest_hint=manifest_hint,
                exc=exc,
                attestation=attestation,
            )
            raise
        current_gate = str(active_gate)
        for gate in gates:
            if gate != current_gate and gates[gate] != 'pass':
                gates[gate] = 'blocked'
        gates[current_gate] = 'fail'
        error_code = exc.code if isinstance(exc, RunnerError) else 'internal_runner_error'
        # Invalid ledger must reject terminal artifacts; no inconsistent fallback write.
        report = _terminal_report(
            manifest=manifest_hint,
            classification=classification,
            machine=machine,
            gates=gates,
            attestation=attestation,
            capability_sha256=capability_sha,
            artifact_sha256=artifact_sha,
            request_sha256=request_sha,
            manifest_sha256=manifest_sha,
            batch_uuid=batch_uuid,
            replay='failed' if commit_started else replay,
            error_code=error_code,
            error_type=type(exc).__name__,
            flags=flags,
            plan_token=plan_token,
            ledger_entries=ledger.entries,
        )
        if result_dir is not None:
            _persist_terminal_artifacts(result_dir, report=report, ledger_entries=ledger.entries)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-url', required=True, help=argparse.SUPPRESS)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--group-id')
    parser.add_argument('--control-group-id')
    parser.add_argument('--batch-id')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--source-head')
    parser.add_argument('--source-map-sha256')
    parser.add_argument('--runner-sha256')
    parser.add_argument('--execution-map-sha256')
    parser.add_argument('--authority-mode', choices=('git', 'archive'), default='git')
    parser.add_argument('--image-fingerprint')
    parser.add_argument('--config-fingerprint')
    parser.add_argument('--mode', default='commit', choices=('commit', 'live-canary'))
    parser.add_argument('--expected-artifact-sha256')
    parser.add_argument('--expected-request-sha256')
    parser.add_argument('--checkpoint', type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument(
        '--allow-unknown-embedding-provider',
        choices=('openai',),
        default=None,
        help='Explicit waiver for provider=openai readiness=unknown only; never rewrites readiness',
    )
    args = parser.parse_args(argv)
    if args.mode == 'live-canary':
        missing = [
            name
            for name in (
                'manifest',
                'run_id',
                'group_id',
                'control_group_id',
                'batch_id',
                'output_dir',
                'source_head',
                'source_map_sha256',
                'runner_sha256',
                'execution_map_sha256',
            )
            if getattr(args, name) is None
        ]
        if missing:
            parser.error(
                'live-canary requires: '
                + ', '.join('--' + name.replace('_', '-') for name in missing)
            )
        if args.output_dir.exists():
            parser.error('live-canary receipt directory must not already exist')
        for name in (
            'source_map_sha256',
            'runner_sha256',
            'execution_map_sha256',
            'image_fingerprint',
            'config_fingerprint',
        ):
            value = getattr(args, name)
            if value is not None and SHA256_RE.fullmatch(value) is None:
                parser.error('--' + name.replace('_', '-') + ' must be lowercase SHA-256')
        if SOURCE_HEAD_RE.fullmatch(args.source_head or '') is None:
            parser.error('--source-head must be lowercase Git SHA-1')
        if (
            args.allow_unknown_embedding_provider is not None
            and args.allow_unknown_embedding_provider != 'openai'
        ):
            parser.error('--allow-unknown-embedding-provider only accepts openai')
    return args


async def execute_cli(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode != 'live-canary':
        return await execute(args)
    payload_path = args.payload.resolve()
    manifest_path = args.manifest.resolve()
    result_dir = validate_result_directory(args.output_dir, payload_path, manifest_path)
    if result_dir.exists():
        raise RunnerError('result_directory_used', 'result directory must not exist')
    manifest_hint = _confirmed_manifest_hint(
        run_id=args.run_id,
        group_id=args.group_id,
        control_group_id=args.control_group_id,
        batch_id=args.batch_id,
    )
    try:
        manifest_hint = preflight_live_manifest(
            manifest_path,
            confirm_run_id=args.run_id,
            confirm_group_id=args.group_id,
            confirm_control_group_id=args.control_group_id,
            confirm_batch_id=args.batch_id,
            allow_unknown_embedding_provider=args.allow_unknown_embedding_provider,
        )
        attestation = attest_local_source(
            expected_head=args.source_head,
            expected_source_map_sha256=args.source_map_sha256,
            expected_runner_sha256=args.runner_sha256,
            authority_mode=args.authority_mode,
        )
        execution_attestation = attest_execution_authority(
            expected_execution_map_sha256=args.execution_map_sha256,
        )
        combined = {**attestation, **execution_attestation}
    except BaseException as exc:
        _persist_pretransport_terminal_failure(
            result_dir,
            manifest_hint=manifest_hint,
            exc=exc,
        )
        raise

    def preverified_source_attestor(**_kwargs: Any) -> dict[str, Any]:
        return {
            'source_head': combined['source_head'],
            'source_map_sha256': combined['source_map_sha256'],
            'runner_sha256': combined['runner_sha256'],
            'source_files': combined['source_files'],
        }

    def preverified_execution_attestor(**_kwargs: Any) -> dict[str, Any]:
        return {
            'execution_map_sha256': combined['execution_map_sha256'],
            'execution_files': combined['execution_files'],
            'execution_digest_method': combined['execution_digest_method'],
        }

    async with (
        streamable_http_client(args.mcp_url) as (read_stream, write_stream, _),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        return await run_live_canary(
            SessionLiveTransport(session),
            payload_path,
            manifest_path,
            confirm_run_id=args.run_id,
            confirm_group_id=args.group_id,
            confirm_control_group_id=args.control_group_id,
            confirm_batch_id=args.batch_id,
            source_head=args.source_head,
            source_map_sha256=args.source_map_sha256,
            runner_sha256=args.runner_sha256,
            execution_map_sha256=args.execution_map_sha256,
            authority_mode=args.authority_mode,
            image_fingerprint=args.image_fingerprint,
            config_fingerprint=args.config_fingerprint,
            output_dir=args.output_dir,
            source_attestor=preverified_source_attestor,
            execution_attestor=preverified_execution_attestor,
            allow_unknown_embedding_provider=args.allow_unknown_embedding_provider,
        )


def main(argv: list[str] | None = None) -> int:
    try:
        result = asyncio.run(execute_cli(parse_args(argv)))
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
