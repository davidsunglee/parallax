/**
 * Transaction / write-sequence / locking **compile lane** over the M8 + M10
 * corpus (`06xx` + `07xx`), Docker-free.
 *
 * Drives the adapter's `runCompile` — the same path the CLI exercises — over the
 * twenty-one `slice-mvp-1` `06xx`/`07xx` harness-lane cases, asserting the emitted
 * SQL + binds equal the golden BY TEXT. The six shapes this slice exercises for
 * the first time:
 *
 *  - **read-lock** (`0603`, `read` shape + `read-lock` tag): the single emission is
 *    the plain `eq` read with the dialect lock suffix `for share of t0` appended;
 *  - **write sequence** (`0604`/`0612`/`0613` batched non-temporal writes on the
 *    non-versioned `Wallet`; `0611` locking-mode versioned update): one emission
 *    per generated DML statement — a multi-row `INSERT`, a uniform `pk in (…)`
 *    update, one keyed `UPDATE` per distinct key, or the ungated version-advancing
 *    `UPDATE` — each keyed by its `/writeSequence/<step>` pointer;
 *  - **scenario** (`0607`, read-your-own-writes; `0608`, rollback/abort; `0609`,
 *    no-op-update-no-DML; `0614`/`0615`, versioned set-based materialize — whose
 *    write step lists SEVERAL per-object `UPDATE`s): a scenario is NOT compiled to
 *    SQL, but the adapter surfaces the per-step golden so the gate classifies it
 *    in-claim, `roundTrips` the declared case total;
 *  - **conflict** (`0703`/`0704`/`0708`, optimistic locking; `0730`-`0733`,
 *    optimistic × temporal close): one emission per attempt's generated versioned
 *    `UPDATE` / gated milestone close, keyed by its case pointer;
 *  - **error** (`0728`, read-lock-blocks-writer): NOT compiled to SQL — its golden
 *    lives per round in `concurrency.rounds`, surfaced as one emission per node so
 *    the gate classifies it in-claim (the two-connection behavior is run-lane only);
 *  - **concurrencySuccess** (`0729`, read-lock-shared-compatible; `0734`,
 *    projection-omits-lock-admits-writer): like `error`, NOT compiled to SQL — the
 *    per-round `concurrency.rounds` golden is surfaced as one emission per node (the
 *    two-connection "no error + expectRows on the held session" proof is run-lane only).
 *
 * The Docker-gated Postgres full M12 profile (`@parallax/typescript`'s
 * `slice-run.test.ts`) proves the SQL leaves the right rows / table state /
 * affected-row counts.
 */
import { describe, expect, it } from "vitest";
import { isConflict } from "../src/conflict.js";
import { discoverCasePaths, loadCase } from "../src/discover.js";
import { runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";
import { isScenario } from "../src/scenario.js";
import { isWriteSequence } from "../src/write-sequence.js";

/**
 * The in-scope `06xx`/`07xx` MVP cases the HARNESS compiles (the four Phase-7
 * shapes + the harness-lane auto-retry `0710`). `api-conformance`-lane cases (the
 * read-lock matrix `0616`-`0619`, the boundary retry cases `0711`-`0718`) are
 * excluded — they have no harness-compiled golden (the API Conformance Suite
 * satisfies them), so `runCompile` routes them to a suite-satisfied `unsupported`.
 */
function txnCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^(06|07)\d\d$/.test(id))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("slice-mvp-1"))
    .filter(({ loaded }) => loaded.lane !== "api-conformance")
    .map(({ id, path }) => ({ id, path }));
}

/**
 * The EXACT in-scope harness-lane `06xx`/`07xx` MVP id set: read-lock `0603`,
 * batched writes `0604`/`0612`/`0613`, read-your-own-writes `0607`, rollback/abort
 * `0608`, no-op update `0609`, locking-mode versioned update `0611`, the
 * optimistic-lock conflict/retry `0703`/`0704`/`0708`, the harness-lane auto-retry
 * `0710`, the read-lock-blocks-writer concurrency case `0728`, the read-lock-shared-
 * compatible `0729` and projection-omits-lock-admits-writer `0734` concurrency-success
 * cases, and the optimistic × temporal close cases `0730`-`0733`. Asserting the exact
 * set fails loudly on a discovery regression
 * (the untagged pkgen / cache / cascade / detached-merge / error-class `06xx`/`07xx`
 * cases, and the api-conformance-lane read-lock / boundary cases, must NOT leak in).
 */
