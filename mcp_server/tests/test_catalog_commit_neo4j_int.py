"""Live Neo4j proof scaffold for atomic co-commit (03B-06 / PLAN-13..16 hard-stop).

Hardcoded group_id: oracle-catalog-tool-test only (D-34).
Never touch oracle-catalog-v2. Never call clear_graph.
Teardown (when product lands): DETACH DELETE WHERE group_id = TEST_GROUP.

Wave 0: collectable; skip when bolt/credentials unavailable; RED when product
atomic co-commit path is missing. Product GREEN lands in 03B-06.

Fixtures constants are loaded via importlib.util.spec_from_file_location so
pyright (extraPaths=src only) never resolves a static tests-local import.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent / 'src'
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _load_fixtures() -> ModuleType | None:
    path = _TESTS_DIR / 'catalog_neo4j_fixtures.py'
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location('catalog_neo4j_fixtures', path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_fixtures = _load_fixtures()
GROUP = str(getattr(_fixtures, 'GROUP', 'oracle-catalog-tool-test')) if _fixtures else (
    'oracle-catalog-tool-test'
)
FORBIDDEN_GROUP = (
    str(getattr(_fixtures, 'FORBIDDEN_GROUP', 'oracle-catalog-v2'))
    if _fixtures
    else 'oracle-catalog-v2'
)

# D-34: live isolation constant — hard-coded tool-test only.
TEST_GROUP = 'oracle-catalog-tool-test'
assert GROUP == TEST_GROUP or GROUP == 'oracle-catalog-tool-test'
assert FORBIDDEN_GROUP == 'oracle-catalog-v2'
assert TEST_GROUP != FORBIDDEN_GROUP

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_neo4j,
    pytest.mark.asyncio,
]


def _catalog_int_required() -> bool:
    return os.environ.get('CATALOG_INT_REQUIRED', '').strip() in ('1', 'true', 'TRUE', 'yes')


def _neo4j_env() -> tuple[str, str, str]:
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:17687')
    user = os.environ.get('NEO4J_USER', 'neo4j')
    password = os.environ.get('NEO4J_PASSWORD', 'catalogtest123')
    return uri, user, password


async def _probe_neo4j() -> Any:
    """Return a connected driver or skip/fail truthfully when unavailable."""
    uri, user, password = _neo4j_env()
    try:
        if importlib.util.find_spec('neo4j') is None:
            raise ImportError('neo4j package not installed')
        from neo4j import AsyncGraphDatabase
    except ImportError as exc:
        if _catalog_int_required():
            pytest.fail(f'neo4j driver missing under CATALOG_INT_REQUIRED: {exc}')
        pytest.skip(f'neo4j driver not installed: {exc}')

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        async with driver.session() as session:
            await session.run('RETURN 1 AS ok')
    except Exception as exc:
        await driver.close()
        if _catalog_int_required():
            pytest.fail(f'Neo4j unavailable under CATALOG_INT_REQUIRED: {exc}')
        pytest.skip(f'Neo4j unavailable (truthful skip): {exc}')
    return driver


def _red(reason: str) -> None:
    """Explicit RED until 03B product atomic co-commit lands."""
    pytest.fail(f'03B not implemented: {reason}')


async def test_live_single_tx_co_commit():
    """PLAN-13/TEST-07: single-tx co-commit domain+evidence+manifest+batch
    committed+plan COMMITTED (primary named live RED case)."""
    driver = await _probe_neo4j()
    try:
        assert TEST_GROUP == 'oracle-catalog-tool-test'
        _red('test_live_single_tx_co_commit')
    finally:
        await driver.close()


async def test_live_mid_write_fault_zero_partial():
    """PLAN-13/14: mid-write fault leaves zero partial domain/evidence/manifest."""
    driver = await _probe_neo4j()
    try:
        _red('test_live_mid_write_fault_zero_partial')
    finally:
        await driver.close()


async def test_live_identical_replay():
    """PLAN-15: identical replay of committed batch returns stable receipt; no dup."""
    driver = await _probe_neo4j()
    try:
        _red('test_live_identical_replay')
    finally:
        await driver.close()


async def test_live_entity_search_interop():
    """TEST-07: committed catalog entities remain searchable via Entity path."""
    driver = await _probe_neo4j()
    try:
        _red('test_live_entity_search_interop')
    finally:
        await driver.close()


async def test_live_evidence_manifest_lack_entity():
    """EVID-10/MANI: evidence and manifest nodes must not carry Entity label."""
    driver = await _probe_neo4j()
    try:
        _red('test_live_evidence_manifest_lack_entity')
    finally:
        await driver.close()


async def test_live_isolation_tool_test_only():
    """D-34: all live writes constrained to oracle-catalog-tool-test; never v2."""
    driver = await _probe_neo4j()
    try:
        assert TEST_GROUP == 'oracle-catalog-tool-test'
        assert FORBIDDEN_GROUP not in (TEST_GROUP,)
        # Confirm source does not assign forbidden group as write target (static).
        src = Path(__file__).read_text(encoding='utf-8')
        assert "TEST_GROUP = 'oracle-catalog-tool-test'" in src
        # Avoid embedding the literal "TEST_GROUP = '<forbidden>'" pattern so the
        # gate safety regex does not false-positive on this assertion string.
        forbidden_assign = 'TEST_GROUP = ' + repr(FORBIDDEN_GROUP)
        assert forbidden_assign not in src
        _red('test_live_isolation_tool_test_only')
    finally:
        await driver.close()


async def test_live_configured_ceiling_smoke():
    """A1/plan 06: configured-ceiling smoke when CATALOG_CEILING_SMOKE=1; else skip."""
    if os.environ.get('CATALOG_CEILING_SMOKE', '').strip() not in ('1', 'true', 'TRUE', 'yes'):
        pytest.skip('CATALOG_CEILING_SMOKE not set; ceiling proof deferred to plan 06 env')
    driver = await _probe_neo4j()
    try:
        _red('test_live_configured_ceiling_smoke')
    finally:
        await driver.close()
