/**
 * The three `m-value-object` / `m-dialect` decision points, proven directly on both
 * concrete dialects (Docker-free): **nested extraction**, **typed cast**, and
 * **array traversal**. The whole-corpus parity check lives in
 * `@parallax/conformance`'s `value-object-compile.test.ts` (compiling every case to
 * its golden); this pins each dialect fragment in isolation, including MariaDB's
 * per-segment vs single-path bind divergence and its equality-only containment
 * golden — a non-equality to-many element predicate is REJECTED with a capability
 * diagnostic (the documented deferred limitation), while Postgres lowers it.
 */
import {
  mariadbDialect,
  type NestedArrayRequest,
  postgresDialect,
  type ResolvedElementPredicate,
} from "@parallax/dialect";
import { describe, expect, it } from "vitest";

describe("nested extraction form (m-dialect)", () => {
  it("Postgres carries one ? per path segment; MariaDB one '$.a.b' path bind", () => {
    expect(postgresDialect.nestedExtraction("t0.address", ["city"])).toEqual({
      sql: "jsonb_extract_path_text(t0.address, ?)",
      binds: ["city"],
    });
    expect(postgresDialect.nestedExtraction("t0.address", ["geo", "country"])).toEqual({
      sql: "jsonb_extract_path_text(t0.address, ?, ?)",
      binds: ["geo", "country"],
    });
    expect(mariadbDialect.nestedExtraction("t0.address", ["city"])).toEqual({
      sql: "json_value(t0.address, ?)",
      binds: ["$.city"],
    });
    expect(mariadbDialect.nestedExtraction("t0.address", ["geo", "point", "lat"])).toEqual({
      sql: "json_value(t0.address, ?)",
      binds: ["$.geo.point.lat"],
    });
  });
});

describe("typed cast form (m-dialect)", () => {
  it("casts a non-text extraction; a text attribute compares directly", () => {
    const pg = "jsonb_extract_path_text(t0.address, ?, ?)";
    expect(postgresDialect.typedCast(pg, "float64")).toBe(`cast(${pg} as double precision)`);
    expect(postgresDialect.typedCast(pg, "int64")).toBe(`cast(${pg} as bigint)`);
    expect(postgresDialect.typedCast(pg, "decimal(18,2)")).toBe(`cast(${pg} as decimal(18, 2))`);
    expect(postgresDialect.typedCast(pg, "string")).toBe(pg);

    const my = "json_value(t0.address, ?)";
    expect(mariadbDialect.typedCast(my, "float64")).toBe(`cast(${my} as double)`);
    expect(mariadbDialect.typedCast(my, "int64")).toBe(`cast(${my} as signed)`);
    expect(mariadbDialect.typedCast(my, "decimal(18,2)")).toBe(`cast(${my} as decimal(18, 2))`);
    expect(mariadbDialect.typedCast(my, "string")).toBe(my);
  });
});

/** A base non-empty / any-element / same-element request over `t0.address.phones`. */
function request(overrides: Partial<NestedArrayRequest> = {}): NestedArrayRequest {
  return {
    column: "t0.address",
    arrayPath: ["phones"],
    elementAlias: "t1",
    negated: false,
    ...overrides,
  };
}

const EQ_TYPE_HOME: ResolvedElementPredicate = {
  op: "eq",
  path: ["type"],
  value: "home",
  valueType: "string",
};
const SAME_ELEMENT: ResolvedElementPredicate = {
  op: "and",
  operands: [EQ_TYPE_HOME, { op: "eq", path: ["number"], value: "555-9999", valueType: "string" }],
};

