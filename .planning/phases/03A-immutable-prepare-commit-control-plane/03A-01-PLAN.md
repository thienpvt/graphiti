---
phase: 03A-immutable-prepare-commit-control-plane
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - mcp_server/src/models/catalog_prepare.py
  - mcp_server/src/models/catalog_responses.py
  - mcp_server/src/models/catalog_common.py
  - mcp_server/src/config/schema.py
  - mcp_server/tests/test_catalog_prepare_models.py
autonomous: true
requirements:
  - PLAN-01
  - PLAN-08
  - PLAN-10
must_haves:
  truths:
    - "PrepareCatalogBatchRequest accepts full catalog-v2 batch domain body without dry_run, plan_token, or caller hash authority (PLAN-01, D-14)"
    - "Strict extra fields, empty/null shells, and full valid request boundaries fail or pass exactly as CatalogStrictModel contracts (PLAN-01 probe edges)"
    - "CommitPreparedCatalogBatchRequest accepts only plan_token plus optional expected_request_sha256; forbids group/batch/entities/edges/sources/evidence/catalog_sha256/replacement payload/flags (PLAN-10, D-20)"
    - "DiscardPreparedCatalogBatchRequest is token-only with same strict forbid (PLAN-19 model surface, D-11)"
    - "Configured plan_ttl_seconds, max_prepared_payload_bytes, max_active_plans_per_group, prepared_chunk_bytes clamp to research defaults/hard ceilings and cannot exceed hard max (PLAN-08, D-24)"
    - "optional expected_request_sha256 is compare-only replay guard never identity authority (assumption_delta no-change)"
  artifacts:
    - path: mcp_server/src/models/catalog_prepare.py
      provides: PrepareCatalogBatchRequest, CommitPreparedCatalogBatchRequest, DiscardPreparedCatalogBatchRequest
      contains: PrepareCatalogBatchRequest
    - path: mcp_server/src/models/catalog_responses.py
      provides: Prepare/Commit/Discard response models
      contains: PrepareCatalogBatchResponse
    - path: mcp_server/src/models/catalog_common.py
      provides: HARD plan ceilings and plan state constants
      contains: HARD_MAX_PREPARED_PAYLOAD_BYTES
    - path: mcp_server/src/config/schema.py
      provides: CatalogConfig plan limit fields with hard clamps
      contains: plan_ttl_seconds
    - path: mcp_server/tests/test_catalog_prepare_models.py
      provides: strict model and limit clamp suite
      contains: PrepareCatalogBatchRequest
  key_links:
    - from: PrepareCatalogBatchRequest
      to: UpsertCatalogBatchRequest domain body
      via: shared entity/edge/source/evidence fields minus dry_run
    - from: CatalogConfig plan fields
      to: HARD_* ceilings in catalog_common
      via: Field le= hard constants
    - from: CommitPreparedCatalogBatchRequest.expected_request_sha256
      to: compare-only guard
      via: optional 64-hex; never plan identity
  prohibitions:
    - status: unverified
      flagged: true
      statement: no hashes-only prepared artifact contract in models
    - status: unverified
      flagged: true
      statement: no client replacement payload fields on commit/discard
    - status: unverified
      flagged: true
      statement: no dry_run on prepare request
    - status: unverified
      flagged: true
      statement: no store service MCP write path in this plan
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy remote
---

<objective>
Define strict prepare/commit/discard request-response contracts and immutable hard plan ceilings so later store/service plans fail closed at the model/config boundary (D-14, D-20, D-24; PLAN-01, PLAN-08, PLAN-10).

Purpose: Transport and replacement-payload authority die at Pydantic before any Neo4j or embedder touch.
Output: `catalog_prepare.py`, response models, HARD_* + CatalogConfig clamps, green `test_catalog_prepare_models.py`.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-CONTEXT.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-PATTERNS.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-VALIDATION.md
@mcp_server/src/models/catalog_batch.py
@mcp_server/src/models/catalog_common.py
@mcp_server/src/models/catalog_responses.py
@mcp_server/src/config/schema.py
@mcp_server/tests/test_catalog_models.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `PrepareCatalogBatchRequest` | new model | create |
| `CommitPreparedCatalogBatchRequest` | new model | create |
| `DiscardPreparedCatalogBatchRequest` | new model | create |
| `PrepareCatalogBatchResponse` | new model | create |
| `CommitPreparedCatalogBatchResponse` | new model | create |
| `DiscardPreparedCatalogBatchResponse` | new model | create |
| `HARD_PLAN_TTL_SECONDS` / payload / active / chunk ceilings | constants | create/replace zeros |
| `CatalogConfig.plan_ttl_seconds` et al. | config fields | create |
| `test_catalog_prepare_models.py` | unit suite | create |

