# Architecture Research

**Domain:** Catalog-v2 pre-canary hardening for deterministic catalog MCP tools
**Researched:** 2026-07-17
**Confidence:** HIGH (repo-sourced live catalog modules + PROJECT.md v1.1 scope)

## Standard Architecture

### System Overview

Catalog-v1 is live. Seven MCP tools, identity helpers, service orchestration, and a dedicated Neo4j store already exist beside the semantic Graphiti path. Catalog-v2 hardens that substrate: breaking FE/BO identity grammar, server-owned endpoint maps, full-domain hashing, capabilities, restart-safe immutable prepared plans, exact evidence links, durable manifests, typed-edge resolve, manifest-backed verify, and split read/write gates.

**No silent identity migration.** Preserve tool names and legacy semantic tools. Catalog-v2 **intentionally breaks** seven deterministic request identity/provenance/hash contracts where required — do not claim old catalog-v1 request payloads remain accepted. Identities are never silently reinterpreted.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MCP TRANSPORT (FastMCP) — mcp_server/src/graphiti_mcp_server.py              │
│ UNCHANGED (14 legacy semantic tools): add_memory, search_*, add_triplet, …  │
│ LIVE v1 CATALOG (7): upsert_typed_entities|edges, resolve_typed_entities,    │
│   verify_catalog_batch, upsert_provenance, upsert_catalog_batch,             │
│   get_catalog_ingest_status                                                  │
│ v2 ADDITIVE: get_catalog_capabilities, resolve_typed_edges,                  │
│   prepare_catalog_batch, commit_prepared_catalog_batch, discard_prepared_catalog_batch,        │
│   get_catalog_batch_manifest, get_catalog_evidence                     │
│   (+ verify_catalog_batch gains manifest-backed mode)                        │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ sync await; no QueueService
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ BOUNDARY                                                                     │
│ MODIFIED models/catalog_*  — recursive extra=forbid; FE/BO grammar;          │
│   endpoint-map refs; full-domain hash fields; evidence-link + manifest DTOs  │
│ MODIFIED services/catalog_identity.py — v2 name-string rules; domain hash    │
│ MODIFIED services/catalog_service.py  — gates, prepare/commit, verify modes  │
│ NEW     services/catalog_endpoint_map.py — finite server edge→endpoint map   │
│ NEW     services/catalog_plan.py — immutable prepared plan + token lifecycle │
│ NEW     services/catalog_manifest.py — durable commit manifest assembly      │
│ MODIFIED services/catalog_store.py — control nodes, CAS, evidence, manifest  │
│ config CatalogConfig — split write/read gates; plan TTL; capabilities flags  │
│ DOES NOT call LLMClient / QueueService / Graphiti.add_episode|add_triplet    │
└───────────┬──────────────────────────────┬───────────────────────────────────┘
            │ embedder (pre-domain-tx)     │ Neo4j 5.26+ only
            ▼                              ▼
┌──────────────────────┐   ┌───────────────────────────────────────────────────┐
│ EmbedderClient       │   │ CatalogNeo4jStore                                 │
│ (existing)           │   │ DOMAIN: Entity + typed labels, RELATES_TO,        │
│                      │   │   Episodic, MENTIONS (searchable)                 │
│                      │   │ CONTROL (never Entity):                           │
│                      │   │   CatalogIngestBatch (v1 status — keep)           │
│                      │   │   CatalogPreparedPlan (v2 NEW)                    │
│                      │   │   CatalogBatchManifest (v2 NEW)                   │
│                      │   │   CatalogEvidenceLink (v2 NEW, non-Entity)        │
└──────────────────────┘   └───────────────────────┬───────────────────────────┘
                                                   ▼
                               Neo4jDriver.transaction() — real commit/rollback
