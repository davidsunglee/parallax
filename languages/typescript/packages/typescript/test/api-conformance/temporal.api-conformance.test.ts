/**
 * API Conformance Suite — **temporal reads** family (Phase 10c): Transaction-Time reads
 * (`find(..., { asOf })`, ranged, full history) and bitemporal reads, plus the two
 * exists-temporal-hop reads, written as a developer would and run against
 * `postgres:17` through the SHIPPED `@parallax/db-postgres` adapter.
 *
 * The temporal read options serialize (Valid-Time dimension outside Transaction Time) to the
 * corpus's canonical `operation` — the no-drift guard (`assertSameOperation`) — and
 * the returned MANAGED rows equal the corpus `expectedRows` (Phase-4 rules) with the
 * managed shapes (10b). An OMITTED axis is left unwrapped (m-temporal-read default-injection at
 * the compiler); explicit Latest emits an `asOf … latest` wrapper (`m-temporal-read-002`).
 */

import { Temporal } from "@parallax/core";
import type { Operation } from "@parallax/operation";
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
  provisionCase,
} from "./_harness.js";
import { caseGuarded, guardedCases, HAS_DOCKER, selectedProviders } from "./_providers.js";
import { TEMPORAL } from "./covered.js";

const attr = (ref: string): AttributeExpression => new AttributeExpression(ref);
const rel = (ref: string): ToManyRelationshipExpression => new ToManyRelationshipExpression(ref);
const all = (): Predicate => new Predicate({ all: {} });
const at = (iso: string): Temporal.Instant => Temporal.Instant.from(iso);

const Balance = { acctNum: attr("Balance.acctNum") };
const Coverage = { amount: attr("Coverage.amount") };
const Policy = { coverages: rel("Policy.coverages") };

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
        temporal: { asOf: { transactionTime: "latest", validTime: "latest" } },
      }),
  },
  {
    stem: "m-navigate-023-exists-temporal-hop-defaulted",
    entity: "Policy",
    build: () => Policy.coverages.exists(Coverage.amount.gte(600.0)).toOperation(),
  },
  // Transaction-Time reads (05xx)
  {
    stem: "m-temporal-read-001-as-of-latest-defaulted",
    entity: "Balance",
    build: () => buildFindOperation(all()),
  },
  {
    stem: "m-temporal-read-002-as-of-latest-explicit",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { transactionTime: "latest" } },
      }),
  },
  {
    stem: "m-temporal-read-003-as-of-past-instant",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { transactionTime: at("2024-04-01T00:00:00+00:00") } },
      }),
  },
  {
    stem: "m-temporal-read-004-history",
    entity: "Balance",
    build: () =>
      buildFindOperation(new Predicate({ eq: { attr: "Balance.id", value: 1 } }), {
        temporal: { history: ["transactionTime"] },
      }),
  },
  {
    stem: "m-temporal-read-005-as-of-latest-with-predicate",
    entity: "Balance",
    build: () =>
      buildFindOperation(Balance.acctNum.eq("A"), {
        temporal: { asOf: { transactionTime: "latest" } },
      }),
  },
  {
    stem: "m-temporal-read-006-as-of-range",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
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
  {
    stem: "m-temporal-read-007-as-of-boundary-exclusive",
    entity: "Balance",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { transactionTime: at("2024-06-01T00:00:00+00:00") } },
      }),
  },
  {
    stem: "m-temporal-read-008-as-of-boundary-inclusive",
    entity: "Ledger",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { transactionTime: at("2024-06-01T00:00:00+00:00") } },
      }),
  },
  // bitemporal reads (08xx) — Valid-Time dimension outside processing
  {
    stem: "m-temporal-read-013-bitemporal-as-of-latest-both-dimensions",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { transactionTime: "latest", validTime: "latest" } },
      }),
  },
  {
    stem: "m-temporal-read-014-bitemporal-valid-time-past-transaction-time-latest",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: {
          asOf: { transactionTime: "latest", validTime: at("2024-03-01T00:00:00+00:00") },
        },
      }),
  },
  {
    stem: "m-temporal-read-015-bitemporal-both-axes-past",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: {
          asOf: {
            transactionTime: at("2024-02-01T00:00:00+00:00"),
            validTime: at("2024-03-01T00:00:00+00:00"),
          },
        },
      }),
  },
  {
    stem: "m-temporal-read-016-bitemporal-history",
    entity: "Position",
    build: () =>
      buildFindOperation(new Predicate({ eq: { attr: "Position.id", value: 1 } }), {
        temporal: { history: ["transactionTime", "validTime"] },
      }),
  },
  {
    stem: "m-temporal-read-017-bitemporal-omitted-transaction-time-default",
    entity: "Position",
    build: () =>
      buildFindOperation(all(), {
        temporal: { asOf: { validTime: at("2024-03-01T00:00:00+00:00") } },
      }),
  },
];

it("the temporal suite covers exactly the TEMPORAL family", () => {
  expect(CASES.map((c) => c.stem).sort()).toEqual([...TEMPORAL].sort());
});

// Temporal reads are dialect-agnostic (the m-temporal-read axis wrapping lowers through the m-dialect seam),
// so the suite fans out over every database `PARALLAX_DATABASES` selects. `MARIADB_GUARDED_
// CASES` (`_providers.ts`) holds no TEMPORAL-family stem — the bitemporal `Position` cases
// (m-temporal-read-013–m-temporal-read-017) used to be guarded off MariaDB (a reserved-word gap), now
// fixed — so this suite runs the same case count on every selected database; the guard stays wired
// for a future dialect-specific gap, and reports each one WITH its reason.
group.skipIf(!HAS_DOCKER).each(selectedProviders())("temporal reads suite ($label)", (dbp) => {
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

  // An explicit loop, NOT `it.skip.each` with a `$reason` placeholder: vitest
  // truncates each `$`-interpolated value at ~35 characters, which would clip the
  // reason mid-sentence. A title built here is printed in full. (Empty today, so
  // nothing renders — but the mechanism has to be right before an entry lands.)
  for (const { stem, reason } of guarded) {
    it.skip(`${stem}: guarded on MariaDB — ${reason}`, () => {});
  }
});
