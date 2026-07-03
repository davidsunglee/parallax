/**
 * Runtime `TransactionWriter` behavior (developer-surface remediation).
 *
 * Write-surface guarantees the conformance slice does not exercise directly:
 *
 *  1. FK-safe insert ordering (spec §4, `0612`): buffered inserts flush with a
 *     referenced parent's INSERT before a dependent child's, EVEN WHEN the
 *     developer authored the child `create` first (`combineWrites` does not infer
 *     FK dependencies, so the runtime must topologically order them itself).
 *  2. Plain `update` on a NON-versioned entity applies the WHOLE assignment array
 *     (spec §4) — `update <t> set c1 = ?, c2 = ? where pk = ?`.
 *  3. VERSIONED `update` (M10, ADR 0029): the version is framework-owned — a prior
 *     in-transaction find records the OBSERVED version, and a later keyed update
 *     advances it (both modes) and gates on it (optimistic mode). An unobserved row
 *     read-before-writes; a no-op `set` issues no DML; a 0-row optimistic gate is a
 *     conflict. In `locking` mode the read takes the `for share of t0` suffix.
 *
 * The runtime is built through the real `createParallax` factory with a stub
 * `ParallaxDatabase` that records the compiled SQL + binds and implements the
 * optional `transaction(body)` port (running the body against the same recording
 * stub), so the write path is exercised end to end the way the barrel drives it.
 */
import { loadCase } from "@parallax/conformance";
import { describe, expect, it } from "vitest";
import {
  createParallax,
  type ParallaxDatabase,
  ParallaxOptimisticLockError,
  ParallaxReadBeforeWriteError,
  type ParallaxRow,
  Predicate,
} from "../src/index.js";

/** A recorded statement: the compiled SQL and its ordered binds. */
interface RecordedQuery {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/**
 * A stub database port that records every executed statement. A SELECT returns the
 * canned `selectRows`; a write (a statement ending `returning 1`) returns an array
 * whose length is the affected-row count (`updateAffected`, defaulting to the
 * select-row count) so a versioned update can be steered to success (1) or conflict
 * (0). It implements the optional `transaction(body)` port by running the body
 * against the same recording stub (commit == the body resolving).
 */
class StubDatabase implements ParallaxDatabase {
  readonly queries: RecordedQuery[] = [];
  private updateAffected: number | undefined;

  constructor(private rows: readonly ParallaxRow[] = []) {}

  setRows(rows: readonly ParallaxRow[]): void {
    this.rows = rows;
  }

  /** Force the affected-row count a write reports (else the select-row count). */
  setUpdateAffected(count: number): void {
    this.updateAffected = count;
  }

  execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    this.queries.push({ sql, binds });
    if (/returning 1$/.test(sql)) {
      const count = this.updateAffected ?? this.rows.length;
      return Promise.resolve(Array.from({ length: count }, () => ({}) as ParallaxRow));
    }
    return Promise.resolve(this.rows);
  }

  transaction<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T> {
    return body(this);
  }
}

/** The orders descriptor (`Order` / `OrderItem`, the `0612` FK-ordering model). */
const ORDERS = loadCase("core/compatibility/cases/0612-fk-insert-ordering.yaml").descriptor;

/** The non-versioned `Wallet` descriptor (two updatable plain columns owner/balance). */
const WALLET = loadCase("core/compatibility/cases/0604-batched-write.yaml").descriptor;

/** The versioned `Account` descriptor (carries the optimistic-lock `version` column). */
const ACCOUNT = loadCase(
  "core/compatibility/cases/0611-versioned-update-locking-mode.yaml",
).descriptor;

/** A physical Account row the stub returns for an in-transaction find (version 1). */
const ACCOUNT_ROW: ParallaxRow = { id: 2, owner: "Linus", balance: "250.00", version: 1 };

/** A pk-equality predicate on `Account.id`. */
const accountPk = (id: number): Predicate =>
  new Predicate({ eq: { attr: "Account.id", value: id } });

/** The index of the first recorded statement whose SQL contains `needle`. */
function indexOf(queries: readonly RecordedQuery[], needle: string): number {
  return queries.findIndex((q) => q.sql.includes(needle));
}

describe("TransactionWriter FK-safe insert ordering (spec §4, 0612)", () => {
  it("orders a parent INSERT before a child even when the child was created first", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: ORDERS, database: db });

    await px.transaction(async (tx) => {
      // Author the CHILD before the PARENT — the failing order the bug preserves.
      await tx.entity("OrderItem").create({ id: 200, orderId: 100, sku: "X-1", quantity: 3 });
      await tx.entity("Order").create({
        id: 100,
        name: "Hopper",
        sku: "X-1",
        qty: 1,
        price: 9.99,
        active: true,
        orderedOn: "2024-07-01",
      });
    });

    const parentAt = indexOf(db.queries, "insert into orders");
    const childAt = indexOf(db.queries, "insert into order_item");
    expect(parentAt).toBeGreaterThanOrEqual(0);
    expect(childAt).toBeGreaterThanOrEqual(0);
    // The referenced parent's INSERT must precede the dependent child's.
    expect(parentAt).toBeLessThan(childAt);
  });

  it("keeps a parent-first author order unchanged (parent before child)", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: ORDERS, database: db });

    await px.transaction(async (tx) => {
      await tx.entity("Order").create({
        id: 100,
        name: "Hopper",
        sku: "X-1",
        qty: 1,
        price: 9.99,
        active: true,
        orderedOn: "2024-07-01",
      });
      await tx.entity("OrderItem").create({ id: 200, orderId: 100, sku: "X-1", quantity: 3 });
    });

    const parentAt = indexOf(db.queries, "insert into orders");
    const childAt = indexOf(db.queries, "insert into order_item");
    expect(parentAt).toBeGreaterThanOrEqual(0);
    expect(childAt).toBeGreaterThanOrEqual(0);
    expect(parentAt).toBeLessThan(childAt);
  });
});

