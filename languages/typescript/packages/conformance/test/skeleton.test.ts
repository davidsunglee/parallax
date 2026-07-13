/**
 * Phase 3 walking-skeleton matrix harness — drives the `parallax-conformance`
 * CLI **by contract only** (spawns the built binary, asserts on its JSON
 * envelope + exit code), importing no runtime internals. This is the same
 * discipline the external corpus runner uses, so a green test here means the
 * adapter is conformant at its actual boundary.
 *
 * Three lanes:
 *  - **compile** (Docker-free): `m-op-algebra-002` emits the canonical golden SQL +
 *    binds, and the envelope validates against the schema (validated inside the CLI).
 *  - **out-of-claim** (Docker-free): a `mariadb` dialect request returns
 *    `unsupported` (exit `10`) with the first-failed-filter diagnostic.
 *  - **run** (Testcontainers `postgres:17`): `m-op-algebra-002` returns
 *    `[{ id, name }]` with `observations.roundTrips == 1` and exit `0`. Skipped when
 *    Docker is unavailable (reported, not silently passed).
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";

/** Resolve a repo-root-relative path from this test file (five dirs up). */
function repoPath(relative: string): string {
  const repoRoot = fileURLToPath(new URL("../../../../../", import.meta.url));
  return `${repoRoot}${relative}`;
}

/** The built CLI entry point the harness drives. */
const CLI = repoPath("languages/typescript/packages/typescript/dist/cli/parallax-conformance.js");

/** The eq walking-skeleton case path (`m-op-algebra-002`, repo-relative envelope form). */
const CASE_0002 = "core/compatibility/cases/m-op-algebra-002-eq.yaml";

/** Run the CLI and capture `{ exitCode, envelope }`, by contract only. */
function runCli(
  args: readonly string[],
  timeoutMs = 180_000,
): { exitCode: number; envelope: Record<string, unknown> } {
  let exitCode = 0;
  let stdout = "";
  try {
    stdout = execFileSync("node", [CLI, ...args], {
      encoding: "utf8",
      timeout: timeoutMs,
      maxBuffer: 16 * 1024 * 1024,
    });
  } catch (error) {
    const e = error as { status?: number; stdout?: string };
    exitCode = e.status ?? 1;
    stdout = e.stdout ?? "";
  }
  return { exitCode, envelope: JSON.parse(stdout) as Record<string, unknown> };
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

beforeAll(() => {
  // The harness drives the built binary; fail loudly (not silently) if the
  // composition root has not been built, so a stale-dist run is never mistaken
  // for a passing one.
  expect(
    existsSync(CLI),
    "build @parallax/typescript (tsc -b) before running the skeleton harness",
  ).toBe(true);
});

group("compile lane (Docker-free)", () => {
  it("m-op-algebra-002 emits the canonical golden SQL + binds and exits 0", () => {
    const { exitCode, envelope } = runCli([
      "compile",
      "--case",
      CASE_0002,
      "--dialect",
      "postgres",
    ]);
    expect(exitCode).toBe(0);
    expect(envelope.status).toBe("ok");
    expect(envelope.case).toBe(CASE_0002);
    expect(envelope.dialect).toBe("postgres");
    expect(envelope.caseShape).toBe("read");
    expect(envelope.roundTrips).toBe(1);

    const emissions = envelope.emissions as {
      casePointer: string;
      sql: string;
      binds: unknown[];
    }[];
    expect(emissions).toHaveLength(1);
    // The read-operation emission points at the case's `operation` key, per the
    // conformance contract's `compile` example (not the empty whole-case pointer).
    expect(emissions[0]?.casePointer).toBe("/operation");
    // The golden SQL the corpus pins for Postgres, by construction — the full
    // declared scalar projection in columnOrder (m-sql "Read projection").
    expect(emissions[0]?.sql).toBe(
      "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0 where t0.id = ?",
    );
    // The int64 bind 42 is carried as the JSON number the corpus authors (it is
    // float-safe and matches `binds: [42]` byte-for-byte; see the wire-form note).
    expect(emissions[0]?.binds).toEqual([42]);
  });
});

group("out-of-claim (Docker-free)", () => {
  it("a non-Postgres dialect returns unsupported (exit 10) with a diagnostic", () => {
    const { exitCode, envelope } = runCli(["compile", "--case", CASE_0002, "--dialect", "mariadb"]);
    expect(exitCode).toBe(10);
    expect(envelope.status).toBe("unsupported");
    const diagnostics = envelope.diagnostics as { code: string; message: string }[];
    expect(diagnostics).toHaveLength(1);
    // The gate names the first failed filter — the unclaimed dialect.
    expect(diagnostics[0]?.code).toBe("unsupported-dialect");
  });
});

const HAS_DOCKER = dockerAvailable();

group.skipIf(!HAS_DOCKER)("run lane (Testcontainers postgres:17)", () => {
  // Booting a container + provisioning is slow; give the lane a generous budget.
  const RUN_TIMEOUT = 240_000;
  let result: { exitCode: number; envelope: Record<string, unknown> };

  beforeAll(() => {
    result = runCli(["run", "--case", CASE_0002, "--dialect", "postgres"], RUN_TIMEOUT);
  }, RUN_TIMEOUT);

  afterAll(() => {
    // nothing to tear down — the CLI owns and stops its container.
  });

  it(
    "m-op-algebra-002 returns [{ id: 42, name: Grace }] with roundTrips 1 and exits 0",
    () => {
      expect(result.exitCode).toBe(0);
      expect(result.envelope.status).toBe("ok");
      // The run emission carries the same `/operation` read pointer as compile.
      const emissions = result.envelope.emissions as { casePointer: string }[];
      expect(emissions[0]?.casePointer).toBe("/operation");
      const observations = result.envelope.observations as {
        roundTrips: number;
        rows: Record<string, unknown>[];
      };
      expect(observations.roundTrips).toBe(1);
      expect(observations.rows).toHaveLength(1);
      const [row] = observations.rows;
      // int64 `id` is carried as its canonical wire string (§3.2.1); `name` is text.
      expect(row?.id).toBe("42");
      expect(row?.name).toBe("Grace");
    },
    RUN_TIMEOUT,
  );
});
