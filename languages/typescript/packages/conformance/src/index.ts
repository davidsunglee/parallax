/**
 * `@parallax/conformance` — M12 compatibility harness.
 *
 * This phase exports the canonical `describe` claim and the ajv-backed envelope
 * validator. Case discovery, the in-claim gate, the provider port, the runner,
 * and the case matrix land in Phase 3+.
 */
export {
  describe,
  FIRST_IMPLEMENTATION_MVP_CAPABILITIES,
  TYPESCRIPT_ADAPTER,
} from "./describe.js";
export {
  assertValidEnvelope,
  conformanceAdapterValidator,
  type ValidationResult,
  validateEnvelope,
} from "./schema.js";
