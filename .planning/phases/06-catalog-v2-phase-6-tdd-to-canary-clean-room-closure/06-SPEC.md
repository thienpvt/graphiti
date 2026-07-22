# Phase 6: Catalog-v2 TDD-to-Canary Clean-Room Closure — Specification

**Created:** 2026-07-22
**Authority:** `fork/v1.1:spec/new-phase.md` at `e52c1b5`
**Ambiguity score:** 0.05 (gate: ≤ 0.20)
**Requirements:** 64 locked

## Goal

Prove one exact committed Catalog-v2 source archive and source-bound image in a fresh isolated Compose authority, then execute exactly one final canary with no historical mutation, secret disclosure, retry after identity allocation, or post-allocation Git commit.

## Background

Commit `1031b79` completed the RED/GREEN harness closure and H1–H7 verification. Commit `090f39b` truthfully records the H8 stop: `git archive` preserved 733/733 members but transformed 634 blob byte streams under Windows EOL handling. No image, namespace, runtime, schema, MCP, or canary action followed. Phase 6 resumes at this exact source-binding defect.

The complete atomic requirements are defined in `.planning/REQUIREMENTS.md` under `## Phase 6 Requirements`. Their IDs are the contractual planning and verification surface:

- Authority/baseline: `P6-AUTH-01`, `P6-BASE-01..03`
- Preservation/provider: `P6-PRES-01..03`, `P6-PROV-01..03`
- Harness: `P6-HARN-01..19`
- TDD/source binding: `P6-TDD-01..04`, `P6-BIND-01..06`
- Image: `P6-IMG-01..05`
- Runtime: `P6-RT-00`, `P6-RT-R0..R3`, `P6-RT-DISP`
- Canary: `P6-CAN-01..06`
- Safety/terminal/report/continuation: `P6-SAFE-01..02`, `P6-TERM-01..04`, `P6-REPT-01`, `P6-CONT-01`

## Requirements

1. **Resume, do not restart**: Reuse immutable H1–H7 evidence; correct H8 through a new fix-forward candidate.
   - Current: `git archive` produced byte-mismatched source authority.
   - Target: raw Git object materialization produces exact files, modes, symlinks, path set, and canonical context hash.
   - Acceptance: every archive member equals its Git blob; archive and Git context hashes match; baseline golden reproduces.

2. **Bind source before runtime**: The exact candidate archive passes the full frozen matrix before image construction.
   - Current: matrix passed in the worktree, not the rejected H8 archive.
   - Target: the same full matrix passes from the exact archive tree.
   - Acceptance: sanitized receipt records all required checks green with no unexplained skip/warning/deselection.

3. **Build one source-bound image**: Build only from the passing archive with exact revision/context labels and no protected material.
   - Current: no Phase 6 clean-room image was built after H8.
   - Target: one commit-derived local image with verified ID, labels, hashes, and secret exclusion.
   - Acceptance: inspect values equal the final candidate; no pull/push/retag or deny-listed file/secret hit occurs.

4. **Stage one fresh runtime**: Render, start Neo4j, bootstrap schema, then start MCP through typed actions only.
   - Current: launcher behavior is covered offline; no final clean-room authority exists.
   - Target: unique absent-before-creation project resources, one hidden namespace, exact 0/14→14/14 schema, exact MCP image ID and readiness.
   - Acceptance: R0–R3 sanitized receipts satisfy every exact count/state check and historical inventory is unchanged.

5. **Cross one irreversible boundary once**: Allocate final canary identities only after every pre-canary gate passes.
   - Current: no canary identity allocated.
   - Target: one final canary, no source/image/runtime mutation, retry, graph cleanup, volume deletion, or Git commit after allocation.
   - Acceptance: one contiguous ledger proves the exact dry-run/prepare/commit/verify/search sequence and a permitted terminal class.

6. **Report without leakage**: Preserve final runtime and emit complete sanitized evidence.
   - Current: H8 stop report contains no runtime/canary results.
   - Target: §20 report binds baseline, iterations, commits, hashes, image, resources, fingerprint, schema, readiness, Gates 0–10, and classification.
   - Acceptance: deny-list scan finds no raw namespace, credential, proxy/API token, prepare token, full environment, or sensitive endpoint parameter.

## Boundaries

