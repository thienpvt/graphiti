# Phase 6: Catalog-v2 TDD-to-Canary Clean-Room Closure - Research

**Researched:** 2026-07-22
**Domain:** Clean-room harness closure, raw-Git source binding, source-bound Docker image, isolated Compose runtime, single final Catalog-v2 canary
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Fixed Authority and Continuation
- `fork/v1.1:spec/new-phase.md` at `e52c1b5` is the Phase 6 authorization and acceptance authority.
- Fixed implementation baseline is commit `35227e0a2c697e643871b5c2052556988c404df6`, tree `fed171af3c49dc96701da26b53fd391511a00735`, source-context SHA-256 `dcf73073443be37b777fc7feef124133be3d9ee305696e84042d5631125ed92f`.
- Existing implementation commit `1031b7921fc1f6ca2b7f5aa20e7a02a0a2959ff8` and documentation commit `090f39bb87194c38d3806f8a75e5a52d51e13b31` are valid prior iteration history, not authority to skip remaining gates.
- Reuse the passing H1-H7 evidence. Correct the raw-Git/archive byte-binding defect with a new fix-forward commit; never amend prior candidates.

#### Source, Test, and Image Gates
- Follow RED → minimal implementation → GREEN → adjacent regression → full matrix. Ordinary failures remain inside the loop.
- Exact raw-Git LF bytes are authoritative. Build and verify an exact archive without checkout/EOL transformation; membership, modes, symlinks, duplicates, collisions, hashes, and full frozen matrix must pass.
- Stage and commit task-owned source/tests/docs only. No push, merge, rebase, amend, or tag.
- Build the production image only from the exact passing archive, with commit-derived tag, exact OCI revision/context labels, no pull, no retag, no dirty context, and no secret/config/evidence inclusion.

#### Clean-Room Runtime Authority
- Use only typed, fixed allow-listed launcher actions and structured subprocess argv. No shell or generic Compose passthrough.
- Preserve the legacy default project while using one explicit fresh validated project for the final runtime.
- Prove project network, containers, data volume, and log volume absent before creation; reject external/historical volumes and host database bind mounts.
- Generate exactly one UUIDv4 namespace via the canonical materializer, bind its fingerprint to project/data-volume identity, and never expose the raw value.
- Stage Neo4j only, run exactly one canonical application-owned 0/14 → 14/14 schema bootstrap, then stage MCP only without dependency recreation. Verify exact running image ID.
- Readiness calls are limited to exact tool registry, `get_status`, and zero-argument `get_catalog_capabilities`. No proactive embedding/provider probe and no generative LLM operation.

#### Final Canary Boundary
- Before allocation of canary run/group/control-group/batch identity, harness/runtime defects may fix forward using new disposable candidates under the specification's proof and cleanup limits.
- Once any canary identity is allocated, freeze source, commit, image, and runtime. No edit, rebuild, new candidate, retry, reset, graph cleanup, or volume deletion.
- Execute exactly one final canary with new identities and the committed `graphiti_mcp_phase6_canary_agent_prompt_en.md` contract.
- An ambiguous commit transport permits bounded read-only reconciliation only; never retry commit.
- Authentication failure is classified exactly as `FAILED_BEFORE_COMMIT` or `FAILED_AFTER_COMMIT`; never change provider, model, endpoint, credential, response, or embedding dimension.
- Leave the final clean-room stack and volumes intact after success or failure.

#### Preservation and Reporting
- Preserve `mcp_server/config/config-docker-neo4j.yaml` untouched and unstaged.
- Never run global Docker prune/removal, historical project cleanup, Kubernetes action, public OpenAI probe, deployment, or historical/live-group mutation.
- Never disclose raw namespace, proxy/API token, prepare token, credentials, full container environment, or sensitive endpoint parameters.
- Final evidence and ledgers are contiguous and sanitized; report baseline, RED/GREEN iterations, test matrix, candidate commits, exact hashes, image/runtime identities, schema transition, readiness, canary gates, and final classification.

### Claude's Discretion
- Minimal internal decomposition, test grouping, evidence filenames, and a raw-Git-exact archive implementation may follow existing project patterns, provided every fixed contract above remains exact.

### Deferred Ideas (OUT OF SCOPE)
- Production deployment, Kubernetes rollout, full catalog ingest, automatic catalog-v1 migration, non-Neo4j portability, historical resource cleanup, and any second canary remain out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

Atomic requirement IDs decomposed from `e52c1b5:spec/new-phase.md` (§5–§20) plus `graphiti_mcp_phase6_canary_agent_prompt_en.md` Gates 0–10. Map status against baseline `35227e0`, prior implementation `1031b79`, and remaining work.

