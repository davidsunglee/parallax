/**
 * The `parallax(...)` factory + the runtime `Parallax` / `ParallaxTransaction`
 * handles (spec §1.2, §3).
 *
 * This is the thin typed surface over the SAME generic runtime the conformance
 * adapter uses (design Q1 Option B): a `find` builds a canonical operation with
 * the DSL, lowers it with the m-sql `compile` visitor, executes it through an
 * injected `ParallaxDatabase` port, and returns a lazy `ParallaxList`. No new
 * package — the composition root wires the runtime packages together.
 *
 * The generated `#parallax` barrel (`codegen/`) parameterizes this factory with
 * the bundled descriptor and exposes typed `px.<entities>` finders whose
 * predicates are the DSL entity symbols. The factory itself is entity-agnostic;
 * typing is layered on by the generated wrapper.
 */

import { isInfinity, toWire } from "@parallax/core";
import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";
import { ParallaxTransientError } from "@parallax/db";
import type { Dialect } from "@parallax/dialect";
import { ParallaxList } from "@parallax/lists";
import type { Metamodel } from "@parallax/metamodel";
import { type EntityMetadata, Metamodel as MetamodelReader } from "@parallax/metamodel";
import type { Operation } from "@parallax/operation";
import { compile } from "@parallax/sql";
import { buildFindOperation, type FindOptions, Predicate } from "../dsl/find.js";
import { type DeepFetchGraph, executeDeepFetch, isDeepFetchOperation } from "./deep-fetch.js";
import { rowMaterializer } from "./materialize.js";
import { executeRead } from "./read.js";
import { RuntimeSchema } from "./schema.js";
import {
  type Assignment,
  type Concurrency,
  isAuditOnly,
  isPkEqualityPredicate,
  type ObservedVersions,
  observedKey,
  ParallaxOptimisticLockError,
  TransactionWriter,
  type UpdateOptions,
  type WriteResult,
} from "./writes.js";

// The runtime consumes the abstract execution port (`ParallaxDatabase` +
// `ParallaxRow`) from `@parallax/db` (m-db-port port/adapter decomposition); a concrete
// adapter (the shippable `@parallax/db-postgres`, or an application's own driver)
// is injected at the composition root. Re-exported below so the generated
// `#parallax` barrel and applications reach the port types through one package.
export type { ParallaxDatabase, ParallaxRow } from "@parallax/db";

/** The clock strategy (spec §3.1) — supplies the transaction processing instant. */
export interface ParallaxClock {
  /** The current processing instant, as an ISO-8601 UTC microsecond string. */
  now(): string;
}

/** Options accepted by the `parallax(...)` factory (spec §1.2). */
export interface ParallaxOptions {
  /** The bound database adapter (a concrete `ParallaxDatabase`). */
  readonly database: ParallaxDatabase;
  /** The parsed canonical descriptor(s) the metamodel is read from. */
  readonly descriptor: unknown;
  /**
   * The bound m-dialect {@link Dialect} — the single authority for identifier quoting,
   * ORDER BY / NULL placement, the row-limit clause, read-lock application, and the
   * boundary value parsers. Injected so a MariaDB runtime swaps `mariadbDialect`
   * with no code edit; always supplied by the composition root.
   */
  readonly dialect: Dialect;
  /** The clock strategy; defaults to the system UTC clock. */
  readonly clock?: ParallaxClock;
}

/** The system UTC clock (microsecond-truncated), the default when none is given. */
const SYSTEM_CLOCK: ParallaxClock = {
  now(): string {
    return new Date().toISOString().replace("Z", "000+00:00");
  },
};

/**
 * An entity finder — `px.<entity>` — bound to one root entity. `find(predicate,
 * options)` builds the canonical operation (via the DSL), compiles it, and
 * returns a lazy `ParallaxList` of the resulting rows. `find()` with no predicate
 * is shorthand for `Entity.all()` (spec §1.3).
 */
