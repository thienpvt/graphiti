# Stack Research

**Domain:** Catalog-v2 pre-canary hardening (deterministic MCP catalog layer)
**Researched:** 2026-07-17
**Confidence:** HIGH
**Milestone:** v1.1 — subsequent to shipped v1.0 typed primitives

## Verdict

**Add zero new runtime dependencies.** Harden with already-installed Pydantic 2.11.x, Neo4j 5.26+/driver 5.28.x, stdlib (`uuid`, `hashlib`, `hmac`, `secrets`, `json`, `datetime`, `re`, `asyncio`), and existing `CatalogNeo4jStore` / `CatalogService` / FastMCP surface.

v1.0 already delivered seven tools, UUIDv5, SHA-256, allowlists, embeddings-before-tx, dry-run/atomic, provenance, and `CatalogIngestBatch` status. v1.1 is **contract and control-plane hardening**, not a stack rewrite.

## Recommended Stack

### Core Technologies (unchanged — reuse)

| Technology | Version (verified in worktree) | Purpose | Why for v1.1 |
|------------|--------------------------------|---------|--------------|
| Python | `>=3.10,<4` (runtime 3.10.20 checked) | Runtime | Keep 3.10 min; no 3.11-only APIs (`enum.StrEnum` already polyfilled) |
| `uv` + `mcp_server/uv.lock` | lockfile-driven | Install truth | Do not hand-edit versions; no new deps → no lock churn |
| `mcp` (FastMCP) | **1.27.2** (`>=1.27.2,<2`) | Tool registration | Additive tools only; same `@mcp.tool()` pattern |
| `graphiti-core` | **0.29.2** | Embedder + search interop | Catalog writes stay off `EntityNode.save` / queue / LLM |
| `neo4j` driver | **5.28.1** (req `>=5.26.0`) | Async Bolt + real txs | Control-plane + domain writes via `tx.run` |
| Neo4j server | **5.26+** (compose `neo4j:5.26.0`) | Graph storage | Composite UNIQUE, MERGE, parameterized Cypher only |
| Pydantic | **2.11.7** (req `>=2.11.5`) | Strict recursive contracts | `ConfigDict(extra='forbid')` on **every** nested model |
| `pydantic-settings` | **2.10.1** | CatalogConfig gates | Split read/write flags without new config libs |
| `openai` (embedder transport) | **2.43.0** range | Embeddings only | Still no LLM extraction for catalog tools |
| `pyyaml` | **6.0.3** | YAML config | Existing `${VAR}` expansion |

### Supporting Libraries (already present — reuse)

| Library | Version | Purpose | When for v1.1 |
|---------|---------|---------|---------------|
| stdlib `uuid` | 3.10 | UUIDv5 identities + FE/BO/COMMON name material | Extend identity strings; never caller UUID authority |
| stdlib `hashlib` | 3.10 | SHA-256 canonical audit | Combined batch/manifest hashes |
| stdlib `hmac` + `secrets` | 3.10 | Opaque prepare/commit tokens | `secrets.token_urlsafe(32)`; store **hash only**; `hmac.compare_digest` on verify |
| stdlib `json` | 3.10 | Canonical dumps + nested serialization | Existing `sort_keys=True, separators=(',', ':')` |
| stdlib `datetime` (UTC) | 3.10 | `expires_at`, `prepared_at`, `committed_at` | Bounded plan TTL; no external scheduler |
| `typing-extensions` | locked | TypedDict on <3.12 | Response shapes only if needed |
| `httpx` (dev) | **0.28.1** | MCP HTTP tests | Gate-split / tool-list tests |
| `tenacity` | via graphiti-core | LLM retries | **Do not** wrap catalog writes |

### Development Tools (unchanged)

| Tool | Locked | Purpose | Notes |
|------|--------|---------|-------|
| pytest | **9.0.3** | Unit/service/store/MCP/live | Markers: unit, integration, requires_neo4j |
| pytest-asyncio | **1.4.0** | Async fixtures | Existing patterns |
| pytest-timeout | **2.4.0** | Hang protection | Live Neo4j |
| pytest-xdist | dev group | Parallel **unit** only | Never parallelize shared-group Neo4j writes |
| ruff | **0.15.x** | Format/lint | line-length 100, single quotes |
| pyright | **1.1.408** | basic typecheck | mcp_server mode |
| faker | **40.x** | Optional noise | Prefer fixed fixtures for determinism |

## Exact Mechanisms for v1.1 Scope

### 1. Strict recursive Pydantic contracts

