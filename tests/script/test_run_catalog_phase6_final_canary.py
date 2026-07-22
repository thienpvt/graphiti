from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / 'scripts' / 'run_catalog_phase6_final_canary.py'
_spec = importlib.util.spec_from_file_location('phase6_final_canary_launcher', LAUNCHER)
assert _spec is not None and _spec.loader is not None
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)


def _job(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    job = tmp_path / 'job'
    job.mkdir()
    (job / 'tmp').mkdir()
    return job, {'CLAUDE_JOB_DIR': str(job)}


def _freeze(tmp_path: Path, **overrides: Any) -> Path:
    receipt = {
        'head': '1' * 40,
        'commit': '1' * 40,
        'git_commit_count_at_freeze': 42,
        'image_id': 'sha256:' + '2' * 64,
        'image_revision_commit': '3' * 40,
        'project': 'graphiti-catalog-v2-phase6-final',
        'fingerprint': '4' * 64,
        'r0_passed': True,
        'r1_passed': True,
        'r2_passed': True,
        'r3_passed': True,
        'canary_ids_allocated': False,
        'plan_status': 'PENDING_TOP_LEVEL_HANDOFF',
        'summary_created': False,
    }
    receipt.update(overrides)
    path = tmp_path / '06-FREEZE-RECEIPT.json'
    path.write_text(json.dumps(receipt), encoding='utf-8')
    return path


def _invocation(tmp_path: Path, **overrides: Any) -> Path:
    raw = {
        'schema_version': 1,
        'after_human_approval': True,
        'forbid_gsd_executor_resume': True,
        'forbid_summary': True,
        'forbid_tracking_updates': True,
        'forbid_verify_complete_tag_cleanup': True,
        'forbid_git_commit_after_id_allocation': True,
        'identities_allocated_before_approval': False,
        'launcher': 'scripts/run_catalog_phase6_final_canary.py',
        'cwd': 'repo_root',
        'shell': False,
        'argv_template': [
            'python',
            'scripts/run_catalog_phase6_final_canary.py',
            '--freeze-receipt',
            str(tmp_path / '06-FREEZE-RECEIPT.json'),
            '--image-receipt',
            str(tmp_path / '06-IMAGE-RECEIPT.json'),
            '--mcp-url-env',
            'GRAPHITI_PHASE6_MCP_URL',
            '--artifact-parent',
            '{CLAUDE_JOB_TMP}/phase6-final-canary',
            '--result-parent',
            '{CLAUDE_JOB_TMP}/phase6-final-canary',
            '--phase-dir',
            str(tmp_path),
        ],
        'argv_expansion': {
            'env_required': ['CLAUDE_JOB_DIR'],
            'tokens': {'{CLAUDE_JOB_TMP}': {'append': 'tmp'}},
            'after_expand': {
                'reject_leftover_braces': True,
                'reject_leftover_dollar': True,
                'require_artifact_result_parents_under_job_tmp': True,
            },
            'invoke': 'exact_validated_expanded_argv_once_shell_false',
        },
    }
    raw.update(overrides)
    path = tmp_path / '06-POST-APPROVAL-INVOCATION.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    return path


def _image(tmp_path: Path) -> None:
    (tmp_path / '06-IMAGE-RECEIPT.json').write_text(
        json.dumps({'image_id': 'sha256:' + '2' * 64, 'commit': '3' * 40}),
        encoding='utf-8',
    )


def test_final_canary_resolve_job_tmp_rejects_bad_environment(tmp_path: Path) -> None:
    with pytest.raises(launcher.FinalCanaryError):
        launcher.resolve_job_tmp({})
    with pytest.raises(launcher.FinalCanaryError):
        launcher.resolve_job_tmp({'CLAUDE_JOB_DIR': 'relative'})
    missing = tmp_path / 'missing'
    with pytest.raises(launcher.FinalCanaryError):
        launcher.resolve_job_tmp({'CLAUDE_JOB_DIR': str(missing)})

    job, environment = _job(tmp_path)
    assert launcher.resolve_job_tmp(environment) == (job / 'tmp').resolve()


def test_final_canary_argv_expand_rejects_leftovers_and_boundary(tmp_path: Path) -> None:
    job_tmp = tmp_path / 'job' / 'tmp'
    job_tmp.mkdir(parents=True)
    expanded = launcher.expand_argv(
        ['--artifact-parent', '{CLAUDE_JOB_TMP}/artifacts'], job_tmp=job_tmp
    )
    assert expanded == ['--artifact-parent', str(job_tmp.resolve() / 'artifacts')]
    for bad in ('{UNKNOWN}/x', '$CLAUDE_JOB_DIR/x', '${CLAUDE_JOB_DIR}/x'):
        with pytest.raises(launcher.FinalCanaryError):
            launcher.expand_argv(['--artifact-parent', bad], job_tmp=job_tmp)
    with pytest.raises(launcher.FinalCanaryError):
        launcher.expand_argv(
            ['--result-parent', '{CLAUDE_JOB_TMP}/../../outside'], job_tmp=job_tmp
        )


def test_final_canary_invalid_freeze_fails_before_identity_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, environment = _job(tmp_path)
    freeze = _freeze(tmp_path, canary_ids_allocated=True)
    invocation = _invocation(tmp_path)
    allocated = False

    def forbidden_allocate() -> str:
        nonlocal allocated
        allocated = True
        return 'forbidden'

    monkeypatch.setattr(launcher, '_allocate_run_id', forbidden_allocate)
    with pytest.raises(launcher.FinalCanaryError):
        launcher.run_final_canary(
            freeze_receipt=freeze,
            invocation=invocation,
            environment=environment,
        )
    assert allocated is False


def test_final_canary_calls_builder_and_runner_once_shell_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, environment = _job(tmp_path)
    freeze = _freeze(tmp_path)
    invocation = _invocation(tmp_path)
    _image(tmp_path)
    monkeypatch.setattr(launcher, '_git_value', lambda argv: '1' * 40 if 'rev-parse' in argv else '42')
    monkeypatch.setattr(launcher, '_allocate_run_id', lambda: '20260722t120000z-a')
    def gate0_digests(head: str) -> dict[str, str]:
        assert head == '1' * 40
        return {
            'source_map_sha256': '5' * 64,
            'runner_sha256': '6' * 64,
            'execution_map_sha256': '7' * 64,
        }

    monkeypatch.setattr(launcher, '_gate0_digests', gate0_digests)
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((argv, kwargs))
        if 'build_catalog_canary_requests.py' in ' '.join(argv):
            artifact_dir = Path(argv[argv.index('--output-dir') + 1])
            artifact_dir.mkdir(parents=True)
            (artifact_dir / 'accept-tab.payload.json').write_text('{}', encoding='utf-8')
            (artifact_dir / 'run-manifest.json').write_text('{}', encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        result_dir = Path(argv[argv.index('--output-dir') + 1])
        result_dir.mkdir(parents=True)
        report = {
            'classification': 'PASSED',
            'counts': {'entities': 3, 'edges': 2, 'sources': 1, 'evidence_links': 5},
            'dry_run_zero_write_proven': True,
            'replay': 'skipped',
        }
        (result_dir / 'final-report.json').write_text(json.dumps(report), encoding='utf-8')
        (result_dir / 'tool-ledger.json').write_text(
            json.dumps(
                {
                    'entries': [
                        {'tool': 'prepare_catalog_batch'},
                        {'tool': 'commit_prepared_catalog_batch'},
                    ]
                }
            ),
            encoding='utf-8',
        )
        (result_dir / 'terminal-artifacts-manifest.json').write_text('{}', encoding='utf-8')
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr='')

    monkeypatch.setattr(launcher.subprocess, 'run', fake_run)
    monkeypatch.setenv('GRAPHITI_PHASE6_MCP_URL', 'http://127.0.0.1:8000/mcp')

    result = launcher.run_final_canary(
        freeze_receipt=freeze,
        invocation=invocation,
        environment={**environment, 'GRAPHITI_PHASE6_MCP_URL': 'http://127.0.0.1:8000/mcp'},
    )

    assert result['classification'] == 'PASSED'
    assert len(calls) == 2
    assert all(call_kwargs.get('shell') is False for _, call_kwargs in calls)
    assert all('git commit' not in ' '.join(argv) for argv, _ in calls)
    assert all('gsd' not in ' '.join(argv).lower() for argv, _ in calls)
    assert all(str(job / 'tmp') in ' '.join(argv) for argv, _ in calls)


@pytest.mark.parametrize(
    'auth_patch',
    [
        {},
        {'kubernetes_applied': True},
        {'namespace_applied': False},
    ],
)
def test_final_canary_auth_01_requires_exact_kubernetes_false(auth_patch: dict[str, Any]) -> None:
    auth = {
        'deployment_applied': False,
        'kubernetes_applied': False,
        'second_canary': False,
        'historical_group_ids_used': False,
        'canary_invocation_count': 1,
        'mode': 'iterative_tdd_plus_one_final_clean_room_canary',
    }
    if auth_patch == {}:
        auth.pop('kubernetes_applied')
    else:
        auth.update(auth_patch)
    with pytest.raises(launcher.FinalCanaryError):
        launcher._validate_auth_01(auth)

    launcher._validate_auth_01(
        {
            'deployment_applied': False,
            'kubernetes_applied': False,
            'second_canary': False,
            'historical_group_ids_used': False,
            'canary_invocation_count': 1,
            'mode': 'iterative_tdd_plus_one_final_clean_room_canary',
        }
    )
