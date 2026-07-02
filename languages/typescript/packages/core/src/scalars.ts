/**
 * M0 neutral scalar handling.
 *
 * The neutral type set (`core/spec/m0-core-conventions.md`) is the
 * language-neutral vocabulary every `attribute.type` draws from. This module
 * gives each scalar an idiomatic TypeScript carrier and — crucially — the
 * **wire (de)serialization rules** that make `?`-bind values and observed rows
 * canonicalize byte-for-byte with the Python oracle at the envelope boundary.
 *
 * | Neutral type     | Carrier                                  |
 * |------------------|------------------------------------------|
 * | `boolean`        | `boolean`                                |
 * | `int32`/`float*` | `number`                                 |
 * | `int64`          | native `bigint`                          |
 * | `decimal(p,s)`   | {@link ParallaxDecimal} (over decimal.js)|
 * | `string`/`uuid`  | `string`                                 |
 * | `bytes`          | `Uint8Array`                             |
 * | `date`/`time`    | `Temporal.PlainDate`/`Temporal.PlainTime`|
 * | `timestamp`      | `Temporal.Instant` (UTC, microsecond)    |
 * | `json`           | plain JSON value                         |
 *
 * Two cross-cutting rules drive the wire boundary:
 *  - `JSON.stringify(bigint)` *throws*, so `int64` (and the exact `decimal`
 *    type, to avoid binary-float drift) serialize to **canonical strings**.
 *  - `timestamp` is UTC-normalized to **microsecond** precision; sub-µs input
 *    is rejected, never silently truncated.
 */

import type * as DecimalNs from "decimal.js";
// decimal.js merges a class + namespace + callable under its default export.
// Under NodeNext the default *binding* surfaces as the namespace (carrying the
// `Decimal.Constructor`/`Decimal.Value` type aliases but no construct signature),
// while the runtime default IS the constructor. We import the namespace for the
// types and the default for the runtime constructor, bridging them with a single
// localized cast so the rest of the module stays fully typed. The concrete
// library stays reversible behind the ParallaxDecimal seam (design Q6).
import DecimalDefault from "decimal.js";
import { Temporal } from "temporal-polyfill";

type DecimalConstructor = DecimalNs.Decimal.Constructor;
type DecimalInstance = DecimalNs.Decimal.Instance;
const Decimal = DecimalDefault as unknown as DecimalConstructor;

/**
 * The neutral scalar type names. `decimal(p,s)` carries its precision/scale in
 * the token, so it is matched by prefix rather than enumerated.
 */
export type NeutralScalar =
  | "boolean"
  | "int32"
  | "int64"
  | "float32"
  | "float64"
  | "string"
  | "bytes"
  | "date"
  | "time"
  | "timestamp"
  | "uuid"
  | "json"
  | `decimal(${number},${number})`;

/**
 * The structural JSON value type (spec §3.2.1) — the public runtime mapping for
 * the M0 `json` scalar and for value-object properties (which V1 exposes as
 * unstructured JSON, spec §2.1). The generated `#parallax` barrel re-exports it
 * from here alongside {@link ParallaxDecimal}.
 */
export type ParallaxJsonValue =
  | null
  | boolean
  | number
  | string
  | ParallaxJsonValue[]
  | { readonly [key: string]: ParallaxJsonValue };

/** Matches a `decimal(p,s)` neutral type token and captures precision/scale. */
const DECIMAL_TYPE = /^decimal\((\d+),(\d+)\)$/;

/** Parsed precision/scale of a `decimal(p,s)` neutral type. */
export interface DecimalTypeSpec {
  readonly precision: number;
  readonly scale: number;
}

/**
 * Parse a `decimal(p,s)` neutral type token. Returns `undefined` for any other
 * (non-decimal) neutral type.
 */
export function parseDecimalType(type: string): DecimalTypeSpec | undefined {
  const match = DECIMAL_TYPE.exec(type);
  if (!match) {
    return undefined;
  }
  // The capture groups are guaranteed numeric by the pattern.
  const precision = Number(match[1]);
  const scale = Number(match[2]);
  return { precision, scale };
}

/**
 * `ParallaxDecimal` — the exact fixed-point carrier for the M0 `decimal(p,s)`
 * type, wrapping `decimal.js` so the concrete library stays reversible behind
 * this seam (design Q6). Comparison and arithmetic run in decimal space, never
 * binary float; the wire form is the fixed-scale canonical string.
 */
export class ParallaxDecimal {
  /** The underlying exact value. */
  private readonly value: DecimalInstance;

  private constructor(value: DecimalInstance) {
    this.value = value;
  }

