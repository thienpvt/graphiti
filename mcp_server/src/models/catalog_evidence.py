"""Explicit one-source/one-target CatalogEvidenceLink contract (EVID-01..05)."""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from models.catalog_common import (
    CATALOG_EDGE_TYPES,
    ENTITY_TYPE_PREFIXES,
    MAX_EVIDENCE_LENGTH,
    MAX_GRAPH_KEY_LENGTH,
    MAX_SHORT_STRING_LENGTH,
    SHA256_HEX_RE,
    CatalogStrictModel,
)
from models.catalog_graph_key import validate_entity_graph_key_at

EVIDENCE_KINDS: frozenset[str] = frozenset(
    {
        'oracle_dictionary',
        'ddl',
        'view_sql',
        'plsql_source',
        'comment',
        'manual',
    }
)

EvidenceKind = Literal[
    'oracle_dictionary',
    'ddl',
    'view_sql',
    'plsql_source',
    'comment',
    'manual',
]


class CatalogEvidenceLocator(CatalogStrictModel):
    """Flat typed locator for evidence excerpts (no open dict)."""

    object_name: str | None = Field(default=None, max_length=MAX_SHORT_STRING_LENGTH)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    statement_index: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def _end_ge_start(self) -> CatalogEvidenceLocator:
        if self.start_line is not None and self.end_line is not None:
            if self.end_line < self.start_line:
                raise ValueError('end_line must be >= start_line')
        return self


class CatalogEvidenceEntityTarget(CatalogStrictModel):
    """Entity identity target for an evidence link."""

    entity_type: str
    graph_key: str = Field(..., max_length=MAX_GRAPH_KEY_LENGTH)

    @field_validator('entity_type')
    @classmethod
    def _entity_type_allowlisted(cls, v: str) -> str:
        if v not in ENTITY_TYPE_PREFIXES:
            raise ValueError(f'entity_type not allowlisted: {v}')
        return v

    @model_validator(mode='after')
    def _graph_key_grammar(self) -> CatalogEvidenceEntityTarget:
        validate_entity_graph_key_at(
            entity_type=self.entity_type,
            graph_key=self.graph_key,
            title=type(self).__name__,
            loc=('graph_key',),
        )
        return self


class CatalogEvidenceEdgeTarget(CatalogStrictModel):
    """Edge identity target for an evidence link."""

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


class CatalogEvidenceLink(CatalogStrictModel):
    """One explicit source-to-target evidence link (non-Cartesian)."""

    source_key: str = Field(..., min_length=1, max_length=MAX_GRAPH_KEY_LENGTH)
    entity_target: CatalogEvidenceEntityTarget | None = None
    edge_target: CatalogEvidenceEdgeTarget | None = None
    evidence_kind: EvidenceKind
    locator: CatalogEvidenceLocator | None = None
    excerpt: str | None = Field(default=None, max_length=MAX_EVIDENCE_LENGTH)
    extractor_name: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    extractor_version: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    rule_id: str | None = Field(default=None, max_length=MAX_SHORT_STRING_LENGTH)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    content_sha256: str | None = None

    @field_validator('source_key', 'extractor_name', 'extractor_version')
    @classmethod
    def _non_empty_required(cls, v: str, info) -> str:
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

    @field_validator('confidence')
    @classmethod
    def _finite_confidence(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if math.isnan(v) or math.isinf(v):
            raise ValueError('confidence must be finite')
        return v

    @model_validator(mode='after')
    def _exactly_one_target(self) -> CatalogEvidenceLink:
        has_entity = self.entity_target is not None
        has_edge = self.edge_target is not None
        if has_entity == has_edge:
            raise ValueError('exactly one of entity_target or edge_target is required')
        return self
