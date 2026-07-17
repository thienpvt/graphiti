# Roadmap: Deterministic Catalog Ingestion for Graphiti MCP

## Overview

v1.1 hardens the shipped deterministic catalog MCP surface before any regenerated canary. Work continues from v1.0 (Phases 1–2 complete) as Phases 3–7: baseline and compatibility policy; fail-closed catalog-v2 contracts and identity; server endpoint maps, exact evidence schema, authoritative hashes, and capabilities; immutable prepare/commit with prepare-time embeddings and co-committed manifests; durable diagnostics and verification; then exhaustive security, compatibility, canary-workflow migration, and documentation. A cherry-picked pre-hardening canary workflow records an ACCEPT_TAB dry-run and commit in `oracle-catalog-v2`; v1.1 treats those repository artifacts as historical evidence only and never queries, mutates, retries, or reuses that live group/hash. No canary execution, automatic v1→v2 migration, deployment, or multi-backend claims.

## Shipped Milestones

- [x] **v1.0 — Deterministic Catalog Ingestion** — Shipped 2026-07-17

| Phase | Plans | Result |
|---|---:|---|
| 1. Typed Catalog Primitives | 8/8 | Verified: 5/5 truths, 55/55 requirements |
| 2. Provenance and Atomic Batch | 6/6 | Verified: 5/5 truths, 31/31 requirements |
| **v1.0 total** | **14/14** | **86/86 requirements; 6/6 integration flows** |

Archives: [v1.0 roadmap](milestones/v1.0-ROADMAP.md) · [v1.0 requirements](milestones/v1.0-REQUIREMENTS.md) · [v1.0 audit](milestones/v1.0-MILESTONE-AUDIT.md) · [phase artifacts](milestones/v1.0-phases/)

## Phases

**Phase Numbering:**

- Integer phases (1, 2, …): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)
- v1.0 used Phases 1–2; v1.1 continues at Phase 3

- [x] **Phase 1: Typed Catalog Primitives** - Config, identity, entity/edge upsert, resolve, verify (v1.0)
- [x] **Phase 2: Provenance and Atomic Batch** - Provenance, batch status, atomic batch, docs (v1.0)
- [ ] **Phase 3: Strict Contracts and Catalog-v2 Identity** - Baseline, recursive forbid contracts, FE/BO/COMMON grammar, fail-closed identity
- [ ] **Phase 4: Endpoint Maps, Hashes, and Capabilities** - Server endpoint map, full-domain hashes, capabilities discovery
- [ ] **Phase 5: Immutable Prepare/Commit and Exact Evidence** - Prepare/commit/discard, explicit evidence, one-tx domain+evidence+manifest
- [ ] **Phase 6: Durable Manifests and Read-Only Diagnostics** - Manifest reads, manifest-backed verify, edge resolve, split gates
- [ ] **Phase 7: Verification, Security, Compatibility, and Migration Docs** - Exhaustive tests, isolation, docs, final report without canary

## Hard Gates

1. **No store/control-plane write implementation** until Phase 3–4 unit gates pass for strict models, identity grammar, endpoint map, and hash coverage.
2. **No commit implementation** until prepare/discard prove zero domain/Entity/Episodic/evidence/status mutation on prepare and discard.
3. **No manifest-backed verification** until atomic commit co-writes domain + evidence + manifest + terminal batch/plan state and concurrency tests pass.
4. **Final readiness** only after available unit/service/store/MCP/concurrency/live Neo4j/Ruff/Pyright checks report truthfully and isolation proves no v1.1 `oracle-catalog-v2` query/mutation or canary execution; pre-hardening repository evidence is historical only.
5. **Stop and report** (do not weaken the contract) if Neo4j cannot safely store immutable prepared payloads or co-commit domain + manifest + terminal states in one transaction.

## Phase Details

### Phase 3: Strict Contracts and Catalog-v2 Identity

