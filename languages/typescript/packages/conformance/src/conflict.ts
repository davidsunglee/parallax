/**
 * Build an executable **conflict plan** from a loaded case (m-opt-lock optimistic
 * locking + m-case-format).
 *
 * A `conflict` case proves the observable form of optimistic-lock conflict
 * detection: fixtures are loaded (the versioned row exists), an OPTIONAL
 * out-of-band `given.apply` simulates a concurrent writer that advanced the
 * version, then the golden versioned `UPDATE`(s) are applied and the affected-row
 * count is asserted (`updatedRows != 1` is the conflict signal). Two forms:
 *
 *  - a SINGLE attempt (`when.write` + `then.statements` + `then.affectedRows`); and
 *  - an ordered `when.attempts` RETRY sequence (each attempt carries its own
 *    `statements` + `write` + `affectedRows`) — a stale UPDATE affects 0 rows, then
 *    a fresh-version retry affects 1 (`m-opt-lock-007`).
 *
 * The golden `UPDATE` text is authored in the case (`update … set … , version = ?
 * where id = ? and version = ?`). This module DERIVES it — text AND binds — from
 * the neutral write input (① `write`, a flat attribute-named row) classified
 * against the metamodel: the domain `set` columns are `columnOrder(entity)`
 * filtered to the row's assigned attributes, the version advances
 * `observedVersion + 1`, and a conflict is intrinsically gated (`and version = ?`,
 * R4). The derived emission is cross-checked against the authored golden + binds —
 * two INDEPENDENT representations of the write — so `emitted === golden` is a
 * genuine check of column identity: ① now carries the column intent the corpus once
 * held only inside the golden string. A `given.apply` entry is an out-of-band naive
 * statement run VERBATIM (it models a concurrent writer, not our runtime's output).
 */
import { auditWriteStatements } from "@parallax/bitemporal";
import type { Dialect } from "@parallax/dialect";
import { type VersionedTarget, versionedUpdate } from "@parallax/locking";
import { type EntityMetadata, Metamodel } from "@parallax/operation";
import {
  dialectStatements,
  entryBinds,
  goldenEntries,
  type StatementEntry,
} from "./case-format.js";
import { bindsEqual } from "./compare.js";
import type { LoadedCase } from "./discover.js";
import { classifyRow, orderedColumns, writeTargetFor } from "./write-sequence.js";

/** One versioned-UPDATE attempt: its generated SQL, binds, expected affected count. */
export interface ConflictAttempt {
  /** The m-conformance-adapter case pointer (`/then/statements/0` or `/attempts/<i>`). */
  readonly casePointer: string;
  /** The canonical versioned-UPDATE text (generated, pinned against the golden). */
  readonly sql: string;
  /** The authored binds `[…set values…, newVersion, pk, observedVersion]`. */
  readonly binds: readonly unknown[];
  /** The expected affected-row count (`1` success, `0` conflict). */
  readonly affectedRows: number;
}

