# Pitfalls Research

**Domain:** Catalog-v2 pre-canary hardening (deterministic Graphiti MCP catalog tools)
**Researched:** 2026-07-17
**Confidence:** HIGH
**Scope:** v1.1 hardening only — identity grammar, validation, prepare/commit, manifests, verification. No canary execution. Replaces obsolete v1.0 ecosystem pitfall research.

**Approved contract corrections (override any conflicting research):**
1. Prepare persists **bounded immutable canonical payload** server-side (restart-safe; chunked non-Entity OK). Hashes/counts alone insufficient. Commit receives token only.
2. Prepare validates/resolves/projects only — **no required embeddings**. Commit embeds from stored payload before domain tx.
3. Commit success: **one Neo4j tx** for domain + evidence + manifest + terminal batch status + plan terminal state. Separate post-rollback failure-status tx only for failures.
4. Exact tools: `prepare_catalog_batch`, `commit_prepared_catalog_batch`, `discard_prepared_catalog_batch`, `get_catalog_capabilities`, `get_catalog_evidence`, `get_catalog_batch_manifest`, `resolve_typed_edges`.
5. Catalog-v2 breaks seven deterministic request identity/provenance/hash contracts where required; preserve tool names and semantic tools; do not claim v1 payloads remain accepted.
6. Capabilities work whenever server init succeeds, even if catalog writes disabled.
7. Required error codes include: , , , , , , , , .
8. No canary, no production/live-group writes, no parser/inference, no automatic catalog-v1 migration.


## Critical Pitfalls

### Pitfall 1: Silent v1 → v2 identity reinterpretation

**What goes wrong:**
Catalog-v2 changes graph-key grammar, FE/BO/COMMON segregation, or hash field sets while reads/writes still match bare v1 keys (`TABLE::HR.EMP`, no plane). Existing Neo4j objects under `oracle-catalog-tool-test` or any residual fixture get “updated” under a new UUIDv5, or verify falsely reports match because resolvers strip plane prefixes. Canary later collides with live `oracle-catalog-v2` if keys are normalized instead of fail-closed.

**Why it happens:**
v1 identity is `UUIDv5(ns, group_id|entity_type|graph_key)` with prefixes only (`ENTITY_TYPE_PREFIXES` in `catalog_common.py`). v1.1 deliberately breaks schema. Convenience normalizers (“accept either form”) look like migration helpers but are silent rekeying. PROJECT forbids automatic v1→v2 migration.

**How to avoid:**
- Fail closed on non-v2 keys when catalog-v2 mode is active; never strip/add FE/BO/COMMON silently.
- Do not recompute UUIDs for stored v1 rows under new grammar.
- Separate test group remains `oracle-catalog-tool-test`; never write `oracle-catalog-v2`.
- Document key grammar version on batch status/manifest; reject cross-version payload.

**Warning signs:**
- Same logical table yields different UUID after “hardening” deploy without re-ingest.
- Verify passes on keys that lack plane segment.
- Migration “helpers” in identity module without explicit version gate.
- Tests assert UUID equality across v1 fixture and v2 grammar.

**Prevention / tests:**
- Unit: v1-shaped `graph_key` → `validation_error` / `graph_key_prefix_mismatch` under v2 validators.
- Unit: v2 key → UUID differs from v1 key for same table name.
- Integration: pre-seeded v1 node not MATCH-updated by v2 upsert of “equivalent” name.
- Negative: no code path maps v1→v2 without explicit offline procedure (absent in v1.1).

**Phase to address:**
Phase 1 — FE/BO/COMMON identity grammar + fail-closed validation.

---

### Pitfall 2: Recursive validation not fail-closed (`extra` allowed)

**What goes wrong:**
Unknown fields on nested entities/edges/provenance/attributes are ignored (Pydantic default). Clients think execution flags, plane markers, evidence refs, or hash fields were accepted; server drops them. Immutable flags (`dry_run`, `atomic`, prepare tokens) smuggled under aliases change behavior only on some code paths. Hardening “looks complete” while contracts are open.

**Why it happens:**
Current catalog models (`catalog_entities.py`, `catalog_edges.py`, `catalog_provenance.py`, `catalog_batch.py`) do not show recursive `extra='forbid'` / strict config on every nested model. `attributes`/`metadata` allow free maps with only protected-key and nested-JSON bounds. Agents send experimental fields freely.

