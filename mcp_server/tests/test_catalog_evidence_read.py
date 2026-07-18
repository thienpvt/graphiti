"""Wave 0 RED scaffolds: get_catalog_evidence pagination (EVID-12, IDEN-08).

Product GREEN lands in 04-05. Bounded pages, compact default, group isolation on
oracle-catalog-tool-test only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
DEFAULT_MAX_PAGE_SIZE = 100
HARD_MAX_PAGE_SIZE = 500


def test_evidence_page_bounded():
    """EVID-12: get_catalog_evidence returns bounded offset/limit page with total."""
    assert GROUP == 'oracle-catalog-tool-test'
    assert DEFAULT_MAX_PAGE_SIZE == 100
    assert HARD_MAX_PAGE_SIZE == 500
    pytest.fail('04 not implemented: get_catalog_evidence bounded page')


def test_page():
    """EVID-12 alias (research test map): evidence pagination."""
    pytest.fail('04 not implemented: get_catalog_evidence page (alias)')


def test_compact_default():
    """EVID-12: compact default projection (no full source payload unless requested)."""
    pytest.fail('04 not implemented: evidence compact default projection')


def test_optional_excerpt_length_bound():
    """EVID-12: optional excerpt length is bounded fail-closed."""
    pytest.fail('04 not implemented: evidence excerpt length bound')


def test_empty_links():
    """EVID-12 empty: zero links → empty page, total 0, still group-scoped."""
    pytest.fail('04 not implemented: empty evidence links page')


def test_adjacency_multi_link():
    """EVID-12 adjacency: multi-link same target returns distinct link rows (no collapse)."""
    pytest.fail('04 not implemented: multi-link evidence adjacency')


def test_ordering_stable():
    """EVID-12 ordering: stable ORDER BY uuid (or documented link_key) then offset/limit."""
    pytest.fail('04 not implemented: evidence page stable ordering')


def test_group_isolation():
    """EVID-12 / GATE-06: evidence reads constrained to group_id; tool-test only."""
    pytest.fail('04 not implemented: evidence group isolation')


def test_full_graph_key_on_target():
    """IDEN-08: target identity on evidence responses is full system-scoped graph_key."""
    pytest.fail('04 not implemented: full graph_key on evidence target identity')
