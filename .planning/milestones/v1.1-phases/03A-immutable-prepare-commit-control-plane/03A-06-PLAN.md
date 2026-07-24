---
phase: 03A-immutable-prepare-commit-control-plane
plan: 06
type: execute
wave: 5
depends_on:
  - 03A-01
  - 03A-02
  - 03A-03
  - 03A-04
  - 03A-05
files_modified:
  - mcp_server/tests/test_catalog_prepare_neo4j_int.py
  - mcp_server/tests/catalog_phase3a_gate_runner.py
  - mcp_server/tests/run_phase3a_gate.py
  - mcp_server/tests/test_catalog_phase3a_gate_runner.py
  - mcp_server/src/services/catalog_capabilities.py
  - mcp_server/tests/test_catalog_capabilities.py
  - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json
  - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-PHASE3A-GATE.md
  - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-VALIDATION.md
  - .planning/phases/03A-immutable-prepare-commit-control-plane/03A-EDGE-PROBE-RESOLUTION.json
  - .planning/ROADMAP.md
  - .planning/STATE.md
autonomous: true
requirements:
  - PLAN-03
  - PLAN-05
  - PLAN-07
  - PLAN-08
  - PLAN-09
  - PLAN-11
  - PLAN-17
  - PLAN-18
  - PLAN-19
  - SAFE-11
  - TEST-05
must_haves:
  truths:
    - "Live Neo4j on oracle-catalog-tool-test only proves configured-max immutable chunked artifact survives commit/driver close/fresh session load with byte-identical reassembly (PLAN-05, D-06 hard-stop)"
    - "Live proves control labels never Entity; zero domain/evidence/manifest/CatalogIngestBatch on prepare; digest-only token storage; capacity serialization; expiry/discard/COMMITTING CAS; no terminal revival (PLAN-03/07/09/11/17/18/19)"
    - "Skipped or failed live immutable-artifact proof forces ready_for_phase_3b=false and features.prepare_commit remains false; never weaken contract (ROADMAP stop, D-29, D-31, D-32)"
    - "features.prepare_commit flips true in source+tests only AFTER required live immutable proof succeeds; then focused suites and live proof are re-run on that final HEAD before HEAD-bound ledger; manifests stay false; pagination 0 (D-29, P22)"
    - "Fail-closed Phase 3A gate runner is sole ready_for_phase_3b authority; safety ledger canary_executed=false oracle_catalog_v2_queried=false clear_graph_called=false (TEST-05, D-31, D-32)"
    - "03A-EDGE-PROBE-RESOLUTION.json maps all 34 research probe rows with unique indices 0..33; no silent drop equality gate (TEST-05)"
    - "All 18 requirement IDs PLAN-01..12,17..20,SAFE-11,TEST-05 have automated evidence citations in gate ledger"
  artifacts:
    - path: mcp_server/tests/test_catalog_prepare_neo4j_int.py
      provides: live hard-stop suite
      contains: oracle-catalog-tool-test
    - path: mcp_server/src/services/catalog_capabilities.py
      provides: final features.prepare_commit flip after live proof only
      contains: prepare_commit
    - path: mcp_server/tests/test_catalog_capabilities.py
      provides: post-proof prepare_commit true assertions on final HEAD
      contains: prepare_commit
    - path: mcp_server/tests/catalog_phase3a_gate_runner.py
      provides: ready_for_phase_3b authority
      contains: ready_for_phase_3b
    - path: mcp_server/tests/run_phase3a_gate.py
      provides: CLI entry
      contains: apply
    - path: .planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json
      provides: HEAD-bound ledger after final re-test
      contains: ready_for_phase_3b
    - path: .planning/phases/03A-immutable-prepare-commit-control-plane/03A-EDGE-PROBE-RESOLUTION.json
      provides: 34-row probe resolution
      contains: row_index
  key_links:
    - from: live neo4j proof
      to: features.prepare_commit true
      via: only after immutable proof pass; then re-test
    - from: live neo4j proof
      to: ready_for_phase_3b
      via: require-neo4j gate flag fail-closed
    - from: RESEARCH probe inventory P01..P34
      to: 03A-EDGE-PROBE-RESOLUTION.json
      via: row_index 0..33 equality
    - from: focused unit suites
      to: local_gate_pass
      via: shell=False argv runner
  prohibitions:
    - status: unverified
      flagged: true
      statement: no hashes-only artifact acceptance to pass live gate
    - status: unverified
      flagged: true
      statement: no client replacement payload at commit
    - status: unverified
      flagged: true
      statement: no raw-token storage/logging
    - status: unverified
      flagged: true
      statement: no Entity/search contamination of control records
    - status: unverified
      flagged: true
      statement: no COMMITTING reset to PREPARED
    - status: unverified
      flagged: true
      statement: no Phase 3B domain writes in live suite
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy remote production writes
    - status: unverified
      flagged: true
      statement: no forced ready_for_phase_3b without live proof when require-neo4j set
    - status: unverified
      flagged: true
      statement: no prepare_commit true without successful live immutable proof on final HEAD
