/**
 * Build an executable **write-sequence plan** from a loaded case (M7 + M12).
 *
 * A `writeSequence` case carries an ordered list of milestone-chaining mutations
 * (`insert` / `update` / `terminate` for the audit-only MVP surface) plus the
 * per-statement `binds` and an `expectedTableState`. This module turns the steps
 * into the ordered canonical DML the runner applies:
 *
 *  - each step's SQL text is generated from the entity's physical shape by
 *    `@parallax/bitemporal` (`auditWriteStatements`) — the milestone-chaining
 *    discipline (open a current row; close the current row keyed by `pk and
 *    out_z = infinity`; chain a new current row) is owned there, never authored
 *    per-case; and
 *  - each generated statement is paired, in order, with the authored bind row —
 *    the write input (the milestone values) the case declares.
 *
 * The statement count equals the sum of the steps' declared counts (insert 1,
 * update 2, terminate 1), which the harness asserts equals `roundTrips`. A
 * **non-temporal** entity's `insert` (`0004` / `0005`, the timestamp-shape cases)
 * reuses the same generator as a plain single-row insert.
 */
import { auditWriteStatements, type MutationKind, type WriteTarget } from "@parallax/bitemporal";
import { type EntityMetadata, Metamodel } from "@parallax/operation";
import { columnOrder, quoteIdentifier } from "@parallax/sql";
import type { LoadedCase } from "./discover.js";

/** One generated DML statement paired with its authored binds + case pointer. */
export interface WriteStatementPlan {
  /** The JSON Pointer into the case (`/writeSequence/<stepIndex>`). */
  readonly casePointer: string;
  /** The canonical `?`-placeholder DML text. */
  readonly sql: string;
  /** The authored bind row for this statement (in statement order). */
  readonly binds: readonly unknown[];
}

/** The executable write-sequence plan: the ordered DML statements to apply. */
export interface WriteSequencePlan {
  readonly statements: readonly WriteStatementPlan[];
}

/** A raw `writeSequence` step (the mutation kind + target entity). */
interface WriteStep {
  readonly mutation: MutationKind;
  readonly entity: string;
  readonly statements?: number;
}

/** True when a case's shape is a write sequence. */
export function isWriteSequence(loaded: LoadedCase): boolean {
  return loaded.shape === "writeSequence";
}

/**
 * Build the ordered DML plan: for each step, generate its statement texts from the
 * entity's write target and pair them, in order, with the case's per-statement
 * binds. The authored `binds` array has one entry per generated statement (an
 * update step consumes two: the close row and the chained-insert row).
 */
export function buildWriteSequencePlan(loaded: LoadedCase): WriteSequencePlan {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const steps = (loaded.raw.writeSequence as readonly WriteStep[] | undefined) ?? [];
  const bindRows = (loaded.raw.binds as readonly (readonly unknown[])[] | undefined) ?? [];

  const statements: WriteStatementPlan[] = [];
  let bindIndex = 0;
  steps.forEach((step, stepIndex) => {
    const target = writeTargetFor(metamodel.entity(step.entity));
    const texts = auditWriteStatements(step.mutation, target);
    for (const sql of texts) {
      statements.push({
        casePointer: `/writeSequence/${stepIndex}`,
        sql,
        binds: bindRows[bindIndex] ?? [],
      });
      bindIndex += 1;
    }
  });
  return { statements };
}

/** Resolve an entity's physical {@link WriteTarget} (table, columns, pk, out_z). */
function writeTargetFor(entity: EntityMetadata): WriteTarget {
  const columns = columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
  }).map(quoteIdentifier);
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a write sequence`);
  }
  // The processing axis's `toColumn` (`out_z`) the close UPDATE sets + keys on.
  // Absent for a non-temporal entity (only `insert` is legal there).
  const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
  return {
    table: quoteIdentifier(entity.table),
    columns,
    pkColumn: quoteIdentifier(pk.column),
    ...(processing === undefined ? {} : { toColumn: quoteIdentifier(processing.toColumn) }),
  };
}

/** Read a table's full state, projecting every column in descriptor order. */
export function tableColumnsInOrder(entity: EntityMetadata): readonly string[] {
  return columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
  });
}
