# Deterministic Catalog Ingestion for Graphiti MCP

## What This Is

An extension to the existing Graphiti MCP server that adds synchronous, typed, deterministic, idempotent Neo4j upsert tools for structured database catalogs. It targets PDF catalog, DDL, Oracle dictionary, and SQL parser output where entity and relationship identity must be exact and no LLM extraction or asynchronous ingestion may occur.

The v1.0 implementation preserves existing Graphiti and MCP behavior. It delivered a gated typed-primitives foundation followed by provenance and atomic batch orchestration.

## Core Value

A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.

## Current Milestone: v1.1 Catalog-v2 Pre-Canary Hardening

**Goal:** Harden deterministic catalog identity, validation, provenance, prepare/commit, manifest, and verification contracts before any regenerated canary is executed.

**Target features:**
- Strict recursive catalog request contracts and fail-closed catalog-v2 FE/BO identity grammar
- Server-owned edge endpoint maps plus authoritative batch hashing and capabilities discovery
- Restart-safe immutable prepare/commit/discard protocol with exact evidence links
- Durable batch manifests, manifest-backed verification, typed edge resolution, and split read/write gates
- Exhaustive unit, service, store, MCP, concurrency, live Neo4j, security, compatibility, and documentation coverage

## Requirements

### Validated

- ✓ Phase 0 recorded the live 14 legacy + 7 catalog MCP tool baseline and offline historical canary evidence — Phase 0
- ✓ Phase 0 froze the catalog-v1 compatibility boundary and test-group/canary/dirty-tree/remote isolation policy — Phase 0
- ✓ Catalog requests reject unknown fields recursively, enforce immutable execution flags, and require collision-safe catalog-v2 FE/BO/COMMON identity — Phase 1
- ✓ Every catalog edge type enforces one finite server-owned endpoint map before side effects — Phase 2
- ✓ Combined batch hashes cover the complete canonical domain and echo authoritative server hashes — Phase 2
- ✓ Explicit catalog evidence links replace Cartesian batch provenance while preserving standalone legacy compatibility — Phase 2
- ✓ Read-only capabilities expose versions, registries, topology, limits, and safe namespace fingerprint without mutation — Phase 2
- ✓ Standard Graphiti MCP tools already expose semantic ingestion, search, triplet, maintenance, and deletion operations — existing
- ✓ The MCP server already supports YAML configuration with environment expansion and Pydantic validation — existing
- ✓ Neo4j is supported through an asynchronous driver with real transactions — existing
- ✓ Graphiti already provides configured embedding clients and node/edge hybrid search — existing
- ✓ `group_id` already partitions Graphiti graph data and search — existing
- ✓ Existing entity, edge, episodic, and provenance models provide the installed schema baseline — existing

### Active

- [ ] Agents can prepare, commit, replay, and discard bounded restart-safe immutable batch plans
- [ ] Every committed batch has a durable exact manifest and manifest-backed verification
- [ ] Read-only catalog diagnostics remain usable while catalog mutation is disabled
- [ ] Existing legacy MCP contracts, deterministic guarantees, search interoperability, and graph isolation remain intact
- [ ] Catalog-v2 migration and regenerated-canary guidance are complete without executing a canary

### Delivered in v1.0

- ✓ Validated catalog-upsert configuration with an explicitly supplied immutable UUID namespace and conservative limits
- ✓ Strict allowlisted entity, edge, source, and batch models with protected-property, hash, size, prefix, confidence, finite-number, and full-string group validation
- ✓ Synchronous deterministic entity/edge upsert, read-only resolve/verify, installed-schema provenance, restart-safe status, and atomic nested batch tools
- ✓ UUIDv5 identities, canonical SHA-256 audit, embeddings before transactions, atomic source compare-and-set, and explicitly ordered retained provenance locks
- ✓ Exact endpoint enforcement, no caller UUID authority, no generic endpoint creation, no LLM extraction, no queueing, no implicit communities
- ✓ Data preservation for creation time, raw/canonical names, labels, endpoints, source references, provenance, and update time
- ✓ Unit/live/concurrency/isolation/search/community/regression coverage using only `oracle-catalog-tool-test`
- ✓ Operator documentation for all seven tools, configuration, limits, errors, sanitized ACCEPT_TAB, rollout/rollback, build, and semantic-versus-deterministic guidance
- ✓ Independent Phase 1 and Phase 2 verification; 86/86 v1 requirements satisfied

### Out of Scope

