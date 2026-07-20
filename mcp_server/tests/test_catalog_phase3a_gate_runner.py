"""Unit tests for catalog_phase3a_gate_runner (no network dependency in unit path)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import catalog_phase3a_gate_runner as gate  # noqa: E402


def _root() -> Path:
    return gate.repo_root_from(Path(__file__))


def test_canonical_specs_shape_and_reject_shell_integration():
    root = _root()
    specs = gate.canonical_specs(root, include_live=False)
    assert specs
    ids = [s['id'] for s in specs]
    assert len(ids) == len(set(ids))
    assert 'focused_pytest' in ids
    assert 'scoped_ruff' in ids
    assert 'scoped_pyright' in ids
    assert 'safety_no_probe' in ids
    assert 'edge_probe_resolution' in ids
    assert 'prepare_commit_true' in ids
    assert 'control_plane_present' in ids
    assert 'live_neo4j_immutable_proof' not in ids

    focused = next(s for s in specs if s['id'] == 'focused_pytest')
    joined = ' '.join(focused['argv'])
    for token in (
        'test_catalog_prepare_models.py',
        'test_catalog_prepare_service.py',
        'test_catalog_capabilities.py',
        'test_catalog_token.py',
    ):
        assert token in joined
    for s in specs:
        gate.validate_spec(s, root)
        assert s['expected_exit'] == 0
        assert isinstance(s['argv'], list) and s['argv']
        if s.get('kind') not in ('tool', 'live') and 'pytest' in s['argv']:
            for a in s['argv']:
                norm = a.replace('\\', '/')
                assert not norm.endswith('test_catalog_prepare_neo4j_int.py')
        assert s['argv'][0].lower() not in gate.SHELL_EXECUTABLES

    live_specs = gate.canonical_specs(root, include_live=True)
    live_ids = [s['id'] for s in live_specs]
    assert 'live_neo4j_immutable_proof' in live_ids
    live = next(s for s in live_specs if s['id'] == 'live_neo4j_immutable_proof')
    assert live['kind'] == 'live'
    assert any('test_catalog_prepare_neo4j_int.py' in a.replace('\\', '/') for a in live['argv'])

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
            'mcp_server/tests/test_catalog_prepare_neo4j_int.py',
        ],
        'expected_exit': 0,
        'mandatory': True,
        'kind': 'pytest',
    }
    with pytest.raises(ValueError, match='test_catalog_prepare_neo4j_int'):
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
    a = gate.canonical_specs_json(gate.canonical_specs(root, include_live=True))
    b = gate.canonical_specs_json(gate.canonical_specs(root, include_live=True))
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
            'kind': 'pytest',
        },
        {
            'id': 'b',
            'status': 'fail',
            'exit_code': 1,
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'tool',
        },
    ]
    assert gate.derive_local_gate_pass(results, sentinel) is False
    results[1]['status'] = 'pass'
    results[1]['exit_code'] = 0
    assert gate.derive_local_gate_pass(results, sentinel) is True
    # live kind ignored for local pass
    results.append(
        {
            'id': 'live_neo4j_immutable_proof',
            'status': 'fail',
            'exit_code': 1,
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'live',
        }
    )
    assert gate.derive_local_gate_pass(results, sentinel) is True


def test_derive_ready_for_phase_3b_fail_closed():
    safety_ok = {
        'canary_executed': False,
        'oracle_catalog_v2_queried': False,
        'clear_graph_called': False,
        'no_domain_write_on_prepare': True,
        'no_external_call_on_commit': True,
        'safety_checks_pass': True,
    }
    live_pass = {
        'live_neo4j_immutable_proof': 'pass',
        'live_neo4j_immutable_proof_pass': True,
        'skipped_or_failed': False,
    }
    live_skip = {
        'live_neo4j_immutable_proof': 'skip',
        'live_neo4j_immutable_proof_pass': False,
        'skipped_or_failed': True,
    }
    live_fail = {
        'live_neo4j_immutable_proof': 'fail',
        'live_neo4j_immutable_proof_pass': False,
        'skipped_or_failed': True,
    }
    assert (
        gate.derive_ready_for_phase_3b(
            True, live_pass, safety_ok, prepare_commit=True, require_neo4j=True
        )
        is True
    )
    assert (
        gate.derive_ready_for_phase_3b(
            False, live_pass, safety_ok, prepare_commit=True, require_neo4j=True
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_3b(
            True, live_skip, safety_ok, prepare_commit=True, require_neo4j=True
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_3b(
            True, live_fail, safety_ok, prepare_commit=True, require_neo4j=True
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_3b(
            True, live_pass, safety_ok, prepare_commit=False, require_neo4j=True
        )
        is False
    )
    bad = dict(safety_ok, canary_executed=True)
    assert (
        gate.derive_ready_for_phase_3b(
            True, live_pass, bad, prepare_commit=True, require_neo4j=True
        )
        is False
    )
    bad2 = dict(safety_ok, clear_graph_called=True)
    assert (
        gate.derive_ready_for_phase_3b(
            True, live_pass, bad2, prepare_commit=True, require_neo4j=True
        )
        is False
    )
    bad3 = dict(safety_ok, no_domain_write_on_prepare=False)
    assert (
        gate.derive_ready_for_phase_3b(
            True, live_pass, bad3, prepare_commit=True, require_neo4j=True
        )
        is False
    )


def test_plan_ownership_covers_0_to_33_unique():
    covered: set[int] = set()
    for rows in gate.PLAN_OWNERSHIP.values():
        covered |= set(rows)
    assert covered == set(range(34))
    total = sum(len(v) for v in gate.PLAN_OWNERSHIP.values())
    assert total == 34


def test_injected_mandatory_failure_and_tamper_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '03A-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE3A_GATE_SKIP_SELF', '1')

    ledger = gate.run_gate(
        root,
        ledger_path,
        require_neo4j=False,
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
    assert ledger['ready_for_phase_3b'] is False
    assert ledger['schema_version'] == gate.SCHEMA_VERSION
    assert ledger['canary_executed'] is False
    assert ledger['oracle_catalog_v2_queried'] is False
    assert ledger['clear_graph_called'] is False
    ids = [r['id'] for r in ledger['results']]
    assert 'focused_pytest' in ids
    assert 'safety_no_probe' in ids
    assert 'prepare_commit_true' in ids

    # Tamper specs digest
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['spec_sha256'] = '0' * 64
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('spec_sha256' in e for e in ver['errors'])

    # Fresh fail ledger then HEAD tamper
    ledger = gate.run_gate(
        root,
        ledger_path,
        require_neo4j=False,
        injected_overrides={
            'focused_pytest': {'exit_code': 1, 'status': 'fail', 'stdout': '', 'stderr': ''}
        },
    )
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['evaluated_head'] = 'deadbeef' * 5
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('evaluated_head' in e for e in ver['errors'])

    # Missing result
    ledger = gate.run_gate(
        root,
        ledger_path,
        require_neo4j=False,
        injected_overrides={
            'focused_pytest': {'exit_code': 1, 'status': 'fail', 'stdout': '', 'stderr': ''}
        },
    )
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['results'] = [r for r in raw['results'] if r['id'] != 'scoped_ruff']
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('scoped_ruff' in e for e in ver['errors'])


def test_require_neo4j_skip_blocks_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root()
    ledger_path = tmp_path / '03A-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        joined = ' '.join(argv)
        if 'test_catalog_prepare_neo4j_int' in joined:
            return {
                'exit_code': 0,
                'stdout': '9 skipped',
                'stderr': '',
                'counts': {
                    'passed': 0,
                    'failed': 0,
                    'skipped': 9,
                    'deselected': 0,
                    'errors': 0,
                },
            }
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE3A_GATE_SKIP_SELF', '1')
    monkeypatch.setattr(gate, 'read_prepare_commit_feature', lambda _r: True)

    ledger = gate.run_gate(root, ledger_path, require_neo4j=True)
    assert ledger['local_gate_pass'] is True
    assert ledger['live_neo4j_immutable_proof_pass'] is False
    assert ledger['ready_for_phase_3b'] is False


def test_require_neo4j_pass_with_prepare_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root()
    ledger_path = tmp_path / '03A-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        joined = ' '.join(argv)
        if 'test_catalog_prepare_neo4j_int' in joined:
            return {
                'exit_code': 0,
                'stdout': '9 passed',
                'stderr': '',
                'counts': {
                    'passed': 9,
                    'failed': 0,
                    'skipped': 0,
                    'deselected': 0,
                    'errors': 0,
                },
            }
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE3A_GATE_SKIP_SELF', '1')
    monkeypatch.setattr(gate, 'read_prepare_commit_feature', lambda _r: True)

    ledger = gate.run_gate(root, ledger_path, require_neo4j=True)
    assert ledger['local_gate_pass'] is True
    assert ledger['live_neo4j_immutable_proof_pass'] is True
    assert ledger['prepare_commit'] is True
    assert ledger['ready_for_phase_3b'] is True
    assert ledger['no_domain_write_on_prepare'] is True
    assert ledger['no_external_call_on_commit'] is True


def test_no_integration_import_in_runner_source():
    module_file = gate.__file__
    assert module_file is not None
    src = Path(module_file).read_text(encoding='utf-8')
    import_lines = [
        ln for ln in src.splitlines() if ln.startswith('import ') or ln.startswith('from ')
    ]
    assert not any('test_catalog_prepare_neo4j_int' in ln for ln in import_lines)
    assert not any('test_catalog_neo4j_int' in ln for ln in import_lines)
    assert 'INTEGRATION_MODULE' in src
    assert 'test_catalog_prepare_neo4j_int' not in sys.modules
    assert 'ready_for_phase_3b' in src
    assert gate.FORBIDDEN_GROUP == 'oracle-catalog-v2'
    assert gate.ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    assert gate.EXPECTED_PROBE_COUNT == 34


def test_edge_probe_resolution_structure():
    root = _root()
    gate.check_edge_probe_resolution(root)
    res = json.loads((root / gate.DEFAULT_RESOLUTION_REL).read_text(encoding='utf-8'))
    assert len(res['entries']) == 34
    assert res['schema_version'] == gate.RESOLUTION_SCHEMA_VERSION
    assert res['no_silent_drop'] is True
