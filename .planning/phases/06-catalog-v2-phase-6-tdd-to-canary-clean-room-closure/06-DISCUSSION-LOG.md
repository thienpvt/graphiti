# Phase 6: Native Ollama Clean-Room Remediation and Final Canary - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-23
**Phase:** 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
**Areas discussed:** embedding route, readiness policy, historical isolation, runtime authority, final boundary
**Mode:** Autonomous continuation; the updated specification selected the locked options without further questions.

---

## Embedding Route

| Option | Description | Selected |
|--------|-------------|----------|
| Native Ollama | Existing `OllamaEmbedder`, native `/api/embed`, exact qwen model and 1024 dimensions | ✓ |
| OpenAI-compatible proxy | Preserve the failed proxy route | |
| New provider | Implement another embedder | |

**Selection authority:** `spec/new-phase.md` at `ab5fdeb`.
**Notes:** No OpenAI embedder variables, proxy token, public provider, `/v1`, or API key may enter the new path.

---

## Capability and Waiver Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Exact ready, null waiver | `/api/tags` exact-model proof; `ready`; manifest waiver null | ✓ |
| Unknown with OpenAI waiver | Prior operation behavior | |
| Proactive readiness embedding | Mutating/functional probe inside capability call | |

**Selection authority:** `spec/new-phase.md` §§6–7.
**Notes:** The separate local preflight may perform one sanitized native embedding probe; capability readiness remains tags-only.

---

## Historical Isolation

| Option | Description | Selected |
|--------|-------------|----------|
| Append-only remediation | Preserve old run/evidence/resources; use new plans and `06-OLLAMA-*` artifacts | ✓ |
| Resume old canary | Retry prior run/project | |
| Replace old evidence | Rewrite ledger/report/receipts | |

**Selection authority:** `spec/new-phase.md` §§1, 11–13.
**Notes:** Preserve the intentional absence of `06-05-SUMMARY.md`; do not query or clean the old project.

---

## Runtime Authority

| Option | Description | Selected |
|--------|-------------|----------|
| Entirely new clean room | New project, volumes, network, namespace, containers, and identities | ✓ |
| Reuse old Neo4j volume | Carry prior schema/runtime state forward | |
| Recreate old project | Delete/rebuild historical resources | |

**Selection authority:** `spec/new-phase.md` §12.
**Notes:** Exact `0/14 → 14/14`, 28 tools, Ollama ready, null waiver, exact image, zero LLM calls.

---

## Final Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| One new canary after freeze | Commit prefreeze evidence, explicit approval, one allocation/builder/runner | ✓ |
| Retry loop after IDs | Edit/rebuild/retry on failure | |
| Cleanup after terminal result | Remove final resources | |

**Selection authority:** `spec/new-phase.md` §§13–14.
**Notes:** The TDD loop closes at first ID allocation. Final stack remains intact after success or failure.

---

## Claude's Discretion

- Minimal internal test grouping and exact append-only plan decomposition.
- Reuse existing native embedder, probe, archive, scanner, materializer, launcher, builder, runner, and bootstrap.

## Deferred Ideas

- OpenAI/proxy remediation, other models/providers, deployment, migration, full ingest, and historical cleanup.
