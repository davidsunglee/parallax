/**
 * API Conformance Suite — **temporal reads** family (Phase 10c): processing-axis reads
 * (`find(..., { asOf })`, ranged, full history) and bitemporal reads, plus the two
 * exists-temporal-hop reads, written as a developer would and run against
 * `postgres:17` through the SHIPPED `@parallax/db-postgres` adapter.
 *
 * The temporal read options serialize (business axis OUTSIDE processing) to the
 * corpus's canonical `operation` — the no-drift guard (`assertSameOperation`) — and
 * the returned MANAGED rows equal the corpus `expectedRows` (Phase-4 rules) with the
 * managed shapes (10b). An OMITTED axis is left unwrapped (M7 default-injection at
 * the compiler); an explicit `now` still emits an `asOf … now` wrapper (`m-temporal-read-002`).
 */

import { Temporal } from "@parallax/core";
import type { Operation } from "@parallax/operation";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import {
  AttributeExpression,
  type AxisRefs,
  buildFindOperation,
  Predicate,
  ToManyRelationshipExpression,
} from "../../src/index.js";
import {
  type ApiConformanceProvider,
  assertManagedShape,
  assertRows,
  assertSameOperation,
  provisionCase,
} from "./_harness.js";
import { HAS_DOCKER, readCaseGuarded, selectedProviders } from "./_providers.js";
import { TEMPORAL } from "./covered.js";

const attr = (ref: string): AttributeExpression => new AttributeExpression(ref);
const rel = (ref: string): ToManyRelationshipExpression => new ToManyRelationshipExpression(ref);
const all = (): Predicate => new Predicate({ all: {} });
const at = (iso: string): Temporal.Instant => Temporal.Instant.from(iso);

const Balance = { acctNum: attr("Balance.acctNum") };
const Coverage = { amount: attr("Coverage.amount") };
const Policy = { coverages: rel("Policy.coverages") };

const BALANCE_AXES: AxisRefs = { processing: "Balance.processingDate" };
const LEDGER_AXES: AxisRefs = { processing: "Ledger.processingDate" };
const POSITION_AXES: AxisRefs = {
  processing: "Position.processingDate",
  business: "Position.businessDate",
};
const POLICY_AXES: AxisRefs = {
  processing: "Policy.processingDate",
  business: "Policy.businessDate",
};

/** One temporal suite row: the DSL `find` operation and its root entity. */
interface Row {
  readonly stem: string;
  readonly entity: string;
  readonly build: () => unknown;
}

const CASES: readonly Row[] = [
  // exists-temporal-hop flat reads
  {
    stem: "m-navigate-018-exists-temporal-hop",
    entity: "Policy",
    build: () =>
      buildFindOperation(Policy.coverages.exists(Coverage.amount.gte(600.0)), {
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: POLICY_AXES,
      }),
  },
  {
    stem: "m-navigate-023-exists-temporal-hop-defaulted",
    entity: "Policy",
    build: () => Policy.coverages.exists(Coverage.amount.gte(600.0)).toOperation(),
  },
  // processing-axis reads (05xx)
  {
    stem: "m-temporal-read-001-as-of-now-defaulted",
    entity: "Balance",
    build: () => buildFindOperation(all()),
  },
  {
    stem: "m-temporal-read-002-as-of-now-explicit",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: "now" } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "m-temporal-read-003-as-of-past-instant",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: at("2024-04-01T00:00:00+00:00") } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "m-temporal-read-004-history",
    entity: "Balance",
    build: () =>
      buildFindOperation(new Predicate({ eq: { attr: "Balance.id", value: 1 } }), {
        temporal: { history: ["processing"] },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "m-temporal-read-005-as-of-now-with-predicate",
    entity: "Balance",
    build: () =>
      buildFindOperation(Balance.acctNum.eq("A"), {
        temporal: { asOf: { processing: "now" } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "m-temporal-read-006-as-of-range",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
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
  {
    stem: "m-temporal-read-007-as-of-boundary-exclusive",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: at("2024-06-01T00:00:00+00:00") } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "m-temporal-read-008-as-of-boundary-inclusive",
    entity: "Ledger",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: at("2024-06-01T00:00:00+00:00") } },
        axisRefs: LEDGER_AXES,
      }),
  },
  // bitemporal reads (08xx) — business axis outside processing
  {
    stem: "m-temporal-read-013-bitemporal-as-of-now-both-axes",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: POSITION_AXES,
      }),
  },
  {
    stem: "m-temporal-read-014-bitemporal-business-past-processing-now",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: {
          asOf: { processing: "now", business: at("2024-03-01T00:00:00+00:00") },
        },
        axisRefs: POSITION_AXES,
      }),
  },
  {
    stem: "m-temporal-read-015-bitemporal-both-axes-past",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
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
    stem: "m-temporal-read-016-bitemporal-history",
    entity: "Position",
    build: () =>
      buildFindOperation(new Predicate({ eq: { attr: "Position.id", value: 1 } }), {
        temporal: { history: ["processing", "business"] },
        axisRefs: POSITION_AXES,
      }),
  },
  {
    stem: "m-temporal-read-017-bitemporal-omitted-processing-default",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { business: at("2024-03-01T00:00:00+00:00") } },
        axisRefs: POSITION_AXES,
      }),
  },
];

it("the temporal suite covers exactly the TEMPORAL family", () => {
  expect(CASES.map((c) => c.stem).sort()).toEqual([...TEMPORAL].sort());
});

// Temporal reads are dialect-agnostic (the M7 axis wrapping lowers through the M11 seam),
// so the suite fans out over every database `PARALLAX_DATABASES` selects. `MARIADB_GUARDED_
// READS` (`_providers.ts`) is currently empty — the bitemporal `Position` cases (m-temporal-read-013–m-temporal-read-017)
// used to be guarded off MariaDB (a reserved-word gap), now fixed — but the guard mechanism
// stays wired for a future dialect-specific gap.
group.skipIf(!HAS_DOCKER).each(selectedProviders())("temporal reads suite ($label)", (dbp) => {
  const BOOT_TIMEOUT = 600_000;
  let provider: ApiConformanceProvider;
  const runnable = CASES.filter((c) => !readCaseGuarded(dbp, c.stem));
  const guarded = CASES.filter((c) => readCaseGuarded(dbp, c.stem));

  beforeAll(async () => {
    provider = await dbp.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(runnable)(
    "$stem: a developer temporal read returns the corpus rows as managed objects",
    async (row) => {
      const fixture = await provisionCase(provider, row.stem);
      const operation = row.build() as Operation;

      // Guard 1 — the temporal read options serialize to the corpus operation.
      assertSameOperation(operation, fixture.loaded);

      // Run the SAME operation through the shipped adapter (no re-expression drift).
      const rows = await fixture.px.entity(row.entity).findByOperation(operation).toArray();

      assertRows(rows, fixture.loaded, row.entity, fixture.metamodel);
      for (const managed of rows) {
        assertManagedShape(managed, row.entity, fixture.metamodel);
      }
    },
    BOOT_TIMEOUT,
  );

  if (guarded.length > 0) {
    it.skip.each(
      guarded,
    )("$stem: guarded on MariaDB — reserved-word table not quoted (see _providers.ts)", () => {});
  }
});
