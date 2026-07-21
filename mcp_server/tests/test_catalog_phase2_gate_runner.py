"""Unit tests for catalog_phase2_gate_runner (no network, no Neo4j)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import catalog_phase2_gate_runner as gate  # noqa: E402


def _root() -> Path:
    return gate.repo_root_from(Path(__file__))


def test_canonical_specs_shape_and_reject_shell_integration():
    root = _root()
    specs = gate.canonical_specs(root)
    assert specs
    ids = [s['id'] for s in specs]
    assert len(ids) == len(set(ids))
    assert 'focused_pytest' in ids
    assert 'topology_evidence_hash_capabilities' in ids
    assert 'scoped_ruff' in ids
    assert 'scoped_pyright' in ids
    assert 'safety_no_probe' in ids
    assert 'edge_probe_resolution' in ids
    assert 'no_new_store_write_path' in ids
    # Focus files include topology/evidence/hash/capabilities.
    focused = next(s for s in specs if s['id'] == 'focused_pytest')
    joined = ' '.join(focused['argv'])
    for token in (
        'test_catalog_topology.py',
        'test_catalog_evidence.py',
        'test_catalog_hash.py',
        'test_catalog_capabilities.py',
    ):
        assert token in joined
    for s in specs:
        gate.validate_spec(s, root)
        assert s['expected_exit'] == 0
        assert isinstance(s['argv'], list) and s['argv']
        for a in s['argv']:
            norm = a.replace('\\', '/')
            assert not norm.endswith('test_catalog_neo4j_int.py')
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
    assert gate.derive_local_gate_pass(results, sentinel, 'skip', False) is False
    results[1]['status'] = 'pass'
    results[1]['exit_code'] = 0
    assert gate.derive_local_gate_pass(results, sentinel, 'skip', False) is True
    assert gate.derive_local_gate_pass(results, sentinel, 'pass', False) is False
    assert gate.derive_local_gate_pass(results, sentinel, 'skip', True) is False


def test_derive_ready_for_phase_3a_fail_closed():
    safety_ok = {
        'canary_executed': False,
        'oracle_catalog_v2_queried': False,
        'no_new_store_or_control_plane_write_path': True,
        'safety_checks_pass': True,
    }
    assert gate.derive_ready_for_phase_3a(True, safety_ok) is True
    assert gate.derive_ready_for_phase_3a(False, safety_ok) is False
    bad = dict(safety_ok, canary_executed=True)
    assert gate.derive_ready_for_phase_3a(True, bad) is False
    bad2 = dict(safety_ok, no_new_store_or_control_plane_write_path=False)
    assert gate.derive_ready_for_phase_3a(True, bad2) is False


def test_plan_ownership_covers_0_to_67_unique():
    covered: set[int] = set()
    for rows in gate.PLAN_OWNERSHIP.values():
        covered |= set(rows)
    assert covered == set(range(68))
    # no overlaps
    total = sum(len(v) for v in gate.PLAN_OWNERSHIP.values())
    assert total == 68


def test_injected_mandatory_failure_and_tamper_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _root()
    ledger_path = tmp_path / '02-GATE-RESULTS.json'

    def fake_run_argv(argv, root_arg, timeout=1800):  # noqa: ARG001
        return {
            'exit_code': 0,
            'stdout': '1 passed',
            'stderr': '',
            'counts': {'passed': 1, 'failed': 0, 'skipped': 0, 'deselected': 0, 'errors': 0},
        }

    monkeypatch.setattr(gate, 'run_argv', fake_run_argv)
    monkeypatch.setenv('CATALOG_PHASE2_GATE_SKIP_SELF', '1')
    if shutil.which('git') is None:
        monkeypatch.setattr(gate, 'git_head', lambda _root: '1' * 40)
        monkeypatch.setattr(gate, 'git_parent', lambda _root: '')
        monkeypatch.setattr(gate, 'git_show_files', lambda _root, _commit='HEAD': [])

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
    assert ledger['ready_for_phase_3a'] is False
    assert ledger['catalog_neo4j_int'] == 'skip'
    assert ledger['availability_probed'] is False
    assert ledger['canary_executed'] is False
    assert ledger['oracle_catalog_v2_queried'] is False
    assert ledger['schema_version'] == gate.SCHEMA_VERSION
    ids = [r['id'] for r in ledger['results']]
    assert 'focused_pytest' in ids
    assert 'safety_no_probe' in ids
    assert 'topology_evidence_hash_capabilities' in ids

    # Tamper specs digest
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['spec_sha256'] = '0' * 64
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path)
    assert ver['ok'] is False
    assert any('spec_sha256' in e for e in ver['errors'])

    # Fresh fail ledger then HEAD tamper
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

    # Missing result
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

    # Raw probe digest tamper
    ledger = gate.run_gate(
        root,
        ledger_path,
        injected_overrides={
            'focused_pytest': {'exit_code': 1, 'status': 'fail', 'stdout': '', 'stderr': ''}
        },
    )
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['raw_edge_probe_sha256'] = '1' * 64
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path)
    assert ver['ok'] is False
    assert any('raw_edge_probe_sha256' in e for e in ver['errors'])

    # Content digest tamper
    ledger = gate.run_gate(
        root,
        ledger_path,
        injected_overrides={
            'focused_pytest': {'exit_code': 1, 'status': 'fail', 'stdout': '', 'stderr': ''}
        },
    )
    raw = json.loads(ledger_path.read_text(encoding='utf-8'))
    raw['content_digest'] = '2' * 64
    ledger_path.write_text(json.dumps(raw), encoding='utf-8')
    ver = gate.verify_ledger(root, ledger_path)
    assert ver['ok'] is False
    assert any('content_digest' in e for e in ver['errors'])


def test_injected_mandatory_failure():
    """Alias node required by plan: test_injected_mandatory_failure."""
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
    assert (
        gate.derive_ready_for_phase_3a(
            False,
            {
                'canary_executed': False,
                'oracle_catalog_v2_queried': False,
                'no_new_store_or_control_plane_write_path': True,
                'safety_checks_pass': True,
            },
        )
        is False
    )


def test_no_integration_import_in_runner_source():
    module_file = gate.__file__
    assert module_file is not None
    src = Path(module_file).read_text(encoding='utf-8')
    import_lines = [
        ln for ln in src.splitlines() if ln.startswith('import ') or ln.startswith('from ')
    ]
    assert not any('test_catalog_neo4j_int' in ln for ln in import_lines)
    assert 'INTEGRATION_MODULE' in src
    assert 'test_catalog_neo4j_int' not in sys.modules
    assert 'ready_for_phase_3a' in src
    assert gate.FORBIDDEN_GROUP == 'oracle-catalog-v2'
    assert gate.ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'


def test_edge_probe_raw_structure():
    root = _root()
    gate.check_edge_probe_raw(root)
    data, raw_bytes, digest = gate.load_raw_probe(root)
    assert len(data['items']) == 68
    assert len(digest) == 64
    assert len(raw_bytes) > 0


# LF-normalized SHA-256 of 02-EDGE-PROBE.json (CRLF/CR → LF before hash).
EXPECTED_RAW_PROBE_LF_SHA256 = '16144e5ebc2ae9a46cda9b45ce0206e1290b954988c227ce97ec0a05f6149ce0'


@pytest.mark.parametrize(
    ('raw', 'canonical'),
    [
        (b'a\nb\n', b'a\nb\n'),
        (b'a\r\nb\r\n', b'a\nb\n'),
        (b'a\rb\r', b'a\nb\n'),
        (b'a\r\nb\rc\n', b'a\nb\nc\n'),
        (b'', b''),
        (b'no-final-newline', b'no-final-newline'),
        ('café\r\n'.encode(), 'café\n'.encode()),
    ],
)
def test_normalize_newlines_lf_text_matrix(raw: bytes, canonical: bytes):
    assert gate.normalize_newlines_lf(raw) == canonical


def test_sha256_bytes_lf_stable_across_newline_forms():
    lf = b'{"items":[]}\n'
    crlf = b'{"items":[]}\r\n'
    lone_cr = b'{"items":[]}\r'
    mixed = b'{"items":[]}\r\nline2\rline3\n'
    assert gate.sha256_bytes_lf(lf) == gate.sha256_bytes_lf(crlf)
    assert gate.sha256_bytes_lf(lf) == gate.sha256_bytes_lf(lone_cr)
    assert gate.sha256_bytes(lf) != gate.sha256_bytes(crlf)
    assert gate.sha256_bytes_lf(mixed) == gate.sha256_bytes(b'{"items":[]}\nline2\nline3\n')
    assert gate.sha256_bytes_lf(b'x\n') != gate.sha256_bytes_lf(b'x')


@pytest.mark.parametrize(
    'raw',
    [
        b'\xef\xbb\xbftext\n',
        b'\xff\xfetext',
        b'\xff\n',
        b'text\x00binary\n',
        b'text\x1fbinary\n',
    ],
)
def test_canonical_text_authority_rejects_bom_invalid_utf8_and_binary(raw: bytes):
    with pytest.raises(ValueError, match='BOM|UTF-8|binary'):
        gate.normalize_newlines_lf(raw)


def test_windows_checkout_simulation_preserves_canonical_authority(tmp_path: Path):
    lf = tmp_path / 'lf.txt'
    crlf = tmp_path / 'crlf.txt'
    lf.write_bytes('café\nline\n'.encode())
    crlf.write_bytes('café\r\nline\r\n'.encode())
    assert gate.sha256_file_lf(lf) == gate.sha256_file_lf(crlf)
    assert gate.sha256_file(lf) != gate.sha256_file(crlf)


def _committed_or_archive_bytes(root: Path, relative: str) -> bytes:
    if (root / '.git').exists() and shutil.which('git') is not None:
        return gate.subprocess.run(
            ['git', 'cat-file', 'blob', f'HEAD:{relative}'],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout
    return (root / relative).read_bytes()


def test_raw_git_lf_is_committed_authority():
    root = _root()
    relative = 'mcp_server/tests/fixtures/accept_tab_sanitized.json'
    committed = _committed_or_archive_bytes(root, relative)
    worktree = (root / relative).read_bytes()
    assert b'\r' not in committed
    assert gate.sha256_bytes(committed) == EXPECTED_FIXTURE_GIT_RAW_SHA256
    assert gate.sha256_bytes_lf(committed) == EXPECTED_FIXTURE_GIT_RAW_SHA256
    assert gate.sha256_bytes_lf(worktree) == EXPECTED_FIXTURE_GIT_RAW_SHA256
    if b'\r\n' in worktree:
        assert gate.sha256_bytes(worktree) != EXPECTED_FIXTURE_GIT_RAW_SHA256


EXPECTED_FIXTURE_GIT_RAW_SHA256 = '145f38edb7245c448badc7598e2e0733b4c72c16f470909284c6e7d955bae922'


@pytest.mark.parametrize(
    ('relative', 'expected'),
    [
        (
            'catalog/CANARY_V2_SUMMARY.md',
            '4221f04488eeb77810e545b62aa49d7271ec6b5ac0bf4ad6dafb1397659ba0d8',
        ),
        (
            'catalog/catalog.json.graphiti-canary-v2-state.json',
            '2b1af22938104c3af84b1a9eefc602b7e7149e52de177dc1fffccee426f24b9d',
        ),
    ],
)
def test_raw_git_authority_values_are_lf_committed(relative: str, expected: str):
    root = _root()
    committed = _committed_or_archive_bytes(root, relative)
    assert b'\r' not in committed
    assert gate.sha256_bytes(committed) == expected
    assert gate.sha256_bytes_lf(committed) == expected
    assert gate.sha256_file_lf(root / relative) == expected


def test_load_raw_probe_digest_is_lf_normalized_and_matches_fixture(tmp_path: Path):
    # LF and CRLF fixture copies yield the same load_raw_probe digest.
    sample_lf = b'{"schema":"x","items":[{"a":1}],"coverage":{}}\n'
    sample_crlf = sample_lf.replace(b'\n', b'\r\n')
    assert b'\r\n' in sample_crlf
    expected = gate.sha256_bytes_lf(sample_lf)
    assert expected == gate.sha256_bytes_lf(sample_crlf)

    for label, payload in (('lf', sample_lf), ('crlf', sample_crlf)):
        root = tmp_path / label
        probe = root / gate.DEFAULT_RAW_PROBE_REL
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(payload)
        data, raw_bytes, digest = gate.load_raw_probe(root)
        assert digest == expected
        assert raw_bytes == payload  # raw bytes preserved for re-read checks
        assert data['items'] == [{'a': 1}]


def test_actual_raw_probe_lf_normalized_digest():
    root = _root()
    data, raw_bytes, digest = gate.load_raw_probe(root)
    assert len(data['items']) == 68
    assert digest == EXPECTED_RAW_PROBE_LF_SHA256
    # Digest equals pure helper over raw bytes regardless of on-disk newlines.
    assert digest == gate.sha256_bytes_lf(raw_bytes)
    assert digest == gate.sha256_file_lf(root / gate.DEFAULT_RAW_PROBE_REL)
    # Same-checkout re-read identity still holds on raw_bytes.
    again = (root / gate.DEFAULT_RAW_PROBE_REL).read_bytes()
    assert again == raw_bytes
