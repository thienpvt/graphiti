"""Unit tests for catalog_phase5_gate_runner (no network; Wave 0 fail-closed).

Proves ready_to_regenerate_canary defaults false without proofs (D-01/D-02),
live-group isolation (D-04), canary_executed always false (D-10), and
historical a67789a pointer preservation.
"""

from __future__ import annotations

import hashlib
import importlib
import json
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
        'test_group': gate.ALLOWED_TEST_GROUP,
        'forbidden_group': gate.FORBIDDEN_GROUP,
        'historical_oracle_catalog_v2_queried': True,
        'historical_v2_commit': gate.HISTORICAL_V2_COMMIT,
        'historical_v2_class': gate.HISTORICAL_V2_CLASS,
        'historical_v2_scope': gate.HISTORICAL_V2_SCOPE,
        'current_source_v2_param_query': False,
        'current_source_v2_hits': [],
        'historical_violation_note': gate.HISTORICAL_V2_VIOLATION_NOTE,
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
            requirements_complete=True,
            edge_probes_complete=True,
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
            requirements_complete=True,
            edge_probes_complete=True,
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
            requirements_complete=True,
            edge_probes_complete=True,
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
            requirements_complete=True,
            edge_probes_complete=True,
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
            requirements_complete=True,
            edge_probes_complete=True,
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
            requirements_complete=True,
            edge_probes_complete=True,
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
    assert tuple(ids) == gate.CANONICAL_CHECK_IDS
    assert len(ids) == 20
    assert 'safety_no_v2_current' in ids
    assert 'security_matrix' in ids
    assert 'legacy_contract_14' in ids
    assert 'focused_pytest' in ids
    assert 'canary_not_executed' in ids
    assert 'live_neo4j_test11' in ids
    assert 'ollama_e2e' in ids
    focused = next(s for s in specs if s['id'] == 'focused_pytest')
    for rel in gate.FOCUS_TEST_FILES:
        assert rel in focused['argv']
    assert len(gate.FOCUS_TEST_FILES) == 10
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


