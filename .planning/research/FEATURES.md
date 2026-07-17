# Feature Research

**Domain:** Deterministic catalog MCP hardening (v1.1 Catalog-v2 Pre-Canary)
**Researched:** 2026-07-17
**Confidence:** HIGH

**Scope note:** v1.0 shipped seven deterministic Neo4j catalog tools (entity/edge upsert, entity resolve, batch verify, provenance, atomic batch, ingest status). This document covers only v1.1 hardening observable from MCP clients and operators. Do not re-specify shipped v1.0 behavior except as compatibility baseline.

## Feature Landscape

### Table Stakes (Operators and Agents Expect These)

Missing any of these makes the surface untrustworthy for a regenerated catalog-v2 canary.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Strict recursive request contracts | Agents emit partial/extra fields; silent accept corrupts identity | MEDIUM | `extra='forbid'` recursively on all catalog request models and nested items; unknown fields fail closed with `validation_error` before any Neo4j/embedder work |
| Immutable execution flags | Retry/replay must not reinterpret `dry_run`/`atomic` mid-plan | LOW | Flags are part of request identity; changing them on a prepared/committed batch returns conflict, never mutates plan semantics |
| Catalog-v2 FE/BO/COMMON identity grammar | FE and BO objects collide without visible isolation | MEDIUM | Graph keys and type grammar must deterministically separate FE, BO, COMMON; wrong-lane keys fail closed; no silent reinterpretation of v1 keys as v2 |
| Server-owned edge endpoint-pair maps | Client-supplied endpoint types alone cannot prevent illegal pairs | MEDIUM | Every allowlisted edge type has a finite source×target type map enforced before side effects; unknown/illegal pairs return structured errors |
| Authoritative combined batch hashes | Client-only hashes can omit nested content | MEDIUM | Server computes canonical SHA-256 over all domain content (entities, edges, provenance, flags as documented); optional client hash compared; mismatch = `content_hash_mismatch` / `batch_conflict` |
| Capabilities discovery | Agents must know limits, gates, identity grammar, endpoint maps without reading source | LOW | Read-only discovery response: enabled flags, limits, entity/edge allowlists, endpoint maps, protocol version, FE/BO grammar version — no secrets |
| Durable prepare / commit / discard | Multi-step agent ingest needs restart-safe plans without partial domain writes | HIGH | Prepare persists **bounded immutable canonical payload** + hashes (restart-safe; chunked non-Entity OK; hashes-only insufficient); commit receives **token only**, embeds from stored payload, applies plan; discard drops plan without domain mutation; identical-plan replay idempotent |
| Explicit evidence links (no Cartesian expansion) | Source×target product explodes and invents unproven links | MEDIUM | Provenance accepts only explicit `(source, target)` pairs or equivalent bounded links; reject implicit all-to-all; preserve deterministic source identity |
| Durable batch manifests | Post-commit audit cannot rely on client memory | HIGH | Committed batch stores exact entity/edge/provenance identity list + hashes under non-`Entity` labels; restart-safe; excluded from entity search/communities |
| Manifest-backed verification | Verify-by-batch-id without re-sending full payload | MEDIUM | `verify_catalog_batch` (or successor) can load expected set from durable manifest; report missing/wrong-type/endpoint/hash/provenance gaps |
| `resolve_typed_edges` | Operators need edge diagnostics symmetric to entity resolve | MEDIUM | Read-only: found state, UUID, type, endpoints, hash, embedding presence, duplicates, anomalies; never writes or embeds |
| Split read/write gates | Diagnostics must work while mutation is disabled | LOW | Writes gated by `catalog_upsert.enabled` (or write gate); resolve/verify/status/capabilities/manifest reads remain available under a read gate or always-on policy |
| Legacy tool compatibility | Existing automations must not break | MEDIUM | Seven v1 tools keep schemas and deterministic guarantees; additive tools/fields only; search interop and `group_id` isolation unchanged |
| Structured fail-closed errors | Operators need machine-actionable codes, not stack traces | LOW | Extend documented codes; never log full payloads/credentials/source text |
| Test-group isolation | Implementation must not touch live catalog groups | LOW | Tests only `oracle-catalog-tool-test`; no `oracle-catalog-v2` writes; no production/canary execution in this milestone |

### Differentiators (Trustworthy Catalog Behavior)