```

### Component Responsibilities

| Component | Status | Responsibility |
|-----------|--------|----------------|
| FastMCP tool adapters | MODIFY (register) | Thin `@mcp.tool`; Pydantic in, structured out; no Cypher |
| 14 legacy semantic tools | UNCHANGED | Preserve contracts; never route catalog through them |
| 7 v1 catalog tools | KEEP (+ verify mode) | Deterministic sync path; v2 must not break them |
| `CatalogConfig` | MODIFY | `enabled` write gate, optional `reads_enabled`, namespace, limits, plan TTL/capacity, capabilities surface |
| `models/catalog_*` | MODIFY | Recursive forbid-unknown; immutable flags; FE/BO keys; endpoint map fields; evidence + manifest DTOs |
| `catalog_identity.py` | MODIFY | UUIDv5 + canonical SHA-256; v2 identity name grammar; full-domain batch hash |
| `catalog_endpoint_map.py` | NEW | Finite server map edge_type → allowed (source_type, target_type) pairs |
| `catalog_service.py` | MODIFY | Orchestration: validate → identity → map check → hash → embed → tx; prepare/commit/discard; verify modes |
| `catalog_plan.py` | NEW | Immutable prepared plan hash, token mint, replay equality, discard semantics |
| `catalog_manifest.py` | NEW | Exact post-commit inventory (uuids, hashes, counts, evidence ids) |
| `catalog_store.py` | MODIFY | Domain MERGEs + control-plane nodes; CAS; bounded state; no conflict repair |
| `GraphitiService.client` | REUSE | driver + embedder only |
| `QueueService` / LLM | OUT OF PATH | |

## Recommended Project Structure

```
mcp_server/src/
├── graphiti_mcp_server.py          # MODIFY: register v2 tools; leave 14+7 intact
├── config/schema.py                # MODIFY: CatalogConfig split gates + plan bounds
├── models/
│   ├── catalog_common.py           # MODIFY: error codes, FE/BO prefixes, map constants
│   ├── catalog_entities.py         # MODIFY: recursive forbid; v2 graph_key grammar
│   ├── catalog_edges.py            # MODIFY: endpoint types validated vs server map
│   ├── catalog_provenance.py       # MODIFY: exact evidence-link payload (no Cartesian)
│   ├── catalog_batch.py            # MODIFY: prepare/commit/discard + domain hash fields
│   ├── catalog_responses.py        # MODIFY: capabilities, plan, manifest, evidence DTOs
│   └── catalog_manifest.py         # NEW (or section in responses): durable manifest shape
├── services/
│   ├── catalog_identity.py         # MODIFY: v2 name strings + full_domain_sha256
│   ├── catalog_endpoint_map.py     # NEW: EDGE_ENDPOINT_MAP + check helpers
│   ├── catalog_plan.py             # NEW: prepare token + immutability checks
│   ├── catalog_manifest.py         # NEW: build/read manifest records
│   ├── catalog_service.py          # MODIFY: gates, prepare/commit, resolve_typed_edges
│   └── catalog_store.py            # MODIFY: control labels, CAS, evidence, manifest CRUD
└── tests/
    ├── test_catalog_identity.py    # MODIFY: FE/BO isolation, domain hash
    ├── test_catalog_models.py      # MODIFY: recursive forbid, endpoint map, flags
    ├── test_catalog_service.py     # MODIFY: prepare/commit ordering, gates
    ├── test_catalog_store_unit.py  # MODIFY: control nodes never Entity
    ├── test_catalog_neo4j_int.py   # MODIFY: restart-safe plan; manifest; isolation
    ├── test_catalog_endpoint_map.py# NEW
    ├── test_catalog_plan.py        # NEW
    └── test_catalog_manifest.py    # NEW
