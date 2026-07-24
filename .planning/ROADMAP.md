# Roadmap: Deterministic Catalog Ingestion for Graphiti MCP

## Milestones

- [x] **v1.0 — Deterministic Catalog Ingestion** — Phases 1–2 (shipped 2026-07-17)
- [x] **v1.1 — Catalog-v2 Pre-Canary Hardening** — Phases 0–6 (shipped 2026-07-24)
- [ ] **v1.2 — FE/BO Catalog Pilot and Object Context** — Phases 7–10 (active)

## Overview

v1.2 proves representative FE/BO data from local `catalog/catalog.json` becomes deterministic, evidence-backed graph context agents can read from a newly built image. Offline converter emits bounded pilot artifacts; existing prepare/token-commit substrate ingests them into isolated per-run groups; one new read-only MCP tool returns exact object context with one-hop neighbors and evidence. Delta acceptance plus source-bound image smoke close the milestone — no v1.1 canary replay, no full ingest, no production promotion.

## Shipped Milestones

<details>
<summary>✅ v1.0 — Deterministic Catalog Ingestion (Phases 1–2) — SHIPPED 2026-07-17</summary>

Archive: [roadmap](milestones/v1.0-ROADMAP.md) · [requirements](milestones/v1.0-REQUIREMENTS.md) · [audit](milestones/v1.0-MILESTONE-AUDIT.md) · [phases](milestones/v1.0-phases/)

Seven additive Neo4j catalog MCP tools; UUIDv5 identity; canonical SHA-256; fixed allowlists; 86/86 requirements.

</details>

<details>
<summary>✅ v1.1 — Catalog-v2 Pre-Canary Hardening (Phases 0–6) — SHIPPED 2026-07-24</summary>

Archive: [roadmap](milestones/v1.1-ROADMAP.md) · [requirements](milestones/v1.1-REQUIREMENTS.md) · [audit](milestones/v1.1-MILESTONE-AUDIT.md) · [phases](milestones/v1.1-phases/)

Strict catalog-v2 contracts, immutable prepare/commit, exact evidence, manifests, diagnostics, source-bound native-Ollama final canary Gates 0–10 PASSED. 215/215 requirements. Accepted debt `DEV-P6-POST-ID-EVIDENCE-COMMITS`. v1.1 prepare/commit substrate reused by v1.2 — not rebuilt.

</details>

## Phases

**v1.2 FE/BO Catalog Pilot and Object Context**

**Phase numbering:** Continues after v1.1 Phase 6. Integer phases only unless urgent insertion.

**Parallelism:** Phase 7 (offline converter/artifacts) and Phase 8 (object-context runtime) are independent until Phase 9 joins them. Phase 10 depends on Phase 9.

- [ ] **Phase 7: Offline Pilot Conversion** - Deterministic FE/BO samples from local catalog authority into reviewable pilot artifacts
- [ ] **Phase 8: Exact Object Context** - Read-only `get_catalog_object_context` with bounded one-hop neighbors and evidence
- [ ] **Phase 9: Isolated FE/BO Integration** - Prepare/commit pilot samples and prove context/search/replay in per-run groups
- [ ] **Phase 10: Image and Delta Acceptance** - Source-bound image, runtime smoke, delta acceptance receipts, honest final report

## Phase Details