  /**
   * Construct from an exact source: a decimal string (the canonical wire form),
   * an exact `bigint`, or another `ParallaxDecimal`. JS `number` is rejected in
   * full — even a whole-valued `number` is a binary float that cannot represent
   * an exact decimal, and the spec's `decimal(p,s)` create/update input is
   * `ParallaxDecimal | string` with `number` rejected to avoid precision drift
   * (`spec/01-implementation-spec.md` §3.2.1). Decimals must arrive as exact
   * strings.
   */
  static from(input: string | bigint | ParallaxDecimal): ParallaxDecimal {
    if (input instanceof ParallaxDecimal) {
      return input;
    }
    if (typeof input === "bigint") {
      return new ParallaxDecimal(new Decimal(input.toString()));
    }
    if (typeof input === "number") {
      // Defensive runtime guard: the type already excludes `number`, but a JS
      // caller without types could still pass one. Reject every number — a
      // float boundary is exactly the precision-drift the seam exists to avoid.
      throw new TypeError(
        `ParallaxDecimal.from rejects JS number (${input as number}); pass an exact decimal string instead`,
      );
    }
    return new ParallaxDecimal(new Decimal(input));
  }

  /** Exact equality in decimal space. */
  equals(other: ParallaxDecimal): boolean {
    return this.value.equals(other.value);
  }

  /** Signed comparison (`-1`, `0`, `1`) in decimal space. */
  compare(other: ParallaxDecimal): -1 | 0 | 1 {
    return this.value.cmp(other.value) as -1 | 0 | 1;
  }

  /**
   * The canonical fixed-scale wire string, e.g. `decimal(18,2)` value `5`
   * renders `"5.00"`. With no scale supplied the natural string is returned.
   */
  toFixedString(scale?: number): string {
    return scale === undefined ? this.value.toString() : this.value.toFixed(scale);
  }

  /** Natural decimal string (no forced scale). */
  toString(): string {
    return this.value.toString();
  }
}

/** Microseconds per second — the M0 timestamp precision granularity. */
const MICROS_PER_SECOND = 1_000_000n;
/** Nanoseconds per microsecond. `Temporal.Instant` stores nanoseconds. */
const NANOS_PER_MICRO = 1_000n;

/**
 * The temporal-infinity sentinel. The open upper bound of a temporal interval
 * is the database-native infinity (M0); in the neutral descriptor / operation
 * surface it is the literal string `"infinity"`, and the M11 dialect seam owns
 * the concrete representation. Temporal binds carry this sentinel as-is.
 */
export const INFINITY = "infinity" as const;
export type Infinity = typeof INFINITY;

/** True when a value is the temporal-infinity sentinel. */
export function isInfinity(value: unknown): value is Infinity {
  return value === INFINITY;
}

/**
 * Parse an ISO-8601 UTC instant into a `Temporal.Instant`, enforcing the M0
 * microsecond-precision rule: an input carrying non-zero sub-microsecond
 * precision is **rejected**, never silently truncated. Inputs with fewer than
 * six fractional digits are interpreted exactly.
 *
 * The temporal-infinity sentinel passes through unchanged (callers that may see
 * `infinity` should branch on {@link isInfinity} first; this helper rejects it
 * so a stray sentinel never masquerades as an instant).
 */
export function parseTimestamp(iso: string): Temporal.Instant {
  const instant = Temporal.Instant.from(iso);
  // `epochNanoseconds` is exact; reject any value not aligned to a microsecond.
  if (instant.epochNanoseconds % NANOS_PER_MICRO !== 0n) {
    throw new RangeError(
      `timestamp ${iso} carries sub-microsecond precision; M0 rejects it (microsecond granularity)`,
    );
  }
  return instant;
}

/**
 * Render a `Temporal.Instant` to its canonical UTC wire string — the exact form
 * the compatibility corpus authors and the reference oracle produces (Python's
 * `datetime.isoformat()`): an explicit `+00:00` offset (not `Z`), with the
 * fractional-seconds component **omitted when the value is whole-second** and
 * rendered to full **microsecond** precision otherwise (`.123456`). Matching this
 * form byte-for-byte is what lets the harness compare a projected/table-state
 * `timestamp` column against its authored expected value by exact string.
 */
export function timestampToWire(instant: Temporal.Instant): string {
  // `smallestUnit: "microsecond"` keeps exactly the µs digits the contract
  // mandates (Temporal otherwise renders nanoseconds when present) and always
  // renders a trailing `Z`.
  const iso = instant.toString({ smallestUnit: "microsecond" });
  // Drop an all-zero fractional part (Python's isoformat omits it for whole
  // seconds), then normalize the `Z` designator to the corpus's `+00:00` offset.
  return iso.replace(".000000Z", "Z").replace(/Z$/, "+00:00");
}