export class EntityFinder<T extends ParallaxRow = ParallaxRow> {
  constructor(
    private readonly metamodel: Metamodel,
    private readonly entity: EntityMetadata,
    private readonly database: ParallaxDatabase,
    /** The injected m-dialect dialect — threaded to `compile()` and the row materializer. */
    private readonly dialect: Dialect,
    /**
     * A hook awaited INSIDE the lazy resolver, just before a read executes. In a
     * transaction this flushes the writer's buffered inserts so a dependent read
     * observes them (read-your-own-writes, `m-unit-work-001`) — a lazy flush that runs only
     * when the list actually resolves, never eagerly. Absent on the root handle.
     */
    private readonly beforeLoad?: () => Promise<void>,
    /**
     * The m-unit-work correctness mode of the enclosing unit of work, threaded to the shared
     * in-transaction read executor: a `locking`-mode read takes the m-unit-work shared row
     * lock (`for share of t0`, `m-read-lock-001`) so a concurrent transaction cannot mutate the
     * row out from under a read-then-write; an `optimistic`-mode read takes none.
     * Absent on the root handle (an out-of-transaction read never locks).
     */
    private readonly concurrency?: Concurrency,
    /**
     * A hook called with a fetched level's entity and its materialized rows, so the
     * unit of work can record the version it OBSERVED for each versioned row (the m-opt-lock
     * observed-version map a later gated / advancing update reads). A flat read calls
     * it once for this finder's entity; a deep fetch calls it once per fetched level
     * (root + each included child). Absent on the root handle.
     */
    private readonly onObserved?: (entity: EntityMetadata, rows: readonly ParallaxRow[]) => void,
  ) {}

  /**
   * Compile a DSL predicate + options to canonical SQL, execute it, and yield a
   * lazy `ParallaxList` keyed on the entity's primary key (same PK ⇒ same object).
   * The element type `T` is the generated managed-object type the barrel binds;
   * rows materialize to it at the adapter boundary (spec §2.2.1).
   *
   * `find()` with no predicate is shorthand for `find(Entity.all())` (spec §1.3):
   * the operand defaults to the entity-agnostic `all` predicate, which the
   * compiler roots at this finder's entity (`select … from <table>`, no `where`).
   */
  find(predicate?: Predicate, options: FindOptions = {}): ParallaxList<T> {
    const operation = buildFindOperation(predicate ?? new Predicate({ all: {} }), options);
    return this.runOperation(operation);
  }

  /**
   * Eager-fetch variant that returns the assembled graph AND the round-trip count
   * (spec §1.6): the decorated managed root objects (relationships attached under
   * their DSL names) plus the `1 + L` statement count that proves N+1 elimination.
   * A developer normally consumes `find(..., { includes })` as a list; the API
   * Conformance Suite (and any caller needing the round-trip proof) uses this to
   * assert both.
   */
  async findGraph(
    predicate: Predicate | undefined,
    options: FindOptions,
  ): Promise<{ rows: readonly T[]; roundTrips: number }> {
    const operation = buildFindOperation(predicate ?? new Predicate({ all: {} }), options);
    if (!isDeepFetchOperation(operation)) {
      const rows = await this.runOperation(operation).toArray();
      return { rows, roundTrips: 1 };
    }
    const graph = await this.executeGraph(operation);
    return { rows: graph.rows as readonly T[], roundTrips: graph.roundTrips };
  }

  /**
   * Run a pre-built canonical operation as a lazy list (the same wire form
   * `find` produces). Convenience for callers that already hold the m-op-algebra operation —
   * the API Conformance Suite builds an operation once (for its `assertSameOperation`
   * drift check) and runs it here, so the executed read and the asserted operation
   * are provably the same object.
   */
  findByOperation(operation: Operation): ParallaxList<T> {
    return this.runOperation(operation);
  }

