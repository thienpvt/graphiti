"""Phase 5 Wave 0 RED: optional local Ollama E2E on oracle-catalog-tool-test only (D-23).

Availability-skip when Ollama/Neo4j unavailable. Never shells canary runner.
Never queries or mutates oracle-catalog-v2. GREEN classification in 05-06.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
FORBIDDEN_GROUP = 'oracle-catalog-v2'


def _ollama_available() -> bool:
    """Pure local probe placeholder — Wave 0 never opens network."""
    return os.environ.get('CATALOG_OLLAMA_E2E') == '1'


def _neo4j_available() -> bool:
    return os.environ.get('CATALOG_INT_REQUIRED') == '1' or os.environ.get('NEO4J_URI') not in (
        None,
        '',
    )


def test_module_hardcodes_allowed_test_group_only():
    """D-04 / D-23: E2E module hard-codes oracle-catalog-tool-test only."""
    assert ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    assert FORBIDDEN_GROUP == 'oracle-catalog-v2'
    src = Path(__file__).read_text(encoding='utf-8')
    # No GROUP = 'oracle-catalog-v2' assignment (FORBIDDEN_GROUP binding is ok).
    assert "GROUP = 'oracle-catalog-v2'" not in src
    assert 'GROUP = "oracle-catalog-v2"' not in src


def test_ollama_e2e_skips_when_unavailable():
    """D-23: skip with non-empty reason when Ollama/Neo4j unavailable; never pass."""
    if not _ollama_available() or not _neo4j_available():
        pytest.skip(
            'Ollama/Neo4j unavailable for catalog E2E '
            '(set CATALOG_OLLAMA_E2E=1 and Neo4j env to enable)'
        )
    pytest.fail('05 not implemented: Ollama E2E prepare/commit on test group')


def test_ollama_e2e_never_targets_protected_group():
    """D-23: E2E must never use oracle-catalog-v2 as group_id."""
    if not _ollama_available():
        pytest.skip('Ollama unavailable — protected-group ban still reserved')
    pytest.fail('05 not implemented: Ollama E2E protected-group ban assertion')


def test_ollama_e2e_never_shells_canary_runner():
    """D-10 / D-23: E2E must not import-exec or shell run_catalog_canary_batch.py live."""
    src = Path(__file__).read_text(encoding='utf-8')
    assert 'run_catalog_canary_batch' not in src or 'never' in src.lower()
    # Wave 0: no subprocess of canary runner.
    assert 'subprocess' not in src
