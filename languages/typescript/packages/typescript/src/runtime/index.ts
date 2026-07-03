/**
 * The application runtime the generated `#parallax` barrel wires together — the
 * `parallax(...)` factory, the `Parallax` / `ParallaxTransaction` handles, and
 * the database port. A thin typed surface over the same generic runtime the
 * conformance adapter uses (design Q1 Option B).
 */
export { type DeepFetchGraph, executeDeepFetch, isDeepFetchOperation } from "./deep-fetch.js";
export {
  type Assignment,
  createParallax,
  EntityFinder,
  Parallax,
  type ParallaxClock,
  type ParallaxDatabase,
  type ParallaxOptions,
  type ParallaxRow,
  ParallaxTransaction,
  TransactionEntity,
  type TransactionOptions,
} from "./parallax.js";
export { RuntimeSchema } from "./schema.js";
export {
  type Concurrency,
  ParallaxOptimisticLockError,
  ParallaxReadBeforeWriteError,
  ParallaxTemporalCloseError,
  ParallaxTemporalOptimisticError,
  TransactionWriter,
  type UpdateOptions,
  type WriteResult,
} from "./writes.js";
