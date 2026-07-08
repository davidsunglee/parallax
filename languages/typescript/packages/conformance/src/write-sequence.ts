/**
 * Build an executable **write-sequence plan** from a loaded case (m-temporal-read + m-unit-work + m-case-format).
 *
 * A `writeSequence` case carries an ordered list of mutations (`when.writeSequence`)
 * plus the golden DML statement entries (`then.statements`, each with its own inline
 * binds) and a `then.tableState`. This module turns the steps into the ordered
 * canonical DML the runner applies, choosing the discipline by the entity's
 * temporality:
 *
 *  - a **temporal** (audit-only) entity's step is milestone-chaining DML generated
 *    by `@parallax/bitemporal` (`auditWriteStatements`) — open a current row; close
 *    the current row keyed by `pk and out_z = infinity`; chain a new current row;
 *  - a **non-temporal** entity's step is the m-unit-work set-based batched flush generated
 *    by `@parallax/transactions`'s unit-of-work planner
 *    (`combineWrites`) — buffered inserts collapse into one multi-row `INSERT`
 *    (`m-batch-write-001`/`m-unit-work-003`), and a batched update is uniform `pk in (…)` (`m-batch-write-001`) or one
 *    keyed `UPDATE` per distinct key (`m-batch-write-002`, `statements: 2`).
 *
 * Each generated statement is paired, in order, with the authored bind row — the
 * write input the case declares. The statement count equals the sum of the steps'
 * declared counts, which the harness asserts equals `roundTrips`. The `m-core-002` /
 * `m-core-003` timestamp-shape single-row inserts fall out of the non-temporal `insert`
 * path (a one-row multi-row insert).
 */
import { auditWriteStatements, type MutationKind, type WriteTarget } from "@parallax/bitemporal";
import { columnOrder, type Dialect } from "@parallax/dialect";
import { type VersionedTarget, versionAdvancingUpdate, versionedUpdate } from "@parallax/locking";
import { type EntityMetadata, Metamodel } from "@parallax/operation";
import { type BatchTarget, combineWrites, type PlannedStatement } from "@parallax/transactions";
import { dialectStatements, goldenEntries } from "./case-format.js";
import { bindsEqual } from "./compare.js";
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

/**
 * A `writeSequence` step (the mutation kind + target entity). The step schema keys
 * its temporal variants on an `allOf`, so its generated static view is a loose
 * object; this reader names the members the plan consumes.
 */
interface RawWriteStep {
  readonly mutation: MutationKind;
  readonly entity: string;
  readonly statements?: number;
  /**
   * The neutral write input (①): the row(s) the step operates on, as flat
   * attribute-named `{ attr: value }` literals. Every derivation path — non-temporal
   * batched, versioned, temporal audit, `*Until` — derives its emitted column list +
   * order + binds from these (classified against the metamodel), so column identity
   * comes from case data, not the golden. REQUIRED on every writeSequence step (the
   * permanent Family A + Family B contract); typed optional only because the
   * step's generated view is a loose object.
   */
  readonly rows?: readonly Record<string, unknown>[];
  /**
   * The transaction / processing instant a TEMPORAL (audit-only) write records —
   * the milestone's `in_z`. The bookkeeping is DERIVED from it (a new milestone
   * opens `in_z = at`, `out_z = infinity`; a close binds `out_z = at`), never
   * authored in `rows`, so the m-audit-write milestone discipline stays under test. Absent on
   * a non-temporal step.
   */
  readonly at?: string;
  /**
   * The BUSINESS valid-time end bound a full-bitemporal `*Until` write closes the
   * window at — the milestone's `thru_z` on the chained rows (m-bitemp-write). A
   * `updateUntil` / `terminateUntil` bounds the change to `[businessFrom, until)`; a
   * plain (unbounded) `update` / `terminate` omits it (the residual window runs to
   * the currently-open row's `thru_z`). Absent on an audit-only step.
   */
  readonly until?: string;
}

