"""Unit tests for catalog_phase3b_gate_runner (no network dependency in unit path).

Proves fail-closed ready_for_phase_4 default (D-32), live-group isolation (D-34),
and historical oracle-catalog-v2 hard gate that permanently blocks Phase 4.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import catalog_phase3b_gate_runner as gate  # noqa: E402


def _root() -> Path:
    return gate.repo_root_from(Path(__file__))


def test_ready_for_phase_4_false_without_live():
    """D-32: ready_for_phase_4 stays false when live proof is absent/skipped."""
    safety_ok = {
        'canary_executed': False,
        'oracle_catalog_v2_queried': False,
        'clear_graph_called': False,
        'safety_checks_pass': True,
    }
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
    # No require_neo4j → always false (live mandatory for Phase 4).
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, safety_ok, manifests=True, require_neo4j=False
        )
        is False
    )
    # require_neo4j but live skip → false
    assert (
        gate.derive_ready_for_phase_4(
            True, live_skip, safety_ok, manifests=True, require_neo4j=True
        )
        is False
    )
    # local fail → false even with live green
    assert (
        gate.derive_ready_for_phase_4(
            False, live_pass, safety_ok, manifests=True, require_neo4j=True
        )
        is False
    )
    # manifests not flipped → false
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, safety_ok, manifests=False, require_neo4j=True
        )
        is False
    )
    # pure-function full green still true when safety has no violation flags
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, safety_ok, manifests=True, require_neo4j=True
        )
        is True
    )


def test_ready_for_phase_4_false_on_safety_violation():
    """T-03B-GATE: canary / v2 / clear_graph flags block readiness."""
    live_pass = {
        'live_neo4j_atomic_proof': 'pass',
        'live_neo4j_atomic_proof_pass': True,
        'skipped_or_failed': False,
    }
    base = {
        'canary_executed': False,
        'oracle_catalog_v2_queried': False,
        'clear_graph_called': False,
        'safety_checks_pass': True,
    }
    for key in ('canary_executed', 'oracle_catalog_v2_queried', 'clear_graph_called'):
        bad = dict(base, **{key: True})
        assert (
            gate.derive_ready_for_phase_4(
                True, live_pass, bad, manifests=True, require_neo4j=True
            )
            is False
        )
    bad_safety = dict(base, safety_checks_pass=False)
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, bad_safety, manifests=True, require_neo4j=True
        )
        is False
    )


def test_historical_v2_hard_gate_in_derived_safety():
    """Historical a67789a read-only v2 probes permanently set oracle_catalog_v2_queried."""
    assert gate.HISTORICAL_ORACLE_CATALOG_V2_QUERIED is True
    safety = gate.derive_safety_ledger([], _root())
    assert safety['oracle_catalog_v2_queried'] is True
    assert safety['historical_oracle_catalog_v2_queried'] is True
    assert safety['safety_checks_pass'] is False
    # Current source may be clean of param queries; history still blocks.
    assert safety['current_source_v2_param_query'] is False
    live_pass = {
        'live_neo4j_atomic_proof': 'pass',
        'live_neo4j_atomic_proof_pass': True,
        'skipped_or_failed': False,
    }
    assert (
        gate.derive_ready_for_phase_4(
            True, live_pass, safety, manifests=True, require_neo4j=True
        )
        is False
    )


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
    # Top-level safety mirrors derived historical hard gate (not constant false).
    assert ledger['canary_executed'] is False
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['clear_graph_called'] is False
    assert ledger['safety']['oracle_catalog_v2_queried'] is True
    assert ledger['safety']['historical_oracle_catalog_v2_queried'] is True

    # Tamper specs digest
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


def test_require_neo4j_pass_still_blocked_by_historical_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Even live green + manifests true cannot open Phase 4 after historical v2 probe."""
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
    assert ledger['manifests'] is True  # patched read — product source is False
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['ready_for_phase_4'] is False
    assert ledger['safety']['historical_oracle_catalog_v2_queried'] is True


def test_verify_ledger_accepts_truthful_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """verify_ledger ok for consistent blocked ledger (v2 true, ready false)."""
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
    # Use real manifests read (False in product source under historical block).
    ledger = gate.run_gate(root, ledger_path, require_neo4j=False)
    assert ledger['ready_for_phase_4'] is False
    assert ledger['oracle_catalog_v2_queried'] is True
    assert ledger['manifests'] is False
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
    assert 'ready_for_phase_4' in src
    assert gate.FORBIDDEN_GROUP == 'oracle-catalog-v2'
    assert gate.ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    assert gate.EXPECTED_PROBE_COUNT == 24


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
    safety_ok = {
        'canary_executed': False,
        'oracle_catalog_v2_queried': False,
        'clear_graph_called': False,
        'safety_checks_pass': True,
    }
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
