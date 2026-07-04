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
import { columnOrder, quoteIdentifier } from "@parallax/dialect";
import { type VersionedTarget, versionAdvancingUpdate } from "@parallax/locking";
import { type EntityMetadata, Metamodel } from "@parallax/operation";
import { type BatchTarget, combineWrites, type PlannedStatement } from "@parallax/transactions";
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
  /**
   * The neutral write input (①): the row(s) the step operates on, as flat
   * attribute-named `{ attr: value }` literals. The non-temporal batched path
   * derives the emitted column list + order + binds from these (classified
   * against the metamodel), so column identity comes from case data, not the
   * golden. Absent on the versioned (`0611`) path until Phase 2.
   */
  readonly rows?: readonly Record<string, unknown>[];
}

/**
 * One flat write row classified by its metamodel role. Every present attribute's
 * value is keyed by its physical column (`columns`, pk + domain); the pk value is
 * split out (`pk` — a written column on `insert`, the `where` key on
 * `update` / `delete`) from the assigned domain columns (`set`). `observedVersion`
 * is the reserved optimistic control key (never a column). Roles come from the
 * metamodel, NEVER from JSON key order.
 */
interface ClassifiedRow {
  readonly columns: ReadonlyMap<string, unknown>;
  readonly pk: unknown;
  readonly set: ReadonlyMap<string, unknown>;
  readonly observedVersion?: number;
}

/**
 * Classify a flat attribute-named row against the entity's metamodel — mirroring
 * the fixture loader (`runner.ts` `loadFixtures`), which resolves attribute-name
 * rows to columns. Each key is either the reserved control key `observedVersion`
 * or an ENTITY ATTRIBUTE name (`attributeByName` throws on anything else, so a
 * typo surfaces loudly); the primary-key attribute's value is split into `pk`,
 * every other attribute into `set`, both keyed by physical column.
 */
function classifyRow(entity: EntityMetadata, row: Record<string, unknown>): ClassifiedRow {
  const pkColumn = entity.primaryKey()[0]?.column;
  const columns = new Map<string, unknown>();
  const set = new Map<string, unknown>();
  let pk: unknown;
  let observedVersion: number | undefined;
  for (const [key, value] of Object.entries(row)) {
    if (key === "observedVersion") {
      observedVersion = value as number;
      continue;
    }
    const attribute = entity.attributeByName(key);
    columns.set(attribute.column, value);
    if (attribute.column === pkColumn) {
      pk = value;
    } else {
      set.set(attribute.column, value);
    }
  }
  return { columns, pk, set, ...(observedVersion === undefined ? {} : { observedVersion }) };
}

/** The entity's physical column list in descriptor order (attribute → column). */
function orderedColumns(entity: EntityMetadata): readonly string[] {
  return columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
  });
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
 * keyed `UPDATE` per distinct key.
 *
 * Column identity + order + binds are DERIVED from the neutral write input (①,
 * `step.rows`) classified against the metamodel — the emitted column list is
 * `columnOrder(entity)` filtered to the present attributes (`0612` omits the
 * nullable `shippedOn`, so `shipped_on` is dropped from the INSERT), never parsed
 * out of the golden. `goldenSql` + `binds` stay an independent oracle the compile
 * lane cross-checks the emission against.
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
  // A VERSIONED entity's keyed update advances its framework-owned version (the
  // locking-mode / `0611` shape) — the readless batched forms below apply only to a
  // non-versioned entity (a versioned set-based update MUST materialize per object,
  // M10 / ADR 0031). Generate it by construction and pin against the golden. (This
  // is the last golden-parsing path in this file; Phase 2 derives it from ① too.)
  if (mutation === "update" && entity.versionAttribute() !== undefined) {
    const stepBinds = bindRows.slice(bindIndex, bindIndex + count);
    return versionedUpdateStatements(entity, stepBinds, golden.slice(bindIndex, bindIndex + count));
  }
  const rows = (step.rows ?? []).map((row) => classifyRow(entity, row));
  const planned =
    mutation === "insert" ? insertStatements(entity, rows) : updateStatements(entity, rows);
  return planned.map((statement: PlannedStatement) => ({
    sql: statement.sql,
    binds: statement.binds,
  }));
}