/**
 * Materialize a raw `timestamptz` string from the driver into a
 * `Temporal.Instant` at the adapter boundary (the §3.2.1 "normalize at the
 * adapter boundary" rule). Drivers parse `timestamptz` into a millisecond JS
 * `Date` by default, which would lose µs precision; the adapter registers
 * raw-string parsers and materializes the instant itself.
 */
export function timestampFromRaw(raw: string): Temporal.Instant {
  return parseTimestamp(normalizeRawTimestamp(raw));
}

/**
 * Normalize a Postgres `timestamptz` text rendering (`2026-01-01 00:00:00+00`)
 * into an ISO-8601 instant `Temporal.Instant.from` accepts. Postgres uses a
 * space separator and a `+00` offset; ISO-8601 wants `T` and a `Z`/`+00:00`.
 */
function normalizeRawTimestamp(raw: string): string {
  let iso = raw.trim().replace(" ", "T");
  // A bare `+00` / `-00` offset must become `+00:00` (or `Z`).
  if (/[+-]\d{2}$/.test(iso)) {
    iso = `${iso}:00`;
  } else if (!/[Zz]|[+-]\d{2}:\d{2}$/.test(iso)) {
    // No timezone designator at all ⇒ the value is already UTC.
    iso = `${iso}Z`;
  }
  return iso;
}

/**
 * Build a `Temporal.Instant` from an exact microseconds-since-epoch count
 * (scaling µs → ns, the unit `Temporal.Instant` stores) — a small helper used
 * by interval math in later phases. Exposed here so the µs constants have a
 * single owner.
 */
export function microsToInstant(epochMicros: bigint): Temporal.Instant {
  return new Temporal.Instant(epochMicros * NANOS_PER_MICRO);
}

/** Exact microseconds-since-epoch of an instant (for interval comparison). */
export function instantToMicros(instant: Temporal.Instant): bigint {
  return instant.epochNanoseconds / NANOS_PER_MICRO;
}

/** Whole microseconds in one second — re-exported for interval callers. */
export const MICROSECONDS_PER_SECOND = MICROS_PER_SECOND;

/**
 * Serialize a scalar JS value to its canonical **wire** JSON form.
 *
 * The wire boundary cannot carry every native carrier directly:
 *  - `bigint` (`int64`) ⇒ canonical decimal string (`JSON.stringify` throws on
 *    bigint).
 *  - {@link ParallaxDecimal} ⇒ canonical decimal string (never binary float).
 *  - `Temporal.Instant` ⇒ canonical UTC µs string.
 *  - `Temporal.PlainDate`/`Temporal.PlainTime` ⇒ their ISO strings.
 *  - `Uint8Array` (`bytes`) ⇒ lowercase hex string.
 *  - everything else (string/number/boolean/null/JSON object/array) passes
 *    through, recursing into containers.
 */
export function toWire(value: unknown): unknown {
  if (typeof value === "bigint") {
    return value.toString();
  }
  if (value instanceof ParallaxDecimal) {
    return value.toFixedString();
  }
  if (value instanceof Temporal.Instant) {
    return timestampToWire(value);
  }
  if (value instanceof Temporal.PlainDate || value instanceof Temporal.PlainTime) {
    return value.toString();
  }
  if (value instanceof Uint8Array) {
    return bytesToHex(value);
  }
  if (Array.isArray(value)) {
    return value.map(toWire);
  }
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      out[key] = toWire(inner);
    }
    return out;
  }
  return value;
}

/** Lowercase-hex rendering of a byte buffer (the `bytes` wire form). */
export function bytesToHex(bytes: Uint8Array): string {
  let hex = "";
  for (const byte of bytes) {
    hex += byte.toString(16).padStart(2, "0");
  }
  return hex;
}

/** A single byte's worth of hex: exactly two hex digits. */
const HEX_BYTE = /^[0-9a-fA-F]{2}$/;

/**
 * Parse a lowercase/uppercase hex string back into a byte buffer.
 *
 * Each two-character chunk is validated against {@link HEX_BYTE} and a
 * non-hex chunk throws. This is load-bearing: `Number.parseInt` yields `NaN`
 * for `"zz"` (silently stored as `0`) and stops at the first invalid char for
 * `"0g"` (silently `0`), so without per-chunk validation invalid wire bytes
 * would round-trip as different — but plausible — bytes.
 */
export function bytesFromHex(hex: string): Uint8Array {
  const clean = hex.startsWith("\\x") ? hex.slice(2) : hex;
  if (clean.length % 2 !== 0) {
    throw new RangeError(`hex string has odd length: ${hex}`);
  }
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    const chunk = clean.slice(i * 2, i * 2 + 2);
    if (!HEX_BYTE.test(chunk)) {
      throw new RangeError(`invalid hex byte '${chunk}' at offset ${i * 2} in: ${hex}`);
    }
    out[i] = Number.parseInt(chunk, 16);
  }
  return out;
}

export { Temporal };
