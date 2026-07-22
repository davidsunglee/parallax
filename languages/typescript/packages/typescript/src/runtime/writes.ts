/**
 * The developer-runtime **write surface** (spec §4.1), executed at the composition
 * root over the injected `ParallaxDatabase`.
 *
 * The typed `tx.<entity>.create / update / terminate / delete` methods let an
 * application author idiomatic, NAMED writes; this module lowers each to canonical
 * DML by reusing the pure m-temporal-read / m-unit-work / m-opt-lock generators (no reinvented DML, no grader
 * code):
 *
 *  - **non-temporal `create`** buffers an insert; the unit of work flushes buffered
 *    inserts through the m-unit-work `combineWrites` planner — same-entity inserts collapse
 *    to one multi-row `INSERT`, a referenced parent's inserts precede a child's
 *    (`m-batch-write-001` / `m-unit-work-003`);
 *  - **non-temporal `update`** on a VERSIONED entity always advances the framework-
 *    owned version (m-opt-lock, core ADR 0013): in `optimistic` mode it issues the gated m-opt-lock
 *    `UPDATE` (gate on the version the unit of work OBSERVED, advance it) and
 *    classifies the affected count (`m-opt-lock-005` / `m-opt-lock-006` / `m-opt-lock-007`); in the default
 *    `locking` mode it issues the ungated version-advancing `UPDATE` (`m-opt-lock-002`). Either
 *    way an unobserved row read-before-writes and a no-op `set` issues no DML
 *    (`m-opt-lock-001`). On a NON-versioned entity it is a plain keyed `UPDATE`, one per
 *    selected key (`m-batch-write-001` / `m-batch-write-002` on the non-versioned `Wallet`);
 *  - **Transaction-Time-Only writes** chain milestones through the
 *    m-temporal-read `auditWriteStatements` generator: `create` opens `[transactionInstant,
 *    infinity)`, `update` closes the current row and chains a new one carrying the
 *    prior domain columns with the assignments applied, `terminate` closes only
 *    (`m-audit-write-001` / `m-audit-write-002` / `m-audit-write-003`).
 *
 * Named inputs map to canonical `columnOrder` binds via the entity metamodel, and
 * scalar values normalize through the injected dialect with the target m-core type
 * available. Transaction-Time instants come only from the transaction clock (spec §4.1)
 * — never a per-operation option — so production code cannot rewrite audit history.
 *
 * The `@parallax/db` port exposes `executeWrite(sql, binds)`, so set-based writes
 * read the native affected-row count from the active adapter without appending a
 * dialect-specific row-returning clause (spec §4 `WriteResult.affectedRows`).
 */

import { auditWriteStatements, type WriteTarget } from "@parallax/bitemporal";
import { INFINITY, ParallaxDecimal, Temporal } from "@parallax/core";
import type { ParallaxDatabase } from "@parallax/db";
import { columnOrder, type Dialect } from "@parallax/dialect";
import { ParallaxError } from "@parallax/lists";
import {
  classifyOutcome,
  type VersionedTarget,
  versionAdvancingUpdate,
  versionedUpdate,
} from "@parallax/locking";
import type { EntityMetadata, NormalizedAttribute } from "@parallax/metamodel";
import { type Operation, RejectionError, validateWriteValueObjects } from "@parallax/operation";
import { combineWrites, type WriteStep } from "@parallax/transactions";
import type { Predicate } from "../dsl/find.js";

/** The result of a set-based write (`update` / `terminate` / `delete`), spec §4. */
export interface WriteResult {
  /** The number of physical rows the write affected. */
  readonly affectedRows: number;
}

/** Thrown when a versioned write expects one row and affects zero (spec §4). */
export class ParallaxOptimisticLockError extends Error {
  constructor(entity: string) {
    super(`optimistic-lock conflict writing '${entity}': the row was modified concurrently`);
    this.name = "ParallaxOptimisticLockError";
    Object.setPrototypeOf(this, ParallaxOptimisticLockError.prototype);
  }
}

/**
 * Thrown when a temporal (audit-only) milestone CLOSE affects zero rows in LOCKING
 * mode (m-temporal-read/m-opt-lock) — the current milestone was superseded or terminated concurrently,
 * so there is no current row to close. Distinct from {@link ParallaxOptimisticLockError}:
 * a locking-mode zero-row close is a stale/consistency error, NOT a conflict — it
 * must surface to the caller and MUST NOT join the retry loop (a retry would re-read
 * the same absent current row and loop). A zero-row close is never silent in any mode.
 */
export class ParallaxTemporalCloseError extends Error {
  constructor(entity: string) {
    super(
      `temporal close affected 0 rows for '${entity}': the current milestone was ` +
        `superseded or terminated concurrently (no current row to close)`,
    );
    this.name = "ParallaxTemporalCloseError";
    Object.setPrototypeOf(this, ParallaxTemporalCloseError.prototype);
  }
}

