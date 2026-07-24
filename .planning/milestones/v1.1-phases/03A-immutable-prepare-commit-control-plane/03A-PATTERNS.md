# Phase 03A: Immutable Prepare/Commit Control Plane - Pattern Map

**Mapped:** 2026-07-18
**Files analyzed:** 18 (create/modify)
**Analogs found:** 18 / 18 (role or exact; no net-new stack)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp_server/src/models/catalog_prepare.py` (new) *or* extend `catalog_batch.py` | model | request-response | `mcp_server/src/models/catalog_batch.py` | exact |
| `mcp_server/src/models/catalog_responses.py` (add prepare/commit/discard responses) | model | request-response | same file `CatalogBatchWriteResponse` / `CatalogCapabilitiesResponse` | exact |
| `mcp_server/src/models/catalog_common.py` (HARD_* plan ceilings only; codes already exist) | model/config | transform | same file HARD_MAX_* + `CatalogErrorCode` | exact |
| `mcp_server/src/config/schema.py` (`CatalogConfig` plan fields) | config | request-response | `CatalogConfig` hard-clamp Fields | exact |
| `mcp_server/src/services/catalog_identity.py` (artifact hash, chunk uuid, token digest) | utility | transform | `canonical_sha256` + `catalog_prepared_plan_uuid` | exact |
| `mcp_server/src/services/catalog_prepared_artifact.py` (new, pure) | utility | transform | `catalog_identity.canonical_sha256` + research chunk design | role-match |
| `mcp_server/src/services/catalog_token.py` (new, pure) *or* helpers in identity | utility | transform | `catalog_capabilities.namespace_fingerprint` domain SHA-256 | role-match |
| `mcp_server/src/services/catalog_store.py` (plan root/chunk/CAS/capacity) | service/store | CRUD + request-response | `CatalogNeo4jStore` batch status claim + fixed Cypher | exact |
| `mcp_server/src/services/catalog_service.py` (prepare/commit/discard; extract preflight) | service | request-response | `upsert_catalog_batch` preflight→embed→tx order | exact |
| `mcp_server/src/services/catalog_capabilities.py` (real plan limits + feature flag) | service | request-response | `build_catalog_capabilities` HARD_* zeros | exact |
| `mcp_server/src/graphiti_mcp_server.py` (3 tools + CATALOG_TOOL_NAMES) | route/controller | request-response | `upsert_catalog_batch` + `CatalogSafeFastMCP` | exact |
| `mcp_server/tests/test_catalog_prepare_models.py` | test | request-response | `tests/test_catalog_models.py` | exact |
| `mcp_server/tests/test_catalog_prepared_artifact.py` | test | transform | `tests/test_catalog_hash.py` / `test_catalog_identity.py` | role-match |
| `mcp_server/tests/test_catalog_token.py` | test | transform | pure identity unit style | role-match |
| `mcp_server/tests/test_catalog_prepare_store.py` | test | CRUD | `tests/test_catalog_store_unit.py` | exact |
| `mcp_server/tests/test_catalog_prepare_service.py` | test | request-response | `tests/test_catalog_service.py` | exact |
| `mcp_server/tests/test_catalog_prepare_neo4j_int.py` | test | CRUD | `tests/test_catalog_neo4j_int.py` | exact |
| `mcp_server/tests/catalog_phase3a_gate_runner.py` + `run_phase3a_gate.py` | test/utility | batch | `catalog_phase2_gate_runner.py` + `run_phase2_gate.py` | exact |

## Pattern Assignments

### `models/catalog_prepare.py` / prepare request models (model, request-response)

**Analog:** `mcp_server/src/models/catalog_batch.py` + `catalog_common.CatalogStrictModel`

**Strict base** (`catalog_common.py` lines 19-22):
```python
class CatalogStrictModel(BaseModel):
    """Fail-closed request base: unknown fields rejected at every nesting depth."""
    model_config = ConfigDict(extra='forbid')
