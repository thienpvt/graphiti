# Phase 3B: Atomic Catalog, Exact Evidence, and Durable Manifest Writes - Research

**Researched:** 2026-07-18
**Domain:** Neo4j 5.26 single-transaction catalog co-commit, exact evidence control records, durable batch manifests, stranded-COMMITTING recovery
**Confidence:** HIGH (existing catalog store/service seams + Phase 3A gate); MEDIUM (practical Neo4j property/tx ceilings — no official hard STRING max)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Phase 3B extends the existing Phase 3A token claim/load/revalidation seam; it does not replace or weaken token-only input, immutable artifact verification, or the `COMMITTING` state claim.
- **D-02:** Keep the Phase 3A claim as a separate transaction: `PREPARED -> COMMITTING`, with legal same-token `COMMITTING -> COMMITTING` re-entry. Open the domain success transaction only after claim and artifact verification succeed.
- **D-03:** One Neo4j success transaction must co-write domain entities, domain edges, provenance sources and Graphiti-compatible links, exact evidence records, durable manifest records, terminal `CatalogIngestBatch=committed`, and terminal prepared-plan `COMMITTED`.
- **D-04:** Use a deterministic write order inside that transaction: claim/recheck batch identity, entities, edges, provenance sources and compatibility links, exact evidence, manifest root/chunks, terminal batch status, terminal plan state. The planner may refine the order only to satisfy dependencies without creating another success transaction.
- **D-05:** Any exception before transaction exit rolls back every success artifact. No domain, evidence, manifest, committed status, or plan `COMMITTED` may survive a failed success transaction.
- **D-06:** Embeddings, payload, identities, membership, hashes, and projections come only from the frozen prepared artifact on commit. Commit performs no embedder, LLM, queue, HTTP, provider, or other external call.
- **D-07:** Recovery is deterministic resume-or-finish from the same verified frozen artifact. Never reset a timed-out or stranded plan to `PREPARED`; never mint replacement authority; never permit a mutable retry payload.
- **D-08:** Serialize recovery for a plan using transaction-local Neo4j locking/CAS authority. A same-token re-entry either observes a valid completed outcome or becomes the sole writer that reruns the complete idempotent success transaction.
- **D-09:** A plan is considered committed only when its terminal `COMMITTED` state, terminal committed batch status, and durable manifest agree on group, batch, request/catalog/artifact hashes, identity schema, and manifest consistency hash. Partial or contradictory terminal evidence fails closed.
- **D-10:** If valid terminal evidence already exists, return the stable committed logical receipt without rewriting domain/evidence/manifest records. Otherwise resume the complete success transaction from the frozen artifact.
- **D-11:** A permanent conflict rolls back the success transaction and returns a bounded structured error. The plan remains `COMMITTING` unless the same success transaction atomically reaches `COMMITTED`; it never revives to `PREPARED`.
- **D-12:** Persist one bounded non-`Entity` exact evidence control record per explicit canonical `CatalogEvidenceLink`, keyed by deterministic server-derived UUID and immutable content hash.
- **D-13:** Resolve each evidence source and its one typed entity-or-edge target within the same `group_id` and success transaction. Missing, duplicate, type-mismatched, endpoint-mismatched, or hash-conflicting targets fail atomically.
- **D-14:** Byte-identical duplicate evidence links coalesce to one logical record and one manifest member. Reuse of an evidence identity with divergent immutable source/target/content returns `provenance_link_conflict`.
- **D-15:** Exact evidence records and relationships use fixed server-owned labels/types/properties only. They never carry `Entity`, enter entity/vector/fulltext indexes, or participate in community clustering.
- **D-16:** Preserve Graphiti-compatible provenance interoperability: source `Episodic` nodes, explicit `MENTIONS` for entity evidence, and edge `episodes` membership remain available where supported by the explicit link. Never fabricate links or recreate the rejected Cartesian source-by-target behavior.
- **D-17:** Persist one deterministic non-`Entity` `CatalogBatchManifest` root plus ordered bounded server-owned membership chunks when needed, mirroring the proven Phase 3A root/chunk integrity pattern rather than one unbounded property.
- **D-18:** The manifest contains exact requested logical membership for entities, edges, provenance sources, and evidence links, including created, updated, and unchanged shared objects. Membership comes from the frozen prepared artifact, not live row counts.
- **D-19:** Entity/edge `batch_id` remains compatibility or last-change metadata only. It is never manifest membership authority.
- **D-20:** Store deterministic compact identities, UUIDs, exact category counts, group/batch scope, identity/canonicalization/catalog versions, request/catalog/artifact hashes, and a canonical manifest consistency hash. Chunks have deterministic ordering, offsets/counts, byte bounds, and per-chunk/full digests.
- **D-21:** Manifest creation is create-once/idempotent. Exact replay preserves byte-identical membership and ordering; same manifest identity with changed content or bindings fails closed as a manifest/batch conflict.
- **D-22:** Manifest/evidence read tools and manifest-backed verification remain Phase 4. Phase 3B implements persistence authorities and internal recovery reads only.
- **D-23:** Identical replay after successful commit returns the original stable logical outcomes and counts from durable authoritative state. It creates no duplicate domain, provenance, evidence, manifest, status, or terminal-plan records.
- **D-24:** Concurrent same-token commits yield one logical committed batch. Neo4j locks/CAS plus uniqueness constraints and create-once identities arbitrate the writer; followers recover or replay deterministically.
- **D-25:** Concurrent different tokens for the same group/batch/request identity either converge on the same committed manifest and stable replay or fail with the documented deterministic conflict. They never produce two logical manifests or duplicated domain/evidence.
- **D-26:** Refactor the existing `upsert_catalog_batch` write body into one shared atomic writer used by prepared commit and direct catalog-v2 upsert. Direct non-dry-run upsert must also co-write exact evidence, manifest, and terminal status so Phase 4 has one committed-batch authority. Preserve `dry_run=true` as zero-write.
- **D-27:** Optional failure recording occurs only after rollback in a separate transaction and stores bounded failure metadata. It must never imply domain success, create a manifest, or mark a prepared plan committed.
- **D-28:** Preserve all legacy MCP tools and existing catalog tool contracts. `commit_prepared_catalog_batch` remains token-only; its success response may add committed outcomes/counts without exposing payload, membership, embeddings, or token.
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