  /** Deep-fetch a pre-built operation, returning the assembled graph + round trips. */
  async findGraphByOperation(
    operation: Operation,
  ): Promise<{ rows: readonly T[]; roundTrips: number }> {
    if (!isDeepFetchOperation(operation)) {
      const rows = await this.runOperation(operation).toArray();
      return { rows, roundTrips: 1 };
    }
    const graph = await this.executeGraph(operation);
    return { rows: graph.rows as readonly T[], roundTrips: graph.roundTrips };
  }

  /**
   * Compile + execute a raw canonical operation as a lazy list.
   *
   * Rows come back keyed by **physical column** with adapter-shaped scalars; the
   * per-entity materializer (spec §2.2.1) renames each column to its DSL property
   * name and coerces each scalar to its managed carrier. The identity key is
   * therefore the PK's **DSL name** (`attr.name`), not its physical column — the
   * rows are already renamed by the time the list dedupes them, so keying on the
   * column would look up an absent field and collapse identity.
   */
  private runOperation(operation: Operation): ParallaxList<T> {
    const identity = this.identityOption();
    // A deep fetch assembles a multi-level graph (spec §1.6): the list resolves to
    // the decorated managed root objects (relationships attached under their DSL
    // names). A flat read compiles + executes a single statement.
    if (isDeepFetchOperation(operation)) {
      return new ParallaxList<T>(async () => {
        await this.beforeLoad?.();
        return (await this.executeGraph(operation)).rows as readonly T[];
      }, identity);
    }
    const schema = new RuntimeSchema(this.metamodel, this.entity, this.dialect);
    // `compile()` applies the m-read-lock shared read-lock in-line for a `locking`-mode object
    // find (`for share of t0`, `m-read-lock-001`); the developer writes no locking SQL, so the
    // executor below just runs the already-locked statement.
    const { sql, binds } = compile(operation, schema, this.dialect, {
      locking: this.concurrency === "locking",
    });
    const materialize = rowMaterializer(this.entity, this.dialect);
    return new ParallaxList<T>(async () => {
      await this.beforeLoad?.();
      const rows = await executeRead(this.database, sql, binds as readonly unknown[]);
      const materialized = rows.map(materialize) as readonly T[];
      // Record the version this unit of work OBSERVED for each versioned row, so a
      // later keyed update gates on / advances from it (m-opt-lock framework-owned versions).
      this.onObserved?.(this.entity, materialized);
      return materialized;
    }, identity);
  }

  /**
   * The list's identity option (same logical row ⇒ same object). For a NON-temporal
   * entity the identity is its primary key. For a TEMPORAL (milestoned) entity a
   * single PK value spans many milestone rows (a `history` read returns them all),
   * so the identity is the FULL logical key — the primary key PLUS each as-of axis's
   * `from` attribute (the milestone start). Keying on the bare PK would collapse
   * distinct milestones to one object (the `m-temporal-read-004` / `m-temporal-read-016` history bug).
   */
  private identityOption(): { identity?: (row: T) => string | number | bigint | null | undefined } {
    const keyNames = this.identityKeyNames();
    if (keyNames.length === 0) {
      return {};
    }
    return {
      identity: (row) => keyNames.map((name) => String((row as ParallaxRow)[name] ?? " ")).join(""),
    };
  }

  /** The DSL attribute names that form the entity's logical identity (PK + as-of froms). */
  private identityKeyNames(): readonly string[] {
    const pkNames = this.entity.primaryKey().map((attr) => attr.name);
    const fromNames = this.entity
      .asOfAttributes()
      .map((axis) => this.entity.attributes().find((attr) => attr.column === axis.fromColumn)?.name)
      .filter((name): name is string => name !== undefined);
    return [...pkNames, ...fromNames];
  }

