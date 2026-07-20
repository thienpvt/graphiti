"""Request models for atomic catalog batch and ingest status."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from models.catalog_common import (
    HARD_MAX_EDGES_PER_BATCH,
    HARD_MAX_ENTITIES_PER_BATCH,
    HARD_MAX_PROVENANCE_LINKS_PER_BATCH,
    MAX_SHORT_STRING_LENGTH,
    SHA256_HEX_RE,
    CatalogStrictModel,
    StrictTrue,
    SystemKey,
)
from models.catalog_edges import CatalogEdgeItem
from models.catalog_entities import CatalogEntityItem
from models.catalog_evidence import CatalogEvidenceLink
from models.catalog_graph_key import validate_entity_graph_key_at
from models.catalog_provenance import CatalogSourceItem


def _validate_group_id(group_id: str | None) -> bool:
    """Mirror graphiti_core.helpers.validate_group_id (ASCII alnum/dash/underscore)."""
    if not group_id:
        return True
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', group_id):
        raise ValueError(f'group_id contains invalid characters: {group_id}')
    return True


class NestedProvenancePayload(CatalogStrictModel):
    """Non-Cartesian provenance nested under UpsertCatalogBatchRequest (EVID-06/14).

    Catalog-v2 batch uses explicit evidence_links only. Legacy multi-target
    entity_targets/edge_targets Cartesian fields are rejected without conversion.
    """

    sources: list[CatalogSourceItem] = Field(
        default_factory=list, max_length=HARD_MAX_PROVENANCE_LINKS_PER_BATCH
    )
    evidence_links: list[CatalogEvidenceLink] = Field(
        default_factory=list, max_length=HARD_MAX_PROVENANCE_LINKS_PER_BATCH
    )

    @model_validator(mode='before')
    @classmethod
    def _reject_cartesian_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            legacy = [k for k in ('entity_targets', 'edge_targets') if k in data]
            if legacy:
                raise ValueError(
                    'Cartesian entity_targets/edge_targets rejected for catalog-v2 batch; '
                    'use explicit evidence_links (no auto-conversion)'
                )
        return data

    @model_validator(mode='after')
    def _require_work_and_bounds(self) -> NestedProvenancePayload:
        if not self.sources and not self.evidence_links:
            raise ValueError('provenance requires at least one of sources or evidence_links')
        if len(self.evidence_links) > HARD_MAX_PROVENANCE_LINKS_PER_BATCH:
            raise ValueError(
                f'evidence_links exceed hard max ({HARD_MAX_PROVENANCE_LINKS_PER_BATCH})'
            )
        return self


class UpsertCatalogBatchRequest(CatalogStrictModel):
    """Atomic nested catalog batch (BATC-01/02). atomic must be true."""

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
    dry_run: bool = False
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
        # HASH-01: required lowercase 64-hex including dry-run; None/wrong case/length fail.
        if not isinstance(v, str) or not re.fullmatch(SHA256_HEX_RE, v):
            raise ValueError('catalog_sha256 must be 64 lowercase hex characters')
        return v

    @model_validator(mode='after')
    def _require_non_empty_work_and_system_scope(self) -> UpsertCatalogBatchRequest:
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
