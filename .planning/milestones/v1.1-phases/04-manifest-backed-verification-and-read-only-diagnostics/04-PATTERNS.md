# Phase 4: Manifest-Backed Verification and Read-Only Diagnostics - Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 16 (modify 11 product + create/extend 5 test files)
**Analogs found:** 16 / 16 (all extensions of existing catalog modules)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp_server/src/config/schema.py` (`CatalogConfig`) | config | request-response | same file `CatalogConfig` | exact |
| `mcp_server/src/services/catalog_capabilities.py` | service (pure builder) | transform | same file `build_catalog_capabilities` | exact |
| `mcp_server/src/services/catalog_service.py` | service | request-response / CRUD-read | same: `_read_gate`, `resolve_typed_entities`, `verify_catalog_batch`, `get_catalog_ingest_status` | exact |
| `mcp_server/src/services/catalog_store.py` | service/store | request-response (read Cypher) | same: `_read_one`/`_read_many`, `read_manifest_root_for_recovery`, `match_edges_for_verify`, `build_load_prepared_plan_chunks_cypher` | exact |
| `mcp_server/src/services/catalog_manifest.py` | utility (pure) | transform | same: category projection + sort | role-match |
| `mcp_server/src/services/catalog_prepared_artifact.py` | utility | transform | same: `reassemble_artifact_bytes` (reuse only) | exact |
| `mcp_server/src/models/catalog_entities.py` | model | request-response | `ResolveTypedEntitiesRequest`, `VerifyCatalogBatchRequest` | exact |
| `mcp_server/src/models/catalog_responses.py` | model | request-response | `ResolveEntityResult`, `VerifyCatalogBatchResponse`, `CatalogIngestStatusResponse` | exact |
| `mcp_server/src/models/catalog_common.py` | config/model | — | `CatalogErrorCode.manifest_mismatch` (exists) | exact |
| `mcp_server/src/graphiti_mcp_server.py` | route/controller | request-response | `resolve_typed_entities` / `verify_catalog_batch` tools | exact |
| `mcp_server/tests/test_catalog_gates.py` | test | — | resolve/status gate tests in `test_catalog_service.py` | role-match |
| `mcp_server/tests/test_catalog_manifest_read.py` | test | — | `test_catalog_manifest.py` + service resolve tests | role-match |
| `mcp_server/tests/test_catalog_verify_manifest.py` | test | — | verify tests in `test_catalog_service.py` | role-match |
| `mcp_server/tests/test_catalog_resolve_edges.py` | test | — | `resolve_typed_entities` tests | exact |
| `mcp_server/tests/test_catalog_evidence_read.py` | test | — | store unit + resolve tests | role-match |
| `mcp_server/tests/test_catalog_service.py` / `test_catalog_capabilities.py` / `test_catalog_store_unit.py` | test | — | same files (extend) | exact |

## Pattern Assignments

### `mcp_server/src/config/schema.py` — `CatalogConfig` (config)

**Analog:** same class (lines 293–352)

**Add fields pattern** (mirror batch limit fields):
```python
# After prepared_chunk_bytes; defaults safe: writes off, reads on
reads_enabled: bool = Field(default=True, description='Enable catalog read/diagnostic tools')
max_page_size: int = Field(default=100, ge=1, le=500)  # hard ceiling enforced in capabilities/service
```

**Write gate unchanged** (lines 302, 340–352): `enabled: bool = False`; namespace required only when `enabled`.

**Do not** couple `reads_enabled` validation to write enable. Optional: allow invalid/missing namespace when reads off; when reads on, identity-bearing paths still fail via service `_read_gate` on bad namespace.

---

### `mcp_server/src/services/catalog_capabilities.py` (pure builder)

**Analog:** `build_catalog_capabilities` lines 42–156

**Replace zero page authority** (line 42):
```python
HARD_MAX_PAGE_SIZE = 500  # was 0 "not configured"
```

**Truthful flags** (lines 112–113, 154):
```python
catalog_writes_enabled=bool(config.enabled),
catalog_reads_enabled=bool(getattr(config, 'reads_enabled', True)),
# limits.configured['max_page_size'] from config.max_page_size
# limits.hard['max_page_size'] = HARD_MAX_PAGE_SIZE
# features.manifest_verification: keep False until last wave after registration + proofs
'manifest_verification': False,  # flip True only after TEST-08/09 green
```

**Never** read `.planning/*` at runtime (D-26).

---

### `mcp_server/src/services/catalog_service.py` — gates + tools

#### Split `_read_gate` (lines 1240–1277) — GATE-01/03/20

**Broken pattern to replace** (lines 1254–1258):
```python
if not self.catalog_config.enabled:
    return (CatalogErrorCode.feature_disabled, 'catalog_upsert.enabled is false')
```

**Target pattern:**
```python
if not getattr(self.catalog_config, 'reads_enabled', True):
    return (CatalogErrorCode.feature_disabled, 'catalog_upsert.reads_enabled is false')
# KEEP: empty group_id, invalid namespace, non-neo4j backend, item_count limits
# DO NOT check catalog_config.enabled here
```

Write paths keep existing `_write`/`_edge_gate`/`enabled` checks.

#### `resolve_typed_entities` (lines 1294–1389) — template for `resolve_typed_edges`

**Core read-only flow:**
1. `_read_gate(client, group_id=..., item_count=...)`
2. On gate fail: per-item `status='error'`, `found=False`, `error_code`, anomalies with code string
3. `namespace = self._namespace(); assert namespace is not None`
4. Store MATCH via `_store.match_*` (no schema ensure, no embedder)
5. Group rows by key; per-ref `_analyze_*` → anomaly tags
6. Log counts only

**Anomaly vocabulary** (`_analyze_resolve_item` ~1391+): `missing`, generic/typed duplicates, wrong_type, uuid_mismatch, missing_embedding.

**Edge twin:** mirror with edge_type+edge_key; anomalies add `endpoint_mismatch`, `endpoint_pair_violation`, `duplicate_edge_key`, `edge_type_mismatch`. Use `match_edges_for_verify` keys path or new `match_edges_for_resolve` sharing keys Cypher RETURN list.

#### `verify_catalog_batch` (lines 1542–1860) — rewire expected authority

**Current anti-pattern** (lines 1783–1786, 1848–1850) — DELETE for batch_id path:
```python
else:
    section.expected = len(rows)  # FORBIDDEN when batch_id present (VERI-01/02/D-11)
    section.found = len(rows)
```

**Target when `request.batch_id` present:**
1. Load committed manifest body (store root + payload chunks + `reassemble_artifact_bytes` + `manifest_sha256` check)
2. Fail closed → `error_code=CatalogErrorCode.manifest_mismatch` (already in catalog_common)
3. Build expected entity/edge refs from body category lists (counts from body `counts` / status metadata)
4. Live `match_entities_for_verify` / `match_edges_for_verify` = observations only
5. Diff: missing members vs extras/duplicates as distinct anomaly kinds
6. Explicit keys still diagnosed when supplied (VERI-06); keys-only (no batch_id) keeps request keys as expected — no fake manifest

#### `get_catalog_ingest_status` (lines 3694–3793) — GATE-05

**Broken missing shape** (3750–3762):
```python
status='failed', error_code=CatalogErrorCode.validation_error, error_summary='batch status not found'
```

**Target:** extend `CatalogIngestStatusResponse` with `found: bool = True` (or default False carefully). Missing:
```python
return CatalogIngestStatusResponse(
    group_id=group_id,
    batch_id=batch_id,
    batch_uuid=batch_uuid,
    found=False,
    status='failed',  # or keep status only when found; do not use validation_error for absence
    error_code=None,
    error_summary='batch status not found',
)
```
Gate failures still use structured error_code; distinguish absence from validation.

#### New service methods (smallest extraction)

| Method | Pattern source |
|--------|----------------|
| `get_catalog_batch_manifest` | resolve gate + status read + page slice |
| `resolve_typed_edges` | `resolve_typed_entities` |
| `get_catalog_evidence` | resolve gate + store match + offset/limit |
| `_load_committed_manifest_body` | research snippet; store recovery + reassemble |

**Pagination helper (pure):**
```python
def page_members(items: list[dict], *, offset: int, limit: int) -> tuple[list[dict], int]:
    total = len(items)
    if offset < 0 or limit < 1:
        raise ValueError('invalid pagination')
    hard = HARD_MAX_PAGE_SIZE  # from capabilities/common
    if limit > hard:
        raise ValueError('page size exceeds hard max')  # or CatalogErrorCode.validation_error
    return items[offset : offset + limit], total
```
Order = durable body category order only (`catalog_manifest` sort keys) — never re-sort by live graph.

---

### `mcp_server/src/services/catalog_store.py` (read loaders)

**Read primitives** (lines 696–710, 772+):
```python
# ALWAYS for Phase 4 reads:
await self._read_one(executor, cypher, params, tx=tx)
await self._read_many(executor, cypher, params, tx=tx)
# NEVER: ensure_evidence_manifest_schema, write_*, CREATE/SET on read tools
```

**Manifest root** — reuse `read_manifest_root_for_recovery` (3822–3841) + `build_read_manifest_root_by_batch_cypher` (3355–3371). Extend RETURN if public needs entity_count/edge_count/source_count/evidence_link_count/version fields (already on CREATE root 3300–3329).

**Chunk payload load** — do **not** use metadata-only `build_list_manifest_chunks_cypher` (3288–3298). **Copy shape from** `build_load_prepared_plan_chunks_cypher` (2175–2188):
```python
def build_load_manifest_chunks_cypher(self) -> str:
    return """
        MATCH (c:CatalogBatchManifestChunk {manifest_uuid: $manifest_uuid, group_id: $group_id})
        RETURN c.uuid AS uuid,
               c.group_id AS group_id,
               c.manifest_uuid AS manifest_uuid,
               c.chunk_index AS chunk_index,
               c.chunk_count AS chunk_count,
               c.byte_offset AS byte_offset,
               c.byte_length AS byte_length,
               c.chunk_sha256 AS chunk_sha256,
               c.payload_b64 AS payload_b64
        ORDER BY c.chunk_index ASC
        """
```

**Edge resolve MATCH** — reuse keys Cypher (926–946); optionally add `e.content_sha256 AS content_sha256` if writer stores it.

**Evidence MATCH (new)** — fixed labels only:
```cypher
MATCH (l:CatalogEvidenceLink {group_id: $group_id})
WHERE l.target_uuid = $target_uuid  -- or link_key / entity graph_key fields as stored on write
RETURN l.uuid AS uuid, l.link_key AS link_key, ...
ORDER BY l.uuid  -- stable; page in service
```
Always `group_id` param; never client labels.

---

### Manifest reassembly (reuse, no rewrite)

**Sources:**
- `catalog_prepared_artifact.reassemble_artifact_bytes` (line 123+)
- `catalog_manifest.manifest_sha256` / `serialize_manifest_body`
- Category order authority: `_project_category` + `_MEMBERSHIP_CATEGORIES` (catalog_manifest.py 93–170)

```python
root = await store.read_manifest_root_for_recovery(driver, group_id=..., batch_id=...)
if not root:
    # manifest_mismatch or found=false depending on caller
chunks = await store.load_manifest_chunks_with_payload(...)
if len(chunks) != int(root['chunk_count']):
    raise ManifestMismatch(...)
raw = reassemble_artifact_bytes(
    chunks,
    expected_sha256=str(root['manifest_sha256']),
    expected_length=int(root['payload_bytes']),
)
if manifest_sha256(raw) != str(root['manifest_sha256']):
    raise ManifestMismatch(...)
body = json.loads(raw.decode('utf-8'))
```

---

### `mcp_server/src/models/catalog_entities.py` / `catalog_responses.py`

**Request analog:** `ResolveTypedEntitiesRequest` (186–214) — `CatalogStrictModel`, `identity_schema_version: Literal['catalog-v2']`, `system_key`, `group_id` + `_validate_group_id`, allowlisted types, nested graph_key validators.

New requests (discretionary field names):
- `GetCatalogBatchManifestRequest` — group_id, batch_id, offset, limit, optional detail flag
- `ResolveTypedEdgesRequest` — system_key, group_id, list of edge_type+edge_key refs
- `GetCatalogEvidenceRequest` — group_id, target identity, offset/limit, optional excerpts

**Response analogs:**
- `ResolveEntityResult` / `ResolveTypedEntitiesResponse` → edge twin with source/target uuid+graph_key, has_fact_embedding
- `VerifyCatalogBatchResponse` — additive fields only (`extras`, `manifest_sha256`, evidence section); keep existing sections
- `CatalogIngestStatusResponse` — add `found: bool`

**Error code:** `CatalogErrorCode.manifest_mismatch` already registered — use it; do not invent parallel strings.

**IDEN-08:** every entity-identifying field on new responses is full system-scoped `graph_key` (same string stored on write/manifest), never name-only.

---

### `mcp_server/src/graphiti_mcp_server.py` — MCP registration

**CATALOG_TOOL_NAMES** (217–231) — add exactly three:
```python
'get_catalog_batch_manifest',
'resolve_typed_edges',
'get_catalog_evidence',
```
11 → 14 catalog names; total tools 25 → 28 (14 catalog + 14 legacy).

**Thin tool pattern** (1340–1385):
```python
@mcp.tool()
async def resolve_typed_entities(request: ResolveTypedEntitiesRequest) -> ResolveTypedEntitiesResponse | ErrorResponse:
    # graphiti_service None → ErrorResponse
    # lazy CatalogService(catalog_config=graphiti_service.config.catalog_upsert)
    # try: client = await graphiti_service.get_client(); return await catalog_service....
    # except: logger.error('... reason=%s', type(e).__name__); return ErrorResponse(...)
    # NEVER log payloads/tokens/source text
```

Copy for three new tools. Keep `CatalogSafeFastMCP` membership via expanded `CATALOG_TOOL_NAMES`.

**Capabilities tool** stays ungated (GATE-02).

---

### Tests

| File | Analog / pattern |
|------|------------------|
| `test_catalog_gates.py` | Service spies: zero `ensure_*_schema`, zero embedder, group_id isolation; writes disabled + reads on |
| `test_catalog_manifest_read.py` | Pure reassembly fail-closed; stable offset/limit; shared `unchanged` still member; no synthesis from batch_id rows |
| `test_catalog_verify_manifest.py` | expected ≠ len(live); missing vs extra; `manifest_mismatch`; keys-only path still works |
| `test_catalog_resolve_edges.py` | Mirror entity resolve tests; endpoint anomalies; no repair |
| `test_catalog_evidence_read.py` | Pagination bounds; compact default; group isolation |
| `test_catalog_service.py` lines 4455–4472 | Update counts: catalog 11→14, total 25→28; freeze LEGACY 14 |
| `test_catalog_capabilities.py` | reads/writes separate; max_page_size > 0; `manifest_verification` flip last |
| `test_catalog_store_unit.py` | New Cypher contains `$group_id`, no string-interpolated labels; payload RETURN present |

**Registration assertion pattern:**
```python
assert len(CATALOG_TOOL_NAMES) == 14  # was 11
assert len(LEGACY_TOOL_NAMES) == 14
assert len(names) == 28  # was 25
assert names == (CATALOG_TOOL_NAMES | LEGACY_TOOL_NAMES)
```

## Shared Patterns

### Thin FastMCP + safe error
**Source:** `graphiti_mcp_server.py` 1340–1385, `CatalogSafeFastMCP` 234–255  
**Apply to:** all 3 new tools + keep existing  
Log IDs/counts/`type(e).__name__` only.

### Read gate (post-split)
**Source:** `catalog_service._read_gate` after fix  
**Apply to:** status, resolve entities/edges, verify, manifest, evidence  
Requires: `reads_enabled`, non-empty `group_id`, valid namespace, neo4j provider.  
**Not** `enabled` (write).

### Write gate (unchanged)
**Source:** existing write gates on upsert/prepare/commit/discard  
Default `enabled=False`. Writes return `feature_disabled` without side effects when off.

### Store read-only Cypher
**Source:** `_read_one` / `_read_many` + fixed MATCH strings  
**Apply to:** all Phase 4 store methods  
Ban: `ensure_evidence_manifest_schema`, CREATE/SET/MERGE on diagnostic paths.

### Manifest expected authority
**Source:** Phase 3B body categories + reassembly  
**Apply to:** batch verify + public manifest read  
Live MATCH never sets `section.expected`.

### Structured errors
**Source:** `CatalogErrorCode` incl. `manifest_mismatch`, `feature_disabled`, `backend_unavailable`, `invalid_uuid_namespace`  
**Apply to:** all gated responses.

### Group isolation
**Source:** every store WHERE `group_id = $group_id`  
**Tests only:** `oracle-catalog-tool-test`  
**Never:** `oracle-catalog-v2`, rewrite historical `a67789a`.

### Capabilities purity
**Source:** `build_catalog_capabilities` — no DB write/schema  
**Apply to:** page size + flag updates; flip `manifest_verification` only after proofs.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | All Phase 4 work extends existing catalog modules; no greenfield packages |

**Gaps are behavioral, not structural:** page size 0, write-coupled `_read_gate`, batch expected=live count, missing `found`, missing public tools, chunk list without `payload_b64`.

## Anti-Patterns (do not copy)

| Location | Issue |
|----------|-------|
| `catalog_service.py:1254-1258` | Read gated by write `enabled` |
| `catalog_service.py:1783-1786, 1848-1850` | `expected = len(rows)` for batch-only |
| `catalog_service.py:3750-3762` | Missing status as `validation_error` |
| `catalog_capabilities.py:42,141,154` | `HARD_MAX_PAGE_SIZE=0`; hardcoded `catalog_reads_enabled=True`; `manifest_verification=False` until end only |
| `catalog_store.py:3288-3298` | Chunk list without payload (insufficient for reassembly) |
| Calling `ensure_evidence_manifest_schema` from reads | GATE-04 violation |

## Implementation Order (for planner)

1. Config `reads_enabled` + `max_page_size`; split `_read_gate`; GATE-05 `found`; capabilities truth (except verification flip)
2. Store: load chunks with payload; evidence/edge read Cypher via `_read_*`
3. Service: manifest load+page; rewire verify expected; resolve_typed_edges; get_catalog_evidence
4. Models + MCP registration; CATALOG_TOOL_NAMES 14; tests 28 tools
5. Flip `features.manifest_verification=True` only after focused suite green

## Metadata

**Analog search scope:** `mcp_server/src/{config,models,services,graphiti_mcp_server.py}`, `mcp_server/tests/test_catalog_*.py`  
**Files scanned:** ~20 primary symbols with line-level excerpts  
**Pattern extraction date:** 2026-07-19  
**Product code mutated:** no (PATTERNS.md only)  
**Phase 3B product HEAD retained:** `1f9a7d75551fe5d1c0260f831102d2a8c5b83e18`  
**Historical live audit (immutable):** `a67789a04ca0cc2f2a56d7498c65be3460215f77`
