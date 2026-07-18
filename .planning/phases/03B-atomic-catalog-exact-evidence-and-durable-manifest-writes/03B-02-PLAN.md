---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 02
type: tdd
wave: 2
depends_on:
  - 03B-01
files_modified:
  - mcp_server/src/services/catalog_manifest.py
  - mcp_server/src/services/catalog_identity.py
  - mcp_server/src/models/catalog_common.py
  - mcp_server/src/models/catalog_responses.py
  - mcp_server/tests/test_catalog_manifest.py
autonomous: true
requirements:
  - MANI-01
  - MANI-02
  - MANI-03
  - MANI-04
  - MANI-07
must_haves:
  truths:
    - "Pure catalog-manifest-v1 body includes exact entity/edge/source/evidence compact identities and counts from frozen membership including unchanged projected_status (MANI-01, MANI-02, D-18, D-20)"
    - "Manifest builder never reads entity.batch_id or edge.batch_id as membership authority (MANI-03, D-19)"
    - "Canonical JSON sort_keys separators ensure_ascii=False UTF-8; lists sorted by graph_key/edge_key/source_key/link_key; equal keys stable by uuid; empty lists legal; single-element legal (MANI-07, D-21)"
    - "manifest_sha256 is sha256 of body bytes without self-hash field; chunk_artifact_bytes reuses Phase 3A defaults 128KiB hard 256KiB max 128 chunks (MANI-04, D-17, D-29)"
    - "catalog_manifest_chunk_uuid material group_id|catalog-v2|ManifestChunk|batch_id|index (D-17 discretion)"
    - "CommitPreparedCatalogBatchResponse gains additive batch_uuid, manifest_sha256, created/updated/unchanged aggregates without token/payload/membership/embeddings (D-28)"
  artifacts:
    - path: mcp_server/src/services/catalog_manifest.py
      provides: build_manifest_body_from_membership, serialize_manifest_body, manifest_sha256, chunk_manifest_body
      contains: catalog-manifest-v1
    - path: mcp_server/src/services/catalog_identity.py
      provides: catalog_manifest_chunk_uuid
      contains: ManifestChunk
    - path: mcp_server/src/models/catalog_responses.py
      provides: additive CommitPreparedCatalogBatchResponse fields
      contains: manifest_sha256
    - path: mcp_server/tests/test_catalog_manifest.py
      provides: GREEN pure suite
      contains: test_manifest_canonical_bytes_stable
  key_links:
    - from: build_manifest_body_from_membership
      to: frozen membership projection
      via: pure function no Neo4j
    - from: chunk_manifest_body
      to: chunk_artifact_bytes
      via: reuse prepared artifact helper
    - from: catalog_manifest_uuid
      to: root identity
      via: existing helper
  prohibitions:
    - status: unverified
      flagged: true
      statement: no unbounded single-property membership JSON without chunking
    - status: unverified
      flagged: true
      statement: no embeddings inside manifest body
    - status: unverified
      flagged: true
      statement: no membership inferred from live graph queries or batch_id properties
    - status: unverified
      flagged: true
      statement: no store Neo4j writes in this plan
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy
---

<objective>
Implement pure durable-manifest canonicalization, chunk identity helper, and additive commit response fields so membership authority is byte-deterministic before any Neo4j write (MANI-01/02/03/04/07; D-17..D-21, D-28, D-29).

Purpose: Manifest bytes and digests are the Phase 4 membership authority; pure layer must freeze first.
Output: catalog_manifest.py, catalog_manifest_chunk_uuid, response field extensions, green test_catalog_manifest.py.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-PATTERNS.md
@mcp_server/src/services/catalog_prepared_artifact.py
@mcp_server/src/services/catalog_identity.py
@mcp_server/src/models/catalog_responses.py
@mcp_server/src/models/catalog_common.py
@mcp_server/tests/test_catalog_manifest.py
@mcp_server/tests/test_catalog_prepared_artifact.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `build_manifest_body_from_membership` | pure fn | create |
| `serialize_manifest_body` | pure fn | create |
| `manifest_sha256` / consistency hash | pure fn | create |
| `chunk_manifest_body` | pure fn | create |
| `catalog_manifest_chunk_uuid` | identity fn | create |
| `CommitPreparedCatalogBatchResponse` additive fields | model | modify |
| HARD/DEFAULT manifest ceilings if missing | constants | optional |

## Interface contracts

- Body version string exactly `catalog-manifest-v1`.
- Direct-upsert path may pass artifact_sha256=null (research A3).
- No Neo4j; no catalog_store edits.
- Reuse chunk_artifact_bytes / reassemble_artifact_bytes; do not fork framing.

## Edge probe discharge (this plan)

