/**
 * `@parallax/db-postgres` — the shippable Postgres **adapter** (m-db-port decomposition,
 * layer 3): a concrete `ParallaxDatabase` over the `postgres` (porsager) driver.
 *
 * This is the first thing a real application imports for Postgres connectivity.
 * It takes a **connection string** (or an already-configured porsager pool) and
 * implements the abstract `@parallax/db` port: `execute` runs a compiled
 * `?`-placeholder row-returning statement, `executeWrite` reports a DML
 * statement's native affected-row count, `transaction` demarcates a unit of work,
 * and every returned scalar is a **managed** value (`bigint` / `ParallaxDecimal` /
 * `Temporal.*` / `Uint8Array` / string) normalized at the boundary (§3.2.1).
 *
 * It depends only on the **port** (`@parallax/db`) and the **pure dialect layer**
 * (`@parallax/dialect`): the dialect owns the `?`→`$n` translation and every
 * parse rule; the adapter owns only driver setup + OID registration. It has **no**
 * `@parallax/typescript` dependency, **no** Testcontainers dependency, and **no**
 * wire / grading logic — a future `@parallax/db-mysql` slots in beside it
 * identically.
 */
import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";
import { ParallaxTransientError } from "@parallax/db";
import { postgresDialect } from "@parallax/dialect";
import postgres, { type Options, type Sql } from "postgres";
import { managedTypes } from "./oids.js";

/**
 * Classify a porsager driver error to the portable retriable surface. A driver
 * error carrying a Postgres SQLSTATE `.code` that classifies to a transient
 * category (`deadlock` — a true deadlock or serialization failure, retriable; or
 * `lockWaitTimeout` — not retriable) is re-surfaced as a {@link ParallaxTransientError}
 * so the unit-of-work retry loop above the port never inspects a driver `.code`.
 * Everything else — including an already-wrapped transient, a `uniqueViolation`, or
 * a non-database error thrown by the transaction body — passes through unchanged.
 */
