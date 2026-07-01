/**
 * M8 buffered-write batching — the set-based DML the unit of work flushes.
 *
 * At the unit-of-work boundary buffered writes are combined and flushed as
 * SET-BASED SQL, not one statement per row (`m8-transactions-cache.md`). This
 * module owns only the canonical `?`-placeholder DML **text** each batched form
 * emits; the caller (the M12 runner) resolves the physical table + columns from
 * the metamodel and threads the authored per-statement binds. Keeping the text a
 * pure function of the physical shape mirrors the audit-write generator in
 * `@parallax/bitemporal`.
 *
 * The three non-temporal batched forms the slice exercises:
 *
 *  | form                    | statements | shape                                      |
 *  |-------------------------|------------|--------------------------------------------|
 *  | multi-row insert (0604) | 1          | `insert into t(cols) values (…), (…), (…)` |
 *  | uniform update  (0604)  | 1          | `update t set col = ? where pk in (?, …)`  |
 *  | per-key update  (0613)  | k          | one `update t set col = ? where pk = ?` ×k |
 *
 * FK-insert ordering (0612) is a UNIT-OF-WORK concern (which entity's inserts run
 * first), so it lives in {@link ./uow.js}; each individual insert is a single-row
 * insert this module renders.
 */

/** The physical shape a batched write targets, resolved from the metamodel. */
export interface BatchTarget {
  /** The (quoted-as-needed) physical table name. */
  readonly table: string;
  /** The ordered physical column names for an `insert` (descriptor order, quoted). */
  readonly columns: readonly string[];
  /** The primary-key column a batched/keyed `update` keys on (quoted). */
  readonly pkColumn: string;
}

/** A generated batched DML statement: canonical `?`-placeholder SQL text. */
export type BatchStatement = string;

/**
 * Render a multi-row `insert` that collapses `rowCount` buffered inserts into one
 * statement (`insert into t(cols) values (?, …), (?, …), …`). A `rowCount` of 1
 * is the ordinary single-row insert (an FK-ordered insert step, `0612`).
 */
export function multiRowInsert(target: BatchTarget, rowCount: number): BatchStatement {
  if (rowCount < 1) {
    throw new Error("multiRowInsert requires at least one row");
  }
  const cols = target.columns.join(", ");
  const tuple = `(${target.columns.map(() => "?").join(", ")})`;
  const values = Array.from({ length: rowCount }, () => tuple).join(", ");
  return `insert into ${target.table}(${cols}) values ${values}`;
}

/**
 * Render a uniform batched `update` over `keyCount` keys that share one new value
 * (`update t set <col> = ? where <pk> in (?, …)`). One statement — the `0604`
 * form. The set column is passed unquoted-as-column-name so the caller quotes it
 * consistently with the metamodel.
 */
export function uniformUpdate(
  target: BatchTarget,
  setColumn: string,
  keyCount: number,
): BatchStatement {
  if (keyCount < 1) {
    throw new Error("uniformUpdate requires at least one key");
  }
  const placeholders = Array.from({ length: keyCount }, () => "?").join(", ");
  return `update ${target.table} set ${setColumn} = ? where ${target.pkColumn} in (${placeholders})`;
}

/**
 * Render ONE keyed `update` for a single distinct key that takes its OWN new
 * value (`update t set <col> = ? where <pk> = ?`). The `0613` per-key form emits
 * one of these per distinct key (the caller repeats it `k` times, pairing each
 * with its own bind row) — the non-uniform complement of {@link uniformUpdate}.
 */
export function keyedUpdate(target: BatchTarget, setColumn: string): BatchStatement {
  return `update ${target.table} set ${setColumn} = ? where ${target.pkColumn} = ?`;
}