| ID | Description | Research Support / Status |
|----|-------------|---------------------------|
| P6-AUTH-01 | Authorization is `ITERATIVE_TDD_IMPLEMENTATION_AND_ONE_FINAL_CLEANROOM_CANARY` from `e52c1b5` | Spec §1; supersedes stale ROADMAP “Phase 6 out of scope” |
| P6-BASE-01 | Start from commit `35227e0`, tree `fed171af`, source-context `dcf73073…` | Verified via `git rev-parse` / `git cat-file` |
| P6-BASE-02 | Prior image `graphiti-mcp:phase6-35227e0a2c69-bound` / `sha256:994e1d13…` is historical only; do not retag | Spec §2; local image present |
| P6-BASE-03 | Known baseline blockers (forced project, launcher Neo4j gap, hardcoded image) must be verified against current code | Closed by `1031b79` harness work; re-verify only if archive rebuild regresses |
| P6-PRES-01 | Leave `mcp_server/config/config-docker-neo4j.yaml` untouched/unstaged | Dirty; current hash-object `bf258b96…` (user-owned; h8 recorded prior `815d00fe…`) |
| P6-PRES-02 | No `git reset/checkout/restore/stash`, broad replacement, push/merge/rebase/amend/tag | Spec §3, §10; CONTEXT locked |
| P6-PRES-03 | Preserve historical Docker resources (`docker-neo4j-1`, `docker_neo4j_*`, prior canary data/evidence) | Spec §18 |
| P6-PROV-01 | No generative LLM ops; no public OpenAI probe; no credential mutation | Spec §4 |
| P6-PROV-02 | Provider ops limited to embeddings via prepare/search; successful prepare is first embedding proof | Spec §4, §17; canary Gate 5 |
| P6-PROV-03 | Auth failure → exact `FAILED_BEFORE_COMMIT` / `FAILED_AFTER_COMMIT` with `embedding_transport_auth` | Spec §4, §17 |
| P6-HARN-01 | Explicit validated clean-room Compose project names; reject empty/path/whitespace/shell/option injection | Implemented in `1031b79` + tests; keep |
| P6-HARN-02 | Backward-compatible default project `graphiti-catalog-local` | Implemented |
| P6-HARN-03 | Canonical effective-Compose render action | Launcher `render` |
| P6-HARN-04 | Neo4j-only startup | Launcher `neo4j` |
| P6-HARN-05 | Application-owned Catalog-v2 schema bootstrap 0/14→14/14, no retry | `catalog_schema_bootstrap.py` + launcher `bootstrap` |
| P6-HARN-06 | graphiti-mcp-only startup without dependency recreation | Launcher `mcp` |
| P6-HARN-07 | Explicit MCP image selection via `GRAPHITI_MCP_IMAGE` | Compose uses `${GRAPHITI_MCP_IMAGE:-thienpvt/mem0:graphiti-mcp}` |
| P6-HARN-08 | Exact post-start image-ID verification | `verify_observed_image_id` / `_inspect_mcp_image` |
| P6-HARN-09 | Project-scoped Neo4j data+log volumes | Compose override + launcher resource map |
| P6-HARN-10 | Prove clean-room volumes absent before creation | `_require_all_absent` |
| P6-HARN-11 | One UUIDv4 per clean-room volume via materializer; fingerprint only | `materialize_clean_room` |
| P6-HARN-12 | Namespace fingerprint bound to project + data volume | Authority file keys |
| P6-HARN-13 | Raw namespace excluded from output/evidence/Git/image | Materializer quiet + sanitization |
| P6-HARN-14 | Fixed allow-listed Compose ops; no shell/arbitrary passthrough | `PUBLIC_ACTIONS`; `shell=False` |
| P6-HARN-15 | Contiguous sanitized launcher/MCP ledgers | Existing sanitization paths |
| P6-HARN-16 | Exact 22-field live-manifest compatibility | `catalog_canary_manifest_contract.py`; H7 proved |
| P6-HARN-17 | Exact 28-tool MCP registry | Canary Gate 1; readiness R3 |
| P6-HARN-18 | Phase 5 + Phase 6 regression compatibility | H7: 80 Phase5 + 413 union + 115 harness/direct |
| P6-HARN-19 | Do not change Catalog-v2 identity/evidence/manifest/MCP tool contracts for orchestration | Spec §5 last clause |
| P6-TDD-01 | RED acceptance tests first for missing capabilities | H1 evidence `expected-red` |
| P6-TDD-02 | Minimal implementation only | H1–H7 closed at `1031b79` |
| P6-TDD-03 | Iterative RED/GREEN; no weaken/skip/mock to green | Spec §8 |
| P6-TDD-04 | Full frozen matrix green before commit binding | H7 `READY_FOR_COMMIT_BINDING` |
| P6-BIND-01 | Stage only task-owned source/tests/docs; create local candidate commit | Done for `1031b79`; new fix-forward still required |
| P6-BIND-02 | Build raw-Git LF-exact archive (no checkout/EOL transform) | **REMAINING — root defect** |
| P6-BIND-03 | Verify membership, modes, symlinks, duplicates, collisions, hashes | H8 inventory 733/733 OK; bytes failed |
| P6-BIND-04 | Compute canonical source-context SHA-256 | H8 raw-git `051c0795…` vs archive `156ba0ce…` mismatch |
| P6-BIND-05 | Re-run complete frozen matrix against exact archive | **REMAINING** (blocked by BIND-02) |
| P6-BIND-06 | Fix-forward new commits only; never amend prior candidates | CONTEXT locked |
| P6-IMG-01 | Build runtime image only from exact passing archive | **REMAINING** |
| P6-IMG-02 | Commit-derived tag `graphiti-mcp:phase6-cleanroom-<short>-bound` | Spec §11 |
| P6-IMG-03 | Production Dockerfile; no dirty context; no pull; OCI revision=commit; OCI source-context label=context hash | Dockerfile.standalone already has `org.opencontainers.image.revision` |
| P6-IMG-04 | Exclude namespace, local Catalog-v2 config, `.env`, proxy token, credentials, runtime evidence, secret patterns | Spec §11 |
| P6-IMG-05 | Capture tag, image ID, Dockerfile/build-log/inspect/archive hashes; no push/retag | Spec §11 |
| P6-RT-00 | Runtime only after tests + exact archive + image binding pass | Spec §12 |
| P6-RT-R0 | Isolation authority: unique project, prove resources absent, render effective Compose proofs | Spec §13 **REMAINING** |
| P6-RT-R1 | One UUIDv4; start Neo4j only; volumes created here; MCP not started | Spec §14 **REMAINING** |
| P6-RT-R2 | Exactly one 0/14 pre, one bootstrap, one 14/14 post; no retry/repair | Spec §15 **REMAINING** |
| P6-RT-R3 | Start MCP only; exact image ID; readiness = registry + get_status + zero-arg capabilities only; embeddings.ready may be `unknown` with OpenAI waiver | Spec §16 **REMAINING** |
| P6-RT-DISP | Pre-canary disposable candidates may clean up only under full proof conditions; else preserve and new project | Spec §12 |
| P6-CAN-01 | Freeze after any canary run/group/control/batch ID allocation | Spec §17 |
| P6-CAN-02 | Exactly one final canary via `graphiti_mcp_phase6_canary_agent_prompt_en.md` with new identities | Spec §17 **REMAINING** |
| P6-CAN-03 | Dry-run counts 3e/2edge/1src/5ev; zero writes after dry-run | Spec §17 items 4–6 |
| P6-CAN-04 | Exactly one prepare (embedding proof) + one token-only commit; no commit retry | Spec §17 items 7–11 |
| P6-CAN-05 | Manifest/entity/edge/batch verify; 5 evidence reconciles; 3 entity + 2 fact searches; empty control; controlled-replay gate; contiguous sanitized ledger | Spec §17 + prompt Gates 8–10 |
| P6-CAN-06 | Ambiguous commit → bounded read-only reconciliation only | Spec §17; prompt Gate 7 |
| P6-SAFE-01 | Never docker system/container/volume prune; never historical down -v; never K8s; never mount historical volumes | Spec §18 |
| P6-SAFE-02 | Leave final clean-room stack+volumes intact after success or failure | Spec §18 |
| P6-TERM-01 | Success terminal: `PASSED` | Spec §19 |
| P6-TERM-02 | Pre-canary hard-stops only: `HARD_BLOCKED_BASELINE_AUTHORITY`, `HARD_BLOCKED_TOOLCHAIN`, `HARD_BLOCKED_REQUIREMENT_CONFLICT`, `HARD_BLOCKED_LOCAL_RUNTIME_AUTHORITY` | Spec §19 |
| P6-TERM-03 | Post-allocation canary classes: `FAILED_BEFORE_COMMIT`, `FAILED_AFTER_COMMIT`, `PASSED` (plus prompt `BLOCKED` pre-dry-run) | Spec §19 + prompt |
| P6-TERM-04 | Missing public OPENAI_API_KEY is not a blocker | Spec §4, §19 |
| P6-REPT-01 | Final report fields per Spec §20; never include secrets/raw namespace/tokens/full env | Spec §20 |
| P6-CONT-01 | Do not re-execute completed H1–H7 without cause; resume from `BLOCKED_POST_COMMIT_SOURCE_BINDING` | CONTEXT + 9s8 evidence |

