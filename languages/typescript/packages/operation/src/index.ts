/**
 * `@parallax/operation` — M2 query/operation algebra.
 *
 * The discriminated-union operation data model (single-key tagged nodes) and
 * ajv-validation against `operation.schema.json`. The wire form and the
 * in-memory form are identical, so operations round-trip trivially through
 * `@parallax/serde`.
 */
export * from "./ast.js";
export * from "./canonicalize.js";
export * from "./schema.js";
