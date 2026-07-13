/**
 * The m-conformance-adapter runner — orchestrates `compile` / `run` for the `read` shape.
 *
 * `compile` (Docker-free): resolve the case's operation against the m-descriptor metamodel
 * reader, lower it with the m-sql canonical-by-construction visitor, and assemble a
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
 * directly from `@parallax/dialect` (m-case-format -> m-dialect), and the m-descriptor reader through the
 * `m-op-algebra -> m-descriptor` facade re-exported by `@parallax/operation`.
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
import { toWire } from "@parallax/core";
import { type ParallaxRow, ParallaxTransientError } from "@parallax/db";
import {
  canonicalBinds,
  type Dialect,
  ddlForDescriptor,
  mariadbDialect,
  postgresDialect,
} from "@parallax/dialect";
import {
  type EntityMetadata,
  Metamodel,
  parseOperation,
  RejectionError,
  validateOperationValueObjects,
  validateWriteValueObjects,
} from "@parallax/operation";
import { deepFetch, type Exec, type Row as GraphRow } from "@parallax/relationships";
import { compile } from "@parallax/sql";
import {
  type DialectStatement,
  dialectStatements,
  goldenEntries,
  type StatementEntry,
} from "./case-format.js";
import { compareRowSet } from "./compare.js";
import { buildConflictPlan, isConflict } from "./conflict.js";
import { buildDeepFetchPlan, type DeepFetchPlan, isDeepFetch } from "./deepfetch-plan.js";
import { SLICE_MVP_1_CAPABILITIES } from "./describe.js";
import type { LoadedCase } from "./discover.js";
import { inClaim } from "./gate.js";
import type { CompatibilityDatabaseProvider, CompatibilitySession } from "./provider.js";
import { buildScenarioPlan, isScenario } from "./scenario.js";
import { assertValidEnvelope } from "./schema.js";
import { columnTypesForCase, schemaForReadCase } from "./schema-resolver.js";
import { decodeTableStateRow, materializeOwnerNode } from "./value-object-materialize.js";
import { buildWriteSequencePlan, isWriteSequence, orderedColumns } from "./write-sequence.js";

/**
 * The `m-read-lock` module tag marks a locking-mode in-transaction object find
 * that must carry the dialect's shared-row-lock suffix (automatic read-lock
 * correctness). The signal is the tag (not the operation AST — the operation is a
 * plain `eq`), so the runner detects it here and compiles the read in `locking`
 * mode; `compile()` then applies the dialect's read-lock in-line (`for share of
 * t0` after every other clause), so the emitted SQL already carries the lock (no
 * post-compile step).
 */
function isReadLock(loaded: LoadedCase): boolean {
  return loaded.tags.includes("m-read-lock");
}

/** One side (`A`/`B`) of a `concurrency.rounds` step: its golden statement entries. */
interface ConcurrencyStep {
  readonly statements?: readonly StatementEntry[];
  /**
   * concurrency-SUCCESS form only: the EXPLICIT read-vs-write discriminator the runner
   * branches on (replacing the old SQL-verb sniffing). `read` → the step is fetched on
   * its HELD session and its rows graded against {@link ConcurrencyStep.expectRows};
   * `write` → the step is executed and asserts only that it did not block/raise. Absent
   * on the error/concurrency shape; a success step missing a valid `kind` fails fast
   * (see {@link concurrencySuccessStepProblems}).
   */
  readonly kind?: "read" | "write";
  /**
   * concurrency-SUCCESS form only: the rows a `kind: read` step MUST return on its HELD
   * session (`m-read-lock-007` / `m-read-lock-008`). Required for a read and forbidden on a write — enforced
   * structurally by the schema's `kind` if/then AND re-checked pre-flight by
   * {@link concurrencySuccessStepProblems}; a write step omits it and asserts only that
   * it did not block/raise.
   */
  readonly expectRows?: readonly Record<string, unknown>[];
}

/** A `concurrency.rounds` step: the `A` and/or `B` statement issued that round. */
interface ConcurrencyRound {
  readonly A?: ConcurrencyStep;
  readonly B?: ConcurrencyStep;
}

/**
 * Resolve a concurrency node step's golden `{sql, binds}` for `dialect` (each
 * concurrency node runs a single statement), or `undefined` when the step is idle /
 * omits the dialect.
 */
function concurrencyStatement(
  step: ConcurrencyStep | undefined,
  dialect: Dialect,
): DialectStatement | undefined {
  return dialectStatements(step?.statements ?? [], dialect.id)[0];
}

/** The two barrier-synchronized nodes of the concurrency choreography. */
const CONCURRENCY_NODES = ["A", "B"] as const;
type ConcurrencyNode = (typeof CONCURRENCY_NODES)[number];

/**
 * The `error`/concurrency case's barrier-separated rounds (`m-read-lock-006` + the m-db-error
 * deadlock/lock-wait family). Each round names the `A` and/or `B` golden a held
 * non-autocommit session runs that round; a node absent from a round is idle.
 */
function concurrencyRounds(loaded: LoadedCase): readonly ConcurrencyRound[] {
  return (loaded.raw.when?.concurrency?.rounds ?? []) as readonly ConcurrencyRound[];
}

/**
 * A per-step node that MAY carry authored golden statement entries — a scenario step
 * (`when.scenario[]`) or a conflict retry attempt (`when.attempts[]`). Both schemas
 * key golden per step (not at the top-level `then.statements`), and both surface as a
 * loosely-typed generated object, so this reader names only the `statements` member
 * the golden-availability check consults (mirroring `scenario.ts`'s `RawScenarioStep`
 * and `conflict.ts`'s per-attempt `statements` access).
 */
interface StatementBearer {
  readonly statements?: readonly StatementEntry[];
}

