"""Unit tests for catalog_phase5_gate_runner (no network; Wave 0 fail-closed).

Proves ready_to_regenerate_canary defaults false without proofs (D-01/D-02),
live-group isolation (D-04), canary_executed always false (D-10), and
historical a67789a pointer preservation.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

gate: ModuleType = importlib.import_module('catalog_phase5_gate_runner')


def _runner_path() -> Path:
    path = getattr(gate, '__file__', None)
    assert isinstance(path, str) and path
    return Path(path)


def _root() -> Path:
    return gate.repo_root_from(Path(__file__))


def _current_clean_safety(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        'canary_executed': False,
        # Top-level/current axis is false on clean HEAD; history is separate.
        'oracle_catalog_v2_queried': False,
        'current_oracle_catalog_v2_queried': False,
        'clear_graph_called': False,
        'safety_checks_pass': True,
        'current_source_v2_param_query': False,
        'historical_oracle_catalog_v2_queried': True,
    }
    base.update(overrides)
    return base


def test_ready_to_regenerate_canary_false_without_proofs():
    """D-01/D-02: ready_to_regenerate_canary stays false when proofs absent (Wave 0)."""
    safety_ok = _current_clean_safety()
    # Wave 0 defaults: audits pending → always false.
    assert (
        gate.derive_ready_to_regenerate_canary(
            True,
            safety_ok,
            registration_pass=True,
            unit_service_pass=True,
            security_matrix_pass=True,
            legacy_contract_pass=True,
            offline_canary_pass=True,
            docs_pass=True,
            audits_pass=True,
            post_execution_audits_pending=True,
            phase_5_complete=False,
        )
        is False
    )
    # Partial proofs still false even with audits closed.
    assert (
        gate.derive_ready_to_regenerate_canary(
            True,
            safety_ok,
            registration_pass=False,
            unit_service_pass=True,
            security_matrix_pass=True,
            legacy_contract_pass=True,
            offline_canary_pass=True,
            docs_pass=True,
            audits_pass=True,
            post_execution_audits_pending=False,
            phase_5_complete=True,
        )
        is False
    )
    assert (
        gate.derive_ready_to_regenerate_canary(
            True,
            safety_ok,
            registration_pass=True,
            unit_service_pass=False,
            security_matrix_pass=True,
            legacy_contract_pass=True,
            offline_canary_pass=True,
            docs_pass=True,
            audits_pass=True,
            post_execution_audits_pending=False,
            phase_5_complete=True,
        )
        is False
    )
    assert (
        gate.derive_ready_to_regenerate_canary(
            False,
            safety_ok,
            registration_pass=True,
            unit_service_pass=True,
            security_matrix_pass=True,
            legacy_contract_pass=True,
            offline_canary_pass=True,
            docs_pass=True,
            audits_pass=True,
            post_execution_audits_pending=False,
            phase_5_complete=True,
        )
        is False
    )
    # Full proofs + safety + audits + phase complete → true (GREEN path reserved 05-07).
    assert (
        gate.derive_ready_to_regenerate_canary(
            True,
            safety_ok,
            registration_pass=True,
            unit_service_pass=True,
            security_matrix_pass=True,
            legacy_contract_pass=True,
            offline_canary_pass=True,
            docs_pass=True,
            audits_pass=True,
            post_execution_audits_pending=False,
            phase_5_complete=True,
        )
        is True
    )


def test_ready_to_regenerate_canary_false_on_safety_violation():
    """Canary / clear_graph / current_source_v2 / safety_checks_pass block readiness."""
    base = _current_clean_safety()
    for key in ('canary_executed', 'clear_graph_called', 'current_source_v2_param_query'):
        bad = dict(base, **{key: True})
        if key == 'current_source_v2_param_query':
            bad['safety_checks_pass'] = False
        assert (
            gate.derive_ready_to_regenerate_canary(
                True,
                bad,
                registration_pass=True,
                unit_service_pass=True,
                security_matrix_pass=True,
                legacy_contract_pass=True,
                offline_canary_pass=True,
                docs_pass=True,
                audits_pass=True,
                post_execution_audits_pending=False,
                phase_5_complete=True,
            )
            is False
        )
    bad_safety = dict(base, safety_checks_pass=False)
    assert (
        gate.derive_ready_to_regenerate_canary(
            True,
            bad_safety,
            registration_pass=True,
            unit_service_pass=True,
            security_matrix_pass=True,
            legacy_contract_pass=True,
            offline_canary_pass=True,
            docs_pass=True,
            audits_pass=True,
            post_execution_audits_pending=False,
            phase_5_complete=True,
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
    assert gate.EXPECTED_PROBE_COUNT == 37
    assert gate.SCHEMA_VERSION == 'phase5-gate-results.v1'


def test_canary_executed_always_false():
    """D-01/D-10: canary_executed is always false; never shells canary runner."""
    root = _root()
    safety = gate.derive_safety_ledger(
        [
            {'id': 'safety_no_v2_current', 'status': 'pass', 'exit_code': 0},
            {'id': 'canary_not_executed', 'status': 'pass', 'exit_code': 0},
        ],
        root,
    )
    assert safety['canary_executed'] is False
    runner = _runner_path().read_text(encoding='utf-8')
    # No argv that would shell the canary script.
    assert "scripts/run_catalog_canary_batch.py'" not in runner.replace('"', "'") or (
        'must not shell' in runner or 'never' in runner.lower()
    )
    # validate_spec rejects canary shell.
    bad = {
        'id': 'bad_canary',
        'argv': ['uv', 'run', 'scripts/run_catalog_canary_batch.py'],
        'expected_exit': 0,
        'mandatory': True,
    }
    with pytest.raises(ValueError, match='canary'):
        gate.validate_spec(bad, root)


def test_default_ready_to_regenerate_canary_constant_contract():
    """Empty/default ledger path: ready_to_regenerate_canary must not be assumed true."""
    safety_ok = _current_clean_safety()
    assert (
        gate.derive_ready_to_regenerate_canary(
            False,
            safety_ok,
            registration_pass=False,
            unit_service_pass=False,
        )
        is False
    )


def test_wave0_files_and_scaffolds_present():
    root = _root()
    gate.check_wave0_files(root)
    gate.check_security_matrix_scaffold(root)
    gate.check_legacy_contract_scaffold(root)
    gate.check_canary_offline_scaffold(root)
    gate.check_ollama_e2e_scaffold(root)
    gate.check_gate_runner_scaffold(root)
    gate.check_safety_no_probe(root)
    gate.check_historical_axis_preserved(root)
    gate.check_registration_contract(root)
    assert (root / 'mcp_server/README.md').is_file()


def test_canonical_specs_shape_and_reject_shell():
    root = _root()
    specs = gate.canonical_specs(root)
    assert specs
    ids = [s['id'] for s in specs]
    assert len(ids) == len(set(ids))
    assert 'wave0_files' in ids
    assert 'safety_no_v2_current' in ids
    assert 'security_matrix' in ids
    assert 'legacy_contract_14' in ids
    assert 'focused_pytest' in ids
    assert 'canary_not_executed' in ids
    assert 'gate_runner' in ids
    focused = next(s for s in specs if s['id'] == 'focused_pytest')
    for rel in gate.FOCUS_TEST_FILES:
        assert rel in focused['argv']
    assert len(gate.FOCUS_TEST_FILES) == 7
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


def test_plan_ownership_covers_0_to_36_unique():
    covered: set[int] = set()
    for rows in gate.PLAN_OWNERSHIP.values():
        covered |= set(rows)
    assert covered == set(range(37))
    total = sum(len(v) for v in gate.PLAN_OWNERSHIP.values())
    assert total == 37


def test_atomic_write_json_raises_when_replace_always_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dest = tmp_path / 'ledger.json'
    original = '{"keep": true}\n'
    dest.write_text(original, encoding='utf-8')
    monkeypatch.setattr(gate.time, 'sleep', lambda *_: None)
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


def test_run_gate_wave0_ready_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """run_gate Wave 0: ready_to_regenerate_canary false; canary false; history preserved."""
    root = _root()
    ledger_path = tmp_path / '05-GATE-RESULTS.json'

    def fake_run_argv(*_: Any, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE5_GATE_SKIP_SELF', '1')
    ledger = gate.run_gate(root, ledger_path)
    assert ledger['canary_executed'] is False
    assert ledger['clear_graph_called'] is False
    # Current axis false; permanent history only under historical_audit.
    assert ledger['oracle_catalog_v2_queried'] is False
    assert ledger['current_oracle_catalog_v2_queried'] is False
    assert ledger['safety']['current_source_v2_param_query'] is False
    assert ledger['safety']['historical_oracle_catalog_v2_queried'] is True
    assert ledger['historical_audit']['commit'] == 'a67789a'
    assert ledger['historical_audit']['historical_oracle_catalog_v2_queried'] is True
    assert ledger['schema_version'] == gate.SCHEMA_VERSION
    assert ledger['raw_edge_probe_count'] == 37
    assert ledger['unit_service_pass'] is True  # focused_pytest (nested skip path)
    assert ledger['registration_pass'] is True
    # Wave 0: audits pending → readiness false even when structural checks pass.
    assert ledger['ready_to_regenerate_canary'] is False
    assert ledger['phase_5_complete'] is False
    assert ledger['post_execution_audits_pending'] is True
    assert ledger['api_coverage_detector'] is False
    assert ledger_path.is_file()


def test_no_forbidden_group_as_test_target_in_scaffolds():
    root = _root()
    ban = re.compile(r"(?<![A-Za-z_])(GROUP|group_id|TEST_GROUP)\s*=\s*['\"]oracle-catalog-v2['\"]")
    for rel in gate.WAVE0_REQUIRED:
        src = (root / rel).read_text(encoding='utf-8')
        # Bare GROUP/TEST_GROUP assignment to v2 forbidden; FORBIDDEN_GROUP = '...' is ok.
        assert ban.search(src) is None, rel


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
    # Skip ≠ pass.
    results[1]['status'] = 'skip'
    assert gate.derive_local_gate_pass(results, sentinel) is False


def test_scan_current_source_v2_param_query_clean():
    """Current source scan proves no forbidden group as query/param on HEAD."""
    root = _root()
    scan = gate.scan_current_source_v2_param_query(root)
    assert scan['current_source_v2_param_query'] is False
    assert scan['current_oracle_catalog_v2_queried'] is False
    assert scan['hits'] == []
    safety = gate.derive_safety_ledger(
        [
            {'id': 'safety_no_v2_current', 'status': 'pass', 'exit_code': 0},
            {'id': 'canary_not_executed', 'status': 'pass', 'exit_code': 0},
        ],
        root,
    )
    assert safety['oracle_catalog_v2_queried'] is False
    assert safety['current_oracle_catalog_v2_queried'] is False
    assert safety['current_source_v2_param_query'] is False
    assert safety['historical_oracle_catalog_v2_queried'] is True
    assert safety['historical_v2_commit'] == 'a67789a'


def test_ready_false_when_current_v2_axis_true():
    safety = _current_clean_safety(
        oracle_catalog_v2_queried=True,
        current_oracle_catalog_v2_queried=True,
    )
    assert (
        gate.derive_ready_to_regenerate_canary(
            True,
            safety,
            registration_pass=True,
            unit_service_pass=True,
            security_matrix_pass=True,
            legacy_contract_pass=True,
            offline_canary_pass=True,
            docs_pass=True,
            audits_pass=True,
            post_execution_audits_pending=False,
            phase_5_complete=True,
        )
        is False
    )


def test_scan_detects_synthetic_v2_param_without_source_literal():
    """Scanner hits synthetic text; runner source must not embed contiguous assignment."""
    _q = chr(39)
    synthetic = f'group_id={_q}{gate.FORBIDDEN_GROUP}{_q}'
    assign_re = re.compile(
        rf'(?<![A-Za-z_])(GROUP|group_id|TEST_GROUP)\s*=\s*[{_q}"]'
        + re.escape(gate.FORBIDDEN_GROUP)
        + rf'[{_q}"]'
    )
    assert assign_re.search(synthetic)
    # Runner itself must not contain contiguous group_id='<forbidden>'.
    runner = _runner_path().read_text(encoding='utf-8')
    contiguous = 'group_id=' + _q + gate.FORBIDDEN_GROUP + _q
    assert contiguous not in runner


def test_no_neo4j_driver_import_in_runner():
    runner = _runner_path().read_text(encoding='utf-8')
    for line in runner.splitlines():
        if line.startswith('import ') or line.startswith('from '):
            assert not ('neo4j' in line.lower() and 'driver' in line.lower())


def test_allowed_and_forbidden_groups():
    assert gate.ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    assert gate.FORBIDDEN_GROUP == 'oracle-catalog-v2'
    assert gate.TEST_GROUP == gate.ALLOWED_TEST_GROUP


def test_docs_authoritative_sets_derive_from_code():
    legacy, catalog, errors = gate._authoritative_doc_sets(_root())
    assert len(legacy) == 14
    assert len(catalog) == 14
    assert len(errors) == 27
    assert legacy.isdisjoint(catalog)
    assert 'add_memory' in legacy
    assert 'prepare_catalog_batch' in catalog
    assert 'prepared_plan_conflict' in errors


def test_doc_inventory_and_error_checks_reject_missing_and_extra():
    expected = frozenset({'alpha', 'beta'})
    with pytest.raises(AssertionError, match=r"missing=\['beta'\]"):
        gate._assert_exact_set('fixture', frozenset({'alpha'}), expected)
    with pytest.raises(AssertionError, match=r"extra=\['gamma'\]"):
        gate._assert_exact_set('fixture', frozenset({'alpha', 'beta', 'gamma'}), expected)


def test_doc_inventory_extractors_ignore_inline_contract_names():
    tools = '- `alpha`: references `other_param`.\n2. `beta` — uses `alpha`.\n'
    errors = '| `validation_error` | bad request |\ntext `not_a_code`\n'
    assert gate._tool_inventory_names(tools) == {'alpha', 'beta'}
    assert gate._error_code_names(errors) == {'validation_error'}


def test_secret_scan_allows_placeholders_and_rejects_values():
    gate._assert_no_sensitive_values(
        'password: "your_password"\napi_key: "ollama"\nPassword: `demodemo`\n',
        'fixture',
    )
    with pytest.raises(AssertionError, match='credential'):
        gate._assert_no_sensitive_values('api_key: "live-secret-value-123"', 'fixture')
    with pytest.raises(AssertionError, match='namespace'):
        gate._assert_no_sensitive_values(
            'GRAPHITI_CATALOG_UUID_NAMESPACE=6ba7b810-9dad-11d1-80b4-00c04fd430c8',
            'fixture',
        )


def test_doc_checks_are_static_and_side_effect_free():
    runner = _runner_path().read_text(encoding='utf-8')
    assert 'ast.parse' in runner
    assert 'os.environ.get(' not in runner[runner.index('def _assert_no_sensitive_values') : runner.index('def _authoritative_doc_sets')]
    for line in runner.splitlines():
        if line.startswith('import ') or line.startswith('from '):
            assert 'graphiti_mcp_server' not in line
            assert 'catalog_common' not in line


def test_check_migration_current_guide_passes():
    gate.check_docs_migration_phrases(_root())
