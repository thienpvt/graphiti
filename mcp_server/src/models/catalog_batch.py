"""Request models for atomic catalog batch and ingest status."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from models.catalog_common import (
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
    MAX_SHORT_STRING_LENGTH,
    SHA256_HEX_RE,
    CatalogStrictModel,
)
from models.catalog_edges import CatalogEdgeItem
from models.catalog_entities import CatalogEntityItem
from models.catalog_provenance import (
    CatalogProvenanceEdgeTarget,
    CatalogProvenanceEntityTarget,
    CatalogSourceItem,
)


def _validate_group_id(group_id: str | None) -> bool:
    """Mirror graphiti_core.helpers.validate_group_id (ASCII alnum/dash/underscore)."""
    if not group_id:
        return True
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', group_id):
        raise ValueError(f'group_id contains invalid characters: {group_id}')
    return True


class NestedProvenancePayload(CatalogStrictModel):
    """Provenance nested under UpsertCatalogBatchRequest."""

    sources: list[CatalogSourceItem] = Field(
        ..., min_length=1, max_length=HARD_MAX_PROVENANCE_LINKS_PER_BATCH
    )
    entity_targets: list[CatalogProvenanceEntityTarget] = Field(default_factory=list)
    edge_targets: list[CatalogProvenanceEdgeTarget] = Field(default_factory=list)

    @model_validator(mode='after')
    def _link_collection_bounds(self) -> NestedProvenancePayload:
        total_links = len(self.sources) * (len(self.entity_targets) + len(self.edge_targets))
        if total_links > HARD_MAX_PROVENANCE_LINKS_PER_BATCH:
            raise ValueError(
                f'provenance links exceed hard max ({HARD_MAX_PROVENANCE_LINKS_PER_BATCH})'
            )
        return self


class UpsertCatalogBatchRequest(CatalogStrictModel):
    """Atomic nested catalog batch (BATC-01/02). atomic must be true."""

    identity_schema_version: Literal['catalog-v2']
    system_key: Literal['FE', 'BO', 'COMMON']
    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    entities: list[CatalogEntityItem] = Field(
        default_factory=list, max_length=HARD_MAX_ENTITIES_PER_BATCH
    )
    edges: list[CatalogEdgeItem] = Field(default_factory=list, max_length=HARD_MAX_EDGES_PER_BATCH)
    provenance: NestedProvenancePayload | None = None
    request_sha256: str | None = None
    catalog_sha256: str | None = None
    dry_run: bool = False
    atomic: Literal[True] = True

    @field_validator('group_id')
    @classmethod
    def _validate_group_id_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('group_id is required and must be non-empty')
        _validate_group_id(v)
        return v

    @field_validator('request_sha256', 'catalog_sha256')
    @classmethod
    def _sha256_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(SHA256_HEX_RE, v):
            raise ValueError('hash must be 64 lowercase hex characters')
        return v

    @field_validator('atomic')
    @classmethod
    def _atomic_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError('atomic must be true for upsert_catalog_batch')
        return v

    @model_validator(mode='after')
    def _require_non_empty_work(self) -> UpsertCatalogBatchRequest:
        has_entities = bool(self.entities)
        has_edges = bool(self.edges)
        has_prov = self.provenance is not None and bool(self.provenance.sources)
        if not (has_entities or has_edges or has_prov):
            raise ValueError(
                'batch requires at least one of entities, edges, or provenance sources'
            )
        return self


class GetCatalogIngestStatusRequest(CatalogStrictModel):
    """Request for get_catalog_ingest_status — group_id + batch_id only."""

    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)

    @field_validator('group_id')
    @classmethod
    def _validate_group_id_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('group_id is required and must be non-empty')
        _validate_group_id(v)
        return v
