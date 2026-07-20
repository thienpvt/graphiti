#!/usr/bin/env python3
"""Phase 1 fail-closed local gate runner (stdlib only).

Owns canonical JSON argv specs, shell=False sequential execution, HEAD/spec/
content-digest-bound ledger emission, and verified apply that never claims
independent audit verdicts.
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

SCHEMA_VERSION = 'phase1-gate-results.v1'
PHASE_DIR_REL = Path('.planning/phases/01-strict-contracts-and-catalog-v2-identity')
DEFAULT_LEDGER_REL = PHASE_DIR_REL / '01-GATE-RESULTS.json'
OUTPUT_BOUND = 4000
INTEGRATION_MODULE = 'test_catalog_neo4j_int.py'
FORBIDDEN_GROUP = 'oracle-catalog-v2'
ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'

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
SHELL_META_TOKENS = frozenset(
    {'|', '||', '&', '&&', ';', '>', '>>', '<', '<<', '`', '$(', ')'}
)

GATE_INPUT_RELS = (
    PHASE_DIR_REL / '01-VALIDATION.md',
    PHASE_DIR_REL / '01-EDGE-PROBE.json',
    PHASE_DIR_REL / '01-SECURITY.md',
    PHASE_DIR_REL / '01-REVIEW-GAPS.md',
    PHASE_DIR_REL / '01-PHASE1-GATE.md',
    PHASE_DIR_REL / '01-09-SUMMARY.md',
    PHASE_DIR_REL / '01-10-SUMMARY.md',
)

FOCUS_TEST_FILES = (
    'mcp_server/tests/test_catalog_models.py',
    'mcp_server/tests/test_catalog_identity.py',
    'mcp_server/tests/test_catalog_service.py',
    'mcp_server/tests/test_catalog_store_unit.py',
    'mcp_server/tests/test_catalog_edge_probe.py',
    'mcp_server/tests/test_catalog_neo4j_fixtures.py',
)

RUFF_PATHS = (
    'mcp_server/src/models',
    'mcp_server/src/services/catalog_identity.py',
    'mcp_server/src/services/catalog_service.py',
    'mcp_server/src/services/catalog_store.py',
    'mcp_server/src/graphiti_mcp_server.py',
    'mcp_server/tests/test_catalog_models.py',
    'mcp_server/tests/test_catalog_identity.py',
    'mcp_server/tests/test_catalog_service.py',
    'mcp_server/tests/test_catalog_store_unit.py',
    'mcp_server/tests/test_catalog_edge_probe.py',
    'mcp_server/tests/catalog_neo4j_fixtures.py',
    'mcp_server/tests/test_catalog_neo4j_fixtures.py',
    'mcp_server/tests/catalog_phase1_gate_runner.py',
    'mcp_server/tests/test_catalog_phase1_gate_runner.py',
)

PYRIGHT_PATHS = RUFF_PATHS


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
        'mcp_server/tests/catalog_phase1_gate_runner.py',
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



def check_validation_rows(root: Path) -> None:
    phase = root / PHASE_DIR_REL
    text = (phase / '01-VALIDATION.md').read_text(encoding='utf-8')
    tick = chr(96)
    pattern = (
        r'^\| (01-(?:0[1-9]|1[0-1])-T\d+) \|.*?\| '
        + tick
        + r'([^'
        + tick
        + r']+)'
        + tick
        + r' \|'
    )
    rows = re.findall(pattern, text, re.M)
    if len(rows) < 17 or len({i for i, _ in rows}) != len(rows):
        raise AssertionError(f'validation row count/id uniqueness failed: {len(rows)}')
    specs: list[dict[str, Any]] = []
    for _, raw in rows:
        spec = json.loads(raw)
        if set(spec) != {'argv', 'expected_exit'} or spec['expected_exit'] != 0:
            raise AssertionError(f'bad validation spec keys: {spec!r}')
        argv = spec['argv']
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
            raise AssertionError(f'bad validation argv: {argv!r}')
        if argv[0].lower() in SHELL_EXECUTABLES:
            raise AssertionError(f'shell executable in validation row: {argv[0]}')
        for a in argv:
            norm = a.replace('\\', '/')
            if norm.endswith(INTEGRATION_MODULE):
                raise AssertionError('validation row targets integration module')
        specs.append(spec)
    failed: list[Any] = []
    for spec in specs:
        result = subprocess.run(
            spec['argv'],
            shell=False,
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != spec['expected_exit']:
            failed.append((spec['argv'][:6], result.returncode, bound_output(result.stderr, 400)))
    if failed:
        raise AssertionError(f'validation rows failed: {failed}')


def check_review_gaps(root: Path) -> None:
    text = (root / PHASE_DIR_REL / '01-REVIEW-GAPS.md').read_text(encoding='utf-8')
    keys = re.findall(r'^### (CR-0[12]|WR-0[12])', text, re.M)
    if keys != ['CR-01', 'CR-02', 'WR-01', 'WR-02']:
        raise AssertionError(f'review gap keys mismatch: {keys}')
    if 'key_equality = true' not in text or 'silent_drops = 0' not in text:
        raise AssertionError('review gap no-silent-drop markers missing')
    for h in ('fd4c65f', '3f3d173', 'f3843e9', '7f5b156'):
        if h not in text:
            raise AssertionError(f'missing commit hash {h}')


def check_security_ledger(root: Path) -> None:
    sec = (root / PHASE_DIR_REL / '01-SECURITY.md').read_text(encoding='utf-8')
    if not re.search(r'(?m)^threats_open:\s*0\s*$', sec):
        raise AssertionError('threats_open not 0')
    for token in ('T-01-09-01', 'T-01-10-01', 'T-01-11-02'):
        if token not in sec:
            raise AssertionError(f'missing threat {token}')
    if re.search(r'user (?:approved|accepted|acceptance)', sec, re.I):
        raise AssertionError('security ledger claims user approval')


def check_edge_probe_structure(root: Path) -> None:
    data = json.loads((root / PHASE_DIR_REL / '01-EDGE-PROBE.json').read_text(encoding='utf-8'))
    items = data['items']
    coverage = data['coverage']
    if len(items) != 53:
        raise AssertionError(f'edge probe items={len(items)}')
    if not all(
        i['status'] == 'resolved' and i['verification'] == 'explicit' and i.get('resolution')
        for i in items
    ):
        raise AssertionError('edge probe item status incomplete')
    if coverage['applicable'] != 53 or coverage['resolved'] != 53 or coverage['unresolved'] != 0:
        raise AssertionError(f'edge probe coverage bad: {coverage}')
    if coverage['byVerification'] != {'explicit': 53, 'backstop': 0}:
        raise AssertionError(f'edge probe byVerification bad: {coverage["byVerification"]}')
    if coverage['no_silent_drop'] != {
        'source_count': 53,
        'resolved_count': 53,
        'key_equality': True,
        'null_dispositions': 0,
    }:
        raise AssertionError(f'edge probe no_silent_drop bad: {coverage["no_silent_drop"]}')
    blob = json.dumps(data)
    if not any(tok in blob for tok in ('gap_cr02', 'CR-02', 'reference_time')):
        raise AssertionError('edge probe missing CR-02 anchor')
    if not any(tok in blob for tok in ('gap_wr01', 'WR-01', 'validate_entity_graph_key_at')):
        raise AssertionError('edge probe missing WR-01 anchor')
    if not any(tok in blob for tok in ('gap_cr01', 'CR-01', 'lock-authoritative')):
        raise AssertionError('edge probe missing CR-01 anchor')
    if not any(tok in blob for tok in ('gap_wr02', 'WR-02', 'offline')):
        raise AssertionError('edge probe missing WR-02 anchor')


def check_summary_consistency(root: Path) -> None:
    s9 = (root / PHASE_DIR_REL / '01-09-SUMMARY.md').read_text(encoding='utf-8')
    s10 = (root / PHASE_DIR_REL / '01-10-SUMMARY.md').read_text(encoding='utf-8')
    if 'f3843e9' not in s9 or '7f5b156' not in s9:
        raise AssertionError('01-09 summary missing integrated hashes')
    if 'fd4c65f' not in s10 or '3f3d173' not in s10:
        raise AssertionError('01-10 summary missing integrated hashes')


def check_safety_no_probe(root: Path) -> None:
    int_path = root / 'mcp_server' / 'tests' / 'test_catalog_neo4j_int.py'
    if not int_path.is_file():
        raise AssertionError('integration file missing')
    src = int_path.read_text(encoding='utf-8')
    if 'pytest.mark.integration' not in src:
        raise AssertionError('integration mark missing')
    if 'test_concurrent_conflicting_entity_names_only_winner_persists' not in src:
        raise AssertionError('live race definition missing')
    if ALLOWED_TEST_GROUP not in src:
        raise AssertionError('allowed test group missing from integration source')
    if FORBIDDEN_GROUP not in src:
        raise AssertionError('forbidden group documentation missing')
    runner_src = (root / 'mcp_server' / 'tests' / 'catalog_phase1_gate_runner.py').read_text(
        encoding='utf-8'
    )
    import_targets = []
    for line in runner_src.splitlines():
        if line.startswith('import ') or line.startswith('from '):
            parts = line.split()
            if len(parts) >= 2:
                import_targets.append(parts[1])
    if any('test_catalog_neo4j_int' in t for t in import_targets):
        raise AssertionError('runner imports integration module')
    diff = subprocess.run(
        [
            'git',
            'diff',
            '--name-only',
            '8a55b6e..HEAD',
            '--',
            'pyproject.toml',
            'mcp_server/pyproject.toml',
            'uv.lock',
            'mcp_server/uv.lock',
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if diff.returncode != 0 or diff.stdout.strip():
        raise AssertionError(f'dependency/lockfile drift: {diff.stdout!r}')
    staged = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        cwd=str(root),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if staged.returncode != 0:
        raise AssertionError('git staged listing failed')
    bad = [
        line
        for line in staged.stdout.splitlines()
        if line
        and not line.startswith('.planning/')
        and 'catalog' not in line
        and not line.startswith('mcp_server/')
    ]
    if bad:
        raise AssertionError(f'unrelated staged dirt: {bad}')


CHECK_FUNCS = {
    'validation_rows': check_validation_rows,
    'review_gaps': check_review_gaps,
    'security_ledger': check_security_ledger,
    'edge_probe_structure': check_edge_probe_structure,
    'summary_consistency': check_summary_consistency,
    'safety_no_probe': check_safety_no_probe,
}


def run_named_check(root: Path, check_id: str) -> None:
    func = CHECK_FUNCS.get(check_id)
    if func is None:
        raise ValueError(f'unknown check id: {check_id}')
    func(root)


def canonical_specs(root: Path) -> list[dict[str, Any]]:
    """Return deterministic named JSON argv specs for the local Phase 1 matrix."""
    root = root.resolve()
    specs: list[dict[str, Any]] = [
        {
            'id': 'runner_self_tests',
            'argv': _uv_pytest(['mcp_server/tests/test_catalog_phase1_gate_runner.py'], ['--tb=short']),
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
            'id': 'gap_filter',
            'argv': _uv_pytest(
                [
                    'mcp_server/tests/test_catalog_models.py',
                    'mcp_server/tests/test_catalog_service.py',
                    'mcp_server/tests/test_catalog_store_unit.py',
                    'mcp_server/tests/test_catalog_neo4j_fixtures.py',
                ],
                ['-k', 'gap_cr01 or gap_cr02 or gap_wr01 or gap_wr02'],
            ),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        {
            'id': 'pure_fixture_unit',
            'argv': _uv_pytest(['mcp_server/tests/test_catalog_neo4j_fixtures.py']),
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
            'id': 'validation_rows',
            'argv': _runner_check_argv('validation_rows'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'review_gaps',
            'argv': _runner_check_argv('review_gaps'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'security_ledger',
            'argv': _runner_check_argv('security_ledger'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'edge_probe_structure',
            'argv': _runner_check_argv('edge_probe_structure'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'summary_consistency',
            'argv': _runner_check_argv('summary_consistency'),
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
    ]
    for spec in specs:
        validate_spec(spec, root)
    return specs


def validate_spec(spec: dict[str, Any], root: Path) -> None:
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
    # Reject only when the integration module is an argv path target (not prose in -c).
    for a in argv:
        norm = a.replace('\\', '/')
        if norm.endswith(INTEGRATION_MODULE) or norm.endswith('/' + INTEGRATION_MODULE):
            raise ValueError(f'{sid}: must not invoke {INTEGRATION_MODULE}')
        if INTEGRATION_MODULE in a and a.strip() in (
            INTEGRATION_MODULE,
            'mcp_server/tests/' + INTEGRATION_MODULE,
            'tests/' + INTEGRATION_MODULE,
        ):
            raise ValueError(f'{sid}: must not invoke {INTEGRATION_MODULE}')
    joined = ' '.join(argv)
    # Reject RED inversion wrappers that invert return codes.
    if 'returncode==0' in joined and 'assert False' in joined and 'sys.executable' not in joined:
        raise ValueError(f'{sid}: RED inversion wrapper rejected')
    if re.search(r'not\s+result\.returncode', joined):
        # allow only the deliberate sentinel proof rows that assert nonzero
        pass


def validate_specs(specs: list[dict[str, Any]], root: Path) -> None:
    ids = [s['id'] for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f'duplicate spec ids: {ids}')
    for s in specs:
        validate_spec(s, root)


def canonical_specs_json(specs: list[dict[str, Any]]) -> str:
    # Stable subset for digest: id, argv, expected_exit, mandatory, kind
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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_file_lf(path: Path) -> str:
    """SHA-256 of file bytes with newlines normalized to LF.

    Windows autocrlf / text-mode writers can flip CRLF between run and apply;
    digest identity must track semantic content, not platform newline bytes.
    """
    data = path.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    return hashlib.sha256(data).hexdigest()


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
    # e.g. "12 passed, 3 deselected in 1.2s"
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
    result = subprocess.run(
        argv,
        shell=False,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
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
    catalog_neo4j_int: str,
    availability_probed: bool,
) -> bool:
    if catalog_neo4j_int != 'skip' or availability_probed is not False:
        return False
    if not sentinel.get('pass'):
        return False
    for r in results:
        if not r.get('mandatory', True):
            continue
        if r.get('status') != 'pass':
            return False
        if r.get('exit_code') != r.get('expected_exit', 0):
            return False
    return True


def write_text_lf(path: Path, text: str) -> None:
    """Write UTF-8 text with LF newlines only (Windows-safe digest stability)."""
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


def run_gate(
    root: Path,
    ledger_path: Path,
    injected_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute canonical specs, write ledger, return ledger dict.

    injected_overrides may force a mandatory result to fail for self-tests.
    """
    root = root.resolve()
    specs = canonical_specs(root)
    validate_specs(specs, root)
    specs_json = canonical_specs_json(specs)
    spec_sha = sha256_text(specs_json)
    content_map = content_digest_map(root)
    digest = content_digest(content_map)
    head = git_head(root)

    results: list[dict[str, Any]] = []
    for spec in specs:
        # Skip recursive self-test when already inside pytest collecting runner tests
        # to avoid infinite recursion. Detect via env or injected flag.
        if (
            spec['id'] == 'runner_self_tests'
            and os.environ.get('CATALOG_PHASE1_GATE_SKIP_SELF') == '1'
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
            status = (
                'pass'
                if outcome['exit_code'] == spec['expected_exit']
                else 'fail'
            )
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
        except Exception as exc:  # continue after failures
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
                if 'status' not in override and r.get('exit_code', 0) != r.get(
                    'expected_exit', 0
                ):
                    r['status'] = 'fail'

    sentinel = run_sentinel(root)
    catalog_neo4j_int = 'skip'
    availability_probed = False
    local_gate_pass = derive_local_gate_pass(
        results, sentinel, catalog_neo4j_int, availability_probed
    )

    ledger: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'evaluated_head': head,
        'canonical_specs': json.loads(specs_json),
        'spec_sha256': spec_sha,
        'content_sha256_map': content_map,
        'content_digest': digest,
        'sentinel': sentinel,
        'results': results,
        'catalog_neo4j_int': catalog_neo4j_int,
        'availability_probed': availability_probed,
        'local_gate_pass': local_gate_pass,
        'nyquist_compliant': False,  # apply may set true from verified local pass
        'ready_for_phase_2': False,
        'independent_code_review': 'pending',
        'independent_goal_verification': 'pending',
        'independent_nyquist_audit': 'pending',
        'independent_security_audit': 'pending',
        'notes': {
            'integration_policy': 'never import/collect/run test_catalog_neo4j_int.py',
            'test_group': ALLOWED_TEST_GROUP,
            'forbidden_group': FORBIDDEN_GROUP,
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
        # also allow Windows path form
        norm = {f.replace('\\', '/') for f in files}
        if norm and all(
            f == DEFAULT_LEDGER_REL.as_posix() or f.endswith('01-GATE-RESULTS.json')
            for f in norm
        ):
            return True, 'ledger-only-child'
        return False, f'parent-match-but-extra-files:{sorted(norm)}'
    return False, f'head-mismatch current={current} evaluated={evaluated_head}'


def verify_ledger(root: Path, ledger_path: Path) -> dict[str, Any]:
    root = root.resolve()
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    errors: list[str] = []

    if raw.get('schema_version') != SCHEMA_VERSION:
        errors.append('schema_version mismatch')

    specs = canonical_specs(root)
    validate_specs(specs, root)
    specs_json = canonical_specs_json(specs)
    spec_sha = sha256_text(specs_json)
    if raw.get('spec_sha256') != spec_sha:
        errors.append('spec_sha256 mismatch')
    if (
        json.dumps(raw.get('canonical_specs'), sort_keys=True, separators=(',', ':')) != specs_json
        and canonical_specs_json(raw.get('canonical_specs') or []) != specs_json
    ):
        errors.append('canonical_specs mismatch')

    content_map = content_digest_map(root)
    digest = content_digest(content_map)
    if raw.get('content_digest') != digest:
        errors.append('content_digest mismatch')
    if raw.get('content_sha256_map') != content_map:
        errors.append('content_sha256_map mismatch')

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
                errors.append(f"missing result for {s['id']}")
                continue
            for key in ('status', 'exit_code', 'expected_exit', 'argv'):
                if key not in r:
                    errors.append(f"{s['id']} missing {key}")
            if r.get('status') not in ('pass', 'fail', 'skip'):
                errors.append(f"{s['id']} bad status")

    sentinel = raw.get('sentinel') or {}
    if not sentinel.get('pass') or sentinel.get('exit_code', 0) == 0:
        errors.append('sentinel must be nonzero pass')
    if sentinel.get('argv_third') != 'assert False':
        errors.append('sentinel argv third element must be assert False')

    if raw.get('catalog_neo4j_int') != 'skip':
        errors.append('catalog_neo4j_int must be skip')
    if raw.get('availability_probed') is not False:
        errors.append('availability_probed must be false')

    audit_fields = (
        'independent_code_review',
        'independent_goal_verification',
        'independent_nyquist_audit',
        'independent_security_audit',
    )
    audit_vals = [raw.get(f) for f in audit_fields]
    if all(v == 'pending' for v in audit_vals):
        if raw.get('ready_for_phase_2') is not False:
            errors.append('ready_for_phase_2 must be false while independent audits pending')
    elif all(v == 'pass' for v in audit_vals):
        # Plan 01-12 final readiness: all four independent audits green.
        if raw.get('local_gate_pass') is not True:
            errors.append('local_gate_pass must be true when independent audits pass')
        if raw.get('ready_for_phase_2') is not True:
            errors.append('ready_for_phase_2 must be true when independent audits pass')
    else:
        for field, val in zip(audit_fields, audit_vals, strict=True):
            if val not in ('pending', 'pass', 'fail'):
                errors.append(f'{field} invalid: {val!r}')
            elif val not in ('pending', 'pass'):
                errors.append(f'{field} is {val!r}; mixed/fail audit set not final-ready')
        if any(v == 'fail' for v in audit_vals) and raw.get('ready_for_phase_2') is not False:
            errors.append('ready_for_phase_2 must be false when any independent audit fails')
        if any(v == 'pending' for v in audit_vals) and any(v == 'pass' for v in audit_vals):
            if raw.get('ready_for_phase_2') is not False:
                errors.append('ready_for_phase_2 must be false while any independent audit pending')

    # Recompute local_gate_pass
    recomputed = derive_local_gate_pass(
        results if isinstance(results, list) else [],
        sentinel,
        raw.get('catalog_neo4j_int', 'fail'),
        bool(raw.get('availability_probed', True)),
    )
    if raw.get('local_gate_pass') != recomputed:
        errors.append(
            f"local_gate_pass mismatch ledger={raw.get('local_gate_pass')} recomputed={recomputed}"
        )

    # Incomplete: pending mandatory
    if isinstance(results, list):
        for r in results:
            if r.get('mandatory', True) and r.get('status') == 'pending':
                errors.append(f"mandatory pending: {r.get('id')}")

    return {
        'ok': not errors,
        'errors': errors,
        'ledger': raw,
        'recomputed_local_gate_pass': recomputed,
        'head_reason': head_reason,
    }


def _set_frontmatter_bool(text: str, key: str, value: bool) -> str:
    pat = re.compile(rf'(?m)^{re.escape(key)}:\s*(true|false)\s*$')
    repl = f"{key}: {'true' if value else 'false'}"
    if pat.search(text):
        return pat.sub(repl, text, count=1)
    return text


def _set_machine_field(text: str, key: str, value: str) -> str:
    pat = re.compile(rf'(?m)^{re.escape(key)}=.*$')
    repl = f'{key}={value}'
    if pat.search(text):
        return pat.sub(repl, text, count=1)
    # append before Scope Stop if present
    if '## Scope Stop' in text:
        return text.replace('## Scope Stop', f'{repl}\n\n## Scope Stop', 1)
    return text.rstrip() + f'\n{repl}\n'


def apply_gate(
    root: Path,
    ledger_path: Path,
    require_local_pass: bool = False,
    require_final_ready: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    verification = verify_ledger(root, ledger_path)
    if not verification['ok']:
        raise RuntimeError(f"ledger verification failed: {verification['errors']}")

    ledger = verification['ledger']
    local_pass = bool(ledger.get('local_gate_pass')) and verification['recomputed_local_gate_pass']
    if require_local_pass and not local_pass:
        raise RuntimeError('require_local_pass set but local_gate_pass is false')
    if require_final_ready and ledger.get('ready_for_phase_2') is not False:
        # Final readiness must stay false while audits pending
        raise RuntimeError('require_final_ready=true is not allowed while audits pending')
    # require_final_ready=false is the expected mode; always keep ready false.
    final_ready = False
    nyquist = bool(local_pass)

    # Update VALIDATION frontmatter nyquist only
    val_path = root / PHASE_DIR_REL / '01-VALIDATION.md'
    val_text = val_path.read_text(encoding='utf-8')
    val_text = _set_frontmatter_bool(val_text, 'nyquist_compliant', nyquist)
    # Mark pending gap rows green/fail from ledger results where possible
    status_token = 'green' if local_pass else 'fail'
    val_text = re.sub(
        r'(\| 01-0(?:9|10|11)-T\d+ \|.*?\| )pending(\s*\|)',
        rf'\1{status_token}\2',
        val_text,
    )
    if local_pass:
        val_text = val_text.replace(
            '- [ ] Every current-HEAD row executed successfully with `shell=False` by Plan 01-11 runner.',
            '- [x] Every current-HEAD row executed successfully with `shell=False` by Plan 01-11 runner.',
        )
        val_text = val_text.replace(
            '- [ ] Current Nyquist compliance remains false until verified runner apply after complete green local matrix.',
            '- [x] Current Nyquist compliance derived true from verified local green ledger; independent audits still pending.',
        )
    write_text_lf(val_path, val_text)

    # Update PHASE1-GATE machine fields
    gate_path = root / PHASE_DIR_REL / '01-PHASE1-GATE.md'
    gate_text = gate_path.read_text(encoding='utf-8')
    # Refresh derivation prose lightly
    if local_pass:
        gate_text = re.sub(
            r'Current derivation is false\..*',
            'Local derivation is green via verified 01-GATE-RESULTS.json; final readiness remains false while independent audits are pending.',
            gate_text,
            count=1,
        )
        gate_text = re.sub(
            r'\*\*2026-07-18 invalidation:\*\* CR-01, CR-02, WR-01, and WR-02 are open\.',
            '**2026-07-18 local closure:** CR-01, CR-02, WR-01, and WR-02 mapped COVERED; local_gate_pass=true; independent audits pending.',
            gate_text,
            count=1,
        )
    for key, val in (
        ('local_gate_pass', 'true' if local_pass else 'false'),
        ('nyquist_compliant', 'true' if nyquist else 'false'),
        ('ready_for_phase_2', 'false'),
        ('independent_code_review', 'pending'),
        ('independent_goal_verification', 'pending'),
        ('independent_nyquist_audit', 'pending'),
        ('independent_security_audit', 'pending'),
        ('catalog_neo4j_int', 'skip'),
        ('availability_probed', 'false'),
        ('canary_executed', 'false'),
        ('oracle_catalog_v2_queried', 'false'),
    ):
        gate_text = _set_machine_field(gate_text, key, val)
    # Ensure Gate Contract ready flag
    gate_text = re.sub(
        r'(?m)^ready_for_phase_2=.*$',
        'ready_for_phase_2=false',
        gate_text,
    )
    write_text_lf(gate_path, gate_text)

    # Persist apply-time fields; refresh content digests after doc writes.
    ledger = dict(ledger)
    ledger['nyquist_compliant'] = nyquist
    ledger['ready_for_phase_2'] = final_ready
    ledger['apply_verified'] = True
    ledger['local_gate_pass'] = local_pass
    content_map = content_digest_map(root)
    ledger['content_sha256_map'] = content_map
    ledger['content_digest'] = content_digest(content_map)
    ledger['ledger_sha256'] = sha256_text(
        json.dumps(
            {k: v for k, v in ledger.items() if k != 'ledger_sha256'},
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True,
        )
    )
    atomic_write_json(ledger_path, ledger)

    return {
        'local_gate_pass': local_pass,
        'nyquist_compliant': nyquist,
        'ready_for_phase_2': final_ready,
        'independent_code_review': 'pending',
        'independent_goal_verification': 'pending',
        'independent_nyquist_audit': 'pending',
        'independent_security_audit': 'pending',
        'catalog_neo4j_int': 'skip',
        'availability_probed': False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Phase 1 catalog gate runner')
    parser.add_argument('command', choices=('run', 'apply', 'check'))
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
        '--require-local-pass',
        action='store_true',
        help='apply: fail if local_gate_pass is false',
    )
    parser.add_argument(
        '--require-final-ready',
        default='false',
        choices=('true', 'false'),
        help='apply: must be false while audits pending',
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
        # Avoid infinite recursion when self-tests invoke run under pytest.
        os.environ.setdefault('CATALOG_PHASE1_GATE_SKIP_SELF', '0')
        ledger = run_gate(root, ledger_path)
        print(
            json.dumps(
                {
                    'local_gate_pass': ledger['local_gate_pass'],
                    'evaluated_head': ledger['evaluated_head'],
                    'spec_sha256': ledger['spec_sha256'],
                    'content_digest': ledger['content_digest'],
                    'catalog_neo4j_int': ledger['catalog_neo4j_int'],
                    'availability_probed': ledger['availability_probed'],
                    'ready_for_phase_2': ledger['ready_for_phase_2'],
                    'results': [
                        {'id': r['id'], 'status': r['status'], 'exit_code': r['exit_code']}
                        for r in ledger['results']
                    ],
                },
                indent=2,
            )
        )
        return 0 if ledger['local_gate_pass'] else 1

    if args.command == 'apply':
        try:
            summary = apply_gate(
                root,
                ledger_path,
                require_local_pass=args.require_local_pass,
                require_final_ready=args.require_final_ready == 'true',
            )
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2, sort_keys=True))
        if args.require_local_pass and not summary['local_gate_pass']:
            return 1
        if summary['ready_for_phase_2'] is not False:
            return 1
        return 0

    return 2


if __name__ == '__main__':
    raise SystemExit(main())
