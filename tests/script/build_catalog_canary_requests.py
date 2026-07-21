from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'build_catalog_canary_requests.py'
FIXTURE = ROOT / 'mcp_server' / 'tests' / 'fixtures' / 'accept_tab_sanitized.json'
GOLDEN = ROOT / 'catalog' / 'canary-v2-requests-hardened'


def _load():
    spec = importlib.util.spec_from_file_location('catalog_canary_builder_4x2', SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load()


def _files(path: Path) -> dict[str, bytes]:
    return {item.name: item.read_bytes() for item in sorted(path.iterdir()) if item.is_file()}


def _live(output: Path, *, suffix: str = 'a') -> dict[str, object]:
    return builder.build_live_canary(
        FIXTURE,
        output,
        run_id=f'20260720T010203Z-{suffix}',
        group_id=f'oracle-catalog-v2-canary-20260720T010203Z-{suffix}',
        control_group_id=f'oracle-catalog-v2-canary-20260720T010203Z-{suffix}-empty-control',
        batch_id=f'accept-tab-catalog-v2-canary-20260720T010203Z-{suffix}',
    )


def test_golden_profile_is_byte_identical(tmp_path: Path) -> None:
    before = _files(GOLDEN)
    builder.build_golden(FIXTURE, tmp_path)
    assert _files(tmp_path) == before


def test_live_profile_is_deterministic_and_control_is_metadata_only(tmp_path: Path) -> None:
    first = tmp_path / 'one'
    second = tmp_path / 'two'
    first_manifest = _live(first)
    second_manifest = _live(second)
    assert _files(first) == _files(second)
    assert first_manifest == second_manifest

    payload = json.loads((first / 'accept-tab.payload.json').read_text(encoding='utf-8'))
    manifest = json.loads((first / 'run-manifest.json').read_text(encoding='utf-8'))
    assert payload['group_id'] == manifest['group_id']
    assert payload['batch_id'] == manifest['batch_id']
    assert manifest['control_group_id'] not in json.dumps(payload)
    assert payload['catalog_sha256'] == builder.sha256_bytes(
        json.dumps(
            json.loads(FIXTURE.read_text(encoding='utf-8')),
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
    )
    assert not ({'plan_token', 'credentials', 'connection_string', 'embeddings'} & set(manifest))


def test_live_identity_changes_only_identity_dependent_output(tmp_path: Path) -> None:
    first = tmp_path / 'one'
    second = tmp_path / 'two'
    _live(first, suffix='a')
    _live(second, suffix='b')
    a = json.loads((first / 'accept-tab.payload.json').read_text(encoding='utf-8'))
    b = json.loads((second / 'accept-tab.payload.json').read_text(encoding='utf-8'))
    assert a['catalog_sha256'] == b['catalog_sha256']
    assert a['entities'] == b['entities']
    assert a['edges'] == b['edges']
    assert a['group_id'] != b['group_id']
    assert a['batch_id'] != b['batch_id']
    assert a['provenance'] == b['provenance']


@pytest.mark.parametrize(
    'group_id',
    ['oracle-core', 'oracle-catalog-v2', 'oracle-catalog-tool-test', 'main', ' MAIN '],
)
def test_live_profile_rejects_protected_groups(tmp_path: Path, group_id: str) -> None:
    with pytest.raises(ValueError, match='protected'):
        builder.build_live_canary(
            FIXTURE,
            tmp_path / 'live',
            run_id='20260720T010203Z-a',
            group_id=group_id,
            control_group_id='fresh-empty-control',
            batch_id='fresh-batch',
        )


def test_live_profile_rejects_equal_malformed_and_overlong_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='differ'):
        builder.build_live_canary(
            FIXTURE,
            tmp_path / 'equal',
            run_id='run-a',
            group_id='fresh-group',
            control_group_id='fresh-group',
            batch_id='fresh-batch',
        )
    with pytest.raises(ValueError):
        builder.build_live_canary(
            FIXTURE,
            tmp_path / 'malformed',
            run_id='run-a',
            group_id='fresh/group',
            control_group_id='fresh-control',
            batch_id='fresh-batch',
        )
    with pytest.raises(ValueError):
        builder.build_live_canary(
            FIXTURE,
            tmp_path / 'long',
            run_id='run-a',
            group_id='fresh-group',
            control_group_id='fresh-control',
            batch_id='x' * 513,
        )


def test_live_profile_refuses_differing_existing_file(tmp_path: Path) -> None:
    output = tmp_path / 'live'
    _live(output)
    (output / 'accept-tab.payload.json').write_text('{}\n', encoding='utf-8')
    with pytest.raises(FileExistsError, match='overwrite'):
        _live(output)


def test_live_cli_requires_every_identity_and_output() -> None:
    with pytest.raises(SystemExit):
        builder.parse_args(['--profile', 'live-canary'])
    args = builder.parse_args(
        [
            '--profile',
            'live-canary',
            '--run-id',
            'run-a',
            '--group-id',
            'fresh-group',
            '--control-group-id',
            'fresh-control',
            '--batch-id',
            'fresh-batch',
            '--output-dir',
            'out',
        ]
    )
    assert args.output_dir == Path('out')


def test_fixture_authority_is_lf_normalized_and_pinned(tmp_path: Path) -> None:
    raw = FIXTURE.read_bytes()
    assert builder.lf_sha256(raw) == builder.APPROVED_FIXTURE_LF_SHA256
    crlf = tmp_path / 'fixture.json'
    crlf.write_bytes(builder.lf_normalized_bytes(raw).replace(b'\n', b'\r\n'))
    assert builder.lf_sha256(crlf.read_bytes()) == builder.APPROVED_FIXTURE_LF_SHA256
    mutated = tmp_path / 'mutated.json'
    mutated.write_bytes(raw + b' ')
    with pytest.raises(ValueError, match='Git/LF authority'):
        builder.build_golden(mutated, tmp_path / 'golden')


def test_five_golden_pins_and_default_never_overwrites(tmp_path: Path) -> None:
    before = _files(GOLDEN)
    assert {
        name: builder.sha256_bytes(raw) for name, raw in before.items()
    } == builder.GOLDEN_SHA256
    builder.build_golden(FIXTURE, GOLDEN)
    assert _files(GOLDEN) == before
    destination = tmp_path / 'golden'
    builder.build_golden(FIXTURE, destination)
    (destination / 'manifest.json').write_text('{}\n', encoding='utf-8')
    with pytest.raises(FileExistsError, match='overwrite'):
        builder.build_golden(FIXTURE, destination)


@pytest.mark.parametrize('protected', sorted(builder.PROTECTED_GROUP_IDS))
@pytest.mark.parametrize('variant', ['exact', 'upper', 'trim'])
def test_protected_matrix_for_canary_and_control(
    tmp_path: Path, protected: str, variant: str
) -> None:
    value = (
        protected
        if variant == 'exact'
        else protected.upper()
        if variant == 'upper'
        else f' {protected} '
    )
    for field in ('group_id', 'control_group_id'):
        kwargs = {
            'run_id': '20260720T010203Z-a',
            'group_id': 'oracle-catalog-v2-canary-20260720T010203Z-a',
            'control_group_id': 'oracle-catalog-v2-canary-20260720T010203Z-a-empty-control',
            'batch_id': 'accept-tab-catalog-v2-canary-20260720T010203Z-a',
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match='protected'):
            builder.build_live_canary(
                FIXTURE, tmp_path / f'{field}-{variant}-{protected}', **kwargs
            )


def test_historical_mode_is_read_only_verifier(tmp_path: Path) -> None:
    historical = ROOT / 'catalog' / 'canary-v2-requests'
    before = _files(historical)
    assert builder.verify_historical(historical)['unique_totals'] == {'entities': 38, 'edges': 85}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--mode', 'historical'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['unique_totals'] == {'entities': 38, 'edges': 85}
    assert _files(historical) == before
    with pytest.raises(ValueError, match='tracked historical'):
        builder.verify_historical(tmp_path)


def test_live_requires_exact_fixture_path_and_manifest_schema(tmp_path: Path) -> None:
    copied = tmp_path / 'copy.json'
    copied.write_bytes(FIXTURE.read_bytes())
    with pytest.raises(ValueError, match='exact approved'):
        builder.build_live_canary(
            copied,
            tmp_path / 'live',
            run_id='20260720T010203Z-a',
            group_id='oracle-catalog-v2-canary-20260720T010203Z-a',
            control_group_id='oracle-catalog-v2-canary-20260720T010203Z-a-empty-control',
            batch_id='accept-tab-catalog-v2-canary-20260720T010203Z-a',
        )
    manifest = _live(tmp_path / 'valid')
    assert set(manifest) == builder.LIVE_MANIFEST_FIELDS
    assert manifest['fixture_lf_sha256'] == builder.APPROVED_FIXTURE_LF_SHA256
