"""Deterministic stdlib image secret scanner (AST + structured literals).

Authority symbol for IMAGE receipts: ``scan_tree`` (also ``scan_text``, ``scan_path``).

Python: only string Constant values in credential-like assignment/keyword contexts hit.
Declarations, references, annotations, and bare keys are non-hits.

Text/JSON/env/YAML: conservative literal extraction. Keys without secret values non-hit.

Token shapes:
  - OpenAI-like: ``sk-`` + long high-entropy alphanumeric body (not algorithm fragments)
  - Explicit non-hit family: ``sk-ecdsa…`` / short non-token ``sk-*`` forms
  - ``ghp_`` / ``ghp-`` and ``glpat-`` live shapes hit
  - ``GRAPHITI_CATALOG_UUID_NAMESPACE`` live UUID assignment hits

Binary / non-UTF8 at text trust boundaries: fail closed via ``ScanUnparseableError``.
Known binary extensions and content-classified binaries (ELF/magic/NUL/control density):
skip with ``binary_skipped`` path class (never silent empty; no whole-path waivers).
Short opaque non-UTF8 without binary evidence remains fail-closed.
Symlinks outside scan root are not followed.
Public ``ScanResult`` exposes counts and path classes only — never raw secret values.
"""

from __future__ import annotations

import ast
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# Credential-ish left-hand identifiers (Python + structured keys).
_CREDENTIAL_NAMES = frozenset(
    {
        'password',
        'api_key',
        'apikey',
        'access_token',
        'accesstoken',
        'refresh_token',
        'refreshtoken',
        'client_secret',
        'clientsecret',
    }
)

_PLACEHOLDER_VALUES = frozenset(
    {
        '',
        'none',
        'null',
        'nil',
        'ollama',
        'password',
        'secret',
        'token',
        'api_key',
        'apikey',
        'access_token',
        'client_secret',
        'neo4j',
        'demodemo',
        'your_password',
        'your_openai_api_key_here',
        'your_anthropic_key',
        'your_gemini_key',
        'your_groq_key',
        'sk-xxxxxxxx',
        'omitted',
        'redacted',
        'changeme',
        'changeit',
        'placeholder',
        'example',
        'sample',
        'default',
        'todo',
        'fixme',
        'xxx',
        'xxxx',
        '*****',
        '****',
        '***',
    }
)
# Synthetic/example markers — token presence marks docs/fixtures.
# Bare password/secret/token are exact-value only (see _PLACEHOLDER_VALUES), not
# tokens — otherwise "super-secret-password-value" would false-negative.
_PLACEHOLDER_MARKERS = frozenset(
    {
        'test',
        'testing',
        'fake',
        'mock',
        'dummy',
        'example',
        'sample',
        'placeholder',
        'changeme',
        'changeit',
        'your',
        'demo',
        'samplekey',
        'notasecret',
        'notreal',
        'replace',
        'redacted',
        'omitted',
    }
)
_IDENTIFIER_VALUE_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')
_OPAQUE_SECRET_RE = re.compile(r'^[A-Za-z0-9_./+=@%:-]{12,}$')

# Live OpenAI-like token: sk- + >=20 alnum body, not algorithm name fragments.
# sk-ecdsa… rejected by requiring body to be pure [A-Za-z0-9] of length >= 20
# (algorithm ids use hyphens after the first segment: sk-ecdsa-sha2-…).
_OPENAI_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{20,}(?![A-Za-z0-9])')
_GHP_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9_-])ghp[_-][A-Za-z0-9]{16,}(?![A-Za-z0-9])')
_GLPAT_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9_-])glpat-[A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])')
_NAMESPACE_UUID_RE = re.compile(
    r'(?i)\bGRAPHITI_CATALOG_UUID_NAMESPACE\s*=\s*[0-9a-f]{8}-[0-9a-f-]{27,}'
)
_ENV_LINE_RE = re.compile(
    r'(?i)^\s*(?:export\s+)?'
    r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<val>.+?)\s*$'
)
_YAML_LINE_RE = re.compile(r'(?i)^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<val>.+?)\s*$')
# Group 1 = full value including optional quotes (quote provenance for loose text).
_TEXT_ASSIGN_RE = re.compile(
    r'(?i)\b(?:password|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret)'
    r'\s*[:=]\s*((?P<q>[`"\'])(?P<quoted>(?:(?!(?P=q)).)*)(?P=q)|(?P<bare>[^\s#;,]+))'
)

