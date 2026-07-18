"""Allowlisted request models for catalog provenance tools."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from models.catalog_common import (
    CATALOG_EDGE_TYPES,
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
    MAX_ATTRIBUTE_KEYS,
    MAX_GRAPH_KEY_LENGTH,
    MAX_SHORT_STRING_LENGTH,
    PROTECTED_ENTITY_PROPERTIES,
    SHA256_HEX_RE,
    CatalogStrictModel,
    StrictTrue,
    SystemKey,
    validate_nested_json,
)
from models.catalog_graph_key import validate_entity_graph_key_at


def _validate_group_id(group_id: str | None) -> bool:
    """Mirror graphiti_core.helpers.validate_group_id (ASCII alnum/dash/underscore)."""
    if not group_id:
        return True
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', group_id):
        raise ValueError(f'group_id contains invalid characters: {group_id}')
    return True


class CatalogSourceItem(CatalogStrictModel):
    """Single provenance source (maps to Episodic later). PROV-02."""

    source_key: str = Field(..., min_length=1, max_length=MAX_GRAPH_KEY_LENGTH)
    reference_time: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    attributes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    content_sha256: str | None = None

    @field_validator('source_key')
    @classmethod
    def _non_empty_source_key(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError('source_key must be a non-empty string')
        return v

    @field_validator('reference_time')
    @classmethod
    def _validate_reference_time(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise PydanticCustomError(
                'value_error',
                'reference_time must be a non-empty ISO-8601 timestamp',
            )
        # Temporary normalize for parse only; return original bytes unchanged.
        normalized = v.strip()
        if normalized.endswith('Z') or normalized.endswith('z'):
            normalized = normalized[:-1] + '+00:00'
        try:
            datetime.fromisoformat(normalized)
        except ValueError:
            raise PydanticCustomError(
                'value_error',
                'reference_time must be a valid ISO-8601 timestamp',
            ) from None
        return v

    @field_validator('content_sha256')
    @classmethod
    def _sha256_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(SHA256_HEX_RE, v):
            raise ValueError('content_sha256 must be 64 lowercase hex characters')
        return v

    @field_validator('attributes', 'metadata')
    @classmethod
    def _validate_bounded_map(cls, v: dict[str, Any] | None, info) -> dict[str, Any] | None:
        if v is None:
            return v
        if len(v) > MAX_ATTRIBUTE_KEYS:
            raise ValueError(f'{info.field_name} exceed max keys ({MAX_ATTRIBUTE_KEYS})')
        protected = set(v.keys()) & PROTECTED_ENTITY_PROPERTIES
        if protected:
            raise ValueError(f'{info.field_name} contain protected keys: {sorted(protected)}')
        validate_nested_json(v, info.field_name)
        return v


class CatalogProvenanceEntityTarget(CatalogStrictModel):
    """Entity identity target for provenance MENTIONS links."""

    entity_type: str
    graph_key: str = Field(..., max_length=MAX_GRAPH_KEY_LENGTH)

    @field_validator('entity_type')
    @classmethod
    def _entity_type_allowlisted(cls, v: str) -> str:
        if v not in ENTITY_TYPE_PREFIXES:
            raise ValueError(f'entity_type not allowlisted: {v}')
        return v

    @model_validator(mode='after')
    def _graph_key_grammar(self) -> CatalogProvenanceEntityTarget:
        validate_entity_graph_key_at(
            entity_type=self.entity_type,
            graph_key=self.graph_key,
            title=type(self).__name__,
            loc=('graph_key',),
        )
        return self


class CatalogProvenanceEdgeTarget(CatalogStrictModel):
    """Edge identity target for provenance episode attachment."""

    edge_type: str
    edge_key: str = Field(..., min_length=1, max_length=MAX_GRAPH_KEY_LENGTH)

    @field_validator('edge_type')
    @classmethod
    def _edge_type_allowlisted(cls, v: str) -> str:
        if v not in CATALOG_EDGE_TYPES:
            raise ValueError(f'edge_type not allowlisted: {v}')
        return v

    @field_validator('edge_key')
    @classmethod
    def _non_empty_edge_key(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError('edge_key must be a non-empty string')
        return v


class UpsertProvenanceRequest(CatalogStrictModel):
    """Request for upsert_provenance (no LLM/queue)."""

    identity_schema_version: Literal['catalog-v2']
    system_key: SystemKey
    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    sources: list[CatalogSourceItem] = Field(
        ..., min_length=1, max_length=HARD_MAX_PROVENANCE_LINKS_PER_BATCH
    )
    entity_targets: list[CatalogProvenanceEntityTarget] = Field(
        default_factory=list, max_length=HARD_MAX_PROVENANCE_LINKS_PER_BATCH
    )
    edge_targets: list[CatalogProvenanceEdgeTarget] = Field(
        default_factory=list, max_length=HARD_MAX_PROVENANCE_LINKS_PER_BATCH
    )
    dry_run: bool = False
    atomic: StrictTrue = True

    @field_validator('group_id')
    @classmethod
    def _validate_group_id_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('group_id is required and must be non-empty')
        _validate_group_id(v)
        return v

    @model_validator(mode='after')
    def _link_collection_bounds_and_system(self) -> UpsertProvenanceRequest:
        total_links = len(self.sources) * (len(self.entity_targets) + len(self.edge_targets))
        if total_links > HARD_MAX_PROVENANCE_LINKS_PER_BATCH:
            raise ValueError(
                f'provenance links exceed hard max ({HARD_MAX_PROVENANCE_LINKS_PER_BATCH})'
            )
        for index, target in enumerate(self.entity_targets):
            validate_entity_graph_key_at(
                entity_type=target.entity_type,
                graph_key=target.graph_key,
                system_key=self.system_key,
                title=type(self).__name__,
                loc=('entity_targets', index, 'graph_key'),
            )
        return self
