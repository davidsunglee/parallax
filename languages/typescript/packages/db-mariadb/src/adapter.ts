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
 *    the `timestamp` parser and mapped back to the `infinity` sentinel. A raw
 *    (un-wrapped) `bytes` column is the one exception: it is read as the driver's
 *    raw `Buffer` (`field.buffer()`) and copied into a `Uint8Array` directly, NOT
 *    through `mariadbDialect.parsers.bytes` — see `typeCast`'s doc for how a raw
 *    blob is told apart from the dialect's `hex(col)` projection (`1005`) by the
 *    codebase-owned `_hex` output-alias convention.
 *  - **binds** — the `infinity` sentinel maps to MariaDB's max-sentinel
 *    `DATETIME` (`mariadbDialect.infinityBind()`), and a TYPED `Temporal.Instant`
 *    is normalized to a naive UTC `DATETIME(6)` string (MariaDB `DATETIME` is
 *    timezone-naive; every instant in the suite is UTC). A plain `string` bind is
 *    passed **verbatim** — the adapter does NOT heuristically rewrite a
 *    timestamp-looking string into a `DATETIME` (genuine text survives). A timestamp
 *    value reaches this adapter as a string on exactly two paths, and NEITHER needs
 *    the adapter to coerce it:
 *      1. the untyped conformance corpus (ISO-instant strings + the `"infinity"`
 *         string) — now materialized to a managed `Temporal.Instant` / left as the
 *         `"infinity"` sentinel ONE LAYER UP, in the grader-side seam that owns it
 *         (`@parallax/typescript` `mariadb-provider.ts` `toManagedBind`);
 *      2. a developer temporal AS-OF pin, whose `Temporal.Instant` the operation
 *         model serializes to the neutral wire string before it is bound (a
 *         `find(..., { asOf })` read reaches the port with an ISO string, not a
 *         `Temporal.Instant`).
 *    A path-2 ISO string is left verbatim and coerced by MariaDB's own implicit
 *    string→`DATETIME` conversion (offset-normalized to the same naive value
 *    regardless of session `time_zone`), exactly as the identical ISO string bound
 *    through the `@parallax/db-postgres` adapter is coerced by Postgres. Only the
 *    non-coercible `"infinity"` sentinel is special-cased above.)
 *
 * Driver errors are classified through `mariadbDialect.classifyErrorCode` +
 * `isRetriable`: a transient failure (deadlock / lock-wait timeout) surfaces as a
 * portable {@link ParallaxTransientError} so the retry loop above the port never
 * inspects a driver `.errno`.
 */
import { isInfinity, ParallaxDecimal, Temporal } from "@parallax/core";
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
 * The minimal `mysql2` type-cast field view: the field-type NAME, the output
 * column NAME/alias, and the raw-text and raw-buffer accessors. A structural
 * supertype of `mysql2`'s `Field` (which carries more props), so this callback is
 * assignable to `mysql2`'s `TypeCast`.
 */
interface TypeCastField {
  readonly type: string;
  /**
   * The output column's NAME (the projected alias, e.g. `payload_hex` for
   * `hex(t0.payload) payload_hex`, or the bare column name `payload` for a raw
   * `t0.payload`). `mysql2` surfaces the MySQL/MariaDB column-definition label —
   * the alias, not the origin column — so this is the `<col>_hex` seam `typeCast`
   * keys the raw-vs-hex `bytes` split on (see its doc).
   */
  readonly name: string;
  string(): string | null;
  /** The column's raw bytes (blob columns only); `null` for a SQL NULL. */
  buffer(): Buffer | null;
}

/**
 * Read one column from the driver via the field-type map: an unmapped type (an
 * `int32` / `float` `number`, a `varchar` / uuid `char(36)` string) falls through
 * to `mysql2`'s default cast (already the managed / wire form); every OTHER
 * mapped type is read as raw text and materialized by `mariadbDialect.parsers[key]`.
 * A NULL column is returned as `null` (never parsed).
 *
 * The `bytes` key needs one more distinction `mysql2`'s bare field-type NAME
 * doesn't carry on its own: a `bytes` (MariaDB `longblob`) column can reach this
 * function via TWO different SQL shapes —
 *
 *  1. a RAW (un-wrapped) select `t0.<col>` — the runtime `find`'s VERBATIM `bytes`
 *     projection (`RuntimeSchema.rootProjection`, case `0003`) — whose wire bytes
 *     ARE the actual byte payload, so it must be read via `field.buffer()`;
 *  2. the dialect's `hex(t0.<col>) <col>_hex` projection (`mariadbDialect.
 *     bytesProjection`, cases like `1005`) — whose wire bytes are HEX TEXT, so it
 *     must be read via `field.string()` and hex-decoded by `mariadbDialect.
 *     parsers.bytes` (`bytesFromHex`); reading the raw buffer here would yield the
 *     hex text's OWN byte encoding, not the decoded payload.
 *
 * `mysql2` cannot tell these apart by SQL shape, so the split keys on a signal the
 * CODEBASE OWNS rather than driver internals: the M3 compiler ALWAYS aliases a
 * `bytes` hex projection to `<col>_hex` (`compile.ts` `renderProjectionColumn`,
 * `column.outputName ?? '<col>_hex'`; the conformance `schema-resolver` only ever
 * routes a `bytes` output through that lowering under a `_hex`-suffixed alias),
 * whereas a RAW `bytes` projection is a BARE column (`RuntimeSchema.rootProjection`
 * emits `t0.<col>` with no alias). `mysql2`'s `Field.name` carries that output
 * alias, so a hex result reports a `<col>_hex` name and a raw result reports the
 * bare column name. The raw-buffer path is therefore gated on the field NAME NOT
 * ending in `_hex`; every `_hex`-aliased blob (case `1005`, and the DDL/table-state
 * reads `readTableState` / `reset`) stays on the hex-decode path. This is strictly
 * more robust than keying on `mysql2`'s empirical field-type NAME (a raw `longblob`
 * reporting bare `'BLOB'` vs `HEX(...)` widening to `'TINY_BLOB'`/`'MEDIUM_BLOB'`/
 * `'LONG_BLOB'`): the `_hex` alias is the compiler's invariant, not an undocumented
 * driver behavior that a `mysql2`/MariaDB upgrade could shift. (The convention
 * assumes no RAW `bytes` column is itself named `*_hex`; the M0 `bytes` column is
 * `payload`, and any `_hex`-named model column would be a self-inflicted collision.)
 */
