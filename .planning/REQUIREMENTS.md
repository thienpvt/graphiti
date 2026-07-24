# Requirements: FE/BO Catalog Pilot and Object Context

**Defined:** 2026-07-24
**Milestone:** v1.2
**Core Value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.

## v1.2 Requirements

### Pilot Authority and Conversion

- [ ] **PILT-01**: Operator can convert only `catalog/catalog.json`; converter performs no LLM, Docling, network, Neo4j, or semantic-ingestion calls.
- [ ] **PILT-02**: Malformed UTF-8/BOM, duplicate JSON keys, non-finite numbers, wrong nested shapes, and duplicate deterministic identities fail before artifact publication.
- [ ] **PILT-03**: Converter verifies `schema_version`, 2 documents, 1,261 tables, 10,649 columns, and 434 FE-only relationships, then records authoritative raw SHA-256.
- [ ] **PILT-04**: Every generated key uses database token `SHB` and matching `FE` or `BO` catalog-v2 plane.
- [ ] **PILT-05**: Bare relationship endpoints resolve uniquely inside FE authority; missing or ambiguous endpoints fail rather than being guessed.
- [ ] **PILT-06**: FE selection produces deterministic connected `SVFE_SHB` sample containing authoritative relationship endpoints.
- [ ] **PILT-07**: BO selection produces deterministic structurally rich `MAIN1` sample without inferred BO relationships.
- [ ] **PILT-08**: Generated objects preserve exact `name_raw`, `name_canonical`, source document ID, page, raw excerpt, normalization data, and supplied confidence.
- [ ] **PILT-09**: FE and BO outputs validate as catalog-v2 prepare requests with explicit evidence links and remain within 500/2,000/5,000 batch limits.
- [ ] **PILT-10**: Reordered equivalent input produces byte-identical payloads and manifests in new `catalog/pilot-v12-requests/`; v1.1 canary directories remain byte-identical.

### Exact Object Context

- [ ] **CTX-01**: Agent can call `get_catalog_object_context` using strict `catalog-v2`, `system_key`, `group_id`, entity type, graph key, and bounded pagination fields.
- [ ] **CTX-02**: Exact identity returns one focal object; absence and duplicate/inconsistent identity return structured results without arbitrary selection.
- [ ] **CTX-03**: Focal response contains allowlisted typed details, deterministic UUID, labels, raw/canonical names, graph key, summary, attributes, and content hash without embeddings or protected internals.
- [ ] **CTX-04**: Response contains immediate incoming and outgoing `RELATES_TO` edges plus typed neighbor projections; no second hop or inferred relation.
- [ ] **CTX-05**: Neighbor default is 50, hard maximum is 200, order is stable, and response reports truncation.
- [ ] **CTX-06**: Response contains paginated compact evidence with evidence kind, bounded excerpt, document/page locator, extractor metadata, and confidence.
- [ ] **CTX-07**: Response excludes images, complete documents, unbounded source text, embeddings, credentials, and plan tokens.
- [ ] **CTX-08**: Every focal, neighbor, edge, and evidence read is constrained by `group_id` and exact typed identity.
- [ ] **CTX-09**: Success, missing, validation, and failure paths perform no writes, schema creation, embedding, LLM, queue, repair, or timestamp mutation.
- [ ] **CTX-10**: Agent can discover object-context support and limits through capabilities, including while catalog writes are disabled.

### Isolated FE/BO Integration

- [ ] **INTG-01**: Acceptance allocates `oracle-catalog-v12-pilot-<run_id>` and distinct empty control group; protected group IDs are rejected.
- [ ] **INTG-02**: FE and BO payloads use separate immutable prepare operations and separate token-only commits within same per-run graph group.
- [ ] **INTG-03**: Acceptance uses native Ollama `qwen3-embedding:0.6b` at 1,024 dimensions and records zero generative LLM calls.
- [ ] **INTG-04**: Manifest-backed verification confirms exact committed identities, endpoints, evidence links, hashes, and counts for both samples.
- [ ] **INTG-05**: Agent retrieves correct context for FE table, FE column, and BO table, including expected one-hop relations and source evidence.
- [ ] **INTG-06**: Existing node/fact search finds representative committed catalog data while empty control group returns no corresponding data.
- [ ] **INTG-07**: Replaying equivalent pilot input creates no duplicate identity and preserves protected creation/name/endpoint fields.
- [ ] **INTG-08**: Acceptance never calls `clear_graph`, deletes existing data, writes protected/live groups, or cleans preserved runtime stacks.

### Image and Delta Acceptance