```

### Structure Rationale

- **Stay in `mcp_server`:** catalog-v2 is product/admin surface, not `graphiti_core`.
- **New modules for map/plan/manifest:** keep service under control; pure helpers unit-testable without Neo4j.
- **Modify store, do not fork:** one Neo4j-first store; control labels coexist with domain writes.
- **No silent v1 identity migration module:** separate docs only; identities never auto-rewritten.

## Architectural Patterns

### Pattern 1: Additive tools, shared service

**What:** New MCP tools call the same `CatalogService` singleton as v1. v1 methods remain; v2 methods added.
**When:** All v2 surface.
**Trade-offs:** Larger service file; one gate/config path; no dual clients.

### Pattern 2: Validate → map → identity → domain-hash → (prepare: store payload) / (commit: embed → one domain+control success tx)

**What:** Hard ordering. Side effects only after full validation. Embeddings never inside domain write tx.
**When:** Every write / prepare / commit.
**Trade-offs:** More preflight work; zero partial domain graph on embed fail.

```
1. Feature/backend/namespace/split-gate checks
2. Pydantic recursive validation (extra=forbid)
3. Server endpoint-map check (edges) — fail closed
4. UUIDv5 identity (v2 grammar when catalog_version=v2)
5. Full-domain canonical hash (entities+edges+provenance+flags)
6. Optional client hash assert
7. Embeddings (create_batch) — outside Neo4j write
8. Domain write transaction (entities → edges → provenance/evidence)
9. Control-plane writes (plan state / manifest / batch status) — separate tx boundaries as specified
10. Return structured result only after commit or full rollback
```

### Pattern 3: Control nodes never Entity

**What:** `CatalogIngestBatch`, `CatalogPreparedPlan`, `CatalogBatchManifest`, `CatalogEvidenceLink` use fixed non-`Entity` labels. No `name_embedding`. Invisible to `search_nodes` / entity fulltext.
**When:** All bookkeeping / evidence indexes.
**Trade-offs:** Separate read APIs required (`get_catalog_*`); correct isolation from semantic graph.

### Pattern 4: Immutable prepared plan + opaque token

**What:** `prepare_catalog_batch` validates/resolves/projects, hashes domain, and persists `CatalogPreparedPlan` with **bounded immutable canonical payload** (chunked non-Entity nodes if needed), `plan_sha256`, `domain_sha256`, counts, expiry, status=`prepared`. **Does not compute required embeddings. Does not write domain entities.** Returns opaque token once (hash stored). `commit_prepared_catalog_batch(token)` loads plan + payload, embeds from stored payload **before** domain tx, then in **one Neo4j transaction** writes domain + evidence + manifest + terminal batch status + plan terminal state. `discard_prepared_catalog_batch` marks discarded. Restart-safe: payload+plan in Neo4j, not process memory. Hashes/counts alone are **insufficient** prepare storage.
**When:** Agent multi-step ingest needing restart safety.
**Trade-offs:** Larger control nodes / chunks; bounded plan store (TTL + max open plans per group).

### Pattern 5: Server-owned edge endpoint map

**What:** Finite map in code (not client): e.g. `Contains → {(Schema,Table),(Table,Column),…}`. Checked before any write. Reject `endpoint_type_mismatch` without repair.
**When:** `upsert_typed_edges`, batch, prepare, `resolve_typed_edges`.
**Trade-offs:** Map updates are code changes; required for fail-closed typing.

### Pattern 6: Exact evidence links (no Cartesian)

**What:** Provenance links are explicit `(source_key, target_ref)` rows. No expand-all sources × all targets. Identity: UUIDv5(`group_id|Evidence|source_uuid|target_kind|target_uuid`) or retain Mentions uuid scheme for entity links; edge episode attach stays installed Graphiti list semantics.
**When:** v2 provenance + evidence read API.
**Trade-offs:** Callers list links; avoids 5k-link explosions from nested product.

### Pattern 7: Split read/write gates

**What:** `catalog_upsert.enabled=false` blocks mutations (upsert/prepare/commit) but `reads_enabled` (default true when feature present) keeps resolve/verify/status/manifest/capabilities/evidence reads.
**When:** Pre-canary / rollback windows.
**Trade-offs:** Two flags; clearer ops than all-or-nothing.

### Pattern 8: No conflict repair

**What:** On `deterministic_uuid_conflict`, type conflict, uniqueness failure: fail closed, rollback, surface code. Never DROP constraints, never rewrite uuid, never merge dissimilar types.
**When:** All store paths.
**Trade-offs:** Ops may need manual cleanup in test group only; production safe.

## Data Flow

### Key Data Flows

1. **Legacy-named direct upserts:** request → gate → identity → embed → domain tx → response. Catalog-v2 may fail closed on v1-shaped identity/provenance/hash payloads; tool **names** preserved.
2. **v2 prepare → commit:** request → validation/resolution/projections + domain hash → control tx write `CatalogPreparedPlan` **+ full bounded payload** (no embed, no domain) → token; later `commit_prepared_catalog_batch(token)` → load payload → **embed** → **one** domain+evidence+manifest+status+plan-terminal tx.
3. **v2 discard:** token → plan=`discarded` (no domain write).
4. **resolve_typed_edges (NEW read):** edge refs → UUIDv5 + MATCH endpoints/types/map → report missing/generic/mismatch/unembedded — no write.
5. **manifest-backed verify / get_catalog_batch_manifest / get_catalog_evidence:** load control nodes by group+batch → compare live graph / return inventory.
6. **get_catalog_capabilities:** pure config/code surface after server init — works even when catalog **writes** disabled.
7. **Search interop:** domain Entity/RELATES_TO only; control labels excluded.

### Request Flow — prepare / commit (atomicity)

```
prepare_catalog_batch
  validate+map+identity+domain_hash (+ projections)
  NO embeddings
  control tx: MERGE CatalogPreparedPlan {status:prepared, plan_sha256, domain_sha256, expires_at}
              + store bounded immutable CANONICAL PAYLOAD (chunked non-Entity children OK)
  return prepare_token once  # no domain Entity/edge mutation

