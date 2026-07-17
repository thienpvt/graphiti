# Feature Research

**Domain:** Deterministic catalog-ingestion MCP tools (Graphiti MCP / Neo4j)
**Researched:** 2026-07-16
**Confidence:** HIGH (sourced from `.planning/PROJECT.md` Active/Out-of-Scope contracts + installed MCP/core behavior; no invented product features)

## Feature Landscape

### Table Stakes (Users Expect These)

Production-safe catalog upserts require these contracts. Missing any of them breaks safe retry, typed identity, or search interoperability for structured catalogs.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Catalog-upsert configuration (`GRAPHITI_CATALOG_UUID_NAMESPACE` + conservative batch limits) | Immutable UUID namespace is identity root; limits bound memory/tx size | MEDIUM | Namespace must be explicitly supplied; never auto-generated. Defaults: 500 entities / 2,000 edges / 5,000 provenance links per batch |
| Strict allowlisted request models (entity, edge, source, batch) | Reject schema drift, Cypher injection, oversized/invalid payloads | HIGH | Protect properties; validate hash, size, prefix, confidence [0,1], finite numbers (reject NaN/inf) |
| `upsert_typed_entities` (sync, deterministic UUIDv5, SHA-256-audited, embedding-backed, typed Neo4j tx) | One retryable catalog entity = one committed typed node | HIGH | Phase 1. Identity: UUIDv5(`namespace`, `group_id\|entity_type\|graph_key`). Embed before write tx |
| `resolve_typed_entities` (read-only preflight) | Detect missing/generic/duplicate/mistyped/UUID-mismatched/unembedded entities before write | MEDIUM | Phase 1. No mutations |
| `upsert_typed_edges` with pre-existing typed endpoints only | Exact relationships without implicit endpoint creation | HIGH | Phase 1. Identity: UUIDv5(`namespace`, `group_id\|edge_type\|edge_key`). Fail on missing/mistyped/generic endpoints |
| `verify_catalog_batch` (read-only batch/key verification) | Post-write/pre-orchestration audit of identities, types, endpoints, duplicates, embeddings, optional provenance | MEDIUM | Phase 1 gate companion |
| Synchronous MCP write semantics | Caller must know commit vs rollback; async queue is unsafe for catalog baseline | MEDIUM | All new write tools return only after commit or rollback; no ingestion queue |
| No LLM / no extraction on catalog path | Semantic extraction invents unwanted nodes/edges; non-deterministic | LOW–MEDIUM | Bypass `add_episode` / `add_memory` extraction entirely |
| Server-derived UUIDv5 only | Caller UUID authority collides with Graphiti episode/triplet semantics | MEDIUM | Never treat caller-supplied DB UUIDs as identity authority |
| SHA-256 canonical content hash (exactly 64 lowercase hex) | Change detection, audit, idempotent re-upsert | MEDIUM | MD5 forbidden. Persist hash on domain payloads |
| Fixed entity-type allowlist + graph-key prefixes | Exact catalog ontology; prefix mismatch = validation failure | LOW | Database/`DATABASE::`, DictionaryDocument/`DOC::`, Schema/`SCHEMA::`, Table/`TABLE::`, View/`VIEW::`, MaterializedView/`MVIEW::`, Column/`COLUMN::`, Constraint/`CONSTRAINT::`, Index/`INDEX::`, Package/`PACKAGE::`, Procedure/`PROCEDURE::`, Function/`FUNCTION::`, Trigger/`TRIGGER::`, Sequence/`SEQUENCE::`, Synonym/`SYNONYM::` |
| Fixed edge-type allowlist | Prevent free-form relationship sprawl | LOW | Contains, PrimaryKeyOf, UniqueKeyOf, ForeignKeyTo, EnforcedBy, TriggerOn, SynonymFor, DocumentedBy, Calls, ReadsFrom, WritesTo, JoinsWith, ReferencesByCode, DependsOn, DerivedFrom, UsesSequence. `EnforcedBy` requires explicit DDL/Oracle dictionary evidence |
| `group_id` isolation on every read/write | Multi-tenant partition already core Graphiti contract | LOW | Tests only `oracle-catalog-tool-test`; never mutate `oracle-catalog-v2` during implementation |
| Item-level structured error codes | Batch partial diagnosis without opaque strings | MEDIUM | Required codes: `validation_error`, `feature_disabled`, `invalid_uuid_namespace`, `batch_limit_exceeded`, `content_hash_mismatch`, `entity_type_conflict`, `graph_key_prefix_mismatch`, `deterministic_uuid_conflict`, `missing_endpoint`, `endpoint_type_mismatch`, `generic_endpoint_conflict`, `edge_identity_conflict`, `batch_conflict`, `provenance_target_missing`, `neo4j_transaction_failed`, `embedding_failed`, `internal_error` |
| Preserve `created_at`; add `updated_at`; keep exact `name_raw`/`name_canonical`, labels, endpoint UUIDs | Idempotent update must not rewrite history or normalize away OCR/source fidelity | MEDIUM | Re-upsert same identity updates payload/hash/embedding/`updated_at` only |
| Embeddings via configured embedder before Neo4j write transaction | Embedding failure must not leave partial graph writes | MEDIUM | Same embedder stack as existing Graphiti; failure → `embedding_failed`, no open write tx |
| Neo4j-first typed persistence (preserve labels/attributes/embeddings) | Graphiti generic save paths can lose typed labels/attrs | HIGH | Prefer Neo4j 5.26+ driver semantics; no multi-backend claims in this milestone |
| Additive MCP surface only | Existing tools (`add_memory`, search, triplet, delete, communities, clear_graph) stay unchanged | LOW | Catalog tools are new; do not change queue behavior |
| Phase 1 quality gate before Phase 2 | Provenance/orchestration must rest on trusted primitives | MEDIUM | Unit + Neo4j integration + format + typecheck + MCP schema registration + regression + generic-duplicate checks; short Phase 1 report |
| Focused tests on `oracle-catalog-tool-test` only | Avoid live catalog group mutation | MEDIUM | Unit + Neo4j integration; no `clear_graph` / live-group writes |
| Search interoperability verification | Catalog nodes/edges must remain findable via existing hybrid search | MEDIUM | Verify `search_nodes`, `search_memory_facts`; safe `build_communities` execution (compatibility only, not auto-build on upsert) |
| Documentation (tools, config, namespace immutability, allowlists, idempotency, atomicity, limits, ACCEPT_TAB examples, rollout/rollback, build command, semantic-vs-deterministic guidance) | Operators and agents must not misuse `add_memory` for catalogs | LOW | Rollout/rollback without deployment automation |

