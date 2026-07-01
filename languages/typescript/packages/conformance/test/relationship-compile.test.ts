/**
 * Relationship **compile lane** over the flat non-temporal `03xx` corpus
 * (Docker-free).
 *
 * Phase 5 introduces the correlated-`EXISTS` navigation semi-join (`navigate` /
 * `exists` / `notExists`, incl. multi-hop nested `EXISTS`). Those lowerings pin a
 * precise canonical `goldenSql.postgres` — the cross-dialect SQL contract — so
 * this lane asserts the emitted SQL + binds equal the golden BY TEXT, complementing
 * the Docker-gated run lane (`@parallax/typescript`'s `graph-run.test.ts`) which
 * proves the SQL returns the right rows. Without this, a canonical-form regression
 * (a wrong alias, a dropped clause, a reordered predicate) that still happens to
 * return the right rows would slip through.
 *
 * Only the **flat, single-statement** `03xx` cases are compiled here (their golden
 * is one string). The **deep-fetch** cases pin an ARRAY of per-level statements
 * whose `IN` lists are keyed by run-time-gathered parent keys — those cannot be
 * reproduced Docker-free, so their statement SQL is pinned in the run lane instead.
 */
import { describe, expect, it } from "vitest";
import { discoverCasePaths } from "../src/discover.js";
import { loadCase, runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";

/**
 * The temporal `m7` `03xx` subset (`0324`–`0336`) is a documented Phase-6 exclusion
 * (per-hop as-of propagation, incl. the defaulted-root EXISTS `0335` and the
 * directive-wrapped deep-fetch root `0336`), filtered out of this Phase-5 lane.
 */
const TEMPORAL_M7_EXCLUSIONS: ReadonlySet<string> = new Set(
  Array.from({ length: 13 }, (_, i) => String(324 + i).padStart(4, "0")),
);

/** The postgres golden as a single statement (flat case) or `undefined` (deep fetch). */
function flatGolden(loaded: ReturnType<typeof loadCase>): string | undefined {
  const golden = (loaded.raw.goldenSql as { postgres?: unknown } | undefined)?.postgres;
  return typeof golden === "string" ? golden : undefined;
}

/**
 * The flat (single-statement) non-temporal `03xx` read cases: navigation / `exists`
 * / `notExists`. A deep-fetch case is excluded here (its golden is an array), so the
 * discriminator is purely the golden shape — no operation sniffing.
 */
function flatRelationshipCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^03\d\d$/.test(id) && !TEMPORAL_M7_EXCLUSIONS.has(id))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(
      ({ loaded }) => loaded.shape === "read" && loaded.tags.includes("first-implementation-mvp"),
    )
    .filter(({ loaded }) => flatGolden(loaded) !== undefined)
    .map(({ id, path }) => ({ id, path }));
}

const CASES = flatRelationshipCases();

/**
 * The EXACT flat-`03xx` set: `0301`–`0309` plus `0317` (multi-hop `notExists`) and
 * `0321` (one-to-one navigate) — the 11 single-statement navigation cases. The
 * other in-scope `03xx` (`0310`–`0316`, `0318`–`0320`, `0322`, `0323`) are deep
 * fetch (array golden) and are compiled per-level in the run lane. Asserting the
 * exact set — not a `>= N` bound — fails loudly if a case is dropped or mis-shaped.
 */
const EXPECTED_FLAT_IDS: readonly string[] = [
  "0301",
  "0302",
  "0303",
  "0304",
  "0305",
  "0306",
  "0307",
  "0308",
  "0309",
  "0317",
  "0321",
];

describe("relationship compile lane — flat EXISTS semi-joins === golden over the corpus", () => {
  it("discovers exactly the flat non-temporal 03xx navigation cases", () => {
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