/**
 * Whether the case declares golden SQL for `dialect` **anywhere its shape authors it**
 * — the TS mirror of the Python oracle's per-dialect skip (`case_runner.run_case`'s
 * `_scenario_has_golden` / `_error_has_golden` / `_concurrency_has_golden` /
 * `_conflict_retry_has_golden` / `dialect in case.golden_dialects` guards). The oracle
 * runs only the dialect-agnostic checks and returns when a case declares no golden for
 * the active dialect; the runner needs the same signal to route such a case to a skip
 * rather than compiling / executing a dialect the case never authored.
 *
 * Golden lives in a DIFFERENT place per shape, so the check is per shape:
 *
 *  - **scenario** — per step at `when.scenario[].statements`; true iff any step declares
 *    the dialect (`_scenario_has_golden`);
 *  - **concurrencySuccess** — per concurrency round node at
 *    `when.concurrency.rounds[].{A,B}.statements`; true iff any node declares the dialect
 *    (`_concurrency_has_golden`);
 *  - **error** — the concurrency choreography (as above) OR, for a single-connection
 *    error case, the top-level `then.statements` (`_error_has_golden`, whose
 *    single-connection branch keys on `dialect in case.golden_dialects`);
 *  - **conflict** — the retry form declares golden per attempt at
 *    `when.attempts[].statements` (`_conflict_retry_has_golden`); the single form uses
 *    the top-level `then.statements`;
 *  - **read / writeSequence / deepFetch (default)** — the top-level `then.statements`
 *    (`dialect in case.golden_dialects`).
 *
 * The `boundary` and `coherence` shapes never reach this check — a boundary case is
 * `lane: api-conformance` (routed by {@link laneSkipOrNonOk}) and a coherence case is an
 * unclaimed shape (rejected by the gate) — but the default `then.statements` branch is a
 * safe (non-throwing) fallback for them regardless.
 */
export function caseDeclaresGoldenForDialect(loaded: LoadedCase, dialect: string): boolean {
  switch (loaded.shape) {
    case "scenario": {
      const steps = (loaded.raw.when?.scenario ?? []) as readonly StatementBearer[];
      return steps.some((step) => dialectStatements(step.statements ?? [], dialect).length > 0);
    }
    case "concurrencySuccess":
      return concurrencyRoundsDeclareGolden(loaded, dialect);
    case "error":
      // Two-connection (concurrency choreography) OR single-connection (top-level golden).
      return (
        concurrencyRoundsDeclareGolden(loaded, dialect) ||
        dialectStatements(goldenEntries(loaded.raw), dialect).length > 0
      );
    case "conflict": {
      const attempts = (loaded.raw.when?.attempts ?? []) as readonly StatementBearer[];
      // The retry form authors golden per attempt; the single form uses then.statements.
      if (attempts.length > 0) {
        return attempts.some(
          (attempt) => dialectStatements(attempt.statements ?? [], dialect).length > 0,
        );
      }
      return dialectStatements(goldenEntries(loaded.raw), dialect).length > 0;
    }
    default:
      // read / writeSequence / deepFetch (and the never-reached boundary / coherence):
      // golden is the top-level then.statements.
      return dialectStatements(goldenEntries(loaded.raw), dialect).length > 0;
  }
}

/**
 * Whether any concurrency round node (`when.concurrency.rounds[].{A,B}`) declares golden
 * for `dialect` — the round-shaped golden location shared by the `error` (two-connection)
 * and `concurrencySuccess` shapes (mirrors Python's `_concurrency_statements`).
 */
function concurrencyRoundsDeclareGolden(loaded: LoadedCase, dialect: string): boolean {
  return concurrencyRounds(loaded).some(
    (round) =>
      dialectStatements(round.A?.statements ?? [], dialect).length > 0 ||
      dialectStatements(round.B?.statements ?? [], dialect).length > 0,
  );
}

/** One malformed concurrency-success step: its case pointer + the specific reason. */
interface ConcurrencyStepProblem {
  /** The `/concurrency/rounds/{i}/{node}` pointer of the offending step. */
  readonly pointer: string;
  /** Why the step is malformed (missing/invalid `kind`, or a `read` without `expectRows`). */
  readonly reason: string;
}

/**
 * Pre-flight structural validator for a concurrency-SUCCESS case: every PRESENT round
 * step MUST declare a valid `kind` (`"read"` or `"write"`), the EXPLICIT discriminator
 * {@link runConcurrencySuccess} branches on (a `read` is fetched + its rows compared; a
 * `write` only asserts it did not raise), AND a `kind: "read"` step MUST carry
 * `expectRows` (its rows are graded on the held session — without it the read would
 * silently grade against nothing). This replaces the old SQL-verb sniffing — a brittle
 * prefix match that could misclassify a write CTE or a novel read form.
 *
 * The schema already enforces both rules structurally (the concurrency-SUCCESS root
 * branch requires `kind`; the `kind` if/then requires `expectRows` on a read); this
 * re-checks them (pure, DB-free, timing-independent) as defense-in-depth mirroring the
 * Python harness's `_assert_concurrency_success_step_kinds`, so a malformed case fails
 * fast — before any session opens — with a clear pointer + reason rather than
 * mis-dispatching. Returns one {@link ConcurrencyStepProblem} per offending step (empty
 * when every present step declares a valid kind and every read carries `expectRows`).
 */
