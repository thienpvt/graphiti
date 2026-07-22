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
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_catalog_canary_batch as runner  # pyright: ignore[reportMissingImports]  # noqa: E402

PUBLIC_ACTIONS = ('render', 'neo4j', 'bootstrap', 'mcp', 'status', 'inspect')
MUTATING_ACTIONS = PUBLIC_ACTIONS[:4]
STATE_SCHEMA = 'catalog-clean-room-launcher-state-v1'
AUTHORITY_ENV = {
    'COMPOSE_FILE',
    'COMPOSE_PROFILES',
    'COMPOSE_PROJECT_NAME',
    'COMPOSE_REMOVE_ORPHANS',
    'DOCKER_CONFIG',
    'DOCKER_CONTEXT',
    'DOCKER_HOST',
    'GRAPHITI_CATALOG_UUID_NAMESPACE',
    'GRAPHITI_MCP_IMAGE',
    'NEO4J_BOLT_PORT',
    'NEO4J_DATABASE',
    'NEO4J_HTTP_PORT',
    'NEO4J_PASSWORD',
    'NEO4J_URI',
    'NEO4J_USER',
    'MCP_PORT',
}
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
NAMESPACE_ENV_RE = re.compile(r'(?i)(?:^|__)UUID_NAMESPACE$')
RUN_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')


def compose_env(options: runner.ComposeOptions) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in AUTHORITY_ENV
        and not key.upper().startswith('COMPOSE_')
        and not NAMESPACE_ENV_RE.search(key)
    }
    env.update(
        {
            'COMPOSE_PROJECT_NAME': options.project,
            'COMPOSE_REMOVE_ORPHANS': '0',
            'GRAPHITI_MCP_IMAGE': options.image,
            'NEO4J_HTTP_PORT': str(options.neo4j_http_port),
            'NEO4J_BOLT_PORT': str(options.neo4j_bolt_port),
            'MCP_PORT': str(options.mcp_port),
            'NEO4J_URI': 'bolt://neo4j:7687',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'demodemo',
            'NEO4J_DATABASE': 'neo4j',
        }
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


def _authority() -> dict[str, str]:
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
    if set(raw) != {'project', 'data_volume', 'namespace'}:
        raise runner.RunnerError('execution_attestation_invalid', 'materializer authority invalid')
    try:
        namespace = uuid.UUID(raw['namespace'])
    except ValueError as exc:
        raise runner.RunnerError(
            'execution_attestation_invalid', 'materializer authority invalid'
        ) from exc
    if str(namespace) != raw['namespace']:
        raise runner.RunnerError('execution_attestation_invalid', 'materializer authority invalid')
    return {
        'project': raw['project'],
        'data_volume': raw['data_volume'],
        'namespace_fingerprint': hashlib.sha256(
            b'graphiti.catalog.nsfp.v1|' + namespace.bytes
        ).hexdigest()[:16],
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
    rows = _inspect_optional('container', resources['neo4j_container'], options)
    if len(rows) != 1:
        raise runner.RunnerError(
            'neo4j_observation_failed', 'Neo4j container is absent or ambiguous'
        )
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
        or health != 'healthy'
        or resources['network'] not in networks
    ):
        raise runner.RunnerError('neo4j_observation_failed', 'Neo4j runtime binding is invalid')
    return {'health': health, 'mounts': mounts, 'network': resources['network']}


def _mcp_absent(options: runner.ComposeOptions) -> bool:
    return not _inspect_optional(
        'container', runner.compose_resource_identities(options.project)['mcp_container'], options
    )


def _inspect_mcp_image(options: runner.ComposeOptions) -> str:
    rows = _inspect_optional(
        'container', runner.compose_resource_identities(options.project)['mcp_container'], options
    )
    observed: list[str] = []
    for row in rows:
        image_id = row.get('Image')
        if isinstance(image_id, str):
            observed.append(image_id)
    verify_observed_image_id(options, observed)
    return observed[0]


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
        image_id = _inspect_mcp_image(selected)
        _append_state(state_dir, state, action, {'observed_image_id': image_id})
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
