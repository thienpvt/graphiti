---
phase: quick
plan: 260719-udj
subsystem: mcp-catalog-capabilities
tags: [catalog-v2, neo4j, ollama, readiness, redaction]
requires:
  - phase: 05-verification-security-compatibility-and-migration-docs
    provides: hardened Catalog-v2 pre-canary baseline
provides:
  - truthful mutation-free Catalog-v2 runtime readiness
  - exact 14-constraint Neo4j schema inspection
  - non-inference Ollama model readiness
  - source-bound local standalone image
affects: [phase-6-canary, mcp-operations]
tech-stack:
  added: []
  patterns: [raw read-only probes, exact schema-shape inspection, type-only failure logging]
key-files:
  created:
    - .planning/quick/260719-udj-implement-truthful-mutation-free-catalog/260719-udj-VERIFICATION.md
  modified:
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_capabilities.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_capabilities.py
    - mcp_server/README.md
    - mcp_server/docs/CATALOG_V2_MIGRATION.md
key-decisions:
  - Keep `neo4j_indexes` for compatibility; define it as exact readiness of all 14 Catalog-v2 uniqueness constraints.
  - Probe only an already-initialized client; never bootstrap through `get_client`.
  - Bypass Graphiti wrappers that log exception text; use raw Neo4j read-only APIs.
  - Use stdlib HTTP for Ollama tags to avoid third-party raw-URL request logs.
requirements-completed: [CAPA-truthful-readiness]
coverage:
  - id: D1
    description: Truthful mutation-free readiness with exact compatibility and redaction contracts
    requirement: CAPA-truthful-readiness
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_capabilities.py + test_legacy_mcp_contract_compatibility.py; 44 passed
        status: pass
      - kind: other
        ref: Ruff and Pyright focused checks
        status: pass
    human_judgment: false
  - id: D2
    description: Local source-bound standalone Docker image
    requirement: CAPA-truthful-readiness
    verification:
      - kind: other
        ref: graphiti-mcp:local-capabilities-truth image/source SHA-256 comparison
        status: pass
    human_judgment: false
completed: 2026-07-19
status: complete
---

# Catalog-v2 Truthful Readiness Summary

**Evidence-backed Neo4j, schema, and Ollama readiness without bootstrap, inference, schema repair, or domain mutation**

## Accomplishments

- `get_catalog_capabilities` now reports bounded evidence-backed readiness using only an already-initialized client.
- `neo4j_indexes='ready'` requires exact shape matches for all 14 required Catalog-v2 uniqueness constraints.
- Ollama readiness requires `GET /api/tags` success plus configured-model presence; no `/api/embed` call.
- Raw Neo4j and stdlib HTTP probes avoid exception-text and request-URL disclosure.
- Existing capability fields and the exact 28-tool MCP surface remain compatible.
- Local image built and byte-bound to current source.

## Verification

- Tests: `44 passed in 1.15s`.
- Ruff: passed; four files formatted.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Docs: `docs-ok`.
- Forbidden calls: none.
- Image ID: `sha256:134ec8dccdd8e717ca9ddb16e884bf4a470b3be9f2ec2f84bf5e064c6b9a7270`.
- Source SHA-256: `4b8b446abc61cbee4972abda1f1d02788b097e1db922b7ab2de046136527c8bf`.
- Independent verifier: PASS, no gaps.

## Deviations from Plan

### Auto-fixed security issue

Initial verification found raw endpoint disclosure from HTTP request logging and Graphiti Neo4j wrappers that print/log full exception text. Replaced those paths with stdlib Ollama tags retrieval, raw Neo4j connectivity, and a raw read-only schema executor. Added adversarial log/stdout/stderr regression checks. No scope creep.

## Scope Boundary

No commit, push, publish, deployment, runtime restart, canary, graph clear, volume deletion, Kubernetes edit, Compose edit, or existing-data deletion. Prior blocked runs and authorized local configuration changes remain unchanged.

## Next Step

Stop. Canary retry remains separate work requiring a fresh run and its existing authorization gates.
