/**
 * Build an executable **scenario plan** from a loaded case (m-unit-work unit-of-work
 * cache / identity + m-case-format).
 *
 * A `scenario` case is an ordered list of steps (`when.scenario`) that prove the
 * cache / identity / read-your-own-writes contract against a real database. Two
 * step kinds:
 *
 *  - a **write** step COMMITs its golden DML (a buffered write the unit of work
 *    flushes) — it captures no rows but its committed state is observable by a
 *    later find; and
 *  - a **find** step executes its golden `select` and asserts `expectRows`; a
 *    cache-HIT step lists no golden SQL and reuses a prior step's rows
 *    (`sameObjectAs`), costing zero round trips.
 *
 * A scenario is NEVER compiled to SQL by the adapter (the golden per step is
 * authored, not derived — `m-case-format.md`): read-your-own-writes,
 * cache reuse and identity are observable RUN properties. This module resolves the
 * ordered steps + their authored golden statement entries so the runner can execute
 * them; each `{sql, binds}` entry carries its own binds inline (no positional
 * pairing). The `m-unit-work-001` slice is the single read-your-own-writes scenario
 * (a committed insert + a dependent find that MUST observe it), `roundTrips` 2.
 */
import { type DialectStatement, dialectStatements, type StatementEntry } from "./case-format.js";
import type { LoadedCase } from "./discover.js";

/** A scenario step: a committed write or a find (with its authored golden). */
export interface ScenarioStep {
  /** The step kind. */
  readonly kind: "write" | "find";
  /** The m-conformance-adapter case pointer for this step (`/scenario/<index>`). */
  readonly casePointer: string;
  /**
   * The ordered golden statements this step executes (empty for a cache hit), each
   * carrying its own inline binds. A multi-statement write step (a versioned
   * set-based materialize write, `m-opt-lock-003` / `m-opt-lock-004`) lists one entry
   * per per-object `UPDATE`; a single-statement find lists one.
   */
  readonly statements: readonly DialectStatement[];
  /** The declared round-trip cost of the step (0 for a cache hit). */
  readonly roundTrips: number;
  /**
   * A write step's abort flag (m-unit-work abort contract): when true its DML is applied
   * then ROLLED BACK, so a later find observes the ORIGINAL rows. Absent / false
   * for a committed write or a find step.
   */
  readonly rollback?: boolean;
  /** The rows a find step asserts (absent for a write or an unasserted find). */
  readonly expectRows?: readonly Record<string, unknown>[];
  /** A `sameObjectAs` reference to an earlier step (identity reuse), if declared. */
  readonly sameObjectAs?: number;
}

/** The executable scenario plan: the ordered steps + the case round-trip total. */
export interface ScenarioPlan {
  readonly steps: readonly ScenarioStep[];
  /** The case-level `then.roundTrips` (equals the sum of the per-step round trips). */
  readonly roundTrips: number;
}

/** True when a case's shape is a scenario. */
export function isScenario(loaded: LoadedCase): boolean {
  return loaded.shape === "scenario";
}

/**
 * A scenario step as authored in `when.scenario`. The step schema keys read-vs-write
 * on a `oneOf` (so the generated static view is a loose object); this reader names
 * the members the runner consumes.
 */
interface RawScenarioStep {
  readonly write?: string;
  readonly rollback?: boolean;
  readonly find?: unknown;
  readonly statements?: readonly StatementEntry[];
  readonly roundTrips?: number;
  readonly expectRows?: readonly Record<string, unknown>[];
  readonly sameObjectAs?: number;
}

/**
 * Build the scenario plan: resolve each step's kind, golden, binds and asserts for
 * the run's active `dialect` (the dialect id keying each step's golden `sql` map). A
 * step whose golden omits `dialect` resolves to zero statements — the caller must
 * skip a scenario the case declares no golden for on the active dialect (mirroring
 * the Python oracle's per-dialect skip), rather than silently emitting another
 * dialect's SQL.
 */
export function buildScenarioPlan(loaded: LoadedCase, dialect: string): ScenarioPlan {
  const rawSteps = (loaded.raw.when?.scenario ?? []) as readonly RawScenarioStep[];
  const steps = rawSteps.map((raw, index) => normalizeStep(raw, index, dialect));
  return {
    steps,
    roundTrips: loaded.raw.then?.roundTrips ?? sumRoundTrips(steps),
  };
}

/** Normalize one raw step into a {@link ScenarioStep} for the active `dialect`. */
function normalizeStep(raw: RawScenarioStep, index: number, dialect: string): ScenarioStep {
  const kind = "write" in raw && raw.write !== undefined ? "write" : "find";
  return {
    kind,
    casePointer: `/scenario/${index}`,
    statements: dialectStatements(raw.statements ?? [], dialect),
    roundTrips: raw.roundTrips ?? 0,
    ...(raw.rollback === undefined ? {} : { rollback: raw.rollback }),
    ...(raw.expectRows === undefined ? {} : { expectRows: raw.expectRows }),
    ...(raw.sameObjectAs === undefined ? {} : { sameObjectAs: raw.sameObjectAs }),
  };
}

/** The sum of the per-step round trips (the case-level total). */
function sumRoundTrips(steps: readonly ScenarioStep[]): number {
  return steps.reduce((total, step) => total + step.roundTrips, 0);
}
