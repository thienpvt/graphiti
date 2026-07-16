# Requirements: Deterministic Catalog Ingestion for Graphiti MCP

**Defined:** 2026-07-16
**Core Value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.

## v1 Requirements

Requirements for this milestone. Each maps to exactly one roadmap phase.

### Configuration and Safety

- [ ] **CONF-01**: Operator can enable or disable deterministic catalog writes through `catalog_upsert.enabled`, defaulting to disabled
- [ ] **CONF-02**: Server validates `GRAPHITI_CATALOG_UUID_NAMESPACE` as a fixed UUID and refuses startup or disables catalog writes when enabled without a valid namespace
- [ ] **CONF-03**: Server never generates a catalog UUID namespace automatically and documents the namespace as immutable deployment configuration
- [ ] **CONF-04**: Operator can configure entity, edge, and provenance-link limits with defaults of 500, 2,000, and 5,000 respectively
- [ ] **CONF-05**: Catalog write tools operate only with the Neo4j provider and make no portability claim for other graph backends
- [ ] **SAFE-01**: Every catalog request requires a non-empty, validated `group_id`, and every catalog read and write is constrained to it
- [ ] **SAFE-02**: Catalog tools accept only fixed server-owned entity labels, edge types, and property schemas; no client value is interpolated into Cypher identifiers
- [ ] **SAFE-03**: Catalog requests enforce string lengths, collection sizes, protected properties, raw-text limits, finite numbers, and confidence values between 0 and 1
- [ ] **SAFE-04**: Catalog tools return item-level structured errors using documented error codes rather than exception text alone
- [ ] **SAFE-05**: Catalog operations log batch IDs and counts without logging credentials, complete payloads, raw documents, or complete source text

### Deterministic Identity and Audit

- [ ] **IDEN-01**: Server derives entity UUIDs with UUIDv5 over `group_id|entity_type|graph_key` using the configured namespace
- [ ] **IDEN-02**: Server derives edge UUIDs with UUIDv5 over `group_id|edge_type|edge_key` using the configured namespace
- [ ] **IDEN-03**: Server derives source UUIDs with UUIDv5 over `group_id|Source|source_key` using the configured namespace
- [ ] **IDEN-04**: Server derives batch UUIDs with UUIDv5 over `group_id|Batch|batch_id` using the configured namespace
- [ ] **IDEN-05**: Caller-supplied database UUIDs are never accepted as identity authority
- [ ] **IDEN-06**: Server canonicalizes mutable payloads and persists a SHA-256 containing exactly 64 lowercase hexadecimal characters
- [ ] **IDEN-07**: Server compares an optional client `content_sha256` or `request_sha256` with its canonical hash and returns `content_hash_mismatch` on mismatch
- [ ] **IDEN-08**: Identical content returns unchanged; changed mutable content updates; identity-property conflicts fail without mutation

### Typed Entity Upsert

- [ ] **ENTY-01**: MCP client can call `upsert_typed_entities` with `group_id`, `batch_id`, `dry_run`, `atomic`, and a bounded entity list
- [ ] **ENTY-02**: Server accepts only the 15 documented catalog entity types and rejects unknown types
- [ ] **ENTY-03**: Server validates each entity type against its documented graph-key prefix and returns `graph_key_prefix_mismatch` for mismatches
- [ ] **ENTY-04**: Server uses `graph_key` as the Graphiti node name while storing `database_qualified_name`, exact `name_raw`, and exact `name_canonical` separately
- [ ] **ENTY-05**: Entity attributes cannot overwrite `uuid`, `group_id`, `labels`, `graph_key`, `name_embedding`, `created_at`, `updated_at`, or `content_sha256`
- [ ] **ENTY-06**: Nested `source_refs` are serialized safely rather than written as unsupported nested Neo4j properties
- [ ] **ENTY-07**: Server embeds `graph_key`, `database_qualified_name`, and summary using the configured embedder before opening the Neo4j write transaction
- [ ] **ENTY-08**: Entity create/update preserves the `Entity` base label and exactly the expected custom type label in both Neo4j labels and Graphiti's `labels` property
- [ ] **ENTY-09**: Entity update preserves original `created_at`, adds or advances `updated_at`, and preserves unrelated catalog properties
- [ ] **ENTY-10**: Atomic entity upsert commits all valid items or rolls back the full request on conflict or transaction failure
- [ ] **ENTY-11**: Entity dry-run performs validation, deterministic identity resolution, and conflict checks without graph writes or persistent batch state
- [ ] **ENTY-12**: Concurrent identical entity upserts result in one logical typed node per deterministic identity
- [ ] **ENTY-13**: Existing `search_nodes` can retrieve catalog entities through expected entity-type filters

### Typed Entity Resolution

