"""RED Wave 0: concurrent same-token / same-batch commit arbitration (PLAN-16, TEST-06).

Product concurrency path lands in 03B-05. Until then cases collect and RED.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'

try:
    from services.catalog_service import CatalogService  # noqa: F401

    _SERVICE_AVAILABLE = True
except ImportError:
    _SERVICE_AVAILABLE = False
    CatalogService = None  # type: ignore[assignment,misc]


def _red(reason: str = '03B not implemented') -> None:
    pytest.fail(reason)


def test_same_token_concurrent_one_logical_commit():
    """PLAN-16/TEST-06: concurrent commit with the same token yields one logical
    commit (primary named RED case)."""
    _red('test_same_token_concurrent_one_logical_commit')


def test_same_batch_different_tokens_converge_or_deterministic_conflict():
    """PLAN-16: same batch_id with different tokens either converge to one
    committed state or raise a deterministic conflict — never both succeed
    with divergent membership."""
    _red('test_same_batch_different_tokens_converge_or_deterministic_conflict')


def test_no_duplicate_manifest_under_race():
    """PLAN-16/TEST-06: concurrent winners leave exactly one CatalogBatchManifest."""
    _red('test_no_duplicate_manifest_under_race')


def test_no_duplicate_domain_under_race():
    """PLAN-16: concurrent same-token races leave no duplicate entity/edge rows."""
    _red('test_no_duplicate_domain_under_race')
