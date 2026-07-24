---
phase: 03A-immutable-prepare-commit-control-plane
plan: 02
type: tdd
wave: 1
depends_on: []
files_modified:
  - mcp_server/src/services/catalog_prepared_artifact.py
  - mcp_server/src/services/catalog_identity.py
  - mcp_server/tests/test_catalog_prepared_artifact.py
  - mcp_server/tests/test_catalog_token.py
autonomous: true
requirements:
  - PLAN-04
  - PLAN-05
  - PLAN-06
  - PLAN-07
  - PLAN-17
must_haves:
  truths:
    - "Canonical prepared-artifact-v1 UTF-8 JSON bytes include membership, embeddings, request_canonical, counts, scope, hashes — never hashes-only (PLAN-04, D-02, D-03)"
    - "artifact_sha256 is external to hashed bytes; reassembly is byte-identical across zero/one/multi chunk and exact chunk boundaries (PLAN-05)"
    - "Chunk order stable by chunk_index; base64 payload_b64; corruption/reorder/truncation fails closed (PLAN-05, D-03)"
    - "mint_plan_token uses secrets; never derived from plan_uuid/batch/hash (PLAN-06, D-07)"
    - "plan_token_digest is domain-separated SHA-256; plan_token_matches uses hmac.compare_digest; raw token never in artifact serialization helpers (PLAN-07, D-08)"
    - "Binding fields for plan_uuid group_id batch_id schema request/catalog/artifact hashes are pure-constructible for root metadata (PLAN-17, D-09)"
  artifacts:
    - path: mcp_server/src/services/catalog_prepared_artifact.py
      provides: serialize_prepared_artifact, chunk_artifact_bytes, reassemble_artifact_bytes, artifact_sha256
      contains: prepared-artifact-v1
    - path: mcp_server/src/services/catalog_identity.py
      provides: catalog_prepared_plan_chunk_uuid, plan_token_digest helpers (or re-export)
      contains: catalog_prepared_plan_chunk_uuid
    - path: mcp_server/tests/test_catalog_prepared_artifact.py
      provides: pure artifact suite
      contains: reassemble
    - path: mcp_server/tests/test_catalog_token.py
      provides: pure token suite
      contains: compare_digest
  key_links:
    - from: serialize_prepared_artifact
      to: artifact_sha256
      via: hash complete canonical bytes without embedded self-hash field
    - from: chunk_artifact_bytes
      to: reassemble_artifact_bytes
      via: ordered b64 decode + total length + digest verify
    - from: mint_plan_token
      to: plan_token_digest
      via: TOKEN_DIGEST_DOMAIN prefix
  prohibitions:
    - status: unverified
      flagged: true
      statement: no hashes-only artifact builders
    - status: unverified
      flagged: true
      statement: no raw-token storage serialization or logging helpers that accept embedding token into artifact
    - status: unverified
      flagged: true
      statement: no Entity/search properties on pure artifact schema
    - status: unverified
      flagged: true
      statement: no Neo4j I/O or MCP registration in this plan
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy
---

<objective>
Implement pure prepared-artifact serialization/chunking/reassembly and opaque token digest helpers with zero I/O so store and service plans consume one byte-identity and one timing-safe token authority (D-01..D-03, D-07..D-09; PLAN-04..07, PLAN-17).

Purpose: Immutability and token security are pure and unit-proven before Neo4j.
Output: `catalog_prepared_artifact.py`, identity/token helpers, green pure tests.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-CONTEXT.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md
@.planning/phases/03A-immutable-prepare-commit-control-plane/03A-PATTERNS.md
@mcp_server/src/services/catalog_identity.py
@mcp_server/tests/test_catalog_identity.py
@mcp_server/tests/test_catalog_hash.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `PREPARED_ARTIFACT_SERIALIZATION_VERSION` | constant `prepared-artifact-v1` | create |
| `serialize_prepared_artifact` | pure fn | create |
| `artifact_sha256` | pure fn | create |
| `chunk_artifact_bytes` | pure fn | create |
| `reassemble_artifact_bytes` | pure fn | create |
| `catalog_prepared_plan_chunk_uuid` | pure fn | create |
| `mint_plan_token` / `plan_token_digest` / `plan_token_matches` | pure fns | create |
| `TOKEN_DIGEST_DOMAIN` | constant | create |
| `test_catalog_prepared_artifact.py` | unit | create |
| `test_catalog_token.py` | unit | create |

## Interface contracts

- Parallel-safe with plan 01 (no shared files).
- Chunk encoding: base64 `payload_b64` per RESEARCH; store metadata chunk_index, byte_offset, byte_length, chunk_sha256.
- Default chunk size constant 131_072; hard 262_144; max chunks 128 — pure functions accept size args and enforce hard max.
- Artifact body excludes `artifact_sha256` field; digest computed over full serialized body then attached only on plan root metadata later.
- Token: `secrets.token_urlsafe(32)`; digest `sha256(b'graphiti.catalog.plan_token.v1|' + token_utf8)`.

## Probe coverage (this plan)

