/**
 * `deepFetch` orchestration unit tests (Docker-free, pure).
 *
 * Drives the m-deep-fetch deep-fetch strategy directly with a FAKE `exec` and hand-built
 * `DeepFetchNode` trees — no metamodel, compiler, or database — to pin the
 * round-trip discipline the conformance suite grades:
 *
 *  - `m-deep-fetch-003` (1 -> N -> N): three statements (root + items + statuses), NOT
 *    `1 + N + N`, so `roundTrips === 3` and the item-level IN list is the DISTINCT
 *    item ids gathered from the items level.
 *  - `m-deep-fetch-007` (shared prefix): `[items]` and `[items, statuses]` share the `items`
 *    hop, which is fetched ONCE — three statements, not four.
 *  - `m-deep-fetch-006` (empty root): the root gathered no parent keys, so every child level
 *    is elided — one statement (`roundTrips === 1`), no child `exec`.
 *  - `m-deep-fetch-008` (empty intermediate): the items level executes but returns NO items,
 *    so the grandchild `statuses` level issues no statement — `roundTrips === 2`.
 *
 * The fake `exec` records every `(sql, binds)` it is called with, so the test
 * asserts the exact statement count AND the exact per-level IN binds (the keys
 * gathered from the previous level), which is what proves N+1 elimination.
 */
import type { DeepFetchNode, Exec, Key, LevelQuery, Row } from "@parallax/relationships";
import { deepFetch } from "@parallax/relationships";
import { describe, expect, it } from "vitest";

