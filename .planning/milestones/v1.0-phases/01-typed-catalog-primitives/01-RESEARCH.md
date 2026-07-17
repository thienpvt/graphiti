# Phase 1: Typed Catalog Primitives - Research

**Researched:** 2026-07-16
**Domain:** Deterministic Neo4j catalog-upsert MCP tools (Graphiti MCP extension)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Mandatory Write Rules
- Entity upsert returns success only after Neo4j commits; no successful response may precede commit.
- Catalog tools never use the ingestion queue and never call an LLM.
- Catalog requests do not accept `excluded_entity_types`.
- Entity and edge identities are server-derived UUIDv5 values under the configured immutable namespace; caller UUIDs have no identity authority.
- Every catalog entity requires exactly one allowlisted custom type label in addition to the `Entity` base label.
- Edge upsert never creates generic or implicit endpoints; both typed endpoints must already resolve in the request scope.
- Existing node types are immutable. A deterministic identity or graph key with conflicting labels fails without mutation.
- Entity upsert generates `name_embedding` before opening the write transaction, including dry-run readiness validation.
- An identical canonical entity payload returns `unchanged` and performs no timestamp or property mutation.
- Edge upsert requires two existing endpoints and resolves each by exact `group_id`, `graph_key`, and expected `entity_type`.
- A missing endpoint returns `missing_endpoint`; an endpoint with the wrong custom label returns `endpoint_type_mismatch`.
- Edge upsert never creates or relabels endpoints.
- Edge UUIDs are server-derived UUIDv5 identities, and `fact_embedding` is generated before opening the write transaction.
- An identical canonical edge payload returns `unchanged` and performs no timestamp or property mutation.

#### Result Contract
- Item success states are `created`, `updated`, and `unchanged`.
- Results preserve input order and include deterministic UUID and canonical SHA-256.
- Expected validation and conflict failures use structured item errors without exposing raw exception text.
- Atomic request failure marks otherwise valid items as `rolled_back` and reports the triggering structured error.

#### Write Semantics
- `atomic=true` uses one request transaction. `atomic=false` uses independent item transactions; every successful item returns only after its own transaction commits.
- Dry-run performs full validation, identity/conflict resolution, and embedding generation without graph writes or persistent batch state.
- Same-request items with identical deterministic identity and canonical payload are coalesced; differing payloads fail as conflicts.
- A request uses one timestamp. Existing `created_at` is preserved; `updated_at` advances only for changed payloads.

#### Verification Scope
- Domain objects persist `batch_id`; batch verification queries only the requested `group_id` and batch.
- Duplicate/anomaly reporting is limited to requested identities rather than scanning unrelated group data.
- A generic duplicate is an `Entity` in the same group whose `name` equals `graph_key` but lacks the expected custom label.
- Phase 1 accepts `require_provenance`; it reports missing provenance read-only while Phase 2 supplies provenance writes.

#### Feature Gates and Failures
- Catalog tool schemas remain registered while writes are disabled; write calls return `feature_disabled`.
- An absent or invalid UUID namespace is tolerated only while catalog writes are disabled. Enabling writes requires a valid explicit namespace.
- Non-Neo4j configurations keep stable tool schemas but return structured backend-unavailable errors for catalog operations.
- Unexpected failures log only safe batch/count context and return `internal_error`; Neo4j transaction failures return `neo4j_transaction_failed`.

### Claude's Discretion
- Exact Pydantic model decomposition, module boundaries, internal helper names, and Cypher layout may follow the smallest secure design consistent with existing MCP conventions.

