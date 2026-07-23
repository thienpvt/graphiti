#!/usr/bin/env python3
"""Execute the single approved Phase 6 clean-room canary."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / 'scripts' / 'run_catalog_canary_batch.py'
BUILDER_PATH = ROOT / 'scripts' / 'build_catalog_canary_requests.py'
SHA1_RE = re.compile(r'^[0-9a-f]{40}$')
IMAGE_ID_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
TERMINAL_CLASSES = {'PASSED', 'FAILED_BEFORE_COMMIT', 'FAILED_AFTER_COMMIT'}
REPORT_SCHEMA_VERSION = 'phase6-canary-report-v1'
TERMINAL_ACCEPTANCE_SCHEMA_VERSION = 'phase6-terminal-artifacts-manifest-v1'
EXPECTED_COUNTS = {'entities': 3, 'edges': 2, 'sources': 1, 'evidence_links': 5}
ALLOCATION_CLAIM = 'phase6-final-canary-allocation.json'
LIVE_FIELDS_START = '<!-- phase6-final-canary-live:start -->'
LIVE_FIELDS_END = '<!-- phase6-final-canary-live:end -->'
AUTH_01 = {
    'deployment_applied': False,
    'kubernetes_applied': False,
    'second_canary': False,
    'historical_group_ids_used': False,
    'canary_invocation_count': 1,
    'mode': 'iterative_tdd_plus_one_final_clean_room_canary',
}


class FinalCanaryError(RuntimeError):
    """Fail-closed final-canary launcher error."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FinalCanaryError('duplicate JSON key')
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(
            path.read_text(encoding='utf-8'),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                FinalCanaryError(f'non-finite JSON number: {value}')
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalCanaryError(f'invalid {path.name}') from exc
    if not isinstance(raw, dict):
        raise FinalCanaryError(f'invalid {path.name}')
    return raw


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise FinalCanaryError(f'cannot read {path.name}') from exc


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root


def resolve_job_tmp(environment: dict[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    raw = env.get('CLAUDE_JOB_DIR')
    if not isinstance(raw, str) or not raw:
        raise FinalCanaryError('CLAUDE_JOB_DIR is required')
    job_dir = Path(raw)
    if not job_dir.is_absolute() or not job_dir.is_dir():
        raise FinalCanaryError('CLAUDE_JOB_DIR must be an absolute existing directory')
    job_tmp = (job_dir / 'tmp').resolve()
    if not job_tmp.is_dir() or not _is_below(job_tmp, job_dir.resolve()):
        raise FinalCanaryError('CLAUDE_JOB_DIR/tmp is invalid')
    return job_tmp


def expand_argv(argv: list[str], *, job_tmp: Path) -> list[str]:
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise FinalCanaryError('argv template is invalid')
    root = job_tmp.resolve()
    expanded = [token.replace('{CLAUDE_JOB_TMP}', str(root)) for token in argv]
    if any('{' in token or '}' in token or '$' in token for token in expanded):
        raise FinalCanaryError('argv contains an unresolved token')
    for option in ('--artifact-parent', '--result-parent'):
        if option not in expanded:
            continue
        index = expanded.index(option)
        if index + 1 >= len(expanded):
            raise FinalCanaryError(f'{option} value is missing')
        path = Path(expanded[index + 1]).resolve()
        if not path.is_absolute() or not _is_below(path, root):
            raise FinalCanaryError(f'{option} escapes CLAUDE_JOB_DIR/tmp')
        expanded[index + 1] = str(path)
    return expanded


def _git_value(argv: list[str]) -> str:
    try:
        result = subprocess.run(
            ['git', '-C', str(ROOT), *argv],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except OSError as exc:
        raise FinalCanaryError('Git freeze validation failed') from exc
    if result.returncode != 0:
        raise FinalCanaryError('Git freeze validation failed')
    return result.stdout.strip()


def _allocate_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz')
    return f'{timestamp}-{uuid.uuid4().hex[:8]}'


def _runner_module() -> Any:
    spec = importlib.util.spec_from_file_location('phase6_bound_canary_runner', RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise FinalCanaryError('runner authority is unavailable')
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise FinalCanaryError('runner authority is unavailable') from exc
    return module


def _gate0_digests(head: str) -> dict[str, str]:
    try:
        runner = _runner_module()
        source_map = runner.source_authority_map(mode='git', revision=head)
        return {
            'source_map_sha256': runner.canonical_sha256({'files': source_map}),
            'runner_sha256': source_map['scripts/run_catalog_canary_batch.py']['lf_sha256'],
            'execution_map_sha256': runner.compute_execution_map_sha256(),
        }
    except FinalCanaryError:
        raise
    except Exception as exc:
        raise FinalCanaryError('Gate 0 digest validation failed') from exc


def _validate_auth_01(auth: dict[str, Any]) -> None:
    if not isinstance(auth, dict) or auth != AUTH_01:
        raise FinalCanaryError('P6-AUTH-01 assertion failed')


def _validate_freeze(raw: dict[str, Any]) -> tuple[str, int, str]:
    head = raw.get('head')
    commit = raw.get('commit')
    count = raw.get('git_commit_count_at_freeze')
    image_id = raw.get('image_id')
    image_revision = raw.get('image_revision_commit')
    fingerprint = raw.get('fingerprint')
    project = raw.get('project')
    if (
        not isinstance(head, str)
        or SHA1_RE.fullmatch(head) is None
        or commit != head
        or type(count) is not int
        or count < 1
        or not isinstance(image_id, str)
        or IMAGE_ID_RE.fullmatch(image_id) is None
        or not isinstance(image_revision, str)
        or SHA1_RE.fullmatch(image_revision) is None
        or not isinstance(fingerprint, str)
        or re.fullmatch(r'^[0-9a-f]{64}$', fingerprint) is None
        or not isinstance(project, str)
        or re.fullmatch(r'^[a-z0-9][a-z0-9_-]{0,62}$', project) is None
        or raw.get('canary_ids_allocated') is not False
        or raw.get('summary_created') is not False
        or raw.get('plan_status') != 'PENDING_TOP_LEVEL_HANDOFF'
        or any(
            raw.get(key) is not True for key in ('r0_passed', 'r1_passed', 'r2_passed', 'r3_passed')
        )
    ):
        raise FinalCanaryError('freeze receipt is invalid')
    return head, count, image_id


def _option_value(argv: list[str], option: str) -> str:
    if argv.count(option) != 1:
        raise FinalCanaryError(f'{option} must appear exactly once')
    index = argv.index(option)
    if index + 1 >= len(argv) or argv[index + 1].startswith('--'):
        raise FinalCanaryError(f'{option} value is missing')
    return argv[index + 1]


def _validate_invocation(raw: dict[str, Any], freeze_receipt: Path, job_tmp: Path) -> list[str]:
    expected_fields = {
        'schema_version',
        'after_human_approval',
        'forbid_gsd_executor_resume',
        'forbid_summary',
        'forbid_tracking_updates',
        'forbid_verify_complete_tag_cleanup',
        'forbid_git_commit_after_id_allocation',
        'identities_allocated_before_approval',
        'launcher',
        'cwd',
        'shell',
        'argv_template',
        'argv_expansion',
        'mcp_url_env',
        'mcp_url_hint_local_only',
    }
    if set(raw) - (expected_fields | {'notes'}):
        raise FinalCanaryError('post-approval invocation fields are invalid')
    required = {
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
    }
    if any(raw.get(key) != value for key, value in required.items()):
        raise FinalCanaryError('post-approval invocation contract is invalid')
    for optional_mcp_field in ('mcp_url_env', 'mcp_url_hint_local_only'):
        if optional_mcp_field not in raw:
            continue
        value = raw[optional_mcp_field]
        if not isinstance(value, str) or not value.strip():
            raise FinalCanaryError('post-approval invocation fields are invalid')
    expansion = raw.get('argv_expansion')
    if (
        not isinstance(expansion, dict)
        or expansion.get('env_required') != ['CLAUDE_JOB_DIR']
        or expansion.get('invoke') != 'exact_validated_expanded_argv_once_shell_false'
        or not isinstance(expansion.get('tokens'), dict)
        or '{CLAUDE_JOB_TMP}' not in expansion['tokens']
        or not isinstance(expansion.get('after_expand'), dict)
        or expansion['after_expand'].get('reject_leftover_braces') is not True
        or expansion['after_expand'].get('reject_leftover_dollar') is not True
        or expansion['after_expand'].get('require_artifact_result_parents_under_job_tmp')
        is not True
    ):
        raise FinalCanaryError('argv expansion contract is invalid')
    template = raw.get('argv_template')
    if not isinstance(template, list) or not all(isinstance(item, str) for item in template):
        raise FinalCanaryError('argv template is invalid')
    expanded = expand_argv(template, job_tmp=job_tmp)
    if (
        len(expanded) < 2
        or Path(expanded[1]).as_posix() != 'scripts/run_catalog_phase6_final_canary.py'
    ):
        raise FinalCanaryError('launcher argv is invalid')
    if Path(_option_value(expanded, '--freeze-receipt')).resolve() != freeze_receipt.resolve():
        raise FinalCanaryError('freeze receipt binding differs')
    _option_value(expanded, '--image-receipt')
    _option_value(expanded, '--mcp-url-env')
    _option_value(expanded, '--artifact-parent')
    _option_value(expanded, '--result-parent')
    _option_value(expanded, '--phase-dir')
    return expanded


def _fresh_child(parent: Path, name: str, job_tmp: Path) -> Path:
    parent = parent.resolve()
    if not _is_below(parent, job_tmp.resolve()):
        raise FinalCanaryError('canary parent escapes CLAUDE_JOB_DIR/tmp')
    path = parent / name
    if path.exists():
        raise FinalCanaryError('canary output path already exists')
    return path


def _run(argv: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except OSError as exc:
        raise FinalCanaryError('canary child launch failed') from exc


def _validate_terminal(
    result_dir: Path,
    returncode: int,
    *,
    run_id: str,
    group_id: str,
    control_group_id: str,
    batch_id: str,
) -> dict[str, Any]:
    report_path = result_dir / 'final-report.json'
    ledger_path = result_dir / 'tool-ledger.json'
    acceptance_path = result_dir / 'terminal-artifacts-manifest.json'
    report = _load_json(report_path)
    ledger = _load_json(ledger_path)
    acceptance = _load_json(acceptance_path)
    entries = ledger.get('entries')
    if not isinstance(entries, list):
        raise FinalCanaryError('runner tool ledger is invalid')
    expected_keys = {'ordinal', 'tool', 'stage', 'success', 'error_code'}
    for index, entry in enumerate(entries, start=1):
        if (
            not isinstance(entry, dict)
            or set(entry) != expected_keys
            or entry.get('ordinal') != index
            or not isinstance(entry.get('tool'), str)
            or not entry.get('tool')
            or not isinstance(entry.get('stage'), str)
            or not entry.get('stage')
            or type(entry.get('success')) is not bool
            or (entry['success'] is True and entry.get('error_code') is not None)
            or (
                entry['success'] is False
                and (not isinstance(entry.get('error_code'), str) or not entry['error_code'])
            )
        ):
            raise FinalCanaryError('runner tool ledger is invalid')
    if (
        ledger.get('schema_version') != 1
        or report.get('schema_version') != REPORT_SCHEMA_VERSION
        or acceptance.get('schema_version') != TERMINAL_ACCEPTANCE_SCHEMA_VERSION
        or acceptance.get('tool_ledger_sha256') != _sha256(ledger_path)
        or acceptance.get('final_report_sha256') != _sha256(report_path)
        or acceptance.get('tool_call_count') != len(entries)
        or acceptance.get('final_ordinal') != len(entries)
        or acceptance.get('tool_count') != 28
        or report.get('tool_call_count') != len(entries)
        or report.get('final_ordinal') != len(entries)
        or report.get('tool_count') != 28
    ):
        raise FinalCanaryError('runner terminal acceptance binding is invalid')
    classification = report.get('classification')
    if (
        classification not in TERMINAL_CLASSES
        or (returncode == 0) != (classification == 'PASSED')
        or report.get('run_id') != run_id
        or report.get('group_id') != group_id
        or report.get('control_group_id') != control_group_id
        or report.get('batch_id') != batch_id
    ):
        raise FinalCanaryError('runner terminal classification is invalid')
    names = [entry['tool'] for entry in entries]
    prepare_count = names.count('prepare_catalog_batch')
    commit_count = names.count('commit_prepared_catalog_batch')
    if prepare_count > 1 or commit_count > 1 or commit_count > prepare_count:
        raise FinalCanaryError('runner prepare/commit count is invalid')
    expected_replay = 'failed' if classification == 'FAILED_AFTER_COMMIT' else 'skipped'
    if report.get('replay') != expected_replay:
        raise FinalCanaryError('runner replay gate is invalid')
    if report.get('dry_run_zero_write_proven') is True and report.get('counts') != EXPECTED_COUNTS:
        raise FinalCanaryError('runner dry-run counts are invalid')
    if classification == 'PASSED' and (
        report.get('dry_run_zero_write_proven') is not True
        or report.get('counts') != EXPECTED_COUNTS
        or prepare_count != 1
        or commit_count != 1
    ):
        raise FinalCanaryError('runner success proof is incomplete')
    return report


def _phase_directory(expanded: list[str]) -> Path:
    phase_dir = Path(_option_value(expanded, '--phase-dir'))
    if not phase_dir.is_absolute():
        phase_dir = ROOT / phase_dir
    phase_dir = phase_dir.resolve()
    try:
        phase_dir.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise FinalCanaryError('phase directory escapes repository') from exc
    if not phase_dir.is_dir():
        raise FinalCanaryError('phase directory is invalid')
    return phase_dir


def _claim_allocation(job_tmp: Path, frozen_head: str) -> tuple[Path, str]:
    path = job_tmp / ALLOCATION_CLAIM
    try:
        with path.open('x', encoding='utf-8', newline='\n') as handle:
            run_id = _allocate_run_id()
            claim = json.dumps(
                {'schema_version': 1, 'run_id': run_id, 'frozen_head': frozen_head},
                sort_keys=True,
            )
            handle.write(claim + '\n')
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise FinalCanaryError('final canary allocation was already claimed') from exc
    except OSError as exc:
        raise FinalCanaryError('final canary allocation claim failed') from exc
    return path, run_id


def _launcher_terminal_report(
    *,
    classification: str,
    run_id: str,
    group_id: str,
    control_group_id: str,
    batch_id: str,
) -> dict[str, Any]:
    return {
        'schema_version': REPORT_SCHEMA_VERSION,
        'classification': classification,
        'run_id': run_id,
        'group_id': group_id,
        'control_group_id': control_group_id,
        'batch_id': batch_id,
        'counts': None,
        'dry_run_zero_write_proven': False,
        'replay': 'failed' if classification == 'FAILED_AFTER_COMMIT' else 'skipped',
        'tool_call_count': 0,
        'final_ordinal': 0,
        'error_code': 'launcher_interrupted_after_allocation',
        'error_type': None,
    }


def _phase_ledger(report: dict[str, Any]) -> dict[str, Any]:
    return {
        'classification': report['classification'],
        'run_id': report.get('run_id'),
        'group_id': report.get('group_id'),
        'control_group_id': report.get('control_group_id'),
        'batch_id': report.get('batch_id'),
        'counts': report.get('counts'),
        'dry_run_zero_write_proven': report.get('dry_run_zero_write_proven'),
        'replay': report.get('replay'),
        'tool_call_count': report.get('tool_call_count'),
        'final_ordinal': report.get('final_ordinal'),
        'error_code': report.get('error_code'),
        'error_type': report.get('error_type'),
        'auth_01': dict(AUTH_01),
        'stack_preserved': True,
    }


def _final_report_text(current: str, ledger: dict[str, Any]) -> str:
    start = current.find(LIVE_FIELDS_START)
    end = current.find(LIVE_FIELDS_END)
    if start < 0 or end < 0 or end <= start:
        raise FinalCanaryError('final report live field markers are invalid')
    fields = [
        LIVE_FIELDS_START,
        f'- Classification: `{ledger["classification"]}`',
        f'- Run ID: `{ledger["run_id"]}`',
        f'- Group ID: `{ledger["group_id"]}`',
        f'- Control group ID: `{ledger["control_group_id"]}`',
        f'- Batch ID: `{ledger["batch_id"]}`',
        f'- Counts: `{json.dumps(ledger["counts"], sort_keys=True)}`',
        f'- Dry-run zero-write proven: `{str(ledger["dry_run_zero_write_proven"]).lower()}`',
        f'- Replay: `{ledger["replay"]}`',
        f'- Tool calls: `{ledger["tool_call_count"]}`',
        f'- Final ordinal: `{ledger["final_ordinal"]}`',
        f'- AUTH-01: `{json.dumps(ledger["auth_01"], sort_keys=True)}`',
        '- Stack preserved: `true`',
        LIVE_FIELDS_END,
    ]
    replacement = '\n'.join(fields)
    return current[:start] + replacement + current[end + len(LIVE_FIELDS_END) :]


def _map_phase_outputs(phase_dir: Path, report: dict[str, Any]) -> None:
    ledger = _phase_ledger(report)
    final_report = phase_dir / '06-FINAL-REPORT.md'
    try:
        final_text = _final_report_text(final_report.read_text(encoding='utf-8'), ledger)
    except OSError as exc:
        raise FinalCanaryError('final report shell is unavailable') from exc
    runner = _runner_module()
    try:
        runner.atomic_write_bytes(final_report, final_text.encode('utf-8'))
        runner.atomic_write_json(phase_dir / '06-CANARY-LEDGER.json', ledger)
    except Exception as exc:
        raise FinalCanaryError('phase live output update failed') from exc


def _map_failure_after_allocation(
    phase_dir: Path,
    fallback: dict[str, Any],
    result_dir: Path,
) -> None:
    report = fallback
    report_path = result_dir / 'final-report.json'
    if report_path.is_file():
        try:
            candidate = _load_json(report_path)
        except FinalCanaryError:
            candidate = None
        if isinstance(candidate, dict) and candidate.get('classification') in TERMINAL_CLASSES:
            report = candidate
    _map_phase_outputs(phase_dir, report)


def run_final_canary(
    *,
    freeze_receipt: Path,
    invocation: Path,
    environment: dict[str, str] | None = None,
    actual_argv: list[str] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environment is None else environment)
    job_tmp = resolve_job_tmp(env)
    freeze_path = freeze_receipt.resolve()
    invocation_path = invocation.resolve()
    freeze = _load_json(freeze_path)
    invocation_raw = _load_json(invocation_path)
    expanded = _validate_invocation(invocation_raw, freeze_path, job_tmp)
    if actual_argv is not None and actual_argv != expanded[2:]:
        raise FinalCanaryError('actual argv differs from approved invocation')
    phase_dir = _phase_directory(expanded)
    head, frozen_count, image_id = _validate_freeze(freeze)
    if _git_value(['rev-parse', 'HEAD']) != head:
        raise FinalCanaryError('freeze HEAD changed')
    if _git_value(['rev-list', '--count', 'HEAD']) != str(frozen_count):
        raise FinalCanaryError('freeze commit count changed')
    image_receipt = Path(_option_value(expanded, '--image-receipt'))
    if not image_receipt.is_absolute():
        image_receipt = (ROOT / image_receipt).resolve()
    image = _load_json(image_receipt)
    image_revision = freeze.get('image_revision_commit')
    image_commit = image.get('commit', image.get('revision'))
    if image.get('image_id') != image_id or image_commit != image_revision:
        raise FinalCanaryError('image receipt differs from freeze')

    artifact_parent = Path(_option_value(expanded, '--artifact-parent'))
    result_parent = Path(_option_value(expanded, '--result-parent'))
    _, run_id = _claim_allocation(job_tmp, head)
    group_id = f'oracle-catalog-v2-canary-{run_id}'
    control_group_id = f'{group_id}-empty-control'
    batch_id = f'accept-tab-catalog-v2-canary-{run_id}'
    artifact_dir = _fresh_child(artifact_parent, f'{run_id}-artifact', job_tmp)
    result_dir = _fresh_child(result_parent, f'{run_id}-result', job_tmp)

    fallback = _launcher_terminal_report(
        classification='FAILED_BEFORE_COMMIT',
        run_id=run_id,
        group_id=group_id,
        control_group_id=control_group_id,
        batch_id=batch_id,
    )
    try:
        builder = [
            sys.executable,
            str(BUILDER_PATH),
            '--profile',
            'live-canary',
            '--run-id',
            run_id,
            '--group-id',
            group_id,
            '--control-group-id',
            control_group_id,
            '--batch-id',
            batch_id,
            '--output-dir',
            str(artifact_dir),
            '--allow-unknown-embedding-provider',
            'openai',
        ]
        built = _run(builder, env)
        payload = artifact_dir / 'accept-tab.payload.json'
        manifest = artifact_dir / 'run-manifest.json'
        if built.returncode != 0 or not payload.is_file() or not manifest.is_file():
            raise FinalCanaryError('canary builder failed')

        digests = _gate0_digests(head)
        mcp_env_name = _option_value(expanded, '--mcp-url-env')
        mcp_url = env.get(mcp_env_name)
        parsed_mcp_url = urlsplit(mcp_url) if isinstance(mcp_url, str) else None
        if (
            parsed_mcp_url is None
            or parsed_mcp_url.scheme != 'http'
            or parsed_mcp_url.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or parsed_mcp_url.username is not None
            or parsed_mcp_url.password is not None
            or parsed_mcp_url.query
            or parsed_mcp_url.fragment
        ):
            raise FinalCanaryError('local MCP URL environment is invalid')
        runner = [
            sys.executable,
            str(RUNNER_PATH),
            '--mode',
            'live-canary',
            '--mcp-url',
            mcp_url,
            '--payload',
            str(payload),
            '--manifest',
            str(manifest),
            '--run-id',
            run_id,
            '--group-id',
            group_id,
            '--control-group-id',
            control_group_id,
            '--batch-id',
            batch_id,
            '--output-dir',
            str(result_dir),
            '--source-head',
            head,
            '--source-map-sha256',
            digests['source_map_sha256'],
            '--runner-sha256',
            digests['runner_sha256'],
            '--execution-map-sha256',
            digests['execution_map_sha256'],
            '--authority-mode',
            'git',
            '--image-fingerprint',
            image_id.removeprefix('sha256:'),
            '--allow-unknown-embedding-provider',
            'openai',
        ]
        completed = _run(runner, env)
        report = _validate_terminal(
            result_dir,
            completed.returncode,
            run_id=run_id,
            group_id=group_id,
            control_group_id=control_group_id,
            batch_id=batch_id,
        )
        if _git_value(['rev-list', '--count', 'HEAD']) != str(frozen_count):
            raise FinalCanaryError('freeze commit count changed after canary')
        _validate_auth_01(dict(AUTH_01))
        result = {
            **report,
            'auth_01': dict(AUTH_01),
            'stack_preserved': True,
        }
        _map_phase_outputs(phase_dir, report)
        return result
    except BaseException as exc:
        try:
            _map_failure_after_allocation(phase_dir, fallback, result_dir)
        except FinalCanaryError as mapping_exc:
            raise mapping_exc from exc
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze-receipt', required=True, type=Path)
    parser.add_argument('--image-receipt', required=True, type=Path)
    parser.add_argument('--mcp-url-env', required=True)
    parser.add_argument('--artifact-parent', required=True, type=Path)
    parser.add_argument('--result-parent', required=True, type=Path)
    parser.add_argument('--phase-dir', required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(actual_argv)
    invocation = args.phase_dir / '06-POST-APPROVAL-INVOCATION.json'
    try:
        result = run_final_canary(
            freeze_receipt=args.freeze_receipt,
            invocation=invocation,
            actual_argv=actual_argv,
        )
    except FinalCanaryError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
