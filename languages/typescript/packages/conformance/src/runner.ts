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
 * The provider is **injected** through the port — the runner imports no driver
 * and no dialect package (it reaches the dialect-owned DDL / quoting helpers
 * through the one allowed `M3 -> M11` facade re-exported by `@parallax/sql`, and
 * the M1 reader through the `M2 -> M1` facade re-exported by
 * `@parallax/operation`).
 */
import type {
  AdapterIdentity,
  BindValue,
  CaseShape,
  CompileOk,
  Diagnostic,
  Emission,
  Envelope,
  NonOk,
  Observations,
  Row,
  RunOk,
} from "@parallax/core";
import { type EntityMetadata, Metamodel, parseOperation } from "@parallax/operation";
import { deepFetch, type Exec, type Row as GraphRow } from "@parallax/relationships";
import { columnOrder, compile, ddlForDescriptor, quoteIdentifier } from "@parallax/sql";
import { buildDeepFetchPlan, type DeepFetchPlan, isDeepFetch } from "./deepfetch-plan.js";
import { FIRST_IMPLEMENTATION_MVP_CAPABILITIES } from "./describe.js";
import type { LoadedCase } from "./discover.js";
import { inClaim } from "./gate.js";
import type { CompatibilityDatabaseProvider } from "./provider.js";
import { assertValidEnvelope } from "./schema.js";
import { schemaForReadCase } from "./schema-resolver.js";
import { buildWriteSequencePlan, isWriteSequence } from "./write-sequence.js";

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

  // A write-sequence case emits one item per generated DML statement, in
  // execution order, with `roundTrips` equal to the statement count.
  if (isWriteSequence(loaded)) {
    const plan = buildWriteSequencePlan(loaded);
    const emissions: Emission[] = plan.statements.map((statement) => ({
      casePointer: statement.casePointer,
      sql: statement.sql,
      binds: statement.binds as readonly WireBind[],
    }));
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

  const { sql, binds } = compileRootStatement(loaded);
  const emission: Emission = {
    casePointer: READ_OPERATION_POINTER,
    sql,
    binds: binds as readonly WireBind[],
  };
  const envelope: CompileOk = {
    schemaVersion: "1",
    command: "compile",
    status: "ok",
    adapter,
    case: loaded.casePath,
    dialect,
    caseShape: loaded.shape,
    emissions: [emission],
    roundTrips: 1,
  };
  return assertValidEnvelope(envelope);
}

/**
 * Compile the single statement a compile emission carries: for a flat read it is
 * the whole operation; for a deep fetch it is the deep-fetch root statement (the
 * operand compiled with the deep-fetch root projection). Both reuse the M3
 * `compile` visitor via a `MetamodelSchema`.
 */
function compileRootStatement(loaded: LoadedCase): { sql: string; binds: readonly BindValue[] } {
  if (isDeepFetch(loaded.raw.operation)) {
    const plan = buildDeepFetchPlan(loaded);
    return { sql: plan.root.sql, binds: plan.root.binds as readonly BindValue[] };
  }
  const operation = parseOperation(loaded.raw.operation);
  const schema = schemaForReadCase(loaded, operation);
  const { sql, binds } = compile(operation, schema);
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

  // A write-sequence case constructs its own milestone history from its ordered
  // DML, so it provisions an EMPTY table (no fixtures) and asserts the resulting
  // `tableState` — the observable form of the milestone-chaining write contract.
  if (isWriteSequence(loaded)) {
    const { emissions, observations } = await runWriteSequence(loaded, provider);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  await provision(loaded, provider);
  const { emissions, observations } = isDeepFetch(loaded.raw.operation)
    ? await runDeepFetch(loaded, provider)
    : await runFlatRead(loaded, provider);
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
): Promise<RunResult> {
  const operation = parseOperation(loaded.raw.operation);
  const schema = schemaForReadCase(loaded, operation);
  const { sql, binds } = compile(operation, schema);

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
): Promise<RunResult> {
  const plan: DeepFetchPlan = buildDeepFetchPlan(loaded);

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
): Promise<RunResult> {
  await provisionEmpty(loaded, provider);
  const plan = buildWriteSequencePlan(loaded);

  const emissions: Emission[] = [];
  for (const statement of plan.statements) {
    emissions.push({
      casePointer: statement.casePointer,
      sql: statement.sql,
      binds: statement.binds as readonly WireBind[],
    });
    await provider.exec(statement.sql, statement.binds);
  }

  const tableState = await readTableState(loaded, provider);
  return {
    emissions,
    observations: { roundTrips: emissions.length, tableState },
  };
}

/**
 * Read the resulting state of every table the case's `expectedTableState` names,
 * projecting each entity's columns in descriptor order (matching the golden
 * table-state authoring). Keyed by physical table name.
 */
async function readTableState(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
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
    state[table] = (await provider.query(readTableSql(entity), [])) as readonly Row[];
  }
  return state;
}

/** `select t0.<col>, … from <table> t0` — the full table state, column-ordered. */
function readTableSql(entity: EntityMetadata): string {
  const columns = columnOrder({
    table: entity.table,
    attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
  });
  const projection = columns.map((column) => `t0.${quoteIdentifier(column)}`).join(", ");
  return `select ${projection} from ${quoteIdentifier(entity.table)} t0`;
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

/** Provision a clean, EMPTY DB (reset + DDL, no fixtures) for a write sequence. */
async function provisionEmpty(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
): Promise<void> {
  await provider.reset();
  await provider.applyDdl(ddlForDescriptor(loaded.descriptor));
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
    FIRST_IMPLEMENTATION_MVP_CAPABILITIES,
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

/** Re-export the shape type for consumers assembling envelopes. */
export type { CaseShape };
