/**
 * Developer showcase — **temporal reads** family (Phase 10c): processing-axis reads
 * (`find(..., { asOf })`, ranged, full history) and bitemporal reads, plus the two
 * exists-temporal-hop reads, written as a developer would and run against
 * `postgres:17` through the SHIPPED `@parallax/db-postgres` adapter.
 *
 * The temporal read options serialize (business axis OUTSIDE processing) to the
 * corpus's canonical `operation` — the no-drift guard (`assertSameOperation`) — and
 * the returned MANAGED rows equal the corpus `expectedRows` (Phase-4 rules) with the
 * managed shapes (10b). An OMITTED axis is left unwrapped (M7 default-injection at
 * the compiler); an explicit `now` still emits an `asOf … now` wrapper (`0502`).
 */

import { execFileSync } from "node:child_process";
import { Temporal } from "@parallax/core";
import type { Operation } from "@parallax/operation";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../../src/conformance/postgres-provider.js";
import {
  AttributeExpression,
  type AxisRefs,
  buildFindOperation,
  Predicate,
  ToManyRelationshipExpression,
} from "../../src/index.js";
import { assertManagedShape, assertRows, assertSameOperation, provisionCase } from "./_harness.js";
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

/** One temporal showcase row: the DSL `find` operation and its root entity. */
interface Row {
  readonly stem: string;
  readonly entity: string;
  readonly build: () => unknown;
}

const CASES: readonly Row[] = [
  // exists-temporal-hop flat reads
  {
    stem: "0330-exists-temporal-hop",
    entity: "Policy",
    build: () =>
      buildFindOperation(Policy.coverages.exists(Coverage.amount.gte(600.0)), {
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: POLICY_AXES,
      }),
  },
  {
    stem: "0335-exists-temporal-hop-defaulted",
    entity: "Policy",
    build: () => Policy.coverages.exists(Coverage.amount.gte(600.0)).toOperation(),
  },
  // processing-axis reads (05xx)
  { stem: "0501-as-of-now-defaulted", entity: "Balance", build: () => buildFindOperation(all()) },
  {
    stem: "0502-as-of-now-explicit",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: "now" } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "0503-as-of-past-instant",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: at("2024-04-01T00:00:00+00:00") } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "0504-history",
    entity: "Balance",
    build: () =>
      buildFindOperation(new Predicate({ eq: { attr: "Balance.id", value: 1 } }), {
        temporal: { history: ["processing"] },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "0505-as-of-now-with-predicate",
    entity: "Balance",
    build: () =>
      buildFindOperation(Balance.acctNum.eq("A"), {
        temporal: { asOf: { processing: "now" } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "0506-as-of-range",
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
    stem: "0507-as-of-boundary-exclusive",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: at("2024-06-01T00:00:00+00:00") } },
        axisRefs: BALANCE_AXES,
      }),
  },
  {
    stem: "0508-as-of-boundary-inclusive",
    entity: "Ledger",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: at("2024-06-01T00:00:00+00:00") } },
        axisRefs: LEDGER_AXES,
      }),
  },
  // bitemporal reads (08xx) — business axis outside processing
  {
    stem: "0801-bitemporal-as-of-now-both-axes",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { processing: "now", business: "now" } },
        axisRefs: POSITION_AXES,
      }),
  },
  {
    stem: "0802-bitemporal-business-past-processing-now",
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
    stem: "0803-bitemporal-both-axes-past",
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
    stem: "0804-bitemporal-history",
    entity: "Position",
    build: () =>
      buildFindOperation(new Predicate({ eq: { attr: "Position.id", value: 1 } }), {
        temporal: { history: ["processing", "business"] },
        axisRefs: POSITION_AXES,
      }),
  },
  {
    stem: "0805-bitemporal-omitted-processing-default",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { business: at("2024-03-01T00:00:00+00:00") } },
        axisRefs: POSITION_AXES,
      }),
  },
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

it("the temporal showcase covers exactly the TEMPORAL family", () => {
  expect(CASES.map((c) => c.stem).sort()).toEqual([...TEMPORAL].sort());
});

group.skipIf(!HAS_DOCKER)("temporal reads showcase (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 600_000;
  let provider: PostgresProvider;

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(CASES)(
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
});
