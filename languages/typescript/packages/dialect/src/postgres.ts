/**
 * The m-dialect Postgres dialect — the runtime DB seam.
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
  toWire,
} from "@parallax/core";
import type {
  Dialect,
  DialectFragment,
  NestedArrayRequest,
  ResolvedElementPredicate,
} from "./dialect.js";
import { classifyErrorCode } from "./errors.js";
import { rawJson } from "./raw-json.js";

/** The dialect identifier this seam answers for. */
export const POSTGRES_DIALECT = "postgres" as const;

/**
 * Translate the canonical `?` positional placeholders (m-sql) into Postgres `$n`
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

/** The canonical root-table alias the m-sql SELECT projects from (`from tbl t0`). */
const READ_LOCK_ALIAS = "t0";

/**
 * **Apply** this dialect's in-transaction shared read lock to a compiled read (m-read-lock
 * automatic read-lock correctness, owned by the m-dialect seam per delta `09` D3). The
 * dialect owns the whole decision — whether, where, and how the lock attaches —
 * not merely the suffix text:
 *
 *  - a lockable **object find** in `locking` mode gets the shared-row-lock form
 *    appended after every other clause — Postgres `for share of t0` (alias-
 *    qualified, lowercased);
 *  - a **projection / aggregation** read (`projection: true` — a `select distinct` /
 *    grouped / aggregate result) is returned **unchanged**: its result rows have no
 *    identifiable base row to lock, and per core ADR 0002 return plain unmanaged data, so
 *    there is nothing to protect — it proceeds unlocked rather than erroring (the D2 reversal;
 *    core ADR 0012);
 *  - any **non-`locking`** read (`optimistic` mode, or an out-of-transaction read)
 *    is returned unchanged.
 *
 * The lock-omission decision keys on the caller-supplied `projection` boolean — the
 * authoritative contract flag `compile` derives from whether it emitted `distinct`
 * (`m-dialect`) — NOT a regex over the SQL text: the compiler already knows the
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
 * One ORDER BY term with Postgres's NULL placement (the m-navigate/m-dialect catalog table,
 * `m-dialect`). Postgres sorts NULLs last for `asc` and first for `desc` by
 * default, so an ascending term is emitted **bare** (relying on the native
 * default, byte-identical to today's `compile.ts` output) while a descending term
 * gets an explicit `nulls last` to override the default and match the neutral
 * "NULLs sort last" ordering. MariaDB expresses the same intent with a leading
 * `is null,` term (its `mariadbDialect` sibling).
 */
