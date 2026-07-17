# Phase 2: Provenance and Atomic Batch - Research

**Researched:** 2026-07-17
**Domain:** Deterministic Neo4j catalog provenance, restart-safe batch status, atomic multi-object upsert
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Provenance Representation
- Represent each deterministic source as an installed-schema `Episodic` node, not an `Entity`; derive its UUIDv5 from `group_id|Source|source_key` and its canonical SHA-256 from allowlisted mutable source metadata.
- Link a source episode to each existing entity target with deterministic `MENTIONS` relationships using server-derived link identities.
- Attach source identity to existing `RELATES_TO` facts through Graphiti's existing `episodes` list, because Neo4j cannot connect a relationship directly to another relationship without inventing a new schema object.
- Preserve exact `reference_time`; store only bounded, allowlisted source metadata. Never call `add_episode`, an LLM, or the ingestion queue.
- Validate every entity and edge target before writes. Any missing or mistyped target returns `provenance_target_missing`; atomic provenance requests write nothing.
- Identical source and links return `unchanged`; changed mutable source metadata updates the existing deterministic episode while preserving `created_at`.

#### Persistent Batch Status
- Persist status as a dedicated `CatalogIngestBatch` node without the `Entity` label, so existing entity search and community clustering exclude it by construction.
- Derive batch UUIDv5 from `group_id|Batch|batch_id`; scope every lookup and write by both deterministic UUID and `group_id`.
- Persist only request/catalog hashes, lifecycle status, bounded counts, timestamps, and bounded sanitized error summaries. Never persist full requests, raw documents, complete source text, or credentials.
- Support `planned`, `validating`, `embedding`, `writing`, `committed`, and `failed`; terminal status survives service restart because Neo4j is authoritative.
- Dry-run creates no persistent status. Successful batch commit writes `committed` inside the domain transaction. A write failure rolls back domain changes, then best-effort persists `failed` in a separate transaction.
- A committed batch ID with the same request hash returns unchanged. Reuse with a different hash returns `batch_conflict` without mutation.

#### Atomic Batch Orchestration
- Require `atomic=true` for `upsert_catalog_batch`; reject non-atomic mode rather than imply weaker whole-batch guarantees.
- Validate the complete nested request and configured entity, edge, and provenance limits before any persistent side effect.
- Reuse Phase 1 canonicalization, identity, allowlist, conflict, endpoint, parameter, and response helpers; avoid routing through standalone tools because those own separate transactions.
- Coalesce identical same-request identities; reject divergent duplicate identities before embedding or writing.
- Resolve edge endpoints against the union of validated same-request entities and existing correctly typed Neo4j entities. Never create an implicit or generic endpoint.
- Detect all known entity, edge, batch, source, target, and hash conflicts before embedding. Recheck invariants inside the transaction for races.
- Generate every needed entity and edge embedding before opening the domain transaction. Embedding failure produces no graph or status write.
- Use one Neo4j transaction for changed entities, changed edges, provenance, and committed batch state. Retry with identical content creates one logical set of objects.

#### Operator Guidance and Verification
- Document all seven catalog tools as an administrative structured-ingestion surface and distinguish them from semantic `add_memory` ingestion.
- Document immutable namespace consequences, allowlists, limits, idempotency, atomicity, structured errors, Graphiti/Neo4j provenance limitations, and community-neutral upsert behavior.
- Include sanitized ACCEPT_TAB and Kubernetes ConfigMap/environment examples plus rollout and rollback guidance. Do not deploy or expose credentials.
- Integration tests use only `oracle-catalog-tool-test`, cover service reinitialization, retries, conflicts, rollback, search interoperability, and explicit safe `build_communities` execution.
- Final report records all seven MCP schemas and exact format, lint, type-check, unit, integration, image-build, and unchanged-live-group results. Recommend a fresh canary only.

### Claude's Discretion
- Exact Pydantic decomposition, internal helper boundaries, Cypher layout, result field naming, bounded error-summary shape, and plan slicing may follow the smallest secure design consistent with Phase 1 patterns.

