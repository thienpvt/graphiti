"""CatalogService: deterministic typed catalog entity upsert orchestration.

Order: validate → uuid5+hash → coalesce → embed → open tx (if not dry_run).
No LLM, no queue, no EntityNode.save.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from config.schema import CatalogConfig
from models.catalog_batch import GetCatalogIngestStatusRequest, UpsertCatalogBatchRequest
from models.catalog_common import (
    IDENTITY_SCHEMA_VERSION,
    PLAN_STATE_COMMITTED,
    PLAN_STATE_COMMITTING,
    PLAN_STATE_DISCARDED,
    PLAN_STATE_EXPIRED,
    PLAN_STATE_PREPARED,
    CatalogErrorCode,
)
from models.catalog_edges import CatalogEdgeItem, UpsertTypedEdgesRequest
from models.catalog_entities import (
    CatalogEntityItem,
    ResolveEntityRef,
    ResolveTypedEntitiesRequest,
    UpsertTypedEntitiesRequest,
    VerifyCatalogBatchRequest,
)
from models.catalog_evidence import CatalogEvidenceLink
from models.catalog_prepare import (
    CommitPreparedCatalogBatchRequest,
    DiscardPreparedCatalogBatchRequest,
    PrepareCatalogBatchRequest,
)
from models.catalog_provenance import CatalogSourceItem, UpsertProvenanceRequest
from models.catalog_responses import (
    CatalogBatchWriteResponse,
    CatalogIngestStatus,
    CatalogIngestStatusResponse,
    CatalogItemResult,
    CatalogWriteResponse,
    CommitPreparedCatalogBatchResponse,
    DiscardPreparedCatalogBatchResponse,
    PrepareCatalogBatchResponse,
    ResolveEntityResult,
    ResolveTypedEntitiesResponse,
    VerifyCatalogBatchResponse,
    VerifyEdgeSection,
    VerifyEntitySection,
)
from models.catalog_topology import validate_edge_endpoint_pair
from services.catalog_identity import (
    CANONICALIZATION_VERSION,
    CATALOG_SCHEMA_VERSION,
    assert_optional_client_hash,
    batch_request_canonical_payload,
    canonical_sha256,
    catalog_batch_uuid,
    catalog_edge_uuid,
    catalog_entity_uuid,
    catalog_evidence_link_uuid,
    catalog_manifest_chunk_uuid,
    catalog_manifest_uuid,
    catalog_mentions_uuid,
    catalog_prepared_plan_chunk_uuid,
    catalog_prepared_plan_uuid,
    catalog_source_uuid,
    coalesce_byte_identical_evidence_links,
    evidence_canonical_payload,
    evidence_link_key,
    mint_plan_token,
    plan_token_digest,
    plan_token_matches,
)
from services.catalog_identity import (
    batch_request_sha256 as pure_batch_request_sha256,
)
from services.catalog_identity import (
    edge_canonical_payload as pure_edge_canonical_payload,
)
from services.catalog_identity import (
    entity_canonical_payload as pure_entity_canonical_payload,
)
from services.catalog_identity import (
    source_canonical_payload as pure_source_canonical_payload,
)
from services.catalog_manifest import (
    build_manifest_body_from_membership,
    chunk_manifest_bytes,
    serialize_manifest_body,
)
from services.catalog_manifest import (
    manifest_sha256 as pure_manifest_sha256,
)
from services.catalog_prepared_artifact import (
    PREPARED_ARTIFACT_SERIALIZATION_VERSION,
    artifact_sha256,
    chunk_artifact_bytes,
    reassemble_artifact_bytes,
    serialize_prepared_artifact,
)
from services.catalog_store import CatalogNeo4jStore, CatalogStoreError

logger = logging.getLogger(__name__)


@dataclass
class _PreparedEntity:
    index: int
    item: CatalogEntityItem
    entity_uuid: str
    content_sha256: str
    name_embedding: list[float] | None = None
    # indices that coalesce onto this prepared write
    coalesced_indices: list[int] = field(default_factory=list)
    existing: dict[str, Any] | None = None
    projected_status: str = 'created'  # created|updated|unchanged|error
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None


@dataclass
class _PreparedEdge:
    index: int
    item: CatalogEdgeItem
    edge_uuid: str
    content_sha256: str
    source_uuid: str | None = None
    target_uuid: str | None = None
    fact_embedding: list[float] | None = None
    coalesced_indices: list[int] = field(default_factory=list)
    existing: dict[str, Any] | None = None
    projected_status: str = 'created'
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None
    batch_result_index: int | None = None


@dataclass
class _PreparedSource:
    index: int
    item: CatalogSourceItem
    source_uuid: str
    content_sha256: str
    content_json: str
    valid_at: datetime
    existing: dict[str, Any] | None = None
    projected_status: str = 'created'  # created|updated|unchanged|error
    error_code: CatalogErrorCode | None = None
    error_message: str | None = None
    # resolved targets after preflight
    entity_uuids: list[str] = field(default_factory=list)
    edge_uuids: list[str] = field(default_factory=list)
    mentions_uuids: list[str] = field(default_factory=list)
    existing_mentions: set[str] = field(default_factory=set)
    existing_edge_links: set[str] = field(default_factory=set)
    links_checked: bool = False
    missing_links: bool = False  # True when any MENTIONS/episode attach still needed
    coalesced_indices: list[int] = field(default_factory=list)


@dataclass
class _BatchPreflightOutcome:
    """Shared preflight result for upsert_catalog_batch and prepare_catalog_batch.

    early_kind is None when projection succeeded (errors empty). Non-None values
    map to structured early exits that must not embed or open domain/plan writes.
    """

    namespace: uuid.UUID | None
    batch_uuid: str | None
    server_hash: str
    hash_echo: dict[str, Any]
    entity_prepared: list[_PreparedEntity] = field(default_factory=list)
    edge_prepared: list[_PreparedEdge] = field(default_factory=list)
    provenance_sources: list[_PreparedSource] = field(default_factory=list)
    edge_offset: int = 0
    request_entity_uuids: dict[tuple[str, str], str] = field(default_factory=dict)
    errors: list[CatalogItemResult] = field(default_factory=list)
    early_kind: str | None = None
    early_code: CatalogErrorCode | None = None
    early_message: str | None = None


@dataclass
class CatalogWriteProjection:
    """Internal projection for one atomic domain+evidence+manifest success tx.

    Built from preflight (upsert) or frozen prepared artifact (commit). Never
    rebuilt from live client re-embed on the prepared-commit path (D-06).
    """

    group_id: str
    batch_id: str
    batch_uuid: str
    request_sha256: str
    catalog_sha256: str
    identity_schema_version: str
    canonicalization_version: str
    namespace: uuid.UUID
    request_ts: datetime
    entity_prepared: list[_PreparedEntity]
    edge_prepared: list[_PreparedEdge]
    provenance_sources: list[_PreparedSource]
    request_entity_uuids: dict[tuple[str, str], str]
    evidence_link_params: list[dict[str, Any]]
    membership: dict[str, Any]
    entity_count: int
    edge_count: int
    provenance_count: int
    edge_offset: int
    request_entity_count: int
    artifact_sha256: str | None = None
    plan: dict[str, Any] | None = None
    request_for_edge_recheck: Any | None = None


class CatalogService:
    """Orchestrates catalog writes against CatalogNeo4jStore + configured embedder."""

    def __init__(
        self,
        catalog_config: CatalogConfig | None = None,
        store: CatalogNeo4jStore | None = None,
        queue_service: Any | None = None,
    ):
        self.catalog_config = catalog_config or CatalogConfig()
        self._store = store or CatalogNeo4jStore()
        # queue_service accepted only so tests can assert it is never used
        self._queue_service = queue_service

    @staticmethod
    def entity_canonical_payload(item: CatalogEntityItem) -> dict[str, Any]:
        """Mutable canonical fields used for content_sha256 (identity excluded)."""
        return pure_entity_canonical_payload(item)

    @staticmethod
    def edge_canonical_payload(item: CatalogEdgeItem) -> dict[str, Any]:
        """Mutable canonical fields used for edge content_sha256 (identity excluded)."""
        return pure_edge_canonical_payload(item)

    def _namespace(self) -> uuid.UUID | None:
        ns = self.catalog_config.uuid_namespace
        if not ns:
            return None
        try:
            return uuid.UUID(ns)
        except (ValueError, AttributeError, TypeError):
            return None

    def _gate_errors(
        self,
        client: Any,
        request: UpsertTypedEntitiesRequest,
    ) -> CatalogWriteResponse | None:
        """Return a full error response if feature/backend/namespace gates fail."""
        n = len(request.entities)

        def _all_error(code: CatalogErrorCode, message: str) -> CatalogWriteResponse:
            results = [
                CatalogItemResult(
                    index=i,
                    status='error',
                    graph_key=request.entities[i].graph_key,
                    entity_type=request.entities[i].entity_type,
                    error_code=code,
                    error_message=message,
                )
                for i in range(n)
            ]
            return CatalogWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                dry_run=request.dry_run,
                atomic=request.atomic,
                results=results,
                failed=n,
            )

        if not self.catalog_config.enabled:
            return _all_error(
                CatalogErrorCode.feature_disabled,
                'catalog_upsert.enabled is false',
            )

        ns = self._namespace()
        if ns is None:
            return _all_error(
                CatalogErrorCode.invalid_uuid_namespace,
                'uuid_namespace missing or invalid',
            )

        provider = getattr(getattr(client, 'driver', None), 'provider', None)
        provider_val = getattr(provider, 'value', provider)
        if provider_val != 'neo4j':
            return _all_error(
                CatalogErrorCode.backend_unavailable,
                'catalog writes require Neo4j backend',
            )

        # batch limit from config
        max_n = self.catalog_config.max_entities_per_batch
        if n > max_n:
            return _all_error(
                CatalogErrorCode.batch_limit_exceeded,
                f'entities exceed max_entities_per_batch ({max_n})',
            )
        return None

    async def _ensure_schema(self, client: Any) -> None:
        """Await product catalog schema readiness immediately before real write tx."""
        await self._store.ensure_uuid_uniqueness_constraints(client.driver)
        # Evidence/manifest constraints outside success tx (same pattern as identity).
        await self._store.ensure_evidence_manifest_schema(client.driver)

    def _schema_fail_entity_response(
        self,
        request: UpsertTypedEntitiesRequest,
        *,
        reason: str,
    ) -> CatalogWriteResponse:
        n = len(request.entities)
        logger.error('catalog schema_init_failed kind=entity reason=%s', reason)
        return CatalogWriteResponse(
            group_id=request.group_id,
            batch_id=request.batch_id,
            dry_run=request.dry_run,
            atomic=request.atomic,
            results=[
                CatalogItemResult(
                    index=i,
                    status='error',
                    graph_key=request.entities[i].graph_key,
                    entity_type=request.entities[i].entity_type,
                    error_code=CatalogErrorCode.neo4j_transaction_failed,
                    error_message='catalog schema initialization failed',
                    details={'reason': reason},
                )
                for i in range(n)
            ],
            failed=n,
        )

    def _schema_fail_edge_response(
        self,
        request: UpsertTypedEdgesRequest,
        *,
        reason: str,
    ) -> CatalogWriteResponse:
        n = len(request.edges)
        logger.error('catalog schema_init_failed kind=edge reason=%s', reason)
        return CatalogWriteResponse(
            group_id=request.group_id,
            batch_id=request.batch_id,
            dry_run=request.dry_run,
            atomic=request.atomic,
            results=[
                CatalogItemResult(
                    index=i,
                    status='error',
                    edge_key=request.edges[i].edge_key,
                    edge_type=request.edges[i].edge_type,
                    error_code=CatalogErrorCode.neo4j_transaction_failed,
                    error_message='catalog schema initialization failed',
                    details={'reason': reason},
                )
                for i in range(n)
            ],
            failed=n,
        )

    async def upsert_typed_entities(
        self,
        *,
        client: Any,
        request: UpsertTypedEntitiesRequest,
    ) -> CatalogWriteResponse:
        gate = self._gate_errors(client, request)
        if gate is not None:
            logger.info(
                'catalog upsert_typed_entities gated batch_id=%s count=%s failed=%s',
                request.batch_id,
                len(request.entities),
                gate.failed,
            )
            return gate

        namespace = self._namespace()
        assert namespace is not None  # gated above

        request_ts = datetime.now(timezone.utc)
        prepared: list[_PreparedEntity] = []
        identity_to_prep: dict[str, _PreparedEntity] = {}
        identity_occurrences: dict[str, list[int]] = {}
        conflicted_entity_uuids: set[str] = set()
        early_errors: dict[int, CatalogItemResult] = {}

        # 1) identity + hash + coalesce
        for idx, item in enumerate(request.entities):
            try:
                payload = self.entity_canonical_payload(item)
                digest = canonical_sha256(payload)
                assert_optional_client_hash(item.content_sha256, digest)
            except ValueError as exc:
                msg = str(exc)
                code = (
                    CatalogErrorCode.content_hash_mismatch
                    if 'content_hash_mismatch' in msg
                    else CatalogErrorCode.validation_error
                )
                early_errors[idx] = CatalogItemResult(
                    index=idx,
                    status='error',
                    graph_key=item.graph_key,
                    entity_type=item.entity_type,
                    error_code=code,
                    error_message=msg,
                )
                continue

            ent_uuid = catalog_entity_uuid(
                namespace, request.group_id, item.entity_type, item.graph_key
            )
            occurrences = identity_occurrences.setdefault(ent_uuid, [])
            occurrences.append(idx)
            if ent_uuid in conflicted_entity_uuids:
                early_errors[idx] = CatalogItemResult(
                    index=idx,
                    status='error',
                    uuid=ent_uuid,
                    graph_key=item.graph_key,
                    entity_type=item.entity_type,
                    error_code=CatalogErrorCode.deterministic_uuid_conflict,
                    error_message='same identity different canonical payload in request',
                )
                continue
            if ent_uuid in identity_to_prep:
                prior = identity_to_prep[ent_uuid]
                if prior.content_sha256 != digest:
                    conflicted_entity_uuids.add(ent_uuid)
                    for occurrence in occurrences:
                        occurrence_item = request.entities[occurrence]
                        early_errors[occurrence] = CatalogItemResult(
                            index=occurrence,
                            status='error',
                            uuid=ent_uuid,
                            graph_key=occurrence_item.graph_key,
                            entity_type=occurrence_item.entity_type,
                            error_code=CatalogErrorCode.deterministic_uuid_conflict,
                            error_message='same identity different canonical payload in request',
                        )
                    if prior in prepared:
                        prepared.remove(prior)
                    identity_to_prep.pop(ent_uuid, None)
                    continue
                prior.coalesced_indices.append(idx)
                continue

            prep = _PreparedEntity(
                index=idx,
                item=item,
                entity_uuid=ent_uuid,
                content_sha256=digest,
            )
            prepared.append(prep)
            identity_to_prep[ent_uuid] = prep

        # If any early validation errors and atomic → mark all as rolled_back/error
        if early_errors and request.atomic:
            return self._atomic_fail_response(
                request,
                early_errors,
                trigger_indices=set(early_errors.keys()),
            )

        # 2) load existing for conflict / unchanged decisions (read, may use execute_query)
        driver = client.driver
        for prep in prepared:
            try:
                existing = await self._store.get_entity_by_uuid(
                    driver,
                    uuid=prep.entity_uuid,
                    group_id=request.group_id,
                )
            except Exception as exc:
                # Fail closed: DB read failure is not "absent".
                logger.error(
                    'catalog entity_pre_read_failed batch_id=%s reason=%s',
                    request.batch_id,
                    type(exc).__name__,
                )
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.internal_error
                prep.error_message = 'entity pre-read failed'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.entity_uuid,
                    content_sha256=prep.content_sha256,
                    graph_key=prep.item.graph_key,
                    entity_type=prep.item.entity_type,
                    error_code=prep.error_code,
                    error_message=prep.error_message,
                    details={'reason': type(exc).__name__},
                )
                continue
            prep.existing = existing
            if existing is None:
                prep.projected_status = 'created'
                continue
            label_err = self._entity_label_conflict(existing, prep.item.entity_type)
            if label_err is not None:
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.entity_type_conflict
                prep.error_message = label_err
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.entity_uuid,
                    content_sha256=prep.content_sha256,
                    graph_key=prep.item.graph_key,
                    entity_type=prep.item.entity_type,
                    error_code=prep.error_code,
                    error_message=prep.error_message,
                )
                continue
            id_err = self._entity_identity_property_conflict(existing, prep.item)
            if id_err is not None:
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.deterministic_uuid_conflict
                prep.error_message = id_err
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.entity_uuid,
                    content_sha256=prep.content_sha256,
                    graph_key=prep.item.graph_key,
                    entity_type=prep.item.entity_type,
                    error_code=prep.error_code,
                    error_message=prep.error_message,
                )
                continue
            if existing.get('content_sha256') == prep.content_sha256:
                prep.projected_status = 'unchanged'
            else:
                prep.projected_status = 'updated'

        # drop conflicted from write set
        write_set = [p for p in prepared if p.projected_status != 'error']
        conflicted = [p for p in prepared if p.projected_status == 'error']

        if conflicted and request.atomic:
            for p in conflicted:
                early_errors[p.index] = CatalogItemResult(
                    index=p.index,
                    status='error',
                    uuid=p.entity_uuid,
                    content_sha256=p.content_sha256,
                    graph_key=p.item.graph_key,
                    entity_type=p.item.entity_type,
                    error_code=p.error_code,
                    error_message=p.error_message,
                )
            return self._atomic_fail_response(
                request,
                early_errors,
                trigger_indices={p.index for p in conflicted} | set(early_errors.keys()),
            )

        # 3) embed for non-unchanged items (including dry-run readiness)
        embed_targets = [p for p in write_set if p.projected_status != 'unchanged']
        embedder = client.embedder
        try:
            for prep in embed_targets:
                text = ' '.join(
                    [
                        prep.item.graph_key,
                        prep.item.database_qualified_name,
                        prep.item.summary,
                    ]
                ).replace('\n', ' ')
                prep.name_embedding = await embedder.create(input_data=[text])
        except Exception as exc:
            logger.error(
                'catalog embedding_failed batch_id=%s count=%s',
                request.batch_id,
                len(embed_targets),
            )
            err_results = []
            for i, item in enumerate(request.entities):
                if i in early_errors:
                    err_results.append(early_errors[i])
                else:
                    err_results.append(
                        CatalogItemResult(
                            index=i,
                            status='error',
                            graph_key=item.graph_key,
                            entity_type=item.entity_type,
                            error_code=CatalogErrorCode.embedding_failed,
                            error_message='embedding generation failed',
                            details={'reason': type(exc).__name__},
                        )
                    )
            return CatalogWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                dry_run=request.dry_run,
                atomic=request.atomic,
                results=sorted(err_results, key=lambda r: r.index),
                failed=len(err_results),
            )

        # 4) dry-run: no transaction, no batch_id persistence
        if request.dry_run:
            results = self._build_results(
                request,
                write_set,
                early_errors,
                written={},
            )
            resp = self._count_response(request, results)
            logger.info(
                'catalog upsert_typed_entities dry_run batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
                request.batch_id,
                len(request.entities),
                resp.created,
                resp.updated,
                resp.unchanged,
                resp.failed,
            )
            return resp

        # 5) schema ensure only for real writes (never dry-run / embed failure path)
        try:
            await self._ensure_schema(client)
        except CatalogStoreError as exc:
            return self._schema_fail_entity_response(request, reason=type(exc).__name__)
        except Exception as exc:
            return self._schema_fail_entity_response(request, reason=type(exc).__name__)

        # 6) write
        if request.atomic:
            return await self._write_atomic(client, request, write_set, early_errors, request_ts)
        return await self._write_per_item(client, request, write_set, early_errors, request_ts)

    async def _write_atomic(
        self,
        client: Any,
        request: UpsertTypedEntitiesRequest,
        write_set: list[_PreparedEntity],
        early_errors: dict[int, CatalogItemResult],
        request_ts: datetime,
    ) -> CatalogWriteResponse:
        written: dict[int, CatalogItemResult] = {}
        to_write = [p for p in write_set if p.projected_status != 'unchanged']
        unchanged = [p for p in write_set if p.projected_status == 'unchanged']
        for p in unchanged:
            written[p.index] = self._success_result(p, 'unchanged')
            for ci in p.coalesced_indices:
                written[ci] = self._success_result(p, 'unchanged', index=ci)

        if not to_write:
            results = self._build_results(request, write_set, early_errors, written)
            resp = self._count_response(request, results)
            logger.info(
                'catalog upsert_typed_entities batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
                request.batch_id,
                len(request.entities),
                resp.created,
                resp.updated,
                resp.unchanged,
                resp.failed,
            )
            return resp

        current_prep: _PreparedEntity | None = None
        try:
            async with client.driver.transaction() as tx:
                for prep in to_write:
                    current_prep = prep
                    inv_err = await self._recheck_entity_in_tx(tx, prep, request)
                    if inv_err is not None:
                        raise self._EntityInvariantRace(inv_err)
                    params = self._params_for(prep, request, request_ts)
                    row = await self._store.upsert_entity_item(
                        tx, entity_type=prep.item.entity_type, params=params
                    )
                    if not row or not row.get('uuid'):
                        raise RuntimeError('entity upsert empty row')
                    self._raise_entity_row_error(row)
                    # Prefer DB-captured status (create-token / hash-derived).
                    status = self._write_status_from_row(row, prep.projected_status)
                    result = CatalogItemResult(
                        index=prep.index,
                        status=status,  # type: ignore[arg-type]
                        uuid=prep.entity_uuid,
                        content_sha256=prep.content_sha256,
                        graph_key=prep.item.graph_key,
                        entity_type=prep.item.entity_type,
                    )
                    written[prep.index] = result
                    for ci in prep.coalesced_indices:
                        written[ci] = CatalogItemResult(
                            index=ci,
                            status=status,  # type: ignore[arg-type]
                            uuid=prep.entity_uuid,
                            content_sha256=prep.content_sha256,
                            graph_key=request.entities[ci].graph_key,
                            entity_type=request.entities[ci].entity_type,
                        )
        except CatalogStoreError as exc:
            mapped = self._map_store_error_code(exc)
            trigger = current_prep or (to_write[0] if to_write else None)
            trigger_idx = trigger.index if trigger is not None else 0
            early_errors[trigger_idx] = CatalogItemResult(
                index=trigger_idx,
                status='error',
                uuid=trigger.entity_uuid if trigger is not None else None,
                graph_key=trigger.item.graph_key if trigger is not None else None,
                entity_type=trigger.item.entity_type if trigger is not None else None,
                error_code=mapped,
                error_message=(
                    'embedding generation failed'
                    if mapped == CatalogErrorCode.embedding_failed
                    else str(exc) or mapped.value
                ),
            )
            return self._atomic_fail_response(
                request,
                early_errors,
                trigger_indices={trigger_idx},
            )
        except self._EntityInvariantRace as exc:
            trigger = current_prep or (to_write[0] if to_write else None)
            trigger_idx = trigger.index if trigger is not None else 0
            early_errors[trigger_idx] = CatalogItemResult(
                index=trigger_idx,
                status='error',
                uuid=trigger.entity_uuid if trigger is not None else None,
                graph_key=trigger.item.graph_key if trigger is not None else None,
                entity_type=trigger.item.entity_type if trigger is not None else None,
                error_code=exc.code,
                error_message=f'entity invariant race in write transaction: {exc.code.value}',
            )
            return self._atomic_fail_response(
                request,
                early_errors,
                trigger_indices={trigger_idx},
            )
        except Exception as exc:
            logger.error(
                'catalog neo4j_transaction_failed batch_id=%s count=%s',
                request.batch_id,
                len(to_write),
            )
            # entire batch rolled back; attribute error to the item being written
            trigger = current_prep or (to_write[0] if to_write else None)
            trigger_idx = trigger.index if trigger is not None else 0
            early_errors[trigger_idx] = CatalogItemResult(
                index=trigger_idx,
                status='error',
                uuid=trigger.entity_uuid if trigger is not None else None,
                graph_key=trigger.item.graph_key if trigger is not None else None,
                entity_type=trigger.item.entity_type if trigger is not None else None,
                error_code=CatalogErrorCode.neo4j_transaction_failed,
                error_message='neo4j transaction failed',
                details={'reason': type(exc).__name__},
            )
            return self._atomic_fail_response(
                request,
                early_errors,
                trigger_indices={trigger_idx},
            )

        results = self._build_results(request, write_set, early_errors, written)
        resp = self._count_response(request, results)
        logger.info(
            'catalog upsert_typed_entities batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
            request.batch_id,
            len(request.entities),
            resp.created,
            resp.updated,
            resp.unchanged,
            resp.failed,
        )
        return resp

    async def _write_per_item(
        self,
        client: Any,
        request: UpsertTypedEntitiesRequest,
        write_set: list[_PreparedEntity],
        early_errors: dict[int, CatalogItemResult],
        request_ts: datetime,
    ) -> CatalogWriteResponse:
        written: dict[int, CatalogItemResult] = {}
        for prep in write_set:
            if prep.projected_status == 'unchanged':
                written[prep.index] = self._success_result(prep, 'unchanged')
                for ci in prep.coalesced_indices:
                    written[ci] = self._success_result(prep, 'unchanged', index=ci)
                continue
            try:
                async with client.driver.transaction() as tx:
                    inv_err = await self._recheck_entity_in_tx(tx, prep, request)
                    if inv_err is not None:
                        written[prep.index] = CatalogItemResult(
                            index=prep.index,
                            status='error',
                            uuid=prep.entity_uuid,
                            graph_key=prep.item.graph_key,
                            entity_type=prep.item.entity_type,
                            error_code=inv_err,
                            error_message=(
                                f'entity invariant race in write transaction: {inv_err.value}'
                            ),
                        )
                        for ci in prep.coalesced_indices:
                            written[ci] = CatalogItemResult(
                                index=ci,
                                status='error',
                                uuid=prep.entity_uuid,
                                graph_key=request.entities[ci].graph_key,
                                entity_type=request.entities[ci].entity_type,
                                error_code=inv_err,
                                error_message=(
                                    f'entity invariant race in write transaction: {inv_err.value}'
                                ),
                            )
                        continue
                    params = self._params_for(prep, request, request_ts)
                    row = await self._store.upsert_entity_item(
                        tx, entity_type=prep.item.entity_type, params=params
                    )
                    if not row or not row.get('uuid'):
                        raise RuntimeError('entity upsert empty row')
                    row_err = self._row_error_code(row)
                    if row_err is not None:
                        written[prep.index] = CatalogItemResult(
                            index=prep.index,
                            status='error',
                            uuid=prep.entity_uuid,
                            graph_key=prep.item.graph_key,
                            entity_type=prep.item.entity_type,
                            error_code=row_err,
                            error_message=(f'entity under-lock conflict: {row_err.value}'),
                        )
                        for ci in prep.coalesced_indices:
                            written[ci] = CatalogItemResult(
                                index=ci,
                                status='error',
                                uuid=prep.entity_uuid,
                                graph_key=request.entities[ci].graph_key,
                                entity_type=request.entities[ci].entity_type,
                                error_code=row_err,
                                error_message=(f'entity under-lock conflict: {row_err.value}'),
                            )
                        continue
                    status = self._write_status_from_row(row, prep.projected_status)
                    written[prep.index] = CatalogItemResult(
                        index=prep.index,
                        status=status,  # type: ignore[arg-type]
                        uuid=prep.entity_uuid,
                        content_sha256=prep.content_sha256,
                        graph_key=prep.item.graph_key,
                        entity_type=prep.item.entity_type,
                    )
                    for ci in prep.coalesced_indices:
                        written[ci] = CatalogItemResult(
                            index=ci,
                            status=status,  # type: ignore[arg-type]
                            uuid=prep.entity_uuid,
                            content_sha256=prep.content_sha256,
                            graph_key=request.entities[ci].graph_key,
                            entity_type=request.entities[ci].entity_type,
                        )
            except CatalogStoreError as exc:
                mapped = self._map_store_error_code(exc)
                message = (
                    'embedding generation failed'
                    if mapped == CatalogErrorCode.embedding_failed
                    else str(exc) or mapped.value
                )
                written[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.entity_uuid,
                    graph_key=prep.item.graph_key,
                    entity_type=prep.item.entity_type,
                    error_code=mapped,
                    error_message=message,
                )
                for ci in prep.coalesced_indices:
                    written[ci] = CatalogItemResult(
                        index=ci,
                        status='error',
                        uuid=prep.entity_uuid,
                        graph_key=request.entities[ci].graph_key,
                        entity_type=request.entities[ci].entity_type,
                        error_code=mapped,
                        error_message=message,
                    )
                continue
            except self._EntityInvariantRace as exc:
                written[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.entity_uuid,
                    graph_key=prep.item.graph_key,
                    entity_type=prep.item.entity_type,
                    error_code=exc.code,
                    error_message=f'entity invariant race in write transaction: {exc.code.value}',
                )
                for ci in prep.coalesced_indices:
                    written[ci] = CatalogItemResult(
                        index=ci,
                        status='error',
                        uuid=prep.entity_uuid,
                        graph_key=request.entities[ci].graph_key,
                        entity_type=request.entities[ci].entity_type,
                        error_code=exc.code,
                        error_message=(
                            f'entity invariant race in write transaction: {exc.code.value}'
                        ),
                    )
            except Exception as exc:
                logger.error(
                    'catalog neo4j_transaction_failed batch_id=%s index=%s',
                    request.batch_id,
                    prep.index,
                )
                written[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.entity_uuid,
                    graph_key=prep.item.graph_key,
                    entity_type=prep.item.entity_type,
                    error_code=CatalogErrorCode.neo4j_transaction_failed,
                    error_message='neo4j transaction failed',
                    details={'reason': type(exc).__name__},
                )
                for ci in prep.coalesced_indices:
                    written[ci] = CatalogItemResult(
                        index=ci,
                        status='error',
                        uuid=prep.entity_uuid,
                        graph_key=request.entities[ci].graph_key,
                        entity_type=request.entities[ci].entity_type,
                        error_code=CatalogErrorCode.neo4j_transaction_failed,
                        error_message='neo4j transaction failed',
                    )

        results = self._build_results(request, write_set, early_errors, written)
        resp = self._count_response(request, results)
        logger.info(
            'catalog upsert_typed_entities batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
            request.batch_id,
            len(request.entities),
            resp.created,
            resp.updated,
            resp.unchanged,
            resp.failed,
        )
        return resp

    @staticmethod
    def _row_error_code(row: dict[str, Any]) -> CatalogErrorCode | None:
        """Consume authoritative under-lock error_code before status fallback."""
        error_code = row.get('error_code')
        if error_code is None:
            return None
        if error_code == CatalogErrorCode.deterministic_uuid_conflict.value:
            return CatalogErrorCode.deterministic_uuid_conflict
        if error_code == CatalogErrorCode.entity_type_conflict.value:
            return CatalogErrorCode.entity_type_conflict
        if error_code == CatalogErrorCode.edge_identity_conflict.value:
            return CatalogErrorCode.edge_identity_conflict
        if error_code == CatalogErrorCode.batch_conflict.value:
            return CatalogErrorCode.batch_conflict
        # Unknown error_code with status=error fails closed.
        if row.get('status') == 'error':
            return CatalogErrorCode.internal_error
        return None

    def _raise_entity_row_error(self, row: dict[str, Any]) -> None:
        code = self._row_error_code(row)
        if code is None:
            return
        raise self._EntityInvariantRace(code)

    def _raise_edge_row_error(self, row: dict[str, Any]) -> None:
        code = self._row_error_code(row)
        if code is None:
            return
        raise self._EdgeEndpointRace(code)

    @staticmethod
    def _write_status_from_row(row: dict[str, Any], projected: str) -> str:
        """Prefer DB-captured write status; never reinterpret status=error as success."""
        status = row.get('status')
        if status == 'error' or row.get('error_code') is not None:
            return 'error'
        if status in ('created', 'updated', 'unchanged'):
            return str(status)
        if projected in ('created', 'updated', 'unchanged'):
            return projected
        return 'updated'

    def _entity_label_conflict(self, existing: dict[str, Any], expected_type: str) -> str | None:
        """Return conflict message unless labels are exactly Entity + expected custom type.

        Bare generic Entity and multi-label / wrong-type rows cannot be silently mutated.
        """
        labels = self._node_labels(existing)
        custom = self._custom_labels(labels)
        if not custom:
            return 'existing entity is generic Entity only; cannot mutate into typed catalog entity'
        if set(custom) != {expected_type}:
            return f'existing custom labels {custom} conflict with exact type {expected_type}'
        return None

    def _entity_identity_property_conflict(
        self,
        existing: dict[str, Any],
        item: CatalogEntityItem,
    ) -> str | None:
        """Fail closed when stored identity props disagree with request (IDEN-08).

        name, graph_key, name_raw, name_canonical are create-once; never rewrite.
        """
        stored_name = existing.get('name')
        stored_key = existing.get('graph_key')
        stored_raw = existing.get('name_raw')
        stored_canon = existing.get('name_canonical')
        # name property is graph_key for catalog entities
        if stored_name is not None and stored_name != item.graph_key:
            return 'existing name conflicts with request graph_key'
        if stored_key is not None and stored_key != item.graph_key:
            return 'existing graph_key conflicts with request graph_key'
        if stored_raw is not None and stored_raw != item.name_raw:
            return 'existing name_raw conflicts with request name_raw'
        if stored_canon is not None and stored_canon != item.name_canonical:
            return 'existing name_canonical conflicts with request name_canonical'
        return None

    async def _recheck_entity_in_tx(
        self,
        tx: Any,
        prep: _PreparedEntity,
        request: UpsertTypedEntitiesRequest,
    ) -> CatalogErrorCode | None:
        """Transaction-local label/identity invariant before entity mutation."""
        try:
            existing = await self._store.get_entity_by_uuid(
                None,
                uuid=prep.entity_uuid,
                group_id=request.group_id,
                tx=tx,
            )
        except Exception as exc:
            logger.error(
                'catalog entity_in_tx_recheck_failed batch_id=%s reason=%s',
                request.batch_id,
                type(exc).__name__,
            )
            return CatalogErrorCode.internal_error
        if existing is None:
            return None
        if self._entity_label_conflict(existing, prep.item.entity_type) is not None:
            return CatalogErrorCode.entity_type_conflict
        if self._entity_identity_property_conflict(existing, prep.item) is not None:
            return CatalogErrorCode.deterministic_uuid_conflict
        return None

    class _EntityInvariantRace(Exception):
        """Internal signal: entity label/identity race inside write transaction."""

        def __init__(self, code: CatalogErrorCode):
            self.code = code
            super().__init__(code.value)

    def _params_for(
        self,
        prep: _PreparedEntity,
        request: UpsertTypedEntitiesRequest,
        request_ts: datetime,
    ) -> dict[str, Any]:
        item = prep.item
        # Fail closed: typed non-unchanged writes must never send empty vectors.
        if not prep.name_embedding:
            raise CatalogStoreError(
                'name_embedding missing for non-unchanged entity',
                code='embedding_failed',
            )
        embedding = list(prep.name_embedding)
        return self._store.prepare_entity_params(
            entity_type=item.entity_type,
            uuid=prep.entity_uuid,
            group_id=request.group_id,
            batch_id=request.batch_id,
            graph_key=item.graph_key,
            name_raw=item.name_raw,
            name_canonical=item.name_canonical,
            database_qualified_name=item.database_qualified_name,
            summary=item.summary,
            content_sha256=prep.content_sha256,
            created_at=request_ts,
            updated_at=request_ts,
            name_embedding=embedding,
            attributes=item.attributes,
            source_refs=(
                [ref.model_dump(mode='json') for ref in item.source_refs]
                if item.source_refs is not None
                else None
            ),
            confidence=item.confidence,
        )

    def _success_result(
        self,
        prep: _PreparedEntity,
        status: str,
        *,
        index: int | None = None,
    ) -> CatalogItemResult:
        return CatalogItemResult(
            index=prep.index if index is None else index,
            status=status,  # type: ignore[arg-type]
            uuid=prep.entity_uuid,
            content_sha256=prep.content_sha256,
            graph_key=prep.item.graph_key,
            entity_type=prep.item.entity_type,
        )

    def _build_results(
        self,
        request: UpsertTypedEntitiesRequest,
        write_set: list[_PreparedEntity],
        early_errors: dict[int, CatalogItemResult],
        written: dict[int, CatalogItemResult],
    ) -> list[CatalogItemResult]:
        # fill dry-run projected results for write_set not in written
        by_index: dict[int, CatalogItemResult] = dict(early_errors)
        by_index.update(written)
        for prep in write_set:
            if prep.index not in by_index:
                by_index[prep.index] = self._success_result(prep, prep.projected_status)
            for ci in prep.coalesced_indices:
                if ci not in by_index:
                    by_index[ci] = self._success_result(prep, prep.projected_status, index=ci)
        results: list[CatalogItemResult] = []
        for i, item in enumerate(request.entities):
            if i in by_index:
                results.append(by_index[i])
            else:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='error',
                        graph_key=item.graph_key,
                        entity_type=item.entity_type,
                        error_code=CatalogErrorCode.internal_error,
                        error_message='missing result',
                    )
                )
        return sorted(results, key=lambda r: r.index)

    def _count_response(
        self,
        request: UpsertTypedEntitiesRequest,
        results: list[CatalogItemResult],
    ) -> CatalogWriteResponse:
        created = sum(1 for r in results if r.status == 'created')
        updated = sum(1 for r in results if r.status == 'updated')
        unchanged = sum(1 for r in results if r.status == 'unchanged')
        failed = sum(1 for r in results if r.status == 'error')
        rolled_back = sum(1 for r in results if r.status == 'rolled_back')
        return CatalogWriteResponse(
            group_id=request.group_id,
            batch_id=request.batch_id,
            dry_run=request.dry_run,
            atomic=request.atomic,
            results=results,
            created=created,
            updated=updated,
            unchanged=unchanged,
            failed=failed,
            rolled_back=rolled_back,
        )

    def _atomic_fail_response(
        self,
        request: UpsertTypedEntitiesRequest,
        early_errors: dict[int, CatalogItemResult],
        trigger_indices: set[int],
    ) -> CatalogWriteResponse:
        results: list[CatalogItemResult] = []
        for i, item in enumerate(request.entities):
            if i in early_errors:
                err = early_errors[i]
                # keep error status for triggers
                results.append(err)
            elif i in trigger_indices:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='error',
                        graph_key=item.graph_key,
                        entity_type=item.entity_type,
                        error_code=CatalogErrorCode.neo4j_transaction_failed,
                        error_message='neo4j transaction failed',
                    )
                )
            else:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='rolled_back',
                        graph_key=item.graph_key,
                        entity_type=item.entity_type,
                        error_code=CatalogErrorCode.batch_conflict,
                        error_message='rolled back due to sibling failure',
                    )
                )
        results = sorted(results, key=lambda r: r.index)
        resp = self._count_response(request, results)
        logger.info(
            'catalog upsert_typed_entities atomic_fail batch_id=%s count=%s failed=%s rolled_back=%s',
            request.batch_id,
            len(request.entities),
            resp.failed,
            resp.rolled_back,
        )
        return resp

    # ------------------------------------------------------------------
    # Read-only resolve / verify
    # ------------------------------------------------------------------

    def _read_gate(
        self,
        client: Any,
        *,
        group_id: str,
        item_count: int,
    ) -> tuple[CatalogErrorCode, str] | None:
        """Shared feature/namespace/backend gates for read-only tools."""
        # group_id required at call sites for isolation; validate non-empty early.
        if not group_id:
            return (
                CatalogErrorCode.validation_error,
                'group_id is required',
            )
        if not self.catalog_config.enabled:
            return (
                CatalogErrorCode.feature_disabled,
                'catalog_upsert.enabled is false',
            )
        if self._namespace() is None:
            return (
                CatalogErrorCode.invalid_uuid_namespace,
                'uuid_namespace missing or invalid',
            )
        provider = getattr(getattr(client, 'driver', None), 'provider', None)
        provider_val = getattr(provider, 'value', provider)
        if provider_val != 'neo4j':
            return (
                CatalogErrorCode.backend_unavailable,
                'catalog operations require Neo4j backend',
            )
        max_n = self.catalog_config.max_entities_per_batch
        if item_count > max_n:
            return (
                CatalogErrorCode.batch_limit_exceeded,
                f'items exceed max_entities_per_batch ({max_n})',
            )
        return None

    @staticmethod
    def _node_labels(row: dict[str, Any]) -> list[str]:
        labels = row.get('neo4j_labels') or row.get('labels') or []
        if isinstance(labels, str):
            return [labels]
        return list(labels)

    @staticmethod
    def _custom_labels(labels: list[str]) -> list[str]:
        return [lb for lb in labels if lb != 'Entity']

    @staticmethod
    def _row_key(row: dict[str, Any]) -> str | None:
        return row.get('graph_key') or row.get('name')

    async def resolve_typed_entities(
        self,
        *,
        client: Any,
        request: ResolveTypedEntitiesRequest,
    ) -> ResolveTypedEntitiesResponse:
        """Read-only resolve of typed catalog entities (RESO-01..04).

        Never opens a write transaction or calls the embedder.
        """
        refs = list(request.entities)

        gate = self._read_gate(client, group_id=request.group_id, item_count=len(refs))
        if gate is not None:
            code, message = gate
            results = [
                ResolveEntityResult(
                    index=i,
                    entity_type=ref.entity_type,
                    graph_key=ref.graph_key,
                    status='error',
                    found=False,
                    error_code=code,
                    error_message=message,
                    anomalies=[code.value if hasattr(code, 'value') else str(code)],
                )
                for i, ref in enumerate(refs)
            ]
            logger.info(
                'catalog resolve_typed_entities gated count=%s code=%s',
                len(refs),
                code,
            )
            return ResolveTypedEntitiesResponse(group_id=request.group_id, results=results)

        # Resolve is read-only: never schema-init or write.
        namespace = self._namespace()
        assert namespace is not None

        graph_keys = [ref.graph_key for ref in refs]
        try:
            rows = await self._store.match_entities_for_resolve(
                client.driver,
                group_id=request.group_id,
                graph_keys=graph_keys,
            )
        except Exception as exc:
            logger.error(
                'catalog resolve_typed_entities read_failed count=%s reason=%s',
                len(refs),
                type(exc).__name__,
            )
            return ResolveTypedEntitiesResponse(
                group_id=request.group_id,
                results=[
                    ResolveEntityResult(
                        index=i,
                        entity_type=ref.entity_type,
                        graph_key=ref.graph_key,
                        status='error',
                        found=False,
                        error_code=CatalogErrorCode.internal_error,
                        error_message='resolve read failed',
                        anomalies=['internal_error'],
                    )
                    for i, ref in enumerate(refs)
                ],
            )

        by_key: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = self._row_key(row)
            if not key:
                continue
            by_key.setdefault(str(key), []).append(row)

        results: list[ResolveEntityResult] = []
        for i, ref in enumerate(refs):
            expected_uuid = catalog_entity_uuid(
                namespace, request.group_id, ref.entity_type, ref.graph_key
            )
            matches = by_key.get(ref.graph_key, [])
            result = self._analyze_resolve_item(
                index=i,
                ref=ref,
                expected_uuid=expected_uuid,
                matches=matches,
            )
            results.append(result)

        logger.info(
            'catalog resolve_typed_entities count=%s found=%s',
            len(refs),
            sum(1 for r in results if r.found),
        )
        return ResolveTypedEntitiesResponse(group_id=request.group_id, results=results)

    def _analyze_resolve_item(
        self,
        *,
        index: int,
        ref: ResolveEntityRef,
        expected_uuid: str,
        matches: list[dict[str, Any]],
    ) -> ResolveEntityResult:
        if not matches:
            return ResolveEntityResult(
                index=index,
                entity_type=ref.entity_type,
                graph_key=ref.graph_key,
                status='missing',
                found=False,
                uuid=None,
                anomalies=['missing'],
            )

        generic_dups: list[str] = []
        typed_nodes: list[dict[str, Any]] = []
        wrong_type_nodes: list[dict[str, Any]] = []

        for row in matches:
            labels = self._node_labels(row)
            custom = self._custom_labels(labels)
            uuid_val = str(row.get('uuid') or '')
            if not custom:
                # bare generic Entity with name/graph_key match
                if uuid_val:
                    generic_dups.append(uuid_val)
                continue
            if set(custom) == {ref.entity_type}:
                typed_nodes.append(row)
            else:
                wrong_type_nodes.append(row)

        anomalies: list[str] = []
        if generic_dups:
            anomalies.append('generic_duplicate')
        if wrong_type_nodes:
            anomalies.append('wrong_type')

        primary: dict[str, Any] | None = None
        typed_dups: list[str] = []

        if typed_nodes:
            # Prefer exact expected UUID, else first typed
            for row in typed_nodes:
                if str(row.get('uuid')) == expected_uuid:
                    primary = row
                    break
            if primary is None:
                primary = typed_nodes[0]
            for row in typed_nodes:
                u = str(row.get('uuid') or '')
                if primary is not None and u and u != str(primary.get('uuid')):
                    typed_dups.append(u)
            if len(typed_nodes) > 1:
                anomalies.append('typed_duplicate')
            # All-row: any typed UUID differing from expected is a mismatch,
            # even when the preferred primary is the expected row.
            if any(str(row.get('uuid') or '') != expected_uuid for row in typed_nodes):
                anomalies.append('uuid_mismatch')
            if any(not row.get('has_name_embedding') for row in typed_nodes):
                anomalies.append('missing_embedding')
        elif wrong_type_nodes:
            primary = wrong_type_nodes[0]
            if any(not row.get('has_name_embedding') for row in wrong_type_nodes):
                anomalies.append('missing_embedding')
        elif generic_dups:
            # only bare generics — found as anomaly state, not verified typed
            primary = next(
                (m for m in matches if str(m.get('uuid')) == generic_dups[0]),
                matches[0],
            )
            anomalies.append('missing')  # no typed node
            if any(
                not row.get('has_name_embedding')
                for row in matches
                if not self._custom_labels(self._node_labels(row))
            ):
                anomalies.append('missing_embedding')

        if primary is None:
            return ResolveEntityResult(
                index=index,
                entity_type=ref.entity_type,
                graph_key=ref.graph_key,
                status='missing',
                found=False,
                generic_duplicates=generic_dups,
                anomalies=anomalies or ['missing'],
            )

        labels = self._node_labels(primary)
        custom = self._custom_labels(labels)
        exact_typed = set(custom) == {ref.entity_type}
        if exact_typed:
            verified = ref.entity_type
        elif custom:
            # Multi-label / wrong-type: prefer a label that is not the expected type.
            verified = next((c for c in custom if c != ref.entity_type), custom[0])
        else:
            verified = None
        has_emb = bool(primary.get('has_name_embedding'))
        uuid_val = str(primary.get('uuid') or '') or None

        # Primary-only fallbacks when no typed rows (wrong/generic primary path).
        if not typed_nodes:
            if uuid_val and uuid_val != expected_uuid:
                anomalies.append('uuid_mismatch')
            if not has_emb and 'missing_embedding' not in anomalies:
                anomalies.append('missing_embedding')

        # Deduplicate anomaly tags while preserving order
        seen_a: set[str] = set()
        ordered_anomalies: list[str] = []
        for a in anomalies:
            if a not in seen_a:
                seen_a.add(a)
                ordered_anomalies.append(a)

        if exact_typed:
            status = 'found'
        elif custom:
            status = 'wrong_type'
        else:
            # bare generic Entity: found for diagnostics, not verified typed
            status = 'generic_only'
            ordered_anomalies = [a for a in ordered_anomalies if a != 'missing']
            if 'generic_duplicate' not in ordered_anomalies:
                ordered_anomalies.insert(0, 'generic_duplicate')
        found = True

        return ResolveEntityResult(
            index=index,
            entity_type=ref.entity_type,
            graph_key=ref.graph_key,
            status=status,
            found=found,
            uuid=uuid_val,
            labels=labels,
            verified_type=verified,
            has_name_embedding=has_emb,
            content_sha256=primary.get('content_sha256'),
            generic_duplicates=generic_dups,
            typed_duplicates=typed_dups,
            anomalies=ordered_anomalies,
        )

    async def verify_catalog_batch(
        self,
        *,
        client: Any,
        request: VerifyCatalogBatchRequest,
    ) -> VerifyCatalogBatchResponse:
        """Read-only batch verification (VERI-01..05). No writes, no embeddings."""
        entity_count = len(request.entities)
        edge_count = len(request.edges)
        gate = self._read_gate(
            client,
            group_id=request.group_id,
            item_count=max(entity_count, 1),
        )
        if gate is not None:
            code, message = gate
            logger.info(
                'catalog verify_catalog_batch gated batch_id=%s code=%s',
                request.batch_id,
                code,
            )
            return VerifyCatalogBatchResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                require_provenance=request.require_provenance,
                error_code=code,
                error_message=message,
            )

        max_edges = self.catalog_config.max_edges_per_batch
        if edge_count > max_edges:
            return VerifyCatalogBatchResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                require_provenance=request.require_provenance,
                error_code=CatalogErrorCode.batch_limit_exceeded,
                error_message=f'edges exceed max_edges_per_batch ({max_edges})',
            )

        # Verify is read-only: never schema-init or write.
        namespace = self._namespace()
        assert namespace is not None

        graph_keys = [e.graph_key for e in request.entities]
        edge_keys = [e.edge_key for e in request.edges]

        try:
            entity_rows = await self._store.match_entities_for_verify(
                client.driver,
                group_id=request.group_id,
                batch_id=request.batch_id,
                graph_keys=graph_keys or None,
            )
            edge_rows = await self._store.match_edges_for_verify(
                client.driver,
                group_id=request.group_id,
                batch_id=request.batch_id,
                edge_keys=edge_keys or None,
            )
        except Exception as exc:
            logger.error(
                'catalog verify_catalog_batch read_failed batch_id=%s reason=%s',
                request.batch_id,
                type(exc).__name__,
            )
            return VerifyCatalogBatchResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                require_provenance=request.require_provenance,
                error_code=CatalogErrorCode.internal_error,
                error_message='verify read failed',
            )

        entity_section = self._verify_entities(
            namespace=namespace,
            group_id=request.group_id,
            expected=request.entities,
            rows=entity_rows,
        )
        edge_section = self._verify_edges(
            namespace=namespace,
            group_id=request.group_id,
            expected=request.edges,
            rows=edge_rows,
        )

        missing = list(entity_section.missing) + list(edge_section.missing)
        anomalies: list[dict[str, Any]] = []
        for key in entity_section.wrong_type:
            anomalies.append({'kind': 'wrong_type', 'graph_key': key})
        for key in entity_section.generic_duplicate:
            anomalies.append({'kind': 'generic_duplicate', 'graph_key': key})
        for key in entity_section.typed_duplicate:
            anomalies.append({'kind': 'typed_duplicate', 'graph_key': key})
        for key in entity_section.uuid_mismatch:
            anomalies.append({'kind': 'uuid_mismatch', 'graph_key': key})
        for key in entity_section.missing_embedding:
            anomalies.append({'kind': 'missing_embedding', 'graph_key': key})
        for key in edge_section.duplicate_edge_key:
            anomalies.append({'kind': 'duplicate_edge_key', 'edge_key': key})
        for key in edge_section.edge_type_mismatch:
            anomalies.append({'kind': 'edge_type_mismatch', 'edge_key': key})
        for key in edge_section.endpoint_mismatch:
            anomalies.append({'kind': 'endpoint_mismatch', 'edge_key': key})
        for key in edge_section.uuid_mismatch:
            anomalies.append({'kind': 'uuid_mismatch', 'edge_key': key})
        for key in edge_section.missing_embedding:
            anomalies.append({'kind': 'missing_embedding', 'edge_key': key})

        missing_provenance: list[str] = []
        if request.require_provenance:
            target_uuids: list[str] = []
            for row in entity_rows:
                u = row.get('uuid')
                if u:
                    target_uuids.append(str(u))
            for row in edge_rows:
                u = row.get('uuid')
                if u:
                    target_uuids.append(str(u))
            # Also include expected deterministic UUIDs for missing targets
            for ent in request.entities:
                target_uuids.append(
                    catalog_entity_uuid(namespace, request.group_id, ent.entity_type, ent.graph_key)
                )
            for edge in request.edges:
                target_uuids.append(
                    catalog_edge_uuid(namespace, request.group_id, edge.edge_type, edge.edge_key)
                )
            # de-dupe preserve order
            seen_u: set[str] = set()
            uniq_targets: list[str] = []
            for u in target_uuids:
                if u not in seen_u:
                    seen_u.add(u)
                    uniq_targets.append(u)
            try:
                prov_rows = await self._store.match_provenance_presence(
                    client.driver,
                    group_id=request.group_id,
                    target_uuids=uniq_targets,
                )
            except Exception as exc:
                logger.error(
                    'catalog verify_catalog_batch provenance_read_failed batch_id=%s reason=%s',
                    request.batch_id,
                    type(exc).__name__,
                )
                return VerifyCatalogBatchResponse(
                    group_id=request.group_id,
                    batch_id=request.batch_id,
                    entities=entity_section,
                    edges=edge_section,
                    missing=missing,
                    anomalies=anomalies,
                    require_provenance=True,
                    error_code=CatalogErrorCode.internal_error,
                    error_message='verify provenance read failed',
                )
            present = {str(r.get('uuid')) for r in prov_rows if r.get('has_provenance')}
            for u in uniq_targets:
                if u not in present:
                    missing_provenance.append(u)

        logger.info(
            'catalog verify_catalog_batch batch_id=%s entities=%s edges=%s',
            request.batch_id,
            entity_section.found,
            edge_section.found,
        )
        return VerifyCatalogBatchResponse(
            group_id=request.group_id,
            batch_id=request.batch_id,
            entities=entity_section,
            edges=edge_section,
            missing=missing,
            anomalies=anomalies,
            require_provenance=request.require_provenance,
            missing_provenance=missing_provenance,
        )

    def _verify_entities(
        self,
        *,
        namespace: uuid.UUID,
        group_id: str,
        expected: list[Any],
        rows: list[dict[str, Any]],
    ) -> VerifyEntitySection:
        # batch_id scoping is enforced by store match_entities_for_verify.
        section = VerifyEntitySection(expected=len(expected))

        by_key: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = self._row_key(row)
            if key:
                by_key.setdefault(str(key), []).append(row)

        if expected:
            found_count = 0
            for ent in expected:
                matches = by_key.get(ent.graph_key, [])
                expected_uuid = catalog_entity_uuid(
                    namespace, group_id, ent.entity_type, ent.graph_key
                )
                if not matches:
                    section.missing.append(ent.graph_key)
                    continue
                typed = []
                generic = []
                wrong = []
                for row in matches:
                    labels = self._node_labels(row)
                    custom = self._custom_labels(labels)
                    if not custom:
                        generic.append(row)
                    elif set(custom) == {ent.entity_type}:
                        typed.append(row)
                    else:
                        wrong.append(row)
                if generic:
                    section.generic_duplicate.append(ent.graph_key)
                if wrong:
                    section.wrong_type.append(ent.graph_key)
                if len(typed) > 1:
                    section.typed_duplicate.append(ent.graph_key)
                if typed:
                    found_count += 1
                    if any(str(row.get('uuid')) != expected_uuid for row in typed):
                        section.uuid_mismatch.append(ent.graph_key)
                    if any(not row.get('has_name_embedding') for row in typed):
                        section.missing_embedding.append(ent.graph_key)
                elif wrong:
                    found_count += 1
                    if any(not row.get('has_name_embedding') for row in wrong):
                        section.missing_embedding.append(ent.graph_key)
                elif generic:
                    found_count += 1
                    if any(not row.get('has_name_embedding') for row in generic):
                        section.missing_embedding.append(ent.graph_key)
            section.found = found_count
        else:
            # batch-scoped only: report rows under batch without per-key expected list
            section.expected = len(rows)
            section.found = len(rows)
            for row in rows:
                key = self._row_key(row) or str(row.get('uuid') or '')
                labels = self._node_labels(row)
                custom = self._custom_labels(labels)
                if not custom and key:
                    section.generic_duplicate.append(str(key))
                if not row.get('has_name_embedding') and key:
                    section.missing_embedding.append(str(key))
        return section

    def _verify_edges(
        self,
        *,
        namespace: uuid.UUID,
        group_id: str,
        expected: list[Any],
        rows: list[dict[str, Any]],
    ) -> VerifyEdgeSection:
        # batch_id scoping is enforced by store match_edges_for_verify.
        section = VerifyEdgeSection(expected=len(expected))
        by_key: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = row.get('edge_key')
            if key:
                by_key.setdefault(str(key), []).append(row)

        if expected:
            found_count = 0
            for edge in expected:
                matches = by_key.get(edge.edge_key, [])
                expected_uuid = catalog_edge_uuid(
                    namespace, group_id, edge.edge_type, edge.edge_key
                )
                if not matches:
                    section.missing.append(edge.edge_key)
                    continue
                found_count += 1
                if len(matches) > 1:
                    section.duplicate_edge_key.append(edge.edge_key)
                if any(str(row.get('uuid')) != expected_uuid for row in matches):
                    section.uuid_mismatch.append(edge.edge_key)
                if any(
                    not (row.get('edge_type') or row.get('name'))
                    or (row.get('edge_type') or row.get('name')) != edge.edge_type
                    for row in matches
                ):
                    section.edge_type_mismatch.append(edge.edge_key)
                if any(
                    any(
                        expected is not None and str(row.get(actual_field)) != expected
                        for expected, actual_field in (
                            (edge.expected_source_uuid, 'source_uuid'),
                            (edge.expected_target_uuid, 'target_uuid'),
                        )
                    )
                    for row in matches
                ):
                    section.endpoint_mismatch.append(edge.edge_key)
                if any(not row.get('has_fact_embedding') for row in matches):
                    section.missing_embedding.append(edge.edge_key)
            section.found = found_count
        else:
            section.expected = len(rows)
            section.found = len(rows)
            seen_keys: dict[str, int] = {}
            for row in rows:
                key = str(row.get('edge_key') or row.get('uuid') or '')
                seen_keys[key] = seen_keys.get(key, 0) + 1
                if not row.get('has_fact_embedding') and key:
                    section.missing_embedding.append(key)
            for key, count in seen_keys.items():
                if count > 1 and key:
                    section.duplicate_edge_key.append(key)
        return section

    # ------------------------------------------------------------------
    # Typed edge upsert
    # ------------------------------------------------------------------

    def _edge_gate_errors(
        self,
        client: Any,
        request: UpsertTypedEdgesRequest,
    ) -> CatalogWriteResponse | None:
        n = len(request.edges)

        def _all_error(code: CatalogErrorCode, message: str) -> CatalogWriteResponse:
            results = [
                CatalogItemResult(
                    index=i,
                    status='error',
                    edge_key=request.edges[i].edge_key,
                    edge_type=request.edges[i].edge_type,
                    error_code=code,
                    error_message=message,
                )
                for i in range(n)
            ]
            return CatalogWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                dry_run=request.dry_run,
                atomic=request.atomic,
                results=results,
                failed=n,
            )

        if not self.catalog_config.enabled:
            return _all_error(
                CatalogErrorCode.feature_disabled,
                'catalog_upsert.enabled is false',
            )
        ns = self._namespace()
        if ns is None:
            return _all_error(
                CatalogErrorCode.invalid_uuid_namespace,
                'uuid_namespace missing or invalid',
            )
        provider = getattr(getattr(client, 'driver', None), 'provider', None)
        provider_val = getattr(provider, 'value', provider)
        if provider_val != 'neo4j':
            return _all_error(
                CatalogErrorCode.backend_unavailable,
                'catalog writes require Neo4j backend',
            )
        max_n = self.catalog_config.max_edges_per_batch
        if n > max_n:
            return _all_error(
                CatalogErrorCode.batch_limit_exceeded,
                f'edges exceed max_edges_per_batch ({max_n})',
            )
        return None

    async def upsert_typed_edges(
        self,
        *,
        client: Any,
        request: UpsertTypedEdgesRequest,
    ) -> CatalogWriteResponse:
        """Deterministic typed edge upsert (EDGE-01..11).

        Order: gate → identity/hash → resolve both endpoints → embed fact →
        open write tx (if not dry_run). Never creates/relabels endpoints.
        """
        gate = self._edge_gate_errors(client, request)
        if gate is not None:
            logger.info(
                'catalog upsert_typed_edges gated batch_id=%s count=%s failed=%s',
                request.batch_id,
                len(request.edges),
                gate.failed,
            )
            return gate

        namespace = self._namespace()
        assert namespace is not None

        request_ts = datetime.now(timezone.utc)
        prepared: list[_PreparedEdge] = []
        identity_to_prep: dict[str, _PreparedEdge] = {}
        identity_occurrences: dict[str, list[int]] = {}
        conflicted_edge_uuids: set[str] = set()
        early_errors: dict[int, CatalogItemResult] = {}

        # 1) topology preflight + identity + hash + coalesce (before resolve/embed/tx)
        for idx, item in enumerate(request.edges):
            try:
                validate_edge_endpoint_pair(
                    item.edge_type, item.source_entity_type, item.target_entity_type
                )
            except ValueError as exc:
                early_errors[idx] = CatalogItemResult(
                    index=idx,
                    status='error',
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=CatalogErrorCode.edge_endpoint_pair_not_allowed,
                    error_message=str(exc),
                )
                continue

            try:
                payload = self.edge_canonical_payload(item)
                digest = canonical_sha256(payload)
                assert_optional_client_hash(item.content_sha256, digest)
            except ValueError as exc:
                msg = str(exc)
                code = (
                    CatalogErrorCode.content_hash_mismatch
                    if 'content_hash_mismatch' in msg
                    else CatalogErrorCode.validation_error
                )
                early_errors[idx] = CatalogItemResult(
                    index=idx,
                    status='error',
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=code,
                    error_message=msg,
                )
                continue

            edge_uuid = catalog_edge_uuid(
                namespace, request.group_id, item.edge_type, item.edge_key
            )
            occurrences = identity_occurrences.setdefault(edge_uuid, [])
            occurrences.append(idx)
            if edge_uuid in conflicted_edge_uuids:
                early_errors[idx] = CatalogItemResult(
                    index=idx,
                    status='error',
                    uuid=edge_uuid,
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=CatalogErrorCode.deterministic_uuid_conflict,
                    error_message='same identity different canonical payload in request',
                )
                continue
            if edge_uuid in identity_to_prep:
                prior = identity_to_prep[edge_uuid]
                if prior.content_sha256 != digest:
                    conflicted_edge_uuids.add(edge_uuid)
                    for occurrence in occurrences:
                        occurrence_item = request.edges[occurrence]
                        early_errors[occurrence] = CatalogItemResult(
                            index=occurrence,
                            status='error',
                            uuid=edge_uuid,
                            edge_key=occurrence_item.edge_key,
                            edge_type=occurrence_item.edge_type,
                            error_code=CatalogErrorCode.deterministic_uuid_conflict,
                            error_message='same identity different canonical payload in request',
                        )
                    if prior in prepared:
                        prepared.remove(prior)
                    identity_to_prep.pop(edge_uuid, None)
                    continue
                prior.coalesced_indices.append(idx)
                continue

            prep = _PreparedEdge(
                index=idx,
                item=item,
                edge_uuid=edge_uuid,
                content_sha256=digest,
            )
            prepared.append(prep)
            identity_to_prep[edge_uuid] = prep

        if early_errors and request.atomic:
            return self._edge_atomic_fail_response(
                request, early_errors, trigger_indices=set(early_errors.keys())
            )

        # 2) resolve both endpoints BEFORE embedding (EDGE-03/05)
        # missing_endpoint is only a successful empty MATCH; DB exceptions are internal_error.
        # Prefer exact expected UUIDv5; never arbitrary-bind first typed row.
        driver = client.driver
        for prep in prepared:
            item = prep.item
            expected_src = catalog_entity_uuid(
                namespace,
                request.group_id,
                item.source_entity_type,
                item.source_graph_key,
            )
            expected_tgt = catalog_entity_uuid(
                namespace,
                request.group_id,
                item.target_entity_type,
                item.target_graph_key,
            )
            try:
                src_code, src_row = await self._store.resolve_endpoint_typed(
                    driver,
                    group_id=request.group_id,
                    graph_key=item.source_graph_key,
                    entity_type=item.source_entity_type,
                    expected_uuid=expected_src,
                )
            except Exception as exc:
                logger.error(
                    'catalog endpoint_resolve_failed batch_id=%s side=source reason=%s',
                    request.batch_id,
                    type(exc).__name__,
                )
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.internal_error
                prep.error_message = 'source endpoint pre-resolve failed'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    content_sha256=prep.content_sha256,
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=CatalogErrorCode.internal_error,
                    error_message=prep.error_message,
                    details={'reason': type(exc).__name__, 'side': 'source'},
                )
                continue
            if src_code is not None:
                code = self._endpoint_error_code(src_code)
                prep.projected_status = 'error'
                prep.error_code = code
                prep.error_message = f'source endpoint: {src_code}'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    content_sha256=prep.content_sha256,
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=code,
                    error_message=prep.error_message,
                )
                continue

            try:
                tgt_code, tgt_row = await self._store.resolve_endpoint_typed(
                    driver,
                    group_id=request.group_id,
                    graph_key=item.target_graph_key,
                    entity_type=item.target_entity_type,
                    expected_uuid=expected_tgt,
                )
            except Exception as exc:
                logger.error(
                    'catalog endpoint_resolve_failed batch_id=%s side=target reason=%s',
                    request.batch_id,
                    type(exc).__name__,
                )
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.internal_error
                prep.error_message = 'target endpoint pre-resolve failed'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    content_sha256=prep.content_sha256,
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=CatalogErrorCode.internal_error,
                    error_message=prep.error_message,
                    details={'reason': type(exc).__name__, 'side': 'target'},
                )
                continue
            if tgt_code is not None:
                code = self._endpoint_error_code(tgt_code)
                prep.projected_status = 'error'
                prep.error_code = code
                prep.error_message = f'target endpoint: {tgt_code}'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    content_sha256=prep.content_sha256,
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=code,
                    error_message=prep.error_message,
                )
                continue

            assert src_row is not None and tgt_row is not None
            src_uuid = str(src_row['uuid'])
            tgt_uuid = str(tgt_row['uuid'])
            if src_uuid != expected_src:
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.deterministic_uuid_conflict
                prep.error_message = 'source endpoint uuid does not match deterministic identity'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    content_sha256=prep.content_sha256,
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=prep.error_code,
                    error_message=prep.error_message,
                )
                continue
            if tgt_uuid != expected_tgt:
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.deterministic_uuid_conflict
                prep.error_message = 'target endpoint uuid does not match deterministic identity'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    content_sha256=prep.content_sha256,
                    edge_key=item.edge_key,
                    edge_type=item.edge_type,
                    error_code=prep.error_code,
                    error_message=prep.error_message,
                )
                continue
            prep.source_uuid = src_uuid
            prep.target_uuid = tgt_uuid

        # 3) load existing for conflict / unchanged
        for prep in prepared:
            if prep.projected_status == 'error':
                continue
            try:
                existing = await self._store.get_edge_by_uuid(
                    driver,
                    uuid=prep.edge_uuid,
                    group_id=request.group_id,
                )
            except Exception as exc:
                # Fail closed: DB read failure is not "absent".
                logger.error(
                    'catalog edge_pre_read_failed batch_id=%s reason=%s',
                    request.batch_id,
                    type(exc).__name__,
                )
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.internal_error
                prep.error_message = 'edge pre-read failed'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    content_sha256=prep.content_sha256,
                    edge_key=prep.item.edge_key,
                    edge_type=prep.item.edge_type,
                    error_code=prep.error_code,
                    error_message=prep.error_message,
                    details={'reason': type(exc).__name__},
                )
                continue
            prep.existing = existing
            if existing is None:
                prep.projected_status = 'created'
                continue
            conflict = self._store.detect_edge_identity_conflict(
                existing,
                edge_type=prep.item.edge_type,
                edge_key=prep.item.edge_key,
                source_uuid=prep.source_uuid or '',
                target_uuid=prep.target_uuid or '',
            )
            if conflict:
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.edge_identity_conflict
                prep.error_message = 'edge uuid exists with conflicting type/key/source/target'
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    content_sha256=prep.content_sha256,
                    edge_key=prep.item.edge_key,
                    edge_type=prep.item.edge_type,
                    error_code=prep.error_code,
                    error_message=prep.error_message,
                )
                continue
            if existing.get('content_sha256') == prep.content_sha256:
                prep.projected_status = 'unchanged'
            else:
                prep.projected_status = 'updated'

        write_set = [p for p in prepared if p.projected_status != 'error']
        conflicted = [p for p in prepared if p.projected_status == 'error']

        if conflicted and request.atomic:
            for p in conflicted:
                if p.index not in early_errors:
                    early_errors[p.index] = CatalogItemResult(
                        index=p.index,
                        status='error',
                        uuid=p.edge_uuid,
                        content_sha256=p.content_sha256,
                        edge_key=p.item.edge_key,
                        edge_type=p.item.edge_type,
                        error_code=p.error_code,
                        error_message=p.error_message,
                    )
            return self._edge_atomic_fail_response(
                request,
                early_errors,
                trigger_indices={p.index for p in conflicted} | set(early_errors.keys()),
            )

        # 4) embed fact for non-unchanged (including dry-run readiness) AFTER endpoints
        embed_targets = [p for p in write_set if p.projected_status != 'unchanged']
        embedder = client.embedder
        try:
            for prep in embed_targets:
                text = prep.item.fact.replace('\n', ' ')
                prep.fact_embedding = await embedder.create(input_data=[text])
        except Exception as exc:
            logger.error(
                'catalog embedding_failed batch_id=%s count=%s',
                request.batch_id,
                len(embed_targets),
            )
            err_results = []
            for i, item in enumerate(request.edges):
                if i in early_errors:
                    err_results.append(early_errors[i])
                else:
                    err_results.append(
                        CatalogItemResult(
                            index=i,
                            status='error',
                            edge_key=item.edge_key,
                            edge_type=item.edge_type,
                            error_code=CatalogErrorCode.embedding_failed,
                            error_message='embedding generation failed',
                            details={'reason': type(exc).__name__},
                        )
                    )
            return CatalogWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                dry_run=request.dry_run,
                atomic=request.atomic,
                results=sorted(err_results, key=lambda r: r.index),
                failed=len(err_results),
            )

        # 5) dry-run: no transaction, no batch_id persistence, no schema init
        if request.dry_run:
            results = self._build_edge_results(request, write_set, early_errors, written={})
            resp = self._count_edge_response(request, results)
            logger.info(
                'catalog upsert_typed_edges dry_run batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
                request.batch_id,
                len(request.edges),
                resp.created,
                resp.updated,
                resp.unchanged,
                resp.failed,
            )
            return resp

        # 6) schema ensure only for real writes (never dry-run / embed failure path)
        try:
            await self._ensure_schema(client)
        except CatalogStoreError as exc:
            return self._schema_fail_edge_response(request, reason=type(exc).__name__)
        except Exception as exc:
            return self._schema_fail_edge_response(request, reason=type(exc).__name__)

        # 7) write
        if request.atomic:
            return await self._write_edges_atomic(
                client, request, write_set, early_errors, request_ts
            )
        return await self._write_edges_per_item(
            client, request, write_set, early_errors, request_ts
        )

    @staticmethod
    def _endpoint_error_code(code: str) -> CatalogErrorCode:
        mapping = {
            'missing_endpoint': CatalogErrorCode.missing_endpoint,
            'endpoint_type_mismatch': CatalogErrorCode.endpoint_type_mismatch,
            'generic_endpoint_conflict': CatalogErrorCode.generic_endpoint_conflict,
            'typed_endpoint_duplicate': CatalogErrorCode.deterministic_uuid_conflict,
            'deterministic_uuid_conflict': CatalogErrorCode.deterministic_uuid_conflict,
            'internal_error': CatalogErrorCode.internal_error,
        }
        # Unknown classify codes are internal defects, not absent endpoints.
        return mapping.get(code, CatalogErrorCode.internal_error)

    def _edge_params_for(
        self,
        prep: _PreparedEdge,
        request: UpsertTypedEdgesRequest,
        request_ts: datetime,
    ) -> dict[str, Any]:
        item = prep.item
        # Fail closed: typed non-unchanged writes must never send empty vectors.
        if not prep.fact_embedding:
            raise CatalogStoreError(
                'fact_embedding missing for non-unchanged edge',
                code='embedding_failed',
            )
        embedding = list(prep.fact_embedding)
        return self._store.prepare_edge_params(
            edge_type=item.edge_type,
            uuid=prep.edge_uuid,
            group_id=request.group_id,
            batch_id=request.batch_id,
            edge_key=item.edge_key,
            source_uuid=prep.source_uuid or '',
            target_uuid=prep.target_uuid or '',
            fact=item.fact,
            evidence=item.evidence,
            content_sha256=prep.content_sha256,
            created_at=request_ts,
            updated_at=request_ts,
            fact_embedding=embedding,
            attributes=item.attributes,
            confidence=item.confidence,
        )

    def _edge_success_result(
        self,
        prep: _PreparedEdge,
        status: str,
        *,
        index: int | None = None,
    ) -> CatalogItemResult:
        return CatalogItemResult(
            index=prep.index if index is None else index,
            status=status,  # type: ignore[arg-type]
            uuid=prep.edge_uuid,
            content_sha256=prep.content_sha256,
            edge_key=prep.item.edge_key,
            edge_type=prep.item.edge_type,
        )

    def _build_edge_results(
        self,
        request: UpsertTypedEdgesRequest,
        write_set: list[_PreparedEdge],
        early_errors: dict[int, CatalogItemResult],
        written: dict[int, CatalogItemResult],
    ) -> list[CatalogItemResult]:
        by_index: dict[int, CatalogItemResult] = dict(early_errors)
        by_index.update(written)
        for prep in write_set:
            if prep.index not in by_index:
                by_index[prep.index] = self._edge_success_result(prep, prep.projected_status)
            for ci in prep.coalesced_indices:
                if ci not in by_index:
                    by_index[ci] = self._edge_success_result(prep, prep.projected_status, index=ci)
        results: list[CatalogItemResult] = []
        for i, item in enumerate(request.edges):
            if i in by_index:
                results.append(by_index[i])
            else:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='error',
                        edge_key=item.edge_key,
                        edge_type=item.edge_type,
                        error_code=CatalogErrorCode.internal_error,
                        error_message='missing result',
                    )
                )
        return sorted(results, key=lambda r: r.index)

    def _count_edge_response(
        self,
        request: UpsertTypedEdgesRequest,
        results: list[CatalogItemResult],
    ) -> CatalogWriteResponse:
        created = sum(1 for r in results if r.status == 'created')
        updated = sum(1 for r in results if r.status == 'updated')
        unchanged = sum(1 for r in results if r.status == 'unchanged')
        failed = sum(1 for r in results if r.status == 'error')
        rolled_back = sum(1 for r in results if r.status == 'rolled_back')
        return CatalogWriteResponse(
            group_id=request.group_id,
            batch_id=request.batch_id,
            dry_run=request.dry_run,
            atomic=request.atomic,
            results=results,
            created=created,
            updated=updated,
            unchanged=unchanged,
            failed=failed,
            rolled_back=rolled_back,
        )

    def _edge_atomic_fail_response(
        self,
        request: UpsertTypedEdgesRequest,
        early_errors: dict[int, CatalogItemResult],
        trigger_indices: set[int],
    ) -> CatalogWriteResponse:
        results: list[CatalogItemResult] = []
        for i, item in enumerate(request.edges):
            if i in early_errors:
                results.append(early_errors[i])
            elif i in trigger_indices:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='error',
                        edge_key=item.edge_key,
                        edge_type=item.edge_type,
                        error_code=CatalogErrorCode.neo4j_transaction_failed,
                        error_message='neo4j transaction failed',
                    )
                )
            else:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='rolled_back',
                        edge_key=item.edge_key,
                        edge_type=item.edge_type,
                        error_code=CatalogErrorCode.batch_conflict,
                        error_message='rolled back due to sibling failure',
                    )
                )
        results = sorted(results, key=lambda r: r.index)
        resp = self._count_edge_response(request, results)
        logger.info(
            'catalog upsert_typed_edges atomic_fail batch_id=%s count=%s failed=%s rolled_back=%s',
            request.batch_id,
            len(request.edges),
            resp.failed,
            resp.rolled_back,
        )
        return resp

    async def _recheck_edge_endpoints_in_tx(
        self,
        tx: Any,
        prep: _PreparedEdge,
        request: UpsertTypedEdgesRequest,
    ) -> CatalogErrorCode | None:
        """Re-resolve endpoints + edge identity inside the write tx; never create/relabel.

        Returns structured endpoint/identity error code on race, else None.
        """
        item = prep.item
        namespace = self._namespace()
        expected_src = (
            catalog_entity_uuid(
                namespace,
                request.group_id,
                item.source_entity_type,
                item.source_graph_key,
            )
            if namespace is not None
            else prep.source_uuid
        )
        expected_tgt = (
            catalog_entity_uuid(
                namespace,
                request.group_id,
                item.target_entity_type,
                item.target_graph_key,
            )
            if namespace is not None
            else prep.target_uuid
        )
        src_code, src_row = await self._store.resolve_endpoint_typed(
            None,
            group_id=request.group_id,
            graph_key=item.source_graph_key,
            entity_type=item.source_entity_type,
            tx=tx,
            expected_uuid=expected_src,
        )
        if src_code is not None:
            return self._endpoint_error_code(src_code)
        tgt_code, tgt_row = await self._store.resolve_endpoint_typed(
            None,
            group_id=request.group_id,
            graph_key=item.target_graph_key,
            entity_type=item.target_entity_type,
            tx=tx,
            expected_uuid=expected_tgt,
        )
        if tgt_code is not None:
            return self._endpoint_error_code(tgt_code)
        assert src_row is not None and tgt_row is not None
        src_uuid = str(src_row['uuid'])
        tgt_uuid = str(tgt_row['uuid'])
        if prep.source_uuid and src_uuid != prep.source_uuid:
            return CatalogErrorCode.missing_endpoint
        if prep.target_uuid and tgt_uuid != prep.target_uuid:
            return CatalogErrorCode.missing_endpoint
        if expected_src and src_uuid != expected_src:
            return CatalogErrorCode.deterministic_uuid_conflict
        if expected_tgt and tgt_uuid != expected_tgt:
            return CatalogErrorCode.deterministic_uuid_conflict
        prep.source_uuid = src_uuid
        prep.target_uuid = tgt_uuid
        # Transaction-local identity invariant for existing edge uuid.
        try:
            existing = await self._store.get_edge_by_uuid(
                None,
                uuid=prep.edge_uuid,
                group_id=request.group_id,
                tx=tx,
            )
        except Exception as exc:
            logger.error(
                'catalog edge_in_tx_recheck_failed batch_id=%s reason=%s',
                request.batch_id,
                type(exc).__name__,
            )
            return CatalogErrorCode.internal_error
        if existing is not None:
            conflict = self._store.detect_edge_identity_conflict(
                existing,
                edge_type=item.edge_type,
                edge_key=item.edge_key,
                source_uuid=src_uuid,
                target_uuid=tgt_uuid,
            )
            if conflict:
                return CatalogErrorCode.edge_identity_conflict
        return None

    class _EdgeEndpointRace(Exception):
        """Internal signal: endpoint race inside write transaction."""

        def __init__(self, code: CatalogErrorCode):
            self.code = code
            super().__init__(code.value)

    async def _write_edges_atomic(
        self,
        client: Any,
        request: UpsertTypedEdgesRequest,
        write_set: list[_PreparedEdge],
        early_errors: dict[int, CatalogItemResult],
        request_ts: datetime,
    ) -> CatalogWriteResponse:
        written: dict[int, CatalogItemResult] = {}
        to_write = [p for p in write_set if p.projected_status != 'unchanged']
        unchanged = [p for p in write_set if p.projected_status == 'unchanged']
        for p in unchanged:
            written[p.index] = self._edge_success_result(p, 'unchanged')
            for ci in p.coalesced_indices:
                written[ci] = self._edge_success_result(p, 'unchanged', index=ci)

        if not to_write:
            results = self._build_edge_results(request, write_set, early_errors, written)
            resp = self._count_edge_response(request, results)
            logger.info(
                'catalog upsert_typed_edges batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
                request.batch_id,
                len(request.edges),
                resp.created,
                resp.updated,
                resp.unchanged,
                resp.failed,
            )
            return resp

        current_prep: _PreparedEdge | None = None
        try:
            async with client.driver.transaction() as tx:
                for prep in to_write:
                    current_prep = prep
                    ep_err = await self._recheck_edge_endpoints_in_tx(tx, prep, request)
                    if ep_err is not None:
                        raise self._EdgeEndpointRace(ep_err)
                    params = self._edge_params_for(prep, request, request_ts)
                    row = await self._store.upsert_edge_item(tx, params=params)
                    if not row or not row.get('uuid'):
                        raise RuntimeError('edge upsert empty row')
                    self._raise_edge_row_error(row)
                    status = self._write_status_from_row(row, prep.projected_status)
                    if status == 'error':
                        raise self._EdgeEndpointRace(
                            self._row_error_code(row) or CatalogErrorCode.internal_error
                        )
                    result = CatalogItemResult(
                        index=prep.index,
                        status=status,  # type: ignore[arg-type]
                        uuid=prep.edge_uuid,
                        content_sha256=prep.content_sha256,
                        edge_key=prep.item.edge_key,
                        edge_type=prep.item.edge_type,
                    )
                    written[prep.index] = result
                    for ci in prep.coalesced_indices:
                        written[ci] = CatalogItemResult(
                            index=ci,
                            status=status,  # type: ignore[arg-type]
                            uuid=prep.edge_uuid,
                            content_sha256=prep.content_sha256,
                            edge_key=request.edges[ci].edge_key,
                            edge_type=request.edges[ci].edge_type,
                        )
        except CatalogStoreError as exc:
            mapped = self._map_store_error_code(exc)
            trigger = current_prep or (to_write[0] if to_write else None)
            trigger_idx = trigger.index if trigger is not None else 0
            early_errors[trigger_idx] = CatalogItemResult(
                index=trigger_idx,
                status='error',
                uuid=trigger.edge_uuid if trigger is not None else None,
                edge_key=trigger.item.edge_key if trigger is not None else None,
                edge_type=trigger.item.edge_type if trigger is not None else None,
                error_code=mapped,
                error_message=(
                    'embedding generation failed'
                    if mapped == CatalogErrorCode.embedding_failed
                    else str(exc) or mapped.value
                ),
            )
            return self._edge_atomic_fail_response(
                request, early_errors, trigger_indices={trigger_idx}
            )
        except self._EdgeEndpointRace as exc:
            trigger = current_prep or (to_write[0] if to_write else None)
            trigger_idx = trigger.index if trigger is not None else 0
            early_errors[trigger_idx] = CatalogItemResult(
                index=trigger_idx,
                status='error',
                uuid=trigger.edge_uuid if trigger is not None else None,
                edge_key=trigger.item.edge_key if trigger is not None else None,
                edge_type=trigger.item.edge_type if trigger is not None else None,
                error_code=exc.code,
                error_message=f'endpoint race in write transaction: {exc.code.value}',
            )
            return self._edge_atomic_fail_response(
                request, early_errors, trigger_indices={trigger_idx}
            )
        except Exception as exc:
            logger.error(
                'catalog neo4j_transaction_failed batch_id=%s count=%s',
                request.batch_id,
                len(to_write),
            )
            trigger = current_prep or (to_write[0] if to_write else None)
            trigger_idx = trigger.index if trigger is not None else 0
            early_errors[trigger_idx] = CatalogItemResult(
                index=trigger_idx,
                status='error',
                uuid=trigger.edge_uuid if trigger is not None else None,
                edge_key=trigger.item.edge_key if trigger is not None else None,
                edge_type=trigger.item.edge_type if trigger is not None else None,
                error_code=CatalogErrorCode.neo4j_transaction_failed,
                error_message='neo4j transaction failed',
                details={'reason': type(exc).__name__},
            )
            return self._edge_atomic_fail_response(
                request, early_errors, trigger_indices={trigger_idx}
            )

        results = self._build_edge_results(request, write_set, early_errors, written)
        resp = self._count_edge_response(request, results)
        logger.info(
            'catalog upsert_typed_edges batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
            request.batch_id,
            len(request.edges),
            resp.created,
            resp.updated,
            resp.unchanged,
            resp.failed,
        )
        return resp

    async def _write_edges_per_item(
        self,
        client: Any,
        request: UpsertTypedEdgesRequest,
        write_set: list[_PreparedEdge],
        early_errors: dict[int, CatalogItemResult],
        request_ts: datetime,
    ) -> CatalogWriteResponse:
        written: dict[int, CatalogItemResult] = {}
        for prep in write_set:
            if prep.projected_status == 'unchanged':
                written[prep.index] = self._edge_success_result(prep, 'unchanged')
                for ci in prep.coalesced_indices:
                    written[ci] = self._edge_success_result(prep, 'unchanged', index=ci)
                continue
            try:
                async with client.driver.transaction() as tx:
                    ep_err = await self._recheck_edge_endpoints_in_tx(tx, prep, request)
                    if ep_err is not None:
                        written[prep.index] = CatalogItemResult(
                            index=prep.index,
                            status='error',
                            uuid=prep.edge_uuid,
                            edge_key=prep.item.edge_key,
                            edge_type=prep.item.edge_type,
                            error_code=ep_err,
                            error_message=f'endpoint race in write transaction: {ep_err.value}',
                        )
                        for ci in prep.coalesced_indices:
                            written[ci] = CatalogItemResult(
                                index=ci,
                                status='error',
                                uuid=prep.edge_uuid,
                                edge_key=request.edges[ci].edge_key,
                                edge_type=request.edges[ci].edge_type,
                                error_code=ep_err,
                                error_message=f'endpoint race in write transaction: {ep_err.value}',
                            )
                        continue
                    params = self._edge_params_for(prep, request, request_ts)
                    row = await self._store.upsert_edge_item(tx, params=params)
                    if not row or not row.get('uuid'):
                        raise RuntimeError('edge upsert empty row')
                    self._raise_edge_row_error(row)
                    status = self._write_status_from_row(row, prep.projected_status)
                    if status == 'error':
                        raise self._EdgeEndpointRace(
                            self._row_error_code(row) or CatalogErrorCode.internal_error
                        )
                    written[prep.index] = CatalogItemResult(
                        index=prep.index,
                        status=status,  # type: ignore[arg-type]
                        uuid=prep.edge_uuid,
                        content_sha256=prep.content_sha256,
                        edge_key=prep.item.edge_key,
                        edge_type=prep.item.edge_type,
                    )
                    for ci in prep.coalesced_indices:
                        written[ci] = CatalogItemResult(
                            index=ci,
                            status=status,  # type: ignore[arg-type]
                            uuid=prep.edge_uuid,
                            content_sha256=prep.content_sha256,
                            edge_key=request.edges[ci].edge_key,
                            edge_type=request.edges[ci].edge_type,
                        )
            except CatalogStoreError as exc:
                mapped = self._map_store_error_code(exc)
                message = (
                    'embedding generation failed'
                    if mapped == CatalogErrorCode.embedding_failed
                    else str(exc) or mapped.value
                )
                written[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    edge_key=prep.item.edge_key,
                    edge_type=prep.item.edge_type,
                    error_code=mapped,
                    error_message=message,
                )
                for ci in prep.coalesced_indices:
                    written[ci] = CatalogItemResult(
                        index=ci,
                        status='error',
                        uuid=prep.edge_uuid,
                        edge_key=request.edges[ci].edge_key,
                        edge_type=request.edges[ci].edge_type,
                        error_code=mapped,
                        error_message=message,
                    )
                continue
            except self._EdgeEndpointRace as exc:
                written[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    edge_key=prep.item.edge_key,
                    edge_type=prep.item.edge_type,
                    error_code=exc.code,
                    error_message=f'endpoint race in write transaction: {exc.code.value}',
                )
                for ci in prep.coalesced_indices:
                    written[ci] = CatalogItemResult(
                        index=ci,
                        status='error',
                        uuid=prep.edge_uuid,
                        edge_key=request.edges[ci].edge_key,
                        edge_type=request.edges[ci].edge_type,
                        error_code=exc.code,
                        error_message=f'endpoint race in write transaction: {exc.code.value}',
                    )
            except Exception as exc:
                logger.error(
                    'catalog neo4j_transaction_failed batch_id=%s index=%s',
                    request.batch_id,
                    prep.index,
                )
                written[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.edge_uuid,
                    edge_key=prep.item.edge_key,
                    edge_type=prep.item.edge_type,
                    error_code=CatalogErrorCode.neo4j_transaction_failed,
                    error_message='neo4j transaction failed',
                    details={'reason': type(exc).__name__},
                )
                for ci in prep.coalesced_indices:
                    written[ci] = CatalogItemResult(
                        index=ci,
                        status='error',
                        uuid=prep.edge_uuid,
                        edge_key=request.edges[ci].edge_key,
                        edge_type=request.edges[ci].edge_type,
                        error_code=CatalogErrorCode.neo4j_transaction_failed,
                        error_message='neo4j transaction failed',
                    )

        results = self._build_edge_results(request, write_set, early_errors, written)
        resp = self._count_edge_response(request, results)
        logger.info(
            'catalog upsert_typed_edges batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
            request.batch_id,
            len(request.edges),
            resp.created,
            resp.updated,
            resp.unchanged,
            resp.failed,
        )
        return resp

    # ------------------------------------------------------------------
    # Provenance (PROV-01, PROV-03..06) — no add_episode / LLM / queue / embed
    # ------------------------------------------------------------------

    @staticmethod
    def source_canonical_payload(item: CatalogSourceItem) -> dict[str, Any]:
        """Mutable canonical fields for source content_sha256 (identity excluded)."""
        return pure_source_canonical_payload(item)

    def _provenance_gate_errors(
        self,
        client: Any,
        request: UpsertProvenanceRequest,
    ) -> CatalogWriteResponse | None:
        n = len(request.sources)

        def _all_error(code: CatalogErrorCode, message: str) -> CatalogWriteResponse:
            results = [
                CatalogItemResult(
                    index=i,
                    status='error',
                    graph_key=request.sources[i].source_key,
                    error_code=code,
                    error_message=message,
                )
                for i in range(n)
            ]
            return CatalogWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                dry_run=request.dry_run,
                atomic=request.atomic,
                results=results,
                failed=n,
            )

        if not self.catalog_config.enabled:
            return _all_error(
                CatalogErrorCode.feature_disabled,
                'catalog_upsert.enabled is false',
            )
        ns = self._namespace()
        if ns is None:
            return _all_error(
                CatalogErrorCode.invalid_uuid_namespace,
                'uuid_namespace missing or invalid',
            )
        provider = getattr(getattr(client, 'driver', None), 'provider', None)
        provider_val = getattr(provider, 'value', provider)
        if provider_val != 'neo4j':
            return _all_error(
                CatalogErrorCode.backend_unavailable,
                'catalog writes require Neo4j backend',
            )
        link_n = len(request.sources) * (len(request.entity_targets) + len(request.edge_targets))
        max_links = self.catalog_config.max_provenance_links_per_batch
        if link_n > max_links:
            return _all_error(
                CatalogErrorCode.batch_limit_exceeded,
                f'provenance links exceed max_provenance_links_per_batch ({max_links})',
            )
        return None

    def _provenance_atomic_fail_response(
        self,
        request: UpsertProvenanceRequest,
        early_errors: dict[int, CatalogItemResult],
        trigger_indices: set[int],
    ) -> CatalogWriteResponse:
        results: list[CatalogItemResult] = []
        for i, item in enumerate(request.sources):
            if i in early_errors:
                results.append(early_errors[i])
            elif i in trigger_indices:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='error',
                        graph_key=item.source_key,
                        error_code=CatalogErrorCode.neo4j_transaction_failed,
                        error_message='neo4j transaction failed',
                    )
                )
            else:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='rolled_back',
                        graph_key=item.source_key,
                        error_code=CatalogErrorCode.batch_conflict,
                        error_message='rolled back due to sibling failure',
                    )
                )
        results = sorted(results, key=lambda r: r.index)
        resp = self._count_provenance_response(request, results)
        logger.info(
            'catalog upsert_provenance atomic_fail batch_id=%s count=%s failed=%s rolled_back=%s',
            request.batch_id,
            len(request.sources),
            resp.failed,
            resp.rolled_back,
        )
        return resp

    def _count_provenance_response(
        self,
        request: UpsertProvenanceRequest,
        results: list[CatalogItemResult],
    ) -> CatalogWriteResponse:
        created = sum(1 for r in results if r.status == 'created')
        updated = sum(1 for r in results if r.status == 'updated')
        unchanged = sum(1 for r in results if r.status == 'unchanged')
        failed = sum(1 for r in results if r.status == 'error')
        rolled_back = sum(1 for r in results if r.status == 'rolled_back')
        return CatalogWriteResponse(
            group_id=request.group_id,
            batch_id=request.batch_id,
            dry_run=request.dry_run,
            atomic=request.atomic,
            results=results,
            created=created,
            updated=updated,
            unchanged=unchanged,
            failed=failed,
            rolled_back=rolled_back,
        )

    @staticmethod
    def _parse_source_valid_at(reference_time: str) -> datetime:
        """Parse ISO-8601 reference_time to UTC datetime."""
        normalized = reference_time.strip()
        if normalized.endswith('Z') or normalized.endswith('z'):
            normalized = normalized[:-1] + '+00:00'
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _source_conflict_result(
        index: int,
        item: CatalogSourceItem,
        source_uuid: str,
        content_sha256: str,
        *,
        batch: bool = False,
    ) -> CatalogItemResult:
        return CatalogItemResult(
            index=index,
            status='error',
            uuid=source_uuid,
            content_sha256=content_sha256,
            graph_key=item.source_key,
            error_code=CatalogErrorCode.deterministic_uuid_conflict,
            error_message='same identity different canonical payload in request',
            details={'kind': 'provenance'} if batch else None,
        )

    @staticmethod
    def _source_result(
        prep: _PreparedSource,
        index: int,
        status: str | None = None,
        *,
        batch: bool = False,
        offset: int = 0,
    ) -> CatalogItemResult:
        return CatalogItemResult(
            index=offset + index,
            status=(status or prep.projected_status),  # type: ignore[arg-type]
            uuid=prep.source_uuid,
            content_sha256=prep.content_sha256,
            graph_key=prep.item.source_key,
            details={'kind': 'provenance'} if batch else None,
        )

    async def _lock_and_recheck_provenance_targets(
        self,
        tx: Any,
        prep: _PreparedSource,
        *,
        group_id: str,
        created_targets: set[tuple[str, str]] | None = None,
    ) -> None:
        rows = await self._store.lock_provenance_targets(
            tx,
            group_id=group_id,
            entity_uuids=prep.entity_uuids,
            edge_uuids=prep.edge_uuids,
        )
        by_target = {(str(row.get('kind')), str(row.get('uuid'))): row for row in rows}
        created_targets = created_targets or set()
        for entity_uuid in prep.entity_uuids:
            row = by_target.get(('entity', entity_uuid))
            if row is None and ('entity', entity_uuid) in created_targets:
                continue
            if row is None or 'Entity' not in (row.get('labels') or []):
                raise self._ProvenanceInvariantRace(CatalogErrorCode.provenance_target_missing)
        for edge_uuid in prep.edge_uuids:
            row = by_target.get(('edge', edge_uuid))
            if row is None and ('edge', edge_uuid) in created_targets:
                continue
            if row is None:
                raise self._ProvenanceInvariantRace(CatalogErrorCode.provenance_target_missing)
            if prep.links_checked:
                linked = prep.source_uuid in (row.get('episodes') or [])
                if linked != (edge_uuid in prep.existing_edge_links):
                    raise self._ProvenanceInvariantRace(CatalogErrorCode.batch_conflict)

        if prep.links_checked:
            for entity_uuid, mentions_uuid in zip(
                prep.entity_uuids, prep.mentions_uuids, strict=True
            ):
                link = await self._store.get_mentions_link(
                    None,
                    episode_uuid=prep.source_uuid,
                    entity_uuid=entity_uuid,
                    mentions_uuid=mentions_uuid,
                    group_id=group_id,
                    tx=tx,
                )
                if (link is not None) != (mentions_uuid in prep.existing_mentions):
                    raise self._ProvenanceInvariantRace(CatalogErrorCode.batch_conflict)

    @staticmethod
    def _source_expected_state(prep: _PreparedSource) -> tuple[bool, str | None, str | None]:
        return (
            prep.existing is not None,
            prep.existing.get('source_key') if prep.existing is not None else None,
            prep.existing.get('content_sha256') if prep.existing is not None else None,
        )

    @staticmethod
    def _source_cas_matches_concurrent_identical(
        prep: _PreparedSource, row: dict[str, Any]
    ) -> bool:
        return (
            prep.existing is None
            and row.get('error_code') == CatalogErrorCode.batch_conflict.value
            and row.get('source_key') == prep.item.source_key
            and row.get('content_sha256') == prep.content_sha256
        )

    def _raise_source_cas_error(self, row: dict[str, Any]) -> None:
        error_code = row.get('error_code')
        if error_code is None:
            return
        code = (
            CatalogErrorCode.deterministic_uuid_conflict
            if error_code == CatalogErrorCode.deterministic_uuid_conflict.value
            else CatalogErrorCode.batch_conflict
        )
        raise self._ProvenanceInvariantRace(code)

    class _ProvenanceInvariantRace(Exception):
        def __init__(self, code: CatalogErrorCode):
            self.code = code
            super().__init__(code.value)

    async def upsert_provenance(
        self,
        *,
        client: Any,
        request: UpsertProvenanceRequest,
    ) -> CatalogWriteResponse:
        """Deterministic provenance upsert (PROV-01, PROV-03..06).

        Order: gate → identity/hash → resolve all targets → dry_run or single tx
        (sources + MENTIONS + edge episode append). No embedder, LLM, queue, add_episode.
        """
        _ = self._queue_service
        gate = self._provenance_gate_errors(client, request)
        if gate is not None:
            logger.info(
                'catalog upsert_provenance gated batch_id=%s count=%s failed=%s',
                request.batch_id,
                len(request.sources),
                gate.failed,
            )
            return gate

        namespace = self._namespace()
        assert namespace is not None
        request_ts = datetime.now(timezone.utc)
        prepared: list[_PreparedSource] = []
        prepared_by_uuid: dict[str, _PreparedSource] = {}
        source_occurrences: dict[str, list[int]] = {}
        conflicted_source_uuids: set[str] = set()
        early_errors: dict[int, CatalogItemResult] = {}
        driver = client.driver

        for idx, item in enumerate(request.sources):
            try:
                payload = self.source_canonical_payload(item)
                digest = canonical_sha256(payload)
                assert_optional_client_hash(item.content_sha256, digest)
            except ValueError as exc:
                msg = str(exc)
                code = (
                    CatalogErrorCode.content_hash_mismatch
                    if 'content_hash_mismatch' in msg
                    else CatalogErrorCode.validation_error
                )
                early_errors[idx] = CatalogItemResult(
                    index=idx,
                    status='error',
                    graph_key=item.source_key,
                    error_code=code,
                    error_message=msg,
                )
                continue
            try:
                valid_at = self._parse_source_valid_at(item.reference_time)
            except ValueError:
                # Defense-in-depth: model boundary should already reject malformed times.
                early_errors[idx] = CatalogItemResult(
                    index=idx,
                    status='error',
                    graph_key=item.source_key,
                    error_code=CatalogErrorCode.validation_error,
                    error_message='reference_time must be a valid ISO-8601 timestamp',
                )
                continue

            source_uuid = catalog_source_uuid(namespace, request.group_id, item.source_key)
            content_json = json.dumps(
                {
                    'source_key': item.source_key,
                    'reference_time': item.reference_time,
                    'attributes': item.attributes,
                    'metadata': item.metadata,
                },
                sort_keys=True,
                separators=(',', ':'),
                ensure_ascii=False,
            )
            occurrences = source_occurrences.setdefault(source_uuid, [])
            occurrences.append(idx)
            prior = prepared_by_uuid.get(source_uuid)
            if source_uuid in conflicted_source_uuids:
                early_errors[idx] = self._source_conflict_result(idx, item, source_uuid, digest)
                continue
            if prior is not None:
                if prior.content_sha256 == digest:
                    prior.coalesced_indices.append(idx)
                    continue
                conflicted_source_uuids.add(source_uuid)
                if prior in prepared:
                    prepared.remove(prior)
                prepared_by_uuid.pop(source_uuid, None)
                for occurrence in occurrences:
                    occurrence_item = request.sources[occurrence]
                    occurrence_digest = canonical_sha256(
                        self.source_canonical_payload(occurrence_item)
                    )
                    early_errors[occurrence] = self._source_conflict_result(
                        occurrence, occurrence_item, source_uuid, occurrence_digest
                    )
                continue
            prep = _PreparedSource(
                index=idx,
                item=item,
                source_uuid=source_uuid,
                content_sha256=digest,
                content_json=content_json,
                valid_at=valid_at,
            )
            prepared.append(prep)
            prepared_by_uuid[source_uuid] = prep

        if early_errors and request.atomic:
            return self._provenance_atomic_fail_response(
                request, early_errors, trigger_indices=set(early_errors.keys())
            )

        resolved_entity_uuids: list[str] = []
        resolved_edge_uuids: list[str] = []
        target_error: CatalogItemResult | None = None

        for t in request.entity_targets:
            expected = catalog_entity_uuid(namespace, request.group_id, t.entity_type, t.graph_key)
            try:
                code, row = await self._store.resolve_endpoint_typed(
                    driver,
                    group_id=request.group_id,
                    graph_key=t.graph_key,
                    entity_type=t.entity_type,
                    expected_uuid=expected,
                )
            except Exception as exc:
                logger.error(
                    'catalog provenance_target_resolve_failed batch_id=%s kind=entity reason=%s',
                    request.batch_id,
                    type(exc).__name__,
                )
                target_error = CatalogItemResult(
                    index=0,
                    status='error',
                    graph_key=t.graph_key,
                    entity_type=t.entity_type,
                    error_code=CatalogErrorCode.internal_error,
                    error_message='entity target pre-resolve failed',
                    details={'reason': type(exc).__name__},
                )
                break
            if code is not None or row is None:
                target_error = CatalogItemResult(
                    index=0,
                    status='error',
                    graph_key=t.graph_key,
                    entity_type=t.entity_type,
                    error_code=CatalogErrorCode.provenance_target_missing,
                    error_message=f'entity target missing or mistyped: {code or "missing"}',
                )
                break
            resolved_entity_uuids.append(str(row['uuid']))

        if target_error is None:
            for t in request.edge_targets:
                edge_uuid = catalog_edge_uuid(namespace, request.group_id, t.edge_type, t.edge_key)
                try:
                    row = await self._store.get_edge_by_uuid(
                        driver, uuid=edge_uuid, group_id=request.group_id
                    )
                except Exception as exc:
                    logger.error(
                        'catalog provenance_target_resolve_failed batch_id=%s kind=edge reason=%s',
                        request.batch_id,
                        type(exc).__name__,
                    )
                    target_error = CatalogItemResult(
                        index=0,
                        status='error',
                        edge_key=t.edge_key,
                        edge_type=t.edge_type,
                        error_code=CatalogErrorCode.internal_error,
                        error_message='edge target pre-resolve failed',
                        details={'reason': type(exc).__name__},
                    )
                    break
                if row is None:
                    target_error = CatalogItemResult(
                        index=0,
                        status='error',
                        edge_key=t.edge_key,
                        edge_type=t.edge_type,
                        error_code=CatalogErrorCode.provenance_target_missing,
                        error_message='edge target missing',
                    )
                    break
                if row.get('name') is not None and row.get('name') != t.edge_type:
                    target_error = CatalogItemResult(
                        index=0,
                        status='error',
                        edge_key=t.edge_key,
                        edge_type=t.edge_type,
                        error_code=CatalogErrorCode.provenance_target_missing,
                        error_message='edge target type mismatch',
                    )
                    break
                resolved_edge_uuids.append(str(row['uuid']))

        if target_error is not None:
            errs: dict[int, CatalogItemResult] = {}
            for prep in prepared:
                errs[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.source_uuid,
                    content_sha256=prep.content_sha256,
                    graph_key=prep.item.source_key,
                    error_code=target_error.error_code,
                    error_message=target_error.error_message,
                    details=target_error.details,
                )
            for idx in early_errors:
                errs[idx] = early_errors[idx]
            if request.atomic:
                return self._provenance_atomic_fail_response(
                    request, errs, trigger_indices=set(errs.keys())
                )
            results = [
                errs.get(
                    i,
                    CatalogItemResult(
                        index=i,
                        status='error',
                        graph_key=request.sources[i].source_key,
                        error_code=target_error.error_code,
                        error_message=target_error.error_message,
                    ),
                )
                for i in range(len(request.sources))
            ]
            return self._count_provenance_response(request, results)

        for prep in prepared:
            prep.entity_uuids = list(resolved_entity_uuids)
            prep.edge_uuids = list(resolved_edge_uuids)
            prep.mentions_uuids = [
                catalog_mentions_uuid(namespace, request.group_id, prep.source_uuid, ent_uuid)
                for ent_uuid in prep.entity_uuids
            ]

        for prep in prepared:
            try:
                existing = await self._store.get_source_episode_by_uuid(
                    driver, uuid=prep.source_uuid, group_id=request.group_id
                )
            except Exception as exc:
                logger.error(
                    'catalog provenance_source_read_failed batch_id=%s reason=%s',
                    request.batch_id,
                    type(exc).__name__,
                )
                early_errors[prep.index] = CatalogItemResult(
                    index=prep.index,
                    status='error',
                    uuid=prep.source_uuid,
                    graph_key=prep.item.source_key,
                    error_code=CatalogErrorCode.internal_error,
                    error_message='source pre-read failed',
                    details={'reason': type(exc).__name__},
                )
                continue
            prep.existing = existing
            missing_links = False
            if existing is not None:
                for ent_uuid, men_uuid in zip(prep.entity_uuids, prep.mentions_uuids, strict=True):
                    try:
                        link = await self._store.get_mentions_link(
                            driver,
                            episode_uuid=prep.source_uuid,
                            entity_uuid=ent_uuid,
                            mentions_uuid=men_uuid,
                            group_id=request.group_id,
                        )
                    except Exception as exc:
                        logger.error(
                            'catalog provenance_link_read_failed batch_id=%s kind=entity reason=%s',
                            request.batch_id,
                            type(exc).__name__,
                        )
                        early_errors[prep.index] = CatalogItemResult(
                            index=prep.index,
                            status='error',
                            uuid=prep.source_uuid,
                            graph_key=prep.item.source_key,
                            error_code=CatalogErrorCode.internal_error,
                            error_message='provenance link pre-read failed',
                            details={'reason': type(exc).__name__, 'kind': 'entity'},
                        )
                        break
                    if link is None:
                        missing_links = True
                    else:
                        prep.existing_mentions.add(men_uuid)
                if prep.index in early_errors:
                    continue
                for edge_uuid in prep.edge_uuids:
                    try:
                        erow = await self._store.get_edge_by_uuid(
                            driver, uuid=edge_uuid, group_id=request.group_id
                        )
                    except Exception as exc:
                        logger.error(
                            'catalog provenance_link_read_failed batch_id=%s kind=edge reason=%s',
                            request.batch_id,
                            type(exc).__name__,
                        )
                        early_errors[prep.index] = CatalogItemResult(
                            index=prep.index,
                            status='error',
                            uuid=prep.source_uuid,
                            graph_key=prep.item.source_key,
                            error_code=CatalogErrorCode.internal_error,
                            error_message='provenance link pre-read failed',
                            details={'reason': type(exc).__name__, 'kind': 'edge'},
                        )
                        break
                    episodes = (erow or {}).get('episodes') or []
                    if prep.source_uuid not in episodes:
                        missing_links = True
                    else:
                        prep.existing_edge_links.add(edge_uuid)
                if prep.index in early_errors:
                    continue
                prep.links_checked = True
                prep.missing_links = missing_links
                prep.projected_status = (
                    'unchanged'
                    if existing.get('content_sha256') == prep.content_sha256 and not missing_links
                    else 'updated'
                )
            else:
                prep.projected_status = 'created'
                prep.missing_links = bool(prep.entity_uuids or prep.edge_uuids)

        if early_errors and request.atomic:
            return self._provenance_atomic_fail_response(
                request, early_errors, trigger_indices=set(early_errors.keys())
            )

        if request.dry_run:
            by_index = dict(early_errors)
            for prep in prepared:
                by_index[prep.index] = self._source_result(prep, prep.index)
                for index in prep.coalesced_indices:
                    by_index[index] = self._source_result(prep, index)
            results = [by_index[index] for index in range(len(request.sources))]
            resp = self._count_provenance_response(request, results)
            logger.info(
                'catalog upsert_provenance dry_run batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
                request.batch_id,
                len(request.sources),
                resp.created,
                resp.updated,
                resp.unchanged,
                resp.failed,
            )
            return resp

        try:
            await self._ensure_schema(client)
        except Exception as exc:
            logger.error(
                'catalog schema_init_failed kind=provenance reason=%s',
                type(exc).__name__,
            )
            n = len(request.sources)
            return CatalogWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                dry_run=False,
                atomic=request.atomic,
                results=[
                    CatalogItemResult(
                        index=i,
                        status='error',
                        graph_key=request.sources[i].source_key,
                        error_code=CatalogErrorCode.neo4j_transaction_failed,
                        error_message='catalog schema initialization failed',
                        details={'reason': type(exc).__name__},
                    )
                    for i in range(n)
                ],
                failed=n,
            )

        written: dict[int, CatalogItemResult] = {}
        write_set = {p.index for p in prepared if p.index not in early_errors}
        sources_to_write = sorted(
            (prep for prep in prepared if prep.index not in early_errors),
            key=lambda prep: prep.source_uuid,
        )

        try:
            async with client.driver.transaction() as tx:
                for prep in sources_to_write:
                    expected_exists, expected_source_key, expected_content_sha256 = (
                        self._source_expected_state(prep)
                    )
                    params = self._store.prepare_source_episode_params(
                        uuid=prep.source_uuid,
                        group_id=request.group_id,
                        batch_id=request.batch_id,
                        source_key=prep.item.source_key,
                        content_sha256=prep.content_sha256,
                        content=prep.content_json,
                        source='json',
                        source_description='catalog provenance source',
                        valid_at=prep.valid_at,
                        created_at=request_ts,
                        updated_at=request_ts,
                        expected_exists=expected_exists,
                        expected_source_key=expected_source_key,
                        expected_content_sha256=expected_content_sha256,
                        entity_edges=list(prep.edge_uuids),
                        name=prep.item.source_key,
                    )
                    row = await self._store.upsert_source_episode(tx, params=params)
                    if self._source_cas_matches_concurrent_identical(prep, row):
                        row = {**row, 'status': 'unchanged', 'error_code': None}
                    self._raise_source_cas_error(row)
                    await self._lock_and_recheck_provenance_targets(
                        tx, prep, group_id=request.group_id
                    )
                    status = str(row.get('status') or prep.projected_status)
                    if prep.missing_links and status == 'unchanged':
                        status = 'updated'
                    for ent_uuid, men_uuid in zip(
                        prep.entity_uuids, prep.mentions_uuids, strict=True
                    ):
                        if men_uuid not in prep.existing_mentions:
                            await self._store.upsert_mentions_link(
                                tx,
                                episode_uuid=prep.source_uuid,
                                entity_uuid=ent_uuid,
                                mentions_uuid=men_uuid,
                                group_id=request.group_id,
                                created_at=request_ts,
                            )
                    for edge_uuid in prep.edge_uuids:
                        if edge_uuid not in prep.existing_edge_links:
                            await self._store.append_edge_episode(
                                tx,
                                edge_uuid=edge_uuid,
                                episode_uuid=prep.source_uuid,
                                group_id=request.group_id,
                            )
                    written[prep.index] = self._source_result(prep, prep.index, status)
                    for index in prep.coalesced_indices:
                        written[index] = self._source_result(prep, index, status)
        except self._ProvenanceInvariantRace as exc:
            logger.error(
                'catalog upsert_provenance invariant_race batch_id=%s code=%s',
                request.batch_id,
                exc.code.value,
            )
            errs = {
                i: CatalogItemResult(
                    index=i,
                    status='error',
                    graph_key=request.sources[i].source_key,
                    error_code=exc.code,
                    error_message='provenance invariant changed in write transaction',
                )
                for i in write_set
            }
            errs.update(early_errors)
            return self._provenance_atomic_fail_response(
                request, errs, trigger_indices=set(errs.keys())
            )
        except Exception as exc:
            logger.error(
                'catalog upsert_provenance neo4j_transaction_failed batch_id=%s reason=%s',
                request.batch_id,
                type(exc).__name__,
            )
            if request.atomic:
                errs = {
                    i: CatalogItemResult(
                        index=i,
                        status='error',
                        graph_key=request.sources[i].source_key,
                        error_code=CatalogErrorCode.neo4j_transaction_failed,
                        error_message='neo4j transaction failed',
                        details={'reason': type(exc).__name__},
                    )
                    for i in write_set
                }
                errs.update(early_errors)
                return self._provenance_atomic_fail_response(
                    request, errs, trigger_indices=set(errs.keys())
                )
            for i in write_set:
                written[i] = CatalogItemResult(
                    index=i,
                    status='error' if i not in written else 'rolled_back',
                    graph_key=request.sources[i].source_key,
                    error_code=(
                        CatalogErrorCode.neo4j_transaction_failed
                        if i not in written
                        else CatalogErrorCode.batch_conflict
                    ),
                    error_message=(
                        'neo4j transaction failed'
                        if i not in written
                        else 'rolled back due to sibling failure'
                    ),
                    details={'reason': type(exc).__name__},
                )

        results = []
        for i, item in enumerate(request.sources):
            if i in early_errors:
                results.append(early_errors[i])
            elif i in written:
                results.append(written[i])
            else:
                results.append(
                    CatalogItemResult(
                        index=i,
                        status='error',
                        graph_key=item.source_key,
                        error_code=CatalogErrorCode.internal_error,
                        error_message='source result missing',
                    )
                )
        resp = self._count_provenance_response(request, results)
        logger.info(
            'catalog upsert_provenance batch_id=%s count=%s created=%s updated=%s unchanged=%s failed=%s',
            request.batch_id,
            len(request.sources),
            resp.created,
            resp.updated,
            resp.unchanged,
            resp.failed,
        )
        return resp

    # ------------------------------------------------------------------
    # Read-only batch ingest status (STAT-01/04/05/06)
    # ------------------------------------------------------------------

    @staticmethod
    def _status_ts(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    async def get_catalog_ingest_status(
        self,
        *,
        client: Any,
        request: GetCatalogIngestStatusRequest,
    ) -> CatalogIngestStatusResponse:
        """Read-only status for group_id+batch_id; Neo4j-persisted, restart-safe.

        No writes, embedder, LLM, or queue. Missing row returns structured error.
        """
        batch_id = request.batch_id
        group_id = request.group_id
        ns = self._namespace()
        batch_uuid = catalog_batch_uuid(ns, group_id, batch_id) if ns is not None else ''

        gate = self._read_gate(client, group_id=group_id, item_count=1)
        if gate is not None:
            code, message = gate
            logger.info(
                'catalog get_catalog_ingest_status gated batch_id=%s code=%s',
                batch_id,
                code,
            )
            return CatalogIngestStatusResponse(
                group_id=group_id,
                batch_id=batch_id,
                batch_uuid=batch_uuid or '00000000-0000-0000-0000-000000000000',
                status='failed',
                error_code=code,
                error_summary=(message or '')[:512],
            )

        assert ns is not None
        batch_uuid = catalog_batch_uuid(ns, group_id, batch_id)

        try:
            row = await self._store.get_batch_status(
                client.driver,
                uuid=batch_uuid,
                group_id=group_id,
            )
        except Exception as exc:
            logger.error(
                'catalog get_catalog_ingest_status read_failed batch_id=%s reason=%s',
                batch_id,
                type(exc).__name__,
            )
            return CatalogIngestStatusResponse(
                group_id=group_id,
                batch_id=batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                error_code=CatalogErrorCode.internal_error,
                error_summary='status read failed',
            )

        if row is None:
            logger.info(
                'catalog get_catalog_ingest_status missing batch_id=%s',
                batch_id,
            )
            return CatalogIngestStatusResponse(
                group_id=group_id,
                batch_id=batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                error_code=CatalogErrorCode.validation_error,
                error_summary='batch status not found',
            )

        raw_status = str(row.get('status') or 'failed')
        allowed: set[str] = {
            'planned',
            'validating',
            'embedding',
            'writing',
            'committed',
            'failed',
        }
        status: CatalogIngestStatus = (  # type: ignore[assignment]
            raw_status if raw_status in allowed else 'failed'
        )
        err_summary = row.get('error_summary') or ''
        if not isinstance(err_summary, str):
            err_summary = str(err_summary)
        if len(err_summary) > 512:
            err_summary = err_summary[:512]

        logger.info(
            'catalog get_catalog_ingest_status batch_id=%s status=%s',
            batch_id,
            status,
        )
        return CatalogIngestStatusResponse(
            group_id=str(row.get('group_id') or group_id),
            batch_id=str(row.get('batch_id') or batch_id),
            batch_uuid=str(row.get('uuid') or batch_uuid),
            status=status,
            request_sha256=row.get('request_sha256'),
            catalog_sha256=row.get('catalog_sha256'),
            entity_count=int(row.get('entity_count') or 0),
            edge_count=int(row.get('edge_count') or 0),
            provenance_count=int(row.get('provenance_count') or 0),
            created_at=self._status_ts(row.get('created_at')),
            updated_at=self._status_ts(row.get('updated_at')),
            committed_at=self._status_ts(row.get('committed_at')),
            error_summary=err_summary,
        )

    # ------------------------------------------------------------------
    # Atomic catalog batch preflight (BATC-03..05, BATC-09/10)
    # ------------------------------------------------------------------

    @staticmethod
    def _batch_canonical_payload(request: UpsertCatalogBatchRequest) -> dict[str, Any]:
        """Delegate to pure full-domain recipe (no parallel legacy Cartesian path)."""
        return batch_request_canonical_payload(request)

    @staticmethod
    def batch_request_sha256(request: UpsertCatalogBatchRequest) -> str:
        """Server-authoritative hash for batch-idempotency checks."""
        return pure_batch_request_sha256(request)

    @staticmethod
    def _batch_hash_echo_fields(
        request: UpsertCatalogBatchRequest,
        server_hash: str | None = None,
    ) -> dict[str, Any]:
        """Authoritative identity/hash fields echoed on every derivable batch response."""
        return {
            'identity_schema_version': IDENTITY_SCHEMA_VERSION,
            'canonicalization_version': CANONICALIZATION_VERSION,
            'request_sha256': server_hash,
            'catalog_sha256': request.catalog_sha256,
        }

    @staticmethod
    def _batch_provenance_item_count(request: UpsertCatalogBatchRequest) -> int:
        """Authoritative provenance item count: sources + evidence_links (request domain)."""
        provenance = request.provenance
        if provenance is None:
            return 0
        return len(provenance.sources) + len(provenance.evidence_links)

    def _batch_gate_error(
        self,
        client: Any,
        request: UpsertCatalogBatchRequest,
    ) -> tuple[CatalogErrorCode, str] | None:
        if not self.catalog_config.enabled:
            return CatalogErrorCode.feature_disabled, 'catalog_upsert.enabled is false'
        if self._namespace() is None:
            return CatalogErrorCode.invalid_uuid_namespace, 'uuid_namespace missing or invalid'
        provider = getattr(getattr(client, 'driver', None), 'provider', None)
        if getattr(provider, 'value', provider) != 'neo4j':
            return CatalogErrorCode.backend_unavailable, 'catalog writes require Neo4j backend'
        provenance = request.provenance
        if provenance is not None:
            source_count = len(provenance.sources)
            link_count = len(provenance.evidence_links)
        else:
            source_count = link_count = 0
        limits = (
            (
                len(request.entities),
                self.catalog_config.max_entities_per_batch,
                'entities',
            ),
            (len(request.edges), self.catalog_config.max_edges_per_batch, 'edges'),
            (
                source_count,
                self.catalog_config.max_provenance_links_per_batch,
                'provenance sources',
            ),
            (
                link_count,
                self.catalog_config.max_provenance_links_per_batch,
                'provenance links',
            ),
        )
        for count, maximum, label in limits:
            if count > maximum:
                return (
                    CatalogErrorCode.batch_limit_exceeded,
                    f'{label} exceed configured batch maximum ({maximum})',
                )
        return None

    @staticmethod
    def _batch_result_for_entity(
        prep: _PreparedEntity,
        *,
        status: str | None = None,
        error_code: CatalogErrorCode | None = None,
        error_message: str | None = None,
    ) -> CatalogItemResult:
        return CatalogItemResult(
            index=prep.index,
            status=(status or prep.projected_status),  # type: ignore[arg-type]
            uuid=prep.entity_uuid,
            content_sha256=prep.content_sha256,
            graph_key=prep.item.graph_key,
            entity_type=prep.item.entity_type,
            error_code=error_code,
            error_message=error_message,
            details={'kind': 'entity'},
        )

    @staticmethod
    def _batch_result_for_edge(
        prep: _PreparedEdge,
        *,
        index: int,
        status: str | None = None,
        error_code: CatalogErrorCode | None = None,
        error_message: str | None = None,
    ) -> CatalogItemResult:
        return CatalogItemResult(
            index=index,
            status=(status or prep.projected_status),  # type: ignore[arg-type]
            uuid=prep.edge_uuid,
            content_sha256=prep.content_sha256,
            edge_key=prep.item.edge_key,
            edge_type=prep.item.edge_type,
            error_code=error_code,
            error_message=error_message,
            details={'kind': 'edge'},
        )

    async def _prepare_batch_preflight(
        self,
        *,
        client: Any,
        request: Any,
        check_batch_status: bool = True,
        log_label: str = 'upsert_catalog_batch',
    ) -> _BatchPreflightOutcome:
        """Shared identity/topology/hash/projection preflight (PLAN-02, D-16).

        Used by upsert_catalog_batch and prepare_catalog_batch. Does not embed,
        open write transactions, or mutate domain/plan nodes.
        """
        namespace = self._namespace()
        batch_uuid = (
            catalog_batch_uuid(namespace, request.group_id, request.batch_id)
            if namespace is not None
            else None
        )
        # HASH-05: request hash is pure over the validated model; echo on gate failures too.
        server_hash = pure_batch_request_sha256(request)
        hash_echo = self._batch_hash_echo_fields(request, server_hash)

        def _early(
            kind: str,
            *,
            code: CatalogErrorCode | None = None,
            message: str | None = None,
        ) -> _BatchPreflightOutcome:
            return _BatchPreflightOutcome(
                namespace=namespace,
                batch_uuid=batch_uuid,
                server_hash=server_hash,
                hash_echo=hash_echo,
                early_kind=kind,
                early_code=code,
                early_message=message,
            )

        # Gate accepts UpsertCatalogBatchRequest shape; prepare shares domain fields.
        if isinstance(request, UpsertCatalogBatchRequest):
            gate_request = request
        else:
            gate_request = UpsertCatalogBatchRequest(
                identity_schema_version=request.identity_schema_version,
                system_key=request.system_key,
                group_id=request.group_id,
                batch_id=request.batch_id,
                entities=list(request.entities),
                edges=list(request.edges),
                provenance=request.provenance,
                catalog_sha256=request.catalog_sha256,
                request_sha256=request.request_sha256,
                dry_run=False,
                atomic=True,
            )
        gate = self._batch_gate_error(client, gate_request)
        if gate is not None:
            code, message = gate
            return _early('gate', code=code, message=message)
        assert namespace is not None and batch_uuid is not None
        try:
            assert_optional_client_hash(request.request_sha256, server_hash)
        except ValueError as exc:
            return _early(
                'hash_mismatch',
                code=CatalogErrorCode.content_hash_mismatch,
                message=str(exc),
            )
        effective_hash = server_hash

        if check_batch_status:
            try:
                prior_status = await self._store.get_batch_status(
                    client.driver,
                    uuid=batch_uuid,
                    group_id=request.group_id,
                )
            except Exception as exc:
                logger.error(
                    'catalog batch_status_pre_read_failed batch_id=%s reason=%s',
                    request.batch_id,
                    type(exc).__name__,
                )
                return _early(
                    'status_read',
                    code=CatalogErrorCode.internal_error,
                    message='batch status pre-read failed',
                )
            if prior_status is not None and prior_status.get('status') == 'committed':
                if prior_status.get('request_sha256') == effective_hash:
                    return _early('committed_same')
                return _early(
                    'committed_conflict',
                    code=CatalogErrorCode.batch_conflict,
                    message='committed batch_id has different request_sha256',
                )

        entity_prepared: list[_PreparedEntity] = []
        entity_by_identity: dict[tuple[str, str], _PreparedEntity] = {}
        entity_occurrences: dict[tuple[str, str], list[int]] = {}
        errors: list[CatalogItemResult] = []
        conflicted_entity_ids: set[str] = set()

        for index, item in enumerate(request.entities):
            digest = canonical_sha256(self.entity_canonical_payload(item))
            try:
                assert_optional_client_hash(item.content_sha256, digest)
            except ValueError as exc:
                errors.append(
                    CatalogItemResult(
                        index=index,
                        status='error',
                        graph_key=item.graph_key,
                        entity_type=item.entity_type,
                        error_code=CatalogErrorCode.content_hash_mismatch,
                        error_message=str(exc),
                        details={'kind': 'entity'},
                    )
                )
                continue
            entity_uuid = catalog_entity_uuid(
                namespace, request.group_id, item.entity_type, item.graph_key
            )
            identity = (item.entity_type, item.graph_key)
            occurrences = entity_occurrences.setdefault(identity, [])
            occurrences.append(index)
            if entity_uuid in conflicted_entity_ids:
                errors.append(
                    CatalogItemResult(
                        index=index,
                        status='error',
                        uuid=entity_uuid,
                        graph_key=item.graph_key,
                        entity_type=item.entity_type,
                        error_code=CatalogErrorCode.deterministic_uuid_conflict,
                        error_message='same identity different canonical payload in request',
                        details={'kind': 'entity'},
                    )
                )
                continue
            prior = entity_by_identity.get(identity)
            if prior is not None:
                if prior.content_sha256 == digest:
                    prior.coalesced_indices.append(index)
                else:
                    conflicted_entity_ids.add(entity_uuid)
                    errors = [
                        result
                        for result in errors
                        if not (result.details == {'kind': 'entity'} and result.uuid == entity_uuid)
                    ]
                    for occurrence in occurrences:
                        occurrence_item = request.entities[occurrence]
                        errors.append(
                            CatalogItemResult(
                                index=occurrence,
                                status='error',
                                uuid=entity_uuid,
                                graph_key=occurrence_item.graph_key,
                                entity_type=occurrence_item.entity_type,
                                error_code=CatalogErrorCode.deterministic_uuid_conflict,
                                error_message='same identity different canonical payload in request',
                                details={'kind': 'entity'},
                            )
                        )
                continue
            prep = _PreparedEntity(
                index=index,
                item=item,
                entity_uuid=entity_uuid,
                content_sha256=digest,
            )
            entity_by_identity[identity] = prep
            entity_prepared.append(prep)

        for prep in entity_prepared:
            if prep.entity_uuid in conflicted_entity_ids:
                continue
            try:
                existing = await self._store.get_entity_by_uuid(
                    client.driver,
                    uuid=prep.entity_uuid,
                    group_id=request.group_id,
                )
            except Exception as exc:
                errors.append(
                    self._batch_result_for_entity(
                        prep,
                        status='error',
                        error_code=CatalogErrorCode.internal_error,
                        error_message=f'entity pre-read failed: {type(exc).__name__}',
                    )
                )
                continue
            prep.existing = existing
            if existing is None:
                prep.projected_status = 'created'
            elif self._entity_label_conflict(existing, prep.item.entity_type) is not None:
                errors.append(
                    self._batch_result_for_entity(
                        prep,
                        status='error',
                        error_code=CatalogErrorCode.entity_type_conflict,
                        error_message='existing entity type conflicts with request',
                    )
                )
            elif self._entity_identity_property_conflict(existing, prep.item) is not None:
                errors.append(
                    self._batch_result_for_entity(
                        prep,
                        status='error',
                        error_code=CatalogErrorCode.deterministic_uuid_conflict,
                        error_message='existing entity identity conflicts with request',
                    )
                )
            else:
                prep.projected_status = (
                    'unchanged'
                    if existing.get('content_sha256') == prep.content_sha256
                    else 'updated'
                )

        edge_prepared: list[_PreparedEdge] = []
        edge_by_uuid: dict[str, _PreparedEdge] = {}
        edge_occurrences: dict[str, list[int]] = {}
        conflicted_edge_ids: set[str] = set()
        edge_offset = len(request.entities)
        request_entity_uuids = {
            identity: prep.entity_uuid
            for identity, prep in entity_by_identity.items()
            if prep.entity_uuid not in conflicted_entity_ids
        }

        async def _resolve_endpoint(
            entity_type: str, graph_key: str
        ) -> tuple[str | None, str | None]:
            identity = (entity_type, graph_key)
            in_request = request_entity_uuids.get(identity)
            if in_request is not None:
                return None, in_request
            expected = catalog_entity_uuid(namespace, request.group_id, entity_type, graph_key)
            try:
                code, row = await self._store.resolve_endpoint_typed(
                    client.driver,
                    group_id=request.group_id,
                    graph_key=graph_key,
                    entity_type=entity_type,
                    expected_uuid=expected,
                )
            except Exception:
                return 'internal_error', None
            if code is not None or row is None:
                return code or 'missing_endpoint', None
            resolved = str(row.get('uuid') or '')
            if resolved != expected:
                return 'deterministic_uuid_conflict', None
            return None, resolved

        for local_index, item in enumerate(request.edges):
            result_index = edge_offset + local_index
            try:
                validate_edge_endpoint_pair(
                    item.edge_type, item.source_entity_type, item.target_entity_type
                )
            except ValueError as exc:
                errors.append(
                    CatalogItemResult(
                        index=result_index,
                        status='error',
                        edge_key=item.edge_key,
                        edge_type=item.edge_type,
                        error_code=CatalogErrorCode.edge_endpoint_pair_not_allowed,
                        error_message=str(exc),
                        details={'kind': 'edge'},
                    )
                )
                continue
            digest = canonical_sha256(self.edge_canonical_payload(item))
            try:
                assert_optional_client_hash(item.content_sha256, digest)
            except ValueError as exc:
                errors.append(
                    CatalogItemResult(
                        index=result_index,
                        status='error',
                        edge_key=item.edge_key,
                        edge_type=item.edge_type,
                        error_code=CatalogErrorCode.content_hash_mismatch,
                        error_message=str(exc),
                        details={'kind': 'edge'},
                    )
                )
                continue
            edge_uuid = catalog_edge_uuid(
                namespace, request.group_id, item.edge_type, item.edge_key
            )
            occurrences = edge_occurrences.setdefault(edge_uuid, [])
            occurrences.append(local_index)
            if edge_uuid in conflicted_edge_ids:
                errors.append(
                    CatalogItemResult(
                        index=result_index,
                        status='error',
                        uuid=edge_uuid,
                        edge_key=item.edge_key,
                        edge_type=item.edge_type,
                        error_code=CatalogErrorCode.deterministic_uuid_conflict,
                        error_message='same identity different canonical payload in request',
                        details={'kind': 'edge'},
                    )
                )
                continue
            prior = edge_by_uuid.get(edge_uuid)
            if prior is not None:
                if prior.content_sha256 == digest:
                    prior.coalesced_indices.append(local_index)
                else:
                    conflicted_edge_ids.add(edge_uuid)
                    errors = [
                        result
                        for result in errors
                        if not (result.details == {'kind': 'edge'} and result.uuid == edge_uuid)
                    ]
                    for occurrence in occurrences:
                        occurrence_item = request.edges[occurrence]
                        errors.append(
                            CatalogItemResult(
                                index=edge_offset + occurrence,
                                status='error',
                                uuid=edge_uuid,
                                edge_key=occurrence_item.edge_key,
                                edge_type=occurrence_item.edge_type,
                                error_code=CatalogErrorCode.deterministic_uuid_conflict,
                                error_message='same identity different canonical payload in request',
                                details={'kind': 'edge'},
                            )
                        )
                continue
            prep = _PreparedEdge(
                index=local_index,
                item=item,
                edge_uuid=edge_uuid,
                content_sha256=digest,
                batch_result_index=result_index,
            )
            edge_by_uuid[edge_uuid] = prep
            edge_prepared.append(prep)

            source_code, prep.source_uuid = await _resolve_endpoint(
                item.source_entity_type, item.source_graph_key
            )
            target_code, prep.target_uuid = await _resolve_endpoint(
                item.target_entity_type, item.target_graph_key
            )
            endpoint_code = source_code or target_code
            if endpoint_code is not None:
                errors.append(
                    self._batch_result_for_edge(
                        prep,
                        index=result_index,
                        status='error',
                        error_code=self._endpoint_error_code(endpoint_code),
                        error_message=f'edge endpoint preflight failed: {endpoint_code}',
                    )
                )
                continue
            try:
                existing = await self._store.get_edge_by_uuid(
                    client.driver,
                    uuid=edge_uuid,
                    group_id=request.group_id,
                )
            except Exception as exc:
                errors.append(
                    self._batch_result_for_edge(
                        prep,
                        index=result_index,
                        status='error',
                        error_code=CatalogErrorCode.internal_error,
                        error_message=f'edge pre-read failed: {type(exc).__name__}',
                    )
                )
                continue
            prep.existing = existing
            if existing is None:
                prep.projected_status = 'created'
            elif self._store.detect_edge_identity_conflict(
                existing,
                edge_type=item.edge_type,
                edge_key=item.edge_key,
                source_uuid=prep.source_uuid or '',
                target_uuid=prep.target_uuid or '',
            ):
                errors.append(
                    self._batch_result_for_edge(
                        prep,
                        index=result_index,
                        status='error',
                        error_code=CatalogErrorCode.edge_identity_conflict,
                        error_message='existing edge identity conflicts with request',
                    )
                )
            else:
                prep.projected_status = (
                    'unchanged' if existing.get('content_sha256') == digest else 'updated'
                )

        provenance_sources: list[_PreparedSource] = []
        provenance_by_uuid: dict[str, _PreparedSource] = {}
        provenance_occurrences: dict[str, list[int]] = {}
        conflicted_provenance_uuids: set[str] = set()
        provenance = request.provenance
        if provenance is not None:
            invalid_uuids = {result.uuid for result in errors if result.uuid}
            # Per-source target sets derived from explicit evidence_links (non-Cartesian).
            source_entity_targets: dict[str, list[tuple[str, str, str]]] = {}
            source_edge_targets: dict[str, list[tuple[str, str, str]]] = {}
            for link in provenance.evidence_links:
                if link.entity_target is not None:
                    source_entity_targets.setdefault(link.source_key, []).append(
                        (
                            link.entity_target.entity_type,
                            link.entity_target.graph_key,
                            catalog_entity_uuid(
                                namespace,
                                request.group_id,
                                link.entity_target.entity_type,
                                link.entity_target.graph_key,
                            ),
                        )
                    )
                elif link.edge_target is not None:
                    source_edge_targets.setdefault(link.source_key, []).append(
                        (
                            link.edge_target.edge_type,
                            link.edge_target.edge_key,
                            catalog_edge_uuid(
                                namespace,
                                request.group_id,
                                link.edge_target.edge_type,
                                link.edge_target.edge_key,
                            ),
                        )
                    )

            # Resolve unique entity/edge targets referenced by evidence_links.
            resolved_entity_ok: set[str] = set()
            resolved_edge_ok: set[str] = set()
            seen_entity_targets: set[tuple[str, str]] = set()
            seen_edge_targets: set[tuple[str, str]] = set()
            for targets in source_entity_targets.values():
                for entity_type, graph_key, target_uuid in targets:
                    key = (entity_type, graph_key)
                    if key in seen_entity_targets:
                        continue
                    seen_entity_targets.add(key)
                    row = None
                    code: str | None = None
                    if target_uuid not in invalid_uuids:
                        if (entity_type, graph_key) in request_entity_uuids:
                            row = {'uuid': target_uuid}
                        else:
                            try:
                                code, row = await self._store.resolve_endpoint_typed(
                                    client.driver,
                                    group_id=request.group_id,
                                    graph_key=graph_key,
                                    entity_type=entity_type,
                                    expected_uuid=target_uuid,
                                )
                            except Exception as exc:
                                code = 'internal_error'
                                logger.error(
                                    'catalog batch provenance_target_read_failed batch_id=%s kind=entity reason=%s',
                                    request.batch_id,
                                    type(exc).__name__,
                                )
                    if code is not None or row is None or str(row.get('uuid')) != target_uuid:
                        errors.append(
                            CatalogItemResult(
                                index=len(request.entities) + len(request.edges),
                                status='error',
                                uuid=target_uuid,
                                graph_key=graph_key,
                                entity_type=entity_type,
                                error_code=CatalogErrorCode.provenance_target_missing,
                                error_message=(
                                    'provenance entity target missing or mistyped: '
                                    f'{code or "missing"}'
                                ),
                                details={'kind': 'provenance'},
                            )
                        )
                    else:
                        resolved_entity_ok.add(target_uuid)

            for targets in source_edge_targets.values():
                for edge_type, edge_key, target_uuid in targets:
                    key = (edge_type, edge_key)
                    if key in seen_edge_targets:
                        continue
                    seen_edge_targets.add(key)
                    request_edge = edge_by_uuid.get(target_uuid)
                    if target_uuid in invalid_uuids:
                        row = None
                    elif request_edge is not None:
                        row = {
                            'uuid': target_uuid,
                            'name': edge_type,
                            'edge_key': edge_key,
                        }
                    else:
                        try:
                            row = await self._store.get_edge_by_uuid(
                                client.driver, uuid=target_uuid, group_id=request.group_id
                            )
                        except Exception as exc:
                            row = None
                            logger.error(
                                'catalog batch provenance_target_read_failed batch_id=%s kind=edge reason=%s',
                                request.batch_id,
                                type(exc).__name__,
                            )
                    if (
                        row is None
                        or str(row.get('uuid') or '') != target_uuid
                        or row.get('name') not in (None, edge_type)
                        or row.get('edge_key') not in (None, edge_key)
                    ):
                        errors.append(
                            CatalogItemResult(
                                index=len(request.entities) + len(request.edges),
                                status='error',
                                uuid=target_uuid,
                                edge_key=edge_key,
                                edge_type=edge_type,
                                error_code=CatalogErrorCode.provenance_target_missing,
                                error_message='provenance edge target missing or mistyped',
                                details={'kind': 'provenance'},
                            )
                        )
                    else:
                        resolved_edge_ok.add(target_uuid)

            for index, source in enumerate(provenance.sources):
                result_index = len(request.entities) + len(request.edges) + index
                try:
                    digest = canonical_sha256(self.source_canonical_payload(source))
                    assert_optional_client_hash(source.content_sha256, digest)
                except ValueError as exc:
                    code = (
                        CatalogErrorCode.content_hash_mismatch
                        if 'content_hash_mismatch' in str(exc)
                        else CatalogErrorCode.validation_error
                    )
                    errors.append(
                        CatalogItemResult(
                            index=result_index,
                            status='error',
                            graph_key=source.source_key,
                            error_code=code,
                            error_message=str(exc),
                            details={'kind': 'provenance'},
                        )
                    )
                    continue
                try:
                    valid_at = self._parse_source_valid_at(source.reference_time)
                except ValueError:
                    # Defense-in-depth: model boundary should already reject malformed times.
                    errors.append(
                        CatalogItemResult(
                            index=result_index,
                            status='error',
                            graph_key=source.source_key,
                            error_code=CatalogErrorCode.validation_error,
                            error_message='reference_time must be a valid ISO-8601 timestamp',
                            details={'kind': 'provenance'},
                        )
                    )
                    continue
                source_uuid = catalog_source_uuid(namespace, request.group_id, source.source_key)
                occurrences = provenance_occurrences.setdefault(source_uuid, [])
                occurrences.append(index)
                prior_source = provenance_by_uuid.get(source_uuid)
                if source_uuid in conflicted_provenance_uuids:
                    errors.append(
                        self._source_conflict_result(
                            result_index, source, source_uuid, digest, batch=True
                        )
                    )
                    continue
                if prior_source is not None:
                    if prior_source.content_sha256 == digest:
                        prior_source.coalesced_indices.append(index)
                        continue
                    conflicted_provenance_uuids.add(source_uuid)
                    if prior_source in provenance_sources:
                        provenance_sources.remove(prior_source)
                    provenance_by_uuid.pop(source_uuid, None)
                    errors = [
                        result
                        for result in errors
                        if not (
                            result.details == {'kind': 'provenance'} and result.uuid == source_uuid
                        )
                    ]
                    for occurrence in occurrences:
                        occurrence_source = provenance.sources[occurrence]
                        occurrence_digest = canonical_sha256(
                            self.source_canonical_payload(occurrence_source)
                        )
                        errors.append(
                            self._source_conflict_result(
                                len(request.entities) + len(request.edges) + occurrence,
                                occurrence_source,
                                source_uuid,
                                occurrence_digest,
                                batch=True,
                            )
                        )
                    continue
                try:
                    existing = await self._store.get_source_episode_by_uuid(
                        client.driver, uuid=source_uuid, group_id=request.group_id
                    )
                except Exception as exc:
                    errors.append(
                        CatalogItemResult(
                            index=result_index,
                            status='error',
                            uuid=source_uuid,
                            graph_key=source.source_key,
                            error_code=CatalogErrorCode.internal_error,
                            error_message=f'provenance source pre-read failed: {type(exc).__name__}',
                            details={'kind': 'provenance'},
                        )
                    )
                    continue
                if existing is not None and existing.get('source_key') not in (
                    None,
                    source.source_key,
                ):
                    errors.append(
                        CatalogItemResult(
                            index=result_index,
                            status='error',
                            uuid=source_uuid,
                            graph_key=source.source_key,
                            error_code=CatalogErrorCode.deterministic_uuid_conflict,
                            error_message='existing provenance source identity conflicts with request',
                            details={'kind': 'provenance'},
                        )
                    )
                    continue
                entity_uuids = [
                    uuid_
                    for _et, _gk, uuid_ in source_entity_targets.get(source.source_key, [])
                    if uuid_ in resolved_entity_ok
                ]
                # Stable unique order
                entity_uuids = list(dict.fromkeys(entity_uuids))
                edge_uuids = [
                    uuid_
                    for _et, _ek, uuid_ in source_edge_targets.get(source.source_key, [])
                    if uuid_ in resolved_edge_ok
                ]
                edge_uuids = list(dict.fromkeys(edge_uuids))
                prep = _PreparedSource(
                    index=index,
                    item=source,
                    source_uuid=source_uuid,
                    content_sha256=digest,
                    content_json=json.dumps(
                        self.source_canonical_payload(source),
                        sort_keys=True,
                        separators=(',', ':'),
                        ensure_ascii=False,
                    ),
                    valid_at=valid_at,
                    existing=existing,
                    projected_status=(
                        'created'
                        if existing is None
                        else (
                            'unchanged' if existing.get('content_sha256') == digest else 'updated'
                        )
                    ),
                    entity_uuids=entity_uuids,
                    edge_uuids=edge_uuids,
                )
                prep.mentions_uuids = [
                    catalog_mentions_uuid(namespace, request.group_id, source_uuid, entity_uuid)
                    for entity_uuid in prep.entity_uuids
                ]
                if existing is not None:
                    link_read_error: Exception | None = None
                    for entity_uuid, mentions_uuid in zip(
                        prep.entity_uuids, prep.mentions_uuids, strict=True
                    ):
                        try:
                            link = await self._store.get_mentions_link(
                                client.driver,
                                episode_uuid=source_uuid,
                                entity_uuid=entity_uuid,
                                mentions_uuid=mentions_uuid,
                                group_id=request.group_id,
                            )
                        except Exception as exc:
                            link_read_error = exc
                            break
                        if link is None:
                            prep.projected_status = 'updated'
                            prep.missing_links = True
                        else:
                            prep.existing_mentions.add(mentions_uuid)
                    if link_read_error is None:
                        for edge_uuid in prep.edge_uuids:
                            try:
                                edge_row = await self._store.get_edge_by_uuid(
                                    client.driver, uuid=edge_uuid, group_id=request.group_id
                                )
                            except Exception as exc:
                                link_read_error = exc
                                break
                            if source_uuid not in ((edge_row or {}).get('episodes') or []):
                                prep.projected_status = 'updated'
                                prep.missing_links = True
                            else:
                                prep.existing_edge_links.add(edge_uuid)
                    if link_read_error is None:
                        prep.links_checked = True
                    if link_read_error is not None:
                        logger.error(
                            'catalog batch provenance_link_read_failed batch_id=%s reason=%s',
                            request.batch_id,
                            type(link_read_error).__name__,
                        )
                        errors.append(
                            CatalogItemResult(
                                index=result_index,
                                status='error',
                                uuid=source_uuid,
                                graph_key=source.source_key,
                                error_code=CatalogErrorCode.internal_error,
                                error_message=(
                                    'provenance link pre-read failed: '
                                    f'{type(link_read_error).__name__}'
                                ),
                                details={'kind': 'provenance'},
                            )
                        )
                        continue
                provenance_sources.append(prep)
                provenance_by_uuid[source_uuid] = prep

        if errors:
            errors.sort(key=lambda item: item.index)
            logger.info(
                'catalog %s preflight_failed batch_id=%s entities=%s edges=%s errors=%s',
                log_label,
                request.batch_id,
                len(request.entities),
                len(request.edges),
                len(errors),
            )
            early_code = (
                CatalogErrorCode.batch_conflict
                if any(
                    result.error_code == CatalogErrorCode.deterministic_uuid_conflict
                    for result in errors
                )
                else errors[0].error_code
            )
            return _BatchPreflightOutcome(
                namespace=namespace,
                batch_uuid=batch_uuid,
                server_hash=effective_hash,
                hash_echo=hash_echo,
                entity_prepared=entity_prepared,
                edge_prepared=edge_prepared,
                provenance_sources=provenance_sources,
                edge_offset=edge_offset,
                request_entity_uuids=request_entity_uuids,
                errors=errors,
                early_kind='preflight_failed',
                early_code=early_code,
                early_message='batch preflight failed',
            )

        return _BatchPreflightOutcome(
            namespace=namespace,
            batch_uuid=batch_uuid,
            server_hash=effective_hash,
            hash_echo=hash_echo,
            entity_prepared=entity_prepared,
            edge_prepared=edge_prepared,
            provenance_sources=provenance_sources,
            edge_offset=edge_offset,
            request_entity_uuids=request_entity_uuids,
            errors=[],
            early_kind=None,
        )

    def _membership_from_prepared(
        self,
        *,
        entity_prepared: list[_PreparedEntity],
        edge_prepared: list[_PreparedEdge],
        provenance_sources: list[_PreparedSource],
        evidence_membership: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compact membership including unchanged (MANI-02); no batch_id authority."""
        return {
            'entities': [
                {
                    'uuid': prep.entity_uuid,
                    'entity_type': prep.item.entity_type,
                    'graph_key': prep.item.graph_key,
                    'content_sha256': prep.content_sha256,
                    'projected_status': prep.projected_status,
                }
                for prep in sorted(
                    entity_prepared,
                    key=lambda p: (p.item.entity_type, p.item.graph_key),
                )
            ],
            'edges': [
                {
                    'uuid': prep.edge_uuid,
                    'edge_type': prep.item.edge_type,
                    'edge_key': prep.item.edge_key,
                    'content_sha256': prep.content_sha256,
                    'projected_status': prep.projected_status,
                }
                for prep in sorted(
                    edge_prepared,
                    key=lambda p: (p.item.edge_type, p.item.edge_key),
                )
            ],
            'sources': [
                {
                    'uuid': prep.source_uuid,
                    'source_key': prep.item.source_key,
                    'content_sha256': prep.content_sha256,
                    'projected_status': prep.projected_status,
                }
                for prep in sorted(provenance_sources, key=lambda p: p.item.source_key)
            ],
            'evidence_links': sorted(
                evidence_membership,
                key=lambda d: str(d.get('link_key') or ''),
            ),
        }

    def _evidence_params_from_request(
        self,
        *,
        namespace: uuid.UUID,
        group_id: str,
        batch_id: str,
        request_ts: datetime,
        evidence_links: list[Any],
        source_uuid_by_key: dict[str, str],
        entity_uuid_by_key: dict[tuple[str, str], str],
        edge_uuid_by_key: dict[tuple[str, str], str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Build store evidence params + compact membership from explicit links only."""
        coalesced = coalesce_byte_identical_evidence_links(list(evidence_links or []))
        params_out: list[dict[str, Any]] = []
        membership_out: list[dict[str, Any]] = []
        seen_link_content: dict[str, str] = {}
        for link in coalesced:
            link_key = evidence_link_key(link)
            content_sha = canonical_sha256(evidence_canonical_payload(link))
            prior = seen_link_content.get(link_key)
            if prior is not None and prior != content_sha:
                raise self._ProvenanceInvariantRace(CatalogErrorCode.provenance_link_conflict)
            if prior is not None:
                continue
            seen_link_content[link_key] = content_sha
            source_uuid = source_uuid_by_key.get(str(link.source_key))
            if not source_uuid:
                raise self._ProvenanceInvariantRace(CatalogErrorCode.provenance_target_missing)
            if link.entity_target is not None:
                target_kind = 'entity'
                target_uuid = entity_uuid_by_key.get(
                    (link.entity_target.entity_type, link.entity_target.graph_key)
                )
            elif link.edge_target is not None:
                target_kind = 'edge'
                target_uuid = edge_uuid_by_key.get(
                    (link.edge_target.edge_type, link.edge_target.edge_key)
                )
            else:
                raise self._ProvenanceInvariantRace(CatalogErrorCode.validation_error)
            if not target_uuid:
                raise self._ProvenanceInvariantRace(CatalogErrorCode.provenance_target_missing)
            ev_uuid = catalog_evidence_link_uuid(namespace, group_id, link_key)
            locator = getattr(link, 'locator', None)
            locator_json = None
            if locator is not None:
                dump = getattr(locator, 'model_dump', None)
                if callable(dump):
                    locator_json = json.dumps(
                        dump(mode='json'),
                        sort_keys=True,
                        separators=(',', ':'),
                        ensure_ascii=False,
                    )
            params_out.append(
                self._store.prepare_evidence_link_params(
                    uuid=ev_uuid,
                    group_id=group_id,
                    batch_id=batch_id,
                    link_key=link_key,
                    content_sha256=content_sha,
                    source_uuid=source_uuid,
                    target_kind=target_kind,
                    target_uuid=target_uuid,
                    evidence_kind=str(link.evidence_kind),
                    locator_json=locator_json,
                    excerpt=link.excerpt,
                    extractor_name=link.extractor_name,
                    extractor_version=link.extractor_version,
                    rule_id=link.rule_id,
                    confidence=link.confidence,
                    created_at=request_ts,
                    updated_at=request_ts,
                )
            )
            membership_out.append(
                {
                    'uuid': ev_uuid,
                    'link_key': link_key,
                    'content_sha256': content_sha,
                }
            )
        return params_out, membership_out

    def _build_projection_from_upsert(
        self,
        *,
        request: UpsertCatalogBatchRequest,
        pre: _BatchPreflightOutcome,
        request_ts: datetime,
    ) -> CatalogWriteProjection:
        """Projection for direct non-dry-run upsert after preflight+embed."""
        assert pre.namespace is not None
        assert pre.batch_uuid is not None
        entity_prepared = pre.entity_prepared
        edge_prepared = pre.edge_prepared
        provenance_sources = pre.provenance_sources
        source_uuid_by_key = {p.item.source_key: p.source_uuid for p in provenance_sources}
        entity_uuid_by_key = {
            (p.item.entity_type, p.item.graph_key): p.entity_uuid for p in entity_prepared
        }
        # Include request-entity map for targets not rewritten this batch.
        entity_uuid_by_key.update(pre.request_entity_uuids)
        edge_uuid_by_key = {(p.item.edge_type, p.item.edge_key): p.edge_uuid for p in edge_prepared}
        evidence_links = list(getattr(request.provenance, 'evidence_links', None) or [])
        evidence_params, evidence_membership = self._evidence_params_from_request(
            namespace=pre.namespace,
            group_id=request.group_id,
            batch_id=request.batch_id,
            request_ts=request_ts,
            evidence_links=evidence_links,
            source_uuid_by_key=source_uuid_by_key,
            entity_uuid_by_key=entity_uuid_by_key,
            edge_uuid_by_key=edge_uuid_by_key,
        )
        membership = self._membership_from_prepared(
            entity_prepared=entity_prepared,
            edge_prepared=edge_prepared,
            provenance_sources=provenance_sources,
            evidence_membership=evidence_membership,
        )
        return CatalogWriteProjection(
            group_id=request.group_id,
            batch_id=request.batch_id,
            batch_uuid=pre.batch_uuid,
            request_sha256=pre.server_hash,
            catalog_sha256=request.catalog_sha256,
            artifact_sha256=None,
            identity_schema_version=request.identity_schema_version,
            canonicalization_version=CANONICALIZATION_VERSION,
            namespace=pre.namespace,
            request_ts=request_ts,
            entity_prepared=entity_prepared,
            edge_prepared=edge_prepared,
            provenance_sources=provenance_sources,
            request_entity_uuids=pre.request_entity_uuids,
            evidence_link_params=evidence_params,
            membership=membership,
            entity_count=len(request.entities),
            edge_count=len(request.edges),
            provenance_count=self._batch_provenance_item_count(request),
            edge_offset=pre.edge_offset,
            request_entity_count=len(request.entities),
            plan=None,
            request_for_edge_recheck=request,
        )

    def _build_projection_from_artifact(
        self,
        *,
        artifact: dict[str, Any],
        root: dict[str, Any],
        token_digest: str,
        request_ts: datetime,
        namespace: uuid.UUID,
    ) -> CatalogWriteProjection:
        """Projection from frozen prepared artifact only — zero external I/O (D-06)."""
        group_id = str(artifact.get('group_id') or root.get('group_id') or '')
        batch_id = str(artifact.get('batch_id') or root.get('batch_id') or '')
        request_sha = str(artifact.get('request_sha256') or root.get('request_sha256') or '')
        catalog_sha = str(artifact.get('catalog_sha256') or root.get('catalog_sha256') or '')
        art_sha = str(root.get('artifact_sha256') or artifact.get('artifact_sha256') or '') or None
        plan_uuid = str(root.get('uuid') or '')
        if not group_id or not batch_id or not request_sha or not catalog_sha or not plan_uuid:
            raise CatalogStoreError(
                'prepared artifact missing identity fields',
                code='prepared_plan_conflict',
            )
        batch_uuid = catalog_batch_uuid(namespace, group_id, batch_id)
        membership_raw = artifact.get('membership')
        if not isinstance(membership_raw, dict):
            raise CatalogStoreError(
                'prepared artifact membership missing',
                code='prepared_plan_conflict',
            )
        request_canonical = artifact.get('request_canonical')
        if not isinstance(request_canonical, dict):
            raise CatalogStoreError(
                'prepared artifact request_canonical missing',
                code='prepared_plan_conflict',
            )

        # Rebuild domain items from frozen request_canonical (no embedder).
        entities_raw = list(request_canonical.get('entities') or [])
        edges_raw = list(request_canonical.get('edges') or [])
        sources_raw = list(request_canonical.get('sources') or [])
        evidence_raw = list(request_canonical.get('evidence_links') or [])

        mem_entities = {
            str(row.get('uuid')): row for row in list(membership_raw.get('entities') or [])
        }
        mem_edges = {str(row.get('uuid')): row for row in list(membership_raw.get('edges') or [])}
        mem_sources = {
            str(row.get('uuid')): row for row in list(membership_raw.get('sources') or [])
        }

        entity_prepared: list[_PreparedEntity] = []
        request_entity_uuids: dict[tuple[str, str], str] = {}
        for index, raw in enumerate(entities_raw):
            item = CatalogEntityItem.model_validate(raw)
            entity_uuid = catalog_entity_uuid(namespace, group_id, item.entity_type, item.graph_key)
            mem = mem_entities.get(entity_uuid) or {}
            emb = mem.get('name_embedding')
            # Membership rows may carry frozen embeddings under the prepare path.
            for cand in list(membership_raw.get('entities') or []):
                if str(cand.get('uuid')) == entity_uuid and cand.get('name_embedding') is not None:
                    emb = cand.get('name_embedding')
                    break
            prep = _PreparedEntity(
                index=index,
                item=item,
                entity_uuid=entity_uuid,
                content_sha256=str(
                    mem.get('content_sha256')
                    or canonical_sha256(pure_entity_canonical_payload(item))
                ),
                name_embedding=list(emb) if isinstance(emb, list) else emb,
                projected_status=str(mem.get('projected_status') or 'created'),
            )
            entity_prepared.append(prep)
            request_entity_uuids[(item.entity_type, item.graph_key)] = entity_uuid

        edge_prepared: list[_PreparedEdge] = []
        for index, raw in enumerate(edges_raw):
            item = CatalogEdgeItem.model_validate(raw)
            edge_uuid = catalog_edge_uuid(namespace, group_id, item.edge_type, item.edge_key)
            mem = mem_edges.get(edge_uuid) or {}
            emb = None
            for cand in list(membership_raw.get('edges') or []):
                if str(cand.get('uuid')) == edge_uuid and cand.get('fact_embedding') is not None:
                    emb = cand.get('fact_embedding')
                    break
            source_uuid = request_entity_uuids.get(
                (item.source_entity_type, item.source_graph_key)
            ) or catalog_entity_uuid(
                namespace, group_id, item.source_entity_type, item.source_graph_key
            )
            target_uuid = request_entity_uuids.get(
                (item.target_entity_type, item.target_graph_key)
            ) or catalog_entity_uuid(
                namespace, group_id, item.target_entity_type, item.target_graph_key
            )
            # Prefer frozen membership endpoint uuids when present.
            for cand in list(membership_raw.get('edges') or []):
                if str(cand.get('uuid')) == edge_uuid:
                    if cand.get('source_uuid'):
                        source_uuid = str(cand.get('source_uuid'))
                    if cand.get('target_uuid'):
                        target_uuid = str(cand.get('target_uuid'))
                    break
            prep = _PreparedEdge(
                index=index,
                item=item,
                edge_uuid=edge_uuid,
                content_sha256=str(
                    mem.get('content_sha256') or canonical_sha256(pure_edge_canonical_payload(item))
                ),
                source_uuid=source_uuid,
                target_uuid=target_uuid,
                fact_embedding=list(emb) if isinstance(emb, list) else emb,
                projected_status=str(mem.get('projected_status') or 'created'),
                batch_result_index=len(entities_raw) + index,
            )
            edge_prepared.append(prep)

        # Explicit evidence targets drive source link sets (non-Cartesian).
        evidence_models: list[Any] = []
        for raw in evidence_raw:
            if hasattr(raw, 'source_key'):
                evidence_models.append(raw)
            else:
                evidence_models.append(CatalogEvidenceLink.model_validate(raw))

        source_entity_targets: dict[str, list[str]] = {}
        source_edge_targets: dict[str, list[str]] = {}
        for link in evidence_models:
            if link.entity_target is not None:
                eu = catalog_entity_uuid(
                    namespace,
                    group_id,
                    link.entity_target.entity_type,
                    link.entity_target.graph_key,
                )
                source_entity_targets.setdefault(link.source_key, []).append(eu)
            elif link.edge_target is not None:
                eu = catalog_edge_uuid(
                    namespace,
                    group_id,
                    link.edge_target.edge_type,
                    link.edge_target.edge_key,
                )
                source_edge_targets.setdefault(link.source_key, []).append(eu)

        provenance_sources: list[_PreparedSource] = []
        for index, raw in enumerate(sources_raw):
            item = CatalogSourceItem.model_validate(raw)
            source_uuid = catalog_source_uuid(namespace, group_id, item.source_key)
            mem = mem_sources.get(source_uuid) or {}
            entity_uuids = list(dict.fromkeys(source_entity_targets.get(item.source_key, [])))
            edge_uuids = list(dict.fromkeys(source_edge_targets.get(item.source_key, [])))
            content_sha = str(
                mem.get('content_sha256') or canonical_sha256(pure_source_canonical_payload(item))
            )
            prep = _PreparedSource(
                index=index,
                item=item,
                source_uuid=source_uuid,
                content_sha256=content_sha,
                content_json=json.dumps(
                    pure_source_canonical_payload(item),
                    sort_keys=True,
                    separators=(',', ':'),
                    ensure_ascii=False,
                ),
                valid_at=self._parse_source_valid_at(item.reference_time),
                projected_status=str(mem.get('projected_status') or 'created'),
                entity_uuids=entity_uuids,
                edge_uuids=edge_uuids,
                mentions_uuids=[
                    catalog_mentions_uuid(namespace, group_id, source_uuid, eu)
                    for eu in entity_uuids
                ],
                missing_links=bool(entity_uuids or edge_uuids),
            )
            provenance_sources.append(prep)

        source_uuid_by_key = {p.item.source_key: p.source_uuid for p in provenance_sources}
        entity_uuid_by_key = {
            (p.item.entity_type, p.item.graph_key): p.entity_uuid for p in entity_prepared
        }
        edge_uuid_by_key = {(p.item.edge_type, p.item.edge_key): p.edge_uuid for p in edge_prepared}
        evidence_params, evidence_membership = self._evidence_params_from_request(
            namespace=namespace,
            group_id=group_id,
            batch_id=batch_id,
            request_ts=request_ts,
            evidence_links=evidence_models,
            source_uuid_by_key=source_uuid_by_key,
            entity_uuid_by_key=entity_uuid_by_key,
            edge_uuid_by_key=edge_uuid_by_key,
        )
        # Manifest membership must match frozen compact rows (including unchanged).
        membership = {
            'entities': [
                {
                    'uuid': str(r.get('uuid')),
                    'entity_type': str(r.get('entity_type')),
                    'graph_key': str(r.get('graph_key')),
                    'content_sha256': str(r.get('content_sha256')),
                    'projected_status': str(r.get('projected_status') or 'created'),
                }
                for r in list(membership_raw.get('entities') or [])
            ],
            'edges': [
                {
                    'uuid': str(r.get('uuid')),
                    'edge_type': str(r.get('edge_type')),
                    'edge_key': str(r.get('edge_key')),
                    'content_sha256': str(r.get('content_sha256')),
                    'projected_status': str(r.get('projected_status') or 'created'),
                }
                for r in list(membership_raw.get('edges') or [])
            ],
            'sources': [
                {
                    'uuid': str(r.get('uuid')),
                    'source_key': str(r.get('source_key')),
                    'content_sha256': str(r.get('content_sha256')),
                    'projected_status': str(r.get('projected_status') or 'created'),
                }
                for r in list(membership_raw.get('sources') or [])
            ],
            'evidence_links': evidence_membership
            or [
                {
                    'uuid': str(r.get('uuid')),
                    'link_key': str(r.get('link_key')),
                    'content_sha256': str(r.get('content_sha256')),
                }
                for r in list(membership_raw.get('evidence_links') or [])
            ],
        }
        edge_offset = len(entities_raw)
        recheck_req = SimpleNamespace(
            group_id=group_id,
            entities=[p.item for p in entity_prepared],
            edges=[p.item for p in edge_prepared],
        )
        return CatalogWriteProjection(
            group_id=group_id,
            batch_id=batch_id,
            batch_uuid=batch_uuid,
            request_sha256=request_sha,
            catalog_sha256=catalog_sha,
            artifact_sha256=art_sha,
            identity_schema_version=str(
                artifact.get('identity_schema_version') or IDENTITY_SCHEMA_VERSION
            ),
            canonicalization_version=str(
                artifact.get('canonicalization_version') or CANONICALIZATION_VERSION
            ),
            namespace=namespace,
            request_ts=request_ts,
            entity_prepared=entity_prepared,
            edge_prepared=edge_prepared,
            provenance_sources=provenance_sources,
            request_entity_uuids=request_entity_uuids,
            evidence_link_params=evidence_params,
            membership=membership,
            entity_count=len(entities_raw),
            edge_count=len(edges_raw),
            provenance_count=len(sources_raw) + len(evidence_models),
            edge_offset=edge_offset,
            request_entity_count=len(entities_raw),
            plan={
                'plan_uuid': plan_uuid,
                'token_digest': token_digest,
            },
            request_for_edge_recheck=recheck_req,
        )

    def _build_manifest_write_params(
        self,
        projection: CatalogWriteProjection,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        """Canonical manifest root+chunks from frozen membership (MANI-02/03)."""
        body = build_manifest_body_from_membership(
            group_id=projection.group_id,
            batch_id=projection.batch_id,
            request_sha256=projection.request_sha256,
            catalog_sha256=projection.catalog_sha256,
            membership=projection.membership,
            artifact_sha256=projection.artifact_sha256,
            identity_schema_version=projection.identity_schema_version,
            canonicalization_version=projection.canonicalization_version,
        )
        raw = serialize_manifest_body(body)
        digest = pure_manifest_sha256(raw)
        chunk_size = int(self.catalog_config.prepared_chunk_bytes)
        chunk_records = chunk_manifest_bytes(raw, chunk_size=chunk_size)
        manifest_uuid = catalog_manifest_uuid(
            projection.namespace, projection.group_id, projection.batch_id
        )
        root = self._store.prepare_manifest_root_params(
            uuid=manifest_uuid,
            group_id=projection.group_id,
            batch_id=projection.batch_id,
            identity_schema_version=projection.identity_schema_version,
            canonicalization_version=projection.canonicalization_version,
            request_sha256=projection.request_sha256,
            catalog_sha256=projection.catalog_sha256,
            artifact_sha256=projection.artifact_sha256,
            manifest_sha256=digest,
            payload_bytes=len(raw),
            chunk_count=len(chunk_records),
            entity_count=int(body['counts']['entities']),
            edge_count=int(body['counts']['edges']),
            source_count=int(body['counts']['sources']),
            evidence_link_count=int(body['counts']['evidence_links']),
            created_at=projection.request_ts,
            updated_at=projection.request_ts,
        )
        chunks: list[dict[str, Any]] = []
        for ch in chunk_records:
            idx = int(ch['chunk_index'])
            chunks.append(
                self._store.prepare_manifest_chunk_params(
                    uuid=catalog_manifest_chunk_uuid(
                        projection.namespace, projection.group_id, projection.batch_id, idx
                    ),
                    group_id=projection.group_id,
                    manifest_uuid=manifest_uuid,
                    batch_id=projection.batch_id,
                    chunk_index=idx,
                    chunk_count=len(chunk_records),
                    byte_offset=int(ch['byte_offset']),
                    byte_length=int(ch['byte_length']),
                    chunk_sha256=ch['chunk_sha256'],
                    payload_b64=ch['payload_b64'],
                )
            )
        return root, chunks, digest

    async def _write_catalog_batch_atomic(
        self,
        tx: Any,
        projection: CatalogWriteProjection,
    ) -> dict[str, Any]:
        """Co-write domain+evidence+manifest+terminals in one open Neo4j tx (D-04).

        Caller owns transaction open/commit/rollback. Any exception must abort the
        entire success transaction. Optional failed status is never written here.
        """
        entity_results: list[CatalogItemResult] = []
        edge_results: list[CatalogItemResult] = []
        provenance_results: list[CatalogItemResult] = []
        request_ts = projection.request_ts
        group_id = projection.group_id
        batch_id = projection.batch_id
        batch_uuid = projection.batch_uuid
        effective_hash = projection.request_sha256

        # 1. Lock plan (prepared) + claim/recheck batch identity
        if projection.plan is not None:
            plan_uuid = str(projection.plan.get('plan_uuid') or '')
            await self._store.lock_prepared_plan_for_commit(
                tx, plan_uuid=plan_uuid, group_id=group_id
            )

        claim = await self._store.claim_batch_status(
            tx,
            params={
                'uuid': batch_uuid,
                'group_id': group_id,
                'batch_id': batch_id,
                'request_sha256': effective_hash,
                'created_at': request_ts,
                'updated_at': request_ts,
            },
        )
        claimed_hash = claim.get('request_sha256')
        claimed_status = str(claim.get('status') or '')
        if claimed_hash != effective_hash:
            raise self._BatchStatusConflict('different_hash')
        if claimed_status == 'committed':
            # Same-hash committed: plan path may short-circuit via terminal agreement;
            # direct upsert short-circuits via conflict path.
            if projection.plan is None:
                raise self._BatchStatusConflict('already_committed')
            # Plan path continues into terminal agreement matrix below.
        elif claimed_status not in ('writing', 'failed'):
            # Unknown/non-reclaimable statuses fail closed (no concurrent rewrite).
            raise CatalogStoreError(
                f'batch status claim rejected for status={claimed_status!r}',
                code='batch_conflict',
            )

        # Recovery matrix (D-07..D-11, D-23): classify durable terminal evidence.
        # Never CAS COMMITTING→PREPARED; never repair partial terminals.
        if projection.plan is not None:
            plan_uuid = str(projection.plan.get('plan_uuid') or '')
            _, _, digest_preview = self._build_manifest_write_params(projection)
            agree_projection = {
                'group_id': group_id,
                'batch_id': batch_id,
                'batch_uuid': batch_uuid,
                'plan_uuid': plan_uuid,
                'request_sha256': effective_hash,
                'catalog_sha256': projection.catalog_sha256,
                'artifact_sha256': projection.artifact_sha256,
                'identity_schema_version': projection.identity_schema_version,
                'manifest_sha256': digest_preview,
            }
            snapshot = await self._store.read_terminal_commit_snapshot(
                tx,
                group_id=group_id,
                batch_id=batch_id,
                plan_uuid=plan_uuid,
                batch_uuid=batch_uuid,
            )
            if await self._store.terminal_commit_agrees(tx, projection=agree_projection):
                # WR-02: durable plan outcome counts authority; preserve legitimate zeros.
                snap = snapshot or {}
                plan = projection.plan or {}

                def _count(snap_key: str, plan_key: str) -> int:
                    if snap.get(snap_key) is not None:
                        return int(snap.get(snap_key) or 0)
                    if plan.get(plan_key) is not None:
                        return int(plan.get(plan_key) or 0)
                    return 0

                return {
                    'short_circuit': True,
                    'manifest_sha256': digest_preview,
                    'entity_results': [],
                    'edge_results': [],
                    'provenance_results': [],
                    'batch_uuid': batch_uuid,
                    'committed_created': _count('plan_created_count', 'created_count'),
                    'committed_updated': _count('plan_updated_count', 'updated_count'),
                    'committed_unchanged': _count('plan_unchanged_count', 'unchanged_count'),
                }
            self._raise_if_partial_terminal(
                snapshot=snapshot,
                projection=agree_projection,
            )

        # 2. Entities
        written_request_entities: set[str] = set()
        for prep in projection.entity_prepared:
            status = prep.projected_status
            existing = await self._store.get_entity_by_uuid(
                None,
                uuid=prep.entity_uuid,
                group_id=group_id,
                tx=tx,
            )
            if existing is None and status == 'unchanged':
                raise self._EntityInvariantRace(CatalogErrorCode.missing_endpoint)
            if existing is not None:
                if self._entity_label_conflict(existing, prep.item.entity_type) is not None:
                    raise self._EntityInvariantRace(CatalogErrorCode.entity_type_conflict)
                if self._entity_identity_property_conflict(existing, prep.item) is not None:
                    raise self._EntityInvariantRace(CatalogErrorCode.deterministic_uuid_conflict)
                if status == 'unchanged' and existing.get('content_sha256') != prep.content_sha256:
                    raise self._EntityInvariantRace(CatalogErrorCode.batch_conflict)
            if status != 'unchanged':
                if not prep.name_embedding:
                    raise CatalogStoreError(
                        'frozen name_embedding missing for non-unchanged entity',
                        code='embedding_failed',
                    )
                row = await self._store.upsert_entity_item(
                    tx,
                    entity_type=prep.item.entity_type,
                    params=self._store.prepare_entity_params(
                        entity_type=prep.item.entity_type,
                        uuid=prep.entity_uuid,
                        group_id=group_id,
                        batch_id=batch_id,
                        graph_key=prep.item.graph_key,
                        name_raw=prep.item.name_raw,
                        name_canonical=prep.item.name_canonical,
                        database_qualified_name=prep.item.database_qualified_name,
                        summary=prep.item.summary,
                        content_sha256=prep.content_sha256,
                        created_at=request_ts,
                        updated_at=request_ts,
                        name_embedding=list(prep.name_embedding),
                        attributes=prep.item.attributes,
                        source_refs=prep.item.source_refs,
                        confidence=prep.item.confidence,
                    ),
                )
                self._raise_entity_row_error(row)
                status = self._write_status_from_row(row, prep.projected_status)
                written_request_entities.add(prep.entity_uuid)
            entity_results.append(self._batch_result_for_entity(prep, status=status))
            for index in prep.coalesced_indices:
                duplicate = self._batch_result_for_entity(prep, status=status)
                duplicate.index = index
                entity_results.append(duplicate)

        # 3. Edges
        recheck_request = projection.request_for_edge_recheck
        for prep in projection.edge_prepared:
            status = prep.projected_status
            if recheck_request is not None:
                existing = await self._batch_recheck_edge_in_tx(
                    tx,
                    prep,
                    recheck_request,
                    projection.request_entity_uuids,
                    written_request_entities,
                )
            else:
                existing = await self._store.get_edge_by_uuid(
                    None, uuid=prep.edge_uuid, group_id=group_id, tx=tx
                )
            if status == 'unchanged':
                if existing is None:
                    raise self._EdgeEndpointRace(CatalogErrorCode.missing_endpoint)
                if existing.get('content_sha256') != prep.content_sha256:
                    raise self._EdgeEndpointRace(CatalogErrorCode.batch_conflict)
            else:
                if not prep.fact_embedding:
                    raise CatalogStoreError(
                        'frozen fact_embedding missing for non-unchanged edge',
                        code='embedding_failed',
                    )
                row = await self._store.upsert_edge_item(
                    tx,
                    params=self._store.prepare_edge_params(
                        edge_type=prep.item.edge_type,
                        uuid=prep.edge_uuid,
                        group_id=group_id,
                        batch_id=batch_id,
                        edge_key=prep.item.edge_key,
                        source_uuid=prep.source_uuid or '',
                        target_uuid=prep.target_uuid or '',
                        fact=prep.item.fact,
                        evidence=prep.item.evidence,
                        content_sha256=prep.content_sha256,
                        created_at=request_ts,
                        updated_at=request_ts,
                        fact_embedding=list(prep.fact_embedding),
                        attributes=prep.item.attributes,
                        confidence=prep.item.confidence,
                    ),
                )
                self._raise_edge_row_error(row)
                status = self._write_status_from_row(row, prep.projected_status)
                if status == 'error':
                    raise CatalogStoreError(
                        'edge write returned error without raise',
                        code='neo4j_transaction_failed',
                    )
            result_index = (
                prep.batch_result_index
                if prep.batch_result_index is not None
                else projection.edge_offset + prep.index
            )
            edge_results.append(
                self._batch_result_for_edge(prep, index=result_index, status=status)
            )
            for local_index in prep.coalesced_indices:
                edge_results.append(
                    self._batch_result_for_edge(
                        prep,
                        index=projection.request_entity_count + local_index,
                        status=status,
                    )
                )

        # 4. Sources + Graphiti compatibility links
        created_targets = {
            *(('entity', uuid_) for uuid_ in written_request_entities),
            *(('edge', result.uuid) for result in edge_results if result.uuid),
        }
        for prep in sorted(projection.provenance_sources, key=lambda source: source.source_uuid):
            expected_exists, expected_source_key, expected_content_sha256 = (
                self._source_expected_state(prep)
            )
            params = self._store.prepare_source_episode_params(
                uuid=prep.source_uuid,
                group_id=group_id,
                batch_id=batch_id,
                source_key=prep.item.source_key,
                content_sha256=prep.content_sha256,
                content=prep.content_json,
                source='json',
                source_description='catalog provenance source',
                valid_at=prep.valid_at,
                created_at=request_ts,
                updated_at=request_ts,
                expected_exists=expected_exists,
                expected_source_key=expected_source_key,
                expected_content_sha256=expected_content_sha256,
                entity_edges=list(prep.edge_uuids),
                name=prep.item.source_key,
            )
            row = await self._store.upsert_source_episode(tx, params=params)
            if self._source_cas_matches_concurrent_identical(prep, row):
                row = {**row, 'status': 'unchanged', 'error_code': None}
            self._raise_source_cas_error(row)
            await self._lock_and_recheck_provenance_targets(
                tx,
                prep,
                group_id=group_id,
                created_targets=created_targets,
            )
            source_status = str(row.get('status') or prep.projected_status)
            if prep.missing_links and source_status == 'unchanged':
                source_status = 'updated'
            for entity_uuid, mentions_uuid in zip(
                prep.entity_uuids, prep.mentions_uuids, strict=True
            ):
                if mentions_uuid not in prep.existing_mentions:
                    await self._store.upsert_mentions_link(
                        tx,
                        episode_uuid=prep.source_uuid,
                        entity_uuid=entity_uuid,
                        mentions_uuid=mentions_uuid,
                        group_id=group_id,
                        created_at=request_ts,
                    )
            for edge_uuid in prep.edge_uuids:
                if edge_uuid not in prep.existing_edge_links:
                    await self._store.append_edge_episode(
                        tx,
                        edge_uuid=edge_uuid,
                        episode_uuid=prep.source_uuid,
                        group_id=group_id,
                    )
            provenance_offset = projection.request_entity_count + projection.edge_count
            provenance_results.append(
                self._source_result(
                    prep,
                    prep.index,
                    source_status,
                    batch=True,
                    offset=provenance_offset,
                )
            )
            for index in prep.coalesced_indices:
                provenance_results.append(
                    self._source_result(
                        prep,
                        index,
                        source_status,
                        batch=True,
                        offset=provenance_offset,
                    )
                )

        # 5. Exact evidence control records (explicit links only)
        if projection.evidence_link_params:
            await self._store.write_evidence_links(tx, links=projection.evidence_link_params)

        # 6. Manifest root + chunks
        root, chunks, digest = self._build_manifest_write_params(projection)
        await self._store.write_manifest_root_and_chunks(tx, root=root, chunks=chunks)

        # 7. Terminal batch committed
        status_params = self._store.prepare_batch_status_params(
            uuid=batch_uuid,
            group_id=group_id,
            batch_id=batch_id,
            status='committed',
            request_sha256=effective_hash,
            catalog_sha256=projection.catalog_sha256,
            entity_count=projection.entity_count,
            edge_count=projection.edge_count,
            provenance_count=projection.provenance_count,
            created_at=request_ts,
            updated_at=request_ts,
            committed_at=request_ts,
        )
        committed_row = await self._store.upsert_batch_status(tx, params=status_params)
        if committed_row.get('request_sha256') != effective_hash:
            raise self._BatchStatusConflict('different_hash')
        if committed_row.get('status') != 'committed':
            raise self._BatchStatusConflict('commit_rejected')

        # 8. Terminal plan COMMITTING→COMMITTED with durable outcome counts (WR-02)
        all_results = entity_results + edge_results + provenance_results
        outcome_created = sum(1 for r in all_results if r.status == 'created')
        outcome_updated = sum(1 for r in all_results if r.status == 'updated')
        outcome_unchanged = sum(1 for r in all_results if r.status == 'unchanged')
        if projection.plan is not None:
            token_digest = str(projection.plan.get('token_digest') or '')
            await self._store.cas_plan_state(
                tx,
                token_digest=token_digest,
                expected_from=PLAN_STATE_COMMITTING,
                to_state=PLAN_STATE_COMMITTED,
                updated_at=request_ts,
                now=request_ts,
                created_count=outcome_created,
                updated_count=outcome_updated,
                unchanged_count=outcome_unchanged,
            )

        return {
            'short_circuit': False,
            'manifest_sha256': digest,
            'entity_results': entity_results,
            'edge_results': edge_results,
            'provenance_results': provenance_results,
            'batch_uuid': batch_uuid,
            'committed_created': outcome_created,
            'committed_updated': outcome_updated,
            'committed_unchanged': outcome_unchanged,
        }

    async def upsert_catalog_batch(
        self,
        *,
        client: Any,
        request: UpsertCatalogBatchRequest,
    ) -> CatalogBatchWriteResponse:
        """Preflight a nested deterministic catalog batch before any embedding/write."""
        pre = await self._prepare_batch_preflight(
            client=client,
            request=request,
            check_batch_status=True,
            log_label='upsert_catalog_batch',
        )
        dry_run = bool(getattr(request, 'dry_run', False))
        hash_echo = pre.hash_echo
        batch_uuid = pre.batch_uuid
        server_hash = pre.server_hash
        effective_hash = server_hash

        if pre.early_kind == 'gate':
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=dry_run,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=pre.early_code,
                error_message=pre.early_message,
                **hash_echo,
            )
        if pre.early_kind == 'hash_mismatch':
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=dry_run,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=pre.early_code,
                error_message=pre.early_message,
                **hash_echo,
            )
        if pre.early_kind == 'status_read':
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=dry_run,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=pre.early_code,
                error_message=pre.early_message,
                **hash_echo,
            )
        if pre.early_kind == 'committed_same':
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=dry_run,
                status='committed',
                entity_unchanged=len(request.entities),
                edge_unchanged=len(request.edges),
                provenance_unchanged=self._batch_provenance_item_count(request),
                **hash_echo,
            )
        if pre.early_kind == 'committed_conflict':
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=dry_run,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=pre.early_code,
                error_message=pre.early_message,
                **hash_echo,
            )
        if pre.early_kind == 'preflight_failed':
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=dry_run,
                status='failed',
                results=pre.errors,
                failed=len(pre.errors),
                error_code=pre.early_code,
                error_message=pre.early_message,
                **hash_echo,
            )

        assert batch_uuid is not None
        entity_prepared = pre.entity_prepared
        edge_prepared = pre.edge_prepared
        provenance_sources = pre.provenance_sources
        edge_offset = pre.edge_offset

        if request.dry_run:
            entity_results: list[CatalogItemResult] = []
            for prep in entity_prepared:
                entity_results.append(self._batch_result_for_entity(prep))
                for coalesced in prep.coalesced_indices:
                    duplicate = self._batch_result_for_entity(prep)
                    duplicate.index = coalesced
                    entity_results.append(duplicate)
            edge_results: list[CatalogItemResult] = []
            for prep in edge_prepared:
                edge_results.append(
                    self._batch_result_for_edge(
                        prep,
                        index=edge_offset + prep.index,
                    )
                )
                for coalesced in prep.coalesced_indices:
                    edge_results.append(
                        self._batch_result_for_edge(
                            prep,
                            index=edge_offset + coalesced,
                        )
                    )
            provenance_results: list[CatalogItemResult] = []
            provenance_offset = len(request.entities) + len(request.edges)
            for prep in provenance_sources:
                provenance_results.append(
                    self._source_result(prep, prep.index, batch=True, offset=provenance_offset)
                )
                for coalesced in prep.coalesced_indices:
                    provenance_results.append(
                        self._source_result(prep, coalesced, batch=True, offset=provenance_offset)
                    )
            results = sorted(
                entity_results + edge_results + provenance_results,
                key=lambda item: item.index,
            )
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=True,
                status='validating',
                results=results,
                entity_created=sum(result.status == 'created' for result in entity_results),
                entity_updated=sum(result.status == 'updated' for result in entity_results),
                entity_unchanged=sum(result.status == 'unchanged' for result in entity_results),
                edge_created=sum(result.status == 'created' for result in edge_results),
                edge_updated=sum(result.status == 'updated' for result in edge_results),
                edge_unchanged=sum(result.status == 'unchanged' for result in edge_results),
                provenance_created=sum(result.status == 'created' for result in provenance_results),
                provenance_updated=sum(result.status == 'updated' for result in provenance_results),
                provenance_unchanged=sum(
                    result.status == 'unchanged' for result in provenance_results
                ),
                **hash_echo,
            )

        entity_to_write = [prep for prep in entity_prepared if prep.projected_status != 'unchanged']
        edge_to_write = [prep for prep in edge_prepared if prep.projected_status != 'unchanged']
        try:
            for prep in entity_to_write:
                text = ' '.join(
                    [prep.item.graph_key, prep.item.database_qualified_name, prep.item.summary]
                ).replace('\n', ' ')
                prep.name_embedding = await client.embedder.create(input_data=[text])
            for prep in edge_to_write:
                prep.fact_embedding = await client.embedder.create(
                    input_data=[prep.item.fact.replace('\n', ' ')]
                )
        except Exception as exc:
            logger.error(
                'catalog upsert_catalog_batch embedding_failed batch_id=%s entities=%s edges=%s reason=%s',
                request.batch_id,
                len(entity_to_write),
                len(edge_to_write),
                type(exc).__name__,
            )
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=CatalogErrorCode.embedding_failed,
                error_message='embedding generation failed',
                **hash_echo,
            )

        try:
            await self._ensure_schema(client)
        except Exception as exc:
            logger.error(
                'catalog schema_init_failed kind=batch batch_id=%s reason=%s',
                request.batch_id,
                type(exc).__name__,
            )
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=CatalogErrorCode.neo4j_transaction_failed,
                error_message='catalog schema initialization failed',
                **hash_echo,
            )

        request_ts = datetime.now(timezone.utc)
        entity_results: list[CatalogItemResult] = []
        edge_results: list[CatalogItemResult] = []
        provenance_results: list[CatalogItemResult] = []

        async def _record_failed_status(error_summary: str) -> None:
            # D-27: optional failed status only after success-tx rollback; never with manifest.
            failed_params = self._store.prepare_batch_status_params(
                uuid=batch_uuid,
                group_id=request.group_id,
                batch_id=request.batch_id,
                status='failed',
                request_sha256=effective_hash,
                catalog_sha256=request.catalog_sha256,
                entity_count=len(request.entities),
                edge_count=len(request.edges),
                provenance_count=self._batch_provenance_item_count(request),
                created_at=request_ts,
                updated_at=datetime.now(timezone.utc),
                error_summary=error_summary,
            )
            try:
                async with client.driver.transaction() as status_tx:
                    await self._store.upsert_batch_status(status_tx, params=failed_params)
            except Exception as status_exc:
                logger.error(
                    'catalog upsert_catalog_batch failed_status_write_failed batch_id=%s reason=%s',
                    request.batch_id,
                    type(status_exc).__name__,
                )

        try:
            projection = self._build_projection_from_upsert(
                request=request,
                pre=pre,
                request_ts=request_ts,
            )
            async with client.driver.transaction() as tx:
                write_out = await self._write_catalog_batch_atomic(tx, projection)
            entity_results = list(write_out.get('entity_results') or [])
            edge_results = list(write_out.get('edge_results') or [])
            provenance_results = list(write_out.get('provenance_results') or [])
        except self._BatchStatusConflict as exc:
            if exc.reason == 'already_committed':
                return CatalogBatchWriteResponse(
                    group_id=request.group_id,
                    batch_id=request.batch_id,
                    batch_uuid=batch_uuid,
                    status='committed',
                    entity_unchanged=len(request.entities),
                    edge_unchanged=len(request.edges),
                    provenance_unchanged=self._batch_provenance_item_count(request),
                    **hash_echo,
                )
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges) + len(provenance_sources), 1),
                error_code=CatalogErrorCode.batch_conflict,
                error_message='batch_id has different request_sha256',
                **hash_echo,
            )
        except self._EntityInvariantRace as exc:
            logger.error(
                'catalog upsert_catalog_batch entity_invariant_race batch_id=%s code=%s',
                request.batch_id,
                exc.code.value,
            )
            await _record_failed_status(exc.code.value)
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges) + len(provenance_sources), 1),
                rolled_back=len(entity_results) + len(edge_results) + len(provenance_results),
                error_code=exc.code,
                error_message=f'entity under-lock conflict: {exc.code.value}',
                **hash_echo,
            )
        except self._ProvenanceInvariantRace as exc:
            logger.error(
                'catalog upsert_catalog_batch invariant_race batch_id=%s code=%s',
                request.batch_id,
                exc.code.value,
            )
            await _record_failed_status(exc.code.value)
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges) + len(provenance_sources), 1),
                rolled_back=len(entity_results) + len(edge_results) + len(provenance_results),
                error_code=exc.code,
                error_message='provenance invariant changed in write transaction',
                **hash_echo,
            )
        except self._EdgeEndpointRace as exc:
            logger.error(
                'catalog upsert_catalog_batch edge_endpoint_race batch_id=%s code=%s',
                request.batch_id,
                exc.code.value,
            )
            await _record_failed_status(exc.code.value)
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges) + len(provenance_sources), 1),
                rolled_back=len(entity_results) + len(edge_results) + len(provenance_results),
                error_code=exc.code,
                error_message=f'edge under-lock conflict: {exc.code.value}',
                **hash_echo,
            )
        except CatalogStoreError as exc:
            # Store-boundary typed codes (batch_conflict, embedding_failed, ...) must not
            # collapse to neo4j_transaction_failed.
            mapped = self._map_store_error_code(exc)
            logger.error(
                'catalog upsert_catalog_batch store_error batch_id=%s code=%s',
                request.batch_id,
                mapped.value,
            )
            await _record_failed_status(mapped.value)
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges) + len(provenance_sources), 1),
                rolled_back=len(entity_results) + len(edge_results) + len(provenance_results),
                error_code=mapped,
                error_message=str(exc) or mapped.value,
                **hash_echo,
            )
        except Exception as exc:
            logger.error(
                'catalog upsert_catalog_batch neo4j_transaction_failed batch_id=%s entities=%s edges=%s provenance=%s reason=%s',
                request.batch_id,
                len(request.entities),
                len(request.edges),
                len(provenance_sources),
                type(exc).__name__,
            )
            await _record_failed_status(type(exc).__name__)
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges) + len(provenance_sources), 1),
                rolled_back=len(entity_results) + len(edge_results) + len(provenance_results),
                error_code=CatalogErrorCode.neo4j_transaction_failed,
                error_message='neo4j transaction failed',
                **hash_echo,
            )

        results = sorted(
            entity_results + edge_results + provenance_results,
            key=lambda result: result.index,
        )
        response = CatalogBatchWriteResponse(
            group_id=request.group_id,
            batch_id=request.batch_id,
            batch_uuid=batch_uuid,
            status='committed',
            results=results,
            entity_created=sum(result.status == 'created' for result in entity_results),
            entity_updated=sum(result.status == 'updated' for result in entity_results),
            entity_unchanged=sum(result.status == 'unchanged' for result in entity_results),
            edge_created=sum(result.status == 'created' for result in edge_results),
            edge_updated=sum(result.status == 'updated' for result in edge_results),
            edge_unchanged=sum(result.status == 'unchanged' for result in edge_results),
            provenance_created=sum(result.status == 'created' for result in provenance_results),
            provenance_updated=sum(result.status == 'updated' for result in provenance_results),
            provenance_unchanged=sum(result.status == 'unchanged' for result in provenance_results),
            **hash_echo,
        )
        logger.info(
            'catalog upsert_catalog_batch committed batch_id=%s entities=%s edges=%s provenance=%s',
            request.batch_id,
            len(request.entities),
            len(request.edges),
            len(provenance_sources),
        )
        return response

    async def prepare_catalog_batch(
        self,
        *,
        client: Any,
        request: PrepareCatalogBatchRequest,
    ) -> PrepareCatalogBatchResponse:
        """Validate/project/embed then persist control-plane plan only (PLAN-02/03/04/06).

        Order: shared preflight → embed all required → serialize artifact →
        ensure_plan_schema → single plan/chunk tx. Never writes Entity/RELATES_TO/
        Episodic/evidence/manifest/CatalogIngestBatch. Raw token returned once.
        """
        pre = await self._prepare_batch_preflight(
            client=client,
            request=request,
            check_batch_status=True,
            log_label='prepare_catalog_batch',
        )
        server_hash = pre.server_hash

        def _fail(
            code: CatalogErrorCode,
            message: str,
            *,
            plan_uuid: str = '',
            artifact_sha: str = '',
            expires_at: str = '',
            projected_created: int = 0,
            projected_updated: int = 0,
            projected_unchanged: int = 0,
        ) -> PrepareCatalogBatchResponse:
            return PrepareCatalogBatchResponse(
                plan_token='',
                plan_uuid=plan_uuid,
                request_sha256=server_hash,
                catalog_sha256=request.catalog_sha256,
                artifact_sha256=artifact_sha,
                identity_schema_version=request.identity_schema_version,
                expires_at=expires_at,
                entity_count=len(request.entities),
                edge_count=len(request.edges),
                source_count=len(request.provenance.sources) if request.provenance else 0,
                evidence_link_count=(
                    len(request.provenance.evidence_links) if request.provenance else 0
                ),
                projected_created=projected_created,
                projected_updated=projected_updated,
                projected_unchanged=projected_unchanged,
                error_code=code,
                error_message=message,
            )

        if pre.early_kind in ('gate', 'hash_mismatch', 'status_read'):
            return _fail(
                pre.early_code or CatalogErrorCode.validation_error,
                pre.early_message or 'prepare preflight failed',
            )
        if pre.early_kind == 'committed_same':
            # Already-committed same hash: reject new token (no domain/status writes).
            return _fail(
                CatalogErrorCode.prepared_plan_conflict,
                'batch already committed with matching request_sha256',
            )
        if pre.early_kind == 'committed_conflict':
            return _fail(
                pre.early_code or CatalogErrorCode.batch_conflict,
                pre.early_message or 'committed batch_id has different request_sha256',
            )
        if pre.early_kind == 'preflight_failed':
            return _fail(
                pre.early_code or CatalogErrorCode.validation_error,
                pre.early_message or 'batch preflight failed',
            )
        assert pre.namespace is not None
        namespace = pre.namespace
        entity_prepared = pre.entity_prepared
        edge_prepared = pre.edge_prepared
        provenance_sources = pre.provenance_sources

        def _status_counts(items: list[Any]) -> tuple[int, int, int]:
            created = updated = unchanged = 0
            for prep in items:
                st = prep.projected_status
                if st == 'created':
                    created += 1
                elif st == 'updated':
                    updated += 1
                elif st == 'unchanged':
                    unchanged += 1
            return created, updated, unchanged

        e_c, e_u, e_x = _status_counts(entity_prepared)
        g_c, g_u, g_x = _status_counts(edge_prepared)
        s_c, s_u, s_x = _status_counts(provenance_sources)
        projected_created = e_c + g_c + s_c
        projected_updated = e_u + g_u + s_u
        projected_unchanged = e_x + g_x + s_x

        entity_to_embed = [p for p in entity_prepared if p.projected_status != 'unchanged']
        edge_to_embed = [p for p in edge_prepared if p.projected_status != 'unchanged']
        try:
            for prep in entity_to_embed:
                text_in = ' '.join(
                    [prep.item.graph_key, prep.item.database_qualified_name, prep.item.summary]
                ).replace('\n', ' ')
                prep.name_embedding = await client.embedder.create(input_data=[text_in])
            for prep in edge_to_embed:
                prep.fact_embedding = await client.embedder.create(
                    input_data=[prep.item.fact.replace('\n', ' ')]
                )
        except Exception as exc:
            logger.error(
                'catalog prepare_catalog_batch embedding_failed batch_id=%s entities=%s edges=%s reason=%s',
                request.batch_id,
                len(entity_to_embed),
                len(edge_to_embed),
                type(exc).__name__,
            )
            return _fail(
                CatalogErrorCode.embedding_failed,
                'embedding generation failed',
                projected_created=projected_created,
                projected_updated=projected_updated,
                projected_unchanged=projected_unchanged,
            )

        membership_entities = [
            {
                'uuid': prep.entity_uuid,
                'entity_type': prep.item.entity_type,
                'graph_key': prep.item.graph_key,
                'content_sha256': prep.content_sha256,
                'projected_status': prep.projected_status,
                'name_embedding': prep.name_embedding,
            }
            for prep in sorted(
                entity_prepared,
                key=lambda p: (p.item.entity_type, p.item.graph_key),
            )
        ]
        membership_edges = [
            {
                'uuid': prep.edge_uuid,
                'edge_type': prep.item.edge_type,
                'edge_key': prep.item.edge_key,
                'source_uuid': prep.source_uuid,
                'target_uuid': prep.target_uuid,
                'content_sha256': prep.content_sha256,
                'projected_status': prep.projected_status,
                'fact_embedding': prep.fact_embedding,
            }
            for prep in sorted(
                edge_prepared,
                key=lambda p: (p.item.edge_type, p.item.edge_key),
            )
        ]
        membership_sources = [
            {
                'uuid': prep.source_uuid,
                'source_key': prep.item.source_key,
                'content_sha256': prep.content_sha256,
                'projected_status': prep.projected_status,
            }
            for prep in sorted(provenance_sources, key=lambda p: p.item.source_key)
        ]
        evidence_links_raw = list(getattr(request.provenance, 'evidence_links', None) or [])
        # Byte-identical coalesce first (same authority as request hash); then reject
        # same link_key with divergent content before freezing membership.
        evidence_links_coalesced = coalesce_byte_identical_evidence_links(evidence_links_raw)
        membership_evidence = []
        seen_link_content: dict[str, str] = {}
        for link in evidence_links_coalesced:
            link_key = evidence_link_key(link)
            content_sha = canonical_sha256(evidence_canonical_payload(link))
            prior_sha = seen_link_content.get(link_key)
            if prior_sha is not None and prior_sha != content_sha:
                return _fail(
                    CatalogErrorCode.provenance_link_conflict,
                    'evidence links share identity key with divergent content',
                    projected_created=projected_created,
                    projected_updated=projected_updated,
                    projected_unchanged=projected_unchanged,
                )
            if prior_sha is None:
                seen_link_content[link_key] = content_sha
                membership_evidence.append(
                    {
                        'uuid': catalog_evidence_link_uuid(namespace, request.group_id, link_key),
                        'link_key': link_key,
                        'content_sha256': content_sha,
                    }
                )
        membership_evidence.sort(key=lambda d: d['link_key'])
        # Coalesced membership is count authority for plan/artifact/response/manifest.
        coalesced_evidence_count = len(membership_evidence)

        plan_id = f'{request.batch_id}|{server_hash}'
        plan_uuid = catalog_prepared_plan_uuid(namespace, request.group_id, plan_id)
        artifact_body = {
            'artifact_serialization_version': PREPARED_ARTIFACT_SERIALIZATION_VERSION,
            'canonicalization_version': CANONICALIZATION_VERSION,
            'identity_schema_version': request.identity_schema_version,
            'catalog_schema_version': CATALOG_SCHEMA_VERSION,
            'group_id': request.group_id,
            'batch_id': request.batch_id,
            'system_key': request.system_key,
            'request_sha256': server_hash,
            'catalog_sha256': request.catalog_sha256,
            'plan_id': plan_id,
            'membership': {
                'entities': membership_entities,
                'edges': membership_edges,
                'sources': membership_sources,
                'evidence_links': membership_evidence,
            },
            'request_canonical': batch_request_canonical_payload(request),
            'counts': {
                'entities': len(request.entities),
                'edges': len(request.edges),
                'sources': len(request.provenance.sources) if request.provenance else 0,
                'evidence_links': coalesced_evidence_count,
                'created': projected_created,
                'updated': projected_updated,
                'unchanged': projected_unchanged,
            },
        }
        try:
            artifact_bytes = serialize_prepared_artifact(artifact_body)
        except ValueError as exc:
            return _fail(
                CatalogErrorCode.validation_error,
                f'prepared artifact serialization failed: {exc}',
                plan_uuid=plan_uuid,
                projected_created=projected_created,
                projected_updated=projected_updated,
                projected_unchanged=projected_unchanged,
            )
        payload_bytes = len(artifact_bytes)
        max_payload = int(self.catalog_config.max_prepared_payload_bytes)
        if payload_bytes > max_payload:
            return _fail(
                CatalogErrorCode.batch_limit_exceeded,
                f'prepared payload exceeds max_prepared_payload_bytes ({max_payload})',
                plan_uuid=plan_uuid,
                projected_created=projected_created,
                projected_updated=projected_updated,
                projected_unchanged=projected_unchanged,
            )
        art_sha = artifact_sha256(artifact_bytes)
        chunk_size = int(self.catalog_config.prepared_chunk_bytes)
        try:
            chunk_records = chunk_artifact_bytes(artifact_bytes, chunk_size=chunk_size)
        except ValueError as exc:
            return _fail(
                CatalogErrorCode.batch_limit_exceeded,
                f'prepared artifact chunking failed: {exc}',
                plan_uuid=plan_uuid,
                artifact_sha=art_sha,
                projected_created=projected_created,
                projected_updated=projected_updated,
                projected_unchanged=projected_unchanged,
            )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=int(self.catalog_config.plan_ttl_seconds))
        expires_at_str = expires_at.isoformat()
        raw_token = mint_plan_token()
        token_digest = plan_token_digest(raw_token)

        chunk_params: list[dict[str, Any]] = []
        for ch in chunk_records:
            idx = int(ch['chunk_index'])
            chunk_params.append(
                {
                    'uuid': catalog_prepared_plan_chunk_uuid(
                        namespace, request.group_id, plan_id, idx
                    ),
                    'group_id': request.group_id,
                    'plan_uuid': plan_uuid,
                    'chunk_index': idx,
                    'chunk_count': len(chunk_records),
                    'byte_offset': int(ch['byte_offset']),
                    'byte_length': int(ch['byte_length']),
                    'chunk_sha256': ch['chunk_sha256'],
                    'payload_b64': ch['payload_b64'],
                }
            )

        plan_params = {
            'uuid': plan_uuid,
            'group_id': request.group_id,
            'batch_id': request.batch_id,
            'plan_id': plan_id,
            'token_digest': token_digest,
            'state': PLAN_STATE_PREPARED,
            'identity_schema_version': request.identity_schema_version,
            'canonicalization_version': CANONICALIZATION_VERSION,
            'artifact_serialization_version': PREPARED_ARTIFACT_SERIALIZATION_VERSION,
            'request_sha256': server_hash,
            'catalog_sha256': request.catalog_sha256,
            'artifact_sha256': art_sha,
            'chunk_count': len(chunk_records),
            'payload_bytes': payload_bytes,
            'entity_count': len(request.entities),
            'edge_count': len(request.edges),
            'source_count': len(request.provenance.sources) if request.provenance else 0,
            'evidence_link_count': coalesced_evidence_count,
            'created_count': projected_created,
            'updated_count': projected_updated,
            'unchanged_count': projected_unchanged,
            'expires_at': expires_at,
            'created_at': now,
            'updated_at': now,
        }

        try:
            await self._store.ensure_plan_schema(client.driver)
        except Exception as exc:
            logger.error(
                'catalog prepare_catalog_batch schema_failed batch_id=%s reason=%s',
                request.batch_id,
                type(exc).__name__,
            )
            return _fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'prepared plan schema initialization failed',
                plan_uuid=plan_uuid,
                artifact_sha=art_sha,
                expires_at=expires_at_str,
                projected_created=projected_created,
                projected_updated=projected_updated,
                projected_unchanged=projected_unchanged,
            )

        max_active = int(self.catalog_config.max_active_plans_per_group)
        try:
            async with client.driver.transaction() as tx:
                await self._store.create_prepared_plan_with_chunks(
                    tx,
                    plan=plan_params,
                    chunks=chunk_params,
                    max_active=max_active,
                    now=now,
                )
        except CatalogStoreError as exc:
            code_text = getattr(exc, 'code', None) or 'neo4j_transaction_failed'
            try:
                err_code = CatalogErrorCode(code_text)
            except ValueError:
                err_code = CatalogErrorCode.neo4j_transaction_failed
            logger.info(
                'catalog prepare_catalog_batch plan_write_failed batch_id=%s plan_uuid=%s code=%s',
                request.batch_id,
                plan_uuid,
                err_code.value,
            )
            return _fail(
                err_code,
                str(exc) or 'prepared plan write failed',
                plan_uuid=plan_uuid,
                artifact_sha=art_sha,
                expires_at=expires_at_str,
                projected_created=projected_created,
                projected_updated=projected_updated,
                projected_unchanged=projected_unchanged,
            )
        except Exception as exc:
            if self._store._is_uniqueness_constraint_race(exc):
                logger.info(
                    'catalog prepare_catalog_batch uniqueness_race batch_id=%s plan_uuid=%s reason=%s',
                    request.batch_id,
                    plan_uuid,
                    type(exc).__name__,
                )
                return _fail(
                    CatalogErrorCode.prepared_plan_conflict,
                    'prepared plan identity already exists',
                    plan_uuid=plan_uuid,
                    artifact_sha=art_sha,
                    expires_at=expires_at_str,
                    projected_created=projected_created,
                    projected_updated=projected_updated,
                    projected_unchanged=projected_unchanged,
                )
            logger.error(
                'catalog prepare_catalog_batch neo4j_transaction_failed batch_id=%s plan_uuid=%s reason=%s',
                request.batch_id,
                plan_uuid,
                type(exc).__name__,
            )
            return _fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'prepared plan write transaction failed',
                plan_uuid=plan_uuid,
                artifact_sha=art_sha,
                expires_at=expires_at_str,
                projected_created=projected_created,
                projected_updated=projected_updated,
                projected_unchanged=projected_unchanged,
            )

        logger.info(
            'catalog prepare_catalog_batch prepared batch_id=%s plan_uuid=%s entities=%s edges=%s chunks=%s',
            request.batch_id,
            plan_uuid,
            len(request.entities),
            len(request.edges),
            len(chunk_records),
        )
        return PrepareCatalogBatchResponse(
            plan_token=raw_token,
            plan_uuid=plan_uuid,
            request_sha256=server_hash,
            catalog_sha256=request.catalog_sha256,
            artifact_sha256=art_sha,
            identity_schema_version=request.identity_schema_version,
            expires_at=expires_at_str,
            entity_count=len(request.entities),
            edge_count=len(request.edges),
            source_count=len(request.provenance.sources) if request.provenance else 0,
            evidence_link_count=coalesced_evidence_count,
            projected_created=projected_created,
            projected_updated=projected_updated,
            projected_unchanged=projected_unchanged,
        )

    def _map_store_error_code(self, exc: CatalogStoreError) -> CatalogErrorCode:
        code_text = getattr(exc, 'code', None) or 'neo4j_transaction_failed'
        try:
            return CatalogErrorCode(code_text)
        except ValueError:
            return CatalogErrorCode.neo4j_transaction_failed

    def _commit_fail(
        self,
        code: CatalogErrorCode,
        message: str,
        *,
        plan_uuid: str = '',
        request_sha256: str | None = None,
        catalog_sha256: str | None = None,
        artifact_sha256: str | None = None,
        state: str = '',
        entity_count: int = 0,
        edge_count: int = 0,
        source_count: int = 0,
        evidence_link_count: int = 0,
        batch_uuid: str | None = None,
        manifest_sha256: str | None = None,
        committed_created: int = 0,
        committed_updated: int = 0,
        committed_unchanged: int = 0,
    ) -> CommitPreparedCatalogBatchResponse:
        return CommitPreparedCatalogBatchResponse(
            plan_uuid=plan_uuid,
            request_sha256=request_sha256,
            catalog_sha256=catalog_sha256,
            artifact_sha256=artifact_sha256,
            state=state,
            entity_count=entity_count,
            edge_count=edge_count,
            source_count=source_count,
            evidence_link_count=evidence_link_count,
            batch_uuid=batch_uuid,
            manifest_sha256=manifest_sha256,
            committed_created=committed_created,
            committed_updated=committed_updated,
            committed_unchanged=committed_unchanged,
            error_code=code,
            error_message=message,
        )

    def _raise_if_partial_terminal(
        self,
        *,
        snapshot: dict[str, Any] | None,
        projection: dict[str, Any],
    ) -> None:
        """Fail closed on partial/contradictory terminal evidence (D-09/D-11).

        Incomplete success (no durable terminals) returns without raising so the
        full idempotent writer may resume. Never repairs; never revives PREPARED.
        """
        if not snapshot:
            return
        plan_state = str(snapshot.get('plan_state') or '')
        batch_status = str(snapshot.get('batch_status') or '')
        manifest_sha = str(snapshot.get('manifest_sha256') or '')
        expected_manifest = str(projection.get('manifest_sha256') or '')
        has_manifest = bool(manifest_sha)
        has_batch = bool(batch_status)
        has_plan = bool(plan_state)

        if not has_plan and not has_batch and not has_manifest:
            return

        # Fully absent success artifacts under COMMITTING → resume full write.
        if (
            plan_state in {'', PLAN_STATE_COMMITTING}
            and batch_status in {'', 'writing', 'open', 'failed'}
            and not has_manifest
        ):
            return

        if plan_state == PLAN_STATE_COMMITTED:
            if batch_status != 'committed':
                raise self._PartialTerminalConflict(
                    CatalogErrorCode.batch_conflict,
                    'partial terminal: plan COMMITTED without committed batch',
                )
            if not has_manifest:
                raise self._PartialTerminalConflict(
                    CatalogErrorCode.manifest_mismatch,
                    'partial terminal: plan COMMITTED without durable manifest',
                )
            if expected_manifest and manifest_sha != expected_manifest:
                raise self._PartialTerminalConflict(
                    CatalogErrorCode.manifest_mismatch,
                    'partial terminal: manifest_sha256 mismatch',
                )
            for key in (
                'request_sha256',
                'catalog_sha256',
                'identity_schema_version',
            ):
                if str(snapshot.get(key) or '') != str(projection.get(key) or ''):
                    raise self._PartialTerminalConflict(
                        CatalogErrorCode.prepared_plan_conflict,
                        f'partial terminal: {key} mismatch',
                    )
            # Should have agreed already; treat residual as fail-closed.
            raise self._PartialTerminalConflict(
                CatalogErrorCode.prepared_plan_conflict,
                'partial terminal: COMMITTED plan without agreement',
            )

        if batch_status == 'committed':
            raise self._PartialTerminalConflict(
                CatalogErrorCode.batch_conflict,
                'partial terminal: batch committed without plan COMMITTED',
            )
        if has_manifest:
            raise self._PartialTerminalConflict(
                CatalogErrorCode.manifest_mismatch,
                'partial terminal: manifest present without committed agreement',
            )
        if plan_state and plan_state not in {PLAN_STATE_COMMITTING, PLAN_STATE_PREPARED}:
            raise self._PartialTerminalConflict(
                CatalogErrorCode.prepared_plan_conflict,
                'partial terminal: unexpected plan state',
            )

    async def _expected_manifest_sha_from_frozen(
        self,
        *,
        client: Any,
        root: dict[str, Any],
        art_sha: str | None,
    ) -> str | None:
        """Reassemble frozen membership and derive expected manifest digest (CR-02).

        Never uses durable snapshot digest as expected. Failures return None
        so callers fail closed without leaking payload.
        """
        plan_uuid = str(root.get('uuid') or '')
        group_id = str(root.get('group_id') or '')
        batch_id = str(root.get('batch_id') or '')
        request_sha = str(root.get('request_sha256') or '')
        catalog_sha = str(root.get('catalog_sha256') or '')
        if not plan_uuid or not group_id or not batch_id or not request_sha or not catalog_sha:
            return None
        try:
            chunks = await self._store.load_prepared_plan_chunks(
                client.driver,
                plan_uuid=plan_uuid,
                group_id=group_id,
            )
            artifact_bytes = reassemble_artifact_bytes(
                chunks,
                expected_sha256=art_sha,
                expected_length=int(root.get('payload_bytes') or 0) or None,
            )
            artifact = json.loads(artifact_bytes.decode('utf-8'))
            if not isinstance(artifact, dict):
                return None
            membership = artifact.get('membership')
            if not isinstance(membership, dict):
                return None
            body = build_manifest_body_from_membership(
                group_id=group_id,
                batch_id=batch_id,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                membership=membership,
                artifact_sha256=art_sha,
                identity_schema_version=str(
                    root.get('identity_schema_version')
                    or artifact.get('identity_schema_version')
                    or IDENTITY_SCHEMA_VERSION
                ),
                canonicalization_version=str(
                    root.get('canonicalization_version')
                    or artifact.get('canonicalization_version')
                    or CANONICALIZATION_VERSION
                ),
            )
            return pure_manifest_sha256(serialize_manifest_body(body))
        except Exception:
            return None

    async def _commit_terminal_state_receipt(
        self,
        *,
        client: Any,
        root: dict[str, Any],
        plan_uuid: str,
        group_id: str,
        request_sha: str | None,
        catalog_sha: str | None,
        art_sha: str | None,
        entity_count: int,
        edge_count: int,
        source_count: int,
        evidence_link_count: int,
    ) -> CommitPreparedCatalogBatchResponse:
        """Stable receipt when durable plan is already COMMITTED (D-09/D-23).

        Zero domain rewrite. Partial/contradictory evidence fails closed.
        Expected manifest_sha256 is derived from frozen membership (CR-02), not
        from the durable snapshot (which would be tautological).
        """
        batch_id = str(root.get('batch_id') or '')
        namespace = self._namespace()
        if namespace is None or not group_id or not batch_id or not plan_uuid:
            return self._commit_fail(
                CatalogErrorCode.prepared_plan_already_consumed,
                'prepared plan already consumed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTED,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        batch_uuid = catalog_batch_uuid(namespace, group_id, batch_id)
        expected_manifest = await self._expected_manifest_sha_from_frozen(
            client=client,
            root=root,
            art_sha=art_sha,
        )
        if not expected_manifest:
            return self._commit_fail(
                CatalogErrorCode.prepared_plan_already_consumed,
                'prepared plan already consumed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTED,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        snapshot: dict[str, Any] | None = None
        try:
            async with client.driver.transaction() as tx:
                await self._store.lock_prepared_plan_for_commit(
                    tx, plan_uuid=plan_uuid, group_id=group_id
                )
                snapshot = await self._store.read_terminal_commit_snapshot(
                    tx,
                    group_id=group_id,
                    batch_id=batch_id,
                    plan_uuid=plan_uuid,
                    batch_uuid=batch_uuid,
                )
                agree_projection = {
                    'group_id': group_id,
                    'batch_id': batch_id,
                    'batch_uuid': batch_uuid,
                    'plan_uuid': plan_uuid,
                    'request_sha256': str(request_sha or ''),
                    'catalog_sha256': str(catalog_sha or ''),
                    'artifact_sha256': art_sha,
                    'identity_schema_version': str(
                        root.get('identity_schema_version') or IDENTITY_SCHEMA_VERSION
                    ),
                    'manifest_sha256': expected_manifest,
                }
                if snapshot is not None and await self._store.terminal_commit_agrees(
                    tx, projection=agree_projection
                ):
                    # WR-02: durable plan outcome counts are authority for receipt.
                    created = snapshot.get('plan_created_count')
                    updated = snapshot.get('plan_updated_count')
                    unchanged = snapshot.get('plan_unchanged_count')
                    if created is None:
                        created = root.get('created_count')
                    if updated is None:
                        updated = root.get('updated_count')
                    if unchanged is None:
                        unchanged = root.get('unchanged_count')
                    return CommitPreparedCatalogBatchResponse(
                        plan_uuid=plan_uuid,
                        request_sha256=request_sha,
                        catalog_sha256=catalog_sha,
                        artifact_sha256=art_sha,
                        state=PLAN_STATE_COMMITTED,
                        entity_count=entity_count,
                        edge_count=edge_count,
                        source_count=source_count,
                        evidence_link_count=evidence_link_count,
                        batch_uuid=batch_uuid,
                        manifest_sha256=expected_manifest,
                        committed_created=int(created or 0),
                        committed_updated=int(updated or 0),
                        committed_unchanged=int(unchanged or 0),
                    )
        except CatalogStoreError as exc:
            return self._commit_fail(
                self._map_store_error_code(exc),
                str(exc) or 'terminal receipt read failed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTED,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        except Exception as exc:
            logger.error(
                'catalog commit_prepared_catalog_batch terminal_receipt_failed '
                'plan_uuid=%s reason=%s',
                plan_uuid,
                type(exc).__name__,
            )
            return self._commit_fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'terminal receipt read failed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTED,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )

        # Partial terminal under COMMITTED root: fail closed, no rewrite.
        try:
            self._raise_if_partial_terminal(
                snapshot=snapshot,
                projection={
                    'group_id': group_id,
                    'batch_id': batch_id,
                    'batch_uuid': batch_uuid,
                    'plan_uuid': plan_uuid,
                    'request_sha256': str(request_sha or ''),
                    'catalog_sha256': str(catalog_sha or ''),
                    'artifact_sha256': art_sha,
                    'identity_schema_version': str(
                        root.get('identity_schema_version') or IDENTITY_SCHEMA_VERSION
                    ),
                    'manifest_sha256': expected_manifest,
                },
            )
        except self._PartialTerminalConflict as exc:
            return self._commit_fail(
                exc.code,
                exc.message,
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTED,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
                batch_uuid=batch_uuid,
            )
        return self._commit_fail(
            CatalogErrorCode.prepared_plan_already_consumed,
            'prepared plan already consumed',
            plan_uuid=plan_uuid,
            request_sha256=request_sha,
            catalog_sha256=catalog_sha,
            artifact_sha256=art_sha,
            state=PLAN_STATE_COMMITTED,
            entity_count=entity_count,
            edge_count=edge_count,
            source_count=source_count,
            evidence_link_count=evidence_link_count,
            batch_uuid=batch_uuid,
        )

    def _discard_fail(
        self,
        code: CatalogErrorCode,
        message: str,
        *,
        plan_uuid: str | None = None,
        state: str = '',
    ) -> DiscardPreparedCatalogBatchResponse:
        return DiscardPreparedCatalogBatchResponse(
            plan_uuid=plan_uuid,
            state=state,
            error_code=code,
            error_message=message,
        )

    def _verify_frozen_plan_binding(
        self,
        root: dict[str, Any],
        artifact: dict[str, Any],
        *,
        expected_request_sha256: str | None,
    ) -> str | None:
        """Return conflict message if root/artifact binding fails; None if ok (D-21)."""
        root_group = str(root.get('group_id') or '')
        art_group = str(artifact.get('group_id') or '')
        root_batch = str(root.get('batch_id') or '')
        art_batch = str(artifact.get('batch_id') or '')
        root_req = str(root.get('request_sha256') or '')
        art_req = str(artifact.get('request_sha256') or '')
        root_cat = str(root.get('catalog_sha256') or '')
        art_cat = str(artifact.get('catalog_sha256') or '')
        root_art = str(root.get('artifact_sha256') or '')
        root_id_ver = str(root.get('identity_schema_version') or '')
        art_id_ver = str(artifact.get('identity_schema_version') or '')
        root_canon = str(root.get('canonicalization_version') or '')
        art_canon = str(artifact.get('canonicalization_version') or '')
        root_art_ver = str(root.get('artifact_serialization_version') or '')
        art_art_ver = str(artifact.get('artifact_serialization_version') or '')
        art_cat_ver = str(artifact.get('catalog_schema_version') or '')

        if root_group != art_group:
            return 'plan group_id binding mismatch'
        if root_batch != art_batch:
            return 'plan batch_id binding mismatch'
        if root_req != art_req or not root_req:
            return 'plan request_sha256 binding mismatch'
        if root_cat != art_cat or not root_cat:
            return 'plan catalog_sha256 binding mismatch'
        if root_id_ver != art_id_ver or root_id_ver != IDENTITY_SCHEMA_VERSION:
            return 'plan identity_schema_version binding mismatch'
        if root_canon != art_canon or root_canon != CANONICALIZATION_VERSION:
            return 'plan canonicalization_version binding mismatch'
        if root_art_ver != art_art_ver or root_art_ver != PREPARED_ARTIFACT_SERIALIZATION_VERSION:
            return 'plan artifact_serialization_version binding mismatch'
        if art_cat_ver != CATALOG_SCHEMA_VERSION:
            return 'plan catalog_schema_version binding mismatch'
        if expected_request_sha256 is not None and expected_request_sha256 != root_req:
            return 'expected_request_sha256 mismatch'
        if not root_art:
            return 'plan artifact_sha256 missing'

        raw_counts = artifact.get('counts')
        counts: dict[str, Any] = raw_counts if isinstance(raw_counts, dict) else {}
        if int(root.get('entity_count') or 0) != int(counts.get('entities') or 0):
            return 'plan entity_count mismatch'
        if int(root.get('edge_count') or 0) != int(counts.get('edges') or 0):
            return 'plan edge_count mismatch'
        if int(root.get('source_count') or 0) != int(counts.get('sources') or 0):
            return 'plan source_count mismatch'
        if int(root.get('evidence_link_count') or 0) != int(counts.get('evidence_links') or 0):
            return 'plan evidence_link_count mismatch'
        return None

    async def commit_prepared_catalog_batch(
        self,
        *,
        client: Any,
        request: CommitPreparedCatalogBatchRequest,
    ) -> CommitPreparedCatalogBatchResponse:
        """Token-only claim/load seam: verify frozen plan, CAS → COMMITTING (PLAN-10/11/12).

        Digest is a locator only. Authorization is post-load plan_token_matches
        (hmac.compare_digest). Stops at COMMITTING — zero domain/embedder/LLM/queue/HTTP.
        """
        raw_token = request.plan_token
        try:
            token_digest = plan_token_digest(raw_token)
        except ValueError:
            return self._commit_fail(
                CatalogErrorCode.prepared_plan_not_found,
                'prepared plan not found',
            )

        try:
            root = await self._store.load_prepared_plan_by_token_digest(
                client.driver,
                token_digest=token_digest,
            )
        except CatalogStoreError as exc:
            return self._commit_fail(
                self._map_store_error_code(exc),
                str(exc) or 'prepared plan load failed',
            )
        except Exception as exc:
            logger.error(
                'catalog commit_prepared_catalog_batch load_failed reason=%s',
                type(exc).__name__,
            )
            return self._commit_fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'prepared plan load failed',
            )

        if root is None:
            return self._commit_fail(
                CatalogErrorCode.prepared_plan_not_found,
                'prepared plan not found',
            )

        stored_digest = str(root.get('token_digest') or '')
        if not plan_token_matches(raw_token, stored_digest):
            return self._commit_fail(
                CatalogErrorCode.prepared_plan_not_found,
                'prepared plan not found',
            )

        plan_uuid = str(root.get('uuid') or '')
        group_id = str(root.get('group_id') or '')
        request_sha = str(root.get('request_sha256') or '') or None
        catalog_sha = str(root.get('catalog_sha256') or '') or None
        art_sha = str(root.get('artifact_sha256') or '') or None
        entity_count = int(root.get('entity_count') or 0)
        edge_count = int(root.get('edge_count') or 0)
        source_count = int(root.get('source_count') or 0)
        evidence_link_count = int(root.get('evidence_link_count') or 0)
        state = str(root.get('state') or '')

        def _echo_fail(code: CatalogErrorCode, message: str) -> CommitPreparedCatalogBatchResponse:
            return self._commit_fail(
                code,
                message,
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=state,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )

        if state == PLAN_STATE_DISCARDED:
            return _echo_fail(
                CatalogErrorCode.prepared_plan_not_found,
                'prepared plan not found',
            )
        if state == PLAN_STATE_COMMITTED:
            # D-09/D-23: terminal agreement → stable receipt; partial → fail closed.
            return await self._commit_terminal_state_receipt(
                client=client,
                root=root,
                plan_uuid=plan_uuid,
                group_id=group_id,
                request_sha=request_sha,
                catalog_sha=catalog_sha,
                art_sha=art_sha,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        if state == PLAN_STATE_EXPIRED:
            return _echo_fail(
                CatalogErrorCode.prepared_plan_expired,
                'prepared plan expired',
            )
        if state not in {PLAN_STATE_PREPARED, PLAN_STATE_COMMITTING}:
            return _echo_fail(
                CatalogErrorCode.prepared_plan_conflict,
                'prepared plan not claimable',
            )

        now = datetime.now(timezone.utc)
        expires_at = root.get('expires_at')
        if state == PLAN_STATE_PREPARED and expires_at is not None and now >= expires_at:
            try:
                async with client.driver.transaction() as tx:
                    await self._store.cas_plan_state(
                        tx,
                        token_digest=token_digest,
                        expected_from=PLAN_STATE_PREPARED,
                        to_state=PLAN_STATE_EXPIRED,
                        updated_at=now,
                        now=now,
                    )
            except CatalogStoreError as exc:
                code = self._map_store_error_code(exc)
                if code == CatalogErrorCode.prepared_plan_expired:
                    return _echo_fail(code, str(exc) or 'prepared plan expired')
                # Race: still report expired for due PREPARED plans.
                return _echo_fail(
                    CatalogErrorCode.prepared_plan_expired,
                    'prepared plan expired',
                )
            except Exception as exc:
                logger.error(
                    'catalog commit_prepared_catalog_batch expire_failed plan_uuid=%s reason=%s',
                    plan_uuid,
                    type(exc).__name__,
                )
                return _echo_fail(
                    CatalogErrorCode.neo4j_transaction_failed,
                    'prepared plan expiry update failed',
                )
            return _echo_fail(
                CatalogErrorCode.prepared_plan_expired,
                'prepared plan expired',
            )

        if not group_id or not plan_uuid:
            return _echo_fail(
                CatalogErrorCode.prepared_plan_conflict,
                'prepared plan missing scope identity',
            )

        try:
            chunks = await self._store.load_prepared_plan_chunks(
                client.driver,
                plan_uuid=plan_uuid,
                group_id=group_id,
            )
        except CatalogStoreError as exc:
            return _echo_fail(
                self._map_store_error_code(exc),
                str(exc) or 'prepared plan chunk load failed',
            )
        except Exception as exc:
            logger.error(
                'catalog commit_prepared_catalog_batch chunks_failed plan_uuid=%s reason=%s',
                plan_uuid,
                type(exc).__name__,
            )
            return _echo_fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'prepared plan chunk load failed',
            )

        expected_chunk_count = int(root.get('chunk_count') or 0)
        if expected_chunk_count and len(chunks) != expected_chunk_count:
            return _echo_fail(
                CatalogErrorCode.prepared_plan_conflict,
                'prepared plan chunk count mismatch',
            )

        try:
            artifact_bytes = reassemble_artifact_bytes(
                chunks,
                expected_sha256=art_sha,
                expected_length=int(root.get('payload_bytes') or 0) or None,
            )
            artifact = json.loads(artifact_bytes.decode('utf-8'))
            if not isinstance(artifact, dict):
                raise ValueError('artifact body must be object')
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return _echo_fail(
                CatalogErrorCode.prepared_plan_conflict,
                f'prepared plan artifact reassembly failed: {exc}',
            )

        binding_err = self._verify_frozen_plan_binding(
            root,
            artifact,
            expected_request_sha256=request.expected_request_sha256,
        )
        if binding_err is not None:
            return _echo_fail(
                CatalogErrorCode.prepared_plan_conflict,
                binding_err,
            )

        expected_from = (
            PLAN_STATE_COMMITTING if state == PLAN_STATE_COMMITTING else PLAN_STATE_PREPARED
        )
        try:
            async with client.driver.transaction() as tx:
                claimed = await self._store.cas_plan_state(
                    tx,
                    token_digest=token_digest,
                    expected_from=expected_from,
                    to_state=PLAN_STATE_COMMITTING,
                    updated_at=now,
                    now=now,
                    require_not_expired=True,
                )
        except CatalogStoreError as exc:
            # WR-01: winner reached COMMITTED during claim → stable terminal receipt.
            if getattr(exc, 'code', None) == 'prepared_plan_already_consumed':
                try:
                    latest = await self._store.load_prepared_plan_by_token_digest(
                        client.driver,
                        token_digest=token_digest,
                    )
                except Exception:
                    latest = None
                receipt_root = latest if isinstance(latest, dict) else root
                return await self._commit_terminal_state_receipt(
                    client=client,
                    root=receipt_root,
                    plan_uuid=str(receipt_root.get('uuid') or plan_uuid),
                    group_id=str(receipt_root.get('group_id') or group_id),
                    request_sha=str(receipt_root.get('request_sha256') or '') or request_sha,
                    catalog_sha=str(receipt_root.get('catalog_sha256') or '') or catalog_sha,
                    art_sha=str(receipt_root.get('artifact_sha256') or '') or art_sha,
                    entity_count=int(receipt_root.get('entity_count') or entity_count),
                    edge_count=int(receipt_root.get('edge_count') or edge_count),
                    source_count=int(receipt_root.get('source_count') or source_count),
                    evidence_link_count=int(
                        receipt_root.get('evidence_link_count') or evidence_link_count
                    ),
                )
            return _echo_fail(
                self._map_store_error_code(exc),
                str(exc) or 'prepared plan claim failed',
            )
        except Exception as exc:
            logger.error(
                'catalog commit_prepared_catalog_batch cas_failed plan_uuid=%s reason=%s',
                plan_uuid,
                type(exc).__name__,
            )
            return _echo_fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'prepared plan claim transaction failed',
            )

        logger.info(
            'catalog commit_prepared_catalog_batch claimed plan_uuid=%s state=%s reentry=%s',
            plan_uuid,
            PLAN_STATE_COMMITTING,
            bool(claimed.get('reentry')),
        )

        # Success path: frozen artifact projection + one atomic writer (D-01/D-06/D-26).
        # Zero embedder/LLM/queue/HTTP after claim.
        namespace = self._namespace()
        if namespace is None:
            return _echo_fail(
                CatalogErrorCode.invalid_uuid_namespace,
                'uuid_namespace missing or invalid',
            )

        try:
            await self._ensure_schema(client)
            await self._store.ensure_plan_schema(client.driver)
        except Exception as exc:
            logger.error(
                'catalog commit_prepared_catalog_batch schema_failed plan_uuid=%s reason=%s',
                plan_uuid,
                type(exc).__name__,
            )
            return self._commit_fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'catalog schema initialization failed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTING,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )

        request_ts = datetime.now(timezone.utc)
        try:
            projection = self._build_projection_from_artifact(
                artifact=artifact,
                root=root,
                token_digest=token_digest,
                request_ts=request_ts,
                namespace=namespace,
            )
        except CatalogStoreError as exc:
            return self._commit_fail(
                self._map_store_error_code(exc),
                str(exc) or 'prepared projection build failed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTING,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        except Exception as exc:
            logger.error(
                'catalog commit_prepared_catalog_batch projection_failed plan_uuid=%s reason=%s',
                plan_uuid,
                type(exc).__name__,
            )
            return self._commit_fail(
                CatalogErrorCode.prepared_plan_conflict,
                'prepared projection build failed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTING,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )

        async def _record_failed_status(error_summary: str) -> None:
            # D-27: separate post-rollback tx only; never plan COMMITTED / manifest.
            failed_params = self._store.prepare_batch_status_params(
                uuid=projection.batch_uuid,
                group_id=projection.group_id,
                batch_id=projection.batch_id,
                status='failed',
                request_sha256=projection.request_sha256,
                catalog_sha256=projection.catalog_sha256,
                entity_count=projection.entity_count,
                edge_count=projection.edge_count,
                provenance_count=projection.provenance_count,
                created_at=request_ts,
                updated_at=datetime.now(timezone.utc),
                error_summary=error_summary,
            )
            try:
                async with client.driver.transaction() as status_tx:
                    await self._store.upsert_batch_status(status_tx, params=failed_params)
            except Exception as status_exc:
                logger.error(
                    'catalog commit_prepared_catalog_batch failed_status_write_failed '
                    'plan_uuid=%s reason=%s',
                    plan_uuid,
                    type(status_exc).__name__,
                )

        try:
            async with client.driver.transaction() as tx:
                write_out = await self._write_catalog_batch_atomic(tx, projection)
        except self._PartialTerminalConflict as exc:
            # D-09/D-11: leave plan COMMITTING; no PREPARED revival; no silent repair.
            return self._commit_fail(
                exc.code,
                exc.message,
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTING,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        except self._BatchStatusConflict as exc:
            if exc.reason == 'already_committed':
                # Partial terminal or competing writer left batch committed without agreement.
                return self._commit_fail(
                    CatalogErrorCode.batch_conflict,
                    'batch already committed with conflicting terminal state',
                    plan_uuid=plan_uuid,
                    request_sha256=request_sha,
                    catalog_sha256=catalog_sha,
                    artifact_sha256=art_sha,
                    state=PLAN_STATE_COMMITTING,
                    entity_count=entity_count,
                    edge_count=edge_count,
                    source_count=source_count,
                    evidence_link_count=evidence_link_count,
                )
            return self._commit_fail(
                CatalogErrorCode.batch_conflict,
                'batch_id has different request_sha256',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTING,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        except CatalogStoreError as exc:
            await _record_failed_status(getattr(exc, 'code', None) or type(exc).__name__)
            return self._commit_fail(
                self._map_store_error_code(exc),
                str(exc) or 'catalog commit write failed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTING,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        except (
            self._EntityInvariantRace,
            self._EdgeEndpointRace,
            self._ProvenanceInvariantRace,
        ) as exc:
            code = getattr(exc, 'code', CatalogErrorCode.neo4j_transaction_failed)
            await _record_failed_status(getattr(code, 'value', str(code)))
            return self._commit_fail(
                code if isinstance(code, CatalogErrorCode) else CatalogErrorCode.batch_conflict,
                'catalog commit invariant conflict',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTING,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )
        except Exception as exc:
            logger.error(
                'catalog commit_prepared_catalog_batch write_failed plan_uuid=%s reason=%s',
                plan_uuid,
                type(exc).__name__,
            )
            await _record_failed_status(type(exc).__name__)
            return self._commit_fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'neo4j transaction failed',
                plan_uuid=plan_uuid,
                request_sha256=request_sha,
                catalog_sha256=catalog_sha,
                artifact_sha256=art_sha,
                state=PLAN_STATE_COMMITTING,
                entity_count=entity_count,
                edge_count=edge_count,
                source_count=source_count,
                evidence_link_count=evidence_link_count,
            )

        # WR-02: prefer durable/outcome counts returned by writer (first == replay).
        if write_out.get('committed_created') is not None or write_out.get('short_circuit'):
            committed_created = int(write_out.get('committed_created') or 0)
            committed_updated = int(write_out.get('committed_updated') or 0)
            committed_unchanged = int(write_out.get('committed_unchanged') or 0)
        else:
            entity_results = list(write_out.get('entity_results') or [])
            edge_results = list(write_out.get('edge_results') or [])
            provenance_results = list(write_out.get('provenance_results') or [])
            all_results = entity_results + edge_results + provenance_results
            committed_created = sum(r.status == 'created' for r in all_results)
            committed_updated = sum(r.status == 'updated' for r in all_results)
            committed_unchanged = sum(r.status == 'unchanged' for r in all_results)

        logger.info(
            'catalog commit_prepared_catalog_batch committed plan_uuid=%s batch_id=%s '
            'entities=%s edges=%s sources=%s evidence=%s short_circuit=%s',
            plan_uuid,
            projection.batch_id,
            entity_count,
            edge_count,
            source_count,
            evidence_link_count,
            bool(write_out.get('short_circuit')),
        )
        return CommitPreparedCatalogBatchResponse(
            plan_uuid=plan_uuid,
            request_sha256=request_sha,
            catalog_sha256=catalog_sha,
            artifact_sha256=art_sha,
            state=PLAN_STATE_COMMITTED,
            entity_count=entity_count,
            edge_count=edge_count,
            source_count=source_count,
            evidence_link_count=evidence_link_count,
            batch_uuid=str(write_out.get('batch_uuid') or projection.batch_uuid),
            manifest_sha256=str(write_out.get('manifest_sha256') or '') or None,
            committed_created=committed_created,
            committed_updated=committed_updated,
            committed_unchanged=committed_unchanged,
        )

    async def discard_prepared_catalog_batch(
        self,
        *,
        client: Any,
        request: DiscardPreparedCatalogBatchRequest,
    ) -> DiscardPreparedCatalogBatchResponse:
        """Token-only discard: PREPARED→DISCARDED idempotent; no domain deletes (PLAN-19)."""
        raw_token = request.plan_token
        try:
            token_digest = plan_token_digest(raw_token)
        except ValueError:
            return self._discard_fail(
                CatalogErrorCode.prepared_plan_not_found,
                'prepared plan not found',
            )

        try:
            root = await self._store.load_prepared_plan_by_token_digest(
                client.driver,
                token_digest=token_digest,
            )
        except CatalogStoreError as exc:
            return self._discard_fail(
                self._map_store_error_code(exc),
                str(exc) or 'prepared plan load failed',
            )
        except Exception as exc:
            logger.error(
                'catalog discard_prepared_catalog_batch load_failed reason=%s',
                type(exc).__name__,
            )
            return self._discard_fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'prepared plan load failed',
            )

        if root is None:
            return self._discard_fail(
                CatalogErrorCode.prepared_plan_not_found,
                'prepared plan not found',
            )

        stored_digest = str(root.get('token_digest') or '')
        if not plan_token_matches(raw_token, stored_digest):
            return self._discard_fail(
                CatalogErrorCode.prepared_plan_not_found,
                'prepared plan not found',
            )

        plan_uuid = str(root.get('uuid') or '') or None
        state = str(root.get('state') or '')

        if state in {PLAN_STATE_COMMITTING, PLAN_STATE_COMMITTED}:
            return self._discard_fail(
                CatalogErrorCode.prepared_plan_conflict,
                'cannot discard committing/committed plan',
                plan_uuid=plan_uuid,
                state=state,
            )
        if state == PLAN_STATE_EXPIRED:
            return self._discard_fail(
                CatalogErrorCode.prepared_plan_expired,
                'prepared plan expired',
                plan_uuid=plan_uuid,
                state=state,
            )
        if state not in {PLAN_STATE_PREPARED, PLAN_STATE_DISCARDED}:
            return self._discard_fail(
                CatalogErrorCode.prepared_plan_conflict,
                'prepared plan not discardable',
                plan_uuid=plan_uuid,
                state=state,
            )

        now = datetime.now(timezone.utc)
        # Store CAS table only allows PREPARED→DISCARDED; already-DISCARDED is
        # handled as an idempotent success inside cas_plan_state (PLAN-19).
        try:
            async with client.driver.transaction() as tx:
                discarded = await self._store.cas_plan_state(
                    tx,
                    token_digest=token_digest,
                    expected_from=PLAN_STATE_PREPARED,
                    to_state=PLAN_STATE_DISCARDED,
                    updated_at=now,
                    now=now,
                )
        except CatalogStoreError as exc:
            return self._discard_fail(
                self._map_store_error_code(exc),
                str(exc) or 'prepared plan discard failed',
                plan_uuid=plan_uuid,
                state=state,
            )
        except Exception as exc:
            logger.error(
                'catalog discard_prepared_catalog_batch cas_failed plan_uuid=%s reason=%s',
                plan_uuid,
                type(exc).__name__,
            )
            return self._discard_fail(
                CatalogErrorCode.neo4j_transaction_failed,
                'prepared plan discard transaction failed',
                plan_uuid=plan_uuid,
                state=state,
            )

        logger.info(
            'catalog discard_prepared_catalog_batch discarded plan_uuid=%s idempotent=%s',
            plan_uuid,
            bool(discarded.get('idempotent')),
        )
        return DiscardPreparedCatalogBatchResponse(
            plan_uuid=plan_uuid or str(discarded.get('uuid') or '') or None,
            state=PLAN_STATE_DISCARDED,
        )

    class _BatchStatusConflict(Exception):
        def __init__(self, reason: str):
            self.reason = reason
            super().__init__(reason)

    class _PartialTerminalConflict(Exception):
        """D-09/D-11: partial or contradictory terminal evidence; fail closed."""

        def __init__(self, code: CatalogErrorCode, message: str):
            self.code = code
            self.message = message
            super().__init__(message)

    async def _batch_recheck_edge_in_tx(
        self,
        tx: Any,
        prep: _PreparedEdge,
        request: UpsertCatalogBatchRequest,
        request_entity_uuids: dict[tuple[str, str], str],
        written_request_entities: set[str],
    ) -> dict[str, Any] | None:
        """Recheck persisted endpoints and return the transaction-local edge row."""
        for entity_type, graph_key, expected_uuid in (
            (prep.item.source_entity_type, prep.item.source_graph_key, prep.source_uuid),
            (prep.item.target_entity_type, prep.item.target_graph_key, prep.target_uuid),
        ):
            if (entity_type, graph_key) in request_entity_uuids:
                if expected_uuid in written_request_entities:
                    continue
                row = await self._store.get_entity_by_uuid(
                    None,
                    uuid=expected_uuid or '',
                    group_id=request.group_id,
                    tx=tx,
                )
                if row is None:
                    raise self._EdgeEndpointRace(CatalogErrorCode.missing_endpoint)
                continue
            code, row = await self._store.resolve_endpoint_typed(
                None,
                group_id=request.group_id,
                graph_key=graph_key,
                entity_type=entity_type,
                tx=tx,
                expected_uuid=expected_uuid,
            )
            if code is not None or row is None or str(row.get('uuid')) != expected_uuid:
                raise self._EdgeEndpointRace(self._endpoint_error_code(code or 'missing_endpoint'))
        existing = await self._store.get_edge_by_uuid(
            None,
            uuid=prep.edge_uuid,
            group_id=request.group_id,
            tx=tx,
        )
        if existing is not None and self._store.detect_edge_identity_conflict(
            existing,
            edge_type=prep.item.edge_type,
            edge_key=prep.item.edge_key,
            source_uuid=prep.source_uuid or '',
            target_uuid=prep.target_uuid or '',
        ):
            raise self._EdgeEndpointRace(CatalogErrorCode.edge_identity_conflict)
        return existing
