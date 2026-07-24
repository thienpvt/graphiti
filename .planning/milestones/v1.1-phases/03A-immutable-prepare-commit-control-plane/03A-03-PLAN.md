---
phase: 03A-immutable-prepare-commit-control-plane
plan: 03
type: tdd
wave: 2
depends_on:
  - 03A-01
  - 03A-02
files_modified:
  - mcp_server/src/services/catalog_store.py
  - mcp_server/tests/test_catalog_prepare_store.py
autonomous: true
requirements:
  - PLAN-05
  - PLAN-09
  - PLAN-11
  - PLAN-18
  - PLAN-19
must_haves:
  truths:
    - "Fixed labels CatalogPreparedPlan CatalogPreparedPlanChunk CatalogPlanGroupLock only; never Entity Episodic CatalogIngestBatch on prepare create path (PLAN-09, D-04)"
    - "CREATE-once root+ordered chunks; same plan identity with different artifact_sha256 conflicts; no MERGE update of artifact bytes after PREPARED (PLAN-05, D-05)"
    - "Active capacity count+create under group lock in one transaction; active=PREPARED|COMMITTING policy per RESEARCH (PLAN-08 capacity seam, D-25)"
    - "CAS matrix enforces legal transitions only; terminal never revive; COMMITTING never timeout-resets to PREPARED; same-token COMMITTING re-entry allowed (PLAN-18, D-10, D-12)"
    - "Discard CAS PREPARED→DISCARDED idempotent for already DISCARDED; COMMITTING/COMMITTED conflict; no DETACH DELETE of domain (PLAN-19, D-11)"
    - "Load by token_digest; expiry access may CAS PREPARED→EXPIRED (PLAN-11, D-26)"
    - "D-27: terminal records retained; cleanup deferred; correctness independent of deletion; no background queue/unbounded cleanup worker in Phase 3A"
  artifacts:
    - path: mcp_server/src/services/catalog_store.py
      provides: ensure_plan_schema, create_prepared_plan, load_prepared_plan_by_token_digest, cas_plan_state, count_active_plans, group lock helpers
      contains: CatalogPreparedPlan
    - path: mcp_server/tests/test_catalog_prepare_store.py
      provides: store unit matrix for create capacity CAS discard
      contains: cas_plan_state
  key_links:
    - from: create_prepared_plan
      to: CatalogPreparedPlan + CatalogPreparedPlanChunk
      via: single tx CREATE fixed labels/params
    - from: CatalogPlanGroupLock
      to: active count + create
      via: same tx serialization
    - from: cas_plan_state
      to: legal transition table
      via: MATCH state + SET only if expected from-state
  prohibitions:
    - status: unverified
      flagged: true
      statement: no Entity or searchable embedding properties on plan/chunk nodes
    - status: unverified
      flagged: true
      statement: no COMMITTING reset to PREPARED
    - status: unverified
      flagged: true
      statement: no raw token property on any node
    - status: unverified
      flagged: true
      statement: no Phase 3B domain Entity RELATES_TO evidence manifest writes
    - status: unverified
      flagged: true
      statement: no client label/property interpolation into Cypher
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy
---

<objective>
Add group-isolated immutable prepared-plan store methods with capacity lock and legal CAS state machine using fixed server Cypher only (D-01, D-04, D-05, D-10..D-12, D-25; PLAN-05/09/11/18/19).

Purpose: Durable control-plane authority for prepare/commit/discard without domain contamination.
Output: additive `catalog_store.py` methods + green `test_catalog_prepare_store.py` (mocked driver / query capture unit style matching existing store unit tests).
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-PATTERNS.md
@mcp_server/src/services/catalog_store.py
@mcp_server/tests/test_catalog_store_unit.py
@mcp_server/src/models/catalog_common.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `ensure_plan_schema` constraints | store method | create |
| `create_prepared_plan_with_chunks` | store method | create |
| `load_prepared_plan_by_token_digest` | store method | create |
| `load_prepared_plan_chunks` | store method | create |
| `cas_plan_state` | store method | create |
| `count_active_plans_for_group` | store method | create |
| `CatalogPlanGroupLock` MERGE helper | store method | create |
| `test_catalog_prepare_store.py` | unit | create |

## Interface contracts

- Depends on plan 01 constants (states, HARD_*) and plan 02 chunk shape fields only.
- Unique constraints: plan (uuid,group_id); token_digest unique; chunk (uuid,group_id); chunk (plan_uuid,group_id,chunk_index).
- Properties allowlist exactly RESEARCH §10 / PATTERNS fixed lists — no name_embedding/fact_embedding on control nodes.
- Discard never issues DETACH DELETE for Entity/evidence/manifest.
- No service orchestration in this plan.

## Probe coverage (this plan)

