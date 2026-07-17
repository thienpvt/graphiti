# Phase 1: Strict Contracts and Catalog-v2 Identity - Research

**Researched:** 2026-07-18
**Domain:** Pydantic v2 fail-closed request contracts + deterministic catalog-v2 identity (mcp_server catalog surface)
**Confidence:** HIGH

## Summary

Phase 1 hardens the already-shipped v1.0 deterministic catalog MCP surface into fail-closed catalog-v2 request contracts and collision-free FE/BO/COMMON identity. Live code today is **prefix-only, unversioned identity material** with **Pydantic default `extra='ignore'`**, optional `strict_endpoints: bool = True`, and UUID material `group_id|entity_type|graph_key` (no `catalog-v2` segment). No `system_key`, no `identity_schema_version`, no complete graph-key grammar, and three entity types required by IDEN-05/09 (`System`, `DatabaseLink`, `SourceArtifact`) are absent from `ENTITY_TYPE_PREFIXES`.

Work is pure model/identity/unit-test surface. **No new store path, no control-plane writes, no endpoint map, no evidence contract, no hash recipe freeze, no canary, no Neo4j mutation of live groups.** Phase 2 is blocked until the Phase 1 focused unit gate is green.

**Primary recommendation:** Add one shared `CatalogStrictModel` (`ConfigDict(extra='forbid')`), a pure grammar/identity registry module next to `catalog_identity.py`, version all UUID helpers with explicit `catalog-v2` material, extend `CatalogErrorCode` without removals, and land table-driven unit tests only — leave service write orchestration and store untouched except signature call-site updates required by identity helper versioning.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Strict Request Contracts
- Introduce one shared strict Pydantic base with `ConfigDict(extra='forbid')`; every deterministic catalog request and nested request model inherits it.
- Unknown and misspelled fields fail at their exact nested field paths; validators preserve submitted bytes for source/hash-bearing text rather than stripping or normalizing them.
- Keep `strict_endpoints` and `atomic` only as enforceable `Literal[True]` contracts; `false` is rejected during model validation.
- Validate the entire request before service access; invalid requests cannot trigger DB reads, embeddings, schema initialization, transactions, status writes, queueing, or LLM calls.

#### Catalog-v2 Scope and Grammar
- Every domain request declares exactly `identity_schema_version='catalog-v2'` and required canonical `system_key` from `FE`, `BO`, or `COMMON`.
- Graph keys visibly include system scope and fully qualified database identity. Use one server-owned registry of exact per-entity-type grammars, not prefix-only checks.
- Add only `System`, `DatabaseLink`, and `SourceArtifact` to the entity allowlist. Add no business-domain entities.
- Procedure and Function grammar includes a stable explicit overload discriminator; package and standalone overloads cannot collapse.

#### Ownership Rules
- FE and BO objects with otherwise identical Oracle names remain in one `group_id` but have different graph keys and UUIDs.
- `COMMON` is accepted only when explicitly supplied by an authoritative caller under the request contract. Unknown ownership fails; it never defaults to `COMMON`.
- Nested entity and endpoint references must carry compatible version/system scope and exact graph-key grammar.
- Empty, non-canonical, overlong, mismatched, or unknown `system_key` fails as `invalid_system_key` before side effects.

#### Deterministic Identity
- Entity UUID material is `group_id|catalog-v2|entity_type|graph_key`; equivalent explicit `catalog-v2` material applies to edge, source, mentions/evidence, batch, manifest, and prepared-plan identity helpers as those helpers exist or are introduced in their owning phases.
- Caller UUIDs remain absent from authority-bearing request contracts and never override server-derived UUIDv5 values.
- Catalog-v1 graph keys, UUID material, payloads, hashes, and historical ACCEPT_TAB goldens are rejected or treated as offline evidence only; no automatic normalization, re-keying, or rewrite exists.
- Preserve tool names. Catalog-v2 request breakage is explicit and documented through required version fields and tests.

#### Structured Errors
- Extend the fixed error registry with the Phase 1 required codes without removing existing codes.
- Validation/service errors expose bounded non-sensitive `code`, `message`, `field_path` when applicable, `retryable`, and safe correlation ID.
- No stack trace, full exception, payload, source text, credential, auth header, or raw secret appears in responses or logs.
- Failures use deterministic precedence: schema/version/system/grammar validation before any backend/provider/readiness error.

#### Unit Gate
- Add table-driven unit tests for recursive strictness, misspelled optionals, literal flags, all entity grammars, FE/BO separation, overload separation, catalog-v1 rejection, UUID versioning, caller-UUID non-authority, safe errors, and no-side-effect precedence.
- Phase 2 remains blocked until the Phase 1 focused unit gate passes. Baseline failures from Phase 0 remain separately recorded and are not repaired unless Phase 1 directly causes them.
- Tests use `oracle-catalog-tool-test` only; no test queries or mutates `oracle-catalog-v2`, and no canary runs.

### Claude's Discretion
- Choose the smallest module split that centralizes strict model configuration and grammar/identity authority without broad refactoring of the MCP monolith.
- Choose exact delimiter and regex syntax for each graph-key grammar, provided the documented examples, complete type coverage, visible system scope, overload stability, and fail-closed behavior are preserved.
- Choose whether safe structured validation conversion sits in model helpers or the thin MCP boundary, favoring one reusable path over duplicate wrappers.