Discharges **P04, P05, P06, P07, P13, P28** and pure edges for PLAN-04/05/06/07/17 (chunk exact-boundary, zero/one/multi, order, corruption, timing-safe digest, binding field construction). Live restart edges remain plan 06.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Prepared artifact serialize/chunk/reassemble</name>
  <files>mcp_server/src/services/catalog_prepared_artifact.py, mcp_server/src/services/catalog_identity.py, mcp_server/tests/test_catalog_prepared_artifact.py</files>
  <read_first>
    mcp_server/src/services/catalog_identity.py (canonical_sha256, catalog_prepared_plan_uuid, CANONICALIZATION_VERSION)
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md (§1 Canonical artifact format)
    mcp_server/tests/test_catalog_hash.py (canonical JSON rules)
  </read_first>
  <behavior>
    - serialize uses sort_keys=True separators (',', ':') ensure_ascii=False encode utf-8
    - version prepared-artifact-v1 present; membership includes entities/edges/sources/evidence_links with embeddings fields as specified
    - artifact_sha256(bytes) stable; does not mutate input
    - chunk at exact boundary produces N chunks; size-1 boundary produces N+1 or documented split; empty bytes → zero or one empty chunk per documented rule (prefer single empty chunk only if payload empty allowed — document; default empty membership still non-empty JSON object)
    - reassemble sorted by chunk_index equals original bytes; wrong order fixed by sort; missing chunk / bad b64 / digest mismatch / length mismatch raises structured ValueError
    - max chunks 128 hard: 129th fails closed
    - catalog_prepared_plan_chunk_uuid deterministic for (ns, group, plan_id, index)
  </behavior>
  <action>
    RED: write test_catalog_prepared_artifact.py covering PLAN-04 full content requirement (fixture membership+embeddings present in serialized JSON), PLAN-05 chunk exact-boundary zero/one/multi, stable order, corruption fail-closed, max chunks. GREEN: implement catalog_prepared_artifact.py pure module; add catalog_prepared_plan_chunk_uuid to catalog_identity.py with domain material `group_id|catalog-v2|PreparedPlanChunk|{plan_id}|{index}`. No I/O. No raw token in artifact object. Per D-01, D-02, D-03.
  </action>
  <acceptance_criteria>
    - Round-trip serialize→chunk→reassemble byte-identical for multi-chunk fixture
    - Corruption cases raise
    - artifact lacks embedded self-hash field
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepared_artifact.py -q --tb=line</automated>
  </verify>
  <done>Pure artifact authority green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Opaque token mint digest timing-safe compare</name>
  <files>mcp_server/src/services/catalog_identity.py, mcp_server/src/services/catalog_prepared_artifact.py, mcp_server/tests/test_catalog_token.py</files>
  <read_first>
    .planning/phases/03A-immutable-prepare-commit-control-plane/03A-RESEARCH.md (§2 Opaque token code)
    mcp_server/src/services/catalog_identity.py (existing domain-separated digests)
  </read_first>
  <behavior>
    - mint_plan_token returns urlsafe string; two calls differ; not equal to plan_uuid or request hash inputs
    - plan_token_digest stable for same token; different domain would differ (domain constant fixed)
    - plan_token_matches true for correct token; false for wrong; uses hmac.compare_digest (assert not plain == on digests in implementation via source inspect or behavior)
    - helpers never write files/logs
  </behavior>
  <action>
    RED: test_catalog_token.py for PLAN-06 entropy non-derivation, PLAN-07 digest-only compare, PLAN-17 binding helper if pure construct for binding dict. GREEN: implement mint/digest/match with stdlib secrets hashlib hmac only. Prefer catalog_identity.py or catalog_prepared_artifact.py — single module ownership documented in module docstring. Per D-07, D-08.
  </action>
  <acceptance_criteria>
    - plan_token_matches(correct) is True and wrong is False
    - mint uses secrets (import present)
    - no raw token appears in serialize_prepared_artifact output for any fixture
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_token.py mcp_server/tests/test_catalog_prepared_artifact.py -q --tb=line</automated>
  </verify>
  <done>Token pure helpers green; digest timing-safe.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Service → pure artifact/token helpers | Trusted callers still must not log raw token |

## ASVS L1

| ASVS ID | Control | Plan application |
|---------|---------|------------------|
| V6.2.1 | Proven crypto | secrets + SHA-256 + hmac.compare_digest |
| V3.2.1 | Session token entropy | token_urlsafe(32) |
| V5.1.3 | Integrity of reassembled payload | chunk digests + artifact_sha256 |

## STRIDE

| Threat ID | Category | Component | Severity | Disposition | Mitigation |
|-----------|----------|-----------|----------|-------------|------------|
| T-03A-01 | Spoofing | token mint | high | mitigate | secrets 256-bit |
| T-03A-02 | Info disclosure | compare | high | mitigate | hmac.compare_digest |
| T-03A-06 | Tampering | chunks | high | mitigate | order+digest+length checks |
| T-03A-03 | Tampering | hashes-only | high | mitigate | full membership+embeddings in serialize contract |
| T-03A-SC | Tampering | packages | high | accept | stdlib only |
</threat_model>

## Probe coverage (owned rows)

P04, P05 (unit), P06, P07, P13 (pure), P28

<verification>
Pure artifact + token pytest green; no Neo4j.
</verification>

<success_criteria>
Byte-identical artifact reassembly and timing-safe token helpers exist.
</success_criteria>

<output>
Create `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-02-SUMMARY.md` when done
</output>
