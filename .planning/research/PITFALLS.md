# Pitfalls Research

**Domain:** v1.2 FE/BO Catalog Pilot and Object Context
**Researched:** 2026-07-24
**Confidence:** HIGH

## Critical Pitfalls

### 1. Input Digest Drift, Duplicate Identity, and Invalid Shape

**What Goes Wrong:** Preparation accepts changed or malformed `catalog/catalog.json`, silently collapses duplicate logical objects, or permits NaN/infinity values that defeat stable validation and serialization. Commit token then describes input other than input reviewed.

**Warning Signs:** Digest differs between prepare and commit; duplicate canonical keys appear; counts vary across identical runs; JSON parsing accepts non-finite constants; nested shapes differ from expected documents/tables/columns/relationships structure.

**Prevention/Tests:** Stream-read bounded input, compute and retain cryptographic digest, reject duplicate deterministic identities before writes, reject non-finite numbers explicitly, validate complete nested shape and exact collection limits, and test malformed roots, missing fields, duplicate keys, NaN, infinity, and digest mismatch.

**Phase:** Input contract and prepare gate.

### 2. Nondeterministic or Biased FE/BO Sample Selection

**What Goes Wrong:** Pilot sample changes with file order, map iteration, database return order, or operator choice. FE sample may look connected only by chance; BO sample may favor convenient tables and conceal structural weaknesses.

**Warning Signs:** Repeated preparation emits different samples; selected objects depend on insertion order; FE connectivity is asserted without deterministic traversal; BO selection uses relationships despite authoritative input containing zero BO relations.

**Prevention/Tests:** Define stable ordering and tie-breakers, avoid randomness, select FE from verified connected components, select BO by deterministic structural-richness score, record selection rationale, and assert byte-identical manifests across repeated runs and reordered equivalent input.

**Phase:** Pilot sample design.

### 3. FE/BO Database-Token Identity Collision

**What Goes Wrong:** Identical table or column names from FE and BO map to same identity because deterministic key omits database token. Upserts merge distinct catalog objects and corrupt endpoint ownership.

**Warning Signs:** UUID fixtures match across FE and BO for same qualified object name; canonical keys start at schema/table level; counts shrink after mixed-database preparation; object context returns cross-database properties.

**Prevention/Tests:** Include normalized database token in every table, column, and relationship identity preimage; keep FE and BO tokens explicit; add collision fixtures using identical schema/table/column names in both databases; assert distinct UUIDv5 values and isolated reads.

**Phase:** Identity contract before ingestion.

### 4. Bare Foreign-Key Endpoint Qualification

**What Goes Wrong:** Relationship endpoints represented as bare table or column names bind to wrong schema or database. Ambiguous references may pass string validation but create false edges.

**Warning Signs:** Endpoint resolver chooses first name match; endpoint keys omit database or schema; duplicate table names exist; unresolved references are guessed; relationship manifests lack fully qualified endpoint evidence.

**Prevention/Tests:** Require full server-defined endpoint qualification, resolve against prepared object index only, reject ambiguity and missing endpoints, never infer schema/database from proximity, and test same-name objects across schemas and FE/BO tokens.

**Phase:** Relationship normalization and validation.

### 5. Invented BO Relationships or Semantics

**What Goes Wrong:** Implementation fabricates BO foreign keys, joins, ownership, or business meaning to make BO appear connected. This violates source fidelity: authoritative input has zero BO relationships.

**Warning Signs:** BO pilot graph contains relationship records not traceable to source; heuristics infer links from matching column names; summaries say BO is connected; evidence fields cite generated reasoning rather than source records.

**Prevention/Tests:** Treat zero BO relations as valid source state, select BO for structural richness only, prohibit heuristic relationship synthesis, assert BO relationship count remains zero, and label absence as source fact rather than readiness defect.

**Phase:** Sample preparation and acceptance reporting.

### 6. Evidence Fidelity Loss or Source Leakage