These distinguish a canary-ready administrative surface from generic graph write APIs.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Visible FE/BO lane separation | Agents and operators can tell front-end vs back-office catalog objects without out-of-band docs | MEDIUM | Grammar in keys/attributes is inspectable via resolve/manifest; wrong lane is a hard error, not a soft warning |
| Endpoint-pair authority on server | Schema integrity survives buggy agents and regenerated parsers | MEDIUM | Maps are server constants; capabilities expose them; clients cannot widen pairs |
| Immutable prepare-then-commit protocol | Agent crash mid-ingest cannot leave half-applied domain state for a prepared plan | HIGH | Prepare does not write domain entities/edges and does **not** embed; commit embeds then atomically writes domain+evidence+manifest+terminal statuses in one Neo4j tx where supported; discard non-destructive to domain |
| Exact evidence links | Provenance remains auditable and non-fabricating under concurrent writes | MEDIUM | Explicit links + ordered/CAS patterns already proven in v1.0; v1.1 forbids Cartesian expansion path in nested batch |
| Manifest as verification authority | Post-restart operators verify committed intent without replaying full request bodies | HIGH | Manifest hash must match commit-time plan hash; verify can assert completeness against manifest alone |
| Capabilities as contract surface | Multi-agent fleets pin behavior to server-advertised protocol/grammar versions | LOW | Version fields must change when maps/grammar/hash coverage change |
| Read diagnostics under write-disable | Safe production posture: inspect without enabling mutation | LOW | Operator can leave writes off, still resolve/verify/status/capabilities |
| Migration guidance without silent rekey | Catalog-v1 → v2 is explicit and operator-driven | LOW | Docs only: no automatic identity migration; changing namespace or grammar re-keys — never silent |

### Anti-Features (Seem Useful; Reject)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Silent unknown-field strip | "Be lenient with agents" | Hides schema drift; identity/hash diverge from client intent | Fail closed with field path in `validation_error` |
| Auto FE/BO remapping of v1 keys | "Ease migration" | Rekeys identities; breaks retry/idempotency; corrupts canary baselines | Explicit new keys + documented migration; never reinterpret |
| Client-supplied endpoint maps | "Support new pairs without deploy" | Injection/schema drift; Cypher-adjacent risk; non-reproducible graphs | Server allowlist only; expand via versioned release |
| Cartesian provenance (all sources × all targets) | "Fewer lines of agent code" | Invents unproven links; blows limits; non-auditable | Explicit evidence links only |
| Prepare that writes domain objects | "Faster commit" | Partial domain state on crash; breaks atomic story | Prepare = plan/status only; domain write only on commit |
| Mutable prepared plans | "Edit without re-prepare" | Hash/identity ambiguity; race with concurrent commit | Immutable plan; discard + re-prepare |
| Soft warnings for illegal endpoint pairs | "Partial success" | Leaves illegal edges if atomic false elsewhere; canary false confidence | Fail closed before side effects; atomic batches roll back fully |
| Automatic v1→v2 identity migration tool in-process | "One-click upgrade" | Dangerous on live groups; out of scope; irreversible rekey risk | Separate approved ops milestone; docs-only guidance in v1.1 |
| Production/canary execution in this milestone | "Prove end-to-end" | Scope breach; mutates live groups; blocks honest gate | Docs + procedure only; execute canary under separate approval |
| Parser / inferred relationships / path-impact APIs | "Complete catalog product" | Different milestone; contaminates substrate hardening | Defer: parser, inference, object-context, delta/retirement |
| Caller UUID as identity authority | "Match external systems" | Breaks deterministic UUIDv5 contract | Server UUIDv5 only; external IDs as attributes |
| Logging full catalog payloads | "Easier debug" | Secrets/PII/source leakage | Batch IDs + counts + structured codes only |
| Disabling reads when writes disabled | "Single feature flag" | Blocks diagnosis of failed canaries | Split read/write gates |
| FalkorDB/other backend claims | "Portability" | Unproven transaction/label/vector semantics | Neo4j only; no portability claim |

## Observable Contracts (Client/Operator Perspective)

### Request validation

- Complete nested validation before any embedding or Neo4j write.
- Unknown fields at any nesting depth → `validation_error` with path.
- Collection/string/hash/prefix/confidence/NaN/infinity/protected-property rules remain enforced.
- Execution flags (`dry_run`, `atomic`, prepare/commit mode) are validated and, once prepared, immutable relative to that `batch_id` + plan hash.

