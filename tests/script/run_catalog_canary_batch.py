from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'scripts/run_catalog_canary_batch.py'
BUILDER = ROOT / 'scripts/build_catalog_canary_requests.py'
FIXTURE = ROOT / 'mcp_server/tests/fixtures/accept_tab_sanitized.json'


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('corrective_runner', RUNNER)
builder = load('corrective_builder', BUILDER)


def artifact(tmp_path: Path):
    directory = tmp_path / 'artifact'
    manifest = builder.build_live_canary(
        FIXTURE,
        directory,
        run_id='20260720T010203Z-a',
        group_id='oracle-catalog-v2-canary-20260720T010203Z-a',
        control_group_id='oracle-catalog-v2-canary-20260720T010203Z-a-empty-control',
        batch_id='accept-tab-catalog-v2-canary-20260720T010203Z-a',
    )
    payload_path = directory / builder.LIVE_PAYLOAD_NAME
    return (
        payload_path,
        directory / builder.LIVE_MANIFEST_NAME,
        json.loads(payload_path.read_text(encoding='utf-8')),
        manifest,
    )


def uid(kind: int, index: int = 0) -> str:
    return str(uuid.UUID(int=kind * 1000 + index + 1))


def attestor(**_kwargs: Any) -> dict[str, Any]:
    return {
        'source_head': '1' * 40,
        'source_map_sha256': '2' * 64,
        'runner_sha256': '3' * 64,
        'source_files': 5,
    }


def execution_attestor(**_kwargs: Any) -> dict[str, Any]:
    return {
        'execution_map_sha256': '4' * 64,
        'execution_files': 3,
        'execution_digest_method': runner.EXECUTION_DIGEST_METHOD,
    }


LIVE_KW = {
    'source_head': '1' * 40,
    'source_map_sha256': '2' * 64,
    'runner_sha256': '3' * 64,
    'execution_map_sha256': '4' * 64,
    'source_attestor': attestor,
    'execution_attestor': execution_attestor,
}