### Differentiators (Competitive Advantage)

These are the value of this milestone relative to existing Graphiti MCP semantic ingestion. They are still required by PROJECT.md Active requirements, but they are what make the product fit structured catalogs.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Deterministic UUIDv5 identity over fixed identity strings | Exact one-object identity for ~14k entities / 30k+ edges; safe retry | HIGH | Entity: `group_id\|entity_type\|graph_key`; Edge: `group_id\|edge_type\|edge_key`; Source: `group_id\|Source\|source_key`; Batch: `group_id\|Batch\|batch_id` |
| Idempotent typed upserts (hash-audited) | Re-run same batch → same graph; detect content change without duplicate nodes | HIGH | Core Value: “retry safely and commit as exactly one deterministic, correctly typed, searchable Neo4j object” |
| No implicit generic endpoint creation | Avoids `add_triplet` class of graph pollution when names/UUIDs missing | HIGH | Standalone edge upsert requires pre-existing **typed** endpoints |
| `upsert_provenance` on installed episodic/provenance schema (no `add_episode`, no LLM, no queue, no generic domain nodes) | Trace catalog rows to PDF/DDL/dictionary evidence without semantic extraction | HIGH | Phase 2. If direct episode→entity linking unsupported, document closest installed representation — do not invent schema |
| `CatalogIngestBatch` status nodes + `get_catalog_ingest_status` | Restart-safe batch status without polluting Entity search | MEDIUM | Phase 2. Non-`Entity` label; internal status only |
| `upsert_catalog_batch` atomic orchestration | One request: validate → resolve endpoints → pre-tx embeddings → one atomic domain tx → safe failed-status persistence → retry idempotency → batch conflict detection | HIGH | Phase 2 only after Phase 1 gate. Complete validation of nested collections |
| Same-request endpoint resolution inside batch | Batch can introduce entities then edges without multi-round-trip races | HIGH | Phase 2; standalone `upsert_typed_edges` still forbids implicit create |
| Explicit semantic-vs-deterministic ingestion guidance | Agents choose `add_memory` for narrative memory, catalog tools for dictionaries/DDL | LOW | Documentation + tool purpose clarity |

