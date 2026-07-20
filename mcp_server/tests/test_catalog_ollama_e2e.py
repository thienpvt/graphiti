"""Optional real local Ollama + Neo4j catalog prepare/commit E2E.

Successful records are intentionally retained. This module closes clients only.
"""

from __future__ import annotations

import ast
import importlib
import os
import shutil
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn

import httpx
import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent / 'src'
for _path in (_TESTS_DIR, _SRC_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

ALLOWED_TEST_GROUP = 'oracle-catalog-tool-test'
# Static ban name only. Never use as a request field, Cypher literal, or parameter.
_FORBIDDEN_GROUP_NAME = 'oracle' + '-catalog-v2'
DEFAULT_OLLAMA_URL = 'http://localhost:11434'
DEFAULT_OLLAMA_MODEL = 'qwen3-embedding:latest'
DEFAULT_OLLAMA_DIMENSIONS = 4096
FIXED_NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
_RUN_ID = uuid.uuid4().hex.upper()
RUN_PREFIX = f'OLLAMAE2E{_RUN_ID}'


def _load_module(name: str) -> Any:
    return importlib.import_module(name)


def _attr(module: Any, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        raise RuntimeError(f'catalog E2E symbol unavailable: {name}')
    return value


def _required() -> bool:
    return os.environ.get('CATALOG_OLLAMA_REQUIRED', '').strip().lower() in {
        '1',
        'true',
        'yes',
    }


def _availability_error(reason: str) -> NoReturn:
    assert reason.strip(), 'availability reason must be non-empty'
    if _required():
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def _ollama_settings() -> tuple[str, str, int]:
    base_url = os.environ.get('CATALOG_OLLAMA_URL', DEFAULT_OLLAMA_URL).rstrip('/')
    model = os.environ.get('CATALOG_OLLAMA_MODEL', DEFAULT_OLLAMA_MODEL).strip()
    raw_dimensions = os.environ.get(
        'CATALOG_OLLAMA_DIMENSIONS', str(DEFAULT_OLLAMA_DIMENSIONS)
    ).strip()
    try:
        dimensions = int(raw_dimensions)
    except ValueError:
        _availability_error(f'CATALOG_OLLAMA_DIMENSIONS is not an integer: {raw_dimensions!r}')
    if not model:
        _availability_error('CATALOG_OLLAMA_MODEL is empty')
    if dimensions <= 0:
        _availability_error('CATALOG_OLLAMA_DIMENSIONS must be positive')
    return base_url, model, dimensions


def _neo4j_settings() -> tuple[str, str, str, str]:
    return (
        os.environ.get('NEO4J_URI', 'bolt://localhost:17687'),
        os.environ.get('NEO4J_USER', 'neo4j'),
        os.environ.get('NEO4J_PASSWORD', 'catalogtest123'),
        os.environ.get('NEO4J_DATABASE', 'neo4j'),
    )


def _walk_group_values(value: Any, found: list[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {'group_id', 'g'} and isinstance(nested, str):
                found.append(nested)
            _walk_group_values(nested, found)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _walk_group_values(nested, found)


class AuditedDriver:
    """Reject every observed group parameter except the hardcoded test group."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.group_params: list[str] = []
        self.cypher_texts: list[str] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _audit(self, cypher: Any, params: dict[str, Any] | None) -> None:
        text = cypher if isinstance(cypher, str) else str(cypher)
        self.cypher_texts.append(text)
        if _FORBIDDEN_GROUP_NAME in text:
            raise AssertionError('forbidden group ban name present in Cypher text')
        found: list[str] = []
        _walk_group_values(params or {}, found)
        self.group_params.extend(found)
        invalid = [group for group in found if group != ALLOWED_TEST_GROUP]
        if invalid:
            raise AssertionError(f'non-test group parameter observed: {invalid!r}')

    async def execute_query(self, cypher_query_: Any, **kwargs: Any) -> Any:
        params = kwargs.get('params')
        self._audit(cypher_query_, params if isinstance(params, dict) else {})
        return await self._inner.execute_query(cypher_query_, **kwargs)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        async with self._inner.transaction() as transaction:
            yield AuditedTransaction(transaction, self)


class AuditedTransaction:
    def __init__(self, inner: Any, driver: AuditedDriver) -> None:
        self._inner = inner
        self._driver = driver

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def run(self, query: str, **kwargs: Any) -> Any:
        self._driver._audit(query, kwargs)
        return await self._inner.run(query, **kwargs)


class CountingOllamaEmbedder:
    """Delegate unchanged to real OllamaEmbedder; count native endpoint calls."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.create_calls = 0
        self.create_batch_calls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def create(self, input_data: Any) -> list[float]:
        self.create_calls += 1
        return await self._inner.create(input_data=input_data)

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        self.create_batch_calls += 1
        return await self._inner.create_batch(input_data_list)

    async def close(self) -> None:
        await self._inner.close()


class ForbiddenLLM:
    calls = 0

    async def generate_response(self, *args: Any, **kwargs: Any) -> Any:
        _ = args, kwargs
        self.calls += 1
        raise AssertionError('LLM must not be used by catalog prepare/commit')


class ForbiddenQueue:
    calls = 0

    def __getattr__(self, name: str) -> Any:
        async def _forbidden(*args: Any, **kwargs: Any) -> Any:
            _ = name, args, kwargs
            self.calls += 1
            raise AssertionError('queue must not be used by catalog prepare/commit')

        return _forbidden


async def _probe_ollama() -> CountingOllamaEmbedder:
    if shutil.which('ollama') is None:
        _availability_error('Ollama CLI is not installed or not on PATH')

    base_url, model, dimensions = _ollama_settings()
    timeout = httpx.Timeout(5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f'{base_url}/api/tags')
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        _availability_error(f'Ollama daemon unavailable at {base_url}: {type(exc).__name__}')

    models = payload.get('models') if isinstance(payload, dict) else None
    names = {
        str(item.get('name') or item.get('model'))
        for item in (models if isinstance(models, list) else [])
        if isinstance(item, dict)
    }
    if model not in names:
        _availability_error(f'Ollama model unavailable: {model}')

    ollama_module = _load_module('graphiti_core.embedder.ollama')
    config_type = _attr(ollama_module, 'OllamaEmbedderConfig')
    embedder_type = _attr(ollama_module, 'OllamaEmbedder')
    embedder = CountingOllamaEmbedder(
        embedder_type(
            config=config_type(
                embedding_model=model,
                embedding_dim=dimensions,
                base_url=base_url,
                timeout=10.0,
            )
        )
    )
    try:
        probe = await embedder.create(input_data=['catalog ollama availability probe'])
    except Exception as exc:
        await embedder.close()
        _availability_error(
            f'Ollama native /api/embed unavailable for {model}: {type(exc).__name__}'
        )
    if len(probe) != dimensions:
        await embedder.close()
        _availability_error(
            f'Ollama embedding dimension mismatch: expected {dimensions}, got {len(probe)}'
        )
    return embedder


async def _probe_neo4j() -> tuple[Any, AuditedDriver]:
    try:
        driver_type = _attr(_load_module('graphiti_core.driver.neo4j_driver'), 'Neo4jDriver')
    except Exception as exc:
        _availability_error(f'Neo4j driver import failed: {type(exc).__name__}')
    uri, user, password, database = _neo4j_settings()
    raw = driver_type(uri=uri, user=user, password=password, database=database)
    audited = AuditedDriver(raw)
    try:
        await audited.execute_query('RETURN 1 AS ok', params={})
    except Exception as exc:
        await raw.close()
        _availability_error(f'Neo4j unavailable at {uri}: {type(exc).__name__}')
    return raw, audited


def _catalog_types() -> SimpleNamespace:
    config = _load_module('config.schema')
    batch = _load_module('models.catalog_batch')
    entities = _load_module('models.catalog_entities')
    prepare = _load_module('models.catalog_prepare')
    identity = _load_module('services.catalog_identity')
    service = _load_module('services.catalog_service')
    return SimpleNamespace(
        CatalogConfig=_attr(config, 'CatalogConfig'),
        GetCatalogIngestStatusRequest=_attr(batch, 'GetCatalogIngestStatusRequest'),
        CatalogEntityItem=_attr(entities, 'CatalogEntityItem'),
        GetCatalogBatchManifestRequest=_attr(entities, 'GetCatalogBatchManifestRequest'),
        ResolveEntityRef=_attr(entities, 'ResolveEntityRef'),
        ResolveTypedEntitiesRequest=_attr(entities, 'ResolveTypedEntitiesRequest'),
        VerifyCatalogBatchRequest=_attr(entities, 'VerifyCatalogBatchRequest'),
        VerifyEntityRef=_attr(entities, 'VerifyEntityRef'),
        CommitPreparedCatalogBatchRequest=_attr(prepare, 'CommitPreparedCatalogBatchRequest'),
        PrepareCatalogBatchRequest=_attr(prepare, 'PrepareCatalogBatchRequest'),
        batch_request_sha256=_attr(identity, 'batch_request_sha256'),
        catalog_entity_uuid=_attr(identity, 'catalog_entity_uuid'),
        catalog_prepared_plan_uuid=_attr(identity, 'catalog_prepared_plan_uuid'),
        CatalogService=_attr(service, 'CatalogService'),
    )


def _static_call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def test_module_hardcodes_allowed_test_group_only():
    assert ALLOWED_TEST_GROUP == 'oracle-catalog-tool-test'
    source = Path(__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) for target in targets):
            continue
        value_node = node.value
        if value_node is None:
            continue
        try:
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            continue
        if value == _FORBIDDEN_GROUP_NAME:
            raise AssertionError('forbidden group must exist only as a split/static ban name')


def test_availability_reason_contract(monkeypatch: pytest.MonkeyPatch):
    reasons: list[str] = []

    def _skip(reason: str) -> None:
        reasons.append(reason)
        raise RuntimeError(reason)

    monkeypatch.delenv('CATALOG_OLLAMA_REQUIRED', raising=False)
    monkeypatch.setattr(pytest, 'skip', _skip)
    with pytest.raises(RuntimeError):
        _availability_error('local dependency unavailable')
    assert reasons == ['local dependency unavailable']

    monkeypatch.setenv('CATALOG_OLLAMA_REQUIRED', '1')
    with pytest.raises(pytest.fail.Exception):
        _availability_error('required local dependency unavailable')
    assert reasons == ['local dependency unavailable']

    with pytest.raises(AssertionError, match='non-empty'):
        _availability_error('')


def test_ollama_e2e_never_shells_canary_runner():
    source = Path(__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    calls = _static_call_names(tree)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert 'subprocess' not in imports
    assert 'system' not in calls
    assert 'Popen' not in calls
    assert 'check_call' not in calls
    assert 'check_output' not in calls
    assert not any('canary' in name.lower() for name in calls)


def test_ollama_e2e_has_no_cleanup_or_delete_execution():
    source = Path(__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    calls = _static_call_names(tree)
    assert 'clear_graph' not in calls
    assert not any(name.startswith(('delete', 'remove', 'cleanup', 'teardown')) for name in calls)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value.upper()
        if 'MATCH ' in text or 'CREATE ' in text or 'MERGE ' in text:
            assert ' DELETE ' not in f' {text} '
            assert ' DETACH ' not in f' {text} '
            assert ' DROP ' not in f' {text} '


@pytest.mark.asyncio
async def test_ollama_e2e_skips_when_unavailable():
    """Real prepare, token-only commit/replay, resolve, status, manifest, verify."""
    embedder = await _probe_ollama()
    raw_driver: Any | None = None
    try:
        raw_driver, driver = await _probe_neo4j()
        types = _catalog_types()
        llm = ForbiddenLLM()
        queue = ForbiddenQueue()
        client = SimpleNamespace(driver=driver, embedder=embedder, llm_client=llm)
        service = types.CatalogService(
            catalog_config=types.CatalogConfig(
                enabled=True,
                reads_enabled=True,
                uuid_namespace=str(FIXED_NAMESPACE),
            ),
            queue_service=queue,
        )

        batch_id = f'ollama-e2e-{_RUN_ID.lower()}'
        entity_name = f'OLLAMA_E2E_{_RUN_ID}'
        graph_key = f'TABLE::FE::ORCL.HR.{entity_name}'
        entity = types.CatalogEntityItem(
            entity_type='Table',
            graph_key=graph_key,
            name_raw=entity_name,
            name_canonical=entity_name.lower(),
            database_qualified_name=f'ORCL.HR.{entity_name}',
            summary=f'Run-scoped Ollama native embedding E2E table {_RUN_ID}',
            attributes={'run_id': _RUN_ID, 'suite': 'catalog-ollama-e2e'},
            confidence=1.0,
        )
        request = types.PrepareCatalogBatchRequest(
            identity_schema_version='catalog-v2',
            system_key='FE',
            group_id=ALLOWED_TEST_GROUP,
            batch_id=batch_id,
            entities=[entity],
            edges=[],
            provenance=None,
            request_sha256=None,
            catalog_sha256=_RUN_ID.lower() * 2,
            atomic=True,
        )
        expected_request_sha = types.batch_request_sha256(request)
        expected_entity_uuid = types.catalog_entity_uuid(
            FIXED_NAMESPACE,
            ALLOWED_TEST_GROUP,
            entity.entity_type,
            entity.graph_key,
        )
        expected_plan_id = f'{batch_id}|{expected_request_sha}'
        expected_plan_uuid = types.catalog_prepared_plan_uuid(
            FIXED_NAMESPACE,
            ALLOWED_TEST_GROUP,
            expected_plan_id,
        )

        probe_calls = embedder.create_calls
        prepared = await service.prepare_catalog_batch(client=client, request=request)
        assert prepared.error_code is None, prepared.error_message
        assert prepared.plan_token
        assert prepared.plan_uuid == expected_plan_uuid
        assert prepared.request_sha256 == expected_request_sha
        assert prepared.entity_count == 1
        assert embedder.create_calls == probe_calls + 1

        calls_after_prepare = embedder.create_calls
        commit_request = types.CommitPreparedCatalogBatchRequest(
            plan_token=prepared.plan_token,
            expected_request_sha256=expected_request_sha,
        )
        assert set(commit_request.model_dump(exclude_none=True)) == {
            'plan_token',
            'expected_request_sha256',
        }
        committed = await service.commit_prepared_catalog_batch(
            client=client,
            request=commit_request,
        )
        assert committed.error_code is None, committed.error_message
        assert committed.state == 'COMMITTED'
        assert committed.plan_uuid == expected_plan_uuid
        assert committed.request_sha256 == expected_request_sha
        assert committed.manifest_sha256
        assert embedder.create_calls == calls_after_prepare

        replay = await service.commit_prepared_catalog_batch(client=client, request=commit_request)
        assert replay.error_code is None, replay.error_message
        assert replay.state == 'COMMITTED'
        assert replay.plan_uuid == committed.plan_uuid
        assert replay.request_sha256 == committed.request_sha256
        assert replay.artifact_sha256 == committed.artifact_sha256
        assert replay.batch_uuid == committed.batch_uuid
        assert replay.manifest_sha256 == committed.manifest_sha256
        assert replay.committed_created == committed.committed_created
        assert replay.committed_updated == committed.committed_updated
        assert replay.committed_unchanged == committed.committed_unchanged
        assert embedder.create_calls == calls_after_prepare

        resolved = await service.resolve_typed_entities(
            client=client,
            request=types.ResolveTypedEntitiesRequest(
                identity_schema_version='catalog-v2',
                system_key='FE',
                group_id=ALLOWED_TEST_GROUP,
                entities=[types.ResolveEntityRef(entity_type='Table', graph_key=graph_key)],
            ),
        )
        assert len(resolved.results) == 1
        result = resolved.results[0]
        assert result.found is True
        assert result.status == 'found'
        assert result.uuid == expected_entity_uuid
        assert result.has_name_embedding is True
        assert 'missing_embedding' not in result.anomalies

        status = await service.get_catalog_ingest_status(
            client=client,
            request=types.GetCatalogIngestStatusRequest(
                group_id=ALLOWED_TEST_GROUP,
                batch_id=batch_id,
            ),
        )
        assert status.found is True
        assert status.status == 'committed'
        assert status.request_sha256 == expected_request_sha
        assert status.entity_count == 1

        manifest = await service.get_catalog_batch_manifest(
            client=client,
            request=types.GetCatalogBatchManifestRequest(
                group_id=ALLOWED_TEST_GROUP,
                batch_id=batch_id,
            ),
        )
        assert manifest.error_code is None, manifest.error_message
        assert manifest.found is True
        assert manifest.request_sha256 == expected_request_sha
        assert manifest.manifest_sha256 == committed.manifest_sha256
        assert manifest.entity_count == 1
        assert len(manifest.entities) == 1
        assert manifest.entities[0].uuid == expected_entity_uuid
        assert manifest.entities[0].graph_key == graph_key

        verified = await service.verify_catalog_batch(
            client=client,
            request=types.VerifyCatalogBatchRequest(
                identity_schema_version='catalog-v2',
                system_key='FE',
                group_id=ALLOWED_TEST_GROUP,
                batch_id=batch_id,
                entities=[types.VerifyEntityRef(entity_type='Table', graph_key=graph_key)],
            ),
        )
        assert verified.error_code is None, verified.error_message
        assert verified.found is True
        assert verified.manifest_sha256 == committed.manifest_sha256
        assert verified.entities.expected == 1
        assert verified.entities.found == 1
        assert verified.missing == []
        assert verified.anomalies == []
        assert verified.entities.missing_embedding == []

        assert llm.calls == 0
        assert queue.calls == 0
        assert driver.group_params
        assert set(driver.group_params) == {ALLOWED_TEST_GROUP}
        assert all(_FORBIDDEN_GROUP_NAME not in query for query in driver.cypher_texts)
        assert embedder.create_batch_calls == 0
    finally:
        if raw_driver is not None:
            await raw_driver.close()
        await embedder.close()
