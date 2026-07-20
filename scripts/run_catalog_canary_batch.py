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
import uuid
from datetime import datetime, timezone
from enum import IntEnum
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
from models.catalog_provenance import CatalogSourceItem  # noqa: E402
from models.catalog_responses import (  # noqa: E402
    CatalogBatchWriteResponse,
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
from services.catalog_identity import (  # noqa: E402
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
        'add_memory', 'search_nodes', 'search_memory_facts', 'update_entity',
        'delete_entity_edge', 'delete_episode', 'get_entity_edge', 'get_episodes',
        'summarize_saga', 'build_communities', 'add_triplet', 'get_episode_entities',
        'clear_graph', 'get_status', 'upsert_typed_entities', 'resolve_typed_entities',
        'verify_catalog_batch', 'upsert_typed_edges', 'upsert_provenance',
        'get_catalog_ingest_status', 'upsert_catalog_batch', 'prepare_catalog_batch',
        'commit_prepared_catalog_batch', 'discard_prepared_catalog_batch',
        'get_catalog_batch_manifest', 'resolve_typed_edges', 'get_catalog_evidence',
        'get_catalog_capabilities',
    }
)
LIVE_PAYLOAD_NAME = 'accept-tab.payload.json'
LIVE_MANIFEST_NAME = 'run-manifest.json'
PROTECTED_GROUP_IDS = frozenset(
    {'oracle-core', 'oracle-catalog-v2', 'oracle-catalog-tool-test', 'main'}
)
LIVE_CANARY_TOOL_SEQUENCE = [
    'list_tools',
    'get_status',
    'get_catalog_capabilities',
    'get_catalog_ingest_status',
    'get_catalog_batch_manifest',
    'get_catalog_ingest_status',
    'get_catalog_batch_manifest',
    'search_nodes',
    'search_memory_facts',
    'search_nodes',
    'search_memory_facts',
    'upsert_catalog_batch',
    'get_catalog_ingest_status',
    'get_catalog_batch_manifest',
    'prepare_catalog_batch',
    'get_catalog_ingest_status',
    'get_catalog_batch_manifest',
    'commit_prepared_catalog_batch',
    'get_catalog_ingest_status',
    'get_catalog_batch_manifest',
    'verify_catalog_batch',
    'resolve_typed_entities',
    'get_catalog_evidence',
    'search_nodes',
    'search_memory_facts',
    'resolve_typed_edges',
    'search_nodes',
    'search_memory_facts',
]


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
            if self.upsert_calls != 1 or request.get('dry_run') is not True or type(request['dry_run']) is not bool:
                raise RunnerError('dry_run_transport_guard', 'live upsert is allowed exactly once with boolean true')
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
        os.replace(temporary, path)
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
    try:
        response = PrepareCatalogBatchResponse.model_validate(structured, strict=True)
    except ValidationError as exc:
        raise RunnerError(
            'invalid_prepare_response', 'prepare response has invalid structure'
        ) from exc
    if response.error_code is not None or response.error_message is not None:
        raise RunnerError('prepare_failed', 'prepare response contains structured error')
    if not response.plan_token:
        raise RunnerError('prepare_failed', 'prepare response omitted plan token')
    try:
        uuid.UUID(response.plan_uuid)
    except ValueError as exc:
        raise RunnerError('prepare_binding_mismatch', 'prepare response plan UUID is invalid') from exc
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
    expected_committed_total = len(request.entities) + len(request.edges) + len(
        request.provenance.sources
    )
    if committed_total != expected_committed_total:
        raise RunnerError('commit_count_mismatch', 'committed outcome count does not match artifact')
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
        raise RunnerError('verify_evidence_count_mismatch', 'verify evidence counts do not match artifact')
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
) -> None:
    facts = structured.get('facts')
    if not isinstance(facts, list) or not facts:
        raise RunnerError('fact_search_failed', 'fact retrieval gate returned no facts')
    for fact in facts:
        if not isinstance(fact, dict) or fact.get('group_id') != group_id:
            continue
        attributes_raw = fact.get('attributes')
        attributes: dict[str, Any] = attributes_raw if isinstance(attributes_raw, dict) else {}
        exact_edge_key = fact.get('edge_key') == edge.edge_key or attributes.get(
            'edge_key'
        ) == edge.edge_key
        if (
            fact.get('uuid') == expected_uuid
            and exact_edge_key
            and fact.get('name') == edge.edge_type
            and fact.get('fact') == edge.fact
        ):
            return
    raise RunnerError('fact_search_failed', 'fact retrieval gate did not return expected edge')