### Anti-Features (Commonly Requested, Often Problematic)

Explicit PROJECT.md Out of Scope / Constraints. Do not build.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| LLM extraction for structured catalog data | Reuse `add_memory` / episodes | Non-deterministic identities, inferred relationships, unwanted generics | Deterministic typed upsert tools only |
| Async queue / fire-and-forget catalog writes | Match `add_memory` DX | Success ≠ commit; restart drops work; partial state | Synchronous tools; return after commit/rollback |
| Caller-supplied database UUID as identity authority | Client convenience | Collides with Graphiti UUID semantics; breaks determinism | Server UUIDv5 from configured namespace + graph keys |
| Automatic UUID namespace generation | Zero-config deploy | Changing namespace rewrites every identity | Require explicit immutable `GRAPHITI_CATALOG_UUID_NAMESPACE` |
| Implicit endpoint creation on edge upsert | Fewer round-trips | Generic Entity nodes; type drift; hard cleanup | Pre-create via `upsert_typed_entities` or batch same-request resolution |
| Arbitrary Cypher / labels / property names from client | Flexibility | Cypher injection; schema drift | Fixed server allowlists only |
| Full catalog production ingest in this milestone | Ship the ~14k object catalog | Out of scope; live groups risk | Fixtures + future canary only; test group `oracle-catalog-tool-test` |
| Kubernetes deployment / live rollout automation | Ops convenience | Task must not deploy | Document config only |
| Mutating existing live groups (`oracle-catalog-v2`, etc.) | Validate against real data | Data loss / pollution | Tests only `oracle-catalog-tool-test` |
| Graph deletion / `clear_graph` in catalog workflow | Easy test reset | Destroys unrelated data | Never call clear/delete existing graph data in this work |
| Changing `add_memory` queue behavior | Make semantic path “safer” | Breaks existing MCP contracts | Leave queue unchanged |
| Multi-backend portability claims (FalkorDB/Kuzu/Neptune) | Abstraction purity | Typed persistence needs Neo4j semantics first | Neo4j first; isolate service boundaries only for future work |
| Automatic community creation during upsert | Search quality | Heavy LLM maintenance; not ingestion | Community-neutral upserts; only verify `build_communities` still runs safely |
| MD5 or non-canonical hashing | Legacy familiarity | Collision / audit weakness | SHA-256, 64 lowercase hex only |
| Logging full payloads / source text / credentials | Debug ease | Secrets and PII in logs | Log batch IDs and counts only |
| Invented provenance schema if episode linking differs | “Clean” design | Diverges from installed Graphiti search/provenance | Closest compatible installed representation + document gap |

## Feature Dependencies

```
Catalog config (namespace + limits + feature flag)
    └──requires──> Allowlisted request models + validation
                       └──requires──> Deterministic identity (UUIDv5 + SHA-256)
                                          ├──requires──> Pre-tx embeddings (configured embedder)
                                          │                  └──requires──> Neo4j typed write transactions
                                          │                                     ├──upsert_typed_entities
                                          │                                     └──upsert_typed_edges ──requires──> existing typed endpoints
                                          ├──resolve_typed_entities (read-only)
                                          └──verify_catalog_batch (read-only)

Phase 1 gate (unit + Neo4j int + format + typecheck + MCP registration + regression + generic-duplicate)
    └──blocks──> Phase 2

Phase 2:
upsert_typed_entities + upsert_typed_edges + verify_catalog_batch
    └──requires──> upsert_provenance (installed episodic/provenance schema)
    └──requires──> CatalogIngestBatch status + get_catalog_ingest_status
    └──requires──> upsert_catalog_batch (atomic orchestration)
                       ├──requires──> same-request endpoint resolution
                       ├──requires──> pre-transaction embeddings
                       ├──requires──> failed-status persistence without domain partial commit
                       └──requires──> retry idempotency + batch_conflict detection

Search interoperability ──enhances──> all typed upserts (must remain Entity-searchable where intended)
CatalogIngestBatch non-Entity label ──conflicts──> labeling status as Entity (would pollute search)
Deterministic path ──conflicts──> LLM extraction / add_memory queue for same catalog writes
Standalone upsert_typed_edges ──conflicts──> implicit endpoint creation
```

