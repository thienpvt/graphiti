# Phase 3B: Atomic Catalog, Exact Evidence, and Durable Manifest Writes - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-18
**Phase:** 3B-atomic-catalog-exact-evidence-and-durable-manifest-writes
**Mode:** Autonomous — standing approval selected every recommended option
**Areas discussed:** Transaction boundary, stranded recovery, exact evidence, durable manifest, replay/concurrency, compatibility/gate

---

## Transaction Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| One success transaction after claim | Co-commit domain, evidence, manifest, batch terminal status, and plan COMMITTED | ✓ |
| Multiple ordered transactions | Persist each category independently with compensation | |
| Fold claim into success transaction | Replace Phase 3A claim seam | |

**Selection:** One success transaction after the existing separate Phase 3A claim.
**Rationale:** Only option satisfying PLAN-13/MANI-06 without weakening the proven token/CAS seam.

---

## Stranded COMMITTING Recovery

| Option | Description | Selected |
|--------|-------------|----------|
| Serialized resume-or-finish | Reverify frozen artifact, lock, observe valid terminal result or rerun complete idempotent success transaction | ✓ |
| Timeout reset | Reset COMMITTING to PREPARED after a lease duration | |
| Permanent manual intervention | Reject all COMMITTING re-entry | |

**Selection:** Serialized resume-or-finish; never reset to PREPARED.
**Rationale:** Prevents second-writer authority and preserves immutable token scope across process restart.

---

## Exact Evidence Persistence

| Option | Description | Selected |
|--------|-------------|----------|
| Dual-layer exact + interop | Non-Entity explicit evidence authority plus compatible Episodic/MENTIONS/edge episodes links | ✓ |
| Graphiti links only | Infer exact evidence from MENTIONS and edge episodes | |
| Control records only | Drop existing search interoperability links | |

**Selection:** Dual-layer exact evidence plus Graphiti interoperability.
**Rationale:** Satisfies exact one-source/one-target authority without breaking entity/edge search behavior.

---

## Durable Manifest

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded root + ordered chunks | Exact frozen membership including unchanged; deterministic hash/identity | ✓ |
| One unbounded JSON property | Store all membership on one manifest node | |
| Infer from batch_id/live rows | Build membership on read from domain properties | |

**Selection:** Deterministic non-Entity root plus bounded chunks.
**Rationale:** Reuses Phase 3A proven bounded storage; avoids property limits and membership lies.

---

## Replay and Concurrency

| Option | Description | Selected |
|--------|-------------|----------|
| One logical commit | CAS/locks/uniqueness serialize writers; followers recover or return stable durable receipt | ✓ |
| Last writer wins | Permit repeated domain/manifest rewrites | |
| Fail every re-entry | Reject COMMITTING and COMMITTED tokens | |

**Selection:** One logical commit with stable replay.
**Rationale:** Required by PLAN-15/16 and deterministic retry semantics.

---

## Compatibility and Gate

| Option | Description | Selected |
|--------|-------------|----------|
| Shared atomic writer | Prepared commit and direct non-dry-run upsert share domain/evidence/manifest/status transaction; dry-run remains zero-write | ✓ |
| Prepared-only manifest | Leave direct upsert without durable membership | |
| Remove direct upsert | Force all callers onto prepare/commit | |

**Selection:** Shared atomic writer; preserve direct upsert and all existing tools.
**Rationale:** Avoids divergent authorities and enables Phase 4 verification for every committed catalog-v2 batch.

---

## Claude's Discretion

- Exact fixed control labels/properties/relationship names.
- Smallest shared-writer module/function extraction.
- Conservative manifest chunk limits after research/live proof.
- Bounded committed response additions.
- Whether each rolled-back failure merits a separate bounded failed-status write.

## Deferred Ideas

- Manifest/evidence read tools, edge resolution, verification, pagination, split read/write gates — Phase 4.
- Long-term cleanup, observability, final compatibility/security/migration docs — Phase 5.
- Canary, `oracle-catalog-v2`, migration, deployment, deletion, graph clear — separate approval/out of scope.