**Use (installed):**

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class CatalogStrictModel(BaseModel):
    model_config = ConfigDict(
        extra='forbid',          # reject unknown fields
        strict=True,             # no str→int / truthy coercion at trust boundary
        validate_assignment=True # immutable-feeling flags stay valid after setattr
        # frozen=True optional for pure value objects (identity refs, endpoint maps)
    )
```

**Contract note (v1.1):** Catalog-v2 **intentionally breaks** seven deterministic request identity/provenance/hash contracts where required. Preserve MCP **tool names** and legacy semantic tools; do **not** claim catalog-v1 request payloads remain accepted. Capabilities work whenever server initialization succeeds, even if catalog writes are disabled.

**Critical fact (verified against Pydantic docs + local 2.11.7):**
- `extra='forbid'` is **per-model**. Outer forbid does **not** cascade into nested models.
- `revalidate_instances` also does **not** propagate to nested models.
- Every nested request model (`CatalogEntityItem`, edge items, provenance targets, prepare plan body, evidence links, manifest sections) must declare its own `model_config`.

**Current gap:** `mcp_server/src/models/catalog_*.py` use bare `BaseModel` (default `extra='ignore'`). v1.1 must set forbid/strict on the full tree and add unit tests for nested extras + type coercion.

**Immutable execution flags:** model `dry_run`, `atomic`, prepare/commit mode as `Literal[...]` (already used for batch `atomic: Literal[True]`) plus `validate_assignment=True` or `frozen=True` on request shells so post-parse mutation cannot flip gates.

**Do not add:** `pydantic[email]`, `pydantic-extra-types`, `jsonschema`, `marshmallow`, `cerberus`, `attrs`.

### 2. Catalog-v2 FE/BO system-scoped identities

**Use:** existing `catalog_identity.py` UUIDv5 helpers + stdlib `uuid.uuid5`.

**Pattern (extend, do not replace):**
- Keep configured `GRAPHITI_CATALOG_UUID_NAMESPACE` as sole namespace authority.
- Materialize system scope **inside the name string** before uuid5, e.g.  
  `group_id|entity_type|FE|graph_key`, `...|BO|...`, `...|COMMON|...`  
  (exact grammar is product decision; stack requirement is: scope is server-owned name material, never a second namespace UUID and never a client-supplied UUID).
- Edge / source / batch / evidence-link identities follow the same server-name composition.
- Visible graph_key grammar (prefix + system tag) is validation-layer only; identity remains uuid5 of composed name.

**Do not add:** `ulid`, `shortuuid`, `hashids`, custom base58 libs, caller UUID fields as authority.

### 3. Server-owned edge endpoint maps + capabilities + hashes

**Use:**
- Module-level `frozenset` / `dict[str, frozenset[tuple[str, str]]]` (or nested frozensets) in `catalog_common.py` / new `catalog_endpoint_map.py` — pure Python constants.
- Existing `canonical_sha256` for domain content + combined batch hash covering entities, edges, provenance, evidence, system scopes.
- Capabilities discovery: pure function returning a **fixed** Pydantic response (supported entity/edge types, endpoint map digest, limits, feature flags, protocol version). No reflection over Neo4j schema.

**Do not add:** dynamic ontology DB, GraphQL, OpenAPI codegen packages, Redis capability cache.

### 4. Restart-safe prepare / commit / discard control plane

**Storage primitive (already proven in v1.0):** non-`Entity` Neo4j label nodes with composite uniqueness.

| Concern | Mechanism | Why |
|---------|-----------|-----|
| Durable plan/status | New label e.g. `CatalogBatchPlan` (or extend `CatalogIngestBatch` with explicit lifecycle) | Same isolation pattern as `CatalogIngestBatch`; excluded from Graphiti entity search |
| Identity uniqueness | `CREATE CONSTRAINT ... IF NOT EXISTS FOR (n:Label) REQUIRE (n.uuid, n.group_id) IS UNIQUE` | Already used for Entity/RELATES_TO/Episodic/MENTIONS/CatalogIngestBatch; coexists with Graphiti RANGE indexes where single-prop UNIQUE does not |
| Upsert semantics | `MERGE (n:Label {uuid:$uuid, group_id:$group_id}) ON CREATE SET ... ON MATCH SET ...` selective properties | Neo4j docs: MERGE does not take free property maps; selective SET preserves fields; never `SET n = $map` |
| Concurrency | Claim row under uniqueness + status CAS (`FOREACH` guard like existing batch status) | MERGE alone ≠ uniqueness under races; constraint + conditional SET is the v1.0 pattern |
| Terminal immutability | Refuse overwrite of `committed` / hash mismatch → `batch_conflict` | Existing `already_committed` / `hash_conflict` guards |
| Bounded TTL | Store `expires_at` (UTC datetime); expire = status transition or delete in app logic on read/commit | Community Neo4j has **no** built-in property TTL without Enterprise/APOC jobs; app-enforced expiry is correct |
| Payload bound | Store **bounded immutable canonical catalog payload** server-side (restart-safe) so commit receives only a token — hashes/counts alone are **insufficient** | Approved contract: commit must rehydrate domain content from prepare snapshot; chunk non-Entity control nodes if needed |
| Manifest | Separate non-Entity node or properties on committed batch: exact entity/edge/evidence UUID lists as JSON **strings** (bounded) via existing `serialize_nested_json` | Neo4j properties are primitives; nested structures already stringified |

**Transactions (approved contract):**
- Prepare: control-plane write only — persist immutable plan + **full bounded canonical payload** (chunked non-Entity nodes OK); **no domain Entity writes**; **does NOT compute required embeddings**.
- Commit: load payload from plan → compute embeddings from stored payload **before** opening domain tx → **one Neo4j transaction** writes domain data + evidence + manifest + terminal batch status + plan terminal state where supported.
- Discard: write tx flips plan to discarded/expired; never domain delete of unrelated data.
- Failed domain write: full rollback of the commit domain/control unit; **separate post-rollback failure-status transaction allowed only for failure reporting**.

**Driver APIs to keep using:**
- `Neo4jDriver.transaction()` / session `execute_write` with `tx.run(cypher, **params)`
- `executor.execute_query` only for schema init / reads outside multi-statement atomicity
- Parameterized values only; labels from fixed server maps

**Do not add:** Redis/RQ/Celery for plans, SQLite sidecar, file-backed plan store, Kafka, temporal/workflow engines, APOC as required dependency, Neo4j Fabric.

### 5. Secure opaque prepare/commit tokens

**Use stdlib only:**

```python
import hashlib
import hmac
import secrets

