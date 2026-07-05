/**
 * The M12 runner — orchestrates `compile` / `run` for the `read` shape.
 *
 * `compile` (Docker-free): resolve the case's operation against the M1 metamodel
 * reader, lower it with the M3 canonical-by-construction visitor, and assemble a
 * schema-valid `compile` envelope (emissions + binds + `roundTrips`). No database
 * is touched.
 *
 * `run` (database-backed): provision a clean DB via the injected
 * `CompatibilityDatabaseProvider` port, derive + apply DDL from the descriptor,
 * load fixtures per the case lifecycle, execute the compiled SQL, assemble `rows`
 * observations with `observations.roundTrips`, and validate the `run` envelope.
 *
 * The provider is **injected** through the port — the runner imports no driver.
 * It is the harness's SQL-assembly orchestrator, so it imports the concrete
 * dialect's pure *rules* (DDL / identifier quoting / read-lock application)
 * directly from `@parallax/dialect` (M12 -> M11), and the M1 reader through the
 * `M2 -> M1` facade re-exported by `@parallax/operation`.
 */
import type {
  AdapterIdentity,
  BindValue,
  CompileOk,
  Diagnostic,
  Emission,
  Envelope,
  IdentityCheck,
  NonOk,
  Observations,
  Row,
  RunOk,
} from "@parallax/core";
import {
  columnOrder,
  type Dialect,
  ddlForDescriptor,
  mariadbDialect,
  postgresDialect,
} from "@parallax/dialect";
import { type EntityMetadata, Metamodel, parseOperation } from "@parallax/operation";
import { deepFetch, type Exec, type Row as GraphRow } from "@parallax/relationships";
import { compile } from "@parallax/sql";
import { buildConflictPlan, isConflict } from "./conflict.js";
import { buildDeepFetchPlan, type DeepFetchPlan, isDeepFetch } from "./deepfetch-plan.js";
import { SLICE_MVP_1_CAPABILITIES } from "./describe.js";
import type { LoadedCase } from "./discover.js";
import { inClaim } from "./gate.js";
import type { CompatibilityDatabaseProvider } from "./provider.js";
import { buildScenarioPlan, isScenario, stepBindsAt } from "./scenario.js";
import { assertValidEnvelope } from "./schema.js";
import { schemaForReadCase } from "./schema-resolver.js";
import { buildWriteSequencePlan, isWriteSequence } from "./write-sequence.js";

/**
 * The `read-lock` tag marks a locking-mode in-transaction object find that must
 * carry the dialect's shared-row-lock suffix (M8 automatic read-lock correctness).
 * The signal is the tag (not the operation AST — the operation is a plain `eq`), so
 * the runner detects it here and compiles the read in `locking` mode; `compile()`
 * then applies the dialect's read-lock in-line (`for share of t0` after every other
 * clause), so the emitted SQL already carries the lock (no post-compile step).
 */
function isReadLock(loaded: LoadedCase): boolean {
  return loaded.tags.includes("read-lock");
}

/**
 * Select the concrete {@link Dialect} for a run key (the dialect id keying
 * `goldenSql`). The runner is the M12 orchestrator, so it consults the concrete
 * dialect's pure rules directly (M12 → M11). Both conforming dialects are
 * registered: Postgres (the claimed run dialect) and MariaDB (the second
 * implementer, driven Docker-free by the compile-golden lane).
 */
function dialectFor(key: string): Dialect {
  if (key === postgresDialect.id) {
    return postgresDialect;
  }
  if (key === mariadbDialect.id) {
    return mariadbDialect;
  }
  throw new Error(`no dialect registered for run key '${key}'`);
}

/** The case's authored binds carried verbatim (a flat scalar list for a read). */
type WireBind = BindValue;

/**
 * The JSON Pointer an emission carries for a single read-shape operation: the
 * case's `operation` key. The conformance contract names `/operation` as the
 * common read-operation pointer (`conformance-adapter-contract.md` — both the
 * `compile` and `run` examples), reserving the empty pointer `""` for
 * diagnostics that apply to the whole case (e.g. the out-of-claim gate). Write
 * sequences / scenarios / deep fetch use per-statement pointers (Phase 4+).
 */
