# Phase 2: Topology Authority, Evidence Contract, Hashes, and Capabilities - Pattern Map

**Mapped:** 2026-07-18
**Files analyzed:** 16 (new/modified)
**Analogs found:** 16 / 16 (role/data-flow matches; no store/control-plane write analogs required — hard gate)

Hard gate: pure authorities + preflight wiring + read-only MCP tool + unit/spy tests only. No `catalog_store` write redesign, no prepare/commit, no canary, no `oracle-catalog-v2`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp_server/src/models/catalog_topology.py` | model / utility (authority) | transform (pure allowlist) | `mcp_server/src/models/catalog_common.py` (`CATALOG_EDGE_TYPES`, `ENTITY_TYPE_PREFIXES`) | exact |
| `mcp_server/src/models/catalog_evidence.py` | model | request-response (trust boundary) | `mcp_server/src/models/catalog_provenance.py` + `catalog_edges.py` (strict models, XOR/bounds) | exact |
| `mcp_server/src/models/catalog_batch.py` | model | request-response | same file (`UpsertCatalogBatchRequest`, `NestedProvenancePayload`) | exact |
| `mcp_server/src/models/catalog_edges.py` | model | request-response | same file (`CatalogEdgeItem`, EnforcedBy rule) | exact |
| `mcp_server/src/models/catalog_responses.py` | model | request-response | same file (`CatalogBatchWriteResponse`, `CatalogIngestStatusResponse`) | exact |
| `mcp_server/src/models/catalog_common.py` | config / utility | transform | same file (limits, `CatalogErrorCode`) | exact |
| `mcp_server/src/services/catalog_identity.py` | utility (pure) | transform | same file (`canonical_sha256`, `catalog_evidence_link_uuid`, `assert_optional_client_hash`) | exact |
| `mcp_server/src/services/catalog_capabilities.py` | service (pure builder) | request-response (read-only) | `catalog_identity.py` purity + `CatalogConfig` fields | role-match |
| `mcp_server/src/services/catalog_service.py` | service | request-response + spy-gated I/O | same file (`upsert_typed_edges`, `_batch_canonical_payload`, gates) | exact |
| `mcp_server/src/graphiti_mcp_server.py` | route / controller | request-response | same file (`CATALOG_TOOL_NAMES`, catalog `@mcp.tool` wrappers, `get_status`) | exact |
| `mcp_server/tests/test_catalog_topology.py` | test | batch (param tables) | `test_catalog_models.py` allowlist tables | role-match |
| `mcp_server/tests/test_catalog_evidence.py` | test | batch | `test_catalog_models.py` provenance/bounds | role-match |
| `mcp_server/tests/test_catalog_hash.py` | test | transform | `test_catalog_identity.py` + service hash spies | role-match |
| `mcp_server/tests/test_catalog_capabilities.py` | test | request-response | `test_catalog_service.py` tool registration + disabled-write spies | role-match |
| `mcp_server/tests/catalog_phase2_gate_runner.py` | utility / test harness | batch | `mcp_server/tests/catalog_phase1_gate_runner.py` | exact |
| `mcp_server/tests/run_phase2_gate.py` or runner entry | utility | batch | phase1 runner `run_gate` / module main | exact |

**Do not modify in Phase 2 (hard gate):** `catalog_store.py` write paths, Neo4j Cypher for evidence/manifest/prepare, canary scripts, live-group fixtures for `oracle-catalog-v2`.

## Pattern Assignments

### `mcp_server/src/models/catalog_topology.py` (utility, transform)

**Analog:** `mcp_server/src/models/catalog_common.py`

**Imports / constants pattern** (lines 135–179):
```python
ENTITY_TYPE_PREFIXES: dict[str, str] = { ... }
CATALOG_ENTITY_TYPES: frozenset[str] = frozenset(ENTITY_TYPE_PREFIXES.keys())
CATALOG_EDGE_TYPES: frozenset[str] = frozenset({
    'Contains', 'PrimaryKeyOf', 'UniqueKeyOf', 'ForeignKeyTo', 'EnforcedBy',
    'TriggerOn', 'SynonymFor', 'DocumentedBy', 'Calls', 'ReadsFrom', 'WritesTo',
    'JoinsWith', 'ReferencesByCode', 'DependsOn', 'DerivedFrom', 'UsesSequence',
})
```

**Error code already reserved** (line 223):
```python
edge_endpoint_pair_not_allowed = 'edge_endpoint_pair_not_allowed'
```

**Core pattern to implement (copy style of allowlist + raise ValueError with code text):**
```python
# NEW module — single authority
EDGE_ENDPOINT_MAP: dict[str, frozenset[tuple[str, str]]] = {
    'ForeignKeyTo': frozenset({('Column', 'Column'), ('Table', 'Table')}),  # dual: fixtures use Table
    # ... all 16 keys == CATALOG_EDGE_TYPES; no LikelyReferencesTo/MapsTo/SynchronizesTo
}