def issue_plan_token() -> tuple[str, str]:
    """Return (token_plaintext_once, token_sha256_hex_to_store)."""
    token = secrets.token_urlsafe(32)  # ~43 chars, 256-bit entropy
    digest = hashlib.sha256(token.encode('ascii')).hexdigest()
    return token, digest

def verify_plan_token(presented: str, stored_digest_hex: str) -> bool:
    presented_digest = hashlib.sha256(presented.encode('ascii')).hexdigest()
    return hmac.compare_digest(presented_digest, stored_digest_hex)
```

**Rules:**
- Return plaintext token **once** on prepare response; persist only SHA-256 (or HMAC with server secret if multi-instance shared secret exists — default single-digest is enough when Neo4j is the sole store).
- Never log token plaintext or full plan payload.
- Constant-time compare always (`hmac.compare_digest`).
- Bind token to `(group_id, batch_uuid, request_sha256, expires_at)` server-side; ignore client identity claims.
- Optional: `hmac.new(server_secret, token, hashlib.sha256)` if operators inject a deploy secret; still no new packages (`hmac` is stdlib).

**Do not add:** `PyJWT` / `jose` / `itsdangerous` / `authlib` for plan tokens (overkill; no need for portable signed JWTs inside a Neo4j-bound control plane). No OAuth libraries.

### 6. Explicit evidence links (no Cartesian expansion)

**Use:** existing provenance path (Episodic + MENTIONS + fact attachment) + **explicit** link rows with server uuid5 (`catalog_mentions_uuid` pattern).

**Stack rule:** reject nested “all sources × all targets” expansion as the write shape. v1.0 `NestedProvenancePayload` already bounds `sources * targets`; v1.1 should prefer explicit `(source_key, target_ref)` lists and hash those links into the combined batch hash.

**Do not add:** graph algorithms packages, networkx for link expansion.

### 7. Read/write gate split

**Use:** extend `CatalogConfig` in `config/schema.py` with pydantic-settings / YAML:

| Flag | Default | Effect |
|------|---------|--------|
| `enabled` (existing) | `false` | Master write gate |
| `reads_enabled` (new, optional) | `true` when diagnostics needed | `resolve_*`, `verify_*`, `get_*_status`, capabilities |
| `writes_enabled` or keep `enabled` | `false` | All mutate/prepare/commit/discard/upsert |

Return existing structured codes (`feature_disabled`, `backend_unavailable`) — no new HTTP framework.

**Do not add:** feature-flag SaaS SDKs, LaunchDarkly, Unleash clients.

### 8. Pagination for verify/manifest reads

**Use:** request fields `limit` + `cursor`/`offset` with hard caps; Cypher `SKIP $skip LIMIT $limit` with **integer parameters** only (never string-concat limits). Default small pages; total counts via separate `count()` query or precomputed manifest counts.

**Do not add:** GraphQL cursor libs, elasticsearch for catalog admin reads.

### 9. Tests (dev stack only — already installed)

| Layer | Tool | Focus |
|-------|------|-------|
| Unit | pytest | recursive extra forbid, strict coercion, FE/BO identity vectors, endpoint map, hash coverage, token hash+compare, gate split |
| Service | pytest + mocks | prepare→commit→discard state machine, replay identical hash, conflict, expiry |
| Store | pytest + Neo4j | composite UNIQUE, MERGE guards, non-Entity labels absent from search |
| MCP | pytest + tool list | schema surface, read tools live when writes disabled |
| Concurrency | asyncio gather | single logical plan/domain object under concurrent prepare/commit |
| Security | unit | Cypher injection attempts on labels/props, token timing-safe path, no payload logging |
| Compatibility | existing MCP tests | seven v1 tools + semantic tools unchanged |

**Do not add:** hypothesis (optional later only if property tests requested), testcontainers (compose Neo4j already), factory_boy, tox, nox.

## Installation

```bash
# No new packages for v1.1 hardening.
cd mcp_server
uv sync --group dev

