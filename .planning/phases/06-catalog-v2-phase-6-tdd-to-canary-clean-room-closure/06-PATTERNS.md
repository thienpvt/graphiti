# Phase 6: Catalog-v2 TDD-to-Canary Clean-Room Closure - Pattern Map

**Mapped:** 2026-07-22
**Files analyzed:** 14 (new/modified/operator artifacts)
**Analogs found:** 12 / 14
**Authority:** `e52c1b5:spec/new-phase.md`; resume from `1031b79` + H8 `BLOCKED_POST_COMMIT_SOURCE_BINDING`
**Do not rewrite:** `.planning/quick/260722-9s8-catalog-v2-phase-6-clean-room-harness-cl/evidence/*`
**User-owned dirty (never stage):** `mcp_server/config/config-docker-neo4j.yaml` (current worktree dirty; H8 recorded blob `815d00fe…`; RESEARCH notes drift risk)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/catalog_raw_git_archive.py` *(new helper; name discretionary)* | utility | file-I/O / transform | `scripts/catalog_authority_hashing.py` | role-match |
| archive unit tests in `mcp_server/tests/test_catalog_canary_scripts.py` *(or sibling)* | test | transform | `mcp_server/tests/test_catalog_phase2_gate_runner.py` (`test_raw_git_*`) + existing canary harness tests | exact/role |
| fix-forward commit of harness sources (if archive helper needs code) | config/source | request-response | commit `1031b79` task-owned path set | exact |
| source-bound image build operator path | config | file-I/O / batch | `mcp_server/docker/Dockerfile.standalone` + `mcp_server/docker/build-standalone.sh` | role-match |
| OCI label / inspect receipt | utility | transform | Dockerfile LABEL `org.opencontainers.image.revision`; workflow `publish-mcp-image.yml` VCS_REF | partial |
| launcher R0–R3 execution | utility / route | request-response | `scripts/run_catalog_canary_launcher.py` | exact |
| materializer clean-room authority | utility | file-I/O | `scripts/materialize_catalog_local_config.py` `materialize_clean_room` | exact |
| schema bootstrap 0/14→14/14 | service | request-response | `mcp_server/src/services/catalog_schema_bootstrap.py` | exact |
| Compose project/image/volumes | config | request-response | `mcp_server/docker/docker-compose-neo4j.yml` + `.catalog-local.override.yml` | exact |
| final canary Gates 0–10 | utility | request-response / CRUD | `scripts/run_catalog_canary_batch.py` + `graphiti_mcp_phase6_canary_agent_prompt_en.md` | exact |
| 22-field live manifest | model / contract | transform | `scripts/catalog_canary_manifest_contract.py` | exact |
| sanitized ledgers / final report | config / report | transform | 9s8 `operation-report.md` + `h*-*.json`; Phase5 `05-IMPLEMENTATION-REPORT.json` | role-match |
| frozen offline matrix commands | test | batch | H7 receipt + RESEARCH Validation Architecture | exact |
| protected-path deny list (stage/build) | middleware / policy | request-response | launcher `AUTHORITY_ENV` scrub + materializer exclusive create | role-match |

## Pattern Assignments

### 1. Raw-Git blob authority + exact archive (P6-BIND-02..05) — **REMAINING ROOT DEFECT**

**Analog:** `scripts/catalog_authority_hashing.py`

**Imports / dual-digest pattern** (lines 1–44, 80–122):
```python
def sha256_raw_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git_blob_bytes(root: Path, relative: str, revision: str = 'HEAD') -> bytes:
    result = subprocess.run(
        ['git', 'cat-file', 'blob', f'{revision}:{relative}'],
        cwd=root, capture_output=True, shell=False, check=False,
    )
    if result.returncode != 0:
        raise ValueError(f'Git authority blob is unavailable: {relative}')
    return result.stdout

def authority_bytes(root, relative, *, mode: str, revision: str = 'HEAD') -> bytes:
    if mode == 'git':
        return git_blob_bytes(root, relative, revision)
    if mode == 'archive':
        return authority_file_bytes(root, relative)  # no symlink traversal
    raise ValueError('source authority mode must be git or archive')

def authority_digest(data: bytes) -> dict[str, str]:
    return {'raw_sha256': sha256_raw_bytes(data), 'lf_sha256': sha256_canonical_text_bytes(data)}
