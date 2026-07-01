/**
 * `@parallax/transactions` — M8 transactions, unit of work & caches.
 *
 * The Phase-7 slice: the closure-demarcated unit of work's combined/flushed
 * writes (buffered inserts → one multi-row `INSERT`; a batched update → uniform
 * `pk in (…)` or one keyed `UPDATE` per key; FK-safe insert ordering) and the
 * automatic in-transaction shared read lock. Each exposes only the pure DML
 * planning / SQL-text discipline; the caller resolves physical targets from the
 * metamodel and executes.
 */
export {
  type BatchStatement,
  type BatchTarget,
  keyedUpdate,
  multiRowInsert,
  uniformUpdate,
} from "./batch.js";
export { appendReadLock } from "./read-lock.js";
export {
  type BatchMutation,
  combineWrites,
  type PlannedStatement,
  type WriteStep,
} from "./uow.js";
