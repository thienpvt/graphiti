---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - mcp_server/tests/test_catalog_manifest.py
  - mcp_server/tests/test_catalog_evidence_store.py
  - mcp_server/tests/test_catalog_atomic_writer.py
  - mcp_server/tests/test_catalog_commit_recovery.py
  - mcp_server/tests/test_catalog_concurrency.py
  - mcp_server/tests/test_catalog_commit_neo4j_int.py
  - mcp_server/tests/test_catalog_phase3b_gate_runner.py
  - mcp_server/tests/catalog_phase3b_gate_runner.py
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
    - "Wave 0 Nyquist scaffolds exist for every Phase 3B missing test module listed in 03B-VALIDATION.md (D-30, D-31)"
    - "Each scaffold declares named failing tests so RED is observable before GREEN plans"
    - "Gate runner scaffold mirrors Phase 3A fail-closed HEAD/content/spec/live ledger and defaults ready_for_phase_4=false (D-32)"
    - "Live integration scaffold hard-codes group_id oracle-catalog-tool-test only and never references oracle-catalog-v2 (D-34)"
  artifacts:
    - path: mcp_server/tests/test_catalog_manifest.py
      provides: RED pure manifest suite skeleton
      contains: test_manifest_canonical_bytes_stable
    - path: mcp_server/tests/test_catalog_evidence_store.py
      provides: RED evidence store suite skeleton
      contains: test_evidence_create_once_conflict
    - path: mcp_server/tests/test_catalog_atomic_writer.py
      provides: RED shared writer + fault-inject suite skeleton
      contains: test_fault_inject_after_entities_rolls_back
    - path: mcp_server/tests/test_catalog_commit_recovery.py
      provides: RED stranded COMMITTING recovery suite skeleton
      contains: test_terminal_agreement_returns_stable_receipt
    - path: mcp_server/tests/test_catalog_concurrency.py
      provides: RED concurrency suite skeleton
      contains: test_same_token_concurrent_one_logical_commit
    - path: mcp_server/tests/test_catalog_commit_neo4j_int.py
      provides: RED live Neo4j suite skeleton
      contains: test_live_single_tx_co_commit
    - path: mcp_server/tests/catalog_phase3b_gate_runner.py
      provides: fail-closed Phase 3B gate runner module
      contains: ready_for_phase_4
    - path: mcp_server/tests/test_catalog_phase3b_gate_runner.py
      provides: unit tests for gate runner fail-closed defaults
      contains: test_ready_for_phase_4_false_without_live
  key_links:
    - from: 03B-VALIDATION.md Wave 0 list
      to: seven test modules + gate runner
      via: one scaffold file per missing row
    - from: catalog_phase3a_gate_runner.py
      to: catalog_phase3b_gate_runner.py
      via: structural HEAD/content/spec/live pattern
  prohibitions:
    - status: unverified
      flagged: true
      statement: no product implementation that makes all RED suites pass in this plan
    - status: unverified
      flagged: true
      statement: no canary execution or oracle-catalog-v2 query mutation
    - status: unverified
      flagged: true
      statement: no clear_graph deploy push merge tag or existing-data deletion
    - status: unverified
      flagged: true
      statement: no new third-party dependencies
    - status: unverified
      flagged: true
      statement: no Phase 4 public read tools registration
---

<objective>
Create Wave 0 TDD RED scaffolds for every missing Phase 3B automated suite and the fail-closed gate runner so later plans have Nyquist-compliant verify targets (D-30, D-31, D-32, D-34; all PLAN/EVID/MANI/TEST IDs referenced by named cases).

