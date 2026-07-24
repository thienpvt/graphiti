---
phase: 03B
slug: atomic-catalog-exact-evidence-and-durable-manifest-writes
status: verified
threats_open: 0
threats_total: 16
asvs_level: 1
block_on: high
register_authored_at_plan_time: true
created: 2026-07-18
---

# Phase 03B — Security

> ASVS Level 1 verification of the Phase 3B authored STRIDE register.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| MCP request → strict catalog models | Untrusted catalog-v2 request enters deterministic service | Identity, hashes, entities, edges, provenance, evidence |
| Prepared artifact → commit | Immutable persisted artifact replaces caller payload | Plan token digest, frozen projections, embeddings, membership |
| Service → Neo4j transaction | Domain, evidence, manifest, and terminal state co-commit | Parameterized Cypher values scoped by `group_id` |
| Gate runner → live local Neo4j | Readiness proof uses the isolated test group | `oracle-catalog-tool-test` only |
| Runtime → response/log surface | Internal failures become bounded diagnostics | IDs, counts, fixed error codes/messages only |

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation evidence | Status |
|-----------|----------|-----------|----------|-------------|---------------------|--------|
| T-03B-01 | Tampering | Atomic co-commit | critical | mitigate | Shared success transaction, driver rollback, fault-injection and live post-manifest rollback tests | closed |
| T-03B-02 | Elevation of privilege | Concurrent authority | high | mitigate | Plan lock, transaction-local CAS, uniqueness, same-token/same-batch concurrency tests | closed |
| T-03B-GATE | Spoofing | Readiness authority | high | mitigate | Fail-closed gate requires local, live, current safety, static manifest capability | closed |
| T-03B-SC | Tampering | Dependencies | high | mitigate | No Phase 3B dependency or lockfile changes | closed |
| T-03B-ISO | Elevation of privilege | Group isolation | critical | mitigate | `group_id` on evidence/manifest/terminal reads/writes; TrackingDriver and source guard | closed |
| T-03B-04 | Tampering | Manifest body | high | mitigate | Canonical bytes/hash, bounded chunks, create-once digest comparison | closed |
| T-03B-INFO | Information disclosure | Responses/logs | medium | mitigate | Bounded response models, token omission, fixed typed store-error messages | closed |
| T-03B-BOUND | Denial of service | Artifact/manifest ceilings | medium | mitigate | Pre-persistence byte/chunk limits and hard-plus-one tests | closed |
| T-03B-03 | Tampering | Evidence persistence | high | mitigate | Create-once identity/content binding, target resolution, conflict tests | closed |
| T-03B-05 | Elevation of privilege | Entity pollution | high | mitigate | Fixed control labels; evidence/manifest nodes never carry `Entity` | closed |
| T-03B-CY | Tampering | Cypher construction | critical | mitigate | Fixed server labels/properties; parameterized values; query-boundary tests | closed |
| T-03B-EXT | Tampering | External call during commit | high | mitigate | Commit uses frozen artifact; no embedder/LLM/queue/HTTP; zero-call tests | closed |
| T-03B-FAIL | Spoofing | Failed status | high | mitigate | Failure status written only post-rollback; no success manifest/terminal survives | closed |
| T-03B-REVIVE | Tampering | Plan state revival | high | mitigate | CAS legality excludes `COMMITTING → PREPARED`; recovery tests | closed |
| T-03B-DUP | Tampering | Duplicate manifests/domain | high | mitigate | Composite uniqueness, create-once checks, race tests | closed |
| T-03B-CAP | Spoofing | Manifest capability | medium | mitigate | Static post-proof capability; gate checks `manifests=true`, verification remains false | closed |

## Historical Safety Audit

The permanent historical `a67789a` local test-policy query is retained. It targeted local Neo4j with no corresponding catalog data. Current source and execution safety remain a separate axis: current forbidden-group query/mutation is false; all final live tests use only `oracle-catalog-tool-test`.

## Accepted Risks Log

No accepted risks.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-18 | 16 | 16 | 0 | Claude (`gsd-security-auditor`) |

## Sign-Off

- [x] All authored threats have a disposition.
- [x] All mitigations verified at ASVS Level 1.
- [x] No accepted risks required.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set.

**Approval:** verified 2026-07-18
