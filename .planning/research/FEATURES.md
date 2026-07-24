# Feature Research

**Domain:** v1.2 FE/BO Catalog Pilot and Object Context
**Researched:** 2026-07-24
**Confidence:** HIGH

## Feature Landscape

v1.2 is a bounded pilot over shipped v1.1 catalog-v2 primitives. It proves two deterministic
samples and one exact read-only context tool. It does not reopen v1.1 foundation work.

### Table Stakes

| Feature | Why Expected | Complexity | Testable Contract |
|---|---|---:|---|
| Normalized authority gate | All pilot facts must come from one stable input | Low | Accept only `catalog/catalog.json`; verify inventory and SHA-256 before selection |
| Deterministic connected FE sample | FE pilot must exercise authoritative relationships | Medium | Same input yields same connected sample, order, manifest, and digest |
| Deterministic rich BO sample | BO pilot must exercise useful table/column structure | Medium | Same structural scoring and tie-breakers yield same sample and digest |
| FE/BO isolation | Different sources must not contaminate identity or evidence | Medium | Separate manifests, prepare tokens, commits, and acceptance snapshots |
| Immutable prepare | Invalid or incomplete data must never reach write transaction | High | Prepare validates all data, performs pre-write work, and writes nothing |
| Token-only commit | Caller cannot replace prepared content | High | Commit accepts only valid prepare token bound to immutable payload digest |
| Atomic idempotent commit | Retry must preserve exact graph identity | High | Whole batch commits or rolls back; replay creates no duplicate object |
| Exact focal-object read | Context must identify one requested typed object | Medium | Exact scoped identity returns one object or typed not-found/integrity error |
| Bounded one-hop context | Output must remain predictable and local | Medium | Only direct neighbors returned under fixed count limits |
| Stable output ordering | Repeat reads need reproducible output | Low | Explicit total sort order includes UUID tie-breaker |
| Evidence excerpts and locators | Context needs audit trail | Medium | Every excerpt has bounded text and stable source-bound locator |
| Source-bound images | Image proof must belong to same source authority | Medium | Image source digest and locator match focal source document |
| No-write read posture | Read tool must not mutate, infer, repair, or embed | Low | Success and failure paths produce zero graph delta |
| Deterministic acceptance artifacts | Pilot must be replayable and reviewable | Medium | Canonical manifests and snapshots have repeatable digests |
| Frozen canary directories | Historical acceptance must not drift | Low | Each run creates new directory; existing canary files never change |
| Batch-cap enforcement | Existing safety ceilings remain authoritative | Low | Reject above 500 entities, 2,000 edges, or 5,000 provenance links |
| Zero new dependencies | Existing stack already supports all work | Low | Dependency manifests and lockfiles add no v1.2 package |
| Existing behavior preservation | v1.2 is additive | Medium | Existing MCP tools, exact resolve/search, and native Ollama remain unchanged |

### Differentiators

| Feature | Value Proposition | Complexity | Testable Contract |
|---|---|---:|---|
| Relationship-connected FE canary | Proves useful graph context, not isolated object writes | Medium | Every non-root FE sample object connects through authoritative FE relation |
| Rich BO without invented edges | Demonstrates BO value while preserving source truth | Medium | BO selection uses table/column structure only; adds no inferred BO relation |
| Typed context envelope | Gives clients machine-checkable object context | Medium | Focal, neighbor, relation, evidence, image, and locator types are explicit |
| Canonical response digest | Makes read regressions visible | Low | Unchanged request and graph yield same canonical response digest |
| Explicit truncation metadata | Prevents silent loss at bounds | Low | Every bounded collection reports applied limit and truncation state |
| Negative-delta proof | Detects unrelated mutations | High | Before/after comparison permits only manifest-declared changes |
| Source-scoped run ledger | Links selection, prepare, commit, and acceptance | Medium | Batch ID and artifact digests cross-reference one immutable run |

### Anti-Features

