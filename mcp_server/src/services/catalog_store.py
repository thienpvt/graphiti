"""Neo4j persistence for deterministic catalog entities (no LLM / queue).

Server-owned Cypher only: allowlisted labels, parameterized values, preserve-on-update
MERGE (never SET n = $map). Caller UUIDs are never identity authority.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from models.catalog_common import (
    CATALOG_EDGE_TYPES,
    CATALOG_ENTITY_TYPES,
    ENTITY_TYPE_PREFIXES,
    HARD_MAX_ACTIVE_PLANS_PER_GROUP,
    HARD_MAX_CHUNKS_PER_PLAN,
    HARD_MAX_PREPARED_PAYLOAD_BYTES,
    MAX_EVIDENCE_LENGTH,
    PLAN_STATE_COMMITTED,
    PLAN_STATE_COMMITTING,
    PLAN_STATE_DISCARDED,
    PLAN_STATE_EXPIRED,
    PLAN_STATE_PREPARED,
    PLAN_STATES,
    PROTECTED_ENTITY_PROPERTIES,
)
from services.catalog_identity import CANONICALIZATION_VERSION

logger = logging.getLogger(__name__)

# Mirror graphiti_core.helpers.SAFE_CYPHER_IDENTIFIER_PATTERN without importing core.
_SAFE_LABEL = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# Fixed map: entity_type -> Neo4j label literal (identity with allowlist keys).
_ENTITY_LABELS: dict[str, str] = {t: t for t in ENTITY_TYPE_PREFIXES if _SAFE_LABEL.match(t)}

# Catalog-owned composite UNIQUE constraints. Single-property UNIQUE on uuid
# cannot coexist with stock Graphiti RANGE indexes (entity_uuid / relation_uuid)
# on Neo4j 5.26. Composite (uuid, group_id) coexists and matches MERGE keys.
# CREATE only — never DROP INDEX / DROP CONSTRAINT / data repair.
CATALOG_ENTITY_IDENTITY_CONSTRAINT = 'catalog_entity_identity_unique'
CATALOG_RELATES_TO_IDENTITY_CONSTRAINT = 'catalog_relates_to_identity_unique'
CATALOG_EPISODIC_IDENTITY_CONSTRAINT = 'catalog_episodic_identity_unique'
CATALOG_MENTIONS_IDENTITY_CONSTRAINT = 'catalog_mentions_identity_unique'
CATALOG_BATCH_IDENTITY_CONSTRAINT = 'catalog_batch_identity_unique'

_CREATE_ENTITY_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_ENTITY_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:Entity) REQUIRE (n.uuid, n.group_id) IS UNIQUE'
)
_CREATE_RELATES_TO_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_RELATES_TO_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR ()-[e:RELATES_TO]-() REQUIRE (e.uuid, e.group_id) IS UNIQUE'
)
_CREATE_EPISODIC_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_EPISODIC_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:Episodic) REQUIRE (n.uuid, n.group_id) IS UNIQUE'
)
_CREATE_MENTIONS_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_MENTIONS_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR ()-[e:MENTIONS]-() REQUIRE (e.uuid, e.group_id) IS UNIQUE'
)
_CREATE_BATCH_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_BATCH_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogIngestBatch) REQUIRE (n.uuid, n.group_id) IS UNIQUE'
)

# Prepared-plan control-plane constraints (PLAN-05/09; fixed labels only).
CATALOG_PREPARED_PLAN_IDENTITY_CONSTRAINT = 'catalog_prepared_plan_identity_unique'
CATALOG_PREPARED_PLAN_TOKEN_DIGEST_CONSTRAINT = 'catalog_prepared_plan_token_digest_unique'
CATALOG_PREPARED_PLAN_CHUNK_IDENTITY_CONSTRAINT = 'catalog_prepared_plan_chunk_identity_unique'
CATALOG_PREPARED_PLAN_CHUNK_INDEX_CONSTRAINT = 'catalog_prepared_plan_chunk_index_unique'

_CREATE_PREPARED_PLAN_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_PREPARED_PLAN_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogPreparedPlan) REQUIRE (n.uuid, n.group_id) IS UNIQUE'
)
_CREATE_PREPARED_PLAN_TOKEN_DIGEST_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_PREPARED_PLAN_TOKEN_DIGEST_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogPreparedPlan) REQUIRE n.token_digest IS UNIQUE'
)
_CREATE_PREPARED_PLAN_CHUNK_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_PREPARED_PLAN_CHUNK_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogPreparedPlanChunk) REQUIRE (n.uuid, n.group_id) IS UNIQUE'
)
_CREATE_PREPARED_PLAN_CHUNK_INDEX_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_PREPARED_PLAN_CHUNK_INDEX_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogPreparedPlanChunk) REQUIRE (n.plan_uuid, n.group_id, n.chunk_index) IS UNIQUE'
)

# Exact evidence + durable manifest control-plane constraints (EVID/MANI; fixed labels only).
CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT = 'catalog_evidence_link_identity_unique'
CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT = 'catalog_evidence_link_key_unique'
CATALOG_MANIFEST_IDENTITY_CONSTRAINT = 'catalog_batch_manifest_identity_unique'
CATALOG_MANIFEST_CHUNK_IDENTITY_CONSTRAINT = 'catalog_batch_manifest_chunk_identity_unique'
CATALOG_MANIFEST_CHUNK_INDEX_CONSTRAINT = 'catalog_batch_manifest_chunk_index_unique'

_CREATE_EVIDENCE_LINK_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogEvidenceLink) REQUIRE (n.uuid, n.group_id) IS UNIQUE'
)
_CREATE_EVIDENCE_LINK_KEY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogEvidenceLink) REQUIRE (n.group_id, n.link_key) IS UNIQUE'
)
_CREATE_MANIFEST_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_MANIFEST_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogBatchManifest) REQUIRE (n.uuid, n.group_id) IS UNIQUE'
)
_CREATE_MANIFEST_CHUNK_IDENTITY_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_MANIFEST_CHUNK_IDENTITY_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogBatchManifestChunk) REQUIRE (n.uuid, n.group_id) IS UNIQUE'
)
_CREATE_MANIFEST_CHUNK_INDEX_UNIQUE = (
    f'CREATE CONSTRAINT {CATALOG_MANIFEST_CHUNK_INDEX_CONSTRAINT} IF NOT EXISTS '
    'FOR (n:CatalogBatchManifestChunk) REQUIRE (n.manifest_uuid, n.group_id, n.chunk_index) IS UNIQUE'
)

_FORBIDDEN_EVIDENCE_MANIFEST_PARAM_KEYS: frozenset[str] = frozenset(
    {
        'plan_token',
        'raw_token',
        'token',
        'name_embedding',
        'fact_embedding',
    }
)

# Legal CAS edges for prepared-plan state machine (PLAN-18 / D-10..D-12).
# Keys are expected_from; values are allowed to-states.
_PLAN_CAS_LEGAL: dict[str, frozenset[str]] = {
    PLAN_STATE_PREPARED: frozenset(
        {PLAN_STATE_DISCARDED, PLAN_STATE_EXPIRED, PLAN_STATE_COMMITTING}
    ),
    PLAN_STATE_COMMITTING: frozenset({PLAN_STATE_COMMITTING, PLAN_STATE_COMMITTED}),
}

_PLAN_ROOT_PROP_KEYS: frozenset[str] = frozenset(
    {
        'uuid',
        'group_id',
        'batch_id',
        'plan_id',
        'token_digest',
        'state',
        'identity_schema_version',
        'canonicalization_version',
        'artifact_serialization_version',
        'request_sha256',
        'catalog_sha256',
        'artifact_sha256',
        'chunk_count',
        'payload_bytes',
        'entity_count',
        'edge_count',
        'source_count',
        'evidence_link_count',
        'created_count',
        'updated_count',
        'unchanged_count',
        'expires_at',
        'created_at',
        'updated_at',
        'committing_started_at',
    }
)
_PLAN_CHUNK_PROP_KEYS: frozenset[str] = frozenset(
    {
        'uuid',
        'group_id',
        'plan_uuid',
        'chunk_index',
        'chunk_count',
        'byte_offset',
        'byte_length',
        'chunk_sha256',
        'payload_b64',
    }
)
_FORBIDDEN_PLAN_PARAM_KEYS: frozenset[str] = frozenset(
    {
        'plan_token',
        'raw_token',
        'token',
        'name_embedding',
        'fact_embedding',
    }
)


class CatalogStoreError(ValueError):
    """Raised when catalog store cannot safely build or execute a query."""

    def __init__(self, message: str, *, code: str | None = None):
        self.code = code
        super().__init__(message)


def _json_compatible(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode='json')
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_compatible(item) for key, item in value.items()}
    return value


def serialize_nested_json(value: Any) -> str | None:
    """Serialize nested structures to a JSON string for Neo4j primitive storage."""
    if value is None:
        return None
    return json.dumps(
        _json_compatible(value),
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    )


def _strip_protected_attributes(attributes: dict[str, Any] | None) -> dict[str, Any] | None:
    if attributes is None:
        return None
    cleaned = {k: v for k, v in attributes.items() if k not in PROTECTED_ENTITY_PROPERTIES}
    return cleaned


class CatalogNeo4jStore:
    """Dedicated Neo4j store for catalog entity writes/reads.

    Does not call EntityNode.save or stock SET-map queries.
    """

    def __init__(self) -> None:
        self._schema_lock = asyncio.Lock()
        self._schema_ready = False
        self._plan_schema_lock = asyncio.Lock()
        self._plan_schema_ready = False
        self._evidence_manifest_schema_lock = asyncio.Lock()
        self._evidence_manifest_schema_ready = False

    @staticmethod
    def identity_uniqueness_constraint_statements() -> tuple[str, ...]:
        """Fixed server Cypher for catalog composite identity UNIQUE (CREATE only)."""
        return (
            _CREATE_ENTITY_IDENTITY_UNIQUE,
            _CREATE_RELATES_TO_IDENTITY_UNIQUE,
            _CREATE_EPISODIC_IDENTITY_UNIQUE,
            _CREATE_MENTIONS_IDENTITY_UNIQUE,
            _CREATE_BATCH_IDENTITY_UNIQUE,
        )

    # Back-compat alias for callers/tests that used the earlier name.
    @staticmethod
    def uuid_uniqueness_constraint_statements() -> tuple[str, ...]:
        return CatalogNeo4jStore.identity_uniqueness_constraint_statements()

    async def ensure_uuid_uniqueness_constraints(self, executor: Any) -> None:
        """Idempotent: composite (uuid, group_id) UNIQUE for concurrent MERGE.

        Awaited before real catalog writes. Once-ready short-circuits.
        CREATE CONSTRAINT IF NOT EXISTS only — never drops indexes/data.
        On existing duplicate (uuid, group_id) pairs, fails closed without repair.
        """
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            await self._ensure_identity_uniqueness_constraints_locked(executor)
            self._schema_ready = True

    async def _run_schema_query(self, executor: Any, stmt: str) -> Any:
        exec_q = getattr(executor, 'execute_query', None)
        if exec_q is None or not callable(exec_q):
            raise CatalogStoreError(
                'catalog schema init requires executor.execute_query',
                code='neo4j_schema_failed',
            )
        result = exec_q(stmt, params={})
        if inspect.isawaitable(result):
            return await result
        # Sync callables (rare) accepted when they return a ready result.
        return result

    async def _ensure_identity_uniqueness_constraints_locked(self, executor: Any) -> None:
        if await self._identity_uniqueness_present(executor):
            return

        for stmt in self.identity_uniqueness_constraint_statements():
            # Safety: product init never issues DROP.
            assert 'DROP' not in stmt.upper()
            try:
                await self._run_schema_query(executor, stmt)
            except CatalogStoreError:
                raise
            except Exception as exc:
                msg = f'{type(exc).__name__}: {exc}'
                # Already-exists races are OK only if final SHOW verifies shape.
                if (
                    'EquivalentSchemaRuleAlreadyExists' in msg
                    or 'already exists' in msg.lower()
                    or 'ConstraintAlreadyExists' in msg
                ):
                    continue
                # Duplicate data prevents uniqueness — fail closed, no repair.
                if (
                    'ConstraintValidationFailed' in msg
                    or 'already has' in msg.lower()
                    or 'duplicate' in msg.lower()
                ):
                    raise CatalogStoreError(
                        'catalog identity uniqueness constraint failed: existing duplicate '
                        '(uuid, group_id) values prevent CREATE CONSTRAINT; resolve manually',
                        code='neo4j_schema_failed',
                    ) from exc
                raise CatalogStoreError(
                    f'catalog schema init failed: {type(exc).__name__}',
                    code='neo4j_schema_failed',
                ) from exc

        # Fail closed: CREATE success / already-exists never skip SHOW verification.
        if not await self._identity_uniqueness_present(executor):
            raise CatalogStoreError(
                'catalog identity uniqueness constraints not present after init',
                code='neo4j_schema_failed',
            )
        logger.info(
            'catalog schema ready constraints=%s,%s,%s,%s,%s',
            CATALOG_ENTITY_IDENTITY_CONSTRAINT,
            CATALOG_RELATES_TO_IDENTITY_CONSTRAINT,
            CATALOG_EPISODIC_IDENTITY_CONSTRAINT,
            CATALOG_MENTIONS_IDENTITY_CONSTRAINT,
            CATALOG_BATCH_IDENTITY_CONSTRAINT,
        )

    @staticmethod
    def _constraint_row_matches(
        row: dict[str, Any],
        *,
        expected_name: str,
        expected_entity_type: str,
        expected_label: str,
        expected_properties: frozenset[str] | set[str] | None = None,
    ) -> bool:
        """True only when named constraint has UNIQUENESS shape on exact props."""
        name = str(row.get('name') or '')
        if name != expected_name:
            return False
        ctype = str(row.get('type') or '').upper()
        if 'UNIQUENESS' not in ctype and 'UNIQUE' not in ctype:
            return False
        etype = str(row.get('entityType') or '').upper()
        if etype != expected_entity_type.upper():
            return False
        labels = list(row.get('labelsOrTypes') or [])
        if expected_label not in labels:
            return False
        props = list(row.get('properties') or [])
        # Exact property set (order-insensitive). Default: composite (uuid, group_id).
        wanted = (
            set(expected_properties) if expected_properties is not None else {'uuid', 'group_id'}
        )
        return set(props) == wanted

    async def _identity_uniqueness_present(self, executor: Any) -> bool:
        """True when both catalog-named constraints have exact identity shape.

        Name match alone is insufficient: wrong type/entity/labels/properties fail closed.
        """
        try:
            result = await self._run_schema_query(
                executor,
                """
                SHOW CONSTRAINTS
                YIELD name, type, entityType, labelsOrTypes, properties
                RETURN name, type, entityType, labelsOrTypes, properties
                """,
            )
        except Exception:
            return False
        rows = self._all_from_execute_query_result(result)
        entity_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_ENTITY_IDENTITY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='Entity',
            )
            for row in rows
        )
        rel_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_RELATES_TO_IDENTITY_CONSTRAINT,
                expected_entity_type='RELATIONSHIP',
                expected_label='RELATES_TO',
            )
            for row in rows
        )
        episodic_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_EPISODIC_IDENTITY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='Episodic',
            )
            for row in rows
        )
        mentions_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_MENTIONS_IDENTITY_CONSTRAINT,
                expected_entity_type='RELATIONSHIP',
                expected_label='MENTIONS',
            )
            for row in rows
        )
        batch_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_BATCH_IDENTITY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogIngestBatch',
            )
            for row in rows
        )
        return entity_ok and rel_ok and episodic_ok and mentions_ok and batch_ok

    def resolve_entity_label(self, entity_type: str) -> str:
        """Map allowlisted entity_type to a fixed Neo4j label (re-validate at builder)."""
        if entity_type not in CATALOG_ENTITY_TYPES or entity_type not in _ENTITY_LABELS:
            raise CatalogStoreError(
                f'entity_type not allowlisted: {entity_type!r}',
                code='validation_error',
            )
        label = _ENTITY_LABELS[entity_type]
        if not _SAFE_LABEL.match(label):
            raise CatalogStoreError(
                f'entity_type label unsafe: {label!r}',
                code='validation_error',
            )
        return label

    def build_entity_upsert_cypher(self, entity_type: str) -> str:
        """Build MERGE Cypher with lock-authoritative identity arbitration.

        Labels are server-resolved literals only. Values are parameters.
        After MERGE, a lock-retaining self-assignment runs before immutable
        name/type checks. Conflict returns status=error + deterministic_uuid_conflict
        and never enters mutable FOREACH or vector update.
        Create path sets full props + per-write $create_token marker.
        Status derived from error_code, token presence, and hash compare.
        Token REMOVEd before RETURN (create-only; never client authority).
        MERGE key is composite (uuid, group_id) matching catalog identity UNIQUE.
        Identity properties set only ON CREATE (never rewritten on match).
        """
        label = self.resolve_entity_label(entity_type)
        # Updated-only content fields (identity/preservation never rewritten on match).
        updated_set = """
                n.database_qualified_name = $database_qualified_name,
                n.summary = $summary,
                n.attributes = $attributes,
                n.source_refs = $source_refs,
                n.confidence = $confidence,
                n.batch_id = $batch_id,
                n.content_sha256 = $content_sha256,
                n.updated_at = $updated_at
        """.strip()

        return f"""
            MERGE (n:Entity {{uuid: $uuid, group_id: $group_id}})
            ON CREATE SET
                n:{label},
                n.uuid = $uuid,
                n.group_id = $group_id,
                n.name = $name,
                n.graph_key = $graph_key,
                n.name_raw = $name_raw,
                n.name_canonical = $name_canonical,
                n.database_qualified_name = $database_qualified_name,
                n.summary = $summary,
                n.attributes = $attributes,
                n.source_refs = $source_refs,
                n.confidence = $confidence,
                n.batch_id = $batch_id,
                n.content_sha256 = $content_sha256,
                n.labels = $labels,
                n.created_at = $created_at,
                n.updated_at = $updated_at,
                n._catalog_create_token = $create_token
            WITH n, coalesce(n._catalog_create_token, '') = $create_token AS created
            SET n.uuid = n.uuid
            WITH n, created,
                 CASE
                   WHEN NOT created AND (
                     n.name IS NULL OR n.name <> $name
                     OR n.graph_key IS NULL OR n.graph_key <> $graph_key
                     OR n.name_raw IS NULL OR n.name_raw <> $name_raw
                     OR n.name_canonical IS NULL OR n.name_canonical <> $name_canonical
                     OR NOT ('Entity' IN labels(n))
                     OR NOT ('{label}' IN labels(n))
                     OR NOT (size([label IN labels(n) WHERE label <> 'Entity']) = 1)
                     OR n.labels IS NULL
                     OR size(n.labels) <> 2
                     OR NOT all(l IN n.labels WHERE l IN ['Entity', '{label}'])
                     OR NOT all(l IN ['Entity', '{label}'] WHERE l IN n.labels)
                   ) THEN 'deterministic_uuid_conflict'
                   ELSE null
                 END AS error_code
            WITH n, created, error_code,
                 CASE
                   WHEN error_code IS NOT NULL THEN 'error'
                   WHEN created THEN 'created'
                   WHEN n.content_sha256 = $content_sha256 THEN 'unchanged'
                   ELSE 'updated'
                 END AS status
            FOREACH (_ IN CASE WHEN status = 'updated' THEN [1] ELSE [] END |
              SET {updated_set}
            )
            REMOVE n._catalog_create_token
            WITH n, status, error_code
            CALL {{
              WITH n, status
              WITH n, status WHERE status IN ['created', 'updated']
              CALL db.create.setNodeVectorProperty(n, 'name_embedding', $name_embedding)
              RETURN 1 AS _
              UNION
              WITH n, status
              WITH n, status WHERE NOT status IN ['created', 'updated']
              RETURN 0 AS _
            }}
            RETURN n.uuid AS uuid,
                   n.name AS name,
                   n.graph_key AS graph_key,
                   n.name_raw AS name_raw,
                   n.name_canonical AS name_canonical,
                   n.labels AS labels,
                   labels(n) AS neo4j_labels,
                   n.content_sha256 AS content_sha256,
                   n.summary AS summary,
                   n.batch_id AS batch_id,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at,
                   n.name_embedding IS NOT NULL AS has_name_embedding,
                   status,
                   error_code
            """

    def build_get_entity_by_uuid_cypher(self) -> str:
        return """
            MATCH (n:Entity {uuid: $uuid})
            WHERE n.group_id = $group_id
            RETURN n.uuid AS uuid,
                   n.group_id AS group_id,
                   n.name AS name,
                   n.graph_key AS graph_key,
                   n.name_raw AS name_raw,
                   n.name_canonical AS name_canonical,
                   n.labels AS labels,
                   labels(n) AS neo4j_labels,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at,
                   n.name_embedding IS NOT NULL AS has_name_embedding
            """

    def build_get_entity_by_group_name_type_cypher(self, entity_type: str) -> str:
        label = self.resolve_entity_label(entity_type)
        return f"""
            MATCH (n:Entity:{label} {{group_id: $group_id, name: $name}})
            RETURN n.uuid AS uuid,
                   n.group_id AS group_id,
                   n.name AS name,
                   n.graph_key AS graph_key,
                   n.labels AS labels,
                   labels(n) AS neo4j_labels,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at,
                   n.name_embedding IS NOT NULL AS has_name_embedding
            """

    def prepare_entity_params(
        self,
        *,
        entity_type: str,
        uuid: str,
        group_id: str,
        batch_id: str,
        graph_key: str,
        name_raw: str,
        name_canonical: str,
        database_qualified_name: str,
        summary: str,
        content_sha256: str,
        created_at: datetime,
        updated_at: datetime,
        name_embedding: list[float],
        attributes: dict[str, Any] | None = None,
        source_refs: list[Any] | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        """Build parameterized property map for entity upsert.

        name equals graph_key; labels property is Entity + custom type.
        Nested maps are JSON strings. Protected keys stripped from attributes.
        """
        label = self.resolve_entity_label(entity_type)
        cleaned_attrs = _strip_protected_attributes(attributes)
        return {
            'uuid': uuid,
            'group_id': group_id,
            'batch_id': batch_id,
            'name': graph_key,
            'graph_key': graph_key,
            'name_raw': name_raw,
            'name_canonical': name_canonical,
            'database_qualified_name': database_qualified_name,
            'summary': summary,
            'content_sha256': content_sha256,
            'created_at': created_at,
            'updated_at': updated_at,
            'name_embedding': name_embedding,
            'attributes': serialize_nested_json(cleaned_attrs),
            'source_refs': serialize_nested_json(source_refs),
            'confidence': confidence,
            'labels': ['Entity', label],
            # Per-write create marker only; never client authority, never persisted.
            'create_token': uuid4().hex,
        }

    async def upsert_entity_item(
        self,
        tx: Any,
        *,
        entity_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute entity MERGE inside an open transaction. Returns first record dict.

        Empty/missing uuid means group-scope miss or write failure — never success.
        """
        cypher = self.build_entity_upsert_cypher(entity_type)
        result = await tx.run(cypher, **params)
        row: dict[str, Any] = {}
        if hasattr(result, 'data'):
            rows = await result.data()
            row = rows[0] if rows else {}
        elif hasattr(result, 'single'):
            record = await result.single()
            row = dict(record) if record is not None else {}
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'entity upsert returned no row (missing, group mismatch, or write failure)',
                code='neo4j_transaction_failed',
            )
        return row

    async def get_entity_by_uuid(
        self,
        executor: Any,
        *,
        uuid: str,
        group_id: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        cypher = self.build_get_entity_by_uuid_cypher()
        params = {'uuid': uuid, 'group_id': group_id}
        return await self._read_one(executor, cypher, params, tx=tx)

    async def get_entity_by_group_name_type(
        self,
        executor: Any,
        *,
        group_id: str,
        name: str,
        entity_type: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        cypher = self.build_get_entity_by_group_name_type_cypher(entity_type)
        params = {'group_id': group_id, 'name': name}
        return await self._read_one(executor, cypher, params, tx=tx)

    async def _read_one(
        self,
        executor: Any,
        cypher: str,
        params: dict[str, Any],
        *,
        tx: Any | None,
    ) -> dict[str, Any] | None:
        if tx is not None:
            result = await tx.run(cypher, **params)
            return await self._first_from_tx_result(result)
        # Neo4jDriver.execute_query binds Cypher values only via params=; other kwargs
        # are AsyncDriver execute options. Never splat property maps as **kwargs.
        result = await executor.execute_query(cypher, params=params)
        return self._first_from_execute_query_result(result)

    @staticmethod
    async def _first_from_tx_result(result: Any) -> dict[str, Any] | None:
        if result is None:
            return None
        if hasattr(result, 'data'):
            rows = await result.data()
            if not rows:
                return None
            first = rows[0]
            return first if isinstance(first, dict) else dict(first)
        if hasattr(result, 'single'):
            record = await result.single()
            if record is None:
                return None
            return record if isinstance(record, dict) else dict(record)
        return None

    @staticmethod
    def _first_from_execute_query_result(result: Any) -> dict[str, Any] | None:
        """Parse Neo4jDriver.execute_query / EagerResult contract.

        Contract: None, or tuple-like (records, summary, keys) where records is a
        sequence of mapping rows. EagerResult is a tuple subclass; index 0 is records.
        Do not use .records attribute access — pyright types the return as tuple.
        """
        if result is None:
            return None
        # EagerResult and plain (records, summary, keys) are both tuple-like.
        if not isinstance(result, tuple) or not result:
            return None
        records = result[0]
        if not records:
            return None
        first = records[0]
        if isinstance(first, dict):
            return first
        try:
            return dict(first)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _all_from_execute_query_result(result: Any) -> list[dict[str, Any]]:
        """Parse all records from Neo4jDriver.execute_query / EagerResult."""
        if result is None:
            return []
        if not isinstance(result, tuple) or not result:
            return []
        records = result[0] or []
        out: list[dict[str, Any]] = []
        for row in records:
            if isinstance(row, dict):
                out.append(row)
            else:
                try:
                    out.append(dict(row))
                except (TypeError, ValueError):
                    continue
        return out

    async def _read_many(
        self,
        executor: Any,
        cypher: str,
        params: dict[str, Any],
        *,
        tx: Any | None = None,
    ) -> list[dict[str, Any]]:
        if tx is not None:
            result = await tx.run(cypher, **params)
            if result is None:
                return []
            if hasattr(result, 'data'):
                rows = await result.data()
                return [r if isinstance(r, dict) else dict(r) for r in (rows or [])]
            return []
        # Live Neo4jDriver contract: Cypher values only via params=
        result = await executor.execute_query(cypher, params=params)
        return self._all_from_execute_query_result(result)

    def build_match_entities_for_resolve_cypher(self) -> str:
        """MATCH Entity nodes by group_id and name/graph_key in requested keys only."""
        return """
            MATCH (n:Entity)
            WHERE n.group_id = $group_id
              AND (n.name IN $graph_keys OR n.graph_key IN $graph_keys)
            RETURN n.uuid AS uuid,
                   n.group_id AS group_id,
                   n.name AS name,
                   n.graph_key AS graph_key,
                   n.labels AS labels,
                   labels(n) AS neo4j_labels,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.name_embedding IS NOT NULL AS has_name_embedding
            """

    async def match_entities_for_resolve(
        self,
        executor: Any,
        *,
        group_id: str,
        graph_keys: list[str],
        tx: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Read-only MATCH for resolve; scoped to group_id + requested keys."""
        if not graph_keys:
            return []
        cypher = self.build_match_entities_for_resolve_cypher()
        params = {'group_id': group_id, 'graph_keys': list(graph_keys)}
        return await self._read_many(executor, cypher, params, tx=tx)

    def build_match_entities_for_verify_by_batch_cypher(self) -> str:
        return """
            MATCH (n:Entity)
            WHERE n.group_id = $group_id
              AND n.batch_id = $batch_id
            RETURN elementId(n) AS element_id,
                   n.uuid AS uuid,
                   n.group_id AS group_id,
                   n.name AS name,
                   n.graph_key AS graph_key,
                   n.labels AS labels,
                   labels(n) AS neo4j_labels,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.name_embedding IS NOT NULL AS has_name_embedding
            """

    def build_match_entities_for_verify_by_keys_cypher(self) -> str:
        return """
            MATCH (n:Entity)
            WHERE n.group_id = $group_id
              AND (n.name IN $graph_keys OR n.graph_key IN $graph_keys)
            RETURN elementId(n) AS element_id,
                   n.uuid AS uuid,
                   n.group_id AS group_id,
                   n.name AS name,
                   n.graph_key AS graph_key,
                   n.labels AS labels,
                   labels(n) AS neo4j_labels,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.name_embedding IS NOT NULL AS has_name_embedding
            """

    async def match_entities_for_verify(
        self,
        executor: Any,
        *,
        group_id: str,
        batch_id: str | None = None,
        graph_keys: list[str] | None = None,
        tx: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Read-only entity MATCH for verify; exact group_id + batch_id and/or keys."""
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _row_identity(row: dict[str, Any]) -> str:
            # Prefer physical element_id; UUID fallback only for legacy mocks.
            return str(row.get('element_id') or row.get('uuid') or '')

        if batch_id:
            cypher = self.build_match_entities_for_verify_by_batch_cypher()
            batch_rows = await self._read_many(
                executor,
                cypher,
                {'group_id': group_id, 'batch_id': batch_id},
                tx=tx,
            )
            for row in batch_rows:
                key = _row_identity(row)
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)

        if graph_keys:
            cypher = self.build_match_entities_for_verify_by_keys_cypher()
            key_rows = await self._read_many(
                executor,
                cypher,
                {'group_id': group_id, 'graph_keys': list(graph_keys)},
                tx=tx,
            )
            for row in key_rows:
                key = _row_identity(row)
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
        return rows

    def build_match_edges_for_verify_by_batch_cypher(self) -> str:
        return """
            MATCH (s:Entity)-[e:RELATES_TO]->(t:Entity)
            WHERE e.group_id = $group_id
              AND e.batch_id = $batch_id
            RETURN elementId(e) AS element_id,
                   e.uuid AS uuid,
                   e.group_id AS group_id,
                   e.name AS edge_type,
                   e.edge_key AS edge_key,
                   e.batch_id AS batch_id,
                   e.fact_embedding IS NOT NULL AS has_fact_embedding,
                   s.uuid AS source_uuid,
                   s.name AS source_name,
                   s.graph_key AS source_graph_key,
                   labels(s) AS source_labels,
                   t.uuid AS target_uuid,
                   t.name AS target_name,
                   t.graph_key AS target_graph_key,
                   labels(t) AS target_labels
            """

    def build_match_edges_for_verify_by_keys_cypher(self) -> str:
        return """
            MATCH (s:Entity)-[e:RELATES_TO]->(t:Entity)
            WHERE e.group_id = $group_id
              AND e.edge_key IN $edge_keys
            RETURN elementId(e) AS element_id,
                   e.uuid AS uuid,
                   e.group_id AS group_id,
                   e.name AS edge_type,
                   e.edge_key AS edge_key,
                   e.batch_id AS batch_id,
                   e.fact_embedding IS NOT NULL AS has_fact_embedding,
                   s.uuid AS source_uuid,
                   s.name AS source_name,
                   s.graph_key AS source_graph_key,
                   labels(s) AS source_labels,
                   t.uuid AS target_uuid,
                   t.name AS target_name,
                   t.graph_key AS target_graph_key,
                   labels(t) AS target_labels
            """

    async def match_edges_for_verify(
        self,
        executor: Any,
        *,
        group_id: str,
        batch_id: str | None = None,
        edge_keys: list[str] | None = None,
        tx: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Read-only edge MATCH for verify; exact group_id + batch_id and/or keys."""
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        if batch_id:
            cypher = self.build_match_edges_for_verify_by_batch_cypher()
            batch_rows = await self._read_many(
                executor,
                cypher,
                {'group_id': group_id, 'batch_id': batch_id},
                tx=tx,
            )
            for row in batch_rows:
                key = str(row.get('element_id') or '')
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)

        if edge_keys:
            cypher = self.build_match_edges_for_verify_by_keys_cypher()
            key_rows = await self._read_many(
                executor,
                cypher,
                {'group_id': group_id, 'edge_keys': list(edge_keys)},
                tx=tx,
            )
            for row in key_rows:
                key = str(row.get('element_id') or '')
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
        return rows

    def build_match_provenance_presence_cypher(self) -> str:
        """Report whether requested entity/edge UUIDs have provenance.

        Entities: any group-scoped MENTIONS from Episodic.
        Edges: non-empty coalesce(e.episodes, []) on group-scoped RELATES_TO.
        """
        return """
            UNWIND $target_uuids AS target_uuid
            OPTIONAL MATCH (ep:Episodic)-[:MENTIONS]->(n {uuid: target_uuid})
            WHERE ep.group_id = $group_id AND n.group_id = $group_id
            WITH target_uuid, count(ep) AS mention_count
            OPTIONAL MATCH ()-[e:RELATES_TO {uuid: target_uuid, group_id: $group_id}]->()
            WITH target_uuid, mention_count,
                 size(coalesce(e.episodes, [])) AS episode_count
            RETURN target_uuid AS uuid,
                   (mention_count > 0 OR episode_count > 0) AS has_provenance
            """

    async def match_provenance_presence(
        self,
        executor: Any,
        *,
        group_id: str,
        target_uuids: list[str],
        tx: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Read-only provenance presence check; no writes."""
        if not target_uuids:
            return []
        cypher = self.build_match_provenance_presence_cypher()
        params = {'group_id': group_id, 'target_uuids': list(target_uuids)}
        return await self._read_many(executor, cypher, params, tx=tx)

    # ------------------------------------------------------------------
    # Provenance: Episodic sources, MENTIONS, RELATES_TO.episodes append
    # ------------------------------------------------------------------

    def build_source_episode_upsert_cypher(self) -> str:
        """Lock and compare-and-set an Episodic source in one fixed query.

        The self-SET takes a write lock before matched-source properties are compared.
        Expected absence/presence and identity/hash drift return an error without updating.
        """
        updated_set = """
                n.name = $name,
                n.source = $source,
                n.source_description = $source_description,
                n.content = $content,
                n.entity_edges = reduce(
                    edges = coalesce(n.entity_edges, []), edge IN $entity_edges |
                    CASE WHEN edge IN edges THEN edges ELSE edges + edge END
                ),
                n.valid_at = $valid_at,
                n.batch_id = $batch_id,
                n.content_sha256 = $content_sha256,
                n.updated_at = $updated_at
        """.strip()
        return f"""
            MERGE (n:Episodic {{uuid: $uuid, group_id: $group_id}})
            ON CREATE SET
                n.uuid = $uuid,
                n.group_id = $group_id,
                n.name = $name,
                n.source = $source,
                n.source_description = $source_description,
                n.content = $content,
                n.entity_edges = $entity_edges,
                n.valid_at = $valid_at,
                n.source_key = $source_key,
                n.batch_id = $batch_id,
                n.content_sha256 = $content_sha256,
                n.created_at = $created_at,
                n.updated_at = $updated_at,
                n._catalog_create_token = $create_token
            WITH n, coalesce(n._catalog_create_token, '') = $create_token AS created
            SET n.uuid = n.uuid
            WITH n, created,
                 CASE
                   WHEN $expected_exists AND created THEN 'batch_conflict'
                   WHEN $expected_exists AND NOT created AND (
                     (n.source_key IS NULL AND $expected_source_key IS NOT NULL)
                     OR (n.source_key IS NOT NULL AND $expected_source_key IS NULL)
                     OR n.source_key <> $expected_source_key
                   ) THEN 'batch_conflict'
                   WHEN NOT created AND (
                     n.source_key IS NULL OR n.source_key <> $source_key
                   ) THEN 'deterministic_uuid_conflict'
                   WHEN $expected_exists AND NOT created AND (
                     n.content_sha256 IS NULL
                     OR n.content_sha256 <> $expected_content_sha256
                   ) THEN 'batch_conflict'
                   WHEN NOT $expected_exists AND NOT created
                     AND n.content_sha256 <> $content_sha256 THEN 'batch_conflict'
                   ELSE null
                 END AS error_code
            WITH n, created, error_code,
                 CASE
                   WHEN error_code IS NOT NULL THEN 'error'
                   WHEN created THEN 'created'
                   WHEN n.content_sha256 = $content_sha256 THEN 'unchanged'
                   ELSE 'updated'
                 END AS status
            FOREACH (_ IN CASE WHEN status = 'updated' THEN [1] ELSE [] END |
              SET {updated_set}
            )
            REMOVE n._catalog_create_token
            RETURN n.uuid AS uuid,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at,
                   n.source_key AS source_key,
                   status,
                   error_code
            """

    def prepare_source_episode_params(
        self,
        *,
        uuid: str,
        group_id: str,
        batch_id: str,
        source_key: str,
        content_sha256: str,
        content: str,
        source: str,
        source_description: str,
        valid_at: datetime,
        created_at: datetime,
        updated_at: datetime,
        expected_exists: bool,
        expected_source_key: str | None,
        expected_content_sha256: str | None,
        entity_edges: list[str] | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Build parameterized map for source episode upsert (no embeddings)."""
        return {
            'uuid': uuid,
            'group_id': group_id,
            'batch_id': batch_id,
            'source_key': source_key,
            'name': name if name is not None else source_key,
            'source': source,
            'source_description': source_description,
            'content': content,
            'entity_edges': list(entity_edges or []),
            'valid_at': valid_at,
            'content_sha256': content_sha256,
            'created_at': created_at,
            'updated_at': updated_at,
            'expected_exists': expected_exists,
            'expected_source_key': expected_source_key,
            'expected_content_sha256': expected_content_sha256,
            'create_token': uuid4().hex,
        }

    async def upsert_source_episode(
        self,
        tx: Any,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Episodic source MERGE inside open transaction."""
        cypher = self.build_source_episode_upsert_cypher()
        result = await tx.run(cypher, **params)
        row: dict[str, Any] = {}
        if hasattr(result, 'data'):
            rows = await result.data()
            row = rows[0] if rows else {}
        elif hasattr(result, 'single'):
            record = await result.single()
            row = dict(record) if record is not None else {}
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'source episode upsert returned no row',
                code='neo4j_transaction_failed',
            )
        return row

    def build_lock_provenance_targets_cypher(self) -> str:
        """Acquire retained write locks on fixed-label provenance targets in UUID order."""
        return """
            UNWIND $targets AS target
            WITH target
            ORDER BY target.uuid, target.kind
            CALL (target) {
              WITH target WHERE target.kind = 'entity'
              MATCH (n:Entity {uuid: target.uuid, group_id: $group_id})
              SET n.uuid = n.uuid
              RETURN target.uuid AS uuid, 'entity' AS kind,
                     labels(n) AS labels, [] AS episodes
              UNION ALL
              WITH target WHERE target.kind = 'edge'
              MATCH ()-[e:RELATES_TO {uuid: target.uuid, group_id: $group_id}]->()
              SET e.uuid = e.uuid
              RETURN target.uuid AS uuid, 'edge' AS kind,
                     [] AS labels, coalesce(e.episodes, []) AS episodes
            }
            RETURN uuid, kind, labels, episodes
            """

    async def lock_provenance_targets(
        self,
        tx: Any,
        *,
        group_id: str,
        entity_uuids: list[str],
        edge_uuids: list[str],
    ) -> list[dict[str, Any]]:
        """Lock all existing provenance targets; return rows for under-lock checks."""
        targets = sorted(
            [
                *({'kind': 'entity', 'uuid': uuid} for uuid in set(entity_uuids)),
                *({'kind': 'edge', 'uuid': uuid} for uuid in set(edge_uuids)),
            ],
            key=lambda target: (target['uuid'], target['kind']),
        )
        if not targets:
            return []
        result = await tx.run(
            self.build_lock_provenance_targets_cypher(),
            group_id=group_id,
            targets=targets,
        )
        if hasattr(result, 'data'):
            return [dict(row) for row in await result.data()]
        rows: list[dict[str, Any]] = []
        if hasattr(result, '__aiter__'):
            async for record in result:
                rows.append(dict(record))
        return rows

    def build_mentions_merge_cypher(self) -> str:
        """MERGE deterministic MENTIONS; both ends MATCH group-scoped; ON CREATE only."""
        return """
            MATCH (episode:Episodic {uuid: $episode_uuid, group_id: $group_id})
            MATCH (node:Entity {uuid: $entity_uuid, group_id: $group_id})
            MERGE (episode)-[e:MENTIONS {uuid: $mentions_uuid}]->(node)
            ON CREATE SET
                e.uuid = $mentions_uuid,
                e.group_id = $group_id,
                e.created_at = $created_at,
                e._catalog_create_token = $create_token
            WITH e,
                 coalesce(e._catalog_create_token, '') = $create_token AS created
            REMOVE e._catalog_create_token
            RETURN e.uuid AS uuid,
                   CASE WHEN created THEN 'created' ELSE 'unchanged' END AS status
            """

    async def upsert_mentions_link(
        self,
        tx: Any,
        *,
        episode_uuid: str,
        entity_uuid: str,
        mentions_uuid: str,
        group_id: str,
        created_at: datetime,
    ) -> dict[str, Any]:
        """MERGE MENTIONS link inside open transaction."""
        cypher = self.build_mentions_merge_cypher()
        params = {
            'episode_uuid': episode_uuid,
            'entity_uuid': entity_uuid,
            'mentions_uuid': mentions_uuid,
            'group_id': group_id,
            'created_at': created_at,
            'create_token': uuid4().hex,
        }
        result = await tx.run(cypher, **params)
        row: dict[str, Any] = {}
        if hasattr(result, 'data'):
            rows = await result.data()
            row = rows[0] if rows else {}
        elif hasattr(result, 'single'):
            record = await result.single()
            row = dict(record) if record is not None else {}
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'mentions upsert returned no row (endpoint miss or write failure)',
                code='neo4j_transaction_failed',
            )
        return row

    def build_append_edge_episode_cypher(self) -> str:
        """APOC-free append of episode uuid onto RELATES_TO.episodes with membership dedup."""
        return """
            MATCH ()-[e:RELATES_TO {uuid: $edge_uuid, group_id: $group_id}]->()
            WITH e, coalesce(e.episodes, []) AS eps
            WITH e, CASE WHEN $episode_uuid IN eps THEN eps ELSE eps + $episode_uuid END AS next
            SET e.episodes = next
            RETURN e.uuid AS uuid, e.episodes AS episodes
            """

    async def append_edge_episode(
        self,
        tx: Any,
        *,
        edge_uuid: str,
        episode_uuid: str,
        group_id: str,
    ) -> dict[str, Any]:
        """Append episode uuid to edge.episodes (dedup) inside open transaction."""
        cypher = self.build_append_edge_episode_cypher()
        params = {
            'edge_uuid': edge_uuid,
            'episode_uuid': episode_uuid,
            'group_id': group_id,
        }
        result = await tx.run(cypher, **params)
        row: dict[str, Any] = {}
        if hasattr(result, 'data'):
            rows = await result.data()
            row = rows[0] if rows else {}
        elif hasattr(result, 'single'):
            record = await result.single()
            row = dict(record) if record is not None else {}
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'append edge episode returned no row (edge miss or write failure)',
                code='neo4j_transaction_failed',
            )
        return row

    def build_get_source_episode_by_uuid_cypher(self) -> str:
        return """
            MATCH (n:Episodic {uuid: $uuid, group_id: $group_id})
            RETURN n.uuid AS uuid,
                   n.group_id AS group_id,
                   n.source_key AS source_key,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at
            """

    async def get_source_episode_by_uuid(
        self,
        executor: Any,
        *,
        uuid: str,
        group_id: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        cypher = self.build_get_source_episode_by_uuid_cypher()
        params = {'uuid': uuid, 'group_id': group_id}
        return await self._read_one(executor, cypher, params, tx=tx)

    def build_get_mentions_link_cypher(self) -> str:
        return """
            MATCH (episode:Episodic {uuid: $episode_uuid, group_id: $group_id})
                  -[e:MENTIONS {uuid: $mentions_uuid}]->
                  (node:Entity {uuid: $entity_uuid, group_id: $group_id})
            RETURN e.uuid AS uuid, e.group_id AS group_id
            """

    async def get_mentions_link(
        self,
        executor: Any,
        *,
        episode_uuid: str,
        entity_uuid: str,
        mentions_uuid: str,
        group_id: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        cypher = self.build_get_mentions_link_cypher()
        params = {
            'episode_uuid': episode_uuid,
            'entity_uuid': entity_uuid,
            'mentions_uuid': mentions_uuid,
            'group_id': group_id,
        }
        return await self._read_one(executor, cypher, params, tx=tx)

    # ------------------------------------------------------------------
    # CatalogIngestBatch status (non-Entity; terminal committed/failed only)
    # ------------------------------------------------------------------

    # Persist only terminal statuses. Response model still allows six lifecycle literals.
    BATCH_STATUS_TERMINAL = frozenset({'committed', 'failed'})
    # Bounded sanitized error summary (matches CatalogIngestStatusResponse max_length).
    BATCH_STATUS_ERROR_SUMMARY_MAX = 512

    def build_batch_status_upsert_cypher(self) -> str:
        """Conditionally persist terminal status without overwriting committed state."""
        return """
            MERGE (b:CatalogIngestBatch {uuid: $uuid, group_id: $group_id})
            ON CREATE SET
                b.uuid = $uuid,
                b.group_id = $group_id,
                b.batch_id = $batch_id,
                b.created_at = $created_at
            WITH b,
                 coalesce(b.status, '') = 'committed' AS already_committed,
                 b.request_sha256 IS NOT NULL
                   AND b.request_sha256 <> $request_sha256 AS hash_conflict
            FOREACH (_ IN CASE
              WHEN NOT already_committed AND NOT hash_conflict THEN [1]
              ELSE []
            END |
              SET b.status = $status,
                  b.request_sha256 = $request_sha256,
                  b.catalog_sha256 = $catalog_sha256,
                  b.entity_count = $entity_count,
                  b.edge_count = $edge_count,
                  b.provenance_count = $provenance_count,
                  b.error_summary = $error_summary,
                  b.updated_at = $updated_at,
                  b.committed_at = $committed_at
            )
            RETURN b.uuid AS uuid,
                   b.group_id AS group_id,
                   b.batch_id AS batch_id,
                   b.status AS status,
                   b.request_sha256 AS request_sha256,
                   b.catalog_sha256 AS catalog_sha256,
                   b.entity_count AS entity_count,
                   b.edge_count AS edge_count,
                   b.provenance_count AS provenance_count,
                   b.error_summary AS error_summary,
                   b.created_at AS created_at,
                   b.updated_at AS updated_at,
                   b.committed_at AS committed_at,
                   already_committed,
                   hash_conflict
            """

    def build_batch_status_claim_cypher(self) -> str:
        """Create/recheck a transaction-local batch claim before domain writes."""
        return """
            MERGE (b:CatalogIngestBatch {uuid: $uuid, group_id: $group_id})
            ON CREATE SET
                b.uuid = $uuid,
                b.group_id = $group_id,
                b.batch_id = $batch_id,
                b.request_sha256 = $request_sha256,
                b.status = 'writing',
                b.created_at = $created_at,
                b.updated_at = $updated_at
            RETURN b.uuid AS uuid,
                   b.status AS status,
                   b.request_sha256 AS request_sha256
            """

    async def claim_batch_status(self, tx: Any, *, params: dict[str, Any]) -> dict[str, Any]:
        """Claim batch identity under the composite uniqueness constraint."""
        result = await tx.run(self.build_batch_status_claim_cypher(), **params)
        row = await self._first_from_tx_result(result)
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'batch status claim returned no row', code='neo4j_transaction_failed'
            )
        return row

    def build_get_batch_status_cypher(self) -> str:
        """MATCH status by composite uuid+group_id; CatalogIngestBatch only."""
        return """
            MATCH (b:CatalogIngestBatch {uuid: $uuid, group_id: $group_id})
            RETURN b.uuid AS uuid,
                   b.group_id AS group_id,
                   b.batch_id AS batch_id,
                   b.status AS status,
                   b.request_sha256 AS request_sha256,
                   b.catalog_sha256 AS catalog_sha256,
                   b.entity_count AS entity_count,
                   b.edge_count AS edge_count,
                   b.provenance_count AS provenance_count,
                   b.error_summary AS error_summary,
                   b.created_at AS created_at,
                   b.updated_at AS updated_at,
                   b.committed_at AS committed_at
            """

    def prepare_batch_status_params(
        self,
        *,
        uuid: str,
        group_id: str,
        batch_id: str,
        status: str,
        entity_count: int,
        edge_count: int,
        provenance_count: int,
        created_at: datetime,
        updated_at: datetime,
        request_sha256: str | None = None,
        catalog_sha256: str | None = None,
        error_summary: str = '',
        committed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Build allowlisted status property map; terminal status only."""
        if not uuid or not str(uuid).strip():
            raise CatalogStoreError('status uuid is required', code='validation_error')
        if not group_id or not str(group_id).strip():
            raise CatalogStoreError('status group_id is required', code='validation_error')
        if not batch_id or not str(batch_id).strip():
            raise CatalogStoreError('status batch_id is required', code='validation_error')
        if status not in self.BATCH_STATUS_TERMINAL:
            raise CatalogStoreError(
                f'status must be terminal committed|failed, got {status!r}',
                code='validation_error',
            )
        summary = error_summary if error_summary is not None else ''
        if not isinstance(summary, str):
            summary = str(summary)
        if len(summary) > self.BATCH_STATUS_ERROR_SUMMARY_MAX:
            summary = summary[: self.BATCH_STATUS_ERROR_SUMMARY_MAX]
        return {
            'uuid': str(uuid),
            'group_id': str(group_id),
            'batch_id': str(batch_id),
            'status': status,
            'request_sha256': request_sha256,
            'catalog_sha256': catalog_sha256,
            'entity_count': int(entity_count),
            'edge_count': int(edge_count),
            'provenance_count': int(provenance_count),
            'error_summary': summary,
            'created_at': created_at,
            'updated_at': updated_at,
            'committed_at': committed_at,
        }

    async def upsert_batch_status(
        self,
        tx: Any,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute CatalogIngestBatch MERGE inside open transaction."""
        # Re-validate terminal status at write boundary (params may bypass prepare).
        status = str(params.get('status') or '')
        if status not in self.BATCH_STATUS_TERMINAL:
            raise CatalogStoreError(
                f'status must be terminal committed|failed, got {status!r}',
                code='validation_error',
            )
        if not params.get('uuid') or not params.get('group_id') or not params.get('batch_id'):
            raise CatalogStoreError(
                'status uuid, group_id, and batch_id are required',
                code='validation_error',
            )
        cypher = self.build_batch_status_upsert_cypher()
        result = await tx.run(cypher, **params)
        row: dict[str, Any] = {}
        if hasattr(result, 'data'):
            rows = await result.data()
            row = rows[0] if rows else {}
        elif hasattr(result, 'single'):
            record = await result.single()
            row = dict(record) if record is not None else {}
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'batch status upsert returned no row',
                code='neo4j_transaction_failed',
            )
        return row

    async def get_batch_status(
        self,
        executor: Any,
        *,
        uuid: str,
        group_id: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        """Read-only MATCH for CatalogIngestBatch by uuid+group_id."""
        if not uuid or not group_id:
            raise CatalogStoreError(
                'status uuid and group_id are required',
                code='validation_error',
            )
        cypher = self.build_get_batch_status_cypher()
        params = {'uuid': uuid, 'group_id': group_id}
        return await self._read_one(executor, cypher, params, tx=tx)

    # ------------------------------------------------------------------
    # Typed edge endpoint resolution + edge upsert
    # ------------------------------------------------------------------

    def resolve_edge_type(self, edge_type: str) -> str:
        """Re-validate edge_type against the fixed server allowlist (EDGE-02)."""
        if edge_type not in CATALOG_EDGE_TYPES:
            raise CatalogStoreError(
                f'edge_type not allowlisted: {edge_type!r}',
                code='validation_error',
            )
        if not _SAFE_LABEL.match(edge_type):
            raise CatalogStoreError(
                f'edge_type unsafe: {edge_type!r}',
                code='validation_error',
            )
        return edge_type

    def build_resolve_endpoint_typed_cypher(self, entity_type: str) -> str:
        """MATCH-only endpoint lookup by group_id + name; never CREATE/MERGE/SET."""
        # Validate allowlist (raises if unknown). Label not interpolated into Cypher:
        # MATCH returns all Entity rows for name so classify can distinguish generic vs typed.
        self.resolve_entity_label(entity_type)
        return """
            MATCH (n:Entity {group_id: $group_id, name: $name})
            RETURN n.uuid AS uuid,
                   n.group_id AS group_id,
                   n.name AS name,
                   n.graph_key AS graph_key,
                   n.labels AS labels,
                   labels(n) AS neo4j_labels,
                   n.content_sha256 AS content_sha256
            """

    def classify_endpoint_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        expected_type: str,
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Classify endpoint MATCH rows into status codes (EDGE-03/04).

        Returns (error_code or None, chosen_row or None).
        Never creates or relabels nodes.
        """
        if not rows:
            return 'missing_endpoint', None

        typed: list[dict[str, Any]] = []
        generic: list[dict[str, Any]] = []
        wrong: list[dict[str, Any]] = []
        for row in rows:
            labels = row.get('neo4j_labels') or row.get('labels') or []
            if isinstance(labels, str):
                labels = [labels]
            custom = [lb for lb in labels if lb != 'Entity']
            if not custom:
                generic.append(row)
            elif set(custom) == {expected_type}:
                # Exactly Entity + one expected custom label; extra labels are wrong_type.
                typed.append(row)
            else:
                wrong.append(row)

        if len(typed) > 1:
            # Ambiguous exact-typed rows: never arbitrary-bind.
            return 'typed_endpoint_duplicate', None
        if typed:
            return None, typed[0]
        if wrong:
            return 'endpoint_type_mismatch', wrong[0]
        if generic:
            return 'generic_endpoint_conflict', generic[0]
        return 'missing_endpoint', None

    async def resolve_endpoint_typed(
        self,
        executor: Any,
        *,
        group_id: str,
        graph_key: str,
        entity_type: str,
        tx: Any | None = None,
        expected_uuid: str | None = None,
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Resolve exact endpoint by group_id + graph_key + entity_type.

        MATCH only; never CREATE. Returns (error_code|None, row|None).
        When expected_uuid is provided, prefer that row among typed matches.
        """
        # Validate type early (raises CatalogStoreError if unknown)
        self.resolve_entity_label(entity_type)
        cypher = self.build_resolve_endpoint_typed_cypher(entity_type)
        params = {'group_id': group_id, 'name': graph_key}
        rows = await self._read_many(executor, cypher, params, tx=tx)
        if expected_uuid is not None:
            typed_exact = [
                r
                for r in rows
                if str(r.get('uuid')) == expected_uuid
                and set(
                    lb for lb in (r.get('neo4j_labels') or r.get('labels') or []) if lb != 'Entity'
                )
                == {entity_type}
            ]
            if typed_exact:
                return None, typed_exact[0]
        code, row = self.classify_endpoint_rows(rows, expected_type=entity_type)
        if code is not None:
            return code, row
        if row is None:
            return 'missing_endpoint', None
        if expected_uuid is not None and str(row.get('uuid')) != expected_uuid:
            return 'deterministic_uuid_conflict', row
        return None, row

    def build_edge_upsert_cypher(self) -> str:
        """MERGE RELATES_TO by uuid; e.name is parameterized allowlisted edge type.

        Endpoints MATCH is group-scoped. Create-token status classification:
        zero property mutation on matched unchanged; vector only on created/updated.
        Identity fields set only ON CREATE.
        """
        # Preserve appended provenance; heal only legacy null for EntityEdge hydration.
        updated_set = """
                e.fact = $fact,
                e.evidence = $evidence,
                e.attributes = $attributes,
                e.confidence = $confidence,
                e.batch_id = $batch_id,
                e.content_sha256 = $content_sha256,
                e.updated_at = $updated_at,
                e.episodes = coalesce(e.episodes, $episodes)
        """.strip()

        return f"""
            MATCH (source:Entity {{uuid: $source_uuid, group_id: $group_id}})
            MATCH (target:Entity {{uuid: $target_uuid, group_id: $group_id}})
            MERGE (source)-[e:RELATES_TO {{uuid: $uuid, group_id: $group_id}}]->(target)
            ON CREATE SET
                e.uuid = $uuid,
                e.group_id = $group_id,
                e.name = $name,
                e.edge_key = $edge_key,
                e.fact = $fact,
                e.evidence = $evidence,
                e.attributes = $attributes,
                e.confidence = $confidence,
                e.batch_id = $batch_id,
                e.content_sha256 = $content_sha256,
                e.source_node_uuid = $source_node_uuid,
                e.target_node_uuid = $target_node_uuid,
                e.created_at = $created_at,
                e.updated_at = $updated_at,
                // Empty list so stock EntityEdge/search hydration never sees episodes=None.
                e.episodes = $episodes,
                e._catalog_create_token = $create_token
            WITH e,
                 coalesce(e._catalog_create_token, '') = $create_token AS created,
                 e.content_sha256 = $content_sha256 AS same
            WITH e, created, same,
                 CASE
                   WHEN created THEN 'created'
                   WHEN same THEN 'unchanged'
                   ELSE 'updated'
                 END AS status
            FOREACH (_ IN CASE WHEN status = 'updated' THEN [1] ELSE [] END |
              SET {updated_set}
            )
            REMOVE e._catalog_create_token
            WITH e, status
            CALL {{
              WITH e, status
              WITH e, status WHERE status IN ['created', 'updated']
              CALL db.create.setRelationshipVectorProperty(e, 'fact_embedding', $fact_embedding)
              RETURN 1 AS _
              UNION
              WITH e, status
              WITH e, status WHERE status = 'unchanged'
              RETURN 0 AS _
            }}
            RETURN e.uuid AS uuid,
                   e.content_sha256 AS content_sha256,
                   e.batch_id AS batch_id,
                   e.created_at AS created_at,
                   e.updated_at AS updated_at,
                   e.name AS name,
                   e.edge_key AS edge_key,
                   e.source_node_uuid AS source_uuid,
                   e.target_node_uuid AS target_uuid,
                   status
            """

    def build_get_edge_by_uuid_cypher(self) -> str:
        return """
            MATCH (s:Entity)-[e:RELATES_TO {uuid: $uuid}]->(t:Entity)
            WHERE e.group_id = $group_id
            RETURN e.uuid AS uuid,
                   e.group_id AS group_id,
                   e.name AS name,
                   e.edge_key AS edge_key,
                   e.fact AS fact,
                   e.content_sha256 AS content_sha256,
                   e.batch_id AS batch_id,
                   e.created_at AS created_at,
                   e.updated_at AS updated_at,
                   e.fact_embedding IS NOT NULL AS has_fact_embedding,
                   coalesce(e.episodes, []) AS episodes,
                   coalesce(e.source_node_uuid, s.uuid) AS source_uuid,
                   coalesce(e.target_node_uuid, t.uuid) AS target_uuid,
                   s.uuid AS source_node_uuid,
                   t.uuid AS target_node_uuid
            """

    def prepare_edge_params(
        self,
        *,
        edge_type: str,
        uuid: str,
        group_id: str,
        batch_id: str,
        edge_key: str,
        source_uuid: str,
        target_uuid: str,
        fact: str,
        content_sha256: str,
        created_at: datetime,
        updated_at: datetime,
        fact_embedding: list[float],
        evidence: str | None = None,
        attributes: dict[str, Any] | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        """Build parameterized property map for edge upsert.

        e.name is the allowlisted edge_type. Nested maps JSON-serialized.
        """
        name = self.resolve_edge_type(edge_type)
        cleaned_attrs = _strip_protected_attributes(attributes)
        return {
            'uuid': uuid,
            'group_id': group_id,
            'batch_id': batch_id,
            'name': name,
            'edge_key': edge_key,
            'source_uuid': source_uuid,
            'target_uuid': target_uuid,
            'source_node_uuid': source_uuid,
            'target_node_uuid': target_uuid,
            'fact': fact,
            'evidence': evidence,
            'content_sha256': content_sha256,
            'created_at': created_at,
            'updated_at': updated_at,
            'fact_embedding': fact_embedding,
            'attributes': serialize_nested_json(cleaned_attrs),
            'confidence': confidence,
            # Catalog edges have no episode provenance in Phase 1; keep list (not null)
            # so graphiti_core EntityEdge/search paths do not ValidationError.
            'episodes': [],
            # Per-write create marker only; never client authority, never persisted.
            'create_token': uuid4().hex,
        }

    def detect_edge_identity_conflict(
        self,
        existing: dict[str, Any],
        *,
        edge_type: str,
        edge_key: str,
        source_uuid: str,
        target_uuid: str,
    ) -> str | None:
        """Return edge_identity_conflict when uuid exists with conflicting fields."""
        existing_name = existing.get('name')
        existing_key = existing.get('edge_key')
        existing_src = existing.get('source_uuid') or existing.get('source_node_uuid')
        existing_tgt = existing.get('target_uuid') or existing.get('target_node_uuid')
        if (
            (existing_name is not None and existing_name != edge_type)
            or (existing_key is not None and existing_key != edge_key)
            or (existing_src is not None and str(existing_src) != str(source_uuid))
            or (existing_tgt is not None and str(existing_tgt) != str(target_uuid))
        ):
            return 'edge_identity_conflict'
        return None

    async def get_edge_by_uuid(
        self,
        executor: Any,
        *,
        uuid: str,
        group_id: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        cypher = self.build_get_edge_by_uuid_cypher()
        params = {'uuid': uuid, 'group_id': group_id}
        return await self._read_one(executor, cypher, params, tx=tx)

    async def upsert_edge_item(
        self,
        tx: Any,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute edge MERGE inside an open transaction. Returns first record dict.

        Empty/missing uuid (endpoint group miss or write failure) raises — never {}.
        """
        # Re-validate edge type from params['name'] at builder boundary
        self.resolve_edge_type(str(params.get('name') or ''))
        cypher = self.build_edge_upsert_cypher()
        result = await tx.run(cypher, **params)
        row: dict[str, Any] = {}
        if hasattr(result, 'data'):
            rows = await result.data()
            row = rows[0] if rows else {}
        elif hasattr(result, 'single'):
            record = await result.single()
            row = dict(record) if record is not None else {}
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'edge upsert returned no row (endpoint miss, group mismatch, or write failure)',
                code='neo4j_transaction_failed',
            )
        return row

    # ------------------------------------------------------------------
    # Prepared-plan control plane (PLAN-05/09/11/18/19; fixed labels only)
    # ------------------------------------------------------------------

    def plan_schema_constraint_statements(self) -> tuple[str, ...]:
        """Fixed CREATE CONSTRAINT IF NOT EXISTS for plan/chunk uniqueness."""
        return (
            _CREATE_PREPARED_PLAN_IDENTITY_UNIQUE,
            _CREATE_PREPARED_PLAN_TOKEN_DIGEST_UNIQUE,
            _CREATE_PREPARED_PLAN_CHUNK_IDENTITY_UNIQUE,
            _CREATE_PREPARED_PLAN_CHUNK_INDEX_UNIQUE,
        )

    async def ensure_plan_schema(self, executor: Any) -> None:
        """Idempotent plan/chunk uniqueness constraints. CREATE only, never DROP.

        Mirrors domain identity ensure: process-local lock + once-ready flag and
        post-CREATE SHOW CONSTRAINTS shape verification (fail closed).
        """
        if self._plan_schema_ready:
            return
        async with self._plan_schema_lock:
            if self._plan_schema_ready:
                return
            await self._ensure_plan_schema_locked(executor)
            self._plan_schema_ready = True

    async def _ensure_plan_schema_locked(self, executor: Any) -> None:
        if await self._plan_uniqueness_present(executor):
            return

        for stmt in self.plan_schema_constraint_statements():
            assert 'DROP' not in stmt.upper()
            try:
                await self._run_schema_query(executor, stmt)
            except CatalogStoreError:
                raise
            except Exception as exc:
                msg = f'{type(exc).__name__}: {exc}'
                if (
                    'EquivalentSchemaRuleAlreadyExists' in msg
                    or 'already exists' in msg.lower()
                    or 'ConstraintAlreadyExists' in msg
                ):
                    continue
                if (
                    'ConstraintValidationFailed' in msg
                    or 'already has' in msg.lower()
                    or 'duplicate' in msg.lower()
                ):
                    raise CatalogStoreError(
                        'prepared-plan uniqueness constraint failed: existing duplicates',
                        code='neo4j_schema_failed',
                    ) from exc
                raise CatalogStoreError(
                    f'prepared-plan schema init failed: {type(exc).__name__}',
                    code='neo4j_schema_failed',
                ) from exc

        if not await self._plan_uniqueness_present(executor):
            raise CatalogStoreError(
                'prepared-plan uniqueness constraints not present after init',
                code='neo4j_schema_failed',
            )
        logger.info(
            'catalog plan schema ready constraints=%s,%s,%s,%s',
            CATALOG_PREPARED_PLAN_IDENTITY_CONSTRAINT,
            CATALOG_PREPARED_PLAN_TOKEN_DIGEST_CONSTRAINT,
            CATALOG_PREPARED_PLAN_CHUNK_IDENTITY_CONSTRAINT,
            CATALOG_PREPARED_PLAN_CHUNK_INDEX_CONSTRAINT,
        )

    async def _plan_uniqueness_present(self, executor: Any) -> bool:
        """True when all plan/chunk named constraints have exact uniqueness shape."""
        try:
            result = await self._run_schema_query(
                executor,
                """
                SHOW CONSTRAINTS
                YIELD name, type, entityType, labelsOrTypes, properties
                RETURN name, type, entityType, labelsOrTypes, properties
                """,
            )
        except Exception:
            return False
        rows = self._all_from_execute_query_result(result)
        plan_id_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_PREPARED_PLAN_IDENTITY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogPreparedPlan',
                expected_properties={'uuid', 'group_id'},
            )
            for row in rows
        )
        token_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_PREPARED_PLAN_TOKEN_DIGEST_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogPreparedPlan',
                expected_properties={'token_digest'},
            )
            for row in rows
        )
        chunk_id_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_PREPARED_PLAN_CHUNK_IDENTITY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogPreparedPlanChunk',
                expected_properties={'uuid', 'group_id'},
            )
            for row in rows
        )
        chunk_idx_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_PREPARED_PLAN_CHUNK_INDEX_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogPreparedPlanChunk',
                expected_properties={'plan_uuid', 'group_id', 'chunk_index'},
            )
            for row in rows
        )
        return plan_id_ok and token_ok and chunk_id_ok and chunk_idx_ok

    def build_plan_group_lock_cypher(self) -> str:
        """MERGE group lock for capacity serialization (same-tx with create)."""
        return """
            MERGE (lock:CatalogPlanGroupLock {group_id: $group_id})
            RETURN lock.group_id AS group_id, true AS locked
            """

    def build_count_active_plans_cypher(self) -> str:
        """Count active plans: PREPARED (unexpired) or COMMITTING (D-25)."""
        return """
            MATCH (p:CatalogPreparedPlan {group_id: $group_id})
            WHERE p.state IN ['PREPARED', 'COMMITTING']
              AND (p.state = 'COMMITTING' OR p.expires_at > $now)
            RETURN count(p) AS active
            """

    def build_existing_prepared_plan_cypher(self) -> str:
        """MATCH existing plan root by deterministic uuid+group_id."""
        return """
            MATCH (p:CatalogPreparedPlan {uuid: $uuid, group_id: $group_id})
            RETURN p.uuid AS uuid,
                   p.group_id AS group_id,
                   p.state AS state,
                   p.artifact_sha256 AS artifact_sha256,
                   p.token_digest AS token_digest,
                   p.request_sha256 AS request_sha256,
                   p.catalog_sha256 AS catalog_sha256,
                   p.expires_at AS expires_at
            """

    def build_create_prepared_plan_cypher(self) -> str:
        """CREATE-once plan root (never MERGE-update artifact bytes)."""
        return """
            CREATE (plan:CatalogPreparedPlan {
                uuid: $uuid,
                group_id: $group_id,
                batch_id: $batch_id,
                plan_id: $plan_id,
                token_digest: $token_digest,
                state: $state,
                identity_schema_version: $identity_schema_version,
                canonicalization_version: $canonicalization_version,
                artifact_serialization_version: $artifact_serialization_version,
                request_sha256: $request_sha256,
                catalog_sha256: $catalog_sha256,
                artifact_sha256: $artifact_sha256,
                chunk_count: $chunk_count,
                payload_bytes: $payload_bytes,
                entity_count: $entity_count,
                edge_count: $edge_count,
                source_count: $source_count,
                evidence_link_count: $evidence_link_count,
                created_count: $created_count,
                updated_count: $updated_count,
                unchanged_count: $unchanged_count,
                expires_at: $expires_at,
                created_at: $created_at,
                updated_at: $updated_at
            })
            RETURN plan.uuid AS uuid,
                   plan.group_id AS group_id,
                   plan.state AS state,
                   plan.token_digest AS token_digest,
                   plan.artifact_sha256 AS artifact_sha256,
                   plan.chunk_count AS chunk_count,
                   plan.payload_bytes AS payload_bytes,
                   plan.expires_at AS expires_at
            """

    def build_create_prepared_plan_chunk_cypher(self) -> str:
        """CREATE-once ordered chunk record; payload_b64 is base64 ASCII only."""
        return """
            CREATE (c:CatalogPreparedPlanChunk {
                uuid: $uuid,
                group_id: $group_id,
                plan_uuid: $plan_uuid,
                chunk_index: $chunk_index,
                chunk_count: $chunk_count,
                byte_offset: $byte_offset,
                byte_length: $byte_length,
                chunk_sha256: $chunk_sha256,
                payload_b64: $payload_b64
            })
            RETURN c.uuid AS uuid,
                   c.plan_uuid AS plan_uuid,
                   c.chunk_index AS chunk_index,
                   c.byte_offset AS byte_offset,
                   c.byte_length AS byte_length,
                   c.chunk_sha256 AS chunk_sha256
            """

    def build_load_prepared_plan_by_token_digest_cypher(self) -> str:
        """Load plan root by unique token_digest (never raw token)."""
        return """
            MATCH (p:CatalogPreparedPlan {token_digest: $token_digest})
            RETURN p.uuid AS uuid,
                   p.group_id AS group_id,
                   p.batch_id AS batch_id,
                   p.plan_id AS plan_id,
                   p.token_digest AS token_digest,
                   p.state AS state,
                   p.identity_schema_version AS identity_schema_version,
                   p.canonicalization_version AS canonicalization_version,
                   p.artifact_serialization_version AS artifact_serialization_version,
                   p.request_sha256 AS request_sha256,
                   p.catalog_sha256 AS catalog_sha256,
                   p.artifact_sha256 AS artifact_sha256,
                   p.chunk_count AS chunk_count,
                   p.payload_bytes AS payload_bytes,
                   p.entity_count AS entity_count,
                   p.edge_count AS edge_count,
                   p.source_count AS source_count,
                   p.evidence_link_count AS evidence_link_count,
                   p.created_count AS created_count,
                   p.updated_count AS updated_count,
                   p.unchanged_count AS unchanged_count,
                   p.expires_at AS expires_at,
                   p.created_at AS created_at,
                   p.updated_at AS updated_at,
                   p.committing_started_at AS committing_started_at
            """

    def build_load_prepared_plan_chunks_cypher(self) -> str:
        """Load ordered chunks for a plan uuid+group_id."""
        return """
            MATCH (c:CatalogPreparedPlanChunk {plan_uuid: $plan_uuid, group_id: $group_id})
            RETURN c.uuid AS uuid,
                   c.group_id AS group_id,
                   c.plan_uuid AS plan_uuid,
                   c.chunk_index AS chunk_index,
                   c.chunk_count AS chunk_count,
                   c.byte_offset AS byte_offset,
                   c.byte_length AS byte_length,
                   c.chunk_sha256 AS chunk_sha256,
                   c.payload_b64 AS payload_b64
            ORDER BY c.chunk_index ASC
            """

    def build_cas_plan_state_cypher(self) -> str:
        """CAS state transition: MATCH expected from-state then SET to-state."""
        return """
            MATCH (p:CatalogPreparedPlan {token_digest: $token_digest})
            WHERE p.state = $expected_from
            SET p.state = $to_state,
                p.updated_at = $updated_at,
                p.committing_started_at = CASE
                    WHEN $to_state = 'COMMITTING' AND $expected_from = 'PREPARED'
                    THEN $updated_at
                    ELSE p.committing_started_at
                END
            RETURN p.uuid AS uuid,
                   p.group_id AS group_id,
                   p.token_digest AS token_digest,
                   p.state AS state,
                   p.artifact_sha256 AS artifact_sha256,
                   p.expires_at AS expires_at,
                   p.updated_at AS updated_at,
                   p.committing_started_at AS committing_started_at
            """

    def prepare_prepared_plan_params(self, **fields: Any) -> dict[str, Any]:
        """Allowlisted plan root params; reject raw token / embedding keys."""
        for key in fields:
            if key in _FORBIDDEN_PLAN_PARAM_KEYS:
                if fields[key] is not None:
                    raise CatalogStoreError(
                        f'forbidden plan param key: {key}',
                        code='validation_error',
                    )
                continue
            if key not in _PLAN_ROOT_PROP_KEYS:
                raise CatalogStoreError(
                    f'unknown plan param key: {key}',
                    code='validation_error',
                )
        required = (
            'uuid',
            'group_id',
            'batch_id',
            'plan_id',
            'token_digest',
            'request_sha256',
            'catalog_sha256',
            'artifact_sha256',
            'chunk_count',
            'payload_bytes',
            'expires_at',
            'created_at',
            'updated_at',
        )
        for key in required:
            val = fields.get(key)
            if val is None or (isinstance(val, str) and not str(val).strip()):
                raise CatalogStoreError(
                    f'plan field {key} is required',
                    code='validation_error',
                )
        payload_bytes = int(fields['payload_bytes'])
        if payload_bytes < 0 or payload_bytes > HARD_MAX_PREPARED_PAYLOAD_BYTES:
            raise CatalogStoreError(
                'payload_bytes out of hard ceiling',
                code='batch_limit_exceeded',
            )
        chunk_count = int(fields['chunk_count'])
        if chunk_count < 1 or chunk_count > HARD_MAX_CHUNKS_PER_PLAN:
            raise CatalogStoreError(
                'chunk_count out of hard ceiling',
                code='batch_limit_exceeded',
            )
        state = str(fields.get('state') or PLAN_STATE_PREPARED)
        if state not in PLAN_STATES:
            raise CatalogStoreError(
                f'invalid plan state {state!r}',
                code='validation_error',
            )
        if state != PLAN_STATE_PREPARED:
            raise CatalogStoreError(
                'create path requires PREPARED state',
                code='validation_error',
            )
        out: dict[str, Any] = {
            'uuid': str(fields['uuid']),
            'group_id': str(fields['group_id']),
            'batch_id': str(fields['batch_id']),
            'plan_id': str(fields['plan_id']),
            'token_digest': str(fields['token_digest']),
            'state': PLAN_STATE_PREPARED,
            'identity_schema_version': str(fields.get('identity_schema_version') or 'catalog-v2'),
            'canonicalization_version': str(
                fields.get('canonicalization_version') or CANONICALIZATION_VERSION
            ),
            'artifact_serialization_version': str(
                fields.get('artifact_serialization_version') or 'prepared-artifact-v1'
            ),
            'request_sha256': str(fields['request_sha256']),
            'catalog_sha256': str(fields['catalog_sha256']),
            'artifact_sha256': str(fields['artifact_sha256']),
            'chunk_count': chunk_count,
            'payload_bytes': payload_bytes,
            'entity_count': int(fields.get('entity_count') or 0),
            'edge_count': int(fields.get('edge_count') or 0),
            'source_count': int(fields.get('source_count') or 0),
            'evidence_link_count': int(fields.get('evidence_link_count') or 0),
            'created_count': int(fields.get('created_count') or 0),
            'updated_count': int(fields.get('updated_count') or 0),
            'unchanged_count': int(fields.get('unchanged_count') or 0),
            'expires_at': fields['expires_at'],
            'created_at': fields['created_at'],
            'updated_at': fields['updated_at'],
        }
        for bad in _FORBIDDEN_PLAN_PARAM_KEYS:
            out.pop(bad, None)
        return out

    def prepare_prepared_plan_chunk_params(self, **fields: Any) -> dict[str, Any]:
        """Allowlisted chunk params; payload_b64 is ASCII base64 storage."""
        for key in fields:
            if key in _FORBIDDEN_PLAN_PARAM_KEYS:
                if fields[key] is not None:
                    raise CatalogStoreError(
                        f'forbidden chunk param key: {key}',
                        code='validation_error',
                    )
                continue
            if key not in _PLAN_CHUNK_PROP_KEYS:
                raise CatalogStoreError(
                    f'unknown plan chunk param key: {key}',
                    code='validation_error',
                )
        required = (
            'uuid',
            'group_id',
            'plan_uuid',
            'chunk_index',
            'chunk_count',
            'byte_offset',
            'byte_length',
            'chunk_sha256',
            'payload_b64',
        )
        for key in required:
            if fields.get(key) is None:
                raise CatalogStoreError(
                    f'chunk field {key} is required',
                    code='validation_error',
                )
        index = int(fields['chunk_index'])
        if index < 0:
            raise CatalogStoreError('chunk_index must be >= 0', code='validation_error')
        payload_b64 = fields['payload_b64']
        if not isinstance(payload_b64, str):
            raise CatalogStoreError('payload_b64 must be str', code='validation_error')
        return {
            'uuid': str(fields['uuid']),
            'group_id': str(fields['group_id']),
            'plan_uuid': str(fields['plan_uuid']),
            'chunk_index': index,
            'chunk_count': int(fields['chunk_count']),
            'byte_offset': int(fields['byte_offset']),
            'byte_length': int(fields['byte_length']),
            'chunk_sha256': str(fields['chunk_sha256']),
            'payload_b64': payload_b64,
        }

    async def count_active_plans_for_group(
        self,
        tx: Any,
        *,
        group_id: str,
        now: datetime,
    ) -> int:
        """Count PREPARED|COMMITTING active plans under group (D-25)."""
        if not group_id:
            raise CatalogStoreError('group_id is required', code='validation_error')
        result = await tx.run(
            self.build_count_active_plans_cypher(),
            group_id=group_id,
            now=now,
        )
        row = await self._first_from_tx_result(result)
        if not row:
            return 0
        return int(row.get('active') or 0)

    @staticmethod
    def _is_uniqueness_constraint_race(exc: BaseException) -> bool:
        """True when Neo4j reports a uniqueness/constraint race on CREATE."""
        msg = f'{type(exc).__name__}: {exc}'.lower()
        markers = (
            'constraintvalidationfailed',
            'constraint error',
            'already exists with',
            'already exists',
            'uniqueness',
            'unique constraint',
            'entityalreadyexists',
            'neo.clienterror.schema.constrainvalidationfailed',
            'neo.clienterror.schema.constraintvalidationfailed',
        )
        return any(m in msg for m in markers)

    async def create_prepared_plan_with_chunks(
        self,
        tx: Any,
        *,
        plan: dict[str, Any],
        chunks: list[dict[str, Any]],
        max_active: int,
        now: datetime,
    ) -> dict[str, Any]:
        """Capacity-locked CREATE-once of plan root + ordered chunks.

        Same plan identity with any existing row → prepared_plan_conflict.
        Capacity full → batch_limit_exceeded. Never writes Entity/domain labels.
        """
        plan_params = self.prepare_prepared_plan_params(**plan)
        if not chunks:
            raise CatalogStoreError('at least one chunk required', code='validation_error')
        if len(chunks) != int(plan_params['chunk_count']):
            raise CatalogStoreError(
                'chunk_count does not match chunks length',
                code='validation_error',
            )
        if max_active < 1 or max_active > HARD_MAX_ACTIVE_PLANS_PER_GROUP:
            raise CatalogStoreError(
                'max_active out of hard ceiling',
                code='batch_limit_exceeded',
            )
        group_id = plan_params['group_id']

        lock_res = await tx.run(
            self.build_plan_group_lock_cypher(),
            group_id=group_id,
        )
        lock_row = await self._first_from_tx_result(lock_res)
        if not lock_row:
            raise CatalogStoreError(
                'plan group lock failed',
                code='neo4j_transaction_failed',
            )

        active = await self.count_active_plans_for_group(tx, group_id=group_id, now=now)
        if active >= max_active:
            raise CatalogStoreError(
                f'active prepared plans at capacity ({active}>={max_active})',
                code='batch_limit_exceeded',
            )

        existing_res = await tx.run(
            self.build_existing_prepared_plan_cypher(),
            uuid=plan_params['uuid'],
            group_id=group_id,
        )
        existing = await self._first_from_tx_result(existing_res)
        if existing and existing.get('uuid'):
            raise CatalogStoreError(
                'prepared plan identity already exists',
                code='prepared_plan_conflict',
            )

        try:
            create_res = await tx.run(self.build_create_prepared_plan_cypher(), **plan_params)
            created = await self._first_from_tx_result(create_res)
        except CatalogStoreError:
            raise
        except Exception as exc:
            if self._is_uniqueness_constraint_race(exc):
                raise CatalogStoreError(
                    'prepared plan identity already exists',
                    code='prepared_plan_conflict',
                ) from exc
            raise CatalogStoreError(
                f'prepared plan create failed: {type(exc).__name__}',
                code='neo4j_transaction_failed',
            ) from exc
        if not created or not created.get('uuid'):
            raise CatalogStoreError(
                'prepared plan create returned no row',
                code='neo4j_transaction_failed',
            )

        ordered = sorted(chunks, key=lambda c: int(c['chunk_index']))
        for ch in ordered:
            ch_params = self.prepare_prepared_plan_chunk_params(**ch)
            if ch_params['plan_uuid'] != plan_params['uuid']:
                raise CatalogStoreError(
                    'chunk plan_uuid mismatch',
                    code='validation_error',
                )
            if ch_params['group_id'] != group_id:
                raise CatalogStoreError(
                    'chunk group_id mismatch',
                    code='validation_error',
                )
            try:
                ch_res = await tx.run(
                    self.build_create_prepared_plan_chunk_cypher(),
                    **ch_params,
                )
                ch_row = await self._first_from_tx_result(ch_res)
            except CatalogStoreError:
                raise
            except Exception as exc:
                if self._is_uniqueness_constraint_race(exc):
                    raise CatalogStoreError(
                        'prepared plan chunk identity already exists',
                        code='prepared_plan_conflict',
                    ) from exc
                raise CatalogStoreError(
                    f'prepared plan chunk create failed: {type(exc).__name__}',
                    code='neo4j_transaction_failed',
                ) from exc
            if not ch_row or not ch_row.get('uuid'):
                raise CatalogStoreError(
                    'prepared plan chunk create returned no row',
                    code='neo4j_transaction_failed',
                )

        return created

    async def load_prepared_plan_by_token_digest(
        self,
        executor: Any,
        *,
        token_digest: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        """Load plan root by token_digest only (no raw token)."""
        if not token_digest or not str(token_digest).strip():
            raise CatalogStoreError(
                'token_digest is required',
                code='validation_error',
            )
        return await self._read_one(
            executor,
            self.build_load_prepared_plan_by_token_digest_cypher(),
            {'token_digest': str(token_digest)},
            tx=tx,
        )

    async def load_prepared_plan_chunks(
        self,
        executor: Any,
        *,
        plan_uuid: str,
        group_id: str,
        tx: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Load ordered chunk records for a plan."""
        if not plan_uuid or not group_id:
            raise CatalogStoreError(
                'plan_uuid and group_id are required',
                code='validation_error',
            )
        return await self._read_many(
            executor,
            self.build_load_prepared_plan_chunks_cypher(),
            {'plan_uuid': str(plan_uuid), 'group_id': str(group_id)},
            tx=tx,
        )

    async def cas_plan_state(
        self,
        tx: Any,
        *,
        token_digest: str,
        expected_from: str,
        to_state: str,
        updated_at: datetime,
        now: datetime | None = None,
        require_not_expired: bool = False,
    ) -> dict[str, Any]:
        """Compare-and-set plan state under legal transition table (PLAN-18/19).

        Zero-row CAS maps to structured prepared-plan codes after a load.
        COMMITTING→PREPARED is never legal. Terminal states never revive.
        """
        if not token_digest:
            raise CatalogStoreError('token_digest is required', code='validation_error')
        if expected_from not in PLAN_STATES or to_state not in PLAN_STATES:
            raise CatalogStoreError(
                'invalid plan state for CAS',
                code='validation_error',
            )
        allowed = _PLAN_CAS_LEGAL.get(expected_from, frozenset())
        if to_state not in allowed:
            raise CatalogStoreError(
                f'illegal plan transition {expected_from}->{to_state}',
                code='prepared_plan_conflict',
            )
        if to_state == PLAN_STATE_PREPARED:
            raise CatalogStoreError(
                'transition to PREPARED is forbidden',
                code='prepared_plan_conflict',
            )

        current = await self.load_prepared_plan_by_token_digest(
            None, token_digest=token_digest, tx=tx
        )
        if current is None:
            raise CatalogStoreError(
                'prepared plan not found',
                code='prepared_plan_not_found',
            )

        current_state = str(current.get('state') or '')
        expires_at = current.get('expires_at')

        if to_state == PLAN_STATE_EXPIRED:
            if current_state != PLAN_STATE_PREPARED:
                raise CatalogStoreError(
                    'only PREPARED plans may expire',
                    code='prepared_plan_conflict',
                )
            if now is None:
                raise CatalogStoreError(
                    'now is required for expiry CAS',
                    code='validation_error',
                )
            if expires_at is not None and now < expires_at:
                raise CatalogStoreError(
                    'plan not yet expired',
                    code='prepared_plan_conflict',
                )

        if to_state == PLAN_STATE_DISCARDED and current_state == PLAN_STATE_DISCARDED:
            return {
                'uuid': current.get('uuid'),
                'group_id': current.get('group_id'),
                'token_digest': current.get('token_digest'),
                'state': PLAN_STATE_DISCARDED,
                'artifact_sha256': current.get('artifact_sha256'),
                'expires_at': expires_at,
                'updated_at': current.get('updated_at'),
                'idempotent': True,
            }

        if to_state == PLAN_STATE_DISCARDED:
            if current_state in {PLAN_STATE_COMMITTING, PLAN_STATE_COMMITTED}:
                raise CatalogStoreError(
                    'cannot discard committing/committed plan',
                    code='prepared_plan_conflict',
                )
            if current_state == PLAN_STATE_EXPIRED:
                raise CatalogStoreError(
                    'prepared plan expired',
                    code='prepared_plan_expired',
                )
            if current_state != PLAN_STATE_PREPARED:
                raise CatalogStoreError(
                    'prepared plan not discardable',
                    code='prepared_plan_conflict',
                )

        if to_state == PLAN_STATE_COMMITTING:
            if current_state == PLAN_STATE_COMMITTED:
                raise CatalogStoreError(
                    'prepared plan already consumed',
                    code='prepared_plan_already_consumed',
                )
            if current_state == PLAN_STATE_DISCARDED:
                raise CatalogStoreError(
                    'prepared plan not found',
                    code='prepared_plan_not_found',
                )
            if current_state == PLAN_STATE_EXPIRED:
                raise CatalogStoreError(
                    'prepared plan expired',
                    code='prepared_plan_expired',
                )
            if current_state not in {PLAN_STATE_PREPARED, PLAN_STATE_COMMITTING}:
                raise CatalogStoreError(
                    'prepared plan not claimable',
                    code='prepared_plan_conflict',
                )
            if (
                require_not_expired
                and current_state == PLAN_STATE_PREPARED
                and now is not None
                and expires_at is not None
                and now >= expires_at
            ):
                await self._cas_plan_state_raw(
                    tx,
                    token_digest=token_digest,
                    expected_from=PLAN_STATE_PREPARED,
                    to_state=PLAN_STATE_EXPIRED,
                    updated_at=updated_at,
                )
                raise CatalogStoreError(
                    'prepared plan expired',
                    code='prepared_plan_expired',
                )
            if current_state == PLAN_STATE_COMMITTING and expected_from == PLAN_STATE_COMMITTING:
                return {
                    'uuid': current.get('uuid'),
                    'group_id': current.get('group_id'),
                    'token_digest': current.get('token_digest'),
                    'state': PLAN_STATE_COMMITTING,
                    'artifact_sha256': current.get('artifact_sha256'),
                    'expires_at': expires_at,
                    'updated_at': current.get('updated_at'),
                    'committing_started_at': current.get('committing_started_at'),
                    'reentry': True,
                }

        if to_state == PLAN_STATE_COMMITTED:
            if current_state == PLAN_STATE_COMMITTED:
                raise CatalogStoreError(
                    'prepared plan already consumed',
                    code='prepared_plan_already_consumed',
                )
            if current_state != PLAN_STATE_COMMITTING:
                raise CatalogStoreError(
                    'only COMMITTING plans may commit',
                    code='prepared_plan_conflict',
                )

        if current_state != expected_from:
            if current_state == PLAN_STATE_COMMITTED:
                raise CatalogStoreError(
                    'prepared plan already consumed',
                    code='prepared_plan_already_consumed',
                )
            if current_state == PLAN_STATE_EXPIRED:
                raise CatalogStoreError(
                    'prepared plan expired',
                    code='prepared_plan_expired',
                )
            if current_state == PLAN_STATE_DISCARDED:
                raise CatalogStoreError(
                    'prepared plan not found',
                    code='prepared_plan_not_found',
                )
            raise CatalogStoreError(
                f'plan state mismatch: have {current_state}, expected {expected_from}',
                code='prepared_plan_conflict',
            )

        row = await self._cas_plan_state_raw(
            tx,
            token_digest=token_digest,
            expected_from=expected_from,
            to_state=to_state,
            updated_at=updated_at,
        )
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'plan CAS returned no row',
                code='prepared_plan_conflict',
            )
        return row

    async def _cas_plan_state_raw(
        self,
        tx: Any,
        *,
        token_digest: str,
        expected_from: str,
        to_state: str,
        updated_at: datetime,
    ) -> dict[str, Any] | None:
        result = await tx.run(
            self.build_cas_plan_state_cypher(),
            token_digest=token_digest,
            expected_from=expected_from,
            to_state=to_state,
            updated_at=updated_at,
        )
        return await self._first_from_tx_result(result)

    # ------------------------------------------------------------------
    # Exact evidence control records + durable manifest (03B-03)
    # ------------------------------------------------------------------

    def evidence_manifest_schema_constraint_statements(self) -> tuple[str, ...]:
        """Fixed CREATE CONSTRAINT IF NOT EXISTS for evidence/manifest uniqueness."""
        return (
            _CREATE_EVIDENCE_LINK_IDENTITY_UNIQUE,
            _CREATE_EVIDENCE_LINK_KEY_UNIQUE,
            _CREATE_MANIFEST_IDENTITY_UNIQUE,
            _CREATE_MANIFEST_CHUNK_IDENTITY_UNIQUE,
            _CREATE_MANIFEST_CHUNK_INDEX_UNIQUE,
        )

    async def ensure_evidence_manifest_schema(self, executor: Any) -> None:
        """Idempotent evidence/manifest uniqueness. CREATE only, never DROP.

        Outside success transaction (same pattern as ensure_plan_schema).
        """
        if self._evidence_manifest_schema_ready:
            return
        async with self._evidence_manifest_schema_lock:
            if self._evidence_manifest_schema_ready:
                return
            await self._ensure_evidence_manifest_schema_locked(executor)
            self._evidence_manifest_schema_ready = True

    async def _ensure_evidence_manifest_schema_locked(self, executor: Any) -> None:
        if await self._evidence_manifest_uniqueness_present(executor):
            return

        for stmt in self.evidence_manifest_schema_constraint_statements():
            assert 'DROP' not in stmt.upper()
            try:
                await self._run_schema_query(executor, stmt)
            except CatalogStoreError:
                raise
            except Exception as exc:
                msg = f'{type(exc).__name__}: {exc}'
                if (
                    'EquivalentSchemaRuleAlreadyExists' in msg
                    or 'already exists' in msg.lower()
                    or 'ConstraintAlreadyExists' in msg
                ):
                    continue
                if (
                    'ConstraintValidationFailed' in msg
                    or 'already has' in msg.lower()
                    or 'duplicate' in msg.lower()
                ):
                    raise CatalogStoreError(
                        'evidence/manifest uniqueness constraint failed: existing duplicates',
                        code='neo4j_schema_failed',
                    ) from exc
                raise CatalogStoreError(
                    f'evidence/manifest schema init failed: {type(exc).__name__}',
                    code='neo4j_schema_failed',
                ) from exc

        if not await self._evidence_manifest_uniqueness_present(executor):
            raise CatalogStoreError(
                'evidence/manifest uniqueness constraints not present after init',
                code='neo4j_schema_failed',
            )
        logger.info(
            'catalog evidence/manifest schema ready constraints=%s,%s,%s,%s,%s',
            CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT,
            CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT,
            CATALOG_MANIFEST_IDENTITY_CONSTRAINT,
            CATALOG_MANIFEST_CHUNK_IDENTITY_CONSTRAINT,
            CATALOG_MANIFEST_CHUNK_INDEX_CONSTRAINT,
        )

    async def _evidence_manifest_uniqueness_present(self, executor: Any) -> bool:
        try:
            result = await self._run_schema_query(
                executor,
                """
                SHOW CONSTRAINTS
                YIELD name, type, entityType, labelsOrTypes, properties
                RETURN name, type, entityType, labelsOrTypes, properties
                """,
            )
        except Exception:
            return False
        rows = self._all_from_execute_query_result(result)
        evidence_id_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogEvidenceLink',
                expected_properties={'uuid', 'group_id'},
            )
            for row in rows
        )
        evidence_key_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogEvidenceLink',
                expected_properties={'group_id', 'link_key'},
            )
            for row in rows
        )
        manifest_id_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_MANIFEST_IDENTITY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogBatchManifest',
                expected_properties={'uuid', 'group_id'},
            )
            for row in rows
        )
        chunk_id_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_MANIFEST_CHUNK_IDENTITY_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogBatchManifestChunk',
                expected_properties={'uuid', 'group_id'},
            )
            for row in rows
        )
        chunk_idx_ok = any(
            self._constraint_row_matches(
                row,
                expected_name=CATALOG_MANIFEST_CHUNK_INDEX_CONSTRAINT,
                expected_entity_type='NODE',
                expected_label='CatalogBatchManifestChunk',
                expected_properties={'manifest_uuid', 'group_id', 'chunk_index'},
            )
            for row in rows
        )
        return (
            evidence_id_ok and evidence_key_ok and manifest_id_ok and chunk_id_ok and chunk_idx_ok
        )

    def build_resolve_evidence_source_cypher(self) -> str:
        """MATCH Episodic source by uuid+group_id (property-touch lock)."""
        return """
            MATCH (n:Episodic {uuid: $source_uuid, group_id: $group_id})
            SET n.uuid = n.uuid
            RETURN n.uuid AS uuid, 'source' AS kind
            """

    def build_resolve_evidence_target_cypher(self) -> str:
        """MATCH typed target under group_id; entity or edge only."""
        return """
            CALL {
              WITH $target_kind AS kind, $target_uuid AS tid, $group_id AS gid
              WITH kind, tid, gid WHERE kind = 'entity'
              MATCH (n:Entity {uuid: tid, group_id: gid})
              SET n.uuid = n.uuid
              RETURN n.uuid AS uuid, 'entity' AS kind, labels(n) AS labels
              UNION ALL
              WITH $target_kind AS kind, $target_uuid AS tid, $group_id AS gid
              WITH kind, tid, gid WHERE kind = 'edge'
              MATCH ()-[e:RELATES_TO {uuid: tid, group_id: gid}]->()
              SET e.uuid = e.uuid
              RETURN e.uuid AS uuid, 'edge' AS kind, [] AS labels
            }
            RETURN uuid, kind, labels
            """

    def build_evidence_link_write_cypher(self) -> str:
        """CREATE-once CatalogEvidenceLink; divergent content_sha256 -> error_code."""
        return """
            MERGE (n:CatalogEvidenceLink {uuid: $uuid, group_id: $group_id})
            ON CREATE SET
                n.uuid = $uuid,
                n.group_id = $group_id,
                n.batch_id = $batch_id,
                n.link_key = $link_key,
                n.content_sha256 = $content_sha256,
                n.source_uuid = $source_uuid,
                n.target_kind = $target_kind,
                n.target_uuid = $target_uuid,
                n.evidence_kind = $evidence_kind,
                n.locator_json = $locator_json,
                n.excerpt = $excerpt,
                n.extractor_name = $extractor_name,
                n.extractor_version = $extractor_version,
                n.rule_id = $rule_id,
                n.confidence = $confidence,
                n.created_at = $created_at,
                n.updated_at = $updated_at,
                n._catalog_create_token = $create_token
            WITH n, coalesce(n._catalog_create_token, '') = $create_token AS created
            SET n.uuid = n.uuid
            WITH n, created,
                 CASE
                   WHEN NOT created AND (
                     n.link_key IS NULL OR n.link_key <> $link_key
                   ) THEN 'provenance_link_conflict'
                   WHEN NOT created AND (
                     n.content_sha256 IS NULL OR n.content_sha256 <> $content_sha256
                   ) THEN 'provenance_link_conflict'
                   WHEN NOT created AND (
                     n.source_uuid IS NULL OR n.source_uuid <> $source_uuid
                     OR n.target_kind IS NULL OR n.target_kind <> $target_kind
                     OR n.target_uuid IS NULL OR n.target_uuid <> $target_uuid
                   ) THEN 'provenance_link_conflict'
                   ELSE null
                 END AS error_code
            WITH n, created, error_code,
                 CASE
                   WHEN error_code IS NOT NULL THEN 'error'
                   WHEN created THEN 'created'
                   ELSE 'unchanged'
                 END AS status
            REMOVE n._catalog_create_token
            RETURN n.uuid AS uuid,
                   n.content_sha256 AS content_sha256,
                   n.link_key AS link_key,
                   n.group_id AS group_id,
                   n.batch_id AS batch_id,
                   n.source_uuid AS source_uuid,
                   n.target_kind AS target_kind,
                   n.target_uuid AS target_uuid,
                   labels(n) AS labels,
                   status,
                   error_code
            """

    def prepare_evidence_link_params(self, **fields: Any) -> dict[str, Any]:
        """Allowlisted evidence params; reject embeddings/raw token keys."""
        for bad in _FORBIDDEN_EVIDENCE_MANIFEST_PARAM_KEYS:
            if bad in fields and fields[bad] is not None:
                raise CatalogStoreError(
                    f'forbidden evidence param key: {bad}',
                    code='validation_error',
                )
        required = (
            'uuid',
            'group_id',
            'batch_id',
            'link_key',
            'content_sha256',
            'source_uuid',
            'target_kind',
            'target_uuid',
            'evidence_kind',
            'created_at',
            'updated_at',
        )
        for key in required:
            val = fields.get(key)
            if val is None or (isinstance(val, str) and not str(val).strip()):
                raise CatalogStoreError(
                    f'evidence field {key} is required',
                    code='validation_error',
                )
        target_kind = str(fields['target_kind'])
        if target_kind not in {'entity', 'edge'}:
            raise CatalogStoreError(
                f'invalid target_kind {target_kind!r}',
                code='validation_error',
            )
        content_sha256 = str(fields['content_sha256'])
        if len(content_sha256) != 64 or any(c not in '0123456789abcdef' for c in content_sha256):
            raise CatalogStoreError(
                'content_sha256 must be 64 lowercase hex characters',
                code='validation_error',
            )
        excerpt = fields.get('excerpt')
        if excerpt is not None:
            if not isinstance(excerpt, str):
                raise CatalogStoreError(
                    'excerpt must be a string',
                    code='validation_error',
                )
            if len(excerpt) > MAX_EVIDENCE_LENGTH:
                raise CatalogStoreError(
                    f'excerpt exceeds max length ({MAX_EVIDENCE_LENGTH})',
                    code='validation_error',
                )
        confidence = fields.get('confidence')
        if confidence is not None:
            try:
                conf_f = float(confidence)
            except (TypeError, ValueError) as exc:
                raise CatalogStoreError(
                    'confidence must be a finite float',
                    code='validation_error',
                ) from exc
            if conf_f != conf_f or conf_f in (float('inf'), float('-inf')):
                raise CatalogStoreError(
                    'confidence must be finite',
                    code='validation_error',
                )
            if conf_f < 0.0 or conf_f > 1.0:
                raise CatalogStoreError(
                    'confidence out of range',
                    code='validation_error',
                )
            confidence = conf_f
        out: dict[str, Any] = {
            'uuid': str(fields['uuid']),
            'group_id': str(fields['group_id']),
            'batch_id': str(fields['batch_id']),
            'link_key': str(fields['link_key']),
            'content_sha256': content_sha256,
            'source_uuid': str(fields['source_uuid']),
            'target_kind': target_kind,
            'target_uuid': str(fields['target_uuid']),
            'evidence_kind': str(fields['evidence_kind']),
            'locator_json': fields.get('locator_json'),
            'excerpt': excerpt,
            'extractor_name': (
                str(fields['extractor_name']) if fields.get('extractor_name') is not None else None
            ),
            'extractor_version': (
                str(fields['extractor_version'])
                if fields.get('extractor_version') is not None
                else None
            ),
            'rule_id': fields.get('rule_id'),
            'confidence': confidence,
            'created_at': fields['created_at'],
            'updated_at': fields['updated_at'],
            'create_token': uuid4().hex,
        }
        for bad in _FORBIDDEN_EVIDENCE_MANIFEST_PARAM_KEYS:
            out.pop(bad, None)
        return out

    async def write_evidence_link(
        self,
        tx: Any,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve source+target then CREATE-once evidence control record in open tx."""
        group_id = str(params.get('group_id') or '')
        source_uuid = str(params.get('source_uuid') or '')
        target_uuid = str(params.get('target_uuid') or '')
        target_kind = str(params.get('target_kind') or '')
        if not group_id or not source_uuid or not target_uuid:
            raise CatalogStoreError(
                'group_id, source_uuid, and target_uuid are required',
                code='validation_error',
            )
        if target_kind not in {'entity', 'edge'}:
            raise CatalogStoreError(
                f'invalid target_kind {target_kind!r}',
                code='validation_error',
            )

        src_res = await tx.run(
            self.build_resolve_evidence_source_cypher(),
            source_uuid=source_uuid,
            group_id=group_id,
        )
        src_row = await self._first_from_tx_result(src_res)
        if not src_row or not src_row.get('uuid'):
            raise CatalogStoreError(
                'evidence source missing in group',
                code='provenance_target_missing',
            )

        tgt_res = await tx.run(
            self.build_resolve_evidence_target_cypher(),
            target_uuid=target_uuid,
            target_kind=target_kind,
            group_id=group_id,
        )
        tgt_row = await self._first_from_tx_result(tgt_res)
        if not tgt_row or not tgt_row.get('uuid'):
            raise CatalogStoreError(
                'evidence target missing in group',
                code='provenance_target_missing',
            )
        if str(tgt_row.get('kind') or '') != target_kind:
            raise CatalogStoreError(
                'evidence target type mismatch',
                code='endpoint_type_mismatch',
            )

        write_params = dict(params)
        if 'create_token' not in write_params or not write_params['create_token']:
            write_params['create_token'] = uuid4().hex
        result = await tx.run(self.build_evidence_link_write_cypher(), **write_params)
        row = await self._first_from_tx_result(result)
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'evidence link write returned no row',
                code='neo4j_transaction_failed',
            )
        error_code = row.get('error_code')
        if error_code:
            raise CatalogStoreError(
                'evidence link identity conflict',
                code=str(error_code),
            )
        labels = list(row.get('labels') or [])
        if 'Entity' in labels or 'Episodic' in labels:
            raise CatalogStoreError(
                'evidence control record must not carry Entity/Episodic labels',
                code='internal_error',
            )
        return row

    async def write_evidence_links(
        self,
        tx: Any,
        *,
        links: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Write zero or more evidence links; empty list is a no-op."""
        if not links:
            return []
        out: list[dict[str, Any]] = []
        for link in links:
            params = link if 'create_token' in link else self.prepare_evidence_link_params(**link)
            out.append(await self.write_evidence_link(tx, params=params))
        return out

    def build_existing_manifest_root_cypher(self) -> str:
        """MATCH existing manifest root by deterministic uuid+group_id."""
        return """
            MATCH (m:CatalogBatchManifest {uuid: $uuid, group_id: $group_id})
            RETURN m.uuid AS uuid,
                   m.group_id AS group_id,
                   m.batch_id AS batch_id,
                   m.manifest_sha256 AS manifest_sha256,
                   m.request_sha256 AS request_sha256,
                   m.catalog_sha256 AS catalog_sha256,
                   m.artifact_sha256 AS artifact_sha256,
                   m.identity_schema_version AS identity_schema_version,
                   m.chunk_count AS chunk_count,
                   m.payload_bytes AS payload_bytes
            """

    def build_create_manifest_root_cypher(self) -> str:
        """CREATE-once CatalogBatchManifest root (never Entity)."""
        return """
            CREATE (m:CatalogBatchManifest {
                uuid: $uuid,
                group_id: $group_id,
                batch_id: $batch_id,
                identity_schema_version: $identity_schema_version,
                canonicalization_version: $canonicalization_version,
                manifest_serialization_version: $manifest_serialization_version,
                catalog_schema_version: $catalog_schema_version,
                request_sha256: $request_sha256,
                catalog_sha256: $catalog_sha256,
                artifact_sha256: $artifact_sha256,
                manifest_sha256: $manifest_sha256,
                payload_bytes: $payload_bytes,
                chunk_count: $chunk_count,
                entity_count: $entity_count,
                edge_count: $edge_count,
                source_count: $source_count,
                evidence_link_count: $evidence_link_count,
                created_at: $created_at,
                updated_at: $updated_at
            })
            RETURN m.uuid AS uuid,
                   m.group_id AS group_id,
                   m.batch_id AS batch_id,
                   m.manifest_sha256 AS manifest_sha256,
                   m.chunk_count AS chunk_count,
                   m.payload_bytes AS payload_bytes
            """

    def build_create_manifest_chunk_cypher(self) -> str:
        """CREATE-once ordered CatalogBatchManifestChunk."""
        return """
            CREATE (c:CatalogBatchManifestChunk {
                uuid: $uuid,
                group_id: $group_id,
                manifest_uuid: $manifest_uuid,
                batch_id: $batch_id,
                chunk_index: $chunk_index,
                chunk_count: $chunk_count,
                byte_offset: $byte_offset,
                byte_length: $byte_length,
                chunk_sha256: $chunk_sha256,
                payload_b64: $payload_b64
            })
            RETURN c.uuid AS uuid,
                   c.manifest_uuid AS manifest_uuid,
                   c.chunk_index AS chunk_index,
                   c.byte_offset AS byte_offset,
                   c.byte_length AS byte_length,
                   c.chunk_sha256 AS chunk_sha256
            """

    def build_read_manifest_root_by_batch_cypher(self) -> str:
        """Internal recovery read of manifest root by group_id+batch_id."""
        return """
            MATCH (m:CatalogBatchManifest {group_id: $group_id, batch_id: $batch_id})
            RETURN m.uuid AS uuid,
                   m.group_id AS group_id,
                   m.batch_id AS batch_id,
                   m.manifest_sha256 AS manifest_sha256,
                   m.request_sha256 AS request_sha256,
                   m.catalog_sha256 AS catalog_sha256,
                   m.artifact_sha256 AS artifact_sha256,
                   m.identity_schema_version AS identity_schema_version,
                   m.chunk_count AS chunk_count,
                   m.payload_bytes AS payload_bytes,
                   m.created_at AS created_at,
                   m.updated_at AS updated_at
            """

    def build_lock_prepared_plan_for_commit_cypher(self) -> str:
        """Property-touch lock on prepared plan under group_id (D-08)."""
        return """
            MATCH (p:CatalogPreparedPlan {uuid: $uuid, group_id: $group_id})
            SET p.uuid = p.uuid
            RETURN p.uuid AS uuid,
                   p.group_id AS group_id,
                   p.state AS state,
                   p.token_digest AS token_digest,
                   p.batch_id AS batch_id,
                   p.request_sha256 AS request_sha256,
                   p.catalog_sha256 AS catalog_sha256,
                   p.artifact_sha256 AS artifact_sha256,
                   true AS locked
            """

    def build_terminal_commit_agrees_cypher(self) -> str:
        """Read plan + batch + manifest binding under group for D-09 agreement."""
        return """
            OPTIONAL MATCH (p:CatalogPreparedPlan {uuid: $plan_uuid, group_id: $group_id})
            OPTIONAL MATCH (b:CatalogIngestBatch {uuid: $batch_uuid, group_id: $group_id})
            OPTIONAL MATCH (m:CatalogBatchManifest {group_id: $group_id, batch_id: $batch_id})
            RETURN p.state AS plan_state,
                   b.status AS batch_status,
                   m.manifest_sha256 AS manifest_sha256,
                   m.request_sha256 AS request_sha256,
                   m.catalog_sha256 AS catalog_sha256,
                   m.artifact_sha256 AS artifact_sha256,
                   m.identity_schema_version AS identity_schema_version,
                   m.batch_id AS batch_id,
                   m.group_id AS group_id
            """

    def prepare_manifest_root_params(self, **fields: Any) -> dict[str, Any]:
        """Allowlisted manifest root params; reject embeddings/raw token."""
        for bad in _FORBIDDEN_EVIDENCE_MANIFEST_PARAM_KEYS:
            if bad in fields and fields[bad] is not None:
                raise CatalogStoreError(
                    f'forbidden manifest param key: {bad}',
                    code='validation_error',
                )
        required = (
            'uuid',
            'group_id',
            'batch_id',
            'request_sha256',
            'catalog_sha256',
            'manifest_sha256',
            'payload_bytes',
            'chunk_count',
            'created_at',
            'updated_at',
        )
        for key in required:
            val = fields.get(key)
            if val is None or (isinstance(val, str) and not str(val).strip()):
                raise CatalogStoreError(
                    f'manifest field {key} is required',
                    code='validation_error',
                )
        payload_bytes = int(fields['payload_bytes'])
        if payload_bytes < 0 or payload_bytes > HARD_MAX_PREPARED_PAYLOAD_BYTES:
            raise CatalogStoreError(
                'payload_bytes out of hard ceiling',
                code='batch_limit_exceeded',
            )
        chunk_count = int(fields['chunk_count'])
        if chunk_count < 1 or chunk_count > HARD_MAX_CHUNKS_PER_PLAN:
            raise CatalogStoreError(
                'chunk_count out of hard ceiling',
                code='batch_limit_exceeded',
            )
        for digest_key in (
            'request_sha256',
            'catalog_sha256',
            'manifest_sha256',
        ):
            digest = str(fields[digest_key])
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise CatalogStoreError(
                    f'{digest_key} must be 64 lowercase hex characters',
                    code='validation_error',
                )
        artifact = fields.get('artifact_sha256')
        if artifact is not None:
            artifact_s = str(artifact)
            if artifact_s and (
                len(artifact_s) != 64 or any(c not in '0123456789abcdef' for c in artifact_s)
            ):
                raise CatalogStoreError(
                    'artifact_sha256 must be 64 lowercase hex characters',
                    code='validation_error',
                )
        out: dict[str, Any] = {
            'uuid': str(fields['uuid']),
            'group_id': str(fields['group_id']),
            'batch_id': str(fields['batch_id']),
            'identity_schema_version': str(fields.get('identity_schema_version') or 'catalog-v2'),
            'canonicalization_version': str(
                fields.get('canonicalization_version') or CANONICALIZATION_VERSION
            ),
            'manifest_serialization_version': str(
                fields.get('manifest_serialization_version') or 'catalog-manifest-v1'
            ),
            'catalog_schema_version': str(
                fields.get('catalog_schema_version') or 'catalog-schema-v1'
            ),
            'request_sha256': str(fields['request_sha256']),
            'catalog_sha256': str(fields['catalog_sha256']),
            'artifact_sha256': (str(artifact) if artifact is not None and str(artifact) else None),
            'manifest_sha256': str(fields['manifest_sha256']),
            'payload_bytes': payload_bytes,
            'chunk_count': chunk_count,
            'entity_count': int(fields.get('entity_count') or 0),
            'edge_count': int(fields.get('edge_count') or 0),
            'source_count': int(fields.get('source_count') or 0),
            'evidence_link_count': int(fields.get('evidence_link_count') or 0),
            'created_at': fields['created_at'],
            'updated_at': fields['updated_at'],
        }
        for bad in _FORBIDDEN_EVIDENCE_MANIFEST_PARAM_KEYS:
            out.pop(bad, None)
        return out

    def prepare_manifest_chunk_params(self, **fields: Any) -> dict[str, Any]:
        """Allowlisted manifest chunk params."""
        for bad in _FORBIDDEN_EVIDENCE_MANIFEST_PARAM_KEYS:
            if bad in fields and fields[bad] is not None:
                raise CatalogStoreError(
                    f'forbidden manifest chunk param key: {bad}',
                    code='validation_error',
                )
        required = (
            'uuid',
            'group_id',
            'manifest_uuid',
            'batch_id',
            'chunk_index',
            'chunk_count',
            'byte_offset',
            'byte_length',
            'chunk_sha256',
            'payload_b64',
        )
        for key in required:
            val = fields.get(key)
            if key == 'payload_b64':
                if val is None:
                    raise CatalogStoreError(
                        f'manifest chunk field {key} is required',
                        code='validation_error',
                    )
                continue
            if val is None or (isinstance(val, str) and not str(val).strip()):
                raise CatalogStoreError(
                    f'manifest chunk field {key} is required',
                    code='validation_error',
                )
        chunk_index = int(fields['chunk_index'])
        chunk_count = int(fields['chunk_count'])
        if chunk_index < 0 or chunk_index >= chunk_count:
            raise CatalogStoreError(
                'chunk_index out of range',
                code='validation_error',
            )
        if chunk_count < 1 or chunk_count > HARD_MAX_CHUNKS_PER_PLAN:
            raise CatalogStoreError(
                'chunk_count out of hard ceiling',
                code='batch_limit_exceeded',
            )
        chunk_sha = str(fields['chunk_sha256'])
        if len(chunk_sha) != 64 or any(c not in '0123456789abcdef' for c in chunk_sha):
            raise CatalogStoreError(
                'chunk_sha256 must be 64 lowercase hex characters',
                code='validation_error',
            )
        out: dict[str, Any] = {
            'uuid': str(fields['uuid']),
            'group_id': str(fields['group_id']),
            'manifest_uuid': str(fields['manifest_uuid']),
            'batch_id': str(fields['batch_id']),
            'chunk_index': chunk_index,
            'chunk_count': chunk_count,
            'byte_offset': int(fields['byte_offset']),
            'byte_length': int(fields['byte_length']),
            'chunk_sha256': chunk_sha,
            'payload_b64': str(fields.get('payload_b64') or ''),
        }
        for bad in _FORBIDDEN_EVIDENCE_MANIFEST_PARAM_KEYS:
            out.pop(bad, None)
        return out

    async def write_manifest_root_and_chunks(
        self,
        tx: Any,
        *,
        root: dict[str, Any],
        chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """CREATE-once manifest root + ordered chunks; divergent hash conflicts."""
        root_params = (
            root
            if 'manifest_sha256' in root and 'identity_schema_version' in root
            else self.prepare_manifest_root_params(**root)
        )
        if not chunks:
            raise CatalogStoreError('at least one manifest chunk required', code='validation_error')
        if len(chunks) != int(root_params['chunk_count']):
            raise CatalogStoreError(
                'chunk_count does not match chunks length',
                code='validation_error',
            )
        group_id = root_params['group_id']

        existing_res = await tx.run(
            self.build_existing_manifest_root_cypher(),
            uuid=root_params['uuid'],
            group_id=group_id,
        )
        existing = await self._first_from_tx_result(existing_res)
        if existing and existing.get('uuid'):
            same = (
                str(existing.get('manifest_sha256') or '') == str(root_params['manifest_sha256'])
                and str(existing.get('request_sha256') or '') == str(root_params['request_sha256'])
                and str(existing.get('catalog_sha256') or '') == str(root_params['catalog_sha256'])
                and str(existing.get('batch_id') or '') == str(root_params['batch_id'])
            )
            existing_artifact = existing.get('artifact_sha256')
            root_artifact = root_params.get('artifact_sha256')
            if (existing_artifact or None) != (root_artifact or None):
                same = False
            if not same:
                raise CatalogStoreError(
                    'manifest identity already exists with divergent binding',
                    code='batch_conflict',
                )
            return {
                'uuid': existing.get('uuid'),
                'group_id': existing.get('group_id'),
                'batch_id': existing.get('batch_id'),
                'manifest_sha256': existing.get('manifest_sha256'),
                'chunk_count': existing.get('chunk_count'),
                'payload_bytes': existing.get('payload_bytes'),
                'idempotent': True,
            }

        try:
            create_res = await tx.run(self.build_create_manifest_root_cypher(), **root_params)
            created = await self._first_from_tx_result(create_res)
        except CatalogStoreError:
            raise
        except Exception as exc:
            if self._is_uniqueness_constraint_race(exc):
                raise CatalogStoreError(
                    'manifest identity already exists',
                    code='batch_conflict',
                ) from exc
            raise CatalogStoreError(
                f'manifest create failed: {type(exc).__name__}',
                code='neo4j_transaction_failed',
            ) from exc
        if not created or not created.get('uuid'):
            raise CatalogStoreError(
                'manifest create returned no row',
                code='neo4j_transaction_failed',
            )

        ordered = sorted(
            (
                ch
                if 'chunk_sha256' in ch and 'manifest_uuid' in ch
                else self.prepare_manifest_chunk_params(**ch)
                for ch in chunks
            ),
            key=lambda c: int(c['chunk_index']),
        )
        for ch_params in ordered:
            if ch_params['manifest_uuid'] != root_params['uuid']:
                raise CatalogStoreError(
                    'chunk manifest_uuid mismatch',
                    code='validation_error',
                )
            if ch_params['group_id'] != group_id:
                raise CatalogStoreError(
                    'chunk group_id mismatch',
                    code='validation_error',
                )
            if ch_params['batch_id'] != root_params['batch_id']:
                raise CatalogStoreError(
                    'chunk batch_id mismatch',
                    code='validation_error',
                )
            try:
                ch_res = await tx.run(
                    self.build_create_manifest_chunk_cypher(),
                    **ch_params,
                )
                ch_row = await self._first_from_tx_result(ch_res)
            except CatalogStoreError:
                raise
            except Exception as exc:
                if self._is_uniqueness_constraint_race(exc):
                    raise CatalogStoreError(
                        'manifest chunk identity already exists',
                        code='batch_conflict',
                    ) from exc
                raise CatalogStoreError(
                    f'manifest chunk create failed: {type(exc).__name__}',
                    code='neo4j_transaction_failed',
                ) from exc
            if not ch_row or not ch_row.get('uuid'):
                raise CatalogStoreError(
                    'manifest chunk create returned no row',
                    code='neo4j_transaction_failed',
                )
        return created

    async def lock_prepared_plan_for_commit(
        self,
        tx: Any,
        *,
        plan_uuid: str,
        group_id: str,
    ) -> dict[str, Any]:
        """Property-touch lock prepared plan under group_id for recovery serialization."""
        if not plan_uuid or not group_id:
            raise CatalogStoreError(
                'plan_uuid and group_id are required',
                code='validation_error',
            )
        result = await tx.run(
            self.build_lock_prepared_plan_for_commit_cypher(),
            uuid=plan_uuid,
            group_id=group_id,
        )
        row = await self._first_from_tx_result(result)
        if not row or not row.get('uuid'):
            raise CatalogStoreError(
                'prepared plan not found for lock',
                code='prepared_plan_not_found',
            )
        return row

    async def read_terminal_commit_snapshot(
        self,
        tx: Any,
        *,
        group_id: str,
        batch_id: str,
        plan_uuid: str,
        batch_uuid: str,
    ) -> dict[str, Any] | None:
        """Group-scoped plan+batch+manifest snapshot for recovery classification (D-09)."""
        if not group_id or not batch_id or not plan_uuid or not batch_uuid:
            return None
        result = await tx.run(
            self.build_terminal_commit_agrees_cypher(),
            group_id=group_id,
            batch_id=batch_id,
            plan_uuid=plan_uuid,
            batch_uuid=batch_uuid,
        )
        row = await self._first_from_tx_result(result)
        return dict(row) if row else None

    async def terminal_commit_agrees(
        self,
        tx: Any,
        *,
        projection: dict[str, Any],
    ) -> bool:
        """True only when plan COMMITTED + batch committed + manifest hashes agree."""
        group_id = str(projection.get('group_id') or '')
        batch_id = str(projection.get('batch_id') or '')
        plan_uuid = str(projection.get('plan_uuid') or '')
        batch_uuid = str(projection.get('batch_uuid') or '')
        if not group_id or not batch_id or not plan_uuid or not batch_uuid:
            return False
        row = await self.read_terminal_commit_snapshot(
            tx,
            group_id=group_id,
            batch_id=batch_id,
            plan_uuid=plan_uuid,
            batch_uuid=batch_uuid,
        )
        if not row:
            return False
        if str(row.get('plan_state') or '') != PLAN_STATE_COMMITTED:
            return False
        if str(row.get('batch_status') or '') != 'committed':
            return False
        if str(row.get('group_id') or '') != group_id:
            return False
        if str(row.get('batch_id') or '') != batch_id:
            return False
        for key in (
            'manifest_sha256',
            'request_sha256',
            'catalog_sha256',
            'identity_schema_version',
        ):
            if str(row.get(key) or '') != str(projection.get(key) or ''):
                return False
        proj_artifact = projection.get('artifact_sha256')
        row_artifact = row.get('artifact_sha256')
        return str(proj_artifact or '') == str(row_artifact or '')

    async def read_manifest_root_for_recovery(
        self,
        executor: Any,
        *,
        group_id: str,
        batch_id: str,
        tx: Any | None = None,
    ) -> dict[str, Any] | None:
        """Internal recovery read of durable manifest root (no public MCP tool)."""
        if not group_id or not batch_id:
            raise CatalogStoreError(
                'group_id and batch_id are required',
                code='validation_error',
            )
        return await self._read_one(
            executor,
            self.build_read_manifest_root_by_batch_cypher(),
            {'group_id': str(group_id), 'batch_id': str(batch_id)},
            tx=tx,
        )
