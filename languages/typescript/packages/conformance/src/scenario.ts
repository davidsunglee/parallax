/**
 * Build an executable **scenario plan** from a loaded case (M8 unit-of-work
 * cache / identity + M12).
 *
 * A `scenario` case is an ordered list of steps that prove the cache / identity /
 * read-your-own-writes contract against a real database. Two step kinds:
 *
 *  - a **write** step COMMITs its golden DML (a buffered write the unit of work
 *    flushes) — it captures no rows but its committed state is observable by a
 *    later find; and
 *  - a **find** step executes its golden `select` and asserts `expectRows`; a
 *    cache-HIT step lists no golden SQL and reuses a prior step's rows
 *    (`sameObjectAs`), costing zero round trips.
 *
 * A scenario is NEVER compiled to SQL by the adapter (the golden per step is
 * authored, not derived — `m12-compatibility-harness.md`): read-your-own-writes,
 * cache reuse and identity are observable RUN properties. This module resolves the
 * ordered steps + their authored golden/binds so the runner can execute them; the
 * `m-unit-work-001` slice is the single read-your-own-writes scenario (a committed insert +
 * a dependent find that MUST observe it), `roundTrips` 2.
 */
import type { LoadedCase } from "./discover.js";

/** A scenario step: a committed write or a find (with its authored golden). */
export interface ScenarioStep {
  /** The step kind. */
  readonly kind: "write" | "find";
  /** The JSON Pointer into the case (`/scenario/<index>`). */
  readonly casePointer: string;
  /** The ordered golden statements this step executes (empty for a cache hit). */
  readonly statements: readonly string[];
  /** The authored binds (a flat row for a single statement). */
  readonly binds: readonly unknown[];
  /** The declared round-trip cost of the step (0 for a cache hit). */
  readonly roundTrips: number;
  /**
   * A write step's abort flag (M8 abort contract): when true its DML is applied
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
  /** The case-level `roundTrips` (equals the sum of the per-step round trips). */
  readonly roundTrips: number;
}

/** True when a case's shape is a scenario. */
export function isScenario(loaded: LoadedCase): boolean {
  return loaded.shape === "scenario";
}

/** A raw scenario step as authored in the case YAML. */
interface RawScenarioStep {
  readonly write?: string;
  readonly rollback?: boolean;
  readonly find?: unknown;
  readonly goldenSql?: { readonly postgres?: string | readonly string[] };
  readonly binds?: readonly unknown[];
  readonly roundTrips?: number;
  readonly expectRows?: readonly Record<string, unknown>[];
  readonly sameObjectAs?: number;
}

/** Build the scenario plan: resolve each step's kind, golden, binds and asserts. */
export function buildScenarioPlan(loaded: LoadedCase): ScenarioPlan {
  const rawSteps = (loaded.raw.scenario as readonly RawScenarioStep[] | undefined) ?? [];
  const steps = rawSteps.map((raw, index) => normalizeStep(raw, index));
  return {
    steps,
    roundTrips: (loaded.raw.roundTrips as number | undefined) ?? sumRoundTrips(steps),
  };
}

/** Normalize one raw step into a {@link ScenarioStep}. */
function normalizeStep(raw: RawScenarioStep, index: number): ScenarioStep {
  const kind = "write" in raw && raw.write !== undefined ? "write" : "find";
  return {
    kind,
    casePointer: `/scenario/${index}`,
    statements: stepStatements(raw),
    binds: (raw.binds ?? []) as readonly unknown[],
    roundTrips: raw.roundTrips ?? 0,
    ...(raw.rollback === undefined ? {} : { rollback: raw.rollback }),
    ...(raw.expectRows === undefined ? {} : { expectRows: raw.expectRows }),
    ...(raw.sameObjectAs === undefined ? {} : { sameObjectAs: raw.sameObjectAs }),
  };
}

/** The ordered golden `postgres` statements a step lists (empty for a cache hit). */
function stepStatements(raw: RawScenarioStep): readonly string[] {
  const golden = raw.goldenSql?.postgres;
  if (golden === undefined) {
    return [];
  }
  return typeof golden === "string" ? [golden] : [...golden];
}

/** The sum of the per-step round trips (the case-level total). */
function sumRoundTrips(steps: readonly ScenarioStep[]): number {
  return steps.reduce((total, step) => total + step.roundTrips, 0);
}

/**
 * The binds for statement `index` of a (possibly MULTI-statement) scenario step.
 * A step with several golden statements (a versioned set-based materialize write —
 * one per-object `UPDATE` per row, `m-opt-lock-003` / `m-opt-lock-004`) carries a LIST-OF-LISTS `binds`,
 * one bind list per statement; a single-statement step carries a flat list. Mirrors
 * the reference harness's `_binds_for_list`, so the TS runner slices per-statement
 * exactly as the Python harness does. A flat list is the binds for statement 0.
 */
export function stepBindsAt(binds: readonly unknown[], index: number): readonly unknown[] {
  if (binds.length > 0 && Array.isArray(binds[0])) {
    return (binds[index] as readonly unknown[] | undefined) ?? [];
  }
  return index === 0 ? binds : [];
}
