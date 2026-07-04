/**
 * Build an executable **conflict plan** from a loaded case (M10 optimistic
 * locking + M12).
 *
 * A `conflict` case proves the observable form of optimistic-lock conflict
 * detection: fixtures are loaded (the versioned row exists), an OPTIONAL
 * out-of-band `precondition` simulates a concurrent writer that advanced the
 * version, then the golden versioned `UPDATE`(s) are applied and the affected-row
 * count is asserted (`updatedRows != 1` is the conflict signal). Two forms:
 *
 *  - a SINGLE attempt (`expectedAffectedRows` + `goldenSql` + `binds`); and
 *  - an ordered `attempts` RETRY sequence (each attempt carries its own
 *    `goldenSql` + `binds` + `expectedAffectedRows`) — a stale UPDATE affects 0
 *    rows, then a fresh-version retry affects 1 (`0708`).
 *
 * The golden `UPDATE` text is authored in the case (`update … set … , version = ?
 * where id = ? and version = ?`). This module DERIVES it — text AND binds — from
 * the neutral write input (① `write`, a flat attribute-named row) classified
 * against the metamodel: the domain `set` columns are `columnOrder(entity)`
 * filtered to the row's assigned attributes, the version advances
 * `observedVersion + 1`, and a conflict is intrinsically gated (`and version = ?`,
 * R4). The derived emission is cross-checked against the authored golden + binds,
 * so `emitted === golden` is a genuine INDEPENDENT check of column identity, not a
 * golden-parse tautology. The `precondition` is an out-of-band naive statement run
 * VERBATIM (it models a concurrent writer, not our runtime's output).
 */
import { auditWriteStatements } from "@parallax/bitemporal";
import { quoteIdentifier } from "@parallax/dialect";
import { type VersionedTarget, versionedUpdate } from "@parallax/locking";
import { type EntityMetadata, Metamodel } from "@parallax/operation";
import { bindsEqual } from "./compare.js";
import type { LoadedCase } from "./discover.js";
import { classifyRow, orderedColumns, writeTargetFor } from "./write-sequence.js";

/** One versioned-UPDATE attempt: its generated SQL, binds, expected affected count. */
export interface ConflictAttempt {
  /** The JSON Pointer into the case (`/goldenSql/postgres` or `/attempts/<i>`). */
  readonly casePointer: string;
  /** The canonical versioned-UPDATE text (generated, pinned against the golden). */
  readonly sql: string;
  /** The authored binds `[…set values…, newVersion, pk, observedVersion]`. */
  readonly binds: readonly unknown[];
  /** The expected affected-row count (`1` success, `0` conflict). */
  readonly expectedAffectedRows: number;
}

/** One out-of-band precondition statement (a concurrent writer) run verbatim. */
export interface PreconditionStatement {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/** The executable conflict plan: the precondition + the ordered attempts. */
export interface ConflictPlan {
  readonly precondition: readonly PreconditionStatement[];
  readonly attempts: readonly ConflictAttempt[];
}

/** True when a case's shape is a conflict (optimistic-lock) case. */
export function isConflict(loaded: LoadedCase): boolean {
  return loaded.shape === "conflict";
}

/** A raw single-form conflict case's golden. */
interface RawSingleGolden {
  readonly postgres?: string;
}

/** A raw retry attempt (its own golden UPDATE + binds + expected count + ① write). */
interface RawAttempt {
  readonly goldenSql?: RawSingleGolden;
  readonly binds?: readonly unknown[];
  readonly expectedAffectedRows?: number;
  /** The neutral write input (①) for this attempt (flat attribute-named row). */
  readonly write?: Record<string, unknown>;
  /** A temporal-close attempt's close instant (→ new `out_z`). */
  readonly at?: string;
  /** A temporal-close attempt's observed processing-from (`in_z`) optimistic gate. */
  readonly observedInZ?: string;
}

/**
 * Build the conflict plan: resolve the precondition statements (each paired with
 * its authored binds), then the ordered attempts — one for the single form, or
 * the declared list for the retry form. Each attempt's UPDATE + binds are DERIVED
 * (a versioned conflict from its ① `write`; a temporal close from the metamodel),
 * then cross-checked against the authored golden + binds — a genuine independent
 * check, failing loudly if ① and the golden disagree.
 */
export function buildConflictPlan(loaded: LoadedCase): ConflictPlan {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const entity = conflictEntity(metamodel);
  const deriveStatement = conflictSqlDeriver(entity, loaded);

  const attempts = rawAttempts(loaded).map((attempt) => {
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
      expectedAffectedRows: attempt.expectedAffectedRows,
    } satisfies ConflictAttempt;
  });