class ContractFake:
    MODELS = {
        'upsert_catalog_batch': runner.UpsertCatalogBatchRequest,
        'prepare_catalog_batch': runner.PrepareCatalogBatchRequest,
        'commit_prepared_catalog_batch': runner.CommitPreparedCatalogBatchRequest,
        'resolve_typed_entities': runner.ResolveTypedEntitiesRequest,
        'resolve_typed_edges': runner.ResolveTypedEdgesRequest,
        'verify_catalog_batch': runner.VerifyCatalogBatchRequest,
        'get_catalog_batch_manifest': runner.GetCatalogBatchManifestRequest,
        'get_catalog_evidence': runner.GetCatalogEvidenceRequest,
    }

    def __init__(
        self,
        payload: dict[str, Any],
        request_sha: str,
        ambiguous: bool = False,
        reconcile_status: str = 'committed',
    ):
        self.p = payload
        self.request_sha = request_sha
        self.ambiguous = ambiguous
        self.reconcile_status = reconcile_status
        self.committed = False
        self.commit_calls = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.token = 'never-persist-this-plan-token'
        self.plan_uuid = uid(9)
        self.batch_uuid = uid(8)
        self.entities = [uid(1, i) for i in range(len(payload['entities']))]
        self.edges = [uid(2, i) for i in range(len(payload['edges']))]
        self.sources = [uid(3, i) for i in range(len(payload['provenance']['sources']))]
        self.evidence = [uid(4, i) for i in range(len(payload['provenance']['evidence_links']))]
        self.artifact_sha = 'a' * 64
        self.membership = self._membership()
        body = runner.catalog_manifest.build_manifest_body_from_membership(
            group_id=payload['group_id'],
            batch_id=payload['batch_id'],
            request_sha256=request_sha,
            catalog_sha256=payload['catalog_sha256'],
            membership=self.membership,
            artifact_sha256=self.artifact_sha,
        )
        self.manifest_sha = runner.catalog_manifest.manifest_sha256(
            runner.catalog_manifest.serialize_manifest_body(body)
        )

    def _membership(self):
        p = self.p
        return {
            'entities': [
                {
                    'uuid': self.entities[i],
                    'entity_type': x['entity_type'],
                    'graph_key': x['graph_key'],
                    'content_sha256': x['content_sha256'],
                    'projected_status': 'created',
                }
                for i, x in enumerate(p['entities'])
            ],
            'edges': [
                {
                    'uuid': self.edges[i],
                    'edge_type': x['edge_type'],
                    'edge_key': x['edge_key'],
                    'content_sha256': x['content_sha256'],
                    'projected_status': 'created',
                }
                for i, x in enumerate(p['edges'])
            ],
            'sources': [
                {
                    'uuid': self.sources[i],
                    'source_key': x['source_key'],
                    'content_sha256': x['content_sha256'],
                    'projected_status': 'created',
                }
                for i, x in enumerate(p['provenance']['sources'])
            ],
            'evidence_links': [
                {
                    'uuid': self.evidence[i],
                    'link_key': runner.evidence_link_key(
                        runner.CatalogEvidenceLink.model_validate(x)
                    ),
                    'content_sha256': runner.canonical_sha256(
                        runner.evidence_canonical_payload(
                            runner.CatalogEvidenceLink.model_validate(x)
                        )
                    ),
                }
                for i, x in enumerate(p['provenance']['evidence_links'])
            ],
        }

    def absent(self, request: dict[str, Any], manifest: bool):
        if manifest:
            return {
                'group_id': request['group_id'],
                'batch_id': request['batch_id'],
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
                'offset': request.get('offset', 0),
                'limit': request.get('limit', 100),
                'entities': [],
                'edges': [],
                'sources': [],
                'evidence_links': [],
                'error_code': 'manifest_mismatch',
                'error_message': 'manifest root not found',
            }
        return {
            'group_id': request['group_id'],
            'batch_id': request['batch_id'],
            'batch_uuid': self.batch_uuid,
            'status': 'failed',
            'found': False,
            'request_sha256': None,
            'catalog_sha256': None,
            'entity_count': 0,
            'edge_count': 0,
            'provenance_count': 0,
            'created_at': None,
            'updated_at': None,
            'committed_at': None,
            'error_summary': 'batch status not found',
            'error_code': None,
        }

    def manifest_page(self, request: dict[str, Any]):
        offset, limit = request['offset'], request['limit']
        return {
            'group_id': self.p['group_id'],
            'batch_id': self.p['batch_id'],
            'found': True,
            'request_sha256': self.request_sha,
            'catalog_sha256': self.p['catalog_sha256'],
            'artifact_sha256': self.artifact_sha,
            'manifest_sha256': self.manifest_sha,
            'identity_schema_version': 'catalog-v2',
            'canonicalization_version': runner.CANONICALIZATION_VERSION,
            'catalog_schema_version': runner.CATALOG_SCHEMA_VERSION,
            'entity_count': len(self.membership['entities']),
            'edge_count': len(self.membership['edges']),
            'source_count': len(self.membership['sources']),
            'evidence_link_count': len(self.membership['evidence_links']),
            'offset': offset,
            'limit': limit,
            **{key: rows[offset : offset + limit] for key, rows in self.membership.items()},
            'error_code': None,
            'error_message': None,
        }

    def evidence_page(self, request: dict[str, Any]):
        entity = request.get('entity_target')
        edge = request.get('edge_target')
        kind = 'entity' if entity else 'edge'
        target = entity or edge
        assert isinstance(target, dict)
        key = target['graph_key'] if entity else target['edge_key']
        item_type = target['entity_type'] if entity else target['edge_type']
        rows = self.p['entities'] if entity else self.p['edges']
        uuids = self.entities if entity else self.edges
        target_uuid = uuids[
            next(
                i
                for i, x in enumerate(rows)
                if (x[f'{kind}_type'], x['graph_key' if entity else 'edge_key']) == (item_type, key)
            )
        ]
        links = []
        for i, raw in enumerate(self.p['provenance']['evidence_links']):
            link = runner.CatalogEvidenceLink.model_validate(raw)
            matches = (
                entity
                and link.entity_target
                and link.entity_target.entity_type == item_type
                and link.entity_target.graph_key == key
            ) or (
                edge
                and link.edge_target
                and link.edge_target.edge_type == item_type
                and link.edge_target.edge_key == key
            )
            if matches:
                links.append(
                    {
                        'uuid': self.evidence[i],
                        'link_key': runner.evidence_link_key(link),
                        'content_sha256': runner.canonical_sha256(
                            runner.evidence_canonical_payload(link)
                        ),
                        'source_uuid': self.sources[0],
                        'target_kind': kind,
                        'target_uuid': target_uuid,
                        'evidence_kind': link.evidence_kind,
                        'extractor_name': link.extractor_name,
                        'extractor_version': link.extractor_version,
                        'rule_id': link.rule_id,
                        'confidence': link.confidence,
                        'excerpt': None,
                    }
                )
        offset, limit = request['offset'], request['limit']
        return {
            'group_id': self.p['group_id'],
            'target_kind': kind,
            'target_uuid': target_uuid,
            'target_graph_key': key if entity else None,
            'target_edge_key': key if edge else None,
            'found_target': True,
            'offset': offset,
            'limit': limit,
            'total': len(links),
            'links': links[offset : offset + limit],
            'error_code': None,
            'error_message': None,
        }

    async def call(self, name: str, request: dict[str, Any]):
        self.calls.append((name, request))
        if name in self.MODELS:
            self.MODELS[name].model_validate(request, strict=True)
        if name in {'get_catalog_batch_manifest', 'get_catalog_evidence'}:
            assert request['limit'] <= 2
        assert 'request' not in request
        p, provenance = self.p, self.p['provenance']
        total = len(p['entities']) + len(p['edges']) + len(provenance['sources'])
        if name == 'list_tools':
            return {'count': 28, 'names': sorted(runner.EXPECTED_MCP_TOOLS)}
        if name == 'get_status':
            return {'status': 'ok'}
        if name == 'get_catalog_capabilities':
            return {
                'package_version': 'test',
                'backend': 'neo4j',
                'connectivity': 'ok',
                'catalog_writes_enabled': True,
                'catalog_reads_enabled': True,
                'uuid_namespace_configured': True,
                'namespace_fingerprint': '0123456789abcdef',
                'identity_schema_version': 'catalog-v2',
                'canonicalization_version': runner.CANONICALIZATION_VERSION,
                'catalog_schema_version': runner.CATALOG_SCHEMA_VERSION,
                'entity_types': [],
                'entity_prefixes': {},
                'edge_types': [],
                'endpoint_map': {},
                'limits': {'configured': {'max_page_size': 2}, 'hard': {'max_page_size': 500}},
                'embeddings': {'ready': 'ready'},
                'neo4j_indexes': 'ready',
                'features': {
                    'prepare_commit': True,
                    'manifests': True,
                    'manifest_verification': True,
                },
            }
        if name == 'get_catalog_ingest_status':
            if not self.committed or request['group_id'] != p['group_id']:
                return self.absent(request, False)
            if self.ambiguous and self.reconcile_status == 'absent':
                return self.absent(request, False)
            status = self.reconcile_status if self.ambiguous else 'committed'
            return {
                'group_id': p['group_id'],
                'batch_id': p['batch_id'],
                'batch_uuid': self.batch_uuid,
                'status': status,
                'found': True,
                'request_sha256': self.request_sha,
                'catalog_sha256': p['catalog_sha256'],
                'entity_count': len(p['entities']),
                'edge_count': len(p['edges']),
                'provenance_count': len(provenance['sources']) + len(provenance['evidence_links']),
                'error_summary': 'synthetic failure' if status == 'failed' else '',
                'error_code': None,
            }
        if name == 'get_catalog_batch_manifest':
            if not self.committed or request['group_id'] != p['group_id']:
                return self.absent(request, True)
            return self.manifest_page(request)
        if name == 'search_nodes':
            if not self.committed or request['group_ids'] != [p['group_id']]:
                return {'nodes': []}
            return {
                'nodes': [
                    {
                        'uuid': self.entities[i],
                        'name': x['graph_key'],
                        'group_id': p['group_id'],
                        'labels': ['Entity', x['entity_type']],
                    }
                    for i, x in enumerate(p['entities'])
                    if x['graph_key'] == request['query']
                ]
            }
        if name == 'search_memory_facts':
            if not self.committed or request['group_ids'] != [p['group_id']]:
                return {'facts': []}
            eu = {
                (x['entity_type'], x['graph_key']): self.entities[i]
                for i, x in enumerate(p['entities'])
            }
            return {
                'facts': [
                    {
                        'uuid': self.edges[i],
                        'name': x['edge_type'],
                        'fact': x['fact'],
                        'group_id': p['group_id'],
                        'source_node_uuid': eu[(x['source_entity_type'], x['source_graph_key'])],
                        'target_node_uuid': eu[(x['target_entity_type'], x['target_graph_key'])],
                        'attributes': {'edge_key': x['edge_key']},
                    }
                    for i, x in enumerate(p['edges'])
                    if x['fact'] == request['query']
                ]
            }
        if name == 'upsert_catalog_batch':
            results = (
                [
                    {
                        'index': i,
                        'status': 'created',
                        'uuid': self.entities[i],
                        'content_sha256': x['content_sha256'],
                        'graph_key': x['graph_key'],
                        'entity_type': x['entity_type'],
                    }
                    for i, x in enumerate(p['entities'])
                ]
                + [
                    {
                        'index': len(p['entities']) + i,
                        'status': 'created',
                        'uuid': self.edges[i],
                        'content_sha256': x['content_sha256'],
                        'edge_key': x['edge_key'],
                        'edge_type': x['edge_type'],
                    }
                    for i, x in enumerate(p['edges'])
                ]
                + [
                    {
                        'index': len(p['entities']) + len(p['edges']) + i,
                        'status': 'created',
                        'uuid': self.sources[i],
                        'content_sha256': x['content_sha256'],
                        'graph_key': x['source_key'],
                    }
                    for i, x in enumerate(provenance['sources'])
                ]
            )
            return {
                'group_id': p['group_id'],
                'batch_id': p['batch_id'],
                'batch_uuid': self.batch_uuid,
                'dry_run': True,
                'atomic': True,
                'status': 'validating',
                'identity_schema_version': 'catalog-v2',
                'canonicalization_version': runner.CANONICALIZATION_VERSION,
                'request_sha256': self.request_sha,
                'catalog_sha256': p['catalog_sha256'],
                'results': results,
                'entity_created': len(p['entities']),
                'edge_created': len(p['edges']),
                'provenance_created': len(provenance['sources']),
            }
        if name == 'prepare_catalog_batch':
            return {
                'plan_token': self.token,
                'plan_uuid': self.plan_uuid,
                'request_sha256': self.request_sha,
                'catalog_sha256': p['catalog_sha256'],
                'artifact_sha256': self.artifact_sha,
                'identity_schema_version': 'catalog-v2',
                'expires_at': '2099-01-01T00:00:00Z',
                'entity_count': len(p['entities']),
                'edge_count': len(p['edges']),
                'source_count': len(provenance['sources']),
                'evidence_link_count': len(provenance['evidence_links']),
                'projected_created': total,
                'projected_updated': 0,
                'projected_unchanged': 0,
            }
        if name == 'commit_prepared_catalog_batch':
            self.commit_calls += 1
            self.committed = True
            if self.ambiguous:
                raise TimeoutError('synthetic')
            return {
                'plan_uuid': self.plan_uuid,
                'request_sha256': self.request_sha,
                'catalog_sha256': p['catalog_sha256'],
                'artifact_sha256': self.artifact_sha,
                'state': 'COMMITTED',
                'entity_count': len(p['entities']),
                'edge_count': len(p['edges']),
                'source_count': len(provenance['sources']),
                'evidence_link_count': len(provenance['evidence_links']),
                'batch_uuid': self.batch_uuid,
                'manifest_sha256': self.manifest_sha,
                'committed_created': total,
                'committed_updated': 0,
                'committed_unchanged': 0,
            }
        if name == 'resolve_typed_entities':
            return {
                'group_id': p['group_id'],
                'results': [
                    {
                        'index': i,
                        'entity_type': x['entity_type'],
                        'graph_key': x['graph_key'],
                        'status': 'found',
                        'found': True,
                        'uuid': self.entities[i],
                        'labels': ['Entity', x['entity_type']],
                        'verified_type': x['entity_type'],
                        'has_name_embedding': True,
                        'content_sha256': x['content_sha256'],
                    }
                    for i, x in enumerate(p['entities'])
                ],
            }
        if name == 'resolve_typed_edges':
            eu = {
                (x['entity_type'], x['graph_key']): self.entities[i]
                for i, x in enumerate(p['entities'])
            }
            return {
                'group_id': p['group_id'],
                'results': [
                    {
                        'index': i,
                        'edge_type': x['edge_type'],
                        'edge_key': x['edge_key'],
                        'status': 'found',
                        'found': True,
                        'uuid': self.edges[i],
                        'verified_type': x['edge_type'],
                        'source_uuid': eu[(x['source_entity_type'], x['source_graph_key'])],
                        'target_uuid': eu[(x['target_entity_type'], x['target_graph_key'])],
                        'source_graph_key': x['source_graph_key'],
                        'target_graph_key': x['target_graph_key'],
                        'source_entity_type': x['source_entity_type'],
                        'target_entity_type': x['target_entity_type'],
                        'content_sha256': x['content_sha256'],
                        'has_fact_embedding': True,
                    }
                    for i, x in enumerate(p['edges'])
                ],
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
                'manifest_sha256': self.manifest_sha,
            }
        if name == 'get_catalog_evidence':
            return self.evidence_page(request)
        raise AssertionError(name)