**Prior iteration evidence (do not rewrite):**
- H1 RED: `.planning/quick/260722-9s8-…/evidence/h1-red-receipt.json`
- H7 full matrix: `h7-full-receipt.json` (`READY_FOR_COMMIT_BINDING`)
- H8 binding failure: `h8-binding-result.json` (`BLOCKED_POST_COMMIT_SOURCE_BINDING` / `archive_blob_bytes_mismatch`)
- Commits: implementation `1031b79`, docs `090f39b`, discuss `1d9e7ba`
</phase_requirements>

## Summary

Phase 6 is an authorized clean-room closure, not a greenfield product feature. Authority is `e52c1b5:spec/new-phase.md` (`fork/v1.1`). Fixed baseline is `35227e0` (tree `fed171af`, source-context `dcf73073…`). Prior work at `1031b79` already closed the harness acceptance surface (H1–H7): staged launcher actions, project/image/volume isolation, materializer UUIDv4 authority, application-owned 0/14→14/14 schema bootstrap, and the frozen offline matrix (50 harness / 80 Phase5 / 413 union / 115 combined, Ruff/Pyright/compile green). Execution stopped truthfully at H8: `git archive` produced inventory-complete (733/733) but EOL-transformed archives (634 blob mismatches), classification `BLOCKED_POST_COMMIT_SOURCE_BINDING`.

