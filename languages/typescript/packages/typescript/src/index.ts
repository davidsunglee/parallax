/**
 * `@parallax/typescript` — the composition root and public runtime facade.
 *
 * Owns the `parallax` and `parallax-conformance` CLIs, the generator config API
 * (`@parallax/typescript/config`), the codegen pipeline, the fluent query DSL,
 * and the `parallax(...)` runtime the generated `#parallax` barrel wires
 * together. It may import any numbered or support package; no package may import
 * it (dependency-cruiser enforces this — generated code lives in an application,
 * not a numbered package).
 *
 * The Phase 9 developer surface (design Q1 Option B) is a thin typed layer over
 * the SAME generic runtime the conformance adapter uses: the DSL builds canonical
 * m-op-algebra operations, the runtime lowers them with the m-sql compiler, so conformance is
 * unaffected. This barrel re-exports the public runtime types (`ParallaxList`,
 * the error classes, `ParallaxDecimal`, `Temporal`) so the generated barrel — and
 * applications — reach them through one package (spec §2.1).
 */

export { ParallaxDecimal, type ParallaxJsonValue, Temporal } from "@parallax/core";
// --- public runtime re-exports (spec §2.1, §3.2.1) --------------------------
export {
  ParallaxError,
  ParallaxList,
  ParallaxNotFoundError,
  ParallaxTooManyResultsError,
} from "@parallax/lists";
// --- fluent query DSL (spec §2) ---------------------------------------------
export {
  AttributeExpression,
  type AxisRefs,
  buildFindOperation,
  type FindOptions,
  NavigationPath,
  NestedFieldExpression,
  OrderKeyExpression,
  Predicate,
  type StringPredicateOptions,
  type TemporalAxis,
  type TemporalPoint,
  type TemporalRange,
  type TemporalReadOptions,
  ToManyRelationshipExpression,
  ValueObjectExpression,
} from "./dsl/index.js";
// --- runtime factory + handles (spec §2.2, §4) ------------------------------
export {
  type Assignment,
  type Concurrency,
  createParallax,
  type DeepFetchGraph,
  EntityFinder,
  executeDeepFetch,
  isDeepFetchOperation,
  Parallax,
  type ParallaxClock,
  type ParallaxDatabase,
  ParallaxOptimisticLockError,
  type ParallaxOptions,
  ParallaxReadBeforeWriteError,
  type ParallaxRow,
  ParallaxTemporalCloseError,
  ParallaxTemporalOptimisticError,
  ParallaxTransaction,
  ParallaxWriteValidationError,
  RuntimeSchema,
  TransactionEntity,
  type TransactionOptions,
  TransactionWriter,
  type UpdateOptions,
  type WriteResult,
} from "./runtime/index.js";
