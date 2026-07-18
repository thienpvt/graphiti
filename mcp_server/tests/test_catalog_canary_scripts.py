from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / 'scripts' / 'run_catalog_canary_batch.py'
ARTIFACT_DIR = ROOT / 'catalog' / 'canary-v2-requests'
CATALOG_PATH = ROOT / 'catalog' / 'catalog.json'
CHECKPOINT_PATH = ROOT / 'catalog' / 'catalog.json.graphiti-canary-v2-state.json'


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_script(
    'catalog_canary_builder_under_test', ROOT / 'scripts' / 'build_catalog_canary_requests.py'
)
runner = _load_script('catalog_canary_runner_under_test', RUNNER_PATH)

EXPECTED_FILES = {
    'accept-tab.payload.json',
    'form-cfg.payload.json',
    'pre-auth-txn-type.payload.json',
    'trans-type.payload.json',
    'trans-type-class.payload.json',
    'documented-foreign-keys.payload.json',
}
COMMIT_TOOL_SEQUENCE = [
    'upsert_catalog_batch',
    'get_catalog_ingest_status',
    'verify_catalog_batch',
    'resolve_typed_entities',
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
}
MANIFEST_FIELDS = {
    'generated_at',
    'catalog_sha256',
    'target_group_id',
    'accept_tab_golden_server_request_sha256',
    'accept_tab_golden_match',
    'unique_totals',
    'entity_counts',
    'edge_counts',
    'quarantines',
    'batches',
}


def _artifact(name: str = 'accept-tab.payload.json') -> tuple[Path, bytes, dict[str, Any]]:
    path = ARTIFACT_DIR / name
    data = path.read_bytes()
    raw = runner.strict_json_loads(data)
    assert isinstance(raw, dict)
    return path, data, raw


def _copy_artifact(tmp_path: Path, name: str = 'accept-tab.payload.json') -> Path:
    source = ARTIFACT_DIR / name
    destination = tmp_path / name
    destination.write_bytes(source.read_bytes())
    return destination


def _args(payload: Path, checkpoint: Path, mode: str) -> argparse.Namespace:
    expected = runner.EXPECTED_BATCHES[runner.strict_json_load(payload)['batch_id']]
    return argparse.Namespace(
        mcp_url='http://offline.invalid/mcp',
        payload=payload,
        mode=mode,
        expected_artifact_sha256=expected['artifact_sha256'],
        expected_request_sha256=expected['request_sha256'],
        checkpoint=checkpoint,
    )


def _batch_response(request: Any, mode: str, item_status: str = 'unchanged') -> dict[str, Any]:
    assert request.provenance is not None
    entity_count = len(request.entities)
    edge_count = len(request.edges)
    provenance_count = len(request.provenance.sources)
    response = {
        'group_id': request.group_id,
        'batch_id': request.batch_id,
        'batch_uuid': 'offline-batch-uuid',
        'dry_run': mode == 'dry-run',
        'atomic': True,
        'status': 'validating' if mode == 'dry-run' else 'committed',
        'results': [
            {'index': index, 'status': item_status}
            for index in range(entity_count + edge_count + provenance_count)
        ],
        'entity_created': 0,
        'entity_updated': 0,
        'entity_unchanged': 0,
        'edge_created': 0,
        'edge_updated': 0,
        'edge_unchanged': 0,
        'provenance_created': 0,
        'provenance_updated': 0,
        'provenance_unchanged': 0,
        'failed': 0,
        'rolled_back': 0,
        'error_code': None,
        'error_message': None,
    }
    suffix = 'unchanged' if item_status == 'unchanged' else 'created'
    response[f'entity_{suffix}'] = entity_count
    response[f'edge_{suffix}'] = edge_count
    response[f'provenance_{suffix}'] = provenance_count
    return response


