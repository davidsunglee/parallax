/**
 * Read-algebra **run lane** over the `00xx` + `02xx` corpus (Testcontainers).
 *
 * Provisions a single `postgres:17` once, then for each `read`-shaped case tagged
 * `first-implementation-mvp` runs the adapter's `runRun` (the same orchestration
 * the CLI uses) with the concrete composition-root provider injected, and
 * compares the observed `rows` against the case's `expectedRows` under the M12
 * adapter-boundary rules (exact decimal, boolean never `== 1`, microsecond
 * timestamps, order-insensitive row-set equality).
 *
 * The provider resets the schema per case, so one container serves every case.
 * This lives in the composition root because the concrete Testcontainers +
 * porsager provider does (the runner depends only on the injected port). Skipped
 * when Docker is unavailable (reported, never silently passed).
 */
import { execFileSync } from "node:child_process";
import {
  compareRowSet,
  discoverCasePaths,
  type LoadedCase,
  loadCase,
  runRun,
  TYPESCRIPT_ADAPTER,
} from "@parallax/conformance";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../src/conformance/postgres-provider.js";

/**
 * Cases excluded from this phase, with the reason. `0003` is read-shaped but
 * projects a `bytes` column through `encode(...)` (a scalar-serde projection
 * concern, not the predicate algebra Phase 4 broadens).
 */
const OUT_OF_PHASE = new Set(["0003"]);

/** The in-scope `00xx` + `02xx` read cases. */
function readRunCases(): readonly { id: string; loaded: LoadedCase }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^(00|02)\d\d$/.test(id) && !OUT_OF_PHASE.has(id))
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
const CASES = readRunCases();

/**
 * The exact in-scope ID set Phase 4 contracts: `0001`/`0002`/`0006` plus the
 * full `0201`–`0232` read family (32 cases) = 35. `0003` is excluded
 * (`OUT_OF_PHASE`, scalar bytes projection); `0004`/`0005` are `writeSequence`
 * and naturally filtered by shape. Asserting the EXACT set — not a `>= N`
 * lower bound — makes a discovery regression that silently drops a 02xx case
 * fail loudly instead of passing vacuously.
 */
const EXPECTED_IDS: readonly string[] = [
  "0001",
  "0002",
  "0006",
  ...Array.from({ length: 32 }, (_, i) => String(201 + i).padStart(4, "0")),
];

// Discovery is Docker-free, so the in-scope set is asserted unconditionally —
// independent of whether the Testcontainers run lane below executes.
it("discovers exactly the in-scope 00xx + 02xx read cases", () => {
  const discovered = CASES.map(({ id }) => id).sort();
  expect(discovered).toEqual([...EXPECTED_IDS].sort());
  // `0003` is read-shaped + mvp-tagged but a documented exclusion (scalar
  // bytes `encode(...)` projection); it must NOT leak into the in-scope set.
  expect(discovered).not.toContain("0003");
});

group.skipIf(!HAS_DOCKER)("read-algebra run lane (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 240_000;
  let provider: PostgresProvider;

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(CASES)(
    "$id returns the expected rows with the declared roundTrips",
    async ({ loaded }) => {
      const envelope = await runRun(loaded, "postgres", TYPESCRIPT_ADAPTER, provider);
      expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
      if (envelope.status !== "ok" || envelope.command !== "run") {
        throw new Error("expected an ok run envelope");
      }

      const observed = envelope.observations.rows ?? [];
      const expected = (loaded.raw.expectedRows as Record<string, unknown>[] | undefined) ?? [];
      const comparison = compareRowSet(observed, expected);
      expect(comparison.equal, `${comparison.reason}\nobserved=${JSON.stringify(observed)}`).toBe(
        true,
      );

      const roundTrips = loaded.raw.roundTrips as number | undefined;
      if (roundTrips !== undefined) {
        expect(envelope.observations.roundTrips).toBe(roundTrips);
      }
    },
    BOOT_TIMEOUT,
  );
});
