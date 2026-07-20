# Phase 3A: Immutable Prepare/Commit Control Plane - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning
**Mode:** Autonomous — all recommended options selected under standing user approval

<domain>
## Phase Boundary

Add restart-safe `prepare_catalog_batch`, token-only `commit_prepared_catalog_batch`, and `discard_prepared_catalog_batch` contracts. Prepare freezes the complete validated catalog-v2 request, deterministic identities, exact proposed membership, projections, and embeddings into bounded immutable Neo4j control-plane state while writing zero domain/evidence/manifest/batch-status data. Phase 3A proves token lifecycle, storage immutability, restart safety, limits, and external-call-free commit loading. Actual atomic domain/evidence/manifest writes remain Phase 3B.

If Neo4j cannot safely store the complete immutable bounded prepared artifact, stop and report. Do not weaken the contract, retain hashes alone, or accept mutable client payloads at commit.

</domain>

<decisions>
## Implementation Decisions

### Prepared Artifact Representation
- **D-01:** Persist one deterministic non-`Entity` prepared-plan root plus ordered bounded server-owned payload-chunk control records when the artifact exceeds a conservative per-record ceiling.
- **D-02:** The frozen artifact contains canonical payload bytes, schema/canonicalization versions, group/batch scope, request/catalog/artifact hashes, deterministic identities, resolved membership, projected outcomes, and all required embeddings. Hashes and counts alone are insufficient.
- **D-03:** Define one deterministic artifact serialization and `artifact_sha256`; chunk ordering, count, byte lengths, and digest are immutable. Reassembly must reproduce byte-identical canonical content before commit may proceed.
- **D-04:** Plan and chunk records carry fixed control labels only. They never carry `Entity`, `Episodic`, semantic edge labels, searchable embeddings, or properties used by normal graph search/community paths.
- **D-05:** Immutability is enforced in both store queries and service checks: create once under deterministic plan identity, reject same identity with changed digest/scope/content, never update artifact bytes or frozen embeddings after PREPARED.
- **D-06:** Research must establish a conservative Neo4j property/transaction sizing policy and chunk threshold. If bounded immutable persistence cannot be proven, Phase 3A hard-stops.

### Opaque Token and Plan State
- **D-07:** Generate a high-entropy opaque token using Python `secrets`; return it exactly once from prepare. Never derive it from plan UUID, batch ID, request hash, or other predictable material.
- **D-08:** Persist only a domain-separated SHA-256 token digest. Compare supplied-token digests with `hmac.compare_digest`. Never log, return later, serialize into the artifact, or store the raw token in recoverable form.
- **D-09:** Bind the token persistently to one `plan_uuid`, `group_id`, `batch_id`, identity schema version, request hash, catalog hash, artifact hash, and expiry. A token cannot authorize another scope.
- **D-10:** Use explicit `PREPARED`, `COMMITTING`, `COMMITTED`, `DISCARDED`, and `EXPIRED` states with legal compare-and-set transitions. Terminal states never revive.
- **D-11:** `discard_prepared_catalog_batch` accepts only the token, is idempotent for an unconsumed plan, transitions `PREPARED` to `DISCARDED`, and never deletes domain graph data, evidence, manifests, or committed batch status.
- **D-12:** A stranded `COMMITTING` plan follows one deterministic recovery rule selected by research and proven by tests. No timeout-only blind reset to PREPARED.
- **D-13:** Missing, malformed, expired, discarded, consumed, or conflicting tokens return fixed structured prepared-plan errors with bounded messages and no token-validity oracle beyond the documented outcome.

### Prepare Preflight and Projection
- **D-14:** `prepare_catalog_batch` accepts the complete canonical catalog-v2 batch contract without `dry_run`, token, or caller identity/hash authority. The server computes all authoritative hashes and identities.
- **D-15:** Before control-plane persistence, validate the whole request: strict fields, identity/version/system grammar, limits, duplicate/coalescing rules, topology, existing and same-batch endpoints, immutable identity conflicts, source/evidence target resolution, and configured/hard plan limits.
- **D-16:** Compute exact projected created/updated/unchanged outcomes and exact entity/edge/source/evidence membership. Reuse current `CatalogService` preparation/preflight helpers where correct; do not fork a second identity/topology/hash authority.
- **D-17:** Compute every required embedding before opening the prepared-artifact write transaction. Embedding failure leaves no plan root, chunk, domain, evidence, manifest, status, or terminal-state partial write.
- **D-18:** Prepare persists control-plane state only after all pure checks, reads, projections, canonicalization, and external precomputation succeed. It writes zero `Entity`, `RELATES_TO`, `Episodic`, MENTIONS/evidence, manifest, or `CatalogIngestBatch` state.
- **D-19:** Prepare receipt returns the one-time token, deterministic plan UUID, authoritative request/catalog/artifact hashes, schema versions, entity/edge/source/evidence-link counts, projected outcomes, and `expires_at`; never returns canonical payload or embeddings.