**How to avoid:**
- `model_config = ConfigDict(extra='forbid')` on every catalog request model and nested item, recursively.
- Immutable execution flags: reject client mutation of server-owned fields; freeze after prepare.
- Re-validate at service boundary (not only MCP parse) so `model_construct` / internal callers cannot bypass.
- Keep attribute maps allowlisted or JSON-blob-only with forbidden top-level collisions.

**Warning signs:**
- Fixture with `"_debug": true` still upserts.
- Prepare payload accepts unknown `commit_mode`.
- Unit suite never uses `pytest.raises` on extra keys at depth ≥2.

**Prevention / tests:**
- Parametrized extras at root, entity, edge, source, nested provenance, attribute child.
- Flag immutability: mutate `dry_run`/`atomic` after model build → error.
- Service-level reject when raw dict injected past MCP.

**Phase to address:**
Phase 1 — strict recursive contracts.

---

### Pitfall 3: Canonical bytes / hash field omissions → false idempotence

**What goes wrong:**
`canonical_sha256` (`catalog_identity.py`) hashes only fields present in `entity_canonical_payload` / `edge_canonical_payload` (`catalog_service.py`). New v2 fields (plane, code-unit role, endpoint map version, evidence link ids, prepare plan id) omitted from payload → two different domain objects share hash → no-op “unchanged” skips real updates, or batch retry accepts divergent content. Combined batch hash (`request_sha256`/`catalog_sha256`) may cover a subset of nested collections. Client hash optional path (`assert_optional_client_hash`) masks server authority if callers skip it.

**Why it happens:**
v1 payloads listed a fixed field set. Hardening adds fields without extending both (1) hash input and (2) persisted `content_sha256` compare. JSON key order is handled (`sort_keys=True`) but **field inclusion** is the real bug. Float/`None` policy drift between prepare snapshot and commit re-hash.

**How to avoid:**
- Single authoritative canonicalizer for each domain object and for whole-batch catalog hash; version the recipe string in manifest.
- Every mutable domain field either in hash or explicitly excluded with comment + test.
- Server always recomputes; client hash audit-only → `content_hash_mismatch`.
- Prepare freezes canonical bytes; commit re-hashes frozen snapshot only (not live re-serialize of mutated model).

**Warning signs:**
- Changing plane/FE marker does not change `content_sha256`.
- Batch retry with extra evidence link returns all `unchanged`.
- Prepare hash ≠ commit hash for identical logical payload after field reorder only (serialization bug) or equal hashes for dropped fields (omission bug).

**Prevention / tests:**
- Mutation matrix: flip each v2 field → hash changes; flip excluded identity fields → hash stable.
- Batch hash covers entities+edges+provenance+evidence links+endpoint map version.
- Prepare/commit: bit-identical canonical bytes across process restart from stored plan.
- NaN/Inf still rejected (`_reject_non_finite`).

**Phase to address:**
Phase 2 — authoritative batch hashing; also Phase 3 prepare immutability.

---

### Pitfall 4: FE/BO/COMMON identity collisions and overloaded code units

**What goes wrong:**
Front-end and back-end objects share unqualified names (`CUSTOMER`, package `ORDER_MGMT`) and collapse to one UUIDv5. Overloaded PL/SQL units (same name, different args) share `PROCEDURE::`/`FUNCTION::` key. Synonyms and targets collide. Search/resolve returns wrong plane’s object; edges attach across planes.

**Why it happens:**
v1 keys are type-prefix + qualified name only. Oracle catalogs need plane + overload discriminator. Developers reuse `name_canonical` as graph_key without overload signature or FE/BO tag.

**How to avoid:**
- Fail-closed grammar: plane segment required (`FE`|`BO`|`COMMON`) in graph_key/edge_key rules; document exact format.
- Code-unit keys include deterministic overload identity (normalized args), not bare name.
- Separate UUID inputs must include plane; never optional default to COMMON.
- Endpoint resolution matches plane + type + key.

**Warning signs:**
- One UUID for FE screen and BO table with same leaf name.
- Package procedure upsert overwrites sibling overload.
- Edge `Calls` links FE stub to BO body unintentionally.

**Prevention / tests:**
- Distinct UUIDs for FE vs BO same leaf name.
- Two overloads → two keys/UUIDs; collision attempt → `deterministic_uuid_conflict` / validation error.
- Cross-plane endpoint mismatch → `endpoint_type_mismatch` or dedicated plane error.
- Property tests on grammar parser reject ambiguous keys.

