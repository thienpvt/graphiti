from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


class Neo4jLikeDateTime:
    def iso_format(self) -> str:
        return '2026-07-17T12:00:00.000000000+00:00'


def _load_formatting(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    graphiti = ModuleType('graphiti_core')
    edges = ModuleType('graphiti_core.edges')
    nodes = ModuleType('graphiti_core.nodes')
    edges.EntityEdge = object
    nodes.EntityNode = object
    models = ModuleType('models')
    response_types = ModuleType('models.response_types')
    response_types.EdgeResult = lambda **kwargs: kwargs
    response_types.NodeResult = lambda **kwargs: kwargs
    for name, module in {
        'graphiti_core': graphiti,
        'graphiti_core.edges': edges,
        'graphiti_core.nodes': nodes,
        'models': models,
        'models.response_types': response_types,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    path = Path(__file__).resolve().parents[1] / 'src' / 'utils' / 'formatting.py'
    spec = importlib.util.spec_from_file_location('formatting_under_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_format_node_result_serializes_nested_driver_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    formatting = _load_formatting(monkeypatch)
    node = SimpleNamespace(
        uuid='node-1',
        name='TABLE::TEST.ITEM',
        group_id='test',
        labels=['Table'],
        created_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        summary='item',
        attributes={'updated_at': Neo4jLikeDateTime(), 'name_embedding': [1.0]},
    )

    assert formatting.format_node_result(node) == {
        'uuid': 'node-1',
        'name': 'TABLE::TEST.ITEM',
        'labels': ['Table'],
        'created_at': '2026-07-17T00:00:00+00:00',
        'summary': 'item',
        'group_id': 'test',
        'attributes': {'updated_at': '2026-07-17T12:00:00.000000000+00:00'},
    }


def test_format_fact_result_serializes_nested_driver_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    formatting = _load_formatting(monkeypatch)
    edge = SimpleNamespace(
        uuid='edge-1',
        source_node_uuid='node-1',
        target_node_uuid='node-2',
        name='Contains',
        fact='Table contains column.',
        group_id='test',
        created_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        valid_at=None,
        invalid_at=None,
        attributes={'updated_at': Neo4jLikeDateTime(), 'fact_embedding': [1.0]},
    )

    assert formatting.format_fact_result(edge) == {
        'uuid': 'edge-1',
        'name': 'Contains',
        'fact': 'Table contains column.',
        'source_node_uuid': 'node-1',
        'target_node_uuid': 'node-2',
        'group_id': 'test',
        'created_at': '2026-07-17T00:00:00+00:00',
        'valid_at': None,
        'invalid_at': None,
        'attributes': {'updated_at': '2026-07-17T12:00:00.000000000+00:00'},
    }