```

**H8 failure recipe (do not reuse `git archive` as authority):**
- Evidence: `.planning/quick/260722-9s8-…/evidence/h8-binding-result.json`
- Classification: `BLOCKED_POST_COMMIT_SOURCE_BINDING` / `archive_blob_bytes_mismatch`
- Inventory OK: 733/733; `blob_mismatch_count`: 634; context raw-git `051c0795…` ≠ archive `156ba0ce…`
- Cause: `git archive` + host `core.autocrlf=true` EOL transform

**Prescriptive materializer (from RESEARCH; implement via plumbing only):**
```text
git ls-tree -r --format='%(objectmode) %(objecttype) %(objectname) %(path)' <commit>
for blob: git cat-file blob <objectname>  → write path with exact bytes (mode 100644/100755)
for symlink: cat-file target bytes as link text
refuse extras/missing vs tree path set
member assert: sha256(member_bytes) == sha256(git cat-file blob)
context hash: versioned canonical digest over sorted (path, mode, raw_sha256) rows
golden baseline: 35227e0 → source-context dcf73073443be37b777fc7feef124133be3d9ee305696e84042d5631125ed92f
```

**Related test analog** — `mcp_server/tests/test_catalog_phase2_gate_runner.py` lines 404–438:
- `test_raw_git_lf_is_committed_authority` proves `cat-file` bytes are LF authority even when worktree has CRLF
- `_committed_or_archive_bytes` pattern: prefer Git object over checkout

**Wave-0 gap:** no in-repo archive materializer yet; only hashing primitives. New helper + tests required before image/runtime.

**Anti-pattern:** using `canonical_text_bytes_lf` as *archive membership* authority. LF digest is for text contracts; **source-context / image binding uses raw blob SHA-256**.

---

### 2. Candidate commit / archive verification (P6-BIND-01, P6-BIND-06)

**Analog evidence recipes:** 9s8 `operation-report.md`, `h8-binding-result.json`, commit `1031b79`

**Commit recipe (fix-forward only):**
```text
# stage ONLY task-owned paths (mirror 1031b79 scope style)
# NEVER: push, merge, rebase, amend, tag, reset, checkout, restore, stash
# NEVER stage: mcp_server/config/config-docker-neo4j.yaml, .env, runtime evidence, .planning/quick/260722-9s8-…/evidence
git commit -m "…"   # new commit; parent of next candidate is previous candidate or 35227e0 line
```

**Post-commit verify checklist (H8 schema):**
| Field | Meaning |
|-------|---------|
| `commit` / `parent` / `tree` | `git rev-parse` |
| `git_blob_count` vs `archive_member_count` | membership |
| `missing_count` / `extra_count` | path set equality |
| `blob_mismatch_count` | must be 0 (raw bytes) |
| `raw_git_context_sha256` | equals `archive_context_sha256` |
| `image_build_count` / `runtime_start_count` / `canary_executed` | stay 0 until gates pass |

**Changed-path audit pattern from H8:** split `changed_exact_paths` vs `changed_mismatch_paths` for diagnosis.

---

### 3. Production Dockerfile / OCI labels / secret exclusion (P6-IMG-01..05)

**Analog Dockerfile:** `mcp_server/docker/Dockerfile.standalone` lines 1–68

**Context is repo root** (not `mcp_server/`):
```dockerfile
COPY pyproject.toml README.md LICENSE ./
COPY graphiti_core/ ./graphiti_core/
WORKDIR /app/mcp
COPY mcp_server/pyproject.toml mcp_server/uv.lock ./
COPY mcp_server/main.py ./
COPY mcp_server/src/ ./src/
COPY mcp_server/config/ ./config/
ARG VCS_REF
LABEL org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Graphiti MCP Server (Standalone)" ...
```

**Analog build driver:** `mcp_server/docker/build-standalone.sh` lines 13–27:
```bash
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
VCS_REF=$(git rev-parse --short HEAD …)
docker build \
  --build-arg MCP_SERVER_VERSION=… \
  --build-arg BUILD_DATE=… \
  --build-arg VCS_REF="${VCS_REF}" \
  -f …/Dockerfile.standalone \
  -t … \
  "${REPO_ROOT}"
