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
  type ColumnTypes,
  compareGraph,
  compareRowSet,
  compareTableState,
  type Graph,
  type GraphColumnTypes,
  type RowSetComparison,
  scalarsEqual,
  type TableState,
} from "./compare.js";
export {
  buildConflictPlan,
  type ConflictAttempt,
  type ConflictPlan,
  isConflict,
} from "./conflict.js";
export {
  buildDeepFetchPlan,
  type DeepFetchPlan,
  isDeepFetch,
} from "./deepfetch-plan.js";
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
export {
  CaseMatrix,
  isGreenStatus,
  type MatrixEntry,
  type MatrixReport,
  type MatrixResidual,
  type MatrixStatus,
  renderMatrixReport,
  summarizeMatrix,
} from "./matrix.js";
export type { CompatibilityDatabaseProvider, ProviderRow } from "./provider.js";
export { readProjection, runCompile, runRun } from "./runner.js";
export {
  buildScenarioPlan,
  isScenario,
  type ScenarioPlan,
  type ScenarioStep,
} from "./scenario.js";
export {
  assertValidEnvelope,
  conformanceAdapterValidator,
  type ValidationResult,
  validateEnvelope,
} from "./schema.js";
export { columnTypesForCase } from "./schema-resolver.js";
export {
  buildConformanceSliceCoverageReport,
  type CommandSliceCoverage,
  type ConformanceSliceCoverageOptions,
  type ConformanceSliceCoverageReport,
  renderConformanceSliceCoverageMarkdown,
} from "./slice-coverage.js";
export {
  buildWriteSequencePlan,
  isWriteSequence,
  type WriteSequencePlan,
  type WriteStatementPlan,
} from "./write-sequence.js";
