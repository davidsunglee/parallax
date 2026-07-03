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
 * where id = ? and version = ?`). This module generates it BY CONSTRUCTION from
 * the entity's physical shape via `@parallax/locking` (`versionedUpdate`) and pins
 * it against the authored golden, so the M10 versioned-UPDATE discipline (gate on
 * the read version, advance it in `set`) is owned by the runtime, not re-authored.
 * The `precondition` is an out-of-band naive statement run VERBATIM (it models a
 * concurrent writer, not our runtime's output).
 */
import { quoteIdentifier } from "@parallax/dialect";
import { type VersionedTarget, versionedUpdate } from "@parallax/locking";
import { type EntityMetadata, Metamodel } from "@parallax/operation";
import type { LoadedCase } from "./discover.js";

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

/** A raw retry attempt (its own golden UPDATE + binds + expected count). */
interface RawAttempt {
  readonly goldenSql?: RawSingleGolden;
  readonly binds?: readonly unknown[];
  readonly expectedAffectedRows?: number;
}

/**
 * Build the conflict plan: resolve the precondition statements (each paired with
 * its authored binds), then the ordered attempts — one for the single form, or
 * the declared list for the retry form. Each attempt's UPDATE is generated from
 * the entity's physical shape and its `set` columns are the case's authored intent
 * (parsed from the golden `set … , version = ?` clause), then pinned equal to the
 * golden by the compile lane.
 */
export function buildConflictPlan(loaded: LoadedCase): ConflictPlan {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const entity = versionedEntity(metamodel);
  const target = versionedTargetFor(entity);

  const attempts = rawAttempts(loaded).map((attempt) => {
    const golden = attempt.golden;
    const sql = versionedUpdate(target, setColumnsFromGolden(golden, target));
    if (sql !== golden) {
      throw new Error(
        `generated versioned UPDATE != golden:\n  generated: ${sql}\n  golden:    ${golden}`,
      );
    }
    return {
      casePointer: attempt.casePointer,
      sql,
      binds: attempt.binds,
      expectedAffectedRows: attempt.expectedAffectedRows,
    } satisfies ConflictAttempt;
  });

  return { precondition: preconditionStatements(loaded), attempts };
}

/** A normalized attempt with its golden text resolved (single or retry form). */
interface NormalizedAttempt {
  readonly casePointer: string;
  readonly golden: string;
  readonly binds: readonly unknown[];
  readonly expectedAffectedRows: number;
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
    }));
  }
  return [
    {
      casePointer: "/goldenSql/postgres",
      golden: requirePostgres(loaded.raw.goldenSql as RawSingleGolden | undefined, "/goldenSql"),
      binds: (loaded.raw.binds as readonly unknown[] | undefined) ?? [],
      expectedAffectedRows: requireCount(
        loaded.raw.expectedAffectedRows as number | undefined,
        "/expectedAffectedRows",
      ),
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

/** The single optimistically-locked entity a conflict case targets. */
function versionedEntity(metamodel: Metamodel): EntityMetadata {
  for (const entity of metamodel.entities()) {
    if (entity.versionAttribute() !== undefined) {
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

/**
 * The quoted DOMAIN set columns a golden versioned UPDATE writes (the `set` list
 * minus the trailing `version = ?`). `update account set balance = ?, version = ?
 * …` → `["balance"]`; the version-only bump `update account set version = ? …` →
 * `[]`. The columns are taken from the golden (the case's authored intent) so the
 * generated UPDATE reproduces it exactly.
 */
function setColumnsFromGolden(golden: string, target: VersionedTarget): readonly string[] {
  const match = /\bset\s+(.+?)\s+where\b/i.exec(golden);
  if (!match) {
    throw new Error(`could not parse the set clause from golden UPDATE: ${golden}`);
  }
  const assignments = (match[1] as string).split(",").map((piece) => piece.trim());
  const columns = assignments.map((assignment) => assignment.split(/\s*=/)[0]?.trim() ?? "");
  // Drop the trailing version assignment; the generator re-appends it.
  return columns.filter((column) => column !== target.versionColumn);
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