### Deferred Ideas (OUT OF SCOPE)
- Edge endpoint-pair map, request hashing, evidence contract, and capabilities: Phase 2.
- Prepared-plan storage/token lifecycle: Phase 3A.
- Atomic domain/evidence/manifest commit: Phase 3B.
- Manifest-backed verification/read diagnostics: Phase 4.
- Canary execution: separate Phase 6 approval.
- Automatic catalog-v1 migration and new business entity types: out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONT-01 | Shared strict Pydantic base `extra='forbid'` | `CatalogStrictModel` on all request/nested models; live gap: no `model_config` / `extra` anywhere under `mcp_server/src/models/catalog_*.py` |
| CONT-02 | Unknown fields rejected every nesting depth | Nested items: entity/edge/source/target/locator/manifest/prepare shells; Phase 1 covers existing shells + nested items (prepare/commit models deferred until 3A) |
| CONT-03 | Misspelled optionals field-addressed | Same as CONT-01/02; Pydantic v2 `extra='forbid'` surfaces loc path |
| CONT-04 | Hash-bearing source bytes preserved | Live pattern already returns original `v` after emptiness check; do **not** return `v.strip()`; add regression tests for trailing space / exact `reference_time` |
| CONT-05 | `strict_endpoints` only `Literal[True]` | Live: `UpsertTypedEdgesRequest.strict_endpoints: bool = True` (`catalog_edges.py:129`) — accepts `false` today |
| CONT-06 | `atomic` only `Literal[True]` on batch | Live batch already `Literal[True]` (`catalog_batch.py:67`); entity/edge/provenance still `bool = True` — tighten all write requests |
| CONT-07 | Full validation before side effects | Service assumes pre-validated Pydantic models; MCP tools must `model_validate` before `CatalogService.*`; spy tests prove no embed/schema/tx/status on invalid input |
| CONT-08 | Extend error registry (9 new codes) | Live `CatalogErrorCode` lacks all 9; add without removing existing 17 codes |
| IDEN-01 | `identity_schema_version='catalog-v2'` required | New required `Literal['catalog-v2']` on domain write/read identity-bearing requests |
| IDEN-02 | Required `system_key` ∈ {FE, BO, COMMON} | New field + closed set constant; never default |
| IDEN-03 | `invalid_system_key` before side effects | Model validator + error code; unknown ownership never → COMMON |
| IDEN-04 | Complete per-type grammar, not prefix-only | Replace `startswith(prefix)` with registry fullmatch |
| IDEN-05 | Grammar for all 18 types | Expand allowlist 15→18; registry covers all |
| IDEN-06 | Procedure/Function overload discriminator | Grammar segment after package/name |
| IDEN-07 | FE/BO same Oracle name → different key/UUID | System segment in graph_key forces UUID divergence under same `group_id` |
| IDEN-08 | Responses expose full system-scoped keys | Existing `graph_key` fields already echo input; ensure no truncation/normalization |
| IDEN-09 | Add System, DatabaseLink, SourceArtifact only | Three new prefixes; no business entities |
| IDEN-10 | Entity UUID `group_id\|catalog-v2\|entity_type\|graph_key` | Change `catalog_entity_uuid` material |
| IDEN-11 | Edge/source/mentions/batch (+ future) versioned | Change existing helpers now; stub-ready names for evidence/manifest/plan without implementing persistence |
| IDEN-12 | No silent v1 accept/rewrite | Reject prefix-only / missing system / wrong version; no normalize path |
| IDEN-13 | ACCEPT_TAB / pre-hardening goldens invalid for v2 | Tests must not treat historical digests as valid v2; offline evidence only (Phase 0 policy) |
| SAFE-05 | Caller UUIDs never identity authority | Keep helpers free of caller-uuid params; no uuid fields on authority request items |
| SAFE-08 | Structured safe errors | Shared converter: code/message/field_path/retryable/correlation_id; no stack/payload |
| TEST-01 | Strictness + literal-flag unit coverage | Extend `test_catalog_models.py` table-driven |
| TEST-03 | Identity grammar/FE-BO/overload/version unit coverage | Extend `test_catalog_identity.py` + grammar tests |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Strict request/nested models | API / Backend (mcp_server models) | — | Trust boundary at Pydantic parse; no browser/CDN |
| Graph-key grammar registry | API / Backend (pure module) | — | Server-owned allowlist; no client widening |
| Deterministic UUIDv5 helpers | API / Backend (`catalog_identity.py`) | — | Pure, no I/O; namespace from config |
| Structured validation errors | API / Backend (model helper + MCP thin wrap) | — | Convert ValidationError once; tools stay thin |
| Side-effect precedence gate | API / Backend (MCP tool entry) | Service | Invalid requests never reach CatalogService |
| Neo4j writes / embeddings | Out of Phase 1 | Service/store | Phase 1 does not add write paths |
| Endpoint map / evidence / hashes | Deferred Phase 2 | — | Explicitly out of scope |
| Prepare/commit control plane | Deferred Phase 3A/3B | — | Out of scope |

## Project Constraints (from CLAUDE.md)

- Preserve every existing MCP tool name and legacy behavior; catalog tools names frozen (7); request contracts may break **explicitly**.
- Neo4j first; no multi-backend portability claim for catalog writes.
- Server-derived UUIDv5 only; `GRAPHITI_CATALOG_UUID_NAMESPACE` immutable deployment config.
- Never interpolate unvalidated client labels/properties into Cypher.
- Validate complete requests, limits, hashes, prefixes, nested refs, confidence, NaN/Inf, protected properties.
- Log batch IDs/counts only — never credentials, payloads, source text.
- Isolation: tests/writes only `oracle-catalog-tool-test`; never query/mutate `oracle-catalog-v2`.
- No canary execution; no deployment; no remote push/merge/tag.
- Preserve dirty-tree unrelated files (`.planning/config.json`, docker/k8s, `.codegraph/`, bulk `catalog/*`, `sample_catalog.json`).
- Python ≥3.10; Pydantic ≥2.11; Ruff line-length 100, single quotes; Pyright basic on mcp_server.
- Phase 2 blocked until Phase 1 unit gates pass.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pydantic | 2.11.7 (live `mcp_server`) | Strict models, `ConfigDict`, `Literal`, validators | Already foundational; CONT-* map directly |
| stdlib `uuid` | 3.10+ | UUIDv5 identity | Existing `catalog_identity.py` pattern |
| stdlib `re` / `hashlib` / `json` | 3.10+ | Grammar fullmatch + canonical SHA-256 | Existing pure helpers |
| pytest + pytest-asyncio | ≥8.3 / ≥0.24 | Unit gates | Existing mcp_server suite |
| Ruff | ≥0.7 | Format/lint | Project standard |
| Pyright | ≥1.1 | Type check (basic) | mcp_server `typeCheckingMode=basic` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typing / typing_extensions | stdlib / dep | `Literal`, `Annotated` if needed | Flag literals, version literals |
| unittest.mock | stdlib | Spy no-side-effect tests | Service-entry precedence without Neo4j |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Shared `CatalogStrictModel` base | Per-model `model_config` | Duplicates; easy to miss nested models — reject |
| Full grammar registry | Prefix-only + system_key field alone | Violates IDEN-04/05; FE/BO collision risk in key body — reject |
| Hand-rolled JSON schema | Pydantic v2 | Already in tree; ValidationError paths exist |
| New error package | Extend `CatalogErrorCode` | Existing enum is the registry |

