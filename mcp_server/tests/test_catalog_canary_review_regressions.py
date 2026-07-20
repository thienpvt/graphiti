"""Deep-review regressions for hardened canary evidence validation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / 'scripts' / 'run_catalog_canary_batch.py'
PAYLOAD_PATH = ROOT / 'catalog' / 'canary-v2-requests-hardened' / 'accept-tab.payload.json'


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location('catalog_canary_review_runner', RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def _request() -> tuple[Any, bytes, str, str]:
    artifact, raw, _, artifact_sha, request_sha = runner.validate_hardened_artifact(PAYLOAD_PATH)
    request = runner.UpsertCatalogBatchRequest.model_validate({**raw, 'dry_run': False}, strict=True)
    return request, artifact, artifact_sha, request_sha


def test_hardened_artifact_rejects_empty_representative_collections(tmp_path: Path) -> None:
    raw = json.loads(PAYLOAD_PATH.read_text(encoding='utf-8'))
    for field in ('entities', 'edges'):
        invalid = dict(raw)
        invalid[field] = []
        path = tmp_path / f'{field}.json'
        path.write_bytes(runner.canonical_artifact_bytes(invalid))
        with pytest.raises(runner.RunnerError, match='at least one entity and one edge'):
            runner.validate_hardened_artifact(path)


@pytest.mark.asyncio
async def test_verified_replay_rejects_shallow_fabricated_wrapper(tmp_path: Path) -> None:
    request, artifact, artifact_sha, request_sha = _request()
    response = tmp_path / 'response.json'
    wrapper = {
        'schema_version': 2,
        'mode': 'commit',
        'artifact_sha256': artifact_sha,
        'server_request_sha256': request_sha,
        'commit': {'state': 'COMMITTED'},
        'post_commit': {name: {} for name in runner.COMMIT_TOOL_SEQUENCE[2:]},
    }
    response_sha = runner.atomic_write_json(response, wrapper)
    checkpoint = tmp_path / 'checkpoint.json'
    runner.atomic_write_json(
        checkpoint,
        {
            'attempts': [
                {
                    'batch_id': request.batch_id,
                    'mode': 'commit',
                    'status': 'commit_verified',
                    'artifact_sha256': artifact_sha,
                    'artifact_size': len(artifact),
                    'server_request_sha256': request_sha,
                    'response_path': response.name,
                    'response_sha256': response_sha,
                    'counts': {},
                }
            ]
        },
    )
    with pytest.raises(runner.RunnerError, match='binding|evidence|counts'):
        await runner.execute(
            argparse.Namespace(
                mcp_url='http://127.0.0.1:8000/mcp/',
                payload=PAYLOAD_PATH,
                mode='commit',
                expected_artifact_sha256=artifact_sha,
                expected_request_sha256=request_sha,
                checkpoint=checkpoint,
                allow_test_paths=True,
            )
        )


def test_manifest_inventory_rejects_empty_lists_with_nonzero_counts() -> None:
    request, _, _, _ = _request()
    assert request.provenance is not None
    manifest = runner.GetCatalogBatchManifestResponse(
        group_id=request.group_id,
        batch_id=request.batch_id,
        found=True,
        entity_count=len(request.entities),
        edge_count=len(request.edges),
        source_count=len(request.provenance.sources),
        evidence_link_count=len(request.provenance.evidence_links),
        limit=max(
            len(request.entities),
            len(request.edges),
            len(request.provenance.sources),
            len(request.provenance.evidence_links),
        ),
    )
    with pytest.raises(runner.RunnerError, match='membership identities'):
        runner._validate_manifest_inventory(manifest, request)


def test_manifest_and_evidence_reject_duplicate_identities() -> None:
    request, _, _, _ = _request()
    assert request.provenance is not None
    entity = request.entities[0]
    duplicate = {
        'uuid': '11111111-1111-1111-1111-111111111111',
        'entity_type': entity.entity_type,
        'graph_key': entity.graph_key,
        'content_sha256': entity.content_sha256,
    }
    manifest = runner.GetCatalogBatchManifestResponse(
        group_id=request.group_id,
        batch_id=request.batch_id,
        found=True,
        entity_count=2,
        edge_count=0,
        source_count=0,
        evidence_link_count=0,
        limit=max(
            len(request.entities),
            len(request.edges),
            len(request.provenance.sources),
            len(request.provenance.evidence_links),
        ),
        entities=[duplicate, duplicate],
    )
    with pytest.raises(runner.RunnerError, match='membership identities'):
        runner._validate_manifest_inventory(manifest, request)

    link = request.provenance.evidence_links[0]
    key = runner.evidence_link_key(link)
    digest = runner.canonical_sha256(runner.evidence_canonical_payload(link))
    response = runner.GetCatalogEvidenceResponse(
        group_id=request.group_id,
        target_kind='entity',
        target_uuid='11111111-1111-1111-1111-111111111111',
        target_graph_key=request.entities[0].graph_key,
        found_target=True,
        limit=2,
        total=2,
        links=[
            {
                'uuid': '22222222-2222-2222-2222-222222222222',
                'link_key': key,
                'content_sha256': digest,
                'target_kind': 'entity',
                'target_uuid': '11111111-1111-1111-1111-111111111111',
            },
            {
                'uuid': '22222222-2222-2222-2222-222222222222',
                'link_key': key,
                'content_sha256': digest,
                'target_kind': 'entity',
                'target_uuid': '11111111-1111-1111-1111-111111111111',
            },
        ],
    )
    with pytest.raises(runner.RunnerError, match='binding'):
        runner._validate_evidence_response(
            response,
            request,
            target_kind='entity',
            target_key=request.entities[0].graph_key,
            target_uuid='11111111-1111-1111-1111-111111111111',
            expected_links={key: '22222222-2222-2222-2222-222222222222'},
        )
