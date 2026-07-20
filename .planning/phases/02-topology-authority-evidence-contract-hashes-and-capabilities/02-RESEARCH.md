# Phase 2: Topology Authority, Evidence Contract, Hashes, and Capabilities - Research

**Researched:** 2026-07-18
**Domain:** Server-owned catalog edge topology, explicit evidence-link contract, versioned request hashing, mutation-free capabilities (mcp_server catalog surface)
**Confidence:** HIGH

## Summary

Phase 2 freezes four pure contracts that Phase 3A prepare/hashing and Phase 3B evidence persistence must not reinvent: (1) one immutable endpoint-pair registry for all 16 approved edge types, (2) explicit one-source/one-target `CatalogEvidenceLink` replacing Cartesian multi-source provenance, (3) version-tagged authoritative `request_sha256` covering `identity_schema_version`, `catalog_sha256`, and every canonical domain field, (4) read-only `get_catalog_capabilities` that works when writes are disabled.

Live code already has the **hooks** but not the **authorities**:

| Surface | Live state (verified) | Phase 2 gap |
|---------|----------------------|-------------|
| Edge types | `CATALOG_EDGE_TYPES` frozenset (16) in `catalog_common.py` | No `(source_type, target_type)` map |
| Endpoint pair code | `edge_endpoint_pair_not_allowed` in `CatalogErrorCode` | Never raised; no checker |
| FK fixtures | Table→Table `ForeignKeyTo` in service/int fixtures | Column→Column not exercised; Table→Table is compatibility evidence |
| Provenance | `sources × (entity_targets + edge_targets)` Cartesian | Must reject; introduce explicit links |
| Batch hash | `_batch_canonical_payload` omits identity version + `catalog_sha256`; no collection sort; no version tag | HASH-01..07 incomplete |
| Batch response | Has `batch_uuid`; no `identity_schema_version` / `request_sha256` / `catalog_sha256` echo | HASH-05 |
| Capabilities | Absent; `get_status` TypedDict `status`+`message` only | CAPA-01..09 |
| Evidence UUID helper | `catalog_evidence_link_uuid` pure stub exists | Needs link_key material + content hash |

**Hard gate (ROADMAP):** No store/control-plane write implementation until Phase 1–2 unit gates pass. Phase 1 gate is green (`ready_for_phase_2=true`). Phase 2 must stay unit/service-spy only — no prepared-plan persistence, no evidence store path, no canary, no `oracle-catalog-v2`.

**Primary recommendation:** Add four thin pure modules (`catalog_topology.py`, evidence models in `catalog_provenance.py` / new `catalog_evidence.py`, hash versioning in `catalog_identity.py`, `catalog_capabilities.py`) and wire shared preflight into edge + batch service paths before any DB/embed/schema/tx/status side effect. Replace incomplete `batch_request_sha256` in place (one authority, not a parallel path). Register `get_catalog_capabilities` outside write gates. Exhaustive table-driven unit gates only.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Endpoint Topology Authority
- Define one immutable server registry containing every allowed `(source_entity_type, target_entity_type)` pair for all 16 approved edge types; all request models, standalone/batch preflight, future prepare/commit, verification, resolution, capabilities, and tests consume it.
- Validate edge type and endpoint pair from request data before endpoint DB reads when possible, always before embeddings, schema initialization, transactions, status writes, queueing, or LLM calls; reject with `edge_endpoint_pair_not_allowed`.
- Keep `ForeignKeyTo` Column-to-Column canonical. Retain Table-to-Table only if existing compatibility evidence requires it, then document and test it as a distinct explicit pair.
- Keep broad semantic edge families finite: executable pairs for `Calls`; explicit code-unit/derived-object sources for `ReadsFrom`/`WritesTo`; documented Table/View/MaterializedView/Column pairs for `JoinsWith`; enumerated maps for `DependsOn`, `ReferencesByCode`, and `DerivedFrom`.
- Enforce special invariants in the same authority: Trigger source for `TriggerOn`, Synonym source for `SynonymFor`, DictionaryDocument/SourceArtifact targets for `DocumentedBy`, Sequence target for `UsesSequence`, and documented evidence requirement for `EnforcedBy`.
- Leave `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` unregistered. Unknown edge types or pairs fail closed; clients cannot widen or replace the registry.

#### Explicit Evidence Contract
- Replace the catalog-v2 Cartesian provenance input with `CatalogEvidenceLink`: exactly one `source_key`, one exclusive typed entity-or-edge target, allowlisted evidence kind, bounded locator/excerpt/extractor/rule metadata, finite confidence, optional lowercase SHA-256.
- Entity targets carry exactly `entity_type` and `graph_key`; edge targets carry exactly `edge_type` and `edge_key`. Mixed, empty, ambiguous, or incomplete targets fail recursive validation.
- Evidence kinds are exactly `oracle_dictionary`, `ddl`, `view_sql`, `plsql_source`, `comment`, and `manual`.
- Preserve source and excerpt bytes used for hashing; apply explicit string, collection, depth, node-count, finite-number, and format bounds at model validation.
- Give each evidence link a catalog-v2 UUIDv5 identity and canonical content hash through pure identity helpers. One request entry means one explicit source-to-target link; duplicates may be normalized only when byte-identical.
- Reject the legacy multi-source/multi-target Cartesian shape. Do not auto-convert it. Persistence and exact-target resolution remain Phase 3B.

#### Authoritative Hash Contract
- Require `catalog_sha256` as lowercase 64-hex on every combined catalog batch, including dry-run.
- Compute `request_sha256` from a version-tagged canonical payload containing identity schema version, canonicalization version, group ID, batch ID, catalog hash, and every canonical entity, edge, provenance-source, and evidence-link field.
- Exclude only documented transport/execution fields: `dry_run`, caller audit hash, generated timestamps, retry counters, and future plan tokens.
- Make canonical collection ordering deterministic and semantically order-invariant while retaining multiplicity where contractually meaningful. Changing any included field or `catalog_sha256` changes the digest; excluded fields do not.
- Use one canonicalization-version constant and reusable canonical JSON recipe for request, item, prepared payload, evidence, and future manifest hashing.
- Treat caller `request_sha256` as audit-only exact-match input; mismatch returns `content_hash_mismatch`. Never let it become identity or write authority.
- Return `identity_schema_version`, `canonicalization_version`, server `request_sha256`, `catalog_sha256`, and deterministic `batch_uuid` from every batch response, including dry-run and safe failures where derivable.

