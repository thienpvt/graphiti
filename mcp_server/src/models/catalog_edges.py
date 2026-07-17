"""Allowlisted request models for typed catalog edge tools."""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from models.catalog_common import (
    CATALOG_EDGE_TYPES,
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_EDGES_PER_BATCH,
    MAX_ATTRIBUTE_KEYS,
    MAX_EVIDENCE_LENGTH,
    MAX_FACT_LENGTH,
    MAX_GRAPH_KEY_LENGTH,
    MAX_SHORT_STRING_LENGTH,
    PROTECTED_ENTITY_PROPERTIES,
    SHA256_HEX_RE,
    CatalogStrictModel,
    StrictTrue,
    SystemKey,
    validate_nested_json,
)
from models.catalog_graph_key import _match_entity_graph_key, validate_entity_graph_key_at


def _validate_group_id(group_id: str | None) -> bool:
    """Mirror graphiti_core.helpers.validate_group_id (ASCII alnum/dash/underscore)."""
    if not group_id:
        return True
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', group_id):
        raise ValueError(f'group_id contains invalid characters: {group_id}')
    return True


class CatalogEdgeItem(CatalogStrictModel):
    """Single typed catalog edge for upsert."""

    edge_type: str
    edge_key: str = Field(..., min_length=1, max_length=MAX_GRAPH_KEY_LENGTH)
    source_graph_key: str = Field(..., min_length=1, max_length=MAX_GRAPH_KEY_LENGTH)
    source_entity_type: str
    target_graph_key: str = Field(..., min_length=1, max_length=MAX_GRAPH_KEY_LENGTH)
    target_entity_type: str
    fact: str = Field(..., min_length=1, max_length=MAX_FACT_LENGTH)
    evidence: str | None = Field(default=None, max_length=MAX_EVIDENCE_LENGTH)
    attributes: dict[str, Any] | None = None
    content_sha256: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator('edge_type')
    @classmethod
    def _edge_type_allowlisted(cls, v: str) -> str:
        if v not in CATALOG_EDGE_TYPES:
            raise ValueError(f'edge_type not allowlisted: {v}')
        return v

    @field_validator('source_entity_type', 'target_entity_type')
    @classmethod
    def _endpoint_type_allowlisted(cls, v: str) -> str:
        if v not in ENTITY_TYPE_PREFIXES:
            raise ValueError(f'entity_type not allowlisted: {v}')
        return v

    @field_validator('edge_key', 'source_graph_key', 'target_graph_key', 'fact')
    @classmethod
    def _non_empty(cls, v: str, info) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f'{info.field_name} must be a non-empty string')
        return v

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
        validate_nested_json(v, 'attributes')
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
    def _enforced_by_requires_evidence(self) -> CatalogEdgeItem:
        if self.edge_type == 'EnforcedBy' and (not self.evidence or not self.evidence.strip()):
            raise ValueError('EnforcedBy requires non-empty evidence')
        for entity_type, graph_key in (
            (self.source_entity_type, self.source_graph_key),
            (self.target_entity_type, self.target_graph_key),
        ):
            _match_entity_graph_key(entity_type, graph_key)
        return self


class UpsertTypedEdgesRequest(CatalogStrictModel):
    """Request for upsert_typed_edges. No excluded_entity_types field."""

    identity_schema_version: Literal['catalog-v2']
    system_key: SystemKey
    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    edges: list[CatalogEdgeItem] = Field(..., min_length=1, max_length=HARD_MAX_EDGES_PER_BATCH)
    dry_run: bool = False
    atomic: StrictTrue = True
    strict_endpoints: StrictTrue = True

    @field_validator('group_id')
    @classmethod
    def _validate_group_id_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('group_id is required and must be non-empty')
        _validate_group_id(v)
        return v

    @model_validator(mode='after')
    def _nested_endpoint_keys_match_shell_system(self) -> UpsertTypedEdgesRequest:
        for index, edge in enumerate(self.edges):
            validate_entity_graph_key_at(
                entity_type=edge.source_entity_type,
                graph_key=edge.source_graph_key,
                system_key=self.system_key,
                title=type(self).__name__,
                loc=('edges', index, 'source_graph_key'),
            )
            validate_entity_graph_key_at(
                entity_type=edge.target_entity_type,
                graph_key=edge.target_graph_key,
                system_key=self.system_key,
                title=type(self).__name__,
                loc=('edges', index, 'target_graph_key'),
            )
        return self