### Deferred Ideas (OUT OF SCOPE)
- Provenance writes, persisted `CatalogIngestBatch` status, and complete atomic catalog-batch orchestration remain Phase 2 work. Phase 2 cannot begin until the complete Phase 1 quality gate and report pass.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONF-01 | `catalog_upsert.enabled` default disabled | Extend `GraphitiConfig` with nested `CatalogConfig` in `mcp_server/src/config/schema.py` [VERIFIED: codebase] |
| CONF-02 | Validate `GRAPHITI_CATALOG_UUID_NAMESPACE` as UUID | Pydantic UUID field + env; refuse enable without valid ns [VERIFIED: pydantic-settings pattern] |
| CONF-03 | Never auto-generate namespace | No default UUID factory; document immutable [ASSUMED: deployment contract] |
| CONF-04 | Limits default 500 / 2000 / 5000 | Config fields with Field defaults [VERIFIED: REQUIREMENTS] |
| CONF-05 | Neo4j-only writes | Gate on `driver.provider == GraphProvider.NEO4J` [VERIFIED: neo4j_driver.py] |
| SAFE-01 | Required validated `group_id` | Reuse `validate_group_id` [VERIFIED: helpers.py] |
| SAFE-02 | Fixed allowlists only; no client Cypher ids | Server enum → literal labels; never interpolate request strings [VERIFIED: helpers + node_db_queries] |
| SAFE-03 | String/collection/protected/finite/confidence validation | Pydantic field validators + model validators [VERIFIED: Pydantic 2.x] |
| SAFE-04 | Item-level structured error codes | Catalog response models with `error_code` enum [CITED: PROJECT.md error list] |
| SAFE-05 | Log batch IDs/counts only | Logger contract in CatalogService [ASSUMED: logging policy] |
| IDEN-01 | Entity UUIDv5 `group_id\|entity_type\|graph_key` | `uuid.uuid5(ns, f'{group_id}\|{entity_type}\|{graph_key}')` [VERIFIED: stdlib uuid] |
| IDEN-02 | Edge UUIDv5 `group_id\|edge_type\|edge_key` | Same pattern for edges [VERIFIED: stdlib uuid] |
| IDEN-05 | Caller UUID never identity authority | Ignore/compare-only; conflict → `deterministic_uuid_conflict` [VERIFIED: CONTEXT] |
| IDEN-06 | Canonical SHA-256 64 lowercase hex | `hashlib.sha256` over sorted JSON [VERIFIED: stdlib] |
| IDEN-07 | Optional client hash compare | `content_hash_mismatch` on differ [VERIFIED: REQUIREMENTS] |
| IDEN-08 | Identical → unchanged; change → update; identity conflict fail | Hash compare + type/key checks in store [VERIFIED: CONTEXT] |
| ENTY-01..13 | Typed entity upsert tool contract | Dedicated CatalogService + CatalogNeo4jStore; not EntityNode.save [VERIFIED: nodes.py SET n = $entity_data] |
| RESO-01..04 | Read-only resolve tool | MATCH-only queries; no embedder/write [VERIFIED: CONTEXT] |
| EDGE-01..12 | Typed edge upsert + no implicit endpoints | MATCH endpoints by group/key/type; RELATES_TO + name=edge_type [VERIFIED: edge_db_queries + CONTEXT] |
| VERI-01..05 | Read-only batch verify | Query by group_id + batch_id / keys; require_provenance report-only [VERIFIED: CONTEXT] |
| GATE-01..05 | Phase 1 quality gate | pytest unit + Neo4j int on `oracle-catalog-tool-test` only; ruff/pyright; MCP schema list; short report [VERIFIED: ROADMAP] |
</phase_requirements>

## Summary

Phase 1 adds four additive MCP tools (`upsert_typed_entities`, `upsert_typed_edges`, `resolve_typed_entities`, `verify_catalog_batch`) that write deterministic, typed catalog objects into Neo4j without LLM extraction, without `QueueService`, and without caller UUID authority. Identity is server-only UUIDv5 under an immutable configured namespace; mutable payloads are audited with exactly 64 lowercase SHA-256 hex characters. Writes must embed first, then open a real Neo4j transaction via `Neo4jDriver.transaction()`, and return only after commit or rollback.

Critical implementation choice: **do not** reuse stock `EntityNode.save` / `EntityEdge.save` as the catalog write path. Stock Neo4j save uses `MERGE … SET n = $entity_data` (full property map replace), flattens attributes, rewrites `created_at` on every save, and lacks preserve-on-update / `updated_at` / `content_sha256` semantics required by ENTY-09 and IDEN-08. Implement a dedicated `CatalogNeo4jStore` with fixed allowlisted Cypher, `ON CREATE` / `ON MATCH` property control, and exact label discipline (`Entity` + exactly one custom type).

