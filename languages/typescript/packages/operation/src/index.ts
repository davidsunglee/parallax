/**
 * `@parallax/operation` — m-op-algebra query/operation algebra.
 *
 * The discriminated-union operation data model (single-key tagged nodes) and
 * ajv-validation against `operation.schema.json`. The wire form and the
 * in-memory form are identical, so operations round-trip trivially through
 * `@parallax/serde`.
 */

// Re-export the m-descriptor metamodel reader so m-op-algebra-consumers (the conformance harness)
// can introspect descriptors through the one allowed `m-op-algebra -> m-descriptor` edge rather
// than taking a direct dependency on `@parallax/metamodel` (which the DAG
// forbids for `@parallax/conformance`). Operations are expressed in terms of
// metamodel references, so surfacing the reader here is the natural facade.
// Named re-exports (not a star) so this does not collide with the local
// `ValidationResult` from `./schema.js`.
export {
  type AttributeIdentity,
  type DefiningRelationshipDeclaration,
  EntityMetadata,
  Metamodel,
  type NormalizedAsOfAxis,
  type NormalizedAttribute,
  type NormalizedEntity,
  type NormalizedNestedValueObject,
  type NormalizedValueObject,
  type NormalizedValueObjectAttribute,
  type NormalizedValueObjectMember,
  type RelationshipDeclaration,
  RelationshipFacet,
  type RelationshipIdentity,
  type RelationshipJoin,
  type RelationshipMetadata,
  type RelationshipOrder,
  type ReverseRelationshipDeclaration,
} from "@parallax/metamodel";
// Re-export the canonical serde seam so m-op-algebra-consumers (the conformance harness)
// can parse case / model YAML through the *same* seam the algebra
// canonicalizes through — without a direct `@parallax/conformance ->
// @parallax/serde` edge (the DAG routes serde through m-descriptor/m-op-algebra only).
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
export * from "./value-object-validate.js";
