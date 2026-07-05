/**
 * The M11 MariaDB dialect — the **second** conforming {@link Dialect}.
 *
 * MariaDB exercises exactly the seam points Postgres does not, proving the
 * abstraction earns its keep at the SQL/value-rule level (the corpus divergences
 * `0006`, `0323`, `1001`, `1002`, `1005`, `0720`–`0727`):
 *
 *  - **identifier quoting** — a backtick, not a double-quote (`` `order` ``), with
 *    embedded backticks doubled and its own reserved-word set;
 *  - **NULL ordering** — MariaDB has no `NULLS LAST` syntax, so an ascending
 *    nullable key forces NULLs last with a leading `is null,` term (`m11:153-167`);
 *  - **read-lock** — MariaDB has no `for share` (MDEV-17514); its shared row lock
 *    is the unaliased ` lock in share mode`;
 *  - **neutral→column type** — `tinyint(1)` / `datetime(6)` / `double` / `longblob`
 *    / `char(36)` … (the M0 table, its MariaDB column);
 *  - **infinity** — MariaDB's `DATETIME` has no native `'infinity'`, so the open
 *    temporal upper bound binds a documented MAX-SENTINEL datetime (`m11:189-202`);
 *  - **error classification** — MariaDB keys on the vendor errno (`1062`/`1213`/
 *    `1205`), not a SQLSTATE string;
 *  - **placeholders** — the MariaDB driver takes native `?`, so the adapter's
 *    `?`→positional rewrite is the identity.
 *
 * Like `postgresDialect`, this module imports no driver: it exposes the *rules* a
 * driver-bound adapter (`@parallax/db-mariadb`, a later phase) applies. Value
 * parsers reuse the neutral `@parallax/core` scalar helpers; only `timestamp`
 * (max-sentinel ↔ infinity) diverges from the Postgres wire form.
 */
import {
  bytesFromHex,
  INFINITY,
  type Infinity as InfinitySentinel,
  ParallaxDecimal,
  Temporal,
  timestampFromRaw,
} from "@parallax/core";
import type { Dialect } from "./dialect.js";
import type { ErrorCategory } from "./errors.js";

/** The dialect identifier this seam answers for (keys `goldenSql`/`expectedNativeCode`). */
export const MARIADB_DIALECT = "mariadb" as const;

/**
 * The MariaDB max-sentinel for the open temporal upper bound: the largest
 * representable `DATETIME(6)`. MariaDB's `DATETIME` has no native `'infinity'`, so
 * the seam substitutes this documented sentinel for the neutral `infinity` on the
 * way in (binds) and detects it on the way out (parsers), so a fixture authored
 * once against native-infinity Postgres compares identically here (`m11:189-202`).
 */
export const MARIADB_INFINITY_SENTINEL = "9999-12-31 23:59:59.999999" as const;

/**
 * MariaDB takes native `?` positional placeholders, so the canonical M3 `?` SQL
 * needs no rewrite at the driver boundary — this is the identity (contrast the
 * Postgres `?`→`$n` translation).
 */
function toPositionalPlaceholders(sql: string): string {
  return sql;
}

/**
 * **Apply** MariaDB's in-transaction shared read lock (M8 automatic read-lock
 * correctness, owned by the M11 seam). MariaDB has no `for share` (MDEV-17514); its
 * shared row lock is the unaliased ` lock in share mode`, appended after every
 * other clause. Mirrors the Postgres decision structure exactly — a projection /
 * aggregation read (`projection: true`) and any non-`locking` read are returned
 * unchanged (no base row to lock) — only the suffix text diverges.
 */
function applyReadLock(
  sql: string,
  options: { readonly locking: boolean; readonly projection: boolean },
): string {
  // MariaDB's shared lock is UNALIASED (unlike Postgres's `for share of t0`).
  if (!options.locking || options.projection) {
    return sql;
  }
  return `${sql} lock in share mode`;
}