Remaining critical path is narrow and ordered: (1) fix-forward raw-Git-exact archive materialization (prefer `ls-tree`/`cat-file` over `git archive`); (2) re-run frozen matrix against that archive; (3) build source-bound image from the passing archive only; (4) R0–R3 clean-room runtime; (5) exactly one final canary under the irreversible identity freeze; (6) sanitized final report. Catalog-v2 domain contracts must not change. Stale ROADMAP/REQUIREMENTS text that forbids real canary (`SAFE-02`, “Phase 6 out of scope”) is superseded for this phase by `e52c1b5` + CONTEXT.md.

**Primary recommendation:** Plan fix-forward archive binding first (no amend of `1031b79`), gate image/runtime/canary behind exact archive+matrix proof, reuse existing launcher/materializer/bootstrap/runner without contract changes, preserve all dirty user state.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| RED/GREEN acceptance tests | Local host / pytest | — | Offline contract before any Docker |
| Raw-Git exact archive + context hash | Local host / Git plumbing | — | Authority is blob bytes, not checkout |
| Source commit (task-owned only) | Local Git | — | No remote mutation |
| Source-bound image build | Docker daemon (local) | Dockerfile.standalone | Image from exact archive only |
| Clean-room Compose project/volumes | Docker Compose | launcher argv | Isolation authority |
| UUIDv4 namespace materialization | Host materializer | ignored authority files | Fingerprint-only exposure |
| Schema 0/14→14/14 bootstrap | Container one-shot + raw Neo4j driver | `CatalogNeo4jStore` | App-owned, no Graphiti driver |
| MCP readiness (28 tools / status / capabilities) | MCP container | launcher R3 | Zero-arg capabilities only |
| Final canary Gates 0–10 | `run_catalog_canary_batch.py` against live MCP | Neo4j clean-room | Irreversible after ID allocation |
| Evidence / final report | Host filesystem (sanitized) | — | Contiguous ledgers; no secrets |
| Historical Docker / live groups | **Untouched** | — | Preservation axis |

## Standard Stack

### Core

| Library / Tool | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| Python | 3.12 host / 3.11 image | Runtime | Project pin `>=3.10,<4`; images 3.11-slim-bookworm |
| pytest + pytest-asyncio | project lock | RED/GREEN matrix | Existing MCP suite |
| Git | 2.52.0.windows.1 | Blob authority, commits | Raw `cat-file` / `ls-tree` for exact bytes |
| Docker Engine | 29.4.3 | Image + Compose | Local daemon present |
| Neo4j image | 5.26.0 (local tag present) | Clean-room graph | Spec Neo4j 5.26+ |
| uv | 0.11.29 host; 0.8.15 in Dockerfile | Env / image build | Project standard |
| neo4j Python driver | `>=5.26.0` (locked) | Raw bootstrap executor | Existing `catalog_schema_bootstrap.RawNeo4jExecutor` |
| Pydantic v2 | project lock | Request contracts | Untouched domain models |
| mcp FastMCP | `>=1.27.2,<2` | Tool surface | Existing server |

### Supporting

| Asset | Path | When to Use |
|-------|------|-------------|
| Launcher | `scripts/run_catalog_canary_launcher.py` | R0–R3 staged actions only |
| Runner | `scripts/run_catalog_canary_batch.py` | Final canary Gates 0–10 |
| Materializer | `scripts/materialize_catalog_local_config.py` | Clean-room UUIDv4 authority |
| Bootstrap | `mcp_server/src/services/catalog_schema_bootstrap.py` | 0/14→14/14 |
| Authority hashing | `scripts/catalog_authority_hashing.py` | `git cat-file blob` exact bytes |
| Manifest contract | `scripts/catalog_canary_manifest_contract.py` | 22-field live manifest |
| Compose base + override | `mcp_server/docker/docker-compose-neo4j.yml` + `.catalog-local.override.yml` | Project-scoped resources |
| Production Dockerfile | `mcp_server/docker/Dockerfile.standalone` | Source-bound image |
| Canary prompt | `graphiti_mcp_phase6_canary_agent_prompt_en.md` | Gate contract |
| Prior evidence | `.planning/quick/260722-9s8-…/evidence/` | Resume, do not rewrite |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `git cat-file`/`ls-tree` archive | `git archive` | **Rejected** — H8 proved EOL transform on Windows/`core.autocrlf=true` |
| Retag prior `phase6-35227e0…` image | Rebuild from new archive | Spec forbids retag workaround |
| Generic Compose CLI wrapper | Typed launcher actions | Spec forbids arbitrary passthrough |
| Graphiti `Neo4jDriver` for bootstrap | Raw async driver | Spec forbids; existing code already raw |
| Second canary / cleanup after fail | Leave stack intact | Spec irreversible + preserve |

