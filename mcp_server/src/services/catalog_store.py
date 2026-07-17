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

from models.catalog_common import (
    CATALOG_EDGE_TYPES,
    CATALOG_ENTITY_TYPES,
    ENTITY_TYPE_PREFIXES,
    PROTECTED_ENTITY_PROPERTIES,
)

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


class CatalogStoreError(ValueError):
    """Raised when catalog store cannot safely build or execute a query."""

    def __init__(self, message: str, *, code: str | None = None):
        self.code = code
        super().__init__(message)


def serialize_nested_json(value: Any) -> str | None:
    """Serialize nested structures to a JSON string for Neo4j primitive storage."""
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


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
        # Exact composite identity properties (order-insensitive).
        return set(props) == {'uuid', 'group_id'}

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
        """Build MERGE Cypher with create-once identity and zero-mutation unchanged path.

        Labels are server-resolved literals only. Values are parameters.
        Create path sets full props + per-write $create_token marker.
        Status derived from token presence + pre-update hash compare — never timestamps.
        Matched unchanged: no SET of content props, no vector rewrite.
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
            WITH n,
                 coalesce(n._catalog_create_token, '') = $create_token AS created,
                 n.content_sha256 = $content_sha256 AS same
            WITH n, created, same,
                 CASE
                   WHEN created THEN 'created'
                   WHEN same THEN 'unchanged'
                   ELSE 'updated'
                 END AS status
            FOREACH (_ IN CASE WHEN status = 'updated' THEN [1] ELSE [] END |
              SET {updated_set}
            )
            REMOVE n._catalog_create_token
            WITH n, status
            CALL {{
              WITH n, status
              WITH n, status WHERE status IN ['created', 'updated']
              CALL db.create.setNodeVectorProperty(n, 'name_embedding', $name_embedding)
              RETURN 1 AS _
              UNION
              WITH n, status
              WITH n, status WHERE status = 'unchanged'
              RETURN 0 AS _
            }}
            RETURN n.uuid AS uuid,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at,
                   status
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
        """MERGE Episodic source without Entity label; preserve created_at on update.

        Never uses stock SET n = $map wipe. Identity + source_key only ON CREATE.
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
            WITH n,
                 coalesce(n._catalog_create_token, '') = $create_token AS created,
                 n.content_sha256 = $content_sha256 AS same
            WITH n, created, same,
                 CASE
                   WHEN created THEN 'created'
                   WHEN same THEN 'unchanged'
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
                   status
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
