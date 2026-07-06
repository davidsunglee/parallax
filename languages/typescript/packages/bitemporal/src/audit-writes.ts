/**
 * M7 milestone-chaining writes (audit-only) — the DML statement generation for the
 * `insert` / `update` / `terminate` mutation surface (the MVP mutation surface;
 * the `*Until` rectangle-split trio is out of V1).
 *
 * A write to an audit-only temporal entity **chains milestone rows** rather than
 * mutating in place — that is what produces the audit trail. In audit-only mode
 * the processing axis has no business-date residual, so the chaining is the simple
 * close-and-open form (m7-temporal.md §"Milestone-chaining writes"):
 *
 *  | mutation  | statements                                                        |
 *  |-----------|-------------------------------------------------------------------|
 *  | insert    | open one current row: `insert … (in_z=tx, out_z=∞)`               |
 *  | update    | close the current row (`update … set out_z=? where pk and out_z=?`)|
 *  |           | then chain a new current row (`insert … (in_z=tx, out_z=∞)`)       |
 *  | terminate | close the current row only (no insert — the terminated state is    |
 *  |           | the *absence* of any `out_z=∞` row)                               |
 *
 * The close `UPDATE` is **keyed by the current-row predicate** (`pk and
 * out_z = infinity`), never a blind in-place set. This module owns only the SQL
 * **text** (canonical, `?`-placeholder): the caller (M12 runner) resolves the
 * physical write target from the metamodel and threads the per-statement binds
 * (the authored milestone values) the case declares — the DML text is a pure
 * function of the entity's physical shape, not the bind values.
 *
 * A **non-temporal** entity's `insert` lowers to the same plain
 * `insert into <table>(<cols>) values (?, …)` (no `out_z` axis to close), so the
 * timestamp-shape write cases (`m-core-002` / `m-core-003`) reuse this generator.
 */

/** The physical write target the DML generation needs, resolved from the metamodel. */
export interface WriteTarget {
  /** The (quoted-as-needed) physical table name. */
  readonly table: string;
  /** The ordered physical column names for an `insert` (descriptor order, quoted). */
  readonly columns: readonly string[];
  /** The primary-key column the close `UPDATE` keys on (quoted). */
  readonly pkColumn: string;
  /**
   * The processing axis's `toColumn` (`out_z`) the close `UPDATE` sets + keys on
   * (quoted). Absent for a non-temporal entity (only `insert` is legal there).
   */
  readonly toColumn?: string;
  /**
   * The processing axis's `fromColumn` (`in_z`) — the DERIVED optimistic key (M10):
   * an OPTIMISTIC-mode close gates on the `in_z` the unit of work observed, since a
   * temporal entity carries no version column and the observed processing-from is
   * the version analogue. Present only for a gated (optimistic) close.
   */
  readonly fromColumn?: string;
}

/** A generated DML statement: canonical `?`-placeholder SQL text. */
export type WriteStatement = string;

/** The MVP audit-only mutation kinds. */
export type MutationKind = "insert" | "update" | "terminate";

/** Options for {@link auditWriteStatements}. */
export interface AuditWriteOptions {
  /**
   * Emit the OPTIMISTIC-mode gated close (`… and <in_z> = ?`) rather than the plain
   * close (M10). A gated close binds the observed processing-from as the version
   * analogue, so a concurrent writer that superseded the milestone matches 0 rows
   * (the conflict signal). Requires {@link WriteTarget.fromColumn}. Default `false`
   * (the plain close, used in locking mode — no drift with {@link closeStatement}).
   */
  readonly gated?: boolean;
}

/**
 * Generate the ordered DML statement texts for one milestone-chaining mutation.
 * The number of statements matches the mutation's declared step count (insert 1,
 * update 2, terminate 1); the caller pairs each with the authored bind row.
 *
 * In OPTIMISTIC mode (`options.gated`) the close/terminate `UPDATE` gains the
 * `… and <in_z> = ?` optimistic gate on the observed processing-from (M10); the
 * plain close stays for locking mode (no drift).
 */
export function auditWriteStatements(
  kind: MutationKind,
  target: WriteTarget,
  options: AuditWriteOptions = {},
): WriteStatement[] {
  // Resolve the close LAZILY — only `update`/`terminate` close a milestone, so a
  // non-temporal `insert` (`m-core-002`/`m-core-003`, no processing axis) never demands one.
  const close = (): WriteStatement =>
    options.gated ? gatedCloseStatement(target) : closeStatement(target);
  switch (kind) {
    case "insert":
      return [insertStatement(target)];
    case "update":
      // Close the current row, then chain a new current milestone.
      return [close(), insertStatement(target)];
    case "terminate":
      // Close the current row and insert nothing.
      return [close()];
  }
}

/** `insert into <table>(<cols>) values (?, …)` — open a milestone row. */
function insertStatement(target: WriteTarget): WriteStatement {
  const cols = target.columns.join(", ");
  const placeholders = target.columns.map(() => "?").join(", ");
  return `insert into ${target.table}(${cols}) values (${placeholders})`;
}

/**
 * `update <table> set out_z = ? where <pk> = ? and out_z = ?` — close the current
 * row, keyed by the current-row predicate (`pk and out_z = infinity`), so only the
 * open milestone is closed (never a blind in-place set).
 */
function closeStatement(target: WriteTarget): WriteStatement {
  if (target.toColumn === undefined) {
    throw new Error(
      "audit close/terminate requires a processing toColumn; the entity is non-temporal",
    );
  }
  return `update ${target.table} set ${target.toColumn} = ? where ${target.pkColumn} = ? and ${target.toColumn} = ?`;
}

/**
 * `update <table> set out_z = ? where <pk> = ? and out_z = ? and <in_z> = ?` — the
 * OPTIMISTIC-mode gated close (M10). Like {@link closeStatement} but with the
 * `… and <in_z> = ?` gate on the observed processing-from (the version analogue for
 * a temporal entity, which carries no version column). The gate shape mirrors
 * `@parallax/locking`'s `versionedUpdate` `… and <version> = ?`: a concurrent writer
 * that superseded the milestone leaves a fresh `in_z`, so the stale gate matches
 * ZERO rows — the `updatedRows != 1` conflict signal.
 */
function gatedCloseStatement(target: WriteTarget): WriteStatement {
  if (target.toColumn === undefined) {
    throw new Error(
      "audit close/terminate requires a processing toColumn; the entity is non-temporal",
    );
  }
  if (target.fromColumn === undefined) {
    throw new Error(
      "a gated (optimistic) audit close requires a processing fromColumn (the in_z gate)",
    );
  }
  return (
    `update ${target.table} set ${target.toColumn} = ? ` +
    `where ${target.pkColumn} = ? and ${target.toColumn} = ? and ${target.fromColumn} = ?`
  );
}