**Installation:** none — no new packages. [VERIFIED: mcp_server env pydantic 2.11.7]

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none new)* | — | — | — | — | — | No installs in Phase 1 |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Live Code Inventory (ground truth)

### Request / nested models (all currently `BaseModel`, default extra=ignore)

| Module | Symbols | Notes |
|--------|---------|-------|
| `mcp_server/src/models/catalog_common.py` | `ENTITY_TYPE_PREFIXES` (15), `CATALOG_EDGE_TYPES` (16), `CatalogErrorCode` (17), limits, `validate_nested_json` | Missing System/DatabaseLink/SourceArtifact; missing 9 Phase-1 error codes |
| `mcp_server/src/models/catalog_entities.py` | `CatalogEntityItem`, `ResolveEntityRef`, `UpsertTypedEntitiesRequest`, `ResolveTypedEntitiesRequest`, `VerifyEntityRef`, `VerifyEdgeRef`, `VerifyCatalogBatchRequest` | Prefix-only graph_key; no system_key / identity_schema_version |
| `mcp_server/src/models/catalog_edges.py` | `CatalogEdgeItem`, `UpsertTypedEdgesRequest` | `strict_endpoints: bool = True`; prefix-only endpoint keys |
| `mcp_server/src/models/catalog_provenance.py` | `CatalogSourceItem`, `CatalogProvenanceEntityTarget`, `CatalogProvenanceEdgeTarget`, `UpsertProvenanceRequest` | Cartesian multi-source shape remains until Phase 2 EVID-* |
| `mcp_server/src/models/catalog_batch.py` | `NestedProvenancePayload`, `UpsertCatalogBatchRequest`, `GetCatalogIngestStatusRequest` | `atomic: Literal[True]` already; no identity_schema_version |
| `mcp_server/src/models/catalog_responses.py` | `CatalogItemResult`, write/resolve/verify/status/batch responses | Has `error_code`/`error_message`; no field_path/retryable/correlation_id on a shared error DTO |

### Identity helpers (`mcp_server/src/services/catalog_identity.py`)

| Function | Current material | Phase 1 target material |
|----------|------------------|-------------------------|
| `catalog_entity_uuid` | `group_id\|entity_type\|graph_key` | `group_id\|catalog-v2\|entity_type\|graph_key` |
| `catalog_edge_uuid` | `group_id\|edge_type\|edge_key` | `group_id\|catalog-v2\|edge_type\|edge_key` |
| `catalog_source_uuid` | `group_id\|Source\|source_key` | `group_id\|catalog-v2\|Source\|source_key` |
| `catalog_batch_uuid` | `group_id\|Batch\|batch_id` | `group_id\|catalog-v2\|Batch\|batch_id` |
| `catalog_mentions_uuid` | `group_id\|Mentions\|source_uuid\|entity_uuid` | `group_id\|catalog-v2\|Mentions\|source_uuid\|entity_uuid` |
| *(future)* evidence / manifest / prepared-plan | absent | Same versioned pattern when Phase 2/3 introduce helpers — **declare constant `IDENTITY_SCHEMA_VERSION = 'catalog-v2'` now**; do not implement persistence |

Pure module today: no neo4j/embedder/llm/queue imports — preserve that invariant.

### Service / MCP surface

- `CatalogService` (`catalog_service.py`, ~4824 lines): stages identity → hash → coalesce → embed → schema → tx. Assumes pre-built Pydantic models. Call sites: `catalog_entity_uuid` / `catalog_edge_uuid` / etc.
- MCP tools (names frozen): `upsert_typed_entities`, `resolve_typed_entities`, `verify_catalog_batch`, `upsert_typed_edges`, `upsert_provenance`, `get_catalog_ingest_status`, `upsert_catalog_batch` in `graphiti_mcp_server.py`.
- Canary builders (`scripts/build_catalog_canary_requests.py`) emit **v1 keys** e.g. `TABLE::{table_id}` — offline only; Phase 1 must not execute canary; fixture regeneration is Phase 5/6, not Phase 1 product path.

### Tests / fixtures (blast radius)

| Path | Role | Phase 1 impact |
|------|------|----------------|
| `mcp_server/tests/test_catalog_models.py` (~1066) | Model/config allowlist tests; v1 keys `TABLE::HR.EMPLOYEES` | Heavy update + new strictness/grammar tables |
| `mcp_server/tests/test_catalog_identity.py` (~190) | UUID material goldens for v1 | **Must** change expected materials to catalog-v2; add FE/BO/overload |
| `mcp_server/tests/test_catalog_service.py` (~3707) | Service spies, atomic, gates | Fixtures using graph keys / UUID expectations need v2 keys; no new write path |
| `mcp_server/tests/test_catalog_store_unit.py` | Store unit | Key/UUID fixture updates only if assertions pin identity |
| `mcp_server/tests/test_catalog_neo4j_int.py` | Live Neo4j; `GROUP=oracle-catalog-tool-test`, forbids v2 group | Optional/skip; never touch `oracle-catalog-v2` |
| `mcp_server/tests/test_catalog_canary_scripts.py` | Offline canary builder/runner unit | **Baseline fail (Phase 0)** — do not repair unless Phase 1 code forces it; never run live canary |

