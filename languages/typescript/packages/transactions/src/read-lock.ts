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
 * Append the shared read-lock suffix to a compiled read, qualified by the root
 * alias (`t0`) and placed AFTER every other clause. The compiled `sql` is the
 * plain read (`select … where …`); the returned SQL is that read followed by the
 * dialect's lock suffix.
 */
export function appendReadLock(sql: string, alias = "t0"): string {
  return `${sql} ${readLockSuffix(alias)}`;
}