const EXPECTED_IDS: readonly string[] = [
  "0603",
  "0604",
  "0607",
  "0608",
  "0609",
  "0611",
  "0612",
  "0613",
  "0614",
  "0615",
  "0703",
  "0704",
  "0708",
  "0710",
  "0728",
  "0729",
  "0730",
  "0731",
  "0732",
  "0733",
  "0734",
];

const CASES = txnCases();

/** The binds for statement `index` of a (possibly multi-statement) scenario step. */
function stepBinds(binds: readonly unknown[], index: number): readonly unknown[] {
  if (binds.length > 0 && Array.isArray(binds[0])) {
    return (binds[index] as readonly unknown[] | undefined) ?? [];
  }
  return index === 0 ? binds : [];
}

/** One `A`/`B` side of a concurrency round: its dialect-keyed golden + binds. */
interface RoundEntry {
  readonly goldenSql?: { readonly postgres?: string };
  readonly binds?: readonly unknown[];
}

/** A `concurrency.rounds` step (the `A` and/or `B` statement issued that round). */
interface Round {
  readonly A?: RoundEntry;
  readonly B?: RoundEntry;
}

/** The declared concurrency rounds of an `error`/concurrency case (else empty). */
function rounds(loaded: ReturnType<typeof loadCase>): readonly Round[] {
  return (loaded.raw.concurrency as { rounds?: readonly Round[] } | undefined)?.rounds ?? [];
}

/** The ordered golden `postgres` statements a case declares, per its shape. */
function goldenStatements(loaded: ReturnType<typeof loadCase>): readonly string[] {
  if (loaded.shape === "error" || loaded.shape === "concurrencySuccess") {
    // A concurrency case (error `0728`, or concurrency-success `0729`/`0734`) keeps its
    // golden per round inside `concurrency.rounds[].{A,B}.goldenSql`, not at the top
    // level — flatten it in round/A/B order (the emission order).
    return rounds(loaded).flatMap((round) =>
      (["A", "B"] as const).flatMap((node) => {
        const golden = round[node]?.goldenSql?.postgres;
        return golden === undefined ? [] : [golden];
      }),
    );
  }
  if (isScenario(loaded)) {
    const steps = (loaded.raw.scenario as { goldenSql?: { postgres?: string | string[] } }[]) ?? [];
    // A step may list SEVERAL golden statements (a versioned set-based materialize
    // write, `0614`/`0615`) — flatten them so each per-object `UPDATE` is one entry.
    return steps.flatMap((step) => {
      const golden = step.goldenSql?.postgres;
      if (golden === undefined) {
        return [];
      }
      return Array.isArray(golden) ? golden : [golden];
    });
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
  if (loaded.shape === "error" || loaded.shape === "concurrencySuccess") {
    // One bind row per present node, in the same round/A/B order as the statements.
    return rounds(loaded).flatMap((round) =>
      (["A", "B"] as const).flatMap((node) => {
        const step = round[node];
        return step?.goldenSql?.postgres === undefined ? [] : [step.binds ?? []];
      }),
    );
  }
  if (isScenario(loaded)) {
    const steps =
      (loaded.raw.scenario as {
        goldenSql?: { postgres?: string | string[] };
        binds?: unknown[];
      }[]) ?? [];
    // A multi-statement step carries a list-of-lists `binds` (one row per per-object
    // `UPDATE`); slice it per statement so each emission's binds line up.
    return steps.flatMap((step) => {
      const golden = step.goldenSql?.postgres;
      if (golden === undefined) {
        return [];
      }
      const statements = Array.isArray(golden) ? golden : [golden];
      const binds = (step.binds ?? []) as unknown[];
      return statements.map((_stmt, index) => stepBinds(binds, index));
    });
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
