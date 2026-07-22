# Operation: Catalog-v2 Phase 6 TDD-to-Canary Clean-Room Closure

Authorization:
ITERATIVE_TDD_IMPLEMENTATION_AND_ONE_FINAL_CLEANROOM_CANARY

## 1. Mission and completion contract

Continuously execute:

RED acceptance tests
→ minimal implementation
→ GREEN focused tests
→ refactor
→ complete regression matrix
→ exact source commit
→ source-bound runtime image
→ clean-room runtime readiness
→ one final Phase 6 canary

Ordinary test failures, lint errors, type errors, and implementation defects are
feedback for the TDD loop. Diagnose, fix, and rerun them.

Do not stop merely with:

- READY_FOR_REVIEW
- BLOCKED_HARNESS_IMPLEMENTATION
- BLOCKED_FROZEN_TESTS
- a failing focused test;
- a regression caused by this task;
- a lint, formatting, or type-check failure caused by this task.

Continue until the complete acceptance contract passes or a genuine hard blocker
requires external authority.

## 2. Fixed baseline

Start from:

- Git commit:
  35227e0a2c697e643871b5c2052556988c404df6
- Git tree:
  fed171af3c49dc96701da26b53fd391511a00735
- Source context SHA-256:
  dcf73073443be37b777fc7feef124133be3d9ee305696e84042d5631125ed92f
- Previously approved image:
  graphiti-mcp:phase6-35227e0a2c69-bound
- Previous image ID:
  sha256:994e1d1307dfd64ba0955a5e2469324721318a81514093b901fd853ad341d099

Preserve all existing immutable runtime and blocked-operation evidence.

Known baseline blockers:

1. Runner forces Compose project graphiti-catalog-local:
   scripts/run_catalog_canary_batch.py around the previously reported line 2665.
2. Launcher can start only graphiti-mcp and cannot stage clean-room Neo4j:
   scripts/run_catalog_canary_launcher.py around the previously reported
   lines 20 and 34.
3. Compose hardcodes thienpvt/mem0:graphiti-mcp instead of accepting the approved
   source-bound image:
   mcp_server/docker/docker-compose-neo4j.yml around the previously reported
   line 25.

Verify these conditions directly before editing. Line numbers may move after
implementation and are not contractual.

## 3. Preserve user-owned state

The user-owned dirty file:

mcp_server/config/config-docker-neo4j.yaml

must remain untouched and unstaged.

Record all dirty paths before work.

Do not use:

- git reset;
- git checkout;
- git restore;
- git stash;
- destructive worktree cleanup;
- broad file replacement.

Do not stage or commit unrelated user changes or runtime evidence.

## 4. Provider and credential policy

This Catalog-v2 canary must not invoke generative LLM operations.

Do not call or probe:

- add_memory;
- summarize_saga;
- build_communities;
- LLM extraction;
- chat/completion endpoints;
- direct LLM provider health endpoints;
- public OpenAI endpoints.

Provider-dependent operations are limited to embeddings required by:

- prepare_catalog_batch;
- search_nodes;
- search_memory_facts.

Use the existing local OpenAI-compatible proxy configuration unchanged.

Do not require, request, generate, rotate, or validate a public OpenAI API key.

If the local proxy accepts unauthenticated requests, no credential is required.

If the OpenAI-compatible client requires a non-empty local development token,
preserve the existing local proxy token without exposing or modifying it.

The token must never appear in:

- source;
- Git;
- command arguments;
- process listings;
- logs;
- evidence;
- reports;
- test snapshots;
- Docker image layers.

An absent public OPENAI_API_KEY is not a blocker.

Do not perform a proactive embedding-provider request during readiness.

Successful prepare_catalog_batch is the first functional embedding proof.

If an actual authorized provider-dependent operation returns an authentication
failure, classify it according to canary state:

- prepare failure before commit:
  FAILED_BEFORE_COMMIT with cause embedding_transport_auth;
