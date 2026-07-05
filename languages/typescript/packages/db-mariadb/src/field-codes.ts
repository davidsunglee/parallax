/**
 * mysql2 field-type → neutral parser key map for `@parallax/db-mariadb`.
 *
 * The MariaDB analogue of `@parallax/db-postgres`'s `RAW_TEXT_OIDS`: an adapter /
 * driver concern (the field type `mysql2` reports for each returned column, in its
 * `typeCast` callback) mapped to the M0 neutral key whose parser materializes the
 * column into a **managed** scalar. The *parse logic* keyed by neutral type lives
 * on `mariadbDialect.parsers` (the pure dialect layer stays the single source of
 * parse logic — M11 decomposition); this map is only "which driver field types are
 * read as raw text, and which neutral parser they route to" (`m11:44-47`, Q3-A).
 *
 * MariaDB has no OIDs — `mysql2` exposes the MySQL/MariaDB protocol field type by
 * its **name** (`'LONGLONG'`, `'NEWDECIMAL'`, `'DATETIME'`, …) in the `typeCast`
 * field — which is exactly why the *type identity* lives on the adapter and the
 * *parse functions* on the dialect. A type absent from this map is left to
 * `mysql2`'s default cast (an `int32` / `float` arrives as a JS `number`, a
 * `varchar` / `char(36)` uuid as a plain string — already the correct managed /
 * wire form), so only the types whose driver-default parse would violate an M0
 * contract are listed.
 */
import type { DialectParsers } from "@parallax/dialect";

/** A neutral parser key on {@link DialectParsers}. */
export type NeutralParserKey = keyof DialectParsers;

/**
 * The MariaDB field-type name → neutral parser key map. A column whose `mysql2`
 * field type is present is read as **raw text** (via the driver's `field.string()`)
 * and parsed by `mariadbDialect.parsers[key]` into its managed carrier (`bigint` /
 * `ParallaxDecimal` / `Temporal.*` / `Uint8Array`). The open temporal upper bound
 * (`9999-12-31 23:59:59.999999`) is detected inside the `timestamp` parser and
 * mapped back to the `infinity` sentinel, so a fixture authored once against
 * native-infinity Postgres compares identically here.
 */
export const MARIADB_FIELD_TYPES: Readonly<Record<string, NeutralParserKey>> = {
  /** Exact decimal — driver returns a lossy binary float / string; parse to `ParallaxDecimal`. */
  DECIMAL: "numeric",
  NEWDECIMAL: "numeric",
  /** `bigint` — JS `number` cannot hold the full int64 range. */
  LONGLONG: "int8",
  /** An instant (µs precision); driver-default parse is a lossy ms `Date`. */
  TIMESTAMP: "timestamp",
  TIMESTAMP2: "timestamp",
  DATETIME: "timestamp",
  DATETIME2: "timestamp",
  /** A calendar date (no time / offset). */
  DATE: "date",
  NEWDATE: "date",
  /** A wall-clock time (no date / offset). */
  TIME: "time",
  TIME2: "time",
  /**
   * A byte string (`longblob` and its siblings). All four names route to the same
   * neutral `bytes` key; `adapter.ts`'s `typeCast` then distinguishes a RAW
   * un-wrapped column (read via `field.buffer()`) from the dialect's `HEX(...)`
   * projection (hex-decoded from `field.string()`) by the codebase-owned `_hex`
   * output-alias convention (`field.name`), not the driver's field-type name — see
   * its doc comment for why that split is needed.
   */
  TINY_BLOB: "bytes",
  MEDIUM_BLOB: "bytes",
  LONG_BLOB: "bytes",
  BLOB: "bytes",
};