**In scope:**
- Raw-Git-exact archive helper/tests and fix-forward candidate commit
- Exact archive matrix and canonical source-context proof
- Local production image build/inspection from that archive
- One fresh local Compose project with new resources only
- One namespace, one schema bootstrap, one MCP activation
- Exactly one final isolated canary and sanitized report
- GSD planning/evidence updates that do not violate the post-allocation no-commit rule

**Out of scope:**
- Production deployment, Kubernetes, push, merge, rebase, amend, tag, or image publication
- Public OpenAI probing or credential/provider/model/endpoint/dimension changes
- Full catalog ingest, automatic v1→v2 migration, historical/live-group access, graph clear/delete
- Historical Docker cleanup, global prune, final-stack cleanup, or a second canary
- Catalog identity/evidence/manifest/request/tool contract changes

## Constraints

- Fixed baseline and prior evidence values remain immutable.
- `mcp_server/config/config-docker-neo4j.yaml` is user-owned and excluded from every stage/build/commit.
- Structured subprocess argv only; fixed allowlists; no shell execution.
- No generative LLM operation. `prepare_catalog_batch` is the first embedding proof.
- After any final canary ID allocation: no source edit, Git commit, image build, alternate runtime, retry, or cleanup.
- Final clean-room project and volumes remain intact.

## Acceptance Criteria

- [ ] Raw Git archive reproduces the baseline context golden and exactly binds the final candidate.
- [ ] Complete frozen matrix passes from the final exact archive.
- [ ] Final local image revision/context labels and ID match candidate authority; deny-list scan is clean.
- [ ] R0 proves selected image/new resources/no build/pull-never and complete historical preservation.
- [ ] R1 creates one namespace authority and starts only healthy Neo4j on exact new volumes.
- [ ] R2 records exactly one 0/14 pre-inspection, one bootstrap, one first 14/14 post-inspection.
- [ ] R3 starts only MCP, verifies exact image ID, 28 tools, status, zero-arg capabilities, fingerprint/schema/provider truth, and allowed unknown readiness.
- [ ] Canary IDs allocate only after all preceding checks pass; Git commit count remains unchanged afterward.
- [ ] Exactly one dry-run returns 3 entities, 2 edges, 1 source, 5 evidence links and persists nothing.
- [ ] Exactly one prepare and one token-only commit occur; commit transport is never retried.
- [ ] Manifest/entity/edge/batch/evidence/search/control/replay reconciliations all pass or yield the exact permitted failure class.
- [ ] Final report is complete and sanitized; final stack/volumes remain intact.

## Edge Coverage

**Coverage:** 18/18 applicable edges resolved · 0 unresolved

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| encoding | P6-BIND-02 | ✅ covered | Raw `git cat-file blob` bytes are authority; CRLF/LF checkout state cannot affect archive members |
| empty/unsupported | P6-BIND-03 | ✅ covered | Empty/missing trees, unsupported modes/types, duplicate paths, collisions, missing/extra members fail closed |
| ordering | P6-BIND-04 | ✅ covered | Context rows use one versioned stable path order and exact `(path, mode, raw digest)` material |
| idempotency | P6-BIND-06 | ✅ covered | Failed candidates are immutable evidence; correction creates a new commit/archive rather than amending |
| boundary | P6-IMG-01 | ✅ covered | Zero image builds before archive gate; exactly one final image authority after gate |
| identity | P6-IMG-03 | ✅ covered | Full revision and context hash labels must exactly equal candidate authority |
| secrecy | P6-IMG-04 | ✅ covered | Explicit context/layer deny list plus secret-pattern scan fails closed |
| validation | P6-HARN-01 | ✅ covered | Empty/path/whitespace/shell/option project names rejected; canonical safe names accepted |
| isolation | P6-HARN-09, P6-HARN-10 | ✅ covered | Two projects have disjoint names/resources; any pre-existing expected resource blocks creation |
| regeneration | P6-HARN-11, P6-HARN-12 | ✅ covered | Authority files are exclusive-create; second generation, overwrite, or project/volume mismatch fails |
| ordering | P6-HARN-03..06 | ✅ covered | Only `render → neo4j → bootstrap → mcp` mutating prefix is accepted; missing/reordered/repeated stage fails |
| schema boundary | P6-HARN-05, P6-RT-R2 | ✅ covered | Preflight must be exact 0/14; first postflight exact 14/14; any other count/shape stops without retry |
| readiness | P6-RT-R3 | ✅ covered | Only registry/status/zero-arg capability calls; `embeddings.ready=unknown` accepted only with native OpenAI waiver |
| adjacency | P6-CAN-01 | ✅ covered | The first allocation of any run/group/control/batch ID starts freeze immediately, not after dry-run or prepare |
| idempotency/concurrency | P6-CAN-04, P6-CAN-06 | ✅ covered | One prepare and one commit only; timeout/ambiguity permits read-only reconciliation, never concurrent/retried commit |
| auth boundary | P6-PROV-03 | ✅ covered | Auth before commit and after commit map to different exact classifications without configuration mutation |
| cardinality | P6-CAN-03, P6-CAN-05 | ✅ covered | Exact dry-run, evidence, search, control, and replay counts are compared without normalization |
| terminal/report | P6-TERM-01..04, P6-REPT-01 | ✅ covered | Classification set depends on boundary state; complete report emitted with secret deny-list and unchanged final resources |