/**
 * Thrown when a versioned entity's row is updated WITHOUT the unit of work having
 * observed it first (m-opt-lock read-before-write). Optimistic-lock version values are
 * framework-owned (core ADR 0013): the gate binds — and the advance is computed from —
 * the version a transaction-scoped read hydrated, so an update of an unobserved
 * row has no version to gate on or advance from and MUST be a read-before-write.
 */
export class ParallaxReadBeforeWriteError extends Error {
  constructor(entity: string) {
    super(
      `read-before-write updating '${entity}': a versioned update requires the unit of work ` +
        `to have read the row first (its optimistic-lock version is framework-owned)`,
    );
    this.name = "ParallaxReadBeforeWriteError";
    Object.setPrototypeOf(this, ParallaxReadBeforeWriteError.prototype);
  }
}

/**
 * Thrown when a developer write presents a structurally INVALID value-object
 * document — a required nested member absent at any depth, a required nested value
 * object / to-many array absent, or a document field whose type mismatches the
 * declared attribute (m-value-object write validation, resolved Q7, the rejected-
 * write contract cases 039-043). The runtime refuses it PRE-SQL — before any bind
 * generation or DML — so an invalid document never reaches the unconstrained jsonb
 * column, the same refusal the conformance runner makes (`validateWriteValueObjects`).
 *
 * It joins the public {@link ParallaxError} hierarchy (ADR-0007) so an application
 * catches it uniformly and branches on its machine-readable `code`; `code` (and the
 * `rule` alias) is the violated normative rule id — `write-required-attribute-missing`
 * / `write-required-value-object-missing` / `write-value-type-mismatch` — carried
 * over from the model-aware validator's `RejectionError`.
 */
export class ParallaxWriteValidationError extends ParallaxError {
  /** The violated normative rule id (an alias of the {@link ParallaxError.code}). */
  readonly rule: string;

  constructor(rule: string, message: string) {
    super(rule, message);
    this.rule = rule;
  }
}

/**
 * Refuse a value-object write PRE-SQL if any of its documents is structurally
 * invalid (m-value-object write validation). A no-op for an entity that declares no
 * value objects, and for a valid document; a violation raises a
 * {@link ParallaxWriteValidationError} (the mapped public form of the model-aware
 * validator's `RejectionError`) BEFORE any bind generation. The developer surface
 * makes the SAME pre-SQL refusal the conformance runner does for the rejected-write
 * contract (cases 039-043).
 */
function assertValueObjectWrite(entity: EntityMetadata, input: Record<string, unknown>): void {
  if (entity.valueObjects().length === 0) {
    return;
  }
  try {
    validateWriteValueObjects(entity, input);
  } catch (error) {
    if (error instanceof RejectionError) {
      throw new ParallaxWriteValidationError(error.rule, error.message);
    }
    throw error;
  }
}

/** The per-unit-of-work concurrency strategy (m-unit-work strategy selection). */
export type Concurrency = "locking" | "optimistic";

/**
 * The per-unit-of-work observed-state map: `entity#pk → observed version | in_z`,
 * populated when a transaction-scoped find hydrates a row whose optimistic key the
 * unit of work tracks. For a VERSIONED entity the value is the observed `version`
 * NUMBER; for a Transaction-Time entity — which carries no
 * version column — it is the observed Transaction-Time start (`in_z`) wire string, the
 * version analogue an optimistic close gates on (m-temporal-read/m-opt-lock). A gated write reads the
 * observed value from it (the gate bind in optimistic mode; the base for the
 * framework-computed advance, for versioned entities). Keyed dialect-free so a
 * `bigint` pk and its numeric literal collide on the same normalized key.
 */
export type ObservedVersions = Map<string, number | string>;

/** The observed-version map key for one row (`Entity#<pk>`). */
export function observedKey(entityName: string, pk: unknown): string {
  return `${entityName}#${String(pk)}`;
}

/** A named attribute assignment (`Balance.value.set(150)`), spec §4. */
export interface Assignment {
  /** The attribute NAME (DSL property name) the assignment targets. */
  readonly attr: string;
  /** The value to write (a managed scalar or its neutral form). */
  readonly value: unknown;
}

/** Options accepted by `update` (spec §4): the explicit assignment array. */
export interface UpdateOptions {
  readonly set: readonly Assignment[];
}

/**
 * The shared physical shape of a versioned `UPDATE`: the {@link VersionedTarget}
 * (table + pk column + version column) plus the quoted DOMAIN `set` columns and
 * their binds (the framework-owned version column dropped). Resolved once from the
 * assignments, then reused for one keyed update or per resolved row of a set-based
 * materialize (core ADR 0014), so both paths render identical statements.
 */
interface VersionedUpdateShape {
  readonly target: VersionedTarget;
  readonly setColumns: readonly string[];
  readonly domainBinds: readonly unknown[];
}

/** True when an entity chains milestones in Transaction Time. */
export function hasTransactionTime(entity: EntityMetadata): boolean {
  return entity.asOfAxes().some((axis) => axis.dimension === "transactionTime");
}