- search failure after commit:
  FAILED_AFTER_COMMIT with cause embedding_transport_auth.

Never bypass an authentication failure by mutating provider responses or using a
different endpoint, model, provider, credential, or embedding dimension.

## 5. Acceptance contract

Implementation is complete only when the committed harness supports:

1. Explicit validated clean-room Compose project names.
2. Backward-compatible default project graphiti-catalog-local.
3. Canonical effective-Compose rendering.
4. Canonical Neo4j-only startup.
5. Canonical application-owned Catalog-v2 schema bootstrap.
6. Canonical graphiti-mcp-only startup.
7. Explicit MCP runtime-image selection.
8. Exact post-start image-ID verification.
9. Project-scoped Neo4j data and log volumes.
10. Proof that clean-room volumes did not previously exist.
11. Safe one-time UUIDv4 namespace generation per clean-room volume.
12. Namespace fingerprint binding to project and data-volume identity.
13. Raw namespace exclusion from output, evidence, Git, and image layers.
14. Fixed allow-listed Compose operations with no arbitrary passthrough.
15. Contiguous sanitized launcher and MCP ledgers.
16. Exact existing 22-field live-manifest compatibility.
17. Exact 28-tool MCP registry compatibility.
18. Phase 5 and Phase 6 regression compatibility.

Do not change Catalog-v2 identity, evidence, manifest, or MCP tool contracts to
solve an orchestration problem.

## 6. TDD Stage A — Write RED acceptance tests first

Before production changes, add behavioral acceptance tests for the missing
capabilities.

Each initial test must fail for the intended missing behavior—not due to broken
imports, fixtures, mocks, dependencies, or test setup.

### Project authority tests

Cover:

- explicit safe project name accepted;
- legacy default project preserved;
- empty project name rejected;
- path-like names rejected;
- whitespace and shell fragments rejected;
- option-injection names rejected;
- runner and launcher share the same effective project;
- project name is passed as structured subprocess argv.

### Service staging tests

Cover:

- render-only action;
- Neo4j-only startup;
- bootstrap-only action;
- graphiti-mcp-only startup;
- required execution order;
- MCP startup cannot recreate Neo4j;
- arbitrary services rejected;
- arbitrary Compose actions rejected.

### Image-binding tests

Cover:

- legacy image default remains unchanged;
- explicit clean-room image accepted;
- rendered Compose contains the selected image;
- no build;
- pull never;
- absent local image rejected;
- ambiguous service container rejected;
- running image-ID mismatch rejected;
- exact matching image ID accepted.

### Volume-isolation tests

Cover:

- two different projects produce disjoint data volumes;
- disjoint log volumes;
- disjoint networks;
- disjoint service containers;
- pre-existing clean-room volume rejected;
- external volume rejected;
- historical volume rejected;
- old host database bind mount rejected;
- only expected new volumes are mounted.

### Namespace tests

Cover:

- one cryptographically random UUIDv4 per clean-room authority;
- exclusive local authority-file creation;
- no overwrite;
- no silent regeneration;
- only fingerprint returned;
- namespace bound to project and data volume;
- raw namespace absent from logs, exceptions, argv, evidence, and Git output;
- existing-runtime mode still requires an existing namespace;
- generation available only in explicit clean-room mode.

### Schema-bootstrap tests

Cover:

- precondition requires Catalog-v2 exact 0/14;
- raw Neo4j driver only;
- no Graphiti Neo4jDriver construction;
- exactly one bootstrap execution;
- exactly one post-bootstrap inspection;
- first non-14/14 result stops;
- no retry;
- no repair;
- no drop;
- no manually authored alternate Cypher;
- no domain/control-plane write.

### Safety-policy tests

Reject:

- docker system prune;
- docker container prune;
- docker volume prune;
- down against historical projects;
- down -v against historical projects;
- arbitrary rm;
- arbitrary build;
- arbitrary pull;
- arbitrary Compose files;
- arbitrary profiles;
- arbitrary command fragments;
- shell execution;
- historical resource mutation.