export function concurrencySuccessStepProblems(
  rounds: readonly ConcurrencyRound[],
): readonly ConcurrencyStepProblem[] {
  const problems: ConcurrencyStepProblem[] = [];
  rounds.forEach((round, index) => {
    for (const node of CONCURRENCY_NODES) {
      const step = round[node];
      if (step === undefined) {
        continue;
      }
      const pointer = `/concurrency/rounds/${index}/${node}`;
      if (step.kind !== "read" && step.kind !== "write") {
        problems.push({
          pointer,
          reason: `must declare kind: "read" | "write" (the explicit read-vs-write discriminator the runner branches on)`,
        });
        continue;
      }
      if (step.kind === "read" && step.expectRows === undefined) {
        problems.push({
          pointer,
          reason: `a kind: "read" step must declare expectRows (its rows are graded on the held session)`,
        });
      }
    }
  });
  return problems;
}

/** One `(casePointer, sql, binds)` per present node of every round, in round/A/B order. */
function concurrencyEmissions(loaded: LoadedCase, dialect: Dialect): Emission[] {
  const emissions: Emission[] = [];
  concurrencyRounds(loaded).forEach((round, roundIndex) => {
    for (const node of CONCURRENCY_NODES) {
      const statement = concurrencyStatement(round[node], dialect);
      if (statement === undefined) {
        continue;
      }
      emissions.push({
        casePointer: `/concurrency/rounds/${roundIndex}/${node}`,
        sql: statement.sql,
        binds: statement.binds as readonly WireBind[],
      });
    }
  });
  return emissions;
}

/**
 * Select the concrete {@link Dialect} for a run key (the dialect id keying each
 * golden statement's `sql` map). The runner is the m-case-format orchestrator, so it consults the concrete
 * dialect's pure rules directly (m-case-format → m-dialect). Both conforming dialects are
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
 * common read-operation pointer (`m-conformance-adapter.md` — both the
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

  // A `rejected` case carries a schema-valid but model-invalid input the adapter
  // MUST refuse BEFORE any SQL is emitted (m-value-object resolved Q7): it has no
  // golden, so the pre-SQL refusal IS the compile result — and it is checked
  // BEFORE the golden-per-dialect guard (which would otherwise skip it).
  if (loaded.shape === "rejected") {
    return rejectedEnvelope(loaded, "compile", adapter);
  }

  const notDeclared = dialectDeclaredOrNonOk(loaded, "compile", dialect, adapter);
  if (notDeclared) {
    return notDeclared;
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
    const plan = buildScenarioPlan(loaded, dialect);
    const emissions: Emission[] = plan.steps.flatMap((step) =>
      // A MULTI-statement step (a versioned set-based materialize write, `m-opt-lock-003` /
      // `m-opt-lock-004`) lists one `{sql, binds}` entry per per-object `UPDATE`, each
      // carrying its own inline binds.
      step.statements.map((statement) => ({
        casePointer: step.casePointer,
        sql: statement.sql,
        binds: statement.binds as readonly WireBind[],
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

  // A concurrency case — error (`m-read-lock-006`) or concurrency-success (`m-read-lock-007`/`m-read-lock-008`) — is
  // NOT compiled to SQL: its golden lives per round inside `concurrency.rounds` and is
  // authored, not derived. Surface those per-round statements as emissions (like a
  // scenario) so the compile gate classifies it in-claim `ok` instead of throwing at
  // `compileRootStatement` (`parseOperation(undefined)`); the real two-connection
  // behavior is graded by the run lane.
  if (loaded.shape === "error" || loaded.shape === "concurrencySuccess") {
    return compileOk(loaded, dialect, adapter, concurrencyEmissions(loaded, dialectFor(dialect)));
  }

  const { sql, binds } = compileRootStatement(loaded, dialectFor(dialect));
  // Canonicalize the compiled binds before REPORTING them: a value-object to-many read
  // carries the array-guard `rawJson('[]')` sentinel, which must collapse to the scalar
  // string `"[]"` so the envelope binds stay wire-scalar and byte-identical to the golden.
  const emission: Emission = {
    casePointer: READ_OPERATION_POINTER,
    sql,
    binds: canonicalBinds(binds) as readonly WireBind[],
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
 * operand compiled with the deep-fetch root projection). Both reuse the m-sql
 * `compile` visitor via a `MetamodelSchema`.
 */