### Phase 0 constraints consumed

- `00-COMPATIBILITY-POLICY.md`: tool name freeze; explicit catalog-v1 break; golden import ban for hardened tests.
- `00-ISOLATION-POLICY.md`: `oracle-catalog-tool-test` only; canary ban; dirty exclude list; remote ban.
- `00-baseline-checks.json`: 319 catalog unit pass + 8 canary-script fails; ruff/pyright pass; neo4j int skip.
- `00-PHASE0-GATE.md`: `ready_for_phase_1=true`.

## Architecture Patterns

### System Architecture Diagram

```text
Client / Agent
    │  MCP tool call (7 catalog tool names frozen)
    ▼
MCP thin wrapper (graphiti_mcp_server.py)
    │  model_validate(payload)  ──► ValidationError
    │         │                         │
    │         │                         ▼
    │         │              to_catalog_validation_error()
    │         │              (code, message, field_path,
    │         │               retryable, correlation_id)
    │         │                         │
    │         │                         └──► safe structured response
    │         │                              (NO service call)
    ▼
CatalogStrictModel tree
  - identity_schema_version == 'catalog-v2'
  - system_key ∈ {FE,BO,COMMON}
  - Literal[True] flags
  - grammar registry fullmatch per entity_type
    │
    ▼
CatalogService (existing) ── only after valid model
    identity helpers (versioned UUIDv5)
    → embed → schema → tx   (unchanged orchestration; no new write API)
```

### Recommended Project Structure (minimal split)

```text
mcp_server/src/models/
├── catalog_common.py          # allowlists, limits, CatalogErrorCode (+9 codes),
│                              # SYSTEM_KEYS, IDENTITY_SCHEMA_VERSION,
│                              # CatalogStrictModel base
├── catalog_graph_key.py       # NEW: per-type grammar registry + validate_graph_key()
├── catalog_entities.py        # inherit strict base; system scope; grammar hooks
├── catalog_edges.py           # Literal[True] strict_endpoints; grammar on endpoints
├── catalog_provenance.py      # strict base; preserve source bytes
├── catalog_batch.py           # identity_schema_version + system_key on domain batch
├── catalog_responses.py       # optional CatalogStructuredError DTO (safe fields)
└── ...

mcp_server/src/services/
├── catalog_identity.py        # versioned UUID material; pure; no I/O
├── catalog_service.py         # call-site only if helper signatures change
└── catalog_store.py           # NO Phase 1 write-path changes

mcp_server/tests/
├── test_catalog_models.py     # CONT-* + grammar rejection tables
├── test_catalog_identity.py   # IDEN-* UUID/FE-BO/overload/version
├── test_catalog_service.py    # no-side-effect spy on invalid input only as needed
└── (no canary execution)
```

**Module split recommendation (discretion locked):**

1. `CatalogStrictModel` + constants + error codes stay in `catalog_common.py` (already the shared hub).
2. New pure `catalog_graph_key.py` for grammar only — keeps `catalog_common.py` from growing regex sprawl and avoids coupling grammar to service.
3. Safe error conversion: one function `catalog_validation_error_to_structured(exc, correlation_id=...)` in `catalog_common.py` or tiny `catalog_errors.py`; MCP wrappers call it. Prefer **models/common helper**, not duplicated per tool.

### Pattern 1: Shared strict base

**What:** Single base for every request and nested request model.
**When:** All catalog request models in Phase 1.

```python
# Source: Pydantic v2 ConfigDict docs + project pattern
from pydantic import BaseModel, ConfigDict

class CatalogStrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
```

Every of: `CatalogEntityItem`, `CatalogEdgeItem`, `CatalogSourceItem`, targets, resolve/verify refs, all `*Request` and nested batch provenance — inherit this. Response models may stay non-strict (server-built).

### Pattern 2: Literal flags

```python
from typing import Literal

strict_endpoints: Literal[True] = True
atomic: Literal[True] = True
identity_schema_version: Literal['catalog-v2']
system_key: Literal['FE', 'BO', 'COMMON']
```

Reject `false` / wrong version at validation time (CONT-05/06, IDEN-01/02).

### Pattern 3: Graph-key grammar registry

**Delimiter recommendation (discretion):**

- Type prefix: existing `TYPE::` (keep)
- System scope: next segment `FE|BO|COMMON` then `::`
- Qualifier: `.`-joined uppercase Oracle identifiers `[A-Z][A-Z0-9_$#]*` (Oracle-ish; fail-closed)
- Overload discriminator for Procedure/Function: final segment after name, using stable form `name(args_sig)` **or** `#overload_id` — **recommend** `#` + non-empty `[A-Za-z0-9_$,#()]+` to avoid `.` ambiguity in signatures

Canonical examples (locked by roadmap/CONTEXT):

```text
TABLE::FE::<DATABASE>.<SCHEMA>.<TABLE>
TABLE::BO::<DATABASE>.<SCHEMA>.<TABLE>
PACKAGE::FE::<DATABASE>.<SCHEMA>.<PACKAGE>
PROCEDURE::BO::<DATABASE>.<SCHEMA>.<PACKAGE>.<PROC>#<OVERLOAD>
FUNCTION::FE::<DATABASE>.<SCHEMA>.<PACKAGE>.<FN>#<OVERLOAD>
SYSTEM::FE::<SYSTEM_NAME>
DATABASE::FE::<DATABASE>
SCHEMA::FE::<DATABASE>.<SCHEMA>
COLUMN::FE::<DATABASE>.<SCHEMA>.<TABLE>.<COLUMN>
DBLINK::FE::<DATABASE>.<LINK_NAME>
SOURCE::FE::<ARTIFACT_KEY>          # SourceArtifact
DOC::FE::<DATABASE>.<DOC_ID>        # DictionaryDocument (keep DOC:: prefix)
```

