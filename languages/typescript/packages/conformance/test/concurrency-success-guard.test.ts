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
 * from the Docker-gated `m-read-lock-007` / `m-read-lock-008` run-lane proof (`slice-run`). The schema's
 * read⇒`expectRows` / write⇒no-`expectRows` if/then is pinned here too, against
 * `compatibility-case.schema.json` directly.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import { describe, expect, it } from "vitest";
import type { StatementEntry } from "../src/index.js";
import { concurrencySuccessStepProblems } from "../src/runner.js";

/** The `/concurrency/rounds/{i}/{node}` pointers the guard flagged, in order. */
function problemPointers(rounds: Parameters<typeof concurrencySuccessStepProblems>[0]): string[] {
  return concurrencySuccessStepProblems(rounds).map((problem) => problem.pointer);
}

/** The shared-read golden as a `then.statements`-shaped `{sql, binds}` entry list. */
const SHARED_READ_STATEMENTS: StatementEntry[] = [
  {
    sql: {
      postgres:
        "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? for share of t0",
      mariadb:
        "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? lock in share mode",
    },
    binds: [2],
  },
];

/** A single-statement entry list for a distinct-id projection / an UPDATE. */
function statements(postgres: string, binds: unknown[] = []): StatementEntry[] {
  return [{ sql: { postgres }, binds }];
}

describe("concurrencySuccessStepProblems — every success step MUST declare a valid kind + a read carries expectRows", () => {
  it("accepts m-read-lock-007's shape: both shared reads declare kind: read", () => {
    const rounds = [
      { A: { kind: "read", statements: SHARED_READ_STATEMENTS, expectRows: [{ id: 2 }] } },
      { B: { kind: "read", statements: SHARED_READ_STATEMENTS, expectRows: [{ id: 2 }] } },
    ] as const;
    expect(concurrencySuccessStepProblems(rounds)).toEqual([]);
  });

  it("accepts m-read-lock-008's shape: a kind: read projection and a kind: write UPDATE", () => {
    const rounds = [
      {
        A: {
          kind: "read",
          statements: statements("select distinct t0.id from account t0"),
          expectRows: [{ id: 1 }, { id: 2 }, { id: 3 }],
        },
      },
      {
        B: {
          kind: "write",
          statements: statements("update account set balance = ? where id = ?", [999, 2]),
        },
      },
    ] as const;
    expect(concurrencySuccessStepProblems(rounds)).toEqual([]);
  });

  it("flags a success step that omits kind, naming its round/node pointer", () => {
    const rounds = [
      { A: { kind: "read", statements: SHARED_READ_STATEMENTS, expectRows: [{ id: 2 }] } },
      { B: { statements: SHARED_READ_STATEMENTS } }, // no kind
    ] as const;
    expect(problemPointers(rounds)).toEqual(["/concurrency/rounds/1/B"]);
  });

  it("flags a step with an unknown kind value", () => {
    // A `kind` sourced from malformed YAML (neither `read` nor `write`) — cast past the
    // type to simulate the untyped parsed input the runtime guard defends against; a
    // well-typed `ConcurrencyStep.kind` cannot express it.
    const rounds = [
      { A: { kind: "select", statements: SHARED_READ_STATEMENTS } },
    ] as unknown as Parameters<typeof concurrencySuccessStepProblems>[0];
    expect(problemPointers(rounds)).toEqual(["/concurrency/rounds/0/A"]);
  });

  it("flags a kind: read step missing expectRows, naming its pointer + reason", () => {
    // The parity gap this guard closes: a `kind: read` step with no `expectRows` would,
    // absent the guard, silently grade its held-session rows against an EMPTY expectation
    // (a spurious pass) instead of failing as malformed. `expectRows` is an OPTIONAL field
    // on `ConcurrencyStep`, so omitting it is already type-valid — no cast needed.
    const rounds = [
      { A: { kind: "read", statements: SHARED_READ_STATEMENTS } }, // no expectRows
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

/** Wrap concurrency rounds into a full concurrencySuccess case document. */
function concurrencySuccessCase(rounds: readonly unknown[]): unknown {
  return {
    model: "models/account.yaml",
    tags: CONCURRENCY_TAGS,
    shape: "concurrencySuccess",
    given: { fixtures: true },
    when: { concurrency: { rounds } },
  };
}

describe("compatibility-case.schema.json — the concurrency-step kind if/then", () => {
  const validate = caseValidator();

  it("accepts m-read-lock-007's shape (two kind: read steps carrying expectRows)", () => {
    const valid = validate(
      concurrencySuccessCase([
        { A: { kind: "read", statements: SHARED_READ_STATEMENTS, expectRows: [{ id: 2 }] } },
        { B: { kind: "read", statements: SHARED_READ_STATEMENTS, expectRows: [{ id: 2 }] } },
      ]),
    );
    expect(valid).toBe(true);
  });

  it("accepts m-read-lock-008's shape (kind: read + kind: write, the write omitting expectRows)", () => {
    const valid = validate(
      concurrencySuccessCase([
        {
          A: {
            kind: "read",
            statements: statements("select distinct t0.id from account t0"),
            expectRows: [{ id: 1 }],
          },
        },
        {
          B: {
            kind: "write",
            statements: statements("update account set balance = ? where id = ?", [999, 2]),
          },
        },
      ]),
    );
    expect(valid).toBe(true);
  });

  it("rejects a success step missing kind (the success branch requires it)", () => {
    const valid = validate(
      concurrencySuccessCase([
        { A: { statements: SHARED_READ_STATEMENTS, expectRows: [{ id: 2 }] } },
      ]),
    );
    expect(valid).toBe(false);
  });

  it("rejects a kind: read step missing expectRows (the if/then requires it)", () => {
    const valid = validate(
      concurrencySuccessCase([{ A: { kind: "read", statements: SHARED_READ_STATEMENTS } }]),
    );
    expect(valid).toBe(false);
  });

  it("rejects a kind: write step carrying expectRows (the if/then forbids it)", () => {
    const valid = validate(
      concurrencySuccessCase([
        {
          A: {
            kind: "write",
            statements: statements("update account set balance = ? where id = ?", [999, 2]),
            expectRows: [{ id: 2 }],
          },
        },
      ]),
    );
    expect(valid).toBe(false);
  });
});
