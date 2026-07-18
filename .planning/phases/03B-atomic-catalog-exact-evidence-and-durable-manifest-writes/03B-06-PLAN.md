---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 06
type: tdd
wave: 6
depends_on:
  - 03B-03
  - 03B-04
  - 03B-05
files_modified:
  - mcp_server/tests/test_catalog_commit_neo4j_int.py
  - mcp_server/tests/catalog_phase3b_gate_runner.py
  - mcp_server/tests/test_catalog_phase3b_gate_runner.py
  - mcp_server/src/services/catalog_capabilities.py
  - mcp_server/tests/test_catalog_capabilities.py
  - mcp_server/src/graphiti_mcp_server.py
  - .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-GATE-RESULTS.json
  - .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-EDGE-PROBE-RESOLUTION.json
autonomous: true
requirements:
  - PLAN-13
  - PLAN-14
  - PLAN-15
  - PLAN-16
  - EVID-07
  - EVID-08
  - EVID-09
  - EVID-10
  - EVID-11
  - MANI-01
  - MANI-02
  - MANI-03
  - MANI-04
  - MANI-06
  - MANI-07
  - TEST-06
  - TEST-07
must_haves:
  truths:
    - "Live Neo4j proves single-tx co-commit of domain+evidence+manifest+batch committed+plan COMMITTED under configured ceilings or hard-stops without splitting (PLAN-13, D-03, D-29)"
    - "Live fault/rollback leaves zero partial success artifacts (PLAN-14, D-05, D-30)"
    - "Live replay and same-token concurrency produce one logical batch (PLAN-15, PLAN-16, TEST-06)"
    - "Live evidence non-Entity, non-Cartesian, conflict fail-closed; search still finds catalog Entity nodes (EVID-07..11, EVID-09, TEST-07)"
    - "Live manifest includes unchanged membership; batch_id not used as membership authority (MANI-01..04, MANI-06, MANI-07)"
    - "features.manifests=true only after gate live+unit proofs; manifest_verification remains false; prepare_commit stays true (D-33)"
    - "ready_for_phase_4 true only from fail-closed gate runner with HEAD/content/spec/live/safety green (D-32)"
    - "All tests use only oracle-catalog-tool-test; never query/mutate oracle-catalog-v2; no canary/deploy/push (D-34)"
    - "D-22: Phase 3B creates persistence authorities and internal recovery reads only; all public manifest/evidence reads and manifest-backed verification remain Phase 4 (no get_catalog_batch_manifest, get_catalog_evidence, or manifest-backed verify tools)"
  artifacts:
    - path: mcp_server/tests/test_catalog_commit_neo4j_int.py
      provides: live atomicity suite
      contains: test_live_single_tx_co_commit
    - path: mcp_server/tests/catalog_phase3b_gate_runner.py
      provides: Phase 3B gate authority
      contains: ready_for_phase_4
    - path: mcp_server/src/services/catalog_capabilities.py
      provides: features.manifests flip post-gate condition
      contains: manifests
    - path: .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-GATE-RESULTS.json
      provides: HEAD-bound ledger
      contains: ready_for_phase_4
    - path: .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-EDGE-PROBE-RESOLUTION.json
      provides: 24/24 edge probe resolution map
      contains: resolved
  key_links:
    - from: live co-commit proof
      to: capabilities.features.manifests
      via: gate before flip
    - from: gate runner
      to: ready_for_phase_4
      via: fail-closed AND of checks
  prohibitions:
    - status: unverified
      flagged: true
      statement: no ready_for_phase_4 true without live proof when Neo4j configured
    - status: unverified
      flagged: true
      statement: no manifests capability true before gate
    - status: unverified
      flagged: true
      statement: no runtime read of planning ledger or GATE-RESULTS for features.manifests
    - status: unverified
      flagged: true
      statement: no multi-tx success workaround if live single-tx fails
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy push merge tag
    - status: unverified
      flagged: true
      statement: no Phase 4 public read tool registration
    - status: unverified
      flagged: true
      statement: no non-Neo4j portability claims
---

<objective>
Prove live Neo4j atomic co-commit, isolation, search interop, and control-label exclusion; publish fail-closed Phase 3B gate with 24/24 edge resolution; flip features.manifests only after proof (all Phase 3B reqs; D-29..D-34).