def _post_commit_responses(request: Any, request_sha256: str) -> dict[str, dict[str, Any]]:
    assert request.provenance is not None
    representative_entity = request.entities[0]
    representative_edge = request.edges[0]
    return {
        'get_catalog_ingest_status': {
            'group_id': request.group_id,
            'batch_id': request.batch_id,
            'batch_uuid': 'offline-batch-uuid',
            'status': 'committed',
            'request_sha256': request_sha256,
            'catalog_sha256': request.catalog_sha256,
            'entity_count': len(request.entities),
            'edge_count': len(request.edges),
            'provenance_count': len(request.provenance.sources),
            'created_at': None,
            'updated_at': None,
            'committed_at': None,
            'error_summary': '',
            'error_code': None,
        },
        'verify_catalog_batch': {
            'group_id': request.group_id,
            'batch_id': request.batch_id,
            'results': [],
            'entities': {'expected': len(request.entities), 'found': len(request.entities)},
            'edges': {'expected': len(request.edges), 'found': len(request.edges)},
            'missing': [],
            'anomalies': [],
            'require_provenance': True,
            'missing_provenance': [],
            'error_code': None,
            'error_message': None,
        },
        'resolve_typed_entities': {
            'group_id': request.group_id,
            'results': [
                {
                    'index': index,
                    'entity_type': entity.entity_type,
                    'graph_key': entity.graph_key,
                    'status': 'found',
                    'found': True,
                    'uuid': f'offline-entity-{index}',
                    'labels': [entity.entity_type],
                    'verified_type': entity.entity_type,
                    'has_name_embedding': True,
                    'content_sha256': entity.content_sha256,
                    'generic_duplicates': [],
                    'typed_duplicates': [],
                    'anomalies': [],
                    'error_code': None,
                    'error_message': None,
                }
                for index, entity in enumerate(request.entities)
            ],
        },
        'search_nodes': {'nodes': [{'name': representative_entity.graph_key}]},
        'search_memory_facts': {
            'facts': [
                {
                    'edge_key': representative_edge.edge_key,
                    'name': representative_edge.edge_type,
                    'fact': representative_edge.fact,
                }
            ]
        },
    }


