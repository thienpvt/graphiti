# Phase 3A: Immutable Prepare/Commit Control Plane - Research

**Researched:** 2026-07-18
**Domain:** Deterministic catalog prepare/commit control plane (Neo4j 5.26+, FastMCP, Pydantic strict contracts)
**Confidence:** HIGH (code seams + Phase 2 gate); MEDIUM (Neo4j property practical ceilings — no official hard string limit)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Persist one deterministic non-`Entity` prepared-plan root plus ordered bounded server-owned payload-chunk control records when the artifact exceeds a conservative per-record ceiling.
- **D-02:** The frozen artifact contains canonical payload bytes, schema/canonicalization versions, group/batch scope, request/catalog/artifact hashes, deterministic identities, resolved membership, projected outcomes, and all required embeddings. Hashes and counts alone are insufficient.
- **D-03:** Define one deterministic artifact serialization and `artifact_sha256`; chunk ordering, count, byte lengths, and digest are immutable. Reassembly must reproduce byte-identical canonical content before commit may proceed.
- **D-04:** Plan and chunk records carry fixed control labels only. They never carry `Entity`, `Episodic`, semantic edge labels, searchable embeddings, or properties used by normal graph search/community paths.
- **D-05:** Immutability is enforced in both store queries and service checks: create once under deterministic plan identity, reject same identity with changed digest/scope/content, never update artifact bytes or frozen embeddings after PREPARED.
- **D-06:** Research must establish a conservative Neo4j property/transaction sizing policy and chunk threshold. If bounded immutable persistence cannot be proven, Phase 3A hard-stops.
- **D-07:** Generate a high-entropy opaque token using Python `secrets`; return it exactly once from prepare. Never derive it from plan UUID, batch ID, request hash, or other predictable material.
- **D-08:** Persist only a domain-separated SHA-256 token digest. Compare supplied-token digests with `hmac.compare_digest`. Never log, return later, serialize into the artifact, or store the raw token in recoverable form.
- **D-09:** Bind the token persistently to one `plan_uuid`, `group_id`, `batch_id`, identity schema version, request hash, catalog hash, artifact hash, and expiry. A token cannot authorize another scope.
- **D-10:** Use explicit `PREPARED`, `COMMITTING`, `COMMITTED`, `DISCARDED`, and `EXPIRED` states with legal compare-and-set transitions. Terminal states never revive.
- **D-11:** `discard_prepared_catalog_batch` accepts only the token, is idempotent for an unconsumed plan, transitions `PREPARED` to `DISCARDED`, and never deletes domain graph data, evidence, manifests, or committed batch status.
- **D-12:** A stranded `COMMITTING` plan follows one deterministic recovery rule selected by research and proven by tests. No timeout-only blind reset to PREPARED.
- **D-13:** Missing, malformed, expired, discarded, consumed, or conflicting tokens return fixed structured prepared-plan errors with bounded messages and no token-validity oracle beyond the documented outcome.
- **D-14:** `prepare_catalog_batch` accepts the complete canonical catalog-v2 batch contract without `dry_run`, token, or caller identity/hash authority. The server computes all authoritative hashes and identities.
- **D-15:** Before control-plane persistence, validate the whole request: strict fields, identity/version/system grammar, limits, duplicate/coalescing rules, topology, existing and same-batch endpoints, immutable identity conflicts, source/evidence target resolution, and configured/hard plan limits.
- **D-16:** Compute exact projected created/updated/unchanged outcomes and exact entity/edge/source/evidence membership. Reuse current `CatalogService` preparation/preflight helpers where correct; do not fork a second identity/topology/hash authority.
- **D-17:** Compute every required embedding before opening the prepared-artifact write transaction. Embedding failure leaves no plan root, chunk, domain, evidence, manifest, status, or terminal-state partial write.
- **D-18:** Prepare persists control-plane state only after all pure checks, reads, projections, canonicalization, and external precomputation succeed. It writes zero `Entity`, `RELATES_TO`, `Episodic`, MENTIONS/evidence, manifest, or `CatalogIngestBatch` state.
- **D-19:** Prepare receipt returns the one-time token, deterministic plan UUID, authoritative request/catalog/artifact hashes, schema versions, entity/edge/source/evidence-link counts, projected outcomes, and `expires_at`; never returns canonical payload or embeddings.
- **D-20:** `commit_prepared_catalog_batch` accepts only `plan_token` and optional `expected_request_sha256`. It cannot accept group, batch, entities, edges, sources, evidence links, catalog hash, replacement payload, or mutable execution flags.
- **D-21:** Commit loads and reassembles the frozen artifact server-side, verifies token binding, state, expiry, chunk integrity, artifact hash, request hash, schema versions, counts, and immutable scope before any domain transaction.
- **D-22:** Commit uses only embeddings frozen in the artifact. It performs no embedder, LLM, queue, HTTP, provider, or other external network call before or during domain commit.
- **D-23:** Phase 3A may implement and test the safe token claim/load/revalidation seam and state machine, but Phase 3B owns the one-transaction domain/evidence/manifest/terminal-state commit body. No provisional domain write is allowed merely to demonstrate commit.
- **D-24:** Add configured TTL, maximum prepared payload bytes, maximum active plans per group, and chunk size/count controls with immutable hard ceilings. Defaults must be conservative and exposed truthfully by capabilities.
- **D-25:** Enforce active-plan capacity by `group_id` under a transaction-safe claim, counting only active nonterminal plans according to a documented policy. Capacity checks cannot race into an unbounded excess.
- **D-26:** Expiry is evaluated against server UTC time. Access may atomically mark an expired PREPARED plan `EXPIRED`; cleanup remains bounded and must not be required for correctness.
- **D-27:** Terminal record retention/cleanup policy may be deferred to operational polish if terminal states remain bounded and correctness does not depend on deletion. No background queue or unbounded cleanup worker in Phase 3A.
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

