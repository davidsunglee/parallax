/**
 * GENERATED — do not edit by hand.
 *
 * The static TypeScript view of the compatibility-case format, derived from
 * `core/schemas/compatibility-case.schema.json` (the single source of truth the
 * `@parallax/conformance` loader validates each document against with Ajv). Run
 * `pnpm run ts:generate-case-types` to regenerate; CI enforces freshness with a
 * `git diff --exit-code` gate (`ts:generate-case-types:check`).
 */
/**
 * The case envelope, grouped as given / when / then. Identity and routing (`model`, `tags`, `lane`) plus the explicit `shape` discriminator and the optional `compileEligibility` declaration (present only to mark a case RUN-ONLY for the compile sweep) stay top-level; everything else is bucketed into `given` (ambient world-state before the action: `fixtures`, `apply`, `fault`), `when` (the action under test and how the client performs it: `operation` | `writeSequence` | `scenario` | `coherence` | `concurrency` | `boundary` | `attempts` | `write`, plus context `uow` / `at` / `observedInZ` / `equivalentEncodings`), and `then` (everything the case asserts: `statements`, `referenceSql`, `rows`, `graph`, `tableState`, `affectedRows`, `errorClass`, `nativeCode`, `outcome`, `rejectedRule`, `roundTrips`, `tolerance`). Every SQL statement — golden or naive — is a `{sql, binds}` statement entry (`$defs/statementEntry`): its `sql` is a dialect-keyed map (`postgres` / `mariadb`) at golden locations (`then.statements`, per-step `statements`) and a plain string at naive locations (`given.apply`); `binds` is authored once per statement and defaults to `[]`. A case is one of nine shapes, named by the required top-level `shape`: a `read` case (a queryable `when.operation`, asserting `then.rows` / `then.graph`); a `writeSequence` case (ordered DML under `when.writeSequence`, asserting `then.tableState`); a `scenario` case (m-unit-work — ordered operation steps under `when.scenario`, golden SQL per step); a `conflict` case (m-opt-lock — a single-attempt optimistic-lock UPDATE asserted by `then.affectedRows`, or an ordered `when.attempts` retry sequence); a `coherence` case (cross-process cache coherence — a two-node sequence under `when.coherence`); an `error` case (m-db-error — `then.errorClass` + `then.nativeCode`, triggered by top-level `then.statements` or a `when.concurrency` choreography); a `concurrencySuccess` case (m-read-lock behavioral read lock — a `when.concurrency` choreography with NO `then.errorClass`); a `boundary` case (m-auto-retry/m-opt-lock bounded automatic retry — `when.boundary` ordered actions + `then.outcome`, on the `api-conformance` lane, carrying no golden SQL); or a `rejected` case (m-value-object / m-op-algebra negative validation — a schema-valid `when.operation` OR a `when.write` a model-aware validator MUST refuse PRE-SQL, naming the violated normative rule in `then.rejectedRule`, carrying no golden SQL). Every case carries an optional `lane` (`harness` default | `api-conformance`): a `harness`-lane case executes as today, while an `api-conformance`-lane case (every boundary case, plus the read-lock matrix reads) is schema-validated by the harness but satisfied by each language's API Conformance Suite.
 */
