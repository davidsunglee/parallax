/**
 * The M11 Postgres dialect — the runtime DB seam.
 *
 * All Postgres-specific SQL decisions live here (and only here): the
 * `?`→`$n` placeholder translation, the neutral-type → column-type vocabulary,
 * the identifier-quoting rule, the in-transaction read-lock application, and the
 * **raw-string type parsers** that materialize `timestamptz` / `numeric` /
 * `int8` / `bytea` into `Temporal.Instant` / `ParallaxDecimal` / `bigint` /
 * `Uint8Array` at the adapter boundary (the §3.2.1 "normalize at the adapter
 * boundary" rule). The concrete Testcontainers provider (composition root)
 * delegates SQL execution and coercion to this seam — it owns no SQL text and no
 * type rules of its own.
 *
 * This module imports no driver: it exposes the *rules* a driver-bound provider
 * applies. Keeping the driver out of `@parallax/dialect` keeps the package free
 * of a Testcontainers / `postgres` dependency (design "provider placement"
 * decision).
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
import { classifyErrorCode } from "./errors.js";

/** The dialect identifier this seam answers for. */
export const POSTGRES_DIALECT = "postgres" as const;

/**
 * Translate the canonical `?` positional placeholders (M3) into Postgres `$n`
 * placeholders, numbered left-to-right starting at `$1`.
 *
 * The canonical SQL never carries a literal `?` outside a placeholder position
 * (rule 4), so a straight left-to-right substitution is exact. Returns the
 * rewritten SQL; the caller passes the binds array unchanged (its order already
 * matches placeholder order).
 */
export function toPositionalPlaceholders(sql: string): string {
  let n = 0;
  return sql.replace(/\?/g, () => {
    n += 1;
    return `$${n}`;
  });
}

/** The canonical root-table alias the M3 SELECT projects from (`from tbl t0`). */
const READ_LOCK_ALIAS = "t0";

/**
 * **Apply** this dialect's in-transaction shared read lock to a compiled read (M8
 * automatic read-lock correctness, owned by the M11 seam per delta `09` D3). The
 * dialect owns the whole decision — whether, where, and how the lock attaches —
 * not merely the suffix text:
 *
 *  - a lockable **object find** in `locking` mode gets the shared-row-lock form
 *    appended after every other clause — Postgres `for share of t0` (alias-
 *    qualified, lowercased);
 *  - a **projection / aggregation** read (`projection: true` — a `select distinct` /
 *    grouped / aggregate result) is returned **unchanged**: its result rows have no
 *    identifiable base row to lock, and per ADR 0024 return plain unmanaged data, so
 *    there is nothing to protect — it proceeds unlocked rather than erroring (ADR
 *    0030, the D2 reversal);
 *  - any **non-`locking`** read (`optimistic` mode, or an out-of-transaction read)
 *    is returned unchanged.
 *
 * The lock-omission decision keys on the caller-supplied `projection` boolean — the
 * authoritative contract flag `compile` derives from whether it emitted `distinct`
 * (`m11:203-216`) — NOT a regex over the SQL text: the compiler already knows the
 * read's shape, so the seam trusts the flag rather than re-deriving it from the SQL.
 *
 * MariaDB diverges (no `for share`; MDEV-17514): its shared lock is the unaliased
 * `lock in share mode`, appended after every other clause. That form lands with the
 * second concrete dialect (the `Dialect`-interface effort); it is not wired here.
 */
export function applyReadLock(
  sql: string,
  options: { readonly locking: boolean; readonly projection: boolean },
): string {
  if (!options.locking || options.projection) {
    return sql;
  }
  return `${sql} for share of ${READ_LOCK_ALIAS}`;
}

