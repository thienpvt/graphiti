---
phase: 03A
slug: immutable-prepare-commit-control-plane
status: verified
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: true
block_on: high
created: 2026-07-18
---

# Phase 03A — Security

> ASVS L1 verification of the planned immutable prepare/commit control-plane threat register.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| MCP client → strict request models | Untrusted prepare/commit/discard arguments | Catalog payload, bearer plan token |
| Service → embedder | External precomputation before plan persistence | Names/facts; no token |
| Service → prepared store | Control-plane persistence and CAS authority | Canonical artifact, digest, metadata |
| Prepared store → commit service | Restart-safe token-authorized artifact load | Root/chunks, hashes, frozen embeddings |
| Phase gate → Phase 3B | Readiness authority | HEAD-bound results and safety ledger |
| Test group → shared Neo4j | Integration isolation boundary | `oracle-catalog-tool-test` records only |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-03A-01 | Spoofing / Elevation | `plan_token` | high | mitigate | `secrets.token_urlsafe(32)`; domain-separated SHA-256 digest only; post-load timing-safe match; scope binding; TTL and terminal state | closed |
| T-03A-02 | Information disclosure | Token comparison/errors | high | mitigate | `hmac.compare_digest`; malformed digests fail closed; discarded/mismatch use bounded `prepared_plan_not_found` | closed |
| T-03A-03 | Tampering | Prepared artifact | high | mitigate | Complete canonical membership and embeddings; CREATE-once root/chunks; chunk and artifact digests; live restart proof | closed |
| T-03A-04 | Tampering / Injection | Requests and Cypher | high | mitigate | Token-only strict models; `extra='forbid'`; fixed labels and property allowlists; no caller schema authority | closed |
| T-03A-05 | Denial of service | Limits/capacity | high | mitigate | Immutable configured/hard ceilings; group lock; same-transaction active count/create | closed |
| T-03A-06 | Tampering | Chunk storage | high | mitigate | Ordered indexes, offsets, lengths, base64 validation, per-chunk digest, total digest/count verification | closed |
| T-03A-07 | Tampering | Plan state | high | mitigate | Explicit legal CAS matrix; no transition back to PREPARED; terminal non-revival; terminal EXPIRED live proof | closed |
| T-03A-08 | Tampering | External computation/write order | high | mitigate | All embeddings before plan transaction; failure leaves no artifact; commit uses frozen data and stops at COMMITTING | closed |
| T-03A-09 | Information disclosure | Responses/logs | high | mitigate | Raw token returned once; receipts expose hashes/counts/state only; logs omit token, payload, source text, embeddings | closed |
| T-03A-SC | Supply chain | Dependencies | high | accept | No new packages; token/artifact cryptography uses Python stdlib | closed |

---

## Review-Fix Security Evidence

| Finding | Closure |
|---------|---------|
| WR-01 | Malformed stored digest returns false; never raises or bypasses timing-safe authorization. |
| WR-02 | Prepared schema initialization uses a process lock, once-ready state, and post-DDL `SHOW CONSTRAINTS` verification. |
| WR-03 | Prepare checks committed batch authority before artifact persistence. |
| WR-04 | Byte-identical evidence links coalesce; divergent same-key links fail with `provenance_link_conflict`. |
| WR-05 | Store defaults to the authoritative `CANONICALIZATION_VERSION`. |
| WR-06 | Prepared identity uniqueness races map fail-closed to `prepared_plan_conflict`. |
| WR-07 | Live expiry proof requires terminal `EXPIRED`; residual PREPARED fails. |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03A-01 | T-03A-SC | Phase 3A adds no dependencies; future dependency additions reopen supply-chain review. | Planned threat register | 2026-07-18 |

---

## Operational Safety Evidence

- Live Neo4j proof: 9/9 passed using only `oracle-catalog-tool-test`.
- `canary_executed=false`.
- `oracle_catalog_v2_queried=false`.
- `clear_graph_called=false`.
- `no_domain_write_on_prepare=true`.
- `no_external_call_on_commit=true`.
- `features.prepare_commit=true` only after the live gate passed.
- No deployment or remote-state mutation performed.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-18 | 10 | 10 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition.
- [x] Accepted risks documented.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set.
- [x] ASVS L1 boundary and mitigation evidence verified.

**Approval:** verified 2026-07-18
