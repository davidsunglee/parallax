/**
 * Relationships / deep-fetch **run lane** over the non-temporal `03xx` corpus
 * (Testcontainers).
 *
 * Provisions a single `postgres:17` once, then for each non-temporal `03xx` case
 * runs the adapter's `runRun` (the same orchestration the CLI uses) with the
 * concrete composition-root provider injected:
 *
 *  - a **flat** navigation / `exists` / `notExists` case (a single `select …
 *    where exists (…)`) reports `rows`, graded against `expectedRows` under the
 *    M12 scalar rules with `roundTrips === 1`;
 *  - a **deep-fetch** case reports the assembled `graph`, graded structurally
 *    against `expectedGraph` under the same scalar rules, with `roundTrips`
 *    asserted EXACTLY equal to the case's declared `1 + L` (e.g. `0312` = 3, not
 *    7; `0315` = 1; `0318` = 2) — which is what proves N+1 elimination.
 *
 * This lives in the composition root because the concrete Testcontainers +
 * porsager provider does: `@parallax/conformance` imports no driver and depends
 * on `@parallax/typescript` only in reverse (the provider is injected through the
 * port), so a `conformance/test` run lane would be a cyclic workspace dep. This
 * mirrors the Phase-4 `read-run.test.ts` placement. Skipped when Docker is
 * unavailable (reported, never silently passed).
 */
import { execFileSync } from "node:child_process";
import {
  columnTypesForCase,
  compareGraph,
  compareRowSet,
  discoverCasePaths,
  type Graph,
  type LoadedCase,
  loadCase,
  runRun,
  TYPESCRIPT_ADAPTER,
} from "@parallax/conformance";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../src/conformance/postgres-provider.js";

/**
 * The temporal `m7` deep-fetch subset (`0324`–`0334`), EXCLUDED from Phase 5 with
 * a reason: temporal deep fetch propagates as-of binds per hop (the `relationships
 * -> bitemporal` edge) and lands in Phase 6 once M7 exists. Every non-temporal
 * `03xx` case (`0301`–`0323`) is in scope; there is no `>= N` lower bound.
 */
const TEMPORAL_M7_EXCLUSIONS: readonly string[] = Array.from({ length: 11 }, (_, i) =>
  String(324 + i).padStart(4, "0"),
);

/** The in-scope non-temporal `03xx` read cases (flat navigation + deep fetch). */
function graphRunCases(): readonly { id: string; loaded: LoadedCase }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^03\d\d$/.test(id) && !TEMPORAL_M7_EXCLUSIONS.includes(id))
    .map(({ id, path }) => ({ id, loaded: loadCase(path) }))
    .filter(
      ({ loaded }) => loaded.shape === "read" && loaded.tags.includes("first-implementation-mvp"),
    );
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
const CASES = graphRunCases();

/**
 * The EXACT in-scope set: the contiguous non-temporal `03xx` block `0301`–`0323`
 * (23 cases). Asserting the exact set — not a `>= N` lower bound — makes a
 * discovery regression that silently drops a case fail loudly, and documents the
 * temporal `m7` exclusions (`0324`–`0334`) explicitly rather than by omission.
 */
const EXPECTED_IDS: readonly string[] = Array.from({ length: 23 }, (_, i) =>
  String(301 + i).padStart(4, "0"),
);

// Discovery is Docker-free, so the in-scope set is asserted unconditionally —
// independent of whether the Testcontainers run lane below executes.
it("discovers exactly the in-scope non-temporal 03xx cases (0301–0323)", () => {
  const discovered = CASES.map(({ id }) => id).sort();
  expect(discovered).toEqual([...EXPECTED_IDS].sort());
  // The temporal m7 subset (0324–0334) is a documented Phase-6 exclusion; it
  // must NOT leak into the Phase-5 in-scope set.
  for (const excluded of TEMPORAL_M7_EXCLUSIONS) {
    expect(discovered).not.toContain(excluded);
  }
});

group.skipIf(!HAS_DOCKER)("deep-fetch run lane (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 240_000;
  let provider: PostgresProvider;

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(CASES)(
    "$id returns the expected rows/graph with the declared roundTrips",
    async ({ loaded }) => {
      const envelope = await runRun(loaded, "postgres", TYPESCRIPT_ADAPTER, provider);
      expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
      if (envelope.status !== "ok" || envelope.command !== "run") {
        throw new Error("expected an ok run envelope");
      }

      // Pin the emitted SQL against the golden. A deep-fetch case's golden is an
      // ARRAY of per-level statements (root + one `… in (?, …) [order by …]` per
      // hop); the run lane is the only place the run-time-keyed level SQL exists,
      // so it is asserted here (the flat single-statement goldens are pinned
      // Docker-free in `conformance/test/relationship-compile.test.ts`). This
      // catches a canonical-form regression the row/graph grading would not.
      const golden = (loaded.raw.goldenSql as { postgres?: string | string[] } | undefined)
        ?.postgres;
      if (Array.isArray(golden)) {
        expect(envelope.emissions.map((emission) => emission.sql)).toEqual(golden);
        // Also pin each child level's IN-list binds against the golden — but as an
        // order-insensitive SET per level, NOT positionally. The IN-list order is
        // semantically irrelevant (it never affects which children match, and the
        // child order is fixed by the level's `orderBy`), so the runtime emits keys
        // in natural first-appearance order and never sorts; the reference oracle
        // likewise compares these binds as a sorted set (`sorted(in_slice) ==
        // parent_keys`). What this asserts is the N+1-eliminating invariant: each
        // level is keyed by EXACTLY the distinct parent keys gathered from the level
        // above. Binds are normalized to numbers first — the in-scope 03xx identity
        // keys are small integer ids and an `int8` column can arrive as a decimal
        // string, so the int64→string wire form (a separate, parked concern the
        // graph grading already tolerates) is not under test here. Only a
        // MULTI-statement deep fetch authors per-level bind arrays (array-of-arrays);
        // a single-statement case (e.g. `0315`, the empty root) authors a flat
        // scalar list with no child IN list to compare, so it is skipped.
        const goldenBinds = loaded.raw.binds;
        if (Array.isArray(goldenBinds) && goldenBinds.every(Array.isArray)) {
          const sortedNums = (rows: readonly (readonly unknown[])[]): number[][] =>
            rows.map((level) => level.map(Number).sort((a, b) => a - b));
          expect(sortedNums(envelope.emissions.map((emission) => emission.binds))).toEqual(
            sortedNums(goldenBinds),
          );
        }
      }

      const columnTypes = columnTypesForCase(loaded);
      const expectedGraph = loaded.raw.expectedGraph as Graph | undefined;
      if (expectedGraph) {
        // Deep-fetch case: grade the assembled graph structurally.
        const observed = (envelope.observations.graph ?? {}) as Graph;
        const comparison = compareGraph(observed, expectedGraph, columnTypes);
        expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
          true,
        );
      } else {
        // Flat navigation / exists case: grade the observed rows.
        const observed = envelope.observations.rows ?? [];
        const expected = (loaded.raw.expectedRows as Record<string, unknown>[] | undefined) ?? [];
        const comparison = compareRowSet(observed, expected, columnTypes);
        expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
          true,
        );
      }

      // roundTrips is asserted EXACTLY equal to the declared 1 + L.
      const roundTrips = loaded.raw.roundTrips as number | undefined;
      expect(roundTrips, "every 03xx case declares roundTrips").not.toBeUndefined();
      expect(envelope.observations.roundTrips).toBe(roundTrips);
    },
    BOOT_TIMEOUT,
  );
});
