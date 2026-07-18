"""RED Wave 0: exact evidence store create-once/conflict/label contract (EVID-07..11).

Product evidence write path lands in 03B-03. Until then cases collect and RED.
MAX_EVIDENCE_LENGTH is loaded via importlib so a missing constant fails at runtime,
not as a static missing-import diagnostic.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'


def _common() -> Any:
    return importlib.import_module('models.catalog_common')


def _max_evidence_length() -> int:
    common = _common()
    value = getattr(common, 'MAX_EVIDENCE_LENGTH', None)
    if not isinstance(value, int) or value <= 0:
        pytest.fail('MAX_EVIDENCE_LENGTH missing or invalid on models.catalog_common')
    return value


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
    max_len = _max_evidence_length()
    assert max_len > 0
    _red('test_evidence_excerpt_length_bound_uses_string_length')
