# Project Research Summary

**Project:** Deterministic Catalog Ingestion for Graphiti MCP — v1.1 Catalog-v2 Pre-Canary Hardening
**Domain:** Deterministic Neo4j catalog MCP control plane (identity, prepare/commit, manifests, verification)
**Researched:** 2026-07-17
**Confidence:** HIGH

## Executive Summary

v1.1 hardens the shipped v1.0 deterministic catalog MCP surface before any regenerated canary. Experts build this as an additive administrative path beside Graphiti semantic tools: Pydantic-strict contracts, server-owned allowlists and endpoint maps, UUIDv5 identity, SHA-256 audit, Neo4j real transactions, embeddings outside domain writes, non-Entity control labels. Zero new runtime dependencies — extend installed Pydantic 2.11.x, neo4j 5.28.x, FastMCP, stdlib, and existing CatalogService / CatalogNeo4jStore.

Approved prepare/commit contract (authoritative): `prepare_catalog_batch` validates/resolves/projects and persists a **bounded immutable canonical payload** server-side (restart-safe; chunked non-Entity control nodes if needed; **hashes/counts alone insufficient**). Commit clients send **only a token**. Prepare does **not** compute required embeddings. `commit_prepared_catalog_batch` embeds from the stored payload **before** opening its domain transaction, then writes **domain data + evidence + manifest + terminal batch status + plan terminal state in one Neo4j transaction** where supported. A separate post-rollback failure-status transaction is allowed **only** for failure reporting. Exact tools: `prepare_catalog_batch`, `commit_prepared_catalog_batch`, `discard_prepared_catalog_batch`, `get_catalog_capabilities`, `get_catalog_evidence`, `get_catalog_batch_manifest`, `resolve_typed_edges`.

Key risks: silent v1 to v2 rekey; open nested validation; incomplete hashes; Cartesian provenance; hashes-only prepare; embed-at-prepare; split success txs without co-committed manifest; gate confusion; live-group/canary writes. Mitigate with fail-closed FE/BO grammar, recursive extra=forbid, server endpoint maps, explicit evidence links, full payload prepare, embed-at-commit, single success tx, split read/write gates, tests only on `oracle-catalog-tool-test`. Catalog-v2 **intentionally breaks** seven deterministic request identity/provenance/hash contracts where required; preserve **tool names** and legacy semantic tools — do **not** claim old catalog-v1 request payloads remain accepted. No canary, production/live-group writes, parser/inference, or automatic v1 migration this milestone.

## Key Findings

### Recommended Stack

Add **no** new packages. Reuse Python 3.10+, Pydantic 2.11.x (`ConfigDict(extra='forbid', strict=True)` on every nested model), neo4j async driver + real txs, FastMCP additive tools, stdlib uuid/hashlib/hmac/secrets/json, existing embedder **at commit only** for prepared batches, non-Entity control nodes mirroring CatalogIngestBatch.

**Core technologies:**
- **Pydantic 2.11.x:** recursive fail-closed contracts — nested extra does not inherit
- **Neo4j 5.26+ / driver 5.28.x:** MERGE + composite UNIQUE + one success write unit
- **stdlib secrets/hmac:** opaque prepare tokens; store digest only
- **Existing CatalogNeo4jStore:** domain Cypher + control labels; no EntityNode.save for catalog
- **pydantic-settings CatalogConfig:** split write vs read/capabilities gates

### Expected Features

**Must have (table stakes):**
- Strict recursive request contracts + immutable execution flags
- Catalog-v2 FE/BO/COMMON identity grammar (fail closed; `unsupported_identity_schema`, `invalid_system_key`)
- Server-owned edge endpoint maps (`edge_endpoint_pair_not_allowed`)
- Authoritative combined batch hashes + `get_catalog_capabilities` (works after server init even if writes disabled)
- Prepare/commit/discard with full payload + token protocol (exact tool names above)
- Explicit evidence links (no Cartesian) + `provenance_link_conflict`
- Durable manifests + manifest-backed verification (`manifest_mismatch`)
- `resolve_typed_edges`, `get_catalog_evidence`, `get_catalog_batch_manifest`
- Split read/write gates; legacy tool names + semantic tools preserved
- Plan codes: `prepared_plan_not_found`, `prepared_plan_expired`, `prepared_plan_conflict`, `prepared_plan_already_consumed`

**Should have (trust differentiators):**
- Capabilities as versioned contract surface (maps, grammar, hash recipe, limits)
- Manifest as post-restart verification authority
- Read diagnostics while mutation disabled

**Defer (not v1.1):**
- Parser / inference / path-impact APIs
- Automatic v1 to v2 migration; canary execution; production writes
- FalkorDB catalog claims; full 14k ingest; K8s deploy

### Architecture Approach

Additive MCP tools on shared CatalogService / CatalogNeo4jStore. Domain labels remain searchable Entity/RELATES_TO; control plane uses non-Entity CatalogIngestBatch, CatalogPreparedPlan (+ payload chunks), CatalogBatchManifest, optional CatalogEvidenceLink. Ordering: validate → endpoint map → UUIDv5 → domain hash → prepare stores payload **or** commit embeds then one success tx. No LLM/queue/add_episode on catalog path.

**Major components:**
1. **Models (catalog_*):** recursive forbid; FE/BO grammar; evidence/manifest DTOs
2. **Identity + endpoint map:** UUIDv5 name material; frozen server maps; full-domain SHA-256
3. **Plan/manifest modules:** immutable payload lifecycle; token mint/verify; manifest assembly
4. **CatalogService:** gates; prepare/commit/discard; resolve/verify modes
5. **CatalogNeo4jStore:** domain MERGEs + control CRUD + CAS; no conflict repair