**Installation:** none new. Reuse locked `mcp_server` / root deps. No package adds.

**Version verification:** Docker 29.4.3, Python 3.12.10, uv 0.11.29, Git 2.52.0, Neo4j image 5.26.0 present — probed this session. `[VERIFIED: local environment]`

## Package Legitimacy Audit

No external packages to install for this phase.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — | — | — | — | — | — | none |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
[Operator / Phase-6 plan]
        |
        v
[RED/GREEN pytest matrix (host)] ----fail----> fix-forward loop
        |
       pass
        v
[Stage task-owned paths] -> [local candidate commit] --no push/amend-->
        |
        v
[Raw-Git exact archive builder]
   ls-tree -r + cat-file blob  == byte-equal members
        |
        +--> source-context SHA-256
        +--> re-run frozen matrix on archive tree
        |
       pass
        v
[docker build -f Dockerfile.standalone from archive]
   tag: graphiti-mcp:phase6-cleanroom-<short>-bound
   labels: revision=commit, source-context=hash
        |
        v
[Launcher R0] render + prove resources ABSENT
        |
        v
[Launcher R1] materialize UUIDv4 (fingerprint only) + Neo4j only
        |
        v
[Launcher R2] bootstrap once: 0/14 -> ensure* -> 14/14
        |
        v
[Launcher R3] MCP only; exact image ID; registry/status/capabilities
        |
        v
 *** CANARY IDENTITY FREEZE ***
        |
        v
[Runner Gates 0-10] dry_run -> prepare -> commit -> verify/search
        |
        v
[Sanitized final report]  leave stack+volumes intact
```

### Recommended Project Structure (no new top-level packages)

```
scripts/
├── run_catalog_canary_launcher.py   # R0-R3 staged actions
├── run_catalog_canary_batch.py      # final canary
├── materialize_catalog_local_config.py
├── catalog_authority_hashing.py     # cat-file authority
├── catalog_canary_manifest_contract.py
└── bootstrap_catalog_v2_schema.py   # thin wrapper
mcp_server/
├── src/services/catalog_schema_bootstrap.py
├── docker/Dockerfile.standalone
├── docker/docker-compose-neo4j.yml
├── docker/docker-compose-neo4j.catalog-local.override.yml
└── tests/test_catalog_canary_scripts.py
    tests/test_catalog_schema_bootstrap.py
