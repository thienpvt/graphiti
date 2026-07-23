#!/usr/bin/env python3
"""Canonical staged Catalog-v2 Compose launcher; never runs the canary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import materialize_catalog_local_config as materializer  # pyright: ignore[reportMissingImports]  # noqa: E402
import run_catalog_canary_batch as runner  # pyright: ignore[reportMissingImports]  # noqa: E402

PUBLIC_ACTIONS = ('render', 'neo4j', 'bootstrap', 'mcp', 'status', 'inspect')
MUTATING_ACTIONS = PUBLIC_ACTIONS[:4]
STATE_SCHEMA = 'catalog-clean-room-launcher-state-v1'
FIXED_SUBPROCESS_ENV = (
    'COMPOSE_PROJECT_NAME',
    'COMPOSE_REMOVE_ORPHANS',
    'GRAPHITI_MCP_IMAGE',
    'LANG',
    'LC_ALL',
    'MCP_PORT',
    'NEO4J_BOLT_PORT',
    'NEO4J_DATABASE',
    'NEO4J_HTTP_PORT',
    'NEO4J_PASSWORD',
    'NEO4J_URI',
    'NEO4J_USER',
    'PATH',
    # Windows Docker CLI loads compose plugins from %USERPROFILE%\.docker\cli-plugins.
    # Bare allowlisted PATH cannot discover plugins without this host profile key.
    'USERPROFILE',
)
SINGLETON_OPTIONS = {
    '--project',
    '--run-id',
    '--state-dir',
    '--neo4j-http-port',
    '--neo4j-bolt-port',
    '--mcp-port',
    '--image',
    '--expected-image-id',
}
RUN_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


def compose_env(options: runner.ComposeOptions) -> dict[str, str]:
    construction = materializer.resolve_mcp_construction_inputs()
    userprofile = os.environ.get('USERPROFILE', '').strip()
    if not userprofile:
        # Non-Windows hosts ignore this key; Windows Docker plugin discovery requires it.
        userprofile = os.environ.get('HOME', '').strip() or os.path.expanduser('~')
    env = {
        'COMPOSE_PROJECT_NAME': options.project,
        'COMPOSE_REMOVE_ORPHANS': '0',
        'GRAPHITI_MCP_IMAGE': options.image,
        'LANG': 'C.UTF-8',
        'LC_ALL': 'C.UTF-8',
        'MCP_PORT': str(options.mcp_port),
        'NEO4J_BOLT_PORT': str(options.neo4j_bolt_port),
        'NEO4J_DATABASE': 'neo4j',
        'NEO4J_HTTP_PORT': str(options.neo4j_http_port),
        'NEO4J_PASSWORD': 'demodemo',
        'NEO4J_URI': 'bolt://neo4j:7687',
        'NEO4J_USER': 'neo4j',
        'PATH': os.defpath,
        'USERPROFILE': userprofile,
    }
    env.update({name: item.value for name, item in construction.items()})
    if set(env) != set(FIXED_SUBPROCESS_ENV) | set(materializer.MCP_CONSTRUCTION_INPUT_NAMES):
        raise runner.RunnerError(
            'execution_boundary_violation', 'launcher subprocess environment is not allowlisted'
        )
    return env


def verify_observed_image_id(options: runner.ComposeOptions, observed: list[str]) -> None:
    if not options.clean_room or options.expected_image_id is None:
        return
    if observed != [options.expected_image_id]:
        raise runner.RunnerError(
            'image_identity_mismatch', 'observed image ID is absent, ambiguous, or mismatched'
        )


def _subprocess(
    argv: list[str], options: runner.ComposeOptions, *, capture_output: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=runner.ROOT,
        env=compose_env(options),
        shell=False,
        check=True,
        capture_output=capture_output,
        text=True,
    )


def _run_compose(
    action: str, options: runner.ComposeOptions, *, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    argv = runner.compose_argv(action, options)
    runner.attest_host_compose_argv(argv, options)
    runner.host_side_execution_authority_digests()
    return _subprocess(argv, options, capture_output=capture_output)


def _docker_json(argv: list[str], options: runner.ComposeOptions) -> Any:
    result = _subprocess(argv, options)
    try:
        return json.loads(result.stdout or '[]')
    except json.JSONDecodeError as exc:
        raise runner.RunnerError('execution_boundary_violation', 'invalid Docker JSON') from exc


def _inspect_optional(kind: str, name: str, options: runner.ComposeOptions) -> list[dict[str, Any]]:
    result = subprocess.run(
        ['docker', kind, 'inspect', name],
        cwd=runner.ROOT,
        env=compose_env(options),
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return []
    try:
        raw = json.loads(result.stdout or '[]')
    except json.JSONDecodeError as exc:
        raise runner.RunnerError(
            'execution_boundary_violation', 'invalid Docker inspect JSON'
        ) from exc
    if not isinstance(raw, list) or any(not isinstance(row, dict) for row in raw):
        raise runner.RunnerError('execution_boundary_violation', 'invalid Docker inspect shape')
    return raw


def _local_image_id(options: runner.ComposeOptions) -> str:
    raw = _docker_json(['docker', 'image', 'inspect', options.image], options)
    observed: list[str] = []
    for row in raw:
        if isinstance(row, dict):
            image_id = row.get('Id')
            if isinstance(image_id, str):
                observed.append(image_id)
    verify_observed_image_id(options, observed)
    return observed[0]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _materializer_authority() -> tuple[dict[str, str], uuid.UUID, dict[str, Any]]:
    path = runner.ROOT / 'mcp_server/config/.catalog-local-authority'
    try:
        pairs = [line.split('=', 1) for line in path.read_text(encoding='ascii').splitlines()]
    except (OSError, ValueError) as exc:
        raise runner.RunnerError(
            'execution_attestation_missing', 'materializer authority missing'
        ) from exc
    if any(len(pair) != 2 for pair in pairs):
        raise runner.RunnerError('execution_attestation_invalid', 'materializer authority invalid')
    raw = dict(pairs)
    if set(raw) != {
        'project',
        'data_volume',
        'namespace',
        'construction_fields_fingerprint',
        'construction_fingerprint',
    }:
        raise runner.RunnerError('execution_attestation_invalid', 'materializer authority invalid')
    try:
        namespace = uuid.UUID(raw['namespace'])
    except ValueError as exc:
        raise runner.RunnerError(
            'execution_attestation_invalid', 'materializer authority invalid'
        ) from exc
    if str(namespace) != raw['namespace']:
        raise runner.RunnerError('execution_attestation_invalid', 'materializer authority invalid')
    try:
        construction = materializer.mcp_construction_receipt(
            materializer.resolve_mcp_construction_inputs(), namespace
        )
        fields_fingerprint = materializer.mcp_construction_fields_fingerprint(construction)
    except ValueError as exc:
        raise runner.RunnerError(
            'execution_attestation_invalid', 'MCP construction authority invalid'
        ) from exc
    if (
        raw['construction_fields_fingerprint'] != fields_fingerprint
        or raw['construction_fingerprint'] != construction['fingerprint']
    ):
        raise runner.RunnerError(
            'execution_attestation_mismatch', 'MCP construction authority changed'
        )
    return raw, namespace, construction


def _authority() -> dict[str, Any]:
    raw, namespace, construction = _materializer_authority()
    return {
        'project': raw['project'],
        'data_volume': raw['data_volume'],
        'namespace_fingerprint': hashlib.sha256(
            b'graphiti.catalog.nsfp.v1|' + namespace.bytes
        ).hexdigest()[:16],
        'construction': construction,
    }


def _state_files(state_dir: Path) -> list[Path]:
    return sorted(state_dir.glob('[0-9][0-9][0-9][0-9]-*.json')) if state_dir.is_dir() else []


def _load_state(state_dir: Path) -> dict[str, Any] | None:
    files = _state_files(state_dir)
    if not files:
        return None
    raw = runner.strict_json_load(files[-1])
    if not isinstance(raw, dict) or raw.get('schema_version') != STATE_SCHEMA:
        raise runner.RunnerError('launcher_state_invalid', 'launcher state is invalid')
    actions = raw.get('actions')
    if not isinstance(actions, list):
        raise runner.RunnerError('launcher_state_invalid', 'launcher ledger is invalid')
    expected = list(MUTATING_ACTIONS[: len(actions)])
    if [row.get('action') for row in actions if isinstance(row, dict)] != expected or [
        row.get('ordinal') for row in actions if isinstance(row, dict)
    ] != list(range(1, len(actions) + 1)):
        raise runner.RunnerError('launcher_state_invalid', 'launcher ledger is not contiguous')
    return raw


def _write_state_exclusive(state_dir: Path, state: dict[str, Any], action: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    ordinal = len(state['actions'])
    destination = state_dir / f'{ordinal:04d}-{action}.json'
    data = (
        json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
    ).encode()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=state_dir, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _base_binding(options: runner.ComposeOptions, run_id: str) -> dict[str, Any]:
    authority = _authority()
    resources = runner.compose_resource_identities(options.project)
    config = runner.ROOT / runner.COMPOSE_GENERATED_CONFIG
    digests = runner.host_side_execution_authority_digests()
    if (
        authority['project'] != options.project
        or authority['data_volume'] != resources['data_volume']
    ):
        raise runner.RunnerError(
            'execution_attestation_mismatch', 'materializer authority mismatch'
        )
    return {
        'schema_version': STATE_SCHEMA,
        'run_id': run_id,
        'project': options.project,
        'ports': {
            'neo4j_http': options.neo4j_http_port,
            'neo4j_bolt': options.neo4j_bolt_port,
            'mcp': options.mcp_port,
        },
        'image': options.image,
        'expected_image_id': options.expected_image_id,
        'resources': resources,
        'config_sha256': _sha256(config),
        'execution_map_sha256': runner.compute_execution_map_sha256(digests),
        'namespace_fingerprint': authority['namespace_fingerprint'],
        'construction': authority['construction'],
        'actions': [],
    }


def _require_binding(state: dict[str, Any], options: runner.ComposeOptions, run_id: str) -> None:
    current = _base_binding(options, run_id)
    for key in (
        'schema_version',
        'run_id',
        'project',
        'ports',
        'image',
        'expected_image_id',
        'resources',
        'config_sha256',
        'execution_map_sha256',
        'namespace_fingerprint',
        'construction',
    ):
        if state.get(key) != current[key]:
            raise runner.RunnerError(
                'launcher_state_mismatch', f'launcher state binding changed: {key}'
            )


def _append_state(
    state_dir: Path, state: dict[str, Any], action: str, evidence: dict[str, Any]
) -> None:
    expected = MUTATING_ACTIONS[len(state['actions'])] if len(state['actions']) < 4 else None
    if action != expected:
        raise runner.RunnerError('stage_order_violation', 'clean-room actions must be ordered')
    state['actions'].append({'ordinal': len(state['actions']) + 1, 'action': action, **evidence})
    _write_state_exclusive(state_dir, state, action)


def _require_all_absent(options: runner.ComposeOptions) -> dict[str, bool]:
    resources = runner.compose_resource_identities(options.project)
    checks = {
        'neo4j_container': not _inspect_optional(
            'container', resources['neo4j_container'], options
        ),
        'mcp_container': not _inspect_optional('container', resources['mcp_container'], options),
        'bootstrap_container': not _inspect_optional(
            'container', resources['bootstrap_container'], options
        ),
        'network': not _inspect_optional('network', resources['network'], options),
        'data_volume': not _inspect_optional('volume', resources['data_volume'], options),
        'logs_volume': not _inspect_optional('volume', resources['logs_volume'], options),
    }
    if not all(checks.values()):
        raise runner.RunnerError(
            'execution_boundary_violation', 'selected clean-room resource exists'
        )
    return checks


def _inspect_neo4j(options: runner.ComposeOptions) -> dict[str, Any]:
    resources = runner.compose_resource_identities(options.project)
    # Neo4j healthchecks start as starting; observe the same container until healthy.
    deadline = time.time() + 180.0
    last_error = 'Neo4j runtime binding is invalid'
    while time.time() < deadline:
        rows = _inspect_optional('container', resources['neo4j_container'], options)
        if len(rows) != 1:
            last_error = 'Neo4j container is absent or ambiguous'
            time.sleep(2.0)
            continue
        row = rows[0]
        labels = row.get('Config', {}).get('Labels', {})
        mounts = {item.get('Destination'): item.get('Name') for item in row.get('Mounts', [])}
        health = row.get('State', {}).get('Health', {}).get('Status')
        networks = set(row.get('NetworkSettings', {}).get('Networks', {}))
        if (
            labels.get('com.docker.compose.project') != options.project
            or labels.get('com.docker.compose.service') != 'neo4j'
            or mounts.get('/data') != resources['data_volume']
            or mounts.get('/logs') != resources['logs_volume']
            or resources['network'] not in networks
        ):
            raise runner.RunnerError('neo4j_observation_failed', 'Neo4j runtime binding is invalid')
        if health == 'healthy':
            return {'health': health, 'mounts': mounts, 'network': resources['network']}
        last_error = f'Neo4j health is {health!r}, waiting for healthy'
        time.sleep(2.0)
    raise runner.RunnerError('neo4j_observation_failed', last_error)


def _mcp_absent(options: runner.ComposeOptions) -> bool:
    return not _inspect_optional(
        'container', runner.compose_resource_identities(options.project)['mcp_container'], options
    )


def validate_mcp_container_authority(
    row: dict[str, Any],
    options: runner.ComposeOptions,
    *,
    construction_inputs: dict[str, materializer.MCPConstructionInput],
    namespace: uuid.UUID,
) -> dict[str, Any]:
    """Validate one Compose-created MCP container and return sanitized evidence."""

    image_id = row.get('Image')
    verify_observed_image_id(options, [image_id] if isinstance(image_id, str) else [])

    config = row.get('Config')
    if not isinstance(config, dict):
        raise runner.RunnerError(
            'mcp_observation_failed', 'MCP Compose authority configuration is invalid'
        )
    labels = config.get('Labels')
    if not isinstance(labels, dict):
        raise runner.RunnerError(
            'mcp_observation_failed', 'MCP Compose authority labels are invalid'
        )
    config_hash = labels.get('com.docker.compose.config-hash')
    config_files = labels.get('com.docker.compose.project.config_files')
    if (
        labels.get('com.docker.compose.project') != options.project
        or labels.get('com.docker.compose.service') != 'graphiti-mcp'
        or not isinstance(config_hash, str)
        or SHA256_RE.fullmatch(config_hash) is None
        or not isinstance(config_files, str)
        or not config_files
    ):
        raise runner.RunnerError(
            'mcp_observation_failed', 'MCP Compose authority labels are invalid'
        )
    expected_files = [
        (runner.ROOT / relative).resolve() for relative in runner.REQUIRED_COMPOSE_FILES
    ]
    try:
        observed_files = [Path(item).resolve() for item in config_files.split(',') if item]
    except (OSError, RuntimeError) as exc:
        raise runner.RunnerError(
            'mcp_observation_failed', 'MCP Compose authority files are invalid'
        ) from exc
    if observed_files != expected_files:
        raise runner.RunnerError(
            'mcp_observation_failed', 'MCP Compose authority files are invalid'
        )

    raw_environment = config.get('Env')
    if not isinstance(raw_environment, list) or not all(
        isinstance(item, str) and '=' in item for item in raw_environment
    ):
        raise runner.RunnerError(
            'mcp_observation_failed', 'MCP construction environment is invalid'
        )
    environment: dict[str, str] = {}
    for item in raw_environment:
        name, value = item.split('=', 1)
        if not name or name in environment:
            raise runner.RunnerError(
                'mcp_observation_failed', 'MCP construction environment is invalid'
            )
        environment[name] = value
    if tuple(construction_inputs) != materializer.MCP_CONSTRUCTION_INPUT_NAMES or any(
        environment.get(name) != construction_inputs[name].value
        for name in materializer.MCP_CONSTRUCTION_INPUT_NAMES
    ):
        raise runner.RunnerError(
            'mcp_observation_failed', 'MCP construction authority does not match'
        )

    construction = materializer.mcp_construction_receipt(construction_inputs, namespace)
    compose_files_bytes = json.dumps(
        [str(path) for path in observed_files], separators=(',', ':'), ensure_ascii=True
    ).encode('ascii')
    return {
        'observed_image_id': image_id,
        'compose_config_hash_fingerprint': hashlib.sha256(
            b'graphiti.catalog.compose-config-hash.v1|' + config_hash.encode('ascii')
        ).hexdigest(),
        'compose_files_fingerprint': hashlib.sha256(
            b'graphiti.catalog.compose-files.v1|' + compose_files_bytes
        ).hexdigest(),
        'construction': construction,
    }


def _inspect_mcp_authority(options: runner.ComposeOptions) -> dict[str, Any]:
    rows = _inspect_optional(
        'container', runner.compose_resource_identities(options.project)['mcp_container'], options
    )
    if len(rows) != 1:
        raise runner.RunnerError('mcp_observation_failed', 'MCP container is absent or ambiguous')
    _, namespace, _ = _materializer_authority()
    construction_inputs = materializer.resolve_mcp_construction_inputs()
    return validate_mcp_container_authority(
        rows[0],
        options,
        construction_inputs=construction_inputs,
        namespace=namespace,
    )


def run_compose(
    action: str,
    options: runner.ComposeOptions | None = None,
    *,
    state_dir: Path | None = None,
    run_id: str | None = None,
) -> subprocess.CompletedProcess[str]:
    selected = options or runner.ComposeOptions()
    if not selected.clean_room:
        return _run_compose(
            action, selected, capture_output=action in {'render', 'status', 'inspect'}
        )
    if state_dir is None or run_id is None or RUN_ID_RE.fullmatch(run_id) is None:
        raise runner.RunnerError(
            'launcher_state_invalid', 'clean-room state-dir and run-id required'
        )
    state = _load_state(state_dir)
    if action in {'status', 'inspect'}:
        if state is not None:
            _require_binding(state, selected, run_id)
        return _run_compose(action, selected, capture_output=True)
    if state is None:
        if action != 'render':
            raise runner.RunnerError('stage_prerequisite_missing', 'render state is required')
        state = _base_binding(selected, run_id)
        result = _run_compose('render', selected, capture_output=True)
        _append_state(state_dir, state, 'render', {'rendered': True})
        return result
    _require_binding(state, selected, run_id)
    if action == 'render':
        raise runner.RunnerError('launcher_state_exists', 'render state already exists')
    expected = MUTATING_ACTIONS[len(state['actions'])] if len(state['actions']) < 4 else None
    if action != expected:
        raise runner.RunnerError('stage_order_violation', 'clean-room actions must be ordered')
    if action == 'neo4j':
        absence = _require_all_absent(selected)
        result = _run_compose(action, selected)
        observed = _inspect_neo4j(selected)
        _append_state(state_dir, state, action, {'absent_before_start': absence, **observed})
        return result
    if action == 'bootstrap':
        image_id = _local_image_id(selected)
        neo4j = _inspect_neo4j(selected)
        if not _mcp_absent(selected):
            raise runner.RunnerError(
                'stage_prerequisite_missing', 'MCP must be absent before bootstrap'
            )
        result = _run_compose(action, selected, capture_output=True)
        try:
            schema = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise runner.RunnerError(
                'schema_bootstrap_failed', 'bootstrap output is invalid'
            ) from exc
        if (
            schema.get('classification') != 'PASSED_SCHEMA_BOOTSTRAP'
            or schema.get('pre_inspection', {}).get('matched') != 0
            or schema.get('pre_inspection', {}).get('expected') != 14
            or schema.get('post_inspection', {}).get('matched') != 14
            or schema.get('post_inspection', {}).get('expected') != 14
        ):
            raise runner.RunnerError(
                'schema_bootstrap_failed', 'bootstrap did not prove 0/14 to 14/14'
            )
        _append_state(
            state_dir,
            state,
            action,
            {
                'neo4j_health': neo4j['health'],
                'mcp_absent': True,
                'observed_image_id': image_id,
                'schema': {
                    'pre': '0/14',
                    'post': '14/14',
                    'classification': schema['classification'],
                },
            },
        )
        return result
    if action == 'mcp':
        if [row['action'] for row in state['actions']] != ['render', 'neo4j', 'bootstrap']:
            raise runner.RunnerError(
                'stage_prerequisite_missing', 'successful bootstrap state required'
            )
        _local_image_id(selected)
        _inspect_neo4j(selected)
        result = _run_compose(action, selected)
        observed = _inspect_mcp_authority(selected)
        _append_state(state_dir, state, action, observed)
        return result
    raise runner.RunnerError('execution_boundary_violation', 'unknown launcher action')


def _reject_duplicate_singletons(argv: list[str]) -> None:
    seen: set[str] = set()
    for token in argv:
        option = token.split('=', 1)[0]
        if option in SINGLETON_OPTIONS:
            if option in seen:
                raise runner.RunnerError('duplicate_option', f'duplicate launcher option: {option}')
            seen.add(option)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv[1:] if argv is None else argv)
    _reject_duplicate_singletons(raw)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=PUBLIC_ACTIONS)
    parser.add_argument('--clean-room', action='store_true')
    parser.add_argument('--project')
    parser.add_argument('--run-id')
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--neo4j-http-port', type=int, default=7474)
    parser.add_argument('--neo4j-bolt-port', type=int, default=7687)
    parser.add_argument('--mcp-port', type=int, default=8000)
    parser.add_argument('--image', default=runner.DEFAULT_MCP_IMAGE)
    parser.add_argument('--expected-image-id')
    args = parser.parse_args(raw)
    project = runner.resolve_compose_project(args.project, clean_room=args.clean_room)
    if args.clean_room and (args.run_id is None or args.state_dir is None):
        parser.error('--clean-room requires --run-id and --state-dir')
    if not args.clean_room and (args.run_id is not None or args.state_dir is not None):
        parser.error('--run-id and --state-dir require --clean-room')
    args.options = runner.ComposeOptions(
        project=project,
        clean_room=args.clean_room,
        neo4j_http_port=args.neo4j_http_port,
        neo4j_bolt_port=args.neo4j_bolt_port,
        mcp_port=args.mcp_port,
        image=args.image,
        expected_image_id=args.expected_image_id,
    )
    return args


def _sanitized_output(action: str, result: subprocess.CompletedProcess[str]) -> None:
    if action == 'render':
        print(json.dumps({'action': action, 'rendered': True}, sort_keys=True))
    elif action in {'status', 'inspect'}:
        try:
            raw: Any = json.loads(result.stdout or '[]')
        except json.JSONDecodeError as exc:
            raise runner.RunnerError(
                'execution_boundary_violation', 'invalid Compose JSON'
            ) from exc
        rows = raw if isinstance(raw, list) else [raw]
        allowed = ('Name', 'Service', 'State', 'Health', 'Image', 'Project')
        sanitized = [
            {key: row[key] for key in allowed if isinstance(row, dict) and key in row}
            for row in rows
        ]
        print(json.dumps({'action': action, 'services': sanitized}, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_compose(
        args.action,
        args.options,
        state_dir=args.state_dir.resolve() if args.state_dir else None,
        run_id=args.run_id,
    )
    _sanitized_output(args.action, result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
