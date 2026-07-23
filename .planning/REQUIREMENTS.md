# Requirements: Deterministic Catalog Ingestion for Graphiti MCP

**Defined:** 2026-07-17
**Milestone:** v1.1 Catalog-v2 Pre-Canary Hardening
**Core Value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.

## v1.1 Requirements

Requirements for pre-canary hardening plus the separately authorized Phase 6 clean-room closure. Every requirement maps to exactly one roadmap phase.

### Baseline and Safety

- [ ] **BASE-01**: Maintainer can review a recorded baseline inventory containing all 14 legacy MCP tools, all 7 catalog tools, catalog models/services/store/schema, and the cherry-picked canary builder, runner, fixtures, receipts, checkpoint, and offline tests present before hardening.
- [ ] **BASE-02**: Maintainer can review baseline findings grounded in live source/tests and committed canary evidence rather than this specification alone, including the historical pre-hardening ACCEPT_TAB dry-run/commit record without querying Neo4j.
- [ ] **BASE-03**: Maintainer can distinguish pre-existing targeted catalog, canary-workflow, and compatibility test failures from regressions introduced by v1.1.
- [ ] **BASE-04**: Maintainer can distinguish pre-existing Ruff and Pyright failures from regressions introduced by v1.1; unavailable checks are reported as skipped rather than passed, and the catalog-v1 compatibility/deprecation boundary is recorded before contract changes.
- [ ] **SAFE-01**: New catalog tests and development writes use only `oracle-catalog-tool-test`; the pre-existing `oracle-catalog-v2` ACCEPT_TAB commit is inventoried only from repository artifacts and that group is never queried or mutated during v1.1.
- [ ] **SAFE-02**: No implementation, test, fixture, or documentation workflow executes the real catalog canary.
- [x] **SAFE-03**: Deterministic catalog workflows never invoke `add_memory`, `add_triplet`, `update_entity`, `delete_entity_edge`, `delete_episode`, `clear_graph`, or `build_communities`.
- [x] **SAFE-04**: Deterministic catalog workflows never invoke LLM extraction, asynchronous queue ingestion, implicit endpoint creation, or implicit community creation.
- [x] **SAFE-05**: Caller-supplied UUIDs never control entity, edge, source, evidence-link, batch, manifest, or prepared-plan identity.
- [x] **SAFE-06**: Identity, type, endpoint, provenance, manifest, uniqueness, and hash conflicts fail closed; no graph data or constraints are silently repaired, merged, deleted, or rewritten.
- [x] **SAFE-07**: Catalog logs contain only safe identifiers, counts, and structured codes; they never contain payloads, source text, credentials, authorization headers, raw plan tokens, or full exception messages that may contain catalog content.
- [x] **SAFE-08**: Every new failure returns a documented structured code, bounded non-sensitive message, retryability, field path when applicable, and safe correlation identifier without leaking stack traces or internals.
- [x] **SAFE-09**: Existing 14 legacy MCP tools retain their names and public contracts; existing seven catalog tool names remain registered while catalog-v2 request contracts may break explicitly as documented.
- [x] **SAFE-10**: Every catalog read and write remains constrained by `group_id`; catalog writes remain Neo4j 5.26+ only with no unsupported backend-portability claim.
- [x] **SAFE-11**: Prepare computes required embeddings before persisting the immutable artifact; commit performs no external embedding, LLM, queue, or network call and embedding failure cannot leave a prepared artifact or any domain, provenance, manifest, status, or plan-terminal partial write.
- [ ] **SAFE-12**: Unrelated dirty-worktree files and user changes remain unmodified and excluded from task commits unless separately approved.
- [ ] **SAFE-13**: No task action pushes, merges, deploys, tags, or otherwise modifies remote state.

### Strict Request Contracts and Errors

- [x] **CONT-01**: Every deterministic catalog request and nested item inherits a common strict Pydantic base using `extra='forbid'` or an equivalent fail-closed configuration.
- [x] **CONT-02**: Unknown fields are rejected at every nesting depth, including request shells, entities, edges, provenance sources, evidence links, evidence targets, locators, manifests, and prepare/commit models.
- [x] **CONT-03**: Misspelled optional fields produce field-addressed validation errors instead of being ignored.
- [x] **CONT-04**: Source strings and other hash-bearing text retain their submitted bytes; validators do not invisibly strip or normalize content before canonical hashing.
- [x] **CONT-05**: `UpsertTypedEdgesRequest.strict_endpoints` accepts only literal `true`, or is removed through an explicit documented migration; `false` is always rejected.
- [x] **CONT-06**: `UpsertCatalogBatchRequest.atomic` remains literal `true`; non-atomic combined catalog writes are rejected.
- [x] **CONT-07**: Complete model, collection, string, hash, prefix, nested-reference, confidence, finite-number, and protected-property validation occurs before side effects.
- [x] **CONT-08**: The structured error registry includes `unsupported_identity_schema`, `invalid_system_key`, `edge_endpoint_pair_not_allowed`, `prepared_plan_not_found`, `prepared_plan_expired`, `prepared_plan_conflict`, `prepared_plan_already_consumed`, `manifest_mismatch`, and `provenance_link_conflict` without removing existing catalog codes.

### Catalog-v2 Identity