| Req | Category | Acceptance |
|-----|----------|------------|
| MANI-01 | adjacency | Two members with equal sort keys remain separate rows; order by key then uuid; no merge of distinct UUIDs |
| MANI-01 | empty | Empty category lists yield counts 0 and legal body/hash; null membership input rejected |
| MANI-01 | ordering | Equal compare keys: stable secondary sort by uuid; byte-identical across runs |
| MANI-04 | adjacency | Chunk boundary exact default size: last chunk may be short; exact hard size ok; hard+1 rejected pre-hash store |
| MANI-04 | empty | Zero-byte body after empty membership still hashes; chunk count 0 or single empty per helper contract documented |
| MANI-04 | ordering | Chunk indices 0..n-1 contiguous deterministic |

Flagged: encoding of string length for any future excerpt fields uses Python str len / existing MAX bounds — not grapheme clusters (assumption flagged).

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Pure manifest body hash chunks + chunk UUID</name>
  <files>mcp_server/src/services/catalog_manifest.py, mcp_server/src/services/catalog_identity.py, mcp_server/src/models/catalog_common.py, mcp_server/tests/test_catalog_manifest.py</files>
  <read_first>
    mcp_server/src/services/catalog_prepared_artifact.py
    mcp_server/src/services/catalog_identity.py (catalog_manifest_uuid, evidence helpers)
    .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md (Pattern 4 JSON shape)
    mcp_server/tests/test_catalog_manifest.py
  </read_first>
  <behavior>
    - build_manifest_body_from_membership accepts compact membership lists with projected_status including unchanged
    - serialize uses sort_keys=True separators=(',', ':') ensure_ascii=False encode utf-8
    - Reject bodies that include manifest_sha256 self field or non-finite floats
    - Sort entities by graph_key then uuid; edges by edge_key; sources by source_key; evidence by link_key
    - manifest_sha256 hex lowercase 64
    - chunk uses DEFAULT 131072 HARD 262144 MAX 128; total membership hard align prepared 16MiB fail closed
    - catalog_manifest_chunk_uuid UUIDv5 material group_id|catalog-v2|ManifestChunk|{batch_id}|{index}
    - Empty input: all lists empty → valid; null lists invalid
  </behavior>
  <action>
    RED: flesh Wave 0 tests to assert concrete digests for fixture membership (golden small fixture). GREEN: add catalog_manifest.py pure module; add catalog_manifest_chunk_uuid to catalog_identity.py; optional HARD_MANIFEST_* constants in catalog_common if not reusing plan chunk constants. Do not write Neo4j. Per D-17, D-18, D-19, D-20, D-21, D-29.
  </action>
  <acceptance_criteria>
    - test_catalog_manifest.py green for canonicalize/chunk/order/empty/bounds
    - Body never embeds self-hash field
    - chunk helper reuses prepared artifact framing
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py -q --tb=line</automated>
  </verify>
  <done>Pure manifest + chunk UUID green; MANI pure edges discharged.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Additive commit response committed fields</name>
  <files>mcp_server/src/models/catalog_responses.py, mcp_server/tests/test_catalog_manifest.py</files>
  <read_first>
    mcp_server/src/models/catalog_responses.py (CommitPreparedCatalogBatchResponse)
    mcp_server/tests/test_catalog_prepare_models.py (response forbid patterns)
  </read_first>
  <behavior>
    - Add optional/defaulted batch_uuid: str | None = None
    - Add manifest_sha256: str | None = None
    - Add projected or committed created/updated/unchanged ints default 0 (names: created_count, updated_count, unchanged_count or match existing prepare projected_* style — prefer committed_created/updated/unchanged if no collision)
    - Still forbid membership arrays, plan_token, embeddings, payload fields
  </behavior>
  <action>
    Extend CommitPreparedCatalogBatchResponse additively only (D-28). Add model tests in test_catalog_manifest.py or extend prepare models suite lightly without breaking Phase 3A tests. No MCP wiring required beyond model.
  </action>
  <acceptance_criteria>
    - Existing prepare/commit model tests still pass
    - New fields default-safe for old constructors
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest.py mcp_server/tests/test_catalog_prepare_models.py -q --tb=line</automated>
  </verify>
  <done>Commit response additive fields ready for service plan.</done>
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
| membership input → canonical bytes | Untrusted catalog content becomes authority hash |
| response model → MCP client | Must not leak token/payload/embeddings |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03B-04 | Tampering | manifest body | high | mitigate | Canonical sort + content hash; create-once later |
| T-03B-INFO | Information disclosure | CommitPreparedCatalogBatchResponse | medium | mitigate | No token/payload/membership/embeddings fields |
| T-03B-SC | Tampering | deps | high | mitigate | No new packages |
| T-03B-BOUND | Denial of service | chunk ceilings | medium | mitigate | Hard max chunks/bytes fail closed pre-tx |
</threat_model>

## Flagged assumptions

- A3 artifact_sha256 null on direct upsert manifests: explicit in body schema
- String length for any bounded text uses Python len (code points for BMP-centric data); not grapheme clusters — flagged

<verification>
test_catalog_manifest.py green; prepare models regression green.
</verification>

<success_criteria>
Pure manifest authority + chunk UUID + additive commit fields land without Neo4j writes.
</success_criteria>

<output>
Create `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-02-SUMMARY.md` when done
</output>
