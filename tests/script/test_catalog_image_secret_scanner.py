"""RED/GREEN contract for deterministic image secret scanner."""

from __future__ import annotations

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'catalog_image_secret_scanner.py'


def _load():
    import sys

    name = 'catalog_image_secret_scanner'
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclass string/annotation resolution needs the module registered.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scanner = _load()


def _result_public_fields(result) -> None:
    """Public result exposes counts/classes only — never raw secret values."""
    assert hasattr(result, 'hit_count')
    assert hasattr(result, 'path_classes')
    blob = json.dumps(
        {
            'hit_count': result.hit_count,
            'path_classes': list(result.path_classes),
            'repr': repr(result),
            'str': str(result),
        }
    )
    forbidden = (
        'sk-liveOpenAITokenBodyWithEntropy01',
        'ghp_liveGitHubTokenBodyXXXX01',
        'glpat-liveGitLabTokenBody01xx',
        'super-secret-password-value',
        'real-client-secret-value',
        '11111111-2222-3333-4444-555555555555',
    )
    for secret in forbidden:
        assert secret not in blob


def test_declaration_and_reference_non_hit() -> None:
    text = '''
def connect(password: str, api_key: str, access_token: str, client_secret: str) -> None:
    """password api_key access_token client_secret mentioned only."""
    cfg = password
    other = self.api_key
    keys = ['password', 'api_key', 'access_token', 'client_secret']
    return keys
'''
    result = scanner.scan_text(text, label='decl')
    assert result.hit_count == 0
    _result_public_fields(result)


def test_python_name_attr_assignment_non_hit() -> None:
    """Valid Python Name/Attribute RHS must not trip env KEY=VALUE scanner."""
    # Exact coordinator reproduction (no spaces).
    bare = 'password=config.password\napi_key=self.api_key\n'
    result = scanner.scan_text(bare, label='python')
    assert result.hit_count == 0
    assert 'credential_literal' not in result.path_classes
    _result_public_fields(result)

    # Spaced + annotated forms via path_hint.
    spaced = """
password = config.password
api_key = self.api_key
access_token: str = other.token
client_secret: str = settings.client_secret
"""
    result = scanner.scan_text(spaced, label='python', path_hint='module.py')
    assert result.hit_count == 0
    assert 'credential_literal' not in result.path_classes
    _result_public_fields(result)

    # Literal still hits under same path claim.
    lit = 'password = "super-secret-password-value"\n'
    hit = scanner.scan_text(lit, label='python', path_hint='module.py')
    assert hit.hit_count >= 1
    assert 'credential_literal' in hit.path_classes
    _result_public_fields(hit)

    # Global token/namespace still apply on Python path.
    tok = 'x = "sk-liveOpenAITokenBodyWithEntropy01abcdef"\n'
    tok_hit = scanner.scan_text(tok, label='python', path_hint='module.py')
    assert tok_hit.hit_count >= 1
    assert 'token_shape' in tok_hit.path_classes


def test_literal_assignment_hit() -> None:
    text = """
password = "super-secret-password-value"
api_key = 'real-api-key-not-placeholder'
access_token = "tok-live-access-token-01"
refresh_token = "tok-live-refresh-token-01"
client_secret = "real-client-secret-value"
"""
    result = scanner.scan_text(text, label='assign')
    assert result.hit_count >= 5
    assert 'credential_literal' in result.path_classes
    _result_public_fields(result)


def test_placeholder_allowlist_non_hit() -> None:
    text = """
password = ""
password = "none"
password = "ollama"
password = "password"
password = "demodemo"
password = "your_password"
api_key = "your_openai_api_key_here"
api_key = "your_anthropic_key"
api_key = "your_gemini_key"
api_key = "your_groq_key"
api_key = "sk-xxxxxxxx"
api_key = "omitted"
api_key = "redacted"
api_key = "your_custom_placeholder"
api_key = "${OPENAI_API_KEY}"
api_key = "<REDACTED>"
"""
    result = scanner.scan_text(text, label='placeholders')
    assert result.hit_count == 0