- [x] **IDEN-01**: Every catalog-v2 domain request declares `identity_schema_version='catalog-v2'`; any other value fails closed with `unsupported_identity_schema`.
- [x] **IDEN-02**: Catalog domain identity includes a required bounded canonical `system_key` from the closed server-owned set `FE`, `BO`, or `COMMON`.
- [x] **IDEN-03**: Invalid, empty, overlong, non-canonical, mismatched, or unknown-ownership system keys fail with `invalid_system_key` before database reads, embeddings, schema initialization, transactions, or status writes; unknown ownership never defaults to `COMMON`.
- [x] **IDEN-04**: Every entity graph key includes its visible system scope and passes a complete server-owned grammar for its exact entity type, not merely a prefix check.
- [x] **IDEN-05**: The graph-key registry defines complete catalog-v2 grammar for all allowed types, including System, Database, DictionaryDocument, Schema, Table, View, MaterializedView, Column, Constraint, Index, Package, Procedure, Function, Trigger, Sequence, Synonym, DatabaseLink, and SourceArtifact.
- [x] **IDEN-06**: Procedure and Function identities include a deterministic overload discriminator so package and standalone overloads cannot collapse.
- [x] **IDEN-07**: FE and BO objects with identical Oracle database, schema, object, and leaf names have different graph keys and server-derived UUIDs while remaining in one `group_id` graph.
- [x] **IDEN-08**: Catalog entities expose their complete system-scoped graph keys through resolve, manifest, evidence, and verification responses used by agents. Phase 1 model/service echo tests are partial foundation evidence only; Phase 4 uniquely owns completion across all response surfaces.
- [x] **IDEN-09**: `System`, `DatabaseLink`, and `SourceArtifact` are added to the fixed entity allowlist with fixed server-owned prefixes and grammars; no business-level entity types are added.
- [x] **IDEN-10**: Entity UUIDs derive from an explicitly versioned canonical name equivalent to `group_id|catalog-v2|entity_type|graph_key` under the configured immutable namespace.
- [x] **IDEN-11**: Edge, provenance source, evidence-link, batch, manifest, and prepared-plan identities use equivalent explicit catalog-v2 versioning and deterministic server derivation.
- [x] **IDEN-12**: Catalog-v1 graph keys, UUID material, or payloads are never silently accepted, normalized, re-keyed, or rewritten as catalog-v2 objects.
- [x] **IDEN-13**: The pre-hardening ACCEPT_TAB hash, 10-entity/16-edge/1-source commit receipt, and prior 38/85 plan remain historical evidence but are explicitly invalid for hardened catalog-v2; builders regenerate new artifacts without executing them or rewriting existing graph data. Phase 1 v1-material inequality and historical-golden guards are partial foundation evidence only; Phase 5 uniquely owns hardened offline regeneration and migration guidance.

### Server-Owned Edge Endpoint Map

- [x] **EDGE-01**: A fixed server-owned endpoint map defines every allowed `(source_entity_type, target_entity_type)` pair for every catalog edge type; clients cannot widen or replace it.
- [x] **EDGE-02**: The map covers `Contains`, `PrimaryKeyOf`, `UniqueKeyOf`, `ForeignKeyTo`, `EnforcedBy`, `TriggerOn`, `SynonymFor`, `DocumentedBy`, `Calls`, `ReadsFrom`, `WritesTo`, `JoinsWith`, `ReferencesByCode`, `DependsOn`, `DerivedFrom`, and `UsesSequence`.
- [x] **EDGE-03**: `ForeignKeyTo` represents declared FK semantics with Column-to-Column as the canonical pair; any retained Table-to-Table legacy pair is explicit, separately documented, and separately tested.
- [x] **EDGE-04**: `Calls` connects only finite executable/code-unit type pairs; `ReadsFrom` and `WritesTo` start only from explicitly allowed code-unit or derived-object types.
- [x] **EDGE-05**: `TriggerOn` starts at Trigger; `SynonymFor` starts at Synonym; `DocumentedBy` targets DictionaryDocument or SourceArtifact; `UsesSequence` targets Sequence.
- [x] **EDGE-06**: `JoinsWith` permits only documented Table, View, MaterializedView, and Column pair combinations; `DependsOn`, `ReferencesByCode`, and `DerivedFrom` remain broad only through documented finite maps.
- [x] **EDGE-07**: `EnforcedBy` accepts only documented endpoint pairs and retains its explicit DDL or Oracle-dictionary evidence requirement.
- [x] **EDGE-08**: Disallowed endpoint pairs fail with `edge_endpoint_pair_not_allowed` before endpoint database reads when possible and always before embeddings, schema initialization, transactions, or status writes.
- [x] **EDGE-09**: Standalone edge upsert, combined batch, dry-run, prepare, commit preflight, verification, and edge resolution share one endpoint-map authority and cannot disagree; `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` remain unregistered until later inference/schema approval.

### Authoritative Hash Contract

- [x] **HASH-01**: Every combined catalog batch requires a valid lowercase 64-hex `catalog_sha256`.
- [x] **HASH-02**: The server-authoritative request hash includes identity schema version, group ID, batch ID, catalog hash, all canonical entity content, all canonical edge content, all canonical provenance source content, and all canonical evidence-link content.
- [x] **HASH-03**: The request hash excludes only documented transport or server-execution fields such as `dry_run`, caller-supplied `request_sha256`, generated timestamps, retry counters, and plan tokens.
- [x] **HASH-04**: Changing `catalog_sha256` or any included canonical domain field changes the server-computed `request_sha256`; collection ordering and canonical JSON rules are deterministic and versioned.
- [x] **HASH-05**: Every `upsert_catalog_batch` result, including dry-run, returns `identity_schema_version`, server-computed `request_sha256`, `catalog_sha256`, and `batch_uuid`.
- [x] **HASH-06**: A caller-supplied `request_sha256` is audit-only and must exactly match the server-computed value or fail with `content_hash_mismatch`.
- [x] **HASH-07**: One documented canonicalization version governs request, item, prepared payload, evidence, and manifest hashing so omitted fields cannot create false idempotence.

### Capabilities and Status

- [x] **CAPA-01**: The read-only `get_catalog_capabilities` MCP tool works after server initialization even when catalog writes are disabled or identity write prerequisites are incomplete.
- [x] **CAPA-02**: Capabilities return server/package version, graph backend, and safely determined connectivity state.
- [x] **CAPA-03**: Capabilities return catalog read/write gate state, UUID namespace configured as a boolean, and a non-reversible namespace fingerprint; the raw namespace is never returned.
- [x] **CAPA-04**: Capabilities return identity schema version, canonicalization version, and catalog schema version.
- [x] **CAPA-05**: Capabilities return the entity type/prefix/grammar registry, edge type registry, and complete endpoint type map.
- [x] **CAPA-06**: Capabilities return configured limits and immutable hard limits for entities, edges, provenance sources, evidence links, prepared payload bytes, active plans, TTL, and pagination.
- [x] **CAPA-07**: Capabilities return embedding provider configuration/readiness and Neo4j vector/index readiness only when those states can be determined safely without mutation.
- [x] **CAPA-08**: Capabilities explicitly report prepare/commit, explicit evidence-link, manifest, and manifest-verification support.
- [x] **CAPA-09**: `get_status` remains backward compatible, preserving its existing `status` and `message` fields even if catalog capability summaries are added.

### Immutable Prepare, Commit, and Discard

