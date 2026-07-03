/**
 * The developer-runtime **write surface** (spec §4.1), executed at the composition
 * root over the injected `ParallaxDatabase`.
 *
 * The typed `tx.<entity>.create / update / terminate / delete` methods let an
 * application author idiomatic, NAMED writes; this module lowers each to canonical
 * DML by reusing the pure M7 / M8 / M10 generators (no reinvented DML, no grader
 * code):
 *
 *  - **non-temporal `create`** buffers an insert; the unit of work flushes buffered
 *    inserts through the M8 `combineWrites` planner — same-entity inserts collapse
 *    to one multi-row `INSERT`, a referenced parent's inserts precede a child's
 *    (`0604` / `0612`);
 *  - **non-temporal `update`** on a VERSIONED entity always advances the framework-
 *    owned version (M10, ADR 0029): in `optimistic` mode it issues the gated M10
 *    `UPDATE` (gate on the version the unit of work OBSERVED, advance it) and
 *    classifies the affected count (`0703` / `0704` / `0708`); in the default
 *    `locking` mode it issues the ungated version-advancing `UPDATE` (`0611`). Either
 *    way an unobserved row read-before-writes and a no-op `set` issues no DML
 *    (`0609`). On a NON-versioned entity it is a plain keyed `UPDATE`, one per
 *    selected key (`0604` / `0613` on the non-versioned `Wallet`);
 *  - **audit-only (`unitemporal-processing`) writes** chain milestones through the
 *    M7 `auditWriteStatements` generator: `create` opens `[processingInstant,
 *    infinity)`, `update` closes the current row and chains a new one carrying the
 *    prior business columns with the assignments applied, `terminate` closes only
 *    (`0510` / `0511` / `0512`).
 *
 * Named inputs map to canonical `columnOrder` binds via the entity metamodel, and
 * scalar values render to the neutral WIRE form the driver binds (the same
 * `toWire` the adapter uses). Processing instants come ONLY from the transaction
 * clock (spec §4.1) — never a per-operation option — so production code cannot
 * rewrite audit history.
 *
 * The `@parallax/db` port returns rows, not an affected-row count, so a set-based
 * write runs with a trailing `returning 1`; `rows.length` is then the affected
 * count (spec §4 `WriteResult.affectedRows`). This is the idiomatic way an ORM
 * reads the affected count through a rows-only port and stays driver-agnostic.
 */

import { auditWriteStatements, type WriteTarget } from "@parallax/bitemporal";
import { INFINITY, ParallaxDecimal, Temporal, toWire } from "@parallax/core";
import type { ParallaxDatabase } from "@parallax/db";
import { columnOrder, quoteIdentifier } from "@parallax/dialect";
import {
  classifyOutcome,
  type VersionedTarget,
  versionAdvancingUpdate,
  versionedUpdate,
} from "@parallax/locking";
import type { EntityMetadata, NormalizedAttribute } from "@parallax/metamodel";
import type { Operation } from "@parallax/operation";
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
 * Thrown when a versioned entity's row is updated WITHOUT the unit of work having
 * observed it first (M10 read-before-write). Optimistic-lock version values are
 * framework-owned (ADR 0029): the gate binds — and the advance is computed from —
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

/** The per-unit-of-work concurrency strategy (M8 strategy selection). */
export type Concurrency = "locking" | "optimistic";

/**
 * The per-unit-of-work observed-state map: `entity#pk → observed version`,
 * populated when a transaction-scoped find hydrates a versioned row. A versioned
 * update reads the observed version from it (the gate bind in optimistic mode; the
 * base for the framework-computed advance in both modes). Keyed dialect-free so a
 * `bigint` pk and its numeric literal collide on the same normalized key.
 */
export type ObservedVersions = Map<string, number>;

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
 * materialize (ADR 0032), so both paths render identical statements.
 */
interface VersionedUpdateShape {
  readonly target: VersionedTarget;
  readonly setColumns: readonly string[];
  readonly domainBinds: readonly unknown[];
}