**Phase to address:**
Phase 1 — identity grammar.

---

### Pitfall 5: Missing or client-owned edge endpoint maps

**What goes wrong:**
v1 checks prefix match per endpoint type but not finite server map of allowed `(edge_type → (source_types, target_types))`. Client can assert `ForeignKeyTo` from `Procedure`→`Sequence`, or `EnforcedBy` without DDL plane. Hardening claims “server-owned endpoint maps” but enforces only prefixes → invalid topology becomes “searchable truth.”

**Why it happens:**
`CatalogEdgeItem` validates allowlisted types and graph_key prefixes (`catalog_edges.py`), not pairwise endpoint maps. Generic `DependsOn`/`ReferencesByCode` invite abuse.

**How to avoid:**
- Frozen server map per edge type; reject before side effects with structured code.
- Capabilities discovery exposes map version; clients must not embed private maps as authority.
- Standalone edge upsert and batch preflight share one checker.
- No generic endpoint creation (retain v1 `missing_endpoint` / `generic_endpoint_conflict`).

**Warning signs:**
- Unit tests only cover happy FK Table→Table.
- Map lives in client docs only.
- Different code paths (edge tool vs batch) disagree on allowed pairs.

**Prevention / tests:**
- Exhaustive negative table: each edge type × disallowed endpoint pair.
- Map version bump changes capabilities payload; old clients get clear validation errors.
- Live: disallowed pair → zero RELATES_TO rows.

**Phase to address:**
Phase 2 — server-owned endpoint maps + capabilities.

---

### Pitfall 6: Cartesian provenance / evidence expansion

**What goes wrong:**
`UpsertProvenanceRequest` and `NestedProvenancePayload` bound links as `len(sources) * (len(entity_targets) + len(edge_targets))` (`catalog_provenance.py`, `catalog_batch.py`). That **is** Cartesian product: every source links to every target. v1.1 requires **explicit** evidence links. Cartesian silently multiplies MENTIONS/`episodes` attachments, hits 5k link caps incorrectly, creates false provenance density, and makes verify “green” while evidence is meaningless.

**Why it happens:**
v1 designed bulk attach for convenience. Hardening language says “exact evidence links without Cartesian expansion” but reusing v1 request shape preserves the product.

**How to avoid:**
- Replace product API with explicit link list: `(source_key, target_kind, target_key[, evidence_span])`.
- Bound by link count only, not sources×targets.
- Generate one MENTIONS / one episode-id append per explicit link; deterministic `catalog_mentions_uuid` per pair remains, but pairs are caller-enumerated.
- Reject empty link list when sources present if policy requires evidence.

**Warning signs:**
- 10 sources × 50 entities = 500 links without 500 explicit rows in request.
- Tests assert product formula as feature.
- Manifest link count ≠ request explicit link count.

**Prevention / tests:**
- Request with 2 sources and 2 entities but **one** explicit link → exactly one MENTIONS.
- Product-shaped legacy payload → `validation_error` under v2.
- Cap tests use link list length, not product.
- Live concurrency: no extra links under dual writers.

**Phase to address:**
Phase 3 — exact evidence links (prepare/commit path); models in Phase 1–2 if API breaks.

---

### Pitfall 7: Mutable prepared payloads / false prepare-commit idempotence

**What goes wrong:**
Prepare returns a plan id/token but server keeps mutable in-memory structures or re-reads client body on commit. Client mutates entities between prepare and commit; commit applies new body while status still references prepare hash. Or commit recomputes UUIDs from fresh body → identity drift. Discard does not invalidate token; replay commits twice.

**Why it happens:**
v1 tools are single-shot upserts. Prepare/commit/discard is new. Easy to store request dict by reference, or trust client to resend body.

**How to avoid:**
- Persist immutable prepared snapshot: **full bounded canonical payload** + server hashes + derived UUIDs under plan identity (chunked non-Entity nodes OK). Hashes/counts alone insufficient.
- Prepare does **not** compute required embeddings; commit embeds from stored payload before domain tx.
- Token binds to snapshot hash; mismatch → reject (`prepared_plan_conflict` / hash mismatch).
- Discard / TTL expiry deletes or tombstones plan; commit after discard → `prepared_plan_not_found` / `prepared_plan_already_consumed` / `prepared_plan_expired`.
- No partial domain writes at prepare; prepare is write-free for domain graph (only non-Entity plan+payload records).
- Commit success path: one Neo4j tx for domain + evidence + manifest + terminal batch status + plan terminal state; separate post-rollback failure-status tx only for failures.