**What Goes Wrong:** Context omits exact source evidence, mutates raw/canonical names, or returns raw documents and oversized source text beyond bounded need. Auditability disappears or sensitive catalog content leaks.

**Warning Signs:** Returned facts lack source document/object locator; `name_raw` differs from input; logs contain payload fragments; context response includes whole DDL/PDF text; evidence is reconstructed from graph labels instead of stored source-bound fields.

**Prevention/Tests:** Preserve exact `name_raw` and canonical fields, attach minimal source locators and digest, return only allowlisted evidence fields, redact logs to batch IDs and counts, test fidelity byte-for-byte, and test unrelated source text never appears.

**Phase:** Evidence model and object-context API.

### 7. Batch Caps Enforced Too Late

**What Goes Wrong:** Limits are checked after expansion, embedding, or transaction start. Oversized requests consume memory/provider quota or partially write before rejection.

**Warning Signs:** More than 500 entities, 2,000 edges, or 5,000 provenance links reaches write code; nested provenance expansion bypasses top-level count checks; limit failures occur after embedder calls; process memory scales without bound.

**Prevention/Tests:** Validate complete expanded request before embeddings and transaction; enforce 500/2,000/5,000 defaults at trust boundary; bound strings and nested references; add tests at limit, limit plus one, and multiplicative nested expansion.

**Phase:** Request validation and batch orchestration.

### 8. Frozen v1.1 Canary Artifact Contamination

**What Goes Wrong:** v1.2 preparation rewrites, reuses, or appends to frozen v1.1 canary artifacts. Historical evidence becomes ambiguous and terminal freeze checkpoint loses integrity.

**Warning Signs:** Existing canary paths show modified timestamps or git diffs; v1.2 output names overlap v1.1; scripts default to old artifact directories; acceptance compares mixed-version manifests.

**Prevention/Tests:** Treat frozen canary artifacts as immutable inputs, write v1.2 artifacts to new versioned paths, snapshot hashes before and after work, fail on mutation, and exclude old artifact directories from cleanup or regeneration.

**Phase:** Workspace setup and artifact production.

### 9. Unbounded One-Hop Cypher and Payload Fan-Out

**What Goes Wrong:** “One hop” is mistaken for bounded work. High-degree objects return every neighbor, property, or evidence blob, causing latency, memory, and MCP payload failures.

**Warning Signs:** Cypher lacks explicit limits and deterministic ordering; variable-length patterns appear; response size tracks node degree without ceiling; `collect(*)` or unrestricted property maps are returned; timeout grows on hub tables.

**Prevention/Tests:** Use exact one-hop patterns only, constrain labels and `group_id`, apply deterministic per-section and total limits, return allowlisted projections, expose truncation metadata, and load-test a synthetic high-degree table for query and serialized payload bounds.

**Phase:** Read-only object context implementation.

### 10. Group Isolation Omitted on Any Read or Write

**What Goes Wrong:** Object lookup, neighbor traversal, endpoint validation, or upsert matches UUID/name without `group_id`. Data crosses tenant/test boundaries even if top-level tool accepted a group.

**Warning Signs:** Any Cypher `MATCH` or `MERGE` lacks `group_id`; endpoint existence checks are global; same UUID fixture in two groups returns mixed results; tests only use one populated group.

**Prevention/Tests:** Thread validated `group_id` through every query and identity lookup, constrain every node and edge match, use only `oracle-catalog-tool-test` for target test writes, and seed adversarial second-group duplicates to prove no cross-group reads or writes.

**Phase:** Persistence and object-context query gates.

### 11. Read Tool Triggers Writes, Embeddings, or Index Mutation

**What Goes Wrong:** Object context calls ingestion helpers, generates embeddings, updates timestamps, lazily creates indexes, or records access state. Read becomes nondeterministic and violates exact read-only contract.

**Warning Signs:** Embedder mock receives calls; transaction contains `CREATE`, `MERGE`, `SET`, or `DELETE`; read changes database counters; context depends on LLM/embedder availability; driver bootstrap side effects occur per request.

