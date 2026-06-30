/**
 * M12 adapter-boundary comparison unit tests (Docker-free).
 *
 * Pins the `scalarsEqual` + `compareRowSet` contract directly, in isolation from
 * the Docker-gated run lane (`@parallax/typescript`'s `read-run.test.ts`), which
 * is the only place the comparator was previously exercised. The central
 * invariant locked in here is the **genuine-numeric discriminator**: a numeric
 * wire STRING reconciles against a genuine `number` / `bigint` in decimal space
 * (the §2.2.1 int64 / decimal wire form vs an authored JS number), but two
 * strings compare as EXACT canonical strings — so a textual / projection bug
 * (`"042"` vs `"42"`) surfaces instead of being masked. This mirrors the Python
 * oracle, whose `_to_decimal` never decimalizes a string.
 */
import { describe, expect, it } from "vitest";
import { compareRowSet, scalarsEqual } from "../src/index.js";

describe("scalarsEqual — genuine-numeric reconciliation vs exact-string", () => {
  it("reconciles an int64 wire string against a genuine number (string vs number)", () => {
    // §2.2.1: an int64 arrives as its canonical base-10 string; the case authors
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
});