def _write_hardened_gate_fixture(root: Path) -> tuple[Path, dict[str, Any]]:
    paths = {
        'payload': 'catalog/canary-v2-requests-hardened/accept-tab.payload.json',
        'offline_prepare_receipt': (
            'catalog/canary-v2-requests-hardened/offline-prepare.receipt.json'
        ),
        'offline_commit_receipt': (
            'catalog/canary-v2-requests-hardened/offline-commit.receipt.json'
        ),
        'offline_checkpoint': 'catalog/canary-v2-requests-hardened/offline-checkpoint.json',
        'sanitized_fixture': 'mcp_server/tests/fixtures/accept_tab_sanitized.json',
    }
    for index, rel in enumerate(paths.values()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f'child-{index}\n'.encode())
    checkpoint_path = root / paths['offline_checkpoint']
    checkpoint = {
        'canary_executed': False,
        'canary_attempt_count': 0,
    }
    checkpoint_path.write_text(json.dumps(checkpoint), encoding='utf-8')
    digests = {
        key: hashlib.sha256((root / rel).read_bytes()).hexdigest() for key, rel in paths.items()
    }
    inventory = {
        **paths,
        'builder': 'scripts/build_catalog_canary_requests.py',
        'runner': 'scripts/run_catalog_canary_batch.py',
        'offline_tests': 'mcp_server/tests/test_catalog_canary_scripts.py',
    }
    for key in ('builder', 'runner', 'offline_tests'):
        path = root / inventory[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# fixture\n', encoding='utf-8')
    manifest = {
        'artifact_schema_version': 'canary-hardened-v1',
        'identity_schema_version': 'catalog-v2',
        'execution_mode': 'offline_simulation',
        'canary_executed': False,
        'group_id': gate.ALLOWED_TEST_GROUP,
        'preferred_tool_sequence': [
            'prepare_catalog_batch',
            'commit_prepared_catalog_batch',
        ],
        'inventory': inventory,
        'digests': digests,
    }
    manifest_path = root / 'catalog/canary-v2-requests-hardened/manifest.json'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    return manifest_path, manifest


def test_hardened_artifact_check_verifies_exact_independent_digests(tmp_path: Path):
    manifest_path, manifest = _write_hardened_gate_fixture(tmp_path)
    gate.check_hardened_artifacts_strict(tmp_path)

    manifest['digests']['manifest'] = '0' * 64
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(AssertionError, match='self-digest'):
        gate.check_hardened_artifacts_strict(tmp_path)

    manifest['digests'].pop('manifest')
    manifest['digests']['payload'] = '0' * 64
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(AssertionError, match='digest mismatch'):
        gate.check_hardened_artifacts_strict(tmp_path)


def test_hardened_artifact_check_rejects_missing_extra_and_escaping_paths(tmp_path: Path):
    manifest_path, manifest = _write_hardened_gate_fixture(tmp_path)
    manifest['digests'].pop('payload')
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(AssertionError, match='key set'):
        gate.check_hardened_artifacts_strict(tmp_path)

    _, manifest = _write_hardened_gate_fixture(tmp_path)
    manifest['digests']['extra'] = '0' * 64
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(AssertionError, match='key set'):
        gate.check_hardened_artifacts_strict(tmp_path)

    _, manifest = _write_hardened_gate_fixture(tmp_path)
    manifest['inventory']['payload'] = '../escape.json'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(AssertionError, match='escapes root'):
        gate.check_hardened_artifacts_strict(tmp_path)


def test_sentinel_exact_third_element_nonzero():
    root = _root()
    sentinel = gate.run_sentinel(root)
    assert sentinel['argv_third'] == 'assert False'
    assert sentinel['exit_code'] != 0
    assert sentinel['pass'] is True
    assert len(sentinel['stdout_sha256']) == 64
    assert len(sentinel['stderr_sha256']) == 64
    assert 'stdout' not in sentinel
    assert 'stderr' not in sentinel
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
    masked = gate.parse_pytest_counts('0 skipped\n===== 4 passed, 2 skipped in 2.0s =====')
    assert masked['skipped'] == 2


def test_deterministic_spec_digest():
    root = _root()
    a = gate.canonical_specs_json(gate.canonical_specs(root))
    b = gate.canonical_specs_json(gate.canonical_specs(root))
    assert a == b
    assert gate.sha256_text(a) == gate.sha256_text(b)


def test_execution_input_digest_covers_dirty_runtime_and_test_sources():
    digest_map = gate.execution_input_digest_map(_root())
    required = {
        'graphiti_core/search/search.py',
        'mcp_server/src/services/catalog_service.py',
        'mcp_server/tests/catalog_phase5_gate_runner.py',
        'mcp_server/tests/test_catalog_neo4j_int.py',
        'mcp_server/pyproject.toml',
        'mcp_server/pytest.ini',
    }
    assert required <= digest_map.keys()
    assert all(re.fullmatch(r'[0-9a-f]{64}', value) for value in digest_map.values())


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
            requirements_complete=True,
            edge_probes_complete=True,
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


def _synthetic_results() -> list[dict[str, Any]]:
    specs = gate.canonical_specs(_root())
    return [
        {
            'id': spec['id'],
            'argv': list(spec['argv']),
            'expected_exit': spec['expected_exit'],
            'exit_code': 0,
            'status': 'pass',
            'availability_reason': None,
            'mandatory': bool(spec.get('mandatory', True)),
            'kind': spec.get('kind'),
            'counts': {},
            'stdout_sha256': gate.sha256_text(''),
            'stderr_sha256': gate.sha256_text(''),
        }
        for spec in specs
    ]


def _synthetic_initial_ledger(root: Path) -> dict[str, Any]:
    results = _synthetic_results()
    sentinel = {
        'argv': ['<sys.executable>', '-c', 'assert False'],
        'argv_third': 'assert False',
        'exit_code': 1,
        'pass': True,
        'stdout_sha256': gate.sha256_text(''),
        'stderr_sha256': gate.sha256_text(''),
        'excluded_from_aggregation': True,
    }
    safety = _current_clean_safety()
    safety.update(
        {
            'test_group': gate.ALLOWED_TEST_GROUP,
            'forbidden_group': gate.FORBIDDEN_GROUP,
            'historical_v2_commit': gate.HISTORICAL_V2_COMMIT,
            'historical_v2_class': gate.HISTORICAL_V2_CLASS,
            'historical_v2_scope': gate.HISTORICAL_V2_SCOPE,
        }
    )
    specs_json = gate.canonical_specs_json(gate.canonical_specs(root))
    ledger: dict[str, Any] = {
        'schema_version': gate.SCHEMA_VERSION,
        'package_stage': 'initial',
        'evaluated_head': gate.git_head(root),
        'proof_head': gate.git_head(root),
        'canonical_specs': json.loads(specs_json),
        'spec_sha256': gate.sha256_text(specs_json),
        'content_sha256_map': gate.content_digest_map(root, gate.INITIAL_GATE_INPUT_RELS),
        'content_digest': gate.content_digest(
            gate.content_digest_map(root, gate.INITIAL_GATE_INPUT_RELS)
        ),
        'execution_input_sha256_map': gate.execution_input_digest_map(root),
        'execution_input_digest': gate.content_digest(gate.execution_input_digest_map(root)),
        'reviewed_worktree_sha256_map': gate.reviewed_worktree_digest_map(root),
        'reviewed_worktree_digest': gate.reviewed_worktree_digest(root),
        'requirement_ids': list(gate.REQUIREMENT_IDS),
        'requirement_dispositions': {
            requirement: 'pending-audits' for requirement in gate.REQUIREMENT_IDS
        },
        'raw_edge_probe_count': gate.EXPECTED_PROBE_COUNT,
        'expected_requirement_count': gate.EXPECTED_REQUIREMENT_COUNT,
        'edge_probe_dispositions': {
            probe: 'pending-audits' for probe in gate.EDGE_PROBE_IDS
        },
        'sentinel': sentinel,
        'results': results,
        'local_gate_pass': True,
        'nyquist_compliant': False,
        'ready_to_regenerate_canary': False,
        'phase_5_complete': False,
        'post_execution_audits_pending': True,
        'audits_pass': False,
        'audits': gate._pending_audits(),
        'unit_service_pass': True,
        'registration_pass': True,
        'security_matrix_pass': True,
        'legacy_contract_pass': True,
        'offline_canary_pass': True,
        'docs_pass': True,
        'canary_executed': False,
        'oracle_catalog_v2_queried': False,
        'current_oracle_catalog_v2_queried': False,
        'current_oracle_catalog_v2_mutated': False,
        'clear_graph_called': False,
        'api_coverage_detector': False,
        'safety': safety,
        'historical_audit': {
            'historical_oracle_catalog_v2_queried': True,
            'commit': gate.HISTORICAL_V2_COMMIT,
            'class': gate.HISTORICAL_V2_CLASS,
            'scope': gate.HISTORICAL_V2_SCOPE,
            'checkpoint_sha256': gate.HISTORICAL_CHECKPOINT_SHA256,
            'checkpoint_attempt_count': gate.HISTORICAL_CHECKPOINT_ATTEMPT_COUNT,
        },
    }
    ledger['ledger_sha256'] = gate._canonical_sha256(ledger, 'ledger_sha256')
    return ledger


def _write_green_audits(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    phase = root / gate.PHASE_DIR_REL
    phase.mkdir(parents=True, exist_ok=True)
    expected_binding = {
        'evaluated_head': 'a' * 40,
        'execution_input_digest': 'b' * 64,
        'reviewed_worktree_digest': 'c' * 64,
        'initial_ledger_sha256': 'd' * 64,
    }
    monkeypatch.setattr(gate, '_initial_ledger_binding', lambda _: expected_binding)
    binding = {**expected_binding, 'audited_at': gate.datetime.now(gate.timezone.utc).isoformat()}
    binding_yaml = ''.join(
        f'{key}: {json.dumps(value) if key == "audited_at" else value}\n'
        for key, value in binding.items()
    )
    probe_items = [
        {
            'requirement_id': probe_id.rsplit('-', 1)[0],
            'category': probe_id.rsplit('-', 1)[1],
            'status': 'resolved',
            'verification': 'explicit',
        }
        for probe_id in gate.EDGE_PROBE_IDS
    ]
    (phase / '05-EDGE-PROBE-LEDGER.json').write_text(
        json.dumps(
            {
                'items': probe_items,
                'coverage': {
                    'applicable': gate.EXPECTED_PROBE_COUNT,
                    'resolved': gate.EXPECTED_PROBE_COUNT,
                    'unresolved': 0,
                },
            }
        ),
        encoding='utf-8',
    )
    (phase / '05-REVIEW.md').write_text(
        '---\n'
        + binding_yaml
        + f'review_scope: {gate.AUDIT_SCOPE_ID}\n'
        + 'status: clean\nfindings:\n  critical: 0\n  warning: 0\n---\n',
        encoding='utf-8',
    )
    (phase / '05-VALIDATION.md').write_text(
        '---\n'
        + binding_yaml
        + 'phase: 05\nslug: verification-security-compatibility-and-migration-docs\n'
        + 'status: validated\nnyquist_compliant: true\nwave_0_complete: true\n'
        + 'created: 2026-07-19\n---\n37/37 probes resolved\n',
        encoding='utf-8',
    )
    (phase / '05-SECURITY.md').write_text(
        '---\n'
        + binding_yaml
        + 'status: verified\nthreats_open: 0\naccepted_risks: []\n---\nNo accepted risks.\n',
        encoding='utf-8',
    )
    (phase / '05-VERIFICATION.md').write_text(
        '---\n'
        + binding_yaml
        + 'status: passed\nscore: 5/5 must-haves verified\nbehavior_unverified: 0\n'
        + 'requirements_verified: 17/17\ngaps: []\n---\n',
        encoding='utf-8',
    )


def test_result_partition_exact_order_and_availability_reason():
    results = _synthetic_results()
    assert gate.validate_result_partition(results, require_all_ids=True)
    results[-1]['status'] = 'availability-skip'
    results[-1]['availability_reason'] = 'Ollama daemon unavailable'
    results[-1]['skip_reasons'] = ['Ollama daemon unavailable at http://127.0.0.1:11434']
    assert gate.validate_result_partition(results, require_all_ids=True)
    results[-1]['availability_reason'] = ''
    assert gate.validate_result_partition(results, require_all_ids=True) is False
    results[-1]['availability_reason'] = 'reason'
    results.reverse()
    assert gate.validate_result_partition(results, require_all_ids=True) is False


def test_live_availability_skip_allows_static_passes_but_not_failures():
    spec = next(
        item for item in gate.canonical_specs(_root()) if item['id'] == 'live_neo4j_test11'
    )
    outcome = {
        'exit_code': 0,
        'counts': {'passed': 3, 'failed': 0, 'skipped': 59, 'errors': 0},
        'skip_reasons': ['Neo4j unavailable: ServiceUnavailable'],
    }
    status, reason = gate.classify_check_outcome(spec, outcome)
    assert status == 'availability-skip'
    assert reason

    outcome['skip_reasons'] = ['CATALOG_CEILING_SMOKE not set; ceiling proof deferred']
    assert gate.classify_check_outcome(spec, outcome) == ('fail', None)
    outcome['skip_reasons'] = ['Neo4j unavailable: ServiceUnavailable']
    outcome['counts']['failed'] = 1
    outcome['exit_code'] = 1
    assert gate.classify_check_outcome(spec, outcome) == ('fail', None)


def test_run_gate_unsets_required_infrastructure_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    seen: list[dict[str, str]] = []

    def fake_run_argv(*_: Any, **kwargs: Any) -> dict[str, Any]:
        env = kwargs['env']
        seen.append(env)
        return {
            'exit_code': 0,
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'errors': 0},
        }

    monkeypatch.setenv('CATALOG_INT_REQUIRED', '1')
    monkeypatch.setenv('CATALOG_OLLAMA_REQUIRED', '1')
    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    gate.run_gate(_root(), tmp_path / 'ledger.json')
    assert seen
    assert all('CATALOG_INT_REQUIRED' not in env for env in seen)
    assert all('CATALOG_OLLAMA_REQUIRED' not in env for env in seen)
    assert all(env['CATALOG_CEILING_SMOKE'] == '1' for env in seen)


@pytest.mark.parametrize('heading', ['Accepted Risks', 'Accepted Risks Log'])
def test_security_audit_rejects_nonempty_accepted_risks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, heading: str
):
    _write_green_audits(tmp_path, monkeypatch)
    security = tmp_path / gate.PHASE_DIR_REL / '05-SECURITY.md'
    text = security.read_text(encoding='utf-8')
    security.write_text(
        text.replace(
            '---\nNo accepted risks.\n',
            f'---\n## {heading}\n\n- High-severity bypass accepted for rollout.\n',
        ),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='audit rejected'):
        gate.parse_audits(tmp_path)


