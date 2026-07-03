/**
 * Build an executable **write-sequence plan** from a loaded case (M7 + M8 + M12).
 *
 * A `writeSequence` case carries an ordered list of mutations plus per-statement
 * `binds` and an `expectedTableState`. This module turns the steps into the
 * ordered canonical DML the runner applies, choosing the discipline by the
 * entity's temporality:
 *
 *  - a **temporal** (audit-only) entity's step is milestone-chaining DML generated
 *    by `@parallax/bitemporal` (`auditWriteStatements`) — open a current row; close
 *    the current row keyed by `pk and out_z = infinity`; chain a new current row;
 *  - a **non-temporal** entity's step is the M8 set-based batched flush generated
 *    by `@parallax/transactions`'s unit-of-work planner
 *    (`combineWrites`) — buffered inserts collapse into one multi-row `INSERT`
 *    (`0604`/`0612`), and a batched update is uniform `pk in (…)` (`0604`) or one
 *    keyed `UPDATE` per distinct key (`0613`, `statements: 2`).
 *
 * Each generated statement is paired, in order, with the authored bind row — the
 * write input the case declares. The statement count equals the sum of the steps'
 * declared counts, which the harness asserts equals `roundTrips`. The `0004` /
 * `0005` timestamp-shape single-row inserts fall out of the non-temporal `insert`
 * path (a one-row multi-row insert).
 */
import { auditWriteStatements, type MutationKind, type WriteTarget } from "@parallax/bitemporal";
import { type VersionedTarget, versionAdvancingUpdate } from "@parallax/locking";
import { type EntityMetadata, Metamodel } from "@parallax/operation";
import { columnOrder, quoteIdentifier } from "@parallax/sql";
import {
  type BatchTarget,
  combineWrites,
  type PlannedStatement,
  type WriteStep as UowStep,
} from "@parallax/transactions";
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
interface RawWriteStep {
  readonly mutation: MutationKind;
  readonly entity: string;
  readonly statements?: number;
}

/** True when a case's shape is a write sequence. */
export function isWriteSequence(loaded: LoadedCase): boolean {
  return loaded.shape === "writeSequence";
}

/**
 * Build the ordered DML plan: for each step, generate its statement texts and pair
 * them, in order, with the case's per-statement binds. The `binds` array has one
 * entry per generated statement, consumed statement-by-statement across the whole
 * sequence (a temporal `update` step consumes two — close + chained insert; a
 * per-key batched update step consumes one per key).
 *
 * The generator is chosen per step by the entity's temporality: an **audit-only
 * temporal** entity chains milestones (`@parallax/bitemporal`), a **non-temporal**
 * entity flushes the M8 set-based batched forms (`@parallax/transactions`'s
 * unit-of-work planner). The two never mix within a step.
 */
export function buildWriteSequencePlan(loaded: LoadedCase): WriteSequencePlan {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const steps = (loaded.raw.writeSequence as readonly RawWriteStep[] | undefined) ?? [];
  const bindRows = (loaded.raw.binds as readonly (readonly unknown[])[] | undefined) ?? [];
  const golden = goldenStatements(loaded);

  const statements: WriteStatementPlan[] = [];
  let bindIndex = 0;
  steps.forEach((step, stepIndex) => {
    const entity = metamodel.entity(step.entity);
    const generated = isTemporalEntity(entity)
      ? auditStatementsForStep(step, entity, bindRows, bindIndex)
      : batchStatementsForStep(step, entity, bindRows, bindIndex, golden);
    for (const { sql, binds } of generated) {
      statements.push({ casePointer: `/writeSequence/${stepIndex}`, sql, binds });
      bindIndex += 1;
    }
  });
  return { statements };
}

/** True when the entity carries a processing axis (audit-only milestone chaining). */
function isTemporalEntity(entity: EntityMetadata): boolean {
  return entity.asOfAttributes().some((axis) => axis.axis === "processing");
}

/**
 * The generated milestone-chaining statements for one TEMPORAL step (audit-only),
 * each paired, in order, with the authored bind row (`insert` consumes one,
 * `update` two — close + chained insert, `terminate` one).
 */
function auditStatementsForStep(
  step: RawWriteStep,
  entity: EntityMetadata,
  bindRows: readonly (readonly unknown[])[],
  bindIndex: number,
): readonly { sql: string; binds: readonly unknown[] }[] {
  const texts = auditWriteStatements(step.mutation, writeTargetFor(entity));
  return texts.map((sql, offset) => ({ sql, binds: bindRows[bindIndex + offset] ?? [] }));
}

/**
 * The generated DML statements for one NON-temporal step, via the M8 unit-of-work
 * planner (`combineWrites`): an `insert` collapses its buffered rows into one
 * multi-row `INSERT`, an `update` is uniform `pk in (…)` (one statement) or one
 * keyed `UPDATE` per distinct key (`statements: 2`). The step's own bind rows are
 * the slice `[bindIndex, bindIndex + statements)` of the case's `binds`.
 *
 * Two per-case authoring choices the model alone cannot determine are taken from
 * the step's golden statement (the authoritative intent): (a) an `insert`'s
 * COLUMN LIST — a nullable column may be omitted (`0612` inserts `order_item(id,
 * order_id, sku, quantity)`, dropping the nullable `shipped_on`) — so the target's
 * columns come from the golden `insert into t(<cols>)`; and (b) an `update`'s SET
 * column, from the golden `set <col> = …`. Everything else (the batched form, the
 * `pk in (…)` vs per-key shape) is generated by construction.
 */