### Critical Pitfalls

1. **Silent v1 to v2 rekey** — fail closed on non-v2 keys; no auto-migration
2. **Nested validation open** — extra=forbid on every nested model + service re-validate
3. **Hash field omissions** — single versioned canonicalizer covering all domain collections
4. **Hashes-only prepare / embed-at-prepare** — full payload store; embed only at commit
5. **Split success txs / Cartesian evidence / gate-kills-reads** — one success tx; explicit links; split gates; no live/canary writes

## Implications for Roadmap

### Phase 1: Strict contracts + FE/BO identity grammar
**Rationale:** All later work depends on fail-closed payloads and collision-free UUIDs
**Delivers:** Recursive forbid/strict models; FE/BO/COMMON grammar; immutable flags; unit vectors
**Addresses:** Strict contracts; identity isolation
**Avoids:** Silent rekey; open nested extras
**Error codes:** `validation_error`, `unsupported_identity_schema`, `invalid_system_key`, `graph_key_prefix_mismatch`

### Phase 2: Endpoint maps + authoritative hashing + capabilities
**Rationale:** Preflight topology and complete hashes before control-plane writes
**Delivers:** Server EDGE_ENDPOINT_MAP; full-domain hash; `get_catalog_capabilities` (init-success even if writes off); map wired into edge/batch preflight
**Addresses:** Endpoint authority; capabilities; hash completeness
**Avoids:** Client maps; false idempotence
**Error codes:** `edge_endpoint_pair_not_allowed`, `content_hash_mismatch`, `endpoint_type_mismatch`

### Phase 3: Prepare/commit/discard + explicit evidence
**Rationale:** Restart-safe multi-step ingest is the core v1.1 protocol
**Delivers:** Full payload prepare; token; `commit_prepared_catalog_batch` (embed-then-one-tx); discard; explicit evidence links; CAS/TTL
**Addresses:** Prepare protocol; evidence; concurrency
**Avoids:** Domain-at-prepare; hashes-only plan; Cartesian product; dual success txs
**Error codes:** `prepared_plan_*`, `provenance_link_conflict`, `embedding_failed`, `batch_conflict`

### Phase 4: Manifests + manifest verify + split gates + edge resolve
**Rationale:** Audit/restart truth and safe ops posture
**Delivers:** Durable manifest co-committed; `get_catalog_batch_manifest` / `get_catalog_evidence`; manifest-backed verify; `resolve_typed_edges`; read vs write gates
**Addresses:** Manifests; diagnostics under write-disable
**Avoids:** Verify-by-client-list false green; single flag killing reads
**Error codes:** `manifest_mismatch`, `feature_disabled` (writes only)

### Phase 5: Exhaustive tests, security, compatibility, docs
**Rationale:** Gate milestone without canary execution
**Delivers:** Unit/service/store/MCP/concurrency/Neo4j/security/compat suites on `oracle-catalog-tool-test`; isolation probes; migration + canary procedure docs only
**Addresses:** Compatibility; logging; isolation
**Avoids:** Live `oracle-catalog-v2` mutation; payload/token logs; tool renames

### Phase Ordering Rationale

- Contracts/identity before maps/hashes (invalid keys must not reach store)
- Maps/hashes/capabilities before prepare (plan identity incomplete otherwise)
- Full payload prepare before commit (commit is pure apply of frozen plan)
- Manifest/verify after commit path exists
- Security/compat continuous but final gate is isolation + docs without canary

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3:** payload chunking property limits; single-tx size under defaults; token CAS details
- **Phase 4:** manifest property size vs chunk children; verify pagination

Phases with standard patterns (skip research-phase):
- **Phase 1:** Pydantic forbid/strict patterns already verified
- **Phase 2:** frozenset maps + existing canonical_sha256
- **Phase 5:** extend v1.0 test/doc patterns

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Local pins + Neo4j/Pydantic docs; zero-new-deps clear |
| Features | HIGH | PROJECT.md v1.1 + operator contracts; approved tool/error names applied |
| Architecture | HIGH | Live catalog modules + approved prepare/commit atomicity contract |
| Pitfalls | HIGH | Grounded in v1.0 store/service + v1.1 failure modes |

**Overall confidence:** HIGH

### Gaps to Address

- Exact FE/BO graph_key grammar string format: freeze in phase design (plane segment placement, overload signature normalization)
- Neo4j property size for max batch payload: plan chunk schema + limits in Phase 3 planning
- Whether legacy seven tools accept any v2-only fields additively: document fail-closed vs additive optional fields per tool without claiming v1 payloads remain valid under v2 grammar
- Hash recipe version string for protocol bump on coverage change

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md` — v1.1 active requirements, constraints, out-of-scope
- Approved milestone contract (prepare payload, embed-at-commit, one success tx, tool names, error codes, no canary/migration)
- Live `mcp_server` catalog identity/service/store and models
- Pydantic ConfigDict / Neo4j 5 constraints and MERGE docs
- Parallel research STACK, FEATURES, ARCHITECTURE, PITFALLS (2026-07-17), corrected in synthesis

### Secondary (MEDIUM confidence)
- v1.0 milestone verification artifacts (CAS, embeddings-before-tx, isolation patterns to retain)

### Tertiary (LOW confidence)
- Exact chunk sizing thresholds for prepare payloads — validate against Neo4j property limits in Phase 3

---
*Research completed: 2026-07-17*
*Ready for roadmap: yes*