### Deferred Ideas (OUT OF SCOPE)
FalkorDB or other backend support, production deployment, live `oracle-catalog-v2` writes, full 14,106-entity ingestion, automatic community creation, graph repair/migration tooling, and production canary execution remain out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDEN-03 | Source UUIDv5 over `group_id\|Source\|source_key` | Extend `catalog_identity.py` with `catalog_source_uuid` mirroring entity/edge helpers |
| IDEN-04 | Batch UUIDv5 over `group_id\|Batch\|batch_id` | Extend identity helpers with `catalog_batch_uuid`; status store keys on it |
| PROV-01 | `upsert_provenance` MCP tool | New models + `CatalogService.upsert_provenance` + tool registration |
| PROV-02 | Deterministic source UUID/hash/time/attrs | Canonical source payload + preserve `reference_time` + allowlisted attrs |
| PROV-03 | Installed Graphiti Episodic/MENTIONS/episodes; no add_episode/LLM/queue | Reuse stock labels/rel types via catalog store Cypher; never call Graphiti ingest |
| PROV-04 | Link entities via MENTIONS; facts via `RELATES_TO.episodes` | Store write primitives for episode, MENTIONS, episodes-list append |
| PROV-05 | Missing targets → `provenance_target_missing`, no partial write | Preflight target resolve; atomic fail-closed like entity atomic path |
| PROV-06 | Idempotent provenance; no generic domain entity | Hash compare + MERGE by deterministic UUID; label only `Episodic` |
| STAT-01 | `CatalogIngestBatch` non-Entity status node | Dedicated label; no `Entity` |
| STAT-02 | Persist UUID/IDs/hashes/timestamps/status/counts/errors | Bounded property map only |
| STAT-03 | Status enum planned→…→committed/failed | Literal status field + validators |
| STAT-04 | Never store secrets/payloads/raw docs | Allowlist properties; log counts only |
| STAT-05 | `get_catalog_ingest_status` restart-safe | Neo4j read by batch_id+group_id after reinit |
| STAT-06 | Status excluded from entity search/communities | No `Entity` label; community queries match `:Entity` only |
| BATC-01 | `upsert_catalog_batch` nested request | Composite request model + service orchestration |
| BATC-02 | Full nested validation before side effects | Pydantic + service limit gates before status/embed/tx |
| BATC-03 | Committed batch_id + different hash → `batch_conflict` | Status pre-read + request_sha256 compare |
| BATC-04 | Same-request + Neo4j endpoint union | In-memory entity map unioned with store endpoint resolve |
| BATC-05 | All conflicts before domain writes | Shared preflight before embed |
| BATC-06 | Embed all before domain tx | Phase 1 order preserved at batch scope |
| BATC-07 | One tx: entities+edges+provenance+committed status | `driver.transaction()` multi-primitive write |
| BATC-08 | Domain failure rollback + separate failed status tx | Exception path: rollback automatic; second best-effort status write |
| BATC-09 | Identical committed batch returns unchanged | Short-circuit on committed + same hash |
| BATC-10 | Dry-run: full validation, no writes/status | Skip schema ensure + status + domain tx |
| BATC-11 | ACCEPT_TAB fixture suite | Live Neo4j tests under `oracle-catalog-tool-test` |
| BATC-12 | Safe `build_communities` after batch; never in upsert | Explicit test-only call; upsert path never invokes it |
| DOCS-01..05 | Seven tools, config, distinction, samples, final report | README + sanitized samples + Phase 2 report |
</phase_requirements>

## Summary

Phase 2 extends the Phase 1 catalog foundation with three additive MCP tools: `upsert_provenance`, `get_catalog_ingest_status`, and `upsert_catalog_batch`. Provenance must use installed Graphiti 0.29.2 primitives — `(:Episodic)` sources, `[:MENTIONS]` entity links, and `RELATES_TO.episodes` fact provenance — without `add_episode`, LLM extraction, or the queue. Batch status lives on a non-`Entity` `CatalogIngestBatch` node so stock search and community clustering ignore it. Atomic batch reuses Phase 1 prepare/embed/conflict helpers inside one Neo4j transaction and persists `failed` only after domain rollback in a separate best-effort write.

Phase 1 already ships identity helpers, allowlists, nested validation, embed-before-tx ordering, atomic entity/edge writers, composite uniqueness constraints, provenance presence reads (entity MENTIONS only), and four MCP tools (18 total). Phase 2 should extend those modules rather than invent parallel stacks. Critical implementation constraints: do not use stock `SET n = $map` episode save queries (they wipe preserve-on-update semantics); do not let edge upsert overwrite `episodes` with `[]` after provenance attaches; require `atomic=true` for the batch tool; keep all tests on `oracle-catalog-tool-test`.

**Primary recommendation:** Extend `catalog_identity` / `catalog_store` / `catalog_service` with source+batch identity, Episodic/MENTIONS/episodes writers, non-Entity status CRUD, and a single batch orchestrator that validates → preflight → embed → one domain tx → optional failed-status tx.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Request validation / allowlists | API / Backend (MCP models) | — | Trust boundary at Pydantic models + service gates |
| Deterministic UUID/hash | API / Backend (catalog_identity) | — | Server-only identity authority |
| Embeddings | API / Backend (embedder client) | — | Must complete before domain tx |
| Provenance graph write | Database / Storage (Neo4j via catalog_store) | — | Episodic/MENTIONS/episodes are Neo4j state |
| Batch status persistence | Database / Storage | — | Restart-safe only if Neo4j-authoritative |
| Atomic multi-object commit | Database / Storage (single tx) | API orchestration | Driver transaction owns commit/rollback |
| Conflict/preflight reads | Database / Storage | API service | Group-scoped MATCH before write |
| MCP tool surface | API / Backend (FastMCP) | — | Additive tools only |
| Operator docs | CDN / Static (repo docs) | — | README/samples/report; no deploy |
| Search / communities interop | Existing Graphiti stack | — | Verify only; upsert never builds communities |

## Project Constraints (from CLAUDE.md)