### Dependency Notes

- **Config requires allowlists:** Without fixed namespace and limits, identity and batch safety are undefined.
- **Edges require typed endpoints (standalone):** Prevents generic endpoint expansion observed with `add_triplet` when nodes are missing.
- **Embeddings before write tx:** Embedding failure must map to `embedding_failed` with zero domain mutation.
- **Phase 2 blocked on Phase 1 gate:** Provenance and batch orchestration depend on trusted entity/edge primitives.
- **Status nodes must not be `Entity`:** Otherwise `search_nodes` / community paths treat ingest bookkeeping as domain knowledge.
- **Atomic batch requires complete pre-validation:** Invalid nested item must not open domain transaction; conflicts roll back completely.
- **Provenance must not call `add_episode`:** That reintroduces LLM extraction and async/episode identity issues called out in PROJECT context.

## Behavioral Contracts (Production-Safe Upserts)

These are the non-negotiable runtime contracts for every catalog write tool.

| Contract | Rule |
|----------|------|
| Typed | Only allowlisted entity/edge/source/batch types and prefixes; labels/properties server-owned |
| Deterministic | Same namespace + `group_id` + type + key → same UUIDv5; same canonical payload → same SHA-256 |
| Synchronous | MCP caller blocked until commit or rollback |
| Idempotent | Re-upsert identical content: no duplicate nodes/edges; preserve `created_at`; refresh `updated_at`/payload/embeddings as needed |
| Auditable | Persist canonical payload SHA-256; structured item-level errors |
| Isolated | All ops constrained by `group_id` |
| Non-semantic | Zero LLM calls; zero ingestion queue; zero generic endpoint creation |
| Atomic (batch) | One domain transaction; conflict/write failure → full rollback; status persistence must not imply domain success |
| Searchable | Domain entities/edges remain compatible with existing hybrid search embeddings/labels |
| Safe ops | No deploy; no live-group mutation; no graph clear/delete; preserve unrelated working-tree files |

### Phase 1 Gate (explicit)

Phase 2 **must not start** until all of the following pass and a short Phase 1 report records the result:

1. Focused unit tests for catalog primitives
2. Neo4j integration tests (group `oracle-catalog-tool-test` only)
3. Formatting
4. Changed-code type checking
5. MCP tool listing / schema registration for new tools
6. Relevant existing MCP regression tests
7. Generic-duplicate checks (no accidental generic Entity endpoints from catalog path)

Phase 1 delivers: `upsert_typed_entities`, `upsert_typed_edges`, `resolve_typed_entities`, `verify_catalog_batch` (+ config, models, validation, docs slice as needed for those tools).

Phase 2 delivers: `upsert_provenance`, `upsert_catalog_batch`, `get_catalog_ingest_status` (+ `CatalogIngestBatch` status model).

## MVP Definition

### Launch With (v1 / Phase 1 — foundation)

- [ ] Catalog upsert configuration (immutable UUID namespace + batch limits + disable/feature path)
- [ ] Allowlisted entity/edge request models with full validation
- [ ] `upsert_typed_entities` — sync deterministic typed entity upsert
- [ ] `upsert_typed_edges` — sync deterministic typed edge upsert (typed endpoints required)
- [ ] `resolve_typed_entities` — read-only conflict/missing/generic/unembedded detector
- [ ] `verify_catalog_batch` — read-only identity/type/endpoint/embedding verification
- [ ] Structured error codes + `group_id` isolation
- [ ] Pre-tx embeddings; SHA-256 audit; preserve `created_at` / add `updated_at`
- [ ] Phase 1 unit + Neo4j integration + format + typecheck + MCP registration + regression gate report
- [ ] Minimal docs for Phase 1 tools, namespace immutability, allowlists, idempotency

### Add After Validation (v1.x / Phase 2 — only after gate)