async def run_case(
    tmp_path: Path,
    ambiguous: bool = False,
    reconcile_status: str = 'committed',
):
    payload_path, manifest_path, payload, manifest = artifact(tmp_path)
    fake = ContractFake(payload, manifest['request_sha256'], ambiguous, reconcile_status)
    output = tmp_path / 'result'
    result = await runner.run_live_canary(
        fake,
        payload_path,
        manifest_path,
        confirm_run_id=manifest['run_id'],
        confirm_group_id=manifest['group_id'],
        confirm_control_group_id=manifest['control_group_id'],
        confirm_batch_id=manifest['batch_id'],
        output_dir=output,
        **LIVE_KW,
    )
    return result, fake, output


@pytest.mark.asyncio
async def test_full_success_contract_validating_fake(tmp_path: Path) -> None:
    result, fake, output = await run_case(tmp_path)
    names = [name for name, _ in fake.calls]
    assert names.index('upsert_catalog_batch') < names.index('prepare_catalog_batch')
    assert names.index('resolve_typed_entities') < names.index('verify_catalog_batch')
    assert result['classification'] == 'PASSED'
    assert result['replay'] == 'skipped'
    assert result['namespace_fingerprint'] == '0123456789abcdef'
    assert result['execution_map_sha256'] == '4' * 64
    assert result['execution_files'] == 3
    assert result['execution_digest_method'] == runner.EXECUTION_DIGEST_METHOD
    report = (output / 'final-report.json').read_text(encoding='utf-8')
    ledger = json.loads((output / 'tool-ledger.json').read_text(encoding='utf-8'))
    acceptance = json.loads(
        (output / 'terminal-artifacts-manifest.json').read_text(encoding='utf-8')
    )
    assert fake.token not in report
    assert [x['ordinal'] for x in ledger['entries']] == list(range(1, len(ledger['entries']) + 1))
    assert acceptance['schema_version'] == runner.TERMINAL_ACCEPTANCE_SCHEMA_VERSION
    assert acceptance['tool_call_count'] == result['tool_call_count']
    assert acceptance['final_ordinal'] == result['final_ordinal']
    assert acceptance['tool_ledger_sha256'] == runner.sha256_bytes(
        (output / 'tool-ledger.json').read_bytes()
    )
    assert acceptance['final_report_sha256'] == runner.sha256_bytes(
        (output / 'final-report.json').read_bytes()
    )
    paginated = [
        body
        for name, body in fake.calls
        if name in {'get_catalog_batch_manifest', 'get_catalog_evidence'}
    ]
    assert paginated
    assert {body['limit'] for body in paginated} == {2}


