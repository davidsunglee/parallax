/**
 * The single in-transaction read executor (delta `09` D1/D3), shared by the flat
 * find path (`parallax.ts` `runOperation`) and every deep-fetch level (root +
 * each included child, `deep-fetch.ts`).
 *
 * It applies this unit of work's read lock through the M11 dialect
 * (`applyReadLock`) and executes: a `locking`-mode object find takes the shared
 * row lock (M8 automatic read-lock correctness); a projection/aggregation read —
 * or any `optimistic`-mode / out-of-transaction read — passes through unlocked (no
 * base row to lock, unmanaged data per ADR 0024; ADR 0030). Lock application lives
 * here, in exactly one place, so a new in-transaction read site does not re-plumb
 * the lock/observe wiring (the recurring soft spot `07-handoff §6` calls out).
 *
 * The runtime is the composition root, so it imports the concrete dialect's
 * `applyReadLock` directly from `@parallax/dialect` (a legal edge).
 */

import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";
import { applyReadLock } from "@parallax/dialect";
import type { Concurrency } from "./writes.js";

/**
 * Execute one in-transaction read: ask the dialect to apply the read lock for the
 * enclosing unit-of-work `mode`, then run the statement and return the rows. The
 * `mode` is absent on a root-handle / out-of-transaction read (no lock, like
 * `optimistic`).
 */
export function executeRead(
  database: ParallaxDatabase,
  sql: string,
  binds: readonly unknown[],
  mode: Concurrency | undefined,
): Promise<readonly ParallaxRow[]> {
  return database.execute(applyReadLock(sql, { locking: mode === "locking" }), binds);
}
