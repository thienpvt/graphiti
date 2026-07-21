"""Configuration schemas with pydantic-settings and YAML support."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from models.catalog_common import (
    DEFAULT_MAX_ACTIVE_PLANS_PER_GROUP,
    DEFAULT_PLAN_TTL_SECONDS,
    DEFAULT_PREPARED_CHUNK_BYTES,
    DEFAULT_PREPARED_PAYLOAD_BYTES,
    HARD_MAX_ACTIVE_PLANS_PER_GROUP,
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    HARD_MAX_PREPARED_PAYLOAD_BYTES,
    HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
    HARD_PLAN_TTL_SECONDS,
    HARD_PREPARED_CHUNK_BYTES,
)


class YamlSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source for loading from YAML files."""

    def __init__(self, settings_cls: type[BaseSettings], config_path: Path | None = None):
        super().__init__(settings_cls)
        self.config_path = config_path or Path('config.yaml')

    def _expand_env_vars(self, value: Any) -> Any:
        """Recursively expand environment variables in configuration values."""
        if isinstance(value, str):
            # Support ${VAR} and ${VAR:default} syntax
            import re

            def replacer(match):
                var_name = match.group(1)
                default_value = match.group(3) if match.group(3) is not None else ''
                return os.environ.get(var_name, default_value)

            pattern = r'\$\{([^:}]+)(:([^}]*))?\}'

            # Check if the entire value is a single env var expression
            full_match = re.fullmatch(pattern, value)
            if full_match:
                result = replacer(full_match)
                # Convert boolean-like strings to actual booleans
                if isinstance(result, str):
                    lower_result = result.lower().strip()
                    if lower_result in ('true', '1', 'yes', 'on'):
                        return True
                    elif lower_result in ('false', '0', 'no', 'off'):
                        return False
                    elif lower_result == '':
                        # Empty string means env var not set - return None for optional fields
                        return None
                return result
            else:
                # Otherwise, do string substitution (keep as strings for partial replacements)
                return re.sub(pattern, replacer, value)
        elif isinstance(value, dict):
            return {k: self._expand_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._expand_env_vars(item) for item in value]
        return value

    def get_field_value(self, field_name: str, field_info: Any) -> Any:
        """Get field value from YAML config."""
        return None

    def __call__(self) -> dict[str, Any]:
        """Load and parse YAML configuration."""
        if not self.config_path.exists():
            return {}

        with open(self.config_path) as f:
            raw_config = yaml.safe_load(f) or {}

        # Expand environment variables
        return self._expand_env_vars(raw_config)


class ServerConfig(BaseModel):
    """Server configuration."""

    transport: str = Field(
        default='http',
        description='Transport type: http (default, recommended), stdio, or sse (deprecated)',
    )
    host: str = Field(default='0.0.0.0', description='Server host')
    port: int = Field(default=8000, description='Server port')


class OpenAIProviderConfig(BaseModel):
    """OpenAI provider configuration."""

    api_key: str | None = None
    api_url: str = 'https://api.openai.com/v1'
    organization_id: str | None = None


class AzureOpenAIProviderConfig(BaseModel):
    """Azure OpenAI provider configuration."""

    api_key: str | None = None
    api_url: str | None = None
    api_version: str = '2024-10-21'
    deployment_name: str | None = None
    use_azure_ad: bool = False


class AnthropicProviderConfig(BaseModel):
    """Anthropic provider configuration."""

    api_key: str | None = None
    api_url: str = 'https://api.anthropic.com'
    max_retries: int = 3


class GeminiProviderConfig(BaseModel):
    """Gemini provider configuration."""

    api_key: str | None = None
    project_id: str | None = None
    location: str = 'us-central1'


class GroqProviderConfig(BaseModel):
    """Groq provider configuration."""

    api_key: str | None = None
    api_url: str = 'https://api.groq.com/openai/v1'


class VoyageProviderConfig(BaseModel):
    """Voyage AI provider configuration."""

    api_key: str | None = None
    api_url: str = 'https://api.voyageai.com/v1'
    model: str = 'voyage-3'


class OllamaProviderConfig(BaseModel):
    """Ollama native embedding provider configuration."""

    api_url: str = 'http://localhost:11434'
    api_key: str | None = None
    truncate: bool = True
    keep_alive: str | None = None
    timeout: float = Field(default=60.0, gt=0)


class LLMProvidersConfig(BaseModel):
    """LLM providers configuration."""

    openai: OpenAIProviderConfig | None = None
    azure_openai: AzureOpenAIProviderConfig | None = None
    anthropic: AnthropicProviderConfig | None = None
    gemini: GeminiProviderConfig | None = None
    groq: GroqProviderConfig | None = None


