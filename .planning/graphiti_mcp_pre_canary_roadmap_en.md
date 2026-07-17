# Graphiti MCP Catalog-v2 — Pre-Canary Implementation Roadmap

## 1. Objective

Complete the deterministic catalog-ingestion capabilities in `mcp_server` before regenerating and running a canary for the relationship graph reconstructed from two card-platform systems:

- `FE`: the human-interactive transaction system, with almost no declared foreign keys.
- `BO`: the request-processing, synchronization, and completion system, with more declared foreign keys than FE.
- `COMMON`: the scope for artifacts that are genuinely shared; it must not become a fallback for objects whose ownership is unknown.

The target is an ingestion foundation that is:

- Fail-closed and deterministic.
- Collision-free across FE, BO, and COMMON identities.
- Restricted to topology approved and enforced by the server.
- Able to preserve exact provenance for every source-to-target assertion.
- Protected by immutable, restart-safe, and replay-safe prepare/commit semantics.
- Backed by exact manifests that can be verified independently after commit.
- Able to serve read-only diagnostics while catalog writes are disabled.
- Free of LLM and queue dependencies in the deterministic catalog path.

This roadmap covers coding and verification **before the canary only**. The coding agent must not execute a real canary as part of this work.

## 2. Mandatory Invariants

The following invariants apply across every phase:

1. Use one `group_id` for the reverse-engineering graph of the same business domain. FE, BO, and COMMON scope must be encoded in canonical identity, not separated through `group_id`.
2. Never create missing edge endpoints implicitly.
3. Do not use an LLM, background queue, or extraction pipeline in the deterministic catalog path.
4. Reject unknown request fields.
5. Every edge type must have a server-owned endpoint-type map.
6. Commit must never accept a mutable catalog payload again from the client.
7. Provenance must consist of explicit source-to-target evidence links; never create a Cartesian product between sources and targets.
8. The batch manifest is the authority for membership. An entity or edge `batch_id` property is not a membership authority.
9. Diagnostic reads must not depend on the catalog write gate.
10. Every phase must add and run its own tests; verification must not be deferred until the final phase.

## 3. Implementation Plan

### Phase 0 — Baseline, Inventory, and Compatibility Policy

**Goal:** Establish a repeatable baseline before changing contracts or identity rules.

#### Work

- Read `AGENTS.md`, repository-specific instructions, and the current architecture before editing code.
- Record the Git state and preserve all user changes outside this task.
- Run all unit and integration tests that can execute in the current environment.
- Inventory the current:
  - MCP tools.
  - Pydantic request and response models.
  - Entity types, edge types, and identity rules.
  - Feature gates.
  - Neo4j constraints, indexes, and control nodes.
  - Golden hashes and canary fixtures.
- Record baseline failures and distinguish pre-existing failures from new regressions.
- Establish a compatibility policy covering:
  - Which v1 contracts remain supported.
  - Which contracts are deprecated.
  - Which contracts Catalog-v2 intentionally breaks.
- Version the identity and hash schemas instead of silently changing the current algorithms.

#### Exit criteria

- A baseline report and reproducible test list exist.
- Every initial failure is recorded.
- Compatibility policy and migration boundaries are explicit.
- No production data has been changed and no canary has been executed.

---

### Phase 1 — Strict Contracts and Catalog-v2 Identity

**Goal:** Provide fail-closed request models and stable, collision-free FE/BO/COMMON identities.

#### Work

##### 1. Strict request contracts

- Apply `ConfigDict(extra="forbid")` to every Catalog-v2 request model and nested request model.
- Never silently ignore unknown fields.
- Remove options that have no behavioral effect, or turn them into enforceable contracts. For example:
  - If endpoints are always strict, use `Literal[True]` or remove `strict_endpoints`.
  - Do not retain a boolean that accepts `false` when the server does not implement a different behavior.
- Standardize structured errors with at least:
  - `code`.
  - `message`.
  - `field_path`, when applicable.
  - `retryable`.
  - A correlation identifier that contains no sensitive data.

##### 2. Catalog-v2 identity

- Add a required `identity_schema_version`, beginning with an explicit version such as `catalog-v2`.
- Require `system_key` from the closed set:
  - `FE`.
  - `BO`.
  - `COMMON`.
- Add, at minimum, these entity types:
  - `System`.
  - `DatabaseLink`.
  - `SourceArtifact`.
