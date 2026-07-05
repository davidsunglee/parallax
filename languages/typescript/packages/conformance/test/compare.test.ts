/**
 * M12 adapter-boundary comparison unit tests (Docker-free).
 *
 * Pins the `scalarsEqual` + `compareRowSet` contract directly, in isolation from
 * the Docker-gated Postgres full M12 profile (`@parallax/typescript`'s
 * `slice-run.test.ts`). The central
 * invariant locked in here is the **genuine-numeric discriminator**: a numeric
 * wire STRING reconciles against a genuine `number` / `bigint` in decimal space
 * (the §3.2.1 int64 / decimal wire form vs an authored JS number), but two
 * strings compare as EXACT canonical strings — so a textual / projection bug
 * (`"042"` vs `"42"`) surfaces instead of being masked. This mirrors the Python
 * oracle, whose `_to_decimal` never decimalizes a string.
 */
import { describe, expect, it } from "vitest";
import { compareGraph, compareRowSet, scalarsEqual } from "../src/index.js";

describe("scalarsEqual — genuine-numeric reconciliation vs exact-string", () => {
  it("reconciles an int64 wire string against a genuine number (string vs number)", () => {
    // §3.2.1: an int64 arrives as its canonical base-10 string; the case authors
    // the same value as a JS number. They denote the same number.
    expect(scalarsEqual("42", 42)).toBe(true);
    expect(scalarsEqual(42, "42")).toBe(true);
  });

  it("reconciles a decimal wire string against a genuine number, scale-insensitively", () => {
    // A decimal(p,s) wire string `"20.00"` denotes the authored number `20`.
    expect(scalarsEqual("20.00", 20)).toBe(true);
    expect(scalarsEqual(20, "20.00")).toBe(true);
    expect(scalarsEqual("20.50", 20.5)).toBe(true);
  });

  it("reconciles a bigint against a numeric string", () => {
    expect(scalarsEqual(42n, "42")).toBe(true);
    expect(scalarsEqual("9007199254740993", 9007199254740993n)).toBe(true);
  });

  it("compares two DIFFERENT numeric wire strings as UNEQUAL (masking fixed: 042 vs 42)", () => {
    // Both sides are strings ⇒ exact canonical-string equality, never decimal.
    // A leading-zero textual difference must surface, not be masked.
    expect(scalarsEqual("042", "42")).toBe(false);
  });

  it("compares two scale-divergent decimal wire strings as UNEQUAL (masking fixed: 20.0 vs 20.00)", () => {
    // Two strings ⇒ exact string compare. A scale/serialization difference
    // surfaces instead of being decimalized away.
    expect(scalarsEqual("20.0", "20.00")).toBe(false);
  });

  it("compares two IDENTICAL numeric wire strings as equal", () => {
    expect(scalarsEqual("42", "42")).toBe(true);
    expect(scalarsEqual("20.00", "20.00")).toBe(true);
  });

  it("compares text against text exactly (string vs string)", () => {
    expect(scalarsEqual("hello", "hello")).toBe(true);
    expect(scalarsEqual("hello", "world")).toBe(false);
  });

  it("never equates a boolean with 1 / 0 (boolean is its own type)", () => {
    expect(scalarsEqual(true, true)).toBe(true);
    expect(scalarsEqual(false, false)).toBe(true);
    expect(scalarsEqual(true, 1)).toBe(false);
    expect(scalarsEqual(true, "1")).toBe(false);
    expect(scalarsEqual(false, 0)).toBe(false);
    expect(scalarsEqual(false, "")).toBe(false);
  });

  it("matches null only with null", () => {
    expect(scalarsEqual(null, null)).toBe(true);
    expect(scalarsEqual(null, 0)).toBe(false);
    expect(scalarsEqual(null, "")).toBe(false);
    expect(scalarsEqual(null, "null")).toBe(false);
    expect(scalarsEqual(0, null)).toBe(false);
  });

  it("compares non-numeric strings (timestamp µs / uuid / date) as exact text", () => {
    expect(scalarsEqual("2024-01-02T03:04:05.000006Z", "2024-01-02T03:04:05.000006Z")).toBe(true);
    expect(scalarsEqual("2024-01-02T03:04:05.000006Z", "2024-01-02T03:04:05.000007Z")).toBe(false);
  });
});