export function orderByTerm(qualifiedColumn: string, direction: "asc" | "desc"): string {
  if (direction === "desc") {
    // `desc nulls last` is spec-mandated — the m-dialect NULL-ordering table
    // (`m-dialect`) fixes Postgres descending as `order by <col> desc nulls last`.
    // Bare `desc` would put NULLs FIRST, violating the m-navigate canonical rule that sorts
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

/** The Postgres `encode(...)` format for a `bytes`-column hex projection. */
const HEX_ENCODE_FORMAT = "hex";

/**
 * Lower a `bytes` column to Postgres's hex-text projection — `encode(<col>, ?)
 * <out>` — carrying the `'hex'` format as a bind (not an inline literal), spliced
 * in projection order. Byte-identical to the form `compile.ts` emitted before the
 * projection moved behind the dialect (`m-core-001`).
 */
export function bytesProjection(
  qualifiedColumn: string,
  outputName: string,
): { readonly sql: string; readonly binds: readonly unknown[] } {
  return {
    sql: `encode(${qualifiedColumn}, ?) ${outputName}`,
    binds: [HEX_ENCODE_FORMAT],
  };
}

// --- value-object structured-column lowering (m-value-object / m-sql) ---------

/**
 * Postgres **nested extraction form** (`m-dialect`): `jsonb_extract_path_text(col,
 * ?, …)` — one `?` bind **per path segment**, in path order. A JSON `null` leaf, a
 * missing key, and a non-object intermediate all extract SQL `NULL` (the
 * absence-collapse rule). Serves both a top-level column (`t0.address`) and a
 * to-many element (`t1.value`).
 */
export function nestedExtraction(
  baseExpression: string,
  segments: readonly string[],
): DialectFragment {
  const placeholders = segments.map(() => "?").join(", ");
  return {
    sql: `jsonb_extract_path_text(${baseExpression}, ${placeholders})`,
    binds: [...segments],
  };
}

/** Postgres cast targets for the non-text neutral types (the m-dialect typed-cast table). */
const POSTGRES_CASTS: Readonly<Record<string, string>> = {
  int32: "bigint",
  int64: "bigint",
  float32: "double precision",
  float64: "double precision",
};

/**
 * Postgres **typed cast form** (`m-dialect`): the text extraction is cast to the
 * declared neutral type before a numeric comparison — `cast(<extraction> as double
 * precision)` / `… as bigint` / `… as decimal(p, s)`. A `string` (or any
 * text/temporal) attribute compares directly, so the extraction is returned
 * unchanged.
 */
export function typedCast(extraction: string, neutralType: string): string {
  const decimal = DECIMAL_TYPE.exec(neutralType);
  if (decimal) {
    return `cast(${extraction} as decimal(${decimal[1]}, ${decimal[2]}))`;
  }
  const target = POSTGRES_CASTS[neutralType];
  return target === undefined ? extraction : `cast(${extraction} as ${target})`;
}

/** The JSON type-name / empty-array literals the array guard binds (kept as `?` binds). */
const PG_JSON_ARRAY_TYPE = "array";
/**
 * The empty-array fallback the `case`/`jsonb_typeof` guard binds to `cast(? as jsonb)`
 * when the column is not a JSON array (absence collapse). It is already-canonical JSON
 * text, so it must reach the driver VERBATIM — {@link rawJson} wraps it so the adapter's
 * fail-safe json serializer passes it through raw rather than JSON-encoding it into the
 * jsonb string scalar `"[]"` (which `jsonb_array_elements` would reject). The wrapper is
 * canonicalized back to the plain string `"[]"` wherever the compiled bind is reported or
 * compared to a golden.
 */
const PG_EMPTY_ARRAY = "[]";

/**
 * Render a resolved element predicate over the Postgres unnested element alias
 * (`t1.value`) — the general lowering the correlated `jsonb_array_elements` subquery
 * carries in its `where`. Every leaf reads the element field with the ordinary
 * `jsonb_extract_path_text` extraction (a numeric leaf casts); the combinators map
 * to `and` / `or` / leading-`not` / parenthesized `group`.
 */
function renderElement(pred: ResolvedElementPredicate, base: string): DialectFragment {
  switch (pred.op) {
    case "eq":
    case "notEq": {
      const ext = nestedExtraction(base, pred.path);
      // Cast the text extraction to the declared leaf type before comparing, exactly
      // as the range ops below do (m-dialect typed-cast form): a no-op for a string
      // element field (so the equality-only corpus goldens stay byte-identical) and a
      // real cast for a numeric one. A boolean field compares as JSON text.
      const expr = `${typedCast(ext.sql, pred.valueType)} = ?`;
      return {
        sql: pred.op === "notEq" ? `not ${expr}` : expr,
        binds: [...ext.binds, elementCompareBind(pred.value, pred.valueType)],
      };
    }
    case "gt":
    case "gte":
    case "lt":
    case "lte": {
      const ext = nestedExtraction(base, pred.path);
      return {
        sql: `${typedCast(ext.sql, pred.valueType)} ${COMPARISON_OPS[pred.op]} ?`,
        binds: [...ext.binds, pred.value],
      };
    }
    case "in": {
      const ext = nestedExtraction(base, pred.path);
      const placeholders = pred.values.map(() => "?").join(", ");
      return {
        sql: `${typedCast(ext.sql, pred.valueType)} in (${placeholders})`,
        binds: [
          ...ext.binds,
          ...pred.values.map((value) => elementCompareBind(value, pred.valueType)),
        ],
      };
    }
    case "isNull": {
      const ext = nestedExtraction(base, pred.path);
      return { sql: `${ext.sql} is null`, binds: [...ext.binds] };
    }
    case "isNotNull": {
      const ext = nestedExtraction(base, pred.path);
      return { sql: `not ${ext.sql} is null`, binds: [...ext.binds] };
    }
    case "and":
    case "or": {
      const parts = pred.operands.map((operand) => renderElement(operand, base));
      return {
        sql: parts.map((part) => part.sql).join(` ${pred.op} `),
        binds: parts.flatMap((part) => [...part.binds]),
      };
    }
    case "not": {
      const inner = renderElement(pred.operand, base);
      return { sql: `not ${inner.sql}`, binds: inner.binds };
    }
    case "group": {
      const inner = renderElement(pred.operand, base);
      return { sql: `(${inner.sql})`, binds: inner.binds };
    }
  }
}

/**
 * The comparison-bind form of an equality/membership element value. A **boolean**
 * element field carries no typed cast (m-dialect specifies casts only for int /
 * float / decimal), so it compares against its JSON-text form (`'true'` / `'false'`)
 * over the text extraction, rather than an invented boolean cast. Every other value
 * (already coerced to its wire form upstream) binds unchanged — a numeric field casts
 * the extraction instead. (Contrast MariaDB's containment candidate, which carries the
 * native JSON boolean.)
 */
function elementCompareBind(value: unknown, valueType: string): unknown {
  if (valueType === "boolean" && typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return value;
}

/** The SQL comparison operator for each range element op. */
const COMPARISON_OPS: Readonly<Record<"gt" | "gte" | "lt" | "lte", string>> = {
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<=",
};

/**
 * Postgres **array traversal form** (`m-dialect`): a correlated `exists` over a
 * set-returning `jsonb_array_elements` unnest. The strict `jsonb_array_elements`
 * errors on a non-array, so the array is reached through a `case`/`jsonb_typeof`
 * guard that yields the extracted value only when it IS a JSON array and an empty
 * `[]` otherwise — folding every non-array `many` value (NULL column, missing key,
 * JSON `null`, scalar, object) to zero elements (absence collapse). The path binds
 * **twice** (in the `when` and the `then`), plus the type name `array` and `[]`.
 * `nestedNotExists` prepends a leading `not`; the lowering is fully general over the
 * element predicate.
 */
export function nestedArrayPredicate(request: NestedArrayRequest): DialectFragment {
  const { column, arrayPath, elementAlias, negated, element } = request;
  const pathHoles = arrayPath.map(() => ", ?").join("");
  const guard =
    `case when jsonb_typeof(jsonb_extract_path(${column}${pathHoles})) = ? ` +
    `then jsonb_extract_path(${column}${pathHoles}) else cast(? as jsonb) end`;
  const guardBinds = [...arrayPath, PG_JSON_ARRAY_TYPE, ...arrayPath, rawJson(PG_EMPTY_ARRAY)];
  const rendered =
    element === undefined ? undefined : renderElement(element, `${elementAlias}.value`);
  const where = rendered === undefined ? "" : ` where ${rendered.sql}`;
  const exists = `exists (select 1 from jsonb_array_elements(${guard}) ${elementAlias}${where})`;
  return {
    sql: negated ? `not ${exists}` : exists,
    binds: [...guardBinds, ...(rendered?.binds ?? [])],
  };
}

// --- neutral-type → Postgres column type (the m-core table) ---------------------

/** m-core neutral base type → Postgres column type (non-parametric types). */
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
 * Map an m-core neutral type to its Postgres column type. `decimal(p,s)` →
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

/**
 * Normalize one managed runtime value for the porsager driver boundary. Most
 * values render to the neutral wire form (`toWire`); a `bytes` value is kept as
 * its raw `Uint8Array` carrier so porsager infers the `bytea` type (OID 17) and
 * serializes it as `\xDEADBEEF`. Flattening it through `toWire` would hand
 * porsager a hex STRING, which Postgres coerces via the `bytea` *escape* format —
 * storing the ASCII hex characters, not the intended bytes.
 *
 * A `json` value (m-value-object / m-core json) is a plain, unencoded JS structure or
 * scalar bound to a structured-document column. It is **pre-serialized to canonical
 * JSON and wrapped in the {@link rawJson} sentinel**, so the adapter's json serializer
 * emits that text verbatim. The wrapper is load-bearing on the write path: the porsager
 * driver infers a bind's Postgres type from its JS value and sends it in `Parse`, so a
 * bare `true` / `bigint` / array would be described to the server as boolean / int8 /
 * array and REJECTED by a `json`/`jsonb` column — only a value porsager can't type (a
 * plain object, like this sentinel) is described by the column OID and routed through
 * the json serializer. Pre-serializing here (rather than passing the raw value) keeps
 * every JSON shape correct; the serializer's fail-safe `JSON.stringify` default remains
 * the safety net for a DIRECT / missed-path bind that reaches it unwrapped. A null json
 * value binds as SQL NULL (no sentinel).
 */
function bindValue(neutralType: string, value: unknown): unknown {
  if (value instanceof Uint8Array) {
    return value;
  }
  if (neutralType === "json" && value !== null && value !== undefined) {
    return rawJson(JSON.stringify(value));
  }
  return toWire(value);
}

// --- the reified Postgres dialect --------------------------------------------

/**
 * The concrete Postgres {@link Dialect} — the layer-1 authority for Postgres,
 * reifying the loose functions above into the normative contract. Its methods
 * delegate to those functions (all correct and tested); the `parsers` record maps
 * each m-core neutral key to its `*FromRaw`/`*FromDb` parser, and `infinityBind`
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
  bytesProjection,
  nestedExtraction,
  typedCast,
  nestedArrayPredicate,
  applyReadLock,
  columnType: postgresColumnType,
  bindValue,
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
