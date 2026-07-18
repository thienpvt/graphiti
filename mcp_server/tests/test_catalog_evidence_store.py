"""RED Wave 0: exact evidence store create-once/conflict/label contract (EVID-07..11).

Product evidence write path lands in 03B-03. Until then cases collect and RED.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'

try:
    from models.catalog_common import MAX_EVIDENCE_LENGTH  # noqa: F401

    _MAX_EVIDENCE_AVAILABLE = True
except ImportError:
    _MAX_EVIDENCE_AVAILABLE = False
    MAX_EVIDENCE_LENGTH = 4000  # scaffold default; product owns the real constant

try:
    from services.catalog_store import CatalogNeo4jStore  # noqa: F401

    _STORE_AVAILABLE = True
except ImportError:
    _STORE_AVAILABLE = False
    CatalogNeo4jStore = None  # type: ignore[assignment,misc]


def _red(reason: str = '03B not implemented') -> None:
    pytest.fail(reason)


def test_evidence_create_once_conflict():
    """EVID-07/08: create-once same content is idempotent; divergent content_sha256
    raises provenance_link_conflict (named primary RED case)."""
    _red('test_evidence_create_once_conflict')


def test_evidence_create_once_same_content():
    """EVID-07: second write with identical content_sha256 is create-once no-op."""
    _red('test_evidence_create_once_same_content')


def test_evidence_divergent_content_raises_provenance_link_conflict():
    """EVID-08: same link identity, different content_sha256 → provenance_link_conflict."""
    _red('test_evidence_divergent_content_raises_provenance_link_conflict')


def test_evidence_missing_target_fails():
    """EVID-09: evidence targeting a missing entity/edge/source fails closed."""
    _red('test_evidence_missing_target_fails')


def test_evidence_type_mismatch_fails():
    """EVID-09: target type mismatch (entity vs edge vs source) fails closed."""
    _red('test_evidence_type_mismatch_fails')


def test_evidence_no_entity_label():
    """EVID-10: CatalogEvidenceLink must never carry Entity or Episodic labels."""
    _red('test_evidence_no_entity_label')


def test_evidence_empty_list_ok():
    """EVID-07: empty evidence list is a valid no-op write."""
    _red('test_evidence_empty_list_ok')


def test_evidence_single_link():
    """EVID-07: single exact evidence link persists with fixed allowlist properties."""
    _red('test_evidence_single_link')


def test_evidence_coalesce_byte_identical():
    """EVID-11: byte-identical evidence links coalesce to one durable record."""
    _red('test_evidence_coalesce_byte_identical')


def test_evidence_excerpt_length_bound_uses_string_length():
    """EVID-11: excerpt bound uses MAX_EVIDENCE_LENGTH string length (not bytes)."""
    assert isinstance(MAX_EVIDENCE_LENGTH, int) and MAX_EVIDENCE_LENGTH > 0
    _red('test_evidence_excerpt_length_bound_uses_string_length')
