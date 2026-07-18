"""Unit tests for catalog_phase3b_gate_runner (no network dependency in unit path).

Proves fail-closed ready_for_phase_4 default (D-32), live-group isolation (D-34),
and schema-v2 two-axis safety: permanent historical audit vs current execution safety.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import catalog_phase3b_gate_runner as gate  # noqa: E402


def _root() -> Path:
    return gate.repo_root_from(Path(__file__))


def _current_clean_safety(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        'canary_executed': False,
        'oracle_catalog_v2_queried': True,  # aggregate includes permanent history
        'clear_graph_called': False,
        'safety_checks_pass': True,
        'current_source_v2_param_query': False,
        'historical_oracle_catalog_v2_queried': True,
    }
    base.update(overrides)
    return base


def test_atomic_write_json_raises_when_replace_always_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Exhausted os.replace PermissionError: destination unchanged; temp cleaned; raise."""
    dest = tmp_path / 'ledger.json'
    original = '{"keep": true}\n'
    dest.write_text(original, encoding='utf-8')
    monkeypatch.setattr(gate.time, 'sleep', lambda _s: None)
    monkeypatch.setattr(
        gate.os,
        'replace',
        mock.Mock(side_effect=PermissionError('locked')),
    )
    with pytest.raises(PermissionError, match='locked'):
        gate.atomic_write_json(dest, {'new': True})
    assert dest.read_text(encoding='utf-8') == original
    leftover = list(tmp_path.glob('ledger.json.*.tmp'))
    assert leftover == []
    assert gate.os.replace.call_count == 8