- Define a complete canonical graph-key grammar; prefix-only validation is insufficient.
- A canonical key must expose system scope and fully qualified database identity. For example:

```text
TABLE::FE::<DATABASE>.<SCHEMA>.<TABLE>
TABLE::BO::<DATABASE>.<SCHEMA>.<TABLE>
TABLE::COMMON::<DATABASE>.<SCHEMA>.<TABLE>
PACKAGE::FE::<DATABASE>.<SCHEMA>.<PACKAGE>
PROCEDURE::BO::<DATABASE>.<SCHEMA>.<PACKAGE>.<OVERLOAD_SIGNATURE>
```

- Procedure and function overloads must include a stable signature or overload discriminator in their identity.
- Derive UUIDv5 values from the versioned canonical identity.
- Do not use `name_raw` as the identity source when its casing or formatting can change.
- Define ownership rules for `COMMON`:
  - Use it only for artifacts that are genuinely shared or are assigned to COMMON by an authoritative source.
  - Reject or quarantine objects with unknown system ownership; never silently assign them to COMMON.
- Add validation for cross-system ambiguity and duplicate canonical identities.

#### Exit criteria

- Unknown fields and invalid enum values are rejected.
- Identically named qualified objects in FE and BO produce different UUIDs.
- The same canonical input always produces the same UUID.
- Overloads do not collide.
- The complete graph-key grammar has positive and negative unit tests.
- Previous fixtures and golden hashes are marked incompatible with identity v2; the old canary payload is not reused.

---

### Phase 2 — Topology Authority, Evidence Contract, Canonical Hashes, and Capabilities

**Goal:** Make the server authoritative for topology and freeze the evidence contract before finalizing canonical hashes and prepared artifacts.

#### Work

##### 1. Server-owned endpoint maps

- Create a centralized mapping from every edge type to its allowed endpoint-type pairs.
- Reject edges that use an allowed edge type with a disallowed endpoint pair.
- Validate endpoint types against resolved typed endpoints, not only client-supplied strings.
- Do not substitute the semantic `edge_type_map` from the Graphiti legacy path for deterministic-catalog validation.
- Preserve distinct relationship semantics:
  - Declared DDL foreign key: `ForeignKeyTo`.
  - Package, procedure, or view read: `ReadsFrom`.
  - Write operation: `WritesTo`.
  - Callable invocation: `Calls`.
  - Join expression: `JoinsWith`.
  - Static or dynamic code reference: `ReferencesByCode`.
  - Heuristic-only relationship: `LikelyReferencesTo`.
  - Cross-system semantic mapping: `MapsTo`.
  - Data propagation or synchronization: `SynchronizesTo`.
- If the final three edge types have not been approved for the v2 schema, stop and request a product decision. Do not substitute a similar edge type merely to continue implementation.

##### 2. Exact evidence contract

- Define `CatalogEvidenceLink` before freezing canonical hashing.
- Every evidence link must point to exactly:
  - One `SourceArtifact`.
  - One specific entity or edge target.
- The evidence model must include at least:
  - `source_graph_key` or a resolved source UUID.
  - `target_kind` and target identity.
  - `evidence_kind`.
  - `source_locator`, such as an object, line range, or statement index when available.
  - `extractor_name` and `extractor_version`.
  - `rule_id`.
  - `assertion_status`.
  - Range-validated `confidence`.
  - `support_count`, when applicable.
  - A stable statement or content hash.
- Store detailed evidence in the control/provenance model; do not disguise it as a semantic-search catalog entity.
- Do not permit legacy Cartesian provenance for multiple sources. If temporary compatibility is required, allow the legacy form only for exactly one source and emit a deprecation warning.

##### 3. Hash contracts

- Keep these concepts distinct:
  - `request_sha256`: hash of the normalized client contract.
  - `artifact_sha256`: checksum of the immutable server-prepared artifact, when storage-integrity verification is required.
- `request_sha256` must cover at least:
  - `identity_schema_version`.
  - `catalog_sha256`.
  - Entity records.
  - Edge records.
  - Source artifacts.
  - Explicit evidence links.
  - Every field that affects semantic output or membership.
- Do not include timestamps, random tokens, or transient server metadata in the canonical request hash.
- Canonical serialization must be versioned, deterministic, and independent of input order whenever order carries no meaning.
- Every applicable dry-run, prepare, and commit receipt must return the server-computed `request_sha256`.

##### 4. Capability discovery

