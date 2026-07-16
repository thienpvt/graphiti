#!/usr/bin/env python3
"""Unit tests for service factory provider detection and client routing."""

import sys
from pathlib import Path

import pytest

# Add the src directory to the path (mirrors the other factory tests)
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from graphiti_core.embedder.ollama import OllamaEmbedder
from graphiti_core.llm_client import OpenAIClient
from graphiti_core.llm_client.azure_openai_client import AzureOpenAILLMClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

from config.schema import (
    AzureOpenAIProviderConfig,
    EmbedderConfig,
    EmbedderProvidersConfig,
    LLMConfig,
    LLMProvidersConfig,
    OllamaProviderConfig,
    OpenAIProviderConfig,
)
from services.factories import (
    EmbedderFactory,
    LLMClientFactory,
    is_non_openai_provider,
    reasoning_effort_for_model,
)


class TestIsNonOpenAIProvider:
    """Tests for the base_url-based provider detection."""

    @pytest.mark.parametrize(
        'base_url',
        [
            None,
            '',
            'https://api.openai.com/v1',
            'https://api.openai.com',
            'https://my-resource.openai.azure.com',
        ],
    )
    def test_official_or_unset_is_openai(self, base_url):
        """Unset, empty, or official OpenAI/Azure endpoints are treated as OpenAI."""
        assert is_non_openai_provider(base_url) is False

    @pytest.mark.parametrize(
        'base_url',
        [
            'http://localhost:11434/v1',  # Ollama
            'http://localhost:1234/v1',  # LM Studio
            'http://localhost:8000/v1',  # vLLM
            'https://my-proxy.internal/v1',
        ],
    )
    def test_compatible_providers_are_non_openai(self, base_url):
        """OpenAI-compatible third-party endpoints are detected as non-OpenAI."""
        assert is_non_openai_provider(base_url) is True


class TestLLMClientFactoryRouting:
    """Tests that the factory selects the right client based on base_url."""

    @staticmethod
    def _config(api_url: str) -> LLMConfig:
        return LLMConfig(
            provider='openai',
            model='gpt-5.5',
            providers=LLMProvidersConfig(
                openai=OpenAIProviderConfig(api_key='test-key', api_url=api_url)
            ),
        )

    def test_official_openai_uses_openai_client(self):
        client = LLMClientFactory.create(self._config('https://api.openai.com/v1'))
        assert isinstance(client, OpenAIClient)
        assert not isinstance(client, OpenAIGenericClient)

    def test_ollama_uses_generic_client(self):
        client = LLMClientFactory.create(self._config('http://localhost:11434/v1'))
        assert isinstance(client, OpenAIGenericClient)


class TestOllamaEmbedderFactory:
    """Tests native Ollama embedder construction."""

    @staticmethod
    def _config(provider: OllamaProviderConfig | None = None) -> EmbedderConfig:
        return EmbedderConfig(
            provider='ollama',
            model='nomic-embed-text',
            dimensions=768,
            providers=EmbedderProvidersConfig(ollama=provider),
        )

    def test_local_ollama_needs_no_api_key(self):
        client = EmbedderFactory.create(
            self._config(
                OllamaProviderConfig(
                    api_url='http://ollama:11434',
                    truncate=False,
                    keep_alive='5m',
                    timeout=90,
                )
            )
        )

        assert isinstance(client, OllamaEmbedder)
        assert client.config.embedding_model == 'nomic-embed-text'
        assert client.config.embedding_dim == 768
        assert client.config.base_url == 'http://ollama:11434'
        assert client.config.api_key is None
        assert client.config.truncate is False
        assert client.config.keep_alive == '5m'
        assert client.config.timeout == 90

    def test_api_key_is_forwarded(self):
        client = EmbedderFactory.create(
            self._config(OllamaProviderConfig(api_url='https://ollama.com', api_key='secret'))
        )

        assert isinstance(client, OllamaEmbedder)
        assert client.config.api_key == 'secret'

    def test_missing_provider_config_fails(self):
        with pytest.raises(ValueError, match='Ollama provider configuration not found'):
            EmbedderFactory.create(self._config())


class TestLLMClientReasoningEffort:
    """The OpenAI factory selects reasoning effort by model family."""

    @staticmethod
    def _config(model: str) -> LLMConfig:
        return LLMConfig(
            provider='openai',
            model=model,
            providers=LLMProvidersConfig(
                openai=OpenAIProviderConfig(api_key='test-key', api_url='https://api.openai.com/v1')
            ),
        )

    def test_gpt_5_5_uses_reasoning_none(self):
        """gpt-5.5 (the default) runs with reasoning off."""
        client = LLMClientFactory.create(self._config('gpt-5.5'))
        assert isinstance(client, OpenAIClient)
        assert client.reasoning == 'none'

    def test_earlier_reasoning_model_uses_minimal(self):
        """Earlier gpt-5 reasoning models keep the historical 'minimal' floor."""
        client = LLMClientFactory.create(self._config('gpt-5'))
        assert isinstance(client, OpenAIClient)
        assert client.reasoning == 'minimal'


class TestReasoningEffortForModel:
    """The shared effort selector used by both the OpenAI and Azure branches."""

    @pytest.mark.parametrize(
        ('model', 'expected'),
        [
            ('gpt-5.5', 'none'),
            ('gpt-5.5-2026-04-23', 'none'),
            ('gpt-5', 'minimal'),
            ('gpt-5-mini', 'minimal'),
            ('gpt-5.4-mini', 'minimal'),
            ('o1', 'minimal'),
            ('o3-mini', 'minimal'),
            ('gpt-4.1', None),
            ('gpt-4o-mini', None),
        ],
    )
    def test_effort_selection(self, model, expected):
        assert reasoning_effort_for_model(model) == expected


class TestAzureReasoningEffort:
    """The Azure OpenAI branch applies the same model-tied reasoning effort."""

    @staticmethod
    def _config(model: str) -> LLMConfig:
        return LLMConfig(
            provider='azure_openai',
            model=model,
            providers=LLMProvidersConfig(
                azure_openai=AzureOpenAIProviderConfig(
                    api_key='test-key',
                    api_url='https://example.openai.azure.com',
                )
            ),
        )

    def test_azure_gpt_5_5_uses_reasoning_none(self):
        client = LLMClientFactory.create(self._config('gpt-5.5'))
        assert isinstance(client, AzureOpenAILLMClient)
        assert client.reasoning == 'none'

    def test_azure_non_reasoning_model_sends_no_effort(self):
        client = LLMClientFactory.create(self._config('gpt-4.1'))
        assert isinstance(client, AzureOpenAILLMClient)
        assert client.reasoning is None
