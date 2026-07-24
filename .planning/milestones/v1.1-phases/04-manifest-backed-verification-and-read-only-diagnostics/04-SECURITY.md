---
phase: 04
slug: manifest-backed-verification-and-read-only-diagnostics
status: verified
threats_open: 0
asvs_level: 1
block_on: high
created: 2026-07-19
verified: 2026-07-19
verified_head: 2627e11db69721122eb1c686597e7cfe75e209fb
register_authored_at_plan_time: true
---

# Phase 04 -- Security

> Per-phase security contract: threat register, accepted risks, historical safety audit, and audit trail for manifest-backed verification and read-only diagnostics.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|--------|---------|----------|
| MCP client to CatalogService gates | Untrusted group_id, pagination, edge/entity keys, batch_id, gate flags | Request params; validated before store |
| expected membership authority | When batch_id present, durable committed manifest is sole expected source; live Neo4j rows are observations only | Manifest body membership vs live MATCH rows |
| client pagination to service | offset/limit untrusted; hard max 500 fail-closed | Page bounds only |
| client edge keys to Cypher | Allowlisted edge types / fixed labels only; values as params | Parameterized MATCH |
| service to Neo4j (read path) | _read_many only for Phase 4 diagnostic reads; no schema ensure, write tx, embedder, or queue | group_id-scoped parameterized Cypher |
| capabilities builder to runtime | Truthful flags from config/constants; must not probe DB or read .planning | Feature flags, limits, namespace fingerprint |
| reassembly / verify response to client | Compact projections; ban embeddings, payload_b64, raw source dump, credentials | Anomaly kinds + compact fields |
| MCP registration surface to clients | Frozen 14-name CATALOG_TOOL_NAMES (28-tool overall contract preserved) | Tool names + thin wrappers |
| gate ledger to Phase 5 | ready_for_phase_5 fail-closed AND of proofs; historical v2 audit pointer only | Structural gate + unit/service pass |
| live/test group isolation | Tests and scaffolds use oracle-catalog-tool-test only; ban current oracle-catalog-v2 access | group_id literals / params |

---

## Threat Register

Consolidated unique threats across plans 04-01..04-06. Severity order: critical > high > medium > low. Only OPEN threats at or above block_on high count toward threats_open.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|---------|---------|---------|---------|----------|-----------|-------|
| T-04-AUTH | Spoofing | expected membership / tool set | high | mitigate | Durable committed manifest sole expected authority when batch_id present (verify_catalog_batch + _load_committed_manifest_body); server UUIDv5 re-derived; exact 14-name CATALOG_TOOL_NAMES freeze | closed |
| T-04-DRIFT | Tampering | missing/extra collapse | high | mitigate | Distinct missing vs extras vs explicit_key_missing; never set expected from live row counts; evidence extras batch+group observation only | closed |
| T-04-MANI | Spoofing | manifest integrity / membership source | high | mitigate | Reassembly + manifest_sha256 fail-closed (manifest_mismatch); missing root/status to found=false; incomplete chunks fail closed; no live synthesis of membership | closed |
| T-04-INFO | Information disclosure | verify / evidence / status projection | high | mitigate | Compact default responses; excerpts opt-in + length-bounded; no embeddings/payload_b64/raw source/credentials in anomalies or logs (type names / counts only) | closed |
| T-04-READ | Tampering | read path mutation | high | mitigate | Phase 4 diagnostic store loaders use _read_many only; verify/resolve/evidence/manifest-read never schema-init, write tx, embedder, or queue | closed |
| T-04-ISO | Elevation of privilege | group isolation | high | mitigate | Empty group_id rejected in _read_gate; every MATCH binds group_id param; scaffolds/tests hard-code oracle-catalog-tool-test; gate bans current v2 | closed |
| T-04-INJ | Tampering | Cypher injection | high | mitigate | Fixed server labels (CatalogEvidenceLink, CatalogBatchManifestChunk, Entity/RELATES_TO); allowlisted entity/edge types; client values only as params | closed |
| T-04-CAP | Spoofing | capabilities flags | high | mitigate | build_catalog_capabilities pure; manifest_verification True static after proofs; no .planning / GATE-RESULTS runtime reads | closed |
| T-04-GATE | Spoofing | feature_disabled / ready_for_phase_5 | high | mitigate | _read_gate uses reads_enabled not write enabled; derive_ready_for_phase_5 fail-closed AND of unit/service/registration/safety + manifest_verification | closed |
| T-04-BOUND | Denial of service | page size | medium | mitigate | HARD_MAX_PAGE_SIZE = 500; service fail-closed on oversize limit; capabilities reports hard max | closed |
| T-04-SC | Tampering | supply chain / packages | high | mitigate | No new package installs in Phase 4 plans; gate/runner do not add deps | closed |

