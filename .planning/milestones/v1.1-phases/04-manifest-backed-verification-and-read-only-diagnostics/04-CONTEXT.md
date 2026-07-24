# Phase 4: Manifest-Backed Verification and Read-Only Diagnostics - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Autonomous - all recommended options selected under standing user approval
**Worktree HEAD at gather:** `a4cac77fd7474bb827f119876cc573366ad199ab`
**Phase 3B product gate HEAD (retained):** `1f9a7d75551fe5d1c0260f831102d2a8c5b83e18`
**Historical 03B-06 live suite commit (preserved, never rewrite):** `a67789a04ca0cc2f2a56d7498c65be3460215f77`

<domain>
## Phase Boundary

Operators can inspect committed membership, evidence, and edges and verify batches from durable manifests while catalog mutation is disabled. Phase 4 completes public read/diagnostic surfaces only:

- `get_catalog_batch_manifest` - paginated durable membership read
- Manifest-backed batch-only path of `verify_catalog_batch` - expected membership/counts from committed manifest authority
- `resolve_typed_edges` - exact typed edge diagnostics
- `get_catalog_evidence` - group-isolated compact evidence read
- Split read/write feature gates with safe defaults
- Capabilities / registration / status compatibility for read tools while writes are off
- IDEN-08 completion: complete system-scoped graph keys on resolve, manifest, evidence, and verification responses

Phase 5 owns final security matrix, live isolation suite expansion, migration/operator docs, and readiness report. Canary execution, `oracle-catalog-v2` access, deployment, migration, graph clearing, existing-data deletion, push, and non-Neo4j portability remain out of scope.

Phase 4 does not redesign write paths, weaken Phase 3B atomic co-commit, invent membership from live row counts or `batch_id`, open write transactions on read paths, initialize/repair schema on reads, call embedders on reads, or claim portability beyond Neo4j 5.26+.

</domain>

<decisions>
## Implementation Decisions

### Manifest Read Surface and Pagination
- **D-01:** Add public `get_catalog_batch_manifest` as a read-only MCP tool. Input is group-scoped batch identity (`group_id` + `batch_id`) plus pagination controls. Output returns group ID, batch ID, request/catalog/artifact/manifest hashes, identity/canonicalization/catalog schema versions, exact category counts, and paginated compact item identities for entities, edges, sources, and evidence links - including unchanged shared entities.
- **D-02:** Membership order is the durable manifest canonical order already established by Phase 3B pure canonicalization (`services/catalog_manifest.py` category sort keys). Never re-sort by live graph discovery or `batch_id`. Pagination is offset/limit over that stable order (or an equivalent opaque cursor that encodes the same stable position). Repeat reads with the same params yield the same page contents for an unchanged manifest.
- **D-03:** Default projection is compact identities only (uuid, type/key, content hash, projected_status where present). Optional detailed audit projection may include bounded extra fields already stored on the manifest body; it never returns embeddings, raw prepared payload, source text, or credentials.
- **D-04:** Configure a non-zero `max_page_size` (config + hard ceiling) for manifest/evidence pagination. Current Phase 2/3 capabilities expose `HARD_MAX_PAGE_SIZE = 0` as explicit not-configured; Phase 4 replaces that zero authority with a conservative positive ceiling and reports it in capabilities limits. Fail closed on page size above configured/hard max.
- **D-05:** Missing, incomplete, hash-mismatched, or chunk-incoherent manifests fail closed. Do not synthesize membership from domain rows, evidence rows, or `entity.batch_id` / `edge.batch_id`.

### Batch-Only Manifest Authority for Verification
- **D-06:** When `verify_catalog_batch` is invoked with `batch_id` (batch-only or batch+keys), load the committed durable manifest as the sole expected membership and count authority (VERI-01/02). Expected counts come from manifest/status metadata, never from the number of physical rows returned by the live query under test.
- **D-07:** Batch verification reports missing manifest members and extra physical duplicates/drift as distinct diagnostics (VERI-03). It never normalizes extras away or treats live-row count as expected count.
- **D-08:** Verification checks exact entity type, deterministic entity UUID, exact edge type, deterministic edge UUID, endpoint UUIDs and graph keys, required name/fact embeddings presence, exact provenance/evidence-link identities and counts (EVID-13), and manifest hash/count consistency (VERI-04). Embedding presence is always verified for members that require embeddings under current server behavior; do not add a no-op optional flag.
- **D-09:** A committed catalog-v2 batch with no valid durable manifest fails with `manifest_mismatch` (VERI-05; code already registered in `CatalogErrorCode`). Incomplete chunk set, digest mismatch, or contradictory root/chunk metadata also map to fail-closed manifest mismatch / conflict - never silent partial verify.
- **D-10:** Explicit-key verification remains available and compatible (VERI-06). `batch_id` and/or explicit entity/edge keys remain valid scopes per existing `VerifyCatalogBatchRequest`. Explicit-key-only mode does not invent a fake batch manifest; batch-only mode does not drop explicit-key checks when both are supplied - keys still diagnose against live rows while expected membership for the batch remains manifest-backed.
- **D-11:** Verify never sets expected values equal to objects returned by the query being verified. Live reads are observations only; manifest (or explicit request keys) are expectations.

