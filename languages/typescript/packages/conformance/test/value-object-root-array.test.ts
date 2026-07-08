/**
 * Top-level `many` value object (a **root array**) — the off-corpus surface the
 * frozen `m-value-object-*` models do not exercise (every corpus value object is a
 * top-level `address` = `one`, with a nested `phones` = `many`).
 *
 * This drives the REAL metamodel-backed resolver (`MetamodelSchema.resolveNested`)
 * over a synthetic, schema-valid descriptor whose top-level `tags` value object is
 * `cardinality: many`, proving:
 *  - `resolveNested` honors the TOP-LEVEL cardinality — a top-level `many` sets
 *    `manyIndex = 0` (the document column itself is the array, an empty `arrayPath`)
 *    and, for an exists path with empty `rest`, `leafIsMany = true`;
 *  - `compile` + the two dialects render the root array validly (Postgres
 *    `jsonb_array_elements` over the guarded column directly; MariaDB the containment
 *    family over the document root `$`);
 *  - MariaDB's equality-only containment deferral holds for a root-array element
 *    predicate too (a non-equality any-element predicate is rejected pre-SQL).
 */
import { canonicalBinds, type Dialect, mariadbDialect, postgresDialect } from "@parallax/dialect";
import { Metamodel, parseOperation } from "@parallax/operation";
import { compile } from "@parallax/sql";
import { describe, expect, it } from "vitest";
import { MetamodelSchema } from "../src/schema-resolver.js";

/** A schema-valid model whose one top-level value object (`tags`) is `many`. */
const ROOT_ARRAY_DESCRIPTOR = {
  entity: {
    name: "Tagged",
    namespace: "parallax.test",
    table: "tagged",
    mutability: "transactional",
    temporal: "non-temporal",
    attributes: [
      {
        name: "id",
        type: "int64",
        column: "id",
        primaryKey: true,
        pkGenerator: "none",
      },
    ],
    valueObjects: [
      {
        name: "tags",
        column: "tags",
        mapping: "json",
        cardinality: "many",
        nullable: true,
        attributes: [
          { name: "label", type: "string", nullable: true },
          { name: "weight", type: "int64", nullable: true },
        ],
      },
    ],
    indices: [{ name: "tagged_pk", attributes: ["id"], unique: true }],
  },
} as const;

/** A `MetamodelSchema` over the root-array model, projecting just `t0.id`. */
function rootArraySchema(dialect: Dialect): MetamodelSchema {
  const metamodel = Metamodel.fromDescriptor(ROOT_ARRAY_DESCRIPTOR);
  const [entity] = metamodel.entities();
  if (entity === undefined) {
    throw new Error("synthetic descriptor declares no entity");
  }
  return new MetamodelSchema(metamodel, entity, [{ column: "id", type: "int64" }], dialect);
}

const HEAD = "select t0.id from tagged t0 where ";
const PG_GUARD =
  "case when jsonb_typeof(jsonb_extract_path(t0.tags)) = ? then jsonb_extract_path(t0.tags) " +
  "else cast(? as jsonb) end";

describe("resolveNested honors a top-level `many` value object", () => {
  const schema = rootArraySchema(postgresDialect);

  it("an exists path with empty `rest` is the to-many leaf (manyIndex 0, root array)", () => {
    expect(schema.resolveNested("Tagged.tags")).toEqual({
      table: "tagged",
      column: "tags",
      segments: [],
      manyIndex: 0,
      leafIsAttribute: false,
      leafIsMany: true,
    });
  });

  it("a leaf under the root array resolves element-relative (manyIndex still 0)", () => {
    expect(schema.resolveNested("Tagged.tags.label")).toEqual({
      table: "tagged",
      column: "tags",
      segments: ["label"],
      manyIndex: 0,
      leafIsAttribute: true,
      leafType: "string",
      leafIsMany: false,
    });
  });
});

describe("compile lowers a root array validly on both dialects", () => {
  it("nestedExists(Class.vo) — Postgres unnests the guarded column directly", () => {
    const op = parseOperation({ nestedExists: { path: "Tagged.tags" } });
    const result = compile(op, rootArraySchema(postgresDialect), postgresDialect);
    expect(result.sql).toBe(`${HEAD}exists (select 1 from jsonb_array_elements(${PG_GUARD}) t1)`);
    // The guard's `rawJson('[]')` sentinel canonicalizes to the scalar string `"[]"`.
    expect(canonicalBinds(result.binds)).toEqual(["array", "[]"]);
  });

  it("nestedExists(Class.vo) — MariaDB tests containment over the document root `$`", () => {
    const op = parseOperation({ nestedExists: { path: "Tagged.tags" } });
    expect(compile(op, rootArraySchema(mariadbDialect), mariadbDialect)).toEqual({
      sql: `${HEAD}json_type(json_extract(t0.tags, ?)) = ? and json_length(t0.tags, ?) > ?`,
      binds: ["$", "ARRAY", "$", 0],
    });
  });

  it("a flat any-element eq through the root array lowers over the element alias", () => {
    const op = parseOperation({
      nestedEq: { path: "Tagged.tags.label", value: "home" },
    });
    const result = compile(op, rootArraySchema(postgresDialect), postgresDialect);
    expect(result.sql).toBe(
      `${HEAD}exists (select 1 from jsonb_array_elements(${PG_GUARD}) t1 where jsonb_extract_path_text(t1.value, ?) = ?)`,
    );
    expect(canonicalBinds(result.binds)).toEqual(["array", "[]", "label", "home"]);
  });

  it("a same-element scoped `where` eq lowers to a MariaDB containment candidate", () => {
    const op = parseOperation({
      nestedExists: {
        path: "Tagged.tags",
        where: { nestedEq: { path: "label", value: "home" } },
      },
    });
    expect(compile(op, rootArraySchema(mariadbDialect), mariadbDialect)).toEqual({
      sql: `${HEAD}json_type(json_extract(t0.tags, ?)) = ? and json_contains(t0.tags, ?, ?)`,
      binds: ["$", "ARRAY", '{"label":"home"}', "$"],
    });
  });

  it("MariaDB still rejects a NON-equality root-array element predicate (deferral #1)", () => {
    const op = parseOperation({
      nestedNotEq: { path: "Tagged.tags.label", value: "home" },
    });
    expect(() => compile(op, rootArraySchema(mariadbDialect), mariadbDialect)).toThrow(
      /containment golden lowers only equality/,
    );
  });
});