**Prevention/Tests:** Build dedicated parameterized read query path, prohibit mutation clauses and model calls, run before/after graph snapshots, use fail-fast embedder stubs, inspect executed Cypher, and assert repeated reads produce equal output and zero writes.

**Phase:** Object-context API.

### 12. Ingest Atomicity Regression

**What Goes Wrong:** v1.2 sample orchestration opens multiple commits, writes before all embeddings complete, or catches conflict after partial upserts. Retry no longer means exactly one deterministic state.

**Warning Signs:** Entities remain after edge conflict; embedder failure leaves nodes; transaction count exceeds one commit batch; rollback test observes changed timestamps; error handler continues after failed write.

**Prevention/Tests:** Validate whole request first, generate all embeddings before write transaction, execute all entities/edges/provenance in one transaction, propagate conflicts, verify rollback on each write stage, and compare graph snapshots after injected failures.

**Phase:** Atomic ingest and token commit.

### 13. Prepare/Commit Boundary Leaks Write Authority

**What Goes Wrong:** Prepare writes graph state or commit accepts raw payload instead of isolated token. Token can be replayed against changed input, another group, another source image, or altered deployment namespace.

**Warning Signs:** Prepare requires DB write permissions; commit receives catalog objects; token lacks digest/group/sample/image binding; mutable server cache is sole token record; token remains valid after source-bound inputs change.

**Prevention/Tests:** Keep prepare read/compute-only, issue opaque single-purpose token bound to input digest, group, deterministic sample manifest, image source, namespace, limits, and expiry; commit accepts token only; reject tamper, replay, cross-group, stale, and mismatched-image cases before transaction.

**Phase:** Prepare/token-only commit protocol.

### 14. New Image Not Bound to Reviewed Source or Delta

**What Goes Wrong:** Acceptance tests image built from different commit, dirty context, mutable tag, or extra files. “New image” then proves neither reviewed source nor intended v1.2 delta.

**Warning Signs:** Image metadata lacks immutable source revision; build context contains untracked payloads; tag is reused; runtime package diff exceeds declared delta; report records tag but not digest.

**Prevention/Tests:** Build from identified source plus explicit v1.2 delta, record image digest and source revision, inspect included files, compare runtime content against trusted v1.1 tested source, require source-bound acceptance manifest, and use digest rather than mutable tag.

**Phase:** Image build and delta acceptance.

### 15. Secret or Catalog Payload Included in Image

**What Goes Wrong:** Build context captures `.env`, credentials, normalized 19MB catalog, generated tokens, raw documents, or logs. Deleted later layers may still retain content.

**Warning Signs:** Broad `COPY .`; missing `.dockerignore` entries; secret scanner finds keys; image history exposes build args; catalog paths appear in layer inventory; acceptance artifact contains full payload.

**Prevention/Tests:** Use narrow explicit `COPY`, exclude catalog and local artifacts, use runtime secret injection, scan final image and history for secrets and catalog fingerprints, inspect layers, and fail acceptance on any source payload or credential match.

**Phase:** Image packaging and security gate.

### 16. Dirty User Tree Overwritten or Smuggled into Results

**What Goes Wrong:** Automation resets, cleans, formats, stages, or packages unrelated user changes. Current dirty files and untracked artifacts are lost or accidentally attributed to v1.2.

**Warning Signs:** `git clean`, hard reset, blanket checkout, global formatter, `git add -A`, or broad build context use; pre-existing dirty paths change unexpectedly.

**Prevention/Tests:** Capture initial status, touch only explicit v1.2 paths, never clean/reset/delete, avoid broad staging, compare final status to baseline, preserve all frozen and dirty files, and report unrelated changes without modifying them.

**Phase:** Every phase; especially setup, build, and handoff.

### 17. Readiness Overclaim or Repeat of v1.1 Canary

**What Goes Wrong:** Team reruns trusted v1.1 canary despite zero runtime diff, treats sample success as production readiness, or claims BO relationship coverage source cannot provide. Time re-proves frozen substrate while new delta remains under-tested.

