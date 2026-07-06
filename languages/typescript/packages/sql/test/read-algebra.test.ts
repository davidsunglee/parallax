/**
 * m-sql read-algebra compiler unit tests (Docker-free).
 *
 * Drives the canonical-by-construction `compile` visitor directly over a small,
 * hand-built `SchemaResolver` for the `orders` model, asserting `emitted ===
 * golden` + binds for every single-entity read-algebra fragment the corpus pins
 * in the 02xx family — comparison, null, string (incl. wildcard escaping +
 * caseInsensitive), membership, boolean precedence (the `m-op-algebra-024`/`m-op-algebra-025` grouped vs
 * ungrouped pair), and the result directives (`orderBy` / `limit` / `distinct`).
 * The whole-corpus compile lane (driving the real adapter path over the metamodel
 * reader) lives in `@parallax/conformance`'s `read-algebra.test.ts`; this file
 * pins the compiler's emission contract in isolation, including the carry-forward
 * type-aware bind coercion for precision-unsafe int64 / decimal literals.
 */

import { postgresDialect, quoteIdentifier } from "@parallax/dialect";
import { type Operation, parseOperation } from "@parallax/operation";
import { describe, expect, it } from "vitest";
import {
  type Bind,
  coerceBind,
  compile,
  type ResolvedColumn,
  type ResolvedRelationship,
  type SchemaResolver,
} from "../src/index.js";

/**
 * The `orders` columns the 02xx read algebra ranges over (name → column + m-core type
 * + nullability). `sku` is the one NULL-bearing column (mirrors the corpus
 * descriptor), so an ORDER BY on it exercises the dialect's NULL-placement branch.
 */
const ORDERS: Record<string, { column: string; type: string; nullable?: boolean }> = {
  id: { column: "id", type: "int64" },
  name: { column: "name", type: "string" },
  sku: { column: "sku", type: "string", nullable: true },
  qty: { column: "qty", type: "int32" },
  price: { column: "price", type: "decimal(18,2)" },
  active: { column: "active", type: "boolean" },
  orderedOn: { column: "ordered_on", type: "date" },
};

/** A minimal resolver for the `orders` root with the case-driven projection. */
function ordersResolver(projection: readonly string[] = ["id", "name"]): SchemaResolver {
  return {
    resolveAttribute(ref: string): ResolvedColumn {
      const attrName = ref.slice(ref.indexOf(".") + 1);
      const attr = ORDERS[attrName];
      if (!attr) {
        throw new Error(`unknown orders attribute '${ref}'`);
      }
      return {
        table: "orders",
        column: quoteIdentifier(attr.column),
        type: attr.type,
        nullable: attr.nullable,
      };
    },
    resolveRelationship(ref: string): ResolvedRelationship {
      throw new Error(`the read-algebra unit tests do not navigate relationships: '${ref}'`);
    },
    rootTable: () => "orders",
    rootProjection: () => projection.map((name) => ({ column: quoteIdentifier(name) })),
  };
}

/** Compile a YAML-authored operation (validated through the schema) over `orders`. */
function emit(
  op: unknown,
  projection?: readonly string[],
): { sql: string; binds: readonly Bind[] } {
  const operation = parseOperation(op) as Operation;
  return compile(operation, ordersResolver(projection), postgresDialect);
}