**Primary recommendation:** Implement entirely inside `mcp_server/` as thin `@mcp.tool` adapters → `CatalogService` (validate, identity, hash, embed-before-tx, feature gate) → `CatalogNeo4jStore` (parameterized Cypher + `driver.transaction()`). Reuse live `GraphitiService.client.driver` and `client.embedder`. Add no new runtime packages. Test only `group_id=oracle-catalog-tool-test`. Preserve dirty unrelated files (`mcp_server/k8s/graphiti-neo4j.yaml`, `.codegraph/`, `mcp_server/sample_catalog.json`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| MCP tool registration / schema surface | MCP Transport (`graphiti_mcp_server.py`) | — | FastMCP `@mcp.tool()` public contract; schemas registered even when disabled |
| Request validation / allowlists | MCP models (`models/catalog_*.py`) | CatalogService | Trust boundary; Pydantic rejects before I/O |
| Config (enabled, namespace, limits) | MCP config (`config/schema.py`) | Env/YAML | Existing pydantic-settings precedence |
| Deterministic identity (UUIDv5) | CatalogService / identity helper | — | Server-only authority |
| Canonical SHA-256 audit | CatalogService / identity helper | — | Pure function |
| Embeddings | EmbedderClient (pre-tx) | CatalogService ordering | Failure must not open write tx |
| Typed Neo4j entity/edge persistence | CatalogNeo4jStore | Neo4jDriver.transaction | Dedicated Cypher; real commit/rollback |
| Endpoint resolution for edges | CatalogNeo4jStore (MATCH) | CatalogService | Exact group_id + graph_key + type; no create |
| Read-only resolve / verify | CatalogNeo4jStore (read) | CatalogService | Zero writes, zero embeds |
| Search interoperability | Existing search tools | Entity + embeddings shape | Unchanged `search_nodes` / `search_memory_facts` |
| Feature / backend gate | CatalogService | Config + driver.provider | `feature_disabled` / backend error |
| Logging (batch id, counts) | CatalogService | stdlib logging | Never full payloads |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | `>=3.10` (env 3.12.10) | Runtime | Monorepo async [VERIFIED: env] |
| `mcp` (FastMCP) | `>=1.27.2,<2` | Tool surface | Existing `FastMCP` + `@mcp.tool()` [VERIFIED: graphiti_mcp_server.py:187] |
| `graphiti-core` | `>=0.29.2` | Driver, embedder ABC, Entity/RELATES_TO, search | MCP PyPI wheel; prefer public APIs [VERIFIED: mcp_server/uv.lock] |
| `neo4j` | `>=5.26.0` | Async Bolt driver | `Neo4jDriver.transaction()` real commit/rollback [VERIFIED: neo4j_driver.py:151-161] |
| Neo4j server | 5.26+ | Graph DB | Project constraint; vector property procs [VERIFIED: CLAUDE.md] |
| Pydantic | `>=2.11.5` | Request/response models | Validation + allowlists [VERIFIED: stack] |
| `pydantic-settings` | installed | Config YAML+env | Extend `GraphitiConfig` [VERIFIED: schema.py] |
| stdlib `uuid` | — | UUIDv5 identity | `uuid.uuid5` [VERIFIED: stdlib] |
| stdlib `hashlib` | — | SHA-256 audit | 64 lowercase hex [VERIFIED: stdlib] |
| stdlib `json` | — | Canonical serialization | `sort_keys=True, separators=(',', ':')` [VERIFIED: stdlib] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `pytest-asyncio` | MCP `>=9.0.3` / asyncio auto | Unit + integration | `mcp_server/tests/` [VERIFIED: pytest.ini] |
| `pytest-timeout` | MCP tests | Hang protection | Integration against Neo4j |
| Ruff | project | Format + lint | line-length 100, single quotes [VERIFIED: CONVENTIONS] |
| Pyright | project | Typecheck | `basic` for mcp_server |
| Configured `EmbedderClient` | via factories | Embeddings only | `create` / `create_batch` before tx [VERIFIED: embedder/client.py] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Dedicated CatalogNeo4jStore Cypher | Stock `EntityNode.save` | Stock `SET n = $entity_data` clobbers `created_at`, drops absent props [VERIFIED: node_db_queries.py:183-186] |
| Catalog tools in `graphiti_core` | MCP-only package | Core stays general-purpose; allowlists are product concerns [ASSUMED] |
| `add_triplet` for edges | Dedicated edge upsert | Triplet creates generic endpoints with uuid4 [VERIFIED: graphiti_mcp_server.py:1076-1097] |
| QueueService for writes | Sync await commit | Queue returns on enqueue; violates post-commit contract [VERIFIED: add_memory] |
| MD5 / non-canonical hash | SHA-256 canonical JSON | Forbidden; false mismatches [VERIFIED: PROJECT.md] |
| New runtime packages | stdlib + installed stack | YAGNI [VERIFIED: research STACK] |

**Installation:**

```bash
# No new packages. From mcp_server/:
uv sync
```

**Version verification:** Stack packages already in `mcp_server/uv.lock`. Do not add Phase 1 runtime deps. [VERIFIED: uv.lock]

## Package Legitimacy Audit

> Phase 1 installs **no** new external packages.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none new)* | — | — | — | — | — | N/A |

**Packages removed due to [SLOP] verdict:** none  
**Packages flagged as suspicious [SUS]:** none  
**New packages recommended:** none

## Architecture Patterns

### System Architecture Diagram

```
MCP Client
    │
    │  tools: upsert_typed_entities | upsert_typed_edges
    │         resolve_typed_entities | verify_catalog_batch
    ▼
┌───────────────────────────────────────────────────────────┐
│ FastMCP  mcp_server/src/graphiti_mcp_server.py            │
│  thin @mcp.tool adapters (Pydantic request in)            │
│  EXISTING tools UNCHANGED (add_memory, search_*, ...)     │
└───────────────────────────┬───────────────────────────────┘
                            │ await (no QueueService)
                            ▼
┌───────────────────────────────────────────────────────────┐
│ CatalogService  services/catalog_service.py               │
│  1. feature_disabled / invalid_uuid_namespace / backend   │
│  2. full request validation                               │
│  3. UUIDv5 identity + canonical SHA-256                   │
│  4. coalesce same-identity same-hash items                │
│  5. conflict detection (type, identity, endpoints)        │
│  6. embedder.create(_batch)  ──► embedding_failed stop    │
│  7. open Neo4j write tx only after embeds ready           │
│  8. map results: created|updated|unchanged|errors         │
└───────────────┬───────────────────────────┬───────────────┘
                │ reads / writes            │ embeddings
                ▼                           ▼
┌────────────────────────────┐   ┌──────────────────────────┐
│ CatalogNeo4jStore          │   │ EmbedderClient           │
│ services/catalog_store.py  │   │ graphiti_core/embedder   │
│ fixed Cypher allowlists    │   └──────────────────────────┘
│ MERGE uuid + ON CREATE/MATCH│
│ MATCH endpoints typed only │
│ RELATES_TO + searchable    │
└───────────────┬────────────┘
                │ async with driver.transaction()
                ▼
┌───────────────────────────────────────────────────────────┐
│ Neo4jDriver  graphiti_core/driver/neo4j_driver.py         │
│ session.begin_transaction → commit | rollback             │
│ provider must be GraphProvider.NEO4J for writes           │
└───────────────────────────────────────────────────────────┘
                │
                ▼
         Neo4j 5.26+  (group_id partition)
         Labels: Entity + <AllowlistedType>
         Edges:  RELATES_TO (name = edge_type, fact, embeddings)
```

