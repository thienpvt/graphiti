# Phase 4: Manifest-Backed Verification and Read-Only Diagnostics - Research

**Researched:** 2026-07-19
**Domain:** MCP catalog read diagnostics, durable manifest reassembly, split feature gates, Neo4j read-only Cypher
**Confidence:** HIGH

## Summary

Phase 4 is additive public **read/diagnostic** work on top of Phase 3B durable manifests. No write-path redesign. No new third-party packages. Extension is entirely within existing `mcp_server` catalog modules using already-proven patterns: thin FastMCP tools → `CatalogService` → fixed Cypher on `CatalogNeo4jStore` → strict Pydantic request/response models.

Critical gaps to close (verified in source this session):
1. `_read_gate` still requires `catalog_config.enabled` (write flag) — blocks GATE-03.
2. Batch-only `verify_catalog_batch` sets `expected = len(rows)` from live batch_id matches — violates VERI-01/02 (must use durable manifest membership).
3. Missing ingest status returns `status=failed` + `validation_error` — violates GATE-05.
4. `HARD_MAX_PAGE_SIZE = 0` and no `reads_enabled` / `max_page_size` config fields.
5. No public tools for manifest page, edge resolve, or evidence read; `features.manifest_verification` remains false by design until proofs pass.
6. Manifest chunk list Cypher returns metadata only (no `payload_b64`) — Phase 4 must add a **read** loader that returns payload for reassembly via existing `reassemble_artifact_bytes`.

**Primary recommendation:** Split gates first, then pure store reassembly + pagination helpers, then rewire verify expected-membership to manifest, then register three new MCP tools and flip `manifest_verification` only after tests green.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Add public `get_catalog_batch_manifest` as a read-only MCP tool. Input is group-scoped batch identity (`group_id` + `batch_id`) plus pagination controls. Output returns group ID, batch ID, request/catalog/artifact/manifest hashes, identity/canonicalization/catalog schema versions, exact category counts, and paginated compact item identities for entities, edges, sources, and evidence links - including unchanged shared entities.
- **D-02:** Membership order is the durable manifest canonical order already established by Phase 3B pure canonicalization (`services/catalog_manifest.py` category sort keys). Never re-sort by live graph discovery or `batch_id`. Pagination is offset/limit over that stable order (or an equivalent opaque cursor that encodes the same stable position). Repeat reads with the same params yield the same page contents for an unchanged manifest.
- **D-03:** Default projection is compact identities only (uuid, type/key, content hash, projected_status where present). Optional detailed audit projection may include bounded extra fields already stored on the manifest body; it never returns embeddings, raw prepared payload, source text, or credentials.
- **D-04:** Configure a non-zero `max_page_size` (config + hard ceiling) for manifest/evidence pagination. Current Phase 2/3 capabilities expose `HARD_MAX_PAGE_SIZE = 0` as explicit not-configured; Phase 4 replaces that zero authority with a conservative positive ceiling and reports it in capabilities limits. Fail closed on page size above configured/hard max.
- **D-05:** Missing, incomplete, hash-mismatched, or chunk-incoherent manifests fail closed. Do not synthesize membership from domain rows, evidence rows, or `entity.batch_id` / `edge.batch_id`.
- **D-06:** When `verify_catalog_batch` is invoked with `batch_id` (batch-only or batch+keys), load the committed durable manifest as the sole expected membership and count authority (VERI-01/02). Expected counts come from manifest/status metadata, never from the number of physical rows returned by the live query under test.
- **D-07:** Batch verification reports missing manifest members and extra physical duplicates/drift as distinct diagnostics (VERI-03). It never normalizes extras away or treats live-row count as expected count.
- **D-08:** Verification checks exact entity type, deterministic entity UUID, exact edge type, deterministic edge UUID, endpoint UUIDs and graph keys, required name/fact embeddings presence, exact provenance/evidence-link identities and counts (EVID-13), and manifest hash/count consistency (VERI-04). Embedding presence is always verified for members that require embeddings under current server behavior; do not add a no-op optional flag.
- **D-09:** A committed catalog-v2 batch with no valid durable manifest fails with `manifest_mismatch` (VERI-05; code already registered in `CatalogErrorCode`). Incomplete chunk set, digest mismatch, or contradictory root/chunk metadata also map to fail-closed manifest mismatch / conflict - never silent partial verify.
- **D-10:** Explicit-key verification remains available and compatible (VERI-06). `batch_id` and/or explicit entity/edge keys remain valid scopes per existing `VerifyCatalogBatchRequest`. Explicit-key-only mode does not invent a fake batch manifest; batch-only mode does not drop explicit-key checks when both are supplied - keys still diagnose against live rows while expected membership for the batch remains manifest-backed.
- **D-11:** Verify never sets expected values equal to objects returned by the query being verified. Live reads are observations only; manifest (or explicit request keys) are expectations.
- **D-12:** Add `resolve_typed_edges` mirroring `resolve_typed_entities` patterns: request by allowlisted edge type + edge key (and system/group scope), return UUID, source/target UUIDs and graph keys, exact type, content hash, embedding presence, and anomaly tags. No semantic search.
- **D-13:** Edge resolution reports not-found, physical duplicates, type mismatch, endpoint mismatch, endpoint-pair violation, and deterministic UUID mismatch without repairing data (RESE-02). Fail closed; never rewrite edges.
- **D-14:** Add `get_catalog_evidence` as read-only compact evidence for one entity or edge target within `group_id`, with bounded pagination and optional excerpts (EVID-12). Default omits full excerpts/source payloads; optional excerpt flag remains length-bounded.
- **D-15:** Evidence and edge diagnostics are group-isolated, perform no embedding, open no write transaction, and remain usable when catalog writes are disabled (RESE-03, GATE-03/04).
- **D-16:** Complete IDEN-08: every resolve, manifest, evidence, and verification response surface that identifies a catalog entity exposes the complete system-scoped graph key (not a truncated or name-only form). Phase 1 model/service echo is foundation only; Phase 4 owns remaining response surfaces.
- **D-17:** Separate explicit feature gates (GATE-01):
  - **Write gate** (`catalog_upsert.enabled`, existing): controls prepare, commit, discard, and non-dry-run upsert mutations. Default remains **false**.
  - **Read/diagnostic gate** (new explicit config, e.g. `catalog_upsert.reads_enabled` or sibling field): controls catalog diagnostic tools. Default **true** so diagnostics work out of the box when identity namespace and Neo4j reads are available.
