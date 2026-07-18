"""RED Wave 0: shared atomic catalog writer + fault-injection boundaries (PLAN-13/14).

Product `_write_catalog_batch_atomic` lands in 03B-04. Until then cases collect and RED.
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


def test_shared_writer_used_by_upsert_and_commit_paths():
    """PLAN-13: direct upsert and prepared commit share one atomic writer."""
    _red('test_shared_writer_used_by_upsert_and_commit_paths')


def test_fault_inject_after_entities_rolls_back():
    """PLAN-13/14: fault after entities leaves zero partial domain writes (primary)."""
    _red('test_fault_inject_after_entities_rolls_back')


def test_fault_inject_after_edges_rolls_back():
    """PLAN-13/14: fault after edges rolls back entities+edges; zero partial."""
    _red('test_fault_inject_after_edges_rolls_back')


def test_fault_inject_after_sources_rolls_back():
    """PLAN-13/14: fault after sources rolls back prior domain writes; zero partial."""
    _red('test_fault_inject_after_sources_rolls_back')


def test_fault_inject_after_evidence_rolls_back():
    """PLAN-13/14: fault after evidence rolls back evidence + domain; zero partial."""
    _red('test_fault_inject_after_evidence_rolls_back')


def test_fault_inject_after_manifest_rolls_back():
    """PLAN-13/14: fault after manifest root/chunks rolls back all prior writes."""
    _red('test_fault_inject_after_manifest_rolls_back')


def test_fault_inject_after_status_rolls_back():
    """PLAN-13/14: fault after batch status claim rolls back; no committed terminal."""
    _red('test_fault_inject_after_status_rolls_back')


def test_plan13_write_order_stub():
    """PLAN-13 order: lock/claim → entities → edges → sources → evidence →
    manifest → batch committed → plan COMMITTED (prepared path)."""
    _red('test_plan13_write_order_stub')


def test_dry_run_zero_write():
    """PLAN-14: dry_run path invokes no Neo4j write transaction."""
    _red('test_dry_run_zero_write')