#### Read-Only Capabilities
- Add `get_catalog_capabilities` as a read-only MCP tool available after server initialization even when catalog writes are disabled or UUID write prerequisites are incomplete.
- Return package/server version, backend, safely determined connectivity state, read/write gate states, namespace-configured boolean, and a non-reversible namespace fingerprint; never expose the raw namespace or secrets.
- Return identity/canonicalization/catalog schema versions; entity prefix/grammar registry; edge registry; complete endpoint map; configured limits plus immutable hard limits.
- Report embedding configuration/readiness and Neo4j index/vector readiness only when safely knowable without mutation. Unknown state remains explicit rather than triggering setup or writes.
- Report support flags for prepare/commit, explicit evidence links, manifests, and manifest verification truthfully according to implemented phase state.
- Preserve `get_status.status` and `get_status.message` exactly; any capability summary is additive only.

#### Phase 2 Gate
- Add exhaustive table-driven tests for every allowed and representative rejected pair across all 16 edge types, shared-authority use, deferred edge rejection, and pre-side-effect ordering.
- Add hash mutation tests covering every included domain field, stable excluded fields, ordering rules, catalog-hash sensitivity, caller mismatch, and dry-run authoritative hashes with zero writes.
- Add recursive evidence tests for exclusive targets, allowlisted kinds, bounds, finite confidence, deterministic UUID/hash, no Cartesian input, and safe errors.
- Add capabilities tests for disabled writes, missing namespace, non-Neo4j/readiness unknown states, no mutation, secret redaction, complete registries/limits/features, tool registration, and `get_status` compatibility.
- Tests use only `oracle-catalog-tool-test`; never query or mutate `oracle-catalog-v2`; never run the canary. Phase 3A remains blocked until this focused gate passes truthfully.

### Claude's Discretion
- Choose the smallest module split that makes topology, canonicalization, and capability metadata single-source authorities without broad MCP-server refactoring.
- Choose exact evidence locator structure and hard bounds, favoring strict flat typed models over open dictionaries.
- Choose namespace fingerprint algorithm and display length, provided it is one-way, stable, domain-separated, non-secret, and tested not to expose the UUID namespace.
- Choose deterministic collection sort keys, provided every supported item has an unambiguous canonical identity and tests prove order invariance plus multiplicity behavior.

### Deferred Ideas (OUT OF SCOPE)
- Prepared-plan storage, opaque tokens, TTL/CAS, and discard: Phase 3A.
- Evidence persistence, exact target resolution, atomic domain/evidence/manifest co-commit: Phase 3B.
- Evidence reads and manifest-backed verification/resolution: Phase 4.
- `LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`, automatic catalog-v1 migration, and backend portability: out of scope.
- Canary execution and any `oracle-catalog-v2` access: separate Phase 6 approval.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EDGE-01 | Fixed server-owned endpoint map | New immutable registry module; single import site for models/service/capabilities/tests |
| EDGE-02 | Map covers all 16 approved edge types | Registry keys == `CATALOG_EDGE_TYPES`; assert equality in unit test |
| EDGE-03 | ForeignKeyTo Column→Column canonical; Table→Table only if needed | Live fixtures use Table→Table — retain both pairs, document dual |
| EDGE-04 | Calls / ReadsFrom / WritesTo finite executable sources | Explicit pair sets in registry (see Topology Authority) |
| EDGE-05 | TriggerOn/SynonymFor/DocumentedBy/UsesSequence specials | Source/target type constraints in same registry |
| EDGE-06 | JoinsWith + DependsOn/ReferencesByCode/DerivedFrom finite maps | Documented finite pairs; no open “any→any” |
| EDGE-07 | EnforcedBy pairs + evidence requirement | Pair map + keep existing `EnforcedBy` evidence model rule |
| EDGE-08 | Fail `edge_endpoint_pair_not_allowed` before side effects | Shared preflight before resolve/embed/schema/tx/status; spy tests |
| EDGE-09 | One authority across paths; deferred edges unregistered | Import map in edge upsert, batch, future prepare/verify/resolve, capabilities |
| HASH-01 | Required lowercase 64-hex `catalog_sha256` | Make field required on `UpsertCatalogBatchRequest` |
| HASH-02 | Server hash covers identity/group/batch/catalog/entities/edges/sources/evidence | Rewrite `_batch_canonical_payload` + version tag |
| HASH-03 | Exclude dry_run, caller hash, timestamps, retries, plan tokens | Documented exclusion set in code comment + tests |
| HASH-04 | Field/`catalog_sha256` mutation changes digest; order-invariant | Sort collections by stable identity keys before dump |
| HASH-05 | Batch results return versions + hashes + batch_uuid | Extend `CatalogBatchWriteResponse` |
| HASH-06 | Caller `request_sha256` audit-only exact match | Keep `assert_optional_client_hash` → `content_hash_mismatch` |
| HASH-07 | One canonicalization version constant | `CANONICALIZATION_VERSION` in identity module; all hash paths share `canonical_sha256` |
| CAPA-01 | `get_catalog_capabilities` works when writes disabled | MCP tool not gated by `catalog_upsert.enabled` |
| CAPA-02 | Version/backend/connectivity | From package + config + safe probe-or-unknown |
| CAPA-03 | Gates + namespace bool + fingerprint | Never return raw namespace |
| CAPA-04 | Identity/canonicalization/catalog schema versions | Constants from registries |
| CAPA-05 | Entity/edge registries + endpoint map | Generated views from same authorities |
| CAPA-06 | Configured + hard limits | From `CatalogConfig` + `HARD_MAX_*` |
| CAPA-07 | Embedding/index readiness without mutation | Explicit unknown; no schema init |
| CAPA-08 | Feature flags truthful to phase state | prepare/commit/manifest false until later phases |
| CAPA-09 | `get_status` status/message preserved | TypedDict contract unchanged |
| EVID-01 | `CatalogEvidenceLink` schema | New strict model |
| EVID-02 | Exclusive complete targets | Discriminated/exclusive validators |
| EVID-03 | Six evidence kinds | Literal allowlist |
| EVID-04 | Bounds on locator/excerpt/etc. | Flat typed locator + existing nested bounds |
| EVID-05 | Deterministic UUID + content hash | Pure helpers beside existing stubs |
| EVID-06 | Explicit links only | No product expansion |
| EVID-14 | Reject Cartesian shape; no auto-convert | Fail closed on legacy multi-source/target arrays for catalog-v2 batch |
| TEST-02 | Exhaustive endpoint pair tables | Parametrized allow + reject per edge type |
| TEST-04 | Hash mutation + dry-run zero-write | Field-by-field + spy suite |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Endpoint-pair registry | API / Backend (pure module) | — | Server authority; never client-owned |
| Edge pair validation | API / Backend (model + service preflight) | — | Fail before DB/embed/tx |
| Evidence-link request schema | API / Backend (Pydantic models) | — | Trust boundary; recursive forbid |
| Evidence identity/hash | API / Backend (pure identity helpers) | — | Deterministic; no I/O |
| Request/catalog hashing | API / Backend (pure + service) | — | Server-authoritative digest |
| Batch response hash echo | API / Backend | MCP wrapper | Include dry-run/safe fail |
| Capabilities discovery | API / Backend builder | MCP tool | Read-only after init |
| `get_status` compatibility | MCP surface | — | Preserve TypedDict fields |
| Neo4j domain writes | Database / Storage | — | **Out of Phase 2 scope** |
| Evidence/manifest persistence | Database / Storage | — | Phase 3B |
| Prepare/commit control plane | Database / Storage | — | Phase 3A |
| Browser / CDN | — | — | N/A (MCP server) |