def _validate_manifest_inventory(
    manifest: GetCatalogBatchManifestResponse,
    request: UpsertCatalogBatchRequest,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str], dict[str, str]]:
    assert request.provenance is not None
    if manifest.offset != 0 or manifest.limit < max(
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources),
        len(request.provenance.evidence_links),
    ):
        raise RunnerError('manifest_failed', 'manifest response is not a complete first page')

    entity_expected = {
        (item.entity_type, item.graph_key): item.content_sha256 for item in request.entities
    }
    edge_expected = {(item.edge_type, item.edge_key): item.content_sha256 for item in request.edges}
    source_expected = {item.source_key: item.content_sha256 for item in request.provenance.sources}
    evidence_expected = {
        evidence_link_key(item): canonical_sha256(evidence_canonical_payload(item))
        for item in request.provenance.evidence_links
    }
    entity_found = {
        (item.entity_type, item.graph_key): item for item in manifest.entities
    }
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
    if any(evidence_found[key].content_sha256 != digest for key, digest in evidence_expected.items()):
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
    _, structured = await call_mcp_tool(
        session, 'verify_catalog_batch', {'request': verify_request}
    )
    _validate_verify_response(structured, request)
    verify = VerifyCatalogBatchResponse.model_validate(structured, strict=True)
    if verify.manifest_sha256 != expected_manifest_sha256:
        raise RunnerError('verify_failed', 'verify manifest hash does not match commit')
    summaries['verify_catalog_batch'] = {
        'manifest_sha256': verify.manifest_sha256,
        'counts': [
            verify.entities.expected,
            verify.edges.expected,
            verify.evidence.expected,
        ],
    }

    resolve_request = {
        'group_id': request.group_id,
        'entities': [
            {'entity_type': item.entity_type, 'graph_key': item.graph_key}
            for item in request.entities
        ],
        'graph_keys': None,
    }
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
                    for (entity_type, graph_key), entity_uuid in sorted(
                        resolved_entities.items()
                    )
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
    if expected_artifact_sha256 is not None and receipt['artifact_sha256'] != expected_artifact_sha256:
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
        value for value in raw_outcome_counts if isinstance(value, int) and not isinstance(value, bool)
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
            'counts': [expected_counts['entities'], expected_counts['edges'], expected_provenance_count],
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
        raise RunnerError('invalid_status_response', 'status response has invalid structure') from exc
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
        raise RunnerError('invalid_manifest_response', 'manifest response has invalid structure') from exc
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
    if (
        not isinstance(rel, str)
        or not rel
        or Path(rel).is_absolute()
        or '..' in Path(rel).parts
    ):
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
    if not isinstance(expected_response_sha, str) or sha256_bytes(response_bytes) != expected_response_sha:
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
    artifact_bytes, raw, _, artifact_sha256, server_request_sha256 = (
        validate_hardened_artifact(
            payload_path,
            expected_artifact_sha256=args.expected_artifact_sha256,
            expected_request_sha256=args.expected_request_sha256,
        )
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
        if not isinstance(manifest_sha256, str) or not isinstance(
            prepared_artifact_sha256, str
        ):
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


def validate_live_operator_confirmation(
    manifest: dict[str, Any], *, group_id: str, control_group_id: str, batch_id: str
) -> None:
    supplied = (group_id, control_group_id, batch_id)
    expected = (manifest.get('group_id'), manifest.get('control_group_id'), manifest.get('batch_id'))
    if supplied != expected:
        raise RunnerError('operator_confirmation_mismatch', 'operator confirmation does not match manifest')
    _reject_live_group(group_id)
    _reject_live_group(control_group_id)
    if group_id == control_group_id:
        raise RunnerError('control_group_mismatch', 'control group must differ from canary group')


def validate_live_artifact(
    payload_path: Path, manifest_path: Path
) -> tuple[bytes, dict[str, Any], dict[str, Any], UpsertCatalogBatchRequest, str, str]:
    for path in (payload_path.resolve(), manifest_path.resolve()):
        if HARDENED_ARTIFACT_DIR.resolve() in path.parents or (
            ROOT / 'catalog' / 'canary-v2-requests'
        ).resolve() in path.parents:
            raise RunnerError('golden_not_live', 'golden or historical artifact is not live authority')
    if payload_path.name != LIVE_PAYLOAD_NAME or manifest_path.name != LIVE_MANIFEST_NAME:
        raise RunnerError('live_filename_mismatch', 'live artifact filenames are invalid')
    payload_bytes = payload_path.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    payload = strict_json_loads(payload_bytes)
    manifest = strict_json_loads(manifest_bytes)
    if not isinstance(payload, dict) or not isinstance(manifest, dict):
        raise RunnerError('invalid_live_artifact', 'live artifact roots must be objects')
    if canonical_artifact_bytes(payload) != payload_bytes or canonical_artifact_bytes(manifest) != manifest_bytes:
        raise RunnerError('non_canonical_artifact', 'live artifact bytes must be canonical')
    fixture_path = ROOT / str(manifest.get('fixture') or '')
    if (
        manifest.get('profile') != 'live-canary'
        or manifest.get('artifact_schema_version') != LIVE_ARTIFACT_SCHEMA_VERSION
        or manifest.get('payload') != LIVE_PAYLOAD_NAME
        or manifest.get('artifact_sha256') != sha256_bytes(payload_bytes)
        or manifest.get('builder_sha256') != sha256_bytes(
            (ROOT / 'scripts' / 'build_catalog_canary_requests.py').read_bytes()
        )
        or not fixture_path.is_file()
        or manifest.get('fixture_sha256') != sha256_bytes(fixture_path.read_bytes())
    ):
        raise RunnerError('live_manifest_mismatch', 'live manifest binding is invalid')
    _validate_hardened_raw_field_sets(payload)
    try:
        request = UpsertCatalogBatchRequest.model_validate({**payload, 'dry_run': True}, strict=True)
    except ValidationError as exc:
        raise RunnerError('request_validation_failed', 'live payload fails validation') from exc
    _validate_content_hashes(request)
    request_sha = CatalogService.batch_request_sha256(request)
    provenance = request.provenance
    assert provenance is not None
    counts = {
        'entities': len(request.entities),
        'edges': len(request.edges),
        'sources': len(provenance.sources),
        'evidence_links': len(provenance.evidence_links),
    }
    if (
        manifest.get('group_id') != request.group_id
        or manifest.get('batch_id') != request.batch_id
        or manifest.get('catalog_sha256') != request.catalog_sha256
        or manifest.get('request_sha256') != request_sha
        or manifest.get('counts') != counts
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
            or response.get('offset', 0) != 0
            or response.get('limit', expected_limit) != expected_limit
            or any(response.get(key) for key in ('entities', 'edges', 'sources', 'evidence_links'))
            or any(
                response.get(key, 0) != 0
                for key in ('entity_count', 'edge_count', 'source_count', 'evidence_link_count')
            )
            or any(
                response.get(key) is not None
                for key in (
                    'request_sha256', 'catalog_sha256', 'artifact_sha256', 'manifest_sha256',
                    'identity_schema_version', 'canonicalization_version', 'catalog_schema_version',
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
        or any(response.get(key, 0) != 0 for key in ('entity_count', 'edge_count', 'provenance_count'))
        or any(
            response.get(key) is not None
            for key in (
                'request_sha256', 'catalog_sha256', 'created_at', 'updated_at', 'committed_at'
            )
        )
    ):
        raise RunnerError('zero_write_not_proven', 'status absence shape is ambiguous')
    return str(batch_uuid)


def _validate_live_dry_run_response(
    raw: dict[str, Any], request: UpsertCatalogBatchRequest, request_sha: str
) -> dict[str, Any]:
    try:
        response = CatalogBatchWriteResponse.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise RunnerError('invalid_dry_run_response', 'dry-run response is invalid') from exc
    try:
        uuid.UUID(response.batch_uuid or '')
    except ValueError as exc:
        raise RunnerError('dry_run_binding_mismatch', 'dry-run batch UUID is invalid') from exc
    provenance = request.provenance
    assert provenance is not None
    if (
        response.group_id != request.group_id
        or response.batch_id != request.batch_id
        or response.dry_run is not True
        or response.atomic is not True
        or response.status != 'validating'
        or response.identity_schema_version != request.identity_schema_version
        or response.request_sha256 != request_sha
        or response.catalog_sha256 != request.catalog_sha256
        or response.error_code is not None
        or response.error_message is not None
        or response.failed != 0
        or response.rolled_back != 0
        or response.entity_created + response.entity_updated + response.entity_unchanged
        != len(request.entities)
        or response.edge_created + response.edge_updated + response.edge_unchanged
        != len(request.edges)
        or response.provenance_created + response.provenance_updated + response.provenance_unchanged
        != len(provenance.sources)
    ):
        raise RunnerError('dry_run_binding_mismatch', 'dry-run receipt binding is invalid')
    return {
        'group_id': response.group_id,
        'batch_id': response.batch_id,
        'batch_uuid': response.batch_uuid,
        'identity_schema_version': response.identity_schema_version,
        'request_sha256': response.request_sha256,
        'catalog_sha256': response.catalog_sha256,
        'counts': _expected_domain_counts(request),
    }


def _validate_live_prepare_overlap(
    raw: dict[str, Any], request: UpsertCatalogBatchRequest, request_sha: str, dry_run: dict[str, Any]
) -> tuple[PrepareCatalogBatchResponse, str]:
    prepared, token = _validate_prepare_response(raw, request, request_sha)
    overlap = {
        'identity_schema_version': prepared.identity_schema_version,
        'request_sha256': prepared.request_sha256,
        'catalog_sha256': prepared.catalog_sha256,
        'counts': {
            'entities': prepared.entity_count,
            'edges': prepared.edge_count,
            'sources': prepared.source_count,
            'evidence_links': prepared.evidence_link_count,
        },
    }
    expected = {key: dry_run[key] for key in overlap}
    if overlap != expected:
        raise RunnerError('prepare_binding_mismatch', 'prepare differs from dry-run overlap')
    return prepared, token


def _validate_live_edges(
    raw: dict[str, Any],
    request: UpsertCatalogBatchRequest,
    entity_uuids: dict[tuple[str, str], str],
) -> None:
    try:
        response = ResolveTypedEdgesResponse.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise RunnerError('invalid_resolve_edges_response', 'typed edge response is invalid') from exc
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
            or result.source_uuid
            != entity_uuids[(edge.source_entity_type, edge.source_graph_key)]
            or result.target_uuid
            != entity_uuids[(edge.target_entity_type, edge.target_graph_key)]
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


def write_live_checkpoint(path: Path, stage: LiveStage, binding: dict[str, Any]) -> None:
    if stage > LiveStage.DRY_RUN_PASSED:
        raise RunnerError(
            'dry_run_checkpoint_required',
            'resume cannot persist or skip post-dry-run token-bound stages',
        )
    safe = {'schema_version': 1, 'stage': stage.name, 'binding': copy.deepcopy(binding)}
    text = json.dumps(safe, sort_keys=True)
    if 'plan_token' in text or 'token_digest' in text:
        raise RunnerError('token_persistence', 'checkpoint contains forbidden token material')
    atomic_write_json(path, safe)


def require_live_resume(path: Path, binding: dict[str, Any]) -> None:
    checkpoint = strict_json_load(path)
    if (
        not isinstance(checkpoint, dict)
        or checkpoint.get('stage') != LiveStage.DRY_RUN_PASSED.name
        or checkpoint.get('binding') != binding
    ):
        raise RunnerError('resume_binding_mismatch', 'resume lacks exact dry-run binding')


async def _call_live(transport: Any, name: str, request: dict[str, Any]) -> dict[str, Any]:
    result = await transport.call(name, request)
    if not isinstance(result, dict):
        raise RunnerError('invalid_transport_result', f'{name} returned invalid result')
    return result


async def run_live_canary(
    transport: Any,
    payload_path: Path,
    manifest_path: Path,
    *,
    confirm_run_id: str,
    confirm_group_id: str,
    confirm_control_group_id: str,
    confirm_batch_id: str,
    source_fingerprint: str,
    tree_fingerprint: str,
    image_fingerprint: str | None = None,
    config_fingerprint: str | None = None,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Run monotonic live stages through an injected transport; tests use fakes only."""
    machine = LiveStageMachine()
    manifest_hint = strict_json_load(manifest_path)
    if not isinstance(manifest_hint, dict):
        raise RunnerError('invalid_live_manifest', 'live manifest must be an object')
    if confirm_run_id != manifest_hint.get('run_id'):
        raise RunnerError('operator_confirmation_mismatch', 'run_id confirmation does not match manifest')
    validate_live_operator_confirmation(
        manifest_hint,
        group_id=confirm_group_id,
        control_group_id=confirm_control_group_id,
        batch_id=confirm_batch_id,
    )
    tools = await _call_live(transport, 'list_tools', {})
    names = tools.get('names')
    if (
        tools.get('count') != 28
        or not isinstance(names, list)
        or set(names) != EXPECTED_MCP_TOOLS
    ):
        raise RunnerError('tool_registry_mismatch', 'MCP registry must match exact 28 tools')
    status = await _call_live(transport, 'get_status', {})
    capabilities = await _call_live(transport, 'get_catalog_capabilities', {})
    features = capabilities.get('features') or {}
    embeddings = capabilities.get('embeddings') or {}
    if (
        status.get('status') != 'ok'
        or capabilities.get('backend') not in {'neo4j', 'Neo4j'}
        or capabilities.get('identity_schema_version') != HARDENED_IDENTITY_SCHEMA_VERSION
        or capabilities.get('connectivity') != 'ok'
        or capabilities.get('catalog_writes_enabled') is not True
        or capabilities.get('catalog_reads_enabled') is not True
        or capabilities.get('uuid_namespace_configured') is not True
        or capabilities.get('neo4j_indexes') != 'ready'
        or embeddings.get('ready') != 'ready'
        or any(features.get(key) is not True for key in ('prepare_commit', 'manifests', 'manifest_verification'))
    ):
        raise RunnerError('capability_preflight_failed', 'runtime catalog capabilities are incomplete')
    capability_fingerprint = canonical_sha256(
        {key: value for key, value in capabilities.items() if key != 'namespace_fingerprint'}
    )
    machine.advance(LiveStage.START, LiveStage.PREFLIGHT_PASSED)

    async def absence(group_id: str, batch_id: str) -> None:
        status_result = await _call_live(
            transport, 'get_catalog_ingest_status', {'group_id': group_id, 'batch_id': batch_id}
        )
        manifest_result = await _call_live(
            transport,
            'get_catalog_batch_manifest',
            {'group_id': group_id, 'batch_id': batch_id, 'offset': 0, 'limit': 100},
        )
        _assert_absent(status_result, group_id=group_id, batch_id=batch_id)
        _assert_absent(manifest_result, group_id=group_id, batch_id=batch_id, manifest=True)

    await absence(confirm_group_id, confirm_batch_id)
    await absence(confirm_control_group_id, confirm_batch_id)
    for group in (confirm_group_id, confirm_control_group_id):
        nodes = await _call_live(transport, 'search_nodes', {'group_ids': [group], 'query': 'phase6-isolation'})
        facts = await _call_live(transport, 'search_memory_facts', {'group_ids': [group], 'query': 'phase6-isolation'})
        if nodes.get('nodes') or facts.get('facts'):
            raise RunnerError('isolation_failed', 'fresh group is not empty')
    machine.advance(LiveStage.PREFLIGHT_PASSED, LiveStage.ISOLATION_PASSED)

    _, payload, manifest, request, artifact_sha, request_sha = validate_live_artifact(
        payload_path, manifest_path
    )
    machine.advance(LiveStage.ISOLATION_PASSED, LiveStage.ARTIFACT_VALIDATED)
    dry_body = build_live_dry_run_request(payload)
    dry_raw = await _call_live(transport, 'upsert_catalog_batch', dry_body)
    dry_receipt = _validate_live_dry_run_response(dry_raw, request, request_sha)
    await absence(request.group_id, request.batch_id)
    binding = {
        'artifact_sha256': artifact_sha,
        'catalog_sha256': request.catalog_sha256,
        'request_sha256': request_sha,
        'group_id': request.group_id,
        'batch_id': request.batch_id,
        'runtime_capability_sha256': capability_fingerprint,
        'source_fingerprint': source_fingerprint,
        'tree_fingerprint': tree_fingerprint,
        'image_fingerprint': image_fingerprint,
        'config_fingerprint': config_fingerprint,
    }
    machine.advance(LiveStage.ARTIFACT_VALIDATED, LiveStage.DRY_RUN_PASSED)
    if checkpoint_path is not None:
        write_live_checkpoint(checkpoint_path, LiveStage.DRY_RUN_PASSED, binding)

    machine.require(LiveStage.DRY_RUN_PASSED)
    prepare_body = build_prepare_transport_request(payload)
    prepared_raw = await _call_live(transport, 'prepare_catalog_batch', prepare_body)
    prepared, plan_token = _validate_live_prepare_overlap(prepared_raw, request, request_sha, dry_receipt)
    await absence(request.group_id, request.batch_id)
    machine.advance(LiveStage.DRY_RUN_PASSED, LiveStage.PREPARE_PASSED)
    machine.require(LiveStage.PREPARE_PASSED)
    commit_body = build_commit_transport_request(plan_token, expected_request_sha256=request_sha)
    try:
        commit_raw = await _call_live(transport, 'commit_prepared_catalog_batch', commit_body)
    except Exception as exc:
        raise RunnerError(
            'ambiguous_commit_requires_reconciliation',
            'commit transport outcome requires same group/batch read reconciliation',
        ) from exc
    committed = _validate_commit_response(
        commit_raw,
        request,
        request_sha,
        expected_plan_uuid=prepared.plan_uuid,
        expected_artifact_sha256=prepared.artifact_sha256,
    )
    machine.advance(LiveStage.PREPARE_PASSED, LiveStage.COMMIT_CONFIRMED)
    manifest_sha = committed.manifest_sha256
    assert manifest_sha is not None
    status_raw = await _call_live(
        transport,
        'get_catalog_ingest_status',
        {'group_id': request.group_id, 'batch_id': request.batch_id},
    )
    _validate_status_response(status_raw, request, request_sha)
    assert request.provenance is not None
    manifest_limit = max(
        len(request.entities),
        len(request.edges),
        len(request.provenance.sources),
        len(request.provenance.evidence_links),
    )
    manifest_raw = await _call_live(
        transport,
        'get_catalog_batch_manifest',
        {
            'group_id': request.group_id,
            'batch_id': request.batch_id,
            'offset': 0,
            'limit': manifest_limit,
        },
    )
    try:
        durable_manifest = GetCatalogBatchManifestResponse.model_validate(
            manifest_raw, strict=True
        )
    except ValidationError as exc:
        raise RunnerError('invalid_manifest_response', 'manifest response is invalid') from exc
    if (
        not durable_manifest.found
        or durable_manifest.request_sha256 != request_sha
        or durable_manifest.catalog_sha256 != request.catalog_sha256
        or durable_manifest.artifact_sha256 != prepared.artifact_sha256
        or durable_manifest.manifest_sha256 != manifest_sha
        or durable_manifest.identity_schema_version != request.identity_schema_version
    ):
        raise RunnerError('manifest_failed', 'manifest response binding failed')
    manifest_entities, manifest_edges, manifest_evidence = _validate_manifest_inventory(
        durable_manifest, request
    )
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
    verify_raw = await _call_live(transport, 'verify_catalog_batch', verify_request)
    _validate_verify_response(verify_raw, request)
    resolved_raw = await _call_live(
        transport,
        'resolve_typed_entities',
        {
            'group_id': request.group_id,
            'entities': [
                {'entity_type': item.entity_type, 'graph_key': item.graph_key}
                for item in request.entities
            ],
            'graph_keys': None,
        },
    )
    resolved_entities = _validate_resolve_response(resolved_raw, request)
    if resolved_entities != manifest_entities:
        raise RunnerError('manifest_failed', 'typed entity UUIDs differ from manifest')
    representative = request.entities[0]
    evidence_raw = await _call_live(
        transport,
        'get_catalog_evidence',
        {
            'group_id': request.group_id,
            'identity_schema_version': request.identity_schema_version,
            'system_key': request.system_key,
            'entity_target': {
                'entity_type': representative.entity_type,
                'graph_key': representative.graph_key,
            },
            'edge_target': None,
            'offset': 0,
            'limit': 100,
            'include_excerpts': False,
        },
    )
    evidence_response = GetCatalogEvidenceResponse.model_validate(evidence_raw, strict=True)
    _validate_evidence_response(
        evidence_response,
        request,
        target_kind='entity',
        target_key=representative.graph_key,
        target_uuid=manifest_entities[(representative.entity_type, representative.graph_key)],
        expected_links=manifest_evidence,
    )
    node_raw = await _call_live(
        transport,
        'search_nodes',
        {
            'query': representative.graph_key,
            'group_ids': [request.group_id],
            'max_nodes': 10,
            'entity_types': [representative.entity_type],
            'center_node_uuid': None,
        },
    )
    _validate_node_search(
        node_raw,
        graph_key=representative.graph_key,
        group_id=request.group_id,
        entity_type=representative.entity_type,
        expected_uuid=manifest_entities[(representative.entity_type, representative.graph_key)],
    )
    representative_edge = request.edges[0]
    fact_raw = await _call_live(
        transport,
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
    _validate_fact_search(
        fact_raw,
        representative_edge,
        group_id=request.group_id,
        expected_uuid=manifest_edges[(representative_edge.edge_type, representative_edge.edge_key)],
    )
    post_commit = {
        'status_verified': True,
        'manifest_verified': True,
        'entities_verified': len(request.entities),
        'edges_verified': len(request.edges),
        'evidence_verified': evidence_response.total,
        'search_verified': True,
    }
    machine.advance(LiveStage.COMMIT_CONFIRMED, LiveStage.MANIFEST_VERIFIED)
    edges_request = {
        'group_id': request.group_id,
        'edges': [{'edge_type': edge.edge_type, 'edge_key': edge.edge_key} for edge in request.edges],
    }
    edges_raw = await _call_live(transport, 'resolve_typed_edges', edges_request)
    _validate_live_edges(edges_raw, request, manifest_entities)
    for group in (manifest['control_group_id'],):
        nodes = await _call_live(transport, 'search_nodes', {'group_ids': [group], 'query': request.entities[0].graph_key})
        facts = await _call_live(transport, 'search_memory_facts', {'group_ids': [group], 'query': request.edges[0].fact})
        if nodes.get('nodes') or facts.get('facts'):
            raise RunnerError('control_isolation_failed', 'control group is not empty')
    machine.advance(LiveStage.MANIFEST_VERIFIED, LiveStage.SEARCH_ISOLATION_VERIFIED)
    replay_advertised = features.get('same_token_replay') is True
    if replay_advertised:
        raise RunnerError(
            'unsupported_replay_contract',
            'runtime advertises replay without a harness-validated response contract',
        )
    machine.advance(
        LiveStage.SEARCH_ISOLATION_VERIFIED,
        LiveStage.REPLAY_VERIFIED_OR_SKIPPED,
    )
    machine.advance(LiveStage.REPLAY_VERIFIED_OR_SKIPPED, LiveStage.FINALIZED)
    report = {
        'classification': 'PASSED',
        'stage': machine.stage.name,
        'stage_ledger': machine.ledger,
        'run_id': manifest['run_id'],
        'group_id': request.group_id,
        'control_group_id': manifest['control_group_id'],
        'batch_id': request.batch_id,
        'binding': binding,
        'batch_uuid': committed.batch_uuid,
        'manifest_sha256': manifest_sha,
        'post_commit': post_commit,
        'replay': 'verified' if replay_advertised else 'skipped',
        'canary_executed': True,
    }
    if plan_token in json.dumps(report, sort_keys=True):
        raise RunnerError('token_persistence', 'raw plan token reached final report')
    return report


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
    parser.add_argument('--source-fingerprint')
    parser.add_argument('--tree-fingerprint')
    parser.add_argument('--image-fingerprint')
    parser.add_argument('--config-fingerprint')
    parser.add_argument('--mode', default='commit', choices=('commit', 'live-canary'))
    parser.add_argument('--expected-artifact-sha256')
    parser.add_argument('--expected-request-sha256')
    parser.add_argument('--checkpoint', type=Path, default=DEFAULT_CHECKPOINT)
    args = parser.parse_args(argv)
    if args.mode == 'live-canary':
        missing = [
            name
            for name in (
                'manifest', 'run_id', 'group_id', 'control_group_id', 'batch_id',
                'output_dir', 'source_fingerprint', 'tree_fingerprint',
            )
            if getattr(args, name) is None
        ]
        if missing:
            parser.error('live-canary requires: ' + ', '.join('--' + name.replace('_', '-') for name in missing))
        if args.output_dir.exists():
            parser.error('live-canary receipt directory must not already exist')
        for name in (
            'source_fingerprint', 'tree_fingerprint', 'image_fingerprint', 'config_fingerprint'
        ):
            value = getattr(args, name)
            if value is not None and SHA256_RE.fullmatch(value) is None:
                parser.error('--' + name.replace('_', '-') + ' must be lowercase SHA-256')
    return args


async def execute_cli(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode != 'live-canary':
        return await execute(args)
    args.output_dir.mkdir(parents=False, exist_ok=False)
    try:
        async with (
            streamable_http_client(args.mcp_url) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            result = await run_live_canary(
                SessionLiveTransport(session),
                args.payload.resolve(),
                args.manifest.resolve(),
                confirm_run_id=args.run_id,
                confirm_group_id=args.group_id,
                confirm_control_group_id=args.control_group_id,
                confirm_batch_id=args.batch_id,
                source_fingerprint=args.source_fingerprint,
                tree_fingerprint=args.tree_fingerprint,
                image_fingerprint=args.image_fingerprint,
                config_fingerprint=args.config_fingerprint,
                checkpoint_path=args.output_dir / 'checkpoint.json',
            )
        atomic_write_json(args.output_dir / 'final-report.json', result)
        atomic_write_json(
            args.output_dir / 'tool-ledger.json',
            {'schema_version': 1, 'stages': result['stage_ledger']},
        )
        return result
    except BaseException:
        # The directory itself is durable proof that a run was attempted; never reuse it.
        raise


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