@pytest.mark.asyncio
async def test_ambiguous_commit_reconciles_once_without_retry(tmp_path: Path) -> None:
    result, fake, _ = await run_case(tmp_path, ambiguous=True)
    assert result['classification'] == 'PASSED'
    assert fake.commit_calls == 1
    index = [name for name, _ in fake.calls].index('commit_prepared_catalog_batch')
    assert [name for name, _ in fake.calls[index + 1 : index + 3]] == [
        'get_catalog_ingest_status',
        'get_catalog_batch_manifest',
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['absent', 'failed', 'writing'])
async def test_ambiguous_commit_unresolved_status_fails_durably(
    tmp_path: Path, status: str
) -> None:
    with pytest.raises(runner.RunnerError):
        await run_case(tmp_path, ambiguous=True, reconcile_status=status)
    output = tmp_path / 'result'
    report = json.loads((output / 'final-report.json').read_text(encoding='utf-8'))
    ledger = json.loads((output / 'tool-ledger.json').read_text(encoding='utf-8'))
    names = [entry['tool'] for entry in ledger['entries']]
    assert report['classification'] == 'FAILED_AFTER_COMMIT'
    assert names.count('commit_prepared_catalog_batch') == 1
    assert names.count('prepare_catalog_batch') == 1
    assert names[-1] == 'get_catalog_ingest_status'


def _canonical_fact(
    *,
    uuid: str,
    group_id: str,
    edge_type: str,
    edge_key: str,
    source: str = 'src-1',
    target: str = 'tgt-1',
    top_level_edge_key: str | None = None,
    attributes: dict | None = None,
) -> dict:
    row = {
        'uuid': uuid,
        'name': edge_type,
        'fact': 'fact',
        'group_id': group_id,
        'source_node_uuid': source,
        'target_node_uuid': target,
        'attributes': {'edge_key': edge_key} if attributes is None else attributes,
    }
    if top_level_edge_key is not None:
        row['edge_key'] = top_level_edge_key
    return row


def test_strict_search_rejects_foreign_group_and_typed_aliases() -> None:
    group_id = 'fresh-group'
    graph_key = 'TABLE::FE::A'
    entity_type = 'Table'
    edge_key = 'contains|TABLE::FE::A|COLUMN::FE::A.ID'
    edge_type = 'Contains'
    expected = uid(1)
    alias = uid(2)
    node = {
        'uuid': expected,
        'name': graph_key,
        'group_id': group_id,
        'labels': ['Entity', entity_type],
    }
    fact = _canonical_fact(uuid=expected, group_id=group_id, edge_type=edge_type, edge_key=edge_key)
    runner._validate_node_search_strict(
        {'nodes': [node, {**node, 'uuid': alias, 'name': 'unrelated'}]},
        group_id=group_id,
        expected_uuid=expected,
        entity_type=entity_type,
        graph_key=graph_key,
    )
    runner._validate_fact_search_strict(
        {
            'facts': [
                fact,
                _canonical_fact(
                    uuid=alias,
                    group_id=group_id,
                    edge_type=edge_type,
                    edge_key='unrelated',
                ),
            ]
        },
        group_id=group_id,
        expected_uuid=expected,
        edge_type=edge_type,
        edge_key=edge_key,
        source_node_uuid='src-1',
        target_node_uuid='tgt-1',
    )
    for rows, validator, kwargs in (
        (
            [node, {**node, 'uuid': alias}],
            runner._validate_node_search_strict,
            {'entity_type': entity_type, 'graph_key': graph_key},
        ),
        (
            [fact, {**fact, 'uuid': alias}],
            runner._validate_fact_search_strict,
            {
                'edge_type': edge_type,
                'edge_key': edge_key,
                'source_node_uuid': 'src-1',
                'target_node_uuid': 'tgt-1',
            },
        ),
    ):
        key = 'nodes' if validator is runner._validate_node_search_strict else 'facts'
        with pytest.raises(runner.RunnerError, match='alias'):
            validator({key: rows}, group_id=group_id, expected_uuid=expected, **kwargs)
        with pytest.raises(runner.RunnerError, match='foreign'):
            validator(
                {key: [{**rows[0], 'group_id': 'foreign'}]},
                group_id=group_id,
                expected_uuid=expected,
                **kwargs,
            )


def test_gate9_canonical_nested_edge_key_and_regressions() -> None:
    group_id = 'g'
    edge_key = 'CONTAINS::A->B'
    edge_type = 'Contains'
    expected = uid(1)
    source, target = uid(3), uid(4)
    base = _canonical_fact(
        uuid=expected,
        group_id=group_id,
        edge_type=edge_type,
        edge_key=edge_key,
        source=source,
        target=target,
    )
    # 1. canonical nested
    runner._validate_fact_search_strict(
        {'facts': [base]},
        group_id=group_id,
        expected_uuid=expected,
        edge_type=edge_type,
        edge_key=edge_key,
        source_node_uuid=source,
        target_node_uuid=target,
    )
    # 2. exact UUID once + unrelated same-group extras ok
    extra = _canonical_fact(
        uuid=uid(9),
        group_id=group_id,
        edge_type='Other',
        edge_key='other-key',
        source=uid(10),
        target=uid(11),
    )
    runner._validate_fact_search_strict(
        {'facts': [base, extra]},
        group_id=group_id,
        expected_uuid=expected,
        edge_type=edge_type,
        edge_key=edge_key,
        source_node_uuid=source,
        target_node_uuid=target,
    )
    # 3. missing nested identity
    with pytest.raises(runner.RunnerError, match='alias|attributes'):
        runner._validate_fact_search_strict(
            {'facts': [{**base, 'attributes': {}}]},
            group_id=group_id,
            expected_uuid=expected,
            edge_type=edge_type,
            edge_key=edge_key,
            source_node_uuid=source,
            target_node_uuid=target,
        )
    # 4. conflicting top/nested
    with pytest.raises(runner.RunnerError, match='conflict'):
        runner._validate_fact_search_strict(
            {
                'facts': [
                    _canonical_fact(
                        uuid=expected,
                        group_id=group_id,
                        edge_type=edge_type,
                        edge_key=edge_key,
                        source=source,
                        target=target,
                        top_level_edge_key='DIFFERENT',
                    )
                ]
            },
            group_id=group_id,
            expected_uuid=expected,
            edge_type=edge_type,
            edge_key=edge_key,
            source_node_uuid=source,
            target_node_uuid=target,
        )
    # 5. wrong type
    with pytest.raises(runner.RunnerError, match='alias'):
        runner._validate_fact_search_strict(
            {'facts': [{**base, 'name': 'ForeignKeyTo'}]},
            group_id=group_id,
            expected_uuid=expected,
            edge_type=edge_type,
            edge_key=edge_key,
            source_node_uuid=source,
            target_node_uuid=target,
        )
    # 6. wrong endpoint
    with pytest.raises(runner.RunnerError, match='alias'):
        runner._validate_fact_search_strict(
            {'facts': [{**base, 'source_node_uuid': uid(99)}]},
            group_id=group_id,
            expected_uuid=expected,
            edge_type=edge_type,
            edge_key=edge_key,
            source_node_uuid=source,
            target_node_uuid=target,
        )
    # 7. foreign group
    with pytest.raises(runner.RunnerError, match='foreign'):
        runner._validate_fact_search_strict(
            {'facts': [{**base, 'group_id': 'foreign'}]},
            group_id=group_id,
            expected_uuid=expected,
            edge_type=edge_type,
            edge_key=edge_key,
            source_node_uuid=source,
            target_node_uuid=target,
        )
    # 8. duplicate expected UUID
    with pytest.raises(runner.RunnerError, match='duplicated|absent'):
        runner._validate_fact_search_strict(
            {'facts': [base, {**base}]},
            group_id=group_id,
            expected_uuid=expected,
            edge_type=edge_type,
            edge_key=edge_key,
            source_node_uuid=source,
            target_node_uuid=target,
        )
    # 9. unrelated-only fails
    with pytest.raises(runner.RunnerError, match='absent|duplicated|alias'):
        runner._validate_fact_search_strict(
            {'facts': [extra]},
            group_id=group_id,
            expected_uuid=expected,
            edge_type=edge_type,
            edge_key=edge_key,
            source_node_uuid=source,
            target_node_uuid=target,
        )
    # top-level-only does not satisfy nested contract
    with pytest.raises(runner.RunnerError, match='alias|attributes'):
        runner._validate_fact_search_strict(
            {
                'facts': [
                    {
                        'uuid': expected,
                        'name': edge_type,
                        'group_id': group_id,
                        'source_node_uuid': source,
                        'target_node_uuid': target,
                        'edge_key': edge_key,
                        'attributes': {},
                    }
                ]
            },
            group_id=group_id,
            expected_uuid=expected,
            edge_type=edge_type,
            edge_key=edge_key,
            source_node_uuid=source,
            target_node_uuid=target,
        )