Capture a RED evidence report mapping each failing test to its requirement.

## 7. TDD Stage B — Minimal implementation

Implement only what is required for the acceptance tests.

Expected scope may include:

- scripts/run_catalog_canary_launcher.py
- scripts/run_catalog_canary_batch.py
- scripts/build_catalog_canary_requests.py
- scripts/bootstrap_catalog_v2_schema.py
- mcp_server/docker/docker-compose-neo4j.yml
- committed Catalog-v2 override/example/materializer
- focused tests
- operator/migration documentation

Prefer a backward-compatible image variable conceptually equivalent to:

image: ${GRAPHITI_MCP_IMAGE:-thienpvt/mem0:graphiti-mcp}

Follow existing project conventions for the final implementation.

Do not retag the previous image as a workaround.

The launcher must expose typed, allow-listed operations. It must not become a
generic Docker Compose wrapper.

Use structured subprocess argv only. Never use shell interpolation.

## 8. TDD Stage C — Iterative RED/GREEN loop

For each failing requirement:

1. Run the smallest relevant failing test.
2. Verify the failure reason.
3. Apply the minimal production fix.
4. Rerun the test.
5. Run adjacent regression tests.
6. Refactor only while tests remain green.
7. Continue with the next requirement.

If a test encodes an incorrect assumption:

1. Compare it with the committed contract and this authorization.
2. Correct it transparently.
3. Record the original assumption and why it was wrong.
4. Prove the revised test still detects a real regression.

Do not weaken, delete, skip, deselect, or broadly mock tests merely to obtain
green output.

Continue until all focused acceptance tests pass.

## 9. TDD Stage D — Full verification loop

Run from a source-complete environment:

- changed Python compilation;
- launcher tests;
- builder/runner tests;
- materializer tests;
- schema-bootstrap tests;
- formatting tests;
- Phase 5 suite;
- Phase 6 suite;
- combined remediation suite;
- full relevant union;
- direct golden contracts;
- exact golden hashes;
- exact shared 22-field manifest;
- exact 28-tool registry;
- Ruff check;
- Ruff format check;
- Pyright.

No unexplained failures, skips, deselections, warnings, or stale test evidence are
acceptable.

If any failure is caused by this task, return to the RED/GREEN loop, fix it, and
rerun the complete matrix.

Do not treat a missing local test dependency as proof that tests pass. Use the
source-complete verification environment already established by the project.

## 10. Source commit and exact archive loop

After the complete matrix passes:

1. Stage only task-owned source, tests, and documentation.
2. Preserve unrelated dirty files.
3. Create a local candidate commit.
4. Do not push, merge, rebase, amend, or tag.
5. Build a raw-Git LF-exact archive from that commit.
6. Verify membership, modes, symlinks, duplicates, collisions, and hashes.
7. Compute the canonical source-context SHA-256.
8. Run the complete frozen matrix against the exact archive.

If the exact committed archive fails:

1. Return to the TDD loop.
2. Fix forward.
3. Create another local commit.
4. Rebuild and reverify a new exact archive.

Do not amend evidence for prior candidate commits.

The final authoritative commit is the latest candidate whose exact archive
passes the complete matrix.

## 11. Source-bound runtime-image loop

Build a new runtime image only from the exact passing Git archive.

Use a commit-derived tag such as:

graphiti-mcp:phase6-cleanroom-<short-commit>-bound

Require:

- production Dockerfile;
- no dirty-worktree build context;
- no pull;
- OCI revision equals final authoritative commit;
- OCI source-context label equals final context hash;
- no namespace;
- no local Catalog-v2 config;
- no `.env`;
- no local proxy token;
- no credential;
- no runtime evidence;
- no secret-pattern hit.

Capture:

- image tag;
- image ID;
- Dockerfile hash;
- build-log hash;
- inspect hash;
- archive/context hash.

Do not push or retag the image.

