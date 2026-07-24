# Phase 1: Strict Contracts and Catalog-v2 Identity - Pattern Map

**Mapped:** 2026-07-18
**Files analyzed:** 15 (1 new product module + 7 model/service mods + 4 test suites + gate report + optional MCP touch)
**Analogs found:** 14 / 15

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp_server/src/models/catalog_common.py` | model / config hub | transform (constants + error registry + strict base) | same file (v1.0 hub) | exact |
| `mcp_server/src/models/catalog_graph_key.py` | utility / registry | transform (pure grammar fullmatch) | `catalog_common.ENTITY_TYPE_PREFIXES` + `catalog_identity.py` purity | partial (new module) |
| `mcp_server/src/models/catalog_entities.py` | model | request-response (validate) | same file prefix validators | exact |
| `mcp_server/src/models/catalog_edges.py` | model | request-response | same file + `Literal[True]` in `catalog_batch.py` | exact |
| `mcp_server/src/models/catalog_provenance.py` | model | request-response | same file byte-preserve validators | exact |
| `mcp_server/src/models/catalog_batch.py` | model | request-response | same file (`atomic: Literal[True]`) | exact |
| `mcp_server/src/models/catalog_responses.py` | model | request-response | `CatalogItemResult.error_code` + `ErrorResponse` | role-match |
| `mcp_server/src/services/catalog_identity.py` | service / pure util | transform (UUIDv5 + hash) | same file | exact |
| `mcp_server/src/services/catalog_service.py` | service | CRUD (call-site only) | same file identity call sites | exact (minimal touch) |
| `mcp_server/src/graphiti_mcp_server.py` | controller / MCP | request-response | catalog tools ~1239–1434 | role-match |
| `mcp_server/tests/test_catalog_models.py` | test | batch (table-driven) | same file `_entity_kwargs` + parametrize | exact |
| `mcp_server/tests/test_catalog_identity.py` | test | transform goldens | same file uuid5 goldens | exact |
| `mcp_server/tests/test_catalog_service.py` | test | request-response spies | same file `_entity`/`_request`/`AsyncMock` | exact |
| `mcp_server/tests/test_catalog_store_unit.py` | test | fixture keys only | same suite | role-match |
| `01-PHASE1-GATE.md` | report / gate | transform (ledger) | `00-PHASE0-GATE.md` | exact |

**Out of Phase 1 (do not touch product paths):** `catalog_store.py` write orchestration, endpoint-pair map, evidence/prepare/manifest, canary scripts execution, dirty deploy/catalog dumps, `oracle-catalog-v2`.

**Note:** `catalog_store.py` imports `ENTITY_TYPE_PREFIXES` for label map (`_ENTITY_LABELS`). Expanding allowlist to 18 types auto-widens labels if names match `_SAFE_LABEL` — no new store path required; avoid unrelated store edits.

## Pattern Assignments

### `mcp_server/src/models/catalog_common.py` (model hub, transform)

**Analog:** self — already owns allowlists, limits, `CatalogErrorCode`, `validate_nested_json`.

**Constants / allowlist pattern** (lines 13–100, 138–139):
```python
DEFAULT_MAX_ENTITIES_PER_BATCH = 500
# ...
ENTITY_TYPE_PREFIXES: dict[str, str] = {
    'Database': 'DATABASE::',
    # ... 15 types today
}
CATALOG_ENTITY_TYPES: frozenset[str] = frozenset(ENTITY_TYPE_PREFIXES.keys())
SHA256_HEX_RE = r'^[0-9a-f]{64}$'
```

**Phase 1 extend (copy shape, do not remove keys):**
```python
IDENTITY_SCHEMA_VERSION = 'catalog-v2'
SYSTEM_KEYS: frozenset[str] = frozenset({'FE', 'BO', 'COMMON'})
# ENTITY_TYPE_PREFIXES += System/SYSTEM::, DatabaseLink/DBLINK::, SourceArtifact/SOURCE::
```

**Error registry pattern** (lines 142–162) — append only:
```python
class CatalogErrorCode(StrEnum):
    validation_error = 'validation_error'
    # ... existing 17 ...
    backend_unavailable = 'backend_unavailable'
    # Phase 1 CONT-08 (add, never remove):
    # unsupported_identity_schema, invalid_system_key,
    # edge_endpoint_pair_not_allowed, prepared_plan_not_found,
    # prepared_plan_expired, prepared_plan_conflict,
    # prepared_plan_already_consumed, manifest_mismatch,
    # provenance_link_conflict
