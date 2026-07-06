/**
 * API Conformance Suite — **deep-fetch** family (Phase 10c): eager relationship
 * loading (`find(..., { includes })`), written as a developer would and run against
 * `postgres:17` through the SHIPPED `@parallax/db-postgres` adapter.
 *
 * Each case:
 *  1. `assertSameOperation` — the include paths (+ temporal axes) serialize to the
 *     corpus's canonical `deepFetch` operation.
 *  2. runs `px.<entity>.findGraphByOperation(...)` and asserts the assembled graph
 *     matches the corpus `expectedGraph` (projected down to the witness columns —
 *     the developer returns full managed objects) AND the round-trip count equals
 *     `1 + L` (never N+1). Root rows carry the managed shapes (10b).
 *
 * A developer's deep fetch returns FULL managed objects; the corpus `expectedGraph`
 * is a projection witness, so the harness compares only the columns the witness
 * names. Temporal deep fetch propagates the root's as-of pins per hop identically
 * to the graded runtime (same m-sql compiler + m-navigate strategy).
 */

import { Temporal } from "@parallax/core";
import type { Operation } from "@parallax/operation";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import {
  AttributeExpression,
  type AxisRefs,
  buildFindOperation,
  NavigationPath,
  Predicate,
} from "../../src/index.js";
import {
  type ApiConformanceProvider,
  assertGraph,
  assertManagedShape,
  assertSameOperation,
  provisionCase,
} from "./_harness.js";
import { HAS_DOCKER, selectedProviders } from "./_providers.js";
import { DEEP_FETCH } from "./covered.js";

const all = (): Predicate => new Predicate({ all: {} });
const eq = (ref: string, value: string | number | boolean): Predicate =>
  new Predicate({ eq: { attr: ref, value } });
const inList = (ref: string, values: readonly (string | number)[]): Predicate =>
  new Predicate({ in: { attr: ref, values } });
const path = (...refs: string[]): NavigationPath => new NavigationPath(refs);
const at = (iso: string): Temporal.Instant => Temporal.Instant.from(iso);

const POLICY_AXES: AxisRefs = {
  processing: "Policy.processingDate",
  business: "Policy.businessDate",
};
const COVERAGE_AXES: AxisRefs = {
  processing: "Coverage.processingDate",
  business: "Coverage.businessDate",
};
const INVOICE_AXES: AxisRefs = { processing: "Invoice.processingDate" };
const LEASE_AXES: AxisRefs = { processing: "Lease.processingDate" };

/** One deep-fetch suite row: the DSL that builds the corpus operation + its root. */
interface Row {
  readonly stem: string;
  readonly entity: string;
  readonly build: () => Operation;
}