## Project Constraints (from CLAUDE.md)

Actionable directives the planner must honor:

- Preserve every existing MCP tool name and public behavior (additive only).
- Neo4j first / 5.26+ only for catalog writes; no portability claim.
- Server-derived UUIDv5 only; `GRAPHITI_CATALOG_UUID_NAMESPACE` immutable; never auto-generate.
- Never interpolate unvalidated client labels/property names into Cypher.
- Writes return only after commit/rollback; Phase 2 must not open new write paths.
- Embeddings before write tx when writes exist — Phase 2 only spies that invalid topology/hash never reach embed.
- Isolation: every op constrained by `group_id`; tests only `oracle-catalog-tool-test`.
- Validate completely before side effects; structured safe logs (IDs/counts/codes only).
- Default limits 500 / 2000 / 5000; hard ceilings already in `catalog_common.py`.
- Phase 2 blocked until Phase 1 gate — **satisfied** (`ready_for_phase_2=true`).
- No deployment, live-group writes, full ingest, graph clear/delete.
- Ruff line length 100, single quotes; Pyright basic on mcp_server; pytest via `uv run --project mcp_server`.
- GSD workflow for product edits; research artifacts only this step.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | ≥3.10 (runtime 3.12.10 local) | Implementation | Project pin |
| Pydantic | ≥2.11.5 (mcp_server env 2.11.7) | Strict models, forbid extra | Already foundation of catalog models |
| pytest | ≥8.3.3 (local 9.0.3) | Unit gates | Existing mcp_server suite |
| pytest-asyncio | ≥0.24.0 | Async service spies | Existing |
| stdlib `hashlib` / `json` / `uuid` / `hmac` | stdlib | Canonical SHA-256, UUIDv5, fingerprint | No new deps |
| FastMCP (`mcp` ≥1.27.2) | installed | Tool registration | Existing MCP surface |
| Ruff / Pyright | project pins | Scoped lint/type | Phase 1 gate pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `CatalogStrictModel` | in-repo | Fail-closed base | All new request models |
| `canonical_sha256` | in-repo | Canonical JSON hash | All digests |
| `CatalogErrorCode` | in-repo | Structured codes | Reuse `edge_endpoint_pair_not_allowed`, `content_hash_mismatch` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pure frozenset map module | Embed map in `catalog_edges.py` only | Couples models to large constant; worse for capabilities generation |
| Discriminated Union evidence target | Two optional target fields + XOR validator | Union clearer at type-check; either OK if exclusive tests pass |
| Parallel hash function | Replace `_batch_canonical_payload` | Parallel path drifts — **forbidden** by CONTEXT |
| New packages for hashing | stdlib | YAGNI |

**Installation:** none — no new packages.

**Version verification:** pydantic 2.11.7 / pytest 9.0.3 via `uv run --project mcp_server` [VERIFIED: local mcp_server env]. Package legitimacy N/A (no installs).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none)* | — | — | — | — | — | No Phase 2 package installs |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
MCP client
  │
  ├─ upsert_typed_edges / upsert_catalog_batch
  │     │
  │     ▼
  │  Pydantic CatalogStrictModel validation
  │     │  (identity, grammar, allowlists, evidence shape)
  │     ▼
  │  Topology preflight ──► EDGE_ENDPOINT_MAP authority
  │     │  reject edge_endpoint_pair_not_allowed
  │     │  BEFORE store.resolve_endpoint / embed / schema / tx / status
  │     ▼
  │  Hash authority ──► CANONICALIZATION_VERSION + canonical_sha256
  │     │  require catalog_sha256; compute request_sha256
  │     │  optional caller request_sha256 audit match
  │     ▼
  │  Existing service path (gate → resolve → embed → write)
  │     │  Phase 2 does NOT redesign store/write
  │     ▼
  │  CatalogBatchWriteResponse (+ identity/canonicalization/request/catalog hashes)
  │
  ├─ get_catalog_capabilities  (NO write gate)
  │     │
  │     ▼
  │  Pure builder from config + registries + safe state
  │     │  never raw namespace / secrets / mutation
  │     ▼
  │  CapabilitiesResponse
  │
  └─ get_status  (unchanged status + message)
```

### Recommended Project Structure

```text
mcp_server/src/
├── models/
│   ├── catalog_common.py          # keep allowlists, limits, error codes
│   ├── catalog_edges.py           # call topology check from model and/or service
│   ├── catalog_batch.py           # require catalog_sha256; evidence links field
│   ├── catalog_provenance.py      # keep CatalogSourceItem; add/coexist evidence models
│   ├── catalog_evidence.py        # NEW (discretion): CatalogEvidenceLink + locator + kinds
│   ├── catalog_topology.py        # NEW: EDGE_ENDPOINT_MAP + is_pair_allowed + export view
│   └── catalog_responses.py       # extend batch response; add CapabilitiesResponse
├── services/
│   ├── catalog_identity.py        # CANONICALIZATION_VERSION; evidence hash/uuid material;
│   │                              # namespace_fingerprint; shared batch canonical recipe
│   ├── catalog_service.py         # preflight topology; replace batch hash; capabilities method
│   └── catalog_capabilities.py    # NEW (discretion): pure build_catalog_capabilities()
└── graphiti_mcp_server.py         # register get_catalog_capabilities; CATALOG_TOOL_NAMES update

mcp_server/tests/
├── test_catalog_topology.py       # NEW: exhaustive pair tables
├── test_catalog_evidence.py       # NEW: evidence contract
├── test_catalog_hash.py           # NEW or section: HASH mutation suite
├── test_catalog_capabilities.py   # NEW: capa + get_status compat
├── test_catalog_models.py         # extend batch required catalog_sha256
└── test_catalog_service.py        # pre-side-effect ordering spies
```

**Smallest-split discretion (locked as recommendation):**

1. `models/catalog_topology.py` — map + pure `assert_edge_endpoint_pair_allowed(...)`.
2. `models/catalog_evidence.py` — evidence models (keeps provenance sources separate).
3. Hash versioning + fingerprint + batch recipe pure functions in `catalog_identity.py` (already pure).
4. `services/catalog_capabilities.py` — pure builder; service/MCP thin wrappers.
5. **Do not** split `catalog_service.py` into multiple write orchestrators this phase.

### Pattern 1: Single Topology Authority

**What:** Immutable `Mapping[str, frozenset[tuple[str, str]]]` keyed by edge type.
**When:** Any edge validation, capabilities export, future prepare/verify/resolve.
**Example:**

```python
# Source: in-repo pattern recommendation (models/catalog_topology.py)
from models.catalog_common import CATALOG_EDGE_TYPES, CatalogErrorCode

