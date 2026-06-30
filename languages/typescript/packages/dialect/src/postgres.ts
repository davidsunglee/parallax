/**
 * The M11 Postgres dialect — the runtime DB seam.
 *
 * All Postgres-specific SQL decisions live here (and only here): the
 * `?`→`$n` placeholder translation, the neutral-type → column-type vocabulary,
 * the identifier-quoting rule, the shared read-lock suffix, and the
 * **raw-string type parsers** that materialize `timestamptz` / `numeric` /
 * `int8` / `bytea` into `Temporal.Instant` / `ParallaxDecimal` / `bigint` /
 * `Uint8Array` at the adapter boundary (the §2.2.1 "normalize at the adapter
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
  type Temporal,
  timestampFromRaw,
} from "@parallax/core";

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

/**
 * The read-lock suffix for an in-transaction shared row lock (M8), owned by the
 * M11 seam. Postgres renders the shared lock as `for share of <alias>`
 * (alias-qualified, lowercased). MariaDB diverges (`lock in share mode`); that
 * lands when the second dialect does. The locking package (Phase 7) appends
 * this; it is defined here so the dialect owns the SQL text.
 */
export function readLockSuffix(alias: string): string {
  return `for share of ${alias}`;
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

/**
 * The Postgres OIDs whose driver-default parse would violate an M0 contract, so
 * the provider registers a raw-text parser for each and we materialize the value
 * here. The OIDs are the stable Postgres catalog numbers.
 */
export const RAW_TEXT_OIDS = {
  /** `int8` — `bigint`. JS `number` cannot hold the full int64 range. */
  int8: 20,
  /** `numeric` — exact decimal. The driver default is a lossy binary float. */
  numeric: 1700,
  /** `timestamptz` — UTC instant. The driver default is a ms-precision `Date`. */
  timestamptz: 1184,
  /** `timestamp` — same precision concern as `timestamptz`. */
  timestamp: 1114,
  /** `bytea` — `Uint8Array`, parsed from the `\x…` hex rendering. */
  bytea: 17,
} as const;

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