- Additive only: preserve every existing MCP tool/behavior.
- Neo4j first (5.26+ semantics); no multi-backend claim.
- Server-derived UUIDv5 only; fixed `GRAPHITI_CATALOG_UUID_NAMESPACE`.
- Never interpolate client labels/property names into Cypher.
- Writes return only after commit/rollback; atomic batches full rollback on failure.
- Embed before Neo4j write transaction.
- All reads/writes constrained by `group_id`; tests only `oracle-catalog-tool-test`.
- Validate complete requests, limits, hashes, prefixes, nested refs, confidence, NaN/Inf, protected props.
- Log batch IDs and counts only — never credentials/payloads/raw docs/source text.
- Preserve original `created_at`, endpoint UUIDs, labels, exact `name_raw`/`name_canonical`; add `updated_at`.
- Defaults: 500 entities / 2,000 edges / 5,000 provenance links per batch.
- No deployment, live-group writes, full ingest, clear/delete, or existing-data deletion.
- Python ≥3.10, Ruff line length 100, single quotes, Pyright basic for mcp_server.
- Catalog-scoped quality gates preferred (GATE-04 pattern).

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| graphiti-core | 0.29.2 | Episodic/MENTIONS/RELATES_TO schema contract | Installed project core; PROV-03 requires compatibility |
| neo4j (Python driver) | ≥5.26 (env: 5.28.1) | Async transactions, parameterized Cypher | Phase 1 store already uses `driver.transaction()` |
| pydantic | ≥2.11 (env: 2.11.7) | Request/response models | Phase 1 catalog models pattern |
| mcp (FastMCP) | ≥1.27.2,<2 | Tool registration | Existing MCP server surface |
| pytest / pytest-asyncio | ≥8.3 / ≥0.24 | Unit + live tests | Existing `mcp_server/tests` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | ≥2.0 | CatalogConfig limits already present | Config only; no new settings required beyond existing max_provenance_links |
| ruff / pyright | project pins | Format/lint/typecheck | Catalog-scoped GATE parity |
| uv | 0.11.29 (local) | Env/runner | `uv run pytest` from `mcp_server/` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `RELATES_TO.episodes` list for fact provenance | Intermediate node linking rel→rel | Invents non-Graphiti schema; forbidden by locked decision |
| In-memory batch status | Neo4j `CatalogIngestBatch` | Not restart-safe (STAT-01/05) |
| Call `upsert_typed_entities` tool from batch | Shared internal helpers in one tx | Separate tools open separate txs; breaks BATC-07 |
| Stock `EpisodicNode.save` / SET-map query | Catalog preserve-on-update MERGE | Stock query overwrites entire node map |

**Installation:** No new packages. Phase 2 uses already-declared mcp_server dependencies.

**Version verification:**
- graphiti-core `0.29.2` from root `pyproject.toml` / mcp_server dep `graphiti-core[falkordb]>=0.29.2` [VERIFIED: codebase]
- neo4j driver `5.28.1` in mcp_server uv env; package pin ≥5.26 [VERIFIED: local uv run]
- pydantic `2.11.7` [VERIFIED: local uv run]
- Live Neo4j container `graphiti-catalog-neo4j-test` Up [VERIFIED: docker ps]

## Package Legitimacy Audit

Phase installs **no new external packages**. Existing stack only.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pydantic | PyPI | mature | n/a (seam unknown-downloads) | github.com/pydantic/pydantic | SUS* | Approved — already installed; false-positive downloads signal |
| neo4j | PyPI | mature | n/a | neo4j.com | SUS* | Approved — already installed |
| pytest | PyPI | mature | n/a | github.com/pytest-dev/pytest | SUS* | Approved — already installed |
| pytest-asyncio | PyPI | mature | n/a | github.com/pytest-dev/pytest-asyncio | SUS* | Approved — already installed |

\*Legitimacy seam returned `unknown-downloads` / `too-new` without download telemetry. Packages are pre-existing project dependencies with official source repos — **not** candidates for removal. No install step.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none requiring planner checkpoint (no new installs)

## Architecture Patterns

### System Architecture Diagram

```text
MCP Client
  │
  ├─ upsert_provenance ──────────────────────────────┐
  ├─ get_catalog_ingest_status ──► CatalogService ───┤
  └─ upsert_catalog_batch ───────────────────────────┤
                                                     ▼
                                          ┌─────────────────────┐
                                          │ CatalogService      │
                                          │ 1 validate nested   │
                                          │ 2 identity+hash     │
                                          │ 3 coalesce/conflict │
                                          │ 4 endpoint union    │
                                          │ 5 embed (all)       │
                                          │ 6 domain tx OR dry  │
                                          │ 7 failed status tx  │
                                          └──────────┬──────────┘
                                                     │
                    ┌────────────────────────────────┼────────────────────────────┐
                    ▼                                ▼                            ▼
           CatalogIdentity                 CatalogNeo4jStore              EmbedderClient
           uuid5/sha256                    parameterized Cypher           create/create_batch
                                                    │
                                                    ▼
                                              Neo4j 5.26+
                                    (:Entity:Type)  -[:RELATES_TO {episodes}]->
                                    (:Episodic)     -[:MENTIONS]-> (:Entity)
                                    (:CatalogIngestBatch)   # no Entity label
```

### Recommended Project Structure

```text
mcp_server/src/
├── models/
│   ├── catalog_common.py          # extend error codes if needed (batch_conflict already present)
│   ├── catalog_entities.py        # Phase 1 entities/verify
│   ├── catalog_edges.py           # Phase 1 edges
│   ├── catalog_provenance.py      # NEW: source items, upsert_provenance request
│   ├── catalog_batch.py           # NEW: upsert_catalog_batch + status request/response
│   └── catalog_responses.py       # extend write/status responses
├── services/
│   ├── catalog_identity.py        # +catalog_source_uuid, +catalog_batch_uuid, +mentions uuid helper
│   ├── catalog_store.py           # +episode/mentions/episodes/status primitives
│   └── catalog_service.py         # +upsert_provenance, +get_status, +upsert_catalog_batch
├── graphiti_mcp_server.py         # register 3 tools → 7 catalog / 21 total tools
└── ...
mcp_server/tests/
├── test_catalog_models.py         # extend nested batch/provenance validation
├── test_catalog_identity.py       # source/batch uuid vectors
├── test_catalog_store_unit.py     # Cypher builders + status isolation
├── test_catalog_service.py        # orchestration unit (AsyncMock store/embedder)
└── test_catalog_neo4j_int.py      # live BATC-11 suite under oracle-catalog-tool-test
mcp_server/README.md               # DOCS-01..04
.planning/phases/02-.../02-PHASE2-REPORT.md  # DOCS-05
```