**Per-type grammar table (recommended authority):**

| entity_type | prefix | body grammar (after `PREFIX::{SYSTEM}::`) |
|-------------|--------|-------------------------------------------|
| System | `SYSTEM::` | `<NAME>` |
| Database | `DATABASE::` | `<DB>` |
| DictionaryDocument | `DOC::` | `<DB>.<DOC>` |
| Schema | `SCHEMA::` | `<DB>.<SCHEMA>` |
| Table | `TABLE::` | `<DB>.<SCHEMA>.<TABLE>` |
| View | `VIEW::` | `<DB>.<SCHEMA>.<VIEW>` |
| MaterializedView | `MVIEW::` | `<DB>.<SCHEMA>.<MVIEW>` |
| Column | `COLUMN::` | `<DB>.<SCHEMA>.<TABLE>.<COLUMN>` |
| Constraint | `CONSTRAINT::` | `<DB>.<SCHEMA>.<CONSTRAINT>` |
| Index | `INDEX::` | `<DB>.<SCHEMA>.<INDEX>` |
| Package | `PACKAGE::` | `<DB>.<SCHEMA>.<PACKAGE>` |
| Procedure | `PROCEDURE::` | `<DB>.<SCHEMA>.(<PACKAGE>.)?<PROC>#<OVERLOAD>` |
| Function | `FUNCTION::` | `<DB>.<SCHEMA>.(<PACKAGE>.)?<FN>#<OVERLOAD>` |
| Trigger | `TRIGGER::` | `<DB>.<SCHEMA>.<TRIGGER>` |
| Sequence | `SEQUENCE::` | `<DB>.<SCHEMA>.<SEQUENCE>` |
| Synonym | `SYNONYM::` | `<DB>.<SCHEMA>.<SYNONYM>` |
| DatabaseLink | `DBLINK::` | `<DB>.<LINK>` |
| SourceArtifact | `SOURCE::` | `<ARTIFACT_KEY>` (bounded, no spaces; allow `._-/#`) |

Rules:

- `SYSTEM_KEY` in key **must equal** request `system_key` (mismatched → `invalid_system_key` or grammar error with field_path).
- Nested endpoint refs (edge source/target, resolve refs, provenance targets) must fullmatch the same registry for their declared type.
- Reject v1 keys (`TABLE::HR.EMPLOYEES`) with explicit validation error — **no auto-rewrite**.

### Pattern 4: Versioned UUID material

```python
IDENTITY_SCHEMA_VERSION = 'catalog-v2'

def catalog_entity_uuid(namespace, group_id, entity_type, graph_key) -> str:
    name = f'{group_id}|{IDENTITY_SCHEMA_VERSION}|{entity_type}|{graph_key}'
    return str(uuid.uuid5(namespace, name))
```

Same insertion of `|catalog-v2|` after `group_id` for edge/source/batch/mentions. Tests pin exact uuid5 strings.

### Pattern 5: Validation-before-side-effects

MCP tool order (must remain / be enforced):

1. Parse+validate full request model (`model_validate`)
2. On failure → structured error; return (zero service calls)
3. On success → `CatalogService.*`

Service-level: grammar/system/version already enforced by model; service keeps content-hash and runtime gates. Do **not** open embed/schema/tx before model validation completes.

### Pattern 6: Safe structured errors

Extend `CatalogErrorCode` with (CONT-08):

- `unsupported_identity_schema`
- `invalid_system_key`
- `edge_endpoint_pair_not_allowed` (registry only in Phase 1; enforcement map = Phase 2)
- `prepared_plan_not_found`
- `prepared_plan_expired`
- `prepared_plan_conflict`
- `prepared_plan_already_consumed`
- `manifest_mismatch`
- `provenance_link_conflict`

Shared response shape (SAFE-08):

```python
class CatalogStructuredError(CatalogStrictModel):
    code: CatalogErrorCode
    message: str = Field(..., max_length=512)
    field_path: str | None = None
    retryable: bool = False
    correlation_id: str  # uuid4 transport id; not identity authority
```

Validation errors: `retryable=False`. Never put `str(exc)` raw stack, payload, or source text into `message`.

Precedence: schema/extra/version/system/grammar → then feature/namespace/backend gates inside service.

### Anti-Patterns to Avoid

- **Prefix-only checks** (`startswith('TABLE::')`) as sole validation — violates IDEN-04.
- **Defaulting missing ownership to COMMON** — violates IDEN-03.
- **Returning `v.strip()`** from hash-bearing validators — violates CONT-04.
- **Accepting `strict_endpoints=false`** as soft mode — no alternate implementation exists.
- **Silent v1→v2 re-key** in service or builder during Phase 1 tests — violates IDEN-12/13.
- **Implementing endpoint map / evidence / request hash / prepare** in this phase — couples to Phase 2/3 and expands blast radius.
- **Editing canary scripts to pass baseline** as Phase 1 success — Phase 0 records those fails; Phase 1 gate is focused unit tests, not canary repair.
- **Touching `oracle-catalog-v2` or running canary** — hard isolation ban.
- **Broad CatalogService rewrite** — only identity call-site/material changes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unknown field rejection | Custom dict walkers | Pydantic `extra='forbid'` | Nested loc paths free |
| UUID identity | Caller UUID / uuid4 | `uuid.uuid5` + fixed namespace | Determinism + SAFE-05 |
| Graph key parse | Ad-hoc split without registry | Compiled `re.fullmatch` per type | Complete grammar, one authority |
| Error envelopes | Free-form exception strings | `CatalogErrorCode` + structured DTO | SAFE-07/08 |
| Canonical hashing | Custom serializers now | Existing `canonical_sha256` | Phase 2 freezes coverage; don't change recipe except as forced by new required fields |