/** True when an entity chains audit milestones (declares a processing as-of axis). */
export function isAuditOnly(entity: EntityMetadata): boolean {
  return entity.asOfAttributes().some((axis) => axis.axis === "processing");
}

/** A buffered non-temporal insert awaiting the unit-of-work flush. */
interface BufferedInsert {
  readonly entity: EntityMetadata;
  readonly binds: readonly unknown[];
}

/**
 * The developer-runtime writer for one transaction. Non-temporal inserts buffer so
 * the unit of work flushes them set-based + FK-safe (M8); audit-only writes and
 * versioned updates issue their DML immediately (their observable contract is
 * per-statement). `flush()` runs at transaction commit; a dependent read forces an
 * insert flush first (read-your-own-writes, `0607`).
 */
export class TransactionWriter {
  private readonly insertBuffer: BufferedInsert[] = [];
  private roundTripCount = 0;

  constructor(
    private readonly database: ParallaxDatabase,
    private readonly processingInstant: string,
    /** The unit-of-work concurrency strategy (default `locking`, M8). */
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
    const binds = insertBinds(entity, input, this.processingInstant);
    if (isAuditOnly(entity)) {
      const [sql] = auditWriteStatements("insert", writeTargetFor(entity));
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
   * M10); a plain (non-versioned) entity issues one keyed UPDATE.
   */
  async update(
    entity: EntityMetadata,
    predicate: Predicate,
    options: UpdateOptions,
  ): Promise<WriteResult> {
    await this.flushInserts();
    if (isAuditOnly(entity)) {
      return this.auditUpdate(entity, predicate, options);
    }
    const version = entity.versionAttribute();
    if (version !== undefined) {
      return this.versionedEntityUpdate(entity, predicate, options, version);
    }
    return this.plainUpdate(entity, predicate, options);
  }

  /**
   * A KEYED versioned-entity `update` (M10). The version is FRAMEWORK-OWNED (ADR
   * 0029): the write advances it in BOTH modes, and in `optimistic` mode also gates
   * on the version the unit of work OBSERVED for the row (a prior transaction-scoped
   * find populated the observed map). Three rules:
   *
   *  - a `set` that changes NO domain attribute issues no DML (`0609`);
   *  - an unobserved row is a read-before-write error (there is no observed version
   *    to gate on or advance from);
   *  - `optimistic` mode emits the gated form and throws `ParallaxOptimisticLockError`
   *    on a 0-row conflict (`0703`); `locking` mode emits the ungated version-
   *    advancing form (`0611`). The advanced version (`observed + 1`) is never
   *    caller-supplied.
   */
  private async versionedEntityUpdate(
    entity: EntityMetadata,
    predicate: Predicate,
    options: UpdateOptions,
    version: NormalizedAttribute,
  ): Promise<WriteResult> {
    const shape = this.versionedShape(entity, options, version);
    // A no-op update (no domain attribute changes) issues NO DML (M10).
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
   * A SET-BASED versioned-entity `update` (M10 materialize, ADR 0032). A versioned
   * set-based update has NO set-based template — the optimistic gate binds a
   * per-row observed version, so a single statement cannot carry it. The caller
   * (`TransactionEntity.update`) has already resolved the predicate to rows through
   * the OBSERVING finder — which recorded each row's observed version and, in
   * `locking` mode, took the M8 shared lock — and passes their primary keys here;
   * this emits ONE keyed per-object `UPDATE` per resolved pk (gated in optimistic
   * mode, ungated version-advancing in locking mode), advancing the observed version
   * per row. A no-op `set` issues no DML; a mid-batch optimistic conflict (a
   * per-object gated update affecting 0 rows) throws `ParallaxOptimisticLockError`.
   * Reuses the same per-row emitter the keyed update uses (no drift). Non-versioned
   * entities never reach here — they keep the readless batched path (ADR 0011).
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
   * version column (a caller assignment to it is ignored, M10). Returns `undefined`
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
      table: quoteIdentifier(entity.table),
      pkColumn: quoteIdentifier(pkColumn(entity)),
      versionColumn: quoteIdentifier(version.column),
    };
    const setColumns = domain.map((a) => quoteIdentifier(entity.attributeByName(a.attr).column));
    const domainBinds = domain.map((a) => bindValue(a.value));
    return { target, setColumns, domainBinds };
  }

