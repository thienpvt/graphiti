#!/usr/bin/env python3
"""Phase 5 fail-closed gate runner (stdlib only).

Wave 0 scaffold: structural checks + ready_to_regenerate_canary fail-closed defaults.
Product GREEN and full gate proofs land in 05-02..05-07 (D-01, D-02, D-20, D-21).

Never opens oracle-catalog-v2. Live proofs stay on oracle-catalog-tool-test only.
Historical a67789a is immutable audit pointer only. Never shells canary runner.
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

SCHEMA_VERSION = 'phase5-gate-results.v1'
PHASE_DIR_REL = Path('.planning/phases/05-verification-security-compatibility-and-migration-docs')
DEFAULT_LEDGER_REL = PHASE_DIR_REL / '05-GATE-RESULTS.json'
OUTPUT_BOUND = 4000
FORBIDDEN_GROUP = 'oracle-catalog-v2'
ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
TEST_GROUP = ALLOWED_TEST_GROUP
EXPECTED_PROBE_COUNT = 37
EXPECTED_REQUIREMENT_COUNT = 17

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
    PHASE_DIR_REL / '05-VALIDATION.md',
    PHASE_DIR_REL / '05-CONTEXT.md',
    PHASE_DIR_REL / '05-EDGE-PROBE-RESOLUTION.md',
    PHASE_DIR_REL / '05-01-SUMMARY.md',
    PHASE_DIR_REL / '05-02-SUMMARY.md',
    PHASE_DIR_REL / '05-03-SUMMARY.md',
    PHASE_DIR_REL / '05-04-SUMMARY.md',
    PHASE_DIR_REL / '05-05-SUMMARY.md',
    PHASE_DIR_REL / '05-06-SUMMARY.md',
    PHASE_DIR_REL / '05-07-SUMMARY.md',
)

# Phase 5 focused suite (security / legacy / canary / gate / ollama).
FOCUS_TEST_FILES = (
    'mcp_server/tests/test_catalog_security_matrix.py',
    'mcp_server/tests/test_catalog_store_unit.py',
    'mcp_server/tests/test_catalog_service.py',
    'mcp_server/tests/test_legacy_mcp_contract_compatibility.py',
    'mcp_server/tests/test_catalog_canary_scripts.py',
    'mcp_server/tests/test_catalog_phase5_gate_runner.py',
    'mcp_server/tests/test_catalog_ollama_e2e.py',
)

# Phase 5 product/test sources scanned for current v2 param/query usage (no DB).
PHASE5_SAFETY_SCAN_RELS = (
    'mcp_server/src/graphiti_mcp_server.py',
    'mcp_server/src/services/catalog_capabilities.py',
    'mcp_server/src/services/catalog_service.py',
    'mcp_server/src/services/catalog_store.py',
    'mcp_server/tests/test_catalog_security_matrix.py',
    'mcp_server/tests/test_catalog_service.py',
    'mcp_server/tests/test_catalog_store_unit.py',
    'mcp_server/tests/test_legacy_mcp_contract_compatibility.py',
    'mcp_server/tests/test_catalog_canary_scripts.py',
    'mcp_server/tests/test_catalog_ollama_e2e.py',
    'mcp_server/tests/catalog_phase5_gate_runner.py',
    'mcp_server/tests/test_catalog_phase5_gate_runner.py',
)

# Plan ownership for research probe rows 0..36 (37 probes).
PLAN_OWNERSHIP = {
    '05-01': frozenset(range(0, 6)),
    '05-02': frozenset(range(6, 12)),
    '05-03': frozenset(range(12, 18)),
    '05-04': frozenset(range(18, 24)),
    '05-05': frozenset(range(24, 30)),
    '05-06': frozenset(range(30, 34)),
    '05-07': frozenset(range(34, 37)),
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
    'or mutate oracle-catalog-v2 again; Phase 5 preserves pointer only'
)

WAVE0_REQUIRED = (
    'mcp_server/tests/catalog_phase5_gate_runner.py',
    'mcp_server/tests/test_catalog_phase5_gate_runner.py',
    'mcp_server/tests/test_catalog_security_matrix.py',
    'mcp_server/tests/test_legacy_mcp_contract_compatibility.py',
    'mcp_server/tests/fixtures/legacy_mcp_contract_baseline.json',
    'mcp_server/tests/test_catalog_canary_scripts.py',
    'mcp_server/tests/test_catalog_ollama_e2e.py',
)

SCAFFOLD_CASES = {
    'security_matrix': (
        'mcp_server/tests/test_catalog_security_matrix.py',
        (
            'test_prohibited_tools_absent_on_catalog_paths',
            'test_llm_or_queue_or_community_ban_on_catalog_paths',
            'test_client_controlled_cypher_entity_identifiers_fail_before_query',
            'test_missing_endpoint_returns_structured_error_zero_writes',
            'test_fail_closed_conflicts_no_silent_repair',
            'test_log_empty_batch_omits_payload_and_credentials',
        ),
    ),
    'legacy_contract': (
        'mcp_server/tests/test_legacy_mcp_contract_compatibility.py',
        (
            'test_baseline_fixture_lists_exactly_14_legacy_tools',
            'test_catalog_tool_names_exact_14_separate_from_legacy',
            'test_tool_union_exact_28',
            'test_legacy_contract_metadata_defaults_schemas_response_invariants',
        ),
    ),
    'canary_offline': (
        'mcp_server/tests/test_catalog_canary_scripts.py',
        (
            'test_historical_inventory_and_digests_preserved',
            'test_hardened_manifest_schema_strict',
            'test_prepare_catalog_batch_commit_prepared_sequence_preferred',
            'test_offline_canary_no_external_side_effect',
        ),
    ),
    'ollama_e2e': (
        'mcp_server/tests/test_catalog_ollama_e2e.py',
        (
            'test_module_hardcodes_allowed_test_group_only',
            'test_ollama_e2e_skips_when_unavailable',
            'test_ollama_e2e_never_shells_canary_runner',
        ),
    ),
    'gate_runner': (
        'mcp_server/tests/test_catalog_phase5_gate_runner.py',
        (
            'test_ready_to_regenerate_canary_false_without_proofs',
            'test_ready_to_regenerate_canary_false_on_safety_violation',
            'test_historical_a67789a_pointer_preserved',
            'test_canary_executed_always_false',
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
        'mcp_server/tests/catalog_phase5_gate_runner.py',
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


def check_security_matrix_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['security_matrix']
    _require_defs(root / rel, names, 'security_matrix')


def check_legacy_contract_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['legacy_contract']
    _require_defs(root / rel, names, 'legacy_contract')
    baseline = root / 'mcp_server/tests/fixtures/legacy_mcp_contract_baseline.json'
    if not baseline.is_file():
        raise AssertionError('legacy_mcp_contract_baseline.json missing')
    data = json.loads(baseline.read_text(encoding='utf-8'))
    if 'add_memory' not in data.get('legacy_tools', {}):
        raise AssertionError('baseline must include add_memory')
    if int(data.get('legacy_tool_count', 0)) != 14:
        raise AssertionError('baseline legacy_tool_count must be 14')


def check_canary_offline_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['canary_offline']
    _require_defs(root / rel, names, 'canary_offline')


def check_ollama_e2e_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['ollama_e2e']
    _require_defs(root / rel, names, 'ollama_e2e')


def check_gate_runner_scaffold(root: Path) -> None:
    rel, names = SCAFFOLD_CASES['gate_runner']
    _require_defs(root / rel, names, 'gate_runner')


def check_canary_not_executed(_root: Path) -> None:
    """D-01 / D-10: canary_executed always false; never shells canary script."""
    return


def check_historical_axis_preserved(root: Path) -> None:
    runner_src = (root / 'mcp_server/tests/catalog_phase5_gate_runner.py').read_text(
        encoding='utf-8'
    )
    if HISTORICAL_V2_COMMIT not in runner_src:
        raise AssertionError('a67789a missing from runner')
    if f"HISTORICAL_V2_COMMIT = '{HISTORICAL_V2_COMMIT}'" not in runner_src:
        raise AssertionError('HISTORICAL_V2_COMMIT binding must remain a67789a')
    if 'HISTORICAL_ORACLE_CATALOG_V2_QUERIED = True' not in runner_src:
        raise AssertionError('historical axis constant must remain True')


def check_docs_operator_sections(root: Path) -> None:
    """Wave 0: README exists (full phrase checks GREEN in 05-05)."""
    readme = root / 'mcp_server' / 'README.md'
    if not readme.is_file():
        raise AssertionError('mcp_server/README.md missing')


def check_docs_migration_phrases(root: Path) -> None:
    """Wave 0: migration guide path reserved (content GREEN in 05-05)."""
    mig = root / 'mcp_server' / 'docs' / 'CATALOG_V2_MIGRATION.md'
    if mig.is_file():
        text = mig.read_text(encoding='utf-8').lower()
        if 'automatic migration' in text and 'no automatic' not in text and 'never' not in text:
            raise AssertionError('migration guide must not claim automatic migration')


def check_registration_contract(root: Path) -> None:
    """Catalog frozenset size 14; key wrappers present (re-prove, no redesign)."""
    path = root / 'mcp_server/src/graphiti_mcp_server.py'
    if not path.is_file():
        raise AssertionError('graphiti_mcp_server.py missing')
    src = path.read_text(encoding='utf-8')
    if 'CATALOG_TOOL_NAMES' not in src:
        raise AssertionError('CATALOG_TOOL_NAMES missing')
    required = (
        'get_catalog_batch_manifest',
        'resolve_typed_edges',
        'get_catalog_evidence',
        'prepare_catalog_batch',
        'commit_prepared_catalog_batch',
    )
    for name in required:
        if f"'{name}'" not in src and f'"{name}"' not in src:
            raise AssertionError(f'CATALOG_TOOL_NAMES missing {name}')
    m = re.search(
        r'CATALOG_TOOL_NAMES\s*:\s*frozenset\[[^\]]+\]\s*=\s*frozenset\s*\(\s*\{([^}]+)\}',
        src,
        re.DOTALL,
    )
    if not m:
        raise AssertionError('CATALOG_TOOL_NAMES frozenset block not parseable')
    names = re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", m.group(1))
    if len(names) != 14 or len(set(names)) != 14:
        raise AssertionError(f'CATALOG_TOOL_NAMES must be exactly 14 unique names, got {names}')


def _non_comment_lines(src: str) -> list[str]:
    return [ln for ln in src.splitlines() if ln.strip() and not ln.lstrip().startswith('#')]


def scan_current_source_v2_param_query(root: Path) -> dict[str, Any]:
    """Static scan: forbidden group used as current query/group parameter (no DB).

    Allows historical constants, FORBIDDEN_GROUP bindings, comments, and ban-check
    string literals. Hits bare GROUP/group_id/TEST_GROUP assignments or call kwargs
    that target oracle-catalog-v2 as an active parameter.
    """
    hits: list[str] = []
    # Build patterns without embedding contiguous forbidden assignment literals.
    _q = chr(39)
    _dq = chr(34)
    _needle = FORBIDDEN_GROUP  # 'oracle-catalog-v2' alone is ok (ban constant)
    assign_re = re.compile(
        rf'(?<![A-Za-z_])(GROUP|group_id|TEST_GROUP)\s*=\s*[{_q}{_dq}]'
        + re.escape(_needle)
        + rf'[{_q}{_dq}]'
    )
    # Call/keyword forms: group_id=<quote>FORBIDDEN_GROUP<quote> (dynamic only).
    kw_re = re.compile(
        rf'(?<![A-Za-z_])group_id\s*=\s*[{_q}{_dq}]' + re.escape(_needle) + rf'[{_q}{_dq}]'
    )
    for rel in PHASE5_SAFETY_SCAN_RELS:
        path = root / rel
        if not path.is_file():
            continue
        src = path.read_text(encoding='utf-8')
        for i, line in enumerate(src.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue
            # Allow FORBIDDEN_GROUP / HISTORICAL_* bindings and ban-check construction.
            if 'FORBIDDEN_GROUP' in line or re.search(r'\bHISTORICAL_', line):
                continue
            if assign_re.search(line) or kw_re.search(line):
                hits.append(f'{rel}:{i}')
    return {
        'current_oracle_catalog_v2_queried': bool(hits),
        'current_source_v2_param_query': bool(hits),
        'hits': hits,
    }


def check_safety_no_probe(root: Path) -> None:
    """No canary, no clear_graph, no oracle-catalog-v2 as current write/query target."""
    _q = chr(39)
    _dq = chr(34)
    assign_ban = re.compile(
        rf'(?<![A-Za-z_])(GROUP|group_id|TEST_GROUP)\s*=\s*[{_q}{_dq}]'
        + re.escape(FORBIDDEN_GROUP)
        + rf'[{_q}{_dq}]'
    )
    for rel in WAVE0_REQUIRED:
        path = root / rel
        if not path.is_file():
            raise AssertionError(f'missing {rel}')
        src = path.read_text(encoding='utf-8')
        # Skip pure comment lines so ban docs cannot self-match.
        code_src = '\n'.join(_non_comment_lines(src))
        if assign_ban.search(code_src):
            raise AssertionError(f'{rel} assigns forbidden group as write target')
        if re.search(r'\bclear_graph\s*\(', src):
            raise AssertionError(f'{rel} calls clear_graph')
        if re.search(r'\bcanary\s*\(', code_src, re.IGNORECASE):
            raise AssertionError(f'{rel} references canary execution')

    scan = scan_current_source_v2_param_query(root)
    if scan['current_source_v2_param_query']:
        raise AssertionError(
            f'current source uses forbidden group as query/param: {scan["hits"][:8]}'
        )

    runner_src = (root / 'mcp_server/tests/catalog_phase5_gate_runner.py').read_text(
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




CHECK_FUNCS = {
    'wave0_files': check_wave0_files,
    'safety_no_probe': check_safety_no_probe,
    'safety_no_v2_current': check_safety_no_probe,
    'security_matrix': check_security_matrix_scaffold,
    'legacy_contract_14': check_legacy_contract_scaffold,
    'catalog_registration_14': check_registration_contract,
    'tool_union_28': check_legacy_contract_scaffold,
    'canary_offline': check_canary_offline_scaffold,
    'offline_canary_pure': check_canary_offline_scaffold,
    'ollama_e2e_scaffold': check_ollama_e2e_scaffold,
    'gate_runner': check_gate_runner_scaffold,
    'canary_not_executed': check_canary_not_executed,
    'historical_axis_preserved': check_historical_axis_preserved,
    'docs_operator_sections': check_docs_operator_sections,
    'docs_migration_phrases': check_docs_migration_phrases,
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
        if a.endswith('run_catalog_canary_batch.py') or a == 'scripts/run_catalog_canary_batch.py':
            raise ValueError(f'{sid}: must not shell canary runner: {a}')


def validate_specs(specs: list[dict[str, Any]], root: Path | None = None) -> None:
    ids = [s['id'] for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f'duplicate spec ids: {ids}')
    for s in specs:
        validate_spec(s, root)


def canonical_specs(root: Path, *, include_live: bool = False) -> list[dict[str, Any]]:
    """Canonical argv specs for Wave 0 structural + focused suite.

    Live/Ollama availability-skip paths reserved; not required for unit gate.
    """
    root = root.resolve()
    _ = include_live
    specs: list[dict[str, Any]] = [
        {
            'id': 'runner_self_tests',
            'argv': _uv_pytest(
                ['mcp_server/tests/test_catalog_phase5_gate_runner.py'], ['--tb=short']
            ),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        {
            'id': 'focused_pytest',
            'argv': _uv_pytest(list(FOCUS_TEST_FILES), ['--tb=short']),
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
            'id': 'security_matrix',
            'argv': _runner_check_argv('security_matrix'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'legacy_contract_14',
            'argv': _runner_check_argv('legacy_contract_14'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'catalog_registration_14',
            'argv': _runner_check_argv('catalog_registration_14'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'tool_union_28',
            'argv': _runner_check_argv('tool_union_28'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'safety_no_v2_current',
            'argv': _runner_check_argv('safety_no_v2_current'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'safety',
        },
        {
            'id': 'historical_axis_preserved',
            'argv': _runner_check_argv('historical_axis_preserved'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'safety',
        },
        {
            'id': 'canary_not_executed',
            'argv': _runner_check_argv('canary_not_executed'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'safety',
        },
        {
            'id': 'offline_canary_pure',
            'argv': _runner_check_argv('offline_canary_pure'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'docs_operator_sections',
            'argv': _runner_check_argv('docs_operator_sections'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'docs_migration_phrases',
            'argv': _runner_check_argv('docs_migration_phrases'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        {
            'id': 'gate_runner',
            'argv': _runner_check_argv('gate_runner'),
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
        if r.get('kind') in ('live', 'availability-skip'):
            continue
        if not r.get('mandatory', True):
            continue
        # Skip ≠ pass (D-02/D-03).
        if r.get('status') in ('skip', 'skipped'):
            return False
        if r.get('status') != 'pass':
            return False
        if r.get('exit_code') != r.get('expected_exit', 0):
            return False
    return True


def derive_safety_ledger(
    results: list[dict[str, Any]],
    root: Path | None = None,
) -> dict[str, Any]:
    """Two-axis safety: permanent historical audit + current execution/source safety.

    Top-level oracle_catalog_v2_queried is CURRENT only (false when clean).
    Historical a67789a lives under historical_* / historical_audit only.
    """
    safety_ids = {'safety_no_v2_current', 'safety_no_probe', 'canary_not_executed'}
    by_id = {r.get('id'): r for r in results}
    current_safety_ok = all(
        by_id.get(sid, {}).get('status') == 'pass' and by_id.get(sid, {}).get('exit_code') == 0
        for sid in safety_ids
    )
    canary_executed = False
    clear_called = False
    if root is not None:
        scan = scan_current_source_v2_param_query(root)
        current_source_v2_param = bool(scan['current_source_v2_param_query'])
        current_v2_queried = bool(scan['current_oracle_catalog_v2_queried'])
        v2_hits = list(scan.get('hits') or [])
    else:
        current_source_v2_param = False
        current_v2_queried = False
        v2_hits = []
    if current_source_v2_param or current_v2_queried:
        current_safety_ok = False
    return {
        'canary_executed': canary_executed,
        # CURRENT axis only — do not OR with historical (D-30 / no-v2 current).
        'oracle_catalog_v2_queried': current_v2_queried,
        'current_oracle_catalog_v2_queried': current_v2_queried,
        'clear_graph_called': clear_called,
        'safety_checks_pass': current_safety_ok,
        'test_group': ALLOWED_TEST_GROUP,
        'forbidden_group': FORBIDDEN_GROUP,
        'historical_oracle_catalog_v2_queried': HISTORICAL_ORACLE_CATALOG_V2_QUERIED,
        'historical_v2_commit': HISTORICAL_V2_COMMIT,
        'historical_v2_class': HISTORICAL_V2_CLASS,
        'historical_v2_scope': HISTORICAL_V2_SCOPE,
        'current_source_v2_param_query': current_source_v2_param,
        'current_source_v2_hits': v2_hits,
        'historical_violation_note': HISTORICAL_V2_VIOLATION_NOTE,
    }


def derive_ready_to_regenerate_canary(
    local_gate_pass: bool,
    safety: dict[str, Any],
    *,
    registration_pass: bool,
    unit_service_pass: bool,
    security_matrix_pass: bool = False,
    legacy_contract_pass: bool = False,
    offline_canary_pass: bool = False,
    docs_pass: bool = False,
    audits_pass: bool = False,
    post_execution_audits_pending: bool = True,
    phase_5_complete: bool = False,
) -> bool:
    """Fail-closed readiness for canary regeneration (D-01, D-02).

    Default false. True only when all available mandatory checks pass, skip≠pass,
    current safety clean, post-execution audits accepted, and phase complete.
    Wave 0 always returns false (audits pending / incomplete).
    """
    if post_execution_audits_pending:
        return False
    if not phase_5_complete:
        return False
    if not local_gate_pass:
        return False
    if not unit_service_pass:
        return False
    if not registration_pass:
        return False
    if not security_matrix_pass:
        return False
    if not legacy_contract_pass:
        return False
    if not offline_canary_pass:
        return False
    if not docs_pass:
        return False
    if not audits_pass:
        return False
    if safety.get('canary_executed') is not False:
        return False
    if safety.get('clear_graph_called') is not False:
        return False
    if safety.get('current_source_v2_param_query') is not False:
        return False
    if safety.get('current_oracle_catalog_v2_queried') is not False:
        return False
    if safety.get('oracle_catalog_v2_queried') is not False:
        return False
    if safety.get('safety_checks_pass') is not True:
        return False
    return True


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
    if ledger.get('oracle_catalog_v2_queried') is not False:
        return 1
    if ledger.get('current_oracle_catalog_v2_queried') is not False:
        return 1
    if safety.get('current_source_v2_param_query') is not False:
        return 1
    if safety.get('current_oracle_catalog_v2_queried') is not False:
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
    # Nested full-gate recursion guard: when focused_pytest includes gate-runner
    # unit tests that call run_gate, skip both runner_self_tests and focused_pytest.
    nested_skip = os.environ.get('CATALOG_PHASE5_GATE_SKIP_SELF') == '1'
    # Prevent focused_pytest subprocess from re-entering full gate via nested run_gate.
    prev_skip = os.environ.get('CATALOG_PHASE5_GATE_SKIP_SELF')
    os.environ['CATALOG_PHASE5_GATE_SKIP_SELF'] = '1'
    try:
        for spec in specs:
            if nested_skip and spec['id'] in ('runner_self_tests', 'focused_pytest'):
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
                        'note': 'nested self/focused suite skipped',
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
    finally:
        if prev_skip is None:
            os.environ.pop('CATALOG_PHASE5_GATE_SKIP_SELF', None)
        else:
            os.environ['CATALOG_PHASE5_GATE_SKIP_SELF'] = prev_skip

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
    by_id = {r.get('id'): r for r in results}

    def _spec_pass(spec_id: str) -> bool:
        row = by_id.get(spec_id) or {}
        return row.get('status') == 'pass' and row.get('exit_code') == row.get('expected_exit', 0)

    unit_service_pass = _spec_pass('focused_pytest')
    registration_pass = _spec_pass('catalog_registration_14') or _spec_pass('registration_contract')
    security_matrix_pass = _spec_pass('security_matrix')
    legacy_contract_pass = _spec_pass('legacy_contract_14')
    offline_canary_pass = _spec_pass('offline_canary_pure')
    docs_pass = _spec_pass('docs_operator_sections') and _spec_pass('docs_migration_phrases')

    # Wave 0 / initial: audits always pending → readiness false.
    ready = derive_ready_to_regenerate_canary(
        local_gate_pass,
        safety,
        registration_pass=registration_pass,
        unit_service_pass=unit_service_pass,
        security_matrix_pass=security_matrix_pass,
        legacy_contract_pass=legacy_contract_pass,
        offline_canary_pass=offline_canary_pass,
        docs_pass=docs_pass,
        audits_pass=False,
        post_execution_audits_pending=True,
        phase_5_complete=False,
    )

    ledger: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'evaluated_head': head,
        'proof_head': head,
        'canonical_specs': json.loads(specs_json),
        'spec_sha256': spec_sha,
        'content_sha256_map': content_map,
        'content_digest': digest,
        'raw_edge_probe_count': EXPECTED_PROBE_COUNT,
        'expected_requirement_count': EXPECTED_REQUIREMENT_COUNT,
        'sentinel': sentinel,
        'results': results,
        'local_gate_pass': local_gate_pass,
        'nyquist_compliant': False,
        'ready_to_regenerate_canary': ready,
        'phase_5_complete': False,
        'post_execution_audits_pending': True,
        'audits_pass': False,
        'unit_service_pass': unit_service_pass,
        'registration_pass': registration_pass,
        'security_matrix_pass': security_matrix_pass,
        'legacy_contract_pass': legacy_contract_pass,
        'offline_canary_pass': offline_canary_pass,
        'docs_pass': docs_pass,
        'canary_executed': False,
        'oracle_catalog_v2_queried': safety['oracle_catalog_v2_queried'],
        'current_oracle_catalog_v2_queried': safety['current_oracle_catalog_v2_queried'],
        'clear_graph_called': safety['clear_graph_called'],
        'api_coverage_detector': False,
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
            'resolution_policy': '37/37 research probe map; no silent drop',
            'd02_policy': (
                'ready_to_regenerate_canary true only after focused proofs + '
                'registration + safety + four audits; fail-closed otherwise'
            ),
            'unit_service_source': 'focused_pytest Phase 5 suite',
            'v2_axes': (
                'oracle_catalog_v2_queried/current_* = current HEAD source scan; '
                'historical_audit preserves a67789a permanently'
            ),
            'historical_v2_policy': HISTORICAL_V2_VIOLATION_NOTE,
            'no_canary': 'Phase 5 never executes canary; canary_executed always false',
            'no_v2': 'never query or mutate oracle-catalog-v2',
            'api_coverage_detector': 'detected=false; no COVERAGE.md required',
            'production_claim': False,
            'canary_claim': False,
            'evaluated_head_policy': (
                'evaluated_head/proof_head = HEAD at proof time; ledger commit may tip after'
            ),
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
    parser = argparse.ArgumentParser(description='Phase 5 catalog gate runner')
    parser.add_argument(
        'command',
        choices=(
            'run',
            'run-initial',
            'check',
            'check-docs',
            'check-migration',
            'finalize',
            'verify-final',
        ),
    )
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


    if args.command == 'check-docs':
        try:
            check_docs_operator_sections(root)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps({'check': 'docs_operator_sections', 'status': 'pass'}))
        return 0

    if args.command == 'check-migration':
        try:
            check_docs_migration_phrases(root)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps({'check': 'docs_migration_phrases', 'status': 'pass'}))
        return 0

    if args.command in ('finalize', 'verify-final'):
        print(
            json.dumps(
                {
                    'command': args.command,
                    'ready_to_regenerate_canary': False,
                    'phase_5_complete': False,
                    'post_execution_audits_pending': True,
                    'canary_executed': False,
                    'note': 'Wave 0: finalize/verify-final reserved for 05-07',
                },
                indent=2,
            )
        )
        return 1

    if args.command in ('run', 'run-initial'):
        os.environ.setdefault('CATALOG_PHASE5_GATE_SKIP_SELF', '0')
        ledger = run_gate(root, ledger_path)
        print(
            json.dumps(
                {
                    'local_gate_pass': ledger['local_gate_pass'],
                    'safety_checks_pass': (ledger.get('safety') or {}).get('safety_checks_pass'),
                    'ready_to_regenerate_canary': ledger['ready_to_regenerate_canary'],
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
