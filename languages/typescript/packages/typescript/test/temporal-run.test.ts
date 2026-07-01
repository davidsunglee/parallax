/**
 * Temporal **run lane** over the M7 corpus (`05xx` + `08xx` + temporal `03xx`),
 * Testcontainers `postgres:17`.
 *
 * Provisions one container, then per case runs the adapter's `runRun` (the same
 * orchestration the CLI uses) with the concrete composition-root provider
 * injected, and grades the observation the case shape asserts:
 *
 *  - **as-of read** (`05xx` / `08xx` reads): the observed `rows` against
 *    `expectedRows` (native `infinity` actually executes — the current-row
 *    predicate binds `infinity` and `history` reads back the open bound), with
 *    `roundTrips === 1`;
 *  - **write sequence** (`0510`–`0512`, `0004`/`0005`): apply the generated
 *    milestone-chaining DML, then grade the observed `tableState` against
 *    `expectedTableState` (the superseded closed rows + the current `out_z = ∞`
 *    row), with `roundTrips` equal to the declared statement count (1/3/2);
 *  - **temporal deep fetch** (`0324`–`0334`): the assembled `graph` against
 *    `expectedGraph`, plus the per-level golden SQL and the propagated as-of
 *    suffix binds, with `roundTrips` the declared `1 + L`.
 *
 * Lives in the composition root because the concrete provider does — the runner
 * depends only on the injected port, so a `conformance/test` run lane would be a
 * cyclic workspace dep (same placement as Phase 4/5 `read-run`/`graph-run`).
 * Skipped when Docker is unavailable (reported, never silently passed).
 */
import { execFileSync } from "node:child_process";
import {
  columnTypesForCase,
  compareGraph,
  compareRowSet,
  compareTableState,
  discoverCasePaths,
  type Graph,
  type LoadedCase,
  loadCase,
  runRun,
  type TableState,
  TYPESCRIPT_ADAPTER,
} from "@parallax/conformance";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../src/conformance/postgres-provider.js";

/** The in-scope M7 MVP cases: `05xx` (reads + audit writes), `08xx` (bitemporal
 * reads), the temporal deep-fetch `03xx` subset (`0324`–`0334`), and the
 * timestamp-shape writeSequence cases `0004`/`0005`. Filtered to the tagged slice
 * (so the out-of-V1 `*Until` writes / business-only cases never discover here). */
function temporalCases(): readonly { id: string; loaded: LoadedCase }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(
      ({ id }) =>
        /^(05|08)\d\d$/.test(id) || /^03(2[4-9]|3[0-4])$/.test(id) || /^000[45]$/.test(id),
    )
    .map(({ id, path }) => ({ id, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("first-implementation-mvp"));
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
const CASES = temporalCases();

/**
 * The EXACT in-scope id set: `0004`/`0005` (timestamp writes), the audit-only
 * `0501`–`0508`/`0510`–`0512`, the bitemporal reads `0801`–`0805`, and the
 * temporal deep-fetch `0324`–`0334`. Asserting the exact set — not a `>= N` bound
 * — fails loudly on a discovery regression that silently drops a case.
 */
const EXPECTED_IDS: readonly string[] = [
  "0004",
  "0005",
  "0501",
  "0502",
  "0503",
  "0504",
  "0505",
  "0506",
  "0507",
  "0508",
  "0510",
  "0511",
  "0512",
  "0801",
  "0802",
  "0803",
  "0804",
  "0805",
  ...Array.from({ length: 11 }, (_, i) => String(324 + i).padStart(4, "0")),
];

it("discovers exactly the in-scope temporal cases", () => {
  expect(CASES.map(({ id }) => id).sort()).toEqual([...EXPECTED_IDS].sort());
});

group.skipIf(!HAS_DOCKER)("temporal run lane (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 240_000;
  let provider: PostgresProvider;

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(CASES)(
    "$id runs green (rows / graph / tableState + roundTrips)",
    async ({ loaded }) => {
      const envelope = await runRun(loaded, "postgres", TYPESCRIPT_ADAPTER, provider);
      expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
      if (envelope.status !== "ok" || envelope.command !== "run") {
        throw new Error("expected an ok run envelope");
      }

      const columnTypes = columnTypesForCase(loaded);

      if (loaded.shape === "writeSequence") {
        // Audit / timestamp write: grade the resulting table state.
        const expected = loaded.raw.expectedTableState as TableState;
        const observed = (envelope.observations.tableState ?? {}) as TableState;
        const comparison = compareTableState(observed, expected, columnTypes);
        expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
          true,
        );
        // The DML text is pinned by construction; also pin it against the golden here.
        const golden = (loaded.raw.goldenSql as { postgres?: string[] }).postgres ?? [];
        expect(envelope.emissions.map((e) => e.sql)).toEqual(golden);
      } else if (loaded.raw.expectedGraph) {
        // Temporal deep fetch: grade the assembled graph, and pin per-level SQL.
        const observed = (envelope.observations.graph ?? {}) as Graph;
        const comparison = compareGraph(observed, loaded.raw.expectedGraph as Graph, columnTypes);
        expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
          true,
        );
        const golden = (loaded.raw.goldenSql as { postgres?: string[] }).postgres ?? [];
        expect(envelope.emissions.map((e) => e.sql)).toEqual(golden);
        assertLevelBinds(envelope.emissions.map((e) => e.binds) as unknown[][], loaded);
      } else {
        // Flat as-of read: grade the observed rows.
        const observed = envelope.observations.rows ?? [];
        const expected = (loaded.raw.expectedRows as Record<string, unknown>[] | undefined) ?? [];
        const comparison = compareRowSet(observed, expected, columnTypes);
        expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
          true,
        );
      }

      const roundTrips = loaded.raw.roundTrips as number | undefined;
      expect(roundTrips, "every temporal case declares roundTrips").not.toBeUndefined();
      expect(envelope.observations.roundTrips).toBe(roundTrips);
    },
    BOOT_TIMEOUT,
  );
});

/**
 * Pin each deep-fetch child level's binds against the golden: the `IN`-list slice
 * as an order-insensitive SET of parent keys (the N+1-eliminating invariant, keyed
 * exactly by the distinct parents — the IN order is non-normative), and the as-of
 * SUFFIX as an ORDERED list (the propagation oracle derives it business-axis-first
 * and NEVER sorts it). A single-statement case (no child level) is skipped.
 */
function assertLevelBinds(observed: unknown[][], loaded: LoadedCase): void {
  const golden = loaded.raw.binds;
  if (!Array.isArray(golden) || !golden.every(Array.isArray)) {
    return;
  }
  expect(observed.length).toBe(golden.length);
  // Level 0 (root) carries only its own as-of binds (no IN list) — compared whole.
  expect(observed[0]).toEqual(golden[0]);
  for (let level = 1; level < golden.length; level += 1) {
    const goldenLevel = golden[level] as unknown[];
    const observedLevel = observed[level] as unknown[];
    // The IN-list slice is the leading numeric keys; the as-of suffix is the rest.
    const inCount = goldenLevel.filter((b) => typeof b === "number").length;
    const goldenIn = goldenLevel
      .slice(0, inCount)
      .map(Number)
      .sort((a, b) => a - b);
    const observedIn = observedLevel
      .slice(0, inCount)
      .map(Number)
      .sort((a, b) => a - b);
    expect(observedIn).toEqual(goldenIn);
    expect(observedLevel.slice(inCount)).toEqual(goldenLevel.slice(inCount));
  }
}
