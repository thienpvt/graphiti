# Phase 2: Topology Authority, Evidence Contract, Hashes, and Capabilities - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning
**Mode:** Autonomous — recommended options pre-approved by user

<domain>
## Phase Boundary

Deliver one server-owned finite endpoint-pair authority for all 16 approved catalog edge types, freeze an explicit one-source/one-target CatalogEvidenceLink contract, establish versioned authoritative catalog-v2 request hashing, expose mutation-free catalog capabilities, and prove these contracts through focused unit gates. No prepared-plan persistence, token lifecycle, domain/evidence/manifest write redesign, manifest-backed verification, canary execution, live `oracle-catalog-v2` access, migration, or deployment belongs in this phase.

</domain>

<decisions>
## Implementation Decisions

### Endpoint Topology Authority
- Define one immutable server registry containing every allowed `(source_entity_type, target_entity_type)` pair for all 16 approved edge types; all request models, standalone/batch preflight, future prepare/commit, verification, resolution, capabilities, and tests consume it.
- Validate edge type and endpoint pair from request data before endpoint DB reads when possible, always before embeddings, schema initialization, transactions, status writes, queueing, or LLM calls; reject with `edge_endpoint_pair_not_allowed`.
- Keep `ForeignKeyTo` Column-to-Column canonical. Retain Table-to-Table only if existing compatibility evidence requires it, then document and test it as a distinct explicit pair.
- Keep broad semantic edge families finite: executable pairs for `Calls`; explicit code-unit/derived-object sources for `ReadsFrom`/`WritesTo`; documented Table/View/MaterializedView/Column pairs for `JoinsWith`; enumerated maps for `DependsOn`, `ReferencesByCode`, and `DerivedFrom`.
- Enforce special invariants in the same authority: Trigger source for `TriggerOn`, Synonym source for `SynonymFor`, DictionaryDocument/SourceArtifact targets for `DocumentedBy`, Sequence target for `UsesSequence`, and documented evidence requirement for `EnforcedBy`.
- Leave `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` unregistered. Unknown edge types or pairs fail closed; clients cannot widen or replace the registry.

### Explicit Evidence Contract
- Replace the catalog-v2 Cartesian provenance input with `CatalogEvidenceLink`: exactly one `source_key`, one exclusive typed entity-or-edge target, allowlisted evidence kind, bounded locator/excerpt/extractor/rule metadata, finite confidence, optional lowercase SHA-256.
- Entity targets carry exactly `entity_type` and `graph_key`; edge targets carry exactly `edge_type` and `edge_key`. Mixed, empty, ambiguous, or incomplete targets fail recursive validation.
- Evidence kinds are exactly `oracle_dictionary`, `ddl`, `view_sql`, `plsql_source`, `comment`, and `manual`.
- Preserve source and excerpt bytes used for hashing; apply explicit string, collection, depth, node-count, finite-number, and format bounds at model validation.
- Give each evidence link a catalog-v2 UUIDv5 identity and canonical content hash through pure identity helpers. One request entry means one explicit source-to-target link; duplicates may be normalized only when byte-identical.
- Reject the legacy multi-source/multi-target Cartesian shape. Do not auto-convert it. Persistence and exact-target resolution remain Phase 3B.

### Authoritative Hash Contract
- Require `catalog_sha256` as lowercase 64-hex on every combined catalog batch, including dry-run.
- Compute `request_sha256` from a version-tagged canonical payload containing identity schema version, canonicalization version, group ID, batch ID, catalog hash, and every canonical entity, edge, provenance-source, and evidence-link field.
- Exclude only documented transport/execution fields: `dry_run`, caller audit hash, generated timestamps, retry counters, and future plan tokens.
- Make canonical collection ordering deterministic and semantically order-invariant while retaining multiplicity where contractually meaningful. Changing any included field or `catalog_sha256` changes the digest; excluded fields do not.
- Use one canonicalization-version constant and reusable canonical JSON recipe for request, item, prepared payload, evidence, and future manifest hashing.
- Treat caller `request_sha256` as audit-only exact-match input; mismatch returns `content_hash_mismatch`. Never let it become identity or write authority.
- Return `identity_schema_version`, `canonicalization_version`, server `request_sha256`, `catalog_sha256`, and deterministic `batch_uuid` from every batch response, including dry-run and safe failures where derivable.

