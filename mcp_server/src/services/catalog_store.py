"""Neo4j persistence for deterministic catalog entities (no LLM / queue).

Server-owned Cypher only: allowlisted labels, parameterized values, preserve-on-update
MERGE (never SET n = $map). Caller UUIDs are never identity authority.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from models.catalog_common import CATALOG_ENTITY_TYPES, ENTITY_TYPE_PREFIXES, PROTECTED_ENTITY_PROPERTIES

# Mirror graphiti_core.helpers.SAFE_CYPHER_IDENTIFIER_PATTERN without importing core.
_SAFE_LABEL = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# Fixed map: entity_type -> Neo4j label literal (identity with allowlist keys).
_ENTITY_LABELS: dict[str, str] = {
    t: t for t in ENTITY_TYPE_PREFIXES if _SAFE_LABEL.match(t)
}


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
        """Build MERGE Cypher with ON CREATE / conditional ON MATCH for one entity type.

        Labels are server-resolved literals only. Values are parameters.
        Identical content_sha256 leaves properties (including batch_id) untouched.
        """
        label = self.resolve_entity_label(entity_type)
        # Conditional SET: only apply mutable fields when content hash differs.
        # CASE WHEN n.content_sha256 = $content_sha256 THEN n.<prop> ELSE $prop END
        mutable = (
            'name',
            'graph_key',
            'name_raw',
            'name_canonical',
            'database_qualified_name',
            'summary',
            'attributes',
            'source_refs',
            'confidence',
            'batch_id',
            'content_sha256',
            'labels',
            'group_id',
        )
        on_match_lines = [
            (
                f'n.{prop} = CASE WHEN n.content_sha256 = $content_sha256 '
                f'THEN n.{prop} ELSE ${prop} END'
            )
            for prop in mutable
        ]
        on_match_lines.append(
            'n.updated_at = CASE WHEN n.content_sha256 = $content_sha256 '
            'THEN n.updated_at ELSE $updated_at END'
        )
        on_match = ',\n                '.join(on_match_lines)

        return f"""
            MERGE (n:Entity {{uuid: $uuid}})
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
                n.updated_at = $updated_at
            ON MATCH SET
                {on_match}
            WITH n
            CALL db.create.setNodeVectorProperty(n, 'name_embedding', $name_embedding)
            RETURN n.uuid AS uuid,
                   n.content_sha256 AS content_sha256,
                   n.batch_id AS batch_id,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at,
                   CASE WHEN n.created_at = $created_at THEN 'created'
                        WHEN n.content_sha256 = $content_sha256
                             AND n.updated_at = $updated_at THEN 'unchanged'
                        ELSE 'updated'
                   END AS status
            """

    def build_get_entity_by_uuid_cypher(self) -> str:
        return """
            MATCH (n:Entity {uuid: $uuid})
            WHERE n.group_id = $group_id
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
        }

    async def upsert_entity_item(
        self,
        tx: Any,
        *,
        entity_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute entity MERGE inside an open transaction. Returns first record dict."""
        cypher = self.build_entity_upsert_cypher(entity_type)
        result = await tx.run(cypher, **params)
        # neo4j AsyncResult or mock
        if hasattr(result, 'data'):
            rows = await result.data()
            return rows[0] if rows else {}
        if hasattr(result, 'single'):
            record = await result.single()
            return dict(record) if record is not None else {}
        return {}

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
        # Neo4jDriver.execute_query -> EagerResult, a tuple of (records, summary, keys).
        result = await executor.execute_query(cypher, **params)
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
        result = await executor.execute_query(cypher, **params)
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

    def build_match_entities_for_verify_by_keys_cypher(self) -> str:
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

        if batch_id:
            cypher = self.build_match_entities_for_verify_by_batch_cypher()
            batch_rows = await self._read_many(
                executor,
                cypher,
                {'group_id': group_id, 'batch_id': batch_id},
                tx=tx,
            )
            for row in batch_rows:
                key = str(row.get('uuid') or '')
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
                key = str(row.get('uuid') or '')
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
        return rows

    def build_match_edges_for_verify_by_batch_cypher(self) -> str:
        return """
            MATCH (s:Entity)-[e:RELATES_TO]->(t:Entity)
            WHERE e.group_id = $group_id
              AND e.batch_id = $batch_id
            RETURN e.uuid AS uuid,
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
            RETURN e.uuid AS uuid,
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
                key = str(row.get('uuid') or row.get('edge_key') or '')
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
                key = str(row.get('uuid') or row.get('edge_key') or '')
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
        return rows

    def build_match_provenance_presence_cypher(self) -> str:
        """Report whether requested entity/edge UUIDs have any MENTIONS provenance."""
        return """
            UNWIND $target_uuids AS target_uuid
            OPTIONAL MATCH (ep:Episodic)-[:MENTIONS]->(n {uuid: target_uuid})
            WHERE n.group_id = $group_id OR n IS NULL
            WITH target_uuid, count(ep) AS mention_count
            RETURN target_uuid AS uuid, mention_count > 0 AS has_provenance
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