### Deferred Ideas (OUT OF SCOPE)
- `get_catalog_batch_manifest`, `get_catalog_evidence`, `resolve_typed_edges`, manifest-backed `verify_catalog_batch`, pagination, and read/write gate separation: Phase 4.
- Final security/compatibility matrix, long-term retention/cleanup jobs, observability, migration docs, offline hardened canary regeneration, and final readiness report: Phase 5.
- `LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`, automatic catalog-v1 migration, parser/extraction, new business entities, and non-Neo4j portability: future/out of scope.
- Canary execution, `oracle-catalog-v2` access, production migration, deployment, graph clearing, and existing-data deletion: separate explicit approval only.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAN-13 | One Neo4j success tx co-writes domain + evidence + manifest + terminal batch + terminal plan | Shared atomic writer inside `Neo4jDriver.transaction()`; order in Architecture |
| PLAN-14 | Failure rolls back success tx; optional post-rollback failed status only; stranded COMMITTING recovery rule | Existing `_record_failed_status` pattern; recovery algorithm below |
| PLAN-15 | Identical replay returns stable committed outcomes; no duplicates | Create-once identities + terminal agreement check before rewrite |
| PLAN-16 | Concurrent same-token → one logical commit | Tx-local plan/batch locks + CAS + uniqueness constraints |
| EVID-07 | Evidence targets resolve in group; miss/mismatch fail atomically | In-tx recheck after source/entity/edge writes; raise → full rollback |
| EVID-08 | Byte-identical coalesce; divergent identity → `provenance_link_conflict` | Reuse `coalesce_byte_identical_evidence_links` / `evidence_link_key` / content hash |
| EVID-09 | Graphiti Episodic + MENTIONS + edge `episodes` preserved for explicit links only | Existing source/mentions/episodes store methods; no Cartesian |
| EVID-10 | Detailed per-link evidence in non-Entity control records | New `CatalogEvidenceLink` node writes |
| EVID-11 | Evidence never Entity / entity indexes / communities | Fixed control label; no `name_embedding` |
| MANI-01 | Durable exact membership of entity/edge/source/evidence UUIDs + compact ids | Manifest root+chunks from frozen membership |
| MANI-02 | Includes unchanged shared objects; not live row counts | Membership from prepared artifact / preflight projection |
| MANI-03 | `batch_id` property never membership authority | Document + tests; verify never reads batch_id for membership |
| MANI-04 | Bounded non-Entity control records; deterministic identity + consistency hash | `catalog_manifest_uuid` + chunk helpers + chunk pattern |
| MANI-06 | Manifest + terminal status/plan in same success tx | Write order ends with status then plan COMMITTED |
| MANI-07 | Replay does not duplicate/reorder/rewrite manifest | Create-once + byte-identical consistency hash check |
| TEST-06 | Concurrency proofs (same token, no dup, no revive) | Unit + live Neo4j concurrent commit tests |
| TEST-07 | Evidence non-Cartesian, conflict fail-closed, exact links | Service/store/live evidence tests |
</phase_requirements>

## Summary

Phase 3B completes `commit_prepared_catalog_batch` after the Phase 3A claim seam: once a plan is verified and in `COMMITTING`, open **one** Neo4j success transaction that co-writes catalog domain data, Graphiti-compatible provenance links, exact non-Entity evidence records, a durable manifest root/chunks, terminal `CatalogIngestBatch=committed`, and plan `COMMITTED`. The Phase 3A claim transaction stays separate. Stranded `COMMITTING` recovers by resume-or-finish from the same frozen artifact under transaction-local locks — never `PREPARED` revival. Direct `upsert_catalog_batch` must call the same shared atomic writer so Phase 4 has one committed-batch authority.

Existing code already supplies the hard pieces: real commit/rollback (`Neo4jDriver.transaction`), single-tx domain write body in `upsert_catalog_batch` (~4790–5011), source/MENTIONS/episodes, batch claim/status, prepared plan CAS including `COMMITTING→COMMITTED`, frozen artifact membership with evidence UUIDs, pure evidence identity/hash/coalesce, and root/chunk serialization primitives. Gaps: exact evidence node persistence, manifest persistence, shared writer extraction, success-path recovery/replay, fault injection, concurrency proofs, and capability flag flips.

**Primary recommendation:** Extract one `_write_catalog_batch_atomic(tx, projection)` consumed by prepared commit and non-dry-run upsert; build projection from frozen artifact on commit (zero external I/O); lock plan+batch at success-tx entry; write domain → Graphiti provenance → evidence → manifest → terminal batch → plan `COMMITTED`; on re-entry return stable receipt when terminal triple agrees; hard-stop if live Neo4j cannot prove single-tx co-commit + full rollback under configured ceilings.

## Project Constraints (from CLAUDE.md)