Purpose: Unblock Phase 4 only with honest live evidence; hard-stop if single-tx impossible.
Output: green live suite (or truthful skip blocking readiness), gate results JSON, edge resolution JSON, capabilities flip, MCP response wiring if needed.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-VALIDATION.md
@mcp_server/tests/test_catalog_prepare_neo4j_int.py
@mcp_server/tests/catalog_phase3a_gate_runner.py
@mcp_server/src/services/catalog_capabilities.py
@mcp_server/src/graphiti_mcp_server.py
@mcp_server/tests/test_catalog_capabilities.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| live commit int suite | tests | GREEN or skip-blocked |
| catalog_phase3b_gate_runner | runner | complete |
| 03B-GATE-RESULTS.json | ledger | create |
| 03B-EDGE-PROBE-RESOLUTION.json | 24/24 map | create |
| features.manifests | capability | true after gate |
| features.manifest_verification | capability | remains false |

## Interface contracts

- Hard stop procedure: if live cannot co-commit or rollback cleanly at configured maxima, write gate ready_for_phase_4=false with stop reason; do not implement multi-tx success.
- After gate proof is green during plan 06 execution, set a **static** source assignment `features['manifests'] = True` (or equivalent literal True in the features dict builder) inside `mcp_server/src/services/catalog_capabilities.py` only. Runtime product code MUST NOT read `.planning/*`, `03B-GATE-RESULTS.json`, or any mutable planning ledger to decide the flag. Keep `features['manifest_verification'] = False` (Phase 4). Follow Phase 3A `prepare_commit` static-true-after-proof pattern — not a runtime file probe.
- MCP: no new tool names; commit response additive fields only if thin wrapper needs update.
- Edge resolution file maps all 24 rows to plan acceptance criteria IDs; zero unresolved silent.

## Edge probe discharge (complete 24/24)

All rows from specless probe must appear in 03B-EDGE-PROBE-RESOLUTION.json with verification explicit:

1. PLAN-13 adjacency/empty/ordering → plan 04+06 live
2. PLAN-14/15/16 unclassified → plan 05+06
3. EVID-07..10 unclassified → plan 03+06
4. EVID-11 empty/encoding → plan 03+06
5. MANI-01 adjacency/empty/ordering → plan 02+06
6. MANI-02 concurrency → plan 05+06
7. MANI-03 unclassified → plan 02+06 (assert no batch_id membership)
8. MANI-04 adjacency/empty/ordering → plan 02+03+06
9. MANI-06/07 unclassified → plan 04+05+06
10. TEST-06/07 unclassified → plan 05+06

Flagged assumptions retained: A1 size estimate; A5 lock; grapheme encoding not used.

## Prohibition recall (precision kept)

| Kept | status | flagged |
|------|--------|---------|
| never split success across Neo4j transactions | unverified | true |
| never reset COMMITTING to PREPARED | unverified | true |
| never infer membership from batch_id | unverified | true |
| never Entity-label evidence/manifest | unverified | true |
| never Cartesian provenance writes | unverified | true |
| never external I/O on prepared commit | unverified | true |
| never canary / oracle-catalog-v2 / clear_graph / deploy / delete | unverified | true |