function typeCast(field: TypeCastField, next: () => unknown): unknown {
  const key = MARIADB_FIELD_TYPES[field.type];
  if (key === undefined) {
    return next();
  }
  if (key === "bytes" && !field.name.endsWith("_hex")) {
    const buf = field.buffer();
    return buf === null ? null : new Uint8Array(buf);
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
 * Adapt one bind value for MariaDB binding (the seam's inbound half): the
 * `infinity` sentinel → the max-sentinel `DATETIME`; a TYPED `Temporal.Instant` →
 * a naive UTC `DATETIME(6)` string; the managed scalars (`ParallaxDecimal` /
 * `bigint` / `Temporal.PlainDate` / `Temporal.PlainTime`) → their canonical
 * strings; a `Uint8Array` → a `Buffer` (the `mysql2` blob bind); every other
 * scalar — INCLUDING a plain `string` — passes through **unchanged**.
 *
 * A `string` is NOT heuristically rewritten into a `DATETIME` here: a shipping
 * adapter cannot know a bind's logical column type, so coercing any
 * timestamp-looking text would corrupt a genuine text value. The developer surface
 * binds a timestamp as a `Temporal.Instant` (handled above); the untyped
 * conformance corpus's ISO-instant strings are materialized to `Temporal.Instant`
 * one layer up, in the grader-side provider (`mariadb-provider.ts` `toManagedBind`),
 * mirroring the Python reference where `_to_db_bind` runs in the PROVIDER, not the
 * driver (mariadb.py:53-72). Any ISO string that still arrives as text is left as
 * text and coerced by MariaDB's own implicit `string`→`DATETIME` conversion (the
 * same delegation `@parallax/db-postgres` makes to Postgres); only the
 * non-coercible `"infinity"` sentinel is special-cased above.
 */
export function toMariaBind(value: unknown): unknown {
  if (isInfinity(value)) {
    return mariadbDialect.infinityBind();
  }
  if (value instanceof Temporal.Instant) {
    return instantToMariaDatetime(value);
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
   *
   * The post-`getConnection()` setup (`set innodb_lock_wait_timeout` +
   * `beginTransaction`) is guarded: if either step throws, the pooled connection is
   * cleaned up on THREE fronts before the error propagates, so a failed open never
   * leaks a connection AND never returns a poisoned one to the pool:
   *
   *  1. **Reset then release.** The lock-wait budget is reset to `default` on a
   *     best-effort basis — swallowing any error, since the connection may already
   *     be broken — BEFORE releasing, mirroring {@link MariaDbSession.close}. This
   *     matters for the split case where lowering the budget SUCCEEDED but
   *     `beginTransaction` then failed: without the reset the connection would be
   *     handed back to the pool still carrying the 1-second budget and silently
   *     starve a later borrower. When the SET itself failed the reset is a harmless
   *     swallowed no-op.
   *  2. **Classify.** The propagated error is run through the shared
   *     {@link classifyDriverError} (as every other adapter method does — `execute`,
   *     `transaction`, `executeRolledBack`), so a transient setup failure surfaces
   *     as a portable {@link ParallaxTransientError} rather than a raw driver error.
   *
   * (Mirrors the Python reference's `except BaseException: conn.close(); raise`,
   * mariadb.py:226-228 — where the reference `close()`s a freshly-opened dedicated
   * connection while this pooled adapter resets-then-`release()`s it.) The
   * successful path is unchanged: ownership of the connection passes to the returned
   * session, which resets-then-releases it in {@link MariaDbSession.close}.
   */
  async openSession(): Promise<MariaDbSession> {
    const connection = await this.db.getConnection();
    try {
      await connection.query("set innodb_lock_wait_timeout = 1");
      await connection.beginTransaction();
    } catch (error) {
      try {
        await connection.query("set innodb_lock_wait_timeout = default");
      } catch {
        // The connection may already be broken; reset is best-effort, release anyway.
      }
      connection.release();
      throw classifyDriverError(error);
    }
    return new MariaDbSession(connection);
  }

  /** Close the underlying pool. */
  async close(): Promise<void> {
    await this.db.end();
  }
}
