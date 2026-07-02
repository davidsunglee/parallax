/**
 * The full-slice **run lane** over the whole `slice-mvp-1` corpus,
 * Testcontainers `postgres:17` — the Phase-8 "is the slice green against a real
 * database?" sweep.
 *
 * One container serves every case (the provider resets the schema per case). For
 * each of the 99 tagged cases the sweep runs the adapter's `runRun` (the same
 * orchestration the CLI drives) with the concrete composition-root provider
 * injected, and grades the observation the case SHAPE asserts, reusing the M12
 * comparison rules (exact decimal, boolean never `== 1`, µs timestamps,
 * order-insensitive multisets):
 *
 *  - **read** (flat): observed `rows` vs `expectedRows`;
 *  - **read** (deep fetch, `expectedGraph`): the assembled `graph` structurally;
 *  - **writeSequence**: the resulting `tableState` vs `expectedTableState`;
 *  - **scenario**: the terminal find's `rows` (read-your-own-writes);
 *  - **conflict**: the terminal `affectedRows` + the resulting `tableState`.
 *
 * Every case's `roundTrips` is asserted against its declared count. The sweep also
 * folds every outcome into the first-class case-matrix report and asserts it is
 * GREEN with no residuals — so a regression names the exact offending case IDs.
 *
 * Lives in the composition root because the concrete Testcontainers + porsager
 * provider does (the runner depends only on the injected port; a `conformance`
 * run lane would be a cyclic workspace dep). Skipped when Docker is unavailable
 * (reported, never silently passed).
 */
import { execFileSync } from "node:child_process";
import {
  CaseMatrix,
  columnTypesForCase,
  compareGraph,
  compareRowSet,
  compareTableState,
  discoverCasePaths,
  type Graph,
  type LoadedCase,
  loadCase,
  type MatrixStatus,
  renderMatrixReport,
  runRun,
  type TableState,
  TYPESCRIPT_ADAPTER,
} from "@parallax/conformance";
import type { Envelope } from "@parallax/core";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../src/conformance/postgres-provider.js";

/** The full `slice-mvp-1` tagged slice, in discovery order. */
function taggedCases(): readonly { id: string; loaded: LoadedCase }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
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
const CASES = taggedCases();

// Discovery is Docker-free; assert the exact slice size unconditionally.
it("discovers the whole slice-mvp-1 slice (99 cases)", () => {
  expect(CASES.length).toBe(99);
});

group.skipIf(!HAS_DOCKER)("full-slice run lane (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 600_000;
  let provider: PostgresProvider;
  const matrix = new CaseMatrix();

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
    // The full sweep either passed (every case green) or a case above already
    // failed; either way surface the folded report so a run summary is legible.
    // eslint-disable-next-line no-console
    console.log(renderMatrixReport(matrix.report()));
  });

  it.each(CASES)(
    "$id runs green (graded per shape + roundTrips)",
    async ({ loaded }) => {
      const envelope = await runRun(loaded, "postgres", TYPESCRIPT_ADAPTER, provider);
      matrix.record({
        casePath: loaded.casePath,
        command: "run",
        status: gradeStatus(envelope, loaded),
      });
      expect(envelope.status, `${loaded.casePath}: ${JSON.stringify(envelope)}`).toBe("ok");
      if (envelope.status !== "ok" || envelope.command !== "run") {
        throw new Error("expected an ok run envelope");
      }
      gradeObservation(envelope, loaded);
      assertRoundTrips(envelope, loaded);
    },
    BOOT_TIMEOUT,
  );

  it("the case-matrix report is GREEN with no residuals", () => {
    const report = matrix.report();
    expect(report.green, `\n${renderMatrixReport(report)}`).toBe(true);
    expect(report.total).toBe(99);
    expect(report.residuals).toEqual([]);
  });
});

/**
 * Grade an observation against the case's shape assertion, throwing on a mismatch.
 * The dispatch mirrors the per-shape run-lane graders (read / deep fetch / write
 * sequence / scenario / conflict), reusing the shared M12 comparison rules.
 */
function gradeObservation(envelope: Envelope, loaded: LoadedCase): void {
  if (envelope.status !== "ok" || envelope.command !== "run") {
    throw new Error("expected an ok run envelope");
  }
  const columnTypes = columnTypesForCase(loaded);
  const observations = envelope.observations;

  if (loaded.shape === "writeSequence") {
    const expected = (loaded.raw.expectedTableState ?? {}) as TableState;
    const observed = (observations.tableState ?? {}) as TableState;
    const comparison = compareTableState(observed, expected, columnTypes);
    expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
    return;
  }
  if (loaded.shape === "conflict") {
    expect(observations.affectedRows, loaded.casePath).toBe(terminalAffectedRows(loaded));
    const expected = (loaded.raw.expectedTableState ?? {}) as TableState;
    const observed = (observations.tableState ?? {}) as TableState;
    const comparison = compareTableState(observed, expected, columnTypes);
    expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
    return;
  }
  if (loaded.raw.expectedGraph) {
    const observed = (observations.graph ?? {}) as Graph;
    const comparison = compareGraph(observed, loaded.raw.expectedGraph as Graph, columnTypes);
    expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
    return;
  }
  // Flat read, read-lock read, or scenario read-your-own-writes: grade the rows.
  const observed = observations.rows ?? [];
  const comparison = compareRowSet(observed, expectedRows(loaded), columnTypes);
  expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
}

/** Assert the observed `roundTrips` equals the case's declared count when present. */
function assertRoundTrips(envelope: Envelope, loaded: LoadedCase): void {
  if (envelope.status !== "ok" || envelope.command !== "run") {
    return;
  }
  const declared = declaredRoundTrips(loaded);
  if (declared !== undefined) {
    expect(envelope.observations.roundTrips, loaded.casePath).toBe(declared);
  }
}

/**
 * The `roundTrips` a case declares. A write sequence's count is the sum of its
 * step statement counts (the golden statement list length); every other shape
 * carries a top-level `roundTrips` (default 1 when absent for a single-statement
 * read).
 */
function declaredRoundTrips(loaded: LoadedCase): number | undefined {
  if (loaded.shape === "writeSequence") {
    const golden = (loaded.raw.goldenSql as { postgres?: string[] } | undefined)?.postgres;
    return Array.isArray(golden) ? golden.length : (loaded.raw.roundTrips as number | undefined);
  }
  const declared = loaded.raw.roundTrips as number | undefined;
  if (declared !== undefined) {
    return declared;
  }
  return loaded.shape === "read" ? 1 : undefined;
}

/** The status a graded envelope contributes to the matrix (`pass`/`fail`/raw). */
function gradeStatus(envelope: Envelope, loaded: LoadedCase): MatrixStatus {
  if (envelope.status !== "ok") {
    return envelope.status as MatrixStatus;
  }
  try {
    gradeObservation(envelope, loaded);
    return "pass";
  } catch {
    return "fail";
  }
}

/** The terminal (last) attempt's expected affected-row count for a conflict case. */
function terminalAffectedRows(loaded: LoadedCase): number {
  const attempts = loaded.raw.attempts as { expectedAffectedRows?: number }[] | undefined;
  if (attempts && attempts.length > 0) {
    return attempts[attempts.length - 1]?.expectedAffectedRows ?? 0;
  }
  return (loaded.raw.expectedAffectedRows as number | undefined) ?? 0;
}

/**
 * The rows a flat read / read-lock / scenario case asserts: `expectedRows`, or the
 * `expectRows` of the last scenario find step (read-your-own-writes).
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
