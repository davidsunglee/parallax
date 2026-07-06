/**
 * Operation canonicalization, routed through the shared `@parallax/serde` seam.
 *
 * The operation algebra and the metamodel canonicalize through the *same* serde
 * seam (ADR-0056), so the adapter canonicalizes byte-for-byte like the Python
 * oracle. This module is the operation side of that seam: it decides node
 * identity for the `equivalentEncodings` precedence check (e.g. `m-op-algebra-024`), where a
 * prefix surface and a fluent surface differing only in object-key order must
 * collapse to one canonical `operation`.
 */
import { canonical, canonicallyEqual } from "@parallax/serde";
import type { Operation } from "./ast.js";

/**
 * Canonicalize an operation: recursive key-sort, array order preserved. Two
 * authored encodings that canonicalize to the same value denote the same node.
 */
export function canonicalOperation(op: Operation): Operation {
  return canonical(op);
}

/**
 * True when an authored surface encoding denotes the same canonical operation
 * as `canonicalForm` — the `equivalentEncodings` identity check, independent of
 * object-key authoring order.
 */
export function isEquivalentEncoding(encoding: unknown, canonicalForm: Operation): boolean {
  return canonicallyEqual(encoding, canonicalForm);
}