- Add `get_catalog_capabilities`, returning at least:
  - Contract and identity-schema versions.
  - Supported entity and edge types.
  - Allowed endpoint pairs.
  - Graph-key grammar and version.
  - Request and batch limits.
  - Embedding behavior.
  - Read and write gate states.
  - Prepare-token TTL policy.
- Never expose secrets, internal token hashes, or storage implementation details through the capability response.

#### Exit criteria

- Every edge type has an endpoint map and negative tests.
- The evidence contract is stable before persistence implementation begins.
- Changing any semantic input changes the request hash.
- Reordering semantically unordered collections does not change the request hash.
- `catalog_sha256` and identity version are actually included in the hash contract.
- Clients can discover schema and operational limits without reading source code.

---

### Phase 3A — Immutable Prepare/Commit Control Plane

**Goal:** Eliminate payload mutation between validation and commit while providing safe restart, retry, and concurrent-commit behavior.

#### Work

- Add these tools:
  - `prepare_catalog_batch`.
  - `commit_prepared_catalog_batch`.
  - `discard_prepared_catalog_batch`.
- `prepare_catalog_batch` must:
  - Validate strict contracts, identity, endpoints, and evidence.
  - Canonicalize the payload.
  - Resolve deterministic UUIDs.
  - Produce the request hash and exact proposed membership.
  - Complete required embedding or other external precomputation before commit.
  - Store an immutable prepared artifact in durable, bounded control-plane storage.
  - Return a high-entropy opaque token exactly once, together with a safe receipt.
- Store only the token hash on the server; do not retain the raw token in recoverable form.
- `commit_prepared_catalog_batch` may accept only the token plus optional retry or correlation metadata that cannot change the artifact.
- Commit must not accept entities, edges, evidence, or catalog hashes again from the client.
- Define a state machine and legal transitions, including at least:

```text
PREPARED -> COMMITTING -> COMMITTED
PREPARED -> DISCARDED
PREPARED -> EXPIRED
```

- A retry after successful commit must idempotently return the original committed receipt without writing again.
- Two concurrent commits for the same token must produce at most one writer.
- A `COMMITTING` state left by process restart must have a deterministic recovery rule.
- Expired, discarded, malformed, and unknown tokens must return appropriate structured errors without leaking more token-validity information than necessary.
- Enforce TTL, bounded retention, cleanup, and capacity limits for prepared artifacts.
- Do not log raw tokens or complete sensitive payloads.
- Preserve the existing `dry_run` invariant: no domain write and no control-plane write.
- `prepare` may write the control-plane artifact, but it must not write the domain catalog graph.

#### Exit criteria

- Client-side mutation after prepare cannot change the committed artifact.
- A restart between prepare and commit still commits the correct artifact.
- Retry after a timeout cannot create duplicate writes.
- Concurrent commit behavior is tested.
- Expiry and discard behavior are tested.
- The commit path makes no external embedding, LLM, or network call.
- Dry-run remains zero-write.

---

### Phase 3B — Atomic Catalog, Exact Evidence, and Durable Manifest Writes

**Goal:** Commit or roll back catalog data, evidence, and batch membership together.

#### Work

- Persist explicit `CatalogEvidenceLink` records and remove the sources × targets behavior.
- Create a durable batch manifest with exact membership for:
  - Entity UUIDs.
  - Edge UUIDs.
  - SourceArtifact UUIDs.
  - Evidence-link UUIDs.
  - Expected counts by category.
  - Request and artifact hashes and schema versions.
- Include existing but unchanged objects that belong to the current batch.
- Never infer manifest membership from `entity.batch_id` or `edge.batch_id`.
- If a `batch_id` property remains for compatibility, document it as informational metadata only.
- Catalog nodes, edges, evidence links, manifest data, and the committed receipt must have atomicity appropriate to the storage architecture.
- Any validation, uniqueness, embedding-data, or persistence failure must roll back the entire domain transaction.
- Detect batch conflicts before mutation or guarantee a complete rollback.
- Use the prepared artifact as the only transaction input.
- Preserve current semantic-search interoperability for catalog entities and edges.

#### Exit criteria

- Cartesian provenance no longer exists.
- One source can support multiple targets, and one target can have multiple sources, through explicit links.
- Manifest membership is exact for created, updated, and unchanged objects.
- Fault injection between persistence steps leaves neither a partial graph nor a partial manifest.
- The committed receipt maps uniquely to a durable manifest.