/**
 * One ORDER BY term with MariaDB's NULL placement (the M4/M11 catalog table,
 * `m11:153-167`). MariaDB has no `NULLS LAST` syntax and sorts NULLs FIRST for
 * `asc` / LAST for `desc` by default, so:
 *
 *  - `asc` forces NULLs last with a leading `<col> is null,` term (`is null` is `0`
 *    for present values and `1` for NULLs, so ascending on it trails the NULLs)
 *    followed by the plain ascending sort — the leading term becomes part of the
 *    ORDER BY list the compiler joins with `, `;
 *  - `desc` is emitted **bare** (its native default already sorts NULLs last, so no
 *    extra term is needed to match the neutral "NULLs sort last" rule).
 *
 * Postgres expresses the same intent with a bare `asc` / an explicit `desc nulls
 * last` (its `postgresDialect` sibling).
 */
function orderByTerm(qualifiedColumn: string, direction: "asc" | "desc"): string {
  if (direction === "desc") {
    // Bare `desc` — MariaDB sorts NULLs LAST for descending by default, matching the
    // M4 canonical rule. Do NOT add `nulls last` (MariaDB has no such syntax).
    return `${qualifiedColumn} desc`;
  }
  // A leading `is null,` term forces NULLs LAST for ascending (MariaDB's default is
  // NULLs FIRST). This is spec-mandated (`m11:153-167`); do NOT drop it.
  return `${qualifiedColumn} is null, ${qualifiedColumn} asc`;
}

/**
 * Apply the MariaDB row-limit clause — append ` limit ?` (the bind carries the
 * count). Byte-identical to Postgres today; modeled as a *wrappable* hook so a
 * future dialect that rewrites the query shape can override rather than append.
 */
function rowLimit(sql: string): string {
  return `${sql} limit ?`;
}

/**
 * Lower a `bytes` column to MariaDB's hex-text projection — the argument-less
 * `hex(<col>) <out>` — carrying NO bind (contrast Postgres's `encode(<col>, ?)`
 * with a `'hex'` format bind). MariaDB's `hex(...)` takes no format argument, so
 * the projection is bind-free (`1005`).
 */
function bytesProjection(
  qualifiedColumn: string,
  outputName: string,
): { readonly sql: string; readonly binds: readonly unknown[] } {
  return { sql: `hex(${qualifiedColumn}) ${outputName}`, binds: [] };
}

// --- neutral-type → MariaDB column type (the M0 table) ----------------------

/**
 * M0 neutral base type → MariaDB column type (non-parametric types). The
 * divergences from Postgres that matter: `boolean`→`tinyint(1)` (no native
 * boolean), `timestamp`→`datetime(6)` (MariaDB `TIMESTAMP` is 2038-limited +
 * auto-updates, so milestones use `DATETIME` with µs precision — and it has no
 * native infinity), `float64`→`double`, `bytes`→`longblob`, `uuid`→`char(36)`.
 */
const MARIADB_BASE_TYPES: Readonly<Record<string, string>> = {
  boolean: "tinyint(1)",
  int32: "int",
  int64: "bigint",
  float32: "float",
  float64: "double",
  bytes: "longblob",
  date: "date",
  time: "time",
  timestamp: "datetime(6)",
  uuid: "char(36)",
  json: "json",
};

/** Matches a `decimal(p,s)` neutral type token and captures precision/scale. */
const DECIMAL_TYPE = /^decimal\((\d+),(\d+)\)$/;

/**
 * Map an M0 neutral type to its MariaDB column type. `decimal(p,s)` stays
 * `decimal(p,s)` (MariaDB spells it `decimal`, not `numeric`), a bounded `string`
 * → `varchar(n)`, an unbounded `string` → `text`; everything else comes from the
 * base table.
 */
