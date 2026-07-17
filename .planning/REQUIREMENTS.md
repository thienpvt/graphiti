# Requirements: Deterministic Catalog Ingestion for Graphiti MCP

**Defined:** 2026-07-17
**Milestone:** v1.1 Catalog-v2 Pre-Canary Hardening
**Core Value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.

## v1.1 Requirements

Requirements for pre-canary hardening. Every requirement maps to exactly one roadmap phase.

### Baseline and Safety

- [ ] **BASE-01**: Maintainer can review a recorded baseline inventory containing all 14 legacy MCP tools, all 7 catalog tools, catalog models/services/store/schema, and the cherry-picked canary builder, runner, fixtures, receipts, checkpoint, and offline tests present before hardening.
- [ ] **BASE-02**: Maintainer can review baseline findings grounded in live source/tests and committed canary evidence rather than this specification alone, including the historical pre-hardening ACCEPT_TAB dry-run/commit record without querying Neo4j.
- [ ] **BASE-03**: Maintainer can distinguish pre-existing targeted catalog, canary-workflow, and compatibility test failures from regressions introduced by v1.1.
- [ ] **BASE-04**: Maintainer can distinguish pre-existing Ruff and Pyright failures from regressions introduced by v1.1; unavailable checks are reported as skipped rather than passed, and the catalog-v1 compatibility/deprecation boundary is recorded before contract changes.
- [ ] **SAFE-01**: New catalog tests and development writes use only `oracle-catalog-tool-test`; the pre-existing `oracle-catalog-v2` ACCEPT_TAB commit is inventoried only from repository artifacts and that group is never queried or mutated during v1.1.
- [ ] **SAFE-02**: No implementation, test, fixture, or documentation workflow executes the real catalog canary.
- [ ] **SAFE-03**: Deterministic catalog workflows never invoke `add_memory`, `add_triplet`, `update_entity`, `delete_entity_edge`, `delete_episode`, `clear_graph`, or `build_communities`.
- [ ] **SAFE-04**: Deterministic catalog workflows never invoke LLM extraction, asynchronous queue ingestion, implicit endpoint creation, or implicit community creation.
- [ ] **SAFE-05**: Caller-supplied UUIDs never control entity, edge, source, evidence-link, batch, manifest, or prepared-plan identity.
- [ ] **SAFE-06**: Identity, type, endpoint, provenance, manifest, uniqueness, and hash conflicts fail closed; no graph data or constraints are silently repaired, merged, deleted, or rewritten.
- [ ] **SAFE-07**: Catalog logs contain only safe identifiers, counts, and structured codes; they never contain payloads, source text, credentials, authorization headers, raw plan tokens, or full exception messages that may contain catalog content.
- [ ] **SAFE-08**: Every new failure returns a documented structured code, bounded non-sensitive message, retryability, field path when applicable, and safe correlation identifier without leaking stack traces or internals.
- [ ] **SAFE-09**: Existing 14 legacy MCP tools retain their names and public contracts; existing seven catalog tool names remain registered while catalog-v2 request contracts may break explicitly as documented.
- [ ] **SAFE-10**: Every catalog read and write remains constrained by `group_id`; catalog writes remain Neo4j 5.26+ only with no unsupported backend-portability claim.
- [ ] **SAFE-11**: Prepare computes required embeddings before persisting the immutable artifact; commit performs no external embedding, LLM, queue, or network call and embedding failure cannot leave a prepared artifact or any domain, provenance, manifest, status, or plan-terminal partial write.
- [ ] **SAFE-12**: Unrelated dirty-worktree files and user changes remain unmodified and excluded from task commits unless separately approved.
- [ ] **SAFE-13**: No task action pushes, merges, deploys, tags, or otherwise modifies remote state.

### Strict Request Contracts and Errors