**Goal**: Maintainers and agents observe fail-closed catalog-v2 request contracts and collision-free FE/BO/COMMON identities before any new store or control-plane write path ships
**Depends on**: v1.0 complete (Phases 1–2)
**Requirements**: BASE-01, BASE-02, BASE-03, BASE-04, SAFE-01, SAFE-02, SAFE-05, SAFE-08, SAFE-12, SAFE-13, CONT-01, CONT-02, CONT-03, CONT-04, CONT-05, CONT-06, CONT-07, CONT-08, IDEN-01, IDEN-02, IDEN-03, IDEN-04, IDEN-05, IDEN-06, IDEN-07, IDEN-08, IDEN-09, IDEN-10, IDEN-11, IDEN-12, IDEN-13, TEST-01, TEST-03
**Success Criteria** (what must be TRUE):

  1. Maintainer can review a recorded live-grounded baseline of all 14 legacy MCP tools, all 7 catalog tools, and the cherry-picked canary builder/runner/fixtures/receipts/checkpoint/tests; historical ACCEPT_TAB commit evidence is inventoried offline, while pre-existing catalog/canary/Ruff/Pyright failures remain distinguishable from v1.1 regressions
  2. Every deterministic catalog request rejects unknown or misspelled nested fields, forbids `strict_endpoints=false` and `atomic=false`, preserves hash-bearing source bytes, and validates completely before any side effect
  3. Catalog-v2 domain requests require `identity_schema_version='catalog-v2'` and a bounded canonical `system_key`; invalid keys fail with `invalid_system_key` / `unsupported_identity_schema` before DB reads, embeddings, schema init, transactions, or status writes
  4. FE and BO objects with identical Oracle names receive different graph keys and server-derived UUIDs in one `group_id`; Procedure/Function overloads do not collapse; catalog-v1 keys/hashes are never silently accepted or rewritten
  5. New tests and development writes use only `oracle-catalog-tool-test`; the pre-existing `oracle-catalog-v2` state is never queried or mutated; no canary runs; caller UUIDs never control identity; structured errors expose safe diagnostics; dirty-worktree and remote state remain untouched

**Plans**: TBD
**Gate**: Unit coverage for recursive forbid, immutable flags, full entity grammar, FE/BO/overload separation, and UUID material versioning must pass before Phase 4 store/control-plane write work

### Phase 4: Endpoint Maps, Hashes, and Capabilities

**Goal**: Agents and operators can rely on one server-owned edge topology, complete authoritative batch hashes, and safe capabilities discovery without enabling mutation
**Depends on**: Phase 3 unit gates green
**Requirements**: EDGE-01, EDGE-02, EDGE-03, EDGE-04, EDGE-05, EDGE-06, EDGE-07, EDGE-08, EDGE-09, HASH-01, HASH-02, HASH-03, HASH-04, HASH-05, HASH-06, HASH-07, CAPA-01, CAPA-02, CAPA-03, CAPA-04, CAPA-05, CAPA-06, CAPA-07, CAPA-08, CAPA-09, TEST-02, TEST-04
**Success Criteria** (what must be TRUE):

  1. Every approved catalog edge type enforces a finite server-owned `(source_entity_type, target_entity_type)` map; disallowed pairs fail before side effects, all paths share one authority, and unapproved `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` remain deferred rather than substituted
  2. Combined batches require lowercase 64-hex `catalog_sha256`; server-computed `request_sha256` covers identity schema, group, batch, catalog hash, and all canonical entity/edge/source/evidence content under one versioned canonicalization recipe; caller `request_sha256` is audit-only or `content_hash_mismatch`
  3. `upsert_catalog_batch` results (including dry-run) return `identity_schema_version`, server `request_sha256`, `catalog_sha256`, and `batch_uuid` with zero dry-run writes
  4. `get_catalog_capabilities` works after server init even when writes are disabled, returns versions, gates, non-reversible namespace fingerprint (never raw namespace), registries, endpoint map, limits, and feature support flags without secrets
  5. `get_status` retains existing `status` and `message` fields; exhaustive table-driven endpoint and hash unit tests pass

**Plans**: TBD
**Gate**: Endpoint-map and hash unit gates must pass before Phase 5 prepare/control-plane write implementation

### Phase 5: Immutable Prepare/Commit and Exact Evidence