- Kubernetes deployment — configuration may be documented, but this task must not deploy
- `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` — edge vocabulary additions require later inference/schema approval
- Full catalog ingestion — only fixtures and a future canary procedure are prepared
- Existing live graph groups — tests use only `oracle-catalog-tool-test`; `oracle-catalog-v2` is not mutated during implementation
- Graph deletion or cleanup operations — never call `clear_graph` or delete existing graph data
- `add_memory` queue behavior — preserve it unchanged
- LLM extraction for structured catalog data — deterministic tools bypass extraction entirely
- Backend portability claims — implement and test Neo4j first; isolate service boundaries only for future work
- Arbitrary Cypher, arbitrary labels, or arbitrary Neo4j property-name exposure — fixed server-owned schemas only
- Automatic UUID namespace generation — deployments must provide one fixed UUID explicitly
- Automatic community creation during upsert — only compatibility execution is tested
- Oracle dictionary, SQL, or PL/SQL parsing — follows only after substrate hardening and canary validation
- Relationship scoring or inference and agent context/path/impact tools — later retrieval milestone
- Catalog delta, retirement, business transaction entities, or FE/BO runtime correlation — later domain work
- Automatic catalog-v1 to catalog-v2 identity migration — identities must never be silently reinterpreted
- Production migration, production writes, or canary execution — requires separate approval after v1.1 verification

## Context

The intended catalog contains approximately 14,106 deterministic entities and more than 30,000 deterministic relationships. Existing ingestion paths are unsafe for this baseline: `add_memory` is asynchronous and invokes extraction; fresh caller episode UUIDs fail with the installed Graphiti behavior; semantic episodes can infer unwanted relationships; `excluded_entity_types` depends on the live registry; and `add_triplet` can create generic endpoints when named entities do not exist.

A cherry-picked pre-hardening canary workflow now exists in `scripts/`, `catalog/canary-v2-requests/`, and `mcp_server/tests/test_catalog_canary_scripts.py`. Repository artifacts record an ACCEPT_TAB dry-run and commit against `oracle-catalog-v2` using the old identity/provenance/hash contract. v1.1 inventories that evidence offline only: it must not query, mutate, retry, or mechanically reuse the live group, old golden hash, 10/16/1 receipt, or 38/85 plan.

Entity identity is UUIDv5 over `group_id|entity_type|graph_key`. Edge identity is UUIDv5 over `group_id|edge_type|edge_key`. Source identity is UUIDv5 over `group_id|Source|source_key`. Batch identity is UUIDv5 over `group_id|Batch|batch_id`. Every mutable domain payload is canonicalized and audited with exactly 64 lowercase hexadecimal SHA-256 characters; MD5 is forbidden.

Allowed entity types and graph-key prefixes are fixed:

| Entity type | Prefix |
|-------------|--------|
| Database | `DATABASE::` |
| DictionaryDocument | `DOC::` |
| Schema | `SCHEMA::` |
| Table | `TABLE::` |
| View | `VIEW::` |
| MaterializedView | `MVIEW::` |
| Column | `COLUMN::` |
| Constraint | `CONSTRAINT::` |
| Index | `INDEX::` |
| Package | `PACKAGE::` |
| Procedure | `PROCEDURE::` |
| Function | `FUNCTION::` |
| Trigger | `TRIGGER::` |
| Sequence | `SEQUENCE::` |
| Synonym | `SYNONYM::` |

Allowed edge types are `Contains`, `PrimaryKeyOf`, `UniqueKeyOf`, `ForeignKeyTo`, `EnforcedBy`, `TriggerOn`, `SynonymFor`, `DocumentedBy`, `Calls`, `ReadsFrom`, `WritesTo`, `JoinsWith`, `ReferencesByCode`, `DependsOn`, `DerivedFrom`, and `UsesSequence`. `EnforcedBy` requires explicit DDL or Oracle dictionary evidence.

Phase 1 delivers `upsert_typed_entities`, `upsert_typed_edges`, `resolve_typed_entities`, and `verify_catalog_batch`. Phase 2 may begin only after Phase 1 focused unit and Neo4j integration tests, formatting, changed-code type checking, MCP tool listing, relevant existing MCP tests, and generic-duplicate checks all pass. A short Phase 1 report records the gate result.

Phase 2 delivers `upsert_provenance`, `upsert_catalog_batch`, and `get_catalog_ingest_status`. Provenance must follow the installed Graphiti representation. If direct episode-to-entity-edge linking is unsupported, the implementation must document that schema and use the closest compatible existing representation rather than silently inventing one.