```

**Strict base (new in this file — no live `ConfigDict` under catalog models):**
```python
from pydantic import BaseModel, ConfigDict

class CatalogStrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
```

**Safe structured error converter (prefer here over per-tool):**
```python
def catalog_validation_error_to_structured(
    exc: ValidationError, *, correlation_id: str
) -> dict[str, Any]:
    # code=validation_error or mapped unsupported_identity_schema/invalid_system_key
    # message bounded <=512, field_path from exc.errors()[0]['loc'], retryable=False
    # never str(exc) stack / payload / source text
    ...
```

**Blast radius:** every `from models.catalog_common import ...` in models, identity, service, store labels, config, tests.

---

### `mcp_server/src/models/catalog_graph_key.py` (utility, transform) — NEW

**Analog A (prefix authority):** `catalog_common.ENTITY_TYPE_PREFIXES`
**Analog B (pure no-I/O module):** `services/catalog_identity.py` header + import ban test

**Module purity invariant** (copy from identity):
```python
"""Pure graph-key grammar registry. No network, Neo4j, embedder, LLM, queue."""
```

**Replace prefix-only checks** currently:
```python
# catalog_entities.py:109-116 (and edges/provenance twins)
prefix = ENTITY_TYPE_PREFIXES[self.entity_type]
if not self.graph_key.startswith(prefix):
    raise ValueError(f'graph_key_prefix_mismatch: ...')
```

**Recommended API:**
```python
import re
from models.catalog_common import ENTITY_TYPE_PREFIXES, IDENTITY_SCHEMA_VERSION

_ORACLE_IDENT = r'[A-Z][A-Z0-9_$#]*'
# compiled fullmatch per entity_type; Procedure/Function require #<OVERLOAD>

def validate_entity_graph_key(
    *, entity_type: str, graph_key: str, system_key: str
) -> None:
    """Fullmatch registry; require PREFIX::{system_key}::...; no v1 rewrite."""
    ...
```

**Canonical examples (locked):**
```text
TABLE::FE::<DATABASE>.<SCHEMA>.<TABLE>
PROCEDURE::BO::<DATABASE>.<SCHEMA>.<PACKAGE>.<PROC>#<OVERLOAD>
FUNCTION::FE::<DATABASE>.<SCHEMA>.<FN>#<OVERLOAD>   # standalone package optional
SYSTEM::FE::<NAME>
DBLINK::FE::<DATABASE>.<LINK>
SOURCE::FE::<ARTIFACT_KEY>
```

**No analog for full grammar table** — planner uses RESEARCH grammar matrix; tests pin 18 positive + v1 rejection negatives.

---

### `mcp_server/src/models/catalog_entities.py` (model, request-response)

**Analog:** self.

**Imports pattern** (lines 1–24) — switch base + pull grammar:
```python
from pydantic import Field, field_validator, model_validator
from models.catalog_common import (
    CatalogStrictModel,
    ENTITY_TYPE_PREFIXES,
    # ...
)
from models.catalog_graph_key import validate_entity_graph_key
```

**Item model** — inherit strict; keep field validators; replace `_graph_key_prefix`:
```python
class CatalogEntityItem(CatalogStrictModel):
    # existing fields...
    @model_validator(mode='after')
    def _graph_key_grammar(self) -> Self:
        # system_key comes from parent request shell (see Shared Patterns)
        ...
```

**Request shell** — add required version/system; tighten atomic:
```python
from typing import Literal

class UpsertTypedEntitiesRequest(CatalogStrictModel):
    identity_schema_version: Literal['catalog-v2']
    system_key: Literal['FE', 'BO', 'COMMON']
    group_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    entities: list[CatalogEntityItem] = Field(..., min_length=1, max_length=HARD_MAX_ENTITIES_PER_BATCH)
    dry_run: bool = False
    atomic: Literal[True] = True
