# Phase 1: Strict Contracts and Catalog-v2 Identity - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning
**Mode:** Autonomous — recommended options pre-approved by user

<domain>
## Phase Boundary

Deliver fail-closed catalog-v2 request contracts, complete FE/BO/COMMON entity identity grammar, explicitly versioned deterministic identity material, safe structured errors, and focused unit gates. No new store/control-plane write path, canary execution, live-group access, automatic catalog-v1 migration, endpoint-map implementation, evidence persistence, prepared-plan storage, manifest write, or deployment belongs in this phase.

</domain>

<decisions>
## Implementation Decisions

### Strict Request Contracts
- Introduce one shared strict Pydantic base with `ConfigDict(extra='forbid')`; every deterministic catalog request and nested request model inherits it.
- Unknown and misspelled fields fail at their exact nested field paths; validators preserve submitted bytes for source/hash-bearing text rather than stripping or normalizing them.
- Keep `strict_endpoints` and `atomic` only as enforceable `Literal[True]` contracts; `false` is rejected during model validation.
- Validate the entire request before service access; invalid requests cannot trigger DB reads, embeddings, schema initialization, transactions, status writes, queueing, or LLM calls.

### Catalog-v2 Scope and Grammar
- Every domain request declares exactly `identity_schema_version='catalog-v2'` and required canonical `system_key` from `FE`, `BO`, or `COMMON`.
- Graph keys visibly include system scope and fully qualified database identity. Use one server-owned registry of exact per-entity-type grammars, not prefix-only checks.
- Add only `System`, `DatabaseLink`, and `SourceArtifact` to the entity allowlist. Add no business-domain entities.
- Procedure and Function grammar includes a stable explicit overload discriminator; package and standalone overloads cannot collapse.

### Ownership Rules
- FE and BO objects with otherwise identical Oracle names remain in one `group_id` but have different graph keys and UUIDs.
- `COMMON` is accepted only when explicitly supplied by an authoritative caller under the request contract. Unknown ownership fails; it never defaults to `COMMON`.
- Nested entity and endpoint references must carry compatible version/system scope and exact graph-key grammar.
- Empty, non-canonical, overlong, mismatched, or unknown `system_key` fails as `invalid_system_key` before side effects.

### Deterministic Identity
- Entity UUID material is `group_id|catalog-v2|entity_type|graph_key`; equivalent explicit `catalog-v2` material applies to edge, source, mentions/evidence, batch, manifest, and prepared-plan identity helpers as those helpers exist or are introduced in their owning phases.
- Caller UUIDs remain absent from authority-bearing request contracts and never override server-derived UUIDv5 values.
- Catalog-v1 graph keys, UUID material, payloads, hashes, and historical ACCEPT_TAB goldens are rejected or treated as offline evidence only; no automatic normalization, re-keying, or rewrite exists.
- Preserve tool names. Catalog-v2 request breakage is explicit and documented through required version fields and tests.

### Structured Errors
- Extend the fixed error registry with the Phase 1 required codes without removing existing codes.
- Validation/service errors expose bounded non-sensitive `code`, `message`, `field_path` when applicable, `retryable`, and safe correlation ID.
- No stack trace, full exception, payload, source text, credential, auth header, or raw secret appears in responses or logs.
- Failures use deterministic precedence: schema/version/system/grammar validation before any backend/provider/readiness error.

### Unit Gate
- Add table-driven unit tests for recursive strictness, misspelled optionals, literal flags, all entity grammars, FE/BO separation, overload separation, catalog-v1 rejection, UUID versioning, caller-UUID non-authority, safe errors, and no-side-effect precedence.
- Phase 2 remains blocked until the Phase 1 focused unit gate passes. Baseline failures from Phase 0 remain separately recorded and are not repaired unless Phase 1 directly causes them.
- Tests use `oracle-catalog-tool-test` only; no test queries or mutates `oracle-catalog-v2`, and no canary runs.

### Claude's Discretion
- Choose the smallest module split that centralizes strict model configuration and grammar/identity authority without broad refactoring of the MCP monolith.
- Choose exact delimiter and regex syntax for each graph-key grammar, provided the documented examples, complete type coverage, visible system scope, overload stability, and fail-closed behavior are preserved.
- Choose whether safe structured validation conversion sits in model helpers or the thin MCP boundary, favoring one reusable path over duplicate wrappers.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mcp_server/src/models/catalog_common.py` already owns entity/edge allowlists, limits, protected properties, SHA-256 format, and `CatalogErrorCode`.
- Catalog request models are split across `catalog_entities.py`, `catalog_edges.py`, `catalog_batch.py`, `catalog_provenance.py`, and response models.
- `mcp_server/src/services/catalog_identity.py` is a pure deterministic identity/hash module with no network, DB, LLM, embedder, or queue dependencies.
- `CatalogService` already separates identity/hash preparation, pre-read, embedding, schema, and transaction stages; unit tests have spies/mocks for side-effect ordering.
- Phase 0 provides `00-COMPATIBILITY-POLICY.md`, `00-ISOLATION-POLICY.md`, `00-baseline-checks.json`, and `00-PHASE0-GATE.md` as entry constraints.

### Established Patterns
- Pydantic field/model validators enforce trust-boundary validation; pytest parametrization covers matrices.
- Fixed server allowlists prevent Cypher schema injection.
- Catalog service logs bounded batch IDs/counts and exception type names, not payloads.
- UUIDv5 uses a configured immutable namespace; canonical SHA-256 rejects non-finite values.
- MCP tool wrappers remain thin and preserve seven catalog tool names.

### Integration Points
- Strict base and grammar registry feed all catalog models.
- Identity helper signature changes affect `CatalogService`, canary builders/tests, model/service/store/live tests; compatibility fixtures must be regenerated offline, never executed.
- Error registry and safe error response shape affect response models and MCP validation/error boundaries.
- Phase 1 unit report becomes the hard gate consumed by Phase 2 planning/execution.

</code_context>

<specifics>
## Specific Ideas

- Canonical examples include `TABLE::FE::<DATABASE>.<SCHEMA>.<TABLE>`, `PACKAGE::FE::<DATABASE>.<SCHEMA>.<PACKAGE>`, and versioned Procedure/Function overload identities.
- The user pre-approved every recommended option. Ignore malformed GSD projection/internal errors only when they do not weaken product, test, security, or hard-gate truth.

</specifics>

<deferred>
## Deferred Ideas

- Edge endpoint-pair map, request hashing, evidence contract, and capabilities: Phase 2.
- Prepared-plan storage/token lifecycle: Phase 3A.
- Atomic domain/evidence/manifest commit: Phase 3B.
- Manifest-backed verification/read diagnostics: Phase 4.
- Canary execution: separate Phase 6 approval.
- Automatic catalog-v1 migration and new business entity types: out of scope.

</deferred>
