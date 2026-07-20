from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / 'scripts' / 'run_catalog_canary_batch.py'
BUILDER_PATH = ROOT / 'scripts' / 'build_catalog_canary_requests.py'
FIXTURE = ROOT / 'mcp_server' / 'tests' / 'fixtures' / 'accept_tab_sanitized.json'


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load('catalog_canary_runner_4x2', RUNNER_PATH)
builder = _load('catalog_canary_builder_for_runner_4x2', BUILDER_PATH)


def _artifact(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    output = tmp_path / 'live-artifact'
    builder.build_live_canary(
        FIXTURE,
        output,
        run_id='20260720T010203Z-a',
        group_id='oracle-catalog-v2-canary-20260720T010203Z-a',
        control_group_id='oracle-catalog-v2-canary-20260720T010203Z-a-empty-control',
        batch_id='accept-tab-catalog-v2-canary-20260720T010203Z-a',
    )
    payload_path = output / 'accept-tab.payload.json'
    manifest_path = output / 'run-manifest.json'
    return (
        payload_path,
        manifest_path,
        json.loads(payload_path.read_text(encoding='utf-8')),
        json.loads(manifest_path.read_text(encoding='utf-8')),
    )


def _not_found(group_id: str, batch_id: str) -> dict[str, dict[str, Any]]:
    return {
        'status': {
            'group_id': group_id,
            'batch_id': batch_id,
            'batch_uuid': str(uuid.UUID(int=0)),
            'status': 'failed',
            'found': False,
            'error_code': None,
            'error_summary': 'batch status not found',
        },
        'manifest': {
            'group_id': group_id,
            'batch_id': batch_id,
            'found': False,
            'request_sha256': None,
            'catalog_sha256': None,
            'artifact_sha256': None,
            'manifest_sha256': None,
            'identity_schema_version': None,
            'canonicalization_version': None,
            'catalog_schema_version': None,
            'entity_count': 0,
            'edge_count': 0,
            'source_count': 0,
            'evidence_link_count': 0,
            'offset': 0,
            'limit': 100,
            'entities': [],
            'edges': [],
            'sources': [],
            'evidence_links': [],
            'error_code': 'manifest_mismatch',
            'error_message': 'manifest root not found',
        },
    }


class FakeTransport:
    def __init__(self, payload: dict[str, Any], request_sha: str, fail_at: str | None = None):
        self.payload = payload
        self.request_sha = request_sha
        self.fail_at = fail_at
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.plan_token = 'never-persist-this-plan-token'
        self.plan_uuid = '11111111-1111-1111-1111-111111111111'
        self.batch_uuid = '22222222-2222-2222-2222-222222222222'
        self.committed = False
        self.entity_uuids = [
            f'11111111-1111-1111-1111-{index + 1:012d}'
            for index in range(len(payload['entities']))
        ]
        self.edge_uuids = [
            f'22222222-2222-2222-2222-{index + 1:012d}'
            for index in range(len(payload['edges']))
        ]
        self.source_uuids = [
            f'33333333-3333-3333-3333-{index + 1:012d}'
            for index in range(len(payload['provenance']['sources']))
        ]
        self.evidence_uuids = [
            f'44444444-4444-4444-4444-{index + 1:012d}'
            for index in range(len(payload['provenance']['evidence_links']))
        ]

    def _manifest_response(self, limit: int) -> dict[str, Any]:
        p = self.payload
        provenance = p['provenance']
        return {
            'group_id': p['group_id'],
            'batch_id': p['batch_id'],
            'found': True,
            'request_sha256': self.request_sha,
            'catalog_sha256': p['catalog_sha256'],
            'artifact_sha256': 'a' * 64,
            'manifest_sha256': 'b' * 64,
            'identity_schema_version': p['identity_schema_version'],
            'canonicalization_version': 'catalog-c14n-v2',
            'catalog_schema_version': 'catalog-v2',
            'entity_count': len(p['entities']),
            'edge_count': len(p['edges']),
            'source_count': len(provenance['sources']),
            'evidence_link_count': len(provenance['evidence_links']),
            'offset': 0,
            'limit': limit,
            'entities': [
                {
                    'uuid': self.entity_uuids[index],
                    'entity_type': item['entity_type'],
                    'graph_key': item['graph_key'],
                    'content_sha256': item['content_sha256'],
                }
                for index, item in enumerate(p['entities'])
            ],
            'edges': [
                {
                    'uuid': self.edge_uuids[index],
                    'edge_type': item['edge_type'],
                    'edge_key': item['edge_key'],
                    'content_sha256': item['content_sha256'],
                }
                for index, item in enumerate(p['edges'])
            ],
            'sources': [
                {
                    'uuid': self.source_uuids[index],
                    'source_key': item['source_key'],
                    'content_sha256': item['content_sha256'],
                }
                for index, item in enumerate(provenance['sources'])
            ],
            'evidence_links': [
                {
                    'uuid': self.evidence_uuids[index],
                    'link_key': runner.evidence_link_key(
                        runner.CatalogEvidenceLink.model_validate(item)
                    ),
                    'content_sha256': runner.canonical_sha256(
                        runner.evidence_canonical_payload(
                            runner.CatalogEvidenceLink.model_validate(item)
                        )
                    ),
                }
                for index, item in enumerate(provenance['evidence_links'])
            ],
            'error_code': None,
            'error_message': None,
        }

    async def call(self, name: str, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, request))
        if name == self.fail_at:
            raise runner.RunnerError('synthetic_failure', f'{name} failed')
        p = self.payload
        provenance = p['provenance']
        counts = (len(p['entities']), len(p['edges']), len(provenance['sources']))
        if name == 'list_tools':
            return {'count': 28, 'names': sorted(runner.EXPECTED_MCP_TOOLS)}
        if name == 'get_status':
            return {'status': 'ok', 'message': 'ready'}
        if name == 'get_catalog_capabilities':
            return {
                'backend': 'neo4j',
                'identity_schema_version': 'catalog-v2',
                'connectivity': 'ok',
                'catalog_writes_enabled': True,
                'catalog_reads_enabled': True,
                'uuid_namespace_configured': True,
                'neo4j_indexes': 'ready',
                'embeddings': {'provider': 'fake', 'model': 'fake', 'ready': 'ready'},
                'features': {
                    'prepare_commit': True,
                    'manifests': True,
                    'manifest_verification': True,
                },
            }
        if name in {'get_catalog_ingest_status', 'get_catalog_batch_manifest'}:
            if not self.committed:
                absent = _not_found(request['group_id'], request['batch_id'])
                return absent['status' if name == 'get_catalog_ingest_status' else 'manifest']
            if name == 'get_catalog_ingest_status':
                return {
                    'group_id': p['group_id'],
                    'batch_id': p['batch_id'],
                    'batch_uuid': self.batch_uuid,
                    'status': 'committed',
                    'found': True,
                    'request_sha256': self.request_sha,
                    'catalog_sha256': p['catalog_sha256'],
                    'entity_count': len(p['entities']),
                    'edge_count': len(p['edges']),
                    'provenance_count': len(provenance['sources']) + len(provenance['evidence_links']),
                    'error_summary': '',
                    'error_code': None,
                }
            return self._manifest_response(request.get('limit', 100))
        if name == 'upsert_catalog_batch':
            return {
                'group_id': p['group_id'],
                'batch_id': p['batch_id'],
                'batch_uuid': self.batch_uuid,
                'dry_run': True,
                'atomic': True,
                'status': 'validating',
                'identity_schema_version': p['identity_schema_version'],
                'request_sha256': self.request_sha,
                'catalog_sha256': p['catalog_sha256'],
                'entity_created': counts[0],
                'edge_created': counts[1],
                'provenance_created': counts[2],
                'failed': 0,
                'rolled_back': 0,
                'error_code': None,
                'error_message': None,
            }
        if name == 'prepare_catalog_batch':
            return {
                'plan_token': self.plan_token,
                'plan_uuid': self.plan_uuid,
                'request_sha256': self.request_sha,
                'catalog_sha256': p['catalog_sha256'],
                'artifact_sha256': 'a' * 64,
                'identity_schema_version': p['identity_schema_version'],
                'expires_at': '2099-01-01T00:00:00Z',
                'entity_count': counts[0],
                'edge_count': counts[1],
                'source_count': counts[2],
                'evidence_link_count': len(provenance['evidence_links']),
                'projected_created': sum(counts) + len(provenance['evidence_links']),
                'projected_updated': 0,
                'projected_unchanged': 0,
                'error_code': None,
                'error_message': None,
            }
        if name == 'commit_prepared_catalog_batch':
            self.committed = True
            return {
                'plan_uuid': self.plan_uuid,
                'request_sha256': self.request_sha,
                'catalog_sha256': p['catalog_sha256'],
                'artifact_sha256': 'a' * 64,
                'state': 'COMMITTED',
                'entity_count': counts[0],
                'edge_count': counts[1],
                'source_count': counts[2],
                'evidence_link_count': len(provenance['evidence_links']),
                'batch_uuid': self.batch_uuid,
                'manifest_sha256': 'b' * 64,
                'committed_created': sum(counts),
                'error_code': None,
                'error_message': None,
            }
        if name == 'verify_catalog_batch':
            return {
                'group_id': p['group_id'],
                'batch_id': p['batch_id'],
                'found': True,
                'entities': {'expected': len(p['entities']), 'found': len(p['entities'])},
                'edges': {'expected': len(p['edges']), 'found': len(p['edges'])},
                'evidence': {
                    'expected': len(provenance['evidence_links']),
                    'found': len(provenance['evidence_links']),
                },
                'require_provenance': True,
                'manifest_sha256': 'b' * 64,
            }
        if name == 'resolve_typed_entities':
            return {
                'group_id': p['group_id'],
                'results': [
                    {
                        'index': index,
                        'entity_type': item['entity_type'],
                        'graph_key': item['graph_key'],
                        'status': 'found',
                        'found': True,
                        'uuid': self.entity_uuids[index],
                        'verified_type': item['entity_type'],
                        'has_name_embedding': True,
                        'content_sha256': item['content_sha256'],
                    }
                    for index, item in enumerate(p['entities'])
                ],
            }
        if name == 'resolve_typed_edges':
            entity_uuid = {
                (item['entity_type'], item['graph_key']): self.entity_uuids[index]
                for index, item in enumerate(p['entities'])
            }
            return {
                'group_id': p['group_id'],
                'results': [
                    {
                        'index': index,
                        'edge_type': item['edge_type'],
                        'edge_key': item['edge_key'],
                        'status': 'found',
                        'found': True,
                        'uuid': self.edge_uuids[index],
                        'verified_type': item['edge_type'],
                        'source_uuid': entity_uuid[(item['source_entity_type'], item['source_graph_key'])],
                        'target_uuid': entity_uuid[(item['target_entity_type'], item['target_graph_key'])],
                        'source_graph_key': item['source_graph_key'],
                        'target_graph_key': item['target_graph_key'],
                        'source_entity_type': item['source_entity_type'],
                        'target_entity_type': item['target_entity_type'],
                        'content_sha256': item['content_sha256'],
                        'has_fact_embedding': True,
                    }
                    for index, item in enumerate(p['edges'])
                ],
            }
        if name == 'get_catalog_evidence':
            item = runner.CatalogEvidenceLink.model_validate(provenance['evidence_links'][0])
            return {
                'group_id': p['group_id'],
                'target_kind': 'entity',
                'target_uuid': self.entity_uuids[0],
                'target_graph_key': p['entities'][0]['graph_key'],
                'found_target': True,
                'offset': 0,
                'limit': 100,
                'total': 1,
                'links': [
                    {
                        'uuid': self.evidence_uuids[0],
                        'link_key': runner.evidence_link_key(item),
                        'content_sha256': runner.canonical_sha256(
                            runner.evidence_canonical_payload(item)
                        ),
                        'target_kind': 'entity',
                        'target_uuid': self.entity_uuids[0],
                    }
                ],
            }
        if name == 'search_nodes':
            if request['group_ids'] == [p['group_id']] and self.committed:
                return {
                    'nodes': [
                        {
                            'uuid': self.entity_uuids[0],
                            'name': p['entities'][0]['graph_key'],
                            'group_id': p['group_id'],
                            'labels': ['Entity', p['entities'][0]['entity_type']],
                        }
                    ]
                }
            return {'nodes': []}
        if name == 'search_memory_facts':
            if request['group_ids'] == [p['group_id']] and self.committed:
                return {
                    'facts': [
                        {
                            'uuid': self.edge_uuids[0],
                            'edge_key': p['edges'][0]['edge_key'],
                            'name': p['edges'][0]['edge_type'],
                            'fact': p['edges'][0]['fact'],
                            'group_id': p['group_id'],
                        }
                    ]
                }
            return {'facts': []}
        raise AssertionError(f'unexpected tool: {name}')


