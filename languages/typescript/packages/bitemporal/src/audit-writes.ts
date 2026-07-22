/**
 * m-audit-write / m-bitemp-write milestone-chaining writes — the DML statement
 * generation for the `insert` / `update` / `terminate` audit-only surface AND the
 * full-bitemporal `insertUntil` / `updateUntil` / `terminateUntil` rectangle-split
 * trio (COR-26 promoted `m-bitemp-write` into `slice-mvp-1`).
 *
 * A write to an audit-only temporal entity **chains milestone rows** rather than
 * mutating in place — that is what produces the audit trail. In audit-only mode
 * Transaction-Time-Only has no Valid-Time residual, so chaining is the simple
 * close-and-open form (m-audit-write.md §"Milestone-chaining writes"):
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
 * **text** (canonical, `?`-placeholder): the caller (m-case-format runner) resolves the
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
   * The Transaction-Time end column (`out_z`) the close `UPDATE` sets + keys on
   * (quoted). Absent for a non-temporal entity (only `insert` is legal there).
   */
  readonly txEndColumn?: string;
  /**
   * The Transaction-Time start column (`in_z`) — the derived optimistic key (m-opt-lock):
   * an OPTIMISTIC-mode close gates on the `in_z` the unit of work observed, since a
   * temporal entity carries no version column and the observed Transaction-Time start is
   * the version analogue. Present only for a gated (optimistic) close.
   */
  readonly txStartColumn?: string;
  /**
   * The Valid-Time start column (`from_z`) — the bitemporal rectangle
   * discriminator (m-bitemp-write). A gated (optimistic) close on a Bitemporal
   * entity targets EXACTLY the observed rectangle, so it adds `and <from_z> = ?`
   * between the `out_z` and `in_z` gates (`m-bitemp-write-004` / `-005` / `-008`).
   * Present only for a bitemporal entity; absent for an audit-only one, whose gated
   * close is `… and out_z = ? and in_z = ?` (no Valid-Time dimension).
   */
  readonly validStartColumn?: string;
}

/** A generated DML statement: canonical `?`-placeholder SQL text. */
export type WriteStatement = string;

/**
 * The milestone-chaining mutation kinds: the audit-only `insert` / `update` /
 * `terminate` surface plus the full-bitemporal `*Until` rectangle-split trio, which
 * bound a mutation to a Valid-Time window (m-bitemp-write).
 */
export type MutationKind =
  | "insert"
  | "update"
  | "terminate"
  | "insertUntil"
  | "updateUntil"
  | "terminateUntil";