describe("scalarsEqual — type-aware grading (carry-forward b)", () => {
  it("grades a TEXTUAL column as exact text, even against a numeric-looking value", () => {
    // A `string`-typed column: `"042"` is text, never decimalized to 42, even
    // though the fallback discriminator would reconcile a numeric string against
    // a genuine number. The column type is authoritative.
    expect(scalarsEqual("042", 42, "string")).toBe(false);
    expect(scalarsEqual("042", "42", "string")).toBe(false);
    expect(scalarsEqual("A-100", "A-100", "string")).toBe(true);
  });

  it("grades a textual column's numeric-looking string against its own text form", () => {
    // Two identical text values match; the string form of a number matches the
    // same text ("42" == String(42)).
    expect(scalarsEqual("42", "42", "string")).toBe(true);
    expect(scalarsEqual(42, "42", "string")).toBe(true);
  });

  it("grades a NUMERIC column in decimal space even when BOTH sides are strings", () => {
    // `decimal(18,2)`/`int64` columns reconcile in decimal space regardless of
    // which side is the wire string — so `"20.0"` and `"20.00"` are equal here
    // (unlike the fallback, which compares two strings exactly).
    expect(scalarsEqual("20.0", "20.00", "decimal(18,2)")).toBe(true);
    expect(scalarsEqual("42", 42, "int64")).toBe(true);
    expect(scalarsEqual("20.00", 20, "decimal(18,2)")).toBe(true);
    expect(scalarsEqual("9007199254740993", 9007199254740993n, "int64")).toBe(true);
  });

  it("a boolean column is still never == 1, with or without a column type", () => {
    expect(scalarsEqual(true, 1, "boolean")).toBe(false);
    expect(scalarsEqual(true, true, "boolean")).toBe(true);
  });

  it("null matches only null regardless of the column type", () => {
    expect(scalarsEqual(null, null, "string")).toBe(true);
    expect(scalarsEqual(null, 0, "int64")).toBe(false);
  });
});

describe("compareRowSet — order-insensitive multiset under the scalar rules", () => {
  it("matches equal row sets regardless of order, reconciling wire strings", () => {
    const observed = [
      { id: "1", price: "20.00", active: true },
      { id: "2", price: "5.50", active: false },
    ];
    const expected = [
      { id: 2, price: 5.5, active: false },
      { id: 1, price: 20, active: true },
    ];
    expect(compareRowSet(observed, expected).equal).toBe(true);
  });

  it("reports a row-count mismatch", () => {
    const result = compareRowSet([{ id: "1" }], []);
    expect(result.equal).toBe(false);
    expect(result.reason).toContain("row count differs");
  });

  it("reports an unmatched row (masking fixed: 042 must not match 42)", () => {
    const result = compareRowSet([{ sku: "042" }], [{ sku: "42" }]);
    expect(result.equal).toBe(false);
    expect(result.reason).toContain("no expected row matches");
  });

  it("treats two textual rows as unequal when a string column differs", () => {
    const result = compareRowSet([{ name: "Ada" }], [{ name: "ada" }]);
    expect(result.equal).toBe(false);
  });

  it("grades columns by their M0 type when a type map is supplied", () => {
    const types = { id: "int64", sku: "string", price: "decimal(18,2)" };
    // sku is textual: "042" must NOT collapse to 42 even though it looks numeric.
    const bad = compareRowSet(
      [{ id: "1", sku: "042", price: "20.00" }],
      [{ id: 1, sku: "42", price: 20 }],
      types,
    );
    expect(bad.equal).toBe(false);
    // With the matching textual sku, the numeric columns still reconcile.
    const good = compareRowSet(
      [{ id: "1", sku: "42", price: "20.00" }],
      [{ id: 1, sku: "42", price: 20 }],
      types,
    );
    expect(good.equal).toBe(true);
  });
});

describe("compareGraph — structural graph equality under the scalar rules", () => {
  it("matches a decorated to-many graph regardless of child list order", () => {
    const types = { id: "int64", name: "string", order_id: "int64", sku: "string" };
    const observed = {
      Order: [
        {
          id: "1",
          name: "Ada",
          items: [
            { id: "11", order_id: "1", sku: "A-100" },
            { id: "12", order_id: "1", sku: "B-200" },
          ],
        },
      ],
    };
    const expected = {
      Order: [
        {
          id: 1,
          name: "Ada",
          items: [
            { id: 12, order_id: 1, sku: "B-200" },
            { id: 11, order_id: 1, sku: "A-100" },
          ],
        },
      ],
    };
    expect(compareGraph(observed, expected, types).equal).toBe(true);
  });

  it("matches childless parents (empty to-many list) and to-one null peers", () => {
    const observed = {
      Order: [
        { id: "3", name: "ada", items: [] },
        { id: "4", name: "Margaret", parent: null },
      ],
    };
    const expected = {
      Order: [
        { id: 4, name: "Margaret", parent: null },
        { id: 3, name: "ada", items: [] },
      ],
    };
    expect(compareGraph(observed, expected).equal).toBe(true);
  });

  it("reports a mismatch when a child scalar differs", () => {
    const observed = { Order: [{ id: "1", items: [{ id: "11", sku: "A-100" }] }] };
    const expected = { Order: [{ id: 1, items: [{ id: 11, sku: "B-999" }] }] };
    const result = compareGraph(observed, expected, { sku: "string" });
    expect(result.equal).toBe(false);
  });

  it("reports differing root entities", () => {
    const result = compareGraph({ Order: [] }, { OrderItem: [] });
    expect(result.equal).toBe(false);
    expect(result.reason).toContain("graph root entities differ");
  });
});
