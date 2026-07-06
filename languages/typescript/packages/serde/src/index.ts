/**
 * `@parallax/serde` — the canonical, format-agnostic serde seam shared by
 * `@parallax/metamodel` (m-descriptor) and `@parallax/operation` (m-op-algebra).
 *
 * `canonical` / `serialize` / `deserialize` / `assertRoundTrip` are the public
 * surface; both consumers route through it so descriptor and operation
 * encodings canonicalize identically to the Python oracle.
 */
export * from "./canonical.js";