- **D-18:** `get_catalog_capabilities` remains callable whenever the MCP server is initialized, independent of write and read gates (GATE-02). It stays mutation-free and never probes with writes or schema init.
- **D-19:** When the write gate is false and the read gate is true (and namespace + Neo4j readable), these remain usable: `get_catalog_ingest_status`, `get_catalog_batch_manifest`, `resolve_typed_entities`, `resolve_typed_edges`, `verify_catalog_batch`, `get_catalog_evidence` (GATE-03). Write tools still return structured `feature_disabled` (or equivalent) without side effects.
- **D-20:** Fix `_read_gate` so it no longer requires `catalog_config.enabled` (write flag). Today `_read_gate` incorrectly couples reads to the write enable flag (`catalog_service.py`); Phase 4 must split that check. Read gate still requires valid configured UUID namespace for identity-bearing diagnostics and Neo4j backend.
- **D-21:** Read-only catalog operations never initialize, alter, or repair schema and never open write transactions (GATE-04). No embedder, LLM, queue, or external network call on read paths.
- **D-22:** Missing batch status is distinguishable via `found=false` (or explicit not-found state/code) and never masquerades as committed success or generic operational failure (GATE-05). Extend `CatalogIngestStatusResponse` (and any new read responses) so absence is not encoded solely as `status=failed` + `validation_error`.
- **D-23:** Every gated read and write retains complete `group_id` isolation (GATE-06). Tests use only `oracle-catalog-tool-test`. Never query or mutate `oracle-catalog-v2`.
- **D-24:** Capabilities report `catalog_writes_enabled` and `catalog_reads_enabled` separately and truthfully from config. Flip `features.manifest_verification` to true only after public manifest-backed verify registration + required proofs pass. Keep `features.manifests` true from Phase 3B persistence authority.
- **D-25:** Register new MCP tools with the same thin FastMCP + safe-error boundary pattern as existing catalog tools. Preserve all 14 legacy MCP tool names/contracts and existing catalog tool contracts (TEST-09). `get_status` remains compatible (additive only).
- **D-26:** Capabilities limits expose configured and hard `max_page_size` after D-04; no runtime read of `.planning/*` gate JSON to decide feature flags.
- **D-27:** TEST-08: manifest and resolver tests prove unchanged shared entities remain members, missing manifest items/count drift are detected, missing manifests fail with `manifest_mismatch`, and edge twins/endpoint mismatches are reported without repair.
- **D-28:** TEST-09: gate and registration tests prove read tools work while writes are disabled, all 14 legacy tools remain registered, all expected catalog-v2 tools are registered (including new Phase 4 tools), and `get_status` remains compatible.
- **D-29:** Unit/service/store coverage for pagination stability, manifest authority vs live-row observation, explicit-key compatibility, evidence pagination, read-gate defaults, no schema/write/embed on reads, and `found=false` missing status.
- **D-30:** Live Neo4j proofs (when available) stay on `oracle-catalog-tool-test` only; no canary, no deploy, no clear/delete, no push. Preserve historical audit commit `a67789a` as immutable evidence of 03B-06 live green - do not amend, rebase, or delete it.
- **D-31:** Phase 5 remains blocked until a fail-closed Phase 4 gate reports manifest reads, manifest-backed verify, edge/evidence diagnostics, split gates, registration, and isolation green.

### Claude's Discretion
- Exact request/response Pydantic model field names for new tools, page cursor encoding, and anomaly list shapes - provided they stay strict, bounded, and secret-free.
- Smallest service/store method extraction for manifest reassembly reads (reuse create-once root/chunk loaders already on `CatalogNeo4jStore`).
- Exact config field name for the read gate and env mapping, as long as default is safe (reads on, writes off) and documented in capabilities.
- Whether verify response gains dedicated evidence/manifest sections vs extending existing anomaly lists - must still satisfy EVID-13 and VERI-03/04.