**Goal**: Agents can prepare, commit, replay, and discard restart-safe immutable catalog plans that apply exact evidence and co-committed manifests without partial domain success
**Depends on**: Phase 4 map/hash unit gates green
**Requirements**: PLAN-01, PLAN-02, PLAN-03, PLAN-04, PLAN-05, PLAN-06, PLAN-07, PLAN-08, PLAN-09, PLAN-10, PLAN-11, PLAN-12, PLAN-13, PLAN-14, PLAN-15, PLAN-16, PLAN-17, PLAN-18, PLAN-19, PLAN-20, EVID-01, EVID-02, EVID-03, EVID-04, EVID-05, EVID-06, EVID-07, EVID-08, EVID-09, EVID-10, EVID-11, EVID-14, MANI-01, MANI-02, MANI-03, MANI-04, MANI-06, MANI-07, SAFE-11, TEST-05, TEST-06, TEST-07
**Success Criteria** (what must be TRUE):

  1. `prepare_catalog_batch` validates the full catalog-v2 batch, projects outcomes, computes required embeddings, and persists bounded non-Entity immutable payload/identity/membership/embedding state (hashes/counts alone insufficient) with zero domain/evidence/manifest/status mutation
  2. Prepare returns a one-time-visible opaque `plan_token` plus plan UUID, hashes, counts, projections, and `expires_at`; only a secure token digest is stored and compared timing-safe; TTL, payload-byte, and active-plan ceilings are enforced
  3. `commit_prepared_catalog_batch` accepts only `plan_token` (and optional expected hash), revalidates the frozen artifact, performs no external embedding/LLM/queue/network call, and writes domain + exact evidence + durable manifest + terminal batch/plan state in one Neo4j transaction where supported; failure rolls back completely and stranded `COMMITTING` state has deterministic recovery
  4. Explicit `CatalogEvidenceLink` provenance replaces Cartesian multi-source target arrays; missing/mismatched targets fail atomically; identical links coalesce; immutable link conflicts return `provenance_link_conflict`; control records never carry Entity labels
  5. Identical replay and concurrent same-token commits yield one logical committed batch without duplicate domain/evidence/manifest/status; discard terminates only unconsumed plans without deleting domain data; existing `upsert_catalog_batch` remains available with zero-write dry-run

**Plans**: TBD
**Research**: required during planning (payload chunking, property limits, single-tx size, token CAS)
**Stop condition**: If Neo4j cannot store immutable prepared payloads or co-commit domain+manifest+terminal states in one transaction, stop and report — do not weaken the contract
**Gate**: Prepare/discard zero-domain-write, commit atomicity, and concurrency tests must pass before Phase 6 manifest-backed verification

### Phase 6: Durable Manifests and Read-Only Diagnostics

**Goal**: Operators can inspect committed membership, evidence, and edges and verify batches from durable manifests while catalog mutation is disabled
**Depends on**: Phase 5 atomic commit + manifest + concurrency gates green
**Requirements**: MANI-05, VERI-01, VERI-02, VERI-03, VERI-04, VERI-05, VERI-06, RESE-01, RESE-02, RESE-03, GATE-01, GATE-02, GATE-03, GATE-04, GATE-05, GATE-06, EVID-12, EVID-13, TEST-08, TEST-09
**Success Criteria** (what must be TRUE):

  1. `get_catalog_batch_manifest` returns group, batch, hashes, identity schema version, exact counts, and paginated compact item identities for committed membership including unchanged shared entities
  2. Batch-only `verify_catalog_batch` uses the committed manifest as membership authority, reports missing members and extra duplicates, checks exact types/UUIDs/endpoints/embeddings/evidence/manifest consistency, and fails with `manifest_mismatch` when no valid manifest exists
  3. `resolve_typed_edges` and `get_catalog_evidence` return group-isolated read-only diagnostics (edge twins, endpoint mismatches, exact evidence links) without embedding or writes
  4. Separate read/write feature gates keep capabilities and catalog diagnostics usable when writes are disabled; read paths never initialize/repair schema or open write transactions; missing batch status is distinguishable as not-found
  5. Explicit-key verification remains available beside manifest-backed verification; gate/registration tests prove read tools work while writes are off and expected tool sets remain registered