- Python `>=3.10`, Ruff line length 100, single quotes, Pyright basic for mcp_server.
- Neo4j first, 5.26+; no unsupported multi-backend portability for catalog.
- Server-derived UUIDv5 only; never interpolate client labels/properties into Cypher.
- Writes return only after commit or rollback; group isolation; tests only `oracle-catalog-tool-test`.
- Log batch IDs and counts only — never credentials, payloads, source text, raw tokens, embeddings.
- Preserve all existing MCP tools; additive catalog behavior only.
- No deployment, live-group writes, canary, clear_graph, or existing-data deletion.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Token claim / artifact revalidation | API / Backend (`CatalogService`) | Database (plan CAS) | Phase 3A seam; stays separate claim tx |
| Shared atomic domain co-commit | Database / Storage (one Neo4j write tx) | Service orchestration | PLAN-13/MANI-06 atomicity |
| Exact evidence persistence | Database / Storage (control nodes) | Pure identity helpers | EVID-10/11 non-Entity |
| Durable manifest authority | Database / Storage (root+chunks) | Pure canonicalization | MANI-01..04; Phase 4 reads later |
| Graphiti search interop (Episodic/MENTIONS/episodes) | Database / Storage | — | EVID-09; explicit links only |
| Concurrent same-token arbitration | Database / Storage (locks+constraints) | Service recovery | PLAN-16; process locks insufficient |
| Failed status side write | Database / Storage (post-rollback) | — | Optional; never implies success |
| Capabilities feature flags | API / Backend (read-only) | — | Flip after live gate only |
| MCP token-only commit surface | API / Backend (FastMCP) | — | Preserve contract; extend success fields only |

## Current Architecture (verified seams)

### What already works [VERIFIED: codebase]

| Seam | Location | Phase 3B use |
|------|----------|--------------|
| Real tx commit/rollback | `graphiti_core/driver/neo4j_driver.py` `transaction()` | Success tx authority |
| Domain write order (entities→edges→sources→mentions→episodes→status) | `catalog_service.upsert_catalog_batch` ~4790–5011 | Extract into shared writer; extend with evidence+manifest+plan terminal |
| Batch claim + terminal status | `CatalogNeo4jStore.claim_batch_status` / `upsert_batch_status` | Start of success tx; end committed |
| Provenance lock + MENTIONS + edge episodes | store methods ~1131–1270 | Keep for EVID-09 |
| Plan CAS legal matrix includes COMMITTING→COMMITTED | `catalog_store._PLAN_CAS_LEGAL` | Terminal plan transition inside success tx |
| Frozen membership with evidence UUIDs | `prepare_catalog_batch` membership build ~5278–5348 | Manifest + evidence write input |
| Evidence pure helpers | `evidence_link_key`, `evidence_canonical_payload`, `coalesce_byte_identical_evidence_links`, `catalog_evidence_link_uuid` | Persist authority |
| Manifest UUID helper | `catalog_manifest_uuid` | Root identity |
| Chunk serialize/reassemble | `catalog_prepared_artifact.py` | Reuse for manifest body (new serialization version or shared chunk helpers) |
| Post-rollback failed status | `_record_failed_status` in upsert | Mirror for commit failures (D-27) |
| Commit claim seam stops at COMMITTING | `commit_prepared_catalog_batch` ~5663–5907 | Extend after claim with success writer |
| Features | `manifests=False`, `manifest_verification=False`, `prepare_commit=True` | Flip manifests (+ exact evidence write support) only after gate |

### Gaps (must build)

| Gap | Notes |
|-----|-------|
| Exact evidence store Cypher + constraints | Non-Entity label; create-once + content hash conflict |
| Manifest root/chunk store + constraints | Mirror plan chunk pattern; create-once |
| Pure manifest canonicalize + consistency hash | Compact membership body; deterministic order |
| Shared atomic writer extraction | One body for upsert + prepared commit |
| Prepared-commit success path + recovery | After COMMITTING: lock, agree-check, write or receipt |
| Commit response committed fields | counts/outcomes without payload/token |
| Fault-injection hooks at store boundaries | Tests only; prove full rollback |
| Concurrency + live atomicity proofs + Phase 3B gate | Block Phase 4 until green |

## Standard Stack

### Core (existing — no new packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| neo4j (Python driver) | 5.26.0 installed; require `>=5.26.0` | Async transactions, constraints | Project pin; real commit/rollback [VERIFIED: local install] |
| Pydantic | `>=2.11.5` | Strict models / responses | Project standard |
| pytest + pytest-asyncio | project pins | TDD + async tests | `workflow.tdd_mode` |
| Python stdlib `json`/`hashlib`/`hmac` | 3.10+ | Canonical hash, chunk digests | Already used by artifact/identity |
| mcp FastMCP | `>=1.27.2,<2` | Tool surface | Existing registration |

### Supporting (in-repo modules)

| Module | Purpose | When |
|--------|---------|------|
| `catalog_prepared_artifact` chunk helpers | Bounded base64 chunks | Manifest body storage |
| `catalog_identity` UUID/hash/evidence helpers | Deterministic IDs | All writes |
| `CatalogNeo4jStore` fixed Cypher | Safe parameterized writes | All Neo4j mutations |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Single success tx | Multi-tx saga with compensating deletes | **Forbidden** — D-03 hard stop if single-tx impossible |
| Process-local asyncio.Lock | Neo4j write locks | Insufficient cross-process; violates D-08/24 |
| Unbounded JSON property for membership | Root+chunks | Phase 3A proved chunking; D-17/29 forbid unbounded |
| New packaging / ORM | Raw store methods | YAGNI; existing pattern works |

**Installation:** none — no new packages.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none new)* | — | — | — | — | — | No installs |

**Packages removed due to [SLOP] verdict:** none  
**Packages flagged as suspicious [SUS]:** none

## Neo4j 5.26 Transaction and Sizing Evidence

### Official / verified findings

| Topic | Finding | Tag |
|-------|---------|-----|
| Property STRING max | No hard max documented in Cypher property types | [CITED: neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/] |
| Tx memory | Caps via `db.memory.transaction.max` / total.max; oversized tx aborted; DB stays healthy | [CITED: neo4j.com/docs/operations-manual/5/performance/memory-configuration/] |
| Driver semantics | `begin_transaction` → commit on clean exit, rollback on any `BaseException` | [VERIFIED: neo4j_driver.py] |
| Existing batch scale | Default 500 entities / 2000 edges / 5000 provenance links already written in **one** upsert tx today | [VERIFIED: catalog_service + catalog_common] |
| Hard batch ceilings | 5000 / 10000 / 20000 | [VERIFIED: catalog_common.py] |
| Plan chunk policy | DEFAULT 128 KiB, HARD 256 KiB, MAX 128 chunks, payload hard 16 MiB | [VERIFIED: catalog_prepared_artifact / catalog_common] |
| Driver pin | `neo4j==5.26.0` importable in research env | [VERIFIED: local] |

