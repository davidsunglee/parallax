/**
 * `@parallax/transactions` unit tests (Docker-free, pure) — the M8 set-based
 * batched-flush SQL discipline, in isolation from the metamodel and a database.
 *
 * Pins the exact canonical DML each batched form emits — the `m-batch-write-001` / `m-batch-write-002`
 * wallet-shaped goldens (plus the single-row insert form):
 *
 *  - buffered inserts collapse into ONE multi-row `INSERT` (row count from the
 *    tuple repetition);
 *  - a uniform batched update is one `set <col> = ? where pk in (?, …)`;
 *  - a non-uniform batched update is one keyed `UPDATE` per distinct key.
 *
 * (The in-transaction shared read lock is a dialect concern — `applyReadLock` in
 * `@parallax/dialect`; its unit test lives beside it in `packages/dialect/test`.)
 *
 * The batched subject is the NON-VERSIONED `Wallet` (`id`/`owner`/`balance`),
 * matching the corpus: the readless batched forms are honest only for a
 * non-versioned entity — a versioned entity's set-based update MUST materialize
 * into per-object version-advancing updates (M10 / ADR 0031), so the batched
 * forms cannot apply to it.
 */
import {
  type BatchTarget,
  combineWrites,
  keyedUpdate,
  multiRowInsert,
  uniformUpdate,
  type WriteStep,
} from "@parallax/transactions";
import { describe, expect, it } from "vitest";

/** The `wallet` batched-write target (id/owner/balance, pk id) — the corpus m-batch-write-001/m-batch-write-002 shape. */
const WALLET: BatchTarget = {
  table: "wallet",
  columns: ["id", "owner", "balance"],
  pkColumn: "id",
};

describe("batched insert (multi-row INSERT)", () => {
  it("collapses three buffered inserts into one 3-tuple INSERT (m-batch-write-001)", () => {
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
  it("renders the uniform `pk in (…)` form over two keys (m-batch-write-001 step 2)", () => {
    expect(uniformUpdate(WALLET, "balance", 2)).toBe(
      "update wallet set balance = ? where id in (?, ?)",
    );
  });

  it("renders one keyed UPDATE for the per-key form (m-batch-write-002)", () => {
    expect(keyedUpdate(WALLET, "balance")).toBe("update wallet set balance = ? where id = ?");
  });
});

describe("combineWrites — the unit-of-work planner", () => {
  it("plans m-batch-write-001: one multi-row insert then one uniform update, in order", () => {
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

  it("plans m-batch-write-002: one keyed UPDATE per distinct key (statements: 2)", () => {
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
