#!/usr/bin/env python3
"""Materialize ignored catalog-local MCP config with one fixed UUID namespace."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'mcp_server/config/config-docker-neo4j.catalog-local.example.yaml'
DEFAULT_OUTPUT = ROOT / 'mcp_server/config/config-docker-neo4j.catalog-local.yaml'
DEFAULT_AUTHORITY = ROOT / 'mcp_server/config/.catalog-local-authority'
NAMESPACE_TOKEN = '${GRAPHITI_CATALOG_UUID_NAMESPACE}'
COMPOSE_PROJECT_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')


def materialize(source: Path, output: Path, namespace: str, *, overwrite: bool = False) -> None:
    try:
        parsed = uuid.UUID(namespace)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError('namespace must be a canonical UUID') from exc
    if str(parsed) != namespace.lower():
        raise ValueError('namespace must be a canonical UUID')
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise ValueError('source and output must differ')
    if output.exists() and not overwrite:
        raise FileExistsError('refusing to overwrite catalog-local config')
    text = source.read_text(encoding='utf-8')
    if text.count(NAMESPACE_TOKEN) != 1:
        raise ValueError('example must contain exactly one namespace token')
    raw = text.replace(NAMESPACE_TOKEN, namespace.lower()).replace('\r\n', '\n').replace('\r', '\n')
    data = re.sub(r'\n*\Z', '\n', raw).encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, output)
            temporary = None
        else:
            os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def namespace_fingerprint(namespace: uuid.UUID) -> str:
    return hashlib.sha256(b'graphiti.catalog.nsfp.v1|' + namespace.bytes).hexdigest()[:16]


def materialize_clean_room(
    source: Path, output: Path, authority: Path, *, project: str, data_volume: str
) -> str:
    if COMPOSE_PROJECT_RE.fullmatch(project) is None:
        raise ValueError('project must use Docker Compose project syntax')
    if data_volume != f'{project}_neo4j_data':
        raise ValueError('data volume must bind to the selected project')
    if output.exists() or authority.exists():
        raise FileExistsError('clean-room authority or config already exists')
    generated = uuid.uuid4()
    authority.parent.mkdir(parents=True, exist_ok=True)
    materialize(source, output, str(generated))
    try:
        with authority.open('x', encoding='ascii', newline='\n') as handle:
            handle.write(f'project={project}\ndata_volume={data_volume}\nnamespace={generated}\n')
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return namespace_fingerprint(generated)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--namespace')
    mode.add_argument('--clean-room', action='store_true')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--authority', type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument('--project')
    parser.add_argument('--data-volume')
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    if args.clean_room and args.overwrite:
        parser.error('--overwrite is forbidden in clean-room mode')
    if args.clean_room and (args.project is None or args.data_volume is None):
        parser.error('--clean-room requires --project and --data-volume')
    if not args.clean_room and (args.project is not None or args.data_volume is not None):
        parser.error('--project and --data-volume require --clean-room')
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.clean_room:
        materialize_clean_room(
            args.source,
            args.output,
            args.authority,
            project=args.project,
            data_volume=args.data_volume,
        )
    else:
        materialize(args.source, args.output, args.namespace, overwrite=args.overwrite)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
