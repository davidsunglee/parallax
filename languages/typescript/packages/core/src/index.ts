/**
 * `@parallax/core` — M0 core conventions.
 *
 * Exports the adapter-envelope types and the M0 neutral scalar handling
 * (`ParallaxDecimal`, `int64` via `bigint`, `timestamp` via `Temporal.Instant`,
 * the `infinity` sentinel, and the wire (de)serialization rules).
 */
export * from "./envelope.js";
export * from "./scalars.js";