```

**Same shell fields** on `ResolveTypedEntitiesRequest`, `VerifyCatalogBatchRequest` when graph keys present (CONTEXT/RESEARCH resolved).

**group_id validator** (copy lines 153–159) — keep; isolation still `oracle-catalog-tool-test` in tests only.

**Nested refs:** `ResolveEntityRef`, `VerifyEntityRef` → `CatalogStrictModel` + grammar fullmatch (not startswith).

---

### `mcp_server/src/models/catalog_edges.py` (model, request-response)

**Analog:** self + batch Literal pattern.

**Live gap** (lines 128–129):
```python
atomic: bool = True
strict_endpoints: bool = True  # accepts false today — CONT-05
```

**Target:**
```python
class UpsertTypedEdgesRequest(CatalogStrictModel):
    identity_schema_version: Literal['catalog-v2']
    system_key: Literal['FE', 'BO', 'COMMON']
    # ...
    atomic: Literal[True] = True
    strict_endpoints: Literal[True] = True
```

**Endpoint grammar** — replace startswith block (lines 106–117) with `validate_entity_graph_key` for source/target + types. `edge_key` stays bounded non-empty string (Phase 2 owns topology).

**EnforcedBy evidence rule** (lines 102–105) — keep.

---

### `mcp_server/src/models/catalog_provenance.py` (model, request-response)

**Analog:** self — CONT-04 byte preservation.

**Preserve-bytes pattern** (lines 41–46) — **return original `v`**, emptiness via `.strip()` only:
```python
@field_validator('source_key', 'reference_time')
@classmethod
def _non_empty(cls, v: str, info) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f'{info.field_name} must be a non-empty string')
    return v  # NOT v.strip()
```

**Strict base** on `CatalogSourceItem`, targets, `UpsertProvenanceRequest`.
**Shell:** `identity_schema_version`, `system_key`, `atomic: Literal[True]`.
**Entity target grammar:** replace prefix startswith (lines 84–91).

---

### `mcp_server/src/models/catalog_batch.py` (model, request-response)

**Analog:** self — already has `atomic: Literal[True]` (lines 67, 86–91).

**Copy Literal + validator:**
```python
atomic: Literal[True] = True

@field_validator('atomic')
@classmethod
def _atomic_must_be_true(cls, v: bool) -> bool:
    if v is not True:
        raise ValueError('atomic must be true for upsert_catalog_batch')
    return v
```

**Add** shell `identity_schema_version` + `system_key`; nest `NestedProvenancePayload(CatalogStrictModel)`; SHA validators (lines 77–84) unchanged.

---

### `mcp_server/src/models/catalog_responses.py` (model, response)

**Analog:** `CatalogItemResult` (lines 14–27) + `models/response_types.ErrorResponse`.

**Existing per-item errors:**
```python
error_code: CatalogErrorCode | None = None
error_message: str | None = None
```

**Optional SAFE-08 DTO (request-side strict; response may stay non-strict):**
```python
class CatalogStructuredError(BaseModel):  # or CatalogStrictModel if reused as payload
    code: CatalogErrorCode
    message: str = Field(..., max_length=512)
    field_path: str | None = None
    retryable: bool = False
    correlation_id: str
```

Do not break existing write/resolve/verify response field names used by service builders.

---

### `mcp_server/src/services/catalog_identity.py` (pure util, transform)

**Analog:** self.

**Current material** (lines 17–43):
```python
def catalog_entity_uuid(namespace, group_id, entity_type, graph_key) -> str:
    return str(uuid.uuid5(namespace, f'{group_id}|{entity_type}|{graph_key}'))
```

**Phase 1 material (signatures unchanged — contain blast radius):**
```python
from models.catalog_common import IDENTITY_SCHEMA_VERSION  # 'catalog-v2'

def catalog_entity_uuid(namespace, group_id, entity_type, graph_key) -> str:
    return str(
        uuid.uuid5(
            namespace,
            f'{group_id}|{IDENTITY_SCHEMA_VERSION}|{entity_type}|{graph_key}',
        )
    )