- [ ] **CONT-01**: Every deterministic catalog request and nested item inherits a common strict Pydantic base using `extra='forbid'` or an equivalent fail-closed configuration.
- [ ] **CONT-02**: Unknown fields are rejected at every nesting depth, including request shells, entities, edges, provenance sources, evidence links, evidence targets, locators, manifests, and prepare/commit models.
- [ ] **CONT-03**: Misspelled optional fields produce field-addressed validation errors instead of being ignored.
- [ ] **CONT-04**: Source strings and other hash-bearing text retain their submitted bytes; validators do not invisibly strip or normalize content before canonical hashing.
- [ ] **CONT-05**: `UpsertTypedEdgesRequest.strict_endpoints` accepts only literal `true`, or is removed through an explicit documented migration; `false` is always rejected.
- [ ] **CONT-06**: `UpsertCatalogBatchRequest.atomic` remains literal `true`; non-atomic combined catalog writes are rejected.
- [ ] **CONT-07**: Complete model, collection, string, hash, prefix, nested-reference, confidence, finite-number, and protected-property validation occurs before side effects.
- [ ] **CONT-08**: The structured error registry includes `unsupported_identity_schema`, `invalid_system_key`, `edge_endpoint_pair_not_allowed`, `prepared_plan_not_found`, `prepared_plan_expired`, `prepared_plan_conflict`, `prepared_plan_already_consumed`, `manifest_mismatch`, and `provenance_link_conflict` without removing existing catalog codes.

### Catalog-v2 Identity

- [ ] **IDEN-01**: Every catalog-v2 domain request declares `identity_schema_version='catalog-v2'`; any other value fails closed with `unsupported_identity_schema`.
- [ ] **IDEN-02**: Catalog domain identity includes a required bounded canonical `system_key` from the closed server-owned set `FE`, `BO`, or `COMMON`.
- [ ] **IDEN-03**: Invalid, empty, overlong, non-canonical, mismatched, or unknown-ownership system keys fail with `invalid_system_key` before database reads, embeddings, schema initialization, transactions, or status writes; unknown ownership never defaults to `COMMON`.
- [ ] **IDEN-04**: Every entity graph key includes its visible system scope and passes a complete server-owned grammar for its exact entity type, not merely a prefix check.
- [ ] **IDEN-05**: The graph-key registry defines complete catalog-v2 grammar for all allowed types, including System, Database, DictionaryDocument, Schema, Table, View, MaterializedView, Column, Constraint, Index, Package, Procedure, Function, Trigger, Sequence, Synonym, DatabaseLink, and SourceArtifact.
- [ ] **IDEN-06**: Procedure and Function identities include a deterministic overload discriminator so package and standalone overloads cannot collapse.
- [ ] **IDEN-07**: FE and BO objects with identical Oracle database, schema, object, and leaf names have different graph keys and server-derived UUIDs while remaining in one `group_id` graph.
- [ ] **IDEN-08**: Catalog entities expose their complete system-scoped graph keys through resolve, manifest, evidence, and verification responses used by agents.
- [ ] **IDEN-09**: `System`, `DatabaseLink`, and `SourceArtifact` are added to the fixed entity allowlist with fixed server-owned prefixes and grammars; no business-level entity types are added.
- [ ] **IDEN-10**: Entity UUIDs derive from an explicitly versioned canonical name equivalent to `group_id|catalog-v2|entity_type|graph_key` under the configured immutable namespace.
- [ ] **IDEN-11**: Edge, provenance source, evidence-link, batch, manifest, and prepared-plan identities use equivalent explicit catalog-v2 versioning and deterministic server derivation.
- [ ] **IDEN-12**: Catalog-v1 graph keys, UUID material, or payloads are never silently accepted, normalized, re-keyed, or rewritten as catalog-v2 objects.
- [ ] **IDEN-13**: The pre-hardening ACCEPT_TAB hash, 10-entity/16-edge/1-source commit receipt, and prior 38/85 plan remain historical evidence but are explicitly invalid for hardened catalog-v2; builders regenerate new artifacts without executing them or rewriting existing graph data.

### Server-Owned Edge Endpoint Map