### Edge and Evidence Diagnostics
- **D-12:** Add `resolve_typed_edges` mirroring `resolve_typed_entities` patterns: request by allowlisted edge type + edge key (and system/group scope), return UUID, source/target UUIDs and graph keys, exact type, content hash, embedding presence, and anomaly tags. No semantic search.
- **D-13:** Edge resolution reports not-found, physical duplicates, type mismatch, endpoint mismatch, endpoint-pair violation, and deterministic UUID mismatch without repairing data (RESE-02). Fail closed; never rewrite edges.
- **D-14:** Add `get_catalog_evidence` as read-only compact evidence for one entity or edge target within `group_id`, with bounded pagination and optional excerpts (EVID-12). Default omits full excerpts/source payloads; optional excerpt flag remains length-bounded.
- **D-15:** Evidence and edge diagnostics are group-isolated, perform no embedding, open no write transaction, and remain usable when catalog writes are disabled (RESE-03, GATE-03/04).
- **D-16:** Complete IDEN-08: every resolve, manifest, evidence, and verification response surface that identifies a catalog entity exposes the complete system-scoped graph key (not a truncated or name-only form). Phase 1 model/service echo is foundation only; Phase 4 owns remaining response surfaces.

### Split Read/Write Gates and Safe Defaults
- **D-17:** Separate explicit feature gates (GATE-01):
  - **Write gate** (`catalog_upsert.enabled`, existing): controls prepare, commit, discard, and non-dry-run upsert mutations. Default remains **false**.
  - **Read/diagnostic gate** (new explicit config, e.g. `catalog_upsert.reads_enabled` or sibling field): controls catalog diagnostic tools. Default **true** so diagnostics work out of the box when identity namespace and Neo4j reads are available.
- **D-18:** `get_catalog_capabilities` remains callable whenever the MCP server is initialized, independent of write and read gates (GATE-02). It stays mutation-free and never probes with writes or schema init.
- **D-19:** When the write gate is false and the read gate is true (and namespace + Neo4j readable), these remain usable: `get_catalog_ingest_status`, `get_catalog_batch_manifest`, `resolve_typed_entities`, `resolve_typed_edges`, `verify_catalog_batch`, `get_catalog_evidence` (GATE-03). Write tools still return structured `feature_disabled` (or equivalent) without side effects.
- **D-20:** Fix `_read_gate` so it no longer requires `catalog_config.enabled` (write flag). Today `_read_gate` incorrectly couples reads to the write enable flag (`catalog_service.py`); Phase 4 must split that check. Read gate still requires valid configured UUID namespace for identity-bearing diagnostics and Neo4j backend.
- **D-21:** Read-only catalog operations never initialize, alter, or repair schema and never open write transactions (GATE-04). No embedder, LLM, queue, or external network call on read paths.
- **D-22:** Missing batch status is distinguishable via `found=false` (or explicit not-found state/code) and never masquerades as committed success or generic operational failure (GATE-05). Extend `CatalogIngestStatusResponse` (and any new read responses) so absence is not encoded solely as `status=failed` + `validation_error`.
- **D-23:** Every gated read and write retains complete `group_id` isolation (GATE-06). Tests use only `oracle-catalog-tool-test`. Never query or mutate `oracle-catalog-v2`.