### Conservative ceilings (discretion recommendations)

Application-enforced only — Neo4j does not publish a vendor STRING hard max.

| Control | Default | Hard | Basis |
|---------|---------|------|-------|
| Manifest chunk bytes | 131_072 (128 KiB) | 262_144 (256 KiB) | Same as prepared artifact; proven live in 3A |
| Max manifest chunks | derived | 128 | Same hard as plan chunks |
| Manifest total membership bytes | 4 MiB configured | 16 MiB hard | Align prepared payload hard; fail closed pre-tx |
| Domain batch | existing config | existing hard | Do not raise in 3B |
| Single success tx policy | **all success artifacts** | — | If live proof fails at hard ceilings → **hard stop** |

**Rough membership size (compact records, no embeddings):**

| Scale | Members | Est. compact bytes | Chunks @128 KiB |
|-------|---------|--------------------|-----------------|
| Default (500/2000/100/5000) | ~7600 | ~2.1 MiB | ~17 |
| Hard (5000/10000/500/20000) | ~35500 | ~9.9 MiB | ~76 |

Both under 128-chunk and 16 MiB hard if membership stays compact (UUID + type + key + content hash + status). **Do not put embeddings in the manifest.** Embeddings stay on Entity/RELATES_TO only.

**Domain tx cost dominates** (entity embeddings + edge embeddings + Episodic content). Phase 3B adds O(evidence + manifest chunks) fixed-size control writes — incremental vs existing upsert. Live proof must still cover hard ceilings.

### Hard stop condition

If live Neo4j under test config cannot:

1. Commit domain + evidence + manifest + terminal batch + plan `COMMITTED` in **one** transaction at configured maxima, **or**
2. Rollback mid-write leaving zero partial domain/evidence/manifest/committed status/plan-COMMITTED,

then **stop and report**. Do not split success across transactions or weaken atomicity (ROADMAP gate 5 / CONTEXT domain).

## Architecture Patterns

### System Architecture Diagram

```text
Agent / MCP
  │
  ├─ prepare_catalog_batch ──► [Phase 3A] control-plane only
  │
  └─ commit_prepared_catalog_batch(plan_token [, expected_request_sha256])
        │
        ├─ Tx0 (claim, existing): load digest → reassemble artifact → verify binding
        │     CAS PREPARED→COMMITTING | re-enter COMMITTING
        │     NO domain/evidence/manifest
        │
        └─ Tx1 (success, NEW — single tx):
              lock plan node (SET uuid=uuid)
              lock/claim batch status (writing / hash check)
              IF terminal triple agrees (plan COMMITTED + batch committed + manifest hash)
                   → return stable receipt (no rewrite)  [exit without further writes]
              ELSE
                   entities (from frozen membership+embeddings)
                   edges
                   Episodic sources + MENTIONS + edge.episodes   (explicit links only)
                   CatalogEvidenceLink control records
                   CatalogBatchManifest root + ordered chunks
                   CatalogIngestBatch status=committed
                   plan CAS COMMITTING→COMMITTED
              any raise → full rollback of Tx1
        │
        └─ optional Tx2 post-rollback: bounded batch status=failed only
              (never plan COMMITTED, never manifest)

upsert_catalog_batch (non-dry-run)
  preflight → embed → Tx1 shared writer (no plan terminal; no frozen artifact required)
  dry_run: zero writes (unchanged)
```

### Recommended Project Structure (touch map)

```text
mcp_server/src/
├── models/
│   ├── catalog_common.py          # optional manifest hard constants if not already
│   └── catalog_responses.py       # commit success committed fields / counts
├── services/
│   ├── catalog_identity.py        # catalog_manifest_chunk_uuid; manifest consistency hash helpers
│   ├── catalog_manifest.py        # NEW pure: canonicalize membership → bytes/hash/chunks
│   ├── catalog_prepared_artifact.py  # reuse chunk_artifact_bytes / reassemble
│   ├── catalog_store.py           # evidence+manifest Cypher, constraints, writers, recovery reads
│   ├── catalog_service.py         # shared writer; commit success path; upsert refactor
│   └── catalog_capabilities.py    # features.manifests (+ evidence write) after gate
├── graphiti_mcp_server.py         # response fields only if needed; no new tools required
└── tests/
    ├── test_catalog_manifest.py           # pure canonicalize/chunk
    ├── test_catalog_evidence_store.py     # store unit + conflict
    ├── test_catalog_atomic_writer.py      # service unit + fault inject
    ├── test_catalog_commit_recovery.py    # stranded COMMITTING / replay
    ├── test_catalog_concurrency.py        # same-token / same-batch races
    ├── test_catalog_commit_neo4j_int.py   # live atomicity, search interop, control exclusion
    └── test_catalog_phase3b_gate_runner.py
```

### Pattern 1: Shared atomic writer projection

**What:** One internal dataclass/dict projection consumed by store writes — never rebuild from client request on prepared commit.

**Projection fields (minimum):**

- `group_id`, `batch_id`, `batch_uuid`, `request_sha256`, `catalog_sha256`, `artifact_sha256` (nullable for direct upsert), `identity_schema_version`, `canonicalization_version`
- `entities[]`: uuid, type, graph_key, content_sha256, projected_status, embeddings, write params
- `edges[]`: same pattern
- `sources[]`: existing prepared source shape + entity/edge link sets from **explicit** evidence only
- `evidence_links[]`: uuid, link_key, content_sha256, source_uuid, target_kind, target_uuid, allowlisted properties
- `manifest`: compact membership lists + counts + consistency hash + chunk list
- `plan` (optional): token_digest, plan_uuid — only prepared-commit path sets terminal plan