---

<objective>
Prove restart-safe immutable prepared artifacts on live Neo4j (`oracle-catalog-tool-test` only), flip capabilities.features.prepare_commit true only after that proof, re-test final HEAD, and bind fail-closed Phase 3A gate ledger with complete 34-row probe resolution so Phase 3B unlocks only on evidence (D-06, D-29, D-31, D-32; TEST-05).

Purpose: Hard-stop authority — Neo4j cannot store immutable payloads means report and stop, not contract weakening; prepare_commit never claims support without live proof.
Output: live int suite, D-29 prepare_commit flip, phase3a gate runner, GATE-RESULTS, PHASE3A-GATE report, EDGE-PROBE-RESOLUTION 34/34, VALIDATION/ROADMAP/STATE updates.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-VALIDATION.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md
@mcp_server/tests/test_catalog_neo4j_int.py
@mcp_server/tests/test_catalog_neo4j_fixtures.py
@mcp_server/tests/catalog_phase2_gate_runner.py
@mcp_server/tests/run_phase2_gate.py
@mcp_server/tests/test_catalog_phase2_gate_runner.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `test_catalog_prepare_neo4j_int.py` | live suite | create |
| `catalog_capabilities.features.prepare_commit` | final true flip | modify after live proof |
| `test_catalog_capabilities.py` | post-proof flag tests | update |
| `catalog_phase3a_gate_runner.py` | gate | create |
| `run_phase3a_gate.py` | entry | create |
| `test_catalog_phase3a_gate_runner.py` | unit | create |
| `03A-GATE-RESULTS.json` | ledger | create |
| `03A-PHASE3A-GATE.md` | report | create |
| `03A-EDGE-PROBE-RESOLUTION.json` | 34-row map | create |
| `03A-VALIDATION.md` | update | modify |
| ROADMAP/STATE | progress | modify |

## D-29 / prepare_commit sequencing (self-consistent)

1. Task 1: run/author live immutable proof (`oracle-catalog-tool-test` only).
2. If live **skip or fail**: leave `features.prepare_commit=false`, set `ready_for_phase_3b=false`, hard-stop report — **do not** flip flag.
3. If live **pass**: set `features.prepare_commit=true` in `catalog_capabilities.py`; update `test_catalog_capabilities.py` to expect true; keep `manifests=false` and pagination 0.
4. Re-run focused prepare/capabilities/service/MCP suites **and** live proof on that final HEAD.
5. Task 2: generate HEAD-bound GATE-RESULTS only after step 4 green; `ready_for_phase_3b=true` only if local+live+safety hold with prepare_commit true on that HEAD.

## Probe coverage (complete 34-row map)

Research Spec-Less Probe Inventory rows P01..P34 map to resolution indices 0..33:

| row_index | Probe | Plan owner | Verification |
|----------:|-------|------------|--------------|
| 0 | P01 PLAN-01 prepare shape | 03A-01 | test_catalog_prepare_models |
| 1 | P02 PLAN-02 preflight reuse | 03A-04 | test_catalog_prepare_service + upsert regression |
| 2 | P03 PLAN-03 zero domain | 03A-04, 03A-06 live | spies + neo4j_int label counts |
| 3 | P04 PLAN-04 full artifact | 03A-02, 03A-04 | artifact + service |
| 4 | P05 PLAN-05 chunk+restart | 03A-02, 03A-03, 03A-06 | pure + store + live |
| 5 | P06 PLAN-06 one-time token | 03A-02, 03A-04 | token + service |
| 6 | P07 PLAN-07 digest compare | 03A-02, 03A-05 service matches, 03A-06 live | token + plan_token_matches + neo4j props |
| 7 | P08 PLAN-08 limits | 03A-01, 03A-05 | models + capabilities |
| 8 | P09 PLAN-09 non-Entity | 03A-03, 03A-06 | store + live labels |
| 9 | P10 PLAN-10 commit token-only | 03A-01, 03A-05 | models + service |
| 10 | P11 PLAN-11 load/errors | 03A-03, 03A-05 | store CAS + service |
| 11 | P12 PLAN-12 no external commit | 03A-05 | service spies |
| 12 | P13 PLAN-17 binding | 03A-02, 03A-05, 03A-06 | pure + service + live |
| 13 | P14 PLAN-18 no revive | 03A-03, 03A-05 | CAS matrix |
| 14 | P15 PLAN-19 discard | 03A-03, 03A-05, 03A-06 | store + service + live |
| 15 | P16 PLAN-20 upsert dry_run | 03A-04 | regression covered |
| 16 | P17 SAFE-11 embed-before-plan | 03A-04 | service spies |
| 17 | P18 TEST-05 matrix | 03A-06 | gate runner |
| 18 | P19 CONT-02 forbid extra | 03A-01 | strict models |
| 19 | P20 SAFE-01 group isolation | 03A-06 | int fixtures |
| 20 | P21 SAFE-02 no canary | 03A-06 | safety ledger |
| 21 | P22 CAPA prepare_commit | 03A-05 false pre-gate; **03A-06 true after live** | capabilities tests |
| 22 | P23 CATALOG_TOOL_NAMES | 03A-05 | MCP tests |
| 23 | P24 no oracle-catalog-v2 | 03A-06 | safety + int group |
| 24 | P25 capacity race | 03A-03, 03A-06 | lock + live |
| 25 | P26 COMMITTING recovery seam | 03A-03, 03A-05 | CAS re-entry |
| 26 | P27 immutability identity conflict | 03A-03, 03A-04 | store + service |
| 27 | P28 chunk reassembly mismatch | 03A-02 | pure unit |
| 28 | P29 expiry access path | 03A-03, 03A-05, 03A-06 | CAS + live |
| 29 | P30 features/limits truthful | 03A-05 | capabilities |
| 30 | P31 logging redaction token | 03A-04 | service assertions |
| 31 | P32 plan schema constraints | 03A-03 | store unit |
| 32 | P33 dry_run no control-plane | 03A-04 | upsert regression |
| 33 | P34 hard stop Neo4j storage | 03A-06 | live + gate require-neo4j |

Equality gate: resolution entries == 34; row_index set == range(34); each cites plan+task+test_or_backstop. Flagged assumptions only if CONTEXT/RESEARCH silent — currently all 34 have planned predicates (0 flagged assumptions expected). If any residual ambiguity remains, list under `flagged_assumptions` array without dropping the row.

## Flagged assumptions (descriptor-less residuals)

None expected after mapping above. If execution discovers missing RESEARCH answer for a row, record:

```json
{"row_index": N, "status": "flagged_assumption", "statement": "...", "default": "fail-closed"}
```