- [ ] **RESO-01**: MCP client can call read-only `resolve_typed_entities` with graph keys and expected entity types
- [ ] **RESO-02**: Resolution reports found state, UUID, labels, verified type, content hash, embedding presence, generic duplicates, and typed duplicates per item
- [ ] **RESO-03**: Resolution detects missing nodes, bare generic entities, duplicate typed nodes, wrong custom labels, deterministic UUID mismatch, and absent embeddings
- [ ] **RESO-04**: Resolution never writes graph data or generates embeddings

### Typed Edge Upsert

- [ ] **EDGE-01**: MCP client can call `upsert_typed_edges` with `group_id`, `batch_id`, `dry_run`, `atomic`, `strict_endpoints`, and a bounded edge list
- [ ] **EDGE-02**: Server accepts only the 16 documented catalog edge types and requires explicit DDL or Oracle dictionary evidence for `EnforcedBy`
- [ ] **EDGE-03**: Server resolves both endpoints by `group_id`, `graph_key`, and expected entity type before generating fact embeddings
- [ ] **EDGE-04**: Edge upsert rejects missing, generic-only, or mistyped endpoints and never creates an endpoint implicitly
- [ ] **EDGE-05**: Server embeds the edge fact with the configured embedder before opening the write transaction
- [ ] **EDGE-06**: Edge persistence uses Graphiti-compatible `RELATES_TO` relationships with allowlisted type stored in searchable edge fields
- [ ] **EDGE-07**: Edge updates preserve source and target UUIDs, endpoint labels, original `created_at`, and add or advance `updated_at`
- [ ] **EDGE-08**: Multiple `ForeignKeyTo` edges can connect the same endpoints when their edge keys or documented relationship IDs differ
- [ ] **EDGE-09**: An existing deterministic edge UUID with conflicting type, key, source, or target returns `edge_identity_conflict` without mutation
- [ ] **EDGE-10**: Atomic edge upsert commits all valid items or rolls back the full request when one item is invalid, conflicting, or fails to write
- [ ] **EDGE-11**: Concurrent or repeated identical edge upserts result in one logical relationship per deterministic identity
- [ ] **EDGE-12**: Existing `search_memory_facts` can retrieve deterministic catalog facts

### Batch Verification

- [ ] **VERI-01**: MCP client can call read-only `verify_catalog_batch` by batch ID, explicit entity graph keys, explicit edge keys, or a combination
- [ ] **VERI-02**: Entity verification reports expected/found counts plus missing, wrong-type, generic duplicate, typed duplicate, UUID mismatch, and missing-embedding lists
- [ ] **VERI-03**: Edge verification reports expected/found counts plus missing, duplicate-edge-key, endpoint-mismatch, and missing-embedding lists
- [ ] **VERI-04**: Verification can require or skip provenance and reports missing provenance targets
- [ ] **VERI-05**: Verification never writes graph data or generates embeddings

### Phase 1 Quality Gate

- [ ] **GATE-01**: Focused unit tests cover configuration, strict validation, allowlists, canonical hashes, deterministic UUIDs, errors, and embedding-before-transaction ordering
- [ ] **GATE-02**: Neo4j integration tests create and verify only `oracle-catalog-tool-test` fixtures, including six typed entities, four structural edges, two distinct foreign keys, conflicts, retries, concurrency, search, and rollback
- [ ] **GATE-03**: Phase 1 tests verify no LLM call, no queue call, no generic endpoint creation, and no mutation outside the dedicated test group
- [x] **GATE-04**: Formatter, linter, changed-code type checking, MCP tool-schema listing, and relevant existing MCP tests pass
- [x] **GATE-05**: A short Phase 1 report records exact commands/results and explicitly gates Phase 2

### Provenance

- [ ] **PROV-01**: MCP client can call `upsert_provenance` with deterministic source metadata and existing entity/edge targets
- [ ] **PROV-02**: Provenance write uses deterministic source UUID, canonical source hash, exact reference time, and safe source attributes
- [ ] **PROV-03**: Provenance reuses the installed Graphiti 0.29.2 Episodic/MENTIONS and fact-provenance representation without calling `add_episode`, LLM extraction, or the queue
- [ ] **PROV-04**: Provenance links sources to existing entities and attaches source identity to existing facts using the closest compatible installed Graphiti representation
- [ ] **PROV-05**: Provenance rejects missing entity or edge targets with `provenance_target_missing` and no partial write
- [ ] **PROV-06**: Identical provenance reruns return unchanged and never create an unrelated generic domain entity

### Persistent Ingest Status

