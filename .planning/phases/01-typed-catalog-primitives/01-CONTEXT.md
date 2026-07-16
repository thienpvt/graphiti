# Phase 1: Typed Catalog Primitives - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver configurable, synchronous Neo4j-only MCP primitives for deterministic typed entity and edge upsert, typed entity resolution, and read-only batch verification. Every write uses server-derived UUIDv5 identity, configured embeddings, strict group isolation, fixed server-owned schemas, and commits or rolls back before returning. Existing MCP tools and behaviors remain unchanged.

</domain>

<decisions>
## Implementation Decisions

### Mandatory Write Rules
- Entity upsert returns success only after Neo4j commits; no successful response may precede commit.
- Catalog tools never use the ingestion queue and never call an LLM.
- Catalog requests do not accept `excluded_entity_types`.
- Entity and edge identities are server-derived UUIDv5 values under the configured immutable namespace; caller UUIDs have no identity authority.
- Every catalog entity requires exactly one allowlisted custom type label in addition to the `Entity` base label.
- Edge upsert never creates generic or implicit endpoints; both typed endpoints must already resolve in the request scope.
- Existing node types are immutable. A deterministic identity or graph key with conflicting labels fails without mutation.
- Entity upsert generates `name_embedding` before opening the write transaction, including dry-run readiness validation.
- An identical canonical entity payload returns `unchanged` and performs no timestamp or property mutation.
- Edge upsert requires two existing endpoints and resolves each by exact `group_id`, `graph_key`, and expected `entity_type`.
- A missing endpoint returns `missing_endpoint`; an endpoint with the wrong custom label returns `endpoint_type_mismatch`.
- Edge upsert never creates or relabels endpoints.
- Edge UUIDs are server-derived UUIDv5 identities, and `fact_embedding` is generated before opening the write transaction.
- An identical canonical edge payload returns `unchanged` and performs no timestamp or property mutation.

### Result Contract
- Item success states are `created`, `updated`, and `unchanged`.
- Results preserve input order and include deterministic UUID and canonical SHA-256.
- Expected validation and conflict failures use structured item errors without exposing raw exception text.
- Atomic request failure marks otherwise valid items as `rolled_back` and reports the triggering structured error.

### Write Semantics
- `atomic=true` uses one request transaction. `atomic=false` uses independent item transactions; every successful item returns only after its own transaction commits.
- Dry-run performs full validation, identity/conflict resolution, and embedding generation without graph writes or persistent batch state.
- Same-request items with identical deterministic identity and canonical payload are coalesced; differing payloads fail as conflicts.
- A request uses one timestamp. Existing `created_at` is preserved; `updated_at` advances only for changed payloads.

### Verification Scope
- Domain objects persist `batch_id`; batch verification queries only the requested `group_id` and batch.
- Duplicate/anomaly reporting is limited to requested identities rather than scanning unrelated group data.
- A generic duplicate is an `Entity` in the same group whose `name` equals `graph_key` but lacks the expected custom label.
- Phase 1 accepts `require_provenance`; it reports missing provenance read-only while Phase 2 supplies provenance writes.

### Feature Gates and Failures
- Catalog tool schemas remain registered while writes are disabled; write calls return `feature_disabled`.
- An absent or invalid UUID namespace is tolerated only while catalog writes are disabled. Enabling writes requires a valid explicit namespace.
- Non-Neo4j configurations keep stable tool schemas but return structured backend-unavailable errors for catalog operations.
- Unexpected failures log only safe batch/count context and return `internal_error`; Neo4j transaction failures return `neo4j_transaction_failed`.

### Claude's Discretion
- Exact Pydantic model decomposition, module boundaries, internal helper names, and Cypher layout may follow the smallest secure design consistent with existing MCP conventions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mcp_server/src/config/schema.py` already provides YAML/environment expansion and Pydantic settings precedence.
- The configured embedder is already constructed by `mcp_server/src/services/factories.py` and exposed through the Graphiti client.
- Neo4j driver transactions and parameterized query execution already exist in `graphiti_core/driver/neo4j_driver.py` and its operation classes.
- Existing `validate_group_id`, search filters, entity/edge models, and MCP search tools provide trust-boundary and interoperability patterns.

### Established Patterns
- Public MCP contracts use Pydantic models and async tool functions; database I/O is async even when caller semantics are synchronous.
- Neo4j entity persistence uses `Entity` plus validated custom labels; edge persistence uses `RELATES_TO` with searchable fields.
- Security validation is duplicated at model and query-construction boundaries where identifier interpolation is unavoidable.
- Unit tests use pytest, `AsyncMock`, and real Pydantic models; integration tests use a live driver and explicit integration markers.

### Integration Points
- Register four additive tools in `mcp_server/src/graphiti_mcp_server.py` without altering existing tool implementations.
- Add catalog configuration beneath the MCP config schema and consume the existing configured Neo4j driver and embedder.
- Keep Neo4j-specific deterministic persistence behind an MCP catalog service boundary; do not claim cross-provider support.
- Verify interoperability through existing `search_nodes` and `search_memory_facts` paths under `oracle-catalog-tool-test` only.

</code_context>

<specifics>
## Specific Ideas

The mandatory rules are hard constraints, not defaults: synchronous post-commit responses, no queue, no LLM, no `excluded_entity_types`, UUIDv5 identity, required custom labels, immutable node types, generated `name_embedding` and `fact_embedding`, exact endpoint resolution by group/key/type, `missing_endpoint` and `endpoint_type_mismatch` errors, no endpoint creation, and no mutation for identical entity or edge payloads.

</specifics>

<deferred>
## Deferred Ideas

Provenance writes, persisted `CatalogIngestBatch` status, and complete atomic catalog-batch orchestration remain Phase 2 work. Phase 2 cannot begin until the complete Phase 1 quality gate and report pass.

</deferred>