def test_synthetic_example_placeholders_and_real_opaque_hit() -> None:
    """Semantic synthetic/example placeholders non-hit; real opaque still hits."""
    docs = """
password = "test-password"
api_key = "fake-api-key-for-docs"
client_secret = "dummy_secret_value"
access_token = "example-token-12345"
password = "mock-neo4j-password"
api_key = "sample_key_here"
"""
    result = scanner.scan_text(docs, label='docs', path_hint='README.md')
    assert result.hit_count == 0
    _result_public_fields(result)

    # Quoted real opaque credential still hits (no path waiver).
    real = 'password = "op4que-Cr3dential-Value-9x"\n'
    hit = scanner.scan_text(real, label='real', path_hint='settings.yaml')
    assert hit.hit_count >= 1
    assert 'credential_literal' in hit.path_classes
    _result_public_fields(hit)

    # Token/UUID detectors remain fail-closed (not weakened by placeholders).
    tok = 'x=sk-liveOpenAITokenBodyWithEntropy01abcdef\n'
    assert scanner.scan_text(tok, label='tok').hit_count >= 1
    ns = 'GRAPHITI_CATALOG_UUID_NAMESPACE=11111111-2222-3333-4444-555555555555\n'
    assert scanner.scan_text(ns, label='ns').hit_count >= 1


def test_openai_like_token_shape_hit() -> None:
    text = 'token=sk-liveOpenAITokenBodyWithEntropy01abcdef'
    result = scanner.scan_text(text, label='openai-token')
    assert result.hit_count >= 1
    assert 'token_shape' in result.path_classes
    _result_public_fields(result)


def test_ghp_and_glpat_token_shape_hit() -> None:
    text = 'a=ghp_liveGitHubTokenBodyXXXX01\nb=glpat-liveGitLabTokenBody01xx'
    result = scanner.scan_text(text, label='forge-tokens')
    assert result.hit_count >= 2
    assert 'token_shape' in result.path_classes
    _result_public_fields(result)


def test_sk_ecdsa_algorithm_non_hit() -> None:
    text = """
algorithm = "sk-ecdsa-sha2-nistp256"
curve = 'sk-ecdsa'
# HostKeyAlgorithms sk-ecdsa-sha2-nistp256,ssh-ed25519
"""
    result = scanner.scan_text(text, label='sk-ecdsa')
    assert result.hit_count == 0


def test_namespace_uuid_hit() -> None:
    text = 'GRAPHITI_CATALOG_UUID_NAMESPACE=11111111-2222-3333-4444-555555555555'
    result = scanner.scan_text(text, label='namespace')
    assert result.hit_count >= 1
    assert 'namespace_uuid' in result.path_classes
    _result_public_fields(result)


def test_structured_config_literals_hit_and_keys_alone_do_not() -> None:
    keys_only = '{"password": null, "api_key": "", "access_token": "omitted"}'
    hit_json = '{"password": "super-secret-password-value", "name": "svc"}'
    env_hit = 'CLIENT_SECRET=real-client-secret-value\nNAME=demo'
    yaml_hit = 'api_key: real-api-key-not-placeholder\nname: demo'
    keys_only_result = scanner.scan_text(keys_only, label='keys-only', path_hint='cfg.json')
    assert keys_only_result.hit_count == 0
    for text, label, hint in (
        (hit_json, 'json-hit', 'cfg.json'),
        (env_hit, 'env-hit', 'secrets.env'),
        (yaml_hit, 'yaml-hit', 'settings.yaml'),
    ):
        result = scanner.scan_text(text, label=label, path_hint=hint)
        assert result.hit_count >= 1
        assert 'credential_literal' in result.path_classes
        _result_public_fields(result)