### Deferred Ideas (OUT OF SCOPE)
- Domain entity/edge/source writes, exact evidence persistence, durable manifest, terminal batch status, and terminal plan co-commit: Phase 3B.
- Concurrent same-token domain commit, complete rollback, and stranded COMMITTING production recovery proof: finalized in Phase 3B using the Phase 3A state seam.
- Manifest/evidence reads, edge resolution, and manifest-backed verification: Phase 4.
- Long-term retention jobs, metrics, migration/rollback docs, and operational cleanup: Phase 5 unless required for Phase 3A correctness.
- Canary execution, `oracle-catalog-v2` access, production migration, deployment, and graph cleanup: separate approval/out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAN-01 | prepare accepts full catalog-v2 domain batch without dry_run/token/caller hash authority | New `PrepareCatalogBatchRequest` = batch contract minus `dry_run`; server hashes via existing `batch_request_sha256` |
| PLAN-02 | Full preflight before plan persist | Extract shared preflight from `CatalogService.upsert_catalog_batch` (lines ~3690–4471) |
| PLAN-03 | Project outcomes + embeddings; zero domain/status mutation | Embed before control-plane tx; assert no Entity/CatalogIngestBatch writes in prepare path |
| PLAN-04 | Persist complete immutable control-plane artifact | Root+chunk model with full membership+embeddings, not hashes alone |
| PLAN-05 | Restart-safe, group-isolated, size-bounded, immutable, chunked | Neo4j durable nodes; constraints; chunk policy below |
| PLAN-06 | One-time token + plan_uuid + hashes + counts + projections + expires_at | Receipt model; raw token only in prepare response |
| PLAN-07 | Digest-only storage; timing-safe compare | `secrets` + domain SHA-256 + `hmac.compare_digest` |
| PLAN-08 | Configured + hard TTL/payload/active-plan ceilings | CatalogConfig + capabilities hard constants |
| PLAN-09 | Control labels never Entity/searchable embeddings | Labels `CatalogPreparedPlan` / `CatalogPreparedPlanChunk` only |
| PLAN-10 | Commit token-only (+ optional expected_request_sha256) | Strict commit request model |
| PLAN-11 | Load/revalidate; specific prepared-plan error codes | Existing CONT-08 codes + CAS outcomes |
| PLAN-12 | Frozen embeddings only; no external calls on commit | Spy embedder/network in tests; Phase 3A load seam only |
| PLAN-17 | Token bound to immutable group/batch/schema/hash/payload | Persist binding fields on plan root |
| PLAN-18 | Expired/discarded/consumed never revive | Terminal CAS matrix |
| PLAN-19 | Discard token-only, idempotent, no domain delete | PREPARED→DISCARDED CAS |
| PLAN-20 | upsert_catalog_batch remains; dry_run zero-write | No regression; additive tools |
| SAFE-11 | Embed before plan persist; embed fail leaves nothing | Same order as entity/edge upserts |
| TEST-05 | Full prepare/control-plane proof suite | Unit + store + service + MCP + live Neo4j map below |
</phase_requirements>

## Summary

Phase 3A adds three additive MCP tools that freeze a complete validated catalog-v2 batch into restart-safe Neo4j control-plane state, then allow token-only load/claim for Phase 3B domain co-commit. Current code already has the pure authorities Phase 3A must reuse: strict batch models, `batch_request_sha256` / canonical payloads, topology map, evidence contract, projection/embed orchestration inside `CatalogService.upsert_catalog_batch`, fixed-query `CatalogNeo4jStore` with real transactions and non-Entity `CatalogIngestBatch` status, `catalog_prepared_plan_uuid`, prepared-plan error codes, and zero-valued capability placeholders for plan limits. **No prepare/commit/discard write path exists yet** — Phase 2 gate recorded `no_new_store_or_control_plane_write_path: true` and `features.prepare_commit=false`.

**Primary recommendation:** Implement prepare as a extracted shared preflight → embed → single control-plane transaction that creates one `CatalogPreparedPlan` root plus ordered `CatalogPreparedPlanChunk` records under deterministic plan identity; store only a domain-separated token digest; expose commit as token-only load/CAS into `COMMITTING` with **zero domain writes** until Phase 3B; hard-stop if live Neo4j cannot round-trip a byte-identical reassembled artifact under the configured ceilings.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Strict prepare/commit/discard request validation | API / Backend (MCP models) | — | Fail closed before service |
| Identity / hash / topology / evidence authority | API / Backend (pure services) | — | Already single authority in Phase 1–2 |
| Projection + embedding precompute | API / Backend (`CatalogService`) | External embedder | Embed before any plan write (SAFE-11) |
| Immutable plan/chunk persistence | Database / Storage (Neo4j control plane) | — | Restart-safe durable state |
| Token digest CAS / state machine | Database / Storage + service | — | Atomic claim under uniqueness constraints |
| Domain/evidence/manifest commit body | Deferred Phase 3B | — | D-23 boundary |
| Capabilities / feature flags | API / Backend (read-only) | — | CAPA truthfulness |
| MCP registration + safe errors | API / Backend (FastMCP) | — | Thin wrappers only |

## Current Architecture

### Reusable seams (verified in source)

| Seam | Location | Phase 3A use |
|------|----------|--------------|
| `UpsertCatalogBatchRequest` | `mcp_server/src/models/catalog_batch.py` | Base domain contract; prepare drops `dry_run` |
| `CatalogStrictModel` / `CatalogErrorCode` | `catalog_common.py` | prepared_plan_* codes already present (CONT-08) |
| `batch_request_sha256` / canonical payloads | `catalog_identity.py` | PLAN-01/02/04 hash authority; extend with artifact helpers |
| `catalog_prepared_plan_uuid` | `catalog_identity.py:71-75` | Deterministic plan UUID |
| Preflight body | `CatalogService.upsert_catalog_batch` ~3690–4471 | Extract `_prepare_batch_preflight` shared by prepare + upsert |
| Embed before write | same method ~4531–4560 | Mirror for prepare (no domain tx after) |
| Status claim pattern | `CatalogNeo4jStore.claim_batch_status` / CAS MERGE | Template for plan state CAS (new labels) |
| Real tx context | `graphiti_core/driver/neo4j_driver.py` `transaction()` | Control-plane writes only after commit |
| Capabilities placeholders | `catalog_capabilities.py` HARD_* = 0, `prepare_commit=False` | Replace with real ceilings; flip flag after tests |
| MCP safe boundary | `CATALOG_TOOL_NAMES` + `CatalogSafeFastMCP` | Add three tool names |
| Live isolation fixture | `test_catalog_neo4j_int.py` group `oracle-catalog-tool-test` | Extend; never `oracle-catalog-v2` |