/**
 * Plan a NON-temporal `insert` step from its classified ① rows: the emitted column
 * list is `columnOrder(entity)` filtered to the columns any row supplies (in model
 * order — an unset nullable attribute is absent, so its column is omitted, `0612`),
 * and the flat binds are each row's values pulled in that same column order. A
 * multi-row insert collapses every row into one statement (`combineWrites`).
 */
function insertStatements(
  entity: EntityMetadata,
  rows: readonly ClassifiedRow[],
): readonly PlannedStatement[] {
  const present = orderedColumns(entity).filter((column) =>
    rows.some((row) => row.columns.has(column)),
  );
  const target: BatchTarget = { ...batchTargetFor(entity), columns: present.map(quoteIdentifier) };
  const flat = rows.flatMap((row) => present.map((column) => row.columns.get(column)));
  return combineWrites([{ mutation: "insert", target, statements: 1, binds: [flat] }]);
}

/**
 * Plan a NON-temporal `update` step from its classified ① rows: the assigned `set`
 * column(s) are `columnOrder(entity)` filtered to the domain columns present (model
 * order, not key order); the pk of each row is the `where` key. Uniform-vs-per-key
 * is decided by value equality across the rows — a shared new value collapses to
 * one `where pk in (…)` statement (`0604`), non-uniform values flush one keyed
 * `UPDATE` per row (`0613`).
 */
function updateStatements(
  entity: EntityMetadata,
  rows: readonly ClassifiedRow[],
): readonly PlannedStatement[] {
  const setColumns = orderedColumns(entity).filter((column) =>
    rows.some((row) => row.set.has(column)),
  );
  const setColumn = setColumns.map(quoteIdentifier).join(", ");
  const target = batchTargetFor(entity);
  const setValues = rows.map((row) => setColumns.map((column) => row.set.get(column)));
  const uniform = setValues.every((values) => tuplesEqual(values, setValues[0] ?? []));
  if (uniform) {
    const flat = [...(setValues[0] ?? []), ...rows.map((row) => row.pk)];
    return combineWrites([{ mutation: "update", target, setColumn, statements: 1, binds: [flat] }]);
  }
  const binds = rows.map((row, index) => [...(setValues[index] ?? []), row.pk]);
  return combineWrites([
    { mutation: "update", target, setColumn, statements: binds.length, binds },
  ]);
}

/** Element-wise scalar equality over two ordered value tuples. */
function tuplesEqual(left: readonly unknown[], right: readonly unknown[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
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

/** The ordered `goldenSql.postgres` statements a write-sequence case declares. */
function goldenStatements(loaded: LoadedCase): readonly string[] {
  const golden = (loaded.raw.goldenSql as { postgres?: string | string[] } | undefined)?.postgres;
  if (golden === undefined) {
    return [];
  }
  return Array.isArray(golden) ? golden : [golden];
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

/**
 * Resolve an entity's physical {@link WriteTarget} (table, columns, pk, out_z,
 * in_z). Shared by the write-sequence chaining generator and the conflict-plan
 * temporal gated-close re-derivation (`conflict.ts`), so both derive the close text
 * from ONE resolver (no drift). `fromColumn` (`in_z`) is the derived optimistic gate
 * an OPTIMISTIC-mode close binds the observed value on (M10).
 */
export function writeTargetFor(entity: EntityMetadata): WriteTarget {
  const columns = columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
  }).map(quoteIdentifier);
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a write sequence`);
  }
  // The processing axis's `toColumn` (`out_z`) the close UPDATE sets + keys on, and
  // its `fromColumn` (`in_z`) the optimistic gate. Absent for a non-temporal entity
  // (only `insert` is legal there).
  const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
  return {
    table: quoteIdentifier(entity.table),
    columns,
    pkColumn: quoteIdentifier(pk.column),
    ...(processing === undefined
      ? {}
      : {
          toColumn: quoteIdentifier(processing.toColumn),
          fromColumn: quoteIdentifier(processing.fromColumn),
        }),
  };
}