- [x] **PLAN-01**: `prepare_catalog_batch` accepts the complete canonical catalog-v2 domain batch without `dry_run`, plan-token, or caller hash authority.
- [x] **PLAN-02**: Prepare validates identity/version, graph-key grammar, allowlists, endpoint pairs, limits, duplicates/coalescing, canonical hashes, existing identity conflicts, existing and same-batch endpoints, and provenance targets before persisting a plan.
- [x] **PLAN-03**: Prepare computes projected created, updated, and unchanged counts plus all required embeddings without mutating Entity, RELATES_TO, Episodic provenance, evidence relationships, manifests, or CatalogIngestBatch status.
- [x] **PLAN-04**: Prepare persists only bounded non-Entity control-plane state containing the immutable canonical payload, deterministic identities, resolved membership, and required embeddings for token-only, external-call-free commit; hashes and counts alone are insufficient.
- [x] **PLAN-05**: Prepared payload storage is restart-safe, group-isolated, size-bounded, immutable after creation, and chunked into bounded server-owned control records when required.
- [x] **PLAN-06**: Prepare returns an opaque one-time-visible `plan_token`, deterministic `plan_uuid`, request and catalog hashes, identity schema version, entity/edge/source/evidence-link counts, projected result counts, and `expires_at`.
- [x] **PLAN-07**: Raw plan tokens are never logged or stored; only a secure token digest is persisted and compared using a timing-safe mechanism.
- [x] **PLAN-08**: Configurable TTL, maximum prepared payload bytes, and maximum active prepared plans per group are enforced together with immutable hard ceilings.
- [x] **PLAN-09**: Prepared-plan and payload-chunk nodes never carry the Entity label, embeddings, or properties that place them in normal search or community clustering.
- [x] **PLAN-10**: `commit_prepared_catalog_batch` accepts only `plan_token` and optional `expected_request_sha256`; it cannot accept group, batch, entities, edges, sources, evidence links, or replacement payload content.
- [x] **PLAN-11**: Commit loads and revalidates the immutable prepared payload server-side and rejects missing, expired, changed, discarded, consumed, or conflicting plans with the specific prepared-plan error code.
- [x] **PLAN-12**: Commit uses only embeddings frozen in the stored prepared artifact and makes no external embedding, LLM, queue, or network call before or during the domain write transaction.
- [x] **PLAN-13**: A successful commit writes all domain data, exact evidence, durable manifest, terminal batch status, and terminal prepared-plan state in one Neo4j transaction where supported.
- [x] **PLAN-14**: A commit failure rolls back the complete success transaction; an optional separate post-rollback status transaction may record only bounded failure metadata and never imply domain success; a process restart from `COMMITTING` follows a deterministic documented recovery rule.
- [x] **PLAN-15**: Identical replay after successful commit returns the committed logical result with unchanged outcomes rather than duplicating data or failing ambiguously.
- [x] **PLAN-16**: Concurrent commits using the same token yield one logical committed batch and one stable replay/conflict outcome without duplicate domain, evidence, manifest, or status records.
- [x] **PLAN-17**: A token is cryptographically and persistently bound to one immutable group, batch, identity schema, request hash, and payload; it cannot commit another scope.
- [x] **PLAN-18**: Expired, discarded, or consumed plans cannot be revived or repurposed.
- [x] **PLAN-19**: `discard_prepared_catalog_batch` accepts a valid token, idempotently terminates only an unconsumed plan, and never deletes domain graph data, evidence, manifests, or committed batch status.
- [x] **PLAN-20**: Existing `upsert_catalog_batch` remains available for compatibility and retains zero-write `dry_run=true`; prepare/commit is documented as the preferred agent path.

### Exact Provenance Evidence

- [x] **EVID-01**: Catalog-v2 provenance uses an explicit `CatalogEvidenceLink` containing `source_key`, exactly one typed entity-or-edge target, evidence kind, bounded locator, optional excerpt, extractor identity/version, optional rule ID, finite confidence, and optional content hash.
- [x] **EVID-02**: Evidence targets are exclusive and complete: entity targets provide entity type and graph key; edge targets provide edge type and edge key; mixed, empty, or ambiguous targets fail validation.
- [x] **EVID-03**: Evidence kind is restricted to the documented server allowlist containing `oracle_dictionary`, `ddl`, `view_sql`, `plsql_source`, `comment`, and `manual`.
- [x] **EVID-04**: Locator, excerpt, extractor, rule, confidence, hash, and nested fields have explicit length, depth, node-count, format, and finite-number bounds.
- [x] **EVID-05**: Every evidence link receives a server-derived catalog-v2 deterministic UUID and canonical content hash.
- [x] **EVID-06**: Every source-to-target relationship must be explicitly listed; no request path creates an implicit sources-by-targets Cartesian product.
- [x] **EVID-07**: Entity and edge evidence targets resolve exactly within `group_id` before writes; missing or mismatched targets fail atomically.
- [x] **EVID-08**: Duplicate byte-identical evidence links coalesce; reuse of one evidence identity with changed immutable source or target fields fails with `provenance_link_conflict`.
- [x] **EVID-09**: Existing Graphiti-compatible source Episodic, MENTIONS, and RELATES_TO `episodes` behavior remains available for search interoperability without fabricating links.
- [x] **EVID-10**: Detailed per-link evidence for both entity and relationship targets is retained in bounded non-Entity control-plane records.
- [x] **EVID-11**: Evidence/control records never carry Entity labels, enter entity indexes, or participate in community clustering.
- [x] **EVID-12**: The read-only `get_catalog_evidence` tool returns compact group-isolated evidence for one entity or edge target with bounded pagination and optional excerpts.
- [x] **EVID-13**: `verify_catalog_batch` can require and compare exact evidence-link identities and counts, not only a boolean provenance-presence flag.
- [x] **EVID-14**: Catalog-v2 rejects the legacy Cartesian provenance request shape; no automatic conversion of multi-source target arrays is performed.

### Durable Batch Manifest and Verification

