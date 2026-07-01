/**
 * Developer showcase — **reads** family (Phase 10c): non-temporal single-entity
 * reads (00xx / 02xx) and flat navigate / exists reads (03xx flat), written as an
 * application developer would, run against `postgres:17` through the SHIPPED
 * `@parallax/db-postgres` adapter.
 *
 * Each case:
 *  1. `assertSameOperation(dsl, case)` — the developer's DSL predicate builds the
 *     corpus's canonical `operation` (the no-drift guard: a snippet that stops
 *     matching its case fails the build).
 *  2. runs `px.<entity>.find(...)` and asserts the returned MANAGED rows equal the
 *     corpus `expectedRows` (Phase-4 comparison rules) and carry the managed shapes
 *     (10b `instanceof` + value).
 *
 * The entity symbols are hand-authored the way codegen emits them (mirroring
 * `dsl.test.ts`), so the showcase exercises the same classes the generated barrel
 * uses. The official grade stays contract-driven over the generic runtime; this is
 * additive proof the developer surface + shipped adapter produce the corpus rows.
 */

import { execFileSync } from "node:child_process";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../../src/conformance/postgres-provider.js";
import {
  AttributeExpression,
  buildFindOperation,
  Predicate,
  ToManyRelationshipExpression,
} from "../../src/index.js";
import {
  assertManagedShape,
  assertRows,
  assertSameOperation,
  type CaseFixture,
  provisionCase,
} from "./_harness.js";
import { READS } from "./covered.js";

// --- entity symbols (as codegen emits them) ---------------------------------

const attr = (ref: string): AttributeExpression => new AttributeExpression(ref);
const rel = (ref: string): ToManyRelationshipExpression => new ToManyRelationshipExpression(ref);
const all = (): Predicate => new Predicate({ all: {} });

const Order = {
  id: attr("Order.id"),
  name: attr("Order.name"),
  sku: attr("Order.sku"),
  qty: attr("Order.qty"),
  price: attr("Order.price"),
  active: attr("Order.active"),
  items: rel("Order.items"),
  statuses: rel("Order.statuses"),
};
const OrderItem = { sku: attr("OrderItem.sku"), quantity: attr("OrderItem.quantity") };
const OrderItemRel = { order: rel("OrderItem.order"), statuses: rel("OrderItem.statuses") };
const OrderStatus = { code: attr("OrderStatus.code"), orderItem: rel("OrderStatus.orderItem") };
const Order_ = { name: attr("Order.name") };
const Person = { passport: rel("Person.passport") };
const Passport = { number: attr("Passport.number") };
const Grade = { ordinal: attr("Grade.ordinal") };

/** One showcase row: the DSL a developer writes, its root entity, and the case stem. */
interface Row {
  readonly stem: string;
  readonly entity: string;
  readonly build: () => { operation: unknown; predicate?: Predicate; options?: object };
}

/** A plain predicate case (no find-options); `find(predicate)`. */
function p(stem: string, entity: string, predicate: () => Predicate): Row {
  return {
    stem,
    entity,
    build: () => {
      const pred = predicate();
      return { operation: pred.toOperation(), predicate: pred };
    },
  };
}

/** A find-options case (`find(base, options)`); the whole `operation` is asserted. */
function f(stem: string, entity: string, base: () => Predicate, options: object): Row {
  return {
    stem,
    entity,
    build: () => ({ operation: buildFindOperation(base(), options), predicate: base(), options }),
  };
}

