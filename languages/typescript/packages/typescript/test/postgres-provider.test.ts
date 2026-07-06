/**
 * Fixture-insertion quoting invariant (Phase 3 review, Finding 2).
 *
 * `loadFixtures` once rendered `insert into ${table} (${cols})` with RAW
 * descriptor names while the DDL quoted identifiers through the m-dialect seam, so a
 * reserved/non-simple table or column (e.g. `order`, `User`) would be CREATEd
 * quoted but INSERTed unquoted — a divergence that fails even though the table
 * exists. The fix routes both paths through the same `quoteIdentifier` seam.
 *
 * These Docker-free unit tests pin the invariant: the INSERT `renderFixtureInsert`
 * builds must quote every identifier exactly as `quoteIdentifier` does, and the
 * table/column tokens it emits must be byte-identical to the tokens the DDL
 * (`ddlForDescriptor`) emits for the same names — so creation and insertion can
 * never disagree on quoting again.
 */
import { ddlForDescriptor, quoteIdentifier } from "@parallax/dialect";
import { expect, describe as group, it } from "vitest";
import { renderFixtureInsert } from "../src/conformance/postgres-provider.js";

group("renderFixtureInsert quoting", () => {
  it("leaves simple lowercase non-reserved identifiers unquoted (m-op-algebra-002 orders)", () => {
    expect(renderFixtureInsert("orders", ["id", "name"])).toBe(
      "insert into orders (id, name) values ($1, $2)",
    );
  });

  it("quotes a reserved-word table and column, leaving simple ones bare", () => {
    // `order` and `select` are reserved and MUST be double-quoted; `id` is a
    // simple non-reserved identifier and stays bare — exactly the per-identifier
    // decision the m-dialect seam (and therefore the DDL) makes.
    const sql = renderFixtureInsert("order", ["id", "select"]);
    expect(sql).toBe('insert into "order" (id, "select") values ($1, $2)');
    // The tokens match the m-dialect seam exactly (single source of truth).
    expect(sql).toContain(quoteIdentifier("order"));
    expect(sql).toContain(quoteIdentifier("select"));
    expect(quoteIdentifier("id")).toBe("id");
  });

  it("quotes a non-simple (mixed-case) identifier", () => {
    expect(renderFixtureInsert("User", ["userId"])).toBe(
      'insert into "User" ("userId") values ($1)',
    );
  });

  it("emits identifier tokens byte-identical to the DDL for the same names", () => {
    // A reserved table + reserved/non-simple columns: the CREATE TABLE the DDL
    // derives and the INSERT loadFixtures builds MUST quote them identically, so
    // a fixture row loads into the table the DDL created.
    const descriptor = {
      entity: {
        table: "order",
        attributes: [
          { name: "id", column: "id", type: "int64", primaryKey: true },
          { name: "user", column: "user", type: "string", nullable: true },
          { name: "weirdName", column: "weirdName", type: "boolean", nullable: true },
        ],
      },
    };
    const [ddl] = ddlForDescriptor(descriptor);
    const insert = renderFixtureInsert("order", ["id", "user", "weirdName"]);
    // Every quoted token the INSERT uses appears verbatim in the CREATE TABLE.
    for (const name of ["order", "user", "weirdName"]) {
      const quoted = quoteIdentifier(name);
      expect(insert).toContain(quoted);
      expect(ddl).toContain(quoted);
    }
  });
});