EDGE_ENDPOINT_MAP: dict[str, frozenset[tuple[str, str]]] = {
    'ForeignKeyTo': frozenset({
        ('Column', 'Column'),  # canonical
        ('Table', 'Table'),    # retained compatibility — see fixtures
    }),
    # ... all 16 types; no LikelyReferencesTo/MapsTo/SynchronizesTo
}

def validate_edge_endpoint_pair(edge_type: str, source: str, target: str) -> None:
    allowed = EDGE_ENDPOINT_MAP.get(edge_type)
    if allowed is None or (source, target) not in allowed:
        raise ValueError(f'{CatalogErrorCode.edge_endpoint_pair_not_allowed}: ...')
```

### Pattern 2: Pre-Side-Effect Ordering

**What:** Topology + full model validation → hash → **then** existing resolve/embed/tx.
**When:** `upsert_typed_edges`, `upsert_catalog_batch` (and future prepare).
**Live order today (edges):** gate → identity/hash → **endpoint DB resolve** → embed → tx.  
**Required change:** insert pair check **before** `_store.resolve_endpoint_typed` (and before any batch endpoint resolve). Prefer model-level check on request data so invalid pairs never enter service; service re-check is defense-in-depth for shared authority.

### Pattern 3: Explicit Evidence Link (no Cartesian)

**What:** One list of `CatalogEvidenceLink` rows; each row one `source_key` + exclusive target.
**When:** catalog-v2 batch path. Standalone `upsert_provenance` Cartesian remains until Phase 3B/compat decision — **catalog-v2 batch must reject Cartesian nested shape** (EVID-14). Recommendation: for catalog-v2 batch, replace `NestedProvenancePayload` entity/edge target arrays with `evidence_links: list[CatalogEvidenceLink]` + optional `sources: list[CatalogSourceItem]` for source records; fail if legacy multi-target product fields present.

### Pattern 4: Versioned Canonical Hash Recipe

**What:** One constant + one pure function used by item, batch, and future prepare/manifest.

```python
# Source: extend catalog_identity.py (existing canonical_sha256 pattern)
CANONICALIZATION_VERSION = 'catalog-canonical-v1'
CATALOG_SCHEMA_VERSION = 'catalog-schema-v1'  # capabilities reporting

def batch_request_canonical_payload(request) -> dict:
    return {
        'canonicalization_version': CANONICALIZATION_VERSION,
        'identity_schema_version': request.identity_schema_version,
        'group_id': request.group_id,
        'batch_id': request.batch_id,
        'catalog_sha256': request.catalog_sha256,
        'entities': sorted(
            (entity_canonical_payload(e) for e in request.entities),
            key=lambda d: (d['entity_type'], d['graph_key']),
        ),
        'edges': sorted(
            (edge_canonical_payload(e) for e in request.edges),
            key=lambda d: (d['edge_type'], d['edge_key']),
        ),
        'sources': sorted(...),  # by source_key
        'evidence_links': sorted(...),  # by link identity key
    }
```

**Excluded fields (document in code):** `dry_run`, caller `request_sha256`, timestamps, retry counters, plan tokens, transport correlation IDs.

### Pattern 5: Capabilities Generated From Registries

**What:** Capabilities payload built by importing topology map, `ENTITY_TYPE_PREFIXES`, grammar registry, limits, phase feature flags — never a hand-copied second table.
**When:** `get_catalog_capabilities`.
**Phase-truthful flags after Phase 2:** `explicit_evidence_links=true` (schema only), `prepare_commit=false`, `manifests=false`, `manifest_verification=false`.

### Pattern 6: Namespace Fingerprint

**Discretion recommendation:**

```python
def namespace_fingerprint(namespace: uuid.UUID | None) -> str | None:
    if namespace is None:
        return None
    # domain-separated, one-way, short display
    material = b'graphiti.catalog.nsfp.v1|' + namespace.bytes
    return hashlib.sha256(material).hexdigest()[:16]