### Capabilities, Registration, and Flags
- **D-24:** Capabilities report `catalog_writes_enabled` and `catalog_reads_enabled` separately and truthfully from config. Flip `features.manifest_verification` to true only after public manifest-backed verify registration + required proofs pass. Keep `features.manifests` true from Phase 3B persistence authority.
- **D-25:** Register new MCP tools with the same thin FastMCP + safe-error boundary pattern as existing catalog tools. Preserve all 14 legacy MCP tool names/contracts and existing catalog tool contracts (TEST-09). `get_status` remains compatible (additive only).
- **D-26:** Capabilities limits expose configured and hard `max_page_size` after D-04; no runtime read of `.planning/*` gate JSON to decide feature flags.

### Tests and Phase Gate
- **D-27:** TEST-08: manifest and resolver tests prove unchanged shared entities remain members, missing manifest items/count drift are detected, missing manifests fail with `manifest_mismatch`, and edge twins/endpoint mismatches are reported without repair.
- **D-28:** TEST-09: gate and registration tests prove read tools work while writes are disabled, all 14 legacy tools remain registered, all expected catalog-v2 tools are registered (including new Phase 4 tools), and `get_status` remains compatible.
- **D-29:** Unit/service/store coverage for pagination stability, manifest authority vs live-row observation, explicit-key compatibility, evidence pagination, read-gate defaults, no schema/write/embed on reads, and `found=false` missing status.
- **D-30:** Live Neo4j proofs (when available) stay on `oracle-catalog-tool-test` only; no canary, no deploy, no clear/delete, no push. Preserve historical audit commit `a67789a` as immutable evidence of 03B-06 live green - do not amend, rebase, or delete it.
- **D-31:** Phase 5 remains blocked until a fail-closed Phase 4 gate reports manifest reads, manifest-backed verify, edge/evidence diagnostics, split gates, registration, and isolation green.

### Claude Discretion
- Exact request/response Pydantic model field names for new tools, page cursor encoding, and anomaly list shapes - provided they stay strict, bounded, and secret-free.
- Smallest service/store method extraction for manifest reassembly reads (reuse create-once root/chunk loaders already on `CatalogNeo4jStore`).
- Exact config field name for the read gate and env mapping, as long as default is safe (reads on, writes off) and documented in capabilities.
- Whether verify response gains dedicated evidence/manifest sections vs extending existing anomaly lists - must still satisfy EVID-13 and VERI-03/04.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone and Phase Contract
- `.planning/ROADMAP.md` Phase 4 - goal, success criteria, dependency on Phase 3B, research note (manifest property size vs chunk children, verify pagination).
- `.planning/REQUIREMENTS.md` - IDEN-08, MANI-05, VERI-01..06, RESE-01..03, GATE-01..06, EVID-12..13, TEST-08..09.
- `.planning/graphiti_mcp_pre_canary_roadmap_en.md` Phase 4 - separate gates; manifest as expected authority; never set expected = observed; bounded projections; exit criteria.