### Phase 7: Offline Pilot Conversion
**Goal**: Operator converts only local `catalog/catalog.json` into deterministic FE and BO catalog-v2 prepare payloads under `catalog/pilot-v12-requests/` with no LLM, network, Neo4j, or semantic-ingestion side effects
**Depends on**: Nothing (v1.1 prepare/commit substrate already shipped; this phase is offline-only)
**Requirements**: PILT-01, PILT-02, PILT-03, PILT-04, PILT-05, PILT-06, PILT-07, PILT-08, PILT-09, PILT-10
**Success Criteria** (what must be TRUE):
  1. Operator runs offline converter against only `catalog/catalog.json`; process performs no LLM, Docling, network, Neo4j, or semantic-ingestion calls
  2. Malformed UTF-8/BOM, duplicate JSON keys, non-finite numbers, wrong nested shapes, and duplicate or ambiguous deterministic identities fail before any pilot artifact is published
  3. Converter verifies inventory (schema_version, 2 documents, 1,261 tables, 10,649 columns, 434 FE-only relationships), records authoritative raw SHA-256, and emits FE connected `SVFE_SHB` plus BO structural `MAIN1` samples using database token `SHB` and matching FE/BO catalog-v2 planes
  4. Generated objects preserve exact names, source document/page/excerpt, normalization data, and confidence; FE/BO outputs validate as catalog-v2 prepare requests with explicit evidence links inside 500/2,000/5,000 batch limits; bare FE relationship endpoints resolve uniquely or fail closed
  5. Reordered equivalent input yields byte-identical payloads and manifests in `catalog/pilot-v12-requests/`; v1.1 canary directories remain byte-identical; full `catalog/catalog.json` stays untracked local authority while committed pilot digests/manifests remain reproducible when authority SHA matches
**Plans**: TBD
**Parallel**: Can run alongside Phase 8

### Phase 8: Exact Object Context
**Goal**: Agent retrieves one compact exact catalog object context — typed focal details, bounded immediate neighbors, and paginated evidence — with zero writes
**Depends on**: Nothing (reads existing committed catalog-v2 graph shape; independent of pilot converter)
**Requirements**: CTX-01, CTX-02, CTX-03, CTX-04, CTX-05, CTX-06, CTX-07, CTX-08, CTX-09, CTX-10
**Success Criteria** (what must be TRUE):
  1. Agent calls `get_catalog_object_context` with strict `catalog-v2`, `system_key`, `group_id`, entity type, graph key, and bounded pagination fields; capabilities advertise support and limits even while catalog writes are disabled
  2. Exact identity returns one focal object with allowlisted typed details, deterministic UUID, labels, raw/canonical names, graph key, summary, attributes, and content hash; absence and duplicate/inconsistent identity return structured results without arbitrary selection
  3. Response includes immediate incoming/outgoing `RELATES_TO` edges plus typed neighbor projections only (no second hop, no inferred relation); neighbor default 50, hard max 200, stable order, truncation reported
  4. Response includes paginated compact evidence (kind, bounded excerpt, document/page locator, extractor metadata, confidence) and excludes images, complete documents, unbounded source text, embeddings, credentials, and plan tokens
  5. Every focal, neighbor, edge, and evidence read is constrained by `group_id` and exact typed identity; success/missing/validation/failure paths perform no writes, schema creation, embedding, LLM, queue, repair, or timestamp mutation
**Plans**: TBD
**Parallel**: Can run alongside Phase 7

### Phase 9: Isolated FE/BO Integration
**Goal**: FE and BO pilot payloads commit through existing immutable prepare/token-commit into a fresh per-run group, and agents observe correct context, search hits, and replay idempotence against an empty control group
**Depends on**: Phase 7, Phase 8
**Requirements**: INTG-01, INTG-02, INTG-03, INTG-04, INTG-05, INTG-06, INTG-07, INTG-08
**Success Criteria** (what must be TRUE):
  1. Acceptance allocates `oracle-catalog-v12-pilot-<run_id>` plus a distinct empty control group and rejects protected group IDs; never calls `clear_graph`, deletes existing data, writes protected/live groups, or cleans preserved runtime stacks
  2. FE and BO payloads use separate immutable prepare operations and separate token-only commits in the same per-run graph group; native Ollama `qwen3-embedding:0.6b` at 1,024 dimensions; zero generative LLM calls recorded
  3. Manifest-backed verification confirms exact committed identities, endpoints, evidence links, hashes, and counts for both samples; replay of equivalent pilot input creates no duplicate identity and preserves protected creation/name/endpoint fields
  4. Agent retrieves correct context for FE table, FE column, and BO table including expected one-hop relations and source evidence; existing node/fact search finds representative committed catalog data while empty control group returns no corresponding data