### Identity (catalog-v2)

- UUIDv5 authority unchanged: entity `group_id|entity_type|graph_key`; edge `group_id|edge_type|edge_key`; source `group_id|Source|source_key`; batch `group_id|Batch|batch_id`.
- FE/BO/COMMON isolation is visible in grammar (keys and/or typed attributes as specified in phase design) and fail-closed on violation.
- Caller database UUIDs never identity authority.
- Namespace still immutable deployment config; change rekeys everything — document, never auto-generate.

### Endpoint pairs

- For each edge type, only documented `(source_entity_type, target_entity_type)` pairs accepted.
- Prefix checks still apply per endpoint type.
- `EnforcedBy` still requires non-empty evidence.
- Illegal pair → structured error before embeddings/writes.

### Hashes and capabilities

- Server-authoritative content/request/catalog hashes cover all domain-bearing fields defined by the contract.
- Optional client hashes compared; mismatch fails closed.
- Capabilities tool/response exposes: write/read enabled, limits, allowlists, endpoint maps, protocol/grammar versions, backend = Neo4j only.

### Prepare / commit / discard

**Approved tools (exact names):** `prepare_catalog_batch`, `commit_prepared_catalog_batch`, `discard_prepared_catalog_batch`, `get_catalog_capabilities`, `get_catalog_evidence`, `get_catalog_batch_manifest`, `resolve_typed_edges`.

| Operation | Domain graph write | Embeddings | Persists | Idempotent replay | On conflict |
|-----------|--------------------|------------|----------|-------------------|-------------|
| prepare | No | **No** (validation/resolution/projections only) | Immutable plan + **full bounded canonical payload** (+ hashes); token returned | Same plan → unchanged; different content same id → `prepared_plan_conflict` | No domain mutation |
| commit | Yes — **one Neo4j tx**: domain + evidence + manifest + terminal batch status + plan terminal state | **Yes** — from stored payload **before** domain tx | Terminal committed state | Same plan hash → unchanged / already_consumed | Full rollback; optional separate failure-status tx only |
| discard | No | No | Clears/marks plan discarded | Safe if already discarded | Never deletes unrelated domain data |
| dry_run (legacy/path) | No | No | No persistent plan (or non-authoritative) | N/A | Validation only |

### Provenance evidence

- Explicit links only; no sources×targets product.
- Missing targets → `provenance_target_missing`, no partial write under atomic.
- No LLM, queue, or `add_memory` path.

### Manifest and verification

- On successful commit: durable manifest with exact identities, counts, hashes, timestamps.
- Manifest nodes non-`Entity`; excluded from search/communities (same isolation principle as `CatalogIngestBatch`).
- Verification modes: explicit keys (v1), batch_id → status, batch_id → manifest-backed expected set.
- `resolve_typed_edges` mirrors entity resolve diagnostics for edges.

### Gates

| Surface | Write gate off | Read gate off (if separate) |
|---------|----------------|-----------------------------|
| upsert_* / prepare / commit | `feature_disabled` | N/A |
| resolve_* / verify / status / capabilities / manifest read | Allowed | `feature_disabled` or equivalent |
| Existing non-catalog MCP tools | Unaffected | Unaffected |

### Required structured error codes (v1.1 additive)

`unsupported_identity_schema`, `invalid_system_key`, `edge_endpoint_pair_not_allowed`, `prepared_plan_not_found`, `prepared_plan_expired`, `prepared_plan_conflict`, `prepared_plan_already_consumed`, `manifest_mismatch`, `provenance_link_conflict` — plus retained v1 codes (`validation_error`, `feature_disabled`, `content_hash_mismatch`, …).

### Security / privacy

- No client labels/property names interpolated into Cypher.
- No credentials, full payloads, raw documents, or complete source text in logs or status/manifest summary fields.
- `group_id` required and constrains every catalog read/write.
- Bounded nested JSON (depth/nodes/string lengths) to resist payload bombs.

### Compatibility

- Preserve **MCP tool names** and legacy **semantic** tools. Catalog-v2 **intentionally breaks** seven deterministic request identity/provenance/hash contracts where required — **do not** claim old catalog-v1 request payloads remain accepted.
- Search: catalog entities via `search_nodes`; facts via `search_memory_facts`.
- No `clear_graph`, no live-group mutation in tests, no canary execution, no automatic v1→v2 migration, no parser/inference.