### Pattern 1: Preserve-on-update MERGE (catalog style)

**What:** MERGE on composite identity; set identity props only `ON CREATE`; mutate content only when hash differs; status from create-token or hash compare.
**When to use:** All catalog writes including Episodic sources and CatalogIngestBatch.
**Example:** Phase 1 entity upsert in `catalog_store.build_entity_upsert_cypher` [VERIFIED: codebase]

```cypher
MERGE (n:Entity {uuid: $uuid, group_id: $group_id})
ON CREATE SET n:TypeLabel, n.created_at = $created_at, ...
WITH n, n.content_sha256 = $content_sha256 AS same, ...
FOREACH (_ IN CASE WHEN status = 'updated' THEN [1] ELSE [] END | SET ...)
```

### Pattern 2: Embed before transaction

**What:** Await all embeddings; only then open `async with driver.transaction()`.
**When to use:** Entity, edge, and batch domain writes. Provenance sources do **not** require embeddings (Episodic has no name_embedding in stock schema).
**Source:** Phase 1 `CatalogService.upsert_typed_entities` / `upsert_typed_edges` [VERIFIED: codebase]

### Pattern 3: Atomic fail-closed preflight

**What:** Collect all validation/conflict/target errors before any write; if any and atomic → return rolled_back/error with zero graph mutation.
**When to use:** Provenance and batch (batch always atomic).

### Pattern 4: Separate failed-status transaction

**What:** Domain tx raises → automatic rollback → new short tx writes `CatalogIngestBatch` status=`failed` with bounded error summary. Best-effort: failure to persist status must not mask original error.
**When to use:** BATC-08 only after domain write failure (not dry-run, not preflight validation failures that never opened domain tx — discretion: still may write failed for mid-flight embedding? Locked decision: embedding failure produces **no** graph or status write).

### Pattern 5: Same-request endpoint union

**What:** Build `dict[(entity_type, graph_key)] → prepared entity uuid` from request entities; for each edge endpoint, prefer same-request map then store typed resolve.
**When to use:** `upsert_catalog_batch` only (standalone edge tool still requires pre-existing endpoints).

### Anti-Patterns to Avoid

- **Calling stock `add_episode` / queue / LLM:** Violates PROV-03 and core value.
- **Using `get_episode_node_save_query` SET-map:** Overwrites node; loses preserve-on-update and can clobber catalog extras.
- **Edge upsert after provenance that resets `episodes: []`:** Phase 1 `prepare_edge_params` always sets `episodes=[]`. Batch path must pass through existing episodes or use append-only Cypher for provenance after edge write; entity/edge content updates must not wipe provenance.
- **Labeling status nodes `Entity`:** Would pollute search/communities (STAT-06).
- **Routing batch through public tool functions:** Separate transactions break atomicity.
- **Storing full source text in Episodic.content:** Logging/storage policy forbids complete source text; store bounded allowlisted metadata / short description only.
- **Interpolating client source labels into Cypher:** Fixed `Episodic` / `MENTIONS` / `CatalogIngestBatch` only.
- **Non-atomic batch mode:** Reject `atomic=false` with `validation_error`.
- **Writing intermediate status during dry-run:** Dry-run is side-effect free.
- **Mutating `oracle-catalog-v2` or calling `clear_graph`:** Hard out of scope.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| UUID identity | Custom hash IDs | `uuid.uuid5` + fixed namespace helpers | Cross-language stability; Phase 1 pattern |
| Canonical content hash | ad-hoc string concat | `canonical_sha256` (sort_keys JSON) | Already rejects NaN/Inf |
| Nested validation | Recursive ad-hoc | `validate_nested_json` | Depth/nodes/cycle/string bounds |
| Neo4j transactions | Manual commit flags | `Neo4jDriver.transaction()` | Real commit/rollback [VERIFIED: neo4j_driver.py] |
| Entity/edge MERGE | EntityNode.save / SET map | CatalogNeo4jStore upsert cypher | Preserve-on-update + no wipe |
| Provenance schema | Custom PROVENANCE nodes | Episodic + MENTIONS + episodes list | Graphiti-compatible |
| Status isolation | Search filters | Omit `Entity` label | Community/search match `:Entity` only |
| Structured errors | Exception strings | `CatalogErrorCode` | SAFE-04 already defines codes incl. `provenance_target_missing`, `batch_conflict` |

**Key insight:** Phase 2 is orchestration + three write primitives on an already-correct identity/validation substrate. Smallest secure design extends store/service, not a second catalog stack.

## Runtime State Inventory