### Gaps (must build)

| Gap | Notes |
|-----|-------|
| Prepare/commit/discard models + responses | New files or extend `catalog_batch.py` / `catalog_responses.py` |
| Artifact serialize/chunk/reassemble pure helpers | Prefer `catalog_identity.py` or new `catalog_prepared_artifact.py` |
| Token mint/digest/verify pure helpers | stdlib only |
| Plan store Cypher (create immutable, load chunks, CAS state, capacity) | `catalog_store.py` additive methods |
| Service methods `prepare_catalog_batch`, `commit_prepared_catalog_batch` (load/claim only), `discard_prepared_catalog_batch` | `catalog_service.py` |
| CatalogConfig plan limits | `schema.py` |
| MCP tools registration | `graphiti_mcp_server.py` |
| TEST-05 suite + Phase 3A gate runner | New tests; mirror Phase 2 gate pattern |

### Existing batch write order (must not break)

```
validate → hash → pre-read/project → (dry_run return) → embed → ensure_schema → tx(claim status + domain writes + terminal status)
```

Prepare order:

```
validate → hash → pre-read/project → size/TTL/capacity precheck → embed → ensure_plan_schema → tx(capacity CAS + create plan+chunks only)
```

Commit Phase 3A order:

```
token digest → load plan+chunks → reassemble → verify binding/hash/expiry/state → optional CAS PREPARED→COMMITTING → return claim receipt (no domain write, no external I/O)
```

## Recommended Design

### 1. Canonical artifact format and IDs

**Serialization version:** `prepared-artifact-v1` (constant beside `CANONICALIZATION_VERSION`).

**Canonical artifact object (JSON object, then UTF-8 bytes):**

```json
{
  "artifact_serialization_version": "prepared-artifact-v1",
  "canonicalization_version": "catalog-canonical-v1",
  "identity_schema_version": "catalog-v2",
  "catalog_schema_version": "catalog-schema-v1",
  "group_id": "...",
  "batch_id": "...",
  "system_key": "FE|BO|COMMON",
  "request_sha256": "64hex",
  "catalog_sha256": "64hex",
  "plan_id": "...",
  "membership": {
    "entities": [{"uuid","entity_type","graph_key","content_sha256","projected_status","name_embedding"}],
    "edges": [{"uuid","edge_type","edge_key","source_uuid","target_uuid","content_sha256","projected_status","fact_embedding"}],
    "sources": [{"uuid","source_key","content_sha256","projected_status"}],
    "evidence_links": [{"uuid","link_key","content_sha256"}]
  },
  "request_canonical": { /* batch_request_canonical_payload without transport fields */ },
  "counts": {"entities","edges","sources","evidence_links","created","updated","unchanged"}
}
```

- **Serialize:** `json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')` — same rules as `canonical_sha256`.
- **`artifact_sha256`:** `sha256(artifact_bytes).hexdigest()` — **not** stored inside the hashed bytes (compute over body excluding self-hash field, or hash the full body then attach hash only on plan root metadata). **Recommendation:** hash the complete canonical bytes **without** an embedded `artifact_sha256` field; store digest only on plan root + receipt.
- **`plan_id` (deterministic):** `f'{batch_id}|{request_sha256}'` → `catalog_prepared_plan_uuid(ns, group_id, plan_id)`. Same content → same plan identity; conflict if PREPARED exists with different `artifact_sha256` (`prepared_plan_conflict`).
- **Chunk IDs:** `catalog_prepared_plan_chunk_uuid(ns, group_id, plan_id, chunk_index)` — new pure helper: material `group_id|catalog-v2|PreparedPlanChunk|{plan_id}|{index}`.
- **Chunk payload encoding:** store each slice as **UTF-8 safe base64** property `payload_b64` (ASCII, no JSON-escape surprises for binary-ish float dumps). Also store `chunk_index`, `chunk_sha256`, `byte_offset`, `byte_length`, `chunk_count` on root.
- **Reassembly:** sort by `chunk_index`, b64decode, concatenate, verify total length + `artifact_sha256`; reject on any mismatch.

### 2. Opaque token

```python
import hashlib, hmac, secrets

TOKEN_DIGEST_DOMAIN = b'graphiti.catalog.plan_token.v1|'

def mint_plan_token() -> str:
    return secrets.token_urlsafe(32)  # 256-bit entropy

def plan_token_digest(token: str) -> str:
    return hashlib.sha256(TOKEN_DIGEST_DOMAIN + token.encode('utf-8')).hexdigest()

def plan_token_matches(token: str, stored_digest: str) -> bool:
    return hmac.compare_digest(plan_token_digest(token), stored_digest)
```

- Never put raw token in logs, artifact, or Neo4j.
- Lookup: scan is not by raw token — **index/constraint on `token_digest` + `group_id` is wrong for cross-group**; prefer global unique `token_digest` (digest is 256-bit; collision negligible) OR match `(token_digest)` unique constraint alone so commit needs only the token.

### 3. State machine and stranded COMMITTING recovery

```
              discard
  PREPARED ──────────► DISCARDED (terminal)
     │  expire(access)
     ├───────────────► EXPIRED (terminal)
     │ claim commit
     ▼
  COMMITTING ────────► COMMITTED (terminal; Phase 3B success)
     │
     └── re-entry with same token: stay COMMITTING / complete 3B (never → PREPARED)
```