**When:** Always for non-dry-run domain commit paths.

### Pattern 2: Transaction-local locking / recovery

At **start** of success tx (fixed labels/params only):

```cypher
// Plan write lock + re-read (prepared path)
MATCH (p:CatalogPreparedPlan {uuid: $plan_uuid, group_id: $group_id})
SET p.uuid = p.uuid
RETURN p.state AS state, p.request_sha256 AS request_sha256, ...

// Batch claim (existing)
MERGE (b:CatalogIngestBatch {uuid: $batch_uuid, group_id: $group_id})
...
```

Recovery decision inside same tx:

1. Load plan state, batch status, manifest root (if any).
2. **Committed agreement** (D-09): `plan.state==COMMITTED` AND `batch.status==committed` AND manifest exists AND all of `{group_id,batch_id,request_sha256,catalog_sha256,identity_schema_version,manifest_sha256}` match frozen artifact → return receipt, **no further writes**.
3. Partial terminal (e.g. batch committed without plan COMMITTED, or manifest hash mismatch) → **fail closed** (`batch_conflict` / `manifest_mismatch` / `prepared_plan_conflict`); rollback; leave plan `COMMITTING`.
4. Else run full idempotent write sequence.

Same-token concurrent writers: Neo4j serializes on plan/batch/manifest unique nodes; loser either observes agreement or reruns idempotent creates.

### Pattern 3: Exact evidence control record

**Label:** `CatalogEvidenceLink` only (never `Entity`, never `Episodic`).

**Recommended properties (allowlist):**

`uuid`, `group_id`, `batch_id`, `link_key`, `content_sha256`, `source_uuid`, `target_kind` (`entity`|`edge`), `target_uuid`, `evidence_kind`, `locator_json` (bounded serialized locator or null), `excerpt` (optional, max `MAX_EVIDENCE_LENGTH`), `extractor_name`, `extractor_version`, `rule_id`, `confidence`, `created_at`, `updated_at`

**Constraints:**

- UNIQUE `(uuid, group_id)`
- UNIQUE `(group_id, link_key)` (or uuid alone if link_key embedded in uuid material — prefer both)

**Write semantics:** CREATE-once / MERGE with create token pattern mirroring sources; if exists with different `content_sha256` → `provenance_link_conflict` and abort tx.

**Graphiti interop (separate from control record):**

- Source still `Episodic` via existing upsert
- Entity targets: existing `MENTIONS` only when explicit entity evidence exists
- Edge targets: append `episodes` only when explicit edge evidence exists
- Never invent links from sources×targets Cartesian (already rejected at model layer)

### Pattern 4: Durable manifest root + chunks

**Labels:** `CatalogBatchManifest`, `CatalogBatchManifestChunk`  
**Never:** `Entity`, searchable embeddings.

**Root identity:** `catalog_manifest_uuid(ns, group_id, batch_id)` [exists]

**Chunk identity:** add

```python
def catalog_manifest_chunk_uuid(ns, group_id, batch_id, chunk_index) -> str:
    # material: group_id|catalog-v2|ManifestChunk|{batch_id}|{index}
```

**Canonical membership body (hashed; no self-hash field):**

```json
{
  "manifest_serialization_version": "catalog-manifest-v1",
  "canonicalization_version": "catalog-canonical-v1",
  "identity_schema_version": "catalog-v2",
  "catalog_schema_version": "catalog-schema-v1",
  "group_id": "...",
  "batch_id": "...",
  "request_sha256": "...",
  "catalog_sha256": "...",
  "artifact_sha256": null,
  "counts": {"entities":N,"edges":N,"sources":N,"evidence_links":N},
  "entities": [{"uuid","entity_type","graph_key","content_sha256","projected_status"}],
  "edges": [{"uuid","edge_type","edge_key","content_sha256","projected_status"}],
  "sources": [{"uuid","source_key","content_sha256","projected_status"}],
  "evidence_links": [{"uuid","link_key","content_sha256"}]
}
```

- Sort each list by stable key (`graph_key` / `edge_key` / `source_key` / `link_key`).
- `manifest_sha256 = sha256(canonical_bytes)`.
- Chunk with `chunk_artifact_bytes` (reuse); store root metadata + chunks like prepared plans.
- Membership **includes unchanged** from frozen/preflight projection (MANI-02).
- Create-once: same uuid + different `manifest_sha256` → conflict + rollback.

### Pattern 5: Deterministic write order (D-04)

1. Lock plan (prepared path) + claim/recheck batch identity  
2. Entities  
3. Edges  
4. Provenance sources + MENTIONS + edge episodes  
5. Exact evidence control records  
6. Manifest root + chunks  
7. Terminal batch `committed`  
8. Terminal plan `COMMITTED` (prepared path only)

Dependencies: evidence targets must exist before evidence create; manifest after membership outcomes known (outcomes may refine projected→actual status for created/updated/unchanged counts on response, but **manifest membership UUIDs come from request membership**, not post-filter).

### Anti-Patterns to Avoid

- **Second success transaction** for manifest or plan terminal — hard stop violation
- **Reset COMMITTING→PREPARED** on timeout — second writer / mutable retry
- **Membership from `MATCH ... batch_id`** — MANI-03 violation
- **Evidence as Entity** or vector-indexed props — pollutes search/communities
- **Cartesian source×target MENTIONS** — EVID-06/14 already forbid request shape; do not reintroduce at write
- **External calls inside success tx or between claim and success** — D-06 / PLAN-12
- **Logging token / payload / excerpt / embeddings** — SAFE-07
- **Duplicating upsert body instead of extracting** — drift between paths
- **Process-local locks only** — multi-worker unsafe

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tx commit/rollback | Manual flags | `Neo4jDriver.transaction()` | Already correct |
| Opaque chunking | Custom framing | `chunk_artifact_bytes` / `reassemble_artifact_bytes` | Proven 3A |
| Evidence identity/hash | Ad-hoc strings | `evidence_link_key` + `canonical_sha256` | Single authority |
| Manifest UUID | Client IDs | `catalog_manifest_uuid` | IDEN-11 |
| Timing / CAS | Application sleep | Neo4j write locks + uniqueness | Cross-process |
| Strict validation | Hand parsers | Existing strict models + store allowlists | CONT/SAFE |

