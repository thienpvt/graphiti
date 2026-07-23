"""Materialize raw Git blobs and hash ``sha256(blob)  path\n`` rows in tree order."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_SUPPORTED_MODES = frozenset({'100644', '100755', '120000'})


@dataclass(frozen=True)
class _TreeEntry:
    mode: str
    object_id: str
    path: str


def _git(repository: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ['git', *arguments],
        cwd=repository,
        capture_output=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise ValueError(f'Git plumbing failed: {arguments[0]}')
    return result.stdout


def _safe_path(raw_path: bytes) -> str:
    try:
        path = raw_path.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('Git tree paths must be UTF-8') from exc
    pure = PurePosixPath(path)
    if not path or pure.is_absolute() or '..' in pure.parts or '\\' in path:
        raise ValueError('Git tree path must be repository-relative POSIX')
    return path


def _tree_entries(repository: Path, revision: str) -> list[_TreeEntry]:
    records = _git(repository, 'ls-tree', '-rz', '--full-tree', revision).split(b'\0')
    entries: list[_TreeEntry] = []
    seen: set[str] = set()
    for record in records:
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b'\t', 1)
            mode, object_type, object_id = metadata.decode('ascii').split()
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError('invalid Git tree entry') from exc
        path = _safe_path(raw_path)
        if object_type != 'blob' or mode not in _SUPPORTED_MODES:
            raise ValueError(f'unsupported Git tree entry: {mode} {object_type} {path}')
        if path in seen:
            raise ValueError(f'duplicate Git tree path: {path}')
        if any(parent.as_posix() in seen for parent in PurePosixPath(path).parents):
            raise ValueError(f'Git tree path collision: {path}')
        if any(existing.startswith(f'{path}/') for existing in seen):
            raise ValueError(f'Git tree path collision: {path}')
        seen.add(path)
        entries.append(_TreeEntry(mode=mode, object_id=object_id, path=path))
    if not entries:
        raise ValueError('Git tree has no supported blob entries')
    return entries


def _blob(repository: Path, entry: _TreeEntry) -> bytes:
    return _git(repository, 'cat-file', 'blob', entry.object_id)


def _mode_is_executable(path: Path) -> bool:
    if os.name == 'nt':
        return False
    return bool(path.stat().st_mode & stat.S_IXUSR)


def _context_sha256(rows: list[tuple[str, bytes]]) -> str:
    aggregate = b''.join(
        f'{hashlib.sha256(raw).hexdigest()}  {path}\n'.encode() for path, raw in rows
    )
    return hashlib.sha256(aggregate).hexdigest()


def _require_empty_destination(destination: Path) -> None:
    if destination.exists():
        if destination.is_symlink() or not destination.is_dir() or any(destination.iterdir()):
            raise ValueError('archive destination must be an empty directory')
    else:
        destination.mkdir(parents=True)


def _destination_path(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    resolved_root = root.resolve()
    resolved_parent = candidate.parent.resolve()
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise ValueError('archive member escapes destination')
    current = resolved_root
    for part in PurePosixPath(relative).parts[:-1]:
        current /= part
        if current.exists() and current.is_symlink():
            raise ValueError('archive destination contains a symlink ancestor')
    return candidate


def materialize_raw_git_archive(
    repository: Path,
    revision: str,
    destination: Path,
) -> dict[str, object]:
    """Write one revision's exact blob bytes into an empty destination."""
    entries = _tree_entries(repository, revision)
    _require_empty_destination(destination)
    rows: list[tuple[str, bytes]] = []
    for entry in entries:
        raw = _blob(repository, entry)
        path = _destination_path(destination, entry.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if entry.mode == '120000':
            path.write_bytes(raw)
        else:
            path.write_bytes(raw)
            mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
            if entry.mode == '100755':
                mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            os.chmod(path, mode)
        rows.append((entry.path, raw))
    return {'file_count': len(entries), 'source_context_sha256': _context_sha256(rows)}


def _archive_files(root: Path) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError('archive root must be a directory')
    files: dict[str, Path] = {}
    for path in root.rglob('*'):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError(f'archive member symlink is forbidden: {relative}')
        if path.is_file():
            if relative in files:
                raise ValueError(f'duplicate archive path: {relative}')
            files[relative] = path
    return files


def verify_archive_against_git(
    repository: Path,
    revision: str,
    archive_root: Path,
) -> dict[str, object]:
    """Compare a materialized tree with its raw Git objects using H8 count fields."""
    entries = _tree_entries(repository, revision)
    expected = {entry.path: entry for entry in entries}
    actual = _archive_files(archive_root)
    missing = expected.keys() - actual.keys()
    extra = actual.keys() - expected.keys()
    mismatched = 0
    raw_rows: list[tuple[str, bytes]] = []
    archive_rows: list[tuple[str, bytes]] = []
    for entry in entries:
        raw = _blob(repository, entry)
        raw_rows.append((entry.path, raw))
        path = actual.get(entry.path)
        if path is None:
            archive_rows.append((entry.path, b''))
            continue
        archived = path.read_bytes()
        archive_rows.append((entry.path, archived))
        mode_mismatch = (
            os.name != 'nt'
            and entry.mode
            in {
                '100644',
                '100755',
            }
            and _mode_is_executable(path) != (entry.mode == '100755')
        )
        if archived != raw or mode_mismatch:
            mismatched += 1
    for path in sorted(extra):
        archive_rows.append((path, actual[path].read_bytes()))
    return {
        'git_blob_count': len(entries),
        'archive_member_count': len(actual),
        'missing_count': len(missing),
        'extra_count': len(extra),
        'blob_mismatch_count': mismatched,
        'raw_git_context_sha256': _context_sha256(raw_rows),
        'archive_context_sha256': _context_sha256(archive_rows),
    }


def compute_source_context_sha256(repository: Path, revision: str) -> str:
    """Hash raw blob-digest/path rows in ``git ls-tree`` order; exclude mode and object ID."""
    return _context_sha256(
        [(entry.path, _blob(repository, entry)) for entry in _tree_entries(repository, revision)]
    )