**Warning signs:**
- Commit accepts body fields absent from prepare response.
- Two commits with same token both create domain rows.
- Prepare writes Entity nodes (search pollution).
- Prepare stores only hashes/counts (cannot rehydrate).
- Embeddings computed at prepare instead of commit.
- Domain succeeds without co-committed manifest/terminal plan state.
- Prepare stores only hashes/counts (cannot rehydrate).
- Embeddings computed at prepare instead of commit.
- Domain succeeds without co-committed manifest/terminal plan state.


**Prevention / tests:**
- Mutate client body after prepare → commit still applies original snapshot or rejects resubmitted divergence.
- Commit ×2 same token → second no-op or `batch_conflict`, domain counts stable.
- Discard then commit → error; domain unchanged.
- Process restart: prepare in DB, new process commits successfully from durable snapshot.

**Phase to address:**
Phase 3 — prepare/commit/discard protocol.

---

### Pitfall 8: Insecure tokens, TTL, concurrency, and replay

**What goes wrong:**
Predictable plan tokens (raw batch_id, sequential ints). Tokens logged in full. TTL not enforced → indefinite commit. Concurrent commit of same plan double-applies without compare-and-set. Replay after success re-enters writing state. Timing attacks on token compare if relevant.

**Why it happens:**
Status today uses deterministic batch UUID (`catalog_batch_uuid`) which is right for batch identity but wrong if reused as secret capability token. Logs often include ids; PROJECT allows batch IDs but not secrets.

**How to avoid:**
- High-entropy commit token; store only hash (SHA-256) server-side; compare digest.
- Bind token to `group_id` + plan uuid + content hash.
- TTL on prepared plans; expire → non-committable.
- Single-winner commit CAS on plan state (`prepared`→`committing`→`committed`/`failed`) inside Neo4j, same pattern as source CAS / batch claim in v1 store.
- Log plan id + counts only; never raw token.

**Warning signs:**
- Token equals `batch_id` or UUIDv5 of batch.
- Logs contain `commit_token=`.
- Parallel commit tests flake with double domain rows.
- Expired plan still commits in tests with freezegun off.

**Prevention / tests:**
- Token entropy / format tests; storage has hash only.
- Concurrent dual commit → one success, one conflict; one domain effect.
- TTL expiry unit + optional live.
- Log capture assert no token/raw payload.

**Phase to address:**
Phase 3 — secure prepare/commit; Phase 5 security suite.

---

### Pitfall 9: Neo4j atomic boundary regressions (races, failed-status, embeddings)

**What goes wrong:**
Hardening splits prepare/commit or manifest writes and reintroduces: embed-inside-tx, multi-`execute_query` auto-commit, status committed while domain rolls back, source validation TOCTOU without CAS, unordered target locks, domain write outside `group_id`. Composite UNIQUE constraints skipped (`ensure_uuid_uniqueness_constraints` short-circuit bugs). Cartesian evidence multiplies lock sets past practical tx time.

**Why it happens:**
v1 closed these (`catalog_store.py` source CAS, ordered retained locks, embeddings before tx, failed status in separate tx). New code paths copy “simple MERGE” without the ceremony. Schema init `_schema_ready` flag can hide failed constraint presence across multi-worker processes (in-memory only).

**How to avoid:**
- Reuse store primitives; do not fork second write path.
- Commit domain + manifest + terminal status rules explicitly ordered; failed-status after rollback only.
- Embeddings complete before domain tx open.
- Every MATCH/MERGE keeps `group_id`.
- Constraint ensure remains fail-closed; workers must not assume peer initialized schema without verification where required.
- Keep live concurrency tests mandatory for commit path.

**Warning signs:**
- New Cypher without `group_id`.
- `SET n = $map` returns.
- Commit path calls embedder under open tx.
- `_schema_ready = True` without SHOW verification.
- Skipped neo4j int tests in CI for “speed”.