Do not hide under truths.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Live Neo4j immutable artifact + control-plane proofs</name>
  <files>mcp_server/tests/test_catalog_prepare_neo4j_int.py</files>
  <read_first>
    mcp_server/tests/test_catalog_neo4j_int.py
    mcp_server/tests/test_catalog_neo4j_fixtures.py
    mcp_server/src/services/catalog_service.py
    mcp_server/src/services/catalog_store.py
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-VALIDATION.md
  </read_first>
  <behavior>
    - GROUP constant oracle-catalog-tool-test only; assert never oracle-catalog-v2
    - Prepare configured-max (or representative multi-chunk near ceiling) artifact; close driver; new session load; reassemble byte-identical; artifact_sha256 match
    - Control node labels exclude Entity; no CatalogIngestBatch created by prepare
    - token_digest stored; raw token property absent
    - capacity: fill max_active; next prepare fails; discard frees slot
    - discard/expiry/COMMITTING CAS live; terminal no revive
    - commit claim live returns COMMITTING without domain Entity nodes for batch
    - On Neo4j unavailable: pytest.skip with clear reason — gate treats skip as not ready
  </behavior>
  <action>
    Implement integration tests marked integration following existing neo4j fixtures. Cleanup only test group nodes (DETACH DELETE WHERE group_id=test). Never clear_graph tool, never canary, never production groups. If Neo4j rejects or corrupts reassembly: leave test failing — do not reduce payload to hashes-only. Ordinary suite may skip when Neo4j unavailable; **final readiness never waives live proof**. Per D-06, D-32, PLAN-05 hard-stop.
  </action>
  <acceptance_criteria>
    - File exists with -m integration tests and GROUP=oracle-catalog-tool-test
    - Restart/fresh-session reassembly test present
    - No oracle-catalog-v2 string used as write target
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_neo4j_int.py -m integration -q --tb=line</automated>
  </verify>
  <done>Live immutable-artifact suite authored; green when Neo4j up, truthful skip when not (skip blocks readiness).</done>
</task>

