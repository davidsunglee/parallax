/**
 * M3 read-algebra compiler unit tests (Docker-free).
 *
 * Drives the canonical-by-construction `compile` visitor directly over a small,
 * hand-built `SchemaResolver` for the `orders` model, asserting `emitted ===
 * golden` + binds for every single-entity read-algebra fragment the corpus pins
 * in the 02xx family — comparison, null, string (incl. wildcard escaping +
 * caseInsensitive), membership, boolean precedence (the `0222`/`0223` grouped vs
 * ungrouped pair), and the result directives (`orderBy` / `limit` / `distinct`).
 * The whole-corpus compile lane (driving the real adapter path over the metamodel
 * reader) lives in `@parallax/conformance`'s `read-algebra.test.ts`; this file
 * pins the compiler's emission contract in isolation, including the carry-forward
 * type-aware bind coercion for precision-unsafe int64 / decimal literals.
 */

import { quoteIdentifier } from "@parallax/dialect";
import { type Operation, parseOperation } from "@parallax/operation";
import { describe, expect, it } from "vitest";
import {
  type Bind,
  coerceBind,
  compile,
  type ResolvedColumn,
  type SchemaResolver,
} from "../src/index.js";

/** The `orders` columns the 02xx read algebra ranges over (name → column + M0 type). */
const ORDERS: Record<string, { column: string; type: string }> = {
  id: { column: "id", type: "int64" },
  name: { column: "name", type: "string" },
  sku: { column: "sku", type: "string" },
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
      return { table: "orders", column: quoteIdentifier(attr.column), type: attr.type };
    },
    rootTable: () => "orders",
    rootProjection: () => projection.map(quoteIdentifier),
  };
}