  return { precondition: preconditionStatements(loaded), attempts };
}

/**
 * The generator that DERIVES a conflict attempt's `UPDATE` + binds, chosen by the
 * entity kind:
 *
 *  - a VERSIONED entity → the M10 versioned `UPDATE` derived from the attempt's
 *    neutral write input (① `write`) classified against the metamodel: the domain
 *    `set` columns are `columnOrder(entity)` filtered to the row's attributes, the
 *    version advances `observedVersion + 1`, and the gate is intrinsic (`and
 *    version = ?`, a conflict is always optimistic — R4). Binds:
 *    `[…set values…, newVersion, pk, observedVersion]`;
 *  - a processing-axis TEMPORAL (audit-only) entity, which carries no version column
 *    → the M7 milestone CLOSE (`@parallax/bitemporal` `auditWriteStatements`,
 *    `"terminate"` yields the single close), GATED on the observed processing-from
 *    (`in_z`) in optimistic mode and ungated in locking mode (the mode the case's
 *    `uow` block declares). The close text is metamodel-derived (DQ-B Family B), and
 *    its binds are DERIVED from the neutral write input (①): `out_z = at` (the close
 *    instant), the still-open bound `infinity`, and — in optimistic mode — the
 *    `and in_z = ?` gate bound to `observedInZ` (the observed processing-from). The
 *    single SET column (`out_z`) stays metamodel-fixed, so ① never names it.
 *
 * Each is cross-checked against the authored golden + binds by `buildConflictPlan`,
 * so column identity is a genuine independent check, not a golden-parse tautology.
 */
function conflictSqlDeriver(
  entity: EntityMetadata,
  loaded: LoadedCase,
): (attempt: NormalizedAttempt) => { sql: string; binds: readonly unknown[] } {
  if (entity.versionAttribute() !== undefined) {
    const target = versionedTargetFor(entity);
    return (attempt) => versionedConflictStatement(entity, target, attempt);
  }
  const target = writeTargetFor(entity);
  const gated = loaded.uow?.concurrency === "optimistic";
  const [close] = auditWriteStatements("terminate", target, { gated });
  const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
  if (processing === undefined) {
    throw new Error(`temporal conflict close on '${entity.name}' has no processing axis`);
  }
  return (attempt) => temporalCloseStatement(entity, close as string, processing.infinity, gated, attempt);
}

/**
 * Derive a TEMPORAL / bitemporal conflict close's binds from its neutral write
 * input (①). A close writes no domain columns — it sets `out_z = at` keyed on the
 * still-open current row (`pk and out_z = infinity`), gated in optimistic mode on
 * the observed processing-from (`and in_z = observedInZ`). The primary-key
 * attribute is the `where` key; a bitemporal entity's business discriminator (e.g.
 * `businessFrom` → `from_z`, classified into `set`) is the extra `where` coordinate
 * the metamodel cannot value — its value slots between `out_z` and `in_z` in model
 * column order. Binds: `[at, pk, infinity, …businessCoords, (observedInZ if gated)]`.
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
  const { at, observedInZ } = attempt;
  if (at === undefined) {
    throw new Error(
      `temporal conflict close at ${attempt.casePointer} requires an 'at' (the close instant → out_z) in its neutral write input (①)`,
    );
  }
  if (gated && observedInZ === undefined) {
    throw new Error(
      `optimistic temporal conflict close at ${attempt.casePointer} requires an observedInZ (the observed in_z gate token) in its neutral write input (①)`,
    );
  }
  const { pk, set } = classifyRow(entity, write);
  const businessCoords = orderedColumns(entity)
    .filter((column) => set.has(column))
    .map((column) => set.get(column));
  const gateBinds = gated ? [observedInZ] : [];
  const binds = [at, pk, infinity, ...businessCoords, ...gateBinds];
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
  const sql = versionedUpdate(target, setColumns.map(quoteIdentifier));
  const setValues = setColumns.map((column) => set.get(column));
  const binds = [...setValues, observedVersion + 1, pk, observedVersion];
  return { sql, binds };
}

/** A normalized attempt with its golden text + ① write resolved (single or retry). */
interface NormalizedAttempt {
  readonly casePointer: string;
  readonly golden: string;
  readonly binds: readonly unknown[];
  readonly expectedAffectedRows: number;
  /** The neutral write input (①) this attempt derives its UPDATE + binds from. */
  readonly write?: Record<string, unknown>;
  /** A temporal-close attempt's close instant (→ new `out_z`). */
  readonly at?: string;
  /** A temporal-close attempt's observed processing-from (`in_z`) optimistic gate. */
  readonly observedInZ?: string;
}

