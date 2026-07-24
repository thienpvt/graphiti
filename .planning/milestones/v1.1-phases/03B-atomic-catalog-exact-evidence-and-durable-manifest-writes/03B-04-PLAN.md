---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 04
type: tdd
wave: 4
depends_on:
  - 03B-02
  - 03B-03
files_modified:
  - mcp_server/src/services/catalog_service.py
  - mcp_server/tests/test_catalog_atomic_writer.py
  - mcp_server/tests/test_catalog_service.py
autonomous: true
requirements:
  - PLAN-13
  - PLAN-14
  - MANI-06
  - EVID-07
  - EVID-09
  - EVID-10
must_haves:
  truths:
    - "One _write_catalog_batch_atomic(tx, projection) co-writes entities, edges, sources+Graphiti links, evidence, manifest, terminal batch committed, and optional plan COMMITTED in the same Neo4j transaction (PLAN-13, MANI-06, D-03, D-04, D-26)"
    - "Any exception before clean exit rolls back all success artifacts; no partial domain/evidence/manifest/committed/plan-COMMITTED (PLAN-14, D-05)"
    - "Prepared commit builds projection only from frozen artifact embeddings/membership/hashes; zero embedder/LLM/queue/HTTP between claim and success exit (D-06)"
    - "upsert_catalog_batch non-dry-run calls the same writer and also co-writes evidence+manifest+terminal status; dry_run remains zero-write (D-26)"
    - "Write order: lock plan if prepared, claim/recheck batch, terminal-agree short-circuit, entities, edges, sources+links, evidence, manifest, batch committed, plan COMMITTING→COMMITTED (D-04)"
    - "Optional failed status only after rollback in separate tx; never creates manifest or plan COMMITTED (D-27)"
    - "Fault injection at every store boundary proves zero partial rows (D-30)"
  artifacts:
    - path: mcp_server/src/services/catalog_service.py
      provides: _write_catalog_batch_atomic, projection builder, upsert refactor, commit success path skeleton through writer
      contains: _write_catalog_batch_atomic
    - path: mcp_server/tests/test_catalog_atomic_writer.py
      provides: GREEN shared writer + fault inject suite
      contains: test_fault_inject_after_entities_rolls_back
  key_links:
    - from: commit_prepared_catalog_batch
      to: _write_catalog_batch_atomic
      via: post-claim success tx
    - from: upsert_catalog_batch
      to: _write_catalog_batch_atomic
      via: replace inline write loop
    - from: Neo4jDriver.transaction
      to: full rollback on BaseException
      via: existing driver semantics
  prohibitions:
    - status: unverified
      flagged: true
      statement: no second success transaction for manifest or plan terminal
    - status: unverified
      flagged: true
      statement: no external I/O during prepared commit success path
    - status: unverified
      flagged: true
      statement: no weaken atomicity if single-tx fails — stop and report
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy
    - status: unverified
      flagged: true
      statement: no capabilities.manifests true in this plan
---

<objective>
Extract shared atomic catalog writer and wire both prepared-commit success path and direct upsert non-dry-run into one Neo4j success transaction that co-commits domain+evidence+manifest+terminals (PLAN-13/14, MANI-06, D-03..D-06, D-26, D-27, D-30).

Purpose: Single authority path so Phase 4 verify works for both entry points; atomicity is non-negotiable.
Output: _write_catalog_batch_atomic, upsert refactor, commit path invoking writer after Phase 3A claim, green fault-injection suite.
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
@mcp_server/src/services/catalog_manifest.py
@graphiti_core/driver/neo4j_driver.py
@mcp_server/tests/test_catalog_atomic_writer.py
@mcp_server/tests/test_catalog_service.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `CatalogWriteProjection` (dataclass/dict) | internal | create |
| `_build_projection_from_artifact` | service | create |
| `_build_projection_from_upsert` | service | create |
| `_write_catalog_batch_atomic` | service | create |
| upsert write-body replacement | service | modify |
| commit success tx after claim | service | modify |

## Interface contracts

- Hard stop: if implementation would require multi-tx success, stop and report — do not ship split commits.
- Claim tx remains separate PREPARED→COMMITTING (D-02); do not merge claim into success tx.
- Schema ensure (evidence/manifest) before opening success tx, matching upsert pattern.
- Projection fields minimum per RESEARCH Pattern 1.
- Map errors to existing CatalogErrorCode set; bounded messages.

## Edge probe discharge

