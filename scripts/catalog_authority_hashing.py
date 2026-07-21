"""Raw-byte and canonical UTF-8 text authority hashing."""

from __future__ import annotations

import hashlib
import subprocess
import unicodedata
from pathlib import Path

_BOMS = (
    b'\xef\xbb\xbf',
    b'\xff\xfe\x00\x00',
    b'\x00\x00\xfe\xff',
    b'\xff\xfe',
    b'\xfe\xff',
)
_ALLOWED_CONTROLS = frozenset({'\t', '\n', '\r'})


def sha256_raw_bytes(data: bytes) -> str:
    """Hash exact bytes without decoding or normalization."""
    return hashlib.sha256(data).hexdigest()


def canonical_text_bytes_lf(data: bytes) -> bytes:
    """Return strict UTF-8 text encoded with LF newlines.

    BOMs, invalid UTF-8, and binary control characters fail closed. A final
    newline remains content; this function only normalizes newline spelling.
    """
    if any(data.startswith(bom) for bom in _BOMS):
        raise ValueError('canonical text authority forbids BOMs')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('canonical text authority requires UTF-8') from exc
    if any(unicodedata.category(char) == 'Cc' and char not in _ALLOWED_CONTROLS for char in text):
        raise ValueError('canonical text authority rejects binary control characters')
    return text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')


def sha256_canonical_text_bytes(data: bytes) -> str:
    """Hash strict UTF-8 text after CRLF and bare-CR normalization to LF."""
    return sha256_raw_bytes(canonical_text_bytes_lf(data))


def sha256_file_raw(path: Path) -> str:
    """Hash exact file bytes."""
    return sha256_raw_bytes(path.read_bytes())


def sha256_file_canonical_text(path: Path) -> str:
    """Hash one strict UTF-8 text file using canonical LF bytes."""
    return sha256_canonical_text_bytes(path.read_bytes())


def authority_file_bytes(root: Path, relative: str) -> bytes:
    """Read one regular repository-relative file from a bound archive tree."""
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative:
        raise ValueError('source authority path must be repository-relative POSIX')
    resolved_root = root.resolve()
    candidate = resolved_root / path
    current = resolved_root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f'source authority path must not use symlinks: {relative}')
    resolved = candidate.resolve()
    if resolved.parent != resolved_root and resolved_root not in resolved.parents:
        raise ValueError('source authority path escapes repository root')
    if not resolved.is_file():
        raise ValueError(f'source authority file is unavailable: {relative}')
    try:
        return resolved.read_bytes()
    except OSError as exc:
        raise ValueError(f'source authority file is unavailable: {relative}') from exc


def git_blob_bytes(root: Path, relative: str, revision: str = 'HEAD') -> bytes:
    """Read exact Git blob bytes without materializing a checkout."""
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative:
        raise ValueError('Git authority path must be repository-relative POSIX')
    result = subprocess.run(
        ['git', 'cat-file', 'blob', f'{revision}:{relative}'],
        cwd=root,
        capture_output=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f'Git authority blob is unavailable: {relative}')
    return result.stdout


def authority_bytes(
    root: Path,
    relative: str,
    *,
    mode: str,
    revision: str = 'HEAD',
) -> bytes:
    """Read authoritative bytes from Git objects or a pre-bound archive tree."""
    if mode == 'git':
        return git_blob_bytes(root, relative, revision)
    if mode == 'archive':
        return authority_file_bytes(root, relative)
    raise ValueError('source authority mode must be git or archive')


def authority_digest(data: bytes) -> dict[str, str]:
    """Return exact-byte identity plus canonical LF text authority."""
    return {
        'raw_sha256': sha256_raw_bytes(data),
        'lf_sha256': sha256_canonical_text_bytes(data),
    }


def sha256_git_blob(root: Path, relative: str, revision: str = 'HEAD') -> str:
    """Hash exact bytes of one Git blob."""
    return sha256_raw_bytes(git_blob_bytes(root, relative, revision))
