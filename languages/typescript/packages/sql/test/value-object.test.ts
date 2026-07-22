/**
 * m-sql value-object nested-predicate compiler unit tests (Docker-free).
 *
 * Drives the `compile` visitor over a small hand-built value-object `SchemaResolver`
 * (`resolveNested`), asserting `emitted === golden` + binds for the flat nested
 * family, the to-one/deep extraction + typed cast, and the to-many array-traversal
 * forms — including the element-scope branches the equality-only corpus does not
 * exercise (a scoped `where` with `or` / a range / a null check), proving the
 * Postgres lowering is fully general and the MariaDB containment golden rejects a
 * non-equality element predicate (deferral #1). The whole-corpus parity lane lives
 * in `@parallax/conformance`; this pins the compiler's nested emission in isolation.
 */
import {
  canonicalBinds,
  mariadbDialect,
  postgresDialect,
  quoteIdentifier,
} from "@parallax/dialect";
import { type Operation, parseOperation } from "@parallax/operation";
import { describe, expect, it } from "vitest";
import {
  type Bind,
  compile,
  type ResolvedColumn,
  type ResolvedNestedPath,
  type ResolvedRelationship,
  type SchemaResolver,
} from "../src/index.js";

/** The declared recursive `address` value-object structure the stub resolves against. */
interface Member {
  readonly multiplicity: "one" | "many";
  readonly attributes: Readonly<Record<string, string>>;
  readonly valueObjects: Readonly<Record<string, Member>>;
}
const ADDRESS: Member = {
  multiplicity: "one",
  // `unit` (int64) and `verified` (boolean) are off-corpus to-one non-string leaves
  // exercising the typed-cast / JSON-text-boolean nested-comparison surface.
  attributes: {
    street: "string",
    city: "string",
    unit: "int64",
    verified: "boolean",
  },
  valueObjects: {
    geo: {
      multiplicity: "one",
      attributes: { country: "string", elevation: "float64" },
      valueObjects: {
        point: {
          multiplicity: "one",
          attributes: { lat: "float64", lon: "float64" },
          valueObjects: {},
        },
      },
    },
    phones: {
      multiplicity: "many",
      attributes: { type: "string", number: "string", rank: "int64" },
      valueObjects: {},
    },
  },
};

/** A `Customer` resolver whose one value object is `address` (column `address`). */
function customerResolver(): SchemaResolver {
  return {
    resolveAttribute(ref: string): ResolvedColumn {
      const attr = ref.slice(ref.indexOf(".") + 1);
      return {
        table: "customer",
        column: quoteIdentifier(attr),
        type: "string",
      };
    },
    resolveRelationship(ref: string): ResolvedRelationship {
      throw new Error(`no relationships in the value-object unit tests: '${ref}'`);
    },
    rootTable: () => "customer",
    rootProjection: () => [{ column: quoteIdentifier("id") }, { column: quoteIdentifier("name") }],
    resolveNested(ref: string): ResolvedNestedPath {
      const [, voName, ...rest] = ref.split(".");
      if (voName !== "address") {
        throw new Error(`'${ref}': '${String(voName)}' is not a value object`);
      }
      let member: Member = ADDRESS;
      // Full-path convention: the top-level value object is index 0, so a nested
      // `many` at `rest[k]` is `k + 1` and a top-level `many` is `0` (root array).
      let manyIndex = ADDRESS.multiplicity === "many" ? 0 : -1;
      let leafIsAttribute = false;
      let leafType: string | undefined;
      let leafIsMany = rest.length === 0 && ADDRESS.multiplicity === "many";
      rest.forEach((segment, index) => {
        const nested = member.valueObjects[segment];
        if (nested !== undefined) {
          if (nested.multiplicity === "many" && manyIndex === -1) {
            manyIndex = index + 1;
          }
          member = nested;
          if (index === rest.length - 1) {
            leafIsMany = nested.multiplicity === "many";
          }
          return;
        }
        const type = member.attributes[segment];
        if (type === undefined) {
          throw new Error(`'${ref}': '${segment}' is not a member`);
        }
        leafIsAttribute = true;
        leafType = type;
      });
      return {
        table: "customer",
        column: quoteIdentifier("address"),
        segments: rest,
        manyIndex,
        leafIsAttribute,
        ...(leafType === undefined ? {} : { leafType }),
        leafIsMany,
      };
    },
  };
}

/**
 * Compile a schema-validated operation over `customer` for the given dialect,
 * canonicalizing the compiled binds: a to-many read carries the array-guard
 * `rawJson('[]')` sentinel, which collapses to the scalar string `"[]"` (a no-op for
 * every scalar-only flat-family bind), matching the reported/golden form.
 */
