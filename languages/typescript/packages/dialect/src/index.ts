/**
 * `@parallax/dialect` — M11 database seam & portability.
 *
 * The Postgres runtime DB seam: `?`→`$n` placeholder translation, the
 * neutral-type vocabulary, identifier quoting, the read-lock suffix, the
 * raw-string type parsers that normalize driver output at the adapter boundary,
 * and `CREATE TABLE` DDL derivation from a parsed descriptor.
 */

export { columnOrder, ddlForDescriptor } from "./ddl.js";
export {
  bytesFromDb,
  dateFromDb,
  int8FromRaw,
  numericFromRaw,
  POSTGRES_DIALECT,
  postgresColumnType,
  quoteIdentifier,
  RAW_TEXT_OIDS,
  readLockSuffix,
  timeFromDb,
  timestampFromDb,
  toPositionalPlaceholders,
  uuidFromDb,
} from "./postgres.js";
