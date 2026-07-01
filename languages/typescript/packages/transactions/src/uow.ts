/**
 * M8 closure-demarcated unit of work — buffered writes combined + flushed as
 * set-based SQL.
 *
 * A unit of work buffers writes as combinable ops and, at its boundary, combines
 * and reorders them so the flush is (a) SET-BASED (buffered inserts of one entity
 * collapse into one multi-row `INSERT`; a batched update over uniform new values
 * collapses to `pk in (…)`, over non-uniform values to one keyed `UPDATE` per key)
 * and (b) FK-SAFE (a referenced parent's insert precedes a child insert that
 * points at it). This module owns the pure PLANNING of that combined flush — the
 * ordered list of canonical DML statements — from the declared write steps and
 * their authored binds; the caller executes them and observes the result.
 *
 * The DML **text** each form emits is delegated to {@link ./batch.js}; this module
 * decides, per step, WHICH form applies (insert row count from the bind arity;
 * uniform vs per-key from the declared statement count) and threads the authored
 * binds. It stays free of the metamodel: the caller resolves each step's
 * {@link BatchTarget} (table + quoted columns + pk) and passes it in.
 */
import { type BatchTarget, keyedUpdate, multiRowInsert, uniformUpdate } from "./batch.js";

/** The mutation kinds the M8 non-temporal batched flush realizes. */
export type BatchMutation = "insert" | "update";

/**
 * One declared write step: its mutation, the resolved physical target, the
 * declared golden statement count (`1` unless the step lists more), the authored
 * bind rows (one flat row per generated statement), and — for an `update` — the
 * quoted column the batch sets (`balance`), taken from the case's golden intent.
 */
export interface WriteStep {
  readonly mutation: BatchMutation;
  readonly target: BatchTarget;
  /** The declared golden statement count for the step (`statements`, default 1). */
  readonly statements: number;
  /** The authored bind rows for this step, one per generated statement. */
  readonly binds: readonly (readonly unknown[])[];
  /** The quoted set column an `update` writes (absent for an `insert`). */
  readonly setColumn?: string;
}

/** One planned DML statement: its canonical text paired with its bind row. */
export interface PlannedStatement {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/**
 * Combine the declared write steps into the ordered set-based flush. Steps are
 * flushed in declared order (the caller has already ordered them FK-safe — a
 * referenced parent's `insert` step precedes the child's; see
 * {@link orderInsertStepsForFk}), so this preserves that order.
 */
export function combineWrites(steps: readonly WriteStep[]): readonly PlannedStatement[] {
  const planned: PlannedStatement[] = [];
  for (const step of steps) {
    planned.push(...planStep(step));
  }
  return planned;
}

/** Plan one step into its one-or-more DML statements. */
function planStep(step: WriteStep): readonly PlannedStatement[] {
  return step.mutation === "insert" ? [planInsert(step)] : planUpdate(step);
}

/**
 * Plan an `insert` step: one multi-row `INSERT` whose row count is the bind arity
 * divided by the column count (three buffered inserts of `Account` → one 3-tuple
 * `INSERT`; a single FK-ordered insert → a 1-tuple `INSERT`). The step's authored
 * binds are a single flat row (all tuples concatenated), as the golden declares.
 */
function planInsert(step: WriteStep): PlannedStatement {
  const flat = step.binds[0] ?? [];
  const columnCount = step.target.columns.length;
  if (columnCount === 0 || flat.length % columnCount !== 0) {
    throw new Error(
      `insert binds arity ${flat.length} is not a multiple of the ${columnCount} column(s)`,
    );
  }
  const rowCount = flat.length / columnCount;
  return { sql: multiRowInsert(step.target, rowCount), binds: flat };
}

/**
 * Plan an `update` step. A single-statement step is the UNIFORM form (`set <col> =
 * ? where pk in (?, …)`) — one shared new value over `keyCount` keys, its binds
 * `[value, ...keys]`. A multi-statement step is the PER-KEY form (`0613`): one
 * keyed `update … where pk = ?` per distinct key, each paired with its own bind
 * row `[value, key]`.
 */
function planUpdate(step: WriteStep): readonly PlannedStatement[] {
  const setColumn = step.setColumn;
  if (setColumn === undefined) {
    throw new Error("an update step requires the quoted set column");
  }
  if (step.statements <= 1) {
    const flat = step.binds[0] ?? [];
    const keyCount = flat.length - 1; // one shared value + one bind per key
    return [{ sql: uniformUpdate(step.target, setColumn, keyCount), binds: flat }];
  }
  return step.binds.map((row) => ({ sql: keyedUpdate(step.target, setColumn), binds: row }));
}