If build failure is caused by implementation, return to TDD and fix forward.

## 12. Pre-canary runtime iteration boundary

Runtime testing may begin only after:

- complete focused tests pass;
- complete regression matrix passes;
- exact committed archive passes;
- new image binding passes.

Before any canary identity is allocated, a harness/runtime implementation defect
may return to the TDD loop.

For each runtime candidate:

- use a unique Compose project;
- use unique Neo4j data and log volumes;
- use one namespace bound only to that data volume;
- preserve sanitized evidence.

If a runtime candidate fails before any canary ID, prepare, domain write, or
control-plane write, it may be treated as disposable.

Scoped cleanup is authorized only when all are proven:

- project was created by this operation;
- no canary ID was allocated;
- no prepare occurred;
- no catalog/domain/control-plane data exists;
- volumes are not external or shared;
- exact project/container/network/volume targets are recorded;
- no historical resource is referenced.

Only that exact disposable project and its exact volumes may be removed.

Global cleanup remains forbidden.

If safe cleanup cannot be proven, preserve the failed candidate and use a new
project name.

## 13. Clean-room runtime Stage R0 — Isolation authority

Allocate a fresh runtime-candidate ID.

Select a unique Compose project such as:

graphiti-phase6-cleanroom-<fresh-runtime-id>

Resolve its expected:

- Neo4j data volume;
- Neo4j log volume;
- network;
- Neo4j container;
- graphiti-mcp container.

Prove all are absent before creation.

Render effective Compose and prove:

- explicit new source-bound MCP image;
- new project-scoped volumes only;
- no historical volume;
- no external volume;
- no old database bind mount;
- no build;
- pull never;
- clean-room MCP connects only to clean-room Neo4j.

Do not delete or alter historical Docker resources.

## 14. Stage R1 — Namespace and Neo4j

Generate exactly one UUIDv4 through the canonical materializer.

Never output the raw namespace.

Record only:

- generation success;
- UUID validity;
- namespace fingerprint;
- sanitized authority hash;
- project identity;
- data-volume identity.

Start only clean-room Neo4j.

Verify:

- data and log volumes were created in this operation;
- Neo4j mounts exactly those volumes;
- historical volumes remain unchanged;
- Neo4j is healthy;
- graphiti-mcp has not started.

## 15. Stage R2 — Schema bootstrap

Run exactly one application-owned pre-bootstrap inspection.

Require:

- required Catalog-v2 constraints: 14;
- exact present: 0;
- missing: 14;
- wrong-shaped: 0.

Run exactly one application-owned bootstrap.

Run exactly one post-bootstrap inspection.

Require the first post-bootstrap result:

- identity category: ready;
- prepared-plan category: ready;
- evidence/manifest category: ready;
- exact present: 14/14;
- missing: 0;
- wrong-shaped: 0.

Do not retry, rerun, repair, or replace schema after a failed post-inspection.

A harness defect found before canary allocation may return to TDD using a new
runtime candidate.

## 16. Stage R3 — MCP activation and readiness

Start only graphiti-mcp using the new source-bound image.

Require:

- no dependencies recreated;
- no build;
- pull never;
- exact expected project;
- exact clean-room Neo4j;
- exact running image ID.

Before allocating any canary identity, call only:

1. exact MCP tool registry;
2. get_status;
3. zero-argument get_catalog_capabilities.

Require:

- exactly 28 tools;
- MCP healthy;
- Neo4j connected;
- catalog reads enabled;
- catalog writes enabled;
- namespace configured;
- effective namespace fingerprint matches local authority;
- Catalog-v2 schema exact 14/14;
- provider=openai;
- actual embeddings.ready=unknown;
- native committed OpenAI unknown-readiness waiver supported;
- raw capability response retained unchanged;
- no response projection;
- no direct provider call.

Do not require an LLM credential or public OpenAI API key.

## 17. Final canary boundary

Once any of the following is allocated:

- canary run ID;
- canary group;
- control group;
- batch ID;