**Key insight:** Domain atomic batch already exists; Phase 3B is **extend + extract + control-plane terminal**, not a new storage engine.

## Common Pitfalls

### Pitfall 1: Claim tx vs success tx race window
**What goes wrong:** Two workers both claim COMMITTING then both write.  
**Why:** Claim is intentionally separate (D-02).  
**How to avoid:** Success-tx plan/batch locks + idempotent create-once + terminal agreement short-circuit.  
**Warning signs:** Duplicate MENTIONS attempts, constraint errors not mapped to stable receipt.

### Pitfall 2: Partial terminal agreement
**What goes wrong:** Batch committed, plan still COMMITTING, or manifest missing after crash mid-success (should be impossible if single tx — unless bug splits writes).  
**Why:** Logic bug or multi-tx regression.  
**How to avoid:** All success artifacts in one tx; recovery treats partial as fail-closed conflict.  
**Warning signs:** Recovery inventing data or resetting to PREPARED.

### Pitfall 3: Manifest membership drift vs request
**What goes wrong:** Manifest lists only physically updated rows; unchanged shared entities omitted.  
**Why:** Building membership from write results instead of frozen membership.  
**How to avoid:** Manifest from artifact/preflight membership always.  
**Warning signs:** Phase 4 verify false missing members.

### Pitfall 4: Oversized single property
**What goes wrong:** Entire membership JSON in one property → memory pressure / aborted tx.  
**Why:** Skipping chunking.  
**How to avoid:** Root+chunks; enforce hard chunk/total ceilings pre-tx.  
**Warning signs:** `TransientError` / tx memory kill on large batches.

### Pitfall 5: Evidence written without target lock
**What goes wrong:** Target deleted/changed concurrently → dangling or wrong type.  
**Why:** Missing under-lock recheck.  
**How to avoid:** Reuse `lock_provenance_targets` pattern for evidence targets; fail atomic.  
**Warning signs:** Intermittent missing_endpoint in races only.

### Pitfall 6: Direct upsert diverges from prepared commit
**What goes wrong:** Phase 4 verify works only for prepare/commit path.  
**Why:** Forgot D-26 shared writer.  
**How to avoid:** One `_write_catalog_batch_atomic`; both paths call it.  
**Warning signs:** Upsert batches lack manifest.

### Pitfall 7: Failed status implies success
**What goes wrong:** `status=failed` written in success tx or with manifest.  
**Why:** Mixing D-27 side tx with success path.  
**How to avoid:** Failed status only after rollback, separate tx; never plan COMMITTED.  
**Warning signs:** Manifest present with failed status.

## Code Examples

### Success transaction skeleton

```python
# Source pattern: catalog_service.upsert_catalog_batch + neo4j_driver.transaction
async with client.driver.transaction() as tx:
    await store.lock_prepared_plan(tx, plan_uuid=..., group_id=...)  # prepared path
    claim = await store.claim_batch_status(tx, params=...)
    if claim_conflict(claim):
        raise BatchStatusConflict(...)
    if await store.terminal_commit_agrees(tx, projection):
        return build_stable_receipt(projection)  # no further writes
    await write_entities(tx, projection)
    await write_edges(tx, projection)
    await write_sources_and_graphiti_links(tx, projection)
    await write_evidence_links(tx, projection)
    await write_manifest_root_and_chunks(tx, projection)
    committed = await store.upsert_batch_status(tx, params=committed_params)
    if committed['status'] != 'committed':
        raise BatchStatusConflict('commit_rejected')
    if projection.plan_token_digest:
        await store.cas_plan_state(
            tx,
            token_digest=projection.plan_token_digest,
            expected_from=PLAN_STATE_COMMITTING,
            to_state=PLAN_STATE_COMMITTED,
            updated_at=now,
        )
# any exception → driver rolls back entire success tx
```

### Fault injection boundary (tests)

```python
# Wrap store methods in tests:
async def boom(*a, **k):
    raise RuntimeError('inject_after_entities')
monkeypatch.setattr(store, 'upsert_edge_item', boom)
# assert: no Entity/edge/evidence/manifest/committed/plan-COMMITTED rows for batch
```

### Manifest consistency hash