### Recommended Project Structure

```
mcp_server/
├── src/
│   ├── graphiti_mcp_server.py       # register 4 tools; do not alter existing tools
│   ├── config/
│   │   └── schema.py                # + CatalogConfig (enabled, uuid_namespace, limits)
│   ├── models/
│   │   ├── catalog_entities.py      # allowlisted entity items + request
│   │   ├── catalog_edges.py         # allowlisted edge items + request
│   │   ├── catalog_common.py        # shared limits, error codes, result items
│   │   └── catalog_responses.py     # structured write/resolve/verify responses
│   ├── services/
│   │   ├── catalog_identity.py      # uuid5 + canonical_sha256
│   │   ├── catalog_service.py       # orchestration + gates + embed-before-tx
│   │   └── catalog_store.py         # Neo4j Cypher + transactions
│   └── ...                          # existing factories, queue (untouched)
└── tests/
    ├── test_catalog_models.py
    ├── test_catalog_identity.py
    ├── test_catalog_service.py      # mock driver/embedder; ordering asserts
    ├── test_catalog_store_unit.py   # Cypher builder / allowlist (no DB)
    └── test_catalog_neo4j_int.py    # group_id=oracle-catalog-tool-test only
```

### Pattern 1: Thin tool → service → store

**What:** `@mcp.tool` accepts Pydantic models, calls `CatalogService`, returns structured dicts. No Cypher in tool body.  
**When to use:** All four Phase 1 tools.

```python
# Source: pattern from graphiti_mcp_server.py tool registration
@mcp.tool()
async def upsert_typed_entities(
    request: UpsertTypedEntitiesRequest,
) -> CatalogWriteResponse | ErrorResponse:
    if graphiti_service is None:
        return ErrorResponse(error='Graphiti service not initialized')
    return await catalog_service.upsert_typed_entities(
        client=await graphiti_service.get_client(),
        request=request,
    )
```

### Pattern 2: Embed before open transaction

**What:** All `name_embedding` / `fact_embedding` generation completes before `async with driver.transaction()`.  
**When to use:** Every write path including dry-run readiness (dry-run embeds but skips write).  
**Ordering (hard):** validate → identity+hash → endpoint reads → **embed** → **write tx** → commit.  
**Source:** `Neo4jDriver.transaction` [VERIFIED: neo4j_driver.py:151-161]; `EmbedderClient.create_batch` [VERIFIED: embedder/client.py].

### Pattern 3: Preserve-on-update Cypher (not stock save)

**What:** MERGE on deterministic uuid; `ON CREATE SET` full allowlisted props + `created_at`; `ON MATCH SET` only mutable allowlisted fields + `updated_at` when hash differs; never `SET n = $map`.  
**When to use:** Entity and edge catalog persistence.  
**Anti-source:** stock query [VERIFIED: node_db_queries.py:182-190].

### Pattern 4: Server-owned labels and properties

**What:** Map allowlisted entity_type → fixed Neo4j label string in code. Parameterize all values. Re-validate at query builder even after Pydantic (`model_construct` bypass risk).  
**When to use:** All catalog Cypher.  
**Source:** `SAFE_CYPHER_IDENTIFIER_PATTERN` + `validate_node_labels` [VERIFIED: helpers.py:35,174-186].

### Pattern 5: Typed endpoint resolution for edges

**What:** Before edge write, MATCH `(n:Entity {group_id, name: graph_key})` and require custom type label present; bare Entity-only → `generic_endpoint_conflict`; missing → `missing_endpoint`; wrong type → `endpoint_type_mismatch`. Never CREATE endpoints.  
**When to use:** `upsert_typed_edges` (Phase 1). Same-request entity creation is Phase 2 batch only.

### Anti-Patterns to Avoid