### Deferred Ideas (OUT OF SCOPE)
- Final security/compatibility matrix, full live isolation expansion, operator/migration docs, offline canary-artifact regeneration, final readiness report with `canary_executed=false`: Phase 5.
- `LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`, automatic catalog-v1 migration, parser/extraction, new business entities, non-Neo4j portability: future/out of scope.
- Canary execution, `oracle-catalog-v2` access, production migration, deployment, graph clearing, existing-data deletion, push/merge/tag: separate explicit approval only.
- Long-term manifest retention/cleanup jobs and advanced observability dashboards: not Phase 4.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDEN-08 | Complete system-scoped graph keys on resolve/manifest/evidence/verify responses | Reuse `graph_key` fields already on entity resolve; ensure edge/source/evidence surfaces echo full keys from manifest body / live rows; ban name-only fallbacks in new response models |
| MANI-05 | Public paginated durable membership read | `catalog_manifest.py` canonical order + store root/chunk reassembly + offset/limit over categories |
| VERI-01 | Batch-only verify loads committed manifest as expected membership | Rewire `verify_catalog_batch` when `batch_id` present: load/reassemble body → expected entities/edges |
| VERI-02 | Expected counts from manifest/status metadata, not live row count | Delete/replace `_verify_entities` branch that sets `section.expected = len(rows)` for batch-only |
| VERI-03 | Report missing members and extras/duplicates separately | Diff manifest expected set vs live observations; keep existing anomaly lists; add extras list |
| VERI-04 | Exact type/UUID/endpoints/embeddings/evidence/manifest consistency | Extend existing `_verify_*` + evidence-link exact match (EVID-13); compare manifest hash/counts |
| VERI-05 | No valid manifest → `manifest_mismatch` | Code exists (`CatalogErrorCode.manifest_mismatch`); map incomplete/hash fail closed |
| VERI-06 | Explicit-key verify remains | Keep `VerifyCatalogBatchRequest` scope validator; keys-only path unchanged authority model |
| RESE-01 | `resolve_typed_edges` by type+key | Mirror `resolve_typed_entities` + `match_edges_for_verify` key Cypher; return endpoints/hash/embedding |
| RESE-02 | Edge anomaly taxonomy without repair | Reuse/extend edge verify anomaly tags; add endpoint-pair violation |
| RESE-03 | Group-isolated read-only, works writes-off | Split `_read_gate`; no embed/schema/write |
| GATE-01 | Separate read/write gates, safe defaults | `CatalogConfig.enabled` false; new `reads_enabled` true; optional `max_page_size` |
| GATE-02 | Capabilities always callable | Already independent of store; keep mutation-free |
| GATE-03 | Six read tools work when writes disabled | Fix `_read_gate`; register new three tools on same gate |
| GATE-04 | No schema init / write tx / embed on reads | Pattern already on resolve/verify; enforce for new paths; ban `ensure_*_schema` |
| GATE-05 | Missing status → `found=false` | Extend `CatalogIngestStatusResponse` |
| GATE-06 | Full `group_id` isolation | Every Cypher WHERE group_id; tests only `oracle-catalog-tool-test` |
| EVID-12 | `get_catalog_evidence` compact paginated read | New store MATCH on `CatalogEvidenceLink` by group+target; bounded page |
| EVID-13 | Verify exact evidence-link identities/counts | Beyond boolean `match_provenance_presence`; load links by expected UUID/key from manifest |
| TEST-08 | Manifest/resolver behavioral proofs | Unit + service + optional live tool-test group |
| TEST-09 | Gate/registration/legacy preservation | Update registration count 25→28; writes-off read smoke |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Additive only: preserve every existing MCP tool and behavior.
- Neo4j first (5.26+); no multi-backend catalog portability claim.
- Server-derived UUIDv5 only; fixed `GRAPHITI_CATALOG_UUID_NAMESPACE`.
- Never interpolate client labels/property names into Cypher; fixed allowlists.
- Reads return after observation only; no partial writes.
- No embedder/LLM/queue on read paths (GATE-04 / Phase 3A commit seam preserved).
- Isolation: every query `group_id`-scoped; tests only `oracle-catalog-tool-test`; never `oracle-catalog-v2`.
- Logs: batch IDs and counts only — never payloads, source text, credentials, tokens.
- Scale defaults: 500 entities / 2k edges / 5k provenance per batch (hard ceilings higher).
- No deployment, live-group writes, full ingest, graph clear, existing-data deletion.
- Ruff single quotes, line length 100; Pyright basic on mcp_server; pytest-asyncio auto.
- Historical audit commit `a67789a` retained; two-axis safety truth (historical vs current).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Request validation (strict models) | API / Backend (MCP models) | — | Trust boundary; extra=forbid before any I/O |
| Feature gates (read vs write) | API / Backend (`CatalogService` + `CatalogConfig`) | — | Policy before store |
| Manifest reassembly + integrity | API / Backend (`CatalogNeo4jStore` + pure reassembly) | Database | Durable bytes authority |
| Membership pagination | API / Backend (pure slice of reassembled body) | — | Order from Phase 3B canonical body |
| Live observation (entities/edges) | Database / Storage (read Cypher) | API / Backend | Observations only, never expected authority |
| Expected membership for batch verify | API / Backend (manifest body) | — | VERI-01/02 |
| Edge/evidence diagnostics | Database / Storage (read MATCH) | API / Backend | Group-scoped, no mutation |
| Capabilities discovery | API / Backend (pure builder) | — | No DB probe, no schema |
| MCP tool registration | API / Backend (`graphiti_mcp_server.py`) | — | Thin wrappers + safe errors |
| Embeddings / schema / writes | Explicitly **not** this phase | — | GATE-04 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | >=3.10,<4 (runtime 3.12.10 verified) | Implementation language | Project pin |
| Pydantic | 2.11.7 verified in mcp_server env | Strict request/response models | Existing catalog contract base |
| neo4j (official driver via graphiti_core) | >=5.26.0 | Async Neo4j reads | Existing `Neo4jDriver.execute_query` |
| mcp / FastMCP | >=1.27.2,<2 | Tool registration | Existing MCP server |
| pytest + pytest-asyncio | pytest 9.0.3 verified | Tests | Existing suite |
| Ruff / Pyright | project pins | Lint/types | CLAUDE.md |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `base64`, `hashlib`, `json` | stdlib | Manifest reassembly / digests | Already used by `catalog_prepared_artifact.reassemble_artifact_bytes` |
| pydantic-settings | >=2.0 | Config nested env | Existing `CatalogConfig` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Offset/limit pagination | Opaque cursor tokens | Cursor deferred by D-02 preference; add only if API stability needs it later |
| In-process expected = live rows | Manifest authority | **Forbidden** by VERI-01/02/D-11 |
| New graph query library | Existing store Cypher | YAGNI; fixed allowlisted Cypher is the security model |
| New packaging deps | None | No new packages for Phase 4 |