## Interface contracts (parallel-safe)

- Plan 03A-02 must not edit `catalog_prepare.py`, `catalog_responses.py` prepare receipts, or `CatalogConfig` plan fields.
- Export prepare request without `dry_run` field entirely (not optional false).
- Commit optional `expected_request_sha256: str | None` — 64 lowercase hex when present; omission valid.
- HARD ceilings (research locked): TTL default 3600 hard 86400; payload default 4_194_304 hard 16_777_216; chunk default 131_072 hard 262_144; max chunks hard 128; active default 8 hard 32.
- Plan states enum/constants: PREPARED, COMMITTING, COMMITTED, DISCARDED, EXPIRED (D-10).

## Probe coverage (this plan)

Discharges research probe rows **P01, P08, P10, P19** (model surface) and PLAN-01/08/10 edge predicates for extra fields/empty/null/full request, token field bounds on commit/discard, and limit min/max/exact/+1 integer clamps. Full 34-row map published in plan 06.

## Assumption delta

`expected_request_sha256` optional; primary authority remains immutable prepared plan by token digest. Decision **no-change**. Omission and correct value must later load same frozen plan; mismatch fails before CAS/domain (invariant owned by service plan 05; model only validates shape here).

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Strict prepare/commit/discard models + receipts</name>
  <files>mcp_server/src/models/catalog_prepare.py, mcp_server/src/models/catalog_responses.py, mcp_server/tests/test_catalog_prepare_models.py</files>
  <read_first>
    mcp_server/src/models/catalog_batch.py (UpsertCatalogBatchRequest full domain body, dry_run field)
    mcp_server/src/models/catalog_common.py (CatalogStrictModel, CatalogErrorCode prepared_plan_*)
    mcp_server/src/models/catalog_responses.py (existing response patterns, capabilities shape)
    mcp_server/tests/test_catalog_models.py (strict extra/empty/null patterns)
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md (§6 commit request, §8 errors)
  </read_first>
  <behavior>
    - PrepareCatalogBatchRequest model_validate accepts full valid catalog-v2 batch domain fields (group_id, batch_id, system_key, identity_schema_version, entities, edges, sources, evidence_links, catalog_sha256, etc.) identical to upsert minus dry_run
    - Field dry_run absent: constructing with dry_run kw or extra key fails forbid-extra
    - Unknown nested fields fail recursively
    - Empty/null required collections or null shell fail; single-entity valid shell passes
    - CommitPreparedCatalogBatchRequest requires plan_token (non-empty str, max length bound ~128); optional expected_request_sha256 64-hex or omit
    - Commit rejects group_id, batch_id, entities, edges, sources, evidence_links, catalog_sha256, atomic, dry_run, replacement payload keys
    - DiscardPreparedCatalogBatchRequest token-only; same forbid set
    - PrepareCatalogBatchResponse fields: plan_token, plan_uuid, request_sha256, catalog_sha256, artifact_sha256, identity_schema_version, counts, projected created/updated/unchanged, expires_at — no payload/embeddings
    - CommitPreparedCatalogBatchResponse: plan_uuid, hashes, state, counts only — no membership/payload/embeddings
    - Discard response: plan_uuid, state DISCARDED (or documented idempotent shape)
  </behavior>
  <action>
    RED first: create `mcp_server/tests/test_catalog_prepare_models.py` covering PLAN-01 strict extra/empty/null/full boundaries, PLAN-10 token empty/malformed/max/+1 and all forbidden extra fields, discard token-only. GREEN: add `mcp_server/src/models/catalog_prepare.py` with CatalogStrictModel subclasses; mirror UpsertCatalogBatchRequest domain fields without dry_run (compose or duplicate field set — prefer shared base only if zero behavior change to upsert). Extend `catalog_responses.py` with prepare/commit/discard receipts omitting payload and embeddings. Reuse CatalogErrorCode prepared_plan_* only. No service/store/MCP. Per D-14, D-19, D-20.
  </action>
  <acceptance_criteria>
    - PrepareCatalogBatchRequest has no dry_run field
    - CommitPreparedCatalogBatchRequest field set is exactly plan_token + optional expected_request_sha256
    - pytest test_catalog_prepare_models.py green for model cases
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_models.py -q --tb=line -k "prepare or commit or discard"</automated>
  </verify>
  <done>Strict prepare/commit/discard models and receipts exist; PLAN-01/10 edges green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Plan hard ceilings + CatalogConfig clamps</name>
  <files>mcp_server/src/models/catalog_common.py, mcp_server/src/config/schema.py, mcp_server/tests/test_catalog_prepare_models.py</files>
  <read_first>
    mcp_server/src/models/catalog_common.py (HARD_MAX_ENTITIES_PER_BATCH pattern)
    mcp_server/src/config/schema.py (CatalogConfig max_* Field le=HARD_*)
    mcp_server/src/services/catalog_capabilities.py (HARD_* placeholders currently 0 — do not flip prepare_commit here)
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-PATTERNS.md (Numeric Defaults)
  </read_first>
  <behavior>
    - HARD_PLAN_TTL_SECONDS = 86400; DEFAULT_PLAN_TTL_SECONDS = 3600
    - HARD_MAX_PREPARED_PAYLOAD_BYTES = 16_777_216; default configured 4_194_304
    - HARD_PREPARED_CHUNK_BYTES = 262_144; default 131_072
    - HARD_MAX_CHUNKS_PER_PLAN = 128
    - HARD_MAX_ACTIVE_PLANS_PER_GROUP = 32; default 8
    - CatalogConfig fields plan_ttl_seconds, max_prepared_payload_bytes, max_active_plans_per_group, prepared_chunk_bytes with ge=1 (or documented min) and le=HARD_*
    - Config values above hard max fail validation; exact hard max accepted; hard+1 rejected
    - Plan state string constants exported for store/service reuse
  </behavior>
  <action>
    RED: extend test_catalog_prepare_models.py (or adjacent section) for PLAN-08 min/max/exact/+1 integer precision on each limit field. GREEN: replace zero placeholders in catalog_common with locked research HARD_* and DEFAULT_* constants; add CatalogConfig fields with Field clamps matching entity batch pattern. Do not modify catalog_capabilities feature flags in this plan (plan 05). No Neo4j. Per D-24.
  </action>
  <acceptance_criteria>
    - HARD_MAX_PREPARED_PAYLOAD_BYTES == 16777216
    - CatalogConfig rejects plan_ttl_seconds greater than HARD_PLAN_TTL_SECONDS
    - Limit clamp tests green
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_models.py -q --tb=line -k "ttl or payload or chunk or active or HARD or plan_ttl"</automated>
  </verify>
  <done>Immutable hard ceilings and CatalogConfig clamps land; PLAN-08 model/config edges green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP client → prepare/commit/discard models | Untrusted JSON/tool args |