**Warning Signs:** Plan includes v1.1 canary rerun; acceptance says full ingest, production-ready, or all catalogs; report hides BO zero-relation limit; source-bound image and delta tests are missing; sample bounds are unstated.

**Prevention/Tests:** Trust shipped v1.1 substrate and recorded zero runtime diff, never repeat v1.1 canary, test only v1.2 delta on new source-bound image, state sample and source limits, separate pilot acceptance from deployment readiness, and require evidence for every readiness claim.

**Phase:** Acceptance, reporting, and release decision.

## Technical Debt Patterns

### Validation Split Across Layers

Duplicated partial checks drift. Keep authoritative request validation at trust boundary, then retain narrow defensive assertions at Cypher construction boundary for labels, properties, `group_id`, and token bindings.

### Identity Logic Embedded in Queries

Ad hoc UUID preimages inside Cypher become inconsistent. Compute canonical, versioned identity preimages server-side; pass UUID and exact preserved names as parameters.

### Unversioned Acceptance Artifacts

Generic filenames invite overwrite and v1.1/v1.2 mixing. Use immutable versioned paths and record hashes, source revision, image digest, input digest, group, and bounded sample manifest.

### Convenience Reads Through Ingest Facade

Reusing mutation-oriented Graphiti flows for context lookup couples reads to embeddings, background index work, and mutable timestamps. Keep object context in dedicated Neo4j read operation with fixed projections.

### Implicit Qualification Defaults

Defaulting absent database/schema from surrounding records makes malformed input look valid. Reject incomplete or ambiguous endpoint identities; normalization must be explicit and testable.

### Mutable Tags as Evidence

Container tags are navigation aids, not acceptance identity. Reports and commit tokens must bind immutable image digest.

### Count-Only Fidelity Checks

Matching 1,261 tables and 10,649 columns does not prove correct identity, endpoints, names, or evidence. Add deterministic manifest hashes and targeted semantic fixtures.

### Pilot Logic Becoming Production Policy

FE connected-sample and BO structural-score rules serve bounded acceptance only. Do not promote them into general ingestion selection or completeness claims.

## Recovery Strategies

### Input or Manifest Mismatch

Abort before embedding or transaction. Preserve diagnostic counts and non-sensitive identifiers, invalidate token, regenerate prepare artifact from authoritative input, then compare deterministic manifest and digest.

### Duplicate or Ambiguous Identity

Do not pick winner. Emit bounded conflict report with canonical keys and source locators, fix normalization/qualification rule, regenerate sample, and prove reordered input produces same manifest.

### Partial-Write Evidence

Treat as atomicity gate failure. Stop acceptance, snapshot affected test group, identify transaction boundary leak, restore only isolated test group through approved test setup, and rerun injected-failure rollback tests before success path.

### Cross-Group Read or Write

Stop pilot operations. Preserve query and test evidence without payload content, patch every match boundary, add adversarial duplicate fixtures, and rerun complete isolation suite.

### Frozen Artifact Mutation

Stop and compare against recorded hashes. Do not repair by regeneration. Restore from trusted frozen source only through approved workflow, then move v1.2 output to new paths.

### Image Provenance Failure

Reject image regardless of functional tests. Rebuild from identified source and explicit delta, use narrow context, rescan layers/secrets, record digest, and rerun only v1.2 delta acceptance.

### Oversized Context Response

Fail closed with bounded error or explicit truncation metadata; never stream unlimited neighbors. Tighten deterministic limits and projections, then test hub-object latency and serialized size.

### Dirty Tree Collision

Stop before overwrite. Record colliding paths, choose new output paths or ask owner, and leave unrelated modifications untouched. Never clean or reset as recovery.

### Overclaimed Report

Withdraw readiness statement, retain factual evidence, rewrite scope around bounded FE/BO samples, zero BO relationships, source-bound image, and untested operational areas.

## Pitfall-to-Phase Mapping

