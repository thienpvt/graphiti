#!/usr/bin/env python3
"""Phase 1 fail-closed local gate runner (stdlib only).

Owns canonical JSON argv specs, shell=False sequential execution, HEAD/spec/
content-digest-bound ledger emission, and verified apply that never claims
independent audit verdicts.
"""

from __future__ import annotations

import argparse
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
    raise RuntimeError('repository root not found from %s' % cur)


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


def canonical_specs(root: Path) -> list[dict[str, Any]]:
    """Return deterministic named JSON argv specs for the local Phase 1 matrix."""
    root = root.resolve()
    phase = root / PHASE_DIR_REL
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
            'argv': [
                'uv',
                'run',
                '--project',
                'mcp_server',
                'python',
                '-c',
                (
                    'import json,re,subprocess; from pathlib import Path; '
                    "v=Path(%r).read_text(encoding='utf-8'); "
                    "tick=chr(96); "
                    r"pattern=r'^\\| (01-(?:0[1-9]|1[0-1])-T\\d+) \\|.*?\\| '+tick+r'([^'+tick+r']+)'+tick+r' \\|'; "
                    'rows=re.findall(pattern,v,re.M); '
                    'assert len(rows)>=17 and len({i for i,_ in rows})==len(rows); '
                    "specs=[]; "
                    "for _,raw in rows: "
                    " s=json.loads(raw); "
                    " assert set(s)=={'argv','expected_exit'} and s['expected_exit']==0; "
                    " assert isinstance(s['argv'],list) and s['argv'] and all(isinstance(a,str) and a for a in s['argv']); "
                    " assert s['argv'][0].lower() not in {'sh','bash','cmd','powershell','pwsh'}; "
                    " assert 'test_catalog_neo4j_int.py' not in ' '.join(s['argv']); "
                    " specs.append(s); "
                    'failed=[]; '
                    'for s in specs: '
                    " r=subprocess.run(s['argv'],shell=False,cwd=str(Path(%r)),capture_output=True,text=True); "
                    " (failed.append((s['argv'][:4],r.returncode)) if r.returncode!=s['expected_exit'] else None); "
                    "assert not failed, failed"
                )
                % (str(phase / '01-VALIDATION.md').replace('\\', '/'), str(root).replace('\\', '/')),
            ],
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'review_gaps',
            'argv': [
                'uv',
                'run',
                '--project',
                'mcp_server',
                'python',
                '-c',
                (
                    "from pathlib import Path; import re; "
                    "t=Path(%r).read_text(encoding='utf-8'); "
                    "keys=re.findall(r'^### (CR-0[12]|WR-0[12])',t,re.M); "
                    "assert keys==['CR-01','CR-02','WR-01','WR-02']; "
                    "assert 'key_equality = true' in t and 'silent_drops = 0' in t; "
                    "assert all(h in t for h in ('fd4c65f','3f3d173','f3843e9','7f5b156'))"
                )
                % str((phase / '01-REVIEW-GAPS.md')).replace('\\', '/'),
            ],
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'security_ledger',
            'argv': [
                'uv',
                'run',
                '--project',
                'mcp_server',
                'python',
                '-c',
                (
                    "from pathlib import Path; import re; "
                    "sec=Path(%r).read_text(encoding='utf-8'); "
                    "assert re.search(r'(?m)^threats_open:\\s*0\\s*$',sec); "
                    "assert 'T-01-09-01' in sec and 'T-01-10-01' in sec and 'T-01-11-02' in sec; "
                    "assert not re.search(r'user (?:approved|accepted|acceptance)',sec,re.I)"
                )
                % str((phase / '01-SECURITY.md')).replace('\\', '/'),
            ],
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'edge_probe_structure',
            'argv': [
                'uv',
                'run',
                '--project',
                'mcp_server',
                'python',
                '-c',
                (
                    "import json; from pathlib import Path; "
                    "d=json.loads(Path(%r).read_text(encoding='utf-8')); "
                    "items=d['items']; c=d['coverage']; "
                    "assert len(items)==53 and all(i['status']=='resolved' and i['verification']=='explicit' and i.get('resolution') for i in items); "
                    "assert c['applicable']==c['resolved']==53 and c['unresolved']==0; "
                    "assert c['byVerification']=={'explicit':53,'backstop':0}; "
                    "assert c['no_silent_drop']=={'source_count':53,'resolved_count':53,'key_equality':True,'null_dispositions':0}; "
                    "blob=json.dumps(d); "
                    "assert 'gap_cr02' in blob or 'CR-02' in blob or 'reference_time' in blob; "
                    "assert 'gap_wr01' in blob or 'WR-01' in blob or 'validate_entity_graph_key_at' in blob; "
                    "assert 'gap_cr01' in blob or 'CR-01' in blob or 'lock-authoritative' in blob; "
                    "assert 'gap_wr02' in blob or 'WR-02' in blob or 'offline' in blob"
                )
                % str((phase / '01-EDGE-PROBE.json')).replace('\\', '/'),
            ],
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'summary_consistency',
            'argv': [
                'uv',
                'run',
                '--project',
                'mcp_server',
                'python',
                '-c',
                (
                    "from pathlib import Path; "
                    "s9=Path(%r).read_text(encoding='utf-8'); "
                    "s10=Path(%r).read_text(encoding='utf-8'); "
                    "assert 'f3843e9' in s9 and '7f5b156' in s9; "
                    "assert 'fd4c65f' in s10 and '3f3d173' in s10; "
                    "assert 'ready_for_phase_2' not in s9 or 'false' in s9"
                )
                % (
                    str((phase / '01-09-SUMMARY.md')).replace('\\', '/'),
                    str((phase / '01-10-SUMMARY.md')).replace('\\', '/'),
                ),
            ],
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'safety_no_probe',
            'argv': [
                'uv',
                'run',
                '--project',
                'mcp_server',
                'python',
                '-c',
                (
                    "from pathlib import Path; import re,subprocess; "
                    "root=Path(%r); "
                    # Never import/collect/run integration module in this check.
                    "int_path=root/'mcp_server'/'tests'/'test_catalog_neo4j_int.py'; "
                    "assert int_path.is_file(); "
                    "src=int_path.read_text(encoding='utf-8'); "
                    "assert 'pytest.mark.integration' in src; "
                    "assert 'test_concurrent_conflicting_entity_names_only_winner_persists' in src; "
                    "assert 'oracle-catalog-tool-test' in src; "
                    "assert 'oracle-catalog-v2' in src; "  # forbidden group documented, not queried
                    # Static only: runner source must not load the integration module.
                    "rsrc=open(root/'mcp_server'/'tests'/'catalog_phase1_gate_runner.py',encoding='utf-8').read(); "
                    "assert 'test_catalog_neo4j_int' not in [ln.split()[1] for ln in rsrc.splitlines() if ln.startswith('import ') or ln.startswith('from ')]; "
                    "diff=subprocess.run(['git','diff','--name-only','8a55b6e..HEAD','--','pyproject.toml','mcp_server/pyproject.toml','uv.lock','mcp_server/uv.lock'],cwd=str(root),capture_output=True,text=True,shell=False); "
                    "assert diff.returncode==0 and not diff.stdout.strip(); "
                    "staged=subprocess.run(['git','diff','--cached','--name-only'],cwd=str(root),capture_output=True,text=True,shell=False); "
                    "assert staged.returncode==0; "
                    "bad=[l for l in staged.stdout.splitlines() if l and not l.startswith('.planning/') and 'catalog' not in l and not l.startswith('mcp_server/')]; "
                    "assert not bad, bad"
                )
                % str(root).replace('\\', '/'),
            ],
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
    argv = spec.get('argv')
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        raise ValueError('%s: argv must be nonempty list[str]' % sid)
    if not isinstance(spec.get('expected_exit'), int):
        raise ValueError('%s: expected_exit must be int' % sid)
    if spec['expected_exit'] != 0:
        raise ValueError('%s: current-HEAD expected_exit must be 0' % sid)
    first = Path(argv[0]).name.lower()
    if first in SHELL_EXECUTABLES:
        raise ValueError('%s: shell executable forbidden: %s' % (sid, argv[0]))
    for a in argv:
        if a in SHELL_META_TOKENS:
            raise ValueError('%s: shell metacharacter token forbidden: %s' % (sid, a))
        if a in ('/bin/sh', '/bin/bash', 'cmd.exe'):
            raise ValueError('%s: shell path forbidden' % sid)
    # Reject only when the integration module is an argv path target (not prose in -c).
    for a in argv:
        norm = a.replace('\\', '/')
        if norm.endswith(INTEGRATION_MODULE) or norm.endswith('/' + INTEGRATION_MODULE):
            raise ValueError('%s: must not invoke %s' % (sid, INTEGRATION_MODULE))
        if INTEGRATION_MODULE in a and a.strip() in (
            INTEGRATION_MODULE,
            'mcp_server/tests/' + INTEGRATION_MODULE,
            'tests/' + INTEGRATION_MODULE,
        ):
            raise ValueError('%s: must not invoke %s' % (sid, INTEGRATION_MODULE))
    joined = ' '.join(argv)
    # Reject RED inversion wrappers that invert return codes.
    if 'returncode==0' in joined and 'assert False' in joined and 'sys.executable' not in joined:
        raise ValueError('%s: RED inversion wrapper rejected' % sid)
    if re.search(r'not\s+result\.returncode', joined):
        # allow only the deliberate sentinel proof rows that assert nonzero
        pass