/** Compile a YAML-authored operation (validated through the schema) over `orders`. */
function emit(
  op: unknown,
  projection?: readonly string[],
): { sql: string; binds: readonly Bind[] } {
  const operation = parseOperation(op) as Operation;
  return compile(operation, ordersResolver(projection));
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
    id: "0201 notEq",
    op: { notEq: { attr: "Order.qty", value: 20 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty <> ?",
    binds: [20],
  },
  {
    id: "0202 greaterThan",
    op: { greaterThan: { attr: "Order.qty", value: 20 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty > ?",
    binds: [20],
  },
  {
    id: "0203 greaterThanEquals",
    op: { greaterThanEquals: { attr: "Order.qty", value: 20 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty >= ?",
    binds: [20],
  },
  {
    id: "0204 lessThan",
    op: { lessThan: { attr: "Order.qty", value: 15 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty < ?",
    binds: [15],
  },
  {
    id: "0205 lessThanEquals",
    op: { lessThanEquals: { attr: "Order.qty", value: 15 } },
    sql: "select t0.id, t0.name from orders t0 where t0.qty <= ?",
    binds: [15],
  },
  {
    id: "0206 between",
    op: { between: { attr: "Order.price", lower: 20.0, upper: 50.75 } },
    sql: "select t0.id, t0.name from orders t0 where t0.price between ? and ?",
    binds: [20.0, 50.75],
  },

  // --- null ---
  {
    id: "0207 isNull",
    op: { isNull: { attr: "Order.sku" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku is null",
    binds: [],
  },
  {
    id: "0208 isNotNull",
    op: { isNotNull: { attr: "Order.sku" } },
    sql: "select t0.id, t0.name from orders t0 where not t0.sku is null",
    binds: [],
  },

  // --- string ---
  {
    id: "0209 like",
    op: { like: { attr: "Order.sku", value: "A-%" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ?",
    binds: ["A-%"],
  },
  {
    id: "0210 notLike",
    op: { notLike: { attr: "Order.sku", value: "A-%" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku not like ?",
    binds: ["A-%"],
  },
  {
    id: "0211 startsWith",
    op: { startsWith: { attr: "Order.sku", value: "A-" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ?",
    binds: ["A-%"],
  },
  {
    id: "0212 endsWith",
    op: { endsWith: { attr: "Order.sku", value: "00" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ?",
    binds: ["%00"],
  },
  {
    id: "0213 contains+escape",
    op: { contains: { attr: "Order.sku", value: "50%" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ? escape ?",
    binds: ["%50\\%%", "\\"],
  },
  {
    id: "0214 like caseInsensitive",
    op: { like: { attr: "Order.name", value: "ada", caseInsensitive: true } },
    sql: "select t0.id, t0.name from orders t0 where lower(t0.name) like lower(?)",
    binds: ["ada"],
  },
  {
    id: "0215 contains caseInsensitive",
    op: { contains: { attr: "Order.name", value: "A", caseInsensitive: true } },
    sql: "select t0.id, t0.name from orders t0 where lower(t0.name) like lower(?)",
    binds: ["%a%"],
  },
  {
    id: "0231 startsWith+escape",
    op: { startsWith: { attr: "Order.sku", value: "C_" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ? escape ?",
    binds: ["C\\_%", "\\"],
  },
  {
    id: "0232 endsWith+escape",
    op: { endsWith: { attr: "Order.sku", value: "50%" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku like ? escape ?",
    binds: ["%50\\%", "\\"],
  },

  // --- membership ---
  {
    id: "0216 in",
    op: { in: { attr: "Order.id", values: [1, 2, 42] } },
    sql: "select t0.id, t0.name from orders t0 where t0.id in (?, ?, ?)",
    binds: [1, 2, 42],
  },
  {
    id: "0217 notIn",
    op: { notIn: { attr: "Order.id", values: [1, 2, 42] } },
    sql: "select t0.id, t0.name from orders t0 where not t0.id in (?, ?, ?)",
    binds: [1, 2, 42],
  },
  {
    id: "0228 notIn null-excluded",
    op: { notIn: { attr: "Order.sku", values: ["A-100", "B-200"] } },
    sql: "select t0.id, t0.name from orders t0 where not t0.sku in (?, ?)",
    binds: ["A-100", "B-200"],
  },

  // --- boolean ---
  {
    id: "0218 and",
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
    id: "0219 or",
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
    id: "0220 not",
    op: { not: { operand: { eq: { attr: "Order.active", value: true } } } },
    sql: "select t0.id, t0.name from orders t0 where not t0.active = ?",
    binds: [true],
  },
  {
    id: "0221 none",
    op: { none: {} },
    sql: "select t0.id, t0.name from orders t0 where 1 = 0",
    binds: [],
  },
  {
    id: "0229 and three operands",
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

  // --- group precedence (0222 grouped vs 0223 ungrouped) ---
  {
    id: "0222 group precedence grouped",
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
    id: "0223 group precedence ungrouped",
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
    id: "0224 orderBy+limit",
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
    id: "0225 orderBy asc+limit",
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
    id: "0230 orderBy multi-key+limit",
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
    id: "0226 distinct",
    op: { distinct: { operand: { all: {} } } },
    sql: "select distinct t0.active from orders t0",
    binds: [],
    projection: ["active"],
  },

  // --- 3VL null exclusion (same SQL as 0201, NULL-bearing column) ---
  {
    id: "0227 notEq null-excluded",
    op: { notEq: { attr: "Order.sku", value: "B-200" } },
    sql: "select t0.id, t0.name from orders t0 where t0.sku <> ?",
    binds: ["B-200"],
  },
];

describe("M3 read algebra — emitted === golden", () => {
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
    );
    expect(result.sql).toBe("select t0.id, t0.name from orders t0 where t0.id = ?");
    expect(result.binds).toEqual([big]);
  });

  it("a float-safe int64 literal stays a JS number (matches binds: [42])", () => {
    const result = compile(
      parseOperation({ eq: { attr: "Order.id", value: 42 } }) as Operation,
      ordersResolver(),
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
    );
    expect(result.binds).toEqual(["1234567890123456.78"]);
  });

  it("a float-safe decimal literal keeps its authored JS number (matches binds: [20])", () => {
    const result = compile(
      parseOperation({ between: { attr: "Order.price", lower: 20.0, upper: 50.75 } }) as Operation,
      ordersResolver(),
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
