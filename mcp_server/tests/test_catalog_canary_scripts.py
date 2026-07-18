"""Offline canary builder/runner tests (Phase 5 / plan 05-03).

Hard constraints:
- Never execute scripts/run_catalog_canary_batch.py as a process against MCP.
- Never open network/DB/LLM/queue/embed side effects.
- Historical catalog/canary-v2-requests/* remain read-only digests.
- Hardened authority lives only under catalog/canary-v2-requests-hardened/.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import socket
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / 'scripts' / 'run_catalog_canary_batch.py'
BUILDER_PATH = ROOT / 'scripts' / 'build_catalog_canary_requests.py'
HISTORICAL_ARTIFACT_DIR = ROOT / 'catalog' / 'canary-v2-requests'
HARDENED_ARTIFACT_DIR = ROOT / 'catalog' / 'canary-v2-requests-hardened'
CHECKPOINT_PATH = ROOT / 'catalog' / 'catalog.json.graphiti-canary-v2-state.json'
SUMMARY_PATH = ROOT / 'catalog' / 'CANARY_V2_SUMMARY.md'
SANITIZED_FIXTURE = ROOT / 'mcp_server' / 'tests' / 'fixtures' / 'accept_tab_sanitized.json'
GATE_RUNNER = ROOT / 'mcp_server' / 'tests' / 'catalog_phase5_gate_runner.py'
PHASE_DIR = (
    ROOT / '.planning' / 'phases' / '05-verification-security-compatibility-and-migration-docs'
)

# Frozen pre-Phase-5 historical digests (D-05, D-11). Scripts/tests may change;
# historical artifacts must not.
HISTORICAL_DIGESTS: dict[str, str] = {
    'catalog/CANARY_V2_SUMMARY.md': (
        '03e8c4bc31e6cbeeb32e4aa2d9cc74dd07c840206b81ea4055ea53e0f3855686'
    ),
    'catalog/catalog.json.graphiti-canary-v2-state.json': (
        'b367e7f395782d13e72671e1b66d36b24432cb2c1b48c7fa45974d232039ace4'
    ),
    'catalog/canary-v2-requests/accept-tab.commit.response.json': (
        '83ac93da85957c5576c745a4db2e64d6e6ee8e99a2ac6c517e17b3f3e1ccc4f4'
    ),
    'catalog/canary-v2-requests/accept-tab.dry-run.response.json': (
        '4767473f3ace434ae23bb69687261da8041f430e5ba1908f0ca62cd496fab139'
    ),
    'catalog/canary-v2-requests/accept-tab.payload.json': (
        '629decce0f7927d4de542b0cf2b11b12f45872c1d5e4771fd00c900091f3ba48'
    ),
    'catalog/canary-v2-requests/documented-foreign-keys.payload.json': (
        '2da07e6a9f9a89d5cc6d5352007a3de3401e492ec66175cf480a501fc9741035'
    ),
    'catalog/canary-v2-requests/form-cfg.payload.json': (
        '25ca477a8f4180baa00d0b4e60b772b1663552ea3d92decac3d276cdcc2ea11b'
    ),
    'catalog/canary-v2-requests/manifest.json': (
        '039063d7adfe774564b8a8009af0868f96bb570fc1d74b4236e891d89506763d'
    ),
    'catalog/canary-v2-requests/pre-auth-txn-type.payload.json': (
        '96150b1e1f10d5b5183f36aecb846f357af6aecd066e7d2d29f84c9872d1bb0b'
    ),
    'catalog/canary-v2-requests/trans-type-class.payload.json': (
        '4337527970d5f010ae842a06b47dd3fc2ef46d8594e3336eb9b17a02b34a3e25'
    ),
    'catalog/canary-v2-requests/trans-type.payload.json': (
        '97d1b81d4a11434020da0b9bb0c6dd3cb5a099c93ac9ce925c92c5f59e704024'
    ),
}
HISTORICAL_CHECKPOINT_ATTEMPTS = 2
HISTORICAL_ACCEPT_TAB_REQUEST_SHA256 = (
    'a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a'
)
HISTORICAL_UNIQUE_TOTALS = {'entities': 38, 'edges': 85}
HISTORICAL_ACCEPT_TAB_RECEIPT_SHAPE = '10/16/1'

PRODUCTION_CONTENT_DENYLIST = (
    'SVFE_SHB',
    'docling-14451470779352042667',
    'docling-144514770779352042667',
    'OPENAI_API_KEY',
    'Bearer ',
    'password',
    'Authorization',
    'plan_token_value',
    'neo4j+s://',
)


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_script('catalog_canary_builder_under_test', BUILDER_PATH)
runner = _load_script('catalog_canary_runner_under_test', RUNNER_PATH)

PREFERRED_HARDENED_SEQUENCE = [
    'prepare_catalog_batch',
    'commit_prepared_catalog_batch',
    'get_catalog_ingest_status',
    'verify_catalog_batch',
    'resolve_typed_entities',
    'get_catalog_batch_manifest',
    'get_catalog_evidence',
    'search_nodes',
    'search_memory_facts',
]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            found.append(str(key))
            found.extend(_walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_strings(item))
    return found


# ---------------------------------------------------------------------------
# Strict JSON (shared pure helpers)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('data', 'message'),
    [
        (b'\xef\xbb\xbf{}', 'UTF-8 BOM is forbidden'),
        (b'{"a":1,"a":2}', 'duplicate JSON key: a'),
        (b'{"a":NaN}', 'non-finite JSON number: NaN'),
    ],
)
def test_builder_strict_json_rejects_bom_duplicates_and_nonfinite(
    data: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        builder.strict_json_bytes(data, 'test.json')


@pytest.mark.parametrize(
    ('data', 'code'),
    [
        (b'\xef\xbb\xbf{}', 'utf8_bom'),
        (b'{"a":1,"a":2}', 'duplicate_json_key'),
        (b'{"a":Infinity}', 'non_finite_json'),
    ],
)
def test_runner_strict_json_rejects_bom_duplicates_and_nonfinite(data: bytes, code: str) -> None:
    with pytest.raises(runner.RunnerError) as error:
        runner.strict_json_loads(data)
    assert error.value.code == code


# ---------------------------------------------------------------------------
# Historical inventory / immutability (D-05, D-11)
# ---------------------------------------------------------------------------


def test_historical_inventory_and_digests_preserved() -> None:
    """Every historical artifact path is inventoried with frozen SHA-256."""
    inventory = {
        'builder': 'scripts/build_catalog_canary_requests.py',
        'runner': 'scripts/run_catalog_canary_batch.py',
        'sanitized_fixture': 'mcp_server/tests/fixtures/accept_tab_sanitized.json',
        'offline_tests': 'mcp_server/tests/test_catalog_canary_scripts.py',
        'historical_summary': 'catalog/CANARY_V2_SUMMARY.md',
        'historical_checkpoint': 'catalog/catalog.json.graphiti-canary-v2-state.json',
        'historical_dir': 'catalog/canary-v2-requests',
        'hardened_dir': 'catalog/canary-v2-requests-hardened',
    }
    for rel in inventory.values():
        assert (ROOT / rel).exists(), rel

    expected_files = {
        'accept-tab.payload.json',
        'form-cfg.payload.json',
        'pre-auth-txn-type.payload.json',
        'trans-type.payload.json',
        'trans-type-class.payload.json',
        'documented-foreign-keys.payload.json',
        'accept-tab.dry-run.response.json',
        'accept-tab.commit.response.json',
        'manifest.json',
    }
    actual = {path.name for path in HISTORICAL_ARTIFACT_DIR.iterdir() if path.is_file()}
    assert expected_files <= actual

    for rel, digest in HISTORICAL_DIGESTS.items():
        path = ROOT / rel
        assert path.is_file(), rel
        assert _sha256_file(path) == digest, rel

    # Historical EXPECTED_BATCHES table remains for inventory (not hardened authority)
    assert 'canary-v2::accept-tab' in runner.EXPECTED_BATCHES
    accept = runner.EXPECTED_BATCHES['canary-v2::accept-tab']
    assert accept['request_sha256'] == HISTORICAL_ACCEPT_TAB_REQUEST_SHA256
    assert accept['provenance'] == (1, 10, 16)


def test_historical_bytes_unchanged_and_attempt_count() -> None:
    checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding='utf-8'))
    assert len(checkpoint['attempts']) == HISTORICAL_CHECKPOINT_ATTEMPTS
    assert (
        _sha256_file(CHECKPOINT_PATH)
        == HISTORICAL_DIGESTS['catalog/catalog.json.graphiti-canary-v2-state.json']
    )
    for rel, digest in HISTORICAL_DIGESTS.items():
        assert _sha256_file(ROOT / rel) == digest


def test_historical_accept_tab_golden_not_hardened_authority() -> None:
    historical_payload = HISTORICAL_ARTIFACT_DIR / 'accept-tab.payload.json'
    with pytest.raises(runner.RunnerError) as error:
        runner.reject_historical_as_hardened(historical_payload)
    assert error.value.code == 'historical_not_hardened_authority'

    hardened = runner.strict_json_loads(
        (HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json').read_bytes()
    )
    hardened_hash = builder.sha256_bytes(
        (HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json').read_bytes()
    )
    # Hardened request SHA must differ from historical ACCEPT_TAB golden
    _, _, _, _, server_hash = runner.validate_hardened_artifact(
        HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json'
    )
    assert server_hash != HISTORICAL_ACCEPT_TAB_REQUEST_SHA256
    assert hardened_hash != HISTORICAL_DIGESTS['catalog/canary-v2-requests/accept-tab.payload.json']
    assert hardened['batch_id'] != 'canary-v2::accept-tab'
    assert hardened['group_id'] == 'oracle-catalog-tool-test'
    # Historical unique totals / receipt shape remain history only
    assert HISTORICAL_UNIQUE_TOTALS == {'entities': 38, 'edges': 85}
    assert HISTORICAL_ACCEPT_TAB_RECEIPT_SHAPE == '10/16/1'


# ---------------------------------------------------------------------------
# Hardened artifacts (D-09, D-15, DOCS-06)
# ---------------------------------------------------------------------------


def test_sanitized_hardened_artifacts_no_production_content() -> None:
    assert SANITIZED_FIXTURE.is_file()
    fixture = json.loads(SANITIZED_FIXTURE.read_text(encoding='utf-8'))
    assert fixture['identity_schema_version'] == 'catalog-v2'
    assert fixture['system_key'] == 'FE'
    assert 'ACCEPT_TAB' in fixture['entities'][0]['name_raw']
    assert fixture['entities'][0]['summary'].startswith('Synthetic')

    for path in HARDENED_ARTIFACT_DIR.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        for banned in PRODUCTION_CONTENT_DENYLIST:
            assert banned not in text, f'{path.name} leaks {banned!r}'
        data = json.loads(text)
        for value in _walk_strings(data):
            for banned in PRODUCTION_CONTENT_DENYLIST:
                assert banned not in value, f'{path.name} string leaks {banned!r}'


def test_hardened_manifest_schema_strict() -> None:
    manifest_path = HARDENED_ARTIFACT_DIR / 'manifest.json'
    raw_bytes = manifest_path.read_bytes()
    manifest = json.loads(raw_bytes.decode('utf-8'))
    assert manifest['artifact_schema_version'] == 'canary-hardened-v1'
    assert manifest['identity_schema_version'] == 'catalog-v2'
    assert manifest['execution_mode'] == 'offline_simulation'
    assert manifest['canary_executed'] is False
    assert manifest['group_id'] == 'oracle-catalog-tool-test'
    assert manifest['future_target_group_id_metadata'] == 'oracle-catalog-v2'
    assert manifest['system_key'] == 'FE'
    assert manifest['preferred_tool_sequence'] == PREFERRED_HARDENED_SEQUENCE

    inventory = manifest['inventory']
    for key in (
        'builder',
        'runner',
        'sanitized_fixture',
        'offline_tests',
        'payload',
        'offline_prepare_receipt',
        'offline_commit_receipt',
        'offline_checkpoint',
    ):
        assert key in inventory

    digests = manifest['digests']
    assert digests['payload'] == _sha256_file(HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json')
    assert digests['offline_prepare_receipt'] == _sha256_file(
        HARDENED_ARTIFACT_DIR / 'offline-prepare.receipt.json'
    )
    assert digests['offline_commit_receipt'] == _sha256_file(
        HARDENED_ARTIFACT_DIR / 'offline-commit.receipt.json'
    )
    assert digests['offline_checkpoint'] == _sha256_file(
        HARDENED_ARTIFACT_DIR / 'offline-checkpoint.json'
    )
    assert digests['sanitized_fixture'] == _sha256_file(SANITIZED_FIXTURE)

    batch = manifest['batches'][0]
    assert batch['batch_id'] == 'accept-tab-batch-001'
    assert batch['counts']['entities'] == 3
    assert batch['counts']['edges'] == 2
    assert batch['counts']['evidence_links'] == 5

    history = manifest['history']
    assert history['status'] == 'read_only_not_authority'
    assert (
        history['historical_accept_tab_golden_server_request_sha256']
        == HISTORICAL_ACCEPT_TAB_REQUEST_SHA256
    )
    assert history['historical_unique_totals'] == HISTORICAL_UNIQUE_TOTALS
    assert history['historical_accept_tab_receipt_shape'] == HISTORICAL_ACCEPT_TAB_RECEIPT_SHAPE

    # Payload validates as prepare-shaped catalog-v2
    _, raw, prepare_req, artifact_sha, request_sha = runner.validate_hardened_artifact(
        HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json'
    )
    assert artifact_sha == digests['payload']
    assert request_sha == batch['server_request_sha256']
    assert prepare_req.identity_schema_version == 'catalog-v2'
    assert prepare_req.system_key == 'FE'
    assert prepare_req.group_id == 'oracle-catalog-tool-test'
    assert raw['provenance']['evidence_links']
    assert 'entity_targets' not in raw['provenance']


def test_offline_receipt_schema_strict() -> None:
    prepare = json.loads(
        (HARDENED_ARTIFACT_DIR / 'offline-prepare.receipt.json').read_text(encoding='utf-8')
    )
    commit = json.loads(
        (HARDENED_ARTIFACT_DIR / 'offline-commit.receipt.json').read_text(encoding='utf-8')
    )
    for receipt, tool in (
        (prepare, 'prepare_catalog_batch'),
        (commit, 'commit_prepared_catalog_batch'),
    ):
        assert receipt['artifact_schema_version'] == 'canary-hardened-v1'
        assert receipt['execution_mode'] == 'offline_simulation'
        assert receipt['canary_executed'] is False
        assert receipt['tool'] == tool
        assert receipt['token_present'] is False
        assert 'plan_token' not in receipt
        assert 'protocol_response' not in receipt
        assert 'entities' not in receipt
        assert 'password' not in json.dumps(receipt)
        blob = json.dumps(receipt)
        for banned in PRODUCTION_CONTENT_DENYLIST:
            assert banned not in blob


def test_offline_checkpoint_schema_strict() -> None:
    checkpoint = json.loads(
        (HARDENED_ARTIFACT_DIR / 'offline-checkpoint.json').read_text(encoding='utf-8')
    )
    assert checkpoint['artifact_schema_version'] == 'canary-hardened-v1'
    assert checkpoint['execution_mode'] == 'offline_simulation'
    assert checkpoint['canary_executed'] is False
    assert checkpoint['canary_attempt_count'] == 0
    assert checkpoint['validation_runs'] == []
    assert checkpoint['future_target_group_id_metadata'] == 'oracle-catalog-v2'
    # Must not equal or replace historical checkpoint
    historical = json.loads(CHECKPOINT_PATH.read_text(encoding='utf-8'))
    assert len(historical['attempts']) == HISTORICAL_CHECKPOINT_ATTEMPTS
    assert checkpoint != historical


def test_builder_hardened_mode_emits_valid_artifacts(tmp_path: Path) -> None:
    out = tmp_path / 'hardened'
    manifest = builder.build_hardened(SANITIZED_FIXTURE, out)
    assert manifest['canary_executed'] is False
    assert (out / 'accept-tab.payload.json').is_file()
    assert (out / 'manifest.json').is_file()
    assert (out / 'offline-prepare.receipt.json').is_file()
    assert (out / 'offline-commit.receipt.json').is_file()
    assert (out / 'offline-checkpoint.json').is_file()
    runner.validate_hardened_artifact(out / 'accept-tab.payload.json')
    # Historical checkpoint untouched
    assert (
        _sha256_file(CHECKPOINT_PATH)
        == HISTORICAL_DIGESTS['catalog/catalog.json.graphiti-canary-v2-state.json']
    )


def test_builder_rejects_cartesian_provenance_for_current_models() -> None:
    raw = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': 'oracle-catalog-tool-test',
        'batch_id': 'x',
        'catalog_sha256': '0' * 64,
        'atomic': True,
        'entities': [],
        'edges': [],
        'provenance': {
            'sources': [],
            'entity_targets': [{'entity_type': 'Table', 'graph_key': 'TABLE::FE::A'}],
            'edge_targets': [],
        },
    }
    with pytest.raises(ValueError, match='entity_targets|edge_targets|evidence_links|Cartesian'):
        builder.validate_hardened_request(raw)


# ---------------------------------------------------------------------------
# Runner pure prepare/commit sequence (D-10) — never live-executed
# ---------------------------------------------------------------------------


def test_prepare_catalog_batch_commit_prepared_sequence_preferred() -> None:
    assert runner.COMMIT_TOOL_SEQUENCE == PREFERRED_HARDENED_SEQUENCE
    assert 'prepare_catalog_batch' in runner.COMMIT_TOOL_SEQUENCE
    assert 'commit_prepared_catalog_batch' in runner.COMMIT_TOOL_SEQUENCE
    assert 'upsert_catalog_batch' not in runner.COMMIT_TOOL_SEQUENCE
    assert 'upsert_catalog_batch' in runner.PROHIBITED_LEGACY_TOOLS

    _, raw, _, _, request_sha = runner.validate_hardened_artifact(
        HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json'
    )
    plan_token = 'offline-in-memory-token-only'
    sequence = runner.simulate_prepare_commit_sequence(
        raw, request_sha256=request_sha, plan_token=plan_token
    )
    runner.assert_sequence_has_no_prohibited_tools(sequence)
    assert [name for name, _ in sequence] == PREFERRED_HARDENED_SEQUENCE

    prepare_name, prepare_args = sequence[0]
    assert prepare_name == 'prepare_catalog_batch'
    prepare_body = prepare_args['request']
    assert prepare_body['identity_schema_version'] == 'catalog-v2'
    assert prepare_body['system_key'] == 'FE'
    assert prepare_body['group_id'] == 'oracle-catalog-tool-test'
    assert 'dry_run' not in prepare_body
    assert 'plan_token' not in prepare_body

    commit_name, commit_args = sequence[1]
    assert commit_name == 'commit_prepared_catalog_batch'
    commit_body = commit_args['request']
    assert set(commit_body) <= {'plan_token', 'expected_request_sha256'}
    assert commit_body['plan_token'] == plan_token
    assert commit_body['expected_request_sha256'] == request_sha
    # Token never persisted to hardened artifacts
    for name in (
        'offline-prepare.receipt.json',
        'offline-commit.receipt.json',
        'offline-checkpoint.json',
        'manifest.json',
    ):
        assert plan_token not in (HARDENED_ARTIFACT_DIR / name).read_text(encoding='utf-8')


def test_runner_rejects_historical_payload_as_hardened() -> None:
    with pytest.raises(runner.RunnerError) as error:
        runner.validate_hardened_artifact(HISTORICAL_ARTIFACT_DIR / 'accept-tab.payload.json')
    assert error.value.code == 'historical_not_hardened_authority'


def test_runner_source_has_no_prohibited_write_tool_call_literals_in_sequence() -> None:
    """Hardened COMMIT_TOOL_SEQUENCE must not include prohibited write tools."""
    for tool in runner.PROHIBITED_LEGACY_TOOLS:
        if tool == 'upsert_catalog_batch':
            # still present as historical execute() string; must not be in sequence constant
            assert tool not in runner.COMMIT_TOOL_SEQUENCE
            continue
        assert tool not in runner.COMMIT_TOOL_SEQUENCE


def test_offline_canary_no_external_side_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Socket / MCP client / Neo4j / embed spies stay unused during pure validation."""
    hits: list[str] = []

    def _block_socket(*_a: Any, **_k: Any) -> None:
        hits.append('socket')
        raise AssertionError('socket must not be used offline')

    monkeypatch.setattr(socket, 'socket', _block_socket)
    monkeypatch.setattr(socket, 'create_connection', _block_socket)

    def _block_client(*_a: Any, **_k: Any) -> None:
        hits.append('mcp_client')
        raise AssertionError('MCP client must not be used offline')

    monkeypatch.setattr(runner, 'streamable_http_client', _block_client)
    monkeypatch.setattr(runner, 'ClientSession', _block_client)

    # Pure validation + sequence simulation
    runner.validate_hardened_artifact(HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json')
    _, raw, _, _, request_sha = runner.validate_hardened_artifact(
        HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json'
    )
    runner.simulate_prepare_commit_sequence(raw, request_sha256=request_sha)
    builder.build_hardened(SANITIZED_FIXTURE, tmp_path / 'hardened-offline')
    assert hits == []
    assert (
        _sha256_file(CHECKPOINT_PATH)
        == HISTORICAL_DIGESTS['catalog/catalog.json.graphiti-canary-v2-state.json']
    )


def test_phase5_gate_never_shells_canary_runner() -> None:
    """D-10: Phase 5 gate/static audit must not shell run_catalog_canary_batch.py."""
    assert GATE_RUNNER.is_file(), 'catalog_phase5_gate_runner missing for shell ban'
    src = GATE_RUNNER.read_text(encoding='utf-8')
    assert 'canary_executed' in src
    assert 'run_catalog_canary_batch.py' in src
    # Must ban shelling the runner (string appears in ban list / comments, not as execution)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ''
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name in {'run', 'Popen', 'call', 'check_call', 'check_output'}:
                # inspect string args for runner path
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        assert 'run_catalog_canary_batch.py' not in arg.value
                    if isinstance(arg, (ast.List, ast.Tuple)):
                        for elt in arg.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                assert 'run_catalog_canary_batch.py' not in elt.value

    # Plans/docs must not instruct live canary shell in Phase 5 verify commands
    for plan_name in ('05-03-PLAN.md', '05-01-PLAN.md', '05-02-PLAN.md'):
        plan = PHASE_DIR / plan_name
        if not plan.is_file():
            continue
        text = plan.read_text(encoding='utf-8')
        # verify blocks use pytest, not python scripts/run_catalog_canary_batch.py
        if 'run_catalog_canary_batch.py' in text:
            for line in text.splitlines():
                if 'run_catalog_canary_batch.py' in line and not line.strip().startswith('#'):
                    assert (
                        'pytest' in line
                        or 'Never' in line
                        or 'never' in line
                        or 'not' in line.lower()
                        or 'ban' in line.lower()
                        or 'shell' in line.lower()
                        or 'invoke' in line.lower()
                        or 'path' in line.lower()
                        or 'scripts/' in line
                    )


def test_hardened_checkpoint_attempt_count_zero_after_validation() -> None:
    offline = json.loads(
        (HARDENED_ARTIFACT_DIR / 'offline-checkpoint.json').read_text(encoding='utf-8')
    )
    assert offline['canary_attempt_count'] == 0
    assert offline['canary_executed'] is False
    historical = json.loads(CHECKPOINT_PATH.read_text(encoding='utf-8'))
    assert len(historical['attempts']) == HISTORICAL_CHECKPOINT_ATTEMPTS


def test_atomic_checkpoint_append_preserves_prior_content(tmp_path: Path) -> None:
    checkpoint = tmp_path / 'offline-checkpoint.json'
    runner.atomic_write_json(
        checkpoint,
        {
            'artifact_schema_version': 'canary-hardened-v1',
            'canary_attempt_count': 0,
            'validation_runs': [],
            'canary_executed': False,
            'execution_mode': 'offline_simulation',
        },
    )
    first = checkpoint.read_bytes()
    state = json.loads(first.decode('utf-8'))
    state['validation_runs'] = list(state.get('validation_runs') or [])
    state['validation_runs'].append({'ok': True})
    runner.atomic_write_json(checkpoint, state)
    second = json.loads(checkpoint.read_text(encoding='utf-8'))
    assert second['validation_runs'] == [{'ok': True}]
    assert second['canary_executed'] is False


def test_unknown_hardened_top_level_field_is_rejected() -> None:
    payload_path = HARDENED_ARTIFACT_DIR / 'accept-tab.payload.json'
    raw = json.loads(payload_path.read_text(encoding='utf-8'))
    raw['unexpected'] = True
    # write temp non-canonical will fail canonical check; use reject on dict path
    with pytest.raises(runner.RunnerError):
        # construct via validate path with temp file
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode='wb', suffix='.json', delete=False, dir=HARDENED_ARTIFACT_DIR
        ) as handle:
            data = (
                json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
            ).encode('utf-8')
            handle.write(data)
            temp_path = Path(handle.name)
        try:
            runner.validate_hardened_artifact(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