  /**
   * Execute a deep-fetch operation, returning the decorated managed graph + round
   * trips. In a transaction EVERY fetched level — the root read AND each included
   * child-level read — carries the SAME read context a flat read does: the m-unit-work shared
   * lock in `locking` mode and the m-opt-lock observed-version recording (keyed by each
   * level's own entity). So a versioned root OR a versioned included child can be
   * updated without a spurious `ParallaxReadBeforeWriteError`. On the root handle
   * both are inert (no lock, no recording).
   */
  private executeGraph(operation: Operation): Promise<DeepFetchGraph> {
    return executeDeepFetch(this.metamodel, operation, this.database, this.dialect, {
      concurrency: this.concurrency,
      onObserved: this.onObserved,
    });
  }
}

/**
 * The configured Parallax handle (`px`). Reads are available on the root handle;
 * writes are available only through {@link transaction} (spec §3). The generated
 * barrel wraps this with typed `px.<entities>` accessors; this base exposes the
 * entity-agnostic `entity(name)` finder and the transaction demarcation.
 */
export class Parallax {
  private readonly finders = new Map<string, EntityFinder>();

  constructor(
    private readonly metamodel: Metamodel,
    private readonly database: ParallaxDatabase,
    /** The injected m-dialect dialect, threaded to every finder + unit of work. */
    private readonly dialect: Dialect,
    private readonly clock: ParallaxClock,
  ) {}

  /** The generic metamodel reader (spec §2.2 generic layer): `px.metamodel`. */
  get metamodelReader(): Metamodel {
    return this.metamodel;
  }

  /**
   * A finder for one entity by domain class name (`px.entity("Order")`). The
   * generated barrel supplies the managed-object type `T` at the call site (rows
   * materialize to it at the adapter boundary).
   */
  entity<T extends ParallaxRow = ParallaxRow>(name: string): EntityFinder<T> {
    let finder = this.finders.get(name);
    if (finder === undefined) {
      finder = new EntityFinder(
        this.metamodel,
        this.metamodel.entity(name),
        this.database,
        this.dialect,
      );
      this.finders.set(name, finder);
    }
    return finder as EntityFinder<T>;
  }

  /**
   * Closure-demarcated unit of work (spec §3): `await px.transaction(async tx =>
   * { … }, options)`. Returns the callback's resolved value after commit; a throw
   * rolls back. Requires a `transaction`-capable database adapter.
   *
   * `options.concurrency` selects the m-unit-work correctness strategy (default `locking`):
   * in `locking` mode in-transaction reads take the automatic shared row lock
   * (m-unit-work); in `optimistic` mode reads take no lock and versioned updates gate on the
   * observed version (m-opt-lock).
   *
   * The boundary offers **bounded automatic retry** (m-auto-retry/m-opt-lock, core ADR 0008 / ts ADR 0026): on a
   * retriable failure it rolls back, discards stale state, and re-executes the body
   * against fresh state, up to `options.retries` re-executions (default 10; `0`
   * disables the loop). Each attempt opens a **fresh** driver transaction and a
   * **fresh** `ParallaxTransaction` — so the per-unit-of-work observed-version map
   * is discarded by construction and the retry re-reads (the "invalidate stale
   * state" step; there is no process-wide cache to invalidate). Transient database
   * failures (`ParallaxTransientError.retriable` — deadlock / serialization) are
   * retried by default; an optimistic-lock conflict (`ParallaxOptimisticLockError`)
   * is retried only when `options.retryOptimisticConflicts` is set.
   */
  async transaction<T>(
    body: (tx: ParallaxTransaction) => Promise<T>,
    options: TransactionOptions = {},
  ): Promise<T> {
    if (this.database.transaction === undefined) {
      throw new Error("the configured ParallaxDatabase does not support transactions");
    }
    const runTransaction = this.database.transaction.bind(this.database);
    const concurrency: Concurrency = options.concurrency ?? "locking";
    const retries = options.retries ?? DEFAULT_RETRIES;
    const retryOptimisticConflicts = options.retryOptimisticConflicts ?? false;

    let attempt = 0;
    for (;;) {
      try {
        // Each attempt opens a FRESH driver transaction + a FRESH ParallaxTransaction
        // (a fresh observed-version map), so a retry re-reads current state.
        return await runTransaction(async (boundDb) => {
          const tx = new ParallaxTransaction(
            this.metamodel,
            boundDb,
            this.dialect,
            this.clock.now(),
            concurrency,
          );
          const result = await body(tx);
          // Flush any buffered writes at the unit-of-work boundary (spec §3: no
          // public flush; the runtime flushes at commit) before the tx commits.
          await tx.flushWrites();
          return result;
        });
      } catch (error) {
        if (attempt < retries && isRetriableFailure(error, retryOptimisticConflicts)) {
          attempt += 1;
          continue;
        }
        // Surface the failure. If it survived one or more retries, annotate the
        // message with the attempt count so a hot loop is diagnosable (the error
        // TYPE is preserved — a caller's `instanceof` check still holds).
        if (attempt > 0 && error instanceof Error) {
          error.message = `${error.message} (surfaced after ${attempt + 1} attempts)`;
        }
        throw error;
      }
    }
  }
}