class LLMConfig(BaseModel):
    """LLM configuration."""

    provider: str = Field(default='openai', description='LLM provider')
    model: str = Field(default='gpt-5.5', description='Model name')
    temperature: float | None = Field(
        default=None, description='Temperature (optional, defaults to None for reasoning models)'
    )
    max_tokens: int = Field(default=4096, description='Max tokens')
    providers: LLMProvidersConfig = Field(default_factory=LLMProvidersConfig)


class EmbedderProvidersConfig(BaseModel):
    """Embedder providers configuration."""

    openai: OpenAIProviderConfig | None = None
    azure_openai: AzureOpenAIProviderConfig | None = None
    gemini: GeminiProviderConfig | None = None
    voyage: VoyageProviderConfig | None = None
    ollama: OllamaProviderConfig | None = None


class EmbedderConfig(BaseModel):
    """Embedder configuration."""

    provider: str = Field(default='openai', description='Embedder provider')
    model: str = Field(default='text-embedding-3-small', description='Model name')
    dimensions: int = Field(default=1536, gt=0, description='Embedding dimensions')
    providers: EmbedderProvidersConfig = Field(default_factory=EmbedderProvidersConfig)


class Neo4jProviderConfig(BaseModel):
    """Neo4j provider configuration."""

    uri: str = 'bolt://localhost:7687'
    username: str = 'neo4j'
    password: str | None = None
    database: str = 'neo4j'
    use_parallel_runtime: bool = False


class FalkorDBProviderConfig(BaseModel):
    """FalkorDB provider configuration."""

    uri: str = 'redis://localhost:6379'
    password: str | None = None
    database: str = 'default_db'


class DatabaseProvidersConfig(BaseModel):
    """Database providers configuration."""

    neo4j: Neo4jProviderConfig | None = None
    falkordb: FalkorDBProviderConfig | None = None


class DatabaseConfig(BaseModel):
    """Database configuration."""

    provider: str = Field(default='falkordb', description='Database provider')
    providers: DatabaseProvidersConfig = Field(default_factory=DatabaseProvidersConfig)


class EntityTypeConfig(BaseModel):
    """Entity type configuration.

    If ``name`` matches a model registered in ``models.entity_types.ENTITY_TYPES``,
    the rich Pydantic model (with its attributes and extraction instructions) is
    registered with graphiti-core. Otherwise a documentation-only model is built
    from ``name`` + ``description`` for backward compatibility.
    """

    name: str
    description: str


class EdgeTypeConfig(BaseModel):
    """Edge (fact) type configuration.

    Mirrors :class:`EntityTypeConfig`. If ``name`` matches a model registered in
    ``models.edge_types.EDGE_TYPES``, the rich Pydantic model is registered with
    graphiti-core. Otherwise a documentation-only model is built from
    ``name`` + ``description``.
    """

    name: str
    description: str


class EdgeTypeMapEntry(BaseModel):
    """Maps an ordered (source entity type, target entity type) pair to the edge
    type names permitted between them.

    Use ``'Entity'`` as a wildcard for either endpoint, matching graphiti-core's
    ``edge_type_map`` convention.
    """

    source: str = Field(default='Entity', description='Source entity type name')
    target: str = Field(default='Entity', description='Target entity type name')
    edge_types: list[str] = Field(
        default_factory=list, description='Edge type names allowed for this pair'
    )


class GraphitiAppConfig(BaseModel):
    """Graphiti-specific configuration."""

    group_id: str = Field(default='main', description='Group ID')
    episode_id_prefix: str | None = Field(default='', description='Episode ID prefix')
    user_id: str = Field(default='mcp_user', description='User ID')
    entity_types: list[EntityTypeConfig] = Field(default_factory=list)
    edge_types: list[EdgeTypeConfig] = Field(default_factory=list)
    edge_type_map: list[EdgeTypeMapEntry] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        """Convert None to empty string for episode_id_prefix."""
        if self.episode_id_prefix is None:
            self.episode_id_prefix = ''


