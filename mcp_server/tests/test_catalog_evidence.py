"""Unit tests for CatalogEvidenceLink contract and pure identity helpers (EVID-01..06)."""

from __future__ import annotations

import math
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_common import MAX_EVIDENCE_LENGTH, MAX_SHORT_STRING_LENGTH  # noqa: E402
from models.catalog_evidence import (  # noqa: E402
    EVIDENCE_KINDS,
    CatalogEvidenceEdgeTarget,
    CatalogEvidenceEntityTarget,
    CatalogEvidenceLink,
    CatalogEvidenceLocator,
)
from services.catalog_identity import (  # noqa: E402
    canonical_sha256,
    catalog_evidence_link_uuid,
    coalesce_byte_identical_evidence_links,
    evidence_canonical_payload,
    evidence_link_key,
)

FIXED_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
GROUP = 'oracle-catalog-tool-test'

SIX_KINDS = (
    'oracle_dictionary',
    'ddl',
    'view_sql',
    'plsql_source',
    'comment',
    'manual',
)


def _entity_target(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
    }
    base.update(overrides)
    return base


def _edge_target(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'edge_type': 'Contains',
        'edge_key': 'CONTAINS::SCHEMA::FE::ORCL.HR->TABLE::FE::ORCL.HR.EMPLOYEES',
    }
    base.update(overrides)
    return base


def _link_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'source_key': 'DOC::HR.PDF#p12',
        'entity_target': _entity_target(),
        'evidence_kind': 'ddl',
        'extractor_name': 'oracle-ddl-extractor',
        'extractor_version': '1.0.0',
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# EVID-01 / EVID-02: construct + XOR targets
# ---------------------------------------------------------------------------


def test_entity_target_link_constructs():
    link = CatalogEvidenceLink.model_validate(_link_kwargs())
    assert link.source_key == 'DOC::HR.PDF#p12'
    assert link.entity_target is not None
    assert link.entity_target.entity_type == 'Table'
    assert link.edge_target is None
    assert link.evidence_kind == 'ddl'


def test_edge_target_link_constructs():
    link = CatalogEvidenceLink.model_validate(
        _link_kwargs(entity_target=None, edge_target=_edge_target())
    )
    assert link.edge_target is not None
    assert link.edge_target.edge_type == 'Contains'
    assert link.entity_target is None


def test_both_targets_fail():
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(
            _link_kwargs(entity_target=_entity_target(), edge_target=_edge_target())
        )


def test_neither_target_fails():
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(entity_target=None, edge_target=None))


def test_incomplete_entity_target_fails():
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(
            _link_kwargs(entity_target={'entity_type': 'Table'})
        )
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(
            _link_kwargs(entity_target={'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES'})
        )


def test_incomplete_edge_target_fails():
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(
            _link_kwargs(
                entity_target=None,
                edge_target={'edge_type': 'Contains'},
            )
        )
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(
            _link_kwargs(
                entity_target=None,
                edge_target={'edge_key': 'CONTAINS::K'},
            )
        )


def test_entity_target_allowlist_and_prefix():
    CatalogEvidenceEntityTarget.model_validate(_entity_target())
    with pytest.raises(ValidationError):
        CatalogEvidenceEntityTarget.model_validate(_entity_target(entity_type='Widget'))
    with pytest.raises(ValidationError):
        CatalogEvidenceEntityTarget.model_validate(
            _entity_target(graph_key='SCHEMA::FE::ORCL.HR.EMPLOYEES')
        )


def test_edge_target_allowlist():
    CatalogEvidenceEdgeTarget.model_validate(_edge_target())
    with pytest.raises(ValidationError):
        CatalogEvidenceEdgeTarget.model_validate(_edge_target(edge_type='Owns'))


# ---------------------------------------------------------------------------
# EVID-03: six evidence kinds
# ---------------------------------------------------------------------------


def test_evidence_kinds_constant_exact():
    assert EVIDENCE_KINDS == frozenset(SIX_KINDS)