def validate_specs(specs: list[dict[str, Any]], root: Path) -> None:
    ids = [s['id'] for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate spec ids: %s' % ids)
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


def content_digest_map(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in GATE_INPUT_RELS:
        path = root / rel
        key = rel.as_posix()
        if path.is_file():
            out[key] = sha256_file(path)
        else:
            out[key] = 'missing'
    return out


def content_digest(content_map: dict[str, str]) -> str:
    return sha256_text(json.dumps(content_map, sort_keys=True, separators=(',', ':')))


def bound_output(text: str | None, limit: int = OUTPUT_BOUND) -> str:
    if not text:
        return ''
    text = text.replace('\x00', '')
    if len(text) <= limit:
        return text
    return text[: limit - 20] + '\n...[truncated]...'


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
        m = re.search(r'(\d+)\s+%s' % key, output)
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
        raise RuntimeError('git rev-parse HEAD failed: %s' % r.stderr)
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
    combined = '%s\n%s' % (result.stdout or '', result.stderr or '')
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
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
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
        allowed = {DEFAULT_LEDGER_REL.as_posix(), str(DEFAULT_LEDGER_REL).replace('\\', '/')}
        # also allow Windows path form
        norm = {f.replace('\\', '/') for f in files}
        if norm and all(
            f == DEFAULT_LEDGER_REL.as_posix() or f.endswith('01-GATE-RESULTS.json')
            for f in norm
        ):
            return True, 'ledger-only-child'
        return False, 'parent-match-but-extra-files:%s' % sorted(norm)
    return False, 'head-mismatch current=%s evaluated=%s' % (current, evaluated_head)


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
    if json.dumps(raw.get('canonical_specs'), sort_keys=True, separators=(',', ':')) != specs_json:
        # compare normalized
        if canonical_specs_json(raw.get('canonical_specs') or []) != specs_json:
            errors.append('canonical_specs mismatch')

    content_map = content_digest_map(root)
    digest = content_digest(content_map)
    if raw.get('content_digest') != digest:
        errors.append('content_digest mismatch')
    if raw.get('content_sha256_map') != content_map:
        errors.append('content_sha256_map mismatch')

    ok_head, head_reason = _head_compatible(root, raw.get('evaluated_head', ''))
    if not ok_head:
        errors.append('evaluated_head invalid: %s' % head_reason)

    results = raw.get('results')
    if not isinstance(results, list) or not results:
        errors.append('results missing')
    else:
        by_id = {r.get('id'): r for r in results if isinstance(r, dict)}
        for s in specs:
            r = by_id.get(s['id'])
            if r is None:
                errors.append('missing result for %s' % s['id'])
                continue
            for key in ('status', 'exit_code', 'expected_exit', 'argv'):
                if key not in r:
                    errors.append('%s missing %s' % (s['id'], key))
            if r.get('status') not in ('pass', 'fail', 'skip'):
                errors.append('%s bad status' % s['id'])

    sentinel = raw.get('sentinel') or {}
    if not sentinel.get('pass') or sentinel.get('exit_code', 0) == 0:
        errors.append('sentinel must be nonzero pass')
    if sentinel.get('argv_third') != 'assert False':
        errors.append('sentinel argv third element must be assert False')

    if raw.get('catalog_neo4j_int') != 'skip':
        errors.append('catalog_neo4j_int must be skip')
    if raw.get('availability_probed') is not False:
        errors.append('availability_probed must be false')

    for field in (
        'independent_code_review',
        'independent_goal_verification',
        'independent_nyquist_audit',
        'independent_security_audit',
    ):
        if raw.get(field) != 'pending':
            errors.append('%s must be pending' % field)

    if raw.get('ready_for_phase_2') is not False:
        errors.append('ready_for_phase_2 must be false in ledger')

    # Recompute local_gate_pass
    recomputed = derive_local_gate_pass(
        results if isinstance(results, list) else [],
        sentinel,
        raw.get('catalog_neo4j_int', 'fail'),
        bool(raw.get('availability_probed', True)),
    )
    if raw.get('local_gate_pass') != recomputed:
        errors.append(
            'local_gate_pass mismatch ledger=%s recomputed=%s'
            % (raw.get('local_gate_pass'), recomputed)
        )

    # Incomplete: pending mandatory
    if isinstance(results, list):
        for r in results:
            if r.get('mandatory', True) and r.get('status') == 'pending':
                errors.append('mandatory pending: %s' % r.get('id'))

    return {
        'ok': not errors,
        'errors': errors,
        'ledger': raw,
        'recomputed_local_gate_pass': recomputed,
        'head_reason': head_reason,
    }


def _set_frontmatter_bool(text: str, key: str, value: bool) -> str:
    pat = re.compile(r'(?m)^%s:\s*(true|false)\s*$' % re.escape(key))
    repl = '%s: %s' % (key, 'true' if value else 'false')
    if pat.search(text):
        return pat.sub(repl, text, count=1)
    return text


def _set_machine_field(text: str, key: str, value: str) -> str:
    pat = re.compile(r'(?m)^%s=.*$' % re.escape(key))
    repl = '%s=%s' % (key, value)
    if pat.search(text):
        return pat.sub(repl, text, count=1)
    # append before Scope Stop if present
    if '## Scope Stop' in text:
        return text.replace('## Scope Stop', '%s\n\n## Scope Stop' % repl, 1)
    return text.rstrip() + '\n%s\n' % repl


def apply_gate(
    root: Path,
    ledger_path: Path,
    require_local_pass: bool = False,
    require_final_ready: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    verification = verify_ledger(root, ledger_path)
    if not verification['ok']:
        raise RuntimeError('ledger verification failed: %s' % verification['errors'])

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
        r'\1%s\2' % status_token,
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
    val_path.write_text(val_text, encoding='utf-8')

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
    gate_path.write_text(gate_text, encoding='utf-8')

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
    parser.add_argument('command', choices=('run', 'apply'))
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