commit_prepared_catalog_batch(prepare_token)
  load plan+payload by token+group_id
  reject: prepared_plan_not_found | prepared_plan_expired | prepared_plan_conflict
          | prepared_plan_already_consumed | content_hash_mismatch
  embed ALL texts from STORED payload  # before domain tx
  ONE Neo4j tx: domain entities/edges + evidence + CatalogBatchManifest
                + terminal batch status + plan terminal state
  on failure: full rollback of that tx; optional separate failure-status tx only
  never open domain write if gate off / plan invalid
```

### State Management

| State | Storage | Restart-safe | Entity-searchable |
|-------|---------|--------------|-------------------|
| Domain catalog nodes/edges | Neo4j Entity/RELATES_TO | Yes | Yes |
| Provenance episodic + MENTIONS | Neo4j Episodic | Yes | Episode paths only |
| Batch status | `CatalogIngestBatch` | Yes | No |
| Prepared plan + canonical payload | `CatalogPreparedPlan` (+ chunk children) | Yes | No |
| Commit manifest | `CatalogBatchManifest` | Yes | No |
| Evidence link index | `CatalogEvidenceLink` and/or MENTIONS | Yes | No (control) / mention path |
| Process memory | none for plans | N/A | N/A |

**Bounded state:** max open prepared plans per `group_id`; TTL expiry; discard/commit free slots. Expired plans not auto-committed.

### Token lifecycle

```
mint (prepare) → prepared
  ├─ commit success → committed (terminal)
  ├─ discard → discarded (terminal)
  ├─ expire → expired (terminal; not commitable)
  └─ commit fail → prepared (retry) OR failed_commit (policy: prefer remain prepared for exact retry)
