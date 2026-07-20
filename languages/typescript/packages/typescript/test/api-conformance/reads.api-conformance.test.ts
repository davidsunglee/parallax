/**
 * API Conformance Suite — **reads** family (Phase 10c): non-temporal single-entity
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
 * `dsl.test.ts`), so the suite exercises the same classes the generated barrel
 * uses. The official grade stays contract-driven over the generic runtime; this is
 * additive proof the developer surface + shipped adapter produce the corpus rows.
 */

import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import {
  AttributeExpression,
  buildFindOperation,
  Predicate,
  ToManyRelationshipExpression,
} from "../../src/index.js";
import {
  type ApiConformanceProvider,
  assertManagedShape,
  assertRows,
  assertSameOperation,
  type CaseFixture,
  provisionCase,
} from "./_harness.js";
import { caseGuarded, guardedCases, HAS_DOCKER, selectedProviders } from "./_providers.js";
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

/** One suite row: the DSL a developer writes, its root entity, and the case stem. */
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
  p("m-op-algebra-001-find-all", "Order", () => all()),
  p("m-op-algebra-002-eq", "Order", () => Order.id.eq(42)),
  p("m-core-001-scalar-types-roundtrip", "ScalarThing", () => all()),
  p("m-descriptor-001-quoted-reserved-identifier", "Grade", () => Grade.ordinal.gt(1)),
  // 02xx — single-entity read algebra
  p("m-op-algebra-003-not-eq", "Order", () => Order.qty.notEq(20)),
  p("m-op-algebra-004-greater-than", "Order", () => Order.qty.gt(20)),
  p("m-op-algebra-005-greater-than-equals", "Order", () => Order.qty.gte(20)),
  p("m-op-algebra-006-less-than", "Order", () => Order.qty.lt(15)),
  p("m-op-algebra-007-less-than-equals", "Order", () => Order.qty.lte(15)),
  p("m-op-algebra-008-between", "Order", () => Order.price.between(20.0, 50.75)),
  p("m-op-algebra-009-is-null", "Order", () => Order.sku.isNull()),
  p("m-op-algebra-010-is-not-null", "Order", () => Order.sku.isNotNull()),
  p("m-op-algebra-011-like", "Order", () => Order.sku.like("A-%")),
  p("m-op-algebra-012-not-like", "Order", () => Order.sku.notLike("A-%")),
  p("m-op-algebra-013-starts-with", "Order", () => Order.sku.startsWith("A-")),
  p("m-op-algebra-014-ends-with", "Order", () => Order.sku.endsWith("00")),
  p("m-op-algebra-015-contains-escape", "Order", () => Order.sku.contains("50%")),
  p("m-op-algebra-016-like-case-insensitive", "Order", () =>
    Order.name.like("ada", { caseInsensitive: true }),
  ),
  p("m-op-algebra-017-contains-case-insensitive", "Order", () =>
    Order.name.contains("A", { caseInsensitive: true }),
  ),
  p("m-op-algebra-018-in", "Order", () => Order.id.in([1, 2, 42])),
  p("m-op-algebra-019-not-in", "Order", () => Order.id.notIn([1, 2, 42])),
  p("m-op-algebra-020-and", "Order", () => Order.active.eq(true).and(Order.qty.gt(10))),
  p("m-op-algebra-021-or", "Order", () => Order.qty.lt(10).or(Order.qty.gt(25))),
  p("m-op-algebra-022-not", "Order", () => Order.active.eq(true).not()),
  p("m-op-algebra-023-none", "Order", () => new Predicate({ none: {} })),
  p("m-op-algebra-025-group-precedence-ungrouped", "Order", () =>
    Order.qty.gte(25).or(Order.qty.lte(5).and(Order.active.eq(true))),
  ),
  f("m-op-algebra-026-order-by-limit", "Order", all, { orderBy: [Order.qty.desc()], limit: 2 }),
  f("m-op-algebra-027-order-by-asc-limit", "Order", all, { orderBy: [Order.id.asc()], limit: 3 }),
  p("m-op-algebra-029-not-eq-null-excluded", "Order", () => Order.sku.notEq("B-200")),
  p("m-op-algebra-030-not-in-null-excluded", "Order", () => Order.sku.notIn(["A-100", "B-200"])),
  p("m-op-algebra-031-and-three-operands", "Order", () =>
    Order.active.eq(true).and(Order.qty.gt(5), Order.qty.lt(30)),
  ),
  f("m-op-algebra-032-order-by-multi-key", "Order", all, {
    orderBy: [Order.active.desc(), Order.qty.asc()],
    limit: 2,
  }),
  p("m-op-algebra-033-starts-with-escape", "Order", () => Order.sku.startsWith("C_")),
  p("m-op-algebra-034-ends-with-escape", "Order", () => Order.sku.endsWith("50%")),
  // 03xx flat — navigate / exists reads (non-temporal)
  p("m-navigate-001-items-sku", "Order", () => Order.items.navigate(OrderItem.sku.eq("A-100"))),
  p("m-navigate-002-exists-items", "Order", () => Order.items.exists()),
  p("m-navigate-003-not-exists-items", "Order", () => Order.items.notExists()),
  p("m-navigate-004-exists-items-quantity", "Order", () =>
    Order.items.exists(OrderItem.quantity.gte(4)),
  ),
  p("m-navigate-005-statuses-code", "Order", () =>
    Order.statuses.navigate(OrderStatus.code.eq("SHIPPED")),
  ),
  p("m-navigate-006-not-exists-items-and-active", "Order", () =>
    Order.items.notExists().and(Order.active.eq(true)),
  ),
  p("m-navigate-007-to-one-parent-predicate", "OrderItem", () =>
    OrderItemRel.order.navigate(Order_.name.eq("Ada")),
  ),
  p("m-navigate-008-exists-multi-hop-items-status", "Order", () =>
    Order.items.exists(OrderItemRel.statuses.exists(OrderStatus.code.eq("PACKED"))),
  ),
  p("m-navigate-009-exists-to-one", "OrderStatus", () => OrderStatus.orderItem.exists()),
  p("m-navigate-010-not-exists-multi-hop", "Order", () =>
    Order.items.notExists(OrderItemRel.statuses.exists()),
  ),
  p("m-navigate-011-one-to-one", "Person", () =>
    Person.passport.navigate(Passport.number.eq("P-AAA")),
  ),
];