the iterative TDD/runtime loop is closed.

After that point:

- do not edit source;
- do not commit;
- do not build another image;
- do not allocate another canary;
- do not retry the canary;
- do not reset or delete the clean-room volume;
- do not clean graph data.

Execute exactly one final canary using the committed:

graphiti_mcp_phase6_canary_agent_prompt_en.md

Use entirely new canary identities.

Never reuse or query historical canary groups.

Require:

1. Fresh canary/control-group isolation.
2. Deterministic live artifact.
3. Exact shared 22-field manifest.
4. Exactly one dry_run=true.
5. Dry-run counts:
   - 3 entities;
   - 2 edges;
   - 1 source artifact;
   - 5 evidence links.
6. Zero persistent writes after dry-run.
7. Exactly one prepare_catalog_batch.
8. Successful prepare as functional embedding proof.
9. Prepare token retained only in memory.
10. Exactly one token-only commit.
11. No commit retry.
12. Manifest verification.
13. Entity resolution.
14. Edge resolution.
15. Batch verification.
16. Five evidence-target reconciliations.
17. Three entity searches.
18. Two fact searches using attributes.edge_key.
19. Empty control-group isolation.
20. Committed controlled-replay gate.
21. Contiguous sanitized tool ledger.

If commit transport is ambiguous, use only committed bounded read-only
reconciliation. Never retry commit.

If prepare returns embedding authentication failure:

- classify FAILED_BEFORE_COMMIT;
- preserve evidence;
- do not change provider configuration;
- do not retry.

If search returns embedding authentication failure after commit:

- classify FAILED_AFTER_COMMIT;
- preserve the committed batch;
- do not clean up or retry.

## 18. Docker safety

Never execute:

- docker system prune;
- docker container prune;
- docker volume prune;
- global container removal;
- global volume removal;
- cleanup of historical Compose projects;
- down -v against historical projects;
- mounting historical Neo4j volumes;
- Kubernetes actions.

Historical resources must remain unchanged, including:

- docker-neo4j-1;
- docker_neo4j_data;
- docker_neo4j_logs;
- historical canary data and evidence.

Leave the final clean-room stack and volume intact after canary success or
failure.

## 19. Terminal conditions

Successful terminal condition:

PASSED

Valid hard-stop conditions before canary allocation:

- HARD_BLOCKED_BASELINE_AUTHORITY
- HARD_BLOCKED_TOOLCHAIN
- HARD_BLOCKED_REQUIREMENT_CONFLICT
- HARD_BLOCKED_LOCAL_RUNTIME_AUTHORITY

Do not use missing public OpenAI credentials as a blocker.

After canary allocation, use only the committed canary classifications,
including:

- FAILED_BEFORE_COMMIT
- FAILED_AFTER_COMMIT
- PASSED

Ordinary code, test, lint, type, build, or pre-canary harness failures remain
inside the authorized iterative TDD loop.

## 20. Final report

Report:

- baseline authority;
- RED tests and mapped requirements;
- RED/GREEN iteration count;
- production changes;
- any corrected test assumptions and justification;
- complete final test matrix;
- candidate commits;
- final authoritative commit and tree;
- exact archive/context hashes;
- final runtime image tag and image ID;
- disposable runtime candidates created or removed;
- proof historical Docker resources remained unchanged;
- final clean-room project, network, data volume, and log volume;
- namespace fingerprint only;
- schema 0/14 → 14/14 evidence;
- running image ID;
- raw capability hash;
- actual embedding readiness;
- native OpenAI waiver decision;
- confirmation no LLM/generation call occurred;
- canary identities;
- request, catalog, artifact, prepared-artifact, and manifest hashes;
- dry-run, prepare, and commit counts;
- Gates 0–10;
- complete sanitized Compose and MCP ledgers;
- final classification.

Never include:

- raw namespace;
- proxy token;
- API key;
- prepare token;
- full container environment;
- credentials or sensitive endpoint parameters.