```python
body = build_manifest_body_from_membership(...)  # sorted lists, no self-hash
raw = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
manifest_sha256 = hashlib.sha256(raw).hexdigest()
chunks = chunk_artifact_bytes(raw, chunk_size=DEFAULT_CHUNK_BYTES)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Cartesian sources×targets | Explicit `CatalogEvidenceLink` only | Phase 2 / EVID-14 | 3B persists explicit links only |
| Membership via `batch_id` property | Durable manifest | Phase 3B | batch_id informational only |
| Upsert domain-only atomic | Domain+evidence+manifest atomic | Phase 3B | One authority for Phase 4 |
| Commit stops at COMMITTING | Commit finishes COMMITTED in success tx | Phase 3B | Completes prepare/commit path |
| `features.manifests=false` | true after live gate | Phase 3B gate | Capability truthfulness |

**Deprecated/outdated:**

- Treating `entity.batch_id` / `edge.batch_id` as membership (forbidden for verify)
- Multi-tx “eventual” manifest write
- Timeout reset of COMMITTING → PREPARED

## Commit Path Algorithms (implementation-ready)

### A. `commit_prepared_catalog_batch` (extends Phase 3A)

1. Existing: digest → load root → token match → state machine → reassemble → binding verify → CAS claim COMMITTING.  
2. **NEW:** Build projection from artifact membership + `request_canonical` (no embedder).  
3. Ensure schema (identity + plan + **evidence + manifest** constraints) **before** success tx (schema DDL may be auto-commit elsewhere — keep outside success tx like upsert).  
4. Open success tx → Pattern 2 recovery/write.  
5. Map conflicts to existing codes: `batch_conflict`, `provenance_link_conflict`, `prepared_plan_conflict`, `neo4j_transaction_failed`, `missing_endpoint`, etc.  
6. On success: response `state=COMMITTED` plus stable counts/outcomes (discretion: include entity/edge/source/evidence counts and created/updated/unchanged; never token/payload/embeddings).  
7. On failure after claim: plan stays COMMITTING; optional failed batch status side tx; return structured error (retryable when transient).

### B. `upsert_catalog_batch` non-dry-run

1. Keep preflight + embed-before-tx.  
2. Replace inline write loop with shared writer.  
3. Build evidence list from request via same coalesce/conflict rules as prepare.  
4. Build manifest from **request membership including unchanged projections**.  
5. No plan terminal.  
6. dry_run unchanged zero-write.

### C. Stranded COMMITTING recovery (D-07..11)

| Observation after lock | Action |
|------------------------|--------|
| Terminal triple agrees | Return stable receipt; no rewrite |
| Plan COMMITTED but batch/manifest disagree | Fail closed; do not repair |
| Plan COMMITTING; no/incomplete success artifacts | Rerun full idempotent success tx from frozen artifact |
| Permanent domain conflict | Rollback success tx; leave COMMITTING; structured error |
| Expired PREPARED | Already handled in claim path; COMMITTING ignores TTL for recovery |

## Response and capabilities (discretion)

**Commit success additions (safe):** `state='COMMITTED'`, `batch_uuid`, counts, optional item outcomes if already in batch response shape — **no** membership listing, raw token, embeddings, excerpts.

**Capabilities after gate:**

- `features.manifests = True` when persist path + live proof green  
- Keep `manifest_verification = False` until Phase 4  
- Optionally surface `explicit_evidence_links` remains True (already); no new secret fields

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`asyncio_mode=auto`) |
| Config file | `mcp_server/pytest.ini` |
| Quick run command | `cd mcp_server && pytest tests/test_catalog_manifest.py tests/test_catalog_atomic_writer.py tests/test_catalog_evidence_store.py -q` |
| Full suite command | `cd mcp_server && pytest tests/test_catalog_*.py -q` |
| Live Neo4j | `pytest tests/test_catalog_commit_neo4j_int.py -q` (requires bolt; group `oracle-catalog-tool-test` only) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| PLAN-13 | Single-tx co-commit all success artifacts | unit + live | `pytest tests/test_catalog_atomic_writer.py tests/test_catalog_commit_neo4j_int.py -q` | ❌ Wave 0 |
| PLAN-14 | Rollback complete; recovery from COMMITTING | unit + live | `pytest tests/test_catalog_commit_recovery.py -q` | ❌ Wave 0 |
| PLAN-15 | Replay stable no dups | unit + live | same + concurrency | ❌ Wave 0 |
| PLAN-16 | Concurrent same-token one logical commit | concurrency + live | `pytest tests/test_catalog_concurrency.py -q` | ❌ Wave 0 |
| EVID-07 | Missing/mismatch target atomic fail | unit + live | `pytest tests/test_catalog_evidence_store.py -k target -q` | ❌ Wave 0 |
| EVID-08 | Coalesce + conflict | unit | `pytest tests/test_catalog_evidence_store.py -k coalesce -q` | partial pure exists; persist ❌ |
| EVID-09 | MENTIONS/episodes only for explicit links | service + live | search interop live tests | ❌ Wave 0 |
| EVID-10 | Control records retained | store + live | evidence store tests | ❌ Wave 0 |
| EVID-11 | No Entity label on evidence | store + live | label assertion tests | ❌ Wave 0 |
| MANI-01..04,06,07 | Manifest persist/idempotent/bounds | pure + store + live | `pytest tests/test_catalog_manifest.py -q` | ❌ Wave 0 |
| TEST-06 | Concurrency matrix | concurrency | concurrency module | ❌ Wave 0 |
| TEST-07 | Evidence non-Cartesian + conflict | unit + service | evidence tests | partial models; persist ❌ |
| D-30 | Fault inject each boundary | unit | inject suite in atomic writer tests | ❌ Wave 0 |
| D-33 | capabilities.manifests true only post-gate | unit | extend `test_catalog_capabilities.py` | ✅ extend |
| SAFE-01 | group isolation | all live | fixture group assert | ✅ pattern |

### Sampling Rate

- **Per task commit:** quick pure/unit commands above  
- **Per wave merge:** full `test_catalog_*.py` excluding optional live if Neo4j down (report skip truthfully)  
- **Phase gate:** live Neo4j green + gate runner `ready_for_phase_4=true` before Phase 4

### Wave 0 Gaps

- [ ] `mcp_server/tests/test_catalog_manifest.py` — pure canonicalize/chunk/hash (MANI-*)  
- [ ] `mcp_server/tests/test_catalog_evidence_store.py` — store create-once/conflict/labels (EVID-*)  
- [ ] `mcp_server/tests/test_catalog_atomic_writer.py` — shared writer + fault injection (PLAN-13/14, D-30)  
- [ ] `mcp_server/tests/test_catalog_commit_recovery.py` — stranded COMMITTING / agreement (PLAN-14/15)  
- [ ] `mcp_server/tests/test_catalog_concurrency.py` — same-token / same-batch (PLAN-16, TEST-06)  
- [ ] `mcp_server/tests/test_catalog_commit_neo4j_int.py` — live atomicity, search interop, control exclusion, group isolation  
- [ ] `mcp_server/tests/test_catalog_phase3b_gate_runner.py` — HEAD-bound ledger like 3A  
- [ ] Extend `test_catalog_capabilities.py` for manifests flag gate  
- [ ] Extend upsert service tests: dry_run still zero-write; non-dry-run writes manifest

*(Existing prepare/upsert suites remain regression nets — do not delete.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | MCP transport outside phase |
| V3 Session Management | no | — |
| V4 Access Control | yes | `group_id` isolation; token digest authority; no cross-group writes |
| V5 Input Validation | yes | Strict Pydantic; fixed allowlists; no client Cypher identifiers |
| V6 Cryptography | yes | UUIDv5 namespace; SHA-256 content/manifest; `hmac.compare_digest` for tokens |

### Known Threat Patterns for Neo4j catalog co-commit

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher injection via labels/props | Tampering | Fixed server labels/properties only |
| Cross-group read/write | Elevation | Every MATCH/MERGE includes `group_id` |
| Token oracle / raw token storage | Info disclosure | Digest-only; not_found mapping for discard |
| Partial commit as success | Tampering | Single success tx; terminal triple agreement |
| Log leakage of excerpts/payloads | Info disclosure | Log IDs/counts/codes only |
| Evidence as searchable Entity | Elevation / pollution | Non-Entity control label; no embeddings |
| Constraint race as silent merge | Tampering | Map uniqueness to conflict; no silent rewrite |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | 3.12.10 | — |
| uv | deps | ✓ | 0.11.29 | — |
| neo4j Python driver | store | ✓ | 5.26.0 | — |
| pytest | tests | ✓ | on PATH | — |
| Live Neo4j bolt | live int tests | ✗ AuthError at default `bolt://localhost:17687` | — | Skip live with truthful skip; gate requires live when configured |
| Node/gsd-tools | planning only | ✓ | — | — |