/** Normalize the case's attempt(s) into a common shape (single or retry form). */
function rawAttempts(loaded: LoadedCase): readonly NormalizedAttempt[] {
  const attempts = loaded.raw.attempts as readonly RawAttempt[] | undefined;
  if (attempts && attempts.length > 0) {
    return attempts.map((attempt, index) => ({
      casePointer: `/attempts/${index}`,
      golden: requirePostgres(attempt.goldenSql, `/attempts/${index}`),
      binds: (attempt.binds ?? []) as readonly unknown[],
      expectedAffectedRows: requireCount(attempt.expectedAffectedRows, `/attempts/${index}`),
      ...(attempt.write === undefined ? {} : { write: attempt.write }),
      ...(attempt.at === undefined ? {} : { at: attempt.at }),
      ...(attempt.observedInZ === undefined ? {} : { observedInZ: attempt.observedInZ }),
    }));
  }
  const write = loaded.raw.write as Record<string, unknown> | undefined;
  const at = loaded.raw.at as string | undefined;
  const observedInZ = loaded.raw.observedInZ as string | undefined;
  return [
    {
      casePointer: "/goldenSql/postgres",
      golden: requirePostgres(loaded.raw.goldenSql as RawSingleGolden | undefined, "/goldenSql"),
      binds: (loaded.raw.binds as readonly unknown[] | undefined) ?? [],
      expectedAffectedRows: requireCount(
        loaded.raw.expectedAffectedRows as number | undefined,
        "/expectedAffectedRows",
      ),
      ...(write === undefined ? {} : { write }),
      ...(at === undefined ? {} : { at }),
      ...(observedInZ === undefined ? {} : { observedInZ }),
    },
  ];
}

/** The out-of-band precondition statement(s), each paired with its binds. */
function preconditionStatements(loaded: LoadedCase): readonly PreconditionStatement[] {
  const raw = loaded.raw.precondition;
  if (raw === undefined) {
    return [];
  }
  const statements = Array.isArray(raw) ? (raw as string[]) : [raw as string];
  const bindsRaw = loaded.raw.preconditionBinds as readonly unknown[] | undefined;
  const perStatement = Array.isArray(bindsRaw?.[0]);
  return statements.map((sql, index) => ({
    sql,
    binds: perStatement
      ? ((bindsRaw?.[index] as readonly unknown[] | undefined) ?? [])
      : index === 0
        ? (bindsRaw ?? [])
        : [],
  }));
}

/**
 * The single entity a conflict case targets: a VERSIONED entity (the M10 optimistic
 * gate on a version column) if one is declared, else a processing-axis TEMPORAL
 * (audit-only) entity (the M7 milestone close gated on the observed `in_z`,
 * `0730`-`0733`), else the first entity.
 */
function conflictEntity(metamodel: Metamodel): EntityMetadata {
  for (const entity of metamodel.entities()) {
    if (entity.versionAttribute() !== undefined) {
      return entity;
    }
  }
  for (const entity of metamodel.entities()) {
    if (entity.asOfAttributes().some((axis) => axis.axis === "processing")) {
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

/** Require the Postgres golden for a conflict statement, or fail with the pointer. */
function requirePostgres(golden: RawSingleGolden | undefined, pointer: string): string {
  const sql = golden?.postgres;
  if (sql === undefined) {
    throw new Error(`conflict case is missing goldenSql.postgres at ${pointer}`);
  }
  return sql;
}

/** Require an expected affected-row count, or fail with the pointer. */
function requireCount(count: number | undefined, pointer: string): number {
  if (count === undefined) {
    throw new Error(`conflict case is missing expectedAffectedRows at ${pointer}`);
  }
  return count;
}