/**
 * One flat write row classified by its metamodel role. Every present attribute's
 * value is keyed by its physical column (`columns`, pk + domain); the pk value is
 * split out (`pk` — a written column on `insert`, the `where` key on
 * `update` / `delete`) from the assigned domain columns (`set`). `observedVersion`
 * is the reserved optimistic control key (never a column). Roles come from the
 * metamodel, NEVER from JSON key order.
 */
export interface ClassifiedRow {
  readonly columns: ReadonlyMap<string, unknown>;
  readonly pk: unknown;
  readonly set: ReadonlyMap<string, unknown>;
  readonly observedVersion?: number;
}

/**
 * Classify a flat write row against the entity's metamodel — mirroring the
 * fixture loader (`runner.ts` `loadFixtures`), which resolves attribute-name rows
 * to columns. Each key is the reserved control key `observedVersion`, an ENTITY
 * ATTRIBUTE name, or a top-level VALUE-OBJECT name. A value object resolves
 * FIRST-class to its ONE structured-document column (m-value-object): the WHOLE
 * value — an object (`one`), an array (`many`), or `null` — binds atomically at
 * that column's `columnOrder` position, NEVER decomposed into path-level binds
 * (even when its content is marker-shaped, per the role-based disambiguation
 * contract). An unknown key throws (a typo surfaces loudly). The primary-key
 * attribute's value is split into `pk`; every other attribute / value object
 * column into `set`.
 */
export function classifyRow(entity: EntityMetadata, row: Record<string, unknown>): ClassifiedRow {
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
    // Resolve the key by role: a top-level value object binds its whole document
    // to the one structured column; otherwise it must be an entity attribute.
    const valueObject = entity.findValueObject(key);
    const column =
      valueObject !== undefined ? valueObject.column : entity.attributeByName(key).column;
    columns.set(column, value);
    if (column === pkColumn) {
      pk = value;
    } else {
      set.set(column, value);
    }
  }
  return { columns, pk, set, ...(observedVersion === undefined ? {} : { observedVersion }) };
}

/**
 * The physical DDL view of an entity — attribute columns PLUS exactly one
 * structured-document column per top-level value object (m-value-object). This is
 * the single seam every column-order / DDL / write-target derivation routes
 * through, so the value-object column lands in `columnOrder` position uniformly
 * (fixture load, table-state read, insert/update binds) instead of each caller
 * rebuilding an attributes-only synthetic entity that would drop it.
 */
export function ddlEntityView(entity: EntityMetadata): {
  readonly table: string;
  readonly attributes: readonly { readonly type: string; readonly column: string }[];
  readonly valueObjects: readonly { readonly column: string; readonly nullable: boolean }[];
} {
  return {
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
    valueObjects: entity.valueObjects().map((vo) => ({ column: vo.column, nullable: vo.nullable })),
  };
}

/**
 * The entity's physical column list in descriptor order: attribute columns then
 * one column per top-level value object (m-value-object).
 */