/** Each row: a label, the operation, the golden Postgres SQL, the ordered binds. */
const CASES: ReadonlyArray<{
  id: string;
  op: unknown;
  sql: string;
  binds: readonly Bind[];
  projection?: readonly string[];
}> = [
  // --- comparison ---
  {
    id: "m-op-algebra-003 notEq",
    op: { notEq: { attr: "Order.qty", value: 20 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty <> ?",
    binds: [20],
  },
  {
    id: "m-op-algebra-004 greaterThan",
    op: { greaterThan: { attr: "Order.qty", value: 20 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty > ?",
    binds: [20],
  },
  {
    id: "m-op-algebra-005 greaterThanEquals",
    op: { greaterThanEquals: { attr: "Order.qty", value: 20 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty >= ?",
    binds: [20],
  },
  {
    id: "m-op-algebra-006 lessThan",
    op: { lessThan: { attr: "Order.qty", value: 15 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty < ?",
    binds: [15],
  },
  {
    id: "m-op-algebra-007 lessThanEquals",
    op: { lessThanEquals: { attr: "Order.qty", value: 15 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty <= ?",
    binds: [15],
  },
  {
    id: "m-op-algebra-008 between",
    op: { between: { attr: "Order.price", lower: 20.0, upper: 50.75 } },
    sql: "select t0.id, t0.name from orders t0 where t0.price between ? and ?",
    binds: [20.0, 50.75],
  },

  // --- null ---
  {
    id: "m-op-algebra-009 isNull",
    op: { isNull: { attr: "Order.sku" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku is null",
    binds: [],
  },
  {
    id: "m-op-algebra-010 isNotNull",
    op: { isNotNull: { attr: "Order.sku" } },
    sql: "select t0.id, t0.name from orders t0 where not t0.sku is null",
    binds: [],
  },

  // --- string ---
  {
    id: "m-op-algebra-011 like",
    op: { like: { attr: "Order.sku", value: "A-%" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ?",
    binds: ["A-%"],
  },
  {
    id: "m-op-algebra-012 notLike",
    op: { notLike: { attr: "Order.sku", value: "A-%" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku not like ?",
    binds: ["A-%"],
  },
  {
    id: "m-op-algebra-013 startsWith",
    op: { startsWith: { attr: "Order.sku", value: "A-" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ?",
    binds: ["A-%"],
  },
  {
    id: "m-op-algebra-014 endsWith",
    op: { endsWith: { attr: "Order.sku", value: "00" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ?",
    binds: ["%00"],
  },
  {
    id: "m-op-algebra-015 contains+escape",
    op: { contains: { attr: "Order.sku", value: "50%" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ? escape ?",
    binds: ["%50\\%%", "\\"],
  },
  {
    id: "m-op-algebra-016 like caseInsensitive",
    op: { like: { attr: "Order.name", value: "ada", caseInsensitive: true } },
    sql: "select t0.id, t0.name from orders t0 where lower(t0.name) like lower(?)",
    binds: ["ada"],
  },
  {
    id: "m-op-algebra-017 contains caseInsensitive",
    op: { contains: { attr: "Order.name", value: "A", caseInsensitive: true } },
    sql: "select t0.id, t0.name from orders t0 where lower(t0.name) like lower(?)",
    binds: ["%a%"],
  },
  {
    id: "m-op-algebra-033 startsWith+escape",
    op: { startsWith: { attr: "Order.sku", value: "C_" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ? escape ?",
    binds: ["C\\_%", "\\"],
  },
  {
    id: "m-op-algebra-034 endsWith+escape",
    op: { endsWith: { attr: "Order.sku", value: "50%" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ? escape ?",
    binds: ["%50\\%", "\\"],
  },

  // --- membership ---
  {
    id: "m-op-algebra-018 in",
    op: { in: { attr: "Order.id", values: [1, 2, 42] } },
    sql: "select t0.id, t0.name from orders t0 where t0.id in (?, ?, ?)",
    binds: [1, 2, 42],
  },
  {
    id: "m-op-algebra-019 notIn",
    op: { notIn: { attr: "Order.id", values: [1, 2, 42] } },
    sql: "select t0.id, t0.name from orders t0 where not t0.id in (?, ?, ?)",
    binds: [1, 2, 42],
  },
  {
    id: "m-op-algebra-030 notIn null-excluded",
    op: { notIn: { attr: "Order.sku", values: ["A-100", "B-200"] } },
    sql: "select t0.id, t0.name from orders t0 where not t0.sku in (?, ?)",
    binds: ["A-100", "B-200"],
  },

  // --- boolean ---
  {
    id: "m-op-algebra-020 and",
    op: {
      and: {
        operands: [
          { eq: { attr: "Order.active", value: true } },
          { greaterThan: { attr: "Order.qty", value: 10 } },
        ],
      },
    },
    sql: "select t0.id, t0.name from orders t0 where t0.active = ? and t0.qty > ?",
    binds: [true, 10],
  },
  {
    id: "m-op-algebra-021 or",
    op: {
      or: {
        operands: [
          { lessThan: { attr: "Order.qty", value: 10 } },
          { greaterThan: { attr: "Order.qty", value: 25 } },
        ],
      },
    },
    sql: "select t0.id, t0.name from orders t0 where t0.qty < ? or t0.qty > ?",
    binds: [10, 25],
  },
  {
    id: "m-op-algebra-022 not",
    op: { not: { operand: { eq: { attr: "Order.active", value: true } } } },
    sql: "select t0.id, t0.name from orders t0 where not t0.active = ?",
    binds: [true],
  },
  {
    id: "m-op-algebra-023 none",
    op: { none: {} },
    sql: "select t0.id, t0.name from orders t0 where 1 = 0",
    binds: [],
  },
  {
    id: "m-op-algebra-031 and three operands",
    op: {
      and: {
        operands: [
          { eq: { attr: "Order.active", value: true } },
          { greaterThan: { attr: "Order.qty", value: 5 } },
          { lessThan: { attr: "Order.qty", value: 30 } },
        ],
      },
    },
    sql: "select t0.id, t0.name from orders t0 where t0.active = ? and t0.qty > ? and t0.qty < ?",
    binds: [true, 5, 30],
  },

  // --- group precedence (m-op-algebra-024 grouped vs m-op-algebra-025 ungrouped) ---
  {
    id: "m-op-algebra-024 group precedence grouped",
    op: {
      and: {
        operands: [
          {
            group: {
              operand: {
                or: {
                  operands: [
                    { greaterThanEquals: { attr: "Order.qty", value: 25 } },
                    { lessThanEquals: { attr: "Order.qty", value: 5 } },
                  ],
                },
              },
            },
          },
          { eq: { attr: "Order.active", value: true } },
        ],
      },
    },
    sql: "select t0.id, t0.name from orders t0 where (t0.qty >= ? or t0.qty <= ?) and t0.active = ?",
    binds: [25, 5, true],
  },
  {
    id: "m-op-algebra-025 group precedence ungrouped",
    op: {
      or: {
        operands: [
          { greaterThanEquals: { attr: "Order.qty", value: 25 } },
          {
            and: {
              operands: [
                { lessThanEquals: { attr: "Order.qty", value: 5 } },
                { eq: { attr: "Order.active", value: true } },
              ],
            },
          },
        ],
      },
    },
    sql: "select t0.id, t0.name from orders t0 where t0.qty >= ? or t0.qty <= ? and t0.active = ?",
    binds: [25, 5, true],
  },

  // --- directives ---
  {
    id: "m-op-algebra-026 orderBy+limit",
    op: {
      limit: {
        count: 2,
        operand: {
          orderBy: {
            keys: [{ attr: "Order.qty", direction: "desc" }],
            operand: { all: {} },
          },
        },
      },
    },
    sql: "select t0.id, t0.name from orders t0 order by t0.qty desc limit ?",
    binds: [2],
  },
  {
    id: "m-op-algebra-027 orderBy asc+limit",
    op: {
      limit: {
        count: 3,
        operand: {
          orderBy: {
            keys: [{ attr: "Order.id", direction: "asc" }],
            operand: { all: {} },
          },
        },
      },
    },
    sql: "select t0.id, t0.name from orders t0 order by t0.id asc limit ?",
    binds: [3],
  },
  {
    id: "m-op-algebra-032 orderBy multi-key+limit",
    op: {
      limit: {
        count: 2,
        operand: {
          orderBy: {
            keys: [
              { attr: "Order.active", direction: "desc" },
              { attr: "Order.qty", direction: "asc" },
            ],
            operand: { all: {} },
          },
        },
      },
    },
    sql: "select t0.id, t0.name from orders t0 order by t0.active desc, t0.qty asc limit ?",
    binds: [2],
  },
  {
    id: "m-op-algebra-028 distinct",
    op: { distinct: { operand: { all: {} } } },
    sql: "select distinct t0.active from orders t0",
    binds: [],
    projection: ["active"],
  },
  {
    // Q8 — the first test of the `desc nulls last` branch. `sku` is NULL-bearing, so
    // the descending order goes through the dialect's NULL-placement rule (Postgres
    // sorts NULLs first on `desc` by default, so an explicit `nulls last` restores
    // the canonical "NULLs last" order). The corpus has no NULL-bearing `desc` key,
    // so this branch is untested there — hence the hand-authored golden here.
    id: "Q8 orderBy desc nullable → nulls last",
    op: {
      orderBy: {
        keys: [{ attr: "Order.sku", direction: "desc" }],
        operand: { all: {} },
      },
    },
    sql: "select t0.id, t0.name from orders t0 order by t0.sku desc nulls last",
    binds: [],
  },

  // --- 3VL null exclusion (same SQL as m-op-algebra-003, NULL-bearing column) ---
  {
    id: "m-op-algebra-029 notEq null-excluded",
    op: { notEq: { attr: "Order.sku", value: "B-200" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku <> ?",
    binds: ["B-200"],
  },
];

describe("m-sql read algebra — emitted === golden", () => {
  it.each(CASES)("$id", ({ op, sql, binds, projection }) => {
    const result = emit(op, projection);
    expect(result.sql).toBe(sql);
    expect(result.binds).toEqual(binds);
  });
});

describe("type-aware bind coercion (carry-forward task 1)", () => {
  it("an int64 literal beyond Number.MAX_SAFE_INTEGER becomes its canonical string", () => {
    // The serde reader preserves the precision-unsafe token as its exact source
    // string; the compiler keeps it as the canonical base-10 string.
    const big = "9223372036854775807";
    const result = compile(
      parseOperation({ eq: { attr: "Order.id", value: big } }) as Operation,
      ordersResolver(),
      postgresDialect,
    );
    expect(result.sql).toBe("select t0.id, t0.name from orders t0 where t0.id = ?");
    expect(result.binds).toEqual([big]);
  });

  it("a float-safe int64 literal stays a JS number (matches binds: [42])", () => {
    const result = compile(
      parseOperation({ eq: { attr: "Order.id", value: 42 } }) as Operation,
      ordersResolver(),
      postgresDialect,
    );
    expect(result.binds).toEqual([42]);
    expect(typeof result.binds[0]).toBe("number");
  });

  it("a precision-unsafe decimal(18,2) literal becomes its scale-aware string", () => {
    // 1234567890123456.78 cannot be held exactly by a JS double; the reader
    // preserves the source, and the compiler renders it at scale 2, exactly.
    const exact = "1234567890123456.78";
    const result = compile(
      parseOperation({ eq: { attr: "Order.price", value: exact } }) as Operation,
      ordersResolver(),
      postgresDialect,
    );
    expect(result.binds).toEqual(["1234567890123456.78"]);
  });

  it("a float-safe decimal literal keeps its authored JS number (matches binds: [20])", () => {
    const result = compile(
      parseOperation({ between: { attr: "Order.price", lower: 20.0, upper: 50.75 } }) as Operation,
      ordersResolver(),
      postgresDialect,
    );
    expect(result.binds).toEqual([20.0, 50.75]);
  });

  it("rejects a non-safe JS-number int64 (precision already lost; must be authored as a string)", () => {
    // The serde reader preserves a precision-unsafe int64 token as a STRING, so a
    // non-safe JS number reaching coercion has already rounded — stringifying it
    // would bless a lossy value. The coercer fails loud instead. `MAX_SAFE + 2`
    // is exactly representable as a double yet `Number.isSafeInteger` is false.
    const unsafe = Number.MAX_SAFE_INTEGER + 2;
    expect(Number.isSafeInteger(unsafe)).toBe(false);
    expect(() => coerceBind(unsafe, "int64")).toThrow(/exceeds the IEEE-754 safe-integer range/);
  });

  it("keeps a float-safe JS-number int64 as the same number (the safe path is unchanged)", () => {
    expect(coerceBind(42, "int64")).toBe(42);
    expect(typeof coerceBind(42, "int64")).toBe("number");
  });
});

describe("root/child `from` table quoting routes through the dialect (Gap 2)", () => {
  /**
   * A resolver whose root table is the reserved word `order` (unquoted, per the
   * `SchemaResolver.rootTable` contract — the alias map is keyed by the unquoted
   * name), proving `compile` — not the resolver — quotes it via
   * `dialect.quoteIdentifier` right before splicing it into the `from` clause.
   */
  function reservedRootResolver(): SchemaResolver {
    return {
      resolveAttribute(ref: string): ResolvedColumn {
        const attrName = ref.slice(ref.indexOf(".") + 1);
        const attr = ORDERS[attrName];
        if (!attr) {
          throw new Error(`unknown orders attribute '${ref}'`);
        }
        return { table: "order", column: quoteIdentifier(attr.column), type: attr.type };
      },
      resolveRelationship(ref: string): ResolvedRelationship {
        throw new Error(`not exercised by this test: '${ref}'`);
      },
      rootTable: () => "order",
      rootProjection: () => [{ column: quoteIdentifier("id") }],
    };
  }

  it('quotes a reserved-word root table (Postgres double-quoted `from "order" t0`)', () => {
    const result = compile(
      parseOperation({ all: {} }) as Operation,
      reservedRootResolver(),
      postgresDialect,
    );
    expect(result.sql).toBe('select t0.id from "order" t0');
  });

  /**
   * A resolver whose EXISTS-child table is the reserved word `order`, proving the
   * semi-join's `from` (deep inside `compilePredicate`, which carries no separate
   * `dialect` parameter) also routes through the dialect via `ctx.dialect`.
   */
  function reservedChildResolver(): SchemaResolver {
    return {
      resolveAttribute(ref: string): ResolvedColumn {
        const attrName = ref.slice(ref.indexOf(".") + 1);
        const attr = ORDERS[attrName];
        if (!attr) {
          throw new Error(`unknown orders attribute '${ref}'`);
        }
        return { table: "orders", column: quoteIdentifier(attr.column), type: attr.type };
      },
      resolveRelationship(_ref: string): ResolvedRelationship {
        return {
          childTable: "order",
          childColumn: quoteIdentifier("id"),
          parentColumn: quoteIdentifier("id"),
        };
      },
      rootTable: () => "orders",
      rootProjection: () => [{ column: quoteIdentifier("id") }],
    };
  }

  it('quotes a reserved-word EXISTS-child table (Postgres double-quoted `from "order" t1`)', () => {
    const result = compile(
      parseOperation({ exists: { rel: "Order.items" } }) as Operation,
      reservedChildResolver(),
      postgresDialect,
    );
    expect(result.sql).toBe(
      'select t0.id from orders t0 where exists (select 1 from "order" t1 where t1.id = t0.id)',
    );
  });
});
