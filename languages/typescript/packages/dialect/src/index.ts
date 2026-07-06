/**
 * `@parallax/dialect` — m-dialect database seam & portability.
 *
 * Layer-1 of the seam: the normative {@link Dialect} interface (the single
 * authority over the per-database decision catalog) plus its two conforming
 * implementations, `postgresDialect` and `mariadbDialect`. The catalog covers `?`→`$n` placeholder
 * translation, the neutral-type vocabulary, identifier quoting, ORDER BY / NULL
 * placement, the row-limit clause, in-transaction read-lock application, typed
 * bind normalization, the SQLSTATE → neutral-category error classification, the
 * raw-string type parsers that normalize driver output at the adapter boundary,
 * and `CREATE TABLE` DDL derivation from a parsed descriptor.
 *
 * The underlying free functions stay exported (consumers re-source through the
 * `Dialect` object in a later phase).
 */

export { columnOrder, ddlForDescriptor } from "./ddl.js";
export type { Dialect, DialectParsers } from "./dialect.js";
export {
  classifyErrorCode,
  type ErrorCategory,
  isRetriableCategory,
} from "./errors.js";
export { MARIADB_DIALECT, MARIADB_INFINITY_SENTINEL, mariadbDialect } from "./mariadb.js";
export {
  applyReadLock,
  bytesFromDb,
  dateFromDb,
  int8FromRaw,
  numericFromRaw,
  orderByTerm,
  POSTGRES_DIALECT,
  postgresColumnType,
  postgresDialect,
  quoteIdentifier,
  timeFromDb,
  timestampFromDb,
  toPositionalPlaceholders,
  uuidFromDb,
} from "./postgres.js";