class CatalogConfig(BaseModel):
    """Deterministic catalog upsert configuration.

    Catalog write tools operate against Neo4j only. Other graph backends keep
    stable tool schemas but return structured backend-unavailable errors.
    GRAPHITI_CATALOG_UUID_NAMESPACE is immutable deployment configuration and
    is never auto-generated.
    """

    enabled: bool = Field(default=False, description='Enable catalog write tools')
    uuid_namespace: str | None = Field(
        default=None,
        description=(
            'Fixed UUIDv5 namespace for deterministic catalog identities. '
            'Mapped from GRAPHITI_CATALOG_UUID_NAMESPACE. Never auto-generated.'
        ),
    )
    max_entities_per_batch: int = Field(default=500, ge=1, le=HARD_MAX_ENTITIES_PER_BATCH)
    max_edges_per_batch: int = Field(default=2000, ge=1, le=HARD_MAX_EDGES_PER_BATCH)
    max_provenance_links_per_batch: int = Field(
        default=5000, ge=1, le=HARD_MAX_PROVENANCE_LINKS_PER_BATCH
    )
    plan_ttl_seconds: int = Field(default=DEFAULT_PLAN_TTL_SECONDS, ge=1, le=HARD_PLAN_TTL_SECONDS)
    max_prepared_payload_bytes: int = Field(
        default=DEFAULT_PREPARED_PAYLOAD_BYTES, ge=1, le=HARD_MAX_PREPARED_PAYLOAD_BYTES
    )
    max_active_plans_per_group: int = Field(
        default=DEFAULT_MAX_ACTIVE_PLANS_PER_GROUP, ge=1, le=HARD_MAX_ACTIVE_PLANS_PER_GROUP
    )
    prepared_chunk_bytes: int = Field(
        default=DEFAULT_PREPARED_CHUNK_BYTES, ge=1, le=HARD_PREPARED_CHUNK_BYTES
    )
    # Phase 4: split read/write gates. Writes stay off by default; reads default on.
    # Do not couple reads_enabled validation to write `enabled` (GATE-01, D-17).
    reads_enabled: bool = Field(default=True, description='Enable catalog read/diagnostic tools')
    max_page_size: int = Field(
        default=100,
        ge=1,
        le=500,
        description='Configured page size ceiling for diagnostic list tools (hard max 500)',
    )

    @model_validator(mode='before')
    @classmethod
    def _bind_namespace_env(cls, data: Any) -> Any:
        """Map GRAPHITI_CATALOG_UUID_NAMESPACE when uuid_namespace is unset."""
        if not isinstance(data, dict):
            return data
        if 'uuid_namespace' not in data:
            env_ns = os.environ.get('GRAPHITI_CATALOG_UUID_NAMESPACE')
            if env_ns:
                data = {**data, 'uuid_namespace': env_ns}
        return data

    @model_validator(mode='after')
    def _require_valid_namespace_when_enabled(self) -> CatalogConfig:
        if not self.enabled:
            return self
        if not self.uuid_namespace:
            raise ValueError('uuid_namespace is required when catalog_upsert.enabled is true')
        try:
            uuid.UUID(self.uuid_namespace)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(
                f'uuid_namespace must be a valid UUID when enabled: {self.uuid_namespace}'
            ) from exc
        return self


class GraphitiConfig(BaseSettings):
    """Graphiti configuration with YAML and environment support."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    graphiti: GraphitiAppConfig = Field(default_factory=GraphitiAppConfig)
    catalog_upsert: CatalogConfig = Field(default_factory=CatalogConfig)

    # Additional server options
    destroy_graph: bool = Field(default=False, description='Clear graph on startup')

    model_config = SettingsConfigDict(
        env_prefix='',
        env_nested_delimiter='__',
        case_sensitive=False,
        extra='ignore',
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources to include YAML."""
        config_path = Path(os.environ.get('CONFIG_PATH', 'config/config.yaml'))
        yaml_settings = YamlSettingsSource(settings_cls, config_path)
        # Priority: CLI args (init) > env vars > yaml > defaults
        return (init_settings, env_settings, yaml_settings, dotenv_settings)

    def apply_cli_overrides(self, args) -> None:
        """Apply CLI argument overrides to configuration."""
        previous_embedder_provider = self.embedder.provider

        # Override server settings
        if hasattr(args, 'transport') and args.transport:
            self.server.transport = args.transport
        if hasattr(args, 'host') and args.host:
            self.server.host = args.host
        if hasattr(args, 'port') and args.port is not None:
            self.server.port = args.port

        # Override LLM settings
        if hasattr(args, 'llm_provider') and args.llm_provider:
            self.llm.provider = args.llm_provider
        if hasattr(args, 'model') and args.model:
            self.llm.model = args.model
        if hasattr(args, 'temperature') and args.temperature is not None:
            self.llm.temperature = args.temperature

        # Override embedder settings
        if hasattr(args, 'embedder_provider') and args.embedder_provider:
            self.embedder.provider = args.embedder_provider
        if hasattr(args, 'embedder_model') and args.embedder_model:
            self.embedder.model = args.embedder_model
        elif self.embedder.provider == 'ollama' and previous_embedder_provider != 'ollama':
            self.embedder.model = 'embeddinggemma'
        if hasattr(args, 'embedder_dimensions') and args.embedder_dimensions is not None:
            if args.embedder_dimensions <= 0:
                raise ValueError('embedder dimensions must be a positive integer')
            self.embedder.dimensions = args.embedder_dimensions
        elif self.embedder.provider == 'ollama' and previous_embedder_provider != 'ollama':
            self.embedder.dimensions = 768

        # Override database settings
        if hasattr(args, 'database_provider') and args.database_provider:
            self.database.provider = args.database_provider

        # Override Graphiti settings
        if hasattr(args, 'group_id') and args.group_id:
            self.graphiti.group_id = args.group_id
        if hasattr(args, 'user_id') and args.user_id:
            self.graphiti.user_id = args.user_id
