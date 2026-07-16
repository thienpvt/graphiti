"""Allowlisted request models for typed catalog entity tools."""

from __future__ import annotations

import math
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from models.catalog_common import (
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    MAX_ATTRIBUTE_KEYS,
    MAX_GRAPH_KEY_LENGTH,
    MAX_SHORT_STRING_LENGTH,
    MAX_SOURCE_REFS,
    MAX_SUMMARY_LENGTH,
    PROTECTED_ENTITY_PROPERTIES,
    SHA256_HEX_RE,
    bound_nested_strings,
)


def _validate_group_id(group_id: str | None) -> bool:
    """Mirror graphiti_core.helpers.validate_group_id (ASCII alnum/dash/underscore)."""
    if not group_id:
        return True
    if not re.match(r'^[a-zA-Z0-9_-]+$', group_id):
        raise ValueError(f'group_id contains invalid characters: {group_id}')
    return True


def _reject_non_finite(obj: Any, path: str = 'value') -> None:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise ValueError(f'non-finite number at {path}')
    if isinstance(obj, dict):
        for k, v in obj.items():
            _reject_non_finite(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _reject_non_finite(v, f'{path}[{i}]')


def _require_non_empty_str(v: str, field_name: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f'{field_name} must be a non-empty string')
    return v


class CatalogEntityItem(BaseModel):
    """Single typed catalog entity for upsert/resolve."""

    entity_type: str
    graph_key: str = Field(..., max_length=MAX_GRAPH_KEY_LENGTH)
    name_raw: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    name_canonical: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    database_qualified_name: str = Field(..., min_length=1, max_length=MAX_GRAPH_KEY_LENGTH)
    summary: str = Field(..., min_length=1, max_length=MAX_SUMMARY_LENGTH)
    attributes: dict[str, Any] | None = None
    source_refs: list[Any] | None = None
    content_sha256: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator('entity_type')
    @classmethod
    def _entity_type_allowlisted(cls, v: str) -> str:
        if v not in ENTITY_TYPE_PREFIXES:
            raise ValueError(f'entity_type not allowlisted: {v}')
        return v

    @field_validator('name_raw', 'name_canonical', 'database_qualified_name', 'summary')
    @classmethod
    def _non_empty_fields(cls, v: str, info) -> str:
        return _require_non_empty_str(v, info.field_name)

    @field_validator('content_sha256')
    @classmethod
    def _sha256_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(SHA256_HEX_RE, v):
            raise ValueError('content_sha256 must be 64 lowercase hex characters')
        return v

    @field_validator('attributes')
    @classmethod
    def _validate_attributes(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        if len(v) > MAX_ATTRIBUTE_KEYS:
            raise ValueError(f'attributes exceed max keys ({MAX_ATTRIBUTE_KEYS})')
        protected = set(v.keys()) & PROTECTED_ENTITY_PROPERTIES
        if protected:
            raise ValueError(f'attributes contain protected keys: {sorted(protected)}')
        _reject_non_finite(v, 'attributes')
        bound_nested_strings(v, 'attributes')
        return v

    @field_validator('source_refs')
    @classmethod
    def _validate_source_refs(cls, v: list[Any] | None) -> list[Any] | None:
        if v is None:
            return v
        if len(v) > MAX_SOURCE_REFS:
            raise ValueError(f'source_refs exceed max ({MAX_SOURCE_REFS})')
        # JSON-safe nested values only (no NaN/Inf)
        _reject_non_finite(v, 'source_refs')
        bound_nested_strings(v, 'source_refs')
        return v

    @field_validator('confidence')
    @classmethod
    def _finite_confidence(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if math.isnan(v) or math.isinf(v):
            raise ValueError('confidence must be finite')
        return v

    @model_validator(mode='after')
    def _graph_key_prefix(self) -> CatalogEntityItem:
        prefix = ENTITY_TYPE_PREFIXES[self.entity_type]
        if not self.graph_key.startswith(prefix):
            raise ValueError(
                f'graph_key_prefix_mismatch: {self.entity_type} requires prefix {prefix}'
            )
        return self


class ResolveEntityRef(BaseModel):
    """Minimal entity identity for resolve_typed_entities."""

    entity_type: str
    graph_key: str = Field(..., max_length=MAX_GRAPH_KEY_LENGTH)

    @field_validator('entity_type')
    @classmethod
    def _entity_type_allowlisted(cls, v: str) -> str:
        if v not in ENTITY_TYPE_PREFIXES:
            raise ValueError(f'entity_type not allowlisted: {v}')
        return v

    @model_validator(mode='after')
    def _graph_key_prefix(self) -> ResolveEntityRef:
        prefix = ENTITY_TYPE_PREFIXES[self.entity_type]
        if not self.graph_key.startswith(prefix):
            raise ValueError(
                f'graph_key_prefix_mismatch: {self.entity_type} requires prefix {prefix}'
            )
        return self


class UpsertTypedEntitiesRequest(BaseModel):
    """Request for upsert_typed_entities. No excluded_entity_types field."""

    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    entities: list[CatalogEntityItem] = Field(
        ..., min_length=1, max_length=HARD_MAX_ENTITIES_PER_BATCH
    )
    dry_run: bool = False
    atomic: bool = True

    @field_validator('group_id')
    @classmethod
    def _validate_group_id_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('group_id is required and must be non-empty')
        _validate_group_id(v)
        return v


class ResolveTypedEntitiesRequest(BaseModel):
    """Request for resolve_typed_entities (read-only)."""

    group_id: str = Field(..., min_length=1)
    entities: list[ResolveEntityRef] = Field(
        default_factory=list, max_length=HARD_MAX_ENTITIES_PER_BATCH
    )
    graph_keys: list[str] | None = Field(default=None, max_length=HARD_MAX_ENTITIES_PER_BATCH)

    @field_validator('group_id')
    @classmethod
    def _validate_group_id_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('group_id is required and must be non-empty')
        _validate_group_id(v)
        return v


class VerifyEntityRef(BaseModel):
    """Optional explicit entity key for verify_catalog_batch."""

    entity_type: str
    graph_key: str = Field(..., max_length=MAX_GRAPH_KEY_LENGTH)

    @field_validator('entity_type')
    @classmethod
    def _entity_type_allowlisted(cls, v: str) -> str:
        if v not in ENTITY_TYPE_PREFIXES:
            raise ValueError(f'entity_type not allowlisted: {v}')
        return v

    @model_validator(mode='after')
    def _graph_key_prefix(self) -> VerifyEntityRef:
        prefix = ENTITY_TYPE_PREFIXES[self.entity_type]
        if not self.graph_key.startswith(prefix):
            raise ValueError(
                f'graph_key_prefix_mismatch: {self.entity_type} requires prefix {prefix}'
            )
        return self


class VerifyEdgeRef(BaseModel):
    """Optional explicit edge key and expected endpoints for verify_catalog_batch."""

    edge_type: str
    edge_key: str = Field(..., min_length=1, max_length=MAX_GRAPH_KEY_LENGTH)
    expected_source_graph_key: str | None = Field(
        default=None, min_length=1, max_length=MAX_GRAPH_KEY_LENGTH
    )
    expected_target_graph_key: str | None = Field(
        default=None, min_length=1, max_length=MAX_GRAPH_KEY_LENGTH
    )
    expected_source_uuid: str | None = Field(default=None, min_length=1)
    expected_target_uuid: str | None = Field(default=None, min_length=1)

    @field_validator('edge_type')
    @classmethod
    def _edge_type_allowlisted(cls, v: str) -> str:
        from models.catalog_common import CATALOG_EDGE_TYPES

        if v not in CATALOG_EDGE_TYPES:
            raise ValueError(f'edge_type not allowlisted: {v}')
        return v

    @field_validator('expected_source_uuid', 'expected_target_uuid')
    @classmethod
    def _expected_uuid_valid(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                uuid.UUID(v)
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError('expected endpoint UUID must be valid') from exc
        return v


class VerifyCatalogBatchRequest(BaseModel):
    """Request for verify_catalog_batch (read-only)."""

    group_id: str = Field(..., min_length=1)
    batch_id: str | None = Field(default=None, max_length=MAX_SHORT_STRING_LENGTH)
    entities: list[VerifyEntityRef] = Field(
        default_factory=list, max_length=HARD_MAX_ENTITIES_PER_BATCH
    )
    edges: list[VerifyEdgeRef] = Field(default_factory=list, max_length=HARD_MAX_EDGES_PER_BATCH)
    require_provenance: bool = False

    @field_validator('group_id')
    @classmethod
    def _validate_group_id_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('group_id is required and must be non-empty')
        _validate_group_id(v)
        return v

    @model_validator(mode='after')
    def _require_scope(self) -> VerifyCatalogBatchRequest:
        if not self.batch_id and not self.entities and not self.edges:
            raise ValueError('verify requires batch_id and/or explicit entity/edge keys')
        return self
