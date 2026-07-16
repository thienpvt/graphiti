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
            if hasattr(result, 'data'):
                rows = await result.data()
                return rows[0] if rows else None
            if hasattr(result, 'single'):
                record = await result.single()
                return dict(record) if record is not None else None
            return None
        # driver.execute_query style
        result = await executor.execute_query(cypher, **params)
        if result is None:
            return None
        # EagerResult: (records, summary, keys) or object with records
        if isinstance(result, tuple) and result:
            records = result[0]
            if not records:
                return None
            first = records[0]
            return dict(first) if not isinstance(first, dict) else first
        if hasattr(result, 'records'):
            records = result.records
            if not records:
                return None
            first = records[0]
            return dict(first) if not isinstance(first, dict) else first
        return None