function batchStatementsForStep(
  step: RawWriteStep,
  entity: EntityMetadata,
  bindRows: readonly (readonly unknown[])[],
  bindIndex: number,
  golden: readonly string[],
): readonly { sql: string; binds: readonly unknown[] }[] {
  const mutation = step.mutation === "insert" ? "insert" : "update";
  const count = step.statements ?? 1;
  const stepBinds = bindRows.slice(bindIndex, bindIndex + count);
  // A VERSIONED entity's keyed update advances its framework-owned version (the
  // locking-mode / `0611` shape) — the readless batched forms below apply only to a
  // non-versioned entity (a versioned set-based update MUST materialize per object,
  // M10 / ADR 0031). Generate it by construction and pin against the golden.
  if (mutation === "update" && entity.versionAttribute() !== undefined) {
    return versionedUpdateStatements(entity, stepBinds, golden.slice(bindIndex, bindIndex + count));
  }
  const uowStep: UowStep = {
    mutation,
    target:
      mutation === "insert"
        ? insertTargetFromGolden(entity, golden[bindIndex])
        : batchTargetFor(entity),
    statements: count,
    binds: stepBinds,
    ...(mutation === "update" ? { setColumn: setColumnFromGolden(golden[bindIndex]) } : {}),
  };
  return combineWrites([uowStep]).map((planned: PlannedStatement) => ({
    sql: planned.sql,
    binds: planned.binds,
  }));
}

/**
 * The generated locking-mode version-advancing `UPDATE`(s) for a VERSIONED entity
 * (`0611`): each keyed update advances the framework-owned version WITHOUT a gate
 * (the M8 shared read lock makes it correct — `@parallax/locking`
 * `versionAdvancingUpdate`). The domain `set` columns are parsed from each golden
 * (its authored intent, minus the trailing `version = ?`) and the generated text is
 * pinned equal to the golden, so the runtime — not the case — owns the DML shape.
 */
function versionedUpdateStatements(
  entity: EntityMetadata,
  stepBinds: readonly (readonly unknown[])[],
  golden: readonly string[],
): readonly { sql: string; binds: readonly unknown[] }[] {
  const target = versionedTargetFor(entity);
  return stepBinds.map((binds, offset) => {
    const goldenSql = golden[offset];
    const sql = versionAdvancingUpdate(target, domainSetColumns(goldenSql, target));
    if (sql !== goldenSql) {
      throw new Error(
        `generated version-advancing UPDATE != golden:\n  generated: ${sql}\n  golden:    ${goldenSql ?? "<absent>"}`,
      );
    }
    return { sql, binds };
  });
}

/** Resolve a versioned entity's {@link VersionedTarget} (table, pk, version column). */
function versionedTargetFor(entity: EntityMetadata): VersionedTarget {
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a versioned update`);
  }
  const version = entity.versionAttribute();
  if (version === undefined) {
    throw new Error(`entity '${entity.name}' has no optimistic-locking version column`);
  }
  return {
    table: quoteIdentifier(entity.table),
    pkColumn: quoteIdentifier(pk.column),
    versionColumn: quoteIdentifier(version.column),
  };
}

/**
 * The quoted DOMAIN `set` columns of a golden version-advancing UPDATE (the `set`
 * list minus the trailing `version = ?`): `update account set balance = ?, version
 * = ? where id = ?` → `["balance"]`. The columns are taken from the golden so the
 * generated UPDATE reproduces it exactly.
 */
function domainSetColumns(golden: string | undefined, target: VersionedTarget): readonly string[] {
  const match = golden ? /\bset\s+(.+?)\s+where\b/i.exec(golden) : null;
  if (!match) {
    throw new Error(`could not parse the set clause from golden UPDATE: ${golden ?? "<absent>"}`);
  }
  return (match[1] as string)
    .split(",")
    .map((piece) => piece.trim().split(/\s*=/)[0]?.trim() ?? "")
    .filter((column) => column !== target.versionColumn);
}

/**
 * Build the {@link BatchTarget} for an `insert` from the entity plus the golden
 * INSERT's column list (a nullable column the case omits is dropped, so the
 * generated statement reproduces the golden). The columns are taken verbatim from
 * `insert into t(<cols>)`; the pk column is resolved from the metamodel.
 */
function insertTargetFromGolden(entity: EntityMetadata, golden: string | undefined): BatchTarget {
  const base = batchTargetFor(entity);
  const match = golden ? /\binsert\s+into\s+\S+\s*\(([^)]*)\)/i.exec(golden) : null;
  if (!match) {
    throw new Error(`could not parse the insert column list from golden: ${golden ?? "<absent>"}`);
  }
  const columns = (match[1] as string).split(",").map((column) => column.trim());
  return { ...base, columns };
}

/** The ordered `goldenSql.postgres` statements a write-sequence case declares. */
function goldenStatements(loaded: LoadedCase): readonly string[] {
  const golden = (loaded.raw.goldenSql as { postgres?: string | string[] } | undefined)?.postgres;
  if (golden === undefined) {
    return [];
  }
  return Array.isArray(golden) ? golden : [golden];
}

/** The quoted `set` column named by a golden `update … set <col> = …` statement. */
function setColumnFromGolden(golden: string | undefined): string {
  const match = golden ? /\bset\s+([^\s=]+)\s*=/i.exec(golden) : null;
  if (!match) {
    throw new Error(`could not resolve the set column from golden UPDATE: ${golden ?? "<absent>"}`);
  }
  return match[1] as string;
}

/** Resolve an entity's physical {@link BatchTarget} (table, quoted columns, pk). */
function batchTargetFor(entity: EntityMetadata): BatchTarget {
  const columns = columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
  }).map(quoteIdentifier);
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a batched write`);
  }
  return { table: quoteIdentifier(entity.table), columns, pkColumn: quoteIdentifier(pk.column) };
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
