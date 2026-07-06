/**
 * `@parallax/db` — the abstract runtime database port and its portable error
 * surface (`m-db-port`, `m-db-error`). The execution interface
 * (`ParallaxDatabase` + `ParallaxRow`) the runtime and composition root call to
 * run compiled SQL; concrete adapters (`@parallax/db-postgres`,
 * `@parallax/db-mariadb`) implement it and return managed scalars for reads plus
 * affected-row counts for writes.
 */
export { ParallaxTransientError, type TransientErrorKind } from "./errors.js";
export type { ParallaxDatabase, ParallaxRow } from "./port.js";
