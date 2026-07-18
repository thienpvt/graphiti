"""Strict prepare/commit/discard request models for immutable prepared plans."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from models.catalog_batch import NestedProvenancePayload, _validate_group_id
from models.catalog_common import (
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    MAX_SHORT_STRING_LENGTH,
    SHA256_HEX_RE,
    CatalogStrictModel,
    StrictTrue,
    SystemKey,
)
from models.catalog_edges import CatalogEdgeItem
from models.catalog_entities import CatalogEntityItem
from models.catalog_graph_key import validate_entity_graph_key_at

# Opaque plan_token upper bound (secrets.token_urlsafe(32) ≈ 43 chars; headroom for formats)
MAX_PLAN_TOKEN_LENGTH = 128


class PrepareCatalogBatchRequest(CatalogStrictModel):
    """Full catalog-v2 batch domain body for prepare — no dry_run, no plan_token authority.

    Mirrors UpsertCatalogBatchRequest domain fields minus dry_run (D-14, PLAN-01).
    """

    identity_schema_version: Literal['catalog-v2']
    system_key: SystemKey
    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    entities: list[CatalogEntityItem] = Field(
        default_factory=list, max_length=HARD_MAX_ENTITIES_PER_BATCH
    )
    edges: list[CatalogEdgeItem] = Field(default_factory=list, max_length=HARD_MAX_EDGES_PER_BATCH)
    provenance: NestedProvenancePayload | None = None
    request_sha256: str | None = None
    catalog_sha256: str = Field(..., min_length=64, max_length=64)
    atomic: StrictTrue = True

    @field_validator('group_id')
    @classmethod
    def _validate_group_id_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('group_id is required and must be non-empty')
        _validate_group_id(v)
        return v

    @field_validator('request_sha256')
    @classmethod
    def _request_sha256_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(SHA256_HEX_RE, v):
            raise ValueError('hash must be 64 lowercase hex characters')
        return v

    @field_validator('catalog_sha256')
    @classmethod
    def _catalog_sha256_format(cls, v: str) -> str:
        if not isinstance(v, str) or not re.fullmatch(SHA256_HEX_RE, v):
            raise ValueError('catalog_sha256 must be 64 lowercase hex characters')
        return v

    @model_validator(mode='after')
    def _require_non_empty_work_and_system_scope(self) -> PrepareCatalogBatchRequest:
        has_entities = bool(self.entities)
        has_edges = bool(self.edges)
        has_sources = self.provenance is not None and bool(self.provenance.sources)
        has_links = self.provenance is not None and bool(self.provenance.evidence_links)
        if not (has_entities or has_edges or has_sources or has_links):
            raise ValueError(
                'batch requires at least one of entities, edges, provenance sources, '
                'or evidence_links'
            )
        for index, item in enumerate(self.entities):
            validate_entity_graph_key_at(
                entity_type=item.entity_type,
                graph_key=item.graph_key,
                system_key=self.system_key,
                title=type(self).__name__,
                loc=('entities', index, 'graph_key'),
            )
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
        if self.provenance is not None:
            for index, link in enumerate(self.provenance.evidence_links):
                if link.entity_target is not None:
                    validate_entity_graph_key_at(
                        entity_type=link.entity_target.entity_type,
                        graph_key=link.entity_target.graph_key,
                        system_key=self.system_key,
                        title=type(self).__name__,
                        loc=(
                            'provenance',
                            'evidence_links',
                            index,
                            'entity_target',
                            'graph_key',
                        ),
                    )
        return self


class CommitPreparedCatalogBatchRequest(CatalogStrictModel):
    """Token-only commit (+ optional expected_request_sha256 compare guard).

    Forbidden: group/batch/entities/edges/sources/evidence/catalog_sha256/replacement
    payload/flags (D-20, PLAN-10). expected_request_sha256 is compare-only, never identity.
    """

    plan_token: str = Field(..., min_length=1, max_length=MAX_PLAN_TOKEN_LENGTH)
    expected_request_sha256: str | None = None

    @field_validator('expected_request_sha256')
    @classmethod
    def _expected_request_sha256_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(SHA256_HEX_RE, v):
            raise ValueError('expected_request_sha256 must be 64 lowercase hex characters')
        return v


class DiscardPreparedCatalogBatchRequest(CatalogStrictModel):
    """Token-only discard request (D-11, PLAN-19 model surface)."""

    plan_token: str = Field(..., min_length=1, max_length=MAX_PLAN_TOKEN_LENGTH)
