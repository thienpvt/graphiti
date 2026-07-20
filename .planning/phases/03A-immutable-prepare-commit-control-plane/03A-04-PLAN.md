---
phase: 03A-immutable-prepare-commit-control-plane
plan: 04
type: tdd
wave: 3
depends_on:
  - 03A-01
  - 03A-02
  - 03A-03
files_modified:
  - mcp_server/src/services/catalog_service.py
  - mcp_server/tests/test_catalog_prepare_service.py
  - mcp_server/tests/test_catalog_service.py
  - mcp_server/tests/test_catalog_hash.py
autonomous: true
requirements:
  - PLAN-02
  - PLAN-03
  - PLAN-04
  - PLAN-06
  - PLAN-12
  - PLAN-20
  - SAFE-11
must_haves:
  truths:
    - "Shared preflight extracted from upsert_catalog_batch; prepare and upsert use one identity/topology/hash/projection authority (PLAN-02, D-15, D-16)"
    - "Characterization proves upsert_catalog_batch and dry_run zero-write behavior unchanged before/after extract (PLAN-20, D-28)"
    - "Prepare runs full preflight then all embeddings before any plan write transaction; embed failure leaves zero plan/chunk/domain/status writes (PLAN-03, SAFE-11, D-17, D-18)"
    - "Prepare persists complete immutable artifact (membership+embeddings) via store only; zero Entity RELATES_TO Episodic evidence manifest CatalogIngestBatch mutation (PLAN-03, PLAN-04, D-18)"
    - "Prepare receipt returns raw plan_token once plus plan_uuid hashes counts projections expires_at; never payload/embeddings; raw token not in artifact (PLAN-06, D-19)"
    - "Projection totals exact for empty/one/mixed statuses; order-invariant membership canonicalization (PLAN-03 adjacency/empty/order edges)"
    - "Re-prepare same deterministic plan identity conflicts; never reissue token (D-05 research re-prepare rule)"
  artifacts:
    - path: mcp_server/src/services/catalog_service.py
      provides: _prepare_batch_preflight (or equivalent shared), prepare_catalog_batch
      contains: prepare_catalog_batch
    - path: mcp_server/tests/test_catalog_prepare_service.py
      provides: prepare orchestration spies
      contains: prepare_catalog_batch
    - path: mcp_server/tests/test_catalog_service.py
      provides: characterization/regression for upsert after extract
      contains: upsert_catalog_batch
  key_links:
    - from: prepare_catalog_batch
      to: shared preflight
      via: same helpers as upsert_catalog_batch
    - from: embedder.create*
      to: plan write tx
      via: all embeddings complete before open tx
    - from: prepare_catalog_batch
      to: create_prepared_plan_with_chunks
      via: control-plane only tx
  prohibitions:
    - status: unverified
      flagged: true
      statement: no Phase 3B domain writes in prepare
    - status: unverified
      flagged: true
      statement: no hashes-only prepare path
    - status: unverified
      flagged: true
      statement: no raw-token persistence or logging of full token
    - status: unverified
      flagged: true
      statement: no second identity/topology/hash authority fork
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy
---

<objective>
Extract shared batch preflight from upsert_catalog_batch with characterization first, then implement prepare_catalog_batch: full validate/project/embed then control-plane-only persist and one-time token receipt (D-14..D-19, D-28; PLAN-02/03/04/06/20, SAFE-11).

Purpose: Freeze complete validated batches without domain mutation; keep upsert compatibility.
Output: shared preflight + prepare_catalog_batch service method + green service spies/regression.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-CONTEXT.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-PATTERNS.md
@mcp_server/src/services/catalog_service.py
@mcp_server/src/services/catalog_store.py
@mcp_server/src/services/catalog_prepared_artifact.py
@mcp_server/src/models/catalog_prepare.py
@mcp_server/tests/test_catalog_service.py
@mcp_server/tests/test_catalog_hash.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `_prepare_batch_preflight` (name flexible) | shared method | extract |
| `prepare_catalog_batch` | service method | create |
| characterization tests | test updates | create |
| `test_catalog_prepare_service.py` | service suite | create |

## Interface contracts

- Depends on 01 models, 02 artifact/token, 03 store.
- Plan 05 owns commit/discard service + MCP; do not register MCP tools here.
- Prepare never opens domain write queries; spy store execute_write / entity upsert methods.
- plan_id = `{batch_id}|{request_sha256}` → catalog_prepared_plan_uuid.

## Probe coverage (this plan)