```

**Batch contract shell** (`catalog_batch.py` 73-88) — prepare reuses fields **minus** `dry_run`; commit is token-only:
```python
class UpsertCatalogBatchRequest(CatalogStrictModel):
    identity_schema_version: Literal['catalog-v2']
    system_key: SystemKey
    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    entities: list[CatalogEntityItem] = Field(default_factory=list, max_length=HARD_MAX_ENTITIES_PER_BATCH)
    edges: list[CatalogEdgeItem] = Field(default_factory=list, max_length=HARD_MAX_EDGES_PER_BATCH)
    provenance: NestedProvenancePayload | None = None
    request_sha256: str | None = None
    catalog_sha256: str = Field(..., min_length=64, max_length=64)
    dry_run: bool = False   # OMIT on PrepareCatalogBatchRequest
    atomic: StrictTrue = True
```

**Copy:** group_id validators, SHA256 hex validators, `_require_non_empty_work_and_system_scope`, graph_key system-scope checks (lines 90-165).

**Commit/discard models:** mirror `GetCatalogIngestStatusRequest` minimalism (token + optional `expected_request_sha256` only; `extra='forbid'`).

---

### `models/catalog_responses.py` prepare receipts (model, request-response)

**Analog:** `CatalogBatchWriteResponse` / `CatalogCapabilitiesResponse` in same file.

**Pattern:** bounded receipt fields; **no** payload/embeddings; echo server hashes; counts + status/state string; `Field(default_factory=...)` for dicts.

**Capabilities shape** (183-203 area): `limits: dict` with `configured`/`hard`; `features: dict[str, bool]`.

---

### `models/catalog_common.py` plan hard ceilings (config constants)

**Analog:** lines 67-73 batch HARD_MAX_*; error codes 224-227 already present — **do not remove or rename**.

```python
HARD_MAX_ENTITIES_PER_BATCH = 5000
# Add (research defaults; hard ceilings):
# HARD_PLAN_TTL_SECONDS = 86400
# HARD_MAX_PREPARED_PAYLOAD_BYTES = 16_777_216
# HARD_MAX_ACTIVE_PLANS = 32
# HARD_PREPARED_CHUNK_BYTES = 262_144
# HARD_MAX_CHUNKS_PER_PLAN = 128
```

**Prepared-plan codes (reuse only):**
```python
prepared_plan_not_found = 'prepared_plan_not_found'
prepared_plan_expired = 'prepared_plan_expired'
prepared_plan_conflict = 'prepared_plan_conflict'
prepared_plan_already_consumed = 'prepared_plan_already_consumed'
```
Map discarded → `prepared_plan_not_found` (oracle reduction). Capacity/payload → `batch_limit_exceeded`.

---

### `config/schema.py` CatalogConfig plan fields (config)

**Analog:** `CatalogConfig` 285-332 — `Field(ge=1, le=HARD_*)` clamps + env bind + enabled namespace validator.

```python
max_entities_per_batch: int = Field(default=500, ge=1, le=HARD_MAX_ENTITIES_PER_BATCH)
# Add: plan_ttl_seconds, max_prepared_payload_bytes, max_active_plans_per_group,
# prepared_chunk_bytes — each le= corresponding HARD_*.
```

---

### `services/catalog_identity.py` (utility, transform)

**Analog:** pure UUIDv5 + canonical hash (no Neo4j/embedder).

**Plan UUID** (71-75):
```python
def catalog_prepared_plan_uuid(namespace: uuid.UUID, group_id: str, plan_id: str) -> str:
    return str(
        uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|PreparedPlan|{plan_id}')
    )