export type ParallaxCompatibilityCaseMCaseFormat = {
  [k: string]: unknown;
} & {
  /**
   * Path to the model descriptor, relative to core/compatibility/.
   */
  model: string;
  /**
   * Module/feature tags driving coverage and test selection.
   *
   * @minItems 1
   */
  tags: [string, ...string[]];
  /**
   * Which executor satisfies this case (m-case-format lane routing). `harness` (the default) — the m-case-format compatibility harness executes it as today (golden-SQL / data observables). `api-conformance` — a runtime-loop or read-lock-matrix branch a single-connection harness cannot provoke: the harness schema-validates it but does NOT execute it, and each language's API Conformance Suite MUST satisfy it. Every `boundary`-shape case is `api-conformance` by construction; the read-lock matrix reads (`m-read-lock-002`-`m-read-lock-005`) are `read`-shape `api-conformance` cases.
   */
  lane?: "harness" | "api-conformance";
  /**
   * The explicit case-shape discriminator: cases are self-describing, and the `oneOf` keys on this `const` for precise validation errors. The reference harness and the TypeScript conformance loader read this field directly instead of sniffing which keys happen to be present. The schema still enforces shape-consistent required members (per branch), so a mislabeled case cannot validate.
   */
  shape:
    | "read"
    | "writeSequence"
    | "scenario"
    | "conflict"
    | "coherence"
    | "error"
    | "concurrencySuccess"
    | "boundary"
    | "rejected";
  /**
   * The compile-eligibility declaration (m-case-format / m-conformance-adapter). ABSENT by default: a case is compile-eligible, so an adapter's `compile` command emits its SQL statically. PRESENT only to declare a case RUN-ONLY — its emissions cannot be derived without executing SQL, so `compile` on it returns `status: run-only` with a `compile-run-only` diagnostic instead of `ok`, and only `run` grades it. Eligibility is an AUTHORED, REVIEWED intent declaration (intent is a human judgment); the harness mechanically backstops the detectable single-connection cases and each language's refusing compile port structurally enforces query-result dependence at runtime.
   */
  compileEligibility?: {
    /**
     * The only declared mode is `run-only`: the field's presence declares the case ineligible for the compile sweep. A compile-eligible case simply omits `compileEligibility`.
     */
    mode: "run-only";
    /**
     * Which run-only criterion applies. `single-connection` — the case intends to exercise database concurrency or locking behavior (a `conflict` / `concurrencySuccess` / `boundary` shape, a `when.concurrency` choreography, or a `given.apply` / `given.fault`), so it is run-only regardless of whether its emissions happen to be statically derivable; the harness backstop requires this declaration on every such detectable case. `query-result-dependent` — the emissions are not a pure function of `when` + `given` (deep-fetch fan-out binds, materialized predicate writes, `sequence`-strategy PK allocations, framework-owned observed-version / `in_z` binds), so compiling would require executing a query; this criterion is a human judgment the harness cannot detect and each language's refusing compile port enforces structurally.
     */
    reason: "single-connection" | "query-result-dependent";
    /**
     * Optional human-readable justification for the reviewer.
     */
    note?: string;
  };
  /**
   * Ambient world-state established BEFORE the action under test: the model fixtures to load, out-of-band SQL to apply verbatim, and any injected fault. Optional — a case that starts from the model's default fixtures and injects nothing omits `given` entirely.
   */
  given?: {
    /**
     * Whether the model's fixtures are loaded BEFORE the action — so a sequence can mutate pre-existing persisted rows (the m-detach detached-update merge-back case; the m-read-lock held-session reads). Defaults to false: a writeSequence case starts from an empty schema and builds its own state (the m-audit-write milestone-chaining and m-batch-write batched-insert cases).
     */
    fixtures?: boolean;
    apply?: NaiveStatements;
    /**
     * boundary cases only. A portable fault kind injected at the database-port seam to drive the retry loop (aligned with the m-db-error `errorClass` vocabulary): a `serialization-failure` or `deadlock` transient (always retriable), a `lock-wait-timeout` (never retriable), or an `optimistic-lock-conflict` (retriable only under `when.uow.retryOptimisticConflicts`). Absent when the case exercises only loop configuration (`retries: 0`, the callback-withheld-on-abort case).
     */
    fault?: "serialization-failure" | "deadlock" | "lock-wait-timeout" | "optimistic-lock-conflict";
  };
  /**
   * The action under test and how the client performs it. Exactly one action member is present per shape (`operation` | `writeSequence` | `scenario` | `coherence` | `concurrency` | `boundary` | `attempts`, plus the single-attempt conflict's `write`); the context members (`uow`, `at`, `observedInZ`, `equivalentEncodings`) describe the unit-of-work mode, transaction instant, observed version, and alternate surface encodings.
   */
  when?: {
    /**
     * The unit-of-work configuration the action runs under (m-unit-work strategy selection + m-auto-retry/m-opt-lock bounded automatic retry). Optional and descriptive: it declares the per-unit-of-work concurrency mode (so a case's mode-dependent golden SQL is self-describing) and the retry configuration a boundary case exercises. `concurrency`: `locking` — the default m-read-lock implicit shared read lock, keyed updates advance the version with NO gate; `optimistic` — reads take no lock and every keyed update / temporal close GATES on the observed version. The harness executes the authored golden SQL either way; the block documents WHICH mode produced it.
     */
    uow?: {
      /**
       * The correctness strategy this unit of work selects: `locking` (default — m-read-lock implicit shared read lock; version advances but no gate is emitted) or `optimistic` (m-opt-lock — reads take no lock; keyed updates and temporal closes gate on the observed version).
       */
      concurrency?: "locking" | "optimistic";
      /**
       * The bound on automatic re-executions of the unit-of-work body after a retriable failure (m-auto-retry/m-opt-lock bounded automatic retry). Default 10; `0` disables the loop, so even a transient failure surfaces to the caller.
       */
      retries?: number;
      /**
       * Whether an optimistic-lock conflict joins the retriable set for this unit of work (m-opt-lock). Default false — a conflict surfaces to the caller after one attempt. Transient database failures (deadlock / serialization failure) are always retriable regardless of this flag.
       */
      retryOptimisticConflicts?: boolean;
    };
    /**
     * A canonical m-op-algebra algebra node (validated separately against operation.schema.json). Present on read cases; absent on writeSequence cases.
     */
    operation?: {};
    /**
     * rejected cases only (m-inheritance, resolved Q3). An INLINE model descriptor document (an instance of metamodel.schema.json) carrying an invalid inheritance family a model-aware semantic validator MUST reject before any SQL — the cross-entity family invariants (parent resolution / acyclicity / exactly one root / concrete-under-abstract-root / tag placement / tag presence under table-per-hierarchy / family-wide tagValue uniqueness / shared-table consistency) that per-entity schema validation cannot catch. Kept inline (never in the shared `models/` registry) so an invalid family cannot break sibling cases that load real models; round-tripped through descriptor serde before semantic validation asserts `then.rejectedRule`.
     */
    model?: {};
    /**
     * read cases only. The entity a read TARGETS — the queried position `when.operation` starts from (m-case-format, resolved Q1). It names the whole family for an abstract root, its concrete descendants for an abstract subtype, and itself for a concrete subtype; today every entity is concrete, so it names exactly the entity whose rows the read returns. REQUIRED on every read case, so the read side reaches the same explicit-entity standard the write side already meets with `writeSequence[].entity` (an `all: {}` read no longer names its subject only in a comment or the golden SQL). A model-aware harness cross-checks it against every queried-entity `Class.attribute` / `Class.relationship` reference in the operation (until inheritance families exist, 'consistent' means 'equal').
     */
    targetEntity?: string;
    /**
     * Optional alternate surface encodings of the same operation (e.g. a prefix vs a fluent spelling, or differently-ordered keys). Each MUST canonicalize to `when.operation` via the serde seam; the harness asserts this dialect-agnostically (layer 4c), proving precedence/serialization fidelity in the fixture itself.
     *
     * @minItems 1
     */
    equivalentEncodings?: [{}, ...{}[]];
    /**
     * A writeSequence case: an ordered list of write steps the golden DML (`then.statements`) realizes. Each step names a mutation kind on an entity; the golden SQL is the matching ordered list of DML statements (one or more per step), applied in order, after which the harness asserts `then.tableState`. Used by milestone-chaining temporal writes (m-audit-write), batched non-temporal writes (m-batch-write), detached merge-back delete (m-detach), and the minimal dependent cascade-delete witness (m-cascade-delete/m-unit-work).
     *
     * @minItems 1
     */
    writeSequence?: [
      {
        [k: string]: unknown;
      } & {
        [k: string]: unknown;
      },
      ...({
        [k: string]: unknown;
      } & {
        [k: string]: unknown;
      })[],
    ];
    /**
     * A scenario (m-unit-work) case: an ordered list of steps proving the unit-of-work / identity / query-cache contract. A step is either a READ step (issues a `find`) or a WRITE step (commits DML via `write`). Golden SQL lives PER STEP (as `statements`), not at `then.statements`: each find costs a declared number of database round trips, and an interleaved committed write lets a later step prove read-your-own-writes or query-cache invalidation. The harness asserts the round-trip counts are internally consistent with the golden SQL each step lists.
     *
     * @minItems 1
     */
    scenario?: [
      {
        [k: string]: unknown;
      } & {
        [k: string]: unknown;
      } & {
        [k: string]: unknown;
      } & {
        [k: string]: unknown;
      } & (
          | {
              [k: string]: unknown;
            }
          | {
              [k: string]: unknown;
            }
          | {
              [k: string]: unknown;
            }
        ) &
        (
          | {
              [k: string]: unknown;
            }
          | {
              [k: string]: unknown;
            }
          | {
              [k: string]: unknown;
            }
        ),
      ...({
        [k: string]: unknown;
      } & {
        [k: string]: unknown;
      } & {
        [k: string]: unknown;
      } & {
        [k: string]: unknown;
      } & (
          | {
              [k: string]: unknown;
            }
          | {
              [k: string]: unknown;
            }
          | {
              [k: string]: unknown;
            }
        ) &
        (
          | {
              [k: string]: unknown;
            }
          | {
              [k: string]: unknown;
            }
          | {
              [k: string]: unknown;
            }
        ))[],
    ];
    /**
     * A coherence (cross-process cache coherence) case: an ordered list of steps run against ONE database over TWO connections modeling two application servers (node A, node B). Each step names the node it runs on, the operation it issues, and its golden SQL (`statements`); a write step (kind `write`) COMMITS on its node, a read step (kind `read`) is a query. The final step is node B's re-fetch after node A's committed write — it carries `observeRows`, the post-write rows node B MUST observe.
     *
     * @minItems 2
     */
    coherence?: [
      {
        [k: string]: unknown;
      },
      {
        [k: string]: unknown;
      },
      ...{
        [k: string]: unknown;
      }[],
    ];
    /**
     * The two-connection choreography for deadlock / lockWaitTimeout error cases and the concurrency-success read-lock cases. Ordered, barrier-separated rounds; each round names the statements nodes A and B run that round (a node absent from a round is idle). Each node step carries `statements` (dialect-keyed golden SQL entries), mirroring a coherence step. The runner runs each node on its own non-autocommit session, synchronizes rounds with a barrier, and (for an error case) classifies the error raised in the contention round.
     */
    concurrency?: {
      /**
       * @minItems 1
       */
      rounds: [
        {
          A?: ConcurrencyStep;
          B?: ConcurrencyStep;
        },
        ...{
          A?: ConcurrencyStep;
          B?: ConcurrencyStep;
        }[],
      ];
    };
    /**
     * boundary cases only (m-auto-retry/m-opt-lock bounded automatic retry). An ordered list of the actions the unit-of-work body performs, portably described so the case is self-documenting without carrying golden SQL. The m-case-format harness never executes these (the case is `api-conformance`-lane); each language's suite realizes them through its idiomatic public API.
     *
     * @minItems 1
     */
    boundary?: [
      {
        /**
         * The unit-of-work action this step performs, portably named (the concrete API is per-language).
         */
        action: "read" | "create" | "update" | "terminate" | "delete";
        /**
         * Optional human-readable description of the action's role in the loop scenario.
         */
        note?: string;
      },
      ...{
        /**
         * The unit-of-work action this step performs, portably named (the concrete API is per-language).
         */
        action: "read" | "create" | "update" | "terminate" | "delete";
        /**
         * Optional human-readable description of the action's role in the loop scenario.
         */
        note?: string;
      }[],
    ];
    /**
     * conflict cases (m-opt-lock), retry form. An ordered list of optimistic-lock UPDATE attempts applied (after any `given.apply`) in sequence, each asserting its own affected-row count — proving the m-opt-lock retry contract end-to-end: the first (stale-version) attempt affects 0 rows, then a retry that re-reads the now-fresh version and re-applies affects 1. When present, the single-attempt `then.statements` / `then.affectedRows` are absent and `then.tableState` (when authored) asserts the retried write landed.
     *
     * @minItems 1
     */
    attempts?: [
      {
        statements: GoldenStatements1;
        write: WriteRow;
        /**
         * conflict RETRY cases (m-opt-lock), temporal-close form. THIS attempt's close instant (→ the new `out_z` the milestone-closing UPDATE sets).
         */
        at?: string;
        /**
         * conflict RETRY cases (m-opt-lock), temporal-close form. THIS attempt's observed processing-from (`in_z`) — the optimistic gate the attempt binds (`and in_z = ?`). Absent in locking mode.
         */
        observedInZ?: string;
        /**
         * The rows this attempt's UPDATE must affect: 0 for the stale-version attempt (conflict), 1 for the fresh-version retry (success). Named to match the single-attempt `then.affectedRows` — no legacy `expected*` vocabulary survives in a migrated case body.
         */
        affectedRows: number;
        /**
         * Optional human-readable description of this attempt's role in the retry sequence.
         */
        note?: string;
      },
      ...{
        statements: GoldenStatements1;
        write: WriteRow;
        /**
         * conflict RETRY cases (m-opt-lock), temporal-close form. THIS attempt's close instant (→ the new `out_z` the milestone-closing UPDATE sets).
         */
        at?: string;
        /**
         * conflict RETRY cases (m-opt-lock), temporal-close form. THIS attempt's observed processing-from (`in_z`) — the optimistic gate the attempt binds (`and in_z = ?`). Absent in locking mode.
         */
        observedInZ?: string;
        /**
         * The rows this attempt's UPDATE must affect: 0 for the stale-version attempt (conflict), 1 for the fresh-version retry (success). Named to match the single-attempt `then.affectedRows` — no legacy `expected*` vocabulary survives in a migrated case body.
         */
        affectedRows: number;
        /**
         * Optional human-readable description of this attempt's role in the retry sequence.
         */
        note?: string;
      }[],
    ];
    write?: WriteRow1;
    /**
     * conflict cases (m-opt-lock), temporal-close form. The close instant a TEMPORAL / bitemporal optimistic conflict close records — the new `out_z` the milestone-closing UPDATE sets, keyed on the still-open current row. A GENERATING adapter DERIVES the close binds from it. Present on a temporal-conflict close; absent on a versioned conflict.
     */
    at?: string;
    /**
     * conflict cases (m-opt-lock), temporal-close form. The processing-from (`in_z`) the unit of work observed — the optimistic-lock version analogue a TEMPORAL / bitemporal entity gates on. In optimistic mode the close gains the `and in_z = ?` gate bound to this value; ABSENT in locking mode. It is the temporal analogue of a versioned write's `observedVersion`.
     */
    observedInZ?: string;
  };
  /**
   * Everything the case asserts after the action runs: the golden SQL an implementation is expected to emit (`statements`), the naive oracle (`referenceSql`), the observed data (`rows` / `graph` / `tableState`), the counts and codes (`affectedRows` / `errorClass` / `nativeCode` / `roundTrips`), the portable boundary `outcome`, and the numeric-comparison `tolerance`.
   */
  then?: {
    statements?: GoldenStatements2;
    referenceSql?: ReferenceSql;
    /**
     * The rows the query must return against the fixture data (single-statement / flat-result cases). An ABSTRACT-target inheritance read (m-inheritance, resolved Q6) additionally carries a `familyVariant` key per row — the CONCRETE subtype name of that row, materialized from the tag metadata map (`tagValue` -> subtype name), NOT projected as SQL — alongside the full concrete-superset columns (non-applicable subtype columns are null). Row objects stay open, so `familyVariant` needs no separate schema property.
     */
    rows?: {}[];
    /**
     * The assembled object graph a read must produce. For a deep fetch: the root rows, each carrying its eager-fetched related rows under the relationship name — OR, for a NARROWED polymorphic hop (m-deep-fetch, m-inheritance), under the DERIVED narrowed view key `<rel>[<Concrete>,<Concrete>]` (the local relationship name, the effective concrete-subtype set in canonical alphabetical order by entity name, no spaces; equivalent authored narrowings collapse to the same key). A polymorphic view's child objects additionally carry `familyVariant` (the concrete subtype name, materialized from the tag map, never projected as SQL). For a value-object materialization read (m-value-object): the owning entity's rows, each carrying its embedded value-object values decoded from the single structured-document column under the value-object name (a nested object for a `one` member, an ordered list for a `many` member, to arbitrary depth). Keyed by the root class name, whose value is a list of root objects; a related set appears under its relationship name (or narrowed view key), and a value-object member under its declared name. When a relationship reaches an ANCESTOR node already on the current path (a true BACK-REFERENCE cycle, m-snapshot-read), recursion stops and the cycle point carries a PK-ONLY stub — ONLY the referenced node's primary-key attribute(s), no other scalars, no relationships; a diamond-shared node at a NON-cyclic position keeps its full-value representation (the stub is scoped to true cycles). The stub proves nothing about sameness by itself — the cycle's same-node claim rides `then.identityChecks`.
     */
    graph?: {
      [k: string]: {}[];
    };
    /**
     * An ORDERED array of per-milestone snapshot graphs a `history` / `asOfRange` read materializes (m-snapshot-read, resolved Q5a), coexisting with the single-graph `then.graph` exactly as `then.rows` does: a single-instant read carries `graph`, a milestone-set read carries `graphs`. Each entry pairs a milestone `pin` — the EDGE coordinate this graph is pinned at, its OWN milestone's from-instant per as-of axis, NOT a shared root pin — with the assembled `graph` at that pin. So `history` returns one independently edge-pinned graph per milestone and `asOfRange` one per overlapping milestone (m-temporal-read edge-point reads). Each `graph` has the same root-class-keyed shape as `then.graph`.
     *
     * @minItems 1
     */
    graphs?: [
      {
        /**
         * The milestone edge coordinate this graph is pinned at, keyed by the as-of ATTRIBUTE name (`processingDate` / `businessDate`) whose value is the milestone's own from-instant (ISO-8601 UTC). Each graph in the array carries its OWN pin — edge-pinning, so a milestone-set read yields independently-pinned graphs, one per milestone, never a shared root pin.
         */
        pin: {
          [k: string]: string;
        };
        /**
         * The assembled object graph at this milestone's pin — the same root-class-keyed shape as `then.graph`.
         */
        graph: {
          [k: string]: {}[];
        };
      },
      ...{
        /**
         * The milestone edge coordinate this graph is pinned at, keyed by the as-of ATTRIBUTE name (`processingDate` / `businessDate`) whose value is the milestone's own from-instant (ISO-8601 UTC). Each graph in the array carries its OWN pin — edge-pinning, so a milestone-set read yields independently-pinned graphs, one per milestone, never a shared root pin.
         */
        pin: {
          [k: string]: string;
        };
        /**
         * The assembled object graph at this milestone's pin — the same root-class-keyed shape as `then.graph`.
         */
        graph: {
          [k: string]: {}[];
        };
      }[],
    ];
    /**
     * Declared reference-identity expectations over graph node positions (m-snapshot-read, resolved Q5b), mirroring the m-conformance-adapter `identityCheck`. Each entry is `{left, right, same}`: `left` / `right` are JSON Pointers into the case (into `then.graph` / `then.graphs`) naming the two compared node positions, and `same` is the asserted reference verdict. Authored where the graph JSON cannot express identity by value — the BACK-REFERENCE cycle (m-snapshot-read-011), whose PK-only stub proves nothing about sameness by itself: the cycle's same-node claim (`items[0].order` is the SAME node as the root, not a lookalike copy) rides this observation, graded as REFERENCE identity by each language's API Conformance Suite while the wire harness proves the accompanying golden SQL / graph. An adapter-delegated observable — the wire harness validates it is well-formed and skips grading it.
     *
     * @minItems 1
     */
    identityChecks?: [
      {
        left: JsonPointer;
        right: JsonPointer;
        same: boolean;
      },
      ...{
        left: JsonPointer;
        right: JsonPointer;
        same: boolean;
      }[],
    ];
    /**
     * The resulting table state a writeSequence or conflict case asserts after applying its ordered DML golden SQL. Keyed by table name; each value is the full set of rows that table must contain (order-insensitive). Row values speak DB column names; timestamp columns are authored as ISO-8601 UTC strings at core microsecond precision, with the open-bound `infinity` as the literal string `infinity`.
     */
    tableState?: {
      [k: string]: {}[];
    };
    /**
     * conflict cases (m-opt-lock), single-attempt form. The number of rows the golden UPDATE must affect after any `given.apply` is applied. A stale optimistic-lock version => 0 (conflict detected); a fresh version => 1 (success). This is the observable form of optimistic-lock conflict detection: `updatedRows != 1` is the conflict signal.
     */
    affectedRows?: number;
    /**
     * error cases (m-db-error). The neutral m-db-error error category a triggered DB error MUST classify to. uniqueViolation = duplicate-key; deadlock = deadlock or serialization failure (retriable); lockWaitTimeout = blocked past the lock-wait budget.
     */
    errorClass?: "uniqueViolation" | "deadlock" | "lockWaitTimeout";
    /**
     * error cases (m-db-error). The native code each dialect's driver MUST surface for this error, witnessing the divergence the classifier absorbs: Postgres a SQLSTATE string (e.g. "23505"), MariaDB a vendor errno (e.g. 1062). `errorClass` is the single dialect-neutral seam output; this is the per-dialect input.
     */
    nativeCode?: {
      [k: string]: string | number;
    };
    /**
     * boundary cases only. The portable expected outcome: `committed` (the unit of work eventually commits — the injected fault was auto-retried away), `aborted` (the closure threw and the boundary rolled back, withholding the callback's return value), or a surfaced error kind the caller observes (`optimistic-lock-conflict` when a conflict is not opted into retry; `deadlock` / `serialization-failure` / `lock-wait-timeout` when a transient exhausts the bound or the loop is disabled). The concrete per-language error type stays language-local; this is the neutral kind the suite asserts.
     */
    outcome?:
      | "committed"
      | "aborted"
      | "optimistic-lock-conflict"
      | "deadlock"
      | "serialization-failure"
      | "lock-wait-timeout";
    /**
     * rejected cases (m-value-object / m-op-algebra / m-inheritance negative validation, resolved Q7 + Q3/Q4). The normative rule the input violates, from a small closed vocabulary a model-aware PRE-SQL validator (and every language implementation) MUST enforce, asserted BEFORE any SQL is emitted. OPERATION rules: `nested-path-first-segment-not-value-object` (a nested path's first segment names no declared value object on the queried entity — m-op-algebra nested-predicate resolver MUST); `nested-path-unknown-member` (an intermediate segment names no declared nested value object, or a leaf names no declared attribute); `nested-literal-type-mismatch` (a nested comparison/membership literal's type differs from the leaf attribute's declared neutral type — m-op-algebra typed-literal MUST); `deep-fetch-value-object-segment` (a `deepFetch` path segment names a value object — m-value-object materialization/navigation contract 4, m-deep-fetch); `navigate-value-object-target` (a `navigate`/`exists`/`notExists` targets a value object — m-value-object contract 4, m-navigate); `find-root-value-object` (a find() is rooted at a value object — m-value-object contract 5). WRITE rules: `write-required-attribute-missing` (a required `nullable:false` attribute is absent at some depth — m-value-object write validation); `write-required-value-object-missing` (a required `nullable:false` nested value object is absent, or a required `many` array is absent — emptiness is fine); `write-value-type-mismatch` (a document field value's type differs from the declared attribute's neutral type). SUBTYPE-WRITE rules (m-inheritance x concrete-subtype writes — a schema-valid neutral write input a model-aware validator MUST refuse pre-SQL because it violates the concrete-subtype write protocol): `subtype-write-set-based-unsupported` (a keyless / predicate-driven write to an inheritance family — a per-object concrete-subtype write is KEYED, so a payload carrying no primary-key attribute denotes an unsupported set-based inheritance write, out of scope for this slice); `subtype-write-metadata-field` (a payload carries a FRAMEWORK-OWNED metadata field — the tag column, `tag`, `tagValue`, or `familyVariant` — which a concrete-subtype write DERIVES from the subtype's tagValue and never accepts as input); `subtype-write-sibling-attribute` (a payload carries an attribute declared on a SIBLING / unrelated concrete branch, so no single concrete subtype in the target's effective set accepts every authored field — the accepted fields are exactly the target's ancestry chain: root + abstract ancestors + own); `abstract-write-target` (a create / update / delete / terminate handle aimed at an ABSTRACT root or abstract subtype — writes are concrete-subtype only). MODEL rules (m-inheritance closed-tree family invariants, one per invariant per resolved Q4): `inheritance-unknown-parent` (a `parent` names no entity in the descriptor); `inheritance-cycle` (parent links form a cycle); `inheritance-missing-root` (the descriptor declares inheritance participants but NO root — a zero-root/abstract-orphan family; distinct from `inheritance-multiple-roots`, which is strictly more than one); `inheritance-multiple-roots` (a family reaches strictly MORE THAN ONE root, or the descriptor declares two roots for one tree; a family has exactly one root, so both zero and more-than-one are rejected, by `inheritance-missing-root` and this rule respectively); `inheritance-concrete-without-abstract-root` (a concrete subtype whose ancestry has no abstract root); `inheritance-abstract-node-with-table` (a `root` / `abstract-subtype` declares a physical table — also caught by the entity `table` conditional); `inheritance-abstract-node-fixture-rows` (fixture rows are keyed to an abstract root / abstract subtype — enforced at fixture load); `inheritance-strategy-redeclared` (a non-root participant redeclares `strategy`); `inheritance-missing-tag-value` (a table-per-hierarchy concrete subtype declares no `tagValue` — the shared table cannot discriminate its rows without one; the per-entity schema leaves `tagValue` optional and delegates its presence-under-table-per-hierarchy to this semantic rule); `inheritance-duplicate-tag-value` (two concrete subtypes in one table-per-hierarchy family share a `tagValue`); `inheritance-inconsistent-hierarchy-table` (table-per-hierarchy concrete subtypes map to different physical tables); `inheritance-tag-on-concrete-subtype-strategy` (a table-per-concrete-subtype family declares a `tag` or `tagValue`); `inheritance-temporal-axes-not-root-owned` (an `abstract-subtype` or `concrete-subtype` declares its own `asOfAttributes` — temporal axes are family-wide metadata that only the root may declare; every descendant inherits the root's complete axis set unchanged, whether the root itself is non-temporal or temporal, so this fires for both a non-temporal root with an axis-declaring descendant and a temporal root whose descendant redeclares, adds, removes, overrides, or shadows an axis); `inheritance-optimistic-locking-not-root-owned` (an `abstract-subtype` or `concrete-subtype` declares its own `optimisticLocking` attribute — the version attribute is family-wide metadata that only the root may declare; every descendant inherits the root's version column unchanged, whether the root itself is versioned or not, so this fires for both a non-versioned root with a version-declaring descendant and a versioned root whose descendant redeclares or adds a second version attribute). NARROW / SUBTYPE-SCOPE operation rules (m-op-algebra × m-inheritance — a schema-valid operation a model-aware validator MUST refuse pre-SQL): `narrow-outside-position` (a `narrow` node's resolved effective concrete-subtype set is not a SUBSET of the ACTIVE polymorphic position — the position threaded into the node, the read's `targetEntity` or the enclosing narrow's resolved set, CLAMPED to (intersected with) the position the node's `entity` names — so narrowing broadens beyond the position in scope, e.g. narrowing to a concrete outside the active set, or a nested narrow broadening back out of the set the enclosing narrow established); `narrow-empty-effective-set` (a `narrow`'s authored `to` list resolves to the EMPTY concrete-subtype set); `subtype-attribute-outside-narrow-scope` (a predicate references a concrete-subtype-declared attribute at a polymorphic position that is not narrowed to that subtype, so the attribute is not available to every concrete in the effective set); `narrow-outside-relationship-target` (a `narrow` in a navigation filter's `op`, or a deep-fetch path segment's `narrow`, either names an `entity` that is not the RELATIONSHIP TARGET exactly — a relationship-scope narrow MUST set `entity` to the target and reach subtypes via `to`, never by naming a broader or other position — or resolves its `to` set to a concrete-subtype set that is NOT a SUBSET of the RELATIONSHIP TARGET's effective concrete set; narrowing a polymorphic relationship to a concrete outside its reachable set, even one sharing the broader family root, is rejected; m-navigate / m-deep-fetch, resolved Q10).
     */
    rejectedRule?:
      | "nested-path-first-segment-not-value-object"
      | "nested-path-unknown-member"
      | "nested-literal-type-mismatch"
      | "deep-fetch-value-object-segment"
      | "navigate-value-object-target"
      | "find-root-value-object"
      | "write-required-attribute-missing"
      | "write-required-value-object-missing"
      | "write-value-type-mismatch"
      | "subtype-write-sibling-attribute"
      | "subtype-write-metadata-field"
      | "abstract-write-target"
      | "subtype-write-set-based-unsupported"
      | "inheritance-unknown-parent"
      | "inheritance-cycle"
      | "inheritance-missing-root"
      | "inheritance-multiple-roots"
      | "inheritance-concrete-without-abstract-root"
      | "inheritance-abstract-node-with-table"
      | "inheritance-abstract-node-fixture-rows"
      | "inheritance-strategy-redeclared"
      | "inheritance-missing-tag-value"
      | "inheritance-duplicate-tag-value"
      | "inheritance-inconsistent-hierarchy-table"
      | "inheritance-tag-on-concrete-subtype-strategy"
      | "inheritance-temporal-axes-not-root-owned"
      | "inheritance-optimistic-locking-not-root-owned"
      | "narrow-outside-position"
      | "narrow-empty-effective-set"
      | "subtype-attribute-outside-narrow-scope"
      | "narrow-outside-relationship-target";
    /**
     * Declared number of SQL statements for the operation. For a deep-fetch read case this MUST equal the number of authored/executed `then.statements` for each dialect; child SQL is omitted when an earlier level gathers no parent keys. For a writeSequence case it MUST equal the number of ordered DML statements; for a scenario case it MUST equal the SUM of the steps' per-step roundTrips.
     */
    roundTrips?: number;
    /**
     * Absolute tolerance for numeric row comparison. Omit for exact comparison (the default; money/counts/exact aggregates compare exactly in Decimal space). Declare ONLY for inherently inexact results (stddev/variance, repeating-decimal avg) that cannot be authored exactly and differ in scale across dialects; comparison then becomes abs(actual - expected) <= tolerance.
     */
    tolerance?: number;
  };
} & (
    | {
        shape: "read";
        when: {
          [k: string]: unknown;
        };
        then: {
          [k: string]: unknown;
        };
      }
    | {
        shape: "writeSequence";
        when: {
          [k: string]: unknown;
        };
        then: {
          [k: string]: unknown;
        };
      }
    | {
        shape: "scenario";
        when: {
          [k: string]: unknown;
        };
      }
    | (
        | {
            when: {
              [k: string]: unknown;
            };
            then: {
              [k: string]: unknown;
            };
          }
        | {
            when: {
              [k: string]: unknown;
            };
          }
      )
    | {
        shape: "coherence";
        when: {
          [k: string]: unknown;
        };
      }
    | (
        | {
            then: {
              [k: string]: unknown;
            };
          }
        | {
            when: {
              [k: string]: unknown;
            };
          }
      )
    | {
        shape: "concurrencySuccess";
        when: {
          concurrency: {
            rounds?: {
              A?: {
                [k: string]: unknown;
              };
              B?: {
                [k: string]: unknown;
              };
            }[];
          };
        };
        then?: {
          [k: string]: unknown;
        };
      }
    | {
        shape: "boundary";
        lane: "api-conformance";
        when: {
          [k: string]: unknown;
        };
        then: {
          [k: string]: unknown;
        };
      }
    | {
        when?: {
          [k: string]: unknown;
        };
      }
  );