Discharges **P02, P03, P04 (service), P06 (service), P16, P17, P27 (service conflict), P31 (no token log), P33**.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Characterize upsert then extract shared preflight</name>
  <files>mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_service.py, mcp_server/tests/test_catalog_hash.py, mcp_server/tests/test_catalog_prepare_service.py</files>
  <read_first>
    mcp_server/src/services/catalog_service.py (upsert_catalog_batch preflight ~3690–4471, embed ~4531–4560, dry_run return)
    mcp_server/tests/test_catalog_service.py (existing spies dry_run zero-write)
    mcp_server/tests/test_catalog_hash.py (hash echo dry_run)
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md (§5 prepare preflight)
  </read_first>
  <behavior>
    - Before extract: existing upsert and dry_run tests still define expected hash echo and zero-write
    - After extract: same tests remain green without behavior change
    - Shared preflight covers identity/version/grammar/limits/duplicates/topology/endpoints/conflicts/source/evidence resolution/projection inputs used by both paths
    - Preflight failure never calls plan create or domain write
  </behavior>
  <action>
    RED/characterize: ensure test_catalog_service.py and test_catalog_hash.py cover upsert dry_run zero-write and request_sha256 echo; add prepare_service characterization hooks if needed that call upsert path. GREEN: extract shared preflight helper used by upsert_catalog_batch without changing outcomes. Do not implement prepare_catalog_batch fully in this task if extract alone is large — but prefer completing extract with upsert wired. Per D-16, D-28, PLAN-20. Mandatory: characterize before structural extract.
  </action>
  <acceptance_criteria>
    - upsert_catalog_batch dry_run tests green after extract
    - Shared helper exists and is called from upsert path
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_hash.py -q --tb=line -k "dry_run or upsert_catalog_batch or request_sha256"</automated>
  </verify>
  <done>Shared preflight extracted; upsert/dry_run regression green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: prepare_catalog_batch embed-before-tx control-only persist + receipt</name>
  <files>mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_prepare_service.py</files>
  <read_first>
    mcp_server/src/services/catalog_service.py (shared preflight, embed loops)
    mcp_server/src/services/catalog_store.py (create_prepared_plan_with_chunks)
    mcp_server/src/services/catalog_prepared_artifact.py
    mcp_server/src/models/catalog_prepare.py
    mcp_server/src/models/catalog_responses.py
  </read_first>
  <behavior>
    - Happy path: preflight → embed all required → build artifact → capacity+create plan/chunks → return receipt with raw token once
    - Embedder raises: zero store create calls; zero domain writes; zero CatalogIngestBatch
    - Concurrent/preflight fail: no partial plan
    - Empty entity/edge lists: projection zeros; still valid if request valid; zero domain writes
    - One/mixed projected statuses: counts match projection helper totals; order of input does not change hashes
    - Payload over max_prepared_payload_bytes fails before write
    - Active plan capacity exceeded fails with batch_limit or prepared_plan_conflict per codes
    - Existing same plan_uuid: prepared_plan_conflict; no second token
    - Receipt omits payload/embeddings; store params omit raw token
    - Logs may include plan_uuid/counts only (no token string)
  </behavior>
  <action>
    RED: test_catalog_prepare_service.py with AsyncMock store/embedder/driver covering PLAN-02 preflight-before-write, PLAN-03 zero domain spies, SAFE-11 embed fail, PLAN-04 full artifact passed to store, PLAN-06 one-time token, PLAN-03 empty/one/mixed projection, same-identity conflict. GREEN: implement prepare_catalog_batch per RESEARCH prepare order. Never call domain entity/edge upsert methods. Per D-15..D-19, D-17, SAFE-11.
  </action>
  <acceptance_criteria>
    - prepare_catalog_batch returns plan_token and plan_uuid on success
    - embed failure tests assert create_prepared_plan not called
    - domain write spies assert zero calls on prepare success
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_service.py -q --tb=line -k "prepare or embedding or zero_write or receipt or conflict or project"</automated>
  </verify>
  <done>prepare_catalog_batch control-plane path green with embed-before-write and zero domain mutation.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Client batch → preflight | Untrusted catalog content |
| Embedder → service | External failure must not partial-write |
| Service → store | Control-plane only |

## ASVS L1

| ASVS ID | Control | Application |
|---------|---------|-------------|
| V5.1.3 | Validate before side effects | full preflight first |
| V10.3.1 | Fail secure on dependency fail | embed fail no writes |
| V7.1.1 | Log no secrets | no raw token logs |

## STRIDE

| Threat ID | Category | Component | Severity | Disposition | Mitigation |
|-----------|----------|-----------|----------|-------------|------------|
| T-03A-03 | Tampering | partial plan | high | mitigate | embed before tx; single plan tx |
| T-03A-08 | Tampering | embed mid-write | high | mitigate | SAFE-11 order |
| T-03A-09 | Info disclosure | receipt/logs | high | mitigate | token once; no payload in receipt |
| T-03A-05 | Denial | payload size | medium | mitigate | enforce ceilings before write |
| T-03A-SC | Tampering | packages | high | accept | no new packages |
</threat_model>

## Assumption delta note

expected_request_sha256 not used on prepare path.

<verification>
Prepare service suite + upsert dry_run regression green.
</verification>

<success_criteria>
Prepare freezes full artifact with one-time token and zero domain writes; upsert remains compatible.
</success_criteria>

<output>
Create `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-04-SUMMARY.md` when done
</output>