/** The default bound on automatic unit-of-work re-executions (m-auto-retry/m-opt-lock; Reladomo parity). */
const DEFAULT_RETRIES = 10;

/**
 * Whether a failed unit-of-work attempt is retriable. A transient database failure
 * (`ParallaxTransientError.retriable` — the `deadlock` category, covering deadlock
 * and serialization failure) is always retriable; an optimistic-lock conflict joins
 * the retriable set only when the unit of work opted in. Everything else surfaces.
 */
function isRetriableFailure(error: unknown, retryOptimisticConflicts: boolean): boolean {
  if (error instanceof ParallaxTransientError) {
    return error.retriable;
  }
  if (error instanceof ParallaxOptimisticLockError) {
    return retryOptimisticConflicts;
  }
  return false;
}

/** Options for a unit of work (spec §3 / m-auto-retry strategy selection + bounded retry). */
export interface TransactionOptions {
  /**
   * The correctness strategy for this unit of work. `locking` (the default) takes
   * the m-read-lock implicit shared read lock on in-transaction reads; `optimistic` (m-opt-lock)
   * takes no lock and gates versioned updates on the observed version.
   */
  readonly concurrency?: Concurrency;
  /**
   * The bound on automatic re-executions of the body after a retriable failure
   * (m-auto-retry/m-opt-lock bounded automatic retry). Default 10; `0` disables the loop, so even a
   * transient failure surfaces after the first attempt.
   */
  readonly retries?: number;
  /**
   * Whether an optimistic-lock conflict (`ParallaxOptimisticLockError`) joins the
   * retriable set for this unit of work. Default false — a conflict surfaces to the
   * caller after one attempt. Transient database failures are always retriable
   * regardless of this flag.
   */
  readonly retryOptimisticConflicts?: boolean;
}

/**
 * A per-entity in-transaction handle (`tx.<entity>`, spec §3, §3.1): the same
 * reads as the root finder PLUS the write surface (`create` / `update` /
 * `terminate` / `delete`). Reads take the automatic in-transaction read lock (m-read-lock)
 * at the adapter boundary; writes buffer / chain through the shared
 * {@link TransactionWriter} (spec §3.1). The generated barrel wraps this with the
 * managed-object type `T`.
 */
export class TransactionEntity<T extends ParallaxRow = ParallaxRow> {
  constructor(
    private readonly finder: EntityFinder<T>,
    private readonly entity: EntityMetadata,
    private readonly writer: TransactionWriter,
  ) {}

  /** An in-transaction read (spec §1.3, §3): takes the automatic read lock (m-read-lock). */
  find(predicate?: Predicate, options: FindOptions = {}): ParallaxList<T> {
    return this.finder.find(predicate, options);
  }

  /**
   * `create` a new managed object from named input (spec §3.1). A non-temporal
   * entity buffers the insert (flushed set-based + FK-safe at commit); an
   * audit-only entity opens a milestone at the transaction processing instant.
   */
  async create(input: Record<string, unknown>): Promise<void> {
    await this.writer.create(this.entity, input);
  }