/** One out-of-band `given.apply` statement (a concurrent writer) run verbatim. */
export interface ApplyStatement {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/** The executable conflict plan: the `given.apply` setup + the ordered attempts. */
export interface ConflictPlan {
  readonly apply: readonly ApplyStatement[];
  readonly attempts: readonly ConflictAttempt[];
}

/** True when a case's shape is a conflict (optimistic-lock) case. */
export function isConflict(loaded: LoadedCase): boolean {
  return loaded.shape === "conflict";
}

/**
 * Build the conflict plan: resolve the `given.apply` statements (each carrying its
 * own inline binds), then the ordered attempts — one for the single form, or the
 * declared list for the retry form. Each attempt's UPDATE + binds are DERIVED (a
 * versioned conflict from its ① `write`; a temporal close from the metamodel), then
 * cross-checked against the authored golden + binds — a genuine independent check,
 * failing loudly if ① and the golden disagree.
 */
export function buildConflictPlan(loaded: LoadedCase, dialect: Dialect): ConflictPlan {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const entity = conflictEntity(metamodel);
  const deriveStatement = conflictSqlDeriver(entity, loaded, dialect);

  const attempts = normalizedAttempts(loaded, dialect).map((attempt) => {
    const { sql, binds } = deriveStatement(attempt);
    if (sql !== attempt.golden || !bindsEqual(binds, attempt.binds)) {
      throw new Error(
        "generated conflict UPDATE + binds != golden:\n" +
          `  generated: ${sql}  ${JSON.stringify(binds)}\n` +
          `  golden:    ${attempt.golden}  ${JSON.stringify(attempt.binds)}`,
      );
    }
    return {
      casePointer: attempt.casePointer,
      sql,
      binds,
      affectedRows: attempt.affectedRows,
    } satisfies ConflictAttempt;
  });

  return { apply: applyStatements(loaded), attempts };
}

/**
 * The generator that DERIVES a conflict attempt's `UPDATE` + binds, chosen by the
 * entity kind:
 *
 *  - a VERSIONED entity → the m-opt-lock versioned `UPDATE` derived from the attempt's
 *    neutral write input (① `write`) classified against the metamodel: the domain
 *    `set` columns are `columnOrder(entity)` filtered to the row's attributes, the
 *    version advances `observedVersion + 1`, and the gate is intrinsic (`and
 *    version = ?`, a conflict is always optimistic — R4). Binds:
 *    `[…set values…, newVersion, pk, observedVersion]`;
 *  - a Transaction-Time entity, which carries no version column
 *    → the m-audit-write milestone CLOSE (`@parallax/bitemporal` `auditWriteStatements`,
 *    `"terminate"` yields the single close), gated on the observed Transaction-Time start
 *    (`in_z`) in optimistic mode and ungated in locking mode (the mode the case's
 *    `uow` block declares). The close text is metamodel-derived (DQ-B Family B), and
 *    its binds are DERIVED from the neutral write input (①): `out_z = at` (the close
 *    instant), the still-open bound `infinity`, and — in optimistic mode — the
 *    `and in_z = ?` gate bound to `observedTxStart`. The
 *    single SET column (`out_z`) stays metamodel-fixed, so ① never names it.
 *
 * Each is cross-checked against the authored golden + binds by `buildConflictPlan`,
 * so column identity is a genuine independent check between ① and the golden oracle.
 */
function conflictSqlDeriver(
  entity: EntityMetadata,
  loaded: LoadedCase,
  dialect: Dialect,
): (attempt: NormalizedAttempt) => { sql: string; binds: readonly unknown[] } {
  if (entity.versionAttribute() !== undefined) {
    const target = versionedTargetFor(entity, dialect);
    return (attempt) => versionedConflictStatement(entity, target, attempt, dialect);
  }
  const target = writeTargetFor(entity, dialect);
  const gated = loaded.uow?.concurrency === "optimistic";
  const [close] = auditWriteStatements("terminate", target, { gated });
  const transactionTime = entity.asOfAxes().find((axis) => axis.dimension === "transactionTime");
  if (transactionTime === undefined) {
    throw new Error(`temporal conflict close on '${entity.name}' has no Transaction Time`);
  }
  return (attempt) =>
    temporalCloseStatement(entity, close as string, transactionTime.infinity, gated, attempt);
}

/**
 * Derive a TEMPORAL / bitemporal conflict close's binds from its neutral write
 * input (①). A close writes no domain columns — it sets `out_z = at` keyed on the
 * still-open current row (`pk and out_z = infinity`), gated in optimistic mode on
 * the observed Transaction-Time start (`and in_z = observedTxStart`). The primary-key
 * attribute is the `where` key; a Bitemporal entity's Valid-Time discriminator
 * (`valid_start` → `from_z`, classified into `set`) is the extra `where` coordinate
 * the metamodel cannot value — its value slots between `out_z` and `in_z` in model
 * column order. Binds: `[at, pk, infinity, …validCoords, (observedTxStart if gated)]`.
 */
function temporalCloseStatement(
  entity: EntityMetadata,
  sql: string,
  infinity: unknown,
  gated: boolean,
  attempt: NormalizedAttempt,
): { sql: string; binds: readonly unknown[] } {
  const write = attempt.write;
  if (write === undefined) {
    throw new Error(
      `temporal conflict close at ${attempt.casePointer} carries no neutral write input (①)`,
    );
  }
  const { at, observedTxStart } = attempt;
  if (at === undefined) {
    throw new Error(
      `temporal conflict close at ${attempt.casePointer} requires an 'at' (the close instant → out_z) in its neutral write input (①)`,
    );
  }
  if (gated && observedTxStart === undefined) {
    throw new Error(
      `optimistic temporal conflict close at ${attempt.casePointer} requires an observedTxStart (the observed in_z gate token) in its neutral write input (①)`,
    );
  }
  const { pk, set } = classifyRow(entity, write);
  const validCoords = orderedColumns(entity)
    .filter((column) => set.has(column))
    .map((column) => set.get(column));
  const gateBinds = gated ? [observedTxStart] : [];
  const binds = [at, pk, infinity, ...validCoords, ...gateBinds];
  return { sql, binds };
}

/**
 * Derive a VERSIONED conflict attempt's `UPDATE` + binds from its neutral write
 * input (① `write`). The primary-key attribute is the `where` key, every other
 * attribute an assigned domain `set` column (in `columnOrder(entity)` order, never
 * JSON key order), and `observedVersion` the optimistic gate/advance token. A
 * conflict is intrinsically gated (R4), so the version advances `observedVersion +
 * 1` and the binds are `[…set values…, newVersion, pk, observedVersion]`.
 */
function versionedConflictStatement(
  entity: EntityMetadata,
  target: VersionedTarget,
  attempt: NormalizedAttempt,
  dialect: Dialect,
): { sql: string; binds: readonly unknown[] } {
  const write = attempt.write;
  if (write === undefined) {
    throw new Error(
      `versioned conflict attempt at ${attempt.casePointer} carries no neutral write input (①)`,
    );
  }
  const { pk, set, observedVersion } = classifyRow(entity, write);
  if (observedVersion === undefined) {
    throw new Error(
      `versioned conflict attempt at ${attempt.casePointer} requires an observedVersion in its write input (①)`,
    );
  }
  const setColumns = orderedColumns(entity).filter((column) => set.has(column));
  const sql = versionedUpdate(
    target,
    setColumns.map((column) => dialect.quoteIdentifier(column)),
  );
  const setValues = setColumns.map((column) => set.get(column));
  const binds = [...setValues, observedVersion + 1, pk, observedVersion];
  return { sql, binds };
}

/** A normalized attempt with its golden text + ① write resolved (single or retry). */
interface NormalizedAttempt {
  readonly casePointer: string;
  readonly golden: string;
  readonly binds: readonly unknown[];
  readonly affectedRows: number;
  /** The neutral write input (①) this attempt derives its UPDATE + binds from. */
  readonly write?: Record<string, unknown>;
  /** A temporal-close attempt's close instant (→ new `out_z`). */
  readonly at?: string;
  /** A temporal-close attempt's observed Transaction-Time start (`in_z`) optimistic gate. */
  readonly observedTxStart?: string;
}

/** Normalize the case's attempt(s) into a common shape (single or retry form). */
function normalizedAttempts(loaded: LoadedCase, dialect: Dialect): readonly NormalizedAttempt[] {
  const attempts = loaded.raw.when?.attempts;
  if (attempts && attempts.length > 0) {
    return attempts.map((attempt, index) => {
      const pointer = `/attempts/${index}`;
      const { sql, binds } = requireGoldenStatement(attempt.statements, dialect, pointer);
      return {
        casePointer: pointer,
        golden: sql,
        binds,
        affectedRows: attempt.affectedRows,
        write: attempt.write as Record<string, unknown>,
        ...(attempt.at === undefined ? {} : { at: attempt.at }),
        ...(attempt.observedTxStart === undefined
          ? {}
          : { observedTxStart: attempt.observedTxStart }),
      };
    });
  }
  const when = loaded.raw.when;
  const { sql, binds } = requireGoldenStatement(
    goldenEntries(loaded.raw),
    dialect,
    "/then/statements",
  );
  const affectedRows = loaded.raw.then?.affectedRows;
  if (affectedRows === undefined) {
    throw new Error(`${loaded.casePath}: conflict case is missing then.affectedRows`);
  }
  return [
    {
      casePointer: "/then/statements/0",
      golden: sql,
      binds,
      affectedRows,
      ...(when?.write === undefined ? {} : { write: when.write as Record<string, unknown> }),
      ...(when?.at === undefined ? {} : { at: when.at }),
      ...(when?.observedTxStart === undefined ? {} : { observedTxStart: when.observedTxStart }),
    },
  ];
}

/** The out-of-band `given.apply` statement(s), each carrying its own inline binds. */
function applyStatements(loaded: LoadedCase): readonly ApplyStatement[] {
  const apply = loaded.raw.given?.apply;
  if (apply === undefined) {
    return [];
  }
  return apply.map((entry) => ({
    sql: typeof entry.sql === "string" ? entry.sql : "",
    binds: entryBinds(entry),
  }));
}

/**
 * The single entity a conflict case targets: a VERSIONED entity (the m-opt-lock optimistic
 * gate on a version column) if one is declared, else a Transaction-Time temporal
 * (audit-only) entity (the m-audit-write milestone close gated on the observed `in_z`,
 * `m-temporal-read-009`-`m-temporal-read-012`), else the first entity.
 */
function conflictEntity(metamodel: Metamodel): EntityMetadata {
  for (const entity of metamodel.entities()) {
    if (entity.versionAttribute() !== undefined) {
      return entity;
    }
  }
  for (const entity of metamodel.entities()) {
    if (entity.asOfAxes().some((axis) => axis.dimension === "transactionTime")) {
      return entity;
    }
  }
  const [first] = metamodel.entities();
  if (first === undefined) {
    throw new Error("conflict case model declares no entities");
  }
  return first;
}

/** Resolve the entity's {@link VersionedTarget} (table, pk, version column). */
function versionedTargetFor(entity: EntityMetadata, dialect: Dialect): VersionedTarget {
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a versioned update`);
  }
  const version = entity.versionAttribute();
  if (version === undefined) {
    throw new Error(`entity '${entity.name}' has no optimistic-locking version column`);
  }
  return {
    table: dialect.quoteIdentifier(entity.table),
    pkColumn: dialect.quoteIdentifier(pk.column),
    versionColumn: dialect.quoteIdentifier(version.column),
  };
}

/**
 * Resolve the compiling dialect's single golden statement (`{sql, binds}`) for a
 * conflict attempt from its statement entries, or fail with the pointer. A conflict
 * attempt is one UPDATE, so the first resolved entry is the golden.
 */
function requireGoldenStatement(
  entries: readonly StatementEntry[],
  dialect: Dialect,
  pointer: string,
): { sql: string; binds: readonly unknown[] } {
  const [statement] = dialectStatements(entries, dialect.id);
  if (statement === undefined) {
    throw new Error(`conflict case is missing golden SQL for ${dialect.id} at ${pointer}`);
  }
  return statement;
}
