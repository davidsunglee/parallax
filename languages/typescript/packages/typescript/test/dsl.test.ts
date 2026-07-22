/**
 * DSL → canonical operation fidelity (Phase 9 automated verification).
 *
 * The fluent DSL MUST serialize to the IDENTICAL canonical `Operation` wire form
 * the compiler already consumes, so conformance is unaffected (design Q1 Option
 * B). This suite builds each representative case's operation with the DSL as an
 * application developer would write it, then asserts it canonicalizes to the
 * corpus case's authored `operation` — the single source of truth. If a DSL
 * spelling stops matching its canonical case, the build fails here.
 *
 * Coverage spans every DSL-expressible family: identity, comparison, null,
 * string (incl. case-insensitive), membership + empty-normalization, boolean
 * (left-associative + `group` precedence), directives (order-by / limit /
 * distinct), navigation (`exists` / `notExists`, multi-hop), deep fetch, and the
 * temporal axes (`asOf` explicit-Latest / past instant, `range`, `history`, and
 * both-axis bitemporal ordering).
 */
import { loadCase } from "@parallax/conformance";
import { Temporal } from "@parallax/core";
import { canonicallyEqual } from "@parallax/operation";
import { describe, expect, it } from "vitest";
import {
  AttributeExpression,
  buildFindOperation,
  NavigationPath,
  Predicate,
  ToManyRelationshipExpression,
} from "../src/index.js";

// --- entity symbols, hand-authored the way codegen would emit them ----------

/** Build an attribute expression for a `Class.attr` ref. */
function attr(ref: string): AttributeExpression {
  return new AttributeExpression(ref);
}

/** Build a to-many relationship expression for a `Class.rel` ref. */
function rel(ref: string): ToManyRelationshipExpression {
  return new ToManyRelationshipExpression(ref);
}

const Order = {
  id: attr("Order.id"),
  qty: attr("Order.qty"),
  price: attr("Order.price"),
  active: attr("Order.active"),
  name: attr("Order.name"),
  sku: attr("Order.sku"),
  items: rel("Order.items"),
};

/**
 * The unfiltered identity predicate, spelled as codegen emits `Entity.all()`
 * (`find()` shorthand, spec §2.3). Built through the real `Predicate` so the
 * fidelity check exercises the same class the generated barrel uses.
 */
function all(): Predicate {
  return new Predicate({ all: {} });
}

const OrderItem = { statuses: rel("OrderItem.statuses") };
const OrderStatus = { code: attr("OrderStatus.code") };
const Balance = { id: attr("Balance.id"), all };
const Position = { id: attr("Position.id"), all };
const Policy = { coverages: new NavigationPath(["Policy.coverages"]), all };

/** An instant literal from an ISO string (the corpus authors `+00:00` offsets). */
function at(iso: string): Temporal.Instant {
  return Temporal.Instant.from(iso);
}

/** One row of the fidelity matrix: a case path and the DSL that must match it. */
interface Row {
  readonly case: string;
  readonly operation: () => unknown;
}

