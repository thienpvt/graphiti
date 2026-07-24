# Phase 3B: Atomic Catalog, Exact Evidence, and Durable Manifest Writes - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning
**Mode:** Autonomous — all recommended options selected under standing user approval

<domain>
## Phase Boundary

Complete `commit_prepared_catalog_batch` so one claimed immutable Phase 3A artifact drives a single Neo4j success transaction that writes catalog domain data, exact evidence, a durable exact-membership manifest, terminal `CatalogIngestBatch` status, and terminal prepared-plan state. Preserve complete rollback, deterministic recovery from stranded `COMMITTING`, identical replay, concurrent same-token single-logical-commit behavior, and Graphiti search interoperability.

Phase 4 owns manifest/evidence reads, edge resolution, manifest-backed verification, and read/write diagnostic gates. Phase 5 owns final operations, compatibility, security, migration documentation, and readiness. Canary execution, `oracle-catalog-v2` access, deployment, migration, graph clearing, and data deletion remain out of scope.

If Neo4j 5.26+ cannot co-commit domain, evidence, manifest, batch terminal state, and plan terminal state in one transaction under the configured hard ceilings, stop and report. Do not weaken atomicity or split success across transactions.

</domain>

<decisions>
## Implementation Decisions

### Transaction Boundary and Write Ordering
- **D-01:** Phase 3B extends the existing Phase 3A token claim/load/revalidation seam; it does not replace or weaken token-only input, immutable artifact verification, or the `COMMITTING` state claim.
- **D-02:** Keep the Phase 3A claim as a separate transaction: `PREPARED -> COMMITTING`, with legal same-token `COMMITTING -> COMMITTING` re-entry. Open the domain success transaction only after claim and artifact verification succeed.
- **D-03:** One Neo4j success transaction must co-write domain entities, domain edges, provenance sources and Graphiti-compatible links, exact evidence records, durable manifest records, terminal `CatalogIngestBatch=committed`, and terminal prepared-plan `COMMITTED`.
- **D-04:** Use a deterministic write order inside that transaction: claim/recheck batch identity, entities, edges, provenance sources and compatibility links, exact evidence, manifest root/chunks, terminal batch status, terminal plan state. The planner may refine the order only to satisfy dependencies without creating another success transaction.
- **D-05:** Any exception before transaction exit rolls back every success artifact. No domain, evidence, manifest, committed status, or plan `COMMITTED` may survive a failed success transaction.
- **D-06:** Embeddings, payload, identities, membership, hashes, and projections come only from the frozen prepared artifact on commit. Commit performs no embedder, LLM, queue, HTTP, provider, or other external call.

### Stranded COMMITTING Recovery
- **D-07:** Recovery is deterministic resume-or-finish from the same verified frozen artifact. Never reset a timed-out or stranded plan to `PREPARED`; never mint replacement authority; never permit a mutable retry payload.
- **D-08:** Serialize recovery for a plan using transaction-local Neo4j locking/CAS authority. A same-token re-entry either observes a valid completed outcome or becomes the sole writer that reruns the complete idempotent success transaction.
- **D-09:** A plan is considered committed only when its terminal `COMMITTED` state, terminal committed batch status, and durable manifest agree on group, batch, request/catalog/artifact hashes, identity schema, and manifest consistency hash. Partial or contradictory terminal evidence fails closed.
- **D-10:** If valid terminal evidence already exists, return the stable committed logical receipt without rewriting domain/evidence/manifest records. Otherwise resume the complete success transaction from the frozen artifact.
- **D-11:** A permanent conflict rolls back the success transaction and returns a bounded structured error. The plan remains `COMMITTING` unless the same success transaction atomically reaches `COMMITTED`; it never revives to `PREPARED`.

### Exact Evidence and Search Interoperability
- **D-12:** Persist one bounded non-`Entity` exact evidence control record per explicit canonical `CatalogEvidenceLink`, keyed by deterministic server-derived UUID and immutable content hash.
- **D-13:** Resolve each evidence source and its one typed entity-or-edge target within the same `group_id` and success transaction. Missing, duplicate, type-mismatched, endpoint-mismatched, or hash-conflicting targets fail atomically.
- **D-14:** Byte-identical duplicate evidence links coalesce to one logical record and one manifest member. Reuse of an evidence identity with divergent immutable source/target/content returns `provenance_link_conflict`.
- **D-15:** Exact evidence records and relationships use fixed server-owned labels/types/properties only. They never carry `Entity`, enter entity/vector/fulltext indexes, or participate in community clustering.
- **D-16:** Preserve Graphiti-compatible provenance interoperability: source `Episodic` nodes, explicit `MENTIONS` for entity evidence, and edge `episodes` membership remain available where supported by the explicit link. Never fabricate links or recreate the rejected Cartesian source-by-target behavior.