**Missing dependencies with no fallback:**

- Live Neo4j with valid credentials for **gate** live proof (not required for pure/unit planning/coding, required for `ready_for_phase_4`)

**Missing dependencies with fallback:**

- Live Neo4j for day-to-day unit work → mock tx / store unit tests

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Compact manifest membership ~280 B/member is adequate for ceiling math | Neo4j sizing | Underestimate chunks; still fail-closed if over hard max |
| A2 | Schema DDL for new constraints stays outside success tx (same as existing ensure_schema) | Architecture | If schema must be in-tx, redesign ensure path |
| A3 | Direct upsert should set `artifact_sha256=null` on manifest but still store request/catalog hashes | Manifest body | Document explicitly in plan |
| A4 | Commit response may gain committed counts without breaking clients (additive fields) | Responses | If MCP clients reject extra fields, keep optional/defaulted |
| A5 | Neo4j write locks via `SET n.uuid = n.uuid` remain sufficient under 5.26 community | Locking | If not, add explicit batch/plan lock nodes |

## Open Questions

1. **Exact commit response schema fields**  
   - What we know: token-only input; success may add counts/outcomes (D-28).  
   - Unclear: whether to embed full per-item results like upsert.  
   - Recommendation: return aggregate counts + `state=COMMITTED` + hashes; omit per-item list unless already required by existing commit response model — keep bounded.

2. **Live Neo4j credentials in this worktree**  
   - What we know: AuthError at default URI during research.  
   - Unclear: operator env for gate.  
   - Recommendation: gate runner skip-live vs fail per Phase 1/3A truthfulness pattern; do not claim live green without probe.

3. **Whether failed status is written for every commit failure class**  
   - Discretion: recommend yes for domain/tx failures (mirror upsert); no for pure token not_found/expired (no batch scope). Correctness independent of side tx.

## Likely File Touch Map

| File | Change |
|------|--------|
| `mcp_server/src/services/catalog_store.py` | Evidence+manifest schema/constraints/writes/reads; plan lock helper; terminal agree query |
| `mcp_server/src/services/catalog_service.py` | Shared writer; commit success path; upsert refactor; recovery |
| `mcp_server/src/services/catalog_manifest.py` | **NEW** pure manifest body/hash/chunk |
| `mcp_server/src/services/catalog_identity.py` | `catalog_manifest_chunk_uuid` (+ any hash helper) |
| `mcp_server/src/services/catalog_capabilities.py` | Flip `manifests` after gate |
| `mcp_server/src/models/catalog_responses.py` | Commit committed fields |
| `mcp_server/src/models/catalog_common.py` | Manifest constants if needed |
| `mcp_server/tests/*` | Wave 0 suites + gate runner |
| `mcp_server/src/graphiti_mcp_server.py` | Only if response wiring needs touch; no new tool names required |

## Sources

### Primary (HIGH confidence)

- Worktree source: `catalog_service.py`, `catalog_store.py`, `catalog_prepared_artifact.py`, `catalog_identity.py`, `catalog_capabilities.py`, `catalog_evidence.py`, `neo4j_driver.py`
- Phase 3A: `03A-CONTEXT.md`, `03A-RESEARCH.md`, `03A-VERIFICATION.md` (`ready_for_phase_3b=true`)
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `graphiti_mcp_pre_canary_roadmap_en.md` §Phase 3B
- Local `import neo4j` → 5.26.0

### Secondary (MEDIUM confidence)

- Neo4j Ops Manual 5 memory configuration (tx memory caps)  
- Neo4j Cypher Manual property types (no documented STRING hard max)

### Tertiary (LOW confidence)

- Membership byte estimates for hard ceilings (engineering estimate; enforce measured live proof)

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — no new packages; reuse verified seams  
- Architecture: HIGH — extends existing single-tx upsert + 3A claim  
- Pitfalls: HIGH — derived from prior phases + concurrent CAS experience  
- Neo4j absolute property limits: MEDIUM — application ceilings + live proof required  

**Research date:** 2026-07-18  
**Valid until:** 2026-08-17 (30 days; re-check if Neo4j major/driver pin changes)

---

*Phase: 3B-atomic-catalog-exact-evidence-and-durable-manifest-writes*  
*Research complete: 2026-07-18*
