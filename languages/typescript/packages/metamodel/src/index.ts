/**
 * `@parallax/metamodel` — domain model and metamodel (`m-descriptor`, `m-pk-gen`, `m-inheritance`, `m-value-object`).
 *
 * The generic descriptor reader (`Metamodel` / `EntityMetadata`), defaulting /
 * normalization, and ajv-validation against `metamodel.schema.json`. The reader
 * presents the fully-defaulted view; the typed layer generated in Phase 9
 * delegates to it.
 */
export * from "./normalize.js";
export * from "./reader.js";
export * from "./schema.js";
export * from "./serde.js";
