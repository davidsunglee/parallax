/**
 * `@parallax/operation` — M2 query/operation algebra.
 *
 * The discriminated-union operation data model (single-key tagged nodes) and
 * ajv-validation against `operation.schema.json`. The wire form and the
 * in-memory form are identical, so operations round-trip trivially through
 * `@parallax/serde`.
 */

// Re-export the M1 metamodel reader so M2-consumers (the conformance harness)
// can introspect descriptors through the one allowed `M2 -> M1` edge rather
// than taking a direct dependency on `@parallax/metamodel` (which the DAG
// forbids for `@parallax/conformance`). Operations are expressed in terms of
// metamodel references, so surfacing the reader here is the natural facade.
// Named re-exports (not a star) so this does not collide with the local
// `ValidationResult` from `./schema.js`.
export {
  EntityMetadata,
  Metamodel,
  type NormalizedAsOfAttribute,
  type NormalizedAttribute,
  type NormalizedEntity,
  type NormalizedRelationship,
} from "@parallax/metamodel";
// Re-export the canonical serde seam so M2-consumers (the conformance harness)
// can parse case / model YAML through the *same* seam the algebra
// canonicalizes through — without a direct `@parallax/conformance ->
// @parallax/serde` edge (the DAG routes serde through M1/M2 only).
export {
  canonical,
  canonicallyEqual,
  deepEqual,
  deserialize,
  type JsonValue,
  type SerdeFormat,
  serialize,
} from "@parallax/serde";
export * from "./ast.js";
export * from "./canonicalize.js";
export * from "./schema.js";