---

### Phase 4 — Manifest-Backed Verification and Read-Only Diagnostics

**Goal:** Resolve, inspect, and verify batches from durable facts, including while catalog writes are disabled.

#### Work

- Separate feature gates:
  - The write gate controls prepare, commit, and upsert mutations.
  - The read/diagnostic gate is independent.
- `resolve_typed_entities`, edge resolution, manifest reads, evidence reads, verification, and status must continue to work when the write gate is disabled, unless the read gate is separately disabled.
- Add or complete:
  - `resolve_typed_edges`.
  - `get_catalog_batch_manifest`.
  - `get_catalog_evidence`.
  - Manifest-backed `verify_catalog_batch`.
- `verify_catalog_batch(batch_id)` must derive expected membership and counts from the manifest. It must never set expected values equal to the objects returned by the query being verified.
- Verification must detect at least:
  - Missing members.
  - Unexpected members.
  - UUID or type mismatches.
  - Endpoint mismatches.
  - Missing or malformed evidence.
  - Hash or version mismatches.
  - Missing embeddings, according to current server behavior.
- If embedding presence is always verified, document that behavior; do not add a meaningless flag that the server does not need.
- Read tools must provide:
  - Bounded limits.
  - Pagination or cursors where needed.
  - A compact default projection.
  - An optional detailed projection for audits.
- `get_catalog_ingest_status` and capability responses must report read and write readiness separately.

#### Exit criteria

- Manifest and evidence reads and batch verification still work when catalog writes are disabled.
- Simulated removal of a manifest member causes verification to fail with a precise diagnostic.
- Edge resolution returns an exact typed edge rather than relying on semantic search.
- Read responses are bounded and do not return the complete evidence payload by default.

---

### Phase 5 — Verification, Security, Compatibility, Observability, and Migration Documentation

**Goal:** Complete the final gates needed to decide whether the canary payload may be regenerated.

#### Work

##### 1. Verification suite

- Run the complete legacy and catalog test suites.
- Add unit and integration coverage for:
  - Strict and unknown fields.
  - FE/BO/COMMON identities and overloads.
  - Endpoint maps.
  - Canonical hashing.
  - Prepare/commit restart, replay, expiry, and concurrency.
  - Exact evidence.
  - Durable manifests.
  - Read/write gate separation.
  - Atomic rollback and fault injection.
  - Search interoperability.
  - Absence of LLM and queue calls in the deterministic path.
- Test Neo4j constraints, indexes, and migrations against both an empty database and a database with the old schema.

##### 2. Security and operational limits

- Validate token entropy, token hashing, expiry, and redaction.
- Enforce limits on request size, object count, evidence count, and prepared-artifact storage.
- Do not log raw tokens, credentials, embeddings, or the complete catalog payload at production log levels.
- Structured errors must not expose internal queries, stack traces, or database credentials.
- Add safe metrics and logging for:
  - Prepare and commit duration.
  - State transitions.
  - Commit retries and concurrency.
  - Expiry and cleanup.
  - Manifest verification failures.
  - Object and evidence counts.

##### 3. Compatibility and migration

- Write a migration guide from the current catalog contract to Catalog-v2.
- State explicitly that previous golden hashes and fixtures are invalidated by the new identity and hash-schema version.
- Do not preserve old hashes by excluding new fields.
- Document constraint and index creation, roll-forward, and rollback procedures.
- Any retained backward-compatible wrapper must have an explicit deprecation path and dedicated tests.
- Update MCP tool documentation, examples, and capability responses.

##### 4. Final pre-canary gate

- Produce a final implementation report containing:
  - Changed files and modules.
  - Contract and schema changes.
  - Database migration changes.
  - Tests executed and actual results.
  - Known limitations.
  - Security and operational limits.
  - Compatibility decisions.
  - `ready_to_regenerate_canary_payload: true|false`.
  - Specific reasons when the value is `false`.

#### Exit criteria

- All required tests pass, or every exception is explicitly explained and approved.
- No P0 or P1 blocker remains.
- Migration and rollback documentation is executable.
- Capability responses match the actual runtime behavior.
- The result may indicate readiness to **regenerate the canary payload**, but it must not execute the canary.

---

### Phase 6 — Canary as a Separate Task

This phase is outside the current coding roadmap. It may begin only after Phase 5 reports `ready_to_regenerate_canary_payload: true` and separate approval is granted.

