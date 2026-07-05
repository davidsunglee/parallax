/**
 * `@parallax/db-mariadb` — the shippable MariaDB **adapter** (M11 decomposition,
 * layer 3): a concrete `ParallaxDatabase` over the `mysql2` driver, the MariaDB
 * sibling of `@parallax/db-postgres`.
 *
 * It implements the abstract `@parallax/db` port: `execute` runs a compiled
 * `?`-placeholder statement (MariaDB takes native `?`, so the dialect's
 * `toPositionalPlaceholders` is the identity), and every returned scalar is a
 * **managed** value (`bigint` / `ParallaxDecimal` / `Temporal.*` / `Uint8Array` /
 * string) normalized at the boundary (§3.2.1). It depends only on the **port**
 * (`@parallax/db`), the **pure dialect layer** (`@parallax/dialect`, its matching
 * strategy `mariadbDialect`), and `@parallax/core` (the neutral scalar helpers) —
 * no `@parallax/typescript`, no Testcontainers, no wire / grading logic.
 *
 * Two MariaDB-specific boundary concerns the adapter owns (both localized to the
 * seam, mirroring the Python reference provider):
 *
 *  - **reads** — `mysql2` field-type codes are mapped (`field-codes.ts`) to the
 *    neutral parser key and materialized by `mariadbDialect.parsers[key]`. The
 *    open temporal upper bound (`9999-12-31 23:59:59.999999`) is detected inside
 *    the `timestamp` parser and mapped back to the `infinity` sentinel.
 *  - **binds** — the `infinity` sentinel maps to MariaDB's max-sentinel
 *    `DATETIME` (`mariadbDialect.infinityBind()`), and an ISO-8601 instant (or a
 *    `Temporal.Instant`) is normalized to a naive UTC `DATETIME(6)` string
 *    (MariaDB `DATETIME` is timezone-naive; every instant in the suite is UTC).
 *
 * Driver errors are classified through `mariadbDialect.classifyErrorCode` +
 * `isRetriable`: a transient failure (deadlock / lock-wait timeout) surfaces as a
 * portable {@link ParallaxTransientError} so the retry loop above the port never
 * inspects a driver `.errno`.
 */
import { isInfinity, ParallaxDecimal, parseTimestamp, Temporal } from "@parallax/core";
import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";
import { ParallaxTransientError } from "@parallax/db";
import { type ErrorCategory, mariadbDialect } from "@parallax/dialect";
import {
  createPool,
  type Pool,
  type PoolConnection,
  type PoolOptions,
  type ResultSetHeader,
  type RowDataPacket,
} from "mysql2/promise";
import { MARIADB_FIELD_TYPES } from "./field-codes.js";

/**
 * The minimal `mysql2` type-cast field view: the field-type NAME plus the raw-text
 * accessor. A structural supertype of `mysql2`'s `Field` (which carries more props),
 * so this callback is assignable to `mysql2`'s `TypeCast`.
 */
interface TypeCastField {
  readonly type: string;
  string(): string | null;
}

/**
 * Read one column from the driver via the field-type map: a mapped type is read as
 * raw text and materialized by `mariadbDialect.parsers[key]` into its managed
 * carrier; an unmapped type (an `int32` / `float` `number`, a `varchar` / uuid
 * `char(36)` string) falls through to `mysql2`'s default cast (already the managed
 * / wire form). A NULL column is returned as `null` (never parsed).
 */
function typeCast(field: TypeCastField, next: () => unknown): unknown {
  const key = MARIADB_FIELD_TYPES[field.type];
  if (key === undefined) {
    return next();
  }
  const raw = field.string();
  if (raw === null) {
    return null;
  }
  const parse = mariadbDialect.parsers[key] as (raw: string) => unknown;
  return parse(raw);
}

/**
 * Render a `Temporal.Instant` as MariaDB's naive UTC `DATETIME(6)` literal —
 * `2024-03-01T12:00:00.123456Z` → `2024-03-01 12:00:00.123456`. MariaDB `DATETIME`
 * is timezone-naive; every instant the suite binds is UTC, so the offset is dropped
 * after normalizing (µs precision preserved).
 */
function instantToMariaDatetime(instant: Temporal.Instant): string {
  return instant.toString({ smallestUnit: "microsecond" }).replace("T", " ").replace(/Z$/, "");
}

/**
 * Parse an ISO-8601 instant string (carrying a `T` separator) to a
 * `Temporal.Instant`, else `undefined` — so a plain `date` / `time` / uuid /
 * business string is left alone (mirrors the Python provider's `_parse_iso_instant`).
 */