### Token-Only Commit Boundary
- **D-20:** `commit_prepared_catalog_batch` accepts only `plan_token` and optional `expected_request_sha256`. It cannot accept group, batch, entities, edges, sources, evidence links, catalog hash, replacement payload, or mutable execution flags.
- **D-21:** Commit loads and reassembles the frozen artifact server-side, verifies token binding, state, expiry, chunk integrity, artifact hash, request hash, schema versions, counts, and immutable scope before any domain transaction.
- **D-22:** Commit uses only embeddings frozen in the artifact. It performs no embedder, LLM, queue, HTTP, provider, or other external network call before or during domain commit.
- **D-23:** Phase 3A may implement and test the safe token claim/load/revalidation seam and state machine, but Phase 3B owns the one-transaction domain/evidence/manifest/terminal-state commit body. No provisional domain write is allowed merely to demonstrate commit.

### Limits, Retention, and Capacity
- **D-24:** Add configured TTL, maximum prepared payload bytes, maximum active plans per group, and chunk size/count controls with immutable hard ceilings. Defaults must be conservative and exposed truthfully by capabilities.
- **D-25:** Enforce active-plan capacity by `group_id` under a transaction-safe claim, counting only active nonterminal plans according to a documented policy. Capacity checks cannot race into an unbounded excess.
- **D-26:** Expiry is evaluated against server UTC time. Access may atomically mark an expired PREPARED plan `EXPIRED`; cleanup remains bounded and must not be required for correctness.
- **D-27:** Terminal record retention/cleanup policy may be deferred to operational polish if terminal states remain bounded and correctness does not depend on deletion. No background queue or unbounded cleanup worker in Phase 3A.

### Compatibility and Phase 3A Gate
- **D-28:** Keep `upsert_catalog_batch` available unchanged for compatibility, including `dry_run=true` zero-write. Prepare/commit/discard are additive and become the preferred agent path only after their gate passes.
- **D-29:** Update `get_catalog_capabilities` from placeholders to actual configured/hard TTL, payload, active-plan, and pagination limits. Set prepare/commit support true only when registration and Phase 3A contract tests are green; manifests remain false until Phase 3B.
- **D-30:** Preserve every legacy MCP tool and existing eight catalog tool contracts. New tools use strict request models and the same structured safe-error boundary.
- **D-31:** Phase 3B remains blocked until tests prove zero domain/status mutation on prepare, byte-immutable restart-safe artifacts, token-only commit, timing-safe digest checks, TTL/size/cardinality enforcement, missing/expired/discarded/consumed/conflicting outcomes, and zero external calls on commit.
- **D-32:** Tests use only `oracle-catalog-tool-test`. Never query/mutate `oracle-catalog-v2`; never run the canary, deploy, clear graph, or touch remote state.

### Claude's Discretion
- Choose exact conservative numeric defaults and hard ceilings after research against Neo4j 5.26 property/transaction behavior and current catalog scale.
- Choose fixed control labels/property names and whether chunk payload is UTF-8 canonical JSON or base64-encoded bytes, provided byte identity, bounded storage, and safe reassembly are proven.
- Choose the deterministic stranded-`COMMITTING` recovery mechanism, provided it cannot cause a second writer or revive terminal plans and Phase 3B can atomically finalize it.
- Choose the smallest module split across models, identity, service, store, and MCP wrappers; do not refactor the MCP monolith beyond thin additive registration.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone and Phase Contract
- `.planning/ROADMAP.md` §Phase 3A — phase goal, success criteria, hard stop, dependency gate.
- `.planning/REQUIREMENTS.md` — PLAN-01..12, PLAN-17..20, SAFE-11, TEST-05 exact contracts.
- `.planning/graphiti_mcp_pre_canary_roadmap_en.md` §Phase 3A and Mandatory Notes — prepare/commit state machine, restart/replay rules, stop conditions.