describe("array traversal form (m-dialect) — Postgres jsonb_array_elements", () => {
  it("non-empty existence unnests under the case/jsonb_typeof array guard", () => {
    expect(postgresDialect.nestedArrayPredicate(request())).toEqual({
      sql: "exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1)",
      binds: ["phones", "array", "phones", "[]"],
    });
  });

  it("any-element eq reads the element field over the unnest alias", () => {
    expect(postgresDialect.nestedArrayPredicate(request({ element: EQ_TYPE_HOME }))).toEqual({
      sql: "exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where jsonb_extract_path_text(t1.value, ?) = ?)",
      binds: ["phones", "array", "phones", "[]", "type", "home"],
    });
  });

  it("same-element `and` puts both predicates on one alias; notExists prepends `not`", () => {
    expect(
      postgresDialect.nestedArrayPredicate(request({ element: SAME_ELEMENT, negated: true })),
    ).toEqual({
      sql: "not exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where jsonb_extract_path_text(t1.value, ?) = ? and jsonb_extract_path_text(t1.value, ?) = ?)",
      binds: ["phones", "array", "phones", "[]", "type", "home", "number", "555-9999"],
    });
  });

  it("casts a numeric element eq/in and compares a boolean element eq as JSON text", () => {
    // Off-corpus: the frozen to-many coverage is equality on string fields. Postgres
    // now casts a numeric element extraction (as the range ops already did) and binds
    // a boolean element value as its JSON-text form so `<extraction> = ?` stays valid.
    const numericEq = postgresDialect.nestedArrayPredicate(
      request({
        element: { op: "eq", path: ["rank"], value: 5, valueType: "int64" },
      }),
    );
    expect(numericEq.sql).toContain(
      "where cast(jsonb_extract_path_text(t1.value, ?) as bigint) = ?",
    );
    expect(numericEq.binds).toEqual(["phones", "array", "phones", "[]", "rank", 5]);

    const numericIn = postgresDialect.nestedArrayPredicate(
      request({
        element: {
          op: "in",
          path: ["rank"],
          values: [1, 2],
          valueType: "int64",
        },
      }),
    );
    expect(numericIn.sql).toContain(
      "where cast(jsonb_extract_path_text(t1.value, ?) as bigint) in (?, ?)",
    );
    expect(numericIn.binds).toEqual(["phones", "array", "phones", "[]", "rank", 1, 2]);

    const boolEq = postgresDialect.nestedArrayPredicate(
      request({
        element: {
          op: "eq",
          path: ["verified"],
          value: true,
          valueType: "boolean",
        },
      }),
    );
    expect(boolEq.sql).toContain("where jsonb_extract_path_text(t1.value, ?) = ?");
    expect(boolEq.binds).toEqual(["phones", "array", "phones", "[]", "verified", "true"]);
  });

  it("lowers a NON-equality element predicate generally (Postgres is fully general)", () => {
    const notEq: ResolvedElementPredicate = {
      op: "notEq",
      path: ["type"],
      value: "home",
      valueType: "string",
    };
    const result = postgresDialect.nestedArrayPredicate(request({ element: notEq }));
    expect(result.sql).toContain("where not jsonb_extract_path_text(t1.value, ?) = ?");
  });
});

describe("array traversal form (m-dialect) — MariaDB containment family", () => {
  it("non-empty existence guards json_length; notExists wraps in coalesce", () => {
    expect(mariadbDialect.nestedArrayPredicate(request())).toEqual({
      sql: "json_type(json_extract(t0.address, ?)) = ? and json_length(t0.address, ?) > ?",
      binds: ["$.phones", "ARRAY", "$.phones", 0],
    });
    expect(mariadbDialect.nestedArrayPredicate(request({ negated: true }))).toEqual({
      sql: "not coalesce(json_type(json_extract(t0.address, ?)) = ? and json_length(t0.address, ?) > ?, ?)",
      binds: ["$.phones", "ARRAY", "$.phones", 0, 0],
    });
  });

  it("any-element eq builds a one-field candidate; same-element carries every field", () => {
    expect(mariadbDialect.nestedArrayPredicate(request({ element: EQ_TYPE_HOME }))).toEqual({
      sql: "json_type(json_extract(t0.address, ?)) = ? and json_contains(t0.address, ?, ?)",
      binds: ["$.phones", "ARRAY", '{"type":"home"}', "$.phones"],
    });
    expect(mariadbDialect.nestedArrayPredicate(request({ element: SAME_ELEMENT }))).toEqual({
      sql: "json_type(json_extract(t0.address, ?)) = ? and json_contains(t0.address, ?, ?)",
      binds: ["$.phones", "ARRAY", '{"type":"home", "number":"555-9999"}', "$.phones"],
    });
  });

  it("a numeric element eq builds a JSON-number candidate; a boolean a JSON-boolean one", () => {
    // The MariaDB containment candidate carries the NATIVE JSON value (a number / a
    // boolean), so `json_contains` matches by JSON containment — contrast Postgres,
    // which compares the text extraction (a boolean → JSON text, see below).
    expect(
      mariadbDialect.nestedArrayPredicate(
        request({
          element: { op: "eq", path: ["rank"], value: 5, valueType: "int64" },
        }),
      ),
    ).toEqual({
      sql: "json_type(json_extract(t0.address, ?)) = ? and json_contains(t0.address, ?, ?)",
      binds: ["$.phones", "ARRAY", '{"rank":5}', "$.phones"],
    });
    expect(
      mariadbDialect.nestedArrayPredicate(
        request({
          element: {
            op: "eq",
            path: ["verified"],
            value: true,
            valueType: "boolean",
          },
        }),
      ),
    ).toEqual({
      sql: "json_type(json_extract(t0.address, ?)) = ? and json_contains(t0.address, ?, ?)",
      binds: ["$.phones", "ARRAY", '{"verified":true}', "$.phones"],
    });
  });

  it("REJECTS a non-equality element predicate with a capability diagnostic (deferral #1)", () => {
    const nonEq: readonly ResolvedElementPredicate[] = [
      { op: "notEq", path: ["type"], value: "home", valueType: "string" },
      { op: "gt", path: ["number"], value: 10, valueType: "int64" },
      { op: "or", operands: [EQ_TYPE_HOME, EQ_TYPE_HOME] },
      { op: "not", operand: EQ_TYPE_HOME },
    ];
    for (const element of nonEq) {
      expect(() => mariadbDialect.nestedArrayPredicate(request({ element }))).toThrow(
        /containment golden lowers only equality/,
      );
    }
  });
});
