/**
 * Temporal **compile lane** over the M7 corpus (Docker-free).
 *
 * Phase 6 lowers the as-of read algebra (`asOf` / `asOfRange` / `history`, single
 * + both axes, default-injection), the temporal EXISTS semi-join (`0330`), and the
 * audit-only milestone-chaining writes (`insert` / `update` / `terminate`). Each
 * pins a precise canonical `goldenSql.postgres`, so this lane asserts the emitted
 * SQL + binds equal the golden BY TEXT, complementing the Docker-gated run lane
 * (`@parallax/typescript`'s `temporal-run.test.ts`) that proves the SQL returns
 * the right rows / table state.
 *
 * Split by golden shape:
 *  - a **single-statement read** (`05xx` reads, `08xx` reads, `0330`) pins one
 *    `goldenSql.postgres` string — asserted against the sole `/operation` emission;
 *  - a **write sequence** (`0510`–`0512`, `0004`/`0005`) pins an ARRAY of DML
 *    statements with an array-of-arrays `binds` — asserted against the per-statement
 *    emissions, each keyed by its `/writeSequence/<step>` pointer;
 *  - a **deep-fetch** read (`0324`–`0334` minus `0330`) pins an ARRAY whose child
 *    levels are keyed by run-time-gathered parent keys — those emit root-only here
 *    (per the Phase-5 rule) and are pinned per-level in the run lane instead.
 */
import { describe, expect, it } from "vitest";
import { isDeepFetch } from "../src/deepfetch-plan.js";
import { discoverCasePaths } from "../src/discover.js";
import { loadCase, runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";

/** The in-scope M7 MVP case ids: `05xx` reads+writes, `08xx` bitemporal reads. */
function temporalReadWriteCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^(05|08)\d\d$/.test(id))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("first-implementation-mvp"))
    .map(({ id, path }) => ({ id, path }));
}

/** The temporal deep-fetch `m7` subset (`0324`–`0334`), single + EXISTS (`0330`). */
function temporalDeepFetchCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^03(2[4-9]|3[0-4])$/.test(id))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("first-implementation-mvp"))
    .map(({ id, path }) => ({ id, path }));
}

/**
 * The EXACT in-scope M7 MVP `05xx`/`08xx` set: the audit-only reads/writes
 * `0501`–`0508`/`0510`–`0512` and the bitemporal reads `0801`–`0805`. The
 * out-of-V1 `*Until` writes (`0810`–`0812`) and the business-only slice
 * (`0820`–`0826`) are NOT tagged `first-implementation-mvp`, so they never
 * discover here. Asserting the exact set fails loudly on a discovery regression.
 */
const EXPECTED_READ_WRITE_IDS: readonly string[] = [
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
];

/** The exact temporal deep-fetch `m7` set (`0324`–`0334`, 11 cases). */
const EXPECTED_DEEP_FETCH_IDS: readonly string[] = Array.from({ length: 11 }, (_, i) =>
  String(324 + i).padStart(4, "0"),
);

const READ_WRITE = temporalReadWriteCases();
const DEEP_FETCH = temporalDeepFetchCases();

describe("temporal compile lane — emitted === golden over the M7 corpus", () => {
  it("discovers exactly the in-scope 05xx + 08xx MVP cases", () => {
    expect(READ_WRITE.map(({ id }) => id).sort()).toEqual([...EXPECTED_READ_WRITE_IDS].sort());
  });

  it("discovers exactly the temporal deep-fetch m7 subset (0324–0334)", () => {
    expect(DEEP_FETCH.map(({ id }) => id).sort()).toEqual([...EXPECTED_DEEP_FETCH_IDS].sort());
  });

  it.each(READ_WRITE)("$id compiles to the golden Postgres SQL + binds", ({ path }) => {
    const loaded = loadCase(path);
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }

    const golden = (loaded.raw.goldenSql as { postgres?: string | string[] }).postgres;
    if (Array.isArray(golden)) {
      // Write sequence: one emission per statement, in order, with its bind row.
      expect(envelope.emissions.map((e) => e.sql)).toEqual(golden);
      expect(envelope.emissions.map((e) => e.binds)).toEqual(loaded.raw.binds);
      // Each write emission is keyed by its step pointer (statements can share one).
      for (const emission of envelope.emissions) {
        expect(emission.casePointer).toMatch(/^\/writeSequence\/\d+$/);
      }
      expect(envelope.roundTrips).toBe(golden.length);
    } else {
      // Single-statement read: the sole `/operation` emission equals the golden.
      const [emission] = envelope.emissions;
      expect(emission?.casePointer).toBe("/operation");
      expect(emission?.sql).toBe(golden);
      expect(emission?.binds).toEqual(loaded.raw.binds ?? []);
      expect(envelope.roundTrips).toBe(1);
    }
  });

  it.each(DEEP_FETCH)("$id compiles its deep-fetch ROOT to the golden root SQL", ({ path }) => {
    const loaded = loadCase(path);
    // 0330 is a flat EXISTS read (single golden string), not a deep fetch.
    if (!isDeepFetch(loaded.raw.operation)) {
      const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
      expect(envelope.status).toBe("ok");
      if (envelope.status !== "ok" || envelope.command !== "compile") {
        throw new Error("expected an ok compile envelope");
      }
      const golden = (loaded.raw.goldenSql as { postgres?: string }).postgres;
      expect(envelope.emissions[0]?.sql).toBe(golden);
      expect(envelope.emissions[0]?.binds).toEqual(loaded.raw.binds ?? []);
      return;
    }
    // A deep fetch emits root-only at compile (child levels are run-time-keyed);
    // the per-level SQL + as-of suffix are pinned in the run lane.
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }
    const golden = (loaded.raw.goldenSql as { postgres?: string[] }).postgres ?? [];
    expect(envelope.emissions).toHaveLength(1);
    expect(envelope.emissions[0]?.sql).toBe(golden[0]);
  });
});