Purpose: Validation map requires missing files before GREEN implementation; gate defaults block Phase 4.
Output: Seven test modules + catalog_phase3b_gate_runner.py with named failing/skipped-live cases; no production commit success path.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-PATTERNS.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-VALIDATION.md
@mcp_server/tests/catalog_phase3a_gate_runner.py
@mcp_server/tests/test_catalog_phase3a_gate_runner.py
@mcp_server/tests/test_catalog_prepared_artifact.py
@mcp_server/tests/test_catalog_prepare_neo4j_int.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `test_catalog_manifest.py` | RED unit suite | create |
| `test_catalog_evidence_store.py` | RED unit/store suite | create |
| `test_catalog_atomic_writer.py` | RED service suite | create |
| `test_catalog_commit_recovery.py` | RED service suite | create |
| `test_catalog_concurrency.py` | RED concurrency suite | create |
| `test_catalog_commit_neo4j_int.py` | RED live suite | create |
| `catalog_phase3b_gate_runner.py` | gate runner | create |
| `test_catalog_phase3b_gate_runner.py` | gate unit suite | create |

## Interface contracts (parallel-safe)

- Tests and gate runner only. Do not implement catalog_manifest.py, evidence/manifest store writers, or shared atomic writer.
- Gate JSON includes ready_for_phase_4 default false, local_gate_pass, live_neo4j, safety flags (no canary / no oracle-catalog-v2).
- Live tests skip when Neo4j unavailable; never claim green live without probe.
- Live group constant: oracle-catalog-tool-test only.

## Edge probe discharge (this plan)

Scaffolds name cases covering all 24 probe rows for later GREEN plans; no silent drop.

## Assumption delta