**Plans**: TBD

### Phase 10: Image and Delta Acceptance
**Goal**: Operator builds one source-bound v1.2 image and completes delta acceptance that proves changed pilot/context behavior plus runtime smoke without replaying v1.1 Gates 0–10 or claiming production readiness
**Depends on**: Phase 9
**Requirements**: ACPT-01, ACPT-02, ACPT-03, ACPT-04, ACPT-05, ACPT-06, ACPT-07, ACPT-08
**Success Criteria** (what must be TRUE):
  1. Operator builds standalone v1.2 image recording committed source revision and immutable image digest without claiming old-digest equivalence; image contains runtime code only and excludes `.planning`, `catalog/catalog.json`, `extracted/`, generated tokens, local overrides, credentials, and runtime evidence
  2. Complete-image and history scans fail closed on credentials, catalog payloads, forbidden paths, or unparseable scan coverage
  3. Runtime smoke proves health, exact 29-tool registry (28 prior + `get_catalog_object_context`), object-context capability, Neo4j connectivity, and Ollama readiness
  4. Delta acceptance executes pilot prepare/commit, verify, context, search, replay, and control-isolation checks; emits bounded receipts/ledger; validates v1.2 changes and packaging without rerunning v1.1 Gates 0–10 or its final canary
  5. Final report states exact tested source/image/runtime authority, representative-sample limits, BO zero-relationship limitation, and no production-readiness overclaim; milestone performs no image push, retag, deployment, production promotion, live-group write, full ingest, graph cleanup, or unrelated working-tree mutation
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order. Phase 7 and Phase 8 may proceed in parallel; Phase 9 waits for both; Phase 10 waits for Phase 9.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 0–6 (archived) | v1.1 | 53/55 by contract | Complete | 2026-07-24 |
| 7. Offline Pilot Conversion | v1.2 | 0/TBD | Not started | - |
| 8. Exact Object Context | v1.2 | 0/TBD | Not started | - |
| 9. Isolated FE/BO Integration | v1.2 | 0/TBD | Not started | - |
| 10. Image and Delta Acceptance | v1.2 | 0/TBD | Not started | - |

## Coverage

| Category | Requirements | Phase |
|----------|--------------|-------|
| Pilot Authority and Conversion | PILT-01 … PILT-10 (10) | Phase 7 |
| Exact Object Context | CTX-01 … CTX-10 (10) | Phase 8 |
| Isolated FE/BO Integration | INTG-01 … INTG-08 (8) | Phase 9 |
| Image and Delta Acceptance | ACPT-01 … ACPT-08 (8) | Phase 10 |

**Coverage:** 36/36 v1.2 requirements mapped. 0 orphans. 0 duplicates.

## Confirmed Decisions (v1.2)

| Decision | Binding |
|----------|---------|
| Database token | `SHB` |
| Pilot groups | `oracle-catalog-v12-pilot-<run_id>` + distinct empty control |
| Neighbor bounds | default 50, hard max 200 |
| Categories | all four (PILT, CTX, INTG, ACPT) |
| Object-context images | none |
| New dependencies | zero |
| v1.1 final canary | do not replay |
| Authority | untracked local `catalog/catalog.json`; pilot artifacts pin raw SHA-256 for reproduce/verify |
| Ingest substrate | reuse v1.1 prepare/commit; do not rebuild |

## Operational Boundary

Production promotion remains separate future work. No push, tag, deployment, image rebuild-as-equivalent, canary rerun of v1.1, live-group write, full ingest, graph cleanup, or final/historical runtime cleanup is authorized by this milestone.

---
*Roadmap created: 2026-07-24 for milestone v1.2*
*Phases 7–10 · 36 requirements · granularity standard*