- [ ] `upsert_provenance` — installed Graphiti episodic/provenance representation, no LLM/queue
- [ ] `CatalogIngestBatch` status nodes + `get_catalog_ingest_status`
- [ ] `upsert_catalog_batch` — complete validation, same-request endpoint resolution, pre-tx embeddings, one atomic domain tx, failed-status persistence, retry idempotency, `batch_conflict`
- [ ] Full docs: atomicity, limits, ACCEPT_TAB examples, rollout/rollback, semantic-vs-deterministic guidance
- [ ] Search interoperability + safe `build_communities` verification coverage expanded as needed

### Future Consideration (v2+ / explicitly deferred)

- [ ] Full production catalog ingest / canary procedure against real groups
- [ ] Kubernetes deployment automation
- [ ] Multi-backend (non-Neo4j) catalog persistence claims
- [ ] Automatic community updates on catalog upsert
- [ ] Any change to `add_memory` queue durability model
- [ ] Live-group migration tools or graph cleanup utilities

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Config + allowlisted models + validation | HIGH | MEDIUM | P1 |
| `upsert_typed_entities` | HIGH | HIGH | P1 |
| `upsert_typed_edges` (no implicit endpoints) | HIGH | HIGH | P1 |
| Deterministic UUIDv5 + SHA-256 + preserve timestamps/names | HIGH | MEDIUM | P1 |
| Sync / no LLM / no queue / no caller UUID authority | HIGH | MEDIUM | P1 |
| `resolve_typed_entities` | HIGH | MEDIUM | P1 |
| `verify_catalog_batch` | HIGH | MEDIUM | P1 |
| Structured errors + `group_id` isolation | HIGH | MEDIUM | P1 |
| Pre-tx embeddings + Neo4j typed tx | HIGH | HIGH | P1 |
| Phase 1 gate report + tests on `oracle-catalog-tool-test` | HIGH | MEDIUM | P1 |
| `upsert_provenance` | HIGH | HIGH | P2 (Phase 2) |
| `CatalogIngestBatch` + `get_catalog_ingest_status` | HIGH | MEDIUM | P2 |
| `upsert_catalog_batch` atomic orchestration | HIGH | HIGH | P2 |
| Full operator docs / ACCEPT_TAB / rollout guidance | MEDIUM | LOW | P2 |
| Search + `build_communities` compatibility verification | HIGH | MEDIUM | P1–P2 |
| Full catalog ingest / K8s deploy / multi-backend | LOW (this milestone) | HIGH | P3 / out of scope |
| Auto communities / caller UUID identity / LLM catalog path | LOW | HIGH | Anti-feature |

**Priority key:**
- P1: Phase 1 — must ship and gate before Phase 2
- P2: Phase 2 — after Phase 1 report
- P3: Deferred / out of scope for this milestone

## Competitor / Baseline Feature Analysis

Not external SaaS competitors — comparison is against **installed Graphiti MCP paths** that are unsafe for this catalog baseline.

| Capability | `add_memory` / episodes | `add_triplet` | Deterministic catalog tools (this milestone) |
|------------|-------------------------|---------------|-----------------------------------------------|
| Sync commit to caller | No (queued) | Yes | Yes |
| LLM extraction | Yes | No (but may still resolve via LLM paths in core) | Never |
| Identity | Episode/entity UUIDs non-catalog-deterministic | Caller or generated UUID; name resolve | UUIDv5 from fixed namespace + graph keys |
| Endpoint creation | Extraction creates entities | Can create generic endpoints if missing | Never for standalone edges; typed only |
| Idempotent catalog retry | Unsafe / non-exact | Weak / UUID overwrite hazards | Required (hash + UUIDv5) |
| Typed catalog ontology | Registry/`excluded_entity_types` fragile | Free-form names | Fixed allowlists + prefixes |
| Provenance | Episode MENTIONS via extraction | Weak | Phase 2 installed-schema provenance links |
| Batch atomicity | No | Single triplet | Phase 2 `upsert_catalog_batch` |
| Suitable for 14k+ dictionary objects | No | No | Yes (with batch limits) |

## Acceptance-Test Implications

