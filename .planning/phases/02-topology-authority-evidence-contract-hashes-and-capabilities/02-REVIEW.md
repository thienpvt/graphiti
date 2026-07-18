---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
reviewed: 2026-07-18T00:00:00Z
depth: deep
files_reviewed: 18
files_reviewed_list:
  - mcp_server/src/graphiti_mcp_server.py
  - mcp_server/src/models/catalog_batch.py
  - mcp_server/src/models/catalog_edges.py
  - mcp_server/src/models/catalog_evidence.py
  - mcp_server/src/models/catalog_responses.py
  - mcp_server/src/models/catalog_topology.py
  - mcp_server/src/services/catalog_capabilities.py
  - mcp_server/src/services/catalog_identity.py
  - mcp_server/src/services/catalog_service.py
  - mcp_server/tests/catalog_phase2_gate_runner.py
  - mcp_server/tests/run_phase2_gate.py
  - mcp_server/tests/test_catalog_capabilities.py
  - mcp_server/tests/test_catalog_evidence.py
  - mcp_server/tests/test_catalog_hash.py
  - mcp_server/tests/test_catalog_models.py
  - mcp_server/tests/test_catalog_phase2_gate_runner.py
  - mcp_server/tests/test_catalog_service.py
  - mcp_server/tests/test_catalog_topology.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: findings
---

# Phase 2: Code Review Report

**Reviewed:** 2026-07-18T00:00:00Z
**Depth:** deep
**Files Reviewed:** 18
**Status:** findings

## Summary

Deep cross-file review of Phase 2 topology authority, evidence contract, authoritative hashing, capabilities, MCP registration, service preflight ordering, and the fail-closed gate runner.

Solid core: single `EDGE_ENDPOINT_MAP` authority, exclusive evidence targets, Cartesian rejection, pure versioned request hash with order-invariant collections, mutation-free capabilities + namespace fingerprint redaction, gate runner fail-closed derivation, and focused unit coverage.

Real defects remain on HASH-05 gate-failure echo, configured provenance limit accounting (sources vs evidence_links), committed-replay provenance counts, and incomplete CAPA-06 pagination surface. TDD missing RED commit noted as process advisory only (not a code defect). Primary gate green claims (918/390/15, Ruff/Pyright, edge-probe 68/68) accepted as operational context; this review is adversarial against source contracts, not a re-run of the gate.

## Narrative Findings (AI reviewer)

### Critical Issues

### CR-01: Gate-failure batch responses omit authoritative `request_sha256` / `canonicalization_version`

**File:** `mcp_server/src/services/catalog_service.py:3687-3701`
**Issue:** `_batch_gate_error` early return (feature disabled, invalid namespace, non-Neo4j backend, configured batch limits) builds `CatalogBatchWriteResponse` with only `identity_schema_version` and `catalog_sha256`. It never calls `batch_request_sha256` / `_batch_hash_echo_fields`, so `request_sha256` and `canonicalization_version` stay `None`.

HASH-05 and Phase 2 context require every `upsert_catalog_batch` result — including dry-run **and safe failures where derivable** — to echo `identity_schema_version`, `canonicalization_version`, server `request_sha256`, `catalog_sha256`, and `batch_uuid` when derivable. Request hash is pure over the validated request and does not need namespace, Neo4j, or embeddings. Gate failures are therefore "derivable" failures; current order computes the hash only **after** the gate.

Mismatch/content-hash paths correctly use `**hash_echo` (lines 3704-3718). Gate path does not. No service test covers batch `feature_disabled` / `invalid_uuid_namespace` hash echo (blind spot).

**Impact:** Clients cannot reconcile audit hashes on the most common pre-write failures; contract drift vs dry-run / mismatch responses; Phase 3A prepare planning cannot rely on uniform hash echo.