| Req | Category | Acceptance |
|-----|----------|------------|
| PLAN-13 | adjacency | Full success vs touch-fail at each step: either all success artifacts or none |
| PLAN-13 | empty | Empty entities with only sources/evidence still co-commits legal empty domain sets per request limits |
| PLAN-13 | ordering | Deterministic write order D-04; equal members do not create duplicate writes |
| PLAN-14 | unclassified | Exception mid-tx → rollback; optional failed status post-rollback only |
| MANI-06 | unclassified | Manifest write inside same tx as domain and plan terminal |
| EVID-09 | unclassified | Explicit Graphiti links only inside writer |

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Shared atomic writer + fault injection GREEN</name>
  <files>mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_atomic_writer.py</files>
  <read_first>
    mcp_server/src/services/catalog_service.py (upsert_catalog_batch write loop ~4790–5011, commit_prepared_catalog_batch claim seam, _record_failed_status)
    mcp_server/src/services/catalog_store.py (new evidence/manifest methods)
    graphiti_core/driver/neo4j_driver.py (transaction commit/rollback)
    .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md (skeleton A/B)
  </read_first>
  <behavior>
    - _write_catalog_batch_atomic executes D-04 order using store methods on provided tx
    - Monkeypatch each boundary (entity, edge, source, evidence, manifest, status, cas_plan) raises → after driver rollback mock, assert no committed success markers
    - terminal_commit_agrees true short-circuits without rewrite
    - plan CAS only when projection.plan present
  </behavior>
  <action>
    RED complete atomic writer tests with FakeTx/FakeStore. GREEN extract writer from upsert body; keep behavior parity for domain writes; append evidence+manifest+terminals. Do not yet complete full recovery matrix (plan 05) beyond agree short-circuit hook. Per D-03, D-04, D-05, D-26, D-30.
  </action>
  <acceptance_criteria>
    - test_catalog_atomic_writer.py green for shared writer + all fault boundaries
    - upsert and commit both reference _write_catalog_batch_atomic (grep)
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_atomic_writer.py -q --tb=line</automated>
  </verify>
  <done>Shared writer exists; fault inject proves rollback intent.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire upsert + prepared commit success path</name>
  <files>mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_service.py, mcp_server/tests/test_catalog_atomic_writer.py</files>
  <read_first>
    mcp_server/src/services/catalog_service.py (prepare membership freeze, commit claim end state)
    mcp_server/tests/test_catalog_service.py
    mcp_server/tests/test_catalog_prepare_service.py
  </read_first>
  <behavior>
    - After Phase 3A claim COMMITTING, open success tx, build projection from artifact only, call writer, return COMMITTED response with additive counts/manifest_sha256/batch_uuid
    - No embedder call on commit path (spy)
    - upsert non-dry-run: preflight+embed then writer; dry_run zero store writes
    - On writer failure: plan stays COMMITTING; optional _record_failed_status after rollback
  </behavior>
  <action>
    Extend commit_prepared_catalog_batch past claim into success writer (D-01, D-02, D-06). Refactor upsert to shared writer (D-26). Preserve legacy tool contracts. Extend service unit tests for dry_run zero-write and commit no-external-call spies. Recovery deep cases remain plan 05 if not already covered.
  </action>
  <acceptance_criteria>
    - Commit success path returns state COMMITTED with manifest_sha256 when writer succeeds (unit)
    - dry_run upsert still zero-write
    - No external client calls on commit (mock asserts)
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_atomic_writer.py mcp_server/tests/test_catalog_service.py -q --tb=line -k "upsert or commit or dry_run or atomic or writer"</automated>
  </verify>
  <done>Both entry points share atomic writer; prepared commit completes success tx in unit scope.</done>
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
| claim tx → success tx | Window requires plan/batch locks inside success tx |
| prepared artifact → domain graph | Frozen only; no live re-embed |
| failure side tx | Must not imply success |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03B-01 | Tampering | partial commit | critical | mitigate | Single success tx; fault inject; driver rollback |
| T-03B-EXT | Tampering | external call mid-commit | high | mitigate | No embedder/LLM/HTTP on prepared commit |
| T-03B-FAIL | Spoofing | failed status as success | high | mitigate | Failed status only post-rollback; no manifest |
| T-03B-CY | Tampering | Cypher | critical | mitigate | Store fixed queries only |
| T-03B-SC | Tampering | deps | high | mitigate | No new packages |
</threat_model>

## Flagged assumptions

- If live Neo4j cannot hold full success tx at ceilings, plan 06 hard-stops — do not pre-split here

<verification>
atomic writer + scoped service tests green.
</verification>

<success_criteria>
Domain+evidence+manifest+terminals share one writer; upsert and commit both call it; fault inject green.
</success_criteria>

<output>
Create `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-04-SUMMARY.md` when done
</output>
