/**
 * Structural guard for the concurrency-SUCCESS shape (Docker-free unit test).
 *
 * `runConcurrencySuccess` grades a round step read-vs-write by its EXPLICIT `kind`
 * (`read` → fetched + rows compared; `write` → executed, asserts only it did not
 * raise), replacing the old brittle SQL-verb sniffing. The pure, DB-free
 * `concurrencySuccessStepProblems` re-checks that every present success step declares a
 * valid kind AND that every `kind: read` step carries `expectRows` (defense-in-depth
 * over the schema's structural requirements, mirroring the Python harness's
 * `_assert_concurrency_success_step_kinds`); this pins that guard directly, in isolation
 * from the Docker-gated `0729` / `0734` run-lane proof (`slice-run`). The schema's
 * read⇒`expectRows` / write⇒no-`expectRows` if/then is pinned here too, against
 * `compatibility-case.schema.json` directly.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import { describe, expect, it } from "vitest";
import { concurrencySuccessStepProblems } from "../src/runner.js";

/** The `/concurrency/rounds/{i}/{node}` pointers the guard flagged, in order. */
function problemPointers(rounds: Parameters<typeof concurrencySuccessStepProblems>[0]): string[] {
  return concurrencySuccessStepProblems(rounds).map((problem) => problem.pointer);
}

const SHARED_READ = {
  postgres:
    "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? for share of t0",
  mariadb:
    "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? lock in share mode",
} as const;

describe("concurrencySuccessStepProblems — every success step MUST declare a valid kind + a read carries expectRows", () => {
  it("accepts 0729's shape: both shared reads declare kind: read", () => {
    const rounds = [
      { A: { kind: "read", goldenSql: SHARED_READ, binds: [2], expectRows: [{ id: 2 }] } },
      { B: { kind: "read", goldenSql: SHARED_READ, binds: [2], expectRows: [{ id: 2 }] } },
    ] as const;
    expect(concurrencySuccessStepProblems(rounds)).toEqual([]);
  });

  it("accepts 0734's shape: a kind: read projection and a kind: write UPDATE", () => {
    const rounds = [
      {
        A: {
          kind: "read",
          goldenSql: { postgres: "select distinct t0.id from account t0" },
          binds: [],
          expectRows: [{ id: 1 }, { id: 2 }, { id: 3 }],
        },
      },
      {
        B: {
          kind: "write",
          goldenSql: { postgres: "update account set balance = ? where id = ?" },
          binds: [999, 2],
        },
      },
    ] as const;
    expect(concurrencySuccessStepProblems(rounds)).toEqual([]);
  });

  it("flags a success step that omits kind, naming its round/node pointer", () => {
    const rounds = [
      { A: { kind: "read", goldenSql: SHARED_READ, binds: [2], expectRows: [{ id: 2 }] } },
      { B: { goldenSql: SHARED_READ, binds: [2] } }, // no kind
    ] as const;
    expect(problemPointers(rounds)).toEqual(["/concurrency/rounds/1/B"]);
  });

  it("flags a step with an unknown kind value", () => {
    // A `kind` sourced from malformed YAML (neither `read` nor `write`) — cast past the
    // type to simulate the untyped parsed input (`loaded.raw`) the runtime guard defends
    // against; a well-typed `ConcurrencyStep.kind` cannot express it.
    const rounds = [
      { A: { kind: "select", goldenSql: SHARED_READ, binds: [2] } },
    ] as unknown as Parameters<typeof concurrencySuccessStepProblems>[0];
    expect(problemPointers(rounds)).toEqual(["/concurrency/rounds/0/A"]);
  });

  it("flags a kind: read step missing expectRows, naming its pointer + reason", () => {
    // The parity gap this guard closes: a `kind: read` step with no `expectRows` would,
    // absent the guard, silently grade its held-session rows against an EMPTY expectation
    // (a spurious pass) instead of failing as malformed. `expectRows` is an OPTIONAL field
    // on `ConcurrencyStep`, so omitting it is already type-valid — no cast needed.
    const rounds = [
      { A: { kind: "read", goldenSql: SHARED_READ, binds: [2] } }, // no expectRows
    ] as const;
    const problems = concurrencySuccessStepProblems(rounds);
    expect(problems).toHaveLength(1);
    expect(problems[0]?.pointer).toBe("/concurrency/rounds/0/A");
    expect(problems[0]?.reason).toContain("expectRows");
  });
});

// --- schema if/then: read⇒expectRows, write⇒no-expectRows --------------------

/** Compile the compatibility-case schema (Draft 2020-12) once for the if/then checks. */
function caseValidator(): ValidateFunction {
  const here = fileURLToPath(import.meta.url);
  const repoRoot = fileURLToPath(new URL("../../../../../", new URL(`file://${here}`)));
  const schema = JSON.parse(
    readFileSync(`${repoRoot}core/schemas/compatibility-case.schema.json`, "utf8"),
  ) as object;
  return new Ajv2020({ allErrors: true, strict: false }).compile(schema);
}

const CONCURRENCY_TAGS = ["m-read-lock", "m-dialect", "concurrency", "slice-mvp-1"];

describe("compatibility-case.schema.json — the concurrency-step kind if/then", () => {
  const validate = caseValidator();

  it("accepts 0729's shape (two kind: read steps carrying expectRows)", () => {
    const valid = validate({
      model: "models/account.yaml",
      tags: CONCURRENCY_TAGS,
      loadFixtures: true,
      concurrency: {
        rounds: [
          { A: { kind: "read", goldenSql: SHARED_READ, binds: [2], expectRows: [{ id: 2 }] } },
          { B: { kind: "read", goldenSql: SHARED_READ, binds: [2], expectRows: [{ id: 2 }] } },
        ],
      },
    });
    expect(valid).toBe(true);
  });

  it("accepts 0734's shape (kind: read + kind: write, the write omitting expectRows)", () => {
    const valid = validate({
      model: "models/account.yaml",
      tags: CONCURRENCY_TAGS,
      loadFixtures: true,
      concurrency: {
        rounds: [
          {
            A: {
              kind: "read",
              goldenSql: { postgres: "select distinct t0.id from account t0" },
              binds: [],
              expectRows: [{ id: 1 }],
            },
          },
          {
            B: {
              kind: "write",
              goldenSql: { postgres: "update account set balance = ? where id = ?" },
              binds: [999, 2],
            },
          },
        ],
      },
    });
    expect(valid).toBe(true);
  });

  it("rejects a success step missing kind (the success branch requires it)", () => {
    const valid = validate({
      model: "models/account.yaml",
      tags: CONCURRENCY_TAGS,
      concurrency: {
        rounds: [{ A: { goldenSql: SHARED_READ, binds: [2], expectRows: [{ id: 2 }] } }],
      },
    });
    expect(valid).toBe(false);
  });

  it("rejects a kind: read step missing expectRows (the if/then requires it)", () => {
    const valid = validate({
      model: "models/account.yaml",
      tags: CONCURRENCY_TAGS,
      concurrency: {
        rounds: [{ A: { kind: "read", goldenSql: SHARED_READ, binds: [2] } }],
      },
    });
    expect(valid).toBe(false);
  });

  it("rejects a kind: write step carrying expectRows (the if/then forbids it)", () => {
    const valid = validate({
      model: "models/account.yaml",
      tags: CONCURRENCY_TAGS,
      concurrency: {
        rounds: [
          {
            A: {
              kind: "write",
              goldenSql: { postgres: "update account set balance = ? where id = ?" },
              binds: [999, 2],
              expectRows: [{ id: 2 }],
            },
          },
        ],
      },
    });
    expect(valid).toBe(false);
  });
});
