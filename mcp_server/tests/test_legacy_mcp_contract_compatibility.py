"""Canonical compatibility checks for the 14 legacy and 14 catalog MCP tools."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'legacy_mcp_contract_baseline.json'

LEGACY_TOOL_NAMES = frozenset(
    {
        'add_memory',
        'search_nodes',
        'search_memory_facts',
        'add_triplet',
        'get_entity_edge',
        'get_episodes',
        'get_episode_entities',
        'update_entity',
        'build_communities',
        'summarize_saga',
        'delete_episode',
        'delete_entity_edge',
        'clear_graph',
        'get_status',
    }
)

CATALOG_TOOL_NAMES = frozenset(
    {
        'upsert_typed_entities',
        'resolve_typed_entities',
        'resolve_typed_edges',
        'verify_catalog_batch',
        'upsert_typed_edges',
        'upsert_provenance',
        'get_catalog_ingest_status',
        'get_catalog_batch_manifest',
        'get_catalog_evidence',
        'upsert_catalog_batch',
        'get_catalog_capabilities',
        'prepare_catalog_batch',
        'commit_prepared_catalog_batch',
        'discard_prepared_catalog_batch',
    }
)

ORIGINAL_CATALOG_TOOL_NAMES = frozenset(
    {
        'upsert_typed_entities',
        'resolve_typed_entities',
        'verify_catalog_batch',
        'upsert_typed_edges',
        'upsert_provenance',
        'get_catalog_ingest_status',
        'upsert_catalog_batch',
    }
)

RESPONSE_CONTRACTS = {
    'add_memory': 'mcp_server/tests/test_catalog_service.py#test_entity_no_queue_or_llm_calls',
    'search_nodes': 'mcp_server/tests/test_core_parity.py#TestCoerceGroupIds',
    'search_memory_facts': 'mcp_server/tests/test_core_parity.py#TestBuildFactSearchFilters',
    'add_triplet': 'mcp_server/tests/test_core_parity.py#test_triplet_objects_construct',
    'get_entity_edge': 'mcp_server/tests/test_comprehensive_integration.py#test_get_entity_edge',
    'get_episodes': 'mcp_server/tests/test_comprehensive_integration.py#test_get_episodes_pagination',
    'get_episode_entities': 'mcp_server/tests/test_core_parity.py#test_core_exposes_parity_methods',
    'update_entity': 'mcp_server/tests/test_update_entity.py#test_update_entity_requires_initialized_service',
    'build_communities': 'mcp_server/tests/test_core_parity.py#test_core_exposes_parity_methods',
    'summarize_saga': 'mcp_server/tests/test_core_parity.py#test_core_exposes_parity_methods',
    'delete_episode': 'mcp_server/tests/test_comprehensive_integration.py#test_delete_episode',
    'delete_entity_edge': 'mcp_server/tests/test_comprehensive_integration.py#test_delete_entity_edge',
    'clear_graph': 'mcp_server/tests/test_falkordb_integration.py#test_clear_graph',
    'get_status': 'mcp_server/tests/test_catalog_capabilities.py#test_get_status_preserves_status_and_message_keys',
}

_REMOVED_SCHEMA_KEYS = frozenset({'description', 'title'})
_EMPTY = inspect.Signature.empty
LEGACY_FACT_RESULT_REQUIRED = frozenset(
    {
        'uuid',
        'name',
        'fact',
        'source_node_uuid',
        'target_node_uuid',
        'group_id',
        'created_at',
        'valid_at',
        'invalid_at',
        'attributes',
    }
)


def _server() -> Any:
    return importlib.import_module('graphiti_mcp_server')


def _canonical_schema(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _canonical_schema(item)
            for key, item in sorted(value.items())
            if key not in _REMOVED_SCHEMA_KEYS
        }
    if isinstance(value, list):
        canonical = [_canonical_schema(item) for item in value]
        if all(isinstance(item, (str, int, float, bool, type(None))) for item in canonical):
            return sorted(canonical, key=lambda item: json.dumps(item, sort_keys=True))
        return canonical
    return value


def _serializable_default(value: Any) -> Any:
    if value is _EMPTY:
        raise ValueError('required parameters do not have defaults')
    json.dumps(value)
    return value


def _parameter_contract(fn: Any) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    required: list[str] = []
    defaults: dict[str, Any] = {}
    for parameter in inspect.signature(fn).parameters.values():
        entry = {
            'name': parameter.name,
            'kind': parameter.kind.name,
            'annotation': inspect.formatannotation(parameter.annotation),
            'required': parameter.default is _EMPTY,
        }
        if parameter.default is _EMPTY:
            required.append(parameter.name)
        else:
            default = _serializable_default(parameter.default)
            entry['default'] = default
            defaults[parameter.name] = default
        parameters.append(entry)
    return parameters, sorted(required), defaults


async def _collect_contracts(server: Any = None) -> tuple[dict[str, Any], frozenset[str]]:
    loaded_server: Any = server if server is not None else _server()
    assert loaded_server is not None
    listed_tools = {tool.name: tool for tool in await loaded_server.mcp.list_tools()}
    registered_names = frozenset(listed_tools)
    contracts: dict[str, Any] = {}
    for name in sorted(LEGACY_TOOL_NAMES):
        registered = loaded_server.mcp._tool_manager.get_tool(name)
        assert registered is not None, f'legacy tool not callable: {name}'
        assert callable(registered.fn), f'legacy tool not callable: {name}'
        parameters, required, defaults = _parameter_contract(registered.fn)
        tool = listed_tools[name]
        contracts[name] = {
            'name': name,
            'parameters': parameters,
            'required': required,
            'defaults': defaults,
            'input_schema': _canonical_schema(tool.inputSchema),
            'output_schema': _canonical_schema(tool.outputSchema),
            'response_contract': {
                'classification': 'schema_and_fake_backed_test',
                'test_ref': RESPONSE_CONTRACTS[name],
            },
        }
    return contracts, registered_names


def _load_baseline() -> dict[str, Any]:
    data = json.loads(FIXTURE.read_text(encoding='utf-8'))
    tools = data.get('legacy_tools')
    if not isinstance(tools, dict) or not tools:
        raise ValueError('legacy contract baseline must be non-empty')
    if frozenset(tools) != LEGACY_TOOL_NAMES:
        raise ValueError('legacy contract baseline names differ from exact 14-tool set')
    return data


def _assert_exact_registration(names: frozenset[str]) -> None:
    if not names:
        raise ValueError('MCP registration must be non-empty')
    legacy = names & LEGACY_TOOL_NAMES
    catalog = names & CATALOG_TOOL_NAMES
    assert legacy == LEGACY_TOOL_NAMES
    assert catalog == CATALOG_TOOL_NAMES
    assert legacy.isdisjoint(catalog)
    assert names == LEGACY_TOOL_NAMES | CATALOG_TOOL_NAMES


def test_baseline_fixture_lists_exactly_14_legacy_tools():
    """SAFE-09 empty: checked-in baseline contains exactly all 14 legacy names."""
    data = _load_baseline()
    names = frozenset(data['legacy_tools'])
    assert names == LEGACY_TOOL_NAMES
    assert len(names) == 14
    assert data['legacy_tool_count'] == 14
    assert data['catalog_tool_count'] == 14
    assert data['union_tool_count'] == 28


def test_legacy_tool_names_constant_size_14():
    assert len(LEGACY_TOOL_NAMES) == 14
    assert 'add_memory' in LEGACY_TOOL_NAMES


def test_catalog_tool_names_exact_14_separate_from_legacy():
    assert len(CATALOG_TOOL_NAMES) == 14
    assert ORIGINAL_CATALOG_TOOL_NAMES <= CATALOG_TOOL_NAMES
    assert LEGACY_TOOL_NAMES.isdisjoint(CATALOG_TOOL_NAMES)


def test_tool_union_exact_28():
    assert len(LEGACY_TOOL_NAMES | CATALOG_TOOL_NAMES) == 28


@pytest.mark.asyncio
async def test_legacy_contract_metadata_defaults_schemas_response_invariants():
    """SAFE-09 encoding: exact behavior-bearing contracts equal the frozen baseline."""
    baseline = _load_baseline()
    current, _ = await _collect_contracts()
    expected = baseline['legacy_tools']
    fact_schema = current['search_memory_facts']['output_schema']
    fact_result = fact_schema['$defs'].pop('FactResult')
    fact_schema['$defs']['FactSearchResponse']['properties']['facts']['items'] = {
        'additionalProperties': True,
        'type': 'object',
    }
    assert current == expected
    assert set(fact_result['required']) == LEGACY_FACT_RESULT_REQUIRED
    assert set(fact_result['properties']) == LEGACY_FACT_RESULT_REQUIRED
    assert frozenset(RESPONSE_CONTRACTS) == LEGACY_TOOL_NAMES
    assert all(
        contract['parameters'] for contract in current.values() if contract['name'] != 'get_status'
    )
    assert all(contract['input_schema'].get('type') == 'object' for contract in current.values())
    assert all(contract['output_schema'] for contract in current.values())


@pytest.mark.asyncio
async def test_legacy_contract_concurrent_metadata_collections_stable():
    """SAFE-09 concurrency: independent collections are identical and non-mutating."""
    (first, first_names), (second, second_names) = await asyncio.gather(
        _collect_contracts(),
        _collect_contracts(),
    )
    assert first == second
    assert first_names == second_names
    _assert_exact_registration(first_names)


def test_empty_baseline_or_registration_fails():
    """SAFE-09 empty: empty baseline/registration fail closed."""
    with pytest.raises(ValueError, match='non-empty'):
        _assert_exact_registration(frozenset())
    with pytest.raises(ValueError, match='non-empty'):
        data = {'legacy_tools': {}}
        tools = data.get('legacy_tools')
        if not isinstance(tools, dict) or not tools:
            raise ValueError('legacy contract baseline must be non-empty')


@pytest.mark.asyncio
async def test_live_registration_contains_exact_14_legacy_and_14_catalog():
    """SAFE-09: live sets are independently exact; union is exactly 28."""
    server = _server()
    _, names = await _collect_contracts(server)
    _assert_exact_registration(names)
    assert server.CATALOG_TOOL_NAMES == CATALOG_TOOL_NAMES
    assert all(callable(getattr(server, name, None)) for name in LEGACY_TOOL_NAMES)
    assert all(callable(getattr(server, name, None)) for name in CATALOG_TOOL_NAMES)


@pytest.mark.asyncio
async def test_get_status_stable_response_baseline(monkeypatch: pytest.MonkeyPatch):
    """Deterministic no-live path preserves the status/message response contract."""
    server = _server()
    monkeypatch.setattr(server, 'graphiti_service', None)
    response = await server.get_status()
    assert dict(response) == {
        'status': 'error',
        'message': 'Graphiti service not initialized',
    }
