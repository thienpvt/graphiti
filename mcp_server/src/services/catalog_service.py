"""CatalogService: deterministic typed catalog entity upsert orchestration.

Order: validate → uuid5+hash → coalesce → embed → open tx (if not dry_run).
No LLM, no queue, no EntityNode.save.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.schema import CatalogConfig
from models.catalog_batch import GetCatalogIngestStatusRequest, UpsertCatalogBatchRequest
from models.catalog_common import CatalogErrorCode
from models.catalog_edges import CatalogEdgeItem, UpsertTypedEdgesRequest
from models.catalog_entities import (
    CatalogEntityItem,
    ResolveEntityRef,
    ResolveTypedEntitiesRequest,
    UpsertTypedEntitiesRequest,
    VerifyCatalogBatchRequest,
)
from models.catalog_provenance import CatalogSourceItem, UpsertProvenanceRequest
from models.catalog_responses import (
    CatalogBatchWriteResponse,
    CatalogIngestStatus,
    CatalogIngestStatusResponse,
    CatalogItemResult,
    CatalogWriteResponse,
    ResolveEntityResult,
    ResolveTypedEntitiesResponse,
    VerifyCatalogBatchResponse,
    VerifyEdgeSection,
    VerifyEntitySection,
)
from services.catalog_identity import (
    assert_optional_client_hash,
    canonical_sha256,
    catalog_batch_uuid,
    catalog_edge_uuid,
    catalog_entity_uuid,
    catalog_mentions_uuid,
    catalog_source_uuid,
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
    missing_links: bool = False  # True when any MENTIONS/episode attach still needed
    coalesced_indices: list[int] = field(default_factory=list)


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
        return {
            'entity_type': item.entity_type,
            'graph_key': item.graph_key,
            'name_raw': item.name_raw,
            'name_canonical': item.name_canonical,
            'database_qualified_name': item.database_qualified_name,
            'summary': item.summary,
            'attributes': item.attributes,
            'source_refs': item.source_refs,
            'confidence': item.confidence,
        }

    @staticmethod
    def edge_canonical_payload(item: CatalogEdgeItem) -> dict[str, Any]:
        """Mutable canonical fields used for edge content_sha256 (identity excluded)."""
        return {
            'edge_type': item.edge_type,
            'edge_key': item.edge_key,
            'source_graph_key': item.source_graph_key,
            'source_entity_type': item.source_entity_type,
            'target_graph_key': item.target_graph_key,
            'target_entity_type': item.target_entity_type,
            'fact': item.fact,
            'evidence': item.evidence,
            'attributes': item.attributes,
            'confidence': item.confidence,
        }

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
            if ent_uuid in identity_to_prep:
                prior = identity_to_prep[ent_uuid]
                if prior.content_sha256 != digest:
                    # same identity, different payload → conflict for both
                    for i in [prior.index, *prior.coalesced_indices, idx]:
                        it = request.entities[i]
                        early_errors[i] = CatalogItemResult(
                            index=i,
                            status='error',
                            uuid=ent_uuid,
                            graph_key=it.graph_key,
                            entity_type=it.entity_type,
                            error_code=CatalogErrorCode.deterministic_uuid_conflict,
                            error_message='same identity different canonical payload in request',
                        )
                    # remove prior from prepared write set
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
    def _write_status_from_row(row: dict[str, Any], projected: str) -> str:
        """Prefer DB-captured write status; fall back to projected only if absent."""
        status = row.get('status')
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
        embedding = prep.name_embedding or []
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
            source_refs=item.source_refs,
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
        # Allow graph_keys-only convenience when entities empty (optional).
        if not refs and request.graph_keys:
            # Without entity_type we cannot fully resolve; treat as validation.
            return ResolveTypedEntitiesResponse(
                group_id=request.group_id,
                results=[
                    ResolveEntityResult(
                        index=0,
                        entity_type='',
                        graph_key='',
                        status='error',
                        found=False,
                        error_code=CatalogErrorCode.validation_error,
                        error_message='entities with entity_type required for resolve',
                        anomalies=['validation_error'],
                    )
                ],
            )

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
                'catalog resolve_typed_entities gated group_id=%s count=%s code=%s',
                request.group_id,
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
                'catalog resolve_typed_entities read_failed group_id=%s count=%s reason=%s',
                request.group_id,
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
            'catalog resolve_typed_entities group_id=%s count=%s found=%s',
            request.group_id,
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
                'catalog verify_catalog_batch gated group_id=%s batch_id=%s code=%s',
                request.group_id,
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
                'catalog verify_catalog_batch read_failed group_id=%s batch_id=%s reason=%s',
                request.group_id,
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
                    'catalog verify_catalog_batch provenance_read_failed group_id=%s '
                    'batch_id=%s reason=%s',
                    request.group_id,
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
            'catalog verify_catalog_batch group_id=%s batch_id=%s entities=%s edges=%s',
            request.group_id,
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
                            (edge.expected_source_graph_key, 'source_graph_key'),
                            (edge.expected_target_graph_key, 'target_graph_key'),
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
        early_errors: dict[int, CatalogItemResult] = {}

        # 1) identity + hash + coalesce
        for idx, item in enumerate(request.edges):
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
            if edge_uuid in identity_to_prep:
                prior = identity_to_prep[edge_uuid]
                if prior.content_sha256 != digest:
                    for i in [prior.index, *prior.coalesced_indices, idx]:
                        it = request.edges[i]
                        early_errors[i] = CatalogItemResult(
                            index=i,
                            status='error',
                            uuid=edge_uuid,
                            edge_key=it.edge_key,
                            edge_type=it.edge_type,
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
        embedding = prep.fact_embedding or []
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
                    status = self._write_status_from_row(row, prep.projected_status)
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
                    status = self._write_status_from_row(row, prep.projected_status)
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
        return {
            'source_key': item.source_key,
            'reference_time': item.reference_time,
            'attributes': item.attributes,
            'metadata': item.metadata,
        }

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
                valid_at = self._parse_source_valid_at(item.reference_time)
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
            if existing is not None and existing.get('content_sha256') == prep.content_sha256:
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
                        break
                if prep.index in early_errors:
                    continue
                if not missing_links:
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
                            break
                if prep.index in early_errors:
                    continue
                if not missing_links:
                    prep.projected_status = 'unchanged'
                else:
                    prep.projected_status = 'updated'
                    prep.missing_links = True
            elif existing is None:
                prep.projected_status = 'created'
                prep.missing_links = bool(prep.entity_uuids or prep.edge_uuids)
            else:
                prep.projected_status = 'updated'
                prep.missing_links = True

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

        try:
            async with client.driver.transaction() as tx:
                for prep in prepared:
                    if prep.index in early_errors:
                        continue
                    if prep.projected_status == 'unchanged' and not prep.missing_links:
                        written[prep.index] = self._source_result(prep, prep.index, 'unchanged')
                        for index in prep.coalesced_indices:
                            written[index] = self._source_result(prep, index, 'unchanged')
                        continue
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
                        entity_edges=list(prep.edge_uuids),
                        name=prep.item.source_key,
                    )
                    row = await self._store.upsert_source_episode(tx, params=params)
                    status = str(row.get('status') or prep.projected_status)
                    if prep.missing_links and status == 'unchanged':
                        status = 'updated'
                    for ent_uuid, men_uuid in zip(
                        prep.entity_uuids, prep.mentions_uuids, strict=True
                    ):
                        await self._store.upsert_mentions_link(
                            tx,
                            episode_uuid=prep.source_uuid,
                            entity_uuid=ent_uuid,
                            mentions_uuid=men_uuid,
                            group_id=request.group_id,
                            created_at=request_ts,
                        )
                    for edge_uuid in prep.edge_uuids:
                        await self._store.append_edge_episode(
                            tx,
                            edge_uuid=edge_uuid,
                            episode_uuid=prep.source_uuid,
                            group_id=request.group_id,
                        )
                    written[prep.index] = self._source_result(prep, prep.index, status)
                    for index in prep.coalesced_indices:
                        written[index] = self._source_result(prep, index, status)
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
                'catalog get_catalog_ingest_status gated group_id=%s batch_id=%s code=%s',
                group_id,
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
                'catalog get_catalog_ingest_status read_failed group_id=%s batch_id=%s reason=%s',
                group_id,
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
                'catalog get_catalog_ingest_status missing group_id=%s batch_id=%s',
                group_id,
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
            'catalog get_catalog_ingest_status group_id=%s batch_id=%s status=%s',
            group_id,
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
        """Canonical nested request without caller hashes or execution flags."""
        provenance = request.provenance
        return {
            'group_id': request.group_id,
            'batch_id': request.batch_id,
            'entities': [
                CatalogService.entity_canonical_payload(item) for item in request.entities
            ],
            'edges': [CatalogService.edge_canonical_payload(item) for item in request.edges],
            'provenance': (
                {
                    'sources': [
                        CatalogService.source_canonical_payload(item) for item in provenance.sources
                    ],
                    'entity_targets': [
                        target.model_dump(mode='json') for target in provenance.entity_targets
                    ],
                    'edge_targets': [
                        target.model_dump(mode='json') for target in provenance.edge_targets
                    ],
                }
                if provenance is not None
                else None
            ),
        }

    @staticmethod
    def batch_request_sha256(request: UpsertCatalogBatchRequest) -> str:
        """Server-authoritative hash for batch-idempotency checks."""
        return canonical_sha256(CatalogService._batch_canonical_payload(request))

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
        limits = (
            (
                len(request.entities),
                self.catalog_config.max_entities_per_batch,
                'entities',
            ),
            (len(request.edges), self.catalog_config.max_edges_per_batch, 'edges'),
            (
                (
                    len(request.provenance.sources)
                    * (
                        len(request.provenance.entity_targets)
                        + len(request.provenance.edge_targets)
                    )
                    if request.provenance is not None
                    else 0
                ),
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

    async def upsert_catalog_batch(
        self,
        *,
        client: Any,
        request: UpsertCatalogBatchRequest,
    ) -> CatalogBatchWriteResponse:
        """Preflight a nested deterministic catalog batch before any embedding/write."""
        namespace = self._namespace()
        batch_uuid = (
            catalog_batch_uuid(namespace, request.group_id, request.batch_id)
            if namespace is not None
            else None
        )
        gate = self._batch_gate_error(client, request)
        if gate is not None:
            code, message = gate
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=request.dry_run,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=code,
                error_message=message,
            )
        assert namespace is not None and batch_uuid is not None

        server_hash = self.batch_request_sha256(request)
        try:
            assert_optional_client_hash(request.request_sha256, server_hash)
        except ValueError as exc:
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=request.dry_run,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=CatalogErrorCode.content_hash_mismatch,
                error_message=str(exc),
            )
        effective_hash = server_hash

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
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=request.dry_run,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=CatalogErrorCode.internal_error,
                error_message='batch status pre-read failed',
            )
        if prior_status is not None and prior_status.get('status') == 'committed':
            if prior_status.get('request_sha256') == effective_hash:
                return CatalogBatchWriteResponse(
                    group_id=request.group_id,
                    batch_id=request.batch_id,
                    batch_uuid=batch_uuid,
                    dry_run=request.dry_run,
                    status='committed',
                    entity_unchanged=len(request.entities),
                    edge_unchanged=len(request.edges),
                    provenance_unchanged=(
                        len(request.provenance.sources) if request.provenance is not None else 0
                    ),
                )
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=request.dry_run,
                status='failed',
                failed=max(len(request.entities) + len(request.edges), 1),
                error_code=CatalogErrorCode.batch_conflict,
                error_message='committed batch_id has different request_sha256',
            )

        entity_prepared: list[_PreparedEntity] = []
        entity_by_identity: dict[tuple[str, str], _PreparedEntity] = {}
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
            prior = entity_by_identity.get(identity)
            if prior is not None:
                if prior.content_sha256 == digest:
                    prior.coalesced_indices.append(index)
                else:
                    conflicted_entity_ids.add(entity_uuid)
                    errors.extend(
                        [
                            CatalogItemResult(
                                index=prior.index,
                                status='error',
                                uuid=entity_uuid,
                                graph_key=prior.item.graph_key,
                                entity_type=prior.item.entity_type,
                                error_code=CatalogErrorCode.deterministic_uuid_conflict,
                                error_message='same identity different canonical payload in request',
                                details={'kind': 'entity'},
                            ),
                            CatalogItemResult(
                                index=index,
                                status='error',
                                uuid=entity_uuid,
                                graph_key=item.graph_key,
                                entity_type=item.entity_type,
                                error_code=CatalogErrorCode.deterministic_uuid_conflict,
                                error_message='same identity different canonical payload in request',
                                details={'kind': 'entity'},
                            ),
                        ]
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
            prior = edge_by_uuid.get(edge_uuid)
            if prior is not None:
                if prior.content_sha256 == digest:
                    prior.coalesced_indices.append(local_index)
                else:
                    errors.extend(
                        [
                            self._batch_result_for_edge(
                                prior,
                                index=edge_offset + prior.index,
                                status='error',
                                error_code=CatalogErrorCode.deterministic_uuid_conflict,
                                error_message='same identity different canonical payload in request',
                            ),
                            CatalogItemResult(
                                index=result_index,
                                status='error',
                                uuid=edge_uuid,
                                edge_key=item.edge_key,
                                edge_type=item.edge_type,
                                error_code=CatalogErrorCode.deterministic_uuid_conflict,
                                error_message='same identity different canonical payload in request',
                                details={'kind': 'edge'},
                            ),
                        ]
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
            provenance_entity_uuids: list[str] = []
            provenance_edge_uuids: list[str] = []

            for target in provenance.entity_targets:
                target_uuid = catalog_entity_uuid(
                    namespace, request.group_id, target.entity_type, target.graph_key
                )
                row = None
                code: str | None = None
                if target_uuid not in invalid_uuids:
                    if (target.entity_type, target.graph_key) in request_entity_uuids:
                        row = {'uuid': target_uuid}
                    else:
                        try:
                            code, row = await self._store.resolve_endpoint_typed(
                                client.driver,
                                group_id=request.group_id,
                                graph_key=target.graph_key,
                                entity_type=target.entity_type,
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
                            graph_key=target.graph_key,
                            entity_type=target.entity_type,
                            error_code=CatalogErrorCode.provenance_target_missing,
                            error_message=f'provenance entity target missing or mistyped: {code or "missing"}',
                            details={'kind': 'provenance'},
                        )
                    )
                else:
                    provenance_entity_uuids.append(target_uuid)

            for target in provenance.edge_targets:
                target_uuid = catalog_edge_uuid(
                    namespace, request.group_id, target.edge_type, target.edge_key
                )
                request_edge = edge_by_uuid.get(target_uuid)
                if target_uuid in invalid_uuids:
                    row = None
                elif request_edge is not None:
                    row = {
                        'uuid': target_uuid,
                        'name': target.edge_type,
                        'edge_key': target.edge_key,
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
                    or row.get('name') not in (None, target.edge_type)
                    or row.get('edge_key') not in (None, target.edge_key)
                ):
                    errors.append(
                        CatalogItemResult(
                            index=len(request.entities) + len(request.edges),
                            status='error',
                            uuid=target_uuid,
                            edge_key=target.edge_key,
                            edge_type=target.edge_type,
                            error_code=CatalogErrorCode.provenance_target_missing,
                            error_message='provenance edge target missing or mistyped',
                            details={'kind': 'provenance'},
                        )
                    )
                else:
                    provenance_edge_uuids.append(target_uuid)

            for index, source in enumerate(provenance.sources):
                result_index = len(request.entities) + len(request.edges) + index
                try:
                    digest = canonical_sha256(self.source_canonical_payload(source))
                    assert_optional_client_hash(source.content_sha256, digest)
                    valid_at = self._parse_source_valid_at(source.reference_time)
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
                    entity_uuids=list(provenance_entity_uuids),
                    edge_uuids=list(provenance_edge_uuids),
                )
                prep.mentions_uuids = [
                    catalog_mentions_uuid(namespace, request.group_id, source_uuid, entity_uuid)
                    for entity_uuid in prep.entity_uuids
                ]
                if existing is not None and prep.projected_status == 'unchanged':
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
                            break
                    if link_read_error is None and prep.projected_status == 'unchanged':
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
                                break
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
                'catalog upsert_catalog_batch preflight_failed batch_id=%s entities=%s edges=%s errors=%s',
                request.batch_id,
                len(request.entities),
                len(request.edges),
                len(errors),
            )
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                dry_run=request.dry_run,
                status='failed',
                results=errors,
                failed=len(errors),
                error_code=(
                    CatalogErrorCode.batch_conflict
                    if any(
                        result.error_code == CatalogErrorCode.deterministic_uuid_conflict
                        for result in errors
                    )
                    else errors[0].error_code
                ),
                error_message='batch preflight failed',
            )

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
            )

        request_ts = datetime.now(timezone.utc)
        entity_results: list[CatalogItemResult] = []
        edge_results: list[CatalogItemResult] = []
        provenance_results: list[CatalogItemResult] = []
        try:
            async with client.driver.transaction() as tx:
                claim = await self._store.claim_batch_status(
                    tx,
                    params={
                        'uuid': batch_uuid,
                        'group_id': request.group_id,
                        'batch_id': request.batch_id,
                        'request_sha256': effective_hash,
                        'created_at': request_ts,
                        'updated_at': request_ts,
                    },
                )
                claimed_hash = claim.get('request_sha256')
                claimed_status = claim.get('status')
                if claimed_hash != effective_hash:
                    raise self._BatchStatusConflict('different_hash')
                if claimed_status == 'committed':
                    raise self._BatchStatusConflict('already_committed')
                written_request_entities: set[str] = set()
                for prep in entity_prepared:
                    status = prep.projected_status
                    existing = await self._store.get_entity_by_uuid(
                        None,
                        uuid=prep.entity_uuid,
                        group_id=request.group_id,
                        tx=tx,
                    )
                    if existing is None and status == 'unchanged':
                        raise self._EntityInvariantRace(CatalogErrorCode.missing_endpoint)
                    if existing is not None:
                        if self._entity_label_conflict(existing, prep.item.entity_type) is not None:
                            raise self._EntityInvariantRace(CatalogErrorCode.entity_type_conflict)
                        if self._entity_identity_property_conflict(existing, prep.item) is not None:
                            raise self._EntityInvariantRace(
                                CatalogErrorCode.deterministic_uuid_conflict
                            )
                        if (
                            status == 'unchanged'
                            and existing.get('content_sha256') != prep.content_sha256
                        ):
                            raise self._EntityInvariantRace(CatalogErrorCode.batch_conflict)
                    if status != 'unchanged':
                        row = await self._store.upsert_entity_item(
                            tx,
                            entity_type=prep.item.entity_type,
                            params=self._store.prepare_entity_params(
                                entity_type=prep.item.entity_type,
                                uuid=prep.entity_uuid,
                                group_id=request.group_id,
                                batch_id=request.batch_id,
                                graph_key=prep.item.graph_key,
                                name_raw=prep.item.name_raw,
                                name_canonical=prep.item.name_canonical,
                                database_qualified_name=prep.item.database_qualified_name,
                                summary=prep.item.summary,
                                content_sha256=prep.content_sha256,
                                created_at=request_ts,
                                updated_at=request_ts,
                                name_embedding=prep.name_embedding or [],
                                attributes=prep.item.attributes,
                                source_refs=prep.item.source_refs,
                                confidence=prep.item.confidence,
                            ),
                        )
                        status = self._write_status_from_row(row, prep.projected_status)
                        written_request_entities.add(prep.entity_uuid)
                    entity_results.append(self._batch_result_for_entity(prep, status=status))
                    for index in prep.coalesced_indices:
                        duplicate = self._batch_result_for_entity(prep, status=status)
                        duplicate.index = index
                        entity_results.append(duplicate)

                for prep in edge_prepared:
                    status = prep.projected_status
                    existing = await self._batch_recheck_edge_in_tx(
                        tx,
                        prep,
                        request,
                        request_entity_uuids,
                        written_request_entities,
                    )
                    if status == 'unchanged':
                        if existing is None:
                            raise self._EdgeEndpointRace(CatalogErrorCode.missing_endpoint)
                        if existing.get('content_sha256') != prep.content_sha256:
                            raise self._EdgeEndpointRace(CatalogErrorCode.batch_conflict)
                    else:
                        row = await self._store.upsert_edge_item(
                            tx,
                            params=self._store.prepare_edge_params(
                                edge_type=prep.item.edge_type,
                                uuid=prep.edge_uuid,
                                group_id=request.group_id,
                                batch_id=request.batch_id,
                                edge_key=prep.item.edge_key,
                                source_uuid=prep.source_uuid or '',
                                target_uuid=prep.target_uuid or '',
                                fact=prep.item.fact,
                                evidence=prep.item.evidence,
                                content_sha256=prep.content_sha256,
                                created_at=request_ts,
                                updated_at=request_ts,
                                fact_embedding=prep.fact_embedding or [],
                                attributes=prep.item.attributes,
                                confidence=prep.item.confidence,
                            ),
                        )
                        status = self._write_status_from_row(row, prep.projected_status)
                    result_index = prep.batch_result_index
                    assert result_index is not None
                    edge_results.append(
                        self._batch_result_for_edge(prep, index=result_index, status=status)
                    )
                    for local_index in prep.coalesced_indices:
                        edge_results.append(
                            self._batch_result_for_edge(
                                prep,
                                index=len(request.entities) + local_index,
                                status=status,
                            )
                        )

                for prep in provenance_sources:
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
                        entity_edges=list(prep.edge_uuids),
                        name=prep.item.source_key,
                    )
                    row = await self._store.upsert_source_episode(tx, params=params)
                    source_status = str(row.get('status') or prep.projected_status)
                    if prep.missing_links and source_status == 'unchanged':
                        source_status = 'updated'
                    for entity_uuid, mentions_uuid in zip(
                        prep.entity_uuids, prep.mentions_uuids, strict=True
                    ):
                        await self._store.upsert_mentions_link(
                            tx,
                            episode_uuid=prep.source_uuid,
                            entity_uuid=entity_uuid,
                            mentions_uuid=mentions_uuid,
                            group_id=request.group_id,
                            created_at=request_ts,
                        )
                    for edge_uuid in prep.edge_uuids:
                        await self._store.append_edge_episode(
                            tx,
                            edge_uuid=edge_uuid,
                            episode_uuid=prep.source_uuid,
                            group_id=request.group_id,
                        )
                    provenance_offset = len(request.entities) + len(request.edges)
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

                status_params = self._store.prepare_batch_status_params(
                    uuid=batch_uuid,
                    group_id=request.group_id,
                    batch_id=request.batch_id,
                    status='committed',
                    request_sha256=effective_hash,
                    catalog_sha256=request.catalog_sha256,
                    entity_count=len(request.entities),
                    edge_count=len(request.edges),
                    provenance_count=len(provenance_sources),
                    created_at=request_ts,
                    updated_at=request_ts,
                    committed_at=request_ts,
                )
                committed_row = await self._store.upsert_batch_status(tx, params=status_params)
                if committed_row.get('request_sha256') != effective_hash:
                    raise self._BatchStatusConflict('different_hash')
                if committed_row.get('status') != 'committed':
                    raise self._BatchStatusConflict('commit_rejected')
        except self._BatchStatusConflict as exc:
            if exc.reason == 'already_committed':
                return CatalogBatchWriteResponse(
                    group_id=request.group_id,
                    batch_id=request.batch_id,
                    batch_uuid=batch_uuid,
                    status='committed',
                    entity_unchanged=len(request.entities),
                    edge_unchanged=len(request.edges),
                    provenance_unchanged=len(provenance_sources),
                )
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges) + len(provenance_sources), 1),
                error_code=CatalogErrorCode.batch_conflict,
                error_message='batch_id has different request_sha256',
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
            failed_params = self._store.prepare_batch_status_params(
                uuid=batch_uuid,
                group_id=request.group_id,
                batch_id=request.batch_id,
                status='failed',
                request_sha256=effective_hash,
                catalog_sha256=request.catalog_sha256,
                entity_count=len(request.entities),
                edge_count=len(request.edges),
                provenance_count=len(provenance_sources),
                created_at=request_ts,
                updated_at=datetime.now(timezone.utc),
                error_summary=type(exc).__name__,
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
            return CatalogBatchWriteResponse(
                group_id=request.group_id,
                batch_id=request.batch_id,
                batch_uuid=batch_uuid,
                status='failed',
                failed=max(len(request.entities) + len(request.edges) + len(provenance_sources), 1),
                rolled_back=len(entity_results) + len(edge_results) + len(provenance_results),
                error_code=CatalogErrorCode.neo4j_transaction_failed,
                error_message='neo4j transaction failed',
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
        )
        logger.info(
            'catalog upsert_catalog_batch committed batch_id=%s entities=%s edges=%s provenance=%s',
            request.batch_id,
            len(request.entities),
            len(request.edges),
            len(provenance_sources),
        )
        return response

    class _BatchStatusConflict(Exception):
        def __init__(self, reason: str):
            self.reason = reason
            super().__init__(reason)

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