/** A buffered non-temporal insert awaiting the unit-of-work flush. */
interface BufferedInsert {
  readonly entity: EntityMetadata;
  readonly binds: readonly unknown[];
}

/**
 * The developer-runtime writer for one transaction. Non-temporal inserts buffer so
 * the unit of work flushes them set-based + FK-safe (m-unit-work); audit-only writes and
 * versioned updates issue their DML immediately (their observable contract is
 * per-statement). `flush()` runs at transaction commit; a dependent read forces an
 * insert flush first (read-your-own-writes, `m-unit-work-001`).
 */
export class TransactionWriter {
  private readonly insertBuffer: BufferedInsert[] = [];
  private roundTripCount = 0;

  constructor(
    private readonly database: ParallaxDatabase,
    private readonly dialect: Dialect,
    private readonly transactionInstant: string,
    /** The unit-of-work concurrency strategy (default `locking`, m-unit-work). */
    private readonly concurrency: Concurrency = "locking",
    /**
     * The per-unit-of-work observed-version map (`entity#pk → version`), shared
     * with the transaction's finders so a versioned update gates on / advances the
     * version a prior read hydrated. Defaults to a private map (a standalone
     * writer with no finders observes nothing, so a versioned update read-before-
     * writes).
     */
    private readonly observed: ObservedVersions = new Map(),
  ) {}

  /** The number of physical statements this writer has issued (round-trip proof). */
  get roundTrips(): number {
    return this.roundTripCount;
  }

  /**
   * `create`. A non-temporal entity buffers the insert for the FK-safe set-based
   * flush; an audit-only entity opens a milestone immediately (`insert … (in_z =
   * txInstant, out_z = infinity)`).
   */
  async create(entity: EntityMetadata, input: Record<string, unknown>): Promise<void> {
    // Refuse a structurally-invalid value-object document PRE-SQL (m-value-object
    // write validation) — before any bind is generated — so an invalid document
    // never reaches the unconstrained jsonb column (the rejected-write contract).
    assertValueObjectWrite(entity, input);
    const binds = this.insertBinds(entity, input);
    if (hasTransactionTime(entity)) {
      const [sql] = auditWriteStatements("insert", this.writeTargetFor(entity));
      await this.exec(sql as string, binds);
      return;
    }
    this.insertBuffer.push({ entity, binds });
  }

  /** Force any buffered inserts to flush (before a dependent read, spec §4). */
  async flush(): Promise<void> {
    await this.flushInserts();
  }

  /**
   * `update`. An audit-only entity chains milestones (close + new current row); a
   * VERSIONED entity advances its framework-owned version (gated in optimistic
   * mode, ungated in locking mode — throwing on a conflict / read-before-write,
   * m-opt-lock); a plain (non-versioned) entity issues one keyed UPDATE.
   */
  async update(
    entity: EntityMetadata,
    predicate: Predicate,
    options: UpdateOptions,
  ): Promise<WriteResult> {
    await this.flushInserts();
    if (hasTransactionTime(entity)) {
      return this.auditUpdate(entity, predicate, options);
    }
    const version = entity.versionAttribute();
    if (version !== undefined) {
      return this.versionedEntityUpdate(entity, predicate, options, version);
    }
    return this.plainUpdate(entity, predicate, options);
  }

  /**
   * A KEYED versioned-entity `update` (m-opt-lock, core ADR 0013). The version is
   * FRAMEWORK-OWNED: the write advances it in BOTH modes, and in `optimistic` mode also gates
   * on the version the unit of work OBSERVED for the row (a prior transaction-scoped
   * find populated the observed map). Three rules:
   *
   *  - a `set` that changes NO domain attribute issues no DML (`m-opt-lock-001`);
   *  - an unobserved row is a read-before-write error (there is no observed version
   *    to gate on or advance from);
   *  - `optimistic` mode emits the gated form and throws `ParallaxOptimisticLockError`
   *    on a 0-row conflict (`m-opt-lock-005`); `locking` mode emits the ungated version-
   *    advancing form (`m-opt-lock-002`). The advanced version (`observed + 1`) is never
   *    caller-supplied.
   */
  private async versionedEntityUpdate(
    entity: EntityMetadata,
    predicate: Predicate,
    options: UpdateOptions,
    version: NormalizedAttribute,
  ): Promise<WriteResult> {
    const shape = this.versionedShape(entity, options, version);
    // A no-op update (no domain attribute changes) issues NO DML (m-opt-lock).
    if (shape === undefined) {
      return { affectedRows: 0 };
    }
    const affectedRows = await this.emitVersionedRowUpdate(
      entity,
      shape,
      this.pkLiteralOf(entity, predicate),
    );
    return { affectedRows };
  }

