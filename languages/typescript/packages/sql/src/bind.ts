/**
 * Type-aware literal coercion at the M3 compile boundary.
 *
 * A predicate literal arrives from the serde reader already normalized: a
 * float-**safe** authored number (`42`, `20.00`, `50.75`) is a JS `number`, while
 * a precision-**unsafe** int64 / decimal token the reader could not represent as
 * a double (`9223372036854775807`, `1234567890123456.78`) is preserved as its
 * exact source **string** (`serde/canonical.ts` `parseYamlLossless`). This module
 * resolves each literal against its M0 neutral type and normalizes it to the
 * canonical wire form the conformance contract compares (§3.2.1):
 *
 *  - `int64`   → keep a float-safe JS number as-is; a preserved source string or
 *               a `bigint` → canonical base-10 string. A non-safe JS number is
 *               rejected (it lost precision before reaching here; the reader
 *               preserves unsafe int64 tokens as strings, so this never fires for
 *               serde-produced literals).
 *  - `decimal(p,s)` → keep a float-safe JS number as-is; a preserved source
 *               string → scale-aware canonical decimal string (`toFixedString(s)`).
 *  - every other type (int32 / float / boolean / string / uuid / date / time /
 *               timestamp / bytes) → pass through unchanged (the reader already
 *               produced the wire form, or there is no precision concern).
 *
 * Keeping a float-safe `42` as a JS number is the Phase-3 wire-form decision the
 * corpus goldens assume (`binds: [42]` is a JSON number); the string path only
 * engages for values a double cannot hold, so no in-slice golden changes.
 */
import { ParallaxDecimal, parseDecimalType } from "@parallax/core";
import type { Bind } from "./compile.js";

/** Largest IEEE-754 double-safe integer magnitude, `2^53 - 1`. */
const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER);

/**
 * Normalize a predicate literal to its canonical wire form against the M0
 * neutral type of the attribute it compares. `null` is a SQL null and passes
 * through untouched regardless of type.
 */
export function coerceBind(value: Bind, neutralType: string): Bind {
  if (value === null) {
    return null;
  }

  const decimal = parseDecimalType(neutralType);
  if (decimal) {
    return coerceDecimal(value, decimal.scale);
  }
  if (neutralType === "int64") {
    return coerceInt64(value);
  }
  // int32 / float* keep their JS-number form; string / uuid / boolean / temporal
  // wire forms are already produced by the serde reader. No coercion needed.
  return value;
}

/**
 * Coerce an `int64` literal. A float-safe JS integer stays a JS number (the
 * authored `42` ⇒ `42`); a `bigint` or a source string the reader preserved
 * (precision-unsafe) becomes the canonical base-10 string.
 *
 * A non-safe JS `number` is rejected, not stringified. The serde reader
 * (`parseYamlLossless`) guarantees a precision-unsafe int64 token arrives as a
 * STRING, so a non-safe `number` reaching here has ALREADY lost precision before
 * coercion — `BigInt(value).toString()` would only bless a rounded value.
 * Failing loud forces such a literal to be authored as a string instead.
 */
function coerceInt64(value: Bind): Bind {
  if (typeof value === "number") {
    if (Number.isSafeInteger(value)) {
      return value;
    }
    throw new Error(
      `int64 literal ${value} exceeds the IEEE-754 safe-integer range ` +
        `(±${Number.MAX_SAFE_INTEGER}); author it as a string to preserve precision`,
    );
  }
  if (typeof value === "string") {
    // A preserved exact source string for an out-of-range int64: keep it as the
    // canonical base-10 string (BigInt validates and normalizes it).
    return BigInt(value).toString();
  }
  return value;
}

/**
 * Coerce a `decimal(p,s)` literal. A float-safe authored JS number stays a JS
 * number (the corpus authors `20.00`, which the reader produced as `20`, and the
 * test reads the same number from the same serde — they compare equal). A source
 * string the reader preserved (precision-unsafe) becomes the scale-aware
 * canonical decimal string, exact in decimal space.
 */
function coerceDecimal(value: Bind, scale: number): Bind {
  if (typeof value === "string") {
    return ParallaxDecimal.from(value).toFixedString(scale);
  }
  return value;
}

/** Whether a `bigint` exceeds the IEEE-754 double-safe integer range. */
export function exceedsSafeInteger(value: bigint): boolean {
  return value > MAX_SAFE || value < -MAX_SAFE;
}