graphiti_mcp_phase6_canary_agent_prompt_en.md
.planning/phases/06-.../             # plans, research, validation, reports
.planning/quick/260722-9s8-.../      # immutable prior evidence
```

### Pattern 1: Raw-Git-exact archive (required fix-forward)

**What:** Materialize a filesystem tree or tar whose every regular-file member equals `git cat-file blob <commit>:<path>` bytes; modes/symlinks from `ls-tree -r`; no `core.autocrlf` / checkout smudge / `git archive` export filters. [VERIFIED: H8 failure + `catalog_authority_hashing.git_blob_bytes`]

**When to use:** P6-BIND-02..05; any image build context.

**Example approach (prescriptive):**
```python
# Prefer plumbing, not git archive (H8: 634 EOL mismatches).
# 1) git ls-tree -r --format='%(objectmode) %(objecttype) %(objectname) %(path)' <commit>
# 2) for blob: git cat-file blob <objectname> -> write path with exact bytes
# 3) for symlink: cat-file blob target bytes as link text
# 4) refuse export-ignore/export-subst surprises by comparing path sets to tree
# 5) context hash = versioned canonical digest over (path, mode, raw_sha256) rows
```

### Pattern 2: Typed staged launcher

**What:** Fixed `PUBLIC_ACTIONS = ('render','neo4j','bootstrap','mcp','status','inspect')`; ordered mutating prefix; structured argv; `shell=False`; ambient env scrub. [VERIFIED: launcher source]

**When to use:** All runtime activation.

### Pattern 3: Irreversible canary freeze

**What:** Before run/group/control/batch IDs: fix-forward OK. After any allocation: freeze source/image/runtime; one canary; no retry/cleanup. [CITED: e52c1b5 §17]

### Anti-Patterns to Avoid
- **`git archive` as byte authority:** H8 proved EOL transform. Use plumbing.
- **Amending `1031b79` or rewriting 9s8 evidence:** Forbidden; fix-forward only.
- **Retagging old bound image:** Spec forbids workaround.
- **Changing Catalog-v2 domain contracts to fix orchestration:** Spec §5.
- **Proactive embedding probe at readiness:** Spec §16; prepare is first proof.
- **Global Docker prune / historical down -v:** Spec §18.
- **Second canary or graph cleanup after fail:** Spec §17–18.
- **Committing dirty `config-docker-neo4j.yaml`:** Preserve unstaged.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exact blob bytes | Custom EOL normalizer in archive | `git cat-file blob` | Authority is stored object |
| UUIDv4 namespace | ad-hoc uuid write | `materialize_clean_room` | Fingerprint + exclusive create |
| Schema bootstrap | Ad-hoc Cypher / docker exec | `catalog_schema_bootstrap.bootstrap` | Exact 0/14→14/14, no retry |
| Compose staging | Shell compose scripts | Launcher allow-list | Injection + order safety |
| Canary protocol | New runner | `run_catalog_canary_batch` + prompt | 22-field + Gates 0–10 already hardened |
| Image base | New Dockerfile | `Dockerfile.standalone` | Existing OCI labels + uv pin |
| Authority digests | Ad-hoc hashlib loops | `catalog_authority_hashing` | Dual raw + LF digests |

**Key insight:** Phase 6 remaining work is orchestration/binding, not catalog domain. Reuse hardened substrate; only the archive path is known-broken.

## Common Pitfalls

### Pitfall 1: `git archive` / checkout EOL
**What goes wrong:** Archive members ≠ Git blobs; context hash drifts; image not source-bound.
**Why:** Windows `core.autocrlf=true` (verified this host); `git archive` applies export/checkout conversion.
**How to avoid:** Plumbing-only materializer; assert every member `sha256(member)==sha256(cat-file blob)`.
**Warning signs:** Inventory match with nonzero `blob_mismatch_count` (H8 pattern).

### Pitfall 2: Crossing canary freeze then “fix”
**What goes wrong:** Second canary, rebuilt image, or volume wipe voids classification.
**How to avoid:** Explicit plan gate before ID allocation; after allocation only canary classifications.

### Pitfall 3: Dirty protected config leakage
**What goes wrong:** Staging `config-docker-neo4j.yaml` or baking into image.
**How to avoid:** Explicit path deny-list in stage/build; re-hash before commit.

### Pitfall 4: Treating missing OPENAI_API_KEY as hard block
**What goes wrong:** False `HARD_BLOCKED_*`.
**How to avoid:** Spec §4/§19; local proxy; prepare is embedding proof; auth fails map to FAILED_*.

### Pitfall 5: Re-running H1–H7 from scratch
**What goes wrong:** Wasted cycles; risk of rewriting historical evidence.
**How to avoid:** Reuse 9s8 receipts; only re-run matrix after archive fix or code change.

### Pitfall 6: Stale planning text vs live authorization
**What goes wrong:** Planner enforces SAFE-02 “no real canary” and never finishes Phase 6.
**How to avoid:** Prefer `e52c1b5` + CONTEXT over pre-canary ROADMAP wording for this phase only.

## Code Examples

### Exact Git blob read (existing)
```python
# Source: scripts/catalog_authority_hashing.py
def git_blob_bytes(root: Path, relative: str, revision: str = 'HEAD') -> bytes:
    result = subprocess.run(
        ['git', 'cat-file', 'blob', f'{revision}:{relative}'],
        cwd=root,
        capture_output=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f'Git authority blob is unavailable: {relative}')
    return result.stdout
```

### Launcher action surface (existing)
```python
# Source: scripts/run_catalog_canary_launcher.py
PUBLIC_ACTIONS = ('render', 'neo4j', 'bootstrap', 'mcp', 'status', 'inspect')
MUTATING_ACTIONS = PUBLIC_ACTIONS[:4]
```

### Compose image binding (existing)
```yaml
# Source: mcp_server/docker/docker-compose-neo4j.yml
image: ${GRAPHITI_MCP_IMAGE:-thienpvt/mem0:graphiti-mcp}
```

### Bootstrap contract (existing)
```python
# Source: mcp_server/src/services/catalog_schema_bootstrap.py
# preflight: matched==0 expected==14; postflight: matched==14 expected==14
# one pre inspect, three ensure groups, one post inspect; no retry
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 6 “out of scope” / SAFE-02 ban | Authorized iterative TDD + one clean-room canary | `e52c1b5` (2026-07-22) | Real canary is in-scope for this phase only |
| Forced project `graphiti-catalog-local` only | Explicit clean-room project + legacy default | `1031b79` | Isolation authority |
| Hardcoded MCP image | `GRAPHITI_MCP_IMAGE` with legacy default | `1031b79` | Source-bound image selectable |
| `git archive` binding | **Must become** raw-Git plumbing archive | Remaining after H8 | Unblocks image/runtime |
| Retag prior image | Forbidden; rebuild from archive | Spec §11 | True source binding |

**Deprecated/outdated:**
- ROADMAP claim “Phase 6 carries no requirement IDs” — superseded by this phase’s P6-* IDs.
- REQUIREMENTS SAFE-02 as absolute ban on real canary — superseded for authorized Phase 6 execution (historical Phase 0–5 still correct under SAFE-02).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No new PyPI packages required | Standard Stack | Low — can add only if archive tooling needs stdlib-insufficient deps |
| A2 | `Dockerfile.standalone` is the production Dockerfile intended by Spec §11 | Image | Medium — if operators expected combined FalkorDB image, label/build path differs |
| A3 | Source-context hash algorithm matches prior phase6 tooling (canonical path/mode/blob digest) | BIND | Medium — must match prior bound images’ formula when recomputed; verify against `dcf73073…` on baseline |
| A4 | Local OpenAI-compatible proxy remains available for prepare embeddings | Canary | Medium — maps to FAILED_* not hard-block if auth fails |
| A5 | Protected config content drift (`815d00fe`→`bf258b96`) is user-owned and must stay unstaged | PRES | Low if preserved; high if staged |