  /**
   * A SET-BASED versioned-entity `update` (m-opt-lock materialize, core ADR 0014). A versioned
   * set-based update has NO set-based template — the optimistic gate binds a
   * per-row observed version, so a single statement cannot carry it. The caller
   * (`TransactionEntity.update`) has already resolved the predicate to rows through
   * the OBSERVING finder — which recorded each row's observed version and, in
   * `locking` mode, took the m-read-lock shared lock — and passes their primary keys here;
   * this emits ONE keyed per-object `UPDATE` per resolved pk (gated in optimistic
   * mode, ungated version-advancing in locking mode), advancing the observed version
   * per row. A no-op `set` issues no DML; a mid-batch optimistic conflict (a
   * per-object gated update affecting 0 rows) throws `ParallaxOptimisticLockError`.
   * Reuses the same per-row emitter the keyed update uses (no drift). Non-versioned
   * entities never reach here — they keep the readless batched path (core ADR 0014).
   */
  async versionedSetUpdate(
    entity: EntityMetadata,
    pks: readonly unknown[],
    options: UpdateOptions,
  ): Promise<WriteResult> {
    await this.flushInserts();
    const version = entity.versionAttribute();
    if (version === undefined) {
      throw new Error(`'${entity.name}' is not a versioned entity — no set-based materialize`);
    }
    const shape = this.versionedShape(entity, options, version);
    if (shape === undefined) {
      return { affectedRows: 0 };
    }
    let affectedRows = 0;
    for (const pkLiteral of pks) {
      affectedRows += await this.emitVersionedRowUpdate(entity, shape, pkLiteral);
    }
    return { affectedRows };
  }

  /**
   * Resolve the shared versioned-update shape — the physical {@link VersionedTarget},
   * the quoted DOMAIN `set` columns, and their binds — dropping the framework-owned
   * version column (a caller assignment to it is ignored, m-opt-lock). Returns `undefined`
   * when the `set` changes no domain attribute (a no-op update — the caller issues no
   * DML). Shared by the keyed update and the set-based materialize.
   */
  private versionedShape(
    entity: EntityMetadata,
    options: UpdateOptions,
    version: NormalizedAttribute,
  ): VersionedUpdateShape | undefined {
    const domain = options.set.filter((a) => a.attr !== version.name);
    if (domain.length === 0) {
      return undefined;
    }
    const target: VersionedTarget = {
      table: this.quote(entity.table),
      pkColumn: this.quote(pkColumn(entity)),
      versionColumn: this.quote(version.column),
    };
    const resolved = domain.map((assignment) => ({
      assignment,
      attr: entity.attributeByName(assignment.attr),
    }));
    const setColumns = resolved.map(({ attr }) => this.quote(attr.column));
    const domainBinds = resolved.map(({ assignment, attr }) =>
      this.bindAttribute(attr, assignment.value),
    );
    return { target, setColumns, domainBinds };
  }

  /**
   * Emit ONE keyed versioned `UPDATE` for a single resolved primary key and return
   * its affected-row count, advancing the framework-owned observed version. Gates on
   * the observed version in `optimistic` mode (a 0-row conflict throws
   * `ParallaxOptimisticLockError`, `m-opt-lock-005`); emits the ungated version-advancing form
   * in `locking` mode (`m-opt-lock-002`). An unobserved row is a read-before-write error (m-opt-lock).
   * The single per-row emitter both the keyed update and the set-based materialize
   * (core ADR 0014) share, so the two paths never drift.
   */
  private async emitVersionedRowUpdate(
    entity: EntityMetadata,
    shape: VersionedUpdateShape,
    pkLiteral: unknown,
  ): Promise<number> {
    const key = observedKey(entity.name, pkLiteral);
    const observed = this.observed.get(key);
    if (observed === undefined) {
      throw new ParallaxReadBeforeWriteError(entity.name);
    }
    // A versioned entity records a numeric version (a temporal in_z string never
    // reaches this per-object emitter — the composition rule forbids a versioned
    // temporal entity, m-descriptor/m-opt-lock).
    if (typeof observed !== "number") {
      throw new Error(`observed value for '${key}' is not a version number`);
    }
    const observedVersion = observed;
    const newVersion = observedVersion + 1;
    const pk = this.bindPkLiteral(entity, pkLiteral);
    if (this.concurrency === "optimistic") {
      // Gate on the observed version; a concurrent writer that advanced it first
      // makes the gate match 0 rows (the conflict signal).
      const sql = versionedUpdate(shape.target, shape.setColumns);
      const affectedRows = await this.exec(sql, [
        ...shape.domainBinds,
        newVersion,
        pk,
        observedVersion,
      ]);
      if (classifyOutcome(affectedRows) === "conflict") {
        throw new ParallaxOptimisticLockError(entity.name);
      }
      this.observed.set(key, newVersion);
      return affectedRows;
    }
    // Locking mode: the m-read-lock shared read lock makes the write correct, so the version
    // advances WITHOUT a gate (the `m-detach-002` / `m-opt-lock-002` shape).
    const sql = versionAdvancingUpdate(shape.target, shape.setColumns);
    const affectedRows = await this.exec(sql, [...shape.domainBinds, newVersion, pk]);
    this.observed.set(key, newVersion);
    return affectedRows;
  }

