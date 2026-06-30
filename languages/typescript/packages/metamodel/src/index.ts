/**
 * `@parallax/metamodel` — M1 domain model & metamodel introspection.
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