function tryParseInstant(text: string): Temporal.Instant | undefined {
  if (!text.includes("T")) {
    return undefined;
  }
  try {
    return parseTimestamp(text);
  } catch {
    return undefined;
  }
}

/**
 * Adapt one bind value for MariaDB binding (the seam's inbound half): the
 * `infinity` sentinel → the max-sentinel `DATETIME`; an ISO-8601 instant (string
 * or `Temporal.Instant`) → a naive UTC `DATETIME(6)` string; the managed scalars
 * (`ParallaxDecimal` / `bigint` / `Temporal.PlainDate` / `Temporal.PlainTime`) →
 * their canonical strings; a `Uint8Array` → a `Buffer` (the `mysql2` blob bind);
 * every other scalar passes through unchanged.
 */
export function toMariaBind(value: unknown): unknown {
  if (isInfinity(value)) {
    return mariadbDialect.infinityBind();
  }
  if (value instanceof Temporal.Instant) {
    return instantToMariaDatetime(value);
  }
  if (typeof value === "string") {
    const instant = tryParseInstant(value);
    return instant === undefined ? value : instantToMariaDatetime(instant);
  }
  if (value instanceof ParallaxDecimal) {
    return value.toString();
  }
  if (typeof value === "bigint") {
    return value.toString();
  }
  if (value instanceof Temporal.PlainDate || value instanceof Temporal.PlainTime) {
    return value.toString();
  }
  if (value instanceof Uint8Array) {
    return Buffer.from(value);
  }
  return value;
}

/** Adapt an ordered bind list for MariaDB binding (per-value {@link toMariaBind}). */
export function toMariaBinds(binds: readonly unknown[]): unknown[] {
  return binds.map(toMariaBind);
}

/** The native MariaDB errno a `mysql2` error carries (else `undefined`). */
function nativeErrno(error: unknown): number | undefined {
  return (error as { errno?: number } | null)?.errno;
}

/**
 * Classify a `mysql2` driver error to a neutral M11 {@link ErrorCategory} via the
 * dialect's errno map. Exposed so the composition root's error-round-trip proofs
 * (`0720`-`0727`) can assert a raised error's category without inspecting a driver
 * `.errno` themselves.
 */
export function classifyMariaError(error: unknown): ErrorCategory {
  return mariadbDialect.classifyErrorCode(nativeErrno(error));
}

/**
 * Re-surface a transient `mysql2` error (deadlock / lock-wait timeout) as the
 * portable {@link ParallaxTransientError} so the retry loop above the port never
 * inspects a driver `.errno`. Everything else — an already-wrapped transient, a
 * `uniqueViolation` (permanent), or a non-database error — passes through unchanged.
 */
function classifyDriverError(error: unknown): unknown {
  if (error instanceof ParallaxTransientError) {
    return error;
  }
  const category = classifyMariaError(error);
  if (category === "deadlock" || category === "lockWaitTimeout") {
    return new ParallaxTransientError(category, mariadbDialect.isRetriable(category), {
      cause: error,
    });
  }
  return error;
}

/** Copy a `mysql2` result row into a plain managed object (never a driver proxy). */
function toRows(rows: unknown): readonly ParallaxRow[] {
  if (!Array.isArray(rows)) {
    return [];
  }
  return (rows as RowDataPacket[]).map((row) => ({ ...(row as object) }) as ParallaxRow);
}

