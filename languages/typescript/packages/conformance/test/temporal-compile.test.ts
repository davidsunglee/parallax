/**
 * Temporal **compile lane** over the m-temporal-read corpus (Docker-free).
 *
 * Phase 6 lowers the as-of read algebra (`asOf` / `asOfRange` / `history`, single
 * + both axes, default-injection), the temporal EXISTS semi-joins
 * (`m-navigate-018` explicit as-of + `m-navigate-023` defaulted root), and the
 * audit-only milestone-chaining writes (`insert` / `update` / `terminate`). Each
 * pins a precise canonical `goldenSql.postgres`, so this lane asserts the emitted
 * SQL + binds equal the golden BY TEXT, complementing the Docker-gated Postgres
 * full m-case-format profile (`@parallax/typescript`'s `slice-run.test.ts`) that proves the
 * SQL returns the right rows / table state.
 *
 * Split by golden shape:
 *  - a **single-statement read** (audit-only reads, bitemporal reads, the temporal
 *    EXISTS semi-joins `m-navigate-018`/`m-navigate-023`) pins one
 *    `goldenSql.postgres` string — asserted against the sole `/operation` emission;
 *  - a **write sequence** (`m-audit-write-001`–`-003`) pins an ARRAY of DML
 *    statements with an array-of-arrays `binds` — asserted against the per-statement
 *    emissions, each keyed by its `/writeSequence/<step>` pointer;
 *  - a **deep-fetch** read (the temporal `m-navigate` subset minus the flat EXISTS
 *    `m-navigate-018`/`m-navigate-023`) pins an ARRAY whose child levels are keyed
 *    by run-time-gathered parent keys — those emit root-only here (per the Phase-5
 *    rule) and are pinned per-level in the run lane instead.
 */
import { describe, expect, it } from "vitest";
import { dialectStatements, goldenEntries } from "../src/case-format.js";
import { isDeepFetch } from "../src/deepfetch-plan.js";
import { discoverCasePaths } from "../src/discover.js";
import { loadCase, runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";

/** The module slug of a per-module case id (`m-temporal-read-003` → `m-temporal-read`). */
function moduleOf(id: string): string {
  return id.replace(/-\d{3}$/, "");
}

/** The audit-only read/write temporal modules this lane compiles (the optimistic ×
 * temporal-close cases share `m-temporal-read` but are `conflict`-shaped, so a shape
 * filter keeps them out — they compile in `txn-compile.test.ts`). */
const TEMPORAL_RW_MODULES: ReadonlySet<string> = new Set(["m-temporal-read", "m-audit-write"]);

/** The in-scope temporal MVP cases: audit-only reads, bitemporal reads, audit writes. */
function temporalReadWriteCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(m-[a-z0-9-]+-\d{3})-.*$/, "$1"), path }))
    .filter(({ id }) => TEMPORAL_RW_MODULES.has(moduleOf(id)))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("slice-mvp-1"))
    .filter(({ loaded }) => loaded.shape === "read" || loaded.shape === "writeSequence")
    .map(({ id, path }) => ({ id, path }));
}

/** The temporal navigate deep-fetch subset (`m-navigate-012`–`m-navigate-024`), incl.
 * the flat EXISTS semi-joins `m-navigate-018` (explicit as-of) and `m-navigate-023`
 * (defaulted root) — the `m-navigate` cases carrying the `temporal` tag. */
function temporalDeepFetchCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(m-[a-z0-9-]+-\d{3})-.*$/, "$1"), path }))
    .filter(({ id }) => moduleOf(id) === "m-navigate")
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("slice-mvp-1") && loaded.tags.includes("temporal"))
    .map(({ id, path }) => ({ id, path }));
}

/**
 * The EXACT in-scope temporal MVP set: the audit-only reads `m-temporal-read-001`–
 * `-008`, the audit writes `m-audit-write-001`–`-005` (COR-26 added the
 * multi-attribute update `-004` and the update-from-existing-history `-005`; the
 * conflict-shaped gated close `-006` files under the txn compile lane), and the
 * bitemporal reads `m-temporal-read-013`–`-017`. The out-of-V1 `*Until` writes
 * (`m-bitemp-write-*`) are NOT tagged `slice-mvp-1`, so they never discover here.
 * Asserting the exact set fails
 * loudly on a discovery regression.
 */