# Verify installed pins (example from this worktree)
uv run python -c "import pydantic,neo4j; from importlib.metadata import version; \
print(pydantic.VERSION, neo4j.__version__, version('mcp'), version('graphiti-core'))"
```

If a lock refresh is unavoidable for unrelated reasons, still **do not** introduce new direct dependencies for this milestone.

## Alternatives Considered

| Recommended | Alternative | When alternative might win | Why not now |
|-------------|-------------|----------------------------|-------------|
| Neo4j non-Entity plan nodes | Redis plan store | Multi-region ephemeral cache | Extra ops surface; breaks single-store restart story; not installed as required |
| `secrets` + SHA-256 digest | JWT (PyJWT) | Cross-service portable claims | Plan is bound to local Neo4j row; JWT adds key mgmt without benefit |
| Pydantic `extra='forbid'` tree | jsonschema draft validators | Non-Python clients share one schema file | Server already Pydantic; dual validators drift |
| App-enforced `expires_at` | APOC TTL / Enterprise TTL | Ops wants automatic background purge | APOC not a hard dep; Community TTL absent; explicit discard is enough pre-canary |
| Module frozenset endpoint map | DB-stored ontology | Frequent type additions by non-devs | Catalog types are fixed allowlists by design |
| Cypher `SKIP`/`LIMIT` | Application-only slicing after full MATCH | Tiny result sets | Manifests can be large; push bound to Neo4j |
| Extend `CatalogIngestBatch` | Second graph DB | Isolation fashion | Violates single Neo4j backend decision |

## What NOT to Use / NOT to Add

| Avoid | Why | Use instead |
|-------|-----|-------------|
| Any new runtime PyPI package for this milestone | YAGNI; lock/review cost; attack surface | Installed Pydantic, neo4j, stdlib |
| FalkorDB/Kuzu/Neptune catalog write path | Explicit non-goal; no portability claim | Neo4j gate + `backend_unavailable` |
| LLM / queue / `add_episode` for catalog-v2 | Breaks deterministic identity | Existing deterministic upserts |
| `EntityNode.save` / bulk SET-map for control plane | Label/property loss; search pollution | Dedicated store Cypher (v1.0 pattern) |
| Caller UUID as identity | Violates server authority | UUIDv5 only |
| MD5 / non-canonical hashes | Forbidden / unstable audit | SHA-256 lowercase 64 hex + canonical JSON |
| Interpolating client labels/property names into Cypher | Injection | Fixed allowlists → fixed Cypher fragments |
| `SET n = $map` / free property maps on MERGE | Wipes preserved fields; Neo4j MERGE map limits | Selective `SET n.prop = $prop` |
| Redis/Celery/RQ/Temporal for prepare state | New infra; dual-write failure modes | Neo4j plan nodes + TTL fields |
| PyJWT / OAuth / session middleware for plan tokens | Overkill inside MCP tool params | `secrets` + hashed token on plan node |
| APOC as required | Not guaranteed in target deployments | Pure Cypher + app logic |
| Automatic v1→v2 identity migration | Silent re-key risk | Explicit dual-read docs only; no code migration |
| Production canary / live `oracle-catalog-v2` writes | Out of scope | Tests only on `oracle-catalog-tool-test` |
| `clear_graph` / DROP CONSTRAINT repair | Data destruction / schema fights with Graphiti | CREATE IF NOT EXISTS only; fail closed on dup data |
| Hypothesis/property-based **framework** (unless later requested) | Extra dep | Table-driven exhaustive vectors |
| NetworkX / graph-tool | Not needed for endpoint maps | Dict/frozenset constants |

## Stack Patterns by Variant

**If only read diagnostics are needed in an environment:**
- `writes_enabled=false` (or `enabled=false`), keep resolve/verify/status/capabilities registered
- No prepare/commit code paths open txs that mutate domain labels

**If prepare/commit is enabled:**
- Require valid `uuid_namespace` (existing validator)
- Embeddings run at **commit** from stored prepare payload (not at prepare)
- Plan token required for commit/discard; hash compare constant-time
- Prepare stores full bounded payload (chunk if needed); not hashes-only

**If manifest exceeds property size comfort:**
- Store manifest as chunked non-Entity child nodes keyed by `(batch_uuid, chunk_index)` with composite uniqueness — still pure Neo4j, no object store
- Chunk oversized prepare payloads the same way; hashes/counts alone are not a valid prepare store

**If multi-instance MCP shares one Neo4j:**
- All plan state in Neo4j (already); optional shared HMAC secret via env for token digests
- No sticky sessions required

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pydantic **2.11.7** | Python 3.10+ | `ConfigDict`, `strict=True`, `extra='forbid'` verified locally |
| neo4j driver **5.28.1** | Neo4j server **5.26+** | Composite node/rel UNIQUE; async transactions |
| graphiti-core **0.29.2** | neo4j `>=5.26.0` | Catalog store bypasses fragile save paths intentionally |
| mcp **1.27.2** | pydantic v2 | Tool schema from function signatures / models |
| pytest **9** + pytest-asyncio **1.4** | Python 3.10 | Existing mcp_server dev group |

**Transaction limitations (document in operator notes, not “solved” by new libs):**
- Neo4j Community: no multi-DB XA; one database per driver config.
- Long prepare windows are **not** held open as Bolt transactions — durable plan node + later commit tx.
- Schema `CREATE CONSTRAINT` is auto-commit DDL; run before write traffic (existing `ensure_uuid_uniqueness_constraints`).
- Uniqueness constraint creation fails closed on pre-existing duplicate `(uuid, group_id)` — no automatic repair.

## Integration Points (code)

| Concern | Integration point |
|---------|-------------------|
| Strict models | `mcp_server/src/models/catalog_*.py` — shared `CatalogStrictModel` base |
| Identity scope | `services/catalog_identity.py` — extend name composition; keep pure |
| Endpoint map / capabilities | `models/catalog_common.py` (+ small map module); MCP read tool |
| Plan/manifest store | `services/catalog_store.py` — mirror `CatalogIngestBatch` helpers |
| Orchestration | `services/catalog_service.py` — prepare/commit/discard state machine |
| Config gates | `config/schema.py` `CatalogConfig` |
| MCP surface | `graphiti_mcp_server.py` `@mcp.tool` registrations |
| Tests | `mcp_server/tests/` — unit without Neo4j; `*_int` for live |

## Sources

- Local worktree pins: `mcp_server` uv env — pydantic **2.11.7**, neo4j **5.28.1**, graphiti-core **0.29.2**, mcp **1.27.2** (2026-07-17)
- Local verification: nested `extra='forbid'` requires per-model config; outer-only forbid allows nested extras (HIGH)
- [Pydantic ConfigDict](https://pydantic.dev/docs/validation/latest/api/pydantic/config/) — `extra`, `strict`, `frozen`, `validate_assignment`; non-propagation of some options (HIGH)
- [Neo4j 5 constraints syntax](https://neo4j.com/docs/cypher-manual/5/constraints/syntax/) — composite UNIQUE, `IF NOT EXISTS` (HIGH)
- [Neo4j 5 MERGE](https://neo4j.com/docs/cypher-manual/5/clauses/merge/) — no free property map on MERGE; constraints needed for concurrent uniqueness (HIGH)
- Python stdlib docs: `secrets.token_urlsafe`, `hmac.compare_digest`, `hashlib.sha256`, `uuid.uuid5` (HIGH)
- Existing implementation: `catalog_store.py` `CatalogIngestBatch` MERGE/claim/status guards; `catalog_identity.py` uuid5 + canonical SHA-256 (HIGH)
- Project constraints: `.planning/PROJECT.md` v1.1 scope; Neo4j-first; no production/canary (HIGH)

---
*Stack research for: Catalog-v2 pre-canary hardening*
*Researched: 2026-07-17*
*Replaces obsolete v1.0-oriented stack notes for this milestone*
