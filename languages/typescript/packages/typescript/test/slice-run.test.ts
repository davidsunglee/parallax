/**
 * The full-slice **run lane** over the whole `slice-mvp-1` corpus,
 * Testcontainers `postgres:17` — the Phase-8 "is the slice green against a real
 * database?" sweep.
 *
 * One container serves every case (the provider resets the schema per case). For
 * each of the 111 harness-lane tagged cases the sweep runs the adapter's `runRun` (the same
 * orchestration the CLI drives) with the concrete composition-root provider
 * injected, and grades the observation the case SHAPE asserts, reusing the m-case-format
 * comparison rules (exact decimal, boolean never `== 1`, µs timestamps,
 * order-insensitive multisets):
 *
 *  - **read** (flat): observed `rows` vs `then.rows`;
 *  - **read** (deep fetch, `then.graph`): the assembled `graph` structurally,
 *    plus runtime-generated per-level SQL and binds against the golden entries;
 *  - **writeSequence**: the resulting `tableState` vs `then.tableState`;
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
  type DialectStatement,
  dialectStatements,
  type Graph,
  goldenEntries,
  type LoadedCase,
  type MatrixStatus,
  renderMatrixReport,
  runRun,
  type TableState,
  TYPESCRIPT_ADAPTER,
} from "@parallax/conformance";
import type { BindValue, Envelope } from "@parallax/core";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../src/conformance/postgres-provider.js";
import { casesForProfile, POSTGRES_FULL_PROFILE } from "./conformance-profiles.js";

/**
 * The full `slice-mvp-1` tagged slice the HARNESS runs, in discovery order.
 * `api-conformance`-lane cases (boundary retry cases + the read-lock matrix reads)
 * are excluded — they have no harness-executable golden (the API Conformance Suite
 * proves them) — so the run sweep covers the 111 harness-lane cases (101 pre-Phase-4
 * cases + the harness-lane auto-retry case `m-opt-lock-009` + the two Phase-5 versioned
 * set-based materialize scenarios `m-opt-lock-003`/`m-opt-lock-004` + the four Phase-6 optimistic ×
 * temporal close cases `m-temporal-read-009`-`m-temporal-read-012` + the COR-12 behavioral read-lock cases `m-read-lock-006`
 * (blocks-writer), `m-read-lock-007` (shared-compatible), and `m-read-lock-008` (projection-omits-lock-
 * admits-writer)).
 */
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
const CASES = casesForProfile(POSTGRES_FULL_PROFILE);

// Discovery is Docker-free; assert the exact slice size unconditionally. It grew
// by the 42 value-object cases (all harness-lane) in Phase 11, then by the 8
// m-bitemp-write cases (COR-26), then by the 7 audit-chaining / unit-work RYOW
// cases (COR-26 Phase 2), then by the 5 batch-DELETE / opt-lock-edge / mixed-op
// cases (COR-26 Phase 3), then by the 12 type-fidelity / value-object-write /
// pk-gen cases (COR-26 Phase 5) — all harness-lane.
it("discovers the harness-lane slice-mvp-1 slice (185 cases)", () => {
  expect(CASES.length).toBe(185);
});

group.skipIf(!HAS_DOCKER)(
  `${POSTGRES_FULL_PROFILE.name} run lane (Testcontainers postgres:17)`,
  () => {
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

        // A `rejected` case is refused PRE-SQL (no provisioning / execution): it
        // returns an `error` envelope whose diagnostic names the violated rule
        // (m-value-object resolved Q7). That refusal IS its green result.
        if (loaded.shape === "rejected") {
          expect(envelope.status, `${loaded.casePath}: ${JSON.stringify(envelope)}`).toBe("error");
          if (envelope.status !== "error") {
            throw new Error("expected an error (pre-SQL refusal) run envelope");
          }
          expect(envelope.diagnostics[0]?.code, loaded.casePath).toBe(
            loaded.raw.then?.rejectedRule,
          );
          return;
        }

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
      expect(report.total).toBe(185);
      expect(report.residuals).toEqual([]);
    });
  },
);

/**
 * Grade an observation against the case's shape assertion, throwing on a mismatch.
 * The dispatch mirrors the per-shape run-lane graders (read / deep fetch / write
 * sequence / scenario / conflict), reusing the shared m-case-format comparison rules.
 */
