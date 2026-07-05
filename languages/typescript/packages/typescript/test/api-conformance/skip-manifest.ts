/**
 * The explicit, reasoned API Conformance Suite **skip manifest** (Phase 10c).
 *
 * A case is skipped ONLY when the thing it proves is harness/serde machinery a
 * developer never authors — not a developer-facing surface. The coverage test
 * (`coverage.test.ts`) asserts every `slice-mvp-1` case is either
 * exercised or listed HERE with a reason, so a silent gap fails the build.
 *
 * The one skipped case in the slice is `0222`, whose distinguishing purpose is the
 * `equivalentEncodings` serde-canonicalization check (a "prefix" and a "fluent"
 * surface spelling MUST canonicalize to the same operation) — a harness/serde
 * concern, not a query a developer writes differently. Its query semantics ARE
 * exercised by the developer surface elsewhere: its DSL fidelity is pinned by the
 * Phase-9 `dsl.test.ts` (`0222-group-precedence-grouped`), and its ungrouped
 * sibling `0223` is exercised in `reads.api-conformance.test.ts`.
 *
 * `0728` (read-lock-blocks-writer) is also skipped here: it is a HARNESS-lane
 * two-connection concurrency case (a held `for share` read excludes a concurrent
 * writer, which times out). Its behavioral proof is discharged by the reference
 * harness AND the TypeScript conformance runner's run lane (`slice-run.test.ts` /
 * `mariadb-run.test.ts` drive `@parallax/conformance`'s two-session `runRun`), not
 * the developer-surface API Conformance Suite — a developer never authors the
 * barrier + lowered-lock-budget choreography. (The read lock's developer-observable
 * behavior — a locking find returns the row — IS exercised here by `0603`/`0616`.)
 *
 * The other two constructs the phase note calls out are NOT case-level skips in the
 * 121-case slice:
 *  - the conflict `precondition` / `preconditionBinds` (out-of-band SQL simulating a
 *    concurrent writer) is a SUB-STEP of the exercised locking cases (`0703` /
 *    `0708`), applied harness-side — those cases ARE exercised;
 *  - the out-of-V1 `createUntil` / `updateUntil` / `terminateUntil` writes
 *    (`0810`–`0812`) are not tagged `slice-mvp-1`, so they are not in
 *    the slice at all.
 */

/** One skipped case: its four-digit id and the reason it is not developer-authored. */
export interface SkippedCase {
  /** The four-digit case id (`0222`). */
  readonly id: string;
  /** Why the case is not a developer-facing suite case (a serde/harness construct). */
  readonly reason: string;
}

/** The explicit skip list over the `slice-mvp-1` slice. */
export const SKIP_MANIFEST: readonly SkippedCase[] = [
  {
    id: "0222",
    reason:
      "equivalentEncodings serde-canonicalization: proves two SURFACE spellings (prefix / " +
      "fluent) collapse to one canonical operation — a serde concern, not a developer query. " +
      "Its DSL fidelity is covered by dsl.test.ts (0222) and its ungrouped sibling 0223 is exercised.",
  },
  {
    id: "0226",
    reason:
      "distinct on a single PROJECTED column (`select distinct t0.active`): its result " +
      "(2 rows) is a projection-specific witness. The V1 developer `find` returns whole managed " +
      "objects, so `distinct` applies to the full row set — a different operation with a " +
      "different result (6 distinct orders). Projecting one column needs the out-of-V1 " +
      "aggregation/projection surface (04xx). Its DSL/operation fidelity is still proven by " +
      "dsl.test.ts (0226-distinct); only the projected-result assertion is out of the V1 surface.",
  },
  {
    id: "0728",
    reason:
      "read-lock-blocks-writer: a HARNESS-lane two-connection concurrency case (a held `for " +
      "share` read excludes a concurrent writer → lockWaitTimeout). Its behavioral proof is " +
      "discharged by the reference harness and the TypeScript conformance runner's two-session " +
      "run lane (slice-run/mariadb-run drive @parallax/conformance's runRun), not the " +
      "developer-surface suite — a developer never authors the barrier + lowered-lock-budget " +
      "choreography. The read lock's developer-observable behavior is exercised by 0603/0616.",
  },
];

/** The set of skipped case ids, for the coverage check. */
export const SKIPPED_IDS: ReadonlySet<string> = new Set(SKIP_MANIFEST.map((c) => c.id));
