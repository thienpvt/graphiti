"""Structured response models for catalog MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.catalog_common import CatalogErrorCode

ItemStatus = Literal['created', 'updated', 'unchanged', 'rolled_back', 'error']


class CatalogStructuredError(BaseModel):
    """SAFE-08 structured validation error DTO (non-strict response surface)."""

    code: CatalogErrorCode
    message: str = Field(..., max_length=512)
    field_path: str | None = None
    retryable: bool = False
    correlation_id: str


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
    """Per-entity resolve outcome (RESO-02)."""

    index: int
    entity_type: str
    graph_key: str
    status: str = 'missing'
    found: bool = False
    uuid: str | None = None
    labels: list[str] | None = None
    verified_type: str | None = None
    has_name_embedding: bool | None = None
    content_sha256: str | None = None
    generic_duplicates: list[str] = Field(default_factory=list)
    typed_duplicates: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None


class ResolveTypedEntitiesResponse(BaseModel):
    """Response for resolve_typed_entities."""

    group_id: str
    results: list[ResolveEntityResult] = Field(default_factory=list)


class VerifyEntitySection(BaseModel):
    """Entity verification counts and anomaly lists (VERI-02)."""

    expected: int = 0
    found: int = 0
    missing: list[str] = Field(default_factory=list)
    wrong_type: list[str] = Field(default_factory=list)
    generic_duplicate: list[str] = Field(default_factory=list)
    typed_duplicate: list[str] = Field(default_factory=list)
    uuid_mismatch: list[str] = Field(default_factory=list)
    missing_embedding: list[str] = Field(default_factory=list)


class VerifyEdgeSection(BaseModel):
    """Edge verification counts and anomaly lists (VERI-03)."""

    expected: int = 0
    found: int = 0
    missing: list[str] = Field(default_factory=list)
    duplicate_edge_key: list[str] = Field(default_factory=list)
    edge_type_mismatch: list[str] = Field(default_factory=list)
    endpoint_mismatch: list[str] = Field(default_factory=list)
    uuid_mismatch: list[str] = Field(default_factory=list)
    missing_embedding: list[str] = Field(default_factory=list)


class VerifyCatalogBatchResponse(BaseModel):
    """Response for verify_catalog_batch (read-only)."""

    group_id: str
    batch_id: str | None = None
    results: list[CatalogItemResult] = Field(default_factory=list)
    entities: VerifyEntitySection = Field(default_factory=VerifyEntitySection)
    edges: VerifyEdgeSection = Field(default_factory=VerifyEdgeSection)
    missing: list[str] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    require_provenance: bool = False
    missing_provenance: list[str] = Field(default_factory=list)
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None


CatalogIngestStatus = Literal[
    'planned',
    'validating',
    'embedding',
    'writing',
    'committed',
    'failed',
]


class CatalogIngestStatusResponse(BaseModel):
    """Ingest status for a batch — no full payloads or secrets (STAT-02/03)."""

    group_id: str
    batch_id: str
    batch_uuid: str
    status: CatalogIngestStatus
    request_sha256: str | None = None
    catalog_sha256: str | None = None
    entity_count: int = 0
    edge_count: int = 0
    provenance_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    committed_at: str | None = None
    error_summary: str = Field(default='', max_length=512)
    error_code: CatalogErrorCode | None = None


class CatalogBatchWriteResponse(BaseModel):
    """Response for upsert_catalog_batch (counts + item results)."""

    group_id: str
    batch_id: str
    batch_uuid: str | None = None
    dry_run: bool = False
    atomic: bool = True
    status: CatalogIngestStatus | None = None
    # HASH-05 authoritative identity/hash echo (derivable after parse)
    identity_schema_version: str | None = None
    canonicalization_version: str | None = None
    request_sha256: str | None = None
    catalog_sha256: str | None = None
    results: list[CatalogItemResult] = Field(default_factory=list)
    entity_created: int = 0
    entity_updated: int = 0
    entity_unchanged: int = 0
    edge_created: int = 0
    edge_updated: int = 0
    edge_unchanged: int = 0
    provenance_created: int = 0
    provenance_updated: int = 0
    provenance_unchanged: int = 0
    failed: int = 0
    rolled_back: int = 0
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None


class CatalogCapabilitiesResponse(BaseModel):
    """Read-only catalog-v2 capabilities discovery (CAPA-01..08). No secrets."""

    package_version: str
    backend: str | None = None
    connectivity: Literal['ok', 'error', 'unknown'] = 'unknown'
    catalog_writes_enabled: bool = False
    catalog_reads_enabled: bool = True
    uuid_namespace_configured: bool = False
    namespace_fingerprint: str | None = None
    identity_schema_version: str
    canonicalization_version: str
    catalog_schema_version: str
    entity_types: list[str] = Field(default_factory=list)
    entity_prefixes: dict[str, str] = Field(default_factory=dict)
    edge_types: list[str] = Field(default_factory=list)
    endpoint_map: dict[str, list[list[str]]] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)
    embeddings: dict[str, Any] = Field(default_factory=dict)
    neo4j_indexes: Literal['ready', 'unknown', 'n/a'] = 'unknown'
    features: dict[str, bool] = Field(default_factory=dict)


class PrepareCatalogBatchResponse(BaseModel):
    """One-time prepare receipt — hashes/counts/projections only (D-19, PLAN-06).

    Never includes canonical payload, membership, or embeddings.
    """

    plan_token: str
    plan_uuid: str
    request_sha256: str
    catalog_sha256: str
    artifact_sha256: str
    identity_schema_version: str
    expires_at: str
    entity_count: int = 0
    edge_count: int = 0
    source_count: int = 0
    evidence_link_count: int = 0
    projected_created: int = 0
    projected_updated: int = 0
    projected_unchanged: int = 0
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None


class CommitPreparedCatalogBatchResponse(BaseModel):
    """Commit claim receipt — plan_uuid/hashes/state/counts only (PLAN-10/12).

    Never includes membership, payload, embeddings, or plan_token.
    """

    plan_uuid: str
    request_sha256: str | None = None
    catalog_sha256: str | None = None
    artifact_sha256: str | None = None
    state: str
    entity_count: int = 0
    edge_count: int = 0
    source_count: int = 0
    evidence_link_count: int = 0
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None


class DiscardPreparedCatalogBatchResponse(BaseModel):
    """Discard receipt — plan_uuid + terminal state (D-11)."""

    plan_uuid: str | None = None
    state: str = 'DISCARDED'
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None