- [ ] **EDGE-01**: A fixed server-owned endpoint map defines every allowed `(source_entity_type, target_entity_type)` pair for every catalog edge type; clients cannot widen or replace it.
- [ ] **EDGE-02**: The map covers `Contains`, `PrimaryKeyOf`, `UniqueKeyOf`, `ForeignKeyTo`, `EnforcedBy`, `TriggerOn`, `SynonymFor`, `DocumentedBy`, `Calls`, `ReadsFrom`, `WritesTo`, `JoinsWith`, `ReferencesByCode`, `DependsOn`, `DerivedFrom`, and `UsesSequence`.
- [ ] **EDGE-03**: `ForeignKeyTo` represents declared FK semantics with Column-to-Column as the canonical pair; any retained Table-to-Table legacy pair is explicit, separately documented, and separately tested.
- [ ] **EDGE-04**: `Calls` connects only finite executable/code-unit type pairs; `ReadsFrom` and `WritesTo` start only from explicitly allowed code-unit or derived-object types.
- [ ] **EDGE-05**: `TriggerOn` starts at Trigger; `SynonymFor` starts at Synonym; `DocumentedBy` targets DictionaryDocument or SourceArtifact; `UsesSequence` targets Sequence.
- [ ] **EDGE-06**: `JoinsWith` permits only documented Table, View, MaterializedView, and Column pair combinations; `DependsOn`, `ReferencesByCode`, and `DerivedFrom` remain broad only through documented finite maps.
- [ ] **EDGE-07**: `EnforcedBy` accepts only documented endpoint pairs and retains its explicit DDL or Oracle-dictionary evidence requirement.
- [ ] **EDGE-08**: Disallowed endpoint pairs fail with `edge_endpoint_pair_not_allowed` before endpoint database reads when possible and always before embeddings, schema initialization, transactions, or status writes.
- [ ] **EDGE-09**: Standalone edge upsert, combined batch, dry-run, prepare, commit preflight, verification, and edge resolution share one endpoint-map authority and cannot disagree; `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` remain unregistered until later inference/schema approval.

### Authoritative Hash Contract

- [ ] **HASH-01**: Every combined catalog batch requires a valid lowercase 64-hex `catalog_sha256`.
- [ ] **HASH-02**: The server-authoritative request hash includes identity schema version, group ID, batch ID, catalog hash, all canonical entity content, all canonical edge content, all canonical provenance source content, and all canonical evidence-link content.
- [ ] **HASH-03**: The request hash excludes only documented transport or server-execution fields such as `dry_run`, caller-supplied `request_sha256`, generated timestamps, retry counters, and plan tokens.
- [ ] **HASH-04**: Changing `catalog_sha256` or any included canonical domain field changes the server-computed `request_sha256`; collection ordering and canonical JSON rules are deterministic and versioned.
- [ ] **HASH-05**: Every `upsert_catalog_batch` result, including dry-run, returns `identity_schema_version`, server-computed `request_sha256`, `catalog_sha256`, and `batch_uuid`.
- [ ] **HASH-06**: A caller-supplied `request_sha256` is audit-only and must exactly match the server-computed value or fail with `content_hash_mismatch`.
- [ ] **HASH-07**: One documented canonicalization version governs request, item, prepared payload, evidence, and manifest hashing so omitted fields cannot create false idempotence.

### Capabilities and Status

- [ ] **CAPA-01**: The read-only `get_catalog_capabilities` MCP tool works after server initialization even when catalog writes are disabled or identity write prerequisites are incomplete.
- [ ] **CAPA-02**: Capabilities return server/package version, graph backend, and safely determined connectivity state.
- [ ] **CAPA-03**: Capabilities return catalog read/write gate state, UUID namespace configured as a boolean, and a non-reversible namespace fingerprint; the raw namespace is never returned.
- [ ] **CAPA-04**: Capabilities return identity schema version, canonicalization version, and catalog schema version.
- [ ] **CAPA-05**: Capabilities return the entity type/prefix/grammar registry, edge type registry, and complete endpoint type map.
- [ ] **CAPA-06**: Capabilities return configured limits and immutable hard limits for entities, edges, provenance sources, evidence links, prepared payload bytes, active plans, TTL, and pagination.
- [ ] **CAPA-07**: Capabilities return embedding provider configuration/readiness and Neo4j vector/index readiness only when those states can be determined safely without mutation.
- [ ] **CAPA-08**: Capabilities explicitly report prepare/commit, explicit evidence-link, manifest, and manifest-verification support.
- [ ] **CAPA-09**: `get_status` remains backward compatible, preserving its existing `status` and `message` fields even if catalog capability summaries are added.

### Immutable Prepare, Commit, and Discard

