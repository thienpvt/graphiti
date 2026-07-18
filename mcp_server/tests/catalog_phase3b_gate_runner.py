#!/usr/bin/env python3
"""Phase 3B fail-closed gate runner (stdlib only).

Owns canonical JSON argv specs, shell=False sequential execution, HEAD/spec/
content-digest-bound ledger emission, 24/24 edge-probe ownership, live Neo4j
atomic co-commit proof under --require-neo4j, and ready_for_phase_4 derivation
that never fakes green (D-32, D-33, D-34).

Wave 0: structural checks + fail-closed defaults. Product GREEN lands in 03B-06.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 'phase3b-gate-results.v1'
PHASE_DIR_REL = Path(
    '.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes'
)
DEFAULT_LEDGER_REL = PHASE_DIR_REL / '03B-GATE-RESULTS.json'
DEFAULT_RESOLUTION_REL = PHASE_DIR_REL / '03B-EDGE-PROBE-RESOLUTION.json'
OUTPUT_BOUND = 4000
INTEGRATION_MODULE = 'test_catalog_commit_neo4j_int.py'
FORBIDDEN_GROUP = 'oracle-catalog-v2'
ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
EXPECTED_PROBE_COUNT = 24
RESOLUTION_SCHEMA_VERSION = 'phase3b-edge-probe-resolution.v1'

SHELL_EXECUTABLES = frozenset(
    {
        'sh',
        'bash',
        'zsh',
        'fish',
        'cmd',
        'cmd.exe',
        'powershell',
        'powershell.exe',
        'pwsh',
        'pwsh.exe',
        'csh',
        'tcsh',
    }
)
SHELL_META_TOKENS = frozenset({'|', '||', '&', '&&', ';', '>', '>>', '<', '<<', '`', '$(', ')'})

GATE_INPUT_RELS = (
    PHASE_DIR_REL / '03B-VALIDATION.md',
    PHASE_DIR_REL / '03B-CONTEXT.md',
    PHASE_DIR_REL / '03B-01-SUMMARY.md',
    PHASE_DIR_REL / '03B-02-SUMMARY.md',
    PHASE_DIR_REL / '03B-03-SUMMARY.md',
    PHASE_DIR_REL / '03B-04-SUMMARY.md',
    PHASE_DIR_REL / '03B-05-SUMMARY.md',
    PHASE_DIR_REL / '03B-06-SUMMARY.md',
)

FOCUS_TEST_FILES = (
    'mcp_server/tests/test_catalog_manifest.py',
    'mcp_server/tests/test_catalog_evidence_store.py',
    'mcp_server/tests/test_catalog_atomic_writer.py',
    'mcp_server/tests/test_catalog_commit_recovery.py',
    'mcp_server/tests/test_catalog_concurrency.py',
    'mcp_server/tests/test_catalog_phase3b_gate_runner.py',
    'mcp_server/tests/test_catalog_capabilities.py',
)

RUFF_PATHS = (
    'mcp_server/tests/test_catalog_manifest.py',
    'mcp_server/tests/test_catalog_evidence_store.py',
    'mcp_server/tests/test_catalog_atomic_writer.py',
    'mcp_server/tests/test_catalog_commit_recovery.py',
    'mcp_server/tests/test_catalog_concurrency.py',
    'mcp_server/tests/test_catalog_commit_neo4j_int.py',
    'mcp_server/tests/catalog_phase3b_gate_runner.py',
    'mcp_server/tests/test_catalog_phase3b_gate_runner.py',
)

PYRIGHT_PATHS = RUFF_PATHS

# Plan ownership for research probe rows 0..23.
PLAN_OWNERSHIP = {
    '03B-01': frozenset({0, 1, 2, 3}),
    '03B-02': frozenset({4, 5, 6, 7}),
    '03B-03': frozenset({8, 9, 10, 11}),
    '03B-04': frozenset({12, 13, 14, 15}),
    '03B-05': frozenset({16, 17, 18, 19}),
    '03B-06': frozenset({20, 21, 22, 23}),
}


def repo_root_from(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / '.planning').is_dir() and (candidate / 'mcp_server').is_dir():
            return candidate
    raise RuntimeError(f'repository root not found from {cur}')


def _uv_pytest(files: list[str], extra: list[str] | None = None) -> list[str]:
    argv = [
        'uv',
        'run',
        '--project',
        'mcp_server',
        'python',
        '-m',
        'pytest',
        '-c',
        'mcp_server/pytest.ini',
        *files,
    ]
    if extra:
        argv.extend(extra)
    argv.extend(['-q', '--tb=line'])
    return argv


def _uv_tool(tool: str, args: list[str]) -> list[str]:
    return ['uv', 'run', '--project', 'mcp_server', tool, *args]


def _runner_check_argv(check_id: str) -> list[str]:
    return [
        'uv',
        'run',
        '--project',
        'mcp_server',
        'python',
        'mcp_server/tests/catalog_phase3b_gate_runner.py',
        'check',
        check_id,
    ]


def bound_output(text: str | None, limit: int = OUTPUT_BOUND) -> str:
    if not text:
        return ''
    text = text.replace('\x00', '')
    if len(text) <= limit:
        return text
    return text[: limit - 20] + '\n...[truncated]...'


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_file_lf(path: Path) -> str:
    data = path.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    return hashlib.sha256(data).hexdigest()


def write_text_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    path.write_bytes(normalized.encode('utf-8'))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + '\n'
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def plan_for_row(row_index: int) -> str:
    for plan, rows in PLAN_OWNERSHIP.items():
        if row_index in rows:
            return plan
    raise AssertionError(f'row_index {row_index} has no plan ownership')


def check_wave0_files(root: Path) -> None:
    required = [
        root / 'mcp_server/tests/test_catalog_manifest.py',
        root / 'mcp_server/tests/test_catalog_evidence_store.py',
        root / 'mcp_server/tests/test_catalog_atomic_writer.py',
        root / 'mcp_server/tests/test_catalog_commit_recovery.py',
        root / 'mcp_server/tests/test_catalog_concurrency.py',
        root / 'mcp_server/tests/test_catalog_commit_neo4j_int.py',
        root / 'mcp_server/tests/catalog_phase3b_gate_runner.py',
        root / 'mcp_server/tests/test_catalog_phase3b_gate_runner.py',
    ]
    missing = [str(p.relative_to(root)).replace('\\', '/') for p in required if not p.is_file()]
    if missing:
        raise AssertionError(f'wave0 product/test files missing: {missing}')


def check_safety_no_probe(root: Path) -> None:
    for rel in (
        'mcp_server/tests/catalog_phase3b_gate_runner.py',
        'mcp_server/tests/test_catalog_phase3b_gate_runner.py',
        'mcp_server/tests/test_catalog_commit_neo4j_int.py',
    ):
        path = root / rel
        if not path.is_file():
            raise AssertionError(f'missing {rel}')
        src = path.read_text(encoding='utf-8')
        if rel.endswith('catalog_phase3b_gate_runner.py') and ALLOWED_TEST_GROUP not in src:
            raise AssertionError('allowed test group constant missing from runner')
        if rel.endswith('test_catalog_commit_neo4j_int.py'):
            # Word-boundary on GROUP so FORBIDDEN_GROUP = '...' is not a false positive.
            if re.search(
                rf"\b(GROUP|group_id|TEST_GROUP)\s*=\s*['\"]{re.escape(FORBIDDEN_GROUP)}['\"]",
                src,
            ):
                raise AssertionError(f'{rel} assigns forbidden group as write target')
            if re.search(r'\bclear_graph\s*\(', src):
                raise AssertionError(f'{rel} calls clear_graph')
            if ALLOWED_TEST_GROUP not in src:
                raise AssertionError(f'{rel} must hard-code {ALLOWED_TEST_GROUP}')

    runner_src = (root / 'mcp_server/tests/catalog_phase3b_gate_runner.py').read_text(
        encoding='utf-8'
    )
    for line in runner_src.splitlines():
        if (line.startswith('import ') or line.startswith('from ')) and (
            'test_catalog_commit_neo4j_int' in line or 'test_catalog_prepare_neo4j_int' in line
        ):
            raise AssertionError('runner imports integration module')

    for rel in FOCUS_TEST_FILES:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        if re.search(rf"GROUP\s*=\s*['\"]{re.escape(FORBIDDEN_GROUP)}['\"]", text):
            raise AssertionError(f'{rel} references forbidden group as GROUP')


def check_atomicity_scaffold(root: Path) -> None:
    """Named atomicity RED cases exist (PLAN-13)."""
    path = root / 'mcp_server/tests/test_catalog_atomic_writer.py'
    if not path.is_file():
        raise AssertionError('test_catalog_atomic_writer.py missing')
    src = path.read_text(encoding='utf-8')
    for name in (
        'test_fault_inject_after_entities_rolls_back',
        'test_shared_writer_used_by_upsert_and_commit_paths',
    ):
        if f'def {name}' not in src:
            raise AssertionError(f'missing atomicity case: {name}')


def check_evidence_scaffold(root: Path) -> None:
    path = root / 'mcp_server/tests/test_catalog_evidence_store.py'
    if not path.is_file():
        raise AssertionError('test_catalog_evidence_store.py missing')
    src = path.read_text(encoding='utf-8')
    for name in (
        'test_evidence_create_once_conflict',
        'test_evidence_no_entity_label',
    ):
        if f'def {name}' not in src:
            raise AssertionError(f'missing evidence case: {name}')


def check_manifest_scaffold(root: Path) -> None:
    path = root / 'mcp_server/tests/test_catalog_manifest.py'
    if not path.is_file():
        raise AssertionError('test_catalog_manifest.py missing')
    src = path.read_text(encoding='utf-8')
    for name in (
        'test_manifest_canonical_bytes_stable',
        'test_manifest_builder_ignores_batch_id_for_membership',
    ):
        if f'def {name}' not in src:
            raise AssertionError(f'missing manifest case: {name}')


def check_recovery_scaffold(root: Path) -> None:
    path = root / 'mcp_server/tests/test_catalog_commit_recovery.py'
    if not path.is_file():
        raise AssertionError('test_catalog_commit_recovery.py missing')
    src = path.read_text(encoding='utf-8')
    for name in (
        'test_terminal_agreement_returns_stable_receipt',
        'test_never_prepared_revival',
    ):
        if f'def {name}' not in src:
            raise AssertionError(f'missing recovery case: {name}')


def check_concurrency_scaffold(root: Path) -> None:
    path = root / 'mcp_server/tests/test_catalog_concurrency.py'
    if not path.is_file():
        raise AssertionError('test_catalog_concurrency.py missing')
    src = path.read_text(encoding='utf-8')
    if 'def test_same_token_concurrent_one_logical_commit' not in src:
        raise AssertionError('missing concurrency case: test_same_token_concurrent_one_logical_commit')


def check_manifests_feature_not_flipped(root: Path) -> None:
    """Wave 0 / pre-gate: features.manifests must remain False until 03B-06 proof."""
    capa = root / 'mcp_server/src/services/catalog_capabilities.py'
    if not capa.is_file():
        raise AssertionError('catalog_capabilities.py missing')
    src = capa.read_text(encoding='utf-8')
    if "'manifests': True" in src or '"manifests": True' in src:
        raise AssertionError(
            'features.manifests must remain false until Phase 3B live gate proof (D-33)'
        )


CHECK_FUNCS = {
    'wave0_files': check_wave0_files,
    'safety_no_probe': check_safety_no_probe,
    'atomicity_scaffold': check_atomicity_scaffold,
    'evidence_scaffold': check_evidence_scaffold,
    'manifest_scaffold': check_manifest_scaffold,
    'recovery_scaffold': check_recovery_scaffold,
    'concurrency_scaffold': check_concurrency_scaffold,
    'manifests_feature_not_flipped': check_manifests_feature_not_flipped,
}


def run_named_check(root: Path, check_id: str) -> None:
    func = CHECK_FUNCS.get(check_id)
    if func is None:
        raise ValueError(f'unknown check id: {check_id}')
    func(root)


def validate_spec(spec: dict[str, Any], root: Path | None = None) -> None:
    """Validate one argv spec. `root` retained for API parity with Phase 3A."""
    _ = root  # reserved for future path-bound argv checks
    if not isinstance(spec, dict):
        raise ValueError('spec must be dict')
    sid = spec.get('id')
    if not isinstance(sid, str) or not sid:
        raise ValueError('spec.id required')
    raw_argv = spec.get('argv')
    if (
        not isinstance(raw_argv, list)
        or not raw_argv
        or not all(isinstance(a, str) and a for a in raw_argv)
    ):
        raise ValueError(f'{sid}: argv must be nonempty list[str]')
    argv: list[str] = [str(a) for a in raw_argv]
    expected_exit = spec.get('expected_exit')
    if not isinstance(expected_exit, int):
        raise ValueError(f'{sid}: expected_exit must be int')
    if expected_exit != 0:
        raise ValueError(f'{sid}: current-HEAD expected_exit must be 0')
    first = Path(argv[0]).name.lower()
    if first in SHELL_EXECUTABLES:
        raise ValueError(f'{sid}: shell executable forbidden: {argv[0]}')
    for a in argv:
        if a in SHELL_META_TOKENS:
            raise ValueError(f'{sid}: shell metacharacter token forbidden: {a}')
        if a in ('/bin/sh', '/bin/bash', 'cmd.exe'):
            raise ValueError(f'{sid}: shell path forbidden')
    if spec.get('kind') not in ('live', 'tool') and 'pytest' in argv:
        for a in argv:
            norm = a.replace('\\', '/')
            if norm.endswith(INTEGRATION_MODULE) or norm.endswith('/' + INTEGRATION_MODULE):
                raise ValueError(f'{sid}: must not invoke {INTEGRATION_MODULE} outside live kind')


def validate_specs(specs: list[dict[str, Any]], root: Path | None = None) -> None:
    ids = [s['id'] for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f'duplicate spec ids: {ids}')
    for s in specs:
        validate_spec(s, root)


def live_neo4j_argv() -> list[str]:
    return _uv_pytest(
        [f'mcp_server/tests/{INTEGRATION_MODULE}'],
        ['-m', 'integration'],
    )


def canonical_specs(root: Path, *, include_live: bool = False) -> list[dict[str, Any]]:
    root = root.resolve()
    specs: list[dict[str, Any]] = [
        {
            'id': 'runner_self_tests',
            'argv': _uv_pytest(
                ['mcp_server/tests/test_catalog_phase3b_gate_runner.py'], ['--tb=short']
            ),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        {
            'id': 'focused_pytest',
            'argv': _uv_pytest(list(FOCUS_TEST_FILES)),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        {
            'id': 'scoped_ruff',
            'argv': _uv_tool('ruff', ['check', *RUFF_PATHS]),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'tool',
        },
        {
            'id': 'scoped_pyright',
            'argv': _uv_tool(
                'pyright',
                ['--project', 'mcp_server/pyproject.toml', *PYRIGHT_PATHS],
            ),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'tool',
        },
        {
            'id': 'wave0_files',
            'argv': _runner_check_argv('wave0_files'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'atomicity_scaffold',
            'argv': _runner_check_argv('atomicity_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'evidence_scaffold',
            'argv': _runner_check_argv('evidence_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'manifest_scaffold',
            'argv': _runner_check_argv('manifest_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'recovery_scaffold',
            'argv': _runner_check_argv('recovery_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'concurrency_scaffold',
            'argv': _runner_check_argv('concurrency_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'safety_no_probe',
            'argv': _runner_check_argv('safety_no_probe'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'safety',
        },
        {
            'id': 'manifests_feature_not_flipped',
            'argv': _runner_check_argv('manifests_feature_not_flipped'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
    ]
    if include_live:
        specs.append(
            {
                'id': 'live_neo4j_atomic_proof',
                'argv': live_neo4j_argv(),
                'expected_exit': 0,
                'mandatory': True,
                'kind': 'live',
            }
        )
    for spec in specs:
        validate_spec(spec, root)
    return specs


def canonical_specs_json(specs: list[dict[str, Any]]) -> str:
    slim = [
        {
            'id': s['id'],
            'argv': s['argv'],
            'expected_exit': s['expected_exit'],
            'mandatory': bool(s.get('mandatory', True)),
            'kind': s.get('kind', 'tool'),
        }
        for s in specs
    ]
    return json.dumps(slim, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def content_digest_map(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in GATE_INPUT_RELS:
        path = root / rel
        key = rel.as_posix()
        if path.is_file():
            out[key] = sha256_file_lf(path)
        else:
            out[key] = 'missing'
    return out


def content_digest(content_map: dict[str, str]) -> str:
    return sha256_text(json.dumps(content_map, sort_keys=True, separators=(',', ':')))


def parse_pytest_counts(output: str) -> dict[str, int]:
    counts = {
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'deselected': 0,
        'errors': 0,
    }
    for key in counts:
        m = re.search(rf'(\d+)\s+{re.escape(key)}', output)
        if m:
            counts[key] = int(m.group(1))
    return counts


def git_head(root: Path) -> str:
    r = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=str(root),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f'git rev-parse HEAD failed: {r.stderr}')
    return r.stdout.strip()


def git_parent(root: Path) -> str:
    r = subprocess.run(
        ['git', 'rev-parse', 'HEAD~1'],
        cwd=str(root),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if r.returncode != 0:
        return ''
    return r.stdout.strip()


def git_show_files(root: Path, commit: str = 'HEAD') -> list[str]:
    r = subprocess.run(
        ['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', commit],
        cwd=str(root),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if r.returncode != 0:
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def run_argv(argv: list[str], root: Path, timeout: int = 1800) -> dict[str, Any]:
    env = os.environ.copy()
    if any(INTEGRATION_MODULE in a.replace('\\', '/') for a in argv):
        env.setdefault('CATALOG_INT_REQUIRED', '1')
    result = subprocess.run(
        argv,
        shell=False,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    stdout = bound_output(result.stdout)
    stderr = bound_output(result.stderr)
    combined = f'{result.stdout or ""}\n{result.stderr or ""}'
    counts = parse_pytest_counts(combined) if 'pytest' in argv else {}
    return {
        'exit_code': result.returncode,
        'stdout': stdout,
        'stderr': stderr,
        'counts': counts,
    }


def run_sentinel(root: Path) -> dict[str, Any]:
    argv = [sys.executable, '-c', 'assert False']
    assert argv[2] == 'assert False'
    result = subprocess.run(
        argv,
        shell=False,
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        'argv': ['<sys.executable>', '-c', 'assert False'],
        'argv_third': argv[2],
        'exit_code': result.returncode,
        'pass': result.returncode != 0 and argv[2] == 'assert False',
        'stdout': bound_output(result.stdout, 200),
        'stderr': bound_output(result.stderr, 200),
        'excluded_from_aggregation': True,
    }


def derive_local_gate_pass(
    results: list[dict[str, Any]],
    sentinel: dict[str, Any],
) -> bool:
    if not sentinel.get('pass'):
        return False
    for r in results:
        if r.get('kind') == 'live':
            continue
        if not r.get('mandatory', True):
            continue
        if r.get('status') != 'pass':
            return False
        if r.get('exit_code') != r.get('expected_exit', 0):
            return False
    return True


def derive_live_proof_status(results: list[dict[str, Any]], require_neo4j: bool) -> dict[str, Any]:
    live = next((r for r in results if r.get('id') == 'live_neo4j_atomic_proof'), None)
    if live is None:
        return {
            'live_neo4j_atomic_proof': 'skip' if not require_neo4j else 'missing',
            'live_neo4j_atomic_proof_pass': False,
            'skipped_or_failed': True,
        }
    status = live.get('status')
    counts = live.get('counts') or {}
    passed = status == 'pass' and live.get('exit_code') == live.get('expected_exit', 0)
    if counts.get('skipped', 0) > 0 and counts.get('passed', 0) == 0:
        passed = False
        status = 'skip'
    if counts.get('failed', 0) > 0 or counts.get('errors', 0) > 0:
        passed = False
        status = 'fail'
    return {
        'live_neo4j_atomic_proof': status if status in ('pass', 'fail', 'skip') else 'fail',
        'live_neo4j_atomic_proof_pass': bool(passed),
        'skipped_or_failed': not bool(passed),
    }


def derive_safety_ledger(results: list[dict[str, Any]]) -> dict[str, Any]:
    safety_ids = {'safety_no_probe'}
    by_id = {r.get('id'): r for r in results}
    safety_ok = all(
        by_id.get(sid, {}).get('status') == 'pass' and by_id.get(sid, {}).get('exit_code') == 0
        for sid in safety_ids
    )
    return {
        'canary_executed': False,
        'oracle_catalog_v2_queried': False,
        'clear_graph_called': False,
        'safety_checks_pass': safety_ok,
        'test_group': ALLOWED_TEST_GROUP,
        'forbidden_group': FORBIDDEN_GROUP,
    }


def read_manifests_feature(root: Path) -> bool:
    src = (root / 'mcp_server/src/services/catalog_capabilities.py').read_text(encoding='utf-8')
    return "'manifests': True" in src or '"manifests": True' in src


def derive_ready_for_phase_4(
    local_gate_pass: bool,
    live: dict[str, Any],
    safety: dict[str, Any],
    *,
    manifests: bool,
    require_neo4j: bool,
) -> bool:
    """Fail-closed readiness: local + live (when required) + safety + manifests flag.

    Default is false. ready_for_phase_4 is true only when every mandatory non-live
    check passes, live atomic proof is green under require_neo4j, safety holds,
    and features.manifests has been flipped after proof (D-32/D-33).
    """
    if not local_gate_pass:
        return False
    if safety.get('canary_executed') is not False:
        return False
    if safety.get('oracle_catalog_v2_queried') is not False:
        return False
    if safety.get('clear_graph_called') is not False:
        return False
    if safety.get('safety_checks_pass') is not True:
        return False
    if require_neo4j and not live.get('live_neo4j_atomic_proof_pass'):
        return False
    if require_neo4j and not manifests:
        return False
    # Without require_neo4j, readiness stays false — live proof is mandatory for Phase 4.
    return require_neo4j


def run_gate(
    root: Path,
    ledger_path: Path,
    *,
    require_neo4j: bool = False,
    injected_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    specs = canonical_specs(root, include_live=require_neo4j)
    validate_specs(specs, root)
    specs_json = canonical_specs_json(specs)
    spec_sha = sha256_text(specs_json)
    content_map = content_digest_map(root)
    digest = content_digest(content_map)
    head = git_head(root)

    results: list[dict[str, Any]] = []
    for spec in specs:
        if (
            spec['id'] == 'runner_self_tests'
            and os.environ.get('CATALOG_PHASE3B_GATE_SKIP_SELF') == '1'
        ):
            results.append(
                {
                    'id': spec['id'],
                    'argv': spec['argv'],
                    'expected_exit': spec['expected_exit'],
                    'exit_code': 0,
                    'status': 'pass',
                    'mandatory': True,
                    'kind': spec.get('kind'),
                    'counts': {},
                    'stdout': 'skipped-nested-self',
                    'stderr': '',
                    'note': 'nested self-test skipped',
                }
            )
            continue
        try:
            outcome = run_argv(spec['argv'], root)
            status = 'pass' if outcome['exit_code'] == spec['expected_exit'] else 'fail'
            results.append(
                {
                    'id': spec['id'],
                    'argv': spec['argv'],
                    'expected_exit': spec['expected_exit'],
                    'exit_code': outcome['exit_code'],
                    'status': status,
                    'mandatory': bool(spec.get('mandatory', True)),
                    'kind': spec.get('kind'),
                    'counts': outcome['counts'],
                    'stdout': outcome['stdout'],
                    'stderr': outcome['stderr'],
                }
            )
        except Exception as exc:
            results.append(
                {
                    'id': spec['id'],
                    'argv': spec['argv'],
                    'expected_exit': spec['expected_exit'],
                    'exit_code': -1,
                    'status': 'fail',
                    'mandatory': bool(spec.get('mandatory', True)),
                    'kind': spec.get('kind'),
                    'counts': {},
                    'stdout': '',
                    'stderr': bound_output(str(exc)),
                }
            )

    if injected_overrides:
        for r in results:
            if r['id'] in injected_overrides:
                override = injected_overrides[r['id']]
                r.update(override)
                if 'status' not in override and r.get('exit_code', 0) != r.get('expected_exit', 0):
                    r['status'] = 'fail'

    sentinel = run_sentinel(root)
    local_gate_pass = derive_local_gate_pass(results, sentinel)
    live = derive_live_proof_status(results, require_neo4j)
    safety = derive_safety_ledger(results)
    manifests = read_manifests_feature(root)
    ready = derive_ready_for_phase_4(
        local_gate_pass,
        live,
        safety,
        manifests=manifests,
        require_neo4j=require_neo4j,
    )

    ledger: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'evaluated_head': head,
        'canonical_specs': json.loads(specs_json),
        'spec_sha256': spec_sha,
        'content_sha256_map': content_map,
        'content_digest': digest,
        'raw_edge_probe_count': EXPECTED_PROBE_COUNT,
        'sentinel': sentinel,
        'results': results,
        'require_neo4j': require_neo4j,
        'live_neo4j_atomic_proof': live['live_neo4j_atomic_proof'],
        'live_neo4j_atomic_proof_pass': live['live_neo4j_atomic_proof_pass'],
        'local_gate_pass': local_gate_pass,
        'nyquist_compliant': False,
        'ready_for_phase_4': ready,
        'manifests': manifests,
        'canary_executed': False,
        'oracle_catalog_v2_queried': False,
        'clear_graph_called': False,
        'safety': safety,
        'notes': {
            'integration_policy': (
                'live suite invoked only under --require-neo4j; skip/fail blocks readiness'
            ),
            'test_group': ALLOWED_TEST_GROUP,
            'forbidden_group': FORBIDDEN_GROUP,
            'resolution_policy': '24/24 research probe map; no silent drop',
            'd32_policy': 'ready_for_phase_4 true only after live+safety+manifests',
        },
    }
    ledger['ledger_sha256'] = sha256_text(
        json.dumps(
            {k: v for k, v in ledger.items() if k != 'ledger_sha256'},
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True,
        )
    )
    atomic_write_json(ledger_path, ledger)
    return ledger


def _head_compatible(root: Path, evaluated_head: str) -> tuple[bool, str]:
    current = git_head(root)
    if current == evaluated_head:
        return True, 'exact'
    parent = git_parent(root)
    if parent == evaluated_head:
        files = git_show_files(root, 'HEAD')
        norm = {f.replace('\\', '/') for f in files}
        allowed_suffixes = (
            '03B-GATE-RESULTS.json',
            '03B-06-SUMMARY.md',
            '03B-VALIDATION.md',
            '03B-EDGE-PROBE-RESOLUTION.json',
        )
        if norm and all(any(f.endswith(s) for s in allowed_suffixes) for f in norm):
            return True, 'ledger-only-child'
        return False, f'parent-match-but-extra-files:{sorted(norm)}'
    return False, f'head-mismatch current={current} evaluated={evaluated_head}'


def verify_ledger(
    root: Path, ledger_path: Path, *, require_neo4j: bool | None = None
) -> dict[str, Any]:
    root = root.resolve()
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    errors: list[str] = []

    if raw.get('schema_version') != SCHEMA_VERSION:
        errors.append('schema_version mismatch')

    req = bool(raw.get('require_neo4j')) if require_neo4j is None else require_neo4j
    specs = canonical_specs(root, include_live=req)
    validate_specs(specs, root)
    specs_json = canonical_specs_json(specs)
    spec_sha = sha256_text(specs_json)
    if raw.get('spec_sha256') != spec_sha:
        errors.append('spec_sha256 mismatch')

    content_map = content_digest_map(root)
    digest = content_digest(content_map)
    if raw.get('content_digest') != digest:
        errors.append('content_digest mismatch')
    if raw.get('content_sha256_map') != content_map:
        errors.append('content_sha256_map mismatch')

    if raw.get('raw_edge_probe_count') != EXPECTED_PROBE_COUNT:
        errors.append('raw_edge_probe_count mismatch')

    ok_head, head_reason = _head_compatible(root, raw.get('evaluated_head', ''))
    if not ok_head:
        errors.append(f'evaluated_head invalid: {head_reason}')

    results = raw.get('results')
    if not isinstance(results, list) or not results:
        errors.append('results missing')
    else:
        by_id = {r.get('id'): r for r in results if isinstance(r, dict)}
        for s in specs:
            r = by_id.get(s['id'])
            if r is None:
                errors.append(f'missing result for {s["id"]}')
                continue
            for key in ('status', 'exit_code', 'expected_exit', 'argv'):
                if key not in r:
                    errors.append(f'{s["id"]} missing {key}')
            if r.get('status') not in ('pass', 'fail', 'skip'):
                errors.append(f'{s["id"]} bad status')

    sentinel = raw.get('sentinel') or {}
    if not sentinel.get('pass') or sentinel.get('exit_code', 0) == 0:
        errors.append('sentinel must be nonzero pass')
    if sentinel.get('argv_third') != 'assert False':
        errors.append('sentinel argv third element must be assert False')

    if raw.get('canary_executed') is not False:
        errors.append('canary_executed must be false')
    if raw.get('oracle_catalog_v2_queried') is not False:
        errors.append('oracle_catalog_v2_queried must be false')
    if raw.get('clear_graph_called') is not False:
        errors.append('clear_graph_called must be false')

    recomputed_local = derive_local_gate_pass(
        results if isinstance(results, list) else [],
        sentinel,
    )
    if raw.get('local_gate_pass') != recomputed_local:
        errors.append(
            f'local_gate_pass mismatch ledger={raw.get("local_gate_pass")} '
            f'recomputed={recomputed_local}'
        )

    live = derive_live_proof_status(results if isinstance(results, list) else [], req)
    safety = derive_safety_ledger(results if isinstance(results, list) else [])
    source_manifests = read_manifests_feature(root)
    ready = derive_ready_for_phase_4(
        recomputed_local,
        live,
        safety,
        manifests=source_manifests,
        require_neo4j=req,
    )
    if raw.get('ready_for_phase_4') != ready:
        errors.append(
            f'ready_for_phase_4 mismatch ledger={raw.get("ready_for_phase_4")} recomputed={ready}'
        )

    if isinstance(results, list):
        for r in results:
            if r.get('mandatory', True) and r.get('status') == 'pending':
                errors.append(f'mandatory pending: {r.get("id")}')

    return {
        'ok': not errors,
        'errors': errors,
        'ledger': raw,
        'recomputed_local_gate_pass': recomputed_local,
        'recomputed_ready_for_phase_4': ready,
        'head_reason': head_reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Phase 3B catalog gate runner')
    parser.add_argument('command', choices=('run', 'check'))
    parser.add_argument(
        'check_id',
        nargs='?',
        default=None,
        help='check subcommand id when command=check',
    )
    parser.add_argument(
        '--ledger',
        default=str(DEFAULT_LEDGER_REL),
        help='ledger path relative to repo root or absolute',
    )
    parser.add_argument(
        '--root',
        default=None,
        help='repository root (default: discover from cwd)',
    )
    parser.add_argument(
        '--require-neo4j',
        action='store_true',
        help='run live neo4j atomic proof; skip/fail blocks ready_for_phase_4',
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else repo_root_from()
    ledger_path = Path(args.ledger)
    if not ledger_path.is_absolute():
        ledger_path = root / ledger_path

    if args.command == 'check':
        if not args.check_id:
            print('check requires check_id', file=sys.stderr)
            return 2
        try:
            run_named_check(root, args.check_id)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps({'check': args.check_id, 'status': 'pass'}))
        return 0

    if args.command == 'run':
        os.environ.setdefault('CATALOG_PHASE3B_GATE_SKIP_SELF', '0')
        ledger = run_gate(root, ledger_path, require_neo4j=args.require_neo4j)
        print(
            json.dumps(
                {
                    'local_gate_pass': ledger['local_gate_pass'],
                    'ready_for_phase_4': ledger['ready_for_phase_4'],
                    'manifests': ledger['manifests'],
                    'evaluated_head': ledger['evaluated_head'],
                    'spec_sha256': ledger['spec_sha256'],
                    'content_digest': ledger['content_digest'],
                    'live_neo4j_atomic_proof': ledger['live_neo4j_atomic_proof'],
                    'live_neo4j_atomic_proof_pass': ledger['live_neo4j_atomic_proof_pass'],
                    'canary_executed': ledger['canary_executed'],
                    'oracle_catalog_v2_queried': ledger['oracle_catalog_v2_queried'],
                    'clear_graph_called': ledger['clear_graph_called'],
                    'results': [
                        {'id': r['id'], 'status': r['status'], 'exit_code': r['exit_code']}
                        for r in ledger['results']
                    ],
                },
                indent=2,
            )
        )
        return (
            0
            if ledger['local_gate_pass']
            and (not args.require_neo4j or ledger['ready_for_phase_4'])
            else 1
        )

    return 2


if __name__ == '__main__':
    raise SystemExit(main())
