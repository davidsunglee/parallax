/**
 * Read-algebra **compile lane** over the real corpus (Docker-free).
 *
 * Drives the adapter's `runCompile` — the same path the CLI exercises — over
 * every `read`-shaped single-entity predicate-algebra case tagged `slice-mvp-1`
 * (the `m-op-algebra` / `m-core` / `m-descriptor` reads),
 * asserting the emitted SQL + binds equal the case's golden Postgres statement entry
 * (`then.statements`). This proves the compiler against the real
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
import { dialectStatements, goldenEntries } from "../src/case-format.js";
import { discoverCasePaths } from "../src/discover.js";
import { loadCase, runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";

/**
 * Cases this phase does not target, with the reason. `m-core-001` is read-shaped
 * but exercises NO predicate algebra (`all: {}`); its golden projects a `bytes`
 * column through `encode(t0.payload, ?) payload_hex` — a scalar-serde projection
 * concern (the case is tagged `scalar`, not part of the single-entity predicate
 * algebra Phase 4 broadens). It lands with the scalar-projection work; tracked
 * here so the exclusion is explicit, not a silent gap.
 */
const OUT_OF_PHASE: ReadonlyMap<string, string> = new Map([
  ["m-core-001", "scalar bytes encode(...) projection — not predicate algebra"],
]);

/** The module slug of a per-module case id (`m-op-algebra-003` → `m-op-algebra`). */
function moduleOf(id: string): string {
  return id.replace(/-\d{3}$/, "");
}

/** The single-entity predicate-algebra modules whose read cases this lane compiles. */
const READ_ALGEBRA_MODULES: ReadonlySet<string> = new Set([
  "m-op-algebra",
  "m-core",
  "m-descriptor",
]);

/** The single-entity read-algebra cases tagged `slice-mvp-1`, in scope. */
function readAlgebraCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(m-[a-z0-9-]+-\d{3})-.*$/, "$1"), path }))
    .filter(({ id }) => READ_ALGEBRA_MODULES.has(moduleOf(id)) && !OUT_OF_PHASE.has(id))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.shape === "read" && loaded.tags.includes("slice-mvp-1"))
    .map(({ id, path }) => ({ id, path }));
}

/** The Postgres golden `{sql, binds}` a case pins (read shape ⇒ one statement entry). */
function golden(loaded: ReturnType<typeof loadCase>): { sql: string; binds: readonly unknown[] } {
  return dialectStatements(goldenEntries(loaded.raw), "postgres")[0] ?? { sql: "", binds: [] };
}

const CASES = readAlgebraCases();

/**
 * The exact in-scope ID set Phase 4 contracts: `m-op-algebra-001`/`-002` and the
 * `m-descriptor-001` identifier read, plus the full `m-op-algebra-003`–`-034`
 * predicate-algebra family (32 cases) = 35. `m-core-001` is excluded
 * (`OUT_OF_PHASE`, scalar bytes projection); `m-core-002`/`-003` are
 * `writeSequence` and naturally filtered by shape. Asserting the EXACT set — not a
 * `>= N` lower bound — makes a discovery regression that silently drops an algebra
 * case fail loudly instead of passing vacuously.
 */
const EXPECTED_IDS: readonly string[] = [
  "m-op-algebra-001",
  "m-op-algebra-002",
  "m-descriptor-001",
  ...Array.from({ length: 32 }, (_, i) => `m-op-algebra-${String(3 + i).padStart(3, "0")}`),
];

describe("read-algebra compile lane — emitted === golden over the corpus", () => {
  it("discovers exactly the in-scope single-entity read-algebra cases", () => {
    const discovered = CASES.map(({ id }) => id).sort();
    expect(discovered).toEqual([...EXPECTED_IDS].sort());
    // `m-core-001` is read-shaped + mvp-tagged but a documented exclusion (scalar
    // bytes `encode(...)` projection); it must NOT leak into the in-scope set.
    expect(discovered).not.toContain("m-core-001");
  });

  it.each(CASES)("$id compiles to the golden Postgres SQL + binds", ({ path }) => {
    const loaded = loadCase(path);
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }
    const [emission] = envelope.emissions;
    const { sql, binds } = golden(loaded);
    expect(emission?.casePointer).toBe("/operation");
    expect(emission?.sql).toBe(sql);
    expect(emission?.binds).toEqual(binds);
  });
});
