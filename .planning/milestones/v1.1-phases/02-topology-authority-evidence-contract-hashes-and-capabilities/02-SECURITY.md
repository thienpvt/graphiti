---
phase: 02
slug: topology-authority-evidence-contract-hashes-and-capabilities
status: verified
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: true
block_on: high
created: 2026-07-18
---

# Phase 02 — Security

> ASVS L1 verification of the threat register authored in Plans 02-01 through 02-05.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| MCP client → strict catalog models | Untrusted catalog-v2 requests enter validation | Graph keys, edge types, evidence, hashes, limits |
| Validated request → deterministic identity/hash | Server becomes identity and hash authority | Canonical request material, UUID namespace fingerprint |
| Validated batch → catalog service | Preflight must reject before reads, embeddings, transactions, or status writes | Entities, edges, sources, evidence links |
| Server configuration → capability response | Operational metadata becomes client-visible | Versions, limits, registries, namespace fingerprint |
| Repository → Phase 3A gate | Tracked checks become readiness authority | HEAD/content digests, test results, safety flags |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Evidence | Status |
|-----------|----------|-----------|----------|-------------|---------------------|--------|
| T-02-01 | Tampering | Endpoint topology | high | mitigate | Immutable `EDGE_ENDPOINT_MAP`; model/service preflight; exhaustive `test_catalog_topology.py` matrix | closed |
| T-02-02 | Tampering | Evidence contract | high | mitigate | Exclusive source/typed target; Cartesian fields rejected; evidence/model/service tests | closed |
| T-02-03 | Tampering | Request hash recipe | high | mitigate | Versioned full-domain canonical recipe; mutation/order/exclusion tests; server hash authority | closed |
| T-02-04 | Information disclosure | Capabilities | high | mitigate | Domain-separated namespace fingerprint; no raw namespace/secrets; redaction tests | closed |
| T-02-05 | Tampering | Capability side effects | high | mitigate | Pure capability builder; zero-mutation spies; usable while writes disabled | closed |
| T-02-06 | Elevation of privilege | Deferred edge types | high | mitigate | Deferred types absent from registries and rejected by model/service tests | closed |
| T-02-07 | Information disclosure | Evidence validation errors | medium | mitigate | Bounded evidence fields; safe field-path errors; full excerpt excluded from validation messages | closed |
| T-02-08 | Denial of service | Endpoint map | medium | mitigate | Finite immutable endpoint-pair sets; no open any-to-any topology | closed |
| T-02-09 | Denial of service | Evidence collections | medium | mitigate | Evidence length and hard collection ceilings enforced by strict models | closed |
| T-02-10 | Spoofing | Caller `request_sha256` | medium | mitigate | Caller hash audit-only; exact-match check; server-computed hash remains authoritative | closed |
| T-02-11 | Tampering | Phase 2 gate ledger | high | mitigate | HEAD/spec/content/raw-probe digest binding; sentinel; stale/tamper refusal; fail-closed readiness | closed |
| T-02-SC | Tampering | Dependency supply chain | high | accept | Phase 2 added no packages or lockfile changes; any future dependency change reopens V14.2.1 | closed |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-SC | No new dependency or lockfile changes in Phase 2. Existing project supply-chain controls remain unchanged. Any later dependency addition reopens review. | Phase 2 plan constraint | 2026-07-18 |

---

## Verification Evidence

- Topology authority: `mcp_server/src/models/catalog_topology.py`; `mcp_server/tests/test_catalog_topology.py`.
- Evidence contract: `mcp_server/src/models/catalog_evidence.py`; `mcp_server/src/models/catalog_batch.py`; `mcp_server/tests/test_catalog_evidence.py`.
- Hash authority: `mcp_server/src/services/catalog_identity.py`; `mcp_server/tests/test_catalog_hash.py`.
- Read-only capabilities: `mcp_server/src/services/catalog_capabilities.py`; `mcp_server/tests/test_catalog_capabilities.py`.
- Gate integrity: `mcp_server/tests/catalog_phase2_gate_runner.py`; `mcp_server/tests/test_catalog_phase2_gate_runner.py`.
- Final local evidence: 927 focused tests, 396 topology/evidence/hash/capability tests, 15 runner tests; Ruff pass; Pyright pass.
- Safety ledger: `canary_executed=false`; `oracle_catalog_v2_queried=false`; `no_new_store_or_control_plane_write_path=true`.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-18 | 12 | 12 | 0 | `gsd-security-auditor` |

---

## Sign-Off

- [x] All threats have a disposition.
- [x] Accepted risks documented.
- [x] `threats_open: 0` confirmed at ASVS L1, block threshold high.
- [x] `status: verified` set.
- [x] No implementation files changed by the audit.

**Approval:** verified 2026-07-18