def validate_edge_endpoint_pair(edge_type: str, source_entity_type: str, target_entity_type: str) -> None:
    allowed = EDGE_ENDPOINT_MAP.get(edge_type)
    if allowed is None or (source_entity_type, target_entity_type) not in allowed:
        raise ValueError(
            f'{CatalogErrorCode.edge_endpoint_pair_not_allowed}: edge endpoint pair not allowed'
        )

def endpoint_map_export() -> dict[str, list[list[str]]]:
    # sorted pairs for capabilities; generate from EDGE_ENDPOINT_MAP only
    ...
```

**Integration:** import only from models/service/capabilities/tests — never accept client-supplied map.

---

### `mcp_server/src/models/catalog_evidence.py` (model, request-response)

**Analog:** `mcp_server/src/models/catalog_provenance.py` + `catalog_edges.py`

**Strict base + allowlist validators** (provenance lines 38–140):
```python
class CatalogSourceItem(CatalogStrictModel):
    ...
class CatalogProvenanceEntityTarget(CatalogStrictModel):
    entity_type: str
    graph_key: str = Field(..., max_length=MAX_GRAPH_KEY_LENGTH)
    @field_validator('entity_type')
    @classmethod
    def _entity_type_allowlisted(cls, v: str) -> str:
        if v not in ENTITY_TYPE_PREFIXES:
            raise ValueError(f'entity_type not allowlisted: {v}')
        return v
```

**Finite confidence** (`catalog_edges.py` lines 97–104):
```python
@field_validator('confidence')
@classmethod
def _finite_confidence(cls, v: float | None) -> float | None:
    if v is None:
        return v
    if math.isnan(v) or math.isinf(v):
        raise ValueError('confidence must be finite')
    return v
```

**SHA-256 format** (provenance lines 75–82):
```python
if not re.fullmatch(SHA256_HEX_RE, v):
    raise ValueError('content_sha256 must be 64 lowercase hex characters')
```

**Core evidence pattern (prescriptive; copy CatalogStrictModel + XOR model_validator):**
```python
class CatalogEvidenceLink(CatalogStrictModel):
    source_key: str
    entity_target: CatalogEvidenceEntityTarget | None = None
    edge_target: CatalogEvidenceEdgeTarget | None = None
    evidence_kind: Literal['oracle_dictionary','ddl','view_sql','plsql_source','comment','manual']
    locator: CatalogEvidenceLocator | None = None
    excerpt: str | None = Field(default=None, max_length=MAX_EVIDENCE_LENGTH)
    extractor_name: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    extractor_version: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    rule_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    content_sha256: str | None = None
    # model_validator: exactly one of entity_target / edge_target