const CASES: readonly Row[] = [
  // non-temporal deep fetch (03xx graph)
  {
    stem: "m-deep-fetch-001-to-one",
    entity: "OrderItem",
    build: () => buildFindOperation(all(), { includes: [path("OrderItem.order")] }),
  },
  {
    stem: "m-deep-fetch-002-to-many",
    entity: "Order",
    build: () => buildFindOperation(all(), { includes: [path("Order.items")] }),
  },
  {
    stem: "m-deep-fetch-003-multi-hop",
    entity: "Order",
    build: () =>
      buildFindOperation(inList("Order.id", [1, 42]), {
        includes: [path("Order.items", "OrderItem.statuses")],
      }),
  },
  {
    stem: "m-deep-fetch-004-two-paths",
    entity: "Order",
    build: () =>
      buildFindOperation(all(), { includes: [path("Order.items"), path("Order.statuses")] }),
  },
  {
    stem: "m-deep-fetch-005-null-to-one",
    entity: "OrderStatus",
    build: () => buildFindOperation(all(), { includes: [path("OrderStatus.orderItem")] }),
  },
  {
    stem: "m-deep-fetch-006-empty-root",
    entity: "Order",
    build: () =>
      buildFindOperation(eq("Order.id", 999), {
        includes: [path("Order.items", "OrderItem.statuses")],
      }),
  },
  {
    stem: "m-deep-fetch-007-shared-prefix",
    entity: "Order",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Order.items"), path("Order.items", "OrderItem.statuses")],
      }),
  },
  {
    stem: "m-deep-fetch-008-empty-intermediate",
    entity: "Order",
    build: () =>
      buildFindOperation(eq("Order.id", 4), {
        includes: [path("Order.items", "OrderItem.statuses")],
      }),
  },
  {
    stem: "m-deep-fetch-009-ordered-items-desc",
    entity: "Order",
    build: () => buildFindOperation(eq("Order.id", 1), { includes: [path("Order.items")] }),
  },
  {
    stem: "m-deep-fetch-010-one-to-one",
    entity: "Person",
    build: () => buildFindOperation(all(), { includes: [path("Person.passport")] }),
  },
  {
    stem: "m-deep-fetch-011-ordered-tags-multikey",
    entity: "Order",
    build: () => buildFindOperation(eq("Order.id", 1), { includes: [path("Order.tags")] }),
  },
  {
    stem: "m-deep-fetch-012-ordered-nullable-nulls-last",
    entity: "Order",
    build: () =>
      buildFindOperation(inList("Order.id", [1, 42]), {
        includes: [path("Order.itemsByShipDate")],
      }),
  },
  // temporal deep fetch (03xx graph, m-temporal-read)
  {
    stem: "m-navigate-012-deepfetch-temporal-both-latest",
    entity: "Policy",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Policy.coverages")],
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: POLICY_AXES,
      }),
  },
  {
    stem: "m-navigate-013-deepfetch-temporal-business-past",
    entity: "Policy",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Policy.coverages")],
        temporal: { asOf: { processing: "now", business: at("2024-03-01T00:00:00+00:00") } },
        axisRefs: POLICY_AXES,
      }),
  },
  {
    stem: "m-navigate-014-deepfetch-temporal-processing-past",
    entity: "Policy",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Policy.coverages")],
        temporal: { asOf: { processing: at("2024-02-01T00:00:00+00:00"), business: "now" } },
        axisRefs: POLICY_AXES,
      }),
  },
  {
    stem: "m-navigate-015-deepfetch-temporal-both-past",
    entity: "Policy",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Policy.coverages")],
        temporal: {
          asOf: {
            processing: at("2024-02-01T00:00:00+00:00"),
            business: at("2024-03-01T00:00:00+00:00"),
          },
        },
        axisRefs: POLICY_AXES,
      }),
  },
  {
    stem: "m-navigate-016-deepfetch-temporal-multihop",
    entity: "Policy",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Policy.coverages", "Coverage.claims")],
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: POLICY_AXES,
      }),
  },
  {
    stem: "m-navigate-017-deepfetch-temporal-to-one",
    entity: "Coverage",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Coverage.policy")],
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: COVERAGE_AXES,
      }),
  },
  {
    stem: "m-navigate-019-deepfetch-processing-only-latest",
    entity: "Invoice",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Invoice.lines")],
        temporal: { asOf: { processing: "now" } },
        axisRefs: INVOICE_AXES,
      }),
  },
  {
    stem: "m-navigate-020-deepfetch-processing-only-instant",
    entity: "Invoice",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Invoice.lines")],
        temporal: { asOf: { processing: at("2024-02-01T00:00:00+00:00") } },
        axisRefs: INVOICE_AXES,
      }),
  },
  {
    stem: "m-navigate-021-deepfetch-nontemporal-to-temporal",
    entity: "Tenant",
    build: () => buildFindOperation(all(), { includes: [path("Tenant.leases")] }),
  },
  {
    stem: "m-navigate-022-deepfetch-temporal-to-nontemporal",
    entity: "Lease",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Lease.notes")],
        temporal: { asOf: { processing: "now" } },
        axisRefs: LEASE_AXES,
      }),
  },
  {
    stem: "m-navigate-024-deepfetch-temporal-ordered-root",
    entity: "Policy",
    build: () =>
      buildFindOperation(all(), {
        includes: [path("Policy.coverages")],
        orderBy: [new AttributeExpression("Policy.id").asc()],
        limit: 1,
        temporal: { asOf: { processing: "now", business: at("2024-03-01T00:00:00+00:00") } },
        axisRefs: POLICY_AXES,
      }),
  },
];

it("the deep-fetch suite covers exactly the DEEP_FETCH family", () => {
  expect(CASES.map((c) => c.stem).sort()).toEqual([...DEEP_FETCH].sort());
});

// Deep fetch is read-only (the dialect-aware m-sql compiler + m-deep-fetch assembly), so the suite
// fans out over every database `PARALLAX_DATABASES` selects (default Postgres).
group.skipIf(!HAS_DOCKER).each(selectedProviders())("deep-fetch suite ($label)", (dbp) => {
  const BOOT_TIMEOUT = 600_000;
  let provider: ApiConformanceProvider;

  beforeAll(async () => {
    provider = await dbp.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(CASES)(
    "$stem: a developer deep fetch assembles the corpus graph in 1+L round trips",
    async (row) => {
      const fixture = await provisionCase(provider, row.stem);
      const operation = row.build();

      assertSameOperation(operation, fixture.loaded);

      const { rows, roundTrips } = await fixture.px
        .entity(row.entity)
        .findGraphByOperation(operation);

      assertGraph(rows, fixture.loaded, row.entity, fixture.metamodel);
      // `1 + L` round trips (never N+1): the declared count the corpus authors.
      const declared = fixture.loaded.raw.roundTrips as number | undefined;
      if (declared !== undefined) {
        expect(roundTrips, `${row.stem}: roundTrips`).toBe(declared);
      }
      for (const managed of rows) {
        assertManagedShape(managed, row.entity, fixture.metamodel);
      }
    },
    BOOT_TIMEOUT,
  );
});