| Config file/env → CatalogConfig plan limits | Operator misconfig |

## ASVS L1 Control Map

| ASVS ID | Control | Plan application |
|---------|---------|------------------|
| V5.1.3 | Input validation | CatalogStrictModel forbid extra; token-only commit |
| V5.1.4 | Input length limits | plan_token max; payload/TTL hard ceilings |
| V4.1.1 | Least privilege params | Commit cannot carry domain payload |
| V14.2.1 | Dependency integrity | No new packages |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03A-01 | Elevation | plan_token field | high | mitigate | Opaque token shape only here; entropy/digest in plan 02 |
| T-03A-04 | Tampering | commit request | high | mitigate | Token-only model; forbid replacement payload fields |
| T-03A-05 | Denial | unlimited TTL/payload config | medium | mitigate | HARD_* clamps on CatalogConfig |
| T-03A-SC | Tampering | npm/pip installs | high | accept | No new packages this plan |
</threat_model>

## Multi-source coverage (this plan)

| Source | ID | Plan | Status |
|--------|-----|------|--------|
| REQ | PLAN-01 | 01 | COVERED |
| REQ | PLAN-08 | 01 | COVERED (config/constants; capabilities truth in 05) |
| REQ | PLAN-10 | 01 | COVERED |
| CONTEXT | D-14, D-19, D-20, D-24 | 01 | COVERED |
| RESEARCH | defaults/hard ceilings | 01 | COVERED |

<verification>
Focused prepare model tests green; no service/store changes required.
</verification>

<success_criteria>
Strict prepare/commit/discard contracts and hard plan ceilings exist and are unit-proven.
</success_criteria>

<output>
Create `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-01-SUMMARY.md` when done
</output>
