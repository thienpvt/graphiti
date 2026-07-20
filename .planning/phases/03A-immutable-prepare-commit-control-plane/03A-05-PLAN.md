---
phase: 03A-immutable-prepare-commit-control-plane
plan: 05
type: tdd
wave: 4
depends_on:
  - 03A-03
  - 03A-04
files_modified:
  - mcp_server/src/services/catalog_service.py
  - mcp_server/src/services/catalog_capabilities.py
  - mcp_server/src/graphiti_mcp_server.py
  - mcp_server/tests/test_catalog_prepare_service.py
  - mcp_server/tests/test_catalog_capabilities.py
  - mcp_server/tests/test_graphiti_mcp_server.py
autonomous: true
requirements:
  - PLAN-10
  - PLAN-11
  - PLAN-12
  - PLAN-17
  - PLAN-18
  - PLAN-19
  - PLAN-20
  - PLAN-08
must_haves:
  truths:
    - "commit_prepared_catalog_batch accepts token + optional expected_request_sha256 only; loads/reassembles/verifies frozen artifact; CAS PREPARED→COMMITTING or same-token COMMITTING re-entry; zero domain writes; zero embedder/LLM/queue/HTTP calls (PLAN-10/11/12, D-20..D-23)"
    - "expected_request_sha256 omission and correct value load same frozen plan; mismatch fails before CAS/domain side effects (assumption_delta no-change invariant)"
    - "Token binding enforces group/batch/schema/request/catalog/artifact scope; cross-scope fails (PLAN-17, D-09)"
    - "Missing→not_found; expired→expired; discarded→prepared_plan_not_found; committed→already_consumed; conflict codes for illegal CAS (PLAN-11, D-13)"
    - "Terminal states never revive via commit (PLAN-18)"
    - "discard_prepared_catalog_batch token-only; PREPARED→DISCARDED idempotent; COMMITTING/COMMITTED conflict; no domain deletes (PLAN-19, D-11)"
    - "Three additive MCP tools registered; CATALOG_TOOL_NAMES includes them; 14 legacy + 8 catalog tools unchanged (PLAN-20, D-30)"
    - "Capabilities expose real TTL/payload/active/chunk HARD and configured limits; features.prepare_commit remains false through Wave 4; features.manifests false; pagination hard limits stay 0 (PLAN-08, D-29; final prepare_commit flip owned by 03A-06 after live proof)"
    - "After digest-keyed load, commit and discard authorize only when plan_token_matches(raw_token, loaded_root.token_digest) via hmac.compare_digest; load miss stays prepared_plan_not_found (PLAN-07, D-08)"
    - "D-21: commit loads/reassembles and validates token binding, state, expiry, chunks, artifact/request hash, versions, counts, immutable scope before CAS/domain"
    - "D-22: commit uses only frozen embeddings; zero embedder/LLM/queue/HTTP/provider/network calls"
  artifacts:
    - path: mcp_server/src/services/catalog_service.py
      provides: commit_prepared_catalog_batch, discard_prepared_catalog_batch
      contains: commit_prepared_catalog_batch
    - path: mcp_server/src/services/catalog_capabilities.py
      provides: real HARD plan limits; prepare_commit stays false in Wave 4
      contains: HARD_MAX_PREPARED_PAYLOAD_BYTES
    - path: mcp_server/src/graphiti_mcp_server.py
      provides: prepare_catalog_batch commit_prepared_catalog_batch discard_prepared_catalog_batch tools
      contains: prepare_catalog_batch
    - path: mcp_server/tests/test_catalog_prepare_service.py
      provides: commit/discard/external-call spies + plan_token_matches authorization
      contains: plan_token_matches
    - path: mcp_server/tests/test_catalog_capabilities.py
      provides: truthful limits tests; prepare_commit false pre-gate
      contains: prepare_commit
    - path: mcp_server/tests/test_graphiti_mcp_server.py
      provides: tool registration + safe error names
      contains: discard_prepared_catalog_batch
  key_links:
    - from: plan_token
      to: token_digest load
      via: plan_token_digest as locator only
    - from: loaded_root.token_digest
      to: plan_token_matches(raw_token, token_digest)
      via: hmac.compare_digest authorization after load (PLAN-07)
    - from: reassemble_artifact_bytes
      to: CAS COMMITTING
      via: verify hashes/binding/expiry after token match before CAS
    - from: MCP tools
      to: CatalogService methods
      via: thin wrappers + CatalogSafeFastMCP
  prohibitions:
    - status: unverified
      flagged: true
      statement: no Phase 3B domain co-commit body in commit
    - status: unverified
      flagged: true
      statement: no external calls on commit path
    - status: unverified
      flagged: true
      statement: no client replacement payload on commit
    - status: unverified
      flagged: true
      statement: no COMMITTING→PREPARED recovery
    - status: unverified
      flagged: true
      statement: no raw-token storage/logging
    - status: unverified
      flagged: true
      statement: no features.prepare_commit true in Wave 4
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy
---

