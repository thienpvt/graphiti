"""
Copyright 2026, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import math
from collections.abc import Iterable
from typing import Any, TypeGuard

import httpx
from pydantic import Field

from .client import EmbedderClient, EmbedderConfig

DEFAULT_EMBEDDING_MODEL = 'embeddinggemma'
DEFAULT_EMBEDDING_DIM = 768
DEFAULT_BASE_URL = 'http://localhost:11434'
DEFAULT_TIMEOUT = 60.0


class OllamaEmbedderConfig(EmbedderConfig):
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dim: int = Field(default=DEFAULT_EMBEDDING_DIM, gt=0, frozen=True)
    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = None
    truncate: bool = True
    keep_alive: str | None = None
    timeout: float = Field(default=DEFAULT_TIMEOUT, gt=0)


class OllamaEmbedder(EmbedderClient):
    """Embed text with Ollama's native ``/api/embed`` endpoint."""

    def __init__(
        self,
        config: OllamaEmbedderConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.config = config or OllamaEmbedderConfig()
        self.client = client or httpx.AsyncClient(timeout=self.config.timeout)
        self._owns_client = client is None

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        input_list = self._normalize_input(input_data)
        if not input_list:
            return []
        return (await self._embed(input_list))[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        input_list = self._normalize_input(input_data_list)
        if not input_list:
            return []
        return await self._embed(input_list)

    @staticmethod
    def _normalize_input(
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[str]:
        if isinstance(input_data, str):
            return [input_data]
        if OllamaEmbedder._is_string_list(input_data):
            return input_data
        raise TypeError('Ollama embeddings require a string or a list of strings')

    @staticmethod
    def _is_string_list(input_data: object) -> TypeGuard[list[str]]:
        return isinstance(input_data, list) and all(isinstance(item, str) for item in input_data)

    async def _embed(self, input_data: list[str]) -> list[list[float]]:
        request: dict[str, Any] = {
            'model': self.config.embedding_model,
            'input': input_data,
            'dimensions': self.config.embedding_dim,
            'truncate': self.config.truncate,
        }
        if self.config.keep_alive is not None:
            request['keep_alive'] = self.config.keep_alive

        headers = (
            {'Authorization': f'Bearer {self.config.api_key}'} if self.config.api_key else None
        )
        url = f'{self.config.base_url.rstrip("/")}/api/embed'

        response = await self.client.post(
            url, json=request, headers=headers, timeout=self.config.timeout
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise ValueError('Ollama embed response is not valid JSON') from error

        embeddings = payload.get('embeddings') if isinstance(payload, dict) else None
        if not isinstance(embeddings, list):
            raise ValueError('Ollama embed response must contain an embeddings array')
        if len(embeddings) != len(input_data):
            raise ValueError(
                f'Ollama returned {len(embeddings)} embeddings for {len(input_data)} inputs'
            )

        return [self._validate_embedding(embedding) for embedding in embeddings]

    async def close(self) -> None:
        """Close the internally-created HTTP client."""
        if self._owns_client and not self.client.is_closed:
            await self.client.aclose()

    async def __aenter__(self) -> 'OllamaEmbedder':
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def _validate_embedding(self, embedding: Any) -> list[float]:
        if not isinstance(embedding, list):
            raise ValueError('Ollama embedding must be an array')
        if len(embedding) != self.config.embedding_dim:
            raise ValueError(
                f'Ollama returned embedding dimension {len(embedding)}; '
                f'expected {self.config.embedding_dim}'
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in embedding
        ):
            raise ValueError('Ollama embedding values must be finite numbers')
        return [float(value) for value in embedding]