```

Tests: fingerprint stable; changing namespace changes fingerprint; fingerprint ≠ str(namespace); raw namespace never in response JSON.

### Anti-Patterns to Avoid

- **Parallel hash paths** — do not leave old `_batch_canonical_payload` and add another; replace in place.
- **Client-owned maps** — capabilities expose map for discovery only; validation always server-side.
- **Cartesian compatibility adapter** — EVID-14 forbids auto-convert.
- **Schema init from capabilities** — CAPA-07 unknown over mutation.
- **Mutating `get_status` required fields** — CAPA-09.
- **New store write for evidence/topology** — hard gate forbids Phase 2 store/control-plane write redesign.
- **Registering deferred edge types** — fail closed.
- **Returning raw `uuid_namespace`** — secret-adjacent deployment config.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Canonical JSON hash | Custom float/key walk | Existing `canonical_sha256` | NaN/Inf reject + sort_keys already correct |
| UUIDv5 identity | Caller UUIDs / random | `catalog_*_uuid` helpers | Collision-free under namespace |
| Strict validation | Ad-hoc dict checks | `CatalogStrictModel` | Recursive forbid + field paths |
| Structured errors | Exception strings | `CatalogErrorCode` + SAFE-08 converter | No payload leak |
| Endpoint allowlist | Per-tool if/else copies | One `EDGE_ENDPOINT_MAP` | Drift across batch/edge/prepare |
| Capabilities tables | Hand-maintained docs only | Generate from registries | Doc/runtime drift |
| Fingerprint | Truncated raw UUID | Domain-separated SHA-256 | Reversible exposure risk |

**Key insight:** Phase 2 is almost entirely pure authority modules + wiring. Complexity is **contract completeness and test exhaustiveness**, not new infrastructure.

## Topology Authority (Prescriptive Map)

> Pair sets marked `[ASSUMED]` are Claude's discretion recommendations for finite broad families. Planner should treat them as the default locked map unless a later discuss pass amends them. Specials and FK dual pairs are grounded in requirements + live fixtures.

### Special / tightly constrained [HIGH]

| Edge type | Allowed pairs | Notes |
|-----------|---------------|-------|
| `ForeignKeyTo` | `(Column, Column)`, `(Table, Table)` | Column canonical; Table retained — live fixtures/int tests [VERIFIED: mcp_server tests] |
| `PrimaryKeyOf` | `(Constraint, Table)`, `(Constraint, Column)` | `[ASSUMED]` PK constraint ownership |
| `UniqueKeyOf` | `(Constraint, Table)`, `(Constraint, Column)` | `[ASSUMED]` |
| `EnforcedBy` | `(Constraint, Table)`, `(Constraint, Column)` | Plus non-empty `evidence` model rule (live) |
| `TriggerOn` | `(Trigger, Table)`, `(Trigger, View)`, `(Trigger, MaterializedView)` | Trigger source only |
| `SynonymFor` | `(Synonym, Table)`, `(Synonym, View)`, `(Synonym, MaterializedView)`, `(Synonym, Sequence)`, `(Synonym, Procedure)`, `(Synonym, Function)`, `(Synonym, Package)`, `(Synonym, Synonym)` | Synonym source only `[ASSUMED]` targets finite |
| `DocumentedBy` | any catalog entity type → `(DictionaryDocument\|SourceArtifact)` as **target** | Encode as pairs `(E, DictionaryDocument)`, `(E, SourceArtifact)` for each entity type E, **or** special-case target check in validator — prefer explicit pairs for capabilities export |
| `UsesSequence` | code-unit sources → `Sequence` | Sources: `Procedure`, `Function`, `Trigger`, `Package`, `View`, `MaterializedView` `[ASSUMED]` |

### Structural Contains [ASSUMED finite]

| Source | Targets |
|--------|---------|
| `System` | `Database` |
| `Database` | `Schema`, `DatabaseLink` |
| `Schema` | `Table`, `View`, `MaterializedView`, `Package`, `Procedure`, `Function`, `Trigger`, `Sequence`, `Synonym`, `Index`, `Constraint`, `SourceArtifact` |
| `Table` / `View` / `MaterializedView` | `Column` |
| `Package` | `Procedure`, `Function` |
| `DictionaryDocument` | `SourceArtifact` |

### Executable / dataflow [ASSUMED finite]

| Edge type | Sources | Targets |
|-----------|---------|---------|
| `Calls` | `Procedure`, `Function`, `Trigger`, `Package` | `Procedure`, `Function`, `Package` |
| `ReadsFrom` | `Procedure`, `Function`, `Trigger`, `Package`, `View`, `MaterializedView` | `Table`, `View`, `MaterializedView`, `Column`, `Synonym` |
| `WritesTo` | `Procedure`, `Function`, `Trigger`, `Package` | `Table`, `Column`, `View`, `MaterializedView`, `Synonym` |
| `JoinsWith` | `Table`, `View`, `MaterializedView`, `Column` | same four types (all combinations among the four) |

### Broad but finite [ASSUMED]

| Edge type | Rule |
|-----------|------|
| `DependsOn` | Finite union of structural + executable dependency pairs (Contains-like hierarchy + Calls/Reads/Writes endpoints); implement as explicit frozenset, not “any→any” |
| `ReferencesByCode` | Code units (`Package`,`Procedure`,`Function`,`Trigger`,`SourceArtifact`) → any of Table/View/MView/Column/Sequence/Synonym/Package/Procedure/Function |
| `DerivedFrom` | `View`/`MaterializedView`/`SourceArtifact` → `Table`/`View`/`MaterializedView`/`Column`/`SourceArtifact` |

### Unregistered (must reject as unknown edge type)

`LikelyReferencesTo`, `MapsTo`, `SynchronizesTo` — not in `CATALOG_EDGE_TYPES` today; keep out.

### Validation API contract

- Input: `edge_type`, `source_entity_type`, `target_entity_type` from request (no DB).
- Unknown edge type: existing allowlist error at model layer (`edge_type not allowlisted`).
- Known edge, disallowed pair: `edge_endpoint_pair_not_allowed`.
- `EnforcedBy` evidence emptiness: keep model validator (orthogonal to pair map).
- Unit test: `set(EDGE_ENDPOINT_MAP) == CATALOG_EDGE_TYPES` and every pair member ∈ `CATALOG_ENTITY_TYPES`.

## Evidence Contract (Prescriptive Schema)

```python
EVIDENCE_KINDS = frozenset({
    'oracle_dictionary', 'ddl', 'view_sql', 'plsql_source', 'comment', 'manual',
})

class CatalogEvidenceLocator(CatalogStrictModel):
    object_name: str | None = Field(default=None, max_length=MAX_SHORT_STRING_LENGTH)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    statement_index: int | None = Field(default=None, ge=0)
    # model_validator: if both lines set, end_line >= start_line

class CatalogEvidenceEntityTarget(CatalogStrictModel):
    entity_type: str  # allowlisted + grammar on graph_key
    graph_key: str

class CatalogEvidenceEdgeTarget(CatalogStrictModel):
    edge_type: str  # allowlisted
    edge_key: str

class CatalogEvidenceLink(CatalogStrictModel):
    source_key: str
    entity_target: CatalogEvidenceEntityTarget | None = None
    edge_target: CatalogEvidenceEdgeTarget | None = None
    evidence_kind: Literal['oracle_dictionary','ddl','view_sql','plsql_source','comment','manual']
    locator: CatalogEvidenceLocator | None = None
    excerpt: str | None = Field(default=None, max_length=MAX_EVIDENCE_LENGTH)  # preserve bytes
    extractor_name: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    extractor_version: str = Field(..., min_length=1, max_length=MAX_SHORT_STRING_LENGTH)
    rule_id: str | None = Field(default=None, max_length=MAX_SHORT_STRING_LENGTH)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # finite check
    content_sha256: str | None = None  # optional client; 64 lowercase hex

    # XOR: exactly one of entity_target / edge_target
