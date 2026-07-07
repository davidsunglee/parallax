/**
 * The **dialect-declared** pre-run guard (Finding 2): the TS mirror of the Python
 * oracle's per-dialect skip (`case_runner.run_case`). After the capability-claim gate
 * and the api-conformance lane-skip, both `runCompile` and `runRun` also skip a case
 * that declares NO golden SQL for the active dialect — routing it to an `unsupported`
 * envelope with the free-form `dialect-not-declared` diagnostic instead of compiling /
 * executing a dialect the case never authored.
 *
 * Two levels of coverage:
 *
 *  1. the pure {@link caseDeclaresGoldenForDialect} helper over the REAL corpus, proving
 *     per-shape golden detection (a scenario's per-step golden, a read's top-level
 *     golden); and
 *  2. the envelope-level guard. The guard is only REACHED when the request dialect
 *     passes the gate (i.e. `postgres`) AND the case lacks Postgres golden — a
 *     combination no real corpus case exhibits (every in-claim case declares Postgres
 *     golden) — so a synthetic in-memory `LoadedCase` (a `read`-shaped, `slice-mvp-1`
 *     case whose `then.statements` declares only `mariadb`) exercises the fire path,
 *     while a real in-claim case confirms the happy path is untouched.
 */
// biome-ignore-all lint/suspicious/noThenProperty: `then` is a compatibility-case group name (plain data, never a thenable), not a Promise-like `then`.
import { describe, expect, it } from "vitest";
import type { LoadedCase } from "../src/discover.js";
import {
  caseDeclaresGoldenForDialect,
  loadCase,
  runCompile,
  TYPESCRIPT_ADAPTER,
} from "../src/index.js";

/**
 * A `read`-shaped, `slice-mvp-1`-tagged synthetic case whose `then.statements` declares
 * golden ONLY for `mariadb`. Its single module tag `m-op-algebra` is claimed and its
 * `slice-mvp-1` include tag is present, so it PASSES the gate for a `postgres` request —
 * the only way to reach the dialect-declared guard, which then fires because no Postgres
 * golden is authored.
 */
function mariadbOnlyReadCase(): LoadedCase {
  return {
    casePath: "core/compatibility/cases/synthetic-mariadb-only-read.yaml",
    // A read case reads its golden from the top-level `then.statements`; this one
    // declares only `mariadb`, so a `postgres` request finds no golden and is skipped.
    raw: {
      then: { statements: [{ sql: { mariadb: "select t0.id from orders t0" } }] },
    } as unknown as LoadedCase["raw"],
    shape: "read",
    tags: ["slice-mvp-1", "m-op-algebra"],
    lane: "harness",
    descriptor: {},
    fixtures: {},
  };
}

describe("caseDeclaresGoldenForDialect — per-shape golden detection over the corpus", () => {
  it("detects a scenario's per-step golden (Postgres-only)", () => {
    const loaded = loadCase("core/compatibility/cases/m-unit-work-001-read-your-own-writes.yaml");
    expect(loaded.shape).toBe("scenario");
    // A scenario authors its golden per step at `when.scenario[].statements`; every
    // scenario case is Postgres-only, so `postgres` is declared and `mariadb` is not.
    expect(caseDeclaresGoldenForDialect(loaded, "postgres")).toBe(true);
    expect(caseDeclaresGoldenForDialect(loaded, "mariadb")).toBe(false);
  });

  it("detects a read case's top-level golden", () => {
    const loaded = loadCase("core/compatibility/cases/m-op-algebra-002-eq.yaml");
    expect(loaded.shape).toBe("read");
    // A read case authors its golden at the top-level `then.statements`.
    expect(caseDeclaresGoldenForDialect(loaded, "postgres")).toBe(true);
  });
});

describe("dialect-declared guard — envelope behavior", () => {
  it("routes a Postgres request for a Postgres-less case to unsupported/dialect-not-declared", () => {
    const synthetic = mariadbOnlyReadCase();
    // Sanity: the helper agrees the synthetic case declares mariadb but not postgres.
    expect(caseDeclaresGoldenForDialect(synthetic, "mariadb")).toBe(true);
    expect(caseDeclaresGoldenForDialect(synthetic, "postgres")).toBe(false);

    const envelope = runCompile(synthetic, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status).toBe("unsupported");
    if (envelope.status !== "unsupported") {
      throw new Error("expected an unsupported envelope");
    }
    expect(envelope.diagnostics[0]?.code).toBe("dialect-not-declared");
    expect(envelope.diagnostics[0]?.casePointer).toBe("");
  });

  it("leaves a normal in-claim case's happy path untouched", () => {
    const loaded = loadCase("core/compatibility/cases/m-op-algebra-002-eq.yaml");
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    // The guard proceeds (Postgres golden is declared), so compile still returns `ok`.
    expect(envelope.status).toBe("ok");
  });
});