- [ ] **PLAN-01**: `prepare_catalog_batch` accepts the complete canonical catalog-v2 domain batch without `dry_run`, plan-token, or caller hash authority.
- [ ] **PLAN-02**: Prepare validates identity/version, graph-key grammar, allowlists, endpoint pairs, limits, duplicates/coalescing, canonical hashes, existing identity conflicts, existing and same-batch endpoints, and provenance targets before persisting a plan.
- [ ] **PLAN-03**: Prepare computes projected created, updated, and unchanged counts plus all required embeddings without mutating Entity, RELATES_TO, Episodic provenance, evidence relationships, manifests, or CatalogIngestBatch status.
- [ ] **PLAN-04**: Prepare persists only bounded non-Entity control-plane state containing the immutable canonical payload, deterministic identities, resolved membership, and required embeddings for token-only, external-call-free commit; hashes and counts alone are insufficient.
- [ ] **PLAN-05**: Prepared payload storage is restart-safe, group-isolated, size-bounded, immutable after creation, and chunked into bounded server-owned control records when required.
- [ ] **PLAN-06**: Prepare returns an opaque one-time-visible `plan_token`, deterministic `plan_uuid`, request and catalog hashes, identity schema version, entity/edge/source/evidence-link counts, projected result counts, and `expires_at`.
- [ ] **PLAN-07**: Raw plan tokens are never logged or stored; only a secure token digest is persisted and compared using a timing-safe mechanism.
- [ ] **PLAN-08**: Configurable TTL, maximum prepared payload bytes, and maximum active prepared plans per group are enforced together with immutable hard ceilings.
- [ ] **PLAN-09**: Prepared-plan and payload-chunk nodes never carry the Entity label, embeddings, or properties that place them in normal search or community clustering.
- [ ] **PLAN-10**: `commit_prepared_catalog_batch` accepts only `plan_token` and optional `expected_request_sha256`; it cannot accept group, batch, entities, edges, sources, evidence links, or replacement payload content.
- [ ] **PLAN-11**: Commit loads and revalidates the immutable prepared payload server-side and rejects missing, expired, changed, discarded, consumed, or conflicting plans with the specific prepared-plan error code.
- [ ] **PLAN-12**: Commit uses only embeddings frozen in the stored prepared artifact and makes no external embedding, LLM, queue, or network call before or during the domain write transaction.
- [ ] **PLAN-13**: A successful commit writes all domain data, exact evidence, durable manifest, terminal batch status, and terminal prepared-plan state in one Neo4j transaction where supported.
- [ ] **PLAN-14**: A commit failure rolls back the complete success transaction; an optional separate post-rollback status transaction may record only bounded failure metadata and never imply domain success; a process restart from `COMMITTING` follows a deterministic documented recovery rule.
- [ ] **PLAN-15**: Identical replay after successful commit returns the committed logical result with unchanged outcomes rather than duplicating data or failing ambiguously.
- [ ] **PLAN-16**: Concurrent commits using the same token yield one logical committed batch and one stable replay/conflict outcome without duplicate domain, evidence, manifest, or status records.
- [ ] **PLAN-17**: A token is cryptographically and persistently bound to one immutable group, batch, identity schema, request hash, and payload; it cannot commit another scope.
- [ ] **PLAN-18**: Expired, discarded, or consumed plans cannot be revived or repurposed.
- [ ] **PLAN-19**: `discard_prepared_catalog_batch` accepts a valid token, idempotently terminates only an unconsumed plan, and never deletes domain graph data, evidence, manifests, or committed batch status.
- [ ] **PLAN-20**: Existing `upsert_catalog_batch` remains available for compatibility and retains zero-write `dry_run=true`; prepare/commit is documented as the preferred agent path.

### Exact Provenance Evidence

- [ ] **EVID-01**: Catalog-v2 provenance uses an explicit `CatalogEvidenceLink` containing `source_key`, exactly one typed entity-or-edge target, evidence kind, bounded locator, optional excerpt, extractor identity/version, optional rule ID, finite confidence, and optional content hash.
- [ ] **EVID-02**: Evidence targets are exclusive and complete: entity targets provide entity type and graph key; edge targets provide edge type and edge key; mixed, empty, or ambiguous targets fail validation.
- [ ] **EVID-03**: Evidence kind is restricted to the documented server allowlist containing `oracle_dictionary`, `ddl`, `view_sql`, `plsql_source`, `comment`, and `manual`.
- [ ] **EVID-04**: Locator, excerpt, extractor, rule, confidence, hash, and nested fields have explicit length, depth, node-count, format, and finite-number bounds.
- [ ] **EVID-05**: Every evidence link receives a server-derived catalog-v2 deterministic UUID and canonical content hash.
- [ ] **EVID-06**: Every source-to-target relationship must be explicitly listed; no request path creates an implicit sources-by-targets Cartesian product.
- [ ] **EVID-07**: Entity and edge evidence targets resolve exactly within `group_id` before writes; missing or mismatched targets fail atomically.
- [ ] **EVID-08**: Duplicate byte-identical evidence links coalesce; reuse of one evidence identity with changed immutable source or target fields fails with `provenance_link_conflict`.
- [ ] **EVID-09**: Existing Graphiti-compatible source Episodic, MENTIONS, and RELATES_TO `episodes` behavior remains available for search interoperability without fabricating links.
- [ ] **EVID-10**: Detailed per-link evidence for both entity and relationship targets is retained in bounded non-Entity control-plane records.
- [ ] **EVID-11**: Evidence/control records never carry Entity labels, enter entity indexes, or participate in community clustering.
- [ ] **EVID-12**: The read-only `get_catalog_evidence` tool returns compact group-isolated evidence for one entity or edge target with bounded pagination and optional excerpts.
- [ ] **EVID-13**: `verify_catalog_batch` can require and compare exact evidence-link identities and counts, not only a boolean provenance-presence flag.
- [ ] **EVID-14**: Catalog-v2 rejects the legacy Cartesian provenance request shape; no automatic conversion of multi-source target arrays is performed.