| Phase | Primary Pitfalls | Required Gate |
|---|---|---|
| 1. Input contract | Digest drift, duplicates, non-finite values, malformed shape, late caps | Full bounded validation and stable digest |
| 2. Identity contract | FE/BO collision, bare FK qualification, implicit defaults | Cross-database collision and ambiguity fixtures |
| 3. Pilot selection | Nondeterministic sample, FE bias, invented BO facts | Reorder-stable FE connectivity and BO structural manifest |
| 4. Evidence model | Fidelity loss, source leakage, count-only checks | Exact-name and allowlisted-evidence tests |
| 5. Prepare protocol | Prepare writes, weak token binding, replay | Read-only prepare and tamper/replay rejection |
| 6. Atomic commit | Late embedding, split transactions, partial writes | Injected-failure graph snapshot equality |
| 7. Object context | Unbounded one-hop, cross-group reads, read mutation | Bounded payload, adversarial isolation, zero-write proof |
| 8. Artifact handling | Frozen contamination, dirty-tree overwrite | Before/after hashes and status comparison |
| 9. Image build | Wrong source, mutable tag, secret/catalog inclusion | Source revision, image digest, layer and secret scan |
| 10. Acceptance | Repeat-canary waste, readiness overclaim | v1.2-delta-only report with explicit limits |

## Looks Done But Isn't Checklist

- [ ] Input digest is recorded and rechecked at commit.
- [ ] Root and every nested collection shape are validated.
- [ ] Duplicate deterministic identities fail before embedding.
- [ ] NaN and infinity are rejected explicitly.
- [ ] Limits cover expanded entities, edges, and provenance links.
- [ ] FE sample remains connected under deterministic ordering.
- [ ] BO sample uses structural richness without invented relations.
- [ ] Reordered equivalent input yields identical sample manifest.
- [ ] Database token participates in every relevant UUIDv5 preimage.
- [ ] Same qualified names in FE and BO produce distinct identities.
- [ ] Bare or ambiguous FK endpoints are rejected, not guessed.
- [ ] BO relationship count remains exactly zero for this input.
- [ ] `name_raw` and `name_canonical` remain exact.
- [ ] Evidence links to source locator and input digest.
- [ ] Logs contain batch IDs and counts only.
- [ ] Prepare performs no graph mutation.
- [ ] Commit accepts isolated token only, not catalog payload.
- [ ] Token binds group, digest, sample, namespace, image, limits, and expiry.
- [ ] Token tamper, replay, stale, cross-group, and image mismatch fail.
- [ ] All embeddings complete before transaction opens.
- [ ] Any commit-stage failure leaves graph snapshot unchanged.
- [ ] Every read and write query constrains `group_id`.
- [ ] Object context uses exact one-hop patterns only.
- [ ] Neighbor and payload bounds are deterministic and reported.
- [ ] Object context returns allowlisted properties only.
- [ ] Read path performs no writes, embeddings, or LLM calls.
- [ ] High-degree object test stays within query and payload ceilings.
- [ ] Frozen v1.1 canary artifact hashes remain unchanged.
- [ ] Existing dirty and untracked user files remain untouched.
- [ ] New image records immutable source revision and image digest.
- [ ] Build context excludes catalog, raw docs, tokens, logs, and secrets.
- [ ] Final image layers and history pass secret/catalog scans.
- [ ] Acceptance tests only v1.2 delta; v1.1 canary is not repeated.
- [ ] Report states 2 documents, 1,261 tables, 10,649 columns, and 434 FE relationships.
- [ ] Report states BO has zero relationships.
- [ ] Pilot success is not labeled full-ingest or production readiness.
- [ ] Source-bound image plus delta acceptance evidence is retained.

## Sources

- User-provided authoritative v1.2 scope and catalog facts, 2026-07-24. Confidence: HIGH.
- Trusted shipped v1.1 substrate and frozen canary status, as declared in task context. Confidence: HIGH.
- Project constraints for deterministic UUIDv5 identity, Neo4j behavior, bounded batches, group isolation, atomic transactions, pre-transaction embeddings, logging, and data preservation. Confidence: HIGH.
