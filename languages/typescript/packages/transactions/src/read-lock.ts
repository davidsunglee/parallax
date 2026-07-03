/**
 * M8 in-transaction shared read lock — the automatic read-lock correctness rule.
 *
 * A read performed inside a unit of work that intends to write is made correct
 * automatically: the default in-transaction read appends the dialect's shared-row-
 * lock suffix so a concurrent transaction cannot mutate the row out from under a
 * read-then-write (`m8-transactions-cache.md`, *Automatic read-lock correctness*).
 * The caller writes no locking SQL.
 *
 * The lock SUFFIX text is owned by the M11 dialect seam (`@parallax/dialect`,
 * `readLockSuffix` → Postgres `for share of t0`); this module's job is the M8
 * discipline of APPENDING it to an already-built read, after every other clause
 * (the canonical fixed point the `0603` golden pins). Keeping the append here (not
 * in the pure M3 compiler) keeps the lock a transaction-scoped concern: an
 * ordinary read emits no suffix, an in-transaction read does.
 */
import { readLockSuffix } from "@parallax/dialect";

/**
 * Thrown when a read whose result shape cannot legally carry a row-level lock is
 * asked to take the M8 shared read lock.
 *
 * A SQL `FOR SHARE` / `FOR UPDATE` row-locking clause locks the **base rows** a
 * statement reads, so the SQL standard — and both Postgres and MariaDB — reject it
 * on a result whose rows are not base rows: a `DISTINCT`, `GROUP BY`, or aggregate
 * projection has no single base row to lock (Postgres errors with *"FOR SHARE is
 * not allowed with DISTINCT clause"*). Rather than append the suffix and emit SQL
 * the database rejects at execution time, the lock seam rejects it here with a
 * clear diagnostic so the caller learns the boundary at the API surface.
 */
export class ParallaxUnlockableReadError extends Error {
  constructor(reason: string) {
    super(
      `cannot take the in-transaction shared read lock on this read: ${reason}. A row lock ` +
        `applies to base rows, so a locked in-transaction read cannot use 'distinct' (nor a ` +
        `grouped / aggregate result). Read it outside the unit of work, or drop 'distinct'.`,
    );
    this.name = "ParallaxUnlockableReadError";
    Object.setPrototypeOf(this, ParallaxUnlockableReadError.prototype);
  }
}

/**
 * A leading `select distinct` projection — the canonical distinct read shape the
 * M3 compiler emits (`0226`: `select distinct t0.…`). The canonical SQL is always
 * lowercase, but the match is case-insensitive so a future dialect's casing cannot
 * slip an unlockable read past the guard.
 */
const DISTINCT_PROJECTION = /^\s*select\s+distinct\b/i;

/**
 * Append the shared read-lock suffix to a compiled read, qualified by the root
 * alias (`t0`) and placed AFTER every other clause. The compiled `sql` is the
 * plain read (`select … where …`); the returned SQL is that read followed by the
 * dialect's lock suffix.
 *
 * A read whose result shape cannot carry a row lock (a `distinct` projection —
 * the one lock-incompatible shape the developer `find` API can produce today) is
 * rejected with {@link ParallaxUnlockableReadError} rather than suffixed into SQL
 * the database would reject. Both `find(pred, { distinct: true })` inside a
 * `locking` transaction (flat and deep-fetch root) funnel through here, so the
 * guard covers every locked read path in one place.
 */
export function appendReadLock(sql: string, alias = "t0"): string {
  if (DISTINCT_PROJECTION.test(sql)) {
    throw new ParallaxUnlockableReadError("the read projects 'distinct'");
  }
  return `${sql} ${readLockSuffix(alias)}`;
}