const READ_OPERATION_POINTER = "/operation" as const;

/**
 * The read-projection helper is re-exported from the schema resolver so the CLI /
 * tests that already imported it from the runner keep working; the resolver + all
 * projection rules now live in `./schema-resolver.js` (single source of truth).
 */
export { readProjection } from "./schema-resolver.js";

// --- compile lane -----------------------------------------------------------

/**
 * Compile a `read` case to its canonical SQL + binds and assemble a schema-valid
 * `compile` envelope.
 *
 * A single-statement read (including the flat navigation/`exists`/`notExists`
 * semi-join cases, which lower to one `select … where exists (…)`) emits one
 * `/operation` emission with `roundTrips: 1`, per the contract's `compile`
 * example.
 *
 * A **deep-fetch** case emits only the ROOT statement (`roundTrips: 1`). Its
 * child levels are keyed by the DISTINCT parent keys gathered from the previous
 * level at run time (the N+1-eliminating `IN` list), so their `IN`-bind arity and
 * values are not statically known — a Docker-free compile cannot reproduce them.
 * The contract permits an emission-per-static-step and treats run-time-only work
 * as producing no static emission; the full multi-statement emission (root +
 * per-level, keyed by real parent keys) is produced by the run lane, which is
 * where non-temporal 03xx deep fetch is graded (graph + `roundTrips`).
 */
export function runCompile(
  loaded: LoadedCase,
  dialect: string,
  adapter: AdapterIdentity,
): Envelope {
  const gate = gateOrNonOk(loaded, "compile", dialect, adapter);
  if (gate) {
    return gate;
  }
  const suiteSatisfied = laneSkipOrNonOk(loaded, "compile", adapter);
  if (suiteSatisfied) {
    return suiteSatisfied;
  }

  // A write-sequence case emits one item per generated DML statement, in
  // execution order, with `roundTrips` equal to the statement count.
  if (isWriteSequence(loaded)) {
    const plan = buildWriteSequencePlan(loaded, dialectFor(dialect));
    return compileOk(loaded, dialect, adapter, toEmissions(plan.statements));
  }

  // A conflict case emits its generated versioned `UPDATE`(s) (one per attempt),
  // keyed by their case pointer; `roundTrips` is the attempt count.
  if (isConflict(loaded)) {
    const plan = buildConflictPlan(loaded, dialectFor(dialect));
    return compileOk(loaded, dialect, adapter, toEmissions(plan.attempts));
  }

  // A scenario is NOT compiled to SQL (its golden is authored per step, not
  // derived); the adapter surfaces the authored step statements so the compile
  // gate can classify it in-claim, with `roundTrips` the declared case total.
  if (isScenario(loaded)) {
    const plan = buildScenarioPlan(loaded);
    const emissions: Emission[] = plan.steps.flatMap((step) =>
      // A MULTI-statement step (a versioned set-based materialize write, `0614` /
      // `0615`) carries a list-of-lists `binds`, one per statement — slice it so
      // each per-object `UPDATE` emission carries its own bind row.
      step.statements.map((sql, statementIndex) => ({
        casePointer: step.casePointer,
        sql,
        binds: stepBindsAt(step.binds, statementIndex) as readonly WireBind[],
      })),
    );
    return assertValidEnvelope({
      schemaVersion: "1",
      command: "compile",
      status: "ok",
      adapter,
      case: loaded.casePath,
      dialect,
      caseShape: loaded.shape,
      emissions,
      roundTrips: plan.roundTrips,
    });
  }

  const { sql, binds } = compileRootStatement(loaded, dialectFor(dialect));
  const emission: Emission = {
    casePointer: READ_OPERATION_POINTER,
    sql,
    binds: binds as readonly WireBind[],
  };
  return assertValidEnvelope({
    schemaVersion: "1",
    command: "compile",
    status: "ok",
    adapter,
    case: loaded.casePath,
    dialect,
    caseShape: loaded.shape,
    emissions: [emission],
    roundTrips: 1,
  });
}

