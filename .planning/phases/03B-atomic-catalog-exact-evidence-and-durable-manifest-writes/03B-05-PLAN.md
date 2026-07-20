---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 05
type: tdd
wave: 5
depends_on:
  - 03B-04
files_modified:
  - mcp_server/src/services/catalog_service.py
  - mcp_server/src/services/catalog_store.py
  - mcp_server/tests/test_catalog_commit_recovery.py
  - mcp_server/tests/test_catalog_concurrency.py
autonomous: true
requirements:
  - PLAN-14
  - PLAN-15
  - PLAN-16
  - MANI-07
  - TEST-06
must_haves:
  truths:
    - "Stranded COMMITTING recovers by resume-or-finish from same frozen artifact; never resets to PREPARED; never mints replacement authority (PLAN-14, D-07, D-11)"
    - "Terminal agreement (plan COMMITTED + batch committed + matching manifest) returns stable receipt without rewrite (PLAN-15, D-09, D-10, D-23)"
    - "Partial or contradictory terminal evidence fails closed with structured conflict; plan remains COMMITTING (D-09, D-11)"
    - "Same-token concurrent commits yield one logical committed batch via Neo4j locks/CAS/uniqueness (PLAN-16, D-08, D-24, TEST-06)"
    - "Different tokens same group/batch/request either converge on same manifest or deterministic conflict; never two logical manifests (D-25)"
    - "Identical replay creates no duplicate domain/evidence/manifest/status/plan rows and preserves manifest order (PLAN-15, MANI-07, D-21, D-23)"
    - "Expired PREPARED cannot revive via commit; COMMITTING ignores TTL for recovery (TEST-06, D-07)"
  artifacts:
    - path: mcp_server/src/services/catalog_service.py
      provides: recovery decision matrix on commit re-entry
      contains: terminal_commit_agrees
    - path: mcp_server/tests/test_catalog_commit_recovery.py
      provides: GREEN recovery suite
      contains: test_terminal_agreement_returns_stable_receipt
    - path: mcp_server/tests/test_catalog_concurrency.py
      provides: GREEN concurrency suite
      contains: test_same_token_concurrent_one_logical_commit
  key_links:
    - from: same-token re-entry
      to: lock_prepared_plan_for_commit
      via: success-tx serialization
    - from: stable receipt
      to: CommitPreparedCatalogBatchResponse
      via: counts/hashes from durable state
  prohibitions:
    - status: unverified
      flagged: true
      statement: no COMMITTING to PREPARED transition
    - status: unverified
      flagged: true
      statement: no process-local-only locks for cross-process authority
    - status: unverified
      flagged: true
      statement: no silent repair of partial terminals
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy
---

<objective>
Complete stranded-COMMITTING recovery, stable replay receipts, and concurrency arbitration so one logical commit exists under races and restarts (PLAN-14/15/16, MANI-07, TEST-06; D-07..D-11, D-23..D-25).

Purpose: Production multi-worker safety and restart correctness before live gate.
Output: recovery matrix in commit path; green recovery + concurrency suites.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md
@mcp_server/src/services/catalog_service.py
@mcp_server/src/services/catalog_store.py
@mcp_server/tests/test_catalog_commit_recovery.py
@mcp_server/tests/test_catalog_concurrency.py
@mcp_server/tests/test_catalog_prepare_service.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| recovery decision table in commit | service logic | complete |
| stable receipt builder | service | create |
| recovery suite | tests | GREEN |
| concurrency suite | tests | GREEN |

## Interface contracts

- Recovery table exactly RESEARCH §C.
- Permanent conflict: rollback success tx; leave COMMITTING; structured error.
- Concurrent tests may use asyncio gather with FakeStore lock semantics or threaded mocks that simulate CAS winners/losers.
- No public Phase 4 read tools.

## Edge probe discharge

