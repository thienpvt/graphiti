# API Coverage — Graphiti MCP tools (Phase 2)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

Full registered MCP tool surface from `mcp_server/src/graphiti_mcp_server.py`
(`@mcp.tool()`). **Legacy 14** preserve existing contracts and behavior
unchanged. **Catalog 8** are additive registrations; they do not replace or
narrow any legacy tool. No OPT-OUT for any registered tool.

| capability | decision | reason |
|---|---|---|
| add_memory | INTEGRATE | |
| search_nodes | INTEGRATE | |
| search_memory_facts | INTEGRATE | |
| update_entity | INTEGRATE | |
| delete_entity_edge | INTEGRATE | |
| delete_episode | INTEGRATE | |
| get_entity_edge | INTEGRATE | |
| get_episodes | INTEGRATE | |
| summarize_saga | INTEGRATE | |
| build_communities | INTEGRATE | |
| add_triplet | INTEGRATE | |
| get_episode_entities | INTEGRATE | |
| clear_graph | INTEGRATE | |
| get_status | INTEGRATE | |
| upsert_typed_entities | INTEGRATE | |
| resolve_typed_entities | INTEGRATE | |
| verify_catalog_batch | INTEGRATE | |
| upsert_typed_edges | INTEGRATE | |
| upsert_provenance | INTEGRATE | |
| get_catalog_ingest_status | INTEGRATE | |
| upsert_catalog_batch | INTEGRATE | |
| get_catalog_capabilities | INTEGRATE | |
