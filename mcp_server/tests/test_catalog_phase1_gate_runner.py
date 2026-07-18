"""Unit tests for catalog_phase1_gate_runner (no network, no Neo4j)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure mcp_server/tests importable when collected via uv project root.
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import catalog_phase1_gate_runner as gate  # noqa: E402


def _root() -> Path:
    return gate.repo_root_from(Path(__file__))


def test_canonical_specs_shape_and_reject_shell_integration():
    root = _root()
    specs = gate.canonical_specs(root)
    assert specs
    ids = [s['id'] for s in specs]
    assert len(ids) == len(set(ids))
    assert 'focused_pytest' in ids
    assert 'gap_filter' in ids
    assert 'pure_fixture_unit' in ids
    assert 'scoped_ruff' in ids
    assert 'scoped_pyright' in ids
    assert 'safety_no_probe' in ids
    for s in specs:
        gate.validate_spec(s, root)
        assert s['expected_exit'] == 0
        assert isinstance(s['argv'], list) and s['argv']
        for a in s['argv']:
            norm = a.replace('\\', '/')
            assert not norm.endswith('test_catalog_neo4j_int.py')
            assert a.strip() not in (
                'test_catalog_neo4j_int.py',
                'mcp_server/tests/test_catalog_neo4j_int.py',
                'tests/test_catalog_neo4j_int.py',
            )
        assert s['argv'][0].lower() not in gate.SHELL_EXECUTABLES

    bad_shell = {
        'id': 'bad',
        'argv': ['bash', '-c', 'true'],
        'expected_exit': 0,
        'mandatory': True,
    }
    with pytest.raises(ValueError, match='shell'):
        gate.validate_spec(bad_shell, root)

    bad_meta = {
        'id': 'bad2',
        'argv': ['uv', 'run', '&&', 'echo'],
        'expected_exit': 0,
        'mandatory': True,
    }
    with pytest.raises(ValueError, match='metacharacter|shell'):
        gate.validate_spec(bad_meta, root)

    bad_int = {
        'id': 'bad3',
        'argv': [
            'uv',
            'run',
            '--project',
            'mcp_server',
            'python',
            '-m',
            'pytest',
            'mcp_server/tests/test_catalog_neo4j_int.py',
        ],
        'expected_exit': 0,
        'mandatory': True,
    }
    with pytest.raises(ValueError, match='test_catalog_neo4j_int'):
        gate.validate_spec(bad_int, root)


def test_sentinel_exact_third_element_nonzero():
    root = _root()
    sentinel = gate.run_sentinel(root)
    assert sentinel['argv_third'] == 'assert False'
    assert sentinel['exit_code'] != 0
    assert sentinel['pass'] is True
    assert sentinel['excluded_from_aggregation'] is True


def test_bound_output_and_pytest_counts():
    long = 'x' * 10000
    bounded = gate.bound_output(long, 100)
    assert len(bounded) <= 100
    assert 'truncated' in bounded
    counts = gate.parse_pytest_counts('===== 12 passed, 3 deselected, 1 failed in 2.0s =====')
    assert counts['passed'] == 12
    assert counts['deselected'] == 3
    assert counts['failed'] == 1


def test_deterministic_spec_digest():
    root = _root()
    a = gate.canonical_specs_json(gate.canonical_specs(root))
    b = gate.canonical_specs_json(gate.canonical_specs(root))
    assert a == b
    assert gate.sha256_text(a) == gate.sha256_text(b)


def test_derive_local_gate_pass_requires_all_mandatory():
    sentinel = {'pass': True, 'exit_code': 1, 'argv_third': 'assert False'}
    results = [
        {
            'id': 'a',
            'status': 'pass',
            'exit_code': 0,
            'expected_exit': 0,
            'mandatory': True,
        },
        {
            'id': 'b',
            'status': 'fail',
            'exit_code': 1,
            'expected_exit': 0,
            'mandatory': True,
        },
    ]
    assert (
        gate.derive_local_gate_pass(results, sentinel, 'skip', False) is False
    )
    results[1]['status'] = 'pass'
    results[1]['exit_code'] = 0
    assert gate.derive_local_gate_pass(results, sentinel, 'skip', False) is True
    assert gate.derive_local_gate_pass(results, sentinel, 'pass', False) is False
    assert gate.derive_local_gate_pass(results, sentinel, 'skip', True) is False


def test_continue_after_failure_via_injected_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Injected mandatory failure yields local_gate_pass=false; apply keeps flags false."""
    root = _root()
    # Use temp ledger + copy minimal docs into temp tree is heavy; instead monkeypatch
    # run_argv for non-sentinel specs to return pass quickly, then inject one failure.
    phase = root / gate.PHASE_DIR_REL
    doc_paths = [
        phase / '01-VALIDATION.md',
        phase / '01-PHASE1-GATE.md',
    ]
    originals = {p: p.read_text(encoding='utf-8') for p in doc_paths if p.is_file()}
    ledger_path = tmp_path / '01-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE1_GATE_SKIP_SELF', '1')

    ledger = gate.run_gate(
        root,
        ledger_path,
        injected_overrides={
            'focused_pytest': {
                'exit_code': 1,
                'status': 'fail',
                'stdout': 'forced failure',
                'stderr': '',
            }
        },
    )
    assert ledger['local_gate_pass'] is False
    assert ledger['ready_for_phase_2'] is False
    assert ledger['catalog_neo4j_int'] == 'skip'
    assert ledger['availability_probed'] is False
    assert ledger['independent_code_review'] == 'pending'
    assert all(r['id'] for r in ledger['results'])
    # ensure continue-after-failure recorded later specs
    ids = [r['id'] for r in ledger['results']]
    assert 'focused_pytest' in ids
    assert 'safety_no_probe' in ids
    assert ledger_path.is_file()

    # apply keeps flags false on failing ledger
    summary = gate.apply_gate(root, ledger_path, require_local_pass=False)
    assert summary['local_gate_pass'] is False
    assert summary['nyquist_compliant'] is False
    assert summary['ready_for_phase_2'] is False

    # require_local_pass must refuse on a freshly failing ledger
    ledger = gate.run_gate(
        root,
        ledger_path,
        injected_overrides={
            'focused_pytest': {
                'exit_code': 1,
                'status': 'fail',
                'stdout': 'forced failure',
                'stderr': '',
            }
        },
    )
    assert ledger['local_gate_pass'] is False
    with pytest.raises(RuntimeError, match='local_gate_pass'):
        gate.apply_gate(root, ledger_path, require_local_pass=True)

    # tamper specs digest
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['spec_sha256'] = '0' * 64
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path)
    assert ver['ok'] is False
    assert any('spec_sha256' in e for e in ver['errors'])

    # restore and tamper HEAD
    ledger = gate.run_gate(
        root,
        ledger_path,
        injected_overrides={
            'focused_pytest': {'exit_code': 1, 'status': 'fail', 'stdout': '', 'stderr': ''}
        },
    )
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['evaluated_head'] = 'deadbeef' * 5
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path)
    assert ver['ok'] is False
    assert any('evaluated_head' in e for e in ver['errors'])

    # missing result
    ledger = gate.run_gate(
        root,
        ledger_path,
        injected_overrides={
            'focused_pytest': {'exit_code': 1, 'status': 'fail', 'stdout': '', 'stderr': ''}
        },
    )
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['results'] = [r for r in raw['results'] if r['id'] != 'scoped_ruff']
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path)
    assert ver['ok'] is False
    assert any('scoped_ruff' in e for e in ver['errors'])

    # content digest tamper
    ledger = gate.run_gate(
        root,
        ledger_path,
        injected_overrides={
            'focused_pytest': {'exit_code': 1, 'status': 'fail', 'stdout': '', 'stderr': ''}
        },
    )
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['content_digest'] = '1' * 64
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path)
    assert ver['ok'] is False
    assert any('content_digest' in e for e in ver['errors'])

    # keep phase docs flags false after inject failure apply
    val = (phase / '01-VALIDATION.md').read_text(encoding='utf-8')
    assert 'nyquist_compliant: false' in val or 'nyquist_compliant: true' not in val[:200]
    # Re-apply clean false ledger to ensure docs stay false
    ledger = gate.run_gate(
        root,
        ledger_path,
        injected_overrides={
            'focused_pytest': {'exit_code': 1, 'status': 'fail', 'stdout': '', 'stderr': ''}
        },
    )
    gate.apply_gate(root, ledger_path)
    val = (phase / '01-VALIDATION.md').read_text(encoding='utf-8')
    assert 'nyquist_compliant: false' in val
    gtxt = (phase / '01-PHASE1-GATE.md').read_text(encoding='utf-8')
    assert 'ready_for_phase_2=false' in gtxt
    assert 'local_gate_pass=false' in gtxt or 'local_gate_pass=true' not in gtxt.split('## Gate Contract')[-1]
    # Restore gate docs so content digests for later real runs stay stable.
    for p, text in originals.items():
        p.write_text(text, encoding='utf-8')


def test_injected_mandatory_failure():
    """Alias name required by plan contains test_injected_mandatory_failure."""
    # Covered by test_continue_after_failure_via_injected_override; keep explicit node.
    root = _root()
    sentinel = gate.run_sentinel(root)
    results = [
        {
            'id': 'x',
            'status': 'fail',
            'exit_code': 2,
            'expected_exit': 0,
            'mandatory': True,
        }
    ]
    assert gate.derive_local_gate_pass(results, sentinel, 'skip', False) is False


def test_no_integration_import_in_runner_source():
    module_file = gate.__file__
    assert module_file is not None
    src = Path(module_file).read_text(encoding='utf-8')
    import_lines = [
        ln
        for ln in src.splitlines()
        if ln.startswith('import ') or ln.startswith('from ')
    ]
    assert not any('test_catalog_neo4j_int' in ln for ln in import_lines)
    assert 'INTEGRATION_MODULE' in src
    assert 'test_catalog_neo4j_int' not in sys.modules