function gradeObservation(envelope: Envelope, loaded: LoadedCase): void {
  if (envelope.status !== "ok" || envelope.command !== "run") {
    throw new Error("expected an ok run envelope");
  }
  const columnTypes = columnTypesForCase(loaded);
  const observations = envelope.observations;

  if (loaded.shape === "writeSequence") {
    const expected = (loaded.raw.then?.tableState ?? {}) as TableState;
    const observed = (observations.tableState ?? {}) as TableState;
    const comparison = compareTableState(observed, expected, columnTypes);
    expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
    return;
  }
  if (loaded.shape === "conflict") {
    expect(observations.affectedRows, loaded.casePath).toBe(terminalAffectedRows(loaded));
    const expected = (loaded.raw.then?.tableState ?? {}) as TableState;
    const observed = (observations.tableState ?? {}) as TableState;
    const comparison = compareTableState(observed, expected, columnTypes);
    expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
    return;
  }
  const graph = loaded.raw.then?.graph;
  if (graph) {
    assertDeepFetchEmissions(envelope, loaded);
    const observed = (observations.graph ?? {}) as Graph;
    const comparison = compareGraph(observed, graph as Graph, columnTypes);
    expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
    return;
  }
  // Flat read, read-lock read, or scenario read-your-own-writes: grade the rows.
  const observed = observations.rows ?? [];
  const comparison = compareRowSet(observed, expectedRows(loaded), columnTypes);
  expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
}

/**
 * Deep-fetch child statements are generated at runtime from the gathered parent
 * keys, so the Postgres full m-case-format profile must pin the executed statement list
 * here. Docker-free compile tests only see the root statement.
 */
function assertDeepFetchEmissions(envelope: Envelope, loaded: LoadedCase): void {
  if (envelope.status !== "ok" || envelope.command !== "run" || !loaded.raw.then?.graph) {
    return;
  }

  // A deep fetch's golden lists one `{sql, binds}` entry per level at `then.statements`.
  const golden = dialectStatements(goldenEntries(loaded.raw), "postgres");
  if (golden.length <= 1) {
    return;
  }

  expect(envelope.emissions.map((emission) => emission.sql)).toEqual(golden.map((g) => g.sql));
  assertDeepFetchBinds(
    envelope.emissions.map((emission) => emission.binds),
    golden,
  );
}

/**
 * Compare each deep-fetch level's binds against the authored golden. The child
 * IN-list key order is non-normative, so compare that leading numeric slice as a
 * set; any temporal/as-of suffix is ordered and must match exactly.
 */
function assertDeepFetchBinds(
  observed: readonly (readonly BindValue[])[],
  golden: readonly DialectStatement[],
): void {
  const goldenBinds = golden.map((statement) => statement.binds);

  expect(observed.length).toBe(goldenBinds.length);
  expect(observed[0]).toEqual(goldenBinds[0]);

  for (let level = 1; level < goldenBinds.length; level += 1) {
    const goldenLevel = goldenBinds[level] as readonly unknown[];
    const observedLevel = observed[level] ?? [];
    const inCount = goldenLevel.filter((bind) => typeof bind === "number").length;

    const goldenIn = numericSet(goldenLevel.slice(0, inCount));
    const observedIn = numericSet(observedLevel.slice(0, inCount));
    expect(observedIn).toEqual(goldenIn);
    expect(observedLevel.slice(inCount)).toEqual(goldenLevel.slice(inCount));
  }
}

function numericSet(values: readonly unknown[]): readonly number[] {
  return values.map(Number).sort((a, b) => a - b);
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
    const golden = dialectStatements(goldenEntries(loaded.raw), "postgres");
    return golden.length > 0 ? golden.length : loaded.raw.then?.roundTrips;
  }
  const declared = loaded.raw.then?.roundTrips;
  if (declared !== undefined) {
    return declared;
  }
  return loaded.shape === "read" ? 1 : undefined;
}

/** The status a graded envelope contributes to the matrix (`pass`/`fail`/raw). */
function gradeStatus(envelope: Envelope, loaded: LoadedCase): MatrixStatus {
  // A `rejected` case is green when it refuses pre-SQL with the declared rule.
  if (loaded.shape === "rejected") {
    const ok =
      envelope.status === "error" &&
      envelope.diagnostics[0]?.code === loaded.raw.then?.rejectedRule;
    return ok ? "pass" : "fail";
  }
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
  const attempts = loaded.raw.when?.attempts;
  if (attempts && attempts.length > 0) {
    return attempts[attempts.length - 1]?.affectedRows ?? 0;
  }
  return loaded.raw.then?.affectedRows ?? 0;
}

/**
 * The rows a flat read / read-lock / scenario case asserts: `then.rows`, or the
 * `expectRows` of the last scenario find step (read-your-own-writes).
 */
function expectedRows(loaded: LoadedCase): readonly Record<string, unknown>[] {
  if (loaded.shape === "scenario") {
    const steps = (loaded.raw.when?.scenario ?? []) as { expectRows?: Record<string, unknown>[] }[];
    for (let i = steps.length - 1; i >= 0; i -= 1) {
      const rows = steps[i]?.expectRows;
      if (rows !== undefined) {
        return rows;
      }
    }
    return [];
  }
  return (loaded.raw.then?.rows as Record<string, unknown>[] | undefined) ?? [];
}