**Key insight:** Phase 1 is contract+identity pure logic. Complexity lives in the grammar table and test matrix, not in new infrastructure.

## Runtime State Inventory

> Not a rename of external systems; identity **material** change is deliberate catalog-v2 break. No live group migration.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Historical `oracle-catalog-v2` ACCEPT_TAB commit (offline inventory only) | **None** — never query/mutate; do not migrate |
| Live service config | Catalog UUID namespace env `GRAPHITI_CATALOG_UUID_NAMESPACE` | Code continues to read it; do not rotate |
| OS-registered state | None for catalog identity | None — verified N/A |
| Secrets/env vars | Namespace UUID, Neo4j creds, API keys | Unchanged; never log |
| Build artifacts | Canary fixtures under `catalog/` (dirty/untracked bulk) | Offline historical; do not execute; do not commit bulk dumps |

**Nothing found requiring data migration in Phase 1.** UUID material change intentionally invalidates v1 graph identities for new writes only after later phases enable them; Phase 1 ships no new write path and no live rewrite.

## Common Pitfalls

### Pitfall 1: Nested models still allow extra
**What goes wrong:** Top-level forbid but `CatalogEntityItem` still ignores typos.
**Why:** Each model needs the strict base; nested classes don't inherit config from parent fields automatically unless they subclass the base.
**How to avoid:** Grep `class X(BaseModel)` under catalog models; all request/nested must be `CatalogStrictModel`.
**Warning signs:** Test with `{"entites": ...}` typo still passes.

### Pitfall 2: `strip()` mutates hash inputs
**What goes wrong:** Validators return stripped strings; hashes diverge from client bytes.
**How to avoid:** Emptiness check via `v.strip()` but **return original `v`**; add CONT-04 tests with trailing spaces where non-empty.

### Pitfall 3: Updating UUID helpers without updating tests/fixtures
**What goes wrong:** Mass test failure; temptation to add compatibility shims.
**How to avoid:** Treat identity test goldens as intentional break; update expected uuid5 strings; no dual-version helper.

### Pitfall 4: Coupling Phase 1 to endpoint map / evidence
**What goes wrong:** Phase 1 PR grows into Phase 2; gate never closes.
**How to avoid:** Add error **codes** only for future use; do not implement map or `CatalogEvidenceLink` persistence.

### Pitfall 5: Procedure overload collapse
**What goes wrong:** Grammar allows optional overload → two overloads same key.
**How to avoid:** Overload segment **required** for Procedure/Function; table tests with two overload IDs.

### Pitfall 6: COMMON as fallback
**What goes wrong:** Missing system_key coerced to COMMON.
**How to avoid:** Required field; no default; unknown value → `invalid_system_key`.

### Pitfall 7: Service spies still hit on ValidationError
**What goes wrong:** Tool constructs partial objects or calls service before validate.
**How to avoid:** MCP path: validate first; unit-test with mocked service asserting `assert_not_called` on invalid payload.

### Pitfall 8: Repairing Phase 0 canary baseline in Phase 1
**What goes wrong:** Scope creep; Windows CRLF noise.
**How to avoid:** Focused gate excludes `test_catalog_canary_scripts.py` unless a Phase 1 change directly breaks import of production modules (then minimal fix only).

## Code Examples

### Strict model + version fields

```python
# Source: live catalog_batch.py pattern + Phase 1 decisions
from typing import Literal
from pydantic import Field
from models.catalog_common import CatalogStrictModel, IDENTITY_SCHEMA_VERSION

class UpsertTypedEntitiesRequest(CatalogStrictModel):
    identity_schema_version: Literal['catalog-v2']
    system_key: Literal['FE', 'BO', 'COMMON']
    group_id: str = Field(..., min_length=1)
    batch_id: str
    entities: list[CatalogEntityItem]
    dry_run: bool = False
    atomic: Literal[True] = True
```

### Grammar validation hook

```python
# Source: recommended catalog_graph_key.py
from models.catalog_graph_key import validate_entity_graph_key

@model_validator(mode='after')
def _graph_key_grammar(self) -> Self:
    validate_entity_graph_key(
        entity_type=self.entity_type,
        graph_key=self.graph_key,
        system_key=self.system_key,  # from parent or item field — see Open Questions
    )
    return self
```

### Versioned UUID

```python
# Source: extend catalog_identity.py
def catalog_entity_uuid(namespace: uuid.UUID, group_id: str, entity_type: str, graph_key: str) -> str:
    return str(
        uuid.uuid5(
            namespace,
            f'{group_id}|catalog-v2|{entity_type}|{graph_key}',
        )
    )
```

### No-side-effect spy sketch

```python
# Source: pytest + unittest.mock pattern used in test_catalog_service.py
@pytest.mark.asyncio
async def test_invalid_identity_schema_never_touches_store(mock_store, mock_embedder):
    with pytest.raises(ValidationError):
        UpsertTypedEntitiesRequest.model_validate({..., 'identity_schema_version': 'catalog-v1'})
    mock_store.assert_not_called()
    mock_embedder.assert_not_called()
```

## State of the Art

| Old Approach (v1.0 shipped) | Current Approach (v1.1 Phase 1) | When Changed | Impact |
|-----------------------------|----------------------------------|--------------|--------|
| `extra` default ignore | `extra='forbid'` strict base | Phase 1 | Typos fail closed |
| Prefix-only graph keys | Full per-type grammar + system scope | Phase 1 | FE/BO collision-free |
| UUID `group\|type\|key` | UUID `group\|catalog-v2\|type\|key` | Phase 1 | Intentional identity break |
| `strict_endpoints: bool` | `Literal[True]` | Phase 1 | No false mode |
| 15 entity types | 18 (+System, DatabaseLink, SourceArtifact) | Phase 1 | Allowlist only |
| Cartesian provenance | Deferred Phase 2 replacement | Phase 2 | Do not redesign in Phase 1 |

**Deprecated/outdated:**

