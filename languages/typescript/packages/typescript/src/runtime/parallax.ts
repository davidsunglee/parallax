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

import { ParallaxList } from "@parallax/lists";
import type { Metamodel } from "@parallax/metamodel";
import { type EntityMetadata, Metamodel as MetamodelReader } from "@parallax/metamodel";
import type { Operation } from "@parallax/operation";
import { compile } from "@parallax/sql";
import { buildFindOperation, type FindOptions, type Predicate } from "../dsl/find.js";
import { RuntimeSchema } from "./schema.js";

/** A row as the database port returns it (physical column name → neutral value). */
export type ParallaxRow = Record<string, unknown>;

/**
 * The database port the factory executes through. A concrete adapter (the
 * Testcontainers Postgres provider at the composition root, or an application's
 * own pool) implements it; the runtime imports no driver. `query` runs a read;
 * `transaction` runs a callback with a bound connection.
 */
export interface ParallaxDatabase {
  /** Execute a compiled read (`?`-placeholder SQL + ordered binds) → rows. */
  query(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]>;
  /**
   * Run `body` inside a database transaction, committing on resolve and rolling
   * back on throw. A connection-bound `ParallaxDatabase` is passed to `body`.
   */
  transaction?<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T>;
}

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
  ) {}

  /**
   * Compile a DSL predicate + options to canonical SQL, execute it, and yield a
   * lazy `ParallaxList` keyed on the entity's primary key (same PK ⇒ same object).
   * The element type `T` is the generated managed-object type the barrel binds;
   * rows materialize to it at the adapter boundary (spec §2.2.1).
   */
  find(predicate: Predicate, options: FindOptions = {}): ParallaxList<T> {
    const operation = buildFindOperation(predicate, options);
    return this.runOperation(operation);
  }

  /** Compile + execute a raw canonical operation as a lazy list. */
  private runOperation(operation: Operation): ParallaxList<T> {
    const schema = new RuntimeSchema(this.metamodel, this.entity);
    const { sql, binds } = compile(operation, schema);
    const pkColumn = this.entity.primaryKey()[0]?.column;
    return new ParallaxList<T>(
      async () => (await this.database.query(sql, binds as readonly unknown[])) as readonly T[],
      pkColumn === undefined
        ? {}
        : { identity: (row) => row[pkColumn] as string | number | bigint | null | undefined },
    );
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
    return this.database.transaction((boundDb) => {
      const tx = new ParallaxTransaction(this.metamodel, boundDb, this.clock.now());
      return body(tx);
    });
  }
}

/**
 * The active transaction handle (`tx`, spec §3, §3.1). Exposes the same reads as
 * the root handle plus temporal writes; it is invalid after its callback
 * completes. Processing instants come from the clock (captured at open), never
 * per-operation options, so production code cannot rewrite audit history.
 */
export class ParallaxTransaction {
  private readonly finders = new Map<string, EntityFinder>();

  constructor(
    private readonly metamodel: Metamodel,
    private readonly database: ParallaxDatabase,
    /** The processing instant captured when the transaction opened (spec §3.1). */
    readonly processingInstant: string,
  ) {}

  /** A finder for one entity by domain class name (in-transaction reads). */
  entity<T extends ParallaxRow = ParallaxRow>(name: string): EntityFinder<T> {
    let finder = this.finders.get(name);
    if (finder === undefined) {
      finder = new EntityFinder(this.metamodel, this.metamodel.entity(name), this.database);
      this.finders.set(name, finder);
    }
    return finder as EntityFinder<T>;
  }
}

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
