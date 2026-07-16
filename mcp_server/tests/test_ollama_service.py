"""Tests for Ollama embedder startup handling."""

from unittest.mock import AsyncMock, patch

import pytest

from config.schema import GraphitiConfig
from graphiti_mcp_server import GraphitiService


@pytest.mark.asyncio
async def test_embedder_factory_error_aborts_initialization() -> None:
    service = GraphitiService(GraphitiConfig())

    with (
        patch(
            'graphiti_mcp_server.EmbedderFactory.create',
            side_effect=ValueError('invalid embedder'),
        ),
        pytest.raises(ValueError, match='invalid embedder'),
    ):
        await service.initialize()

    assert service.client is None


@pytest.mark.asyncio
async def test_service_close_closes_client_once() -> None:
    service = GraphitiService(GraphitiConfig())
    client = AsyncMock()
    service.client = client

    await service.close()
    await service.close()

    client.close.assert_awaited_once()
    assert service.client is None