@pytest.mark.parametrize('kind', SIX_KINDS)
def test_each_evidence_kind_accepted(kind: str):
    link = CatalogEvidenceLink.model_validate(_link_kwargs(evidence_kind=kind))
    assert link.evidence_kind == kind


def test_unknown_evidence_kind_rejected():
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(evidence_kind='guesswork'))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(evidence_kind='DDL'))


# ---------------------------------------------------------------------------
# EVID-04: locator bounds, confidence, excerpt, content_sha256
# ---------------------------------------------------------------------------


def test_empty_locator_allowed():
    link = CatalogEvidenceLink.model_validate(_link_kwargs(locator=None))
    assert link.locator is None
    empty = CatalogEvidenceLink.model_validate(_link_kwargs(locator={}))
    assert empty.locator is not None
    assert empty.locator.object_name is None
    assert empty.locator.start_line is None


def test_locator_end_before_start_fails():
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(
            _link_kwargs(locator={'start_line': 10, 'end_line': 5})
        )


def test_locator_equal_lines_ok():
    link = CatalogEvidenceLink.model_validate(
        _link_kwargs(locator={'start_line': 3, 'end_line': 3, 'statement_index': 0})
    )
    assert link.locator is not None
    assert link.locator.start_line == 3
    assert link.locator.end_line == 3


def test_locator_start_line_ge_1_statement_index_ge_0():
    with pytest.raises(ValidationError):
        CatalogEvidenceLocator.model_validate({'start_line': 0})
    with pytest.raises(ValidationError):
        CatalogEvidenceLocator.model_validate({'end_line': 0})
    with pytest.raises(ValidationError):
        CatalogEvidenceLocator.model_validate({'statement_index': -1})
    loc = CatalogEvidenceLocator.model_validate({'statement_index': 0, 'start_line': 1})
    assert loc.statement_index == 0
    assert loc.start_line == 1


def test_locator_object_name_max_short_string():
    ok = 'x' * MAX_SHORT_STRING_LENGTH
    CatalogEvidenceLocator.model_validate({'object_name': ok})
    with pytest.raises(ValidationError):
        CatalogEvidenceLocator.model_validate({'object_name': ok + 'y'})


def test_confidence_bounds_and_finite():
    CatalogEvidenceLink.model_validate(_link_kwargs(confidence=0.0))
    CatalogEvidenceLink.model_validate(_link_kwargs(confidence=1.0))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(confidence=1.0001))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(confidence=-0.01))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(confidence=math.nan))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(confidence=math.inf))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(confidence=-math.inf))


def test_excerpt_preserves_trailing_spaces_when_non_empty():
    raw = 'CREATE TABLE employees (  '
    link = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt=raw))
    assert link.excerpt == raw
    assert link.excerpt.endswith('  ')


def test_excerpt_max_length():
    ok = 'e' * MAX_EVIDENCE_LENGTH
    CatalogEvidenceLink.model_validate(_link_kwargs(excerpt=ok))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(excerpt=ok + 'x'))


def test_content_sha256_optional_and_64_lowercase_hex():
    link = CatalogEvidenceLink.model_validate(_link_kwargs(content_sha256=None))
    assert link.content_sha256 is None
    digest = 'a' * 64
    link2 = CatalogEvidenceLink.model_validate(_link_kwargs(content_sha256=digest))
    assert link2.content_sha256 == digest
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(content_sha256='deadbeef'))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(content_sha256='A' * 64))


def test_source_key_and_extractor_required_non_empty():
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(source_key=''))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(source_key='   '))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(extractor_name=''))
    with pytest.raises(ValidationError):
        CatalogEvidenceLink.model_validate(_link_kwargs(extractor_version='  '))


def test_validation_error_does_not_embed_full_excerpt():
    secret = 'SECRET_PAYLOAD_' + ('x' * 200)
    with pytest.raises(ValidationError) as excinfo:
        CatalogEvidenceLink.model_validate(
            _link_kwargs(entity_target=None, edge_target=None, excerpt=secret)
        )
    text = str(excinfo.value)
    assert secret not in text


# ---------------------------------------------------------------------------
# EVID-05: identity / hash helpers
# ---------------------------------------------------------------------------