**Prevention / tests:**
- Fault injection: fail mid-commit → zero partial entities/edges/evidence; status `failed` or absent per contract.
- Concurrent source update / dual batch claim → structured `batch_conflict` / `deterministic_uuid_conflict`.
- Embedder raise → no domain writes.
- Constraint missing → fail closed, no repair DROP.
- Residual count 0 on `oracle-catalog-tool-test`; `oracle-catalog-v2` node count unchanged.

**Phase to address:**
Phase 3–4 write paths; Phase 5 live concurrency gates.

---

### Pitfall 10: Manifest drift and verify false green

**What goes wrong:**
`verify_catalog_batch` compares live graph to client re-supplied lists (v1 pattern) instead of durable manifest written at commit. Manifest omitted fields (edge endpoints, evidence links, plane, hash recipe version). Verify checks counts only not identities. Manifest updated out-of-band or partially on retry. Operators trust verify while graph ≠ committed plan.

**Why it happens:**
v1 verify is request-driven. v1.1 requires durable exact manifest + manifest-backed verification. Easy to “enhance” verify without persisting manifest, or persist summary counts only.

**How to avoid:**
- On successful commit, persist full manifest (entity/edge/source/link UUIDs, keys, content hashes, endpoint UUIDs, map version, hash recipe version) under batch identity.
- Verify loads manifest by `group_id`+`batch_id` (or plan id); client body cannot redefine expected set.
- Drift → structured failure listing mismatches; never repair silently.
- Dry-run produces no durable manifest (or explicitly marked non-authoritative).

**Warning signs:**
- Verify passes after manual Neo4j delete of one entity.
- Manifest node missing but status `committed`.
- Verify API still requires full entity list identical to upsert.
- Manifest hash ≠ batch catalog hash.

**Prevention / tests:**
- Commit → manifest present; verify no client domain list → pass.
- Delete one node → verify fail; manifest unchanged.
- Retry identical commit → manifest stable (byte/hash equality).
- Conflicting retry → no manifest overwrite.
- Read-only verify works when mutation gate disabled.

**Phase to address:**
Phase 4 — durable manifests + manifest-backed verification.

---

### Pitfall 11: Read/write gate confusion and accidental live/canary activity

**What goes wrong:**
Single `catalog_upsert.enabled=false` disables resolve/verify/status too, or write tools ignore gate. Split gates misconfigured so mutation enabled in shared env. Tests or docs use `oracle-catalog-v2` / production URI. “Canary prep” scripts actually ingest. K8s/sample manifest edits ship with enabled writes. Agents call `clear_graph` or delete tools during cleanup.

**Why it happens:**
v1 one feature flag. v1.1 wants read-only diagnostics while mutation disabled. Operational pressure to “just run canary”. Working tree already has k8s/sample paths that must not be task-mutated casually.

**How to avoid:**
- Separate flags: mutation vs read diagnostics; capabilities discovery advertises both.
- Hard-code test group allowlist in live tests; assert forbidden group untouched before/after.
- No canary execution in v1.1; docs are procedure-only.
- Never `clear_graph` for cleanup; scoped deletes of tool-test UUIDs only if absolutely required (prefer tx rollback + explicit test fixtures).
- CI env: mutation disabled by default except labeled integration jobs.

**Warning signs:**
- Integration log shows `group_id=oracle-catalog-v2`.
- Verify fails with `feature_disabled` when only writes should be gated.
- Node counts on forbidden group change during test run.
- README “run canary” without approval gate language.

**Prevention / tests:**
- Mutation off → upsert/prepare/commit error `feature_disabled`; resolve/verify/status/capabilities succeed.
- Pre/post probe: forbidden group checksum/count stable.
- Grep CI and tests for forbidden group string as write target.
- Docs lint: canary marked non-executed.

**Phase to address:**
Phase 4 — split gates; Phase 5 — isolation/docs enforcement.

---

### Pitfall 12: Log / response leakage (tokens, payloads, source text)

**What goes wrong:**
Debug logs print full catalog payloads, evidence strings, raw DDL, commit tokens, credentials from config. Error messages echo attribute maps. MCP responses include server-only secrets. Telemetry captures batch bodies.

**Why it happens:**
f-string logging culture in Graphiti (`logger.debug(f'...{payload}')`). Catalog evidence fields are large (`MAX_EVIDENCE_LENGTH=8192`). Prepare tokens are new secret material.

**How to avoid:**
- Log `group_id`, `batch_id`/`plan_id`, counts, error codes only.
- Redact tokens always; store hash only.
- Structured errors: codes + short messages; no raw source text.
- Review MCP tool result models for accidental field exposure.

