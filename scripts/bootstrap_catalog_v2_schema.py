#!/usr/bin/env python3
"""Bootstrap only the fixed Catalog-v2 Neo4j constraints."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MCP_SRC = ROOT / 'mcp_server' / 'src'
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from config.schema import GraphitiConfig, Neo4jProviderConfig  # noqa: E402
from services.catalog_store import CatalogNeo4jStore  # noqa: E402

SCHEMA_VERSION = 'catalog-v2-schema-bootstrap-report-v2'
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


def _report(
    steps: list[dict[str, Any]],
    inspection: dict[str, Any],
    *,
    error_type: str | None,
) -> dict[str, Any]:
    succeeded = len(steps) == len(METHODS) and all(step['status'] == 'succeeded' for step in steps)
    ready = inspection.get('ready') is True
    return {
        'schema_version': SCHEMA_VERSION,
        'classification': 'PASSED_SCHEMA_BOOTSTRAP'
        if succeeded and ready
        else 'FAILED_SCHEMA_BOOTSTRAP',
        'steps': steps,
        'post_inspection': inspection,
        'partial_failure': not (succeeded and ready),
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
    catalog_store = store or CatalogNeo4jStore()
    steps: list[dict[str, Any]] = []
    error_type: str | None = None
    for category, method_name in METHODS:
        try:
            await getattr(catalog_store, method_name)(executor)
        except Exception as exc:
            error_type = type(exc).__name__
            steps.append({'category': category, 'method': method_name, 'status': 'failed'})
            break
        steps.append({'category': category, 'method': method_name, 'status': 'succeeded'})

    inspection: dict[str, Any]
    try:
        result = await catalog_store.inspect_catalog_v2_schema_readiness(executor)
        inspection = {
            'status': 'succeeded',
            'identity': result.get('identity') is True,
            'plan': result.get('plan') is True,
            'evidence_manifest': result.get('evidence_manifest') is True,
            'ready': result.get('ready') is True,
        }
    except Exception as exc:
        error_type = error_type or type(exc).__name__
        inspection = {
            'status': 'failed',
            'identity': False,
            'plan': False,
            'evidence_manifest': False,
            'ready': False,
        }
    report = _report(steps, inspection, error_type=error_type)
    return (0 if report['classification'] == 'PASSED_SCHEMA_BOOTSTRAP' else 1), report


async def execute() -> tuple[int, dict[str, Any]]:
    from neo4j import AsyncGraphDatabase  # pyright: ignore[reportMissingImports]

    config = GraphitiConfig()
    uri, user, password, database = _neo4j_config(config)
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
        report = _report([], {'status': 'not_run', 'ready': False}, error_type=type(exc).__name__)
    print(json.dumps(report, sort_keys=True, separators=(',', ':')))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