```

**Anti-pattern:** do not auto-convert Cartesian `sources × targets` (`NestedProvenancePayload` lines 48–55 product counter is the legacy shape to reject on catalog-v2 batch).

---

### `mcp_server/src/models/catalog_batch.py` (model, request-response)

**Analog:** same file lines 39–133

**Live Cartesian nested shape** (lines 39–55) — Phase 2 replaces catalog-v2 path:
```python
class NestedProvenancePayload(CatalogStrictModel):
    sources: list[CatalogSourceItem] = Field(...)
    entity_targets: list[CatalogProvenanceEntityTarget] = Field(default_factory=list)
    edge_targets: list[CatalogProvenanceEdgeTarget] = Field(default_factory=list)
    # total_links = len(sources) * (len(entity_targets) + len(edge_targets))  # REJECT for v2
```

**Optional hashes today** (lines 70–71) — HASH-01 makes catalog required:
```python
request_sha256: str | None = None
catalog_sha256: str | None = None  # → required str Field(...); keep lowercase 64-hex validator
```

**Pattern change (smallest blast radius):**
- Prefer `sources: list[CatalogSourceItem]` + `evidence_links: list[CatalogEvidenceLink]` on batch (or nested non-Cartesian payload).
- Reject legacy multi-target product fields on catalog-v2 batch (EVID-14); no adapter.
- Keep `dry_run` / caller `request_sha256` as transport fields (hash exclusions).
- Leave standalone `UpsertProvenanceRequest` Cartesian until Phase 3B (tool name preserved).

---

### `mcp_server/src/models/catalog_edges.py` (model, request-response)

**Analog:** same file

**Type allowlists only today** (lines 54–66) — add topology call:
```python
@field_validator('edge_type')
def _edge_type_allowlisted(...):
    if v not in CATALOG_EDGE_TYPES: ...

# After allowlists, in model_validator or service preflight:
# validate_edge_endpoint_pair(self.edge_type, self.source_entity_type, self.target_entity_type)
```

**Keep EnforcedBy evidence rule** (lines 106–109) — orthogonal to pair map:
```python
if self.edge_type == 'EnforcedBy' and (not self.evidence or not self.evidence.strip()):
    raise ValueError('EnforcedBy requires non-empty evidence')
```

**Service insertion point** (`catalog_service.upsert_typed_edges` docstring order lines 1782–1785, code after gate ~1787–1808):
```python
# Order today: gate → identity/hash → resolve_endpoint_typed → embed → tx
# Required: after gate (and preferably at model), BEFORE resolve_endpoint_typed (~1901)
for idx, item in enumerate(request.edges):
    try:
        validate_edge_endpoint_pair(
            item.edge_type, item.source_entity_type, item.target_entity_type
        )
    except ValueError:
        early_errors[idx] = CatalogItemResult(
            ...,
            error_code=CatalogErrorCode.edge_endpoint_pair_not_allowed,
            error_message='edge endpoint pair not allowed',
        )
```

---

### `mcp_server/src/services/catalog_identity.py` (utility, transform)

**Analog:** same file — pure, no I/O (module docstring lines 1–4)

**Canonical hash recipe** (lines 85–93):
```python
def canonical_sha256(payload: dict[str, Any]) -> str:
    _reject_non_finite(payload)
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()
```

**Evidence UUID stub** (lines 55–59) — flesh link_key material only:
```python
def catalog_evidence_link_uuid(namespace: uuid.UUID, group_id: str, link_key: str) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|{IDENTITY_SCHEMA_VERSION}|EvidenceLink|{link_key}'))
```

**Caller audit hash** (lines 101–110):
```python
def assert_optional_client_hash(client_hash: str | None, server_hash: str) -> None:
    if client_hash is None:
        return
    if client_hash.lower() != server_hash.lower():
        raise ValueError(f'{CatalogErrorCode.content_hash_mismatch}: client hash mismatch')
```

**Add (same purity constraints):**
```python
CANONICALIZATION_VERSION = 'catalog-canonical-v1'
CATALOG_SCHEMA_VERSION = 'catalog-schema-v1'

