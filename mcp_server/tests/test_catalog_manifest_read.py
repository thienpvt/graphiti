"""Wave 0 RED scaffolds: public manifest read + pagination (MANI-05, IDEN-08).

Product GREEN lands in 04-03. Durable category order is authority; fail closed on
missing/incomplete/hash-mismatch; compact projection only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
# Page defaults reserved per A1 / D-04 (GREEN implements).
DEFAULT_MAX_PAGE_SIZE = 100
HARD_MAX_PAGE_SIZE = 500


def test_manifest_page_stable_order():
    """MANI-05 ordering: page order == Phase 3B canonical category order; stable rereads."""
    assert GROUP == 'oracle-catalog-tool-test'
    pytest.fail('04 not implemented: get_catalog_batch_manifest stable category order paging')


def test_empty_categories_legal():
    """MANI-05 empty: empty category membership → empty page total 0; authority still manifest."""
    pytest.fail('04 not implemented: empty manifest categories legal page')


def test_adjacency_equal_keys_distinct():
    """MANI-05 adjacency: adjacent offset windows no silent overlap/drop for multi-member category."""
    pytest.fail('04 not implemented: adjacent offset windows distinct membership')


def test_page_size_above_hard_max_fail_closed():
    """MANI-05 boundary: page size above hard max (500) fails closed; default configured 100."""
    assert DEFAULT_MAX_PAGE_SIZE == 100
    assert HARD_MAX_PAGE_SIZE == 500
    pytest.fail('04 not implemented: hard max_page_size fail-closed on manifest page')


def test_missing_incomplete_hash_mismatch_fail_closed():
    """MANI-05 / VERI-05: missing root, incomplete chunks, hash mismatch → fail closed; no batch_id synthesis."""
    pytest.fail(
        '04 not implemented: manifest reassembly fail-closed (no batch_id row synthesis)'
    )


def test_compact_projection_no_embeddings_payload_source():
    """MANI-05: compact projection omits embeddings, payload_b64, and source text."""
    pytest.fail('04 not implemented: compact manifest projection bans embeddings/payload/source')


def test_graph_key_complete():
    """IDEN-08: every entity-identifying field is full system-scoped graph_key (not name-only)."""
    pytest.fail('04 not implemented: full system-scoped graph_key on manifest members')


def test_unchanged_shared_entities_remain_members():
    """TEST-08 / MANI-05: unchanged shared entities remain manifest members (not dropped)."""
    pytest.fail('04 not implemented: unchanged shared entities remain membership')


def test_concurrent_same_params_identical_page():
    """MANI-05 concurrency: concurrent identical page reads return identical contents on frozen store."""
    pytest.fail('04 not implemented: concurrent same-params identical manifest page')