/** Map a list of `{ casePointer, sql, binds }` plan items to wire emissions. */
function toEmissions(
  items: readonly { casePointer: string; sql: string; binds: readonly unknown[] }[],
): Emission[] {
  return items.map((item) => ({
    casePointer: item.casePointer,
    sql: item.sql,
    binds: item.binds as readonly WireBind[],
  }));
}

/**
 * Assemble a statement-list `compile` success envelope (`roundTrips` = the emitted
 * statement count). Used by the write-sequence and conflict shapes, whose
 * emissions map one-to-one onto their generated DML statements.
 */
function compileOk(
  loaded: LoadedCase,
  dialect: string,
  adapter: AdapterIdentity,
  emissions: readonly Emission[],
): Envelope {
  const envelope: CompileOk = {
    schemaVersion: "1",
    command: "compile",
    status: "ok",
    adapter,
    case: loaded.casePath,
    dialect,
    caseShape: loaded.shape,
    emissions,
    roundTrips: emissions.length,
  };
  return assertValidEnvelope(envelope);
}

/**
 * Compile the single statement a compile emission carries: for a flat read it is
 * the whole operation; for a deep fetch it is the deep-fetch root statement (the
 * operand compiled with the deep-fetch root projection). Both reuse the M3
 * `compile` visitor via a `MetamodelSchema`.
 */
function compileRootStatement(
  loaded: LoadedCase,
  dialect: Dialect,
): { sql: string; binds: readonly BindValue[] } {
  if (isDeepFetch(loaded.raw.operation)) {
    const plan = buildDeepFetchPlan(loaded, dialect);
    return { sql: plan.root.sql, binds: plan.root.binds as readonly BindValue[] };
  }
  const operation = parseOperation(loaded.raw.operation);
  const schema = schemaForReadCase(loaded, operation, dialect);
  // A `read-lock`-tagged case is a locking-mode object find: `compile()` applies the
  // dialect's shared-row-lock in-line after every other clause (M8 automatic read-
  // lock correctness; the dialect owns the append — M11), so the SQL is already
  // locked with no post-compile step.
  const { sql, binds } = compile(operation, schema, dialect, { locking: isReadLock(loaded) });
  return { sql, binds: binds as readonly BindValue[] };
}

// --- run lane ---------------------------------------------------------------

/**
 * Run a `read` case end-to-end against an injected provider: provision, derive +
 * apply DDL, load fixtures, execute the compiled SQL, and assemble a schema-valid
 * `run` envelope. A flat read reports `rows`; a deep fetch reports the assembled
 * `graph` with `roundTrips = 1 + non-elided levels`.
 */
