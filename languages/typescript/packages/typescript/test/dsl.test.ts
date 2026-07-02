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
 * temporal axes (`asOf` explicit-now / past instant, `range`, `history`, and
 * both-axis bitemporal ordering).
 */
import { loadCase } from "@parallax/conformance";
import { Temporal } from "@parallax/core";
import { canonicallyEqual } from "@parallax/operation";
import { describe, expect, it } from "vitest";
import {
  AttributeExpression,
  type AxisRefs,
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

/** Axis refs for the temporal models (what the typed `find` resolves). */
const BALANCE_AXES: AxisRefs = { processing: "Balance.processingDate" };
const POSITION_AXES: AxisRefs = {
  processing: "Position.processingDate",
  business: "Position.businessDate",
};
const POLICY_AXES: AxisRefs = {
  processing: "Policy.processingDate",
  business: "Policy.businessDate",
};

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
  { case: "0002-eq", operation: () => Order.id.eq(42).toOperation() },
  { case: "0201-not-eq", operation: () => Order.qty.notEq(20).toOperation() },
  { case: "0202-greater-than", operation: () => Order.qty.gt(20).toOperation() },
  { case: "0203-greater-than-equals", operation: () => Order.qty.gte(20).toOperation() },
  { case: "0204-less-than", operation: () => Order.qty.lt(15).toOperation() },
  { case: "0205-less-than-equals", operation: () => Order.qty.lte(15).toOperation() },
  { case: "0206-between", operation: () => Order.price.between(20.0, 50.75).toOperation() },
  // --- null ---
  { case: "0207-is-null", operation: () => Order.sku.isNull().toOperation() },
  { case: "0208-is-not-null", operation: () => Order.sku.isNotNull().toOperation() },
  // --- string (incl. case-insensitive) ---
  { case: "0210-not-like", operation: () => Order.sku.notLike("A-%").toOperation() },
  { case: "0211-starts-with", operation: () => Order.sku.startsWith("A-").toOperation() },
  { case: "0212-ends-with", operation: () => Order.sku.endsWith("00").toOperation() },
  {
    case: "0214-like-case-insensitive",
    operation: () => Order.name.like("ada", { caseInsensitive: true }).toOperation(),
  },
  // --- membership ---
  { case: "0216-in", operation: () => Order.id.in([1, 2, 42]).toOperation() },
  // --- boolean (left-associative + group precedence) ---
  {
    case: "0218-and",
    operation: () => Order.active.eq(true).and(Order.qty.gt(10)).toOperation(),
  },
  {
    case: "0229-and-three-operands",
    operation: () => Order.active.eq(true).and(Order.qty.gt(5), Order.qty.lt(30)).toOperation(),
  },
  {
    case: "0222-group-precedence-grouped",
    operation: () =>
      Order.qty.gte(25).or(Order.qty.lte(5)).group().and(Order.active.eq(true)).toOperation(),
  },
  {
    case: "0223-group-precedence-ungrouped",
    operation: () =>
      Order.qty
        .gte(25)
        .or(Order.qty.lte(5).and(Order.active.eq(true)))
        .toOperation(),
  },
  // --- directives ---
  {
    case: "0224-order-by-limit",
    operation: () => buildFindOperation(all(), { orderBy: [Order.qty.desc()], limit: 2 }),
  },
  { case: "0226-distinct", operation: () => buildFindOperation(all(), { distinct: true }) },
  // --- navigation ---
  { case: "0303-not-exists-items", operation: () => Order.items.notExists().toOperation() },
  {
    case: "0308-exists-multi-hop-items-status",
    operation: () =>
      Order.items.exists(OrderItem.statuses.exists(OrderStatus.code.eq("PACKED"))).toOperation(),
  },
  // --- deep fetch ---
  {
    case: "0312-deep-fetch-multi-hop",
    operation: () =>
      buildFindOperation(Order.id.in([1, 42]), {
        includes: [new NavigationPath(["Order.items", "OrderItem.statuses"])],
      }),
  },
  // --- temporal reads ---
  { case: "0501-as-of-now-defaulted", operation: () => buildFindOperation(Balance.all()) },
  {
    case: "0502-as-of-now-explicit",
    operation: () =>
      buildFindOperation(Balance.all(), {
        temporal: { asOf: { processing: "now" } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    case: "0503-as-of-past-instant",
    operation: () =>
      buildFindOperation(Balance.all(), {
        temporal: { asOf: { processing: at("2024-04-01T00:00:00+00:00") } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    case: "0504-history",
    operation: () =>
      buildFindOperation(Balance.id.eq(1), {
        temporal: { history: ["processing"] },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    case: "0506-as-of-range",
    operation: () =>
      buildFindOperation(Balance.all(), {
        temporal: {
          range: {
            processing: {
              start: at("2024-06-15T00:00:00+00:00"),
              end: at("2024-07-01T00:00:00+00:00"),
            },
          },
        },
        axisRefs: BALANCE_AXES,
      }),
  },
  // --- bitemporal (both-axis ordering: business outside processing) ---
  {
    case: "0801-bitemporal-as-of-now-both-axes",
    operation: () =>
      buildFindOperation(Position.all(), {
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: POSITION_AXES,
      }),
  },
  {
    case: "0803-bitemporal-both-axes-past",
    operation: () =>
      buildFindOperation(Position.all(), {
        temporal: {
          asOf: {
            processing: at("2024-02-01T00:00:00+00:00"),
            business: at("2024-03-01T00:00:00+00:00"),
          },
        },
        axisRefs: POSITION_AXES,
      }),
  },
  {
    case: "0804-bitemporal-history",
    operation: () =>
      buildFindOperation(Position.id.eq(1), {
        temporal: { history: ["processing", "business"] },
        axisRefs: POSITION_AXES,
      }),
  },
  {
    case: "0805-bitemporal-omitted-processing-default",
    operation: () =>
      buildFindOperation(Position.all(), {
        temporal: { asOf: { business: at("2024-03-01T00:00:00+00:00") } },
        axisRefs: POSITION_AXES,
      }),
  },
  // --- temporal deep fetch (both axes latest, propagated per hop) ---
  {
    case: "0324-deepfetch-temporal-both-latest",
    operation: () =>
      buildFindOperation(Policy.all(), {
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: POLICY_AXES,
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
      expect(
        canonicallyEqual(built, loaded.raw.operation),
        `DSL for ${row.case} did not canonicalize to the corpus operation:\n` +
          `  dsl:    ${JSON.stringify(built)}\n` +
          `  corpus: ${JSON.stringify(loaded.raw.operation)}`,
      ).toBe(true);
    });
  }

  it("empty membership normalizes: in([]) → none, notIn([]) → all (spec §2.5)", () => {
    expect(new AttributeExpression("Order.id").in([]).toOperation()).toEqual({ none: {} });
    expect(new AttributeExpression("Order.id").notIn([]).toOperation()).toEqual({ all: {} });
  });
});
