/**
 * The `parallax(...)` factory + the runtime `Parallax` / `ParallaxTransaction`
 * handles (spec §1.2, §3).
 *
 * This is the thin typed surface over the SAME generic runtime the conformance
 * adapter uses (design Q1 Option B): a `find` builds a canonical operation with
 * the DSL, lowers it with the M3 `compile` visitor, executes it through an
 * injected `ParallaxDatabase` port, and returns a lazy `ParallaxList`. No new
 * package — the composition root wires the runtime packages together.
 *
 * The generated `#parallax` barrel (`codegen/`) parameterizes this factory with
 * the bundled descriptor and exposes typed `px.<entities>` finders whose
 * predicates are the DSL entity symbols. The factory itself is entity-agnostic;
 * typing is layered on by the generated wrapper.
 */

import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";
import { ParallaxList } from "@parallax/lists";
import type { Metamodel } from "@parallax/metamodel";
import { type EntityMetadata, Metamodel as MetamodelReader } from "@parallax/metamodel";
import type { Operation } from "@parallax/operation";
import { compile } from "@parallax/sql";
import { buildFindOperation, type FindOptions, Predicate } from "../dsl/find.js";
import { type DeepFetchGraph, executeDeepFetch, isDeepFetchOperation } from "./deep-fetch.js";
import { rowMaterializer } from "./materialize.js";
import { RuntimeSchema } from "./schema.js";
import {
  type Assignment,
  isAuditOnly,
  TransactionWriter,
  type UpdateOptions,
  type WriteResult,
} from "./writes.js";

// The runtime consumes the abstract execution port (`ParallaxDatabase` +
// `ParallaxRow`) from `@parallax/db` (M11 port/adapter decomposition); a concrete
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
    /**
     * A hook awaited INSIDE the lazy resolver, just before a read executes. In a
     * transaction this flushes the writer's buffered inserts so a dependent read
     * observes them (read-your-own-writes, `0607`) — a lazy flush that runs only
     * when the list actually resolves, never eagerly. Absent on the root handle.
     */
    private readonly beforeLoad?: () => Promise<void>,
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
   * `find` produces). Convenience for callers that already hold the M2 operation —
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
    const schema = new RuntimeSchema(this.metamodel, this.entity);
    const { sql, binds } = compile(operation, schema);
    const materialize = rowMaterializer(this.entity);
    return new ParallaxList<T>(async () => {
      await this.beforeLoad?.();
      const rows = await this.database.execute(sql, binds as readonly unknown[]);
      return rows.map(materialize) as readonly T[];
    }, identity);
  }

  /**
   * The list's identity option (same logical row ⇒ same object). For a NON-temporal
   * entity the identity is its primary key. For a TEMPORAL (milestoned) entity a
   * single PK value spans many milestone rows (a `history` read returns them all),
   * so the identity is the FULL logical key — the primary key PLUS each as-of axis's
   * `from` attribute (the milestone start). Keying on the bare PK would collapse
   * distinct milestones to one object (the `0504` / `0804` history bug).
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

  /** Execute a deep-fetch operation, returning the decorated managed graph + round trips. */
  private executeGraph(operation: Operation): Promise<DeepFetchGraph> {
    return executeDeepFetch(this.metamodel, operation, this.database);
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
      finder = new EntityFinder(this.metamodel, this.metamodel.entity(name), this.database);
      this.finders.set(name, finder);
    }
    return finder as EntityFinder<T>;
  }

  /**
   * Closure-demarcated unit of work (spec §3): `await px.transaction(async tx =>
   * { … })`. Returns the callback's resolved value after commit; a throw rolls
   * back. Requires a `transaction`-capable database adapter. Reads through `tx`
   * take the automatic in-transaction read lock (M8) at the adapter boundary.
   */
  async transaction<T>(body: (tx: ParallaxTransaction) => Promise<T>): Promise<T> {
    if (this.database.transaction === undefined) {
      throw new Error("the configured ParallaxDatabase does not support transactions");
    }
    return this.database.transaction(async (boundDb) => {
      const tx = new ParallaxTransaction(this.metamodel, boundDb, this.clock.now());
      const result = await body(tx);
      // Flush any buffered writes at the unit-of-work boundary (spec §3: no public
      // flush; the runtime flushes at commit) before the transaction commits.
      await tx.flushWrites();
      return result;
    });
  }
}

/**
 * A per-entity in-transaction handle (`tx.<entity>`, spec §3, §3.1): the same
 * reads as the root finder PLUS the write surface (`create` / `update` /
 * `terminate` / `delete`). Reads take the automatic in-transaction read lock (M8)
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

  /** An in-transaction read (spec §1.3, §3): takes the automatic read lock (M8). */
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

  /** `update` the selected row (spec §3): explicit assignment array, not a partial. */
  async update(predicate: Predicate, options: UpdateOptions): Promise<WriteResult> {
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

  constructor(
    private readonly metamodel: Metamodel,
    private readonly database: ParallaxDatabase,
    /** The processing instant captured when the transaction opened (spec §3.1). */
    readonly processingInstant: string,
  ) {
    this.writer = new TransactionWriter(database, processingInstant);
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
      // observes the just-buffered write (read-your-own-writes, `0607`).
      const finder = new EntityFinder(this.metamodel, metadata, this.database, () =>
        this.writer.flush(),
      );
      handle = new TransactionEntity(finder, metadata, this.writer);
      this.handles.set(name, handle);
    }
    return handle as TransactionEntity<T>;
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
 * into the M1 metamodel, binds the database adapter and clock, and returns the
 * `px` handle. The generated `parallax(...)` in the `#parallax` barrel calls this
 * with its bundled descriptor and wraps the result with typed accessors.
 */
export function createParallax(options: ParallaxOptions): Parallax {
  const metamodel = MetamodelReader.fromDescriptor(options.descriptor);
  return new Parallax(metamodel, options.database, options.clock ?? SYSTEM_CLOCK);
}
