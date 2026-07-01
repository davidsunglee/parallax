/**
 * `@parallax/db-postgres` — the shippable Postgres **adapter** (M11 decomposition,
 * layer 3): a concrete `ParallaxDatabase` over the `postgres` (porsager) driver.
 *
 * This is the first thing a real application imports for Postgres connectivity.
 * It takes a **connection string** (or an already-configured porsager pool) and
 * implements the abstract `@parallax/db` port: `execute` runs a compiled
 * `?`-placeholder statement, `transaction` demarcates a unit of work, and every
 * returned scalar is a **managed** value (`bigint` / `ParallaxDecimal` /
 * `Temporal.*` / `Uint8Array` / string) normalized at the boundary (§2.2.1).
 *
 * It depends only on the **port** (`@parallax/db`) and the **pure dialect layer**
 * (`@parallax/dialect`): the dialect owns the `?`→`$n` translation and every
 * parse rule; the adapter owns only driver setup + OID registration. It has **no**
 * `@parallax/typescript` dependency, **no** Testcontainers dependency, and **no**
 * wire / grading logic — a future `@parallax/db-mysql` slots in beside it
 * identically.
 */
import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";
import { toPositionalPlaceholders } from "@parallax/dialect";
import postgres, { type Options, type Sql } from "postgres";
import { managedTypes } from "./oids.js";

/**
 * porsager types `unsafe`'s parameter array over the connection's custom-type
 * map; because we register parsers via an untyped `types` map, that map widens to
 * `never`, so a plain `unknown[]` is not assignable. The binds are already
 * neutral scalars / wire-form values the driver serializes, so this localized
 * cast at the driver boundary is sound.
 */
type DriverParams = Parameters<Sql["unsafe"]>[1];
function asParams(binds: readonly unknown[]): DriverParams {
  return binds as DriverParams;
}

/** Options for constructing a `PostgresDatabase` (beyond the porsager defaults). */
export type PostgresDatabaseOptions = Options<Record<string, never>>;

/**
 * A concrete `ParallaxDatabase` over Postgres. Construct it from a connection
 * string with {@link PostgresDatabase.fromConnectionString} (the common path for
 * an application) or wrap an existing porsager pool with
 * {@link PostgresDatabase.fromPool} (e.g. a shared app pool, or a
 * container-bound one).
 */
export class PostgresDatabase implements ParallaxDatabase {
  private constructor(private readonly sql: Sql) {}

  /**
   * Build an adapter over a fresh porsager pool for `connectionString`, with the
   * managed-type OID registration applied. `options` merges over the adapter
   * defaults (single-connection pool, notices silenced) for a caller that needs
   * a larger pool or its own settings.
   */
  static fromConnectionString(
    connectionString: string,
    options: PostgresDatabaseOptions = {},
  ): PostgresDatabase {
    const sql = postgres(connectionString, {
      // biome-ignore lint/suspicious/noExplicitAny: porsager's custom-type map is loosely typed.
      types: managedTypes() as any,
      max: 1,
      onnotice: () => {},
      ...options,
    });
    return new PostgresDatabase(sql);
  }

  /**
   * Wrap an already-configured porsager pool. The caller is responsible for
   * registering the managed-type parsers ({@link managedTypes}) on that pool if it
   * wants managed row scalars; use {@link fromConnectionString} to get that wiring
   * for free.
   */
  static fromPool(sql: Sql): PostgresDatabase {
    return new PostgresDatabase(sql);
  }

  /** The underlying porsager pool (for provisioning at the composition root). */
  get pool(): Sql {
    return this.sql;
  }

  /**
   * Execute a compiled statement (`?`-placeholder SQL + ordered binds). The
   * dialect translates `?`→`$n`; every returned scalar is a managed value
   * (§2.2.1). Rows are copied into plain objects so callers never hold a driver
   * row proxy.
   */
  async execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    const text = toPositionalPlaceholders(sql);
    const result = await this.sql.unsafe(text, asParams(binds));
    return [...result].map((row) => ({ ...(row as ParallaxRow) }));
  }

  /**
   * Run `body` inside a Postgres transaction (porsager `sql.begin`), committing on
   * resolve and rolling back on throw. A connection-bound `PostgresDatabase` (over
   * the reserved connection) is passed to `body`, so its reads/writes run inside
   * the transaction.
   */
  transaction<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T> {
    return this.sql.begin((reserved) =>
      body(new PostgresDatabase(reserved as unknown as Sql)),
    ) as Promise<T>;
  }

  /** Close the underlying pool (no-op for a wrapped, externally-owned pool caller). */
  async close(): Promise<void> {
    await this.sql.end({ timeout: 5 });
  }
}