/**
 * conflict / temporal-conflict cases (m-opt-lock) only. An ordered list of out-of-band naive statement entries the harness applies verbatim AFTER the fixtures load and BEFORE the golden UPDATE, simulating a concurrent transaction that mutated the row (e.g. bumping the optimistic-lock version) so the golden UPDATE's stale-version predicate now matches zero rows. Each entry is a `{sql, binds}` statement whose `sql` is a plain string (dialect-agnostic naive SQL, run on every dialect). Absent for the success case (the version is fresh, so the UPDATE affects one row).
 *
 * @minItems 1
 */
export type NaiveStatements = [
  StatementEntry & {
    sql?: string;
  },
  ...(StatementEntry & {
    sql?: string;
  })[],
];
/**
 * One node's step within a `when.concurrency` round. Carries its golden SQL as `statements` ({sql, binds} entries, dialect-keyed map form). On the concurrency-SUCCESS shape it additionally declares an explicit `kind`: a `read` step is fetched on its HELD session and its `expectRows` graded; a `write` step is executed and asserts only that it did not block/raise. `kind` is optional in this base def so the error/concurrency shape — whose only assertion is the classified error — carries no `kind`; the concurrency-success root branch requires it on every present step.
 */
export type ConcurrencyStep = {
  [k: string]: unknown;
} & {
  [k: string]: unknown;
} & {
  statements: GoldenStatements;
  /**
   * concurrency-success form only: the EXPLICIT read-vs-write discriminator the runners branch on (replacing the brittle SQL-verb sniffing). `read` — the step is fetched on its HELD session (`session.query`) and its rows graded against `expectRows`; `write` — the step is executed (`session.execute`) and asserts only that it did not block/raise. Structural: a `read` step MUST carry `expectRows`, a `write` step MUST omit it (the if/then below).
   */
  kind?: "read" | "write";
  /**
   * concurrency-success form only: the rows this node's read MUST return on its HELD session. A read step (`kind: read`) MUST declare it; a write step (`kind: write`) omits it. Absent on the error/concurrency shape, whose only assertion is the classified error. Its result form follows the read's nature (m-case-format *Read result form*, m-sql *Read projection*): a full-scalar shared read observes the object (INSTANCE-FORM / the object lane), a `distinct` / grouped witness is a projection over the values lane (ROW-FORM) — immaterial here, since every concurrency-success case reads the value-object-free `account`.
   */
  expectRows?: {}[];
} & {
  statements: GoldenStatements;
  /**
   * concurrency-success form only: the EXPLICIT read-vs-write discriminator the runners branch on (replacing the brittle SQL-verb sniffing). `read` — the step is fetched on its HELD session (`session.query`) and its rows graded against `expectRows`; `write` — the step is executed (`session.execute`) and asserts only that it did not block/raise. Structural: a `read` step MUST carry `expectRows`, a `write` step MUST omit it (the if/then below).
   */
  kind?: "read" | "write";
  /**
   * concurrency-success form only: the rows this node's read MUST return on its HELD session. A read step (`kind: read`) MUST declare it; a write step (`kind: write`) omits it. Absent on the error/concurrency shape, whose only assertion is the classified error. Its result form follows the read's nature (m-case-format *Read result form*, m-sql *Read projection*): a full-scalar shared read observes the object (INSTANCE-FORM / the object lane), a `distinct` / grouped witness is a projection over the values lane (ROW-FORM) — immaterial here, since every concurrency-success case reads the value-object-free `account`.
   */
  expectRows?: {}[];
};
/**
 * This node step's golden SQL, as an ordered list of `{sql, binds}` statement entries (dialect-keyed map form).
 *
 * @minItems 1
 */