```

**Canonical hash** (89-97) — artifact bytes use same JSON rules:
```python
def canonical_sha256(payload: dict[str, Any]) -> str:
    _reject_non_finite(payload)
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()
```

**Add:** `catalog_prepared_plan_chunk_uuid(ns, group_id, plan_id, chunk_index)` material  
`{group_id}|catalog-v2|PreparedPlanChunk|{plan_id}|{index}`; optional `artifact_bytes_sha256(bytes)`.

---

### `services/catalog_prepared_artifact.py` (utility, transform) — NEW pure

**Analog:** `canonical_sha256` + research §1 serialization.

**Core pattern (stdlib only):**
```python
# serialize: json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
# chunk: fixed prepared_chunk_bytes; store payload_b64 + chunk_index/offset/length/chunk_sha256
# reassemble: sort index → b64decode → concat → verify len + artifact_sha256; fail closed
# ARTIFACT_SERIALIZATION_VERSION = 'prepared-artifact-v1'
# Never embed artifact_sha256 inside hashed body
```

**No Neo4j/network.** Embeddings live **inside** artifact membership JSON only, not as control-node vector props.

---

### Token mint/digest (utility, transform)

**Analog:** domain-separated digest in `catalog_capabilities.namespace_fingerprint` (37-42):
```python
material = b'graphiti.catalog.nsfp.v1|' + namespace.bytes
return hashlib.sha256(material).hexdigest()[:16]
```

**Phase 3A token pattern (research; stdlib):**
```python
import hashlib, hmac, secrets
TOKEN_DIGEST_DOMAIN = b'graphiti.catalog.plan_token.v1|'

def mint_plan_token() -> str:
    return secrets.token_urlsafe(32)

def plan_token_digest(token: str) -> str:
    return hashlib.sha256(TOKEN_DIGEST_DOMAIN + token.encode('utf-8')).hexdigest()

def plan_token_matches(token: str, stored_digest: str) -> bool:
    return hmac.compare_digest(plan_token_digest(token), stored_digest)
```

Never store/log raw token; never derive from plan_uuid/batch/hash.

---

### `services/catalog_store.py` plan control plane (store, CRUD)

**Analog:** non-Entity `CatalogIngestBatch` + claim CAS (`catalog_store.py` 1226-1304).

**Fixed-label control pattern (status):**
```python
# Labels: CatalogIngestBatch — never Entity
MERGE (b:CatalogIngestBatch {uuid: $uuid, group_id: $group_id})
ON CREATE SET b.uuid = $uuid, b.group_id = $group_id, ...
```

**claim_batch_status** (1296-1304): first-row required; `CatalogStoreError(..., code='neo4j_transaction_failed')`.

**Phase 3A copy rules:**
- Labels fixed: `CatalogPreparedPlan`, `CatalogPreparedPlanChunk`, optional `CatalogPlanGroupLock`
- **CREATE once** for plan root/chunks (not MERGE that updates artifact bytes)
- Unique constraints IF NOT EXISTS: `(uuid, group_id)`, `token_digest`, chunk `(plan_uuid, group_id, chunk_index)`
- Capacity: same-tx `MERGE` lock + count active `PREPARED|COMMITTING` + CREATE
- CAS state transitions only legal edges (PREPARED→DISCARDED/EXPIRED/COMMITTING; COMMITTING re-entry same digest; **never** →PREPARED; terminals immutable)
- Property allowlist only; params never client labels
- Group isolation on every MATCH/CREATE

**Error type** (67+):
```python
class CatalogStoreError(ValueError):
    def __init__(self, message: str, *, code: str | None = None): ...
```

**Schema ensure:** mirror `ensure_uuid_uniqueness_constraints` / identity constraints CREATE IF NOT EXISTS only — never drop.

---

### `services/catalog_service.py` prepare/commit/discard (service, request-response)

**Analog:** `upsert_catalog_batch` 3690–4624 order.

**Write order to preserve / mirror:**
```
validate → server hash → pre-read/project → (dry_run return) → embed → ensure_schema → tx(claim + domain)
```

**Prepare order (new):**
```
validate (no dry_run) → server hash → shared preflight (extract from ~3690–4471)
  → size/TTL/capacity precheck → embed all required → ensure_plan_schema
  → ONE tx: capacity lock + CREATE plan+chunks only (zero Entity/RELATES_TO/Episodic/MENTIONS/CatalogIngestBatch)