- [x] **MANI-01**: Every committed batch records a durable exact manifest of requested entity, edge, provenance-source, and evidence-link UUIDs plus deterministic compact identities.
- [x] **MANI-02**: Manifest membership includes objects observed unchanged during the request, including shared entities; it does not depend on an object's current `batch_id` property.
- [x] **MANI-03**: Existing entity and edge `batch_id` properties remain only as compatibility or last-change metadata and are never the authoritative membership source.
- [x] **MANI-04**: Manifest data is stored in bounded, group-isolated, non-Entity control-plane records with deterministic catalog-v2 manifest identity and canonical consistency hash.
- [x] **MANI-05**: `get_catalog_batch_manifest` returns group ID, batch ID, request hash, catalog hash, identity schema version, exact counts, and paginated compact item identities.
- [x] **MANI-06**: Manifest creation and terminal status/plan updates are part of the same atomic success transaction as domain and evidence writes.
- [x] **MANI-07**: Identical replay does not duplicate, reorder, or silently rewrite manifest entries.
- [x] **VERI-01**: Batch-only `verify_catalog_batch` loads the committed manifest as its expected membership authority.
- [x] **VERI-02**: Batch-only expected counts come from committed manifest/status metadata, never from the number of physical rows returned by a live query.
- [x] **VERI-03**: Verification reports missing manifest members and extra physical duplicates instead of normalizing them away.
- [x] **VERI-04**: Verification checks exact entity type, deterministic entity UUID, exact edge type, deterministic edge UUID, endpoint UUIDs and graph keys, required name/fact embeddings, exact provenance/evidence links, and manifest hash/count consistency.
- [x] **VERI-05**: A committed catalog-v2 batch with no valid manifest fails with `manifest_mismatch`.
- [x] **VERI-06**: Existing explicit-key verification remains available alongside manifest-backed batch verification.
- [x] **RESE-01**: `resolve_typed_edges` resolves by edge type and edge key and returns UUID, source/target UUIDs and graph keys, exact type, content hash, and embedding presence.
- [x] **RESE-02**: Edge resolution reports not-found, physical duplicates, type mismatch, endpoint mismatch, endpoint-pair violation, and deterministic UUID mismatch without repairing data.
- [x] **RESE-03**: Edge resolution is group-isolated, read-only, performs no embedding, and works while catalog writes are disabled.

### Read and Write Feature Gates

- [x] **GATE-01**: Catalog read diagnostics and catalog mutations use separate explicit feature gates with safe defaults.
- [x] **GATE-02**: `get_catalog_capabilities` remains callable whenever the MCP server is initialized, independent of the write gate.
- [x] **GATE-03**: `get_catalog_ingest_status`, `get_catalog_batch_manifest`, `resolve_typed_entities`, `resolve_typed_edges`, `verify_catalog_batch`, and `get_catalog_evidence` remain usable when writes are disabled, identity configuration is available, and Neo4j is readable.
- [x] **GATE-04**: Read-only catalog operations do not initialize, alter, or repair schema and never open write transactions.
- [x] **GATE-05**: Missing batch status is distinguishable through `found=false` or an explicit not-found state/code and never masquerades as a committed or operational failure.
- [x] **GATE-06**: Every gated read and write retains complete `group_id` isolation.

### Verification, Regression, and Documentation

- [x] **TEST-01**: Automated unit coverage proves strict unknown-field rejection at every nested level, misspelled optional-field rejection, `strict_endpoints=false` rejection, and `atomic=false` rejection.
- [x] **TEST-02**: Exhaustive table-driven tests cover every allowed and rejected endpoint pair for all 16 edge types.
- [x] **TEST-03**: Identity tests prove FE/BO separation, overload separation, graph-key grammar, unsupported-version rejection, and UUID/hash changes when identity schema version changes.
- [x] **TEST-04**: Hash tests prove `catalog_sha256` changes `request_sha256`, every included domain field is covered, excluded transport fields are stable, and dry-run returns authoritative hashes with zero writes.
- [x] **TEST-05**: Prepare tests prove no domain/status mutation, immutable persisted payloads, token-only commit, restart safety, TTL/size/cardinality limits, and missing/expired/discarded/consumed/conflicting behavior.
- [x] **TEST-06**: Concurrency tests prove one logical result for identical concurrent commit, token scope cannot change, expired plans cannot revive, and no duplicate manifest/evidence/domain records appear.
- [x] **TEST-07**: Evidence tests prove multiple sources link only to explicitly declared targets, no Cartesian provenance occurs, exact link verification works, and conflicting immutable link targets fail closed.
- [x] **TEST-08**: Manifest and resolver tests prove unchanged shared entities remain members, missing manifest items/count drift are detected, missing manifests fail, and edge twins/endpoint mismatches are reported.
- [x] **TEST-09**: Gate and registration tests prove read tools work while writes are disabled, all 14 legacy tools remain registered, all expected catalog-v2 tools are registered, and `get_status` remains compatible.
- [x] **TEST-10**: Security tests prove no LLM, queue, prohibited Graphiti tool, implicit community, client Cypher identifier, payload, source text, credential, authorization header, raw token, or unsafe exception appears in deterministic execution or logs.
- [x] **TEST-11**: Live Neo4j tests prove atomic rollback, search interoperability, exact evidence/manifest behavior, control labels excluded from normal entity search, and no writes outside `oracle-catalog-tool-test`.
- [x] **TEST-12**: Targeted unit, service, store, MCP, concurrency, live Neo4j, Ruff, and Pyright checks are run when available; each final result reports pass/fail/skip truthfully without fixing unrelated baseline failures.
- [x] **DOCS-01**: Operator documentation lists all legacy and catalog tools and identifies prepare/commit as the preferred large-payload agent path.
- [x] **DOCS-02**: Documentation defines catalog-v2 system-scoped graph-key grammar, FE/BO single-group guidance, overload handling, entity/edge registries, and the complete endpoint type map.
- [x] **DOCS-03**: Documentation defines canonical hash coverage/exclusions, capability fields, prepare/commit/discard lifecycle, TTL and payload limits, explicit evidence examples, manifest semantics, and read/write gate behavior.
- [x] **DOCS-04**: Documentation lists every structured error code plus rollout configuration and environment variables without exposing secrets.
- [x] **DOCS-05**: Migration documentation states catalog-v1 keys and golden hashes are obsolete, automatic in-place identity migration does not exist, canary artifacts must be regenerated under catalog-v2, and the old ACCEPT_TAB SHA-256 must not be reused.
- [x] **DOCS-06**: The cherry-picked builder, token-aware runner, sanitized fixtures, receipts, checkpoint, and offline tests are migrated to hardened catalog-v2 prepare/commit; generated artifacts are validated offline without executing the real canary or embedding production catalog content into logs/docs.
- [x] **REPT-01**: The final implementation report follows the requested structured JSON shape, reports baseline/tool/test/change/migration/risk facts, sets `canary_executed=false`, and sets `ready_to_regenerate_canary=true` only after every stated gate passes.

## Phase 6 Requirements

Phase 6 is authorized by fetched fork commit `e52c1b5` under `ITERATIVE_TDD_IMPLEMENTATION_AND_ONE_FINAL_CLEANROOM_CANARY`. These requirements derive from `spec/new-phase.md`; stale Phase 0–5 canary prohibitions remain historical truth for those phases but do not override this explicitly authorized clean-room operation.