- [ ] **ACPT-01**: Operator can build source-bound standalone v1.2 image recording committed source revision and immutable image digest without claiming old-digest equivalence.
- [ ] **ACPT-02**: Image contains runtime code only; excludes `.planning`, `catalog/catalog.json`, `extracted/`, generated tokens, local overrides, credentials, and runtime evidence.
- [ ] **ACPT-03**: Complete-image and history scans fail closed on credentials, catalog payloads, forbidden paths, or unparseable scan coverage.
- [ ] **ACPT-04**: Runtime smoke proves health, exact 29-tool registry, object-context capability, Neo4j connectivity, and Ollama readiness.
- [ ] **ACPT-05**: Delta acceptance executes pilot prepare/commit, verify, context, search, replay, and control-isolation checks and emits bounded receipts/ledger.
- [ ] **ACPT-06**: Acceptance validates v1.2 changes and runtime packaging without rerunning v1.1 Gates 0–10 or its final canary.
- [ ] **ACPT-07**: Final report states exact tested source/image/runtime authority, representative-sample limits, BO zero-relationship limitation, and no production-readiness overclaim.
- [ ] **ACPT-08**: Milestone performs no image push, retag, deployment, production promotion, live-group write, full ingest, graph cleanup, or unrelated working-tree mutation.

## Future Requirements

### Rich Retrieval

- **RETR-01**: Agent can request bounded multi-hop paths with evidence on every returned edge.
- **RETR-02**: Agent can request bounded upstream/downstream impact analysis with explicit completeness limits.
- **RETR-03**: Agent can issue a natural-language query that resolves candidates before exact context assembly.

### Cross-System Knowledge

- **MAPS-01**: Operator can ingest explicit evidence-backed FE-to-BO object mappings.
- **MAPS-02**: Agent can distinguish documented mappings from proposed or inferred mappings.

### Catalog Lifecycle

- **LIFE-01**: Operator can compare catalog snapshots and deterministically retire missing objects without deleting history.
- **LIFE-02**: Agent can retrieve current and retired catalog state with temporal evidence.

### Full Catalog Operations

- **OPER-01**: Operator can ingest complete FE/BO catalog through bounded resumable partitions with whole-run verification.
- **OPER-02**: Operator can promote a tested image digest through an explicitly approved production rollout.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full 1,261-table ingest | v1.2 proves representative bounded samples only |
| BO relationship inference | Normalized authority contains zero BO relationships; invented graph truth is forbidden |
| FE-to-BO mapping | Requires separate evidence/schema approval |
| Natural-language context orchestration | Exact typed context comes first |
| Multi-hop paths or impact analysis | One-hop object context bounds v1.2 scope |
| Docling regeneration or cross-check | `catalog/catalog.json` is normalized authority for this milestone |
| LLM extraction or normalization | Deterministic converter must perform no LLM calls |
| Object-context images | User requested object details, relationships, evidence, confidence, and locators only |
| Automatic catalog-v1 migration | Existing identities must never be silently reinterpreted |
| Production promotion or deployment | Requires separate explicit approval after acceptance |
| Image push, retag, or Kubernetes action | Milestone produces local tested digest only |
| v1.1 final canary replay | v1.1 substrate already passed; v1.2 validates delta only |
| Live/protected group writes | Acceptance uses new per-run isolated groups only |
| Graph clearing or existing-data deletion | Destructive cleanup remains forbidden |
| FalkorDB, Kuzu, or Neptune catalog claims | Neo4j-only implementation and proof |
| New runtime or dev dependencies | Existing stack and stdlib cover milestone |

## Traceability

Populated during roadmap creation. Every v1.2 requirement must map to exactly one roadmap phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PILT-01 | TBD | Pending |
| PILT-02 | TBD | Pending |
| PILT-03 | TBD | Pending |
| PILT-04 | TBD | Pending |
| PILT-05 | TBD | Pending |
| PILT-06 | TBD | Pending |
| PILT-07 | TBD | Pending |
| PILT-08 | TBD | Pending |
| PILT-09 | TBD | Pending |
| PILT-10 | TBD | Pending |
| CTX-01 | TBD | Pending |
| CTX-02 | TBD | Pending |
| CTX-03 | TBD | Pending |
| CTX-04 | TBD | Pending |
| CTX-05 | TBD | Pending |
| CTX-06 | TBD | Pending |
| CTX-07 | TBD | Pending |
| CTX-08 | TBD | Pending |
| CTX-09 | TBD | Pending |
| CTX-10 | TBD | Pending |
| INTG-01 | TBD | Pending |
| INTG-02 | TBD | Pending |
| INTG-03 | TBD | Pending |
| INTG-04 | TBD | Pending |
| INTG-05 | TBD | Pending |
| INTG-06 | TBD | Pending |
| INTG-07 | TBD | Pending |
| INTG-08 | TBD | Pending |
| ACPT-01 | TBD | Pending |
| ACPT-02 | TBD | Pending |
| ACPT-03 | TBD | Pending |
| ACPT-04 | TBD | Pending |
| ACPT-05 | TBD | Pending |
| ACPT-06 | TBD | Pending |
| ACPT-07 | TBD | Pending |
| ACPT-08 | TBD | Pending |

**Coverage:**
- v1.2 requirements: 36 total
- Mapped to phases: 0
- Unmapped: 36

---
*Requirements defined: 2026-07-24*
*Last updated: 2026-07-24 after v1.2 scope approval*