/**
 * One ORDER BY term with Postgres's NULL placement (the M4/M11 catalog table,
 * `m11:153-167`). Postgres sorts NULLs last for `asc` and first for `desc` by
 * default, so an ascending term is emitted **bare** (relying on the native
 * default, byte-identical to today's `compile.ts` output) while a descending term
 * gets an explicit `nulls last` to override the default and match the neutral
 * "NULLs sort last" ordering. MariaDB expresses the same intent with a leading
 * `is null,` term (its `mariadbDialect` sibling).
 */
export function orderByTerm(qualifiedColumn: string, direction: "asc" | "desc"): string {
  if (direction === "desc") {
    // `desc nulls last` is spec-mandated — the m11 NULL-ordering table
    // (`m11:153-167`) fixes Postgres descending as `order by <col> desc nulls last`.
    // Bare `desc` would put NULLs FIRST, violating the M4 canonical rule that sorts
    // NULLs LAST on every key, so the explicit `nulls last` is REQUIRED. Do NOT
    // "simplify" this to bare `desc`.
    return `${qualifiedColumn} desc nulls last`;
  }
  return `${qualifiedColumn} asc`;
}

/**
 * Apply the Postgres row-limit clause — append ` limit ?` (the bind carries the
 * count). Modeled as a *wrappable* hook rather than a bare suffix so a future
 * dialect that must rewrite the query shape (Oracle `ROWNUM`, SQL Server `TOP`)
 * can override the whole assembly rather than only append.
 */
export function rowLimit(sql: string): string {
  return `${sql} limit ?`;
}

// --- neutral-type → Postgres column type (the M0 table) ---------------------

/** M0 neutral base type → Postgres column type (non-parametric types). */
const POSTGRES_BASE_TYPES: Readonly<Record<string, string>> = {
  boolean: "boolean",
  int32: "integer",
  int64: "bigint",
  float32: "real",
  float64: "double precision",
  bytes: "bytea",
  date: "date",
  time: "time",
  timestamp: "timestamptz",
  uuid: "uuid",
  json: "jsonb",
};

/** Matches a `decimal(p,s)` neutral type token and captures precision/scale. */
const DECIMAL_TYPE = /^decimal\((\d+),(\d+)\)$/;

/**
 * Map an M0 neutral type to its Postgres column type. `decimal(p,s)` →
 * `numeric(p,s)`, a bounded `string` → `varchar(n)`, an unbounded `string` →
 * `text`; everything else comes from the base table.
 */
export function postgresColumnType(neutralType: string, maxLength?: number): string {
  const decimal = DECIMAL_TYPE.exec(neutralType);
  if (decimal) {
    return `numeric(${decimal[1]},${decimal[2]})`;
  }
  if (neutralType === "string") {
    return maxLength ? `varchar(${maxLength})` : "text";
  }
  const base = POSTGRES_BASE_TYPES[neutralType];
  if (base === undefined) {
    throw new Error(`no Postgres mapping for neutral type '${neutralType}'`);
  }
  return base;
}

// --- identifier quoting ------------------------------------------------------

/** A lexically-simple identifier needs no quoting unless it is reserved. */
const SIMPLE_IDENTIFIER = /^[a-z_][a-z0-9_]*$/;

/**
 * Reserved words that, although lexically simple, MUST be quoted as an
 * identifier (mirrors the harness's curated set). A non-simple name (uppercase /
 * special) is caught by the regex regardless.
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
 * Quote a Postgres identifier when it is reserved or otherwise non-simple. A
 * simple lowercase non-reserved identifier is returned unquoted (so generated
 * SQL is byte-identical to the hand-authored goldens); a reserved word (e.g.
 * `order`) or a name with uppercase / special characters is double-quoted, with
 * any embedded double-quote doubled.
 */
export function quoteIdentifier(name: string): string {
  if (SIMPLE_IDENTIFIER.test(name) && !RESERVED_WORDS.has(name)) {
    return name;
  }
  return `"${name.replace(/"/g, '""')}"`;
}

// --- raw-string type coercion at the adapter boundary -----------------------