**Legal CAS table**

| From | To | Actor | Condition |
|------|-----|-------|-----------|
| (absent) | PREPARED | prepare | capacity ok; create once |
| PREPARED | DISCARDED | discard | token ok; not expired |
| PREPARED | EXPIRED | any access | `now >= expires_at` |
| PREPARED | COMMITTING | commit claim | token+binding ok; not expired |
| COMMITTING | COMMITTED | Phase 3B only | domain tx success |
| COMMITTING | COMMITTING | commit re-entry | same token digest; recovery |
| * | PREPARED | — | **forbidden** |
| terminal | non-terminal | — | **forbidden** |

**Stranded COMMITTING recovery (D-12 recommendation):**

1. **No timeout reset to PREPARED.**
2. Commit always: resolve plan by token digest → if `EXPIRED` mark/fail → if `DISCARDED`/`COMMITTED` structured codes → if `PREPARED` CAS to `COMMITTING` → if already `COMMITTING` with matching digest+artifact, treat as **sole writer recovery re-entry** (Phase 3A returns claim success with `state=COMMITTING` and frozen artifact handle; Phase 3B decides domain completion vs conflict under single-tx rules).
3. Optional lease field `committing_started_at` for observability only — **not** an automatic state transition.
4. Phase 3A tests: CAS matrix + re-entry does not create second plan or revive terminals. Phase 3B owns domain uniqueness under concurrent re-entry.

### 4. Active-plan capacity (race-safe)

**Active** = `state IN ('PREPARED','COMMITTING')` AND (`expires_at > now` OR state=`COMMITTING`). Optionally treat expired PREPARED as inactive for capacity even before EXPIRED mark.

**Enforcement (single control-plane tx):**

```cypher
// Pseudocode fixed labels/params only
MATCH (p:CatalogPreparedPlan {group_id: $group_id})
WHERE p.state IN ['PREPARED','COMMITTING']
  AND (p.state = 'COMMITTING' OR p.expires_at > $now)
WITH count(p) AS active
WHERE active < $max_active
// then CREATE plan root + chunks
```

Plus unique constraints:

- `CatalogPreparedPlan` unique `(uuid, group_id)`
- `CatalogPreparedPlan` unique `token_digest`
- `CatalogPreparedPlanChunk` unique `(uuid, group_id)` and unique `(plan_uuid, group_id, chunk_index)`

If count check + create is not atomic enough under concurrent prepares, add **group lock node**:

```cypher
MERGE (g:CatalogPlanGroupLock {group_id: $group_id})
// then count + create in same tx (lock serializes writers on group)
```

**Recommendation:** use group lock node + count in one tx (simplest race-free pattern already familiar from batch claim).

### 5. Prepare preflight and zero domain writes

Extract from `upsert_catalog_batch`:

1. Gate / namespace / limits / optional client hash
2. Entity/edge/source prepare loops with projection
3. Topology + endpoint resolution
4. Evidence target resolution (links identity only; no evidence persist)
5. Error aggregation

Prepare-specific:

- Reject presence of `dry_run` field (model omits it)
- After projection success: compute embeddings for non-unchanged entities/edges
- Build artifact bytes; enforce payload byte ceiling
- Open **one** write tx: capacity + plan root CREATE (not MERGE-update) + chunks CREATE
- **Forbidden in prepare tx:** Entity, RELATES_TO, Episodic, MENTIONS, CatalogIngestBatch, evidence, manifest labels

Idempotent re-prepare of identical plan identity in PREPARED: return `prepared_plan_conflict` or optional same-token denial (token already one-time). **Recommendation:** conflict if exists in any state with same plan_uuid (caller must discard or use new batch/hash). Do not re-issue token for existing plan (PLAN-06 one-time).

### 6. Commit Phase 3A boundary

`CommitPreparedCatalogBatchRequest`:

- `plan_token: str` (min length bound, max ~128)
- `expected_request_sha256: str | None`

Service:

1. Digest token; load plan by digest
2. If missing → `prepared_plan_not_found`
3. If expired → CAS EXPIRED → `prepared_plan_expired`
4. If DISCARDED → `prepared_plan_not_found` or dedicated discarded mapping — **use existing codes only** (`prepared_plan_not_found` / `prepared_plan_already_consumed` / `prepared_plan_conflict` / `prepared_plan_expired`); map discarded → `prepared_plan_not_found` or conflict per D-13 (prefer **not_found** to reduce oracle; document)
5. If COMMITTED → `prepared_plan_already_consumed` (replay body is Phase 3B)
6. Reassemble chunks; verify artifact_sha256, request hash, optional expected hash, schema versions
7. CAS PREPARED→COMMITTING (or re-enter COMMITTING)
8. Return `CommitPreparedCatalogBatchResponse` with plan_uuid, hashes, state=`COMMITTING`, counts — **no domain mutation**
9. Assert embedder/LLM/queue not called (unit spy)

Phase 3B later replaces step 8 body with domain co-commit ending COMMITTED.

### 7. TTL / discard / retention

| Control | Default | Hard ceiling | Basis |
|---------|---------|--------------|-------|
| plan_ttl_seconds | 3600 (1h) | 86400 (24h) | Agent session window; hard stop runaway retention |
| max_prepared_payload_bytes | 4_194_304 (4 MiB) | 16_777_216 (16 MiB) | Conservative vs default batch scale + embeddings; under typical heap/tx budgets |
| prepared_chunk_bytes | 131_072 (128 KiB) | 262_144 (256 KiB) | ≪ Bolt max chunk 65_535 is transport-only; property chunks kept small for page/tx friendliness |
| max_chunks_per_plan | derived | 128 | hard payload / min chunk |
| max_active_plans_per_group | 8 | 32 | Prevent control-plane DoS per group |