**Warning signs:**
- Test log fixtures contain `name_raw` lists or SHA inputs.
- Exception handlers `str(request)`.
- Token appears in `CatalogIngestStatus` response.

**Prevention / tests:**
- Caplog assertions on success/failure paths.
- Response schema tests: no `commit_token` after first return policy; never `password`.
- Security suite cases from v1.0 remain green and extended for tokens.

**Phase to address:**
Phase 5 — security/logging; design discipline in Phases 3–4.

---

### Pitfall 13: Legacy MCP compatibility break and dual-stack false confidence

**What goes wrong:**
Hardening renames tools, changes required fields on existing seven tools, or breaks 14 legacy tools registration. Semantic `add_memory`/`add_triplet` still create generic endpoints while catalog claims exclusive deterministic path—agents mix paths and “verify” only catalog slice. Test suite green on catalog units while MCP listing drops tools.

**Why it happens:**
v1 promised additive tools. v2 contracts want stricter shapes; tempting to change in place without versioning. Registration is central in `graphiti_mcp_server.py`.

**How to avoid:**
- Keep v1 tool names working with documented compatibility mode **or** explicit versioned tool names; no silent required-field change without error code.
- Registration test: catalog + legacy counts; `MISSING []`.
- Agents must not use `add_triplet` for catalog; docs + optional runtime warnings.
- Compatibility suite runs every phase gate.

**Warning signs:**
- Runtime tool count ≠ expected.
- Existing MCP regression file skipped.
- Catalog verify green while `add_triplet` polluted group.

**Prevention / tests:**
- 86 legacy MCP tests remain; catalog registration snapshot.
- Mixed-path isolation test: semantic tools do not run in catalog int modules.
- Contract tests for unchanged v1 fields where compatibility required.

**Phase to address:**
Phase 5 — compatibility; continuous regression each phase.

---

### Pitfall 14: Overloaded verify / status vocabulary hides incomplete hardening

**What goes wrong:**
Status lifecycle vocabulary (`planned`/`validating`/…/`committed`/`failed`) confuses with durable terminal-only persistence (v1 STAT-03 nuance). Prepare states bolted on without clarifying restart-safe set. Verify “passed” means schema-valid request not graph match. Capabilities endpoint overclaims endpoint map / hash version.

**Why it happens:**
v1 already had model/read vocabulary vs persisted terminal states. v1.1 adds prepare states—easy to over-persist or under-document.

**How to avoid:**
- Explicit state machine table: which states durable, which ephemeral.
- Verify response distinguishes `manifest_match`, `missing`, `hash_mismatch`, `plane_mismatch`.
- Capabilities returns exact versions; tests pin them.

**Warning signs:**
- Status `writing` survives process restart.
- Verify boolean `ok` without per-item codes.
- Capabilities missing hash recipe version.

**Prevention / tests:**
- Restart-safe matrix for each state.
- Verify error taxonomy unit tests.
- Capabilities snapshot test.