@pytest.mark.asyncio
async def test_live_sequence_dry_run_before_prepare_and_token_only_commit(tmp_path: Path) -> None:
    payload_path, manifest_path, payload, manifest = _artifact(tmp_path)
    transport = FakeTransport(payload, manifest['request_sha256'])
    result = await runner.run_live_canary(
        transport,
        payload_path,
        manifest_path,
        confirm_group_id=manifest['group_id'],
        confirm_control_group_id=manifest['control_group_id'],
        confirm_batch_id=manifest['batch_id'],
        confirm_run_id=manifest['run_id'],
        source_fingerprint='a' * 64,
        tree_fingerprint='b' * 64,
    )
    names = [name for name, _ in transport.calls]
    assert names == runner.LIVE_CANARY_TOOL_SEQUENCE
    assert names.index('upsert_catalog_batch') < names.index('prepare_catalog_batch')
    dry_run = next(body for name, body in transport.calls if name == 'upsert_catalog_batch')
    assert dry_run == {**payload, 'dry_run': True}
    commit = next(body for name, body in transport.calls if name == 'commit_prepared_catalog_batch')
    assert set(commit) == {'plan_token', 'expected_request_sha256'}
    assert result['stage'] == 'FINALIZED'
    assert transport.plan_token not in json.dumps(result)
    assert 'resolve_typed_entities' in names and 'resolve_typed_edges' in names