def namespace_fingerprint(namespace: uuid.UUID | None) -> str | None:
    if namespace is None:
        return None
    material = b'graphiti.catalog.nsfp.v1|' + namespace.bytes
    return hashlib.sha256(material).hexdigest()[:16]

def batch_request_canonical_payload(request) -> dict:  # move recipe HERE from service
    return {
        'canonicalization_version': CANONICALIZATION_VERSION,
        'identity_schema_version': request.identity_schema_version,
        'system_key': request.system_key,  # A2 include
        'group_id': request.group_id,
        'batch_id': request.batch_id,
        'catalog_sha256': request.catalog_sha256,
        'entities': sorted((entity_canonical_payload(e) for e in request.entities),
                          key=lambda d: (d['entity_type'], d['graph_key'])),
        'edges': sorted(..., key=lambda d: (d['edge_type'], d['edge_key'])),
        'sources': sorted(..., key=lambda d: d['source_key']),
        'evidence_links': sorted(..., key=lambda d: link_sort_key),
    }
# Exclude: dry_run, caller request_sha256, timestamps, retries, plan tokens
```

**Item payloads live today on service** (lines 124–156) — either re-export pure copies in identity or import service statics carefully; prefer pure functions in identity to avoid prepare coupling later.

---

### `mcp_server/src/services/catalog_service.py` (service, request-response)

**Analog:** same file — replace hash in place; wire preflight; no store redesign.

**Incomplete batch hash** (lines 3579–3609) — **replace, do not parallel**:
```python
@staticmethod
def _batch_canonical_payload(request: UpsertCatalogBatchRequest) -> dict[str, Any]:
    # LIVE: group_id, batch_id, entities[], edges[], provenance{sources, entity_targets, edge_targets}
    # MISSING: identity_schema_version, catalog_sha256, canonicalization_version, sort, evidence_links
    ...

@staticmethod
def batch_request_sha256(request: UpsertCatalogBatchRequest) -> str:
    return canonical_sha256(CatalogService._batch_canonical_payload(request))
```

**Batch early path** (lines 3693–3734) — hash after gate; echo new response fields:
```python
gate = self._batch_gate_error(client, request)
...
server_hash = self.batch_request_sha256(request)
assert_optional_client_hash(request.request_sha256, server_hash)
# On success/dry-run/safe fail where derivable, set:
# identity_schema_version, canonicalization_version, request_sha256=server_hash, catalog_sha256
```

**Gate pattern** (`_edge_gate_errors` 1722–1774 / `_batch_gate_error` 3611+): enabled → namespace → neo4j → limits. Topology is **not** a gate disable; it is per-item validation before resolve.

**Spy test pattern** (`test_catalog_service.py`): AsyncMock store methods; assert `resolve_endpoint_typed` / `embedder.create` / `execute_write` not called for bad topology or dry-run hash paths.

**FK fixture compatibility** (`test_catalog_service.py` `_edge` 1697–1711): Table→Table ForeignKeyTo — map must keep both Column and Table pairs.

---

### `mcp_server/src/models/catalog_responses.py` (model, request-response)

**Analog:** `CatalogBatchWriteResponse` lines 153–175; status hash fields lines 134–149

**Extend batch response (additive):**
```python
class CatalogBatchWriteResponse(BaseModel):
    ...
    batch_uuid: str | None = None
    # ADD:
    identity_schema_version: str | None = None
    canonicalization_version: str | None = None
    request_sha256: str | None = None  # server
    catalog_sha256: str | None = None