## Open Questions

1. **Exact source-context hash recipe for new commits**
   - What we know: baseline context `dcf73073…`; H8 raw-git context `051c0795…` for `1031b79`.
   - What's unclear: single shared function vs ad-hoc script used in 9s8 operation.
   - Recommendation: locate prior context hasher in quick evidence/scripts; pin one implementation in fix-forward; golden against baseline.

2. **Whether archive materializer lives in-repo or operator-only**
   - Discretion allows either; tests should pin byte-equality behavior.
   - Recommendation: small pure helper under `scripts/` + unit tests (TDD), used by bind step.

3. **OCI custom source-context label name**
   - Dockerfile has `org.opencontainers.image.revision`; Spec also wants source-context label.
   - Recommendation: add explicit label key consistent with prior bound images if already used; else document chosen key in report.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Git | Archive binding, commits | ✓ | 2.52.0.windows.1 | — |
| Python | Tests, scripts | ✓ | 3.12.10 | — |
| uv | MCP tests/image | ✓ | 0.11.29 | — |
| pytest | Matrix | ✓ | on PATH | — |
| Docker Engine | Image + runtime | ✓ | 29.4.3 | — |
| Neo4j image | Clean-room | ✓ | 5.26.0 local | pull never once bound (must be local) |
| Prior bound image | Historical only | ✓ | `graphiti-mcp:phase6-35227e0a2c69-bound` | Do not retag |
| core.autocrlf | EOL risk | true | — | Plumbing archive avoids |
| Public OPENAI_API_KEY | Not required | n/a | — | Local proxy / prepare proof |
| Kubernetes | Forbidden | n/a | — | Never use |

**Missing dependencies with no fallback:** none identified for planning.

**Missing dependencies with fallback:** public OpenAI key (not required).

## Validation Architecture

> `workflow.nyquist_validation` is true in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-asyncio) via uv / project locks |
| Config file | `pytest.ini`, `mcp_server/pytest.ini`, `pyproject.toml` |
| Quick run command | `uv run --project mcp_server --frozen pytest mcp_server/tests/test_catalog_canary_scripts.py mcp_server/tests/test_catalog_schema_bootstrap.py -q` |
| Full suite command | Focused harness + Phase5 compatibility + catalog union + direct runner/builder + Ruff + Pyright (mirror H7 matrix) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| P6-HARN-01..14 | Project/image/volume/namespace/order/safety | unit | `pytest mcp_server/tests/test_catalog_canary_scripts.py -k "clean_room or launcher or materializer or compose" -q` | ✅ |
| P6-HARN-05 | Schema 0/14→14/14 no retry | unit | `pytest mcp_server/tests/test_catalog_schema_bootstrap.py -q` | ✅ |
| P6-HARN-16 | 22-field manifest | unit | matrix check in H7 / canary scripts | ✅ |
| P6-TDD-01..04 | RED/GREEN + full matrix | unit/integration offline | H7 command set | ✅ evidence |
| P6-BIND-02..05 | Raw-Git archive byte equality + matrix on archive | unit + offline | **Wave 0 gap** — add tests asserting member==`cat-file` blob | ❌ Wave 0 |
| P6-IMG-01..05 | Image labels, no secrets, no pull | offline inspect | plan-time scripts; not yet automated suite | ❌ Wave 0 / operator |
| P6-RT-R0..R3 | Runtime stages | live Docker | launcher actions; gated after image | ⚠️ partial unit only |
| P6-CAN-01..06 | Final canary Gates 0–10 | live | `run_catalog_canary_batch` once after freeze | ✅ runner exists; live not yet run |
| P6-SAFE-01..02 | No prune/historical mutation | policy unit + operator ledger | existing reject tests + evidence | ✅ partial |
| P6-PROV-01..03 | No LLM; auth classification | unit + live canary | runner classification paths | ✅ offline; live remaining |
| P6-REPT-01 | Sanitized report | offline schema check | final report writer | ⚠️ plan must define artifact path |

### Sampling Rate
- **Per task commit:** focused canary/bootstrap tests + new archive tests
- **Per wave merge:** H7-equivalent frozen matrix
- **Phase gate:** archive equality + matrix on archive + image inspect + R0–R3 proofs + single canary classification + final report

### Wave 0 Gaps
- [ ] Archive materializer + tests: every tree path byte-equals `git cat-file blob <commit>:<path>`; modes/symlinks; no extras/missing; context hash stable
- [ ] Explicit test that `git archive` is **not** used as authority (or that wrapper fails closed if it transforms)
- [ ] Image-build secret/config exclusion checklist automated where feasible
- [ ] VALIDATION.md generation from this map during plan-phase