### Prior Authorities
- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-CONTEXT.md` — strict contracts, catalog-v2 identity, safe errors, no client UUID authority.
- `.planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-CONTEXT.md` — topology, evidence, canonical hash, capabilities decisions that prepare must reuse.
- `.planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-VERIFICATION.md` — verified Phase 2 truths and `ready_for_phase_3a=true` evidence.
- `.planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-SECURITY.md` — threat controls carried into token/artifact work.

### Existing Code Boundaries
- `mcp_server/src/config/schema.py` — `CatalogConfig` and hard/configured batch-limit pattern.
- `mcp_server/src/models/catalog_batch.py` — complete strict canonical batch request.
- `mcp_server/src/models/catalog_common.py` — strict base, bounds, prepared-plan error codes.
- `mcp_server/src/models/catalog_responses.py` — additive response models and capability shape.
- `mcp_server/src/services/catalog_identity.py` — UUIDv5 and canonical hash authorities.
- `mcp_server/src/services/catalog_service.py` — preparation, conflict, projection, embedding, and transaction orchestration seams.
- `mcp_server/src/services/catalog_store.py` — fixed-query Neo4j store and transaction helpers.
- `mcp_server/src/services/catalog_capabilities.py` — current Phase 3A placeholder limits/features.
- `mcp_server/src/graphiti_mcp_server.py` — thin FastMCP tool registration and safe error rewriting.
- `graphiti_core/driver/neo4j_driver.py` — real commit/rollback transaction context.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `UpsertCatalogBatchRequest` already contains the complete strict Phase 2 domain contract and authoritative request-hash inputs.
- `CatalogService` already prepares typed entities, edges, sources, projections, endpoint checks, embeddings, and batch hash echoes; refactor shared pure/pre-write preparation rather than cloning behavior.
- `CatalogNeo4jStore` already uses fixed server-owned Cypher, composite identity claims, explicit transaction objects, first-row checks, and structured `CatalogStoreError` codes.
- `catalog_identity.py` already provides `catalog_prepared_plan_uuid`; extend it with artifact/token digest helpers under explicit domains.
- `CatalogErrorCode` already includes prepared-plan not-found, expired, conflict, and already-consumed codes.
- Capabilities already expose zero-valued Phase 3A placeholders, providing an additive contract seam.

### Established Patterns
- Strict Pydantic models validate all nested input before service/backend access.
- Fixed labels/property names prevent Cypher injection; group isolation appears in every store query.
- Embeddings precede domain write transactions; real Neo4j transactions roll back on exceptions.
- Control records such as `CatalogIngestBatch` avoid the `Entity` label and normal semantic search.
- Thin MCP wrappers delegate to `CatalogService`; safe structured responses hide raw exceptions and payloads.

### Integration Points
- New request/response models feed three new MCP tools and `CATALOG_TOOL_NAMES` error rewriting.
- Prepare orchestration reuses Phase 2 canonical payload/hash, endpoint map, evidence contract, and current service projection helpers.
- New plan/chunk store methods must support group-isolated immutable create/load/CAS state transitions without schema interpolation.
- Config and capabilities gain actual TTL/payload/active-plan/chunk ceilings.
- Phase 3B consumes the frozen artifact and COMMITTING claim seam; Phase 3A must not bake in a non-atomic domain write workaround.

</code_context>

<specifics>
## Specific Ideas

- Use stdlib `secrets`, `hashlib`, and `hmac`; no new dependency is justified for opaque tokens or timing-safe comparison.
- Prefer a deterministic plan root keyed by server-derived UUID plus ordered chunk identities over one unbounded JSON property.
- Treat cleanup as storage hygiene, not correctness: expiry/state checks must remain fail-closed even if expired records have not yet been deleted.
- The user pre-approved every recommended discussion option. Transient parser/internal errors may be retried or ignored only when product, security, validation, and hard-gate truth remain intact.

</specifics>

<deferred>
## Deferred Ideas

- Domain entity/edge/source writes, exact evidence persistence, durable manifest, terminal batch status, and terminal plan co-commit: Phase 3B.
- Concurrent same-token domain commit, complete rollback, and stranded COMMITTING production recovery proof: finalized in Phase 3B using the Phase 3A state seam.
- Manifest/evidence reads, edge resolution, and manifest-backed verification: Phase 4.
- Long-term retention jobs, metrics, migration/rollback docs, and operational cleanup: Phase 5 unless required for Phase 3A correctness.
- Canary execution, `oracle-catalog-v2` access, production migration, deployment, and graph cleanup: separate approval/out of scope.

</deferred>

---

*Phase: 3A-immutable-prepare-commit-control-plane*
*Context gathered: 2026-07-18*