The old canary must not be reused mechanically because identity, graph keys, request hashes, evidence, and manifest contracts have changed.

## 4. Requirement Tracking

The original roadmap contains 138 requirements:

| Original group | Count |
|---|---:|
| Phase 1 | 33 |
| Phase 2 | 27 |
| Phase 3 | 42 |
| Phase 4 | 20 |
| Phase 5 | 16 |
| **Total** | **138** |

Do not estimate new counts. Remap every existing requirement ID:

- Phase 0 is an entry gate and does not necessarily add product requirements.
- Evidence-contract requirements move from Phase 3 to Phase 2.
- The remaining Phase 3 requirements split between Phase 3A and Phase 3B.
- Phase 4 is renamed to reflect that Phase 3B already persists the durable manifest; Phase 4 reads and verifies it.
- The total must remain 138 requirement IDs after remapping unless a separately recorded change request modifies scope.

## 5. Out of Scope

Do not implement the following within this pre-canary task:

- Oracle dictionary extraction.
- SQL or PL/SQL parsing and static analysis.
- Relationship inference or scoring engines.
- Runtime transaction correlation.
- `get_object_context`, dependency-path, or impact-analysis tools.
- Delta ingestion, retirement, or tombstone lifecycle.
- Business transaction or concept ontology.
- Production data migration.
- Execution of a real canary.

Future-facing schema hooks may be defined when necessary, but they must not expand into out-of-scope implementation.

## 6. Mandatory Notes for the Coding Agent

1. **Inspect before coding.** Do not assume this roadmap perfectly matches the current source. Verify tool registrations, models, services, stores, migrations, and tests first.
2. **Preserve user changes.** Do not reset, overwrite, or edit unrelated files. Do not use destructive Git or filesystem commands.
3. **Do not run the canary.** This task ends with a pre-canary readiness report.
4. **Do not preserve old fixtures at any cost.** Catalog-v2 intentionally changes identity and hashing. Update fixtures to the new contract and record migration impact.
5. **Use one graph group with system-scoped identity.** Do not use group separation to avoid cross-system endpoint resolution.
6. **COMMON is not a fallback.** Ambiguous system ownership must fail or enter an explicit quarantine path with a clear diagnostic.
7. **Do not create ad hoc edges.** Every edge type and endpoint pair must be centrally registered and tested.
8. **Do not confuse evidence with fact.** Declared foreign keys, code references, and heuristic inferences must preserve different semantics and evidence.
9. **Never create Cartesian provenance.** Every evidence record must identify one exact source and target.
10. **Hash completely and stably.** Do not omit new fields to preserve an old golden value, and do not include transient metadata in the canonical hash.
11. **Commit only the prepared artifact.** Do not accept or merge a client payload in the commit path.
12. **Do not call external services during commit.** Embeddings and external validation must finish during prepare; commit must use the stored artifact.
13. **Treat the manifest as authoritative.** Verification must not derive expected values from the query result under verification.
14. **Keep read and write gates independent.** Disabling writes must not remove the ability to audit persisted state.
15. **Add tests in every phase.** Do not postpone tests for Phases 1–4 until Phase 5.
16. **Prefer safe migration.** Schema and constraint changes require forward migration, rollback guidance, and integration coverage.
17. **Stop and report when a product decision is required**, especially when:
    - The edge vocabulary has not been approved.
    - A destructive migration appears necessary.
    - The current storage design cannot guarantee atomicity or restart recovery.
    - Backward compatibility conflicts with the fail-closed v2 contract.
    - Baseline failures make regressions impossible to distinguish.
18. **Do not claim readiness without evidence.** Set `ready_to_regenerate_canary_payload=true` only when every exit criterion and required test has a verifiable result.

## 7. Required Final Report Format

```yaml
implementation_status: complete | partial | blocked
completed_phases:
  - phase_0
  - phase_1
  - phase_2
  - phase_3a
  - phase_3b
  - phase_4
  - phase_5
requirements:
  total_expected: 138
  mapped: 0
  implemented: 0
  verified: 0
tests:
  passed: 0
  failed: 0
  skipped: 0
compatibility_breaks: []
migrations_added: []
known_limitations: []
blockers: []
ready_to_regenerate_canary_payload: false
canary_executed: false
```

The agent must also list the commands and tests it actually ran, their results, and the reason for every skipped test or failure. `canary_executed` must not be set to `true` within this task.