### Prior Locked Authorities
- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-CONTEXT.md` - strict contracts, catalog-v2 identity, safe errors, no caller UUID authority.
- `.planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-CONTEXT.md` - endpoint map, evidence schema, hashes, mutation-free capabilities.
- `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-CONTEXT.md` - frozen artifact, token lifecycle, zero-external commit seam.
- `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md` - durable manifest root/chunks, exact evidence, shared atomic writer, Phase 4 boundary (D-22, D-33, deferred reads).
- `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-VERIFICATION.md` - Phase 3B complete; ready_for_phase_4.
- `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-GATE-RESULTS.json` - final HEAD-bound Phase 3B hard-gate authority.
- Historical live suite commit `a67789a04ca0cc2f2a56d7498c65be3460215f77` - preserve; do not rewrite history around this audit.

### Existing Code Boundaries
- `mcp_server/src/services/catalog_service.py` - `_read_gate` (currently write-coupled), `resolve_typed_entities`, pre-Phase-4 `verify_catalog_batch`, `get_catalog_ingest_status` missing-status shape.
- `mcp_server/src/services/catalog_store.py` - `CatalogBatchManifest` / chunk create-once Cypher, `build_existing_manifest_root_cypher`, `build_list_manifest_chunks_cypher`, evidence write helpers; Phase 4 adds matching **read** paths only.
- `mcp_server/src/services/catalog_manifest.py` - pure membership canonicalize/chunk/hash; stable category order is pagination authority.
- `mcp_server/src/services/catalog_capabilities.py` - `catalog_writes_enabled` / `catalog_reads_enabled`; `features.manifest_verification` still false until Phase 4 proofs; `HARD_MAX_PAGE_SIZE = 0` to replace.
- `mcp_server/src/models/catalog_entities.py` - `ResolveTypedEntitiesRequest`, `VerifyCatalogBatchRequest` (batch and/or explicit keys), explicit key refs.
- `mcp_server/src/models/catalog_responses.py` - resolve/verify/status/capabilities response shells; status missing currently uses failed/validation_error.
- `mcp_server/src/models/catalog_common.py` - `CatalogErrorCode.manifest_mismatch` and shared limits.
- `mcp_server/src/config/schema.py` - `CatalogConfig.enabled` write gate default false; add explicit read gate.
- `mcp_server/src/graphiti_mcp_server.py` - thin FastMCP registration; existing resolve/verify/status/capabilities/upsert/prepare/commit/discard tools.
- `graphiti_core/driver/neo4j_driver.py` - real async transactions; reads must not open write txs.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `resolve_typed_entities` already proves read-only typed diagnostics: no embedder, no schema init, anomaly taxonomy (missing, wrong_type, generic/typed duplicate, uuid_mismatch, missing_embedding).
- `verify_catalog_batch` already accepts batch_id and/or explicit keys and runs store match helpers; Phase 4 rewires **batch expected membership** to durable manifest rather than live discovery or request-only keys.
- Phase 3B `catalog_manifest.py` + store root/chunk writers provide deterministic membership bytes and create-once identities; public reads reassemble from the same records.
- `build_catalog_capabilities` already exposes separate read/write booleans and feature flags; only gate wiring and `manifest_verification` / page size need Phase 4 truth.
- `CatalogErrorCode.manifest_mismatch` already exists for VERI-05.

### Established Patterns
- Thin MCP wrappers -> `CatalogService` -> fixed Cypher on `CatalogNeo4jStore`; no client label interpolation.
- Control records (`CatalogBatchManifest`, chunks, evidence) never carry `Entity` or searchable embeddings.
- Structured errors and bounded logs: IDs and counts only; never tokens, payloads, source text, credentials, raw exceptions.
- Group isolation on every query; test group `oracle-catalog-tool-test` only.

### Integration Points
- Split `_read_gate` from write `enabled`; introduce read-config default true.
- New store read methods for manifest root+ordered chunks+membership page and evidence-by-target; reuse integrity checks from write-side idempotent loaders where pure.
- Extend verify path: if `batch_id` present -> load manifest -> set expected members/counts -> observe live rows -> diff.
- Register `get_catalog_batch_manifest`, `resolve_typed_edges`, `get_catalog_evidence`; keep existing tool names.
- Flip capabilities `manifest_verification` only after tests/gate evidence.

### Known Gaps Phase 4 Must Close
- `_read_gate` returns `feature_disabled` when `catalog_upsert.enabled` is false - violates GATE-03 until split.
- `get_catalog_ingest_status` maps missing row to `status=failed` + `validation_error` - violates GATE-05 `found=false` distinguishability until fixed.
- No public manifest/evidence/edge-resolve tools yet; `features.manifest_verification` is false by design until this phase.
- Capabilities `max_page_size` hard/configured currently zero - pagination not actually configured.

</code_context>

<specifics>
## Specific Ideas

- Prefer offset/limit over the durable canonical member list first; add opaque cursors only if needed for API stability.
- Reuse `resolve_typed_entities` anomaly vocabulary for edges where meanings align; add edge-specific tags for endpoint-pair and endpoint mismatch.
- Keep verify response backward-compatible: additive evidence/manifest sections preferred over breaking field renames.
- User pre-approved every recommended discussion option. Transient parser/internal errors may be retried or ignored only when product, security, validation, and hard-gate truth remain intact. Stop on real contract conflict.

</specifics>

<deferred>
## Deferred Ideas

- Final security/compatibility matrix, full live isolation expansion, operator/migration docs, offline canary-artifact regeneration, final readiness report with `canary_executed=false`: Phase 5.
- `LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`, automatic catalog-v1 migration, parser/extraction, new business entities, non-Neo4j portability: future/out of scope.
- Canary execution, `oracle-catalog-v2` access, production migration, deployment, graph clearing, existing-data deletion, push/merge/tag: separate explicit approval only.
- Long-term manifest retention/cleanup jobs and advanced observability dashboards: not Phase 4.

</deferred>

---

*Phase: 04-manifest-backed-verification-and-read-only-diagnostics*
*Context gathered: 2026-07-19*