def test_atomic_write_json_succeeds_after_transient_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Retry os.replace: first PermissionError then success; destination updated."""
    dest = tmp_path / 'ledger.json'
    dest.write_text('{"old": true}\n', encoding='utf-8')
    monkeypatch.setattr(gate.time, 'sleep', lambda _s: None)
    calls = {'n': 0}

    def flaky_replace(src: str, dst: str) -> None:
        calls['n'] += 1
        if calls['n'] < 3:
            raise PermissionError('transient')
        Path(dst).write_bytes(Path(src).read_bytes())
        Path(src).unlink(missing_ok=True)

    monkeypatch.setattr(gate.os, 'replace', flaky_replace)
    gate.atomic_write_json(dest, {'ok': True})
    assert calls['n'] == 3
    assert json.loads(dest.read_text(encoding='utf-8')) == {'ok': True}
    assert list(tmp_path.glob('ledger.json.*.tmp')) == []


def test_ready_for_phase_4_false_without_live():
    """D-32: ready_for_phase_4 stays false when live proof is absent/skipped."""
    safety_ok = _current_clean_safety()
    live_skip = {
        'live_neo4j_atomic_proof': 'skip',
        'live_neo4j_atomic_proof_pass': False,
        'skipped_or_failed': True,
    }
    live_pass = {
        'live_neo4j_atomic_proof': 'pass',
        'live_neo4j_atomic_proof_pass': True,
        'skipped_or_failed': False,
    }
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, safety_ok, manifests=True, require_neo4j=False
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_4(
            True, live_skip, safety_ok, manifests=True, require_neo4j=True
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_4(
            False, live_pass, safety_ok, manifests=True, require_neo4j=True
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, safety_ok, manifests=False, require_neo4j=True
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, safety_ok, manifests=True, require_neo4j=True
        )
        is True
    )


def test_ready_for_phase_4_false_on_current_safety_violation():
    """Current-axis canary / clear_graph / current_source_v2 / safety_checks_pass block."""
    live_pass = {
        'live_neo4j_atomic_proof': 'pass',
        'live_neo4j_atomic_proof_pass': True,
        'skipped_or_failed': False,
    }
    base = _current_clean_safety()
    for key in ('canary_executed', 'clear_graph_called', 'current_source_v2_param_query'):
        bad = dict(base, **{key: True})
        if key == 'current_source_v2_param_query':
            bad['safety_checks_pass'] = False
        assert (
            gate.derive_ready_for_phase_4(True, live_pass, bad, manifests=True, require_neo4j=True)
            is False
        )
    bad_safety = dict(base, safety_checks_pass=False)
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, bad_safety, manifests=True, require_neo4j=True
        )
        is False
    )
    hist_only = dict(base, oracle_catalog_v2_queried=True)
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, hist_only, manifests=True, require_neo4j=True
        )
        is True
    )


def test_historical_audit_permanent_current_safety_independent():
    """History always true on audit axis; current safety independent of history."""
    assert gate.HISTORICAL_ORACLE_CATALOG_V2_QUERIED is True
    assert gate.HISTORICAL_V2_COMMIT == 'a67789a'
    assert gate.HISTORICAL_V2_CLASS == 'test_policy'
    assert gate.HISTORICAL_V2_SCOPE == 'local_neo4j_no_corresponding_data'
    results = [
        {
            'id': 'safety_no_probe',
            'status': 'pass',
            'exit_code': 0,
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'safety',
        }
    ]
    safety_with_check = gate.derive_safety_ledger(results, _root())
    assert safety_with_check['historical_oracle_catalog_v2_queried'] is True
    assert safety_with_check['oracle_catalog_v2_queried'] is True
    assert safety_with_check['current_source_v2_param_query'] is False
    assert safety_with_check['safety_checks_pass'] is True
    assert safety_with_check['canary_executed'] is False
    assert safety_with_check['clear_graph_called'] is False
    live_pass = {
        'live_neo4j_atomic_proof': 'pass',
        'live_neo4j_atomic_proof_pass': True,
        'skipped_or_failed': False,
    }
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, safety_with_check, manifests=True, require_neo4j=True
        )
        is True
    )


def test_current_forbidden_reference_blocks_current_safety(tmp_path: Path):
    """current_source_v2_param_query true forces safety_checks_pass false and blocks ready."""
    root = tmp_path
    (root / 'mcp_server' / 'tests').mkdir(parents=True)
    live = root / 'mcp_server' / 'tests' / 'test_catalog_commit_neo4j_int.py'
    live.write_text(
        "params = {'g': 'oracle-catalog-v2'}\nexecute_query('MATCH (n)', params)\n",
        encoding='utf-8',
    )
    results = [
        {
            'id': 'safety_no_probe',
            'status': 'pass',
            'exit_code': 0,
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'safety',
        }
    ]
    safety = gate.derive_safety_ledger(results, root)
    assert safety['current_source_v2_param_query'] is True
    assert safety['oracle_catalog_v2_queried'] is True
    assert safety['safety_checks_pass'] is False
    live_pass = {
        'live_neo4j_atomic_proof': 'pass',
        'live_neo4j_atomic_proof_pass': True,
        'skipped_or_failed': False,
    }
    assert (
        gate.derive_ready_for_phase_4(True, live_pass, safety, manifests=True, require_neo4j=True)
        is False
    )
    assert (
        gate.derive_cli_exit_code(
            {
                'local_gate_pass': True,
                'ready_for_phase_4': False,
                'canary_executed': False,
                'clear_graph_called': False,
                'safety': safety,
            },
            require_neo4j=False,
        )
        == 1
    )


def test_history_erasure_rejected_by_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """verify_ledger rejects ledger that erases historical/aggregate v2 flags."""
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE3B_GATE_SKIP_SELF', '1')
    ledger = gate.run_gate(root, ledger_path, require_neo4j=False)
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['safety']['historical_oracle_catalog_v2_queried'] is True
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['oracle_catalog_v2_queried'] = False
    raw['safety']['oracle_catalog_v2_queried'] = False
    raw['safety']['historical_oracle_catalog_v2_queried'] = False
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    joined = ' '.join(ver['errors'])
    assert 'oracle_catalog_v2_queried' in joined or 'historical' in joined or 'erasure' in joined


def test_history_only_accepted_with_green_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """History true + current clean -> verify accepts; non-live ready false; CLI 0."""
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE3B_GATE_SKIP_SELF', '1')
    ledger = gate.run_gate(root, ledger_path, require_neo4j=False)
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['safety']['historical_oracle_catalog_v2_queried'] is True
    assert ledger['safety']['current_source_v2_param_query'] is False
    assert ledger['safety']['safety_checks_pass'] is True
    assert ledger['canary_executed'] is False
    assert ledger['clear_graph_called'] is False
    assert ledger['ready_for_phase_4'] is False
    assert ledger['phase_3b_complete'] is False
    assert ledger['pre_live_only'] is True
    assert ledger['manifests'] is False
    assert ledger['schema_version'] == gate.SCHEMA_VERSION
    assert ledger['schema_version'] == 'phase3b-gate-results.v2'
    assert ledger['historical_audit']['commit'] == 'a67789a'
    assert ledger['historical_audit']['class'] == 'test_policy'
    assert ledger['historical_audit']['scope'] == 'local_neo4j_no_corresponding_data'
    assert ledger['historical_audit']['note'] == gate.HISTORICAL_V2_VIOLATION_NOTE
    assert ledger['historical_audit']['historical_oracle_catalog_v2_queried'] is True
    ver = gate.verify_ledger(root, ledger_path, require_neo4j=False)
    assert ver['ok'] is True, ver['errors']
    assert gate.derive_cli_exit_code(ledger, require_neo4j=False) == 0


def test_green_with_history_allowed_under_synthetic_live_manifests():
    """History true does not block pure-function readiness when current axis green."""
    safety = _current_clean_safety()
    live_pass = {
        'live_neo4j_atomic_proof': 'pass',
        'live_neo4j_atomic_proof_pass': True,
        'skipped_or_failed': False,
    }
    assert (
        gate.derive_ready_for_phase_4(True, live_pass, safety, manifests=True, require_neo4j=True)
        is True
    )
    ledger = {
        'local_gate_pass': True,
        'ready_for_phase_4': True,
        'canary_executed': False,
        'oracle_catalog_v2_queried': True,
        'clear_graph_called': False,
        'safety': safety,
    }
    assert gate.derive_cli_exit_code(ledger, require_neo4j=True) == 0


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
    assert 'wave0_files' in ids
    assert 'atomicity_scaffold' in ids
    assert 'evidence_scaffold' in ids
    assert 'manifest_scaffold' in ids
    assert 'recovery_scaffold' in ids
    assert 'concurrency_scaffold' in ids
    assert 'manifests_feature_false' in ids
    assert 'edge_resolution_complete' in ids
    assert 'manifests_feature_true' not in ids
    assert 'manifests_feature_not_flipped' not in ids
    assert 'live_neo4j_atomic_proof' not in ids

    focused = next(s for s in specs if s['id'] == 'focused_pytest')
    joined = ' '.join(focused['argv'])
    for token in (
        'test_catalog_manifest.py',
        'test_catalog_atomic_writer.py',
        'test_catalog_concurrency.py',
    ):
        assert token in joined
    for s in specs:
        gate.validate_spec(s, root)
        assert s['expected_exit'] == 0
        assert isinstance(s['argv'], list) and s['argv']
        if s.get('kind') not in ('tool', 'live') and 'pytest' in s['argv']:
            for a in s['argv']:
                norm = a.replace('\\', '/')
                assert not norm.endswith('test_catalog_commit_neo4j_int.py')
        assert s['argv'][0].lower() not in gate.SHELL_EXECUTABLES

    live_specs = gate.canonical_specs(root, include_live=True)
    live_ids = [s['id'] for s in live_specs]
    assert 'live_neo4j_atomic_proof' in live_ids
    live = next(s for s in live_specs if s['id'] == 'live_neo4j_atomic_proof')
    assert live['kind'] == 'live'
    assert any('test_catalog_commit_neo4j_int.py' in a.replace('\\', '/') for a in live['argv'])

    bad_shell = {
        'id': 'bad',
        'argv': ['bash', '-c', 'true'],
        'expected_exit': 0,
        'mandatory': True,
    }
    with pytest.raises(ValueError, match='shell'):
        gate.validate_spec(bad_shell, root)

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
            'mcp_server/tests/test_catalog_commit_neo4j_int.py',
        ],
        'expected_exit': 0,
        'mandatory': True,
        'kind': 'pytest',
    }
    with pytest.raises(ValueError, match='test_catalog_commit_neo4j_int'):
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
    results.append(
        {
            'id': 'live_neo4j_atomic_proof',
            'status': 'fail',
            'exit_code': 1,
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'live',
        }
    )
    assert gate.derive_local_gate_pass(results, sentinel) is True


def test_plan_ownership_covers_0_to_23_unique():
    covered: set[int] = set()
    for rows in gate.PLAN_OWNERSHIP.values():
        covered |= set(rows)
    assert covered == set(range(24))
    total = sum(len(v) for v in gate.PLAN_OWNERSHIP.values())
    assert total == 24


def test_injected_mandatory_failure_keeps_ready_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE3B_GATE_SKIP_SELF', '1')

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
    assert ledger['ready_for_phase_4'] is False
    assert ledger['schema_version'] == gate.SCHEMA_VERSION
    assert ledger['canary_executed'] is False
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['clear_graph_called'] is False
    assert ledger['safety']['oracle_catalog_v2_queried'] is True
    assert ledger['safety']['historical_oracle_catalog_v2_queried'] is True

    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['spec_sha256'] = '0' * 64
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('spec_sha256' in e for e in ver['errors'])


def test_require_neo4j_skip_blocks_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        joined = ' '.join(argv)
        if 'test_catalog_commit_neo4j_int' in joined:
            return {
                'exit_code': 0,
                'stdout': '7 skipped',
                'stderr': '',
                'counts': {
                    'passed': 0,
                    'failed': 0,
                    'skipped': 7,
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
    monkeypatch.setenv('CATALOG_PHASE3B_GATE_SKIP_SELF', '1')
    monkeypatch.setattr(gate, 'read_manifests_feature', lambda _r: True)

    ledger = gate.run_gate(root, ledger_path, require_neo4j=True)
    assert ledger['local_gate_pass'] is True
    assert ledger['live_neo4j_atomic_proof_pass'] is False
    assert ledger['ready_for_phase_4'] is False
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['safety']['safety_checks_pass'] is True


def test_require_neo4j_pass_with_history_and_manifests_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Live green + manifests true + current clean -> ready true despite history audit."""
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        joined = ' '.join(argv)
        if 'test_catalog_commit_neo4j_int' in joined:
            return {
                'exit_code': 0,
                'stdout': '7 passed',
                'stderr': '',
                'counts': {
                    'passed': 7,
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
    monkeypatch.setenv('CATALOG_PHASE3B_GATE_SKIP_SELF', '1')
    monkeypatch.setattr(gate, 'read_manifests_feature', lambda _r: True)

    ledger = gate.run_gate(root, ledger_path, require_neo4j=True)
    assert ledger['local_gate_pass'] is True
    assert ledger['live_neo4j_atomic_proof_pass'] is True
    assert ledger['manifests'] is True
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['safety']['historical_oracle_catalog_v2_queried'] is True
    assert ledger['safety']['safety_checks_pass'] is True
    assert ledger['ready_for_phase_4'] is True
    assert gate.derive_cli_exit_code(ledger, require_neo4j=True) == 0


def test_verify_ledger_accepts_truthful_history_current_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """verify_ledger ok for history true + current clean + ready false non-live."""
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE3B_GATE_SKIP_SELF', '1')
    ledger = gate.run_gate(root, ledger_path, require_neo4j=False)
    assert ledger['ready_for_phase_4'] is False
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['manifests'] is False
    assert ledger['safety']['safety_checks_pass'] is True
    ver = gate.verify_ledger(root, ledger_path, require_neo4j=False)
    assert ver['ok'] is True, ver['errors']
    assert ver['recomputed_ready_for_phase_4'] is False


def test_no_integration_import_in_runner_source():
    module_file = gate.__file__
    assert module_file is not None
    src = Path(module_file).read_text(encoding='utf-8')
    import_lines = [
        ln for ln in src.splitlines() if ln.startswith('import ') or ln.startswith('from ')
    ]
    assert not any('test_catalog_commit_neo4j_int' in ln for ln in import_lines)
    assert not any('test_catalog_prepare_neo4j_int' in ln for ln in import_lines)
    assert 'INTEGRATION_MODULE' in src
    assert gate.FORBIDDEN_GROUP == 'oracle-catalog-v2'
    assert gate.ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    assert gate.EXPECTED_PROBE_COUNT == 24
    assert gate.SCHEMA_VERSION == 'phase3b-gate-results.v2'


def test_wave0_files_check_passes_after_scaffolds():
    root = _root()
    gate.check_wave0_files(root)
    gate.check_atomicity_scaffold(root)
    gate.check_evidence_scaffold(root)
    gate.check_manifest_scaffold(root)
    gate.check_recovery_scaffold(root)
    gate.check_concurrency_scaffold(root)
    gate.check_manifests_feature_false(root)
    gate.check_edge_resolution_complete(root)


def test_default_ready_for_phase_4_constant_contract():
    """Empty/default ledger path: ready_for_phase_4 must not be assumed true."""
    safety_ok = _current_clean_safety()
    live_missing = {
        'live_neo4j_atomic_proof': 'missing',
        'live_neo4j_atomic_proof_pass': False,
        'skipped_or_failed': True,
    }
    assert (
        gate.derive_ready_for_phase_4(
            False, live_missing, safety_ok, manifests=False, require_neo4j=False
        )
        is False
    )


def test_cli_exit_current_axis_only():
    """CLI success requires current safety; aggregate historical v2 alone does not fail."""
    clean_with_history = {
        'local_gate_pass': True,
        'ready_for_phase_4': False,
        'canary_executed': False,
        'oracle_catalog_v2_queried': True,
        'clear_graph_called': False,
        'safety': _current_clean_safety(),
    }
    assert gate.derive_cli_exit_code(clean_with_history, require_neo4j=False) == 0
    assert gate.derive_cli_exit_code(clean_with_history, require_neo4j=True) == 1

    blocked_current = {
        'local_gate_pass': True,
        'ready_for_phase_4': False,
        'canary_executed': False,
        'oracle_catalog_v2_queried': True,
        'clear_graph_called': False,
        'safety': _current_clean_safety(safety_checks_pass=False),
    }
    assert gate.derive_cli_exit_code(blocked_current, require_neo4j=False) == 1

    ready_with_history = dict(clean_with_history, ready_for_phase_4=True)
    assert gate.derive_cli_exit_code(ready_with_history, require_neo4j=True) == 0


def test_main_run_exits_zero_for_history_current_green_nonlive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """main(['run']) exits 0 when current axis green even with historical audit true."""
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'
    green_ledger = {
        'local_gate_pass': True,
        'ready_for_phase_4': False,
        'manifests': False,
        'evaluated_head': 'deadbeef',
        'spec_sha256': '0' * 64,
        'content_digest': '0' * 64,
        'live_neo4j_atomic_proof': 'skip',
        'live_neo4j_atomic_proof_pass': False,
        'canary_executed': False,
        'oracle_catalog_v2_queried': True,
        'clear_graph_called': False,
        'safety': _current_clean_safety(),
        'results': [],
    }

    def fake_run_gate(r, path, *, require_neo4j=False, injected_overrides=None):  # noqa: ARG001
        ledger_path.write_text(json.dumps(green_ledger), encoding='utf-8')
        return green_ledger

    monkeypatch.setattr(gate, 'run_gate', fake_run_gate)
    monkeypatch.setattr(gate, 'repo_root_from', lambda start=None: root)  # noqa: ARG005
    code = gate.main(['run', '--ledger', str(ledger_path), '--root', str(root)])
    assert code == 0


def test_main_run_exits_nonzero_when_current_safety_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'
    blocked = {
        'local_gate_pass': True,
        'ready_for_phase_4': False,
        'manifests': False,
        'evaluated_head': 'deadbeef',
        'spec_sha256': '0' * 64,
        'content_digest': '0' * 64,
        'live_neo4j_atomic_proof': 'skip',
        'live_neo4j_atomic_proof_pass': False,
        'canary_executed': False,
        'oracle_catalog_v2_queried': True,
        'clear_graph_called': False,
        'safety': _current_clean_safety(safety_checks_pass=False),
        'results': [],
    }

    def fake_run_gate(r, path, *, require_neo4j=False, injected_overrides=None):  # noqa: ARG001
        return blocked

    monkeypatch.setattr(gate, 'run_gate', fake_run_gate)
    monkeypatch.setattr(gate, 'repo_root_from', lambda start=None: root)  # noqa: ARG005
    code = gate.main(['run', '--ledger', str(ledger_path), '--root', str(root)])
    assert code == 1


def _fresh_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict]:
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE3B_GATE_SKIP_SELF', '1')
    ledger = gate.run_gate(root, ledger_path, require_neo4j=False)
    return ledger_path, ledger


def test_verify_rejects_missing_historical_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    del raw['historical_audit']
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('historical_audit missing' in e for e in ver['errors'])


def test_verify_rejects_wrong_historical_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['historical_audit']['commit'] = 'deadbeef'
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('historical_audit.commit' in e for e in ver['errors'])


def test_verify_rejects_wrong_historical_class(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['historical_audit']['class'] = 'production'
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('historical_audit.class' in e for e in ver['errors'])


def test_verify_rejects_wrong_historical_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['historical_audit']['scope'] = 'wrong_scope'
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('historical_audit.scope' in e for e in ver['errors'])


def test_verify_rejects_wrong_historical_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['historical_audit']['note'] = 'tampered note'
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('historical_audit.note' in e for e in ver['errors'])


def test_verify_rejects_nested_aggregate_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['safety']['oracle_catalog_v2_queried'] = False
    # keep top-level true so nested mismatch is the signal
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    joined = ' '.join(ver['errors'])
    assert 'safety.oracle_catalog_v2_queried' in joined


def test_verify_rejects_omitted_nested_historical_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    del raw['safety']['historical_oracle_catalog_v2_queried']
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('safety.historical_oracle_catalog_v2_queried missing' in e for e in ver['errors'])


def test_verify_rejects_current_axis_nested_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['safety']['safety_checks_pass'] = False  # derived is True for clean source
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('safety.safety_checks_pass mismatch' in e for e in ver['errors'])


def test_verify_rejects_missing_phase_3b_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger_path, _ = _fresh_ledger(tmp_path, monkeypatch)
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    del raw['phase_3b_complete']
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(_root(), ledger_path, require_neo4j=False)
    assert ver['ok'] is False
    assert any('phase_3b_complete missing' in e for e in ver['errors'])


def test_product_sourced_manifests_false_blocks_ready_with_synthetic_live():
    """Product-sourced manifests=False: synthetic live pass still ready false (pre-live)."""
    root = _root()
    assert gate.read_manifests_feature(root) is False
    safety = _current_clean_safety()
    live_pass = {
        'live_neo4j_atomic_proof': 'pass',
        'live_neo4j_atomic_proof_pass': True,
        'skipped_or_failed': False,
    }
    assert (
        gate.derive_ready_for_phase_4(
            True,
            live_pass,
            safety,
            manifests=gate.read_manifests_feature(root),
            require_neo4j=True,
        )
        is False
    )


def test_require_neo4j_pass_product_manifests_false_ready_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Integration path: live green but product manifests False => ready false."""
    root = _root()
    ledger_path = tmp_path / '03B-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        joined = ' '.join(argv)
        if 'test_catalog_commit_neo4j_int' in joined:
            return {
                'exit_code': 0,
                'stdout': '7 passed',
                'stderr': '',
                'counts': {
                    'passed': 7,
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
    monkeypatch.setenv('CATALOG_PHASE3B_GATE_SKIP_SELF', '1')
    # Do NOT patch read_manifests_feature — product source must remain False.

    ledger = gate.run_gate(root, ledger_path, require_neo4j=True)
    assert ledger['local_gate_pass'] is True
    assert ledger['live_neo4j_atomic_proof_pass'] is True
    assert ledger['manifests'] is False
    assert ledger['ready_for_phase_4'] is False
    assert ledger['phase_3b_complete'] is False
    assert ledger['pre_live_only'] is False
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['safety']['safety_checks_pass'] is True
    assert gate.derive_cli_exit_code(ledger, require_neo4j=True) == 1
