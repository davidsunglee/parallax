/**
 * M3 read-algebra **compile lane** over the real corpus (Docker-free).
 *
 * Drives the adapter's `runCompile` — the same path the CLI exercises — over
 * every `read`-shaped `00xx` + `02xx` case tagged `slice-mvp-1`,
 * asserting the emitted SQL equals `goldenSql.postgres` and the emitted binds
 * equal the case's authored `binds`. This proves the compiler against the real
 * metamodel-backed resolver (projection resolved from the case, attribute types
 * resolved from the descriptor), complementing the in-isolation compiler unit
 * test in `@parallax/sql`.
 *
 * Both the emitted binds and the expected binds are read through the SAME
 * canonical serde seam, so a precision-unsafe literal is normalized identically
 * on both sides; the in-slice corpus carries only float-safe values, so the
 * comparison is exact today and stays exact when unsafe values are added.
 */
import { describe, expect, it } from "vitest";
import { discoverCasePaths } from "../src/discover.js";
import { loadCase, runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";

/**
 * Cases this phase does not target, with the reason. `0003` is read-shaped but
 * exercises NO predicate algebra (`all: {}`); its golden projects a `bytes`
 * column through `encode(t0.payload, ?) payload_hex` — a scalar-serde projection
 * concern (the case is tagged `scalar`, not part of the single-entity predicate
 * algebra Phase 4 broadens). It lands with the scalar-projection work; tracked
 * here so the exclusion is explicit, not a silent gap.
 */
const OUT_OF_PHASE: ReadonlyMap<string, string> = new Map([
  ["0003", "scalar bytes encode(...) projection — not predicate algebra"],
]);

/** The `00xx` + `02xx` read cases tagged `slice-mvp-1`, in scope. */
function readAlgebraCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ id }) => /^(00|02)\d\d$/.test(id) && !OUT_OF_PHASE.has(id))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.shape === "read" && loaded.tags.includes("slice-mvp-1"))
    .map(({ id, path }) => ({ id, path }));
}

/** The Postgres golden SQL a case pins (read shape ⇒ a single string). */
function goldenSql(loaded: ReturnType<typeof loadCase>): string {
  const golden = loaded.raw.goldenSql as { postgres?: string } | undefined;
  return golden?.postgres ?? "";
}

const CASES = readAlgebraCases();

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

describe("read-algebra compile lane — emitted === golden over the corpus", () => {
  it("discovers exactly the in-scope 00xx + 02xx read cases", () => {
    const discovered = CASES.map(({ id }) => id).sort();
    expect(discovered).toEqual([...EXPECTED_IDS].sort());
    // `0003` is read-shaped + mvp-tagged but a documented exclusion (scalar
    // bytes `encode(...)` projection); it must NOT leak into the in-scope set.
    expect(discovered).not.toContain("0003");
  });

  it.each(CASES)("$id compiles to the golden Postgres SQL + binds", ({ path }) => {
    const loaded = loadCase(path);
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }
    const [emission] = envelope.emissions;
    expect(emission?.casePointer).toBe("/operation");
    expect(emission?.sql).toBe(goldenSql(loaded));
    expect(emission?.binds).toEqual(loaded.raw.binds ?? []);
  });
});
