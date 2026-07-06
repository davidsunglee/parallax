/**
 * The canonical, format-agnostic serde seam shared by `@parallax/metamodel`
 * (m-descriptor) and `@parallax/operation` (m-op-algebra).
 *
 * The canonical model is plain JSON-compatible data (objects / arrays /
 * scalars) — the identical in-memory shape descriptors and operations
 * serialize to. Routing both consumers through this one seam is what makes the
 * TypeScript adapter canonicalize **byte-for-byte** like the Python oracle
 * (`reference-harness/src/reference_harness/serde.py`), including the
 * `equivalentEncodings` precedence check.
 *
 * The four-part contract (m-descriptor §"Metamodel serde"; ADR-0010):
 *  1. safe load (the `yaml` reader is safe by default — no custom tags);
 *  2. **recursive key-sort** so object-key authoring order is irrelevant;
 *  3. **list order preserved** — order is significant in the algebra and in
 *     attribute / row sequences, so arrays are never sorted;
 *  4. an idempotent, lossless round-trip in both JSON and YAML.
 */
import {
  parseDocument,
  parse as parseYaml,
  type Scalar,
  stringify as stringifyYaml,
  visit,
} from "yaml";

/** The serde formats with concrete writers. */
export const JSON_FORMAT = "json" as const;
export const YAML_FORMAT = "yaml" as const;
export type SerdeFormat = typeof JSON_FORMAT | typeof YAML_FORMAT;
export const FORMATS: readonly SerdeFormat[] = [JSON_FORMAT, YAML_FORMAT];

/** A JSON-compatible value: the canonical model's universe of discourse. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

/**
 * Return a deterministically-ordered, JSON-compatible copy of `value`.
 *
 * Object keys are sorted recursively; **arrays keep their order** (order is
 * significant). Scalars pass through unchanged. Two authored encodings that
 * canonicalize to the same value denote the same node — the property the
 * `equivalentEncodings` check (e.g. `m-op-algebra-024`) relies on: a prefix surface and a
 * fluent surface differing only in object-key order both collapse here.
 */
export function canonical<T>(value: T): T {
  return canonicalize(value as unknown) as T;
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value !== null && typeof value === "object") {
    const source = value as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(source).sort()) {
      out[key] = canonicalize(source[key]);
    }
    return out;
  }
  return value;
}

/** Serialize a value to the given format after canonicalizing it. */
export function serialize(value: unknown, format: SerdeFormat = JSON_FORMAT): string {
  const value_ = canonicalize(value);
  if (format === JSON_FORMAT) {
    return JSON.stringify(value_);
  }
  // The `yaml` writer is safe by default; `sortMapEntries` keeps the written
  // form deterministic regardless of authoring order (a second guard alongside
  // the already-canonicalized input).
  return stringifyYaml(value_, { sortMapEntries: true });
}

/** Deserialize a value from the given format back into the canonical model. */
export function deserialize(text: string, format: SerdeFormat = JSON_FORMAT): unknown {
  if (format === JSON_FORMAT) {
    return JSON.parse(text);
  }
  return parseYamlLossless(text);
}

/**
 * Parse YAML, but preserve the **exact source text** of any numeric scalar whose
 * value cannot survive a JavaScript `number` round-trip — carried as a string so
 * downstream type-aware coercion (the m-sql compiler resolving a literal against its
 * m-core neutral type) can recover the exact int64 / decimal value.
 *
 * Why this lives in the serde reader and not only the compiler: `yaml.parse`
 * (like `JSON.parse`) materializes a numeric scalar as a binary-float `number`
 * **before** any consumer sees it, so `9223372036854775807` is already
 * `9223372036854776000` and `1234567890123456.78` is already `…6.8`. Precision is
 * destroyed at parse time, so it must be preserved at parse time.
 *
 * The rule is deliberately type-agnostic and conservative: a float-**safe**
 * authored number (`42`, `20.00`, `50.75`) keeps its JS-number form — exactly the
 * Phase-3 wire-form decision the corpus goldens assume (`binds: [42]` is a JSON
 * number) — and only a genuinely-unrepresentable token (`> 2^53`, or a decimal
 * the double cannot hold) is preserved as its source string. The m-sql compiler then
 * normalizes it against the resolved attribute type into the canonical wire form.
 */
export function parseYamlLossless(text: string): unknown {
  const doc = parseDocument(text);
  visit(doc, {
    Scalar(_key, node: Scalar) {
      if (typeof node.value === "number" && isLossyNumericScalar(node)) {
        // Re-tag as a string carrying the exact source text. `toJS` then yields
        // the source string instead of the precision-truncated number.
        node.value = node.source ?? String(node.value);
        node.type = "QUOTE_DOUBLE";
      }
    },
  });
  return doc.toJS();
}

