/**
 * `@parallax/metamodel` — domain model and metamodel (`m-descriptor`, `m-pk-gen`, `m-inheritance`, `m-value-object`).
 *
 * The generic descriptor reader (`Metamodel` / `EntityMetadata`), canonical
 * relationship declarations and Relationship Facet, and ajv-validation against
 * `metamodel.schema.json`. The reader is not yet the complete accepted
 * m-metamodel formation implementation.
 */
export * from "./normalize.js";
export * from "./reader.js";
export * from "./schema.js";
export * from "./serde.js";