/*
 * The driver's raw-text type codes (Postgres OIDs) that must be parsed here now
 * live in the adapter (`@parallax/db-postgres`, `oids.ts`), because *which codes are
 * raw text* is a driver concern while *how to parse* is the dialect's (Q3-A). The
 * parse functions below stay the single source of parse logic, surfaced through the
 * `postgresDialect.parsers` record.
 */

/**
 * Materialize a raw `int8` string into a native `bigint`. The driver must be
 * configured to hand `int8` columns back as text (its default `number` parse
 * silently loses precision beyond `2^53`).
 */
export function int8FromRaw(raw: string): bigint {
  return BigInt(raw.trim());
}

/**
 * Materialize a raw `numeric` string into a {@link ParallaxDecimal} — exact, in
 * decimal space, never a binary float (the driver default would inject float
 * drift into a money column).
 */
export function numericFromRaw(raw: string): ParallaxDecimal {
  return ParallaxDecimal.from(raw.trim());
}

/**
 * Materialize a raw `timestamptz`/`timestamp` string into a `Temporal.Instant`
 * at microsecond precision, passing the native-infinity sentinel through as the
 * `infinity` literal (the open temporal upper bound has no instant).
 */
export function timestampFromDb(raw: string): Temporal.Instant | InfinitySentinel {
  const text = raw.trim();
  if (text === "infinity" || text === "-infinity") {
    return INFINITY;
  }
  return timestampFromRaw(text);
}

/**
 * Materialize a raw `bytea` rendering (`\xDEADBEEF`) into a `Uint8Array`. The
 * provider configures the driver to return `bytea` as its hex text form.
 */
export function bytesFromDb(raw: string): Uint8Array {
  return bytesFromHex(raw.trim());
}

/**
 * Materialize a raw `date` string (`2024-03-01`) into a `Temporal.PlainDate` —
 * a calendar date with no time or offset (the managed carrier for `date`, §3.2.1).
 */
export function dateFromDb(raw: string): Temporal.PlainDate {
  return Temporal.PlainDate.from(raw.trim());
}

/**
 * Materialize a raw `time` string (`12:34:56`, optionally with fractional
 * seconds) into a `Temporal.PlainTime` — a wall-clock time with no date or
 * offset (the managed carrier for `time`, §3.2.1).
 */
export function timeFromDb(raw: string): Temporal.PlainTime {
  return Temporal.PlainTime.from(raw.trim());
}

/**
 * Materialize a raw `uuid` string into a canonical lowercase string — `uuid` has
 * no managed carrier beyond `string`, but the parse fn lives here so the dialect
 * stays the single source of parse logic and an adapter owns only OID
 * registration.
 */
export function uuidFromDb(raw: string): string {
  return raw.trim();
}

// --- the reified Postgres dialect --------------------------------------------

/**
 * The concrete Postgres {@link Dialect} — the layer-1 authority for Postgres,
 * reifying the loose functions above into the normative contract. Its methods
 * delegate to those functions (all correct and tested); the `parsers` record maps
 * each M0 neutral key to its `*FromRaw`/`*FromDb` parser, and `infinityBind`
 * returns the native `'infinity'` sentinel Postgres binds directly.
 *
 * The three error predicates are category membership over the closed neutral
 * vocabulary (`classifyErrorCode` yields the category; the predicates test it),
 * mirroring Reladomo's predicate-per-call-site classification.
 */
export const postgresDialect: Dialect = {
  id: POSTGRES_DIALECT,
  quoteIdentifier,
  orderByTerm,
  rowLimit,
  applyReadLock,
  columnType: postgresColumnType,
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
  infinityBind: () => INFINITY,
  classifyErrorCode,
  isRetriable: (category) => category === "deadlock",
  violatesUniqueIndex: (category) => category === "uniqueViolation",
  isTimedOut: (category) => category === "lockWaitTimeout",
};
