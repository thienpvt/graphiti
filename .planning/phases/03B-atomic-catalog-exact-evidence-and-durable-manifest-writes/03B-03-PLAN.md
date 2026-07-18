---
phase: 03B-atomic-catalog-exact-evidence-and-durable-manifest-writes
plan: 03
type: tdd
wave: 3
depends_on:
  - 03B-01
  - 03B-02
files_modified:
  - mcp_server/src/services/catalog_store.py
  - mcp_server/tests/test_catalog_evidence_store.py
autonomous: true
requirements:
  - EVID-07
  - EVID-08
  - EVID-09
  - EVID-10
  - EVID-11
  - MANI-01
  - MANI-04
  - MANI-06
  - MANI-07
  - TEST-07
must_haves:
  truths:
    - "CatalogEvidenceLink nodes use fixed non-Entity label and allowlisted properties only; no name_embedding; never Entity/Episodic (EVID-10, EVID-11, D-12, D-15)"
    - "Evidence create-once: same uuid/link_key + same content_sha256 idempotent; divergent content returns provenance_link_conflict (EVID-08, D-14)"
    - "Target resolve under group_id; missing/type/endpoint mismatch fails atomically via raise inside caller tx (EVID-07, D-13)"
    - "Byte-identical links coalesce before write using coalesce_byte_identical_evidence_links; one logical record (EVID-08, D-14)"
    - "Graphiti Episodic + MENTIONS + edge episodes remain via existing store methods for explicit links only; no Cartesian (EVID-09, D-16)"
    - "CatalogBatchManifest + CatalogBatchManifestChunk create-once with deterministic root uuid and ordered chunks; divergent manifest_sha256 conflicts (MANI-04, MANI-07, D-17, D-21)"
    - "Schema ensure adds UNIQUE (uuid,group_id) and (group_id,link_key) for evidence and manifest root/chunk uniqueness outside success-tx pattern (D-29)"
    - "terminal_commit_agrees reads plan COMMITTED + batch committed + manifest binding hashes group-scoped (D-09)"
    - "lock_prepared_plan property-touch under group_id for recovery serialization (D-08)"
  artifacts:
    - path: mcp_server/src/services/catalog_store.py
      provides: evidence/manifest writers, constraints, terminal agree, plan lock
      contains: CatalogEvidenceLink
    - path: mcp_server/tests/test_catalog_evidence_store.py
      provides: GREEN store unit suite
      contains: test_evidence_create_once_conflict
  key_links:
    - from: write_evidence_links
      to: lock_provenance_targets pattern
      via: group-scoped fixed Cypher
    - from: write_manifest_root_and_chunks
      to: create_prepared_plan_with_chunks analog
      via: create-once + chunk rows
    - from: terminal_commit_agrees
      to: recovery short-circuit
      via: single read helper
  prohibitions:
    - status: unverified
      flagged: true
      statement: no Entity label on evidence or manifest nodes
    - status: unverified
      flagged: true
      statement: no client-interpolated labels or property names in Cypher
    - status: unverified
      flagged: true
      statement: no Cartesian source-by-target link fabrication
    - status: unverified
      flagged: true
      statement: no public get_catalog_evidence or get_catalog_batch_manifest tools
    - status: unverified
      flagged: true
      statement: no canary oracle-catalog-v2 clear_graph deploy
---

<objective>
Add CatalogNeo4jStore persistence for exact evidence control records, durable manifest root/chunks, plan write-lock, and terminal-agreement read using fixed-label Cypher only (EVID-07..11, MANI-01/04/06/07, TEST-07; D-08, D-09, D-12..D-17, D-21).

Purpose: Store primitives required by the shared atomic writer without implementing service orchestration yet.
Output: store methods + constraints + green test_catalog_evidence_store.py (manifest store cases included or colocated).
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-RESEARCH.md
@.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-PATTERNS.md
@mcp_server/src/services/catalog_store.py
@mcp_server/src/services/catalog_manifest.py
@mcp_server/src/services/catalog_identity.py
@mcp_server/tests/test_catalog_store_unit.py
@mcp_server/tests/test_catalog_evidence_store.py
@mcp_server/tests/test_catalog_prepare_store.py
</context>

## Artifacts this phase produces

| Symbol / file | Kind | Status |
|---------------|------|--------|
| `ensure_evidence_manifest_schema` (or extend ensure) | store schema | create/modify |
| `write_evidence_link` / bulk | store write | create |
| `write_manifest_root_and_chunks` | store write | create |
| `lock_prepared_plan_for_commit` | store lock | create |
| `terminal_commit_agrees` | store read | create |
| `read_manifest_root_for_recovery` | internal read | create |
| evidence/manifest constraints | DDL | create |

## Interface contracts

- Labels exactly: CatalogEvidenceLink, CatalogBatchManifest, CatalogBatchManifestChunk.
- Property allowlists per RESEARCH Pattern 3/4; parameterized only.
- All MATCH/MERGE include group_id.
- Manifest create-once: existing root with different manifest_sha256 → raise mapped conflict (batch_conflict or dedicated code already in CatalogErrorCode if present; else reuse batch_conflict / prepared_plan_conflict consistently).
- Evidence conflict code: provenance_link_conflict.
- No service shared writer yet (plan 04). Do not flip capabilities.

## Edge probe discharge

