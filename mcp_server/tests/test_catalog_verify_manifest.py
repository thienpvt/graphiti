"""Wave 0 RED scaffolds: manifest-backed verify rewire (VERI-01..06, EVID-13, TEST-08).

Product GREEN lands in 04-04. Durable manifest is sole batch expected authority;
live rows are observations only; never expected=len(live).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'


def test_batch_only_uses_manifest():
    """VERI-01: batch_id path loads committed manifest expected; not len(live)."""
    assert GROUP == 'oracle-catalog-tool-test'
    pytest.fail('04 not implemented: batch_only verify uses durable manifest expected set')


def test_expected_not_live_count():
    """VERI-02 boundary+precision: expected ints from manifest counts; never len(rows)/float."""
    pytest.fail('04 not implemented: expected counts must not equal len(live rows)')


def test_missing_and_extra():
    """VERI-03: missing list and extras list both populated when both conditions true."""
    pytest.fail('04 not implemented: missing vs extra distinct anomaly lists')


def test_consistency_checks():
    """VERI-04: type/UUID/endpoint/embed/evidence/hash consistency; boundary/empty/encoding/precision/concurrency."""
    pytest.fail(
        '04 not implemented: verify consistency checks (type/uuid/endpoint/embed/evidence/hash)'
    )


def test_missing_manifest_code():
    """VERI-05: missing/incomplete/hash-mismatch → CatalogErrorCode.manifest_mismatch (not status absence)."""
    pytest.fail('04 not implemented: missing committed manifest → manifest_mismatch')


def test_explicit_keys_only():
    """VERI-06: keys-only path never uses manifest load as expected authority; no fake manifest."""
    pytest.fail('04 not implemented: keys-only verify without fake manifest synthesis')


def test_batch_and_keys_both_apply():
    """VERI-06: batch_id + explicit keys both apply (keys still diagnosed when supplied)."""
    pytest.fail('04 not implemented: batch+keys combined verify path')


def test_never_expected_equals_observed_len():
    """VERI-01/02: never section.expected = len(observed live rows) on batch path."""
    pytest.fail('04 not implemented: forbid expected=observed live length on batch verify')


def test_empty_expected_categories():
    """VERI-02 boundary: empty expected categories legal; live rows become extras."""
    pytest.fail('04 not implemented: empty expected categories verify path')


def test_exact_evidence():
    """EVID-13: exact evidence MATCH by group_id + evidence-link uuid from durable manifest."""
    pytest.fail('04 not implemented: exact evidence identity authority from manifest')


def test_unchanged_member_missing_diagnostic():
    """TEST-08 boundary: shared unchanged member missing from live → missing diagnostic."""
    pytest.fail('04 not implemented: unchanged member missing stays in expected')


def test_duplicate_key_anomaly_no_repair():
    """TEST-08 adjacency: duplicate_key anomaly without repair/write."""
    pytest.fail('04 not implemented: duplicate key anomaly without repair on verify')


def test_empty_batch_membership_clean():
    """TEST-08 empty: empty batch membership verifies clean when live empty."""
    pytest.fail('04 not implemented: empty membership clean verify')


def test_missing_extra_lists_deterministic():
    """TEST-08 ordering: missing/extra lists deterministic sorted by key."""
    pytest.fail('04 not implemented: deterministic sorted missing/extra lists')


def test_count_drift_off_by_one():
    """TEST-08 precision: count drift off-by-one detected."""
    pytest.fail('04 not implemented: off-by-one count drift detection')


def test_concurrent_verify_stable():
    """TEST-08 concurrency: concurrent verifies same batch_id; no shared mutable expected mutation."""
    pytest.fail('04 not implemented: concurrent verify stable results')
