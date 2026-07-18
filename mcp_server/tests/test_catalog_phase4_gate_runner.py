"""Unit tests for catalog_phase4_gate_runner (no network; Wave 0 fail-closed).

Proves ready_for_phase_5 defaults false without proofs (D-31), live-group
isolation (D-30), and historical a67789a pointer preservation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import catalog_phase4_gate_runner as gate  # noqa: E402


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


def test_ready_for_phase_5_false_without_proofs():
    """D-31: ready_for_phase_5 stays false when proofs absent (Wave 0 default)."""
    safety_ok = _current_clean_safety()
    # No unit/service, no registration, no manifest_verification.
    assert (
        gate.derive_ready_for_phase_5(
            True,
            safety_ok,
            manifest_verification=False,
            registration_pass=False,
            unit_service_pass=False,
        )
        is False
    )
    # Partial proofs still false.
    assert (
        gate.derive_ready_for_phase_5(
            True,
            safety_ok,
            manifest_verification=True,
            registration_pass=False,
            unit_service_pass=True,
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_5(
            True,
            safety_ok,
            manifest_verification=True,
            registration_pass=True,
            unit_service_pass=False,
        )
        is False
    )
    assert (
        gate.derive_ready_for_phase_5(
            False,
            safety_ok,
            manifest_verification=True,
            registration_pass=True,
            unit_service_pass=True,
        )
        is False
    )
    # Full proofs + safety → true (GREEN path reserved for 04-06).
    assert (
        gate.derive_ready_for_phase_5(
            True,
            safety_ok,
            manifest_verification=True,
            registration_pass=True,
            unit_service_pass=True,
        )
        is True
    )


def test_ready_for_phase_5_false_on_safety_violation():
    """Canary / clear_graph / current_source_v2 / safety_checks_pass block readiness."""
    base = _current_clean_safety()
    for key in ('canary_executed', 'clear_graph_called', 'current_source_v2_param_query'):
        bad = dict(base, **{key: True})
        if key == 'current_source_v2_param_query':
            bad['safety_checks_pass'] = False
        assert (
            gate.derive_ready_for_phase_5(
                True,
                bad,
                manifest_verification=True,
                registration_pass=True,
                unit_service_pass=True,
            )
            is False
        )
    bad_safety = dict(base, safety_checks_pass=False)
    assert (
        gate.derive_ready_for_phase_5(
            True,
            bad_safety,
            manifest_verification=True,
            registration_pass=True,
            unit_service_pass=True,
        )
        is False
    )


def test_historical_a67789a_pointer_preserved():
    """Historical audit commit a67789a is immutable pointer only."""
    assert gate.HISTORICAL_V2_COMMIT == 'a67789a'
    assert gate.HISTORICAL_ORACLE_CATALOG_V2_QUERIED is True
    assert gate.HISTORICAL_V2_CLASS == 'test_policy'
    assert gate.FORBIDDEN_GROUP == 'oracle-catalog-v2'
    assert gate.ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    assert gate.TEST_GROUP == 'oracle-catalog-tool-test'
    assert gate.EXPECTED_PROBE_COUNT == 42
    assert gate.SCHEMA_VERSION == 'phase4-gate-results.v1'


def test_default_ready_for_phase_5_constant_contract():
    """Empty/default ledger path: ready_for_phase_5 must not be assumed true."""
    safety_ok = _current_clean_safety()
    assert (
        gate.derive_ready_for_phase_5(
            False,
            safety_ok,
            manifest_verification=False,
            registration_pass=False,
            unit_service_pass=False,
        )
        is False
    )


def test_wave0_files_and_scaffolds_present():
    root = _root()
    gate.check_wave0_files(root)
    gate.check_gates_scaffold(root)
    gate.check_manifest_read_scaffold(root)
    gate.check_verify_manifest_scaffold(root)
    gate.check_resolve_edges_scaffold(root)
    gate.check_evidence_read_scaffold(root)
    gate.check_safety_no_probe(root)
    gate.check_manifest_verification_true(root)
    gate.check_registration_contract(root)


def test_canonical_specs_shape_and_reject_shell():
    root = _root()
    specs = gate.canonical_specs(root)
    assert specs
    ids = [s['id'] for s in specs]
    assert len(ids) == len(set(ids))
    assert 'wave0_files' in ids
    assert 'safety_no_probe' in ids
    assert 'gates_scaffold' in ids
    assert 'manifest_verification_true' in ids
    assert 'registration_contract' in ids
    for s in specs:
        gate.validate_spec(s, root)
        assert s['expected_exit'] == 0
        assert isinstance(s['argv'], list) and s['argv']
        assert s['argv'][0].lower() not in gate.SHELL_EXECUTABLES

    bad_shell = {
        'id': 'bad',
        'argv': ['bash', '-c', 'true'],
        'expected_exit': 0,
        'mandatory': True,
    }
    with pytest.raises(ValueError, match='shell'):
        gate.validate_spec(bad_shell, root)


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


def test_plan_ownership_covers_0_to_41_unique():
    covered: set[int] = set()
    for rows in gate.PLAN_OWNERSHIP.values():
        covered |= set(rows)
    assert covered == set(range(42))
    total = sum(len(v) for v in gate.PLAN_OWNERSHIP.values())
    assert total == 42


def test_atomic_write_json_raises_when_replace_always_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
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


def test_run_gate_post_proof_ready_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """run_gate after 04-06 proofs: ready_for_phase_5 true; canary false; history preserved."""
    root = _root()
    ledger_path = tmp_path / '04-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE4_GATE_SKIP_SELF', '1')
    ledger = gate.run_gate(root, ledger_path)
    assert ledger['canary_executed'] is False
    assert ledger['clear_graph_called'] is False
    assert ledger['oracle_catalog_v2_queried'] is True  # historical aggregate
    assert ledger['historical_audit']['commit'] == 'a67789a'
    assert ledger['manifest_verification'] is True
    assert ledger['schema_version'] == gate.SCHEMA_VERSION
    assert ledger['raw_edge_probe_count'] == 42
    assert ledger['unit_service_pass'] is True
    assert ledger['registration_pass'] is True
    assert ledger['ready_for_phase_5'] is True
    assert ledger['phase_4_complete'] is True
    assert ledger['api_coverage_detector'] is False
    assert gate.derive_cli_exit_code(ledger) == 0


def test_no_forbidden_group_as_test_target_in_scaffolds():
    import re

    root = _root()
    ban = re.compile(r"(?<![A-Za-z_])(GROUP|group_id|TEST_GROUP)\s*=\s*['\"]oracle-catalog-v2['\"]")
    for rel in gate.WAVE0_REQUIRED:
        src = (root / rel).read_text(encoding='utf-8')
        # Bare GROUP/TEST_GROUP assignment to v2 forbidden; FORBIDDEN_GROUP = '...' is ok.
        assert ban.search(src) is None, rel


def test_read_manifest_verification_feature_true_post_proof():
    root = _root()
    assert gate.read_manifest_verification_feature(root) is True


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
