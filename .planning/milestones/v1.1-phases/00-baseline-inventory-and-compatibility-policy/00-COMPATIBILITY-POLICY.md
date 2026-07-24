# Phase 0 Compatibility Policy

**Date:** 2026-07-18  
**Authority:** Phase 0 freeze before catalog-v2 contract/identity implementation. Policy only — no product code, no catalog-v2 implementation.

## 1. Scope

This document freezes the public MCP tool surface and the catalog-v1 deprecation boundary before Phase 1 contract/identity changes (D-03, BASE-04 deprecation boundary, SAFE-09 intent).

- Does **not** implement catalog-v2.
- Does **not** change product contracts, identity code, or tool registrations.
- Later phases must cite this path as a constraint; silent reinterpretation of catalog-v1 as catalog-v2 is forbidden.

## 2. Legacy MCP tools (14) — name and public contract freeze

Names and public contracts for the following 14 legacy tools **must be preserved** (SAFE-09 intent). Later work is additive only.

| # | Tool name | Live anchor |
|---|-----------|-------------|
| 1 | `add_memory` | `mcp_server/src/graphiti_mcp_server.py:385` |
| 2 | `search_nodes` | `mcp_server/src/graphiti_mcp_server.py:521` |
| 3 | `search_memory_facts` | `mcp_server/src/graphiti_mcp_server.py:598` |
| 4 | `update_entity` | `mcp_server/src/graphiti_mcp_server.py:678` |
| 5 | `delete_entity_edge` | `mcp_server/src/graphiti_mcp_server.py:795` |
| 6 | `delete_episode` | `mcp_server/src/graphiti_mcp_server.py:821` |
| 7 | `get_entity_edge` | `mcp_server/src/graphiti_mcp_server.py:850` |
| 8 | `get_episodes` | `mcp_server/src/graphiti_mcp_server.py:877` |
| 9 | `summarize_saga` | `mcp_server/src/graphiti_mcp_server.py:947` |
| 10 | `build_communities` | `mcp_server/src/graphiti_mcp_server.py:1000` |
| 11 | `add_triplet` | `mcp_server/src/graphiti_mcp_server.py:1054` |
| 12 | `get_episode_entities` | `mcp_server/src/graphiti_mcp_server.py:1128` |
| 13 | `clear_graph` | `mcp_server/src/graphiti_mcp_server.py:1164` |
| 14 | `get_status` | `mcp_server/src/graphiti_mcp_server.py:1207` |

## 3. Catalog tools (7) — name freeze; payload contracts may break explicitly

The following 7 catalog tool **names remain registered**. Catalog-v2 **request identity**, **provenance**, and **hash** contracts may break catalog-v1 payloads **explicitly**. They must **never** silently reinterpret, normalize, migrate, or rewrite catalog-v1 as catalog-v2 (IDEN-12 intent).

| # | Tool name | Live anchor |
|---|-----------|-------------|
| 1 | `upsert_typed_entities` | `mcp_server/src/graphiti_mcp_server.py:1240` |
| 2 | `resolve_typed_entities` | `mcp_server/src/graphiti_mcp_server.py:1269` |
| 3 | `verify_catalog_batch` | `mcp_server/src/graphiti_mcp_server.py:1294` |
| 4 | `upsert_typed_edges` | `mcp_server/src/graphiti_mcp_server.py:1319` |
| 5 | `upsert_provenance` | `mcp_server/src/graphiti_mcp_server.py:1349` |
| 6 | `get_catalog_ingest_status` | `mcp_server/src/graphiti_mcp_server.py:1378` |
| 7 | `upsert_catalog_batch` | `mcp_server/src/graphiti_mcp_server.py:1407` |

### Explicit non-silent-migration rules

- catalog-v1 graph keys, UUID material, hashes, or payloads are never silently accepted as catalog-v2.
- No automatic normalize / re-key / rewrite path from catalog-v1 identity to catalog-v2.
- Breaking changes must be explicit in request schema / `identity_schema` (or equivalent) and tests — never implicit acceptance of pre-hardening payloads.

## 4. Identity authority (document only)

- Caller-supplied UUIDs are **never** identity authority.
- Server-derived UUIDv5 under immutable deployment configuration `GRAPHITI_CATALOG_UUID_NAMESPACE` is the identity authority.
- Changing `GRAPHITI_CATALOG_UUID_NAMESPACE` changes every deterministic identity — treat as immutable for a deployment.
- Phase 0 does **not** implement or modify identity code (`catalog_identity.py` remains pre-hardening until Phase 1).

## 5. Deprecation disposition — historical artifacts

Hashes and counts only. Full payloads are not embedded.

| Artifact | Digest / identity | Disposition |
|----------|-------------------|-------------|
| ACCEPT_TAB golden server request | SHA-256 `a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a` | Historical evidence; **not** a future golden |
| ACCEPT_TAB artifact | SHA-256 `a89e3427a3b1ceec10f36d361fcdbe9e7e30243db4ff51ca59848dfb33968a33` | Historical |
| 10e / 16r / 1-source commit receipt | dry-run/commit counts from checkpoint + receipts | Historical offline only |
| 38 / 85 plan | planned unique entities/edges from manifest | Historical; builders regenerate later **without** executing against live groups |
| `oracle-catalog-v2` graph state | canary target group | Inventory offline only; **never** query or mutate in v1.1 |

Offline sources (paths only): `catalog/CANARY_V2_SUMMARY.md`, `catalog/catalog.json.graphiti-canary-v2-state.json`, `catalog/canary-v2-requests/manifest.json`, `catalog/canary-v2-requests/accept-tab.*`.

## 6. Phase 1+ golden import ban (IDEN-13 intent)

Phase 1+ tests **must not** import pre-hardening golden constants (ACCEPT_TAB request/artifact SHAs, pre-hardening UUID material, catalog-v1 graph keys) as still-valid hardened catalog-v2 goldens.

- Historical digests remain evidence for regression classification and offline narrative.
- Hardened catalog-v2 goldens must be regenerated under the new identity schema after Phase 1 contracts land.
- Builders may regenerate artifacts without executing the canary or rewriting existing graph data.

## 7. Non-goals (this policy)

- No product contract or identity implementation in Phase 0.
- No silent catalog-v1 → catalog-v2 migration tooling.
- No canary execution; no live Neo4j mutation of historical groups.