/** Parse a `mysql://user:pass@host:port/db` connection URI into `mysql2` options. */
function parseConnectionString(uri: string): PoolOptions {
  const url = new URL(uri);
  const database = url.pathname.replace(/^\//, "");
  return {
    host: url.hostname,
    port: url.port ? Number(url.port) : 3306,
    user: decodeURIComponent(url.username),
    password: decodeURIComponent(url.password),
    ...(database ? { database } : {}),
  };
}

/** Options for constructing a `MariaDbDatabase` (beyond the adapter defaults). */
export type MariaDbDatabaseOptions = Partial<PoolOptions>;

/**
 * A manual-commit MariaDB connection with a lowered lock-wait budget, for the
 * two-connection lock-contention proofs (`0723`-`0726`). Each `execute` runs
 * inside the session's open transaction (no auto-commit) so locks are held until
 * {@link commit} / {@link rollback}; a blocked lock raises errno `1205` within the
 * 1-second budget, and InnoDB victimizes a deadlock immediately (errno `1213`).
 * Errors are classified through the shared {@link classifyDriverError}.
 */
export class MariaDbSession {
  constructor(private readonly connection: PoolConnection) {}

  /** Run one statement inside the session's transaction (classifying transient errors). */
  async execute(sql: string, binds: readonly unknown[] = []): Promise<void> {
    try {
      await this.connection.query(sql, toMariaBinds(binds));
    } catch (error) {
      throw classifyDriverError(error);
    }
  }

  /** Commit the session's transaction. */
  async commit(): Promise<void> {
    await this.connection.commit();
  }

  /** Roll back the session's transaction. */
  async rollback(): Promise<void> {
    await this.connection.rollback();
  }

  /** Reset the lowered lock budget and return the connection to the pool. */
  async close(): Promise<void> {
    try {
      await this.connection.query("set innodb_lock_wait_timeout = default");
    } catch {
      // The connection may already be broken (a deadlock victim); release anyway.
    }
    this.connection.release();
  }
}

/**
 * A concrete `ParallaxDatabase` over MariaDB (`mysql2`). Construct it from a
 * connection string with {@link MariaDbDatabase.fromConnectionString} (the common
 * path for an application / the Testcontainers provider).
 */
export class MariaDbDatabase implements ParallaxDatabase {
  private constructor(private readonly db: Pool) {}

  /**
   * Build an adapter over a fresh `mysql2` pool for `connectionString`, with the
   * managed-type `typeCast` registered. `options` merges over the adapter defaults.
   */
  static fromConnectionString(
    connectionString: string,
    options: MariaDbDatabaseOptions = {},
  ): MariaDbDatabase {
    const pool = createPool({
      ...parseConnectionString(connectionString),
      connectionLimit: 4,
      ...options,
      typeCast,
    });
    return new MariaDbDatabase(pool);
  }

  /** The underlying `mysql2` pool (for provisioning at the composition root). */
  get pool(): Pool {
    return this.db;
  }

  /**
   * Execute a compiled statement (`?`-placeholder SQL + ordered binds). MariaDB
   * takes native `?`, so no placeholder rewrite is needed; every returned scalar is
   * a managed value (§3.2.1) via the registered `typeCast`.
   */
  async execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    try {
      const [rows] = await this.db.query(sql, toMariaBinds(binds));
      return toRows(rows);
    } catch (error) {
      throw classifyDriverError(error);
    }
  }

  /**
   * Execute a DML statement and return the affected-row count (the write path the
   * conformance provider grades write sequences with).
   */
  async executeWrite(sql: string, binds: readonly unknown[]): Promise<number> {
    try {
      const [result] = await this.db.query(sql, toMariaBinds(binds));
      return (result as ResultSetHeader).affectedRows ?? 0;
    } catch (error) {
      throw classifyDriverError(error);
    }
  }

  /**
   * Apply a DML statement inside a transaction, then ROLL IT BACK, returning the
   * affected-row count it reported before the rollback (the M8 abort seam).
   */
  async executeRolledBack(sql: string, binds: readonly unknown[]): Promise<number> {
    const connection = await this.db.getConnection();
    try {
      await connection.beginTransaction();
      const [result] = await connection.query(sql, toMariaBinds(binds));
      const affected = (result as ResultSetHeader).affectedRows ?? 0;
      await connection.rollback();
      return affected;
    } catch (error) {
      await connection.rollback();
      throw classifyDriverError(error);
    } finally {
      connection.release();
    }
  }

  /** Run `body` inside a MariaDB transaction, committing on resolve, rolling back on throw. */
  async transaction<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T> {
    const connection = await this.db.getConnection();
    const tx: ParallaxDatabase = {
      execute: async (sql, binds) => {
        try {
          const [rows] = await connection.query(sql, toMariaBinds(binds));
          return toRows(rows);
        } catch (error) {
          throw classifyDriverError(error);
        }
      },
    };
    try {
      await connection.beginTransaction();
      const result = await body(tx);
      await connection.commit();
      return result;
    } catch (error) {
      await connection.rollback();
      throw classifyDriverError(error);
    } finally {
      connection.release();
    }
  }

  /**
   * Open a manual-commit {@link MariaDbSession} over a dedicated pool connection
   * with the lock-wait budget lowered to 1 second (so a blocked lock raises errno
   * `1205` quickly), for the two-connection lock-contention proofs.
   */
  async openSession(): Promise<MariaDbSession> {
    const connection = await this.db.getConnection();
    await connection.query("set innodb_lock_wait_timeout = 1");
    await connection.beginTransaction();
    return new MariaDbSession(connection);
  }

  /** Close the underlying pool. */
  async close(): Promise<void> {
    await this.db.end();
  }
}