  /** `terminate` (audit-only): close the current milestone, insert nothing. */
  async terminate(entity: EntityMetadata, predicate: Predicate): Promise<WriteResult> {
    await this.flushInserts();
    if (!hasTransactionTime(entity)) {
      throw new Error(`'terminate' is a temporal removal; '${entity.name}' is non-temporal`);
    }
    const gated = this.concurrency === "optimistic";
    const [closeSql] = auditWriteStatements("terminate", this.writeTargetFor(entity), { gated });
    const affectedRows = await this.closeMilestone(
      entity,
      closeSql as string,
      this.pkLiteralOf(entity, predicate),
      gated,
    );
    return { affectedRows };
  }

  /** `delete` (physical, non-temporal entities only). */
  async delete(entity: EntityMetadata, predicate: Predicate): Promise<WriteResult> {
    await this.flushInserts();
    if (hasTransactionTime(entity)) {
      throw new Error(
        `'delete' is physical; use 'terminate' for the audit entity '${entity.name}'`,
      );
    }
    const sql =
      `delete from ${this.quote(entity.table)} ` + `where ${this.quote(pkColumn(entity))} = ?`;
    const affectedRows = await this.exec(sql, [this.pkValue(entity, predicate)]);
    return { affectedRows };
  }

  // --- internals ------------------------------------------------------------

  /** Flush buffered non-temporal inserts through the m-unit-work combine planner (FK-safe). */
  private async flushInserts(): Promise<void> {
    if (this.insertBuffer.length === 0) {
      return;
    }
    const buffered = [...this.insertBuffer];
    this.insertBuffer.length = 0;
    // Group per entity (one multi-row INSERT each), remembering first-appearance
    // order (the tiebreaker among FK-independent entities).
    const order: EntityMetadata[] = [];
    const rowsByEntity = new Map<string, unknown[][]>();
    for (const { entity, binds } of buffered) {
      const identity = entityIdentity(entity);
      const bucket = rowsByEntity.get(identity);
      if (bucket === undefined) {
        rowsByEntity.set(identity, [[...binds]]);
        order.push(entity);
      } else {
        bucket.push([...binds]);
      }
    }
    // `combineWrites` flushes steps in DECLARED order — it does NOT infer FK
    // dependencies (uow.ts) — so a referenced parent's insert must be handed to it
    // BEFORE a dependent child's. Topologically sort the grouped entities so a
    // parent precedes a child that points at it (`m-unit-work-003`), regardless of the order
    // the developer authored the `create` calls in.
    const sorted = fkSortInsertOrder(order);
    const steps: WriteStep[] = sorted.map((entity) => ({
      mutation: "insert",
      target: {
        table: this.quote(entity.table),
        columns: this.quotedColumnOrder(entity),
        pkColumn: this.quote(pkColumn(entity)),
      },
      statements: 1,
      binds: [(rowsByEntity.get(entityIdentity(entity)) ?? []).flat()],
    }));
    for (const planned of combineWrites(steps)) {
      await this.exec(planned.sql, planned.binds);
    }
  }

  /**
   * An audit-only `update`: close the current row, then chain a new current row. In
   * OPTIMISTIC mode the close gates on the observed Transaction-Time start (`in_z`), so a
   * concurrent supersession is caught (m-opt-lock); a zero-row close raises BEFORE the
   * chained insert in any mode (never silent).
   */
  private async auditUpdate(
    entity: EntityMetadata,
    predicate: Predicate,
    options: UpdateOptions,
  ): Promise<WriteResult> {
    const gated = this.concurrency === "optimistic";
    const [closeSql, insertSql] = auditWriteStatements("update", this.writeTargetFor(entity), {
      gated,
    });
    const pkLiteral = this.pkLiteralOf(entity, predicate);
    // Read the row being superseded so unchanged domain columns carry forward.
    const current = await this.currentRow(entity, predicate);
    const affectedRows = await this.closeMilestone(entity, closeSql as string, pkLiteral, gated);
    await this.exec(insertSql as string, this.chainedBinds(entity, current, options));
    return { affectedRows };
  }