```

**Embed-before-write** (4531-4560):
```python
entity_to_write = [prep for prep in entity_prepared if prep.projected_status != 'unchanged']
try:
    for prep in entity_to_write:
        prep.name_embedding = await client.embedder.create(input_data=[text])
    for prep in edge_to_write:
        prep.fact_embedding = await client.embedder.create(input_data=[...])
except Exception as exc:
    # return embedding_failed — no plan nodes
```

**Dry-run zero-write** (4473-4529): keep for upsert; prepare model has no dry_run.

**Commit Phase 3A:** token digest → load+reassemble+verify → CAS PREPARED→COMMITTING (or re-enter COMMITTING) → return claim receipt — **no domain write, no embedder/LLM/queue**.

**Discard:** token-only CAS PREPARED→DISCARDED; idempotent if DISCARDED; no domain delete.

**Reuse:** single identity/topology/hash authority — extract `_prepare_batch_preflight` shared by prepare + upsert; characterization tests first.

**Logging:** batch_id/plan_uuid/counts/state/error_code only — never token, payload, embeddings.

---

### `services/catalog_capabilities.py` (service, request-response)

**Analog:** lines 29-34 placeholders + 115-139 limits/features.

```python
HARD_MAX_PREPARED_PAYLOAD_BYTES = 0  # replace with real hard
HARD_MAX_ACTIVE_PLANS = 0
HARD_PLAN_TTL_SECONDS = 0
features={'prepare_commit': False, 'manifests': False, ...}
```

**Pattern:** pure builder; no Neo4j side effects. Flip `prepare_commit=True` only after tools registered **and** Phase 3A gate green. Expose configured + hard TTL/payload/active-plan/chunk honestly.

---

### `graphiti_mcp_server.py` MCP tools (controller, request-response)

**Analog:** `CATALOG_TOOL_NAMES` + `CatalogSafeFastMCP` (208-246) + `upsert_catalog_batch` (1462-1489).

```python
CATALOG_TOOL_NAMES: frozenset[str] = frozenset({
    'upsert_typed_entities', ..., 'upsert_catalog_batch',
    # ADD: 'prepare_catalog_batch', 'commit_prepared_catalog_batch', 'discard_prepared_catalog_batch',
})
```

**Thin wrapper pattern:**
```python
@mcp.tool()
async def upsert_catalog_batch(...) -> CatalogBatchWriteResponse | ErrorResponse:
    try:
        return await catalog_service.upsert_catalog_batch(client=client, request=request)
    except Exception as e:
        logger.error('upsert_catalog_batch failed batch_id=%s ... reason=%s', ..., type(e).__name__)
        return ErrorResponse(error='catalog upsert_catalog_batch failed')