def test_public_entrypoint_json_env_yaml_path_regression(tmp_path: Path) -> None:
    """Public scan_text/scan_path/scan_tree/scan cover JSON+env+YAML via path_hint."""
    for name in ('scan_text', 'scan_path', 'scan_tree', 'scan'):
        assert callable(getattr(scanner, name))

    hit_json = '{"password": "super-secret-password-value", "name": "svc"}'
    env_body = 'CLIENT_SECRET=real-client-secret-value\nNAME=demo'
    yaml_body = 'api_key: real-api-key-not-placeholder\nname: demo'

    # path_hint proves structured helpers for each trust boundary.
    json_text = scanner.scan_text(hit_json, label='json', path_hint='cfg.json')
    env_text = scanner.scan_text(env_body, label='env', path_hint='secrets.env')
    yaml_text = scanner.scan_text(yaml_body, label='yaml', path_hint='settings.yaml')
    assert json_text.hit_count >= 1 and 'credential_literal' in json_text.path_classes
    assert env_text.hit_count >= 1 and 'credential_literal' in env_text.path_classes
    assert yaml_text.hit_count >= 1 and 'credential_literal' in yaml_text.path_classes
    for result in (json_text, env_text, yaml_text):
        _result_public_fields(result)

    # Same env body with .py path_hint is AST-only: RHS is Name/BinOp, not str Constant.
    env_as_py = scanner.scan_text(env_body, label='env-as-py', path_hint='module.py')
    assert env_as_py.hit_count == 0
    assert 'credential_literal' not in env_as_py.path_classes

    root = tmp_path / 'entry'
    root.mkdir()
    (root / 'cfg.json').write_text(hit_json + '\n', encoding='utf-8')
    (root / 'secrets.env').write_text(env_body + '\n', encoding='utf-8')
    (root / 'settings.yaml').write_text(yaml_body + '\n', encoding='utf-8')
    (root / 'clean.json').write_text(
        '{"password": "omitted", "api_key": "", "access_token": null}\n',
        encoding='utf-8',
    )

    json_hit = scanner.scan_path(root / 'cfg.json')
    env_hit = scanner.scan_path(root / 'secrets.env')
    yaml_hit = scanner.scan_path(root / 'settings.yaml')
    clean_hit = scanner.scan_path(root / 'clean.json')
    assert json_hit.hit_count >= 1
    assert env_hit.hit_count >= 1
    assert yaml_hit.hit_count >= 1
    assert clean_hit.hit_count == 0
    assert 'credential_literal' in json_hit.path_classes
    assert 'credential_literal' in env_hit.path_classes
    assert 'credential_literal' in yaml_hit.path_classes
    for result in (json_hit, env_hit, yaml_hit, clean_hit):
        _result_public_fields(result)

    tree = scanner.scan_tree(root)
    assert tree.hit_count >= 3
    assert 'credential_literal' in tree.path_classes
    _result_public_fields(tree)

    alias = scanner.scan(root)
    assert alias.hit_count == tree.hit_count
    assert alias.path_classes == tree.path_classes


def test_docker_config_env_array_json_nested_string_hit(tmp_path: Path) -> None:
    """Docker config/history JSON Env string arrays: hit secret, skip placeholder."""
    payload = {
        'Config': {
            'Env': [
                'NEO4J_PASSWORD=super-secret-password-value',
                'OPENAI_API_KEY=omitted',
                'NAME=demo',
            ]
        }
    }
    text = json.dumps(payload)
    result = scanner.scan_text(text, label='docker-config', path_hint='config.json')
    assert result.hit_count == 1
    assert 'credential_literal' in result.path_classes
    _result_public_fields(result)

    path = tmp_path / 'config.json'
    path.write_text(text + '\n', encoding='utf-8')
    path_result = scanner.scan_path(path)
    assert path_result.hit_count == 1
    assert 'credential_literal' in path_result.path_classes
    _result_public_fields(path_result)

    # Placeholder-only env array is non-hit.
    clean = json.dumps({'Config': {'Env': ['OPENAI_API_KEY=omitted', 'NAME=demo']}})
    clean_result = scanner.scan_text(clean, label='docker-clean', path_hint='history.json')
    assert clean_result.hit_count == 0