- Expiry: compare `datetime.now(timezone.utc)` to stored `expires_at` (UTC ISO/datetime).
- Discard: token-only CAS PREPARED→DISCARDED; idempotent if already DISCARDED; error if COMMITTING/COMMITTED.
- Cleanup deletion: **deferred** (D-27). Correctness via state checks only.

### 8. Config / capabilities / MCP / errors

**CatalogConfig** additive fields (with hard clamps like batch limits):

- `plan_ttl_seconds`
- `max_prepared_payload_bytes`
- `max_active_plans_per_group`
- `prepared_chunk_bytes` (optional config; else constant)

**Capabilities:** replace zeros in Wave 4 with tools registered but `features.prepare_commit=False`; set `True` only in Wave 5 **after** required live immutable-artifact proof + re-test on final HEAD (gate-controlled). Keep `manifests=False`.

**MCP tools (additive):**

- `prepare_catalog_batch`
- `commit_prepared_catalog_batch`
- `discard_prepared_catalog_batch`

Add all three to `CATALOG_TOOL_NAMES`. Preserve existing eight catalog tools + 14 legacy.

**Errors:** reuse CONT-08 prepared_plan_* codes; add only if essential:

- `batch_limit_exceeded` for payload/active-plan ceilings (existing)
- Optional message-bounded `prepared_plan_conflict` for capacity/identity conflicts

No new dependency packages.

### 9. Module split (minimal)

| Module | Additions |
|--------|-----------|
| `models/catalog_batch.py` or `models/catalog_prepare.py` | Prepare/Commit/Discard requests |
| `models/catalog_responses.py` | Prepare/Commit/Discard responses |
| `services/catalog_identity.py` | artifact_sha256, token digest, chunk uuid |
| `services/catalog_prepared_artifact.py` (new, optional) | serialize/chunk/reassemble pure |
| `services/catalog_store.py` | plan schema constraints + CRUD/CAS |
| `services/catalog_service.py` | three methods; extract shared preflight |
| `services/catalog_capabilities.py` | real limits + feature flag |
| `config/schema.py` | CatalogConfig fields |
| `graphiti_mcp_server.py` | three `@mcp.tool` wrappers |

### 10. Control labels and properties (fixed)

**Labels:** `CatalogPreparedPlan`, `CatalogPreparedPlanChunk`, optional `CatalogPlanGroupLock`  
**Never:** `Entity`, `Episodic`, edge type labels, vector index properties named `name_embedding`/`fact_embedding` on control nodes (store embeddings **inside chunk payload only**).

**Plan root properties (allowlist):**  
`uuid`, `group_id`, `batch_id`, `plan_id`, `token_digest`, `state`, `identity_schema_version`, `canonicalization_version`, `artifact_serialization_version`, `request_sha256`, `catalog_sha256`, `artifact_sha256`, `chunk_count`, `payload_bytes`, `entity_count`, `edge_count`, `source_count`, `evidence_link_count`, `created_count`, `updated_count`, `unchanged_count`, `expires_at`, `created_at`, `updated_at`, `committing_started_at` (optional)

**Chunk properties:**  
`uuid`, `group_id`, `plan_uuid`, `chunk_index`, `chunk_count`, `byte_offset`, `byte_length`, `chunk_sha256`, `payload_b64`

## Neo4j Evidence

### Official findings

