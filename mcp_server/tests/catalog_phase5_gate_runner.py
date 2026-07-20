#!/usr/bin/env python3
"""Phase 5 fail-closed gate runner (stdlib only).

Wave 0 scaffold: structural checks + ready_to_regenerate_canary fail-closed defaults.
Product GREEN and full gate proofs land in 05-02..05-07 (D-01, D-02, D-20, D-21).

Never opens oracle-catalog-v2. Live proofs stay on oracle-catalog-tool-test only.
Historical a67789a is immutable audit pointer only. Never shells canary runner.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
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

DEFAULT_REPORT_JSON_REL = PHASE_DIR_REL / '05-IMPLEMENTATION-REPORT.json'
DEFAULT_REPORT_MD_REL = PHASE_DIR_REL / '05-IMPLEMENTATION-REPORT.md'
DEFAULT_PACKAGE_MARKER_REL = PHASE_DIR_REL / '05-PROOF-PACKAGE.json'
PROOF_PACKAGE_SCHEMA_VERSION = 'phase5-proof-package.v1'
AUDIT_RELS = (
    PHASE_DIR_REL / '05-REVIEW.md',
    PHASE_DIR_REL / '05-VALIDATION.md',
    PHASE_DIR_REL / '05-SECURITY.md',
    PHASE_DIR_REL / '05-VERIFICATION.md',
)
POST_PROOF_TRACKING_RELS = (
    Path('.planning/ROADMAP.md'),
    Path('.planning/REQUIREMENTS.md'),
    Path('.planning/STATE.md'),
    PHASE_DIR_REL / '05-07-SUMMARY.md',
)
PROOF_CLOSURE_RELS = frozenset(
    {
        DEFAULT_LEDGER_REL.as_posix(),
        DEFAULT_REPORT_JSON_REL.as_posix(),
        DEFAULT_REPORT_MD_REL.as_posix(),
        DEFAULT_PACKAGE_MARKER_REL.as_posix(),
        *(path.as_posix() for path in AUDIT_RELS),
        *(path.as_posix() for path in POST_PROOF_TRACKING_RELS),
    }
)
INITIAL_GATE_INPUT_RELS = (
    PHASE_DIR_REL / '05-CONTEXT.md',
    PHASE_DIR_REL / '05-RESEARCH.md',
    PHASE_DIR_REL / '05-EDGE-PROBE-RESOLUTION.md',
    PHASE_DIR_REL / '05-EDGE-PROBE-LEDGER.json',
    PHASE_DIR_REL / '05-01-PLAN.md',
    PHASE_DIR_REL / '05-02-PLAN.md',
    PHASE_DIR_REL / '05-03-PLAN.md',
    PHASE_DIR_REL / '05-04-PLAN.md',
    PHASE_DIR_REL / '05-05-PLAN.md',
    PHASE_DIR_REL / '05-06-PLAN.md',
    PHASE_DIR_REL / '05-07-PLAN.md',
    PHASE_DIR_REL / '05-01-SUMMARY.md',
    PHASE_DIR_REL / '05-02-SUMMARY.md',
    PHASE_DIR_REL / '05-03-SUMMARY.md',
    PHASE_DIR_REL / '05-04-SUMMARY.md',
    PHASE_DIR_REL / '05-05-SUMMARY.md',
    Path('mcp_server/README.md'),
    Path('mcp_server/docs/CATALOG_V2_MIGRATION.md'),
    Path('mcp_server/tests/fixtures/legacy_mcp_contract_baseline.json'),
    Path('scripts/build_catalog_canary_requests.py'),
    Path('scripts/run_catalog_canary_batch.py'),
    Path('mcp_server/tests/test_catalog_canary_scripts.py'),
    Path('mcp_server/tests/fixtures/accept_tab_sanitized.json'),
    Path('catalog/canary-v2-requests-hardened/accept-tab.payload.json'),
    Path('catalog/canary-v2-requests-hardened/offline-prepare.receipt.json'),
    Path('catalog/canary-v2-requests-hardened/offline-commit.receipt.json'),
    Path('catalog/canary-v2-requests-hardened/offline-checkpoint.json'),
    Path('catalog/canary-v2-requests-hardened/manifest.json'),
    Path('catalog/catalog.json.graphiti-canary-v2-state.json'),
)
FINAL_GATE_INPUT_RELS = INITIAL_GATE_INPUT_RELS + (
    PHASE_DIR_REL / '05-06-SUMMARY.md',
    *AUDIT_RELS,
)
# Backward-compatible name for callers that inspect the initial evidence set.
GATE_INPUT_RELS = INITIAL_GATE_INPUT_RELS

REQUIREMENT_IDS = (
    'IDEN-13',
    'SAFE-03',
    'SAFE-04',
    'SAFE-06',
    'SAFE-07',
    'SAFE-09',
    'SAFE-10',
    'TEST-10',
    'TEST-11',
    'TEST-12',
    'DOCS-01',
    'DOCS-02',
    'DOCS-03',
    'DOCS-04',
    'DOCS-05',
    'DOCS-06',
    'REPT-01',
)
EDGE_PROBE_IDS = (
    'IDEN-13-unclassified',
    'SAFE-03-unclassified',
    'SAFE-04-concurrency',
    'SAFE-06-concurrency',
    'SAFE-07-empty',
    'SAFE-07-encoding',
    'SAFE-09-empty',
    'SAFE-09-encoding',
    'SAFE-09-concurrency',
    'SAFE-10-adjacency',
    'SAFE-10-empty',
    'SAFE-10-ordering',
    'TEST-10-empty',
    'TEST-10-encoding',
    'TEST-11-empty',
    'TEST-11-encoding',
    'TEST-12-adjacency',
    'TEST-12-empty',
    'TEST-12-ordering',
    'TEST-12-idempotency',
    'TEST-12-concurrency',
    'DOCS-01-adjacency',
    'DOCS-01-empty',
    'DOCS-01-ordering',
    'DOCS-02-adjacency',
    'DOCS-02-empty',
    'DOCS-02-ordering',
    'DOCS-02-concurrency',
    'DOCS-03-unclassified',
    'DOCS-04-adjacency',
    'DOCS-04-empty',
    'DOCS-04-ordering',
    'DOCS-05-unclassified',
    'DOCS-06-unclassified',
    'REPT-01-adjacency',
    'REPT-01-empty',
    'REPT-01-ordering',
)
CANONICAL_CHECK_IDS = (
    'runner_self_tests',
    'focused_pytest',
    'security_matrix',
    'legacy_contract_14',
    'catalog_registration_14',
    'tool_union_28',
    'cypher_identifier_authority',
    'endpoint_no_implicit_creation',
    'safety_no_v2_current',
    'historical_axis_preserved',
    'historical_artifacts_unchanged',
    'hardened_artifacts_strict',
    'canary_not_executed',
    'offline_canary_pure',
    'docs_operator_sections',
    'docs_migration_phrases',
    'ruff',
    'pyright',
    'live_neo4j_test11',
    'ollama_e2e',
)
OPTIONAL_AVAILABILITY_CHECK_IDS = frozenset(
    {'ruff', 'pyright', 'live_neo4j_test11', 'ollama_e2e'}
)
AUDIT_NAMES = ('review', 'validation', 'security', 'verification')
AUDIT_PATH_BY_NAME = dict(zip(AUDIT_NAMES, AUDIT_RELS, strict=True))
# Finalization reruns every canonical check. This costs one bounded local Neo4j/Ollama
# pass, but prevents an editable self-hashed initial ledger from minting final readiness.
FINAL_RERUN_CHECK_IDS = CANONICAL_CHECK_IDS
PRESERVED_EXTERNAL_CHECK_IDS: tuple[str, ...] = ()

HISTORICAL_CHECKPOINT_SHA256 = (
    'b367e7f395782d13e72671e1b66d36b24432cb2c1b48c7fa45974d232039ace4'
)
HISTORICAL_CHECKPOINT_ATTEMPT_COUNT = 2
HARDENED_CHECKPOINT_ATTEMPT_COUNT = 0
HARDENED_ARTIFACT_DIR_REL = Path('catalog/canary-v2-requests-hardened')
HARDENED_EXPECTED_FILE_NAMES = frozenset(
    {
        'accept-tab.payload.json',
        'offline-prepare.receipt.json',
        'offline-commit.receipt.json',
        'offline-checkpoint.json',
        'manifest.json',
    }
)
AUDIT_SCOPE_ID = 'phase5-execution-inputs.v1'
AUDIT_BINDING_KEYS = frozenset(
    {
        'evaluated_head',
        'execution_input_digest',
        'reviewed_worktree_digest',
        'initial_ledger_sha256',
        'audited_at',
    }
)

# Phase 5 focused offline suite. Infrastructure-specific modules run separately.
FOCUS_TEST_FILES = (
    'mcp_server/tests/test_catalog_security_matrix.py',
    'mcp_server/tests/test_catalog_canary_scripts.py',
    'mcp_server/tests/test_catalog_canary_review_regressions.py',
    'mcp_server/tests/test_catalog_service.py',
    'mcp_server/tests/test_catalog_capabilities.py',
    'mcp_server/tests/test_catalog_gates.py',
    'mcp_server/tests/test_catalog_commit_recovery.py',
    'mcp_server/tests/test_catalog_concurrency.py',
    'mcp_server/tests/test_catalog_store_unit.py',
    'mcp_server/tests/test_legacy_mcp_contract_compatibility.py',
)
LIVE_TEST_FILES = (
    'mcp_server/tests/test_catalog_neo4j_int.py',
    'mcp_server/tests/test_catalog_commit_neo4j_int.py',
    'mcp_server/tests/test_catalog_prepare_neo4j_int.py',
)
RUFF_FILES = (
    'mcp_server/src/services/catalog_service.py',
    'mcp_server/src/services/catalog_store.py',
    'scripts/build_catalog_canary_requests.py',
    'scripts/run_catalog_canary_batch.py',
    'mcp_server/tests/catalog_phase5_gate_runner.py',
    'mcp_server/tests/test_catalog_phase5_gate_runner.py',
    'mcp_server/tests/test_catalog_security_matrix.py',
    'mcp_server/tests/test_catalog_canary_scripts.py',
    'mcp_server/tests/test_catalog_canary_review_regressions.py',
    'mcp_server/tests/test_catalog_ollama_e2e.py',
)
PYRIGHT_FILES = (
    'mcp_server/src/services/catalog_service.py',
    'mcp_server/src/services/catalog_store.py',
    'scripts/build_catalog_canary_requests.py',
    'scripts/run_catalog_canary_batch.py',
    'mcp_server/tests/catalog_phase5_gate_runner.py',
    'mcp_server/tests/test_catalog_phase5_gate_runner.py',
    'mcp_server/tests/test_catalog_security_matrix.py',
    'mcp_server/tests/test_catalog_canary_scripts.py',
    'mcp_server/tests/test_catalog_canary_review_regressions.py',
    'mcp_server/tests/test_catalog_ollama_e2e.py',
)
EXECUTION_INPUT_DIR_RELS = (Path('graphiti_core'), Path('mcp_server/src'))
EXECUTION_INPUT_FILE_RELS = tuple(
    dict.fromkeys(
        (
            Path('mcp_server/pyproject.toml'),
            Path('mcp_server/pytest.ini'),
            Path('mcp_server/tests/catalog_phase5_gate_runner.py'),
            Path('mcp_server/tests/test_catalog_phase5_gate_runner.py'),
            Path('mcp_server/tests/test_catalog_security_matrix.py'),
            Path('mcp_server/tests/test_catalog_ollama_e2e.py'),
            *(Path(rel) for rel in FOCUS_TEST_FILES),
            *(Path(rel) for rel in LIVE_TEST_FILES),
            *(Path(rel) for rel in RUFF_FILES),
            *(Path(rel) for rel in PYRIGHT_FILES),
            Path('mcp_server/tests/test_catalog_canary_review_regressions.py'),
        )
    )
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
    'mcp_server/tests/catalog_neo4j_fixtures.py',
    'mcp_server/tests/test_catalog_neo4j_int.py',
    'mcp_server/tests/test_catalog_commit_neo4j_int.py',
    'mcp_server/tests/test_catalog_prepare_neo4j_int.py',
    'mcp_server/tests/test_catalog_canary_scripts.py',
    'mcp_server/tests/test_catalog_ollama_e2e.py',
    'scripts/run_catalog_canary_batch.py',
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
            'test_representative_fail_closed_conflicts_no_silent_repair',
            'test_rejected_empty_and_malicious_logs_omit_sensitive_material',
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


def sha256_file_raw(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _call_target_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ''


def _constant_strings(node: ast.AST) -> list[str]:
    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def check_canary_not_executed(root: Path) -> None:
    """D-01 / D-10: no Phase 5 command can launch the canary runner."""
    runner_rel = 'scripts/run_catalog_canary_batch.py'
    phase_runner = root / 'mcp_server/tests/catalog_phase5_gate_runner.py'
    tree = ast.parse(phase_runner.read_text(encoding='utf-8'), filename=str(phase_runner))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _call_target_name(node)
        if target not in {'run', 'Popen', 'call', 'check_call', 'check_output', 'system'}:
            continue
        if any(runner_rel in value.replace('\\', '/') for value in _constant_strings(node)):
            raise AssertionError('Phase 5 gate must never launch the canary runner')

    for rel in (
        PHASE_DIR_REL / '05-01-PLAN.md',
        PHASE_DIR_REL / '05-02-PLAN.md',
        PHASE_DIR_REL / '05-03-PLAN.md',
        PHASE_DIR_REL / '05-04-PLAN.md',
        PHASE_DIR_REL / '05-05-PLAN.md',
        PHASE_DIR_REL / '05-06-PLAN.md',
        PHASE_DIR_REL / '05-07-PLAN.md',
    ):
        text = (root / rel).read_text(encoding='utf-8')
        for line in text.splitlines():
            normalized = line.replace('\\', '/')
            if runner_rel not in normalized:
                continue
            if re.search(r'\b(?:python|uv\s+run)\b.*run_catalog_canary_batch\.py', normalized):
                raise AssertionError(f'{rel.as_posix()} instructs canary execution')


def check_historical_artifacts_unchanged(root: Path) -> None:
    checkpoint = root / 'catalog/catalog.json.graphiti-canary-v2-state.json'
    if sha256_file_raw(checkpoint) != HISTORICAL_CHECKPOINT_SHA256:
        raise AssertionError('historical checkpoint digest changed')
    payload = json.loads(checkpoint.read_text(encoding='utf-8'))
    attempts = payload.get('attempts')
    if not isinstance(attempts, list) or len(attempts) != HISTORICAL_CHECKPOINT_ATTEMPT_COUNT:
        raise AssertionError('historical checkpoint attempt count changed')


def check_hardened_artifacts_strict(root: Path) -> None:
    artifact_dir = root / HARDENED_ARTIFACT_DIR_REL
    manifest_path = artifact_dir / 'manifest.json'
    checkpoint_path = artifact_dir / 'offline-checkpoint.json'
    if not manifest_path.is_file() or not checkpoint_path.is_file():
        raise AssertionError('hardened manifest/checkpoint missing')
    actual_names = frozenset(path.name for path in artifact_dir.iterdir() if path.is_file())
    if actual_names != HARDENED_EXPECTED_FILE_NAMES:
        extra = sorted(actual_names - HARDENED_EXPECTED_FILE_NAMES)
        missing = sorted(HARDENED_EXPECTED_FILE_NAMES - actual_names)
        raise AssertionError(
            f'hardened runtime artifact inventory mismatch: missing={missing}, extra={extra}'
        )
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
    if manifest.get('artifact_schema_version') != 'canary-hardened-v1':
        raise AssertionError('hardened manifest schema mismatch')
    if manifest.get('identity_schema_version') != 'catalog-v2':
        raise AssertionError('hardened manifest identity schema mismatch')
    if manifest.get('execution_mode') != 'offline_simulation':
        raise AssertionError('hardened manifest execution mode mismatch')
    if manifest.get('canary_executed') is not False:
        raise AssertionError('hardened manifest claims canary execution')
    if manifest.get('group_id') != ALLOWED_TEST_GROUP:
        raise AssertionError('hardened manifest group must be test-only')
    if manifest.get('preferred_tool_sequence', [])[:2] != [
        'prepare_catalog_batch',
        'commit_prepared_catalog_batch',
    ]:
        raise AssertionError('hardened sequence must start prepare/token-only commit')

    required_digests = {
        'payload',
        'offline_prepare_receipt',
        'offline_commit_receipt',
        'offline_checkpoint',
        'sanitized_fixture',
    }
    digests = manifest.get('digests')
    inventory = manifest.get('inventory')
    if not isinstance(digests, dict) or not isinstance(inventory, dict):
        raise AssertionError('hardened digest/inventory maps missing')
    if 'manifest' in digests:
        raise AssertionError('hardened manifest self-digest forbidden')
    if set(digests) != required_digests:
        raise AssertionError(f'hardened digest key set mismatch: {sorted(digests)}')
    root_resolved = root.resolve()
    for key in required_digests:
        rel = inventory.get(key)
        if not isinstance(rel, str) or not rel:
            raise AssertionError(f'hardened inventory path missing: {key}')
        path = (root / rel).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise AssertionError(f'hardened inventory path escapes root: {key}') from exc
        if not path.is_file():
            raise AssertionError(f'hardened inventory path stale: {key}')
        if sha256_file_raw(path) != digests[key]:
            raise AssertionError(f'hardened digest mismatch: {key}')
    for key, rel in inventory.items():
        if not isinstance(rel, str):
            raise AssertionError(f'hardened inventory path stale: {key}')
        path = (root / rel).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise AssertionError(f'hardened inventory path escapes root: {key}') from exc
        if not path.is_file():
            raise AssertionError(f'hardened inventory path stale: {key}')

    if checkpoint.get('canary_executed') is not False:
        raise AssertionError('hardened checkpoint claims canary execution')
    if checkpoint.get('canary_attempt_count') != HARDENED_CHECKPOINT_ATTEMPT_COUNT:
        raise AssertionError('hardened canary attempt count changed')


def check_cypher_identifier_authority(root: Path) -> None:
    security = root / 'mcp_server/tests/test_catalog_security_matrix.py'
    required = (
        'test_client_controlled_cypher_entity_identifiers_fail_before_query',
        'test_client_controlled_cypher_edge_identifiers_fail_before_query',
        'test_client_controlled_property_keys_fail_before_query',
        'test_cypher_identifier_registry_nonempty',
        'test_store_rejects_malicious_types_before_executor_or_transaction',
    )
    _require_defs(security, required, 'cypher identifier authority')


def check_endpoint_no_implicit_creation(root: Path) -> None:
    security = root / 'mcp_server/tests/test_catalog_security_matrix.py'
    required = (
        'test_missing_endpoint_returns_structured_error_zero_writes',
        'test_same_batch_endpoints_resolve_from_request_union_only',
        'test_implicit_endpoint_creation_forbidden',
    )
    _require_defs(security, required, 'endpoint no implicit creation')


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


def _literal_value(node: ast.AST, assignments: dict[str, object]) -> object:
    if isinstance(node, ast.Name) and node.id in assignments:
        return assignments[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        owner = _literal_value(node.func.value, assignments)
        if node.func.attr == 'keys' and isinstance(owner, dict) and not node.args:
            return tuple(owner)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {'set', 'frozenset'}
        and len(node.args) == 1
    ):
        values = _literal_value(node.args[0], assignments)
        if isinstance(values, (dict, list, tuple, set, frozenset)):
            items = tuple(values)
        else:
            raise TypeError('set/frozenset argument is not a static iterable')
        return frozenset(items) if node.func.id == 'frozenset' else set(items)
    return ast.literal_eval(node)


def _python_assignments(path: Path) -> dict[str, object]:
    """Return static module assignments without importing product code."""
    if not path.is_file():
        raise AssertionError(f'authoritative source missing: {path}')
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_node = node.value
            if value_node is None:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                try:
                    assignments[target.id] = _literal_value(value_node, assignments)
                except (ValueError, TypeError, KeyError):
                    continue
    return assignments


def _enum_string_values(path: Path, class_name: str) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        values: set[str] = set()
        for statement in node.body:
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                continue
            if not isinstance(statement.targets[0], ast.Name):
                continue
            value = ast.literal_eval(statement.value)
            if isinstance(value, str):
                values.add(value)
        if not values:
            raise AssertionError(f'{class_name} has no string members')
        return frozenset(values)
    raise AssertionError(f'{class_name} missing from {path}')


def _markdown_section(text: str, heading: str) -> str:
    match = re.search(
        rf'^(?P<marks>#{{2,6}})\s+{re.escape(heading)}\s*$',
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f'documentation section missing: {heading}')
    level = len(match.group('marks'))
    start = match.end()
    end = len(text)
    for candidate in re.finditer(r'^(?P<marks>#{2,6})\s+', text[start:], re.MULTILINE):
        if len(candidate.group('marks')) <= level:
            end = start + candidate.start()
            break
    return text[start:end]


def _tool_inventory_names(section: str) -> frozenset[str]:
    return frozenset(
        re.findall(r'^\s*(?:-\s+|\d+\.\s+)`([a-z][a-z0-9_]*)`', section, re.MULTILINE)
    )


def _error_code_names(section: str) -> frozenset[str]:
    return frozenset(
        re.findall(r'^\|\s*`([a-z][a-z0-9_]*)`\s*\|', section, re.MULTILINE)
    )


def _assert_exact_set(label: str, actual: frozenset[str], expected: frozenset[str]) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise AssertionError(f'{label} mismatch: missing={missing}, extra={extra}')


def _require_phrases(label: str, text: str, phrases: tuple[str, ...]) -> None:
    lowered = text.lower()
    missing = [phrase for phrase in phrases if phrase.lower() not in lowered]
    if missing:
        raise AssertionError(f'{label} missing required statements: {missing}')


def _assert_no_sensitive_values(text: str, label: str) -> None:
    """Reject secret-like assignments; allow explicit placeholders/default examples."""
    placeholder_values = {
        '',
        'none',
        'ollama',
        'password',
        'demodemo',
        'your_password',
        'your_openai_api_key_here',
        'your_anthropic_key',
        'your_gemini_key',
        'your_groq_key',
        'sk-xxxxxxxx',
    }
    assignment = re.compile(
        r'(?i)\b(?:password|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret)'
        r'\s*[:=]\s*[`"\']?([^\s`"\']+)'
    )
    for match in assignment.finditer(text):
        value = match.group(1).rstrip('`,;').lower()
        if value in placeholder_values or value.startswith(('your_', '${', '<')):
            continue
        if value in {'omitted', 'redacted'}:
            continue
        raise AssertionError(f'{label} contains a credential or raw namespace value')
    if re.search(
        r'(?i)\bGRAPHITI_CATALOG_UUID_NAMESPACE\s*=\s*[0-9a-f]{8}-[0-9a-f-]{27,}', text
    ) or re.search(r'(?i)\b(?:sk|ghp|glpat)-[A-Za-z0-9_-]{12,}', text):
        raise AssertionError(f'{label} contains a credential or raw namespace value')


def _registered_tool_names(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == 'tool'
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == 'mcp'
            ):
                names.add(node.name)
    return frozenset(names)


def _authoritative_doc_sets(root: Path) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    server = root / 'mcp_server/src/graphiti_mcp_server.py'
    assignments = _python_assignments(server)
    catalog_value = assignments.get('CATALOG_TOOL_NAMES')
    if not isinstance(catalog_value, (set, frozenset)):
        raise AssertionError('CATALOG_TOOL_NAMES must be a literal set/frozenset')
    catalog_tools = frozenset(str(name) for name in catalog_value)
    registered_tools = _registered_tool_names(server)
    legacy_tools = registered_tools - catalog_tools

    baseline_path = root / 'mcp_server/tests/fixtures/legacy_mcp_contract_baseline.json'
    if not baseline_path.is_file():
        raise AssertionError('legacy MCP baseline missing')
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    legacy_map = baseline.get('legacy_tools')
    if not isinstance(legacy_map, dict):
        raise AssertionError('legacy MCP baseline has no legacy_tools object')
    baseline_legacy = frozenset(str(name) for name in legacy_map)
    _assert_exact_set('registered legacy tools vs baseline', legacy_tools, baseline_legacy)

    error_codes = _enum_string_values(
        root / 'mcp_server/src/models/catalog_common.py', 'CatalogErrorCode'
    )
    if (
        len(legacy_tools) != 14
        or len(catalog_tools) != 14
        or len(registered_tools) != 28
        or legacy_tools & catalog_tools
    ):
        raise AssertionError('authoritative tool sets must be disjoint 14 legacy + 14 catalog')
    return legacy_tools, catalog_tools, error_codes


def _authoritative_endpoint_map(root: Path) -> dict[str, frozenset[tuple[str, str]]]:
    """Evaluate only the pure topology authority with imports disabled.

    The module contains constants, comprehensions, and set unions; reimplementing Python's
    expression semantics here is more error-prone than executing this bounded pure file.
    """
    common = _python_assignments(root / 'mcp_server/src/models/catalog_common.py')
    prefixes = common.get('ENTITY_TYPE_PREFIXES')
    if not isinstance(prefixes, dict):
        raise AssertionError('ENTITY_TYPE_PREFIXES authority is not statically parseable')
    path = root / 'mcp_server/src/models/catalog_topology.py'
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    body = [
        node
        for node in tree.body
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef))
        and (
            not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            or node.name == '_product'
        )
    ]
    scope: dict[str, Any] = {
        '__builtins__': {'frozenset': frozenset, 'tuple': tuple, 'list': list, 'set': set},
        'CATALOG_ENTITY_TYPES': frozenset(str(name) for name in prefixes),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), scope)
    value = scope.get('EDGE_ENDPOINT_MAP')
    if not isinstance(value, dict):
        raise AssertionError('EDGE_ENDPOINT_MAP is not statically parseable')
    out: dict[str, frozenset[tuple[str, str]]] = {}
    for edge_type, pairs in value.items():
        if not isinstance(edge_type, str) or not isinstance(pairs, (set, frozenset)):
            raise AssertionError('EDGE_ENDPOINT_MAP contains invalid static data')
        out[edge_type] = frozenset((str(source), str(target)) for source, target in pairs)
    return out


def _endpoint_doc_pairs(section: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for edge_type, expression in re.findall(
        r'^\|\s*`([A-Za-z][A-Za-z0-9]*)`\s*\|\s*(.*?)\s*\|\s*$',
        section,
        re.MULTILINE,
    ):
        rows[edge_type] = expression
    return rows


def _parse_doc_type_set(value: str) -> frozenset[str]:
    clean = value.replace('`', '').strip()
    if clean.startswith('{') and clean.endswith('}'):
        clean = clean[1:-1]
    names = [name.strip() for name in re.split(r',|\bor\b', clean) if name.strip()]
    if not names or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', name) for name in names):
        raise AssertionError(f'unparseable endpoint type set: {value}')
    return frozenset(names)


def _parse_endpoint_expression(
    edge_type: str,
    expression: str,
    authority: dict[str, frozenset[tuple[str, str]]],
    entity_types: frozenset[str],
) -> frozenset[tuple[str, str]]:
    clean = expression.replace('`', '').strip()
    if clean.startswith('union of '):
        references = re.findall(r'[A-Za-z][A-Za-z0-9]*', clean.removeprefix('union of '))
        references = [name for name in references if name not in {'pairs'}]
        if not references or any(name not in authority for name in references):
            raise AssertionError(f'unparseable endpoint union: {edge_type}')
        return frozenset().union(*(authority[name] for name in references))

    if '× same set' in clean:
        left = clean.split('×', 1)[0].strip()
        types = _parse_doc_type_set(left)
        return frozenset((source, target) for source in types for target in types)

    pairs: set[tuple[str, str]] = set()
    for clause in clean.split(';'):
        if '→' not in clause:
            raise AssertionError(f'unparseable endpoint clause: {edge_type}: {clause}')
        source_text, target_text = (part.strip() for part in clause.split('→', 1))
        sources = (
            entity_types
            if source_text == 'every allowlisted entity type'
            else _parse_doc_type_set(source_text)
        )
        targets = _parse_doc_type_set(target_text)
        pairs.update((source, target) for source in sources for target in targets)
    return frozenset(pairs)


def _assert_registry_members(root: Path, text: str) -> None:
    common_assignments = _python_assignments(root / 'mcp_server/src/models/catalog_common.py')
    entity_prefixes = common_assignments.get('ENTITY_TYPE_PREFIXES')
    edge_types = common_assignments.get('CATALOG_EDGE_TYPES')
    if not isinstance(entity_prefixes, dict) or not isinstance(edge_types, (set, frozenset)):
        raise AssertionError('catalog entity/edge registries are not literal authoritative sets')

    registry = _markdown_section(text, 'Entity and edge registries')
    grammar = _markdown_section(text, 'Catalog-v2 graph-key grammar and group scope')
    endpoint_section = _markdown_section(text, 'Endpoint type map')
    endpoint_rows = _endpoint_doc_pairs(endpoint_section)
    endpoint_authority = _authoritative_endpoint_map(root)
    entity_type_names = frozenset(str(name) for name in entity_prefixes)
    parsed_endpoint_rows: dict[str, frozenset[tuple[str, str]]] = {}
    for edge_type in endpoint_rows:
        parsed_endpoint_rows[edge_type] = _parse_endpoint_expression(
            edge_type,
            endpoint_rows[edge_type],
            {**endpoint_authority, **parsed_endpoint_rows},
            entity_type_names,
        )
    for entity_type, prefix in entity_prefixes.items():
        if f'`{entity_type}`' not in registry or f'`{prefix}`' not in grammar:
            raise AssertionError(f'entity registry/grammar missing {entity_type} / {prefix}')
    if set(endpoint_rows) != set(endpoint_authority):
        raise AssertionError('endpoint type map rows differ from EDGE_ENDPOINT_MAP keys')
    for edge_type in edge_types:
        if f'`{edge_type}`' not in registry:
            raise AssertionError(f'edge registry missing {edge_type}')
        expression = endpoint_rows.get(str(edge_type), '')
        if not expression:
            raise AssertionError(f'endpoint type map missing {edge_type}')
        authority_pairs = endpoint_authority[str(edge_type)]
        if parsed_endpoint_rows[str(edge_type)] != authority_pairs:
            missing = sorted(authority_pairs - parsed_endpoint_rows[str(edge_type)])
            extra = sorted(parsed_endpoint_rows[str(edge_type)] - authority_pairs)
            raise AssertionError(
                f'endpoint type map {edge_type} differs from authority: '
                f'missing={missing[:5]}, extra={extra[:5]}'
            )

    identity_policy = _markdown_section(text, 'Identity schema and system keys')
    _require_phrases(
        'graph-key policy',
        grammar + identity_policy,
        ('one group_id', 'FE', 'BO', 'COMMON', 'never a fallback'),
    )
    if re.search(r'(?i)(?:separate|different|distinct)\s+group_id.{0,80}\bFE\b.{0,80}\bBO\b', text):
        raise AssertionError('operator guide contradicts FE/BO one-group policy')


def check_docs_operator_sections(root: Path) -> None:
    """Fail closed on the complete operator-reference contract (DOCS-01..04)."""
    readme = root / 'mcp_server' / 'README.md'
    if not readme.is_file():
        raise AssertionError('mcp_server/README.md missing')
    text = readme.read_text(encoding='utf-8')
    legacy_tools, catalog_tools, error_codes = _authoritative_doc_sets(root)

    legacy_section = _markdown_section(text, 'Legacy tool inventory (14)')
    catalog_section = _markdown_section(text, 'Catalog tool inventory (14)')
    error_section = _markdown_section(text, 'Catalog error codes')
    _assert_exact_set(
        'legacy tool inventory', _tool_inventory_names(legacy_section), legacy_tools
    )
    _assert_exact_set(
        'catalog tool inventory', _tool_inventory_names(catalog_section), catalog_tools
    )
    _assert_exact_set('CatalogErrorCode inventory', _error_code_names(error_section), error_codes)

    required_sections = (
        'Preferred large-payload path',
        'Catalog-v2 graph-key grammar and group scope',
        'Entity and edge registries',
        'Endpoint type map',
        'Hash contracts',
        'Capabilities contract',
        'Prepare, commit, and discard lifecycle',
        'Limits and overload handling',
        'Explicit evidence links',
        'Manifest semantics',
        'Read and write gates',
        'Rollout configuration',
        'Catalog safety and backend scope',
    )
    for heading in required_sections:
        _markdown_section(text, heading)
    _assert_registry_members(root, text)

    _require_phrases(
        'operator reference',
        text,
        (
            '28 total',
            'preferred large-payload path',
            'prepare_catalog_batch',
            'commit_prepared_catalog_batch',
            'compatibility',
            'catalog-v2',
            'system_key',
            'FE',
            'BO',
            'one group_id',
            'single server-owned endpoint map',
            'request_sha256',
            'catalog_sha256',
            'artifact_sha256',
            'manifest_sha256',
            'expires_at',
            'payload_b64',
            'content_sha256',
            'link_key',
            'catalog_reads_enabled',
            'catalog_writes_enabled',
            'GRAPHITI_CATALOG_UUID_NAMESPACE',
            'Neo4j 5.26+',
            'no non-Neo4j portability claim',
            'never executes canary',
            'do not query or mutate',
        ),
    )
    _assert_no_sensitive_values(text, 'operator reference')


def check_docs_migration_phrases(root: Path) -> None:
    """Fail closed on catalog-v2 offline migration guidance (DOCS-05/06)."""
    mig = root / 'mcp_server' / 'docs' / 'CATALOG_V2_MIGRATION.md'
    if not mig.is_file():
        raise AssertionError('mcp_server/docs/CATALOG_V2_MIGRATION.md missing')
    text = mig.read_text(encoding='utf-8')
    for heading in (
        'Status',
        'Identity rules',
        'Historical canary materials',
        'Offline regeneration',
        'Future live path',
        'Phase 5 ban',
        'Separate residual axis',
    ):
        _markdown_section(text, heading)
    _require_phrases(
        'migration guide',
        text,
        (
            'catalog-v1 identity keys and content hashes are **obsolete**',
            'no automatic migration',
            'catalog/canary-v2-requests-hardened/',
            'offline',
            'prepare_catalog_batch',
            'commit_prepared_catalog_batch',
            'ACCEPT_TAB',
            'must **never** be reused',
            'historical',
            'active ban on querying/mutating `oracle-catalog-v2`',
            'separate residual axis',
            'a67789a',
            'phase 5 **never**',
            'queries or mutates `oracle-catalog-v2`',
            'Neo4j 5.26+ only',
        ),
    )
    lowered = text.lower()
    if re.search(r'(?<!no )(?<!never )automatic (?:identity )?migration', lowered):
        raise AssertionError('migration guide contains a positive automatic-migration claim')
    for line in text.splitlines():
        lowered_line = line.lower()
        if 'reuse' not in lowered_line or 'accept_tab' not in lowered_line or 'sha' not in lowered_line:
            continue
        if not any(negation in lowered_line for negation in ('no ', 'not ', 'never', "mustn't")):
            raise AssertionError('migration guide contains ACCEPT_TAB SHA reuse guidance')
    _assert_no_sensitive_values(text, 'migration guide')


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


def _is_static_ban_binding(target_name: str) -> bool:
    return target_name in {
        'FORBIDDEN_GROUP',
        '_FORBIDDEN_GROUP_NAME',
        'HISTORICAL_V2_GROUP',
        'future_target_group_id_metadata',
    } or target_name.startswith('HISTORICAL_')


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


def _dict_has_group_field(node: ast.AST) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    return any(
        isinstance(key, ast.Constant) and key.value in {'group_id', 'group_ids'}
        for key in node.keys
    )


def _expr_may_resolve_forbidden(node: ast.AST, tainted_names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in tainted_names
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value == FORBIDDEN_GROUP
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        try:
            value = ast.literal_eval(node)
        except (ValueError, TypeError):
            return _expr_may_resolve_forbidden(node.left, tainted_names) or _expr_may_resolve_forbidden(
                node.right, tainted_names
            )
        return value == FORBIDDEN_GROUP
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_expr_may_resolve_forbidden(item, tainted_names) for item in node.elts)
    if isinstance(node, ast.Dict):
        return any(
            value is not None and _expr_may_resolve_forbidden(value, tainted_names)
            for value in node.values
        )
    return False


def _positional_dict_uses_forbidden_group(
    node: ast.AST,
    tainted_names: set[str],
    request_dict_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in request_dict_names
    if not isinstance(node, ast.Dict):
        return False
    for key, value in zip(node.keys, node.values, strict=True):
        if (
            isinstance(key, ast.Constant)
            and key.value in {'group_id', 'group_ids'}
            and value is not None
            and _expr_may_resolve_forbidden(value, tainted_names)
        ):
            return True
        if value is not None and _positional_dict_uses_forbidden_group(
            value, tainted_names, request_dict_names
        ):
            return True
    return False


def scan_current_source_v2_param_query(root: Path) -> dict[str, Any]:
    """AST scan for forbidden-group data flowing into active request/query fields."""
    hits: list[str] = []
    for rel in PHASE5_SAFETY_SCAN_RELS:
        path = root / rel
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        tainted_names: set[str] = set()
        request_dict_names: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            names = _assigned_names(node)
            if _expr_may_resolve_forbidden(node.value, tainted_names):
                tainted_names.update(names)
                if _dict_has_group_field(node.value):
                    request_dict_names.update(names)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                for name in _assigned_names(node):
                    if _is_static_ban_binding(name):
                        continue
                    if name in {'GROUP', 'TEST_GROUP', 'group_id'} and _expr_may_resolve_forbidden(
                        node.value, tainted_names
                    ):
                        hits.append(f'{rel}:{getattr(node, "lineno", 0)}:{name}')
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg in {
                    'group_id',
                    'group_ids',
                    'group',
                    'g',
                    'params',
                    'request',
                } and _expr_may_resolve_forbidden(keyword.value, tainted_names):
                    hits.append(f'{rel}:{getattr(node, "lineno", 0)}:{keyword.arg}')
            if any(
                _positional_dict_uses_forbidden_group(
                    argument, tainted_names, request_dict_names
                )
                for argument in node.args
            ):
                hits.append(f'{rel}:{getattr(node, "lineno", 0)}:positional_request')
    return {
        'current_oracle_catalog_v2_queried': bool(hits),
        'current_source_v2_param_query': bool(hits),
        'hits': sorted(set(hits)),
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
    'cypher_identifier_authority': check_cypher_identifier_authority,
    'endpoint_no_implicit_creation': check_endpoint_no_implicit_creation,
    'historical_artifacts_unchanged': check_historical_artifacts_unchanged,
    'hardened_artifacts_strict': check_hardened_artifacts_strict,
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
        if not (
            a.endswith('run_catalog_canary_batch.py')
            or a == 'scripts/run_catalog_canary_batch.py'
        ):
            continue
        if sid not in {'ruff', 'pyright'}:
            raise ValueError(f'{sid}: must not shell canary runner: {a}')


def validate_specs(specs: list[dict[str, Any]], root: Path | None = None) -> None:
    ids = [s['id'] for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f'duplicate spec ids: {ids}')
    for s in specs:
        validate_spec(s, root)


def _uv_tool(tool: str, files: tuple[str, ...]) -> list[str]:
    return ['uv', 'run', '--project', 'mcp_server', tool, *files]


def canonical_specs(root: Path, *, include_live: bool = True) -> list[dict[str, Any]]:
    """Exact ordered TEST-12 check inventory from 05-VALIDATION.md."""
    root = root.resolve()
    structural = {
        check_id: {
            'id': check_id,
            'argv': _runner_check_argv(check_id),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'safety' if check_id in {
                'safety_no_v2_current',
                'historical_axis_preserved',
                'historical_artifacts_unchanged',
                'canary_not_executed',
            } else 'structural',
        }
        for check_id in CANONICAL_CHECK_IDS
        if check_id not in {
            'runner_self_tests',
            'focused_pytest',
            'security_matrix',
            'legacy_contract_14',
            'catalog_registration_14',
            'tool_union_28',
            'ruff',
            'pyright',
            'live_neo4j_test11',
            'ollama_e2e',
        }
    }
    specs_by_id: dict[str, dict[str, Any]] = {
        'runner_self_tests': {
            'id': 'runner_self_tests',
            'argv': _uv_pytest(['mcp_server/tests/test_catalog_phase5_gate_runner.py']),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        'focused_pytest': {
            'id': 'focused_pytest',
            'argv': _uv_pytest(list(FOCUS_TEST_FILES)),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        'security_matrix': {
            'id': 'security_matrix',
            'argv': _uv_pytest(['mcp_server/tests/test_catalog_security_matrix.py']),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        'legacy_contract_14': {
            'id': 'legacy_contract_14',
            'argv': _uv_pytest(['mcp_server/tests/test_legacy_mcp_contract_compatibility.py']),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        'catalog_registration_14': {
            'id': 'catalog_registration_14',
            'argv': _runner_check_argv('catalog_registration_14'),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'structural',
        },
        'tool_union_28': {
            'id': 'tool_union_28',
            'argv': _uv_pytest(
                ['mcp_server/tests/test_legacy_mcp_contract_compatibility.py'],
                ['-k', 'tool_union_exact_28'],
            ),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'pytest',
        },
        'ruff': {
            'id': 'ruff',
            'argv': _uv_tool('ruff', ('check', *RUFF_FILES)),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'tool',
            'availability_optional': True,
        },
        'pyright': {
            'id': 'pyright',
            'argv': _uv_tool('pyright', ('--project', 'mcp_server/pyproject.toml', *PYRIGHT_FILES)),
            'expected_exit': 0,
            'mandatory': True,
            'kind': 'tool',
            'availability_optional': True,
        },
        'live_neo4j_test11': {
            'id': 'live_neo4j_test11',
            'argv': _uv_pytest(list(LIVE_TEST_FILES)),
            'expected_exit': 0,
            'mandatory': False,
            'kind': 'live',
            'availability_optional': True,
            'enabled': include_live,
        },
        'ollama_e2e': {
            'id': 'ollama_e2e',
            'argv': _uv_pytest(['mcp_server/tests/test_catalog_ollama_e2e.py']),
            'expected_exit': 0,
            'mandatory': False,
            'kind': 'live',
            'availability_optional': True,
            'enabled': include_live,
        },
        **structural,
    }
    specs = [specs_by_id[check_id] for check_id in CANONICAL_CHECK_IDS]
    validate_specs(specs, root)
    return specs


def canonical_specs_json(specs: list[dict[str, Any]]) -> str:
    slim = [
        {
            'id': s['id'],
            'argv': s['argv'],
            'expected_exit': s['expected_exit'],
            'mandatory': bool(s.get('mandatory', True)),
            'kind': s.get('kind', 'tool'),
            'availability_optional': bool(s.get('availability_optional', False)),
            'enabled': bool(s.get('enabled', True)),
        }
        for s in specs
    ]
    return json.dumps(slim, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def content_digest_map(
    root: Path, rels: tuple[Path, ...] = GATE_INPUT_RELS
) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in rels:
        path = root / rel
        key = rel.as_posix()
        out[key] = sha256_file_lf(path) if path.is_file() else 'missing'
    return out


def content_digest(content_map: dict[str, str]) -> str:
    return sha256_text(json.dumps(content_map, sort_keys=True, separators=(',', ':')))


def execution_input_digest_map(root: Path) -> dict[str, str]:
    paths = {
        *(root / rel for rel in EXECUTION_INPUT_FILE_RELS),
        *(
            path
            for rel in EXECUTION_INPUT_DIR_RELS
            for path in (root / rel).rglob('*.py')
            if path.is_file()
        ),
    }
    return {
        path.resolve().relative_to(root.resolve()).as_posix(): sha256_file_lf(path)
        for path in sorted(paths)
    }


def reviewed_worktree_digest_map(root: Path) -> dict[str, str]:
    """Bind every tracked modification plus non-ignored untracked file except proof outputs."""
    result = subprocess.run(
        ['git', 'status', '--porcelain=v1', '--untracked-files=all'],
        cwd=str(root),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError('git status failed')
    excluded = {
        DEFAULT_LEDGER_REL.as_posix(),
        DEFAULT_REPORT_JSON_REL.as_posix(),
        DEFAULT_REPORT_MD_REL.as_posix(),
        DEFAULT_PACKAGE_MARKER_REL.as_posix(),
        *(path.as_posix() for path in AUDIT_RELS),
        *(path.as_posix() for path in POST_PROOF_TRACKING_RELS),
    }
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        raw_path = line[3:]
        if ' -> ' in raw_path:
            raw_path = raw_path.split(' -> ', 1)[1]
        rel = Path(raw_path.strip('"').replace('\\', '/'))
        key = rel.as_posix()
        if key in excluded:
            continue
        path = (root / rel).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError('reviewed working-tree path escapes root') from exc
        out[key] = sha256_file_raw(path) if path.is_file() else 'deleted'
    return dict(sorted(out.items()))


def reviewed_worktree_digest(root: Path) -> str:
    return content_digest(reviewed_worktree_digest_map(root))


def parse_pytest_counts(output: str) -> dict[str, int]:
    counts = {
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'deselected': 0,
        'errors': 0,
    }
    for key in counts:
        matches = re.findall(rf'(\d+)\s+{re.escape(key)}', output)
        if matches:
            counts[key] = int(matches[-1])
    return counts


def _git_stdout(root: Path, argv: list[str], error: str) -> str:
    result = subprocess.run(
        ['git', *argv],
        cwd=str(root),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f'{error}: {result.stderr}')
    return result.stdout.strip()


def git_head(root: Path) -> str:
    return _git_stdout(root, ['rev-parse', 'HEAD'], 'git rev-parse HEAD failed')


def _verify_proof_head(root: Path, proof_head: object) -> None:
    if not isinstance(proof_head, str) or re.fullmatch(r'[0-9a-f]{40}', proof_head) is None:
        raise ValueError('final HEAD binding mismatch')
    current_head = git_head(root)
    if current_head == proof_head:
        return
    ancestor = subprocess.run(
        ['git', 'merge-base', '--is-ancestor', proof_head, current_head],
        cwd=str(root),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if ancestor.returncode != 0:
        raise ValueError('final HEAD binding mismatch')
    changed = {
        line
        for line in _git_stdout(
            root,
            ['log', '--format=', '--name-only', '--no-renames', f'{proof_head}..{current_head}'],
            'git log proof closure failed',
        ).splitlines()
        if line
    }
    if not changed or not changed <= PROOF_CLOSURE_RELS:
        raise ValueError('final closure commit contains non-proof paths')


def run_argv(
    argv: list[str],
    root: Path,
    timeout: int = 1800,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = subprocess.run(
        argv,
        shell=False,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    combined = f'{result.stdout or ""}\n{result.stderr or ""}'
    counts = parse_pytest_counts(combined) if 'pytest' in argv else {}
    lowered = combined.lower()
    skip_reasons = (
        sorted(
            set(
                re.findall(
                    r'(?im)^SKIPPED\s+[^\r\n]+?[:\-]\s*(.+?)\s*$',
                    combined,
                )
            )
        )
        if 'pytest' in argv
        else []
    )
    unavailable_markers = (
        'no such file or directory',
        'command not found',
        'failed to spawn',
        'no module named ruff',
        'no module named pyright',
    )
    return {
        'exit_code': result.returncode,
        'stdout_sha256': sha256_text(result.stdout or ''),
        'stderr_sha256': sha256_text(result.stderr or ''),
        'counts': counts,
        'skip_reasons': skip_reasons,
        'tool_unavailable': any(marker in lowered for marker in unavailable_markers),
    }


def _safe_failure_summary(exc: BaseException) -> str:
    return type(exc).__name__


def _availability_reason(check_id: str, outcome: dict[str, Any]) -> str | None:
    counts = outcome.get('counts') or {}
    if check_id in {'ruff', 'pyright'} and outcome.get('tool_unavailable') is True:
        return f'{check_id} executable unavailable in the configured uv environment'
    if check_id not in {'live_neo4j_test11', 'ollama_e2e'}:
        return None
    if (
        int(counts.get('skipped', 0)) < 1
        or int(counts.get('failed', 0)) != 0
        or int(counts.get('errors', 0)) != 0
    ):
        return None
    reasons = outcome.get('skip_reasons')
    if not isinstance(reasons, list) or not reasons:
        return None
    allowed_markers = (
        'neo4j driver unavailable',
        'neo4j unavailable',
        'ollama cli is not installed',
        'ollama daemon unavailable',
        'ollama model unavailable',
        'ollama native /api/embed unavailable',
        'ollama embedding dimension mismatch',
    )
    if any(
        not isinstance(reason, str)
        or not any(marker in reason.lower() for marker in allowed_markers)
        for reason in reasons
    ):
        return None
    return f'{check_id} infrastructure unavailable: {"; ".join(reasons)}'


def classify_check_outcome(
    spec: dict[str, Any], outcome: dict[str, Any]
) -> tuple[str, str | None]:
    if not bool(spec.get('enabled', True)):
        if not bool(spec.get('availability_optional', False)):
            return 'fail', None
        return 'availability-skip', f'{spec["id"]} disabled by explicit runner option'
    exit_code = int(outcome.get('exit_code', -1))
    reason = _availability_reason(str(spec['id']), outcome)
    if reason:
        return 'availability-skip', reason
    if exit_code != int(spec.get('expected_exit', 0)):
        return 'fail', None
    counts = outcome.get('counts') or {}
    if spec.get('kind') == 'pytest' and (
        int(counts.get('failed', 0)) > 0 or int(counts.get('errors', 0)) > 0
    ):
        return 'fail', None
    if spec.get('kind') in {'pytest', 'live'} and int(counts.get('skipped', 0)) > 0:
        return 'fail', None
    return 'pass', None


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
        'stdout_sha256': sha256_text(result.stdout or ''),
        'stderr_sha256': sha256_text(result.stderr or ''),
        'excluded_from_aggregation': True,
    }


def validate_result_partition(
    results: list[dict[str, Any]],
    *,
    require_all_ids: bool = True,
) -> bool:
    ids = [str(row.get('id') or '') for row in results]
    if not ids or len(ids) != len(set(ids)):
        return False
    if require_all_ids and tuple(ids) != CANONICAL_CHECK_IDS:
        return False
    for row in results:
        status = row.get('status')
        if status not in {'pass', 'fail', 'availability-skip'}:
            return False
        reason = row.get('availability_reason')
        if status == 'availability-skip':
            if row.get('id') not in OPTIONAL_AVAILABILITY_CHECK_IDS:
                return False
            if not isinstance(reason, str) or not reason.strip():
                return False
        elif reason not in (None, ''):
            return False
        if status == 'pass' and row.get('exit_code') != row.get('expected_exit', 0):
            return False
    return True


def derive_local_gate_pass(
    results: list[dict[str, Any]],
    sentinel: dict[str, Any],
    *,
    require_all_ids: bool = False,
) -> bool:
    if not sentinel.get('pass') or not validate_result_partition(
        results, require_all_ids=require_all_ids
    ):
        return False
    for row in results:
        status = row.get('status')
        if status == 'fail':
            return False
        if status == 'availability-skip':
            continue
        if status != 'pass':
            return False
    return True


def derive_safety_ledger(
    results: list[dict[str, Any]],
    root: Path | None = None,
) -> dict[str, Any]:
    """Two-axis safety: permanent historical audit + current execution/source safety."""
    safety_ids = {
        'safety_no_v2_current',
        'historical_axis_preserved',
        'historical_artifacts_unchanged',
        'canary_not_executed',
    }
    by_id = {r.get('id'): r for r in results}
    current_safety_ok = all(by_id.get(sid, {}).get('status') == 'pass' for sid in safety_ids)
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
    requirements_complete: bool = False,
    edge_probes_complete: bool = False,
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
    if phase_5_complete and (not requirements_complete or not edge_probes_complete):
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
    return safety.get('safety_checks_pass') is True


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


def _canonical_sha256(payload: dict[str, Any], omitted_key: str) -> str:
    return sha256_text(
        json.dumps(
            {key: value for key, value in payload.items() if key != omitted_key},
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True,
        )
    )


def _result_row(spec: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    status, reason = classify_check_outcome(spec, outcome)
    row = {
        'id': spec['id'],
        'argv': list(spec['argv']),
        'expected_exit': spec['expected_exit'],
        'exit_code': int(outcome.get('exit_code', -1)),
        'status': status,
        'availability_reason': reason,
        'mandatory': bool(spec.get('mandatory', True)),
        'kind': spec.get('kind'),
        'counts': dict(outcome.get('counts') or {}),
        'stdout_sha256': str(outcome.get('stdout_sha256') or sha256_text('')),
        'stderr_sha256': str(outcome.get('stderr_sha256') or sha256_text('')),
    }
    if status == 'availability-skip':
        row['skip_reasons'] = list(outcome.get('skip_reasons') or [])
    return row


def _failure_row(spec: dict[str, Any], exc: BaseException) -> dict[str, Any]:
    return {
        'id': spec['id'],
        'argv': list(spec['argv']),
        'expected_exit': spec['expected_exit'],
        'exit_code': -1,
        'status': 'fail',
        'availability_reason': None,
        'mandatory': bool(spec.get('mandatory', True)),
        'kind': spec.get('kind'),
        'counts': {},
        'stdout_sha256': sha256_text(''),
        'stderr_sha256': sha256_text(_safe_failure_summary(exc)),
        'failure_class': _safe_failure_summary(exc),
    }


def _spec_pass(results: list[dict[str, Any]], spec_id: str) -> bool:
    row = next((item for item in results if item.get('id') == spec_id), None)
    return bool(row and row.get('status') == 'pass')


def _pending_audits() -> dict[str, dict[str, Any]]:
    return {
        name: {
            'path': AUDIT_PATH_BY_NAME[name].as_posix(),
            'status': 'pending',
            'sha256': None,
        }
        for name in AUDIT_NAMES
    }


def _test_totals(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        key: sum(int((row.get('counts') or {}).get(key, 0)) for row in results)
        for key in ('passed', 'failed', 'skipped', 'deselected', 'errors')
    }


def _build_report_model(ledger: dict[str, Any]) -> dict[str, Any]:
    complete = bool(ledger.get('phase_5_complete'))
    report: dict[str, Any] = {
        'schema_version': 'phase5-implementation-report.v1',
        'implementation_status': 'complete' if complete else 'partial',
        'completed_phases': ['phase_0', 'phase_1', 'phase_2', 'phase_3a', 'phase_3b', 'phase_4']
        + (['phase_5'] if complete else []),
        'requirements': {
            'total_expected': 138,
            'mapped': 138,
            'implemented': 138 if complete else 121,
            'verified': 138 if complete else 121,
            'phase_5_expected': EXPECTED_REQUIREMENT_COUNT,
            'phase_5_ids': list(ledger.get('requirement_ids') or REQUIREMENT_IDS),
            'phase_5_verified': EXPECTED_REQUIREMENT_COUNT if complete else 0,
        },
        'baseline': {
            'legacy_tools': 14,
            'pre_phase_5_catalog_tools': 14,
            'tool_union': 28,
            'historical_audit_commit': HISTORICAL_V2_COMMIT,
        },
        'changed_files_and_modules': [
            'mcp_server/src/services/catalog_service.py',
            'mcp_server/src/services/catalog_store.py',
            'mcp_server/src/graphiti_mcp_server.py',
            'scripts/build_catalog_canary_requests.py',
            'scripts/run_catalog_canary_batch.py',
            'mcp_server/tests/catalog_phase5_gate_runner.py',
            'mcp_server/tests/test_catalog_canary_scripts.py',
            'mcp_server/tests/test_catalog_security_matrix.py',
            'mcp_server/tests/test_legacy_mcp_contract_compatibility.py',
            'mcp_server/README.md',
            'mcp_server/docs/CATALOG_V2_MIGRATION.md',
        ],
        'contract_and_schema_changes': [
            'catalog-v2 system-scoped graph keys and UUIDv5 identity',
            '14 legacy plus 14 catalog MCP tools with exact disjoint union 28',
            'prepare/token-only-commit lifecycle and explicit evidence links',
            'durable manifest-backed verification contracts',
        ],
        'database_migration_changes': [
            'Neo4j 5.26+ catalog-v2 constraints, labels, and control records',
            'no automatic catalog-v1 identity migration or graph rewrite',
            'offline hardened canary artifacts replace historical hashes as authority',
        ],
        'edge_probes': {
            'expected': EXPECTED_PROBE_COUNT,
            'dispositions': dict(ledger.get('edge_probe_dispositions') or {}),
        },
        'tests': _test_totals(list(ledger.get('results') or [])),
        'commands': [
            {
                'check_id': row['id'],
                'argv': row['argv'],
                'status': row['status'],
                'availability_reason': row.get('availability_reason'),
                'evidence_source': (ledger.get('result_sources') or {}).get(row['id'], 'initial'),
            }
            for row in ledger.get('results') or []
        ],
        'spec_sha256': ledger.get('spec_sha256'),
        'initial_evidence': {
            key: (ledger.get('initial_evidence') or {}).get(key)
            for key in ('evaluated_head', 'ledger_sha256', 'spec_sha256', 'content_digest')
        },
        'closure_evidence': {
            key: (ledger.get('closure_evidence') or {}).get(key)
            for key in (
                'evaluated_head',
                'spec_sha256',
                'input_digest',
                'execution_input_digest',
                'reviewed_worktree_digest',
            )
        },
        'compatibility': {
            'legacy_tools': 14,
            'catalog_tools': 14,
            'tool_union': 28,
            'compatibility_breaks': [],
        },
        'compatibility_breaks': [],
        'compatibility_decisions': [
            'preserve all 14 legacy MCP tool names and public contracts',
            'catalog-v2 contract changes are explicit and separately versioned',
            'Neo4j-only deterministic catalog support; no portability claim',
        ],
        'security_and_operational_limits': [
            'catalog writes require fixed server allowlists and Neo4j 5.26+',
            'all reads and writes are constrained by group_id',
            'commit performs no embedding, LLM, queue, HTTP, or payload replacement',
            'default batch ceilings: 500 entities, 2000 edges, 5000 provenance links',
            'Phase 5 never executes canary, clear_graph, deployment, or deletion',
        ],
        'migrations_added': [
            'offline catalog-v2 hardened artifact regeneration',
            'prepare/token-only-commit future canary path',
        ],
        'known_limitations': [
            'Neo4j 5.26+ catalog writes only; no non-Neo4j portability claim',
            'no automatic catalog-v1 to catalog-v2 migration',
            'Phase 6 canary remains separate and unexecuted',
        ],
        'blockers': [] if complete else ['post-execution audits pending'],
        'risks': [
            'changing GRAPHITI_CATALOG_UUID_NAMESPACE changes every deterministic identity',
            'historical catalog-v1 ACCEPT_TAB hashes remain audit-only and invalid for catalog-v2',
        ],
        'migration_status': 'offline_hardened_artifacts_only',
        'two_axis_safety': {
            'historical': dict(ledger.get('historical_audit') or {}),
            'current_oracle_catalog_v2_queried': ledger.get(
                'current_oracle_catalog_v2_queried'
            ),
            'current_oracle_catalog_v2_mutated': False,
        },
        'audits': dict(ledger.get('audits') or {}),
        'evaluated_head': ledger.get('evaluated_head'),
        'content_digest': ledger.get('content_digest'),
        'reviewed_worktree_digest': ledger.get('reviewed_worktree_digest'),
        'authoritative_ledger_sha256': ledger.get('ledger_sha256'),
        'proof_package_marker': DEFAULT_PACKAGE_MARKER_REL.as_posix(),
        'ready_to_regenerate_canary': bool(ledger.get('ready_to_regenerate_canary')),
        'ready_to_regenerate_canary_payload': bool(ledger.get('ready_to_regenerate_canary')),
        'phase_5_complete': complete,
        'post_execution_audits_pending': bool(ledger.get('post_execution_audits_pending')),
        'canary_executed': False,
        'clear_graph_called': False,
    }
    report['report_sha256'] = _canonical_sha256(report, 'report_sha256')
    return report


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        '# Phase 5 Final Readiness Report',
        '',
        f"- Implementation status: `{report['implementation_status']}`",
        f"- Evaluated HEAD: `{report['evaluated_head']}`",
        f"- Ready to regenerate canary: `{str(report['ready_to_regenerate_canary']).lower()}`",
        f"- Phase 5 complete: `{str(report['phase_5_complete']).lower()}`",
        '- Canary executed: `false`',
        '',
        '## Test Classifications',
        '',
        '| Check | Status | Availability reason |',
        '|---|---|---|',
    ]
    for command in report['commands']:
        reason = command.get('availability_reason') or ''
        lines.append(
            f"| `{command['check_id']}` | {command['status']} "
            f"({command.get('evidence_source', 'initial')}) | {reason} |"
        )
    lines.extend(
        [
            '',
            '## Safety',
            '',
            '- Current `oracle-catalog-v2` queried: `false`',
            '- Current `oracle-catalog-v2` mutated: `false`',
            '- Historical audit pointer: `a67789a`',
            '- `clear_graph` called: `false`',
            '',
            '## Known Limitations',
            '',
        ]
    )
    lines.extend(f'- {item}' for item in report['known_limitations'])
    lines.extend(['', '## Blockers', ''])
    lines.extend(f'- {item}' for item in report['blockers'])
    if not report['blockers']:
        lines.append('- None')
    return '\n'.join(lines) + '\n'


def _stage_file(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(name)
        raise
    return Path(name)


def _package_payloads(
    ledger: dict[str, Any], report: dict[str, Any], markdown: str
) -> tuple[bytes, bytes, bytes]:
    return (
        (json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode(),
        (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode(),
        markdown.encode('utf-8'),
    )


def _package_marker_path(ledger_path: Path) -> Path:
    return ledger_path.with_name(DEFAULT_PACKAGE_MARKER_REL.name)


def _package_marker_payload(
    ledger_path: Path,
    report_json_path: Path,
    report_md_path: Path,
    payloads: tuple[bytes, bytes, bytes],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    paths = (ledger_path, report_json_path, report_md_path)
    marker: dict[str, Any] = {
        'schema_version': PROOF_PACKAGE_SCHEMA_VERSION,
        'package_stage': ledger.get('package_stage'),
        'ledger_sha256': ledger.get('ledger_sha256'),
        'files': {
            path.name: {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
            for path, data in zip(paths, payloads, strict=True)
        },
    }
    marker['marker_sha256'] = _canonical_sha256(marker, 'marker_sha256')
    return marker


def _validate_package_marker(
    marker_path: Path,
    ledger_path: Path,
    report_json_path: Path,
    report_md_path: Path,
    ledger: dict[str, Any],
) -> None:
    marker = _load_json_object(marker_path)
    if (
        marker.get('schema_version') != PROOF_PACKAGE_SCHEMA_VERSION
        or marker.get('package_stage') != ledger.get('package_stage')
        or marker.get('ledger_sha256') != ledger.get('ledger_sha256')
        or marker.get('marker_sha256') != _canonical_sha256(marker, 'marker_sha256')
    ):
        raise ValueError('proof package marker binding mismatch')
    files = marker.get('files')
    targets = (ledger_path, report_json_path, report_md_path)
    if not isinstance(files, dict) or set(files) != {path.name for path in targets}:
        raise ValueError('proof package marker inventory mismatch')
    for path in targets:
        row = files.get(path.name)
        if (
            not isinstance(row, dict)
            or set(row) != {'sha256', 'size'}
            or type(row.get('size')) is not int
            or row['size'] < 0
            or row.get('sha256') != sha256_file_raw(path)
            or row['size'] != path.stat().st_size
        ):
            raise ValueError('proof package marker file mismatch')


def _fsync_parent(path: Path) -> None:
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _restore_package(backups: dict[Path, bytes | None]) -> None:
    data_targets = tuple(backups)[:-1]
    marker_path = tuple(backups)[-1]
    with contextlib.suppress(OSError):
        marker_path.unlink()
    for target in reversed(data_targets):
        prior = backups[target]
        if prior is None:
            with contextlib.suppress(OSError):
                target.unlink()
        else:
            restore = _stage_file(target, prior)
            os.replace(restore, target)
    marker_prior = backups[marker_path]
    if marker_prior is not None:
        restore = _stage_file(marker_path, marker_prior)
        os.replace(restore, marker_path)
    _fsync_parent(marker_path)


def atomic_write_package(
    ledger_path: Path,
    ledger: dict[str, Any],
    report_json_path: Path,
    report: dict[str, Any],
    report_md_path: Path,
    markdown: str,
) -> None:
    data_targets = (ledger_path, report_json_path, report_md_path)
    payloads = _package_payloads(ledger, report, markdown)
    marker_path = _package_marker_path(ledger_path)
    marker = _package_marker_payload(
        ledger_path, report_json_path, report_md_path, payloads, ledger
    )
    marker_payload = (
        json.dumps(marker, indent=2, sort_keys=True, ensure_ascii=True) + '\n'
    ).encode()
    targets = (*data_targets, marker_path)
    all_payloads = (*payloads, marker_payload)
    staged: list[Path] = []
    backups = {path: path.read_bytes() if path.exists() else None for path in targets}
    replaced: list[Path] = []
    try:
        staged = [
            _stage_file(path, data) for path, data in zip(targets, all_payloads, strict=True)
        ]
        # Marker is the commit point: publish it only after every data file is durable.
        for tmp_path, target in zip(staged, targets, strict=True):
            os.replace(tmp_path, target)
            replaced.append(target)
        _fsync_parent(marker_path)
        if tuple(path.read_bytes() for path in targets) != all_payloads:
            raise ValueError('package reread mismatch')
    except BaseException:
        if replaced:
            _restore_package(backups)
        raise
    finally:
        for tmp_path in staged:
            with contextlib.suppress(OSError):
                tmp_path.unlink()


def validate_initial_package(ledger: dict[str, Any], report: dict[str, Any]) -> None:
    if ledger.get('phase_5_complete') is not False:
        raise ValueError('initial phase_5_complete must be false')
    if ledger.get('ready_to_regenerate_canary') is not False:
        raise ValueError('initial readiness must be false')
    if ledger.get('post_execution_audits_pending') is not True:
        raise ValueError('initial audits must remain pending')
    if ledger.get('canary_executed') is not False:
        raise ValueError('canary_executed must be false')
    if tuple(row.get('id') for row in ledger.get('results') or []) != CANONICAL_CHECK_IDS:
        raise ValueError('initial result inventory mismatch')
    if not validate_result_partition(list(ledger.get('results') or [])):
        raise ValueError('initial result classification invalid')
    audits = ledger.get('audits') or {}
    if set(audits) != set(AUDIT_NAMES) or any(
        row.get('status') != 'pending' for row in audits.values()
    ):
        raise ValueError('initial audit slots mismatch')
    if report.get('phase_5_complete') is not False or report.get(
        'ready_to_regenerate_canary'
    ) is not False:
        raise ValueError('initial report cannot claim closure')
    if report != _build_report_model(ledger) or not _report_integrity_ok(report):
        raise ValueError('initial report model mismatch')
    expected_tests = _test_totals(list(ledger.get('results') or []))
    if report.get('tests') != expected_tests:
        raise ValueError('initial report test totals mismatch')


def _normalize_injected_result(row: dict[str, Any]) -> None:
    status = row.get('status')
    if status == 'pass':
        row['exit_code'] = row.get('expected_exit', 0)
        row['availability_reason'] = None
    elif status == 'availability-skip' and not row.get('availability_reason'):
        row['availability_reason'] = f'{row.get("id")} infrastructure unavailable'
    elif status == 'fail':
        row['availability_reason'] = None


def run_gate(
    root: Path,
    ledger_path: Path,
    *,
    injected_overrides: dict[str, Any] | None = None,
    include_live: bool = True,
    report_json_path: Path | None = None,
    report_md_path: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    specs = canonical_specs(root, include_live=include_live)
    specs_json = canonical_specs_json(specs)
    head = git_head(root)
    content_map = content_digest_map(root, INITIAL_GATE_INPUT_RELS)
    execution_map = execution_input_digest_map(root)
    worktree_map = reviewed_worktree_digest_map(root)
    results: list[dict[str, Any]] = []
    child_env = dict(os.environ)
    child_env['CATALOG_PHASE5_GATE_SKIP_SELF'] = '1'
    child_env['CATALOG_CEILING_SMOKE'] = '1'
    child_env.pop('CATALOG_INT_REQUIRED', None)
    child_env.pop('CATALOG_OLLAMA_REQUIRED', None)
    for spec in specs:
        try:
            outcome = run_argv(spec['argv'], root, env=child_env)
            results.append(_result_row(spec, outcome))
        except Exception as exc:
            results.append(_failure_row(spec, exc))

    if injected_overrides:
        for row in results:
            override = injected_overrides.get(str(row['id']))
            if override:
                row.update(override)
                _normalize_injected_result(row)

    sentinel = run_sentinel(root)
    end_content_map = content_digest_map(root, INITIAL_GATE_INPUT_RELS)
    end_execution_map = execution_input_digest_map(root)
    end_worktree_map = reviewed_worktree_digest_map(root)
    if (
        git_head(root) != head
        or end_content_map != content_map
        or end_execution_map != execution_map
        or end_worktree_map != worktree_map
    ):
        raise ValueError('initial gate input drift detected')
    local_gate_pass = derive_local_gate_pass(results, sentinel, require_all_ids=True)
    safety = derive_safety_ledger(results, root)
    audits = _pending_audits()
    ledger: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'package_stage': 'initial',
        'evaluated_head': head,
        'proof_head': head,
        'canonical_specs': json.loads(specs_json),
        'spec_sha256': sha256_text(specs_json),
        'content_sha256_map': content_map,
        'content_digest': content_digest(content_map),
        'execution_input_sha256_map': execution_map,
        'execution_input_digest': content_digest(execution_map),
        'reviewed_worktree_sha256_map': worktree_map,
        'reviewed_worktree_digest': content_digest(worktree_map),
        'requirement_ids': list(REQUIREMENT_IDS),
        'requirement_dispositions': {requirement: 'pending-audits' for requirement in REQUIREMENT_IDS},
        'raw_edge_probe_count': EXPECTED_PROBE_COUNT,
        'expected_requirement_count': EXPECTED_REQUIREMENT_COUNT,
        'edge_probe_dispositions': {probe: 'pending-audits' for probe in EDGE_PROBE_IDS},
        'sentinel': sentinel,
        'results': results,
        'local_gate_pass': local_gate_pass,
        'nyquist_compliant': False,
        'ready_to_regenerate_canary': False,
        'phase_5_complete': False,
        'post_execution_audits_pending': True,
        'audits_pass': False,
        'audits': audits,
        'unit_service_pass': _spec_pass(results, 'focused_pytest'),
        'registration_pass': _spec_pass(results, 'catalog_registration_14'),
        'security_matrix_pass': _spec_pass(results, 'security_matrix'),
        'legacy_contract_pass': _spec_pass(results, 'legacy_contract_14'),
        'offline_canary_pass': _spec_pass(results, 'offline_canary_pure'),
        'docs_pass': _spec_pass(results, 'docs_operator_sections')
        and _spec_pass(results, 'docs_migration_phrases'),
        'canary_executed': False,
        'oracle_catalog_v2_queried': safety['oracle_catalog_v2_queried'],
        'current_oracle_catalog_v2_queried': safety['current_oracle_catalog_v2_queried'],
        'current_oracle_catalog_v2_mutated': False,
        'clear_graph_called': False,
        'api_coverage_detector': False,
        'safety': safety,
        'historical_audit': {
            'historical_oracle_catalog_v2_queried': HISTORICAL_ORACLE_CATALOG_V2_QUERIED,
            'commit': HISTORICAL_V2_COMMIT,
            'class': HISTORICAL_V2_CLASS,
            'scope': HISTORICAL_V2_SCOPE,
            'checkpoint_sha256': HISTORICAL_CHECKPOINT_SHA256,
            'checkpoint_attempt_count': HISTORICAL_CHECKPOINT_ATTEMPT_COUNT,
            'note': HISTORICAL_V2_VIOLATION_NOTE,
        },
        'notes': {
            'test_group': ALLOWED_TEST_GROUP,
            'forbidden_group': FORBIDDEN_GROUP,
            'resolution_policy': '37 exact probes; initial dispositions remain pending-audits',
            'no_canary': 'Phase 5 never executes canary; canary_executed always false',
            'no_v2': 'never query or mutate oracle-catalog-v2',
        },
    }
    ledger['ledger_sha256'] = _canonical_sha256(ledger, 'ledger_sha256')
    report = _build_report_model(ledger)
    validate_initial_package(ledger, report)
    if report_json_path is None and report_md_path is None:
        if ledger_path.resolve() == (root / DEFAULT_LEDGER_REL).resolve():
            report_json_path = root / DEFAULT_REPORT_JSON_REL
            report_md_path = root / DEFAULT_REPORT_MD_REL
        else:
            report_json_path = ledger_path.with_name('05-IMPLEMENTATION-REPORT.json')
            report_md_path = ledger_path.with_name('05-IMPLEMENTATION-REPORT.md')
    elif report_json_path is None or report_md_path is None:
        raise ValueError('report paths must be provided together')
    atomic_write_package(
        ledger_path,
        ledger,
        report_json_path,
        report,
        report_md_path,
        render_report_markdown(report),
    )
    _validate_package_marker(
        _package_marker_path(ledger_path),
        ledger_path,
        report_json_path,
        report_md_path,
        ledger,
    )
    return ledger


def parse_frontmatter(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f'audit missing: {path.name}')
    text = path.read_text(encoding='utf-8')
    match = re.match(r'\A---\s*\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)', text, re.DOTALL)
    if match is None:
        raise ValueError(f'audit frontmatter missing or unterminated: {path.name}')
    try:
        import yaml

        class UniqueKeyLoader(yaml.SafeLoader):
            pass

        def construct_mapping(
            loader: UniqueKeyLoader,
            node: Any,
            deep: bool = False,
        ) -> dict[Any, Any]:
            if any(getattr(key_node, 'tag', '') == 'tag:yaml.org,2002:merge' for key_node, _ in node.value):
                raise yaml.constructor.ConstructorError(
                    'while constructing a mapping',
                    node.start_mark,
                    'YAML merge keys are not allowed',
                    node.start_mark,
                )
            loader.flatten_mapping(node)
            result: dict[Any, Any] = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in result
                except TypeError as exc:
                    raise yaml.constructor.ConstructorError(
                        'while constructing a mapping',
                        node.start_mark,
                        'found unhashable key',
                        key_node.start_mark,
                    ) from exc
                if duplicate:
                    raise yaml.constructor.ConstructorError(
                        'while constructing a mapping',
                        node.start_mark,
                        f'found duplicate key ({key!r})',
                        key_node.start_mark,
                    )
                result[key] = loader.construct_object(value_node, deep=deep)
            return result

        UniqueKeyLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            construct_mapping,
        )
        data = yaml.load(match.group('body'), Loader=UniqueKeyLoader)
    except Exception as exc:
        raise ValueError(f'audit frontmatter malformed: {path.name}') from exc
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise ValueError(f'audit frontmatter must be a string-keyed mapping: {path.name}')
    return data


def _require_keys(data: dict[str, Any], required: frozenset[str], label: str) -> None:
    if not required <= set(data):
        raise ValueError(f'{label} audit schema mismatch')


def _require_exact_keys(data: dict[str, Any], expected: frozenset[str], label: str) -> None:
    if set(data) != expected:
        raise ValueError(f'{label} audit schema mismatch')


AUDIT_COMMON_KEYS = AUDIT_BINDING_KEYS
AUDIT_FRONTMATTER_KEYS = {
    'review': AUDIT_COMMON_KEYS | frozenset({'status', 'findings', 'review_scope'}),
    'validation': AUDIT_COMMON_KEYS
    | frozenset(
        {'phase', 'slug', 'status', 'nyquist_compliant', 'wave_0_complete', 'created'}
    ),
    'security': AUDIT_COMMON_KEYS | frozenset({'status', 'threats_open', 'accepted_risks'}),
    'verification': AUDIT_COMMON_KEYS
    | frozenset({'status', 'score', 'behavior_unverified', 'requirements_verified', 'gaps'}),
}


HEX_SHA256 = re.compile(r'[0-9a-f]{64}')
RESULT_COUNT_KEYS = frozenset({'passed', 'failed', 'skipped', 'deselected', 'errors'})


def _validate_result_evidence(row: dict[str, Any]) -> None:
    for digest_key in ('stdout_sha256', 'stderr_sha256'):
        digest = row.get(digest_key)
        if not isinstance(digest, str) or HEX_SHA256.fullmatch(digest) is None:
            raise ValueError('result evidence digest mismatch')
    counts = row.get('counts')
    if not isinstance(counts, dict) or set(counts) - RESULT_COUNT_KEYS:
        raise ValueError('result evidence counts mismatch')
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError('result evidence counts mismatch')
    failed = int(counts.get('failed', 0))
    errors = int(counts.get('errors', 0))
    skipped = int(counts.get('skipped', 0))
    if row.get('status') == 'pass' and (failed or errors or skipped):
        raise ValueError('passing result contains non-pass pytest counts')
    if row.get('status') == 'availability-skip':
        if row.get('id') not in OPTIONAL_AVAILABILITY_CHECK_IDS:
            raise ValueError('availability result check id mismatch')
        if row.get('kind') == 'tool':
            if counts or row.get('skip_reasons') not in (None, []):
                raise ValueError('availability result counts mismatch')
        else:
            reasons = row.get('skip_reasons')
            if failed or errors or skipped < 1 or not isinstance(reasons, list) or not reasons:
                raise ValueError('availability result counts mismatch')


def _validate_sentinel(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError('sentinel evidence missing')
    expected_keys = {
        'argv',
        'argv_third',
        'exit_code',
        'pass',
        'stdout_sha256',
        'stderr_sha256',
        'excluded_from_aggregation',
    }
    if set(value) != expected_keys:
        raise ValueError('sentinel evidence schema mismatch')
    if (
        value.get('argv') != ['<sys.executable>', '-c', 'assert False']
        or value.get('argv_third') != 'assert False'
        or type(value.get('exit_code')) is not int
        or value.get('exit_code') == 0
        or value.get('pass') is not True
        or value.get('excluded_from_aggregation') is not True
    ):
        raise ValueError('sentinel evidence mismatch')
    for key in ('stdout_sha256', 'stderr_sha256'):
        digest = value.get(key)
        if not isinstance(digest, str) or HEX_SHA256.fullmatch(digest) is None:
            raise ValueError('sentinel evidence digest mismatch')


def _review_is_clean(data: dict[str, Any]) -> bool:
    findings = data.get('findings')
    required = frozenset({'critical', 'warning'})
    allowed = required | {'info', 'total'}
    if not isinstance(findings, dict) or not required <= set(findings) or set(findings) - allowed:
        raise ValueError('review audit findings schema mismatch')
    if any(type(value) is not int or value < 0 for value in findings.values()):
        raise ValueError('review audit findings counts mismatch')
    if 'total' in findings and findings['total'] != sum(
        findings.get(key, 0) for key in ('critical', 'warning', 'info')
    ):
        raise ValueError('review audit findings total mismatch')
    return bool(
        data.get('status') == 'clean'
        and findings['critical'] == 0
        and findings['warning'] == 0
    )


def _validation_is_green(data: dict[str, Any], text: str) -> bool:
    return bool(
        data.get('status') == 'validated'
        and data.get('nyquist_compliant') is True
        and re.search(r'37\s*/\s*37', text)
        and not re.search(r'(?i)unresolved(?:\s+after\s+audit)?\s*[:|]\s*[1-9]\d*', text)
    )


def _security_is_green(data: dict[str, Any], text: str) -> bool:
    threats_open = data.get('threats_open')
    if type(threats_open) is not int or threats_open < 0:
        raise ValueError('security audit threats_open type mismatch')
    accepted_risks = data.get('accepted_risks')
    if not isinstance(accepted_risks, list) or accepted_risks:
        raise ValueError('security audit accepted_risks mismatch')
    accepted_risk_section = re.search(
        r'(?ims)^#{2,6}\s+Accepted Risks?(?:\s+Log)?\s*$\n(?P<body>.*?)(?=^#{1,6}\s|\Z)',
        text,
    )
    accepted_risk = False
    if accepted_risk_section is not None:
        body = accepted_risk_section.group('body').strip()
        normalized = re.sub(r'(?m)^\s*(?:[-*]\s*)?', '', body).strip().lower()
        accepted_risk = normalized not in {'', 'none', 'none.', 'no accepted risks.'}
    accepted_high_row = re.search(
        r'(?i)^\|[^\n]*(?:critical|high)[^\n]*\|[^\n]*accepted[^\n]*\|\s*$',
        text,
        re.MULTILINE,
    )
    return bool(
        data.get('status') == 'verified'
        and data.get('threats_open') == 0
        and not accepted_risk
        and accepted_high_row is None
    )


def _verification_is_green(data: dict[str, Any]) -> bool:
    behavior_unverified = data.get('behavior_unverified')
    if type(behavior_unverified) is not int or behavior_unverified < 0:
        raise ValueError('verification audit behavior_unverified type mismatch')
    gaps = data.get('gaps')
    return bool(
        data.get('status') == 'passed'
        and data.get('score') == '5/5 must-haves verified'
        and behavior_unverified == 0
        and data.get('requirements_verified') == '17/17'
        and gaps == []
    )


def _validate_probe_ledger(root: Path) -> None:
    data = _load_json_object(root / PHASE_DIR_REL / '05-EDGE-PROBE-LEDGER.json')
    items = data.get('items')
    if not isinstance(items, list) or len(items) != EXPECTED_PROBE_COUNT:
        raise ValueError('probe ledger count mismatch')
    ids = [f'{item.get("requirement_id")}-{item.get("category")}' for item in items]
    if tuple(ids) != EDGE_PROBE_IDS:
        raise ValueError('probe ledger ids mismatch')
    if any(
        item.get('status') != 'resolved' or item.get('verification') != 'explicit'
        for item in items
    ):
        raise ValueError('probe ledger unresolved')
    coverage = data.get('coverage') or {}
    if (
        coverage.get('applicable') != EXPECTED_PROBE_COUNT
        or coverage.get('resolved') != EXPECTED_PROBE_COUNT
        or coverage.get('unresolved') != 0
    ):
        raise ValueError('probe ledger coverage mismatch')


def _initial_ledger_binding(root: Path) -> dict[str, str]:
    ledger = _load_json_object(root / DEFAULT_LEDGER_REL)
    digest = ledger.get('ledger_sha256')
    if not _ledger_integrity_ok(ledger) or not isinstance(digest, str):
        raise ValueError('initial ledger binding invalid')
    if ledger.get('package_stage') == 'final':
        digest = (ledger.get('initial_evidence') or {}).get('ledger_sha256')
        if not isinstance(digest, str) or HEX_SHA256.fullmatch(digest) is None:
            raise ValueError('initial ledger binding invalid')
    evaluated_head = ledger.get('evaluated_head')
    if not isinstance(evaluated_head, str) or re.fullmatch(r'[0-9a-f]{40}', evaluated_head) is None:
        raise ValueError('initial ledger binding invalid')
    return {
        'evaluated_head': evaluated_head,
        'execution_input_digest': content_digest(execution_input_digest_map(root)),
        'reviewed_worktree_digest': reviewed_worktree_digest(root),
        'initial_ledger_sha256': digest,
    }


def _validate_audit_binding(data: dict[str, Any], expected: dict[str, str], name: str) -> None:
    _require_keys(data, AUDIT_BINDING_KEYS, name)
    for key, value in expected.items():
        if data.get(key) != value:
            raise ValueError(f'{name} audit binding mismatch')
    audited_at = data.get('audited_at')
    if not isinstance(audited_at, str):
        raise ValueError(f'{name} audit timestamp mismatch')
    try:
        parsed = datetime.fromisoformat(audited_at.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'{name} audit timestamp mismatch') from exc
    if parsed.tzinfo is None:
        raise ValueError(f'{name} audit timestamp mismatch')
    now = datetime.now(timezone.utc)
    parsed_utc = parsed.astimezone(timezone.utc)
    if parsed_utc > now + timedelta(minutes=5) or parsed_utc < now - timedelta(days=7):
        raise ValueError(f'{name} audit timestamp stale')
    if name == 'review' and data.get('review_scope') != AUDIT_SCOPE_ID:
        raise ValueError('review audit scope mismatch')


def parse_audits(root: Path) -> dict[str, dict[str, Any]]:
    _validate_probe_ledger(root)
    expected_binding = _initial_ledger_binding(root)
    accepted: dict[str, dict[str, Any]] = {}
    for name in AUDIT_NAMES:
        rel = AUDIT_PATH_BY_NAME[name]
        path = root / rel
        data = parse_frontmatter(path)
        _require_exact_keys(data, AUDIT_FRONTMATTER_KEYS[name], name)
        _validate_audit_binding(data, expected_binding, name)
        text = path.read_text(encoding='utf-8')
        if name == 'review':
            green = _review_is_clean(data)
        elif name == 'validation':
            green = _validation_is_green(data, text)
        elif name == 'security':
            green = _security_is_green(data, text)
        else:
            green = _verification_is_green(data)
        if not green:
            raise ValueError(f'audit rejected: {path.name}')
        accepted[name] = {
            'path': rel.as_posix(),
            'status': 'pass',
            'sha256': sha256_file_lf(path),
        }
    return accepted


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'invalid JSON artifact: {path.name}') from exc
    if not isinstance(value, dict):
        raise ValueError(f'JSON artifact must be object: {path.name}')
    return value


def _ledger_integrity_ok(ledger: dict[str, Any]) -> bool:
    expected = ledger.get('ledger_sha256')
    return isinstance(expected, str) and expected == _canonical_sha256(ledger, 'ledger_sha256')


def _report_integrity_ok(report: dict[str, Any]) -> bool:
    expected = report.get('report_sha256')
    return isinstance(expected, str) and expected == _canonical_sha256(report, 'report_sha256')


def _assert_initial_ledger_for_finalization(
    root: Path, ledger: dict[str, Any]
) -> list[dict[str, Any]]:
    if (
        ledger.get('schema_version') != SCHEMA_VERSION
        or ledger.get('package_stage') != 'initial'
        or not _ledger_integrity_ok(ledger)
    ):
        raise ValueError('initial ledger stage/integrity invalid')
    validate_initial_package(ledger, _build_report_model(ledger))
    if ledger.get('phase_5_complete') is not False or ledger.get(
        'ready_to_regenerate_canary'
    ) is not False:
        raise ValueError('initial ledger already claims closure')
    current_specs = canonical_specs(root)
    current_specs_json = canonical_specs_json(current_specs)
    if ledger.get('canonical_specs') != json.loads(current_specs_json) or ledger.get(
        'spec_sha256'
    ) != sha256_text(current_specs_json):
        raise ValueError('initial canonical spec drift detected')
    initial_content_map = content_digest_map(root, INITIAL_GATE_INPUT_RELS)
    if ledger.get('content_sha256_map') != initial_content_map or ledger.get(
        'content_digest'
    ) != content_digest(initial_content_map):
        raise ValueError('initial content drift detected')
    initial_execution_map = execution_input_digest_map(root)
    if ledger.get('execution_input_sha256_map') != initial_execution_map or ledger.get(
        'execution_input_digest'
    ) != content_digest(initial_execution_map):
        raise ValueError('initial execution input drift detected')
    worktree_map = reviewed_worktree_digest_map(root)
    if ledger.get('reviewed_worktree_sha256_map') != worktree_map or ledger.get(
        'reviewed_worktree_digest'
    ) != content_digest(worktree_map):
        raise ValueError('initial reviewed worktree drift detected')
    if ledger.get('evaluated_head') != git_head(root) or ledger.get('proof_head') != ledger.get(
        'evaluated_head'
    ):
        raise ValueError('initial HEAD binding mismatch')
    _validate_sentinel(ledger.get('sentinel'))
    results = list(ledger.get('results') or [])
    if not validate_result_partition(results, require_all_ids=True):
        raise ValueError('initial result inventory/classification invalid')
    for spec, row in zip(current_specs, results, strict=True):
        _validate_result_evidence(row)
        for key in ('id', 'argv', 'expected_exit', 'mandatory', 'kind'):
            if row.get(key) != spec.get(key):
                raise ValueError('initial result/spec binding mismatch')
        if row.get('status') == 'availability-skip':
            if spec['id'] not in OPTIONAL_AVAILABILITY_CHECK_IDS or spec.get('enabled') is not True:
                raise ValueError('initial availability classification invalid')
            if not row.get('availability_reason'):
                raise ValueError('initial availability classification invalid')
        elif row.get('status') != 'pass':
            raise ValueError('initial runnable failure blocks finalization')
    safety = ledger.get('safety') or {}
    if (
        safety.get('safety_checks_pass') is not True
        or safety.get('test_group') != ALLOWED_TEST_GROUP
        or safety.get('forbidden_group') != FORBIDDEN_GROUP
        or safety.get('historical_oracle_catalog_v2_queried')
        is not HISTORICAL_ORACLE_CATALOG_V2_QUERIED
        or safety.get('historical_v2_commit') != HISTORICAL_V2_COMMIT
        or safety.get('historical_v2_class') != HISTORICAL_V2_CLASS
        or safety.get('historical_v2_scope') != HISTORICAL_V2_SCOPE
        or safety.get('historical_violation_note') != HISTORICAL_V2_VIOLATION_NOTE
        or safety.get('current_source_v2_hits') != []
        or any(
            value is not False
            for value in (
                ledger.get('canary_executed'),
                ledger.get('oracle_catalog_v2_queried'),
                ledger.get('current_oracle_catalog_v2_queried'),
                ledger.get('current_oracle_catalog_v2_mutated'),
                ledger.get('clear_graph_called'),
                safety.get('canary_executed'),
                safety.get('oracle_catalog_v2_queried'),
                safety.get('current_oracle_catalog_v2_queried'),
                safety.get('clear_graph_called'),
                safety.get('current_source_v2_param_query'),
            )
        )
    ):
        raise ValueError('initial safety invariant failed')
    history = ledger.get('historical_audit') or {}
    if (
        history.get('commit') != HISTORICAL_V2_COMMIT
        or history.get('class') != HISTORICAL_V2_CLASS
        or history.get('scope') != HISTORICAL_V2_SCOPE
        or history.get('checkpoint_sha256') != HISTORICAL_CHECKPOINT_SHA256
        or history.get('checkpoint_attempt_count') != HISTORICAL_CHECKPOINT_ATTEMPT_COUNT
    ):
        raise ValueError('historical axis mismatch')
    return current_specs


def run_final_closure_checks(
    root: Path, specs: list[dict[str, Any]]
) -> dict[str, Any]:
    by_id = {spec['id']: spec for spec in specs}
    if set(FINAL_RERUN_CHECK_IDS) - by_id.keys():
        raise ValueError('final closure check inventory mismatch')
    start_head = git_head(root)
    start_map = content_digest_map(root, FINAL_GATE_INPUT_RELS)
    start_execution_map = execution_input_digest_map(root)
    start_worktree_map = reviewed_worktree_digest_map(root)
    child_env = dict(os.environ)
    child_env['CATALOG_PHASE5_GATE_SKIP_SELF'] = '1'
    child_env['CATALOG_CEILING_SMOKE'] = '1'
    child_env.pop('CATALOG_INT_REQUIRED', None)
    child_env.pop('CATALOG_OLLAMA_REQUIRED', None)
    outcomes: list[dict[str, Any]] = []
    for check_id in FINAL_RERUN_CHECK_IDS:
        spec = by_id[check_id]
        try:
            row = _result_row(spec, run_argv(spec['argv'], root, env=child_env))
        except Exception as exc:
            row = _failure_row(spec, exc)
        outcomes.append(row)
    sentinel = run_sentinel(root)
    end_map = content_digest_map(root, FINAL_GATE_INPUT_RELS)
    end_execution_map = execution_input_digest_map(root)
    end_worktree_map = reviewed_worktree_digest_map(root)
    if (
        git_head(root) != start_head
        or end_map != start_map
        or end_execution_map != start_execution_map
        or end_worktree_map != start_worktree_map
    ):
        raise ValueError('final closure input drift detected')
    if any(row.get('status') != 'pass' for row in outcomes) or sentinel.get('pass') is not True:
        raise ValueError('final closure check failed')
    return {
        'evaluated_head': start_head,
        'spec_sha256': sha256_text(canonical_specs_json(specs)),
        'rerun_check_ids': list(FINAL_RERUN_CHECK_IDS),
        'preserved_external_check_ids': list(PRESERVED_EXTERNAL_CHECK_IDS),
        'results': outcomes,
        'sentinel': sentinel,
        'input_sha256_map': start_map,
        'input_digest': content_digest(start_map),
        'execution_input_sha256_map': start_execution_map,
        'execution_input_digest': content_digest(start_execution_map),
        'reviewed_worktree_sha256_map': start_worktree_map,
        'reviewed_worktree_digest': content_digest(start_worktree_map),
    }


def _validate_final_closure_checks(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError('final closure checks missing')
    evidence: dict[str, Any] = value
    rows = evidence.get('results')
    if not isinstance(rows, list):
        raise ValueError('final closure checks missing')
    if tuple(row.get('id') for row in rows if isinstance(row, dict)) != FINAL_RERUN_CHECK_IDS:
        raise ValueError('final closure check inventory mismatch')
    for row in rows:
        if not isinstance(row, dict) or row.get('status') != 'pass' or row.get(
            'exit_code'
        ) != row.get('expected_exit', 0):
            raise ValueError('final closure check result mismatch')
        for digest_key in ('stdout_sha256', 'stderr_sha256'):
            digest = row.get(digest_key)
            if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
                raise ValueError('final closure check digest mismatch')
    if evidence.get('rerun_check_ids') != list(FINAL_RERUN_CHECK_IDS) or evidence.get(
        'preserved_external_check_ids'
    ) != list(PRESERVED_EXTERNAL_CHECK_IDS):
        raise ValueError('final closure check ids mismatch')
    if (evidence.get('sentinel') or {}).get('pass') is not True:
        raise ValueError('final closure sentinel mismatch')
    return evidence


def _derive_final_readiness(
    results: list[dict[str, Any]], safety: dict[str, Any], local_gate_pass: bool
) -> bool:
    return derive_ready_to_regenerate_canary(
        local_gate_pass,
        safety,
        registration_pass=_spec_pass(results, 'catalog_registration_14'),
        unit_service_pass=_spec_pass(results, 'focused_pytest'),
        security_matrix_pass=_spec_pass(results, 'security_matrix'),
        legacy_contract_pass=_spec_pass(results, 'legacy_contract_14'),
        offline_canary_pass=_spec_pass(results, 'offline_canary_pure'),
        docs_pass=_spec_pass(results, 'docs_operator_sections')
        and _spec_pass(results, 'docs_migration_phrases'),
        audits_pass=True,
        post_execution_audits_pending=False,
        phase_5_complete=True,
        requirements_complete=True,
        edge_probes_complete=True,
    )


def _build_final_ledger(
    root: Path,
    initial: dict[str, Any],
    audits: dict[str, dict[str, Any]],
    closure_checks: dict[str, Any],
) -> dict[str, Any]:
    closure_rows = {
        row['id']: row for row in _validate_final_closure_checks(closure_checks)['results']
    }
    initial_rows = {row['id']: row for row in initial['results']}
    results = [
        closure_rows.get(check_id, initial_rows[check_id]) for check_id in CANONICAL_CHECK_IDS
    ]
    safety = derive_safety_ledger(results, root)
    local_gate_pass = derive_local_gate_pass(
        results, dict(closure_checks.get('sentinel') or {}), require_all_ids=True
    )
    requirements = {requirement: 'verified' for requirement in REQUIREMENT_IDS}
    probes = {probe: 'resolved' for probe in EDGE_PROBE_IDS}
    ready = _derive_final_readiness(results, safety, local_gate_pass)
    if not ready:
        raise ValueError('final readiness formula rejected inputs')
    content_map = content_digest_map(root, FINAL_GATE_INPUT_RELS)
    final = dict(initial)
    final.update(
        {
            'package_stage': 'final',
            'evaluated_head': git_head(root),
            'proof_head': git_head(root),
            'content_sha256_map': content_map,
            'content_digest': content_digest(content_map),
            'results': results,
            'sentinel': closure_checks['sentinel'],
            'initial_evidence': {
                'evaluated_head': initial.get('evaluated_head'),
                'proof_head': initial.get('proof_head'),
                'ledger_sha256': initial.get('ledger_sha256'),
                'spec_sha256': initial.get('spec_sha256'),
                'content_digest': initial.get('content_digest'),
                'results': list(initial['results']),
            },
            'result_sources': {
                check_id: (
                    'initial_external'
                    if check_id in PRESERVED_EXTERNAL_CHECK_IDS
                    else 'final_rerun'
                )
                for check_id in CANONICAL_CHECK_IDS
            },
            'requirement_ids': list(REQUIREMENT_IDS),
            'requirement_dispositions': requirements,
            'edge_probe_dispositions': probes,
            'audits': audits,
            'audits_pass': True,
            'closure_evidence': closure_checks,
            'post_execution_audits_pending': False,
            'nyquist_compliant': True,
            'phase_5_complete': True,
            'ready_to_regenerate_canary': True,
            'local_gate_pass': True,
            'safety': safety,
            'canary_executed': False,
            'current_oracle_catalog_v2_queried': False,
            'current_oracle_catalog_v2_mutated': False,
            'oracle_catalog_v2_queried': False,
            'clear_graph_called': False,
        }
    )
    final.pop('ledger_sha256', None)
    final['ledger_sha256'] = _canonical_sha256(final, 'ledger_sha256')
    return final


def verify_final_package(
    root: Path,
    ledger_path: Path,
    report_json_path: Path,
    report_md_path: Path,
    *,
    require_ready: bool,
    expected_requirements: int,
    expected_edge_probes: int,
) -> dict[str, Any]:
    check_historical_artifacts_unchanged(root)
    check_hardened_artifacts_strict(root)
    check_canary_not_executed(root)
    check_safety_no_probe(root)
    audits = parse_audits(root)
    ledger = _load_json_object(ledger_path)
    report = _load_json_object(report_json_path)
    markdown = report_md_path.read_text(encoding='utf-8')
    _validate_package_marker(
        _package_marker_path(ledger_path),
        ledger_path,
        report_json_path,
        report_md_path,
        ledger,
    )
    if not _ledger_integrity_ok(ledger) or not _report_integrity_ok(report):
        raise ValueError('final package digest mismatch')
    if ledger.get('package_stage') != 'final':
        raise ValueError('final ledger stage mismatch')
    closure = _validate_final_closure_checks(ledger.get('closure_evidence'))
    current_specs = canonical_specs(root)
    current_specs_json = canonical_specs_json(current_specs)
    if ledger.get('canonical_specs') != json.loads(current_specs_json) or ledger.get(
        'spec_sha256'
    ) != sha256_text(current_specs_json):
        raise ValueError('final canonical spec drift detected')
    if closure.get('spec_sha256') != ledger.get('spec_sha256'):
        raise ValueError('final closure spec binding mismatch')
    if closure.get('evaluated_head') != ledger.get('evaluated_head'):
        raise ValueError('final closure HEAD binding mismatch')
    closure_map = content_digest_map(root, FINAL_GATE_INPUT_RELS)
    if closure.get('input_sha256_map') != closure_map or closure.get(
        'input_digest'
    ) != content_digest(closure_map):
        raise ValueError('final closure input drift detected')
    execution_map = execution_input_digest_map(root)
    if closure.get('execution_input_sha256_map') != execution_map or closure.get(
        'execution_input_digest'
    ) != content_digest(execution_map):
        raise ValueError('final execution input drift detected')
    worktree_map = reviewed_worktree_digest_map(root)
    if closure.get('reviewed_worktree_sha256_map') != worktree_map or closure.get(
        'reviewed_worktree_digest'
    ) != content_digest(worktree_map):
        raise ValueError('final reviewed worktree drift detected')
    if expected_requirements != EXPECTED_REQUIREMENT_COUNT or len(
        ledger.get('requirement_dispositions') or {}
    ) != expected_requirements:
        raise ValueError('final requirement count mismatch')
    if expected_edge_probes != EXPECTED_PROBE_COUNT or len(
        ledger.get('edge_probe_dispositions') or {}
    ) != expected_edge_probes:
        raise ValueError('final probe count mismatch')
    if set(ledger['requirement_dispositions']) != set(REQUIREMENT_IDS):
        raise ValueError('final requirement ids mismatch')
    if set(ledger['edge_probe_dispositions']) != set(EDGE_PROBE_IDS):
        raise ValueError('final probe ids mismatch')
    if require_ready and (
        ledger.get('ready_to_regenerate_canary') is not True
        or ledger.get('phase_5_complete') is not True
        or report.get('ready_to_regenerate_canary') is not True
        or report.get('phase_5_complete') is not True
    ):
        raise ValueError('final package is not ready')
    if ledger.get('proof_head') != ledger.get('evaluated_head') or report.get(
        'evaluated_head'
    ) != ledger.get('evaluated_head'):
        raise ValueError('final HEAD binding mismatch')
    _verify_proof_head(root, ledger.get('evaluated_head'))
    current_map = content_digest_map(root, FINAL_GATE_INPUT_RELS)
    if ledger.get('content_sha256_map') != current_map or ledger.get(
        'content_digest'
    ) != content_digest(current_map):
        raise ValueError('final source drift detected')
    if report.get('content_digest') != ledger.get('content_digest'):
        raise ValueError('final content binding mismatch')
    recorded_audits = ledger.get('audits') or {}
    if recorded_audits != audits or report.get('audits') != audits:
        raise ValueError('final audit binding mismatch')
    initial_evidence = ledger.get('initial_evidence') or {}
    initial_results = list(initial_evidence.get('results') or [])
    if not validate_result_partition(initial_results, require_all_ids=True):
        raise ValueError('final initial evidence mismatch')
    for spec, row in zip(current_specs, initial_results, strict=True):
        for key in ('id', 'argv', 'expected_exit', 'mandatory', 'kind'):
            if row.get(key) != spec.get(key):
                raise ValueError('final initial result/spec binding mismatch')
    closure_specs = {spec['id']: spec for spec in current_specs}
    for row in closure['results']:
        spec = closure_specs[row['id']]
        for key in ('id', 'argv', 'expected_exit', 'mandatory', 'kind'):
            if row.get(key) != spec.get(key):
                raise ValueError('final closure result/spec binding mismatch')
    closure_rows = {row['id']: row for row in closure['results']}
    initial_rows = {row['id']: row for row in initial_results}
    effective = [
        closure_rows.get(check_id, initial_rows[check_id]) for check_id in CANONICAL_CHECK_IDS
    ]
    if ledger.get('results') != effective:
        raise ValueError('final effective result mismatch')
    if ledger.get('result_sources') != {
        check_id: (
            'initial_external'
            if check_id in PRESERVED_EXTERNAL_CHECK_IDS
            else 'final_rerun'
        )
        for check_id in CANONICAL_CHECK_IDS
    }:
        raise ValueError('final result source mismatch')
    safety = derive_safety_ledger(effective, root)
    local_gate_pass = derive_local_gate_pass(
        effective, dict(closure.get('sentinel') or {}), require_all_ids=True
    )
    if ledger.get('safety') != safety or ledger.get('local_gate_pass') is not local_gate_pass:
        raise ValueError('final derived safety/gate mismatch')
    ready = _derive_final_readiness(effective, safety, local_gate_pass)
    if (
        ready is not True
        or ledger.get('ready_to_regenerate_canary') is not ready
        or ledger.get('phase_5_complete') is not ready
    ):
        raise ValueError('final derived readiness mismatch')
    if any(value != 'verified' for value in ledger['requirement_dispositions'].values()):
        raise ValueError('final requirement disposition mismatch')
    if any(value != 'resolved' for value in ledger['edge_probe_dispositions'].values()):
        raise ValueError('final probe disposition mismatch')
    if report.get('canary_executed') is not False or ledger.get(
        'canary_executed'
    ) is not False:
        raise ValueError('final canary invariant mismatch')
    expected_report = _build_report_model(ledger)
    if report != expected_report:
        raise ValueError('final report model mismatch')
    if render_report_markdown(report) != markdown:
        raise ValueError('final Markdown report mismatch')
    return ledger


def _require_canonical_package_paths(
    root: Path,
    ledger_path: Path,
    report_json_path: Path,
    report_md_path: Path,
) -> None:
    expected = (
        (root / DEFAULT_LEDGER_REL).resolve(),
        (root / DEFAULT_REPORT_JSON_REL).resolve(),
        (root / DEFAULT_REPORT_MD_REL).resolve(),
    )
    actual = (
        ledger_path.resolve(),
        report_json_path.resolve(),
        report_md_path.resolve(),
    )
    if actual != expected:
        raise ValueError('final proof paths must be canonical')


def finalize_package(
    root: Path,
    ledger_path: Path,
    report_json_path: Path,
    report_md_path: Path,
    *,
    require_audits: bool,
    require_ready: bool,
    expected_requirements: int,
    expected_edge_probes: int,
) -> dict[str, Any]:
    if require_audits is not True or require_ready is not True:
        raise ValueError('finalize requires --require-audits and --require-ready')
    if expected_requirements != EXPECTED_REQUIREMENT_COUNT:
        raise ValueError('expected requirement count must be 17')
    if expected_edge_probes != EXPECTED_PROBE_COUNT:
        raise ValueError('expected edge probe count must be 37')
    initial = _load_json_object(ledger_path)
    initial_report = _load_json_object(report_json_path)
    _validate_package_marker(
        _package_marker_path(ledger_path),
        ledger_path,
        report_json_path,
        report_md_path,
        initial,
    )
    validate_initial_package(initial, initial_report)
    if report_md_path.read_text(encoding='utf-8') != render_report_markdown(initial_report):
        raise ValueError('initial Markdown report mismatch')
    current_specs = _assert_initial_ledger_for_finalization(root, initial)
    audits = parse_audits(root)
    check_historical_artifacts_unchanged(root)
    check_hardened_artifacts_strict(root)
    check_canary_not_executed(root)
    check_safety_no_probe(root)
    closure_checks = run_final_closure_checks(root, current_specs)
    final = _build_final_ledger(root, initial, audits, closure_checks)
    report = _build_report_model(final)
    markdown = render_report_markdown(report)
    targets = (
        ledger_path,
        report_json_path,
        report_md_path,
        _package_marker_path(ledger_path),
    )
    backups = {path: path.read_bytes() if path.exists() else None for path in targets}
    atomic_write_package(
        ledger_path,
        final,
        report_json_path,
        report,
        report_md_path,
        markdown,
    )
    try:
        return verify_final_package(
            root,
            ledger_path,
            report_json_path,
            report_md_path,
            require_ready=True,
            expected_requirements=expected_requirements,
            expected_edge_probes=expected_edge_probes,
        )
    except Exception:
        _restore_package(backups)
        raise


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
    parser.add_argument('--report-json', default=str(DEFAULT_REPORT_JSON_REL))
    parser.add_argument('--report-md', default=str(DEFAULT_REPORT_MD_REL))
    parser.add_argument('--no-live', action='store_true')
    parser.add_argument('--require-audits', action='store_true')
    parser.add_argument('--require-ready', action='store_true')
    parser.add_argument('--expected-requirements', type=int, default=EXPECTED_REQUIREMENT_COUNT)
    parser.add_argument('--expected-edge-probes', type=int, default=EXPECTED_PROBE_COUNT)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else repo_root_from()
    ledger_path = Path(args.ledger)
    report_json_path = Path(args.report_json)
    report_md_path = Path(args.report_md)
    if not ledger_path.is_absolute():
        ledger_path = root / ledger_path
    if not report_json_path.is_absolute():
        report_json_path = root / report_json_path
    if not report_md_path.is_absolute():
        report_md_path = root / report_md_path

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

    if args.command == 'finalize':
        try:
            _require_canonical_package_paths(
                root, ledger_path, report_json_path, report_md_path
            )
            ledger = finalize_package(
                root,
                ledger_path,
                report_json_path,
                report_md_path,
                require_audits=args.require_audits,
                require_ready=args.require_ready,
                expected_requirements=args.expected_requirements,
                expected_edge_probes=args.expected_edge_probes,
            )
        except Exception as exc:
            print(_safe_failure_summary(exc), file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    'command': 'finalize',
                    'ready_to_regenerate_canary': ledger['ready_to_regenerate_canary'],
                    'phase_5_complete': ledger['phase_5_complete'],
                    'evaluated_head': ledger['evaluated_head'],
                    'canary_executed': ledger['canary_executed'],
                },
                indent=2,
            )
        )
        return 0

    if args.command == 'verify-final':
        try:
            _require_canonical_package_paths(
                root, ledger_path, report_json_path, report_md_path
            )
            ledger = verify_final_package(
                root,
                ledger_path,
                report_json_path,
                report_md_path,
                require_ready=args.require_ready,
                expected_requirements=args.expected_requirements,
                expected_edge_probes=args.expected_edge_probes,
            )
        except Exception as exc:
            print(_safe_failure_summary(exc), file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    'command': 'verify-final',
                    'ready_to_regenerate_canary': ledger['ready_to_regenerate_canary'],
                    'phase_5_complete': ledger['phase_5_complete'],
                    'evaluated_head': ledger['evaluated_head'],
                    'canary_executed': ledger['canary_executed'],
                },
                indent=2,
            )
        )
        return 0

    if args.command in ('run', 'run-initial'):
        ledger = run_gate(
            root,
            ledger_path,
            include_live=not args.no_live,
            report_json_path=report_json_path,
            report_md_path=report_md_path,
        )
        print(
            json.dumps(
                {
                    'local_gate_pass': ledger['local_gate_pass'],
                    'safety_checks_pass': (ledger.get('safety') or {}).get('safety_checks_pass'),
                    'ready_to_regenerate_canary': ledger['ready_to_regenerate_canary'],
                    'phase_5_complete': ledger['phase_5_complete'],
                    'post_execution_audits_pending': ledger['post_execution_audits_pending'],
                    'evaluated_head': ledger['evaluated_head'],
                    'spec_sha256': ledger['spec_sha256'],
                    'content_digest': ledger['content_digest'],
                    'canary_executed': ledger['canary_executed'],
                    'oracle_catalog_v2_queried': ledger['oracle_catalog_v2_queried'],
                    'clear_graph_called': ledger['clear_graph_called'],
                    'results': [
                        {
                            'id': row['id'],
                            'status': row['status'],
                            'exit_code': row['exit_code'],
                            'availability_reason': row.get('availability_reason'),
                        }
                        for row in ledger['results']
                    ],
                },
                indent=2,
            )
        )
        return derive_cli_exit_code(ledger)

    return 2


if __name__ == '__main__':
    raise SystemExit(main())