> Not a rename/refactor phase. Status nodes are **new** Neo4j state under test group only.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | No Phase 2 status/provenance product writes yet; Phase 1 entities/edges under test groups only | Create new Episodic/MENTIONS/episodes/status in `oracle-catalog-tool-test` only |
| Live service config | CatalogConfig already has `max_provenance_links_per_batch` | No config key rename; document usage |
| OS-registered state | None for catalog Phase 2 | None |
| Secrets/env vars | `GRAPHITI_CATALOG_UUID_NAMESPACE` already required when enabled | Code/docs only; do not rotate namespace |
| Build artifacts | None Phase-2-specific | None |

**Nothing found requiring data migration of renamed keys.** Explicit: no migration of existing live groups.

## Common Pitfalls

### Pitfall 1: Stock episode save overwrites node
**What goes wrong:** `SET n = {uuid, name, ...}` replaces all properties.
**Why it happens:** Copying `get_episode_node_save_query` from graphiti_core.
**How to avoid:** Catalog-owned MERGE with ON CREATE / conditional content SET like entities.
**Warning signs:** Lost `content_sha256` / `source_key` / `updated_at` on retry.

### Pitfall 2: Edge content update wipes `episodes`
**What goes wrong:** Provenance attaches episode UUIDs; later edge upsert sets `episodes=[]`.
**Why it happens:** Phase 1 `prepare_edge_params` hardcodes empty list for search hydration.
**How to avoid:** Provenance uses append-only Cypher (`e.episodes = apoc.coll.toSet(coalesce(e.episodes,[]) + [$ep])` **or** pure Cypher list concat + dedup without APOC). Batch edge write must either (a) write edges first then provenance append, or (b) compute final episodes list before edge SET and never pass bare `[]` when sources exist. Prefer pure Cypher without APOC dependency.
**Warning signs:** `require_provenance` passes then fails after entity/edge retry.

### Pitfall 3: Edge provenance invisible to Phase 1 verify
**What goes wrong:** `match_provenance_presence` OPTIONAL MATCHes `(ep:Episodic)-[:MENTIONS]->(n {uuid})` — works for entity nodes, **not** for RELATES_TO edges (edges are not nodes).
**Why it happens:** Phase 1 stub only implements entity-style presence.
**How to avoid:** Extend presence check: entities via MENTIONS; edges via `MATCH ()-[e:RELATES_TO {uuid, group_id}]->() WHERE $source_uuid IN coalesce(e.episodes,[])` (or any episode present if checking "has provenance").
**Warning signs:** Edge targets always in `missing_provenance` after successful fact provenance attach.

### Pitfall 4: Partial batch status without domain commit
**What goes wrong:** Writing `writing`/`embedding` status before domain tx, then crash → sticky non-terminal state.
**Why it happens:** Over-modeling lifecycle.
**How to avoid:** Locked design: dry-run no status; success writes `committed` inside domain tx; failure best-effort `failed` after rollback. Intermediate statuses optional in-memory only unless product requires them — if persisted, never leave them without crash recovery semantics. **Recommendation:** Only persist terminal `committed`/`failed` for v1; treat planned/validating/embedding/writing as response/log fields or ephemeral. If STAT-03 requires stored enum values, document that non-terminal rows are optional and tests assert terminal outcomes.
**Warning signs:** Status stuck in `writing` after process kill.

### Pitfall 5: Same-request FK edges fail missing_endpoint
**What goes wrong:** Batch includes table+column+FK but edge resolve only hits Neo4j.
**Why it happens:** Reusing standalone edge path unchanged.
**How to avoid:** Union map of prepared request entities before endpoint resolve (BATC-04).
**Warning signs:** ACCEPT_TAB single-batch fails; split upserts pass.

### Pitfall 6: Mentions UUID nondeterminism
**What goes wrong:** Retry creates duplicate MENTIONS rels.
**Why it happens:** Random UUID on EpisodicEdge.
**How to avoid:** UUIDv5 e.g. `group_id|Mentions|source_uuid|entity_uuid` (or `group_id|Mentions|source_key|entity_graph_key|entity_type`). MERGE on that uuid.
**Warning signs:** Duplicate MENTIONS after retry; verify counts grow.

### Pitfall 7: Community build during upsert
**What goes wrong:** Upsert latency + LLM calls + non-determinism.
**Why it happens:** Calling maintenance after write.
**How to avoid:** Never invoke `build_communities` from catalog write path; only explicit test/tool call for BATC-12.
**Warning signs:** Queue/LLM mocks fire during catalog tests.

### Pitfall 8: Windows PYTHONPATH monorepo override
**What goes wrong:** site-packages graphiti_core shadows worktree.
**Why it happens:** Documented Phase 1 issue.
**How to avoid:** Semicolon PYTHONPATH with worktree root first in test commands/docs.
**Warning signs:** Missing local catalog changes at runtime.

## Code Examples

### Source identity (extend catalog_identity)

```python
# Pattern mirrors catalog_entity_uuid / catalog_edge_uuid [VERIFIED: catalog_identity.py]
def catalog_source_uuid(namespace: uuid.UUID, group_id: str, source_key: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|Source|{source_key}'))

def catalog_batch_uuid(namespace: uuid.UUID, group_id: str, batch_id: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|Batch|{batch_id}'))

def catalog_mentions_uuid(
    namespace: uuid.UUID, group_id: str, source_uuid: str, entity_uuid: str
) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|Mentions|{source_uuid}|{entity_uuid}'))
```

### Installed Graphiti provenance shapes

