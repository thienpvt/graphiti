# API Coverage — Graphiti MCP catalog tools (Phase 2)

> Detector fired on internal MCP/catalog wording (wire MCP tool, integration tests), not a new third-party SaaS SDK.
> Full coverage by default for the Phase 2 catalog administrative surface. Opt-outs are explicit.

| capability | decision | reason |
|---|---|---|
| upsert_provenance | INTEGRATE | |
| get_catalog_ingest_status | INTEGRATE | |
| upsert_catalog_batch | INTEGRATE | |
| upsert_typed_entities | INTEGRATE | |
| upsert_typed_edges | INTEGRATE | |
| resolve_typed_entities | INTEGRATE | |
| verify_catalog_batch | INTEGRATE | |
| add_memory semantic ingest changes | OPT-OUT | explicitly out of scope — preserve existing semantic path |
| add_episode for catalog sources | OPT-OUT | explicitly out of scope — catalog uses deterministic Episodic writers |
| queue_service catalog routing | OPT-OUT | explicitly out of scope — no async catalog ingest |
| falkordb catalog writes | OPT-OUT | explicitly out of scope — Neo4j only this milestone |
| live oracle-catalog-v2 canary execution | OPT-OUT | explicitly out of scope — documentation recommendation only |
| full 14106-entity production ingest | OPT-OUT | explicitly out of scope — tools and tests only |
| kubernetes deployment automation | OPT-OUT | explicitly out of scope — docs samples only |
| clear_graph or destructive cleanup tools | OPT-OUT | explicitly out of scope — no destructive ops |
| automatic build_communities on upsert | OPT-OUT | explicitly out of scope — community-neutral upserts |
| new external REST or SaaS SDK | OPT-OUT | not needed — extends existing internal Neo4j MCP catalog surface only |
