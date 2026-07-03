/**
 * `@parallax/transactions` unit tests (Docker-free, pure) — the M8 set-based
 * batched-flush + read-lock SQL discipline, in isolation from the metamodel and a
 * database.
 *
 * Pins the exact canonical DML each batched form emits — the `0604` / `0613`
 * wallet-shaped goldens (plus the single-row insert form) — and the `0603`
 * read-lock suffix:
 *
 *  - buffered inserts collapse into ONE multi-row `INSERT` (row count from the
 *    tuple repetition);
 *  - a uniform batched update is one `set <col> = ? where pk in (?, …)`;
 *  - a non-uniform batched update is one keyed `UPDATE` per distinct key;
 *  - the shared read lock appends `for share of t0` after every other clause.
 *
 * The batched subject is the NON-VERSIONED `Wallet` (`id`/`owner`/`balance`),
 * matching the corpus: the readless batched forms are honest only for a
 * non-versioned entity — a versioned entity's set-based update MUST materialize
 * into per-object version-advancing updates (M10 / ADR 0031), so the batched
 * forms cannot apply to it.
 */
import {
  appendReadLock,
  type BatchTarget,
  combineWrites,
  keyedUpdate,
  multiRowInsert,
  ParallaxUnlockableReadError,
  uniformUpdate,
  type WriteStep,
} from "@parallax/transactions";
import { describe, expect, it } from "vitest";

/** The `wallet` batched-write target (id/owner/balance, pk id) — the corpus 0604/0613 shape. */
const WALLET: BatchTarget = {
  table: "wallet",
  columns: ["id", "owner", "balance"],
  pkColumn: "id",
};

describe("batched insert (multi-row INSERT)", () => {
  it("collapses three buffered inserts into one 3-tuple INSERT (0604)", () => {
    expect(multiRowInsert(WALLET, 3)).toBe(
      "insert into wallet(id, owner, balance) values (?, ?, ?), (?, ?, ?), (?, ?, ?)",
    );
  });

  it("renders a single-row INSERT for one row (the single-tuple degenerate form)", () => {
    expect(multiRowInsert(WALLET, 1)).toBe(
      "insert into wallet(id, owner, balance) values (?, ?, ?)",
    );
  });

  it("rejects a non-positive row count", () => {
    expect(() => multiRowInsert(WALLET, 0)).toThrow(/at least one row/);
  });
});

describe("batched update forms", () => {
  it("renders the uniform `pk in (…)` form over two keys (0604 step 2)", () => {
    expect(uniformUpdate(WALLET, "balance", 2)).toBe(
      "update wallet set balance = ? where id in (?, ?)",
    );
  });

  it("renders one keyed UPDATE for the per-key form (0613)", () => {
    expect(keyedUpdate(WALLET, "balance")).toBe("update wallet set balance = ? where id = ?");
  });
});

describe("combineWrites — the unit-of-work planner", () => {
  it("plans 0604: one multi-row insert then one uniform update, in order", () => {
    const steps: WriteStep[] = [
      {
        mutation: "insert",
        target: WALLET,
        statements: 1,
        binds: [[10, "Mira", "100.00", 11, "Omar", "20.00", 12, "Nell", "30.00"]],
      },
      {
        mutation: "update",
        target: WALLET,
        statements: 1,
        binds: [["500.00", 10, 11]],
        setColumn: "balance",
      },
    ];
    const planned = combineWrites(steps);
    expect(planned.map((p) => p.sql)).toEqual([
      "insert into wallet(id, owner, balance) values (?, ?, ?), (?, ?, ?), (?, ?, ?)",
      "update wallet set balance = ? where id in (?, ?)",
    ]);
    expect(planned[1]?.binds).toEqual(["500.00", 10, 11]);
  });

  it("plans 0613: one keyed UPDATE per distinct key (statements: 2)", () => {
    const step: WriteStep = {
      mutation: "update",
      target: WALLET,
      statements: 2,
      binds: [
        ["111.00", 1],
        ["222.00", 2],
      ],
      setColumn: "balance",
    };
    const planned = combineWrites([step]);
    expect(planned.map((p) => p.sql)).toEqual([
      "update wallet set balance = ? where id = ?",
      "update wallet set balance = ? where id = ?",
    ]);
    expect(planned.map((p) => p.binds)).toEqual([
      ["111.00", 1],
      ["222.00", 2],
    ]);
  });

  it("rejects an insert whose bind arity is not a multiple of the columns", () => {
    const step: WriteStep = {
      mutation: "insert",
      target: WALLET,
      statements: 1,
      binds: [[1, "Ada"]], // 2 values, 3 columns
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

  it("rejects a `distinct` read rather than emit a lock the database forbids", () => {
    // A row lock applies to base rows, so Postgres/MariaDB reject `FOR SHARE` on a
    // DISTINCT result. The seam refuses it here instead of suffixing illegal SQL.
    const distinctRead = "select distinct t0.owner from account t0";
    expect(() => appendReadLock(distinctRead)).toThrow(ParallaxUnlockableReadError);
    // The guard is shape-based (leading `select distinct`), not alias-dependent.
    expect(() => appendReadLock(distinctRead, "t3")).toThrow(/cannot take the .* read lock/);
  });

  it("locks an ordinary (non-distinct) read whose column name merely contains 'distinct'", () => {
    // The guard keys on the `select distinct` projection shape, not a substring, so a
    // plain read that happens to project a `distinct_flag` column is still lockable.
    const read = "select t0.distinct_flag from account t0";
    expect(appendReadLock(read)).toBe(`${read} for share of t0`);
  });
});