- [ ] **STAT-01**: Server persists restart-safe ingest state in Neo4j under a non-`Entity` `CatalogIngestBatch` label
- [ ] **STAT-02**: Batch status stores deterministic batch UUID, IDs, hashes, lifecycle timestamps, status, item counts, and bounded error summary
- [ ] **STAT-03**: Batch status supports `planned`, `validating`, `embedding`, `writing`, `committed`, and `failed`
- [ ] **STAT-04**: Batch status never stores API keys, raw documents, complete source text, or full request payloads
- [ ] **STAT-05**: MCP client can call read-only `get_catalog_ingest_status` after server reinitialization and receive persisted state and counts
- [ ] **STAT-06**: Batch status nodes do not appear in Graphiti entity search or community inputs

### Atomic Catalog Batch

- [ ] **BATC-01**: MCP client can call `upsert_catalog_batch` with group, batch and catalog hashes, entities, edges, provenance, dry-run, and atomic controls
- [ ] **BATC-02**: Server validates the complete nested request and all configured limits before any persistent side effect
- [ ] **BATC-03**: Server computes canonical request SHA-256 and returns `batch_conflict` for a committed batch ID reused with different content
- [ ] **BATC-04**: Batch endpoint resolution includes both entities already in Neo4j and entities included in the same request
- [ ] **BATC-05**: Server detects all known identity, type, endpoint, hash, and provenance conflicts before domain writes
- [ ] **BATC-06**: Server generates all required entity and edge embeddings before opening the domain write transaction
- [ ] **BATC-07**: One Neo4j transaction upserts typed entities, typed edges, provenance, and committed batch state atomically
- [ ] **BATC-08**: A domain write failure rolls back every domain mutation and persists failed status in a separate safe transaction
- [ ] **BATC-09**: An identical committed batch ID and request hash returns unchanged without duplicating domain objects
- [ ] **BATC-10**: Batch dry-run performs complete validation, identity resolution, endpoint planning, and conflict checks without graph writes or persistent status
- [ ] **BATC-11**: Combined ACCEPT_TAB fixture batch, retry, conflict, missing-endpoint rollback, persisted failure/success status, search interop, and service reinitialization tests pass
- [ ] **BATC-12**: `build_communities` executes against batch-created entities without schema errors, but normal upserts never invoke it

### Documentation and Final Verification

- [ ] **DOCS-01**: MCP documentation explains each deterministic catalog tool and warns that it is an administrative structured-ingestion surface
- [ ] **DOCS-02**: Documentation lists required configuration, immutable namespace warning, supported entity/edge types, batch limits, idempotency, atomicity, and structured errors
- [ ] **DOCS-03**: Documentation distinguishes `add_memory` semantic ingestion from deterministic PDF catalog, DDL, Oracle dictionary, and SQL parser ingestion
- [ ] **DOCS-04**: Documentation includes sanitized ACCEPT_TAB requests, Kubernetes ConfigMap/environment examples, and rollout/rollback notes without deploying or exposing credentials
- [ ] **DOCS-05**: Final verification lists all seven MCP tool schemas, exact test/format/lint/type-check results, Graphiti/Neo4j limitations, unchanged live-group confirmation, image build command, and fresh canary recommendation

## v2 Requirements

Deferred beyond this milestone.

### Backend Expansion

- **BACK-01**: Deterministic catalog persistence supports FalkorDB after equivalent transaction, label, vector, provenance, and concurrency semantics are designed and tested
- **BACK-02**: Deterministic catalog persistence supports other Graphiti backends only after explicit capability analysis

### Operations

- **OPER-01**: Operator can run a separately approved production canary against `oracle-catalog-v2`
- **OPER-02**: Operator can run the full 14,106-entity and 30,000+-edge catalog ingestion after canary verification
- **OPER-03**: Deployment automation can apply the documented Kubernetes configuration after separate approval

## Out of Scope

| Feature | Reason |
|---------|--------|
| Kubernetes deployment | Documentation only; task explicitly forbids deployment |
| Live write to `oracle-catalog-v2` | Implementation and tests must not mutate a live group |
| Full catalog ingestion | Task ends with tools and canary recommendation, not ingest execution |
| `clear_graph` or existing-data deletion | Avoid destructive or unrelated graph mutation |
| `add_memory` queue changes | Preserve backward compatibility and existing semantics |
| LLM extraction for deterministic catalogs | Violates exact identity and relationship requirements |
| Implicit or generic endpoint creation | Violates typed graph integrity |
| Caller-controlled Neo4j UUIDs | Violates server deterministic identity authority |
| Automatic UUID namespace creation | Namespace changes re-key the complete catalog |
| Arbitrary Cypher, labels, relationship types, or property names | Prevent injection and schema drift |
| Multi-backend support claim | Neo4j is the only implementation/test target for this milestone |
| Automatic community creation | Maintenance behavior is separate from deterministic ingestion |
| Production graph repair or migration tooling | Requires separate design and authorization |

## Traceability