```

**New capabilities response** — non-strict `BaseModel` like other responses (not `CatalogStrictModel` request base). Follow field style of `CatalogIngestStatusResponse` (no secrets).

---

### `mcp_server/src/services/catalog_capabilities.py` (service, read-only)

**Analog purity:** `catalog_identity.py` (no Neo4j/embedder/LLM imports)

**Config inputs** (`config/schema.py` `CatalogConfig` 285–332):
```python
enabled: bool = False
uuid_namespace: str | None = None
max_entities_per_batch / max_edges_per_batch / max_provenance_links_per_batch
```

**Core pattern:**
```python
def build_catalog_capabilities(*, config: CatalogConfig, client: Any | None = None) -> CapabilitiesResponse:
    # never call build_indices / execute_write / schema ensure
    # uuid_namespace_configured = bool(valid parse)
    # namespace_fingerprint = namespace_fingerprint(parsed)  # never raw namespace
    # endpoint_map from catalog_topology.endpoint_map_export()
    # features: prepare_commit=False, explicit_evidence_links=True, manifests=False, manifest_verification=False
    # embeddings/indexes: ready | unknown | n/a without mutation
```

---

### `mcp_server/src/graphiti_mcp_server.py` (route, request-response)

**Catalog tool set** (lines 206–216):
```python
CATALOG_TOOL_NAMES: frozenset[str] = frozenset({
    'upsert_typed_entities', 'resolve_typed_entities', 'verify_catalog_batch',
    'upsert_typed_edges', 'upsert_provenance', 'get_catalog_ingest_status',
    'upsert_catalog_batch',
})
```

**Thin wrapper pattern** (upsert_catalog_batch 1459–1487):
```python
@mcp.tool()
async def upsert_catalog_batch(request: UpsertCatalogBatchRequest) -> CatalogBatchWriteResponse | ErrorResponse:
    global graphiti_service, catalog_service
    if graphiti_service is None:
        return ErrorResponse(error='Graphiti service not initialized')
    if catalog_service is None:
        catalog_service = CatalogService(catalog_config=graphiti_service.config.catalog_upsert)
    try:
        client = await graphiti_service.get_client()
        return await catalog_service.upsert_catalog_batch(client=client, request=request)
    except Exception as e:
        logger.error('upsert_catalog_batch failed batch_id=%s ... reason=%s', ..., type(e).__name__)
        return ErrorResponse(error='catalog upsert_catalog_batch failed')
```

**get_status contract** (`response_types.py` 41–43 + handler 1262–1292) — **preserve keys only**:
```python
class StatusResponse(TypedDict):
    status: str
    message: str