@pytest.mark.parametrize('value', [False, None, 'true', 'false', 1, 0])
def test_dry_run_builder_rejects_anything_except_boolean_true(value: object) -> None:
    payload = {'identity_schema_version': 'catalog-v2'}
    with pytest.raises(runner.RunnerError, match='dry_run'):
        runner.build_live_dry_run_request(payload, dry_run=value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'fail_at',
    ['get_status', 'get_catalog_capabilities', 'get_catalog_ingest_status', 'upsert_catalog_batch'],
)
async def test_pre_prepare_failures_never_call_prepare_or_commit(
    tmp_path: Path, fail_at: str
) -> None:
    payload_path, manifest_path, payload, manifest = _artifact(tmp_path)
    transport = FakeTransport(payload, manifest['request_sha256'], fail_at=fail_at)
    with pytest.raises(runner.RunnerError):
        await runner.run_live_canary(
            transport,
            payload_path,
            manifest_path,
            confirm_group_id=manifest['group_id'],
            confirm_control_group_id=manifest['control_group_id'],
            confirm_batch_id=manifest['batch_id'],
            confirm_run_id=manifest['run_id'],
        source_fingerprint='a' * 64,
        tree_fingerprint='b' * 64,
        )
    names = [name for name, _ in transport.calls]
    assert 'prepare_catalog_batch' not in names
    assert 'commit_prepared_catalog_batch' not in names