function classifyDriverError(error: unknown): unknown {
  if (error instanceof ParallaxTransientError) {
    return error;
  }
  const code = (error as { code?: string | number } | null)?.code;
  const category = postgresDialect.classifyErrorCode(code);
  if (category === "deadlock" || category === "lockWaitTimeout") {
    return new ParallaxTransientError(category, postgresDialect.isRetriable(category), {
      cause: error,
    });
  }
  return error;
}

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
 * A manual-commit Postgres session on a **fresh, independent** non-autocommit
 * connection with a lowered lock-wait budget, for the two-connection lock-
 * contention proofs (`m-db-error-004`-`m-read-lock-007`, `m-read-lock-008`). The Postgres sibling of {@link MariaDbSession}
 * — Postgres has no auto-detected lock-wait deadline, so the session lowers BOTH
 * `lock_timeout` (bounding a plain wait) and `deadlock_timeout` (shortening the
 * cycle-detector delay), mirroring the Python reference provider. Each `execute`
 * runs inside the session's open transaction (no auto-commit) so locks are HELD
 * until {@link commit} / {@link rollback}; a blocked lock raises SQLSTATE `55P03`
 * within the budget, re-surfaced as a portable {@link ParallaxTransientError}
 * (`kind === "lockWaitTimeout"`) through the shared {@link classifyDriverError}.
 *
 * The session owns its OWN dedicated single-connection porsager pool (the shipped
 * adapter's pool is `max: 1`, so a second held connection needs its own), which
 * {@link close} ends.
 */
export class PostgresSession {
  constructor(private readonly sql: Sql) {}

  /** Run one statement inside the session's transaction (classifying transient errors). */
  async execute(sql: string, binds: readonly unknown[] = []): Promise<void> {
    const text = postgresDialect.toPositionalPlaceholders(sql);
    try {
      await this.sql.unsafe(text, asParams(binds));
    } catch (error) {
      throw classifyDriverError(error);
    }
  }

  /**
   * Fetch rows INSIDE the session's held transaction — the concurrency-success seam
   * (`m-read-lock-007` / `m-read-lock-008`): a `for share of t0` SELECT both takes its shared lock AND
   * returns its rows, and an unlocked projection reads under the open unit of work.
   * Returns **managed** scalars (§3.2.1), copied into plain objects, exactly like
   * {@link PostgresDatabase.execute}.
   */
  async query(sql: string, binds: readonly unknown[] = []): Promise<readonly ParallaxRow[]> {
    const text = postgresDialect.toPositionalPlaceholders(sql);
    try {
      const result = await this.sql.unsafe(text, asParams(binds));
      return [...result].map((row) => ({ ...(row as ParallaxRow) }));
    } catch (error) {
      throw classifyDriverError(error);
    }
  }

  /** Commit the session's transaction. */
  async commit(): Promise<void> {
    await this.sql.unsafe("commit");
  }

  /** Roll back the session's transaction (best-effort; the connection may be broken). */
  async rollback(): Promise<void> {
    try {
      await this.sql.unsafe("rollback");
    } catch {
      // The held connection may already be broken (a timed-out / aborted transaction);
      // the pool is ended in `close` regardless.
    }
  }

  /** End the session's dedicated pool, returning its held connection to the server. */
  async close(): Promise<void> {
    await this.sql.end({ timeout: 5 });
  }
}

/**
 * A concrete `ParallaxDatabase` over Postgres. Construct it from a connection
 * string with {@link PostgresDatabase.fromConnectionString} (the common path for
 * an application) or wrap an existing porsager pool with
 * {@link PostgresDatabase.fromPool} (e.g. a shared app pool, or a
 * container-bound one).
 */
export class PostgresDatabase implements ParallaxDatabase {
  private constructor(
    private readonly sql: Sql,
    /**
     * The connection string, retained ONLY when the adapter was built from one
     * ({@link fromConnectionString}) — {@link openSession} uses it to open a
     * fresh, independent session connection beside the adapter's `max: 1` pool.
     * `undefined` for a wrapped external pool ({@link fromPool}), where
     * `openSession` cannot manufacture a peer connection.
     */
    private readonly connectionString?: string,
  ) {}

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
    return new PostgresDatabase(sql, connectionString);
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
   * (§3.2.1). Rows are copied into plain objects so callers never hold a driver
   * row proxy.
   */
  async execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    const text = postgresDialect.toPositionalPlaceholders(sql);
    try {
      const result = await this.sql.unsafe(text, asParams(binds));
      return [...result].map((row) => ({ ...(row as ParallaxRow) }));
    } catch (error) {
      // Surface a transient DB failure (deadlock / serialization / lock-wait
      // timeout) as the portable `ParallaxTransientError` so the retry loop above
      // the port classifies without touching a driver `.code`.
      throw classifyDriverError(error);
    }
  }

  /**
   * Execute a DML statement and return Postgres's native affected-row count
   * (porsager `Result.count`). The runtime write path deliberately does not append
   * a Postgres-only `returning` clause.
   */
  async executeWrite(sql: string, binds: readonly unknown[]): Promise<number> {
    const text = postgresDialect.toPositionalPlaceholders(sql);
    try {
      const result = await this.sql.unsafe(text, asParams(binds));
      // Guard a non-numeric `count` (mirrors the MariaDB sibling's `?? 0`): the
      // optimistic gate's `classifyOutcome` must see a real affected-row number, not
      // `undefined`, so a versioned update never misclassifies its conflict outcome.
      return result.count ?? 0;
    } catch (error) {
      throw classifyDriverError(error);
    }
  }

  /**
   * Run `body` inside a Postgres transaction (porsager `sql.begin`), committing on
   * resolve and rolling back on throw. A connection-bound `PostgresDatabase` (over
   * the reserved connection) is passed to `body`, so its reads/writes run inside
   * the transaction.
   */
  transaction<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T> {
    return (
      this.sql.begin((reserved) =>
        body(new PostgresDatabase(reserved as unknown as Sql)),
      ) as Promise<T>
    ).catch((error: unknown) => {
      // A transient failure can surface at COMMIT (e.g. a SERIALIZABLE
      // serialization failure), not only mid-statement — classify it here too so
      // the retry loop sees the portable transient regardless of where it arose.
      throw classifyDriverError(error);
    });
  }

  /**
   * Open a manual-commit {@link PostgresSession} on a FRESH, independent
   * single-connection pool over this adapter's connection string, with the
   * lock-wait budget lowered (`lock_timeout = '250ms'`, `deadlock_timeout =
   * '100ms'`) and a transaction opened, so the session holds any lock it takes
   * across a barrier while a peer session contends. The Postgres sibling of
   * {@link MariaDbSession} via `MariaDbDatabase.openSession`.
   *
   * The adapter's own pool is `max: 1`, so a second held connection cannot come
   * from it — the session gets its own dedicated pool (mirroring the composition-
   * root `peer`), which the returned session's {@link PostgresSession.close} ends.
   * The lowered budget + `begin` setup is guarded: if any step throws, the fresh
   * pool is ended before the (classified) error propagates, so a failed open never
   * leaks a connection.
   */
  async openSession(): Promise<PostgresSession> {
    if (this.connectionString === undefined) {
      throw new Error(
        "openSession requires a connection string; build the adapter with fromConnectionString",
      );
    }
    const sessionSql = postgres(this.connectionString, {
      // biome-ignore lint/suspicious/noExplicitAny: porsager's custom-type map is loosely typed.
      types: managedTypes() as any,
      max: 1,
      onnotice: () => {},
    });
    try {
      // Session-level SETs (auto-committed on the single connection, so they persist)
      // then BEGIN the holding transaction; every later `execute` runs inside it.
      await sessionSql.unsafe("set lock_timeout = '250ms'");
      await sessionSql.unsafe("set deadlock_timeout = '100ms'");
      await sessionSql.unsafe("begin");
    } catch (error) {
      await sessionSql.end({ timeout: 5 });
      throw classifyDriverError(error);
    }
    return new PostgresSession(sessionSql);
  }

  /** Close the underlying pool (no-op for a wrapped, externally-owned pool caller). */
  async close(): Promise<void> {
    await this.sql.end({ timeout: 5 });
  }
}