  /**
   * Execute an audit milestone CLOSE and return its affected-row count, enforcing
   * the m-temporal-read/m-opt-lock conflict contract:
   *
   *  - OPTIMISTIC mode (`gated`) binds the observed Transaction-Time start (`in_z`) as the
   *    optimistic gate — a temporal entity carries no version column, so the observed
   *    `in_z` is the version analogue. An unobserved row is a read-before-write error
   *    (m-opt-lock); a zero-row close (a concurrent writer superseded the milestone, leaving
   *    a fresh `in_z`) throws `ParallaxOptimisticLockError` (retriable under the
   *    phase-4 flag).
   *  - LOCKING mode closes UNGATED (the m-read-lock shared read lock makes it correct), but a
   *    zero-row close still raises a DISTINCT non-retriable `ParallaxTemporalCloseError`
   *    (a stale/consistency error). A zero-row close is never silent in ANY mode.
   */
  private async closeMilestone(
    entity: EntityMetadata,
    closeSql: string,
    pkLiteral: unknown,
    gated: boolean,
  ): Promise<number> {
    const txStart = requireTxStart(entity);
    const txEnd = requireTxEnd(entity);
    const pk = this.bindPkLiteral(entity, pkLiteral);
    const closeAt = this.bindAttribute(txEnd, this.transactionInstant);
    const openUpper = this.bindAttribute(txEnd, INFINITY);
    let binds: readonly unknown[];
    if (gated) {
      const observedTxStart = this.observed.get(observedKey(entity.name, pkLiteral));
      if (observedTxStart === undefined) {
        throw new ParallaxReadBeforeWriteError(entity.name);
      }
      binds = [closeAt, pk, openUpper, this.bindAttribute(txStart, observedTxStart)];
    } else {
      binds = [closeAt, pk, openUpper];
    }
    const affectedRows = await this.exec(closeSql, binds);
    if (affectedRows === 0) {
      throw gated
        ? new ParallaxOptimisticLockError(entity.name)
        : new ParallaxTemporalCloseError(entity.name);
    }
    return affectedRows;
  }

  /** The current (open, `out_z = infinity`) row of an audit entity, by pk. */
  private async currentRow(
    entity: EntityMetadata,
    predicate: Predicate,
  ): Promise<Record<string, unknown>> {
    const transactionTime = entity.asOfAxes().find((axis) => axis.dimension === "transactionTime");
    const endColumn = transactionTime?.endColumn;
    const cols = entity
      .attributes()
      .map((a) => this.quote(a.column))
      .join(", ");
    const sql =
      `select ${cols} from ${this.quote(entity.table)} ` +
      `where ${this.quote(pkColumn(entity))} = ?` +
      (endColumn ? ` and ${this.quote(endColumn)} = ?` : "");
    const binds = endColumn
      ? [this.pkValue(entity, predicate), this.bindAttribute(requireTxEnd(entity), INFINITY)]
      : [this.pkValue(entity, predicate)];
    const rows = await this.database.execute(sql, binds);
    this.roundTripCount += 1; // the carry-forward read is a real round trip
    return (rows[0] as Record<string, unknown> | undefined) ?? {};
  }

  /**
   * The chained-insert binds for a Transaction-Time update: the superseded row's
   * domain columns, with the assignments applied, `in_z = transactionInstant`, `out_z =
   * infinity` (never a partial milestone).
   */
  private chainedBinds(
    entity: EntityMetadata,
    current: Record<string, unknown>,
    options: UpdateOptions,
  ): readonly unknown[] {
    const transactionTime = entity.asOfAxes().find((axis) => axis.dimension === "transactionTime");
    const assignments = new Map(options.set.map((a) => [a.attr, a.value]));
    return entity.attributes().map((attr) => {
      if (assignments.has(attr.name)) {
        return this.bindAttribute(attr, assignments.get(attr.name));
      }
      if (transactionTime !== undefined && attr.column === transactionTime.startColumn) {
        return this.bindAttribute(attr, this.transactionInstant);
      }
      if (transactionTime !== undefined && attr.column === transactionTime.endColumn) {
        return this.bindAttribute(attr, INFINITY);
      }
      // Carry the superseded row's value forward (already managed by the port).
      return this.bindAttribute(attr, current[attr.column]);
    });
  }

  /**
   * A plain non-temporal `update`: one keyed UPDATE for the selected pk that
   * applies EVERY authored assignment (`set col1 = ?, col2 = ?, … where pk = ?`),
   * binding the values in declaration order followed by the pk (spec §4: `update`
   * applies the explicit assignment array). An empty `set` is a no-op.
   */
  private async plainUpdate(
    entity: EntityMetadata,
    predicate: Predicate,
    options: UpdateOptions,
  ): Promise<WriteResult> {
    if (options.set.length === 0) {
      return { affectedRows: 0 };
    }
    const resolved = options.set.map((assignment) => ({
      assignment,
      attr: entity.attributeByName(assignment.attr),
    }));
    const setClause = resolved.map(({ attr }) => `${this.quote(attr.column)} = ?`).join(", ");
    const sql =
      `update ${this.quote(entity.table)} set ${setClause} ` +
      `where ${this.quote(pkColumn(entity))} = ?`;
    const affectedRows = await this.exec(sql, [
      ...resolved.map(({ assignment, attr }) => this.bindAttribute(attr, assignment.value)),
      this.pkValue(entity, predicate),
    ]);
    return { affectedRows };
  }

