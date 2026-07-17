# Phase 2: Provenance and Atomic Batch - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning
**Mode:** Autonomous recommendations pre-authorized by user

<domain>
## Phase Boundary

Deliver three additive Neo4j-only MCP tools: deterministic installed-schema provenance upsert, restart-safe non-Entity catalog ingest status lookup, and complete atomic catalog batch upsert. The batch path validates the full request, resolves same-request and persisted endpoints, embeds before the domain transaction, commits entities, edges, provenance, and committed status together, and persists bounded failed status separately after rollback. Finish with operator documentation and verification. Do not deploy, ingest a live catalog, mutate `oracle-catalog-v2`, clear graph data, alter semantic ingestion, or create communities during upsert.

</domain>

<decisions>
## Implementation Decisions

### Provenance Representation
- Represent each deterministic source as an installed-schema `Episodic` node, not an `Entity`; derive its UUIDv5 from `group_id|Source|source_key` and its canonical SHA-256 from allowlisted mutable source metadata.
- Link a source episode to each existing entity target with deterministic `MENTIONS` relationships using server-derived link identities.
- Attach source identity to existing `RELATES_TO` facts through Graphiti's existing `episodes` list, because Neo4j cannot connect a relationship directly to another relationship without inventing a new schema object.
- Preserve exact `reference_time`; store only bounded, allowlisted source metadata. Never call `add_episode`, an LLM, or the ingestion queue.
- Validate every entity and edge target before writes. Any missing or mistyped target returns `provenance_target_missing`; atomic provenance requests write nothing.
- Identical source and links return `unchanged`; changed mutable source metadata updates the existing deterministic episode while preserving `created_at`.

### Persistent Batch Status
- Persist status as a dedicated `CatalogIngestBatch` node without the `Entity` label, so existing entity search and community clustering exclude it by construction.
- Derive batch UUIDv5 from `group_id|Batch|batch_id`; scope every lookup and write by both deterministic UUID and `group_id`.
- Persist only request/catalog hashes, lifecycle status, bounded counts, timestamps, and bounded sanitized error summaries. Never persist full requests, raw documents, complete source text, or credentials.
- Support `planned`, `validating`, `embedding`, `writing`, `committed`, and `failed`; terminal status survives service restart because Neo4j is authoritative.
- Dry-run creates no persistent status. Successful batch commit writes `committed` inside the domain transaction. A write failure rolls back domain changes, then best-effort persists `failed` in a separate transaction.
- A committed batch ID with the same request hash returns unchanged. Reuse with a different hash returns `batch_conflict` without mutation.

### Atomic Batch Orchestration
- Require `atomic=true` for `upsert_catalog_batch`; reject non-atomic mode rather than imply weaker whole-batch guarantees.
- Validate the complete nested request and configured entity, edge, and provenance limits before any persistent side effect.
- Reuse Phase 1 canonicalization, identity, allowlist, conflict, endpoint, parameter, and response helpers; avoid routing through standalone tools because those own separate transactions.
- Coalesce identical same-request identities; reject divergent duplicate identities before embedding or writing.
- Resolve edge endpoints against the union of validated same-request entities and existing correctly typed Neo4j entities. Never create an implicit or generic endpoint.
- Detect all known entity, edge, batch, source, target, and hash conflicts before embedding. Recheck invariants inside the transaction for races.
- Generate every needed entity and edge embedding before opening the domain transaction. Embedding failure produces no graph or status write.
- Use one Neo4j transaction for changed entities, changed edges, provenance, and committed batch state. Retry with identical content creates one logical set of objects.

### Operator Guidance and Verification
- Document all seven catalog tools as an administrative structured-ingestion surface and distinguish them from semantic `add_memory` ingestion.
- Document immutable namespace consequences, allowlists, limits, idempotency, atomicity, structured errors, Graphiti/Neo4j provenance limitations, and community-neutral upsert behavior.
- Include sanitized ACCEPT_TAB and Kubernetes ConfigMap/environment examples plus rollout and rollback guidance. Do not deploy or expose credentials.
- Integration tests use only `oracle-catalog-tool-test`, cover service reinitialization, retries, conflicts, rollback, search interoperability, and explicit safe `build_communities` execution.
- Final report records all seven MCP schemas and exact format, lint, type-check, unit, integration, image-build, and unchanged-live-group results. Recommend a fresh canary only.

### Claude's Discretion
- Exact Pydantic decomposition, internal helper boundaries, Cypher layout, result field naming, bounded error-summary shape, and plan slicing may follow the smallest secure design consistent with Phase 1 patterns.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mcp_server/src/services/catalog_service.py` already owns Phase 1 canonicalization, UUID/hash preparation, conflict checks, embedding-before-transaction ordering, atomic writes, structured results, and safe logging.
- `mcp_server/src/services/catalog_store.py` already centralizes parameterized Neo4j reads/writes and transaction-safe entity/edge primitives.
- `mcp_server/src/models/catalog_common.py`, `catalog_entities.py`, `catalog_edges.py`, and `catalog_responses.py` provide allowlists, trust-boundary validation, limits, errors, and response conventions.
- `mcp_server/src/services/catalog_identity.py` provides deterministic identity and canonical SHA-256 helpers; extend it for source and batch identities.
- Installed Graphiti uses `(:Episodic)-[:MENTIONS]->(:Entity)` and stores episode UUIDs in `RELATES_TO.episodes`; these are the compatible provenance primitives.
- `Neo4jDriver.transaction()` provides real commit/rollback semantics. Existing search and community queries anchor on `Entity`, naturally excluding `CatalogIngestBatch`.

### Established Patterns
- MCP tools are async and Pydantic-backed while remaining synchronous from the caller's commit/rollback perspective.
- Catalog Cypher is server-owned and parameterized; only fixed allowlisted labels may be selected by server code.
- Expected validation/conflict failures return structured codes; unexpected errors expose sanitized type context only.
- Unit tests use real Pydantic models plus AsyncMock stores/clients; Neo4j integration tests isolate `oracle-catalog-tool-test`.

### Integration Points
- Add provenance, batch, and status models beside current catalog models.
- Extend `CatalogNeo4jStore` with installed-schema provenance, batch-status, bulk preflight, and shared-transaction operations.
- Extend `CatalogService` with `upsert_provenance`, `upsert_catalog_batch`, and `get_catalog_ingest_status` while keeping Phase 1 APIs unchanged.
- Register three additive tools in `mcp_server/src/graphiti_mcp_server.py`; catalog tool count becomes seven.
- Update MCP docs and sanitized sample/config manifests only where Phase 2 requirements require them; preserve unrelated working-tree edits.

</code_context>

<specifics>
## Specific Ideas

Recommended choices were pre-authorized: source-as-Episodic, entity provenance via deterministic MENTIONS, fact provenance via `RELATES_TO.episodes`, non-Entity batch nodes, strict atomic batch mode, preflight before embeddings, one domain transaction, separate safe failed-status persistence, no dry-run status, and no normal-upsert community calls.

</specifics>

<deferred>
## Deferred Ideas

FalkorDB or other backend support, production deployment, live `oracle-catalog-v2` writes, full 14,106-entity ingestion, automatic community creation, graph repair/migration tooling, and production canary execution remain out of scope.

</deferred>