```text
# Episodic node fields used by stock Graphiti [VERIFIED: graphiti_core/nodes.py EpisodicNode]
uuid, name, group_id, source_description, source (EpisodeType value),
content, entity_edges (list[str]), created_at, valid_at

# MENTIONS [VERIFIED: edge_db_queries.EPISODIC_EDGE_SAVE]
(:Episodic)-[:MENTIONS {uuid, group_id, created_at}]->(:Entity)

# Fact provenance [VERIFIED: edges.py EntityEdge.episodes]
()-[e:RELATES_TO {..., episodes: [episode_uuid, ...]}]->()
```

### Catalog Episodic upsert sketch (do NOT use SET n = map)

```cypher
// Server-owned; parameters only. No Entity label.
MERGE (n:Episodic {uuid: $uuid, group_id: $group_id})
ON CREATE SET
  n.name = $name,
  n.source = $source,                // e.g. 'json' or 'text'
  n.source_description = $source_description,
  n.content = $content,              // bounded metadata JSON string, NOT full document
  n.entity_edges = $entity_edges,    // edge UUIDs this source documents
  n.valid_at = $valid_at,            // exact reference_time
  n.source_key = $source_key,
  n.content_sha256 = $content_sha256,
  n.created_at = $created_at,
  n.updated_at = $updated_at
// ON MATCH: if hash differs, SET mutable fields + updated_at; never rewrite created_at/uuid/group_id/source_key
```

### MENTIONS link

```cypher
MATCH (episode:Episodic {uuid: $episode_uuid, group_id: $group_id})
MATCH (node:Entity {uuid: $entity_uuid, group_id: $group_id})
MERGE (episode)-[e:MENTIONS {uuid: $mentions_uuid}]->(node)
ON CREATE SET e.group_id = $group_id, e.created_at = $created_at
// no property clobber on match
```

### Append episode to RELATES_TO.episodes (APOC-free)

```cypher
MATCH ()-[e:RELATES_TO {uuid: $edge_uuid, group_id: $group_id}]->()
WITH e, coalesce(e.episodes, []) AS eps
WITH e, CASE WHEN $episode_uuid IN eps THEN eps ELSE eps + $episode_uuid END AS next
SET e.episodes = next
RETURN e.uuid AS uuid, e.episodes AS episodes
```

### CatalogIngestBatch status node

```cypher
MERGE (b:CatalogIngestBatch {uuid: $uuid, group_id: $group_id})
ON CREATE SET b.batch_id = $batch_id, b.created_at = $created_at, ...
SET b.status = $status,
    b.request_sha256 = $request_sha256,
    b.catalog_sha256 = $catalog_sha256,
    b.entity_count = $entity_count,
    b.edge_count = $edge_count,
    b.provenance_count = $provenance_count,
    b.error_summary = $error_summary,  // bounded sanitized string/json
    b.updated_at = $updated_at,
    b.committed_at = $committed_at
// NEVER set :Entity
```

### Domain transaction boundary

```python
# [VERIFIED: graphiti_core/driver/neo4j_driver.py transaction()]
async with client.driver.transaction() as tx:
    for prep in entities_to_write:
        await store.upsert_entity_item(tx, ...)
    for prep in edges_to_write:
        await store.upsert_edge_item(tx, ...)
    for prov in provenance_to_write:
        await store.upsert_source_and_links(tx, ...)
    await store.upsert_batch_status(tx, status='committed', ...)
# on exception: automatic rollback; then best-effort:
async with client.driver.transaction() as tx:
    await store.upsert_batch_status(tx, status='failed', error_summary=bounded)
```

### Real Neo4j transaction semantics

