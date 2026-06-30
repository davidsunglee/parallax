/**
 * The canonical, format-agnostic serde seam shared by `@parallax/metamodel`
 * (M1) and `@parallax/operation` (M2).
 *
 * The canonical model is plain JSON-compatible data (objects / arrays /
 * scalars) — the identical in-memory shape descriptors and operations
 * serialize to. Routing both consumers through this one seam is what makes the
 * TypeScript adapter canonicalize **byte-for-byte** like the Python oracle
 * (`reference-harness/src/reference_harness/serde.py`), including the
 * `equivalentEncodings` precedence check.
 *
 * The four-part contract (M1 §"Metamodel serde"; ADR-0057):
 *  1. safe load (the `yaml` reader is safe by default — no custom tags);
 *  2. **recursive key-sort** so object-key authoring order is irrelevant;
 *  3. **list order preserved** — order is significant in the algebra and in
 *     attribute / row sequences, so arrays are never sorted;
 *  4. an idempotent, lossless round-trip in both JSON and YAML.
 */
import { parse as parseYaml, stringify as stringifyYaml } from "yaml";

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
 * `equivalentEncodings` check (e.g. `0222`) relies on: a prefix surface and a
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
  return parseYaml(text);
}

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
