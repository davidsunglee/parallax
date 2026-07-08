/**
 * API Conformance Suite — **value-objects** family (Phase 11): the typed
 * nested-predicate developer surface (m-value-object) and value-object
 * materialization, written as an application developer would, run against
 * `postgres:17` through the SHIPPED `@parallax/db-postgres` adapter.
 *
 * Each case:
 *  1. `assertSameOperation(dsl, case)` — the developer's typed nested-predicate
 *     DSL (`Customer.address.city.eq(...)`, `Customer.address.phones.exists(...)`
 *     with a scoped element `where`) builds the corpus's canonical `operation`
 *     (the no-drift guard);
 *  2. runs `px.customers.find(...)` and asserts the returned MANAGED rows (flat
 *     reads) or the assembled `graph` (materialization reads) equal the corpus —
 *     the value-object composite arriving WITH the owner in one round trip, its
 *     declared nested getters to arbitrary depth (no reverse getter, no child
 *     fetch); a write case commits `px.transaction(create)` and asserts the
 *     resulting table state (the atomic document bind).
 *
 * The `Customer` entity symbol is hand-authored exactly as codegen emits it
 * (`codegen/emit.ts` `valueObjectBuilder`), so the suite exercises the same DSL
 * classes the generated barrel uses. The official grade stays contract-driven
 * over the generic runtime; this is additive proof the developer surface + shipped
 * adapter reproduce the corpus.
 */

import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import {
  AttributeExpression,
  NestedFieldExpression,
  Predicate,
  ValueObjectExpression,
} from "../../src/index.js";
import {
  type ApiConformanceProvider,
  assertGraph,
  assertRows,
  assertSameOperation,
  assertTableState,
  type CaseFixture,
  provisionCase,
} from "./_harness.js";
import { HAS_DOCKER, selectedProviders } from "./_providers.js";
import { VALUE_OBJECTS } from "./covered.js";

// --- entity symbols (as codegen emits them) ---------------------------------

const attr = (ref: string): AttributeExpression => new AttributeExpression(ref);
const nf = (ref: string): NestedFieldExpression => new NestedFieldExpression(ref);
const all = (): Predicate => new Predicate({ all: {} });

/** The `Customer.address.phones` builder — full-path fields + an element-relative scope. */
const phones = Object.assign(new ValueObjectExpression("Customer.address.phones"), {
  type: nf("Customer.address.phones.type"),
  number: nf("Customer.address.phones.number"),
  element: { type: nf("type"), number: nf("number") },
});

const point = Object.assign(new ValueObjectExpression("Customer.address.geo.point"), {
  lat: nf("Customer.address.geo.point.lat"),
  lon: nf("Customer.address.geo.point.lon"),
});

const geo = Object.assign(new ValueObjectExpression("Customer.address.geo"), {
  country: nf("Customer.address.geo.country"),
  elevation: nf("Customer.address.geo.elevation"),
  point,
});

const address = Object.assign(new ValueObjectExpression("Customer.address"), {
  street: nf("Customer.address.street"),
  city: nf("Customer.address.city"),
  geo,
  phones,
});

const Customer = { id: attr("Customer.id"), name: attr("Customer.name"), address };

// --- suite rows -------------------------------------------------------------

/** How a value-object case is graded: flat rows, a materialized graph, or table state. */
type Kind = "rows" | "graph" | "write";

/** One suite row: the DSL a developer writes, its grading kind, and the case stem. */
interface Row {
  readonly stem: string;
  readonly kind: Kind;
  /** The developer predicate (read cases); absent on a write case. */
  readonly predicate?: () => Predicate;
  /** The create input (write cases). */
  readonly input?: Record<string, unknown>;
}

/** A flat-read predicate case (graded against `then.rows`). */
function r(stem: string, predicate: () => Predicate): Row {
  return { stem, kind: "rows", predicate };
}

/** A value-object materialization case (graded against `then.graph`). */
function g(stem: string, predicate: () => Predicate): Row {
  return { stem, kind: "graph", predicate };
}