  /**
   * Emit ONE keyed versioned `UPDATE` for a single resolved primary key and return
   * its affected-row count, advancing the framework-owned observed version. Gates on
   * the observed version in `optimistic` mode (a 0-row conflict throws
   * `ParallaxOptimisticLockError`, `0703`); emits the ungated version-advancing form
   * in `locking` mode (`0611`). An unobserved row is a read-before-write error (M10).
   * The single per-row emitter both the keyed update and the set-based materialize
   * (ADR 0032) share, so the two paths never drift.
   */
  private async emitVersionedRowUpdate(
    entity: EntityMetadata,
    shape: VersionedUpdateShape,
    pkLiteral: unknown,
  ): Promise<number> {
    const key = observedKey(entity.name, pkLiteral);
    const observedVersion = this.observed.get(key);
    if (observedVersion === undefined) {
      throw new ParallaxReadBeforeWriteError(entity.name);
    }
    const newVersion = observedVersion + 1;
    const pk = bindValue(pkLiteral);
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
    // Locking mode: the M8 shared read lock makes the write correct, so the version
    // advances WITHOUT a gate (the `0702` / `0611` shape).
    const sql = versionAdvancingUpdate(shape.target, shape.setColumns);
    const affectedRows = await this.exec(sql, [...shape.domainBinds, newVersion, pk]);
    this.observed.set(key, newVersion);
    return affectedRows;
  }

  /** `terminate` (audit-only): close the current milestone, insert nothing. */
  async terminate(entity: EntityMetadata, predicate: Predicate): Promise<WriteResult> {
    await this.flushInserts();
    if (!isAuditOnly(entity)) {
      throw new Error(`'terminate' is a temporal removal; '${entity.name}' is non-temporal`);
    }
    const [closeSql] = auditWriteStatements("terminate", writeTargetFor(entity));
    const affectedRows = await this.exec(closeSql as string, [
      this.processingInstant,
      this.pkValue(entity, predicate),
      INFINITY,
    ]);
    return { affectedRows };
  }

  /** `delete` (physical, non-temporal entities only). */
  async delete(entity: EntityMetadata, predicate: Predicate): Promise<WriteResult> {
    await this.flushInserts();
    if (isAuditOnly(entity)) {
      throw new Error(
        `'delete' is physical; use 'terminate' for the audit entity '${entity.name}'`,
      );
    }
    const sql =
      `delete from ${quoteIdentifier(entity.table)} ` +
      `where ${quoteIdentifier(pkColumn(entity))} = ?`;
    const affectedRows = await this.exec(sql, [this.pkValue(entity, predicate)]);
    return { affectedRows };
  }

  // --- internals ------------------------------------------------------------