**Phase to address:**
Phase 4 status/manifest; Phase 5 docs/tests.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep Cartesian provenance API | Less client work | False evidence density; wrong caps | Never for v1.1 |
| Optional plane default COMMON | Easier migration | FE/BO collision | Never |
| Hash subset of fields “for speed” | Smaller canonicalizer | False idempotence | Never |
| In-memory prepare only | Faster spike | Lost on restart; dual-writer races | Never (restart-safe required) |
| Reuse v1 verify client lists | Less store work | Manifest drift invisible | Never for v1.1 verify |
| Skip live concurrency this milestone | Faster CI | TOCTOU regressions | Never for commit path |
| Silent v1 key accept | Soft migration | Identity corruption | Never |
| Log full payload in debug | Easy debug | Leakage / PII / tokens | Never in product paths |
| Single feature flag for all catalog | Simple config | Read diagnostics die with writes | Only temporary pre-Phase 4 |
| Claim multi-backend support | Marketing | Untested Falkor/Kuzu paths | Never this milestone |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Neo4j 5.26 constraints | Assume stock Graphiti UNIQUE on uuid alone | Catalog composite `(uuid, group_id)` CREATE IF NOT EXISTS; verify SHOW; no DROP |
| Neo4j transactions | `execute_query` per MERGE | One domain tx; failed status separate |
| Embedder | Embed inside write tx / after partial write | All embeddings before tx; fail `embedding_failed` |
| Graphiti search | Expect CatalogIngestBatch / plan nodes in entity search | Non-Entity labels only for status/plan/manifest |
| MCP FastMCP | Change tool signatures in place | Additive or versioned; registration snapshot |
| Source CAS | Check hash in Python then write | Fixed Cypher CAS + retained locks (v1 pattern) |
| Evidence links | Product of sources×targets | Explicit link rows only |
| group_id | Default empty / shared | Required; tests only `oracle-catalog-tool-test` |
| UUID namespace | Auto-gen per process | Immutable `GRAPHITI_CATALOG_UUID_NAMESPACE` |
| Canary group | Write `oracle-catalog-v2` in tests | Probe-only; zero mutation |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Cartesian evidence | Tx timeouts; link cap false hits | Explicit links | >~50 sources × >~100 targets |
| Unbounded prepare store | Disk growth; stale commits | TTL + discard + cap plans/group | Long-running MCP |
| Per-item round trips | Slow batch | Bulk MERGE in one tx | 500 entities / 2k edges defaults |
| Re-embed unchanged | Cost/latency; vector churn | Hash short-circuit before embed | Large retries |
| Lock order inversion | Deadlocks under concurrency | Fixed `ORDER BY uuid, kind` | Parallel provenance |
| Manifest full scan verify | Slow verify | Keyed MATCH by manifest UUID list | Full catalog later (~14k) — design now |
| Schema ensure every request | Latency | Process-local ready flag **plus** correct SHOW | High QPS (still fail closed if missing) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Client labels/properties in Cypher | Injection | Allowlists only; re-validate at store |
| Raw commit token storage/logs | Replay / theft | Store hash; log ids only |
| Predictable tokens | Cross-client commit | CSPRNG token bound to plan hash |
| Protected property via attributes | Identity clobber | Denylist + forbid extra |
| group_id omission | Cross-tenant read/write | Require + MATCH predicate |
| Trust client UUID | Identity takeover | Server UUIDv5 only |
| MD5 / short hash | Collision / policy break | SHA-256 64 lowercase hex only |
| Capabilities over-exposure | Info leak of internal limits | Safe public map; no secrets |
| Mutation enabled in shared Neo4j | Accidental canary/live write | Split gates; env defaults off |
| Error echo of source text | Data leak | Bounded messages; codes |

## UX Pitfalls (operator / agent)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Opaque `validation_error` | Cannot fix plane/key | Field path + grammar hint |
| Cartesian surprise | Huge link counts | Explicit links + examples |
| Verify needs full resend | Fragile agents | Manifest-backed verify |
| One flag kills diagnostics | Blind ops | Split read/write gates |
| Silent no-op on hash omit | Believe data applied | Field-complete hashes + statuses |
| Docs imply canary ran | False production confidence | Procedure only; approval required |

## "Looks Done But Isn't" Checklist