const CASES: readonly Row[] = [
  // 00xx — identity / scalars / quoting
  p("0001-find-all", "Order", () => all()),
  p("0002-eq", "Order", () => Order.id.eq(42)),
  p("0003-scalar-types-roundtrip", "ScalarThing", () => all()),
  p("0006-quoted-reserved-identifier", "Grade", () => Grade.ordinal.gt(1)),
  // 02xx — single-entity read algebra
  p("0201-not-eq", "Order", () => Order.qty.notEq(20)),
  p("0202-greater-than", "Order", () => Order.qty.gt(20)),
  p("0203-greater-than-equals", "Order", () => Order.qty.gte(20)),
  p("0204-less-than", "Order", () => Order.qty.lt(15)),
  p("0205-less-than-equals", "Order", () => Order.qty.lte(15)),
  p("0206-between", "Order", () => Order.price.between(20.0, 50.75)),
  p("0207-is-null", "Order", () => Order.sku.isNull()),
  p("0208-is-not-null", "Order", () => Order.sku.isNotNull()),
  p("0209-like", "Order", () => Order.sku.like("A-%")),
  p("0210-not-like", "Order", () => Order.sku.notLike("A-%")),
  p("0211-starts-with", "Order", () => Order.sku.startsWith("A-")),
  p("0212-ends-with", "Order", () => Order.sku.endsWith("00")),
  p("0213-contains-escape", "Order", () => Order.sku.contains("50%")),
  p("0214-like-case-insensitive", "Order", () => Order.name.like("ada", { caseInsensitive: true })),
  p("0215-contains-case-insensitive", "Order", () =>
    Order.name.contains("A", { caseInsensitive: true }),
  ),
  p("0216-in", "Order", () => Order.id.in([1, 2, 42])),
  p("0217-not-in", "Order", () => Order.id.notIn([1, 2, 42])),
  p("0218-and", "Order", () => Order.active.eq(true).and(Order.qty.gt(10))),
  p("0219-or", "Order", () => Order.qty.lt(10).or(Order.qty.gt(25))),
  p("0220-not", "Order", () => Order.active.eq(true).not()),
  p("0221-none", "Order", () => new Predicate({ none: {} })),
  p("0223-group-precedence-ungrouped", "Order", () =>
    Order.qty.gte(25).or(Order.qty.lte(5).and(Order.active.eq(true))),
  ),
  f("0224-order-by-limit", "Order", all, { orderBy: [Order.qty.desc()], limit: 2 }),
  f("0225-order-by-asc-limit", "Order", all, { orderBy: [Order.id.asc()], limit: 3 }),
  p("0227-not-eq-null-excluded", "Order", () => Order.sku.notEq("B-200")),
  p("0228-not-in-null-excluded", "Order", () => Order.sku.notIn(["A-100", "B-200"])),
  p("0229-and-three-operands", "Order", () =>
    Order.active.eq(true).and(Order.qty.gt(5), Order.qty.lt(30)),
  ),
  f("0230-order-by-multi-key", "Order", all, {
    orderBy: [Order.active.desc(), Order.qty.asc()],
    limit: 2,
  }),
  p("0231-starts-with-escape", "Order", () => Order.sku.startsWith("C_")),
  p("0232-ends-with-escape", "Order", () => Order.sku.endsWith("50%")),
  // 03xx flat — navigate / exists reads (non-temporal)
  p("0301-navigate-items-sku", "Order", () => Order.items.navigate(OrderItem.sku.eq("A-100"))),
  p("0302-exists-items", "Order", () => Order.items.exists()),
  p("0303-not-exists-items", "Order", () => Order.items.notExists()),
  p("0304-exists-items-quantity", "Order", () => Order.items.exists(OrderItem.quantity.gte(4))),
  p("0305-navigate-statuses-code", "Order", () =>
    Order.statuses.navigate(OrderStatus.code.eq("SHIPPED")),
  ),
  p("0306-not-exists-items-and-active", "Order", () =>
    Order.items.notExists().and(Order.active.eq(true)),
  ),
  p("0307-navigate-to-one-parent-predicate", "OrderItem", () =>
    OrderItemRel.order.navigate(Order_.name.eq("Ada")),
  ),
  p("0308-exists-multi-hop-items-status", "Order", () =>
    Order.items.exists(OrderItemRel.statuses.exists(OrderStatus.code.eq("PACKED"))),
  ),
  p("0309-exists-to-one", "OrderStatus", () => OrderStatus.orderItem.exists()),
  p("0317-not-exists-multi-hop", "Order", () =>
    Order.items.notExists(OrderItemRel.statuses.exists()),
  ),
  p("0321-navigate-one-to-one", "Person", () =>
    Person.passport.navigate(Passport.number.eq("P-AAA")),
  ),
];

/** True when a Docker daemon is reachable (gates the Testcontainers lane). */
function dockerAvailable(): boolean {
  try {
    execFileSync("docker", ["info"], { stdio: "ignore", timeout: 10_000 });
    return true;
  } catch {
    return false;
  }
}

const HAS_DOCKER = dockerAvailable();

it("the reads showcase covers exactly the READS family", () => {
  expect(CASES.map((c) => c.stem).sort()).toEqual([...READS].sort());
});

group.skipIf(!HAS_DOCKER)("reads showcase (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 600_000;
  let provider: PostgresProvider;

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(CASES)(
    "$stem: a developer read returns the corpus rows as managed objects",
    async (row) => {
      const fixture: CaseFixture = await provisionCase(provider, row.stem);
      const built = row.build();

      // Guard 1 — the DSL builds the corpus's canonical operation (no drift).
      assertSameOperation(built.operation, fixture.loaded);

      // Run the developer read through the shipped adapter.
      const rows = await fixture.px
        .entity(row.entity)
        .find(built.predicate, (built.options ?? {}) as object)
        .toArray();

      // The rows equal the corpus expectedRows (Phase-4 rules) …
      assertRows(rows, fixture.loaded, row.entity, fixture.metamodel);
      // … and carry the managed shapes (10b instanceof + value).
      for (const managed of rows) {
        assertManagedShape(managed, row.entity, fixture.metamodel);
      }
    },
    BOOT_TIMEOUT,
  );
});
