from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/bootstrap_catalog_v2_schema.py'


def _load():
    spec = importlib.util.spec_from_file_location('catalog_schema_bootstrap_under_test', SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load()


class StoreSpy:
    def __init__(self, *, fail: str | None = None, ready: bool = True):
        self.fail = fail
        self.ready = ready
        self.calls: list[str] = []

    async def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.fail == name:
            raise RuntimeError('secret-bearing failure')

    async def ensure_uuid_uniqueness_constraints(self, _executor: Any) -> None:
        await self._call('ensure_uuid_uniqueness_constraints')

    async def ensure_plan_schema(self, _executor: Any) -> None:
        await self._call('ensure_plan_schema')

    async def ensure_evidence_manifest_schema(self, _executor: Any) -> None:
        await self._call('ensure_evidence_manifest_schema')

    async def inspect_catalog_v2_schema_readiness(self, _executor: Any) -> dict[str, bool]:
        self.calls.append('inspect_catalog_v2_schema_readiness')
        return {
            'identity': self.ready,
            'plan': self.ready,
            'evidence_manifest': self.ready,
            'ready': self.ready,
        }


@pytest.mark.asyncio
async def test_bootstrap_calls_exact_methods_and_one_inspection() -> None:
    store = StoreSpy()
    code, report = await bootstrap.bootstrap(object(), store)
    assert code == 0
    assert store.calls == [
        'ensure_uuid_uniqueness_constraints',
        'ensure_plan_schema',
        'ensure_evidence_manifest_schema',
        'inspect_catalog_v2_schema_readiness',
    ]
    assert report['classification'] == 'PASSED_SCHEMA_BOOTSTRAP'
    assert report['graphiti_driver_constructed'] is False


@pytest.mark.asyncio
async def test_bootstrap_fails_fast_without_retry_then_inspects_once() -> None:
    store = StoreSpy(fail='ensure_plan_schema')
    code, report = await bootstrap.bootstrap(object(), store)
    assert code == 1
    assert store.calls == [
        'ensure_uuid_uniqueness_constraints',
        'ensure_plan_schema',
        'inspect_catalog_v2_schema_readiness',
    ]
    assert report['classification'] == 'FAILED_SCHEMA_BOOTSTRAP'
    assert report['retry_count'] == 0
    assert report['rollback_attempted'] is False
    assert 'secret-bearing failure' not in str(report)
    assert report['error_type'] == 'RuntimeError'


@pytest.mark.asyncio
async def test_first_nonready_inspection_is_terminal() -> None:
    store = StoreSpy(ready=False)
    code, report = await bootstrap.bootstrap(object(), store)
    assert code == 1
    assert store.calls.count('inspect_catalog_v2_schema_readiness') == 1
    assert report['post_inspection']['ready'] is False


@pytest.mark.asyncio
async def test_raw_executor_uses_session_run_without_managed_retry() -> None:
    calls: list[tuple[str, Any]] = []

    class Result:
        async def to_eager_result(self):
            return ([{'ok': True}], None, None)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def run(self, query: str, *, parameters: dict[str, Any]):
            calls.append((query, parameters))
            return Result()

    class Driver:
        execute_query = pytest.fail

        def session(self, *, database: str):
            assert database == 'neo4j'
            return Session()

    result = await bootstrap.RawNeo4jExecutor(Driver(), 'neo4j').execute_query(
        'SHOW CONSTRAINTS', params={'x': 1}
    )
    assert result[0] == [{'ok': True}]
    assert calls == [('SHOW CONSTRAINTS', {'x': 1})]


def test_script_never_imports_graphiti_driver_or_handwrites_create() -> None:
    source = SCRIPT.read_text(encoding='utf-8')
    assert 'Neo4jDriver' not in source
    assert 'graphiti_core' not in source
    assert 'build_indices_and_constraints' not in source
    assert 'CREATE CONSTRAINT' not in source


def test_relationship_uniqueness_matches_application_contract() -> None:
    store = bootstrap.CatalogNeo4jStore()
    assert store._constraint_row_matches(
        {
            'name': 'catalog_relates_to_identity_unique',
            'type': 'RELATIONSHIP_UNIQUENESS',
            'entityType': 'RELATIONSHIP',
            'labelsOrTypes': ['RELATES_TO'],
            'properties': ['group_id', 'uuid'],
        },
        expected_name='catalog_relates_to_identity_unique',
        expected_entity_type='RELATIONSHIP',
        expected_label='RELATES_TO',
    )


def test_config_rejects_non_neo4j_provider() -> None:
    config = SimpleNamespace(database=SimpleNamespace(provider='falkordb'))
    with pytest.raises(ValueError, match='requires Neo4j'):
        bootstrap._neo4j_config(config)


def test_cli_and_migration_doc_match_real_contract() -> None:
    assert bootstrap.parse_args([]) is not None
    for option in ('--dry-print-statements', '--uri', '--user', '--password', '--database'):
        with pytest.raises(SystemExit) as error:
            bootstrap.parse_args([option])
        assert error.value.code == 2
    migration = (Path(__file__).resolve().parents[1] / 'docs/CATALOG_V2_MIGRATION.md').read_text(
        encoding='utf-8'
    )
    for forbidden in (
        'catalog_schema_bootstrap.py',
        '--dry-print-statements',
        '--uri',
        '--user',
        '--password',
        '--database',
    ):
        assert forbidden not in migration
    assert (
        'CONFIG_PATH=mcp_server/config/config-docker-neo4j.catalog-local.yaml '
        'uv run --project mcp_server --frozen python scripts/bootstrap_catalog_v2_schema.py'
        in migration
    )
    assert (
        "$env:CONFIG_PATH='mcp_server/config/config-docker-neo4j.catalog-local.yaml'; "
        'uv run --project mcp_server --frozen python scripts/bootstrap_catalog_v2_schema.py'
        in migration
    )
