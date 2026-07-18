"""RED Wave 0: stranded COMMITTING recovery + terminal agreement (PLAN-14/15, MANI-07).

Product recovery path lands in 03B-05. Until then cases collect and RED.
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


def test_terminal_agreement_returns_stable_receipt():
    """PLAN-15/MANI-07: plan COMMITTED + batch committed + manifest digest agree
    → stable receipt on re-commit (primary named RED case)."""
    _red('test_terminal_agreement_returns_stable_receipt')


def test_partial_terminal_fails_closed():
    """PLAN-15: partial terminal evidence (plan/batch/manifest disagree) fails closed;
    no repair or silent rewrite."""
    _red('test_partial_terminal_fails_closed')


def test_committing_resume_full_write():
    """PLAN-14/15: stranded COMMITTING resumes the full atomic write, not a partial."""
    _red('test_committing_resume_full_write')


def test_never_prepared_revival():
    """PLAN-15: COMMITTING must never transition back to PREPARED (no revival)."""
    _red('test_never_prepared_revival')


def test_terminal_receipt_idempotent_across_calls():
    """PLAN-15: two successive terminal-agreement reads return equal bounded receipts."""
    _red('test_terminal_receipt_idempotent_across_calls')