*(Existing H1–H7 harness tests remain authoritative offline coverage for P6-HARN-* already closed.)*

## Security Domain

> `security_enforcement` enabled; ASVS level 1.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial | Local proxy token never logged/committed/imaged; no public OpenAI key required |
| V3 Session Management | no | N/A |
| V4 Access Control | yes | group_id isolation; protected groups never queried; clean-room project isolation |
| V5 Input Validation | yes | Project name allowlist; fixed Compose argv; no shell; strict catalog models unchanged |
| V6 Cryptography | yes | UUIDv4 for namespace; SHA-256 fingerprints; UUIDv5 domain identity unchanged; never expose raw namespace |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Shell injection via project/image args | Tampering | Structured argv, allowlists, no shell |
| Secret leakage in logs/image/evidence | Information Disclosure | Sanitization; image exclude list; report deny-list |
| Historical volume/data wipe | Destruction | No prune; no historical down -v; prove targets before any disposable cleanup |
| Cypher injection via client labels | Tampering | Unchanged catalog allowlists; bootstrap uses fixed store statements |
| Identity authority takeover | Spoofing | Server UUIDv5 only; caller UUIDs never authority |
| Canary retry after partial commit | Tampering / Elevation | Freeze + no commit retry + read-only reconcile |
| EOL-transformed “source-bound” image | Spoofing | Raw-Git archive equality gate before build |
| Protected dirty config commit | Information Disclosure | Explicit preserve/unstage |

## Project Constraints (from CLAUDE.md)

- Additive MCP/catalog behavior only; preserve legacy tools.
- Neo4j 5.26+ first; no unsupported multi-backend claims.
- Server-derived UUIDv5; `GRAPHITI_CATALOG_UUID_NAMESPACE` immutable.
- Never interpolate unvalidated client labels/properties into Cypher.
- Writes return only after commit/rollback; atomic batches full rollback.
- Embeddings before domain write transaction; embedding failure ⇒ no partial write.
- Tests/dev isolation: historical `oracle-catalog-tool-test`; Phase 6 clean-room uses **new** canary identities only — never historical `oracle-catalog-v2`.
- Logging: counts/IDs only; no payloads/credentials/source text.
- Ruff line length 100, single quotes; Pyright basic for mcp_server.
- No deployment, live historical-group mutation, full ingest, graph clear, or existing-data deletion.
- GSD workflow for edits; research/planning artifacts only this session.

## Sources

### Primary (HIGH confidence)
- `git show e52c1b5:spec/new-phase.md` — full acceptance contract (749 lines) `[VERIFIED: git object e52c1b5]`
- `.planning/phases/06-…/06-CONTEXT.md` — locked decisions `[VERIFIED: worktree file]`
- `.planning/quick/260722-9s8-…/{260722-9s8-SUMMARY.md,operation-report.md,evidence/*}` — H1/H7/H8 receipts `[VERIFIED: worktree files]`
- `scripts/run_catalog_canary_launcher.py`, `catalog_authority_hashing.py`, `materialize_catalog_local_config.py`, `catalog_schema_bootstrap.py`, Compose/Dockerfile, canary prompt — live implementation `[VERIFIED: codebase]`
- `git show 1031b79 --stat`, `git rev-parse 35227e0^{tree}` — commit/tree identity `[VERIFIED: git]`

### Secondary (MEDIUM confidence)
- Local Docker image list / tool versions — environment probe this session
- Stale ROADMAP/REQUIREMENTS Phase-6 wording — read and explicitly superseded by e52c1b5

### Tertiary (LOW confidence)
- Exact historical source-context hash function internals not re-derived line-by-line this session (A3)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — existing scripts/images/tools verified
- Architecture: HIGH — H1–H7 closed; H8 defect isolated; R0–canary path specified
- Pitfalls: HIGH — H8 EOL failure is empirical; freeze/safety from authoritative spec
- Remaining runtime/canary: MEDIUM until live execution (by design not run during research)

**Research date:** 2026-07-22
**Valid until:** 2026-08-21 (stable contracts; re-verify if baseline/spec commit moves)

## Contradiction Resolution (stale pre-Phase-6 text)

| Stale claim | Location | Resolution |
|-------------|----------|------------|
| Phase 6 out of scope / no requirement IDs | ROADMAP, STATE | Superseded: Phase 6 authorized by `e52c1b5`; use P6-* IDs |
| SAFE-02 never execute real canary | REQUIREMENTS | Superseded for this authorized operation only; still true for Phases 0–5 artifacts |
| `canary_executed=false` forever | STATE/REPT-01 history | Historical Phase 5 truth; Phase 6 may set terminal canary classification after freeze |
| Stop before Phase 6 | STATE pending todos | Superseded by discuss CONTEXT ready-for-planning |

Planner must treat `e52c1b5` + CONTEXT as higher authority than pre-canary milestone freezes when they conflict.
