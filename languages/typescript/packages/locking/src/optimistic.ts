/**
 * m-opt-lock version-column optimistic locking — the versioned `UPDATE` and its conflict
 * signal.
 *
 * An update to an optimistically-locked entity ALWAYS advances the version, and —
 * in OPTIMISTIC mode — also gates on the version the unit of work observed:
 *
 *   update <table> set [<col> = ?, ] version = ? where <pk> = ? and version = ?   (optimistic)
 *   update <table> set [<col> = ?, ] version = ? where <pk> = ?                   (locking)
 *
 * The `... and version = ?` gate (optimistic mode) is the whole conflict
 * mechanism: if a concurrent transaction advanced the row's version since the
 * unit of work observed it, the stale gate matches ZERO rows and the `UPDATE`
 * affects none — the `updatedRows != 1` conflict signal
 * (`m-opt-lock.md`). A fresh version matches exactly ONE row
 * (success) and the advance moves the gate forward so the next writer's check
 * stays meaningful. In LOCKING mode the m-read-lock shared read lock makes the write
 * correct, so the version advances WITHOUT a gate ({@link versionAdvancingUpdate},
 * the `m-detach-002` / detached-merge-back shape). A versioned update that changes no
 * domain column issues no DML at all (the version is framework-owned, not bumped
 * for nothing).
 *
 * This module owns only the canonical `?`-placeholder statement TEXT (a pure
 * function of the physical shape); the caller threads the authored binds
 * (optimistic: `[…set values…, newVersion, pk, observedVersion]`; locking:
 * `[…set values…, newVersion, pk]`) and reads the affected-row count to classify
 * the outcome via {@link classifyOutcome}.
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
 * Render the OPTIMISTIC-mode versioned `UPDATE`. `setColumns` are the quoted
 * DOMAIN columns the update writes; the version column is always appended to the
 * `set` clause and the `where` always gates on `pk` AND the observed version.
 * Binds order (caller-supplied): the domain set values, then the new version, then
 * the pk, then the observed version. (A no-op update — no domain columns — issues
 * no DML, m-opt-lock, so this is never called with an empty `setColumns`.)
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
 * Render the LOCKING-mode versioned `UPDATE`: like {@link versionedUpdate} but
 * WITHOUT the `and <version> = ?` gate — the version still advances in the `set`,
 * but the `m-read-lock` shared read lock (not the version) makes the write correct (the
 * `m-detach-002` / detached-merge-back / `m-opt-lock-002` shape). Binds order (caller-supplied): the
 * domain set values, then the new version, then the pk.
 */
export function versionAdvancingUpdate(
  target: VersionedTarget,
  setColumns: readonly string[],
): string {
  const assignments = [
    ...setColumns.map((column) => `${column} = ?`),
    `${target.versionColumn} = ?`,
  ];
  return `update ${target.table} set ${assignments.join(", ")} where ${target.pkColumn} = ?`;
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