def test_gate9_live_formatter_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from datetime import datetime, timezone
    from types import ModuleType, SimpleNamespace

    graphiti = ModuleType('graphiti_core')
    edges_mod: Any = ModuleType('graphiti_core.edges')
    nodes_mod: Any = ModuleType('graphiti_core.nodes')
    edges_mod.EntityEdge = object
    nodes_mod.EntityNode = object
    models = ModuleType('models')
    response_types_mod: Any = ModuleType('models.response_types')
    response_types_mod.EdgeResult = lambda **kwargs: kwargs
    response_types_mod.NodeResult = lambda **kwargs: kwargs
    edges = edges_mod
    nodes = nodes_mod
    response_types = response_types_mod
    for name, module in {
        'graphiti_core': graphiti,
        'graphiti_core.edges': edges,
        'graphiti_core.nodes': nodes,
        'models': models,
        'models.response_types': response_types,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    path = ROOT / 'mcp_server' / 'src' / 'utils' / 'formatting.py'
    spec = importlib.util.spec_from_file_location('formatting_live_compat', path)
    assert spec is not None and spec.loader is not None
    formatting = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(formatting)
    edge_key = 'CONTAINS::T->C'
    edge = SimpleNamespace(
        uuid=uid(1),
        source_node_uuid=uid(2),
        target_node_uuid=uid(3),
        name='Contains',
        fact='t contains c',
        group_id='g',
        created_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        valid_at=None,
        invalid_at=None,
        attributes={'edge_key': edge_key, 'fixture': 'x'},
    )
    fact = formatting.format_fact_result(edge)
    assert fact['attributes']['edge_key'] == edge_key
    assert 'edge_key' not in fact or fact.get('edge_key') is None
    runner._validate_fact_search_strict(
        {'facts': [fact]},
        group_id='g',
        expected_uuid=edge.uuid,
        edge_type='Contains',
        edge_key=edge_key,
        source_node_uuid=edge.source_node_uuid,
        target_node_uuid=edge.target_node_uuid,
    )


def test_embedding_waiver_matrix_and_capability_hash_immutable() -> None:
    ready = runner.evaluate_embedding_readiness({'provider': 'openai', 'ready': 'ready'})
    assert ready['waiver_applied'] is False
    assert ready['observed_readiness'] == 'ready'
    waived = runner.evaluate_embedding_readiness(
        {'provider': 'openai', 'ready': 'unknown'},
        allow_unknown_embedding_provider='openai',
    )
    assert waived['waiver_applied'] is True
    assert waived['observed_readiness'] == 'unknown'
    assert waived['observed_provider'] == 'openai'
    with pytest.raises(runner.RunnerError, match='unknown'):
        runner.evaluate_embedding_readiness({'provider': 'openai', 'ready': 'unknown'})
    with pytest.raises(runner.RunnerError, match='unknown'):
        runner.evaluate_embedding_readiness(
            {'provider': 'ollama', 'ready': 'unknown'},
            allow_unknown_embedding_provider='openai',
        )
    with pytest.raises(runner.RunnerError, match='error'):
        runner.evaluate_embedding_readiness({'provider': 'openai', 'ready': 'error'})
    with pytest.raises(runner.RunnerError, match='openai'):
        runner.evaluate_embedding_readiness(
            {'provider': 'openai', 'ready': 'unknown'},
            allow_unknown_embedding_provider='ollama',
        )


def test_raw_capability_sha_uses_unmodified_server_dict() -> None:
    """Capability SHA is canonical over raw server dict; raw structure stays unchanged."""
    raw = {
        'package_version': 'test',
        'backend': 'neo4j',
        'connectivity': 'ok',
        'catalog_writes_enabled': True,
        'catalog_reads_enabled': True,
        'uuid_namespace_configured': True,
        'namespace_fingerprint': '0123456789abcdef',
        'identity_schema_version': 'catalog-v2',
        'canonicalization_version': runner.CANONICALIZATION_VERSION,
        'catalog_schema_version': runner.CATALOG_SCHEMA_VERSION,
        'entity_types': [],
        'entity_prefixes': {},
        'edge_types': [],
        'endpoint_map': {},
        'limits': {'configured': {'max_page_size': 2}, 'hard': {'max_page_size': 500}},
        'embeddings': {'provider': 'openai', 'ready': 'unknown', 'extra_raw_field': True},
        'neo4j_indexes': 'ready',
        'features': {
            'prepare_commit': True,
            'manifests': True,
            'manifest_verification': True,
        },
        'raw_only_key': 'must-survive',
    }
    snapshot = copy.deepcopy(raw)
    expected_sha = runner.canonical_sha256(raw)
    # Live path invariants: hash raw before validation/policy; no mutation.
    assert runner.canonical_sha256(raw) == expected_sha
    model = runner.CatalogCapabilitiesResponse.model_validate(raw, strict=True)
    assert raw == snapshot
    assert runner.canonical_sha256(raw) == expected_sha
    # Projection SHA must not replace raw SHA (extra raw fields change the hash).
    projection = model.model_dump(mode='json')
    assert runner.canonical_sha256(projection) != expected_sha
    policy = runner.evaluate_embedding_readiness(
        dict(model.embeddings or {}),
        allow_unknown_embedding_provider='openai',
    )
    assert policy['waiver_applied'] is True
    assert raw == snapshot
    assert runner.canonical_sha256(raw) == expected_sha
    assert 'raw_only_key' in raw and raw['embeddings']['extra_raw_field'] is True


def test_tool_ledger_validation_rejects_corrupt_ordinals() -> None:
    good = [
        {'ordinal': 1, 'tool': 'a', 'stage': 'S', 'success': True, 'error_code': None},
        {'ordinal': 2, 'tool': 'b', 'stage': 'S', 'success': False, 'error_code': 'boom'},
    ]
    meta = runner.validate_tool_ledger(good)
    assert meta == {'tool_call_count': 2, 'final_ordinal': 2, 'tool_count': 28}
    # missing error_code key
    with pytest.raises(runner.RunnerError, match='keys'):
        runner.validate_tool_ledger([{'ordinal': 1, 'tool': 'a', 'stage': 'S', 'success': True}])
    # success with non-null error_code
    with pytest.raises(runner.RunnerError, match='error_code'):
        runner.validate_tool_ledger(
            [
                {
                    'ordinal': 1,
                    'tool': 'a',
                    'stage': 'S',
                    'success': True,
                    'error_code': 'nope',
                }
            ]
        )
    # failure with empty error_code
    with pytest.raises(runner.RunnerError, match='error_code'):
        runner.validate_tool_ledger(
            [
                {
                    'ordinal': 1,
                    'tool': 'a',
                    'stage': 'S',
                    'success': False,
                    'error_code': '',
                }
            ]
        )
    # duplicate
    with pytest.raises(runner.RunnerError, match='ordinal'):
        runner.validate_tool_ledger(
            [
                {
                    'ordinal': 1,
                    'tool': 'a',
                    'stage': 'S',
                    'success': True,
                    'error_code': None,
                },
                {
                    'ordinal': 1,
                    'tool': 'b',
                    'stage': 'S',
                    'success': True,
                    'error_code': None,
                },
            ]
        )
    # gap / missing
    with pytest.raises(runner.RunnerError, match='ordinal'):
        runner.validate_tool_ledger(
            [
                {
                    'ordinal': 1,
                    'tool': 'a',
                    'stage': 'S',
                    'success': True,
                    'error_code': None,
                },
                {
                    'ordinal': 3,
                    'tool': 'b',
                    'stage': 'S',
                    'success': True,
                    'error_code': None,
                },
            ]
        )
    # reorder
    with pytest.raises(runner.RunnerError, match='ordinal'):
        runner.validate_tool_ledger(
            [
                {
                    'ordinal': 2,
                    'tool': 'a',
                    'stage': 'S',
                    'success': True,
                    'error_code': None,
                },
                {
                    'ordinal': 1,
                    'tool': 'b',
                    'stage': 'S',
                    'success': True,
                    'error_code': None,
                },
            ]
        )
    # non-int
    with pytest.raises(runner.RunnerError, match='ordinal'):
        runner.validate_tool_ledger(
            [
                {
                    'ordinal': 1.0,  # type: ignore[dict-item]
                    'tool': 'a',
                    'stage': 'S',
                    'success': True,
                    'error_code': None,
                }
            ]
        )
    # report metadata mismatch
    with pytest.raises(runner.RunnerError, match='tool_call_count|final_ordinal|tool_count'):
        runner.validate_report_ledger_metadata(
            {'tool_count': 28, 'tool_call_count': 1, 'final_ordinal': 2},
            meta,
        )
    with pytest.raises(runner.RunnerError, match='tool_count'):
        runner.validate_report_ledger_metadata(
            {'tool_count': 27, 'tool_call_count': 2, 'final_ordinal': 2},
            meta,
        )


def test_execution_boundary_rejects_standalone_and_unapproved() -> None:
    ok = runner.validate_execution_command(
        [
            'docker',
            'compose',
            '-f',
            runner.COMPOSE_BASE_FILE,
            '-f',
            runner.COMPOSE_OVERRIDE_FILE,
            'up',
            '-d',
            'neo4j',
            'graphiti-mcp',
        ]
    )
    assert ok['ok'] is True
    assert ok['files'] == list(runner.REQUIRED_COMPOSE_FILES)
    assert ok['services'] == ['neo4j', 'graphiti-mcp']
    for bad in (
        ['docker', 'run', '--rm', 'neo4j'],
        ['docker', 'build', '.'],
        ['docker', 'pull', 'neo4j'],
        ['docker', 'exec', 'x', 'sha256sum', '/app'],
        ['docker-compose', '-f', runner.COMPOSE_BASE_FILE, 'up', 'neo4j'],
        ['docker', 'compose', 'run', 'graphiti-mcp'],
        ['docker', 'compose', 'build'],
        [
            'docker',
            'compose',
            '-f',
            runner.COMPOSE_BASE_FILE,
            'up',
            'neo4j',
        ],
        [
            'docker',
            'compose',
            '-f',
            runner.COMPOSE_OVERRIDE_FILE,
            '-f',
            runner.COMPOSE_BASE_FILE,
            'up',
            'neo4j',
        ],
        [
            'docker',
            'compose',
            '-f',
            runner.COMPOSE_BASE_FILE,
            '-f',
            runner.COMPOSE_OVERRIDE_FILE,
            '-f',
            runner.COMPOSE_BASE_FILE,
            'up',
            'neo4j',
        ],
        [
            'docker',
            'compose',
            '-f',
            'docker-compose.yml',
            '-f',
            runner.COMPOSE_OVERRIDE_FILE,
            'up',
            'neo4j',
        ],
        [
            'docker',
            'compose',
            '-f',
            runner.COMPOSE_BASE_FILE,
            '-f',
            runner.COMPOSE_OVERRIDE_FILE,
            'up',
            'mcp',
        ],
        [
            'docker',
            'compose',
            '-f',
            runner.COMPOSE_BASE_FILE,
            '-f',
            runner.COMPOSE_OVERRIDE_FILE,
            'up',
            'redis',
        ],
        [
            'docker',
            'compose',
            '--project-name',
            'x',
            '-f',
            runner.COMPOSE_BASE_FILE,
            '-f',
            runner.COMPOSE_OVERRIDE_FILE,
            'up',
            'neo4j',
        ],
        ['bash', '-c', 'docker compose up'],
        'docker compose up',
    ):
        with pytest.raises(runner.RunnerError) as ei:
            runner.validate_execution_command(bad)  # type: ignore[arg-type]
        assert ei.value.code == 'execution_boundary_violation'
    # Fixed host execution authority map only; no arbitrary-path helper.
    assert not hasattr(runner, 'host_side_source_digest')
    assert runner.HOST_EXECUTION_AUTHORITY_PATHS == (
        runner.COMPOSE_BASE_FILE,
        runner.COMPOSE_OVERRIDE_FILE,
        'mcp_server/config/config-docker-neo4j.yaml',
    )
    ok = runner.attest_host_compose_argv(
        [
            'docker',
            'compose',
            '-f',
            runner.COMPOSE_BASE_FILE,
            '-f',
            runner.COMPOSE_OVERRIDE_FILE,
            'up',
            '-d',
            'neo4j',
            'graphiti-mcp',
        ]
    )
    assert ok['ok'] is True


@pytest.mark.asyncio
async def test_prepare_embedding_failure_never_commits(tmp_path: Path) -> None:
    payload_path, manifest_path, payload, manifest = artifact(tmp_path)

    class PrepareFail(ContractFake):
        async def call(self, name: str, request: dict):
            if name == 'prepare_catalog_batch':
                self.calls.append((name, request))
                raise runner.RunnerError('prepare_failed', 'embedding provider failed')
            return await super().call(name, request)

    fake = PrepareFail(payload, manifest['request_sha256'])
    output = tmp_path / 'result'
    with pytest.raises(runner.RunnerError, match='prepare|embedding'):
        await runner.run_live_canary(
            fake,
            payload_path,
            manifest_path,
            confirm_run_id=manifest['run_id'],
            confirm_group_id=manifest['group_id'],
            confirm_control_group_id=manifest['control_group_id'],
            confirm_batch_id=manifest['batch_id'],
            output_dir=output,
            **LIVE_KW,
        )
    names = [n for n, _ in fake.calls]
    assert 'commit_prepared_catalog_batch' not in names
    assert names.count('prepare_catalog_batch') == 1
    report = __import__('json').loads((output / 'final-report.json').read_text(encoding='utf-8'))
    assert report['classification'] == 'FAILED_BEFORE_COMMIT'
    assert report.get('prepare_functional_embedding_proof') is False
    assert (output / 'terminal-artifacts-manifest.json').is_file()


@pytest.mark.asyncio
async def test_openai_unknown_waiver_records_observed_state(tmp_path: Path) -> None:
    payload_path, manifest_path, payload, manifest = artifact(tmp_path)

    class OpenAIUnknown(ContractFake):
        async def call(self, name: str, request: dict[str, Any]) -> dict[str, Any]:
            body: dict[str, Any] = dict(await super().call(name, request))
            if name == 'get_catalog_capabilities':
                body['embeddings'] = {
                    'provider': 'openai',
                    'model': 'text-embedding-3-small',
                    'ready': 'unknown',
                }
            return body

    fake = OpenAIUnknown(payload, manifest['request_sha256'])
    # without waiver fails
    with pytest.raises(runner.RunnerError, match='unknown|capability'):
        await runner.run_live_canary(
            fake,
            payload_path,
            manifest_path,
            confirm_run_id=manifest['run_id'],
            confirm_group_id=manifest['group_id'],
            confirm_control_group_id=manifest['control_group_id'],
            confirm_batch_id=manifest['batch_id'],
            **LIVE_KW,
        )
    # with waiver succeeds and records observed unknown + waiver_applied
    fake2 = OpenAIUnknown(payload, manifest['request_sha256'])
    output = tmp_path / 'result-waived'
    result = await runner.run_live_canary(
        fake2,
        payload_path,
        manifest_path,
        confirm_run_id=manifest['run_id'],
        confirm_group_id=manifest['group_id'],
        confirm_control_group_id=manifest['control_group_id'],
        confirm_batch_id=manifest['batch_id'],
        output_dir=output,
        allow_unknown_embedding_provider='openai',
        **LIVE_KW,
    )
    assert result['classification'] == 'PASSED'
    assert result['embedding_readiness'] == 'unknown'
    assert result['embedding_provider'] == 'openai'
    assert result['waiver_applied'] is True
    assert result['prepare_functional_embedding_proof'] is True
    assert result['tool_count'] == 28
    assert result['tool_call_count'] == result['final_ordinal']
    assert result['final_ordinal'] >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize('code', ['source_attestation_mismatch', 'source_attestation_dirty'])
async def test_gate0_blocks_before_transport(tmp_path: Path, code: str) -> None:
    payload_path, manifest_path, payload, manifest = artifact(tmp_path)
    fake = ContractFake(payload, manifest['request_sha256'])

    def blocked(**_kwargs: Any):
        raise runner.RunnerError(code, 'blocked')

    with pytest.raises(runner.RunnerError):
        await runner.run_live_canary(
            fake,
            payload_path,
            manifest_path,
            confirm_run_id=manifest['run_id'],
            confirm_group_id=manifest['group_id'],
            confirm_control_group_id=manifest['control_group_id'],
            confirm_batch_id=manifest['batch_id'],
            source_head='1' * 40,
            source_map_sha256='2' * 64,
            runner_sha256='3' * 64,
            execution_map_sha256='4' * 64,
            source_attestor=blocked,
            execution_attestor=execution_attestor,
        )
    assert fake.calls == []


def test_pure_strict_request_builders(tmp_path: Path) -> None:
    _, _, payload, _ = artifact(tmp_path)
    request = runner.UpsertCatalogBatchRequest.model_validate({**payload, 'dry_run': True})
    entity_uuids = {(x.entity_type, x.graph_key): uid(1, i) for i, x in enumerate(request.entities)}
    verify = runner.build_verify_request(request, entity_uuids)
    entities = runner.build_resolve_entities_request(request)
    edges = runner.build_resolve_edges_request(request)
    runner.VerifyCatalogBatchRequest.model_validate(verify, strict=True)
    assert 'graph_keys' not in entities
    assert all('expected_source_graph_key' not in x for x in verify['edges'])
    assert set(edges) == set(runner.ResolveTypedEdgesRequest.model_fields)


@pytest.mark.parametrize('value', [False, None, 'true', 'false', 1, 0])
def test_dry_run_rejects_non_true(value: object) -> None:
    with pytest.raises(runner.RunnerError, match='dry_run'):
        runner.build_live_dry_run_request({}, dry_run=value)


def test_fastmcp_envelope_split(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    async def fake(_session: Any, name: str, args: dict[str, Any]):
        seen.append((name, args))
        return {}, {}

    monkeypatch.setattr(runner, 'call_mcp_tool', fake)
    transport = runner.SessionLiveTransport(object())
    asyncio.run(transport.call('resolve_typed_entities', {'x': 1}))
    asyncio.run(transport.call('search_nodes', {'query': 'x'}))
    assert seen == [
        ('resolve_typed_entities', {'request': {'x': 1}}),
        ('search_nodes', {'query': 'x'}),
    ]


def test_protected_matrix_artifact_and_result_paths(tmp_path: Path) -> None:
    for value in runner.PROTECTED_GROUP_IDS:
        for variant in (value, value.upper(), f' {value} '):
            with pytest.raises(runner.RunnerError, match='protected'):
                runner._reject_live_group(variant)
    payload, manifest, _, _ = artifact(tmp_path)
    with pytest.raises(runner.RunnerError, match='protected'):
        runner.validate_result_directory(payload.parent / 'result', payload, manifest)
    (payload.parent / 'unexpected').write_text('x', encoding='utf-8')
    with pytest.raises(runner.RunnerError, match='unexpected'):
        runner.validate_live_artifact(payload, manifest)


def test_cli_requires_reviewed_attestation(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        runner.parse_args(
            [
                '--mode',
                'live-canary',
                '--mcp-url',
                'hidden',
                '--payload',
                'payload',
                '--manifest',
                'manifest',
                '--run-id',
                'run',
                '--group-id',
                'group',
                '--control-group-id',
                'control',
                '--batch-id',
                'batch',
                '--output-dir',
                str(tmp_path / 'output'),
            ]
        )
    # Missing --execution-map-sha256 still blocks CLI parse.
    with pytest.raises(SystemExit):
        runner.parse_args(
            [
                '--mode',
                'live-canary',
                '--mcp-url',
                'hidden',
                '--payload',
                'payload',
                '--manifest',
                'manifest',
                '--run-id',
                'run',
                '--group-id',
                'group',
                '--control-group-id',
                'control',
                '--batch-id',
                'batch',
                '--output-dir',
                str(tmp_path / 'output2'),
                '--source-head',
                '1' * 40,
                '--source-map-sha256',
                '2' * 64,
                '--runner-sha256',
                '3' * 64,
            ]
        )


@pytest.mark.asyncio
async def test_execution_map_mismatch_blocks_before_transport(tmp_path: Path) -> None:
    payload_path, manifest_path, payload, manifest = artifact(tmp_path)
    fake = ContractFake(payload, manifest['request_sha256'])

    def bad_exec(**_kwargs: Any):
        raise runner.RunnerError('execution_attestation_mismatch', 'blocked')

    with pytest.raises(runner.RunnerError) as ei:
        await runner.run_live_canary(
            fake,
            payload_path,
            manifest_path,
            confirm_run_id=manifest['run_id'],
            confirm_group_id=manifest['group_id'],
            confirm_control_group_id=manifest['control_group_id'],
            confirm_batch_id=manifest['batch_id'],
            source_head='1' * 40,
            source_map_sha256='2' * 64,
            runner_sha256='3' * 64,
            execution_map_sha256='4' * 64,
            source_attestor=attestor,
            execution_attestor=bad_exec,
        )
    assert ei.value.code == 'execution_attestation_mismatch'
    assert fake.calls == []


def test_host_execution_authority_raw_byte_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Worktree may lack override; synthesize fixed authority tree under tmp and bind ROOT.
    base = tmp_path / 'mcp_server' / 'docker' / 'docker-compose-neo4j.yml'
    override = (
        tmp_path / 'mcp_server' / 'docker' / 'docker-compose-neo4j.catalog-local.override.yml'
    )
    config = tmp_path / 'mcp_server' / 'config' / 'config-docker-neo4j.yaml'
    base.parent.mkdir(parents=True, exist_ok=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    base.write_bytes(b'base\r\ncontent')
    override.write_bytes(b'override\ncontent')
    config.write_bytes(b'config-bytes')
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    digests = runner.host_side_execution_authority_digests()
    assert digests[runner.COMPOSE_BASE_FILE] == runner.sha256_bytes(b'base\r\ncontent')
    assert digests[runner.COMPOSE_OVERRIDE_FILE] == runner.sha256_bytes(b'override\ncontent')
    assert digests['mcp_server/config/config-docker-neo4j.yaml'] == runner.sha256_bytes(
        b'config-bytes'
    )
    expected = runner.canonical_sha256({'files': digests})
    assert runner.compute_execution_map_sha256(digests) == expected
    ok = runner.attest_execution_authority(expected_execution_map_sha256=expected)
    assert ok['execution_map_sha256'] == expected
    assert ok['execution_files'] == 3
    assert ok['execution_digest_method'] == 'raw-byte-sha256'
    with pytest.raises(runner.RunnerError) as ei:
        runner.attest_execution_authority(expected_execution_map_sha256='a' * 64)
    assert ei.value.code == 'execution_attestation_mismatch'
    # Missing override fail-closed.
    override.unlink()
    with pytest.raises(runner.RunnerError) as ei2:
        runner.host_side_execution_authority_digests()
    assert ei2.value.code == 'execution_attestation_missing'


@pytest.mark.asyncio
async def test_terminal_acceptance_manifest_written_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload_path, manifest_path, payload, manifest = artifact(tmp_path)
    fake = ContractFake(payload, manifest['request_sha256'])
    output = tmp_path / 'accept-ok'
    result = await runner.run_live_canary(
        fake,
        payload_path,
        manifest_path,
        confirm_run_id=manifest['run_id'],
        confirm_group_id=manifest['group_id'],
        confirm_control_group_id=manifest['control_group_id'],
        confirm_batch_id=manifest['batch_id'],
        output_dir=output,
        **LIVE_KW,
    )
    accept = json.loads((output / 'terminal-artifacts-manifest.json').read_text(encoding='utf-8'))
    assert accept['tool_call_count'] == result['tool_call_count']
    assert accept['final_ordinal'] == result['final_ordinal']
    assert accept['tool_ledger_sha256'] == runner.sha256_bytes(
        (output / 'tool-ledger.json').read_bytes()
    )
    assert accept['final_report_sha256'] == runner.sha256_bytes(
        (output / 'final-report.json').read_bytes()
    )

    # final-report write failure => no acceptance manifest (artifacts unaccepted).
    real_atomic = runner.atomic_write_json

    def flaky(path: Path, value: Any) -> str:
        if path.name == 'final-report.json':
            raise runner.RunnerError('atomic_write_failed', 'forced')
        return real_atomic(path, value)

    fake2 = ContractFake(payload, manifest['request_sha256'])
    output2 = tmp_path / 'accept-fail'
    monkeypatch.setattr(runner, 'atomic_write_json', flaky)
    with pytest.raises(runner.RunnerError, match='forced|atomic_write'):
        await runner.run_live_canary(
            fake2,
            payload_path,
            manifest_path,
            confirm_run_id=manifest['run_id'],
            confirm_group_id=manifest['group_id'],
            confirm_control_group_id=manifest['control_group_id'],
            confirm_batch_id=manifest['batch_id'],
            output_dir=output2,
            **LIVE_KW,
        )
    assert (output2 / 'tool-ledger.json').is_file()
    assert not (output2 / 'final-report.json').exists()
    assert not (output2 / 'terminal-artifacts-manifest.json').exists()