### Authority and Baseline

- [x] **P6-AUTH-01**: Execution follows the fetched Phase 6 authorization and acceptance contract without widening it to deployment, production migration, historical groups, or a second canary.
- [x] **P6-BASE-01**: Source authority starts from commit `35227e0a2c697e643871b5c2052556988c404df6`, tree `fed171af3c49dc96701da26b53fd391511a00735`, and source-context SHA-256 `dcf73073443be37b777fc7feef124133be3d9ee305696e84042d5631125ed92f`.
- [ ] **P6-BASE-02**: The previously approved image and image ID remain historical evidence only and are never retagged as the final source-bound image.
- [x] **P6-BASE-03**: The original forced-project, Neo4j-staging, and hardcoded-image blockers are verified closed by current committed source before runtime activation.

### Preservation and Provider Policy

- [x] **P6-PRES-01**: User-owned `mcp_server/config/config-docker-neo4j.yaml` remains untouched, unstaged, uncommitted, and excluded from image context/evidence.
- [x] **P6-PRES-02**: No reset, checkout, restore, stash, broad replacement, push, merge, rebase, amend, or tag occurs; task commits contain task-owned paths only.
- [ ] **P6-PRES-03**: Historical Docker containers, networks, volumes, canary data, and evidence remain unchanged.
- [ ] **P6-PROV-01**: Phase 6 invokes no generative LLM operation, public OpenAI endpoint/probe, credential mutation, or provider substitution.
- [ ] **P6-PROV-02**: Provider-dependent work is limited to prepare/search embeddings; successful `prepare_catalog_batch` is the first functional embedding proof.
- [ ] **P6-PROV-03**: Actual embedding authentication failures classify exactly as `FAILED_BEFORE_COMMIT` or `FAILED_AFTER_COMMIT` with cause `embedding_transport_auth`, without bypass or retry.

### Harness Acceptance

- [ ] **P6-HARN-01**: Clean-room Compose project names are explicit and validated; empty, path-like, whitespace, shell-fragment, and option-injection values fail closed.
- [ ] **P6-HARN-02**: Omitted project authority preserves the legacy default `graphiti-catalog-local`.
- [ ] **P6-HARN-03**: The launcher provides one canonical effective-Compose render action.
- [ ] **P6-HARN-04**: The launcher starts Neo4j only when requested.
- [ ] **P6-HARN-05**: The launcher invokes one canonical application-owned Catalog-v2 schema bootstrap from exact 0/14 to exact 14/14 with no retry, repair, drop, alternate Cypher, or Graphiti driver construction.
- [ ] **P6-HARN-06**: The launcher starts graphiti-mcp only without recreating Neo4j or dependencies.
- [ ] **P6-HARN-07**: Compose accepts explicit `GRAPHITI_MCP_IMAGE` selection while preserving the legacy image default.
- [ ] **P6-HARN-08**: Post-start inspection requires the exact expected running MCP image ID and rejects absent, ambiguous, or mismatched containers.
- [ ] **P6-HARN-09**: Neo4j data and log volumes are project-scoped and disjoint across projects.
- [ ] **P6-HARN-10**: Clean-room project containers, network, data volume, and log volume are proven absent before creation.
- [ ] **P6-HARN-11**: The canonical materializer creates exactly one cryptographically random UUIDv4 namespace per clean-room data-volume authority using exclusive creation and no silent regeneration.
- [ ] **P6-HARN-12**: Namespace fingerprint authority binds to exact project and data-volume identity.
- [ ] **P6-HARN-13**: Raw namespace bytes never appear in output, exceptions, argv, evidence, Git, image layers, or reports.
- [ ] **P6-HARN-14**: Compose operations are fixed and allow-listed, use structured subprocess argv, and reject arbitrary services/actions/files/profiles/fragments, shell execution, build, pull, prune, and historical mutation.
- [ ] **P6-HARN-15**: Launcher and MCP ledgers are contiguous, complete, bounded, and sanitized.
- [ ] **P6-HARN-16**: The exact existing 22-field live-manifest contract remains unchanged.
- [ ] **P6-HARN-17**: The exact existing 28-tool MCP registry remains unchanged.
- [ ] **P6-HARN-18**: Phase 5, Phase 6, combined remediation, golden contract/hash, Ruff, format, Pyright, and relevant union regressions remain compatible.
- [x] **P6-HARN-19**: No Catalog-v2 identity, evidence, manifest, request, or MCP tool contract changes are used to solve orchestration.

### TDD and Exact Source Binding

- [x] **P6-TDD-01**: Missing behavior begins with intentional RED acceptance tests mapped to requirements, not fixture/import/infrastructure failures.
- [x] **P6-TDD-02**: Production changes are the minimum required for GREEN behavior.
- [x] **P6-TDD-03**: Every defect follows focused RED/GREEN, adjacent regression, and refactor-with-green iteration without weakening, skipping, deselecting, or broadly mocking tests.
- [x] **P6-TDD-04**: The complete frozen verification matrix passes with no unexplained failures, skips, deselections, warnings, or stale evidence before source binding.
- [x] **P6-BIND-01**: Only task-owned source/tests/docs are staged into local candidate commits.
- [x] **P6-BIND-02**: A raw-Git LF-exact archive is materialized without checkout, export, or EOL transformation.
- [x] **P6-BIND-03**: Archive membership, paths, modes, symlinks, duplicates, collisions, and every blob hash exactly match the candidate Git tree.
- [x] **P6-BIND-04**: The canonical source-context SHA-256 is computed from exact Git authority and matches the archive authority.
- [x] **P6-BIND-05**: The complete frozen matrix passes from the exact candidate archive.
- [x] **P6-BIND-06**: A failed candidate is preserved as evidence and corrected only through a new fix-forward commit; no amend or evidence rewrite.

### Source-Bound Image

- [ ] **P6-IMG-01**: The final runtime image is built only from the exact passing Git archive.
- [ ] **P6-IMG-02**: The image uses a commit-derived `graphiti-mcp:phase6-cleanroom-<short-commit>-bound` tag and is never pushed or retagged.
- [ ] **P6-IMG-03**: The production Dockerfile builds with no pull; OCI revision equals the final commit and OCI source-context label equals the canonical context hash.
- [ ] **P6-IMG-04**: Image context/layers contain no namespace, local Catalog-v2 config, `.env`, proxy token, credential, runtime evidence, or secret-pattern hit.
- [ ] **P6-IMG-05**: Sanitized evidence records image tag/ID plus Dockerfile, build-log, inspect, archive, and context hashes.

