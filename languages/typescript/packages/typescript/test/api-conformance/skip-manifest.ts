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
 * The conflict `precondition` / `preconditionBinds` (out-of-band SQL simulating a
 * concurrent writer) is NOT a case-level skip: it is a SUB-STEP of the exercised
 * locking cases (`m-opt-lock-005` / `m-opt-lock-007`), applied harness-side — those
 * cases ARE exercised.
 *
 * The nine full-bitemporal milestone-chaining writes (`m-bitemp-write-001`–`-009`,
 * promoted into `slice-mvp-1` by COR-26 plus the standalone plain-insert witness `-009`
 * from COR-9 — the windowed / plain rectangle splits, the plain fully-current insert, and
 * the optimistic-gated close) are all skipped here: their rectangle-split / plain-write /
 * optimistic-gated DML is proven end-to-end by the reference harness AND
 * the TypeScript conformance runner's run lane (`slice-run` / `mariadb-run` drive
 * `@parallax/conformance`'s write-sequence / conflict plan), not the developer-surface
 * object-lifecycle API — a developer never authors the milestone-chaining DML directly
 * (the developer surface for the bitemporal *reads* IS exercised, in `temporal`).
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
  // --- value objects: the non-developer-query slice (m-value-object) ---------
  {
    id: "m-value-object-003",
    reason:
      "project-nested-field: a projection of one nested field (`select … jsonb_extract_path_text(t0.address, 'city') city …`) " +
      "whose witness rows name a PROJECTED column. The V1 developer `find` returns whole managed " +
      "objects (with the value-object composite), so a projected-column result needs the out-of-V1 " +
      "aggregation/projection surface (m-agg, deferred by §2.8) — exactly as m-op-algebra-028 is skipped. " +
      "The nested-extraction developer surface itself is exercised by m-value-object-001/023.",
  },
  {
    id: "m-value-object-026",
    reason:
      "write-update-whole-document: a whole-document UPDATE (`update customer set address = ?`). The V1 " +
      "value-object developer write surface is the atomic document create (exercised by m-value-object-025); " +
      "assigning a document to a value-object member via the update DSL is a follow-on surface. The write's " +
      "observable (the replaced document in tableState) is proven by the harness run lane (slice-run).",
  },
  {
    id: "m-value-object-027",
    reason:
      "write-null-out: a whole-document null-out (`update customer set address = ?` binding SQL NULL). Same " +
      "follow-on value-object UPDATE surface as m-value-object-026; the null-out observable is proven by the " +
      "harness run lane (slice-run).",
  },
  {
    id: "m-value-object-028",
    reason:
      "temporal-as-of-now-document: a value-object materialization under an `asOf` processing pin. It composes " +
      "two surfaces already exercised — the temporal-read developer surface (temporal.api-conformance.test.ts, " +
      "m-temporal-read-*) and value-object materialization (m-value-object-023/024) — and the composed observable is " +
      "proven end-to-end by the harness run lane (slice-run).",
  },
  {
    id: "m-value-object-029",
    reason:
      "temporal-as-of-past-document: an as-of-past value-object materialization; same composition as " +
      "m-value-object-028 (temporal read × value-object materialization), proven end-to-end by the harness run lane.",
  },
  {
    id: "m-value-object-030",
    reason:
      "bitemporal-as-of-now-document: a bitemporal (both-axes) value-object materialization; same composition as " +
      "m-value-object-028, proven end-to-end by the harness run lane.",
  },
  {
    id: "m-value-object-031",
    reason:
      "bitemporal-as-of-past-document: a bitemporal as-of-past value-object materialization; same composition as " +
      "m-value-object-028, proven end-to-end by the harness run lane.",
  },
  {
    id: "m-value-object-032",
    reason:
      "temporal-write-chaining-document: an audit-only milestone-chaining UPDATE that carries the document across " +
      "the chain. It composes the audit-write developer surface (transactions.api-conformance.test.ts, " +
      "m-audit-write-*) with the value-object document; the chaining observable (the document on each milestone) is " +
      "proven by the harness run lane (slice-run).",
  },
  ...["034", "035", "036", "037", "038", "039", "040", "041", "042", "043"].map((n) => ({
    id: `m-value-object-${n}`,
    reason:
      "rejected: a pre-SQL refusal negative (m-value-object resolved Q7). Its whole assertion is that a " +
      "model-invalid input (a value-object root, an unknown nested path, a deepFetch/navigation targeting a " +
      "value object, a type-mismatched literal, a missing required attribute / nested value object) is REFUSED " +
      "before any query is built — so there is no idiomatic developer query to author. The refusal is proven by " +
      "the `@parallax/operation` validators and the harness run lane (slice-run emits the rejected rule).",
  })),
  // --- bitemporal milestone-chaining writes (m-bitemp-write, promoted by COR-26;
  //     the standalone plain-insert witness -009 added by COR-9 Phase 1) ---
  ...["001", "002", "003", "004", "005", "006", "007", "008", "009"].map((n) => ({
    id: `m-bitemp-write-${n}`,
    reason:
      "bitemporal milestone-chaining write (rectangle split / plain insert-update-terminate / optimistic-gated " +
      "close): the windowed `*Until` and plain `insert`/`update`/`terminate` writes and the optimistic-gated " +
      "inactivation close never mutate in place — they open a fully-current rectangle or close the original on " +
      "the processing axis and chain milestone rows. " +
      "Their DML is proven end-to-end by the reference harness AND the TypeScript conformance runner's run lane " +
      "(slice-run drives @parallax/conformance's write-sequence / conflict plan, grading the resulting tableState " +
      "/ affectedRows), not the developer-surface object API — a developer never authors the milestone-chaining " +
      "DML directly. The bitemporal READ developer surface is exercised in temporal.api-conformance.test.ts.",
  })),
  // --- audit-chaining breadth + unit-work RYOW (COR-26 Phase 2, already-claimed modules) ---
  ...["m-audit-write-004", "m-audit-write-005", "m-audit-write-006"].map((id) => ({
    id,
    reason:
      "audit-only milestone-chaining write breadth (multi-attribute correction, update from EXISTING " +
      "persisted history, and the optimistic-gated close): the close-and-chain / gated-close DML is proven " +
      "end-to-end by the reference harness AND the TypeScript conformance runner's run lane (slice-run drives " +
      "@parallax/conformance's write-sequence / conflict plan, grading tableState / affectedRows). The " +
      "audit-write developer idiom is already exercised by m-audit-write-001/-002/-003 in " +
      "transactions.api-conformance.test.ts — these are breadth variants whose specific goldens the run lane " +
      "grades, not a distinct developer query.",
  })),
  ...["m-unit-work-005", "m-unit-work-006", "m-unit-work-007", "m-unit-work-008"].map((id) => ({
    id,
    reason:
      "unit-of-work read-your-own-writes / flush breadth (RYOW update, RYOW delete, non-cascade FK-delete " +
      "ordering, insert-then-update combining): the observable — a dependent find seeing the committed write, the " +
      "ordered delete flush, the single combined INSERT — is proven end-to-end by the reference harness AND the " +
      "conformance runner's run lane (slice-run drives @parallax/conformance's scenario / write-sequence plan). " +
      "The unit-of-work developer idiom is already exercised by m-unit-work-001/-002/-003 in " +
      "transactions.api-conformance.test.ts — these are breadth variants whose specific goldens the run lane grades.",
  })),
  // --- batch-DELETE + opt-lock edges + mixed-op flush (COR-26 Phase 3, already-claimed modules) ---
  ...["m-batch-write-003", "m-batch-write-004"].map((id) => ({
    id,
    reason:
      "set-based DELETE flush breadth (the non-versioned `delete ... where id in (...)` collapse and the " +
      "versioned per-key version-gated materialize): the collapsed / materialized DML is proven end-to-end by the " +
      "reference harness AND the conformance runner's run lane (slice-run drives @parallax/conformance's " +
      "write-sequence plan, grading the resulting tableState). The batched-write developer idiom is already " +
      "exercised by m-batch-write-001/-002 (and the versioned materialize by m-opt-lock-003/-004) in " +
      "transactions.api-conformance.test.ts — these are the DELETE-form variants whose specific goldens the run lane grades.",
  })),
  ...["m-opt-lock-012", "m-opt-lock-013"].map((id) => ({
    id,
    reason:
      "optimistic-lock edges (a `updatedRows != 1` conflict ABORTING the whole unit of work with no partial " +
      "flush; a multi-attribute versioned update advancing the version once): the affected-row count and the " +
      "aborted-then-unchanged / multi-column tableState are proven end-to-end by the reference harness AND the " +
      "conformance runner's run lane (slice-run drives @parallax/conformance's scenario / conflict plan). The " +
      "opt-lock developer idiom is already exercised by m-opt-lock-005/-006 (conflict + success) and the abort by " +
      "m-unit-work-002 in transactions.api-conformance.test.ts — these are edge variants whose specific goldens the run lane grades.",
  })),
  {
    id: "m-unit-work-009",
    reason:
      "mixed-op flush ordering (one unit of work flushing an insert + an update + a delete in the combined " +
      "canonical order): the combined net state a dependent find observes is proven end-to-end by the reference " +
      "harness AND the conformance runner's run lane (slice-run drives @parallax/conformance's scenario plan). The " +
      "unit-of-work flush idiom is already exercised by m-unit-work-001/-003 in transactions.api-conformance.test.ts — " +
      "this is a cross-kind flush-ordering variant whose specific golden the run lane grades.",
  },
  // --- type fidelity + value-object write gaps + pk-gen (COR-26 Phase 5) ------
  ...["005", "006", "007", "008"].map((n) => ({
    id: `m-core-${n}`,
    reason:
      "scalar WRITE round-trip / boundary (float32/float64/bytes/time/uuid round-trip, explicit-null write, " +
      "decimal-precision and string-max-length boundaries): that the value survives the encode-at-bind / " +
      "decode-at-read boundary is proven end-to-end by the reference harness (both dialects) AND the conformance " +
      "runner's run lane (slice-run grades the resulting tableState). The developer scalar-write idiom is already " +
      "exercised by the timestamp inserts m-core-002/-003 in transactions.api-conformance.test.ts — these are " +
      "type-fidelity variants whose specific goldens the run lane grades.",
  })),
  {
    id: "m-value-object-044",
    reason:
      "rejected: a pre-SQL refusal negative (m-value-object resolved Q7) — a write OMITTING a required TOP-LEVEL " +
      "value object is refused before any DML with write-required-value-object-missing. Like the other rejected " +
      "negatives, there is no idiomatic developer query to author; the refusal is proven by the @parallax/operation " +
      "validators and the harness run lane (slice-run emits the rejected rule).",
  },
  {
    id: "m-value-object-045",
    reason:
      "value-object multi-row batched INSERT: two Customers collapse into one multi-row INSERT, each address " +
      "document bound atomically. The collapsed DML + decoded read-back is proven end-to-end by the reference " +
      "harness AND the conformance runner's run lane (slice-run grades tableState). The value-object developer write " +
      "idiom is exercised by m-value-object-025 and the batched collapse by m-batch-write-001 — this is the " +
      "composition whose specific golden the run lane grades.",
  },
  {
    id: "m-value-object-046",
    reason:
      "value-object document WRITE under an optimistic gate: a versioned UPDATE replaces the whole address document " +
      "and advances the version once, gated on the observed version. The affected-row count + decoded tableState is " +
      "proven end-to-end by the reference harness AND the conformance runner's run lane (slice-run drives " +
      "@parallax/conformance's conflict plan). The value-object write is exercised by m-value-object-025 and the " +
      "optimistic gate by m-opt-lock-005/-006 — this is the composition whose specific golden the run lane grades.",
  },
  ...["m-pk-gen-001", "m-pk-gen-002", "m-pk-gen-004", "m-pk-gen-006", "m-pk-gen-014"].map((id) => ({
    id,
    reason:
      "primary-key generation (the max strategy `coalesce(max(col), ?) + ?`; the simulated-sequence " +
      "`next_val += n` reserve then the reserved id; and the sequence x audit-only-temporal milestone insert): pk " +
      "allocation is a framework concern a developer never authors as DML. The allocated ids + advanced counter + " +
      "resulting rows are proven end-to-end by the reference harness (the pk-allocation oracle AND the run lane " +
      "grading tableState) and the conformance runner's run lane (slice-run). No idiomatic developer query spells " +
      "the coalesce/max or the sequence-reservation SQL.",
  })),
];

/** The set of skipped case ids, for the coverage check. */
export const SKIPPED_IDS: ReadonlySet<string> = new Set(SKIP_MANIFEST.map((c) => c.id));