def test_evidence_link_key_deterministic():
    link = CatalogEvidenceLink.model_validate(
        _link_kwargs(
            locator={'start_line': 1, 'end_line': 2, 'object_name': 'EMP'},
            rule_id='R1',
        )
    )
    k1 = evidence_link_key(link)
    k2 = evidence_link_key(link)
    assert k1 == k2
    assert 'DOC::HR.PDF#p12' in k1
    assert 'entity' in k1
    assert 'Table' in k1
    assert 'ddl' in k1


def test_catalog_evidence_link_uuid_stable():
    link = CatalogEvidenceLink.model_validate(_link_kwargs())
    key = evidence_link_key(link)
    u1 = catalog_evidence_link_uuid(FIXED_NS, GROUP, key)
    u2 = catalog_evidence_link_uuid(FIXED_NS, GROUP, key)
    assert u1 == u2
    assert u1 == str(uuid.uuid5(FIXED_NS, f'{GROUP}|catalog-v2|EvidenceLink|{key}'))


def test_evidence_canonical_payload_and_hash_stable():
    link = CatalogEvidenceLink.model_validate(
        _link_kwargs(excerpt='CREATE TABLE t (id INT)', confidence=0.9)
    )
    p1 = evidence_canonical_payload(link)
    p2 = evidence_canonical_payload(link)
    assert p1 == p2
    h1 = canonical_sha256(p1)
    h2 = canonical_sha256(p2)
    assert h1 == h2
    assert len(h1) == 64
    assert h1 == h1.lower()
    # content_sha256 is transport-only — not in identity payload
    assert 'content_sha256' not in p1


def test_change_excerpt_changes_hash():
    a = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt='AAA'))
    b = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt='BBB'))
    ha = canonical_sha256(evidence_canonical_payload(a))
    hb = canonical_sha256(evidence_canonical_payload(b))
    assert ha != hb


def test_coalesce_byte_identical_links():
    a = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt='same'))
    b = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt='same'))
    c = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt='other', source_key='DOC::OTHER'))
    # Reverse order input; coalesce collapses identical, retains distinct, sorts by key
    out = coalesce_byte_identical_evidence_links([c, b, a])
    assert len(out) == 2
    keys = [evidence_link_key(x) for x in out]
    assert keys == sorted(keys)
    payloads = [evidence_canonical_payload(x) for x in out]
    assert len({canonical_sha256(p) for p in payloads}) == 2


def test_coalesce_retains_non_identical_multiplicity():
    """Same source/target identity material but different excerpt → not coalesced."""
    a = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt='one'))
    b = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt='two'))
    out = coalesce_byte_identical_evidence_links([a, b])
    assert len(out) == 2


def test_coalesce_empty_list():
    assert coalesce_byte_identical_evidence_links([]) == []


def test_evidence_helpers_reentrant_no_shared_state():
    link = CatalogEvidenceLink.model_validate(_link_kwargs(excerpt='concurrent'))

    def _once() -> str:
        return canonical_sha256(evidence_canonical_payload(link))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _once(), range(32)))
    assert len(set(results)) == 1


# ---------------------------------------------------------------------------
# EVID-06 / EVID-14: batch non-Cartesian evidence_links
# ---------------------------------------------------------------------------


def _batch_shell(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': GROUP,
        'batch_id': 'batch-1',
        'entities': [],
        'edges': [],
    }
    base.update(overrides)
    return base


def test_batch_accepts_sources_and_evidence_links():
    from models.catalog_batch import UpsertCatalogBatchRequest

    req = UpsertCatalogBatchRequest.model_validate(
        _batch_shell(
            provenance={
                'sources': [
                    {
                        'source_key': 'DOC::HR.PDF#p12',
                        'reference_time': '2024-01-15T10:30:00+00:00',
                    }
                ],
                'evidence_links': [_link_kwargs()],
            }
        )
    )
    assert req.provenance is not None
    assert len(req.provenance.sources) == 1
    assert len(req.provenance.evidence_links) == 1
    assert req.provenance.evidence_links[0].evidence_kind == 'ddl'