  /** Flush buffered non-temporal inserts through the M8 combine planner (FK-safe). */
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
      const bucket = rowsByEntity.get(entity.name);
      if (bucket === undefined) {
        rowsByEntity.set(entity.name, [[...binds]]);
        order.push(entity);
      } else {
        bucket.push([...binds]);
      }
    }
    // `combineWrites` flushes steps in DECLARED order — it does NOT infer FK
    // dependencies (uow.ts) — so a referenced parent's insert must be handed to it
    // BEFORE a dependent child's. Topologically sort the grouped entities so a
    // parent precedes a child that points at it (`0612`), regardless of the order
    // the developer authored the `create` calls in.
    const sorted = fkSortInsertOrder(order);
    const steps: WriteStep[] = sorted.map((entity) => ({
      mutation: "insert",
      target: {
        table: quoteIdentifier(entity.table),
        columns: quotedColumnOrder(entity),
        pkColumn: quoteIdentifier(pkColumn(entity)),
      },
      statements: 1,
      binds: [(rowsByEntity.get(entity.name) ?? []).flat()],
    }));
    for (const planned of combineWrites(steps)) {
      await this.exec(planned.sql, planned.binds);
    }
  }

  /** An audit-only `update`: close the current row, then chain a new current row. */
  private async auditUpdate(
    entity: EntityMetadata,
    predicate: Predicate,
    options: UpdateOptions,
  ): Promise<WriteResult> {
    const [closeSql, insertSql] = auditWriteStatements("update", writeTargetFor(entity));
    const pk = this.pkValue(entity, predicate);
    // Read the row being superseded so unchanged business columns carry forward.
    const current = await this.currentRow(entity, predicate);
    const affectedRows = await this.exec(closeSql as string, [
      this.processingInstant,
      pk,
      INFINITY,
    ]);
    await this.exec(insertSql as string, this.chainedBinds(entity, current, options));
    return { affectedRows };
  }

  /** The current (open, `out_z = infinity`) row of an audit entity, by pk. */
  private async currentRow(
    entity: EntityMetadata,
    predicate: Predicate,
  ): Promise<Record<string, unknown>> {
    const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
    const toCol = processing?.toColumn;
    const cols = entity
      .attributes()
      .map((a) => quoteIdentifier(a.column))
      .join(", ");
    const sql =
      `select ${cols} from ${quoteIdentifier(entity.table)} ` +
      `where ${quoteIdentifier(pkColumn(entity))} = ?` +
      (toCol ? ` and ${quoteIdentifier(toCol)} = ?` : "");
    const binds = toCol
      ? [this.pkValue(entity, predicate), INFINITY]
      : [this.pkValue(entity, predicate)];
    const rows = await this.database.execute(sql, binds);
    this.roundTripCount += 1; // the carry-forward read is a real round trip
    return (rows[0] as Record<string, unknown> | undefined) ?? {};
  }

  /**
   * The chained-insert binds for an audit update: the superseded row's business
   * columns, with the assignments applied, `in_z = processingInstant`, `out_z =
   * infinity` (never a partial milestone).
   */
  private chainedBinds(
    entity: EntityMetadata,
    current: Record<string, unknown>,
    options: UpdateOptions,
  ): readonly unknown[] {
    const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
    const assignments = new Map(options.set.map((a) => [a.attr, a.value]));
    return entity.attributes().map((attr) => {
      if (assignments.has(attr.name)) {
        return bindValue(assignments.get(attr.name));
      }
      if (processing !== undefined && attr.column === processing.fromColumn) {
        return this.processingInstant;
      }
      if (processing !== undefined && attr.column === processing.toColumn) {
        return INFINITY;
      }
      // Carry the superseded row's value forward (already in wire form off the port).
      return bindValue(current[attr.column]);
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
    const setClause = options.set
      .map((a) => `${quoteIdentifier(entity.attributeByName(a.attr).column)} = ?`)
      .join(", ");
    const sql =
      `update ${quoteIdentifier(entity.table)} set ${setClause} ` +
      `where ${quoteIdentifier(pkColumn(entity))} = ?`;
    const affectedRows = await this.exec(sql, [
      ...options.set.map((a) => bindValue(a.value)),
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

  /** The single primary-key VALUE (wire form) a pk-equality write predicate selects. */
  private pkValue(entity: EntityMetadata, predicate: Predicate): unknown {
    return bindValue(this.pkLiteralOf(entity, predicate));
  }

  /**
   * Execute a set-based DML statement and return its affected-row count. The port
   * returns rows, not a count, so a trailing `returning 1` makes `rows.length` the
   * affected count (spec §4). Every issued statement increments the round-trip count.
   */
  private async exec(sql: string, binds: readonly unknown[]): Promise<number> {
    const rows = await this.database.execute(`${sql} returning 1`, binds);
    this.roundTripCount += 1;
    return rows.length;
  }
}

/** Render one named input value to the neutral WIRE form the driver binds. */
function bindValue(value: unknown): unknown {
  return toWire(value);
}

/**
 * Order the grouped insert entities FK-safe: a referenced parent precedes a
 * dependent child (`0612`). A `many-to-one` relationship is the FK-holding side,
 * so an entity that declares one depends on that `relatedEntity` — but only when
 * that parent is ALSO in this insert set (an out-of-set reference is already
 * present, so it imposes no ordering here). The sort is STABLE: among entities
 * with no in-set dependency it preserves first-appearance order (the tiebreak),
 * matching `combineWrites`'s declared-order flush. A dependency cycle (which a
 * self-consistent model has none of) falls back to first-appearance order.
 */
function fkSortInsertOrder(order: readonly EntityMetadata[]): readonly EntityMetadata[] {
  const inSet = new Set(order.map((entity) => entity.name));
  // Each entity's in-set parents (the `relatedEntity` of its `many-to-one` rels).
  const parentsOf = new Map<string, Set<string>>();
  for (const entity of order) {
    const parents = new Set<string>();
    for (const rel of entity.relationships()) {
      if (rel.cardinality === "many-to-one" && inSet.has(rel.relatedEntity)) {
        parents.add(rel.relatedEntity);
      }
    }
    parentsOf.set(entity.name, parents);
  }
  const emitted = new Set<string>();
  const result: EntityMetadata[] = [];
  // Repeatedly emit, in first-appearance order, the first not-yet-emitted entity
  // all of whose in-set parents are already emitted (a stable topological order).
  while (result.length < order.length) {
    const next = order.find(
      (entity) =>
        !emitted.has(entity.name) &&
        [...(parentsOf.get(entity.name) ?? [])].every((parent) => emitted.has(parent)),
    );
    if (next === undefined) {
      // A dependency cycle: fall back to first-appearance order for the rest.
      for (const entity of order) {
        if (!emitted.has(entity.name)) {
          emitted.add(entity.name);
          result.push(entity);
        }
      }
      break;
    }
    emitted.add(next.name);
    result.push(next);
  }
  return result;
}

/** The quoted columns of an entity in `columnOrder` (descriptor order). */
function quotedColumnOrder(entity: EntityMetadata): readonly string[] {
  return columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
  }).map(quoteIdentifier);
}

/** The single primary-key physical column name of an entity. */
function pkColumn(entity: EntityMetadata): string {
  const pk = entity.primaryKey()[0];
  if (pk === undefined) {
    throw new Error(`entity '${entity.name}' has no primary key for a write`);
  }
  return pk.column;
}

/** Resolve an entity's audit {@link WriteTarget} (table, columns, pk, out_z). */
function writeTargetFor(entity: EntityMetadata): WriteTarget {
  const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
  return {
    table: quoteIdentifier(entity.table),
    columns: quotedColumnOrder(entity),
    pkColumn: quoteIdentifier(pkColumn(entity)),
    ...(processing === undefined ? {} : { toColumn: quoteIdentifier(processing.toColumn) }),
  };
}

/**
 * The ordered positional insert binds for a named input, in `columnOrder`. A
 * missing attribute binds `null`; an audit entity's interval columns default to
 * `[processingInstant, infinity)` when the caller does not supply them.
 */
function insertBinds(
  entity: EntityMetadata,
  input: Record<string, unknown>,
  processingInstant: string,
): readonly unknown[] {
  const processing = entity.asOfAttributes().find((axis) => axis.axis === "processing");
  return entity.attributes().map((attr) => {
    if (attr.name in input) {
      return bindValue(input[attr.name]);
    }
    if (processing !== undefined && attr.column === processing.fromColumn) {
      return processingInstant;
    }
    if (processing !== undefined && attr.column === processing.toColumn) {
      return INFINITY;
    }
    return null;
  });
}

/**
 * Whether a write predicate selects exactly one row by PRIMARY-KEY equality
 * (`Account.id.eq(1)`). A versioned `update` on such a predicate is a KEYED update
 * (the caller observed the row first, then updates it by pk); a versioned update on
 * ANY OTHER predicate — a range (`balance < ?`), a non-pk equality, `all` — has no
 * single pk to key on and MATERIALIZES instead: `TransactionEntity.update` resolves
 * the predicate to rows through the observing finder, then updates per object (M10,
 * ADR 0032). A non-versioned entity keeps its readless batched path either way.
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