- **Stock `EntityNode.save` / `EntityEdge.save` for catalog domain:** property clobber and uuid4 defaults.
- **`add_triplet` / `add_memory` / QueueService on catalog path:** generic endpoints, async non-commit, LLM.
- **Caller UUID as MERGE key:** breaks idempotency.
- **Auto-generate UUID namespace:** re-keys entire catalog on redeploy.
- **`execute_query` multi-statement without `transaction()`:** auto-commit partial graphs.
- **Interpolating client property names into SET:** injection / schema drift.
- **Logging full catalog payloads or source text:** SAFE-05 violation.
- **Mutating `oracle-catalog-v2` or calling `clear_graph` in tests:** out of scope / destructive.
- **Writing outside `oracle-catalog-tool-test` in tests:** isolation contract.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| UUIDv5 | Custom hash-to-uuid | `uuid.uuid5` | RFC 4122 |
| SHA-256 | MD5 / homebrew digest | `hashlib.sha256` | Project forbids MD5 |
| Canonical JSON | Ad-hoc string concat | `json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)` + reject NaN/Inf | Cross-client stability |
| group_id validation | New regex | `validate_group_id` | Existing contract |
| Label safety | Trust client | Allowlist enum + `validate_node_labels` at builder | Injection defense |
| Async Neo4j tx | DIY session mgmt | `Neo4jDriver.transaction()` | Commit/rollback correct |
| Embeddings | New embedder | Configured `EmbedderClient` via factories | Same vectors as search |
| MCP registration | Second server/app | Existing `FastMCP` + `@mcp.tool()` | Additive surface only |
| Search for interop tests | New search engine | Existing `search_nodes` / `search_memory_facts` | ENTY-13 / EDGE-12 |

**Key insight:** Complexity is write semantics and safety, not inventing crypto or drivers.

## Common Pitfalls

### Pitfall 1: Caller- or uuid4-based identity
**What goes wrong:** Retries create second nodes.  
**Why:** Graphiti defaults `uuid4()` on `Node`/`Edge` [VERIFIED: nodes.py:94, edges.py:50]; `add_triplet` uses uuid4 when omitted.  
**How to avoid:** Always set uuid from `uuid5` before any write; never trust client UUID as MERGE key.  
**Warning signs:** Double ingest yields two UUIDs for one `graph_key`.

### Pitfall 2: Non-canonical hashing
**What goes wrong:** False `content_hash_mismatch` or false updates.  
**How to avoid:** Single server canonicalize function; client hash audit-only.  
**Warning signs:** Reordered keys change hash; uppercase digests.

### Pitfall 3: `SET n = $entity_data` clobber
**What goes wrong:** Loses properties, rewrites `created_at`.  
**Why:** Stock save [VERIFIED: node_db_queries.py:185].  
**How to avoid:** Dedicated ON CREATE / ON MATCH Cypher; protected property denylist.

### Pitfall 4: Label accretion / generic endpoints
**What goes wrong:** Multi-type labels or bare Entity endpoints.  
**How to avoid:** Exactly `{Entity, Type}`; type conflict fails; edges never CREATE endpoints.

### Pitfall 5: Cypher injection via dynamic identifiers
**What goes wrong:** Client label/property in f-string Cypher.  
**How to avoid:** Fixed allowlists; parameterize values; re-validate at builder.

### Pitfall 6: Concurrent double-create
**What goes wrong:** Two logical objects for one key.  
**Why:** Indexes are non-unique; no stock unique on `(group_id, graph_key)` [ASSUMED].  
**How to avoid:** MERGE only on deterministic UUIDv5 inside one transaction.

### Pitfall 7: Embed-after-write or multi auto-commit
**What goes wrong:** Partial graph on embed/tx failure.  
**How to avoid:** Embed all first; single `transaction()` for atomic request; `atomic=false` still commits per successful item before returning success.

### Pitfall 8: Using queue / LLM accidentally
**What goes wrong:** Non-deterministic, async success.  
**How to avoid:** CatalogService never imports/calls `QueueService` or `llm_client`; unit tests assert mock call counts zero.

### Pitfall 9: Dirty worktree pollution
**What goes wrong:** Accidental commit of unrelated k8s/codegraph/sample changes.  
**How to avoid:** Stage only catalog source/tests/docs; leave `mcp_server/k8s/graphiti-neo4j.yaml`, `.codegraph/`, `mcp_server/sample_catalog.json` untouched [VERIFIED: STATE.md].

### Pitfall 10: Test group leakage
**What goes wrong:** Writes to live groups.  
**How to avoid:** Fixture `group_id == 'oracle-catalog-tool-test'` only; never clear other groups.

## Code Examples

### Deterministic identity + hash

```python
# Source: stdlib uuid/hashlib/json — verified in research session
from __future__ import annotations

import hashlib
import json
import math
import uuid
from typing import Any


def catalog_entity_uuid(namespace: uuid.UUID, group_id: str, entity_type: str, graph_key: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|{entity_type}|{graph_key}'))


def catalog_edge_uuid(namespace: uuid.UUID, group_id: str, edge_type: str, edge_key: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|{edge_type}|{edge_key}'))


def _reject_non_finite(obj: Any) -> None:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise ValueError('non-finite number')
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_non_finite(v)
    elif isinstance(obj, list):
        for v in obj:
            _reject_non_finite(v)


def canonical_sha256(payload: dict[str, Any]) -> str:
    _reject_non_finite(payload)
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()  # 64 lowercase hex
```

### Real Neo4j transaction boundary

```python
# Source: graphiti_core/driver/neo4j_driver.py:151-161
async with driver.transaction() as tx:
    await tx.run(entity_merge_cypher, **params)
    # commit on clean exit; rollback on exception
```

### Entity embedding before write (concept)