### Durable Manifest Authority
- **D-17:** Persist one deterministic non-`Entity` `CatalogBatchManifest` root plus ordered bounded server-owned membership chunks when needed, mirroring the proven Phase 3A root/chunk integrity pattern rather than one unbounded property.
- **D-18:** The manifest contains exact requested logical membership for entities, edges, provenance sources, and evidence links, including created, updated, and unchanged shared objects. Membership comes from the frozen prepared artifact, not live row counts.
- **D-19:** Entity/edge `batch_id` remains compatibility or last-change metadata only. It is never manifest membership authority.
- **D-20:** Store deterministic compact identities, UUIDs, exact category counts, group/batch scope, identity/canonicalization/catalog versions, request/catalog/artifact hashes, and a canonical manifest consistency hash. Chunks have deterministic ordering, offsets/counts, byte bounds, and per-chunk/full digests.
- **D-21:** Manifest creation is create-once/idempotent. Exact replay preserves byte-identical membership and ordering; same manifest identity with changed content or bindings fails closed as a manifest/batch conflict.
- **D-22:** Manifest/evidence read tools and manifest-backed verification remain Phase 4. Phase 3B implements persistence authorities and internal recovery reads only.

### Replay, Concurrency, and Compatibility
- **D-23:** Identical replay after successful commit returns the original stable logical outcomes and counts from durable authoritative state. It creates no duplicate domain, provenance, evidence, manifest, status, or terminal-plan records.
- **D-24:** Concurrent same-token commits yield one logical committed batch. Neo4j locks/CAS plus uniqueness constraints and create-once identities arbitrate the writer; followers recover or replay deterministically.
- **D-25:** Concurrent different tokens for the same group/batch/request identity either converge on the same committed manifest and stable replay or fail with the documented deterministic conflict. They never produce two logical manifests or duplicated domain/evidence.
- **D-26:** Refactor the existing `upsert_catalog_batch` write body into one shared atomic writer used by prepared commit and direct catalog-v2 upsert. Direct non-dry-run upsert must also co-write exact evidence, manifest, and terminal status so Phase 4 has one committed-batch authority. Preserve `dry_run=true` as zero-write.
- **D-27:** Optional failure recording occurs only after rollback in a separate transaction and stores bounded failure metadata. It must never imply domain success, create a manifest, or mark a prepared plan committed.
- **D-28:** Preserve all legacy MCP tools and existing catalog tool contracts. `commit_prepared_catalog_batch` remains token-only; its success response may add committed outcomes/counts without exposing payload, membership, embeddings, or token.

### Limits, Gates, and Proof
- **D-29:** Research must establish conservative Neo4j single-transaction and manifest chunk/property ceilings against the configured batch maxima. Reuse Phase 3A bounded artifact/chunk primitives where correct; do not add an unbounded manifest representation.
- **D-30:** Add fault-injection tests at every persistence boundary; each injected failure must prove zero partial graph and zero partial manifest after rollback.
- **D-31:** Add unit/service/store/concurrency/live Neo4j proofs for exact evidence, unchanged membership, replay, same-token and same-batch races, stranded `COMMITTING`, search interoperability, and control-label exclusion.
- **D-32:** Phase 4 remains blocked until a fail-closed Phase 3B gate reports atomicity, evidence persistence, manifest durability, recovery, concurrency, search interoperability, and safety green.
- **D-33:** Capability flags for manifests and committed exact-evidence persistence become true only after registration/persistence contracts and required live gate evidence pass. Manifest verification remains false until Phase 4.
- **D-34:** Tests and development writes use only `oracle-catalog-tool-test`. Never query or mutate `oracle-catalog-v2`; never run canary, deploy, push, merge, tag, clear graph, delete existing data, or claim non-Neo4j portability.

### Claude's Discretion
- Choose fixed manifest/evidence control labels, property allowlists, relationship names, and deterministic chunk identities consistent with Phase 3A security patterns.
- Choose the smallest shared atomic-writer extraction that avoids duplicating direct-upsert and prepared-commit logic; no broad MCP monolith refactor.
- Choose exact committed response additions and internal recovery result shape, preserving bounded safe output and existing public fields.
- Choose whether bounded failure status is recorded for each failure class; correctness must never depend on that side transaction.
- Choose exact conservative manifest chunk size/count ceilings after research and live proof.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone and Phase Contract
- `.planning/ROADMAP.md` §Phase 3B — goal, success criteria, dependency gate, hard stop.
- `.planning/REQUIREMENTS.md` — PLAN-13..16, EVID-07..11, MANI-01..04, MANI-06..07, TEST-06..07.
- `.planning/graphiti_mcp_pre_canary_roadmap_en.md` §Phase 3B and mandatory notes — state recovery, exact evidence, manifest authority, atomicity, stop conditions.