it("the reads suite covers exactly the READS family", () => {
  expect(CASES.map((c) => c.stem).sort()).toEqual([...READS].sort());
});

// Reads are dialect-agnostic (the m-sql compiler is behind the m-dialect seam), so the suite fans
// out over every database `PARALLAX_DATABASES` selects (default Postgres). `MARIADB_GUARDED_
// CASES` (`_providers.ts`) holds no READS-family stem — the raw `bytes` read case (`m-core-001`)
// used to be guarded off MariaDB, now fixed — so this suite runs the same case count on every
// selected database; the guard stays wired for a future gap, and reports each one WITH its reason.
group.skipIf(!HAS_DOCKER).each(selectedProviders())("reads suite ($label)", (dbp) => {
  const BOOT_TIMEOUT = 600_000;
  let provider: ApiConformanceProvider;
  const runnable = CASES.filter((c) => !caseGuarded(dbp, c.stem));
  const guarded = guardedCases(
    dbp,
    CASES.map((c) => c.stem),
  );

  beforeAll(async () => {
    provider = await dbp.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(runnable)(
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

  // An explicit loop, NOT `it.skip.each` with a `$reason` placeholder: vitest
  // truncates each `$`-interpolated value at ~35 characters, which would clip the
  // reason mid-sentence. A title built here is printed in full. (Empty today, so
  // nothing renders — but the mechanism has to be right before an entry lands.)
  for (const { stem, reason } of guarded) {
    it.skip(`${stem}: guarded on MariaDB — ${reason}`, () => {});
  }
});