```python
# Source: graphiti_core/nodes.py:506-509 pattern; catalog embeds composite text per ENTY-07
text = f'{graph_key}\n{database_qualified_name}\n{summary}'.replace('\n', ' ')
name_embedding = await embedder.create(input_data=[text])
# only then:
async with driver.transaction() as tx:
    ...
```

### Edge shape compatible with search

```python
# Source: edge_db_queries.py Neo4j RELATES_TO MERGE pattern (adapted; do not use SET e = $map)
# MATCH endpoints by uuid (already resolved typed)
# MERGE (source)-[e:RELATES_TO {uuid: $uuid}]->(target)
# SET e.name = $edge_type, e.fact = $fact, e.group_id = $group_id, ...
# CALL db.create.setRelationshipVectorProperty(e, 'fact_embedding', $fact_embedding)
```

### Config extension sketch

```python
# Source: mcp_server/src/config/schema.py GraphitiConfig pattern
class CatalogConfig(BaseModel):
    enabled: bool = False
    uuid_namespace: str | None = None  # must parse as UUID when enabled
    max_entities_per_batch: int = 500
    max_edges_per_batch: int = 2000
    max_provenance_links_per_batch: int = 5000  # Phase 1 config surface; writes Phase 2


class GraphitiConfig(BaseSettings):
    ...
    catalog_upsert: CatalogConfig = Field(default_factory=CatalogConfig)
```

Env: nested delimiter `__` already configured [VERIFIED: schema.py:290]. Map `GRAPHITI_CATALOG_UUID_NAMESPACE` explicitly if not nested under `catalog_upsert`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Semantic `add_memory` + LLM extract | Deterministic typed upsert tools | This milestone | Exact identity for catalogs |
| `add_triplet` optional uuid4 endpoints | Typed endpoints required; no create | This milestone | No generic pollution |
| Auto-commit `execute_query` saves | `driver.transaction()` domain writes | Catalog path only | Atomic multi-item requests |
| uuid4 node defaults | Server UUIDv5 + immutable namespace | Catalog path only | Retry-safe identity |
| Full map `SET n = $entity_data` | ON CREATE / ON MATCH allowlisted props | Catalog store only | Preserve created_at / audit |

**Deprecated/outdated for this phase:**
- MD5 content audit
- FalkorDB/Kuzu/Neptune catalog write claims
- Async queue success as write confirmation

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Namespace must never be auto-generated at runtime | CONF-03 | Redeploy re-keys graph if uuid4 default sneaks in |
| A2 | Prefer MCP-package implementation over graphiti_core changes | Architecture | If public 0.29.2 lacks needed tx access on client.driver, need core patch |
| A3 | Stock indexes lack unique `(group_id, graph_key)` | Pitfall 6 | Rely solely on UUIDv5 MERGE |
| A4 | Edge searchability via `RELATES_TO.name` / `fact` matches `search_memory_facts` | EDGE-12 | May need exact field alignment with SearchFilters |
| A5 | Embedding text = graph_key + database_qualified_name + summary OK for ENTY-07 | ENTY-07 | Product may want different corpus |
| A6 | Nested `source_refs` serialize as JSON string property | ENTY-06 | Neo4j nested map limits |
| A7 | Phase 1 `require_provenance` only reports absence | VERI-04 | Matches CONTEXT deferred provenance |

## Open Questions (RESOLVED)

1. **Public Graphiti client driver access for custom Cypher** — RESOLVED
   - Decision: Use `client.driver` (`Neo4jDriver.transaction`) for catalog multi-statement MERGEs. Gate writes when `provider == NEO4J`. No public multi-statement catalog helper required.
   - Evidence: MCP Graphiti client exposes driver; `Neo4jDriver.transaction` is the established write boundary (Pattern 2, Architecture Patterns).

2. **Exact property names for edge type in hybrid search** — RESOLVED
   - Decision: Persist allowlisted edge type in `e.name`; searchable text in `e.fact`; vector in `e.fact_embedding`. Also store `edge_key`, `content_sha256`, `batch_id`. No separate `edge_type` property required for Phase 1.
   - Evidence: EntityEdge / edge search filters use `e.name in $edge_types` and hybrid fact search uses `fact` + `fact_embedding` (Search Compatibility, EDGE-12).

3. **Dry-run embedding cost** — RESOLVED
   - Decision: Dry-run still generates embeddings for readiness validation (CONTEXT mandatory write rules). Unit tests mock the embedder; integration may use mock or require key. Never open a write transaction on dry-run.
   - Evidence: CONTEXT requires embed-before-tx including dry-run readiness; CI without API keys uses AsyncMock.

4. **Cleanup strategy for integration tests** — RESOLVED
   - Decision: Integration fixture teardown deletes only `group_id='oracle-catalog-tool-test'`. Never `clear_graph`, never delete other groups or live data.
   - Evidence: Project constraints Isolation / Operations; PATTERNS Test Pattern.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime / tests | ✓ | 3.12.10 | — |
| Node | gsd-tools only | ✓ | v24.14.0 | — |
| uv | package install | ? | — | `uv sync` in mcp_server |
| Neo4j 5.26+ | Integration GATE-02 | ? | not probed running | Unit mocks; mark int `requires_neo4j` |
| OpenAI/embedder API | Real embeddings | ? | env-dependent | AsyncMock unit; int mock or require key |
| mcp_server deps | Implementation | ✓ | lockfile present | `uv sync` |

