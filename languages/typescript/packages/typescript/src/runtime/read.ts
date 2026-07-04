/**
 * The single in-transaction read executor (delta `09` D1/D3), shared by the flat
 * find path (`parallax.ts` `runOperation`) and every deep-fetch level (root +
 * each included child, `deep-fetch.ts`).
 *
 * Since the M3 → M11 inversion the SQL arrives **already locked**: `compile()`
 * applies the dialect's in-transaction shared read-lock as its final step (gated on
 * the unit of work's `locking` mode), so a `locking`-mode object find carries the
 * shared row lock (M8 automatic read-lock correctness) and a projection/aggregation
 * read — or any `optimistic`-mode / out-of-transaction read — carries none. This
 * executor therefore just runs the compiled statement, keeping a single place where
 * every in-transaction read reaches the port (the recurring soft spot `07-handoff
 * §6` calls out).
 */

import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";

/** Execute one already-locked compiled read statement and return the rows. */
export function executeRead(
  database: ParallaxDatabase,
  sql: string,
  binds: readonly unknown[],
): Promise<readonly ParallaxRow[]> {
  return database.execute(sql, binds);
}
