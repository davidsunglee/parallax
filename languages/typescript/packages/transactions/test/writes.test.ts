/**
 * `@parallax/transactions` unit tests (Docker-free, pure) — the M8 set-based
 * batched-flush + read-lock SQL discipline, in isolation from the metamodel and a
 * database.
 *
 * Pins the exact canonical DML each batched form emits (the `0604` / `0612` /
 * `0613` goldens) and the `0603` read-lock suffix:
 *
 *  - buffered inserts collapse into ONE multi-row `INSERT` (row count from the
 *    tuple repetition);
 *  - a uniform batched update is one `set <col> = ? where pk in (?, …)`;
 *  - a non-uniform batched update is one keyed `UPDATE` per distinct key;
 *  - the shared read lock appends `for share of t0` after every other clause.
 */
import {
  appendReadLock,
  type BatchTarget,
  combineWrites,
  keyedUpdate,
  multiRowInsert,
  uniformUpdate,
  type WriteStep,
} from "@parallax/transactions";
import { describe, expect, it } from "vitest";

/** The `account` batched-write target (id/owner/balance/version, pk id). */
const ACCOUNT: BatchTarget = {
  table: "account",
  columns: ["id", "owner", "balance", "version"],
  pkColumn: "id",
};

describe("batched insert (multi-row INSERT)", () => {
  it("collapses three buffered inserts into one 3-tuple INSERT (0604)", () => {
    expect(multiRowInsert(ACCOUNT, 3)).toBe(
      "insert into account(id, owner, balance, version) values (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)",
    );
  });

  it("renders a single-row INSERT for one row (an FK-ordered insert, 0612)", () => {
    expect(multiRowInsert(ACCOUNT, 1)).toBe(
      "insert into account(id, owner, balance, version) values (?, ?, ?, ?)",
    );
  });

  it("rejects a non-positive row count", () => {
    expect(() => multiRowInsert(ACCOUNT, 0)).toThrow(/at least one row/);
  });
});

describe("batched update forms", () => {
  it("renders the uniform `pk in (…)` form over two keys (0604 step 2)", () => {
    expect(uniformUpdate(ACCOUNT, "balance", 2)).toBe(
      "update account set balance = ? where id in (?, ?)",
    );
  });

  it("renders one keyed UPDATE for the per-key form (0613)", () => {
    expect(keyedUpdate(ACCOUNT, "balance")).toBe("update account set balance = ? where id = ?");
  });
});

describe("combineWrites — the unit-of-work planner", () => {
  it("plans 0604: one multi-row insert then one uniform update, in order", () => {
    const steps: WriteStep[] = [
      {
        mutation: "insert",
        target: ACCOUNT,
        statements: 1,
        binds: [[10, "Mira", "100.00", 1, 11, "Omar", "20.00", 1, 12, "Nell", "30.00", 1]],
      },
      {
        mutation: "update",
        target: ACCOUNT,
        statements: 1,
        binds: [["500.00", 10, 11]],
        setColumn: "balance",
      },
    ];
    const planned = combineWrites(steps);
    expect(planned.map((p) => p.sql)).toEqual([
      "insert into account(id, owner, balance, version) values (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)",
      "update account set balance = ? where id in (?, ?)",
    ]);
    expect(planned[1]?.binds).toEqual(["500.00", 10, 11]);
  });

  it("plans 0613: one keyed UPDATE per distinct key (statements: 2)", () => {
    const step: WriteStep = {
      mutation: "update",
      target: ACCOUNT,
      statements: 2,
      binds: [
        ["111.00", 1],
        ["222.00", 2],
      ],
      setColumn: "balance",
    };
    const planned = combineWrites([step]);
    expect(planned.map((p) => p.sql)).toEqual([
      "update account set balance = ? where id = ?",
      "update account set balance = ? where id = ?",
    ]);
    expect(planned.map((p) => p.binds)).toEqual([
      ["111.00", 1],
      ["222.00", 2],
    ]);
  });

  it("rejects an insert whose bind arity is not a multiple of the columns", () => {
    const step: WriteStep = {
      mutation: "insert",
      target: ACCOUNT,
      statements: 1,
      binds: [[1, "Ada", "10.00"]], // 3 values, 4 columns
    };
    expect(() => combineWrites([step])).toThrow(/not a multiple/);
  });
});

describe("appendReadLock (0603)", () => {
  it("appends the Postgres shared-row-lock suffix after every other clause", () => {
    const read = "select t0.id, t0.owner, t0.balance from account t0 where t0.id = ?";
    expect(appendReadLock(read)).toBe(`${read} for share of t0`);
  });

  it("qualifies the suffix by the given root alias", () => {
    expect(appendReadLock("select t1.x from y t1", "t1")).toBe(
      "select t1.x from y t1 for share of t1",
    );
  });
});
