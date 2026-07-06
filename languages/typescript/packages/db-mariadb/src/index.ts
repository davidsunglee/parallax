/**
 * `@parallax/db-mariadb` — the shippable MariaDB adapter (m-db-port decomposition,
 * layer 3): a concrete `ParallaxDatabase` over the `mysql2` driver, returning
 * managed scalars via the `@parallax/dialect` `mariadbDialect` parsers for reads
 * and native affected-row counts for writes. The MariaDB sibling of
 * `@parallax/db-postgres`. No Testcontainers, no `@parallax/typescript`
 * dependency, no wire / grading logic.
 */
export {
  classifyMariaError,
  instantToMariaDatetime,
  MariaDbDatabase,
  type MariaDbDatabaseOptions,
  MariaDbSession,
  toMariaBind,
  toMariaBinds,
} from "./adapter.js";
export { MARIADB_FIELD_TYPES, type NeutralParserKey } from "./field-codes.js";