<task type="auto">
  <name>Task 2: D-29 prepare_commit flip after live proof + gate + 34/34 resolution</name>
  <files>mcp_server/src/services/catalog_capabilities.py, mcp_server/tests/test_catalog_capabilities.py, mcp_server/tests/catalog_phase3a_gate_runner.py, mcp_server/tests/run_phase3a_gate.py, mcp_server/tests/test_catalog_phase3a_gate_runner.py, .planning/phases/03A-immutable-prepare-commit-control-plane/03A-GATE-RESULTS.json, .planning/phases/03A-immutable-prepare-commit-control-plane/03A-PHASE3A-GATE.md, .planning/phases/03A-immutable-prepare-commit-control-plane/03A-VALIDATION.md, .planning/phases/03A-immutable-prepare-commit-control-plane/03A-EDGE-PROBE-RESOLUTION.json, .planning/ROADMAP.md, .planning/STATE.md</files>
  <read_first>
    mcp_server/tests/catalog_phase2_gate_runner.py
    mcp_server/tests/run_phase2_gate.py
    mcp_server/tests/test_catalog_phase2_gate_runner.py
    mcp_server/src/services/catalog_capabilities.py
    mcp_server/tests/test_catalog_capabilities.py
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-VALIDATION.md
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md (probe inventory)
  </read_first>
  <action>
    Sequence (mandatory, D-29/P22):
    1) Confirm Task 1 live immutable proof outcome. If skip/fail: leave features.prepare_commit=false; write PHASE3A-GATE blocker; ready_for_phase_3b=false; do not claim readiness.
    2) Only if live proof **passed**: set features.prepare_commit=True in catalog_capabilities.py; update test_catalog_capabilities.py to assert true; keep manifests=false and pagination hard 0.
    3) Re-run focused suites (prepare models/artifact/token/store/service/capabilities/MCP/hash) and re-run live neo4j int on that final HEAD. If any fail: revert or leave prepare_commit false and ready_for_phase_3b=false.
    4) Clone Phase 2 gate patterns for Phase 3A: SCHEMA phase3a-gate-results.v1; FORBIDDEN_GROUP oracle-catalog-v2; ALLOWED_TEST_GROUP oracle-catalog-tool-test; FOCUS files include all prepare test modules + capabilities + service + hash + graphiti_mcp_server; shell=False argv. derive_ready_for_phase_3b requires local_gate_pass AND live_neo4j_immutable_proof_pass when --require-neo4j AND prepare_commit true only when those hold; any skip/fail of live proof → ready_for_phase_3b=false and prepare_commit must not be true on ledger HEAD. Safety: canary_executed=false, oracle_catalog_v2_queried=false, clear_graph_called=false, no_domain_write_on_prepare=true, no_external_call_on_commit=true. Unit-test runner fail-closed. Author 03A-EDGE-PROBE-RESOLUTION.json with 34 entries per table above (P22 cites 03A-06 final flip). Update 03A-VALIDATION.md task statuses; set nyquist_compliant/wave_0_complete only with evidence. Write 03A-PHASE3A-GATE.md human report. Update ROADMAP Phase 3A plans list and progress; STATE position. Generate final HEAD-bound GATE-RESULTS only after re-test green. Never force ready true without evidence. Preserve unrelated dirty files. Per D-29, D-31, D-32, TEST-05.
  </action>
  <acceptance_criteria>
    - ready_for_phase_3b derivation fail-closed on missing live proof
    - prepare_commit true in source only if live proof + re-test green on same final HEAD; else false
    - manifests false; pagination 0
    - EDGE-PROBE-RESOLUTION has 34 unique row_index 0..33
    - GATE-RESULTS includes safety ledger fields and prepare_commit state
    - ROADMAP lists 6 Phase 3A plans
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_phase3a_gate_runner.py mcp_server/tests/test_catalog_capabilities.py -q --tb=line</automated>
  </verify>
  <done>Phase 3A gate authority, D-29 prepare_commit sequencing, and 34/34 probe resolution complete; ready_for_phase_3b truthful.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Gate ledger → Phase 3B authorization | False green unlocks domain co-commit |
| Live Neo4j test group → shared DB | Isolation required |

## ASVS L1

| ASVS ID | Control | Application |
|---------|---------|-------------|
| V10.3.2 | Build integrity | HEAD bind on GATE-RESULTS |
| V4.2.1 | Fail closed | ready_for_phase_3b false without proof |
| V5.1.3 | Isolation | test group only |

## STRIDE

| Threat ID | Category | Component | Severity | Disposition | Mitigation |
|-----------|----------|-----------|----------|-------------|------------|
| T-03A-03 | Tampering | live storage | high | mitigate | byte-identical restart proof |
| T-03A-05 | Denial | capacity | medium | mitigate | live capacity test |
| T-03A-07 | Tampering | CAS live | high | mitigate | state matrix on Neo4j |
| T-03A-01 | Elevation | token live | high | mitigate | digest-only property assert |
| T-03A-09 | Info disclosure | gate logs | low | mitigate | ledger IDs only |
| T-03A-SC | Tampering | packages | high | accept | no new packages |
</threat_model>

## Hard-stop rule (non-negotiable)

If live Neo4j cannot store/reassemble bounded immutable artifact: `ready_for_phase_3b=false`, `features.prepare_commit=false`, write blocker in PHASE3A-GATE.md, **do not** accept hashes-only, client replacement payload, provisional domain writes, or readiness waiver.

<verification>
Gate unit tests green; live suite green for readiness (skip allowed only as non-ready); prepare_commit matches proof; resolution 34/34; ready_for_phase_3b matches evidence.
</verification>

<success_criteria>
TEST-05 aggregate map complete; Phase 3B unlock only with live immutable proof + prepare_commit true on re-tested final HEAD + full safety ledger.
</success_criteria>

<output>
Create `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-06-SUMMARY.md` when done
</output>
