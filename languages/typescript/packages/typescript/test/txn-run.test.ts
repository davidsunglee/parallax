/**
 * Transaction / write-sequence / locking **run lane** over the M8 + M10 corpus
 * (`06xx` + `07xx`), Testcontainers `postgres:17`.
 *
 * Provisions one container, then per case runs the adapter's `runRun` (the same
 * orchestration the CLI uses) with the concrete composition-root provider
 * injected, and grades the observation the case shape asserts — the four Phase-7
 * shapes:
 *
 *  - **read-lock** (`0603`): the locking read (`… for share of t0`) executes and
 *    returns the expected row (the lock does not change the result), `roundTrips 1`;
 *  - **write sequence** (`0604`/`0612`/`0613` on the non-versioned `Wallet`; `0611`
 *    locking-mode versioned update): apply the generated batched / version-advancing
 *    DML, then grade the resulting `tableState` against `expectedTableState`, with
 *    the emissions pinned to the golden and `roundTrips` the statement count;
 *  - **scenario** (`0607`, read-your-own-writes; `0608`, rollback/abort; `0609`,
 *    no-op-update-no-DML): apply the write step(s) (committed for `0607`, applied-
 *    then-ROLLED-BACK for `0608`, no DML for `0609`), run the dependent find, and
 *    grade its observed rows against `expectRows` — `roundTrips` the declared total;
 *  - **conflict** (`0703`/`0704`/`0708`): load fixtures, apply the precondition,
 *    apply the versioned UPDATE(s), and grade `affectedRows` (terminal outcome) +
 *    the resulting `tableState`.
 *
 * Lives in the composition root because the concrete provider does — the runner
 * depends only on the injected port, so a `conformance/test` run lane would be a
 * cyclic workspace dep (same placement as Phase 4/5/6 run lanes). Skipped when
 * Docker is unavailable (reported, never silently passed).
 */
import { execFileSync } from "node:child_process";
import {
  columnTypesForCase,
  compareRowSet,
  compareTableState,
  discoverCasePaths,
  type LoadedCase,
  loadCase,
  runRun,
  type TableState,
  TYPESCRIPT_ADAPTER,
} from "@parallax/conformance";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../src/conformance/postgres-provider.js";

/** The in-scope `06xx`/`07xx` MVP cases (the four Phase-7 shapes). */
function txnCases(): readonly { id: string; loaded: LoadedCase }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^(06|07)\d\d$/.test(id))
    .map(({ id, path }) => ({ id, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("slice-mvp-1"));
}

/** True when a Docker daemon is reachable (gates the Testcontainers lane). */
function dockerAvailable(): boolean {
  try {
    execFileSync("docker", ["info"], { stdio: "ignore", timeout: 10_000 });
    return true;
  } catch {
    return false;
  }
}

const HAS_DOCKER = dockerAvailable();
const CASES = txnCases();

/** The EXACT in-scope id set (the tagged `06xx`/`07xx` Phase-7 + abort cases). */
const EXPECTED_IDS: readonly string[] = [
  "0603",
  "0604",
  "0607",
  "0608",
  "0609",
  "0611",
  "0612",
  "0613",
  "0703",
  "0704",
  "0708",
];

it("discovers exactly the in-scope 06xx + 07xx cases", () => {
  expect(CASES.map(({ id }) => id).sort()).toEqual([...EXPECTED_IDS].sort());
});

group.skipIf(!HAS_DOCKER)("txn run lane (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 240_000;
  let provider: PostgresProvider;

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(CASES)(
    "$id runs green (rows / tableState / affectedRows + roundTrips)",
    async ({ loaded }) => {
      const envelope = await runRun(loaded, "postgres", TYPESCRIPT_ADAPTER, provider);
      expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
      if (envelope.status !== "ok" || envelope.command !== "run") {
        throw new Error("expected an ok run envelope");
      }
      const columnTypes = columnTypesForCase(loaded);

      if (loaded.shape === "writeSequence") {
        const expected = loaded.raw.expectedTableState as TableState;
        const observed = (envelope.observations.tableState ?? {}) as TableState;
        const comparison = compareTableState(observed, expected, columnTypes);
        expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
          true,
        );
        const golden = (loaded.raw.goldenSql as { postgres?: string[] }).postgres ?? [];
        expect(envelope.emissions.map((e) => e.sql)).toEqual(golden);
        expect(envelope.observations.roundTrips).toBe(golden.length);
      } else if (loaded.shape === "conflict") {
        // Grade the terminal affected-row count + the resulting table state.
        const expectedAffected = terminalAffectedRows(loaded);
        expect(envelope.observations.affectedRows).toBe(expectedAffected);
        const expected = loaded.raw.expectedTableState as TableState;
        const observed = (envelope.observations.tableState ?? {}) as TableState;
        const comparison = compareTableState(observed, expected, columnTypes);
        expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
          true,
        );
      } else {
        // read-lock (`0603`) or scenario (`0607`): grade the observed rows.
        const observed = envelope.observations.rows ?? [];
        const expected = expectedRows(loaded);
        const comparison = compareRowSet(observed, expected, columnTypes);
        expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
          true,
        );
        const roundTrips = loaded.raw.roundTrips as number | undefined;
        if (roundTrips !== undefined) {
          expect(envelope.observations.roundTrips).toBe(roundTrips);
        }
      }
    },
    BOOT_TIMEOUT,
  );
});

/** The terminal (last) attempt's expected affected-row count for a conflict case. */
function terminalAffectedRows(loaded: LoadedCase): number {
  const attempts = loaded.raw.attempts as { expectedAffectedRows?: number }[] | undefined;
  if (attempts && attempts.length > 0) {
    return attempts[attempts.length - 1]?.expectedAffectedRows ?? 0;
  }
  return (loaded.raw.expectedAffectedRows as number | undefined) ?? 0;
}

/**
 * The rows a read-lock / scenario case asserts: `expectedRows` (read-lock) or the
 * `expectRows` of the last find step (scenario read-your-own-writes).
 */
function expectedRows(loaded: LoadedCase): readonly Record<string, unknown>[] {
  if (loaded.shape === "scenario") {
    const steps = (loaded.raw.scenario as { expectRows?: Record<string, unknown>[] }[]) ?? [];
    for (let i = steps.length - 1; i >= 0; i -= 1) {
      const rows = steps[i]?.expectRows;
      if (rows !== undefined) {
        return rows;
      }
    }
    return [];
  }
  return (loaded.raw.expectedRows as Record<string, unknown>[] | undefined) ?? [];
}