```

Safe validation rewrite only for names in `CATALOG_TOOL_NAMES`. No monolith refactor beyond additive tools.

---

### Tests

| New test | Analog | Copy |
|----------|--------|------|
| `test_catalog_prepare_models.py` | `test_catalog_models.py` | strict extra=forbid, hash format, limits |
| `test_catalog_prepared_artifact.py` | `test_catalog_hash.py` / identity | pure serialize/chunk/reassemble/corrupt |
| `test_catalog_token.py` | identity pure tests | secrets entropy, domain digest, compare_digest, binding |
| `test_catalog_prepare_store.py` | `test_catalog_store_unit.py` | Cypher builders, CAS matrix, capacity, immutability |
| `test_catalog_prepare_service.py` | `test_catalog_service.py` | spies: embed before write; zero domain; no external on commit |
| `test_catalog_prepare_neo4j_int.py` | `test_catalog_neo4j_int.py` | `GROUP=oracle-catalog-tool-test`; DETACH DELETE that group only; never `oracle-catalog-v2` / `clear_graph` |
| `catalog_phase3a_gate_runner.py` | `catalog_phase2_gate_runner.py` | fail-closed ledger; `ready_for_phase_3b`; safety flags |
| `run_phase3a_gate.py` | `run_phase2_gate.py` | thin argv → runner.main |

**Int fixture invariants** (`test_catalog_neo4j_int.py` header): hardcoded group; teardown DETACH DELETE WHERE group_id; never clear_graph; never FORBIDDEN_GROUP mutation.

---

## Shared Patterns

### Strict validation boundary
**Source:** `CatalogStrictModel` + `CATALOG_TOOL_NAMES` + `catalog_validation_error_to_structured`  
**Apply to:** prepare/commit/discard requests and MCP tools.

### Fixed labels / no Cypher injection
**Source:** `CatalogNeo4jStore` resolve_entity_label + fixed batch Cypher  
**Apply to:** all plan/chunk/lock queries — allowlisted labels/properties only.

### Embeddings before write transactions
**Source:** `upsert_catalog_batch` 4531-4560; SAFE-11  
**Apply to:** prepare only. Commit uses frozen embeddings only.

### Real Neo4j transactions
**Source:** `client.driver.transaction()` in service; store methods take `tx`  
**Apply to:** capacity+create; CAS; never partial control-plane without commit/rollback.

### Non-Entity control records
**Source:** `CatalogIngestBatch`  
**Apply to:** `CatalogPreparedPlan` / `CatalogPreparedPlanChunk` / lock — no `Entity`, no searchable `name_embedding`/`fact_embedding` properties on control nodes.

### Group isolation
**Source:** every store MATCH includes `group_id`; int tests use `oracle-catalog-tool-test`  
**Apply to:** all prepare store ops and live tests.

### Domain-separated digests
**Source:** `namespace_fingerprint` domain prefix  
**Apply to:** plan_token digest domain `graphiti.catalog.plan_token.v1|`.

### Safe structured errors
**Source:** `CatalogErrorCode` prepared_plan_* + batch_limit_exceeded; bounded messages  
**Apply to:** missing/expired/discarded/consumed/conflict token outcomes.

### Capabilities truthfulness
**Source:** `build_catalog_capabilities` pure; features false until ready  
**Apply to:** plan limits + `prepare_commit` flag.

### Gate fail-closed ledger
**Source:** Phase 2 runner `derive_ready_for_phase_3a`, safety ledger  
**Apply to:** Phase 3A `ready_for_phase_3b`; record `canary_executed=false`, `oracle_catalog_v2_queried=false`, `clear_graph_called=false`.

## Explicit Reuse Seams

1. `UpsertCatalogBatchRequest` domain body → Prepare request without dry_run.
2. `CatalogService.upsert_catalog_batch` preflight (~3690-4471) → extract shared pure/pre-read path.
3. `batch_request_sha256` / topology / evidence resolution — single authority.
4. `catalog_prepared_plan_uuid` — deterministic plan identity.
5. `CatalogNeo4jStore` fixed Cypher + `CatalogStoreError` + schema ensure style.
6. `claim_batch_status` CAS shape → plan state CAS (new labels).
7. Embed-before-tx + dry_run zero-write for upsert regression.
8. `CATALOG_TOOL_NAMES` + safe FastMCP subclass.
9. Capabilities HARD placeholders → real values.
10. Phase 2 gate runner structure → Phase 3A gate.

## Anti-Patterns (do not copy)

| Anti-pattern | Why |
|--------------|-----|
| Raw token in Neo4j/logs/artifact | PLAN-07 |
| Hashes-only prepared artifact | PLAN-04 / D-02 |
| MERGE updating artifact bytes | immutability |
| Embed inside control-plane tx | partial plan on embed fail |
| Domain write in prepare/commit 3A | D-23 / Phase 3B |
| COMMITTING→PREPARED timeout reset | second writer |
| Client labels/properties in Cypher | SAFE injection |
| Fork second identity/hash authority | D-16 |
| New pip dependencies | research: stdlib only |
| `oracle-catalog-v2`, canary, clear_graph, deploy | D-32 |

## Fixed Labels / Cypher Property Allowlists

**Labels:** `CatalogPreparedPlan`, `CatalogPreparedPlanChunk`, `CatalogPlanGroupLock`  
**Never:** `Entity`, `Episodic`, semantic edge types, `CatalogIngestBatch` on prepare path.

**Plan root props:** uuid, group_id, batch_id, plan_id, token_digest, state, identity_schema_version, canonicalization_version, artifact_serialization_version, request_sha256, catalog_sha256, artifact_sha256, chunk_count, payload_bytes, entity/edge/source/evidence_link counts, created/updated/unchanged counts, expires_at, created_at, updated_at, optional committing_started_at.

**Chunk props:** uuid, group_id, plan_uuid, chunk_index, chunk_count, byte_offset, byte_length, chunk_sha256, payload_b64.

## State Machine (CAS)

| From | To | Who |
|------|-----|-----|
| absent | PREPARED | prepare (capacity ok, CREATE once) |
| PREPARED | DISCARDED | discard |
| PREPARED | EXPIRED | access if now≥expires_at |
| PREPARED | COMMITTING | commit claim |
| COMMITTING | COMMITTING | same-token re-entry (no PREPARED reset) |
| COMMITTING | COMMITTED | Phase 3B only |
| terminal | * | forbidden |

## Numeric Defaults (research discretion)

| Control | Default | Hard |
|---------|---------|------|
| plan_ttl_seconds | 3600 | 86400 |
| max_prepared_payload_bytes | 4_194_304 | 16_777_216 |
| prepared_chunk_bytes | 131_072 | 262_144 |
| max_chunks_per_plan | derived | 128 |
| max_active_plans_per_group | 8 | 32 |

## No-Silent-Drop Mapping (PLAN/SAFE/TEST)

| ID | Pattern home |
|----|----------------|
| PLAN-01 | prepare models (no dry_run/token authority) |
| PLAN-02 | service shared preflight extract |
| PLAN-03 | prepare tx control-only; spies |
| PLAN-04/05 | artifact module + store chunks + live int |
| PLAN-06 | prepare receipt; token once |
| PLAN-07/17 | token helpers + root binding fields |
| PLAN-08 | CatalogConfig + common HARD_* + capabilities |
| PLAN-09 | store fixed labels |
| PLAN-10 | commit request model token-only |
| PLAN-11/18/19 | store CAS + service error map + discard |
| PLAN-12 | commit zero external spies |
| PLAN-20 | upsert/dry_run regression |
| SAFE-11 | embed before plan tx |
| TEST-05 | gate runner + full suite |

PLAN-13..16 deferred Phase 3B — not silent drop.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| *(none critical)* | — | — | Token/artifact pure modules are new but patterns exist (domain SHA-256, canonical JSON). No event-driven or new framework seams. |

## TDD Touchpoints (Wave 0)

RED first: prepare models, artifact, token, store unit, service spies, neo4j_int scaffold, phase3a gate.  
Characterization on upsert preflight before extract.  
Gate: `ready_for_phase_3b=false` until live immutable proof + ledger safety.

## Metadata

**Analog search scope:** `mcp_server/src/{models,services,config}`, `mcp_server/src/graphiti_mcp_server.py`, `mcp_server/tests/test_catalog_*`, `catalog_phase2_gate_runner.py`  
**Files scanned:** ~25 catalog-relevant modules  
**Pattern extraction date:** 2026-07-18  
**Constraint:** pattern map only — no implementation, no Neo4j/canary/oracle-catalog-v2/deploy/clear_graph actions