export function orderedColumns(entity: EntityMetadata): readonly string[] {
  return columnOrder(ddlEntityView(entity));
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
 * entity flushes the m-unit-work set-based batched forms (`@parallax/transactions`'s
 * unit-of-work planner). The two never mix within a step.
 */
export function buildWriteSequencePlan(loaded: LoadedCase, dialect: Dialect): WriteSequencePlan {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const steps = (loaded.raw.when?.writeSequence ?? []) as readonly RawWriteStep[];
  // The golden DML lives at `then.statements`; each `{sql, binds}` entry carries its
  // own inline binds (no positional pairing), so the per-statement sql + binds are
  // read directly from the dialect's entries.
  const goldenStmts = dialectStatements(goldenEntries(loaded.raw), dialect.id);
  const golden = goldenStmts.map((statement) => statement.sql);
  const bindRows = goldenStmts.map((statement) => statement.binds);
  const concurrency = loaded.uow?.concurrency;
  // A full-bitemporal write sequence gates its inactivating close in OPTIMISTIC mode
  // (the observed rectangle's `(from_z, in_z)`, `m-bitemp-write-008`). A writeSequence
  // carries no `when.uow`, so the optimistic intent rides the `m-opt-lock` module tag —
  // the same signal the case declares to claim the gate is under test.
  const gated = loaded.tags.includes("m-opt-lock");
  // The currently-open (current-on-processing) rows per pk, reconstructed by in-memory
  // replay: a rectangle split's head/tail inserts carry the UNCHANGED columns of the
  // open row (acct_num, the old value) — not present in the mutating step's own ①. A pk
  // holds a LIST because a split leaves several open business rectangles (head / (middle /)
  // tail), each a candidate for a later same-pk split.
  const openRows = new Map<unknown, ReadonlyMap<string, unknown>[]>();

  const statements: WriteStatementPlan[] = [];
  let bindIndex = 0;
  steps.forEach((step, stepIndex) => {
    const entity = metamodel.entity(step.entity);
    const generated = isBitemporalEntity(entity)
      ? bitemporalStatementsForStep(step, entity, dialect, openRows, gated)
      : isTemporalEntity(entity)
        ? auditStatementsForStep(step, entity, dialect)
        : batchStatementsForStep(step, entity, bindRows, bindIndex, golden, concurrency, dialect);
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

/** True when the entity carries BOTH as-of axes — the full-bitemporal rectangle profile. */
function isBitemporalEntity(entity: EntityMetadata): boolean {
  const axes = new Set(entity.asOfAttributes().map((axis) => axis.axis));
  return axes.has("business") && axes.has("processing");
}

/**
 * The generated rectangle-split statements for one FULL-bitemporal step, each paired
 * with binds DERIVED from the classified ① row, the step instants (`at` / `until`),
 * and the currently-open row reconstructed by replay (`openRows`). A bitemporal write
 * never mutates in place — it closes the original on the PROCESSING axis and chains
 * milestones partitioned on the BUSINESS axis (m-bitemp-write):
 *
 *  - `insert` / `insertUntil` open one milestone `[businessFrom, businessTo|until) ×
 *    [at, infinity)` and record it as the pk's currently-open row;
 *  - `update` (plain, unbounded) → close + head (old `[from_z, B)`) + new tail (new
 *    `[B, thru_z)`); `updateUntil` (windowed) → close + head + middle (new `[B, until)`)
 *    + tail (old `[until, thru_z)`); `terminate` → close + head only; `terminateUntil`
 *    → close + head + tail (no middle).
 *
 * The head/tail carry the open row's UNCHANGED columns (acct_num, the old value) — NOT
 * present in the mutating step's own ① — so they are reconstructed from `openRows` (the
 * compile lane is Docker-free, so no DB read-back is available). A gated close
 * (`m-bitemp-write-008`, optimistic) binds the observed rectangle's `(from_z, in_z)`
 * from that same open row — distinct from the window boundary.
 */
function bitemporalStatementsForStep(
  step: RawWriteStep,
  entity: EntityMetadata,
  dialect: Dialect,
  openRows: Map<unknown, ReadonlyMap<string, unknown>[]>,
  gated: boolean,
): readonly { sql: string; binds: readonly unknown[] }[] {
  const business = entity.asOfAttributes().find((axis) => axis.axis === "business");
  const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
  if (business === undefined || processing === undefined) {
    throw new Error(`bitemporal write on '${entity.name}' is missing a business/processing axis`);
  }
  const fromZ = business.fromColumn;
  const thruZ = business.toColumn;
  const inZ = processing.fromColumn;
  const outZ = processing.toColumn;
  const infinity = processing.infinity;
  const cols = orderedColumns(entity);
  const target = writeTargetFor(entity, dialect);
  const [rawRow] = step.rows ?? [];
  if (rawRow === undefined) {
    throw new Error(`bitemporal write on '${entity.name}' requires a row in its ① input`);
  }
  const row = classifyRow(entity, rawRow);
  const { at, until } = step;
  if (at === undefined) {
    throw new Error(
      `bitemporal write on '${entity.name}' requires an 'at' (the txn instant → in_z)`,
    );
  }

  // A milestone OPEN (insert / insertUntil): the full physical row with `in_z = at`,
  // `out_z = infinity`, and — for insertUntil — `thru_z = until` (a bounded business
  // window). Record it as the pk's currently-open row for a later rectangle split.
  if (step.mutation === "insert" || step.mutation === "insertUntil") {
    const openBinds = cols.map((column) =>
      column === inZ
        ? at
        : column === outZ
          ? infinity
          : column === thruZ && step.mutation === "insertUntil"
            ? until
            : row.columns.get(column),
    );
    const openRow = new Map(cols.map((column, index) => [column, openBinds[index]]));
    const opened = openRows.get(row.pk);
    if (opened === undefined) {
      openRows.set(row.pk, [openRow]);
    } else {
      opened.push(openRow);
    }
    const [insertSql] = auditWriteStatements("insert", target);
    return [{ sql: insertSql as string, binds: openBinds }];
  }

  // A rectangle SPLIT (update / terminate / updateUntil / terminateUntil): reconstruct the
  // currently-open row COVERING the mutation's business instant, chain the milestones
  // around it, then ADVANCE the open-row set (below) so a later same-pk split reconstructs
  // from the new current state — not a stale original.
  const businessFrom = row.columns.get(fromZ);
  if (businessFrom === undefined) {
    throw new Error(
      `bitemporal ${step.mutation} on '${entity.name}' requires a businessFrom (→ from_z)`,
    );
  }
  const openList = openRows.get(row.pk);
  if (openList === undefined || openList.length === 0) {
    throw new Error(
      `bitemporal ${step.mutation} on '${entity.name}' has no prior insert opening pk ${String(row.pk)}`,
    );
  }
  // The open milestone whose BUSINESS window `[from_z, thru_z)` contains `businessFrom` —
  // the rectangle this split partitions. With one open row (the everyday single-split
  // cases) it is that row; after a prior split there are several, so the covering one is
  // selected on the business axis (`infinity` the open upper bound).
  const open = coveringOpenRow(openList, businessFrom, fromZ, thruZ, infinity);
  if (open === undefined) {
    throw new Error(
      `bitemporal ${step.mutation} on '${entity.name}' has no currently-open row covering ` +
        `businessFrom ${String(businessFrom)} for pk ${String(row.pk)}`,
    );
  }
  const bounded = step.mutation === "updateUntil" || step.mutation === "terminateUntil";
  if (bounded && until === undefined) {
    throw new Error(`bitemporal ${step.mutation} on '${entity.name}' requires an 'until' bound`);
  }
  // The residual window's upper bound: the explicit `until` for a windowed write, else
  // the covering row's own `thru_z` (unbounded — runs to that row's business end).
  const windowEnd = bounded ? until : open.get(thruZ);
  // The step's NEW domain values (the value(s) it corrects), i.e. its `set` columns
  // excluding the as-of axis columns — applied only to the new-value milestones.
  const axisColumns = new Set([fromZ, thruZ, inZ, outZ]);
  const newDomain = new Map<string, unknown>();
  for (const [column, value] of row.set) {
    if (!axisColumns.has(column)) {
      newDomain.set(column, value);
    }
  }
  // Build one chained-milestone bind row: the open row's columns (base) with the
  // business interval [from, thru), fresh processing [at, infinity), and — for a
  // new-value milestone — the step's domain overrides.
  const rectangle = (fromValue: unknown, thruValue: unknown, useNew: boolean): readonly unknown[] =>
    cols.map((column) => {
      if (column === inZ) return at;
      if (column === outZ) return infinity;
      if (column === fromZ) return fromValue;
      if (column === thruZ) return thruValue;
      if (useNew && newDomain.has(column)) return newDomain.get(column);
      return open.get(column);
    });

  const head = rectangle(open.get(fromZ), businessFrom, false); // old value, [from_z, B)
  const inserts: (readonly unknown[])[] = [];
  switch (step.mutation) {
    case "update": // plain unbounded: head (old) + new tail (new), no middle/old-tail
      inserts.push(head, rectangle(businessFrom, windowEnd, true));
      break;
    case "updateUntil": // windowed: head (old) + middle (new) + tail (old)
      inserts.push(
        head,
        rectangle(businessFrom, windowEnd, true),
        rectangle(windowEnd, open.get(thruZ), false),
      );
      break;
    case "terminate": // plain unbounded: head only — value absent from B onward
      inserts.push(head);
      break;
    case "terminateUntil": // windowed: head (old) + tail (old), no middle
      inserts.push(head, rectangle(windowEnd, open.get(thruZ), false));
      break;
  }

  // Advance the open-row set: the split row is now closed on the processing axis, and each
  // chained milestone (head / (middle /) tail) opens fresh — record them as the pk's
  // currently-open rows so a subsequent same-pk split reconstructs from here.
  const remaining = openList.filter((candidate) => candidate !== open);
  for (const binds of inserts) {
    remaining.push(new Map(cols.map((column, index) => [column, binds[index]])));
  }
  openRows.set(row.pk, remaining);

  const [closeSql] = auditWriteStatements("terminate", target, { gated });
  const [insertSql] = auditWriteStatements("insert", target);
  // The inactivating close sets `out_z = at` keyed on the current-on-processing row; a
  // gated close adds the observed rectangle's `(from_z, in_z)` from the open row.
  const closeBinds: readonly unknown[] = gated
    ? [at, row.pk, infinity, open.get(fromZ), open.get(inZ)]
    : [at, row.pk, infinity];
  return [
    { sql: closeSql as string, binds: closeBinds },
    ...inserts.map((binds) => ({ sql: insertSql as string, binds })),
  ];
}

/**
 * The currently-open milestone whose BUSINESS window `[from_z, thru_z)` contains the
 * mutation instant `businessFrom` — the rectangle a split partitions. The processing
 * axis's `infinity` sentinel is the open upper bound (greater than every finite instant);
 * finite instants share an ISO-8601 shape, so their lexical order is chronological.
 * Returns `undefined` when no open row covers the instant (a malformed sequence).
 */
function coveringOpenRow(
  openList: readonly ReadonlyMap<string, unknown>[],
  businessFrom: unknown,
  fromZ: string,
  thruZ: string,
  infinity: unknown,
): ReadonlyMap<string, unknown> | undefined {
  const before = (left: unknown, right: unknown): boolean => {
    if (left === right) return false;
    if (left === infinity) return false;
    if (right === infinity) return true;
    return String(left) < String(right);
  };
  // Half-open coverage: `from_z <= businessFrom < thru_z`.
  return openList.find(
    (open) => !before(businessFrom, open.get(fromZ)) && before(businessFrom, open.get(thruZ)),
  );
}

/**
 * The generated milestone-chaining statements for one TEMPORAL step (audit-only),
 * each paired with its binds DERIVED from the classified ① row + the step-level
 * transaction instant (`at`). A milestone ALWAYS writes the entity's full physical
 * row (DQ-B Family B), so the emitted column list stays metamodel-sourced
 * (`writeTargetFor`, `columnOrder(entity)`) — ① carries only the domain values
 * (`rows`) and `at`, and the bookkeeping is DERIVED: a new milestone opens
 * `in_z = at`, `out_z = infinity`, and a close binds `[at, pk, infinity]` (set
 * `out_z = at` where the pk and the still-open `out_z = infinity`). So the m-temporal-read
 * discipline — bookkeeping is derived, never authored — is under test:
 * `in_z`/`out_z`/`infinity` never appear in ①.
 *
 * `insert` consumes one statement (open); `update` two over the SAME row (close,
 * then chain a new full-row milestone carrying the row's unchanged columns);
 * `terminate` one (close only). The derived binds cross-check the authored golden
 * binds in the compile lane — a genuine independent check, not a golden parse.
 */
function auditStatementsForStep(
  step: RawWriteStep,
  entity: EntityMetadata,
  dialect: Dialect,
): readonly { sql: string; binds: readonly unknown[] }[] {
  const texts = auditWriteStatements(step.mutation, writeTargetFor(entity, dialect));
  const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
  if (processing === undefined) {
    throw new Error(`temporal write on '${entity.name}' has no processing axis to derive in_z`);
  }
  const { at } = step;
  if (at === undefined) {
    throw new Error(
      `temporal write on '${entity.name}' requires an 'at' (the transaction instant → in_z) in its neutral write input (①)`,
    );
  }
  const [row] = (step.rows ?? []).map((r) => classifyRow(entity, r));
  if (row === undefined) {
    throw new Error(
      `temporal write on '${entity.name}' requires a row in its neutral write input (①)`,
    );
  }
  // A new milestone opens the full physical row with `in_z = at` and the open
  // bound `out_z = infinity` (both DERIVED, never authored); every other column's
  // value is pulled from the classified row by physical column, in columnOrder.
  const openBinds: readonly unknown[] = orderedColumns(entity).map((column) =>
    column === processing.fromColumn
      ? at
      : column === processing.toColumn
        ? processing.infinity
        : row.columns.get(column),
  );
  // The close sets `out_z = at`, keyed on the still-open current row
  // (`pk and out_z = infinity`).
  const closeBinds: readonly unknown[] = [at, row.pk, processing.infinity];
  const binds =
    step.mutation === "insert"
      ? [openBinds]
      : step.mutation === "update"
        ? [closeBinds, openBinds]
        : [closeBinds];
  return texts.map((sql, offset) => ({ sql, binds: binds[offset] ?? [] }));
}

/**
 * The generated DML statements for one NON-temporal step, via the m-unit-work unit-of-work
 * planner (`combineWrites`): an `insert` collapses its buffered rows into one
 * multi-row `INSERT`, an `update` is uniform `pk in (…)` (one statement) or one
 * keyed `UPDATE` per distinct key.
 *
 * Column identity + order + binds are DERIVED from the neutral write input (①,
 * `step.rows`) classified against the metamodel — the emitted column list is
 * `columnOrder(entity)` filtered to the present attributes (`m-unit-work-003` omits the
 * nullable `shippedOn`, so `shipped_on` is dropped from the INSERT), never parsed
 * out of the golden. The `then.statements` golden stays an independent oracle the
 * compile lane cross-checks the emission against.
 */
function batchStatementsForStep(
  step: RawWriteStep,
  entity: EntityMetadata,
  bindRows: readonly (readonly unknown[])[],
  bindIndex: number,
  golden: readonly string[],
  concurrency: string | undefined,
  dialect: Dialect,
): readonly { sql: string; binds: readonly unknown[] }[] {
  const mutation = step.mutation === "insert" ? "insert" : "update";
  const count = step.statements ?? 1;
  const rows = (step.rows ?? []).map((row) => classifyRow(entity, row));
  // A VERSIONED entity's keyed update advances its framework-owned version — the
  // readless batched forms below apply only to a non-versioned entity (a versioned
  // set-based update MUST materialize per object, m-opt-lock / core ADR 0014). Columns, the
  // advance, and the binds are DERIVED from the neutral write input (①) and routed
  // by `(versionAttribute, uow.concurrency)`: locking mode ⇒ ungated advance
  // (`m-opt-lock-002`), optimistic ⇒ gated advance — mirroring the runtime's own routing.
  if (mutation === "update" && entity.versionAttribute() !== undefined) {
    return versionedUpdateStatements(
      entity,
      rows,
      concurrency,
      golden.slice(bindIndex, bindIndex + count),
      bindRows.slice(bindIndex, bindIndex + count),
      dialect,
    );
  }
  const planned =
    mutation === "insert"
      ? insertStatements(entity, rows, dialect)
      : updateStatements(entity, rows, dialect);
  return planned.map((statement: PlannedStatement) => ({
    sql: statement.sql,
    binds: statement.binds,
  }));
}

/**
 * Plan a NON-temporal `insert` step from its classified ① rows: the emitted column
 * list is `columnOrder(entity)` filtered to the domain columns any row supplies (in
 * model order — an unset nullable attribute is absent, so its column is omitted,
 * `m-unit-work-003`), and the flat binds are each row's values pulled in that same column
 * order. A multi-row insert collapses every row into one statement (`combineWrites`).
 *
 * A VERSIONED entity's insert appends the framework-owned version column with the
 * DERIVED initial value `1` (the m-opt-lock optimistic-lock baseline, `m-detach-001`) — never
 * authored in ① (`observedVersion` is absent on an insert), so it is neither in the
 * row's columns nor its binds. This mirrors the reference harness's
 * `_assert_insert_input` gate.
 */
function insertStatements(
  entity: EntityMetadata,
  rows: readonly ClassifiedRow[],
  dialect: Dialect,
): readonly PlannedStatement[] {
  const versionColumn = entity.versionAttribute()?.column;
  const domain = orderedColumns(entity).filter(
    (column) => column !== versionColumn && rows.some((row) => row.columns.has(column)),
  );
  const present = versionColumn === undefined ? domain : [...domain, versionColumn];
  const target: BatchTarget = {
    ...batchTargetFor(entity, dialect),
    columns: present.map((column) => dialect.quoteIdentifier(column)),
  };
  const flat = rows.flatMap((row) => [
    ...domain.map((column) => row.columns.get(column)),
    ...(versionColumn === undefined ? [] : [1]),
  ]);
  return combineWrites([{ mutation: "insert", target, statements: 1, binds: [flat] }]);
}

/**
 * Plan a NON-temporal `update` step from its classified ① rows: the assigned `set`
 * column(s) are `columnOrder(entity)` filtered to the domain columns present (model
 * order, not key order); the pk of each row is the `where` key. Uniform-vs-per-key
 * is decided by value equality across the rows — a shared new value collapses to
 * one `where pk in (…)` statement (`m-batch-write-001`), non-uniform values flush one keyed
 * `UPDATE` per row (`m-batch-write-002`).
 */
function updateStatements(
  entity: EntityMetadata,
  rows: readonly ClassifiedRow[],
  dialect: Dialect,
): readonly PlannedStatement[] {
  const setColumns = orderedColumns(entity).filter((column) =>
    rows.some((row) => row.set.has(column)),
  );
  const setColumn = setColumns.map((column) => dialect.quoteIdentifier(column)).join(", ");
  const target = batchTargetFor(entity, dialect);
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
 * The generated versioned `UPDATE`(s) for a VERSIONED entity, DERIVED from the
 * neutral write input (①) classified against the metamodel — one per ① row:
 *
 *  - the domain `set` columns are `columnOrder(entity)` filtered to the row's
 *    assigned attributes (model order, never JSON key order);
 *  - the framework-owned version advances `observedVersion + 1` (derived, never
 *    authored), appended to the `set`;
 *  - the mode routes the gate: `locking` ⇒ an ungated advance
 *    (`versionAdvancingUpdate`, the m-read-lock shared-read-lock `m-opt-lock-002` / `m-detach-002` shape),
 *    `optimistic` ⇒ a gated advance (`versionedUpdate`, `... and version = ?`);
 *  - the binds are `[…set values…, newVersion, pk]` (locking) or
 *    `[…set values…, newVersion, pk, observedVersion]` (optimistic).
 *
 * The generated text AND binds are cross-checked against the authored golden (②) —
 * a genuine INDEPENDENT check now the columns come from ①, not a golden parse — so
 * a case whose ① and golden disagree fails loudly here.
 */
function versionedUpdateStatements(
  entity: EntityMetadata,
  rows: readonly ClassifiedRow[],
  concurrency: string | undefined,
  golden: readonly string[],
  goldenBinds: readonly (readonly unknown[])[],
  dialect: Dialect,
): readonly { sql: string; binds: readonly unknown[] }[] {
  const target = versionedTargetFor(entity, dialect);
  const gated = concurrency === "optimistic";
  return rows.map((row, offset) => {
    if (row.observedVersion === undefined) {
      throw new Error(
        `versioned update on '${entity.name}' requires an observedVersion in its neutral write input (①)`,
      );
    }
    const setColumns = orderedColumns(entity).filter((column) => row.set.has(column));
    const quoted = setColumns.map((column) => dialect.quoteIdentifier(column));
    const sql = gated ? versionedUpdate(target, quoted) : versionAdvancingUpdate(target, quoted);
    const setValues = setColumns.map((column) => row.set.get(column));
    const newVersion = row.observedVersion + 1;
    const binds = gated
      ? [...setValues, newVersion, row.pk, row.observedVersion]
      : [...setValues, newVersion, row.pk];
    const goldenText = golden[offset];
    if (sql !== goldenText || !bindsEqual(binds, goldenBinds[offset] ?? [])) {
      throw new Error(
        "generated versioned UPDATE + binds != golden:\n" +
          `  generated: ${sql}  ${JSON.stringify(binds)}\n` +
          `  golden:    ${goldenText ?? "<absent>"}  ${JSON.stringify(goldenBinds[offset] ?? [])}`,
      );
    }
    return { sql, binds };
  });
}

/** Resolve a versioned entity's {@link VersionedTarget} (table, pk, version column). */
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

/** Resolve an entity's physical {@link BatchTarget} (table, quoted columns, pk). */
function batchTargetFor(entity: EntityMetadata, dialect: Dialect): BatchTarget {
  const columns = columnOrder(ddlEntityView(entity)).map((column) =>
    dialect.quoteIdentifier(column),
  );
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a batched write`);
  }
  return {
    table: dialect.quoteIdentifier(entity.table),
    columns,
    pkColumn: dialect.quoteIdentifier(pk.column),
  };
}

/**
 * Resolve an entity's physical {@link WriteTarget} (table, columns, pk, out_z,
 * in_z). Shared by the write-sequence chaining generator and the conflict-plan
 * temporal gated-close re-derivation (`conflict.ts`), so both derive the close text
 * from ONE resolver (no drift). `fromColumn` (`in_z`) is the derived optimistic gate
 * an OPTIMISTIC-mode close binds the observed value on (m-opt-lock).
 */
export function writeTargetFor(entity: EntityMetadata, dialect: Dialect): WriteTarget {
  const columns = columnOrder(ddlEntityView(entity)).map((column) =>
    dialect.quoteIdentifier(column),
  );
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a write sequence`);
  }
  // The processing axis's `toColumn` (`out_z`) the close UPDATE sets + keys on, and
  // its `fromColumn` (`in_z`) the optimistic gate. Absent for a non-temporal entity
  // (only `insert` is legal there). The BUSINESS axis's `fromColumn` (`from_z`) is the
  // bitemporal discriminator a gated close on a full-bitemporal entity adds
  // (m-bitemp-write); absent for an audit-only entity, whose gated close omits it.
  const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
  const business = entity.asOfAttributes().find((axis) => axis.axis === "business");
  return {
    table: dialect.quoteIdentifier(entity.table),
    columns,
    pkColumn: dialect.quoteIdentifier(pk.column),
    ...(processing === undefined
      ? {}
      : {
          toColumn: dialect.quoteIdentifier(processing.toColumn),
          fromColumn: dialect.quoteIdentifier(processing.fromColumn),
        }),
    ...(business === undefined
      ? {}
      : { businessFromColumn: dialect.quoteIdentifier(business.fromColumn) }),
  };
}
