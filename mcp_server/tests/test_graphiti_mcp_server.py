"""MCP registration for prepare/commit/discard tools (PLAN-20 / 03A-05)."""

from __future__ import annotations

import importlib

import pytest


def _mcp_server():
    return importlib.import_module('graphiti_mcp_server')


PREPARE_TOOLS = (
    'prepare_catalog_batch',
    'commit_prepared_catalog_batch',
    'discard_prepared_catalog_batch',
)


@pytest.mark.asyncio
async def test_prepare_commit_discard_tools_registered():
    server = _mcp_server()
    for name in PREPARE_TOOLS:
        assert hasattr(server, name), name
        assert callable(getattr(server, name)), name
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    for name in PREPARE_TOOLS:
        assert name in names
    assert 'upsert_catalog_batch' in names


@pytest.mark.asyncio
async def test_prepare_tools_in_catalog_tool_names_for_safe_errors():
    server = _mcp_server()
    for name in PREPARE_TOOLS:
        assert name in server.CATALOG_TOOL_NAMES
    assert 'upsert_catalog_batch' in server.CATALOG_TOOL_NAMES
    assert 'get_catalog_capabilities' in server.CATALOG_TOOL_NAMES
    # 8 prior catalog + 3 prepare tools = 11
    assert len(server.CATALOG_TOOL_NAMES) == 11


@pytest.mark.asyncio
async def test_upsert_catalog_batch_still_registered():
    server = _mcp_server()
    assert hasattr(server, 'upsert_catalog_batch')
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    assert 'upsert_catalog_batch' in names