### Prior Locked Authorities
- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-CONTEXT.md` — strict contracts, catalog-v2 identity, safe errors, no caller UUID authority.
- `.planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-CONTEXT.md` — endpoint map, exact evidence schema, canonical hashes, capabilities.
- `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-CONTEXT.md` — frozen artifact, token lifecycle, state machine, zero-external commit seam, Phase 3B boundary.
- `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-VERIFICATION.md` — passed 6/6 product/process evidence and `ready_for_phase_3b=true`.
- `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-REVIEW.md` — clean review plus residual concurrency/schema considerations.
- `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json` — final HEAD-bound Phase 3A hard-gate authority.

### Existing Code Boundaries
- `mcp_server/src/services/catalog_service.py` — current direct batch transaction and Phase 3A commit claim/reassembly seam.
- `mcp_server/src/services/catalog_store.py` — fixed Cypher, entity/edge/source/MENTIONS/status writes, constraints, prepared-plan CAS.
- `mcp_server/src/services/catalog_identity.py` — catalog-v2 UUIDv5 and canonical hash authorities.
- `mcp_server/src/services/catalog_prepared_artifact.py` — proven canonical root/chunk serialization and integrity checks.
- `mcp_server/src/models/catalog_batch.py` — strict direct batch request and explicit evidence payload.
- `mcp_server/src/models/catalog_prepare.py` — token-only commit contract.
- `mcp_server/src/models/catalog_common.py` — limits, error registry, prepared states.
- `mcp_server/src/models/catalog_responses.py` — batch and prepared commit response contracts.
- `mcp_server/src/services/catalog_capabilities.py` — feature and configured/hard limit truth.
- `mcp_server/src/graphiti_mcp_server.py` — thin FastMCP registration and safe error boundary.
- `graphiti_core/driver/neo4j_driver.py` — real async commit/rollback transaction authority.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CatalogService._prepare_batch_preflight` and Phase 3A artifact membership already centralize strict validation, authoritative identities/hashes, projections, resolved membership, and frozen embeddings.
- `CatalogService.upsert_catalog_batch` already demonstrates embed-before-transaction ordering, a real batch identity claim, domain write ordering, and separate post-rollback failed status.
- `CatalogNeo4jStore` already provides fixed-query entity/edge/source writes, `MENTIONS`, edge `episodes`, terminal status writes, uniqueness constraints, prepared plan/chunk roots, and legal CAS.
- `catalog_prepared_artifact.py` already proves canonical bytes, bounded chunks, offsets, per-chunk hashes, and total digest; manifest storage should reuse that pattern where semantically correct.
- `Neo4jDriver.transaction()` commits on clean exit and rolls back on any `BaseException`.

### Established Patterns
- Validate and precompute before write transactions; commit consumes frozen data only.
- Every query is group-scoped and uses fixed server-owned labels/property names.
- Control records avoid `Entity` and searchable embedding properties.
- Create-once deterministic identities plus immutable-content checks provide replay/conflict authority.
- Structured errors and bounded logging expose identifiers/counts only, never raw tokens, payloads, source text, embeddings, or complete exceptions.

### Integration Points
- `commit_prepared_catalog_batch` extends after current artifact revalidation/claim into recovery and the shared success writer.
- `upsert_catalog_batch` supplies the existing transaction body to extract rather than clone.
- New evidence/manifest store methods and constraints integrate into `CatalogNeo4jStore` under one transaction.
- Prepared-plan `COMMITTING -> COMMITTED` and terminal batch status must occur through the same transaction object as domain/evidence/manifest writes.
- Capabilities and Phase 3B gate flip write-support truth only after live atomicity proof.

</code_context>

<specifics>
## Specific Ideas

- Prefer a small internal prepared-write projection consumed by one shared atomic writer over reconstructing Pydantic client requests or duplicating direct-upsert logic.
- Make manifest canonicalization a pure module/function with deterministic category ordering before any transaction.
- Use transaction-scoped lock acquisition on the prepared plan and batch/manifest identity before writes; do not rely on process-local locks for cross-process concurrency.
- Treat a stranded `COMMITTING` record as recoverable authority, not a failed or expired request.
- The user pre-approved every recommended discussion option. Transient parser/internal errors may be retried or ignored only when product, security, validation, and hard-gate truth remain intact.

</specifics>

<deferred>
## Deferred Ideas

- `get_catalog_batch_manifest`, `get_catalog_evidence`, `resolve_typed_edges`, manifest-backed `verify_catalog_batch`, pagination, and read/write gate separation: Phase 4.
- Final security/compatibility matrix, long-term retention/cleanup jobs, observability, migration docs, offline hardened canary regeneration, and final readiness report: Phase 5.
- `LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`, automatic catalog-v1 migration, parser/extraction, new business entities, and non-Neo4j portability: future/out of scope.
- Canary execution, `oracle-catalog-v2` access, production migration, deployment, graph clearing, and existing-data deletion: separate explicit approval only.

</deferred>

---

*Phase: 3B-atomic-catalog-exact-evidence-and-durable-manifest-writes*
*Context gathered: 2026-07-18*
