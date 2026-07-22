"""Canonical no-retry Catalog-v2 schema bootstrap and CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from config.schema import GraphitiConfig, Neo4jProviderConfig
from services.catalog_store import CatalogNeo4jStore, CatalogStoreError

CATALOG_V2_REQUIRED_CONSTRAINT_COUNT = 14
SCHEMA_VERSION = 'catalog-v2-schema-bootstrap-report-v3'
METHODS = (
    ('identity', 'ensure_uuid_uniqueness_constraints'),
    ('prepared_plan', 'ensure_plan_schema'),
    ('evidence_manifest', 'ensure_evidence_manifest_schema'),
)


class RawNeo4jExecutor:
    """No-retry auto-commit executor for CatalogNeo4jStore schema methods."""

    def __init__(self, driver: Any, database: str):
        self._driver = driver
        self._database = database

    async def execute_query(self, query: str, **kwargs: Any) -> Any:
        params = dict(kwargs.get('params') or {})
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, parameters=params)
            return await result.to_eager_result()


def catalog_v2_constraint_statements(
    store: CatalogNeo4jStore | None = None,
) -> tuple[str, ...]:
    """Return only the application-owned fixed 14 constraint statements."""
    selected = store if store is not None else CatalogNeo4jStore()
    statements = (
        *selected.identity_uniqueness_constraint_statements(),
        *selected.plan_schema_constraint_statements(),
        *selected.evidence_manifest_schema_constraint_statements(),
    )
    if len(statements) != CATALOG_V2_REQUIRED_CONSTRAINT_COUNT:
        raise CatalogStoreError(
            'catalog-v2 constraint statement count is not 14', code='neo4j_schema_failed'
        )
    for statement in statements:
        upper = statement.upper()
        if 'DROP' in upper or 'CREATE CONSTRAINT' not in upper or 'IF NOT EXISTS' not in upper:
            raise CatalogStoreError(
                'catalog-v2 bootstrap statements are not fixed create-if-absent constraints',
                code='neo4j_schema_failed',
            )
    return statements


def _inspection(result: Any, *, status: str = 'succeeded') -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            'status': 'failed',
            'identity': False,
            'plan': False,
            'evidence_manifest': False,
            'ready': False,
            'expected': CATALOG_V2_REQUIRED_CONSTRAINT_COUNT,
            'matched': -1,
            'missing': [],
        }
    missing = result.get('missing')
    return {
        'status': status,
        'identity': result.get('identity') is True,
        'plan': result.get('plan') is True,
        'evidence_manifest': result.get('evidence_manifest') is True,
        'ready': result.get('ready') is True,
        'expected': result.get('expected'),
        'matched': result.get('matched'),
        'missing': list(missing) if isinstance(missing, list) else [],
    }


def _is_exact_preflight(inspection: dict[str, Any]) -> bool:
    return (
        inspection['status'] == 'succeeded'
        and inspection['expected'] == CATALOG_V2_REQUIRED_CONSTRAINT_COUNT
        and inspection['matched'] == 0
        and len(inspection['missing']) == CATALOG_V2_REQUIRED_CONSTRAINT_COUNT
        and inspection['ready'] is False
    )


def _is_exact_postflight(inspection: dict[str, Any]) -> bool:
    return (
        inspection['status'] == 'succeeded'
        and inspection['expected'] == CATALOG_V2_REQUIRED_CONSTRAINT_COUNT
        and inspection['matched'] == CATALOG_V2_REQUIRED_CONSTRAINT_COUNT
        and inspection['missing'] == []
        and inspection['identity'] is True
        and inspection['plan'] is True
        and inspection['evidence_manifest'] is True
        and inspection['ready'] is True
    )


def _report(
    steps: list[dict[str, Any]],
    pre_inspection: dict[str, Any],
    post_inspection: dict[str, Any],
    *,
    classification: str,
    error_type: str | None,
) -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'classification': classification,
        'steps': steps,
        'pre_inspection': pre_inspection,
        'post_inspection': post_inspection,
        'partial_failure': classification != 'PASSED_SCHEMA_BOOTSTRAP',
        'retry_count': 0,
        'rollback_attempted': False,
        'driver_kind': 'neo4j.AsyncDriver',
        'graphiti_driver_constructed': False,
        'error_type': error_type,
    }


async def bootstrap(
    executor: Any,
    store: CatalogNeo4jStore | None = None,
) -> tuple[int, dict[str, Any]]:
    selected = store or CatalogNeo4jStore()
    catalog_v2_constraint_statements(selected if isinstance(selected, CatalogNeo4jStore) else None)
    steps: list[dict[str, Any]] = []
    not_run = _inspection(None, status='not_run')
    try:
        pre = _inspection(
            await selected.inspect_catalog_v2_schema_readiness(executor, include_counts=True)
        )
    except Exception as exc:
        return 1, _report(
            steps,
            _inspection(None),
            not_run,
            classification='FAILED_SCHEMA_PRECONDITION',
            error_type=type(exc).__name__,
        )
    if not _is_exact_preflight(pre):
        return 1, _report(
            steps,
            pre,
            not_run,
            classification='FAILED_SCHEMA_PRECONDITION',
            error_type=None,
        )

    for category, method_name in METHODS:
        try:
            await getattr(selected, method_name)(executor)
        except Exception as exc:
            steps.append({'category': category, 'method': method_name, 'status': 'failed'})
            return 1, _report(
                steps,
                pre,
                not_run,
                classification='FAILED_SCHEMA_BOOTSTRAP',
                error_type=type(exc).__name__,
            )
        steps.append({'category': category, 'method': method_name, 'status': 'succeeded'})

    try:
        post = _inspection(
            await selected.inspect_catalog_v2_schema_readiness(executor, include_counts=True)
        )
    except Exception as exc:
        return 1, _report(
            steps,
            pre,
            _inspection(None),
            classification='FAILED_SCHEMA_BOOTSTRAP',
            error_type=type(exc).__name__,
        )
    classification = (
        'PASSED_SCHEMA_BOOTSTRAP' if _is_exact_postflight(post) else 'FAILED_SCHEMA_BOOTSTRAP'
    )
    return (0 if classification == 'PASSED_SCHEMA_BOOTSTRAP' else 1), _report(
        steps, pre, post, classification=classification, error_type=None
    )


async def bootstrap_catalog_v2_schema(
    executor: Any,
    *,
    store: CatalogNeo4jStore | None = None,
) -> dict[str, Any]:
    """Compatibility API returning exact ready state or raising the store error."""
    code, report = await bootstrap(executor, store)
    if code:
        raise CatalogStoreError(report['classification'], code='neo4j_schema_failed')
    return report['post_inspection']


def _neo4j_config(config: GraphitiConfig) -> tuple[str, str, str | None, str]:
    if config.database.provider != 'neo4j':
        raise ValueError('catalog schema bootstrap requires Neo4j provider')
    provider = config.database.providers.neo4j or Neo4jProviderConfig()
    return (
        os.environ.get('NEO4J_URI', provider.uri),
        os.environ.get('NEO4J_USER', provider.username),
        os.environ.get('NEO4J_PASSWORD', provider.password),
        os.environ.get('NEO4J_DATABASE', provider.database),
    )


async def execute() -> tuple[int, dict[str, Any]]:
    from neo4j import AsyncGraphDatabase  # pyright: ignore[reportMissingImports]

    config = GraphitiConfig()
    uri, user, password, database = _neo4j_config(config)
    if password is None:
        raise ValueError('Neo4j password is required')
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        return await bootstrap(RawNeo4jExecutor(driver, database))
    finally:
        await driver.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return argparse.ArgumentParser(description=__doc__).parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    try:
        code, report = asyncio.run(execute())
    except Exception as exc:
        code = 2
        report = _report(
            [],
            _inspection(None, status='not_run'),
            _inspection(None, status='not_run'),
            classification='FAILED_SCHEMA_BOOTSTRAP',
            error_type=type(exc).__name__,
        )
    print(json.dumps(report, sort_keys=True, separators=(',', ':')))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
