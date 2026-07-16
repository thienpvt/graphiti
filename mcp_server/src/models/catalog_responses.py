"""Structured response models for catalog MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.catalog_common import CatalogErrorCode

ItemStatus = Literal['created', 'updated', 'unchanged', 'rolled_back', 'error']


class CatalogItemResult(BaseModel):
    """Per-item result preserving input order."""

    index: int
    status: ItemStatus
    uuid: str | None = None
    content_sha256: str | None = None
    graph_key: str | None = None
    edge_key: str | None = None
    entity_type: str | None = None
    edge_type: str | None = None
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None
    details: dict[str, Any] | None = None


class CatalogWriteResponse(BaseModel):
    """Response for upsert_typed_entities / upsert_typed_edges."""

    group_id: str
    batch_id: str
    dry_run: bool = False
    atomic: bool = True
    results: list[CatalogItemResult] = Field(default_factory=list)
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    rolled_back: int = 0


class ResolveEntityResult(BaseModel):
    """Per-entity resolve outcome."""

    index: int
    entity_type: str
    graph_key: str
    status: str
    uuid: str | None = None
    labels: list[str] | None = None
    has_name_embedding: bool | None = None
    content_sha256: str | None = None
    anomalies: list[str] = Field(default_factory=list)
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None


class ResolveTypedEntitiesResponse(BaseModel):
    """Response for resolve_typed_entities."""

    group_id: str
    results: list[ResolveEntityResult | CatalogItemResult] = Field(default_factory=list)


class VerifyCatalogBatchResponse(BaseModel):
    """Response for verify_catalog_batch (read-only)."""

    group_id: str
    batch_id: str
    results: list[CatalogItemResult] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    require_provenance: bool = False
    missing_provenance: list[str] = Field(default_factory=list)
