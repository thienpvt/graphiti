"""Formatting utilities for Graphiti MCP Server."""

from typing import Any

from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode

from models.response_types import EdgeResult, NodeResult


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    iso_format = getattr(value, 'iso_format', None)
    if callable(iso_format):
        return iso_format()
    isoformat = getattr(value, 'isoformat', None)
    if callable(isoformat):
        return isoformat()
    return str(value)


def to_node_result(node: EntityNode) -> NodeResult:
    """Build a NodeResult TypedDict from an EntityNode, dropping embeddings."""
    attrs = node.attributes if node.attributes else {}
    attrs = {
        key: _json_safe(value) for key, value in attrs.items() if 'embedding' not in key.lower()
    }
    return NodeResult(
        uuid=node.uuid,
        name=node.name,
        labels=node.labels if node.labels else [],
        created_at=node.created_at.isoformat() if node.created_at else None,
        summary=node.summary,
        group_id=node.group_id,
        attributes=attrs,
    )


def to_edge_result(edge: EntityEdge) -> EdgeResult:
    """Build an EdgeResult TypedDict from an EntityEdge."""
    return EdgeResult(
        uuid=edge.uuid,
        name=edge.name,
        fact=edge.fact,
        source_node_uuid=edge.source_node_uuid,
        target_node_uuid=edge.target_node_uuid,
        group_id=edge.group_id,
        created_at=edge.created_at.isoformat() if edge.created_at else None,
        valid_at=edge.valid_at.isoformat() if edge.valid_at else None,
        invalid_at=edge.invalid_at.isoformat() if edge.invalid_at else None,
    )


def format_node_result(node: EntityNode) -> dict[str, Any]:
    """Format an entity node into a readable result without embedding vectors."""
    return dict(to_node_result(node))


def format_fact_result(edge: EntityEdge) -> dict[str, Any]:
    """Format an entity edge into a readable result without embedding vectors."""
    result = dict(to_edge_result(edge))
    result['attributes'] = {
        key: _json_safe(value)
        for key, value in (edge.attributes or {}).items()
        if 'embedding' not in key.lower()
    }
    return result
