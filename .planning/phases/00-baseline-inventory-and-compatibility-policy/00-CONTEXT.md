# Phase 0: Baseline, Inventory, and Compatibility Policy - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning
**Mode:** Autonomous — recommended options pre-approved by user

<domain>
## Phase Boundary

Record a live-source-grounded baseline, offline historical canary inventory, explicit compatibility boundary, and isolation policy before catalog-v2 contract or identity implementation. This phase does not change product contracts, execute a canary, query or mutate `oracle-catalog-v2`, or modify remote state.

</domain>

<decisions>
## Implementation Decisions

### Baseline Evidence
- Treat current source and tests as authority for the 14 legacy MCP tools, seven catalog tools, catalog models/services/store/schema, and canary workflow inventory.
- Treat repository receipts, checkpoints, requests, and tests as offline historical evidence only.
- Record the pre-hardening ACCEPT_TAB result without querying Neo4j or retrying the canary.
- Keep inventory reproducible through file/symbol references and exact check commands.

### Test and Check Reporting
- Run targeted catalog, canary-workflow, compatibility, Ruff, and Pyright checks when locally available.
- Report each check as pass, fail, or skip; never convert unavailable checks into passes.
- Preserve raw failure identity sufficiently to distinguish pre-existing failures from later v1.1 regressions.
- Do not repair unrelated baseline failures in Phase 0.

### Compatibility Boundary
- Preserve names and public contracts for all 14 legacy MCP tools.
- Preserve all seven existing catalog tool names while documenting that catalog-v2 request identity, provenance, and hash contracts intentionally break catalog-v1 payload compatibility.
- Never silently reinterpret, normalize, migrate, or rewrite catalog-v1 identity as catalog-v2.
- Preserve historical hashes and receipts as invalid-for-v2 evidence rather than reusable golden values.

### Isolation and Repository Safety
- New tests and any permitted development writes use only `oracle-catalog-tool-test`.
- Never query or mutate `oracle-catalog-v2`; never execute the real canary.
- Preserve unrelated dirty-worktree files; task commits include only intentional phase files.
- Do not push, merge, deploy, tag, clear graph data, or delete existing data.

### Claude's Discretion
- Choose the smallest auditable baseline artifact structure and exact non-destructive check subset consistent with the requirements.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Catalog models are split under `mcp_server/src/models/catalog_*.py`.
- Catalog orchestration and Neo4j persistence already live in `mcp_server/src/services/catalog_service.py` and `catalog_store.py`.
- Canary builder and runner exist under `scripts/`; offline coverage exists in `mcp_server/tests/test_catalog_canary_scripts.py`.
- Existing codebase maps document repository structure, conventions, testing, and known concerns.

### Established Patterns
- MCP tools use FastMCP registrations in `mcp_server/src/graphiti_mcp_server.py`.
- MCP tests run from `mcp_server/`, separate from the root suite.
- Ruff and Pyright are the package lint/type gates; pytest reports integration unavailability through skips.
- Domain safety uses strict fixed allowlists, group isolation, and parameterized Cypher.

### Integration Points
- Baseline artifacts should cite MCP registration, catalog model/service/store/schema, canary scripts/artifacts/tests, and package check commands.
- Later phases consume the recorded compatibility and failure baseline to classify regressions.

</code_context>

<specifics>
## Specific Ideas

The user pre-approved every recommended autonomous discussion option. Malformed GSD projections and non-semantic internal workflow errors may be bypassed, but product/test failures must remain truthful.

</specifics>

<deferred>
## Deferred Ideas

- Catalog-v2 contract and identity changes begin in Phase 1.
- Real canary execution remains Phase 6 under separate approval.
- Automatic catalog-v1 migration remains out of scope.

</deferred>