### Mitigation evidence (source, not test names alone)

| Threat ID | Evidence |
|-----------|----------|
| T-04-AUTH | catalog_service.py verify_catalog_batch (~2024-2191): batch_id path loads committed durable manifest as sole expected; live MATCH is observation. graphiti_mcp_server.py CATALOG_TOOL_NAMES frozenset size 14 with Phase 4 reads. |
| T-04-DRIFT | catalog_service.py _verify_entities / edge / evidence sections: separate missing, extras, explicit_key_missing, extra_evidence; never set expected from len(rows). |
| T-04-MANI | catalog_service.py _load_committed_manifest_body (~4826-4915): missing root / incomplete chunks / digest mismatch to manifest_mismatch or found=false. Store load_manifest_chunks_with_payload via _read_many. |
| T-04-INFO | catalog_responses.py compact evidence projection; get_catalog_evidence strips excerpt unless include_excerpts and truncates to MAX_EVIDENCE_LENGTH; MCP wrappers log type names / counts only. |
| T-04-READ | Store match/load helpers call _read_many; verify_catalog_batch is read-only (never schema-init or write); resolve/evidence same pattern. |
| T-04-ISO | _read_gate requires non-empty group_id; Cypher WHERE n.group_id =  / composite keys; catalog_phase4_gate_runner.py FORBIDDEN_GROUP / ALLOWED_TEST_GROUP. |
| T-04-INJ | Fixed-label Cypher builders in catalog_store.py (build_match_evidence_links_*, build_load_manifest_chunks_cypher, resolve/verify match builders); params dict only. |
| T-04-CAP | catalog_capabilities.py pure builder; features.manifest_verification True; comments forbid .planning runtime; gate check_manifest_verification_true scans for planning paths. |
| T-04-GATE | _read_gate checks reads_enabled; derive_ready_for_phase_5 requires local_gate + unit_service + registration + safety + manifest_verification. |
| T-04-BOUND | HARD_MAX_PAGE_SIZE = 500 in catalog_capabilities.py; get_catalog_evidence / manifest page paths reject limit > HARD_MAX_PAGE_SIZE. |
| T-04-SC | Phase 4 plans declare no installs; implementation adds only source/tests under existing package. |

---

## Historical Safety Audit (current-vs-historical v2)

| Axis | Finding | Status |
|------|---------|--------|
| Historical pointer a67789a | Preserved under gate historical_audit only; documents past read-only v2 count probe as permanent audit record | preserved |
| Current oracle-catalog-v2 access | Gate check_safety_no_probe + assignment/kw bans; current axis oracle_catalog_v2_queried=false | closed / banned |
| Test group | oracle-catalog-tool-test hard-coded for Phase 4 tests/scaffolds | enforced |
| Canary / clear / deploy | Gate asserts canary_executed=false; no clear_graph / live migrate in Phase 4 | closed |
| ready_for_phase_5 | True only after proofs + manifest_verification (ledger post-04-06); not a runtime capabilities input | fail-closed |

---

## Accepted Risks Log

No accepted risks.

---

## Unregistered Threat Flags

None. SUMMARY.md Threat Flags entries across 04-02..04-06 map to the register above (no new attack surface without mapping).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open (blocking) | Open (non-blocking) | ASVS | Run By |
|------------|---------------|--------|-----------------|---------------------|------|--------|
| 2026-07-19 | 11 | 11 | 0 | 0 | L1 | gsd-secure-phase / security auditor (orchestrator) |

### Audit notes

- Input state: B (no prior SECURITY.md; six PLANs with authored threat_model; six SUMMARYs present).
- Config: asvs_level=1, block_on=high.
- Depth: L1 present-in-code verification against cited mitigation sites; cross-checked implementation (not documentation-only).
- Cross-refs: 04-REVIEW.md clean at 92cee52; 04-GATE-RESULTS.json ready_for_phase_5 / no current v2; focused suite 380 passed (per SUMMARY/REVIEW).
- Implementation files not modified during this audit.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (none)
- [x] threats_open: 0 confirmed (no open high/critical)
- [x] status: verified set in frontmatter

**Approval:** verified 2026-07-19