Every v1 requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONF-01 | Phase 1 | Pending |
| CONF-02 | Phase 1 | Pending |
| CONF-03 | Phase 1 | Pending |
| CONF-04 | Phase 1 | Pending |
| CONF-05 | Phase 1 | Pending |
| SAFE-01 | Phase 1 | Pending |
| SAFE-02 | Phase 1 | Pending |
| SAFE-03 | Phase 1 | Pending |
| SAFE-04 | Phase 1 | Pending |
| SAFE-05 | Phase 1 | Pending |
| IDEN-01 | Phase 1 | Pending |
| IDEN-02 | Phase 1 | Pending |
| IDEN-05 | Phase 1 | Pending |
| IDEN-06 | Phase 1 | Pending |
| IDEN-07 | Phase 1 | Pending |
| IDEN-08 | Phase 1 | Pending |
| ENTY-01 | Phase 1 | Pending |
| ENTY-02 | Phase 1 | Pending |
| ENTY-03 | Phase 1 | Pending |
| ENTY-04 | Phase 1 | Pending |
| ENTY-05 | Phase 1 | Pending |
| ENTY-06 | Phase 1 | Pending |
| ENTY-07 | Phase 1 | Pending |
| ENTY-08 | Phase 1 | Pending |
| ENTY-09 | Phase 1 | Pending |
| ENTY-10 | Phase 1 | Pending |
| ENTY-11 | Phase 1 | Pending |
| ENTY-12 | Phase 1 | Pending |
| ENTY-13 | Phase 1 | Pending |
| RESO-01 | Phase 1 | Pending |
| RESO-02 | Phase 1 | Pending |
| RESO-03 | Phase 1 | Pending |
| RESO-04 | Phase 1 | Pending |
| EDGE-01 | Phase 1 | Pending |
| EDGE-02 | Phase 1 | Pending |
| EDGE-03 | Phase 1 | Pending |
| EDGE-04 | Phase 1 | Pending |
| EDGE-05 | Phase 1 | Pending |
| EDGE-06 | Phase 1 | Pending |
| EDGE-07 | Phase 1 | Pending |
| EDGE-08 | Phase 1 | Pending |
| EDGE-09 | Phase 1 | Pending |
| EDGE-10 | Phase 1 | Pending |
| EDGE-11 | Phase 1 | Pending |
| EDGE-12 | Phase 1 | Pending |
| VERI-01 | Phase 1 | Pending |
| VERI-02 | Phase 1 | Pending |
| VERI-03 | Phase 1 | Pending |
| VERI-04 | Phase 1 | Pending |
| VERI-05 | Phase 1 | Pending |
| GATE-01 | Phase 1 | Pending |
| GATE-02 | Phase 1 | Pending |
| GATE-03 | Phase 1 | Pending |
| GATE-04 | Phase 1 | Complete |
| GATE-05 | Phase 1 | Complete |
| IDEN-03 | Phase 2 | Pending |
| IDEN-04 | Phase 2 | Pending |
| PROV-01 | Phase 2 | Pending |
| PROV-02 | Phase 2 | Pending |
| PROV-03 | Phase 2 | Pending |
| PROV-04 | Phase 2 | Pending |
| PROV-05 | Phase 2 | Pending |
| PROV-06 | Phase 2 | Pending |
| STAT-01 | Phase 2 | Pending |
| STAT-02 | Phase 2 | Pending |
| STAT-03 | Phase 2 | Pending |
| STAT-04 | Phase 2 | Pending |
| STAT-05 | Phase 2 | Pending |
| STAT-06 | Phase 2 | Pending |
| BATC-01 | Phase 2 | Pending |
| BATC-02 | Phase 2 | Pending |
| BATC-03 | Phase 2 | Pending |
| BATC-04 | Phase 2 | Pending |
| BATC-05 | Phase 2 | Pending |
| BATC-06 | Phase 2 | Pending |
| BATC-07 | Phase 2 | Pending |
| BATC-08 | Phase 2 | Pending |
| BATC-09 | Phase 2 | Pending |
| BATC-10 | Phase 2 | Pending |
| BATC-11 | Phase 2 | Pending |
| BATC-12 | Phase 2 | Pending |
| DOCS-01 | Phase 2 | Pending |
| DOCS-02 | Phase 2 | Pending |
| DOCS-03 | Phase 2 | Pending |
| DOCS-04 | Phase 2 | Pending |
| DOCS-05 | Phase 2 | Pending |

**Coverage:**

- v1 requirements: 86 total (corrected from earlier 81 miscount)
- Mapped to phases: 86
- Unmapped: 0
- Phase 1: 55 (CONF 5, SAFE 5, IDEN 6, ENTY 13, RESO 4, EDGE 12, VERI 5, GATE 5)
- Phase 2: 31 (IDEN 2, PROV 6, STAT 6, BATC 12, DOCS 5)

---
*Requirements defined: 2026-07-16*
*Last updated: 2026-07-16 after roadmap creation*