def test_batch_rejects_cartesian_entity_targets():
    from models.catalog_batch import UpsertCatalogBatchRequest

    with pytest.raises(ValidationError) as exc:
        UpsertCatalogBatchRequest.model_validate(
            _batch_shell(
                provenance={
                    'sources': [
                        {
                            'source_key': 'DOC::HR.PDF#p12',
                            'reference_time': '2024-01-15T10:30:00+00:00',
                        }
                    ],
                    'entity_targets': [_entity_target()],
                }
            )
        )
    text = str(exc.value).lower()
    assert 'cartesian' in text or 'entity_targets' in text
    assert 'auto-conversion' in text or 'evidence_links' in text


def test_batch_rejects_cartesian_edge_targets():
    from models.catalog_batch import UpsertCatalogBatchRequest

    with pytest.raises(ValidationError):
        UpsertCatalogBatchRequest.model_validate(
            _batch_shell(
                provenance={
                    'sources': [
                        {
                            'source_key': 'DOC::A',
                            'reference_time': '2024-01-15T10:30:00+00:00',
                        }
                    ],
                    'edge_targets': [_edge_target()],
                }
            )
        )


def test_batch_no_cartesian_product_expansion():
    """Two sources + one explicit link remains one link (not product)."""
    from models.catalog_batch import UpsertCatalogBatchRequest

    req = UpsertCatalogBatchRequest.model_validate(
        _batch_shell(
            provenance={
                'sources': [
                    {
                        'source_key': 'DOC::A',
                        'reference_time': '2024-01-15T10:30:00+00:00',
                    },
                    {
                        'source_key': 'DOC::B',
                        'reference_time': '2024-01-15T10:30:00+00:00',
                    },
                ],
                'evidence_links': [_link_kwargs(source_key='DOC::A')],
            }
        )
    )
    assert req.provenance is not None
    assert len(req.provenance.sources) == 2
    assert len(req.provenance.evidence_links) == 1


def test_batch_evidence_links_only_ok():
    from models.catalog_batch import UpsertCatalogBatchRequest

    req = UpsertCatalogBatchRequest.model_validate(
        _batch_shell(provenance={'evidence_links': [_link_kwargs()]})
    )
    assert req.provenance is not None
    assert req.provenance.sources == []
    assert len(req.provenance.evidence_links) == 1


def test_batch_empty_evidence_links_with_sources_ok():
    from models.catalog_batch import UpsertCatalogBatchRequest

    req = UpsertCatalogBatchRequest.model_validate(
        _batch_shell(
            provenance={
                'sources': [
                    {
                        'source_key': 'DOC::ONLY',
                        'reference_time': '2024-01-15T10:30:00+00:00',
                    }
                ],
                'evidence_links': [],
            }
        )
    )
    assert req.provenance is not None
    assert len(req.provenance.sources) == 1
    assert req.provenance.evidence_links == []


def test_standalone_upsert_provenance_cartesian_still_valid():
    from models.catalog_provenance import UpsertProvenanceRequest

    req = UpsertProvenanceRequest.model_validate(
        {
            'identity_schema_version': 'catalog-v2',
            'system_key': 'FE',
            'group_id': GROUP,
            'batch_id': 'batch-1',
            'sources': [
                {
                    'source_key': 'DOC::HR.PDF#p12',
                    'reference_time': '2024-01-15T10:30:00+00:00',
                }
            ],
            'entity_targets': [_entity_target()],
            'edge_targets': [_edge_target()],
        }
    )
    assert len(req.entity_targets) == 1
    assert len(req.edge_targets) == 1


def test_model_validate_does_not_invent_links_from_cartesian():
    from models.catalog_batch import NestedProvenancePayload

    with pytest.raises(ValidationError):
        NestedProvenancePayload.model_validate(
            {
                'sources': [
                    {
                        'source_key': 'DOC::A',
                        'reference_time': '2024-01-15T10:30:00+00:00',
                    }
                ],
                'entity_targets': [_entity_target(), _entity_target(graph_key='TABLE::FE::ORCL.X')],
            }
        )