def test_live_artifact_rejects_golden_and_confirmation_mismatch(tmp_path: Path) -> None:
    with pytest.raises(runner.RunnerError, match='golden|historical'):
        runner.validate_live_artifact(
            ROOT / 'catalog/canary-v2-requests-hardened/accept-tab.payload.json',
            ROOT / 'catalog/canary-v2-requests-hardened/manifest.json',
        )
    _, _, _, manifest = _artifact(tmp_path)
    with pytest.raises(runner.RunnerError, match='confirmation'):
        runner.validate_live_operator_confirmation(
            manifest,
            group_id='wrong',
            control_group_id=manifest['control_group_id'],
            batch_id=manifest['batch_id'],
        )


def test_checkpoint_requires_exact_dry_run_binding_and_contains_no_token(tmp_path: Path) -> None:
    path = tmp_path / 'checkpoint.json'
    binding = {'artifact_sha256': 'a' * 64, 'request_sha256': 'b' * 64}
    runner.write_live_checkpoint(path, runner.LiveStage.DRY_RUN_PASSED, binding)
    runner.require_live_resume(path, binding)
    with pytest.raises(runner.RunnerError, match='binding'):
        runner.require_live_resume(path, {**binding, 'request_sha256': 'c' * 64})
    with pytest.raises(runner.RunnerError, match='dry-run'):
        runner.write_live_checkpoint(path, runner.LiveStage.PREPARE_PASSED, binding)
    assert 'plan_token' not in path.read_text(encoding='utf-8')