function mariadbColumnType(neutralType: string, maxLength?: number): string {
  const decimal = DECIMAL_TYPE.exec(neutralType);
  if (decimal) {
    return `decimal(${decimal[1]},${decimal[2]})`;
  }
  if (neutralType === "string") {
    return maxLength ? `varchar(${maxLength})` : "text";
  }
  const base = MARIADB_BASE_TYPES[neutralType];
  if (base === undefined) {
    throw new Error(`no MariaDB mapping for neutral type '${neutralType}'`);
  }
  return base;
}

// --- identifier quoting ------------------------------------------------------

/** A lexically-simple identifier needs no quoting unless it is reserved. */
const SIMPLE_IDENTIFIER = /^[a-z_][a-z0-9_]*$/;

/**
 * Reserved words that, although lexically simple, MUST be quoted as an identifier.
 * MariaDB carries its OWN reserved set (a database's keyword list differs from
 * Postgres's); the curated set below covers the identifiers the corpus models
 * emit (e.g. `order`) — enough to keep generated SQL byte-identical to the
 * hand-authored goldens. A non-simple name (uppercase / special) is caught by the
 * regex regardless.
 *
 * `position` is a MariaDB-only addition (`POSITION()` is a reserved SQL function
 * name here but not on Postgres, and the corpus's `Position` table would otherwise
 * emit unquoted on MariaDB — both in this DDL derivation and in the M3 compiler's
 * `from` clause, which now also routes through `quoteIdentifier`). Postgres's
 * reserved set intentionally omits it (`position t0` stays unquoted there,
 * byte-identical to the hand-authored golden).
 */
const RESERVED_WORDS: ReadonlySet<string> = new Set([
  "all",
  "and",
  "as",
  "asc",
  "between",
  "by",
  "case",
  "check",
  "column",
  "constraint",
  "create",
  "default",
  "delete",
  "desc",
  "distinct",
  "drop",
  "else",
  "end",
  "exists",
  "foreign",
  "from",
  "group",
  "having",
  "in",
  "index",
  "insert",
  "into",
  "is",
  "join",
  "key",
  "like",
  "limit",
  "not",
  "null",
  "on",
  "or",
  "order",
  "position",
  "primary",
  "references",
  "select",
  "set",
  "table",
  "then",
  "to",
  "union",
  "unique",
  "update",
  "user",
  "using",
  "values",
  "when",
  "where",
]);

/**
 * Quote a MariaDB identifier when it is reserved or otherwise non-simple. A simple
 * lowercase non-reserved identifier is returned unquoted (so generated SQL is
 * byte-identical to the hand-authored goldens); a reserved word (e.g. `order`) or
 * a name with uppercase / special characters is **backtick**-quoted, with any
 * embedded backtick doubled — the one genuine cross-dialect divergence in the
 * quote CHARACTER (Postgres double-quotes; MariaDB backticks).
 */
function quoteIdentifier(name: string): string {
  if (SIMPLE_IDENTIFIER.test(name) && !RESERVED_WORDS.has(name)) {
    return name;
  }
  return `\`${name.replace(/`/g, "``")}\``;
}

// --- raw-string type coercion at the adapter boundary -----------------------

/** Materialize a raw `int8` string into a native `bigint` (µ-precision-safe). */
function int8FromRaw(raw: string): bigint {
  return BigInt(raw.trim());
}

/** Materialize a raw `numeric` string into an exact {@link ParallaxDecimal}. */
function numericFromRaw(raw: string): ParallaxDecimal {
  return ParallaxDecimal.from(raw.trim());
}

/**
 * Materialize a raw MariaDB `datetime(6)` string into a `Temporal.Instant` at
 * microsecond precision. The MAX-SENTINEL (`9999-12-31 23:59:59.999999`) is mapped
 * back to the `infinity` sentinel — the open temporal upper bound has no instant —
 * so a current-row open bound compares to the fixture's native-infinity Postgres
 * value. A MariaDB `DATETIME` carries no offset; `timestampFromRaw` treats an
 * offset-less value as UTC (every instant in the suite is UTC).
 */
