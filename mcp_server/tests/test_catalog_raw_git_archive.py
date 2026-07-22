from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.catalog_raw_git_archive import (  # noqa: E402
    compute_source_context_sha256,
    materialize_raw_git_archive,
    verify_archive_against_git,
)

BASELINE = '35227e0a2c697e643871b5c2052556988c404df6'
BASELINE_CONTEXT_SHA256 = 'dcf73073443be37b777fc7feef124133be3d9ee305696e84042d5631125ed92f'


def _run(repository: Path, *argv: str) -> bytes:
    completed = subprocess.run(
        ['git', *argv],
        cwd=repository,
        capture_output=True,
        check=True,
        shell=False,
    )
    return completed.stdout


def _job_tmp_path(name: str) -> Path:
    job_dir = Path(os.environ['CLAUDE_JOB_DIR']).resolve()
    parent = job_dir / 'tmp'
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f'{name}-', dir=parent))


def _init_repository(path: Path) -> str:
    path.mkdir()
    _run(path, 'init', '--quiet')
    _run(path, 'config', 'user.email', 'phase6@example.invalid')
    _run(path, 'config', 'user.name', 'Phase 6 Test')
    (path / 'plain.txt').write_bytes(b'one\ntwo\n')
    executable = path / 'bin' / 'tool'
    executable.parent.mkdir()
    executable.write_bytes(b'#!/bin/sh\nprintf ok\n')
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    _run(path, 'add', 'plain.txt', 'bin/tool')
    _run(path, 'commit', '--quiet', '-m', 'fixture')
    return _run(path, 'rev-parse', 'HEAD').decode('ascii').strip()


def test_baseline_source_context_golden() -> None:
    repository = Path(__file__).resolve().parents[2]
    assert compute_source_context_sha256(repository, BASELINE) == BASELINE_CONTEXT_SHA256


def test_materialize_uses_raw_blobs_not_checkout_eol() -> None:
    parent = _job_tmp_path('phase6-archive-crlf')
    repository = parent / 'repository'
    revision = _init_repository(repository)
    (repository / 'plain.txt').write_bytes(b'one\r\ntwo\r\n')
    destination = parent / 'archive'

    result = materialize_raw_git_archive(repository, revision, destination)

    committed = _run(repository, 'cat-file', 'blob', f'{revision}:plain.txt')
    assert (destination / 'plain.txt').read_bytes() == committed == b'one\ntwo\n'
    assert result['file_count'] == 2
    assert result['source_context_sha256'] == compute_source_context_sha256(repository, revision)


def test_materialize_preserves_regular_modes() -> None:
    parent = _job_tmp_path('phase6-archive-modes')
    repository = parent / 'repository'
    revision = _init_repository(repository)
    destination = parent / 'archive'

    materialize_raw_git_archive(repository, revision, destination)

    if os.name == 'nt':
        assert (destination / 'plain.txt').is_file()
        assert (destination / 'bin' / 'tool').is_file()
    else:
        assert stat.S_IMODE((destination / 'plain.txt').stat().st_mode) == 0o644
        assert stat.S_IMODE((destination / 'bin' / 'tool').stat().st_mode) == 0o755


def test_verify_reports_exact_h8_counts() -> None:
    parent = _job_tmp_path('phase6-archive-verify')
    repository = parent / 'repository'
    revision = _init_repository(repository)
    destination = parent / 'archive'
    materialize_raw_git_archive(repository, revision, destination)

    result = verify_archive_against_git(repository, revision, destination)

    assert result == {
        'git_blob_count': 2,
        'archive_member_count': 2,
        'missing_count': 0,
        'extra_count': 0,
        'blob_mismatch_count': 0,
        'raw_git_context_sha256': compute_source_context_sha256(repository, revision),
        'archive_context_sha256': compute_source_context_sha256(repository, revision),
    }


def test_verify_detects_missing_extra_and_mismatched_files() -> None:
    parent = _job_tmp_path('phase6-archive-drift')
    repository = parent / 'repository'
    revision = _init_repository(repository)
    destination = parent / 'archive'
    materialize_raw_git_archive(repository, revision, destination)
    (destination / 'plain.txt').unlink()
    (destination / 'bin' / 'tool').write_bytes(b'changed')
    (destination / 'extra.txt').write_bytes(b'extra')

    result = verify_archive_against_git(repository, revision, destination)

    assert result['missing_count'] == 1
    assert result['extra_count'] == 1
    assert result['blob_mismatch_count'] == 1
    assert result['raw_git_context_sha256'] != result['archive_context_sha256']


def test_destination_must_be_empty() -> None:
    parent = _job_tmp_path('phase6-archive-nonempty')
    repository = parent / 'repository'
    revision = _init_repository(repository)
    destination = parent / 'archive'
    destination.mkdir()
    (destination / 'owned.txt').write_text('owned', encoding='utf-8')

    with pytest.raises(ValueError, match='empty'):
        materialize_raw_git_archive(repository, revision, destination)


def test_context_formula_uses_ls_tree_order_and_path_blob_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = b'alpha\n'
    second = b'beta\n'
    first_digest = hashlib.sha256(first).hexdigest()
    second_digest = hashlib.sha256(second).hexdigest()
    expected = hashlib.sha256(
        f'{first_digest}  z.txt\n{second_digest}  a.txt\n'.encode()
    ).hexdigest()
    calls: list[list[str]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        argv = list(args[0])  # type: ignore[arg-type]
        calls.append(argv)
        if argv[1:4] == ['ls-tree', '-rz', '--full-tree']:
            return subprocess.CompletedProcess(
                argv,
                0,
                b'100644 blob 1111111111111111111111111111111111111111\tz.txt\0'
                b'100644 blob 2222222222222222222222222222222222222222\ta.txt\0',
                b'',
            )
        object_id = argv[-1]
        return subprocess.CompletedProcess(
            argv, 0, first if object_id.startswith('1') else second, b''
        )

    monkeypatch.setattr(subprocess, 'run', fake_run)

    assert compute_source_context_sha256(Path('repository'), 'revision') == expected
    assert calls[0] == ['git', 'ls-tree', '-rz', '--full-tree', 'revision']
    assert all('archive' not in argument for call in calls for argument in call)


def test_unsupported_tree_mode_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        argv = list(args[0])  # type: ignore[arg-type]
        return subprocess.CompletedProcess(
            argv,
            0,
            b'160000 commit 1111111111111111111111111111111111111111\tsubmodule\0',
            b'',
        )

    monkeypatch.setattr(subprocess, 'run', fake_run)

    with pytest.raises(ValueError, match='unsupported'):
        compute_source_context_sha256(Path('repository'), 'revision')