| Anti-Feature | Why Avoid | Required Alternative |
|---|---|---|
| Full catalog ingest | v1.2 is bounded pilot | Commit only manifest-selected FE and BO samples |
| Inferred BO relations | Normalized authority has no BO relations | Return BO table/column structure only |
| FE/BO maps | Mapping would assert unsupported cross-source semantics | Keep source namespaces and contexts isolated |
| Natural-language orchestration | Adds ambiguity and model dependence | Use typed exact MCP request fields |
| Multi-hop traversal | Expands scope and response variance | Return one-hop neighbors only |
| Path finding | Not needed for focal context pilot | Defer until explicit bounded path requirement |
| Impact analysis | Requires unsupported semantics | Return direct authoritative relations without impact claims |
| User-facing delta analysis | Delta exists only for acceptance | Keep comparison in canary artifacts |
| Docling or LLM processing | JSON is sole normalized authority | Apply fixed deterministic rules only |
| Production promotion | Pilot acceptance is not deployment authorization | Stop at isolated canary evidence |
| Repeat v1.1 canary | v1.1 is shipped and frozen | Reuse contracts without rerunning old canary |
| Caller UUID authority | Breaks deterministic identity | Derive UUIDv5 server-side from fixed namespace |
| Dynamic Cypher labels/properties | Enables injection and schema drift | Use fixed server allowlists and query parameters |
| Read-time repair | Violates no-write read posture | Return typed integrity error |
| Unbounded evidence text | Risks oversized responses and source leakage | Cap counts and excerpt length |
| New framework/package | Existing Python, Pydantic, Neo4j, MCP suffice | Add zero dependencies |

## Observable Contracts

### Normalized Authority

1. `catalog/catalog.json` is sole normalized authority.
2. Authority contains exactly 2 documents.
3. Authority contains exactly 1,261 tables.
4. Authority contains exactly 10,649 columns.
5. Authority contains exactly 434 relationships, all FE.
6. FE source `SVFE_SHB` contains exactly 637 tables.
7. BO source `MAIN1` contains exactly 624 tables.
8. Inventory mismatch fails before sample selection or prepare.
9. Authority SHA-256 binds every sample manifest and acceptance run.
10. PDF, DDL, dictionary, parser, Docling, and LLM outputs cannot override JSON.

### Deterministic Sampling

1. FE sample uses only `SVFE_SHB` objects and authoritative FE relationships.
2. FE sample forms a connected subgraph under documented selection rules.
3. FE ranking, closure, and tie-breakers use explicit total ordering.
4. BO sample uses only `MAIN1` tables and columns.
5. BO richness uses deterministic structural metrics such as column count and metadata coverage.
6. BO selection creates no relation from naming similarity or shared columns.
7. Sample sizes are fixed below shipped batch caps.
8. Cap overflow fails; selection never silently truncates graph closure.
9. Each source gets separate canonical manifest and SHA-256 digest.
10. Equivalent input yields byte-identical canonical sample content.

### Prepare and Commit

1. FE and BO use isolated prepare calls and separate commit tokens.
2. Prepare validates full request before issuing commit authority.
3. Validation covers collection counts, string limits, hashes, prefixes, nested references,
   confidence range, NaN, infinity, protected properties, and `group_id`.
4. Prepare rejects more than 500 entities, 2,000 edges, or 5,000 provenance links.
5. Server derives all identities through UUIDv5 and fixed `GRAPHITI_CATALOG_UUID_NAMESPACE`.
6. Caller UUIDs never control identity.
7. Embeddings are generated before opening Neo4j write transaction.
8. Embedding failure produces no graph write and no usable token.
9. Prepared payload is immutable and content-addressed by deterministic digest.
10. Commit accepts token only, never a resubmitted catalog payload.
11. Token binds batch ID, source, `group_id`, namespace, and prepared digest.
12. Commit returns only after transaction commit or rollback.
13. Conflict or write failure rolls back complete batch.
14. Retry preserves `created_at`, endpoint UUIDs, labels, `name_raw`, and `name_canonical`.
15. Retry may update only allowed mutable fields, including `updated_at`.
16. Logs contain batch IDs and counts only, never full payload, document, source text, or secrets.

### `get_catalog_object_context`