| Contract | Test implication |
|----------|------------------|
| Idempotent entity upsert | Insert → re-insert identical payload → same UUID, count unchanged, `created_at` stable, `updated_at` advances on change only as specified |
| Content hash | Mutate payload → hash changes → upsert updates; wrong hash → `content_hash_mismatch` |
| Prefix/type allowlist | Bad prefix/type → `graph_key_prefix_mismatch` / `entity_type_conflict` / `validation_error` |
| Edge without endpoint | `missing_endpoint`; mistyped → `endpoint_type_mismatch`; bare Entity → `generic_endpoint_conflict` |
| Deterministic UUID conflict | Same UUID different identity payload → `deterministic_uuid_conflict` |
| Batch limits | Over limit → `batch_limit_exceeded` without partial write |
| Namespace | Missing/invalid → `invalid_uuid_namespace` / `feature_disabled` |
| Embeddings | Embedder failure → `embedding_failed`, zero domain nodes/edges written |
| Tx failure | Neo4j error → `neo4j_transaction_failed`, full rollback |
| Sync | Tool await completes only after commit/rollback observable in Neo4j |
| Isolation | Writes in `oracle-catalog-tool-test` invisible/unaltered in other group_ids |
| No LLM/queue | Catalog tools do not enqueue `QueueService`; no LLM client calls |
| Search | Upserted typed entities/edges retrievable via `search_nodes` / `search_memory_facts` when embedded |
| Communities | `build_communities` runs without crash on test group; upsert itself does not auto-build |
| Phase 2 batch | Partial invalid item → no domain commit; retry same batch_id idempotent; conflicting batch → `batch_conflict` |
| Provenance | Links only to existing targets; missing → `provenance_target_missing`; no generic domain nodes |
| Status | `CatalogIngestBatch` not returned as Entity search hits |
| Regression | Existing MCP tests still pass; no commits touch unrelated dirty files unless approved |

## Supplied-Requirement Categorization Summary

| Category | Contents |
|----------|----------|
| **Table stakes** | Config, allowlists/validation, four Phase 1 tools, sync/no-LLM/no-queue, UUIDv5+SHA-256, embeddings-before-tx, Neo4j typed writes, `group_id`, structured errors, timestamp/name preservation, Phase 1 gate, test isolation, search compatibility, docs for safe use |
| **Differentiators** | Deterministic catalog identity at scale; idempotent audited upserts; no generic endpoints; Phase 2 provenance + atomic batch + non-Entity ingest status |
| **Anti-features** | LLM catalog path, async catalog writes, caller UUID authority, auto namespace, implicit endpoints, arbitrary Cypher/labels, full ingest, K8s deploy, live-group mutation, graph clear/delete, changing `add_memory`, multi-backend claims, auto communities, MD5, payload logging, invented provenance schema |
| **Phase 1 only** | `upsert_typed_entities`, `upsert_typed_edges`, `resolve_typed_entities`, `verify_catalog_batch` + foundations |
| **Phase 2 only (gated)** | `upsert_provenance`, `upsert_catalog_batch`, `get_catalog_ingest_status` / `CatalogIngestBatch` |
| **Explicit non-goals** | See PROJECT.md Out of Scope — retained verbatim in Anti-Features |

## Sources

- `.planning/PROJECT.md` — validated/active requirements, out of scope, constraints, key decisions, identity/error allowlists, phase gate (HIGH)
- `mcp_server/src/graphiti_mcp_server.py` — existing tools: `add_memory` (queued), `add_triplet` (can create endpoints), search, communities, clear/delete (HIGH)
- `graphiti_core/graphiti.py` `add_triplet` — resolve/create endpoints, embedding generation, edge UUID overwrite hazards (HIGH)
- `graphiti_core/nodes.py` / `edges.py` — Entity/Episodic models, `name_embedding`/`fact_embedding`, `group_id`, MENTIONS provenance edges (HIGH)
- `mcp_server/src/models/*` — current semantic entity/edge types (baseline; catalog types are separate allowlists) (HIGH)
- `mcp_server/sample_catalog.json` + `catalog/*` — structured dictionary shape motivating deterministic tools (MEDIUM for product scope; fixture evidence)
- `.planning/codebase/ARCHITECTURE.md`, `CONCERNS.md` — MCP queue non-durability, Cypher label safety, Neo4j-first driver notes (HIGH)

---
*Feature research for: Deterministic Catalog Ingestion for Graphiti MCP*
*Researched: 2026-07-16*
*Scope discipline: no invented features; every Active/Out-of-Scope PROJECT constraint retained*