const EXPECTED_READ_WRITE_IDS: readonly string[] = [
  "m-temporal-read-001",
  "m-temporal-read-002",
  "m-temporal-read-003",
  "m-temporal-read-004",
  "m-temporal-read-005",
  "m-temporal-read-006",
  "m-temporal-read-007",
  "m-temporal-read-008",
  "m-audit-write-001",
  "m-audit-write-002",
  "m-audit-write-003",
  "m-audit-write-004",
  "m-audit-write-005",
  "m-temporal-read-013",
  "m-temporal-read-014",
  "m-temporal-read-015",
  "m-temporal-read-016",
  "m-temporal-read-017",
];

/** The exact temporal navigate deep-fetch set (`m-navigate-012`–`m-navigate-024`, 13
 * cases: the 11 as-of propagation cases plus the defaulted-root EXISTS
 * `m-navigate-023` and the directive-wrapped temporal deep-fetch root `m-navigate-024`). */
const EXPECTED_DEEP_FETCH_IDS: readonly string[] = Array.from(
  { length: 13 },
  (_, i) => `m-navigate-${String(12 + i).padStart(3, "0")}`,
);

const READ_WRITE = temporalReadWriteCases();
const DEEP_FETCH = temporalDeepFetchCases();

describe("temporal compile lane — emitted === golden over the m-temporal-read corpus", () => {
  it("discovers exactly the in-scope temporal audit-only + bitemporal MVP cases", () => {
    expect(READ_WRITE.map(({ id }) => id).sort()).toEqual([...EXPECTED_READ_WRITE_IDS].sort());
  });

  it("discovers exactly the temporal navigate deep-fetch subset", () => {
    expect(DEEP_FETCH.map(({ id }) => id).sort()).toEqual([...EXPECTED_DEEP_FETCH_IDS].sort());
  });

  it.each(READ_WRITE)("$id compiles to the golden Postgres SQL + binds", ({ path }) => {
    const loaded = loadCase(path);
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }

    const golden = dialectStatements(goldenEntries(loaded.raw), "postgres");
    if (loaded.shape === "writeSequence") {
      // Write sequence: one emission per statement, in order, with its bind row.
      expect(envelope.emissions.map((e) => e.sql)).toEqual(golden.map((g) => g.sql));
      expect(envelope.emissions.map((e) => e.binds)).toEqual(golden.map((g) => g.binds));
      // Each write emission is keyed by its step pointer (statements can share one).
      for (const emission of envelope.emissions) {
        expect(emission.casePointer).toMatch(/^\/writeSequence\/\d+$/);
      }
      expect(envelope.roundTrips).toBe(golden.length);
    } else {
      // Single-statement read: the sole `/operation` emission equals the golden.
      const [emission] = envelope.emissions;
      const [g] = golden;
      expect(emission?.casePointer).toBe("/operation");
      expect(emission?.sql).toBe(g?.sql);
      expect(emission?.binds).toEqual(g?.binds ?? []);
      expect(envelope.roundTrips).toBe(1);
    }
  });

  it.each(DEEP_FETCH)("$id compiles its deep-fetch ROOT to the golden root SQL", ({ path }) => {
    const loaded = loadCase(path);
    // m-navigate-018 / m-navigate-023 are flat EXISTS reads (single golden entry),
    // not deep fetches.
    const golden = dialectStatements(goldenEntries(loaded.raw), "postgres");
    if (!isDeepFetch(loaded.raw.when?.operation)) {
      const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
      expect(envelope.status).toBe("ok");
      if (envelope.status !== "ok" || envelope.command !== "compile") {
        throw new Error("expected an ok compile envelope");
      }
      expect(envelope.emissions[0]?.sql).toBe(golden[0]?.sql);
      expect(envelope.emissions[0]?.binds).toEqual(golden[0]?.binds ?? []);
      return;
    }
    // A deep fetch emits root-only at compile (child levels are run-time-keyed);
    // the per-level SQL + as-of suffix are pinned in the run lane.
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }
    expect(envelope.emissions).toHaveLength(1);
    expect(envelope.emissions[0]?.sql).toBe(golden[0]?.sql);
  });
});