```

**Phase 6 deltas (spec):**
- Build **only from exact passing archive tree**, not dirty worktree
- Tag: `graphiti-mcp:phase6-cleanroom-<short>-bound` (not retag `phase6-35227e0a2c69-bound` / `sha256:994e1d13…`)
- `VCS_REF` / revision label = **full final commit**, not short-only if inspect requires full
- Add **source-context** label = canonical context SHA-256 (key not yet in Dockerfile — open Q3; document chosen key)
- `--pull never`; no push; no retag historical image
- Exclude from context/stage: namespace authority, `config-docker-neo4j.yaml` (user), `.env`, proxy tokens, `.planning/**` evidence, secrets

**Inspect capture pattern:**
```text
docker image inspect <tag> → Id, RepoTags, Config.Labels, RootFS
hash: Dockerfile, build log, archive tree, image Id
```

**Compose image binding analog** — `mcp_server/docker/docker-compose-neo4j.yml:25`:
```yaml
image: ${GRAPHITI_MCP_IMAGE:-thienpvt/mem0:graphiti-mcp}
```
Launcher injects `GRAPHITI_MCP_IMAGE` via `compose_env` (`run_catalog_canary_launcher.py:67-71`).

---

### 4. Typed launcher R0–R3, materializer, bootstrap, MCP readiness

#### 4a. Launcher surface — **exact analog**

**File:** `scripts/run_catalog_canary_launcher.py`

```python
PUBLIC_ACTIONS = ('render', 'neo4j', 'bootstrap', 'mcp', 'status', 'inspect')
MUTATING_ACTIONS = PUBLIC_ACTIONS[:4]  # ordered prefix only
STATE_SCHEMA = 'catalog-clean-room-launcher-state-v1'
```

| Stage | Action | Required proof |
|-------|--------|----------------|
| R0 | `render` | exclusive state create; effective Compose; resources absent later at neo4j |
| R1 | `neo4j` | `_require_all_absent` then `up --no-build --pull never -d neo4j` |
| R2 | `bootstrap` | MCP absent; local image ID; stdout classification `PASSED_SCHEMA_BOOTSTRAP` + pre 0/14 + post 14/14 |
| R3 | `mcp` | prior actions `['render','neo4j','bootstrap']`; `--no-deps`; `_inspect_mcp_image` == `expected_image_id` |

**Structured argv authority** — `scripts/run_catalog_canary_batch.py` `compose_argv` / `_compose_suffix` (≈2801–2838):
```python
'neo4j': ['up', '--no-build', '--pull', 'never', '-d', 'neo4j'],
'bootstrap': ['--profile', 'catalog-bootstrap', 'run', '--no-deps', '--no-build', '--pull', 'never', '--rm', 'catalog-bootstrap'],
'mcp': ['up', '--no-deps', '--no-build', '--pull', 'never', '-d', 'graphiti-mcp'],
```
Always `shell=False`. `validate_execution_command` rejects non-allowlisted argv.

**Ambient scrub:** `compose_env` strips `AUTHORITY_ENV`, all `COMPOSE_*`, `*UUID_NAMESPACE*` before re-injecting fixed keys (launcher:59–81).

**Resource identities** — `compose_resource_identities` (batch:2722–2730):
```python
f'{project}_neo4j_data', f'{project}_neo4j_logs', f'{project}_default',
f'{project}-neo4j-1', f'{project}-graphiti-mcp-1', f'{project}-catalog-bootstrap-1'
```

**Absence gate** — launcher `_require_all_absent` (296–314).

**Image ID gate** — `verify_observed_image_id` (84–90); clean-room requires `IMAGE_ID_RE` sha256-prefixed expected id (`_validate_image` batch:2741–2749).

**Sanitized stdout** — `_sanitized_output` (496–512): only `Name/Service/State/Health/Image/Project`.

**Tests to reuse (do not re-author H1–H7):**
- `test_launcher_public_actions_and_fixed_compose_argv`
- `test_launcher_clean_room_state_order_and_no_docker_before_prerequisite`
- `test_launcher_sanitizes_ambient_authority`
- `test_clean_room_project_contract_and_launcher_options`
- `test_compose_override_isolated_and_bootstrap_uses_project_environment`
File: `mcp_server/tests/test_catalog_canary_scripts.py` ≈1672–1805.

#### 4b. Materializer UUIDv4 — **exact analog**

**File:** `scripts/materialize_catalog_local_config.py` `materialize_clean_room` (62–82)

```python
COMPOSE_PROJECT_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')
# data_volume must be f'{project}_neo4j_data'
# exclusive create: output/authority must not exist
generated = uuid.uuid4()
# authority file keys exactly: project, data_volume, namespace
return namespace_fingerprint(generated)  # sha256(b'graphiti.catalog.nsfp.v1|'+bytes)[:16]
```

Launcher `_authority()` re-derives fingerprint only; never prints raw namespace (163–190).

#### 4c. Schema bootstrap — **exact analog**

**File:** `mcp_server/src/services/catalog_schema_bootstrap.py`

```python
CATALOG_V2_REQUIRED_CONSTRAINT_COUNT = 14
METHODS = (
    ('identity', 'ensure_uuid_uniqueness_constraints'),
    ('prepared_plan', 'ensure_plan_schema'),
    ('evidence_manifest', 'ensure_evidence_manifest_schema'),
)
# RawNeo4jExecutor — neo4j.AsyncDriver only; graphiti_driver_constructed=False
# preflight matched==0; postflight matched==14; retry_count always 0
# classifications: PASSED_SCHEMA_BOOTSTRAP | FAILED_SCHEMA_PRECONDITION | …
```

Launcher hard-checks bootstrap JSON (414–423). Thin CLI wrapper: `scripts/bootstrap_catalog_v2_schema.py`.

#### 4d. MCP readiness (R3 / canary preflight) — **exact analog**

**File:** `scripts/run_catalog_canary_batch.py` ≈4048–4101, `evaluate_embedding_readiness` ≈2932–2975

Allowed readiness calls only:
1. Exact 28-tool registry match (`tool_count` must stay 28)
2. `get_status` zero-arg
3. `get_catalog_capabilities` zero-arg

```python
# embeddings.ready may be 'unknown' only with exact openai waiver
# never proactive embedding probe; prepare is first embedding proof
```

Do **not** invent new readiness tools.

---

### 5. Canary runner freeze, exact counts, bounded reconcile, sanitized ledger (P6-CAN-*)

**Analog:** `scripts/run_catalog_canary_batch.py` + `scripts/catalog_canary_manifest_contract.py` + prompt `graphiti_mcp_phase6_canary_agent_prompt_en.md`

**22-field live manifest** — `LIVE_MANIFEST_FIELDS` (contract:3–28). Fail closed if set inequality (`batch:3040`, `3124`).

**Gate sequence (runner main path ≈4153–4439):**
| Gate | Call / check |
|------|----------------|
| 0 | host execution authority digests (override/base/config) before MCP open |
| dry-run | `upsert_catalog_batch` with **only** transport `dry_run=true`; counts 3e/2edge/1src/5ev; zero writes |
| prepare | `prepare_catalog_batch` once — embedding proof |
| commit | `commit_prepared_catalog_batch` token-only once — **no retry** |
| ambiguous commit | `_requires_remote_reconciliation` → read-only reconcile only |
| verify/search | manifest/entity/edge/batch; 5 evidence; 3 entity + 2 fact searches; empty control; controlled replay |
| terminal | `PASSED` / `FAILED_BEFORE_COMMIT` / `FAILED_AFTER_COMMIT` / `BLOCKED` |

**Auth classification:**
```python
# embedding_transport_auth → FAILED_BEFORE_COMMIT or FAILED_AFTER_COMMIT
# never mutate provider/model/endpoint/credential/dimension
```

**Freeze rule (spec, not code flag):** once any of `run_id` / `group_id` / `control_group_id` / `batch_id` allocated → no edit/rebuild/new candidate/retry/reset/graph cleanup/volume delete.

**Sanitized durable report keys** — runner report builder ≈3819–3885, 4404–4439: classification, tool_count, gate map, embedding readiness observed, `dry_run_zero_write_proven`; notes forbid raw tokens/namespace.

**Builder golden fixture path:** `mcp_server/tests/fixtures/accept_tab_sanitized.json` with fixed raw SHA-256 `145f38ed…` (runner + phase2 tests).

---

### 6. GSD Phase 5 / quick-task evidence and final report patterns

**Immutable prior Phase 6 harness evidence (resume only):**
| Artifact | Path |
|----------|------|
| H1 RED | `.planning/quick/260722-9s8-…/evidence/h1-red-receipt.json` |
| H7 full matrix | `…/evidence/h7-full-receipt.json` (`READY_FOR_COMMIT_BINDING`) |
| H8 binding fail | `…/evidence/h8-binding-result.json` |
| Operation report | `…/operation-report.md` |
| Summary | `…/260722-9s8-SUMMARY.md` |
| Commits | impl `1031b79`, docs `090f39b` |

**Phase 5 final report shape analog:**
- `.planning/phases/05-verification-security-compatibility-and-migration-docs/05-IMPLEMENTATION-REPORT.json`
- `05-IMPLEMENTATION-REPORT.md`, `05-GATE-RESULTS.json`, `05-PROOF-PACKAGE.json`
- Plan/summary naming: `05-0N-PLAN.md` / `05-0N-SUMMARY.md`

**Phase 6 report must add (Spec §20 / P6-REPT-01):** baseline hashes, RED/GREEN iterations, matrix, candidate commits, archive+context hashes, image Id/labels, runtime project/volumes (no raw ns), schema 0/14→14/14, readiness, canary gates, terminal classification. Never secrets/raw namespace/prepare token/full env.

**Frozen matrix command skeleton (from RESEARCH / H7):**
```bash
uv run --project mcp_server --frozen pytest \
  mcp_server/tests/test_catalog_canary_scripts.py \
  mcp_server/tests/test_catalog_schema_bootstrap.py -q
# + Phase5 gate suite + catalog union + direct runner/builder + Ruff + Pyright
# After archive fix: re-run complete matrix against materialised archive tree
```

---

## Shared Patterns

### Structured subprocess, no shell
**Source:** launcher `_subprocess` / batch `compose_argv`
**Apply to:** all Docker/Git plumbing
```python
subprocess.run(argv, cwd=ROOT, env=scrubbed, shell=False, check=…, capture_output=True)
```

### Fail-closed exact counts/hashes
**Source:** bootstrap inspections; runner dry-run/manifest; authority digests
**Apply to:** archive membership, schema 0/14|14/14, tool_count=28, live manifest field set

### Fingerprint-only secrets
**Source:** `namespace_fingerprint`; plan token digests (catalog domain, unchanged)
**Apply to:** clean-room authority, evidence, image labels (no raw UUID)

### Fix-forward commits
**Source:** H8 policy + CONTEXT
**Apply to:** archive materializer work; never amend `1031b79`

### Historical preservation axis
**Source:** Spec §18; operation-report “Preserved boundaries”
**Apply to:** never prune/historical `down -v`/retag prior bound image/mutate `oracle-catalog-v2`

### Authority supersession (stale text)
| Stale | Prefer |
|-------|--------|
| REQUIREMENTS SAFE-02 “never real canary” | `e52c1b5` + CONTEXT for this phase only |
| ROADMAP “Phase 6 out of scope” | P6-* IDs in REQUIREMENTS Phase 6 section |
| Phase5 `canary_executed=false` forever | Phase 6 terminal classification after freeze |

---

## No Analog Found / Partial

| File / concern | Role | Data Flow | Reason |
|----------------|------|-----------|--------|
| Full-tree raw-Git archive materializer | utility | file-I/O | Only `git_blob_bytes` per path; no `ls-tree` tree walker committed |
| Canonical source-context hasher as single shared symbol | utility | transform | Values exist (baseline `dcf73073…`, H8 `051c0795…`); function not re-derived as one module export (RESEARCH A3/Q1) |
| OCI source-context label key on image | config | transform | Dockerfile has `revision` only; custom context label name open |
| Automated image secret-exclusion suite | test | batch | Operator checklist only; Wave 0 gap |
| Live R0–R3 / canary execution evidence | report | request-response | H8 stopped before image/runtime (`image_build_count=0`) |

Planner: implement archive helper + tests first; gate image/runtime/canary on equality proofs; reuse launcher/runner/bootstrap without domain contract changes.

## Stale / User-Owned Warnings

1. **`mcp_server/config/config-docker-neo4j.yaml`** — user dirty; unstaged forever this phase. H8 blob `815d00fe…`; do not hash-mismatch “fix” by staging.
2. **9s8 evidence directory** — immutable historical receipts; append new phase evidence under `.planning/phases/06-…/` or new quick id, never rewrite H1/H7/H8 JSON.
3. **Prior image** `graphiti-mcp:phase6-35227e0a2c69-bound` / `sha256:994e1d13…` — historical only; retag forbidden.
4. **SAFE-02 / ROADMAP Phase-6-out-of-scope** — stale vs `e52c1b5`; do not plan a stop that ignores authorized canary.
5. **`git archive` any remaining operator scripts** — treat as non-authority; H8 is proof.
6. **Catalog domain models/tools** — out of scope for orchestration fixes (Spec §5 last clause).

## Metadata

**Analog search scope:** `scripts/*catalog*`, `mcp_server/src/services/catalog_schema_bootstrap.py`, `mcp_server/docker/*`, `mcp_server/tests/test_catalog_canary_scripts.py`, `test_catalog_phase2_gate_runner.py`, `.planning/quick/260722-9s8-…`, `.planning/phases/05-…`, `e52c1b5:spec/new-phase.md`
**Files scanned:** ~25 primary + evidence
**Pattern extraction date:** 2026-07-22
**Resume point:** `BLOCKED_POST_COMMIT_SOURCE_BINDING` after H1–H7 green at `1031b79`
```