  /** The raw primary-key LITERAL a pk-equality write predicate selects (pre-wire). */
  private pkLiteralOf(entity: EntityMetadata, predicate: Predicate): unknown {
    const pkName = entity.primaryKey()[0]?.name;
    const literal = pkLiteral(predicate.toOperation(), pkName);
    if (literal === undefined) {
      throw new Error(
        `a write on '${entity.name}' must select one row by its primary key equality`,
      );
    }
    return literal;
  }

  /** The single primary-key VALUE a pk-equality write predicate selects, normalized for the driver. */
  private pkValue(entity: EntityMetadata, predicate: Predicate): unknown {
    return this.bindPkLiteral(entity, this.pkLiteralOf(entity, predicate));
  }

  /**
   * Execute a set-based DML statement and return its affected-row count. The port
   * reports the native count through `executeWrite`, keeping emitted DML dialect
   * neutral. Every issued statement increments the round-trip count.
   */
  private async exec(sql: string, binds: readonly unknown[]): Promise<number> {
    const affectedRows = await this.database.executeWrite(sql, binds);
    this.roundTripCount += 1;
    return affectedRows;
  }

  /**
   * The ordered positional insert binds for a named input, in descriptor attribute
   * order. A missing attribute binds `null`; an audit entity's interval columns
   * default to `[transactionInstant, infinity)` when the caller does not supply them.
   */
  private insertBinds(entity: EntityMetadata, input: Record<string, unknown>): readonly unknown[] {
    const transactionTime = entity.asOfAxes().find((axis) => axis.dimension === "transactionTime");
    const attributeBinds = entity.attributes().map((attr) => {
      if (attr.name in input) {
        return this.bindAttribute(attr, input[attr.name]);
      }
      if (transactionTime !== undefined && attr.column === transactionTime.startColumn) {
        return this.bindAttribute(attr, this.transactionInstant);
      }
      if (transactionTime !== undefined && attr.column === transactionTime.endColumn) {
        return this.bindAttribute(attr, INFINITY);
      }
      return this.bindAttribute(attr, null);
    });
    // A top-level value object binds its WHOLE document atomically in columnOrder
    // position (m-value-object) — after the scalar attributes, matching
    // `quotedColumnOrder`. The object / array / null rides through to the dialect's
    // structured-document bind (jsonb / json); an omitted value object binds null.
    const valueObjectBinds = entity
      .valueObjects()
      .map((vo) => (vo.name in input ? (input[vo.name] ?? null) : null));
    return [...attributeBinds, ...valueObjectBinds];
  }

  /** Normalize one attribute value for the injected dialect's driver boundary. */
  private bindAttribute(attr: NormalizedAttribute, value: unknown): unknown {
    return this.dialect.bindValue(attr.type, value);
  }

  /** Normalize one primary-key literal for the injected dialect's driver boundary. */
  private bindPkLiteral(entity: EntityMetadata, pkLiteral: unknown): unknown {
    const pk = entity.primaryKey()[0];
    if (pk === undefined) {
      throw new Error(`entity '${entity.name}' has no primary key for a write`);
    }
    return this.bindAttribute(pk, pkLiteral);
  }

  /** Quote one physical identifier through the injected m-dialect dialect. */
  private quote(name: string): string {
    return this.dialect.quoteIdentifier(name);
  }

  /** The quoted columns of an entity in descriptor `columnOrder`, via the injected dialect. */
  private quotedColumnOrder(entity: EntityMetadata): readonly string[] {
    return quotedColumnOrder(entity, this.dialect);
  }

  /** Resolve this entity's audit write target using the injected dialect. */
  private writeTargetFor(entity: EntityMetadata): WriteTarget {
    return writeTargetFor(entity, this.dialect);
  }
}

/**
 * Order the grouped insert entities FK-safe: a referenced parent precedes a
 * dependent child (`m-unit-work-003`). A `many-to-one` relationship is the FK-holding side,
 * so an entity that declares one depends on its join target — but only when
 * that parent is ALSO in this insert set (an out-of-set reference is already
 * present, so it imposes no ordering here). The sort is STABLE: among entities
 * with no in-set dependency it preserves first-appearance order (the tiebreak),
 * matching `combineWrites`'s declared-order flush. A dependency cycle (which a
 * self-consistent model has none of) falls back to first-appearance order.
 */
function fkSortInsertOrder(order: readonly EntityMetadata[]): readonly EntityMetadata[] {
  const inSet = new Set(order.map(entityIdentity));
  // Each entity's in-set parents (the join target of its `many-to-one` relations).
  const parentsOf = new Map<string, Set<string>>();
  for (const entity of order) {
    const parents = new Set<string>();
    for (const rel of entity.relationships()) {
      if (rel.cardinality === "many-to-one" && inSet.has(rel.join.target.entity)) {
        parents.add(rel.join.target.entity);
      }
    }
    parentsOf.set(entityIdentity(entity), parents);
  }
  const emitted = new Set<string>();
  const result: EntityMetadata[] = [];
  // Repeatedly emit, in first-appearance order, the first not-yet-emitted entity
  // all of whose in-set parents are already emitted (a stable topological order).
  while (result.length < order.length) {
    const next = order.find(
      (entity) =>
        !emitted.has(entityIdentity(entity)) &&
        [...(parentsOf.get(entityIdentity(entity)) ?? [])].every((parent) => emitted.has(parent)),
    );
    if (next === undefined) {
      // A dependency cycle: fall back to first-appearance order for the rest.
      for (const entity of order) {
        const identity = entityIdentity(entity);
        if (!emitted.has(identity)) {
          emitted.add(identity);
          result.push(entity);
        }
      }
      break;
    }
    emitted.add(entityIdentity(next));
    result.push(next);
  }
  return result;
}