function emit(op: unknown, dialect = postgresDialect): { sql: string; binds: readonly Bind[] } {
  const operation = parseOperation(op) as Operation;
  const { sql, binds } = compile(operation, customerResolver(), dialect);
  return { sql, binds: canonicalBinds(binds) as readonly Bind[] };
}

const HEAD = "select t0.id, t0.name from customer t0 where ";

describe("m-sql value-object nested predicates — flat family (Postgres)", () => {
  const cases: ReadonlyArray<{
    id: string;
    op: unknown;
    where: string;
    binds: readonly Bind[];
  }> = [
    {
      id: "nestedEq shallow",
      op: { nestedEq: { path: "Customer.address.city", value: "Oslo" } },
      where: "jsonb_extract_path_text(t0.address, ?) = ?",
      binds: ["city", "Oslo"],
    },
    {
      id: "nestedEq deep two-level",
      op: { nestedEq: { path: "Customer.address.geo.country", value: "US" } },
      where: "jsonb_extract_path_text(t0.address, ?, ?) = ?",
      binds: ["geo", "country", "US"],
    },
    {
      id: "nestedNotEq leading not",
      op: { nestedNotEq: { path: "Customer.address.city", value: "Oslo" } },
      where: "not jsonb_extract_path_text(t0.address, ?) = ?",
      binds: ["city", "Oslo"],
    },
    {
      id: "nestedGt numeric cast",
      op: { nestedGt: { path: "Customer.address.geo.elevation", value: 8 } },
      where: "cast(jsonb_extract_path_text(t0.address, ?, ?) as double precision) > ?",
      binds: ["geo", "elevation", 8],
    },
    {
      id: "nestedGte three-level cast",
      op: {
        nestedGte: { path: "Customer.address.geo.point.lat", value: 59.9 },
      },
      where: "cast(jsonb_extract_path_text(t0.address, ?, ?, ?) as double precision) >= ?",
      binds: ["geo", "point", "lat", 59.9],
    },
    {
      id: "nestedIn membership",
      op: {
        nestedIn: { path: "Customer.address.city", values: ["Oslo", "Boston"] },
      },
      where: "jsonb_extract_path_text(t0.address, ?) in (?, ?)",
      binds: ["city", "Oslo", "Boston"],
    },
    {
      id: "nestedIsNull",
      op: { nestedIsNull: { path: "Customer.address.city" } },
      where: "jsonb_extract_path_text(t0.address, ?) is null",
      binds: ["city"],
    },
    {
      id: "nestedIsNotNull leading not",
      op: { nestedIsNotNull: { path: "Customer.address.city" } },
      where: "not jsonb_extract_path_text(t0.address, ?) is null",
      binds: ["city"],
    },
  ];
  it.each(cases)("$id", ({ op, where, binds }) => {
    const result = emit(op);
    expect(result.sql).toBe(`${HEAD}${where}`);
    expect(result.binds).toEqual(binds);
  });
});

describe("m-sql value-object nested predicates — MariaDB flat divergence", () => {
  it("carries one '$.a.b' path bind and casts to `double`", () => {
    expect(
      emit({ nestedEq: { path: "Customer.address.geo.country", value: "US" } }, mariadbDialect),
    ).toEqual({
      sql: `${HEAD}json_value(t0.address, ?) = ?`,
      binds: ["$.geo.country", "US"],
    });
    expect(
      emit({ nestedGt: { path: "Customer.address.geo.elevation", value: 8 } }, mariadbDialect),
    ).toEqual({
      sql: `${HEAD}cast(json_value(t0.address, ?) as double) > ?`,
      binds: ["$.geo.elevation", 8],
    });
  });
});