export async function runRun(
  loaded: LoadedCase,
  dialect: string,
  adapter: AdapterIdentity,
  provider: CompatibilityDatabaseProvider,
): Promise<Envelope> {
  const gate = gateOrNonOk(loaded, "run", dialect, adapter);
  if (gate) {
    return gate;
  }
  const suiteSatisfied = laneSkipOrNonOk(loaded, "run", adapter);
  if (suiteSatisfied) {
    return suiteSatisfied;
  }

  const dialectImpl = dialectFor(dialect);

  // A write-sequence case constructs its own milestone history from its ordered
  // DML, so it provisions an EMPTY table (no fixtures) and asserts the resulting
  // `tableState` — the observable form of the milestone-chaining write contract.
  if (isWriteSequence(loaded)) {
    const { emissions, observations } = await runWriteSequence(loaded, provider, dialectImpl);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  // A conflict case loads fixtures, applies the out-of-band precondition (a
  // concurrent writer), then the versioned UPDATE(s), and reports the affected-row
  // count + resulting `tableState` (the observable optimistic-lock contract).
  if (isConflict(loaded)) {
    const { emissions, observations } = await runConflict(loaded, provider, dialectImpl);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  // A scenario case commits its write steps and executes its finds against the
  // provisioned DB, reporting the observed rows + identity checks (M8 read-your-
  // own-writes / cache / identity).
  if (isScenario(loaded)) {
    const { emissions, observations } = await runScenario(loaded, provider);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  await provision(loaded, provider);
  const { emissions, observations } = isDeepFetch(loaded.raw.operation)
    ? await runDeepFetch(loaded, provider, dialectImpl)
    : await runFlatRead(loaded, provider, dialectImpl);
  return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
}

/** Assemble a `run` success envelope from its emissions + observations. */
function runOk(
  loaded: LoadedCase,
  dialect: string,
  adapter: AdapterIdentity,
  emissions: readonly Emission[],
  observations: Observations,
): RunOk {
  return {
    schemaVersion: "1",
    command: "run",
    status: "ok",
    adapter,
    case: loaded.casePath,
    dialect,
    caseShape: loaded.shape,
    emissions,
    observations,
  };
}

/** The emissions + observations a run produces (assembled into the envelope). */
interface RunResult {
  readonly emissions: readonly Emission[];
  readonly observations: Observations;
}

/**
 * Execute a flat read: compile the whole operation, run the single statement, and
 * report the observed `rows` with `roundTrips: 1`. Covers the plain scalar reads
 * and the navigation/`exists`/`notExists` semi-join cases (one `select`).
 */
async function runFlatRead(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  const operation = parseOperation(loaded.raw.operation);
  const schema = schemaForReadCase(loaded, operation, dialect);
  // A `read-lock`-tagged case is a locking-mode object find; `compile()` applies the
  // dialect's shared-row-lock in-line after every other clause (the lock does not
  // change rows), so the executed SQL is already locked.
  const { sql, binds } = compile(operation, schema, dialect, { locking: isReadLock(loaded) });

  const rows = await provider.query(sql, binds as readonly unknown[]);
  return {
    emissions: [{ casePointer: READ_OPERATION_POINTER, sql, binds: binds as readonly WireBind[] }],
    observations: { roundTrips: 1, rows: rows as readonly Row[] },
  };
}

/**
 * Execute a deep fetch: build the plan, run the root statement, then let the pure
 * `@parallax/relationships` strategy fetch one bulk `IN`-keyed query per non-empty
 * level (never N+1). Assemble the `graph` observation (decorated root rows keyed
 * by the root entity's domain name), report `roundTrips = 1 + non-elided levels`,
 * and emit one emission per statement actually issued (root + each executed
 * level), in execution order.
 */
async function runDeepFetch(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  const plan: DeepFetchPlan = buildDeepFetchPlan(loaded, dialect);

  const rootRows = await provider.query(plan.root.sql, plan.root.binds);
  const emissions: Emission[] = [
    {
      casePointer: READ_OPERATION_POINTER,
      sql: plan.root.sql,
      binds: plan.root.binds as readonly WireBind[],
    },
  ];

  // Each level the strategy issues runs through this `exec`, which records the
  // exact SQL + binds (the real IN list keyed by gathered parent keys) so the
  // envelope's emissions mirror the statements executed, in order.
  const exec: Exec = async (sql, binds) => {
    emissions.push({
      casePointer: READ_OPERATION_POINTER,
      sql,
      binds: binds as readonly WireBind[],
    });
    return (await provider.query(sql, binds)) as readonly GraphRow[];
  };

  const result = await deepFetch(rootRows as readonly GraphRow[], plan.tree, exec);

  const graph: Record<string, readonly Row[]> = {
    [plan.rootEntity]: result.rows as readonly Row[],
  };
  return {
    emissions,
    observations: { roundTrips: result.roundTrips, graph },
  };
}

/**
 * Execute a write sequence: provision an EMPTY table (the case builds its own
 * milestone history from its ordered DML — no fixtures), apply the generated DML
 * statements in order with the authored per-statement binds, then read back the
 * resulting `tableState` (every table the case's `expectedTableState` names). One
 * emission per statement, `roundTrips` = statement count.
 */
async function runWriteSequence(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  await provisionEmpty(loaded, provider);
  const plan = buildWriteSequencePlan(loaded, dialect);

  const emissions: Emission[] = [];
  for (const statement of plan.statements) {
    emissions.push({
      casePointer: statement.casePointer,
      sql: statement.sql,
      binds: statement.binds as readonly WireBind[],
    });
    await provider.exec(statement.sql, statement.binds);
  }

  const tableState = await readTableState(loaded, provider, dialect);
  return {
    emissions,
    observations: { roundTrips: emissions.length, tableState },
  };
}

/**
 * Execute a conflict case (M10): provision + load fixtures (the versioned row
 * exists), apply the out-of-band `precondition` (a concurrent writer) VERBATIM,
 * then apply the versioned UPDATE(s) — one per attempt — and report the LAST
 * attempt's affected-row count as `affectedRows` plus the resulting `tableState`.
 *
 * The single form has one attempt (`affectedRows` is that update's count); the
 * retry form has two (`0708`: a stale attempt affects 0, the fresh retry affects
 * 1 — `affectedRows` reports the retry's 1, the terminal outcome). Each attempt's
 * count is checked against its declared `expectedAffectedRows` so a wrong count
 * fails loudly here, not only at the table-state grade. `roundTrips` counts the
 * versioned UPDATE(s) issued (the precondition is out-of-band, not our runtime).
 */
async function runConflict(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  await provision(loaded, provider);
  const plan = buildConflictPlan(loaded, dialect);

  for (const statement of plan.precondition) {
    await provider.exec(statement.sql, statement.binds);
  }

  const emissions: Emission[] = [];
  let lastAffected = 0;
  for (const attempt of plan.attempts) {
    emissions.push({
      casePointer: attempt.casePointer,
      sql: attempt.sql,
      binds: attempt.binds as readonly WireBind[],
    });
    const affected = await provider.exec(attempt.sql, attempt.binds);
    if (affected !== attempt.expectedAffectedRows) {
      throw new Error(
        `attempt ${attempt.casePointer}: versioned UPDATE affected ${affected} row(s), ` +
          `expected ${attempt.expectedAffectedRows}`,
      );
    }
    lastAffected = affected;
  }

  const tableState = await readTableState(loaded, provider, dialect);
  return {
    emissions,
    observations: { roundTrips: emissions.length, affectedRows: lastAffected, tableState },
  };
}

/**
 * Execute a scenario (M8): provision + load fixtures, then run each step in order.
 * A WRITE step COMMITs its golden DML (a buffered write the unit of work flushes)
 * and captures no rows; a FIND step executes its golden `select` and captures the
 * observed rows (a cache-HIT step lists no golden and reuses a prior step's rows).
 * The `rows` observation is the LAST find's rows (`0607`'s dependent find that
 * MUST observe the committed write); `roundTrips` is the declared case total; each
 * `sameObjectAs` becomes an `identityChecks` entry (the one-object-per-PK rule).
 */
async function runScenario(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
): Promise<RunResult> {
  await provision(loaded, provider);
  const plan = buildScenarioPlan(loaded);

  const emissions: Emission[] = [];
  const results: (readonly Row[])[] = [];
  let lastFindRows: readonly Row[] = [];
  const identityChecks: IdentityCheck[] = [];

  for (const [index, step] of plan.steps.entries()) {
    if (step.kind === "write") {
      // A step may emit SEVERAL statements (a versioned set-based materialize write,
      // `0614` / `0615`: one per-object `UPDATE` per row); its `binds` is then a
      // list-of-lists sliced per statement (`stepBindsAt`).
      for (const [statementIndex, sql] of step.statements.entries()) {
        const stmtBinds = stepBindsAt(step.binds, statementIndex);
        emissions.push({
          casePointer: step.casePointer,
          sql,
          binds: stmtBinds as readonly WireBind[],
        });
        // A `rollback: true` step applies the DML then ROLLS IT BACK (the M8 abort
        // contract): the write lands in an atomic scope that is discarded, so a
        // later find MUST observe the ORIGINAL rows. A default write COMMITs.
        if (step.rollback === true) {
          await provider.execRolledBack(sql, stmtBinds);
        } else {
          await provider.exec(sql, stmtBinds);
        }
      }
      results.push([]);
      continue;
    }

    // A find step: execute its golden (a cache hit lists none and reuses a prior
    // step's rows via `sameObjectAs`, or the immediately-preceding step). A find is
    // single-statement, so its binds are the (flat) statement-0 binds.
    let rows: readonly Row[];
    if (step.statements.length > 0) {
      const sql = step.statements[0] as string;
      const stmtBinds = stepBindsAt(step.binds, 0);
      emissions.push({
        casePointer: step.casePointer,
        sql,
        binds: stmtBinds as readonly WireBind[],
      });
      rows = (await provider.query(sql, stmtBinds)) as readonly Row[];
    } else {
      const source = step.sameObjectAs ?? index - 1;
      rows = results[source] ?? [];
    }
    results.push(rows);
    lastFindRows = rows;

    if (step.sameObjectAs !== undefined) {
      const source = step.sameObjectAs;
      identityChecks.push({
        left: `/scenario/${index}`,
        right: `/scenario/${source}`,
        same: sameIdentity(rows, results[source] ?? [], pkColumnName(loaded)),
      });
    }
  }

  const observations: Observations = {
    roundTrips: plan.roundTrips,
    rows: lastFindRows,
    ...(identityChecks.length > 0 ? { identityChecks } : {}),
  };
  return { emissions, observations };
}

/** The root entity's primary-key column name (the scenario identity column). */
function pkColumnName(loaded: LoadedCase): string {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const [entity] = metamodel.entities();
  const pk = entity?.primaryKey()[0];
  return pk?.column ?? "id";
}

/** True when two row sets carry the same set of primary-key identities. */
function sameIdentity(left: readonly Row[], right: readonly Row[], pkColumn: string): boolean {
  const keys = (rows: readonly Row[]): string[] => rows.map((row) => String(row[pkColumn])).sort();
  const a = keys(left);
  const b = keys(right);
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

/**
 * Read the resulting state of every table the case's `expectedTableState` names,
 * projecting each entity's columns in descriptor order (matching the golden
 * table-state authoring). Keyed by physical table name.
 */
async function readTableState(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<Record<string, readonly Row[]>> {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const byTable = new Map<string, EntityMetadata>();
  for (const entity of metamodel.entities()) {
    if (!byTable.has(entity.table)) {
      byTable.set(entity.table, entity);
    }
  }
  const expected = (loaded.raw.expectedTableState as Record<string, unknown> | undefined) ?? {};
  const state: Record<string, readonly Row[]> = {};
  for (const table of Object.keys(expected)) {
    const entity = byTable.get(table);
    if (entity === undefined) {
      throw new Error(`expectedTableState names table '${table}' not in the model`);
    }
    state[table] = (await provider.query(readTableSql(entity, dialect), [])) as readonly Row[];
  }
  return state;
}

/**
 * `select t0.<col>, … from <table> t0` — the full table state, column-ordered.
 * Identifiers are quoted through the injected dialect so a reserved-word column /
 * table (e.g. `order`) reads back correctly on MariaDB (backticks) as well as
 * Postgres (double-quotes).
 */
function readTableSql(entity: EntityMetadata, dialect: Dialect): string {
  const columns = columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
  });
  const projection = columns.map((column) => `t0.${dialect.quoteIdentifier(column)}`).join(", ");
  return `select ${projection} from ${dialect.quoteIdentifier(entity.table)} t0`;
}

/** Provision a clean DB: reset, derive + apply DDL, load fixtures. */
async function provision(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
): Promise<void> {
  await provider.reset();
  await provider.applyDdl(ddlForDescriptor(loaded.descriptor));
  await loadFixtures(loaded, provider);
}

/**
 * Provision a clean, EMPTY DB (reset + DDL, no fixtures) for a write sequence —
 * the case builds its own state from its ordered DML — UNLESS it opts into
 * `loadFixtures` (the per-key batched-update case `0613` mutates pre-existing
 * fixture rows), in which case the model's fixtures are loaded first (mirrors the
 * Python harness `_provision_empty`).
 */
async function provisionEmpty(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
): Promise<void> {
  await provider.reset();
  await provider.applyDdl(ddlForDescriptor(loaded.descriptor));
  if (loaded.raw.loadFixtures === true) {
    await loadFixtures(loaded, provider);
  }
}

/**
 * Load every entity's fixture rows. Fixture rows speak attribute-name
 * vocabulary; resolve them to descriptor column order, filling missing
 * attributes with `null` (mirrors the harness data loader).
 */
async function loadFixtures(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
): Promise<void> {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  for (const entity of metamodel.entities()) {
    const rows = loaded.fixtures[entity.name] ?? [];
    if (rows.length === 0) {
      continue;
    }
    const attributes = entity.attributes();
    const columns = columnOrder({
      table: entity.table,
      attributes: attributes.map((a) => ({ type: a.type, column: a.column })),
    });
    const nameByColumn = new Map(attributes.map((a) => [a.column, a.name]));
    const tuples = rows.map((row) =>
      columns.map((column) => row[nameByColumn.get(column) ?? column] ?? null),
    );
    await provider.loadFixtures(entity.table, columns, tuples);
  }
}

// --- shared gating ----------------------------------------------------------

/**
 * Evaluate the in-claim gate; return an `unsupported` envelope (out of claim)
 * or `undefined` (in claim — proceed). The diagnostic names the first failed
 * filter.
 */
function gateOrNonOk(
  loaded: LoadedCase,
  command: "compile" | "run",
  dialect: string,
  adapter: AdapterIdentity,
): NonOk | undefined {
  const gate = inClaim(
    { shape: loaded.shape, tags: loaded.tags },
    command,
    dialect,
    SLICE_MVP_1_CAPABILITIES,
  );
  if (gate.inClaim) {
    return undefined;
  }
  const diagnostic: Diagnostic = {
    code: gate.code,
    message: gate.message,
    casePointer: "",
  };
  return {
    schemaVersion: "1",
    command,
    status: "unsupported",
    adapter,
    diagnostics: [diagnostic],
  };
}

/**
 * Route an `api-conformance`-lane case to a **suite-satisfied** `unsupported`
 * envelope (in-claim by shape/tags/dialect, but not harness-run — the language's
 * API Conformance Suite satisfies it). Applies to every `boundary`-shape case and
 * to the `read`-shape read-lock matrix cases (`0616`-`0619`) that carry
 * `lane: api-conformance`: their observable is a runtime-loop / injected-fault /
 * emitted-lock property the single-connection harness cannot execute. The full-slice
 * harness sweeps filter these out; this branch is the defensive route for the CLI /
 * a direct `runCompile` / `runRun` call. The slice-coverage claim stays lane-agnostic
 * (an api-conformance case is still *claimed*), so this changes routing, not claim.
 */
function laneSkipOrNonOk(
  loaded: LoadedCase,
  command: "compile" | "run",
  adapter: AdapterIdentity,
): NonOk | undefined {
  if (loaded.lane !== "api-conformance") {
    return undefined;
  }
  const diagnostic: Diagnostic = {
    code: "suite-satisfied",
    message: `case is api-conformance lane (${loaded.shape} shape); satisfied by the API Conformance Suite, not harness-run`,
    casePointer: "",
  };
  return {
    schemaVersion: "1",
    command,
    status: "unsupported",
    adapter,
    diagnostics: [diagnostic],
  };
}