## Prohibitions (must-NOT)

**Coverage:** 16/16 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| MUST NOT stage/commit/image the user-owned config or unrelated dirty paths | P6-PRES-01..02 | resolved | test + staged/context path audit |
| MUST NOT reset, checkout, restore, stash, amend, push, merge, rebase, or tag | P6-PRES-02 | resolved | judgment + Git ledger |
| MUST NOT mutate historical Docker resources or groups | P6-PRES-03, P6-SAFE-01 | resolved | before/after inventory |
| MUST NOT invoke generative LLM or public OpenAI probes | P6-PROV-01 | resolved | call ledger/static contract |
| MUST NOT change provider/model/endpoint/credential/dimension after auth failure | P6-PROV-03 | resolved | configuration/ledger comparison |
| MUST NOT use arbitrary Compose passthrough or shell execution | P6-HARN-14 | resolved | negative argv tests |
| MUST NOT use `git archive`, checkout bytes, or EOL normalization as raw source authority | P6-BIND-02 | resolved | source assertion + CRLF fixture |
| MUST NOT rewrite failed candidate evidence or amend commits | P6-BIND-06 | resolved | Git/evidence ledger |
| MUST NOT retag the historical image or build from dirty worktree | P6-IMG-01..03 | resolved | build command/inspect audit |
| MUST NOT include namespace, `.env`, tokens, credentials, local config, or runtime evidence in image | P6-IMG-04 | resolved | context/layer scan |
| MUST NOT activate runtime before exact archive/image gates pass | P6-RT-00 | resolved | ordered gate receipt |
| MUST NOT rerun/repair/drop/replace schema after failed first post-inspection | P6-RT-R2 | resolved | bootstrap/launcher ledger |
| MUST NOT proactively probe embeddings during readiness | P6-RT-R3 | resolved | MCP call ledger |
| MUST NOT edit source, commit, rebuild, allocate another runtime, retry, or clean after canary ID allocation | P6-CAN-01 | resolved | freeze receipt + Git/Docker/MCP ledger |
| MUST NOT retry ambiguous commit transport | P6-CAN-06 | resolved | exactly one commit-call ledger entry |
| MUST NOT remove final clean-room stack/volumes after any terminal result | P6-SAFE-02 | resolved | final resource inventory |

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|-----------|------:|----:|--------|-------|
| Goal Clarity | 0.98 | 0.75 | ✓ | Exact ordered terminal operation |
| Boundary Clarity | 0.99 | 0.70 | ✓ | Fixed authority, resource, provider, and destructive-operation fences |
| Constraint Clarity | 0.99 | 0.65 | ✓ | Exact counts, hashes, stages, calls, classifications |
| Acceptance Criteria | 0.96 | 0.70 | ✓ | Offline, image, runtime, and one-canary proofs |
| **Ambiguity** | **0.05** | **≤0.20** | ✓ | Remaining implementation details are explicitly discretionary |

## Interview Log

| Round | Perspective | Question summary | Decision locked |
|-------|-------------|------------------|-----------------|
| 1 | Authority | What supersedes stale Phase 5 canary bans? | Fetched `e52c1b5` for Phase 6 only |
| 2 | Continuation | Restart H1 or resume H8? | Reuse H1–H7; fix-forward raw-source binding |
| 3 | Safety | When does authority freeze? | First final canary ID allocation |
| 4 | Verification | What proves done? | Exact archive/image/R0–R3/Gates 0–10/report chain |

---

*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Spec created: 2026-07-22*
*Next step: `/gsd-plan-phase 6`*