1. Tool name is exactly `get_catalog_object_context`.
2. Request requires `group_id`, source, object type, and exact canonical object identity.
3. Resolution is exact: no BM25, vector search, fuzzy match, alias expansion, or LLM fallback.
4. Success returns exactly one typed focal object.
5. Duplicate exact matches return typed integrity error, not arbitrary first match.
6. Missing exact match returns typed not-found result.
7. Default `neighbor_limit` is 25; accepted range is 0 through 100.
8. Neighbors are direct stored one-hop objects only.
9. Neighbor query fetches at most requested limit plus one for truncation detection.
10. Neighbor order is relation type, object type, canonical name, source, then UUID.
11. No second-hop object, path, transitive claim, inferred relation, or impact result appears.
12. Default `evidence_limit` is 10; accepted range is 0 through 25.
13. Each evidence excerpt is at most 1,000 Unicode code points.
14. Every evidence item has typed stable locator and source document digest.
15. Default `image_limit` is 3; accepted range is 0 through 10.
16. Every image has source document binding and typed locator.
17. Source-mismatched evidence or image is never returned.
18. Response reports applied limits and `truncated` for each bounded collection.
19. Invalid bounds fail before database access.
20. Every read constrains exact `group_id` and source.
21. Tool uses Neo4j read access only.
22. Tool never calls prepare, commit, embedder, LLM, queue, index creation, or repair.
23. Success, not-found, validation, and integrity-error paths perform zero writes.
24. Unchanged graph and request produce same logical response and canonical digest.

### Acceptance Artifacts

1. Each run writes a new canary directory.
2. Frozen v1.1 and prior v1.2 canary directories are never overwritten.
3. Canonical serialization fixes field order, collection order, UTF-8 encoding, and digest rules.
4. Manifest records authority, sample, prepare, commit, and context-response digests.
5. FE and BO artifacts remain separate and source-bound.
6. Before snapshot records exact pilot-group object, edge, evidence, and image inventories.
7. After snapshot records same dimensions.
8. Delta acceptance allows only manifest-declared additions and allowed idempotent updates.
9. Unrelated source, group, label, endpoint, evidence, or image change fails acceptance.
10. Commit replay produces zero identity-count delta.
11. Context calls produce zero before/after graph delta.
12. No dependency file or lockfile gains a v1.2 package.

## Feature Dependencies

```text
Authority inventory + digest
  => deterministic FE selection => FE manifest => FE prepare => FE commit
  => deterministic BO selection => BO manifest => BO prepare => BO commit

Shipped v1.1 typed ingest + UUIDv5 + evidence + immutable prepare/token commit
  => source-isolated pilot writes
  => exact focal lookup
  => bounded one-hop context

Before snapshot + source manifests + commits + context reads
  => image binding checks
  => declared-delta proof
  => no-write proof
  => frozen acceptance directory
```

Dependency rules:

- FE and BO commits do not depend on each other.
- BO selection does not depend on inferred relationships.
- Context acceptance depends only on corresponding source commit.
- Production promotion is not an output dependency.
- No phase depends on new packages, Docling, LLMs, or natural-language parsing.

## Edge Cases

| Case | Expected Behavior |
|---|---|
| Authority count differs | Fail before selection; no token and no write |
| Same path has changed JSON | New digest invalidates old manifest/token binding |
| FE candidates tie | Canonical identity and UUID tie-breakers choose stable order |
| FE closure exceeds cap | Fail with cap detail; do not truncate silently |
| BO table has zero columns | Score deterministically under documented rule |
| BO name resembles FE name | Keep isolated; create no map or inferred edge |
| UUID namespace changes after prepare | Reject token at commit |
| Embedder fails midway | Prepare fails; graph remains unchanged |
| Prepared artifact changes | Digest mismatch rejects commit |
| One batch row conflicts | Roll back complete transaction |
| Valid token replays | Return idempotent result; create no duplicate |
| Focal object absent | Typed not-found; zero writes |
| Duplicate exact focal identity | Typed integrity error; no repair write |
| `neighbor_limit` is zero | Return focal object and empty neighbor list |
| Any limit exceeds maximum | Validation error before Neo4j access |
| More neighbors than limit | Return stable prefix with `truncated: true` |
| Neighbor sort fields tie | UUID decides final order |
| Evidence text exceeds cap | Return bounded excerpt, truncation marker, full locator |
| Evidence locator missing | Return fixed integrity outcome; never invent locator |
| Image belongs to other document | Omit/reject and fail image-binding acceptance |
| Same identity exists in another group | Exact `group_id` prevents disclosure |
| Concurrent identical reads | Return same ordering and no side effects |
| Frozen canary path exists | Refuse overwrite; allocate new run directory |
| Read transaction unavailable | Return operational error; never fall back to write mode |

## MVP Definition

MVP is one bounded vertical pilot:

1. Validate authoritative JSON inventory and digest.
2. Select deterministic connected FE sample from `SVFE_SHB`.
3. Select deterministic structurally rich BO sample from `MAIN1` without inferred relations.
4. Produce separate source-bound manifests and digests.
5. Enforce shipped batch caps.
6. Prepare and token-commit FE and BO independently.
7. Expose exact read-only `get_catalog_object_context`.
8. Return typed focal object, stable bounded one-hop neighbors, evidence, locators, and images.
9. Prove source binding, idempotent retry, group isolation, declared delta, and zero-write reads.
10. Freeze acceptance in new canary directories.
11. Add zero dependencies and preserve existing tools, exact search/resolve, and native Ollama.

MVP excludes full ingest, inferred BO relations, FE/BO maps, natural-language orchestration,
multi-hop/path/impact/delta features, Docling, LLM processing, production promotion, and any
repeat of v1.1 canary.

## Requirement-Ready Categories

### Authority Requirements

- SHALL accept only `catalog/catalog.json` as normalized authority.
- SHALL verify all authoritative inventory counts before selection.
- SHALL bind every artifact to authority SHA-256.

### Sampling Requirements

- SHALL select a connected FE sample using authoritative FE relations only.
- SHALL select a rich BO sample using BO structure only.
- SHALL use fixed scoring, total ordering, and deterministic digests.
- SHALL keep FE and BO manifests isolated.

### Write-Safety Requirements

- SHALL validate full request and shipped caps before commit authority.
- SHALL derive UUIDv5 identity server-side.
- SHALL finish embeddings before write transaction.
- SHALL commit by token only and roll back atomically.
- SHALL preserve protected identity and creation fields on retry.

### Context Requirements

- SHALL resolve one exact typed focal object within source and `group_id`.
- SHALL return only stable bounded one-hop neighbors.
- SHALL enforce neighbor 0..100, evidence 0..25, and image 0..10.
- SHALL cap excerpts at 1,000 Unicode code points.
- SHALL report applied bounds and truncation.
- SHALL use read-only database posture with no LLM or embedder call.

### Evidence and Acceptance Requirements

- SHALL bind evidence and images to exact source document and locator.
- SHALL create deterministic manifests, snapshots, and response digests.
- SHALL preserve frozen canary directories.
- SHALL prove declared delta, idempotent replay, and zero-write reads.
- SHALL add zero dependencies.

## Feature Prioritization

| Priority | Capability | Exit Signal |
|---:|---|---|
| P0 | Authority inventory and digest gate | Counts and digest match authoritative facts |
| P0 | Deterministic FE/BO sample manifests | Repeated derivation yields identical isolated manifests |
| P0 | Immutable isolated prepare | Tokens bind separate source payloads and digests |
| P0 | Atomic token-only commit | Replay adds nothing; injected failure rolls back all |
| P0 | Exact read-only focal lookup | Typed FE and BO focal tests pass with zero writes |
| P0 | Bounded stable one-hop neighbors | Bound, ordering, and truncation tests pass |
| P0 | Evidence excerpts and locators | Every item has valid source-bound locator |
| P0 | Delta/no-write acceptance | Only declared commit delta; read delta is zero |
| P1 | Source-bound images | Correct images pass; mismatches fail |
| P1 | Canonical context digest | Repeated reads produce same digest |
| P1 | Run-ledger cross-links | Every artifact digest resolves within run |
| Excluded | Full ingest and production promotion | No implementation or acceptance claim |
| Excluded | Inference, maps, paths, impact, NL | No schema, tool, or dependency added |

Recommended order:

1. Lock authority gate and canonical digest format.
2. Lock deterministic FE/BO selectors and separate manifests.
3. Exercise shipped prepare/commit under isolation and caps.
4. Add minimum exact read-only context focal lookup.
5. Add bounded neighbors, evidence, locators, and image binding.
6. Freeze delta, replay, isolation, and no-write acceptance artifacts.

## Sources

- User-provided authoritative v1.2 scope and inventory facts, 2026-07-24. Confidence: HIGH.
- Shipped v1.1 contract: deterministic catalog-v2 typed ingest, evidence, immutable prepare,
  token-only commit, manifests, exact resolve/search, and native Ollama. Confidence: HIGH.
- Project constraints: Neo4j-first transactions, server UUIDv5 identity, validation, embedding
  order, group isolation, safe logging, field preservation, and batch caps. Confidence: HIGH.
- `catalog/catalog.json` intentionally not inspected; supplied inventory is authoritative.
  Confidence: HIGH.