<objective>
Implement token-only commit claim/load seam (stop at COMMITTING, no domain writes), discard, real capability limits with prepare_commit still false, and three additive MCP tools with safe errors (D-11, D-13, D-20..D-23, D-29 partial, D-30).

Purpose: Phase 3B can attach domain co-commit to a proven CAS/load boundary; D-29 prepare_commit true only after 03A-06 live proof.
Output: commit/discard service methods, capability limit wiring (flag false), MCP registration, green unit suites.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-CONTEXT.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md
@mcp_server/src/services/catalog_service.py
@mcp_server/src/services/catalog_capabilities.py
@mcp_server/src/graphiti_mcp_server.py
@mcp_server/tests/test_catalog_capabilities.py
@mcp_server/tests/test_graphiti_mcp_server.py
@mcp_server/tests/catalog_phase2_gate_runner.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `commit_prepared_catalog_batch` | service method | create |
| `discard_prepared_catalog_batch` | service method | create |
| capabilities HARD_* real values | constants wire | update |
| `features.prepare_commit` | flag | **false** through Wave 4 (flip in 03A-06 only) |
| MCP tools ×3 | wrappers | create |
| CATALOG_TOOL_NAMES +3 | set | update |

## Interface contracts

- Commit response: plan_uuid, hashes, counts, state=COMMITTING — no membership/payload/embeddings.
- Discarded token → CatalogErrorCode.prepared_plan_not_found (oracle reduction).
- Commit path must not call embedder/llm/queue/http (AsyncMock assert_not_called).
- Phase 3A commit does not write Entity/evidence/manifest/CatalogIngestBatch.
- Pagination hard limits remain 0.
- **D-29 / P22:** `features.prepare_commit` stays **false** for entire plan 05 even after tool registration. Plan 06 flips source+tests only after required live immutable proof succeeds on final HEAD.
- **PLAN-07 authorization:** digest-keyed load is a **locator** only. After a root is loaded, service **must** call `plan_token_matches(raw_token, loaded_root.token_digest)` (stdlib `hmac.compare_digest` inside). False match → `prepared_plan_not_found` (no oracle). Load miss → `prepared_plan_not_found` without compare. Same post-load match required on discard.

## Probe coverage (this plan)

Discharges **P10, P11, P12, P13 (service), P14, P15, P23, P26, P29, P30 (limits; prepare_commit false half)** plus assumption_delta expected_request_sha256 invariant tests and PLAN-07 service compare. **P22 prepare_commit true** owned by 03A-06.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: commit claim/load seam + discard + expected_hash invariant</name>
  <files>mcp_server/src/services/catalog_service.py, mcp_server/tests/test_catalog_prepare_service.py</files>
  <read_first>
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md (§6 commit boundary, open Q discarded mapping)
    mcp_server/src/services/catalog_store.py (load/CAS methods from plan 03)
    mcp_server/src/models/catalog_prepare.py
    mcp_server/tests/test_catalog_prepare_service.py
  </read_first>
  <behavior>
    - Happy: digest locator → load root → plan_token_matches(raw_token, loaded_root.token_digest) true → reassemble → verify → CAS PREPARED→COMMITTING → response state COMMITTING
    - PLAN-07: digest lookup is locator only; authorization is post-load plan_token_matches using hmac.compare_digest; tests spy/assert plan_token_matches called with raw token + stored digest on commit and discard success paths
    - PLAN-07: failed plan_token_matches yields prepared_plan_not_found and no CAS
    - Load miss (no root for digest): prepared_plan_not_found without requiring plan_token_matches success
    - Re-entry COMMITTING same token: success claim response without second plan after successful match
    - expected_request_sha256 omitted: same load path as correct value
    - expected_request_sha256 wrong: fail before CAS (spy cas not called)
    - expired PREPARED: mark EXPIRED + prepared_plan_expired (after successful token match)
    - discarded: prepared_plan_not_found
    - committed: prepared_plan_already_consumed
    - missing/malformed token: not_found or validation error at model (service sees digest miss)
    - binding mismatch (tampered root fields vs artifact): conflict/fail closed
    - discard PREPARED→DISCARDED after plan_token_matches; second discard idempotent; discard COMMITTING/COMMITTED conflict
    - discard never calls domain delete APIs
    - commit never calls embedder/llm/queue/network
  </behavior>
  <action>
    RED: extend test_catalog_prepare_service.py for PLAN-10/11/12/17/18/19 matrix, assumption_delta invariant, and PLAN-07 post-load plan_token_matches authorization (assert helper used; mismatch → prepared_plan_not_found; load miss remains not_found). GREEN: implement commit_prepared_catalog_batch and discard_prepared_catalog_batch. Order: compute digest → load by digest → if missing not_found → if not plan_token_matches(raw_token, root.token_digest) not_found → then expiry/state/reassemble/CAS. Stop before any domain co-commit. Optional committing_started_at observability only. Source must call plan_token_matches (or equivalent hmac.compare_digest on digests) — not plain ==. Per D-08, D-11, D-12, D-13, D-20..D-23, PLAN-07.
  </action>
  <acceptance_criteria>
    - Commit success returns state COMMITTING without domain write spies firing
    - External client mocks assert_not_called on commit
    - expected_request_sha256 mismatch prevents CAS
    - plan_token_matches invoked on successful commit/discard; failed match prevents CAS and returns prepared_plan_not_found
    - Discard idempotent + conflict cases green
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_service.py -q --tb=line -k "commit or discard or expected_request or external or binding or revive or expired or consum or plan_token_matches or compare_digest"</automated>
  </verify>
  <done>Token-only commit/discard service seam green with PLAN-07 post-load timing-safe auth and zero external/domain side effects.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: MCP tools + capability limits with prepare_commit false</name>
  <files>mcp_server/src/graphiti_mcp_server.py, mcp_server/src/services/catalog_capabilities.py, mcp_server/tests/test_catalog_capabilities.py, mcp_server/tests/test_graphiti_mcp_server.py</files>
  <read_first>
    mcp_server/src/graphiti_mcp_server.py (CATALOG_TOOL_NAMES, upsert_catalog_batch wrapper, CatalogSafeFastMCP)
    mcp_server/src/services/catalog_capabilities.py (placeholders HARD_*=0, prepare_commit False)
    mcp_server/tests/test_catalog_capabilities.py
    mcp_server/tests/test_graphiti_mcp_server.py
  </read_first>
  <behavior>
    - Three tools registered: prepare_catalog_batch, commit_prepared_catalog_batch, discard_prepared_catalog_batch
    - Names in CATALOG_TOOL_NAMES for safe error rewriting
    - Existing 14 legacy + prior 8 catalog tool names still present (now 11 catalog names total: 8+3)
    - Capabilities hard/configured limits match catalog_common HARD_* and CatalogConfig defaults (non-zero plan ceilings)
    - features.prepare_commit is **False** after tool registration in this plan (D-29 / P22 deferred to 03A-06)
    - features.manifests False; max_page_size hard 0
    - get_catalog_capabilities still mutation-free
  </behavior>
  <action>
    RED: capabilities tests for non-zero plan limits and explicit prepare_commit **false** pre-gate; MCP tests for three tool registrations and CATALOG_TOOL_NAMES membership; regression that upsert_catalog_batch still registered. GREEN: thin MCP wrappers delegating to CatalogService; replace capability HARD zeros with imports from catalog_common; wire configured values from config; leave features.prepare_commit=False (do not flip true on registration). No canary. Per D-29 (partial — flag flip in 03A-06), D-30, PLAN-08, PLAN-20.
  </action>
  <acceptance_criteria>
    - Three new tool functions exist and are registered
    - HARD_MAX_PREPARED_PAYLOAD_BYTES exposed non-zero in capabilities
    - prepare_commit false; manifests false; pagination 0
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_graphiti_mcp_server.py -q --tb=line -k "prepare or commit or discard or capabilit or tool or CATALOG_TOOL"</automated>
  </verify>
  <done>MCP surface additive; limits truthful; prepare_commit remains false until 03A-06 live-proof gate.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Client token → commit/discard | Bearer of plan_token |