**Installation:** none — no new packages.

**Version verification:** pydantic 2.11.7, pytest 9.0.3, Python 3.12.10 confirmed in mcp_server `uv` env this session. No registry package installs planned.

## Package Legitimacy Audit

> No external packages to install for Phase 4.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — | — | — | — | — | — | No installs |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
MCP Client
    |
    v
FastMCP tools (thin, CatalogSafeFastMCP)
  - get_catalog_batch_manifest
  - resolve_typed_edges
  - get_catalog_evidence
  - verify_catalog_batch (rewired)
  - resolve_typed_entities / get_catalog_ingest_status (gate-fixed)
  - get_catalog_capabilities (ungated)
    |
    |  Pydantic validate (extra=forbid)
    v
CatalogService
  |_ _read_gate(reads_enabled, namespace, neo4j)   # NOT write enabled
  |_ _write_gate(enabled, namespace, neo4j)        # mutations only
  |_ load_manifest_body(group,batch) -> fail closed
  |_ paginate(membership categories, offset, limit)
  |_ verify: expected=manifest | keys; observe=live MATCH; diff
  |_ resolve edges / evidence: observe only
    |
    |  parameterized Cypher only
    v
CatalogNeo4jStore (read helpers)
  - read_manifest_root_by_batch
  - list_manifest_chunks_with_payload (NEW; payload_b64)
  - match_entities_for_verify / match_edges_for_verify (existing)
  - match_edges_for_resolve (NEW or reuse key path)
  - match_evidence_links_for_target (NEW)
  - match_evidence_links_exact (NEW for EVID-13)
    |
    v
Neo4j 5.26+  (group_id isolation; no write tx on read paths)
  CatalogBatchManifest + CatalogBatchManifestChunk
  Entity / RELATES_TO / CatalogEvidenceLink
```

### Recommended Project Structure (extension points only)

```
mcp_server/src/
├── config/schema.py              # CatalogConfig: reads_enabled, max_page_size
├── models/
│   ├── catalog_entities.py       # ResolveTypedEdgesRequest, GetManifestRequest, GetEvidenceRequest
│   ├── catalog_responses.py      # Manifest/edge/evidence/status found=false extensions
│   └── catalog_common.py         # HARD_MAX_PAGE_SIZE constant (or keep in capabilities)
├── services/
│   ├── catalog_capabilities.py   # truthful reads_enabled; non-zero page size; flip manifest_verification last
│   ├── catalog_manifest.py       # pure; optional page helper over body categories
│   ├── catalog_prepared_artifact.py  # reassemble_artifact_bytes (reuse)
│   ├── catalog_store.py          # read loaders only
│   └── catalog_service.py        # gate split + tools logic
└── graphiti_mcp_server.py        # register 3 tools; extend CATALOG_TOOL_NAMES

