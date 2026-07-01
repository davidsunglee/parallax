/**
 * M10 version-column optimistic locking — the versioned `UPDATE` and its conflict
 * signal.
 *
 * Every update to an optimistically-locked entity (a) GATES on the version the
 * caller read earlier and (b) ADVANCES the version in the same statement:
 *
 *   update <table> set [<col> = ?, ] version = ? where <pk> = ? and version = ?
 *
 * The `... and version = ?` gate is the whole mechanism: if a concurrent
 * transaction advanced the row's version since the caller read it, the stale gate
 * matches ZERO rows and the `UPDATE` affects none — the `updatedRows != 1`
 * conflict signal (`m10-optimistic-locking.md`). A fresh version matches exactly
 * ONE row (success) and the advance moves the gate forward so the next writer's
 * check stays meaningful. The version is written on EVERY update even when no
 * domain column changed (the `0707` version-only bump), otherwise a no-domain
 * write would leave the gate where the next writer last saw it.
 *
 * This module owns only the canonical `?`-placeholder statement TEXT (a pure
 * function of the physical shape); the caller threads the authored binds
 * (`[…set values…, newVersion, pk, expectedVersion]`) and reads the affected-row
 * count to classify the outcome via {@link classifyOutcome}.
 */

/** The physical shape a versioned update targets, resolved from the metamodel. */
export interface VersionedTarget {
  /** The (quoted-as-needed) physical table name. */
  readonly table: string;
  /** The quoted primary-key column the `where` gates on. */
  readonly pkColumn: string;
  /** The quoted optimistic-locking version column (set + gated on). */
  readonly versionColumn: string;
}

/** The classified outcome of a versioned update by its affected-row count. */
export type OptimisticOutcome = "success" | "conflict";

/**
 * Render a versioned `UPDATE`. `setColumns` are the quoted DOMAIN columns the
 * update writes (empty for the `0707` version-only bump); the version column is
 * always appended to the `set` clause and the `where` always gates on `pk` AND
 * the (old) version. Binds order (caller-supplied): the domain set values, then
 * the new version, then the pk, then the expected (old) version.
 */
export function versionedUpdate(target: VersionedTarget, setColumns: readonly string[]): string {
  const assignments = [
    ...setColumns.map((column) => `${column} = ?`),
    `${target.versionColumn} = ?`,
  ];
  return (
    `update ${target.table} set ${assignments.join(", ")} ` +
    `where ${target.pkColumn} = ? and ${target.versionColumn} = ?`
  );
}

/**
 * Classify a versioned update's outcome from its affected-row count: exactly one
 * row is `success`; zero rows is a `conflict` (the stale-version gate matched
 * nothing). Any other count is a data error (a versioned update is keyed on the
 * primary key, so it can never touch more than one row).
 */
export function classifyOutcome(affectedRows: number): OptimisticOutcome {
  if (affectedRows === 1) {
    return "success";
  }
  if (affectedRows === 0) {
    return "conflict";
  }
  throw new Error(
    `a versioned UPDATE affected ${affectedRows} rows; a pk-keyed optimistic update affects 0 (conflict) or 1 (success)`,
  );
}
