/**
 * `@parallax/locking` — m-opt-lock optimistic locking.
 *
 * Owns the version-column optimistic-lock discipline: the versioned `UPDATE` that
 * gates on the read version and advances it in the same statement, and the
 * `updatedRows != 1` conflict signal. The m-case-format harness imports these directly over
 * the legal `m-case-format -> m-opt-lock` edge; it reaches the m-unit-work unit-of-work helpers over its own
 * direct `m-case-format -> m-unit-work` edge (importing `@parallax/transactions`), not through this
 * package.
 */
export {
  classifyOutcome,
  type OptimisticOutcome,
  type VersionedTarget,
  versionAdvancingUpdate,
  versionedUpdate,
} from "./optimistic.js";