def test_binary_skip_class_and_unknown_non_utf8_fail_closed(tmp_path: Path) -> None:
    """Known binary + content-classified ELF/terminfo → binary_skipped; short opaque fail-closed."""
    bin_root = tmp_path / 'bin'
    bin_root.mkdir()
    png = bin_root / 'icon.png'
    png.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\xff\xfe')
    skipped = scanner.scan_path(png)
    assert skipped.hit_count == 0
    assert 'binary_skipped' in skipped.path_classes
    _result_public_fields(skipped)

    # Extensionless ELF magic → content binary_skipped (no path waiver).
    elf = bin_root / 'ld-linux-x86-64'
    elf.write_bytes(b'\x7fELF' + b'\x00' * 60 + bytes(range(256)) * 2)
    elf_result = scanner.scan_path(elf)
    assert elf_result.hit_count == 0
    assert 'binary_skipped' in elf_result.path_classes

    # Extensionless terminfo-like compiled entry.
    terminfo = bin_root / 'xterm-256color'
    terminfo.write_bytes(b'\x1e\x02' + bytes([i % 256 for i in range(128)]))
    ti_result = scanner.scan_path(terminfo)
    assert ti_result.hit_count == 0
    assert 'binary_skipped' in ti_result.path_classes

    tree = scanner.scan_tree(bin_root)
    assert tree.hit_count == 0
    assert 'binary_skipped' in tree.path_classes
    _result_public_fields(tree)

    # Short opaque non-UTF8 without magic/NUL density → fail closed.
    unknown = tmp_path / 'blob.dat'
    unknown.write_bytes(b'\xff\xfe\xfd\xfc')
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_path(unknown)

    # Text-claimed source/config remains fail-closed on non-UTF8.
    bad_py = tmp_path / 'mod.py'
    bad_py.write_bytes(b'password = "\xff\xfe"\n')
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_path(bad_py)
    bad_json = tmp_path / 'cfg.json'
    bad_json.write_bytes(b'{"password": "\xff\xfe"}')
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_path(bad_json)

    # Tree with short opaque non-UTF8 fails closed (no silent pass).
    mixed = tmp_path / 'mixed'
    mixed.mkdir()
    (mixed / 'icon.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    (mixed / 'blob.dat').write_bytes(b'\xff\xfe\xfd\xfc')
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_tree(mixed)


def test_pkl_msgpack_suffix_binary_skipped(tmp_path: Path) -> None:
    """Fixed format suffixes (.pkl/.msgpack) → binary_skipped; text-claimed still fail-closed."""
    pkl = tmp_path / 'model.pkl'
    pkl.write_bytes(b'\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x08password')
    pkl_result = scanner.scan_path(pkl)
    assert pkl_result.hit_count == 0
    assert 'binary_skipped' in pkl_result.path_classes
    _result_public_fields(pkl_result)

    msgpack = tmp_path / 'cache.msgpack'
    msgpack.write_bytes(b'\x82\xa8password\xa6secret\xa7api_key\xabsk-livebody')
    mp_result = scanner.scan_path(msgpack)
    assert mp_result.hit_count == 0
    assert 'binary_skipped' in mp_result.path_classes
    _result_public_fields(mp_result)

    # Text-claimed non-UTF8 remains fail-closed (suffix set is not a path waiver).
    bad_py = tmp_path / 'mod.py'
    bad_py.write_bytes(b'password = "\xff\xfe"\n')
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_path(bad_py)


def test_scan_tree_skips_symlink_escape(tmp_path: Path) -> None:
    """Symlinks resolving outside scan root must not be followed."""
    root = tmp_path / 'root'
    outside = tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    secret = outside / 'leak.env'
    secret.write_text('NEO4J_PASSWORD=super-secret-password-value\n', encoding='utf-8')
    (root / 'safe.py').write_text('x = 1\n', encoding='utf-8')
    link = root / 'escape.env'
    try:
        link.symlink_to(secret)
    except OSError as exc:
        pytest.skip(f'symlink not available: {exc}')

    result = scanner.scan_tree(root)
    assert result.hit_count == 0
    assert 'credential_literal' not in result.path_classes
    _result_public_fields(result)


def test_unparseable_trust_boundary_fail_closed(tmp_path: Path) -> None:
    binary = tmp_path / 'config.json'
    binary.write_bytes(b'{"password": "\xff\xfe secret"}')
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_path(binary)

    # Text-claimed .py with broken syntax: fail closed (no silent regex pass).
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_text(
            'password = !!!not-python\n',
            label='broken-py',
            path_hint='module.py',
        )

    broken = tmp_path / 'broken.py'
    broken.write_text('password = !!!not-python\n', encoding='utf-8')
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_path(broken)

    # Invalid JSON at .json path: fail closed (no regex fallback).
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_text(
            '{password: not-json, api_key: x}',
            label='bad-json',
            path_hint='cfg.json',
        )
    bad_json = tmp_path / 'bad.json'
    bad_json.write_text('{password: not-json}\n', encoding='utf-8')
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_path(bad_json)

    # Env/YAML values are literals: config.password is a non-placeholder string hit.
    # Variable-ref suppression is Python-AST-only (Name/Attribute RHS, not Constant).
    env_like = 'password=config.password\napi_key=self.api_key\n'
    env_ref = scanner.scan_text(env_like, label='env', path_hint='secrets.env')
    assert env_ref.hit_count >= 2
    assert 'credential_literal' in env_ref.path_classes
    py_non_hit = scanner.scan_text(env_like, label='py', path_hint='module.py')
    assert py_non_hit.hit_count == 0
    assert 'credential_literal' not in py_non_hit.path_classes
    # Opaque env assignment still hits.
    env_lit = 'password=op4que-Cr3dential-Value-9x\n'
    env_hit = scanner.scan_text(env_lit, label='env-lit', path_hint='secrets.env')
    assert env_hit.hit_count >= 1
    assert 'credential_literal' in env_hit.path_classes


def test_scan_tree_counts_and_classes_only(tmp_path: Path) -> None:
    clean = tmp_path / 'clean'
    dirty = tmp_path / 'dirty'
    clean.mkdir()
    dirty.mkdir()
    (clean / 'mod.py').write_text(
        'def f(password: str, api_key: str) -> str:\n    return password\n',
        encoding='utf-8',
    )
    (clean / 'cfg.json').write_text('{"password": "omitted", "api_key": ""}\n', encoding='utf-8')
    (dirty / 'mod.py').write_text('password = "super-secret-password-value"\n', encoding='utf-8')
    (dirty / 'tok.env').write_text(
        'KEY=sk-liveOpenAITokenBodyWithEntropy01abcdef\n', encoding='utf-8'
    )

    clean_result = scanner.scan_tree(clean)
    assert clean_result.hit_count == 0
    _result_public_fields(clean_result)

    dirty_result = scanner.scan_tree(dirty)
    assert dirty_result.hit_count >= 2
    assert dirty_result.path_classes
    _result_public_fields(dirty_result)


def test_zero_hit_clean_fixture(tmp_path: Path) -> None:
    root = tmp_path / 'src'
    root.mkdir()
    (root / 'service.py').write_text(
        """
from typing import Optional

class Client:
    def __init__(self, api_key: Optional[str] = None, password: str = "password") -> None:
        self.api_key = api_key
        self.password = password

    def auth(self, access_token: str, client_secret: str = "omitted") -> dict:
        return {"access_token": access_token, "client_secret": client_secret}
""",
        encoding='utf-8',
    )
    (root / 'settings.yaml').write_text(
        'name: demo\napi_key: your_openai_api_key_here\npassword: demodemo\n',
        encoding='utf-8',
    )
    (root / 'hostkey.txt').write_text(
        'HostKeyAlgorithms sk-ecdsa-sha2-nistp256\n', encoding='utf-8'
    )
    result = scanner.scan_tree(root)
    assert result.hit_count == 0
    _result_public_fields(result)


def test_posthog_api_key_literal_hits_env_style_non_hit() -> None:
    """Opaque POSTHOG_API_KEY string Constant hits; env/Call RHS does not."""
    synthetic = 'POSTHOG_API_KEY = "phc_SYNTH_OPAQUE_TEST_KEY_NOT_REAL_01"\n'
    hit = scanner.scan_text(synthetic, label='posthog-literal', path_hint='telemetry.py')
    assert hit.hit_count >= 1
    assert 'credential_literal' in hit.path_classes
    _result_public_fields(hit)

    env_style = (
        'import os\n'
        'POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY")\n'
        'POSTHOG_HOST = "https://us.i.posthog.com"\n'
    )
    clean = scanner.scan_text(env_style, label='posthog-env', path_hint='telemetry.py')
    assert clean.hit_count == 0
    _result_public_fields(clean)


def test_telemetry_key_is_env_only_and_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing/empty key disables telemetry; configured key comes only from environment."""
    import sys
    from types import SimpleNamespace

    path = ROOT / 'graphiti_core' / 'telemetry' / 'telemetry.py'
    name = 'catalog_test_telemetry'
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    telemetry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(telemetry)

    fake_posthog = SimpleNamespace(api_key=None, host=None)
    monkeypatch.setitem(sys.modules, 'posthog', fake_posthog)
    monkeypatch.delenv('POSTHOG_API_KEY', raising=False)
    assert telemetry.initialize_posthog() is None

    monkeypatch.setenv('POSTHOG_API_KEY', '')
    assert telemetry.initialize_posthog() is None

    configured = 'test-placeholder'
    monkeypatch.setenv('POSTHOG_API_KEY', configured)
    assert telemetry.initialize_posthog() is fake_posthog
    assert fake_posthog.api_key == configured


def test_readme_password_placeholder_vs_opaque() -> None:
    """README-like password literals: opaque hits; allowlist placeholders do not."""
    opaque = 'password="falkor_password"\n'
    hit = scanner.scan_text(opaque, label='readme-opaque', path_hint='README.md')
    assert hit.hit_count >= 1
    assert 'credential_literal' in hit.path_classes
    _result_public_fields(hit)

    for placeholder in ('password', 'your_password', 'demodemo'):
        text = f'password="{placeholder}"\n'
        clean = scanner.scan_text(text, label=f'readme-{placeholder}', path_hint='README.md')
        assert clean.hit_count == 0


def test_repo_telemetry_and_readme_zero_hit() -> None:
    """Remediated Docker-consumed telemetry + README scan_path hit_count==0."""
    telemetry = ROOT / 'graphiti_core' / 'telemetry' / 'telemetry.py'
    readme = ROOT / 'README.md'
    assert telemetry.is_file() and readme.is_file()

    tel = scanner.scan_path(telemetry)
    assert tel.hit_count == 0
    assert not (tel.path_classes & {'credential_literal', 'token_shape', 'namespace_uuid'})
    _result_public_fields(tel)

    rm = scanner.scan_path(readme)
    assert rm.hit_count == 0
    assert not (rm.path_classes & {'credential_literal', 'token_shape', 'namespace_uuid'})
    _result_public_fields(rm)


def test_docker_projection_subset_zero_hit(tmp_path: Path) -> None:
    """Synthetic Dockerfile.standalone projection subset scans hits==0."""
    root = tmp_path / 'projection'
    tel_dir = root / 'graphiti_core' / 'telemetry'
    tel_dir.mkdir(parents=True)
    (tel_dir / 'telemetry.py').write_text(
        'import os\n'
        'POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY")\n'
        'POSTHOG_HOST = "https://us.i.posthog.com"\n'
        'def initialize_posthog():\n'
        '    key = os.environ.get("POSTHOG_API_KEY")\n'
        '    if not key:\n'
        '        return None\n'
        '    return key\n',
        encoding='utf-8',
    )
    (root / 'README.md').write_text(
        'driver = FalkorDriver(\n    host="localhost",\n    password="password",\n)\n',
        encoding='utf-8',
    )
    (root / 'graphiti_core' / '__init__.py').write_text('', encoding='utf-8')
    result = scanner.scan_tree(root)
    assert result.hit_count == 0
    _result_public_fields(result)


def _write_tar(path: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, 'w') as archive:
        for name, raw in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))


def _clean_complete_image(root: Path) -> Path:
    root.mkdir()
    dependency = root / 'rootfs/usr/lib/python3/site-packages/vendor'
    dependency.mkdir(parents=True)
    (dependency / 'auth.py').write_text(
        'def connect(password: str, api_key: str) -> None:\n'
        '    selected = api_key\n'
        '    algorithm = "sk-ecdsa-sha2-nistp256"\n',
        encoding='utf-8',
    )
    (root / 'config.json').write_text(
        json.dumps({'Config': {'Env': ['OPENAI_API_KEY=omitted', 'NAME=demo']}}),
        encoding='utf-8',
    )
    (root / 'history.json').write_text(
        json.dumps([{'created_by': 'password=config.password'}]),
        encoding='utf-8',
    )
    _write_tar(
        root / 'layer.tar',
        {
            'usr/lib/python3/site-packages/dep.py': (
                b'def f(client_secret: str) -> str:\n    return client_secret\n'
            ),
            'usr/share/doc/example.txt': b'api_key=your_openai_api_key_here\n',
            'usr/bin/tool': b'\x7fELF' + b'\x00' * 64,
        },
    )
    return root


def test_complete_image_clean_dependency_tree_zero_hit(tmp_path: Path) -> None:
    root = _clean_complete_image(tmp_path / 'image')
    result = scanner.scan_complete_image(root)
    assert result.hit_count == 0
    assert 'credential_literal' not in result.path_classes
    assert 'token_shape' not in result.path_classes
    assert 'namespace_uuid' not in result.path_classes
    _result_public_fields(result)


def test_complete_image_scans_dependency_config_history_and_layer(tmp_path: Path) -> None:
    root = _clean_complete_image(tmp_path / 'image')
    dependency = root / 'rootfs/usr/lib/python3/site-packages/vendor/auth.py'
    dependency.write_text(
        'api_key = "op4que-Cr3dential-Value-9x"\n',
        encoding='utf-8',
    )
    (root / 'config.json').write_text(
        json.dumps({'Config': {'Env': ['OPENAI_API_KEY=sk-liveOpenAITokenBodyWithEntropy01']}}),
        encoding='utf-8',
    )
    (root / 'history.json').write_text(
        json.dumps(
            [
                {
                    'created_by': (
                        'GRAPHITI_CATALOG_UUID_NAMESPACE=11111111-2222-3333-4444-555555555555'
                    )
                }
            ]
        ),
        encoding='utf-8',
    )
    _write_tar(
        root / 'layer.tar',
        {
            'usr/lib/python3/site-packages/dep.py': (
                b'client_secret = "real-client-secret-value"\n'
            ),
            'app/.planning/receipt.json': b'{}',
        },
    )
    result = scanner.scan_complete_image(root)
    assert result.hit_count >= 5
    assert {'credential_literal', 'token_shape', 'namespace_uuid', 'denylist_path'} <= set(
        result.path_classes
    )
    _result_public_fields(result)


def test_complete_image_layer_unparseable_text_fails_closed(tmp_path: Path) -> None:
    root = _clean_complete_image(tmp_path / 'image')
    _write_tar(root / 'layer.tar', {'app/settings.json': b'{password: \xff\xfe}'})
    with pytest.raises(scanner.ScanUnparseableError):
        scanner.scan_complete_image(root)
