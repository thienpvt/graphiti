#!/usr/bin/env python3
"""Materialize ignored catalog-local MCP config with one fixed UUID namespace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'mcp_server/config/config-docker-neo4j.catalog-local.example.yaml'
DEFAULT_OUTPUT = ROOT / 'mcp_server/config/config-docker-neo4j.catalog-local.yaml'
DEFAULT_AUTHORITY = ROOT / 'mcp_server/config/.catalog-local-authority'
NAMESPACE_TOKEN = '${GRAPHITI_CATALOG_UUID_NAMESPACE}'
COMPOSE_PROJECT_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')
MCP_CONSTRUCTION_AUTHORITY_SCHEMA = 'catalog-mcp-construction-authority-v1'
MCP_CONSTRUCTION_INPUT_NAMES = (
    'MODEL_NAME',
    'OLLAMA_EMBEDDER_API_URL',
    'OPENAI_API_KEY',
    'OPENAI_API_URL',
)
MCP_CONSTRUCTION_INPUT_DEFAULTS = {
    'MODEL_NAME': 'gpt-4.1-mini',
    'OLLAMA_EMBEDDER_API_URL': 'http://host.docker.internal:11434',
    'OPENAI_API_URL': 'https://api.openai.com/v1',
}
MCP_REQUIRED_CONSTRUCTION_INPUTS = ('OPENAI_API_KEY',)


class MCPConstructionInput:
    """One effective MCP construction input; values never enter receipts."""

    __slots__ = ('source', 'value')

    def __init__(self, *, value: str, source: str) -> None:
        self.value = value
        self.source = source


def resolve_mcp_construction_inputs(
    environ: Mapping[str, str] | None = None,
) -> dict[str, MCPConstructionInput]:
    """Resolve only the reviewed MCP construction allowlist.

    The OpenAI fields configure the already-authorized, construction-only LLM
    client. Catalog embeddings remain native Ollama. Ambient environment fields,
    including legacy OpenAI embedder variables, are never copied.
    """

    source = os.environ if environ is None else environ
    resolved: dict[str, MCPConstructionInput] = {}
    for name in MCP_CONSTRUCTION_INPUT_NAMES:
        value = source.get(name)
        if isinstance(value, str) and value.strip():
            resolved[name] = MCPConstructionInput(value=value, source='host_environment')
            continue
        if name in MCP_REQUIRED_CONSTRUCTION_INPUTS:
            raise ValueError(f'required MCP construction input is missing: {name}')
        default = MCP_CONSTRUCTION_INPUT_DEFAULTS.get(name)
        if default is None:
            raise RuntimeError(f'reviewed MCP construction default is missing: {name}')
        resolved[name] = MCPConstructionInput(value=default, source='reviewed_default')
    return resolved


def _construction_field_fingerprint(
    name: str, item: MCPConstructionInput, namespace: uuid.UUID
) -> str:
    payload = (
        b'graphiti.catalog.mcp-construction.v1\x00'
        + namespace.bytes
        + b'\x00'
        + name.encode('ascii')
        + b'\x00'
        + item.source.encode('ascii')
        + b'\x00'
        + item.value.encode('utf-8')
    )
    return hashlib.sha256(payload).hexdigest()


def mcp_construction_receipt(
    inputs: Mapping[str, MCPConstructionInput], namespace: uuid.UUID
) -> dict[str, object]:
    """Return presence/source/fingerprints only; never return input values."""

    if tuple(inputs) != MCP_CONSTRUCTION_INPUT_NAMES:
        raise ValueError('MCP construction inputs must match the exact allowlist')
    fields = [
        {
            'name': name,
            'present': True,
            'source': inputs[name].source,
            'fingerprint': _construction_field_fingerprint(name, inputs[name], namespace),
        }
        for name in MCP_CONSTRUCTION_INPUT_NAMES
    ]
    canonical = json.dumps(
        {
            'schema_version': MCP_CONSTRUCTION_AUTHORITY_SCHEMA,
            'fields': fields,
        },
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
    ).encode('ascii')
    return {
        'schema_version': MCP_CONSTRUCTION_AUTHORITY_SCHEMA,
        'allowlist': list(MCP_CONSTRUCTION_INPUT_NAMES),
        'fields': fields,
        'fingerprint': hashlib.sha256(canonical).hexdigest(),
    }


def mcp_construction_fields_fingerprint(receipt: Mapping[str, object]) -> str:
    """Bind the sanitized field presence/source surface independently of values."""

    raw_fields = receipt.get('fields')
    if (
        receipt.get('schema_version') != MCP_CONSTRUCTION_AUTHORITY_SCHEMA
        or receipt.get('allowlist') != list(MCP_CONSTRUCTION_INPUT_NAMES)
        or not isinstance(raw_fields, list)
        or len(raw_fields) != len(MCP_CONSTRUCTION_INPUT_NAMES)
    ):
        raise ValueError('MCP construction receipt fields are invalid')
    fields: list[dict[str, object]] = []
    for expected_name, field in zip(MCP_CONSTRUCTION_INPUT_NAMES, raw_fields, strict=True):
        if (
            not isinstance(field, dict)
            or field.get('name') != expected_name
            or field.get('present') is not True
            or field.get('source') not in {'host_environment', 'reviewed_default'}
        ):
            raise ValueError('MCP construction receipt fields are invalid')
        fields.append(
            {
                'name': expected_name,
                'present': True,
                'source': field['source'],
            }
        )
    canonical = json.dumps(fields, sort_keys=True, separators=(',', ':')).encode('ascii')
    return hashlib.sha256(canonical).hexdigest()


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
    source: Path,
    output: Path,
    authority: Path,
    *,
    project: str,
    data_volume: str,
    environ: Mapping[str, str] | None = None,
    namespace_factory: Callable[[], uuid.UUID] | None = None,
) -> str:
    if COMPOSE_PROJECT_RE.fullmatch(project) is None:
        raise ValueError('project must use Docker Compose project syntax')
    if data_volume != f'{project}_neo4j_data':
        raise ValueError('data volume must bind to the selected project')
    if output.exists() or authority.exists():
        raise FileExistsError('clean-room authority or config already exists')
    construction_inputs = resolve_mcp_construction_inputs(environ)
    generated = (namespace_factory or uuid.uuid4)()
    if not isinstance(generated, uuid.UUID) or generated.version != 4:
        raise ValueError('clean-room namespace factory must return UUIDv4')
    construction = mcp_construction_receipt(construction_inputs, generated)
    fields_fingerprint = mcp_construction_fields_fingerprint(construction)
    authority.parent.mkdir(parents=True, exist_ok=True)
    materialize(source, output, str(generated))
    try:
        with authority.open('x', encoding='ascii', newline='\n') as handle:
            handle.write(
                f'project={project}\n'
                f'data_volume={data_volume}\n'
                f'namespace={generated}\n'
                f'construction_fields_fingerprint={fields_fingerprint}\n'
                f'construction_fingerprint={construction["fingerprint"]}\n'
            )
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