# edge:  group_id|catalog-v2|edge_type|edge_key
# source: group_id|catalog-v2|Source|source_key
# batch:  group_id|catalog-v2|Batch|batch_id
# mentions: group_id|catalog-v2|Mentions|source_uuid|entity_uuid
```

**Keep pure:** no neo4j/embedder/llm/queue imports (`test_identity_module_has_no_io_imports`).
**Keep SAFE-05:** no caller-uuid params (`test_identity_functions_do_not_accept_caller_uuid_authority`).
**Hash recipe:** do **not** change `canonical_sha256` algorithm (Phase 2 freezes coverage).

**Call-site blast (signatures stable → material-only break):**
| Area | Sites |
|------|-------|
| `catalog_service.py` | imports 43–47; entity prep ~331; resolve/verify ~1166, 1462, 1466, 1544+ |
| `test_catalog_identity.py` | all goldens |
| `test_catalog_service.py` | UUID assertions via helpers |
| `test_catalog_store_unit.py` | if pins UUID |
| `test_catalog_neo4j_int.py` | skip in Phase 1 gate; goldens if run later |
| canary builders | offline v1 — **do not execute / do not repair baseline** |

---

### `mcp_server/src/services/catalog_service.py` (service, CRUD) — minimal

**Analog:** self.

**Identity call pattern** (~331–333):
```python
ent_uuid = catalog_entity_uuid(
    namespace, request.group_id, item.entity_type, item.graph_key
)
```

**Phase 1 rule:** keep orchestration stages (identity → hash → coalesce → embed → schema → tx). No new store/control-plane path. Prefer **no signature change** so service only inherits new UUID material. If models add required fields, constructors in tests update — service methods already take typed requests.

**Error item pattern** (~321–328):
```python
early_errors[idx] = CatalogItemResult(
    index=idx,
    status='error',
    graph_key=item.graph_key,
    entity_type=item.entity_type,
    error_code=code,
    error_message=msg,
)
```

Validation precedence: model layer fails before service entry (CONT-07).

---

### `mcp_server/src/graphiti_mcp_server.py` (MCP controller)

**Analog:** catalog tools lines 1239–1434.

**Thin wrapper pattern:**
```python
@mcp.tool()
async def upsert_typed_entities(
    request: UpsertTypedEntitiesRequest,
) -> CatalogWriteResponse | ErrorResponse:
    if graphiti_service is None:
        return ErrorResponse(error='Graphiti service not initialized')
    if catalog_service is None:
        catalog_service = CatalogService(...)
    try:
        client = await graphiti_service.get_client()
        return await catalog_service.upsert_typed_entities(client=client, request=request)
    except Exception as e:
        logger.error(
            'upsert_typed_entities failed batch_id=%s count=%s reason=%s',
            getattr(request, 'batch_id', None),
            len(getattr(request, 'entities', []) or []),
            type(e).__name__,  # type name only — never payload
        )
        return ErrorResponse(error='catalog upsert_typed_entities failed')
```

**Tool names frozen (7):** upsert_typed_entities, resolve_typed_entities, verify_catalog_batch, upsert_typed_edges, upsert_provenance, get_catalog_ingest_status, upsert_catalog_batch.

**FastMCP** currently type-binds `request: UpsertTypedEntitiesRequest` — invalid payloads may fail before body. Phase 1: if framework already raises ValidationError pre-handler, structured conversion may live in a shared helper used where dicts are validated; unit tests can call `Model.model_validate` directly for CONT-07 without live MCP. Prefer **one** `catalog_validation_error_to_structured` in models; avoid seven duplicated wrappers.

**Logging:** batch_id + counts + `type(e).__name__` only (SAFE logging).

---

### `mcp_server/tests/test_catalog_models.py` (test, table-driven)

**Analog:** self.

**Fixture helpers** (lines 61–93) — migrate to v2:
```python
def _entity_kwargs(**overrides: Any) -> dict[str, Any]:
    base = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',  # was TABLE::HR.EMPLOYEES
        'name_raw': 'EMPLOYEES',
        'name_canonical': 'employees',
        'database_qualified_name': 'ORCL.HR.EMPLOYEES',
        'summary': 'Employee master table',
    }
    base.update(overrides)
    return base