export type GoldenStatements = [
  StatementEntry & {
    sql?: {};
  },
  ...(StatementEntry & {
    sql?: {};
  })[],
];
/**
 * This attempt's golden UPDATE, as an ordered list of `{sql, binds}` statement entries (dialect-keyed map form).
 *
 * @minItems 1
 */
export type GoldenStatements1 = [
  StatementEntry & {
    sql?: {};
  },
  ...(StatementEntry & {
    sql?: {};
  })[],
];
/**
 * The golden SQL an implementation is expected to emit, as an ordered list of `{sql, binds}` statement entries. Each entry's `sql` is a dialect-keyed map (`postgres` / `mariadb`) and its `binds` are authored once (dialect-agnostic), defaulting to `[]`. For a deep-fetch read the list has one entry per relationship/deep-fetch level; for a writeSequence one entry per DML statement. The per-level binds for a deep-fetch child level are the distinct parent keys gathered from the previous level, which the harness asserts equal the authored binds.
 *
 * @minItems 1
 */
export type GoldenStatements2 = [
  StatementEntry & {
    sql?: {};
  },
  ...(StatementEntry & {
    sql?: {};
  })[],
];
/**
 * Independent naive SQL oracle. Required for non-trivial reads and optional for trivial single-table predicates. A string is dialect-neutral; a dialect-keyed map MUST cover the exact golden SQL dialect set, which the harness verifies.
 */