A2 schema DDL outside success tx: no-change. A5 SET uuid=uuid locks: no-change. Live ceiling proof deferred to plan 06.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED pure/store/service suite scaffolds</name>
  <files>mcp_server/tests/test_catalog_manifest.py, mcp_server/tests/test_catalog_evidence_store.py, mcp_server/tests/test_catalog_atomic_writer.py, mcp_server/tests/test_catalog_commit_recovery.py, mcp_server/tests/test_catalog_concurrency.py</files>
  <read_first>
    .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-VALIDATION.md
    .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md
    mcp_server/tests/test_catalog_prepared_artifact.py
    mcp_server/tests/test_catalog_store_unit.py
    mcp_server/tests/test_catalog_prepare_service.py
  </read_first>
  <behavior>
    - test_catalog_manifest.py: empty membership, single member, four-category membership, equal-key sort stability, adjacency equal graph_key ordering, chunk exact default boundary, chunk hard+1 fail, no self-hash field, byte-identical rehash, MANI-03 pure builder never consults batch_id for membership
    - test_catalog_evidence_store.py: create-once same content, divergent content_sha256 raises provenance_link_conflict, missing target fail, type mismatch fail, no Entity label, empty evidence list ok, single link, coalesce byte-identical, excerpt length bound uses MAX_EVIDENCE_LENGTH string length
    - test_catalog_atomic_writer.py: shared writer both paths, fault inject after entities/edges/sources/evidence/manifest/status each zero partial, PLAN-13 order stub
    - test_catalog_commit_recovery.py: terminal triple agrees stable receipt; partial terminal fail-closed; COMMITTING resume full write; never PREPARED revival
    - test_catalog_concurrency.py: same-token one logical; same-batch different tokens converge or deterministic conflict; no duplicates
    - Until product lands: pytest.fail('03B not implemented') or missing-symbol assert; suite must be collectable
  </behavior>
  <action>
    Create five modules under mcp_server/tests/ with collectable pytest functions matching 03B-VALIDATION task IDs. Prefer try/import missing product symbols so collection succeeds and failures are RED. Mirror PATTERNS.md names. No production code. Per D-30, D-31. Cite PLAN-13..16, EVID-07..11, MANI-01..07, TEST-06/07 in test docstrings.
  </action>
  <acceptance_criteria>
    - All five files exist and pytest collects at least one test each
    - Primary named cases RED not collection ERROR
    - No mcp_server/src production files modified
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_evidence_store.py mcp_server/tests/test_catalog_atomic_writer.py mcp_server/tests/test_catalog_commit_recovery.py mcp_server/tests/test_catalog_concurrency.py --collect-only -q</automated>
  </verify>
  <done>Wave 0 pure/store/service/concurrency RED scaffolds collectable with named Phase 3B cases.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: RED live Neo4j + Phase 3B gate runner scaffolds</name>
  <files>mcp_server/tests/test_catalog_commit_neo4j_int.py, mcp_server/tests/catalog_phase3b_gate_runner.py, mcp_server/tests/test_catalog_phase3b_gate_runner.py</files>
  <read_first>
    mcp_server/tests/test_catalog_prepare_neo4j_int.py
    mcp_server/tests/catalog_phase3a_gate_runner.py
    mcp_server/tests/test_catalog_phase3a_gate_runner.py
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json
  </read_first>
  <behavior>
    - Live cases: single-tx co-commit domain+evidence+manifest+batch committed+plan COMMITTED; mid-write fault zero partial; identical replay; Entity search interop; evidence/manifest lack Entity; isolation oracle-catalog-tool-test only; configured-ceiling smoke when env present
    - Skip live when bolt/credentials unavailable with truthful skip reason
    - Gate runner: ready_for_phase_4 true only when unit/store/service/concurrency + live + safety pass; default false
    - test_catalog_phase3b_gate_runner.py asserts ready_for_phase_4 false without live green
  </behavior>
  <action>
    Port Phase 3A gate runner structure into catalog_phase3b_gate_runner.py with Phase 3B check IDs (atomicity, evidence, manifest, recovery, concurrency, search interop, safety). Live int skeleton reuses catalog_neo4j_fixtures; TEST_GROUP = 'oracle-catalog-tool-test'. Never open oracle-catalog-v2. Per D-32, D-33, D-34. No capabilities flip this plan.
  </action>
  <acceptance_criteria>
    - catalog_phase3b_gate_runner.py importable; ready_for_phase_4 defaults false
    - test_catalog_commit_neo4j_int.py collects; skips or RED without implementation
    - test_catalog_phase3b_gate_runner.py proves fail-closed default
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_phase3b_gate_runner.py mcp_server/tests/test_catalog_commit_neo4j_int.py --collect-only -q</automated>
  </verify>
  <done>Live + gate Wave 0 scaffolds exist; gate fail-closed by default.</done>
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
| test harness → Neo4j | Live tests write only oracle-catalog-tool-test |
| gate ledger → Phase 4 unblock | False readiness must not flip from empty scaffolds |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03B-01 | Tampering | atomic co-commit (future) | high | mitigate | Scaffolds assert full rollback; product later |
| T-03B-02 | Elevation | concurrent authority | high | mitigate | Same-token race suite scaffold |
| T-03B-GATE | Spoofing | gate ready_for_phase_4 | high | mitigate | Default false; require live+safety |
| T-03B-SC | Tampering | package installs | high | mitigate | No new packages |
| T-03B-ISO | Elevation | live group | high | mitigate | Hard-code oracle-catalog-tool-test; ban v2 in live tests |
</threat_model>

## Edge probes (plan 01 contribution)

Named scaffolds reserve all 24 probe rows for discharge in plans 02–06; no auto-dismiss.

## Flagged assumptions

- A1 membership byte estimate: unverified until live ceiling proof (plan 06)
- Live Neo4j availability: gate remains false if skip

## Prohibition recall (phase-wide breadcrumb)

Canon security (fixed Cypher, group isolation, token secrecy, bounded logs) → secure-phase / threat_model. Bespoke kept in must_haves.prohibitions per plan.

<verification>
pytest --collect-only on all seven modules succeeds; gate unit shows ready_for_phase_4 false.
</verification>

<success_criteria>
Wave 0 complete: every 03B-VALIDATION missing file exists with named RED cases; no product co-commit implementation yet.
</success_criteria>

<output>
Create `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-01-SUMMARY.md` when done
</output>
