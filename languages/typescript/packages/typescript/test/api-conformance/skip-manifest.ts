/**
 * The explicit, reasoned API Conformance Suite **skip manifest** (Phase 10c).
 *
 * A case is skipped ONLY when the thing it proves is harness/serde machinery a
 * developer never authors — not a developer-facing surface. The coverage test
 * (`coverage.test.ts`) asserts every `slice-mvp-1` case is either
 * exercised or listed HERE with a reason, so a silent gap fails the build.
 *
 * The one skipped case in the slice is `m-op-algebra-024`, whose distinguishing
 * purpose is the `equivalentEncodings` serde-canonicalization check (a "prefix" and a
 * "fluent" surface spelling MUST canonicalize to the same operation) — a harness/serde
 * concern, not a query a developer writes differently. Its query semantics ARE
 * exercised by the developer surface elsewhere: its DSL fidelity is pinned by the
 * Phase-9 `dsl.test.ts` (`m-op-algebra-024-group-precedence-grouped`), and its ungrouped
 * sibling `m-op-algebra-025` is exercised in `reads.api-conformance.test.ts`.
 *
 * The COR-12 behavioral read-lock concurrency cases `m-read-lock-006` (blocks-writer),
 * `m-read-lock-007` (shared-compatible), and `m-read-lock-008`
 * (projection-omits-lock-admits-writer) are all skipped here: each is a HARNESS-lane
 * two-connection concurrency case (a held `for share` read excludes / admits a peer, or
 * an unlocked projection admits a writer). Their behavioral proof is discharged by the
 * reference harness AND the TypeScript conformance runner's run lane (`slice-run.test.ts`
 * / `mariadb-run.test.ts` drive `@parallax/conformance`'s two-session `runRun`), not the
 * developer-surface API Conformance Suite — a developer never authors the barrier +
 * lowered-lock-budget choreography. (The read lock's developer-observable behavior — a
 * locking find returns the row — IS exercised here by `m-read-lock-001`/`m-read-lock-002`.)
 *
 * The other two constructs the phase note calls out are NOT case-level skips in the
 * 123-case slice:
 *  - the conflict `precondition` / `preconditionBinds` (out-of-band SQL simulating a
 *    concurrent writer) is a SUB-STEP of the exercised locking cases (`m-opt-lock-005` /
 *    `m-opt-lock-007`), applied harness-side — those cases ARE exercised;
 *  - the out-of-V1 `createUntil` / `updateUntil` / `terminateUntil` writes
 *    (`m-bitemp-write-001`–`-003`) are not tagged `slice-mvp-1`, so they are not in
 *    the slice at all.
 */

/** One skipped case: its per-module id and the reason it is not developer-authored. */
export interface SkippedCase {
  /** The per-module case id (`m-op-algebra-024`). */
  readonly id: string;
  /** Why the case is not a developer-facing suite case (a serde/harness construct). */
  readonly reason: string;
}

/** The explicit skip list over the `slice-mvp-1` slice. */
export const SKIP_MANIFEST: readonly SkippedCase[] = [
  {
    id: "m-op-algebra-024",
    reason:
      "equivalentEncodings serde-canonicalization: proves two SURFACE spellings (prefix / " +
      "fluent) collapse to one canonical operation — a serde concern, not a developer query. " +
      "Its DSL fidelity is covered by dsl.test.ts (m-op-algebra-024) and its ungrouped sibling " +
      "m-op-algebra-025 is exercised.",
  },
  {
    id: "m-op-algebra-028",
    reason:
      "distinct on a single PROJECTED column (`select distinct t0.active`): its result " +
      "(2 rows) is a projection-specific witness. The V1 developer `find` returns whole managed " +
      "objects, so `distinct` applies to the full row set — a different operation with a " +
      "different result (6 distinct orders). Projecting one column needs the out-of-V1 " +
      "aggregation/projection surface (m-agg). Its DSL/operation fidelity is still proven by " +
      "dsl.test.ts (m-op-algebra-028-distinct); only the projected-result assertion is out of the V1 surface.",
  },
  {
    id: "m-read-lock-006",
    reason:
      "read-lock-blocks-writer: a HARNESS-lane two-connection concurrency case (a held `for " +
      "share` read excludes a concurrent writer → lockWaitTimeout). Its behavioral proof is " +
      "discharged by the reference harness and the TypeScript conformance runner's two-session " +
      "run lane (slice-run/mariadb-run drive @parallax/conformance's runRun), not the " +
      "developer-surface suite — a developer never authors the barrier + lowered-lock-budget " +
      "choreography. The read lock's developer-observable behavior is exercised by m-read-lock-001/m-read-lock-002.",
  },
  {
    id: "m-read-lock-007",
    reason:
      "read-lock-shared-compatible: a HARNESS-lane two-connection concurrency-success case (A " +
      "and B BOTH take `for share` on the same row and both succeed — the lock is shared, not " +
      "exclusive). Like m-read-lock-006, its behavioral proof is discharged by the reference harness and " +
      "the conformance runner's two-session runRun (slice-run/mariadb-run), not the developer " +
      "surface — a developer never authors the barrier + two held sessions. The read lock's " +
      "developer-observable behavior is exercised by m-read-lock-001/m-read-lock-002.",
  },
  {
    id: "m-read-lock-008",
    reason:
      "projection-omits-lock-admits-writer: a HARNESS-lane two-connection concurrency-success " +
      "case (A holds an unlocked `distinct` projection, B's concurrent UPDATE is admitted — no " +
      "lock to block it). Like m-read-lock-006/m-read-lock-007, its behavioral proof is discharged by the reference " +
      "harness and the conformance runner's two-session runRun (slice-run/mariadb-run), not the " +
      "developer surface. The projection-omits-lock EMISSION is exercised by m-read-lock-003.",
  },
];

/** The set of skipped case ids, for the coverage check. */
export const SKIPPED_IDS: ReadonlySet<string> = new Set(SKIP_MANIFEST.map((c) => c.id));
