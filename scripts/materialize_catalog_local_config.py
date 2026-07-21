#!/usr/bin/env python3
"""Materialize ignored catalog-local MCP config with one fixed UUID namespace."""

from __future__ import annotations

import argparse
import os
import re
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'mcp_server/config/config-docker-neo4j.catalog-local.example.yaml'
DEFAULT_OUTPUT = ROOT / 'mcp_server/config/config-docker-neo4j.catalog-local.yaml'
NAMESPACE_TOKEN = '${GRAPHITI_CATALOG_UUID_NAMESPACE}'


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--overwrite', action='store_true')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    materialize(args.source, args.output, args.namespace, overwrite=args.overwrite)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
