/**
 * `@parallax/conformance` — M12 compatibility harness.
 *
 * Exports the canonical `describe` claim, the ajv-backed envelope validator,
 * case discovery, the six-condition in-claim gate, the `CompatibilityDatabase`
 * provider port, the read-shape runner, and the case matrix. The concrete
 * Testcontainers provider lives in the `@parallax/typescript` composition root
 * and is injected through the port.
 */

export {
  compareRowSet,
  type RowSetComparison,
  scalarsEqual,
} from "./compare.js";
export {
  describe,
  FIRST_IMPLEMENTATION_MVP_CAPABILITIES,
  TYPESCRIPT_ADAPTER,
} from "./describe.js";
export {
  detectShape,
  discoverCasePaths,
  type LoadedCase,
  loadCase,
  repoRoot,
  toCasePath,
} from "./discover.js";
export {
  type GateCase,
  type GateDiagnosticCode,
  type GateResult,
  inClaim,
} from "./gate.js";
export { CaseMatrix, type MatrixEntry, type MatrixStatus } from "./matrix.js";
export type { CompatibilityDatabaseProvider, ProviderRow } from "./provider.js";
export { readProjection, runCompile, runRun } from "./runner.js";
export {
  assertValidEnvelope,
  conformanceAdapterValidator,
  type ValidationResult,
  validateEnvelope,
} from "./schema.js";