Required structured error codes include `validation_error`, `feature_disabled`, `invalid_uuid_namespace`, `batch_limit_exceeded`, `content_hash_mismatch`, `entity_type_conflict`, `graph_key_prefix_mismatch`, `deterministic_uuid_conflict`, `missing_endpoint`, `endpoint_type_mismatch`, `generic_endpoint_conflict`, `edge_identity_conflict`, `batch_conflict`, `provenance_target_missing`, `neo4j_transaction_failed`, `embedding_failed`, and `internal_error`.

Existing unrelated working-tree changes in `mcp_server/k8s/graphiti-neo4j.yaml`, `.codegraph/`, and `mcp_server/sample_catalog.json` must be preserved and excluded from task commits unless explicitly needed and approved.

## Constraints

- **Compatibility**: Preserve every existing MCP tool and behavior — this is additive functionality
- **Backend**: Neo4j first, using installed driver semantics and Neo4j 5.26+ behavior — no unsupported portability claim
- **Identity**: Server-derived UUIDv5 only, using a fixed configured namespace — caller UUIDs are never identity authority
- **Configuration**: `GRAPHITI_CATALOG_UUID_NAMESPACE` is immutable deployment configuration — changing it changes every deterministic identity
- **Safety**: Never interpolate unvalidated client labels or property names into Cypher — labels and properties come from fixed server allowlists
- **Transactions**: Writes return only after commit or rollback; atomic batches roll back completely on conflict or write failure
- **Embeddings**: Generate with the configured embedder before opening the Neo4j write transaction — embedding failure cannot produce partial writes
- **Isolation**: Every read and write is constrained by `group_id`; tests use only `oracle-catalog-tool-test`
- **Validation**: Validate complete requests, collection limits, string limits, hashes, prefixes, nested references, confidence range, NaN, infinity, and protected properties
- **Logging**: Log batch IDs and counts only — never credentials, complete catalog payloads, raw documents, or complete source text
- **Data preservation**: Preserve original `created_at`, endpoint UUIDs, labels, and exact `name_raw`/`name_canonical`; add `updated_at`
- **Scale**: Default limits are 500 entities, 2,000 edges, and 5,000 provenance links per batch
- **Workflow**: Phase 2 is blocked until every Phase 1 gate passes and a Phase 1 report is produced
- **Operations**: No deployment, live-group writes, full ingest, graph clearing, or existing-data deletion

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Add dedicated deterministic administrative MCP tools | Semantic ingestion cannot guarantee exact catalog identities or relationships | ✓ Delivered |
| Use Neo4j-specific persistence where Graphiti save paths lose labels, attributes, or embeddings | Correct typed persistence outranks premature backend abstraction | ✓ Delivered |
| Use fixed allowlists for entity labels, edge types, and graph-key prefixes | Prevent schema drift and Cypher injection | ✓ Delivered |
| Use canonical SHA-256 plus deterministic UUIDv5 | Enables safe retry, change detection, and auditable identity | ✓ Delivered |
| Require existing typed endpoints for standalone edge upserts | Prevent generic endpoint creation and accidental graph expansion | ✓ Delivered |
| Store ingest status under non-`Entity` label `CatalogIngestBatch` | Persist restart-safe status without polluting Graphiti search | ✓ Delivered |
| Gate Phase 2 on Phase 1 integration quality | Provenance and orchestration depend on trusted typed primitives | ✓ Gate passed before Phase 2 |
| Keep normal upserts community-neutral | Community construction is maintenance behavior, not ingestion behavior | ✓ Delivered |
| Use source CAS and ordered retained target locks | Close provenance validation/mutation TOCTOU under concurrent writes | ✓ Delivered |
| Treat pre-hardening ACCEPT_TAB artifacts as offline historical evidence only | Catalog-v1 hashes and receipts cannot authorize hardened catalog-v2 behavior | ✓ Phase 0 |
| Gate Phase 1 on recorded artifacts, safety invariants, and truthful pass/fail/skip results | Baseline failures must remain distinguishable from v1.1 regressions | ✓ Phase 0 |
| Use one immutable server-owned endpoint registry for all 16 approved edge types | Client-supplied or divergent topology would create invalid searchable truth | ✓ Phase 2 |
| Replace catalog-v2 Cartesian provenance with explicit one-source/one-target evidence links | Prevent implicit or inflated provenance while preserving standalone legacy behavior until Phase 3B | ✓ Phase 2 |
| Hash the complete canonical batch domain under one versioned recipe | Omitted fields would create false idempotence and unsafe prepare/commit replay | ✓ Phase 2 |
| Keep capability discovery mutation-free and available while writes are disabled | Agents need safe contract discovery before attempting writes | ✓ Phase 2 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-18 after Phase 2*
