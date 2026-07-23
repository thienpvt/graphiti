"""R3 acceptance tests for canonical MCP construction authority.

Unit only: no Docker, network, database, Ollama, or MCP process is started.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / 'scripts' / 'run_catalog_canary_batch.py'
LAUNCHER_PATH = ROOT / 'scripts' / 'run_catalog_canary_launcher.py'
MATERIALIZER_PATH = ROOT / 'scripts' / 'materialize_catalog_local_config.py'
OVERRIDE_PATH = ROOT / 'mcp_server/docker/docker-compose-neo4j.catalog-local.override.yml'
BASE_COMPOSE_PATH = ROOT / 'mcp_server/docker/docker-compose-neo4j.yml'
EXAMPLE_PATH = ROOT / 'mcp_server/config/config-docker-neo4j.catalog-local.example.yaml'

FIXED_NAMESPACE = uuid.UUID('12345678-1234-4678-9234-567812345678')
LOCAL_KEY = 'catalog-local-construction-key'
LOCAL_LLM_URL = 'http://local-llm.invalid/v1'
LOCAL_LLM_MODEL = 'local-construction-model'
LOCAL_OLLAMA_URL = 'http://local-ollama.invalid'


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_script('catalog_r3_runner_under_test', RUNNER_PATH)
sys.modules['run_catalog_canary_batch'] = runner
materializer = _load_script('catalog_r3_materializer_under_test', MATERIALIZER_PATH)
sys.modules['materialize_catalog_local_config'] = materializer
launcher = _load_script('catalog_r3_launcher_under_test', LAUNCHER_PATH)


def _host_environment() -> dict[str, str]:
    return {
        'OPENAI_API_KEY': LOCAL_KEY,
        'OPENAI_API_URL': LOCAL_LLM_URL,
        'MODEL_NAME': LOCAL_LLM_MODEL,
        'OLLAMA_EMBEDDER_API_URL': LOCAL_OLLAMA_URL,
        'OPENAI_EMBEDDER_API_KEY': 'must-not-pass',
        'OPENAI_EMBEDDER_API_URL': 'http://must-not-pass.invalid/v1',
        'UNRELATED_HOST_SECRET': 'must-not-pass',
    }


def test_materializer_selects_only_explicit_construction_allowlist() -> None:
    inputs = materializer.resolve_mcp_construction_inputs(_host_environment())

    assert tuple(inputs) == materializer.MCP_CONSTRUCTION_INPUT_NAMES
    assert set(inputs) == {
        'MODEL_NAME',
        'OLLAMA_EMBEDDER_API_URL',
        'OPENAI_API_KEY',
        'OPENAI_API_URL',
    }
    assert {item.source for item in inputs.values()} == {'host_environment'}
    assert 'OPENAI_EMBEDDER_API_KEY' not in inputs
    assert 'OPENAI_EMBEDDER_API_URL' not in inputs
    assert 'UNRELATED_HOST_SECRET' not in inputs

    with pytest.raises(ValueError, match='construction input'):
        materializer.resolve_mcp_construction_inputs({})
    with pytest.raises(ValueError, match='construction input'):
        materializer.resolve_mcp_construction_inputs({'OPENAI_API_KEY': ''})


def test_materializer_uses_reviewed_defaults_without_ambient_copy() -> None:
    inputs = materializer.resolve_mcp_construction_inputs({'OPENAI_API_KEY': LOCAL_KEY})

    assert inputs['OPENAI_API_KEY'].source == 'host_environment'
    for name in ('MODEL_NAME', 'OLLAMA_EMBEDDER_API_URL', 'OPENAI_API_URL'):
        assert inputs[name].source == 'reviewed_default'
        assert inputs[name].value == materializer.MCP_CONSTRUCTION_INPUT_DEFAULTS[name]


def test_construction_receipt_contains_presence_source_and_fingerprints_only() -> None:
    inputs = materializer.resolve_mcp_construction_inputs(_host_environment())
    receipt = materializer.mcp_construction_receipt(inputs, FIXED_NAMESPACE)
    encoded = json.dumps(receipt, sort_keys=True)

    assert receipt['schema_version'] == 'catalog-mcp-construction-authority-v1'
    assert receipt['allowlist'] == list(materializer.MCP_CONSTRUCTION_INPUT_NAMES)
    assert re.fullmatch(r'[0-9a-f]{64}', receipt['fingerprint'])
    assert [field['name'] for field in receipt['fields']] == list(
        materializer.MCP_CONSTRUCTION_INPUT_NAMES
    )
    assert all(field['present'] is True for field in receipt['fields'])
    assert all(field['source'] == 'host_environment' for field in receipt['fields'])
    assert all(re.fullmatch(r'[0-9a-f]{64}', field['fingerprint']) for field in receipt['fields'])

    for value in (LOCAL_KEY, LOCAL_LLM_URL, LOCAL_LLM_MODEL, LOCAL_OLLAMA_URL):
        assert value not in encoded
    assert 'must-not-pass' not in encoded


def test_clean_room_authority_binds_sanitized_construction_fingerprint(tmp_path: Path) -> None:
    output = tmp_path / 'catalog-local.yaml'
    authority = tmp_path / 'catalog-local.authority'
    fingerprint = materializer.materialize_clean_room(
        EXAMPLE_PATH,
        output,
        authority,
        project='clean-r3',
        data_volume='clean-r3_neo4j_data',
        environ=_host_environment(),
        namespace_factory=lambda: FIXED_NAMESPACE,
    )

    assert fingerprint == materializer.namespace_fingerprint(FIXED_NAMESPACE)
    raw = authority.read_text(encoding='ascii')
    pairs = dict(line.split('=', 1) for line in raw.splitlines())
    assert set(pairs) == {
        'project',
        'data_volume',
        'namespace',
        'construction_fields_fingerprint',
        'construction_fingerprint',
    }
    assert re.fullmatch(r'[0-9a-f]{64}', pairs['construction_fields_fingerprint'])
    assert re.fullmatch(r'[0-9a-f]{64}', pairs['construction_fingerprint'])
    for value in (LOCAL_KEY, LOCAL_LLM_URL, LOCAL_LLM_MODEL, LOCAL_OLLAMA_URL):
        assert value not in raw
    assert 'must-not-pass' not in raw


def test_launcher_subprocess_environment_is_minimal_and_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in _host_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'must-not-pass')
    monkeypatch.setenv('COMPOSE_FILE', 'must-not-pass.yml')
    monkeypatch.setenv('DOCKER_HOST', 'must-not-pass')

    env = launcher.compose_env(runner.ComposeOptions())

    for name in materializer.MCP_CONSTRUCTION_INPUT_NAMES:
        assert env[name] == _host_environment()[name]
    for name in (
        'AWS_SECRET_ACCESS_KEY',
        'COMPOSE_FILE',
        'DOCKER_HOST',
        'OPENAI_EMBEDDER_API_KEY',
        'OPENAI_EMBEDDER_API_URL',
        'UNRELATED_HOST_SECRET',
    ):
        assert name not in env
    assert set(env) == set(launcher.FIXED_SUBPROCESS_ENV) | set(
        materializer.MCP_CONSTRUCTION_INPUT_NAMES
    )


def _environment_names(raw: list[str]) -> set[str]:
    return {item.split('=', 1)[0] for item in raw}


def test_compose_resets_base_env_file_and_injects_only_allowlisted_inputs() -> None:
    base = yaml.safe_load(BASE_COMPOSE_PATH.read_text(encoding='utf-8'))
    assert base['services']['graphiti-mcp']['env_file']

    raw = OVERRIDE_PATH.read_text(encoding='utf-8')
    mcp_block = raw.split('  graphiti-mcp:\n', 1)[1].split('\n  catalog-bootstrap:\n', 1)[0]
    assert re.search(r'^    env_file: !reset \[\]$', mcp_block, re.MULTILINE)

    doc = yaml.safe_load(raw.replace('!reset ', ''))
    mcp_environment = doc['services']['graphiti-mcp']['environment']
    bootstrap_environment = doc['services']['catalog-bootstrap']['environment']
    mcp_names = _environment_names(mcp_environment)
    bootstrap_names = _environment_names(bootstrap_environment)
    construction_candidates = {
        name
        for name in mcp_names | bootstrap_names
        if name.startswith(('OPENAI_', 'OLLAMA_', 'MODEL_', 'EMBEDDER_'))
    }

    assert construction_candidates == set(materializer.MCP_CONSTRUCTION_INPUT_NAMES)
    assert set(materializer.MCP_CONSTRUCTION_INPUT_NAMES) <= mcp_names
    assert set(materializer.MCP_CONSTRUCTION_INPUT_NAMES).isdisjoint(bootstrap_names)
    assert doc['services']['graphiti-mcp']['env_file'] == []


def _canonical_row(inputs: dict[str, Any], options: Any) -> dict[str, Any]:
    config_files = ','.join(
        str((runner.ROOT / relative).resolve()) for relative in runner.REQUIRED_COMPOSE_FILES
    )
    return {
        'Image': options.expected_image_id,
        'Config': {
            'Env': [
                'PATH=/usr/local/bin:/usr/bin:/bin',
                *[f'{name}={item.value}' for name, item in inputs.items()],
            ],
            'Labels': {
                'com.docker.compose.project': options.project,
                'com.docker.compose.service': 'graphiti-mcp',
                'com.docker.compose.config-hash': 'a' * 64,
                'com.docker.compose.project.config_files': config_files,
            },
        },
    }


def test_r3_container_authority_requires_compose_labels_and_matching_inputs() -> None:
    options = runner.ComposeOptions(
        project='clean-r3',
        clean_room=True,
        image='graphiti-mcp:phase6-r3-test',
        expected_image_id='sha256:' + 'b' * 64,
    )
    inputs = materializer.resolve_mcp_construction_inputs(_host_environment())
    row = _canonical_row(inputs, options)
    receipt = launcher.validate_mcp_container_authority(
        row,
        options,
        construction_inputs=inputs,
        namespace=FIXED_NAMESPACE,
    )
    encoded = json.dumps(receipt, sort_keys=True)

    assert receipt['observed_image_id'] == options.expected_image_id
    assert re.fullmatch(r'[0-9a-f]{64}', receipt['compose_config_hash_fingerprint'])
    assert re.fullmatch(r'[0-9a-f]{64}', receipt['compose_files_fingerprint'])
    assert (
        receipt['construction']['fingerprint']
        == materializer.mcp_construction_receipt(inputs, FIXED_NAMESPACE)['fingerprint']
    )
    for value in (LOCAL_KEY, LOCAL_LLM_URL, LOCAL_LLM_MODEL, LOCAL_OLLAMA_URL):
        assert value not in encoded

    raw_replacement = _canonical_row(inputs, options)
    raw_replacement['Config']['Labels'] = {}
    with pytest.raises(runner.RunnerError, match='Compose authority'):
        launcher.validate_mcp_container_authority(
            raw_replacement,
            options,
            construction_inputs=inputs,
            namespace=FIXED_NAMESPACE,
        )

    wrong_environment = _canonical_row(inputs, options)
    wrong_environment['Config']['Env'] = [
        item.replace(LOCAL_KEY, 'different-value') for item in wrong_environment['Config']['Env']
    ]
    with pytest.raises(runner.RunnerError, match='construction'):
        launcher.validate_mcp_container_authority(
            wrong_environment,
            options,
            construction_inputs=inputs,
            namespace=FIXED_NAMESPACE,
        )