_TEXT_SUFFIXES = frozenset(
    {
        '.py',
        '.pyi',
        '.json',
        '.yml',
        '.yaml',
        '.env',
        '.ini',
        '.cfg',
        '.conf',
        '.toml',
        '.txt',
        '.md',
        '.rst',
        '.xml',
        '.html',
        '.css',
        '.js',
        '.ts',
        '.sh',
        '.bash',
        '.zsh',
        '.ps1',
        '.bat',
        '.cmd',
        '.dockerfile',
        '.properties',
        '.csv',
        '.log',
    }
)
_TEXT_NAMES = frozenset(
    {
        'dockerfile',
        'makefile',
        'containerfile',
        '.env',
        '.env.example',
        'config',
        'config.json',
        'history.json',
    }
)
# Fixed format suffixes — extension classification, not path/dependency waivers.
_BINARY_SUFFIXES = frozenset(
    {
        '.png',
        '.jpg',
        '.jpeg',
        '.gif',
        '.webp',
        '.ico',
        '.so',
        '.dll',
        '.exe',
        '.bin',
        '.whl',
        '.gz',
        '.zip',
        '.tar',
        '.pyc',
        '.pyo',
        '.pyd',
        '.pkl',
        '.pickle',
        '.msgpack',
        '.rkyv',
        '.npy',
        '.npz',
        '.a',
        '.o',
        '.gpg',
        '.xz',
    }
)
_BINARY_SKIPPED = 'binary_skipped'
# Magic prefixes for extensionless ELF/archives/images common in image FS exports.
_BINARY_MAGIC_PREFIXES = (
    b'\x7fELF',  # ELF
    b'MZ',  # PE/DOS
    b'\x89PNG\r\n\x1a\n',
    b'\xff\xd8\xff',  # JPEG
    b'GIF87a',
    b'GIF89a',
    b'PK\x03\x04',  # ZIP/whl/jar
    b'\x1f\x8b',  # gzip
    b'BZ',  # bzip2 (short; also check length below)
    b'\xfd7zXZ\x00',  # xz
    b'#!',  # not binary — excluded by content path only after magic loop skip
    b'\x00\x61\x73\x6d',  # wasm
    b'rkyv',  # rkyv header fragment (best-effort)
)
# Opaque non-UTF8 shorter than this without magic/NUL density stays fail-closed.
_BINARY_MIN_OPAQUE_BYTES = 32
_BINARY_SAMPLE_BYTES = 8192
_BINARY_NUL_RATIO = 0.01
_BINARY_CONTROL_RATIO = 0.30


class ScanUnparseableError(ValueError):
    """Trust-boundary text claimed but not safely parseable as UTF-8 text."""

    def __init__(self, label: str, reason: str = 'unparseable') -> None:
        self.label = label
        self.reason = reason
        super().__init__(f'scan incomplete / unparseable: {label} ({reason})')


@dataclass(frozen=True)
class ScanResult:
    """Public scan outcome: counts and path classes only (no raw secrets)."""

    hit_count: int
    path_classes: frozenset[str] = field(default_factory=frozenset)

    def __repr__(self) -> str:
        classes = ','.join(sorted(self.path_classes))
        return f'ScanResult(hit_count={self.hit_count}, path_classes={{{classes}}})'

    def __str__(self) -> str:
        return repr(self)


def _norm_key(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())


def _is_credential_name(name: str) -> bool:
    n = _norm_key(name)
    if n in _CREDENTIAL_NAMES:
        return True
    # Tolerate common env-style suffixes: OPENAI_API_KEY, NEO4J_PASSWORD, …
    for suffix in (
        'password',
        'apikey',
        'accesstoken',
        'refreshtoken',
        'clientsecret',
    ):
        if n.endswith(suffix) and len(n) >= len(suffix):
            return True
    return False