export type ReferenceSql =
  | string
  | {
      [k: string]: string;
    };
/**
 * A JSON Pointer into the case (RFC 6901), naming a graph node position for a `then.identityChecks` entry. Mirrors the m-conformance-adapter `jsonPointer` def: the empty string (whole document) or a `/`-rooted path.
 */
export type JsonPointer = string;

/**
 * One logical statement in the execution sequence: a closed `{sql, binds}` object. `sql` is a plain string at naive locations (`given.apply`) or a dialect-keyed map (`postgres` / `mariadb`) at golden locations (`then.statements`, per-step `statements`); `binds` is authored once per statement (dialect-agnostic) and defaults to `[]`. The `{sql, binds}` wrapper keeps dialect keys and entry-level keys in separate namespaces, so the schema needs no reserved-key carve-outs. Golden and naive locations narrow `sql` to the map / string form respectively via `goldenStatements` / `naiveStatements`.
 */
export interface StatementEntry {
  sql:
    | string
    | {
        [k: string]: string;
      };
  /**
   * Bind values for the `?` placeholders in this statement's `sql`. Follows the same scalar-or-dialect-keyed polymorphism as `sql`: a flat ordered array when the bind holes are shared across dialects (the authored default), OR a dialect-keyed map of arrays when the hole structure diverges (e.g. Postgres carries per-segment JSON keys while MariaDB carries one `'$.a.b'` path bind). When a map, its keys MUST equal this entry's `sql` map's keys (harness-asserted). Defaults to empty.
   */
  binds?:
    | unknown[]
    | {
        [k: string]: unknown[];
      };
}
/**
 * A flat attribute-named write row at a FLUSH / MATERIALIZATION location (an m-opt-lock conflict / retry gated write, a writeSequence step) — the neutral write input (①), same vocabulary as a fixture row, PLUS the reserved framework-owned `observedVersion` control key. It is the canonical durable instruction row (`write-instruction.schema.json#/$defs/writeRow`) with ONE difference: `observedVersion` is legitimate FLUSH-TIME context here (the version a versioned write gates on / advances), whereas the canonical durable instruction FORBIDS it. Every OTHER key is an ENTITY ATTRIBUTE name OR a top-level VALUE-OBJECT name (a business/developer name like `id` / `orderedOn` / `address`, NOT a physical column like `ordered_on`), and its value is the shared canonical `writeRowValue` — a scalar literal / explicit `null`, a one-key DB-COMPUTED marker (`{ computed: "maxPlusOne" }` / `{ increment: <n> }`), or the WHOLE embedded value-object document — REFERENCED from `write-instruction.schema.json` rather than redefined. The adapter classifies each field by its metamodel role and derives the emitted column list + ORDER from `columnOrder(entity)` — never from JSON/YAML key order — so a marker-SHAPED value is a DB-computed marker vs a value-object document by MODEL ROLE, not by the value's SHAPE. A row object therefore CANNOT be `additionalProperties: false`: it names `observedVersion` and admits attribute / value-object keys via `additionalProperties`.
 */
