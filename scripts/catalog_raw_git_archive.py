"""Materialize exact source trees from raw Git object bytes."""

from __future__ import annotations

from pathlib import Path


def materialize_raw_git_archive(
    repository: Path,
    revision: str,
    destination: Path,
) -> dict[str, object]:
    """Write one revision's exact blob bytes into an empty directory."""
    raise NotImplementedError


def verify_archive_against_git(
    repository: Path,
    revision: str,
    archive_root: Path,
) -> dict[str, object]:
    """Compare a materialized tree with its raw Git objects."""
    raise NotImplementedError


def compute_source_context_sha256(repository: Path, revision: str) -> str:
    """Compute the canonical source-context digest from raw Git blobs."""
    raise NotImplementedError