describe("TransactionWriter plain update applies every assignment (spec §4)", () => {
  it("sets ALL columns in a multi-assignment plain update and binds values then pk", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: WALLET, database: db });

    // A plain (non-versioned Wallet) update of TWO columns.
    await px.transaction(async (tx) => {
      await tx.entity("Wallet").update(new Predicate({ eq: { attr: "Wallet.id", value: 10 } }), {
        set: [
          { attr: "owner", value: "Mira" },
          { attr: "balance", value: 500 },
        ],
      });
    });

    const update = db.queries.find((q) => q.sql.includes("update wallet"));
    expect(update).toBeDefined();
    const { sql, binds } = update as RecordedQuery;
    // BOTH columns are set (the bug drops everything after the first assignment).
    expect(sql).toContain("set owner = ?, balance = ?");
    expect(sql).toContain("where id = ?");
    // Bind order: each assignment value (wire form) in declaration order, then the pk.
    expect(binds).toEqual(["Mira", 500, 10]);
  });

  it("is a no-op for an empty assignment set", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: WALLET, database: db });

    let result: { affectedRows: number } | undefined;
    await px.transaction(async (tx) => {
      result = await tx
        .entity("Wallet")
        .update(new Predicate({ eq: { attr: "Wallet.id", value: 10 } }), { set: [] });
    });

    expect(result).toEqual({ affectedRows: 0 });
    expect(db.queries.some((q) => q.sql.includes("update wallet"))).toBe(false);
  });
});

describe("TransactionWriter versioned update (M10 framework-owned versions)", () => {
  it("locking mode: an observed row advances the version WITHOUT a gate, and the read locks", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    const result = await px.transaction(async (tx) => {
      const accounts = tx.entity("Account");
      // A prior in-transaction find observes version 1 (and takes the shared lock).
      await accounts.find(accountPk(2)).single();
      return accounts.update(accountPk(2), { set: [{ attr: "balance", value: "500.00" }] });
    });

    // The locking-mode read appends the M8 shared-row-lock suffix (0603).
    const read = db.queries.find((q) => q.sql.startsWith("select"));
    expect(read?.sql.endsWith("for share of t0")).toBe(true);
    // The versioned update advances the version (observed 1 -> 2) with NO gate.
    const update = db.queries.find((q) => q.sql.includes("update account"));
    expect(update?.sql).toContain("set balance = ?, version = ? where id = ?");
    expect(update?.sql).not.toContain("and version = ?");
    expect(update?.binds).toEqual(["500.00", 2, 2]);
    expect(result.affectedRows).toBe(1);
  });

  it("optimistic mode: the read takes NO lock and the update GATES on the observed version", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    const result = await px.transaction(
      async (tx) => {
        const accounts = tx.entity("Account");
        await accounts.find(accountPk(2)).single(); // observes version 1, no lock
        return accounts.update(accountPk(2), { set: [{ attr: "balance", value: "500.00" }] });
      },
      { concurrency: "optimistic" },
    );

    const read = db.queries.find((q) => q.sql.startsWith("select"));
    expect(read?.sql.includes("for share")).toBe(false);
    const update = db.queries.find((q) => q.sql.includes("update account"));
    // The gated form: advance the version AND gate on the observed one.
    expect(update?.sql).toContain("set balance = ?, version = ? where id = ? and version = ?");
    expect(update?.binds).toEqual(["500.00", 2, 2, 1]);
    expect(result.affectedRows).toBe(1);
  });

  it("read-before-write: updating an UNOBSERVED versioned row throws", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    await expect(
      px.transaction(async (tx) => {
        // No prior find — the version was never observed.
        return tx.entity("Account").update(accountPk(2), {
          set: [{ attr: "balance", value: "500.00" }],
        });
      }),
    ).rejects.toBeInstanceOf(ParallaxReadBeforeWriteError);
    // No UPDATE was issued (the read-before-write short-circuits).
    expect(db.queries.some((q) => q.sql.includes("update account"))).toBe(false);
  });

  it("no-op: a versioned update whose set changes no attribute issues no DML", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    let result: { affectedRows: number } | undefined;
    await px.transaction(async (tx) => {
      const accounts = tx.entity("Account");
      await accounts.find(accountPk(2)).single();
      result = await accounts.update(accountPk(2), { set: [] });
    });

    expect(result).toEqual({ affectedRows: 0 });
    expect(db.queries.some((q) => q.sql.includes("update account"))).toBe(false);
  });

  it("optimistic conflict: a 0-row gated update throws ParallaxOptimisticLockError", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    db.setUpdateAffected(0); // the gate matches no row — a concurrent writer advanced it
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    await expect(
      px.transaction(
        async (tx) => {
          const accounts = tx.entity("Account");
          await accounts.find(accountPk(2)).single();
          return accounts.update(accountPk(2), { set: [{ attr: "balance", value: "500.00" }] });
        },
        { concurrency: "optimistic" },
      ),
    ).rejects.toBeInstanceOf(ParallaxOptimisticLockError);
  });
});