Discharges **P05 (store), P09, P11 (store paths), P14, P15, P25, P26, P27, P29, P32**.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Plan schema + immutable create/load + capacity lock</name>
  <files>mcp_server/src/services/catalog_store.py, mcp_server/tests/test_catalog_prepare_store.py</files>
  <read_first>
    mcp_server/src/services/catalog_store.py (ensure_schema, claim_batch_status, fixed Cypher style, CatalogStoreError)
    mcp_server/tests/test_catalog_store_unit.py (query capture / fake tx patterns)
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-PATTERNS.md (labels/props)
  </read_first>
  <behavior>
    - ensure_plan_schema emits CREATE CONSTRAINT IF NOT EXISTS for plan/chunk/token_digest uniqueness — fixed strings only
    - create path uses CREATE not MERGE-update for root and chunks; params include token_digest never raw token
    - capacity: MERGE CatalogPlanGroupLock{group_id}; count active; reject when active >= max; then create
    - load by token_digest returns root metadata + ordered chunks
    - labels in Cypher strings are only CatalogPreparedPlan CatalogPreparedPlanChunk CatalogPlanGroupLock
    - Unicode/byte length of payload_b64 treated as storage of base64 ASCII; total payload_bytes is UTF-8 artifact byte length (PLAN-09 length definition)
  </behavior>
  <action>
    RED: test_catalog_prepare_store.py asserts Cypher label allowlist, CREATE-once, capacity rejection, load order, no Entity label substrings in plan write queries (grep query strings). GREEN: implement additive store methods following claim_batch_status patterns with real tx parameter objects. Never interpolate client strings into labels. Per D-01, D-04, D-05, D-25.
  </action>
  <acceptance_criteria>
    - Store methods exist and unit tests prove fixed labels and capacity gate query structure
    - token_digest param present; raw token key absent from params
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_store.py -q --tb=line -k "create or capacity or load or schema or label"</automated>
  </verify>
  <done>Immutable create/load/capacity store unit green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: CAS state matrix discard expiry COMMITTING re-entry</name>
  <files>mcp_server/src/services/catalog_store.py, mcp_server/tests/test_catalog_prepare_store.py</files>
  <read_first>
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md (§3 state machine table)
    mcp_server/src/services/catalog_store.py (claim_batch_status first-row checks)
  </read_first>
  <behavior>
    - Legal: absent→PREPARED (create), PREPARED→DISCARDED, PREPARED→EXPIRED, PREPARED→COMMITTING, COMMITTING→COMMITTING re-entry, COMMITTING→COMMITTED reserved (method may exist but Phase 3A service must not call for domain)
    - Illegal: any→PREPARED after create, terminal→nonterminal, DISCARDED→COMMITTING, EXPIRED→COMMITTING, COMMITTED→anything
    - Discard already DISCARDED returns success/idempotent row; COMMITTING/COMMITTED → conflict code
    - Expiry CAS only from PREPARED when now>=expires_at
    - Same identity different digest create fails prepared_plan_conflict
  </behavior>
  <action>
    RED: table-driven CAS tests for PLAN-18 terminal matrix and PLAN-19 discard idempotency/conflicts; PLAN-11 missing/expired/consumed/conflict outcomes at store error mapping. GREEN: cas_plan_state with expected_from + to params; map zero-row to structured CatalogStoreError codes aligned with CatalogErrorCode. No COMMITTING→PREPARED path exists (negative test). Per D-10, D-11, D-12, D-26.
  </action>
  <acceptance_criteria>
    - Full legal/illegal CAS matrix unit coverage
    - No query string contains transition to PREPARED from COMMITTING
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_store.py -q --tb=line -k "cas or state or discard or expired or conflict or consum"</automated>
  </verify>
  <done>CAS/discard/expiry store matrix green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Service params → Cypher | Must remain fixed labels/props |
| Concurrent prepares per group | Capacity race |

## ASVS L1

| ASVS ID | Control | Application |
|---------|---------|-------------|
| V5.1.3 | Injection | Fixed labels only |
| V4.2.1 | Access control | group_id on every MATCH/CREATE |
| V10.3.2 | Integrity | CREATE-once + CAS |

## STRIDE

| Threat ID | Category | Component | Severity | Disposition | Mitigation |
|-----------|----------|-----------|----------|-------------|------------|
| T-03A-03 | Tampering | artifact update | high | mitigate | CREATE-once; no byte MERGE |
| T-03A-04 | Tampering | Cypher | high | mitigate | allowlisted labels/props |
| T-03A-05 | Denial | capacity race | high | mitigate | group lock + same-tx count |
| T-03A-07 | Tampering | state revival | high | mitigate | CAS table; no PREPARED reset |
| T-03A-01 | Elevation | token_digest lookup | medium | mitigate | unique digest; no raw token |
| T-03A-SC | Tampering | packages | high | accept | no new packages |
</threat_model>

<verification>
Store unit suite green for create/capacity/CAS/discard.
</verification>

<success_criteria>
Control-plane store methods enforce immutability, labels, capacity, and legal CAS only.
</success_criteria>

<output>
Create `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-03-SUMMARY.md` when done
</output>