```

Token is server secret-ish opaque id derived from UUIDv5(`group_id|PrepareToken|batch_id|plan_sha256`) or random uuid stored on plan — **not** caller identity authority for domain objects.

## Transaction Boundaries

| Operation | Domain tx | Control tx | Embed timing | Atomicity claim |
|-----------|-----------|------------|--------------|-----------------|
| `upsert_typed_entities` | 1 write | none | before domain | All entities in request commit or roll back together |
| `upsert_typed_edges` | 1 write | none | before domain | All edges; endpoints must pre-exist |
| `upsert_provenance` | 1 write | none | before if needed | Sources+links |
| `upsert_catalog_batch` | 1 domain | status after | all before domain | Domain all-or-nothing; status may persist failed after rollback |
| `prepare_catalog_batch` | **none** | 1 plan + **payload** write | **none** | Plan+payload durable; **zero domain mutation** |
| `commit_prepared_catalog_batch` | domain+evidence+manifest+terminal status+plan terminal **same tx** | (included) | **at commit from payload** | Single atomic success unit; post-rollback failure status optional |
| `discard_prepared_catalog_batch` | none | 1 plan update | none | No domain |
| resolve / verify / status / manifest / evidence / capabilities | read | read | none | No writes |
| Schema ensure (constraints) | auto-commit DDL | — | — | CREATE IF NOT EXISTS only; fail closed on duplicates; **no repair** |

**Neo4j semantics bound claims:** one `async with driver.transaction()` = one atomic unit. Cross-tx (domain then status) is **not** single atomic unit — by design so failed status can be recorded after domain rollback. Prepare and domain commit are deliberately separate so prepare cannot leave half-entities.

**Embeddings before domain write:** absolute. Embed fail → `embedding_failed`, no domain tx.

## Control-Plane Labels (server-owned)

| Label | Purpose | Key properties |
|-------|---------|----------------|
| `CatalogIngestBatch` | v1 status (keep) | uuid, group_id, batch_id, status, counts, hashes, timestamps |
| `CatalogPreparedPlan` | v2 immutable plan | uuid/token, group_id, batch_id, status, plan_sha256, domain_sha256, expires_at, embedding_fingerprint, counts |
| `CatalogBatchManifest` | v2 durable exact inventory | uuid, group_id, batch_id, domain_sha256, entity_uuids[], edge_uuids[], evidence_ids[], counts, committed_at |
| `CatalogEvidenceLink` | v2 exact link index (if not solely MENTIONS) | uuid, group_id, source_uuid, target_kind, target_uuid, confidence, content_sha256 |

All constrained by `group_id`. Composite uniqueness `(uuid, group_id)` pattern from v1 store. Never dual-label with `Entity`.

## Canonicalization Flow

```
item fields (identity keys excluded from content hash)
  → strip protected props
  → reject non-finite floats
  → json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)
  → sha256 → 64 lowercase hex

full_domain_sha256 =
  canonical_sha256({
    'catalog_version': 'v2',
    'group_id', 'batch_id',
    'entities': [entity_canonical… ordered stable],
    'edges': [edge_canonical…],
    'provenance': [explicit links…],
    'flags': {atomic, dry_run, … allowed immutables}
  })