def _install_fake_mcp(
    monkeypatch: pytest.MonkeyPatch,
    responder: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> tuple[list[str], list[tuple[str, dict[str, Any]]]]:
    urls: list[str] = []
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeTransport:
        async def __aenter__(self) -> tuple[object, object, Callable[[], str]]:
            return object(), object(), lambda: 'offline-session'

        async def __aexit__(self, *_args: object) -> None:
            return None

    def fake_streamable_http_client(url: str) -> FakeTransport:
        urls.append(url)
        return FakeTransport()

    class FakeClientSession:
        def __init__(self, _read: object, _write: object):
            pass

        async def __aenter__(self) -> FakeClientSession:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def initialize(self) -> None:
            return None

        async def call_tool(self, name: str, arguments: dict[str, Any]) -> SimpleNamespace:
            calls.append((name, copy.deepcopy(arguments)))
            structured = responder(name, arguments)
            return SimpleNamespace(
                content=[],
                structuredContent={'result': structured},
                isError=False,
            )

    monkeypatch.setattr(runner, 'streamable_http_client', fake_streamable_http_client)
    monkeypatch.setattr(runner, 'ClientSession', FakeClientSession)
    return urls, calls


def _write_dry_run_receipt(
    payload: Path,
    request: Any,
    artifact_sha256: str,
    request_sha256: str,
    *,
    receipt_artifact_sha256: str | None = None,
) -> Path:
    structured = _batch_response(request, 'dry-run')
    protocol = {
        'content': [],
        'structuredContent': {'result': structured},
        'isError': False,
    }
    wrapper = runner._response_wrapper(
        payload_path=payload,
        mode='dry-run',
        artifact_sha256=receipt_artifact_sha256 or artifact_sha256,
        artifact_size=payload.stat().st_size,
        server_request_sha256=request_sha256,
        protocol_response=protocol,
    )
    receipt = runner.response_path_for(payload, 'dry-run')
    runner.atomic_write_json(receipt, wrapper)
    return receipt


def _expected_commit_calls(
    raw: dict[str, Any], request: Any, request_sha256: str
) -> list[tuple[str, dict[str, Any]]]:
    transport_request = copy.deepcopy(raw)
    transport_request['dry_run'] = False
    transport_request['request_sha256'] = request_sha256
    representative_entity = request.entities[0]
    representative_edge = request.edges[0]
    return [
        ('upsert_catalog_batch', {'request': transport_request}),
        (
            'get_catalog_ingest_status',
            {'request': {'group_id': request.group_id, 'batch_id': request.batch_id}},
        ),
        (
            'verify_catalog_batch',
            {
                'request': {
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
            },
        ),
        (
            'resolve_typed_entities',
            {
                'request': {
                    'group_id': request.group_id,
                    'entities': [
                        {'entity_type': item.entity_type, 'graph_key': item.graph_key}
                        for item in request.entities
                    ],
                    'graph_keys': None,
                }
            },
        ),
        (
            'search_nodes',
            {
                'query': representative_entity.graph_key,
                'group_ids': [request.group_id],
                'max_nodes': 10,
                'entity_types': [representative_entity.entity_type],
                'center_node_uuid': None,
            },
        ),
        (
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
        ),
    ]


@pytest.mark.parametrize(
    ('data', 'message'),
    [
        (b'\xef\xbb\xbf{}', 'UTF-8 BOM is forbidden'),
        (b'{"a":1,"a":2}', 'duplicate JSON key: a'),
        (b'{"a":NaN}', 'non-finite JSON number: NaN'),
    ],
)
def test_builder_strict_json_rejects_bom_duplicates_and_nonfinite(
    data: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        builder.strict_json_bytes(data, 'test.json')


@pytest.mark.parametrize(
    ('data', 'code'),
    [
        (b'\xef\xbb\xbf{}', 'utf8_bom'),
        (b'{"a":1,"a":2}', 'duplicate_json_key'),
        (b'{"a":Infinity}', 'non_finite_json'),
    ],
)
def test_runner_strict_json_rejects_bom_duplicates_and_nonfinite(data: bytes, code: str) -> None:
    with pytest.raises(runner.RunnerError) as error:
        runner.strict_json_loads(data)
    assert error.value.code == code


def test_unknown_top_level_field_is_rejected() -> None:
    _, _, raw = _artifact()
    raw['unexpected'] = True
    with pytest.raises(ValueError, match='top-level fields must be'):
        builder.validate_request(raw)
    with pytest.raises(runner.RunnerError) as error:
        runner._validate_raw_field_sets(raw)
    assert error.value.code == 'field_set_mismatch'


@pytest.mark.parametrize(
    ('path', 'match'),
    [
        (('entities', 0), r'\$\.entities\[0\]: unknown fields'),
        (('edges', 0), r'\$\.edges\[0\]: unknown fields'),
        (('provenance',), r'\$\.provenance: unknown fields'),
        (('provenance', 'sources', 0), r'\$\.provenance\.sources\[0\]: unknown fields'),
        (
            ('provenance', 'entity_targets', 0),
            r'\$\.provenance\.entity_targets\[0\]: unknown fields',
        ),
        (
            ('provenance', 'edge_targets', 0),
            r'\$\.provenance\.edge_targets\[0\]: unknown fields',
        ),
    ],
)
def test_unknown_nested_fields_are_rejected(path: tuple[str | int, ...], match: str) -> None:
    _, _, raw = _artifact()
    target: Any = raw
    for part in path:
        target = target[part]
    target['unexpected'] = True

    with pytest.raises(ValueError, match=match):
        builder.validate_request(raw)
    with pytest.raises(runner.RunnerError) as error:
        runner._validate_raw_field_sets(raw)
    assert error.value.code == 'field_set_mismatch'


def test_runner_source_has_no_prohibited_write_tool_call_literals() -> None:
    tree = ast.parse(RUNNER_PATH.read_text(encoding='utf-8'))
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert PROHIBITED_LEGACY_TOOLS.isdisjoint(string_literals)


def test_artifact_set_fields_canonical_bytes_hashes_and_manifest_counts() -> None:
    manifest = runner.strict_json_load(ARTIFACT_DIR / 'manifest.json')
    assert set(manifest) == MANIFEST_FIELDS
    assert set(path.name for path in ARTIFACT_DIR.glob('*.payload.json')) == EXPECTED_FILES
    assert {entry['path'].rsplit('/', 1)[-1] for entry in manifest['batches']} == EXPECTED_FILES
    assert set(runner.EXPECTED_BATCHES) == {entry['batch_id'] for entry in manifest['batches']}
    assert manifest['catalog_sha256'] == builder.EXPECTED_CATALOG_SHA256
    assert manifest['target_group_id'] == builder.GROUP_ID
    assert runner.DEFAULT_CHECKPOINT == CHECKPOINT_PATH

    for entry in manifest['batches']:
        path = ROOT / entry['path']
        data = path.read_bytes()
        raw = runner.strict_json_loads(data)
        assert set(raw) == builder.PAYLOAD_FIELDS == runner.ARTIFACT_FIELDS
        assert not builder.TRANSIENT_FIELDS & set(raw)
        assert data.endswith(b'\n') and not data.endswith(b'\n\n')
        assert builder.canonical_bytes(raw) == runner.canonical_artifact_bytes(raw) == data
        assert hashlib.sha256(data).hexdigest() == entry['artifact_sha256']
        model, request_sha256 = builder.validate_request(raw)
        assert model.batch_id == entry['batch_id']
        assert request_sha256 == entry['server_request_sha256']
        provenance = raw['provenance']
        assert entry['counts'] == {
            'entities': len(raw['entities']),
            'edges': len(raw['edges']),
            'provenance_sources': len(provenance['sources']),
            'provenance_entity_targets': len(provenance['entity_targets']),
            'provenance_edge_targets': len(provenance['edge_targets']),
            'provenance_links': len(provenance['sources'])
            * (len(provenance['entity_targets']) + len(provenance['edge_targets'])),
        }


def test_artifact_unique_counts_golden_document_target_and_quarantine_contract() -> None:
    manifest = runner.strict_json_load(ARTIFACT_DIR / 'manifest.json')
    unique_entities: set[tuple[str, str]] = set()
    unique_edges: set[tuple[str, str]] = set()
    entity_counts: Counter[str] = Counter()
    edge_counts: Counter[str] = Counter()
    all_bytes = b''
    selected_relationships: set[str] = set()

    for name in EXPECTED_FILES:
        _, data, raw = _artifact(name)
        all_bytes += data
        for entity in raw['entities']:
            identity = (entity['entity_type'], entity['graph_key'])
            if identity not in unique_entities:
                unique_entities.add(identity)
                entity_counts[identity[0]] += 1
        for edge in raw['edges']:
            identity = (edge['edge_type'], edge['edge_key'])
            assert identity not in unique_edges
            unique_edges.add(identity)
            edge_counts[identity[0]] += 1
            if edge['edge_type'] == 'DocumentedBy':
                assert (edge['target_entity_type'], edge['target_graph_key']) == (
                    'DictionaryDocument',
                    builder.DOCUMENT_KEY,
                )
            if edge['edge_type'] == 'ForeignKeyTo':
                selected_relationships.add(edge['attributes']['documented_relationship_id'])

    assert manifest['unique_totals'] == {'entities': 38, 'edges': 85}
    assert len(unique_entities) == 38 and len(unique_edges) == 85
    assert entity_counts == builder.EXPECTED_ENTITY_COUNTS == Counter(manifest['entity_counts'])
    assert edge_counts == builder.EXPECTED_EDGE_COUNTS == Counter(manifest['edge_counts'])
    assert selected_relationships == set(builder.SELECTED_FKS)
    assert manifest['quarantines'] == sorted(builder.QUARANTINES)
    assert builder.MALFORMED_DOCUMENT_ID.encode() not in all_bytes
    assert all(value.encode() not in all_bytes for value in builder.QUARANTINES)
    accept = runner.EXPECTED_BATCHES['canary-v2::accept-tab']
    assert manifest['accept_tab_golden_match'] is True
    assert (
        manifest['accept_tab_golden_server_request_sha256']
        == builder.ACCEPT_TAB_GOLDEN_REQUEST_SHA256
        == accept['request_sha256']
    )


def test_builder_replay_is_noop_and_does_not_touch_checkpoint() -> None:
    tracked = [ARTIFACT_DIR / name for name in EXPECTED_FILES] + [ARTIFACT_DIR / 'manifest.json']
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked}
    checkpoint_before = (
        (True, CHECKPOINT_PATH.read_bytes()) if CHECKPOINT_PATH.exists() else (False, b'')
    )

    manifest = builder.build(CATALOG_PATH, ARTIFACT_DIR)

    assert manifest == runner.strict_json_load(ARTIFACT_DIR / 'manifest.json')
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked} == before
    checkpoint_after = (
        (True, CHECKPOINT_PATH.read_bytes()) if CHECKPOINT_PATH.exists() else (False, b'')
    )
    assert checkpoint_after == checkpoint_before


def test_validate_artifact_accepts_every_approved_artifact() -> None:
    for batch_id, expected in runner.EXPECTED_BATCHES.items():
        result = runner.validate_artifact(
            ARTIFACT_DIR / expected['filename'],
            expected_artifact_sha256=expected['artifact_sha256'],
            expected_request_sha256=expected['request_sha256'],
        )
        artifact_bytes, raw, request, artifact_sha256, request_sha256 = result
        assert raw['batch_id'] == request.batch_id == batch_id
        assert artifact_sha256 == hashlib.sha256(artifact_bytes).hexdigest()
        assert request_sha256 == expected['request_sha256']


def test_atomic_checkpoint_append_preserves_prior_content(tmp_path: Path) -> None:
    checkpoint = tmp_path / 'catalog.json.graphiti-canary-v2-state.json'
    original = {
        'schema_version': 9,
        'operator': {'name': 'keep'},
        'attempts': [{'status': 'prior'}],
    }
    digest = runner.atomic_write_json(checkpoint, original)
    assert digest == hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert checkpoint.read_bytes().endswith(b'\n')

    attempt = {'status': 'new', 'nested': {'value': 1}}
    runner.append_checkpoint_attempt(checkpoint, attempt)
    attempt['nested']['value'] = 2

    stored = runner.strict_json_load(checkpoint)
    assert stored == {
        'schema_version': 9,
        'operator': {'name': 'keep'},
        'attempts': [{'status': 'prior'}, {'status': 'new', 'nested': {'value': 1}}],
    }


@pytest.mark.asyncio
async def test_dry_run_uses_exact_mcp_envelope_persists_response_and_appends_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _copy_artifact(tmp_path)
    checkpoint = tmp_path / 'catalog.json.graphiti-canary-v2-state.json'
    runner.atomic_write_json(
        checkpoint,
        {'schema_version': 3, 'operator_note': 'preserve', 'attempts': [{'status': 'prior'}]},
    )
    _, raw, request, artifact_sha256, request_sha256 = runner.validate_artifact(payload)
    structured = _batch_response(request, 'dry-run')
    urls, calls = _install_fake_mcp(monkeypatch, lambda _name, _arguments: structured)

    result = await runner.execute(_args(payload, checkpoint, 'dry-run'))

    expected_transport = copy.deepcopy(raw)
    expected_transport['dry_run'] = True
    assert urls == ['http://offline.invalid/mcp']
    assert calls == [('upsert_catalog_batch', {'request': expected_transport})]
    assert result['status'] == 'dry_run_passed'
    response_path = runner.response_path_for(payload, 'dry-run')
    assert response_path.name == 'accept-tab.dry-run.response.json'
    wrapper = runner.strict_json_load(response_path)
    assert wrapper == {
        'schema_version': 1,
        'tool': 'upsert_catalog_batch',
        'mode': 'dry-run',
        'payload_path': payload.name,
        'artifact_sha256': artifact_sha256,
        'artifact_size': payload.stat().st_size,
        'server_request_sha256': request_sha256,
        'recorded_at': wrapper['recorded_at'],
        'protocol_response': {
            'content': [],
            'structuredContent': {'result': structured},
            'isError': False,
        },
    }
    checkpoint_raw = runner.strict_json_load(checkpoint)
    assert checkpoint_raw['schema_version'] == 3
    assert checkpoint_raw['operator_note'] == 'preserve'
    assert checkpoint_raw['attempts'][0] == {'status': 'prior'}
    assert checkpoint_raw['attempts'][-1]['status'] == 'dry_run_passed'
    assert (
        checkpoint_raw['attempts'][-1]['response_sha256']
        == hashlib.sha256(response_path.read_bytes()).hexdigest()
    )


@pytest.mark.asyncio
async def test_commit_refuses_missing_receipt_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _copy_artifact(tmp_path)
    checkpoint = tmp_path / 'catalog.json.graphiti-canary-v2-state.json'
    urls, calls = _install_fake_mcp(monkeypatch, lambda _name, _arguments: {})

    with pytest.raises(runner.RunnerError) as error:
        await runner.execute(_args(payload, checkpoint, 'commit'))

    assert error.value.code == 'missing_dry_run_receipt'
    assert urls == [] and calls == []
    attempt = runner.strict_json_load(checkpoint)['attempts'][-1]
    assert attempt['status'] == 'failed_before_call'
    assert attempt['error_code'] == 'missing_dry_run_receipt'


@pytest.mark.asyncio
async def test_commit_refuses_dry_run_artifact_mismatch_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _copy_artifact(tmp_path)
    checkpoint = tmp_path / 'catalog.json.graphiti-canary-v2-state.json'
    _, _, request, artifact_sha256, request_sha256 = runner.validate_artifact(payload)
    _write_dry_run_receipt(
        payload,
        request,
        artifact_sha256,
        request_sha256,
        receipt_artifact_sha256='0' * 64,
    )
    urls, calls = _install_fake_mcp(monkeypatch, lambda _name, _arguments: {})

    with pytest.raises(runner.RunnerError) as error:
        await runner.execute(_args(payload, checkpoint, 'commit'))

    assert error.value.code == 'dry_run_artifact_mismatch'
    assert urls == [] and calls == []
    attempt = runner.strict_json_load(checkpoint)['attempts'][-1]
    assert attempt['status'] == 'failed_before_call'
    assert attempt['error_code'] == 'dry_run_artifact_mismatch'


@pytest.mark.asyncio
async def test_transport_ambiguity_calls_once_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _copy_artifact(tmp_path)
    checkpoint = tmp_path / 'catalog.json.graphiti-canary-v2-state.json'
    call_count = 0

    def ambiguous(_name: str, _arguments: dict[str, Any]) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        raise TimeoutError('offline ambiguous outcome')

    urls, calls = _install_fake_mcp(monkeypatch, ambiguous)

    with pytest.raises(runner.RunnerError) as error:
        await runner.execute(_args(payload, checkpoint, 'dry-run'))

    assert error.value.code == 'transport_outcome_uncertain'
    assert call_count == 1
    assert urls == ['http://offline.invalid/mcp']
    assert len(calls) == 1 and calls[0][0] == 'upsert_catalog_batch'
    attempt = runner.strict_json_load(checkpoint)['attempts'][-1]
    assert attempt['status'] == 'uncertain'
    assert attempt['error_code'] == 'transport_outcome_uncertain'
    assert not runner.response_path_for(payload, 'dry-run').exists()


@pytest.mark.asyncio
async def test_commit_success_and_idempotent_replay_use_exact_gates_and_no_prohibited_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _copy_artifact(tmp_path)
    checkpoint = tmp_path / 'catalog.json.graphiti-canary-v2-state.json'
    _, raw, request, artifact_sha256, request_sha256 = runner.validate_artifact(payload)
    _write_dry_run_receipt(payload, request, artifact_sha256, request_sha256)
    post_commit = _post_commit_responses(request, request_sha256)

    def first_responder(name: str, _arguments: dict[str, Any]) -> dict[str, Any]:
        if name == 'upsert_catalog_batch':
            return _batch_response(request, 'commit', 'created')
        return post_commit[name]

    _, first_calls = _install_fake_mcp(monkeypatch, first_responder)
    first = await runner.execute(_args(payload, checkpoint, 'commit'))

    assert first['status'] == 'commit_verified'
    assert first_calls == _expected_commit_calls(raw, request, request_sha256)
    assert [name for name, _ in first_calls] == COMMIT_TOOL_SEQUENCE
    assert PROHIBITED_LEGACY_TOOLS.isdisjoint(name for name, _ in first_calls)
    commit_wrapper = runner.strict_json_load(runner.response_path_for(payload, 'commit'))
    assert set(commit_wrapper['post_commit']) == set(COMMIT_TOOL_SEQUENCE[1:])
    assert all(
        protocol['structuredContent'].keys() == {'result'}
        for protocol in commit_wrapper['post_commit'].values()
    )

    def replay_responder(name: str, _arguments: dict[str, Any]) -> dict[str, Any]:
        if name == 'upsert_catalog_batch':
            return _batch_response(request, 'commit', 'unchanged')
        return post_commit[name]

    _, replay_calls = _install_fake_mcp(monkeypatch, replay_responder)
    replay = await runner.execute(_args(payload, checkpoint, 'commit'))

    assert replay['status'] == 'commit_verified'
    assert replay_calls == _expected_commit_calls(raw, request, request_sha256)
    attempts = runner.strict_json_load(checkpoint)['attempts']
    assert [attempt['status'] for attempt in attempts] == ['commit_verified', 'commit_verified']
    assert attempts[0]['idempotent_replay'] is False
    assert attempts[1]['idempotent_replay'] is True
    assert attempts[1]['counts'] == {
        'entity_created': 0,
        'entity_updated': 0,
        'entity_unchanged': len(request.entities),
        'edge_created': 0,
        'edge_updated': 0,
        'edge_unchanged': len(request.edges),
        'provenance_created': 0,
        'provenance_updated': 0,
        'provenance_unchanged': len(request.provenance.sources),
        'failed': 0,
        'rolled_back': 0,
    }

# ---------------------------------------------------------------------------
# Phase 5 Wave 0 RED scaffolds (IDEN-13 / DOCS-06) — GREEN in 05-03
# Historical ACCEPT_TAB golden is NOT hardened authority (D-11).
# Never execute run_catalog_canary_batch.py live (D-10).
# ---------------------------------------------------------------------------

HARDENED_ARTIFACT_DIR = ROOT / 'catalog' / 'canary-v2-requests-hardened'
PREFERRED_HARDENED_SEQUENCE = [
    'prepare_catalog_batch',
    'commit_prepared_catalog_batch',
    'get_catalog_ingest_status',
    'verify_catalog_batch',
]


def test_historical_inventory_and_digests_preserved():
    """IDEN-13 / DOCS-06: full historical inventory/digests/attempt count preserved."""
    pytest.fail('05 not implemented: historical_inventory / historical_bytes_unchanged')


def test_historical_bytes_unchanged_and_attempt_count():
    """IDEN-13: historical artifact bytes and exact checkpoint attempt count unchanged."""
    pytest.fail('05 not implemented: historical_bytes_unchanged')


def test_hardened_manifest_schema_strict():
    """DOCS-06: strict versioned hardened fixture/manifest schema."""
    pytest.fail('05 not implemented: hardened_manifest_schema')


def test_offline_receipt_schema_strict():
    """DOCS-06: strict offline receipt schema for prepare/commit sequence."""
    pytest.fail('05 not implemented: offline_receipt_schema')


def test_offline_checkpoint_schema_strict():
    """DOCS-06: strict offline checkpoint schema; hardened attempt count zero."""
    pytest.fail('05 not implemented: offline_checkpoint_schema')


def test_sanitized_hardened_artifacts_no_production_content():
    """DOCS-06: recursive leakage scan bans production source/secrets/tokens/payloads."""
    pytest.fail('05 not implemented: sanitized_hardened / no_production_content')


def test_prepare_catalog_batch_commit_prepared_sequence_preferred():
    """DOCS-06 / D-09: preferred offline sequence is prepare + commit_prepared."""
    assert 'prepare_catalog_batch' in PREFERRED_HARDENED_SEQUENCE
    assert 'commit_prepared_catalog_batch' in PREFERRED_HARDENED_SEQUENCE
    pytest.fail('05 not implemented: prepare_catalog_batch + commit_prepared sequence')


def test_historical_accept_tab_golden_not_hardened_authority():
    """IDEN-13 / D-11: historical ACCEPT_TAB golden SHA is not hardened authority."""
    pytest.fail('05 not implemented: historical ACCEPT_TAB not hardened authority')


def test_offline_canary_no_external_side_effect():
    """DOCS-06: pure offline — no network/DB/MCP/LLM/queue/embed side effects."""
    pytest.fail('05 not implemented: no_external_side_effect spies')


def test_phase5_gate_never_shells_canary_runner():
    """D-10: Phase 5 gate/static audit must not shell run_catalog_canary_batch.py."""
    gate = ROOT / 'mcp_server' / 'tests' / 'catalog_phase5_gate_runner.py'
    if not gate.is_file():
        pytest.fail('05 not implemented: catalog_phase5_gate_runner missing for shell ban')
    src = gate.read_text(encoding='utf-8')
    assert 'canary_executed' in src
