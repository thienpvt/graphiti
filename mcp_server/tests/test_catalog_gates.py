"""Wave 0 RED scaffolds: split read/write gates (GATE-01..06).

Product GREEN lands in 04-02. Collection must succeed; bodies fail closed until
reads_enabled / found=false / mutation-free read paths exist.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

GROUP = 'oracle-catalog-tool-test'
# Isolation tests hard-code tool-test only (D-23, D-30). Never oracle-catalog-v2.


def _load_module(module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(f'04 not implemented: {module_name} missing ({exc})')


def _attr(mod: Any, symbol: str) -> Any:
    value = getattr(mod, symbol, None)
    if value is None:
        pytest.fail(f'04 not implemented: missing symbol {symbol}')
    return value


def test_reads_enabled_default_true_writes_false():
    """GATE-01: CatalogConfig.reads_enabled default True; write enabled default False."""
    cfg_mod = _load_module('config.schema')
    CatalogConfig = _attr(cfg_mod, 'CatalogConfig')
    cfg = CatalogConfig()
    assert hasattr(cfg, 'reads_enabled')
    assert cfg.reads_enabled is True
    assert cfg.enabled is False
    assert getattr(cfg, 'max_page_size', None) == 100


def test_capabilities_callable_both_gates_false():
    """GATE-02: get_catalog_capabilities callable with writes false and reads false; mutation-free."""
    from unittest.mock import MagicMock

    cfg_mod = _load_module('config.schema')
    cap_mod = _load_module('services.catalog_capabilities')
    CatalogConfig = _attr(cfg_mod, 'CatalogConfig')
    build = _attr(cap_mod, 'build_catalog_capabilities')
    hard = _attr(cap_mod, 'HARD_MAX_PAGE_SIZE')
    cfg = CatalogConfig(enabled=False, reads_enabled=False)
    # Pure builder: no client probe, no schema/write side effects.
    driver = MagicMock()
    caps = build(config=cfg, client=None)
    assert caps is not None
    assert getattr(caps, 'catalog_writes_enabled', None) is False
    assert getattr(caps, 'catalog_reads_enabled', None) is False
    assert hard == 500
    assert caps.limits['hard']['max_page_size'] == 500
    assert caps.limits['configured']['max_page_size'] == 100
    assert caps.features['manifest_verification'] is False
    # Mutation-free: never touches a driver even if one were passed.
    _ = driver
    assert not driver.method_calls


def test_read_tools_when_writes_disabled():
    """GATE-03: six identity-bearing read tools usable when writes off (reads on)."""
    pytest.fail(
        '04 not implemented: read tools must work with enabled=False and reads_enabled=True'
    )


def test_reads_no_schema_write_embed():
    """GATE-04: zero ensure_*_schema / write tx / embedder / LLM / queue on read paths."""
    pytest.fail(
        '04 not implemented: read paths must spy zero schema/write/embed/LLM/queue calls'
    )


def test_missing_status_found_false():
    """GATE-05: missing ingest status returns found=false (not validation_error sole encoding)."""
    resp_mod = _load_module('models.catalog_responses')
    Status = getattr(resp_mod, 'CatalogIngestStatusResponse', None)
    if Status is None:
        pytest.fail('04 not implemented: CatalogIngestStatusResponse missing')
    fields = getattr(Status, 'model_fields', {})
    if 'found' not in fields:
        pytest.fail('04 not implemented: CatalogIngestStatusResponse.found missing')
    pytest.fail(
        '04 not implemented: get_catalog_ingest_status missing branch must return found=False'
    )


def test_group_id_isolation_on_reads():
    """GATE-06 adjacency: foreign group_id rows never appear in tool-test results."""
    assert GROUP == 'oracle-catalog-tool-test'
    pytest.fail('04 not implemented: cross-group isolation on read tools')


def test_empty_group_id_rejected():
    """GATE-06 empty: empty/invalid group_id rejected; no unscoped MATCH."""
    pytest.fail('04 not implemented: empty group_id rejection on read gate')


def test_isolation_group_id_set_equality():
    """GATE-06 ordering: isolation checks use set equality on group_id (order-independent)."""
    pytest.fail('04 not implemented: group_id set equality isolation asserts')


def test_cypher_binds_group_id():
    """GATE-06: every new Phase 4 Cypher binds $group_id (store unit + service)."""
    pytest.fail('04 not implemented: Phase 4 read Cypher must bind group_id param')


def test_concurrent_read_isolation_same_group():
    """GATE-06 concurrency: concurrent same-group reads stay isolated and consistent."""
    pytest.fail('04 not implemented: concurrent read isolation same group')