**Fix:**
```python
# Compute hash echo before gate when request is already model-validated.
server_hash = self.batch_request_sha256(request)
hash_echo = self._batch_hash_echo_fields(request, server_hash)
gate = self._batch_gate_error(client, request)
if gate is not None:
    code, message = gate
    return CatalogBatchWriteResponse(
        group_id=request.group_id,
        batch_id=request.batch_id,
        batch_uuid=batch_uuid,
        dry_run=request.dry_run,
        status='failed',
        failed=max(len(request.entities) + len(request.edges), 1),
        error_code=code,
        error_message=message,
        **hash_echo,
    )
```
Add unit tests: feature-disabled, invalid-namespace, backend-unavailable, and limit-exceeded batch paths all assert non-null `request_sha256` matching `batch_request_sha256(request)` and `canonicalization_version == CANONICALIZATION_VERSION`, with zero store/embed calls.

## Warnings

### WR-01: Configured provenance limit counts only `evidence_links`, not `sources`

**File:** `mcp_server/src/services/catalog_service.py:3609-3624`
**Issue:** `_batch_gate_error` sets
```python
provenance_link_count = (
    len(request.provenance.evidence_links) if request.provenance is not None else 0
)
```
and compares that sole count to `max_provenance_links_per_batch`. `NestedProvenancePayload` allows sources-only batches (`sources` or `evidence_links`), and both collections are independently capped at `HARD_MAX_PROVENANCE_LINKS_PER_BATCH` (20000) at the model layer. A request with N sources and 0 evidence links therefore bypasses the **configured** provenance limit (default 5000) until the hard ceiling.

`test_batch_gate_counts_evidence_links_not_cartesian` only exercises multi-link evidence; no test asserts sources are gated by the configured max.

**Impact:** Operators who lower `max_provenance_links_per_batch` still accept up to 20000 source episodes per batch. Write amplification / resource bound intended by CONF-04 / project scale limits is incomplete for the sources collection.

**Fix:** Count both collections under the configured cap (or define an explicit dual limit and document it). Minimal fail-closed option:
```python
provenance = request.provenance
if provenance is not None:
    source_count = len(provenance.sources)
    link_count = len(provenance.evidence_links)
else:
    source_count = link_count = 0
# Enforce configured max against each, or max(source_count, link_count), or source_count + link_count
# Prefer the strictest documented semantics; recommend:
for count, label in (
    (source_count, 'provenance sources'),
    (link_count, 'provenance links'),
):
    if count > self.catalog_config.max_provenance_links_per_batch:
        return (
            CatalogErrorCode.batch_limit_exceeded,
            f'{label} exceed configured batch maximum '
            f'({self.catalog_config.max_provenance_links_per_batch})',
        )
```
Add a unit test with `max_provenance_links_per_batch=1`, two sources, zero links → `batch_limit_exceeded`, no store/embed.

### WR-02: Committed idempotent replay undercounts `provenance_unchanged`

**File:** `mcp_server/src/services/catalog_service.py:3745-3758`
**Issue:** On committed same-hash replay:
```python
provenance_unchanged=(
    len(request.provenance.sources) if request.provenance is not None else 0
),
```
Evidence-link-only batches (valid under `NestedProvenancePayload`) report `provenance_unchanged=0` even though the request carried links and the hash matched. Links are part of the authoritative request domain (HASH-02) and the committed batch identity, but replay accounting ignores them.

**Impact:** Misleading success metrics / agent reconciliation on evidence-only or mixed batches; future manifest membership counts can disagree with replay echoes.

**Fix:**
```python
prov = request.provenance
if prov is None:
    provenance_unchanged = 0
else:
    provenance_unchanged = len(prov.sources) + len(prov.evidence_links)
```
Or return separate source/link unchanged fields if the response model is extended. Cover with a dry-run-free committed-replay unit test using sources=[] and one evidence_link.

### WR-03: Capabilities hard limits omit pagination (CAPA-06 incomplete)