## Feature Dependencies

```
Strict recursive contracts
    └──requires──> Immutable execution flags
                       └──enhances──> Authoritative batch hashes

FE/BO identity grammar
    └──requires──> Strict recursive contracts
    └──enhances──> Manifest identity lists

Server endpoint-pair maps
    └──requires──> Strict recursive contracts
    └──requires──> Capabilities discovery (advertise maps)
    └──enhances──> resolve_typed_edges / edge upsert safety

Authoritative hashes
    └──requires──> Strict contracts + explicit evidence model
    └──requires──> Prepare/commit immutability

Prepare/commit/discard
    └──requires──> Authoritative hashes
    └──requires──> Endpoint-pair maps + FE/BO grammar
    └──requires──> Explicit evidence links
    └──requires──> Durable manifests (on commit)
    └──conflicts──> Prepare-with-domain-writes (anti-feature)

Durable manifests
    └──requires──> Successful atomic commit path
    └──enhances──> Manifest-backed verification

Manifest-backed verification
    └──requires──> Durable manifests
    └──enhances──> Split read/write gates (verify while writes off)

resolve_typed_edges
    └──requires──> Endpoint-pair maps (anomaly reporting)
    └──enhances──> Manifest-backed verification

Split read/write gates
    └──enhances──> Capabilities discovery
    └──enhances──> All read-only diagnostics

Legacy compatibility
    └──conflicts──> Breaking schema renames without aliases
    └──requires──> Additive-only MCP tool changes

Docs + tests (exhaustive)
    └──requires──> All table-stakes contracts frozen
    └──conflicts──> Production/canary execution (out of scope)
```

### Dependency Notes

- **Prepare/commit requires hashes + maps + grammar + evidence:** plan identity is incomplete without all four; otherwise commit cannot be deterministic.
- **Manifest requires commit:** do not persist "expected" domain manifests from prepare alone if that implies domain presence; prepare stores plan, commit stores manifest of applied identities.
- **Manifest-backed verify requires read path while writes disabled:** otherwise operators cannot audit a locked environment.
- **Legacy compatibility conflicts with silent v2 rekey:** additive tools preferred over redefining `graph_key` meaning in place.

## Edge Cases (Must Specify in Requirements)

| Case | Expected behavior |
|------|-------------------|
| Unknown nested field in attributes/source_refs | `validation_error`; no write |
| Prepared batch_id reused with different content hash | conflict; plan unchanged |
| Commit after discard | fail; no domain write |
| Commit when write gate off | `feature_disabled`; plan retained |
| Prepare when write gate off | `feature_disabled` (prepare is mutation of control plane) unless design explicitly allows plan-only under read — default: prepare needs write gate |
| Resolve/verify when write gate off | success if data exists |
| Illegal endpoint pair in dry_run | error; no write; no plan unless prepare path |
| Explicit provenance link to missing target | `provenance_target_missing`; atomic full fail |
| Cartesian-sized link explosion attempt | reject at validation (link count / require explicit pairs) |
| FE key used with BO-only edge pair | fail closed |
| Concurrent identical commit | one logical domain outcome; idempotent unchanged |
| Concurrent different content same batch_id | one winner; loser `batch_conflict`; no mixed graph |
| Embedding failure during commit | no domain partial write; failed status via post-rollback status tx only |
| Prepare stores hashes only | **rejected by contract** — payload must be rehydratable at commit |
| Capabilities when writes disabled | still returns maps/limits/`enabled=false` after successful server init |
| Server restart after prepare before commit | plan durable; commit still applies or discards |
| Server restart after commit | status+manifest durable; verify works |
| Legacy tool **names** without prepare | names preserved; v2 request contracts may fail closed on v1-shaped payloads |
| Capabilities under disabled catalog writes | still returns enabled=false + maps/limits whenever server init succeeds |

## Migration Implications

| Topic | v1.1 stance |
|-------|-------------|
| Existing v1 identities in test/live graphs | Leave untouched; no auto-migration |
| New catalog-v2 FE/BO keys | New writes only under explicit grammar |
| Namespace change | Forbidden as casual ops; full rekey; docs warn |
| Client scripts on seven tools | Keep working; optional new tools for prepare/commit/manifest/resolve_edges/capabilities |
| Regenerated canary | Procedure documented; **not executed** this milestone |
| Production writes | Out of scope |
| Hash coverage expansion | Protocol version bump; old client hashes may mismatch until clients recompute — document |