| MCP transport → tools | Untrusted args already model-validated |

## ASVS L1

| ASVS ID | Control | Application |
|---------|---------|-------------|
| V3.3.1 | Logout/session terminate | discard terminal |
| V4.1.2 | Object-level authz | binding fields |
| V5.1.3 | Input validation | token-only models |
| V7.1.2 | No sensitive in logs | safe MCP errors |

## STRIDE

| Threat ID | Category | Component | Severity | Disposition | Mitigation |
|-----------|----------|-----------|----------|-------------|------------|
| T-03A-01 | Elevation | commit token | high | mitigate | digest locator + plan_token_matches + binding+TTL+terminal |
| T-03A-02 | Info disclosure | error oracle | medium | mitigate | discarded→not_found; failed match→not_found |
| T-03A-04 | Tampering | replacement payload | high | mitigate | token-only commit model+service |
| T-03A-07 | Tampering | revival | high | mitigate | CAS terminal immutable |
| T-03A-08 | Tampering | re-embed on commit | high | mitigate | frozen embeddings only; spies |
| T-03A-09 | Info disclosure | MCP response | high | mitigate | hashes/counts/state only |
| T-03A-SC | Tampering | packages | high | accept | no new packages |
</threat_model>

## Assumption delta (required invariant)

Primary authority = immutable prepared plan resolved by token **authorization** (post-load plan_token_matches), not digest lookup alone. optional expected_request_sha256 is compare-only. Tests: omit vs correct identical frozen load; mismatch fails before CAS.

## D-29 sequencing note

Wave 4 ends with tools registered, limits non-zero, **prepare_commit=false**. Wave 5 (03A-06) is the only plan allowed to set prepare_commit true, and only after required live immutable proof on the final re-tested HEAD.

<verification>
Commit/discard service + capabilities (flag false) + MCP registration tests green.
</verification>

<success_criteria>
Token-only commit ends at COMMITTING with zero domain/external I/O; PLAN-07 post-load match enforced; discard safe; three tools additive; limits truthful; prepare_commit still false.
</success_criteria>

<output>
Create `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-05-SUMMARY.md` when done
</output>