def _request_shell(**overrides) -> dict[str, Any]:
    base = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': 'oracle-catalog-tool-test',
        'batch_id': 'batch-1',
    }
    base.update(overrides)
    return base
```

**Parametrize pattern** (lines 132–142 style):
```python
@pytest.mark.parametrize(('field', 'value'), [...])
def test_...(field, value):
    with pytest.raises(ValidationError):
        Model.model_validate({...})
```

**Wave 0 matrices to add:** recursive extra forbid; misspelled optionals; `strict_endpoints=false`; `atomic=false` all write reqs; trailing-space preserve; 18-type grammar pos/neg; system_key mismatch; catalog-v1 key reject; error code enum membership.

---

### `mcp_server/tests/test_catalog_identity.py` (test, goldens)

**Analog:** self.

**Golden rewrite pattern** (lines 30–33 → v2):
```python
def test_catalog_entity_uuid_matches_uuid5():
    key = 'TABLE::FE::ORCL.HR.EMPLOYEES'
    got = catalog_entity_uuid(FIXED_NS, GROUP, 'Table', key)
    expected = str(uuid.uuid5(FIXED_NS, f'{GROUP}|catalog-v2|Table|{key}'))
    assert got == expected
```

**Add:** FE vs BO same Oracle body → different UUID; overload `#a` vs `#b` non-collapse; v1 material string must not equal v2; caller-uuid authority test unchanged; pure-module import ban unchanged.

**GROUP** stays `oracle-catalog-tool-test` (line 27).

---

### `mcp_server/tests/test_catalog_service.py` (test, spies)

**Analog:** self.

**Fixture pattern** (lines 79–108) — add shell fields + v2 keys:
```python
def _entity(**overrides) -> CatalogEntityItem:
    data = {
        'entity_type': 'Table',
        'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
        # ...
    }
    data.update(overrides)
    return CatalogEntityItem.model_validate(data)

def _request(...):
    return UpsertTypedEntitiesRequest(
        identity_schema_version='catalog-v2',
        system_key='FE',
        group_id=GROUP,
        ...
    )
```

**Mock client pattern** (lines 13, 168+): `AsyncMock` embedder; `MagicMock` tx; spy `_store` / `_ensure_schema`.

**CONT-07 no-side-effect** (new; ValidationError before service):
```python
with pytest.raises(ValidationError):
    UpsertTypedEntitiesRequest.model_validate({..., 'identity_schema_version': 'catalog-v1'})
# service methods / store / embedder never called when invalid at model boundary
```

**Tool name freeze set** (lines 47–55) — keep assertions; names must remain 7.

---

### `01-PHASE1-GATE.md` (report)

**Analog:** `00-PHASE0-GATE.md`.

**Structure to copy:**
1. Artifact checklist table
2. Safety invariants (`canary_executed=false`, `oracle_catalog_v2_queried=false`, no dirty-file commit, no remote)
3. Requirement coverage map (CONT-*, IDEN-*, SAFE-05/08, TEST-01/03)
4. Check summary with truthful pass|fail|skip (never reclassify canary baseline fails as Phase 1 pass)
5. `ready_for_phase_2=true` only when focused unit + ruff + pyright green and fences held
6. Explicit non-goals

**Focused commands** (from VALIDATION/RESEARCH):
```bash
cd mcp_server
uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py \
  tests/test_catalog_service.py tests/test_catalog_store_unit.py -q --tb=line
uv run ruff check src/models/catalog_*.py src/services/catalog_identity.py \
  tests/test_catalog_models.py tests/test_catalog_identity.py
uv run pyright src/models src/services/catalog_identity.py
```

## Shared Patterns

### Strict request base
**Source:** new `CatalogStrictModel` in `catalog_common.py` (no live catalog `ConfigDict`)
**Apply to:** all request + nested request models (not necessarily server-built responses)
```python
class CatalogStrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
```

### Literal immutable flags + version/system
**Source:** `catalog_batch.py` atomic Literal; extend to all write shells
```python
identity_schema_version: Literal['catalog-v2']
system_key: Literal['FE', 'BO', 'COMMON']
atomic: Literal[True] = True
strict_endpoints: Literal[True] = True  # edges only
```
Shell-level `system_key` only (Phase 1); nested keys must match shell scope.