/** Options for {@link auditWriteStatements}. */
export interface AuditWriteOptions {
  /**
   * Emit the OPTIMISTIC-mode gated close (`… and <in_z> = ?`) rather than the plain
   * close (m-opt-lock). A gated close binds the observed Transaction-Time start as the version
   * analogue, so a concurrent writer that superseded the milestone matches 0 rows
   * (the conflict signal). Requires {@link WriteTarget.txStartColumn}. Default `false`
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
 * `… and <in_z> = ?` optimistic gate on the observed Transaction-Time start (m-opt-lock); the
 * plain close stays for locking mode (no drift).
 */
export function auditWriteStatements(
  kind: MutationKind,
  target: WriteTarget,
  options: AuditWriteOptions = {},
): WriteStatement[] {
  // Resolve the close LAZILY — only `update`/`terminate`/`*Until` close a milestone,
  // so a non-temporal `insert` (`m-core-002`/`m-core-003`, no Transaction Time) never
  // demands one.
  const close = (): WriteStatement =>
    options.gated ? gatedCloseStatement(target) : closeStatement(target);
  const insert = (): WriteStatement => insertStatement(target);
  switch (kind) {
    case "insert":
    case "insertUntil":
      // Open one milestone: a Transaction-Time-Only insert, or a Valid-Time-bounded insertUntil
      // (`m-bitemp-write-003`, a single INSERT with no prior row to close).
      return [insert()];
    case "update":
      // Audit-only close-and-chain (2): close the current row, chain a new current
      // milestone. A bitemporal PLAIN update's extra head/new-tail split is
      // orchestrated by the write-sequence rectangle-split planner (m-bitemp-write-006).
      return [close(), insert()];
    case "updateUntil":
      // Bitemporal rectangle split (4): inactivate the original in Transaction Time,
      // then chain head / middle / tail (`m-bitemp-write-001` / `-008`).
      return [close(), insert(), insert(), insert()];
    case "terminate":
      // Audit-only close (1): close the current row and insert nothing.
      return [close()];
    case "terminateUntil":
      // Bitemporal rectangle split with NO middle (3): inactivate + head / tail — the
      // value is absent inside the terminated window (`m-bitemp-write-002`).
      return [close(), insert(), insert()];
  }
}

/**
 * A bare, lexically-simple identifier — the shape the dialect quoting seam leaves
 * UNQUOTED (`^[a-z_][a-z0-9_]*$`, m-dialect). A table reference is quoted exactly when
 * it does NOT match this, which is what {@link insertStatement} keys its INSERT
 * column-list spacing on.
 */
const SIMPLE_TABLE_REFERENCE = /^[a-z_][a-z0-9_]*$/;

/**
 * `insert into <table>(<cols>) values (?, …)` — open a milestone row, with the m-sql
 * canonical spacing before the column list. A BARE (simple, unquoted) table name
 * renders TIGHT against its `(` (`insert into position(...)`, Postgres), while a
 * QUOTED / otherwise non-simple table reference takes a single space before `(`
 * (`` insert into `position` (...) ``, MariaDB). This mirrors the m-sql normalizer: a
 * bare name tokenizes as a function-call VAR (no space before its `(`), a quoted name
 * as an IDENTIFIER (a space before `(`). The separator is therefore CONDITIONAL on the
 * table's quoting — never a blanket space, which would corrupt the unquoted-Postgres
 * canonical form the existing goldens pin.
 */
function insertStatement(target: WriteTarget): WriteStatement {
  const cols = target.columns.join(", ");
  const placeholders = target.columns.map(() => "?").join(", ");
  const gap = SIMPLE_TABLE_REFERENCE.test(target.table) ? "" : " ";
  return `insert into ${target.table}${gap}(${cols}) values (${placeholders})`;
}

/**
 * `update <table> set out_z = ? where <pk> = ? and out_z = ?` — close the current
 * row, keyed by the current-row predicate (`pk and out_z = infinity`), so only the
 * open milestone is closed (never a blind in-place set).
 */
function closeStatement(target: WriteTarget): WriteStatement {
  if (target.txEndColumn === undefined) {
    throw new Error(
      "audit close/terminate requires a Transaction-Time end column; the entity is non-temporal",
    );
  }
  return `update ${target.table} set ${target.txEndColumn} = ? where ${target.pkColumn} = ? and ${target.txEndColumn} = ?`;
}

/**
 * The OPTIMISTIC-mode gated close (m-opt-lock). Like {@link closeStatement} but with
 * the `… and <in_z> = ?` gate on the observed Transaction-Time start (the version analogue
 * for a temporal entity, which carries no version column). The gate shape mirrors
 * `@parallax/locking`'s `versionedUpdate` `… and <version> = ?`: a concurrent writer
 * that superseded the milestone leaves a fresh `in_z`, so the stale gate matches
 * ZERO rows — the `updatedRows != 1` conflict signal.
 *
 * On a Bitemporal entity ({@link WriteTarget.validStartColumn} present) the
 * gate additionally carries the Valid-Time discriminator so the close targets exactly
 * the observed rectangle (m-bitemp-write): `… where <pk> = ? and out_z = ? and
 * <from_z> = ? and <in_z> = ?`. A Transaction-Time-Only entity has no Valid Time, so it
 * omits the `and <from_z> = ?` term: `… where <pk> = ? and out_z = ? and <in_z> = ?`.
 */
function gatedCloseStatement(target: WriteTarget): WriteStatement {
  if (target.txEndColumn === undefined) {
    throw new Error(
      "audit close/terminate requires a Transaction-Time end column; the entity is non-temporal",
    );
  }
  if (target.txStartColumn === undefined) {
    throw new Error(
      "a gated (optimistic) audit close requires a Transaction-Time start column (the in_z gate)",
    );
  }
  // A Bitemporal close's Valid-Time discriminator slots between the out_z and in_z gates
  // (model column order: from_z precedes in_z), so the observed rectangle is targeted.
  const validTimeGate =
    target.validStartColumn === undefined ? "" : ` and ${target.validStartColumn} = ?`;
  return (
    `update ${target.table} set ${target.txEndColumn} = ? ` +
    `where ${target.pkColumn} = ? and ${target.txEndColumn} = ?${validTimeGate} and ${target.txStartColumn} = ?`
  );
}