def _is_placeholder(value: str) -> bool:
    """True for explicit synthetic/example/docs placeholders — not path waivers.

    Token/UUID detectors are independent and remain fail-closed for live shapes.
    Short credentials are NOT blanket-ignored — only exact allowlist, synthetic
    markers (test/mock/fake/…), or obvious repeated/sample forms.
    """
    v = value.strip().strip('`"\'')
    if not v:
        return True
    low = v.lower()
    if low in _PLACEHOLDER_VALUES:
        return True
    if low.startswith(
        ('your_', '${', '<', 'example_', 'sample_', 'test_', 'fake_', 'mock_', 'dummy_')
    ):
        return True
    if low.endswith(('_example', '_sample', '_test', '_fake', '_mock', '_dummy', '_placeholder')):
        return True
    # All-x / mask patterns (sk-xxxxxxxx already exact-matched above).
    if re.fullmatch(r'[xX*]{4,}', low) or re.fullmatch(r'(?:sk-|ghp[_-]|glpat-)?[xX*]{6,}', low):
        return True
    # Repeated short sample forms: aaaa, 1111, ababab, xxxyyy-style low entropy.
    if len(low) <= 16 and (
        re.fullmatch(r'(.)\1{3,}', low) or re.fullmatch(r'([a-z0-9]{1,4})\1{1,}', low)
    ):
        return True
    # Tokenize on non-alnum; any synthetic marker token → placeholder.
    # Exception: compound forms like "not-placeholder" / "real-not-secret" that
    # include a marker but are still real-looking opaque fixtures must not waive.
    tokens = {t for t in re.split(r'[^a-z0-9]+', low) if t}
    if tokens & _PLACEHOLDER_MARKERS and 'not' not in tokens and 'real' not in tokens:
        return True
    # Hyphen/underscore label that is only credential vocabulary (docs prose).
    compact = re.sub(r'[^a-z0-9]', '', low)
    return compact in {
        'password',
        'secret',
        'token',
        'apikey',
        'accesstoken',
        'clientsecret',
        'neo4j',
        'neo4jpassword',
        'openaikey',
    }


def _is_variable_reference(value: str) -> bool:
    """Unquoted identifier/attr chain — not a secret literal (e.g. config.password).

    Only for loose env/text where quote provenance is absent. Quoted values and
    AST/JSON string Constants must not use this path.
    """
    raw = value.strip()
    # Quoted value is a literal by syntax — never a variable reference.
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'", '`'}:
        return False
    v = raw.strip('`"\'')
    if not v or ' ' in v or '/' in v or '\\' in v:
        return False
    return bool(_IDENTIFIER_VALUE_RE.fullmatch(v))