- [ ] **Strict models:** Extra keys rejected at every nesting level — not only root.
- [ ] **FE/BO/COMMON grammar:** Parser + UUID tests for plane and overloads; v1 keys fail closed.
- [ ] **Endpoint map:** Server map enforced on edge tool **and** batch; capabilities versioned.
- [ ] **Hash completeness:** Mutation matrix includes all v2 fields; batch hash covers all collections.
- [ ] **Explicit evidence:** No sources×targets product; one request row per link.
- [ ] **Prepare immutability:** Snapshot durable; commit ignores mutated client body or rejects.
- [ ] **Token safety:** Hash-at-rest; TTL; single-winner CAS; no token in logs.
- [ ] **Atomic commit:** Embed before tx; rollback completeness; failed status separate.
- [ ] **Manifest:** Written on commit; verify uses manifest not client lists; drift detected.
- [ ] **Split gates:** Reads work when mutation off.
- [ ] **Isolation:** Only `oracle-catalog-tool-test` writes; `oracle-catalog-v2` unchanged probes.
- [ ] **Legacy MCP:** Tool counts + regression suite green.
- [ ] **No canary execution:** Docs/procedure only; no full 14k ingest.
- [ ] **Logging:** Caplog tests for payload/token absence.
- [ ] **Compatibility with v1 objects:** No silent rekey of existing nodes.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Silent rekey / wrong plane UUIDs | HIGH | Stop writers; do not “fix” in place; rebuild in tool-test only; production needs approved migration (out of scope) |
| Cartesian evidence explosion | MEDIUM | Discard plan; re-ingest with explicit links; delete tool-test residuals by batch UUID |
| Partial commit (bug) | HIGH | Tx fix first; tool-test cleanup by known UUIDs; never clear_graph |
| Manifest drift | MEDIUM | Trust graph or re-commit after fix; mark status failed if policy says; no silent manifest rewrite |
| Token leak | MEDIUM | Invalidate all prepared plans; rotate nothing else if hash-only storage; scrub logs |
| Forbidden group write | HIGH | Halt; incident; do not automate delete; human recovery |
| Hash recipe change mid-flight | MEDIUM | Bump recipe version; require re-prepare; reject old plans |
| Constraint create fail (dup data) | HIGH | Fail closed; manual dedupe; no DROP in product |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Silent v1→v2 reinterpretation | Phase 1 Identity grammar | v1 key rejected; UUID ≠ v1; no update of pre-seeded v1 nodes |
| Recursive validation open | Phase 1 Strict contracts | Extra-key matrix all depths |
| Hash field omissions / false idempotence | Phase 2 Batch hashing | Mutation matrix; prepare/commit byte equality |
| FE/BO/overload collisions | Phase 1 Identity grammar | Distinct UUIDs; conflict tests |
| Client endpoint maps | Phase 2 Endpoint maps + capabilities | Negative pair table; map version |
| Cartesian evidence | Phase 3 Evidence links (API earlier if needed) | Explicit single-link live count |
| Mutable prepare / replay | Phase 3 Prepare/commit/discard | Restart commit; discard; dual commit |
| Token/TTL/concurrency | Phase 3 + Phase 5 security | Hash-at-rest; TTL; race test |
| Neo4j atomic regressions | Phase 3–4 writes + Phase 5 live | Fault inject; concurrent CAS |
| Manifest drift / false verify | Phase 4 Manifests + verify | Delete-one-node verify fail |
| Gate / live canary accident | Phase 4 gates + Phase 5 isolation | Forbidden group probe; read-only mode |
| Log/token leakage | Phase 5 security | Caplog + response schema |
| Legacy MCP break | Phase 5 compatibility (each gate) | Registration + 86 legacy tests |
| Status/verify vocabulary lie | Phase 4–5 | State matrix + capabilities pin |

Suggested v1.1 phase spine (roadmap consumer):

1. **Strict contracts + FE/BO identity grammar** — fail closed; no silent v1 rekey; `unsupported_identity_schema` / `invalid_system_key`.
2. **Endpoint maps + authoritative hashing + capabilities** — server maps (`edge_endpoint_pair_not_allowed`); complete hashes; capabilities after init even if writes off.
3. **Prepare/commit/discard + explicit evidence** — full payload prepare; embed at commit; one success tx; exact tool names; plan error codes.
4. **Manifests + manifest verify + split read/write gates** — durable truth; `manifest_mismatch`; safe diagnostics.
5. **Exhaustive tests, security, compatibility, docs** — no canary; no auto migration; isolation proof.


## Sources

- `.planning/PROJECT.md` — v1.1 goals, constraints, out-of-scope (no canary, no v1 silent migration, test group only)
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md` — v1 closures (CAS, locks, embeddings-before-tx, isolation) that must not regress
- `.planning/milestones/v1.0-phases/02-provenance-and-atomic-batch/02-VERIFICATION.md` — atomic/status/provenance truths
- `mcp_server/src/services/catalog_identity.py` — UUIDv5 formulas, `canonical_sha256`, optional client hash
- `mcp_server/src/services/catalog_service.py` — canonical payload field sets, prepare-less single-shot flow
- `mcp_server/src/services/catalog_store.py` — composite UNIQUE, CAS, schema ensure, no SET-map
- `mcp_server/src/models/catalog_*.py` — allowlists, Cartesian link bound, missing `extra='forbid'`, batch hash fields
- `mcp_server/tests/test_catalog_*.py` — v1 unit/live/concurrency baselines to extend

---
*Pitfalls research for: Catalog-v2 pre-canary hardening*
*Researched: 2026-07-17*
*Confidence: HIGH — grounded in current mcp_server catalog implementation and v1.0 verification artifacts; phase names are recommendations for roadmap authoring*
