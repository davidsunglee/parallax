/**
 * DB-free fidelity suite for the grouped compatibility-case schema (COR-23) — the
 * TypeScript mirror of the reference harness's `test_case_schema.py`.
 *
 * The `@parallax/conformance` loader validates every case document once at load
 * against `core/schemas/compatibility-case.schema.json` behind the `validateCase`
 * seam (Ajv2020, the same library `schema.ts` uses for adapter envelopes). This
 * suite pins that seam three ways:
 *
 *  - every migrated corpus case loads (and so validates) without throwing;
 *  - a minimal well-formed document for each of the eight shapes is ACCEPTED; and
 *  - a curated set of malformed documents — the legacy flat layout, a mislabeled
 *    `shape`, a plain-string `sql` at a golden location, an empty `sql` map, an
 *    extra key inside a closed group, `binds` authored outside a statement entry, a
 *    retry attempt carrying the legacy `expectedAffectedRows` name, and a read case
 *    with a stray cross-shape `when` member — is REJECTED.
 *
 * The accept/reject corpus is kept in lockstep with the Python fidelity suite so the
 * two harnesses agree on exactly which documents are valid.
 */
// biome-ignore-all lint/suspicious/noThenProperty: `then` is a compatibility-case group name (plain data, never a thenable), not a Promise-like `then`.
import { describe, expect, it } from "vitest";
import { discoverCasePaths, loadCase, validateCase } from "../src/discover.js";

/** True when the loader seam accepts a document (no validation throw). */
function accepts(doc: unknown): boolean {
  try {
    validateCase(doc, "fixture");
    return true;
  } catch {
    return false;
  }
}

// --- minimal well-formed documents, one per shape --------------------------

function readCase(): Record<string, unknown> {
  return {
    model: "models/orders.yaml",
    tags: ["m-agg"],
    shape: "read",
    when: { targetEntity: "Order", operation: { all: {} } },
    then: {
      statements: [{ sql: { postgres: "select t0.id from orders t0" }, binds: [] }],
      rows: [{ id: 1 }],
      roundTrips: 1,
    },
  };
}

function writeSequenceCase(): Record<string, unknown> {
  return {
    model: "models/balance.yaml",
    tags: ["m-audit-write"],
    shape: "writeSequence",
    when: {
      writeSequence: [{ mutation: "insert", entity: "Balance", rows: [{ id: 1, acctNum: "A" }] }],
    },
    then: {
      statements: [{ sql: { postgres: "insert into balance(bal_id) values (?)" }, binds: [1] }],
      tableState: { balance: [{ bal_id: 1 }] },
    },
  };
}

function scenarioCase(): Record<string, unknown> {
  return {
    model: "models/account.yaml",
    tags: ["m-unit-work"],
    shape: "scenario",
    when: {
      scenario: [
        {
          targetEntity: "Account",
          find: { eq: { attr: "Account.id", value: 7 } },
          roundTrips: 1,
          statements: [
            { sql: { postgres: "select t0.id from account t0 where t0.id = ?" }, binds: [7] },
          ],
          expectRows: [{ id: 7 }],
        },
      ],
    },
    then: { roundTrips: 1 },
  };
}

function conflictCase(): Record<string, unknown> {
  return {
    model: "models/account.yaml",
    tags: ["m-opt-lock"],
    shape: "conflict",
    given: { apply: [{ sql: "update account set version = 2 where id = 2" }] },
    when: { uow: { concurrency: "optimistic" }, write: { id: 2, observedVersion: 1 } },
    then: {
      statements: [
        {
          sql: { postgres: "update account set balance = ? where id = ? and version = ?" },
          binds: [250.0, 2, 1],
        },
      ],
      affectedRows: 0,
      tableState: { account: [{ id: 2, version: 2 }] },
    },
  };
}

function conflictRetryCase(): Record<string, unknown> {
  return {
    model: "models/account.yaml",
    tags: ["m-opt-lock"],
    shape: "conflict",
    given: { apply: [{ sql: "update account set version = 2 where id = 2" }] },
    when: {
      uow: { concurrency: "optimistic" },
      attempts: [
        {
          statements: [
            {
              sql: { postgres: "update account set balance = ? where id = ? and version = ?" },
              binds: [250.0, 2, 1],
            },
          ],
          write: { id: 2, balance: 250.0, observedVersion: 1 },
          affectedRows: 0,
        },
        {
          statements: [
            {
              sql: { postgres: "update account set balance = ? where id = ? and version = ?" },
              binds: [250.0, 2, 2],
            },
          ],
          write: { id: 2, balance: 250.0, observedVersion: 2 },
          affectedRows: 1,
        },
      ],
    },
    then: { tableState: { account: [{ id: 2, version: 3 }] } },
  };
}

function coherenceCase(): Record<string, unknown> {
  const stepSql = [
    { sql: { postgres: "select t0.id from account t0 where t0.id = ?" }, binds: [2] },
  ];
  return {
    model: "models/account.yaml",
    tags: ["m-coherence"],
    shape: "coherence",
    when: {
      coherence: [
        {
          node: "B",
          kind: "read",
          targetEntity: "Account",
          statements: stepSql,
          observeRows: [{ id: 2 }],
        },
        {
          node: "A",
          kind: "write",
          statements: [
            { sql: { postgres: "update account set balance = ? where id = ?" }, binds: [9, 2] },
          ],
        },
      ],
    },
  };
}