```python
# Source: graphiti_core/driver/neo4j_driver.py
async def transaction(self) -> AsyncIterator[Transaction]:
    async with self.client.session(database=self._database) as session:
        tx = await session.begin_transaction()
        try:
            yield _Neo4jTransaction(tx)
            await tx.commit()
        except BaseException:
            await tx.rollback()
            raise
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Semantic `add_memory` + queue + LLM extract | Deterministic catalog tools | This milestone | Exact identity for DDL/PDF/Oracle catalogs |
| Phase 1 entity/edge only | + provenance + status + atomic batch | Phase 2 | Complete administrative ingest surface |
| Random episode UUIDs | UUIDv5 source/batch/mentions | Phase 2 | Idempotent provenance |
| In-tool separate txs | Shared domain transaction | Phase 2 batch | True multi-object atomicity |

**Deprecated/outdated for this phase:**
- Using `add_episode` for catalog sources
- Claiming FalkorDB support for catalog writes
- Single-property UNIQUE on uuid (Phase 1 already uses composite uuid+group_id)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | **RESOLVED:** Persist only terminal `committed`/`failed` status rows; six lifecycle literals remain valid response/model states; intermediates are never durable Neo4j rows (restart-safe, no sticky mid-flight status) | Pitfall 4 / STAT-03 / Open Questions | Locked for v1; changing later requires crash-recovery rules |
| A2 | `EpisodeType` value for catalog sources should be `json` (structured metadata) unless sample docs specify `text` | Provenance | Wrong source enum may confuse semantic tools reading episodes |
| A3 | Mentions identity formula `group_id\|Mentions\|source_uuid\|entity_uuid` is acceptable (not externally mandated beyond determinism) | Code examples | Formula change re-keys MENTIONS; pick once and document |
| A4 | Bounded `Episodic.content` stores canonical allowlisted source metadata JSON, not raw PDF/DDL text | PROV-02 | If operators expect full text retrieval from episodes, need separate object store (out of scope) |
| A5 | `entity_edges` on Episodic should list documented edge UUIDs for Graphiti compatibility; empty list acceptable when only entity targets | Provenance | Minor interop difference with stock episodes |

**A1 locked** via Open Questions (RESOLVED). A2–A3 remain plan defaults matching CONTEXT; override formulas only before first write to a durable group (tests only for now).

## Planning note: `depends_on` ID form

Repository convention (Phase 1 evidence: `plan: 02` with `depends_on: [01-01]`): frontmatter `plan` is the local two-digit number; `depends_on` uses full phase-plan IDs (`02-01`, `02-02`, …). Phase 2 plans follow the same form. Do not normalize `depends_on` to bare two-digit locals.

## Open Questions (RESOLVED)

1. **Must non-terminal statuses be durable? — RESOLVED (A1 terminals-only)**
   - **Decision:** Persist only terminal Neo4j rows `committed` and `failed` for v1.
   - **Model/response:** All six STAT-03 lifecycle literals remain valid response/model states: `planned`, `validating`, `embedding`, `writing`, `committed`, `failed`. Intermediate values may appear in in-memory responses/logs only; writers do not MERGE non-terminal status into Neo4j mid-flight.
   - **Restart-safety:** Neo4j is authoritative for terminal outcomes only. After process kill or service reinit, `get_catalog_ingest_status` returns a committed/failed row if one was written, otherwise not-found — never a sticky `writing`/`embedding`/`validating`/`planned` node left by a crashed mid-flight write.
   - **No sticky intermediates:** Dry-run writes no status. Embed failure writes no status. Domain success writes `committed` inside the domain transaction. Domain failure rolls back domain objects, then best-effort persists `failed` in a separate transaction. Matches CONTEXT locked batch-status decisions and plans 02-01/02-03/02-04 A1 notes.

2. **Edge provenance verify semantics — RESOLVED**
   - **Decision:** Two layers.
     - Generic `require_provenance` edge presence: non-empty `episodes` — `size(coalesce(e.episodes, [])) > 0`.
     - Source-specific verification: UUID membership — source episode uuid `IN coalesce(e.episodes, [])`.
   - Entity presence remains MENTIONS-based. Extend Phase 1 `match_provenance_presence` accordingly (plan 02-02).

3. **ACCEPT_TAB fixture location — RESOLVED**
   - **Canonical path:** `mcp_server/tests/fixtures/accept_tab_sanitized.json`.
   - **Contents:** Created only from synthetic sanitized data (minimal multi-entity/edge/provenance batch for `oracle-catalog-tool-test`). Never copy blindly from untracked worktree inputs, live catalogs, `catalog/`, or `sample_catalog.json`.
   - **Docs:** README may reference the same sanitized shape; no secrets. Plan 02-05 owns fixture creation when inline builders are insufficient.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python / uv | tests, quality | ✓ | CPython 3.12 host; uv 0.11.29; mcp_server venv 3.10.20 | — |
| neo4j driver | store | ✓ | 5.28.1 (uv env) | — |
| Neo4j server | live int tests | ✓ | container `graphiti-catalog-neo4j-test` Up | Skip unless `CATALOG_INT_REQUIRED=1` (then fail) |
| Docker | image build check DOCS-05 | ✓ | 29.4.3 | Document build command even if not pushed |
| pydantic | models | ✓ | 2.11.7 | — |
| graphiti-core | schema compat | ✓ | 0.29.2 declared | PYTHONPATH monorepo override on Windows |
| LLM / OpenAI | **not required** for catalog writes | n/a | n/a | Catalog path must not call LLM |
| FalkorDB | out of scope | n/a | n/a | Return backend_unavailable if misconfigured |

**Missing dependencies with no fallback:** none for planning/execution of Phase 2 code+tests on this machine (Neo4j live present).

**Missing dependencies with fallback:** none critical.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode auto) |
| Config file | `mcp_server/tests/pytest.ini` (+ package pyproject) |
| Quick run command | `cd mcp_server && uv run pytest tests/test_catalog_{models,identity,store_unit,service}.py -q` |
| Full suite command | `cd mcp_server && uv run pytest tests/test_catalog_*.py -q --timeout=120` |
| Live required | `cd mcp_server && CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_neo4j_int.py -q --timeout=120` |
| Quality | catalog-scoped ruff format/check + pyright on catalog paths; MCP tool listing assert |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IDEN-03 | source uuid5 stable | unit | `pytest tests/test_catalog_identity.py -k source -q` | ❌ Wave 0 extend |
| IDEN-04 | batch uuid5 stable | unit | `pytest tests/test_catalog_identity.py -k batch -q` | ❌ Wave 0 extend |
| PROV-01..02 | model validation + hash | unit | `pytest tests/test_catalog_models.py -k provenance -q` | ❌ Wave 0 |
| PROV-03..04 | Episodic/MENTIONS/episodes write | integration | `pytest tests/test_catalog_neo4j_int.py -k provenance -q` | ❌ Wave 0 |
| PROV-05 | missing target no partial | unit+int | service mock + live | ❌ Wave 0 |
| PROV-06 | identical rerun unchanged | integration | live retry | ❌ Wave 0 |
| STAT-01..04 | status node shape/safety | unit+int | store unit + live | ❌ Wave 0 |
| STAT-05 | status after reinit | integration | new service instance same driver | ❌ Wave 0 |
| STAT-06 | not in search/communities | integration | search_nodes + optional community | ❌ Wave 0 |
| BATC-01..10 | batch orchestration | unit+int | service + live | ❌ Wave 0 |
| BATC-11 | ACCEPT_TAB suite | integration | dedicated live tests | ❌ Wave 0 |
| BATC-12 | build_communities safe | integration | explicit call after batch | ❌ Wave 0 |
| DOCS-01..05 | docs/report presence | smoke/manual | file asserts + tool list | ❌ Wave 0 |
| GATE parity | no LLM/queue | integration | existing mock spies pattern | ✅ pattern exists |
| Isolation | only test group | integration | teardown + forbidden group asserts | ✅ pattern exists |

### Sampling Rate

- **Per task commit:** catalog unit quick run
- **Per wave merge:** unit + live if Neo4j available; with `CATALOG_INT_REQUIRED=1` for gate waves
- **Phase gate:** full catalog unit+live, ruff, pyright, MCP regression subset, 21-tool listing (14 existing + 7 catalog)

### Wave 0 Gaps

- [ ] `tests/test_catalog_identity.py` — source/batch/mentions UUID vectors (IDEN-03/04)
- [ ] `tests/test_catalog_models.py` — provenance + nested batch models, limits, atomic=true enforcement
- [ ] `tests/test_catalog_store_unit.py` — episode/mentions/episodes-append/status Cypher builders; no Entity on status
- [ ] `tests/test_catalog_service.py` — provenance/status/batch orchestration with AsyncMock; embed-before-tx; failed-status secondary tx
- [ ] `tests/test_catalog_neo4j_int.py` — BATC-11 ACCEPT_TAB, retry, batch_conflict, missing endpoint rollback, reinit status, search interop, build_communities, no LLM/queue
- [ ] `tests/fixtures/accept_tab_sanitized.json` (or inline builders) — sanitized multi-entity/edge/provenance batch
- [ ] Docs: README catalog section + Phase 2 report template path

*(Existing Phase 1 infrastructure is the base; Wave 0 is extension, not framework install.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | MCP transport auth out of phase scope |
| V3 Session Management | no | — |
| V4 Access Control | yes | `group_id` isolation on every read/write; test group only |
| V5 Input Validation | yes | Pydantic allowlists, `validate_nested_json`, limits, SHA-256 format, protected props |
| V6 Cryptography | partial | UUIDv5 + SHA-256 via stdlib; no hand-rolled crypto |
| V5 Injection | yes | Parameterized Cypher; server-owned labels only |

### Known Threat Patterns for catalog Neo4j upserts

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher injection via labels | Tampering | Fixed allowlists; never interpolate client identifiers |
| Cross-group read/write | Elevation | Every MATCH/MERGE includes `group_id` |
| Payload/credential logging | Info disclosure | Log batch_id + counts only |
| Full document storage | Info disclosure | Bounded source content; STAT-04 property allowlist |
| Partial commit on failure | Tampering | Single domain tx + rollback |
| Client UUID authority | Spoofing | Server UUIDv5 only; ignore caller DB UUIDs |
| Namespace rotation | Tampering | Immutable deployment config; docs warning |
| Status node search pollution | Elevation/DoS of search quality | No `Entity` label on `CatalogIngestBatch` |

## Sources

### Primary (HIGH confidence)

- `mcp_server/src/services/catalog_{identity,store,service}.py` — Phase 1 patterns [VERIFIED: codebase]
- `mcp_server/src/models/catalog_*.py`, `config/schema.py` CatalogConfig — limits/errors [VERIFIED: codebase]
- `graphiti_core/nodes.py` EpisodicNode, EpisodeType [VERIFIED: codebase]
- `graphiti_core/edges.py` EntityEdge.episodes, EpisodicEdge/MENTIONS [VERIFIED: codebase]
- `graphiti_core/models/nodes/node_db_queries.py` episode save (anti-pattern reference) [VERIFIED: codebase]
- `graphiti_core/models/edges/edge_db_queries.py` EPISODIC_EDGE_SAVE [VERIFIED: codebase]
- `graphiti_core/driver/neo4j_driver.py` transaction commit/rollback [VERIFIED: codebase]
- `graphiti_core/utils/maintenance/community_operations.py` MATCH (n:Entity) [VERIFIED: codebase]
- `.planning/phases/02-.../02-CONTEXT.md`, REQUIREMENTS.md, 01-VERIFICATION.md [VERIFIED: planning artifacts]
- Local env: neo4j 5.28.1, pydantic 2.11.7, graphiti-core 0.29.2, Neo4j container up [VERIFIED: local tools]

### Secondary (MEDIUM confidence)

- None required beyond codebase for this phase (external web research not needed for locked design).

### Tertiary (LOW confidence)

- Legitimacy seam download telemetry (ignored for preinstalled deps).
- classify-confidence seam returned LOW for provider `codebase` even with `--verified`; research confidence still **HIGH** based on direct source reads.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; versions verified locally
- Architecture: HIGH — locked CONTEXT + Phase 1 code + Graphiti schema read end-to-end
- Pitfalls: HIGH — edge episodes wipe, stock SET-map, verify edge gap observed in code

**Research date:** 2026-07-17
**Valid until:** 2026-08-16 (stable internal APIs; re-check if graphiti-core version changes)