  /**
   * `update` the selected row(s) (spec §3): explicit assignment array, not a partial.
   *
   * A versioned entity whose predicate is NOT a single primary-key equality is a
   * SET-BASED versioned update, which MATERIALIZES (m-opt-lock, core ADR 0014): resolve the
   * predicate to rows through the OBSERVING finder — which records each row's
   * observed version and, in `locking` mode, takes the m-read-lock shared lock (satisfying
   * read-before-write) — then emit one keyed per-object update per resolved row.
   * A keyed (single-pk) versioned update and EVERY non-versioned update keep the
   * direct write path (the latter's readless batched form is unchanged, core ADR 0014).
   */
  async update(predicate: Predicate, options: UpdateOptions): Promise<WriteResult> {
    if (
      this.entity.versionAttribute() !== undefined &&
      !isPkEqualityPredicate(this.entity, predicate)
    ) {
      const pkName = this.entity.primaryKey()[0]?.name;
      const rows = await this.finder.find(predicate).toArray();
      const pks = rows.map((row) => (row as ParallaxRow)[pkName as string]);
      return this.writer.versionedSetUpdate(this.entity, pks, options);
    }
    return this.writer.update(this.entity, predicate, options);
  }

  /** `terminate` (audit-only temporal removal): close the current milestone (spec §3.1). */
  async terminate(predicate: Predicate): Promise<WriteResult> {
    return this.writer.terminate(this.entity, predicate);
  }

  /** `delete` (physical removal, non-temporal entities) — spec §3.1. */
  async delete(predicate: Predicate): Promise<WriteResult> {
    return this.writer.delete(this.entity, predicate);
  }
}

/**
 * The active transaction handle (`tx`, spec §3, §3.1). Exposes the same reads as
 * the root handle plus temporal writes; it is invalid after its callback
 * completes. Processing instants come from the clock (captured at open), never
 * per-operation options, so production code cannot rewrite audit history.
 */
export class ParallaxTransaction {
  private readonly handles = new Map<string, TransactionEntity>();
  /** The shared unit-of-work writer (buffers inserts; chains audit milestones). */
  readonly writer: TransactionWriter;
  /**
   * The per-unit-of-work observed-version map (`entity#pk → version`), shared with
   * the writer: a locking/optimistic keyed update reads the version a prior in-
   * transaction find hydrated (m-opt-lock framework-owned versions).
   */
  private readonly observed: ObservedVersions = new Map();

  constructor(
    private readonly metamodel: Metamodel,
    private readonly database: ParallaxDatabase,
    /** The injected m-dialect dialect, threaded to the in-transaction finders' reads. */
    private readonly dialect: Dialect,
    /** The processing instant captured when the transaction opened (spec §3.1). */
    readonly processingInstant: string,
    /** The m-unit-work correctness strategy for this unit of work (default `locking`). */
    readonly concurrency: Concurrency = "locking",
  ) {
    this.writer = new TransactionWriter(
      database,
      this.dialect,
      processingInstant,
      concurrency,
      this.observed,
    );
  }

  /**
   * A per-entity in-transaction handle by domain class name (`tx.entity("Balance")`),
   * carrying both the reads and the write surface. The generated barrel supplies
   * the managed-object type `T` at the call site.
   */
  entity<T extends ParallaxRow = ParallaxRow>(name: string): TransactionEntity<T> {
    let handle = this.handles.get(name);
    if (handle === undefined) {
      const metadata = this.metamodel.entity(name);
      // The in-transaction finder flushes the writer's buffered inserts before a
      // read executes (lazily, inside the list resolver), so a dependent find
      // observes the just-buffered write (read-your-own-writes, `m-unit-work-001`). In
      // `locking` mode the read also takes the m-read-lock shared lock (`m-read-lock-001`); either way
      // it records the versions it observed so a later versioned update can gate
      // on / advance from them (m-opt-lock).
      const finder = new EntityFinder(
        this.metamodel,
        metadata,
        this.database,
        this.dialect,
        () => this.writer.flush(),
        this.concurrency,
        // A flat read reports this finder's entity; a deep fetch reports each fetched
        // level's own entity (root + included children), so a versioned child read is
        // recorded under the CHILD entity, not the root.
        (entity, rows) => this.recordObserved(entity, rows),
      );
      handle = new TransactionEntity(finder, metadata, this.writer);
      this.handles.set(name, handle);
    }
    return handle as TransactionEntity<T>;
  }