function errorCase(): Record<string, unknown> {
  const stmt = { sql: { postgres: "insert into widget(id) values (?)" }, binds: [1] };
  return {
    model: "models/error-cases.yaml",
    tags: ["m-db-error"],
    shape: "error",
    then: {
      statements: [stmt, stmt],
      errorClass: "uniqueViolation",
      nativeCode: { postgres: "23505", mariadb: 1062 },
    },
  };
}

function concurrencySuccessCase(): Record<string, unknown> {
  return {
    model: "models/account.yaml",
    tags: ["m-read-lock"],
    shape: "concurrencySuccess",
    given: { fixtures: true },
    when: {
      concurrency: {
        rounds: [
          {
            A: {
              kind: "read",
              statements: [
                { sql: { postgres: "select t0.id from account t0 where t0.id = ?" }, binds: [2] },
              ],
              expectRows: [{ id: 2 }],
            },
          },
        ],
      },
    },
  };
}

function boundaryCase(): Record<string, unknown> {
  return {
    model: "models/account.yaml",
    tags: ["m-auto-retry"],
    shape: "boundary",
    lane: "api-conformance",
    given: { fault: "serialization-failure" },
    when: {
      uow: { concurrency: "optimistic" },
      boundary: [{ action: "read" }, { action: "update" }],
    },
    then: { outcome: "committed" },
  };
}

const VALID_CASES: Record<string, () => Record<string, unknown>> = {
  read: readCase,
  writeSequence: writeSequenceCase,
  scenario: scenarioCase,
  conflict: conflictCase,
  "conflict-retry": conflictRetryCase,
  coherence: coherenceCase,
  error: errorCase,
  concurrencySuccess: concurrencySuccessCase,
  boundary: boundaryCase,
};

// --- rejected malformed documents ------------------------------------------

/** The pre-migration flat layout: no shape, positional goldenSql/binds. */
function legacyLayout(): Record<string, unknown> {
  return {
    model: "models/orders.yaml",
    tags: ["m-agg"],
    operation: { all: {} },
    goldenSql: { postgres: "select t0.id from orders t0" },
    binds: [],
    expectedRows: [{ id: 1 }],
  };
}

/** A well-formed writeSequence document mislabeled as a read. */
function mislabeledShape(): Record<string, unknown> {
  const doc = writeSequenceCase();
  doc.shape = "read";
  return doc;
}

/** A golden statement whose sql is a plain string instead of a dialect map. */
function stringSqlAtGoldenLocation(): Record<string, unknown> {
  const doc = readCase();
  (doc.then as { statements: { sql: unknown }[] }).statements[0]!.sql =
    "select t0.id from orders t0";
  return doc;
}

/** A golden statement whose sql map declares no dialect. */
function emptySqlMap(): Record<string, unknown> {
  const doc = readCase();
  (doc.then as { statements: { sql: unknown }[] }).statements[0]!.sql = {};
  return doc;
}

/** A stray legacy key inside the closed `then` group. */
function extraKeyInClosedGroup(): Record<string, unknown> {
  const doc = readCase();
  (doc.then as Record<string, unknown>).expectedRows = [{ id: 1 }];
  return doc;
}

/** `binds` authored at the root instead of inside a statement entry. */
function bindsOutsideStatementEntry(): Record<string, unknown> {
  const doc = readCase();
  doc.binds = [1];
  return doc;
}

/** A retry attempt carrying the legacy `expectedAffectedRows` name. */
function attemptLegacyAffectedRows(): Record<string, unknown> {
  const doc = conflictRetryCase();
  const attempt = (doc.when as { attempts: Record<string, unknown>[] }).attempts[0]!;
  attempt.expectedAffectedRows = attempt.affectedRows;
  delete attempt.affectedRows;
  return doc;
}

/** A read case carrying a stray cross-shape `when.boundary` block. */
function crossShapeWhenMember(): Record<string, unknown> {
  const doc = readCase();
  (doc.when as Record<string, unknown>).boundary = [{ action: "read" }];
  return doc;
}

const REJECTED_CASES: Record<string, () => Record<string, unknown>> = {
  "legacy-layout": legacyLayout,
  "mislabeled-shape": mislabeledShape,
  "string-sql-at-golden-location": stringSqlAtGoldenLocation,
  "empty-sql-map": emptySqlMap,
  "extra-key-in-closed-group": extraKeyInClosedGroup,
  "binds-outside-statement-entry": bindsOutsideStatementEntry,
  "attempt-legacy-affected-rows": attemptLegacyAffectedRows,
  "cross-shape-when-member": crossShapeWhenMember,
};

describe("compatibility-case.schema.json — every migrated corpus case validates at load", () => {
  it.each(discoverCasePaths())("%s loads + validates without throwing", (path) => {
    expect(() => loadCase(path)).not.toThrow();
  });
});

describe("compatibility-case.schema.json — a minimal document per shape is accepted", () => {
  it.each(Object.keys(VALID_CASES))("accepts a minimal %s case", (shape) => {
    expect(accepts(VALID_CASES[shape]?.() ?? {})).toBe(true);
  });
});

describe("compatibility-case.schema.json — malformed documents are rejected", () => {
  it.each(Object.keys(REJECTED_CASES))("rejects %s", (label) => {
    expect(accepts(REJECTED_CASES[label]?.() ?? {})).toBe(false);
  });
});