const CASES: readonly Row[] = [
  // --- identity + comparison ---
  { case: "m-op-algebra-002-eq", operation: () => Order.id.eq(42).toOperation() },
  { case: "m-op-algebra-003-not-eq", operation: () => Order.qty.notEq(20).toOperation() },
  { case: "m-op-algebra-004-greater-than", operation: () => Order.qty.gt(20).toOperation() },
  {
    case: "m-op-algebra-005-greater-than-equals",
    operation: () => Order.qty.gte(20).toOperation(),
  },
  { case: "m-op-algebra-006-less-than", operation: () => Order.qty.lt(15).toOperation() },
  { case: "m-op-algebra-007-less-than-equals", operation: () => Order.qty.lte(15).toOperation() },
  {
    case: "m-op-algebra-008-between",
    operation: () => Order.price.between(20.0, 50.75).toOperation(),
  },
  // --- null ---
  { case: "m-op-algebra-009-is-null", operation: () => Order.sku.isNull().toOperation() },
  { case: "m-op-algebra-010-is-not-null", operation: () => Order.sku.isNotNull().toOperation() },
  // --- string (incl. case-insensitive) ---
  { case: "m-op-algebra-012-not-like", operation: () => Order.sku.notLike("A-%").toOperation() },
  {
    case: "m-op-algebra-013-starts-with",
    operation: () => Order.sku.startsWith("A-").toOperation(),
  },
  { case: "m-op-algebra-014-ends-with", operation: () => Order.sku.endsWith("00").toOperation() },
  {
    case: "m-op-algebra-016-like-case-insensitive",
    operation: () => Order.name.like("ada", { caseInsensitive: true }).toOperation(),
  },
  // --- membership ---
  { case: "m-op-algebra-018-in", operation: () => Order.id.in([1, 2, 42]).toOperation() },
  // --- boolean (left-associative + group precedence) ---
  {
    case: "m-op-algebra-020-and",
    operation: () => Order.active.eq(true).and(Order.qty.gt(10)).toOperation(),
  },
  {
    case: "m-op-algebra-031-and-three-operands",
    operation: () => Order.active.eq(true).and(Order.qty.gt(5), Order.qty.lt(30)).toOperation(),
  },
  {
    case: "m-op-algebra-024-group-precedence-grouped",
    operation: () =>
      Order.qty.gte(25).or(Order.qty.lte(5)).group().and(Order.active.eq(true)).toOperation(),
  },
  {
    case: "m-op-algebra-025-group-precedence-ungrouped",
    operation: () =>
      Order.qty
        .gte(25)
        .or(Order.qty.lte(5).and(Order.active.eq(true)))
        .toOperation(),
  },
  // --- directives ---
  {
    case: "m-op-algebra-026-order-by-limit",
    operation: () => buildFindOperation(all(), { orderBy: [Order.qty.desc()], limit: 2 }),
  },
  {
    // `distinct` directive fidelity. The old op-algebra witness `m-op-algebra-028`
    // (`distinct` on a projected subset) was removed with the base read-projection
    // rule; the surviving `distinct { operand: all }` witness is the read-lock
    // projection read, whose operation is identical.
    case: "m-read-lock-003-locking-txn-projection-omits-lock",
    operation: () => buildFindOperation(all(), { distinct: true }),
  },
  // --- navigation ---
  {
    case: "m-navigate-003-not-exists-items",
    operation: () => Order.items.notExists().toOperation(),
  },
  {
    case: "m-navigate-008-exists-multi-hop-items-status",
    operation: () =>
      Order.items.exists(OrderItem.statuses.exists(OrderStatus.code.eq("PACKED"))).toOperation(),
  },
  // --- deep fetch ---
  {
    case: "m-deep-fetch-003-multi-hop",
    operation: () =>
      buildFindOperation(Order.id.in([1, 42]), {
        includes: [new NavigationPath(["Order.items", "OrderItem.statuses"])],
      }),
  },
  // --- temporal reads ---
  {
    case: "m-temporal-read-001-as-of-latest-defaulted",
    operation: () => buildFindOperation(Balance.all()),
  },
  {
    case: "m-temporal-read-002-as-of-latest-explicit",
    operation: () =>
      buildFindOperation(Balance.all(), {
        temporal: { asOf: { transactionTime: "latest" } },
      }),
  },
  {
    case: "m-temporal-read-003-as-of-past-instant",
    operation: () =>
      buildFindOperation(Balance.all(), {
        temporal: { asOf: { transactionTime: at("2024-04-01T00:00:00+00:00") } },
      }),
  },
  {
    case: "m-temporal-read-004-history",
    operation: () =>
      buildFindOperation(Balance.id.eq(1), {
        temporal: { history: ["transactionTime"] },
      }),
  },
  {
    case: "m-temporal-read-006-as-of-range",
    operation: () =>
      buildFindOperation(Balance.all(), {
        temporal: {
          range: {
            transactionTime: {
              start: at("2024-06-15T00:00:00+00:00"),
              end: at("2024-07-01T00:00:00+00:00"),
            },
          },
        },
      }),
  },
  // --- bitemporal (both-axis ordering: business outside processing) ---
  {
    case: "m-temporal-read-013-bitemporal-as-of-latest-both-dimensions",
    operation: () =>
      buildFindOperation(Position.all(), {
        temporal: { asOf: { transactionTime: "latest", validTime: "latest" } },
      }),
  },
  {
    case: "m-temporal-read-015-bitemporal-both-axes-past",
    operation: () =>
      buildFindOperation(Position.all(), {
        temporal: {
          asOf: {
            transactionTime: at("2024-02-01T00:00:00+00:00"),
            validTime: at("2024-03-01T00:00:00+00:00"),
          },
        },
      }),
  },
  {
    case: "m-temporal-read-016-bitemporal-history",
    operation: () =>
      buildFindOperation(Position.id.eq(1), {
        temporal: { history: ["transactionTime", "validTime"] },
      }),
  },
  {
    case: "m-temporal-read-017-bitemporal-omitted-transaction-time-default",
    operation: () =>
      buildFindOperation(Position.all(), {
        temporal: { asOf: { validTime: at("2024-03-01T00:00:00+00:00") } },
      }),
  },
  // --- temporal deep fetch (both axes latest, propagated per hop) ---
  {
    case: "m-navigate-012-deepfetch-temporal-both-latest",
    operation: () =>
      buildFindOperation(Policy.all(), {
        temporal: { asOf: { transactionTime: "latest", validTime: "latest" } },
        includes: [Policy.coverages],
      }),
  },
];

/** Resolve a case stem to its repo-relative path. */
function casePath(stem: string): string {
  return `core/compatibility/cases/${stem}.yaml`;
}

describe("DSL → canonical operation fidelity", () => {
  for (const row of CASES) {
    it(`${row.case}: DSL serializes to the corpus operation`, () => {
      const loaded = loadCase(casePath(row.case));
      const built = row.operation();
      const corpus = loaded.raw.when?.operation;
      expect(
        canonicallyEqual(built, corpus),
        `DSL for ${row.case} did not canonicalize to the corpus operation:\n` +
          `  dsl:    ${JSON.stringify(built)}\n` +
          `  corpus: ${JSON.stringify(corpus)}`,
      ).toBe(true);
    });
  }

  it("empty membership normalizes: in([]) → none, notIn([]) → all (spec §2.5)", () => {
    expect(new AttributeExpression("Order.id").in([]).toOperation()).toEqual({ none: {} });
    expect(new AttributeExpression("Order.id").notIn([]).toOperation()).toEqual({ all: {} });
  });
});