| Topic | Finding | Source | Confidence |
|-------|---------|--------|------------|
| Property types | STRING, LIST of homogeneous simple types, byte arrays pass-through | [Neo4j Cypher Manual 5 — values and types](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/) | HIGH |
| Hard STRING size limit | **Not documented** as a fixed max length in Cypher property types page | same | HIGH (absence) |
| Transaction memory | Configurable caps `db.memory.transaction.max` / total.max; oversized tx killed | [Operations Manual — memory configuration](https://neo4j.com/docs/operations-manual/5/performance/memory-configuration/) | HIGH |
| Bolt transport | Max **chunk** size 65_535 bytes; messages multi-chunked; no total message size in Bolt message doc | [Bolt message](https://neo4j.com/docs/bolt/current/bolt/message/) | HIGH |
| MERGE/CREATE immutability | Application-enforced: CREATE once + reject updates; constraints for uniqueness | Code pattern + Cypher semantics | HIGH |
| Concurrent capacity | Must be same-tx count+create or lock node; read-then-write outside tx races | General Neo4j tx isolation | HIGH |
| Restart persistence | Committed nodes durable; in-flight tx rollback on crash | Driver `transaction()` real commit/rollback in this repo | HIGH |

### Conservative policy (discretion)

Because Neo4j documents **no hard property string limit**, Phase 3A must not claim a vendor hard max. Instead:

1. **Configured/hard application ceilings** (table in §7) — fail closed before write.
2. **Chunk ≤ 256 KiB** property payloads to keep page cache and tx state predictable.
3. **Total prepared artifact ≤ 16 MiB hard** — enough for default 500/2000 entity/edge batches with float embeddings in JSON, small enough for typical heap.
4. **Live proof required** (`oracle-catalog-tool-test`): write max configured artifact, restart process (or new driver session), reassemble byte-identical, CAS state. If Neo4j rejects or corrupts → **hard stop** (ROADMAP stop condition).

### Driver version

Installed/available: `neo4j` Python driver **5.26.0** (probed in worktree). Aligns with project `neo4j>=5.26.0` and Neo4j 5.26+ requirement.

## Standard Stack

### Core (existing — no new packages)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| Python stdlib `secrets`/`hashlib`/`hmac`/`json` | 3.10+ | Token + digests + canonical JSON | D-07/D-08; no new deps |
| Pydantic | ≥2.11.5 | Strict request/response models | Project standard |
| neo4j | ≥5.26.0 | Control-plane persistence | Existing store |
| pytest / pytest-asyncio | project pins | TDD | workflow.tdd_mode |
| mcp FastMCP | ≥1.27.2 | Tool registration | Existing |

### Package Legitimacy Audit

| Package | Registry | Verdict | Disposition |
|---------|----------|---------|-------------|
| *(none new)* | — | — | No installs required for Phase 3A |

**Packages removed due to [SLOP]:** none  
**Packages flagged [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
Agent/MCP client
    │
    ├─ prepare_catalog_batch(request[-dry_run])
    │     → Pydantic strict validate
    │     → CatalogService shared preflight (identity/topology/project)
    │     → embedder.create* (external) ── on fail: return, no writes
    │     → build artifact bytes + artifact_sha256
    │     → Neo4j TX: capacity lock + CREATE plan + chunks (control only)
    │     → receipt {plan_token once, plan_uuid, hashes, counts, expires_at}
    │
    ├─ discard_prepared_catalog_batch(plan_token)
    │     → digest → CAS PREPARED→DISCARDED
    │
    └─ commit_prepared_catalog_batch(plan_token[, expected_request_sha256])
          → digest → load+reassemble+verify
          → CAS PREPARED→COMMITTING (or re-enter)
          → Phase 3A STOP (no domain write)
          → [Phase 3B] domain+evidence+manifest+COMMITTED one TX
```

### Anti-Patterns to Avoid

- **Storing raw token or re-deriving token from plan_uuid** — breaks PLAN-07/entropy
- **Hashes-only prepare** — violates PLAN-04/D-02
- **MERGE that updates artifact bytes** — breaks immutability
- **Embedding inside control-plane tx** — embed failure mid-write risk
- **Domain write in prepare "to help 3B"** — D-23 / hard gate
- **Timeout reset COMMITTING→PREPARED** — second writer hazard
- **Client Cypher labels** — fixed server labels only
- **Logging plan_token / payload / embeddings** — SAFE-07/11

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Opaque tokens | Custom PRNG | `secrets.token_urlsafe` |
| Timing-safe compare | `==` on digests | `hmac.compare_digest` |
| Canonical JSON hash | ad-hoc dumps | existing `canonical_sha256` pattern |
| Transactions | manual commit flags | `Neo4jDriver.transaction()` |
| UUID identity | client UUIDs | `catalog_prepared_plan_uuid` + chunk helper |
| Strict validation | hand parsers | `CatalogStrictModel` |

## Spec-Less Probe Inventory

Classification: **covered** (existing tests/code already enforce), **backstop** (existing partial; Phase 3A must extend), **unresolved** (must implement + test).

| # | Edge / requirement | Class | Notes |
|---|--------------------|-------|-------|
| P01 | PLAN-01 prepare request shape | unresolved | New model |
| P02 | PLAN-02 full preflight reuse | backstop | Logic lives in upsert_catalog_batch |
| P03 | PLAN-03 zero domain on prepare | unresolved | New assertions + spies |
| P04 | PLAN-04 full artifact content | unresolved | |
| P05 | PLAN-05 chunk+restart | unresolved | Live Neo4j essential |
| P06 | PLAN-06 one-time token receipt | unresolved | |
| P07 | PLAN-07 digest + compare_digest | unresolved | |
| P08 | PLAN-08 limits | backstop | placeholders 0 today |
| P09 | PLAN-09 non-Entity control labels | backstop | CatalogIngestBatch pattern |
| P10 | PLAN-10 commit token-only model | unresolved | |
| P11 | PLAN-11 load/revalidate errors | backstop | codes exist; paths don't |
| P12 | PLAN-12 no external commit calls | unresolved | |
| P13 | PLAN-17 token binding fields | unresolved | |
| P14 | PLAN-18 no revive | unresolved | |
| P15 | PLAN-19 discard | unresolved | |
| P16 | PLAN-20 upsert + dry_run preserved | covered | regression suite |
| P17 | SAFE-11 embed-before-plan | backstop | embed-before-domain exists |
| P18 | TEST-05 matrix | unresolved | new suite |
| P19 | CONT-02 prepare/commit forbid extra | backstop | CatalogStrictModel |
| P20 | SAFE-01 group isolation | covered | int fixtures |
| P21 | SAFE-02 no canary | covered | policy |
| P22 | CAPA prepare_commit false until green | covered | flip at gate |
| P23 | CATALOG_TOOL_NAMES safe errors | backstop | add 3 names |
| P24 | No oracle-catalog-v2 | covered | int tests |
| P25 | Capacity race | unresolved | lock+count |
| P26 | COMMITTING recovery seam | unresolved | CAS re-entry |
| P27 | Immutability same identity different digest | unresolved | |
| P28 | Chunk reassembly mismatch fail-closed | unresolved | |
| P29 | Expiry access path | unresolved | |
| P30 | Features/limits truthful | backstop | capabilities tests |
| P31 | Logging redaction token | backstop | scrub patterns Phase 1 |
| P32 | Schema ensure plan constraints CREATE IF NOT EXISTS | backstop | store pattern |
| P33 | dry_run upsert zero control-plane | covered | keep; prepare has no dry_run |
| P34 | Hard stop if Neo4j cannot store | unresolved | live probe gate |

**Silent drop check:** 18 Phase 3A requirement IDs mapped; PLAN-13..16 intentionally Phase 3B (not in this phase). No PLAN-01..12/17..20/SAFE-11/TEST-05 left unmapped.

**Live Neo4j essential for hard stop?** **Yes.** Unit mocks cannot prove durable property storage, constraint behavior, or restart reassembly under real Neo4j 5.26. Design: extend `test_catalog_neo4j_int.py` patterns only with `GROUP=oracle-catalog-tool-test`, DETACH DELETE that group, never `oracle-catalog-v2`, never `clear_graph`.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (mcp_server) |
| Config | `mcp_server/pytest.ini` |
| Quick run | `cd mcp_server && uv run pytest tests/test_catalog_prepare.py tests/test_catalog_prepared_artifact.py -q` |
| Focused control-plane | `uv run pytest tests/test_catalog_prepare.py tests/test_catalog_store_prepare.py tests/test_catalog_service_prepare.py -q` |
| Live Neo4j | `uv run pytest tests/test_catalog_prepare_neo4j_int.py -m integration` (skip unless Neo4j up; `CATALOG_INT_REQUIRED=1` to fail) |
| Full catalog regression | `uv run pytest tests/test_catalog_*.py -q --ignore=tests/test_catalog_canary_scripts.py` |
| Gate | stdlib runner `catalog_phase3a_gate_runner.py` mirroring Phase 2 |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| PLAN-01 | prepare model rejects dry_run/token/extra | unit | `pytest tests/test_catalog_prepare_models.py -q` | ❌ Wave 0 |
| PLAN-02 | preflight fails before plan write | unit/service | service spies store | ❌ Wave 0 |
| PLAN-03 | zero Entity/status mutation | unit + live | count group nodes labels | ❌ Wave 0 |
| PLAN-04 | artifact contains membership+embeddings | unit | reassemble equality | ❌ Wave 0 |
| PLAN-05 | chunk bounds + restart load | unit + live | int roundtrip | ❌ Wave 0 |
| PLAN-06 | token once; receipt fields | unit | mock store | ❌ Wave 0 |
| PLAN-07 | digest only; compare_digest | unit | pure crypto tests | ❌ Wave 0 |
| PLAN-08 | TTL/payload/active ceilings | unit | config + service | ❌ Wave 0 |
| PLAN-09 | labels not Entity | unit + live | MATCH labels | ❌ Wave 0 |
| PLAN-10 | commit rejects payload fields | unit | model forbid | ❌ Wave 0 |
| PLAN-11 | missing/expired/discarded/consumed/conflict | unit | state matrix | ❌ Wave 0 |
| PLAN-12 | no embedder call on commit | unit | AsyncMock assert | ❌ Wave 0 |
| PLAN-17 | token cannot cross scope | unit | binding fields | ❌ Wave 0 |
| PLAN-18 | terminal no revive | unit | CAS table | ❌ Wave 0 |
| PLAN-19 | discard idempotent | unit + live | | ❌ Wave 0 |
| PLAN-20 | upsert dry_run still zero-write | regression | existing hash/service tests | ✅ |
| SAFE-11 | embed fail → no plan nodes | unit | | ❌ Wave 0 |
| TEST-05 | aggregate | gate runner | `python -m tests.catalog_phase3a_gate_runner` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** focused prepare unit file(s)
- **Per wave merge:** all new prepare tests + capabilities + models regression
- **Phase gate:** Phase 3A gate runner green + live Neo4j when available (truthful skip vs fail)

### Wave 0 Gaps

- [ ] `tests/test_catalog_prepare_models.py`
- [ ] `tests/test_catalog_prepared_artifact.py` (serialize/chunk/hash pure)
- [ ] `tests/test_catalog_token.py` (mint/digest/compare)
- [ ] `tests/test_catalog_prepare_service.py` (orchestration + spies)
- [ ] `tests/test_catalog_prepare_store.py` (Cypher builders / CAS unit)
- [ ] `tests/test_catalog_prepare_neo4j_int.py` (live hard-stop proof)
- [ ] `tests/catalog_phase3a_gate_runner.py` + `run_phase3a_gate.py`
- [ ] Shared preflight extraction tests (no behavior change to upsert)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | partial | Opaque unguessable plan_token (not user auth) |
| V3 Session Management | yes | Token one-time visibility; TTL; no raw storage |
| V4 Access Control | yes | group_id isolation; token scope binding |
| V5 Input Validation | yes | CatalogStrictModel; fixed labels; size ceilings |
| V6 Cryptography | yes | SHA-256 domain separation; secrets; compare_digest — never hand-roll |

### Known Threat Patterns

| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Token theft / replay after discard | Elevation | Terminal states; digest only; TTL |
| Timing oracle on token compare | Information | `hmac.compare_digest` |
| Token validity oracle | Information | Map discard→not_found; bounded messages |
| Cypher injection via labels | Tampering | Fixed server labels/properties |
| Control-plane DoS (many plans) | Denial | max_active_plans + payload ceilings |
| Embedding mid-write partial plan | Tampering | Embed before tx |
| Log leakage of token/payload | Information | SAFE-07 scrub; log plan_uuid/counts only |
| Cross-group commit | Elevation | Binding fields + group match on load |
| Client mutates payload post-prepare | Tampering | Token-only commit; frozen artifact |
| COMMITTING double domain write | Tampering | Phase 3A no domain; 3B single-tx + CAS |

### Logging / redaction

Log: `plan_uuid`, `batch_id`, `group_id`, counts, `state`, error codes, `artifact_sha256` prefix optional.  
Never: `plan_token`, token digest (optional allow digest prefix for support — prefer not), embeddings, request payload, source text.

### Fail-closed stop criteria

1. Neo4j cannot store/reassemble configured max artifact → **stop, report, do not weaken**
2. Cannot enforce capacity without race → redesign lock; do not ship best-effort count
3. Cannot avoid Entity label contamination → stop
4. Commit path would require re-embed → stop

## Plan Decomposition (planner hint)

| Wave | Focus | Exit |
|------|-------|------|
| 0 | TDD scaffolds, pure artifact/token helpers, models, config constants | RED tests collect |
| 1 | Store plan/chunk constraints + immutable create/load/CAS + capacity lock | Store unit green |
| 2 | Service prepare (shared preflight extract) + discard + commit claim/load | Service unit green; zero domain spies |
| 3 | MCP registration + capabilities truth + CATALOG_TOOL_NAMES | MCP unit green |
| 4 | Live Neo4j hard-stop suite + Phase 3A gate runner | `ready_for_phase_3b` candidate |

## Stop Conditions

| Condition | Action |
|-----------|--------|
| Live Neo4j rejects bounded immutable payload or corrupts reassembly | **Hard stop** — write report; no contract weakening |
| Official property limit found lower than ceilings | Lower hard ceilings; re-prove |
| Shared preflight extraction risks upsert regression | Extract with characterization tests first; do not fork second authority |
| Phase 3B domain write accidentally in 3A | Block merge; D-23 |

## Open Questions (RESOLVED)

1. **Discarded token error code mapping** — **RESOLVED**
   - Selected: discarded → `prepared_plan_not_found` (reduces token-validity oracle). Consumed → `prepared_plan_already_consumed`. Document in service error map and tests.

2. **Re-prepare same plan_id while PREPARED** — **RESOLVED**
   - Selected: always `prepared_plan_conflict`; never re-issue token for an existing plan identity in any state.

3. **Whether commit Phase 3A response includes full membership** — **RESOLVED**
   - Selected: counts + hashes + state only (no membership list, embeddings, or payload) to match prepare receipt hygiene.

4. **Pagination hard limits** — **RESOLVED**
   - Selected: stay **0** until Phase 4 read tools need them; capabilities continue to expose hard/configured page size as 0.

5. **Live Neo4j availability in CI** — **RESOLVED**
   - Selected: ordinary live suite may `pytest.skip` when Neo4j is unavailable. **Final Phase 3A readiness does not waive live proof**: skip or fail of the required immutable-artifact proof keeps `ready_for_phase_3b=false` and `features.prepare_commit=false`. No readiness waiver.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | ≥3.10 | — |
| neo4j driver | store | ✓ | 5.26.0 | — |
| Live Neo4j 5.26+ | hard-stop proof | probe at gate | — | skip int tests; **cannot** claim ready_for_3b without proof or explicit waiver |
| pytest | tests | ✓ | project | — |
| uv | tooling | ✓ | project | — |

**Missing dependencies with no fallback:** none for unit path; live Neo4j required for hard-stop closure.

## Code Examples

### Token digest (stdlib)

```python
# Pattern: secrets + domain-separated SHA-256 + hmac.compare_digest
import hashlib, hmac, secrets
DOMAIN = b'graphiti.catalog.plan_token.v1|'

def mint_plan_token() -> str:
    return secrets.token_urlsafe(32)

def plan_token_digest(token: str) -> str:
    return hashlib.sha256(DOMAIN + token.encode('utf-8')).hexdigest()

def plan_token_matches(token: str, stored: str) -> bool:
    return hmac.compare_digest(plan_token_digest(token), stored)
```

### Artifact hash

```python
# Reuse catalog_identity canonical JSON rules
raw = json.dumps(artifact_obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
artifact_bytes = raw.encode('utf-8')
artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
```

### Capacity + create (illustrative fixed Cypher)

```cypher
MERGE (lock:CatalogPlanGroupLock {group_id: $group_id})
WITH lock
OPTIONAL MATCH (p:CatalogPreparedPlan {group_id: $group_id})
WHERE p.state IN ['PREPARED', 'COMMITTING']
  AND (p.state = 'COMMITTING' OR p.expires_at > $now)
WITH lock, count(p) AS active
WHERE active < $max_active
CREATE (plan:CatalogPreparedPlan {
  uuid: $uuid, group_id: $group_id, /* allowlisted props only */
  state: 'PREPARED', token_digest: $token_digest
})
// then CREATE chunks...
RETURN plan.uuid AS uuid, active
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No Neo4j-documented hard STRING property max; 16 MiB app hard ceiling is safe | Neo4j Evidence | Must lower ceiling if field failures appear |
| A2 | Discarded → prepared_plan_not_found is acceptable oracle posture | Open Questions | May need explicit code later (append-only enum) |
| A3 | plan_id = batch_id\|request_sha256 is correct deterministic identity | Design §1 | Alternate plan_id recipe if product wants multi-prepare same batch hash |
| A4 | Group lock node acceptable control label | Capacity | If forbidden by future search rules, use other serialization |
| A5 | Phase 3A commit may leave state COMMITTING without domain rows | D-23 | Product may want prepare-only until 3B ships tools — still OK if commit tool returns clear state |

## Project Constraints (from CLAUDE.md)

- Preserve all existing MCP tools; additive only
- Neo4j 5.26+ only for catalog writes; no portability claim
- Server-derived UUIDv5; fixed namespace config
- Never interpolate client labels/properties into Cypher
- Writes return after commit/rollback
- Embeddings before write transactions
- group_id isolation; tests `oracle-catalog-tool-test` only
- Validate complete requests/limits before side effects
- Log ids/counts only — no payloads/credentials/tokens
- Ruff line length 100, single quotes; pyright basic for mcp_server
- No deployment, live-group writes, graph clearing, canary

## Sources

### Primary (HIGH confidence)

- Worktree source: `mcp_server/src/services/catalog_{service,store,identity,capabilities}.py`, `models/catalog_{common,batch,responses}.py`, `config/schema.py`, `graphiti_mcp_server.py`
- Phase 2 verification: `02-VERIFICATION.md` (`ready_for_phase_3a=true`)
- CONTEXT / REQUIREMENTS / ROADMAP / pre-canary roadmap Phase 3A section
- [Neo4j Cypher Manual — property types](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/)
- [Neo4j Operations Manual — memory](https://neo4j.com/docs/operations-manual/5/performance/memory-configuration/)
- [Bolt message framing](https://neo4j.com/docs/bolt/current/bolt/message/)

### Secondary (MEDIUM confidence)

- Practical property size community knowledge superseded by **application ceilings** due to missing official string max

### Tertiary (LOW confidence)

- None retained as authoritative

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — reuse only, no new packages
- Architecture: HIGH — locked decisions + verified seams
- Pitfalls / Neo4j ceilings: MEDIUM — no vendor hard string limit; live proof mandatory

**Research date:** 2026-07-18  
**Valid until:** 2026-08-18 (or next Neo4j major docs change)

---

*Phase: 03A-immutable-prepare-commit-control-plane*  
*Research complete: 2026-07-18*  
*No code modified; no commit performed (per instructions).*
