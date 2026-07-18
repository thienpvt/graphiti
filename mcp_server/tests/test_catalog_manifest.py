"""RED Wave 0: pure catalog manifest serialize/hash/chunk contract (MANI-01..07).

Product module `services.catalog_manifest` lands in 03B-02. Until then every case
is collectable and fails closed with an explicit RED signal.
Future product symbols are resolved via importlib + getattr so static analysis
never sees a missing import (same pattern as test_catalog_identity helpers).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'

# Scaffold defaults mirror Phase 3A prepared-artifact ceilings (PATTERNS.md).
DEFAULT_CHUNK_BYTES = 131_072
HARD_CHUNK_BYTES = 262_144
MANIFEST_SERIALIZATION_VERSION = 'catalog-manifest-v1'

_PRODUCT_SYMBOLS = (
    'DEFAULT_CHUNK_BYTES',
    'HARD_CHUNK_BYTES',
    'MANIFEST_SERIALIZATION_VERSION',
    'build_manifest_body_from_membership',
    'chunk_manifest_bytes',
    'manifest_sha256',
    'serialize_manifest_body',
)


def _product() -> Any | None:
    """Load services.catalog_manifest when present; None while Wave 0 RED."""
    try:
        return importlib.import_module('services.catalog_manifest')
    except ImportError:
        return None


def _red(reason: str = '03B not implemented') -> None:
    # Even if the module later appears, Wave 0 cases stay RED until GREEN plans wire them.
    mod = _product()
    if mod is None:
        pytest.fail(reason)
    pytest.fail(f'{reason}: product present but behavior not yet GREEN for this case')


def _empty_membership() -> dict:
    return {'entities': [], 'edges': [], 'sources': [], 'evidence_links': []}


def _single_member_membership() -> dict:
    return {
        'entities': [
            {
                'uuid': 'e1',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': 'a' * 64,
            }
        ],
        'edges': [],
        'sources': [],
        'evidence_links': [],
    }


def _four_category_membership() -> dict:
    return {
        'entities': [
            {
                'uuid': 'e1',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': 'a' * 64,
            },
            {
                'uuid': 'e2',
                'entity_type': 'Table',
                'graph_key': 'TABLE::FE::ORCL.HR.DEPARTMENTS',
                'content_sha256': 'b' * 64,
            },
        ],
        'edges': [
            {
                'uuid': 'r1',
                'edge_type': 'ForeignKeyTo',
                'edge_key': 'FK::EMP->DEPT',
                'source_uuid': 'e1',
                'target_uuid': 'e2',
                'content_sha256': 'c' * 64,
            }
        ],
        'sources': [
            {
                'uuid': 's1',
                'source_key': 'SRC::ddl.sql#employees',
                'content_sha256': 'd' * 64,
            }
        ],
        'evidence_links': [
            {
                'uuid': 'l1',
                'link_key': 'SRC::ddl.sql#employees|entity|Table|TABLE::FE::ORCL.HR.EMPLOYEES',
                'content_sha256': 'e' * 64,
            }
        ],
    }


def test_manifest_canonical_bytes_stable():
    """MANI-01/02: equal membership yields byte-identical canonical serialization."""
    assert GROUP == 'oracle-catalog-tool-test'
    assert 'build_manifest_body_from_membership' in _PRODUCT_SYMBOLS
    _red('test_manifest_canonical_bytes_stable')


def test_manifest_empty_membership():
    """MANI-01: empty four-category membership is valid and stable."""
    _ = _empty_membership()
    _red('test_manifest_empty_membership')


def test_manifest_single_member():
    """MANI-01: single entity membership serializes deterministically."""
    _ = _single_member_membership()
    _red('test_manifest_single_member')


def test_manifest_four_category_membership():
    """MANI-01: entities+edges+sources+evidence_links all participate in digest."""
    _ = _four_category_membership()
    _red('test_manifest_four_category_membership')


def test_manifest_equal_key_sort_stability():
    """MANI-02: equal-key members sort stably so digest is order-invariant on input."""
    _red('test_manifest_equal_key_sort_stability')


def test_manifest_adjacency_equal_graph_key_ordering():
    """MANI-02: equal graph_key adjacency ordering is deterministic."""
    _red('test_manifest_adjacency_equal_graph_key_ordering')


def test_manifest_chunk_exact_default_boundary():
    """MANI-04: payload exactly DEFAULT_CHUNK_BYTES produces well-formed chunks."""
    assert DEFAULT_CHUNK_BYTES == 131_072
    _red('test_manifest_chunk_exact_default_boundary')


def test_manifest_chunk_hard_plus_one_fails():
    """MANI-04: payload of HARD_CHUNK_BYTES+1 fails closed (no silent truncate)."""
    assert HARD_CHUNK_BYTES == 262_144
    _red('test_manifest_chunk_hard_plus_one_fails')


def test_manifest_no_self_hash_field():
    """MANI-01: canonical body must not embed its own sha256 field."""
    _red('test_manifest_no_self_hash_field')


def test_manifest_byte_identical_rehash():
    """MANI-02: rehash of canonical bytes equals stored digest (byte-identical)."""
    _red('test_manifest_byte_identical_rehash')


def test_manifest_builder_ignores_batch_id_for_membership():
    """MANI-03: pure builder never consults batch_id when computing membership bytes."""
    _red('test_manifest_builder_ignores_batch_id_for_membership')


def test_manifest_serialization_version_constant():
    """MANI-01: version pin catalog-manifest-v1."""
    assert MANIFEST_SERIALIZATION_VERSION == 'catalog-manifest-v1'
    mod = _product()
    if mod is not None:
        got = getattr(mod, 'MANIFEST_SERIALIZATION_VERSION', None)
        assert got == 'catalog-manifest-v1'
    _red('test_manifest_serialization_version_constant')