```

**Identity material (pure):**

- Link key for UUID: canonical fields excluding client content hash transport:
  `source_key|target_kind|target_type|target_key|evidence_kind|extractor_name|extractor_version|rule_id|locator_canonical`
- UUID: existing `catalog_evidence_link_uuid(ns, group_id, link_key)`
- Content hash: `canonical_sha256(evidence_canonical_payload(link))` including excerpt bytes as submitted

**Batch model change:**

- Require `catalog_sha256: str` (not optional).
- Catalog-v2 batch provenance: prefer `sources` + `evidence_links`; reject if legacy `entity_targets`/`edge_targets` multi-link Cartesian fields appear on catalog-v2 requests (EVID-14). Implementation option with least blast radius: replace `NestedProvenancePayload` fields for v2 batch with evidence_links list; update service Cartesian counters to `len(evidence_links)`.

**Standalone `upsert_provenance`:** leave v1 Cartesian tool name registered (SAFE-09) but do not use it as catalog-v2 batch authority; Phase 3B owns persistence redesign. Phase 2 tests focus on batch + model rejection of Cartesian for v2.

## Hash Contract Gaps (Live vs Required)

Live `_batch_canonical_payload` [VERIFIED: catalog_service.py:3579-3604]:

```text
includes: group_id, batch_id, entities[], edges[], provenance{sources, entity_targets, edge_targets}
excludes: identity_schema_version, catalog_sha256, canonicalization_version, system_key?
order: input order (NOT sorted)
```

Required recipe:

| Field | Include? |
|-------|----------|
| `canonicalization_version` | yes |
| `identity_schema_version` | yes |
| `system_key` | yes (affects domain identity scope) `[ASSUMED include — changes semantic membership]` |
| `group_id`, `batch_id` | yes |
| `catalog_sha256` | yes (required input) |
| entity/edge/source/evidence canonical bodies | yes |
| `dry_run` | no |
| caller `request_sha256` | no |
| timestamps / retries / plan tokens | no |

**Response fields to add on `CatalogBatchWriteResponse`:**

- `identity_schema_version: str | None`
- `canonicalization_version: str | None`
- `request_sha256: str | None` (server)
- `catalog_sha256: str | None`
- existing `batch_uuid`

Return these on dry-run success and on failures **where hash is derivable** (after successful model parse). Gate failures before hash may omit server hash but should still echo `catalog_sha256` input when present.

**Item-level** `entity_canonical_payload` / `edge_canonical_payload` / `source_canonical_payload` remain building blocks; add `evidence_canonical_payload`. Move batch recipe to `catalog_identity` pure functions so prepare (3A) imports the same code without service coupling.

## Capabilities Contract

### Tool

```python
@mcp.tool()
async def get_catalog_capabilities() -> CapabilitiesResponse | ErrorResponse:
    # Works when catalog_service exists OR pure builder from config
    # MUST NOT require catalog_upsert.enabled
```

Add name to a **read-tool** set; do not put it behind write-only registration. Update `CATALOG_TOOL_NAMES` carefully: Phase 1 SAFE-08 boundary applies to validation-bearing catalog tools — capabilities may be read-only without request body; either include in structured-error set or leave as simple tool.

### Response shape (prescriptive)

```text
package_version: str          # mcp_server pyproject 1.0.2
backend: str | None           # neo4j / falkordb / ...
connectivity: 'ok'|'error'|'unknown'
catalog_writes_enabled: bool
catalog_reads_enabled: bool   # Phase 2: default True when server up (GATE split is Phase 4; report write gate + true reads)
uuid_namespace_configured: bool
namespace_fingerprint: str | None
identity_schema_version: 'catalog-v2'
canonicalization_version: str
catalog_schema_version: str
entity_types: [...]           # from ENTITY_TYPE_PREFIXES + grammar summaries
edge_types: [...]             # from CATALOG_EDGE_TYPES
endpoint_map: {edge_type: [[source, target], ...]}  # sorted
limits: {configured: {...}, hard: {...}}
embeddings: {provider, model?, ready: bool|'unknown'}
neo4j_indexes: 'ready'|'unknown'|'n/a'  # no mutation to discover if unsafe
features: {
  prepare_commit: false,
  explicit_evidence_links: true,   # schema available
  manifests: false,
  manifest_verification: false,
}
```

### `get_status` compatibility

Live [VERIFIED: response_types.py StatusResponse TypedDict + graphiti_mcp_server.get_status]:

```python
class StatusResponse(TypedDict):
    status: str
    message: str
```

Do **not** remove or rename these keys. Additive optional keys only if ever extended; Phase 2 recommendation: **leave `get_status` body unchanged**.

## Common Pitfalls

### Pitfall 1: Pair check after endpoint DB resolve
**What goes wrong:** Disallowed pairs still hit Neo4j; fails EDGE-08.
**How to avoid:** Model validator and/or first lines of service after gate, before `_store.resolve_endpoint_typed`.
**Warning signs:** Spy shows `resolve_endpoint` called for bad pairs.

### Pitfall 2: Dual map drift (docs vs code vs capabilities)
**What goes wrong:** Capabilities lie; prepare later disagrees.
**How to avoid:** One module; capabilities import it; test equality.

### Pitfall 3: Cartesian leftover on batch
**What goes wrong:** EVID-06/14 fail; link counts explode.
**How to avoid:** Remove product validator; reject legacy fields; tests with multi-source×multi-target payload.

### Pitfall 4: Incomplete hash recipe → false idempotence
**What goes wrong:** Change `catalog_sha256` or identity version; same `request_sha256`.
**How to avoid:** Mutation tests per included field; golden vectors under version constant.

### Pitfall 5: Unstable collection order
**What goes wrong:** Same multiset different digest.
**How to avoid:** Sort by identity keys; multiplicity retained (stable sort of identical keys keeps duplicates).

### Pitfall 6: Capabilities mutates / leaks namespace
**What goes wrong:** Schema init or raw UUID in response.
**How to avoid:** Pure builder; fingerprint tests; no driver.write / build_indices.

### Pitfall 7: Breaking `get_status` or tool names
**What goes wrong:** SAFE-09 / CAPA-09 regressions.
**How to avoid:** Explicit tests for status keys and 7+1 tool registration.

### Pitfall 8: Implementing store/prepare “while here”
**What goes wrong:** Violates hard gate; Phase 3A scope bleed.
**How to avoid:** Phase 2 plans list pure modules + service preflight + MCP tool only.

### Pitfall 9: FK Column-only map breaks existing fixtures
**What goes wrong:** Mass test failure on Table→Table ForeignKeyTo.
**How to avoid:** Dual pair + migrate fixtures gradually; both pairs tested.

### Pitfall 10: Touching unrelated dirty tree
**What goes wrong:** SAFE-12 violation.
**How to avoid:** Commit only phase files; leave config/docker/catalog/ dirt alone.

## Code Examples

### Shared preflight in edge upsert (insertion point)

```python
# Source: catalog_service.upsert_typed_edges live order — insert after gate, before resolve
# After: gate = self._edge_gate_errors(...)
for idx, item in enumerate(request.edges):
    try:
        validate_edge_endpoint_pair(
            item.edge_type, item.source_entity_type, item.target_entity_type
        )
    except ValueError as exc:
        early_errors[idx] = CatalogItemResult(
            index=idx,
            status='error',
            edge_key=item.edge_key,
            edge_type=item.edge_type,
            error_code=CatalogErrorCode.edge_endpoint_pair_not_allowed,
            error_message='edge endpoint pair not allowed',
        )
