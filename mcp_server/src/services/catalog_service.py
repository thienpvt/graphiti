"""CatalogService: deterministic typed catalog entity upsert orchestration.

Order: validate → uuid5+hash → coalesce → embed → open tx (if not dry_run).
No LLM, no queue, no EntityNode.save.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.schema import CatalogConfig
from models.catalog_common import CatalogErrorCode
from models.catalog_entities import CatalogEntityItem, UpsertTypedEntitiesRequest
from models.catalog_responses import CatalogItemResult, CatalogWriteResponse
from services.catalog_identity import (
    assert_optional_client_hash,
    canonical_sha256,
    catalog_entity_uuid,
)
from services.catalog_store import CatalogNeo4jStore

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
            except Exception:
                existing = None
            prep.existing = existing
            if existing is None:
                prep.projected_status = 'created'
                continue
            labels = existing.get('labels') or []
            # Neo4j labels property may be list; also check neo4j_labels
            custom = [lb for lb in labels if lb != 'Entity']
            if existing.get('neo4j_labels'):
                custom = [lb for lb in existing['neo4j_labels'] if lb != 'Entity']
            expected = prep.item.entity_type
            if custom and expected not in custom:
                prep.projected_status = 'error'
                prep.error_code = CatalogErrorCode.entity_type_conflict
                prep.error_message = (
                    f'existing custom labels {custom} conflict with {expected}'
                )
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

        # 5) write
        if request.atomic:
            return await self._write_atomic(
                client, request, write_set, early_errors, request_ts
            )
        return await self._write_per_item(
            client, request, write_set, early_errors, request_ts
        )

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
                    params = self._params_for(prep, request, request_ts)
                    row = await self._store.upsert_entity_item(
                        tx, entity_type=prep.item.entity_type, params=params
                    )
                    status = row.get('status') or prep.projected_status
                    if status not in ('created', 'updated', 'unchanged'):
                        status = prep.projected_status
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
                    params = self._params_for(prep, request, request_ts)
                    row = await self._store.upsert_entity_item(
                        tx, entity_type=prep.item.entity_type, params=params
                    )
                    status = row.get('status') or prep.projected_status
                    if status not in ('created', 'updated', 'unchanged'):
                        status = prep.projected_status
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
                    by_index[ci] = self._success_result(
                        prep, prep.projected_status, index=ci
                    )
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