def test_parse_audits_exact_green_and_malformed_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / '.planning').mkdir()
    (tmp_path / 'mcp_server').mkdir()
    _write_green_audits(tmp_path, monkeypatch)
    audits = gate.parse_audits(tmp_path)
    assert tuple(audits) == gate.AUDIT_NAMES
    assert all(row['status'] == 'pass' for row in audits.values())

    validation = tmp_path / gate.PHASE_DIR_REL / '05-VALIDATION.md'
    validation.write_text(
        validation.read_text(encoding='utf-8').replace(
            '37/37 probes resolved', '36/37 probes resolved'
        ),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='audit (?:rejected|schema mismatch)'):
        gate.parse_audits(tmp_path)


def test_atomic_write_package_rolls_back_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ledger_path = tmp_path / 'ledger.json'
    report_path = tmp_path / 'report.json'
    markdown_path = tmp_path / 'report.md'
    marker_path = gate._package_marker_path(ledger_path)
    ledger_path.write_text('{"old":1}\n', encoding='utf-8')
    report_path.write_text('{"old":2}\n', encoding='utf-8')
    markdown_path.write_text('old\n', encoding='utf-8')
    marker_path.write_text('{"old":3}\n', encoding='utf-8')
    before = {
        path: path.read_bytes()
        for path in (ledger_path, report_path, markdown_path, marker_path)
    }
    real_replace = gate.os.replace
    calls = 0

    def flaky_replace(source: Any, target: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError('synthetic package failure')
        real_replace(source, target)

    monkeypatch.setattr(gate.os, 'replace', flaky_replace)
    with pytest.raises(PermissionError, match='synthetic'):
        gate.atomic_write_package(
            ledger_path,
            {'new': 1},
            report_path,
            {'new': 2},
            markdown_path,
            'new\n',
        )
    assert {path: path.read_bytes() for path in before} == before


def test_atomic_write_package_fsyncs_directory_after_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_path = tmp_path / '05-GATE-RESULTS.json'
    report_path = tmp_path / '05-IMPLEMENTATION-REPORT.json'
    markdown_path = tmp_path / '05-IMPLEMENTATION-REPORT.md'
    calls: list[Path] = []
    monkeypatch.setattr(gate, '_fsync_parent', lambda path: calls.append(path))
    gate.atomic_write_package(
        ledger_path,
        {'package_stage': 'initial', 'ledger_sha256': 'a' * 64},
        report_path,
        {'report': 1},
        markdown_path,
        'report\n',
    )
    assert calls == [gate._package_marker_path(ledger_path)]


def test_proof_package_marker_rejects_interrupted_publication(tmp_path: Path) -> None:
    ledger_path = tmp_path / '05-GATE-RESULTS.json'
    report_json = tmp_path / '05-IMPLEMENTATION-REPORT.json'
    report_md = tmp_path / '05-IMPLEMENTATION-REPORT.md'
    ledger = _synthetic_initial_ledger(_root())
    report = gate._build_report_model(ledger)
    gate.atomic_write_package(
        ledger_path,
        ledger,
        report_json,
        report,
        report_md,
        gate.render_report_markdown(report),
    )
    marker_path = gate._package_marker_path(ledger_path)
    gate._validate_package_marker(
        marker_path, ledger_path, report_json, report_md, ledger
    )

    report_md.write_text('interrupted replacement\n', encoding='utf-8')
    with pytest.raises(ValueError, match='marker file mismatch'):
        gate._validate_package_marker(
            marker_path, ledger_path, report_json, report_md, ledger
        )


def test_atomic_write_package_restores_marker_on_base_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_path = tmp_path / 'ledger.json'
    report_path = tmp_path / 'report.json'
    markdown_path = tmp_path / 'report.md'
    marker_path = gate._package_marker_path(ledger_path)
    for path, text in (
        (ledger_path, '{"old":1}\n'),
        (report_path, '{"old":2}\n'),
        (markdown_path, 'old\n'),
        (marker_path, '{"old":3}\n'),
    ):
        path.write_text(text, encoding='utf-8')
    before = {
        path: path.read_bytes()
        for path in (ledger_path, report_path, markdown_path, marker_path)
    }
    real_replace = gate.os.replace
    calls = 0

    def interrupt_replace(source: Any, target: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise KeyboardInterrupt
        real_replace(source, target)

    monkeypatch.setattr(gate.os, 'replace', interrupt_replace)
    with pytest.raises(KeyboardInterrupt):
        gate.atomic_write_package(
            ledger_path,
            {'new': 1},
            report_path,
            {'new': 2},
            markdown_path,
            'new\n',
        )
    assert {path: path.read_bytes() for path in before} == before


def test_finalize_synthetic_green_and_verify_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '05-GATE-RESULTS.json'
    report_json = tmp_path / '05-IMPLEMENTATION-REPORT.json'
    report_md = tmp_path / '05-IMPLEMENTATION-REPORT.md'
    initial = _synthetic_initial_ledger(root)
    initial_report = gate._build_report_model(initial)
    gate.atomic_write_package(
        ledger_path,
        initial,
        report_json,
        initial_report,
        report_md,
        gate.render_report_markdown(initial_report),
    )
    audits = {
        name: {
            'path': gate.AUDIT_PATH_BY_NAME[name].as_posix(),
            'status': 'pass',
            'sha256': 'a' * 64,
        }
        for name in gate.AUDIT_NAMES
    }
    def fake_parse_audits(root_arg: Path) -> dict[str, dict[str, Any]]:
        assert root_arg == root
        return audits

    def fake_check(root_arg: Path) -> None:
        assert root_arg == root

    def fake_safety(results_arg: list[dict[str, Any]], root_arg: Path) -> dict[str, object]:
        assert results_arg
        assert root_arg == root
        return dict(_current_clean_safety())

    def fake_closure_checks(
        root_arg: Path, specs_arg: list[dict[str, Any]]
    ) -> dict[str, Any]:
        assert root_arg == root
        assert specs_arg
        by_id = {row['id']: row for row in _synthetic_results()}
        content_map = gate.content_digest_map(root, gate.FINAL_GATE_INPUT_RELS)
        execution_map = gate.execution_input_digest_map(root)
        return {
            'evaluated_head': gate.git_head(root),
            'spec_sha256': initial['spec_sha256'],
            'rerun_check_ids': list(gate.FINAL_RERUN_CHECK_IDS),
            'preserved_external_check_ids': list(gate.PRESERVED_EXTERNAL_CHECK_IDS),
            'results': [by_id[check_id] for check_id in gate.FINAL_RERUN_CHECK_IDS],
            'sentinel': dict(initial['sentinel']),
            'input_sha256_map': content_map,
            'input_digest': gate.content_digest(content_map),
            'execution_input_sha256_map': execution_map,
            'execution_input_digest': gate.content_digest(execution_map),
            'reviewed_worktree_sha256_map': gate.reviewed_worktree_digest_map(root),
            'reviewed_worktree_digest': gate.reviewed_worktree_digest(root),
        }

    monkeypatch.setattr(gate, 'parse_audits', fake_parse_audits)
    monkeypatch.setattr(gate, 'check_historical_artifacts_unchanged', fake_check)
    monkeypatch.setattr(gate, 'check_hardened_artifacts_strict', fake_check)
    monkeypatch.setattr(gate, 'check_canary_not_executed', fake_check)
    monkeypatch.setattr(gate, 'check_safety_no_probe', fake_check)
    monkeypatch.setattr(gate, 'derive_safety_ledger', fake_safety)
    monkeypatch.setattr(gate, 'run_final_closure_checks', fake_closure_checks)
    final = gate.finalize_package(
        root,
        ledger_path,
        report_json,
        report_md,
        require_audits=True,
        require_ready=True,
        expected_requirements=17,
        expected_edge_probes=37,
    )
    assert final['ready_to_regenerate_canary'] is True
    assert final['phase_5_complete'] is True
    assert len(final['requirement_dispositions']) == 17
    assert len(final['edge_probe_dispositions']) == 37
    verified = gate.verify_final_package(
        root,
        ledger_path,
        report_json,
        report_md,
        require_ready=True,
        expected_requirements=17,
        expected_edge_probes=37,
    )
    assert verified['ledger_sha256'] == final['ledger_sha256']


def test_verify_proof_head_accepts_current_and_closure_only_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    proof_head = 'a' * 40
    current_head = 'b' * 40
    monkeypatch.setattr(gate, 'git_head', lambda _: proof_head)
    gate._verify_proof_head(tmp_path, proof_head)

    monkeypatch.setattr(gate, 'git_head', lambda _: current_head)
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> mock.Mock:
        calls.append(argv)
        if argv[1:3] == ['merge-base', '--is-ancestor']:
            return mock.Mock(returncode=0, stdout='', stderr='')
        assert argv[1:5] == ['log', '--format=', '--name-only', '--no-renames']
        return mock.Mock(returncode=0, stdout='.planning/STATE.md\n', stderr='')

    monkeypatch.setattr(gate.subprocess, 'run', fake_run)
    gate._verify_proof_head(tmp_path, proof_head)
    assert len(calls) == 2


def test_verify_proof_head_rejects_non_descendant_and_non_proof_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    proof_head = 'a' * 40
    monkeypatch.setattr(gate, 'git_head', lambda _: 'b' * 40)
    monkeypatch.setattr(
        gate.subprocess,
        'run',
        lambda *_args, **_kwargs: mock.Mock(returncode=1, stdout='', stderr=''),
    )
    with pytest.raises(ValueError, match='HEAD binding'):
        gate._verify_proof_head(tmp_path, proof_head)

    def source_change(argv: list[str], **_kwargs: object) -> mock.Mock:
        if argv[1:3] == ['merge-base', '--is-ancestor']:
            return mock.Mock(returncode=0, stdout='', stderr='')
        return mock.Mock(
            returncode=0,
            stdout='mcp_server/tests/catalog_phase5_gate_runner.py\n',
            stderr='',
        )

    monkeypatch.setattr(gate.subprocess, 'run', source_change)
    with pytest.raises(ValueError, match='non-proof paths'):
        gate._verify_proof_head(tmp_path, proof_head)


def test_verify_proof_head_rejects_unrelated_and_net_zero_commit_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    proof_head = 'a' * 40
    monkeypatch.setattr(gate, 'git_head', lambda _: 'b' * 40)
    outputs = iter(('README.md\n', '\n'))

    def changed_paths(argv: list[str], **_kwargs: object) -> mock.Mock:
        if argv[1:3] == ['merge-base', '--is-ancestor']:
            return mock.Mock(returncode=0, stdout='', stderr='')
        return mock.Mock(returncode=0, stdout=next(outputs), stderr='')

    monkeypatch.setattr(gate.subprocess, 'run', changed_paths)
    with pytest.raises(ValueError, match='non-proof paths'):
        gate._verify_proof_head(tmp_path, proof_head)
    with pytest.raises(ValueError, match='non-proof paths'):
        gate._verify_proof_head(tmp_path, proof_head)


def test_verify_proof_head_rejects_malformed_hash(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='HEAD binding'):
        gate._verify_proof_head(tmp_path, '../HEAD')


def test_report_model_has_required_final_contract_shape():
    ledger = _synthetic_initial_ledger(_root())
    report = gate._build_report_model(ledger)
    assert report['requirements'] == {
        'total_expected': 138,
        'mapped': 138,
        'implemented': 121,
        'verified': 121,
        'phase_5_expected': 17,
        'phase_5_ids': list(gate.REQUIREMENT_IDS),
        'phase_5_verified': 0,
    }
    assert report['compatibility_breaks'] == []
    assert report['changed_files_and_modules']
    assert report['contract_and_schema_changes']
    assert report['database_migration_changes']
    assert report['baseline']['tool_union'] == 28
    assert report['security_and_operational_limits']
    assert report['ready_to_regenerate_canary_payload'] is False
    assert report['canary_executed'] is False


def test_run_gate_temp_ledger_keeps_reports_in_temp_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    default_json = root / gate.DEFAULT_REPORT_JSON_REL
    default_md = root / gate.DEFAULT_REPORT_MD_REL
    before = (default_json.read_bytes(), default_md.read_bytes())

    def fake_run_argv(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = args, kwargs
        return {
            'exit_code': 0,
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'errors': 0},
            'stdout_sha256': gate.sha256_text(''),
            'stderr_sha256': gate.sha256_text(''),
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    gate.run_gate(root, tmp_path / 'ledger.json')
    assert (tmp_path / '05-IMPLEMENTATION-REPORT.json').is_file()
    assert (tmp_path / '05-IMPLEMENTATION-REPORT.md').is_file()
    assert (default_json.read_bytes(), default_md.read_bytes()) == before


def test_final_closure_reruns_all_canonical_checks(monkeypatch: pytest.MonkeyPatch):
    root = _root()
    specs = gate.canonical_specs(root)
    called: list[str] = []

    def fake_run_argv(
        argv: list[str], root_arg: Path, **kwargs: Any
    ) -> dict[str, Any]:
        _ = kwargs
        assert root_arg == root
        spec = next(row for row in specs if row['argv'] == argv)
        called.append(spec['id'])
        return {
            'exit_code': 0,
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'errors': 0},
            'stdout_sha256': gate.sha256_text(spec['id']),
            'stderr_sha256': gate.sha256_text(''),
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setattr(gate, 'content_digest_map', lambda *_: {})
    evidence = gate.run_final_closure_checks(root, specs)
    assert tuple(called) == gate.CANONICAL_CHECK_IDS
    assert gate.PRESERVED_EXTERNAL_CHECK_IDS == ()
    assert evidence['preserved_external_check_ids'] == []
    assert evidence['sentinel']['pass'] is True


def test_finalize_rejects_spec_drift_before_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '05-GATE-RESULTS.json'
    report_json = tmp_path / '05-IMPLEMENTATION-REPORT.json'
    report_md = tmp_path / '05-IMPLEMENTATION-REPORT.md'
    initial = _synthetic_initial_ledger(root)
    initial['canonical_specs'][0]['argv'] = ['python', '-c', 'changed']
    initial['ledger_sha256'] = gate._canonical_sha256(initial, 'ledger_sha256')
    report = gate._build_report_model(initial)
    gate.atomic_write_package(
        ledger_path,
        initial,
        report_json,
        report,
        report_md,
        gate.render_report_markdown(report),
    )
    closure = mock.Mock()
    monkeypatch.setattr(gate, 'run_final_closure_checks', closure)
    with pytest.raises(ValueError, match='spec drift'):
        gate.finalize_package(
            root,
            ledger_path,
            report_json,
            report_md,
            require_audits=True,
            require_ready=True,
            expected_requirements=17,
            expected_edge_probes=37,
        )
    closure.assert_not_called()


def test_finalize_closure_failure_leaves_initial_artifacts_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '05-GATE-RESULTS.json'
    report_json = tmp_path / '05-IMPLEMENTATION-REPORT.json'
    report_md = tmp_path / '05-IMPLEMENTATION-REPORT.md'
    initial = _synthetic_initial_ledger(root)
    report = gate._build_report_model(initial)
    gate.atomic_write_package(
        ledger_path,
        initial,
        report_json,
        report,
        report_md,
        gate.render_report_markdown(report),
    )
    before = {path: path.read_bytes() for path in (ledger_path, report_json, report_md)}
    monkeypatch.setattr(
        gate,
        'parse_audits',
        mock.Mock(return_value={name: {} for name in gate.AUDIT_NAMES}),
    )
    monkeypatch.setattr(gate, 'check_historical_artifacts_unchanged', lambda *_: None)
    monkeypatch.setattr(gate, 'check_hardened_artifacts_strict', lambda *_: None)
    monkeypatch.setattr(gate, 'check_canary_not_executed', lambda *_: None)
    monkeypatch.setattr(gate, 'check_safety_no_probe', lambda *_: None)
    monkeypatch.setattr(
        gate,
        'run_final_closure_checks',
        mock.Mock(side_effect=ValueError('final closure check failed')),
    )
    with pytest.raises(ValueError, match='final closure'):
        gate.finalize_package(
            root,
            ledger_path,
            report_json,
            report_md,
            require_audits=True,
            require_ready=True,
            expected_requirements=17,
            expected_edge_probes=37,
        )
    assert {path: path.read_bytes() for path in before} == before


def test_finalize_post_write_verification_failure_restores_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '05-GATE-RESULTS.json'
    report_json = tmp_path / '05-IMPLEMENTATION-REPORT.json'
    report_md = tmp_path / '05-IMPLEMENTATION-REPORT.md'
    initial = _synthetic_initial_ledger(root)
    report = gate._build_report_model(initial)
    gate.atomic_write_package(
        ledger_path,
        initial,
        report_json,
        report,
        report_md,
        gate.render_report_markdown(report),
    )
    before = {path: path.read_bytes() for path in (ledger_path, report_json, report_md)}
    audits = {
        name: {
            'path': gate.AUDIT_PATH_BY_NAME[name].as_posix(),
            'status': 'pass',
            'sha256': 'a' * 64,
        }
        for name in gate.AUDIT_NAMES
    }
    by_id = {row['id']: row for row in _synthetic_results()}
    content_map = gate.content_digest_map(root, gate.FINAL_GATE_INPUT_RELS)
    execution_map = gate.execution_input_digest_map(root)
    closure = {
        'evaluated_head': gate.git_head(root),
        'spec_sha256': initial['spec_sha256'],
        'rerun_check_ids': list(gate.FINAL_RERUN_CHECK_IDS),
        'preserved_external_check_ids': list(gate.PRESERVED_EXTERNAL_CHECK_IDS),
        'results': [by_id[check_id] for check_id in gate.FINAL_RERUN_CHECK_IDS],
        'sentinel': dict(initial['sentinel']),
        'input_sha256_map': content_map,
        'input_digest': gate.content_digest(content_map),
        'execution_input_sha256_map': execution_map,
        'execution_input_digest': gate.content_digest(execution_map),
        'reviewed_worktree_sha256_map': gate.reviewed_worktree_digest_map(root),
        'reviewed_worktree_digest': gate.reviewed_worktree_digest(root),
    }
    monkeypatch.setattr(gate, 'parse_audits', lambda *_: audits)
    monkeypatch.setattr(gate, 'check_historical_artifacts_unchanged', lambda *_: None)
    monkeypatch.setattr(gate, 'check_hardened_artifacts_strict', lambda *_: None)
    monkeypatch.setattr(gate, 'check_canary_not_executed', lambda *_: None)
    monkeypatch.setattr(gate, 'check_safety_no_probe', lambda *_: None)
    monkeypatch.setattr(gate, 'derive_safety_ledger', lambda *_: dict(_current_clean_safety()))
    monkeypatch.setattr(gate, 'run_final_closure_checks', lambda *_: closure)
    monkeypatch.setattr(
        gate,
        'verify_final_package',
        mock.Mock(side_effect=ValueError('synthetic reread failure')),
    )
    with pytest.raises(ValueError, match='synthetic reread'):
        gate.finalize_package(
            root,
            ledger_path,
            report_json,
            report_md,
            require_audits=True,
            require_ready=True,
            expected_requirements=17,
            expected_edge_probes=37,
        )
    assert {path: path.read_bytes() for path in before} == before


def test_finalize_failure_leaves_initial_artifacts_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '05-GATE-RESULTS.json'
    report_json = tmp_path / '05-IMPLEMENTATION-REPORT.json'
    report_md = tmp_path / '05-IMPLEMENTATION-REPORT.md'
    initial = _synthetic_initial_ledger(root)
    report = gate._build_report_model(initial)
    gate.atomic_write_package(
        ledger_path,
        initial,
        report_json,
        report,
        report_md,
        gate.render_report_markdown(report),
    )
    before = {path: path.read_bytes() for path in (ledger_path, report_json, report_md)}
    monkeypatch.setattr(
        gate,
        'parse_audits',
        mock.Mock(side_effect=ValueError('synthetic malformed audit')),
    )
    with pytest.raises(ValueError, match='synthetic malformed'):
        gate.finalize_package(
            root,
            ledger_path,
            report_json,
            report_md,
            require_audits=True,
            require_ready=True,
            expected_requirements=17,
            expected_edge_probes=37,
        )
    assert {path: path.read_bytes() for path in before} == before


def test_initial_finalization_rejects_forged_result_evidence():
    root = _root()
    ledger = _synthetic_initial_ledger(root)
    live = next(row for row in ledger['results'] if row['id'] == 'live_neo4j_test11')
    live['stdout_sha256'] = 'forged'
    live['counts'] = {'passed': 999999, 'failed': 1, 'errors': 1, 'skipped': 0}
    ledger['ledger_sha256'] = gate._canonical_sha256(ledger, 'ledger_sha256')
    with pytest.raises(ValueError, match='result evidence'):
        gate._assert_initial_ledger_for_finalization(root, ledger)


def test_initial_finalization_rejects_forged_safety_summary():
    root = _root()
    ledger = _synthetic_initial_ledger(root)
    ledger['safety']['safety_checks_pass'] = False
    ledger['ledger_sha256'] = gate._canonical_sha256(ledger, 'ledger_sha256')
    with pytest.raises(ValueError, match='safety invariant'):
        gate._assert_initial_ledger_for_finalization(root, ledger)


def test_initial_optional_availability_may_recover_on_final_rerun():
    root = _root()
    ledger = _synthetic_initial_ledger(root)
    live = next(row for row in ledger['results'] if row['id'] == 'live_neo4j_test11')
    live.update(
        {
            'status': 'availability-skip',
            'availability_reason': 'live_neo4j_test11 infrastructure unavailable',
            'counts': {'passed': 0, 'failed': 0, 'skipped': 1, 'errors': 0},
            'skip_reasons': ['Neo4j unavailable: ServiceUnavailable'],
        }
    )
    ledger['ledger_sha256'] = gate._canonical_sha256(ledger, 'ledger_sha256')
    assert gate._assert_initial_ledger_for_finalization(root, ledger)


def test_initial_finalization_rejects_execution_input_drift():
    root = _root()
    ledger = _synthetic_initial_ledger(root)
    ledger['execution_input_sha256_map']['mcp_server/tests/test_catalog_neo4j_int.py'] = '0' * 64
    ledger['execution_input_digest'] = gate.content_digest(
        ledger['execution_input_sha256_map']
    )
    ledger['ledger_sha256'] = gate._canonical_sha256(ledger, 'ledger_sha256')
    with pytest.raises(ValueError, match='execution input drift'):
        gate._assert_initial_ledger_for_finalization(root, ledger)


def test_reviewed_worktree_excludes_only_proof_audits_and_post_proof_tracking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    tracked = tmp_path / 'product.py'
    tracked.write_text('value = 1\n', encoding='utf-8')
    lines = [
        ' M product.py',
        ' M .planning/ROADMAP.md',
        ' M .planning/REQUIREMENTS.md',
        ' M .planning/STATE.md',
        '?? .planning/phases/05-verification-security-compatibility-and-migration-docs/05-07-SUMMARY.md',
    ]
    monkeypatch.setattr(
        gate.subprocess,
        'run',
        lambda *args, **kwargs: mock.Mock(returncode=0, stdout='\n'.join(lines) + '\n'),
    )
    assert gate.reviewed_worktree_digest_map(tmp_path) == {
        'product.py': gate.sha256_file_raw(tracked)
    }


def test_initial_finalization_rejects_reviewed_worktree_drift():
    root = _root()
    ledger = _synthetic_initial_ledger(root)
    ledger['reviewed_worktree_sha256_map']['synthetic.py'] = '0' * 64
    ledger['reviewed_worktree_digest'] = gate.content_digest(
        ledger['reviewed_worktree_sha256_map']
    )
    ledger['ledger_sha256'] = gate._canonical_sha256(ledger, 'ledger_sha256')
    with pytest.raises(ValueError, match='reviewed worktree drift'):
        gate._assert_initial_ledger_for_finalization(root, ledger)


def test_final_ledger_keeps_initial_audit_binding(monkeypatch: pytest.MonkeyPatch):
    root = _root()
    initial = _synthetic_initial_ledger(root)
    final = dict(initial)
    final.update(
        {
            'package_stage': 'final',
            'initial_evidence': {'ledger_sha256': initial['ledger_sha256']},
        }
    )
    final['ledger_sha256'] = gate._canonical_sha256(final, 'ledger_sha256')
    monkeypatch.setattr(
        gate,
        '_load_json_object',
        lambda path: final if path.name == gate.DEFAULT_LEDGER_REL.name else {},
    )
    binding = gate._initial_ledger_binding(root)
    assert binding['evaluated_head'] == initial['evaluated_head']
    assert binding['initial_ledger_sha256'] == initial['ledger_sha256']
    assert binding['initial_ledger_sha256'] != final['ledger_sha256']


def test_final_ledger_audits_keep_proof_head_after_closure_commit(
    monkeypatch: pytest.MonkeyPatch,
):
    root = _root()
    initial = _synthetic_initial_ledger(root)
    final = dict(initial)
    final.update(
        {
            'package_stage': 'final',
            'initial_evidence': {'ledger_sha256': initial['ledger_sha256']},
        }
    )
    final['ledger_sha256'] = gate._canonical_sha256(final, 'ledger_sha256')
    monkeypatch.setattr(gate, '_load_json_object', lambda _: final)
    monkeypatch.setattr(gate, 'git_head', lambda _: 'f' * 40)
    assert gate._initial_ledger_binding(root)['evaluated_head'] == initial['evaluated_head']


def test_initial_ledger_binding_rejects_malformed_evaluated_head(
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _synthetic_initial_ledger(_root())
    ledger['evaluated_head'] = '../HEAD'
    ledger['ledger_sha256'] = gate._canonical_sha256(ledger, 'ledger_sha256')
    monkeypatch.setattr(gate, '_load_json_object', lambda _: ledger)
    with pytest.raises(ValueError, match='initial ledger binding invalid'):
        gate._initial_ledger_binding(_root())


def test_audit_binding_rejects_stale_timestamp_and_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _write_green_audits(tmp_path, monkeypatch)
    review = tmp_path / gate.PHASE_DIR_REL / '05-REVIEW.md'
    green = review.read_text(encoding='utf-8')
    stale = (gate.datetime.now(gate.timezone.utc) - gate.timedelta(days=8)).isoformat()
    current = gate.parse_frontmatter(review)['audited_at']
    review.write_text(green.replace(str(current), stale), encoding='utf-8')
    with pytest.raises(ValueError, match='timestamp stale'):
        gate.parse_audits(tmp_path)

    review.write_text(
        green.replace(gate.AUDIT_SCOPE_ID, 'wrong-review-scope'), encoding='utf-8'
    )
    with pytest.raises(ValueError, match='scope mismatch'):
        gate.parse_audits(tmp_path)


def test_hardened_artifacts_reject_runtime_live_receipt(tmp_path: Path) -> None:
    root = _root()
    artifact_dir = tmp_path / gate.HARDENED_ARTIFACT_DIR_REL
    artifact_dir.mkdir(parents=True)
    for name in gate.HARDENED_EXPECTED_FILE_NAMES:
        (artifact_dir / name).write_bytes(
            (root / gate.HARDENED_ARTIFACT_DIR_REL / name).read_bytes()
        )
    (artifact_dir / 'live-checkpoint.json').write_text('{}\n', encoding='utf-8')
    with pytest.raises(AssertionError, match='runtime artifact inventory mismatch'):
        gate.check_hardened_artifacts_strict(tmp_path)


def test_audit_parser_rejects_extra_metadata_and_blocker_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _write_green_audits(tmp_path, monkeypatch)
    review = tmp_path / gate.PHASE_DIR_REL / '05-REVIEW.md'
    green = review.read_text(encoding='utf-8')
    review.write_text(
        green.replace('status: clean\n', 'status: clean\nfiles_reviewed_list: [a.py]\n'),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='audit schema mismatch'):
        gate.parse_audits(tmp_path)

    review.write_text(
        green.replace('  warning: 0\n', '  warning: 0\n  blocker: 1\n'),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='findings schema mismatch'):
        gate.parse_audits(tmp_path)


@pytest.mark.parametrize(
    ('name', 'old', 'new', 'message'),
    [
        ('review', '  critical: 0\n', '  critical: false\n', 'findings counts mismatch'),
        ('security', 'threats_open: 0\n', 'threats_open: false\n', 'threats_open type mismatch'),
        (
            'verification',
            'behavior_unverified: 0\n',
            'behavior_unverified: false\n',
            'behavior_unverified type mismatch',
        ),
    ],
)
def test_audit_parser_rejects_boolean_count_spoof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    old: str,
    new: str,
    message: str,
):
    _write_green_audits(tmp_path, monkeypatch)
    path = tmp_path / gate.AUDIT_PATH_BY_NAME[name]
    path.write_text(path.read_text(encoding='utf-8').replace(old, new), encoding='utf-8')
    with pytest.raises(ValueError, match=message):
        gate.parse_audits(tmp_path)


def test_audit_parser_rejects_duplicate_yaml_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _write_green_audits(tmp_path, monkeypatch)
    review = tmp_path / gate.PHASE_DIR_REL / '05-REVIEW.md'
    green = review.read_text(encoding='utf-8')
    review.write_text(
        green.replace('status: clean\n', 'status: blocked\nstatus: clean\n'),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='frontmatter malformed'):
        gate.parse_audits(tmp_path)

    review.write_text(
        green.replace('  critical: 0\n', '  critical: 1\n  critical: 0\n'),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='frontmatter malformed'):
        gate.parse_audits(tmp_path)


def test_tool_availability_evidence_accepts_empty_counts():
    row = next(item for item in _synthetic_results() if item['id'] == 'ruff')
    row.update(
        {
            'status': 'availability-skip',
            'availability_reason': 'ruff executable unavailable in the configured uv environment',
            'counts': {},
            'skip_reasons': [],
        }
    )
    gate._validate_result_evidence(row)

    row['id'] = 'focused_pytest'
    with pytest.raises(ValueError, match='check id mismatch'):
        gate._validate_result_evidence(row)


def test_initial_package_rejects_premature_ready():
    ledger = _synthetic_initial_ledger(_root())
    report = gate._build_report_model(ledger)
    gate.validate_initial_package(ledger, report)
    ledger['ready_to_regenerate_canary'] = True
    with pytest.raises(ValueError, match='readiness'):
        gate.validate_initial_package(ledger, report)


def test_doc_gate_rejects_missing_endpoint_row_and_one_group_contradiction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    readme = (root / 'mcp_server/README.md').read_text(encoding='utf-8')
    broken_endpoint = readme.replace(
        '| `ForeignKeyTo` | `Column→Column`; `Table→Table` |\n', ''
    )
    broken_group = readme.replace(
        'keep FE and BO catalog objects in one group_id',
        'keep FE and BO catalog objects in separate group_id values',
    )

    fake = tmp_path / 'README.md'
    fake.write_text(broken_endpoint, encoding='utf-8')
    real_read_text = Path.read_text

    def endpoint_read(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == root / 'mcp_server/README.md':
            return fake.read_text(encoding='utf-8')
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', endpoint_read)
    with pytest.raises(AssertionError, match='endpoint type map rows'):
        gate.check_docs_operator_sections(root)

    fake.write_text(broken_group, encoding='utf-8')
    with pytest.raises(AssertionError, match='missing required statements|contradicts'):
        gate.check_docs_operator_sections(root)


@pytest.mark.parametrize(
    'call',
    [
        'call(group_id=alias)',
        'call(group_ids=[alias])',
        "call(request={'group_id': alias})",
        "call({'group_id': alias})",
        "request = {'group_id': alias}\ncall(request)",
        "payload = {'group_id': alias}\ncall(payload)",
    ],
)
def test_safety_scan_detects_forbidden_alias_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, call: str
):
    source = tmp_path / 'synthetic.py'
    source.write_text(
        f"FORBIDDEN_GROUP = 'oracle-catalog-v2'\nalias = FORBIDDEN_GROUP\n{call}\n",
        encoding='utf-8',
    )
    monkeypatch.setattr(gate, 'PHASE5_SAFETY_SCAN_RELS', (str(source),))
    scan = gate.scan_current_source_v2_param_query(Path('/'))
    assert scan['current_source_v2_param_query'] is True
    assert scan['hits']


def test_check_migration_current_guide_passes():
    gate.check_docs_migration_phrases(_root())