```

**Capabilities registration:**
- Add `@mcp.tool() async def get_catalog_capabilities()` **outside** write-enabled gate.
- Update tool-count tests (`test_catalog_service.py` ~4016–4023: `CATALOG_TOOL_NAMES | LEGACY_TOOL_NAMES == 21` today → +1).
- SAFE-08: either add to `CATALOG_TOOL_NAMES` if request validation applies, or leave as simple read tool without ValidationError rewrite — prefer read-only without request body.

**Logging pattern for catalog tools:** batch_id + counts + exception type only — never payloads/excerpts.

---

### Tests

| New test file | Analog | Patterns to copy |
|---------------|--------|------------------|
| `test_catalog_topology.py` | `test_catalog_models.py` (`test_catalog_edge_types_has_sixteen`, entity prefix tables) | parametrize allow/reject; `set(EDGE_ENDPOINT_MAP)==CATALOG_EDGE_TYPES`; deferred edges fail; entity types ∈ `CATALOG_ENTITY_TYPES` |
| `test_catalog_evidence.py` | `test_catalog_models.py` nested bounds / SHA validators | XOR target; kinds; finite confidence; Cartesian reject; no auto-convert |
| `test_catalog_hash.py` | `test_catalog_identity.py` (`canonical_sha256_*`) + service dry_run spies | mutate each included field; order invariance; exclude dry_run/caller hash; require catalog_sha256 |
| `test_catalog_capabilities.py` | `test_catalog_service.py` disabled feature + tool registration | writes disabled; missing ns; fingerprint ≠ raw; no mutation spies; get_status keys |
| Phase2 gate runner | `catalog_phase1_gate_runner.py` | `SCHEMA_VERSION`, `FORBIDDEN_GROUP='oracle-catalog-v2'`, `ALLOWED_TEST_GROUP='oracle-catalog-tool-test'`, `canary_executed=false`, focus tests, ruff/pyright paths, `derive_local_gate_pass` |

**Service spy helpers to reuse** (`test_catalog_service.py`): `_client` factory with AsyncMock driver/embedder; `_edge` / `_edge_request`; assert store methods not awaited.

**GROUP constant:** tests only `oracle-catalog-tool-test`.

## Shared Patterns

### Strict trust boundary
**Source:** `catalog_common.CatalogStrictModel` (`extra='forbid'`)
**Apply to:** all new request models (evidence, locator, targets, batch fields)

### Structured error codes
**Source:** `CatalogErrorCode` + `assert_optional_client_hash` / item `error_code` fields
**Apply to:** topology (`edge_endpoint_pair_not_allowed`), hash (`content_hash_mismatch`), capabilities failures as safe ErrorResponse

### Pure identity / hash
**Source:** `catalog_identity.py` — no network/Neo4j/embedder/queue imports (enforced by `test_identity_module_has_no_io_imports`)
**Apply to:** new fingerprint, batch recipe, evidence content hash, capabilities builder

### Pre-side-effect ordering
**Source:** service method docs + resolve call sites
**Order:** Pydantic validate → topology pair check → versioned request hash / caller audit → **then** status read / resolve_endpoint / embed / schema / tx
**Apply to:** `upsert_typed_edges`, `upsert_catalog_batch` (and future prepare — not this phase)

### Single authority, generated views
**Source:** `ENTITY_TYPE_PREFIXES` / `CATALOG_EDGE_TYPES` as single maps
**Apply to:** `EDGE_ENDPOINT_MAP` consumed by models, service, capabilities, tests — never hand-copied tables

### MCP thin wrappers
**Source:** catalog `@mcp.tool` functions in `graphiti_mcp_server.py`
**Apply to:** `get_catalog_capabilities` — init check, optional CatalogService, structured ErrorResponse, no payload logs

### get_status compatibility
**Source:** `StatusResponse` TypedDict `status` + `message` only
**Apply to:** CAPA-09 — leave body unchanged

### Phase gate harness
**Source:** `mcp_server/tests/catalog_phase1_gate_runner.py`
**Apply to:** Phase 2 runner — same safety ledger keys; expand FOCUS_TEST_FILES and RUFF_PATHS for topology/evidence/hash/capabilities modules; no canary/int probe

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| *(none blocking)* | — | — | Capabilities builder has no prior catalog capabilities module; pattern is pure identity + config composition (role-match listed above). Evidence link schema is new but clones provenance/edge strict models. |

## Hard-Gate Exclusions (planner)

Do **not** plan actions that:
- Add store methods for evidence/manifest/prepared-plan persistence
- Open new Neo4j write Cypher for topology or evidence
- Query or seed `oracle-catalog-v2`
- Run canary or live E2E against production groups
- Parallelize a second `batch_request_sha256` path
- Change `get_status` required TypedDict keys
- Register deferred edges `LikelyReferencesTo` / `MapsTo` / `SynchronizesTo`

## Metadata

**Analog search scope:** `mcp_server/src/models/catalog_*`, `mcp_server/src/services/catalog_*`, `mcp_server/src/graphiti_mcp_server.py`, `mcp_server/src/config/schema.py`, `mcp_server/src/models/response_types.py`, `mcp_server/tests/test_catalog_*`, `mcp_server/tests/catalog_phase1_gate_runner.py`
**Files scanned:** ~20 primary
**Pattern extraction date:** 2026-07-18
**Phase 1 gate prerequisite:** satisfied (`ready_for_phase_2=true` per RESEARCH)