**Plans**: TBD
**Research**: required during planning (manifest property size vs chunk children, verify pagination)

### Phase 7: Verification, Security, Compatibility, and Migration Docs

**Goal**: Maintainers can prove catalog-v2 pre-canary readiness with truthful checks, isolation, security, compatibility, and migration guidance without executing a canary
**Depends on**: Phase 6 complete
**Requirements**: SAFE-03, SAFE-04, SAFE-06, SAFE-07, SAFE-09, SAFE-10, TEST-10, TEST-11, TEST-12, DOCS-01, DOCS-02, DOCS-03, DOCS-04, DOCS-05, DOCS-06, REPT-01
**Success Criteria** (what must be TRUE):

  1. Deterministic catalog paths never invoke prohibited Graphiti tools, LLM extraction, async queue ingestion, implicit endpoints, or communities; conflicts fail closed without silent repair; logs stay free of payloads, source text, credentials, auth headers, raw tokens, and unsafe exceptions
  2. All 14 legacy MCP tools retain names and public contracts; seven catalog tool names remain registered; every read/write stays `group_id`-isolated on Neo4j 5.26+ only
  3. Live Neo4j tests on `oracle-catalog-tool-test` prove atomic rollback, search interop, exact evidence/manifest behavior, control labels excluded from entity search, and zero writes outside the test group
  4. Operator and migration docs cover tool inventory, catalog-v2 grammar/map/hash/capabilities/prepare/evidence/manifest/gates/errors/config, obsolete pre-hardening identities/hashes, no automatic migration, and migrated builder/token-runner/fixtures/receipts/checkpoint tests that regenerate artifacts offline without running the canary
  5. Final structured report sets `canary_executed=false` and sets `ready_to_regenerate_canary=true` only after every stated available gate reports pass/fail/skip truthfully

**Plans**: TBD

## Progress

**Execution Order:**
1 → 2 (shipped) → 3 → 4 → 5 → 6 → 7. Decimal insertions execute in numeric order between integers.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Typed Catalog Primitives | 8/8 | Complete | 2026-07-17 |
| 2. Provenance and Atomic Batch | 6/6 | Complete | 2026-07-17 |
| 3. Strict Contracts and Catalog-v2 Identity | 0/TBD | Not started | - |
| 4. Endpoint Maps, Hashes, and Capabilities | 0/TBD | Not started | - |
| 5. Immutable Prepare/Commit and Exact Evidence | 0/TBD | Not started | - |
| 6. Durable Manifests and Read-Only Diagnostics | 0/TBD | Not started | - |
| 7. Verification, Security, Compatibility, and Migration Docs | 0/TBD | Not started | - |

## Coverage

| Phase | Requirement count | Categories |
|-------|------------------:|------------|
| 3 | 33 | BASE, SAFE (baseline/isolation/identity/errors/worktree), CONT, IDEN, TEST-01/03 |
| 4 | 27 | EDGE, HASH, CAPA, TEST-02/04 |
| 5 | 42 | PLAN, EVID (write-side), MANI (co-commit write), SAFE-11, TEST-05/06/07 |
| 6 | 20 | MANI-05, VERI, RESE, GATE, EVID-12/13, TEST-08/09 |
| 7 | 16 | SAFE (security/compat/isolation), TEST-10/11/12, DOCS, REPT |
| **v1.1 total** | **138** | All v1.1 |

- v1.1 requirements: 138
- Mapped: 138/138
- Orphans: 0
- Duplicates: 0

## Explicit Non-Goals (v1.1)

- Real canary execution or production/`oracle-catalog-v2` writes
- Automatic catalog-v1 → catalog-v2 identity migration
- Oracle/SQL/PL/SQL parsing, relationship inference, object-context/path/impact tools
- Catalog delta/retirement, business-transaction entities
- FalkorDB/Kuzu/Neptune catalog portability claims
- Deployment, push/merge/tag, graph clear/delete, full 14k ingest

---
*Roadmap created: 2026-07-17 for milestone v1.1*