  /**
   * Record the optimistic key this unit of work observed for each hydrated row
   * (`entity#pk → version | in_z`), so a subsequent gated write gates on it
   * (optimistic mode) or advances from it (versioned entities, both modes):
   *
   *  - a VERSIONED entity records the observed `version` NUMBER;
   *  - a processing-axis TEMPORAL (audit-only) entity — which carries no version
   *    column — records the observed processing-from (`in_z`) as its wire STRING, the
   *    version analogue an optimistic close gates on (m-temporal-read/m-opt-lock). Recording FILTERS to the
   *    CURRENT (`out_z = infinity`) milestone: a multi-milestone as-of/history read
   *    returns both the current row AND closed rows for one pk, so recording every row
   *    (last-row-wins) could overwrite the current `in_z` with a stale closed one — the
   *    gate must key on the CURRENT milestone's processing-from.
   *
   * A non-versioned, non-temporal entity records nothing.
   */
  private recordObserved(entity: EntityMetadata, rows: readonly ParallaxRow[]): void {
    const pk = entity.primaryKey()[0];
    if (pk === undefined) {
      return;
    }
    const version = entity.versionAttribute();
    if (version !== undefined) {
      for (const row of rows) {
        const pkValue = row[pk.name];
        const versionValue = row[version.name];
        if (pkValue != null && versionValue != null) {
          this.observed.set(observedKey(entity.name, pkValue), Number(versionValue));
        }
      }
      return;
    }
    const processingFrom = entity.processingFromAttribute();
    if (processingFrom === undefined) {
      return;
    }
    // Only the CURRENT milestone (`out_z = infinity`) carries the observed `in_z` an
    // optimistic close gates on; skip closed milestones so a history/as-of read that
    // returns them too cannot overwrite the current observation (last-row-wins). If a
    // temporal entity somehow declares no processing-to attribute we cannot identify
    // the current milestone, so we record NOTHING rather than risk latching a stale
    // `in_z` — a subsequent gated close then read-before-writes, which is safe.
    const processingTo = entity.processingToAttribute();
    if (processingTo === undefined) {
      return;
    }
    for (const row of rows) {
      const pkValue = row[pk.name];
      const inZValue = row[processingFrom.name];
      if (pkValue != null && inZValue != null && isInfinity(toWire(row[processingTo.name]))) {
        this.observed.set(observedKey(entity.name, pkValue), toWire(inZValue) as string);
      }
    }
  }

  /** True when the entity chains audit milestones (declares a processing axis). */
  isAuditOnly(name: string): boolean {
    return isAuditOnly(this.metamodel.entity(name));
  }

  /** Flush buffered writes at the unit-of-work boundary (called at commit). */
  async flushWrites(): Promise<void> {
    await this.writer.flush();
  }
}

/** The named-assignment helper the API Conformance Suite write cases use (`{ attr, value }`). */
export type { Assignment };

/**
 * Create a configured Parallax handle (spec §1.2). Reads the bundled descriptor
 * into the m-descriptor metamodel, binds the database adapter and clock, and returns the
 * `px` handle. The generated `parallax(...)` in the `#parallax` barrel calls this
 * with its bundled descriptor and wraps the result with typed accessors.
 */
export function createParallax(options: ParallaxOptions): Parallax {
  const metamodel = MetamodelReader.fromDescriptor(options.descriptor);
  return new Parallax(metamodel, options.database, options.dialect, options.clock ?? SYSTEM_CLOCK);
}