### Durable Batch Manifest and Verification

- [ ] **MANI-01**: Every committed batch records a durable exact manifest of requested entity, edge, provenance-source, and evidence-link UUIDs plus deterministic compact identities.
- [ ] **MANI-02**: Manifest membership includes objects observed unchanged during the request, including shared entities; it does not depend on an object's current `batch_id` property.
- [ ] **MANI-03**: Existing entity and edge `batch_id` properties remain only as compatibility or last-change metadata and are never the authoritative membership source.
- [ ] **MANI-04**: Manifest data is stored in bounded, group-isolated, non-Entity control-plane records with deterministic catalog-v2 manifest identity and canonical consistency hash.
- [ ] **MANI-05**: `get_catalog_batch_manifest` returns group ID, batch ID, request hash, catalog hash, identity schema version, exact counts, and paginated compact item identities.
- [ ] **MANI-06**: Manifest creation and terminal status/plan updates are part of the same atomic success transaction as domain and evidence writes.
- [ ] **MANI-07**: Identical replay does not duplicate, reorder, or silently rewrite manifest entries.
- [ ] **VERI-01**: Batch-only `verify_catalog_batch` loads the committed manifest as its expected membership authority.
- [ ] **VERI-02**: Batch-only expected counts come from committed manifest/status metadata, never from the number of physical rows returned by a live query.
- [ ] **VERI-03**: Verification reports missing manifest members and extra physical duplicates instead of normalizing them away.
- [ ] **VERI-04**: Verification checks exact entity type, deterministic entity UUID, exact edge type, deterministic edge UUID, endpoint UUIDs and graph keys, required name/fact embeddings, exact provenance/evidence links, and manifest hash/count consistency.
- [ ] **VERI-05**: A committed catalog-v2 batch with no valid manifest fails with `manifest_mismatch`.
- [ ] **VERI-06**: Existing explicit-key verification remains available alongside manifest-backed batch verification.
- [ ] **RESE-01**: `resolve_typed_edges` resolves by edge type and edge key and returns UUID, source/target UUIDs and graph keys, exact type, content hash, and embedding presence.
- [ ] **RESE-02**: Edge resolution reports not-found, physical duplicates, type mismatch, endpoint mismatch, endpoint-pair violation, and deterministic UUID mismatch without repairing data.
- [ ] **RESE-03**: Edge resolution is group-isolated, read-only, performs no embedding, and works while catalog writes are disabled.

### Read and Write Feature Gates

- [ ] **GATE-01**: Catalog read diagnostics and catalog mutations use separate explicit feature gates with safe defaults.
- [ ] **GATE-02**: `get_catalog_capabilities` remains callable whenever the MCP server is initialized, independent of the write gate.
- [ ] **GATE-03**: `get_catalog_ingest_status`, `get_catalog_batch_manifest`, `resolve_typed_entities`, `resolve_typed_edges`, `verify_catalog_batch`, and `get_catalog_evidence` remain usable when writes are disabled, identity configuration is available, and Neo4j is readable.
- [ ] **GATE-04**: Read-only catalog operations do not initialize, alter, or repair schema and never open write transactions.
- [ ] **GATE-05**: Missing batch status is distinguishable through `found=false` or an explicit not-found state/code and never masquerades as a committed or operational failure.
- [ ] **GATE-06**: Every gated read and write retains complete `group_id` isolation.

### Verification, Regression, and Documentation