### Clean-Room Runtime

- [ ] **P6-RT-00**: Runtime activation occurs only after focused tests, full regressions, exact archive verification, archive matrix, and image binding pass.
- [ ] **P6-RT-R0**: One unique Compose authority proves all expected resources absent and renders only the selected source-bound image, new project resources, no build, and pull-never behavior.
- [ ] **P6-RT-R1**: Exactly one namespace is materialized; only Neo4j starts; this operation creates the exact data/log volumes; Neo4j is healthy; MCP remains absent.
- [ ] **P6-RT-R2**: Exactly one application-owned pre-inspection observes 0/14, one bootstrap runs, and one first post-inspection observes 14/14; failure stops without retry or repair.
- [ ] **P6-RT-R3**: MCP starts alone using the exact image ID and passes only the 28-tool registry, `get_status`, and zero-argument `get_catalog_capabilities` readiness calls with matching namespace/schema/provider truth and supported OpenAI unknown-readiness waiver.
- [ ] **P6-RT-DISP**: A pre-canary runtime candidate is removed only after separate confirmation and proof it is operation-owned, pre-identity, pre-prepare, data-empty, non-external, non-shared, and exactly targeted; otherwise it is preserved.

### One Final Canary

- [ ] **P6-CAN-01**: Allocation of any canary run, canary group, control group, or batch ID irreversibly freezes source, commits, image, and runtime authority.
- [ ] **P6-CAN-02**: Exactly one final canary runs from committed `graphiti_mcp_phase6_canary_agent_prompt_en.md` using entirely new identities and never historical groups.
- [ ] **P6-CAN-03**: Exactly one dry run reports 3 entities, 2 edges, 1 source artifact, and 5 evidence links with zero persistent writes.
- [ ] **P6-CAN-04**: Exactly one prepare succeeds as embedding proof and exactly one token-only commit occurs with no commit retry and no persisted raw token.
- [ ] **P6-CAN-05**: Manifest, entities, edges, batch, five evidence targets, three entity searches, two `attributes.edge_key` fact searches, empty control group, controlled replay, and contiguous sanitized ledger all reconcile.
- [ ] **P6-CAN-06**: Ambiguous commit transport triggers bounded committed read-only reconciliation only and never a second commit.

### Safety, Terminal State, and Report

- [ ] **P6-SAFE-01**: No global/system/container/volume prune, arbitrary removal, historical `down -v`, historical mount, graph clear/delete, or Kubernetes action occurs.
- [ ] **P6-SAFE-02**: The final clean-room stack and volumes remain intact after canary success or failure.
- [ ] **P6-TERM-01**: Successful completion terminates as `PASSED`.
- [ ] **P6-TERM-02**: Pre-canary hard stops use only `HARD_BLOCKED_BASELINE_AUTHORITY`, `HARD_BLOCKED_TOOLCHAIN`, `HARD_BLOCKED_REQUIREMENT_CONFLICT`, or `HARD_BLOCKED_LOCAL_RUNTIME_AUTHORITY`.
- [ ] **P6-TERM-03**: After identity allocation, terminal classification is only `FAILED_BEFORE_COMMIT`, `FAILED_AFTER_COMMIT`, or `PASSED` as applicable to committed canary state.
- [ ] **P6-TERM-04**: Missing public `OPENAI_API_KEY` is never classified as a blocker.
- [ ] **P6-REPT-01**: Final sanitized report includes every field required by specification §20 and excludes raw namespace, credentials, tokens, full environment, and sensitive endpoint parameters.
- [x] **P6-CONT-01**: Passing H1–H7 evidence is reused; work resumes from `BLOCKED_POST_COMMIT_SOURCE_BINDING` and completed work is rerun only when a fix or authoritative gate requires it.

### Native Ollama Remediation (gap closure; ab5fdeb)

Additive after OpenAI-proxy final canary `20260723t065038z-8b0d3621` failed Gate 2 (`FAILED_BEFORE_COMMIT`). Old OpenAI-path evidence remains immutable terminal. Execute via gaps-only / wave≥6 / direct plan; never resume 06-05.