/**
 * True when a numeric YAML scalar's exact source text cannot be reproduced from
 * its parsed JS `number` — i.e. the double silently dropped digits. Compares the
 * source's exact decimal value against the value the parsed double denotes; a
 * scale-only difference (`20.00` vs `20`) is **not** lossy (the numeric value is
 * identical), so float-safe authored numbers are left untouched.
 */
function isLossyNumericScalar(node: Scalar): boolean {
  const source = node.source;
  if (source === undefined) {
    return false;
  }
  // Only plain (unquoted) numeric tokens are candidates; an explicitly-quoted or
  // tagged scalar is already a string and never reached the lossy `number` path.
  const trimmed = source.trim();
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(trimmed)) {
    return false;
  }
  return !numbersEqual(trimmed, node.value as number);
}

/**
 * Whether a decimal source string denotes exactly the same value as a JS number.
 * Normalizes both to a canonical digit form (strip sign, leading/trailing zeros,
 * a trailing decimal point) so `20.00` ≡ `20` ≡ `20.` but `9223372036854775807`
 * ≢ `9223372036854776000`.
 */
function numbersEqual(source: string, parsed: number): boolean {
  // Exponent forms are rare in the corpus; fall back to the parsed value's own
  // string (an exponent token that survived parsing is, by definition, safe).
  if (/[eE]/.test(source)) {
    return Number(source) === parsed;
  }
  return canonicalDigits(source) === canonicalDigits(String(parsed));
}

/** Canonical digit signature of a plain decimal string (sign + digits + scale). */
function canonicalDigits(text: string): string {
  let sign = "";
  let body = text;
  if (body.startsWith("+")) {
    body = body.slice(1);
  } else if (body.startsWith("-")) {
    sign = "-";
    body = body.slice(1);
  }
  const dot = body.indexOf(".");
  let intPart = dot === -1 ? body : body.slice(0, dot);
  let fracPart = dot === -1 ? "" : body.slice(dot + 1);
  intPart = intPart.replace(/^0+(?=\d)/, "");
  fracPart = fracPart.replace(/0+$/, "");
  const digits = fracPart === "" ? intPart : `${intPart}.${fracPart}`;
  return digits === "0" || digits === "" ? "0" : `${sign}${digits}`;
}

/** Re-export the JSON-only YAML parser (lossy) for callers that need raw parse. */
export { parseYaml as parseYamlLossy };

/** `serialize -> deserialize` for one format, returning the parsed node. */
export function roundTrip(value: unknown, format: SerdeFormat): unknown {
  return deserialize(serialize(value, format), format);
}

/**
 * Assert `serialize(deserialize(x)) == x` for **both** JSON and YAML.
 *
 * Concretely, for each format: serializing the canonicalized value, parsing it
 * back, and re-serializing must yield byte-identical text (a fixed point), and
 * the re-canonicalized parse must equal the original canonical value (lossless).
 * This is the fixed-point property an implementation's serde must satisfy
 * (mirrors the oracle's `assert_roundtrip`).
 */
export function assertRoundTrip(value: unknown): void {
  const value_ = canonicalize(value);
  for (const format of FORMATS) {
    const first = serialize(value_, format);
    const parsed = deserialize(first, format);
    const second = serialize(parsed, format);
    if (first !== second) {
      throw new Error(
        `serde round-trip is not a fixed point for format '${format}':\n` +
          `  first:  ${first}\n  second: ${second}`,
      );
    }
    if (!deepEqual(canonicalize(parsed), value_)) {
      throw new Error(
        `serde round-trip changed the value for format '${format}':\n` +
          `  before: ${serialize(value_, JSON_FORMAT)}\n` +
          `  after:  ${serialize(parsed, JSON_FORMAT)}`,
      );
    }
  }
}

/**
 * Structural equality over canonical (key-sorted) JSON-compatible values. Both
 * operands are assumed already canonicalized, so a key-order-insensitive
 * comparison is a plain recursive walk.
 */
export function deepEqual(left: unknown, right: unknown): boolean {
  if (left === right) {
    return true;
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
      return false;
    }
    return left.every((item, index) => deepEqual(item, right[index]));
  }
  if (left !== null && right !== null && typeof left === "object" && typeof right === "object") {
    const leftKeys = Object.keys(left as Record<string, unknown>);
    const rightKeys = Object.keys(right as Record<string, unknown>);
    if (leftKeys.length !== rightKeys.length) {
      return false;
    }
    return leftKeys.every((key) =>
      deepEqual((left as Record<string, unknown>)[key], (right as Record<string, unknown>)[key]),
    );
  }
  return false;
}

/**
 * True when two authored encodings denote the same canonical node — the
 * `equivalentEncodings` identity check, independent of object-key order.
 */
export function canonicallyEqual(left: unknown, right: unknown): boolean {
  return deepEqual(canonicalize(left), canonicalize(right));
}