Canon security breadcrumbs (not duplicated as product prohibitions): fixed Cypher, group isolation, token digest secrecy, bounded logs → secure-phase / threat models.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Live Neo4j co-commit rollback search isolation proof</name>
  <files>mcp_server/tests/test_catalog_commit_neo4j_int.py</files>
  <read_first>
    mcp_server/tests/test_catalog_prepare_neo4j_int.py
    mcp_server/tests/catalog_neo4j_fixtures.py
    mcp_server/src/services/catalog_service.py
    .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md (hard stop)
  </read_first>
  <behavior>
    - prepare+commit happy path: domain Entity searchable; evidence/manifest labels exclude Entity; manifest root exists with counts including unchanged
    - inject failure mid-success via test hook or constrained conflict: zero partial domain/evidence/manifest/committed/plan-COMMITTED
    - replay commit: stable; no dup manifest
    - optional concurrent same-token if fixture allows
    - group only oracle-catalog-tool-test; assert no session uses oracle-catalog-v2
    - unavailable Neo4j: skip with reason; do not fake pass
  </behavior>
  <action>
    Implement live tests. If single-tx proof fails at ceilings, stop and record hard-stop in gate — do not split. Per D-03, D-05, D-29, D-30, D-31, D-34. Cleanup only test group data created by test (no clear_graph global).
  </action>
  <acceptance_criteria>
    - Live suite green when Neo4j available
    - When unavailable, skips truthful; gate will not set ready_for_phase_4 true
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_commit_neo4j_int.py -q --tb=line</automated>
  </verify>
  <done>Live atomicity/search/isolation proofs exist and pass or skip truthfully.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Gate runner ledger edge map capabilities flip</name>
  <files>mcp_server/tests/catalog_phase3b_gate_runner.py, mcp_server/tests/test_catalog_phase3b_gate_runner.py, mcp_server/src/services/catalog_capabilities.py, mcp_server/tests/test_catalog_capabilities.py, mcp_server/src/graphiti_mcp_server.py, .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-GATE-RESULTS.json, .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-EDGE-PROBE-RESOLUTION.json</files>
  <read_first>
    mcp_server/tests/catalog_phase3a_gate_runner.py
    mcp_server/src/services/catalog_capabilities.py
    mcp_server/tests/test_catalog_capabilities.py
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json
  </read_first>
  <behavior>
    - Gate checks: unit suites, fault inject, recovery, concurrency, live, safety (no v2, no canary strings in changed product paths), edge 24/24
    - ready_for_phase_4 true only if all required green; else false
    - After gate proof green in this plan's execution, set static features['manifests'] = True in catalog_capabilities.py source; features['manifest_verification'] remains False; runtime must not read .planning or GATE-RESULTS
    - EDGE-PROBE-RESOLUTION.json lists all 24 items resolved with plan references
    - GATE-RESULTS.json HEAD/content digests LF-stable like Phase 1/3A
  </behavior>
  <action>
    Complete gate runner; emit planning JSON ledgers under phase dir (ledger is audit authority only). After unit+live+safety gate proof is green during execution, edit catalog_capabilities.py so the features dict contains a static True for manifests (literal assignment in source). Runtime MUST NOT open .planning/*, 03B-GATE-RESULTS.json, or any mutable ledger to decide manifests. Keep manifest_verification=False. Touch graphiti_mcp_server.py only if commit response wiring requires additive fields. Extend test_catalog_capabilities.py to assert features['manifests'] is True and features['manifest_verification'] is False without mocking planning files. Per D-32, D-33, D-34.
  </action>
  <acceptance_criteria>
    - test_catalog_phase3b_gate_runner.py and test_catalog_capabilities.py green
    - 03B-EDGE-PROBE-RESOLUTION.json coverage resolved==24
    - ready_for_phase_4 reflects truthful live status
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_phase3b_gate_runner.py mcp_server/tests/test_catalog_capabilities.py -q --tb=line</automated>
  </verify>
  <done>Phase 3B gate authority published; capabilities truthful; 24/24 edges mapped.</done>
</task>

</tasks>

<threat_model>

## ASVS L1

Security enforcement target: **OWASP ASVS Level 1**. Applicable L1 control tags for this plan:

| ASVS L1 tag | Control focus | How this plan applies |
|-------------|---------------|------------------------|
| V4.1 Access Control | group isolation; authority bound to token digest / group_id | Every Neo4j read/write group-scoped; no cross-group |
| V5.1 Input Validation | strict models; fixed allowlists; no client Cypher identifiers | Server-owned labels/properties only; bound params |
| V6.2 Cryptography | UUIDv5 + SHA-256 content/manifest; timing-safe token compare | Digests only; no raw token storage on commit path |
| V7.1 Error Handling | bounded structured errors | IDs/counts/codes only; no payload/token/embeddings |
| V14.2 Dependency | no new packages this phase | Package installs forbidden |

High and critical threats in the STRIDE register below remain **mitigate** (never accept).

## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| live DB | Only tool-test group |
| gate ledger | Phase 4 unblock authority |
| capabilities | Clients trust feature flags |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03B-01 | Tampering | live partial commit | critical | mitigate | Live rollback proof; hard stop if fail |
| T-03B-GATE | Spoofing | ready_for_phase_4 | high | mitigate | Fail-closed runner; require live |
| T-03B-CAP | Spoofing | features.manifests | medium | mitigate | Flip only after gate |
| T-03B-ISO | Elevation | oracle-catalog-v2 | critical | mitigate | Ban group; safety checks |
| T-03B-INFO | Information disclosure | logs/errors | medium | mitigate | IDs/counts only |
| T-03B-SC | Tampering | deps | high | mitigate | No new packages |
</threat_model>

## Flagged assumptions

- Live credentials may be absent: readiness blocked (not forged)
- A1 chunk estimate validated or fail-closed at hard max

<verification>
Live suite + gate + capabilities tests; edge resolution 24/24.
</verification>

<success_criteria>
Phase 3B unblocks Phase 4 only with honest atomicity proof; manifests capability true; verification capability false; safety intact.
</success_criteria>

<output>
Create `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-06-SUMMARY.md` when done
</output>