### Graph-key validation
**Source today:** startswith prefix in entities/edges/provenance
**Target:** `catalog_graph_key.validate_entity_graph_key` fullmatch + system segment
**Apply to:** entity items, resolve/verify refs, edge endpoints, provenance entity targets

### Deterministic UUIDv5
**Source:** `catalog_identity.py`
**Apply to:** all five helpers with `|catalog-v2|` segment; keep signatures

### Validation before side effects
**Source intent:** MCP thin tools + Pydantic; service assumes valid model
**Apply to:** never open embed/schema/tx/status on ValidationError; unit spies prove it

### Safe errors + logging
**Source:** `CatalogErrorCode` + MCP `logger.error(..., type(e).__name__)` + `CatalogItemResult`
**Apply to:** extend codes; structured validation converter; no payload/source/credentials

### Isolation
**Source:** Phase 0 policies + test GROUP constant
**Apply to:** tests only `oracle-catalog-tool-test`; ban canary run; ban `oracle-catalog-v2`; dirty files untouched

## Dependency / Call-Site Blast Radius

```text
catalog_common (strict base, SYSTEM_KEYS, IDENTITY_SCHEMA_VERSION, +3 prefixes, +9 codes)
    ├── catalog_graph_key (new; reads prefixes/constants)
    ├── catalog_entities / edges / provenance / batch (inherit + grammar hooks)
    ├── catalog_responses (optional structured error DTO)
    ├── catalog_identity (reads IDENTITY_SCHEMA_VERSION)
    ├── catalog_service (UUID material via helpers; request field access)
    ├── catalog_store (label map from ENTITY_TYPE_PREFIXES — passive widen)
    ├── config/schema CatalogConfig (unchanged unless imports enums)
    ├── graphiti_mcp_server (tool types auto-pick new models)
    └── tests: models, identity, service, store_unit (+ int offline)
```

**Containment:** keep identity helper **signatures**; update goldens/fixtures; no dual-version compatibility layer; no canary repair.

## TDD-Friendly Feature Slices (planner waves)

| Slice | RED tests first | GREEN product touch | Fence |
|-------|-----------------|---------------------|-------|
| **S1 Strict + flags** | extra/misspell/atomic/strict_endpoints matrices | `CatalogStrictModel`; Literal flags; inherit all request/nested | no store |
| **S2 Grammar + system** | 18-type pos/neg; FE/BO; overload; v1 reject; system_key | `catalog_graph_key.py`; replace startswith; shell fields | no endpoint map |
| **S3 UUID versioning** | material goldens; FE≠BO UUID; no caller uuid | `catalog_identity` material only | no hash recipe change |
| **S4 Errors + precedence** | structured fields; spy no embed/store | error codes + converter; fixture shells | no MCP redesign |
| **S5 Gate** | focused suite + ruff + pyright | `01-PHASE1-GATE.md` ledger | canary still fail baseline OK |

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `catalog_graph_key.py` (full registry) | utility | transform | Prefix map only today; new fullmatch table — use RESEARCH grammar + identity purity pattern |

## Phase 1 Fences (planner must preserve)

- No new store/control-plane write path
- No endpoint-pair map / evidence contract / request-hash freeze / prepare / manifest
- No canary execution; no `oracle-catalog-v2` query/mutate
- No automatic catalog-v1 migration/rewrite
- Dirty exclude: `.planning/config.json`, docker/k8s yaml, `.codegraph/`, bulk `catalog/*`, `sample_catalog.json`
- Phase 0 canary-script fails remain recorded noise — not Phase 1 repair target
- Tool names: 14 legacy + 7 catalog frozen

## Metadata

**Analog search scope:** `mcp_server/src/models/catalog_*.py`, `mcp_server/src/services/catalog_{identity,service,store}.py`, `mcp_server/src/graphiti_mcp_server.py`, `mcp_server/tests/test_catalog_*.py`, Phase 0 gate/policies, `.claude/CLAUDE.md`
**Files scanned:** ~20 product/test + Phase 0/1 planning
**Pattern extraction date:** 2026-07-18
