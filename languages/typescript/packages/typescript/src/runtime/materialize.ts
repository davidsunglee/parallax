/**
 * Row materialization for the developer runtime (`px.*` finds), spec §3.2.1.
 *
 * A `find` compiles to a projection keyed by **physical column** (`RuntimeSchema`
 * projects `attr.column`), so the raw rows the database port returns are keyed by
 * column name with each scalar in whatever representation the bound adapter
 * produced. This module turns each such raw row into the managed object `T` a
 * developer expects: it
 *
 *  1. **renames** each physical column to its DSL property name (`local_time` →
 *     `localTime`, `external_id` → `externalId`), driven entirely by the entity
 *     metamodel (`attr.column` → `attr.name`), and
 *  2. **coerces** each scalar to its managed carrier per the attribute's M0 type
 *     (`int64` → `bigint`, `decimal` → `ParallaxDecimal`, `timestamp` →
 *     `Temporal.Instant`, `date` → `Temporal.PlainDate`, `time` →
 *     `Temporal.PlainTime`, `bytes` → `Uint8Array`, `uuid`/`string` → string,
 *     `boolean`, `json` → `ParallaxJsonValue`).
 *
 * The coercions apply the same `@parallax/core` / `@parallax/dialect` parse
 * functions the shippable `@parallax/db-postgres` adapter uses, but they run
 * **defensively / idempotently**: a value that is *already* managed (from a
 * managed adapter) is passed through (or copied, for `bytes`) unchanged, while a
 * raw driver representation (a string / number / `Buffer` from a thin BYO
 * adapter) is parsed into the managed carrier. Both adapter shapes therefore
 * yield the same correct managed object.
 *
 * This **subsumes** the earlier bytes-only normalizer: it is the single
 * materialization path for the developer runtime. (The conformance grader path —
 * `MetamodelSchema` / `readProjection` — is separate and unaffected; it grades in
 * the wire domain and never runs this materializer.)
 */

import { bytesFromHex, ParallaxDecimal, Temporal } from "@parallax/core";
import type { ParallaxRow } from "@parallax/db";
import { dateFromDb, timeFromDb, timestampFromDb } from "@parallax/dialect";
import type { EntityMetadata } from "@parallax/metamodel";

/** Matches an M0 `decimal(p,s)` neutral type token. */
const DECIMAL_TYPE = /^decimal\(\d+,\d+\)$/;

/**
 * Build a per-entity row materializer: `(rawRow keyed by column) → managed object
 * keyed by DSL name`. The mapping (column → name) and per-attribute coercion are
 * fixed by the entity metamodel, so the closure is built once per finder and
 * reused for every row.
 *
 * Only the entity's own attributes are projected into the managed object; a raw
 * row carries exactly those columns (the runtime projects the full attribute set,
 * spec §2.3), so there is no stray column to preserve.
 */
export function rowMaterializer(entity: EntityMetadata): (row: ParallaxRow) => ParallaxRow {
  const attributes = entity.attributes();
  return (row) => {
    const out: ParallaxRow = {};
    for (const attr of attributes) {
      out[attr.name] = coerceScalar(row[attr.column], attr.type);
    }
    return out;
  };
}

/**
 * Coerce one adapter-returned scalar to its managed carrier for the attribute's
 * M0 type, defensively: an already-managed value is passed through (or copied,
 * for `bytes`), a raw driver representation is parsed. `null` / `undefined` pass
 * through for every type (a nullable column stays null).
 */
function coerceScalar(value: unknown, type: string): unknown {
  if (value === null || value === undefined) {
    return value;
  }
  if (DECIMAL_TYPE.test(type)) {
    return coerceDecimal(value);
  }
  switch (type) {
    case "boolean":
      return coerceBoolean(value);
    case "int32":
    case "float32":
    case "float64":
      return coerceNumber(value);
    case "int64":
      return coerceBigInt(value);
    case "string":
    case "uuid":
      return coerceString(value);
    case "bytes":
      return coerceBytes(value);
    case "date":
      return coerceDate(value);
    case "time":
      return coerceTime(value);
    case "timestamp":
      return coerceTimestamp(value);
    case "json":
      return coerceJson(value);
    default:
      // An unknown M0 type is passed through untouched rather than guessed at.
      return value;
  }
}