**Missing dependencies with no fallback:**
- Live Neo4j required for GATE-02 green; planner must include env setup or skip-with-marker policy that still blocks Phase 2 if int not run.

**Missing dependencies with fallback:**
- Embedder API → AsyncMock in unit tests; deterministic fake vectors for ordering tests.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (MCP `>=9.0.3`) + pytest-asyncio (`asyncio_mode=auto`) |
| Config file | `mcp_server/tests/pytest.ini` (markers: `unit`, `integration`, `requires_neo4j`) |
| Quick run command | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py tests/test_catalog_service.py -q` |
| Full suite command | `cd mcp_server && uv run pytest tests/test_catalog_*.py -q` |
| Integration only | `cd mcp_server && uv run pytest tests/test_catalog_neo4j_int.py -m "integration and requires_neo4j"` |
| Format / lint / type | `cd mcp_server && uv run ruff format --check . && uv run ruff check . && uv run pyright` |
| MCP schema listing | Assert four catalog tools registered |
| Existing MCP regressions | Relevant existing `mcp_server/tests/test_*.py` subset |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONF-01..05 | Config enable/disable, namespace, limits, Neo4j gate | unit | `pytest tests/test_catalog_models.py -k config` | ❌ Wave 0 |
| SAFE-01..03 | group_id, allowlists, limits, finite, confidence, protected | unit | `pytest tests/test_catalog_models.py` | ❌ Wave 0 |
| SAFE-04 | Structured error codes | unit | `pytest tests/test_catalog_service.py -k error` | ❌ Wave 0 |
| SAFE-05 | Log sanitization | unit | `pytest tests/test_catalog_service.py -k log` | ❌ Wave 0 |
| IDEN-01,02,05 | UUIDv5 determinism; caller UUID ignored | unit | `pytest tests/test_catalog_identity.py` | ❌ Wave 0 |
| IDEN-06,07 | Canonical hash + mismatch | unit | `pytest tests/test_catalog_identity.py -k hash` | ❌ Wave 0 |
| IDEN-08 | unchanged vs update vs conflict | unit + int | service mock + neo4j int | ❌ Wave 0 |
| ENTY-01..11 | Upsert validation, embed-before-tx, atomic/dry-run | unit | `pytest tests/test_catalog_service.py` | ❌ Wave 0 |
| ENTY-07 | Embed called before transaction | unit | mock order assert | ❌ Wave 0 |
| ENTY-12 | Concurrent identical upserts → one node | int | `pytest tests/test_catalog_neo4j_int.py -k concurrent` | ❌ Wave 0 |
| ENTY-13 | `search_nodes` finds typed entities | int | neo4j int + search | ❌ Wave 0 |
| RESO-01..04 | Resolve anomalies; no writes | unit + int | resolve tests | ❌ Wave 0 |
| EDGE-01..11 | Endpoints, identity, atomic, concurrency | unit + int | edge tests | ❌ Wave 0 |
| EDGE-12 | `search_memory_facts` finds facts | int | neo4j int | ❌ Wave 0 |
| VERI-01..05 | Verify counts/lists; no writes; require_provenance report | unit + int | verify tests | ❌ Wave 0 |
| GATE-01 | Focused unit suite green | unit | catalog unit modules | ❌ Wave 0 |
| GATE-02 | Neo4j fixture suite (6 entities, 4 edges, 2 FKs, conflicts, retries, concurrency, search, rollback) | int | `test_catalog_neo4j_int.py` | ❌ Wave 0 |
| GATE-03 | No LLM/queue/generic endpoint/out-of-group mutation | unit + int | spies + group asserts | ❌ Wave 0 |
| GATE-04 | format/lint/typecheck/schema/regressions | tooling | ruff/pyright + tool list | ❌ Wave 0 |
| GATE-05 | Phase 1 report gates Phase 2 | manual/doc | `01-PHASE1-REPORT.md` after green | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** quick unit catalog tests
- **Per wave merge:** all `test_catalog_*.py` (int when Neo4j available)
- **Phase gate:** Full unit + Neo4j int green; ruff/pyright; four tools listed; relevant existing MCP tests; Phase 1 report

### Wave 0 Gaps

- [ ] `mcp_server/tests/test_catalog_models.py` — CONF/SAFE validation, allowlists, prefixes, protected props
- [ ] `mcp_server/tests/test_catalog_identity.py` — UUIDv5 + SHA-256 contracts
- [ ] `mcp_server/tests/test_catalog_service.py` — embed-before-tx, feature gates, dry-run, atomic rollback (AsyncMock)
- [ ] `mcp_server/tests/test_catalog_neo4j_int.py` — GATE-02; `group_id='oracle-catalog-tool-test'`; markers `integration` + `requires_neo4j`
- [ ] Shared fixtures: catalog namespace UUID, mock embedder fixed vectors, Neo4j driver from env
- [ ] Framework already installed — no new pytest install

### Integration fixture outline (GATE-02)

Under `oracle-catalog-tool-test`:

1. Six typed entities (Database, Schema, Table, Column, Constraint, Index) with correct prefixes.
2. Four structural edges (Contains, PrimaryKeyOf, UniqueKeyOf, DocumentedBy).
3. Two distinct `ForeignKeyTo` edges sharing endpoints but different edge keys (EDGE-08).
4. Conflicts: type conflict, content_hash_mismatch, edge_identity_conflict, missing_endpoint, endpoint_type_mismatch, generic_endpoint_conflict.
5. Retry identical payload → all `unchanged`.
6. Concurrent identical upserts → single node/edge counts.
7. Atomic failure rolls back siblings (`rolled_back`).
8. `search_nodes` with type filter; `search_memory_facts` for edge fact text.
9. Assert no nodes outside test group; no LLM/queue calls.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | MCP transport auth out of phase scope |
| V3 Session Management | no | — |
| V4 Access Control | partial | `group_id` isolation; no cross-group writes |
| V5 Input Validation | yes | Pydantic allowlists, lengths, finite numbers, confidence [0,1], protected props |
| V6 Cryptography | yes | stdlib SHA-256 + UUIDv5 only |
| V5.3 Injection | yes | No client labels/properties as Cypher identifiers; parameterized values |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher label/property injection | Tampering | Fixed server allowlists; `validate_node_labels`; parameters for values |
| Cross-group data access | Information Disclosure | Required validated `group_id`; MATCH always filters group_id |
| Log leakage of catalog/PII | Information Disclosure | Log batch_id + counts only (SAFE-05) |
| Identity spoof via caller UUID | Spoofing | Server UUIDv5 only; `deterministic_uuid_conflict` |
| Partial write on failure | Tampering | Embed-before-tx + real transaction rollback |
| Resource exhaustion via huge batches | Denial of Service | Config limits 500/2000/5000 |
| Schema pollution via free labels | Tampering | 15 entity + 16 edge allowlists only |

## Project Constraints (from CLAUDE.md)

- Preserve existing Graphiti MCP tools and behaviors (additive only).
- Neo4j first; Neo4j 5.26+; no multi-backend catalog write claims.
- Server UUIDv5 only; immutable `GRAPHITI_CATALOG_UUID_NAMESPACE`.
- Never interpolate unvalidated client labels/property names into Cypher.
- Writes return only after commit or rollback; atomic batches full rollback on failure.
- Embeddings before Neo4j write transaction.
- Tests/writes constrained by `group_id`; tests only `oracle-catalog-tool-test`.
- Validate complete requests, limits, hashes, prefixes, nested refs, confidence, NaN/Inf, protected properties.
- Log batch IDs and counts only — never credentials or full payloads.
- Preserve original `created_at`, labels, exact `name_raw`/`name_canonical`; add `updated_at`.
- Defaults: 500 entities, 2000 edges, 5000 provenance links per batch.
- Phase 2 blocked until Phase 1 gate + report.
- No deployment, live-group writes, full ingest, graph clearing, existing-data deletion.
- Code style: Ruff line length 100, single quotes; Pyright; async-first.
- MCP development from `mcp_server/`; `uv sync`; pytest markers as existing.

## Sources

### Primary (HIGH confidence)

- `.planning/phases/01-typed-catalog-primitives/01-CONTEXT.md` — locked decisions
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/PROJECT.md`
- `.planning/research/{SUMMARY,ARCHITECTURE,FEATURES,PITFALLS,STACK}.md` — project research (2026-07-16)
- `mcp_server/src/graphiti_mcp_server.py` — FastMCP tools, add_triplet/search patterns
- `mcp_server/src/config/schema.py` — settings precedence and extension point
- `graphiti_core/driver/neo4j_driver.py` — `transaction()` commit/rollback
- `graphiti_core/models/nodes/node_db_queries.py` — stock `SET n = $entity_data`
- `graphiti_core/models/edges/edge_db_queries.py` — RELATES_TO MERGE pattern
- `graphiti_core/nodes.py` / `edges.py` — EntityNode/EntityEdge fields, uuid4 defaults, save paths
- `graphiti_core/helpers.py` — `validate_group_id`, `validate_node_labels`, SAFE_CYPHER
- `graphiti_core/embedder/client.py` — `create` / `create_batch`
- `mcp_server/tests/pytest.ini` — markers and asyncio config
- `.planning/codebase/{ARCHITECTURE,CONVENTIONS,TESTING}.md`

### Secondary (MEDIUM confidence)

- Research synthesis on unique constraints and search field alignment (re-check in implementation)
- Exact lockfile pin numbers (class verified; not every pin re-dumped)

### Tertiary (LOW confidence)

- Live Neo4j/embedder availability on this machine (running service not fully probed)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — reuse installed MCP/Graphiti/Neo4j/Pydantic only; no new packages
- Architecture: HIGH — dedicated CatalogService/Store matches code constraints and prior research
- Pitfalls: HIGH — stock save clobber, uuid4, triplet generics, embed/tx ordering verified in code

**Research date:** 2026-07-16  
**Valid until:** 2026-08-15 (stable stack; re-check if graphiti-core or neo4j driver majors change)
