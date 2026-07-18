"""Phase 5 Wave 0 RED: SAFE-09 legacy MCP contract compatibility scaffolds.

Canonical baseline vs live FastMCP registration for 14 legacy tools;
separate exact 14 catalog names; exact union 28 (D-07). GREEN in 05-04.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'legacy_mcp_contract_baseline.json'

LEGACY_TOOL_NAMES = frozenset(
    {
        'add_memory',
        'search_nodes',
        'search_memory_facts',
        'add_triplet',
        'get_entity_edge',
        'get_episodes',
        'get_episode_entities',
        'update_entity',
        'build_communities',
        'summarize_saga',
        'delete_episode',
        'delete_entity_edge',
        'clear_graph',
        'get_status',
    }
)

CATALOG_TOOL_NAMES = frozenset(
    {
        'upsert_typed_entities',
        'resolve_typed_entities',
        'resolve_typed_edges',
        'verify_catalog_batch',
        'upsert_typed_edges',
        'upsert_provenance',
        'get_catalog_ingest_status',
        'get_catalog_batch_manifest',
        'get_catalog_evidence',
        'upsert_catalog_batch',
        'get_catalog_capabilities',
        'prepare_catalog_batch',
        'commit_prepared_catalog_batch',
        'discard_prepared_catalog_batch',
    }
)


def test_baseline_fixture_lists_exactly_14_legacy_tools():
    """SAFE-09 empty: checked-in baseline contains exactly all 14 legacy names."""
    data = json.loads(FIXTURE.read_text(encoding='utf-8'))
    names = set(data['legacy_tools'].keys())
    assert names == LEGACY_TOOL_NAMES
    assert len(names) == 14
    assert 'add_memory' in names


def test_legacy_tool_names_constant_size_14():
    """SAFE-09: LEGACY_TOOL_NAMES is exact set of 14."""
    assert len(LEGACY_TOOL_NAMES) == 14
    assert 'add_memory' in LEGACY_TOOL_NAMES


def test_catalog_tool_names_exact_14_separate_from_legacy():
    """SAFE-09 / D-07: catalog set is exactly 14 and disjoint from legacy."""
    assert len(CATALOG_TOOL_NAMES) == 14
    assert LEGACY_TOOL_NAMES.isdisjoint(CATALOG_TOOL_NAMES)


def test_tool_union_exact_28():
    """SAFE-09: legacy ∪ catalog is exact union 28."""
    union = LEGACY_TOOL_NAMES | CATALOG_TOOL_NAMES
    assert len(union) == 28
    assert union == LEGACY_TOOL_NAMES | CATALOG_TOOL_NAMES


def test_legacy_contract_metadata_defaults_schemas_response_invariants():
    """SAFE-09 encoding: every legacy tool compares metadata/default/schema/invariants."""
    pytest.fail('05 not implemented: SAFE-09 legacy contract deep comparison')


def test_legacy_contract_concurrent_metadata_collections_stable():
    """SAFE-09 concurrency: two independent FastMCP collections canonicalize identically."""
    pytest.fail('05 not implemented: SAFE-09 concurrent metadata collection stability')


def test_empty_baseline_or_registration_fails():
    """SAFE-09 empty: empty baseline/registration/set fails closed."""
    pytest.fail('05 not implemented: SAFE-09 empty baseline/registration fail-closed')


def test_live_registration_contains_exact_14_legacy_and_14_catalog():
    """SAFE-09: live FastMCP registration contains exact legacy + catalog sets."""
    pytest.fail('05 not implemented: SAFE-09 live registration 14+14 contract')