- [ ] **TEST-01**: Automated unit coverage proves strict unknown-field rejection at every nested level, misspelled optional-field rejection, `strict_endpoints=false` rejection, and `atomic=false` rejection.
- [ ] **TEST-02**: Exhaustive table-driven tests cover every allowed and rejected endpoint pair for all 16 edge types.
- [ ] **TEST-03**: Identity tests prove FE/BO separation, overload separation, graph-key grammar, unsupported-version rejection, and UUID/hash changes when identity schema version changes.
- [ ] **TEST-04**: Hash tests prove `catalog_sha256` changes `request_sha256`, every included domain field is covered, excluded transport fields are stable, and dry-run returns authoritative hashes with zero writes.
- [ ] **TEST-05**: Prepare tests prove no domain/status mutation, immutable persisted payloads, token-only commit, restart safety, TTL/size/cardinality limits, and missing/expired/discarded/consumed/conflicting behavior.
- [ ] **TEST-06**: Concurrency tests prove one logical result for identical concurrent commit, token scope cannot change, expired plans cannot revive, and no duplicate manifest/evidence/domain records appear.
- [ ] **TEST-07**: Evidence tests prove multiple sources link only to explicitly declared targets, no Cartesian provenance occurs, exact link verification works, and conflicting immutable link targets fail closed.
- [ ] **TEST-08**: Manifest and resolver tests prove unchanged shared entities remain members, missing manifest items/count drift are detected, missing manifests fail, and edge twins/endpoint mismatches are reported.
- [ ] **TEST-09**: Gate and registration tests prove read tools work while writes are disabled, all 14 legacy tools remain registered, all expected catalog-v2 tools are registered, and `get_status` remains compatible.
- [ ] **TEST-10**: Security tests prove no LLM, queue, prohibited Graphiti tool, implicit community, client Cypher identifier, payload, source text, credential, authorization header, raw token, or unsafe exception appears in deterministic execution or logs.
- [ ] **TEST-11**: Live Neo4j tests prove atomic rollback, search interoperability, exact evidence/manifest behavior, control labels excluded from normal entity search, and no writes outside `oracle-catalog-tool-test`.
- [ ] **TEST-12**: Targeted unit, service, store, MCP, concurrency, live Neo4j, Ruff, and Pyright checks are run when available; each final result reports pass/fail/skip truthfully without fixing unrelated baseline failures.
- [ ] **DOCS-01**: Operator documentation lists all legacy and catalog tools and identifies prepare/commit as the preferred large-payload agent path.
- [ ] **DOCS-02**: Documentation defines catalog-v2 system-scoped graph-key grammar, FE/BO single-group guidance, overload handling, entity/edge registries, and the complete endpoint type map.
- [ ] **DOCS-03**: Documentation defines canonical hash coverage/exclusions, capability fields, prepare/commit/discard lifecycle, TTL and payload limits, explicit evidence examples, manifest semantics, and read/write gate behavior.
- [ ] **DOCS-04**: Documentation lists every structured error code plus rollout configuration and environment variables without exposing secrets.
- [ ] **DOCS-05**: Migration documentation states catalog-v1 keys and golden hashes are obsolete, automatic in-place identity migration does not exist, canary artifacts must be regenerated under catalog-v2, and the old ACCEPT_TAB SHA-256 must not be reused.
- [ ] **DOCS-06**: The cherry-picked builder, token-aware runner, sanitized fixtures, receipts, checkpoint, and offline tests are migrated to hardened catalog-v2 prepare/commit; generated artifacts are validated offline without executing the real canary or embedding production catalog content into logs/docs.
- [ ] **REPT-01**: The final implementation report follows the requested structured JSON shape, reports baseline/tool/test/change/migration/risk facts, sets `canary_executed=false`, and sets `ready_to_regenerate_canary=true` only after every stated gate passes.

## Future Requirements

Deferred until the deterministic substrate is implemented and verified.

### Oracle Extraction and Analysis

