from __future__ import annotations

import importlib.util
import json
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
