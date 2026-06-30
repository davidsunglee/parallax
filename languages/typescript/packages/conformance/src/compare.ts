/**
 * Adapter-boundary row comparison rules (M12, the case's row comparison rules).
 *
 * A `run` envelope reports observed `rows` in the **neutral wire form** (§2.2.1):
 * an `int64` arrives as its canonical base-10 string (`"42"`), an exact
 * `decimal(p,s)` as its scale-aware string (`"20.00"`), a `boolean` as a JS
 * boolean, a `timestamp` as its microsecond UTC string. A case's `expectedRows`
 * are authored values parsed by the same serde (numbers / strings / booleans).
 * Comparing them faithfully needs the M12 rules, NOT JS `==`:
 *
 *  - **Exact decimal.** Decimal-looking values compare in decimal space
 *    (`ParallaxDecimal`), never as binary floats, so `"20.00"` equals `20` and a
 *    money value never drifts.
 *  - **Boolean is never `== 1`.** A boolean compares only to a boolean; `true`
 *    never equals `1` and `false` never equals `0` / `""`.
 *  - **Microsecond timestamps.** Instant strings compare to microsecond
 *    precision (exact string equality on the canonical µs form).
 *  - **Order-insensitive row-set equality.** A read's rows are a SET: the
 *    observed and expected multisets must match regardless of order (the corpus
 *    makes ordering observable through membership + `limit`, never row order).
 *
 * The comparator lives in the harness (not the runner) because the runner is a
 * pure observation **producer**; grading observed-vs-expected is the harness's
 * job, shared by the run-lane tests and any external runner.
 */
import { ParallaxDecimal } from "@parallax/core";

/** A materialized row keyed by output column name. */
type Row = Record<string, unknown>;

/** The outcome of comparing an observed row set against the expected one. */
export interface RowSetComparison {
  /** True when the two row sets are equal as order-insensitive multisets. */
  readonly equal: boolean;
  /** A human-readable reason when they differ (empty when equal). */
  readonly reason: string;
}

/**
 * Compare two row sets as **order-insensitive multisets** under the M12 scalar
 * rules. Rows match when they have the same column keys and every column's
 * values are scalar-equal; the sets match when each observed row pairs with a
 * distinct expected row (greedy one-to-one matching, correct for the small,
 * duplicate-light corpus row sets).
 */
export function compareRowSet(
  observed: readonly Row[],
  expected: readonly Row[],
): RowSetComparison {
  if (observed.length !== expected.length) {
    return {
      equal: false,
      reason: `row count differs: observed ${observed.length}, expected ${expected.length}`,
    };
  }
  const remaining = expected.map((row) => row);
  for (const obs of observed) {
    const index = remaining.findIndex((exp) => rowsEqual(obs, exp));
    if (index === -1) {
      return { equal: false, reason: `no expected row matches observed ${JSON.stringify(obs)}` };
    }
    remaining.splice(index, 1);
  }
  return { equal: true, reason: "" };
}

/** Two rows are equal when they have the same keys and scalar-equal values. */
function rowsEqual(left: Row, right: Row): boolean {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  for (const key of leftKeys) {
    if (!(key in right)) {
      return false;
    }
    if (!scalarsEqual(left[key], right[key])) {
      return false;
    }
  }
  return true;
}

/**
 * Scalar equality under the M12 rules, reconciling the wire form of an observed
 * value with the authored form of an expected value:
 *
 *  - `null` matches only `null`.
 *  - booleans compare only to booleans (never `== 1`).
 *  - a number / numeric string compares in **decimal space** (exact), so an
 *    int64 wire string `"42"` equals the authored number `42` and a decimal wire
 *    string `"20.00"` equals `20`.
 *  - everything else compares as exact strings (timestamps to µs, uuid, text,
 *    hex bytes, dates, times).
 */
export function scalarsEqual(observed: unknown, expected: unknown): boolean {
  if (observed === null || expected === null) {
    return observed === expected;
  }
  // Boolean is its own type: never coerced to/from 1/0.
  if (typeof observed === "boolean" || typeof expected === "boolean") {
    return observed === expected;
  }

  const obsNumeric = asDecimal(observed);
  const expNumeric = asDecimal(expected);
  if (obsNumeric !== undefined && expNumeric !== undefined) {
    return obsNumeric.equals(expNumeric);
  }

  // Non-numeric (text / uuid / timestamp µs string / date / time / hex bytes):
  // exact string equality on the canonical wire form.
  return String(observed) === String(expected);
}

/**
 * Interpret a value as an exact decimal when it is a finite number, a bigint, or
 * a numeric string; otherwise `undefined` (it is genuinely textual). A boolean is
 * never numeric (handled before this is reached). A non-numeric string (e.g. a
 * timestamp `2024-…`) returns `undefined` so it compares as text.
 */
function asDecimal(value: unknown): ParallaxDecimal | undefined {
  if (typeof value === "bigint") {
    return ParallaxDecimal.from(value);
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? ParallaxDecimal.from(String(value)) : undefined;
  }
  if (typeof value === "string" && isNumericString(value)) {
    return ParallaxDecimal.from(value);
  }
  return undefined;
}

/** A plain signed decimal token (no exponent, no date/time punctuation). */
function isNumericString(text: string): boolean {
  return /^[+-]?(\d+\.?\d*|\.\d+)$/.test(text.trim());
}
