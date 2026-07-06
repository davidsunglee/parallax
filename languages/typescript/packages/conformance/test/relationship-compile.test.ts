/**
 * Relationship **compile lane** over the flat non-temporal navigation corpus
 * (Docker-free).
 *
 * Phase 5 introduces the correlated-`EXISTS` navigation semi-join (`navigate` /
 * `exists` / `notExists`, incl. multi-hop nested `EXISTS`). Those lowerings pin a
 * precise canonical `goldenSql.postgres` — the cross-dialect SQL contract — so
 * this lane asserts the emitted SQL + binds equal the golden BY TEXT,
 * complementing the Docker-gated Postgres full m-case-format profile
 * (`@parallax/typescript`'s `slice-run.test.ts`) which proves the SQL returns the
 * right rows. Without this, a canonical-form regression
 * (a wrong alias, a dropped clause, a reordered predicate) that still happens to
 * return the right rows would slip through.
 *
 * Only the **flat, single-statement** navigation cases are compiled here (their
 * golden is one string). The **deep-fetch** cases pin an ARRAY of per-level statements
 * whose `IN` lists are keyed by run-time-gathered parent keys — those cannot be
 * reproduced Docker-free, so their statement SQL is pinned in the run lane instead.
 */
import { describe, expect, it } from "vitest";
import { discoverCasePaths } from "../src/discover.js";
import { loadCase, runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";

/** The module slug of a per-module case id (`m-navigate-003` → `m-navigate`). */
function moduleOf(id: string): string {
  return id.replace(/-\d{3}$/, "");
}

/** The navigation modules whose flat single-statement reads this lane compiles. */
const RELATIONSHIP_MODULES: ReadonlySet<string> = new Set(["m-navigate", "m-deep-fetch"]);

/**
 * The temporal navigate subset (`m-navigate-012`–`m-navigate-024`) is a documented
 * Phase-6 exclusion (per-hop as-of propagation, incl. the defaulted-root EXISTS
 * `m-navigate-023` and the directive-wrapped deep-fetch root `m-navigate-024`),
 * filtered out of this Phase-5 lane.
 */
const TEMPORAL_M7_EXCLUSIONS: ReadonlySet<string> = new Set(
  Array.from({ length: 13 }, (_, i) => `m-navigate-${String(12 + i).padStart(3, "0")}`),
);

/** The postgres golden as a single statement (flat case) or `undefined` (deep fetch). */
function flatGolden(loaded: ReturnType<typeof loadCase>): string | undefined {
  const golden = (loaded.raw.goldenSql as { postgres?: unknown } | undefined)?.postgres;
  return typeof golden === "string" ? golden : undefined;
}

/**
 * The flat (single-statement) non-temporal navigation read cases: navigation /
 * `exists` / `notExists`. A deep-fetch case is excluded here (its golden is an
 * array), so the discriminator is purely the golden shape — no operation sniffing.
 */
function flatRelationshipCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(m-[a-z0-9-]+-\d{3})-.*$/, "$1"), path }))
    .filter(({ id }) => RELATIONSHIP_MODULES.has(moduleOf(id)) && !TEMPORAL_M7_EXCLUSIONS.has(id))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.shape === "read" && loaded.tags.includes("slice-mvp-1"))
    .filter(({ loaded }) => flatGolden(loaded) !== undefined)
    .map(({ id, path }) => ({ id, path }));
}

const CASES = flatRelationshipCases();

/**
 * The EXACT flat navigation set: `m-navigate-001`–`m-navigate-011` — the 11
 * single-statement navigation cases (navigate / `exists` / `notExists`, incl. the
 * multi-hop `notExists` and the one-to-one navigate). The `m-deep-fetch` cases are
 * deep fetch (array golden) and are compiled per-level in the run lane. Asserting
 * the exact set — not a `>= N` bound — fails loudly if a case is dropped or
 * mis-shaped.
 */
const EXPECTED_FLAT_IDS: readonly string[] = Array.from(
  { length: 11 },
  (_, i) => `m-navigate-${String(1 + i).padStart(3, "0")}`,
);

describe("relationship compile lane — flat EXISTS semi-joins === golden over the corpus", () => {
  it("discovers exactly the flat non-temporal navigation cases", () => {
    const discovered = CASES.map(({ id }) => id).sort();
    expect(discovered).toEqual([...EXPECTED_FLAT_IDS].sort());
  });

  it.each(CASES)("$id compiles to the golden Postgres EXISTS SQL + binds", ({ path }) => {
    const loaded = loadCase(path);
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }
    const [emission] = envelope.emissions;
    expect(emission?.casePointer).toBe("/operation");
    expect(emission?.sql).toBe(flatGolden(loaded));
    expect(emission?.binds).toEqual(loaded.raw.binds ?? []);
  });
});