- **PARS-01**: Operator can extract Oracle dictionary catalogs into catalog-v2 requests.
- **PARS-02**: Operator can parse DDL, view SQL, PL/SQL packages, procedures, functions, and triggers into explicit catalog-v2 objects and evidence.
- **INFR-01**: Operator can infer and score undeclared FE/BO relationships from comments, SQL, views, and code usage.
- **RETR-01**: Agent can retrieve compact object context through a dedicated `get_object_context` tool.
- **RETR-02**: Agent can query dependency paths and impact analysis across FE and BO.
- **LIFE-01**: Operator can apply catalog delta, retirement, and reconciliation semantics.
- **DOMN-01**: Operator can model business transactions and FE/BO runtime transaction correlation.
- **OPER-01**: Operator can run an separately approved production migration and catalog canary after v1.1 gates pass.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Oracle dictionary extraction | Parser milestone follows substrate hardening |
| SQL, DDL, or PL/SQL parsing | No parser implementation before contract verification |
| Relationship inference or scoring | Requires trusted explicit substrate first |
| `get_object_context`, dependency paths, impact analysis | Retrieval milestone follows canary validation |
| Catalog delta or retirement | Lifecycle semantics deferred |
| Business transaction entities or runtime correlation | No business-level types in v1.1 |
| Automatic catalog-v1 to catalog-v2 migration | Silent identity reinterpretation is forbidden |
| Production migration or live-group writes | Requires separate operational approval |
| Real canary execution | This milestone prepares artifacts only |
| Graph cleanup or existing-data deletion | No destructive operations |
| FalkorDB, Kuzu, or Neptune catalog portability | Neo4j semantics are the verified target |
| Deployment or Kubernetes rollout | Configuration may be documented; deployment is separate |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BASE-01 | Phase 3 | Pending |
| BASE-02 | Phase 3 | Pending |
| BASE-03 | Phase 3 | Pending |
| BASE-04 | Phase 3 | Pending |
| SAFE-01 | Phase 3 | Pending |
| SAFE-02 | Phase 3 | Pending |
| SAFE-03 | Phase 7 | Pending |
| SAFE-04 | Phase 7 | Pending |
| SAFE-05 | Phase 3 | Pending |
| SAFE-06 | Phase 7 | Pending |
| SAFE-07 | Phase 7 | Pending |
| SAFE-08 | Phase 3 | Pending |
| SAFE-09 | Phase 7 | Pending |
| SAFE-10 | Phase 7 | Pending |
| SAFE-11 | Phase 5 | Pending |
| SAFE-12 | Phase 3 | Pending |
| SAFE-13 | Phase 3 | Pending |
| CONT-01 | Phase 3 | Pending |
| CONT-02 | Phase 3 | Pending |
| CONT-03 | Phase 3 | Pending |
| CONT-04 | Phase 3 | Pending |
| CONT-05 | Phase 3 | Pending |
| CONT-06 | Phase 3 | Pending |
| CONT-07 | Phase 3 | Pending |
| CONT-08 | Phase 3 | Pending |
| IDEN-01 | Phase 3 | Pending |
| IDEN-02 | Phase 3 | Pending |
| IDEN-03 | Phase 3 | Pending |
| IDEN-04 | Phase 3 | Pending |
| IDEN-05 | Phase 3 | Pending |
| IDEN-06 | Phase 3 | Pending |
| IDEN-07 | Phase 3 | Pending |
| IDEN-08 | Phase 3 | Pending |
| IDEN-09 | Phase 3 | Pending |
| IDEN-10 | Phase 3 | Pending |
| IDEN-11 | Phase 3 | Pending |
| IDEN-12 | Phase 3 | Pending |
| IDEN-13 | Phase 3 | Pending |
| EDGE-01 | Phase 4 | Pending |
| EDGE-02 | Phase 4 | Pending |
| EDGE-03 | Phase 4 | Pending |
| EDGE-04 | Phase 4 | Pending |
| EDGE-05 | Phase 4 | Pending |
| EDGE-06 | Phase 4 | Pending |
| EDGE-07 | Phase 4 | Pending |
| EDGE-08 | Phase 4 | Pending |
| EDGE-09 | Phase 4 | Pending |
| HASH-01 | Phase 4 | Pending |
| HASH-02 | Phase 4 | Pending |
| HASH-03 | Phase 4 | Pending |
| HASH-04 | Phase 4 | Pending |
| HASH-05 | Phase 4 | Pending |
| HASH-06 | Phase 4 | Pending |
| HASH-07 | Phase 4 | Pending |
| CAPA-01 | Phase 4 | Pending |
| CAPA-02 | Phase 4 | Pending |
| CAPA-03 | Phase 4 | Pending |
| CAPA-04 | Phase 4 | Pending |
| CAPA-05 | Phase 4 | Pending |
| CAPA-06 | Phase 4 | Pending |
| CAPA-07 | Phase 4 | Pending |
| CAPA-08 | Phase 4 | Pending |
| CAPA-09 | Phase 4 | Pending |
| PLAN-01 | Phase 5 | Pending |
| PLAN-02 | Phase 5 | Pending |
| PLAN-03 | Phase 5 | Pending |
| PLAN-04 | Phase 5 | Pending |
| PLAN-05 | Phase 5 | Pending |
| PLAN-06 | Phase 5 | Pending |
| PLAN-07 | Phase 5 | Pending |
| PLAN-08 | Phase 5 | Pending |
| PLAN-09 | Phase 5 | Pending |
| PLAN-10 | Phase 5 | Pending |
| PLAN-11 | Phase 5 | Pending |
| PLAN-12 | Phase 5 | Pending |
| PLAN-13 | Phase 5 | Pending |
| PLAN-14 | Phase 5 | Pending |
| PLAN-15 | Phase 5 | Pending |
| PLAN-16 | Phase 5 | Pending |
| PLAN-17 | Phase 5 | Pending |
| PLAN-18 | Phase 5 | Pending |
| PLAN-19 | Phase 5 | Pending |
| PLAN-20 | Phase 5 | Pending |
| EVID-01 | Phase 5 | Pending |
| EVID-02 | Phase 5 | Pending |
| EVID-03 | Phase 5 | Pending |
| EVID-04 | Phase 5 | Pending |
| EVID-05 | Phase 5 | Pending |
| EVID-06 | Phase 5 | Pending |
| EVID-07 | Phase 5 | Pending |
| EVID-08 | Phase 5 | Pending |
| EVID-09 | Phase 5 | Pending |
| EVID-10 | Phase 5 | Pending |
| EVID-11 | Phase 5 | Pending |
| EVID-12 | Phase 6 | Pending |
| EVID-13 | Phase 6 | Pending |
| EVID-14 | Phase 5 | Pending |
| MANI-01 | Phase 5 | Pending |
| MANI-02 | Phase 5 | Pending |
| MANI-03 | Phase 5 | Pending |
| MANI-04 | Phase 5 | Pending |
| MANI-05 | Phase 6 | Pending |
| MANI-06 | Phase 5 | Pending |
| MANI-07 | Phase 5 | Pending |
| VERI-01 | Phase 6 | Pending |
| VERI-02 | Phase 6 | Pending |
| VERI-03 | Phase 6 | Pending |
| VERI-04 | Phase 6 | Pending |
| VERI-05 | Phase 6 | Pending |
| VERI-06 | Phase 6 | Pending |
| RESE-01 | Phase 6 | Pending |
| RESE-02 | Phase 6 | Pending |
| RESE-03 | Phase 6 | Pending |
| GATE-01 | Phase 6 | Pending |
| GATE-02 | Phase 6 | Pending |
| GATE-03 | Phase 6 | Pending |
| GATE-04 | Phase 6 | Pending |
| GATE-05 | Phase 6 | Pending |
| GATE-06 | Phase 6 | Pending |
| TEST-01 | Phase 3 | Pending |
| TEST-02 | Phase 4 | Pending |
| TEST-03 | Phase 3 | Pending |
| TEST-04 | Phase 4 | Pending |
| TEST-05 | Phase 5 | Pending |
| TEST-06 | Phase 5 | Pending |
| TEST-07 | Phase 5 | Pending |
| TEST-08 | Phase 6 | Pending |
| TEST-09 | Phase 6 | Pending |
| TEST-10 | Phase 7 | Pending |
| TEST-11 | Phase 7 | Pending |
| TEST-12 | Phase 7 | Pending |
| DOCS-01 | Phase 7 | Pending |
| DOCS-02 | Phase 7 | Pending |
| DOCS-03 | Phase 7 | Pending |
| DOCS-04 | Phase 7 | Pending |
| DOCS-05 | Phase 7 | Pending |
| DOCS-06 | Phase 7 | Pending |
| REPT-01 | Phase 7 | Pending |

**Coverage:**
- v1.1 requirements: 138 total
- Mapped to phases: 138
- Unmapped: 0
- Duplicates: 0

| Phase | Count |
|-------|------:|
| Phase 3 | 33 |
| Phase 4 | 27 |
| Phase 5 | 42 |
| Phase 6 | 20 |
| Phase 7 | 16 |
| **Total** | **138** |

---
*Requirements defined: 2026-07-17*
*Last updated: 2026-07-17 after v1.1 roadmap mapping*