/** The canonical entity identity used by relationship metadata and model-wide maps. */
function entityIdentity(entity: EntityMetadata): string {
  return entity.namespace === undefined ? entity.name : `${entity.namespace}.${entity.name}`;
}

/**
 * The quoted physical columns of an entity in descriptor `columnOrder`, quoted
 * through the injected dialect. The single source of the insert / audit-milestone
 * column list — both the insert-flush path (`quotedColumnOrder` method) and the
 * audit path ({@link writeTargetFor}) route through here, so a change to how insert
 * columns are ordered or quoted lands in one place.
 */
function quotedColumnOrder(entity: EntityMetadata, dialect: Dialect): readonly string[] {
  return columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
    // A top-level value object contributes one structured-document column in
    // columnOrder position (m-value-object) — the whole document binds atomically.
    valueObjects: entity.valueObjects().map((vo) => ({ column: vo.column, nullable: vo.nullable })),
  }).map((column) => dialect.quoteIdentifier(column));
}

/** The single primary-key physical column name of an entity. */
function pkColumn(entity: EntityMetadata): string {
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a write`);
  }
  return pk.column;
}

/** The Transaction-Time start attribute (`in_z`) required by temporal writes. */
function requireTxStart(entity: EntityMetadata): NormalizedAttribute {
  const attr = entity.txStartAttribute();
  if (attr === undefined) {
    throw new Error(`entity '${entity.name}' has no Transaction-Time start attribute`);
  }
  return attr;
}

/** The Transaction-Time end attribute (`out_z`) required by temporal writes. */
function requireTxEnd(entity: EntityMetadata): NormalizedAttribute {
  const attr = entity.txEndAttribute();
  if (attr === undefined) {
    throw new Error(`entity '${entity.name}' has no Transaction-Time end attribute`);
  }
  return attr;
}

/**
 * Resolve an entity's audit {@link WriteTarget} (table, columns, pk, out_z, in_z).
 * `txStartColumn` (`in_z`) is the optimistic gate; `txEndColumn` (`out_z`) is set
 * and keyed by every close.
 */
function writeTargetFor(entity: EntityMetadata, dialect: Dialect): WriteTarget {
  const transactionTime = entity.asOfAxes().find((axis) => axis.dimension === "transactionTime");
  return {
    table: dialect.quoteIdentifier(entity.table),
    columns: quotedColumnOrder(entity, dialect),
    pkColumn: dialect.quoteIdentifier(pkColumn(entity)),
    ...(transactionTime === undefined
      ? {}
      : {
          txEndColumn: dialect.quoteIdentifier(transactionTime.endColumn),
          txStartColumn: dialect.quoteIdentifier(transactionTime.startColumn),
        }),
  };
}

/**
 * Whether a write predicate selects exactly one row by PRIMARY-KEY equality
 * (`Account.id.eq(1)`). A versioned `update` on such a predicate is a KEYED update
 * (the caller observed the row first, then updates it by pk); a versioned update on
 * ANY OTHER predicate — a range (`balance < ?`), a non-pk equality, `all` — has no
 * single pk to key on and MATERIALIZES instead: `TransactionEntity.update` resolves
 * the predicate to rows through the observing finder, then updates per object (m-opt-lock,
 * core ADR 0014). A non-versioned entity keeps its readless batched path either way.
 */
export function isPkEqualityPredicate(entity: EntityMetadata, predicate: Predicate): boolean {
  const pkName = entity.primaryKey()[0]?.name;
  return pkLiteral(predicate.toOperation(), pkName) !== undefined;
}

/**
 * Extract the primary-key literal a pk-equality predicate carries (the bare `eq`
 * the API Conformance Suite write predicates use); `undefined` for anything else.
 */
function pkLiteral(operation: Operation, pkName: string | undefined): unknown {
  const eq = (operation as { eq?: { attr?: string; value?: unknown } }).eq;
  if (eq === undefined) {
    return undefined;
  }
  if (pkName !== undefined && typeof eq.attr === "string" && !eq.attr.endsWith(`.${pkName}`)) {
    return undefined;
  }
  return eq.value;
}

/** Re-exported managed carriers so the API Conformance Suite can author managed write inputs. */
export { ParallaxDecimal, Temporal };