# then existing identity/hash loop OR merge into it — still before resolve_endpoint_typed
```

### Dry-run hash echo without writes

```python
# Spies must show: no embedder.create, no driver.execute_write, no schema ensure
resp = await service.upsert_catalog_batch(client=client, request=req_dry)
assert resp.request_sha256 == CatalogService.batch_request_sha256(req_dry)
assert resp.catalog_sha256 == req_dry.catalog_sha256
assert resp.identity_schema_version == 'catalog-v2'
assert client.write_calls == []
```

### Capabilities with writes disabled

```python
config = CatalogConfig(enabled=False, uuid_namespace=None)
caps = build_catalog_capabilities(config=config, client=None)
assert caps.catalog_writes_enabled is False
assert caps.uuid_namespace_configured is False
assert caps.namespace_fingerprint is None
assert 'uuid_namespace' not in caps.model_dump()
```

## State of the Art

| Old Approach (v1.0 / pre-Phase-2) | Current Required Approach | Impact |
|-----------------------------------|---------------------------|--------|
| Edge type allowlist only | Finite endpoint-pair map | Topology fail-closed |
| Cartesian provenance | Explicit evidence links | Exact evidence; no product |
| Partial batch hash | Versioned full-domain recipe | True idempotence / prepare-ready |
| No capabilities tool | Read-only discovery | Agents learn limits without source |
| Optional `catalog_sha256` | Required on batch | HASH-01 |

**Deprecated/outdated for catalog-v2 batch:**

- `NestedProvenancePayload` multi-target product as the v2 write contract.
- Input-order-dependent request hashing.
- Treating Table→Table as the only FK form without documenting Column→Column.

## Runtime State Inventory

> Not a rename/migration phase. Omit full inventory.

**Note:** No runtime rename. Do not query/mutate `oracle-catalog-v2`. Historical ACCEPT_TAB hashes remain offline evidence only.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Finite pair sets for Contains/Calls/Reads/Writes/Joins/Depends/References/DerivedFrom as tabulated | Topology Authority | Over/under-accept edges; amend map + tests before 3A |
| A2 | Include `system_key` in request hash payload | Hash Contract | Hash mismatch with external builders if excluded |
| A3 | Batch v2 replaces Cartesian nested targets with `evidence_links` list | Evidence | Larger batch model break; still required by EVID-14 |
| A4 | Standalone `upsert_provenance` may remain Cartesian until 3B | Evidence | Dual API confusion — document clearly |
| A5 | Namespace fingerprint = SHA-256 domain sep, 16 hex chars | Capabilities | Display length preference only |
| A6 | Collection sort keys = (type, key) tuples as shown | Hash | Must match any external golden builders later |
| A7 | Phase 2 feature flags: prepare/manifest false; evidence schema true | Capabilities | Honesty of CAPA-08 |
| A8 | DocumentedBy expanded as explicit pairs for all entity types | Topology | Large map; special-case target check alternative |

**If wrong:** Discuss-phase can amend A1/A2/A3 without reopening Phase 1. Map content is the highest product-risk assumption.

## Open Questions (RESOLVED)

1. **DocumentedBy encoding — RESOLVED**
   - Decision: finite expanded-pair encoding. For every entity type E in `CATALOG_ENTITY_TYPES`, register pairs `(E, DictionaryDocument)` and `(E, SourceArtifact)` in `EDGE_ENDPOINT_MAP['DocumentedBy']` (A8 locked).
   - Rationale: single authority for validation and `endpoint_map_export` / capabilities; no special-case target branch that diverges from the map.
   - Plan owner: 02-01 Task 1.

2. **`system_key` in request hash — RESOLVED**
   - Decision: include `system_key` in `batch_request_canonical_payload` (A2 locked).
   - Rationale: system_key gates FE/BO domain membership; shell-only or partial batches must not silently share digests across systems.
   - Plan owner: 02-03 Task 1.

3. **Standalone provenance tool — RESOLVED**
   - Decision: `UpsertProvenanceRequest` / standalone `upsert_provenance` remains legacy Cartesian until Phase 3B (A4 locked). Catalog-v2 `UpsertCatalogBatchRequest` rejects Cartesian multi-target arrays and accepts only explicit `evidence_links` (EVID-14). No auto-convert adapter on either path.
   - Plan owner: 02-02 Task 2 (batch reject); standalone left intact.

4. **Exact `CATALOG_SCHEMA_VERSION` string — RESOLVED**
   - Decision: single exported authority `CATALOG_SCHEMA_VERSION = 'catalog-schema-v1'` in `mcp_server/src/services/catalog_identity.py` alongside `CANONICALIZATION_VERSION = 'catalog-canonical-v1'`.
   - Capabilities and responses import these symbols only; no duplicate string literals.
   - Plan owner: 02-03 creates; 02-04 imports.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | 3.12.10 | — |
| uv / mcp_server env | tests | ✓ | pydantic 2.11.7, pytest 9.0.3 | — |
| Neo4j live | Phase 2 unit policy | not required | — | skip int; spies only |
| Network package install | — | N/A | — | no new packages |

**Missing dependencies with no fallback:** none for Phase 2 unit scope.

**Step 2.6:** External services not required for this phase's unit gate.

## Validation Architecture

> `workflow.nyquist_validation` enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (mcp_server) |
| Config file | `mcp_server/pytest.ini` |
| Quick run command | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_topology.py mcp_server/tests/test_catalog_evidence.py mcp_server/tests/test_catalog_hash.py mcp_server/tests/test_catalog_capabilities.py -q --tb=line` |
| Full suite command | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_identity.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_topology.py mcp_server/tests/test_catalog_evidence.py mcp_server/tests/test_catalog_hash.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_store_unit.py -q --tb=line` |
| Scoped ruff | `uv run --project mcp_server ruff check mcp_server/src/models mcp_server/src/services/catalog_identity.py mcp_server/src/services/catalog_service.py mcp_server/src/services/catalog_capabilities.py mcp_server/src/graphiti_mcp_server.py mcp_server/tests/test_catalog_*.py` |
| Scoped pyright | `uv run --project mcp_server pyright --project mcp_server/pyproject.toml` + same paths |
| Neo4j int | **skip** for Phase 2 gate (unit policy; do not probe) |
| Safety | `canary_executed=false`; `oracle_catalog_v2_queried=false`; `no_new_store_or_control_plane_write_path=true` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| EDGE-01..02 | Map covers 16 types; equals allowlist | unit | `pytest ... test_catalog_topology.py -k map_complete` | ❌ Wave 0 |
| EDGE-03 | FK Column+Table pairs | unit | `pytest ... -k foreign_key_pairs` | ❌ Wave 0 |
| EDGE-04..07 | Family specials | unit table | `pytest ... test_catalog_topology.py` | ❌ Wave 0 |
| EDGE-08 | Pair fail before resolve/embed/schema/tx | service spy | `pytest ... test_catalog_service.py -k endpoint_pair_before` | ❌ Wave 0 |
| EDGE-09 | Shared authority import; deferred edges | unit | `pytest ... -k deferred_edge or shared_authority` | ❌ Wave 0 |
| TEST-02 | Exhaustive allow+reject tables | unit | `pytest ... test_catalog_topology.py` | ❌ Wave 0 |
| EVID-01..06,14 | Evidence schema + no Cartesian | unit | `pytest ... test_catalog_evidence.py` | ❌ Wave 0 |
| HASH-01 | catalog_sha256 required | unit | `pytest ... test_catalog_models.py -k catalog_sha256` | ❌ Wave 0 |
| HASH-02..04,07 | Recipe coverage + order + version | unit | `pytest ... test_catalog_hash.py` | ❌ Wave 0 |
| HASH-05..06 | Response echo + caller mismatch | service | `pytest ... test_catalog_service.py -k request_sha256 or hash_mismatch` | ❌ Wave 0 |
| TEST-04 | Field mutation + dry-run zero write | unit+spy | `pytest ... test_catalog_hash.py test_catalog_service.py -k dry_run_hash` | ❌ Wave 0 |
| CAPA-01..08 | Capabilities content + no mutation | unit | `pytest ... test_catalog_capabilities.py` | ❌ Wave 0 |
| CAPA-09 | get_status keys preserved | unit | `pytest ... -k get_status_compat` | ❌ Wave 0 |
| SAFE-01/02 | Isolation / no canary | structural gate | Phase 2 gate runner (mirror 01-11) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** quick run command (topology+evidence+hash+capabilities)
- **Per wave merge:** full suite command + scoped ruff/pyright
- **Phase gate:** full green + safety flags + `ready_for_phase_3a=false` until all exit criteria true

### Wave 0 Gaps

- [ ] `mcp_server/src/models/catalog_topology.py` — map authority
- [ ] `mcp_server/src/models/catalog_evidence.py` — evidence models (or section in provenance)
- [ ] `mcp_server/src/services/catalog_capabilities.py` — pure builder
- [ ] `mcp_server/tests/test_catalog_topology.py` — covers EDGE-*/TEST-02
- [ ] `mcp_server/tests/test_catalog_evidence.py` — covers EVID-01..06,14
- [ ] `mcp_server/tests/test_catalog_hash.py` — covers HASH-*/TEST-04
- [ ] `mcp_server/tests/test_catalog_capabilities.py` — covers CAPA-*
- [ ] Extend `CatalogBatchWriteResponse` + batch request model
- [ ] Replace `CatalogService._batch_canonical_payload` / `batch_request_sha256`
- [ ] Wire topology preflight in `upsert_typed_edges` + `upsert_catalog_batch`
- [ ] Register `get_catalog_capabilities` MCP tool
- [ ] Phase 2 gate report + optional tracked runner (mirror Phase 1 pattern)
- [ ] Update fixtures that build batch without `catalog_sha256` / Cartesian provenance

*(Existing `test_catalog_models.py` / `test_catalog_service.py` / `test_catalog_identity.py` remain; extend rather than discard.)*

### Suggested Phase 2 Gate Contract Keys

```
topology_map=pass
evidence_contract=pass
hash_contract=pass
capabilities=pass
focused_pytest=pass
scoped_ruff=pass
scoped_pyright=pass
safety_no_probe=pass
canary_executed=false
oracle_catalog_v2_queried=false
no_new_store_or_control_plane_write_path=true
ready_for_phase_3a=true|false
local_gate_pass=true|false
nyquist_compliant=true|false
```

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | MCP transport auth out of scope |
| V3 Session Management | no | — |
| V4 Access Control | yes | `group_id` isolation; write gate; capabilities without write |
| V5 Input Validation | yes | `CatalogStrictModel`, allowlists, topology map, evidence XOR, hash format |
| V6 Cryptography | yes | SHA-256 digests; UUIDv5; one-way namespace fingerprint — never hand-roll crypto |
| V7 Error Handling | yes | SAFE-08 structured codes; no payload/stack in logs |
| V13 API | yes | Fail closed; no client Cypher identifiers |

### Known Threat Patterns for catalog MCP

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Illegal topology becomes searchable truth | Tampering | Server endpoint map before write |
| Cartesian provenance inflation | Denial of Service / Tampering | Explicit evidence links only |
| Hash exclusion → false idempotence | Tampering | Versioned full-domain recipe + mutation tests |
| Namespace/secret leak via capabilities | Information Disclosure | Fingerprint only; redaction tests |
| Capabilities triggers schema repair | Elevation / Tampering | Read-only builder; unknown readiness |
| Client supplies edge map | Spoofing | Ignore client maps; server authority only |
| Log payload / excerpt | Information Disclosure | Log batch_id/counts/codes only |
| Deferred edge smuggling | Tampering | Unregistered types fail closed |

## Sources

### Primary (HIGH confidence)

- Live code: `mcp_server/src/models/catalog_{common,edges,batch,provenance,responses}.py`
- Live code: `mcp_server/src/services/catalog_{identity,service,store}.py`
- Live code: `mcp_server/src/graphiti_mcp_server.py` (tools + `get_status`)
- Live fixtures: `mcp_server/tests/catalog_neo4j_fixtures.py` (Table→Table FK)
- Live tests: `test_catalog_service.py` `_edge()` Table→Table ForeignKeyTo
- Phase 1 gate: `01-PHASE1-GATE.md` (`ready_for_phase_2=true`)
- CONTEXT: `02-CONTEXT.md` locked decisions
- REQUIREMENTS / ROADMAP Phase 2 IDs and hard gates
- Prior research: `.planning/research/{ARCHITECTURE,PITFALLS}.md` patterns 5–6
- Pre-canary roadmap EN Phase 2 section

### Secondary (MEDIUM confidence)

- `.planning/research/FEATURES.md` illegal pair / dry-run behaviors
- Phase 1 RESEARCH module-split precedents

### Tertiary (LOW confidence)

- Exact finite pair enumerations for broad edge families (A1) — product discretion defaults above

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — no new deps; versions verified in mcp_server env
- Architecture: **HIGH** — live code paths and insertion points verified
- Topology pair enumerations: **MEDIUM** — specials/FK dual HIGH; broad families ASSUMED
- Pitfalls: **HIGH** — grounded in live Cartesian hash gaps + prior PITFALLS.md
- Validation: **HIGH** — mirrors Phase 1 Nyquist pattern

**Research date:** 2026-07-18  
**Valid until:** 2026-08-17 (30 days; contracts stable)

---

*Planner must honor User Constraints first. Prefer pure modules + wiring over service rewrites. No store/control-plane write path in Phase 2 plans.*