| Req | Category | Acceptance |
|-----|----------|------------|
| PLAN-14 | unclassified | Restart from COMMITTING documented path: resume full writer or stable receipt |
| PLAN-15 | unclassified | Replay returns same counts/hashes/state; no dup rows |
| PLAN-16 | unclassified | Concurrent same-token → one logical |
| MANI-01 | (replay) | Manifest membership stable on replay |
| MANI-07 | unclassified | No reorder/rewrite on replay |
| TEST-06 | unclassified | Same-token, no revive expired PREPARED, no dups |
| MANI-02 | concurrency | Unchanged members still present after race winner |

Flagged: different-token same-batch arbitration exact error code name if not already in registry — pick existing batch_conflict/prepared_plan_conflict; document in SUMMARY.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Stranded COMMITTING recovery + stable replay</name>
  <files>mcp_server/src/services/catalog_service.py, mcp_server/src/services/catalog_store.py, mcp_server/tests/test_catalog_commit_recovery.py</files>
  <read_first>
    mcp_server/src/services/catalog_service.py (commit_prepared_catalog_batch)
    mcp_server/src/services/catalog_store.py (terminal_commit_agrees, cas_plan_state, lock)
    .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md (recovery table C)
  </read_first>
  <behavior>
    - terminal triple agrees → return COMMITTED receipt; zero further writes
    - COMMITTING without success artifacts → full idempotent writer
    - partial terminal → fail closed; no PREPARED CAS
    - permanent domain conflict → rollback; state remains COMMITTING
    - identical second commit after success → stable same logical outcomes
  </behavior>
  <action>
    Implement recovery branch at success-tx entry after lock (D-07..D-11, D-23). GREEN test_catalog_commit_recovery.py with FakeStore states. Assert cas_plan_state never called with to_state PREPARED from COMMITTING.
  </action>
  <acceptance_criteria>
    - Recovery suite green
    - Grep: no legal transition COMMITTING→PREPARED in _PLAN_CAS_LEGAL or commit path
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_commit_recovery.py -q --tb=line</automated>
  </verify>
  <done>Recovery + replay unit matrix green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Same-token and same-batch concurrency</name>
  <files>mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_concurrency.py</files>
  <read_first>
    mcp_server/tests/test_catalog_prepare_service.py (CAS race patterns if any)
    mcp_server/src/services/catalog_store.py (_PLAN_CAS_LEGAL, uniqueness)
    .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md (D-24, D-25)
  </read_first>
  <behavior>
    - N concurrent same-token commits → one committed logical batch; others receipt or wait-then-receipt
    - Concurrent different tokens same batch identity → one manifest or deterministic conflict; never two roots
    - Token scope cannot rewrite group/batch on frozen plan
  </behavior>
  <action>
    GREEN concurrency tests using asyncio.gather and store fakes that serialize on plan uuid. Harden service only if races reveal missing lock/agree paths. Per D-08, D-24, D-25, TEST-06.
  </action>
  <acceptance_criteria>
    - test_catalog_concurrency.py green
    - No duplicate manifest roots in fake graph under same-token race
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_concurrency.py mcp_server/tests/test_catalog_commit_recovery.py -q --tb=line</automated>
  </verify>
  <done>Concurrency + recovery unit proofs green.</done>
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
| multi-worker commit | Cross-process races on plan/batch |
| recovery authority | Frozen artifact only |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03B-02 | Elevation | concurrent writers | high | mitigate | Neo4j locks + CAS + uniqueness |
| T-03B-REVIVE | Tampering | PREPARED revival | high | mitigate | Forbid COMMITTING→PREPARED; tests |
| T-03B-DUP | Tampering | duplicate manifests | high | mitigate | Create-once root + races tests |
| T-03B-ISO | Elevation | group isolation | high | mitigate | group_id on recovery reads |
| T-03B-SC | Tampering | deps | high | mitigate | No new packages |
</threat_model>

## Flagged assumptions

- Different-token conflict code reuses existing registry codes (document if new code required — prefer no new codes)

<verification>
recovery + concurrency suites green.
</verification>

<success_criteria>
Restart and race paths produce one logical commit or fail closed without PREPARED revival.
</success_criteria>

<output>
Create `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-05-SUMMARY.md` when done
</output>