def _is_literal_secret_value(value: str, *, require_quoted_or_opaque: bool = False) -> bool:
    """Credential assignment value is a real non-placeholder literal (not a name ref).

    When ``require_quoted_or_opaque`` (loose text), unquoted short alpha tokens
    without opaque shape are non-hits so docs prose does not fire.
    """
    if _is_placeholder(value):
        return False
    if _is_variable_reference(value):
        return False
    raw = value.strip()
    quoted = len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'", '`'}
    v = raw.strip('`"\'')
    if not v:
        return False
    opaque = bool(_OPAQUE_SECRET_RE.fullmatch(v)) or (len(v) >= 8 and not v.isalpha())
    if require_quoted_or_opaque:
        return quoted or opaque
    # Env/YAML line values: opaque shape or non-trivial mixed value.
    return opaque or len(v) >= 8


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return None
    return None


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_python_literals(text: str) -> list[str]:
    """Return hit classes from Python AST credential string literals only."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # Not valid Python — fall through to text scanners only.
        return []

    hits: list[str] = []

    def consider(name: str | None, value_node: ast.AST | None) -> None:
        if name is None or not _is_credential_name(name):
            return
        value = _const_str(value_node)
        if value is None:
            return
        # AST Constant is already a string literal by syntax — never treat as
        # identifier/var-ref. Only placeholder allowlist suppresses.
        if _is_placeholder(value):
            return
        hits.append('credential_literal')

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = node.value
            for target in node.targets:
                consider(_target_name(target), value)
        elif isinstance(node, ast.AnnAssign):
            consider(_target_name(node.target), node.value)
        elif isinstance(node, ast.keyword):
            consider(node.arg, node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # defaults aligned to trailing args
            args = node.args
            positional = list(args.posonlyargs) + list(args.args)
            defaults = list(args.defaults)
            if defaults:
                for arg, default in zip(positional[-len(defaults) :], defaults, strict=False):
                    consider(arg.arg, default)
            for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=False):
                if default is not None:
                    consider(arg.arg, default)
    return hits


def _scan_token_shapes(text: str) -> list[str]:
    hits: list[str] = []
    if _OPENAI_TOKEN_RE.search(text):
        hits.append('token_shape')
    if _GHP_TOKEN_RE.search(text):
        hits.append('token_shape')
    if _GLPAT_TOKEN_RE.search(text):
        hits.append('token_shape')
    return hits


def _scan_namespace_uuid(text: str) -> list[str]:
    return ['namespace_uuid'] if _NAMESPACE_UUID_RE.search(text) else []


def _value_from_structured(raw: str) -> str:
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
        v = v[1:-1]
    # Strip trailing inline comments for yaml-ish lines.
    if ' #' in v:
        v = v.split(' #', 1)[0].rstrip()
    return v


def _env_credential_hit(raw: str) -> bool:
    """True when a single KEY=VALUE string assigns a non-placeholder credential.

    Env/JSON nested Env values are literals by format — no variable-ref waiver.
    ``password=config.password`` hits; only placeholder allowlist suppresses.
    """
    match = _ENV_LINE_RE.match(raw.strip())
    if not match:
        return False
    key = match.group('key')
    val = _value_from_structured(match.group('val'))
    return _is_credential_name(key) and not _is_placeholder(val)


def _scan_json_data(data: object) -> list[str]:
    """Credential hits from JSON object keys and nested string KEY=VALUE literals.

    Docker config/history encode env as string arrays:
    ``{"Config":{"Env":["NEO4J_PASSWORD=secret","OPENAI_API_KEY=omitted"]}}``.
    """
    hits: list[str] = []
    for key, value in _iter_json_pairs(data):
        # JSON string values are literals by syntax (not env-style name refs).
        if _is_credential_name(str(key)) and isinstance(value, str) and not _is_placeholder(value):
            hits.append('credential_literal')
    for string in _iter_json_strings(data):
        if _env_credential_hit(string):
            hits.append('credential_literal')
    return hits


def _scan_json_literals(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped or stripped[0] not in '{[':
        return []
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    return _scan_json_data(data)


def _scan_env_lines(text: str) -> list[str]:
    """KEY=VALUE lines (env-like). Safe on Python source — annotations use ``:``."""
    hits: list[str] = []
    for line in text.splitlines():
        if _env_credential_hit(line):
            hits.append('credential_literal')
    return hits


def _scan_yaml_and_text_assign(text: str) -> list[str]:
    """YAML-ish ``key: value`` + loose assignment regex. Not for parseable Python.

    YAML line values are literals (like env/JSON) — non-placeholder hits.
    Loose ``_TEXT_ASSIGN_RE`` is the only path that requires quoted/opaque shape
    and suppresses identifier-looking unquoted refs.
    """
    hits: list[str] = []
    for line in text.splitlines():
        match = _YAML_LINE_RE.match(line)
        if not match:
            continue
        key = match.group('key')
        val = _value_from_structured(match.group('val'))
        if _is_credential_name(key) and not _is_placeholder(val):
            hits.append('credential_literal')
    for match in _TEXT_ASSIGN_RE.finditer(text):
        # Preserve quote provenance: quoted group keeps delimiters for literal check.
        if match.group('quoted') is not None:
            q = match.group('q')
            value = f'{q}{match.group("quoted")}{q}'
        else:
            value = (match.group('bare') or '').rstrip('`,;')
        # Loose text only: require quoted or opaque; suppress bare identifier refs.
        if not _is_literal_secret_value(value, require_quoted_or_opaque=True):
            continue
        hits.append('credential_literal')
    return hits


def _iter_json_pairs(data: object) -> Iterable[tuple[object, object]]:
    if isinstance(data, dict):
        for key, value in data.items():
            yield key, value
            yield from _iter_json_pairs(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_json_pairs(item)


def _iter_json_strings(data: object) -> Iterable[str]:
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for value in data.values():
            yield from _iter_json_strings(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_json_strings(item)


def _is_parseable_python(text: str) -> bool:
    try:
        ast.parse(text)
    except SyntaxError:
        return False
    return True


def _is_valid_json_payload(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _path_kind(path_hint: str | None) -> str:
    """Classify path_hint for exclusive parser dispatch.

    Returns one of: python | json | env | yaml | other | unknown.
    Explicit path kind is never overridden by content heuristics.
    """
    if not path_hint:
        return 'unknown'
    path = Path(path_hint)
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in {'.py', '.pyi'}:
        return 'python'
    if suffix == '.json' or name.endswith('.json'):
        return 'json'
    if suffix == '.env' or name in {'.env', '.env.example'} or name.endswith('.env'):
        return 'env'
    if suffix in {'.yaml', '.yml'}:
        return 'yaml'
    return 'other'


def _scan_json_literals_strict(text: str, *, label: str) -> list[str]:
    """Strict JSON for path-claimed .json — invalid JSON fails closed."""
    stripped = text.strip()
    if not stripped:
        raise ScanUnparseableError(label, 'json')
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ScanUnparseableError(label, 'json') from exc
    return _scan_json_data(data)


def scan_text(text: str, *, label: str, path_hint: str | None = None) -> ScanResult:
    """Scan a text blob. Never stores raw secret substrings in the result.

    Path-strict dispatch (path_hint wins over content ambiguity):
    - ``.py``/``.pyi``: AST credential Constants only; syntax error → fail closed
    - ``.json``: strict JSON parse; invalid JSON → fail closed
    - ``.env``: env KEY=VALUE parser only
    - ``.yaml``/``.yml``: yaml-ish line parser (+ loose assign)
    - unknown/other text: conservative structured fallback
    - no path_hint: JSON if valid payload, else AST if parseable Python, else fallback
    - Live token shapes + namespace UUID always apply
    """
    classes: list[str] = []
    kind = _path_kind(path_hint)
    boundary = path_hint or label

    if kind == 'python':
        if not _is_parseable_python(text):
            raise ScanUnparseableError(boundary, 'python-syntax')
        classes.extend(_scan_python_literals(text))
    elif kind == 'json':
        classes.extend(_scan_json_literals_strict(text, label=boundary))
    elif kind == 'env':
        classes.extend(_scan_env_lines(text))
    elif kind == 'yaml':
        classes.extend(_scan_yaml_and_text_assign(text))
    elif kind == 'other':
        # Explicit non-special text path: conservative multi-helper scan.
        classes.extend(_scan_json_literals(text))
        classes.extend(_scan_env_lines(text))
        classes.extend(_scan_yaml_and_text_assign(text))
    else:
        # No path_hint — content heuristics only (never invent a path claim).
        if _is_valid_json_payload(text):
            classes.extend(_scan_json_literals(text))
        elif _is_parseable_python(text):
            classes.extend(_scan_python_literals(text))
        else:
            classes.extend(_scan_env_lines(text))
            classes.extend(_scan_yaml_and_text_assign(text))

    classes.extend(_scan_token_shapes(text))
    classes.extend(_scan_namespace_uuid(text))
    _ = label  # label kept for call-site identity; never embed secret values
    unique = frozenset(classes)
    return ScanResult(hit_count=len(classes), path_classes=unique)


def _looks_like_text_path(path: Path) -> bool:
    name = path.name.lower()
    if name in _TEXT_NAMES or path.suffix.lower() in _TEXT_SUFFIXES:
        return True
    # Extensionless names often used for config/history export.
    return path.suffix == '' and name in {'config', 'history', 'manifest', 'labels'}


def _is_known_binary_path(path: Path) -> bool:
    return path.suffix.lower() in _BINARY_SUFFIXES


def _binary_skipped_result() -> ScanResult:
    return ScanResult(hit_count=0, path_classes=frozenset({_BINARY_SKIPPED}))


def _looks_like_binary_content(raw: bytes) -> bool:
    """Content-based binary classification (no path/dependency waivers).

    True for magic signatures, NUL density, or high non-text control density on
    a sufficiently large opaque sample. Short opaque blobs without evidence
    return False so callers can fail closed.
    """
    if not raw:
        return False
    sample = raw[:_BINARY_SAMPLE_BYTES]
    # Magic: skip shebang (text) and bare BZ (too short alone unless bzip2 full).
    for magic in _BINARY_MAGIC_PREFIXES:
        if magic == b'#!':
            continue
        if magic == b'BZ':
            if sample.startswith(b'BZh'):
                return True
            continue
        if sample.startswith(magic):
            return True
    # terminfo compiled entries often start with magic 0x011a / 0x021e (little-endian).
    if len(sample) >= 2 and sample[:2] in {b'\x1a\x01', b'\x1e\x02', b'\x01\x1a', b'\x02\x1e'}:
        return True
    nul_count = sample.count(b'\x00')
    if nul_count and (nul_count / len(sample)) >= _BINARY_NUL_RATIO:
        return True
    # Control bytes excluding tab/LF/CR.
    control = 0
    for byte in sample:
        if byte < 9 or byte == 11 or byte == 12 or (14 <= byte <= 31) or byte == 127:
            control += 1
    if len(sample) >= _BINARY_MIN_OPAQUE_BYTES and (control / len(sample)) >= _BINARY_CONTROL_RATIO:
        return True
    # High-bit density on longer non-UTF8 samples (msgpack/rkyv/terminfo bodies).
    if len(sample) >= _BINARY_MIN_OPAQUE_BYTES:
        high = sum(1 for byte in sample if byte >= 0x80)
        if (high / len(sample)) >= 0.40:
            return True
    return False


def _path_inside_root(path: Path, root: Path) -> bool:
    """True when path resolves inside root (blocks symlink escape)."""
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def scan_path(path: Path) -> ScanResult:
    """Scan one filesystem path. Text-claimed paths fail closed on non-UTF8."""
    path = Path(path)
    if not path.is_file():
        raise ScanUnparseableError(path.name, 'not a file')

    if _is_known_binary_path(path):
        return _binary_skipped_result()

    raw = path.read_bytes()
    text_claimed = _looks_like_text_path(path)
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        # Claimed source/config text never silently skips.
        if text_claimed:
            raise ScanUnparseableError(path.name, 'non-utf8') from exc
        # Extensionless ELF/terminfo/msgpack: content-classified binary → skip.
        if _looks_like_binary_content(raw):
            return _binary_skipped_result()
        # Short/opaque non-UTF8 without binary evidence: fail closed.
        raise ScanUnparseableError(path.name, 'non-utf8') from exc

    # Content-classified binary even when UTF-8-decodable (terminfo/control-heavy).
    # Text-claimed paths never skip — fail closed only on NUL/non-utf8 above.
    if not text_claimed and _looks_like_binary_content(raw):
        return _binary_skipped_result()

    # NUL-heavy payload after successful UTF-8 decode (rare; embedded NULs).
    if b'\x00' in raw[:_BINARY_SAMPLE_BYTES]:
        if text_claimed:
            raise ScanUnparseableError(path.name, 'binary-nul')
        if _looks_like_binary_content(raw):
            return _binary_skipped_result()
        raise ScanUnparseableError(path.name, 'binary-nul')

    return scan_text(text, label=path.name, path_hint=str(path))


def scan_tree(root: Path) -> ScanResult:
    """Walk a directory tree; aggregate hit counts and path classes only.

    Does not follow symlinks outside the scan root. Known binary skips record
    ``binary_skipped``; unknown non-UTF8 fails closed.
    """
    root = Path(root)
    if not root.exists():
        raise ScanUnparseableError(root.name, 'missing')
    if root.is_file():
        return scan_path(root)

    total = 0
    classes: set[str] = set()
    # os.walk(followlinks=False) — never traverse symlink directories.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        # Drop dir entries that resolve outside root (symlink escape).
        keep: list[str] = []
        for name in dirnames:
            child = current / name
            if child.is_symlink() or not _path_inside_root(child, root):
                continue
            keep.append(name)
        dirnames[:] = keep
        for name in sorted(filenames):
            path = current / name
            if path.is_symlink() and not _path_inside_root(path, root):
                continue
            if not path.is_file():
                continue
            result = scan_path(path)
            total += result.hit_count
            classes.update(result.path_classes)
    return ScanResult(hit_count=total, path_classes=frozenset(classes))


# Stable authority symbol alias for IMAGE receipt scanner_authority_symbol.
scan = scan_tree


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description='Deterministic image secret scanner')
    parser.add_argument('path', type=Path, help='file or directory to scan')
    args = parser.parse_args(argv)
    try:
        result = scan_tree(args.path) if args.path.is_dir() else scan_path(args.path)
    except ScanUnparseableError as exc:
        print(f'unparseable hit_count=-1 path_classes=unparseable reason={exc.reason}')
        return 2
    classes = ','.join(sorted(result.path_classes)) or '-'
    print(f'hit_count={result.hit_count} path_classes={classes}')
    return 1 if result.hit_count else 0


if __name__ == '__main__':
    raise SystemExit(main())