describe("m-sql value-object flat family — typed cast on non-string leaves (off-corpus)", () => {
  // The frozen corpus exercises eq/notEq/in only on `string` leaves; these pin the
  // spec's general rule (m-op-algebra: "casts it to the declared type before
  // comparing") for a numeric / boolean leaf, which the goldens never witness.
  it("numeric nestedEq/nestedNotEq cast the extraction (Postgres bigint, MariaDB signed)", () => {
    expect(emit({ nestedEq: { path: "Customer.address.unit", value: 42 } })).toEqual({
      sql: `${HEAD}cast(jsonb_extract_path_text(t0.address, ?) as bigint) = ?`,
      binds: ["unit", 42],
    });
    expect(emit({ nestedNotEq: { path: "Customer.address.unit", value: 42 } })).toEqual({
      sql: `${HEAD}not cast(jsonb_extract_path_text(t0.address, ?) as bigint) = ?`,
      binds: ["unit", 42],
    });
    expect(
      emit({ nestedEq: { path: "Customer.address.unit", value: 42 } }, mariadbDialect),
    ).toEqual({
      sql: `${HEAD}cast(json_value(t0.address, ?) as signed) = ?`,
      binds: ["$.unit", 42],
    });
  });

  it("numeric nestedIn casts the extraction once before the membership list", () => {
    expect(emit({ nestedIn: { path: "Customer.address.unit", values: [1, 2] } })).toEqual({
      sql: `${HEAD}cast(jsonb_extract_path_text(t0.address, ?) as bigint) in (?, ?)`,
      binds: ["unit", 1, 2],
    });
    expect(
      emit({ nestedIn: { path: "Customer.address.unit", values: [1, 2] } }, mariadbDialect),
    ).toEqual({
      sql: `${HEAD}cast(json_value(t0.address, ?) as signed) in (?, ?)`,
      binds: ["$.unit", 1, 2],
    });
  });

  it("a boolean leaf carries NO cast and compares as JSON text ('true'/'false')", () => {
    // m-dialect specifies no boolean cast, so the boolean compares against its
    // JSON-text form over the (text) extraction — valid text-to-text on both dialects.
    expect(emit({ nestedEq: { path: "Customer.address.verified", value: true } })).toEqual({
      sql: `${HEAD}jsonb_extract_path_text(t0.address, ?) = ?`,
      binds: ["verified", "true"],
    });
    expect(
      emit({
        nestedNotEq: { path: "Customer.address.verified", value: false },
      }),
    ).toEqual({
      sql: `${HEAD}not jsonb_extract_path_text(t0.address, ?) = ?`,
      binds: ["verified", "false"],
    });
    expect(
      emit({ nestedEq: { path: "Customer.address.verified", value: true } }, mariadbDialect),
    ).toEqual({
      sql: `${HEAD}json_value(t0.address, ?) = ?`,
      binds: ["$.verified", "true"],
    });
  });

  it("a string leaf still emits NO cast (the no-op is byte-identical to the goldens)", () => {
    expect(emit({ nestedEq: { path: "Customer.address.city", value: "Oslo" } })).toEqual({
      sql: `${HEAD}jsonb_extract_path_text(t0.address, ?) = ?`,
      binds: ["city", "Oslo"],
    });
    expect(
      emit({
        nestedIn: { path: "Customer.address.city", values: ["Oslo", "Boston"] },
      }),
    ).toEqual({
      sql: `${HEAD}jsonb_extract_path_text(t0.address, ?) in (?, ?)`,
      binds: ["city", "Oslo", "Boston"],
    });
  });
});

describe("m-sql value-object to-many — Postgres jsonb_array_elements (general)", () => {
  it("a scoped `where` with `or` / a range cast / a null check lowers generally", () => {
    const op = {
      nestedExists: {
        path: "Customer.address.phones",
        where: {
          or: {
            operands: [
              { nestedGt: { path: "rank", value: 5 } },
              { nestedIsNull: { path: "type" } },
            ],
          },
        },
      },
    };
    const { sql, binds } = emit(op);
    expect(sql).toBe(
      `${HEAD}exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where cast(jsonb_extract_path_text(t1.value, ?) as bigint) > ? or jsonb_extract_path_text(t1.value, ?) is null)`,
    );
    expect(binds).toEqual(["phones", "array", "phones", "[]", "rank", 5, "type"]);
  });

  it("two ANDed any-element predicates get independent aliases t1 and t2", () => {
    const op = {
      and: {
        operands: [
          { nestedEq: { path: "Customer.address.phones.type", value: "home" } },
          {
            nestedEq: {
              path: "Customer.address.phones.number",
              value: "555-9999",
            },
          },
        ],
      },
    };
    const { sql } = emit(op);
    expect(sql).toContain(") t1 where");
    expect(sql).toContain(") t2 where");
  });
});

describe("m-sql value-object to-many — MariaDB rejects non-equality (deferral #1)", () => {
  it("a scoped `or` where cannot be lowered to the containment golden", () => {
    const op = {
      nestedExists: {
        path: "Customer.address.phones",
        where: {
          or: {
            operands: [
              { nestedEq: { path: "type", value: "home" } },
              { nestedEq: { path: "number", value: "555-9999" } },
            ],
          },
        },
      },
    };
    expect(() => emit(op, mariadbDialect)).toThrow(/containment golden lowers only equality/);
  });
});