| Req | Category | Acceptance |
|-----|----------|------------|
| EVID-07 | unclassified | Missing target, wrong type, wrong group → raise; no partial evidence row after rollback by caller |
| EVID-08 | unclassified | Coalesce then write one; divergent identity → provenance_link_conflict |
| EVID-09 | unclassified | MENTIONS/episodes only when explicit entity/edge evidence; zero fabricated pairs |
| EVID-10 | unclassified | Control record retains allowlisted per-link fields |
| EVID-11 | empty | Empty evidence list: no evidence nodes; no Entity |
| EVID-11 | encoding | excerpt/locator bounds use existing MAX_EVIDENCE_LENGTH string length; oversize rejected |
| TEST-07 | unclassified | Multi-source only to declared targets; conflict fail-closed |
| MANI-06 | unclassified | Store APIs designed for same-tx call with domain writers (document; service proves) |

Flagged: Neo4j STRING hard max vendor-undefined — application ceilings only (research).

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Evidence schema constraints create-once and target checks</name>
  <files>mcp_server/src/services/catalog_store.py, mcp_server/tests/test_catalog_evidence_store.py</files>
  <read_first>
    mcp_server/src/services/catalog_store.py (create source, lock_provenance_targets, constraints, plan chunks)
    mcp_server/src/services/catalog_identity.py (evidence_link_key, catalog_evidence_link_uuid, coalesce)
    mcp_server/tests/test_catalog_store_unit.py
    mcp_server/tests/test_catalog_evidence.py
  </read_first>
  <behavior>
    - ensure schema creates uniqueness for evidence uuid+group and group+link_key
    - write_evidence_link MERGE/CREATE-once; same content_sha256 no-op success; different → provenance_link_conflict
    - verify target exists in group with expected kind before write; missing → structured raise
    - returned labels never include Entity
    - coalesce applied at service later; store still idempotent on uuid
  </behavior>
  <action>
    RED expand test_catalog_evidence_store.py with fake/mock executor or existing store unit harness. GREEN implement fixed Cypher methods on CatalogNeo4jStore. Reuse lock_provenance_targets for target property-touch where applicable. Per D-12, D-13, D-14, D-15, D-16. No service commit path.
  </action>
  <acceptance_criteria>
    - Evidence create-once/conflict/target/label tests green
    - Cypher strings contain only fixed labels CatalogEvidenceLink and bound parameters for property values
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_evidence_store.py -q --tb=line -k "evidence or coalesce or conflict or label or target"</automated>
  </verify>
  <done>Evidence store persistence green for EVID-07..11/TEST-07 unit scope.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Manifest root/chunks terminal agree plan lock</name>
  <files>mcp_server/src/services/catalog_store.py, mcp_server/tests/test_catalog_evidence_store.py</files>
  <read_first>
    mcp_server/src/services/catalog_store.py (create_prepared_plan_with_chunks, cas_plan_state, claim_batch_status)
    mcp_server/src/services/catalog_manifest.py
    mcp_server/src/services/catalog_identity.py (catalog_manifest_uuid, catalog_manifest_chunk_uuid)
  </read_first>
  <behavior>
    - write_manifest_root_and_chunks create-once root+ordered chunks; divergent hash conflict
    - root stores group_id batch_id versions hashes counts manifest_sha256 payload_bytes chunk_count
    - lock_prepared_plan_for_commit SET uuid=uuid RETURN state under group_id
    - terminal_commit_agrees true only when plan COMMITTED AND batch committed AND manifest root matches projection hashes/schema
    - partial (batch committed without plan COMMITTED or hash mismatch) → false/fail-closed signal for service
  </behavior>
  <action>
    Implement manifest writers mirroring plan chunk pattern with labels CatalogBatchManifest / CatalogBatchManifestChunk. Add recovery helpers only (no public MCP). Extend unit tests for create-once, chunk order, terminal agree true/false matrix. Per D-08, D-09, D-17, D-20, D-21, MANI-06 readiness.
  </action>
  <acceptance_criteria>
    - Manifest store unit tests green
    - terminal_commit_agrees matrix covers agree / partial / missing
    - No Entity on manifest labels
  </acceptance_criteria>
  <verify>
    <automated>uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_evidence_store.py -q --tb=line</automated>
  </verify>
  <done>Manifest store + recovery reads + plan lock ready for shared writer.</done>
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
| MCP/service params → Cypher | Labels/props server-fixed; values bound |
| group_id partition | Cross-group evidence/manifest forbidden |
| control records → search indexes | Must not enter Entity fulltext/vector |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03B-03 | Tampering | evidence write | high | mitigate | Create-once + content hash; fixed label |
| T-03B-05 | Elevation | Entity pollution | high | mitigate | Never set Entity; no embeddings on control |
| T-03B-CY | Tampering | Cypher injection | critical | mitigate | Fixed labels/property names only |
| T-03B-ISO | Elevation | group isolation | high | mitigate | group_id on every MATCH/MERGE |
| T-03B-04 | Tampering | manifest rewrite | high | mitigate | Create-once + digest compare |
| T-03B-SC | Tampering | deps | high | mitigate | No new packages |
</threat_model>

## Flagged assumptions

- A2 schema ensure remains outside success tx (same as existing ensure_schema)
- A5 property-touch lock sufficient under Neo4j 5.26 community

<verification>
test_catalog_evidence_store.py fully green.
</verification>

<success_criteria>
Store can persist evidence+manifest and answer terminal agreement under group isolation without service orchestration.
</success_criteria>

<output>
Create `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-03-SUMMARY.md` when done
</output>