## MVP Definition (v1.1 Hardening)

### Ship in this milestone

- [ ] Strict recursive fail-closed request contracts + immutable flags
- [ ] Catalog-v2 FE/BO/COMMON identity grammar (visible, deterministic)
- [ ] Server-owned edge endpoint-pair maps enforced pre-side-effect
- [ ] Authoritative combined hashing + capabilities discovery
- [ ] Durable prepare / commit / discard protocol
- [ ] Explicit evidence links (no Cartesian expansion)
- [ ] Durable manifests + manifest-backed verification
- [ ] `resolve_typed_edges`
- [ ] Split read/write gates
- [ ] Legacy seven-tool compatibility + search/isolation preserved
- [ ] Exhaustive unit/service/store/MCP/concurrency/Neo4j/security/compat tests on `oracle-catalog-tool-test` only
- [ ] Operator docs: contracts, migration guidance, canary procedure **without** execution

### Explicitly defer (not v1.1)

- [ ] Oracle/SQL/PLSQL parser
- [ ] Inferred relationships / scoring
- [ ] Object-context / path / impact APIs
- [ ] Catalog delta / retirement / FE-BO runtime correlation
- [ ] Automatic v1→v2 identity migration
- [ ] Production migration, production writes, canary execution
- [ ] FalkorDB or multi-backend catalog claims
- [ ] K8s deployment / full 14k entity ingest

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Strict recursive contracts | HIGH | MEDIUM | P1 |
| FE/BO identity grammar | HIGH | MEDIUM | P1 |
| Endpoint-pair maps | HIGH | MEDIUM | P1 |
| Authoritative hashes | HIGH | MEDIUM | P1 |
| Capabilities discovery | HIGH | LOW | P1 |
| Prepare/commit/discard | HIGH | HIGH | P1 |
| Explicit evidence links | HIGH | MEDIUM | P1 |
| Durable manifests | HIGH | HIGH | P1 |
| Manifest-backed verification | HIGH | MEDIUM | P1 |
| resolve_typed_edges | HIGH | MEDIUM | P1 |
| Split read/write gates | HIGH | LOW | P1 |
| Legacy compatibility + tests/docs | HIGH | MEDIUM | P1 |
| Auto migration tooling | MEDIUM | HIGH | P3 (out of scope) |
| Parser / inference / path APIs | HIGH later | HIGH | P3 (later milestone) |
| Canary execution | HIGH later | MEDIUM | P3 (separate approval) |

**Priority key:**
- P1: Must have for v1.1 pre-canary hardening
- P2: Should have if schedule allows (none reserved — hardening is the milestone)
- P3: Future / explicit non-goal this milestone

## Competitor / Baseline Feature Analysis

| Feature | Semantic Graphiti MCP (`add_memory`) | Generic Cypher admin | Deterministic catalog (this product) |
|---------|--------------------------------------|----------------------|--------------------------------------|
| Exact identity | No (LLM extract + fresh UUIDs) | Manual | UUIDv5 + hashes |
| Typed endpoints | Weak / generic create risk | Manual | Fail-closed maps |
| Idempotent retry | Queue/async hazards | Manual | Designed |
| Provenance | Episode extract | Ad hoc | Explicit links, no Cartesian |
| Agent crash safety | Partial episodes possible | Manual tx | Prepare/commit + atomic domain |
| Audit expected set | No | Manual queries | Durable manifest |
| FE/BO isolation | None | Manual labels | Grammar + gates |

## Sources

- `.planning/PROJECT.md` — v1.1 active requirements and non-goals
- `.planning/milestones/v1.0-REQUIREMENTS.md` — shipped baseline (86 requirements)
- `mcp_server/src/models/catalog_*.py` — current request/response contracts
- `mcp_server/src/graphiti_mcp_server.py` / catalog services — existing seven-tool surface
- Operator constraints: Neo4j-only, test group isolation, no production/canary execution

---
*Feature research for: Catalog-v2 Pre-Canary Hardening (MCP client/operator contracts)*
*Researched: 2026-07-17*
*Replaces: obsolete v1.0-oriented FEATURES.md content for this milestone*
