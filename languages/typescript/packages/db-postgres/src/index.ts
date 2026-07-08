/**
 * `@parallax/db-postgres` — the shippable Postgres adapter (m-db-port decomposition,
 * layer 3): a concrete `ParallaxDatabase` over the `postgres` (porsager) driver,
 * from a connection string / pool, returning managed scalars via the
 * `@parallax/dialect` parse functions for reads and native affected-row counts
 * for writes. No Testcontainers, no `@parallax/typescript` dependency, no wire /
 * grading logic.
 */
export { PostgresDatabase, type PostgresDatabaseOptions, PostgresSession } from "./adapter.js";
export { managedTypes, serializeBytea, serializeJson } from "./oids.js";