- catalog-v1 graph keys / UUID material / ACCEPT_TAB goldens as validity oracles for hardened v2.
- Soft boolean flags with no alternate implementation.

## Migration Blast Radius (and how to contain it)

| Area | Blast | Containment |
|------|-------|-------------|
| `catalog_identity.py` helpers | All UUID assertions in unit/service/store/int tests | Update goldens; no dual-write compatibility layer |
| Model constructors in tests | Fixtures missing new required fields | Shared fixture helpers `_entity_kwargs()` gain `identity_schema_version` / `system_key` / v2 keys |
| Canary builder scripts | Emit v1 keys | **Do not run**; offline regeneration later (Phase 5/6); Phase 1 may leave scripts failing baseline as recorded |
| Live Neo4j data | Old keys remain in historical group | Never migrate; never query `oracle-catalog-v2` |
| Phase 2 hash coverage | New required fields enter canonical payloads | Phase 1 may add fields to models; **do not freeze** `request_sha256` recipe until Phase 2 |
| Service orchestration | Minimal | Only if helper signatures change (prefer keep signatures; change material only) |

**Avoid Phase 2 coupling:**

- Do not implement endpoint pair map (EDGE-*).
- Do not implement `CatalogEvidenceLink` or remove Cartesian provenance yet (EVID-*).
- Do not implement prepare/commit/manifest.
- Do not change `canonical_sha256` algorithm.
- Adding error codes for future phases is OK; implementing their emitters is not required beyond validation codes used now (`unsupported_identity_schema`, `invalid_system_key`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Oracle identifier class `[A-Z][A-Z0-9_$#]*` is acceptable for grammar segments | Grammar | Too strict/loose for real catalog extracts — adjust regex in same module if builders need more later |
| A2 | Overload discriminator uses `#<token>` suffix | Grammar / IDEN-06 | Alternate `(sig)` form may be preferred by Oracle tools — change registry only, keep tests |
| A3 | `system_key` lives on **request shell** and is imposed on all nested keys (not repeated per entity) unless entity carries optional override equal to shell | Ownership | If per-entity system needed in one batch, model must add per-item `system_key`; recommend shell-level for Phase 1 minimalism |
| A4 | Response models stay non-strict (`extra` default) | Strict base | Low risk; server-built |
| A5 | Phase 1 focused gate excludes live Neo4j and canary-script suite | Validation | If CI runs full suite, baseline canary fails remain known noise |

**Conservative defaults:** A3 shell-level `system_key`; A2 `#overload`; no per-item system override in Phase 1.

## Open Questions (RESOLVED)

1. **Per-item vs request-level `system_key`**
   - **Resolved:** request-level only for Phase 1. Every nested domain key must match the shell scope. Mixed FE+BO content uses separate requests in the same `group_id`; no per-item override.

2. **Where `system_key` attaches on resolve/verify read paths**
   - **Resolved:** require `identity_schema_version` and `system_key` on resolve/verify requests whenever graph keys are supplied, enabling one grammar/scope check.

3. **Edge key grammar**
   - **Resolved:** Phase 1 fully validates endpoint graph keys; `edge_key` remains a bounded non-empty string. Phase 2 owns endpoint topology and any authoritative edge-key refinement.

4. **SourceArtifact vs provenance `source_key`**
   - **Resolved:** `SourceArtifact` entity keys use `SOURCE::...`; the current provenance `source_key` remains a separate catalog-v2 identity input until Phase 2 freezes the evidence contract.

5. **Procedure/Function overload token**
   - **Resolved:** require a final `#<OVERLOAD>` discriminator for both package and standalone Procedure/Function keys. Empty or missing discriminators fail grammar validation.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | ≥3.10 | — |
| Pydantic | models | ✓ | 2.11.7 | — |
| pytest | unit gate | ✓ | project pin | — |
| Ruff | lint gate | ✓ (Phase 0 pass) | project | — |
| Pyright | type gate | ✓ (Phase 0 pass) | project | — |
| Neo4j | live int | optional | 5.26+ | **skip** Phase 1 (unit only) |
| Canary runner | forbidden | N/A | — | never invoke |

**Missing dependencies with no fallback:** none for Phase 1 unit work.

**Missing dependencies with fallback:** Neo4j int → skip.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (mcp_server) + pytest-asyncio `auto` |
| Config file | `mcp_server/pytest.ini` |
| Quick run command | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py -q --tb=line` |
| Full Phase 1 gate command | `cd mcp_server && uv run pytest tests/test_catalog_models.py tests/test_catalog_identity.py tests/test_catalog_service.py tests/test_catalog_store_unit.py -q --tb=line` |
| Lint | `cd mcp_server && uv run ruff check src/models/catalog_*.py src/services/catalog_identity.py tests/test_catalog_models.py tests/test_catalog_identity.py` |
| Types | `cd mcp_server && uv run pyright src/models src/services/catalog_identity.py` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| CONT-01..03 | extra forbid recursive + misspell | unit | `pytest tests/test_catalog_models.py -k "strict or extra or misspel" -q` | ❌ Wave 0 add |
| CONT-04 | raw bytes preserved | unit | `pytest tests/test_catalog_models.py -k "preserve or reference_time or trailing" -q` | ⚠️ partial (`test_catalog_source_item_preserves_exact_reference_time`) |
| CONT-05 | strict_endpoints false rejected | unit | `pytest tests/test_catalog_models.py -k "strict_endpoints" -q` | ❌ Wave 0 add |
| CONT-06 | atomic false rejected (all write reqs) | unit | `pytest tests/test_catalog_models.py -k "atomic" -q` | ⚠️ batch only exists |
| CONT-07 / SAFE | invalid never calls store/embed | unit spy | `pytest tests/test_catalog_service.py -k "no_side_effect or gated or invalid_identity" -q` | ❌ Wave 0 add focused |
| CONT-08 | new error codes present | unit | `pytest tests/test_catalog_models.py -k "error_code" -q` | ⚠️ extend existing |
| IDEN-01..03 | version + system_key | unit | `pytest tests/test_catalog_models.py -k "identity_schema or system_key" -q` | ❌ Wave 0 add |
| IDEN-04..06,09 | full grammar matrix 18 types | unit | `pytest tests/test_catalog_models.py -k "grammar" -q` | ❌ Wave 0 add |
| IDEN-07,10..12 | FE/BO UUID + version material + v1 reject | unit | `pytest tests/test_catalog_identity.py -q` | ⚠️ rewrite goldens |
| IDEN-13 | no ACCEPT_TAB as v2 golden | unit/policy | assert tests do not import historical SHA as valid v2 | ❌ add guard test |
| SAFE-05 | no caller uuid authority | unit | existing `test_identity_functions_do_not_accept_caller_uuid_authority` | ✅ update if sigs change |
| SAFE-08 | structured error shape | unit | `pytest tests/test_catalog_models.py -k "structured_error" -q` | ❌ Wave 0 add |
| TEST-01 | aggregate strictness | unit | models suite | ❌ |
| TEST-03 | aggregate identity | unit | identity suite | ❌ |

### Sampling Rate

- **Per task commit:** quick models+identity command above
- **Per wave merge:** full Phase 1 gate + ruff + pyright scoped
- **Phase gate:** full Phase 1 gate green; compare to Phase 0 baseline — canary-script fails may remain; must not newly fail previously passing model/identity/service/store unit tests without intentional golden updates

### Baseline comparison protocol

1. Record Phase 1 gate exit codes separately from `test_catalog_canary_scripts.py`.
2. Do not reclassify Phase 0 canary fails as Phase 1 regressions.
3. Any new fail in `test_catalog_models/identity/service/store_unit` after intentional updates must be fixed before Phase 2.
4. Ruff/pyright scoped commands must stay pass (Phase 0 baseline pass).

### Wave 0 Gaps

- [ ] Table-driven strict/extra/misspell tests for every nested request model
- [ ] `strict_endpoints=false` / `atomic=false` rejection tests on all write requests
- [ ] Grammar positive/negative matrix for all 18 entity types
- [ ] FE vs BO same Oracle name → different graph_key + UUID
- [ ] Procedure/Function overload non-collapse
- [ ] UUID material `\|catalog-v2\|` goldens
- [ ] catalog-v1 key rejection (no rewrite)
- [ ] Structured error field_path/retryable/correlation_id
- [ ] No-side-effect spy: invalid schema/system never touches store/embed/schema/tx
- [ ] Shared fixture helpers updated to v2 keys + required fields
- [ ] Phase 1 gate report artifact path (planner should require `01-PHASE1-GATE.md` or JSON ledger)

*(Framework install: none — already present)*

### Phase 2 hard gate (exit criteria for planner)

Phase 2 planning/execution **must not start** until:

1. Focused unit gate (models + identity + required service spy tests) is green.
2. Ruff + Pyright scoped catalog surface is green.
3. No new write/control-plane path was introduced in Phase 1.
4. `canary_executed=false` and `oracle_catalog_v2_queried=false` remain true.
5. Error registry contains CONT-08 codes; identity helpers emit catalog-v2 material; strict base covers all request/nested models.
6. Written Phase 1 gate note records pass/fail/skip truthfully (mirror Phase 0 style).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | MCP auth out of scope |
| V3 Session Management | no | — |
| V4 Access Control | partial | `group_id` isolation; test group only |
| V5 Input Validation | **yes** | Pydantic strict models, allowlists, grammar fullmatch, bounds |
| V6 Cryptography | partial | UUIDv5 identity (not secrecy); SHA-256 content hashes existing |

### Known Threat Patterns for catalog MCP

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher label/property injection | Tampering | Fixed allowlists; never interpolate client labels |
| Unknown field smuggling / mass assignment | Tampering | `extra='forbid'` recursive |
| Identity spoof via caller UUID | Spoofing | No caller UUID authority (SAFE-05) |
| Cross-group read/write | Elevation | `group_id` on every op; tests only `oracle-catalog-tool-test` |
| Log leakage of catalog source | Info disclosure | Bounded messages; no payload/source in logs |
| Silent identity migration | Tampering | Reject v1; no rewrite (IDEN-12) |

## Sources

### Primary (HIGH confidence)

- Live source: `mcp_server/src/models/catalog_{common,entities,edges,provenance,batch,responses}.py`
- Live source: `mcp_server/src/services/catalog_identity.py`, `catalog_service.py` (header + UUID call sites)
- Live tests: `mcp_server/tests/test_catalog_{models,identity,service,store_unit,neo4j_int,canary_scripts}.py`
- Phase 0: `00-COMPATIBILITY-POLICY.md`, `00-ISOLATION-POLICY.md`, `00-baseline-checks.json`, `00-PHASE0-GATE.md`
- Phase 1 CONTEXT + ROADMAP + REQUIREMENTS + `graphiti_mcp_pre_canary_roadmap_en.md`
- Runtime: `pydantic==2.11.7` via mcp_server environment

### Secondary (MEDIUM confidence)

- Canary builder key shapes: `scripts/build_catalog_canary_requests.py` (`TABLE::{table_id}` v1 form)
- Pydantic v2 `ConfigDict(extra='forbid')` behavior from installed v2.11 semantics [ASSUMED from installed major; confirmed via project usage patterns]

### Tertiary (LOW confidence)

- Exact Oracle identifier character class details (A1) — adjustable without design change

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; versions verified in tree/env
- Architecture: HIGH — live modules mapped; decisions locked in CONTEXT
- Pitfalls: HIGH — derived from live gaps (extra ignore, prefix-only, unversioned UUID, bool flags)
- Grammar regex details: MEDIUM — examples locked; token class assumed (A1/A2)

**Research date:** 2026-07-18
**Valid until:** 2026-08-17 (30 days; contracts stable unless Phase 1 execution mutates surface)