### Read-Only Capabilities
- Add `get_catalog_capabilities` as a read-only MCP tool available after server initialization even when catalog writes are disabled or UUID write prerequisites are incomplete.
- Return package/server version, backend, safely determined connectivity state, read/write gate states, namespace-configured boolean, and a non-reversible namespace fingerprint; never expose the raw namespace or secrets.
- Return identity/canonicalization/catalog schema versions; entity prefix/grammar registry; edge registry; complete endpoint map; configured limits plus immutable hard limits.
- Report embedding configuration/readiness and Neo4j index/vector readiness only when safely knowable without mutation. Unknown state remains explicit rather than triggering setup or writes.
- Report support flags for prepare/commit, explicit evidence links, manifests, and manifest verification truthfully according to implemented phase state.
- Preserve `get_status.status` and `get_status.message` exactly; any capability summary is additive only.

### Phase 2 Gate
- Add exhaustive table-driven tests for every allowed and representative rejected pair across all 16 edge types, shared-authority use, deferred edge rejection, and pre-side-effect ordering.
- Add hash mutation tests covering every included domain field, stable excluded fields, ordering rules, catalog-hash sensitivity, caller mismatch, and dry-run authoritative hashes with zero writes.
- Add recursive evidence tests for exclusive targets, allowlisted kinds, bounds, finite confidence, deterministic UUID/hash, no Cartesian input, and safe errors.
- Add capabilities tests for disabled writes, missing namespace, non-Neo4j/readiness unknown states, no mutation, secret redaction, complete registries/limits/features, tool registration, and `get_status` compatibility.
- Tests use only `oracle-catalog-tool-test`; never query or mutate `oracle-catalog-v2`; never run the canary. Phase 3A remains blocked until this focused gate passes truthfully.

### Claude's Discretion
- Choose the smallest module split that makes topology, canonicalization, and capability metadata single-source authorities without broad MCP-server refactoring.
- Choose exact evidence locator structure and hard bounds, favoring strict flat typed models over open dictionaries.
- Choose namespace fingerprint algorithm and display length, provided it is one-way, stable, domain-separated, non-secret, and tested not to expose the UUID namespace.
- Choose deterministic collection sort keys, provided every supported item has an unambiguous canonical identity and tests prove order invariance plus multiplicity behavior.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mcp_server/src/models/catalog_common.py` owns strict-model behavior, entity/edge allowlists, limits, SHA-256 validation, and `CatalogErrorCode`.
- `mcp_server/src/models/catalog_edges.py`, `catalog_provenance.py`, and `catalog_batch.py` contain the current typed request boundaries to harden.
- `mcp_server/src/services/catalog_identity.py` provides pure UUIDv5 and canonical SHA-256 helpers and is the natural home for versioned evidence/hash material.
- `mcp_server/src/services/catalog_service.py` already separates request hashing, gate checks, endpoint preflight, dry-run projection, embeddings, and transaction work.
- Existing service/store/MCP tests provide spies for DB, embedder, queue, LLM, schema, transaction, and registration side effects.

### Established Patterns
- Fixed allowlists and strict Pydantic models guard trust boundaries; validators must run before service/backend access.
- Catalog UUIDs remain server-derived from one configured namespace and catalog-v2 domain-separated material.
- `CatalogService.batch_request_sha256()` currently canonicalizes batch content; Phase 2 replaces its incomplete/legacy recipe rather than adding a parallel hash path.
- Current provenance batching multiplies sources by target arrays; catalog-v2 must remove that shape instead of preserving an implicit compatibility adapter.
- Thin FastMCP wrappers delegate to `CatalogService`; structured responses avoid raw exceptions and sensitive payload logging.

### Integration Points
- The endpoint registry feeds edge models, `CatalogService.upsert_typed_edges`, `upsert_catalog_batch`, future prepare/commit, resolver/verification code, capabilities, and tests.
- Evidence models and identity helpers affect batch models now, then Phase 3B persistence and Phase 4 reads/verification.
- Hash response fields affect batch response models, MCP wrappers, service tests, canary fixture builders, and offline docs; historical ACCEPT_TAB hashes remain evidence only.
- Capability construction integrates config schema, initialized client/driver state, catalog registries, FastMCP registration, and backward-compatible `get_status`.

</code_context>

<specifics>
## Specific Ideas

- The user pre-approved every recommended option for discussion. Ignore malformed GSD parser projections and transient internal errors only when product contracts, security, tests, or hard-gate truth remain intact.
- Prefer generated capability views directly from immutable registries/constants so documentation and runtime behavior cannot drift.

</specifics>

<deferred>
## Deferred Ideas

- Prepared-plan storage, opaque tokens, TTL/CAS, and discard: Phase 3A.
- Evidence persistence, exact target resolution, atomic domain/evidence/manifest co-commit: Phase 3B.
- Evidence reads and manifest-backed verification/resolution: Phase 4.
- `LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`, automatic catalog-v1 migration, and backend portability: out of scope.
- Canary execution and any `oracle-catalog-v2` access: separate Phase 6 approval.

</deferred>