export interface WriteRow {
  /**
   * The optimistic-lock version the unit of work read (m-opt-lock). A reserved control key, NOT an attribute/column: it is the gate/advance token (the advance `observedVersion + 1` and the `and version = ?` gate are DERIVED, never authored). Present on a versioned update; absent on a versioned insert and on a non-versioned write. This is FLUSH-TIME / materialization context — the durable instruction row (`write-instruction.schema.json#/$defs/writeRow`) forbids it, since the observation is never carried on the durable instruction (ADR 0013).
   */
  observedVersion?: number;
  /**
   * The value a neutral write-row field carries, classified by the field's metamodel role (resolved from `columnOrder(entity)`, NOT from the value's shape): a scalar literal / explicit `null` for a scalar attribute; a one-key DB-computed marker (`writeComputedMarker`) for a computed scalar column; or the WHOLE embedded value-object document — a JSON object for a `one` member, a JSON array of objects for a `many` member — bound atomically in its columnOrder position. The branches are NON-exclusive (`anyOf`): a marker-shaped value-object document validates via both the marker and the document branch, and the model role decides. This is the single shared value vocabulary `compatibility-case.schema.json`'s flush-context write row references rather than redefining.
   */
  [k: string]: (string | number | boolean | null) | WriteComputedMarker | ({} | unknown[]);
}
/**
 * A one-key DB-COMPUTED marker in a neutral write row: the attribute's value is derived by the database rather than authored as a literal bind, so the generating implementation emits the strategy's SQL fragment. Applies ONLY to a scalar-attribute column (a value-object column's value is always the literal document even when marker-shaped, disambiguated by metamodel role, not by shape).
 */