function timestampFromDb(raw: string): Temporal.Instant | InfinitySentinel {
  const text = raw.trim();
  if (text === MARIADB_INFINITY_SENTINEL) {
    return INFINITY;
  }
  return timestampFromRaw(text);
}

/**
 * Materialize a raw `longblob` hex rendering into a `Uint8Array`. MariaDB's
 * `hex(...)` yields plain hex text (no `\x` prefix); {@link bytesFromHex} accepts
 * both the prefixed and bare forms, so the same parser serves both dialects.
 */
function bytesFromDb(raw: string): Uint8Array {
  return bytesFromHex(raw.trim());
}

/** Materialize a raw `date` string (`2024-03-01`) into a `Temporal.PlainDate`. */
function dateFromDb(raw: string): Temporal.PlainDate {
  return Temporal.PlainDate.from(raw.trim());
}

/** Materialize a raw `time` string (`12:34:56`) into a `Temporal.PlainTime`. */
function timeFromDb(raw: string): Temporal.PlainTime {
  return Temporal.PlainTime.from(raw.trim());
}

/** Materialize a raw `char(36)` uuid into a canonical string. */
function uuidFromDb(raw: string): string {
  return raw.trim();
}

// --- error classification (MariaDB vendor errno) ----------------------------

/**
 * MariaDB keys error classification on the vendor **errno** (an int), not the
 * SQLSTATE string Postgres uses: `1062` (ER_DUP_ENTRY), `1213` (ER_LOCK_DEADLOCK),
 * `1205` (ER_LOCK_WAIT_TIMEOUT). This is exactly why the code *source* is a dialect
 * decision — SQLSTATE `40001` is a serialization failure on Postgres but the
 * deadlock state on MariaDB (`errors.py` records the same split).
 */
const MARIADB_ERROR_CODES: Readonly<Record<number, ErrorCategory>> = {
  1062: "uniqueViolation",
  1213: "deadlock",
  1205: "lockWaitTimeout",
};

/**
 * Classify a native MariaDB error code (the vendor errno the driver surfaces) to a
 * neutral M11 category. Coerces the code to an integer errno and looks it up;
 * returns `unknown` for an unrecognized / missing / non-numeric code so an
 * unclassified error is never silently treated as retriable.
 */
function classifyErrorCode(code: string | number | null | undefined): ErrorCategory {
  if (code === null || code === undefined) {
    return "unknown";
  }
  const errno = Number(code);
  if (!Number.isInteger(errno)) {
    return "unknown";
  }
  return MARIADB_ERROR_CODES[errno] ?? "unknown";
}

// --- the reified MariaDB dialect ---------------------------------------------

/**
 * The concrete MariaDB {@link Dialect} — the second conforming implementation of
 * the layer-1 contract. Every method is MariaDB's answer to the same catalog
 * question `postgresDialect` answers for Postgres; the two diverge only where the
 * corpus witnesses a genuine dialect difference. `infinityBind` returns the
 * max-sentinel datetime MariaDB binds for the open temporal upper bound.
 */
export const mariadbDialect: Dialect = {
  id: MARIADB_DIALECT,
  quoteIdentifier,
  orderByTerm,
  rowLimit,
  bytesProjection,
  applyReadLock,
  columnType: mariadbColumnType,
  toPositionalPlaceholders,
  parsers: {
    int8: int8FromRaw,
    numeric: numericFromRaw,
    timestamp: timestampFromDb,
    bytes: bytesFromDb,
    date: dateFromDb,
    time: timeFromDb,
    uuid: uuidFromDb,
  },
  infinityBind: () => MARIADB_INFINITY_SENTINEL,
  classifyErrorCode,
  isRetriable: (category) => category === "deadlock",
  violatesUniqueIndex: (category) => category === "uniqueViolation",
  isTimedOut: (category) => category === "lockWaitTimeout",
};
