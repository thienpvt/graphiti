"""Phase 5 Wave 0 RED: SAFE-03/04/06/07 + TEST-10 security matrix scaffolds.

Collectable named cases reserve Nyquist targets. GREEN lands in 05-02.
Never shells canary; never targets oracle-catalog-v2 (D-04, D-10, D-12).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MCP_SRC = ROOT / 'mcp_server' / 'src'
SERVICE_PATH = MCP_SRC / 'services' / 'catalog_service.py'
STORE_PATH = MCP_SRC / 'services' / 'catalog_store.py'
MCP_PATH = MCP_SRC / 'graphiti_mcp_server.py'

ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
FORBIDDEN_GROUP = 'oracle-catalog-v2'

# SAFE-03: maintenance/LLM path tools must not be call targets on catalog paths.
PROHIBITED_ON_CATALOG_PATH = frozenset(
    {
        'add_memory',
        'add_triplet',
        'build_communities',
        'clear_graph',
        'delete_entity_edge',
        'delete_episode',
        'summarize_saga',
        'update_entity',
    }
)

# Exact UTF-8 forbidden log substrings (SAFE-07 encoding).
FORBIDDEN_LOG_MARKERS = (
    'plan_token=',
    'password=',
    'api_key=',
    'authorization:',
    'payload=',
    'source_text=',
)


def test_prohibited_tools_absent_on_catalog_paths():
    """SAFE-03: deterministic catalog service+MCP wrappers never call prohibited tools."""
    pytest.fail('05 not implemented: SAFE-03 prohibited-tools AST matrix')


def test_llm_or_queue_or_community_ban_on_catalog_paths():
    """SAFE-04: LLM/queue/community counts stay zero on prepare/commit/upsert paths."""
    pytest.fail('05 not implemented: SAFE-04 llm/queue/community spy matrix')


def test_commit_path_embedder_not_awaited():
    """SAFE-04: commit never re-embeds (embedder.create not awaited)."""
    pytest.fail('05 not implemented: SAFE-04 commit embedder spy')


def test_client_controlled_cypher_entity_identifiers_fail_before_query():
    """TEST-10: malicious entity-type identifiers never enter Cypher / tx.run."""
    pytest.fail('05 not implemented: TEST-10 entity cypher_identifier authority')


def test_client_controlled_cypher_edge_identifiers_fail_before_query():
    """TEST-10: malicious edge-type identifiers never enter Cypher / tx.run."""
    pytest.fail('05 not implemented: TEST-10 edge cypher_identifier authority')


def test_client_controlled_property_keys_fail_before_query():
    """TEST-10: client attribute/property keys never interpolate into Cypher."""
    pytest.fail('05 not implemented: TEST-10 property_allowlist authority')


def test_missing_endpoint_returns_structured_error_zero_writes():
    """SAFE-04: missing persisted endpoints → existing missing_endpoint; zero writes."""
    pytest.fail('05 not implemented: SAFE-04 missing_endpoint zero-write matrix')


def test_same_batch_endpoints_resolve_from_request_union_only():
    """SAFE-04: same-batch endpoints resolve from validated entity union only."""
    pytest.fail('05 not implemented: SAFE-04 endpoint_union no extra endpoint creation')


def test_implicit_endpoint_creation_forbidden():
    """SAFE-04 / TEST-10: MATCH-only lookup; zero implicit endpoint/community writes."""
    pytest.fail('05 not implemented: SAFE-04 implicit_endpoint ban')


def test_fail_closed_conflicts_no_silent_repair():
    """SAFE-06: identity/type/endpoint/provenance/manifest/hash conflicts fail closed."""
    pytest.fail('05 not implemented: SAFE-06 fail_closed conflict matrix')


def test_log_empty_batch_omits_payload_and_credentials():
    """SAFE-07 empty: empty/minimal catalog log events omit payload/source/token/creds."""
    pytest.fail('05 not implemented: SAFE-07 log_empty scrub')


def test_log_encoding_forbids_plan_token_and_payload_markers():
    """SAFE-07 encoding: AST/caplog exact UTF-8 containment bans for forbidden markers."""
    pytest.fail('05 not implemented: SAFE-07 log_encoding scrub')


def test_empty_spy_baseline_no_prohibited_call():
    """TEST-10 empty: empty-spy baseline executes no prohibited call/query."""
    pytest.fail('05 not implemented: TEST-10 empty spy baseline')


def test_cypher_identifier_registry_nonempty():
    """TEST-10 empty: fixed-authority identifier registry must be nonempty."""
    pytest.fail('05 not implemented: TEST-10 cypher_identifier registry inventory')


def test_matrix_hardcodes_allowed_test_group_only():
    """D-04: matrix module may name forbidden group only as ban constant."""
    assert ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    assert FORBIDDEN_GROUP == 'oracle-catalog-v2'
    src = Path(__file__).read_text(encoding='utf-8')
    # No bare GROUP/group_id/TEST_GROUP assignment to protected group.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    'GROUP',
                    'group_id',
                    'TEST_GROUP',
                }:
                    if isinstance(node.value, ast.Constant) and node.value.value == FORBIDDEN_GROUP:
                        pytest.fail(f'forbidden assignment of {target.id} to protected group')