/** `int64` → native `bigint` (already a `bigint` passes; a raw string/number is lifted). */
function coerceBigInt(value: unknown): unknown {
  if (typeof value === "bigint") {
    return value;
  }
  if (typeof value === "string") {
    return BigInt(value.trim());
  }
  if (typeof value === "number") {
    return BigInt(value);
  }
  return value;
}

/** `decimal(p,s)` → {@link ParallaxDecimal} (already one passes; a raw string/bigint is lifted). */
function coerceDecimal(value: unknown): unknown {
  if (value instanceof ParallaxDecimal) {
    return value;
  }
  if (typeof value === "string" || typeof value === "bigint") {
    return ParallaxDecimal.from(value);
  }
  return value;
}

/** `int32`/`float32`/`float64` → `number` (a raw numeric string is lifted). */
function coerceNumber(value: unknown): unknown {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string") {
    return Number(value);
  }
  return value;
}

/** `string`/`uuid` → string (a non-string carrier is stringified defensively). */
function coerceString(value: unknown): unknown {
  return typeof value === "string" ? value : String(value);
}

/**
 * `boolean` → `boolean`. An already-boolean passes; a driver's text (`t`/`f`,
 * `true`/`false`, `1`/`0`) or numeric (`0`/`1`) form is mapped without the
 * `== 1` pitfall (spec §3.2.1 comparison rule).
 */
function coerceBoolean(value: unknown): unknown {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (text === "t" || text === "true" || text === "1") {
      return true;
    }
    if (text === "f" || text === "false" || text === "0") {
      return false;
    }
  }
  return value;
}

/**
 * `bytes` → a **fresh** `Uint8Array` (spec §3.2.1). A Node `Buffer` /
 * `Uint8Array` is copied so the managed object never aliases the adapter's
 * buffer; a hex string (possibly `\x`-prefixed) is parsed. Because the column is
 * a KNOWN `bytes` column, a string value is unambiguously hex — no heuristic.
 */
function coerceBytes(value: unknown): unknown {
  if (value instanceof Uint8Array) {
    return Uint8Array.from(value);
  }
  if (typeof value === "string") {
    return bytesFromHex(value);
  }
  return value;
}

/** `date` → `Temporal.PlainDate` (already one passes; a raw `YYYY-MM-DD` string is parsed). */
function coerceDate(value: unknown): unknown {
  if (value instanceof Temporal.PlainDate) {
    return value;
  }
  if (typeof value === "string") {
    return dateFromDb(value);
  }
  return value;
}

/** `time` → `Temporal.PlainTime` (already one passes; a raw `HH:MM:SS` string is parsed). */
function coerceTime(value: unknown): unknown {
  if (value instanceof Temporal.PlainTime) {
    return value;
  }
  if (typeof value === "string") {
    return timeFromDb(value);
  }
  return value;
}

/**
 * `timestamp` → `Temporal.Instant` (already one passes; the `infinity` sentinel
 * passes; a raw Postgres/ISO string is parsed via the dialect; a driver `Date` is
 * lifted through its ISO rendering). The dialect parser enforces the M0
 * microsecond-precision rule.
 */
function coerceTimestamp(value: unknown): unknown {
  if (value instanceof Temporal.Instant) {
    return value;
  }
  if (typeof value === "string") {
    return timestampFromDb(value);
  }
  if (value instanceof Date) {
    return timestampFromDb(value.toISOString());
  }
  return value;
}

/**
 * `json` → `ParallaxJsonValue`. A driver that hands `jsonb` back as text is
 * parsed; an already-structured value (object / array / scalar) passes through.
 */
function coerceJson(value: unknown): unknown {
  if (typeof value === "string") {
    return JSON.parse(value);
  }
  return value;
}