**File:** `mcp_server/src/services/catalog_capabilities.py:113-127`
**Issue:** CAPA-06 requires configured + immutable hard limits for entities, edges, provenance sources, evidence links, prepared payload bytes, active plans, TTL, **and pagination**. Response `limits.hard` exposes prepared/plan/TTL placeholders (0) and batch collection ceilings, but no pagination keys (`max_page_size`, etc.). `limits.configured` likewise has no pagination.

**Impact:** Agents cannot discover read pagination ceilings from the capabilities tool; Phase 4 evidence/manifest readers will invent ad-hoc limits or drift from a missing authority.

**Fix:** Add explicit pagination hard/configured keys now (even if Phase 2 values are placeholders or current read defaults), e.g.:
```python
'hard': {
    ...,
    'max_page_size': HARD_MAX_PAGE_SIZE,  # define constant, even if 0/placeholder
},
'configured': {
    ...,
    'max_page_size': getattr(config, 'max_page_size', HARD_MAX_PAGE_SIZE),
},
```
Extend `test_catalog_capabilities.py` to assert pagination keys exist on both maps.

## Info

### IN-01: `CATALOG_TOOL_NAMES` SAFE-08 set still excludes `get_catalog_capabilities`

**File:** `mcp_server/src/graphiti_mcp_server.py:208-217`
**Issue:** Frozen SAFE-08 rewrite set lists the original seven request tools only. `get_catalog_capabilities` is registered and listed in service registration tests, but validation errors on that tool would not receive structured catalog ToolError rewriting. Currently the tool takes no request model, so practical impact is near zero.
**Fix:** When capabilities gains parameters, add it to `CATALOG_TOOL_NAMES` (or rename the set to request-tools-only and document the split). Optional now: include it for future-proofing.

### IN-02: Evidence-link UUID helper unused on write path (Phase 3B deferred)

**File:** `mcp_server/src/services/catalog_identity.py:59-63` (helper); `mcp_server/src/services/catalog_service.py:4087-4428` (batch provenance)
**Issue:** `catalog_evidence_link_uuid` / `evidence_link_key` exist and feed request hashing coalesce, but `upsert_catalog_batch` never assigns evidence-link UUIDs or validates per-link `content_sha256` against `evidence_canonical_payload`. Links only expand into source→target MENTIONS / edge episode attachment sets. Acceptable under Phase 2 deferral of evidence persistence (EVID-07..11 / 3B), but easy to misread as complete evidence identity enforcement.
**Fix:** No Phase 2 code change required. Phase 3B must wire UUID + content-hash checks and stop treating links as pure target expanders. Add a code comment at the batch evidence loop stating persistence is out of scope for Phase 2.

## Cross-file notes (no extra findings)

- Topology: `EDGE_ENDPOINT_MAP` keys match `CATALOG_EDGE_TYPES` (16); deferred types absent; `CatalogEdgeItem` + service preflight share `validate_edge_endpoint_pair` before embed/tx.
- Evidence model: exclusive target, kind allowlist, finite confidence, SHA-256 format, Cartesian rejected in `NestedProvenancePayload` without conversion.
- Hash recipe: single `CANONICALIZATION_VERSION`, excludes `dry_run` / caller `request_sha256`, order-invariant entity/edge/source/evidence collections, byte-identical evidence coalesce — covered by `test_catalog_hash.py`.
- Capabilities: no `get_client`, no schema/index mutation, fingerprint domain-separated SHA-256 prefix, raw namespace never returned; `get_status` `status`/`message` preserved.
- Gate runner: shell-exec forbid, integration module forbid, mandatory exit=0 specs, sentinel `assert False` expected nonzero and excluded from aggregation, `ready_for_phase_3a` requires local pass + safety flags; fail-closed integrity looks sound.
- Process: missing TDD RED commit is advisory only — not filed as a code defect.

---

_Reviewed: 2026-07-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