const CASES: readonly Row[] = [
  // Flat nested predicates — comparisons at shallow / two-level / three-level depth.
  r("m-value-object-001-nested-eq", () => Customer.address.city.eq("Oslo")),
  r("m-value-object-002-nested-deep-eq", () => Customer.address.geo.country.eq("US")),
  r("m-value-object-004-nested-not-eq", () => Customer.address.city.notEq("Oslo")),
  r("m-value-object-005-nested-null-excluded", () => Customer.address.city.notEq("Boston")),
  r("m-value-object-006-nested-in", () => Customer.address.city.in(["Oslo", "Boston"])),
  r("m-value-object-007-nested-is-null", () => Customer.address.city.isNull()),
  r("m-value-object-008-nested-is-not-null", () => Customer.address.city.isNotNull()),
  r("m-value-object-009-nested-gt-cast", () => Customer.address.geo.elevation.gt(8)),
  r("m-value-object-010-nested-lt-cast", () => Customer.address.geo.elevation.lt(8)),
  r("m-value-object-011-nested-gte-deep-cast", () => Customer.address.geo.point.lat.gte(59.9)),
  r("m-value-object-012-nested-lte-deep-cast", () => Customer.address.geo.point.lat.lte(50)),
  r("m-value-object-013-nested-is-null-collapse", () => Customer.address.geo.country.isNull()),
  r("m-value-object-014-nested-is-not-null-deep", () => Customer.address.geo.country.isNotNull()),
  // To-many — exists / any-element / same-element (scoped where).
  r("m-value-object-015-nested-exists-nonempty", () => Customer.address.phones.exists()),
  r("m-value-object-016-nested-not-exists-empty-or-null", () =>
    Customer.address.phones.notExists(),
  ),
  r("m-value-object-017-nested-any-element-eq", () => Customer.address.phones.type.eq("home")),
  r("m-value-object-018-nested-any-element-and-different", () =>
    Customer.address.phones.type.eq("home").and(Customer.address.phones.number.eq("555-9999")),
  ),
  r("m-value-object-019-nested-exists-scoped-where", () =>
    Customer.address.phones.exists(
      phones.element.type.eq("home").and(phones.element.number.eq("555-9999")),
    ),
  ),
  r("m-value-object-020-nested-not-exists-scoped-where", () =>
    Customer.address.phones.notExists(
      phones.element.type.eq("home").and(phones.element.number.eq("555-9999")),
    ),
  ),
  r("m-value-object-021-nested-any-element-scalar-collapse", () =>
    Customer.address.phones.number.eq("555-0000"),
  ),
  r("m-value-object-022-nested-not-exists-scoped-scalar-collapse", () =>
    Customer.address.phones.notExists(phones.element.number.eq("555-0000")),
  ),
  // Materialization — the whole nested composite arrives with the owner.
  g("m-value-object-023-graph-nested-materialization", () => all()),
  g("m-value-object-024-graph-filtered-materialization", () => Customer.address.city.eq("Oslo")),
  // Write — the whole document binds atomically in columnOrder position.
  {
    stem: "m-value-object-025-write-insert-document",
    kind: "write",
    input: {
      id: 100n,
      name: "Solveig",
      address: {
        street: "12 Aurora Ave",
        city: "Tromso",
        geo: { country: "NO" },
        phones: [
          { type: "home", number: "555-0001" },
          { type: "work", number: "555-0002" },
        ],
      },
    },
  },
];

it("the value-objects suite covers exactly the VALUE_OBJECTS family", () => {
  expect(CASES.map((c) => c.stem).sort()).toEqual([...VALUE_OBJECTS].sort());
});

group.skipIf(!HAS_DOCKER).each(selectedProviders())("value-objects suite ($label)", (dbp) => {
  const BOOT_TIMEOUT = 600_000;
  let provider: ApiConformanceProvider;

  beforeAll(async () => {
    provider = await dbp.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it.each(CASES.filter((c) => c.kind !== "write"))(
    "$stem: a developer nested-predicate read reproduces the corpus",
    async (row) => {
      const fixture: CaseFixture = await provisionCase(provider, row.stem);
      const predicate = row.predicate?.() ?? all();

      // Guard 1 — the typed nested-predicate DSL builds the corpus operation (no drift).
      assertSameOperation(predicate.toOperation(), fixture.loaded);

      const rows = await fixture.px.entity("Customer").find(predicate).toArray();
      if (row.kind === "graph") {
        // The value-object composite materializes WITH the owner (one round trip).
        assertGraph(rows, fixture.loaded, "Customer", fixture.metamodel);
      } else {
        assertRows(rows, fixture.loaded, "Customer", fixture.metamodel);
      }
    },
    BOOT_TIMEOUT,
  );

  it.each(CASES.filter((c) => c.kind === "write"))(
    "$stem: a developer create binds the whole document atomically",
    async (row) => {
      const fixture = await provisionCase(provider, row.stem);
      await fixture.px.transaction(async (tx) => {
        await tx.entity("Customer").create(row.input ?? {});
      });
      await assertTableState(fixture);
    },
    BOOT_TIMEOUT,
  );
});