mcp_server/tests/
├── test_catalog_manifest_read.py     # Wave 0/1 reassembly + pagination pure/service
├── test_catalog_verify_manifest.py   # VERI-01..06
├── test_catalog_resolve_edges.py     # RESE-01..03
├── test_catalog_evidence_read.py     # EVID-12/13
├── test_catalog_gates.py             # GATE-01..06 (or extend test_catalog_service)
└── test_catalog_service.py           # update registration 25 → 28 tools
```

### Pattern 1: Thin MCP + structured safe error
**What:** `@mcp.tool()` async function builds typed request, calls service, catches Exception → `ErrorResponse` / structured code.
**When to use:** All three new tools.
**Example:** Existing `resolve_typed_entities` / `verify_catalog_batch` wrappers in `graphiti_mcp_server.py:1340+`. [VERIFIED: codebase]

### Pattern 2: Read-only store via `execute_query` params=
**What:** `CatalogNeo4jStore._read_one` / `_read_many` call `executor.execute_query(cypher, params=params)` — never open write transactions, never schema ensure.
**When to use:** All Phase 4 store reads.
**Anti-pattern:** Calling `ensure_evidence_manifest_schema` or `tx.run` write Cypher from read tools.

### Pattern 3: Manifest as expected authority
**What:** Reassemble canonical body bytes → `json.loads` → category lists are expected membership; live MATCH rows are observations for diff only.
**When to use:** Batch-only and batch+keys verify; never for keys-only (keys-only uses request keys as expected).

### Pattern 4: Pure reassembly fail-closed
**What:** Reuse `reassemble_artifact_bytes(chunks, expected_sha256=root.manifest_sha256, expected_length=root.payload_bytes)` then verify `manifest_sha256(bytes) == root.manifest_sha256`. [VERIFIED: `catalog_prepared_artifact.py:123`]
**When to use:** Any public or verify load of durable membership.

### Anti-Patterns to Avoid
- **Expected = observed:** `_verify_entities` batch-only branch currently sets `section.expected = len(rows)` — must die for batch_id path. [VERIFIED: `catalog_service.py:1783-1786`]
- **Read gated by write enable:** `_read_gate` checks `self.catalog_config.enabled`. [VERIFIED: `catalog_service.py:1254-1258`]
- **Synthesize membership from batch_id property:** Phase 3B explicitly forbids; Phase 4 must not revive.
- **Schema init on first read:** `ensure_evidence_manifest_schema` is write-side only.
- **Return embeddings / payload_b64 / source text** on public surfaces.
- **Flip `manifest_verification=true` before tests/gate proof.**
- **Touch `oracle-catalog-v2` or rewrite `a67789a` history.**

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chunk reassembly + digest | Custom base64 loop | `reassemble_artifact_bytes` | Already enforces order, offset, per-chunk hash, length |
| Manifest canonical order | Live graph sort | `catalog_manifest` body categories | Durable authority; MANI-03/D-02 |
| Edge key match Cypher | New ad-hoc MATCH | Extend `match_edges_for_verify` / resolve twin | Allowlisted labels; group_id param |
| Structured error codes | New string enums ad hoc | `CatalogErrorCode` (incl. `manifest_mismatch`) | CONT-08 registry |
| Capabilities feature flags | Read `.planning/*` at runtime | Static/config-derived builder | D-26 / Phase 3B precedent |
| Pagination protocol | Cursor crypto | Offset/limit ints + hard max | D-02/D-04 simplicity |

**Key insight:** Phase 3B already stored the authority; Phase 4 is mostly **load, page, diff, and ungate reads**.

## Common Pitfalls

### Pitfall 1: Leaving batch-only expected = live row count
**What goes wrong:** Verify always "passes" membership by construction.
**Why:** Pre-Phase-4 code path when `expected` list empty. [VERIFIED: catalog_service.py]
**How to avoid:** If `batch_id` present, load manifest first; build expected refs from body; live rows only for found/extra.
**Warning signs:** Tests where deleting a graph node still reports expected==found without missing list.

### Pitfall 2: Incomplete chunk list Cypher for public reads
**What goes wrong:** Reassembly fails or silent empty membership.
**Why:** `build_list_manifest_chunks_cypher` returns metadata only (no `payload_b64`, no offsets). [VERIFIED: catalog_store.py:3288-3298]
**How to avoid:** New `build_load_manifest_chunks_cypher` mirroring prepared-plan chunk load (payload_b64, byte_offset, byte_length, chunk_sha256, chunk_index, chunk_count).

### Pitfall 3: Coupling namespace requirement to write enable
**What goes wrong:** Reads need identity for UUIDv5 diagnostics but write default false.
**How to avoid:** Read gate requires valid `uuid_namespace` independently; write gate keeps existing "namespace required when enabled" validator. Optionally require namespace for identity-bearing reads even when writes off.

### Pitfall 4: Registration count drift
**What goes wrong:** TEST-09 fails; tool set desync.
**Why:** Current test asserts exactly 25 tools (11 catalog + 14 legacy). [VERIFIED: test_catalog_service.py:4455-4472]
**How to avoid:** Add 3 names to `CATALOG_TOOL_NAMES` and update exact-count assertion to 28; keep LEGACY_TOOL_NAMES frozen at 14.

### Pitfall 5: Page size zero authority leftover
**What goes wrong:** Clients cannot page; capabilities lie.
**How to avoid:** Set conservative defaults e.g. configured 100, hard 500 (discretion); fail closed above hard; report both in capabilities.

### Pitfall 6: Evidence verify stays boolean-only
**What goes wrong:** EVID-13 incomplete.
**How to avoid:** For batch verify with evidence in manifest, MATCH `CatalogEvidenceLink` by group_id + uuid/link_key and compare counts/identities; keep optional boolean provenance as additive, not sole check.

### Pitfall 7: Write transactions smuggled via shared helpers
**What goes wrong:** GATE-04 fail.
**How to avoid:** Read methods use only `_read_one`/`_read_many`/`execute_query`; never `write_*` or schema ensure; service-level spies in tests assert zero embedder/schema calls (existing resolve tests pattern).

## Code Examples

### Manifest load + reassembly (recommended shape)

```python
# Pattern: reuse store root-by-batch + full chunk payload load + pure reassembly
# Sources: catalog_store.build_read_manifest_root_by_batch_cypher,
#          catalog_prepared_artifact.reassemble_artifact_bytes,
#          catalog_manifest.manifest_sha256 / serialize_manifest_body

async def load_committed_manifest_body(store, driver, *, group_id: str, batch_id: str) -> dict:
    root = await store.read_manifest_root_for_recovery(driver, group_id=group_id, batch_id=batch_id)
    if not root:
        raise ManifestMismatch('manifest root missing')
    chunks = await store.load_manifest_chunks_with_payload(
        driver, manifest_uuid=str(root['uuid']), group_id=group_id
    )
    if len(chunks) != int(root['chunk_count']):
        raise ManifestMismatch('incomplete chunk set')
    raw = reassemble_artifact_bytes(
        chunks,
        expected_sha256=str(root['manifest_sha256']),
        expected_length=int(root['payload_bytes']),
    )
    if manifest_sha256(raw) != str(root['manifest_sha256']):
        raise ManifestMismatch('manifest digest mismatch')
    body = json.loads(raw.decode('utf-8'))
    # optional: re-serialize and re-hash for canonicalization drift detection
    return body
```

### Offset/limit over canonical categories

```python
# Categories already sorted in body (entities, edges, sources, evidence_links)
def page_members(items: list[dict], *, offset: int, limit: int) -> tuple[list[dict], int]:
    total = len(items)
    if offset < 0 or limit < 1:
        raise ValueError('invalid pagination')
    return items[offset : offset + limit], total
```

### Split read gate (required change)

```python
# Replace enabled check with reads_enabled
if not getattr(self.catalog_config, 'reads_enabled', True):
    return CatalogErrorCode.feature_disabled, 'catalog_upsert.reads_enabled is false'
# do NOT check self.catalog_config.enabled here
```

### Missing status found=false (GATE-05)

```python
# Extend CatalogIngestStatusResponse with found: bool = True (or default False careful)
# Missing row:
return CatalogIngestStatusResponse(
    group_id=group_id,
    batch_id=batch_id,
    batch_uuid=batch_uuid,
    found=False,
    status='failed',  # or dedicated not_found if model allows without lying
    error_code=None,  # prefer not validation_error
    error_summary='batch status not found',
)
```

## State of the Art (this codebase)

| Old Approach (pre-Phase 4) | Current Approach (Phase 4 target) | When Changed | Impact |
|----------------------------|-----------------------------------|--------------|--------|
| Read tools require write enable | Separate `reads_enabled` default true | Phase 4 | Diagnostics usable safely |
| Batch verify expected from live batch_id rows | Expected from durable manifest | Phase 4 | True membership verification |
| Missing status → failed+validation_error | `found=false` distinguishable | Phase 4 | Operators don't misread absence |
| `HARD_MAX_PAGE_SIZE=0` | Positive configured+hard ceilings | Phase 4 | Real pagination |
| `manifest_verification=false` | true only after proofs | End of Phase 4 | Capabilities honesty |
| Manifest write-only | Public read + verify authority | Phase 4 | MANI-05 / VERI-* |

**Deprecated/outdated:**
- Using `entity.batch_id` / `edge.batch_id` as membership authority (still may appear on rows as observation metadata only).
- Boolean-only provenance as sole evidence check when exact links exist (EVID-13).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Conservative default `max_page_size=100`, hard `500` is acceptable | D-04 discretion | User may want different ceilings; easy config change |
| A2 | Config field name `reads_enabled` under `catalog_upsert` is preferred | GATE-01 | Rename-only if discuss prefers sibling name |
| A3 | Verify response can stay backward-compatible via additive fields (`extras`, `manifest_sha256`, `evidence` section) without breaking existing clients | VERI-03/04 | If strict consumers reject unknown fields — unlikely for Pydantic responses |
| A4 | SUPERSEDED by Open Questions (RESOLVED) Q2 — edge writer always stores `e.content_sha256`; verify/resolve Cypher must RETURN it; null observation is anomaly not schema absence | RESE-01 | See Q2 RESOLVED |
| A5 | Live Neo4j optional for Phase 4 unit gate; retained 3B live proof sufficient until Phase 5 expansion | TEST-08/D-30 | Planner may still want one optional live smoke on tool-test group |

**If this table is empty:** N/A — five discretionary assumptions above need planner awareness only; none block planning.

## Open Questions (RESOLVED)

1. **Exact evidence-link MATCH shape for EVID-13**
   - What we know: write path creates `CatalogEvidenceLink` with `(uuid, group_id)` and `(group_id, link_key)` uniqueness; verify currently only boolean provenance. [VERIFIED: `catalog_store.py` constraints `CATALOG_EVIDENCE_LINK_IDENTITY_CONSTRAINT` / `CATALOG_EVIDENCE_LINK_KEY_CONSTRAINT` + `match_provenance_presence`]
   - Manifest body evidence_links members always carry `uuid`, `link_key`, `content_sha256` under Phase 3B canonicalization. [VERIFIED: `catalog_manifest.py` category projection `('evidence_links', 'link_key', ('uuid', 'link_key', 'content_sha256'))`]
   - **RESOLVED:** EVID-13 lookup authority is **`group_id + evidence-link uuid`** from the committed durable manifest member. MATCH `(:CatalogEvidenceLink {uuid: $uuid, group_id: $group_id})` (or equivalent parameterized form). After load, compare `link_key` and `content_sha256` as consistency properties — they are **not** alternate identity authorities. **Do not** fall back to `link_key`-only MATCH when uuid is present; that can hide uuid drift. If a manifest evidence member lacks uuid (non-canonical / corrupt body), fail closed as invalid manifest (`manifest_mismatch` / incomplete), never synthesize identity from live rows or link_key alone. Report missing expected uuids and extra live links as distinct diagnostics. Locked by D-08/D-09 and checker revision (prefer uuid when canonical manifest contains UUID).

2. **Edge `content_sha256` on live RELATES_TO**
   - What we know: entity verify returns content_sha256; edge verify Cypher currently omits it. [VERIFIED: `build_match_edges_for_verify_by_batch_cypher` / `_by_keys_cypher` RETURN lists at `catalog_store.py` ~904–946 omit `e.content_sha256`]
   - Writer always stores the property on upsert. [VERIFIED: `build_edge_upsert_cypher` sets `e.content_sha256 = $content_sha256` and RETURN includes `e.content_sha256 AS content_sha256`; `build_get_edge_by_uuid_cypher` also returns it]
   - **RESOLVED:** `content_sha256` **exists** on catalog RELATES_TO writes. Phase 4 edge resolve and any edge verify observation path **must** add `e.content_sha256 AS content_sha256` to the read RETURN. Expected edge content hash for batch verify comes from the durable manifest edge member (`content_sha256` field), not from inventing a hash. A null/missing live property is an **observation anomaly** (report; do not repair), not a permanent schema-optional field. Supersedes discretionary A4 “null-tolerant if absent from schema.”

3. **Committed batch without manifest (legacy pre-3B rows)**
   - What we know: VERI-05 / D-09 require `manifest_mismatch` for committed catalog-v2 batches lacking a valid durable manifest; GATE-05 / D-22 require missing status `found=false`.
   - **RESOLVED:**
     - Ingest/batch **status present and committed** (or equivalent committed catalog-v2 state) **and** durable manifest load/reassembly fails (missing root, incomplete chunks, digest mismatch, contradictory metadata) → **`CatalogErrorCode.manifest_mismatch`** (fail closed; never silent partial verify).
     - **Missing batch status entirely** → **`found=false`** (GATE-05 path); **not** `manifest_mismatch`, **not** committed success, **not** generic operational failure alone.
     - Never synthesize membership from live `batch_id` rows when manifest is invalid.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.12.10 | — |
| uv / mcp_server deps | Tests | ✓ | pydantic 2.11.7, pytest 9.0.3 | — |
| Neo4j live | Optional live proofs | Not probed (research ban) | — | Unit/service mocks; skip live |
| New npm/pip packages | — | N/A | — | None required |

**Missing dependencies with no fallback:** none for unit/service Phase 4.
**Missing dependencies with fallback:** live Neo4j — optional; mark live tests skip if unavailable.

Step 2.6 note: research deliberately does **not** open Neo4j connections (safety constraint).

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio (auto) |
| Config file | `mcp_server/pytest.ini` (canonical; package-root; used by Phase 1–3A gate runners and all 04-*-PLAN verify blocks) |
| Quick run command | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_capabilities.py -q --tb=line` |
| Full suite command (Phase 4 focused) | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_manifest_read.py mcp_server/tests/test_catalog_verify_manifest.py mcp_server/tests/test_catalog_resolve_edges.py mcp_server/tests/test_catalog_evidence_read.py mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_store_unit.py -q --tb=short` |
| Lint/type | `cd mcp_server && uv run ruff check src/services/catalog_*.py src/models/catalog_*.py src/config/schema.py src/graphiti_mcp_server.py && uv run pyright src/services/catalog_*.py src/models/catalog_*.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GATE-01 | Separate read/write defaults | unit | `pytest tests/test_catalog_gates.py::test_reads_enabled_default_true_writes_false -x` | ❌ Wave 0 |
| GATE-02 | Capabilities independent of gates | unit | `pytest tests/test_catalog_capabilities.py -k capabilities -x` | ✅ extend |
| GATE-03 | Reads work when writes disabled | unit/service | `pytest tests/test_catalog_gates.py::test_read_tools_when_writes_disabled -x` | ❌ Wave 0 |
| GATE-04 | No schema/write/embed on reads | unit spy | `pytest tests/test_catalog_gates.py::test_reads_no_schema_write_embed -x` | ❌ Wave 0 |
| GATE-05 | Missing status found=false | unit | `pytest tests/test_catalog_gates.py::test_missing_status_found_false -x` | ❌ Wave 0 |
| GATE-06 | group_id isolation on new Cypher | unit static/store | `pytest tests/test_catalog_store_unit.py -k group_id -x` | ✅ extend |
| MANI-05 | Paginated manifest membership | unit/service | `pytest tests/test_catalog_manifest_read.py -x` | ❌ Wave 0 |
| VERI-01 | Manifest expected membership | unit | `pytest tests/test_catalog_verify_manifest.py::test_batch_only_uses_manifest -x` | ❌ Wave 0 |
| VERI-02 | Expected counts ≠ live len | unit | `pytest tests/test_catalog_verify_manifest.py::test_expected_not_live_count -x` | ❌ Wave 0 |
| VERI-03 | Missing vs extra distinct | unit | `pytest tests/test_catalog_verify_manifest.py::test_missing_and_extra -x` | ❌ Wave 0 |
| VERI-04 | Type/UUID/endpoint/embed/evidence/hash | unit | `pytest tests/test_catalog_verify_manifest.py::test_consistency_checks -x` | ❌ Wave 0 |
| VERI-05 | No manifest → manifest_mismatch | unit | `pytest tests/test_catalog_verify_manifest.py::test_missing_manifest_code -x` | ❌ Wave 0 |
| VERI-06 | Explicit-key path preserved | unit | `pytest tests/test_catalog_verify_manifest.py::test_explicit_keys_only -x` | ✅ partial in service tests |
| RESE-01 | resolve_typed_edges fields | unit | `pytest tests/test_catalog_resolve_edges.py::test_resolve_fields -x` | ❌ Wave 0 |
| RESE-02 | Edge anomalies no repair | unit | `pytest tests/test_catalog_resolve_edges.py::test_anomalies -x` | ❌ Wave 0 |
| RESE-03 | Works writes-off, no embed | unit | `pytest tests/test_catalog_resolve_edges.py::test_writes_off -x` | ❌ Wave 0 |
| EVID-12 | get_catalog_evidence pagination | unit | `pytest tests/test_catalog_evidence_read.py::test_page -x` | ❌ Wave 0 |
| EVID-13 | Exact evidence identities in verify | unit | `pytest tests/test_catalog_verify_manifest.py::test_exact_evidence -x` | ❌ Wave 0 |
| IDEN-08 | Full graph keys on surfaces | unit | `pytest tests/test_catalog_manifest_read.py::test_graph_key_complete -x` | ❌ Wave 0 |
| TEST-08 | Unchanged members + twins | unit | `pytest tests/test_catalog_verify_manifest.py tests/test_catalog_resolve_edges.py -x` | ❌ Wave 0 |
| TEST-09 | Registration + legacy 14 | unit | `pytest tests/test_catalog_service.py::test_mcp_registers_exactly_* -x` | ✅ update count |

### Sampling Rate
- **Per task commit:** focused file(s) for that wave (`uv run pytest <files> -x`)
- **Per wave merge:** Phase 4 focused suite above
- **Phase gate:** focused suite green + ruff + pyright + registration exact set; optional live smoke only on `oracle-catalog-tool-test` if Neo4j available; never v2

### Wave 0 Gaps
- [ ] `mcp_server/tests/test_catalog_manifest_read.py` — MANI-05, IDEN-08, pagination stability, fail-closed reassembly
- [ ] `mcp_server/tests/test_catalog_verify_manifest.py` — VERI-01..06, EVID-13, TEST-08
- [ ] `mcp_server/tests/test_catalog_resolve_edges.py` — RESE-01..03
- [ ] `mcp_server/tests/test_catalog_evidence_read.py` — EVID-12
- [ ] `mcp_server/tests/test_catalog_gates.py` — GATE-01..06 (or expand existing service tests)
- [ ] Update `test_catalog_service.py` registration exact count 25→28 and `CATALOG_TOOL_NAMES` expectations
- [ ] Update `test_catalog_capabilities.py` for non-zero page size + `catalog_reads_enabled` from config + final `manifest_verification` flip test (last wave)

Existing assets to **reuse**, not replace: `test_catalog_manifest.py` (pure builder), `test_catalog_store_unit.py` (Cypher safety), resolve/verify tests in `test_catalog_service.py`, capabilities registration tests.

## Security Domain

> `security_enforcement` enabled; ASVS L1.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (MCP process auth out of phase) | — |
| V3 Session Management | no | — |
| V4 Access Control | yes | `group_id` isolation on every read; test group only |
| V5 Input Validation | yes | `CatalogStrictModel` extra=forbid; allowlisted types; page size ceilings |
| V6 Cryptography | yes (integrity) | SHA-256 manifest/chunk digests; no hand-rolled crypto |
| V7 Error Handling / Logging | yes | Structured codes; no payloads/tokens/source in logs |
| V13 API | yes | Thin tools; feature gates; no write side effects on reads |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher injection via labels/props | Tampering | Fixed server Cypher; params only |
| Cross-group data read | Elevation of privilege | Mandatory `group_id` MATCH; reject empty group_id |
| Manifest membership spoof via live rows | Spoofing | Manifest sole expected authority |
| Schema mutation on diagnostic call | Tampering | GATE-04: no ensure/repair on reads |
| Info leak via detailed projection | Information disclosure | Compact default; ban embeddings/payload/source/credentials |
| Feature flag lie (`manifest_verification`) | Spoofing | Flip only after proof; no `.planning` runtime read |
| DoS via huge page size | Denial of service | hard max_page_size fail closed |
| Write while "read" tool | Tampering | `_read_many` only; spies in tests |
| Historical v2 access | Elevation / policy | Never query `oracle-catalog-v2`; preserve `a67789a` audit as historical only |

### Inherited Phase 3B trust boundaries still binding
- MCP request → strict models
- Service → Neo4j parameterized values only
- Runtime → bounded response/log surface
- Two-axis safety: historical `a67789a` vs current execution

## Likely Plan Waves (for planner)

| Wave | Focus | Unblocks |
|------|-------|----------|
| 0 | RED tests / scaffolds for gates, manifest read, verify rewire, edge resolve, evidence | TDD |
| 1 | Config: `reads_enabled`, `max_page_size`; split `_read_gate`; GATE-05 `found`; capabilities truth (except verification flip) | All read tools |
| 2 | Store loaders: full chunk payload read, reassembly helper, evidence MATCH, edge resolve MATCH | Service tools |
| 3 | Service: `get_catalog_batch_manifest` pagination; pure page helper | MANI-05 |
| 4 | Service: rewire `verify_catalog_batch` manifest authority + extras + EVID-13 | VERI-* |
| 5 | Service: `resolve_typed_edges`, `get_catalog_evidence` | RESE/EVID-12 |
| 6 | MCP registration + CATALOG_TOOL_NAMES + TEST-09 count; flip `manifest_verification=true` after green; Phase 4 gate runner | Phase 5 |

## Sources

### Primary (HIGH confidence)
- `mcp_server/src/services/catalog_service.py` — `_read_gate`, `resolve_typed_entities`, `verify_catalog_batch`, `get_catalog_ingest_status` (lines ~1240–1795, ~3694–3793)
- `mcp_server/src/services/catalog_store.py` — verify MATCH Cypher, manifest root/chunk writers, `read_manifest_root_for_recovery`, chunk list without payload
- `mcp_server/src/services/catalog_manifest.py` — canonical membership order and counts
- `mcp_server/src/services/catalog_prepared_artifact.py` — `reassemble_artifact_bytes`
- `mcp_server/src/services/catalog_capabilities.py` — page size 0, `manifest_verification=False`, reads hardcoded True
- `mcp_server/src/config/schema.py` — `CatalogConfig.enabled` default false; no reads_enabled yet
- `mcp_server/src/models/catalog_entities.py` / `catalog_responses.py` / `catalog_common.py` — request/response shells; `manifest_mismatch` code
- `mcp_server/src/graphiti_mcp_server.py` — `CATALOG_TOOL_NAMES` (11 tools), registration pattern
- `mcp_server/tests/test_catalog_service.py` — LEGACY 14, exact 25 tool registration
- `.planning/phases/03B-*/03B-VERIFICATION.md`, `03B-SECURITY.md` — prerequisite proof and threat inheritance
- `.planning/REQUIREMENTS.md`, `ROADMAP.md`, `04-CONTEXT.md` — scope and locked decisions

### Secondary (MEDIUM confidence)
- Neo4j Python driver `execute_query` usage via `graphiti_core/driver/neo4j_driver.py` (read path already used by store)

### Tertiary (LOW confidence)
- None material; discretionary page size numbers marked [ASSUMED] in Assumptions Log (A1)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; versions verified in local uv env
- Architecture: HIGH — extension points and anti-patterns verified in source
- Pitfalls: HIGH — current failing contracts for GATE/VERI read directly from code
- Page size numeric defaults: LOW/ASSUMED — discretionary only

**Research date:** 2026-07-19
**Valid until:** 2026-08-18 (30 days; stable internal API)
**Worktree HEAD at research:** not mutated; product code untouched
**Phase 3B product gate HEAD (retained):** `1f9a7d75551fe5d1c0260f831102d2a8c5b83e18`
**Historical audit commit (immutable):** `a67789a04ca0cc2f2a56d7498c65be3460215f77`
