/**
 * Runtime `TransactionWriter` behavior (developer-surface remediation).
 *
 * Two write-surface guarantees the conformance slice does not exercise, because
 * the API Conformance Suite authors parent inserts before children and only ever assigns a
 * single plain column — masking these developer-runtime bugs:
 *
 *  1. FK-safe insert ordering (spec §3, `0612`): buffered inserts flush with a
 *     referenced parent's INSERT before a dependent child's, EVEN WHEN the
 *     developer authored the child `create` first (`combineWrites` does not infer
 *     FK dependencies, so the runtime must topologically order them itself).
 *  2. Plain `update` applies the WHOLE assignment array (spec §3), not just the
 *     first entry — `update <t> set c1 = ?, c2 = ? where pk = ?`, values in
 *     declaration order then the pk.
 *
 * The runtime is built through the real `createParallax` factory with a stub
 * `ParallaxDatabase` that records the compiled SQL + binds and implements the
 * optional `transaction(body)` port (running the body against the same recording
 * stub), so the write path — buffer, FK-sort, flush at commit — is exercised end
 * to end the way the generated barrel drives it.
 */
import { loadCase } from "@parallax/conformance";
import { describe, expect, it } from "vitest";
import {
  createParallax,
  type ParallaxDatabase,
  type ParallaxRow,
  Predicate,
} from "../src/index.js";

/** A recorded statement: the compiled SQL and its ordered binds. */
interface RecordedQuery {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/**
 * A stub database port that records every executed statement and returns canned
 * rows. It implements the optional `transaction(body)` port by running the body
 * against the same recording stub (commit == the body resolving), so buffered
 * inserts flush at the end of the transaction body.
 */
class StubDatabase implements ParallaxDatabase {
  readonly queries: RecordedQuery[] = [];

  constructor(private rows: readonly ParallaxRow[] = []) {}

  setRows(rows: readonly ParallaxRow[]): void {
    this.rows = rows;
  }

  execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    this.queries.push({ sql, binds });
    return Promise.resolve(this.rows);
  }

  transaction<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T> {
    return body(this);
  }
}

/** The orders descriptor (`Order` / `OrderItem`, the `0612` FK-ordering model). */
const ORDERS = loadCase("core/compatibility/cases/0612-fk-insert-ordering.yaml").descriptor;

/** The account descriptor (`Account`, two updatable plain columns `owner`/`balance`). */
const ACCOUNT = loadCase("core/compatibility/cases/0604-batched-write.yaml").descriptor;

/** The index of the first recorded statement whose SQL contains `needle`. */
function indexOf(queries: readonly RecordedQuery[], needle: string): number {
  return queries.findIndex((q) => q.sql.includes(needle));
}

describe("TransactionWriter FK-safe insert ordering (spec §3, 0612)", () => {
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

describe("TransactionWriter plain update applies every assignment (spec §3)", () => {
  it("sets ALL columns in a multi-assignment plain update and binds values then pk", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    // A plain (non-versioned: no `expectedVersion`) update of TWO columns.
    await px.transaction(async (tx) => {
      await tx.entity("Account").update(new Predicate({ eq: { attr: "Account.id", value: 10 } }), {
        set: [
          { attr: "owner", value: "Mira" },
          { attr: "balance", value: 500 },
        ],
      });
    });

    const update = db.queries.find((q) => q.sql.includes("update account"));
    expect(update).toBeDefined();
    const { sql, binds } = update as RecordedQuery;
    // BOTH columns are set (the bug drops everything after the first assignment).
    expect(sql).toContain("set owner = ?, balance = ?");
    expect(sql).toContain("where id = ?");
    // Bind order: each assignment value (wire form) in declaration order, then
    // the pk.
    expect(binds).toEqual(["Mira", 500, 10]);
  });

  it("is a no-op for an empty assignment set", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    let result: { affectedRows: number } | undefined;
    await px.transaction(async (tx) => {
      result = await tx
        .entity("Account")
        .update(new Predicate({ eq: { attr: "Account.id", value: 10 } }), { set: [] });
    });

    expect(result).toEqual({ affectedRows: 0 });
    expect(db.queries.some((q) => q.sql.includes("update account"))).toBe(false);
  });
});