```

**v2 identity grammar (breaking, fail-closed):** graph_key / name strings visibly isolate FE, BO, COMMON (e.g. required zone segment or prefix policy defined in models). FE and BO objects with same logical name produce **different** UUIDv5 names (`group_id|entity_type|graph_key` still formula; graph_key carries zone). **No auto-migration** of v1 keys.

## Read Paths

| API | Gate | Data source |
|-----|------|-------------|
| `resolve_typed_entities` | read | MATCH Entity by uuid/key |
| `resolve_typed_edges` NEW | read | MATCH RELATES_TO + endpoint types + map |
| `verify_catalog_batch` | read | Live graph; optional manifest mode |
| `get_catalog_ingest_status` | read | CatalogIngestBatch |
| `get_catalog_batch_manifest` NEW | read | CatalogBatchManifest |
| `get_catalog_evidence` NEW | read | Evidence / MENTIONS by source or batch |
| `get_catalog_capabilities` NEW | read | Config + code constants (maps, limits, versions) |
| `search_nodes` / `search_memory_facts` | legacy | Domain only; control invisible |

## Failure Modes

| Failure | When | Effect | Code |
|---------|------|--------|------|
| Unknown field / bad grammar | model validate | No side effects | `validation_error` |
| Write gate off | any mutate | No side effects; reads OK if split gate | `feature_disabled` |
| Bad namespace | gate | No side effects | `invalid_uuid_namespace` |
| Over limits | gate | No side effects | `batch_limit_exceeded` |
| Client hash ≠ server | pre-tx | No side effects | `content_hash_mismatch` |
| Endpoint map miss | pre-tx | No side effects | `endpoint_type_mismatch` |
| Missing / generic endpoint | pre-tx or in-tx MATCH | Rollback if in tx | `missing_endpoint` / `generic_endpoint_conflict` |
| Type / uuid conflict | in-tx | Rollback; no repair | `entity_type_conflict` / `deterministic_uuid_conflict` |
| Embedder down | pre-tx | No Neo4j domain write | `embedding_failed` |
| Neo4j error | in-tx | Full rollback of that tx | `neo4j_transaction_failed` |
| Plan expired / not prepared | commit | No domain write | `batch_conflict` or dedicated `plan_invalid` |
| Plan payload drift | commit | No domain write | `content_hash_mismatch` |
| Duplicate open plan | prepare | Reject | `batch_conflict` |
| Schema uniqueness blocked by dirty data | ensure | Fail closed | `neo4j_transaction_failed` / schema code |

## Integration Points

### External Services

| Service | Pattern | Notes |
|---------|---------|-------|
| Neo4j 5.26+ | `GraphitiService.client.driver` + `transaction()` | Only supported backend for catalog writes |
| Embedder | `client.embedder` | Same as semantic; pre-domain-tx only |
| LLM | none | Catalog path must work if LLM broken |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| MCP tools ↔ CatalogService | async call | Thin adapters |
| CatalogService ↔ identity/map/plan/manifest helpers | pure functions | No I/O in identity/map |
| CatalogService ↔ CatalogNeo4jStore | methods + tx | All Cypher in store |
| CatalogService ↔ Embedder | create_batch | Before domain tx |
| Catalog ↔ QueueService | none | |
| Catalog ↔ Graphiti write APIs | none | No add_episode/add_triplet |
| Domain graph ↔ search | shared Entity indexes | Control labels excluded |
| v1 tools ↔ v2 tools | shared service/store | No identity reinterpretation |

### Existing Analogs (reuse map)

| Need | Live symbol | Action |
|------|-------------|--------|
| Tool registration | `graphiti_mcp_server.py` catalog tools | Add v2 tools same pattern |
| Orchestration | `CatalogService` | Extend methods |
| Identity | `catalog_identity.py` | Extend; keep v1 functions |
| Store + constraints | `CatalogNeo4jStore` | Add control labels; CREATE only |
| Status pattern | `CatalogIngestBatch` | Template for plan/manifest |
| Embed-before-tx | service entity/edge paths | Reuse ordering |
| Endpoint existence | edge upsert MATCH | Extend with map |
| Semantic tools | 14 legacy | Unchanged |

## Phased Build Order (dependency-aware)

Preserves atomicity and compatibility: pure/validation first, no domain write changes until maps+hashes land, prepare before commit, manifest before manifest-verify, tests per layer. **No canary / no production write / no v1 mass rewrite.**

```
P0  Config split gates + capabilities constants
      → CatalogConfig.reads_enabled / write enabled; capabilities DTO fields
P1  Models: recursive extra=forbid; immutable flags; v2 identity grammar validators
      → unit tests only (no Neo4j)