/** A recorded `exec` call: the SQL it issued and the binds it carried. */
interface IssuedStatement {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/**
 * A fake `exec` backed by an in-memory table of child rows per relationship name.
 * Each level's `compileLevel` tags its SQL with the relationship name and the
 * gathered keys; the fake returns the rows whose child column matches a key,
 * mimicking `where <childCol> in (?, …)`. Every call is recorded so the test can
 * assert the exact statement count and IN binds.
 */
function fakeExec(tables: Record<string, { childColumn: string; rows: readonly Row[] }>): {
  exec: Exec;
  issued: IssuedStatement[];
} {
  const issued: IssuedStatement[] = [];
  const exec: Exec = async (sql, binds) => {
    issued.push({ sql, binds });
    const relName = sql.replace(/^level:/, "");
    const table = tables[relName];
    if (!table) {
      return [];
    }
    const keys = new Set(binds.map((b) => String(b)));
    return table.rows.filter((row) => keys.has(String(row[table.childColumn])));
  };
  return { exec, issued };
}

/** Build a `DeepFetchNode`; its `compileLevel` tags SQL with the relationship name. */
function node(
  name: string,
  parentColumn: string,
  childColumn: string,
  children: readonly DeepFetchNode[] = [],
  toOne = false,
): DeepFetchNode {
  const compileLevel = (keys: readonly Key[]): LevelQuery => ({
    sql: `level:${name}`,
    binds: keys.map((k) => k),
  });
  return { name, toOne, parentColumn, childColumn, compileLevel, children };
}

describe("deepFetch — round-trip discipline (1 + L, never N+1)", () => {
  it("m-deep-fetch-003: 1 -> N -> N resolves in exactly THREE statements (roundTrips === 3)", async () => {
    // Root: orders {1, 42}. items keyed by order_id, statuses keyed by
    // order_item_id — one bulk query per level.
    const rootRows: Row[] = [
      { id: 1, name: "Ada" },
      { id: 42, name: "Grace" },
    ];
    const items: Row[] = [
      { id: 12, order_id: 1, sku: "B-200", quantity: 1 },
      { id: 11, order_id: 1, sku: "A-100", quantity: 2 },
      { id: 422, order_id: 42, sku: "B-200", quantity: 5 },
      { id: 421, order_id: 42, sku: "A-999", quantity: 3 },
    ];
    const statuses: Row[] = [
      { id: 203, order_item_id: 12, code: "PICKED" },
      { id: 202, order_item_id: 11, code: "PACKED" },
      { id: 201, order_item_id: 11, code: "PICKED" },
      { id: 204, order_item_id: 421, code: "PICKED" },
    ];
    const { exec, issued } = fakeExec({
      items: { childColumn: "order_id", rows: items },
      statuses: { childColumn: "order_item_id", rows: statuses },
    });

    const tree = [node("items", "id", "order_id", [node("statuses", "id", "order_item_id")])];
    const result = await deepFetch(rootRows, tree, exec);

    // Root (implicit, roundTrips starts at 1) + items + statuses = 3.
    expect(result.roundTrips).toBe(3);
    expect(issued).toHaveLength(2); // deepFetch issues only the CHILD statements.

    // Level 1 IN binds = distinct order ids {1, 42}; level 2 = distinct item ids
    // {12, 11, 422, 421} in FIRST-APPEARANCE order (the items arrive `id desc`).
    // The IN-list order is NOT part of the contract — it never affects which
    // children match — so the runtime keeps first-appearance order (no sort) and
    // the harness compares these binds as an order-insensitive set. What matters
    // here is that the level is keyed by the DISTINCT key set, NOT one query per
    // parent.
    expect(issued[0]?.binds).toEqual([1, 42]);
    expect(issued[1]?.binds).toEqual([12, 11, 422, 421]);

    // Item 422 has no statuses ⇒ empty list; item 421 has one.
    const order42 = result.rows.find((r) => r.id === 42) as Row;
    const order42Items = order42.items as Row[];
    const item422 = order42Items.find((i) => i.id === 422) as Row;
    const item421 = order42Items.find((i) => i.id === 421) as Row;
    expect(item422.statuses).toEqual([]);
    expect((item421.statuses as Row[]).map((s) => s.id)).toEqual([204]);
  });

  it("m-deep-fetch-007: a SHARED prefix hop is fetched ONCE (three statements, not four)", async () => {
    // Two paths, [items] and [items, statuses], share the `items` hop.
    const rootRows: Row[] = [
      { id: 1, name: "Ada" },
      { id: 2, name: "Linus" },
    ];
    const items: Row[] = [
      { id: 11, order_id: 1 },
      { id: 21, order_id: 2 },
    ];
    const statuses: Row[] = [{ id: 201, order_item_id: 11, code: "PICKED" }];
    const { exec, issued } = fakeExec({
      items: { childColumn: "order_id", rows: items },
      statuses: { childColumn: "order_item_id", rows: statuses },
    });

    // The merged tree has ONE `items` node with `statuses` as its only child.
    const tree = [node("items", "id", "order_id", [node("statuses", "id", "order_item_id")])];
    const result = await deepFetch(rootRows, tree, exec);

    expect(result.roundTrips).toBe(3);
    expect(issued.map((s) => s.sql)).toEqual(["level:items", "level:statuses"]);
    // `items` appears exactly once in the issued statements.
    expect(issued.filter((s) => s.sql === "level:items")).toHaveLength(1);
  });

  it("m-deep-fetch-006: an EMPTY root elides all child levels (roundTrips === 1, no child exec)", async () => {
    const rootRows: Row[] = [];
    const { exec, issued } = fakeExec({
      items: { childColumn: "order_id", rows: [] },
      statuses: { childColumn: "order_item_id", rows: [] },
    });

    const tree = [node("items", "id", "order_id", [node("statuses", "id", "order_item_id")])];
    const result = await deepFetch(rootRows, tree, exec);

    expect(result.roundTrips).toBe(1);
    expect(issued).toHaveLength(0); // no child statement issued at all
    expect(result.rows).toEqual([]);
  });

  it("m-deep-fetch-008: an EMPTY intermediate elides the grandchild (roundTrips === 2)", async () => {
    // Root pins order 4, which has NO items; the items level executes (keyed by
    // {4}) and returns zero rows, so the statuses grandchild issues no statement.
    const rootRows: Row[] = [{ id: 4, name: "Margaret" }];
    const { exec, issued } = fakeExec({
      items: { childColumn: "order_id", rows: [] }, // order 4 has no items
      statuses: { childColumn: "order_item_id", rows: [] },
    });

    const tree = [node("items", "id", "order_id", [node("statuses", "id", "order_item_id")])];
    const result = await deepFetch(rootRows, tree, exec);

    // Root + items (executes, empty) = 2; statuses is elided (no parent keys).
    expect(result.roundTrips).toBe(2);
    expect(issued.map((s) => s.sql)).toEqual(["level:items"]);
    expect(issued[0]?.binds).toEqual([4]);
    // Order 4 is decorated with an empty items list.
    expect((result.rows[0] as Row).items).toEqual([]);
  });
});