export interface WriteComputedMarker {
  /**
   * The pk-gen `max` strategy: the column is emitted as `coalesce(max(col), ?) + ?` — the computation folds into the INSERT's SQL, so a `max`-strategy insert stays statically derivable.
   */
  computed?: "maxPlusOne";
  /**
   * A self-referential advance emitted as `col = col + ?` (e.g. a sequence registry's `next_val`); the integer is the amount added.
   */
  increment?: number;
}
/**
 * A flat attribute-named write row at a FLUSH / MATERIALIZATION location (an m-opt-lock conflict / retry gated write, a writeSequence step) — the neutral write input (①), same vocabulary as a fixture row, PLUS the reserved framework-owned `observedVersion` control key. It is the canonical durable instruction row (`write-instruction.schema.json#/$defs/writeRow`) with ONE difference: `observedVersion` is legitimate FLUSH-TIME context here (the version a versioned write gates on / advances), whereas the canonical durable instruction FORBIDS it. Every OTHER key is an ENTITY ATTRIBUTE name OR a top-level VALUE-OBJECT name (a business/developer name like `id` / `orderedOn` / `address`, NOT a physical column like `ordered_on`), and its value is the shared canonical `writeRowValue` — a scalar literal / explicit `null`, a one-key DB-COMPUTED marker (`{ computed: "maxPlusOne" }` / `{ increment: <n> }`), or the WHOLE embedded value-object document — REFERENCED from `write-instruction.schema.json` rather than redefined. The adapter classifies each field by its metamodel role and derives the emitted column list + ORDER from `columnOrder(entity)` — never from JSON/YAML key order — so a marker-SHAPED value is a DB-computed marker vs a value-object document by MODEL ROLE, not by the value's SHAPE. A row object therefore CANNOT be `additionalProperties: false`: it names `observedVersion` and admits attribute / value-object keys via `additionalProperties`.
 */
