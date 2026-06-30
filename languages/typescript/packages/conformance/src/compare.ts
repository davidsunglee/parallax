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
 *  - **Exact decimal (genuine-numeric reconciliation).** When at least one side
 *    is a genuine `number` / `bigint`, both sides compare in decimal space
 *    (`ParallaxDecimal`), never as binary floats, so a numeric wire string
 *    `"20.00"` equals the authored `20` and a money value never drifts. Two
 *    strings are NOT decimalized — they compare as exact canonical strings (the
 *    Python oracle never decimalizes a string), so a textual difference such as
 *    `"042"` vs `"42"` surfaces rather than being masked.
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
 *  - when at least one side is a **genuine** `number` / `bigint`, both sides
 *    compare in **decimal space** (exact). This is the int64 / decimal wire-form
 *    reconciliation: TypeScript's neutral wire form (§2.2.1) carries an `int64`
 *    or `decimal(p,s)` as a **string** (`"42"`, `"20.00"`), whereas the case's
 *    `expectedRows` author the same value as a JS `number` (`42`, `20`). The
 *    genuine number/bigint on one side is the signal that the numeric string on
 *    the other side denotes that same number, so `"42"` equals `42` and `"20.00"`
 *    equals `20`, never via a binary float.
 *  - when **both** sides are strings, compare as **exact canonical strings**.
 *    This mirrors the Python oracle exactly (see below) and is deliberately NOT
 *    decimal: two *different* canonical numeric wire strings (`"042"` vs `"42"`,
 *    `"20.0"` vs `"20.00"`) must compare UNEQUAL so a textual / projection /
 *    serialization bug surfaces instead of being masked.
 *  - everything else compares as exact strings (timestamps to µs, uuid, text,
 *    hex bytes, dates, times).
 *
 * **Why the genuine-numeric discriminator (oracle fidelity).** The Python oracle
 * (`reference_harness.case_runner._scalars_equal` / `_to_decimal`) decimalizes
 * ONLY native `int` / `float` / `Decimal`, never a `str`; two strings fall
 * through to Python `==`. Python's DB driver returns native `int` / `Decimal`,
 * so there is never a numeric *string* to reconcile on its side. TypeScript's
 * driver path produces the canonical *string* wire form instead, so the TS
 * comparator must decimalize a numeric string — but ONLY to reconcile it against
 * a genuine numeric counterpart. With two strings, exact-string equality is the
 * faithful match for the oracle's `str == str`.
 *
 * **Forward note.** Full column-type-aware comparison — threading the projected
 * `column -> M0 type` so a `string` column is graded as text even against a
 * numeric-looking value — lands with the Phase 5 projection-metadata rework. The
 * genuine-numeric rule is the correct intermediate: it matches the oracle for the
 * current / near-term corpus (numeric columns observed as numeric wire strings,
 * everything else textual), and exact-string equality of two canonical numeric
 * wire strings is the documented Phase-8 boundary for unsafe scalar round-trip.
 */
export function scalarsEqual(observed: unknown, expected: unknown): boolean {
  if (observed === null || expected === null) {
    return observed === expected;
  }
  // Boolean is its own type: never coerced to/from 1/0.
  if (typeof observed === "boolean" || typeof expected === "boolean") {
    return observed === expected;
  }

  // Decimal space only reconciles a numeric STRING against a genuine number /
  // bigint. When neither side is a genuine number/bigint (both are strings),
  // fall through to exact-string equality — matching the Python oracle, which
  // never decimalizes strings and so compares two strings with `==`.
  if (isGenuineNumber(observed) || isGenuineNumber(expected)) {
    const obsNumeric = asDecimal(observed);
    const expNumeric = asDecimal(expected);
    if (obsNumeric !== undefined && expNumeric !== undefined) {
      return obsNumeric.equals(expNumeric);
    }
  }

  // Non-numeric, or two strings (text / uuid / timestamp µs string / date /
  // time / hex bytes / two canonical numeric wire strings): exact string
  // equality on the canonical wire form.
  return String(observed) === String(expected);
}

/** A genuine JS numeric value (a finite `number` or a `bigint`), not a string. */
function isGenuineNumber(value: unknown): boolean {
  return typeof value === "bigint" || (typeof value === "number" && Number.isFinite(value));
}

/**
 * Interpret a value as an exact decimal when it is a finite number, a bigint, or
 * a numeric string; otherwise `undefined` (it is genuinely textual). A boolean is
 * never numeric (handled before this is reached). A non-numeric string (e.g. a
 * timestamp `2024-…`) returns `undefined` so it compares as text.
 *
 * A numeric string is decimalized here only after the caller has established that
 * the OTHER operand is a genuine number/bigint — so this reconciles a wire string
 * against a native number, never two strings against each other.
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