- [ ] **P6-OLL-AUTH-01**: Prior failed canary remains immutable terminal evidence; Ollama remediation binds only reviewed HEAD and never rewrites old ledger/report/R receipts.
- [ ] **P6-OLL-CONF-01**: Clean-room catalog-local example and materializer emit native Ollama authority — provider `ollama`, model `qwen3-embedding:0.6b`, dimensions `1024`, host URL default `http://host.docker.internal:11434`, no required API key, truncate true.
- [ ] **P6-OLL-EMB-01**: Factory and embedder path use native `OllamaEmbedder` `/api/embed` with model/dimensions 1024; no OpenAI proxy path; dimension mismatch fails before graph write; prepare/commit paths prove zero generative LLM calls under spy.
- [ ] **P6-OLL-CAPA-01**: Capability probe uses Ollama `/api/tags` only; model present ⇒ `embeddings.ready=ready`; missing/unreachable ⇒ `error`; Ollama `unknown` receives no OpenAI waiver; manifest `allow_unknown_embedding_provider=null`.
- [ ] **P6-OLL-LAUNCH-01**: Final-canary launcher builds Ollama argv without unconditional OpenAI waiver; freeze receipt binds provider/model/dimensions/ready/null waiver and rejects openai/unknown/drift.
- [ ] **P6-OLL-PREFLIGHT-01**: Host Ollama preflight proves daemon, exact model, one native embed probe at 1024 dims; sanitized receipt only (no vector/secrets).
- [ ] **P6-OLL-TDD-01**: Complete frozen remediation matrix plus required Ollama E2E pass with zero unexplained skips/deselections before rebind.
- [ ] **P6-OLL-BIND-01**: Candidate commit + raw-Git exact archive bind under 06-OLLAMA-BIND evidence only.
- [ ] **P6-OLL-IMG-01**: One new source-bound Ollama image; prior OpenAI image remains historical only.
- [ ] **P6-OLL-RT-01**: Entirely new clean-room R0–R3 with Ollama ready; never reuse failed project/volumes; 0/14→14/14 one-shot; 28 tools; exact image ID.
- [ ] **P6-OLL-CAN-01**: Exactly one top-level Ollama final canary after freeze approval under 06-OLLAMA-* live names.
- [ ] **P6-OLL-SAFE-01**: Preserve user-owned dirty config, historical stacks, and final Ollama stack; no prune/cleanup/graph clear; no wrong staging of dirty overlay.
- [ ] **P6-OLL-REPT-01**: Sanitized 06-OLLAMA final report/ledger only; no secrets/namespace/raw vectors; old OpenAI report untouched.

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
| Production migration or historical/live-group writes | Phase 6 authorizes only new isolated canary groups |
| More than one final canary | Phase 6 authorizes exactly one after the identity-allocation boundary |
| Graph cleanup or existing-data deletion | Historical/final resources remain intact; only separately confirmed, proven disposable pre-boundary candidates may be scoped-cleaned |
| FalkorDB, Kuzu, or Neptune catalog portability | Neo4j semantics are the verified target |
| Deployment or Kubernetes rollout | Configuration may be documented; deployment is separate |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| P6-AUTH-01 | Phase 6 | Complete |
| P6-BASE-01 | Phase 6 | Complete |
| P6-BASE-02 | Phase 6 | Pending |
| P6-BASE-03 | Phase 6 | Complete |
| P6-PRES-01 | Phase 6 | Complete |
| P6-PRES-02 | Phase 6 | Complete |
| P6-PRES-03 | Phase 6 | Pending |
| P6-PROV-01 | Phase 6 | Pending |
| P6-PROV-02 | Phase 6 | Pending |
| P6-PROV-03 | Phase 6 | Pending |
| P6-HARN-01 | Phase 6 | Pending |
| P6-HARN-02 | Phase 6 | Pending |
| P6-HARN-03 | Phase 6 | Pending |
| P6-HARN-04 | Phase 6 | Pending |
| P6-HARN-05 | Phase 6 | Pending |
| P6-HARN-06 | Phase 6 | Pending |
| P6-HARN-07 | Phase 6 | Pending |
| P6-HARN-08 | Phase 6 | Pending |
| P6-HARN-09 | Phase 6 | Pending |
| P6-HARN-10 | Phase 6 | Pending |
| P6-HARN-11 | Phase 6 | Pending |
| P6-HARN-12 | Phase 6 | Pending |
| P6-HARN-13 | Phase 6 | Pending |
| P6-HARN-14 | Phase 6 | Pending |
| P6-HARN-15 | Phase 6 | Pending |
| P6-HARN-16 | Phase 6 | Pending |
| P6-HARN-17 | Phase 6 | Pending |
| P6-HARN-18 | Phase 6 | Pending |
| P6-HARN-19 | Phase 6 | Complete |
| P6-TDD-01 | Phase 6 | Complete |
| P6-TDD-02 | Phase 6 | Complete |
| P6-TDD-03 | Phase 6 | Complete |
| P6-TDD-04 | Phase 6 | Complete |
| P6-BIND-01 | Phase 6 | Complete |
| P6-BIND-02 | Phase 6 | Complete |
| P6-BIND-03 | Phase 6 | Complete |
| P6-BIND-04 | Phase 6 | Complete |
| P6-BIND-05 | Phase 6 | Complete |
| P6-BIND-06 | Phase 6 | Complete |
| P6-IMG-01 | Phase 6 | Pending |
| P6-IMG-02 | Phase 6 | Pending |
| P6-IMG-03 | Phase 6 | Pending |
| P6-IMG-04 | Phase 6 | Pending |
| P6-IMG-05 | Phase 6 | Pending |
| P6-RT-00 | Phase 6 | Pending |
| P6-RT-R0 | Phase 6 | Pending |
| P6-RT-R1 | Phase 6 | Pending |
| P6-RT-R2 | Phase 6 | Pending |
| P6-RT-R3 | Phase 6 | Pending |
| P6-RT-DISP | Phase 6 | Pending |
| P6-CAN-01 | Phase 6 | Pending |
| P6-CAN-02 | Phase 6 | Pending |
| P6-CAN-03 | Phase 6 | Pending |
| P6-CAN-04 | Phase 6 | Pending |
| P6-CAN-05 | Phase 6 | Pending |
| P6-CAN-06 | Phase 6 | Pending |
| P6-SAFE-01 | Phase 6 | Pending |
| P6-SAFE-02 | Phase 6 | Pending |
| P6-TERM-01 | Phase 6 | Pending |
| P6-TERM-02 | Phase 6 | Pending |
| P6-TERM-03 | Phase 6 | Pending |
| P6-TERM-04 | Phase 6 | Pending |
| P6-REPT-01 | Phase 6 | Pending |
| P6-CONT-01 | Phase 6 | Complete |
| P6-OLL-AUTH-01 | Phase 6 | Pending |
| P6-OLL-CONF-01 | Phase 6 | Pending |
| P6-OLL-EMB-01 | Phase 6 | Pending |
| P6-OLL-CAPA-01 | Phase 6 | Pending |
| P6-OLL-LAUNCH-01 | Phase 6 | Pending |
| P6-OLL-PREFLIGHT-01 | Phase 6 | Pending |
| P6-OLL-TDD-01 | Phase 6 | Pending |
| P6-OLL-BIND-01 | Phase 6 | Pending |
| P6-OLL-IMG-01 | Phase 6 | Pending |
| P6-OLL-RT-01 | Phase 6 | Pending |
| P6-OLL-CAN-01 | Phase 6 | Pending |
| P6-OLL-SAFE-01 | Phase 6 | Pending |
| P6-OLL-REPT-01 | Phase 6 | Pending |
| BASE-01 | Phase 0 | Pending |
| BASE-02 | Phase 0 | Pending |
| BASE-03 | Phase 0 | Pending |
| BASE-04 | Phase 0 | Pending |
| SAFE-01 | Phase 0 | Pending |
| SAFE-02 | Phase 0 | Pending |
| SAFE-03 | Phase 5 | Complete |
| SAFE-04 | Phase 5 | Complete |
| SAFE-05 | Phase 1 | Complete |
| SAFE-06 | Phase 5 | Complete |
| SAFE-07 | Phase 5 | Complete |
| SAFE-08 | Phase 1 | Complete |
| SAFE-09 | Phase 5 | Complete |
| SAFE-10 | Phase 5 | Complete |
| SAFE-11 | Phase 3A | Complete |
| SAFE-12 | Phase 0 | Pending |
| SAFE-13 | Phase 0 | Pending |
| CONT-01 | Phase 1 | Complete |
| CONT-02 | Phase 1 | Complete |
| CONT-03 | Phase 1 | Complete |
| CONT-04 | Phase 1 | Complete |
| CONT-05 | Phase 1 | Complete |
| CONT-06 | Phase 1 | Complete |
| CONT-07 | Phase 1 | Complete |
| CONT-08 | Phase 1 | Complete |
| IDEN-01 | Phase 1 | Complete |
| IDEN-02 | Phase 1 | Complete |
| IDEN-03 | Phase 1 | Complete |
| IDEN-04 | Phase 1 | Complete |
| IDEN-05 | Phase 1 | Complete |
| IDEN-06 | Phase 1 | Complete |
| IDEN-07 | Phase 1 | Complete |
| IDEN-08 | Phase 4 | Complete |
| IDEN-09 | Phase 1 | Complete |
| IDEN-10 | Phase 1 | Complete |
| IDEN-11 | Phase 1 | Complete |
| IDEN-12 | Phase 1 | Complete |
| IDEN-13 | Phase 5 | Complete |
| EDGE-01 | Phase 2 | Complete |
| EDGE-02 | Phase 2 | Complete |
| EDGE-03 | Phase 2 | Complete |
| EDGE-04 | Phase 2 | Complete |
| EDGE-05 | Phase 2 | Complete |
| EDGE-06 | Phase 2 | Complete |
| EDGE-07 | Phase 2 | Complete |
| EDGE-08 | Phase 2 | Complete |
| EDGE-09 | Phase 2 | Complete |
| HASH-01 | Phase 2 | Complete |
| HASH-02 | Phase 2 | Complete |
| HASH-03 | Phase 2 | Complete |
| HASH-04 | Phase 2 | Complete |
| HASH-05 | Phase 2 | Complete |
| HASH-06 | Phase 2 | Complete |
| HASH-07 | Phase 2 | Complete |
| CAPA-01 | Phase 2 | Complete |
| CAPA-02 | Phase 2 | Complete |
| CAPA-03 | Phase 2 | Complete |
| CAPA-04 | Phase 2 | Complete |
| CAPA-05 | Phase 2 | Complete |
| CAPA-06 | Phase 2 | Complete |
| CAPA-07 | Phase 2 | Complete |
| CAPA-08 | Phase 2 | Complete |
| CAPA-09 | Phase 2 | Complete |
| PLAN-01 | Phase 3A | Complete |
| PLAN-02 | Phase 3A | Complete |
| PLAN-03 | Phase 3A | Complete |
| PLAN-04 | Phase 3A | Complete |
| PLAN-05 | Phase 3A | Complete |
| PLAN-06 | Phase 3A | Complete |
| PLAN-07 | Phase 3A | Complete |
| PLAN-08 | Phase 3A | Complete |
| PLAN-09 | Phase 3A | Complete |
| PLAN-10 | Phase 3A | Complete |
| PLAN-11 | Phase 3A | Complete |
| PLAN-12 | Phase 3A | Complete |
| PLAN-13 | Phase 3B | Complete |
| PLAN-14 | Phase 3B | Complete |
| PLAN-15 | Phase 3B | Complete |
| PLAN-16 | Phase 3B | Complete |
| PLAN-17 | Phase 3A | Complete |
| PLAN-18 | Phase 3A | Complete |
| PLAN-19 | Phase 3A | Complete |
| PLAN-20 | Phase 3A | Complete |
| EVID-01 | Phase 2 | Complete |
| EVID-02 | Phase 2 | Complete |
| EVID-03 | Phase 2 | Complete |
| EVID-04 | Phase 2 | Complete |
| EVID-05 | Phase 2 | Complete |
| EVID-06 | Phase 2 | Complete |
| EVID-07 | Phase 3B | Complete |
| EVID-08 | Phase 3B | Complete |
| EVID-09 | Phase 3B | Complete |
| EVID-10 | Phase 3B | Complete |
| EVID-11 | Phase 3B | Complete |
| EVID-12 | Phase 4 | Complete |
| EVID-13 | Phase 4 | Complete |
| EVID-14 | Phase 2 | Complete |
| MANI-01 | Phase 3B | Complete |
| MANI-02 | Phase 3B | Complete |
| MANI-03 | Phase 3B | Complete |
| MANI-04 | Phase 3B | Complete |
| MANI-05 | Phase 4 | Complete |
| MANI-06 | Phase 3B | Complete |
| MANI-07 | Phase 3B | Complete |
| VERI-01 | Phase 4 | Complete |
| VERI-02 | Phase 4 | Complete |
| VERI-03 | Phase 4 | Complete |
| VERI-04 | Phase 4 | Complete |
| VERI-05 | Phase 4 | Complete |
| VERI-06 | Phase 4 | Complete |
| RESE-01 | Phase 4 | Complete |
| RESE-02 | Phase 4 | Complete |
| RESE-03 | Phase 4 | Complete |
| GATE-01 | Phase 4 | Complete |
| GATE-02 | Phase 4 | Complete |
| GATE-03 | Phase 4 | Complete |
| GATE-04 | Phase 4 | Complete |
| GATE-05 | Phase 4 | Complete |
| GATE-06 | Phase 4 | Complete |
| TEST-01 | Phase 1 | Complete |
| TEST-02 | Phase 2 | Complete |
| TEST-03 | Phase 1 | Complete |
| TEST-04 | Phase 2 | Complete |
| TEST-05 | Phase 3A | Complete |
| TEST-06 | Phase 3B | Complete |
| TEST-07 | Phase 3B | Complete |
| TEST-08 | Phase 4 | Complete |
| TEST-09 | Phase 4 | Complete |
| TEST-10 | Phase 5 | Complete |
| TEST-11 | Phase 5 | Complete |
| TEST-12 | Phase 5 | Complete |
| DOCS-01 | Phase 5 | Complete |
| DOCS-02 | Phase 5 | Complete |
| DOCS-03 | Phase 5 | Complete |
| DOCS-04 | Phase 5 | Complete |
| DOCS-05 | Phase 5 | Complete |
| DOCS-06 | Phase 5 | Complete |
| REPT-01 | Phase 5 | Complete |

**Coverage:**

- v1.1 requirements: 202 total
- Mapped: 202/202
- Orphans: 0
- Duplicates: 0

| Phase | Count |
|-------|------:|
| Phase 0 | 8 |
| Phase 1 | 23 |
| Phase 2 | 34 |
| Phase 3A | 18 |
| Phase 3B | 17 |
| Phase 4 | 21 |
| Phase 5 | 17 |
| Phase 6 | 64 |
| **Total** | **202** |

---
*Requirements defined: 2026-07-17*
*Last updated: 2026-07-22 Phase 6 requirements ingested from fork commit `e52c1b5`; execution pending*
