#!/usr/bin/env python3
"""Phase 4 fail-closed gate runner (stdlib only).

Wave 0 scaffold: structural checks + ready_for_phase_5 fail-closed defaults.
Product GREEN and full gate proofs land in 04-02..04-06 (D-30, D-31).

Never opens oracle-catalog-v2. Live proofs (when later added) stay on
oracle-catalog-tool-test only. Historical a67789a is immutable audit pointer only.
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
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 'phase4-gate-results.v1'
PHASE_DIR_REL = Path(
    '.planning/phases/04-manifest-backed-verification-and-read-only-diagnostics'
)
DEFAULT_LEDGER_REL = PHASE_DIR_REL / '04-GATE-RESULTS.json'
OUTPUT_BOUND = 4000
FORBIDDEN_GROUP = 'oracle-catalog-v2'
ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
TEST_GROUP = ALLOWED_TEST_GROUP
EXPECTED_PROBE_COUNT = 42

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
    PHASE_DIR_REL / '04-VALIDATION.md',
    PHASE_DIR_REL / '04-CONTEXT.md',
    PHASE_DIR_REL / '04-EDGE-PROBE-LEDGER.md',
    PHASE_DIR_REL / '04-01-SUMMARY.md',
    PHASE_DIR_REL / '04-02-SUMMARY.md',
    PHASE_DIR_REL / '04-03-SUMMARY.md',
    PHASE_DIR_REL / '04-04-SUMMARY.md',
    PHASE_DIR_REL / '04-05-SUMMARY.md',
    PHASE_DIR_REL / '04-06-SUMMARY.md',
)

FOCUS_TEST_FILES = (
    'mcp_server/tests/test_catalog_gates.py',
    'mcp_server/tests/test_catalog_manifest_read.py',
    'mcp_server/tests/test_catalog_verify_manifest.py',
    'mcp_server/tests/test_catalog_resolve_edges.py',
    'mcp_server/tests/test_catalog_evidence_read.py',
    'mcp_server/tests/test_catalog_phase4_gate_runner.py',
    'mcp_server/tests/test_catalog_capabilities.py',
    'mcp_server/tests/test_catalog_service.py',
    'mcp_server/tests/test_catalog_store_unit.py',
    'mcp_server/tests/test_catalog_manifest.py',
)

# Plan ownership for research probe rows 0..41 (42 probes).
PLAN_OWNERSHIP = {
    '04-01': frozenset(range(0, 7)),
    '04-02': frozenset(range(7, 14)),
    '04-03': frozenset(range(14, 21)),
    '04-04': frozenset(range(21, 28)),
    '04-05': frozenset(range(28, 35)),
    '04-06': frozenset(range(35, 42)),
}

# Historical audit (immutable pointer only — never rewrite a67789a).
HISTORICAL_ORACLE_CATALOG_V2_QUERIED = True
HISTORICAL_V2_COMMIT = 'a67789a'
HISTORICAL_V2_CLASS = 'test_policy'
HISTORICAL_V2_SCOPE = 'local_neo4j_no_corresponding_data'
HISTORICAL_V2_VIOLATION_NOTE = (
    'initial 03B-06 live suite (a67789a) queried oracle-catalog-v2 read-only for '
    'before/after group counts; local test-policy violation on local Neo4j with no '
    'corresponding production/second-schema data; permanent audit record; never query '
    'or mutate oracle-catalog-v2 again; Phase 4 preserves pointer only'
)

WAVE0_REQUIRED = (
    'mcp_server/tests/test_catalog_gates.py',
    'mcp_server/tests/test_catalog_manifest_read.py',
    'mcp_server/tests/test_catalog_verify_manifest.py',
    'mcp_server/tests/test_catalog_resolve_edges.py',
    'mcp_server/tests/test_catalog_evidence_read.py',
    'mcp_server/tests/catalog_phase4_gate_runner.py',
    'mcp_server/tests/test_catalog_phase4_gate_runner.py',
)

SCAFFOLD_CASES = {
    'gates_scaffold': (
        'mcp_server/tests/test_catalog_gates.py',
        (
            'test_reads_enabled_default_true_writes_false',
            'test_read_tools_when_writes_disabled',
            'test_reads_no_schema_write_embed',
            'test_missing_status_found_false',
        ),
    ),
    'manifest_read_scaffold': (
        'mcp_server/tests/test_catalog_manifest_read.py',
        (
            'test_manifest_page_stable_order',
            'test_graph_key_complete',
            'test_page_size_above_hard_max_fail_closed',
        ),
    ),
    'verify_manifest_scaffold': (
        'mcp_server/tests/test_catalog_verify_manifest.py',
        (
            'test_batch_only_uses_manifest',
            'test_expected_not_live_count',
            'test_missing_manifest_code',
            'test_exact_evidence',
        ),
    ),
    'resolve_edges_scaffold': (
        'mcp_server/tests/test_catalog_resolve_edges.py',
        (
            'test_resolve_typed_edges_fields',
            'test_anomalies',
            'test_writes_off',
        ),
    ),
    'evidence_read_scaffold': (
        'mcp_server/tests/test_catalog_evidence_read.py',
        (
            'test_evidence_page_bounded',
            'test_adjacency_multi_link',
            'test_full_graph_key_on_target',
        ),
    ),
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


def _runner_check_argv(check_id: str) -> list[str]:
    return [
        'uv',
        'run',
        '--project',
        'mcp_server',
        'python',
        'mcp_server/tests/catalog_phase4_gate_runner.py',
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


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomic JSON write via temp + os.replace only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + '\n'
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        last_err: PermissionError | None = None
        for attempt in range(8):
            try:
                os.replace(tmp_name, path)
                return
            except PermissionError as exc:
                last_err = exc
                time.sleep(0.05 * (attempt + 1))
        assert last_err is not None
        raise last_err
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
    missing = [rel for rel in WAVE0_REQUIRED if not (root / rel).is_file()]
    if missing:
        raise AssertionError(f'wave0 product/test files missing: {missing}')


def _require_defs(path: Path, names: tuple[str, ...], label: str) -> None:
    if not path.is_file():
        raise AssertionError(f'{label} missing: {path}')
    src = path.read_text(encoding='utf-8')
    for name in names:
        if f'def {name}' not in src:
            raise AssertionError(f'missing {label} case: {name}')


def check_gates_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['gates_scaffold']
    _require_defs(root / rel, names, 'gates')


def check_manifest_read_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['manifest_read_scaffold']
    _require_defs(root / rel, names, 'manifest_read')


def check_verify_manifest_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['verify_manifest_scaffold']
    _require_defs(root / rel, names, 'verify_manifest')


def check_resolve_edges_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['resolve_edges_scaffold']
    _require_defs(root / rel, names, 'resolve_edges')


def check_evidence_read_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['evidence_read_scaffold']
    _require_defs(root / rel, names, 'evidence_read')


def _non_comment_lines(src: str) -> list[str]:
    return [ln for ln in src.splitlines() if ln.strip() and not ln.lstrip().startswith('#')]


def check_safety_no_probe(root: Path) -> None:
    """No canary, no clear_graph, no oracle-catalog-v2 as write/query target in Phase 4 scaffolds."""
    for rel in WAVE0_REQUIRED:
        path = root / rel
        if not path.is_file():
            raise AssertionError(f'missing {rel}')
        src = path.read_text(encoding='utf-8')
        # Require bare GROUP/TEST_GROUP/group_id — not FORBIDDEN_GROUP / ALLOWED_TEST_GROUP.
        if re.search(
            rf"(?<![A-Za-z_])(GROUP|group_id|TEST_GROUP)\s*=\s*['\"]{re.escape(FORBIDDEN_GROUP)}['\"]",
            src,
        ):
            raise AssertionError(f'{rel} assigns forbidden group as write target')
        if re.search(r'\bclear_graph\s*\(', src):
            raise AssertionError(f'{rel} calls clear_graph')
        code = '\n'.join(_non_comment_lines(src))
        if re.search(r'\bcanary\s*\(', code, re.IGNORECASE):
            raise AssertionError(f'{rel} references canary execution')

    runner_src = (root / 'mcp_server/tests/catalog_phase4_gate_runner.py').read_text(
        encoding='utf-8'
    )
    if ALLOWED_TEST_GROUP not in runner_src:
        raise AssertionError('runner must hard-code oracle-catalog-tool-test')
    if FORBIDDEN_GROUP not in runner_src:
        raise AssertionError('runner must name forbidden group for ban checks')
    if HISTORICAL_V2_COMMIT not in runner_src:
        raise AssertionError('runner must preserve a67789a historical pointer')
    for line in runner_src.splitlines():
        if (line.startswith('import ') or line.startswith('from ')) and (
            'neo4j' in line.lower() and 'driver' in line.lower()
        ):
            raise AssertionError('runner must not import neo4j driver')


def check_manifest_verification_not_flipped(root: Path) -> None:
    """Wave 0 / until 04-06: features.manifest_verification must remain False."""
    capa = root / 'mcp_server/src/services/catalog_capabilities.py'
    if not capa.is_file():
        raise AssertionError('catalog_capabilities.py missing')
    src = capa.read_text(encoding='utf-8')
    if _manifest_verification_true_marker(src):
        raise AssertionError(
            'features.manifest_verification must remain false until plan 06 proofs (D-24)'
        )
    code_lines = [ln for ln in src.splitlines() if ln.strip() and not ln.lstrip().startswith('#')]
    code = '\n'.join(code_lines)
    for forbidden in ('GATE-RESULTS', '04-GATE', '.planning/phases', 'ready_for_phase_5'):
        if forbidden in code:
            raise AssertionError(
                f'catalog_capabilities must not read planning ledger ({forbidden})'
            )


def check_registration_contract(root: Path) -> None:
    """Wave 0: registration not yet 28; structural presence of CATALOG_TOOL_NAMES only."""
    path = root / 'mcp_server/src/graphiti_mcp_server.py'
    if not path.is_file():
        raise AssertionError('graphiti_mcp_server.py missing')
    src = path.read_text(encoding='utf-8')
    if 'CATALOG_TOOL_NAMES' not in src:
        raise AssertionError('CATALOG_TOOL_NAMES missing')


CHECK_FUNCS = {
    'wave0_files': check_wave0_files,
    'safety_no_probe': check_safety_no_probe,
    'gates_scaffold': check_gates_scaffold,
    'manifest_read_scaffold': check_manifest_read_scaffold,
    'verify_manifest_scaffold': check_verify_manifest_scaffold,
    'resolve_edges_scaffold': check_resolve_edges_scaffold,
    'evidence_read_scaffold': check_evidence_read_scaffold,
    'manifest_verification_not_flipped': check_manifest_verification_not_flipped,
    'registration_contract': check_registration_contract,
}


def run_named_check(root: Path, check_id: str) -> None:
    func = CHECK_FUNCS.get(check_id)
    if func is None:
        raise ValueError(f'unknown check id: {check_id}')
    func(root)


def validate_spec(spec: object, root: Path | None = None) -> None:
    _ = root
    if not isinstance(spec, dict):
        raise ValueError('spec must be dict')
    payload: dict[str, Any] = spec
    sid = payload.get('id')
    if not isinstance(sid, str) or not sid:
        raise ValueError('spec.id required')
    raw_argv = payload.get('argv')
    if (
        not isinstance(raw_argv, list)
        or not raw_argv
        or not all(isinstance(a, str) and a for a in raw_argv)
    ):
        raise ValueError(f'{sid}: argv must be nonempty list[str]')
    argv: list[str] = [str(a) for a in raw_argv]
    expected_exit = payload.get('expected_exit')
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


def validate_specs(specs: list[dict[str, Any]], root: Path | None = None) -> None:
    ids = [s['id'] for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f'duplicate spec ids: {ids}')
    for s in specs:
        validate_spec(s, root)


def canonical_specs(root: Path, *, include_live: bool = False) -> list[dict[str, Any]]:
    """Canonical argv specs. Live suite intentionally absent in Wave 0 (no Neo4j)."""
    root = root.resolve()
    _ = include_live  # reserved; Phase 4 unit gate does not require live
    specs: list[dict[str, Any]] = [
        {
            'id': 'runner_self_tests',
            'argv': _uv_pytest(
                ['mcp_server/tests/test_catalog_phase4_gate_runner.py'], ['--tb=short']
            ),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        {
            'id': 'wave0_files',
            'argv': _runner_check_argv('wave0_files'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'gates_scaffold',
            'argv': _runner_check_argv('gates_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'manifest_read_scaffold',
            'argv': _runner_check_argv('manifest_read_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'verify_manifest_scaffold',
            'argv': _runner_check_argv('verify_manifest_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'resolve_edges_scaffold',
            'argv': _runner_check_argv('resolve_edges_scaffold'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'evidence_read_scaffold',
            'argv': _runner_check_argv('evidence_read_scaffold'),
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
            'id': 'manifest_verification_not_flipped',
            'argv': _runner_check_argv('manifest_verification_not_flipped'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'registration_contract',
            'argv': _runner_check_argv('registration_contract'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
    ]
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
        out[key] = sha256_file_lf(path) if path.is_file() else 'missing'
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


def derive_safety_ledger(
    results: list[dict[str, Any]],
    root: Path | None = None,
) -> dict[str, Any]:
    """Two-axis safety: permanent historical audit + current execution safety."""
    safety_ids = {'safety_no_probe'}
    by_id = {r.get('id'): r for r in results}
    current_safety_ok = all(
        by_id.get(sid, {}).get('status') == 'pass' and by_id.get(sid, {}).get('exit_code') == 0
        for sid in safety_ids
    )
    canary_executed = False
    clear_called = False
    current_source_v2_param = False
    # Aggregate audit includes permanent history.
    v2_queried = HISTORICAL_ORACLE_CATALOG_V2_QUERIED or current_source_v2_param
    _ = root
    return {
        'canary_executed': canary_executed,
        'oracle_catalog_v2_queried': v2_queried,
        'clear_graph_called': clear_called,
        'safety_checks_pass': current_safety_ok,
        'test_group': ALLOWED_TEST_GROUP,
        'forbidden_group': FORBIDDEN_GROUP,
        'historical_oracle_catalog_v2_queried': HISTORICAL_ORACLE_CATALOG_V2_QUERIED,
        'historical_v2_commit': HISTORICAL_V2_COMMIT,
        'historical_v2_class': HISTORICAL_V2_CLASS,
        'historical_v2_scope': HISTORICAL_V2_SCOPE,
        'current_source_v2_param_query': current_source_v2_param,
        'historical_violation_note': HISTORICAL_V2_VIOLATION_NOTE,
    }


def _manifest_verification_true_marker(src: str) -> bool:
    """True when source text sets features.manifest_verification to True.

    Markers built without nested quote soup so parsers cannot report a false
    unterminated-string diagnostic on this check.
    """
    single = chr(39) + 'manifest_verification' + chr(39) + ': True'
    double = chr(34) + 'manifest_verification' + chr(34) + ': True'
    return single in src or double in src


def read_manifest_verification_feature(root: Path) -> bool:
    src = (root / 'mcp_server/src/services/catalog_capabilities.py').read_text(encoding='utf-8')
    return _manifest_verification_true_marker(src)


def derive_ready_for_phase_5(
    local_gate_pass: bool,
    safety: dict[str, Any],
    *,
    manifest_verification: bool,
    registration_pass: bool,
    unit_service_pass: bool,
) -> bool:
    """Fail-closed readiness for Phase 5 (D-31).

    Default false. True only when unit/service/registration + current safety pass
    and features.manifest_verification is proven true after proofs.
    """
    if not local_gate_pass:
        return False
    if not unit_service_pass:
        return False
    if not registration_pass:
        return False
    if safety.get('canary_executed') is not False:
        return False
    if safety.get('clear_graph_called') is not False:
        return False
    if safety.get('current_source_v2_param_query') is not False:
        return False
    if safety.get('safety_checks_pass') is not True:
        return False
    return bool(manifest_verification)


def derive_cli_exit_code(ledger: dict[str, Any]) -> int:
    """CLI process exit for `run`. Fail-closed on current safety axis."""
    if not ledger.get('local_gate_pass'):
        return 1
    safety = ledger.get('safety') or {}
    if safety.get('safety_checks_pass') is not True:
        return 1
    if ledger.get('canary_executed') is not False:
        return 1
    if ledger.get('clear_graph_called') is not False:
        return 1
    if safety.get('current_source_v2_param_query') is not False:
        return 1
    return 0


def run_gate(
    root: Path,
    ledger_path: Path,
    *,
    injected_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        if (
            spec['id'] == 'runner_self_tests'
            and os.environ.get('CATALOG_PHASE4_GATE_SKIP_SELF') == '1'
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
    safety = derive_safety_ledger(results, root)
    manifest_verification = read_manifest_verification_feature(root)
    # Wave 0: unit/service product suites and registration are not yet green.
    # Structural scaffolds may pass; readiness stays false until proofs (04-06).
    unit_service_pass = False
    registration_pass = False
    ready = derive_ready_for_phase_5(
        local_gate_pass,
        safety,
        manifest_verification=manifest_verification,
        registration_pass=registration_pass,
        unit_service_pass=unit_service_pass,
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
        'local_gate_pass': local_gate_pass,
        'nyquist_compliant': False,
        'ready_for_phase_5': ready,
        'phase_4_complete': ready,
        'manifest_verification': manifest_verification,
        'unit_service_pass': unit_service_pass,
        'registration_pass': registration_pass,
        'canary_executed': safety['canary_executed'],
        'oracle_catalog_v2_queried': safety['oracle_catalog_v2_queried'],
        'clear_graph_called': safety['clear_graph_called'],
        'safety': safety,
        'historical_audit': {
            'historical_oracle_catalog_v2_queried': HISTORICAL_ORACLE_CATALOG_V2_QUERIED,
            'commit': HISTORICAL_V2_COMMIT,
            'class': HISTORICAL_V2_CLASS,
            'scope': HISTORICAL_V2_SCOPE,
            'note': HISTORICAL_V2_VIOLATION_NOTE,
        },
        'notes': {
            'test_group': ALLOWED_TEST_GROUP,
            'forbidden_group': FORBIDDEN_GROUP,
            'resolution_policy': '42/42 research probe map; no silent drop',
            'd31_policy': (
                'ready_for_phase_5 true only after unit/service/registration + safety + '
                'manifest_verification proven; Wave 0 defaults false'
            ),
            'historical_v2_policy': HISTORICAL_V2_VIOLATION_NOTE,
            'no_canary': 'Phase 4 never executes canary; canary_executed always false',
            'no_v2': 'never query or mutate oracle-catalog-v2',
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Phase 4 catalog gate runner')
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
        os.environ.setdefault('CATALOG_PHASE4_GATE_SKIP_SELF', '0')
        ledger = run_gate(root, ledger_path)
        print(
            json.dumps(
                {
                    'local_gate_pass': ledger['local_gate_pass'],
                    'safety_checks_pass': (ledger.get('safety') or {}).get('safety_checks_pass'),
                    'ready_for_phase_5': ledger['ready_for_phase_5'],
                    'manifest_verification': ledger['manifest_verification'],
                    'evaluated_head': ledger['evaluated_head'],
                    'spec_sha256': ledger['spec_sha256'],
                    'content_digest': ledger['content_digest'],
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
        return derive_cli_exit_code(ledger)

    return 2


if __name__ == '__main__':
    raise SystemExit(main())