P2  catalog_endpoint_map + wire into edge model/service preflight
      → unit tests; fail closed before any store change
P3  Full-domain hash in catalog_identity + optional request fields
      → unit tests; v1 per-item hash still works
P4  resolve_typed_edges (read) + get_catalog_capabilities (read)
      → MCP register; prove split-gate reads while writes disabled
P5  Store: CatalogPreparedPlan CRUD + constraints; catalog_plan helpers
      → unit + neo4j int (test group only)
P6  prepare_catalog_batch + discard_prepared_catalog_batch
      → control write with full payload; no embed; assert zero domain mutation
P7  Store: CatalogBatchManifest + CatalogEvidenceLink (exact links)
      → unit + neo4j int
P8  commit_prepared_catalog_batch
      → load payload → embed → one tx domain+evidence+manifest+terminals; concurrency
P9  get_catalog_batch_manifest + get_catalog_evidence
      → read APIs
P10 verify_catalog_batch manifest-backed mode
      → compare live vs manifest
P11 Compatibility suite: 14 legacy + 7 v1 tools green; search interop;
      control nodes absent from search_nodes; group isolation
P12 Docs: migration guidance (manual), regenerated-canary procedure (do not run)
```

### Phase gates (suggested)

| Gate | Must pass before |
|------|------------------|
| G1 models+map+hash unit | any store control write |
| G2 prepare/discard int (no domain leak) | commit implementation |
| G3 commit+manifest int + concurrency | manifest-backed verify |
| G4 full compatibility + security (no Cypher inject, no Entity control) | milestone verify / canary *planning* only |

### What not to build in this order

- Automatic v1→v2 identity rewrite
- Parser / full ingest / canary execution
- Conflict repair / DROP CONSTRAINT
- Queue or LLM integration
- Writes outside `oracle-catalog-tool-test`

## Scaling Considerations

| Scale | Adjustment |
|-------|------------|
| Unit / fixture batches | Default limits; single prepare |
| ~14k entities / 30k edges | Chunk by limits; sequential commits per group; manifests per batch_id |
| Concurrent same group | Plan CAS on batch_id; one prepared plan wins; no silent merge |
| Restart mid-flight | Resume via token; expire stale plans |

### Scaling Priorities

1. **Prepare payload size** — chunk non-Entity control nodes; never hashes-only.
2. **Embed latency** — batch embed at **commit** from stored payload.
3. **Tx size** — enforce limits; never one-shot full catalog.
4. **Open plan cardinality** — TTL + max-open; discard path.

## Anti-Patterns

### Anti-Pattern 1: Silent v1 identity reinterpretation

**What people do:** Accept old graph_keys under v2 uuid formula without zone segment.
**Why wrong:** FE/BO collision; non-auditable migration.
**Instead:** Fail closed on grammar; document manual migration; never auto-rewrite.

### Anti-Pattern 2: Domain writes or embeddings inside prepare

**What people do:** MERGE entities at prepare for speed, or embed at prepare and store only hashes.
**Why wrong:** Discard leaves orphans; hashes-only prepare cannot rehydrate commit; wrong embed timing.
**Instead:** Prepare = control plane + full bounded canonical payload only; embed at commit.

### Anti-Pattern 3: Split success path across txs without atomic domain+manifest+terminal

**What people do:** Commit domain in one tx then best-effort manifest/status in another as the success path.
**Why wrong:** Domain can succeed without durable manifest/terminal plan state.
**Instead:** On success, one Neo4j tx writes domain + evidence + manifest + terminal batch status + plan terminal state. Separate post-rollback failure-status tx is allowed only for failure reporting.

### Anti-Pattern 4: Cartesian provenance expansion

**What people do:** Every source links every entity in batch.
**Why wrong:** Limit blowups; false evidence.
**Instead:** Explicit evidence link list only.

### Anti-Pattern 5: Control label + Entity

**What people do:** `:Entity:CatalogPreparedPlan` for “reuse indexes”.
**Why wrong:** Pollutes hybrid search and communities.
**Instead:** Non-Entity control labels + dedicated read APIs.

### Anti-Pattern 6: Embed inside domain transaction

**What people do:** Open tx, call embedder, write.
**Why wrong:** Long locks; embed fail aborts mid-flight.
**Instead:** Embed fully before domain tx (v1 Pattern retained).

### Anti-Pattern 7: Caller UUID / token as domain identity

**What people do:** Client supplies entity uuid or reuses prepare token as node uuid.
**Why wrong:** Breaks UUIDv5 determinism.
**Instead:** Server UUIDv5 for domain; token only addresses plan row.

### Anti-Pattern 8: Conflict repair

**What people do:** On uniqueness failure, DELETE duplicate and retry.
**Why wrong:** Data loss; hides corruption.
**Instead:** Fail closed; operator resolves in test group manually.

## Compatibility Contract (explicit)

| Surface | v1.1 rule |
|---------|-----------|
| 14 legacy MCP tools | Bit-compatible behavior |
| 7 catalog tool **names** | Preserve names + semantic tools; v2 breaks request identity/provenance/hash contracts where required — no claim that v1 payloads remain accepted |
| Identity namespace env | Unchanged immutability rule |
| Search interop | Domain entities remain searchable |
| group_id isolation | All ops; tests only `oracle-catalog-tool-test` |
| Neo4j-only catalog writes | Unchanged |
| No queue / no LLM on catalog path | Unchanged |

## Error Code Surface (v1 + v2)

**v1 retained:** `validation_error`, `feature_disabled`, `invalid_uuid_namespace`, `batch_limit_exceeded`, `content_hash_mismatch`, `entity_type_conflict`, `graph_key_prefix_mismatch`, `deterministic_uuid_conflict`, `missing_endpoint`, `endpoint_type_mismatch`, `generic_endpoint_conflict`, `edge_identity_conflict`, `batch_conflict`, `provenance_target_missing`, `neo4j_transaction_failed`, `embedding_failed`, `internal_error`, `backend_unavailable`.

**v2 required (approved names):** `unsupported_identity_schema`, `invalid_system_key`, `edge_endpoint_pair_not_allowed`, `prepared_plan_not_found`, `prepared_plan_expired`, `prepared_plan_conflict`, `prepared_plan_already_consumed`, `manifest_mismatch`, `provenance_link_conflict`.

## Test Architecture

| Layer | Focus |
|-------|-------|
| Unit identity/map/hash | FE/BO isolation; domain hash stability; map rejects |
| Unit models | Recursive forbid; immutable flags |
| Service ordering | Embed before domain; prepare no domain; commit order |
| Store unit | Control labels; no Entity; no DROP |
| Neo4j int | Restart plan; commit/discard; manifest verify; isolation; concurrency |
| Compatibility | Legacy 14 + v1 7 + search_nodes ignore control |
| Security | No client label interpolation; group isolation |

Forbidden: production groups, canary execution, clear_graph, conflict repair tests that delete live data.

## Sources

- `.planning/PROJECT.md` — v1.1 active requirements, constraints, out-of-scope
- Live `mcp_server/src/services/catalog_{identity,service,store}.py`
- Live `mcp_server/src/models/catalog_*.py`
- Live `mcp_server/src/graphiti_mcp_server.py` — tool registration
- Live `mcp_server/tests/test_catalog_*.py`
- `.planning/codebase/ARCHITECTURE.md` — Graphiti layers
- Prior `.planning/research/ARCHITECTURE.md` (v1.0) — replaced by this document

---
*Architecture research for: Catalog-v2 pre-canary hardening*
*Researched: 2026-07-17*
*Confidence: HIGH — integration points from live source; atomicity bounded to Neo4j single-tx; build order dependency-aware; no hidden v1 rewrite*
