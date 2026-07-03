/**
 * Transaction / write-sequence / locking **compile lane** over the M8 + M10
 * corpus (`06xx` + `07xx`), Docker-free.
 *
 * Drives the adapter's `runCompile` — the same path the CLI exercises — over the
 * ten `slice-mvp-1` `06xx`/`07xx` cases, asserting the emitted SQL +
 * binds equal the golden BY TEXT. The four shapes this slice exercises for the
 * first time:
 *
 *  - **read-lock** (`0603`, `read` shape + `read-lock` tag): the single emission is
 *    the plain `eq` read with the dialect lock suffix `for share of t0` appended;
 *  - **write sequence** (`0604`/`0612`/`0613`, batched non-temporal writes): one
 *    emission per generated DML statement — a multi-row `INSERT`, a uniform
 *    `pk in (…)` update, one keyed `UPDATE` per distinct key — each keyed by its
 *    `/writeSequence/<step>` pointer, `roundTrips` the statement count;
 *  - **scenario** (`0607`, read-your-own-writes; `0608`, rollback/abort): a scenario
 *    is NOT compiled to SQL, but the adapter surfaces the per-step golden so the
 *    gate classifies it in-claim, `roundTrips` the declared case total;
 *  - **conflict** (`0703`/`0704`/`0707`/`0708`, optimistic locking): one emission
 *    per attempt's generated versioned `UPDATE`, keyed by its case pointer.
 *
 * The Docker-gated run lane (`@parallax/typescript`'s `txn-run.test.ts`) proves
 * the SQL leaves the right rows / table state / affected-row counts.
 */
import { describe, expect, it } from "vitest";
import { isConflict } from "../src/conflict.js";
import { discoverCasePaths, loadCase } from "../src/discover.js";
import { runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";
import { isScenario } from "../src/scenario.js";
import { isWriteSequence } from "../src/write-sequence.js";

/** The in-scope `06xx`/`07xx` MVP cases (the four Phase-7 shapes). */
function txnCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^(06|07)\d\d$/.test(id))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("slice-mvp-1"))
    .map(({ id, path }) => ({ id, path }));
}

/**
 * The EXACT in-scope `06xx`/`07xx` MVP id set: read-lock `0603`, batched writes
 * `0604`/`0612`/`0613`, read-your-own-writes `0607`, rollback/abort `0608`, and the
 * optimistic-lock conflict/retry `0703`/`0704`/`0707`/`0708`. Asserting the exact set fails loudly
 * on a discovery regression (the untagged pkgen / cache / cascade / detached-merge
 * / error-class `06xx`/`07xx` cases must NOT leak in).
 */
const EXPECTED_IDS: readonly string[] = [
  "0603",
  "0604",
  "0607",
  "0608",
  "0612",
  "0613",
  "0703",
  "0704",
  "0707",
  "0708",
];

const CASES = txnCases();

/** The ordered golden `postgres` statements a case declares, per its shape. */
function goldenStatements(loaded: ReturnType<typeof loadCase>): readonly string[] {
  if (isScenario(loaded)) {
    const steps = (loaded.raw.scenario as { goldenSql?: { postgres?: string } }[]) ?? [];
    return steps.flatMap((step) => (step.goldenSql?.postgres ? [step.goldenSql.postgres] : []));
  }
  if (isConflict(loaded)) {
    const attempts = loaded.raw.attempts as { goldenSql?: { postgres?: string } }[] | undefined;
    if (attempts) {
      return attempts.map((attempt) => attempt.goldenSql?.postgres ?? "");
    }
    return [(loaded.raw.goldenSql as { postgres?: string }).postgres ?? ""];
  }
  const golden = (loaded.raw.goldenSql as { postgres?: string | string[] }).postgres;
  if (golden === undefined) {
    return [];
  }
  return Array.isArray(golden) ? golden : [golden];
}

/** The authored binds a case declares (flat for a single read, list-of-lists otherwise). */
function goldenBinds(loaded: ReturnType<typeof loadCase>): readonly (readonly unknown[])[] {
  if (isScenario(loaded)) {
    const steps =
      (loaded.raw.scenario as { goldenSql?: { postgres?: string }; binds?: unknown[] }[]) ?? [];
    return steps.flatMap((step) => (step.goldenSql?.postgres ? [step.binds ?? []] : []));
  }
  if (isConflict(loaded)) {
    const attempts = loaded.raw.attempts as { binds?: unknown[] }[] | undefined;
    if (attempts) {
      return attempts.map((attempt) => attempt.binds ?? []);
    }
    return [(loaded.raw.binds as unknown[] | undefined) ?? []];
  }
  const binds = loaded.raw.binds as unknown[] | unknown[][] | undefined;
  if (binds === undefined) {
    return [[]];
  }
  return Array.isArray(binds[0]) ? (binds as unknown[][]) : [binds as unknown[]];
}

describe("txn compile lane — emitted === golden over the 06xx + 07xx corpus", () => {
  it("discovers exactly the in-scope 06xx + 07xx MVP cases", () => {
    expect(CASES.map(({ id }) => id).sort()).toEqual([...EXPECTED_IDS].sort());
  });

  it.each(CASES)("$id compiles to the golden Postgres SQL + binds", ({ path }) => {
    const loaded = loadCase(path);
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }

    expect(envelope.emissions.map((e) => e.sql)).toEqual(goldenStatements(loaded));
    expect(envelope.emissions.map((e) => e.binds)).toEqual(goldenBinds(loaded));

    // Shape-specific `roundTrips` + case-pointer conventions.
    if (isWriteSequence(loaded) || isConflict(loaded)) {
      expect(envelope.roundTrips).toBe(envelope.emissions.length);
    }
    if (isScenario(loaded)) {
      expect(envelope.roundTrips).toBe(loaded.raw.roundTrips);
    }
    if (loaded.shape === "read") {
      expect(envelope.emissions).toHaveLength(1);
      expect(envelope.emissions[0]?.casePointer).toBe("/operation");
      expect(envelope.roundTrips).toBe(1);
    }
  });
});