function compileRootStatement(
  loaded: LoadedCase,
  dialect: Dialect,
): { sql: string; binds: readonly BindValue[] } {
  if (isDeepFetch(loaded.raw.when?.operation)) {
    const plan = buildDeepFetchPlan(loaded, dialect);
    return { sql: plan.root.sql, binds: plan.root.binds as readonly BindValue[] };
  }
  const operation = parseOperation(loaded.raw.when?.operation);
  const schema = schemaForReadCase(loaded, operation, dialect);
  // A `read-lock`-tagged case is a locking-mode object find: `compile()` applies the
  // dialect's shared-row-lock in-line after every other clause (m-read-lock automatic read-
  // lock correctness; the dialect owns the append — m-dialect), so the SQL is already
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

  // A `rejected` case is refused pre-SQL — no provisioning, no execution, no
  // dialect: the refusal is dialect-agnostic model-aware validation, and it is
  // checked BEFORE the golden-per-dialect guard (a rejected case has no golden).
  if (loaded.shape === "rejected") {
    return rejectedEnvelope(loaded, "run", adapter);
  }

  const notDeclared = dialectDeclaredOrNonOk(loaded, "run", dialect, adapter);
  if (notDeclared) {
    return notDeclared;
  }

  const dialectImpl = dialectFor(dialect);
  const operation = loaded.raw.when?.operation;

  // A write-sequence case constructs its own milestone history from its ordered
  // DML, so it provisions an EMPTY table (no fixtures) and asserts the resulting
  // `tableState` — the observable form of the milestone-chaining write contract.
  if (isWriteSequence(loaded)) {
    const { emissions, observations } = await runWriteSequence(loaded, provider, dialectImpl);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  // A conflict case loads fixtures, applies the out-of-band `given.apply` (a
  // concurrent writer), then the versioned UPDATE(s), and reports the affected-row
  // count + resulting `tableState` (the observable optimistic-lock contract).
  if (isConflict(loaded)) {
    const { emissions, observations } = await runConflict(loaded, provider, dialectImpl);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  // A scenario case commits its write steps and executes its finds against the
  // provisioned DB, reporting the observed rows + identity checks (m-unit-work read-your-
  // own-writes / cache / identity).
  if (isScenario(loaded)) {
    const { emissions, observations } = await runScenario(loaded, provider, dialect);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  // An error/concurrency case (`m-read-lock-006`) opens two held non-autocommit sessions,
  // runs the barrier-separated rounds, and asserts the contention round raises the
  // declared `errorClass` (a held `for share` read excludes B's UPDATE → a
  // lockWaitTimeout). This is the behavioral proof the single-connection read-lock
  // cases (`m-read-lock-001`/`m-read-lock-009`) cannot make.
  if (loaded.shape === "error") {
    const { emissions, observations } = await runErrorConcurrency(loaded, provider, dialectImpl);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  // A concurrency-success case (`m-read-lock-007`/`m-read-lock-008`) opens two held non-autocommit sessions
  // and runs the barrier-separated rounds asserting NO error is raised — the read
  // lock is SHARED (`m-read-lock-007`, a second reader is admitted) or ABSENT (`m-read-lock-008`, an
  // unlocked projection admits a writer) — and checks each read step's `expectRows` on
  // its HELD session. The behavioral control m-read-lock-006 (blocks a writer) cannot make.
  if (loaded.shape === "concurrencySuccess") {
    const { emissions, observations } = await runConcurrencySuccess(loaded, provider, dialectImpl);
    return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
  }

  await provision(loaded, provider);
  const { emissions, observations } = isDeepFetch(operation)
    ? await runDeepFetch(loaded, provider, dialectImpl)
    : isValueObjectGraph(loaded)
      ? await runValueObjectGraph(loaded, provider, dialectImpl)
      : await runFlatRead(loaded, provider, dialectImpl);
  return assertValidEnvelope(runOk(loaded, dialect, adapter, emissions, observations));
}

/**
 * Whether a read case materializes value objects with their owner (a `then.graph`
 * over an entity that declares value objects, and NOT a deep fetch): the whole
 * nested composite arrives with the owner in one round trip (m-value-object). This
 * distinguishes a value-object graph read (001-024/028-031's graph cases) from a
 * deep-fetch graph, which is keyed by `isDeepFetch`.
 */
function isValueObjectGraph(loaded: LoadedCase): boolean {
  if (loaded.shape !== "read" || loaded.raw.then?.graph === undefined) {
    return false;
  }
  if (isDeepFetch(loaded.raw.when?.operation)) {
    return false;
  }
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const operation = parseOperation(loaded.raw.when?.operation);
  const schema = schemaForReadCase(loaded, operation, dialectFor("postgres"));
  return metamodel.entity(schema.rootEntityName()).valueObjects().length > 0;
}

/**
 * Execute a value-object materialization read: run the single projected statement
 * (the golden projects the whole structured-document column through the graph
 * witness), decode each row's document into its DECLARED nested to-one / to-many
 * projection, and assemble `graph[rootEntity] = nodes` at `roundTrips: 1`. There
 * is NO child statement — the nested values ride the owner (m-value-object).
 */
async function runValueObjectGraph(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  const operation = parseOperation(loaded.raw.when?.operation);
  const schema = schemaForReadCase(loaded, operation, dialect);
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const rootEntity = metamodel.entity(schema.rootEntityName());
  const { sql, binds } = compile(operation, schema, dialect, { locking: false });

  // The provider gets the RAW binds (any `rawJson('[]')` guard sentinel must reach the
  // driver's json serializer verbatim); the REPORTED emission gets the canonicalized
  // scalars (the sentinel collapses to `"[]"` for the wire-scalar envelope).
  const rows = await provider.query(sql, binds as readonly unknown[]);
  const nodes = rows.map((row) => materializeOwnerNode(rootEntity, row as Row));
  const graph: Record<string, readonly Row[]> = { [rootEntity.name]: nodes };
  return {
    emissions: [
      {
        casePointer: READ_OPERATION_POINTER,
        sql,
        binds: canonicalBinds(binds) as readonly WireBind[],
      },
    ],
    observations: { roundTrips: 1, graph },
  };
}

/**
 * The pre-SQL refusal envelope for a `rejected` case (m-value-object resolved Q7):
 * run the model-aware value-object validator over the case's invalid `when`
 * (`operation` or `write`) against the queried entity's DECLARED value-object
 * structure and surface the {@link RejectionError}'s rule as an `error`-status
 * diagnostic (`code` == the rule, mechanically comparable to `then.rejectedRule`).
 * If validation ACCEPTS the input, that is itself the failure — an `error`
 * envelope whose code says the refusal never happened, so the grade fails loudly.
 */
function rejectedEnvelope(
  loaded: LoadedCase,
  command: "compile" | "run",
  adapter: AdapterIdentity,
): NonOk {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const [entity] = metamodel.entities();
  if (entity === undefined) {
    throw new Error(`${loaded.casePath}: rejected case model declares no entity`);
  }
  const when = loaded.raw.when as
    | { operation?: unknown; write?: Record<string, unknown> }
    | undefined;
  try {
    if (when?.operation !== undefined) {
      validateOperationValueObjects(entity, when.operation);
    } else if (when?.write !== undefined) {
      validateWriteValueObjects(entity, when.write);
    } else {
      throw new Error(
        `${loaded.casePath}: rejected case carries neither when.operation nor when.write`,
      );
    }
  } catch (error) {
    if (error instanceof RejectionError) {
      return nonOk(command, adapter, {
        code: error.rule,
        message: error.message,
        casePointer: when?.operation !== undefined ? "/operation" : "/write",
      });
    }
    throw error;
  }
  // Validation accepted a case the corpus pins as rejected — a conformance failure.
  return nonOk(command, adapter, {
    code: "rejected-input-accepted",
    message: `${loaded.casePath}: expected a pre-SQL rejection (${String(
      loaded.raw.then?.rejectedRule,
    )}) but model-aware validation accepted the input`,
    casePointer: "",
  });
}

/** Assemble an `error`-status envelope carrying a single diagnostic. */
function nonOk(
  command: "compile" | "run",
  adapter: AdapterIdentity,
  diagnostic: Diagnostic,
): NonOk {
  return {
    schemaVersion: "1",
    command,
    status: "error",
    adapter,
    diagnostics: [diagnostic],
  };
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
  const operation = parseOperation(loaded.raw.when?.operation);
  const schema = schemaForReadCase(loaded, operation, dialect);
  // A `read-lock`-tagged case is a locking-mode object find; `compile()` applies the
  // dialect's shared-row-lock in-line after every other clause (the lock does not
  // change rows), so the executed SQL is already locked.
  const { sql, binds } = compile(operation, schema, dialect, { locking: isReadLock(loaded) });

  // The provider gets the RAW binds (a value-object to-many read's `rawJson('[]')` guard
  // sentinel must reach the driver's json serializer verbatim); the REPORTED emission gets
  // the canonicalized scalars (the sentinel collapses to `"[]"` for the wire-scalar envelope).
  const rows = await provider.query(sql, binds as readonly unknown[]);
  return {
    emissions: [
      {
        casePointer: READ_OPERATION_POINTER,
        sql,
        binds: canonicalBinds(binds) as readonly WireBind[],
      },
    ],
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

  // Decode value-object documents at EVERY graph level (m-value-object
  // materialization at depth — `m-deep-fetch-018`): the deep-fetch assembler is
  // metamodel-free and carries raw structured-document columns, so decode each
  // level's rows to the declared value-object shape here, recursing along the
  // fetched relationship names. A non-value-object level passes through unchanged.
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const decoded = decodeGraphRows(result.rows as readonly Row[], plan.rootEntity, metamodel);

  const graph: Record<string, readonly Row[]> = {
    [plan.rootEntity]: decoded,
  };
  return {
    emissions,
    observations: { roundTrips: result.roundTrips, graph },
  };
}

/**
 * Decode value-object document columns at every level of an assembled deep-fetch
 * graph (m-value-object materialization at depth). Each node's own declared
 * top-level value-object columns are decoded + projected to the declared shape
 * (`materializeOwnerNode`, exactly as an owner read does); each fetched
 * relationship then recurses into its related entity, so a value-object-bearing
 * child (`m-deep-fetch-018`'s `Location.address`) materializes just like the root.
 * An entity with no value objects passes through as a shallow structural copy.
 */
function decodeGraphRows(
  rows: readonly Row[],
  entityName: string,
  metamodel: Metamodel,
): readonly Row[] {
  const entity = metamodel.entity(entityName);
  return rows.map((row) => {
    const node = materializeOwnerNode(entity, row) as Record<string, unknown>;
    for (const relationship of entity.relationships()) {
      if (!(relationship.name in node)) {
        continue;
      }
      const related = node[relationship.name];
      if (Array.isArray(related)) {
        node[relationship.name] = decodeGraphRows(
          related as readonly Row[],
          relationship.relatedEntity,
          metamodel,
        );
      } else if (related !== null && typeof related === "object") {
        node[relationship.name] = decodeGraphRows(
          [related as Row],
          relationship.relatedEntity,
          metamodel,
        )[0];
      }
    }
    return node as Row;
  });
}

/**
 * Execute a write sequence: provision an EMPTY table (the case builds its own
 * milestone history from its ordered DML — no fixtures), apply the generated DML
 * statements in order with the authored per-statement binds, then read back the
 * resulting `tableState` (every table the case's `then.tableState` names). One
 * emission per statement, `roundTrips` = statement count.
 */
async function runWriteSequence(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  await provisionEmpty(loaded, provider);
  // Pre-SQL, before classifying any row: a value-object write validates its
  // document against the declared recursive structure (m-value-object resolved
  // Q7) — a no-op for a valid write (the write cases here), but the same refusal
  // seam the `rejected` write cases prove. A structurally-invalid document raises
  // a RejectionError before any DML is generated.
  validateWriteSequenceDocuments(loaded);
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
 * Run the model-aware value-object write validator over every write-sequence
 * step's rows pre-SQL (m-value-object): each row's value-object documents are
 * checked against the declared recursive structure. A no-op for an entity with no
 * value objects, and for the valid value-object write cases; a structurally
 * invalid document raises a `RejectionError` before any DML is generated (the
 * refusal the `rejected` write cases pin).
 */
function validateWriteSequenceDocuments(loaded: LoadedCase): void {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const steps = (loaded.raw.when?.writeSequence ?? []) as readonly {
    entity?: string;
    rows?: readonly Record<string, unknown>[];
  }[];
  for (const step of steps) {
    if (step.entity === undefined) {
      continue;
    }
    const entity = metamodel.entity(step.entity);
    if (entity.valueObjects().length === 0) {
      continue;
    }
    for (const row of step.rows ?? []) {
      validateWriteValueObjects(entity, row);
    }
  }
}

/**
 * Execute a conflict case (m-opt-lock): provision + load fixtures (the versioned row
 * exists), apply the out-of-band `given.apply` (a concurrent writer) VERBATIM,
 * then apply the versioned UPDATE(s) — one per attempt — and report the LAST
 * attempt's affected-row count as `affectedRows` plus the resulting `tableState`.
 *
 * The single form has one attempt (`affectedRows` is that update's count); the
 * retry form has two (`m-opt-lock-007`: a stale attempt affects 0, the fresh retry affects
 * 1 — `affectedRows` reports the retry's 1, the terminal outcome). Each attempt's
 * count is checked against its declared `affectedRows` so a wrong count
 * fails loudly here, not only at the table-state grade. `roundTrips` counts the
 * versioned UPDATE(s) issued (the `given.apply` setup is out-of-band, not our runtime).
 */
async function runConflict(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  await provision(loaded, provider);
  const plan = buildConflictPlan(loaded, dialect);

  for (const statement of plan.apply) {
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
    if (affected !== attempt.affectedRows) {
      throw new Error(
        `attempt ${attempt.casePointer}: versioned UPDATE affected ${affected} row(s), ` +
          `expected ${attempt.affectedRows}`,
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
 * Execute a scenario (m-unit-work): provision + load fixtures, then run each step in order.
 * A WRITE step COMMITs its golden DML (a buffered write the unit of work flushes)
 * and captures no rows; a FIND step executes its golden `select` and captures the
 * observed rows (a cache-HIT step lists no golden and reuses a prior step's rows).
 * The `rows` observation is the LAST find's rows (`m-unit-work-001`'s dependent find that
 * MUST observe the committed write); `roundTrips` is the declared case total; each
 * `sameObjectAs` becomes an `identityChecks` entry (the one-object-per-PK rule).
 */
async function runScenario(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: string,
): Promise<RunResult> {
  await provision(loaded, provider);
  const plan = buildScenarioPlan(loaded, dialect);

  const emissions: Emission[] = [];
  const results: (readonly Row[])[] = [];
  let lastFindRows: readonly Row[] = [];
  const identityChecks: IdentityCheck[] = [];

  for (const [index, step] of plan.steps.entries()) {
    if (step.kind === "write") {
      // A step may emit SEVERAL statements (a versioned set-based materialize write,
      // `m-opt-lock-003` / `m-opt-lock-004`: one per-object `UPDATE` per row); each
      // `{sql, binds}` entry carries its own inline binds.
      for (const statement of step.statements) {
        emissions.push({
          casePointer: step.casePointer,
          sql: statement.sql,
          binds: statement.binds as readonly WireBind[],
        });
        // A `rollback: true` step applies the DML then ROLLS IT BACK (the m-unit-work abort
        // contract): the write lands in an atomic scope that is discarded, so a
        // later find MUST observe the ORIGINAL rows. A default write COMMITs.
        if (step.rollback === true) {
          await provider.execRolledBack(statement.sql, statement.binds);
        } else {
          await provider.exec(statement.sql, statement.binds);
        }
      }
      results.push([]);
      continue;
    }

    // A find step: execute its golden (a cache hit lists none and reuses a prior
    // step's rows via `sameObjectAs`, or the immediately-preceding step). A find is
    // single-statement, so its binds are that statement's inline binds.
    let rows: readonly Row[];
    const [find] = step.statements;
    if (find !== undefined) {
      emissions.push({
        casePointer: step.casePointer,
        sql: find.sql,
        binds: find.binds as readonly WireBind[],
      });
      rows = (await provider.query(find.sql, find.binds)) as readonly Row[];
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

/**
 * Execute an error/concurrency case (`m-read-lock-006`, the m-db-error deadlock/lock-wait family):
 * provision + load fixtures, open TWO held non-autocommit sessions (each on its
 * own independent connection with a lowered lock-wait budget via the provider's
 * `openSession` seam), then run the barrier-separated rounds. A round with a
 * single node runs awaited (the holder acquires + keeps its lock); a round with
 * BOTH nodes runs them concurrently (the crossing that provokes a deadlock). The
 * contention round MUST raise a portable {@link ParallaxTransientError}; we assert
 * its `kind` equals the case's declared `errorClass` AND its driver-native code
 * equals the declared `then.nativeCode[dialect]`, and that NOTHING unexpected was
 * raised elsewhere. Sessions are always rolled back + closed (whichever opened). No
 * rows are observed — the case's whole assertion is "the lock
 * held, so the writer was excluded / classified", proven inside this function
 * (a buggy adapter whose lock has no effect raises nothing and fails here).
 */
async function runErrorConcurrency(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  await provision(loaded, provider);
  const rounds = concurrencyRounds(loaded);
  const errorClass = String(loaded.raw.then?.errorClass);

  const emissions: Emission[] = [];
  const raised: unknown[] = [];
  // The two held sessions, opened lazily INSIDE the `try` (below) and tracked here
  // so `finally` rolls back + closes whichever actually opened — a failure opening B
  // must never orphan an already-open A.
  const sessions: Partial<Record<ConcurrencyNode, CompatibilitySession>> = {};

  const runStep = async (node: ConcurrencyNode, round: ConcurrencyRound, index: number) => {
    const statement = concurrencyStatement(round[node], dialect);
    const session = sessions[node];
    if (statement === undefined || session === undefined) {
      return;
    }
    emissions.push({
      casePointer: `/concurrency/rounds/${index}/${node}`,
      sql: statement.sql,
      binds: statement.binds as readonly WireBind[],
    });
    try {
      await session.execute(statement.sql, statement.binds);
    } catch (error) {
      raised.push(error);
    }
  };

  try {
    // Open both held sessions here (not in a pre-`try` initializer): if B's
    // `openSession` throws, A is already tracked in `sessions` and rolled back below.
    sessions.A = await provider.openSession();
    sessions.B = await provider.openSession();
    for (const [index, round] of rounds.entries()) {
      const active = CONCURRENCY_NODES.filter((node) => round[node] !== undefined);
      if (active.length > 1) {
        // Both nodes act this round — run them concurrently (the deadlock crossing).
        await Promise.all(active.map((node) => runStep(node, round, index)));
      } else {
        // A single node holds (round 0) or contends (round 1) — run it awaited.
        for (const node of active) {
          await runStep(node, round, index);
        }
      }
    }
  } finally {
    // Roll back BOTH sessions, then close BOTH — each step independent + guarded so
    // one session's rejecting rollback/close never skips the other's cleanup (a
    // leaked held connection). An unopened session (`?.`) is a no-op.
    for (const node of CONCURRENCY_NODES) {
      await sessions[node]?.rollback().catch(() => {});
    }
    for (const node of CONCURRENCY_NODES) {
      await sessions[node]?.close().catch(() => {});
    }
  }

  // Success is exactly "the declared transient was raised and NOTHING else": any
  // recorded error that is non-transient, or a transient of the wrong `kind`, fails
  // here rather than being masked by a matching sibling error (an unexpected failure
  // in one step must not pass silently because another produced the expected one).
  const unexpected = raised.find(
    (error) => !(error instanceof ParallaxTransientError) || error.kind !== errorClass,
  );
  if (unexpected !== undefined) {
    throw new Error(
      `${loaded.casePath}: expected only a ${errorClass} transient, but also raised: ${String(unexpected)}`,
    );
  }
  const transient = raised.find(
    (error): error is ParallaxTransientError => error instanceof ParallaxTransientError,
  );
  if (transient === undefined) {
    throw new Error(
      `${loaded.casePath}: expected the contention round to raise a ${errorClass}, ` +
        `but no ParallaxTransientError was raised (the lock had no effect?)`,
    );
  }
  // Assert the case's declared native code too (not just the neutral `kind`): the
  // portable transient preserves the driver's native error as `cause`, where
  // Postgres carries the SQLSTATE string on `.code` ("55P03") and MariaDB the vendor
  // errno on `.errno` (1205). Prefer `.errno` so MariaDB's numeric code wins over its
  // symbolic `.code` name; compare via string coercion so a numeric errno and a
  // string SQLSTATE each match their declared value.
  const cause = transient.cause as { code?: string | number; errno?: number } | null | undefined;
  const nativeCode = cause?.errno ?? cause?.code;
  const expected = loaded.raw.then?.nativeCode?.[dialect.id];
  if (expected !== undefined && String(nativeCode) !== String(expected)) {
    throw new Error(
      `${loaded.casePath}: raised native code '${String(nativeCode)}', expected '${String(expected)}'`,
    );
  }

  return { emissions, observations: { roundTrips: emissions.length } };
}

/** Render one **managed** row (§3.2.1) to its neutral wire form for row grading. */
function renderManagedRowToWire(row: ParallaxRow): Row {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(row)) {
    out[key] = toWire(value);
  }
  return out as Row;
}

/**
 * Execute a concurrency-SUCCESS case (`m-read-lock-007` read-lock-shared-compatible, `m-read-lock-008`
 * projection-omits-lock-admits-writer): provision + load fixtures, open TWO held
 * non-autocommit sessions, and run the barrier-separated rounds asserting NO error is
 * raised on either node. A round runs its single node awaited (round 0 holds, round 1
 * proceeds), so round 0's lock/read is held before round 1 — the ordering the Python
 * harness's `threading.Barrier` gives, here from awaiting rounds in order over two
 * INDEPENDENT held connections. A `kind: read` step fetches on its HELD session
 * (`session.query` — a `for share` SELECT both takes its shared lock and returns its
 * rows) and the observed rows are graded (rendered to wire, compared as an
 * order-insensitive multiset under the m-case-format type-aware rules); a `kind: write` step
 * asserts only that it did not block/raise (`m-read-lock-008`'s admitted UPDATE).
 *
 * Success is exactly "NO node raised AND every `expectRows` matched": a buggy adapter
 * whose read took an EXCLUSIVE lock (`for update` not `for share`) — or that wrongly
 * locked the projection — blocks the peer, whose contention times out and raises here.
 * Sessions are always rolled back + closed (releasing any lock a held read took).
 */
async function runConcurrencySuccess(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
  dialect: Dialect,
): Promise<RunResult> {
  const rounds = concurrencyRounds(loaded);
  // Pre-flight structural guard (DB-free, timing-independent): every success step must
  // declare an explicit `kind` (`read` | `write`), the discriminator this runner
  // dispatches on, and every `kind: read` step must carry `expectRows` (graded on its
  // held session — else the read would silently grade against nothing). Fail fast BEFORE
  // provisioning / opening any session so a mis-declared step surfaces a deterministic
  // diagnostic and never races the lock choreography (mirrors the Python harness).
  const problems = concurrencySuccessStepProblems(rounds);
  if (problems.length > 0) {
    throw new Error(
      `${loaded.casePath}: malformed concurrency-success step(s) — ` +
        problems.map((problem) => `${problem.pointer}: ${problem.reason}`).join("; "),
    );
  }
  await provision(loaded, provider);
  const columnTypes = columnTypesForCase(loaded);

  const emissions: Emission[] = [];
  const raised: unknown[] = [];
  const rowFailures: string[] = [];
  // The two held sessions, opened lazily INSIDE the `try` and tracked here so `finally`
  // rolls back + closes whichever actually opened (a failed open of B must not orphan A).
  const sessions: Partial<Record<ConcurrencyNode, CompatibilitySession>> = {};

  const runStep = async (node: ConcurrencyNode, round: ConcurrencyRound, index: number) => {
    const step = round[node];
    const statement = concurrencyStatement(step, dialect);
    const session = sessions[node];
    if (statement === undefined || session === undefined) {
      return;
    }
    const { sql, binds } = statement;
    emissions.push({
      casePointer: `/concurrency/rounds/${index}/${node}`,
      sql,
      binds: binds as readonly WireBind[],
    });
    try {
      if (step?.kind === "read") {
        // A read step: fetch on the HELD session (a shared-lock SELECT takes its lock
        // here), render the managed rows to wire, and grade against `expectRows`. The
        // pre-flight `concurrencySuccessStepProblems` guard guarantees a `kind: read`
        // step carries `expectRows`, so read it directly — a defensive `?? []` fallback
        // here can never trigger and would only silently grade a malformed read (a
        // missing `expectRows`) against an empty expectation instead of failing loudly.
        const observed = (await session.query(sql, binds)).map(renderManagedRowToWire);
        const expect = step.expectRows as readonly Row[];
        const comparison = compareRowSet(observed, expect, columnTypes);
        if (!comparison.equal) {
          rowFailures.push(`/concurrency/rounds/${index}/${node}: ${comparison.reason}`);
        }
      } else {
        // A write step (`m-read-lock-008`'s round-1 UPDATE): succeeds iff no lock blocks it.
        await session.execute(sql, binds);
      }
    } catch (error) {
      raised.push(error);
    }
  };

  try {
    sessions.A = await provider.openSession();
    sessions.B = await provider.openSession();
    for (const [index, round] of rounds.entries()) {
      const active = CONCURRENCY_NODES.filter((node) => round[node] !== undefined);
      if (active.length > 1) {
        await Promise.all(active.map((node) => runStep(node, round, index)));
      } else {
        for (const node of active) {
          await runStep(node, round, index);
        }
      }
    }
  } finally {
    for (const node of CONCURRENCY_NODES) {
      await sessions[node]?.rollback().catch(() => {});
    }
    for (const node of CONCURRENCY_NODES) {
      await sessions[node]?.close().catch(() => {});
    }
  }

  // No node may raise (the lock is shared / absent), and every declared `expectRows`
  // must match — either failure surfaces here (the run envelope stays `ok`; the
  // behavioral proof lives inside this function, like the error path's classification).
  if (raised.length > 0) {
    throw new Error(
      `${loaded.casePath}: expected NO error (the shared read lock is compatible / absent), ` +
        `but a node raised: ${raised.map(String).join("; ")}`,
    );
  }
  if (rowFailures.length > 0) {
    throw new Error(
      `${loaded.casePath}: held-session rows != expectRows — ${rowFailures.join("; ")}`,
    );
  }

  return { emissions, observations: { roundTrips: emissions.length } };
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
 * Read the resulting state of every table the case's `then.tableState` names,
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
  const expected = loaded.raw.then?.tableState ?? {};
  const state: Record<string, readonly Row[]> = {};
  for (const table of Object.keys(expected)) {
    const entity = byTable.get(table);
    if (entity === undefined) {
      throw new Error(`then.tableState names table '${table}' not in the model`);
    }
    const rows = (await provider.query(readTableSql(entity, dialect), [])) as readonly Row[];
    // Decode each top-level value-object document column so `then.tableState`'s
    // authored document compares structurally on both dialects (Postgres returns
    // a parsed jsonb, MariaDB raw json text) — m-value-object write read-back.
    state[table] = rows.map((row) => decodeTableStateRow(entity, row));
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
  // Attribute columns then one structured-document column per top-level value
  // object (m-value-object), so a value-object write reads its document back.
  const columns = orderedColumns(entity);
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
 * `given.fixtures` (the per-key batched-update case `m-batch-write-002` mutates pre-existing
 * fixture rows), in which case the model's fixtures are loaded first (mirrors the
 * Python harness `_provision_empty`).
 */
async function provisionEmpty(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
): Promise<void> {
  await provider.reset();
  await provider.applyDdl(ddlForDescriptor(loaded.descriptor));
  if (loaded.raw.given?.fixtures === true) {
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
    // Attribute columns then one structured-document column per top-level value
    // object (m-value-object); a fixture row speaks attribute / value-object
    // NAMES, so map each physical column back to the name that supplies it (the
    // value-object document rides its column atomically).
    const columns = orderedColumns(entity);
    const nameByColumn = new Map<string, string>([
      ...entity.attributes().map((a) => [a.column, a.name] as const),
      ...entity.valueObjects().map((vo) => [vo.column, vo.name] as const),
    ]);
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
 * Route a case that declares **no golden SQL for the active dialect** to a skip
 * `unsupported` envelope, or `undefined` (the case declares golden — proceed). This is
 * the pre-run mirror of the Python oracle's per-dialect skip (`case_runner.run_case`),
 * which runs only the dialect-agnostic checks and returns when a case authors no golden
 * for the active dialect. It is a SEPARATE pre-run check, not a gate condition — the
 * gate ({@link gateOrNonOk}) stays the pure capability-claim contract; this is a
 * correctness-by-construction parity guard applied AFTER the gate + lane-skip.
 *
 * In the current corpus every in-claim (Postgres) case declares Postgres golden, so this
 * branch does not fire in the harness sweeps; it exists so a future dialect-partial case
 * routes to a skip (like the oracle) instead of the runner trying to compile / execute a
 * dialect the case never authored. The diagnostic `code` is free-form (the envelope
 * `status` stays the schema's `unsupported`).
 */
function dialectDeclaredOrNonOk(
  loaded: LoadedCase,
  command: "compile" | "run",
  dialect: string,
  adapter: AdapterIdentity,
): NonOk | undefined {
  if (caseDeclaresGoldenForDialect(loaded, dialect)) {
    return undefined;
  }
  const diagnostic: Diagnostic = {
    code: "dialect-not-declared",
    message: `case declares no golden SQL for dialect '${dialect}'`,
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
 * to the `read`-shape read-lock matrix cases (`m-read-lock-002`-`m-read-lock-005`) that carry
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