export interface WriteRow1 {
  /**
   * The optimistic-lock version the unit of work read (m-opt-lock). A reserved control key, NOT an attribute/column: it is the gate/advance token (the advance `observedVersion + 1` and the `and version = ?` gate are DERIVED, never authored). Present on a versioned update; absent on a versioned insert and on a non-versioned write. This is FLUSH-TIME / materialization context — the durable instruction row (`write-instruction.schema.json#/$defs/writeRow`) forbids it, since the observation is never carried on the durable instruction (ADR 0013).
   */
  observedVersion?: number;
  /**
   * The value a neutral write-row field carries, classified by the field's metamodel role (resolved from `columnOrder(entity)`, NOT from the value's shape): a scalar literal / explicit `null` for a scalar attribute; a one-key DB-computed marker (`writeComputedMarker`) for a computed scalar column; or the WHOLE embedded value-object document — a JSON object for a `one` member, a JSON array of objects for a `many` member — bound atomically in its columnOrder position. The branches are NON-exclusive (`anyOf`): a marker-shaped value-object document validates via both the marker and the document branch, and the model role decides. This is the single shared value vocabulary `compatibility-case.schema.json`'s flush-context write row references rather than redefining.
   */
  [k: string]: (string | number | boolean | null) | WriteComputedMarker | ({} | unknown[]);
}
